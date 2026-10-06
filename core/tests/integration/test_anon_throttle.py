"""The per-IP ceiling on API requests made with no session (`ANON_API_RATE`).

A PUBLIC collection answers anyone, so before this its reads had no limit at all.
The rest of the suite runs with ``RATELIMIT_ENABLE = False``; here it is turned on
with a small rate, and the throttle is driven through the whole DRF stack:
authentication, permissions, the throttle, the exception handler.

The count lives in process memory (`core.throttles`), so no cache is overridden
here; `conftest.anonymous_api_counts_start_at_zero` empties it around every test.
"""

import os
import subprocess
import sys
from datetime import UTC, datetime

import pytest
import time_machine
from django.db import connection
from django.test.utils import CaptureQueriesContext

from core import throttles

RATE = "3/m"


@pytest.fixture(autouse=True)
def _limits_on(settings):
    """The limiter on, at a rate small enough to reach."""
    settings.RATELIMIT_ENABLE = True
    settings.ANON_API_RATE = RATE


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

    def test_the_next_window_brings_a_fresh_allowance_and_retry_after_says_when(
        self, api_client, collection_url
    ):
        # Ten seconds into a minute: the refusal says fifty are left, and the next
        # minute answers again.
        with time_machine.travel(datetime(2026, 9, 29, 12, 0, 10, tzinfo=UTC), tick=False):
            responses = [api_client.get(collection_url) for _ in range(4)]
        with time_machine.travel(datetime(2026, 9, 29, 12, 1, 0, tzinfo=UTC), tick=False):
            next_minute = api_client.get(collection_url)

        assert [r.status_code for r in responses] == [200, 200, 200, 429]
        assert responses[-1]["Retry-After"] == "50"
        assert next_minute.status_code == 200

    @pytest.mark.parametrize(
        ("rate", "expected"),
        [
            # The restart is a real count: the visitor gets one more read out of it
            # (the lost one forgot a request) and is then refused as usual.
            ("3/m", [200, 200, 200, 200, 429]),
            # And it restarts at ONE, not at two: with a ceiling of one the request
            # that lost its count is let through, the next one is not.
            ("1/m", [200, 200, 429]),
        ],
    )
    def test_a_count_lost_between_its_two_steps_starts_again_at_one(
        self, api_client, collection_url, settings, monkeypatch, rate, expected
    ):
        # The key was there for `add` and gone for `incr` (culled, or expired on the
        # boundary) — gone here for the second request only, so what the first
        # restart *stored* is what the later requests count on.
        settings.ANON_API_RATE = rate
        real_incr = throttles._counters.incr
        lost = []

        def incr_after_the_key_vanished(key, *args, **kwargs):
            if not lost:
                lost.append(key)
                throttles._counters.delete(key)
            return real_incr(key, *args, **kwargs)  # the cache's own ValueError

        monkeypatch.setattr(throttles._counters, "incr", incr_after_the_key_vanished)

        assert statuses(api_client, collection_url, len(expected)) == expected


@pytest.mark.django_db
class TestTheCountCostsTheDatabaseNothing:
    """The first version counted in the shared DatabaseCache: a read went from 4
    statements to 16, and a refused one still wrote its counter (2026-09-29)."""

    def test_an_allowed_read_asks_exactly_what_it_would_with_the_ceiling_off(
        self, api_client, collection_url, settings
    ):
        api_client.get(collection_url)  # warm whatever a first request warms
        with CaptureQueriesContext(connection) as counted:
            assert api_client.get(collection_url).status_code == 200
        settings.RATELIMIT_ENABLE = False
        with CaptureQueriesContext(connection) as uncounted:
            assert api_client.get(collection_url).status_code == 200

        assert len(counted.captured_queries) == len(uncounted.captured_queries)
        assert not any("oiueei_cache" in q["sql"] for q in counted.captured_queries)

    def test_a_refused_read_costs_the_database_nothing_at_all(self, api_client, collection_url):
        statuses(api_client, collection_url, 3)

        with CaptureQueriesContext(connection) as refused:
            assert api_client.get(collection_url).status_code == 429

        assert refused.captured_queries == []


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


@pytest.mark.django_db
def test_a_deployment_that_never_defines_the_layer_switch_has_the_ceiling_on(
    api_client, collection_url, settings
):
    # Only development.py defines `RATELIMIT_ENABLE` (as False); production never
    # writes it down, so "on" is not a setting there but the default of the read.
    # Every test above sets the switch, and would stay green if that default flipped
    # and silently took the public side's only ceiling off.
    del settings.RATELIMIT_ENABLE

    assert statuses(api_client, collection_url, 4) == [200, 200, 200, 429]


@pytest.mark.parametrize(
    ("rate", "parsed"),
    [
        ("300/m", (300, 60)),
        ("20/s", (20, 1)),
        ("1000/5m", (1000, 300)),
        ("5/h", (5, 3600)),
        ("10000/d", (10000, 86400)),
        (" 300/m ", (300, 60)),
        ("0", None),
        ("", None),
        (None, None),
    ],
)
def test_parse_rate_reads_a_count_and_a_window_in_seconds(rate, parsed):
    assert throttles.parse_rate(rate) == parsed


@pytest.mark.parametrize("rate", ["abc", "300", "300/M", "0/m", "300/0m", "-5/m", "3.5/m"])
def test_parse_rate_refuses_what_is_not_a_rate(rate):
    with pytest.raises(ValueError):
        throttles.parse_rate(rate)


def test_the_shipped_default_is_three_hundred_a_minute():
    # A fresh interpreter, so the answer is what a deployment gets when it sets
    # nothing — not this test run's overrides — and no settings module is reloaded
    # inside the suite. The number is a deliberate choice.
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
