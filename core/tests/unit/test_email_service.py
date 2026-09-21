"""Unit tests for the email service: resilience and legally-required content.

A failing/slow SMTP provider must never propagate out of the email layer:
user actions whose DB work has already committed must not 500, and
multi-recipient loops must not abort on one bad recipient.

The MIME-structure and legal-footer tests below protect obligations that no
other test in the suite would notice going missing: nothing else renders a
real message and inspects it, so a regression here is silent everywhere else.
"""

import smtplib
from unittest.mock import patch

import pytest
from django.core import mail
from django.test import override_settings

from core.services import email_service


def test_send_returns_false_on_smtp_error():
    """_send swallows an SMTP error and reports failure instead of raising."""
    with patch(
        "core.services.email_service.EmailMultiAlternatives.send",
        side_effect=smtplib.SMTPException("provider down"),
    ):
        result = email_service._send(
            "nobody@example.com",
            "Subject",
            "plain",
            "<p>html</p>",
            email_service.CATEGORY_MANDATORY,
            include_viral=False,
        )
    assert result is False


def test_send_returns_false_on_socket_error():
    """A socket-level error (timeout/connection) is also swallowed."""
    with patch(
        "core.services.email_service.EmailMultiAlternatives.send",
        side_effect=OSError("connection refused"),
    ):
        result = email_service._send(
            "nobody@example.com",
            "Subject",
            "plain",
            "<p>html</p>",
            email_service.CATEGORY_MANDATORY,
            include_viral=False,
        )
    assert result is False


@pytest.mark.django_db
def test_public_send_does_not_raise_when_provider_is_down():
    """A mandatory email (magic link) must not raise when SMTP fails — the
    sign-in action it backs must not 500 because mail is temporarily down.
    Needs DB access now (S2): the viral-line gate looks the recipient up."""
    with patch(
        "core.services.email_service.EmailMultiAlternatives.send",
        side_effect=smtplib.SMTPException("down"),
    ) as mock_send:
        email_service.send_magic_link_email("nobody@example.com", "https://x/verify/ABC123")
    # The send must have been ATTEMPTED — otherwise this test would also pass
    # if the function silently skipped sending, which is a different bug.
    mock_send.assert_called_once()


@pytest.mark.django_db
def test_html_email_embeds_logo_inline():
    """An activity email carries the OIUEEI logo as a CID attachment (S5): one
    inline image attachment on the message, referenced from the HTML
    alternative, plain-text body untouched."""
    email_service.send_invite_rejected_email("Ana", "Ropa de invierno", "owner@example.com")

    assert len(mail.outbox) == 1
    msg = mail.outbox[0]
    assert len(msg.attachments) == 1
    assert msg.attachments[0]["Content-ID"] == "<oiueei-logo>"
    assert msg.attachments[0]["Content-Disposition"].startswith("inline")
    html_body = msg.alternatives[0][0]
    assert "cid:oiueei-logo" in html_body
    assert "cid:oiueei-logo" not in msg.body


@pytest.mark.django_db
def test_logo_send_uses_multipart_related():
    """The CID logo rides in multipart/related, not the default multipart/mixed,
    so Apple Mail renders it once inline instead of also appending a full-size
    copy with a paperclip (S1). The multipart/alternative (plain + html) stays
    nested inside, and the logo keeps its Content-ID."""
    email_service.send_invite_rejected_email("Ana", "Ropa de invierno", "owner@example.com")

    assert len(mail.outbox) == 1
    msg = mail.outbox[0].message()
    assert msg.get_content_type() == "multipart/related"

    # The alternative (plain + html) is nested inside the related wrapper.
    alternative = next(
        part for part in msg.get_payload() if part.get_content_type() == "multipart/alternative"
    )
    subtypes = {part.get_content_type() for part in alternative.get_payload()}
    assert subtypes == {"text/plain", "text/html"}

    # The logo is still inline by CID, now a related sibling of the alternative.
    logo = next(part for part in msg.get_payload() if part["Content-ID"] == "<oiueei-logo>")
    assert logo.get_content_type() == "image/png"


@pytest.mark.django_db
def test_every_email_links_to_the_legal_page():
    """Art. 14 GDPR: every email carries a link to /legal, mandatory ones
    included — this is a disclosure duty, not an opt-out preference, so it
    can't live behind the same category gate as the "manage your emails"
    footer. Proven on a mandatory-category send (the magic link) precisely
    because that is the one category the preferences footer skips."""
    email_service.send_magic_link_email("someone@example.com", "http://localhost:3000/verify/tok")

    html = mail.outbox[0].alternatives[0][0]
    assert 'href="http://localhost:3000/legal"' in html


@pytest.mark.django_db
def test_the_legal_link_follows_the_deployments_own_frontend_url():
    """Not hardcoded to localhost: a deployment sets MAGIC_LINK_BASE_URL to its
    real domain, and every derived link — this one included — has to follow."""
    with override_settings(MAGIC_LINK_BASE_URL="https://oiueei.example/verify"):
        email_service.send_magic_link_email(
            "someone@example.com", "https://oiueei.example/verify/x"
        )

    html = mail.outbox[0].alternatives[0][0]
    assert 'href="https://oiueei.example/legal"' in html


@pytest.mark.django_db
def test_the_legal_link_label_is_translated():
    with override_settings(EMAIL_LANGUAGE="es"):
        email_service.send_magic_link_email(
            "someone@example.com", "http://localhost:3000/verify/tok"
        )

    html = mail.outbox[0].alternatives[0][0]
    assert ">Legal y privacidad<" in html


