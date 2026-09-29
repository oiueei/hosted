"""Throttles for the DRF API.

## `AnonymousApiThrottle` — one ceiling for everything a visitor with no session reads

A PUBLIC collection is readable by anyone: its things, calendars, FAQ and
journeys answer without a login, which is the point of them. It also means that
before this class a script could read them as fast as the dynos would answer —
scraping a group's members and things. The endpoints that *write* already carried
their own per-IP limits (`@ratelimit` on the magic link, join, contact…); the reads
did not.

It is deliberately **not DRF's `AnonRateThrottle`**. DRF identifies a caller by
`REMOTE_ADDR` or a naive `X-Forwarded-For` split, which behind the Heroku router is
either one shared proxy address (every visitor in one bucket) or a header the
client wrote (a fresh bucket per request). This project already settled who "the
client's IP" is — `core.utils.get_client_ip`, honouring `TRUSTED_PROXY_COUNT` —
and every other limit in the app reads it; so does this one.

**The count lives in this process's memory, not in the database** (2026-09-29).
The first version counted in `CACHES['default']` through django-ratelimit, like
every other limit — and that is a `DatabaseCache`. Measured: an anonymous read went
from 4 statements to 16, and a request already refused still wrote its counter, so
the ceiling made each read of a flood dearer than no ceiling at all. It also filled
the shared cache table with one key per visitor address per minute, and that table
culls lowest key first — the operator's daily quotas before anything else (see
`CACHES` in `config/settings/base.py`). Here a read, allowed or refused, asks the
database nothing for its count.

What that costs, knowingly:

- **The ceiling is per web process.** Each gunicorn process keeps its own count,
  so one address gets up to `ANON_API_RATE` × processes × dynos before every one of
  them refuses. For what this is for — a script reading as fast as it can — that
  is still a wall; for an exact quota it would be wrong, and none of the limits
  that need exactness (invitations, joins, magic links) use it.
- **A restart forgets the count**, and a Heroku dyno restarts at least daily and
  on every deploy. A window's allowance at most, once.
- **Every other limit is unchanged**: they still count in the shared cache, where
  the numbers have to agree across processes.

Points worth knowing before changing it:

- **It counts only requests with no session.** A signed-in member is never
  throttled here; the per-user limits on the endpoints that need them stay as
  they were.
- **DRF checks permissions before throttles**, so a 401 or 403 never spends quota.
  Correct as it is: an anonymous probe of an authenticated endpoint costs the
  operator nothing to refuse.
- **`ANON_API_RATE=0` (or empty) switches it off**, and so does `RATELIMIT_ENABLE =
  False` (development and the test suite): the one switch for the whole layer.
- **Fixed windows**: `"300/m"` is 300 per calendar minute of the server clock, and
  `Retry-After` says how much of that minute is left.
- **`parse_rate` is the one reading of the setting** — the deploy check
  (`core.checks.check_anon_api_rate`) calls it too, so a value the check lets
  through is one this class can read.
"""

import math
import re
import time

from django.conf import settings
from django.core.cache.backends.locmem import LocMemCache
from rest_framework.throttling import BaseThrottle

from core.utils import get_client_ip

# A count of at least 1, "/", an optional multiplier and a period: "300/m",
# "20/s", "1000/5m". Nothing lenient — "300/M" or "0/m" are mistakes, not rates.
_RATE = re.compile(r"([1-9]\d*)/([1-9]\d*)?([smhd])")
_PERIOD_SECONDS = {"s": 1, "m": 60, "h": 3600, "d": 86400}

# One per process, never shared: that is the point (see the module docstring). A
# LocMemCache rather than a dict for its expiry, its atomic `incr` under a lock,
# and its own cull, which bounds the memory a flood of addresses can take.
_counters = LocMemCache("oiueei-anon-api", {"OPTIONS": {"MAX_ENTRIES": 10_000}})


def parse_rate(value):
    """``"300/m"`` → ``(300, 60)``, ``"1000/5m"`` → ``(1000, 300)``; ``"0"`` or empty
    → ``None`` (the ceiling is off). Anything else raises ``ValueError``."""
    rate = str(value or "").strip()
    if rate in ("", "0"):
        return None
    match = _RATE.fullmatch(rate)
    if not match:
        raise ValueError(f"not a rate: {rate!r}")
    count, multiplier, unit = match.groups()
    return int(count), int(multiplier or 1) * _PERIOD_SECONDS[unit]


def reset_counters():
    """Forget every count in this process — for the test suite, which a shared
    database rolled back between tests and process memory does not."""
    _counters.clear()


class AnonymousApiThrottle(BaseThrottle):
    """At most ``settings.ANON_API_RATE`` API requests per IP while not signed in,
    counted in this process's memory."""

    def __init__(self):
        # DRF builds one throttle per request, so this is that request's alone.
        self._wait = None

    def allow_request(self, request, view):
        if request.user.is_authenticated or not getattr(settings, "RATELIMIT_ENABLE", True):
            return True
        rate = parse_rate(getattr(settings, "ANON_API_RATE", ""))
        if rate is None:
            return True
        limit, period = rate
        now = time.time()
        window = int(now // period)
        key = f"{get_client_ip(request)}:{period}:{window}"
        # The key outlives its window by a second so a request on the boundary
        # never finds it gone between these two calls; if it is anyway (culled),
        # the count starts again at one.
        if _counters.add(key, 1, period + 1):
            count = 1
        else:
            try:
                count = _counters.incr(key)
            except ValueError:
                _counters.set(key, 1, period + 1)
                count = 1
        if count > limit:
            self._wait = (window + 1) * period - now
            return False
        return True

    def wait(self):
        """Seconds left in the window, for DRF's ``Retry-After`` header."""
        if self._wait is None:
            return None
        return max(math.ceil(self._wait), 1)
