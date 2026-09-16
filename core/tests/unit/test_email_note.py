"""
`Collection.email_note` — the owner's note in the emails a *requester*
receives about their request ("received" + "accepted" for every verb, plus
RESERVE's auto-confirmation), rendered after the listing link by
`email_service._note_blocks` and resolved per recipient like every owner
text. The email-side behaviour lives in core/tests/unit/test_email_service.py;
this suite pins the field itself.

Owner prose like every other (D5): localized (O6), 512 visible per language,
2048 stored — the same shape and the same trap as `request_info`
(core/tests/unit/test_request_info.py), pinned again rather than assumed.
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
    assert collection.email_note == ""
    assert CollectionSerializer(collection).data["email_note"] == ""


def test_a_group_can_write_one(user):
    serializer = CollectionCreateSerializer(
        data={"headline": "Tools", "email_note": "We confirm within 48h."}
    )
    assert serializer.is_valid(), serializer.errors
    created = serializer.save(owner=user)
    assert CollectionSerializer(created).data["email_note"] == "We confirm within 48h."


def test_a_bilingual_group_writes_it_twice_and_both_survive(collection):
    note = {"es": "Confirmamos en 48h.", "ca": "Confirmem en 48h."}
    serializer = CollectionUpdateSerializer(
        collection, data={"email_note": json.dumps(note)}, partial=True
    )
    assert serializer.is_valid(), serializer.errors
    saved = serializer.save()
    # Stored as the map the owner wrote — the email resolves it per recipient,
    # so resolving it here would pick one language for everybody.
    assert parse_localized(saved.email_note) == note


def test_the_visible_limit_is_per_language(collection):
    too_long = json.dumps({"es": "x" * 513})
    serializer = CollectionUpdateSerializer(collection, data={"email_note": too_long}, partial=True)
    assert not serializer.is_valid()
    assert "email_note" in serializer.errors


def test_three_full_languages_still_fit_the_column(collection):
    full = json.dumps({lang: "x" * 512 for lang in ("es", "ca", "en")})
    assert len(full) > Collection._meta.get_field("email_note").max_length - 512

    serializer = CollectionUpdateSerializer(collection, data={"email_note": full}, partial=True)
    assert serializer.is_valid(), serializer.errors


def test_markdown_and_emojis_are_prose_not_html(collection):
    """The note carries Markdown and emojis as plain text — rejecting raw HTML
    is `SafeTextField`'s job (a `<script>` never validates), and Markdown
    syntax surviving to storage is what `_note_blocks` renders later."""
    note = "Bring **ID** 🛠️ — see [the rules](https://example.com)"
    serializer = CollectionUpdateSerializer(collection, data={"email_note": note}, partial=True)
    assert serializer.is_valid(), serializer.errors
    assert serializer.save().email_note == note


def test_the_thing_serializer_does_not_carry_it(user, collection):
    """Unlike `request_info`, email_note has no `collection_email_note` mirror
    on ThingSerializer — the note is consumed server-side by the two email
    senders, so no page ever needs it."""
    collection.email_note = "Note the frontend never sees."
    collection.save(update_fields=["email_note"])
    thing = Thing.objects.create(
        code="ENNOTE", type=Thing.Type.GIFT_THING, owner=user, headline="X"
    )
    collection.things.add(thing)
    assert "collection_email_note" not in ThingSerializer(thing).data
