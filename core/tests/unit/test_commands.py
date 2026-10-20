"""
Unit tests for OIUEEI management commands.
"""

import contextlib
from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from datetime import timezone as dt_timezone
from io import StringIO
from unittest.mock import patch

import pytest
import time_machine
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from core.models import RSVP, Collection, Thing, User
from core.models.booking import BookingPeriod
from core.services import email_service, storage


@pytest.mark.django_db
class TestExpireBookingsCommand:
    """Tests for expire_bookings management command."""

    def _create_booking(self, hours_ago=0):
        owner = User.objects.create(email=f"lala{hours_ago}@your-domain.test")
        requester = User.objects.create(email=f"lili{hours_ago}@your-domain.test")
        thing = Thing.objects.create(owner=owner, headline="Thing")
        booking = BookingPeriod.objects.create(
            thing_code=thing,
            thing_type="GIFT_THING",
            requester_code=requester,
            requester_email=requester.email,
            owner_code=owner,
        )
        if hours_ago:
            booking.created = timezone.now() - timedelta(hours=hours_ago)
            booking.save(update_fields=["created"])
        return booking

    def test_expire_old_bookings(self):
        """Should expire bookings older than 72 hours."""
        old_booking = self._create_booking(hours_ago=73)
        new_booking = self._create_booking(hours_ago=0)

        out = StringIO()
        call_command("expire_bookings", stdout=out)

        old_booking.refresh_from_db()
        new_booking.refresh_from_db()
        assert old_booking.status == "EXPIRED"
        assert new_booking.status == "PENDING"
        assert "Expired 1 bookings" in out.getvalue()

    def test_no_bookings_to_expire(self):
        """Should report zero when no bookings to expire."""
        out = StringIO()
        call_command("expire_bookings", stdout=out)
        assert "Expired 0 bookings" in out.getvalue()


@pytest.mark.django_db
class TestCleanupRsvpsCommand:
    """Tests for cleanup_rsvps management command."""

    def _create_rsvp(self, hours_ago=0, action=RSVP.Action.MAGIC_LINK):
        user = User.objects.create(email=f"lele{hours_ago}{action}@your-domain.test")
        rsvp = RSVP.objects.create(user_code=user, user_email=user.email, action=action)
        if hours_ago:
            rsvp.created = timezone.now() - timedelta(hours=hours_ago)
            rsvp.save(update_fields=["created"])
        return rsvp

    def test_cleanup_expired_rsvps(self):
        """Should delete magic-link RSVPs older than 24 hours."""
        old_rsvp = self._create_rsvp(hours_ago=25)
        new_rsvp = self._create_rsvp(hours_ago=0)

        out = StringIO()
        call_command("cleanup_rsvps", stdout=out)

        assert not RSVP.objects.filter(code=old_rsvp.code).exists()
        assert RSVP.objects.filter(code=new_rsvp.code).exists()
        assert "Cleaned up 1 expired RSVPs" in out.getvalue()

    def test_cleanup_keeps_booking_link_within_72h(self):
        """A booking link at 25h is past the old flat cutoff but still valid (72h)."""
        booking_rsvp = self._create_rsvp(hours_ago=25, action=RSVP.Action.BOOKING_ACCEPT)
        call_command("cleanup_rsvps", stdout=StringIO())
        assert RSVP.objects.filter(code=booking_rsvp.code).exists()

    def test_cleanup_deletes_booking_link_past_72h(self):
        """A booking link past 72h is expired and swept."""
        booking_rsvp = self._create_rsvp(hours_ago=73, action=RSVP.Action.BOOKING_ACCEPT)
        call_command("cleanup_rsvps", stdout=StringIO())
        assert not RSVP.objects.filter(code=booking_rsvp.code).exists()

    def test_cleanup_keeps_invite_within_30_days(self):
        """A pending invitation at 48h is no longer deleted a day after sending."""
        invite_rsvp = self._create_rsvp(hours_ago=48, action=RSVP.Action.COLLECTION_INVITE)
        call_command("cleanup_rsvps", stdout=StringIO())
        assert RSVP.objects.filter(code=invite_rsvp.code).exists()

    def test_no_rsvps_to_cleanup(self):
        """Should report zero when no RSVPs to clean up."""
        out = StringIO()
        call_command("cleanup_rsvps", stdout=out)
        assert "Cleaned up 0 expired RSVPs" in out.getvalue()


