"""Ending a membership: the one place a person leaves a group's ``invites``.

A thing lives in one collection and its owner always has access to it. A member who
leaves, or is removed, would otherwise leave things behind that nobody can manage from
inside the group, so the things go with the person: every one they own in that group,
whatever its status, in both modes (their contributions in a COMMUNITY collection, a
co-curator's catalogue entries in a PROPRIETARY one).
"""

from django.db import transaction

from core.models import Thing
from core.services.deletion_events import deleting_as


def things_leaving_with(collection, user):
    """The things of ``user`` in ``collection`` that will go with them: all, any status."""
    return Thing.objects.filter(owner=user, collections=collection).order_by("created", "code")


def end_membership(collection, user, *, actor):
    """Take ``user`` out of the group and delete their things there.

    ``actor`` is whoever does it (the member leaving, or the curator removing them):
    each ``THING_REMOVED`` event names them. Returns how many things were deleted.
    """
    with transaction.atomic(), deleting_as(actor):
        leaving = list(things_leaving_with(collection, user))
        for thing in leaving:
            thing.delete()
        collection.invites.remove(user)
        # co_owners is a subset of invites by construction (promotion, never a
        # separate door in): losing membership must never leave a stale co-owner
        # row behind. A no-op for anyone who was never promoted.
        collection.co_owners.remove(user)
    return len(leaving)
