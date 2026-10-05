"""The requester's emails say where they will be written to (E2, CA 2026-10-05).

E1 made the requester's address travel with the request to whoever manages the thing. The
person it belongs to must not find that out by being written to: the three emails they
receive about their own request say it, in one sentence each, in the words CA approved.

What is pinned:

- **"request sent"** (``send_booking_confirmation_email``) says it right behind the
  sentence that tells them the curator was told, in the HTML and in the plain text, for
  every verb that waits for a decision;
- **"accepted"** (``send_booking_decision_email``) is the email it was before this round,
  and a refusal too: E2 gave it a sentence and E6 (CA, 2026-10-05) took it back out;
- **"reservation confirmed"** (``send_reservation_confirmed_email``) says it;
- none of the three **prints the address** — the email is already in that inbox;
- the sentences are the approved ones in the three catalogues, and the managers' emails
  (which E1 pinned) do not carry them.
"""

from datetime import date
from importlib import import_module

import pytest
from django.core import mail
from django.utils.html import escape

from core.models import BookingPeriod
from core.services import email_service

# Letter by letter, as CA approved them (SONNET_TASKS.md, round E): the catalogues are held
# to this table, and the emails to the catalogues.
APPROVED = {
    "contact_shared_request": {
        "es": "Tu email va con la solicitud: si hace falta, te escribirán aquí, al correo con el "
        "que entras en OIUEEI.",
        "ca": "El teu email va amb la sol·licitud: si cal, t'escriuran aquí, al correu amb què "
        "entres a OIUEEI.",
        "en": "Your email goes with the request: if needed, they'll write to you here, at the "
        "address you sign in to OIUEEI with.",
    },
    "contact_shared_reservation": {
        "es": "Tu email va con la reserva.",
        "ca": "El teu email va amb la reserva.",
        "en": "Your email goes with the booking.",
    },
}

# What E2 put in the "accepted" email until E6 (CA, 2026-10-05) took it out: the words that
# must not come back, in the three languages.
GONE_ACCEPTED = {
    "es": "Para quedar, te escribirán aquí, al correo con el que entras en OIUEEI.",
    "ca": "Per quedar, t'escriuran aquí, al correu amb què entres a OIUEEI.",
    "en": "To arrange the hand-over, they'll write to you here, at the address you sign in "
    "to OIUEEI with.",
}
LANGUAGES = ["es", "ca", "en"]
# The catalogues themselves, not `T()`: that falls back to English for a missing key, which
# would hide exactly what these tests are about.
TEXTS = {lang: import_module(f"core.services.email_texts.{lang}").TEXTS for lang in LANGUAGES}


def speaking(user, language):
    user.language = language
    user.save(update_fields=["language"])


def a_booking(thing, requester, owner, *, kind="LEND_THING", dates=True, status="PENDING"):
    thing.type = kind
    thing.save(update_fields=["type"])
    return BookingPeriod.objects.create(
        thing_code=thing,
        thing_type=thing.type,
        requester_code=requester,
        requester_email=requester.email,
        owner_code=owner,
        start_date=date(2026, 10, 13) if dates else None,
        end_date=date(2026, 10, 15) if dates else None,
        status=getattr(BookingPeriod.Status, status),
    )


def the_email_sent():
    (message,) = mail.outbox
    return message.body, message.alternatives[0][0]


def phrase(key, language):
    return APPROVED[key][language]