# --- The magic link: greeting, button, fallback (CA, 2026-09-21) --------------


@pytest.mark.django_db
def test_magic_link_repeats_the_subjects_greeting_in_the_body():
    """The subject names the collection being joined, but an inbox preview
    shows only the subject — the body opens with the same greeting, in bold in
    the HTML, so the message stands on its own once opened (and says *what*
    was joined before asking for the click)."""
    email_service.send_magic_link_email(
        "someone@example.com",
        "http://localhost:3000/verify/tok",
        collection_headline="Chalmercadillo",
    )
    msg = mail.outbox[0]
    assert "welcome to 'Chalmercadillo'" in msg.subject
    assert "welcome to 'Chalmercadillo'" in msg.body
    html = msg.alternatives[0][0]
    # The greeting is the body's own bold headline. Django's autoescape turns
    # the quotes around the name into &#x27; — assert the escaped form, that
    # IS what the reader's client will decode back into 'Chalmercadillo'.
    assert "<strong>Hello, welcome to &#x27;Chalmercadillo&#x27;!</strong>" in html
    # The generic /login variant carries the same structure without a name.
    mail.outbox.clear()
    email_service.send_magic_link_email("someone@example.com", "http://x/verify/t")
    assert "<strong>Hello, welcome to OIUEEI!</strong>" in mail.outbox[0].alternatives[0][0]


@pytest.mark.django_db
def test_magic_link_action_is_a_button_with_the_link_spelled_out():
    """Email clients strip <form>/<button> and ignore CSS custom properties,
    so the CTA is an inline-styled anchor in the app's literal bus blue — and
    the raw link follows as text, because the one click this email exists for
    is exactly what some clients refuse (CA, 2026-09-21)."""
    link = "http://localhost:3000/verify/tok"
    email_service.send_magic_link_email("someone@example.com", link)
    html = mail.outbox[0].alternatives[0][0]
    # The button: the magic link behind a bus-blue, white-text inline-styled
    # anchor — the token styles travel inline or not at all.
    assert (
        f'<a href="{link}" '
        'style="display:inline-block;background-color:#0000bf;color:#ffffff;' in html
    )
    # The fallback sentence, and the URL again as plain copy-pastable text.
    assert "copy and paste this link into your browser" in html
    assert f">{link}</a>" in html
    # The plain-text half never stopped carrying the raw link.
    assert link in mail.outbox[0].body


@pytest.mark.django_db
def test_the_invitation_email_tells_the_recipient_where_their_address_came_from():
    """Art. 14: this address was given to us by the inviter, not by its owner,
    so the invitation — the recipient's first contact with OIUEEI — has to say
    where it came from, what it's for, and that doing nothing ends it. Checked
    in both formats: a client that renders the plain body must not lose it."""
    email_service.send_collection_invite_email(
        "Lala",
        "Tools for the block",
        "invitee@example.com",
        "http://localhost:3000/rsvp/accept",
        "http://localhost:3000/rsvp/reject",
    )

    msg = mail.outbox[0]
    note = "someone invited you"
    assert note in msg.body
    assert note in msg.alternatives[0][0]


@pytest.mark.django_db
def test_the_invitation_source_note_is_translated_too():
    with override_settings(EMAIL_LANGUAGE="ca"):
        email_service.send_collection_invite_email(
            "Lala",
            "Coses del barri",
            "invitee@example.com",
            "http://localhost:3000/rsvp/accept",
            "http://localhost:3000/rsvp/reject",
        )

    assert "no tornes a rebre res nostre" in mail.outbox[0].body


# The OIUEEI mark, exactly as the layout draws it, wherever it appears.
LOGO_IMG = (
    '<img src="cid:oiueei-logo" alt="OIUEEI" height="15" width="53" '
    'style="display:block;width:53px;height:15px;border:0;">'
)


def _assert_the_mark_sits_right_above_the_legal_link(html):
    """The OIUEEI mark closes every message, directly above "Legal & privacy"
    (CA, 2026-09-21): exactly one, and nothing but the legal paragraph between
    them. It used to lead the messages that had no collection header."""
    assert html.count(LOGO_IMG) == 1
    assert html.index(LOGO_IMG) < html.index("Legal")
    assert html[html.index(LOGO_IMG) : html.index("Legal")].count("<p") == 1


# --- The invitation: accept / decline as buttons (CA, 2026-09-21) -------------

INVITE_ACCEPT = "http://localhost:3000/rsvp/accept"
INVITE_REJECT = "http://localhost:3000/rsvp/reject"


def _invitation_html():
    email_service.send_collection_invite_email(
        "Lala", "Tools for the block", "invitee@example.com", INVITE_ACCEPT, INVITE_REJECT
    )
    return mail.outbox[0].alternatives[0][0]


@pytest.mark.django_db
def test_the_invitation_answers_are_a_primary_and_a_secondary_button():
    """Accepting is the filled bus-blue button and declining the outlined one —
    the app's own primary/secondary split, as inline-styled anchors because
    email clients strip <button> and ignore CSS custom properties. They used
    to be two text links on one line, "Accept | Decline", equal in weight."""
    html = _invitation_html()

    primary = (
        f'<a href="{INVITE_ACCEPT}" '
        'style="display:inline-block;background-color:#0000bf;color:#ffffff;'
    )
    secondary = (
        f'<a href="{INVITE_REJECT}" '
        'style="display:inline-block;background-color:#ffffff;color:#000000;'
        "border:2px solid #0000bf;"
    )
    assert primary in html
    assert secondary in html
    # Each label sits inside its own button, accept first.
    assert ">Accept invitation</a>" in html
    assert ">Decline invitation</a>" in html
    assert html.index(primary) < html.index(secondary)
    # The old equal-weight "Accept | Decline" row is gone.
    assert f'<a href="{INVITE_ACCEPT}">Accept invitation</a>' not in html


