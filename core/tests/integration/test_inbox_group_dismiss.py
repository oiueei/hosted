"""``DELETE /api/v1/inbox/?group=bookings`` — dismissing the team's notices in one go.

Home's inbox fills fast for whoever runs a busy group: a request, then a
"confirmed" for each decision, a reservation per booking. Past three, the inbox
folds them into one summary card (``InboxNotifications``), and the card's X has to
dismiss all of them at once — where ``DELETE /inbox/{code}/`` only ever took one.

What it must never take is anything else. The group is the notices that are *for
whoever manages* a request or reservation; a copy for the person who asked, or who
held the reservation, links to their own page and stays. The table of cases lives in
``frontend/src/test/inboxGroupParity.json``, which the browser's copy of the rule
reads too, so the two cannot drift.
"""

import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from core.models import BookingPeriod, Collection, Thing, User
from core.models.notification import InAppNotification

pytestmark = pytest.mark.django_db

URL = "/api/v1/inbox/"
GROUP = "?group=bookings"
ROWS = json.loads(
    (
        Path(__file__).resolve().parents[3] / "frontend" / "src" / "test" / "inboxGroupParity.json"
    ).read_text(encoding="utf-8")
)["rows"]


def client_for(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}")
    return client


def inbox_of(user):
    return list(InAppNotification.objects.filter(user=user).values_list("type", flat=True))


@pytest.fixture
def lala(db):
    return User.objects.create(code="LALA01", email="lala@test.com", name="Lala")


@pytest.fixture
def lele(db):
    return User.objects.create(code="LELE01", email="lele@test.com", name="Lele")


class TestTheGroupFollowsTheSharedTable:
    @pytest.mark.parametrize("row", ROWS, ids=[row["what"] for row in ROWS])
    def test_a_notice_is_dismissed_exactly_when_the_table_says_it_is_for_the_team(self, lala, row):
        InAppNotification.objects.create(user=lala, type=row["type"], payload=row["payload"])

        res = client_for(lala).delete(URL + GROUP)

        assert res.status_code == 204
        still_there = InAppNotification.objects.filter(user=lala).exists()
        assert still_there is not row["grouped"]


class TestWhatTheGroupTakes:
    def test_only_the_callers_own_notices(self, lala, lele):
        for user in (lala, lele):
            InAppNotification.objects.create(
                user=user, type="BOOKING_REQUESTED", payload={"collection_code": "COL001"}
            )

        client_for(lala).delete(URL + GROUP)

        assert inbox_of(lala) == []
        # Somebody else's inbox is none of this call's business.
        assert inbox_of(lele) == ["BOOKING_REQUESTED"]

    def test_with_a_collection_only_the_ones_born_in_it(self, lala):
        for collection_code in ("COL001", "COL002", ""):
            InAppNotification.objects.create(
                user=lala,
                type="BOOKING_REQUESTED",
                payload={"collection_code": collection_code, "thing_code": "THG001"},
            )

        client_for(lala).delete(URL + GROUP + "&collection=COL001")

        left = InAppNotification.objects.filter(user=lala).values_list(
            "payload__collection_code", flat=True
        )
        assert sorted(left) == ["", "COL002"]

    def test_everything_else_in_the_inbox_stays_next_to_it(self, lala):
        InAppNotification.objects.create(user=lala, type="BOOKING_REQUESTED", payload={})
        InAppNotification.objects.create(user=lala, type="FAQ_QUESTION", payload={})
        InAppNotification.objects.create(user=lala, type="BROADCAST", payload={})

        client_for(lala).delete(URL + GROUP)

        assert sorted(inbox_of(lala)) == ["BROADCAST", "FAQ_QUESTION"]

    def test_a_group_nobody_has_heard_of_is_a_400_and_deletes_nothing(self, lala):
        InAppNotification.objects.create(user=lala, type="BOOKING_REQUESTED", payload={})

        res = client_for(lala).delete(URL + "?group=everything")

        assert res.status_code == 400
        assert inbox_of(lala) == ["BOOKING_REQUESTED"]

    def test_without_a_session_it_is_a_401_and_deletes_nothing(self, lala):
        InAppNotification.objects.create(user=lala, type="BOOKING_REQUESTED", payload={})

        res = APIClient().delete(URL + GROUP)

        assert res.status_code == 401
        assert inbox_of(lala) == ["BOOKING_REQUESTED"]


# --- the real producers ------------------------------------------------------
# The table above is written by hand from what `booking_service` produces today.
# These run the producers themselves, so a payload that changes shape fails here
# even when the table was not edited.


