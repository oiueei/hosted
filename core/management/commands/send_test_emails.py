"""Send one sample of every email OIUEEI can send to an address you choose.

    python manage.py send_test_emails --to you@example.com
    python manage.py send_test_emails --to you@example.com --lang ca --only booking
    python manage.py send_test_emails --list

Why it exists: an email is the one part of the product that cannot be looked at
in a browser or a test — the client decides how it draws (Apple Mail ignored a
logo's size that Gmail honoured; some clients strip buttons), so it has to be
opened in the client. This sends the real builders, with realistic sample data,
so that can be done for every email in one sitting.

**It can only ever mail the address you pass.** Every message is rewritten on its
way out — recipient forced to ``--to``, Cc/Bcc dropped — so it does not matter how
a builder works out its recipients (the capacity alarm mails the superusers, the
contact form the operator): none of it can reach anyone else. Each subject is
prefixed ``[TEST 07/34 booking_request]`` so the messages sort and tell
themselves apart.

**It leaves nothing behind.** The sample users, collections, things and bookings
are created inside a transaction that is rolled back at the end. That includes
``--to`` itself: if it already belongs to a real account, that account is used —
with its language and notification preferences overridden for the run — and
restored by the rollback, so the emails render as any recipient would see them
(footer link, opt-outs off) whoever you are.

**The buttons are decoys.** The links point at the deployment's real address but
carry sample tokens, so they will not do anything when clicked. What is being
tested is how the message looks and reads, not what its links do.

Sending for real (an SMTP backend) needs ``--yes``, so a typo in ``--to`` cannot
send 34 emails by accident; the console backend needs nothing.
"""

import time
from dataclasses import dataclass
from datetime import date, timedelta
from datetime import time as dtime
from typing import Callable

from django.conf import settings
from django.core import mail
from django.core.mail.backends.base import BaseEmailBackend
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.test.utils import override_settings

from core.models import BookingPeriod, Collection, Thing, User
from core.services import email_service as es

LANGS = ("es", "ca", "en")

# Backends that put nothing on the wire: no confirmation needed for these.
HARMLESS_BACKENDS = ("console", "locmem", "filebased", "dummy")


class TestSendBackend(BaseEmailBackend):
    """Wraps the real backend and rewrites every message on the way out: one
    recipient, no Cc/Bcc, a tagged subject. The real backend's dotted path, the
    address and the current label are class attributes because Django builds a
    fresh backend instance per connection."""

    __test__ = False  # pytest: not a test class, despite the name

    real_backend = None
    target = None
    label = ""

    def send_messages(self, email_messages):
        for message in email_messages:
            message.subject = f"[TEST {self.label}] {message.subject}"
            message.to = [self.target]
            message.cc = []
            message.bcc = []
        real = mail.get_connection(self.real_backend, fail_silently=self.fail_silently)
        return real.send_messages(email_messages) or 0


@dataclass(frozen=True)
class Sample:
    """One email to send: its name, the ``email_service`` function it exercises
    (so a test can prove none is missing) and how to call it."""

    name: str
    covers: str
    send: Callable


SAMPLES = []


def sample(name, covers):
    def register(fn):
        SAMPLES.append(Sample(name, covers, fn))
        return fn

    return register