@pytest.mark.django_db
def test_the_invitation_spells_both_links_out_under_the_buttons():
    """A button some clients will not draw is a dead end, and this email's whole
    job is one of two clicks. Both raw links follow as copy-pastable text —
    accept first, after a sentence saying why — and still before the art. 14
    note, which stays the last thing said."""
    email_service.send_collection_invite_email(
        "Lala", "Tools for the block", "invitee@example.com", INVITE_ACCEPT, INVITE_REJECT
    )
    msg = mail.outbox[0]
    html = msg.alternatives[0][0]

    assert "copy and paste these links into your browser" in html
    accept_text = f">{INVITE_ACCEPT}</a>"
    reject_text = f">{INVITE_REJECT}</a>"
    assert accept_text in html
    assert reject_text in html
    assert html.index("Decline invitation</a>") < html.index("copy and paste these links")
    assert html.index(accept_text) < html.index(reject_text)
    assert html.index(reject_text) < html.index("someone invited you")
    # The plain-text half never stopped carrying both.
    assert INVITE_ACCEPT in msg.body
    assert INVITE_REJECT in msg.body


@pytest.mark.django_db
@pytest.mark.parametrize(
    "lang, phrase",
    [("es", "copia y pega estos enlaces"), ("ca", "copia i enganxa aquests enllaços")],
)
def test_the_invitation_link_fallback_is_translated_too(lang, phrase):
    with override_settings(EMAIL_LANGUAGE=lang):
        html = _invitation_html()

    assert phrase in html


# --- The hold request: confirm / cancel as buttons (CA, 2026-09-21) ----------

HOLD_ACCEPT = "http://localhost:3000/rsvp/confirm"
HOLD_REJECT = "http://localhost:3000/rsvp/cancel"


def _hold_request(user, user2, thing):
    """Send the owner's "someone asked for your thing" email; return the message."""
    from core.models import BookingPeriod

    booking = BookingPeriod.objects.create(
        thing_code=thing,
        thing_type=thing.type,
        requester_code=user2,
        requester_email=user2.email,
        owner_code=user,
        status=BookingPeriod.Status.PENDING,
    )
    email_service.send_booking_request_email(
        user2, thing, booking, user.email, HOLD_ACCEPT, HOLD_REJECT
    )
    return mail.outbox[0]


@pytest.mark.django_db
def test_the_hold_request_answers_are_a_primary_and_a_secondary_button(user, user2, thing):
    """The owner's whole job in this email is one of two clicks, so it gets the
    invitation's shape: confirming is the filled bus-blue button and cancelling
    the outlined one, as inline-styled anchors (email clients strip <button>).
    They used to be two equal text links, "Confirm hold | Cancel hold"."""
    html = _hold_request(user, user2, thing).alternatives[0][0]

    primary = (
        f'<a href="{HOLD_ACCEPT}" '
        'style="display:inline-block;background-color:#0000bf;color:#ffffff;'
    )
    secondary = (
        f'<a href="{HOLD_REJECT}" '
        'style="display:inline-block;background-color:#ffffff;color:#000000;'
        "border:2px solid #0000bf;"
    )
    assert primary in html
    assert secondary in html
    assert ">Confirm hold</a>" in html
    assert ">Cancel hold</a>" in html
    assert html.index(primary) < html.index(secondary)
    # The old equal-weight row is gone.
    assert f'<a href="{HOLD_ACCEPT}">Confirm hold</a>' not in html


@pytest.mark.django_db
def test_the_hold_request_spells_both_links_out_under_the_buttons(user, user2, thing):
    """A button some clients will not draw must not strand the owner: both raw
    links follow as copy-pastable text, confirm first, after a sentence saying
    why. The plain-text half never stopped carrying both."""
    msg = _hold_request(user, user2, thing)
    html = msg.alternatives[0][0]

    assert "copy and paste these links into your browser" in html
    accept_text = f">{HOLD_ACCEPT}</a>"
    reject_text = f">{HOLD_REJECT}</a>"
    assert accept_text in html
    assert reject_text in html
    assert html.index("Cancel hold</a>") < html.index("copy and paste these links")
    assert html.index(accept_text) < html.index(reject_text)
    assert HOLD_ACCEPT in msg.body
    assert HOLD_REJECT in msg.body


@pytest.mark.django_db
@pytest.mark.parametrize(
    "lang, label, phrase",
    [
        ("es", "Confirmar la reserva", "copia y pega estos enlaces"),
        ("ca", "Cancel·lar la reserva", "copia i enganxa aquests enllaços"),
    ],
)
def test_the_hold_request_buttons_and_fallback_are_translated(
    user, user2, thing, lang, label, phrase
):
    with override_settings(EMAIL_LANGUAGE=lang):
        html = _hold_request(user, user2, thing).alternatives[0][0]

    assert f">{label}</a>" in html
    assert phrase in html


# --- The house rule for action buttons (CA, 2026-09-21) ------------------------
#
# The primary action of an email — sign in, open the group, look at the thing —
# is a primary button, never a bare text link. Where an email asks a yes/no
# question, the positive answer is the primary button and the negative the
# secondary one. `_links` is the bare-text-link row; the rule says almost
# nothing may use it.

BUTTON_PRIMARY_START = 'style="display:inline-block;background-color:#0000bf;color:#ffffff;'