@pytest.mark.django_db
class TestRequestSent:
    @pytest.mark.parametrize("language", LANGUAGES)
    def test_it_says_where_they_will_be_written_to_in_both_halves(
        self, user, user2, thing, language
    ):
        speaking(user2, language)
        booking = a_booking(thing, user2, user)
        mail.outbox.clear()

        email_service.send_booking_confirmation_email(user2, thing, booking)

        body, html = the_email_sent()
        sentence = phrase("contact_shared_request", language)
        assert sentence in body
        assert escape(sentence) in html

    @pytest.mark.parametrize("language", LANGUAGES)
    def test_it_comes_right_behind_the_outro_and_before_the_link(
        self, user, user2, thing, language
    ):
        speaking(user2, language)
        booking = a_booking(thing, user2, user)
        mail.outbox.clear()

        email_service.send_booking_confirmation_email(user2, thing, booking, informed=1)

        body, html = the_email_sent()
        texts = TEXTS[language]
        outro = texts["confirmation_outro_one"]
        sentence = phrase("contact_shared_request", language)
        # Plain text: the outro and the sentence are one run, the listing link after them.
        assert f"{outro} {sentence}" in body
        assert body.index(sentence) < body.index("http")
        # HTML: the outro's paragraph, then the sentence's, then the button.
        assert (
            html.index(escape(outro))
            < html.index(escape(sentence))
            < html.index(texts["view_thing_cta"])
        ), "outro, then the sentence, then the call to action"

    @pytest.mark.parametrize("informed", [1, 2])
    def test_it_is_there_whether_one_person_was_told_or_a_team(self, user, user2, thing, informed):
        booking = a_booking(thing, user2, user)
        mail.outbox.clear()

        email_service.send_booking_confirmation_email(user2, thing, booking, informed=informed)

        body, html = the_email_sent()
        assert phrase("contact_shared_request", "en") in body
        assert escape(phrase("contact_shared_request", "en")) in html

    @pytest.mark.parametrize("kind", ["LEND_THING", "RENT_THING", "GIFT_THING", "SELL_THING"])
    def test_it_holds_for_every_verb_that_waits_for_a_decision(self, user, user2, thing, kind):
        dated = kind in ("LEND_THING", "RENT_THING")
        booking = a_booking(thing, user2, user, kind=kind, dates=dated)
        mail.outbox.clear()

        email_service.send_booking_confirmation_email(user2, thing, booking)

        body, html = the_email_sent()
        assert phrase("contact_shared_request", "en") in body
        assert escape(phrase("contact_shared_request", "en")) in html

    def test_it_does_not_print_the_address_it_was_sent_to(self, user, user2, thing):
        booking = a_booking(thing, user2, user)
        mail.outbox.clear()

        email_service.send_booking_confirmation_email(user2, thing, booking)

        body, html = the_email_sent()
        assert user2.email not in body
        assert user2.email not in html

    def test_the_owners_note_still_closes_the_email(self, user, user2, thing, collection):
        collection.email_note = "Bring a bag."
        collection.save(update_fields=["email_note"])
        booking = a_booking(thing, user2, user)
        mail.outbox.clear()

        email_service.send_booking_confirmation_email(user2, thing, booking, collection=collection)

        body, html = the_email_sent()
        sentence = phrase("contact_shared_request", "en")
        assert body.index(sentence) < body.index("Bring a bag.")
        assert html.index(escape(sentence)) < html.index("Bring a bag.")


@pytest.mark.django_db
class TestDecision:
    """E6 (CA, 2026-10-05): the decision email is the one it was before the round. E2 had
    given the accepted copy a sentence about the hand-over; it is gone, and so is its key."""

    @pytest.mark.parametrize("accepted", [True, False])
    @pytest.mark.parametrize("language", LANGUAGES)
    def test_neither_decision_says_anything_about_being_written_to(
        self, user, user2, thing, language, accepted
    ):
        speaking(user2, language)
        booking = a_booking(thing, user2, user, status="ACCEPTED" if accepted else "REJECTED")
        mail.outbox.clear()

        email_service.send_booking_decision_email(booking, thing, accepted=accepted)

        body, html = the_email_sent()
        for gone in GONE_ACCEPTED.values():
            assert gone not in body
            assert escape(gone) not in html
        for key in APPROVED:
            assert phrase(key, language) not in body
            assert escape(phrase(key, language)) not in html

    def test_an_accepted_one_still_has_its_details_its_button_and_the_owners_note(
        self, user, user2, thing, collection
    ):
        collection.email_note = "Ring the bell twice."
        collection.save(update_fields=["email_note"])
        booking = a_booking(thing, user2, user, status="ACCEPTED")
        mail.outbox.clear()

        email_service.send_booking_decision_email(
            booking, thing, accepted=True, collection=collection
        )

        body, html = the_email_sent()
        assert "has been confirmed" in body
        assert "Ring the bell twice." in body and "Ring the bell twice." in html
        assert TEXTS["en"]["view_thing_cta"] in html

    def test_it_holds_for_a_thing_with_no_dates(self, user, user2, thing):
        booking = a_booking(thing, user2, user, kind="GIFT_THING", dates=False, status="ACCEPTED")
        mail.outbox.clear()

        email_service.send_booking_decision_email(booking, thing, accepted=True)

        body, html = the_email_sent()
        assert GONE_ACCEPTED["en"] not in body
        assert escape(GONE_ACCEPTED["en"]) not in html

    def test_it_does_not_print_the_address(self, user, user2, thing):
        booking = a_booking(thing, user2, user, status="ACCEPTED")
        mail.outbox.clear()

        email_service.send_booking_decision_email(booking, thing, accepted=True)

        body, html = the_email_sent()
        assert user2.email not in body
        assert user2.email not in html


