"""
The four-type catalogue is closed: WISH, SWAP and SHARE cannot come back.

Migrations 0121-0123 extirpated the three types from the schema, but they only
**hid** the rows a real user had already created — nothing rewrote them, and
nothing stops a request from naming a retired type again. What refuses it today
is `Thing.Type.choices`, via DRF's `ChoiceField`, at each door a type can enter
through. That is one line in a model, and a widened `choices` (or a serializer
that stops declaring the field) would resurrect a type silently: the request
would 201 and the row would carry a type no view, serializer or template has
handled since this release.

There is no single "is this type allowed" function to unit-test — the guarantee
is distributed across the doors — so the doors are what these tests knock on:
single create, the update that "stays editable", and the bulk import. The
collection allowlist is the fourth and is covered in `test_allowed_thing_types`.

A stale mobile client, a queued retry, a saved CSV or somebody with curl is
exactly who arrives at these doors after a type is retired.
"""

import pytest

from core.models import Thing

RETIRED = ["WISH_THING", "SWAP_THING", "SHARE_THING"]

BULK_URL = "/api/v1/collections/{code}/things/bulk/"


@pytest.mark.django_db
@pytest.mark.parametrize("retired", RETIRED)
def test_a_retired_type_cannot_be_created(retired, authenticated_client, collection):
    """The main door: `POST /api/v1/things/` with a type that no longer exists."""
    res = authenticated_client.post(
        "/api/v1/things/",
        {"headline": "A thing from before", "type": retired, "collection_code": collection.code},
        format="json",
    )

    assert res.status_code == 400
    assert "type" in res.data
    assert not Thing.objects.filter(headline="A thing from before").exists()


@pytest.mark.django_db
@pytest.mark.parametrize("retired", RETIRED)
def test_a_live_thing_cannot_be_moved_onto_a_retired_type(
    retired, authenticated_client, thing, collection
):
    """The type stays editable after creation (`perform_update` re-checks it
    against the collection), so the retired set has to be refused here too —
    otherwise the closed door on create is walked around with a PATCH."""
    original = thing.type

    res = authenticated_client.patch(
        f"/api/v1/things/{thing.code}/", {"type": retired}, format="json"
    )

    assert res.status_code == 400
    thing.refresh_from_db()
    assert thing.type == original


@pytest.mark.django_db
@pytest.mark.parametrize("retired", RETIRED)
def test_a_retired_type_in_a_bulk_row_is_refused_by_row(retired, authenticated_client, collection):
    """The bulk import is the door a *saved CSV* arrives at — the one most likely
    to still name a retired type months later. The batch is all-or-nothing, so
    the valid rows beside it must not land either."""
    res = authenticated_client.post(
        BULK_URL.format(code=collection.code),
        {
            "rows": [
                {"type": "GIFT_THING", "headline": "A good row"},
                {"type": retired, "headline": "A row from the old catalogue"},
            ]
        },
        format="json",
    )

    assert res.status_code == 400
    assert Thing.objects.count() == 0, "all-or-nothing: the valid row must not land alone"


@pytest.mark.django_db
def test_the_four_live_types_still_pass_every_door(authenticated_client, collection):
    """The other half. A `choices` list emptied by accident — or a serializer
    that refused every type — would satisfy all three tests above, so the live
    catalogue has to be pinned in the same breath as the retired one."""
    live = ["GIFT_THING", "SELL_THING", "RENT_THING", "LEND_THING"]

    for thing_type in live:
        res = authenticated_client.post(
            "/api/v1/things/",
            {
                "headline": f"A live {thing_type}",
                "type": thing_type,
                "fee": "5.00",
                "collection_code": collection.code,
            },
            format="json",
        )
        assert res.status_code == 201, (thing_type, res.data)

    assert set(Thing.objects.values_list("type", flat=True)) == set(live)
