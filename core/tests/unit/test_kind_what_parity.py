"""The sentence of a kind: the same words in the app and in a link's preview card.

`kinds.<K>.what` in the frontend's locale files is what the kind chooser shows;
`kind_what_<K>` in `core/services/email_texts` is what a shared link's card says for
a collection with no description of its own. They are the same sentence, written
twice because the server has no way to read the app's catalogue; this keeps the two
from drifting apart.
"""

import json
from pathlib import Path

import pytest

from core.models.collection import KIND_THING_TYPES
from core.services.email_texts import T

LOCALES = Path(__file__).resolve().parents[3] / "frontend" / "src" / "i18n" / "locales"


@pytest.mark.parametrize("lang", ["en", "es", "ca"])
@pytest.mark.parametrize("kind", list(KIND_THING_TYPES))
def test_the_card_says_what_the_app_says_of_the_kind(lang, kind):
    app = json.loads((LOCALES / f"{lang}.json").read_text())["kinds"][kind]["what"]

    assert T(f"kind_what_{kind}", lang) == app
