"""One week of the series, derived from the event log.

Pure functions over `Event`, `DailyActivity` and `CreatorValidation`: they write
nothing. **The same function serves the backfill and the live recording**, which is
what guarantees the two cannot give different numbers for the same week.

Definitions that the tests pin:

- **The week** runs from Monday 00:00 to Sunday 23:59:59.999 in `WEEK_TZ`
  (`Europe/Madrid` unless `STATS_WEEK_TZ` says otherwise), whatever `TIME_ZONE` is.
  An event belongs to the week when ``start <= created < cutoff``, the cutoff being
  the start of the next Monday.
- **What is real** is decided by `_real_events`, once, for the whole history.
- **A person enters the real population with their first real event**: a
  `MEMBER_JOINED` or a `COLLECTION_CREATED`. `USER_JOINED` does not count: a visit
  through the open door generates one without entering anything real.
- **Stocks at the cutoff** are rebuilt from the log: a collection is alive when its
  `COLLECTION_CREATED` has no later `COLLECTION_DELETED`; a membership is a
  (person, collection) pair whose last `MEMBER_JOINED` / `MEMBER_LEFT` is a join, in
  a live collection; a creator owns a live collection; a guest has a membership and
  is not a creator; a thing is alive until its `THING_REMOVED`, and its verb is the
  `thing_type` of its `THING_ADDED` (a later change of type is accepted drift).
- **The organic cycle** follows people whose first real relation is a
  `MEMBER_JOINED`, through six stages (`cycle_*`). The stages count how many people
  reached each one, without requiring the order between the second and third.
  Their date for "returned" is the second distinct day of `DailyActivity` on or
  after the day they entered.
- **Generations:** an owner who has no real `MEMBER_JOINED` before their first
  `COLLECTION_CREATED` is *seeded* (generation 0); an organic owner is one more than
  the owner of the collection of their first real join. That owner comes from the
  `COLLECTION_CREATED` with that code, which survives the collection being deleted.
  If that event is not in the log, the parent counts as generation 0.

- **The five seed characters stand for nothing, whoever acts.** Everything done by them,
  in a collection of theirs or on a thing of theirs is out (`seed_scope`): the operator
  signs in as them to try the product in production without touching a number. The
  person who asked or joined is not erased, only that event stops counting, so their
  first real join may become the next one.
- **What vanished without a trace** (rules 1 to 4, `_Vanished`) reads the state of
  *today*, but only for what left no event: since deletions are logged by the models,
  none of them can fire for anything new. They are the reason the history does not use
  `_partition()` either: that one sorts people by today's state, these rules only fill
  the holes of the log.
  1. A *phantom collection* has a `COLLECTION_CREATED`, no `COLLECTION_DELETED` and no
     row in `Collection`: it was never real, so all its events and those of the things
     added to it are out.
  2. An *orphan thing without a trace* was added to a collection that has a
     `COLLECTION_DELETED`, has no `THING_REMOVED` and has no row in `Thing`: it counts as
     removed at the moment of that deletion. It is **not** a `things_removed` movement of
     that week, because no event says so.
  3. A *thing without a trace in a live collection* has no row, no `THING_REMOVED` and
     its collection exists: a phantom, out as a whole like rule 1.
  4. A *person who no longer exists* has no row in `User` and open memberships: they
     close at the person's **last event** (of any time, so a past week still sees the
     membership). The person stays in the history: they were there, and left.

Nothing here keeps a user code: the results are counts and medians.
"""

import os
import statistics
from collections import defaultdict
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.db.models import Max

from core.management.commands.seed_data.common import COLLECTIONS as _SEED_COLLECTIONS
from core.management.commands.seed_data.common import THINGS as _SEED_THINGS
from core.management.commands.seed_data.common import USERS as _SEED_USERS
from core.models import Collection, DailyActivity, Event, Thing, User
from hosted.models import CreatorValidation

