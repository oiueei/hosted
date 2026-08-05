"""
Integration tests for the per-collection mass-upload guards.

Two independent counters — things and invitees — each with a silent operator
alarm and a hard ceiling that only a superuser can lift. The thresholds are
**unpublished** policy (they must be adjustable without notice), so they live in
settings and the standalone default is off; these tests set their own.

The property that matters most, and the one every test here leans on: with no
thresholds configured NOTHING changes. A self-hosted instance must not inherit
www.oiueei.com's abuse posture.
"""

from unittest.mock import patch

import pytest
from django.test import override_settings

from core.models import Collection, Thing, User

THINGS_URL = "/api/v1/things/"
BULK_THINGS_URL = "/api/v1/collections/{code}/things/bulk/"
ADD_THING_URL = "/api/v1/collections/{code}/add-thing/"
INVITE_URL = "/api/v1/collections/{code}/invite/"
BULK_INVITE_URL = "/api/v1/collections/{code}/invite/bulk/"


def _fill_things(collection, owner, n):
    """Put ``n`` things in the collection without going through the API."""
    things = [Thing.objects.create(owner=owner, headline=f"Thing {i}") for i in range(n)]
    collection.things.add(*things)
    return things


def _fill_members(collection, n):
    members = [User.objects.create(email=f"member{i}@example.com") for i in range(n)]
    collection.invites.add(*members)
    return members


# ── The default: no thresholds, no behaviour change ──────────────────────────


@pytest.mark.django_db
def test_without_thresholds_nothing_is_blocked(authenticated_client, collection, user):
    """The standalone default. A self-hoster must not inherit our numbers."""
    _fill_things(collection, user, 5)
    res = authenticated_client.post(
        THINGS_URL,
        {"headline": "One more", "type": "GIFT_THING", "collection_code": collection.code},
        format="json",
    )
    assert res.status_code == 201, res.data


@pytest.mark.django_db
@patch("core.models.collection.Collection._capacity_count")
def test_without_thresholds_the_counters_are_never_even_read(count, collection):
    """Not just "allowed" — the guard must not cost a COUNT query per add on a
    deployment that never opted in."""
    assert collection.capacity_violation("things", adding=1) is None
    collection.note_capacity("things")
    count.assert_not_called()


# ── The things ceiling ───────────────────────────────────────────────────────


@pytest.mark.django_db
@override_settings(COLLECTION_THINGS_BLOCK=3)
def test_single_create_refused_at_the_ceiling(authenticated_client, collection, user):
    _fill_things(collection, user, 3)
    before = Thing.objects.count()

    res = authenticated_client.post(
        THINGS_URL,
        {"headline": "Over the line", "type": "GIFT_THING", "collection_code": collection.code},
        format="json",
    )

    assert res.status_code == 400
    # Refused BEFORE the row is created, or a blocked add leaves an orphan Thing
    # owned by nobody's collection.
    assert Thing.objects.count() == before


@pytest.mark.django_db
@override_settings(COLLECTION_THINGS_BLOCK=10)
def test_bulk_import_cannot_step_over_the_line_in_batches(authenticated_client, collection, user):
    """The whole point of checking the batch: 100 rows at a time would walk
    straight past a ceiling that only ever looked at the next single row."""
    _fill_things(collection, user, 8)
    rows = [{"headline": f"Row {i}", "type": "GIFT_THING"} for i in range(5)]

    res = authenticated_client.post(
        BULK_THINGS_URL.format(code=collection.code), {"rows": rows}, format="json"
    )

    assert res.status_code == 400
    assert "error" in res.data
    # All-or-nothing, like every other failure on this endpoint.
    assert collection.things.count() == 8


@pytest.mark.django_db
@override_settings(COLLECTION_THINGS_BLOCK=10)
def test_a_batch_that_fits_is_still_imported(authenticated_client, collection, user):
    _fill_things(collection, user, 8)
    rows = [{"headline": f"Row {i}", "type": "GIFT_THING"} for i in range(2)]

    res = authenticated_client.post(
        BULK_THINGS_URL.format(code=collection.code), {"rows": rows}, format="json"
    )

    assert res.status_code == 201, res.data
    assert collection.things.count() == 10


@pytest.mark.django_db
@override_settings(COLLECTION_THINGS_BLOCK=2)
def test_add_thing_is_not_a_way_around_the_ceiling(authenticated_client, collection, user):
    """add-thing moves an existing thing rather than creating one, but it lands
    in the same collection — it must not be the unguarded door."""
    _fill_things(collection, user, 2)
    loose = Thing.objects.create(owner=user, headline="Elsewhere")

    res = authenticated_client.post(
        ADD_THING_URL.format(code=collection.code), {"thing_code": loose.code}, format="json"
    )

    assert res.status_code == 400
    assert collection.things.count() == 2


