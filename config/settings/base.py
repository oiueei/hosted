"""
Base settings for OIUEEI project.
"""

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("DJANGO_SECRET_KEY environment variable must be set")

# SECURITY WARNING: don't run with debug turned on in production!
# Default False (fail-closed): a missing/typo'd DJANGO_DEBUG must NOT leak
# stack traces or drop the cookie Secure flag. development.py opts back in.
DEBUG = os.environ.get("DJANGO_DEBUG", "False").lower() == "true"

ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")


# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "corsheaders",
    "rest_framework_simplejwt.token_blacklist",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "django_otp.plugins.otp_static",
    # Local
    "core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Apply CSP/Permissions-Policy in every environment, not just production (I5).
    # Production additionally inserts WhiteNoise right after this so the SPA shell
    # it serves still gets these headers.
    "core.middleware.SecurityHeadersMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Resolves request.user's OTP verification state — required by OTPAdminSite
    # (config/urls.py) to gate admin login behind a second factor.
    "django_otp.middleware.OTPMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Innermost (after the view): records the DRF-authenticated user's daily
    # activity — request.user is only resolved once a DRF view touches it.
    "core.middleware.DailyActivityMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Password validation (for admin users - regular users use magic link)
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


# Static files (CSS, JavaScript, Images)
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"


# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Cache
# A shared backend so rate-limit counters are consistent across gunicorn
# workers and dynos — the default per-process LocMemCache is NOT shared, so
# counters would multiply per worker and reset on every dyno cycle.
# DatabaseCache reuses the existing PostgreSQL add-on at zero extra cost;
# the cache table is created by migration (see core/migrations).
# Note (I7): DatabaseCache increments are not atomic, so under heavy concurrency
# a rate-limit counter can slightly under-count (a few requests over the limit).
# Accepted: the limits are coarse abuse-prevention, not exact quotas.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "oiueei_cache",
    }
}


# REST Framework settings
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "core.authentication.CookieJWTAuthentication",
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
    "EXCEPTION_HANDLER": "core.exceptions.api_exception_handler",
    "DEFAULT_PAGINATION_CLASS": "core.pagination.StandardResultsPagination",
    "PAGE_SIZE": 20,
}


# JWT signing key — defaults to SECRET_KEY but can be set independently via the
# JWT_SIGNING_KEY env var, so the two can be rotated separately. Rotating
# SECRET_KEY alone would otherwise also invalidate every issued JWT.
JWT_SIGNING_KEY = os.environ.get("JWT_SIGNING_KEY", SECRET_KEY)

# Simple JWT settings
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=1),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": JWT_SIGNING_KEY,
    "AUTH_HEADER_TYPES": ("Bearer",),
    "USER_ID_FIELD": "code",
    "USER_ID_CLAIM": "user_code",
}


# CORS settings
CORS_ALLOWED_ORIGINS = os.environ.get(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
).split(",")

CORS_ALLOW_CREDENTIALS = True


# CSRF settings
CSRF_COOKIE_HTTPONLY = False  # React needs to read the cookie
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_TRUSTED_ORIGINS = os.environ.get(
    "CSRF_TRUSTED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
).split(",")


# Rate limiting (django-ratelimit)
# Bucket limiters per REAL client IP. The built-in "ip" key reads
# REMOTE_ADDR, which behind the Heroku router is a single shared proxy
# address — collapsing every client into one bucket (so "5/m per IP" becomes
# "5/m for everyone", letting one abuser lock out all users). Point it at our
# anti-spoofing helper, which takes the rightmost X-Forwarded-For value
# appended by the Heroku router. Accepts a dotted path called as fn(request).
RATELIMIT_IP_META_KEY = "core.utils.get_client_ip"

# How many proxies in front of this app are trusted to have appended to
# X-Forwarded-For. It decides which entry `core.utils.get_client_ip` reads —
# counted from the right, since only the tail was written by a proxy we control.
#
# The default of 1 is the Heroku router, which appends the connecting client's
# address: the last entry is genuine and anything the client prepended is
# ignored. **A deployment that terminates connections directly must set 0** —
# there, the whole header is client-supplied, and reading it lets one caller mint
# a fresh rate-limit bucket per request, defeating every IP limit in the app.
# Raise it above 1 only when another trusted proxy (a CDN) sits in front.
TRUSTED_PROXY_COUNT = int(os.environ.get("TRUSTED_PROXY_COUNT", "1"))

