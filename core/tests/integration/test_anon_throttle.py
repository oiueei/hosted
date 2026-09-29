"""The per-IP ceiling on API requests made with no session (`ANON_API_RATE`).

A PUBLIC collection answers anyone, so before this its reads had no limit at all.
The rest of the suite runs with ``RATELIMIT_ENABLE = False``; here it is turned on
with a real local-memory cache (the pattern of ``test_ratelimit.py``) and a small
rate, and the throttle is driven through the whole DRF stack: authentication,
permissions, the throttle, the exception handler.
"""

import os
import subprocess
import sys

import pytest
from django.core.cache import caches

RATE = "3/m"

LOCMEM = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "anon-throttle-test",
    }
}


@pytest.fixture(autouse=True)
def _limits_on(settings):
    """The limiter on, counting in a real cache, at a rate small enough to reach."""
    settings.RATELIMIT_ENABLE = True
    settings.CACHES = LOCMEM
    settings.ANON_API_RATE = RATE
    caches["default"].clear()
    yield
    caches["default"].clear()


@pytest.fixture
def collection_url(public_collection):
    return f"/api/v1/collections/{public_collection.code}/"


def statuses(client, url, times, **extra):
    return [client.get(url, **extra).status_code for _ in range(times)]


@pytest.mark.django_db
class TestAnonymousCeiling:
    def test_the_read_after_the_ceiling_is_a_429_that_says_when_to_come_back(
        self, api_client, collection_url
    ):
        responses = [api_client.get(collection_url) for _ in range(4)]

        assert [r.status_code for r in responses] == [200, 200, 200, 429]
        blocked = responses[-1]
        assert "detail" in blocked.data
        # DRF turns the throttle's wait() into the header a well-behaved client
        # backs off by: a whole number of seconds, inside the minute window.
        assert 1 <= int(blocked["Retry-After"]) <= 60

    def test_a_counter_that_could_not_be_read_refuses_and_still_gives_a_real_wait(
        self, api_client, collection_url, monkeypatch
    ):
        # django-ratelimit's own answer when the cache fails between `add` and `incr`:
        # refuse, with `time_left = -1`. A `Retry-After: -1` is not a time, so the
        # header says one second — the library's fail-closed default is the app's
        # (`RATELIMIT_FAIL_OPEN` is unset), and this pins that it stays well formed.
        broken = {"count": 0, "limit": 0, "should_limit": True, "time_left": -1}
        monkeypatch.setattr("core.throttles.get_usage", lambda *args, **kwargs: broken)

        response = api_client.get(collection_url)

        assert response.status_code == 429
        assert response["Retry-After"] == "1"

    def test_a_signed_in_member_is_never_counted(self, authenticated_client, collection_url):
        assert set(statuses(authenticated_client, collection_url, 10)) == {200}

    def test_a_member_does_not_spend_the_quota_of_visitors_on_the_same_address(
        self, api_client, authenticated_client, collection_url
    ):
        # Same IP (the test client's REMOTE_ADDR): ten reads with a session leave the
        # anonymous allowance untouched.
        statuses(authenticated_client, collection_url, 10)

        assert statuses(api_client, collection_url, 3) == [200, 200, 200]

    def test_two_addresses_have_separate_allowances(self, api_client, collection_url, settings):
        settings.TRUSTED_PROXY_COUNT = 1
        first = {"HTTP_X_FORWARDED_FOR": "203.0.113.1"}
        second = {"HTTP_X_FORWARDED_FOR": "203.0.113.2"}

        assert statuses(api_client, collection_url, 4, **first) == [200, 200, 200, 429]
        # The other visitor is untouched by the first one having run out.
        assert statuses(api_client, collection_url, 3, **second) == [200, 200, 200]
        assert statuses(api_client, collection_url, 1, **first) == [429]

    def test_a_forged_left_hand_address_does_not_mint_a_fresh_allowance(
        self, api_client, collection_url, settings
    ):
        settings.TRUSTED_PROXY_COUNT = 1
        # Only the entry the trusted proxy appended (the rightmost) counts; text the
        # client prepended is its own.
        codes = [
            api_client.get(
                collection_url, HTTP_X_FORWARDED_FOR=f"198.51.100.{n}, 203.0.113.9"
            ).status_code
            for n in range(1, 5)
        ]

        assert codes == [200, 200, 200, 429]


@pytest.mark.django_db
@pytest.mark.parametrize("off", ["0", ""])
def test_a_zero_or_empty_rate_switches_the_ceiling_off(api_client, collection_url, settings, off):
    settings.ANON_API_RATE = off

    assert set(statuses(api_client, collection_url, 10)) == {200}


@pytest.mark.django_db
def test_the_layer_wide_switch_turns_the_ceiling_off_with_the_rest(
    api_client, collection_url, settings
):
    # `RATELIMIT_ENABLE` is what development and the suite flip to stop every limit;
    # a ceiling that ignored it would be the one that still fired.
    settings.RATELIMIT_ENABLE = False

    assert set(statuses(api_client, collection_url, 10)) == {200}


def test_the_shipped_default_is_three_hundred_a_minute():
    # A fresh interpreter, so the answer is what a deployment gets when it sets
    # nothing — not this test run's overrides — and no settings module is reloaded
    # inside the suite. The number is CA's (2026-09-29).
    env = {k: v for k, v in os.environ.items() if k != "ANON_API_RATE"}
    code = (
        "from config.settings import base;"
        "print(base.ANON_API_RATE);"
        "print(base.REST_FRAMEWORK['DEFAULT_THROTTLE_CLASSES'])"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], env=env, capture_output=True, text=True, check=True
    ).stdout.splitlines()

    assert out == ["300/m", "['core.throttles.AnonymousApiThrottle']"]