@pytest.mark.django_db
class TestSendRemindersCommand:
    """Tests for send_reminders management command."""

    def test_return_reminder_reaches_both_sides(self):
        """Both parties are reminded a loan ends tomorrow — each in their own words.

        The borrower's half is the one that was missing: only the owner was ever
        told, so the person who actually has to carry the drill back heard
        nothing. A lending library runs on that message, and the reminder is
        pointless without it.
        """
        tomorrow = date.today() + timedelta(days=1)
        owner = User.objects.create(code="RMOWN1", email="lala@your-domain.test", name="Owner")
        requester = User.objects.create(
            code="RMREQ1", email="lili@your-domain.test", name="Requester"
        )
        thing = Thing.objects.create(
            code="RMTHN1", owner=owner, headline="Drill", type="LEND_THING"
        )
        BookingPeriod.objects.create(
            thing_code=thing,
            thing_type="LEND_THING",
            requester_code=requester,
            requester_email=requester.email,
            owner_code=owner,
            start_date=date.today(),
            end_date=tomorrow,
            status="ACCEPTED",
        )

        out = StringIO()
        call_command("send_reminders", stdout=out)

        assert len(mail.outbox) == 2
        by_recipient = {m.to[0]: m for m in mail.outbox}
        assert set(by_recipient) == {"lala@your-domain.test", "lili@your-domain.test"}

        # The owner is told somebody's hold is ending; nothing is asked of them.
        to_owner = by_recipient["lala@your-domain.test"]
        assert "comes back tomorrow" in to_owner.subject
        assert "Requester" in to_owner.body

        # The borrower is told what they must do, and who they owe it to.
        to_borrower = by_recipient["lili@your-domain.test"]
        assert "Drill" in to_borrower.subject
        assert "return" in to_borrower.body.lower()
        assert "Owner" in to_borrower.body
        assert "Sent 2 reminder" in out.getvalue()

        # Both halves show the date DD/MM/YYYY (like the SPA), never ISO.
        assert tomorrow.strftime("%d/%m/%Y") in to_owner.body
        assert tomorrow.strftime("%d/%m/%Y") in to_borrower.body
        assert tomorrow.isoformat() not in to_owner.body

    def test_a_failing_recipient_does_not_cost_the_other_their_reminder(self, monkeypatch):
        """One broken send must not silence the other half of the same loan."""
        tomorrow = date.today() + timedelta(days=1)
        owner = User.objects.create(code="RMOWN2", email="lala1@your-domain.test", name="Owner")
        requester = User.objects.create(
            code="RMREQ2", email="lili1@your-domain.test", name="Requester"
        )
        thing = Thing.objects.create(
            code="RMTHN2", owner=owner, headline="Ladder", type="LEND_THING"
        )
        BookingPeriod.objects.create(
            thing_code=thing,
            thing_type="LEND_THING",
            requester_code=requester,
            requester_email=requester.email,
            owner_code=owner,
            start_date=date.today(),
            end_date=tomorrow,
            status="ACCEPTED",
        )

        def boom(**kwargs):
            raise RuntimeError("SMTP down")

        monkeypatch.setattr(
            "core.management.commands.send_reminders.send_return_reminder_email", boom
        )

        out = StringIO()
        err = StringIO()
        call_command("send_reminders", stdout=out, stderr=err)

        # The borrower still got theirs.
        assert [m.to[0] for m in mail.outbox] == ["lili1@your-domain.test"]
        assert "Sent 1 reminder" in out.getvalue()
        assert "Reminder failed" in err.getvalue()

    def test_a_reservation_starting_tomorrow_reminds_the_member(self):
        """An on-site reservation auto-confirms weeks ahead; this is the only nudge.

        The return reminder is nonsense for RESERVE (nothing is carried), so the
        member would otherwise hear nothing between the confirmation and the day
        — and a no-show costs a real slot.
        """
        tomorrow = date.today() + timedelta(days=1)
        owner = User.objects.create(
            code="RSVOW1", email="lala3@your-domain.test", name="Space owner"
        )
        member = User.objects.create(code="RSVME1", email="lele@your-domain.test", name="Member")
        thing = Thing.objects.create(
            code="RSVTH1",
            owner=owner,
            headline="Sala polivalent",
            type="RESERVE_THING",
            location="Planta 1",
        )
        BookingPeriod.objects.create(
            thing_code=thing,
            thing_type="RESERVE_THING",
            requester_code=member,
            requester_email=member.email,
            owner_code=owner,
            start_date=tomorrow,
            end_date=tomorrow + timedelta(days=1),
            status="ACCEPTED",
        )

        out = StringIO()
        call_command("send_reminders", stdout=out)

        # Only the member — nobody has to "take it back", so the owner is not pinged.
        assert [m.to[0] for m in mail.outbox] == ["lele@your-domain.test"]
        msg = mail.outbox[0]
        assert "Sala polivalent" in msg.subject
        assert "tomorrow" in msg.subject.lower()
        assert tomorrow.strftime("%d/%m/%Y") in msg.body
        assert "Sent 1 reminder" in out.getvalue()

    def test_a_reservation_further_out_is_left_alone(self):
        """Only start_date == tomorrow is due; a reservation in three days is not."""
        owner = User.objects.create(code="RSVOW2", email="lala4@your-domain.test")
        member = User.objects.create(code="RSVME2", email="lele1@your-domain.test")
        thing = Thing.objects.create(
            code="RSVTH2", owner=owner, headline="Torn", type="RESERVE_THING"
        )
        BookingPeriod.objects.create(
            thing_code=thing,
            thing_type="RESERVE_THING",
            requester_code=member,
            requester_email=member.email,
            owner_code=owner,
            start_date=date.today() + timedelta(days=3),
            end_date=date.today() + timedelta(days=4),
            status="ACCEPTED",
        )

        out = StringIO()
        call_command("send_reminders", stdout=out)

        assert len(mail.outbox) == 0
        assert "Sent 0 reminder" in out.getvalue()

    def test_a_cancelled_reservation_starting_tomorrow_is_not_nudged(self):
        """A member who cancelled must not get "your reservation starts tomorrow".

        Cancelling leaves `start_date` where it was and only flips `status`, so
        the arrival query has to filter on ACCEPTED — without that filter a
        cancelled (or otherwise settled) slot still mails the person who is not
        coming.
        """
        tomorrow = date.today() + timedelta(days=1)
        owner = User.objects.create(code="RSVOW4", email="lala6@your-domain.test")
        member = User.objects.create(code="RSVME4", email="lele2@your-domain.test")
        thing = Thing.objects.create(
            code="RSVTH4", owner=owner, headline="Sala", type="RESERVE_THING"
        )
        BookingPeriod.objects.create(
            thing_code=thing,
            thing_type="RESERVE_THING",
            requester_code=member,
            requester_email=member.email,
            owner_code=owner,
            start_date=tomorrow,
            end_date=tomorrow + timedelta(days=1),
            status="CANCELLED",
        )

        out = StringIO()
        call_command("send_reminders", stdout=out)

        assert mail.outbox == []
        assert "Sent 0 reminder" in out.getvalue()

    def test_a_reservation_ending_tomorrow_gets_no_return_reminder(self):
        """RESERVE is carried nowhere, so "take it back tomorrow" must never fire."""
        tomorrow = date.today() + timedelta(days=1)
        owner = User.objects.create(code="RSVOW3", email="lala7@your-domain.test")
        member = User.objects.create(code="RSVME3", email="lele3@your-domain.test")
        thing = Thing.objects.create(
            code="RSVTH3", owner=owner, headline="Sala", type="RESERVE_THING"
        )
        BookingPeriod.objects.create(
            thing_code=thing,
            thing_type="RESERVE_THING",
            requester_code=member,
            requester_email=member.email,
            owner_code=owner,
            start_date=date.today() - timedelta(days=1),
            end_date=tomorrow,
            status="ACCEPTED",
        )

        out = StringIO()
        call_command("send_reminders", stdout=out)

        assert len(mail.outbox) == 0
        assert "Sent 0 reminder" in out.getvalue()

    def test_no_reminders(self):
        """Should report zero when nothing is due tomorrow."""
        out = StringIO()
        call_command("send_reminders", stdout=out)
        assert "Sent 0 reminder" in out.getvalue()

    def test_skips_non_accepted_bookings(self):
        """Should not send reminders for PENDING or REJECTED bookings."""
        tomorrow = date.today() + timedelta(days=1)
        owner = User.objects.create(code="RMOWN4", email="lala8@your-domain.test")
        requester = User.objects.create(code="RMREQ4", email="lili2@your-domain.test")
        thing = Thing.objects.create(code="RMTHN4", owner=owner, headline="X", type="LEND_THING")
        BookingPeriod.objects.create(
            thing_code=thing,
            thing_type="LEND_THING",
            requester_code=requester,
            requester_email=requester.email,
            owner_code=owner,
            start_date=date.today(),
            end_date=tomorrow,
            status="PENDING",
        )

        out = StringIO()
        call_command("send_reminders", stdout=out)

        assert len(mail.outbox) == 0
        assert "Sent 0 reminder" in out.getvalue()

    def test_a_pending_booking_starting_tomorrow_gets_no_pickup_reminder(self):
        """A hold nobody has confirmed yet has no handover to remind about.

        The pickup block filters on ACCEPTED for the same reason the arrival
        one does: a PENDING loan's dates are still a request, and "tomorrow
        you pick up" about a day the owner may yet decline is a promise the
        app has no right to make.
        """
        tomorrow = date.today() + timedelta(days=1)
        owner = User.objects.create(code="RMOWN6", email="lala9@your-domain.test")
        requester = User.objects.create(code="RMREQ6", email="lili3@your-domain.test")
        thing = Thing.objects.create(
            code="RMTHN6", owner=owner, headline="Drill", type="LEND_THING"
        )
        BookingPeriod.objects.create(
            thing_code=thing,
            thing_type="LEND_THING",
            requester_code=requester,
            requester_email=requester.email,
            owner_code=owner,
            start_date=tomorrow,
            end_date=tomorrow + timedelta(days=2),
            status="PENDING",
        )

        out = StringIO()
        call_command("send_reminders", stdout=out)

        assert mail.outbox == []
        assert "Sent 0 reminder" in out.getvalue()

    def test_pickup_reminder_reaches_both_sides_in_their_own_language(self):
        """A loan starting tomorrow nudges both sides the day before the handover.

        Until now the only pickup email was the acceptance, sent when the dates
        were agreed — weeks can pass before the day, and nobody was told it had
        arrived. Each side gets their own words, in their own language: the
        borrower what they must do, the owner what is about to leave.
        """
        tomorrow = date.today() + timedelta(days=1)
        owner = User.objects.create(
            code="RMOWN7", email="lala10@your-domain.test", name="Owner", language="ca"
        )
        requester = User.objects.create(
            code="RMREQ7", email="lili4@your-domain.test", name="Requester", language="es"
        )
        thing = Thing.objects.create(
            code="RMTHN7", owner=owner, headline="Drill", type="LEND_THING"
        )
        BookingPeriod.objects.create(
            thing_code=thing,
            thing_type="LEND_THING",
            requester_code=requester,
            requester_email=requester.email,
            owner_code=owner,
            start_date=tomorrow,
            end_date=tomorrow + timedelta(days=3),
            status="ACCEPTED",
        )

        out = StringIO()
        call_command("send_reminders", stdout=out)

        assert len(mail.outbox) == 2
        by_recipient = {m.to[0]: m for m in mail.outbox}
        assert set(by_recipient) == {"lala10@your-domain.test", "lili4@your-domain.test"}

        # The borrower is told what they must do, and who they collect from —
        # in their own language, with the date DD/MM/YYYY like the SPA.
        to_borrower = by_recipient["lili4@your-domain.test"]
        assert to_borrower.subject == "Mañana recoges Drill"
        assert "recoges 'Drill' de Owner" in to_borrower.body
        assert tomorrow.strftime("%d/%m/%Y") in to_borrower.body
        assert tomorrow.isoformat() not in to_borrower.body

        # The owner is told who is coming for it — nothing is asked of them.
        to_owner = by_recipient["lala10@your-domain.test"]
        assert to_owner.subject == "Demà lliures Drill"
        assert "Requester recull 'Drill'" in to_owner.body
        assert "Sent 2 reminder" in out.getvalue()

    def test_a_reservation_starting_tomorrow_gets_no_pickup_reminders(self):
        """RESERVE has its own arrival reminder; the pickup pair is not for it.

        A reservation's "pickup" is the member turning up on the owner's
        premises — exactly what `send_reservation_reminder_email` already says,
        requester-only. The LEND/RENT pair would mail the owner a handover
        that never happens.
        """
        tomorrow = date.today() + timedelta(days=1)
        owner = User.objects.create(code="RSVOW5", email="lala11@your-domain.test")
        member = User.objects.create(code="RSVME5", email="lele5@your-domain.test")
        thing = Thing.objects.create(
            code="RSVTH5", owner=owner, headline="Sala", type="RESERVE_THING"
        )
        BookingPeriod.objects.create(
            thing_code=thing,
            thing_type="RESERVE_THING",
            requester_code=member,
            requester_email=member.email,
            owner_code=owner,
            start_date=tomorrow,
            end_date=tomorrow + timedelta(days=1),
            status="ACCEPTED",
        )

        out = StringIO()
        call_command("send_reminders", stdout=out)

        # One mail: the member's arrival reminder, and nothing to the owner.
        assert [m.to[0] for m in mail.outbox] == ["lele5@your-domain.test"]
        assert "Sala" in mail.outbox[0].subject
        assert "Sent 1 reminder" in out.getvalue()

    def test_a_single_day_loan_gets_one_reminder_per_person(self):
        """A loan out and back the same day says the day once, not twice.

        Its return day is its pickup day, so without the exclusion both blocks
        fire and each person is mailed twice about one day — the second mail
        answering a question the first already did.
        """
        tomorrow = date.today() + timedelta(days=1)
        owner = User.objects.create(code="RMOWN8", email="lala12@your-domain.test", name="Owner")
        requester = User.objects.create(
            code="RMREQ8", email="lili5@your-domain.test", name="Requester"
        )
        thing = Thing.objects.create(
            code="RMTHN8", owner=owner, headline="Drill", type="LEND_THING"
        )
        BookingPeriod.objects.create(
            thing_code=thing,
            thing_type="LEND_THING",
            requester_code=requester,
            requester_email=requester.email,
            owner_code=owner,
            start_date=tomorrow,
            end_date=tomorrow,
            status="ACCEPTED",
        )

        out = StringIO()
        call_command("send_reminders", stdout=out)

        # The pickup pair only — the day's one handover, said once per person.
        assert sorted(m.to[0] for m in mail.outbox) == [
            "lala12@your-domain.test",
            "lili5@your-domain.test",
        ]
        by_recipient = {m.to[0]: m for m in mail.outbox}
        assert "pick up" in by_recipient["lili5@your-domain.test"].subject
        assert "hand over" in by_recipient["lala12@your-domain.test"].subject
        assert "Sent 2 reminder" in out.getvalue()

    @pytest.mark.parametrize(
        "start_offset, end_offset",
        [(1, 3), (-3, 1)],
        ids=["pickup", "return"],
    )
    def test_the_borrower_never_reads_the_owners_address(self, start_offset, end_offset):
        """An owner who never set a name is "a member" to the borrower, not their email.

        ``display_name`` falls back to the address, and every account made by a magic
        link or an invitation has no name — so passing it put the owner's email in the
        borrower's pickup and return reminders, in the HTML and the plain text alike.
        """
        today = date.today()
        owner = User.objects.create(code="RMOWN9", email="lala13@your-domain.test")
        requester = User.objects.create(
            code="RMREQ9", email="lili6@your-domain.test", name="Requester"
        )
        thing = Thing.objects.create(
            code="RMTHN9", owner=owner, headline="Drill", type="LEND_THING"
        )
        BookingPeriod.objects.create(
            thing_code=thing,
            thing_type="LEND_THING",
            requester_code=requester,
            requester_email=requester.email,
            owner_code=owner,
            start_date=today + timedelta(days=start_offset),
            end_date=today + timedelta(days=end_offset),
            status="ACCEPTED",
        )

        call_command("send_reminders", stdout=StringIO())

        to_borrower = next(m for m in mail.outbox if m.to == ["lili6@your-domain.test"])
        html = to_borrower.alternatives[0][0]
        assert "lala13@your-domain.test" not in to_borrower.body
        assert "lala13@your-domain.test" not in html
        # In the middle of the sentence ("…to a member on…"), so lower case.
        assert "a member" in to_borrower.body

    @pytest.mark.parametrize(
        "start_offset, end_offset, subject",
        [(1, 3, "hand over"), (-3, 1, "comes back tomorrow")],
        ids=["pickup", "return"],
    )
    def test_the_whole_team_that_runs_the_thing_is_reminded(
        self, start_offset, end_offset, subject
    ):
        """In a PROPRIETARY collection the request went to every curator, so the
        handover and the return reach every curator too — not only whoever is
        recorded as the thing's owner. A curator who borrows is told once, as the
        borrower."""
        today = date.today()
        founder = User.objects.create(code="RMFND1", email="lala5@your-domain.test", name="Founder")
        cocurator = User.objects.create(code="RMCOC1", email="lala2@your-domain.test", name="Co")
        borrower = User.objects.create(code="RMBOR1", email="lili7@your-domain.test", name="Co2")
        collection = Collection.objects.create(
            code="RMCOL1", owner=founder, headline="Library", mode=Collection.Mode.PROPRIETARY
        )
        collection.invites.add(cocurator, borrower)
        collection.co_owners.add(cocurator, borrower)
        thing = Thing.objects.create(
            code="RMTHNA", owner=founder, headline="Drill", type="LEND_THING"
        )
        collection.things.add(thing)
        BookingPeriod.objects.create(
            thing_code=thing,
            thing_type="LEND_THING",
            requester_code=borrower,
            requester_email=borrower.email,
            owner_code=founder,
            start_date=today + timedelta(days=start_offset),
            end_date=today + timedelta(days=end_offset),
            status="ACCEPTED",
        )

        out = StringIO()
        call_command("send_reminders", stdout=out)

        team = sorted(m.to[0] for m in mail.outbox if subject in m.subject)
        assert team == ["lala2@your-domain.test", "lala5@your-domain.test"]
        assert [m.to[0] for m in mail.outbox].count("lili7@your-domain.test") == 1
        assert "Sent 3 reminder" in out.getvalue()

    @pytest.mark.parametrize(
        "start_offset, end_offset", [(1, 3), (-3, 1)], ids=["pickup", "return"]
    )
    def test_the_run_costs_the_same_queries_however_many_loans_are_due(
        self, start_offset, end_offset
    ):
        """Each loan's team is read from rows prefetched with the bookings, so a
        morning with six handovers in six groups asks the database what a morning
        with two does. The senders are stubbed: what they look up for their own
        email is theirs, and this counts what the command asks to know whom to tell."""
        today = date.today()

        def due_loans(count, start):
            for n in range(start, start + count):
                founder = User.objects.create(code=f"RQF{n:03d}", email=f"lala{n}@your-domain.test")
                cocurator = User.objects.create(
                    code=f"RQC{n:03d}", email=f"lele{n}@your-domain.test"
                )
                borrower = User.objects.create(
                    code=f"RQB{n:03d}", email=f"lili{n}@your-domain.test"
                )
                group = Collection.objects.create(
                    code=f"RQG{n:03d}",
                    owner=founder,
                    headline="Taller",
                    mode=Collection.Mode.PROPRIETARY,
                )
                group.invites.add(cocurator, borrower)
                group.co_owners.add(cocurator)
                thing = Thing.objects.create(
                    code=f"RQT{n:03d}", owner=founder, headline="Drill", type="LEND_THING"
                )
                group.things.add(thing)
                BookingPeriod.objects.create(
                    thing_code=thing,
                    thing_type="LEND_THING",
                    requester_code=borrower,
                    requester_email=borrower.email,
                    owner_code=founder,
                    start_date=today + timedelta(days=start_offset),
                    end_date=today + timedelta(days=end_offset),
                    status="ACCEPTED",
                )

        module = "core.management.commands.send_reminders"
        senders = [
            "send_pickup_due_email",
            "send_pickup_reminder_email",
            "send_return_due_email",
            "send_return_reminder_email",
        ]

        def run():
            with contextlib.ExitStack() as stack:
                mocks = {n: stack.enter_context(patch(f"{module}.{n}")) for n in senders}
                with CaptureQueriesContext(connection) as queries:
                    call_command("send_reminders", stdout=StringIO())
            team = (
                "send_pickup_reminder_email" if start_offset > 0 else "send_return_reminder_email"
            )
            told = sorted(c.kwargs["owner_email"] for c in mocks[team].call_args_list)
            return len(queries), told

        due_loans(2, 0)
        small, told_small = run()
        due_loans(4, 2)
        big, told_big = run()

        # Not vacuous: every founder and every co-curator was told, in both runs.
        assert told_small == sorted(
            f"{who}{n}@your-domain.test" for who in ("lala", "lele") for n in range(2)
        )
        assert told_big == sorted(
            f"{who}{n}@your-domain.test" for who in ("lala", "lele") for n in range(6)
        )
        assert big == small, f"a query per loan: {small} for 2 due, {big} for 6"


