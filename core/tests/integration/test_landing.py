"""
Post-login landing (O3): where VerifyLinkView sends the user after a magic link.

The destination used to be a client-side ``seenWelcome`` localStorage heuristic —
and since logout clears that key, every re-login looked like a first visit and
dumped returning users on the new-visitor page. It is now decided server-side from the RSVP's
origin and the user's collections.
"""

import pytest
from rest_framework.test import APIClient

from core.models import RSVP, Collection

VERIFY_URL = "/api/v1/auth/verify/{}/"


def _magic_link(user, origin=RSVP.Origin.LOGIN, target_code=""):
    return RSVP.objects.create(
        user_code=user,
        user_email=user.email,
        action=RSVP.Action.MAGIC_LINK,
        origin=origin,
        target_code=target_code,
    )


def _verify(rsvp):
    return APIClient().get(VERIFY_URL.format(rsvp.token))


@pytest.mark.django_db
class TestMagicLinkLanding:
    def test_a_targetless_join_link_lands_on_welcome(self, user):
        """The landing a deployment with its own open door depends on.

        Built directly: nothing here stamps POPIN without a collection any more.
        """
        res = _verify(_magic_link(user, origin=RSVP.Origin.POPIN))

        assert res.status_code == 200
        assert res.data["landing"] == "welcome"

    def test_link_carrying_a_collection_lands_on_it(self, user, collection):
        # A share-token / public-collection join: they joined that collection to
        # get here, so the origin doesn't matter — the target wins.
        res = _verify(_magic_link(user, origin=RSVP.Origin.POPIN, target_code=collection.code))

        assert res.data["landing"] == "collection"
        assert res.data["collection"] == collection.code
        assert res.data["invited_collection"] == collection.code

    def test_link_carrying_an_inactive_collection_falls_back(self, user, collection):
        # The collection went INACTIVE between the join and the click — landing
        # there would 403. The origin rule takes over instead (POPIN -> welcome).
        collection.status = Collection.Status.INACTIVE
        collection.save()
        res = _verify(_magic_link(user, origin=RSVP.Origin.POPIN, target_code=collection.code))

        assert res.data["landing"] == "welcome"
        assert "collection" not in res.data
        assert "invited_collection" not in res.data

    def test_login_with_exactly_one_collection_lands_on_it(self, user, collection):
        # `collection` is this user's only one.
        res = _verify(_magic_link(user))

        assert res.data["landing"] == "collection"
        assert res.data["collection"] == collection.code
        # Not an invitation — the SPA must not show the invite welcome box.
        assert "invited_collection" not in res.data

    def test_login_with_one_invited_collection_lands_on_it(self, user, user2, collection):
        # Invited counts the same as owned: it's still their only collection.
        collection.invites.add(user2)
        res = _verify(_magic_link(user2))

        assert res.data["landing"] == "collection"
        assert res.data["collection"] == collection.code

    def test_login_with_several_collections_lands_on_home(self, user, collection):
        Collection.objects.create(code="SECOND", owner=user, headline="Second one")
        res = _verify(_magic_link(user))

        assert res.data["landing"] == "home"
        assert "collection" not in res.data

    def test_login_with_no_collections_lands_on_home(self, user2):
        res = _verify(_magic_link(user2))

        assert res.data["landing"] == "home"

    def test_inactive_collections_do_not_count(self, user, collection):
        collection.status = Collection.Status.INACTIVE
        collection.save()
        res = _verify(_magic_link(user))

        assert res.data["landing"] == "home"

    def test_legacy_link_without_an_origin_is_treated_as_a_login(self, user, collection):
        # Magic links minted before RSVP.origin existed have origin="" — they are
        # returning users, so they follow the login rule.
        res = _verify(_magic_link(user, origin=""))

        assert res.data["landing"] == "collection"
        assert res.data["collection"] == collection.code


@pytest.mark.django_db
class TestOriginIsStamped:
    def test_request_link_stamps_login(self, api_client, user):
        api_client.post("/api/v1/auth/request-link/", {"email": user.email}, format="json")

        rsvp = RSVP.objects.get(user_code=user, action=RSVP.Action.MAGIC_LINK)
        assert rsvp.origin == RSVP.Origin.LOGIN

    def test_joining_stamps_popin(self, api_client, user):
        """Every join through this endpoint is stamped POPIN, whichever door it came in by.

        Written through a PUBLIC collection rather than a bare email: that is
        one of the two doors that outlive the demo, and the endpoint now needs
        a target before it creates anything.
        """
        public = Collection.objects.create(
            code="LANDPB",
            owner=user,
            headline="Public",
            visibility=Collection.Visibility.PUBLIC,
        )

        api_client.post(
            "/api/v1/auth/join/",
            {"email": "fresh@test.com", "collection_code": public.code},
            format="json",
        )

        rsvp = RSVP.objects.get(user_email="fresh@test.com", action=RSVP.Action.MAGIC_LINK)
        assert rsvp.origin == RSVP.Origin.POPIN


@pytest.mark.django_db
class TestCollectionInviteLanding:
    def test_invite_lands_on_its_collection(self, user2, collection):
        rsvp = RSVP.objects.create(
            user_code=user2,
            user_email=user2.email,
            action=RSVP.Action.COLLECTION_INVITE,
            target_code=collection.code,
        )

        res = _verify(rsvp)

        assert res.data["landing"] == "collection"
        assert res.data["collection"] == collection.code
        assert res.data["invited_collection"] == collection.code

    def test_invite_to_a_deleted_collection_lands_on_home(self, user2):
        rsvp = RSVP.objects.create(
            user_code=user2,
            user_email=user2.email,
            action=RSVP.Action.COLLECTION_INVITE,
            target_code="GONE01",
        )

        res = _verify(rsvp)

        assert res.data["landing"] == "home"
