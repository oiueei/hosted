"""A person with no name is "a member": capitalised when the name opens its sentence,
in lower case in the middle of one or inside a list."""

from datetime import date

import pytest
from django.core import mail
from django.test import override_settings

from core.models import BookingPeriod
from core.services import email_service

STAND_IN = {"en": "a member", "es": "un miembro", "ca": "un membre"}
OPENING = {"en": "A member", "es": "Un miembro", "ca": "Un membre"}


@pytest.mark.parametrize("lang", ["en", "es", "ca"])
def test_the_stand_in_has_a_form_for_each_place_in_a_sentence(lang):
    assert email_service._member_name("", lang) == OPENING[lang]
    assert email_service._member_name("", lang, inline=True) == STAND_IN[lang]
    # A real name is never touched.
    assert email_service._member_name("Lala", lang, inline=True) == "Lala"


def _booking(thing, owner, requester):
    return BookingPeriod.objects.create(
        thing_code=thing,
        thing_type="RESERVE_THING",
        requester_code=requester,
        requester_email=requester.email,
        owner_code=owner,
        start_date=date(2026, 10, 5),
        end_date=date(2026, 10, 6),
        status=BookingPeriod.Status.ACCEPTED,
    )


def _body_of_first_mail():
    return mail.outbox[0].body


@pytest.mark.parametrize(
    "lang,expected",
    [
        ("en", "Message from a member:"),
        ("es", "Mensaje de un miembro:"),
        ("ca", "Missatge d'un membre:"),
    ],
)
def test_a_broadcast_from_a_nameless_owner_reads_in_lower_case_mid_sentence(
    collection, user2, lang, expected
):
    with override_settings(EMAIL_LANGUAGE=lang):
        email_service.send_broadcast_email(
            "", "owner@your-domain.test", "Group", collection.code, "Hi", [user2.email]
        )
    assert expected in _body_of_first_mail()
    # The HTML opens its sentence with the name: capital there.
    html = mail.outbox[0].alternatives[0][0]
    assert f"{OPENING[lang]} " in html


@pytest.mark.parametrize(
    "lang,expected",
    [
        ("en", "return 'The Thing' to a member on"),
        ("es", "a un miembro el"),
        ("ca", "a un membre el"),
    ],
)
def test_a_return_reminder_names_a_nameless_owner_in_lower_case(thing, user2, lang, expected):
    with override_settings(EMAIL_LANGUAGE=lang):
        email_service.send_return_due_email("", thing, date(2026, 10, 6), user2.email)
    assert expected.replace("The Thing", thing.headline) in _body_of_first_mail()


@pytest.mark.parametrize(
    "lang,expected",
    [
        ("en", "from a member on"),
        ("es", "de un miembro el"),
        ("ca", "d'un membre el"),
    ],
)
def test_a_pickup_reminder_names_a_nameless_owner_in_lower_case(thing, user2, lang, expected):
    with override_settings(EMAIL_LANGUAGE=lang):
        email_service.send_pickup_due_email("", thing, date(2026, 10, 6), user2.email)
    assert expected in _body_of_first_mail()


@pytest.mark.parametrize(
    "lang,expected",
    [
        ("en", "You cancelled a member's reservation"),
        ("es", "Has cancelado la reserva de un miembro"),
        ("ca", "Has cancel·lat la reserva d'un membre"),
    ],
)
def test_cancelling_a_nameless_members_reservation_names_them_in_lower_case(
    thing, user, user2, lang, expected
):
    booking = _booking(thing, user, user2)
    with override_settings(EMAIL_LANGUAGE=lang):
        email_service.send_reservation_cancel_confirmation_email(
            user.email, thing, booking, is_own_reservation=False, member_name=""
        )
    assert expected in _body_of_first_mail()


@pytest.mark.parametrize(
    "lang,expected",
    [
        ("en", "Lala, a member and Lolo."),
        ("es", "Lala, un miembro y Lolo."),
        ("ca", "Lala, un membre i Lolo."),
    ],
)
def test_the_join_summary_list_has_the_nameless_in_lower_case(collection, user, lang, expected):
    user.language = lang
    user.save(update_fields=["language"])
    email_service.send_join_summary_email(collection, user, ["Lala", "", "Lolo"])
    assert expected in _body_of_first_mail()


