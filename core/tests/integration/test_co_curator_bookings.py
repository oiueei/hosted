"""A PROPRIETARY collection's curators run its bookings and FAQs together.

Commit 3 of co-curators: `faq.py` and `booking.py` move from `thing.is_owner`
to `thing.can_manage`, so a co-curator answers questions and decides holds; and
a reservation notice fans out to **every** curator (owner + co-curators), deduped
and skipping whoever acted — CA's call, "avisos de reserva → a todos los curators".
COMMUNITY is unchanged.
"""

from datetime import date, timedelta

import pytest
from django.core import mail
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import FAQ, BookingPeriod, Collection, Thing, User
from core.models.notification import InAppNotification

pytestmark = pytest.mark.django_db


def client_for(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


def _next_weekday(weekday):
    d = date.today() + timedelta(days=1)
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d


@pytest.fixture
def owner(db):
    return User.objects.create(code="OWNR01", email="owner@test.com", name="Lala")


@pytest.fixture
def co_curator(db):
    return User.objects.create(code="COCU01", email="cocurator@test.com", name="Lele")


@pytest.fixture
def member(db):
    return User.objects.create(code="MEMB01", email="member@test.com", name="Lili")


@pytest.fixture
def space(db, owner, co_curator, member):
    coll = Collection.objects.create(
        code="RSVC01",
        owner=owner,
        headline="Ateneu spaces",
        mode=Collection.Mode.PROPRIETARY,
        allowed_thing_types=["RESERVE_THING"],
        reservation_max_days=3,
        rental_weekdays=[0, 1, 2, 3, 4],
    )
    coll.invites.add(co_curator, member)
    coll.co_owners.add(co_curator)
    thing = Thing.objects.create(
        code="RSVT01", type=Thing.Type.RESERVE_THING, owner=owner, headline="Sala polivalent"
    )
    coll.things.add(thing)
    return {"collection": coll, "thing": thing}


def _reserve(space, member, weekday=0):
    res = client_for(member).post(
        f"/api/v1/things/{space['thing'].code}/request/",
        {"start_date": str(_next_weekday(weekday)), "duration_days": 1},
        format="json",
    )
    assert res.status_code == 201, res.data
    return BookingPeriod.objects.get(code=res.data["booking_code"])


class TestReservationNoticesFanOutToEveryCurator:
    def test_both_the_founder_and_the_co_curator_are_notified(
        self, space, member, owner, co_curator
    ):
        mail.outbox.clear()
        _reserve(space, member)

        recipients = set(
            InAppNotification.objects.filter(
                type=InAppNotification.Type.RESERVATION_MADE
            ).values_list("user_id", flat=True)
        )
        assert recipients == {owner.code, co_curator.code}
        # one notice email per curator, plus the requester's confirmation
        assert {owner.email, co_curator.email, member.email} <= {m.to[0] for m in mail.outbox}

    def test_a_curator_who_reserves_the_space_is_not_notified_of_their_own(
        self, space, co_curator, owner
    ):
        mail.outbox.clear()
        _reserve(space, co_curator)  # a co-curator books the room for themselves

        notified = set(
            InAppNotification.objects.filter(
                type=InAppNotification.Type.RESERVATION_MADE
            ).values_list("user_id", flat=True)
        )
        assert notified == {owner.code}  # the founder, not the acting co-curator


class TestACoCuratorRunsTheBookings:
    def test_a_co_curator_cancels_a_reservation_on_the_founders_thing(
        self, space, member, owner, co_curator
    ):
        booking = _reserve(space, member)
        InAppNotification.objects.all().delete()
        mail.outbox.clear()

        res = client_for(co_curator).post(f"/api/v1/bookings/{booking.code}/cancel/")
        assert res.status_code == 200
        booking.refresh_from_db()
        assert booking.status == BookingPeriod.Status.CANCELLED

        # the member hears it; the founder (the other curator) hears it; the
        # co-curator who did it does not
        told = set(
            InAppNotification.objects.filter(
                type=InAppNotification.Type.RESERVATION_CANCELLED
            ).values_list("user_id", flat=True)
        )
        assert told == {member.code, owner.code}
        # `other_name` is whoever actually cancelled
        note = InAppNotification.objects.filter(user=member.code).first()
        assert note.payload["other_name"] == co_curator.name

    def test_owner_bookings_lists_the_spaces_reservations_for_a_co_curator(
        self, space, member, co_curator
    ):
        _reserve(space, member)
        res = client_for(co_curator).get("/api/v1/owner-bookings/")
        assert res.status_code == 200
        rows = res.data["results"]
        codes = [b["thing_code"] for b in rows]
        assert space["thing"].code in codes
        # Each row names the group it belongs to — a co-curator of more than one
        # group needs it to tell the rows apart (the page pools them all).
        row = next(b for b in rows if b["thing_code"] == space["thing"].code)
        assert row["collection_code"] == space["collection"].code
        assert row["collection_headline"] == "Ateneu spaces"

    def test_a_co_curator_answers_a_faq_on_the_founders_thing(self, space, member, co_curator):
        faq = FAQ.objects.create(
            thing=space["thing"], questioner=member, question="What are the hours?"
        )
        res = client_for(co_curator).post(
            f"/api/v1/faq/{faq.code}/answer/", {"answer": "Nine to nine."}, format="json"
        )
        assert res.status_code == 200
        faq.refresh_from_db()
        assert faq.answer == "Nine to nine."
        # the questioner is told, by whoever answered
        assert InAppNotification.objects.filter(
            user=member.code,
            type=InAppNotification.Type.FAQ_ANSWERED,
            payload__owner_name=co_curator.name,
        ).exists()

    def test_a_co_curator_cannot_ask_a_question_about_a_thing_they_run(self, space, co_curator):
        res = client_for(co_curator).post(
            f"/api/v1/things/{space['thing'].code}/faq/", {"question": "?"}, format="json"
        )
        assert res.status_code == 400

    def test_a_new_faq_question_notifies_every_curator(self, space, member, owner, co_curator):
        mail.outbox.clear()
        res = client_for(member).post(
            f"/api/v1/things/{space['thing'].code}/faq/",
            {"question": "Is there wifi?"},
            format="json",
        )
        assert res.status_code == 201

        told = set(
            InAppNotification.objects.filter(type=InAppNotification.Type.FAQ_QUESTION).values_list(
                "user_id", flat=True
            )
        )
        assert told == {owner.code, co_curator.code}
        assert {owner.email, co_curator.email} <= {m.to[0] for m in mail.outbox}

    def test_a_community_question_still_reaches_only_the_thing_owner(self, db):
        owner = User.objects.create(code="QOWN01", email="qowner@test.com", name="Owner")
        co_curator = User.objects.create(code="QCUR01", email="qcur@test.com", name="Curator")
        contributor = User.objects.create(code="QCON01", email="qcon@test.com", name="Member")
        asker = User.objects.create(code="QASK01", email="qask@test.com", name="Asker")
        group = Collection.objects.create(
            code="QCOM01", owner=owner, headline="Street", mode=Collection.Mode.COMMUNITY
        )
        group.invites.add(co_curator, contributor, asker)
        group.co_owners.add(co_curator)
        thing = Thing.objects.create(
            code="QTHG01", owner=contributor, headline="A tent", type="LEND_THING"
        )
        group.things.add(thing)

        res = client_for(asker).post(
            f"/api/v1/things/{thing.code}/faq/", {"question": "Waterproof?"}, format="json"
        )
        assert res.status_code == 201
        told = set(
            InAppNotification.objects.filter(type=InAppNotification.Type.FAQ_QUESTION).values_list(
                "user_id", flat=True
            )
        )
        assert told == {contributor.code}  # the thing's owner, not the group's curators


class TestACoCuratorDecidesHolds:
    def test_a_co_curator_accepts_a_hold_on_a_lend_thing(self, db):
        owner = User.objects.create(code="LOWN01", email="lowner@test.com", name="Owner")
        co_curator = User.objects.create(code="LCUR01", email="lcur@test.com", name="Curator")
        member = User.objects.create(code="LMEM01", email="lmem@test.com", name="Member")
        space = Collection.objects.create(
            code="LSPC01", owner=owner, headline="Tool room", mode=Collection.Mode.PROPRIETARY
        )
        space.invites.add(co_curator, member)
        space.co_owners.add(co_curator)
        thing = Thing.objects.create(
            code="LTHG01", owner=owner, headline="Drill", type="LEND_THING"
        )
        space.things.add(thing)

        req = client_for(member).post(
            f"/api/v1/things/{thing.code}/request/",
            {
                "start_date": str(date.today() + timedelta(days=3)),
                "end_date": str(date.today() + timedelta(days=5)),
            },
            format="json",
        )
        assert req.status_code == 201
        booking = BookingPeriod.objects.get(thing_code=thing)

        res = client_for(co_curator).post(f"/api/v1/bookings/{booking.code}/accept/")
        assert res.status_code == 200
        booking.refresh_from_db()
        assert booking.status == BookingPeriod.Status.ACCEPTED


class TestCommunityFaqsAreUnchanged:
    def test_a_community_co_curator_cannot_answer_a_faq_on_a_members_thing(self, db):
        owner = User.objects.create(code="COWN01", email="cowner@test.com", name="Owner")
        co_curator = User.objects.create(code="CCUR01", email="ccur@test.com", name="Curator")
        contributor = User.objects.create(code="CONT01", email="cont@test.com", name="Member")
        group = Collection.objects.create(
            code="COM001", owner=owner, headline="The street", mode=Collection.Mode.COMMUNITY
        )
        group.invites.add(co_curator, contributor)
        group.co_owners.add(co_curator)
        thing = Thing.objects.create(
            code="CTHG01", owner=contributor, headline="Ladder", type="LEND_THING"
        )
        group.things.add(thing)
        faq = FAQ.objects.create(thing=thing, questioner=owner, question="Height?")

        res = client_for(co_curator).post(
            f"/api/v1/faq/{faq.code}/answer/", {"answer": "Tall."}, format="json"
        )
        assert res.status_code == 403
        faq.refresh_from_db()
        assert faq.answer == ""
