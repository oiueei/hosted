"""Integration tests for the `cleanup_orphan_images` command (#9).

The bucket is mocked — what these assert is the command's classification logic:
which objects it treats as orphans, that a dry-run deletes nothing, that
`--commit` deletes only orphans, and that referenced / seed / out-of-window
objects are always kept.

The stakes are asymmetric and that is why the negative cases outnumber the
positive one. A missed orphan costs a few kilobytes a month. A wrongly deleted
object is somebody's photo, or the welcome PDF a collection emails to every new
member, gone with no way back — the bucket is the only copy.
"""

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from core.models import Collection, Thing

pytestmark = pytest.mark.django_db


def _asset(key, *, days_ago=2):
    """One listing entry, in the shape `storage.iter_objects` yields."""
    return {"key": key, "last_modified": timezone.now() - timedelta(days=days_ago), "size": 1024}


def _run(objects, commit=False):
    """Run the command with the bucket listing mocked; return (out, delete_mock)."""
    out = StringIO()
    with (
        patch("core.services.storage.iter_objects", return_value=iter(objects)),
        # delete_many answers with how many keys it was handed, as the real one does.
        patch("core.services.storage.delete_many", side_effect=len) as delete_mock,
    ):
        call_command("cleanup_orphan_images", commit=commit, stdout=out)
    return out.getvalue(), delete_mock


def test_dry_run_lists_orphan_but_deletes_nothing():
    out, delete_mock = _run([_asset("oiueei/things/orphan1")])
    assert "orphan: oiueei/things/orphan1" in out
    assert "DRY-RUN" in out
    delete_mock.assert_not_called()


def test_commit_deletes_only_orphans(user):
    Thing.objects.create(
        code="THKEEP",
        type="GIFT_THING",
        owner=user,
        headline="Keep",
        thumbnail="oiueei/things/keep",
    )
    resources = [_asset("oiueei/things/keep"), _asset("oiueei/things/orphan1")]
    out, delete_mock = _run(resources, commit=True)

    delete_mock.assert_called_once()
    assert delete_mock.call_args.args[0] == ["oiueei/things/orphan1"]
    assert "Deleted 1 orphan" in out


@pytest.mark.parametrize(
    "make_ref",
    [
        lambda u: Thing.objects.create(
            code="THREF1", type="GIFT_THING", owner=u, headline="x", thumbnail="oiueei/things/ref"
        ),
        lambda u: Thing.objects.create(
            code="THREF2", type="GIFT_THING", owner=u, headline="x", gallery=["oiueei/things/ref"]
        ),
        lambda u: setattr(u, "photo", "oiueei/things/ref") or u.save(),
        lambda u: Collection.objects.create(
            code="COREF1", owner=u, headline="x", thumbnail="oiueei/things/ref"
        ),
        # The welcome PDF lives in the same tree as the photos, so this sweep sees
        # it. Deleting one takes the document every new member is emailed.
        lambda u: Collection.objects.create(
            code="COREF2", owner=u, headline="x", welcome_doc="oiueei/things/ref"
        ),
    ],
)
def test_referenced_assets_are_kept(user, make_ref):
    make_ref(user)
    out, delete_mock = _run([_asset("oiueei/things/ref")], commit=True)
    delete_mock.assert_not_called()
    assert "1 in use" in out


def test_seed_folder_is_never_touched():
    # Unreferenced, old enough, in window — but under oiueei/seed/, so untouchable.
    out, delete_mock = _run([_asset("oiueei/seed/lala-cup")], commit=True)
    delete_mock.assert_not_called()
    assert "1 seed" in out


def test_recent_uploads_are_skipped():
    # 1 hour old → younger than the 24h min-age → treated as maybe-in-flight.
    out, delete_mock = _run([_asset("oiueei/things/fresh", days_ago=0)], commit=True)
    delete_mock.assert_not_called()
    assert "outside the age window" in out


def test_old_uploads_are_skipped():
    out, delete_mock = _run([_asset("oiueei/things/ancient", days_ago=40)], commit=True)
    delete_mock.assert_not_called()
    assert "1 orphan" not in out  # counted under the age window, not as an orphan


def test_every_listed_object_is_considered_however_many_there_are():
    """Paging is `storage.iter_objects`' job; the command must simply drain it."""
    out, delete_mock = _run([_asset(f"oiueei/things/o{i}") for i in range(250)], commit=True)
    sent = [key for call in delete_mock.call_args_list for key in call.args[0]]
    assert sent == [f"oiueei/things/o{i}" for i in range(250)]
    assert "Deleted 250 orphan" in out


def test_deletion_is_batched_so_one_failure_costs_a_batch_not_the_run():
    out, delete_mock = _run([_asset(f"oiueei/things/o{i}") for i in range(250)], commit=True)
    assert [len(call.args[0]) for call in delete_mock.call_args_list] == [100, 100, 50]


def test_a_failing_batch_is_reported_and_the_rest_still_go():
    """A bucket hiccup halfway through must not abandon the orphans after it."""
    err = StringIO()
    calls = []

    def flaky(batch):
        calls.append(batch)
        if len(calls) == 2:
            raise RuntimeError("bucket down")
        return len(batch)

    with (
        patch(
            "core.services.storage.iter_objects",
            return_value=iter([_asset(f"oiueei/things/o{i}") for i in range(250)]),
        ),
        patch("core.services.storage.delete_many", side_effect=flaky),
    ):
        call_command("cleanup_orphan_images", commit=True, stdout=StringIO(), stderr=err)

    assert len(calls) == 3
    assert "Failed to delete batch" in err.getvalue()


def test_an_unreachable_bucket_is_a_clean_error_not_a_traceback():
    """Run by hand on a dyno; the first thing anyone gets wrong is the credentials."""
    with patch("core.services.storage.iter_objects", side_effect=RuntimeError("no such bucket")):
        with pytest.raises(CommandError, match="Could not list stored objects"):
            call_command("cleanup_orphan_images", stdout=StringIO())
