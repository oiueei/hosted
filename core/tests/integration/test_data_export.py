"""
The two download endpoints: who may ask, what comes back, and what a file
that leaves the server is allowed to carry.

The service tests (``unit/test_export_service.py``) own the contents; these own
the HTTP contract — the gate, the attachment, the caching rule and the cap.
"""

import json

import pytest
from django.core.cache import caches
from django.test import override_settings

from core.models import Collection, Thing

pytestmark = pytest.mark.django_db

ACCOUNT_URL = "/api/v1/auth/export/"
COLLECTION_URL = "/api/v1/collections/{code}/export/"


def _payload(response):
    return json.loads(response.content.decode())


class TestAccountExportEndpoint:
    def test_anonymous_gets_nothing(self, api_client):
        assert api_client.get(ACCOUNT_URL).status_code == 401

    def test_the_response_is_a_named_file_no_cache_may_keep(
        self, authenticated_client, user, collection
    ):
        res = authenticated_client.get(ACCOUNT_URL)

        assert res.status_code == 200
        assert res["Content-Type"] == "application/json"
        assert f'filename="oiueei-{user.code}-' in res["Content-Disposition"]
        assert res["Content-Disposition"].startswith("attachment;")
        # A shared proxy holding this would hand somebody their neighbour's file.
        assert res["Cache-Control"] == "private, no-store"

    def test_the_body_is_the_tree_the_manifest_describes(
        self, authenticated_client, user, collection, thing
    ):
        payload = _payload(authenticated_client.get(ACCOUNT_URL))

        assert payload["_manifest"]["user_code"] == user.code
        assert set(payload) - {"_manifest", "_readme", "profile"} == set(
            payload["_manifest"]["counts"]
        )
        assert payload["collections_owned"][0]["code"] == collection.code
        assert payload["things"][0]["code"] == thing.code

    def test_one_persons_export_knows_nothing_about_another(
        self, authenticated_client2, user, user2, collection, thing
    ):
        # user2 shares no group with user here: their file must be empty of them.
        thing.description = "A secret only its owner wrote"
        thing.save()

        res = authenticated_client2.get(ACCOUNT_URL)

        assert res.status_code == 200
        assert user.email.encode() not in res.content
        assert b"A secret only its owner wrote" not in res.content
        assert _payload(res)["_manifest"]["user_code"] == user2.code


class TestCollectionExportEndpoint:
    def test_anonymous_gets_nothing(self, api_client, collection):
        assert api_client.get(COLLECTION_URL.format(code=collection.code)).status_code == 401

    def test_the_owner_gets_the_group(self, authenticated_client, user, collection, thing):
        res = authenticated_client.get(COLLECTION_URL.format(code=collection.code))

        assert res.status_code == 200
        assert f'filename="oiueei-{collection.code}-' in res["Content-Disposition"]
        assert res["Cache-Control"] == "private, no-store"
        payload = _payload(res)
        assert payload["_manifest"]["collection_code"] == collection.code
        assert [t["code"] for t in payload["things"]] == [thing.code]

    def test_a_member_gets_403_not_a_smaller_file(
        self, authenticated_client2, user, user2, collection
    ):
        collection.invites.add(user2)

        res = authenticated_client2.get(COLLECTION_URL.format(code=collection.code))

        # There is no partial export: a member's entitlement is their own copy.
        assert res.status_code == 403
        assert res.data["error"] == "Only the owner can export this collection"

    def test_a_stranger_gets_403_too(self, authenticated_client2, user, collection):
        assert (
            authenticated_client2.get(COLLECTION_URL.format(code=collection.code)).status_code
            == 403
        )

    def test_an_unknown_collection_is_404(self, authenticated_client):
        assert authenticated_client.get(COLLECTION_URL.format(code="NOPE01")).status_code == 404

    def test_the_group_copy_carries_a_members_thing_in_full(
        self, authenticated_client, user, user2, collection
    ):
        collection.invites.add(user2)
        theirs = Thing.objects.create(
            code="MBTH02", owner=user2, headline="Their ladder", description="Four steps"
        )
        collection.things.add(theirs)

        payload = _payload(authenticated_client.get(COLLECTION_URL.format(code=collection.code)))

        member_thing = next(t for t in payload["things"] if t["code"] == "MBTH02")
        assert member_thing["description"] == "Four steps"
        assert member_thing["is_mine"] is False

    def test_demographics_follow_the_collections_mode_not_the_endpoint(
        self, authenticated_client, user, user2, collection
    ):
        collection.invites.add(user2)
        user2.postal_code = "48001"
        user2.save()

        private = authenticated_client.get(COLLECTION_URL.format(code=collection.code))
        assert b"postal_code" not in private.content

        collection.mode = Collection.Mode.COMMUNITY
        collection.save()
        community = authenticated_client.get(COLLECTION_URL.format(code=collection.code))
        assert _payload(community)["members"][0]["postal_code"] == "48001"


RATELIMIT_SETTINGS = {
    "RATELIMIT_ENABLE": True,
    "CACHES": {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "ratelimit-export-test",
        }
    },
}


class TestExportRateLimit:
    """Ten a day, per user. Building an export is the heaviest read in the app,
    and a cap is what keeps "download my data" from being a way to walk a server
    out one file at a time."""

    @override_settings(**RATELIMIT_SETTINGS)
    def test_the_eleventh_account_export_of_the_day_is_refused(self, authenticated_client):
        caches["default"].clear()

        statuses = [authenticated_client.get(ACCOUNT_URL).status_code for _ in range(11)]

        assert statuses[0] == 200
        assert statuses[-1] == 429  # not 403 — see core.exceptions.api_exception_handler

    @override_settings(**RATELIMIT_SETTINGS)
    def test_the_collection_copy_is_capped_too(self, authenticated_client, collection):
        caches["default"].clear()
        url = COLLECTION_URL.format(code=collection.code)

        statuses = [authenticated_client.get(url).status_code for _ in range(11)]

        assert statuses[0] == 200
        assert statuses[-1] == 429
