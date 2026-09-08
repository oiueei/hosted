"""Integration tests for RESERVE_THING — on-site reservations.

The distinctive shape: **auto-confirmed** (no owner accept step), no
ThingTransfer, no deposit, optional fee, a member-only requester, and a
reservations-only PROPRIETARY collection. Either party may cancel a
not-yet-started one.
"""

from datetime import date, timedelta

import pytest
from django.core import mail
from rest_framework import status

from core.models import RSVP, BookingPeriod, Collection, Thing, User
from core.models.notification import InAppNotification
from core.models.transfer import ThingTransfer

pytestmark = pytest.mark.django_db

REQUEST_URL = "/api/v1/things/{}/request/"
CANCEL_URL = "/api/v1/bookings/{}/cancel/"


def _next_weekday(weekday, base=None):
    d = (base or date.today()) + timedelta(days=1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d


@pytest.fixture
def reservations(db, user, user2, api_client):
    """An operator (user) with a reservations collection + one space, and a
    member (user2) who can book it. Weekdays Mon–Fri, up to 3 days."""
    coll = Collection.objects.create(
        code="RSVC01",
        owner=user,
        headline="Ateneu spaces",
        status="ACTIVE",
        mode=Collection.Mode.PROPRIETARY,
        allowed_thing_types=["RESERVE_THING"],
        reservation_max_days=3,
        rental_weekdays=[0, 1, 2, 3, 4],
    )
    coll.invites.add(user2)
    thing = Thing.objects.create(
        code="RSVT01",
        type=Thing.Type.RESERVE_THING,
        owner=user,
        headline="Sala polivalent",
        location="Planta 1, sala 2",
        fee="5.00",
    )
    coll.things.add(thing)
    return {"collection": coll, "thing": thing, "owner": user, "member": user2}


def _member_client(api_client, member):
    from rest_framework_simplejwt.tokens import RefreshToken

    api_client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(member).access_token}"
    )
    return api_client


# --- the auto-confirm flow --------------------------------------------------


def test_a_reservation_is_confirmed_on_the_spot(reservations, authenticated_client2):
    thing = reservations["thing"]
    mon = _next_weekday(0)
    mail.outbox.clear()

    resp = authenticated_client2.post(
        REQUEST_URL.format(thing.code),
        {
            "start_date": str(mon),
            "duration_days": 2,
            "collection_code": reservations["collection"].code,
        },
        format="json",
    )

    assert resp.status_code == status.HTTP_201_CREATED
    assert resp.data["message"] == "Reservation confirmed"
    booking = BookingPeriod.objects.get(code=resp.data["booking_code"])
    assert booking.status == BookingPeriod.Status.ACCEPTED
    assert booking.start_date == mon
    assert booking.end_date == mon + timedelta(days=2)
    # both parties emailed, nothing to accept
    assert len(mail.outbox) == 2
    # no accept/reject RSVP pair
    assert not RSVP.objects.filter(
        target_code=booking.code,
        action__in=[RSVP.Action.BOOKING_ACCEPT, RSVP.Action.BOOKING_REJECT],
    ).exists()
    # nothing changed hands
    assert not ThingTransfer.objects.filter(thing=thing).exists()
    # the owner gets a notice, not a question
    note = InAppNotification.objects.get(user=reservations["owner"], type="RESERVATION_MADE")
    assert note.payload["booking_code"] == booking.code


