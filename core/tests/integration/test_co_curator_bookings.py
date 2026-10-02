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

from core.models import FAQ, RSVP, BookingPeriod, Collection, Thing, ThingTransfer, User
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
        # co-curator who did it keeps a record of their own (CA, 2026-09-29)
        told = set(
            InAppNotification.objects.filter(
                type=InAppNotification.Type.RESERVATION_CANCELLED
            ).values_list("user_id", flat=True)
        )
        assert told == {member.code, owner.code, co_curator.code}
        # `other_name` is whoever actually cancelled
        note = InAppNotification.objects.filter(user=member.code).first()
        assert note.payload["other_name"] == co_curator.name
        # theirs is the first-person copy, naming whose reservation it was
        mine = InAppNotification.objects.get(user=co_curator.code)
        assert mine.payload["by_you"] is True
        assert mine.payload["member_name"] == member.name
        assert "by_you" not in note.payload

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


TEAM_ANSWER_SUBJECT = "A question about 'Sala polivalent' has been answered"


class TestAnAnswerSettlesTheQuestionForTheWholeTeam:
    """CA's production report (2026-09-28): a question warns EVERY manager, but
    the answer warned only the asker — so the co-curator's inbox kept a
    FAQ_QUESTION asking for a decision the founder had already made (and the
    other way round). One answer settles the question for the team: the others
    hear who answered, and the pending notice leaves every inbox."""

    def _ask(self, space, member):
        res = client_for(member).post(
            f"/api/v1/things/{space['thing'].code}/faq/",
            {"question": "Is there wifi?"},
            format="json",
        )
        assert res.status_code == 201
        mail.outbox.clear()
        return FAQ.objects.get(code=res.data["code"])

    def _team_emails(self):
        return [m for m in mail.outbox if m.subject == TEAM_ANSWER_SUBJECT]

    def test_the_founder_answering_tells_the_co_curator_once(
        self, space, member, owner, co_curator
    ):
        faq = self._ask(space, member)

        res = client_for(owner).post(
            f"/api/v1/faq/{faq.code}/answer/", {"answer": "Yes, fibre."}, format="json"
        )
        assert res.status_code == 200

        # One team email, to the co-curator only — not the answerer, not the asker.
        team = self._team_emails()
        assert [m.to[0] for m in team] == [co_curator.email]
        # The asker got their ordinary answer notice, nothing more.
        to_asker = [m.subject for m in mail.outbox if m.to[0] == member.email]
        assert to_asker == ["Your question has been answered"]
        assert owner.email not in {m.to[0] for m in mail.outbox}

    def test_the_co_curator_answering_tells_the_founder(self, space, member, owner, co_curator):
        faq = self._ask(space, member)

        res = client_for(co_curator).post(
            f"/api/v1/faq/{faq.code}/answer/", {"answer": "Yes, fibre."}, format="json"
        )
        assert res.status_code == 200

        assert [m.to[0] for m in self._team_emails()] == [owner.email]

    def test_answering_clears_the_pending_question_for_every_manager(
        self, space, member, owner, co_curator
    ):
        faq = self._ask(space, member)
        holders = set(
            InAppNotification.objects.filter(type=InAppNotification.Type.FAQ_QUESTION).values_list(
                "user_id", flat=True
            )
        )
        assert holders == {owner.code, co_curator.code}  # the premise of the bug

        res = client_for(owner).post(
            f"/api/v1/faq/{faq.code}/answer/", {"answer": "Yes."}, format="json"
        )
        assert res.status_code == 200

        assert not InAppNotification.objects.filter(
            type=InAppNotification.Type.FAQ_QUESTION
        ).exists()

    def test_a_community_answer_sends_no_team_email(self, db):
        # In COMMUNITY the managers of a thing are its owner alone, and they
        # answered — there is no team left to tell.
        contributor = User.objects.create(code="ACON01", email="acon@test.com", name="Member")
        asker = User.objects.create(code="AASK01", email="aask@test.com", name="Asker")
        group = Collection.objects.create(
            code="ACOM01", owner=asker, headline="Street", mode=Collection.Mode.COMMUNITY
        )
        thing = Thing.objects.create(
            code="ATHG01", owner=contributor, headline="A tent", type="LEND_THING"
        )
        group.things.add(thing)

        res = client_for(asker).post(
            f"/api/v1/things/{thing.code}/faq/", {"question": "Waterproof?"}, format="json"
        )
        assert res.status_code == 201
        faq = FAQ.objects.get(code=res.data["code"])
        mail.outbox.clear()

        res = client_for(contributor).post(
            f"/api/v1/faq/{faq.code}/answer/", {"answer": "Yes."}, format="json"
        )
        assert res.status_code == 200
        # The asker's ordinary answer notice, and nothing else.
        assert [m.to[0] for m in mail.outbox] == [asker.email]


