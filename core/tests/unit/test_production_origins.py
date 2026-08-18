"""Production does not inherit a developer's laptop as a trusted origin.

`base.py` defaults both origin lists to `http://localhost:3000,...` so the SPA
runs locally with no `.env`. That default is right there and wrong in
production, where an unset config var quietly left `localhost:3000` in the
trusted set of the live site.

CORS was already rebuilt in `production.py` to fail closed; `CSRF_TRUSTED_ORIGINS`
was not, and an inconsistency between two settings that are supposed to share a
rule is precisely the kind that survives a review — both look deliberate.

These are the first tests to load `production.py` at all, which is why they
carry the environment it refuses to boot without. Like `test_database_config.py`,
the module is re-imported under a patched environment rather than read as text:
what matters is the list it actually produces — a settings file asserted as
source is a test of its formatting.

Reloading this one is not free, though, and `_production_settings` says why:
unlike `development.py`, it *mutates* a list `base.py` owns.
"""

import importlib
import os
from unittest import mock

# Enough to get past production.py's own fail-fast checks (`_require_env`, the
# SECRET_KEY length floor). None of it is what the tests are about.
BOOT_ENV = {
    "DJANGO_SECRET_KEY": "x" * 60,
    "DATABASE_URL": "postgres://u:p@localhost:5432/d",
    "DEFAULT_FROM_EMAIL": "noreply@example.org",
    "MAGIC_LINK_BASE_URL": "https://example.org/verify",
    "RSVP_BASE_URL": "https://example.org/rsvp",
    "SHARE_LINK_BASE_URL": "https://example.org/share",
    "CLOUDINARY_URL": "cloudinary://k:s@c",
}

ORIGIN_VARS = ("CSRF_TRUSTED_ORIGINS", "CORS_ALLOWED_ORIGINS")


def _production_settings(env=None):
    """The production settings module, re-imported under ``BOOT_ENV`` + ``env``.

    The import happens **inside** the patched environment: `production.py`
    fails fast on a missing `DEFAULT_FROM_EMAIL` and friends, so importing it
    first and patching second raises before anything can be read.

    `base.MIDDLEWARE` is snapshotted and restored around the reload, and that is
    not defensive tidiness. `production.py` does `MIDDLEWARE.insert(2, ...)` to
    place WhiteNoise, which **mutates the list `base.py` owns** — the same object
    `django.conf.settings` is holding for this very test run, since the test
    settings also do `from .base import *`. Without the restore, each reload
    would push another WhiteNoise entry into the live middleware chain and the
    damage would surface somewhere else entirely, in a test that never mentioned
    settings.
    """
    import config.settings.base as base

    original_middleware = list(base.MIDDLEWARE)
    with mock.patch.dict(os.environ, {**BOOT_ENV, **(env or {})}, clear=False):
        for key in ORIGIN_VARS:
            if not env or key not in env:
                os.environ.pop(key, None)
        import config.settings.production as prod

        try:
            return importlib.reload(prod)
        finally:
            # Slice assignment, not rebinding: everything holding this list —
            # base, the test settings module, the live `settings` object — must
            # see it repaired, and they all reference the same object.
            base.MIDDLEWARE[:] = original_middleware


def test_an_unset_csrf_var_trusts_nobody():
    """The bug. It used to inherit base.py's localhost pair."""
    settings = _production_settings()

    assert settings.CSRF_TRUSTED_ORIGINS == []
    assert not any("localhost" in origin for origin in settings.CSRF_TRUSTED_ORIGINS)


def test_cors_and_csrf_fail_closed_the_same_way():
    """They share a rule, so they must share a default.

    Asserted together rather than one each: the failure this guards is the two
    drifting apart, which a pair of separate tests would let happen as long as
    somebody updated the one they touched.
    """
    settings = _production_settings()

    assert settings.CSRF_TRUSTED_ORIGINS == settings.CORS_ALLOWED_ORIGINS == []


def test_a_cross_domain_frontend_can_still_name_its_origin():
    """Failing closed must not mean the setting stopped working."""
    settings = _production_settings({"CSRF_TRUSTED_ORIGINS": "https://app.example.org"})

    assert settings.CSRF_TRUSTED_ORIGINS == ["https://app.example.org"]


def test_whitespace_and_empty_entries_are_dropped():
    """A trailing comma in a config var must not add an empty trusted origin —
    `"".split(",")` is `[""]`, which is why the comprehension filters."""
    settings = _production_settings(
        {"CSRF_TRUSTED_ORIGINS": " https://a.example.org , https://b.example.org ,"}
    )

    assert settings.CSRF_TRUSTED_ORIGINS == ["https://a.example.org", "https://b.example.org"]