def _next_weekday(weekday):
    day = date.today() + timedelta(days=1)
    while day.weekday() != weekday:
        day += timedelta(days=1)
    return day


@pytest.fixture
def team(db, lala, lele):
    """A reservations collection run by Lala and Lele (co-curator), and a member."""
    member = User.objects.create(code="MEMB01", email="member@test.com", name="Lili")
    collection = Collection.objects.create(
        code="RSVC01",
        owner=lala,
        headline="Spaces",
        status="ACTIVE",
        mode=Collection.Mode.PROPRIETARY,
        allowed_thing_types=["RESERVE_THING"],
        reservation_max_days=3,
        rental_weekdays=[0, 1, 2, 3, 4],
    )
    collection.invites.add(lele, member)
    collection.co_owners.add(lele)
    thing = Thing.objects.create(
        code="RSVT01", type=Thing.Type.RESERVE_THING, owner=lala, headline="Sala"
    )
    collection.things.add(thing)
    return {"member": member, "collection": collection, "thing": thing}


def _reserve(team):
    res = client_for(team["member"]).post(
        f"/api/v1/things/{team['thing'].code}/request/",
        {
            "start_date": str(_next_weekday(0)),
            "duration_days": 1,
            "collection_code": team["collection"].code,
        },
        format="json",
    )
    assert res.status_code == 201, res.data
    return BookingPeriod.objects.get(code=res.data["booking_code"])


def _cancel(who, booking):
    res = client_for(who).post(f"/api/v1/bookings/{booking.code}/cancel/")
    assert res.status_code == 200, res.data


class TestAgainstWhatTheServiceReallyWrites:
    def test_a_manager_who_cancels_clears_the_teams_notices_and_leaves_the_members(
        self, team, lala, lele
    ):
        booking = _reserve(team)
        _cancel(lala, booking)
        member = team["member"]
        # Lele: the reservation, then the cancellation told to a manager who didn't
        # cancel. Lala: the reservation, then her own record of cancelling Lili's.
        assert sorted(inbox_of(lele)) == ["RESERVATION_CANCELLED", "RESERVATION_MADE"]
        assert sorted(inbox_of(lala)) == ["RESERVATION_CANCELLED", "RESERVATION_MADE"]
        assert inbox_of(member) == ["RESERVATION_CANCELLED"]

        for manager in (lele, lala):
            client_for(manager).delete(URL + GROUP)
        client_for(member).delete(URL + GROUP)

        assert inbox_of(lele) == []
        assert inbox_of(lala) == []
        # Lili was told her reservation was cancelled: that notice is hers, and
        # it is not for the team's page.
        assert inbox_of(member) == ["RESERVATION_CANCELLED"]

    def test_a_member_who_cancels_keeps_their_own_record_and_the_team_loses_theirs(
        self, team, lala, lele
    ):
        booking = _reserve(team)
        _cancel(team["member"], booking)

        for who in (lala, lele, team["member"]):
            client_for(who).delete(URL + GROUP)

        assert inbox_of(lala) == []
        assert inbox_of(lele) == []
        assert inbox_of(team["member"]) == ["RESERVATION_CANCELLED"]

    def test_a_request_and_a_decision_are_the_teams_and_the_requesters_answer_is_not(
        self, lala, lele
    ):
        member = User.objects.create(code="MEMB02", email="m2@test.com", name="Lili")
        collection = Collection.objects.create(
            code="HOLD01", owner=lala, headline="Tools", mode=Collection.Mode.PROPRIETARY
        )
        collection.invites.add(lele, member)
        collection.co_owners.add(lele)
        gift = Thing.objects.create(
            code="GIFT01", type=Thing.Type.GIFT_THING, owner=lala, headline="Books"
        )
        collection.things.add(gift)
        res = client_for(member).post(f"/api/v1/things/{gift.code}/request/", {}, format="json")
        assert res.status_code == 201, res.data
        booking_code = res.data["booking_code"]
        res = client_for(lele).post(f"/api/v1/bookings/{booking_code}/accept/")
        assert res.status_code == 200, res.data
        # Lala hears Lele's decision (the request was cleared when it was settled);
        # Lele, who pressed accept, gets no record of it.
        assert inbox_of(lala) == ["BOOKING_DECIDED"]
        assert inbox_of(lele) == []
        assert inbox_of(member) == ["BOOKING_ACCEPTED"]

        for who in (lala, lele, member):
            client_for(who).delete(URL + GROUP)

        assert inbox_of(lala) == []
        assert inbox_of(lele) == []
        assert inbox_of(member) == ["BOOKING_ACCEPTED"]
