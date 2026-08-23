"""`core.services.storage` — the single door to the object store.

Four properties are worth a test, and none of them are "boto3 works":

1. **Reads come from a setting, not from the client.** `MEDIA_PUBLIC_BASE_URL`
   is what lets a deployment put a CDN or a custom domain in front of the bucket
   without touching code, and it is also what feeds the CSP. Build the URL from
   the client instead and both promises quietly break.
2. **The upload policy signs the content type.** A policy that signs only the
   ACL and the size stores the object as `binary/octet-stream` — that is how the
   welcome PDF stops opening in the browser's viewer and starts downloading, and
   it is a bug that only shows up in production, behind an email link. Signing it
   also pins the served type server-side, so an upload cannot come back as
   `text/html` and make the bucket an XSS origin.
3. **The size cap is signed too.** Cloudinary could not sign one, so until now
   the only limit was an `if` in the browser. If this condition ever stops being
   built, the cap is gone and nothing else notices.
4. **Batching respects S3's limits.** `delete_objects` refuses more than 1000
   keys per call, and the orphan sweep is the caller that will one day exceed it.

The last class covers the *setting* rather than the service: `MEDIA_PUBLIC_BASE_URL`
is derived from the bucket and endpoint when nobody sets it, which is what makes a
fresh deployment serve images without a sixth config var to get wrong.
"""

import importlib
import os
from unittest import mock
from unittest.mock import MagicMock, patch

import pytest
from botocore.exceptions import ClientError
from django.core.exceptions import ImproperlyConfigured

import config.settings.base as base_settings
from core.services import storage

CONFIGURED = {
    "OBJECT_STORAGE_ENDPOINT": "https://fsn1.example-storage.com",
    "OBJECT_STORAGE_BUCKET": "test-bucket",
    "OBJECT_STORAGE_REGION": "fsn1",
    "OBJECT_STORAGE_ACCESS_KEY": "key",
    "OBJECT_STORAGE_SECRET_KEY": "secret",
    "MEDIA_PUBLIC_BASE_URL": "https://test-bucket.fsn1.example-storage.com",
}


@pytest.fixture(autouse=True)
def configured(settings):
    """Every test starts from a fully configured store, and leaves no cached client.

    The client cache is module state: a mock left in it would leak into the next
    test and quietly answer for a bucket that test never configured.
    """
    for name, value in CONFIGURED.items():
        setattr(settings, name, value)
    storage._clients.clear()
    yield settings
    storage._clients.clear()


@pytest.fixture
def s3():
    """A stand-in S3 client. No test in this file touches the network."""
    fake = MagicMock()
    with patch.object(storage.boto3, "client", return_value=fake) as factory:
        fake.factory = factory
        yield fake


class TestPublicUrlsComeFromTheSetting:
    def test_url_is_the_base_plus_the_key(self):
        assert (
            storage.public_url("oiueei/things/abc")
            == "https://test-bucket.fsn1.example-storage.com/oiueei/things/abc"
        )

    def test_a_cdn_override_wins_over_the_bucket(self, configured):
        """The whole point of the setting: a CDN in front is config, not a patch."""
        configured.MEDIA_PUBLIC_BASE_URL = "https://cdn.example.org/"
        assert storage.public_url("k") == "https://cdn.example.org/k"

    def test_an_empty_key_has_no_url(self):
        """Serializers pass unset image fields straight in and expect None back."""
        assert storage.public_url("") is None
        assert storage.public_url(None) is None

    def test_reading_a_url_needs_no_credentials(self, configured):
        """Serving existing assets must not depend on upload credentials."""
        configured.OBJECT_STORAGE_SECRET_KEY = ""
        assert storage.public_url("k").endswith("/k")

    def test_an_unconfigured_checkout_has_no_url_rather_than_a_relative_one(self, configured):
        """`/k` would be a link back to Django, which answers 404 and renders broken."""
        configured.MEDIA_PUBLIC_BASE_URL = ""
        assert storage.public_url("k") is None


