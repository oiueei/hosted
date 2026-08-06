"""
A JSON *array* body must never 500 an endpoint that expects an object.

DRF parses `[{"email": "a@b.com"}]` into a `list`, which has no `.get` — so a
view reading `request.data.get(...)` before any serializer has run raises
`AttributeError` and answers 500 where it owes a 400. Every endpoint here reads
the body that way, and `core.views._helpers.body_dict` is what keeps them honest:
a non-object body is "no fields given" and falls through to the view's own
validation, which already has the right message for an empty request.

These are contract tests, not smoke tests: each asserts the specific 4xx the
endpoint owes, so a regression that turns one back into a 500 — or into the
wrong 4xx — fails here. `ThingBulkCreateView` and the auth doors are covered
too even though they already guarded correctly; the point is that the whole
family holds, not that today's broken members were patched.
"""

import pytest

from core.models import Thing

ARRAY_BODY = [{"email": "someone@example.com"}]


@pytest.mark.django_db
def test_bulk_invite_answers_400_not_500(authenticated_client, collection):
    """Regression: the capacity check jumped ahead of this view's own guard."""
    res = authenticated_client.post(
        f"/api/v1/collections/{collection.code}/invite/bulk/", ARRAY_BODY, format="json"
    )

    assert res.status_code == 400
    assert "No emails to invite." in str(res.data)


@pytest.mark.django_db
def test_share_link_answers_a_normal_response_not_500(authenticated_client, collection):
    """`rotate` is absent from an array body, so this behaves as a plain POST."""
    res = authenticated_client.post(
        f"/api/v1/collections/{collection.code}/share-link/", ARRAY_BODY, format="json"
    )

    assert res.status_code == 200
    assert res.data["share_token"]


@pytest.mark.django_db
def test_upload_signature_answers_a_normal_response_not_500(authenticated_client, settings):
    """No `kind`/`folder` in an array body ⇒ the image defaults, not a crash."""
    res = authenticated_client.post("/api/v1/upload/signature/", ARRAY_BODY, format="json")

    assert res.status_code == 200
    assert res.data["folder"] == "oiueei/users"
    assert res.data["resource_type"] == "image"


@pytest.mark.django_db
def test_thing_request_answers_400_not_500(api_client, user2, collection, thing):
    """The read of `collection_code` sits before any serializer on this path."""
    collection.invites.add(user2)
    api_client.force_authenticate(user=user2)

    res = api_client.post(f"/api/v1/things/{thing.code}/request/", ARRAY_BODY, format="json")

    # A GIFT thing needs no fields, so the request is simply accepted with no
    # collection context — what matters is that it resolved instead of crashing.
    assert res.status_code == 201


@pytest.mark.django_db
def test_thing_bulk_create_answers_400_not_500(authenticated_client, collection):
    res = authenticated_client.post(
        f"/api/v1/collections/{collection.code}/things/bulk/", ARRAY_BODY, format="json"
    )

    assert res.status_code == 400
    assert Thing.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize("path", ["/api/v1/auth/pop-in/", "/api/v1/auth/request-link/"])
def test_the_public_auth_doors_answer_400_not_500(api_client, path):
    """The two unauthenticated doors — the ones a stranger can reach."""
    res = api_client.post(path, ARRAY_BODY, format="json")

    assert res.status_code == 400


@pytest.mark.django_db
def test_logout_answers_200_not_500(api_client):
    """The third public door, and the one with no serializer to catch the body.

    `pop-in` and `request-link` both validate through `RequestLinkSerializer`
    before reading anything, so a list body 400s there on its own. Logout reads
    the body directly — it authenticates nobody and takes no CSRF token — so the
    `.get` was reached and answered 500. Logout must never fail: no refresh token
    in the body is the same as not sending one, and the cookies still get dropped.
    """
    res = api_client.post("/api/v1/auth/logout/", ARRAY_BODY, format="json")

    assert res.status_code == 200
    assert res.cookies["access_token"].value == ""
    assert res.cookies["refresh_token"].value == ""
