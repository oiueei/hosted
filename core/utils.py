"""
Utility functions for OIUEEI.
"""

import hashlib
import hmac
import ipaddress
import json
import secrets
import string

from django.conf import settings


def redact_email(email):
    """Return a keyed, non-reversible tag for an email, safe to write to logs.

    An HMAC-SHA256 (keyed by ``SECRET_KEY``) prefix — never the address — so ops
    can still correlate events for the same user (same email → same tag) without
    writing PII, and without the tag being recoverable via a dictionary attack on
    a bare hash of a low-entropy email (M5). Tags change if ``SECRET_KEY`` rotates.
    """
    if not email:
        return "email#none"
    digest = hmac.new(
        settings.SECRET_KEY.encode(), email.strip().lower().encode(), hashlib.sha256
    ).hexdigest()[:12]
    return f"email#{digest}"


def generate_id():
    """Generate a unique 6-character alphanumeric ID in uppercase."""
    chars = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(6))


def generate_token():
    """Generate a high-entropy URL token for email/magic links.

    26 lowercase alphanumeric characters from a 36-symbol alphabet via
    ``secrets.choice`` → ~134 bits of entropy (log2(36**26)). Used for the RSVP
    ``token`` column that backs every email action link, so the link can't be
    brute-forced the way the 6-char PK (~31 bits) could. Lowercase-only keeps the
    alphabet unambiguous in URLs and avoids the entropy collapse of
    ``token_urlsafe().lower()``.
    """
    chars = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(chars) for _ in range(26))


# Every request that cannot be tied to a parseable address shares this bucket.
# Fail-closed on purpose: they are rate-limited together rather than each getting
# a fresh allowance. It is a real IPv4 address, which matters — django-ratelimit
# feeds whatever we return straight into ``ipaddress.ip_network()``.
UNKNOWN_CLIENT_IP = "0.0.0.0"  # noqa: S104 — a bucket key, never a bind address.


def _valid_ip(value):
    """``value`` if it parses as an IP address, else ``None``."""
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return None
    return value


def get_client_ip(request):
    """The client's IP address: the rate-limit bucket key, and what we log.

    ``X-Forwarded-For`` is written by whoever is upstream, and the part of it that
    can be trusted is only the tail a proxy we control appended — everything to
    the left of that is the client's own text. ``TRUSTED_PROXY_COUNT`` says how
    many hops that is, so the entry we read is counted from the **right**:

    - ``1`` (default) — one trusted proxy, the Heroku router. It appends the
      connecting client's address, so the last entry is the genuine one and
      anything the client prepended is ignored.
    - ``0`` — nothing trusted in front of the app. ``X-Forwarded-For`` is then
      entirely client-supplied and is not read at all; ``REMOTE_ADDR`` is the
      only honest source. **This is the setting for a deployment that terminates
      connections directly**, where trusting the header would let one caller mint
      a fresh rate-limit bucket per request — every IP limit in the app (magic
      links, join, contact, CSP reports, the admin login) defeated by a header.
    - ``N`` — a CDN in front of the router: skip the CDN's own hops.

    The chosen entry is **validated** before it is returned. django-ratelimit
    passes it to ``ipaddress.ip_network()``, so a value like ``abc`` used to raise
    ``ValueError`` inside the decorator and answer 500 before the view ever ran.
    Anything unparseable — or a chain shorter than the trusted hop count, i.e. a
    request that did not come through the expected proxies — falls back to
    ``REMOTE_ADDR``, and then to ``UNKNOWN_CLIENT_IP``.
    """
    hops = getattr(settings, "TRUSTED_PROXY_COUNT", 1)
    if hops > 0:
        chain = [part.strip() for part in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")]
        chain = [part for part in chain if part]
        if len(chain) >= hops:
            trusted = _valid_ip(chain[-hops])
            if trusted:
                return trusted
    return _valid_ip(request.META.get("REMOTE_ADDR", "")) or UNKNOWN_CLIENT_IP


def parse_localized(value):
    """Read owner content as a ``{lang: text}`` map, or ``None`` if it isn't one.

    Owners of bilingual groups can write a headline, a description or a tag label
    as inline JSON — ``{"es": "Las cosas de mamá", "ca": "Les coses de mama"}`` —
    and every reader sees it in their own language. There is no per-field schema
    behind it: the map lives in the existing CharField, and the parse is what
    makes it a map.

    Deliberately **strict**, because everything it rejects renders verbatim: a
    value only qualifies when it is a JSON *object* whose keys are all languages
    OIUEEI speaks (at least one) and whose values are all non-empty strings.
    Anything else — plain text, a JSON list, ``{"es": ""}``, an unknown key — is
    prose the owner happened to write, and comes back as ``None`` so the caller
    shows it untouched. Surrounding whitespace is tolerated (a pasted example
    usually carries some).
    """
    from core.models.language import Language

    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text.startswith("{"):
        return None
    try:
        parsed = json.loads(text)
    except ValueError:
        return None
    if not isinstance(parsed, dict) or not parsed:
        return None
    languages = set(Language.values)
    for key, text_in_lang in parsed.items():
        if key not in languages:
            return None
        if not isinstance(text_in_lang, str) or not text_in_lang.strip():
            return None
    return parsed


def resolve_localized(value, lang=None):
    """The text a reader of ``lang`` should see for a possibly-localized value.

    Plain text is returned unchanged. A localized map (see ``parse_localized``)
    resolves through ``lang`` → ``es`` → the first key it has, so a reader whose
    language the owner didn't write still gets words rather than JSON.
    """
    localized = parse_localized(value)
    if localized is None:
        return value
    for key in (lang, "es"):
        if key and key in localized:
            return localized[key]
    return next(iter(localized.values()))


def asset_url(key):
    """Public URL of a stored image key, or ``None`` if there is no key.

    Thin on purpose: the key stored on the model *is* the path in the bucket, so
    there is nothing to build beyond the base URL. The Cloudinary version this
    replaces asked for ``f_auto,q_auto`` — automatic format and quality — which
    an object store does not do. That work moved to where the bytes are: the
    browser resizes and encodes to WebP before uploading, so the object served
    here is already the one we want served.
    """
    from core.services import storage

    return storage.public_url(key)


def doc_asset_url(key):
    """Public URL of an uploaded PDF (``Collection.welcome_doc``).

    Identical to :func:`asset_url` today, and kept separate anyway. Under
    Cloudinary a PDF needed its own URL shape — it lived under
    ``resource_type=image`` and had to be asked for with a ``.pdf`` extension and
    without the photo transformations. That peculiarity is gone: the object store
    serves the ``Content-Type`` that was signed at upload.

    What has not gone is the reason for a separate function. A document is the
    one asset that travels by email and gets opened weeks later, so it is the one
    most likely to need a ``Content-Disposition``, or a signed URL, or an
    expiring link. When that day comes there is already a place to put it, and
    the photos do not follow it there.
    """
    from core.services import storage

    return storage.public_url(key)
