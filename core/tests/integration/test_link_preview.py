"""The ``<head>`` of a shared link: what a preview card may say, and what it must not.

A chat app reads the HTML the server sends and runs no JavaScript. These tests hold
the two halves of ``core.services.link_preview``: a public collection, a thing in
one and a share link get a filled ``<head>``; everything a stranger could not read
on the page is answered with the **same bytes** as a neutral route, so a private
collection cannot be told from a code that does not exist.
"""

import pytest
from django.test import Client, override_settings

from core.models import Collection, Thing, User
from core.services.link_preview import inject_preview, plain_description

HEAD = "<!doctype html><html><head><title>OIUEEI</title></head><body></body></html>"
TOKEN = "tok_preview_group_0123"
MEDIA = "https://media.your-domain.test"


@pytest.fixture
def built(tmp_path):
    dist = tmp_path / "frontend" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text(HEAD, encoding="utf-8")
    with override_settings(BASE_DIR=tmp_path):
        yield tmp_path


@pytest.fixture
def owner(db):
    return User.objects.create(code="PRVOW1", email="lele14@your-domain.test", name="Owner")


def _collection(owner, code="PUB001", **fields):
    fields.setdefault("headline", "The street")
    fields.setdefault("description", "Things we share")
    fields.setdefault("status", Collection.Status.ACTIVE)
    fields.setdefault("visibility", Collection.Visibility.PUBLIC)
    return Collection.objects.create(code=code, owner=owner, **fields)


def _thing(owner, collection, code="THG001", **fields):
    fields.setdefault("headline", "Drill")
    thing = Thing.objects.create(code=code, owner=owner, **fields)
    collection.things.add(thing)
    return thing


def _body(path):
    return Client().get(path).content.decode()


def _neutral():
    return _body("/me")


class TestACollection:
    def test_a_public_collection_names_itself(self, built, owner):
        _collection(owner)

        body = Client().get("/collections/PUB001", HTTP_HOST="testserver").content.decode()

        assert "<title>The street — OIUEEI</title>" in body
        assert '<meta property="og:title" content="The street">' in body
        assert '<meta property="og:description" content="Things we share">' in body
        assert '<meta name="description" content="Things we share">' in body
        assert '<meta property="og:url" content="http://testserver/collections/PUB001">' in body
        assert '<meta property="og:site_name" content="OIUEEI">' in body

    @override_settings(MEDIA_PUBLIC_BASE_URL=MEDIA)
    def test_a_photo_becomes_the_card_image(self, built, owner):
        _collection(owner, thumbnail="oiueei/u/cover.webp")

        body = _body("/collections/PUB001")

        assert f'<meta property="og:image" content="{MEDIA}/oiueei/u/cover.webp">' in body
        assert "summary_large_image" in body

    @override_settings(MEDIA_PUBLIC_BASE_URL=MEDIA)
    def test_without_a_photo_there_is_no_image_at_all(self, built, owner):
        _collection(owner)

        body = _body("/collections/PUB001")

        assert "og:image" not in body
        assert "summary_large_image" not in body
        assert '<meta name="twitter:card" content="summary">' in body

    def test_the_join_page_carries_the_same_preview(self, built, owner):
        _collection(owner)

        assert "<title>The street — OIUEEI</title>" in _body("/collections/PUB001/join")
        assert "<title>The street — OIUEEI</title>" in _body("/collections/PUB001/join/")

    def test_a_description_less_collection_has_no_description_tags(self, built, owner):
        _collection(owner, description="")

        body = _body("/collections/PUB001")

        assert "description" not in body

    @pytest.mark.parametrize(
        "language,expected",
        [("ca", "Els carrers"), ("", "Las calles"), ("en", "Las calles")],
    )
    def test_the_collections_own_language_picks_the_text(self, built, owner, language, expected):
        _collection(owner, headline='{"es": "Las calles", "ca": "Els carrers"}', language=language)

        assert f"<title>{expected} — OIUEEI</title>" in _body("/collections/PUB001")


class TestWhatAStrangerCannotSee:
    def test_a_private_collection_is_the_untouched_page(self, built, owner):
        _collection(owner, visibility=Collection.Visibility.PRIVATE)

        assert _body("/collections/PUB001") == _neutral() == HEAD
        assert _body("/collections/PUB001/join") == HEAD

    def test_an_inactive_public_collection_is_the_untouched_page(self, built, owner):
        _collection(owner, status=Collection.Status.INACTIVE)

        assert _body("/collections/PUB001") == _neutral()

    def test_an_unknown_code_is_the_untouched_page(self, built, db):
        assert _body("/collections/NOPE00") == _neutral()
        assert _body("/things/NOPE00") == _neutral()
        assert _body("/share/nope") == _neutral()


