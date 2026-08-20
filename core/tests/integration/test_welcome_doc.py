"""
Collection welcome & rules PDF (O4): uploaded by the owner, emailed once as a link
to every member the first time they join.
"""

import pytest
from django.core import mail
from rest_framework.test import APIClient

from core.models import RSVP, Collection, User

JOIN_URL = "/api/v1/auth/join/"
SIGNATURE_URL = "/api/v1/upload/signature/"

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
class TestDocumentSignature:
    def test_document_mode_signs_pdf_only(self, authenticated_client):
        res = authenticated_client.post(
            SIGNATURE_URL,
            {"folder": "oiueei/collections", "kind": "document"},
            format="json",
        )

        assert res.status_code == 200
        assert res.data["allowed_formats"] == "pdf"
        # max_file_size isn't a signable Cloudinary parameter (S3) — never returned.
        assert "max_file_size" not in res.data
        # A PDF is a page-based image to Cloudinary — same resource type as a photo.
        assert res.data["resource_type"] == "image"

    def test_document_mode_always_signs_the_documents_folder(self, authenticated_client):
        # S4: document mode forces oiueei/documents regardless of the body's folder.
        res = authenticated_client.post(
            SIGNATURE_URL,
            {"folder": "oiueei/collections", "kind": "document"},
            format="json",
        )
        assert res.data["folder"] == "oiueei/documents"

    def test_document_mode_ignores_a_missing_folder_too(self, authenticated_client):
        res = authenticated_client.post(SIGNATURE_URL, {"kind": "document"}, format="json")
        assert res.status_code == 200
        assert res.data["folder"] == "oiueei/documents"

    def test_image_mode_is_unchanged(self, authenticated_client):
        res = authenticated_client.post(SIGNATURE_URL, {"folder": "oiueei/things"}, format="json")

        assert res.status_code == 200
        assert "pdf" not in res.data["allowed_formats"]
        assert "max_file_size" not in res.data
        assert res.data["resource_type"] == "image"

    def test_image_mode_cannot_choose_the_documents_folder(self, authenticated_client):
        # S4: oiueei/documents is document-only — an image request naming it
        # falls back like any other disallowed value.
        res = authenticated_client.post(
            SIGNATURE_URL, {"folder": "oiueei/documents"}, format="json"
        )
        assert res.status_code == 200
        assert res.data["folder"] == "oiueei/users"

    def test_an_unknown_kind_falls_back_to_an_image_upload(self, authenticated_client):
        res = authenticated_client.post(
            SIGNATURE_URL,
            {"folder": "oiueei/collections", "kind": "executable"},
            format="json",
        )

        assert res.status_code == 200
        assert "pdf" not in res.data["allowed_formats"]
        assert "max_file_size" not in res.data


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
        # Delivered as a .pdf URL — no f_auto/q_auto photo transformations.
        assert detail.data["welcome_doc_url"].endswith(".pdf")

    def test_a_path_traversing_id_is_rejected(self, authenticated_client, collection):
        res = authenticated_client.patch(
            f"/api/v1/collections/{collection.code}/",
            {"welcome_doc": "../../etc/passwd"},
            format="json",
        )

        assert res.status_code == 400
