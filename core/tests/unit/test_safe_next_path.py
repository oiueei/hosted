"""``safe_next_path``: the one door a login's ``next`` has to pass.

A magic link can carry the page the person was heading for when their session ran
out, so the login can send them back to it. That is a redirect built from a value
a client typed, which is exactly the shape of an open redirect: every row of the
table in ``frontend/src/test/nextPathParity.json`` is either a same-site path the
SPA really has, or one thing a browser could read as *somewhere else* (another
origin, a script, a page that only loops). ``nextPath.test.js`` runs the same
file — one of the two fixtures ``CLAUDE.md`` names as shared across the wire, so
the server's table and the browser's defence in depth cannot drift apart.
"""

import json
from pathlib import Path

import pytest

from core.utils import safe_next_path

ROOT = Path(__file__).resolve().parents[3]
TABLE = json.loads((ROOT / "frontend" / "src" / "test" / "nextPathParity.json").read_text())
ACCEPTED = TABLE["accepted"]
REJECTED = TABLE["rejected"]


def test_the_shared_table_travelled_intact():
    """The table is data now: a reshaped or emptied file must fail loudly, not
    silently test nothing. It moved here holding 31 rejected and 8 accepted
    rows, each list ending on its length boundary."""
    assert len(REJECTED) >= 30
    assert len(ACCEPTED) >= 8
    # The boundary rows travel as full strings; a hand edit that changed their
    # length would quietly move the limit every other row is measured against.
    assert len(ACCEPTED[-1]) == 256  # exactly at the limit
    assert len(REJECTED[-1]) == 257  # one character over


@pytest.mark.parametrize("value", ACCEPTED)
def test_a_same_site_path_the_spa_has_is_returned_untouched(value):
    assert safe_next_path(value) == value


@pytest.mark.parametrize("value", REJECTED)
def test_anything_that_could_leave_the_site_or_loop_is_dropped(value):
    assert safe_next_path(value) == ""
