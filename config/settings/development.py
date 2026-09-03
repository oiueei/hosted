"""
Development settings for OIUEEI project.
Uses SQLite and console email backend.
"""

import os

from .base import *  # noqa: F401, F403

DEBUG = True

# Disable rate limiting in development/testing
RATELIMIT_ENABLE = False

# Database: SQLite locally, PostgreSQL wherever DATABASE_URL says so.
#
# **DATABASE_URL is what CI sets**, so the suite runs on the engine production
# runs on. It is not a nicety: SQLite reports `has_select_for_update = False`, so
# Django *silently drops* the FOR UPDATE clause — no warning, the query just runs
# unlocked. Every row-locked path in this app (accepting, rejecting and
# cancelling a booking in `booking_service`, the capacity recheck in
# `views/things.py`) therefore proved only that its logic reads correctly in one
# process, never that the lock held. SQLite also doesn't enforce
# `CharField(max_length=N)`, which PostgreSQL does.
#
# DEV_DB_NAME points the SQLite path at a throwaway file, which is what makes a
# migration rehearsal safe: seed the "before" rows, migrate, inspect the result,
# delete the file — without any of it landing in the working DB. Unset (the
# normal case) it falls back to db.sqlite3 exactly as before.
#
#   DEV_DB_NAME=/tmp/rehearsal.sqlite3 python manage.py migrate core 0121
#
# Production never reaches this file: production.py builds DATABASES from
# DATABASE_URL on its own, with SSL required and connection pooling.
if os.environ.get("DATABASE_URL"):
    import dj_database_url

    DATABASES = {"default": dj_database_url.config(conn_max_age=0, ssl_require=False)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": os.environ.get("DEV_DB_NAME") or BASE_DIR / "db.sqlite3",  # noqa: F405
        }
    }

# Email: Console backend for development
# Magic link emails will be printed to the terminal
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# CORS: Only allow specific origins (not all)
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
CORS_ALLOW_CREDENTIALS = True

# Logging with security logger
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
        "security": {
            "format": "{levelname} {asctime} [SECURITY] {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
        "security_console": {
            "class": "logging.StreamHandler",
            "formatter": "security",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "security": {
            "handlers": ["security_console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# ─────────────────────────────────────────────────────────────
# THE SERVICE LAYER OF THIS DEPLOYMENT (this deployment only)
#
# `hosted/` is this operator's own app: the open sign-up door, the page saying
# what this service is, who may run a community collection or lend things, and
# whatever any of it costs. It is not part of what OIUEEI distributes — see
# SELF_HOSTING.md — and it only ever adds: it mounts its own URLs, supplies
# its own policy, and imports from `core` while `core` knows nothing about it.
#
# Declared in code rather than left to config vars on purpose. An app installed
# with its routes unmounted fails **silently** — the deployment simply stops
# answering a URL it used to — and that is not a thing to leave to remembering
# two Heroku settings. Anything the environment adds is kept alongside.
# ─────────────────────────────────────────────────────────────
INSTALLED_APPS += ["hosted"]  # noqa: F405
DEPLOYMENT_URLCONFS = [*DEPLOYMENT_URLCONFS, "hosted.urls"]  # noqa: F405

# Present in development too so `pytest` — which runs on these settings — sees the
# app's models and routes. Without it the suite in this repo would exercise the
# upstream product only, and the service layer would ship untested.