@pytest.mark.django_db
class TestSendDigestsCommand:
    """Tests for send_digests management command."""

    def _setup_collection_with_things(
        self, code_prefix, frequency, thing_days_ago=3, anchor_date=None
    ):
        owner = User.objects.create(
            code=f"{code_prefix}O1", email=f"lala{code_prefix}@your-domain.test", name="Owner"
        )
        invitee = User.objects.create(
            code=f"{code_prefix}I1",
            email=f"lele{code_prefix}@your-domain.test",
            name="Invitee",
            notify_news=True,  # digest recipient must opt into Cat. 3 (default is now off)
        )
        collection = Collection.objects.create(
            code=f"{code_prefix}C1",
            owner=owner,
            headline=f"{code_prefix} Club",
            digest_frequency=frequency,
        )
        collection.invites.add(invitee)

        thing = Thing.objects.create(code=f"{code_prefix}T1", owner=owner, headline="New Widget")
        if anchor_date is not None:
            thing.created = datetime.combine(
                anchor_date - timedelta(days=thing_days_ago), time(12, 0), tzinfo=dt_timezone.utc
            )
        else:
            thing.created = timezone.now() - timedelta(days=thing_days_ago)
        thing.save(update_fields=["created"])
        collection.things.add(thing)

        return collection, owner, invitee

    @time_machine.travel(date(2026, 4, 20))  # 2026-04-20 is a Monday
    def test_weekly_digest_on_monday(self):
        """Should send weekly digest on Mondays."""
        monday = date(2026, 4, 20)
        self._setup_collection_with_things("DGW", "WEEKLY", thing_days_ago=3, anchor_date=monday)

        out = StringIO()
        call_command("send_digests", stdout=out)

        # The member and the founder: the whole team gets the summary.
        assert len(mail.outbox) == 2
        assert all("New Widget" in m.body for m in mail.outbox)
        assert {m.to[0] for m in mail.outbox} == {
            "leleDGW@your-domain.test",
            "lalaDGW@your-domain.test",
        }
        assert "Sent 2 digest" in out.getvalue()

    @time_machine.travel(date(2026, 4, 21))  # a Tuesday
    def test_weekly_digest_not_on_tuesday(self):
        """Should not send weekly digest on non-Mondays."""
        self._setup_collection_with_things("DGX", "WEEKLY", thing_days_ago=3)

        out = StringIO()
        call_command("send_digests", stdout=out)

        assert len(mail.outbox) == 0
        assert "Sent 0 digest" in out.getvalue()

    @time_machine.travel(date(2026, 5, 1))  # the 1st of the month
    def test_monthly_digest_on_first(self):
        """Should send monthly digest on the 1st of the month."""
        first = date(2026, 5, 1)
        self._setup_collection_with_things("DGM", "MONTHLY", thing_days_ago=15, anchor_date=first)

        out = StringIO()
        call_command("send_digests", stdout=out)

        assert len(mail.outbox) == 2
        assert "Sent 2 digest" in out.getvalue()

    @time_machine.travel(date(2026, 4, 20))  # a Monday
    def test_skips_none_frequency(self):
        """Should not send digests for collections with NONE frequency."""
        self._setup_collection_with_things("DGN", "NONE", thing_days_ago=3)

        out = StringIO()
        call_command("send_digests", stdout=out)

        assert len(mail.outbox) == 0

    @time_machine.travel(date(2026, 4, 20))  # a Monday
    def test_skips_when_no_new_things(self):
        """Should not send digest when no new things in the period."""
        monday = date(2026, 4, 20)
        # Thing created 30 days ago — outside the weekly window
        self._setup_collection_with_things("DGO", "WEEKLY", thing_days_ago=30, anchor_date=monday)

        out = StringIO()
        call_command("send_digests", stdout=out)

        assert len(mail.outbox) == 0

    @time_machine.travel(date(2026, 4, 20))  # a Monday
    def test_a_collection_with_nobody_to_tell_is_skipped(self):
        """New things but no members: the digest has an audience of nobody.

        Worth its own case because the emptiness is on the *recipient* side —
        the things query matched, so this is a different `continue` from the one
        above, and getting it wrong means composing a digest for zero addresses.
        """
        monday = date(2026, 4, 20)
        collection, _, invitee = self._setup_collection_with_things(
            "DGE", "WEEKLY", thing_days_ago=3, anchor_date=monday
        )
        collection.invites.remove(invitee)

        out = StringIO()
        call_command("send_digests", stdout=out)

        assert mail.outbox == []
        assert "Sent 0 digest" in out.getvalue()

    @time_machine.travel(date(2026, 4, 20))  # a Monday
    def test_one_collection_failing_does_not_cost_the_rest_their_digest(self):
        """This runs nightly on the scheduler, unattended, for every collection
        at once. One group whose send raises must not take the whole run down
        with it — the others would silently lose a week and nobody would look
        until somebody complained.
        """
        monday = date(2026, 4, 20)
        self._setup_collection_with_things("DGA", "WEEKLY", thing_days_ago=3, anchor_date=monday)
        self._setup_collection_with_things("DGB", "WEEKLY", thing_days_ago=3, anchor_date=monday)

        real = email_service.send_digest_email
        calls = []

        def one_bad_apple(**kwargs):
            calls.append(kwargs["collection_code"])
            if len(calls) == 1:
                raise RuntimeError("template blew up")
            return real(**kwargs)

        out, err = StringIO(), StringIO()
        with patch(
            "core.management.commands.send_digests.send_digest_email", side_effect=one_bad_apple
        ):
            call_command("send_digests", stdout=out, stderr=err)

        assert len(calls) == 2, "the run carried on to the second collection"
        # The healthy collection still got its digest: its member and its founder.
        assert len(mail.outbox) == 2
        # The failure is reported, not swallowed: an operator reading the
        # scheduler log has to be able to see which collection went wrong.
        assert calls[0] in err.getvalue()
        # And it is not counted as delivered.
        assert "Sent 2 digest" in out.getvalue()

    @time_machine.travel(date(2026, 4, 20))  # a Monday
    def test_the_founder_gets_it_too(self):
        monday = date(2026, 4, 20)
        _, owner, _ = self._setup_collection_with_things(
            "DGF", "WEEKLY", thing_days_ago=3, anchor_date=monday
        )

        call_command("send_digests", stdout=StringIO())

        assert owner.email in [m.to[0] for m in mail.outbox]

    @time_machine.travel(date(2026, 4, 20))  # a Monday
    def test_a_co_curator_still_gets_it_once(self):
        """Co-curators are in `invites`, the founder is added to them: nobody
        twice."""
        monday = date(2026, 4, 20)
        collection, owner, invitee = self._setup_collection_with_things(
            "DGG", "WEEKLY", thing_days_ago=3, anchor_date=monday
        )
        collection.co_owners.add(invitee)

        out = StringIO()
        call_command("send_digests", stdout=out)

        recipients = [m.to[0] for m in mail.outbox]
        assert sorted(recipients) == sorted([invitee.email, owner.email])
        assert "Sent 2 digest" in out.getvalue()

    @time_machine.travel(date(2026, 4, 20))  # a Monday
    def test_a_founder_who_muted_the_group_does_not_get_it(self):
        monday = date(2026, 4, 20)
        collection, owner, invitee = self._setup_collection_with_things(
            "DGH", "WEEKLY", thing_days_ago=3, anchor_date=monday
        )
        collection.digest_muted.add(owner)

        call_command("send_digests", stdout=StringIO())

        assert [m.to[0] for m in mail.outbox] == [invitee.email]

    @time_machine.travel(date(2026, 4, 20))  # a Monday
    def test_a_founder_who_opted_out_of_news_does_not_get_it(self):
        monday = date(2026, 4, 20)
        _, owner, invitee = self._setup_collection_with_things(
            "DGJ", "WEEKLY", thing_days_ago=3, anchor_date=monday
        )
        User.objects.filter(pk=owner.pk).update(notify_news=False)

        call_command("send_digests", stdout=StringIO())

        assert [m.to[0] for m in mail.outbox] == [invitee.email]

    @time_machine.travel(date(2026, 4, 20))  # a Monday
    def test_the_founders_footer_link_mutes_the_group_for_them_and_the_next_digest_skips_them(
        self,
    ):
        """The link at the foot of the digest is built for the founder like for anyone,
        and following it takes them out of the next one."""
        import re

        from rest_framework.test import APIClient

        monday = date(2026, 4, 20)
        collection, owner, invitee = self._setup_collection_with_things(
            "DGK", "WEEKLY", thing_days_ago=3, anchor_date=monday
        )
        call_command("send_digests", stdout=StringIO())
        founders = next(m for m in mail.outbox if m.to[0] == owner.email)
        token = re.search(r"/digest/mute/([^\s\"<>)]+)", founders.body).group(1)

        res = APIClient().post(f"/api/v1/digest/mute/{token}/")

        assert res.status_code == 200
        assert collection.digest_muted.filter(pk=owner.pk).exists()
        mail.outbox.clear()
        call_command("send_digests", stdout=StringIO())
        assert [m.to[0] for m in mail.outbox] == [invitee.email]


