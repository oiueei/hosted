"""The row locks in ``booking_service`` — tested as locks, not as re-reads.

Every accept/reject/cancel path re-reads its booking through
``select_for_update()`` and re-checks ``PENDING`` under that lock. Until this
file, **nothing in the suite could tell the lock from the re-read**: removing all
five ``select_for_update()`` calls (and the sixth in ``views/things.py``) left
1428 tests green. That is not a missing assertion, it is a missing *shape* — the
whole suite runs single-threaded, inside one transaction, on one connection, and
a ``FOR UPDATE`` never blocks against the transaction that took it. Zero tests
used ``transaction=True``; zero used threads.

So the guard has to be a real race: two connections, both reading the booking as
PENDING before either commits. Without the lock both proceed and the money /
ownership side effects run twice. With it, the second blocks until the first
commits, re-reads, finds the booking settled and returns ``None``.

**This file is why CI runs on Postgres.** SQLite reports
``has_select_for_update = False``, so Django drops the clause silently and these
tests would measure the unlocked behaviour — they skip there instead of lying.
Locally they are skipped; in CI (``DATABASE_URL`` → postgres:16) they run. To
rehearse one by hand, point DATABASE_URL at a Postgres and run this file.

The barrier is the only artificial part, and it buys determinism rather than
behaviour: ``BookingPeriod.accept``/``reject``/``cancel`` are wrapped so the
first thread inside the transaction waits until the second has reached the
locked read. Nothing about the code under test is patched — the wrapper calls
straight through.
"""

import threading
import time
from datetime import date, timedelta

import pytest
from django.db import connection, connections

from core.models import CalendarExportMark, Collection, Thing, User
from core.models.booking import BookingPeriod
from core.models.transfer import ThingTransfer
from core.services import calendar_export_service
from core.services.booking_service import (
    BookingRequestError,
    accept_booking,
    cancel_booking,
    reject_booking,
    request_date_based_booking,
    request_reservation,
    request_standard_booking,
)

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.skipif(
        not connection.features.has_select_for_update,
        reason="SQLite drops FOR UPDATE silently — these prove the lock, so they need Postgres",
    ),
]


def _pending_booking(thing, owner, requester):
    return BookingPeriod.objects.create(
        thing_code=thing,
        thing_type=thing.type,
        requester_code=requester,
        requester_email=requester.email,
        owner_code=owner,
        status=BookingPeriod.Status.PENDING,
    )


# How long the first transaction keeps holding the row after the second has said
# it is about to read. There is no way to observe "that query is now blocked"
# without reading `pg_locks`, so this is the one timing constant in the file. It
# only ever has to outlast the second thread's own `SELECT … FOR UPDATE` reaching
# the server; a whole second is enormous for that and still costs three seconds
# across the file. The assertion does not depend on the value being *just* right:
# too short and the second thread simply is not blocked yet, which shows up as
# the "never blocked" failure below, never as a false pass.
_HOLD_SECONDS = 1.0


