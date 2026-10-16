"""
Integration tests for community collection endpoints.
"""

import pytest

from core.models import Collection, Thing


@pytest.mark.django_db
class TestCommunityCollectionCreate:
    """Tests for creating community collections."""

    def test_create_proprietary_by_default(self, authenticated_client):
        """Creating a collection without mode should default to PROPRIETARY."""
        response = authenticated_client.post(
            "/api/v1/collections/",
            {"headline": "My Collection", "kind": "STALL"},
            format="json",
        )
        assert response.status_code == 201
        assert response.json()["mode"] == "PROPRIETARY"

    def test_create_community_collection(self, authenticated_client):
        """Should create a community collection."""
        response = authenticated_client.post(
            "/api/v1/collections/",
            {"headline": "Mercadillo", "kind": "STALL", "mode": "COMMUNITY"},
            format="json",
        )
        assert response.status_code == 201
        assert response.json()["mode"] == "COMMUNITY"

    def test_mode_in_collection_detail(self, authenticated_client, collection):
        """Collection detail should include mode field."""
        response = authenticated_client.get(f"/api/v1/collections/{collection.code}/")
        assert response.status_code == 200
        assert response.json()["mode"] == "PROPRIETARY"


@pytest.mark.django_db
class TestCommunityCollectionUpdate:
    """Tests for updating collection mode."""

    def test_change_to_community(self, authenticated_client, collection):
        """Owner should be able to change mode to COMMUNITY."""
        response = authenticated_client.patch(
            f"/api/v1/collections/{collection.code}/",
            {"mode": "COMMUNITY"},
            format="json",
        )
        assert response.status_code == 200
        collection.refresh_from_db()
        assert collection.mode == "COMMUNITY"

    def test_change_to_proprietary(self, authenticated_client, user):
        """Owner should be able to change mode back to PROPRIETARY."""
        coll = Collection.objects.create(owner=user, headline="Market", mode="COMMUNITY")
        response = authenticated_client.patch(
            f"/api/v1/collections/{coll.code}/",
            {"mode": "PROPRIETARY"},
            format="json",
        )
        assert response.status_code == 200
        coll.refresh_from_db()
        assert coll.mode == "PROPRIETARY"


@pytest.mark.django_db
class TestCommunityAddThing:
    """Tests for adding things to community collections."""

    def test_create_thing_with_community_collection(self, authenticated_client2, user, user2):
        """Invited user should create a thing directly into a community collection."""
        coll = Collection.objects.create(owner=user, headline="Market", mode="COMMUNITY")
        coll.invites.add(user2)

        response = authenticated_client2.post(
            "/api/v1/things/",
            {
                "type": "SELL_THING",
                "headline": "My Book",
                "fee": "5.00",
                "collection_code": coll.code,
            },
            format="json",
        )
        assert response.status_code == 201
        assert coll.things.filter(headline="My Book").exists()

    def test_create_thing_with_proprietary_collection_denied(
        self, authenticated_client2, user, user2, collection
    ):
        """Invited user should NOT create a thing into a proprietary collection."""
        collection.invites.add(user2)

        response = authenticated_client2.post(
            "/api/v1/things/",
            {
                "type": "GIFT_THING",
                "headline": "My Gift",
                "collection_code": collection.code,
            },
            format="json",
        )
        # Not permitted to add to someone else's proprietary collection → 403.
        assert response.status_code == 403

    def test_create_thing_with_unknown_collection_is_404(self, authenticated_client):
        """A collection_code that resolves to nothing → 404, not a generic 400."""
        response = authenticated_client.post(
            "/api/v1/things/",
            {"type": "GIFT_THING", "headline": "My Gift", "collection_code": "NOPE99"},
            format="json",
        )
        assert response.status_code == 404


@pytest.mark.django_db
class TestNoRouteTakesAThingOutOfItsCollection:
    """A thing lives in exactly one collection, so nothing detaches it from it."""

    def test_the_curator_gets_a_404_and_the_thing_stays(self, authenticated_client, user, user2):
        coll = Collection.objects.create(owner=user, headline="Market", mode="COMMUNITY")
        thing = Thing.objects.create(owner=user2, headline="Guest Item", type="SELL_THING")
        coll.things.add(thing)

        response = authenticated_client.post(
            f"/api/v1/collections/{coll.code}/remove-thing/",
            {"thing_code": thing.code},
            format="json",
        )

        assert response.status_code == 404
        assert coll.things.filter(code=thing.code).exists()