@pytest.mark.django_db
class TestTheDigestSaysHowManyJoined:
    """One line, after the new things: how many people joined in the same window and
    are still in the group. A number, never a name; nothing when there are none."""

    MONDAY = date(2026, 4, 20)

    @pytest.fixture
    def group(self):
        owner = User.objects.create(code="DJO001", email="lala@your-domain.test", name="Lala")
        collection = Collection.objects.create(
            code="DJC001", owner=owner, headline="The street", digest_frequency="WEEKLY"
        )
        thing = Thing.objects.create(code="DJT001", owner=owner, headline="New Widget")
        thing.created = datetime.combine(
            self.MONDAY - timedelta(days=3), time(12, 0), tzinfo=dt_timezone.utc
        )
        thing.save(update_fields=["created"])
        collection.things.add(thing)
        reader = User.objects.create(code="DJR001", email="lele@your-domain.test", name="Lele")
        collection.invites.add(reader)
        return collection

    def _join(self, collection, n, days_ago=2, stay=True):
        from core.models.event import Event

        people = []
        for i in range(n):
            person = User.objects.create(
                code=f"DJN{days_ago}{i}{int(stay)}",
                email=f"lili{days_ago}{i}{int(stay)}@your-domain.test",
                name=f"Newcomer{days_ago}{i}{int(stay)}",
            )
            Event.log(
                Event.Kind.MEMBER_JOINED,
                actor=person,
                collection=collection,
                created=datetime.combine(
                    self.MONDAY - timedelta(days=days_ago), time(10, 0), tzinfo=dt_timezone.utc
                ),
            )
            if stay:
                collection.invites.add(person)
            people.append(person)
        return people

    def _run(self):
        mail.outbox.clear()
        with time_machine.travel(self.MONDAY):
            call_command("send_digests", stdout=StringIO())
        return next(m for m in mail.outbox if m.to[0] == "lele@your-domain.test")

    def _html(self, message):
        return message.alternatives[0][0]

    def test_three_joined_this_week_the_line_says_3_in_both_formats(self, group):
        self._join(group, 3)

        message = self._run()

        assert "And 3 new people joined the group." in message.body
        assert "And 3 new people joined the group." in self._html(message)

    def test_one_is_said_in_the_singular(self, group):
        self._join(group, 1)

        assert "And 1 new person joined the group." in self._run().body

    def test_the_line_comes_after_the_list_and_before_the_button(self, group):
        self._join(group, 2)

        body = self._run().body
        assert (
            body.index("New Widget")
            < body.index("And 2 new people joined")
            < body.index("View collection")
        )
        html = self._html(self._run())
        assert (
            html.index("New Widget") < html.index("And 2 new people joined") < html.index("View ")
        )

    def test_with_nobody_new_there_is_no_line_at_all(self, group):
        message = self._run()

        assert "joined the group" not in message.body
        assert "joined the group" not in self._html(message)

    def test_a_join_from_before_the_window_does_not_count(self, group):
        self._join(group, 2, days_ago=9)

        assert "joined the group" not in self._run().body

    def test_someone_who_joined_and_left_is_not_counted_or_mentioned(self, group):
        self._join(group, 2, stay=True)
        self._join(group, 4, stay=False)

        body = self._run().body

        assert "And 2 new people joined the group." in body
        assert "And 4 " not in body and "And 6 " not in body

    def test_a_week_of_only_departures_says_nothing(self, group):
        self._join(group, 3, stay=False)

        assert "joined the group" not in self._run().body

    def test_no_name_or_address_of_a_newcomer_is_in_the_email(self, group):
        people = self._join(group, 3)

        message = self._run()

        for person in people:
            for text in (message.body, self._html(message)):
                assert person.name not in text
                assert person.email not in text

    def test_a_group_with_no_new_things_still_sends_nothing(self, group):
        group.things.all().delete()
        self._join(group, 3)

        with time_machine.travel(self.MONDAY):
            mail.outbox.clear()
            call_command("send_digests", stdout=StringIO())

        assert mail.outbox == []

    @pytest.mark.parametrize(
        ("language", "sentence"),
        [
            ("es", "Y 3 personas nuevas se han sumado al grupo."),
            ("ca", "I 3 persones noves s'han sumat al grup."),
            ("en", "And 3 new people joined the group."),
        ],
    )
    def test_it_speaks_the_readers_language(self, group, language, sentence):
        User.objects.filter(code="DJR001").update(language=language)
        self._join(group, 3)

        assert sentence in self._run().body

    def test_the_count_costs_one_event_query_for_the_collection_not_one_per_reader(self, group):
        self._join(group, 3)
        for i in range(4):
            group.invites.add(
                User.objects.create(code=f"DJX00{i}", email=f"lolo{i}@your-domain.test")
            )

        with time_machine.travel(self.MONDAY), CaptureQueriesContext(connection) as queries:
            call_command("send_digests", stdout=StringIO())

        assert sum('FROM "events"' in q["sql"] for q in queries) == 1


