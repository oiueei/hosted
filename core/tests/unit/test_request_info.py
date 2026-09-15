"""
`Collection.request_info` — a short owner note shown at the top of the
request page for anyone about to request anything from the collection, every
verb (GIFT/SELL/RENT/LEND/RESERVE) alike, not RESERVE_THING only.

Owner prose like every other (D5): localized (O6), 256 visible per language,
1024 stored — the same shape and the same trap as `deposit_policy`
(core/tests/unit/test_deposits.py), pinned again here rather than assumed.
"""

import json

import pytest

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
    too_long = json.dumps({"es": "x" * 257})
    serializer = CollectionUpdateSerializer(
        collection, data={"request_info": too_long}, partial=True
    )
    assert not serializer.is_valid()
    assert "request_info" in serializer.errors


def test_three_full_languages_still_fit_the_column(collection):
    full = json.dumps({lang: "x" * 256 for lang in ("es", "ca", "en")})
    assert len(full) > Collection._meta.get_field("request_info").max_length - 256

    serializer = CollectionUpdateSerializer(collection, data={"request_info": full}, partial=True)
    assert serializer.is_valid(), serializer.errors


def test_reaches_the_request_page_for_every_verb_not_only_reserve(user, collection):
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


def test_a_thing_in_two_collections_uses_the_first_ones_note(user, collection):
    """Same rule `collection_headline` already follows — the first collection
    this viewer may read decides every `collection_*` field, this one included,
    so a thing shared into two groups can't leak the wrong one's note."""
    collection.request_info = "First group's note."
    collection.save(update_fields=["request_info"])
    other = Collection.objects.create(owner=user, headline="Other", request_info="Other's note.")

    thing = Thing.objects.create(
        code="RQITWO", type=Thing.Type.GIFT_THING, owner=user, headline="X"
    )
    collection.things.add(thing)
    other.things.add(thing)

    assert ThingSerializer(thing).data["collection_request_info"] == "First group's note."
