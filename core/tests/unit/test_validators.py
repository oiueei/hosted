"""
Unit tests for OIUEEI validators.
"""

import pytest
from rest_framework import serializers

from core.validators import (
    ImageIdField,
    SafeHeadlineField,
    SafeTextField,
    validate_headline,
    validate_image_id,
    validate_text,
)


class TestValidateImageId:
    """Tests for validate_image_id function."""

    @pytest.mark.parametrize(
        "value",
        [
            "abc123",
            "ABC123",
            "ABCDEF",
            "123456",
            "abc_123",
            "_test_",
            "abc-123",
            "-test-",
            "abc_123-XYZ",
        ],
    )
    def test_valid_values_pass_through(self, value):
        """Alphanumerics, underscores and hyphens are accepted unchanged."""
        assert validate_image_id(value) == value

    def test_empty_value_allowed(self):
        """Should accept empty values."""
        assert validate_image_id("") == ""
        assert validate_image_id(None) is None

    @pytest.mark.parametrize(
        "value",
        [
            "<script>alert(1)</script>",  # HTML
            "../etc/passwd",  # path traversal (unix)
            "..\\windows\\system32",  # path traversal (windows)
            "abc 123",  # spaces
            "abc@123",  # special chars
            "abc#123",
            "abc$123",
        ],
    )
    def test_invalid_values_raise(self, value):
        """HTML, path traversal, spaces and special characters are rejected."""
        with pytest.raises(serializers.ValidationError):
            validate_image_id(value)


class TestImageIdField:
    """Tests for ImageIdField serializer field."""

    def test_valid_value(self):
        """Should accept valid image IDs."""
        field = ImageIdField()
        assert field.to_internal_value("abc123") == "abc123"

    def test_max_length_default(self):
        """Should have default max_length of 255 (folder-prefixed storage keys)."""
        field = ImageIdField()
        assert field.max_length == 255

    def test_not_required_by_default(self):
        """Should not be required by default."""
        field = ImageIdField()
        assert field.required is False

    def test_invalid_value_raises(self):
        """Should raise on invalid input."""
        field = ImageIdField()
        with pytest.raises(serializers.ValidationError):
            field.to_internal_value("<script>")


class TestValidateHeadline:
    """Tests for validate_headline function."""

    @pytest.mark.parametrize(
        "value",
        [
            "Hello World",
            "My Collection 2024",
            "Hello, World!",
            "What's up?",
            "Boda de Maria",  # unicode
        ],
    )
    def test_valid_values_pass_through(self, value):
        """Plain text, punctuation and unicode are accepted unchanged."""
        assert validate_headline(value) == value

    def test_empty_value_allowed(self):
        """Should accept empty values."""
        assert validate_headline("") == ""
        assert validate_headline(None) is None

    @pytest.mark.parametrize(
        "value",
        [
            "<script>alert(1)</script>",  # script tag
            "<b>Bold</b>",  # any HTML tag
            "<a href='bad'>Link</a>",
            "<img src=x onerror=alert(1)>",
            '<div onmouseover="alert(1)">',  # event handler
            "Hello\r\nBcc: victim@example.com",  # CRLF header injection
            "Line one\nLine two",  # bare LF
            "[click](javascript:alert(1))",  # javascript: scheme
            "[x](data:text/plain,hello)",  # data: scheme
        ],
    )
    def test_invalid_values_raise(self, value):
        """HTML tags, event handlers, CR/LF and dangerous link schemes are rejected."""
        with pytest.raises(serializers.ValidationError):
            validate_headline(value)


class TestValidateText:
    """Tests for validate_text (multi-line Markdown fields)."""

    def test_allows_newlines(self):
        """Should permit line breaks (Markdown paragraphs/lists)."""
        assert validate_text("a\nb\nc") == "a\nb\nc"

    def test_allows_safe_markdown_links(self):
        """Should permit http(s) Markdown links."""
        value = "See [my site](https://example.org/path?q=1)"
        assert validate_text(value) == value

    def test_rejects_html(self):
        """Should reject raw HTML tags."""
        with pytest.raises(serializers.ValidationError):
            validate_text("<script>alert(1)</script>")

    def test_rejects_unsafe_scheme(self):
        """Should reject dangerous URL schemes in Markdown links."""
        with pytest.raises(serializers.ValidationError):
            validate_text("[x](javascript:alert(1))")

    def test_empty_value_allowed(self):
        """Should accept empty values."""
        assert validate_text("") == ""
        assert validate_text(None) is None


class TestSafeHeadlineField:
    """Tests for SafeHeadlineField serializer field."""

    def test_valid_value(self):
        """Should accept valid headlines."""
        field = SafeHeadlineField()
        assert field.to_internal_value("My Collection") == "My Collection"

    def test_invalid_value_raises(self):
        """Should raise on HTML input."""
        field = SafeHeadlineField()
        with pytest.raises(serializers.ValidationError):
            field.to_internal_value("<script>bad</script>")


