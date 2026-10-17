"""
Middleware for OIUEEI: security headers + first-party daily-activity and device counts.
"""

import logging
from urllib.parse import urlparse

from django.conf import settings
from django.core.cache import cache
from django.db.models import F
from django.utils import timezone

from core.device import device_class

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware:
    """Add Content-Security-Policy and Permissions-Policy headers to every response.

    Enabled in all environments (registered in base MIDDLEWARE), not just
    production, so the API and the served SPA shell always carry a CSP.

    Two deliberate relaxations:
    - ``style-src 'unsafe-inline'`` stays in every environment: HDS components and
      the per-user theeeme set inline ``style`` attributes throughout the React
      app, so dropping it would break styling — the "remove unsafe-inline"
      hardening is not viable for styles.
    - ``script-src`` gains ``'unsafe-inline'`` only under ``DEBUG`` so the dev-only
      DRF browsable API (inline scripts) keeps working; production stays strict.

    And one that is not a relaxation so much as a correction: ``img-src`` names
    ``data:``. HDS draws a large part of its iconography as inline
    ``data:image/svg+xml`` URIs — forty of them in the built ``vendor-hds``
    chunk — so without it the policy blocked an icon on nearly every page, in
    production, for as long as this header has existed. A ``data:`` URI in
    ``img-src`` cannot execute anything: an SVG rendered through ``<img>`` runs
    no script, and ``object-src 'none'`` still refuses the element that would.
    ``font-src`` has carried ``data:`` all along for the same practical reason.
    """

    # Violations are reported to our own endpoint (core/views/csp.py) — a hosted
    # collector would be handed the URL of every page a member visits, which is
    # the tracking DESIGN §9 rules out. Both syntaxes are sent: `report-to` is
    # the current standard and needs the Reporting-Endpoints header to resolve
    # the name, `report-uri` is deprecated but is still what several browsers
    # actually implement. A browser honouring both sends one report, not two.
    REPORT_ENDPOINT = "/api/v1/csp-report/"
    REPORT_GROUP = "csp"

    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def _origin(setting_name):
        """The scheme+host named by a setting, or "" when it names none.

        Derived from settings rather than written in here, which it used to be. A
        literal stopped working the moment there was more than one bucket:
        production and development serve from different hostnames, and a
        deployment pointing storage at its own bucket or a CDN would have had to
        edit this file — a file it should never have to touch — to be allowed to
        load its own images. Only the origin is taken; a path in the setting is
        not part of what CSP matches on.
        """
        base = getattr(settings, setting_name, "")
        if not base:
            return ""
        parsed = urlparse(base)
        return f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""

    @classmethod
    def _asset_origins(cls):
        """``(read, connect)`` — the hosts assets are fetched from and written to.

        **Two settings, because they are two hosts the moment anybody splits
        them.** Reads come from ``MEDIA_PUBLIC_BASE_URL``; a browser upload is a
        ``PUT`` to a presigned URL, which is always signed for the bucket's own
        virtual host (``OBJECT_STORAGE_PUBLIC_URL``) and does not follow a CDN.

        Naming only the read origin is what this did before, and it was correct
        exactly as long as nobody used the setting it read: on the default
        deployment the two coincide. Point ``MEDIA_PUBLIC_BASE_URL`` at a CDN or
        a custom domain — which README and HEROKU.md both invite — and
        ``connect-src`` stopped naming the bucket, so every upload was refused by
        the browser before it left, while the images it had already stored went on
        loading perfectly. A configuration that half-works is worse than one that
        doesn't, and this is the half that fails silently.

        ``connect`` keeps both, deduplicated and in a stable order so the header
        doesn't churn between requests.
        """
        read = cls._origin("MEDIA_PUBLIC_BASE_URL")
        upload = cls._origin("OBJECT_STORAGE_PUBLIC_URL")
        return read, [origin for origin in dict.fromkeys((read, upload)) if origin]

    def __call__(self, request):
        response = self.get_response(request)
        script_src = (
            "script-src 'self' 'unsafe-inline'; " if settings.DEBUG else "script-src 'self'; "
        )
        read_origin, connect_origins = self._asset_origins()
        img = f" {read_origin}" if read_origin else ""
        connect = "".join(f" {origin}" for origin in connect_origins)
        response["Content-Security-Policy"] = (
            "default-src 'self'; " + script_src + "style-src 'self' 'unsafe-inline'; "
            f"img-src 'self' blob: data:{img}; "
            "font-src 'self' data:; "
            f"connect-src 'self'{connect}; "
            "frame-ancestors 'none'; "
            "object-src 'none'; "
            "base-uri 'self'; "
            "form-action 'self'; "
            f"report-uri {self.REPORT_ENDPOINT}; "
            f"report-to {self.REPORT_GROUP}; "
        )
        response["Reporting-Endpoints"] = f'{self.REPORT_GROUP}="{self.REPORT_ENDPOINT}"'
        response["Permissions-Policy"] = "camera=(), microphone=(), geolocation=(), payment=()"
        return response