class TestMissingConfigurationSaysWhatIsMissing:
    def test_the_error_names_the_unset_setting(self, configured, s3):
        configured.OBJECT_STORAGE_BUCKET = ""
        with pytest.raises(ImproperlyConfigured, match="OBJECT_STORAGE_BUCKET"):
            storage.client()

    def test_every_missing_setting_is_named_not_just_the_first(self, configured, s3):
        configured.OBJECT_STORAGE_ACCESS_KEY = ""
        configured.OBJECT_STORAGE_SECRET_KEY = ""
        with pytest.raises(ImproperlyConfigured) as exc:
            storage.client()
        assert "OBJECT_STORAGE_ACCESS_KEY" in str(exc.value)
        assert "OBJECT_STORAGE_SECRET_KEY" in str(exc.value)


class TestTheClientIsCachedButNotStale:
    def test_repeated_calls_reuse_one_client(self, s3):
        assert storage.client() is storage.client()
        assert s3.factory.call_count == 1

    def test_changing_the_bucket_builds_a_new_client(self, configured, s3):
        """A cache keyed on nothing would answer for the wrong bucket after a change."""
        first = storage.client()
        configured.OBJECT_STORAGE_BUCKET = "other-bucket"
        second = storage.client()
        assert s3.factory.call_count == 2
        assert (first, second) == (s3, s3)  # both from the patched factory


class TestTheUploadTicketSignsTheRulesItPromises:
    """The ticket is a presigned PUT, and every rule it claims must really be signed.

    It is a PUT rather than a presigned POST for one measured reason: Hetzner
    accepts a POST policy but **silently drops its Cache-Control field** — the
    object comes back without the header and without the metadata. A PUT carries
    the type, the cache header and an exact signed length at once.
    """

    def _params(self, s3, **kwargs):
        defaults = {
            "key": "oiueei/things/abc",
            "content_type": "image/webp",
            "content_length": 1_000,
            "max_bytes": 5_000,
        }
        ticket = storage.presign_upload(**{**defaults, **kwargs})
        call = s3.generate_presigned_url.call_args
        assert call.args[0] == "put_object"
        return call.kwargs["Params"], ticket

    def test_the_content_type_is_signed_exactly(self, s3):
        """Without this the object is stored as binary/octet-stream — see the docstring."""
        params, ticket = self._params(s3, content_type="application/pdf")
        assert params["ContentType"] == "application/pdf"
        assert ticket["headers"]["Content-Type"] == "application/pdf"

    def test_cache_control_is_signed_so_assets_are_not_refetched(self, s3):
        """There is no CDN: without this every visit is another trip to the bucket."""
        params, ticket = self._params(s3)
        assert params["CacheControl"] == storage.CACHE_CONTROL
        assert ticket["headers"]["Cache-Control"] == storage.CACHE_CONTROL
        assert "immutable" in storage.CACHE_CONTROL

    def test_the_object_is_public_and_the_acl_is_signed(self, s3):
        params, ticket = self._params(s3)
        assert params["ACL"] == "public-read"
        assert ticket["headers"]["x-amz-acl"] == "public-read"

    def test_the_exact_length_is_signed_which_is_what_caps_the_upload(self, s3):
        """Sending any other number of bytes fails the signature, in either direction."""
        params, _ = self._params(s3, content_length=4_096)
        assert params["ContentLength"] == 4_096

    def test_content_length_is_not_returned_as_a_header(self, s3):
        """JavaScript may not set it; the browser does, from the real body length."""
        _, ticket = self._params(s3)
        assert "Content-Length" not in ticket["headers"]

    def test_an_oversized_upload_is_refused_before_anything_is_signed(self, s3):
        """The cap has to bite here. Nothing downstream looks at the size again."""
        with pytest.raises(ValueError, match="5000"):
            storage.presign_upload("k", "image/webp", content_length=5_001, max_bytes=5_000)
        s3.generate_presigned_url.assert_not_called()

    def test_an_upload_of_exactly_the_limit_is_allowed(self, s3):
        """Off-by-one in the other direction: the cap is inclusive."""
        params, _ = self._params(s3, content_length=5_000, max_bytes=5_000)
        assert params["ContentLength"] == 5_000

    def test_an_empty_upload_is_refused(self, s3):
        """Zero bytes is never a legitimate upload, and neither is a negative claim."""
        for size in (0, -1):
            with pytest.raises(ValueError):
                storage.presign_upload("k", "image/webp", content_length=size, max_bytes=5_000)
        s3.generate_presigned_url.assert_not_called()

    def test_the_ticket_is_short_lived(self, s3):
        storage.presign_upload("k", "image/webp", 10, 5_000)
        assert s3.generate_presigned_url.call_args.kwargs["ExpiresIn"] <= 900

    def test_it_uploads_to_the_configured_bucket_under_the_given_key(self, s3):
        params, ticket = self._params(s3, key="oiueei/documents/xyz")
        assert (params["Bucket"], params["Key"]) == ("test-bucket", "oiueei/documents/xyz")
        assert ticket["method"] == "PUT"