WEEK_TZ = ZoneInfo(os.environ.get("STATS_WEEK_TZ", "Europe/Madrid"))
FIRST_WEEK = date(2026, 9, 7)
SCHEMA_VERSION = 1

SEED_USER_CODES = frozenset(u["code"] for u in _SEED_USERS)
SEED_COLLECTION_CODES = frozenset(c["code"] for c in _SEED_COLLECTIONS)
SEED_THING_CODES = frozenset(t["code"] for t in _SEED_THINGS)

K = Event.Kind
REQUEST_TYPES = ("GIFT_THING", "SELL_THING", "LEND_THING", "RENT_THING")
RESERVE_TYPE = "RESERVE_THING"
ALL_TYPES = REQUEST_TYPES + (RESERVE_TYPE,)

# Window, in weeks, after which a cohort's conversion to owner is reported.
COHORT_WINDOWS = (1, 2, 4, 8)

LIVE_ONLY_KEYS = ("collections_community", "collections_public", "things_available")

METRIC_KEYS = (
    # Stocks at the cutoff.
    "creators",
    "creators_seeded",
    "creators_organic",
    "guests",
    "collections",
    "memberships",
    "things",
    "things_gift",
    "things_sell",
    "things_lend",
    "things_rent",
    "things_reserve",
    # Movements of the week.
    "new_people",
    "new_guests",
    "new_creators",
    "new_creators_organic",
    "collections_created",
    "collections_deleted",
    "things_added",
    "things_removed",
    "requests",
    "requests_gift",
    "requests_sell",
    "requests_lend",
    "requests_rent",
    "requests_accepted",
    "reservations",
    "joins_invite",
    "joins_recommendation",
    "joins_share",
    "joins_public",
    "joins_unknown",
    "validations_requested",
    "validations_approved",
    "active_creators",
    "active_guests",
    # The cycle, accumulated at the cutoff.
    "cycle_entered",
    "cycle_returned",
    "cycle_requested",
    "cycle_owner",
    "cycle_first_thing",
    "cycle_closed",
    "cycle_median_days_to_owner",
    "owner_median_days_to_first_request",
    "owners_gen0",
    "owners_gen1",
    "owners_gen2plus",
    # Only when recorded live: they describe the state of today.
    *LIVE_ONLY_KEYS,
)


def week_bounds(week_start):
    """``(start, cutoff)`` as aware datetimes: Monday 00:00 and the next Monday 00:00."""
    start = datetime.combine(week_start, time.min, tzinfo=WEEK_TZ)
    cutoff = datetime.combine(week_start + timedelta(days=7), time.min, tzinfo=WEEK_TZ)
    return start, cutoff


def _monday_of(moment):
    local = moment.astimezone(WEEK_TZ).date()
    return local - timedelta(days=local.weekday())


def _days(delta):
    return round(delta.total_seconds() / 86400, 2)


def _median(values):
    return statistics.median(values) if values else None


def seed_scope(events=None):
    """``(collections, things)`` that belong to the five seed characters.

    The fixed codes of the seed, plus what a character created later from the app
    (their `COLLECTION_CREATED` / `THING_ADDED`), plus what is theirs today (for what left
    no event), plus the things added to any of those collections. ``events`` are the ones
    already loaded; without them the log is read. Shared with `stats_summary`'s
    accumulated history, which counts raw events and must leave the same ones out.
    """
    if events is None:
        events = list(
            Event.objects.filter(kind__in=(K.COLLECTION_CREATED, K.THING_ADDED)).filter(
                actor_code__in=SEED_USER_CODES
            )
        )
    collections = set(SEED_COLLECTION_CODES)
    things = set(SEED_THING_CODES)
    for e in events:
        if e.actor_code in SEED_USER_CODES:
            if e.kind == K.COLLECTION_CREATED:
                collections.add(e.collection_code)
            elif e.kind == K.THING_ADDED and e.thing_code:
                things.add(e.thing_code)
    collections |= set(
        Collection.objects.filter(owner_id__in=SEED_USER_CODES).values_list("code", flat=True)
    )
    things |= set(Thing.objects.filter(owner_id__in=SEED_USER_CODES).values_list("code", flat=True))
    # What other people added to a character's collection is the character's scene.
    things |= {
        e.thing_code
        for e in events
        if e.kind == K.THING_ADDED and e.collection_code in collections and e.thing_code
    }
    collections.discard("")
    things.discard("")
    return collections, things