def test_the_project_note_reaches_the_owner(reservations, authenticated_client2):
    thing = reservations["thing"]
    mail.outbox.clear()
    resp = authenticated_client2.post(
        REQUEST_URL.format(thing.code),
        {
            "start_date": str(_next_weekday(0)),
            "duration_days": 1,
            "project_note": "Un taller de serigrafia per a sis persones.",
            "collection_code": reservations["collection"].code,
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_201_CREATED
    assert BookingPeriod.objects.get(code=resp.data["booking_code"]).project_note.startswith(
        "Un taller"
    )
    owner_mail = next(m for m in mail.outbox if reservations["owner"].email in m.to)
    assert "taller de serigrafia" in owner_mail.body


def test_no_note_means_no_note(reservations, authenticated_client2):
    resp = authenticated_client2.post(
        REQUEST_URL.format(reservations["thing"].code),
        {"start_date": str(_next_weekday(0)), "duration_days": 1},
        format="json",
    )
    assert resp.status_code == status.HTTP_201_CREATED
    assert BookingPeriod.objects.get(code=resp.data["booking_code"]).project_note == ""


# --- who may reserve ------------------------------------------------------


def test_a_non_member_cannot_reserve(reservations, api_client):
    stranger = User.objects.create(code="STRNGR", email="stranger@test.com")
    client = _member_client(api_client, stranger)
    resp = client.post(
        REQUEST_URL.format(reservations["thing"].code),
        {"start_date": str(_next_weekday(0)), "duration_days": 1},
        format="json",
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert not BookingPeriod.objects.exists()


# --- the reservation rules -------------------------------------------------


def test_over_the_max_days_is_refused(reservations, authenticated_client2):
    resp = authenticated_client2.post(
        REQUEST_URL.format(reservations["thing"].code),
        {"start_date": str(_next_weekday(0)), "duration_days": 4},
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


def test_a_span_over_a_closed_day_is_refused(reservations, authenticated_client2):
    """Fri + 3 days would occupy Fri/Sat/Sun — the space is Mon–Fri only."""
    resp = authenticated_client2.post(
        REQUEST_URL.format(reservations["thing"].code),
        {"start_date": str(_next_weekday(4)), "duration_days": 3},
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert not BookingPeriod.objects.exists()


def test_a_clash_is_a_409_and_blocks_only_its_days(reservations, authenticated_client2, api_client):
    thing = reservations["thing"]
    mon = _next_weekday(0)
    first = authenticated_client2.post(
        REQUEST_URL.format(thing.code),
        {"start_date": str(mon), "duration_days": 2},
        format="json",
    )
    assert first.status_code == status.HTTP_201_CREATED

    # a second member, same days → clash
    other = User.objects.create(code="MEMB03", email="m3@test.com")
    reservations["collection"].invites.add(other)
    clash = _member_client(api_client, other).post(
        REQUEST_URL.format(thing.code),
        {"start_date": str(mon), "duration_days": 1},
        format="json",
    )
    assert clash.status_code == status.HTTP_409_CONFLICT

    # the day the first booking frees (its end day) is bookable
    free = _member_client(api_client, other).post(
        REQUEST_URL.format(thing.code),
        {"start_date": str(mon + timedelta(days=2)), "duration_days": 1},
        format="json",
    )
    assert free.status_code == status.HTTP_201_CREATED


# --- money ---------------------------------------------------------------


def test_a_reservation_thing_may_carry_a_fee(authenticated_client):
    coll = Collection.objects.create(
        code="RSVC02",
        owner=User.objects.get(code="TEST01"),
        headline="X",
        allowed_thing_types=["RESERVE_THING"],
        reservation_max_days=1,
    )
    resp = authenticated_client.post(
        "/api/v1/things/",
        {
            "type": "RESERVE_THING",
            "headline": "Paid room",
            "fee": "12.00",
            "collection_code": coll.code,
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_201_CREATED
    assert resp.data["fee"] == "12.00"


def test_a_reservation_thing_may_not_carry_a_deposit(authenticated_client):
    coll = Collection.objects.create(
        code="RSVC03",
        owner=User.objects.get(code="TEST01"),
        headline="X",
        allowed_thing_types=["RESERVE_THING"],
        reservation_max_days=1,
    )
    resp = authenticated_client.post(
        "/api/v1/things/",
        {
            "type": "RESERVE_THING",
            "headline": "Room",
            "deposit": "50.00",
            "collection_code": coll.code,
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "deposit" in resp.data


# --- collection shape rules ---------------------------------------------


def test_a_reservation_thing_needs_a_reservations_collection(authenticated_client):
    plain = Collection.objects.create(
        code="PLAIN1", owner=User.objects.get(code="TEST01"), headline="Plain"
    )
    resp = authenticated_client.post(
        "/api/v1/things/",
        {"type": "RESERVE_THING", "headline": "Room", "collection_code": plain.code},
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "type" in resp.data


def test_a_standalone_reservation_thing_is_refused(authenticated_client):
    resp = authenticated_client.post(
        "/api/v1/things/",
        {"type": "RESERVE_THING", "headline": "Nowhere room"},
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert not Thing.objects.filter(headline="Nowhere room").exists()


def test_a_reservations_collection_holds_only_reservations(authenticated_client):
    coll = Collection.objects.create(
        code="RSVC04",
        owner=User.objects.get(code="TEST01"),
        headline="X",
        allowed_thing_types=["RESERVE_THING"],
        reservation_max_days=1,
    )
    resp = authenticated_client.post(
        "/api/v1/things/",
        {"type": "GIFT_THING", "headline": "A gift", "collection_code": coll.code},
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.parametrize(
    "payload",
    [
        {"headline": "Mixed", "allowed_thing_types": ["RESERVE_THING", "GIFT_THING"]},
        {
            "headline": "Community reservations",
            "mode": "COMMUNITY",
            "allowed_thing_types": ["RESERVE_THING"],
        },
    ],
)
def test_reserve_allowlist_rules_at_collection_creation(authenticated_client, payload):
    resp = authenticated_client.post("/api/v1/collections/", payload, format="json")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


def test_a_reservations_collection_cannot_become_community(authenticated_client):
    coll = Collection.objects.create(
        code="RSVC05",
        owner=User.objects.get(code="TEST01"),
        headline="X",
        allowed_thing_types=["RESERVE_THING"],
        reservation_max_days=1,
    )
    resp = authenticated_client.patch(
        f"/api/v1/collections/{coll.code}/", {"mode": "COMMUNITY"}, format="json"
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


# --- cancellation (both sides) -----------------------------------------


def _make_booking(reservations, authenticated_client2, days_ahead_weekday=0):
    resp = authenticated_client2.post(
        REQUEST_URL.format(reservations["thing"].code),
        {"start_date": str(_next_weekday(days_ahead_weekday)), "duration_days": 1},
        format="json",
    )
    assert resp.status_code == status.HTTP_201_CREATED
    return BookingPeriod.objects.get(code=resp.data["booking_code"])


def test_the_member_can_cancel_and_it_frees_the_slot(
    reservations, authenticated_client2, api_client
):
    booking = _make_booking(reservations, authenticated_client2)
    mail.outbox.clear()

    resp = authenticated_client2.post(CANCEL_URL.format(booking.code))
    assert resp.status_code == status.HTTP_200_OK
    booking.refresh_from_db()
    assert booking.status == BookingPeriod.Status.CANCELLED
    # the owner is told
    assert InAppNotification.objects.filter(
        user=reservations["owner"], type="RESERVATION_CANCELLED"
    ).exists()
    assert any(reservations["owner"].email in m.to for m in mail.outbox)

    # the freed day is bookable again
    again = authenticated_client2.post(
        REQUEST_URL.format(reservations["thing"].code),
        {"start_date": str(booking.start_date), "duration_days": 1},
        format="json",
    )
    assert again.status_code == status.HTTP_201_CREATED


def test_the_owner_can_cancel_a_members_reservation(
    reservations, authenticated_client2, api_client
):
    booking = _make_booking(reservations, authenticated_client2)
    mail.outbox.clear()

    # switch the shared client to the owner and hit the same endpoint (rule 4:
    # the owner may cancel a member's reservation — e.g. they need the space)
    owner_client = _member_client(api_client, reservations["owner"])
    resp = owner_client.post(CANCEL_URL.format(booking.code))
    assert resp.status_code == status.HTTP_200_OK
    booking.refresh_from_db()
    assert booking.status == BookingPeriod.Status.CANCELLED
    # the party that did NOT cancel — the member — is the one told
    assert InAppNotification.objects.filter(
        user=reservations["member"], type="RESERVATION_CANCELLED"
    ).exists()
    assert any(reservations["member"].email in m.to for m in mail.outbox)


def test_an_unrelated_user_cannot_cancel(reservations, authenticated_client2, api_client):
    booking = _make_booking(reservations, authenticated_client2)
    other = User.objects.create(code="NOSY01", email="nosy@test.com")
    resp = _member_client(api_client, other).post(CANCEL_URL.format(booking.code))
    assert resp.status_code == status.HTTP_403_FORBIDDEN


def test_a_started_reservation_cannot_be_cancelled(reservations, authenticated_client2):
    # book today directly in the DB, then try to cancel
    thing = reservations["thing"]
    booking = BookingPeriod.objects.create(
        thing_code=thing,
        thing_type=Thing.Type.RESERVE_THING,
        requester_code=reservations["member"],
        requester_email=reservations["member"].email,
        owner_code=reservations["owner"],
        start_date=date.today() - timedelta(days=1),
        end_date=date.today() + timedelta(days=1),
        status=BookingPeriod.Status.ACCEPTED,
    )
    resp = authenticated_client2.post(CANCEL_URL.format(booking.code))
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


# --- serializer surface --------------------------------------------------


def test_the_thing_serializer_exposes_the_reservation_cap(reservations, authenticated_client2):
    resp = authenticated_client2.get(f"/api/v1/things/{reservations['thing'].code}/")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["reservation_max_days"] == 3
    assert resp.data["reservation_horizon_days"] == 90  # collection default
    assert resp.data["rental_weekdays"] == [0, 1, 2, 3, 4]


def test_a_reservation_past_the_horizon_is_refused(reservations, authenticated_client2):
    reservations["collection"].reservation_horizon_days = 10
    reservations["collection"].save(update_fields=["reservation_horizon_days"])
    far = date.today() + timedelta(days=20)
    while far.weekday() > 4:  # land on a Mon–Fri
        far += timedelta(days=1)
    resp = authenticated_client2.post(
        REQUEST_URL.format(reservations["thing"].code),
        {"start_date": str(far), "duration_days": 1},
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "10" in str(resp.data)


def test_send_reminders_skips_reservations(reservations):
    from io import StringIO

    from django.core.management import call_command

    tomorrow = date.today() + timedelta(days=1)
    BookingPeriod.objects.create(
        thing_code=reservations["thing"],
        thing_type=Thing.Type.RESERVE_THING,
        requester_code=reservations["member"],
        requester_email=reservations["member"].email,
        owner_code=reservations["owner"],
        start_date=tomorrow - timedelta(days=1),
        end_date=tomorrow,
        status=BookingPeriod.Status.ACCEPTED,
    )
    mail.outbox.clear()
    call_command("send_reminders", stdout=StringIO())
    assert mail.outbox == []
