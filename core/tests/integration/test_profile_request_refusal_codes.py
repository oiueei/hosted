"""Refusals of the request, report, profile and booking endpoints carry a ``code``.

The English sentence stays under ``error``; the code is what the app words in the
reader's language (``requestErrors.<code>``).
"""

import pytest

from core.models import BookingPeriod, Collection, Thing


def _refusal(res, status, code):
    assert res.status_code == status, res.data
    assert res.data["code"] == code
    assert isinstance(res.data["error"], str) and res.data["error"]


def _request(client, thing, **body):
    return client.post(f"/api/v1/things/{thing.code}/request/", body, format="json")


@pytest.mark.django_db
def test_asking_for_your_own_thing_is_coded(authenticated_client, thing):
    _refusal(_request(authenticated_client, thing), 400, "cannot_request_own_thing")


@pytest.mark.django_db
def test_asking_for_a_thing_that_is_taken_is_coded(authenticated_client2, collection, thing, user2):
    collection.invites.add(user2)
    Thing.objects.filter(code=thing.code).update(status=Thing.Status.TAKEN)
    _refusal(_request(authenticated_client2, thing), 400, "thing_unavailable")


@pytest.mark.django_db
def test_asking_in_a_paused_collection_is_coded(authenticated_client2, collection, thing, user2):
    collection.invites.add(user2)
    Collection.objects.filter(code=collection.code).update(pause_message="Back in May")
    _refusal(_request(authenticated_client2, thing), 400, "collection_paused")


@pytest.mark.django_db
def test_reporting_your_own_listing_is_coded(authenticated_client, thing):
    res = authenticated_client.post(f"/api/v1/things/{thing.code}/report/")
    _refusal(res, 400, "cannot_report_own_thing")


@pytest.mark.django_db
def test_editing_someone_elses_profile_is_coded(authenticated_client, user2):
    res = authenticated_client.put(f"/api/v1/users/{user2.code}/", {"name": "X"}, format="json")
    _refusal(res, 403, "profile_not_yours")


@pytest.mark.django_db
def test_viewing_a_stranger_profile_is_coded(authenticated_client, user2):
    res = authenticated_client.get(f"/api/v1/users/{user2.code}/")
    _refusal(res, 403, "profile_not_viewable")


@pytest.mark.django_db
def test_cancelling_a_request_that_was_already_answered_is_coded(
    authenticated_client2, thing, user2
):
    booking = BookingPeriod.objects.create(
        thing_code=thing,
        requester_code=user2,
        owner_code=thing.owner,
        status=BookingPeriod.Status.REJECTED,
    )
    res = authenticated_client2.post(f"/api/v1/bookings/{booking.code}/cancel/")
    _refusal(res, 400, "booking_not_pending")


@pytest.mark.django_db
def test_cancelling_someone_elses_request_is_coded(authenticated_client, thing, user, user2):
    booking = BookingPeriod.objects.create(thing_code=thing, requester_code=user2, owner_code=user)
    res = authenticated_client.post(f"/api/v1/bookings/{booking.code}/cancel/")
    _refusal(res, 403, "not_allowed")
