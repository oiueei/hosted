"""The refusals of the collection and invitation endpoints carry a ``code``.

The sentence stays what it was (a client that does not know the code still shows
it, under the same ``error`` / ``detail`` key); the code and its params are what the
app words in the reader's language (``requestErrors.<code>``).
"""

from unittest.mock import patch

import pytest
from django.core.cache import caches
from django.test import override_settings

from core.models import Thing, User
from core.tests.integration.test_invite_quota import QUOTA_SETTINGS

INVITE = "/api/v1/collections/{code}/invite/"
BULK = "/api/v1/collections/{code}/invite/bulk/"
LEAVE = "/api/v1/collections/{code}/leave/"
JOIN = "/api/v1/collections/{code}/join/"
BROADCAST = "/api/v1/collections/{code}/broadcast/"
THINGS = "/api/v1/things/"


def _refusal(res, status, key, code, **params):
    assert res.status_code == status, res.data
    assert res.data["code"] == code
    assert res.data.get("params", {}) == params
    assert isinstance(res.data[key], str) and res.data[key]


@pytest.mark.django_db
def test_inviting_someone_already_invited_is_coded(authenticated_client, collection, user2):
    collection.invites.add(user2)
    res = authenticated_client.post(
        INVITE.format(code=collection.code), {"email": user2.email}, format="json"
    )
    _refusal(res, 400, "detail", "already_invited")


@pytest.mark.django_db
def test_removing_someone_who_is_not_invited_is_coded(authenticated_client, collection, user2):
    res = authenticated_client.delete(
        INVITE.format(code=collection.code), {"user_code": user2.code}, format="json"
    )
    _refusal(res, 400, "error", "not_invited")


@pytest.mark.django_db
def test_the_owner_cannot_leave_and_is_told_with_a_code(authenticated_client, collection):
    res = authenticated_client.post(LEAVE.format(code=collection.code))
    _refusal(res, 400, "detail", "owner_cannot_leave")


@pytest.mark.django_db
def test_joining_a_collection_you_own_is_coded(authenticated_client, collection):
    collection.visibility = "PUBLIC"
    collection.save()
    res = authenticated_client.post(JOIN.format(code=collection.code))
    _refusal(res, 400, "detail", "already_owner")


@pytest.mark.django_db
def test_a_bulk_invite_with_no_emails_is_coded(authenticated_client, collection):
    res = authenticated_client.post(
        BULK.format(code=collection.code), {"invites": []}, format="json"
    )
    _refusal(res, 400, "error", "no_emails_to_invite")


@pytest.mark.django_db
def test_a_bulk_invite_over_the_row_cap_carries_the_cap(authenticated_client, collection):
    rows = [{"email": f"lele{i}@your-domain.test"} for i in range(101)]
    res = authenticated_client.post(
        BULK.format(code=collection.code), {"invites": rows}, format="json"
    )
    _refusal(res, 400, "error", "too_many_invites", max=100)


@pytest.mark.django_db
def test_a_broadcast_with_nobody_to_send_to_is_coded(authenticated_client, collection):
    res = authenticated_client.post(
        BROADCAST.format(code=collection.code), {"message": "Hola"}, format="json"
    )
    _refusal(res, 400, "error", "no_invitees_to_broadcast")


@pytest.mark.django_db
@override_settings(COLLECTION_INVITES_BLOCK=1)
def test_the_member_ceiling_names_the_ceiling(authenticated_client, collection):
    collection.invites.add(User.objects.create(email="lili@your-domain.test"))
    res = authenticated_client.post(
        INVITE.format(code=collection.code), {"email": "lolo@your-domain.test"}, format="json"
    )
    _refusal(res, 400, "error", "members_limit", max=1)


@pytest.mark.django_db
@override_settings(COLLECTION_THINGS_BLOCK=1)
def test_the_things_ceiling_refusal_carries_its_code(collection, user):
    collection.things.add(Thing.objects.create(owner=user, headline="Una"))
    refusal = collection.capacity_violation("things", adding=1)
    assert (refusal.code, refusal.params) == ("things_limit", {"max": 1})


@override_settings(**QUOTA_SETTINGS, INVITE_EMAILS_PER_DAY=1)
@patch("core.services.invitation_service.send_collection_invite_email")
def test_the_daily_invitation_quota_is_coded(_mail, authenticated_client, collection):
    caches["default"].clear()
    first = authenticated_client.post(
        INVITE.format(code=collection.code), {"email": "lili@your-domain.test"}, format="json"
    )
    assert first.status_code == 200

    res = authenticated_client.post(
        INVITE.format(code=collection.code), {"email": "lolo@your-domain.test"}, format="json"
    )
    _refusal(res, 429, "error", "invite_quota_exhausted")
