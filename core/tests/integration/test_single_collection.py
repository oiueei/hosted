"""A thing lives in exactly one collection, and the M2M refuses a second membership.

The guard sits on ``Collection.things.through`` so it holds from either side of the
relation and for any caller (a view, the admin, a shell). A thing is created in the
collection it is for, so none of the ways of creating one is a second membership.
"""

from io import StringIO

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import transaction

from core.models import Collection, Thing

THINGS_URL = "/api/v1/things/"
BULK_URL = "/api/v1/collections/{code}/things/bulk/"


@pytest.fixture
def first(user):
    return Collection.objects.create(code="SNGL01", owner=user, headline="First")


@pytest.fixture
def second(user):
    return Collection.objects.create(code="SNGL02", owner=user, headline="Second")


@pytest.fixture
def placed(user, first):
    thing = Thing.objects.create(code="SNGT01", owner=user, headline="Placed", type="GIFT_THING")
    first.things.add(thing)
    return thing


@pytest.mark.django_db
class TestCreatingAThingInACollection:
    def test_the_form_puts_it_in_its_one_collection(self, authenticated_client, first):
        response = authenticated_client.post(
            THINGS_URL,
            {"headline": "Form", "type": "GIFT_THING", "collection_code": first.code},
            format="json",
        )

        assert response.status_code == 201, response.data
        assert list(Thing.objects.get(code=response.data["code"]).collections.all()) == [first]

    def test_a_csv_or_zip_import_puts_each_row_in_the_collection(self, authenticated_client, first):
        rows = [{"headline": f"Row {i}", "type": "GIFT_THING"} for i in range(3)]

        response = authenticated_client.post(
            BULK_URL.format(code=first.code), {"rows": rows}, format="json"
        )

        assert response.status_code == 201, response.data
        assert first.things.count() == 3
        for thing in first.things.all():
            assert thing.collections.count() == 1


@pytest.mark.django_db
class TestASecondCollection:
    def test_adding_it_from_the_collection_side_is_refused(self, placed, second):
        with pytest.raises(ValidationError), transaction.atomic():
            second.things.add(placed)

        assert not second.things.exists()
        assert placed.collections.count() == 1

    def test_adding_it_from_the_thing_side_is_refused(self, placed, second):
        with pytest.raises(ValidationError), transaction.atomic():
            placed.collections.add(second)

        assert not second.things.exists()

    def test_a_batch_with_one_taken_thing_adds_none_of_them(self, user, placed, second):
        free = Thing.objects.create(code="SNGT02", owner=user, headline="Free", type="GIFT_THING")

        with pytest.raises(ValidationError), transaction.atomic():
            second.things.add(free, placed)

        assert not second.things.exists()

    def test_a_thing_cannot_be_given_two_collections_at_once(self, user, first, second):
        loose = Thing.objects.create(code="SNGT03", owner=user, headline="Loose", type="GIFT_THING")

        with pytest.raises(ValidationError), transaction.atomic():
            loose.collections.add(first, second)

        assert loose.collections.count() == 0

    def test_adding_it_again_to_the_same_collection_is_harmless(self, placed, first):
        first.things.add(placed)
        placed.collections.add(first)

        assert placed.collections.count() == 1

    def test_a_loose_thing_can_join_a_collection_from_either_side(self, user, first, second):
        a = Thing.objects.create(code="SNGT04", owner=user, headline="A", type="GIFT_THING")
        b = Thing.objects.create(code="SNGT05", owner=user, headline="B", type="GIFT_THING")

        first.things.add(a)
        b.collections.add(second)

        assert list(first.things.all()) == [a]
        assert list(second.things.all()) == [b]

    def test_a_thing_taken_out_of_its_collection_may_go_to_another(self, placed, first, second):
        first.things.remove(placed)

        second.things.add(placed)

        assert list(placed.collections.all()) == [second]


@pytest.mark.django_db
class TestTheRetiredEndpointsStayGone:
    """A thing used to be moved between collections over the API. Neither route exists
    any more, and a curator posting to one finds nothing and moves nothing."""

    def test_adding_a_thing_to_a_second_collection_is_not_a_route(
        self, authenticated_client, first, second, placed
    ):
        response = authenticated_client.post(
            f"/api/v1/collections/{second.code}/add-thing/",
            {"thing_code": placed.code},
            format="json",
        )

        assert response.status_code == 404
        assert list(placed.collections.all()) == [first]

    def test_taking_a_thing_out_of_its_collection_is_not_a_route(
        self, authenticated_client, first, placed
    ):
        response = authenticated_client.post(
            f"/api/v1/collections/{first.code}/remove-thing/",
            {"thing_code": placed.code},
            format="json",
        )

        assert response.status_code == 404
        assert list(placed.collections.all()) == [first]


@pytest.mark.django_db
class TestTheCommandsThatBuildThings:
    def test_the_demo_seed_still_runs(self):
        call_command("seed_demo", stdout=StringIO())

        assert Thing.objects.exists()
        assert not any(thing.collections.count() > 1 for thing in Thing.objects.all())
