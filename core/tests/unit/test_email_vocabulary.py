"""The emails call a thing of OIUEEI a "thing" ("cosa"), as the app does.

"Listing" / "anuncio" / "anunci" came from the days the product was a classifieds
board; the app's copy dropped them and the emails must not bring them back.
"""

import re

import pytest

from core.services.email_texts import ca, en, es

RETIRED = {
    "en": re.compile(r"\blistings?\b", re.IGNORECASE),
    "es": re.compile(r"\banuncios?\b", re.IGNORECASE),
    "ca": re.compile(r"\banuncis?\b|\banunci\b", re.IGNORECASE),
}


@pytest.mark.parametrize("lang, module", [("en", en), ("es", es), ("ca", ca)])
def test_no_email_text_names_a_thing_a_listing(lang, module):
    offenders = {
        key: value
        for key, value in module.TEXTS.items()
        if isinstance(value, str) and RETIRED[lang].search(value)
    }
    assert offenders == {}


def test_the_reported_thing_emails_say_thing():
    assert "things" in en.TEXTS["reported_subject"]
    assert en.TEXTS["view_thing_cta"] == "View the thing"