def _run_both(first, second):
    """Run ``first`` and ``second`` concurrently, ``first`` holding its lock.

    Returns ``(first_result, second_result, was_blocked)``.

    The ordering is the whole test, and getting it wrong makes this file pass
    against unlocked code:

    1. ``first`` reaches the inside of its transaction, past the locked read,
       and signals ``inside``.
    2. ``second`` wakes, signals ``attempting`` and calls straight into its own
       locked read.
    3. ``first`` waits ``_HOLD_SECONDS`` *still holding the row*, then commits.

    Step 3 is what an earlier version of this helper got wrong: it released the
    first transaction the moment the second **woke up**, rather than after
    letting it run into the lock. The first could then commit before the second
    had read anything, so the second found the booking already settled and
    returned ``None`` — the exact result a working lock produces — with the lock
    playing no part. It would have passed with ``select_for_update()`` deleted.

    ``was_blocked`` is the direct evidence, rather than an inference from the
    outcome: it records whether the second call was *still running* at the moment
    the first was about to commit. Under a real lock it must be.
    """
    errors = []
    inside = threading.Event()
    attempting = threading.Event()
    second_done = threading.Event()
    observed = {}
    results = {}

    def guard():
        """Hold the row while the second transaction runs into it."""
        inside.set()
        attempting.wait(timeout=5)
        time.sleep(_HOLD_SECONDS)
        # Sampled before this transaction commits: with the row locked the other
        # one cannot have got past its own read yet.
        observed["blocked"] = not second_done.is_set()

    def run_first():
        try:
            results["first"] = first(guard)
        except BaseException as exc:  # noqa: BLE001 — re-raised by the caller
            errors.append(("first", exc))
        finally:
            connections.close_all()

    def run_second():
        try:
            inside.wait(timeout=5)
            attempting.set()
            results["second"] = second()
        except BaseException as exc:  # noqa: BLE001 — re-raised by the caller
            errors.append(("second", exc))
        finally:
            second_done.set()
            connections.close_all()

    threads = [threading.Thread(target=run_first), threading.Thread(target=run_second)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    assert not any(t.is_alive() for t in threads), "a thread deadlocked instead of serialising"

    # Without this, a thread that *crashed* leaves its result unset — and "unset"
    # reads as the `None` that means "the lock made me stand down", so the whole
    # file passes while proving nothing. That is exactly what happened on the
    # first run of these tests against SQLite, whose coarse table lock threw
    # `database table is locked` at the second thread. A blocked transaction
    # waits; it does not raise.
    assert not errors, "a transaction raised instead of waiting its turn: " + "; ".join(
        f"{who}: {exc!r}" for who, exc in errors
    )
    assert set(results) == {"first", "second"}, f"a thread produced no result at all: {results}"
    return results["first"], results["second"], observed.get("blocked", False)


def _with_barrier(model_method, guard):
    """Call ``guard()`` from inside the service's transaction, then carry on."""
    original = getattr(BookingPeriod, model_method)

    def wrapper(self, *args, **kwargs):
        guard()
        return original(self, *args, **kwargs)

    return original, wrapper


class TestOnlyOneTransitionWins:
    def test_two_concurrent_accepts_accept_the_booking_once(self, monkeypatch, user, user2, thing):
        """An owner double-clicking, or the email link racing the in-app button,
        must not run the transfer and the deal twice.

        The observable that needs the lock is the **pair** of return values:
        exactly one Thing and exactly one None. Unlocked, both transactions read
        PENDING and both return a Thing — and `ThingTransfer`'s unique constraint
        would hide it, since `get_or_create` quietly settles for the existing row.
        """
        booking = _pending_booking(thing, user, user2)

        def first(guard):
            original, wrapper = _with_barrier("accept", guard)
            monkeypatch.setattr(BookingPeriod, "accept", wrapper)
            try:
                return accept_booking(booking)
            finally:
                monkeypatch.setattr(BookingPeriod, "accept", original)

        first_result, second_result, was_blocked = _run_both(first, lambda: accept_booking(booking))

        assert was_blocked, "the second transaction read straight past the lock"
        assert [first_result, second_result].count(None) == 1, (
            "both transactions accepted the same booking — the row was never locked"
        )
        booking.refresh_from_db()
        assert booking.status == BookingPeriod.Status.ACCEPTED
        assert ThingTransfer.objects.filter(booking=booking).count() == 1

    def test_an_accept_racing_a_reject_settles_one_way_only(self, monkeypatch, user, user2, thing):
        """The two decisions are mutually exclusive, and the loser is a no-op —
        not a booking that ends up rejected while a transfer says it was lent."""
        booking = _pending_booking(thing, user, user2)

        def first(guard):
            original, wrapper = _with_barrier("accept", guard)
            monkeypatch.setattr(BookingPeriod, "accept", wrapper)
            try:
                return accept_booking(booking)
            finally:
                monkeypatch.setattr(BookingPeriod, "accept", original)

        first_result, second_result, was_blocked = _run_both(first, lambda: reject_booking(booking))

        assert was_blocked, "the reject read straight past the lock"
        assert [first_result, second_result].count(None) == 1
        booking.refresh_from_db()
        assert booking.status == BookingPeriod.Status.ACCEPTED
        # The reject lost, so nothing may claim the thing came back.
        assert ThingTransfer.objects.filter(booking=booking).count() == 1

    def test_a_requester_cancelling_cannot_race_the_owner_accepting(
        self, monkeypatch, user, user2, thing
    ):
        """The reported shape: the guest withdraws at the moment the owner says
        yes. One of them must find the booking already settled."""
        booking = _pending_booking(thing, user, user2)

        def first(guard):
            original, wrapper = _with_barrier("cancel", guard)
            monkeypatch.setattr(BookingPeriod, "cancel", wrapper)
            try:
                return cancel_booking(booking)
            finally:
                monkeypatch.setattr(BookingPeriod, "cancel", original)

        first_result, second_result, was_blocked = _run_both(first, lambda: accept_booking(booking))

        assert was_blocked, "the accept read straight past the cancel's lock"
        assert [first_result, second_result].count(None) == 1
        booking.refresh_from_db()
        assert booking.status in (
            BookingPeriod.Status.CANCELLED,
            BookingPeriod.Status.ACCEPTED,
        )


# ── The create side: two requests for one slot ───────────────────────────────
# `request_reservation` / `request_standard_booking` / `request_date_based_booking`
# each lock the Thing row and *then* check for a clash under that lock. Drop the
# lock and two requests for the same slot both read "free" before either commits,
# and both create the booking. The audit that added this file (2026-09) covered
# accept/reject/cancel; the create paths went in unguarded by any real race.


def _one_shot(original, guard):
    """Wrap ``original`` so ``guard()`` fires exactly once, on the first call.

    The second racing thread reaches the same patched callable once it unblocks
    — it must run straight through, not re-enter the barrier.
    """
    fired = threading.Event()

    def wrapper(*args, **kwargs):
        if not fired.is_set():
            fired.set()
            guard()
        return original(*args, **kwargs)

    return wrapper


class TestTwoRequestsForOneSlotAreSerialised:
    def _reservations_collection(self, owner, *members):
        coll = Collection.objects.create(
            code="RCEC01",
            owner=owner,
            headline="Rooms",
            mode=Collection.Mode.PROPRIETARY,
            allowed_thing_types=["RESERVE_THING"],
            reservation_max_days=3,
        )
        coll.invites.add(*members)
        thing = Thing.objects.create(
            code="RCET01", type=Thing.Type.RESERVE_THING, owner=owner, headline="Sala"
        )
        coll.things.add(thing)
        return coll, thing

    def test_a_reservation_clash_is_serialised_not_double_booked(self, monkeypatch, user, user2):
        """RESERVE auto-confirms with no owner step, so an unlocked clash is two
        members turning up to one room. The loser must get the 409, and exactly
        one ACCEPTED booking may exist."""
        other = User.objects.create(code="RCEUSR", email="rce-other@test.com")
        coll, thing = self._reservations_collection(user, user2, other)
        day = date.today() + timedelta(days=2)
        original = BookingPeriod.has_overlap

        def first(guard):
            monkeypatch.setattr(BookingPeriod, "has_overlap", _one_shot(original, guard))
            try:
                return request_reservation(
                    thing, user2, user.email, day, 1, collection_code=coll.code
                )
            finally:
                monkeypatch.setattr(BookingPeriod, "has_overlap", original)

        def second():
            try:
                return request_reservation(
                    thing, other, user.email, day, 1, collection_code=coll.code
                )
            except BookingRequestError as exc:
                return ("refused", exc.status_code)

        first_result, second_result, was_blocked = _run_both(first, second)

        assert was_blocked, "the second request read straight past the Thing lock"
        assert isinstance(first_result, BookingPeriod)
        assert second_result == ("refused", 409), second_result
        assert (
            BookingPeriod.objects.filter(
                thing_code=thing, status=BookingPeriod.Status.ACCEPTED
            ).count()
            == 1
        )

    def test_a_gift_cannot_be_claimed_twice_at_once(self, monkeypatch, user, user2):
        """Two members claiming the same single-use GIFT: one booking, the thing
        TAKEN once. Unlocked, both read status ACTIVE and both create."""
        other = User.objects.create(code="RCEG02", email="rce-g2@test.com")
        thing = Thing.objects.create(
            code="RCEG01", type=Thing.Type.GIFT_THING, owner=user, headline="A lamp"
        )
        original = BookingPeriod.save

        def first(guard):
            monkeypatch.setattr(BookingPeriod, "save", _one_shot(original, guard))
            try:
                return request_standard_booking(thing, user2, user.email)
            finally:
                monkeypatch.setattr(BookingPeriod, "save", original)

        def second():
            try:
                return request_standard_booking(thing, other, user.email)
            except BookingRequestError as exc:
                return ("refused", exc.status_code)

        first_result, second_result, was_blocked = _run_both(first, second)

        assert was_blocked, "the second claim read past the lock the first was holding"
        assert isinstance(first_result, BookingPeriod)
        assert second_result[0] == "refused", second_result
        thing.refresh_from_db()
        assert thing.status == Thing.Status.TAKEN
        assert BookingPeriod.objects.filter(thing_code=thing).count() == 1

    def test_two_overlapping_loans_cannot_both_be_created(self, monkeypatch, user, user2):
        """Same dates, same drill: the second request finds the first's booking
        under the lock and is a 409, not a second row."""
        other = User.objects.create(code="RCEL02", email="rce-l2@test.com")
        thing = Thing.objects.create(
            code="RCEL01", type=Thing.Type.LEND_THING, owner=user, headline="A drill"
        )
        start = date.today() + timedelta(days=3)
        end = start + timedelta(days=4)
        original = BookingPeriod.has_overlap

        def first(guard):
            monkeypatch.setattr(BookingPeriod, "has_overlap", _one_shot(original, guard))
            try:
                return request_date_based_booking(thing, user2, user.email, start, end)
            finally:
                monkeypatch.setattr(BookingPeriod, "has_overlap", original)

        def second():
            try:
                return request_date_based_booking(thing, other, user.email, start, end)
            except BookingRequestError as exc:
                return ("refused", exc.status_code)

        first_result, second_result, was_blocked = _run_both(first, second)

        assert was_blocked, "the second loan request read past the lock"
        assert isinstance(first_result, BookingPeriod)
        assert second_result == ("refused", 409), second_result
        assert BookingPeriod.objects.filter(thing_code=thing).count() == 1


class TestTwoCuratorsExportingTheCalendarAtOnce:
    """`build_calendar_export` locks the collection row, then reads the
    un-exported reservations and marks them delivered under that lock. Without
    it two curators pressing "download" together each read the same reservations
    — the second file duplicates the first (and the second `bulk_create` of the
    marks trips the `(collection, booking)` unique constraint)."""

    def test_the_second_download_carries_nothing_the_first_already_took(
        self, monkeypatch, user, user2
    ):
        coll = Collection.objects.create(
            code="RCECAL", owner=user, headline="Rooms", mode=Collection.Mode.PROPRIETARY
        )
        for i in range(3):
            thing = Thing.objects.create(
                code=f"RCEC{i}0", type=Thing.Type.LEND_THING, owner=user, headline=f"Tool {i}"
            )
            coll.things.add(thing)
            BookingPeriod.objects.create(
                thing_code=thing,
                thing_type="LEND_THING",
                requester_code=user2,
                requester_email=user2.email,
                owner_code=user,
                start_date=date.today() + timedelta(days=5),
                end_date=date.today() + timedelta(days=8),
                status=BookingPeriod.Status.ACCEPTED,
            )
        original = calendar_export_service._pending_bookings

        def first(guard):
            monkeypatch.setattr(
                calendar_export_service, "_pending_bookings", _one_shot(original, guard)
            )
            try:
                return calendar_export_service.build_calendar_export(coll, user)
            finally:
                monkeypatch.setattr(calendar_export_service, "_pending_bookings", original)

        def second():
            return calendar_export_service.build_calendar_export(coll, user2)

        first_result, second_result, was_blocked = _run_both(first, second)

        assert was_blocked, "the second export ran straight through the first's lock"
        assert first_result[1] == 3, "the curator who got there first carries all three"
        assert second_result[1] == 0, "the other curator's file carries nothing new"
        assert CalendarExportMark.objects.filter(collection=coll).count() == 3
