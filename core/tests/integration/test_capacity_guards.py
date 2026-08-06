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
from django.core import mail
from django.test import override_settings

from core.models import Collection, Thing, User
from core.services.email_service import send_collection_capacity_alarm

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
def test_alarm_fires_once_and_never_interrupts_the_upload(
    alarm, authenticated_client, collection, user
):
    """A tripwire, not a warning. Crossing the line must not interrupt the
    upload, and must not re-fire on every subsequent add — an alarm that mails
    the operator per row is an alarm they will filter away.

    This asserts *when* the alarm fires; it cannot say anything about who
    receives it, because the send is mocked out. The recipient rule — the
    operator, never the owner — is pinned further down against `mail.outbox`.
    """
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


# ── The ceiling counts what would LAND, not what was typed ───────────────────
#
# `adding` must be the number of rows that genuinely add to the counter. An
# address that is already a member sits *inside* the count the ceiling is
# measured against, so counting it again refuses a request that adds nobody.


@pytest.mark.django_db
@override_settings(COLLECTION_INVITES_BLOCK=10)
@patch("core.views.collections.send_collection_invite_email")
def test_bulk_reinviting_existing_members_is_not_a_ceiling_refusal(
    mock_send, authenticated_client, collection
):
    """A batch made only of current members adds nobody, so no ceiling can bite."""
    members = _fill_members(collection, 9)
    invites = [{"email": m.email} for m in members[:5]]

    res = authenticated_client.post(
        BULK_INVITE_URL.format(code=collection.code), {"invites": invites}, format="json"
    )

    assert res.status_code == 200
    assert {s["reason"] for s in res.data["skipped"]} == {"already_member"}
    assert collection.invites.count() == 9


@pytest.mark.django_db
@override_settings(COLLECTION_INVITES_BLOCK=10)
@patch("core.views.collections.send_collection_invite_email")
def test_bulk_counts_only_the_newcomers_against_the_ceiling(
    mock_send, authenticated_client, collection
):
    """9 members + 5 rows, 4 of them already members: exactly one seat is needed."""
    members = _fill_members(collection, 9)
    invites = [{"email": m.email} for m in members[:4]] + [{"email": "new@example.com"}]

    res = authenticated_client.post(
        BULK_INVITE_URL.format(code=collection.code), {"invites": invites}, format="json"
    )

    assert res.status_code == 200
    assert res.data["invited"] == 1
    assert mock_send.call_count == 1


@pytest.mark.django_db
@override_settings(COLLECTION_INVITES_BLOCK=10)
@patch("core.views.collections.send_collection_invite_email")
def test_bulk_still_refuses_when_the_newcomers_alone_cross_it(
    mock_send, authenticated_client, collection
):
    """The relaxation must not defeat the guard: 9 members + 2 real newcomers."""
    members = _fill_members(collection, 9)
    invites = [{"email": members[0].email}] + [{"email": f"new{i}@example.com"} for i in range(2)]

    res = authenticated_client.post(
        BULK_INVITE_URL.format(code=collection.code), {"invites": invites}, format="json"
    )

    assert res.status_code == 400
    assert mock_send.call_count == 0


@pytest.mark.django_db
@override_settings(COLLECTION_INVITES_BLOCK=2)
@patch("core.views.collections.send_collection_invite_email")
def test_single_reinvite_of_a_member_answers_already_invited_not_the_ceiling(
    mock_send, authenticated_client, collection
):
    """At the ceiling, re-inviting a member gets the accurate 'already invited'."""
    members = _fill_members(collection, 2)

    res = authenticated_client.post(
        INVITE_URL.format(code=collection.code), {"email": members[0].email}, format="json"
    )

    assert res.status_code == 400
    assert "already invited" in str(res.data).lower()
    assert mock_send.call_count == 0


