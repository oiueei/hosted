"""S3-compatible object storage — the only module in the project that imports boto3.

Everything else (the upload ticket view, the delete-on-delete signals, the orphan
sweep, the URL helpers) goes through the small API below, so swapping the
provider again means editing one file. That is not hypothetical: this module
exists because Cloudinary served images from the United States and the GDPR work
needed them inside the EU.

**Buckets are private; objects are public.** The bucket must never be listable —
a listable bucket makes the photos of a *private* collection enumerable by
anyone who knows the bucket name, which would be a real privacy regression
against Cloudinary. Public reads work because every object is uploaded with
``x-amz-acl: public-read``, signed by us and not chosen by the client. Keys are
unguessable (``secrets.token_urlsafe(16)``, 128 bits), exactly as before.

Notes from the verification spike, kept here because they are the sort of thing
that gets painfully rediscovered six months later:

- **Checksums.** botocore 1.36 began sending ``x-amz-checksum-crc32`` by default
  and dropping ``Content-MD5``; several S3-compatible providers reject it (OVH
  did), and the call it breaks first is ``delete_objects`` — the one the orphan
  sweep depends on. Verified against Hetzner on botocore 1.43.78: both
  ``put_object`` and ``delete_objects`` are accepted with the defaults, so the
  ``Config(request_checksum_calculation="when_required", ...)`` rescue is **not**
  needed. If a future bump starts failing there, that is the knob.
- **A freshly created bucket lies.** A tight upload loop against a bucket minutes
  old returned ``NoSuchBucket`` — a 404, with an empty message — part-way
  through, and did not reproduce hours later at the same rate. Whatever the
  cause, botocore does **not** retry a 404, so bulk work against a new bucket
  needs its own retry. Do not point a mass copy at a bucket that was just
  created.
"""

import boto3
from botocore.config import Config
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

# Uploaded keys are random and their contents never change, so the browser may
# keep them forever. There is no CDN in front of the bucket: without this every
# visit is another round trip to Falkenstein.
CACHE_CONTROL = "public, max-age=31536000, immutable"

# S3 caps one DeleteObjects call at 1000 keys.
_DELETE_LIMIT = 1000

_clients = {}


def _config():
    """The five settings this module needs, or an error naming the missing one."""
    values = {
        name: getattr(settings, f"OBJECT_STORAGE_{name.upper()}", "")
        for name in ("endpoint", "bucket", "region", "access_key", "secret_key")
    }
    missing = [f"OBJECT_STORAGE_{name.upper()}" for name, value in values.items() if not value]
    if missing:
        raise ImproperlyConfigured(
            f"Object storage is not configured: {', '.join(missing)} unset. "
            "Uploads and asset deletion need it; serving existing assets does not."
        )
    return values


def client():
    """A cached boto3 S3 client for the configured bucket.

    Cached per credential set rather than with ``lru_cache`` so that a test using
    ``override_settings`` gets a client that matches the settings it just set.
    """
    conf = _config()
    key = tuple(conf.values())
    if key not in _clients:
        _clients[key] = boto3.client(
            "s3",
            endpoint_url=conf["endpoint"],
            region_name=conf["region"],
            aws_access_key_id=conf["access_key"],
            aws_secret_access_key=conf["secret_key"],
            config=Config(
                signature_version="s3v4",
                # Virtual addressing puts the bucket in the hostname, which is what
                # makes the public URL a plain `https://<bucket>.<endpoint>/<key>`.
                s3={"addressing_style": "virtual", "payload_signing_enabled": False},
                retries={"max_attempts": 5, "mode": "standard"},
            ),
        )
    return _clients[key]


def public_url(key):
    """The public URL of a stored key, or ``None`` for an empty key.

    Built from ``MEDIA_PUBLIC_BASE_URL`` rather than from the client, so putting a
    CDN in front of the bucket is a setting and not a code change.
    """
    if not key:
        return None
    return f"{settings.MEDIA_PUBLIC_BASE_URL.rstrip('/')}/{key}"