@pytest.mark.django_db
class TestSeedDemoCommand:
    """Tests for the seed_demo management command (demo data integrity)."""

    SUCCULENTS = {"l0l001", "l0l002", "l0l003", "l0l004", "l0l005", "l0l006", "l0l007"}

    def test_maps_gallery_key(self):
        """Regression guard: _seed_things must copy the `gallery` key onto the model
        (image ids are stored under the SEED_IMAGE_FOLDER storage prefix)."""
        call_command("seed_demo")
        assert Thing.objects.get(code="La1a01").gallery == ["oiueei/seed/La1a01_b"]

    def test_maps_tags_key(self):
        """Regression guard: _seed_collections and _seed_things must copy `tags`.

        Tag labels are localized {lang: text} maps now — the stored value
        is the serialized constant from seed_data/common.py, byte-identical
        between the vocabulary and the thing that wears it."""
        from core.management.commands.seed_data.common import TAG_CRIANZA, TAG_JARDIN

        call_command("seed_demo")
        assert TAG_JARDIN in Collection.objects.get(code="l1l1C1").tags
        assert Thing.objects.get(code="l1l101").tags == [TAG_CRIANZA]

    def test_maps_user_photo_key(self):
        """Regression guard: _seed_users must copy the `photo` key onto the user
        (image ids are stored under the SEED_IMAGE_FOLDER storage prefix)."""
        call_command("seed_demo")
        assert User.objects.get(code="La1aN1").photo == "oiueei/seed/La1aPH"

    def test_maps_allowed_thing_types_key(self):
        """Regression guard: _seed_collections must copy `allowed_thing_types`."""
        call_command("seed_demo")
        assert Collection.objects.get(code="l1l1C1").allowed_thing_types == [
            "LEND_THING",
            "RENT_THING",
        ]

    def test_every_demo_collection_has_its_kind_and_holds_only_that_kinds_things(self):
        """A collection holds one kind of thing, and a thing's verb follows its price:
        the gift and the loan are free, the sale and the rental carry a price."""
        from core.models.collection import KIND_THING_TYPES, derive_thing_type

        call_command("seed_demo")

        kinds = dict(Collection.objects.filter(is_onboarding=True).values_list("code", "kind"))
        assert kinds == {
            "La1aC1": "STALL",
            "l0l0C1": "STALL",
            "l1l1C1": "LIBRARY",
            "1u1uC1": "LIBRARY",
            "L3L3C1": "STALL",
            "1u1uRe": "SHED",
        }
        for collection in Collection.objects.filter(is_onboarding=True):
            assert set(collection.allowed_thing_types) <= set(KIND_THING_TYPES[collection.kind])
            for thing in collection.things.all():
                assert thing.type in KIND_THING_TYPES[collection.kind], thing.code
                if collection.kind != "SHED":
                    assert thing.type == derive_thing_type(collection.kind, thing.fee), thing.code

    def test_a_community_demo_that_never_took_prices_keeps_only_its_free_verb(self):
        call_command("seed_demo")

        assert Collection.objects.get(code="1u1uC1").allowed_thing_types == ["LEND_THING"]
        assert Collection.objects.get(code="L3L3C1").allowed_thing_types == ["GIFT_THING"]

    def test_lolo_owns_succulent_collection(self):
        call_command("seed_demo")
        coll = Collection.objects.get(code="l0l0C1")
        assert coll.owner_id == "l0l0oh"
        codes = set(coll.things.values_list("code", flat=True))
        assert self.SUCCULENTS <= codes
        assert all(t.owner_id == "l0l0oh" for t in coll.things.filter(code__in=self.SUCCULENTS))
        invites = set(coll.invites.values_list("code", flat=True))
        assert "L3L3oo" in invites and "l0l0oh" not in invites

    def test_is_idempotent(self):
        call_command("seed_demo")
        counts = (User.objects.count(), Collection.objects.count(), Thing.objects.count())
        call_command("seed_demo")
        assert (User.objects.count(), Collection.objects.count(), Thing.objects.count()) == counts

    def test_skeleton_and_locales_stay_in_sync(self):
        """R17: every structural skeleton row has matching localised text in both
        languages — no untranslated skeleton row, no orphan text."""
        from core.management.commands.seed_demo import _MERGE_KEYS, load_seed_data

        en, es = load_seed_data("en"), load_seed_data("es")
        for entity, key in _MERGE_KEYS.items():
            en_rows, es_rows = getattr(en, entity), getattr(es, entity)
            assert len(en_rows) == len(es_rows) > 0
            assert {r[key] for r in en_rows} == {r[key] for r in es_rows}

    def test_merge_yields_structure_and_text(self):
        """Merged rows carry skeleton fields plus text. Thing text is
        now a localized map identical whatever --lang says (every reader gets
        their language from the same row); --lang still picks the plain-column
        text, so the FAQ question genuinely differs between languages."""
        from core.management.commands.seed_demo import load_seed_data
        from core.utils import resolve_localized

        en = load_seed_data("en")
        es = load_seed_data("es")
        sample = {t["code"]: t for t in en.THINGS}["La1a01"]
        assert sample["type"] == "SELL_THING" and sample["owner_code"] == "La1aN1"  # skeleton
        headline = sample["headline"]
        assert headline == {t["code"]: t for t in es.THINGS}["La1a01"]["headline"]  # same map
        assert resolve_localized(headline, "en") != resolve_localized(headline, "es")
        assert en.FAQS[0]["question"] != es.FAQS[0]["question"]  # --lang still matters


