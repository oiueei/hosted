"""Asking for any thing is being part of the group that lists it.

Only a reservation used to demand membership. A signed-in reader of a PUBLIC
group could ask for a loan, a rental, a gift or a sale without being a member,
so whoever ran the thing could not open their profile and they never got the
group's summary — while someone who arrived without a session ended up a member.
"""

from datetime import date, timedelta

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import BookingPeriod, Collection, Thing, User

pytestmark = pytest.mark.django_db

NEEDS_A_SEAT = "You need to be a member of this group to ask for this."


def client_for(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


def make_user(code, name):
    return User.objects.create(code=code, email=f"{name.lower()}@test.com", name=name)


@pytest.fixture
def founder():
    return make_user("MBFND1", "Lala")


@pytest.fixture
def contributor():
    return make_user("MBCON1", "Lele")


@pytest.fixture
def stranger():
    return make_user("MBSTR1", "Lili")


@pytest.fixture
def group(founder, contributor):
    """A PUBLIC COMMUNITY group: Lele contributes things, Lala only founded it."""
    collection = Collection.objects.create(
        code="MBCOL1",
        owner=founder,
        headline="Barrio",
        mode=Collection.Mode.COMMUNITY,
        visibility=Collection.Visibility.PUBLIC,
    )
    collection.invites.add(contributor)
    return collection


def thing_in(collection, owner, kind, code):
    thing = Thing.objects.create(code=code, owner=owner, headline=code, type=kind)
    collection.things.add(thing)
    return thing


def ask(user, thing, **body):
    if thing.type in ("LEND_THING", "RENT_THING"):
        body.setdefault("start_date", str(date.today() + timedelta(days=1)))
        body.setdefault("end_date", str(date.today() + timedelta(days=3)))
    return client_for(user).post(f"/api/v1/things/{thing.code}/request/", body, format="json")


KINDS = ["LEND_THING", "RENT_THING", "GIFT_THING", "SELL_THING"]


class TestSomeoneWithNoSeat:
    @pytest.mark.parametrize("kind", KINDS)
    def test_a_reader_of_a_public_group_is_not_a_member_and_asks_nothing(
        self, group, contributor, stranger, kind
    ):
        thing = thing_in(group, contributor, kind, "MBTH01")

        response = ask(stranger, thing)

        assert response.status_code == 403
        assert response.data["code"] == "not_a_member"
        assert response.data["error"] == NEEDS_A_SEAT
        assert BookingPeriod.objects.count() == 0
        thing.refresh_from_db()
        assert thing.status == Thing.Status.ACTIVE

    def test_being_in_an_inactive_group_is_no_seat(self, group, contributor, stranger):
        """The thing sits in two groups: one the reader belongs to but is switched
        off, and the public one they are only reading."""
        closed = Collection.objects.create(
            code="MBCOL2", owner=contributor, headline="Old", status=Collection.Status.INACTIVE
        )
        closed.invites.add(stranger)
        thing = thing_in(group, contributor, "GIFT_THING", "MBTH02")
        closed.things.add(thing)

        assert ask(stranger, thing).status_code == 403


class TestSomeoneWithASeat:
    @pytest.mark.parametrize("kind", KINDS)
    def test_a_member_asks(self, group, contributor, stranger, kind):
        group.invites.add(stranger)
        thing = thing_in(group, contributor, kind, "MBTH03")

        assert ask(stranger, thing).status_code == 201

    def test_whoever_founded_a_community_group_may_ask_for_a_members_thing(
        self, group, founder, contributor
    ):
        """The founder is not in `invites` — they are the owner."""
        assert not group.invites.filter(code=founder.code).exists()
        thing = thing_in(group, contributor, "GIFT_THING", "MBTH04")

        assert ask(founder, thing).status_code == 201

    def test_a_co_curator_may_ask_too(self, group, contributor):
        # In a PROPRIETARY group a co-curator is in `invites` as well, but the
        # seat must not depend on that: the curator rule stands on its own.
        co = make_user("MBCOC1", "Lolo")
        group.co_owners.add(co)
        thing = thing_in(group, contributor, "GIFT_THING", "MBTH05")

        assert ask(co, thing).status_code == 201

    def test_one_group_of_several_is_enough(self, group, contributor, stranger):
        other = Collection.objects.create(code="MBCOL3", owner=contributor, headline="Otro")
        other.invites.add(stranger)
        thing = thing_in(group, contributor, "GIFT_THING", "MBTH06")
        other.things.add(thing)

        assert ask(stranger, thing).status_code == 201


class TestAReservationIsUnchanged:
    def test_it_still_asks_for_membership_in_its_own_words(self, founder, stranger):
        rooms = Collection.objects.create(
            code="MBCOL4",
            owner=founder,
            headline="Salas",
            allowed_thing_types=["RESERVE_THING"],
            visibility=Collection.Visibility.PUBLIC,
        )
        room = thing_in(rooms, founder, "RESERVE_THING", "MBTH07")

        response = ask(
            stranger, room, start_date=str(date.today() + timedelta(days=1)), duration_days=1
        )

        assert response.status_code == 403
        assert response.data["code"] == "not_a_member"
        assert response.data["error"] == "You need to be a member of this group to reserve."
