"""The email of whoever asks for a thing reaches whoever manages it.

A public COMMUNITY collection selling things: whoever sells does
not know whoever buys, and the request email said only "Lele sent you a request". So
the requester's address travels **with the request**, not when it is accepted,
so the seller can agree on price, place and time before committing the thing; it holds
for every collection and every verb; and it goes **one way** — requester to manager. The
manager's address is never shown to the requester, who will have it if they are written to.

What is pinned, for the two emails that tell a manager someone asked:

- **the address is in the email**, under the entry sentence, as a real ``mailto:`` link in
  the HTML and as ``Email: …`` in the plain text — in **each** manager's copy, not just the
  owner's;
- **replying works**: ``Reply-To`` is the requester's address, so "Reply" reaches them. There
  is no sentence saying so any more: the field and the ``Reply-To`` are
  the whole of it;
- it is **one way**: the requester's own emails carry no ``Reply-To``, and never the manager's
  address.
"""

from datetime import date
from importlib import import_module

import pytest
from django.core import mail

from core.models import BookingPeriod, Collection, User
from core.services import email_service
from core.services.booking_service import send_booking_request_notifications

# The sentence that used to explain the Reply-To, in the three languages. Kept here as the
# words that must not come back.
GONE_HINTS = {
    "es": "Para escribirle, responde a este correo.",
    "ca": "Per escriure-li, respon aquest correu.",
    "en": "To write to them, reply to this email.",
}
# The catalogues themselves, not `T()`: that falls back to English for a missing key, which
# would hide exactly what these tests are about.
TEXTS = {lang: import_module(f"core.services.email_texts.{lang}").TEXTS for lang in GONE_HINTS}


@pytest.fixture
def team(user, user2, thing, collection):
    """``thing`` in a PROPRIETARY group run by two people — the owner (``user``) and a
    co-curator — asked for by ``user2``, a member. Two managers, two copies."""
    co_curator = User.objects.create(code="CURA01", email="curator@example.com", name="Cura")
    collection.mode = Collection.Mode.PROPRIETARY
    collection.save(update_fields=["mode"])
    collection.invites.add(user2, co_curator)
    collection.co_owners.add(co_curator)
    return user, co_curator, user2


def a_request(thing, requester, owner, *, dates=True, kind="LEND_THING", status="PENDING"):
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


def halves(message):
    return message.body, message.alternatives[0][0]


def sent_to(address):
    return [message for message in mail.outbox if message.to == [address]]


@pytest.mark.django_db
class TestTheRequestEmailEachManagerGets:
    def test_every_managers_copy_has_the_address_as_a_mailto_and_replies_to_it(self, team, thing):
        owner, co_curator, requester = team
        booking = a_request(thing, requester, owner)
        mail.outbox.clear()

        send_booking_request_notifications(requester, thing, booking)

        for manager in (owner, co_curator):
            (message,) = sent_to(manager.email)
            body, html = halves(message)
            assert f'href="mailto:{requester.email}"' in html
            assert f"Email: {requester.email}" in body
            assert message.reply_to == [requester.email]

    def test_it_is_the_request_email_and_still_has_its_decision_links(self, team, thing):
        owner, _, requester = team
        booking = a_request(thing, requester, owner)
        mail.outbox.clear()

        send_booking_request_notifications(requester, thing, booking)

        (message,) = sent_to(owner.email)
        body, html = halves(message)
        # The two decisions are links with the manager's own RSVP tokens, in both halves.
        assert body.count("/rsvp/") == 2
        assert html.count("/rsvp/") >= 2
        assert "Confirm hold" in body and "Decline hold" in body
        assert (
            message.subject == "You have a pending rental request" or "request" in message.subject
        )

    def test_it_holds_for_a_thing_with_no_dates_too(self, team, thing):
        """Every verb: a gift or a sale has no dates and a plainer sentence."""
        owner, _, requester = team
        booking = a_request(thing, requester, owner, dates=False, kind="SELL_THING")
        mail.outbox.clear()

        send_booking_request_notifications(requester, thing, booking)

        (message,) = sent_to(owner.email)
        body, html = halves(message)
        assert f"Email: {requester.email}" in body
        assert f'href="mailto:{requester.email}"' in html
        assert message.reply_to == [requester.email]

    @pytest.mark.parametrize("language", ["es", "ca", "en"])
    def test_there_is_no_sentence_about_replying_in_any_language_but_reply_still_reaches_them(
        self, user, user2, thing, language
    ):
        """The line that explained the Reply-To is gone. The field and
        the Reply-To stay: "Reply" still goes to whoever asked."""
        user.language = language
        user.save(update_fields=["language"])
        booking = a_request(thing, user2, user)
        mail.outbox.clear()

        email_service.send_booking_request_email(
            user2, thing, booking, user.email, "http://x/a", "http://x/r"
        )

        (message,) = mail.outbox
        body, html = halves(message)
        for gone in GONE_HINTS.values():
            assert gone not in body
            assert gone not in html
        assert f"Email: {user2.email}" in body
        assert f'href="mailto:{user2.email}"' in html
        assert message.reply_to == [user2.email]

    def test_the_address_is_under_the_entry_sentence_and_above_the_details(
        self, user, user2, thing
    ):
        booking = a_request(thing, user2, user)
        mail.outbox.clear()

        email_service.send_booking_request_email(
            user2, thing, booking, user.email, "http://x/a", "http://x/r"
        )

        body, html = halves(mail.outbox[0])
        intro = html.index("has sent a")
        address = html.index(f"mailto:{user2.email}")
        dates = html.index("Dates")
        assert intro < address < dates
        # …and in the plain text the address comes after the sentence.
        assert body.index("has sent a") < body.index(f"Email: {user2.email}")

    def test_it_is_one_way_the_requester_gets_no_reply_to_and_never_the_managers_address(
        self, team, thing
    ):
        owner, co_curator, requester = team
        booking = a_request(thing, requester, owner)
        mail.outbox.clear()

        send_booking_request_notifications(requester, thing, booking)

        mine = sent_to(requester.email)
        assert mine, "the requester's own confirmation should have been sent"
        for message in mine:
            assert message.reply_to == []
            for half in halves(message):
                assert owner.email not in half
                assert co_curator.email not in half