class _Vanished:
    """What the log lost, read once: today's codes and the deletions of any time.

    Five queries however many weeks are asked for in one `_History`: the codes of
    `Collection`, `Thing` and `User`, the deletion markers of the log (not cut at the
    cutoff: a collection deleted next week was alive this one) and the last event of
    every actor.
    """

    def __init__(self):
        self.collections = set(Collection.objects.values_list("code", flat=True))
        self.things = set(Thing.objects.values_list("code", flat=True))
        self.users = set(User.objects.values_list("code", flat=True))
        self.collection_deleted_at = {}
        self.thing_removed = set()
        for kind, collection, thing, created in Event.objects.filter(
            kind__in=(K.COLLECTION_DELETED, K.THING_REMOVED)
        ).values_list("kind", "collection_code", "thing_code", "created"):
            if kind == K.COLLECTION_DELETED:
                self.collection_deleted_at.setdefault(collection, created)
            else:
                self.thing_removed.add(thing)
        self.last_event = {
            actor: last
            for actor, last in Event.objects.exclude(actor_code="")
            .values_list("actor_code")
            .annotate(last=Max("created"))
        }

    def ghosts(self, events):
        """``(collections, things)`` whose events are all out (rules 1 and 3)."""
        created = {e.collection_code for e in events if e.kind == K.COLLECTION_CREATED}
        phantom_collections = {
            code
            for code in created
            if code not in self.collection_deleted_at and code not in self.collections
        }
        phantom_things = set()
        for e in events:
            if e.kind != K.THING_ADDED or not e.thing_code:
                continue
            if e.thing_code in self.things or e.thing_code in self.thing_removed:
                continue
            if e.collection_code in phantom_collections or e.collection_code in self.collections:
                phantom_things.add(e.thing_code)
        return phantom_collections, phantom_things

    def orphans(self, events):
        """``{thing code: when its collection was deleted}`` for rule 2."""
        return {
            e.thing_code: self.collection_deleted_at[e.collection_code]
            for e in events
            if e.kind == K.THING_ADDED
            and e.thing_code
            and e.collection_code in self.collection_deleted_at
            and e.thing_code not in self.things
            and e.thing_code not in self.thing_removed
        }


def _real_events(cutoff, vanished=None):
    """Every real event before ``cutoff``, oldest first.

    This is **not** `stats_summary._partition()`, on purpose: that function sorts
    people by their state *today*, so a guest of week 38 who has since left their group
    would come out as demo and their events would vanish from the history. Here the
    exclusion is made event by event, from what the event itself says:

    - the actor is one of the five seed characters, or it is about a collection or a
      thing of theirs (`seed_scope`);
    - it is about a collection that is `is_onboarding`;
    - it is a `MEMBER_JOINED` through the open door (`source == ONBOARDING`);
    - it is about a thing whose `THING_ADDED` fell in an onboarding collection
      (`HOLD_REQUESTED` and `THING_REMOVED` carry no collection of their own);
    - it is about a phantom collection or thing (rules 1 and 3 of the module).
    """
    vanished = vanished or _Vanished()
    onboarding = set(Collection.objects.filter(is_onboarding=True).values_list("code", flat=True))
    events = list(Event.objects.filter(created__lt=cutoff).order_by("created", "code"))
    seed_collections, seed_things = seed_scope(events)
    ghost_collections, ghost_things = vanished.ghosts(events)
    demo_things = {
        e.thing_code
        for e in events
        if e.kind == K.THING_ADDED and e.collection_code in onboarding and e.thing_code
    }
    out_collections = onboarding | seed_collections | ghost_collections
    out_things = demo_things | seed_things | ghost_things
    # A thing added to a phantom collection is as phantom as it is.
    out_things |= {
        e.thing_code
        for e in events
        if e.kind == K.THING_ADDED and e.collection_code in ghost_collections and e.thing_code
    }
    return [
        e
        for e in events
        if e.actor_code not in SEED_USER_CODES
        and e.collection_code not in out_collections
        and not (e.kind == K.MEMBER_JOINED and e.source == Event.Source.ONBOARDING)
        and e.thing_code not in out_things
    ]


