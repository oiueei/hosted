"""The health endpoint backs the external uptime monitor: 200 means "app AND
database are serving", 503 means degraded — a bare liveness ping would report
"up" straight through a database outage."""

from unittest.mock import patch

import pytest
from django.core.cache import caches
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