@pytest.mark.parametrize(
    "lang,expected",
    [
        (
            "en",
            "Lala, a member, Lele, Lili, a member, Lolo, Lulu, Lola, a member, Lalo and 2 more.",
        ),
        (
            "es",
            "Lala, un miembro, Lele, Lili, un miembro, Lolo, Lulu, Lola, un miembro, Lalo y 2 más.",
        ),
        (
            "ca",
            "Lala, un membre, Lele, Lili, un membre, Lolo, Lulu, Lola, un membre, Lalo i 2 més.",
        ),
    ],
)
def test_twelve_people_name_ten_then_say_and_two_more(collection, user, lang, expected):
    user.language = lang
    user.save(update_fields=["language"])
    names = ["Lala", "", "Lele", "Lili", "", "Lolo", "Lulu", "Lola", "", "Lalo", "Lila", "Lilo"]
    email_service.send_join_summary_email(collection, user, names)
    assert expected in _body_of_first_mail()


def test_the_english_join_summary_opens_with_new_in():
    from core.services.email_texts.en import TEXTS

    assert TEXTS["join_summary_intro_one"] == "New in {group}: {names}."
    assert TEXTS["join_summary_intro_other"] == "New in {group}: {names}."


@pytest.mark.parametrize(
    "send",
    [
        lambda es, thing, to: es.send_faq_question_email("", thing, "Free?", to),
        lambda es, thing, to: es.send_faq_answer_email("", thing, "Free?", "Yes", to),
    ],
    ids=["a question", "an answer"],
)
def test_a_name_that_opens_its_sentence_keeps_the_capital(thing, user2, send):
    with override_settings(EMAIL_LANGUAGE="en"):
        send(email_service, thing, user2.email)
    assert "A member has" in _body_of_first_mail()


# ── Catalan joins "de un membre" into "d'un membre" — in the sentence, never in
# what the user wrote.
class TestElisionLeavesUsersTextAlone:
    def test_a_catalan_broadcast_keeps_a_message_that_says_de_un_membre(self, collection, user2):
        message = "Parlem de un membre nou i de un altre."
        with override_settings(EMAIL_LANGUAGE="ca"):
            email_service.send_broadcast_email(
                "", "owner@your-domain.test", "Group", collection.code, message, [user2.email]
            )
        body = _body_of_first_mail()
        assert message in body
        assert "Missatge d'un membre:" in body

    def test_a_named_owner_keeps_the_plain_de(self, collection, user2):
        with override_settings(EMAIL_LANGUAGE="ca"):
            email_service.send_broadcast_email(
                "Lala", "owner@your-domain.test", "Group", collection.code, "Hola", [user2.email]
            )
        assert "Missatge de Lala:" in _body_of_first_mail()

    def test_a_catalan_pickup_reminder_keeps_a_headline_that_says_de_un_membre(self, thing, user2):
        thing.headline = "Cadira de un membre"
        thing.save(update_fields=["headline"])
        with override_settings(EMAIL_LANGUAGE="ca"):
            email_service.send_pickup_due_email("", thing, date(2026, 10, 6), user2.email)
        body = _body_of_first_mail()
        # The headline inside the sentence is as typed; the stand-in is elided.
        assert "reculls 'Cadira de un membre' d'un membre el" in body

    def test_a_catalan_cancel_confirmation_keeps_a_headline_that_says_de_un_membre(
        self, thing, user, user2
    ):
        thing.headline = "Taula de un membre"
        thing.save(update_fields=["headline"])
        booking = _booking(thing, user, user2)
        with override_settings(EMAIL_LANGUAGE="ca"):
            email_service.send_reservation_cancel_confirmation_email(
                user.email, thing, booking, is_own_reservation=False, member_name=""
            )
        body = _body_of_first_mail()
        assert "la reserva d'un membre de 'Taula de un membre'" in body

    def test_a_named_member_in_a_catalan_cancel_confirmation_keeps_de(self, thing, user, user2):
        booking = _booking(thing, user, user2)
        with override_settings(EMAIL_LANGUAGE="ca"):
            email_service.send_reservation_cancel_confirmation_email(
                user.email, thing, booking, is_own_reservation=False, member_name="Lele"
            )
        assert "la reserva de Lele" in _body_of_first_mail()