class TestAThing:
    def test_both_routes_carry_the_things_own_data(self, built, owner):
        _thing(
            owner, _collection(owner, language="ca"), headline='{"es": "Taladro", "ca": "Trepant"}'
        )

        for path in ("/things/THG001", "/collections/PUB001/things/THG001"):
            body = _body(path)
            assert "<title>Trepant — OIUEEI</title>" in body, path
            assert '<meta property="og:title" content="Trepant">' in body, path

    def test_an_inactive_thing_is_the_untouched_page(self, built, owner):
        _thing(owner, _collection(owner), status=Thing.Status.INACTIVE)

        assert _body("/things/THG001") == _neutral()
        assert _body("/collections/PUB001/things/THG001") == _neutral()

    def test_a_thing_of_a_private_collection_is_the_untouched_page(self, built, owner):
        _thing(owner, _collection(owner, visibility=Collection.Visibility.PRIVATE))

        assert _body("/things/THG001") == _neutral()

    def test_the_things_other_pages_are_not_previewed(self, built, owner):
        _thing(owner, _collection(owner))

        assert _body("/things/THG001/request") == _neutral()


class TestAShareLink:
    @override_settings(MEDIA_PUBLIC_BASE_URL=MEDIA)
    def test_a_private_group_gives_name_and_description_but_never_the_photo(self, built, owner):
        _collection(
            owner,
            visibility=Collection.Visibility.PRIVATE,
            share_token=TOKEN,
            thumbnail="oiueei/u/cover.webp",
        )

        body = _body(f"/share/{TOKEN}")

        assert "<title>The street — OIUEEI</title>" in body
        assert '<meta property="og:description" content="Things we share">' in body
        assert "og:image" not in body
        assert "summary_large_image" not in body

    def test_a_revoked_or_unknown_token_or_an_inactive_group_is_the_untouched_page(
        self, built, owner
    ):
        _collection(owner, code="REV001", share_token=None)
        _collection(owner, code="OFF001", share_token=TOKEN, status=Collection.Status.INACTIVE)

        for token in ("never-issued", TOKEN):
            assert _body(f"/share/{token}") == _neutral(), token


class TestEscaping:
    def test_an_owners_markup_never_reaches_the_page_as_markup(self, built, owner):
        _collection(owner, headline='"><script>alert(1)</script>')

        body = _body("/collections/PUB001")

        assert "<script>alert" not in body
        assert "&quot;" in body

    def test_a_page_without_head_or_title_is_returned_as_it_was(self):
        preview = {"title": "T", "description": "d", "image": None}

        assert inject_preview("<p>x</p>", preview, "http://x/") == "<p>x</p>"
        assert inject_preview("<title>a</title>", preview, "http://x/") == "<title>a</title>"


class TestPlainDescription:
    @pytest.mark.parametrize(
        "markdown,expected",
        [
            ("see [the rules](https://x.test/r) now", "see the rules now"),
            ("a **bold** word", "a bold word"),
            ("an *italic* word", "an italic word"),
            ("# Title\ntext", "Title text"),
            ("- one\n* two\n+ three\n1. four", "one two three four"),
            ("| a | b |\n|---|---|", "a b"),
            ("line one\n\n\nline   two", "line one line two"),
            ("snake_case and _slant_", "snake_case and slant"),
            ("", ""),
            (None, ""),
        ],
    )
    def test_markup_goes_and_whitespace_collapses(self, markdown, expected):
        assert plain_description(markdown) == expected

    def test_a_long_text_is_cut_at_a_word_with_an_ellipsis(self):
        text = " ".join(["palabra"] * 60)

        out = plain_description(text)

        assert out.endswith("…")
        assert len(out) <= 201
        assert out[:-1].split(" ")[-1] == "palabra"

    def test_a_text_at_the_limit_is_kept_whole(self):
        assert plain_description("a" * 200) == "a" * 200


class TestQueryBudget:
    @pytest.mark.parametrize("path", ["/", "/me", "/login", "/things/THG001/request"])
    def test_neutral_routes_ask_the_database_nothing(self, built, django_assert_num_queries, path):
        with django_assert_num_queries(0):
            Client().get(path)

    def test_a_collection_costs_one_query(self, built, owner, django_assert_max_num_queries):
        _collection(owner)

        with django_assert_max_num_queries(1):
            Client().get("/collections/PUB001")

    def test_a_thing_costs_a_few(self, built, owner, django_assert_max_num_queries):
        _thing(owner, _collection(owner))

        with django_assert_max_num_queries(3):
            Client().get("/things/THG001")