@pytest.mark.django_db
class TestReservationConfirmed:
    @pytest.mark.parametrize("language", LANGUAGES)
    def test_it_says_where_they_will_be_written_to_in_both_halves(
        self, user, user2, thing, language
    ):
        speaking(user2, language)
        booking = a_booking(thing, user2, user, kind="RESERVE_THING", status="ACCEPTED")
        mail.outbox.clear()

        email_service.send_reservation_confirmed_email(user2, thing, booking)

        body, html = the_email_sent()
        sentence = phrase("contact_shared_reservation", language)
        assert sentence in body
        assert escape(sentence) in html
        assert html.index(escape(sentence)) < html.index(TEXTS[language]["view_thing_cta"])

    def test_it_follows_the_fee_and_the_place(self, user, user2, thing):
        thing.fee = 12
        thing.location = "Workshop, ground floor"
        thing.save(update_fields=["fee", "location"])
        booking = a_booking(thing, user2, user, kind="RESERVE_THING", status="ACCEPTED")
        mail.outbox.clear()

        email_service.send_reservation_confirmed_email(user2, thing, booking)

        _, html = the_email_sent()
        sentence = phrase("contact_shared_reservation", "en")
        assert html.index("Workshop, ground floor") < html.index(escape(sentence))

    def test_it_does_not_print_the_address(self, user, user2, thing):
        booking = a_booking(thing, user2, user, kind="RESERVE_THING", status="ACCEPTED")
        mail.outbox.clear()

        email_service.send_reservation_confirmed_email(user2, thing, booking)

        body, html = the_email_sent()
        assert user2.email not in body
        assert user2.email not in html


@pytest.mark.django_db
class TestItIsForTheRequesterOnly:
    """E1's other half: the managers' emails say what they hold, not what the requester
    is told — so the sentences about being written to are not in them."""

    def test_the_managers_request_email_does_not_carry_them(self, user, user2, thing):
        booking = a_booking(thing, user2, user)
        mail.outbox.clear()

        email_service.send_booking_request_email(
            user2, thing, booking, user.email, "http://x/a", "http://x/r"
        )

        body, html = the_email_sent()
        for key in APPROVED:
            assert phrase(key, "en") not in body
            assert escape(phrase(key, "en")) not in html

    def test_the_managers_reservation_notice_does_not_carry_them(self, user, user2, thing):
        booking = a_booking(thing, user2, user, kind="RESERVE_THING", status="ACCEPTED")
        mail.outbox.clear()

        email_service.send_reservation_notice_email(user.email, user2, thing, booking)

        body, html = the_email_sent()
        for key in APPROVED:
            assert phrase(key, "en") not in body
            assert escape(phrase(key, "en")) not in html


class TestTheWordsAreInTheThreeCatalogues:
    @pytest.mark.parametrize("language", LANGUAGES)
    @pytest.mark.parametrize("key", sorted(APPROVED))
    def test_the_catalogue_holds_the_approved_text_letter_by_letter(self, key, language):
        assert TEXTS[language][key] == APPROVED[key][language]

    @pytest.mark.parametrize("key", sorted(APPROVED))
    def test_no_language_is_left_to_fall_back_to_english(self, key):
        assert all(key in TEXTS[language] for language in LANGUAGES)

    @pytest.mark.parametrize("language", LANGUAGES)
    def test_the_accepted_sentence_is_gone_from_the_catalogue(self, language):
        assert "contact_shared_accepted" not in TEXTS[language]