@pytest.mark.django_db
class TestCommunityInactiveThingVisibility:
    """A member's own INACTIVE thing must stay visible to *them* on the
    collection page — `Thing.can_view()` already says "owner can always view
    their own things", and `CollectionSerializer.get_things()` used to answer
    a narrower question (are you the *collection* owner) that only happened to
    agree with it in PROPRIETARY mode, where those are the same person. In
    COMMUNITY mode they can differ: a contributed GIFT that completed (a
    non-endless hand-off flips it INACTIVE) or a listing the member hid
    themselves used to vanish from `/collections/{code}/` for everyone but the
    collection owner — including the person who owns it.
    """

    def _community_with_member_thing(self, user, user2, *, status="INACTIVE"):
        coll = Collection.objects.create(owner=user, headline="Market", mode="COMMUNITY")
        coll.invites.add(user2)
        thing = Thing.objects.create(
            owner=user2, headline="My gift", type="GIFT_THING", status=status
        )
        coll.things.add(thing)
        return coll, thing

    def test_member_sees_their_own_inactive_thing(self, authenticated_client2, user, user2):
        """The thing's own owner sees it, even INACTIVE and even as a non-owner
        of the collection."""
        coll, thing = self._community_with_member_thing(user, user2)

        response = authenticated_client2.get(f"/api/v1/collections/{coll.code}/")

        assert response.status_code == 200
        codes = [t["code"] for t in response.json()["things"]]
        assert thing.code in codes

    def test_a_different_member_does_not_see_it(self, authenticated_client, user, user2, db):
        """A co-member who isn't the thing's owner still can't — this is not a
        general INACTIVE-things-are-public change, only an exception for the
        thing's own owner."""
        from core.models import User

        coll, thing = self._community_with_member_thing(user, user2)
        other = User.objects.create(
            code="TEST03", email="lele1@your-domain.test", name="Test User 3"
        )
        coll.invites.add(other)
        from rest_framework.test import APIClient
        from rest_framework_simplejwt.tokens import RefreshToken

        other_client = APIClient()
        other_client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(other).access_token}"
        )

        response = other_client.get(f"/api/v1/collections/{coll.code}/")

        assert response.status_code == 200
        codes = [t["code"] for t in response.json()["things"]]
        assert thing.code not in codes

    def test_collection_owner_still_sees_every_members_inactive_thing(
        self, authenticated_client, user, user2
    ):
        """Unchanged: the collection owner's existing "see everything" answer
        does not depend on this exception."""
        coll, thing = self._community_with_member_thing(user, user2)

        response = authenticated_client.get(f"/api/v1/collections/{coll.code}/")

        assert response.status_code == 200
        codes = [t["code"] for t in response.json()["things"]]
        assert thing.code in codes

    def test_active_things_are_unaffected(self, authenticated_client2, user, user2):
        """The exception is INACTIVE-only — an ACTIVE contribution was already
        visible to everyone invited, this must not change that."""
        coll, thing = self._community_with_member_thing(user, user2, status="ACTIVE")

        response = authenticated_client2.get(f"/api/v1/collections/{coll.code}/")

        assert response.status_code == 200
        codes = [t["code"] for t in response.json()["things"]]
        assert thing.code in codes

    def test_anonymous_visitor_never_sees_it(self, api_client, user, user2):
        """An anonymous reader has no `viewer_code` to match — the exception
        must not become "nobody" and pass INACTIVE things through by accident."""
        coll, thing = self._community_with_member_thing(user, user2)
        coll.visibility = Collection.Visibility.PUBLIC
        coll.save(update_fields=["visibility"])

        response = api_client.get(f"/api/v1/collections/{coll.code}/")

        assert response.status_code == 200
        codes = [t["code"] for t in response.json()["things"]]
        assert thing.code not in codes