def _first_button(url):
    """The `<a>` anchor pointing at `url` that carries the primary button style."""
    return f'<a href="{url}" {BUTTON_PRIMARY_START}'


def test_no_email_action_is_a_bare_text_link_except_the_erasure_one():
    """The rule, enforced on the source so a NEW email cannot quietly break it.

    `_links` draws a row of plain text links. Every email builder that calls it
    must be in the allow-list below; a builder that is not gets told why. The one
    entry is the account-erasure confirmation: a destructive step is deliberately
    not styled as the app's friendliest control, and whether it should be a
    button at all is CA's call, not something to slip through here."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(email_service))
    callers = set()
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef):
            for node in ast.walk(fn):
                if (
                    isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id == "_links"
                ):
                    callers.add(fn.name)
    assert callers == {"send_account_delete_email"}, (
        f"{sorted(callers - {'send_account_delete_email'})} draw a bare text link. "
        "An email's primary action is a primary button (_button); a yes/no pair is "
        "_ctas (primary + secondary)."
    )


def test_a_single_action_button_is_primary_and_has_no_copy_paste_fallback():
    """`_button` is the light version of `_cta`: the button and nothing else —
    no sentence, no raw URL under it (the plain-text half already carries it)."""
    html = email_service._render_email(
        [email_service._button("http://x/go", "Go there")], lang="en"
    )

    assert _first_button("http://x/go") in html
    assert ">Go there</a>" in html
    assert "copy and paste" not in html
    assert ">http://x/go</a>" not in html


@pytest.mark.django_db
def test_signing_back_in_from_the_inactivity_email_is_a_primary_button(user):
    email_service.send_inactivity_warning_email(user, months=24, days=30, will_delete=True)

    html = mail.outbox[0].alternatives[0][0]
    assert _first_button("http://localhost:3000/login") in html


@pytest.mark.django_db
def test_opening_the_group_from_a_digest_is_a_primary_button():
    email_service.send_digest_email("Chalmercadillo", "COL001", ["A chair"], ["a@example.com"])

    html = mail.outbox[0].alternatives[0][0]
    assert _first_button("http://localhost:3000/collections/COL001") in html
    assert f">{email_service.T('view_collection_cta', lang='en')}</a>" in html


@pytest.mark.django_db
def test_opening_the_welcome_document_is_a_primary_button():
    email_service.send_collection_welcome_doc_email(
        "Chalmercadillo", "http://localhost:3000/doc.pdf", "a@example.com"
    )

    html = mail.outbox[0].alternatives[0][0]
    assert _first_button("http://localhost:3000/doc.pdf") in html


@pytest.mark.django_db
def test_the_proposal_answers_are_a_primary_and_a_secondary_button():
    """The owner deciding on a member's suggested guest is the same yes/no as
    the invitation and the hold request: approving is primary, rejecting the
    outlined secondary, both links spelled out after a sentence."""
    approve, reject = "http://localhost:3000/rsvp/yes", "http://localhost:3000/rsvp/no"
    email_service.send_invitation_proposal_email(
        "owner@example.com", "Lala", "Chalmercadillo", "guest@example.com", "", approve, reject
    )

    html = mail.outbox[0].alternatives[0][0]
    assert _first_button(approve) in html
    secondary = (
        f'<a href="{reject}" style="display:inline-block;background-color:#ffffff;'
        "color:#000000;border:2px solid #0000bf;"
    )
    assert secondary in html
    assert html.index(_first_button(approve)) < html.index(secondary)
    assert "copy and paste these links into your browser" in html
    assert f">{approve}</a>" in html and f">{reject}</a>" in html


@pytest.mark.django_db
def test_every_email_declares_its_language_on_the_html_tag():
    """A4: a screen reader picks its pronunciation from `<html lang>`, and
    every email already speaks a specific, known language
    (`resolve_email_language`) — leaving the attribute blank was never
    "unknown", only unstated."""
    email_service.send_magic_link_email("someone@example.com", "http://localhost:3000/verify/tok")

    html = mail.outbox[0].alternatives[0][0]
    assert '<html lang="en">' in html


@pytest.mark.django_db
def test_the_html_lang_attribute_follows_the_recipients_own_language():
    email_service.send_magic_link_email(
        "someone@example.com", "http://localhost:3000/verify/tok", lang="ca"
    )

    html = mail.outbox[0].alternatives[0][0]
    assert '<html lang="ca">' in html


@pytest.mark.django_db
def test_a_sender_with_no_lang_in_scope_still_declares_the_deployment_default():
    # `lang` unset here reaches `_render_email(blocks, lang=None)` for real —
    # the same path an operator-only sender like send_collection_capacity_alarm
    # takes on purpose (no recipient to speak for) — and the tag still has to
    # name a real language, not render lang="".
    with override_settings(EMAIL_LANGUAGE="es"):
        email_service.send_magic_link_email("someone@example.com", "http://localhost:3000/x")

    html = mail.outbox[0].alternatives[0][0]
    assert '<html lang="es">' in html


# --- Dates in emails render DD/MM/YYYY, not ISO ------------------------------


def test_fmt_date_renders_ddmmyyyy_and_tolerates_junk():
    from datetime import date, datetime

    assert email_service._fmt_date(date(2026, 3, 5)) == "05/03/2026"
    assert email_service._fmt_date(datetime(2026, 3, 5, 9, 30)) == "05/03/2026"
    assert email_service._fmt_date("2026-03-05") == "05/03/2026"
    assert email_service._fmt_date("2026-03-05T09:30:00Z") == "05/03/2026"
    assert email_service._fmt_date(None) == ""
    assert email_service._fmt_date("") == ""
    assert email_service._fmt_date("whenever") == "whenever"  # passed through, not dropped


@pytest.mark.django_db
def test_a_dated_booking_email_shows_the_dates_ddmmyyyy(user, user2, thing):
    """The SPA and the date pickers speak DD/MM/YYYY; the emails must match, so
    a member never sees the same booking two ways."""
    from datetime import date

    from core.models import BookingPeriod

    thing.type = "LEND_THING"
    thing.save(update_fields=["type"])
    start, end = date(2026, 3, 5), date(2026, 3, 12)
    booking = BookingPeriod.objects.create(
        thing_code=thing,
        thing_type=thing.type,
        requester_code=user2,
        requester_email=user2.email,
        owner_code=user,
        start_date=start,
        end_date=end,
        status=BookingPeriod.Status.PENDING,
    )

    email_service.send_booking_request_email(
        user2, thing, booking, user.email, "http://x/a", "http://x/r"
    )

    body = mail.outbox[0].body
    html = mail.outbox[0].alternatives[0][0]
    assert "05/03/2026" in body and "12/03/2026" in body
    assert "05/03/2026" in html
    assert "2026-03-05" not in body and "2026-03-05" not in html


# --- The collection name is the header, not the OIUEEI logo -----------------
#
# People recognise the group they're in, not the software. So a collection-
# scoped email leads with the collection name where the logo used to sit; the
# small OIUEEI mark closes every message, right above the legal link.


@pytest.mark.django_db
def test_a_collection_scoped_email_leads_with_the_collection_name(user, user2, thing):
    """The `thing` fixture lives in "Test Collection". A reservation-style email
    about it names that collection at the top, puts the small wordmark at the
    foot above the legal link, and puts the name on the first line of the
    plain body too."""
    from datetime import date

    from core.models import BookingPeriod

    thing.type = "RESERVE_THING"
    thing.save(update_fields=["type"])
    booking = BookingPeriod.objects.create(
        thing_code=thing,
        thing_type=thing.type,
        requester_code=user2,
        requester_email=user2.email,
        owner_code=user,
        start_date=date(2026, 3, 5),
        end_date=date(2026, 3, 6),
        status=BookingPeriod.Status.ACCEPTED,
    )

    email_service.send_reservation_notice_email(user.email, user2, thing, booking)

    msg = mail.outbox[0]
    html = msg.alternatives[0][0]
    # The name is the header: bold, before the body, before the legal link.
    assert "Test Collection" in html
    assert html.index("Test Collection") < html.index("Legal")
    # The wordmark is the small mark, closing the message right above the legal
    # link — after the body, never at the top.
    _assert_the_mark_sits_right_above_the_legal_link(html)
    assert html.index("Test Collection") < html.index(LOGO_IMG)
    # Plain-text body opens with the collection name.
    assert msg.body.startswith("Test Collection")


@pytest.mark.django_db
def test_a_standalone_things_email_has_no_header_and_the_mark_at_the_foot(user, user2):
    """A thing in no collection has no group to name, so nothing leads the
    message but its own content; the small OIUEEI mark still closes it above the
    legal link (CA, 2026-09-21), and nothing is prepended to the plain body."""
    from datetime import date

    from core.models import BookingPeriod, Thing

    loner = Thing.objects.create(code="LONER1", type="LEND_THING", owner=user, headline="Ladder")
    booking = BookingPeriod.objects.create(
        thing_code=loner,
        thing_type=loner.type,
        requester_code=user2,
        requester_email=user2.email,
        owner_code=user,
        start_date=date(2026, 3, 5),
        end_date=date(2026, 3, 12),
        status=BookingPeriod.Status.PENDING,
    )

    email_service.send_booking_request_email(
        user2, loner, booking, user.email, "http://x/a", "http://x/r"
    )

    html = mail.outbox[0].alternatives[0][0]
    _assert_the_mark_sits_right_above_the_legal_link(html)
    # No logo at the top: the body comes first, the mark after it.
    assert html.index("Ladder") < html.index(LOGO_IMG)
    assert not mail.outbox[0].body.startswith("Ladder")


@pytest.mark.django_db
def test_a_non_collection_email_grows_no_header(user):
    """Account-lifecycle mail (here: the erasure link) has no collection, so it
    grows no header — and the mark sits at the foot like everywhere else."""
    email_service.send_account_delete_email(user, "http://x/confirm")

    html = mail.outbox[0].alternatives[0][0]
    _assert_the_mark_sits_right_above_the_legal_link(html)
    assert "font-size:18px;font-weight:700" not in html


@pytest.mark.django_db
def test_every_logo_is_the_small_mark_and_the_file_cannot_be_drawn_giant(user):
    """The OIUEEI mark is 53x15 wherever it appears (CA, 2026-09-21). Apple Mail
    ignored the width/height attributes and drew the old 212x60 file at its
    natural size while Gmail honoured them, so the size is also declared as
    inline CSS, and the attached PNG is small enough that a client which
    ignores both still cannot draw it giant: at most twice the displayed size,
    which is what a retina screen wants anyway."""
    import struct

    email_service.send_account_delete_email(user, "http://x/confirm")

    msg = mail.outbox[0]
    html = msg.alternatives[0][0]
    assert 'height="15" width="53"' in html
    assert "width:53px;height:15px" in html
    assert 'height="30"' not in html
    logo = next(p for p in msg.attachments if p["Content-ID"] == "<oiueei-logo>")
    png = logo.get_payload(decode=True)
    width, height = struct.unpack(">II", png[16:24])
    assert (width, height) == (106, 30)


@pytest.mark.django_db
def test_the_header_speaks_the_readers_language(user):
    """A bilingual collection headline resolves to the reader's own language in
    the header, like every other owner-written value in an email."""
    import json

    from core.models import Collection, User

    catalan = User.objects.create(email="ca@example.com", language="ca")
    collection = Collection.objects.create(
        code="BILN01",
        owner=user,
        headline=json.dumps({"es": "Cosas de casa", "ca": "Coses de casa"}),
    )
    collection.invites.add(catalan)

    email_service.send_collection_revoke_email(
        "Owner", collection.headline, catalan.email, collection=collection
    )

    html = mail.outbox[0].alternatives[0][0]
    assert "Coses de casa" in html and "Cosas de casa" not in html
    # No bold repeat of the name in the body — the header carries it now.
    assert "<strong>Coses de casa</strong>" not in html


# --- _fmt_when: HOUR-unit reservations in the four reservation emails -------
#
# The four RESERVE_THING senders already read "{start} to {end}" / "del
# {start} al {end}" in all three catalogues — no template changed. What
# changed is what `start`/`end` are for an HOUR-unit booking (start_time set):
# the date once, on `start`, then both HH:MM times, so "05/10/2026 10:00 to
# 13:00" reads correctly with no catalogue edits.


def test_fmt_when_a_one_day_reservation_ends_on_that_day():
    """A DAY-unit reservation stores ``end_date = start + duration`` — the day the
    space is free again. The emails used to print it as the end, so a one-day
    reservation on the 5th was "confirmed for 05/10 to 06/10": a day the member
    never booked, and possibly somebody else's."""
    from datetime import date

    from core.models import BookingPeriod

    booking = BookingPeriod(start_date=date(2026, 10, 5), end_date=date(2026, 10, 6))

    assert email_service._fmt_when(booking) == ("05/10/2026", "05/10/2026")


