"""Ending a membership: the one place a person leaves a group's ``invites``.

A thing lives in one collection and its owner always has access to it. A member who
leaves, or is removed, would otherwise leave things behind that nobody can manage from
inside the group, so the things go with the person: every one they own in that group,
whatever its status, in both modes (their contributions in a COMMUNITY collection, a
co-curator's catalogue entries in a PROPRIETARY one).
"""

from datetime import date

from django.db import transaction

from core.models import BookingPeriod, Thing
from core.models.booking import RETURNABLE_TYPES
from core.services.deletion_events import deleting_as
from core.services.email_service import send_thing_left_with_owner_email


def things_leaving_with(collection, user):
    """The things of ``user`` in ``collection`` that will go with them: all, any status."""
    return Thing.objects.filter(owner=user, collections=collection).order_by("created", "code")


def _people_to_tell(leaving, user):
    """Who must hear that a thing is going: one entry per (requester, thing) with a live
    request or reservation (``BookingPeriod.blocking_filter``), read before the delete
    takes the bookings with it. ``holding`` is true when they have the thing now — an
    accepted loan or rental that has already started. The leaving member's own bookings
    are not announced to them."""
    today = date.today()
    told = {}
    bookings = BookingPeriod.objects.filter(
        BookingPeriod.blocking_filter(), thing_code__in=leaving
    ).select_related("thing_code")
    for booking in bookings:
        if booking.requester_code_id == user.code:
            continue
        holding = (
            booking.status == BookingPeriod.Status.ACCEPTED
            and booking.thing_type in RETURNABLE_TYPES
            and booking.start_date is not None
            and booking.start_date <= today
        )
        key = (booking.requester_email, booking.thing_code_id)
        _, already = told.get(key, (None, False))
        told[key] = (booking.thing_code.headline, already or holding)
    return [(email, headline, holding) for (email, _), (headline, holding) in told.items()]


def end_membership(collection, user, *, actor):
    """Take ``user`` out of the group and delete their things there.

    ``actor`` is whoever does it (the member leaving, or the curator removing them):
    each ``THING_REMOVED`` event names them. Whoever had a live request or reservation on
    one of those things is emailed once the transaction commits, and never if it rolls
    back. Returns how many things were deleted.
    """
    with transaction.atomic(), deleting_as(actor):
        leaving = list(things_leaving_with(collection, user))
        to_tell = _people_to_tell(leaving, user)
        for thing in leaving:
            thing.delete()
        collection.invites.remove(user)
        # co_owners is a subset of invites by construction (promotion, never a
        # separate door in): losing membership must never leave a stale co-owner
        # row behind. A no-op for anyone who was never promoted.
        collection.co_owners.remove(user)

        group_headline = collection.headline

        def tell():
            for email, headline, holding in to_tell:
                send_thing_left_with_owner_email(
                    headline, group_headline, email, holding=holding, collection=collection
                )

        transaction.on_commit(tell)
    return len(leaving)
