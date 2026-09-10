"""Unit tests for the RESERVE_THING model layer (commit 1).

Pure model methods: ``Collection.is_reservations_collection`` and
``Collection.reservation_violation`` (the server-side backstop the reservation
request view calls), plus the fact that a RESERVE booking participates in the
strict-overlap / live-availability machinery.
"""

from datetime import date, timedelta

import pytest
import time_machine

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


# --- reservation_violation: the "how far ahead" horizon ---------------------


def test_reservation_violation_rejects_past_the_horizon(db):
    owner = User.objects.create(code="HZOWN1", email="hzown@test.com")
    coll = Collection.objects.create(
        code="HZCOL1",
        owner=owner,
        headline="Short lead time",
        allowed_thing_types=["RESERVE_THING"],
        reservation_max_days=1,
        reservation_horizon_days=14,
        rental_weekdays=[],
    )
    today = date(2026, 6, 1)
    assert coll.reservation_violation(today + timedelta(days=13), 1, today=today) is None
    msg = coll.reservation_violation(today + timedelta(days=20), 1, today=today)
    assert msg is not None and "14" in msg


def test_the_horizon_is_the_pickup_day_not_the_exclusive_end(db):
    """A pickup exactly ``reservation_horizon_days`` out is allowed; the day
    after is not. The bug this pins: the check judged the exclusive ``end_date``
    (start + duration), so with any duration the last few days the picker
    offered — and every day of them when ``reservation_max_days`` > 1 — were
    refused by the server the picker's own ``maxDate`` had just allowed.
    """
    owner = User.objects.create(code="HZOWN3", email="hzown3@test.com")
    coll = Collection.objects.create(
        code="HZCOL3",
        owner=owner,
        headline="Exact horizon",
        allowed_thing_types=["RESERVE_THING"],
        reservation_max_days=3,
        reservation_horizon_days=7,
        rental_weekdays=[],
    )
    today = date(2026, 6, 1)
    # Pickup ON the horizon, whatever the duration — the picker offers this day.
    assert coll.reservation_violation(today + timedelta(days=7), 1, today=today) is None
    assert coll.reservation_violation(today + timedelta(days=7), 3, today=today) is None
    # One day past it: refused, and the message names the limit.
    msg = coll.reservation_violation(today + timedelta(days=8), 1, today=today)
    assert msg is not None and "7" in msg


def test_reservation_horizon_defaults_to_90(db):
    owner = User.objects.create(code="HZOWN2", email="hzown2@test.com")
    coll = Collection.objects.create(
        code="HZCOL2", owner=owner, headline="X", allowed_thing_types=["RESERVE_THING"]
    )
    assert coll.reservation_horizon_days == 90
    today = date(2026, 6, 1)
    assert coll.reservation_violation(today + timedelta(days=89), 1, today=today) is None
    assert coll.reservation_violation(today + timedelta(days=95), 1, today=today) is not None


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


def test_availability_window_for_reserve_uses_the_collections_horizon_and_closures(
    reservations_collection,
):
    """The RESERVE branch of `Thing.availability_window` walks to the
    collection's `reservation_horizon_days` (not the fixed 90) and skips its
    `closed_dates`, so the card indicator agrees with `RequestThingPage`'s
    picker."""
    coll = reservations_collection
    thing = Thing.objects.create(
        code="AVWRSV", type=Thing.Type.RESERVE_THING, owner=coll.owner, headline="Sala"
    )
    coll.things.add(thing)

    mon = _next_weekday(0)
    with time_machine.travel(mon, tick=False):
        # Baseline: open today.
        assert thing.availability_window()["available_today"] is True

        # Close today and tomorrow → next_available is the day after.
        coll.closed_dates = [mon.isoformat(), (mon + timedelta(days=1)).isoformat()]
        coll.save(update_fields=["closed_dates"])
        del thing._availability_window_cache  # clear the per-instance memo
        window = thing.availability_window()
        assert window["available_today"] is False
        assert window["next_available"] == mon + timedelta(days=2)

        # A horizon of 1 day with both days shut → nothing in range.
        coll.reservation_horizon_days = 1
        coll.save(update_fields=["reservation_horizon_days"])
        del thing._availability_window_cache
        assert thing.availability_window()["next_available"] is None


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
