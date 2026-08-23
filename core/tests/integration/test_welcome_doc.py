"""
Collection welcome & rules PDF (O4): uploaded by the owner, emailed once as a link
to every member the first time they join.
"""

import pytest
from django.conf import settings
from django.core import mail
from rest_framework.test import APIClient

from core.models import RSVP, Collection, User

JOIN_URL = "/api/v1/auth/join/"

DOC_ID = "oiueei/collections/welcome-doc-1"


def _verify(rsvp):
    return APIClient().get(f"/api/v1/auth/verify/{rsvp.token}/")


def _doc_emails():
    """The welcome-doc emails in the outbox — the ones carrying the PDF link.

    Not filtered by subject: the join magic-link subject also names the collection.
    """
    return [m for m in mail.outbox if DOC_ID in m.body]


def _invite_rsvp(user, collection):
    return RSVP.objects.create(
        user_code=user,
        user_email=user.email,
        action=RSVP.Action.COLLECTION_INVITE,
        target_code=collection.code,
    )


@pytest.mark.django_db
class TestWelcomeDocOnJoin:
    def test_accepting_an_invitation_sends_the_document(self, user2, collection):
        collection.welcome_doc = DOC_ID
        collection.save()

        _verify(_invite_rsvp(user2, collection))

        sent = _doc_emails()
        assert len(sent) == 1
        assert collection.headline in sent[0].subject
        assert sent[0].to == [user2.email]

    def test_no_document_means_no_email(self, user2, collection):
        assert collection.welcome_doc == ""

        _verify(_invite_rsvp(user2, collection))

        assert _doc_emails() == []

    def test_rejoining_does_not_resend(self, api_client, collection):
        # Login-to-act on a PUBLIC collection re-runs the (idempotent) M2M add on
        # every join, so an existing member must not get the document again.
        collection.welcome_doc = DOC_ID
        collection.visibility = Collection.Visibility.PUBLIC
        collection.save()

        api_client.post(
            JOIN_URL,
            {"email": "joiner@test.com", "collection_code": collection.code},
            format="json",
        )
        assert len(_doc_emails()) == 1

        api_client.post(
            JOIN_URL,
            {"email": "joiner@test.com", "collection_code": collection.code},
            format="json",
        )

        assert len(_doc_emails()) == 1
        assert collection.invites.filter(email="joiner@test.com").exists()

    def test_share_token_join_sends_the_document(self, api_client, collection):
        collection.welcome_doc = DOC_ID
        collection.share_token = "sharetoken1234567890ab"
        collection.save()

        api_client.post(
            JOIN_URL,
            {"email": "shared@test.com", "share_token": collection.share_token},
            format="json",
        )

        sent = _doc_emails()
        assert len(sent) == 1
        assert sent[0].to == ["shared@test.com"]
        assert User.objects.filter(email="shared@test.com").exists()

    def test_the_signed_in_door_sends_it_like_every_other(
        self, authenticated_client, user, user2, collection
    ):
        """The fourth way in, added this round, and the one nothing checked.

        `POST /collections/{code}/join/` reaches `_join_collection` by import
        rather than by reimplementation, which is exactly why it is worth one
        test and not four: what it has to prove is that it really does go
        through the shared funnel. A door that grew its own `invites.add()` —
        the obvious way to write it — would admit the member correctly and
        silently never send them the rules.
        """
        # Owned by somebody else: the owner of a collection cannot join it, so
        # the joiner has to be the *other* account for this door to open at all.
        collection.owner = user2
        collection.welcome_doc = DOC_ID
        collection.visibility = Collection.Visibility.PUBLIC
        collection.save()

        res = authenticated_client.post(f"/api/v1/collections/{collection.code}/join/")

        assert res.status_code == 200
        sent = _doc_emails()
        assert len(sent) == 1
        assert sent[0].to == [user.email]


@pytest.mark.django_db
class TestWelcomeDocField:
    def test_owner_can_set_and_read_back_the_document(self, authenticated_client, collection):
        res = authenticated_client.patch(
            f"/api/v1/collections/{collection.code}/",
            {"welcome_doc": DOC_ID},
            format="json",
        )
        assert res.status_code == 200

        detail = authenticated_client.get(f"/api/v1/collections/{collection.code}/")
        assert detail.data["welcome_doc"] == DOC_ID
        # The URL is the stored key under the media base, and nothing else. It used
        # to have to end in `.pdf`: Cloudinary filed a PDF under resource_type=image
        # and only served it as a document if the URL carried the extension. The
        # object store has no such quirk — what makes it open in the viewer is the
        # Content-Type signed at upload, which is pinned in unit/test_storage.py.
        assert detail.data["welcome_doc_url"] == f"{settings.MEDIA_PUBLIC_BASE_URL}/{DOC_ID}"

    def test_a_path_traversing_id_is_rejected(self, authenticated_client, collection):
        res = authenticated_client.patch(
            f"/api/v1/collections/{collection.code}/",
            {"welcome_doc": "../../etc/passwd"},
            format="json",
        )

        assert res.status_code == 400
