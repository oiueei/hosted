"""
Integration tests for the shared daily invitation-email quota.

The per-view rate limits count *requests*, so one bulk request could still fan
out 100 emails — the quota counts the emails themselves, shared between the
single and bulk invite endpoints (see INVITE_EMAILS_PER_DAY in
core/views/collections.py). It follows RATELIMIT_ENABLE — off in the test
settings — so these tests switch it on with a local-memory cache, like
test_ratelimit.py does.
"""

from unittest.mock import patch

from django.core.cache import caches
from django.test import override_settings

from core.models import RSVP, User
from core.services.invitation_service import _consume_invite_quota, _invite_quota_key

SINGLE_URL = "/api/v1/collections/{code}/invite/"
BULK_URL = "/api/v1/collections/{code}/invite/bulk/"

# The quota is pure cache bookkeeping keyed by user code — no row needed.
QUOTA_USER = "QUOTA1"

QUOTA_SETTINGS = {
    "RATELIMIT_ENABLE": True,
    "CACHES": {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "invite-quota-test",
        }
    },
}


def _emails_sent(*mocks):
    """Invitation emails across both delivery paths.

    The single invite runs through `invitation_service.deliver_invitation` (the
    path an approved member proposal also takes); the bulk endpoint keeps its own
    batched fan-out. The daily quota counts emails, not endpoints, so a test that
    watched only one path would pass while the other quietly went uncapped.
    """
    return sum(m.call_count for m in mocks)


def _invite_rsvp_count(collection):
    return RSVP.objects.filter(
        target_code=collection.code, action=RSVP.Action.COLLECTION_INVITE
    ).count()


@override_settings(**QUOTA_SETTINGS, INVITE_EMAILS_PER_DAY=2)
@patch("core.views.collections.send_collection_invite_email")  # bulk fan-out
@patch("core.services.invitation_service.send_collection_invite_email")  # single invite
def test_single_invite_blocks_after_daily_cap(
    mock_single, mock_bulk, authenticated_client, collection
):
    caches["default"].clear()
    for email in ("a@example.com", "b@example.com"):
        res = authenticated_client.post(
            SINGLE_URL.format(code=collection.code), {"email": email}, format="json"
        )
        assert res.status_code == 200

    res = authenticated_client.post(
        SINGLE_URL.format(code=collection.code), {"email": "c@example.com"}, format="json"
    )
    assert res.status_code == 429
    assert "error" in res.data
    assert _emails_sent(mock_single, mock_bulk) == 2
    # The blocked request created neither RSVPs nor a User row.
    assert _invite_rsvp_count(collection) == 2
    assert not User.objects.filter(email="c@example.com").exists()


@override_settings(**QUOTA_SETTINGS, INVITE_EMAILS_PER_DAY=3)
@patch("core.views.collections.send_collection_invite_email")  # bulk fan-out
@patch("core.services.invitation_service.send_collection_invite_email")  # single invite
def test_bulk_invite_caps_batch_and_reports_daily_limit(
    mock_single, mock_bulk, authenticated_client, collection
):
    caches["default"].clear()
    invites = [{"email": f"u{i}@example.com"} for i in range(5)]
    res = authenticated_client.post(
        BULK_URL.format(code=collection.code), {"invites": invites}, format="json"
    )
    assert res.status_code == 200
    assert res.data["invited"] == 3
    assert [s["reason"] for s in res.data["skipped"]] == ["daily_limit", "daily_limit"]
    assert {s["email"] for s in res.data["skipped"]} == {"u3@example.com", "u4@example.com"}
    assert _emails_sent(mock_single, mock_bulk) == 3
    assert _invite_rsvp_count(collection) == 3
    # Quota-skipped rows never reached get_or_create.
    assert not User.objects.filter(email="u3@example.com").exists()


@override_settings(**QUOTA_SETTINGS, INVITE_EMAILS_PER_DAY=2)
@patch("core.views.collections.send_collection_invite_email")  # bulk fan-out
@patch("core.services.invitation_service.send_collection_invite_email")  # single invite
def test_quota_is_shared_between_single_and_bulk(
    mock_single, mock_bulk, authenticated_client, collection
):
    caches["default"].clear()
    res = authenticated_client.post(
        SINGLE_URL.format(code=collection.code), {"email": "one@example.com"}, format="json"
    )
    assert res.status_code == 200

    invites = [{"email": "two@example.com"}, {"email": "three@example.com"}]
    res = authenticated_client.post(
        BULK_URL.format(code=collection.code), {"invites": invites}, format="json"
    )
    assert res.status_code == 200
    assert res.data["invited"] == 1
    assert res.data["skipped"] == [{"email": "three@example.com", "reason": "daily_limit"}]
    assert _emails_sent(mock_single, mock_bulk) == 2


@override_settings(**QUOTA_SETTINGS, INVITE_EMAILS_PER_DAY=1)
@patch("core.views.collections.send_collection_invite_email")  # bulk fan-out
@patch("core.services.invitation_service.send_collection_invite_email")  # single invite
def test_bulk_invite_blocks_outright_when_quota_exhausted(
    mock_single, mock_bulk, authenticated_client, collection
):
    caches["default"].clear()
    res = authenticated_client.post(
        SINGLE_URL.format(code=collection.code), {"email": "first@example.com"}, format="json"
    )
    assert res.status_code == 200

    res = authenticated_client.post(
        BULK_URL.format(code=collection.code),
        {"invites": [{"email": "x@example.com"}]},
        format="json",
    )
    assert res.status_code == 429
    assert "error" in res.data
    assert _emails_sent(mock_single, mock_bulk) == 1


