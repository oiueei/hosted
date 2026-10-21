"""Who is emailed when a member's things leave the group with them.

Everybody with a live request or reservation on one of the deleted things hears it once
the deletion has committed; the person who holds the thing now is also reminded to give it
back. The removed member's own email lists the things that went with them. None of it may
leak the address of the member or the curator, and none of it is sent if the transaction
rolls back.
"""

import time
from datetime import date, timedelta

import pytest
import time_machine
from django.core import mail
from django.db import transaction
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import BookingPeriod, Collection, Thing, User
from core.services.membership_service import end_membership

LEAVE = "/api/v1/collections/{code}/leave/"
INVITE = "/api/v1/collections/{code}/invite/"


def client_for(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


@pytest.fixture
def founder(db):
    return User.objects.create(code="FOUN01", email="lala@your-domain.test", name="Lala")


@pytest.fixture
def member(db):
    return User.objects.create(code="MEMB01", email="lele@your-domain.test", name="Lele")


@pytest.fixture
def asker(db):
    return User.objects.create(
        code="ASKR01", email="lili@your-domain.test", name="Lili", language="en"
    )


@pytest.fixture
def borrower(db):
    return User.objects.create(
        code="BORR01", email="lolo@your-domain.test", name="Lolo", language="en"
    )


@pytest.fixture
def group(db, founder, member, asker, borrower):
    collection = Collection.objects.create(
        code="GRP001", owner=founder, headline="The street", mode=Collection.Mode.COMMUNITY
    )
    collection.invites.add(member, asker, borrower)
    return collection


def book(thing, requester, status=BookingPeriod.Status.PENDING, **dates):
    return BookingPeriod.objects.create(
        thing_code=thing,
        thing_type=thing.type,
        requester_code=requester,
        requester_email=requester.email,
        owner_code=thing.owner,
        status=status,
        **dates,
    )


def make_thing(group, owner, code, headline, type="GIFT_THING"):
    thing = Thing.objects.create(code=code, owner=owner, type=type, headline=headline)
    group.things.add(thing)
    return thing


def html_of(message):
    return message.alternatives[0][0]


@pytest.fixture
def leave(django_capture_on_commit_callbacks, member):
    def go(group):
        with django_capture_on_commit_callbacks(execute=True):
            return client_for(member).post(LEAVE.format(code=group.code), format="json")

    return go


class TestRequestersAreTold:
    def test_each_requester_gets_exactly_one_email_in_their_language(
        self, group, member, asker, borrower, leave
    ):
        drill = make_thing(group, member, "DRILL1", "Drill")
        book(drill, asker)
        book(drill, borrower)

        leave(group)

        assert sorted(m.to[0] for m in mail.outbox) == sorted([asker.email, borrower.email])
        assert all(m.subject == "“Drill” is no longer in The street" for m in mail.outbox)

    def test_only_the_one_who_has_it_now_is_told_to_give_it_back(
        self, group, member, asker, borrower, leave
    ):
        today = date.today()
        ladder = make_thing(group, member, "LADD01", "Ladder", type="LEND_THING")
        book(
            ladder,
            borrower,
            BookingPeriod.Status.ACCEPTED,
            start_date=today - timedelta(days=1),
            end_date=today + timedelta(days=3),
        )
        book(
            ladder,
            asker,
            BookingPeriod.Status.PENDING,
            start_date=today,
            end_date=today + timedelta(days=6),
        )

        leave(group)

        by_recipient = {m.to[0]: m.body for m in mail.outbox}
        assert "return it to them as you agreed" in by_recipient[borrower.email]
        assert "return it to them" not in by_recipient[asker.email]

    def test_a_loan_that_has_not_started_is_not_held_yet(self, group, member, borrower, leave):
        today = date.today()
        ladder = make_thing(group, member, "LADD01", "Ladder", type="LEND_THING")
        book(
            ladder,
            borrower,
            BookingPeriod.Status.ACCEPTED,
            start_date=today + timedelta(days=2),
            end_date=today + timedelta(days=3),
        )

        leave(group)

        assert "return it to them" not in mail.outbox[0].body

    def test_a_loan_starting_today_by_the_deployments_day_is_held(
        self, group, member, borrower, leave, settings, monkeypatch
    ):
        """23:30 UTC on the 21st is already the 22nd in Madrid: a loan that starts
        on the 22nd is in the borrower's hands by the deployment's calendar.

        Django points the process clock at TIME_ZONE, so ``date.today()`` and
        ``timezone.localdate()`` agree in a running app; the process zone is
        forced back to UTC here to stand in for any clock that differs from the
        deployment's day, which only the latter may judge by."""
        settings.TIME_ZONE = "Europe/Madrid"
        monkeypatch.setenv("TZ", "UTC")
        time.tzset()
        ladder = make_thing(group, member, "LADD01", "Ladder", type="LEND_THING")
        book(
            ladder,
            borrower,
            BookingPeriod.Status.ACCEPTED,
            start_date=date(2026, 10, 22),
            end_date=date(2026, 10, 25),
        )

        try:
            with time_machine.travel("2026-10-21 23:30:00+00:00", tick=False):
                leave(group)
        finally:
            monkeypatch.undo()
            time.tzset()

        assert "return it to them as you agreed" in mail.outbox[0].body

    def test_nobody_is_told_about_a_finished_or_rejected_request(
        self, group, member, asker, borrower, leave
    ):
        drill = make_thing(group, member, "DRILL1", "Drill")
        book(drill, asker, BookingPeriod.Status.REJECTED)
        book(drill, borrower, BookingPeriod.Status.CANCELLED)

        leave(group)

        assert mail.outbox == []

    def test_the_email_carries_neither_the_members_nor_the_curators_address(
        self, group, founder, member, asker, django_capture_on_commit_callbacks
    ):
        drill = make_thing(group, member, "DRILL1", "Drill")
        book(drill, asker)

        with django_capture_on_commit_callbacks(execute=True):
            client_for(founder).delete(
                INVITE.format(code=group.code), {"user_code": member.code}, format="json"
            )

        told = [m for m in mail.outbox if m.to == [asker.email]]
        assert len(told) == 1
        for address in (member.email, founder.email):
            assert address not in told[0].body
            assert address not in html_of(told[0])
            assert address not in str(told[0].extra_headers)
            assert address not in told[0].reply_to

    def test_a_title_with_markup_arrives_escaped(self, group, member, asker, leave):
        drill = make_thing(group, member, "DRILL1", "<b>Drill</b>")
        book(drill, asker)

        leave(group)

        html = html_of(mail.outbox[0])
        assert "&lt;b&gt;Drill&lt;/b&gt;" in html
        assert "<b>Drill</b>" not in html

    def test_a_title_in_several_languages_reads_in_the_recipients(
        self, group, member, asker, leave
    ):
        drill = make_thing(group, member, "DRILL1", '{"es": "Taladro", "en": "Drill"}')
        book(drill, asker)

        leave(group)

        assert mail.outbox[0].subject == "“Drill” is no longer in The street"

    def test_the_member_is_not_told_about_their_own_requests(self, group, member, leave):
        theirs = make_thing(group, member, "MINE01", "Mine")
        book(theirs, member)

        leave(group)

        assert mail.outbox == []

    def test_nothing_is_sent_when_the_transaction_rolls_back(
        self, group, member, asker, django_capture_on_commit_callbacks
    ):
        drill = make_thing(group, member, "DRILL1", "Drill")
        book(drill, asker)

        with django_capture_on_commit_callbacks(execute=True):
            with pytest.raises(RuntimeError):
                with transaction.atomic():
                    end_membership(group, member, actor=member)
                    raise RuntimeError("the rest of the request failed")

        assert mail.outbox == []
        assert Thing.objects.filter(code="DRILL1").exists()
        assert group.invites.filter(code=member.code).exists()

    def test_nothing_is_sent_before_the_commit(self, group, member, asker):
        drill = make_thing(group, member, "DRILL1", "Drill")
        book(drill, asker)

        end_membership(group, member, actor=member)

        assert mail.outbox == []


class TestTheRemovedMemberIsTold:
    def remove(self, group, founder, member, callbacks):
        with callbacks(execute=True):
            return client_for(founder).delete(
                INVITE.format(code=group.code), {"user_code": member.code}, format="json"
            )

    def test_their_revocation_email_lists_the_things_that_went(
        self, group, founder, member, django_capture_on_commit_callbacks
    ):
        make_thing(group, member, "DRILL1", "Drill")
        make_thing(group, member, "LADD01", "<i>Ladder</i>")

        self.remove(group, founder, member, django_capture_on_commit_callbacks)

        revoke = next(m for m in mail.outbox if m.to == [member.email])
        assert "deleted with your membership" in revoke.body
        assert "Drill, <i>Ladder</i>" in revoke.body
        assert "Drill, &lt;i&gt;Ladder&lt;/i&gt;" in html_of(revoke)

    def test_without_things_the_revocation_email_has_no_such_line(
        self, group, founder, member, django_capture_on_commit_callbacks
    ):
        self.remove(group, founder, member, django_capture_on_commit_callbacks)

        revoke = next(m for m in mail.outbox if m.to == [member.email])
        assert "deleted with your membership" not in revoke.body
        assert "deleted with your membership" not in html_of(revoke)