TEAM_HIDE_SUBJECT = "A question about 'Sala polivalent' was hidden"


class TestHidingSettlesTheQuestionForTheWholeTeam:
    """The hide-side twin: retiring a question is as much a team decision as
    answering it. Without a notice the other managers never learn the question
    was withdrawn deliberately, and an unanswered one kept asking them for a
    reply nobody owed any more."""

    def _ask(self, space, member):
        res = client_for(member).post(
            f"/api/v1/things/{space['thing'].code}/faq/",
            {"question": "Is there wifi?"},
            format="json",
        )
        assert res.status_code == 201
        mail.outbox.clear()
        return FAQ.objects.get(code=res.data["code"])

    def _team_emails(self):
        return [m for m in mail.outbox if m.subject == TEAM_HIDE_SUBJECT]

    def test_the_founder_hiding_tells_the_co_curator_once(self, space, member, owner, co_curator):
        faq = self._ask(space, member)

        res = client_for(owner).post(f"/api/v1/faq/{faq.code}/hide/")
        assert res.status_code == 200

        # One team email, to the co-curator only — not the hider, not the asker.
        assert [m.to[0] for m in self._team_emails()] == [co_curator.email]
        # The asker got their ordinary hidden notice, nothing more.
        to_asker = [m.subject for m in mail.outbox if m.to[0] == member.email]
        assert to_asker == ["Your question has been hidden"]
        assert owner.email not in {m.to[0] for m in mail.outbox}

    def test_the_co_curator_hiding_tells_the_founder(self, space, member, owner, co_curator):
        faq = self._ask(space, member)

        res = client_for(co_curator).post(f"/api/v1/faq/{faq.code}/hide/")
        assert res.status_code == 200

        assert [m.to[0] for m in self._team_emails()] == [owner.email]

    def test_hiding_clears_the_pending_question_for_every_manager(
        self, space, member, owner, co_curator
    ):
        faq = self._ask(space, member)
        assert (
            InAppNotification.objects.filter(type=InAppNotification.Type.FAQ_QUESTION).count() == 2
        )

        res = client_for(owner).post(f"/api/v1/faq/{faq.code}/hide/")
        assert res.status_code == 200

        assert not InAppNotification.objects.filter(
            type=InAppNotification.Type.FAQ_QUESTION
        ).exists()

    def test_a_community_hide_sends_no_team_email(self, db):
        # In COMMUNITY the managers of a thing are its owner alone, and they
        # hid it — there is no team left to tell.
        contributor = User.objects.create(code="HCON01", email="hcon@test.com", name="Member")
        asker = User.objects.create(code="HASK01", email="hask@test.com", name="Asker")
        group = Collection.objects.create(
            code="HCOM01", owner=asker, headline="Street", mode=Collection.Mode.COMMUNITY
        )
        thing = Thing.objects.create(
            code="HTHG01", owner=contributor, headline="A tent", type="LEND_THING"
        )
        group.things.add(thing)

        res = client_for(asker).post(
            f"/api/v1/things/{thing.code}/faq/", {"question": "Waterproof?"}, format="json"
        )
        assert res.status_code == 201
        faq = FAQ.objects.get(code=res.data["code"])
        mail.outbox.clear()

        res = client_for(contributor).post(f"/api/v1/faq/{faq.code}/hide/")
        assert res.status_code == 200
        # The asker's ordinary hidden notice, and nothing else.
        assert [m.to[0] for m in mail.outbox] == [asker.email]

    def test_hiding_an_already_hidden_question_tells_nobody_again(
        self, space, member, owner, co_curator
    ):
        faq = self._ask(space, member)
        res = client_for(owner).post(f"/api/v1/faq/{faq.code}/hide/")
        assert res.status_code == 200
        mail.outbox.clear()
        notices_before = InAppNotification.objects.filter(
            type=InAppNotification.Type.FAQ_HIDDEN
        ).count()

        # The co-curator hides it a moment later (or the founder clicks twice).
        res = client_for(co_curator).post(f"/api/v1/faq/{faq.code}/hide/")
        assert res.status_code == 200
        assert res.data["faq"]["is_visible"] is False
        assert mail.outbox == []
        assert (
            InAppNotification.objects.filter(type=InAppNotification.Type.FAQ_HIDDEN).count()
            == notices_before
        )

    def test_showing_back_tells_nobody(self, space, member, owner, co_curator):
        faq = self._ask(space, member)
        res = client_for(owner).post(f"/api/v1/faq/{faq.code}/hide/")
        assert res.status_code == 200
        mail.outbox.clear()

        res = client_for(owner).post(f"/api/v1/faq/{faq.code}/show/")
        assert res.status_code == 200
        # Putting a question back is not something the team needs to hear.
        assert mail.outbox == []


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


