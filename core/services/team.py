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
