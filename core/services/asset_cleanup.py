"""Delete a record's stored assets when the record itself is deleted.

Wired as ``post_delete`` signal handlers on Thing, Collection and User (see
``core.apps.CoreConfig.ready``) so it covers direct deletes, the collection
view's orphan-thing sweep, and user-account cascades alike — anywhere a row
actually disappears. The destroy runs on ``transaction.on_commit`` (a
rolled-back delete keeps its images) and never raises: an orphaned asset is a
smaller problem than a delete that blows up.

Keys under ``storage.SEED_PREFIX`` are **never** destroyed. The demo's fixtures
are a shared pool: every database that has ever seeded points at the same
objects, so deleting one demo row — from the admin, from a cascade, from
anywhere — must not take an image away from every other environment. This used
to be handled only by ``seed_demo --reset`` suspending the whole mechanism,
which left the admin as an open trapdoor; the skip below closes it, and
``suspended()`` stays for what it is actually for.
"""

import logging
from contextlib import contextmanager

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from core.models import Collection, Thing, User
from core.services import storage

logger = logging.getLogger(__name__)

_suspended = False


@contextmanager
def suspended():
    """Disable asset cleanup for any delete performed inside the block."""
    global _suspended
    previous = _suspended
    _suspended = True
    try:
        yield
    finally:
        _suspended = previous


def _assets(instance):
    """Yield the storage key of each asset owned by ``instance`` (Thing/Collection/User)."""
    if isinstance(instance, Thing):
        if instance.thumbnail:
            yield instance.thumbnail
        for key in instance.gallery or []:
            yield key
    elif isinstance(instance, Collection):
        if instance.thumbnail:
            yield instance.thumbnail
        # The welcome PDF is an object like any other — no special case left. It
        # needed one under Cloudinary, which filed it under resource_type=image.
        if instance.welcome_doc:
            yield instance.welcome_doc
    elif isinstance(instance, User):
        if instance.photo:
            yield instance.photo


def _destroy(key):
    try:
        storage.delete(key)
    except Exception:
        logger.warning("Asset cleanup failed for %r", key, exc_info=True)


@receiver(post_delete, sender=Thing)
@receiver(post_delete, sender=Collection)
@receiver(post_delete, sender=User)
def _cleanup_assets_on_delete(sender, instance, **kwargs):
    if _suspended:
        return
    assets = [key for key in _assets(instance) if not key.startswith(storage.SEED_PREFIX)]
    if assets:
        transaction.on_commit(lambda: [_destroy(key) for key in assets])
