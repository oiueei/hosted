"""The team that runs a thing, without a query per collection.

``Thing.managers()`` and ``Thing.can_manage()`` walk every collection the thing
sits in, reading each one's owner and co-curators. Prefetched with
``managers_ready_collections`` they cost nothing; without it each collection
costs its own owner and co-owners queries, and a notice fanned out to the team
grows with the number of groups the thing lives in.

Lives in ``services`` rather than ``views`` because the booking service needs it
too (a service never imports from a view) and the views import it from here.
"""

from django.db.models import Prefetch, prefetch_related_objects


def managers_ready_collections():
    """The collection queryset that makes ``Thing.managers()`` (and
    ``can_manage``) fire **nothing** once prefetched: each collection with its
    ``owner`` selected — the fan-out reads ``c.owner`` per collection, and a
    plain ``prefetch_related("collections")`` would cost one owner query per
    collection — and its ``co_owners`` prefetched.

    Used as ``Prefetch("collections", queryset=managers_ready_collections())``
    by the notice fan-outs (a FAQ question, its answer or hiding, a hold request
    and its decision, a reservation made or cancelled), so a thing in many
    collections costs no query per collection to notify the whole team that
    runs it.
    """
    from core.models.collection import Collection

    return Collection.objects.select_related("owner").prefetch_related("co_owners")


def load_team(thing):
    """Make ``thing.managers()`` free on this instance, whatever loaded it.

    A no-op when the caller already prefetched ``collections`` (Django only
    fetches what an instance has not got), so a view that did its own prefetch
    pays nothing here, and one that did not still pays a constant two queries
    instead of a few per collection. Returns ``thing`` for chaining.
    """
    prefetch_related_objects(
        [thing], Prefetch("collections", queryset=managers_ready_collections())
    )
    return thing


def drop_team_notices_of(user, collection):
    """Take out of ``user``'s inbox the team notices of ``collection`` they no
    longer have any business with, because they have just stopped running it.

    A request, its decision and a reservation made reach whoever manages the
    thing (``InAppNotification.team_booking_notices``). Demoted from co-curator —
    or removed from the group, which removes the role too — a person kept those
    notices on screen, still asking them to decide what the server would now
    refuse (CA, 2026-10-02: "New request — Lolioctupus asked for…" in the inbox
    of someone just demoted). So they go, and only they, and only this
    collection's:

    - **only theirs** (``user``) and **only this collection's**
      (``payload.collection_code``);
    - **not what is theirs as a person** — their own requests, the
      ``DEMOTED_CO_OWNER`` that tells them what happened, group messages: none of
      those is a team notice, so they are never selected;
    - **not about a thing they still run.** A COMMUNITY member who contributed a
      thing is its manager whatever their role in the group; a thing in two
      collections is still theirs to decide if they curate the other one. The
      notice about it still asks for something they can do, so it stays.

    ``FAQ_QUESTION`` is deliberately not here: its payload carries no collection
    (only the thing's headline, the asker and the FAQ's code), so there is no
    way to say which of a person's questions belong to this group. Call it after
    the role has been removed, so ``can_manage`` sees the new state. Returns how
    many notices went.
    """
    from core.models import Thing
    from core.models.notification import InAppNotification

    notices = list(
        InAppNotification.team_booking_notices(
            InAppNotification.objects.filter(user=user, payload__collection_code=collection.code)
        )
    )
    if not notices:
        return 0
    codes = {n.payload.get("thing_code") for n in notices} - {None, ""}
    still_run = {
        thing.code
        for thing in Thing.objects.filter(code__in=codes).prefetch_related(
            Prefetch("collections", queryset=managers_ready_collections())
        )
        if thing.can_manage(user.code)
    }
    doomed = [n.pk for n in notices if n.payload.get("thing_code") not in still_run]
    InAppNotification.objects.filter(pk__in=doomed).delete()
    return len(doomed)
