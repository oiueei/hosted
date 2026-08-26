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

import pytest
from django.db import connection, connections

from core.models.booking import BookingPeriod
from core.models.transfer import ThingTransfer
from core.services.booking_service import accept_booking, cancel_booking, reject_booking

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