def real_events(cutoff):
    """The public door to `_real_events`: every real event before ``cutoff``, oldest first.

    What the operator report counts from the log must be what the series counts, so it
    reads the events through this function and never through its own filters. It does
    not drop the people `stats_summary._partition()` calls demo (the visitors of the
    open door who only left a `USER_JOINED`): the series does not either, and a caller
    that wants that adds it.
    """
    return _real_events(cutoff, _Vanished())


def retired_orphans(events):
    """``{thing code: moment}`` of the things rule 2 takes as removed with their collection.

    ``events`` are the real ones (`real_events`). The things of a collection that was
    deleted without a removal of their own and are gone from the database. `_History`
    reads the same through `_Vanished.orphans`, so the series and the report agree.
    """
    return _Vanished().orphans(events)


class _History:
    """Everything the week needs, indexed once from the real events before the cutoff."""

    def __init__(self, cutoff):
        self.cutoff = cutoff
        vanished = _Vanished()
        self.events = _real_events(cutoff, vanished)

        self.collection_creator = {}  # code -> actor (survives the collection's deletion)
        self.collection_deleted = set()
        self.membership = {}  # (actor, collection) -> bool
        self.thing_added = {}  # code -> event
        self.thing_removed = set()
        self.first_join = {}  # person -> event
        self.first_created = {}  # person -> event
        self.first_request = {}  # person -> datetime
        self.requests_by_thing = defaultdict(list)  # thing code -> [datetime]
        self.things_by_actor = defaultdict(list)  # person -> [event]
        for e in self.events:
            if e.kind == K.COLLECTION_CREATED:
                self.collection_creator.setdefault(e.collection_code, e.actor_code)
                self.first_created.setdefault(e.actor_code, e)
            elif e.kind == K.COLLECTION_DELETED:
                self.collection_deleted.add(e.collection_code)
            elif e.kind == K.MEMBER_JOINED:
                self.membership[(e.actor_code, e.collection_code)] = True
                self.first_join.setdefault(e.actor_code, e)
            elif e.kind == K.MEMBER_LEFT:
                self.membership[(e.actor_code, e.collection_code)] = False
            elif e.kind == K.THING_ADDED:
                self.thing_added.setdefault(e.thing_code, e)
                self.things_by_actor[e.actor_code].append(e)
            elif e.kind == K.THING_REMOVED:
                self.thing_removed.add(e.thing_code)
            elif e.kind == K.HOLD_REQUESTED:
                self.first_request.setdefault(e.actor_code, e.created)
                self.requests_by_thing[e.thing_code].append(e.created)

        # Rule 2: a thing whose collection was deleted without a trace of its own is
        # taken as removed when that collection was.
        for code, when in vanished.orphans(self.events).items():
            if when < cutoff:
                self.thing_removed.add(code)
        # Rule 4: somebody who no longer exists left every group at their last event.
        for (actor, collection), joined in list(self.membership.items()):
            last = vanished.last_event.get(actor)
            if joined and actor not in vanished.users and last is not None and last < cutoff:
                self.membership[(actor, collection)] = False

        self.alive_collections = {
            code for code in self.collection_creator if code not in self.collection_deleted
        }
        self.creators = {self.collection_creator[code] for code in self.alive_collections}
        self.memberships = {
            pair
            for pair, joined in self.membership.items()
            if joined and pair[1] in self.alive_collections
        }
        members = {actor for actor, _ in self.memberships}
        self.guests = members - self.creators

        # The organic cycle: people whose first real relation is a join.
        self.cycle = {
            person
            for person, joined in self.first_join.items()
            if person not in self.first_created
            or joined.created < self.first_created[person].created
        }
        self.owner_at = {
            person: self.first_created[person].created
            for person in self.cycle
            if person in self.first_created
        }
        self.seeded_owners = set(self.first_created) - self.cycle
        self._generation = {}

    # --- generations -------------------------------------------------------------

    def parent_of(self, person):
        """The owner of the collection of this person's first real join, or ``None``."""
        return self.collection_creator.get(self.first_join[person].collection_code)

    def generation(self, person, _seen=()):
        """0 for a seeded owner (and for anyone unknown), else one more than the parent's."""
        if person not in self.owner_at or person in _seen:
            return 0
        if person not in self._generation:
            parent = self.parent_of(person)
            self._generation[person] = 1 + self.generation(parent, _seen + (person,))
        return self._generation[person]

    # --- the cycle ---------------------------------------------------------------

    def stage_counts(self, activity_dates):
        """How many cycle people reached each stage by the cutoff."""
        returned = 0
        for person in self.cycle:
            entered_day = self.first_join[person].created.astimezone(WEEK_TZ).date()
            days = {d for d in activity_dates.get(person, ()) if d >= entered_day}
            if len(days) >= 2:
                returned += 1

        first_thing = sum(
            1
            for person, owned in self.owner_at.items()
            if any(e.created > owned for e in self.things_by_actor.get(person, ()))
        )

        closed = set()
        for e in self.events:
            if e.kind != K.MEMBER_JOINED:
                continue
            owner = self.collection_creator.get(e.collection_code)
            if (
                owner in self.owner_at
                and owner != e.actor_code
                and e.created > self.owner_at[owner]
            ):
                closed.add(owner)

        return {
            "cycle_entered": len(self.cycle),
            "cycle_returned": returned,
            "cycle_requested": sum(1 for p in self.cycle if p in self.first_request),
            "cycle_owner": len(self.owner_at),
            "cycle_first_thing": first_thing,
            "cycle_closed": len(closed),
        }

    def median_days_to_owner(self):
        return _median(
            [_days(owned - self.first_join[p].created) for p, owned in self.owner_at.items()]
        )

    def median_days_to_first_request(self):
        """Owner → first request or reservation *received* on a thing they added."""
        waits = []
        for person, owned in self.owner_at.items():
            received = [
                moment
                for e in self.things_by_actor.get(person, ())
                for moment in self.requests_by_thing.get(e.thing_code, ())
            ]
            if received:
                waits.append(_days(min(received) - owned))
        return _median(waits)