class TestAHoldRequestWarnsTheWholeTeam:
    """A hold request is a question put to everyone who can answer it (CA,
    2026-09-29). Since 2026-09 a PROPRIETARY collection's co-curators decide
    holds and hear the decision (`BOOKING_DECIDED`), but the request itself
    reached only the thing's owner — so the first they heard of it was that the
    founder had already settled it."""

    @pytest.fixture
    def catalogue(self, owner, co_curator, member):
        coll = Collection.objects.create(
            code="HOLD01", owner=owner, headline="Tools", mode=Collection.Mode.PROPRIETARY
        )
        coll.invites.add(co_curator, member)
        coll.co_owners.add(co_curator)
        lend = Thing.objects.create(
            code="LEND01", type=Thing.Type.LEND_THING, owner=owner, headline="Drill"
        )
        gift = Thing.objects.create(
            code="GIFT01", type=Thing.Type.GIFT_THING, owner=owner, headline="Books"
        )
        coll.things.add(lend, gift)
        return {"collection": coll, "lend": lend, "gift": gift}

    def _ask(self, who, thing):
        body = {}
        if thing.type == Thing.Type.LEND_THING:
            start = date.today() + timedelta(days=2)
            body = {"start_date": str(start), "end_date": str(start + timedelta(days=3))}
        res = client_for(who).post(f"/api/v1/things/{thing.code}/request/", body, format="json")
        assert res.status_code == 201, res.data
        return BookingPeriod.objects.get(code=res.data["booking_code"])

    def _holders(self, booking):
        return set(
            InAppNotification.objects.filter(
                type=InAppNotification.Type.BOOKING_REQUESTED,
                payload__booking_code=booking.code,
            ).values_list("user_id", flat=True)
        )

    def test_a_loan_and_a_gift_request_each_reach_the_founder_and_the_co_curator(
        self, catalogue, member, owner, co_curator
    ):
        loan = self._ask(member, catalogue["lend"])
        gift = self._ask(member, catalogue["gift"])

        assert self._holders(loan) == {owner.code, co_curator.code}
        assert self._holders(gift) == {owner.code, co_curator.code}

    def test_every_copy_carries_the_same_payload(self, catalogue, member, owner, co_curator):
        booking = self._ask(member, catalogue["lend"])

        copies = InAppNotification.objects.filter(
            type=InAppNotification.Type.BOOKING_REQUESTED, payload__booking_code=booking.code
        )
        assert copies.count() == 2
        first, second = (n.payload for n in copies)
        assert first == second
        assert first["thing_headline"] == "Drill"
        assert first["start_date"] and first["end_date"]

    def test_a_co_curator_who_asks_is_not_warned_of_their_own_request(
        self, catalogue, owner, co_curator
    ):
        booking = self._ask(co_curator, catalogue["gift"])

        assert self._holders(booking) == {owner.code}

    def test_in_a_community_group_only_the_things_owner_is_asked(self, db, owner, co_curator):
        contributor = User.objects.create(code="CONT01", email="contrib@test.com", name="Lolo")
        asker = User.objects.create(code="ASKR01", email="asker@test.com", name="Lulu")
        group = Collection.objects.create(
            code="COMM01", owner=owner, headline="Street", mode=Collection.Mode.COMMUNITY
        )
        group.invites.add(co_curator, contributor, asker)
        group.co_owners.add(co_curator)
        tent = Thing.objects.create(
            code="TENT01", type=Thing.Type.GIFT_THING, owner=contributor, headline="A tent"
        )
        group.things.add(tent)

        booking = self._ask(asker, tent)

        # The group's curators run the group, not one member's own things.
        assert self._holders(booking) == {contributor.code}

    def test_a_decision_by_the_co_curator_leaves_no_copy_for_anyone(
        self, catalogue, member, owner, co_curator
    ):
        booking = self._ask(member, catalogue["gift"])

        res = client_for(co_curator).post(f"/api/v1/bookings/{booking.code}/accept/")
        assert res.status_code == 200

        assert self._holders(booking) == set()
        # The decision record is a different type and stays — for the founder, who
        # did not decide. Whoever did gets none: they pressed the button themselves
        # (CA, 2026-10-02).
        decided = InAppNotification.objects.filter(
            type=InAppNotification.Type.BOOKING_DECIDED, payload__booking_code=booking.code
        )
        assert {n.user_id for n in decided} == {owner.code}

    def test_the_requester_withdrawing_leaves_no_copy_for_anyone(
        self, catalogue, member, owner, co_curator
    ):
        booking = self._ask(member, catalogue["lend"])
        assert self._holders(booking) == {owner.code, co_curator.code}

        res = client_for(member).post(f"/api/v1/bookings/{booking.code}/cancel/")
        assert res.status_code == 200

        assert self._holders(booking) == set()


