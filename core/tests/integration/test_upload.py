"""
The upload ticket endpoint — every rule it enforces, and the one it gained.

Signing a presigned URL is local arithmetic, so these run for real against the
fake credentials `conftest` configures, with no network and no mocking.

What the tests are here to protect is that the server, not the client, decides
what may be written: the key, the folder, the content type and now the size. The
size is the new one and the one with history — Cloudinary's signature excluded
`max_file_size`, so signing it broke every document upload (the S3 outage) and
the cap had to live in the browser, where anybody could skip it.
"""

import pytest

from core.views.upload import DOCUMENT_MAX_BYTES, IMAGE_MAX_BYTES

URL = "/api/v1/upload/ticket/"


def image_body(**overrides):
    return {
        "folder": "oiueei/things",
        "content_type": "image/webp",
        "content_length": 120_000,
        **overrides,
    }


def document_body(**overrides):
    return {
        "kind": "document",
        "content_type": "application/pdf",
        "content_length": 400_000,
        **overrides,
    }


@pytest.mark.django_db
class TestOnlyASignedInUserGetsATicket:
    def test_anonymous_is_unauthorized(self, api_client):
        assert api_client.post(URL, image_body(), format="json").status_code == 401


@pytest.mark.django_db
class TestTheServerNamesTheObject:
    def test_the_key_is_generated_here_not_taken_from_the_client(self, authenticated_client):
        """A client-chosen key could overwrite somebody else's photo."""
        res = authenticated_client.post(URL, image_body(key="oiueei/things/victim"), format="json")
        assert res.status_code == 200
        assert res.data["key"] != "oiueei/things/victim"
        assert res.data["key"].startswith("oiueei/things/")

    def test_two_tickets_never_name_the_same_object(self, authenticated_client):
        keys = {
            authenticated_client.post(URL, image_body(), format="json").data["key"]
            for _ in range(5)
        }
        assert len(keys) == 5

    def test_the_random_part_is_long_enough_to_be_unguessable(self, authenticated_client):
        """The key is what keeps a public object private. 16 bytes, url-safe."""
        key = authenticated_client.post(URL, image_body(), format="json").data["key"]
        assert len(key.rsplit("/", 1)[1]) >= 20


@pytest.mark.django_db
class TestTheFolderIsConstrained:
    @pytest.mark.parametrize("folder", ["oiueei/users", "oiueei/things", "oiueei/collections"])
    def test_an_allowed_folder_is_honoured(self, authenticated_client, folder):
        res = authenticated_client.post(URL, image_body(folder=folder), format="json")
        assert res.data["key"].startswith(f"{folder}/")

    def test_a_disallowed_folder_falls_back_to_users(self, authenticated_client):
        res = authenticated_client.post(URL, image_body(folder="../../etc"), format="json")
        assert res.status_code == 200
        assert res.data["key"].startswith("oiueei/users/")

    def test_a_missing_folder_falls_back_to_users(self, authenticated_client):
        body = image_body()
        del body["folder"]
        assert (
            authenticated_client.post(URL, body, format="json")
            .data["key"]
            .startswith("oiueei/users/")
        )

    def test_an_image_cannot_choose_the_documents_folder(self, authenticated_client):
        """S4: documents is document-mode-only, so photos can never land there."""
        res = authenticated_client.post(URL, image_body(folder="oiueei/documents"), format="json")
        assert res.data["key"].startswith("oiueei/users/")

    def test_document_mode_forces_its_folder_whatever_the_body_asks(self, authenticated_client):
        res = authenticated_client.post(URL, document_body(folder="oiueei/things"), format="json")
        assert res.data["key"].startswith("oiueei/documents/")

    def test_document_mode_needs_no_folder_in_the_body_at_all(self, authenticated_client):
        assert (
            authenticated_client.post(URL, document_body(), format="json")
            .data["key"]
            .startswith("oiueei/documents/")
        )


@pytest.mark.django_db
class TestTheContentTypeIsChosenFromAnAllowlist:
    def test_a_raster_photo_type_is_accepted(self, authenticated_client):
        res = authenticated_client.post(URL, image_body(content_type="image/png"), format="json")
        assert res.data["headers"]["Content-Type"] == "image/png"

    def test_svg_is_refused_because_it_can_carry_script(self, authenticated_client):
        """An <img> rendering an uploaded SVG would be executing somebody's markup."""
        res = authenticated_client.post(
            URL, image_body(content_type="image/svg+xml"), format="json"
        )
        assert res.status_code == 400
        assert "content_type" in res.data

    def test_html_is_refused_so_the_bucket_cannot_serve_a_page(self, authenticated_client):
        res = authenticated_client.post(URL, image_body(content_type="text/html"), format="json")
        assert res.status_code == 400

    def test_a_missing_content_type_is_refused_rather_than_guessed(self, authenticated_client):
        body = image_body()
        del body["content_type"]
        assert authenticated_client.post(URL, body, format="json").status_code == 400

    def test_image_mode_refuses_a_pdf(self, authenticated_client):
        res = authenticated_client.post(
            URL, image_body(content_type="application/pdf"), format="json"
        )
        assert res.status_code == 400

    def test_document_mode_accepts_only_a_pdf(self, authenticated_client):
        assert (
            authenticated_client.post(URL, document_body(), format="json").data["headers"][
                "Content-Type"
            ]
            == "application/pdf"
        )
        assert (
            authenticated_client.post(
                URL, document_body(content_type="image/webp"), format="json"
            ).status_code
            == 400
        )

    def test_an_unknown_kind_is_an_image_upload(self, authenticated_client):
        """An unrecognised value can only ever narrow to the image defaults."""
        res = authenticated_client.post(
            URL, image_body(kind="executable", content_type="application/pdf"), format="json"
        )
        assert res.status_code == 400


