"""Every in-app notice about a thing names it by ``thing_headline``.

The inbox renders "{thing}" from that key, so a notice written without it shows a
sentence with a hole. The request and the decision-to-the-requester are pinned in
``test_notifications.py``; these are the three the team and the cancelled party
receive.
"""

from datetime import date, timedelta

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import BookingPeriod, Collection, Thing, User
from core.models.notification import InAppNotification

pytestmark = pytest.mark.django_db
Type = InAppNotification.Type


def client_for(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


@pytest.fixture
def people(db):
    return {
        "owner": User.objects.create(code="NHOWN1", email="lala7@your-domain.test", name="Lala"),
        "curator": User.objects.create(code="NHCUR1", email="lele8@your-domain.test", name="Lele"),
        "member": User.objects.create(code="NHMEM1", email="lili7@your-domain.test", name="Lili"),
    }


@pytest.fixture
def group(people):
    coll = Collection.objects.create(
        code="NHGRP1",
        owner=people["owner"],
        headline="Tools",
        mode=Collection.Mode.PROPRIETARY,
        kind="SHED",
        allowed_thing_types=["RESERVE_THING"],
        reservation_max_days=3,
    )
    coll.invites.add(people["curator"], people["member"])
    coll.co_owners.add(people["curator"])
    return coll


def _next_weekday():
    day = date.today() + timedelta(days=1)
    while day.weekday() > 4:
        day += timedelta(days=1)
    return day


def test_a_decision_tells_the_rest_of_the_team_which_thing(people, group):
    stall = Collection.objects.create(
        code="NHSTL1", owner=people["owner"], headline="Stall", mode=Collection.Mode.PROPRIETARY
    )
    stall.invites.add(people["curator"], people["member"])
    stall.co_owners.add(people["curator"])
    gift = Thing.objects.create(
        code="NHGFT1", type=Thing.Type.GIFT_THING, owner=people["owner"], headline="Books"
    )
    stall.things.add(gift)
    res = client_for(people["member"]).post(
        f"/api/v1/things/{gift.code}/request/", {}, format="json"
    )
    booking = BookingPeriod.objects.get(code=res.data["booking_code"])

    assert (
        client_for(people["curator"]).post(f"/api/v1/bookings/{booking.code}/accept/").status_code
        == 200
    )

    notice = InAppNotification.objects.get(
        user=people["owner"], type=Type.BOOKING_DECIDED, payload__booking_code=booking.code
    )
    assert notice.payload["thing_headline"] == "Books"


def _reserve(people, group):
    room = Thing.objects.create(
        code="NHROM1", type=Thing.Type.RESERVE_THING, owner=people["owner"], headline="Sala"
    )
    group.things.add(room)
    res = client_for(people["member"]).post(
        f"/api/v1/things/{room.code}/request/",
        {"start_date": str(_next_weekday()), "duration_days": 1},
        format="json",
    )
    assert res.status_code == 201, res.data
    return BookingPeriod.objects.get(code=res.data["booking_code"])


def test_a_reservation_made_tells_each_curator_which_thing(people, group):
    _reserve(people, group)

    notices = InAppNotification.objects.filter(type=Type.RESERVATION_MADE)
    assert {n.user_id for n in notices} == {people["owner"].code, people["curator"].code}
    assert {n.payload["thing_headline"] for n in notices} == {"Sala"}


def test_a_cancelled_reservation_tells_everyone_involved_which_thing(people, group):
    booking = _reserve(people, group)
    InAppNotification.objects.all().delete()

    res = client_for(people["curator"]).post(f"/api/v1/bookings/{booking.code}/cancel/")
    assert res.status_code == 200

    notices = InAppNotification.objects.filter(type=Type.RESERVATION_CANCELLED)
    assert {n.user_id for n in notices} == {
        people["member"].code,
        people["owner"].code,
        people["curator"].code,
    }
    assert {n.payload["thing_headline"] for n in notices} == {"Sala"}