@pytest.mark.django_db
@override_settings(COLLECTION_INVITES_BLOCK=2)
@patch("core.views.collections.send_collection_invite_email")
def test_single_invite_of_a_newcomer_still_hits_the_ceiling(
    mock_send, authenticated_client, collection
):
    """The single-endpoint relaxation is scoped to members, not to everyone."""
    _fill_members(collection, 2)

    res = authenticated_client.post(
        INVITE_URL.format(code=collection.code), {"email": "newcomer@example.com"}, format="json"
    )

    assert res.status_code == 400
    assert not User.objects.filter(email="newcomer@example.com").exists()
    assert mock_send.call_count == 0


@pytest.mark.django_db
@override_settings(COLLECTION_INVITES_BLOCK=10)
@patch("core.views.collections.send_collection_invite_email")
def test_a_no_op_batch_is_not_refused_by_a_ceiling_already_crossed(
    mock_send, authenticated_client, collection
):
    """A ceiling lowered after the fact must not trap requests that add nobody.

    15 members under a ceiling of 10 (the operator tightened it, or lifted then
    re-applied it). A batch of current members adds no one, so there is nothing
    for the ceiling to refuse — and refusing it would leave the owner unable to
    act on a state they cannot change from the API.
    """
    members = _fill_members(collection, 15)

    res = authenticated_client.post(
        BULK_INVITE_URL.format(code=collection.code),
        {"invites": [{"email": m.email} for m in members[:3]]},
        format="json",
    )

    assert res.status_code == 200
    assert res.data["invited"] == 0
    # A real newcomer is still refused — the counter is over its line.
    refused = authenticated_client.post(
        BULK_INVITE_URL.format(code=collection.code),
        {"invites": [{"email": "newcomer@example.com"}]},
        format="json",
    )
    assert refused.status_code == 400


# ── Fire-once holds under concurrency ────────────────────────────────────────


@pytest.mark.django_db
@override_settings(COLLECTION_THINGS_ALARM=1)
def test_the_alarm_is_claimed_by_exactly_one_racing_request(collection, user):
    """Two requests that both read `things_alarm_sent=False` must send ONE email.

    The two instances stand in for two request threads that loaded the row
    before either had written to it: both see `False` in memory, so the only
    thing separating them is the conditional `UPDATE … WHERE flag=False`. The
    loser's update matches no row and it must return without sending.

    Deliberately **not** mocked at the manager: patching `Collection.objects` to
    report 0 rows affected proves only that the code branches on its own mock.
    Drop the `flag=False` from the WHERE clause and this test goes red, which is
    the whole point of it.
    """
    _fill_things(collection, user, 1)
    first = Collection.objects.get(code=collection.code)
    second = Collection.objects.get(code=collection.code)
    assert (first.things_alarm_sent, second.things_alarm_sent) == (False, False)

    with patch("core.services.email_service.send_collection_capacity_alarm") as mock_alarm:
        first.note_capacity("things")
        second.note_capacity("things")

    assert mock_alarm.call_count == 1


@pytest.mark.django_db
@override_settings(COLLECTION_THINGS_ALARM=1)
def test_the_winner_of_the_race_is_the_one_that_sends(collection, user):
    """The other half: the request that *does* claim the flag must send.

    Without this, a claim that never matched anything would satisfy the test
    above just as well as a correct one.
    """
    _fill_things(collection, user, 1)
    fresh = Collection.objects.get(code=collection.code)

    with patch("core.services.email_service.send_collection_capacity_alarm") as mock_alarm:
        fresh.note_capacity("things")

    mock_alarm.assert_called_once_with(fresh, "things", 1, 1)
    collection.refresh_from_db()
    assert collection.things_alarm_sent is True


# ── What the alarm actually sends ────────────────────────────────────────────
#
# Everything above mocks `send_collection_capacity_alarm` away to assert *when*
# it fires. These assert what it puts in the mailbox — the half no mocked test
# can reach, and the half carrying the guarantee that matters: this mail is the
# operator's, and the owner must never be on it.