def test_fmt_when_a_multi_day_reservation_ends_on_its_last_day():
    from datetime import date

    from core.models import BookingPeriod

    # Three days from Monday the 5th: the 5th, 6th and 7th.
    booking = BookingPeriod(start_date=date(2026, 10, 5), end_date=date(2026, 10, 8))

    assert email_service._fmt_when(booking) == ("05/10/2026", "07/10/2026")


def test_fmt_when_an_hourly_booking_names_the_date_once_and_two_times():
    from datetime import date, time

    from core.models import BookingPeriod

    booking = BookingPeriod(
        start_date=date(2026, 10, 5),
        end_date=date(2026, 10, 6),  # the day-based "free again" marker, unused here
        start_time=time(10, 0),
        end_time=time(13, 0),
    )

    assert email_service._fmt_when(booking) == ("05/10/2026 10:00", "13:00")


@pytest.mark.django_db
def test_an_hourly_reservation_confirmation_reads_correctly_in_all_three_languages(
    user, user2, thing
):
    from datetime import date, time

    from core.models import BookingPeriod

    thing.type = "RESERVE_THING"
    thing.save(update_fields=["type"])
    booking = BookingPeriod.objects.create(
        thing_code=thing,
        thing_type=thing.type,
        requester_code=user2,
        requester_email=user2.email,
        owner_code=user,
        start_date=date(2026, 10, 5),
        end_date=date(2026, 10, 6),
        start_time=time(10, 0),
        end_time=time(13, 0),
        status=BookingPeriod.Status.ACCEPTED,
    )

    expectations = {
        "en": "05/10/2026 10:00 to 13:00",
        "es": "del 05/10/2026 10:00 al 13:00",
        "ca": "del 05/10/2026 10:00 al 13:00",
    }
    for lang, phrase in expectations.items():
        mail.outbox.clear()
        with override_settings(EMAIL_LANGUAGE=lang):
            email_service.send_reservation_confirmed_email(user2, thing, booking)
        body = mail.outbox[0].body
        assert phrase in body, f"{lang}: {phrase!r} not in {body!r}"


