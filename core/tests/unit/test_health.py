"""The health endpoint backs the external uptime monitor: 200 means "app AND
database are serving", 503 means degraded — a bare liveness ping would report
"up" straight through a database outage."""

from unittest.mock import patch

import pytest
from django.core.cache import caches
from django.core.cache.backends.base import BaseCache
from django.db import OperationalError
from django.test import override_settings

HEALTH_URL = "/api/v1/health/"

_LIMITED = override_settings(
    RATELIMIT_ENABLE=True,
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "health-ratelimit-test",
        }
    },
)


class RefusedCache(BaseCache):
    """A cache whose every operation raises the way ``DatabaseCache`` does when
    Postgres is refusing connections.

    This is not a contrivance: ``CACHES['default']`` in this project IS the
    database (``django.core.cache.backends.db.DatabaseCache``,
    config/settings/base.py), and the rate limiter keeps its counter there. So
    the one outage ``/health/`` exists to report is the same outage that breaks
    the limiter, and a test that leaves the cache working is testing a state
    production never reaches.
    """

    def _refused(self, *args, **kwargs):
        raise OperationalError(
            'connection to server at "cluster.eu-west-1.rds.amazonaws.com", '
            "port 5432 failed: Connection refused"
        )

    add = _refused
    get = _refused
    set = _refused
    touch = _refused
    delete = _refused
    clear = _refused
    incr = _refused
    decr = _refused
    get_many = _refused
    set_many = _refused


# Everything Postgres-backed is down at once — the connection the view checks
# AND the cache the limiter counts in. The limiter is left ENABLED on purpose:
# switching it off here would be the test quietly stepping around the bug.
_WHOLE_DATABASE_DOWN = override_settings(
    RATELIMIT_ENABLE=True,
    CACHES={"default": {"BACKEND": f"{__name__}.RefusedCache", "LOCATION": "refused"}},
)


@pytest.mark.django_db
class TestHealthCheck:
    def test_healthy_when_the_database_answers(self, api_client):
        response = api_client.get(HEALTH_URL)
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_degraded_when_the_database_is_down(self, api_client):
        with patch("core.urls.connection") as mock_connection:
            mock_connection.cursor.side_effect = Exception("db down")
            response = api_client.get(HEALTH_URL)
        assert response.status_code == 503
        # No error detail — the endpoint is public.
        assert response.json() == {"status": "degraded"}

    @_WHOLE_DATABASE_DOWN
    def test_degraded_when_the_outage_takes_the_limiter_with_it(self, api_client):
        """The real shape of a database outage, which the test above does not have.

        `test_degraded_when_the_database_is_down` fakes only the view's own
        cursor, leaving the limiter's cache — the same Postgres — answering
        happily. Production on 2026-09-16 had neither: the @ratelimit decorator
        ran first, its DatabaseCache raised, and the monitor got an unhandled
        500 with a Sentry traceback instead of this 503. Restore the decorator
        and this test errors out on that exception rather than asserting.
        """
        with patch("core.urls.connection") as mock_connection:
            mock_connection.cursor.side_effect = OperationalError("Connection refused")
            response = api_client.get(HEALTH_URL)
        assert response.status_code == 503
        assert response.json() == {"status": "degraded"}

    @_WHOLE_DATABASE_DOWN
    def test_head_degraded_when_the_outage_takes_the_limiter_with_it(self, api_client):
        """HEAD is the verb that actually caught the outage — UptimeRobot probes
        with it, and it is what the 2026-09-16 Sentry event recorded."""
        with patch("core.urls.connection") as mock_connection:
            mock_connection.cursor.side_effect = OperationalError("Connection refused")
            response = api_client.head(HEALTH_URL)
        assert response.status_code == 503

    @_WHOLE_DATABASE_DOWN
    def test_a_dead_limiter_never_reports_a_healthy_app_as_throttled(self, api_client):
        """Swallowing the limiter's failure must not turn into swallowing the
        answer: with the cache dead but the database itself fine, the endpoint
        still has to do its real check and say so — not 429, not 503."""
        response = api_client.get(HEALTH_URL)
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_head_works_for_monitors(self, api_client):
        # Uptime monitors often probe with HEAD to save bandwidth.
        assert api_client.head(HEALTH_URL).status_code == 200

    def test_head_degraded_when_the_database_is_down(self, api_client):
        # A HEAD-probing monitor must also see the outage — 200 here would
        # report "up" straight through a database failure.
        with patch("core.urls.connection") as mock_connection:
            mock_connection.cursor.side_effect = Exception("db down")
            assert api_client.head(HEALTH_URL).status_code == 503

    @_LIMITED
    def test_a_flood_is_capped(self, api_client):
        """This is the one anonymous endpoint that touches the database on every
        hit, so uncapped it is cheap DB amplification rather than a monitor."""
        caches["default"].clear()
        statuses = [api_client.get(HEALTH_URL).status_code for _ in range(61)]
        assert statuses[0] == 200
        assert statuses[-1] == 429

    @_LIMITED
    def test_the_cap_counts_head_probes_too(self, api_client):
        """Monitors probe with HEAD, so a limiter scoped to GET alone would leave
        the flood one verb away from being unlimited."""
        caches["default"].clear()
        statuses = [api_client.head(HEALTH_URL).status_code for _ in range(61)]
        assert statuses[0] == 200
        assert statuses[-1] == 429

    @_LIMITED
    def test_a_real_monitor_is_nowhere_near_the_cap(self, api_client):
        """60/m against a 5-minute cadence (0.2/m): the cap must never be the
        reason an uptime monitor reports an outage."""
        caches["default"].clear()
        assert {api_client.get(HEALTH_URL).status_code for _ in range(30)} == {200}
