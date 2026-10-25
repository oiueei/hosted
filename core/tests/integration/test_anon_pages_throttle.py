"""The pages that ask the database for a visitor count against the API's ceiling.

`spa_index` (the link preview of a collection, a thing and a share link) and
`collection_address` (the 301 off an old or wrong prefix) each make a query per
anonymous visit. They spend the **same per-IP count** as `AnonymousApiThrottle`
(`ANON_API_RATE`, in this process's memory), and past the ceiling they stop asking:
a person who opens a link must not see an error for the sake of a preview card, so
the page is the site's own card (not the collection's, no redirect), made with no query.
A route that was never going to ask anything spends nothing.
"""

import types

import pytest
from django.test import Client, override_settings

from core import throttles
from core.models import Collection, User

RATE = "3/m"
MID_MINUTE = 1_800_000_030.0
GROUP_TITLE = "<title>The street — OIUEEI</title>"
HEAD = "<!doctype html><html><head><title>OIUEEI</title></head><body></body></html>"
OTHER_IP = {"HTTP_X_FORWARDED_FOR": "203.0.113.77"}


@pytest.fixture(autouse=True)
def _pinned_clock(monkeypatch):
    monkeypatch.setattr(throttles, "time", types.SimpleNamespace(time=lambda: MID_MINUTE))


@pytest.fixture(autouse=True)
def _limits_on(settings):
    settings.RATELIMIT_ENABLE = True
    settings.ANON_API_RATE = RATE
    settings.TRUSTED_PROXY_COUNT = 1


@pytest.fixture(autouse=True)
def built(tmp_path, db):
    dist = tmp_path / "frontend" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text(HEAD, encoding="utf-8")
    with override_settings(BASE_DIR=tmp_path):
        yield tmp_path


@pytest.fixture
def group(db):
    owner = User.objects.create(code="THR001", email="lele21@your-domain.test", name="Owner")
    return Collection.objects.create(
        code="THRGRP",
        owner=owner,
        headline="The street",
        description="Things we share",
        kind=Collection.Kind.LIBRARY,
        visibility=Collection.Visibility.PUBLIC,
    )


def _site_card():
    """What a page with no card of its own (or one that may not be asked for) gets."""
    return Client().get("/login").content.decode()


def _mine(path="/library/THRGRP"):
    return Client().get(path, HTTP_X_FORWARDED_FOR="198.51.100.1")


def _spend(times, path="/library/THRGRP"):
    for _ in range(times):
        _mine(path)


@pytest.mark.django_db
class TestTheLinkPreview:
    def test_the_visit_after_the_ceiling_is_the_plain_page_and_asks_nothing(
        self, group, django_assert_num_queries
    ):
        _spend(3)

        with django_assert_num_queries(0):
            res = _mine()

        assert res.status_code == 200
        assert res.content.decode() == _site_card()

    def test_inside_the_ceiling_the_card_is_there(self, group):
        _spend(2)

        assert GROUP_TITLE in _mine().content.decode()

    def test_another_address_in_the_same_window_still_gets_the_card(self, group):
        _spend(4)

        assert GROUP_TITLE in Client().get("/library/THRGRP", **OTHER_IP).content.decode()

    def test_a_share_link_is_counted_too(self, group, django_assert_num_queries):
        group.share_token = "tok_throttle_share_01"
        group.save(update_fields=["share_token"])
        _spend(3, "/share/tok_throttle_share_01")

        with django_assert_num_queries(0):
            res = _mine("/share/tok_throttle_share_01")

        assert res.content.decode() == _site_card()


@pytest.mark.django_db
class TestTheAddressRedirect:
    def test_the_visit_after_the_ceiling_is_the_page_not_the_redirect_and_asks_nothing(
        self, group, django_assert_num_queries
    ):
        _spend(3, "/collections/THRGRP")

        with django_assert_num_queries(0):
            res = _mine("/collections/THRGRP")

        assert res.status_code == 200
        assert res.content.decode() == _site_card()

    def test_inside_the_ceiling_it_still_redirects(self, group):
        _spend(2, "/collections/THRGRP")

        res = _mine("/collections/THRGRP")

        assert res.status_code == 301
        assert res["Location"] == "/library/THRGRP"

    def test_one_visit_spends_one_unit_not_two(self, group):
        """A visit to the right address goes through `collection_address` and on to
        `spa_index`; the second must not count the same visit again."""
        _spend(2)

        assert GROUP_TITLE in _mine().content.decode()
        assert GROUP_TITLE not in _mine().content.decode()


@pytest.mark.django_db
class TestWhatSpendsNothing:
    def test_neutral_routes_leave_the_whole_allowance_to_the_first_collection(self, group):
        for _ in range(10):
            _mine("/login")
            _mine("/")
            _mine("/me/edit")

        assert GROUP_TITLE in _mine().content.decode()


@pytest.mark.django_db
class TestOneCountForThePagesAndTheApi:
    def test_what_the_api_read_spent_is_gone_from_the_pages(self, group, django_assert_num_queries):
        client = Client()
        for _ in range(3):
            client.get(f"/api/v1/collections/{group.code}/", HTTP_X_FORWARDED_FOR="198.51.100.1")

        with django_assert_num_queries(0):
            res = _mine()

        assert res.content.decode() == _site_card()

    def test_what_the_pages_spent_is_gone_from_the_api(self, group):
        _spend(3)

        res = Client().get(
            f"/api/v1/collections/{group.code}/", HTTP_X_FORWARDED_FOR="198.51.100.1"
        )

        assert res.status_code == 429


@pytest.mark.django_db
class TestSwitchedOff:
    @pytest.mark.parametrize("rate", ["0", ""])
    def test_a_rate_of_zero_leaves_the_pages_unlimited(self, group, settings, rate):
        settings.ANON_API_RATE = rate
        _spend(10)

        assert GROUP_TITLE in _mine().content.decode()

    def test_the_global_switch_does_too(self, group, settings):
        settings.RATELIMIT_ENABLE = False
        _spend(10)

        assert GROUP_TITLE in _mine().content.decode()
