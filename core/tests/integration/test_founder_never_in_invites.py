"""The founder is an FK on the collection, never a row in ``invites``.

``Thing.can_manage`` and the thing-delete rules treat the founder and the members as
different people; ending a "membership" deletes the member's things. So a founder who
slipped into ``invites`` could be "removed" by a co-curator, losing things nobody else
may delete. No door may put them there, and nobody may remove them.
"""

import pytest
from django.core import mail
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import RSVP, Collection, Event, Thing, User
from core.services.membership_service import end_membership

INVITE = "/api/v1/collections/{code}/invite/"
BULK = "/api/v1/collections/{code}/invite/bulk/"
PROPOSE = "/api/v1/collections/{code}/invite/propose/"
JOIN = "/api/v1/auth/join/"
VERIFY = "/api/v1/auth/verify/{token}/"


def client_for(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


@pytest.fixture
def founder(db):
    return User.objects.create(code="FOUN01", email="lala@your-domain.test", name="Lala")


@pytest.fixture
def curator(db):
    return User.objects.create(code="CURA01", email="lele@your-domain.test", name="Lele")


@pytest.fixture
def member(db):
    return User.objects.create(code="MEMB01", email="lili@your-domain.test", name="Lili")


@pytest.fixture
def group(db, founder, curator, member):
    collection = Collection.objects.create(
        code="GRP001", owner=founder, headline="The street", mode=Collection.Mode.COMMUNITY
    )
    collection.invites.add(curator, member)
    collection.co_owners.add(curator)
    return collection


def founders_thing(group, founder):
    thing = Thing.objects.create(
        code="FTHG01", owner=founder, type="GIFT_THING", headline="Founder's thing"
    )
    group.things.add(thing)
    return thing


class TestNoInvitationIsMintedForTheFounder:
    def test_a_curator_inviting_the_founders_address_is_told_they_are_already_in(
        self, group, founder, curator
    ):
        res = client_for(curator).post(
            INVITE.format(code=group.code), {"email": founder.email}, format="json"
        )

        assert res.status_code == 400
        assert res.data["code"] == "already_invited"
        assert not RSVP.objects.filter(user_code=founder).exists()
        assert mail.outbox == []

    def test_the_address_is_matched_whatever_its_case(self, group, founder, curator):
        res = client_for(curator).post(
            INVITE.format(code=group.code), {"email": founder.email.upper()}, format="json"
        )

        assert res.status_code == 400
        assert not RSVP.objects.filter(user_code=founder).exists()

    def test_bulk_skips_the_founder_as_already_member(self, group, founder, curator):
        res = client_for(curator).post(
            BULK.format(code=group.code),
            {"invites": [{"email": founder.email}, {"email": "lolo@your-domain.test"}]},
            format="json",
        )

        assert res.status_code == 200
        assert res.data["invited"] == 1
        assert res.data["skipped"] == [{"email": founder.email, "reason": "already_member"}]
        assert not RSVP.objects.filter(user_code=founder).exists()

    def test_a_recommendation_of_the_founder_gets_the_unified_answer(self, group, founder, member):
        group.allow_member_proposals = True
        group.save(update_fields=["allow_member_proposals"])
        url = PROPOSE.format(code=group.code)
        client_for(member).post(url, {"email": "lulu@your-domain.test"}, format="json")

        founder_res = client_for(member).post(url, {"email": founder.email}, format="json")
        queued_res = client_for(member).post(url, {"email": "lulu@your-domain.test"}, format="json")

        assert founder_res.status_code == 400
        assert founder_res.data == queued_res.data


class TestNoDoorPutsTheFounderInInvites:
    def test_accepting_an_invitation_minted_before_the_fix_adds_nobody(self, group, founder):
        accept = RSVP.objects.create(
            user_code=founder,
            user_email=founder.email,
            action=RSVP.Action.COLLECTION_INVITE,
            target_code=group.code,
        )

        res = APIClient().get(VERIFY.format(token=accept.token))

        assert res.status_code == 200
        assert res.data["landing"] == "collection"
        assert res.data["collection"] == group.code
        assert not group.invites.filter(code=founder.code).exists()
        assert not Event.objects.filter(
            kind=Event.Kind.MEMBER_JOINED, collection_code=group.code, actor_code=founder.code
        ).exists()

    def test_the_founder_pressing_their_own_public_join_link_adds_nobody(self, group, founder):
        group.visibility = Collection.Visibility.PUBLIC
        group.save()
        api = APIClient()
        api.post(JOIN, {"email": founder.email, "collection_code": group.code}, format="json")
        rsvp = RSVP.objects.get(user_code=founder, target_code=group.code)

        res = api.get(VERIFY.format(token=rsvp.token))

        assert res.status_code == 200
        assert res.data["invited_collection"] == group.code
        assert not group.invites.filter(code=founder.code).exists()
        assert not Event.objects.filter(
            kind=Event.Kind.MEMBER_JOINED, collection_code=group.code, actor_code=founder.code
        ).exists()


class TestTheFounderCannotBeRemoved:
    def test_a_curator_removing_a_founder_found_in_invites_is_refused_and_nothing_is_lost(
        self, group, founder, curator
    ):
        # An ``invites`` row from before the fix.
        group.invites.add(founder)
        thing = founders_thing(group, founder)

        res = client_for(curator).delete(
            INVITE.format(code=group.code), {"user_code": founder.code}, format="json"
        )

        assert res.status_code == 400
        assert res.data["code"] == "owner_cannot_be_removed"
        assert Thing.objects.filter(code=thing.code).exists()
        assert mail.outbox == []

    def test_ending_the_founders_membership_raises_and_deletes_nothing(self, group, founder):
        group.invites.add(founder)
        thing = founders_thing(group, founder)

        with pytest.raises(ValueError):
            end_membership(group, founder, actor=founder)

        assert Thing.objects.filter(code=thing.code).exists()
        assert group.invites.filter(code=founder.code).exists()
