"""Throttles for the DRF API.

## `AnonymousApiThrottle` — one ceiling for everything a visitor with no session reads

A PUBLIC collection is readable by anyone: its things, calendars, FAQ and
journeys answer without a login, which is the point of them. It also means that
before this class a script could read them as fast as the dynos would answer —
scraping a group's members and things, and multiplying the queries each read costs
for nobody's benefit. The endpoints that *write* already carried their own
per-IP limits (`@ratelimit` on the magic link, join, contact…); the reads did not.

It is deliberately **built on django-ratelimit, not on DRF's `AnonRateThrottle`**.
DRF identifies a caller by `REMOTE_ADDR` or a naive `X-Forwarded-For` split, which
behind the Heroku router is either one shared proxy address (every visitor in one
bucket) or a header the client wrote (a fresh bucket per request). This project
already settled who "the client's IP" is — `RATELIMIT_IP_META_KEY` →
`core.utils.get_client_ip`, honouring `TRUSTED_PROXY_COUNT` — and every other limit
in the app reads it. Going through `get_usage` means this one cannot disagree.

Points worth knowing before changing it:

- **It counts only requests with no session.** A signed-in member is never
  throttled here; the per-user limits on the endpoints that need them stay as
  they were.
- **DRF checks permissions before throttles**, so a 401 or 403 never spends quota.
  Correct as it is: an anonymous probe of an authenticated endpoint costs the
  operator nothing to refuse.
- **`ANON_API_RATE=0` (or empty) switches it off**, and so does `RATELIMIT_ENABLE =
  False` (development and the test suite), for which `get_usage` answers `None`.
- **The counter lives in `CACHES["default"]`**, a DatabaseCache in production: one
  more query per anonymous request, and the same non-atomic increment note as every
  other limit (a burst can slip a few requests past the line). Coarse abuse
  prevention, not an exact quota.
- **A cache that cannot be read or written fails closed**, django-ratelimit's own
  default (`RATELIMIT_FAIL_OPEN` is not set): the request is refused with a 429.
  The library reaches that only when a counter vanishes between `add` and `incr`,
  which is rare, and it is the behaviour of every limit in the app.
"""

from django.conf import settings
from django_ratelimit.core import get_usage
from rest_framework.throttling import BaseThrottle


class AnonymousApiThrottle(BaseThrottle):
    """At most ``settings.ANON_API_RATE`` API requests per IP while not signed in."""

    def __init__(self):
        # DRF builds one throttle per request, so this is that request's alone.
        self._time_left = None

    def allow_request(self, request, view):
        rate = str(getattr(settings, "ANON_API_RATE", "") or "").strip()
        if request.user.is_authenticated or rate in ("", "0"):
            return True
        usage = get_usage(request, group="anon-api", key="ip", rate=rate, increment=True)
        if usage is None:  # RATELIMIT_ENABLE=False: the whole layer is off
            return True
        if usage["should_limit"]:
            self._time_left = usage["time_left"]
            return False
        return True

    def wait(self):
        """Seconds until the window closes, for DRF's ``Retry-After`` header."""
        if self._time_left is None:
            return None
        # ``time_left`` is -1 when the cache itself failed; a header of -1 is not
        # a time, so say "try again in a second".
        return max(int(self._time_left), 1)
