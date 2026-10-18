"""The refusals of the thing and FAQ endpoints carry a ``code``.

The English sentence stays under the key it always had; the code (and the params its
sentence interpolates) is what the app words in the reader's language.
"""

import pytest
from django.test import override_settings

from core.models import Thing

BULK = "/api/v1/collections/{code}/things/bulk/"


def _refusal(res, status, code, key="error", **params):
    assert res.status_code == status, res.data
    assert res.data["code"] == code
    assert res.data.get("params", {}) == params
    assert isinstance(res.data[key], str) and res.data[key]


@pytest.mark.django_db
def test_activating_a_thing_that_is_not_hidden_is_coded(authenticated_client, thing):
    res = authenticated_client.post(f"/api/v1/things/{thing.code}/activate/")
    _refusal(res, 400, "thing_not_inactive")


@pytest.mark.django_db
def test_hiding_a_thing_that_is_not_active_is_coded(authenticated_client, thing):
    Thing.objects.filter(code=thing.code).update(status=Thing.Status.INACTIVE)
    res = authenticated_client.post(f"/api/v1/things/{thing.code}/hide/")
    _refusal(res, 400, "thing_not_active")


@pytest.mark.django_db
def test_a_bulk_import_by_someone_who_cannot_add_is_coded(authenticated_client2, collection):
    res = authenticated_client2.post(
        BULK.format(code=collection.code), {"rows": [{"headline": "A"}]}, format="json"
    )
    _refusal(res, 403, "cannot_add_things")


@pytest.mark.django_db
def test_a_bulk_import_with_no_rows_is_coded(authenticated_client, collection):
    res = authenticated_client.post(BULK.format(code=collection.code), {"rows": []}, format="json")
    _refusal(res, 400, "no_rows_to_import")


@pytest.mark.django_db
def test_a_bulk_import_over_the_row_cap_carries_the_cap(authenticated_client, collection):
    rows = [{"headline": f"Row {i}"} for i in range(101)]
    res = authenticated_client.post(
        BULK.format(code=collection.code), {"rows": rows}, format="json"
    )
    _refusal(res, 400, "too_many_rows", max=100)


@pytest.mark.django_db
@override_settings(COLLECTION_THINGS_BLOCK=1)
def test_a_bulk_import_over_the_ceiling_carries_the_ceiling(
    authenticated_client, collection, thing
):
    res = authenticated_client.post(
        BULK.format(code=collection.code), {"rows": [{"headline": "One more"}]}, format="json"
    )
    _refusal(res, 400, "things_limit", max=1)


@pytest.mark.django_db
@override_settings(COLLECTION_THINGS_BLOCK=1)
def test_creating_one_thing_over_the_ceiling_lifts_the_code_and_the_ceiling(
    authenticated_client, collection, thing
):
    res = authenticated_client.post(
        "/api/v1/things/",
        {"headline": "Over", "type": "GIFT_THING", "collection_code": collection.code},
        format="json",
    )
    assert res.status_code == 400
    assert res.data["code"] == "things_limit"
    assert res.data["params"] == {"max": 1}
    assert res.data["collection_code"]


@pytest.mark.django_db
def test_a_manager_asking_about_their_own_thing_is_coded(authenticated_client, thing):
    res = authenticated_client.post(
        f"/api/v1/things/{thing.code}/faq/", {"question": "Is it mine?"}, format="json"
    )
    _refusal(res, 400, "manager_cannot_ask")


@pytest.mark.django_db
def test_a_non_manager_answering_is_coded(authenticated_client2, faq):
    res = authenticated_client2.post(
        f"/api/v1/faq/{faq.code}/answer/", {"answer": "Yes"}, format="json"
    )
    _refusal(res, 403, "only_managers_answer")


@pytest.mark.django_db
def test_a_non_manager_changing_visibility_is_coded(authenticated_client2, faq):
    res = authenticated_client2.post(f"/api/v1/faq/{faq.code}/hide/")
    _refusal(res, 403, "only_managers_change_visibility")


@pytest.mark.django_db
def test_a_hidden_question_is_not_found_for_someone_else(api_client, user, user2, faq, collection):
    from rest_framework_simplejwt.tokens import RefreshToken

    third = type(user).objects.create(code="TEST03", email="lili3@your-domain.test", name="Third")
    collection.invites.add(third)
    faq.is_visible = False
    faq.save()
    api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(third).access_token}")
    res = api_client.get(f"/api/v1/faq/{faq.code}/")
    _refusal(res, 404, "faq_not_found")
