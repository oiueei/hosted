"""The "this group is a demo" line in the emails of a demo collection.

A demo collection (``is_onboarding``) is shared by everyone who tries the product, so
a message that comes out of it says so, right under its title, in HTML and in plain
text. It rides only on the senders that are *handed the collection*: nothing is looked
up to find out, so a message that only knows a thing carries no line (the collection's
own title already says "DEMO ·"). A real group's messages are as they were.
"""

import pytest
from django.core import mail
from django.test import override_settings
from django.utils.html import escape

from core.models import Collection
from core.services import email_service
from core.services.email_texts import T

LANGS = ["en", "es", "ca"]


@pytest.fixture
def demo(db, user):
    return Collection.objects.create(
        code="DEMO01", owner=user, headline="DEMO · Tools", is_onboarding=True
    )


@pytest.fixture
def real(db, user):
    return Collection.objects.create(code="REAL01", owner=user, headline="Tools")


def _invite(col):
    email_service.send_collection_invite_email(
        "Lala", col.headline, "lele@your-domain.test", "http://x/a", "http://x/r", collection=col
    )


def _welcome(col):
    email_service.send_collection_welcome_doc_email(
        col.headline, "http://x/d.pdf", "lele@your-domain.test", collection=col
    )


def _revoke(col):
    email_service.send_collection_revoke_email(
        "Lala", col.headline, "lele@your-domain.test", collection=col
    )


def _rejected(col):
    email_service.send_invite_rejected_email(
        "Lele", col.headline, "lala@your-domain.test", collection=col
    )


def _broadcast(col):
    email_service.send_broadcast_email(
        "Lala",
        "lala@your-domain.test",
        col.headline,
        col.code,
        "Hello",
        ["lele@your-domain.test"],
        collection=col,
    )


def _digest(col):
    email_service.send_digest_email(
        col.headline, col.code, ["A drill"], ["lele@your-domain.test"], collection=col
    )


def _note_test(col):
    email_service.send_email_note_test_email(col.owner, col, "Ring the bell")


SENDERS = [_invite, _welcome, _revoke, _rejected, _broadcast, _digest, _note_test]


def _sent():
    message = mail.outbox[-1]
    return message.body, message.alternatives[0][0]


@pytest.mark.parametrize("send", SENDERS, ids=lambda f: f.__name__)
@pytest.mark.parametrize("lang", LANGS)
class TestADemoCollectionsMessagesSayIt:
    def test_the_line_is_in_both_halves_under_the_title(self, send, lang, demo):
        with override_settings(EMAIL_LANGUAGE=lang):
            send(demo)

        line = T("demo_note", lang)
        plain, html = _sent()
        assert line in plain
        # Plain: the title, then the line, before anything else.
        assert plain.split("\n\n")[1] == line
        # HTML: after the <h1> and before every other paragraph of the card.
        assert html.index(escape(line)) > html.index("</h1>")
        between = html[html.index("</h1>") : html.index(escape(line))]
        assert "<a " not in between and between.count("<p") <= 1

    def test_a_real_group_gets_none(self, send, lang, real):
        with override_settings(EMAIL_LANGUAGE=lang):
            send(real)

        plain, html = _sent()
        assert T("demo_note", lang) not in plain
        assert escape(T("demo_note", lang)) not in html


@pytest.mark.parametrize("lang", LANGS)
def test_the_three_catalogues_have_the_line(lang):
    assert T("demo_note", lang).strip()
    # Not the English fallback, in the other two languages.
    if lang != "en":
        assert T("demo_note", lang) != T("demo_note", "en")


@pytest.mark.django_db
def test_a_message_that_only_knows_the_thing_carries_no_line(user, thing):
    """No collection is looked up for it: a reminder knows the thing, not the group,
    even when the thing's group is a demo."""
    Collection.objects.filter(code="COLL01").update(is_onboarding=True)

    email_service.send_return_reminder_email("Lele", thing, "2026-10-20", "lala@your-domain.test")

    plain, html = _sent()
    assert T("demo_note", "en") not in plain
    assert escape(T("demo_note", "en")) not in html


@pytest.mark.parametrize("send", SENDERS, ids=lambda f: f.__name__)
def test_the_line_costs_no_query(send, demo, real):
    """Demo or not, the same queries: the sender is handed the collection and reads
    one attribute of it."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    with CaptureQueriesContext(connection) as for_real:
        send(real)
    with CaptureQueriesContext(connection) as for_demo:
        send(demo)

    assert len(for_demo) == len(for_real)


@pytest.fixture
def booking(db, user, thing):
    from datetime import date

    from core.models import BookingPeriod, User

    requester = User.objects.create(code="REQ001", email="lele@your-domain.test", name="Lele")
    return BookingPeriod.objects.create(
        thing_code=thing,
        thing_type=thing.type,
        requester_code=requester,
        requester_email=requester.email,
        owner_code=user,
        start_date=date(2026, 11, 2),
        end_date=date(2026, 11, 3),
        status="PENDING",
    )


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("is_demo", [True, False], ids=["demo", "real"])
class TestTheRequestEmailsWhichAreHandedTheirCollection:
    """The request sent, its decision and a reservation confirmed know the collection the
    request was made through (the caller resolved it): they carry the line when it is a demo."""

    def _check(self, lang, is_demo):
        plain, html = _sent()
        line = T("demo_note", lang)
        assert (line in plain) is is_demo
        assert (escape(line) in html) is is_demo

    def test_request_sent(self, lang, is_demo, booking, thing):
        col = Collection.objects.get(code="COLL01")
        Collection.objects.filter(pk=col.pk).update(is_onboarding=is_demo)
        col.refresh_from_db()
        requester = booking.requester_code
        with override_settings(EMAIL_LANGUAGE=lang):
            email_service.send_booking_confirmation_email(requester, thing, booking, collection=col)
        self._check(lang, is_demo)

    def test_decision(self, lang, is_demo, booking, thing):
        col = Collection.objects.get(code="COLL01")
        Collection.objects.filter(pk=col.pk).update(is_onboarding=is_demo)
        col.refresh_from_db()
        with override_settings(EMAIL_LANGUAGE=lang):
            email_service.send_booking_decision_email(booking, thing, True, collection=col)
        self._check(lang, is_demo)

    def test_reservation_confirmed(self, lang, is_demo, booking, thing):
        col = Collection.objects.get(code="COLL01")
        Collection.objects.filter(pk=col.pk).update(is_onboarding=is_demo)
        col.refresh_from_db()
        with override_settings(EMAIL_LANGUAGE=lang):
            email_service.send_reservation_confirmed_email(
                booking.requester_code, thing, booking, collection=col
            )
        self._check(lang, is_demo)

    def test_reservation_notice(self, lang, is_demo, booking, thing, user):
        col = Collection.objects.get(code="COLL01")
        Collection.objects.filter(pk=col.pk).update(is_onboarding=is_demo)
        col.refresh_from_db()
        with override_settings(EMAIL_LANGUAGE=lang):
            email_service.send_reservation_notice_email(
                user.email, booking.requester_code, thing, booking, collection=col
            )
        self._check(lang, is_demo)
