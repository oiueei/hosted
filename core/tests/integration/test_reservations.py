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


@pytest.fixture
def hourly_reservations(db, user, user2, api_client):
    """An HOUR-unit twin of ``reservations``: Mon-Thu 10-14 & 16-20, Fri 10-14,
    weekend closed, max 3h per reservation."""
    coll = Collection.objects.create(
        code="HRVC01",
        owner=user,
        headline="Ateneu spaces (hourly)",
        status="ACTIVE",
        mode=Collection.Mode.PROPRIETARY,
        allowed_thing_types=["RESERVE_THING"],
        reservation_unit=Collection.ReservationUnit.HOUR,
        reservation_max_minutes=180,
        opening_hours={
            "0": [["10:00", "14:00"], ["16:00", "20:00"]],
            "1": [["10:00", "14:00"], ["16:00", "20:00"]],
            "2": [["10:00", "14:00"], ["16:00", "20:00"]],
            "3": [["10:00", "14:00"], ["16:00", "20:00"]],
            "4": [["10:00", "14:00"]],
        },
    )
    coll.invites.add(user2)
    thing = Thing.objects.create(
        code="HRVT01",
        type=Thing.Type.RESERVE_THING,
        owner=user,
        headline="Sala polivalent",
        location="Planta 1, sala 2",
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
    # both emails show the dates DD/MM/YYYY (like the SPA), never ISO
    for m in mail.outbox:
        assert mon.strftime("%d/%m/%Y") in m.body
        assert mon.isoformat() not in m.body


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
    """The `reservations` fixture is PRIVATE (the model default), so a total
    stranger fails `can_view` before `request_reservation` is ever reached —
    this is `get_viewable_thing`'s generic "not authorized" 403, not the
    membership-specific one below, and it carries no `code`. See
    `test_a_signed_in_non_member_of_a_public_collection_gets_the_not_a_member_code`
    for the one that does — the two must stay tellable apart, since the
    frontend's auto-join only ever fires for the latter."""
    stranger = User.objects.create(code="STRNGR", email="stranger@test.com")
    client = _member_client(api_client, stranger)
    resp = client.post(
        REQUEST_URL.format(reservations["thing"].code),
        {"start_date": str(_next_weekday(0)), "duration_days": 1},
        format="json",
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert "code" not in resp.data
    assert not BookingPeriod.objects.exists()


def test_a_signed_in_non_member_of_a_public_collection_gets_the_not_a_member_code(
    reservations, api_client
):
    """A PUBLIC collection lets anyone view it and reach `request_reservation`,
    where `is_invited` is what actually refuses a non-member — this is the one
    403 the frontend's auto-join is meant to catch, so it has to carry the
    `code` the test above's `can_view` 403 does not."""
    reservations["collection"].visibility = Collection.Visibility.PUBLIC
    reservations["collection"].save(update_fields=["visibility"])
    stranger = User.objects.create(code="STRNG2", email="stranger2@test.com")
    client = _member_client(api_client, stranger)

    resp = client.post(
        REQUEST_URL.format(reservations["thing"].code),
        {"start_date": str(_next_weekday(0)), "duration_days": 1},
        format="json",
    )

    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert resp.data["code"] == "not_a_member"
    assert not BookingPeriod.objects.exists()


# --- the reservation rules -------------------------------------------------


def test_duration_is_capped_at_the_collections_max(reservations, authenticated_client2):
    """The collection sets `reservation_max_days=3`. Four is refused, and the
    refusal names the limit; exactly three still books. Boundary, not just
    'something over the top 400s'."""
    thing = reservations["thing"]
    mon = _next_weekday(0)  # Mon–Wed is three weekdays, inside the space's rules

    over = authenticated_client2.post(
        REQUEST_URL.format(thing.code),
        {"start_date": str(mon), "duration_days": 4},
        format="json",
    )
    assert over.status_code == status.HTTP_400_BAD_REQUEST
    assert "3" in str(over.data)
    assert not BookingPeriod.objects.exists()

    at_the_cap = authenticated_client2.post(
        REQUEST_URL.format(thing.code),
        {"start_date": str(mon), "duration_days": 3},
        format="json",
    )
    assert at_the_cap.status_code == status.HTTP_201_CREATED


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


def test_the_active_reservation_cap_is_per_member_per_collection(
    reservations, authenticated_client2
):
    """`reservation_max_active_per_member=1`: a first reservation (on any thing
    in the collection) succeeds; a second, on a different thing so it can't
    collide on dates, is refused — the cap counts across the whole collection,
    not per thing."""
    coll = reservations["collection"]
    coll.reservation_max_active_per_member = 1
    coll.save(update_fields=["reservation_max_active_per_member"])
    second_thing = Thing.objects.create(
        code="RSVT02", type=Thing.Type.RESERVE_THING, owner=reservations["owner"], headline="Sala 2"
    )
    coll.things.add(second_thing)

    first = authenticated_client2.post(
        REQUEST_URL.format(reservations["thing"].code),
        {"start_date": str(_next_weekday(0)), "duration_days": 1},
        format="json",
    )
    assert first.status_code == status.HTTP_201_CREATED

    over_cap = authenticated_client2.post(
        REQUEST_URL.format(second_thing.code),
        {"start_date": str(_next_weekday(1)), "duration_days": 1},
        format="json",
    )
    assert over_cap.status_code == status.HTTP_400_BAD_REQUEST
    # Coded, with the cap itself, so the request page can say it in the
    # member's language and name the number.
    assert over_cap.data["code"] == "reservation_max_active"
    assert over_cap.data["params"] == {"max": 1}
    assert BookingPeriod.objects.filter(status=BookingPeriod.Status.ACCEPTED).count() == 1


# --- a thing in two reservations collections ------------------------------
# The request form is built from the thing's serialized rules and the POST
# names the collection it came from (`collection_code`); `?collection=` on the
# read is what makes the two agree when the collections disagree on the unit.


@pytest.fixture
def space_in_two_collections(reservations, hourly_reservations):
    thing = reservations["thing"]  # lives in the DAY collection already
    hourly_reservations["collection"].things.add(thing)
    return thing


def test_a_thing_read_through_a_collection_serves_that_collections_rules(
    space_in_two_collections, authenticated_client2
):
    url = f"/api/v1/things/{space_in_two_collections.code}/"

    by_hour = authenticated_client2.get(url, {"collection": "HRVC01"}).data
    assert by_hour["collection_code"] == "HRVC01"
    assert by_hour["reservation_unit"] == "HOUR"
    assert by_hour["opening_hours"]["4"] == [["10:00", "14:00"]]

    by_day = authenticated_client2.get(url, {"collection": "RSVC01"}).data
    assert by_day["collection_code"] == "RSVC01"
    assert by_day["reservation_unit"] == "DAY"


def test_availability_follows_the_named_collection_too(
    space_in_two_collections, hourly_reservations, authenticated_client2
):
    """The hourly collection has no opening hours yet (every day closed); the
    daily one is open Mon-Fri. Each read reports its own collection's answer —
    the indicator above the form has to agree with the form below it."""
    hourly_reservations["collection"].opening_hours = {}
    hourly_reservations["collection"].save(update_fields=["opening_hours"])
    url = f"/api/v1/things/{space_in_two_collections.code}/"

    by_hour = authenticated_client2.get(url, {"collection": "HRVC01"}).data
    assert by_hour["available_today"] is False
    assert by_hour["next_available"] is None

    by_day = authenticated_client2.get(url, {"collection": "RSVC01"}).data
    assert by_day["next_available"] is not None


def test_the_grid_serializer_shares_the_mixin_without_the_resolver(space_in_two_collections, user2):
    """`CollectionThingSummarySerializer` shares `ThingComputedFieldsMixin` but
    has no `_viewable_collection`; its one call site always passes
    `parent_collection`. Reached without one and with `?collection=` in the
    request, the availability walk must fall back quietly, not raise."""
    from rest_framework.request import Request
    from rest_framework.test import APIRequestFactory, force_authenticate

    from core.serializers.collection import CollectionThingSummarySerializer

    raw = APIRequestFactory().get("/", {"collection": "HRVC01"})
    force_authenticate(raw, user=user2)

    data = CollectionThingSummarySerializer(
        space_in_two_collections, context={"request": Request(raw)}
    ).data

    assert data["available_today"] in (True, False)


def test_naming_a_collection_the_reader_cannot_see_changes_nothing(
    space_in_two_collections, user, authenticated_client2
):
    """`?collection=` is a preference among collections the reader may already
    read, never a door: a private group they aren't in is ignored, and its
    code, headline and rules stay out of the response."""
    hidden = Collection.objects.create(
        code="HIDC01",
        owner=user,
        headline="Staff only",
        status="ACTIVE",
        mode=Collection.Mode.PROPRIETARY,
        allowed_thing_types=["RESERVE_THING"],
        reservation_unit=Collection.ReservationUnit.HOUR,
    )
    hidden.things.add(space_in_two_collections)
    url = f"/api/v1/things/{space_in_two_collections.code}/"

    data = authenticated_client2.get(url, {"collection": "HIDC01"}).data

    assert data["collection_code"] in {"RSVC01", "HRVC01"}
    assert data["collection_headline"] != "Staff only"


# --- HOUR-unit reservations (API) -----------------------------------------


def test_an_hourly_reservation_is_confirmed_on_the_spot(hourly_reservations, authenticated_client2):
    thing = hourly_reservations["thing"]
    mon = _next_weekday(0)
    mail.outbox.clear()

    resp = authenticated_client2.post(
        REQUEST_URL.format(thing.code),
        {"start_date": str(mon), "start_time": "11:00", "end_time": "13:00"},
        format="json",
    )

    assert resp.status_code == status.HTTP_201_CREATED
    assert resp.data["start_date"] == str(mon)
    assert resp.data["end_date"] == str(mon + timedelta(days=1))
    assert resp.data["start_time"] == "11:00:00"
    assert resp.data["end_time"] == "13:00:00"
    booking = BookingPeriod.objects.get(code=resp.data["booking_code"])
    assert booking.status == BookingPeriod.Status.ACCEPTED
    assert len(mail.outbox) == 2  # requester confirmation + owner notice
    # the notice names the date once and both times — not the day-based
    # end_date (mon + 1), which would read as the reservation crossing a day
    for m in mail.outbox:
        assert f"{mon.strftime('%d/%m/%Y')} 11:00" in m.body
        assert "13:00" in m.body
        assert (mon + timedelta(days=1)).strftime("%d/%m/%Y") not in m.body
    # the owner's in-app notice carries the hours too (unrendered by the SPA
    # today, but the data is there for when it is)
    note = InAppNotification.objects.get(user=hourly_reservations["owner"], type="RESERVATION_MADE")
    assert note.payload["start_time"] == "11:00"
    assert note.payload["end_time"] == "13:00"


def test_an_hourly_request_outside_opening_hours_is_refused(
    hourly_reservations, authenticated_client2
):
    resp = authenticated_client2.post(
        REQUEST_URL.format(hourly_reservations["thing"].code),
        {"start_date": str(_next_weekday(0)), "start_time": "13:00", "end_time": "17:00"},
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert not BookingPeriod.objects.exists()


def test_a_request_for_a_slot_that_already_began_today_is_refused(hourly_reservations, api_client):
    """The request page no longer offers a start that has passed; the API
    refuses one sent any other way (found in review, 2026-09-18). 2026-06-01
    is a Monday, open 10-14 and 16-20; the clock stands at 12:00 (UTC here)."""
    import time_machine

    thing = hourly_reservations["thing"]
    with time_machine.travel("2026-06-01 12:00:00+00:00", tick=False):
        # Signed in inside the travel: a token minted at the real "now" would
        # not be valid yet in June.
        client = _member_client(api_client, hourly_reservations["member"])
        past = client.post(
            REQUEST_URL.format(thing.code),
            {"start_date": "2026-06-01", "start_time": "10:00", "end_time": "11:00"},
            format="json",
        )
        later = client.post(
            REQUEST_URL.format(thing.code),
            {"start_date": "2026-06-01", "start_time": "13:00", "end_time": "14:00"},
            format="json",
        )

    assert past.status_code == status.HTTP_400_BAD_REQUEST
    # The English sentence stays; the code is what lets the request page say it
    # in the member's own language (core has no gettext catalogue).
    assert past.data == {
        "error": "That time has already begun.",
        "code": "reservation_already_begun",
    }
    assert later.status_code == status.HTTP_201_CREATED


@pytest.mark.parametrize(
    ("start", "end", "body"),
    [
        (
            "10:30",
            "11:30",
            {
                "error": "Reservations here start every 60 minutes from opening time.",
                "code": "reservation_off_grid_start",
                "params": {"step": 60},
            },
        ),
        (
            "10:00",
            "11:30",
            {
                "error": "A reservation here lasts a multiple of 60 minutes.",
                "code": "reservation_off_grid_length",
                "params": {"step": 60},
            },
        ),
        (
            "10:00:30",
            "11:00:30",
            {
                "error": "Reservation times are whole minutes (HH:MM).",
                "code": "reservation_whole_minutes",
            },
        ),
    ],
)
def test_an_hourly_request_off_the_pickers_grid_is_refused_with_the_rule(
    hourly_reservations, authenticated_client2, start, end, body
):
    """The request page only ever sends starts on the minimum-minute grid and
    durations that are multiples of it; a request made straight to the API
    gets the same rules, named, instead of a booking that leaves slivers no
    member can book (found in review, 2026-09-18)."""
    resp = authenticated_client2.post(
        REQUEST_URL.format(hourly_reservations["thing"].code),
        {"start_date": str(_next_weekday(0)), "start_time": start, "end_time": end},
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.data == body
    assert not BookingPeriod.objects.exists()


def test_an_hourly_clash_is_a_409_and_leaves_the_rest_of_the_day_free(
    hourly_reservations, authenticated_client2, api_client
):
    thing = hourly_reservations["thing"]
    mon = _next_weekday(0)
    first = authenticated_client2.post(
        REQUEST_URL.format(thing.code),
        {"start_date": str(mon), "start_time": "10:00", "end_time": "12:00"},
        format="json",
    )
    assert first.status_code == status.HTTP_201_CREATED

    other = User.objects.create(code="HMEMB2", email="hm2@test.com")
    hourly_reservations["collection"].invites.add(other)
    clash = _member_client(api_client, other).post(
        REQUEST_URL.format(thing.code),
        {"start_date": str(mon), "start_time": "11:00", "end_time": "13:00"},
        format="json",
    )
    assert clash.status_code == status.HTTP_409_CONFLICT

    free = _member_client(api_client, other).post(
        REQUEST_URL.format(thing.code),
        {"start_date": str(mon), "start_time": "12:00", "end_time": "14:00"},
        format="json",
    )
    assert free.status_code == status.HTTP_201_CREATED


def test_a_full_day_hourly_reservation_is_refused_when_it_exceeds_the_hour_cap(
    hourly_reservations, authenticated_client2
):
    """CA's call, made explicitly when this feature was scoped: the cap
    applies to a full-day reservation too, no exception. Monday's full day is
    600 minutes (10:00-20:00 across the lunch gap); this collection's cap is
    180."""
    resp = authenticated_client2.post(
        REQUEST_URL.format(hourly_reservations["thing"].code),
        {"start_date": str(_next_weekday(0)), "start_time": "10:00", "end_time": "20:00"},
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert "180" in str(resp.data)


def test_a_full_day_hourly_reservation_is_accepted_when_it_fits_under_a_generous_cap(
    db, user, user2, authenticated_client2
):
    coll = Collection.objects.create(
        code="HRVC02",
        owner=user,
        headline="Ateneu spaces (hourly, generous cap)",
        status="ACTIVE",
        mode=Collection.Mode.PROPRIETARY,
        allowed_thing_types=["RESERVE_THING"],
        reservation_unit=Collection.ReservationUnit.HOUR,
        reservation_max_minutes=720,
        opening_hours={"0": [["10:00", "14:00"], ["16:00", "20:00"]]},
    )
    coll.invites.add(user2)
    thing = Thing.objects.create(
        code="HRVT02", type=Thing.Type.RESERVE_THING, owner=user, headline="Sala 2"
    )
    coll.things.add(thing)

    resp = authenticated_client2.post(
        REQUEST_URL.format(thing.code),
        {"start_date": str(_next_weekday(0)), "start_time": "10:00", "end_time": "20:00"},
        format="json",
    )
    assert resp.status_code == status.HTTP_201_CREATED


def test_sending_both_duration_days_and_hours_is_a_400(hourly_reservations, authenticated_client2):
    resp = authenticated_client2.post(
        REQUEST_URL.format(hourly_reservations["thing"].code),
        {
            "start_date": str(_next_weekday(0)),
            "duration_days": 1,
            "start_time": "10:00",
            "end_time": "12:00",
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


def test_sending_neither_duration_nor_hours_is_a_400(hourly_reservations, authenticated_client2):
    resp = authenticated_client2.post(
        REQUEST_URL.format(hourly_reservations["thing"].code),
        {"start_date": str(_next_weekday(0))},
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


def test_a_reservation_request_for_a_past_date_is_refused(reservations, authenticated_client2):
    resp = authenticated_client2.post(
        REQUEST_URL.format(reservations["thing"].code),
        {"start_date": str(date.today() - timedelta(days=1)), "duration_days": 1},
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert not BookingPeriod.objects.exists()


def test_an_hourly_request_missing_end_time_is_a_400(hourly_reservations, authenticated_client2):
    resp = authenticated_client2.post(
        REQUEST_URL.format(hourly_reservations["thing"].code),
        {"start_date": str(_next_weekday(0)), "start_time": "10:00"},
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


def test_an_hourly_request_with_end_before_start_is_a_400(
    hourly_reservations, authenticated_client2
):
    resp = authenticated_client2.post(
        REQUEST_URL.format(hourly_reservations["thing"].code),
        {"start_date": str(_next_weekday(0)), "start_time": "12:00", "end_time": "10:00"},
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST


def test_the_day_mode_endpoint_is_unaffected_by_the_hour_serializer_fields(
    reservations, authenticated_client2
):
    """A DAY-unit collection's own flow is untouched by the new optional
    fields — the exact request that worked before still does."""
    resp = authenticated_client2.post(
        REQUEST_URL.format(reservations["thing"].code),
        {"start_date": str(_next_weekday(0)), "duration_days": 1},
        format="json",
    )
    assert resp.status_code == status.HTTP_201_CREATED
    assert resp.data["start_time"] is None
    assert resp.data["end_time"] is None


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


def test_a_reserve_create_naming_a_missing_collection_is_a_404_not_a_400(authenticated_client):
    """The documented contract for an unknown ``collection_code`` is 404, for
    every type. The RESERVE-only "must be a reservations collection" 400 used to
    fire first — turning a typo'd code into a wrong status and skipping the
    existence check entirely."""
    resp = authenticated_client.post(
        "/api/v1/things/",
        {"type": "RESERVE_THING", "headline": "Ghost room", "collection_code": "ZZZZZZ"},
        format="json",
    )
    assert resp.status_code == status.HTTP_404_NOT_FOUND
    assert not Thing.objects.filter(headline="Ghost room").exists()


def test_a_reserve_create_on_someone_elses_collection_is_a_403_not_a_reservations_probe(
    authenticated_client2, user
):
    """A stranger naming a real non-reservations collection gets the same 403 any
    other type would — not the RESERVE 400. Otherwise the 400-vs-403 split told
    an outsider "this code names a reservations collection" one guess at a time.
    """
    Collection.objects.create(code="OTHER1", owner=user, headline="Someone else's")
    resp = authenticated_client2.post(
        "/api/v1/things/",
        {"type": "RESERVE_THING", "headline": "Sneaky room", "collection_code": "OTHER1"},
        format="json",
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert not Thing.objects.filter(headline="Sneaky room").exists()


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
    assert "type" in resp.data  # field-keyed, like every other thing-type refusal
    assert not Thing.objects.filter(headline="A gift").exists()


@pytest.mark.parametrize(
    ("payload", "reason"),
    [
        (
            {"headline": "Mixed", "allowed_thing_types": ["RESERVE_THING", "GIFT_THING"]},
            "can't be mixed",
        ),
        (
            {
                "headline": "Community reservations",
                "mode": "COMMUNITY",
                "allowed_thing_types": ["RESERVE_THING"],
            },
            "community collection",
        ),
    ],
)
def test_reserve_allowlist_rules_at_collection_creation(authenticated_client, payload, reason):
    resp = authenticated_client.post("/api/v1/collections/", payload, format="json")
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    # The refusal says which rule was broken — mixing types, or COMMUNITY mode —
    # not just "400". And no half-made collection is left behind.
    assert reason in str(resp.data)
    assert not Collection.objects.filter(headline=payload["headline"]).exists()


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
    assert "community collection" in str(resp.data)
    coll.refresh_from_db()
    assert coll.mode == Collection.Mode.PROPRIETARY  # the switch did not take


def test_creating_an_hourly_reservations_collection_stores_opening_hours(authenticated_client):
    resp = authenticated_client.post(
        "/api/v1/collections/",
        {
            "headline": "Ateneu (hourly)",
            "allowed_thing_types": ["RESERVE_THING"],
            "reservation_unit": "HOUR",
            "reservation_max_minutes": 180,
            "opening_hours": {"0": [["16:00", "20:00"], ["10:00", "14:00"]]},
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_201_CREATED
    assert resp.data["reservation_unit"] == "HOUR"
    # Sorted by the validator, regardless of the order the owner sent them in.
    assert resp.data["opening_hours"] == {"0": [["10:00", "14:00"], ["16:00", "20:00"]]}
    assert resp.data["reservation_max_minutes"] == 180


def test_creating_a_collection_with_overlapping_opening_hours_is_a_400(authenticated_client):
    resp = authenticated_client.post(
        "/api/v1/collections/",
        {
            "headline": "Bad hours",
            "allowed_thing_types": ["RESERVE_THING"],
            "reservation_unit": "HOUR",
            "opening_hours": {"0": [["10:00", "15:00"], ["14:00", "20:00"]]},
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert not Collection.objects.filter(headline="Bad hours").exists()


def test_creating_a_collection_with_a_minimum_above_the_maximum_is_a_400(authenticated_client):
    resp = authenticated_client.post(
        "/api/v1/collections/",
        {
            "headline": "Backwards",
            "allowed_thing_types": ["RESERVE_THING"],
            "reservation_unit": "HOUR",
            "reservation_min_minutes": 120,
            "reservation_max_minutes": 60,
            "opening_hours": {"0": [["10:00", "14:00"]]},
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert not Collection.objects.filter(headline="Backwards").exists()


def test_updating_only_the_minimum_above_an_untouched_maximum_is_a_400(authenticated_client):
    """The minimum is being changed but the maximum isn't part of this
    request at all — the check must fall back to the stored maximum, not skip
    itself because only one side of the pair was sent."""
    coll = Collection.objects.create(
        code="RSVC08",
        owner=User.objects.get(code="TEST01"),
        headline="X",
        allowed_thing_types=["RESERVE_THING"],
        reservation_unit=Collection.ReservationUnit.HOUR,
        reservation_min_minutes=15,
        reservation_max_minutes=60,
        opening_hours={"0": [["10:00", "14:00"]]},
    )
    resp = authenticated_client.patch(
        f"/api/v1/collections/{coll.code}/", {"reservation_min_minutes": 90}, format="json"
    )
    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    coll.refresh_from_db()
    assert coll.reservation_min_minutes == 15  # the update did not go through


def test_updating_a_reservations_collection_switches_it_to_hourly(authenticated_client):
    coll = Collection.objects.create(
        code="RSVC06",
        owner=User.objects.get(code="TEST01"),
        headline="X",
        allowed_thing_types=["RESERVE_THING"],
        reservation_max_days=1,
    )
    resp = authenticated_client.patch(
        f"/api/v1/collections/{coll.code}/",
        {
            "reservation_unit": "HOUR",
            "opening_hours": {"0": [["10:00", "14:00"]]},
            "reservation_max_minutes": 120,
        },
        format="json",
    )
    assert resp.status_code == status.HTTP_200_OK
    coll.refresh_from_db()
    assert coll.reservation_unit == Collection.ReservationUnit.HOUR
    assert coll.opening_hours == {"0": [["10:00", "14:00"]]}
    assert coll.reservation_max_minutes == 120


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


def test_cancelling_an_hourly_reservation_carries_the_hours_in_the_notice(
    hourly_reservations, authenticated_client2
):
    mon = _next_weekday(0)
    resp = authenticated_client2.post(
        REQUEST_URL.format(hourly_reservations["thing"].code),
        {"start_date": str(mon), "start_time": "11:00", "end_time": "13:00"},
        format="json",
    )
    assert resp.status_code == status.HTTP_201_CREATED
    booking = BookingPeriod.objects.get(code=resp.data["booking_code"])
    mail.outbox.clear()

    resp = authenticated_client2.post(CANCEL_URL.format(booking.code))
    assert resp.status_code == status.HTTP_200_OK

    note = InAppNotification.objects.get(
        user=hourly_reservations["owner"], type="RESERVATION_CANCELLED"
    )
    assert note.payload["start_time"] == "11:00"
    assert note.payload["end_time"] == "13:00"
    (m,) = mail.outbox
    assert f"{mon.strftime('%d/%m/%Y')} 11:00" in m.body and "13:00" in m.body


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
    assert "already started" in str(resp.data)
    booking.refresh_from_db()
    assert booking.status == BookingPeriod.Status.ACCEPTED  # still confirmed, not cancelled


# --- serializer surface --------------------------------------------------


def test_the_thing_serializer_exposes_the_reservation_cap(reservations, authenticated_client2):
    resp = authenticated_client2.get(f"/api/v1/things/{reservations['thing'].code}/")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["reservation_max_days"] == 3
    assert resp.data["reservation_horizon_days"] == 90  # collection default
    assert resp.data["rental_weekdays"] == [0, 1, 2, 3, 4]
    assert resp.data["reservation_unit"] == "DAY"


def test_the_thing_serializer_exposes_the_hourly_rules(hourly_reservations, authenticated_client2):
    resp = authenticated_client2.get(f"/api/v1/things/{hourly_reservations['thing'].code}/")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["reservation_unit"] == "HOUR"
    assert resp.data["reservation_min_minutes"] == 60
    assert resp.data["reservation_max_minutes"] == 180
    assert resp.data["opening_hours"]["0"] == [["10:00", "14:00"], ["16:00", "20:00"]]


def test_the_thing_serializer_hides_reservation_unit_for_non_reserve_types(authenticated_client):
    coll = Collection.objects.create(
        code="RSVC07", owner=User.objects.get(code="TEST01"), headline="X"
    )
    thing = Thing.objects.create(
        code="RSVT07",
        type=Thing.Type.GIFT_THING,
        owner=User.objects.get(code="TEST01"),
        headline="A gift",
    )
    coll.things.add(thing)
    resp = authenticated_client.get(f"/api/v1/things/{thing.code}/")
    assert resp.status_code == status.HTTP_200_OK
    assert resp.data["reservation_unit"] is None
    assert resp.data["reservation_min_minutes"] is None
    assert resp.data["reservation_max_minutes"] is None
    assert resp.data["opening_hours"] == {}


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
    assert resp.data == {
        "error": "This space can only be booked up to 10 days ahead.",
        "code": "reservation_beyond_horizon",
        "params": {"days": 10},
    }


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
