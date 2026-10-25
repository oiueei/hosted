"""The app's own palette rides in the HTML the server hands out.

`spa_index` writes the `Braaanding` row into every page it serves, as six CSS
variables and a koro `<meta>`, so the first paint wears the right colours with no
request and no flash. These tests hold that: what is served is the row, changing the
row changes what is served, a collection's page carries it too (it paints over it
once loaded), a value that is not a hex colour is never written into markup, and the
fallback in the stylesheet is the very palette the migration seeds.
"""

import importlib
import re
from pathlib import Path

import pytest
from django.test import Client, override_settings

from core.models import Braaanding, Collection, User
from core.models.braaanding import DEFAULT_COLORS
from core.services.app_palette import inject_app_palette, palette_style_and_meta

HEAD = "<!doctype html><html><head><title>OIUEEI</title></head><body></body></html>"
CSS = Path(__file__).resolve().parents[3] / "frontend" / "src" / "styles" / "oiueei-theme.css"


@pytest.fixture
def built(tmp_path, db):
    dist = tmp_path / "frontend" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text(HEAD, encoding="utf-8")
    with override_settings(BASE_DIR=tmp_path):
        yield tmp_path


def _variables(body):
    block = re.search(r'<style id="braaanding">html:root\{([^}]*)\}</style>', body)
    assert block, "the page carries no braaanding style block"
    return dict(pair.split(":") for pair in block.group(1).split(";"))


def _koro(body):
    meta = re.search(r'<meta name="braaanding-koro" content="([^"]*)">', body)
    assert meta, "the page carries no braaanding koro meta"
    return meta.group(1)


class TestWhatIsServed:
    def test_the_page_carries_the_six_colours_and_the_koro_of_the_row(self, built):
        body = Client().get("/login").content.decode()

        assert _variables(body) == {
            "--color-braaanding-01": "#191919",
            "--color-braaanding-02": "#F4E5DD",
            "--color-braaanding-03": "#D77452",
            "--color-braaanding-04": "#191919",
            "--color-braaanding-05": "#191919",
            "--color-braaanding-06": "#FAFAFA",
        }
        assert _koro(body) == "basic"

    def test_changing_the_row_changes_what_is_served(self, built):
        row = Braaanding.objects.get()
        row.color_03 = "#E0B090"
        row.koro = "wave"
        row.save()

        body = Client().get("/me").content.decode()

        assert _variables(body)["--color-braaanding-03"] == "#E0B090"
        assert _koro(body) == "wave"

    def test_the_block_sits_in_the_head_and_beats_the_fallback_whatever_the_order(self, built):
        body = Client().get("/login").content.decode()

        assert body.index('<style id="braaanding">') < body.index("</head>")
        # `html:root` outweighs the stylesheet's plain `:root`, so source order is moot.
        assert "html:root{" in body

    def test_a_collections_page_carries_it_too(self, built):
        owner = User.objects.create(code="APOWN1", email="lala@your-domain.test", name="O")
        Collection.objects.create(
            code="APCOL1",
            owner=owner,
            headline="Street",
            visibility=Collection.Visibility.PUBLIC,
        )

        body = Client().get("/stall/APCOL1").content.decode()

        assert "<title>Street — OIUEEI</title>" in body
        assert _variables(body)["--color-braaanding-01"] == "#191919"

    def test_the_response_is_still_not_cached(self, built):
        assert Client().get("/login")["Cache-Control"] == "no-cache"

    def test_a_page_without_a_head_comes_back_as_it_was(self):
        assert inject_app_palette("<p>no head</p>") == "<p>no head</p>"


class TestNothingButAHexIsWrittenIntoMarkup:
    @pytest.mark.parametrize(
        "bad", ["red", "#FFF", "url(x)", "#191919;}</style><script>x</script>", "", None, 7]
    )
    def test_a_value_that_is_not_a_hex_colour_is_replaced_by_its_seeded_default(self, bad):
        palette = {**DEFAULT_COLORS, "koro": "basic", "color_02": bad}

        tags = palette_style_and_meta(palette)

        assert "<script" not in tags
        assert "--color-braaanding-02:#F4E5DD" in tags

    @pytest.mark.parametrize("bad", ['x"><script>', "tsunami", "", None])
    def test_a_koro_that_is_not_one_of_the_six_becomes_basic(self, bad):
        tags = palette_style_and_meta({**DEFAULT_COLORS, "koro": bad})

        assert 'content="basic"' in tags
        assert "<script" not in tags


class TestTheFallbackInTheStylesheetIsTheSeededPalette:
    def test_the_css_declares_exactly_the_colours_the_migration_seeds(self):
        css = CSS.read_text(encoding="utf-8")
        declared = {
            f"color_0{n}": value.upper()
            for n, value in re.findall(r"--color-braaanding-0(\d):\s*(#[0-9a-fA-F]{6});", css)
        }
        seed = importlib.import_module("core.migrations.0164_braaanding")

        assert declared == DEFAULT_COLORS
        # The migration states the same values (it must not import them: a migration
        # records what was true when it ran), so all three agree.
        source = Path(seed.__file__).read_text(encoding="utf-8")
        for role, value in DEFAULT_COLORS.items():
            assert f'"{role}": "{value}"' in source