@pytest.mark.django_db
def test_a_day_reservation_confirmation_names_the_days_booked_and_no_other(user, user2, thing):
    from datetime import date

    from core.models import BookingPeriod

    thing.type = "RESERVE_THING"
    thing.save(update_fields=["type"])
    booking = BookingPeriod.objects.create(
        thing_code=thing,
        thing_type=thing.type,
        requester_code=user2,
        requester_email=user2.email,
        owner_code=user,
        start_date=date(2026, 10, 5),
        end_date=date(2026, 10, 7),  # two days: the 5th and the 6th
        status=BookingPeriod.Status.ACCEPTED,
    )

    email_service.send_reservation_confirmed_email(user2, thing, booking)

    sent = mail.outbox[0]
    for part in (sent.body, sent.alternatives[0][0]):
        assert "06/10/2026" in part
        assert "07/10/2026" not in part


# --- The owner's email note (Collection.email_note) ------------------------------


def test_note_blocks_renders_bold_links_lists_and_emojis():
    """The subset a 512-char note actually needs, rendered to one md block."""
    plain, blocks = email_service._note_blocks(
        "Hola! **Léenos** 🛠️\n"
        "\n"
        "- Trae tu [carnet](https://example.com/reglas)\n"
        "- Planta 2\n"
        "\n"
        "1. Confirma\n"
        "2. Llega pronto"
    )
    # The plain half is the raw Markdown — the standard text/plain alternative.
    assert plain.startswith("Hola! **Léenos**")
    assert len(blocks) == 1 and blocks[0]["type"] == "md"
    html = str(blocks[0]["html"])
    assert "<p>Hola! <strong>Léenos</strong> 🛠️</p>" in html
    expected_list = (
        '<ul><li>Trae tu <a href="https://example.com/reglas">carnet</a> (example.com)</li>'
        "<li>Planta 2</li></ul>"
    )
    assert expected_list in html
    assert "<ol><li>Confirma</li><li>Llega pronto</li></ol>" in html


