"""POST /api/v1/collections/{code}/email-note/test/ — a curator's note, seen first.

A collection's ``email_note`` only ever appears in the emails a *requester*
receives, and a curator can't request their own things — so it was written
blind. The page's own Markdown preview would lie about it (the email subset has
no headings or tables, and prints a link's host after it), so the test sends
the curator the real rendering, in the real layout, of the draft they typed.
"""

import pytest
from django.core import mail
from rest_framework import status

URL = "/api/v1/collections/{}/email-note/test/"


@pytest.mark.django_db
def test_a_curator_gets_their_draft_rendered_as_members_will_see_it(
    authenticated_client, user, user2, collection
):
    collection.invites.add(user2)

    resp = authenticated_client.post(
        URL.format(collection.code),
        {"email_note": "**Bring ID.**\n\n- Floor 2\n- [Rules](https://example.com/rules)"},
        format="json",
    )

    assert resp.status_code == status.HTTP_200_OK
    assert len(mail.outbox) == 1
    sent = mail.outbox[0]
    # To the curator who asked, and to nobody else in the group.
    assert sent.to == [user.email]
    html = sent.alternatives[0][0]
    # The email's own renderer: bold, a list, a link with its real host after.
    assert "<strong>Bring ID.</strong>" in html
    assert "<li>Floor 2</li>" in html
    assert (
        '<a href="https://example.com/rules" style="color:#0000bf;text-decoration:underline;">'
        "Rules</a> (example.com)" in html
    )
    assert "Test Collection" in sent.subject
    # The plain half carries the raw Markdown, as the real emails do.
    assert "**Bring ID.**" in sent.body


@pytest.mark.django_db
def test_a_note_written_per_language_shows_every_version_under_its_name(
    authenticated_client, collection
):
    resp = authenticated_client.post(
        URL.format(collection.code),
        {"email_note": '{"es": "Trae el DNI.", "ca": "Porta el DNI."}'},
        format="json",
    )

    assert resp.status_code == status.HTTP_200_OK
    html = mail.outbox[0].alternatives[0][0]
    assert "Español" in html and "Trae el DNI." in html
    assert "Català" in html and "Porta el DNI." in html


@pytest.mark.django_db
def test_an_activity_opt_out_does_not_swallow_a_test_the_curator_asked_for(
    authenticated_client, user, collection
):
    user.notify_activity = False
    user.save(update_fields=["notify_activity"])

    authenticated_client.post(URL.format(collection.code), {"email_note": "Hi."}, format="json")

    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_a_member_who_is_not_a_curator_cannot_send_one(authenticated_client2, user2, collection):
    collection.invites.add(user2)

    resp = authenticated_client2.post(
        URL.format(collection.code), {"email_note": "Hi."}, format="json"
    )

    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert mail.outbox == []


@pytest.mark.django_db
def test_a_note_over_the_limit_is_refused_and_nothing_is_sent(authenticated_client, collection):
    resp = authenticated_client.post(
        URL.format(collection.code), {"email_note": "x" * 513}, format="json"
    )

    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert mail.outbox == []


@pytest.mark.django_db
def test_an_empty_note_is_refused(authenticated_client, collection):
    resp = authenticated_client.post(URL.format(collection.code), {"email_note": ""}, format="json")

    assert resp.status_code == status.HTTP_400_BAD_REQUEST
    assert mail.outbox == []