def _activity_dates(people, cutoff):
    """``{user code: {dates}}`` of `DailyActivity` before the cutoff's day."""
    found = defaultdict(set)
    rows = DailyActivity.objects.filter(
        user_id__in=people, date__lt=cutoff.astimezone(WEEK_TZ).date()
    ).values_list("user_id", "date")
    for user_id, day in rows:
        found[user_id].add(day)
    return found


def cohorts_as_of(cutoff):
    """The conversion triangle: for each week of entry, how many became owners in time.

    ``size`` is how many people entered, ``owners`` how many of them are owners by the
    cutoff whenever it happened, and ``owner_within`` how many were within each window.

    Keyed by the Monday (ISO) of the week the people entered. A window of ``w`` weeks
    is reported only once it has elapsed in full for the *whole* cohort, that is, when
    the week the cohort closed plus ``w`` weeks is not after the cutoff — otherwise
    the number would still be moving. The last snapshot therefore keeps the whole
    triangle even after the log is anonymised.
    """
    history = _History(cutoff)
    by_week = defaultdict(list)
    for person in history.cycle:
        by_week[_monday_of(history.first_join[person].created)].append(person)

    triangle = {}
    for week, people in sorted(by_week.items()):
        closed_at = week_bounds(week)[1]
        within = {}
        for w in COHORT_WINDOWS:
            if closed_at + timedelta(weeks=w) <= cutoff:
                within[str(w)] = sum(
                    1
                    for p in people
                    if p in history.owner_at
                    and history.owner_at[p] - history.first_join[p].created <= timedelta(weeks=w)
                )
        triangle[week.isoformat()] = {
            "size": len(people),
            "owners": sum(1 for p in people if p in history.owner_at),
            "owner_within": within,
        }
    return triangle


