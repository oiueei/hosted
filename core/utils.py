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


def cloudinary_url(image_id):
    """Build Cloudinary URL from a stored public_id."""
    if not image_id:
        return None
    import cloudinary.utils

    url, _ = cloudinary.utils.cloudinary_url(image_id, fetch_format="auto", quality="auto")
    return url


def cloudinary_doc_url(public_id):
    """Build the delivery URL of an uploaded PDF (``Collection.welcome_doc``).

    Cloudinary stores a PDF under ``resource_type=image`` (it treats it as a
    page-based image), so the id lives in the same namespace as the photos — but
    the URL must carry the ``.pdf`` extension and **no** ``f_auto``/``q_auto``:
    those are photo transformations and would ask Cloudinary to re-encode the
    document instead of serving it. Delivery also requires "Allow delivery of PDF
    and ZIP files" to be on in the account's security settings (it is).
    """
    if not public_id:
        return None
    import cloudinary.utils

    url, _ = cloudinary.utils.cloudinary_url(public_id, resource_type="image", format="pdf")
    return url