@pytest.mark.django_db
@override_settings(COLLECTION_THINGS_BLOCK=2)
def test_superuser_unblock_lifts_the_ceiling(authenticated_client, collection, user):
    """The documented manual override: a superuser ticks it in the admin after
    reviewing the account, and the collection may pass."""
    _fill_things(collection, user, 2)
    Collection.objects.filter(code=collection.code).update(capacity_unblocked=True)

    res = authenticated_client.post(
        THINGS_URL,
        {"headline": "Allowed now", "type": "GIFT_THING", "collection_code": collection.code},
        format="json",
    )

    assert res.status_code == 201, res.data


# ── The silent alarm ─────────────────────────────────────────────────────────


@pytest.mark.django_db
@override_settings(COLLECTION_THINGS_ALARM=3)
@patch("core.services.email_service.send_collection_capacity_alarm")
def test_alarm_fires_once_and_never_reaches_the_owner(
    alarm, authenticated_client, collection, user
):
    """A tripwire, not a warning. Crossing the line must not interrupt the
    upload, must not tell the owner anything, and must not re-fire on every
    subsequent add — an alarm that mails the operator per row is an alarm they
    will filter away."""
    _fill_things(collection, user, 2)

    for i in range(3):
        res = authenticated_client.post(
            THINGS_URL,
            {"headline": f"Extra {i}", "type": "GIFT_THING", "collection_code": collection.code},
            format="json",
        )
        # Never interrupted: the upload succeeds either side of the line.
        assert res.status_code == 201, res.data

    assert alarm.call_count == 1
    collection.refresh_from_db()
    assert collection.things_alarm_sent is True


@pytest.mark.django_db
@override_settings(COLLECTION_THINGS_ALARM=3)
@patch(
    "core.services.email_service.send_collection_capacity_alarm",
    side_effect=RuntimeError("smtp down"),
)
def test_a_failing_alarm_never_costs_the_upload(alarm, authenticated_client, collection, user):
    """The rows are already committed by the time the alarm runs. The ceiling is
    what stops abuse; the alarm is only the early warning, and it must not be
    able to 500 a good import."""
    _fill_things(collection, user, 2)

    res = authenticated_client.post(
        THINGS_URL,
        {"headline": "Crosses the line", "type": "GIFT_THING", "collection_code": collection.code},
        format="json",
    )

    assert res.status_code == 201, res.data
    assert alarm.called
    # Flag set anyway, so a broken mailer cannot re-arm the alarm every add.
    collection.refresh_from_db()
    assert collection.things_alarm_sent is True


@pytest.mark.django_db
@override_settings(COLLECTION_THINGS_ALARM=5)
@patch("core.services.email_service.send_collection_capacity_alarm")
def test_below_the_line_stays_quiet(alarm, authenticated_client, collection, user):
    _fill_things(collection, user, 2)
    authenticated_client.post(
        THINGS_URL,
        {"headline": "Still low", "type": "GIFT_THING", "collection_code": collection.code},
        format="json",
    )
    assert alarm.call_count == 0


# ── The member counter is independent ────────────────────────────────────────


@pytest.mark.django_db
@override_settings(COLLECTION_THINGS_BLOCK=2, COLLECTION_INVITES_BLOCK=100)
@patch("core.views.collections.send_collection_invite_email")
def test_a_full_things_counter_does_not_block_invitations(
    mock_send, authenticated_client, collection, user
):
    """Two counters, two meanings: dumping stock and harvesting a mailing list
    are different abuses, and one crossing says nothing about the other."""
    _fill_things(collection, user, 5)

    res = authenticated_client.post(
        INVITE_URL.format(code=collection.code), {"email": "guest@example.com"}, format="json"
    )

    assert res.status_code == 200, res.data


@pytest.mark.django_db
@override_settings(COLLECTION_INVITES_BLOCK=2)
@patch("core.views.collections.send_collection_invite_email")
def test_invitations_refused_at_the_member_ceiling(mock_send, authenticated_client, collection):
    _fill_members(collection, 2)

    res = authenticated_client.post(
        INVITE_URL.format(code=collection.code), {"email": "guest@example.com"}, format="json"
    )

    assert res.status_code == 400
    # Refused before any User row or invitation email exists.
    assert not User.objects.filter(email="guest@example.com").exists()
    assert mock_send.call_count == 0


@pytest.mark.django_db
@override_settings(COLLECTION_INVITES_BLOCK=5)
@patch("core.views.collections.send_collection_invite_email")
def test_bulk_invite_checks_the_whole_batch(mock_send, authenticated_client, collection):
    _fill_members(collection, 4)
    invites = [{"email": f"guest{i}@example.com"} for i in range(3)]

    res = authenticated_client.post(
        BULK_INVITE_URL.format(code=collection.code), {"invites": invites}, format="json"
    )

    assert res.status_code == 400
    assert mock_send.call_count == 0
