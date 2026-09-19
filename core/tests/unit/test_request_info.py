"""
`Collection.request_info` — a short owner note shown at the top of the
request page: LEND/RENT/RESERVE alike, not RESERVE_THING only, but never
GIFT/SELL — those complete straight from the card and never visit that page,
so a note written here is invisible to them. The serializer field itself is
populated for every type regardless (see the test below), which is what keeps
`ThingSerializer` from branching by type; the frontend is what decides whether
to render it.

Owner prose like every other (D5): localized (O6), 512 visible per language,
2048 stored (CA's call, 2026-09: 256 was too short for this one) — the same
shape and the same trap as `deposit_policy` (core/tests/unit/test_deposits.py),
pinned again here rather than assumed.
"""

import json

import pytest
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory, force_authenticate

from core.models import Collection, Thing
from core.serializers import (
    CollectionCreateSerializer,
    CollectionSerializer,
    CollectionUpdateSerializer,
    ThingSerializer,
)
from core.utils import parse_localized

pytestmark = pytest.mark.django_db


def test_defaults_to_empty(collection):
    assert collection.request_info == ""
    assert CollectionSerializer(collection).data["request_info"] == ""


def test_a_group_can_write_one(user):
    serializer = CollectionCreateSerializer(
        data={"headline": "Tools", "request_info": "Bring your own bag."}
    )
    assert serializer.is_valid(), serializer.errors
    created = serializer.save(owner=user)
    assert CollectionSerializer(created).data["request_info"] == "Bring your own bag."


def test_a_bilingual_group_writes_it_twice_and_both_survive(collection):
    note = {"es": "Trae tu propia bolsa.", "ca": "Porta la teva pròpia bossa."}
    serializer = CollectionUpdateSerializer(
        collection, data={"request_info": json.dumps(note)}, partial=True
    )
    assert serializer.is_valid(), serializer.errors
    saved = serializer.save()
    # Stored as the map the owner wrote — resolving it here would pick one
    # language for everybody.
    assert parse_localized(saved.request_info) == note


def test_the_visible_limit_is_per_language(collection):
    too_long = json.dumps({"es": "x" * 513})
    serializer = CollectionUpdateSerializer(
        collection, data={"request_info": too_long}, partial=True
    )
    assert not serializer.is_valid()
    assert "request_info" in serializer.errors


def test_three_full_languages_still_fit_the_column(collection):
    full = json.dumps({lang: "x" * 512 for lang in ("es", "ca", "en")})
    assert len(full) > Collection._meta.get_field("request_info").max_length - 512

    serializer = CollectionUpdateSerializer(collection, data={"request_info": full}, partial=True)
    assert serializer.is_valid(), serializer.errors


def test_the_serializer_field_is_populated_for_every_type_not_only_reserve(user, collection):
    """The field itself doesn't branch by type — whether the frontend ever
    renders it (only for LEND/RENT/RESERVE, never GIFT/SELL) is a separate
    decision made on `RequestThingPage`, not here."""
    collection.request_info = "Please arrive on time."
    collection.save(update_fields=["request_info"])

    for thing_type in Thing.Type.values:
        thing = Thing.objects.create(
            code=f"RQ{thing_type[:4]}", type=thing_type, owner=user, headline="A thing"
        )
        collection.things.add(thing)
        data = ThingSerializer(thing).data
        assert data["collection_request_info"] == "Please arrive on time."


def test_empty_when_the_thing_has_no_viewable_collection(user):
    thing = Thing.objects.create(
        code="RQINOC", type=Thing.Type.GIFT_THING, owner=user, headline="Standalone"
    )
    assert ThingSerializer(thing).data["collection_request_info"] == ""


def test_a_thing_in_two_collections_names_one_of_them_and_sticks_to_it(user, collection):
    """`collections.all()` carries no ORDER BY, so *which* of two readable
    collections the `collection_*` fields name is the database's to decide.
    What has to hold is that they all name the **same** one — a note from one
    group beside another group's name is how the wrong note gets followed —
    and that `?collection=` settles it when the page knows which."""
    collection.request_info = "First group's note."
    collection.save(update_fields=["request_info"])
    other = Collection.objects.create(
        code="RQIOTH", owner=user, headline="Other", request_info="Other's note."
    )
    notes = {collection.code: "First group's note.", other.code: "Other's note."}

    thing = Thing.objects.create(
        code="RQITWO", type=Thing.Type.GIFT_THING, owner=user, headline="X"
    )
    collection.things.add(thing)
    other.things.add(thing)

    data = ThingSerializer(thing).data
    assert data["collection_request_info"] == notes[data["collection_code"]]

    # Asked through one of them, it is that one's note, whichever came first.
    raw = APIRequestFactory().get("/", {"collection": other.code})
    force_authenticate(raw, user=user)
    # A fresh instance: the resolved collection is memoised on the thing.
    read_again = Thing.objects.get(code=thing.code)
    through_other = ThingSerializer(read_again, context={"request": Request(raw)}).data
    assert through_other["collection_code"] == other.code
    assert through_other["collection_request_info"] == "Other's note."