class TestAServerSideUploadMatchesATicketedOne:
    """`put` is how the server moves bytes it already has (a copy, a migration).

    The object it produces has to be indistinguishable from one a browser
    uploaded through a ticket, because everything downstream — the CDN-less
    cache story, the PDF opening in a viewer, the public read — depends on the
    same three headers being on it. An object copied in without them is the bug
    that only shows up months later, behind an email link.
    """

    def test_it_carries_the_same_three_things_a_signed_ticket_does(self, s3):
        storage.put("oiueei/seed/x", b"bytes", "image/webp")
        call = s3.put_object.call_args.kwargs
        assert call["ACL"] == "public-read"
        assert call["ContentType"] == "image/webp"
        assert call["CacheControl"] == storage.CACHE_CONTROL

    def test_it_writes_the_given_bytes_to_the_given_key_in_the_configured_bucket(self, s3):
        storage.put("oiueei/seed/x", b"bytes", "image/png")
        call = s3.put_object.call_args.kwargs
        assert (call["Bucket"], call["Key"], call["Body"]) == (
            "test-bucket",
            "oiueei/seed/x",
            b"bytes",
        )


class TestExistsAnswersWithoutDownloading:
    """What makes a copy idempotent — and it must not turn a real fault into False."""

    def test_a_present_object_is_true(self, s3):
        assert storage.exists("k") is True
        s3.head_object.assert_called_once_with(Bucket="test-bucket", Key="k")

    def test_a_missing_object_is_false(self, s3):
        s3.head_object.side_effect = ClientError(
            {"Error": {"Code": "404"}, "ResponseMetadata": {"HTTPStatusCode": 404}}, "HeadObject"
        )
        assert storage.exists("k") is False

    def test_a_permission_error_raises_rather_than_reading_as_absent(self, s3):
        """Swallowing this would make a copy re-upload everything and call it success."""
        s3.head_object.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied"}, "ResponseMetadata": {"HTTPStatusCode": 403}},
            "HeadObject",
        )
        with pytest.raises(ClientError):
            storage.exists("k")


class TestDeletionIsBatchedAndForgiving:
    def test_one_key_is_one_call(self, s3):
        storage.delete("oiueei/things/gone")
        s3.delete_object.assert_called_once_with(Bucket="test-bucket", Key="oiueei/things/gone")

    def test_deleting_nothing_touches_the_network(self, s3):
        storage.delete("")
        assert storage.delete_many([]) == 0
        assert storage.delete_many(["", None]) == 0
        s3.delete_object.assert_not_called()
        s3.delete_objects.assert_not_called()

    def test_a_batch_never_exceeds_the_s3_limit_of_1000(self, s3):
        """The orphan sweep is the caller that will eventually hand over more."""
        assert storage.delete_many([f"k{i}" for i in range(2_500)]) == 2_500
        sizes = [len(c.kwargs["Delete"]["Objects"]) for c in s3.delete_objects.call_args_list]
        assert sizes == [1000, 1000, 500]

    def test_every_key_handed_over_is_actually_deleted(self, s3):
        storage.delete_many([f"k{i}" for i in range(1_100)])
        sent = [
            obj["Key"]
            for call in s3.delete_objects.call_args_list
            for obj in call.kwargs["Delete"]["Objects"]
        ]
        assert sent == [f"k{i}" for i in range(1_100)]