def test_note_blocks_leaves_an_unsafe_url_as_literal_text():
    """A javascript: 'link' is not a link in the email — a dead href="#"
    would be worse than the raw text (the deliberate divergence from the
    frontend's sanitizeUrl)."""
    _, blocks = email_service._note_blocks("mira [esto](javascript:alert(1))")
    html = str(blocks[0]["html"])
    assert "<a " not in html
    assert "[esto](javascript:alert(1))" in html


def test_a_link_dressed_as_another_address_names_where_it_really_goes():
    """The owner picks both the text and the target, and the email leaves from
    the operator's own domain — so text that looks like the operator's sign-in
    link must not be all the reader sees."""
    _, blocks = email_service._note_blocks(
        "[https://www.oiueei.com/verify/abc](https://elsewhere.example/verify)"
    )
    html = str(blocks[0]["html"])
    assert html == (
        '<p><a href="https://elsewhere.example/verify">https://www.oiueei.com/verify/abc</a>'
        " (elsewhere.example)</p>"
    )


def test_a_link_whose_text_is_its_own_url_needs_no_host():
    _, blocks = email_service._note_blocks(
        "[https://example.com/a?b=1&c=2](https://example.com/a?b=1&c=2)"
    )
    html = str(blocks[0]["html"])
    # Escaped once — the & survives as one &amp;, never &amp;amp; — and no
    # "(example.com)" repeating what the text already says.
    assert html == (
        '<p><a href="https://example.com/a?b=1&amp;c=2">https://example.com/a?b=1&amp;c=2</a></p>'
    )


def test_a_lookalike_host_is_named_in_punycode():
    # "еxample.com" with a Cyrillic е: shown as itself it would pass for the
    # real name; in ASCII it cannot.
    _, blocks = email_service._note_blocks("[rules](https://\u0435xample.com/rules)")
    html = str(blocks[0]["html"])
    assert "(xn--xample-2of.com)" in html
    assert "(\u0435xample.com)" not in html


def test_a_link_with_no_host_stays_literal_text():
    _, blocks = email_service._note_blocks("mira [esto](https://)")
    html = str(blocks[0]["html"])
    assert "<a " not in html
    assert "[esto](https://)" in html


@pytest.mark.parametrize(
    "url",
    [
        "https://[oops/normas",  # an unclosed IPv6 bracket: urlsplit raises ValueError
        "https://" + "a" * 64 + ".example/normas",  # a 64-char label: IDNA raises UnicodeError
    ],
)
def test_a_link_whose_host_cannot_be_read_stays_literal_text(url):
    """An owner can type either of these by accident. Both make the host
    lookup raise; the note must still render — as the literal text the owner
    wrote — or every email carrying it would fail to send."""
    _, blocks = email_service._note_blocks(f"Normas: [aquí]({url})")
    html = str(blocks[0]["html"])
    assert "<a " not in html
    assert f"[aquí]({url})" in html


def test_note_blocks_escapes_html_before_transforming(collection):
    """Raw HTML reaching the renderer (only possible bypassing the serializer,
    e.g. the admin) must render inert — and a typed NUL must not be able to
    forge an anchor placeholder. The NUL half never goes through the DB:
    PostgreSQL text columns cannot hold a NUL byte (CI runs Postgres; local
    SQLite would swallow it and the test would only ever prove the happy
    path), so it exercises the renderer directly instead."""
    collection.email_note = "<script>alert(1)</script> ok"
    collection.save(update_fields=["email_note"])
    _, blocks = email_service._note_blocks(collection.email_note)
    html = str(blocks[0]["html"])
    assert "<script>" not in html
    assert "&lt;script&gt;" in html

    # The NUL case needs no stored value — the stripping is the renderer's.
    _, blocks = email_service._note_blocks("<b>bold?</b> ok\x00")
    html = str(blocks[0]["html"])
    assert "\x00" not in html
    assert "&lt;b&gt;" in html


def test_note_blocks_is_empty_for_blank_text():
    assert email_service._note_blocks("") == ("", [])
    assert email_service._note_blocks(None) == ("", [])
    assert email_service._note_blocks("   \n  ") == ("", [])


@pytest.mark.django_db
def test_the_reservation_confirmation_embeds_the_note_after_the_listing_link(
    user, user2, thing, collection
):
    """With no note nothing is added; setting one inserts the rendered block
    after the listing link and the raw Markdown after the body — both before
    the appended viral line / footers, by construction of _send."""
    from datetime import date

    from core.models import BookingPeriod

    thing.type = "RESERVE_THING"
    thing.save(update_fields=["type"])
    booking = BookingPeriod.objects.create(
        thing_code=thing,
        thing_type=thing.type,
        requester_code=user2,
        requester_email=user2.email,
        owner_code=user,
        start_date=date(2026, 10, 5),
        end_date=date(2026, 10, 6),
        status=BookingPeriod.Status.ACCEPTED,
    )

    mail.outbox.clear()
    email_service.send_reservation_confirmed_email(user2, thing, booking, collection)
    plain_before = mail.outbox[0].body
    html_before = mail.outbox[0].alternatives[0][0]
    # No note: nothing appended to either half.
    assert "Trae el" not in plain_before
    assert "Trae el" not in html_before

    collection.email_note = "Trae el **carnet** 🛠️"
    collection.save(update_fields=["email_note"])
    mail.outbox.clear()
    email_service.send_reservation_confirmed_email(user2, thing, booking, collection)
    plain_after = mail.outbox[0].body
    html_after = mail.outbox[0].alternatives[0][0]

    assert "Trae el **carnet** 🛠️" in plain_after  # raw Markdown in text/plain
    note_html = "<p>Trae el <strong>carnet</strong> 🛠️</p>"
    assert note_html in html_after
    # Position, both halves: after the listing link, before the footers.
    thing_url = email_service._thing_url(thing)
    assert (
        plain_after.index(thing_url)
        < plain_after.index("Trae el **carnet** 🛠️")
        < plain_after.index("/me/notifications/")
    )
    assert html_after.index(thing_url) < html_after.index(note_html) < html_after.index("/legal")