@pytest.mark.django_db
class TestAddTotpDeviceCommand:
    """Tests for the add_totp_device management command (admin 2FA bootstrap)."""

    def test_creates_confirmed_device_for_staff_user(self):
        from django_otp.plugins.otp_totp.models import TOTPDevice

        user = User.objects.create(email="lala15@your-domain.test", is_staff=True)
        out = StringIO()
        call_command("add_totp_device", "lala15@your-domain.test", stdout=out)

        device = TOTPDevice.objects.get(user=user)
        assert device.confirmed is True
        assert "otpauth://" in out.getvalue()

    def test_rejects_non_staff_user(self):
        from django.core.management.base import CommandError

        User.objects.create(email="lele4@your-domain.test", is_staff=False)
        with pytest.raises(CommandError):
            call_command("add_totp_device", "lele4@your-domain.test")

    def test_rejects_unknown_email(self):
        from django.core.management.base import CommandError

        with pytest.raises(CommandError):
            call_command("add_totp_device", "lolo9@your-domain.test")

    def test_refuses_to_duplicate_without_replace(self):
        from django.core.management.base import CommandError

        User.objects.create(email="lala15@your-domain.test", is_staff=True)
        call_command("add_totp_device", "lala15@your-domain.test")
        with pytest.raises(CommandError):
            call_command("add_totp_device", "lala15@your-domain.test")

    def test_replace_regenerates_the_device(self):
        from django_otp.plugins.otp_totp.models import TOTPDevice

        user = User.objects.create(email="lala15@your-domain.test", is_staff=True)
        call_command("add_totp_device", "lala15@your-domain.test")
        first_key = TOTPDevice.objects.get(user=user).key

        call_command("add_totp_device", "lala15@your-domain.test", "--replace")
        assert TOTPDevice.objects.filter(user=user).count() == 1
        assert TOTPDevice.objects.get(user=user).key != first_key


