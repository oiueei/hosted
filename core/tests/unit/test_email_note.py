"""
`Collection.email_note` — the owner's note in the emails a *requester*
receives about their request ("received" + "accepted" for every verb, plus
RESERVE's auto-confirmation), rendered after the listing link by
`email_service._note_blocks` and resolved per recipient like every owner
text. The email-side behaviour lives in core/tests/unit/test_email_service.py;
this suite pins the field itself; who may read it back, through the
collection or a thing, is pinned against the API in
core/tests/integration/test_curator_only_collection_fields.py.

Owner prose like every other: localized, 512 visible per language,
2048 stored — the same shape and the same trap as `request_info`
(core/tests/unit/test_request_info.py), pinned again rather than assumed.
"""

import json
import re
from pathlib import Path

import pytest

from core.models import Collection
from core.serializers import (
    CollectionCreateSerializer,
    CollectionSerializer,
    CollectionUpdateSerializer,
)
from core.utils import parse_localized

pytestmark = pytest.mark.django_db


def test_defaults_to_empty(collection):
    assert collection.email_note == ""


def test_a_group_can_write_one(user):
    serializer = CollectionCreateSerializer(
        data={"headline": "Tools", "email_note": "We confirm within 48h."}
    )
    assert serializer.is_valid(), serializer.errors
    created = serializer.save(owner=user)
    created.refresh_from_db()
    assert created.email_note == "We confirm within 48h."


def test_the_read_serializer_withholds_it_without_a_request(collection):
    """Who may read it back is pinned against the API in
    core/tests/integration/test_curator_only_collection_fields.py; this is the
    request-less half — internal use fails closed, like `pending_invites`."""
    collection.email_note = "Door code 4417."
    collection.save(update_fields=["email_note"])
    assert CollectionSerializer(collection).data["email_note"] == ""


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


# --- The links, read as the app reads them --------------------------------------
#
# `frontend/src/test/markdownLinkParity.json` is read by the frontend's Markdown
# test and by this one: an owner's `[text](url)` must mean the same in the app
# and in the email. New cases go in the file, not here.

_PARITY = json.loads(
    (Path(__file__).resolve().parents[3] / "frontend/src/test/markdownLinkParity.json").read_text()
)["cases"]


@pytest.mark.parametrize("case", _PARITY, ids=[c["input"] for c in _PARITY])
def test_a_link_target_means_what_it_means_in_the_app(case):
    from html import unescape

    from django.utils.html import escape

    from core.services.email_service import _md_inline

    found = re.search(r'<a href="([^"]*)"', _md_inline(escape(case["input"])))

    assert (unescape(found.group(1)) if found else None) == case["href"]


def test_an_address_with_parentheses_is_not_cut_at_the_first_one():
    from django.utils.html import escape

    from core.services.email_service import _md_inline

    out = _md_inline(escape("[wiki](https://es.wikipedia.org/wiki/Foo_(bar)) y más"))

    assert 'href="https://es.wikipedia.org/wiki/Foo_(bar)"' in out
    assert "(es.wikipedia.org) y más" in out


def test_www_is_read_as_https_and_a_mailbox_names_no_host():
    from django.utils.html import escape

    from core.services.email_service import _md_inline

    assert 'href="https://www.x.cat"' in _md_inline(escape("[la web](www.x.cat)"))
    assert "(www.x.cat)" in _md_inline(escape("[la web](www.x.cat)"))
    mail = _md_inline(escape("[escríbeme](mailto:lala@example.com)"))
    assert 'href="mailto:lala@example.com"' in mail
    assert mail.endswith("escríbeme</a>")


def test_a_link_whose_text_is_its_own_address_names_no_host_even_without_the_scheme():
    from django.utils.html import escape

    from core.services.email_service import _md_inline

    out = _md_inline(escape("[www.x.cat](www.x.cat)"))

    assert 'href="https://www.x.cat"' in out
    assert out.count("www.x.cat") == 2  # the href host and the label, no "(host)" after
