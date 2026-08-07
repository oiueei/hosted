"""
Unit tests for ThingTransfer model and close_transfers management command.
"""

from datetime import date, timedelta
from io import StringIO

import pytest
import time_machine
from django.core.management import call_command

from core.models.booking import BookingPeriod
from core.models.thing import Thing
from core.models.transfer import ThingTransfer
from core.models.user import User
from core.services.booking_service import accept_booking


@pytest.mark.django_db
class TestThingTransferModel:
    """Tests for ThingTransfer model."""

    def test_create_transfer(self, user, user2, thing):
        """Should create a transfer record."""
        transfer = ThingTransfer.objects.create(
            thing=thing,
            from_user=user,
            to_user=user2,
            lent_date=date.today(),
        )
        assert transfer.code
        assert len(transfer.code) == 6
        assert transfer.thing == thing
        assert transfer.from_user == user
        assert transfer.to_user == user2
        assert transfer.returned_date is None

    def test_transfer_str_active(self, user, user2, thing):
        """String representation should show active status."""
        transfer = ThingTransfer.objects.create(
            thing=thing,
            from_user=user,
            to_user=user2,
            lent_date=date.today(),
        )
        assert "active" in str(transfer)

    def test_transfer_str_returned(self, user, user2, thing):
        """String representation should show returned status."""
        transfer = ThingTransfer.objects.create(
            thing=thing,
            from_user=user,
            to_user=user2,
            lent_date=date.today(),
            returned_date=date.today(),
        )
        assert "returned" in str(transfer)

    def test_transfer_ordering(self, user, user2, thing):
        """Transfers should be ordered by -lent_date."""
        t1 = ThingTransfer.objects.create(
            thing=thing,
            from_user=user,
            to_user=user2,
            lent_date=date.today() - timedelta(days=10),
        )
        t2 = ThingTransfer.objects.create(
            thing=thing,
            from_user=user,
            to_user=user2,
            lent_date=date.today(),
        )
        transfers = list(ThingTransfer.objects.filter(thing=thing))
        assert transfers[0] == t2
        assert transfers[1] == t1


@pytest.mark.django_db
class TestTransferCreatedOnBookingAccept:
    """Tests that accepting a booking creates a ThingTransfer."""

    def _make_booking(self, thing, owner, requester, thing_type="LEND_THING", **kwargs):
        return BookingPeriod.objects.create(
            thing_code=thing,
            thing_type=thing_type,
            requester_code=requester,
            requester_email=requester.email,
            owner_code=owner,
            **kwargs,
        )

    def test_accept_date_based_creates_transfer(self, user, user2, thing):
        """Accepting a date-based booking should create a transfer."""
        start = date.today()
        end = date.today() + timedelta(days=7)
        thing.type = "LEND_THING"
        thing.save()
        booking = self._make_booking(
            thing,
            user,
            user2,
            thing_type="LEND_THING",
            start_date=start,
            end_date=end,
        )

        accept_booking(booking)

        transfer = ThingTransfer.objects.get(thing=thing)
        assert transfer.from_user == user
        assert transfer.to_user == user2
        assert transfer.lent_date == start
        assert transfer.returned_date is None
        assert transfer.booking == booking

    @time_machine.travel(date(2026, 6, 15))
    def test_accept_gift_creates_transfer(self, user, user2, thing):
        """Accepting a gift booking should create a transfer with today's date.

        Time is frozen so the ``lent_date`` (set to "today" by the service) is
        asserted against a fixed date rather than a re-evaluated ``date.today()``
        that could tick over a midnight boundary mid-test.
        """
        booking = self._make_booking(thing, user, user2, thing_type="GIFT_THING")

        accept_booking(booking)

        transfer = ThingTransfer.objects.get(thing=thing)
        assert transfer.from_user == user
        assert transfer.to_user == user2
        assert transfer.lent_date == date(2026, 6, 15)
        assert transfer.returned_date is None

    def test_accept_twice_is_idempotent(self, user, user2, thing):
        """A second accept on an already-processed booking is a race-safe no-op:
        the service re-reads the locked row, sees it is no longer PENDING,
        returns None, and creates no duplicate ThingTransfer."""
        booking = self._make_booking(thing, user, user2, thing_type="GIFT_THING")

        first = accept_booking(booking)
        assert first is not None

        second = accept_booking(booking)
        assert second is None

        assert ThingTransfer.objects.filter(booking=booking, thing=thing).count() == 1