@pytest.mark.django_db
class TestTheReservationNotice:
    def _reservation(self, user, user2, thing):
        return a_request(thing, user2, user, kind="RESERVE_THING", status="ACCEPTED")

    def test_it_replies_to_the_requester(self, user, user2, thing):
        booking = self._reservation(user, user2, thing)
        mail.outbox.clear()

        email_service.send_reservation_notice_email(user.email, user2, thing, booking)

        assert mail.outbox[0].reply_to == [user2.email]

    @pytest.mark.parametrize("language", ["es", "ca", "en"])
    def test_it_has_the_address_and_no_sentence_about_replying_in_any_language(
        self, user, user2, thing, language
    ):
        """The Email field and the Reply-To stay, the sentence is gone."""
        user.language = language
        user.save(update_fields=["language"])
        booking = self._reservation(user, user2, thing)
        mail.outbox.clear()

        email_service.send_reservation_notice_email(user.email, user2, thing, booking)

        (message,) = mail.outbox
        body, html = halves(message)
        assert f"Email: {user2.email}" in body
        assert f'href="mailto:{user2.email}"' in html
        for gone in GONE_HINTS.values():
            assert gone not in body
            assert gone not in html
        assert message.reply_to == [user2.email]

    def test_the_address_is_still_a_mailto_and_the_note_is_still_there(self, user, user2, thing):
        booking = self._reservation(user, user2, thing)
        booking.project_note = "Soldering workshop"
        booking.save(update_fields=["project_note"])
        mail.outbox.clear()

        email_service.send_reservation_notice_email(user.email, user2, thing, booking)

        body, html = halves(mail.outbox[0])
        assert f'href="mailto:{user2.email}"' in html
        assert "Soldering workshop" in body and "Soldering workshop" in html

    def test_every_manager_of_the_space_gets_the_reply_to(self, team, thing):
        owner, co_curator, requester = team
        booking = self._reservation(owner, requester, thing)
        mail.outbox.clear()

        for manager in (owner, co_curator):
            email_service.send_reservation_notice_email(manager.email, requester, thing, booking)

        assert [message.reply_to for message in mail.outbox] == [[requester.email]] * 2


class TestTheWordsAreInTheThreeCatalogues:
    @pytest.mark.parametrize("language", ["es", "ca", "en"])
    def test_the_label_is_the_generic_one_and_the_reply_hint_is_gone(self, language):
        texts = TEXTS[language]

        assert texts["requester_email_label"] == "Email"
        assert "requester_reply_hint" not in texts

    @pytest.mark.parametrize("language", ["es", "ca", "en"])
    def test_the_reservation_only_label_is_gone_not_left_beside_the_new_one(self, language):
        assert "reservation_requester_email_label" not in TEXTS[language]
