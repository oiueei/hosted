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
from botocore.exceptions import ClientError
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

# Uploaded keys are random and their contents never change, so the browser may
# keep them forever. There is no CDN in front of the bucket: without this every
# visit is another round trip to Falkenstein.
CACHE_CONTROL = "public, max-age=31536000, immutable"

# The demo's fixture images — a **shared, static pool**. Every database that has
# ever run `seed_demo` points at these same objects, so they do not belong to the
# rows that reference them and no single delete may take them away. Both sweeps
# that could destroy them (the orphan sweep and the delete-time cleanup) skip this
# prefix, and both read it from here so the two can never drift apart.
SEED_PREFIX = "oiueei/seed/"

# The folders this project stores assets in, one per kind of thing that owns one.
# `views/upload.py` decides which of them a ticket may be signed for;
# `validators.validate_key_folder` refuses a key that names one of the others.
# Both read this, so the set cannot drift between the door and the field —
# the same reason SEED_PREFIX lives here rather than in each sweep.
USER_FOLDER = "oiueei/users"
THING_FOLDER = "oiueei/things"
COLLECTION_FOLDER = "oiueei/collections"
DOCUMENT_FOLDER = "oiueei/documents"
ASSET_FOLDERS = frozenset({USER_FOLDER, THING_FOLDER, COLLECTION_FOLDER, DOCUMENT_FOLDER})

# S3 caps one DeleteObjects call at 1000 keys.
_DELETE_LIMIT = 1000

# ── CORS: what the *bucket* has to allow, as opposed to what we sign ──────────
#
# The browser writes to the bucket cross-origin — the app is served from the
# deployment's own domain and the presigned PUT goes to the bucket's virtual
# host. That request carries ``x-amz-acl`` and ``Cache-Control``, so it is never
# a "simple" request: the browser sends a preflight ``OPTIONS`` first, and a
# store with no CORS configuration answers it **403**. Ceph answers it with a
# ``SignatureDoesNotMatch`` body, which reads like a signing bug and is not one —
# a preflight carries none of the signed headers, because it is the browser
# asking permission rather than the app uploading.
#
# Nothing on our side sees any of it. The ticket was issued, the credentials are
# right, the signature is right, and the file never leaves the laptop. Reads go
# on working throughout, because an ``<img src>`` is not a cross-origin request
# in the CORS sense and needs no rules at all — which is how a bucket can serve
# every photo it holds while accepting no new one.
#
# ``manage.py set_bucket_cors`` writes these. They are declared *here* because
# this is the module that owns the bucket, and because ``presign_upload`` above
# is what decides the three headers the rules have to allow: two lists that must
# agree, kept in one file.
CORS_METHODS = ("PUT",)
# Exactly the headers ``presign_upload`` returns. ``Content-Length`` is signed
# too but is deliberately absent: it is a forbidden header name, set by the
# browser itself, and never named in a preflight.
CORS_HEADERS = ("Content-Type", "Cache-Control", "x-amz-acl")
# One hour of preflight cache. The number that matters is the ZIP import: a
# hundred rows with a photo each is a hundred uploads, and without this it is
# also a hundred extra round trips to Falkenstein before any of them starts.
CORS_MAX_AGE_SECONDS = 3600


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


def bucket_name():
    """The configured bucket, or ``ImproperlyConfigured`` naming what is unset.

    A named accessor because callers outside this module want the bucket for a
    message ("Bucket: oiueei") and reaching into ``_config()`` for it is how a
    private helper becomes public by habit rather than by decision.
    """
    return _config()["bucket"]


def public_url(key):
    """The public URL of a stored key, or ``None`` if there cannot be one.

    Built from ``MEDIA_PUBLIC_BASE_URL`` rather than from the client, so putting a
    CDN in front of the bucket is a setting and not a code change.

    ``None`` covers two cases, and the second is the one worth stating: an empty
    key (the field was never set), and **no configured base URL** (a checkout with
    no storage account). Joining a key onto an empty base would produce ``/key`` —
    a relative link back to Django, which answers 404. Callers already treat None
    as "no image"; a 404 they would render as a broken one.
    """
    if not key or not settings.MEDIA_PUBLIC_BASE_URL:
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


def cors_rules(origins, max_age=CORS_MAX_AGE_SECONDS):
    """The rule set this project needs for ``origins``. Pure — no network.

    One rule holding every origin, not one rule each: a CORS rule already takes a
    list, and the browser matches the request's ``Origin`` against the whole set.

    ``GET`` is deliberately not among the methods. Reads are ``<img src>``, which
    works against a bucket with no rules whatsoever — that is exactly what this
    deployment did for a week — so allowing it would widen the policy for a
    request nobody makes.
    """
    return [
        {
            "AllowedOrigins": list(origins),
            "AllowedMethods": list(CORS_METHODS),
            "AllowedHeaders": list(CORS_HEADERS),
            "MaxAgeSeconds": max_age,
        }
    ]


def get_cors():
    """The bucket's CORS rules, or ``[]`` when it has none.

    A bucket that was never configured answers ``NoSuchCORSConfiguration``
    rather than an empty list. Having none is the state every fresh bucket is in,
    so that is an answer here and not an error.
    """
    try:
        return client().get_bucket_cors(Bucket=_config()["bucket"]).get("CORSRules", [])
    except ClientError as exc:
        error = exc.response.get("Error", {})
        status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if error.get("Code", "").startswith("NoSuchCORSConfiguration") or status == 404:
            return []
        raise


def put_cors(rules):
    """Replace the bucket's CORS configuration with ``rules``.

    Replace, not merge — S3 has no partial update for this, and pretending
    otherwise is how a bucket ends up carrying two half-right policies. Refusing
    to overwrite rules somebody else wrote is the command's job, not this one's:
    this is the door, and it does what it is told.
    """
    client().put_bucket_cors(Bucket=_config()["bucket"], CORSConfiguration={"CORSRules": rules})


def exists(key):
    """Whether ``key`` is already in the bucket. Used to make copies idempotent."""
    try:
        client().head_object(Bucket=_config()["bucket"], Key=key)
        return True
    except ClientError as exc:
        if exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") == 404:
            return False
        raise


def put(key, body, content_type):
    """Upload ``body`` from the server, with the same guarantees a ticket gives.

    The browser path (:func:`presign_upload`) is how user uploads arrive and is
    the one that matters; this is for the server moving bytes it already has —
    seeding, migrating from another provider. Both must produce objects that are
    indistinguishable afterwards, so the ACL, the content type and the cache
    header are the same three the presigned policy signs. An object copied in
    without them is one that reads as ``binary/octet-stream`` and is re-fetched
    on every visit.
    """
    client().put_object(
        Bucket=_config()["bucket"],
        Key=key,
        Body=body,
        ACL="public-read",
        ContentType=content_type,
        CacheControl=CACHE_CONTROL,
    )


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