# Invitation emails one account may send per day. This is **operator policy,
# not a product rule**: it protects the deployment's own sending domain and
# reputation, and only the operator knows what their provider tolerates. The
# standalone default is therefore **unlimited** — a self-hoster decides for
# their own instance — while www.oiueei.com sets the config var explicitly.
#
# 0 (or unset) means no limit. Also gated by RATELIMIT_ENABLE, which switches
# the whole rate-limiting layer off in development and tests.
INVITE_EMAILS_PER_DAY = int(os.environ.get("INVITE_EMAILS_PER_DAY", "0"))

# How many people one collection may be joined by per day through
# `POST /auth/join/`. The invitation cap above guards the doors an *account*
# sends through; this guards the one that needs no account, where the address
# mailed is whatever a stranger typed and the collection code is public by
# construction. Without it the per-IP limit is all that stands between the
# operator's sending domain and a hundred IPs mailing a hundred strangers each.
#
# Keyed per collection so abusing one group's public code costs that group its
# day and leaves every other collection working — a deployment-wide counter
# would hand the attacker a way to shut joining off for everyone.
#
# 0 (or unset) means no limit, and that is the standalone default: a share link
# pasted into a group chat can legitimately bring in two hundred people in an
# evening. Also gated by RATELIMIT_ENABLE. See `core/services/join_quota.py`.
COLLECTION_JOINS_PER_DAY = int(os.environ.get("COLLECTION_JOINS_PER_DAY", "0"))

# Per-collection capacity guards against mass upload. Same reasoning as the
# invitation cap above: this is the operator protecting their own storage,
# Cloudinary bill and moderation load, so the standalone default is **off** and
# each deployment sets its own numbers.
#
# COLLECTION_THINGS_ALARM — cross it and the operator gets ONE email per
#   collection. The owner is never told: a silent tripwire, not a warning, so a
#   real bulk import is not interrupted and someone abusing the endpoint is not
#   told where the line sits.
# COLLECTION_THINGS_BLOCK — adds that would cross it are refused (400) until a
#   superuser ticks `capacity_unblocked` on the collection in the admin.
#
# 0 (or unset) disables each independently. Unlike the invitation cap these do
# NOT follow RATELIMIT_ENABLE: they are a storage ceiling rather than a rate,
# and a test that sets them means to exercise them.
COLLECTION_THINGS_ALARM = int(os.environ.get("COLLECTION_THINGS_ALARM", "0"))
COLLECTION_THINGS_BLOCK = int(os.environ.get("COLLECTION_THINGS_BLOCK", "0"))
COLLECTION_INVITES_ALARM = int(os.environ.get("COLLECTION_INVITES_ALARM", "0"))
COLLECTION_INVITES_BLOCK = int(os.environ.get("COLLECTION_INVITES_BLOCK", "0"))

# Extra URL modules this deployment mounts alongside the product's own routes.
# The standalone ships **none**: everything OIUEEI does as a product already
# lives in `core.urls`.
#
# It exists so a deployment can add views of its own — an operator's service
# layer, a self-hoster's intranet page — **without editing `config/urls.py`**.
# That file is the one both would otherwise have to patch, and re-patch, on
# every update; naming a module here instead is what lets those routes survive
# an upgrade untouched.
#
# Comma-separated dotted paths, e.g. "deployment.urls,intranet.urls". Each is
# mounted at the root and, deliberately, **before** the SPA catch-all — see
# `config/urls.py`, where that ordering is the whole point.
DEPLOYMENT_URLCONFS = [
    module.strip()
    for module in os.environ.get("DEPLOYMENT_URLCONFS", "").split(",")
    if module.strip()
]

# Who may create which kind of collection, and offer a thing under which verb.
# The default says **yes to everyone, always**, which is OIUEEI as a product:
# an account is the only requirement to open a collection or offer a thing.
#
# A deployment with a narrower answer — a cooperative where only the board opens
# COMMUNITY collections, an operator who vets whoever asks to lend — points this
# at its own subclass instead of editing the serializers. Both the enforcement
# and the capabilities the SPA reads from `GET /auth/me/` come from it, so the
# UI can never offer what the API would refuse. See `core/services/creator_policy.py`.
CREATOR_POLICY = os.environ.get("CREATOR_POLICY", "core.services.creator_policy.OpenCreatorPolicy")