def presign_upload(key, content_type, content_length, max_bytes):
    """Ticket for one direct browser-to-bucket upload of ``key``.

    Returns ``{"url", "method", "headers"}``. The caller ``PUT``s the file as the
    raw request body with exactly those headers — not multipart form-data.

    Everything that matters is signed into the URL, and a client that changes any
    of it gets 403 rather than a successful upload:

    - ``x-amz-acl: public-read`` — the object is readable, the bucket still is not.
    - ``Content-Type`` — **exact**, and not optional. Without it the object is
      stored as ``binary/octet-stream``, which is how the welcome PDF stops
      opening in the browser's viewer and starts downloading. Signing it also
      means the served type is decided here, so an upload can never come back as
      ``text/html`` and turn the bucket into an XSS origin.
    - ``Cache-Control`` — there is no CDN in front of the bucket, so without this
      every visit is another round trip to Falkenstein.
    - ``Content-Length`` — the size cap, and the reason this is a ``PUT`` and not
      a presigned ``POST``. A POST policy can express a size *range*, which is
      what the plan originally chose, but **Hetzner silently drops the
      ``Cache-Control`` field of a POST policy** — it is not stored, not even as
      metadata. A PUT keeps both: the caller declares the size, this function
      refuses anything over ``max_bytes``, and the exact value is signed.
      Declaring one size and sending another — in either direction — fails with
      ``SignatureDoesNotMatch``. The browser cannot forge it either: JavaScript
      may not set ``Content-Length``, so the value on the wire is always the real
      body length. That is why it is absent from ``headers`` below.

    The size cap being server-side at all is new. Cloudinary could not sign one,
    so until now the only limit on the welcome PDF was an ``if`` in the browser.
    """
    if not 1 <= content_length <= max_bytes:
        raise ValueError(f"upload of {content_length} bytes is outside 1..{max_bytes}")

    url = client().generate_presigned_url(
        "put_object",
        Params={
            "Bucket": _config()["bucket"],
            "Key": key,
            "ACL": "public-read",
            "ContentType": content_type,
            "CacheControl": CACHE_CONTROL,
            "ContentLength": content_length,
        },
        ExpiresIn=600,
    )
    return {
        "url": url,
        "method": "PUT",
        # Sent verbatim by the client. Content-Length is deliberately not here:
        # it is signed, but the browser is the one that sets it.
        "headers": {
            "x-amz-acl": "public-read",
            "Content-Type": content_type,
            "Cache-Control": CACHE_CONTROL,
        },
    }


def delete(key):
    """Delete one object. Deleting a key that isn't there is not an error in S3."""
    if not key:
        return
    client().delete_object(Bucket=_config()["bucket"], Key=key)


def delete_many(keys):
    """Delete many objects, batched. Returns the number of keys requested.

    Missing keys count as deleted, matching ``delete`` and S3 itself: the callers
    are cleanup paths, and "it is already gone" is the outcome they wanted.
    """
    keys = [key for key in keys if key]
    if not keys:
        return 0
    s3, bucket = client(), _config()["bucket"]
    for start in range(0, len(keys), _DELETE_LIMIT):
        batch = keys[start : start + _DELETE_LIMIT]
        s3.delete_objects(
            Bucket=bucket,
            Delete={"Objects": [{"Key": key} for key in batch], "Quiet": True},
        )
    return len(keys)


def iter_objects(prefix=""):
    """Yield every object under ``prefix`` as ``{"key", "last_modified", "size"}``.

    Paginated, because the orphan sweep has to see the whole bucket, and
    ``last_modified`` is included because that sweep's age windows are built on
    it (asking for it per object would be one HEAD per asset).
    """
    paginator = client().get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=_config()["bucket"], Prefix=prefix):
        for obj in page.get("Contents", []):
            yield {
                "key": obj["Key"],
                "last_modified": obj["LastModified"],
                "size": obj["Size"],
            }