class DailyActivityMiddleware:
    """Record that the authenticated user was active today, and count it by device.

    Runs *after* the view so it can read the DRF-authenticated user: this app has no
    Django session (auth is JWT-cookie via DRF authenticators), so ``request.user``
    is only resolved once a view/permission accesses it, at which point DRF writes
    the real user back onto the underlying request. Anonymous / non-DRF requests are
    skipped.

    It does two independent things, each best-effort:

    - **Daily activity**: a cache key (``da:{user}:{date}``, TTL ~24h, on the shared
      DatabaseCache) gates the write so it costs one ``DailyActivity`` row per user
      per day, not one per request.
    - **Device counts** (``DeviceDay``, numbers only): ``PEOPLE`` once per person, day
      and kind of device (cache key ``dd:{user}:{date}:{device}``), and ``FORM_SAVES``
      for every successful create (``POST``) or edit (``PATCH``/``PUT``) of a
      collection or a thing. The row holds the date, the device group, the metric and
      a count: never the user and never the ``User-Agent``. It is counted whatever
      the activity gate said, so a second device the same day still counts.

    The two gates' keys are read in **one** cache query (the cache is the database, so one
    ``get`` each was two SELECTs on every request with a session); if that read fails, both
    steps are skipped.

    Any failure here is swallowed — bookkeeping must never turn a successful
    response into a 500, and one count failing must not lose the other (DESIGN §9:
    this stays first-party, in our DB).
    """

    CACHE_TTL = 60 * 60 * 24  # ~24h; the date is in the key, so it rolls over anyway.

    # The router's own names: `things` / `collections`, creating (list, POST) or
    # editing (detail, PATCH/PUT).
    SAVE_ROUTES = {
        ("collection-list", "POST"),
        ("thing-list", "POST"),
        ("collection-detail", "PATCH"),
        ("collection-detail", "PUT"),
        ("thing-detail", "PATCH"),
        ("thing-detail", "PUT"),
    }

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            user_code = self._user_code(request)
            device = device_class(request) if user_code else None
            today = timezone.localdate()
            keys = self._keys(user_code, device, today)
            # One query for both gates: the cache is the database, so two `get`s were two
            # SELECTs on every request with a session.
            cached = cache.get_many(list(keys.values())) if keys else {}
        except Exception:  # noqa: BLE001 — never let tracking break the response.
            logger.warning("Daily activity cache read failed", exc_info=True)
            return response
        try:
            self._record(user_code, today, keys.get("da"), cached)
        except Exception:  # noqa: BLE001 — never let tracking break the response.
            logger.warning("DailyActivity recording failed", exc_info=True)
        try:
            self._count_device(request, response, user_code, device, today, keys.get("dd"), cached)
        except Exception:  # noqa: BLE001 — same: a count never breaks the response.
            logger.warning("DeviceDay counting failed", exc_info=True)
        return response

    @staticmethod
    def _user_code(request):
        user = getattr(request, "user", None)
        if user is None or not getattr(user, "is_authenticated", False):
            return None
        return getattr(user, "code", None) or None

    @staticmethod
    def _keys(user_code, device, today):
        """The cache keys this request's two gates read, by name; none for no session."""
        if not user_code:
            return {}
        day = today.isoformat()
        keys = {"da": f"da:{user_code}:{day}"}
        if device is not None:
            keys["dd"] = f"dd:{user_code}:{day}:{device}"
        return keys

    def _record(self, user_code, today, cache_key, cached):
        if not user_code or cached.get(cache_key):
            return

        from core.models.activity import DailyActivity

        # get_or_create (not create) so a warm-DB / cold-cache request can't trip the
        # unique(user, date) constraint.
        DailyActivity.objects.get_or_create(user_id=user_code, date=today)
        cache.set(cache_key, 1, self.CACHE_TTL)

    def _count_device(self, request, response, user_code, device, today, cache_key, cached):
        if not user_code or device is None:
            return

        from core.models.activity import DeviceDay

        if not cached.get(cache_key):
            self._bump(DeviceDay, today, device, DeviceDay.PEOPLE)
            cache.set(cache_key, 1, self.CACHE_TTL)

        match = getattr(request, "resolver_match", None)
        if (
            match is not None
            and response.status_code in (200, 201)
            and (match.url_name, request.method) in self.SAVE_ROUTES
        ):
            self._bump(DeviceDay, today, device, DeviceDay.FORM_SAVES)

    @staticmethod
    def _bump(model, day, device, metric):
        """Add one to the day's count, in the database: never read, add and save."""
        row, _ = model.objects.get_or_create(date=day, device=device, metric=metric)
        model.objects.filter(pk=row.pk).update(count=F("count") + 1)
