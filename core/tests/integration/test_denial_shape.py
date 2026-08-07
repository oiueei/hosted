"""
Every ``can_view`` denial answers in the same shape, and says something.

``deny_if_cannot_view`` exists for exactly one reason, written in its own
docstring: to centralise the guard "so every endpoint returns the same
``{"error": ...}`` shape (one endpoint previously used ``{"detail": ...}``)".
That is a contract about the **body**, and the suite only ever asserted the
status. Emptying the body, renaming the key, or dropping the message all
survived the mutation pass — a 403 with no body would have shipped as green,
and the frontend would show a denial with nothing in it.

The message matters as much as the key: `get_viewable_thing` takes it as an
argument, so each endpoint says why *it* refused, and a caller passing `None`
also survived. These are the endpoints that route their denial through the
helper — the booking calendar and both FAQ doors.
"""

import pytest

from core.models import Collection, Thing, User


@pytest.fixture
def someone_elses_thing(db):
    """A thing in a private collection the second user is not invited to."""
    owner = User.objects.create(code="DOWN01", email="denyowner@test.com", name="Lala")
    collection = Collection.objects.create(code="DENY01", owner=owner, headline="Private")
    thing = Thing.objects.create(code="DENYT1", owner=owner, headline="A drill", type="LEND_THING")
    collection.things.add(thing)
    return thing


DENYING_ENDPOINTS = [
    pytest.param("/api/v1/things/{code}/calendar/", "get", id="booking-calendar"),
    pytest.param("/api/v1/things/{code}/faq/", "get", id="faq-list"),
]


@pytest.mark.django_db
@pytest.mark.parametrize("path,method", DENYING_ENDPOINTS)
def test_a_denial_carries_the_error_key_and_a_reason(
    path, method, authenticated_client2, someone_elses_thing
):
    """403 is only half the answer — the other half is a body the reader can act
    on, under the one key every denial in the app agrees to use."""
    response = getattr(authenticated_client2, method)(path.format(code=someone_elses_thing.code))

    assert response.status_code == 403
    assert response.data is not None, "a denial with no body tells the reader nothing"
    assert "error" in response.data, (
        "the shared key: `detail` is DRF's, and mixing the two is what this helper ended"
    )
    assert isinstance(response.data["error"], str) and response.data["error"].strip(), (
        "the message is per-endpoint and must survive to the caller"
    )


@pytest.mark.django_db
def test_each_endpoint_gives_its_own_reason_rather_than_one_generic_line(
    authenticated_client2, someone_elses_thing
):
    """The message is an argument, not a constant. A refactor that dropped it —
    passing None, or hardcoding one line for the whole app — reads the same in a
    status-only test, and costs the reader the only clue about what they were
    refused."""
    code = someone_elses_thing.code
    calendar = authenticated_client2.get(f"/api/v1/things/{code}/calendar/")
    faqs = authenticated_client2.get(f"/api/v1/things/{code}/faq/")

    assert calendar.data["error"] != faqs.data["error"]
    assert "FAQ" in faqs.data["error"]