def generation_k(cutoff):
    """See `_generation_rows`; this is the version that reads the log up to ``cutoff``."""
    return _generation_rows(_History(cutoff))


def _generation_rows(history):
    """One row per generation of owners: how many, how many they brought, how many converted.

    ``k`` is ``next_owners / owners``, split into its two factors: guests brought per
    owner of the generation (people whose first real join was in a collection of
    theirs) and the share of those who became owners themselves. Not stored: the
    counts per generation already travel in ``owners_gen*``.
    """
    owners = defaultdict(list)
    for person in history.owner_at:
        owners[history.generation(person)].append(person)
    for person in history.seeded_owners:
        owners[0].append(person)

    brought = defaultdict(int)
    converted = defaultdict(int)
    for person in history.cycle:
        parent = history.parent_of(person)
        if parent is None:
            continue
        g = history.generation(parent)
        brought[g] += 1
        if person in history.owner_at:
            converted[g] += 1

    rows = []
    for g in range(max(owners, default=-1) + 1):
        count = len(owners.get(g, ()))
        if not count:
            continue
        next_owners = len(owners.get(g + 1, ()))
        rows.append(
            {
                "generation": g,
                "owners": count,
                "next_owners": next_owners,
                "k": next_owners / count,
                "brought": brought[g],
                "converted": converted[g],
            }
        )
    return rows


def _live_only():
    """The three numbers that describe the state of today, over what is real."""
    real_collections = Collection.objects.filter(is_onboarding=False).exclude(
        owner_id__in=SEED_USER_CODES
    )
    return {
        "collections_community": real_collections.filter(mode=Collection.Mode.COMMUNITY).count(),
        "collections_public": real_collections.filter(
            visibility=Collection.Visibility.PUBLIC
        ).count(),
        "things_available": Thing.objects.filter(
            status=Thing.Status.ACTIVE, collections__is_onboarding=False
        )
        .exclude(owner_id__in=SEED_USER_CODES)
        .distinct()
        .count(),
    }