class TestSafeTextField:
    """Tests for SafeTextField serializer field (used by the User `about` Markdown bio)."""

    def test_accepts_multiline_markdown(self):
        """Should accept multi-line Markdown (newlines, bold, list dashes, links)."""
        field = SafeTextField(max_length=2000)
        value = "Contact me at [my site](https://example.com)\n- one\n- two\n**bold**"
        assert field.to_internal_value(value) == value

    def test_empty_value_allowed(self):
        field = SafeTextField(allow_blank=True)
        assert field.to_internal_value("") == ""

    def test_invalid_with_html(self):
        """Should reject raw HTML tags (XSS guard) while permitting Markdown."""
        field = SafeTextField()
        with pytest.raises(serializers.ValidationError):
            field.to_internal_value("<script>alert(1)</script>")
        with pytest.raises(serializers.ValidationError):
            field.to_internal_value("<iframe src=x></iframe>")

    def test_invalid_with_unsafe_link_scheme(self):
        """Should reject dangerous URL schemes in Markdown links."""
        field = SafeTextField()
        with pytest.raises(serializers.ValidationError):
            field.to_internal_value("[click me](javascript:alert(document.cookie))")

    def test_allows_newlines_with_safe_links(self):
        """Multi-line Markdown plus http(s) links must pass."""
        field = SafeTextField(max_length=2000)
        value = "Para 1\n\nPara 2 with [a link](https://example.org/path?q=1)"
        assert field.to_internal_value(value) == value


class TestKeyStaysInItsFolder:
    """A stored key may not name one of the *other* asset folders.

    The upload ticket already refuses to sign a write outside a known folder, but
    the key that lands on the model arrives in a **separate** request afterwards,
    and nothing tied the two together: a member could put a collection's welcome
    PDF (`oiueei/documents/…`) into their own `photo` and republish a document its
    owner shared with one group. Keys carry 128 bits of entropy, so this is
    defence in depth — but the field already knows what it is for.
    """

    def test_a_key_in_its_own_folder_is_accepted(self):
        field = ImageIdField(folder="oiueei/users")
        assert field.to_internal_value("oiueei/users/abc123") == "oiueei/users/abc123"

    def test_a_key_naming_another_asset_folder_is_refused(self):
        """The attack this exists for: a document keyed into a photo field."""
        field = ImageIdField(folder="oiueei/users")
        with pytest.raises(serializers.ValidationError):
            field.to_internal_value("oiueei/documents/someone-elses-rules")

    @pytest.mark.parametrize(
        "other",
        ["oiueei/things", "oiueei/collections", "oiueei/documents"],
    )
    def test_every_other_asset_folder_is_refused(self, other):
        """Named one by one, so adding a folder to ASSET_FOLDERS without adding it
        here leaves a gap this file can be read to notice."""
        field = ImageIdField(folder="oiueei/users")
        with pytest.raises(serializers.ValidationError):
            field.to_internal_value(f"{other}/abc123")

    def test_the_shared_seed_pool_is_accepted_anywhere(self):
        """The demo's fixtures legitimately back things, collections and profiles
        alike, and they are not one of the asset folders."""
        field = ImageIdField(folder="oiueei/users")
        assert field.to_internal_value("oiueei/seed/lala") == "oiueei/seed/lala"

    def test_a_bare_legacy_key_still_saves(self):
        """The guard arrived years after the keys did. A Cloudinary-era public id
        with no folder at all must keep working — refusing it would make a field
        somebody could no longer save without re-uploading a photo that was fine."""
        field = ImageIdField(folder="oiueei/users")
        assert field.to_internal_value("v1234_abc") == "v1234_abc"

    def test_an_unknown_namespace_still_saves(self):
        """Same reasoning: only the *other known* folders are refused, so whatever
        shape a future provider hands back is not broken by this."""
        field = ImageIdField(folder="oiueei/users")
        assert field.to_internal_value("some/other/store") == "some/other/store"

    def test_a_field_with_no_folder_is_unchanged(self):
        field = ImageIdField()
        assert field.to_internal_value("oiueei/documents/x") == "oiueei/documents/x"

    def test_path_traversal_is_still_refused_inside_the_right_folder(self):
        """The folder check runs after `validate_image_id`, never instead of it."""
        field = ImageIdField(folder="oiueei/users")
        with pytest.raises(serializers.ValidationError):
            field.to_internal_value("oiueei/users/../documents/x")


class TestTheTicketAndTheFieldAgreeOnTheFolders:
    """One definition, read by both the door and the field.

    `views/upload.py` decides which folders a ticket may be signed for and
    `validators.validate_key_folder` refuses a key naming one of the others — if
    those lists drifted, a folder could become writable but unstorable, or the
    reverse. Both read `storage.ASSET_FOLDERS`, and this is what says so.
    """

    def test_every_folder_a_ticket_can_be_signed_for_is_a_known_asset_folder(self):
        from core.services import storage
        from core.views import upload

        assert upload.IMAGE_FOLDERS <= storage.ASSET_FOLDERS
        assert upload.DOCUMENT_FOLDER in storage.ASSET_FOLDERS

    def test_the_documents_folder_is_never_image_mode(self):
        """S4: an image must never be written where documents live."""
        from core.views import upload

        assert upload.DOCUMENT_FOLDER not in upload.IMAGE_FOLDERS