class TestACuratorDecidingTheirOwnRequest:
    """A curator who asks for a thing of their own group may accept or reject that
    request themselves — **on purpose** (CA, 2026-09-29), not by oversight.

    `BookingActionView` lets anyone who `can_manage` the thing decide, and a
    curator of a PROPRIETARY collection manages every thing in it, so nothing
    stops the person who asked from being the person who answers. For a GIFT or a
    SELL that hands the thing over, in their own name. The alternatives — a guard
    that refuses the requester, or a second curator's sign-off — were weighed and
    turned down: the team is small and trusts itself, and it is told either way.
    These tests fix the decision so that changing it is visible as one.
    """

    @pytest.fixture
    def catalogue(self, owner, co_curator, member):
        coll = Collection.objects.create(
            code="SELF01", owner=owner, headline="Books", mode=Collection.Mode.PROPRIETARY
        )
        coll.invites.add(co_curator, member)
        coll.co_owners.add(co_curator)
        gift = Thing.objects.create(
            code="SELG01", type=Thing.Type.GIFT_THING, owner=owner, headline="Old atlas"
        )
        coll.things.add(gift)
        return gift

    def _ask(self, who, thing):
        res = client_for(who).post(f"/api/v1/things/{thing.code}/request/", {}, format="json")
        assert res.status_code == 201, res.data
        return BookingPeriod.objects.get(code=res.data["booking_code"])

    def test_a_curator_may_decide_their_own_request_and_the_team_hears_of_it(
        self, catalogue, owner, co_curator
    ):
        booking = self._ask(co_curator, catalogue)

        res = client_for(co_curator).post(f"/api/v1/bookings/{booking.code}/accept/")

        assert res.status_code == 200
        catalogue.refresh_from_db()
        assert catalogue.status == Thing.Status.INACTIVE
        # The handover is recorded in the curator's own name.
        transfer = ThingTransfer.objects.get(booking=booking)
        assert (transfer.from_user_id, transfer.to_user_id) == (owner.code, co_curator.code)
        # The team hears of it through BOOKING_DECIDED: the founder, who did not
        # decide, gets the trail...
        decided = InAppNotification.objects.filter(
            type=InAppNotification.Type.BOOKING_DECIDED, payload__booking_code=booking.code
        )
        assert {n.user_id for n in decided} == {owner.code}
        assert "by_you" not in decided.get().payload
        assert decided.get().payload["decider_name"] == "Lele"
        # ...and the curator, as the requester, gets their own BOOKING_ACCEPTED —
        # never a "so-and-so decided" line about their own request.
        accepted = InAppNotification.objects.filter(
            user=co_curator,
            type=InAppNotification.Type.BOOKING_ACCEPTED,
            payload__booking_code=booking.code,
        )
        assert accepted.count() == 1
        assert accepted.get().payload["owner_name"] == "Lele"
        assert not InAppNotification.objects.filter(
            user=co_curator, type=InAppNotification.Type.BOOKING_DECIDED
        ).exists()

    def test_a_curator_may_reject_their_own_request_too(self, catalogue, owner, co_curator):
        booking = self._ask(co_curator, catalogue)

        res = client_for(co_curator).post(f"/api/v1/bookings/{booking.code}/reject/")

        assert res.status_code == 200
        booking.refresh_from_db()
        assert booking.status == BookingPeriod.Status.REJECTED
        catalogue.refresh_from_db()
        assert catalogue.status == Thing.Status.ACTIVE

    def test_the_email_fan_out_gives_whoever_asked_no_links_to_decide_with(
        self, catalogue, owner, co_curator
    ):
        # The emailed accept/reject links go to the *other* managers: the requester
        # is left out of the fan-out, so the only way for them to decide their own
        # request is the app.
        mail.outbox.clear()
        booking = self._ask(co_curator, catalogue)

        assert RSVP.objects.filter(user_code=co_curator, target_code=booking.code).count() == 0
        assert RSVP.objects.filter(user_code=owner, target_code=booking.code).count() == 2
