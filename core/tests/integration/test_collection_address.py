"""A collection lives at ``/{kind}/{code}``; the old and the wrong prefixes are sent there.

The 301 is safe to cache because a kind never changes, keeps the rest of the path
and the query string (the join page's ``?thing=``), and asks nothing about
permissions: an old link to a private collection has to reach its page so the
member can sign in. Emails carry the kind's prefix from the start.
"""

import pytest
from django.core import mail
from django.test import Client, override_settings

from core.models import Collection, Thing, User
from core.services import email_service

PREFIXES = ("collections", "stall", "library", "shed")


@pytest.fixture
def built(tmp_path):
    dist = tmp_path / "frontend" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text(
        "<!doctype html><html><head><title>OIUEEI</title></head></html>", encoding="utf-8"
    )
    with override_settings(BASE_DIR=tmp_path):
        yield tmp_path


@pytest.fixture
def owner(db):
    return User.objects.create(code="ADROW1", email="lulu7@your-domain.test", name="Owner")


def _group(owner, kind, code="ADR001", **fields):
    return Collection.objects.create(code=code, owner=owner, headline="G", kind=kind, **fields)


def _get(path):
    return Client().get(path)


@pytest.mark.django_db
class TestTheRedirect:
    @pytest.mark.parametrize("kind", ["STALL", "LIBRARY", "SHED"])
    @pytest.mark.parametrize("prefix", PREFIXES)
    def test_every_other_prefix_goes_to_the_kinds_own(self, built, owner, kind, prefix):
        _group(owner, kind)
        res = _get(f"/{prefix}/ADR001")

        if prefix == kind.lower():
            assert res.status_code == 200
        else:
            assert res.status_code == 301
            assert res["Location"] == f"/{kind.lower()}/ADR001"

    def test_the_query_string_and_the_rest_of_the_path_survive(self, built, owner):
        _group(owner, "LIBRARY")

        res = _get("/collections/ADR001/things/XyZ789/request?collection=ADR001&x=1")

        assert res.status_code == 301
        assert res["Location"] == "/library/ADR001/things/XyZ789/request?collection=ADR001&x=1"

    def test_the_join_page_keeps_the_thing_it_was_opened_for(self, built, owner):
        _group(owner, "STALL")

        res = _get("/library/ADR001/join?thing=XyZ789")

        assert res["Location"] == "/stall/ADR001/join?thing=XyZ789"

    def test_a_trailing_slash_is_kept(self, built, owner):
        _group(owner, "SHED")

        assert _get("/collections/ADR001/")["Location"] == "/shed/ADR001/"

    def test_a_private_collection_is_redirected_all_the_same(self, built, owner):
        """No permission is asked: the member has to reach the page to sign in."""
        _group(owner, "LIBRARY", visibility=Collection.Visibility.PRIVATE)

        assert _get("/collections/ADR001").status_code == 301

    def test_an_inactive_collection_is_redirected_too(self, built, owner):
        _group(owner, "LIBRARY", status=Collection.Status.INACTIVE)

        assert _get("/stall/ADR001").status_code == 301

    def test_a_code_that_names_nothing_is_the_spa_as_usual(self, built, db):
        res = _get("/collections/NOPE00/join?thing=X")

        assert res.status_code == 200
        assert b"<title>OIUEEI</title>" in res.content

    def test_only_a_six_character_code_is_a_collection(self, built, owner):
        _group(owner, "LIBRARY")

        assert _get("/collections/ADR0011").status_code == 200

    def test_the_old_new_page_moves_to_new(self, built, db):
        assert _get("/collections/new")["Location"] == "/new"
        assert _get("/collections/new/")["Location"] == "/new"

    @pytest.mark.parametrize("path", ["/new", "/stall", "/library", "/shed", "/stall/new"])
    def test_the_spas_own_routes_are_served(self, built, db, path):
        res = _get(path)

        assert res.status_code == 200
        assert b"<title>OIUEEI</title>" in res.content
        assert not res.has_header("Location")

    def test_a_redirect_does_not_need_the_frontend_built(self, tmp_path, owner):
        _group(owner, "LIBRARY")
        with override_settings(BASE_DIR=tmp_path):
            assert _get("/collections/ADR001").status_code == 301


@pytest.mark.django_db
class TestEmailsCarryTheKindsAddress:
    @pytest.mark.parametrize("kind", ["STALL", "LIBRARY", "SHED"])
    def test_a_thing_link_goes_through_the_collections_own_prefix(self, owner, kind):
        group = _group(owner, kind)
        thing = Thing.objects.create(code="THG001", owner=owner, headline="Drill")
        group.things.add(thing)

        url = email_service._thing_url(thing, reader=owner, collection=group)

        assert url.endswith(f"/{kind.lower()}/ADR001/things/THG001")

    @pytest.mark.parametrize("kind", ["STALL", "LIBRARY", "SHED"])
    def test_the_broadcast_and_the_digest_link_the_group_at_its_address(self, owner, kind):
        group = _group(owner, kind)
        member = User.objects.create(code="ADRMB1", email="lili9@your-domain.test", name="M")
        group.invites.add(member)

        email_service.send_broadcast_email(
            "Owner", owner.email, "G", group.code, "Hi", [member.email]
        )
        email_service.send_digest_email("G", group.code, ["A chair"], [member.email])

        for message in mail.outbox:
            assert f"/{kind.lower()}/ADR001" in message.body
            assert "/collections/ADR001" not in message.body

    def test_a_code_that_names_nothing_falls_back_to_the_old_address(self, db):
        email_service.send_digest_email("G", "GONE01", ["A chair"], ["lili9@your-domain.test"])

        assert "/collections/GONE01" in mail.outbox[0].body

    def test_the_viral_line_points_at_the_new_page(self, owner):
        stranger = User.objects.create(code="ADRST1", email="lele9@your-domain.test", name="S")
        group = _group(owner, "STALL")
        group.invites.add(stranger)

        email_service.send_digest_email("G", group.code, ["A chair"], [stranger.email])

        body = mail.outbox[0].body
        assert "/new" in body
        assert "/collections/new" not in body