def snapshot_metrics(week_start, *, live=False):
    """Every metric of one week, plus the cohort triangle under ``"cohorts"``.

    ``live`` fills in the three keys that describe today's state; a rebuilt past week
    has them as ``None`` because the log cannot say what they were.
    """
    start, cutoff = week_bounds(week_start)
    history = _History(cutoff)
    in_week = [e for e in history.events if e.created >= start]

    def count(kind, **match):
        return sum(
            1
            for e in in_week
            if e.kind == kind and all(getattr(e, name) == value for name, value in match.items())
        )

    def stock(verb):
        return sum(
            1
            for code, e in history.thing_added.items()
            if code not in history.thing_removed and e.thing_type == verb
        )

    def entered_in_week(first):
        return {p for p, e in first.items() if e.created >= start}

    new_creators = entered_in_week(history.first_created)
    joiners = entered_in_week(history.first_join)
    first_real = {
        p
        for p in set(history.first_join) | set(history.first_created)
        if min(e.created for e in (history.first_join.get(p), history.first_created.get(p)) if e)
        >= start
    }

    week_activity = defaultdict(set)
    for user_id, day in DailyActivity.objects.filter(
        date__gte=start.date(), date__lt=cutoff.date()
    ).values_list("user_id", "date"):
        week_activity[user_id].add(day)

    activity = _activity_dates(history.cycle, cutoff)
    gens = [history.generation(p) for p in history.owner_at]

    metrics = {
        "creators": len(history.creators),
        "creators_organic": len(history.creators & history.cycle),
        "guests": len(history.guests),
        "collections": len(history.alive_collections),
        "memberships": len(history.memberships),
        "things": sum(1 for code in history.thing_added if code not in history.thing_removed),
        "things_gift": stock("GIFT_THING"),
        "things_sell": stock("SELL_THING"),
        "things_lend": stock("LEND_THING"),
        "things_rent": stock("RENT_THING"),
        "things_reserve": stock(RESERVE_TYPE),
        "new_people": len(first_real),
        # A guest is somebody whose first real relation is a join.
        "new_guests": len(joiners & history.cycle),
        "new_creators": len(new_creators),
        "new_creators_organic": len(new_creators & history.cycle),
        "collections_created": count(K.COLLECTION_CREATED),
        "collections_deleted": count(K.COLLECTION_DELETED),
        "things_added": count(K.THING_ADDED),
        "things_removed": count(K.THING_REMOVED),
        "reservations": count(K.HOLD_REQUESTED, thing_type=RESERVE_TYPE),
        "requests_accepted": sum(count(K.HOLD_ACCEPTED, thing_type=t) for t in REQUEST_TYPES),
        "joins_invite": count(K.MEMBER_JOINED, source=Event.Source.INVITE),
        "joins_recommendation": count(K.MEMBER_JOINED, source=Event.Source.RECOMMENDATION),
        "joins_share": count(K.MEMBER_JOINED, source=Event.Source.SHARE),
        "joins_public": count(K.MEMBER_JOINED, source=Event.Source.PUBLIC),
        "joins_unknown": count(K.MEMBER_JOINED, source=""),
        "validations_requested": CreatorValidation.objects.filter(
            created__gte=start, created__lt=cutoff
        ).count(),
        "validations_approved": CreatorValidation.objects.filter(
            status=CreatorValidation.Status.APPROVED, resolved__gte=start, resolved__lt=cutoff
        ).count(),
        "active_creators": sum(1 for u in week_activity if u in history.creators),
        "active_guests": sum(1 for u in week_activity if u in history.guests),
        **history.stage_counts(activity),
        "cycle_median_days_to_owner": history.median_days_to_owner(),
        "owner_median_days_to_first_request": history.median_days_to_first_request(),
        "owners_gen0": len(history.seeded_owners),
        "owners_gen1": sum(1 for g in gens if g == 1),
        "owners_gen2plus": sum(1 for g in gens if g >= 2),
    }
    metrics["creators_seeded"] = metrics["creators"] - metrics["creators_organic"]
    for verb, key in zip(REQUEST_TYPES, ("gift", "sell", "lend", "rent"), strict=True):
        metrics[f"requests_{key}"] = count(K.HOLD_REQUESTED, thing_type=verb)
    metrics["requests"] = sum(metrics[f"requests_{k}"] for k in ("gift", "sell", "lend", "rent"))

    live_values = _live_only() if live else dict.fromkeys(LIVE_ONLY_KEYS)
    metrics.update(live_values)

    ordered = {key: metrics[key] for key in METRIC_KEYS}
    ordered["cohorts"] = cohorts_as_of(cutoff)
    return ordered


def cycle_as_of(cutoff):
    """The cycle as of ``cutoff`` in one pass: stages, medians and the table of generations.

    What the Monday email shows live; the same numbers per week are in the snapshots.
    """
    history = _History(cutoff)
    return {
        **history.stage_counts(_activity_dates(history.cycle, cutoff)),
        "median_days_to_owner": history.median_days_to_owner(),
        "median_days_to_first_request": history.median_days_to_first_request(),
        "generations": _generation_rows(history),
    }
