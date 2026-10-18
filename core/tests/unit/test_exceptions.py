"""Unit tests for the custom DRF exception handler (rate-limit → 429)."""

import json
from pathlib import Path

from django_ratelimit.exceptions import Ratelimited
from rest_framework import serializers
from rest_framework.exceptions import NotFound, PermissionDenied

from core.exceptions import CODED_VALIDATION_REFUSALS, api_exception_handler
from core.utils import Refusal

LOCALES = Path(__file__).resolve().parents[3] / "frontend" / "src" / "i18n" / "locales"


def test_ratelimited_maps_to_429():
    res = api_exception_handler(Ratelimited(), {})
    assert res.status_code == 429
    assert "detail" in res.data


def test_genuine_permission_denied_still_403():
    res = api_exception_handler(PermissionDenied(), {})
    assert res.status_code == 403
    assert "detail" in res.data


def test_not_found_delegates_to_default():
    res = api_exception_handler(NotFound(), {})
    assert res.status_code == 404
    assert "detail" in res.data


def _refused(detail):
    return api_exception_handler(serializers.ValidationError(detail), {})


def test_a_coded_refusal_keeps_its_code_through_drf():
    exc = serializers.ValidationError(Refusal("No prices.", "no_prices_here"))

    assert exc.detail[0].code == "no_prices_here"


def test_a_coded_validation_refusal_is_lifted_to_the_top_of_the_body():
    res = _refused({"type": Refusal("No prices.", "no_prices_here")})

    assert res.status_code == 400
    assert res.data["code"] == "no_prices_here"
    assert res.data["type"] == "No prices."


def test_a_refusal_nested_in_a_list_is_found_too():
    res = _refused([Refusal("Prices remain.", "priced_things_remain")])

    # A list body has no place for a top-level code: it is left as DRF sends it.
    assert isinstance(res.data, list)

    res = _refused({"non_field_errors": [Refusal("Prices remain.", "priced_things_remain")]})
    assert res.data["code"] == "priced_things_remain"


def test_an_ordinary_validation_error_carries_no_code():
    res = _refused({"headline": ["This field may not be blank."]})

    assert "code" not in res.data


def test_two_different_coded_refusals_lift_nothing():
    res = _refused(
        {
            "type": Refusal("No prices.", "no_prices_here"),
            "other": Refusal("Prices remain.", "priced_things_remain"),
        }
    )

    assert "code" not in res.data


def test_a_code_outside_the_set_is_never_lifted():
    res = _refused({"type": Refusal("Something.", "reservation_already_begun")})

    assert "code" not in res.data


def test_every_lifted_code_is_translated_in_the_three_locales():
    for lang in ("en", "es", "ca"):
        table = json.loads((LOCALES / f"{lang}.json").read_text())["requestErrors"]
        # A code whose params carry a count is written as a plural pair.
        missing = sorted(
            code
            for code in CODED_VALIDATION_REFUSALS
            if code not in table and f"{code}_other" not in table
        )
        assert not missing, f"{lang}.json requestErrors has no string for: {missing}"
