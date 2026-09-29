"""`spa_index` — the SPA's `index.html`, served for every route the API does not own.

A release replaces the hashed JS chunks the page names, so the reload a stale tab
does after a deploy (`reloadOnStaleChunk.js`) only helps if the browser asks for a
fresh `index.html` instead of reusing a cached one that names the chunks that are
gone. That is a header on this response.
"""

import pytest
from django.test import Client, override_settings


@pytest.fixture
def built(tmp_path):
    dist = tmp_path / "frontend" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>OIUEEI</title>", encoding="utf-8")
    with override_settings(BASE_DIR=tmp_path):
        yield tmp_path


def test_a_spa_route_is_served_with_no_cache(built):
    response = Client().get("/collections/ABC123")

    assert response.status_code == 200
    assert b"<title>OIUEEI</title>" in response.content
    assert response["Cache-Control"] == "no-cache"


def test_the_root_and_a_deep_route_carry_it_alike(built):
    for path in ("/", "/things/ABC123/request"):
        assert Client().get(path)["Cache-Control"] == "no-cache", path


def test_an_unbuilt_frontend_says_which_command_builds_it(tmp_path):
    with override_settings(BASE_DIR=tmp_path):
        response = Client().get("/collections/ABC123")

    assert response.status_code == 503
    assert b"npm run build" in response.content
    assert b"yarn" not in response.content
