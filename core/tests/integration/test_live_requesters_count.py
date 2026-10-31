"""The thing says, to whoever may delete it, how many people deleting it would email.

The page that asks "delete this?" shows the number, so it is the number of emails that go:
the people with a pending or accepted request, one each, the reader left out. Only for
someone who may delete the thing (``Thing.can_delete``, the endpoint's own rule), and never
in a list.
"""

from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import BookingPeriod, Collection, Thing, User
from core.tests.factories import (
    BookingPeriodFactory,
    CollectionFactory,
    ThingFactory,
    ThingTransferFactory,
)

LEND, RENT = "LEND_THING", "RENT_THING"


def client_for(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


def _user(code, name):
    return User.objects.create(code=code, email=f"{name.lower()}@your-domain.test", name=name)


@pytest.fixture
def world(db):
    owner, curator, lili, lolo, outsider = (
        _user("OWNR01", "Lala"),
        _user("CURA01", "Lele"),
        _user("ASK001", "Lili"),
        _user("ASK002", "Lolo"),
        _user("OUTS01", "Lulu"),
    )
    group = CollectionFactory(
        owner=owner, mode=Collection.Mode.PROPRIETARY, allowed_thing_types=[LEND, RENT]
    )
    group.invites.add(curator, lili, lolo, outsider)
    group.co_owners.add(curator)
    thing = ThingFactory(owner=owner, type=LEND, headline="Drill")
    group.things.add(thing)
    return {
        "group": group,
        "thing": thing,
        "owner": owner,
        "curator": curator,
        "lili": lili,
        "lolo": lolo,
        "outsider": outsider,
    }


def ask(world, who, *, start=3, end=6, status_=BookingPeriod.Status.PENDING):
    today = timezone.localdate()
    return BookingPeriodFactory(
        thing_code=world["thing"],
        requester_code=world[who],
        owner_code=world["owner"],
        thing_type=LEND,
        status=status_,
        start_date=today + timedelta(days=start),
        end_date=today + timedelta(days=end),
    )


def count_for(world, who, thing=None):
    thing = thing or world["thing"]
    res = client_for(world[who]).get(
        f"/api/v1/things/{thing.code}/?collection={world['group'].code}"
    )
    assert res.status_code == 200
    return res.data["live_requesters_count"]


def test_nobody_asked_is_zero(world):
    assert count_for(world, "owner") == 0


def test_it_counts_each_person_once_whatever_they_asked(world):
    ask(world, "lili")
    ask(world, "lili", start=10, end=12)
    ask(world, "lolo", status_=BookingPeriod.Status.ACCEPTED)

    assert count_for(world, "owner") == 2


def test_what_is_over_or_refused_does_not_count(world):
    ask(world, "lili", start=-30, end=-20, status_=BookingPeriod.Status.ACCEPTED)
    ask(world, "lolo", status_=BookingPeriod.Status.REJECTED)

    assert count_for(world, "owner") == 0


def test_the_reader_is_left_out_as_they_are_from_the_emails(world):
    ask(world, "lili")
    ask(world, "curator")

    assert count_for(world, "curator") == 1
    assert count_for(world, "owner") == 2


def test_it_is_the_number_of_emails_that_go(world, django_capture_on_commit_callbacks):
    ask(world, "lili")
    ask(world, "lolo", status_=BookingPeriod.Status.ACCEPTED)
    ask(world, "curator")
    shown = count_for(world, "curator")
    mail.outbox.clear()

    with django_capture_on_commit_callbacks(execute=True):
        client_for(world["curator"]).delete(f"/api/v1/things/{world['thing'].code}/")

    assert shown == len(mail.outbox) == 2


def test_someone_who_may_not_delete_it_is_told_nothing(world):
    ask(world, "lili")

    assert count_for(world, "outsider") is None
    assert count_for(world, "lili") is None


def test_an_anonymous_reader_is_told_nothing(world):
    world["group"].visibility = Collection.Visibility.PUBLIC
    world["group"].save()

    res = APIClient().get(f"/api/v1/things/{world['thing'].code}/?collection={world['group'].code}")

    assert res.status_code == 200
    assert res.data["live_requesters_count"] is None


def test_it_is_not_in_a_list(world):
    ask(world, "lili")

    res = client_for(world["owner"]).get("/api/v1/things/")

    assert res.status_code == 200
    rows = res.data["results"] if isinstance(res.data, dict) else res.data
    assert rows and all(row["live_requesters_count"] is None for row in rows)


class TestWhoMayDelete:
    """``Thing.can_delete`` is the rule the endpoint and the count share."""

    def test_the_collection_owner_and_a_proprietary_co_curator(self, world):
        thing = Thing.objects.get(code=world["thing"].code)

        assert thing.can_delete("OWNR01")
        assert thing.can_delete("CURA01")
        assert not thing.can_delete("ASK001")

    def test_a_thing_owner_loses_it_once_the_thing_has_changed_hands_in_a_community(self, world):
        community = CollectionFactory(owner=world["owner"], mode=Collection.Mode.COMMUNITY)
        community.invites.add(world["lili"], world["lolo"])
        thing = ThingFactory(owner=world["lili"], type=LEND)
        community.things.add(thing)
        assert Thing.objects.get(code=thing.code).can_delete("ASK001")

        ThingTransferFactory(thing=thing, from_user=world["lili"], to_user=world["lolo"])

        assert not Thing.objects.get(code=thing.code).can_delete("ASK001")

    def test_a_network_dinamizador_keeps_it_for_their_own_things_only(self, world):
        network = CollectionFactory(owner=world["owner"], mode=Collection.Mode.NETWORK)
        network.invites.add(world["curator"], world["lili"])
        network.co_owners.add(world["curator"], world["lili"])
        mine = ThingFactory(owner=world["curator"], type=LEND)
        network.things.add(mine)
        ThingTransferFactory(thing=mine, from_user=world["curator"], to_user=world["lolo"])
        mine = Thing.objects.get(code=mine.code)

        assert mine.can_delete("CURA01")
        assert not mine.can_delete("ASK001")
        assert mine.can_delete("OWNR01")