class World:
    """The sample data every builder draws on, created once per language."""

    def __init__(self, to, lang):
        self.to = to
        self.lang = lang
        today = date.today()
        self.start = today + timedelta(days=7)
        self.end = today + timedelta(days=10)

        # The recipient. An existing account is used as it is (and put back by the
        # rollback); a new address gets a throwaway one. Either way the language
        # and the notification switches are forced, so what arrives is what a
        # fresh recipient would get and not whatever this account happened to set.
        self.me, _ = User.objects.get_or_create(email=to, defaults={"name": "Tú"})
        self.me.language = lang
        self.me.notify_activity = True
        self.me.notify_news = True
        self.me.save()

        self.owner = User.objects.create(email="lala.sample@example.com", name="Lala")
        self.member = User.objects.create(email="lele.sample@example.com", name="Lele")

        self.collection = Collection.objects.create(
            owner=self.owner,
            headline="Chalmercadillo",
            description="El mercadillo de los domingos en el patio.",
            language=lang,
            email_note=(
                "**Cómo recoger:** pásate el domingo entre las 11 y las 13 h. "
                "Pregunta por Lala en el patio."
            ),
        )
        self.collection.invites.add(self.me, self.member)

        self.gift = self._thing(Thing.Type.GIFT_THING, "Silla de madera")
        self.lend = self._thing(Thing.Type.LEND_THING, "Escalera de mano", location="Planta baja")

        self.rooms = Collection.objects.create(
            owner=self.owner,
            headline="Sala polivalente",
            language=lang,
            allowed_thing_types=[Thing.Type.RESERVE_THING],
        )
        self.reserve = Thing.objects.create(
            type=Thing.Type.RESERVE_THING,
            owner=self.owner,
            headline="Sala polivalente",
            location="Planta 1, sala 2",
            fee="5.00",
        )
        self.rooms.things.add(self.reserve)

    def _thing(self, kind, headline, **extra):
        thing = Thing.objects.create(type=kind, owner=self.owner, headline=headline, **extra)
        self.collection.things.add(thing)
        return thing

    def link(self, path):
        """A link on the deployment's own address with a sample token: it looks
        right and does nothing."""
        return f"{es._frontend_base_url()}/{path}/SAMPLE"

    def booking(self, thing, requester, *, dated=True, times=False, accepted=False):
        kwargs = {}
        if dated:
            kwargs.update(start_date=self.start, end_date=self.end)
        if times:
            kwargs.update(
                start_date=self.start,
                end_date=self.start + timedelta(days=1),
                start_time=dtime(11, 0),
                end_time=dtime(13, 0),
            )
        return BookingPeriod.objects.create(
            thing_code=thing,
            thing_type=thing.type,
            requester_code=requester,
            requester_email=requester.email,
            owner_code=self.owner,
            status=BookingPeriod.Status.ACCEPTED if accepted else BookingPeriod.Status.PENDING,
            **kwargs,
        )


# --- Category 1: mandatory ---------------------------------------------------------


@sample("magic_link", "send_magic_link_email")
def _(w):
    es.send_magic_link_email(w.to, w.link("verify"), lang=w.lang)


@sample("magic_link_joining_a_group", "send_magic_link_email")
def _(w):
    es.send_magic_link_email(
        w.to, w.link("verify"), collection_headline="Chalmercadillo", lang=w.lang
    )


@sample("collection_invite", "send_collection_invite_email")
def _(w):
    es.send_collection_invite_email(
        "Lala", "Chalmercadillo", w.to, w.link("rsvp"), w.link("rsvp"), collection=w.collection
    )


@sample("collection_invite_recommended", "send_collection_invite_email")
def _(w):
    es.send_collection_invite_email(
        "Lala",
        "Chalmercadillo",
        w.to,
        w.link("rsvp"),
        w.link("rsvp"),
        collection=w.collection,
        proposer_name="Lele",
    )


@sample("collection_welcome_doc", "send_collection_welcome_doc_email")
def _(w):
    es.send_collection_welcome_doc_email(
        "Chalmercadillo", f"{es._frontend_base_url()}/normas.pdf", w.to, collection=w.collection
    )


@sample("collection_revoke", "send_collection_revoke_email")
def _(w):
    es.send_collection_revoke_email("Lala", "Chalmercadillo", w.to, collection=w.collection)


@sample("account_delete", "send_account_delete_email")
def _(w):
    es.send_account_delete_email(w.me, w.link("verify"))


@sample("inactivity_will_delete", "send_inactivity_warning_email")
def _(w):
    es.send_inactivity_warning_email(w.me, months=24, days=30, will_delete=True)


@sample("inactivity_account_kept", "send_inactivity_warning_email")
def _(w):
    es.send_inactivity_warning_email(w.me, months=24, days=30, will_delete=False)


# --- Category 2: activity ----------------------------------------------------------


@sample("invitation_proposal", "send_invitation_proposal_email")
def _(w):
    es.send_invitation_proposal_email(
        w.to,
        "Lele",
        "Chalmercadillo",
        "amiga.de.lele@example.com",
        "Vive en mi escalera y le encantaría participar.",
        w.link("rsvp"),
        w.link("rsvp"),
        collection=w.collection,
    )


@sample("proposal_declined", "send_proposal_declined_email")
def _(w):
    es.send_proposal_declined_email(
        w.to, "Lala", "Chalmercadillo", "amiga.de.lele@example.com", collection=w.collection
    )