@pytest.mark.django_db
class TestCloseTransfersCommand:
    """Tests for close_transfers management command."""

    @time_machine.travel(date(2026, 6, 15))
    def test_close_ended_transfers(self, user, user2, thing):
        """Should close transfers for bookings that have ended.

        Frozen time pins the ``returned_date`` the command stamps (= today) to a
        fixed date for a deterministic assertion."""
        booking = BookingPeriod.objects.create(
            thing_code=thing,
            thing_type="LEND_THING",
            requester_code=user2,
            requester_email=user2.email,
            owner_code=user,
            start_date=date.today() - timedelta(days=7),
            end_date=date.today() - timedelta(days=1),
            status="ACCEPTED",
        )
        ThingTransfer.objects.create(
            thing=thing,
            from_user=user,
            to_user=user2,
            booking=booking,
            lent_date=date.today() - timedelta(days=7),
        )

        out = StringIO()
        call_command("close_transfers", stdout=out)

        transfer = ThingTransfer.objects.get(thing=thing)
        assert transfer.returned_date == date(2026, 6, 15)
        assert "Closed 1 transfers" in out.getvalue()

    def test_no_transfers_to_close(self):
        """Should report zero when no transfers to close."""
        out = StringIO()
        call_command("close_transfers", stdout=out)
        assert "Closed 0 transfers" in out.getvalue()

    def test_skip_active_bookings(self, user, user2, thing):
        """Should not close transfers for bookings still in progress."""
        booking = BookingPeriod.objects.create(
            thing_code=thing,
            thing_type="LEND_THING",
            requester_code=user2,
            requester_email=user2.email,
            owner_code=user,
            start_date=date.today() - timedelta(days=3),
            end_date=date.today() + timedelta(days=4),
            status="ACCEPTED",
        )
        ThingTransfer.objects.create(
            thing=thing,
            from_user=user,
            to_user=user2,
            booking=booking,
            lent_date=date.today() - timedelta(days=3),
        )

        out = StringIO()
        call_command("close_transfers", stdout=out)

        transfer = ThingTransfer.objects.get(thing=thing)
        assert transfer.returned_date is None
        assert "Closed 0 transfers" in out.getvalue()


@pytest.mark.django_db
class TestAutoClosedIsNotAConfirmedReturn:
    """`close_transfers` infers a return; it never witnesses one.

    The journey timeline is the product's most human surface — "this item has
    travelled to 4 homes" — and it used to print "Returned on {date}" for a hop
    that nobody confirmed: the command simply stamped today's date once the
    booking's end_date had passed. `auto_closed` is what lets the UI say "due
    back on" instead of narrating a handover that may not have happened.
    """

    def _overdue_transfer(self):
        owner = User.objects.create(code="ACOWN1", email="acowner@test.com", name="Owner")
        borrower = User.objects.create(code="ACBOR1", email="acbor@test.com", name="Borrower")
        thing = Thing.objects.create(
            code="ACTHN1", owner=owner, headline="Drill", type="LEND_THING"
        )
        booking = BookingPeriod.objects.create(
            thing_code=thing,
            thing_type="LEND_THING",
            requester_code=borrower,
            requester_email=borrower.email,
            owner_code=owner,
            start_date=date.today() - timedelta(days=10),
            end_date=date.today() - timedelta(days=1),
            status="ACCEPTED",
        )
        return ThingTransfer.objects.create(
            thing=thing,
            from_user=owner,
            to_user=borrower,
            booking=booking,
            lent_date=date.today() - timedelta(days=10),
        )

    def test_the_command_marks_what_it_closes_as_inferred(self):
        transfer = self._overdue_transfer()
        assert transfer.auto_closed is False

        call_command("close_transfers", stdout=StringIO())

        transfer.refresh_from_db()
        assert transfer.returned_date == date.today()
        # The flag is the whole point: the date is a guess and says so.
        assert transfer.auto_closed is True

    def test_a_transfer_closed_by_a_real_handover_stays_unflagged(self):
        transfer = self._overdue_transfer()
        transfer.returned_date = date.today() - timedelta(days=2)
        transfer.save(update_fields=["returned_date"])

        call_command("close_transfers", stdout=StringIO())

        transfer.refresh_from_db()
        # Already returned, so the command skips it — and it keeps reading as a
        # confirmed return rather than being retroactively downgraded.
        assert transfer.auto_closed is False
        assert transfer.returned_date == date.today() - timedelta(days=2)
