"""The temporary Cloudinary → object-storage copy of the demo's fixture images.

It runs a handful of times and is then deleted, so these tests cover only what
could go wrong *silently* — a run that reports success while having done the
wrong thing. Everything visible (a network failure, a bad bucket name) announces
itself the moment it happens.

Three things qualify:

1. **A dry-run must write nothing.** It is the default, and the first thing
   anyone does with a command that copies 44 files into a fresh bucket.
2. **A file already there must be skipped, not re-uploaded.** That is what makes
   a half-finished run safe to re-run, which is the whole reason the command is
   idempotent rather than transactional.
3. **A response that is not an image must not be stored.** Cloudinary answering
   an HTML error page with 200 is exactly how an object ends up public with the
   wrong content type — the failure this migration spent a day finding.
"""

from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core.models import Thing, User

pytestmark = pytest.mark.django_db


@pytest.fixture
def seeded(settings):
    """One thing pointing at one seed image — the shape the command reads."""
    settings.CLOUDINARY_CLOUD_NAME = "test-cloud"
    owner = User.objects.create(email="seed@example.com")
    Thing.objects.create(
        owner=owner,
        headline="Cazo",
        type="GIFT_THING",
        thumbnail="oiueei/seed/l1l101",
    )
    return owner


def _run(**kwargs):
    out = StringIO()
    call_command("copy_seed_images", stdout=out, stderr=StringIO(), **kwargs)
    return out.getvalue()


def _response(content=b"\x89PNG", content_type="image/png"):
    res = type("R", (), {})()
    res.content = content
    res.headers = {"Content-Type": content_type}
    res.raise_for_status = lambda: None
    return res


def test_a_dry_run_writes_nothing(seeded):
    with (
        patch("core.services.storage.exists", return_value=False),
        patch("core.services.storage.put") as put,
        patch("requests.get") as get,
    ):
        out = _run()

    put.assert_not_called()
    get.assert_not_called()  # not even downloaded — a dry-run costs no bandwidth
    assert "DRY-RUN" in out
    assert "would copy: oiueei/seed/l1l101" in out


def test_an_object_already_there_is_skipped(seeded):
    with (
        patch("core.services.storage.exists", return_value=True),
        patch("core.services.storage.put") as put,
        patch("requests.get") as get,
    ):
        out = _run(commit=True)

    put.assert_not_called()
    get.assert_not_called()
    assert "1 already present" in out


def test_a_missing_object_is_copied_with_the_type_the_response_declared(seeded):
    with (
        patch("core.services.storage.exists", return_value=False),
        patch("core.services.storage.put") as put,
        patch("requests.get", return_value=_response(content_type="image/webp")),
    ):
        _run(commit=True)

    key, body, content_type = put.call_args.args
    assert (key, body, content_type) == ("oiueei/seed/l1l101", b"\x89PNG", "image/webp")


def test_a_non_image_response_is_never_stored(seeded):
    """A 200 carrying an HTML error page is how a public object gets the wrong type."""
    with (
        patch("core.services.storage.exists", return_value=False),
        patch("core.services.storage.put") as put,
        patch("requests.get", return_value=_response(b"<html>", "text/html")),
        pytest.raises(CommandError, match="did not copy"),
    ):
        _run(commit=True)

    put.assert_not_called()


def test_an_unseeded_database_refuses_rather_than_reporting_nothing_to_do(settings):
    """'0 copied' on an empty database looks exactly like success."""
    settings.CLOUDINARY_CLOUD_NAME = "test-cloud"
    with pytest.raises(CommandError, match="seed_demo"):
        _run()


def test_it_refuses_without_a_cloudinary_source(seeded, settings):
    settings.CLOUDINARY_CLOUD_NAME = ""
    with pytest.raises(CommandError, match="CLOUDINARY_URL"):
        _run()
