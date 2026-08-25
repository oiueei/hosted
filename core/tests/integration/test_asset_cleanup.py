"""Stored-asset cleanup when a Thing / Collection / User is deleted.

The cleanup runs on transaction commit, so every test wraps the delete in
``django_capture_on_commit_callbacks(execute=True)`` and patches
``storage.delete`` (no real network calls).

What these protect is that a deleted record takes its objects with it — the
bucket has no notion of a foreign key, so nothing else will ever notice they are
unreachable — and, just as importantly, that a delete which *fails* to reach the
bucket still deletes the row. An orphaned object costs storage; a delete that
raises costs the user their action.
"""

from unittest.mock import patch

import pytest

from core.models import Collection, Thing, User
from core.services import asset_cleanup


@pytest.mark.django_db
class TestAssetCleanup:
    def test_thing_delete_destroys_thumbnail_and_gallery(self, django_capture_on_commit_callbacks):
        owner = User.objects.create(email="o1@example.com")
        thing = Thing.objects.create(
            owner=owner,
            headline="Drill",
            type="GIFT_THING",
            thumbnail="oiueei/things/cover",
            gallery=["oiueei/things/g1", "oiueei/things/g2"],
        )
        with patch("core.services.storage.delete") as destroy:
            with django_capture_on_commit_callbacks(execute=True):
                thing.delete()

        destroyed = {call.args[0] for call in destroy.call_args_list}
        assert destroyed == {
            "oiueei/things/cover",
            "oiueei/things/g1",
            "oiueei/things/g2",
        }

    def test_collection_delete_destroys_thumbnail(self, django_capture_on_commit_callbacks):
        owner = User.objects.create(email="o2@example.com")
        coll = Collection.objects.create(
            owner=owner, headline="C", thumbnail="oiueei/collections/c1"
        )
        with patch("core.services.storage.delete") as destroy:
            with django_capture_on_commit_callbacks(execute=True):
                coll.delete()

        assert [c.args[0] for c in destroy.call_args_list] == ["oiueei/collections/c1"]

    def test_user_delete_cascades_to_collection_and_thing_assets(
        self, django_capture_on_commit_callbacks
    ):
        owner = User.objects.create(email="o3@example.com", photo="oiueei/users/p1")
        Collection.objects.create(owner=owner, headline="C", thumbnail="oiueei/collections/c2")
        Thing.objects.create(
            owner=owner, headline="T", type="GIFT_THING", thumbnail="oiueei/things/t1"
        )
        with patch("core.services.storage.delete") as destroy:
            with django_capture_on_commit_callbacks(execute=True):
                owner.delete()  # FK cascade deletes the collection and the thing

        destroyed = {call.args[0] for call in destroy.call_args_list}
        assert {"oiueei/users/p1", "oiueei/collections/c2", "oiueei/things/t1"} <= destroyed

    def test_empty_image_fields_destroy_nothing(self, django_capture_on_commit_callbacks):
        owner = User.objects.create(email="o4@example.com")  # no photo
        with patch("core.services.storage.delete") as destroy:
            with django_capture_on_commit_callbacks(execute=True):
                owner.delete()
        destroy.assert_not_called()

    def test_a_storage_failure_does_not_break_the_delete(self, django_capture_on_commit_callbacks):
        owner = User.objects.create(email="o5@example.com")
        thing = Thing.objects.create(
            owner=owner, headline="T", type="GIFT_THING", thumbnail="oiueei/things/boom"
        )
        with patch("core.services.storage.delete", side_effect=RuntimeError("bucket down")):
            with django_capture_on_commit_callbacks(execute=True):
                thing.delete()  # must not raise
        assert not Thing.objects.filter(code=thing.code).exists()

    def test_seed_reset_does_not_touch_the_bucket(self, django_capture_on_commit_callbacks):
        from django.core.management import call_command

        call_command("seed_demo")  # demo things carry real shared storage keys
        with patch("core.services.storage.delete") as destroy:
            with django_capture_on_commit_callbacks(execute=True):
                call_command("seed_demo", "--reset")  # deletes then re-creates
        destroy.assert_not_called()

    def test_suspended_context_blocks_cleanup(self, django_capture_on_commit_callbacks):
        owner = User.objects.create(email="o6@example.com", photo="oiueei/users/keep")
        with patch("core.services.storage.delete") as destroy:
            with django_capture_on_commit_callbacks(execute=True):
                with asset_cleanup.suspended():
                    owner.delete()
        destroy.assert_not_called()


@pytest.mark.django_db
class TestSeedPoolIsNeverDestroyed:
    """The demo's fixture pool survives any delete.

    These exist because the pool was destroyed for real: deleting the demo from
    the Django admin emptied the whole ``oiueei/seed/`` folder. ``seed_demo
    --reset`` was safe because it suspends the mechanism; every other door —
    the admin, a cascade, a shell delete — was not. The pool is shared by every
    database that has ever seeded, so one row's delete must never reach it.
    """

    def test_thing_delete_spares_seed_keys(self, django_capture_on_commit_callbacks):
        owner = User.objects.create(email="seed1@example.com")
        thing = Thing.objects.create(
            owner=owner,
            headline="Demo drill",
            type="GIFT_THING",
            thumbnail="oiueei/seed/l1l112",
            gallery=["oiueei/seed/l1l112_b"],
        )
        with patch.object(asset_cleanup.storage, "delete") as destroy:
            with django_capture_on_commit_callbacks(execute=True):
                thing.delete()
        destroy.assert_not_called()

    def test_collection_and_user_deletes_spare_seed_keys(self, django_capture_on_commit_callbacks):
        owner = User.objects.create(email="seed2@example.com", photo="oiueei/seed/1u1uPH")
        collection = Collection.objects.create(
            owner=owner, headline="Demo group", thumbnail="oiueei/seed/l1l1C1"
        )
        with patch.object(asset_cleanup.storage, "delete") as destroy:
            with django_capture_on_commit_callbacks(execute=True):
                collection.delete()
                owner.delete()
        destroy.assert_not_called()

    def test_a_real_upload_alongside_a_seed_key_still_goes(
        self, django_capture_on_commit_callbacks
    ):
        """The skip is per key, not per record — a genuine upload is still cleaned."""
        owner = User.objects.create(email="seed3@example.com")
        thing = Thing.objects.create(
            owner=owner,
            headline="Half and half",
            type="GIFT_THING",
            thumbnail="oiueei/seed/l1l112",
            gallery=["oiueei/things/a-real-upload"],
        )
        with patch.object(asset_cleanup.storage, "delete") as destroy:
            with django_capture_on_commit_callbacks(execute=True):
                thing.delete()
        destroy.assert_called_once_with("oiueei/things/a-real-upload")