@sample("invite_rejected", "send_invite_rejected_email")
def _(w):
    es.send_invite_rejected_email("Lele", "Chalmercadillo", w.to, collection=w.collection)


@sample("booking_request", "send_booking_request_email")
def _(w):
    es.send_booking_request_email(
        w.member, w.lend, w.booking(w.lend, w.member), w.to, w.link("rsvp"), w.link("rsvp")
    )


@sample("booking_request_gift", "send_booking_request_email")
def _(w):
    es.send_booking_request_email(
        w.member,
        w.gift,
        w.booking(w.gift, w.member, dated=False),
        w.to,
        w.link("rsvp"),
        w.link("rsvp"),
    )


@sample("booking_confirmed", "send_booking_decision_email")
def _(w):
    es.send_booking_decision_email(
        w.booking(w.lend, w.me, accepted=True), w.lend, accepted=True, collection=w.collection
    )


@sample("booking_declined", "send_booking_decision_email")
def _(w):
    es.send_booking_decision_email(
        w.booking(w.lend, w.me), w.lend, accepted=False, collection=w.collection
    )


@sample("booking_confirmation", "send_booking_confirmation_email")
def _(w):
    es.send_booking_confirmation_email(
        w.me, w.lend, w.booking(w.lend, w.me, accepted=True), collection=w.collection
    )


@sample("faq_question", "send_faq_question_email")
def _(w):
    es.send_faq_question_email("Lele", w.gift, "¿Sigue disponible?", w.to)


@sample("faq_answer", "send_faq_answer_email")
def _(w):
    es.send_faq_answer_email("Lala", w.gift, "¿Sigue disponible?", "Sí, ven a por ella.", w.to)


@sample("faq_hide", "send_faq_hide_email")
def _(w):
    es.send_faq_hide_email("Lala", w.gift, "¿Sigue disponible?", w.to)


@sample("thing_reported", "send_thing_reported_email")
def _(w):
    es.send_thing_reported_email(w.gift, w.to)


@sample("return_reminder_to_owner", "send_return_reminder_email")
def _(w):
    es.send_return_reminder_email("Lele", w.lend, w.end, w.to)


@sample("return_due_to_borrower", "send_return_due_email")
def _(w):
    es.send_return_due_email("Lala", w.lend, w.end, w.to)


@sample("reservation_confirmed", "send_reservation_confirmed_email")
def _(w):
    es.send_reservation_confirmed_email(
        w.me, w.reserve, w.booking(w.reserve, w.me, accepted=True), collection=w.rooms
    )


@sample("reservation_confirmed_hourly", "send_reservation_confirmed_email")
def _(w):
    es.send_reservation_confirmed_email(
        w.me,
        w.reserve,
        w.booking(w.reserve, w.me, dated=False, times=True, accepted=True),
        collection=w.rooms,
    )


@sample("reservation_notice_to_owner", "send_reservation_notice_email")
def _(w):
    es.send_reservation_notice_email(
        w.to, w.member, w.reserve, w.booking(w.reserve, w.member, accepted=True), collection=w.rooms
    )


@sample("reservation_cancelled_by_owner", "send_reservation_cancelled_email")
def _(w):
    es.send_reservation_cancelled_email(
        w.to, "Lala", w.reserve, w.booking(w.reserve, w.me), cancelled_by_owner=True
    )


@sample("reservation_cancelled_by_guest", "send_reservation_cancelled_email")
def _(w):
    es.send_reservation_cancelled_email(
        w.to, "Lele", w.reserve, w.booking(w.reserve, w.member), cancelled_by_owner=False
    )


@sample("reservation_reminder", "send_reservation_reminder_email")
def _(w):
    es.send_reservation_reminder_email(w.to, w.reserve, w.booking(w.reserve, w.me, accepted=True))


@sample("email_note_test", "send_email_note_test_email")
def _(w):
    es.send_email_note_test_email(w.me, w.collection, w.collection.email_note)


@sample("broadcast", "send_broadcast_email")
def _(w):
    es.send_broadcast_email(
        "Lala",
        w.owner.email,
        "Chalmercadillo",
        w.collection.code,
        "Este domingo hay mercadillo doble: traed lo que os sobre.",
        [w.to],
        collection=w.collection,
    )


# --- Category 3: news --------------------------------------------------------------