@pytest.mark.django_db
class TestTheSizeCapIsEnforcedHereNowNotInTheBrowser:
    def test_an_image_over_the_cap_is_refused(self, authenticated_client):
        res = authenticated_client.post(
            URL, image_body(content_length=IMAGE_MAX_BYTES + 1), format="json"
        )
        assert res.status_code == 400
        assert "content_length" in res.data

    def test_a_document_over_five_megabytes_is_refused(self, authenticated_client):
        """The welcome doc's long-standing limit, in the one place a client can't skip."""
        assert DOCUMENT_MAX_BYTES == 5 * 1024 * 1024
        res = authenticated_client.post(
            URL, document_body(content_length=DOCUMENT_MAX_BYTES + 1), format="json"
        )
        assert res.status_code == 400

    def test_a_document_may_not_borrow_the_larger_image_cap(self, authenticated_client):
        """The two limits are picked by mode; a PDF must not get the image allowance."""
        assert DOCUMENT_MAX_BYTES < IMAGE_MAX_BYTES
        res = authenticated_client.post(
            URL, document_body(content_length=IMAGE_MAX_BYTES - 1), format="json"
        )
        assert res.status_code == 400

    def test_exactly_the_cap_is_allowed(self, authenticated_client):
        res = authenticated_client.post(
            URL, image_body(content_length=IMAGE_MAX_BYTES), format="json"
        )
        assert res.status_code == 200

    def test_an_empty_upload_is_refused(self, authenticated_client):
        assert (
            authenticated_client.post(URL, image_body(content_length=0), format="json").status_code
            == 400
        )

    def test_a_negative_length_is_refused(self, authenticated_client):
        assert (
            authenticated_client.post(URL, image_body(content_length=-5), format="json").status_code
            == 400
        )

    def test_a_missing_length_is_refused_rather_than_defaulted(self, authenticated_client):
        body = image_body()
        del body["content_length"]
        assert authenticated_client.post(URL, body, format="json").status_code == 400

    def test_a_length_that_is_not_a_number_is_refused(self, authenticated_client):
        """A string would sail into the signature and break it at upload time instead."""
        for value in ("120000", None, 1.5, [1], True):
            res = authenticated_client.post(URL, image_body(content_length=value), format="json")
            assert res.status_code == 400, value


@pytest.mark.django_db
class TestTheTicketIsUsableAsGiven:
    def test_it_names_the_method_the_client_must_use(self, authenticated_client):
        assert authenticated_client.post(URL, image_body(), format="json").data["method"] == "PUT"

    def test_the_url_points_at_the_bucket_and_carries_a_signature(self, authenticated_client):
        url = authenticated_client.post(URL, image_body(), format="json").data["url"]
        assert url.startswith("https://test-bucket.fsn1.example-storage.com/")
        assert "X-Amz-Signature=" in url

    def test_the_url_is_for_the_key_the_client_is_told_to_store(self, authenticated_client):
        res = authenticated_client.post(URL, image_body(), format="json")
        assert res.data["key"] in res.data["url"]

    def test_the_headers_carry_the_public_acl_and_the_cache_policy(self, authenticated_client):
        headers = authenticated_client.post(URL, image_body(), format="json").data["headers"]
        assert headers["x-amz-acl"] == "public-read"
        assert "immutable" in headers["Cache-Control"]

    def test_it_says_where_the_object_will_be_readable(self, authenticated_client):
        """Answered by the server: a CDN in front means reads and writes differ."""
        res = authenticated_client.post(URL, image_body(), format="json")
        assert res.data["public_url"] == (
            f"https://test-bucket.fsn1.example-storage.com/{res.data['key']}"
        )

    def test_the_public_url_follows_the_media_base_not_the_bucket(
        self, authenticated_client, settings
    ):
        settings.MEDIA_PUBLIC_BASE_URL = "https://cdn.example.org"
        res = authenticated_client.post(URL, image_body(), format="json")
        assert res.data["public_url"].startswith("https://cdn.example.org/")
        assert res.data["url"].startswith("https://test-bucket.")

    def test_no_cloudinary_parameters_survive_in_the_response(self, authenticated_client):
        """The old contract is gone: a client still sending it back would be ignored."""
        res = authenticated_client.post(URL, image_body(), format="json")
        assert set(res.data) == {"url", "method", "headers", "key", "public_url"}
