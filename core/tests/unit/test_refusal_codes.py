"""The coded refusals a request can meet, and the promise their codes make.

``core`` has no gettext catalogue, so every refusal the API sends is an English
sentence — and the request page used to show it as-is to a Catalan or Spanish
member. A refusal now also carries a ``code`` (and the ``params`` its sentence
interpolates) that the SPA says in the reader's language, from
``requestErrors.<code>`` in ``frontend/src/i18n/locales``.

A code with no string there silently falls back to English again, which is the
failure this whole change exists to remove — so the last test reads the codes
straight out of the source and fails if one has no translation.
"""

import json
import re
from pathlib import Path

from core.services.booking_service import BookingRequestError
from core.utils import Refusal

ROOT = Path(__file__).resolve().parents[3]
SOURCES = [
    ROOT / "core" / "models" / "collection.py",
    ROOT / "core" / "services" / "booking_service.py",
]
LOCALES = ROOT / "frontend" / "src" / "i18n" / "locales"


def test_a_refusal_is_still_the_sentence_it_always_was():
    refusal = Refusal("That time has already begun.", "reservation_already_begun")

    assert refusal == "That time has already begun."
    assert isinstance(refusal, str)
    assert refusal.code == "reservation_already_begun"
    assert refusal.params == {}


def test_a_booking_error_raised_on_a_refusal_carries_its_code_and_params():
    exc = BookingRequestError(
        Refusal("Up to 10 days ahead.", "reservation_beyond_horizon", days=10)
    )

    assert exc.as_body() == {
        "error": "Up to 10 days ahead.",
        "code": "reservation_beyond_horizon",
        "params": {"days": 10},
    }


def test_a_plain_message_keeps_the_plain_body():
    assert BookingRequestError("Not a reservation.").as_body() == {"error": "Not a reservation."}


def _codes_in_source():
    codes = set()
    for path in SOURCES:
        text = path.read_text()
        # Refusal("…", "code", …) — the code is the second string literal.
        codes |= set(re.findall(r'Refusal\(\s*(?:f?"[^"]*"\s*)+,\s*"([a-z_]+)"', text))
        # BookingRequestError(…, code="code", …) and the clash's conditional code.
        codes |= set(re.findall(r'code="([a-z_]+)"', text))
        codes |= set(re.findall(r'else "([a-z_]+)"', text))
    return codes


def test_every_code_a_request_can_be_refused_with_is_translated():
    codes = _codes_in_source()
    # The scan itself must be finding things, or this test proves nothing.
    assert {"reservation_already_begun", "rental_pickup_weekday", "time_taken"} <= codes
    for lang in ("en", "es", "ca"):
        table = json.loads((LOCALES / f"{lang}.json").read_text())["requestErrors"]
        # A code whose sentence carries a number is pluralised (`_one`/`_other`).
        missing = sorted(
            code for code in codes if code not in table and f"{code}_other" not in table
        )
        assert not missing, f"{lang}.json requestErrors has no string for: {missing}"