class TestSetBucketCorsCommand:
    """The command that writes the one piece of setup living on the bucket.

    Every test here is about a way the bucket can end up *looking* configured
    while uploads go on failing — which is the failure this command exists to
    end, and the only one that never shows up in a log.
    """

    BUCKET = {
        "OBJECT_STORAGE_ENDPOINT": "https://fsn1.example-storage.com",
        "OBJECT_STORAGE_BUCKET": "a-bucket",
        "OBJECT_STORAGE_REGION": "fsn1",
        "OBJECT_STORAGE_ACCESS_KEY": "key",
        "OBJECT_STORAGE_SECRET_KEY": "secret",
    }

    @pytest.fixture(autouse=True)
    def configured(self, settings):
        for name, value in self.BUCKET.items():
            setattr(settings, name, value)
        settings.CORS_ALLOWED_ORIGINS = []
        return settings

    @contextmanager
    def _bucket(self, existing=None):
        """A bucket holding ``existing`` rules, recording what gets written."""
        written = []

        def put(rules):
            written.clear()
            written.extend(rules)

        state = list(existing or [])

        with (
            patch.object(storage, "get_cors", side_effect=lambda: written or state),
            patch.object(storage, "put_cors", side_effect=put),
        ):
            yield written

    def _run(self, *args, **kwargs):
        out = StringIO()
        call_command("set_bucket_cors", *args, stdout=out, stderr=out, **kwargs)
        return out.getvalue()

    def test_it_writes_rules_for_the_origin_it_was_given(self):
        with self._bucket() as written:
            self._run("--origin", "https://www.your-domain.test")

        assert written == storage.cors_rules(["https://www.your-domain.test"])

    def test_it_falls_back_to_the_origins_this_deployment_already_declares(self, configured):
        """CORS_ALLOWED_ORIGINS is the list the API already had to get right."""
        configured.CORS_ALLOWED_ORIGINS = ["https://www.your-domain.test"]

        with self._bucket() as written:
            self._run()

        assert written[0]["AllowedOrigins"] == ["https://www.your-domain.test"]

    def test_with_no_origins_anywhere_it_refuses_rather_than_writing_an_empty_rule(self):
        """A rule allowing nobody is indistinguishable from a configured bucket."""
        with self._bucket() as written, pytest.raises(CommandError, match="No origins"):
            self._run()

        assert written == []

    def test_a_trailing_slash_is_normalised_away(self):
        """`https://x/` never equals the `Origin` a browser sends — it would match nothing.

        And it fails *silently*: the bucket now has rules, so it looks done.
        Pasting out of the address bar is how the slash gets there, so it is
        corrected rather than refused.
        """
        with self._bucket() as written:
            self._run("--origin", "https://www.your-domain.test/")

        assert written[0]["AllowedOrigins"] == ["https://www.your-domain.test"]

    def test_a_real_path_is_refused_because_cors_never_matches_one(self):
        with self._bucket(), pytest.raises(CommandError, match="no path"):
            self._run("--origin", "https://www.your-domain.test/media")

    def test_something_that_is_not_an_origin_is_refused(self):
        with self._bucket(), pytest.raises(CommandError, match="Not an origin"):
            self._run("--origin", "www.your-domain.test")

    def test_running_it_twice_writes_nothing_the_second_time(self):
        rules = storage.cors_rules(["https://www.your-domain.test"])

        with self._bucket(existing=rules):
            with patch.object(storage, "put_cors") as put:
                output = self._run("--origin", "https://www.your-domain.test")

        put.assert_not_called()
        assert "nothing to do" in output

    def test_a_store_that_lowercases_the_headers_is_still_the_same_rules(self):
        """Ceph answers with what it stored, not with what was sent.

        Comparing dicts would make this command rewrite identical rules forever
        and report a change every time.
        """
        stored = storage.cors_rules(["https://www.your-domain.test"])
        stored[0]["AllowedHeaders"] = [h.lower() for h in stored[0]["AllowedHeaders"]]
        stored[0]["ExposeHeaders"] = []

        with self._bucket(existing=stored):
            with patch.object(storage, "put_cors") as put:
                self._run("--origin", "https://www.your-domain.test")

        put.assert_not_called()

    def test_it_will_not_throw_away_rules_somebody_else_wrote(self):
        """A PutBucketCors replaces the whole configuration. On a shared bucket
        that silently revokes another application's permissions."""
        theirs = [{"AllowedOrigins": ["https://other.example"], "AllowedMethods": ["GET"]}]

        with self._bucket(existing=theirs) as written:
            with pytest.raises(CommandError, match="--replace"):
                self._run("--origin", "https://www.your-domain.test")

        assert written == []

    def test_replace_says_the_overwrite_was_meant(self):
        theirs = [{"AllowedOrigins": ["https://other.example"], "AllowedMethods": ["GET"]}]

        with self._bucket(existing=theirs) as written:
            self._run("--origin", "https://www.your-domain.test", "--replace")

        assert written[0]["AllowedOrigins"] == ["https://www.your-domain.test"]

    def test_show_reports_and_changes_nothing(self):
        rules = storage.cors_rules(["https://www.your-domain.test"])

        with self._bucket(existing=rules):
            with patch.object(storage, "put_cors") as put:
                output = self._run("--show")

        put.assert_not_called()
        assert "https://www.your-domain.test" in output

    def test_it_fails_loudly_when_the_store_did_not_keep_what_it_accepted(self):
        """Hetzner drops the Cache-Control of a POST policy without a word — the
        reason uploads are a PUT at all. A 200 is not evidence."""
        with (
            patch.object(storage, "get_cors", return_value=[]),
            patch.object(storage, "put_cors"),
            pytest.raises(CommandError, match="did not store them"),
        ):
            self._run("--origin", "https://www.your-domain.test")

    def test_an_unconfigured_checkout_says_which_setting_is_missing(self, configured):
        configured.OBJECT_STORAGE_BUCKET = ""

        with pytest.raises(CommandError, match="OBJECT_STORAGE_BUCKET"):
            self._run("--origin", "https://www.your-domain.test")
