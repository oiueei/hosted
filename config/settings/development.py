"""
Development settings for OIUEEI project.
Uses SQLite and console email backend.
"""

import os

from .base import *  # noqa: F401, F403

DEBUG = True

# Disable rate limiting in development/testing
RATELIMIT_ENABLE = False

# Database: SQLite for development.
#
# DEV_DB_NAME points the whole thing at a throwaway file, which is what makes a
# migration rehearsal safe: seed the "before" rows, migrate, inspect the result,
# delete the file — without any of it landing in the working DB. Unset (the
# normal case) it falls back to db.sqlite3 exactly as before.
#
#   DEV_DB_NAME=/tmp/rehearsal.sqlite3 python manage.py migrate core 0121
#
# Production never reaches here: production.py builds DATABASES from DATABASE_URL.
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
