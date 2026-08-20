"""
Integration tests for Collection.allowed_thing_types.

Validates the per-collection thing-type allowlist set at creation/edit
time on `/collections/new` and `/collections/{code}/edit`.
"""

import pytest
from rest_framework import status

from core.models import Collection, Thing


@pytest.mark.django_db
class TestCreateWithAllowedTypes:
    """POST /api/v1/collections/ — allowlist is persisted and validated."""

    def test_create_proprietary_with_allowlist(self, authenticated_client):
        response = authenticated_client.post(
            "/api/v1/collections/",
            {"headline": "Books to lend", "allowed_thing_types": ["LEND_THING"]},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["allowed_thing_types"] == ["LEND_THING"]

    def test_create_proprietary_without_allowlist_succeeds(self, authenticated_client):
        """Empty list is tolerated by the API — UI enforces 'pick at least one'."""
        response = authenticated_client.post(
            "/api/v1/collections/",
            {"headline": "Untyped collection"},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["allowed_thing_types"] == []


@pytest.mark.django_db
class TestCommunityWithAllowedTypes:
    """COMMUNITY changes WHO may add a thing, never WHICH types are on offer.

    This class used to claim "COMMUNITY collections accept the wider type set;
    flags override the list" — true while SWAP and SHARE existed, and both the
    wider set and the flags went with them (see `type_validity_error`). The
    removal emptied the class and left the docstring behind, so it collected as
    a passing class that checked none of it. What holds now is the opposite and
    is worth pinning: the list is the same four types in either mode, and in
    COMMUNITY it has to gate the *member* who adds, since the owner is no
    longer the only one who can.
    """

    def test_community_gets_no_wider_type_set_than_a_proprietary_list(self, authenticated_client):
        """A type that no longer exists is refused here too, not quietly stored."""
        response = authenticated_client.post(
            "/api/v1/collections/",
            {
                "headline": "Mercadillo",
                "mode": "COMMUNITY",
                "allowed_thing_types": ["GIFT_THING", "SWAP_THING"],
            },
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "SWAP_THING" in str(response.data)
        assert not Collection.objects.filter(headline="Mercadillo").exists()

    def test_the_allowlist_gates_the_member_who_adds_not_only_the_owner(
        self, authenticated_client2, user, user2
    ):
        """COMMUNITY's whole point is that members contribute — so the owner's
        allowlist has to reach them. Gating only the owner would mean the one
        person it was written for can add anything (L4: no path bypasses it)."""
        coll = Collection.objects.create(
            code="COLL12",
            owner=user,
            headline="Books only",
            mode="COMMUNITY",
            allowed_thing_types=["LEND_THING"],
        )
        coll.invites.add(user2)

        response = authenticated_client2.post(
            "/api/v1/things/",
            {"headline": "A drill for sale", "type": "SELL_THING", "collection_code": coll.code},
            format="json",
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert not Thing.objects.filter(headline="A drill for sale").exists()

    def test_a_member_may_add_a_type_the_owner_did_allow(self, authenticated_client2, user, user2):
        """The other half: a gate that refused everything would satisfy the test
        above just as well as a correct one."""
        coll = Collection.objects.create(
            code="COLL13",
            owner=user,
            headline="Books only",
            mode="COMMUNITY",
            allowed_thing_types=["LEND_THING"],
        )
        coll.invites.add(user2)

        response = authenticated_client2.post(
            "/api/v1/things/",
            {"headline": "A novel", "type": "LEND_THING", "collection_code": coll.code},
            format="json",
        )

        assert response.status_code == status.HTTP_201_CREATED
        assert coll.things.filter(headline="A novel").exists()


@pytest.mark.django_db
class TestUpdateWithAllowedTypes:
    """PUT /api/v1/collections/{code}/ — narrowing is rejected when it would orphan."""

    def test_update_widens_list(self, authenticated_client, collection):
        """A 200 was the only thing asserted here, so a PATCH that answered OK and
        dropped the field on the floor passed. The point of widening is that the
        wider list is what the collection then holds."""
        response = authenticated_client.patch(
            f"/api/v1/collections/{collection.code}/",
            {"allowed_thing_types": ["GIFT_THING", "SELL_THING"]},
            format="json",
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.data["allowed_thing_types"] == ["GIFT_THING", "SELL_THING"]
        collection.refresh_from_db()
        assert collection.allowed_thing_types == ["GIFT_THING", "SELL_THING"]

    def test_update_narrows_orphaning_existing_things_fails(
        self, authenticated_client, user, collection
    ):
        """Cannot drop a type from the allowlist while things of that type sit in the collection."""
        thing = Thing.objects.create(code="THNG10", type="LEND_THING", owner=user, headline="Drill")
        collection.things.add(thing)
        # Restrict to GIFT only — the existing LEND_THING would be orphaned.
        response = authenticated_client.patch(
            f"/api/v1/collections/{collection.code}/",
            {"allowed_thing_types": ["GIFT_THING"]},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        # Error must name the offending type so the UI can guide the user.
        assert "LEND_THING" in str(response.data)


@pytest.mark.django_db
class TestAddThingRespectsAllowlist:
    """POST /api/v1/things/ with collection_code is gated by allowed_thing_types."""

    def test_add_thing_of_allowed_type(self, authenticated_client, user):
        coll = Collection.objects.create(
            code="COLL11",
            owner=user,
            headline="Sells only",
            allowed_thing_types=["SELL_THING"],
        )
        response = authenticated_client.post(
            "/api/v1/things/",
            {
                "type": "SELL_THING",
                "headline": "Bike",
                "fee": "50.00",
                "collection_code": coll.code,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED

    def test_add_thing_of_disallowed_type_rejected(self, authenticated_client, user):
        coll = Collection.objects.create(
            code="COLL12",
            owner=user,
            headline="Sells only",
            allowed_thing_types=["SELL_THING"],
        )
        response = authenticated_client.post(
            "/api/v1/things/",
            {
                "type": "GIFT_THING",
                "headline": "Sweater",
                "collection_code": coll.code,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_empty_allowlist_means_no_restriction(self, authenticated_client, user):
        """When allowed_thing_types is empty, any type is accepted (subject to other rules)."""
        coll = Collection.objects.create(
            code="COLL13",
            owner=user,
            headline="Free for all",
            allowed_thing_types=[],
        )
        response = authenticated_client.post(
            "/api/v1/things/",
            {
                "type": "GIFT_THING",
                "headline": "Anything goes",
                "collection_code": coll.code,
            },
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED


@pytest.mark.django_db
class TestChangingAnExistingThingsType:
    """The allowlist governs the **edit** door too, not only the add door.

    `ThingViewSet.perform_update` re-runs `type_validity_error` against every
    collection the thing lives in whenever the verb changes — and no test in the
    suite ever reached that code. The three PATCHes that touched `type` all
    stopped short of it: one names a retired type (refused by the serializer),
    one names a type this deployment withholds (refused by `CREATOR_POLICY`, one
    line above), and one re-sends the type the thing already has (no change, so
    the block is skipped entirely).

    So the whole re-validation was live and unguarded, on the path where it
    matters most: adding a thing of the wrong type is caught by a form that only
    offers the right ones, while *editing* is where an owner arrives with a verb
    already chosen and a collection that has since narrowed underneath it.
    """

    def _collection(self, owner, allowed, code="EDT001"):
        return Collection.objects.create(
            code=code, owner=owner, headline="Editables", allowed_thing_types=allowed
        )

    def _thing(self, owner, collection, thing_type=Thing.Type.GIFT_THING):
        thing = Thing.objects.create(
            code="EDTH01", type=thing_type, owner=owner, headline="A blender"
        )
        collection.things.add(thing)
        return thing

    def test_an_owner_may_move_a_thing_to_another_type_the_collection_allows(
        self, authenticated_client, user
    ):
        """The happy path, which had no test at all: a gift becomes a sale."""
        collection = self._collection(user, ["GIFT_THING", "SELL_THING"])
        thing = self._thing(user, collection)

        response = authenticated_client.patch(
            f"/api/v1/things/{thing.code}/", {"type": "SELL_THING"}, format="json"
        )

        assert response.status_code == status.HTTP_200_OK
        thing.refresh_from_db()
        assert thing.type == Thing.Type.SELL_THING

    def test_a_type_the_collection_does_not_allow_is_refused_on_edit_too(
        self, authenticated_client, user
    ):
        """Otherwise the allowlist is a rule you obey once and then edit around.

        The add door refuses `LEND_THING` here; without this the owner could
        create the thing as a gift and immediately PATCH it into a loan, landing
        exactly the row the collection said it would not hold.
        """
        collection = self._collection(user, ["GIFT_THING", "SELL_THING"])
        thing = self._thing(user, collection)

        response = authenticated_client.patch(
            f"/api/v1/things/{thing.code}/", {"type": "LEND_THING"}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "type" in response.data
        # Refused *and* unchanged — a 400 that had already written the row would
        # be worse than no check, since the owner is told it did not happen.
        thing.refresh_from_db()
        assert thing.type == Thing.Type.GIFT_THING

    def test_every_collection_the_thing_lives_in_gets_a_vote(self, authenticated_client, user):
        """The loop is over `thing.collections.all()`, and this is why.

        A thing shared with two groups must satisfy both: the drill lent to the
        neighbourhood *and* the family group cannot become a sale because one of
        them permits sales. A check that looked only at the first collection
        would pass here and quietly break the other group's rule.
        """
        permissive = self._collection(user, ["GIFT_THING", "SELL_THING"], code="EDT002")
        strict = self._collection(user, ["GIFT_THING"], code="EDT003")
        thing = self._thing(user, permissive)
        strict.things.add(thing)

        response = authenticated_client.patch(
            f"/api/v1/things/{thing.code}/", {"type": "SELL_THING"}, format="json"
        )

        assert response.status_code == status.HTTP_400_BAD_REQUEST
        thing.refresh_from_db()
        assert thing.type == Thing.Type.GIFT_THING
