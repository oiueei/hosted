"""``GET /api/v1/auth/me/`` says whether "Requests to me" has anything to show.

The account menu offered the page to everybody, so somebody who had only joined a
group saw a link to a page that could never hold a request. The answer is the reach
of the owner-bookings page read as a yes/no: **a thing of their own** (a member of a
COMMUNITY collection who contributed one gets requests on it), or **a PROPRIETARY
collection they run**, as founder or co-curator. The browser cannot know either, so
the server says, and the menu asks when it opens.
"""

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import Collection, Thing, User

pytestmark = pytest.mark.django_db


def me(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    res = client.get("/api/v1/auth/me/")
    assert res.status_code == 200
    return res.data


@pytest.fixture
def founder(db):
    return User.objects.create(code="FNDR01", email="founder@test.com", name="Lala")


@pytest.fixture
def newcomer(db):
    return User.objects.create(code="NEWC01", email="newcomer@test.com", name="Lili")


def group(owner, code, mode):
    return Collection.objects.create(code=code, owner=owner, headline=code, mode=mode)


class TestWhoHasRequestsToReceive:
    def test_somebody_who_only_joined_a_group_has_none(self, founder, newcomer):
        community = group(founder, "COMM01", Collection.Mode.COMMUNITY)
        proprietary = group(founder, "PROP01", Collection.Mode.PROPRIETARY)
        community.invites.add(newcomer)
        proprietary.invites.add(newcomer)

        assert me(newcomer)["receives_requests"] is False

    def test_somebody_who_owns_a_thing_has_some_even_in_a_community_group(self, founder, newcomer):
        community = group(founder, "COMM01", Collection.Mode.COMMUNITY)
        community.invites.add(newcomer)
        thing = Thing.objects.create(
            code="THG001", type=Thing.Type.LEND_THING, owner=newcomer, headline="A drill"
        )
        community.things.add(thing)

        assert me(newcomer)["receives_requests"] is True

    def test_the_founder_of_a_proprietary_collection_has_some_before_any_thing(self, founder):
        group(founder, "PROP01", Collection.Mode.PROPRIETARY)

        assert me(founder)["receives_requests"] is True

    def test_a_co_curator_of_a_proprietary_collection_has_some_owning_nothing(
        self, founder, newcomer
    ):
        proprietary = group(founder, "PROP01", Collection.Mode.PROPRIETARY)
        proprietary.invites.add(newcomer)
        proprietary.co_owners.add(newcomer)

        assert me(newcomer)["receives_requests"] is True

    def test_running_a_community_collection_is_not_enough_on_its_own(self, founder, newcomer):
        # In a COMMUNITY collection each member answers for their own things; whoever
        # founded it, or helps run it, receives requests only on things they own.
        community = group(founder, "COMM01", Collection.Mode.COMMUNITY)
        community.invites.add(newcomer)
        community.co_owners.add(newcomer)

        assert me(founder)["receives_requests"] is False
        assert me(newcomer)["receives_requests"] is False

    def test_what_somebody_else_has_is_not_theirs(self, founder, newcomer):
        group(founder, "PROP01", Collection.Mode.PROPRIETARY)
        Thing.objects.create(
            code="THG001", type=Thing.Type.GIFT_THING, owner=founder, headline="Books"
        )

        assert me(newcomer)["receives_requests"] is False
