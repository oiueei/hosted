"""
Collection model for OIUEEI.
"""

import logging
import secrets
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models.language import Language
from core.utils import generate_id

logger = logging.getLogger(__name__)


def generate_share_token():
    """22-char URL-safe token for public share links. Bearer credential — must be unguessable."""
    return secrets.token_urlsafe(16)


class Collection(models.Model):
    """
    A collection of things (gifts, sales, orders) owned by a user.
    Can be shared with other users via invites.
    """

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"

    class Mode(models.TextChoices):
        PROPRIETARY = "PROPRIETARY", "Proprietary"
        COMMUNITY = "COMMUNITY", "Community"

    class Visibility(models.TextChoices):
        PUBLIC = "PUBLIC", "Public"
        PRIVATE = "PRIVATE", "Private"

    class DigestFrequency(models.TextChoices):
        NONE = "NONE", "None"
        WEEKLY = "WEEKLY", "Weekly"
        MONTHLY = "MONTHLY", "Monthly"

    code = models.CharField(max_length=6, primary_key=True, default=generate_id)
    owner = models.ForeignKey(
        "User",
        on_delete=models.CASCADE,
        to_field="code",
        db_column="owner",
        related_name="owned_collections",
    )
    created = models.DateTimeField(default=timezone.now)
    # headline: 256 stored for the O6 {lang: text} map, 64 visible per language.
    headline = models.CharField(max_length=256)
    # TextField like Thing.description (2000 visible per language, serializer-
    # enforced): a group's description is long-form Markdown and the column is
    # only a backstop.
    description = models.TextField(blank=True, default="")
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE)
    mode = models.CharField(max_length=12, choices=Mode.choices, default=Mode.PROPRIETARY)
    visibility = models.CharField(
        max_length=7, choices=Visibility.choices, default=Visibility.PRIVATE
    )
    # WEEKLY by default since the 2026-08 design round. It was NONE, which — with
    # `User.notify_news` also defaulting off — is why the digest reached almost
    # nobody: it needed an owner to find a setting inside an accordion *and* every
    # reader to have opted in.
    #
    # A default that sends email has to be visible to the person it sends on
    # behalf of, so the selector is now in the Create form too (it was Edit-only).
    # And it has to be escapable by the people who receive it, which is
    # `digest_muted` — one click, per group, from the footer of the digest itself.
    #
    # Existing collections keep whatever they have: an `AlterField` default does
    # not rewrite rows, and quietly starting to mail someone else's members on
    # their behalf is not ours to decide (contrast 0127, which subscribes existing
    # *recipients*, who can unsubscribe themselves).
    digest_frequency = models.CharField(
        max_length=7, choices=DigestFrequency.choices, default=DigestFrequency.WEEKLY
    )
    # The language this group's outbound email speaks. Blank = inherit the
    # deployment default (EMAIL_LANGUAGE); a member's own preference still wins
    # over it. See email_service.resolve_email_language.
    language = models.CharField(max_length=2, choices=Language.choices, blank=True, default="")
    # Whether members may suggest new guests (InvitationProposal). The owner
    # always decides on each one — this decides whether they are willing to be
    # asked at all. A group with a waiting list, a subscription or an admission
    # process may not want the question raised, and saying so once beats
    # declining the same suggestion over and over.
    #
    # Default ON: the proposal reaches nobody but the owner, who can decline it
    # in one click and turn this off just as easily, so the cost of being asked
    # is small and the cost of the feature never being discovered is the whole
    # point of building it.
    allow_member_proposals = models.BooleanField(default=True)
    is_onboarding = models.BooleanField(default=False)
    # Rental rules for LEND/RENT things in this collection (#7).
    # rental_durations: allowed rental lengths in DAYS (weeks are normalised to
    #   days, e.g. [1, 3, 7, 14]); the renter picks exactly one. Empty = no fixed
    #   durations (free date range, the legacy behaviour).
    # rental_weekdays: allowed weekdays for BOTH pickup (start) and return (end),
    #   Python weekday() numbering (0=Mon … 6=Sun). Empty = any day.
    rental_durations = models.JSONField(default=list, blank=True)
    rental_weekdays = models.JSONField(default=list, blank=True)
    # Holidays and one-off closures — ISO date strings ("2026-12-25"), sorted,
    # deduped, past ones dropped on save (the owner re-enters each year). No
    # pickup or return can land on one for a LEND/RENT booking; a RESERVE
    # booking can't span one at all. The serializer parses the owner's
    # comma-separated DD/MM/YYYY line into this. Empty = no closures.
    closed_dates = models.JSONField(default=list, blank=True)
    # RESERVE_THING collections only (``allowed_thing_types == ["RESERVE_THING"]``).
    # The longest a member may book the space for in one reservation, in days —
    # the renter picks any length from 1 to this. ``rental_weekdays`` above is
    # reused as "days reservations are allowed" (every day of the span must fall
    # on one). Inert on every other collection.
    reservation_max_days = models.PositiveSmallIntegerField(default=1)
    # How far ahead a member may book — the owner's call, since lead time is a
    # fact about the space (a workshop bench next week, an events hall six
    # months out). Default 90, matching the LEND/RENT horizon it replaces for
    # this type. Also caps how far the live-availability calendar looks.
    reservation_horizon_days = models.PositiveSmallIntegerField(default=90)
    # How deposits work in this group, in the owner's own words — "50 €, back
    # when the drill comes home in one piece". A bare number is the beginning of
    # an argument: the condition for getting it back is the actual rule, and that
    # rule belongs to the group rather than to each thing.
    #
    # No on/off switch beside it, on purpose: **writing the policy is the
    # switch**, the same shape as `digest_muted` below, where the presence of a
    # row means something and the absence costs no data. A group that wants no
    # deposits simply has no policy and no thing carrying one; a boolean beside
    # it would be a second door that can disagree with the first.
    #
    # 256/1024 like `description`, for the same reason: the visible limit is per
    # language and the column has to hold all three plus the JSON scaffolding.
    deposit_policy = models.CharField(max_length=1024, blank=True, default="")
    allowed_thing_types = models.JSONField(default=list, blank=True)
    tags = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "Owner-defined tag vocabulary for this collection: an ordered list of "
            "free-text labels. Things in the collection may be tagged with a subset. Max 12."
        ),
    )
    # The group's own website, if it has one — shown in the hero. A URLField, so
    # Django's URLValidator rejects anything but http(s)/ftp(s); the frontend
    # still runs it through `sanitizeUrl` before rendering the link.
    home_page = models.URLField(max_length=128, blank=True, default="")
    thumbnail = models.CharField(max_length=255, blank=True, default="")
    # Storage key of the owner's optional welcome & rules PDF. Emailed as a link
    # (never an attachment) to every member the first time they join, which is why
    # the link has to still work weeks later — see core.utils.doc_asset_url.
    welcome_doc = models.CharField(max_length=255, blank=True, default="")
    pause_message = models.CharField(max_length=256, blank=True, default="")
    share_token = models.CharField(max_length=22, blank=True, null=True, unique=True)
    # Mass-upload guards (see the COLLECTION_* thresholds in settings). The two
    # `*_alarm_sent` flags make each counter's alarm fire once per collection
    # rather than on every add past the line. `capacity_unblocked` is the
    # superuser's override: tick it in the admin and this collection may pass
    # BOTH ceilings — the unblock follows one manual review of the account, the
    # owner and the collection. All three are inert without thresholds.
    things_alarm_sent = models.BooleanField(default=False)
    invites_alarm_sent = models.BooleanField(default=False)
    capacity_unblocked = models.BooleanField(default=False)
    things = models.ManyToManyField(
        "Thing",
        blank=True,
        related_name="collections",
        db_table="collection_things",
    )
    invites = models.ManyToManyField(
        "User",
        blank=True,
        related_name="invited_to_collections",
        db_table="collection_invites",
    )
    # Members who have silenced THIS group's digest. Presence of a row means
    # "don't send"; the absence of one means subscribed — so the default costs no
    # data and a new member starts subscribed without anything being written.
    #
    # It is what makes `User.notify_news` defaulting to True honest rather than a
    # pre-ticked opt-in (DESIGN §6): the global switch is not the only way out,
    # so silencing one noisy group never costs you the booking and question
    # emails you actually want. `notify_news` remains the master switch — this
    # narrows it, it cannot re-enable anything.
    digest_muted = models.ManyToManyField(
        "User",
        blank=True,
        related_name="muted_digest_collections",
        db_table="collection_digest_muted",
    )
    # COMMUNITY-only admin tier, promoted from the collection's own `invites` —
    # never a separate door in. A co-owner gets owner-level powers (edit,
    # invite/revoke, broadcast, share link, stats/export) but is deliberately
    # NOT a CASCADE root: deleting a co-owner's account never takes the
    # collection with it, only the founding `owner` does. See `is_curator`.
    co_owners = models.ManyToManyField(
        "User",
        blank=True,
        related_name="co_owned_collections",
        db_table="collection_co_owners",
    )

    class Meta:
        app_label = "core"
        db_table = "collections"

    def __str__(self):
        return f"{self.code}: {self.headline}"

    def add_thing(self, thing_code):
        """Test-only fixture helper: link a thing via the M2M.

        Skips the views' permission/allowed-type checks and Event logging,
        and an unknown code is a silent no-op. Production code must go
        through the views instead of calling this.
        """
        from core.models import Thing

        try:
            thing = Thing.objects.get(code=thing_code)
            self.things.add(thing)
        except Thing.DoesNotExist:
            pass

    def remove_thing(self, thing_code):
        """Test-only fixture helper: unlink a thing via the M2M.

        Same caveats as add_thing — no permission checks, no Event logging,
        silent no-op on unknown codes. Not for production code.
        """
        from core.models import Thing

        try:
            thing = Thing.objects.get(code=thing_code)
            self.things.remove(thing)
        except Thing.DoesNotExist:
            pass

    def add_invite(self, user_code):
        """Test-only fixture helper: add a user to invites via the M2M.

        Skips the views' owner check and the invitation email/RSVP flow,
        and an unknown code is a silent no-op. Production code must go
        through CollectionInviteView instead of calling this.
        """
        from core.models import User

        try:
            user = User.objects.get(code=user_code)
            self.invites.add(user)
        except User.DoesNotExist:
            pass

    def remove_invite(self, user_code):
        """Test-only fixture helper: remove a user from invites via the M2M.

        Same caveats as add_invite — no owner check, no notifications,
        silent no-op on unknown codes. Not for production code.
        """
        from core.models import User

        try:
            user = User.objects.get(code=user_code)
            self.invites.remove(user)
        except User.DoesNotExist:
            pass

    @property
    def is_paused(self):
        return bool(self.pause_message)

    def is_owner(self, user_code):
        """Check if the given user is the owner."""
        return self.owner_id == user_code

    def is_invited(self, user_code):
        """Check if the given user is invited."""
        return self.invites.filter(code=user_code).exists()

    def is_curator(self, user_code):
        """Owner or co-owner — the group's admin tier.

        The single primitive every co-owner permission gate builds on, the way
        `is_owner` already was for owner-only ones. A co-owner is always also
        in `invites` (promotion, not a separate door), so this is strictly
        wider than `is_owner`, never wider than `is_invited`.

        Checks `co_owners` via `.all()` and Python iteration rather than
        `.filter(...).exists()`, deliberately: `co_owners` is prefetched
        alongside `invites` for any signed-in viewer (`_optimise_collection_
        queryset`), and a `.filter()` call would bypass that cache and reopen
        the N+1 the prefetch exists to close — the same reasoning behind
        `get_is_member`'s `any(u.code == ... for u in obj.invites.all())`.

        Does **not** check `is_community()`, and nothing about co-curators does
        any more: a curator has the founder's reach in either mode (2026-09,
        co-curators in PROPRIETARY), and only deleting the collection stays
        `is_owner`. An existing co-owner's status is sticky across a later mode
        switch, the same way `owner` itself is.
        """
        return self.is_owner(user_code) or any(u.code == user_code for u in self.co_owners.all())

    def is_community(self):
        """Check if this is a community collection."""
        return self.mode == self.Mode.COMMUNITY

    def owner_member_rows(self, members=None):
        """Every member as **their owner** sees them, demographics gated by mode.

        The one definition of a privacy rule that used to be written twice —
        once in `CollectionSerializer.get_invites`, once in
        `export_service._collection_members` — as two near-identical loops that
        agreed only because somebody kept them agreeing. `age_range` and
        `postal_code` are optional answers a member gave; in a COMMUNITY group
        their owner sees them (it is what the demographics breakdown is for), and
        in every other mode nobody but the member does. An export must not become
        the back door to what the API withholds, and the next mode added must not
        have to be remembered in two files.

        It lives on the model rather than in either caller because the gate is
        `self.mode` — a fact about the group, not about JSON. It builds a row and
        nothing else: **who may ask is the caller's job** (`_requester_is_owner`
        in the serializer, `require_collection_curator` on the export view), and
        calling this does not make anyone a curator.

        `members` defaults to the M2M, so a caller with a prefetched or ordered
        queryset passes it in rather than triggering a second one.
        """
        community = self.is_community()
        rows = []
        for member in self.invites.all() if members is None else members:
            row = {"code": member.code, "name": member.name, "email": member.email}
            if community:
                row["age_range"] = member.age_range
                row["postal_code"] = member.postal_code
            rows.append(row)
        return rows

    def is_public(self):
        """Check if this collection is publicly readable (anonymous-friendly)."""
        return self.visibility == self.Visibility.PUBLIC

    def has_rental_rules(self):
        """True if this collection constrains LEND/RENT booking dates (#7)."""
        return bool(self.rental_durations) or bool(self.rental_weekdays) or bool(self.closed_dates)

    def closed_date_set(self):
        """``closed_dates`` (ISO strings) as a set of ``date`` objects. A bad
        string is skipped rather than raising — the serializer is what keeps the
        column clean, this stays defensive."""
        from datetime import date as _date

        out = set()
        for raw in self.closed_dates or []:
            try:
                out.add(_date.fromisoformat(raw))
            except (TypeError, ValueError):
                continue
        return out

    def is_reservations_collection(self):
        """True if this is a RESERVE_THING collection.

        Derived from the allowlist rather than a marker field: a collection
        holds RESERVE things **iff** ``allowed_thing_types == ["RESERVE_THING"]``.
        The serializer enforces that a RESERVE entry stands alone and forces
        PROPRIETARY mode, so "reservations collection" and "solo-RESERVE
        PROPRIETARY collection" are the same thing.
        """
        return list(self.allowed_thing_types or []) == ["RESERVE_THING"]

    def reservation_violation(self, start_date, duration_days, today=None):
        """Return an error string if a RESERVE booking breaks this collection's
        reservation rules, else ``None``. Mirrors ``rental_violation``'s shape.

        ``duration_days`` is how many days the member wants the space, 1 to
        ``reservation_max_days``. The booking occupies ``[start, start + N)`` —
        every one of those days must fall on an allowed weekday
        (``rental_weekdays``, reused; empty = any day), because the space is only
        open on those days. A reservation that would span a closed day is
        refused rather than silently shortened.

        The **pickup day** must land within ``reservation_horizon_days`` of
        ``today`` (default ``timezone.localdate()``) — the owner's "how far
        ahead" limit, and the single backstop the request view relies on. It is
        the pickup day, not the return day: that is what ``RequestThingPage``'s
        date picker caps (``maxDate = today + reservation_horizon_days``) and
        what ``Thing.availability_window`` walks, so judging the exclusive
        ``end_date`` here rejected the last day of the picker's own range
        (horizon 7 ⇒ day 7 selectable, ``end_date`` day 8, refused).
        """
        if duration_days < 1:
            return "A reservation is at least one day."
        if duration_days > self.reservation_max_days:
            return (
                f"This space can be reserved for at most "
                f"{self.reservation_max_days} day(s) at a time."
            )
        today = today or timezone.localdate()
        if start_date > today + timedelta(days=self.reservation_horizon_days):
            return (
                f"This space can only be booked up to {self.reservation_horizon_days} days ahead."
            )
        weekdays = self.rental_weekdays or []
        closed = self.closed_date_set()
        for offset in range(duration_days):
            day = start_date + timedelta(days=offset)
            if weekdays and day.weekday() not in weekdays:
                return "Those dates include a day this space isn't open for reservations."
            if day in closed:
                return "Those dates include a day this space is closed."
        return None

    # ---- Mass-upload capacity guards -------------------------------------
    # Two INDEPENDENT counters per collection — things and invitees — because a
    # collection can be abused in either direction (dumping stock, or harvesting
    # a mailing list) and one crossing says nothing about the other. Each has its
    # own thresholds and its own fire-once alarm flag; a single
    # `capacity_unblocked` lifts both ceilings, since the unblock follows one
    # manual review of the account, the owner and the collection.
    #
    # Both counters are inert unless the deployment sets thresholds (see
    # settings) — the standalone default is off.
    _COUNTERS = {
        "things": {
            "alarm_setting": "COLLECTION_THINGS_ALARM",
            "block_setting": "COLLECTION_THINGS_BLOCK",
            "flag": "things_alarm_sent",
            "noun": "things",
        },
        "invites": {
            "alarm_setting": "COLLECTION_INVITES_ALARM",
            "block_setting": "COLLECTION_INVITES_BLOCK",
            "flag": "invites_alarm_sent",
            "noun": "members",
        },
    }

    def _capacity_count(self, counter):
        return (self.things if counter == "things" else self.invites).count()

    def capacity_ceiling(self, counter="things"):
        """The hard ceiling in force for ``counter``, or ``0`` when there is none.

        ``0`` means either the deployment set no ceiling (the standalone default)
        or a superuser lifted it for this collection. Callers use it as a cheap
        gate: with no ceiling to judge them, working out how many rows a request
        would actually add is wasted effort, so the guard costs not one query.
        """
        if self.capacity_unblocked:
            return 0
        return max(getattr(settings, self._COUNTERS[counter]["block_setting"], 0) or 0, 0)

    def capacity_violation(self, counter="things", adding=1):
        """Return an error string if adding ``adding`` rows to ``counter`` would
        cross this deployment's hard ceiling, else ``None``.

        Mirrors ``rental_violation``'s shape: a string is a refusal the caller
        turns into a 400. A ceiling of 0 (or unset) means no ceiling, which is
        the standalone default. A superuser who has ticked
        ``capacity_unblocked`` lifts it for this collection.

        Checked BEFORE the add and against the WHOLE batch, so a bulk import or
        bulk invite cannot step over the line 100 rows at a time. ``adding`` is
        the number of rows that would genuinely *land* — callers must not count
        rows the request will drop anyway (an invitee who is already a member is
        inside the count the ceiling measures, so counting them again would
        refuse a batch that adds nobody). The message names the ceiling: once it
        actually bites, hiding the number would just leave the owner with an
        unexplained refusal (the thresholds are unpublished, not secret from the
        person hitting one).
        """
        spec = self._COUNTERS[counter]
        ceiling = self.capacity_ceiling(counter)
        if ceiling <= 0:
            return None
        # Adding nothing can never *cross* a line. Without this, a batch whose
        # rows all turn out to be no-ops (already members, or every row invalid)
        # would still be refused on a collection that is already over a ceiling
        # lowered after the fact — a refusal the request could do nothing about.
        if adding <= 0:
            return None
        if self._capacity_count(counter) + adding > ceiling:
            return (
                f"This collection has reached its limit of {ceiling} "
                f"{spec['noun']}. Contact the site administrator if you need "
                "more room."
            )
        return None

    def note_capacity(self, counter="things"):
        """Email the superusers once if ``counter`` has crossed its alarm line.

        A **silent** tripwire: the owner is told nothing. A legitimate bulk
        import must not be interrupted, and someone probing the endpoint must not
        be told where the line sits — only the hard ceiling is user-visible, and
        only once it bites. Called AFTER a successful add, so the count is real.

        The per-counter flag makes it fire once per collection. Failures are
        swallowed — an alarm that cannot send must never 500 an upload whose rows
        are already committed; the ceiling is the guard that actually stops
        abuse, the alarm is only the early warning.
        """
        spec = self._COUNTERS[counter]
        threshold = getattr(settings, spec["alarm_setting"], 0) or 0
        if threshold <= 0 or getattr(self, spec["flag"]):
            return
        count = self._capacity_count(counter)
        if count < threshold:
            return
        # Claim the alarm with a conditional UPDATE: the `flag=False` in the
        # WHERE is what makes "fire once" hold under concurrency. Two requests
        # crossing the line together both read False above, but only one gets a
        # matched row back — the loser returns without sending, so the operator
        # gets one email rather than one per racing request. Claiming BEFORE the
        # send also means a send that raises can't leave the alarm armed to
        # re-fire on every subsequent add.
        claimed = Collection.objects.filter(code=self.code, **{spec["flag"]: False}).update(
            **{spec["flag"]: True}
        )
        setattr(self, spec["flag"], True)
        if not claimed:
            return
        try:
            from core.services.email_service import send_collection_capacity_alarm

            send_collection_capacity_alarm(self, counter, count, threshold)
        except Exception:  # pragma: no cover - defensive
            logger.exception("Capacity alarm email failed for collection %s", self.code)

    def rental_violation(self, start_date, end_date):
        """Return an error string if a LEND/RENT booking of ``[start, end]`` breaks
        this collection's rental rules, else ``None``.

        ``start`` is the pickup day and ``end`` the return day, so an allowed
        length of N days means ``end`` is ``start + N`` days — a one-week rental
        picked up on a Wednesday is returned the NEXT Wednesday. (With an
        inclusive span, the return of every 7/14/21-day rental landed on the day
        BEFORE the pickup weekday, so a single allowed weekday could never be
        satisfied.) Weekdays use Python's ``weekday()`` (0=Mon…6=Sun) and gate
        BOTH the pickup (start) and the return (end).
        """
        durations = self.rental_durations or []
        if durations:
            span_days = (end_date - start_date).days
            if span_days not in durations:
                allowed = ", ".join(str(d) for d in sorted(durations))
                return f"This collection only allows rentals of {allowed} day(s)."
        weekdays = self.rental_weekdays or []
        if weekdays:
            if start_date.weekday() not in weekdays:
                return "The pickup day isn't available for this collection."
            if end_date.weekday() not in weekdays:
                return "The return day isn't available for this collection."
        # Holidays / closures: only the handoff days matter for a loan or a
        # rental — the item is already out in between, so an interior closure
        # stops nothing.
        closed = self.closed_date_set()
        if start_date in closed:
            return "The pickup day is a closure day for this collection."
        if end_date in closed:
            return "The return day is a closure day for this collection."
        return None

    def can_add_thing(self, user_code):
        """Check if the given user can add things to this collection.

        Any curator (owner or co-curator) can always add — a PROPRIETARY
        collection's catalogue is run by its curators collectively (2026-09).
        Beyond that, an invited member can add in COMMUNITY mode.
        """
        if self.is_curator(user_code):
            return True
        return self.is_community() and self.is_invited(user_code)

    def can_view(self, user_code):
        """Check if the given user can view this collection.

        Owner always; INACTIVE collections only the owner; PUBLIC collections
        anyone — including anonymous visitors (``user_code=None``); otherwise an
        invited member only.
        """
        if self.is_owner(user_code):
            return True
        if self.status == self.Status.INACTIVE:
            return False
        if self.is_public():
            return True
        return self.is_invited(user_code)
