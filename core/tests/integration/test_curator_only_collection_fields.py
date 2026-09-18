"""Collection fields not every reader of the collection may have.

`CollectionSerializer` answers every reader of a collection — its members and,
on a PUBLIC one, anybody at all. Some of what it holds is written for a
narrower audience than that: the email note for the curators alone (it goes
out by email; only their edit form reads it back), the welcome document for
the group. These tests ask the API as each kind of reader, so a field that
starts travelling to the wrong one fails here rather than in a screenshot
somebody shares.
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


DOC = "oiueei/documents/rules"


class TestTheWelcomeDocument:
    """The group's rules, mailed to each member on joining — for the group,
    not for whoever can read a PUBLIC collection's page. Unlike the email
    note, members keep it: the document is addressed to them."""

    @pytest.fixture
    def with_doc(self, space):
        space.welcome_doc = DOC
        space.save(update_fields=["welcome_doc"])
        return space

    @pytest.fixture
    def outsider(self, db):
        return User.objects.create(code="OUTS01", email="outsider@example.com", name="Out")

    def test_an_anonymous_reader_gets_neither_key_nor_link(self, with_doc):
        data = _read(_client(), with_doc)
        assert data["welcome_doc"] == ""
        assert data["welcome_doc_url"] is None

    def test_a_signed_in_reader_outside_the_group_gets_nothing_either(self, with_doc, outsider):
        data = _read(_client(outsider), with_doc)
        assert data["welcome_doc"] == ""
        assert data["welcome_doc_url"] is None

    def test_a_member_reads_the_rules_they_were_sent(self, with_doc, member):
        data = _read(_client(member), with_doc)
        assert data["welcome_doc"] == DOC
        assert data["welcome_doc_url"].endswith(f"/{DOC}")

    @pytest.mark.parametrize("who", ["user", "co_owner"])
    def test_the_curators_read_it_back_to_edit_it(self, with_doc, who, request):
        data = _read(_client(request.getfixturevalue(who)), with_doc)
        assert data["welcome_doc"] == DOC
        assert data["welcome_doc_url"].endswith(f"/{DOC}")

    def test_the_document_url_is_nowhere_in_an_outsiders_response(self, with_doc, outsider):
        for client in (_client(), _client(outsider)):
            response = client.get(f"/api/v1/collections/{with_doc.code}/")
            assert DOC not in response.content.decode()
