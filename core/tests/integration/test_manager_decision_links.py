"""Each manager decides a hold with their own emailed link (CA, 2026-09-29).

A hold request is emailed to every manager of the thing (its owner and the
curators of a PROPRIETARY collection it sits in), each with **their own**
accept/reject pair. Using a link signs the decision as whoever it was minted to,
and — the reason this is safe — authority is checked again at the click: a
co-curator demoted after the email cannot decide with the old link.
"""

from datetime import date, timedelta

import pytest
from django.core import mail
from django.utils.html import escape
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import RSVP, BookingPeriod, Collection, Thing, User
from core.models.notification import InAppNotification

pytestmark = pytest.mark.django_db


def client_for(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


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
def catalogue(owner, co_curator, member):
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


def _ask(who, thing):
    body = {}
    if thing.type == Thing.Type.LEND_THING:
        start = date.today() + timedelta(days=2)
        body = {"start_date": str(start), "end_date": str(start + timedelta(days=3))}
    res = client_for(who).post(f"/api/v1/things/{thing.code}/request/", body, format="json")
    assert res.status_code == 201, res.data
    return BookingPeriod.objects.get(code=res.data["booking_code"])


def _link(booking, user, action=RSVP.Action.BOOKING_ACCEPT):
    return RSVP.objects.get(target_code=booking.code, user_code=user, action=action)


def _press(rsvp):
    """What the confirm button on the verify page does: POST the token."""
    return APIClient().post(f"/api/v1/auth/verify/{rsvp.token}/")


class TestEveryManagerGetsTheirOwnEmail:
    def test_each_manager_is_mailed_separately_with_links_only_they_hold(
        self, catalogue, member, owner, co_curator
    ):
        mail.outbox.clear()
        booking = _ask(member, catalogue["lend"])

        to_managers = {
            m.to[0]: m for m in mail.outbox if m.to[0] in {owner.email, co_curator.email}
        }
        assert set(to_managers) == {owner.email, co_curator.email}
        assert all(len(m.to) == 1 for m in mail.outbox)  # never one message to both

        tokens = {}
        for who in (owner, co_curator):
            accept = _link(booking, who)
            reject = _link(booking, who, RSVP.Action.BOOKING_REJECT)
            assert accept.user_email == who.email
            body = to_managers[who.email].body
            assert accept.action_link() in body
            assert reject.action_link() in body
            tokens[who.code] = {accept.token, reject.token}

        assert tokens[owner.code].isdisjoint(tokens[co_curator.code])
        # Each one's message carries nobody else's links.
        for who, other in ((owner, co_curator), (co_curator, owner)):
            for token in tokens[other.code]:
                assert token not in to_managers[who.email].body

    def test_a_co_curator_who_asks_gets_no_email_and_no_links(self, catalogue, owner, co_curator):
        mail.outbox.clear()
        booking = _ask(co_curator, catalogue["gift"])

        assert not RSVP.objects.filter(target_code=booking.code, user_code=co_curator).exists()
        assert co_curator.email in {m.to[0] for m in mail.outbox}  # their own confirmation…
        request_mail = [m for m in mail.outbox if _link(booking, owner).token in m.body]
        assert [m.to[0] for m in request_mail] == [owner.email]  # …and no request

    def test_in_a_community_group_a_curator_who_is_not_the_owner_gets_no_links(
        self, db, owner, co_curator
    ):
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

        booking = _ask(asker, tent)

        holders = set(
            RSVP.objects.filter(target_code=booking.code).values_list("user_code_id", flat=True)
        )
        assert holders == {contributor.code}


class TestTheRequesterIsToldHowManyWereWarned:
    """The "request sent" email says who was warned by number — "the person who runs
    it", or "the people who run it" — and that number is the request's own fan-out:
    the thing's managers bar the requester (CA, 2026-10-02: it used to name the
    owner, which was untrue once a team runs the thing; CT1, CA, 2026-10-05: nor
    does it say "curator", which is untrue in a COMMUNITY, where whoever runs a
    thing is its owner, a member)."""

    ONE = "We've let the person who runs it know"
    MANY = "We've let the people who run it know"
    # Letter by letter, as CA approved them (SONNET_TASKS.md, round CT), for one person.
    RUNS_IT = {
        "es": "Hemos avisado a quien gestiona esta cosa — te responderá pronto.",
        "ca": "Hem avisat qui gestiona aquesta cosa — aviat et respondrà.",
        "en": "We've let the person who runs it know — they'll get back to you soon.",
    }

    def _told(self, who):
        sent = [m for m in mail.outbox if m.to == [who.email]]
        assert len(sent) == 1
        return sent[0].body

    def test_a_thing_with_one_manager_says_the_person_who_runs_it(self, db, owner, member):
        solo = Collection.objects.create(
            code="SOLO01", owner=owner, headline="Mine", mode=Collection.Mode.PROPRIETARY
        )
        solo.invites.add(member)
        drill = Thing.objects.create(
            code="SOLT01", type=Thing.Type.GIFT_THING, owner=owner, headline="Books"
        )
        solo.things.add(drill)
        mail.outbox.clear()

        _ask(member, drill)

        body = self._told(member)
        assert self.ONE in body and self.MANY not in body

    def test_a_thing_run_by_a_team_says_the_people_who_run_it(self, catalogue, member):
        mail.outbox.clear()

        _ask(member, catalogue["lend"])

        body = self._told(member)
        assert self.MANY in body and self.ONE not in body

    def test_it_says_so_in_the_requesters_language(self, catalogue, member):
        member.language = "es"
        member.save(update_fields=["language"])
        mail.outbox.clear()

        _ask(member, catalogue["lend"])

        assert "Hemos avisado a quienes gestionan esta cosa — te responderán pronto." in self._told(
            member
        )

    @pytest.mark.parametrize("lang", ["es", "ca", "en"])
    def test_in_a_community_it_never_calls_whoever_runs_the_thing_a_curator(
        self, db, owner, co_curator, member, lang
    ):
        # In a COMMUNITY the one who runs a thing is its owner — a member, not whoever
        # curates the group — so the email may not say "dinamizador" / "dinamitzador" /
        # "curator", in any language, and says what the request page says.
        contributor = User.objects.create(code="CONT02", email="contrib2@test.com", name="Lolo")
        group = Collection.objects.create(
            code="COMM02", owner=owner, headline="Street", mode=Collection.Mode.COMMUNITY
        )
        group.invites.add(co_curator, contributor, member)
        group.co_owners.add(co_curator)
        tent = Thing.objects.create(
            code="TENT02", type=Thing.Type.GIFT_THING, owner=contributor, headline="A tent"
        )
        group.things.add(tent)
        member.language = lang
        member.save(update_fields=["language"])
        mail.outbox.clear()

        _ask(member, tent)

        (confirmation,) = [m for m in mail.outbox if m.to == [member.email]]
        html = confirmation.alternatives[0][0]
        said = self.RUNS_IT[lang]
        assert said in confirmation.body
        assert escape(said) in html
        for stem in ("dinamiz", "dinamitz", "curator"):
            assert stem not in confirmation.body.lower()
            assert stem not in html.lower()

    def test_a_curator_who_asks_is_not_counted_among_those_warned(
        self, catalogue, owner, co_curator
    ):
        # Two people run the thing, but one of them is the one asking: only the
        # founder is warned, so it is "the person who runs it", not "the people".
        mail.outbox.clear()

        _ask(co_curator, catalogue["gift"])

        body = self._told(co_curator)
        assert self.ONE in body and self.MANY not in body


class TestAManagerOfBothCollectionsHearsARequestOnce:
    """A thing may sit in two PROPRIETARY collections with the same people
    running both — the drill listed under "Tools" and under "Neighbours".
    Whoever curates the two hears one request **once**: one email, one link
    pair, one inbox notice, not one of each per collection. That is what the
    dedupe in ``Thing.managers()`` buys; the query budget in
    ``test_query_counts.py`` guards the fan-out's cost, but a rewrite of it
    would not name this behaviour."""

    def test_a_curator_of_both_collections_is_emailed_linked_and_warned_once(
        self, db, owner, co_curator, member
    ):
        drill = Thing.objects.create(
            code="LEND02", type=Thing.Type.LEND_THING, owner=owner, headline="Drill"
        )
        for code, name in (("HOLD02", "Tools"), ("HOLD03", "Neighbours")):
            coll = Collection.objects.create(
                code=code, owner=owner, headline=name, mode=Collection.Mode.PROPRIETARY
            )
            coll.invites.add(co_curator, member)
            coll.co_owners.add(co_curator)
            coll.things.add(drill)

        mail.outbox.clear()
        booking = _ask(member, drill)

        for who in (owner, co_curator):
            theirs = [m for m in mail.outbox if m.to == [who.email]]
            assert len(theirs) == 1, f"{who.name} got {len(theirs)} emails, wanted 1"
            links = RSVP.objects.filter(target_code=booking.code, user_code=who)
            assert links.count() == 2
            assert set(links.values_list("action", flat=True)) == {
                RSVP.Action.BOOKING_ACCEPT,
                RSVP.Action.BOOKING_REJECT,
            }
            assert (
                InAppNotification.objects.filter(
                    user=who,
                    type=InAppNotification.Type.BOOKING_REQUESTED,
                    payload__booking_code=booking.code,
                ).count()
                == 1
            )
        # And the fan-out as a whole: two managers, one pair of links and one
        # notice each — nothing per collection.
        assert RSVP.objects.filter(target_code=booking.code).count() == 4
        assert (
            InAppNotification.objects.filter(
                type=InAppNotification.Type.BOOKING_REQUESTED,
                payload__booking_code=booking.code,
            ).count()
            == 2
        )


class TestTheDecisionIsSignedByWhoeverPressed:
    def test_a_co_curators_link_accepts_and_names_them(self, catalogue, member, owner, co_curator):
        booking = _ask(member, catalogue["gift"])

        res = _press(_link(booking, co_curator))

        assert res.status_code == 200, res.data
        booking.refresh_from_db()
        assert booking.status == BookingPeriod.Status.ACCEPTED
        # The requester is told by the co-curator, not by the founder…
        told = InAppNotification.objects.get(
            user=member, type=InAppNotification.Type.BOOKING_ACCEPTED
        )
        assert told.payload["owner_name"] == co_curator.name
        # …the founder, who did not decide, gets the record of the call; the
        # co-curator who pressed the link gets none (they just did it).
        decided = {
            n.user_id: n.payload
            for n in InAppNotification.objects.filter(type=InAppNotification.Type.BOOKING_DECIDED)
        }
        assert set(decided) == {owner.code}
        assert decided[owner.code]["decider_name"] == co_curator.name

    def test_the_founders_link_still_works_as_before(self, catalogue, member, owner, co_curator):
        booking = _ask(member, catalogue["gift"])

        res = _press(_link(booking, owner))

        assert res.status_code == 200, res.data
        booking.refresh_from_db()
        assert booking.status == BookingPeriod.Status.ACCEPTED
        told = InAppNotification.objects.get(
            user=member, type=InAppNotification.Type.BOOKING_ACCEPTED
        )
        assert told.payload["owner_name"] == owner.name

    def test_once_anyone_decides_every_managers_links_are_dead(
        self, catalogue, member, owner, co_curator
    ):
        booking = _ask(member, catalogue["lend"])
        founders = [
            _link(booking, owner),
            _link(booking, owner, RSVP.Action.BOOKING_REJECT),
        ]

        assert _press(_link(booking, co_curator)).status_code == 200

        assert not RSVP.objects.filter(target_code=booking.code).exists()
        for rsvp in founders:
            assert _press(rsvp).status_code == 401
        booking.refresh_from_db()
        assert booking.status == BookingPeriod.Status.ACCEPTED


class TestALinkThatLosesARace:
    def test_it_decides_nothing_and_says_the_booking_is_already_processed(
        self, catalogue, member, owner, co_curator, monkeypatch
    ):
        # Two managers press at once: both pass the link's validity check, and only
        # one wins the locked transition. One thread cannot interleave them, so the
        # winner commits from inside the loser's call and the loser then runs the
        # real service, which finds the booking decided and does nothing.
        from core.views import auth as auth_views

        booking = _ask(member, catalogue["gift"])
        losing_link = _link(booking, co_curator, RSVP.Action.BOOKING_REJECT)
        real = auth_views.finalize_booking_decision

        def the_owner_decides_first(pending, **kwargs):
            real(BookingPeriod.objects.get(pk=pending.pk), accepted=True, decided_by=owner)
            return real(pending, **kwargs)

        monkeypatch.setattr(auth_views, "finalize_booking_decision", the_owner_decides_first)

        res = _press(losing_link)

        assert res.status_code == 400
        assert res.data == {"error": "Booking expired or already processed"}
        # The winner's call stands, and the requester heard one answer, not two.
        booking.refresh_from_db()
        assert booking.status == BookingPeriod.Status.ACCEPTED
        told = InAppNotification.objects.filter(
            user=member,
            type__in=[
                InAppNotification.Type.BOOKING_ACCEPTED,
                InAppNotification.Type.BOOKING_REJECTED,
            ],
        )
        assert [n.type for n in told] == [InAppNotification.Type.BOOKING_ACCEPTED]


class TestAuthorityIsCheckedAtTheClick:
    """The link outlives the role that earned it — 72 hours, in the mailbox of
    someone who may since have been demoted or removed."""

    def test_a_co_curator_demoted_after_the_email_cannot_decide(
        self, catalogue, member, owner, co_curator
    ):
        booking = _ask(member, catalogue["gift"])
        accept = _link(booking, co_curator)
        reject = _link(booking, co_curator, RSVP.Action.BOOKING_REJECT)
        catalogue["collection"].co_owners.remove(co_curator)

        res = _press(accept)

        assert res.status_code == 403
        # The sentence is what it always was, for a client that knows nothing more;
        # the code is what lets the verify page say why (H9b).
        assert res.data == {"error": "Not authorized", "code": "no_longer_manages"}
        booking.refresh_from_db()
        assert booking.status == BookingPeriod.Status.PENDING
        assert not RSVP.objects.filter(pk=accept.pk).exists()
        # The refusal decided nothing for anyone: no notice went to the requester
        # and the founder can still answer.
        assert not InAppNotification.objects.filter(
            user=member, type=InAppNotification.Type.BOOKING_ACCEPTED
        ).exists()
        # The sibling link is no more use to them.
        assert _press(reject).status_code == 403
        booking.refresh_from_db()
        assert booking.status == BookingPeriod.Status.PENDING
        assert _press(_link(booking, owner)).status_code == 200

    def test_a_refused_decision_is_logged_with_who_which_booking_and_from_where(
        self, catalogue, member, co_curator, security_log
    ):
        # The only trace the operator has that a stale link was used — told apart
        # from a probe by who held it, for which request and from which address.
        # The three facts, not the sentence around them.
        booking = _ask(member, catalogue["gift"])
        accept = _link(booking, co_curator)
        catalogue["collection"].co_owners.remove(co_curator)
        security_log.clear()

        res = APIClient().post(f"/api/v1/auth/verify/{accept.token}/", REMOTE_ADDR="203.0.113.7")

        assert res.status_code == 403
        refusals = [r.getMessage() for r in security_log.records if r.name == "security"]
        assert len(refusals) == 1
        for fact in (co_curator.code, booking.code, "203.0.113.7"):
            assert fact in refusals[0]

    def test_a_curator_of_a_collection_turned_community_cannot_decide(
        self, catalogue, member, owner, co_curator
    ):
        booking = _ask(member, catalogue["gift"])
        accept = _link(booking, co_curator)
        collection = catalogue["collection"]
        collection.mode = Collection.Mode.COMMUNITY
        collection.save()

        assert _press(accept).status_code == 403
        booking.refresh_from_db()
        assert booking.status == BookingPeriod.Status.PENDING

    def test_a_previewing_scanner_never_reaches_the_check_or_the_booking(
        self, catalogue, member, co_curator
    ):
        booking = _ask(member, catalogue["gift"])
        accept = _link(booking, co_curator)

        res = APIClient().get(f"/api/v1/auth/verify/{accept.token}/")

        assert res.status_code == 200
        assert res.data["requires_confirmation"] is True
        booking.refresh_from_db()
        assert booking.status == BookingPeriod.Status.PENDING
        assert RSVP.objects.filter(pk=accept.pk).exists()