class TestListingWalksThePagesAndCarriesTheAge:
    def _pages(self, s3, pages):
        s3.get_paginator.return_value.paginate.return_value = pages

    def test_objects_from_every_page_are_yielded(self, s3):
        self._pages(
            s3,
            [
                {"Contents": [{"Key": "a", "LastModified": "T1", "Size": 1}]},
                {"Contents": [{"Key": "b", "LastModified": "T2", "Size": 2}]},
            ],
        )
        assert [o["key"] for o in storage.iter_objects("oiueei/")] == ["a", "b"]

    def test_last_modified_is_carried_through(self, s3):
        """The sweep's --min-age-hours / --max-age-days windows are built on it."""
        self._pages(s3, [{"Contents": [{"Key": "a", "LastModified": "T1", "Size": 7}]}])
        assert list(storage.iter_objects()) == [{"key": "a", "last_modified": "T1", "size": 7}]

    def test_an_empty_bucket_yields_nothing_rather_than_raising(self, s3):
        self._pages(s3, [{}])
        assert list(storage.iter_objects()) == []

    def test_the_prefix_is_passed_to_the_provider_not_filtered_here(self, s3):
        """Filtering client-side would page the whole bucket to find one folder."""
        self._pages(s3, [])
        list(storage.iter_objects("oiueei/seed/"))
        s3.get_paginator.return_value.paginate.assert_called_once_with(
            Bucket="test-bucket", Prefix="oiueei/seed/"
        )


class TestThePublicBaseUrlIsDerivedUnlessGiven:
    """The setting is built in `config/settings/base.py`, so read it from there.

    The module is re-imported under a patched environment rather than inspected
    as text — what matters is the value it actually produces. `django.conf`
    already holds its own copy, so the reload does not disturb the run.
    """

    @staticmethod
    def _base_url_with(env):
        with mock.patch.dict(os.environ, env, clear=False):
            for key in (
                "OBJECT_STORAGE_ENDPOINT",
                "OBJECT_STORAGE_BUCKET",
                "MEDIA_PUBLIC_BASE_URL",
            ):
                if key not in env:
                    os.environ.pop(key, None)
            return importlib.reload(base_settings).MEDIA_PUBLIC_BASE_URL

    @staticmethod
    def teardown_class():
        """Leave the module holding the real environment's answer again."""
        importlib.reload(base_settings)

    def test_it_is_built_from_the_bucket_and_the_endpoint(self):
        """A deployment that sets the bucket gets working URLs with no extra var."""
        assert (
            self._base_url_with(
                {
                    "OBJECT_STORAGE_ENDPOINT": "https://fsn1.example-storage.com",
                    "OBJECT_STORAGE_BUCKET": "a-bucket",
                }
            )
            == "https://a-bucket.fsn1.example-storage.com"
        )

    def test_an_explicit_value_is_never_overwritten(self):
        """This is the CDN / custom-domain escape hatch. Derivation must not win."""
        assert (
            self._base_url_with(
                {
                    "OBJECT_STORAGE_ENDPOINT": "https://fsn1.example-storage.com",
                    "OBJECT_STORAGE_BUCKET": "a-bucket",
                    "MEDIA_PUBLIC_BASE_URL": "https://cdn.example.org",
                }
            )
            == "https://cdn.example.org"
        )

    def test_an_unconfigured_checkout_gets_an_empty_string_not_a_broken_url(self):
        """Without a bucket there is nothing to point at, and `https://.` is worse."""
        assert self._base_url_with({}) == ""
        assert self._base_url_with({"OBJECT_STORAGE_BUCKET": "a-bucket"}) == ""
