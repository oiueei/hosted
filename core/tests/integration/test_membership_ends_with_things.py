"""Leaving a group, or being removed from it, takes the person's things there with them.

A thing lives in one collection and its owner always has access to it, so a member who
goes must not leave things behind that nobody can manage from inside. These tests pin the
edges of that rule: exactly the things of *that person* in *that group* go, whatever their
status; a demotion is not a departure; running bookings do not hold a thing back.
"""

from datetime import date, timedelta
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import BookingPeriod, Collection, Event, Thing, User

LEAVE = "/api/v1/collections/{code}/leave/"
INVITE = "/api/v1/collections/{code}/invite/"
CO_OWNERS = "/api/v1/collections/{code}/co-owners/"


def client_for(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


@pytest.fixture
def founder(db):
    return User.objects.create(code="FOUN01", email="lala@your-domain.test", name="Lala")


@pytest.fixture
def member(db):
    return User.objects.create(code="MEMB01", email="lele@your-domain.test", name="Lele")


@pytest.fixture
def other_member(db):
    return User.objects.create(code="MEMB02", email="lili@your-domain.test", name="Lili")


@pytest.fixture
def group(db, founder, member, other_member):
    collection = Collection.objects.create(
        code="GRP001", owner=founder, headline="The street", mode=Collection.Mode.COMMUNITY
    )
    collection.invites.add(member, other_member)
    return collection


@pytest.fixture
def elsewhere(db, founder, member):
    """A second group the same member belongs to."""
    collection = Collection.objects.create(
        code="GRP002", owner=founder, headline="The block", mode=Collection.Mode.COMMUNITY
    )
    collection.invites.add(member)
    return collection


def make_thing(collection, owner, code, status=Thing.Status.ACTIVE, **extra):
    thing = Thing.objects.create(
        code=code,
        owner=owner,
        type=extra.pop("type", "GIFT_THING"),
        headline=f"Thing {code}",
        status=status,
        **extra,
    )
    collection.things.add(thing)
    return thing


def codes(queryset):
    return set(queryset.values_list("code", flat=True))


class TestAMemberWhoLeaves:
    def test_all_their_things_in_that_group_go_whatever_the_status(self, group, member):
        for code, status in [
            ("AAA001", Thing.Status.ACTIVE),
            ("AAA002", Thing.Status.TAKEN),
            ("AAA003", Thing.Status.INACTIVE),
        ]:
            make_thing(group, member, code, status)

        response = client_for(member).post(LEAVE.format(code=group.code), format="json")

        assert response.status_code == 200
        assert response.data["things_deleted"] == 3
        assert not Thing.objects.filter(owner=member).exists()
        assert not group.invites.filter(code=member.code).exists()

    def test_the_things_of_other_members_and_the_founder_stay(
        self, group, founder, member, other_member
    ):
        make_thing(group, member, "MINE01")
        make_thing(group, other_member, "THEIR1")
        make_thing(group, founder, "FOUND1")

        client_for(member).post(LEAVE.format(code=group.code), format="json")

        assert codes(Thing.objects.all()) == {"THEIR1", "FOUND1"}
        assert codes(group.things.all()) == {"THEIR1", "FOUND1"}

    def test_their_things_in_another_group_stay(self, group, elsewhere, member):
        make_thing(group, member, "HERE01")
        make_thing(elsewhere, member, "THERE1")

        response = client_for(member).post(LEAVE.format(code=group.code), format="json")

        assert response.data["things_deleted"] == 1
        assert codes(Thing.objects.filter(owner=member)) == {"THERE1"}
        assert elsewhere.invites.filter(code=member.code).exists()

    def test_the_count_is_zero_when_they_had_nothing_there(self, group, member):
        response = client_for(member).post(LEAVE.format(code=group.code), format="json")

        assert response.status_code == 200
        assert response.data["things_deleted"] == 0

    def test_each_removed_thing_is_logged_with_the_member_as_actor(self, group, member):
        make_thing(group, member, "MINE01")

        client_for(member).post(LEAVE.format(code=group.code), format="json")

        removed = Event.objects.get(kind=Event.Kind.THING_REMOVED)
        assert (removed.thing_code, removed.actor_code) == ("MINE01", member.code)

    def test_a_pending_request_and_a_running_loan_do_not_hold_the_thing_back(
        self, group, founder, member, other_member
    ):
        asked = make_thing(group, member, "ASKED1")
        lent = make_thing(group, member, "LENT01", type="LEND_THING")
        today = date.today()
        pending = BookingPeriod.objects.create(
            thing_code=asked,
            thing_type="GIFT_THING",
            requester_code=other_member,
            requester_email=other_member.email,
            owner_code=member,
            status=BookingPeriod.Status.PENDING,
        )
        running = BookingPeriod.objects.create(
            thing_code=lent,
            thing_type="LEND_THING",
            requester_code=founder,
            requester_email=founder.email,
            owner_code=member,
            start_date=today - timedelta(days=1),
            end_date=today + timedelta(days=5),
            status=BookingPeriod.Status.ACCEPTED,
        )

        response = client_for(member).post(LEAVE.format(code=group.code), format="json")

        assert response.data["things_deleted"] == 2
        assert not Thing.objects.filter(code__in=["ASKED1", "LENT01"]).exists()
        assert not BookingPeriod.objects.filter(code__in=[pending.code, running.code]).exists()

    def test_the_photos_of_a_removed_thing_enter_the_cleanup(
        self, group, member, django_capture_on_commit_callbacks
    ):
        make_thing(
            group,
            member,
            "PHOTO1",
            thumbnail="oiueei/things/cover",
            gallery=["oiueei/things/g1"],
        )

        with patch("core.services.storage.delete") as destroy:
            with django_capture_on_commit_callbacks(execute=True):
                client_for(member).post(LEAVE.format(code=group.code), format="json")

        assert {c.args[0] for c in destroy.call_args_list} == {
            "oiueei/things/cover",
            "oiueei/things/g1",
        }


class TestAMemberWhoIsRemoved:
    def test_the_curator_removing_them_takes_their_things_and_is_named_as_actor(
        self, group, founder, member, other_member
    ):
        make_thing(group, member, "MINE01")
        make_thing(group, member, "MINE02", Thing.Status.INACTIVE)
        make_thing(group, other_member, "THEIR1")

        response = client_for(founder).delete(
            INVITE.format(code=group.code), {"user_code": member.code}, format="json"
        )

        assert response.status_code == 200
        assert response.data["things_deleted"] == 2
        assert codes(Thing.objects.all()) == {"THEIR1"}
        actors = set(
            Event.objects.filter(kind=Event.Kind.THING_REMOVED).values_list("actor_code", flat=True)
        )
        assert actors == {founder.code}

    def test_their_things_in_another_group_stay(self, group, elsewhere, founder, member):
        make_thing(elsewhere, member, "THERE1")

        response = client_for(founder).delete(
            INVITE.format(code=group.code), {"user_code": member.code}, format="json"
        )

        assert response.data["things_deleted"] == 0
        assert codes(Thing.objects.filter(owner=member)) == {"THERE1"}

    def test_removing_a_co_curator_from_a_proprietary_group_deletes_their_catalogue_entries(
        self, founder, member
    ):
        shop = Collection.objects.create(
            code="PROP01", owner=founder, headline="Shed", mode=Collection.Mode.PROPRIETARY
        )
        shop.invites.add(member)
        shop.co_owners.add(member)
        make_thing(shop, member, "CATA01")
        make_thing(shop, founder, "CATA02")

        response = client_for(founder).delete(
            INVITE.format(code=shop.code), {"user_code": member.code}, format="json"
        )

        assert response.data["things_deleted"] == 1
        assert codes(shop.things.all()) == {"CATA02"}
        assert not shop.co_owners.filter(code=member.code).exists()

    def test_demoting_a_co_curator_deletes_nothing(self, founder, member):
        shop = Collection.objects.create(
            code="PROP01", owner=founder, headline="Shed", mode=Collection.Mode.PROPRIETARY
        )
        shop.invites.add(member)
        shop.co_owners.add(member)
        make_thing(shop, member, "CATA01")

        response = client_for(founder).delete(
            CO_OWNERS.format(code=shop.code), {"user_code": member.code}, format="json"
        )

        assert response.status_code == 200
        assert Thing.objects.filter(code="CATA01").exists()
        assert shop.invites.filter(code=member.code).exists()

    def test_cancelling_a_pending_invitation_deletes_nothing(self, group, founder, member):
        make_thing(group, member, "MINE01")
        stranger = User.objects.create(code="STRA01", email="lolo@your-domain.test")

        response = client_for(founder).delete(
            INVITE.format(code=group.code), {"user_code": stranger.code}, format="json"
        )

        assert response.status_code == 400
        assert Thing.objects.filter(code="MINE01").exists()
