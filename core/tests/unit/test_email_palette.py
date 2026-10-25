"""An email wears the app's own palette (`Braaanding`), read each time it is composed.

The buttons and links of every message take their colours from the row an operator
edits in the Django admin: the primary button is filled with `color_01` and labelled in
`color_06`, the secondary is white with an accent border and label, links are the
accent underlined, and the two hover states are the hero pair (`color_03`/`color_05`)
and a `color_02` fill. The accent is `color_01` where it reads at 4.5:1 on white and on
the page colour, else `color_04` — the rule the web app's content links follow.
"""

import re

import pytest
from django.core import mail

from core.models import Braaanding
from core.services import email_service
from core.services.palette_contrast import contrast_ratio

SEED = {
    "color_01": "#191919",
    "color_02": "#f4e5dd",
    "color_03": "#d77452",
    "color_04": "#191919",
    "color_05": "#191919",
    "color_06": "#fafafa",
}


def _set(**changes):
    row = Braaanding.objects.get()
    for field, value in changes.items():
        setattr(row, field, value)
    row.save()


def _magic_link_html():
    mail.outbox.clear()
    email_service.send_magic_link_email("lala@your-domain.test", "http://localhost:3000/verify/tok")
    return mail.outbox[0].alternatives[0][0]


@pytest.mark.django_db
class TestTheSeededPaletteInAnEmail:
    def test_the_primary_button_is_color_01_with_color_06_text(self):
        style = email_service.email_style()

        assert style["btn_primary"].startswith(
            "display:inline-block;background-color:#191919;color:#fafafa;"
        )
        assert "padding:14px 24px;" in style["btn_primary"]

    def test_the_secondary_is_white_with_an_accent_border_and_label(self):
        style = email_service.email_style()

        assert style["btn_secondary"].startswith(
            "display:inline-block;background-color:#ffffff;color:#191919;border:2px solid #191919;"
        )
        # Two pixels short of the primary's padding on every side: the border makes up the size.
        assert "padding:12px 22px;" in style["btn_secondary"]

    def test_links_are_the_accent_underlined(self):
        assert email_service.email_style()["link_style"] == (
            "color:#191919 !important;text-decoration:underline !important;"
        )

    def test_hover_states_are_the_hero_pair_and_a_page_colour_fill(self):
        style = email_service.email_style()

        assert style["primary_hover"] == (
            "background-color:#d77452 !important;color:#191919 !important;"
        )
        assert style["secondary_hover"] == "background-color:#f4e5dd !important;"

    def test_a_sent_email_carries_them_in_its_markup_and_its_hover_rules(self):
        html = _magic_link_html()

        assert 'style="display:inline-block;background-color:#191919;color:#fafafa;' in html
        assert ".btn-primary:hover { background-color:#d77452 !important;" in html
        assert "color:#191919 !important; }" in html
        assert ".btn-secondary:hover { background-color:#f4e5dd !important; }" in html
        # The old blue is nowhere.
        assert "#0000bf" not in html
        assert "#00005e" not in html and "#f0f0ff" not in html

    def test_the_seeded_palette_meets_the_contrast_its_hover_pair_needs(self):
        assert contrast_ratio(SEED["color_05"], SEED["color_03"]) >= 4.5
        assert contrast_ratio(SEED["color_06"], SEED["color_01"]) >= 4.5


@pytest.mark.django_db
class TestChangingTheRowChangesTheEmail:
    def test_a_new_color_01_and_color_06_repaint_the_primary_button(self):
        _set(color_01="#003366", color_06="#ffffff")

        html = _magic_link_html()

        assert 'style="display:inline-block;background-color:#003366;color:#ffffff;' in html
        assert "background-color:#191919;color:#fafafa;" not in html

    def test_the_hover_follows_color_03_color_05_and_color_02(self):
        _set(color_03="#e0b090", color_05="#000000", color_02="#eeeeee")

        html = _magic_link_html()

        assert ".btn-primary:hover { background-color:#e0b090 !important;" in html
        assert ".btn-secondary:hover { background-color:#eeeeee !important; }" in html

    def test_colours_are_written_lowercase_whatever_the_admin_typed(self):
        _set(color_01="#003366", color_06="#FFFFFF")

        style = email_service.email_style()

        assert "#FFFFFF" not in style["btn_primary"]
        assert "color:#ffffff;" in style["btn_primary"]

    def test_every_link_in_the_email_takes_the_accent(self):
        _set(color_01="#003366", color_04="#222222")

        html = _magic_link_html()

        links = re.findall(r'style="(color:[^"]*underline !important;)"', html)
        assert links, "an email has plain links"
        assert set(links) == {"color:#003366 !important;text-decoration:underline !important;"}


@pytest.mark.django_db
class TestTheAccentFallsBackToTheTextColour:
    def test_a_color_01_too_pale_for_white_is_not_the_accent(self):
        """A pale primary colour reads on neither white nor the page: links, the secondary
        border and its label take `color_04` instead; the primary button keeps `color_01`
        (its label is `color_06`, judged on the fill)."""
        _set(color_01="#ffe977", color_06="#191919", color_04="#222222")

        style = email_service.email_style()

        assert "background-color:#ffe977;color:#191919;" in style["btn_primary"]
        assert "color:#222222;border:2px solid #222222;" in style["btn_secondary"]
        assert style["link_style"].startswith("color:#222222 !important;")

    def test_a_color_01_that_reads_on_white_but_not_on_the_page_colour_falls_back_too(self):
        # Dark enough for white, not for a dark page colour.
        _set(color_01="#5a5a5a", color_02="#6a6a6a", color_04="#000000", color_06="#ffffff")
        assert contrast_ratio("#5a5a5a", "#ffffff") >= 4.5
        assert contrast_ratio("#5a5a5a", "#6a6a6a") < 4.5

        style = email_service.email_style()

        assert style["link_style"].startswith("color:#000000 !important;")

    def test_a_readable_color_01_is_kept(self):
        _set(color_01="#003366")

        assert email_service.email_style()["link_style"].startswith("color:#003366 !important;")


@pytest.mark.django_db
def test_every_kind_of_message_uses_the_same_palette(settings):
    """The three places that spell a style — a CTA, a pair of answers, a plain link — read
    one source, so they cannot drift apart."""
    _set(color_01="#003366", color_06="#ffffff")

    html = _magic_link_html()

    primary = re.findall(r'class="btn-primary"', html)
    assert primary
    for style in re.findall(r'style="([^"]*)" class="btn-primary"', html):
        assert style == email_service.email_style()["btn_primary"]
