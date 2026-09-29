"""The shared cache keeps a day's quotas through a burst of other keys.

`CACHES['default']` is one DatabaseCache table holding two kinds of thing: the
operator's daily allowances (`INVITE_EMAILS_PER_DAY` as `invq:…`,
`COLLECTION_JOINS_PER_DAY` as `joinq:…`, about a day each) and the per-IP limiter
windows (`rl:…`, a minute or so each). Past `MAX_ENTRIES` Django culls on every
write — expired rows, then a third of the live ones, **lowest key first** — and
`invq`/`joinq` sort before `rl`. With Django's default of 300, a few hundred
client IPs touching any IP-limited endpoint inside a minute erased both
allowances: measured on 2026-09-29 with 420 IPs, one request each.

These tests run on the cache **as configured** (no `CACHES` override): what they
guard is the setting in `config/settings/base.py`.
"""

import pytest

from core.services.invitation_service import _consume_invite_quota, _invite_quota_left
from core.services.join_quota import consume_join_quota, join_quota_exhausted

# More live keys than Django's default MAX_ENTRIES (300), one per client address.
BURST = 420


@pytest.fixture
def quotas_on(settings):
    settings.RATELIMIT_ENABLE = True
    settings.TRUSTED_PROXY_COUNT = 1
    settings.INVITE_EMAILS_PER_DAY = 150
    settings.COLLECTION_JOINS_PER_DAY = 2


def burst_of_limiter_windows(client):
    """One request from each of `BURST` addresses to an IP-limited endpoint: a
    limiter window per address, all alive at once."""
    for n in range(BURST):
        response = client.get("/api/v1/health/", HTTP_X_FORWARDED_FOR=f"10.{n // 250}.{n % 250}.1")
        # The health check itself answered (its limiter ran), not the SPA catch-all.
        assert response.json()["status"] == "ok"


@pytest.mark.django_db
def test_a_burst_of_client_addresses_leaves_a_day_of_invitations_spent(quotas_on, api_client, user):
    _consume_invite_quota(user.code, 149)
    assert _invite_quota_left(user.code) == 1

    burst_of_limiter_windows(api_client)

    # Culled, the counter reads as never spent: 150 fresh invitations today.
    assert _invite_quota_left(user.code) == 1


@pytest.mark.django_db
def test_a_burst_of_client_addresses_leaves_a_full_collection_full(
    quotas_on, api_client, public_collection
):
    consume_join_quota(public_collection.code)
    consume_join_quota(public_collection.code)
    assert join_quota_exhausted(public_collection.code)

    burst_of_limiter_windows(api_client)

    assert join_quota_exhausted(public_collection.code)