@pytest.mark.django_db
def test_the_booking_confirmation_embeds_the_note_too(user, user2, thing, collection):
    """The LEND/RENT 'we've let the owner know' email carries the note of the
    collection the request was made through — the new `collection` param —
    while its language stays recipient-only (pinned in test_email_hierarchy)."""
    from core.models import BookingPeriod

    booking = BookingPeriod.objects.create(
        thing_code=thing,
        thing_type=thing.type,
        requester_code=user2,
        requester_email=user2.email,
        owner_code=user,
        status=BookingPeriod.Status.PENDING,
    )

    collection.email_note = "Confirmamos en **48h**"
    collection.save(update_fields=["email_note"])
    mail.outbox.clear()
    email_service.send_booking_confirmation_email(user2, thing, booking, collection)

    html = mail.outbox[0].alternatives[0][0]
    note_html = "<p>Confirmamos en <strong>48h</strong></p>"
    assert note_html in html
    assert "Confirmamos en **48h**" in mail.outbox[0].body
    # The param is optional and defaults to no note — the pre-feature callers
    # (and any direct call without a collection) must keep working.
    mail.outbox.clear()
    email_service.send_booking_confirmation_email(user2, thing, booking)
    assert note_html not in mail.outbox[0].alternatives[0][0]


@pytest.mark.django_db
def test_the_note_is_resolved_per_recipient_language(user, user2, thing, collection):
    """A bilingual note reaches each member in their own language — the same
    `L` every other owner content goes through."""
    from datetime import date

    from core.models import BookingPeriod

    collection.email_note = '{"es": "Trae el carnet", "ca": "Porta el carnet"}'
    collection.save(update_fields=["email_note"])
    thing.type = "RESERVE_THING"
    thing.save(update_fields=["type"])
    booking = BookingPeriod.objects.create(
        thing_code=thing,
        thing_type=thing.type,
        requester_code=user2,
        requester_email=user2.email,
        owner_code=user,
        start_date=date(2026, 10, 5),
        end_date=date(2026, 10, 6),
        status=BookingPeriod.Status.ACCEPTED,
    )

    user2.language = "ca"
    user2.save(update_fields=["language"])
    mail.outbox.clear()
    email_service.send_reservation_confirmed_email(user2, thing, booking, collection)
    html = mail.outbox[0].alternatives[0][0]
    assert "Porta el carnet" in html
    assert "Trae el carnet" not in html


@pytest.mark.django_db
def test_the_acceptance_decision_carries_the_note_but_a_refusal_does_not(
    user, user2, thing, collection
):
    """An acceptance is the requester-facing confirmation for GIFT/SELL/LEND/
    RENT — the sibling of RESERVE's auto-confirm — so the note rides it. A
    refusal has no next steps for the note's prose to describe."""
    from core.models import BookingPeriod

    collection.email_note = "Recogida en **planta 2**"
    collection.save(update_fields=["email_note"])
    booking = BookingPeriod.objects.create(
        thing_code=thing,
        thing_type=thing.type,
        requester_code=user2,
        requester_email=user2.email,
        owner_code=user,
        status=BookingPeriod.Status.PENDING,
    )

    mail.outbox.clear()
    email_service.send_booking_decision_email(booking, thing, accepted=True, collection=collection)
    assert "Recogida en <strong>planta 2</strong>" in mail.outbox[0].alternatives[0][0]
    assert "Recogida en **planta 2**" in mail.outbox[0].body

    mail.outbox.clear()
    email_service.send_booking_decision_email(booking, thing, accepted=False, collection=collection)
    assert "Recogida en" not in mail.outbox[0].alternatives[0][0]
    assert "Recogida en" not in mail.outbox[0].body


@pytest.mark.django_db
def test_the_decision_takes_no_note_from_a_collection_it_was_not_given(
    user, user2, thing, collection
):
    """The note's collection is the caller's to resolve for this requester
    (`finalize_booking_decision`, among collections they may read). Given
    none, the email carries none — it no longer falls back to the thing's
    first collection, which can be a private group the requester isn't in."""
    from core.models import BookingPeriod

    collection.email_note = "Recogida en **planta 2**"
    collection.save(update_fields=["email_note"])
    booking = BookingPeriod.objects.create(
        thing_code=thing,
        thing_type=thing.type,
        requester_code=user2,
        requester_email=user2.email,
        owner_code=user,
        status=BookingPeriod.Status.PENDING,
    )

    mail.outbox.clear()
    email_service.send_booking_decision_email(booking, thing, accepted=True)
    assert "Recogida en" not in mail.outbox[0].alternatives[0][0]
    assert "Recogida en" not in mail.outbox[0].body
