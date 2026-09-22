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
    shows only the subject — the body opens with the same greeting, so the
    message stands on its own once opened (and says *what* was joined before
    asking for the click). The collection is also this email's <h1> parent
    now (CA, 2026-09-22), so the name appears twice — once as the title, once
    in the sentence beneath it."""
    email_service.send_magic_link_email(
        "someone@example.com",
        "http://localhost:3000/verify/tok",
        collection_headline="Chalmercadillo",
    )
    msg = mail.outbox[0]
    assert "welcome to 'Chalmercadillo'" in msg.subject
    assert "welcome to 'Chalmercadillo'" in msg.body
    html = msg.alternatives[0][0]
    # Django's autoescape turns the quotes around the name into &#x27; — assert
    # the escaped form, that IS what the reader's client will decode back into
    # 'Chalmercadillo'.
    assert "<h1" in html and ">Chalmercadillo</h1>" in html
    assert "Hello, welcome to &#x27;Chalmercadillo&#x27;!" in html
    assert html.index(">Chalmercadillo</h1>") < html.index("Hello, welcome")
    # The generic /login variant has no collection to be its parent: OIUEEI is,
    # with its own one-line pitch as the intro.
    mail.outbox.clear()
    email_service.send_magic_link_email("someone@example.com", "http://x/verify/t")
    generic_html = mail.outbox[0].alternatives[0][0]
    # No collection to be the parent: the mark itself leads as the <h1>
    # (CA, 2026-09-22), not the literal word "OIUEEI".
    assert GENERIC_H1_LOGO_IMG in generic_html
    assert email_service.T("generic_parent_pitch", lang="en") in generic_html
    assert "Hello, welcome to OIUEEI!" in generic_html
    assert generic_html.index(GENERIC_H1_LOGO_IMG) < generic_html.index(
        email_service.T("generic_parent_pitch", lang="en")
    )


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


# The OIUEEI mark as the footer draws it (60x17, CA's own numbers, 2026-09-22
# third review round) — the small size, wherever a non-generic email's footer
# still carries it. The generic "OIUEEI" parent case is different: the mark
# moves to the <h1>, bigger (see GENERIC_H1_LOGO_IMG / test_a_no_parent_email_...),
# and the footer carries none.
LOGO_IMG = (
    '<img src="cid:oiueei-logo" alt="OIUEEI" height="17" width="60" '
    'style="display:block;width:60px;height:17px;margin-bottom:15px;border:0;">'
)

# The mark as the <h1> draws it for a GENERIC_PARENT ("OIUEEI") email — 162x46
# (CA's own numbers), since the mark itself is the title there.
GENERIC_H1_LOGO_IMG = (
    '<img src="cid:oiueei-logo" alt="OIUEEI" height="46" width="162" '
    'style="display:block;width:162px;height:46px;border:0;">'
)


def _assert_the_footer_order(html, generic=False):
    """The bottom of every message, in one fixed order (CA, 2026-09-22): a
    rule, the OIUEEI mark, then whatever else applies (viral line, "manage
    your preferences", a sender-specific extra line), and always last the
    legal link. Checks the two fixed points — mark right after the rule,
    legal genuinely last — since what sits between them varies per email.

    ``generic=True`` is the GENERIC_PARENT ("OIUEEI") case: the mark already
    led the message as its <h1>, at double size, so the footer carries none
    — the rule goes straight to whatever comes next (or to the legal link)."""
    if generic:
        assert LOGO_IMG not in html
    else:
        assert html.count(LOGO_IMG) == 1
    hr = '<hr style="border:none;border-top:1px solid #ddd;margin-top:24px;">'
    assert html.count(hr) == 1
    if not generic:
        assert html.index(hr) < html.index(LOGO_IMG)
        assert html.index(LOGO_IMG) < html.index("Legal")
    # Nothing after "Legal & privacy" but the card's own closing tags.
    tail = html[html.index("</a></p>", html.index("Legal")) :]
    assert tail.strip() == "</a></p></div></div></html>"


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
        'style="display:inline-block;background-color:#ffffff;color:#0000bf;'
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
        'style="display:inline-block;background-color:#ffffff;color:#0000bf;'
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


def test_no_email_action_is_ever_a_bare_text_link():
    """The rule, enforced on the source so a NEW email cannot quietly break it.

    `_links` draws a row of plain text links. It used to have one allowed
    caller — the account-erasure confirmation, kept a text link on the
    reasoning that a destructive step was not obviously the place for the
    app's friendliest control — until CA reviewed the real thing and asked for
    it to be a button too (2026-09-22). `_links` now has NO callers left in
    the module; this fails the moment a new email reaches for it instead of
    `_cta` (one action) or `_ctas` (a yes/no pair)."""
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
    assert callers == set(), (
        f"{sorted(callers)} draw a bare text link. "
        "An email's primary action is a primary button (_cta); a yes/no pair is "
        "_ctas (primary + secondary)."
    )


def test_the_light_no_fallback_button_is_gone():
    """`_button` used to be a lighter `_cta`: a bare button, no "copy and paste
    this link" sentence, no raw URL under it. The house rule grew a second
    clause (CA, 2026-09-22): EVERY CTA repeats its link as plain text now, not
    only the ones whose whole job is one click — so the light variant has
    nothing left to be lighter than, and is deleted rather than kept unused."""
    assert not hasattr(email_service, "_button")


def test_every_single_action_cta_spells_its_own_link_out_below_it():
    """The single-button case, generically: whatever URL and label a caller
    gives `_cta`, both the fallback sentence and the raw link follow — this is
    what `_button` no longer existing has to mean in practice."""
    html = email_service._render_email(
        [email_service._cta("http://x/go", "Go there", "Trouble clicking?")], lang="en"
    )

    assert _first_button("http://x/go") in html
    assert ">Go there</a>" in html
    assert "Trouble clicking?" in html
    assert (
        '<a href="http://x/go" style="color:#0000bf !important;text-decoration:underline !important;">http://x/go</a>'
        in html
    )


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
        "color:#0000bf;border:2px solid #0000bf;"
    )
    assert secondary in html
    assert html.index(_first_button(approve)) < html.index(secondary)
    assert "copy and paste these links into your browser" in html
    assert f">{approve}</a>" in html and f">{reject}</a>" in html


# --- Email addresses shown as data (CA, 2026-09-22, second review round) -----
#
# An address the reader should notice but not click as an action — a proposed
# guest, a contact form's sender, an operator alert's Owner — is bus blue,
# underlined, and now a real `mailto:` link: a client's own auto-linkification
# (Gmail, iOS/Android "data detectors") wraps a bare address that LOOKS like
# one in its own default blue regardless of any inline style on a non-anchor
# element around it, which is what CA kept seeing after the first pass added
# `!important` everywhere else. Making it a real anchor, in our colour, up
# front removes the client's opening to re-wrap it its own way. None is bold —
# `_email()` used to be; CA called that a second, unexplained treatment for
# the same kind of value `_field(email=True)` already rendered plainly.


def test_an_email_shown_as_its_own_value_is_a_plain_mailto_link():
    """`_email()` — the proposed guest's address on an invitation proposal,
    the declined proposal's own."""
    html = email_service._render_email([email_service._email("guest@example.com")], lang="en")

    assert (
        '<p><a href="mailto:guest@example.com" '
        'style="color:#0000bf !important;text-decoration:underline !important;">'
        "guest@example.com</a></p>" in html
    )
    assert "<strong" not in html


def test_a_field_shown_as_an_address_is_a_plain_mailto_link():
    """`_field(label, value, email=True)` — the contact form's sender address."""
    html = email_service._render_email(
        [email_service._field("Email", "sender@example.com", email=True)], lang="en"
    )

    assert (
        '<p>Email: <a href="mailto:sender@example.com" '
        'style="color:#0000bf !important;text-decoration:underline !important;">'
        "sender@example.com</a></p>" in html
    )
    assert "<strong" not in html


def test_a_named_email_field_keeps_the_name_plain_and_links_only_the_address():
    """`_named_email_field()` — the capacity alarm's Owner row (CA, 2026-09-22,
    third review round): the person's name is not itself a link, only their
    parenthesised address is."""
    html = email_service._render_email(
        [email_service._named_email_field("Owner", "Lala", "lala@example.com")], lang="en"
    )

    assert (
        '<p>Owner: Lala (<a href="mailto:lala@example.com" '
        'style="color:#0000bf !important;text-decoration:underline !important;">'
        "lala@example.com</a>)</p>" in html
    )


@pytest.mark.django_db
def test_the_capacity_alarms_owner_row_has_no_angle_brackets():
    """CA's report, 2026-09-22: 'Owner: Lala <lala.sample@example.com>' read as
    a stray, unstyled HTML tag next to the name — parentheses instead, and
    only the address itself is a link (the two rows above)."""
    from core.models import Collection, User

    owner = User.objects.create(code="ALRMO2", email="alarmowner2@test.com", name="Lala")
    collection = Collection.objects.create(
        code="ALRMC2", owner=owner, headline="Busy", status="ACTIVE"
    )
    User.objects.create(code="ALRMS2", email="root2@test.com", is_superuser=True)
    mail.outbox.clear()

    email_service.send_collection_capacity_alarm(collection, "things", 501, 500)

    html = mail.outbox[0].alternatives[0][0]
    assert f"<{owner.email}>" not in html
    assert (
        f"Owner: {owner.display_name} "
        f'(<a href="mailto:{owner.email}" '
        'style="color:#0000bf !important;text-decoration:underline !important;">'
        f"{owner.email}</a>)" in html
    )
    plain = mail.outbox[0].body
    assert f"Owner: {owner.display_name} ({owner.email})" in plain


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


# --- The viral line is a highlighted callout (CA, 2026-09-22) ----------------


@pytest.mark.django_db
def test_the_viral_line_is_a_pale_yellow_callout_with_black_text():
    """CA, looking at the real thing: the growth line reads as one more grey
    footer sentence otherwise. A pale-yellow background + padding sets it
    apart; its own text is black, not the footer's muted grey — only the CTA
    link inside keeps the bus-blue LINK_STYLE."""
    email_service.send_magic_link_email("someone@example.com", "http://localhost:3000/verify/tok")

    html = mail.outbox[0].alternatives[0][0]
    assert (
        f'<p style="font-size:{email_service.EMAIL_FOOTER_SIZE};color:#000000;'
        'background-color:#fff1a8;padding:10px;margin-top:16px;">' in html
    )


# --- The card gives up its own framing on a phone (CA, 2026-09-22) -----------


def test_the_card_and_page_shed_their_padding_below_480px():
    """CA, opening a real message in the Gmail iOS app: the page's 40px
    padding plus the card's own 24px stack to ~64px lost from each side on a
    phone-width screen, shrinking the reading column to almost nothing. Below
    480px both containers give up their framing (no grey/white split, no
    border, no radius) and the page div becomes the only, much smaller,
    source of padding."""
    html = email_service._render_email([email_service._para("Hi")], lang="en")

    assert 'class="oiueei-email-page" style="background-color:#f9fafb;padding:40px;"' in html
    assert 'class="oiueei-email-card" style="max-width:600px;' in html
    assert (
        "@media only screen and (max-width: 480px) {\n"
        "  .oiueei-email-page { background-color: #ffffff !important; padding: 16px !important; }\n"
        "  .oiueei-email-card { max-width: 100% !important; border: none !important; "
        "border-radius: 0 !important; padding: 0 !important; }\n"
        "}" in html
    )


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


# --- Every email names one parent, as its <h1> (CA, 2026-09-22) -------------
#
# A thing's own headline for thing-scoped mail (people recognise the drill,
# the room, the listing — not a group name they may belong to several of), a
# collection's for collection-scoped mail, the FAQ question itself for the
# three FAQ emails, "OIUEEI" for the rest. It replaced an earlier rule where
# every thing-scoped email named its *collection* at the top instead.


@pytest.mark.django_db
def test_a_collection_scoped_email_leads_with_the_collection_name(user):
    """A genuinely collection-scoped email (no thing, no FAQ question involved)
    still takes the collection's name as its <h1>, as it did before this
    round — the invitation is one of these."""
    email_service.send_collection_invite_email(
        "Lala", "Chalmercadillo", "invitee@example.com", "http://x/a", "http://x/r"
    )

    msg = mail.outbox[0]
    html = msg.alternatives[0][0]
    assert "<h1" in html and ">Chalmercadillo</h1>" in html
    assert html.index(">Chalmercadillo</h1>") < html.index("Legal")
    _assert_the_footer_order(html)
    # Plain-text body opens with the collection name too.
    assert msg.body.startswith("Chalmercadillo")


@pytest.mark.django_db
def test_a_thing_scoped_email_names_the_thing_not_its_collection(user, user2, thing):
    """The `thing` fixture ("Test Thing") lives in "Test Collection" — a
    reservation-style email about it now names the THING at the top, not the
    group it happens to be in (CA, 2026-09-22; it used to be the collection's
    name). The wordmark still closes the message, after the rule."""
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
    assert "<h1" in html and ">Test Thing</h1>" in html
    assert html.index(">Test Thing</h1>") < html.index("Legal")
    assert "Test Collection" not in html
    _assert_the_footer_order(html)
    assert html.index(">Test Thing</h1>") < html.index(LOGO_IMG)
    assert msg.body.startswith("Test Thing")


@pytest.mark.django_db
def test_a_standalone_things_email_names_the_thing_too(user, user2):
    """A thing in no collection has no group to name either way — it was
    always the thing (or nothing) for a standalone one; unchanged here, this
    just confirms the new footer order still holds for it."""
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
    assert ">Ladder</h1>" in html
    _assert_the_footer_order(html)
    assert html.index(">Ladder</h1>") < html.index(LOGO_IMG)
    assert mail.outbox[0].body.startswith("Ladder")


@pytest.mark.django_db
def test_a_no_parent_email_still_gets_oiueei_as_its_h1(user):
    """Account-lifecycle mail (here: the erasure link) has no thing, no
    collection, no question — "OIUEEI" is its <h1> (CA, 2026-09-22; it used to
    grow no header at all), without the generic pitch (a destructive step is
    not a pitch moment — see GENERIC_PARENT's own docstring)."""
    email_service.send_account_delete_email(user, "http://x/confirm")

    html = mail.outbox[0].alternatives[0][0]
    # The mark itself is the <h1> now — double the footer size, no literal
    # "OIUEEI" text (CA, 2026-09-22: "OIUEEI is the protagonist" of this kind
    # of email — the mark moves up rather than appearing twice).
    assert GENERIC_H1_LOGO_IMG in html
    assert html.count("cid:oiueei-logo") == 1  # once total: h1 only, footer none
    assert ">OIUEEI</h1>" not in html
    assert email_service.T("generic_parent_pitch", lang="en") not in html
    _assert_the_footer_order(html, generic=True)


@pytest.mark.django_db
def test_every_logo_is_the_small_mark_and_the_file_cannot_be_drawn_giant(user):
    """The OIUEEI mark is 60x17 in the footer (CA, 2026-09-22, third review
    round — CA's own numbers, up from 53x15) wherever the parent is a real
    thing/collection/question — the erasure email now being a GENERIC_PARENT
    case (its mark leads as a bigger <h1> instead, see the test below), a
    collection-scoped send is what still exercises the small footer mark.
    Apple Mail ignored the width/height attributes and drew the old 212x60
    file at its natural size while Gmail honoured them, so the size is also
    declared as inline CSS regardless of the file's own pixels.
    **The file itself is 1944x552** (a second Figma export, CA: "un poco mas
    ligero de peso" — a lighter font weight, same display sizes), replacing
    the earlier 106x30 (2x) and then 846x240 versions, both reported pixelated
    on a real screen: a client honouring the displayed 60x17 draws crisp,
    heavily-oversampled art; one that ignores both attributes and CSS — Apple
    Mail's old behaviour — draws it at its full file size, big rather than
    giant, and still not garbled. The PNG stays small on disk despite the
    resolution because it is flat two-colour line art."""
    import struct

    email_service.send_collection_revoke_email("Lala", "Chalmercadillo", user.email)

    msg = mail.outbox[0]
    html = msg.alternatives[0][0]
    assert 'height="17" width="60"' in html
    assert "width:60px;height:17px" in html
    assert 'height="46"' not in html
    logo = next(p for p in msg.attachments if p["Content-ID"] == "<oiueei-logo>")
    png = logo.get_payload(decode=True)
    width, height = struct.unpack(">II", png[16:24])
    assert (width, height) == (1944, 552)


@pytest.mark.django_db
def test_a_generic_parent_emails_mark_is_the_h1_bigger_than_the_footer(user):
    """The one exception: when "OIUEEI" is the parent, its own mark leads the
    message as the <h1> (CA, 2026-09-22) — 162x46, bigger than the footer's
    60x17 — and the footer carries none, so the mark never appears twice."""
    email_service.send_account_delete_email(user, "http://x/confirm")

    html = mail.outbox[0].alternatives[0][0]
    assert GENERIC_H1_LOGO_IMG in html
    assert html.count("cid:oiueei-logo") == 1
    assert LOGO_IMG not in html


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
        '<ul><li>Trae tu <a href="https://example.com/reglas" '
        'style="color:#0000bf !important;text-decoration:underline !important;">'
        "carnet</a> (example.com)</li>"
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
        '<p><a href="https://elsewhere.example/verify" '
        'style="color:#0000bf !important;text-decoration:underline !important;">https://www.oiueei.com/verify/abc</a>'
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
        '<p><a href="https://example.com/a?b=1&amp;c=2" '
        'style="color:#0000bf !important;text-decoration:underline !important;">https://example.com/a?b=1&amp;c=2</a></p>'
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