# Retention periods (GDPR art. 5.1.e), in months unless the name says otherwise.
#
# Nothing here happens on its own: `python manage.py purge_expired_data` is what
# enforces them, and it has to be scheduled (see README §Scheduled jobs). The
# defaults are the ones www.oiueei.com decided in its retention table, and they
# are shipped ON because a period that protects the people in the database is a
# better default than "forever" — but they are still **operator policy**, and a
# deployment under a different regime overrides any of them. **0 means keep
# indefinitely**, the same "0 = off" idiom as the quota settings above.
#
# `Event` is anonymised rather than deleted: what expires is the link to a
# person (`actor_code`), not the fact, so the history survives as aggregate.
RETENTION_INACTIVE_ACCOUNT_MONTHS = int(os.environ.get("RETENTION_INACTIVE_ACCOUNT_MONTHS", "24"))
RETENTION_INACTIVE_WARNING_DAYS = int(os.environ.get("RETENTION_INACTIVE_WARNING_DAYS", "30"))
RETENTION_UNVISITED_GUEST_DAYS = int(os.environ.get("RETENTION_UNVISITED_GUEST_DAYS", "60"))
RETENTION_EVENT_ANONYMISE_MONTHS = int(os.environ.get("RETENTION_EVENT_ANONYMISE_MONTHS", "14"))
RETENTION_DAILY_ACTIVITY_MONTHS = int(os.environ.get("RETENTION_DAILY_ACTIVITY_MONTHS", "26"))
RETENTION_NOTIFICATION_MONTHS = int(os.environ.get("RETENTION_NOTIFICATION_MONTHS", "12"))
RETENTION_REPORT_MONTHS = int(os.environ.get("RETENTION_REPORT_MONTHS", "12"))


# Custom User Model
AUTH_USER_MODEL = "core.User"


# Magic Link settings
MAGIC_LINK_EXPIRY_HOURS = 24
# Send magic-link emails off the request thread (constant-time response, so the
# request-link timing can't reveal whether an email is registered — L10).
# Off by default so dev/test send synchronously and stay deterministic;
# production.py turns it on.
EMAIL_SEND_ASYNC = False
# The single language all outbound email speaks (core/services/email_texts/):
# the open-source standalone defaults to English; a deployment sets e.g.
# EMAIL_LANGUAGE=es. Unknown codes fall back to English per key.
EMAIL_LANGUAGE = os.environ.get("EMAIL_LANGUAGE", "en")
MAGIC_LINK_BASE_URL = os.environ.get(
    "MAGIC_LINK_BASE_URL",
    "http://localhost:3000/verify",
)
RSVP_BASE_URL = os.environ.get(
    "RSVP_BASE_URL",
    "http://localhost:3000/rsvp",
)
SHARE_LINK_BASE_URL = os.environ.get(
    "SHARE_LINK_BASE_URL",
    "http://localhost:3000/share",
)


# Object storage (S3-compatible). It replaced Cloudinary, which served the images
# from the United States — see `core/services/storage.py`, the only module that
# talks to it.
#
# Unset, the app starts and serves fine; uploads and asset deletion are what
# fail. That is what keeps a checkout runnable without an account.
OBJECT_STORAGE_ENDPOINT = os.environ.get("OBJECT_STORAGE_ENDPOINT", "")
OBJECT_STORAGE_BUCKET = os.environ.get("OBJECT_STORAGE_BUCKET", "")
OBJECT_STORAGE_REGION = os.environ.get("OBJECT_STORAGE_REGION", "")
OBJECT_STORAGE_ACCESS_KEY = os.environ.get("OBJECT_STORAGE_ACCESS_KEY", "")
OBJECT_STORAGE_SECRET_KEY = os.environ.get("OBJECT_STORAGE_SECRET_KEY", "")

# The bucket's own virtual-host URL — **where an upload goes**. A presigned URL
# is signed for this host and no other, so this is the origin the browser has to
# be allowed to PUT to, whatever reads are pointed at.
_endpoint_host = OBJECT_STORAGE_ENDPOINT.split("://", 1)[-1].strip("/")
OBJECT_STORAGE_PUBLIC_URL = (
    f"https://{OBJECT_STORAGE_BUCKET}.{_endpoint_host}"
    if OBJECT_STORAGE_BUCKET and _endpoint_host
    else ""
)

# Where assets are **read** from. Defaults to the bucket itself, and is
# deliberately **overridable**: pointing it at a CDN or a custom domain is then a
# config var, not a patch.
#
# The two are separate settings because they are separate hosts the moment
# anybody uses that override, and the CSP needs both — reads from here, writes
# from the bucket above. Deriving one from the other is what made
# `MEDIA_PUBLIC_BASE_URL=https://cdn.example.com` silently forbid every upload.
MEDIA_PUBLIC_BASE_URL = os.environ.get("MEDIA_PUBLIC_BASE_URL", "") or OBJECT_STORAGE_PUBLIC_URL


# Security Headers
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
# X-XSS-Protection (SECURE_BROWSER_XSS_FILTER) intentionally omitted: the header
# is deprecated and the strong CSP (script-src 'self') already supersedes it.

# django-otp: label shown alongside the account name in authenticator apps.
OTP_TOTP_ISSUER = "OIUEEI"