@override_settings(INVITE_EMAILS_PER_DAY=1)
@patch("core.views.collections.send_collection_invite_email")  # bulk fan-out
@patch("core.services.invitation_service.send_collection_invite_email")  # single invite
def test_quota_follows_the_ratelimit_switch(
    mock_single, mock_bulk, authenticated_client, collection
):
    """RATELIMIT_ENABLE=False (the dev/test default) disables the quota too —
    same switch the django-ratelimit decorators read, so local development
    never trips an abuse guard."""
    for email in ("a@example.com", "b@example.com"):
        res = authenticated_client.post(
            SINGLE_URL.format(code=collection.code), {"email": email}, format="json"
        )
        assert res.status_code == 200
    assert _emails_sent(mock_single, mock_bulk) == 2


@override_settings(**QUOTA_SETTINGS)
@patch("core.views.collections.send_collection_invite_email")  # bulk fan-out
@patch("core.services.invitation_service.send_collection_invite_email")  # single invite
def test_no_cap_configured_means_unlimited(
    mock_single, mock_bulk, authenticated_client, collection
):
    """The standalone default: rate limiting ON, no INVITE_EMAILS_PER_DAY set.

    The cap is operator policy — it protects a particular deployment's sending
    reputation — so a self-hosted instance must not inherit a number chosen for
    www.oiueei.com. This is the case that regresses silently: reinstate a
    module-level default and every self-hoster starts getting 429s they never
    configured, on a limit they cannot find in their settings.
    """
    caches["default"].clear()
    for i in range(4):
        res = authenticated_client.post(
            SINGLE_URL.format(code=collection.code),
            {"email": f"guest{i}@example.com"},
            format="json",
        )
        assert res.status_code == 200, res.data
    assert _emails_sent(mock_single, mock_bulk) == 4
    assert _invite_rsvp_count(collection) == 4


@override_settings(**QUOTA_SETTINGS, INVITE_EMAILS_PER_DAY=0)
@patch("core.views.collections.send_collection_invite_email")  # bulk fan-out
@patch("core.services.invitation_service.send_collection_invite_email")  # single invite
def test_zero_is_the_explicit_way_to_turn_the_quota_off(
    mock_single, mock_bulk, authenticated_client, collection
):
    """0 means unlimited, not "no invitations allowed".

    An operator turning the cap off writes INVITE_EMAILS_PER_DAY=0 rather than
    deleting the config var. Reading it as a literal ceiling would lock every
    owner out of inviting anyone at all.
    """
    caches["default"].clear()
    for i in range(3):
        res = authenticated_client.post(
            SINGLE_URL.format(code=collection.code),
            {"email": f"guest{i}@example.com"},
            format="json",
        )
        assert res.status_code == 200, res.data
    assert _emails_sent(mock_single, mock_bulk) == 3


@override_settings(**QUOTA_SETTINGS, INVITE_EMAILS_PER_DAY=2)
@patch("core.views.collections.send_collection_invite_email")  # bulk fan-out
@patch("core.services.invitation_service.send_collection_invite_email")  # single invite
def test_bulk_respects_a_configured_cap(mock_single, mock_bulk, authenticated_client, collection):
    """The cap counts emails, so the bulk fan-out cannot multiply past it."""
    caches["default"].clear()
    res = authenticated_client.post(
        BULK_URL.format(code=collection.code),
        {"invites": [{"email": f"guest{i}@example.com"} for i in range(4)]},
        format="json",
    )
    assert res.status_code == 200, res.data
    assert res.data["invited"] == 2
    assert _emails_sent(mock_single, mock_bulk) == 2
    assert [s["reason"] for s in res.data["skipped"]] == ["daily_limit", "daily_limit"]


@override_settings(**QUOTA_SETTINGS)
def test_an_unset_cap_records_no_bookkeeping_at_all():
    """Off means off, down to the cache.

    `_consume_invite_quota` returns before writing when there is nothing to
    record — no cap configured, or nothing sent. Both guards survived mutation
    (`or` → `and`, `<= 0` → `< 0`) because a stray key changes no answer today:
    `_invite_quota_left` reads None while the cap is off. It would start
    mattering the moment an operator sets a cap on a running deployment, which
    is exactly when the counter must begin at zero rather than at whatever a
    disabled feature had been quietly accumulating per user per day.
    """
    caches["default"].clear()

    _consume_invite_quota(QUOTA_USER, 5)  # no INVITE_EMAILS_PER_DAY set
    assert caches["default"].get(_invite_quota_key(QUOTA_USER)) is None

    # And with a cap on, recording nothing writes nothing.
    with override_settings(INVITE_EMAILS_PER_DAY=10):
        _consume_invite_quota(QUOTA_USER, 0)
        assert caches["default"].get(_invite_quota_key(QUOTA_USER)) is None

        # The other half: a real send does land, so this isn't a dead assertion.
        _consume_invite_quota(QUOTA_USER, 2)
        assert caches["default"].get(_invite_quota_key(QUOTA_USER)) == 2
