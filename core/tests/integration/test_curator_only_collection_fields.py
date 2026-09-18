"""Collection fields only its curators may read.

`CollectionSerializer` answers every reader of a collection — its members and,
on a PUBLIC one, anybody at all. Some of what it holds is written for a
narrower audience than that, and the only page that reads it back is the
curators' own edit form. These tests ask the API as each kind of reader, so a
field that starts travelling to the wrong one fails here rather than in a
screenshot somebody shares.
"""

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import Collection, User

pytestmark = pytest.mark.django_db

NOTE = "Key box by the door, code 4417. Call 600 000 000 when you arrive."


def _client(user=None):
    client = APIClient()
    if user is not None:
        token = RefreshToken.for_user(user).access_token
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.fixture
def member(db):
    return User.objects.create(code="MEMB01", email="member@example.com", name="Member")


@pytest.fixture
def co_owner(db):
    return User.objects.create(code="COOW01", email="cocurator@example.com", name="Co")


@pytest.fixture
def space(user, member, co_owner):
    collection = Collection.objects.create(
        code="NOTE01",
        owner=user,
        headline="Community room",
        visibility=Collection.Visibility.PUBLIC,
        email_note=NOTE,
    )
    collection.invites.add(member, co_owner)
    collection.co_owners.add(co_owner)
    return collection


def _read(client, collection):
    response = client.get(f"/api/v1/collections/{collection.code}/")
    assert response.status_code == 200
    return response.json()


class TestTheEmailNote:
    """Written for the emails a member gets about their own request — never
    for the collection page."""

    def test_an_anonymous_reader_of_a_public_collection_does_not_get_it(self, space):
        assert _read(_client(), space)["email_note"] == ""

    def test_a_member_does_not_get_it_from_the_collection_either(self, space, member):
        assert _read(_client(member), space)["email_note"] == ""

    def test_the_owner_reads_it_back_to_edit_it(self, space, user):
        assert _read(_client(user), space)["email_note"] == NOTE

    def test_a_co_curator_reads_it_back_too(self, space, co_owner):
        # The edit form is theirs as much as the founder's (IsCollectionCurator).
        assert _read(_client(co_owner), space)["email_note"] == NOTE

    def test_the_list_of_invited_collections_withholds_it(self, space, member):
        response = _client(member).get("/api/v1/invited-collections/")
        assert response.status_code == 200
        [row] = [c for c in response.json() if c["code"] == space.code]
        assert row["email_note"] == ""

    def test_no_reader_finds_it_anywhere_in_the_response(self, space, member):
        # Not only the key: a field added later that mirrors the note (as
        # `collection_request_info` mirrors `request_info`) would leak the same
        # text under another name.
        for client in (_client(), _client(member)):
            response = client.get(f"/api/v1/collections/{space.code}/")
            assert "4417" not in response.content.decode()
