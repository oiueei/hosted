"""A collection booked by the hour needs at least one opening block."""

import pytest
from rest_framework import status

from core.models import Collection, User

pytestmark = pytest.mark.django_db

BASE = {"headline": "Workshop", "allowed_thing_types": ["RESERVE_THING"]}
ONE_BLOCK = {"0": [["10:00", "14:00"]]}


def _hourly(code, opening_hours):
    return Collection.objects.create(
        code=code,
        owner=User.objects.get(code="TEST01"),
        headline="X",
        kind="SHED",
        allowed_thing_types=["RESERVE_THING"],
        reservation_unit=Collection.ReservationUnit.HOUR,
        opening_hours=opening_hours,
    )


@pytest.mark.parametrize(
    "hours",
    [
        pytest.param(None, id="no opening_hours at all"),
        pytest.param({}, id="an empty week"),
        pytest.param({"0": [], "3": []}, id="days with no ranges"),
    ],
)
def test_creating_an_hourly_collection_without_a_range_is_refused_with_a_code(
    authenticated_client, hours
):
    body = {**BASE, "reservation_unit": "HOUR"}
    if hours is not None:
        body["opening_hours"] = hours

    resp = authenticated_client.post("/api/v1/collections/", body, format="json")

    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.data["code"] == "opening_hours_required"
    assert not Collection.objects.filter(headline="Workshop").exists()


def test_creating_an_hourly_collection_with_one_range_is_accepted(authenticated_client):
    resp = authenticated_client.post(
        "/api/v1/collections/",
        {**BASE, "reservation_unit": "HOUR", "opening_hours": ONE_BLOCK},
        format="json",
    )

    assert resp.status_code == status.HTTP_201_CREATED


def test_a_day_collection_needs_no_hours(authenticated_client):
    resp = authenticated_client.post(
        "/api/v1/collections/", {**BASE, "reservation_unit": "DAY"}, format="json"
    )

    assert resp.status_code == status.HTTP_201_CREATED


def test_switching_a_day_collection_to_hourly_without_hours_is_refused(authenticated_client):
    coll = Collection.objects.create(
        code="HRS001",
        owner=User.objects.get(code="TEST01"),
        headline="X",
        kind="SHED",
        allowed_thing_types=["RESERVE_THING"],
    )

    resp = authenticated_client.patch(
        f"/api/v1/collections/{coll.code}/", {"reservation_unit": "HOUR"}, format="json"
    )

    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.data["code"] == "opening_hours_required"
    coll.refresh_from_db()
    assert coll.reservation_unit == Collection.ReservationUnit.DAY


def test_switching_to_hourly_with_hours_in_the_same_request_is_accepted(authenticated_client):
    coll = Collection.objects.create(
        code="HRS002",
        owner=User.objects.get(code="TEST01"),
        headline="X",
        kind="SHED",
        allowed_thing_types=["RESERVE_THING"],
    )

    resp = authenticated_client.patch(
        f"/api/v1/collections/{coll.code}/",
        {"reservation_unit": "HOUR", "opening_hours": ONE_BLOCK},
        format="json",
    )

    assert resp.status_code == status.HTTP_200_OK


def test_clearing_the_hours_of_an_hourly_collection_is_refused(authenticated_client):
    coll = _hourly("HRS003", ONE_BLOCK)

    resp = authenticated_client.patch(
        f"/api/v1/collections/{coll.code}/", {"opening_hours": {}}, format="json"
    )

    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert resp.data["code"] == "opening_hours_required"
    coll.refresh_from_db()
    assert coll.opening_hours == ONE_BLOCK


def test_editing_something_else_of_an_hourly_collection_with_hours_is_accepted(
    authenticated_client,
):
    coll = _hourly("HRS004", ONE_BLOCK)

    resp = authenticated_client.patch(
        f"/api/v1/collections/{coll.code}/", {"headline": "Renamed"}, format="json"
    )

    assert resp.status_code == status.HTTP_200_OK


def test_an_existing_hourly_collection_without_hours_can_still_be_paused_and_resumed(
    authenticated_client,
):
    coll = _hourly("HRS005", {})
    url = f"/api/v1/collections/{coll.code}/"

    paused = authenticated_client.patch(url, {"pause_message": "Back soon"}, format="json")
    resumed = authenticated_client.patch(url, {"pause_message": ""}, format="json")
    renamed = authenticated_client.patch(url, {"headline": "Renamed"}, format="json")

    assert paused.status_code == status.HTTP_200_OK
    assert resumed.status_code == status.HTTP_200_OK
    assert renamed.status_code == status.HTTP_200_OK


def test_saving_the_edit_form_of_an_hourly_collection_without_hours_asks_for_them(
    authenticated_client,
):
    """The form sends the unit and the hours with HOUR, so it is judged."""
    coll = _hourly("HRS006", {})
    url = f"/api/v1/collections/{coll.code}/"

    refused = authenticated_client.patch(
        url,
        {"headline": "Renamed", "reservation_unit": "HOUR", "opening_hours": {}},
        format="json",
    )
    saved = authenticated_client.patch(
        url,
        {"headline": "Renamed", "reservation_unit": "HOUR", "opening_hours": ONE_BLOCK},
        format="json",
    )

    assert refused.status_code == status.HTTP_400_BAD_REQUEST
    assert refused.data["code"] == "opening_hours_required"
    assert saved.status_code == status.HTTP_200_OK
