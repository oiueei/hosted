"""Unit tests for per-collection PUBLIC/PRIVATE visibility (#5, phase 1).

Cover the model authorisation helpers (``Collection.can_view`` / ``Thing.can_view``
made anonymous-safe with a PUBLIC branch) and the create serializer's
default-by-mode behaviour. The view-level anonymous read and the auto-join flow
are exercised in their own integration suites.
"""

import pytest

from core.models import Collection, Thing
from core.serializers import CollectionCreateSerializer
from core.tests.factories import CollectionFactory, ThingFactory, UserFactory

pytestmark = pytest.mark.django_db


# --- Collection.is_public / can_view -------------------------------------


def test_is_public_reflects_visibility():
    assert CollectionFactory(visibility=Collection.Visibility.PUBLIC).is_public() is True
    assert CollectionFactory(visibility=Collection.Visibility.PRIVATE).is_public() is False


def test_owner_can_view_own_private_and_inactive_collection():
    owner = UserFactory()
    private = CollectionFactory(owner=owner, visibility=Collection.Visibility.PRIVATE)
    inactive = CollectionFactory(
        owner=owner,
        visibility=Collection.Visibility.PRIVATE,
        status=Collection.Status.INACTIVE,
    )
    assert private.can_view(owner.code) is True
    assert inactive.can_view(owner.code) is True


def test_anonymous_can_view_public_active_collection():
    public = CollectionFactory(visibility=Collection.Visibility.PUBLIC)
    # An anonymous visitor is passed user_code=None.
    assert public.can_view(None) is True


def test_anonymous_cannot_view_private_collection():
    private = CollectionFactory(visibility=Collection.Visibility.PRIVATE)
    assert private.can_view(None) is False


def test_anonymous_cannot_view_public_but_inactive_collection():
    hidden = CollectionFactory(
        visibility=Collection.Visibility.PUBLIC,
        status=Collection.Status.INACTIVE,
    )
    assert hidden.can_view(None) is False


def test_invited_member_can_view_private_collection_but_stranger_cannot():
    member = UserFactory()
    stranger = UserFactory()
    private = CollectionFactory(visibility=Collection.Visibility.PRIVATE)
    private.invites.add(member)
    assert private.can_view(member.code) is True
    assert private.can_view(stranger.code) is False


@pytest.mark.parametrize("visibility", list(Collection.Visibility))
@pytest.mark.parametrize("status", list(Collection.Status))
def test_a_known_membership_set_never_changes_the_answer(visibility, status):
    """`invited_to` only saves the membership query for a caller judging many
    collections at once: for every visibility, status and relationship the
    answer must be exactly the one the database gives, or the shortcut would be a
    second, drifting copy of the rules."""
    owner, member, stranger = UserFactory.create_batch(3)
    collection = CollectionFactory(owner=owner, visibility=visibility, status=status)
    collection.invites.add(member)

    for who in (owner, member, stranger, None):
        code = who.code if who else None
        invited_to = {collection.code} if who is member else set()
        assert collection.can_view(code, invited_to=invited_to) == collection.can_view(code), (
            visibility,
            status,
            who,
        )


def test_a_known_membership_set_is_read_instead_of_asking_the_database(
    django_assert_num_queries,
):
    collection = CollectionFactory(visibility=Collection.Visibility.PRIVATE)
    member = UserFactory()
    collection.invites.add(member)

    with django_assert_num_queries(0):
        assert collection.can_view(member.code, invited_to={collection.code}) is True
        assert collection.can_view(member.code, invited_to=set()) is False


def test_stranger_can_view_public_collection():
    stranger = UserFactory()
    public = CollectionFactory(visibility=Collection.Visibility.PUBLIC)
    assert public.can_view(stranger.code) is True


# --- Thing.can_view through a PUBLIC collection ---------------------------


def test_anonymous_can_view_active_thing_in_public_collection():
    public = CollectionFactory(visibility=Collection.Visibility.PUBLIC)
    thing = ThingFactory(status=Thing.Status.ACTIVE)
    public.things.add(thing)
    assert thing.can_view(None) is True


def test_anonymous_cannot_view_thing_in_private_collection():
    private = CollectionFactory(visibility=Collection.Visibility.PRIVATE)
    thing = ThingFactory(status=Thing.Status.ACTIVE)
    private.things.add(thing)
    assert thing.can_view(None) is False


def test_anonymous_cannot_view_inactive_thing_even_in_public_collection():
    public = CollectionFactory(visibility=Collection.Visibility.PUBLIC)
    thing = ThingFactory(status=Thing.Status.INACTIVE)
    public.things.add(thing)
    assert thing.can_view(None) is False


def test_anonymous_cannot_view_thing_in_public_but_inactive_collection():
    hidden = CollectionFactory(
        visibility=Collection.Visibility.PUBLIC,
        status=Collection.Status.INACTIVE,
    )
    thing = ThingFactory(status=Thing.Status.ACTIVE)
    hidden.things.add(thing)
    assert thing.can_view(None) is False


def test_invited_member_can_view_thing_in_private_collection():
    member = UserFactory()
    private = CollectionFactory(visibility=Collection.Visibility.PRIVATE)
    private.invites.add(member)
    thing = ThingFactory(status=Thing.Status.ACTIVE)
    private.things.add(thing)
    assert thing.can_view(member.code) is True


# --- CollectionCreateSerializer: a collection is born private --------------


def _validated(data):
    serializer = CollectionCreateSerializer(data=data)
    assert serializer.is_valid(), serializer.errors
    return serializer.validated_data


def test_a_community_collection_is_born_private_like_any_other():
    """Making a group public is an explicit decision.

    It used to be born PUBLIC, and whoever contributed a thing to it was never
    shown that — so a group of neighbours' families was readable by anyone.
    """
    data = _validated({"headline": "Neighbourhood share", "mode": "COMMUNITY"})
    assert data["visibility"] == Collection.Visibility.PRIVATE


def test_proprietary_collection_is_born_private():
    data = _validated({"headline": "My shelf"})  # mode defaults to PROPRIETARY
    assert data["visibility"] == Collection.Visibility.PRIVATE


def test_an_explicit_visibility_is_respected_in_either_mode():
    # A proprietary owner may open their collection to the public…
    data = _validated({"headline": "Open shelf", "mode": "PROPRIETARY", "visibility": "PUBLIC"})
    assert data["visibility"] == Collection.Visibility.PUBLIC
    # …and so may a community's: it can be born public when that is asked for.
    data = _validated({"headline": "Open group", "mode": "COMMUNITY", "visibility": "PUBLIC"})
    assert data["visibility"] == Collection.Visibility.PUBLIC
    # Private stays private in either mode, of course.
    data = _validated({"headline": "Closed group", "mode": "COMMUNITY", "visibility": "PRIVATE"})
    assert data["visibility"] == Collection.Visibility.PRIVATE
