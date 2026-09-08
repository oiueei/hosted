"""Unit tests for the RESERVE_THING model layer (commit 1).

Pure model methods: ``Collection.is_reservations_collection`` and
``Collection.reservation_violation`` (the server-side backstop the reservation
request view calls), plus the fact that a RESERVE booking participates in the
strict-overlap / live-availability machinery.
"""

from datetime import date, timedelta

import pytest

from core.models import BookingPeriod, Collection, Thing, User
from core.models.booking import DATE_BASED_TYPES, ON_SITE_TYPES, SINGLE_USE_TYPES
from core.services.booking_service import (
    BookingRequestError,
    cancel_reservation,
    compute_availability,
    request_reservation,
    resolve_reservations_collection,
)

pytestmark = pytest.mark.django_db


def _next_weekday(weekday):
    """First future date (from tomorrow) that falls on the given weekday (0=Mon)."""
    d = date.today() + timedelta(days=1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d


@pytest.fixture
def reservations_collection(db):
    owner = User.objects.create(code="RSVOWN", email="rsvown@test.com", name="Ateneu")
    coll = Collection.objects.create(
        code="RSVCOL",
        owner=owner,
        headline="Ateneu spaces",
        status="ACTIVE",
        mode=Collection.Mode.PROPRIETARY,
        allowed_thing_types=["RESERVE_THING"],
        reservation_max_days=3,
        rental_weekdays=[0, 1, 2, 3, 4],  # Mon–Fri
    )
    return coll


# --- is_reservations_collection -----------------------------------------------


def test_is_reservations_collection_true_only_for_solo_reserve_allowlist(reservations_collection):
    assert reservations_collection.is_reservations_collection() is True


@pytest.mark.parametrize(
    "allowlist",
    [
        [],
        ["GIFT_THING"],
        ["RESERVE_THING", "GIFT_THING"],
        ["GIFT_THING", "RESERVE_THING"],
    ],
)
def test_is_reservations_collection_false_for_anything_else(db, allowlist):
    owner = User.objects.create(code="OWNX01", email="ownx@test.com")
    coll = Collection.objects.create(
        code="COLLX1", owner=owner, headline="X", allowed_thing_types=allowlist
    )
    assert coll.is_reservations_collection() is False


# --- reservation_violation: duration -----------------------------------------


def test_reservation_violation_rejects_zero_or_negative_days(reservations_collection):
    mon = _next_weekday(0)
    assert reservations_collection.reservation_violation(mon, 0) is not None
    assert reservations_collection.reservation_violation(mon, -1) is not None


def test_reservation_violation_rejects_over_the_max(reservations_collection):
    mon = _next_weekday(0)
    msg = reservations_collection.reservation_violation(mon, 4)  # max is 3
    assert msg is not None and "3" in msg


def test_reservation_violation_accepts_exactly_the_max(reservations_collection):
    mon = _next_weekday(0)  # Mon+3 occupies Mon/Tue/Wed — all weekdays
    assert reservations_collection.reservation_violation(mon, 3) is None


# --- reservation_violation: every day of the span must be an open weekday ----


def test_reservation_violation_rejects_a_span_crossing_a_closed_day(reservations_collection):
    """Fri + 3 days occupies Fri/Sat/Sun — Sat and Sun are not in Mon–Fri."""
    fri = _next_weekday(4)
    assert reservations_collection.reservation_violation(fri, 3) is not None


def test_reservation_violation_rejects_a_start_on_a_closed_day(reservations_collection):
    sat = _next_weekday(5)
    assert reservations_collection.reservation_violation(sat, 1) is not None


def test_reservation_violation_ignores_weekdays_when_unset(db):
    owner = User.objects.create(code="OWNY01", email="owny@test.com")
    coll = Collection.objects.create(
        code="COLLY1",
        owner=owner,
        headline="Any day",
        allowed_thing_types=["RESERVE_THING"],
        reservation_max_days=7,
        rental_weekdays=[],
    )
    sun = _next_weekday(6)
    assert coll.reservation_violation(sun, 7) is None


# --- the booking-model wiring ------------------------------------------------


def test_reserve_thing_is_date_based_and_on_site_not_single_use():
    assert "RESERVE_THING" in DATE_BASED_TYPES
    assert "RESERVE_THING" in ON_SITE_TYPES
    assert "RESERVE_THING" not in SINGLE_USE_TYPES


def test_an_accepted_reservation_blocks_its_day_and_frees_the_next(db):
    """Strict overlap: a booking [Mon, Wed] blocks Mon+Tue, leaves Wed free."""
    owner = User.objects.create(code="AVOWN1", email="avown@test.com")
    requester = User.objects.create(code="AVREQ1", email="avreq@test.com")
    thing = Thing.objects.create(
        code="AVTHG1", type=Thing.Type.RESERVE_THING, owner=owner, headline="Room"
    )
    mon = _next_weekday(0)
    BookingPeriod.objects.create(
        thing_code=thing,
        thing_type=Thing.Type.RESERVE_THING,
        requester_code=requester,
        requester_email=requester.email,
        owner_code=owner,
        start_date=mon,
        end_date=mon + timedelta(days=2),  # occupies Mon, Tue
        status=BookingPeriod.Status.ACCEPTED,
    )
    blocked = list(BookingPeriod.get_blocked_periods(thing.code))
    _, next_available = compute_availability(blocked, today=mon, horizon_days=30)
    assert next_available == mon + timedelta(days=2)  # Wed, the return day, is free


def test_request_reservation_refuses_a_thing_with_no_reservations_collection(db):
    """Defensive: a RESERVE thing that somehow sits in no reservations
    collection (a hand-edited allowlist) cannot be booked."""
    owner = User.objects.create(code="RRSVO1", email="rrsvo@test.com")
    member = User.objects.create(code="RRSVM1", email="rrsvm@test.com")
    coll = Collection.objects.create(
        code="RRSVC1", owner=owner, headline="X", allowed_thing_types=["GIFT_THING"]
    )
    coll.invites.add(member)
    thing = Thing.objects.create(
        code="RRSVT1", type=Thing.Type.RESERVE_THING, owner=owner, headline="Room"
    )
    coll.things.add(thing)

    assert resolve_reservations_collection(thing) is None
    with pytest.raises(BookingRequestError):
        request_reservation(thing, member, owner.email, _next_weekday(0), 1)


def test_cancel_reservation_rejects_a_non_reservation_booking(db):
    owner = User.objects.create(code="CRSVO1", email="crsvo@test.com")
    member = User.objects.create(code="CRSVM1", email="crsvm@test.com")
    thing = Thing.objects.create(
        code="CRSVT1", type=Thing.Type.LEND_THING, owner=owner, headline="Drill"
    )
    booking = BookingPeriod.objects.create(
        thing_code=thing,
        thing_type=Thing.Type.LEND_THING,
        requester_code=member,
        requester_email=member.email,
        owner_code=owner,
        start_date=_next_weekday(0),
        end_date=_next_weekday(0) + timedelta(days=2),
        status=BookingPeriod.Status.ACCEPTED,
    )
    with pytest.raises(BookingRequestError):
        cancel_reservation(booking, member)


def test_cancel_reservation_is_idempotent_under_a_lost_race(db):
    owner = User.objects.create(code="IRSVO1", email="irsvo@test.com")
    member = User.objects.create(code="IRSVM1", email="irsvm@test.com")
    coll = Collection.objects.create(
        code="IRSVC1",
        owner=owner,
        headline="X",
        allowed_thing_types=["RESERVE_THING"],
        reservation_max_days=1,
    )
    coll.invites.add(member)
    thing = Thing.objects.create(
        code="IRSVT1", type=Thing.Type.RESERVE_THING, owner=owner, headline="Room"
    )
    coll.things.add(thing)
    booking = request_reservation(thing, member, owner.email, _next_weekday(0), 1)

    cancel_reservation(booking, member)
    with pytest.raises(BookingRequestError):
        cancel_reservation(booking, owner)  # already cancelled


def test_project_note_defaults_blank_and_holds_512(db):
    owner = User.objects.create(code="PNOWN1", email="pnown@test.com")
    requester = User.objects.create(code="PNREQ1", email="pnreq@test.com")
    thing = Thing.objects.create(
        code="PNTHG1", type=Thing.Type.RESERVE_THING, owner=owner, headline="Lab"
    )
    b1 = BookingPeriod.objects.create(
        thing_code=thing,
        thing_type=Thing.Type.RESERVE_THING,
        requester_code=requester,
        requester_email=requester.email,
        owner_code=owner,
    )
    assert b1.project_note == ""
    b2 = BookingPeriod.objects.create(
        thing_code=thing,
        thing_type=Thing.Type.RESERVE_THING,
        requester_code=requester,
        requester_email=requester.email,
        owner_code=owner,
        project_note="x" * 512,
    )
    b2.refresh_from_db()
    assert len(b2.project_note) == 512