@sample("digest", "send_digest_email")
def _(w):
    es.send_digest_email(
        "Chalmercadillo",
        w.collection.code,
        ["Silla de madera", "Escalera de mano"],
        [w.to],
        collection=w.collection,
    )


# --- Operator mail -----------------------------------------------------------------


@sample("contact_form", "send_contact_email")
def _(w):
    es.send_contact_email("Lele", "lele.sample@example.com", "No consigo entrar en mi cuenta.")


@sample("collaboration_form", "send_contact_email")
def _(w):
    es.send_contact_email(
        "Lele", "lele.sample@example.com", "Me gustaría colaborar con el diseño.", kind="collab"
    )


@sample("capacity_alarm", "send_collection_capacity_alarm")
def _(w):
    es.send_collection_capacity_alarm(w.collection, "things", 5000, 4000)


class Command(BaseCommand):
    help = "Send one sample of every email to an address you choose (see the module docstring)."

    def add_arguments(self, parser):
        parser.add_argument("--to", help="The one address every sample is sent to. Required.")
        parser.add_argument(
            "--lang",
            default="es",
            choices=LANGS + ("all",),
            help="Language of the samples; 'all' sends every email in es, ca and en (default es).",
        )
        parser.add_argument(
            "--only",
            help="Only the samples whose name contains this text (e.g. 'booking', 'invite').",
        )
        parser.add_argument("--list", action="store_true", help="List the samples and stop.")
        parser.add_argument(
            "--yes",
            action="store_true",
            help="Confirm a real send (an SMTP backend). Not needed for the console.",
        )
        parser.add_argument(
            "--delay",
            type=float,
            default=1.0,
            help="Seconds between sends on a real backend, so the provider is not hammered.",
        )

    def handle(self, *args, **opts):
        chosen = [s for s in SAMPLES if not opts["only"] or opts["only"] in s.name]
        if opts["list"]:
            for i, s in enumerate(chosen, 1):
                self.stdout.write(f"{i:>2}  {s.name:<34} {s.covers}")
            self.stdout.write(f"\n{len(chosen)} samples")
            return

        to = (opts["to"] or "").strip()
        if not to or "@" not in to:
            raise CommandError("--to is required: the one address every sample is sent to.")
        if not chosen:
            raise CommandError(f"No sample matches --only {opts['only']!r}. Try --list.")

        langs = LANGS if opts["lang"] == "all" else (opts["lang"],)
        total = len(chosen) * len(langs)
        real_backend = settings.EMAIL_BACKEND
        harmless = any(kind in real_backend for kind in HARMLESS_BACKENDS)
        if not harmless and not opts["yes"]:
            raise CommandError(
                f"This would really send {total} emails to {to} through {real_backend}.\n"
                "Run it again with --yes to confirm."
            )

        self.stdout.write(
            f"Sending {total} sample emails to {to} "
            f"({', '.join(langs)}) through {real_backend.rsplit('.', 2)[-2]}.\n"
        )

        TestSendBackend.real_backend = real_backend
        TestSendBackend.target = to
        sent = 0
        with override_settings(EMAIL_BACKEND=f"{__name__}.TestSendBackend", EMAIL_SEND_ASYNC=False):
            for lang in langs:
                # One rolled-back transaction per language: the data is built for
                # that language and nothing survives it.
                with override_settings(EMAIL_LANGUAGE=lang):
                    sent += self._send_language(chosen, to, lang, total, sent, opts, harmless)
        self.stdout.write(self.style.SUCCESS(f"\nDone: {sent} of {total} emails sent to {to}."))

    def _send_language(self, chosen, to, lang, total, done, opts, harmless):
        sent = 0
        try:
            with transaction.atomic():
                world = World(to, lang)
                for sample_ in chosen:
                    number = done + sent + 1
                    TestSendBackend.label = f"{number:02d}/{total} {lang} {sample_.name}"
                    try:
                        sample_.send(world)
                        sent += 1
                        self.stdout.write(f"  {TestSendBackend.label}")
                    except Exception as exc:  # noqa: BLE001 — report and carry on
                        self.stderr.write(
                            self.style.ERROR(f"  {TestSendBackend.label}  FAILED: {exc!r}")
                        )
                    if not harmless and opts["delay"]:
                        time.sleep(opts["delay"])
                # Nothing of the sample world is kept, the recipient's account
                # (if it has one) included.
                transaction.set_rollback(True)
        finally:
            TestSendBackend.label = ""
        return sent
