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
