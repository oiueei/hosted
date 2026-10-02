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

**A key another row still holds is never destroyed either** (2026-10-02). A
row does not own its keys: a key is the path of its public URL, and
``ImageIdField`` binds it to a folder, not to an uploader. So a member who
could see someone else's photo could save its key on a thing of their own and
delete that thing — and this handler deleted the other person's photo with it.
The check runs at destroy time, after the commit, so the row being deleted no
longer counts.
"""

import logging
from contextlib import contextmanager

from django.db import transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver

from core.models import Collection, Thing, User
from core.services import storage

logger = logging.getLogger(__name__)

# Every column that holds a storage key. The delete handler, the in-use check
# and the orphan sweep (``cleanup_orphan_images``) all read this one table: a
# field missing from one copy of a hand-written list is a live photo deleted.
ASSET_FIELDS = {
    Thing: ("thumbnail", "gallery"),
    # The welcome PDF is an object like any other — no special case left. It
    # needed one under Cloudinary, which filed it under resource_type=image.
    Collection: ("thumbnail", "welcome_doc"),
    User: ("photo",),
}
# The one column that holds an ordered list of keys rather than a single key.
_LIST_FIELDS = frozenset({"gallery"})

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


def _keys(field, value):
    """The keys one column value holds, in order, empties dropped."""
    if field in _LIST_FIELDS:
        return [key for key in value or [] if key]
    return [value] if value else []


def _assets(instance):
    """Yield the storage key of each asset ``instance`` (Thing/Collection/User) holds."""
    for model, fields in ASSET_FIELDS.items():
        if isinstance(instance, model):
            for field in fields:
                yield from _keys(field, getattr(instance, field))


def referenced_keys():
    """Every storage key some row holds — what the orphan sweep must keep."""
    referenced = set()
    for model, fields in ASSET_FIELDS.items():
        for row in model.objects.values_list(*fields):
            for field, value in zip(fields, row, strict=True):
                referenced.update(_keys(field, value))
    return referenced


def is_referenced(key):
    """Whether any row still holds ``key``."""
    for model, fields in ASSET_FIELDS.items():
        for field in fields:
            if field in _LIST_FIELDS:
                # SQLite has no JSON containment lookup, so match the list's text
                # on every backend and confirm on the decoded list: a substring of
                # another key is not this key.
                lists = model.objects.filter(**{f"{field}__icontains": key}).values_list(
                    field, flat=True
                )
                if any(key in (value or []) for value in lists):
                    return True
            elif model.objects.filter(**{field: key}).exists():
                return True
    return False


def _destroy(key):
    try:
        if is_referenced(key):
            logger.info("Asset %r is still in use by another record; kept", key)
            return
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
