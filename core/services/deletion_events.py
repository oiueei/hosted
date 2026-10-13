"""Record a deletion in the Event log when the row goes, whichever way it goes.

The log is the only memory of a hard-deleted collection or thing, so a delete that
leaves no event leaves a hole every weekly count carries forever. Writing the events
in the two views that delete (the API) lost every other path: the admin, the cascade
of an account erasure, the retention purge, a ``QuerySet.delete()``. They are written
here instead, as signal receivers on the models themselves (wired in
``core.apps.CoreConfig.ready``), so no future delete can skip them.

- ``post_delete`` of a Collection → ``COLLECTION_DELETED``.
- ``post_delete`` of a Thing → ``THING_REMOVED`` (with its type).
- ``pre_delete`` of a User → one ``MEMBER_LEFT`` per collection they were a member of
  (the M2M rows are still there in ``pre_delete``; the user's own collections and things
  are covered by their own receivers when the cascade deletes them).

The events are written inside the delete's transaction — never on commit — so a
rollback leaves no event behind. ``instance.code`` is still the original in
``post_delete`` (Django nulls the primary key afterwards).

The actor is whoever is deleting, which a receiver cannot know: ``deleting_as(user)``
sets it for the block (the API views and the account erasure do). Outside one — the
admin, a shell — the actor is blank. ``deletion_events_suppressed()`` turns the
recording off for what is not history, such as the demo's reset.
"""

from contextlib import contextmanager
from contextvars import ContextVar

from django.db.models.signals import post_delete, pre_delete
from django.dispatch import receiver

from core.models import Collection, Event, Thing, User

_actor = ContextVar("deletion_actor", default="")
_suppressed = ContextVar("deletion_events_suppressed", default=False)


@contextmanager
def deleting_as(actor):
    """Attribute the deletions made inside the block to ``actor`` (a user or a code)."""
    token = _actor.set(getattr(actor, "code", actor) or "")
    try:
        yield
    finally:
        _actor.reset(token)


@contextmanager
def deletion_events_suppressed():
    """Record no deletion event for what is deleted inside the block."""
    token = _suppressed.set(True)
    try:
        yield
    finally:
        _suppressed.reset(token)


@receiver(post_delete, sender=Collection, dispatch_uid="deletion_events.collection")
def _collection_deleted(sender, instance, **kwargs):
    if _suppressed.get():
        return
    Event.log(Event.Kind.COLLECTION_DELETED, actor=_actor.get(), collection=instance.code)


@receiver(post_delete, sender=Thing, dispatch_uid="deletion_events.thing")
def _thing_removed(sender, instance, **kwargs):
    if _suppressed.get():
        return
    Event.log(
        Event.Kind.THING_REMOVED,
        actor=_actor.get(),
        thing=instance.code,
        thing_type=instance.type,
    )


@receiver(pre_delete, sender=User, dispatch_uid="deletion_events.user")
def _user_leaves_their_groups(sender, instance, **kwargs):
    if _suppressed.get():
        return
    for collection_code in instance.invited_to_collections.values_list("code", flat=True):
        Event.log(Event.Kind.MEMBER_LEFT, actor=instance.code, collection=collection_code)
