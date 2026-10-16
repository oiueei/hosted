"""The verb a price makes, and the verbs each kind holds: one table, two readers.

The form decides what to show — and which verb to ask the deployment's policy about
— from a browser copy of ``KIND_THING_TYPES`` and ``derive_thing_type``. If the two
drift, the form blocks a send the server would accept or lets through one it refuses.
``frontend/src/test/kindVerbParity.json`` is what both sides read
(``frontend/src/constants/things.test.js`` is the other): one of the shared fixtures
``CLAUDE.md`` names.
"""

import json
from decimal import Decimal
from pathlib import Path

import pytest

from core.models.collection import KIND_THING_TYPES, derive_thing_type

ROOT = Path(__file__).resolve().parents[3]
TABLE = json.loads((ROOT / "frontend" / "src" / "test" / "kindVerbParity.json").read_text())


def test_the_kinds_are_exactly_the_servers():
    assert {kind: tuple(verbs) for kind, verbs in TABLE["kinds"].items()} == KIND_THING_TYPES


@pytest.mark.parametrize("case", TABLE["cases"], ids=lambda c: f"{c['kind']}-{c['fee']}")
def test_the_price_makes_the_verb_the_table_says(case):
    fee = Decimal(case["fee"]) if case["fee"] is not None else None

    assert derive_thing_type(case["kind"], fee) == case["verb"], case["note"]


def test_the_table_covers_every_kind_with_and_without_a_price():
    for kind in KIND_THING_TYPES:
        fees = {c["fee"] is None for c in TABLE["cases"] if c["kind"] == kind}
        assert fees == {True, False}, kind