@pytest.mark.django_db
def test_the_alarm_goes_to_the_superusers_and_never_to_the_owner(collection, user):
    """A tripwire, not a warning.

    Copying the owner would interrupt a legitimate bulk import and would tell
    somebody probing the endpoint exactly where the line sits. Only the hard
    ceiling is ever user-visible, and only once it bites.
    """
    admin = User.objects.create(email="admin@example.com", is_superuser=True)
    mail.outbox.clear()

    send_collection_capacity_alarm(collection, "things", 42, 40)

    recipients = {addr for m in mail.outbox for addr in m.to}
    assert recipients == {admin.email}
    assert collection.owner.email not in recipients


@pytest.mark.django_db
def test_every_superuser_gets_their_own_copy(collection, user):
    """One send per address: `_send` takes a single recipient, and a per-recipient
    send keeps one bad address from costing the others their alert."""
    first = User.objects.create(email="admin1@example.com", is_superuser=True)
    second = User.objects.create(email="admin2@example.com", is_superuser=True)
    mail.outbox.clear()

    send_collection_capacity_alarm(collection, "invites", 100, 80)

    assert sorted(m.to for m in mail.outbox) == [[first.email], [second.email]]


@pytest.mark.django_db
def test_a_superuser_without_an_email_is_not_mailed_into_the_void(collection, monkeypatch):
    """An abuse signal that silently goes nowhere is worse than no signal, so an
    installation whose superusers have no address still reaches the operator."""
    User.objects.create(email="", is_superuser=True)
    monkeypatch.setenv("CONTACT_EMAIL", "ops@example.com")
    mail.outbox.clear()

    send_collection_capacity_alarm(collection, "things", 42, 40)

    assert [m.to for m in mail.outbox] == [["ops@example.com"]]


@pytest.mark.django_db
def test_with_no_operator_address_configured_it_falls_back_to_the_from_address(
    collection, settings, monkeypatch
):
    monkeypatch.delenv("CONTACT_EMAIL", raising=False)
    settings.DEFAULT_FROM_EMAIL = "noreply@example.com"
    mail.outbox.clear()

    send_collection_capacity_alarm(collection, "things", 42, 40)

    assert [m.to for m in mail.outbox] == [["noreply@example.com"]]


@pytest.mark.django_db
def test_the_alarm_names_everything_needed_to_judge_it(collection, user):
    """The operator has to decide whether this volume is wrong for this account
    without opening the admin, so the mail carries the account, not just a count.
    """
    User.objects.create(email="admin@example.com", is_superuser=True)
    mail.outbox.clear()

    send_collection_capacity_alarm(collection, "things", 42, 40)

    sent = mail.outbox[0]
    assert collection.code in sent.subject
    assert "40" in sent.subject, "the threshold crossed belongs in the subject line"
    assert collection.code in sent.body
    assert "42" in sent.body, "the count that tripped it"
    assert user.email in sent.body, "the owner to look at — named to the operator, not copied"


@pytest.mark.django_db
@override_settings(COLLECTION_THINGS_BLOCK=5)
def test_the_locked_recheck_refuses_the_loser_of_a_race(authenticated_client, collection, user):
    """A batch that passed the unlocked check is still refused under the lock.

    The count before the transaction is read outside it, so two bulk imports
    arriving together can each see room for themselves — the drift the row lock
    exists to close. Here the "other" request commits its rows in the window
    between the two checks; the loser must re-count with them included and
    refuse, all-or-nothing, rather than land its own on top.
    """
    real = Collection.capacity_violation
    calls = []

    def racing(self, counter="things", adding=1):
        calls.append(counter)
        if len(calls) == 1:
            return None  # the unlocked check: room for us
        _fill_things(collection, user, 5)  # the winner commits, filling it
        return real(self, counter, adding)

    with patch.object(Collection, "capacity_violation", racing):
        res = authenticated_client.post(
            BULK_THINGS_URL.format(code=collection.code),
            {"rows": [{"headline": f"Row {i}"} for i in range(3)]},
            format="json",
        )

    assert res.status_code == 400
    assert not Thing.objects.filter(headline__startswith="Row").exists()
