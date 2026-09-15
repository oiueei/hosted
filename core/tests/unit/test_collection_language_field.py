"""
`ThingSerializer.collection_language` — the one signal a thing-only page
(`ThingPage`, `RequestThingPage`, `EditThingPage`, `DeleteThingPage`) has for
the frontend's `useCollectionLanguage` hook: those pages fetch `/things/{code}/`
and never see the collection object a `collection_headline`-style field
already resolves through `_viewable_collection`. Mirrors that field's tests
(`test_request_info.py`) rather than inventing a new shape.
"""

import pytest
from django.contrib.auth.models import AnonymousUser
from rest_framework.test import APIRequestFactory

from core.models import Collection, Language, Thing
from core.serializers import ThingSerializer

pytestmark = pytest.mark.django_db


def test_defaults_to_empty(user, collection):
    thing = Thing.objects.create(code="CLDEF1", type=Thing.Type.GIFT_THING, owner=user)
    collection.things.add(thing)
    assert ThingSerializer(thing).data["collection_language"] == ""


def test_reflects_the_collections_own_language(user, collection):
    collection.language = Language.CA
    collection.save(update_fields=["language"])
    thing = Thing.objects.create(code="CLCA01", type=Thing.Type.GIFT_THING, owner=user)
    collection.things.add(thing)
    assert ThingSerializer(thing).data["collection_language"] == "ca"


def test_empty_when_the_thing_has_no_viewable_collection(user):
    thing = Thing.objects.create(code="CLNOC1", type=Thing.Type.GIFT_THING, owner=user)
    assert ThingSerializer(thing).data["collection_language"] == ""


def test_a_thing_in_two_collections_uses_the_first_ones_language(user, collection):
    """Same rule `collection_headline`/`collection_request_info` already
    follow — the first collection this viewer may read decides every
    `collection_*` field."""
    collection.language = Language.CA
    collection.save(update_fields=["language"])
    other = Collection.objects.create(owner=user, headline="Other", language=Language.ES)

    thing = Thing.objects.create(code="CLTWO1", type=Thing.Type.GIFT_THING, owner=user)
    collection.things.add(thing)
    other.things.add(thing)

    assert ThingSerializer(thing).data["collection_language"] == "ca"


def test_an_anonymous_reader_never_sees_a_private_collections_language(user, public_collection):
    """`collection_language` goes through `_viewable_collection`, the same
    viewer-scoping `collection_headline` uses — not `collections.all()[0]`.
    A thing shared into both a private group and a public one must not leak
    the private one's language (or anything else about it) to a stranger who
    can only see the public one, the exact leak `_viewable_collection`'s
    docstring exists to close."""
    private = Collection.objects.create(owner=user, headline="Private", language=Language.CA)
    public_collection.language = Language.ES
    public_collection.save(update_fields=["language"])

    thing = Thing.objects.create(code="CLPRIV", type=Thing.Type.GIFT_THING, owner=user)
    private.things.add(thing)
    public_collection.things.add(thing)

    request = APIRequestFactory().get("/")
    request.user = AnonymousUser()
    data = ThingSerializer(thing, context={"request": request}).data

    assert data["collection_language"] == "es"
