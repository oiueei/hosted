"""Weekly first-party stats summary for OIUEEI.

Computes product metrics from three sources — current state (domain tables),
accumulated history (the Event log), and retention (DailyActivity) — and prints
them to stdout, emailing them to the operator once a week — on Mondays by
default, or the weekday set by ``STATS_EMAIL_WEEKDAY`` (0=Monday … 6=Sunday;
weekday-gated like ``send_digests`` because Heroku Scheduler has no weekly
frequency; pass ``--email`` to force a send for a manual run).

Demo data never mixes into the real numbers: the five seed users
(Lala/Lele/Lili/Lolo/Lulu), ``is_onboarding`` collections, and pop-in users who
only ever landed in onboarding collections are split off into a separate
"Demo funnel" section. Everything stays first-party and in our DB (DESIGN §9).

Run daily via Heroku Scheduler (it self-gates to the configured weekday):
    ... && python manage.py stats_summary
Manual, any day:
    heroku run --app <app> "python manage.py stats_summary --email"
"""

import os
from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db.models import Count, Min, Q
from django.utils import timezone

from core.management.commands.device_share import _cell, weekly_device_share
from core.management.commands.seed_data.common import USERS as _SEED_USERS
from core.models import FAQ, BookingPeriod, Collection, DailyActivity, Event, Thing, User
from hosted.emails import send_stats_summary_email
from hosted.metrics import WEEK_TZ, cohorts_as_of, cycle_as_of, real_events, retired_orphans
from hosted.models import AccessInterest, CreatorValidation, Milestone, WeeklySnapshot

SEED_USER_CODES = frozenset(u["code"] for u in _SEED_USERS)


def _pct(part, whole):
    return f"{100 * part / whole:.0f}%" if whole else "—"


def _avg(total, count, unit=""):
    return f"{total / count:.1f}{unit}" if count else "—"


class Command(BaseCommand):
    help = (
        "Print (and, on the STATS_EMAIL_WEEKDAY — default Monday — email) "
        "the first-party product stats summary."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            action="store_true",
            help="Send the email regardless of weekday (for a manual run).",
        )

    def handle(self, *args, **options):
        sections = build_report()
        self.stdout.write(render_text(sections))

        today = timezone.localdate()
        try:
            # 0=Monday … 6=Sunday. Heroku Scheduler has no weekly frequency, so the
            # daily run gates itself; the deployment picks the day via config var.
            email_day = int(os.environ.get("STATS_EMAIL_WEEKDAY", "0"))
        except ValueError:
            email_day = 0
        if not (options["email"] or today.weekday() == email_day):
            self.stdout.write(
                "Not the stats-email weekday "
                f"(STATS_EMAIL_WEEKDAY={email_day}, 0=Monday) — "
                "email skipped (use --email to force a send)."
            )
            return

        recipient = os.environ.get("STATS_EMAIL")
        if not recipient:
            self.stdout.write("STATS_EMAIL not set — email skipped.")
            return

        send_stats_summary_email(recipient, f"OIUEEI stats — {today.isoformat()}", sections)
        self.stdout.write(self.style.SUCCESS(f"Stats email sent to {recipient}"))


# --- Demo/real partition --------------------------------------------------------


def _partition():
    """Split the population into real vs demo.

    Returns a dict of code sets:
    - ``creators``  real users owning ≥1 non-onboarding collection
    - ``guests``    real users invited to ≥1 non-onboarding collection (not creators)
    - ``real``      creators ∪ guests
    - ``demo``      everyone else (seed users + onboarding-only pop-in users)
    - ``demo_collections`` onboarding collection codes
    """
    demo_collections = set(
        Collection.objects.filter(is_onboarding=True).values_list("code", flat=True)
    )
    creators = (
        set(Collection.objects.filter(is_onboarding=False).values_list("owner_id", flat=True))
        - SEED_USER_CODES
    )
    invited_real = (
        set(
            User.objects.filter(invited_to_collections__is_onboarding=False).values_list(
                "code", flat=True
            )
        )
        - SEED_USER_CODES
    )
    guests = invited_real - creators
    real = creators | guests
    demo = set(User.objects.values_list("code", flat=True)) - real
    return {
        "creators": creators,
        "guests": guests,
        "real": real,
        "demo": demo,
        "demo_collections": demo_collections,
    }


# --- Report ---------------------------------------------------------------------


def build_report():
    """Compute every section. Returns a list of ``{title, rows, note?}`` dicts."""
    now = timezone.now()
    today = timezone.localdate()
    p = _partition()
    real, creators, guests = p["real"], p["creators"], p["guests"]
    demo, demo_collections = p["demo"], p["demo_collections"]
    real_list = list(real)
    # What the series counts, minus the visitors of the open door who left only a
    # `USER_JOINED` (the series does not enter them in the population; these blocks never
    # counted them either), so the three blocks that read the log agree with it.
    events = [
        e
        for e in real_events(now)
        if e.actor_code not in demo and e.collection_code not in demo_collections
    ]

    sections = [
        _users_section(real, creators, guests),
        _collections_section(creators, guests),
        _things_section(real_list),
        _holds_section(real_list, guests),
        _history_section(events, now),
        _joins_by_door_section(events, now),
        _conversion_section(events),
        _retention_section(real, creators, guests, today),
        _evolution_section(),
        _cycle_section(now),
        _phases_section(),
        _devices_section(),
        _interest_section(),
        _demo_section(demo, demo_collections),
    ]
    return sections


def _users_section(real, creators, guests):
    return {
        "title": "Users (real)",
        "rows": [
            ("Total real users", len(real)),
            ("Creators (own ≥1 real collection)", len(creators)),
            ("Guests (invited only)", len(guests)),
        ],
    }


def _collections_section(creators, guests):
    real = Collection.objects.filter(is_onboarding=False)
    total = real.count()
    active = real.filter(status=Collection.Status.ACTIVE).count()
    community = real.filter(mode=Collection.Mode.COMMUNITY).count()
    public = real.filter(visibility=Collection.Visibility.PUBLIC).count()
    invites = real.aggregate(n=Count("invites"))["n"] or 0
    # Distinct guests per creator: a guest under two of the same creator's
    # collections counts once for that creator. Anonymous visitors aren't tracked.
    per_creator = real.values("owner_id").annotate(g=Count("invites", distinct=True))
    guests_per_creator = sum(r["g"] for r in per_creator)
    n_creators = len(creators)
    return {
        "title": "Collections (real)",
        "rows": [
            ("Total", total),
            ("Active (status ACTIVE)", active),
            ("COMMUNITY / PROPRIETARY", f"{community} / {total - community}"),
            ("PUBLIC / PRIVATE", f"{public} / {total - public}"),
            ("Avg collections per creator", _avg(total, n_creators)),
            ("Avg guests per collection", _avg(invites, total)),
            ("Avg guests brought per creator", _avg(guests_per_creator, n_creators)),
        ],
    }


def _things_section(real_list):
    things = Thing.objects.filter(owner_id__in=real_list)
    total = things.count()
    active = things.filter(status=Thing.Status.ACTIVE).count()
    by_type = dict(things.values_list("type").annotate(n=Count("code")).values_list("type", "n"))
    faqs = FAQ.objects.filter(thing__owner_id__in=real_list).count()
    holds = BookingPeriod.objects.filter(thing_code__owner_id__in=real_list).count()
    type_rows = [(t, f"{c} ({_pct(c, total)})") for t, c in sorted(by_type.items())]

    # Things per (real) collection, by M2M membership — added vs currently active.
    real_collections = Collection.objects.filter(is_onboarding=False)
    n_collections = real_collections.count()
    agg = real_collections.aggregate(
        members=Count("things"),
        active=Count("things", filter=Q(things__status=Thing.Status.ACTIVE)),
    )
    per_coll = (
        f"{_avg(agg['members'] or 0, n_collections)} / {_avg(agg['active'] or 0, n_collections)}"
    )
    return {
        "title": "Things (real)",
        "rows": [
            ("Total", total),
            ("Available (status ACTIVE)", active),
            *type_rows,
            ("Avg things per collection (added / active)", per_coll),
            ("Avg FAQs per thing", _avg(faqs, total)),
            ("Avg holds per thing", _avg(holds, total)),
        ],
    }


def _holds_section(real_list, guests):
    bookings = BookingPeriod.objects.filter(thing_code__owner_id__in=real_list)
    total = bookings.count()
    accepted = bookings.filter(status=BookingPeriod.Status.ACCEPTED).count()

    # Time-to-first-hold: for each thing that got a hold, first hold minus thing
    # creation, averaged (in days).
    first_holds = bookings.values("thing_code_id").annotate(
        first=Min("created"), created=Min("thing_code__created")
    )
    deltas = [
        (r["first"] - r["created"]).total_seconds()
        for r in first_holds
        if r["first"] and r["created"]
    ]
    ttfh = _avg(sum(deltas) / 86400, len(deltas), unit="d") if deltas else "—"

    booked_guests = set(
        bookings.filter(requester_code__in=guests).values_list("requester_code", flat=True)
    )
    never_booked = len(guests - booked_guests)

    return {
        "title": "Holds (real, current bookings)",
        "rows": [
            ("Total hold requests", total),
            ("Success rate (accepted / requested)", _pct(accepted, total)),
            ("Avg time from thing added → first hold", ttfh),
            ("Guests who never booked", f"{never_booked} ({_pct(never_booked, len(guests))})"),
        ],
    }


def _history_section(events, now):
    d7, d30 = now - timedelta(days=7), now - timedelta(days=30)

    def n(kind, since=None):
        return sum(1 for e in events if e.kind == kind and (since is None or e.created >= since))

    K = Event.Kind
    joined = f"{n(K.USER_JOINED, d7)} / {n(K.USER_JOINED, d30)} / {n(K.USER_JOINED)}"
    requested, accepted = n(K.HOLD_REQUESTED), n(K.HOLD_ACCEPTED)
    # A thing that went with its collection leaving no removal counts as removed, as the
    # series' stocks take it.
    added = n(K.THING_ADDED)
    removed = n(K.THING_REMOVED) + len(retired_orphans(events))
    # The same add/remove lifecycle averaged over the collections created in the same
    # period: the counts above are the log's whole history, so dividing by today's
    # collections (which leave out the deleted ones and any older than the log) would
    # measure two different populations.
    n_created = n(K.COLLECTION_CREATED)
    return {
        "title": "History (accumulated, from Event log)",
        "rows": [
            ("Users joined (7d / 30d / all)", joined),
            (
                "Collections created / deleted",
                f"{n(K.COLLECTION_CREATED)} / {n(K.COLLECTION_DELETED)}",
            ),
            ("Things added / removed", f"{added} / {removed}"),
            (
                "Avg added / removed per collection created",
                f"{_avg(added, n_created)} / {_avg(removed, n_created)}",
            ),
            ("Members joined / left", f"{n(K.MEMBER_JOINED)} / {n(K.MEMBER_LEFT)}"),
            ("FAQs asked", n(K.FAQ_ASKED)),
            ("Holds requested / accepted", f"{requested} / {accepted}"),
            ("Hold success rate (all time)", _pct(accepted, requested)),
        ],
        "note": (
            "Created minus deleted need not equal today's collections: "
            "some collections are older than the log."
        ),
    }


def _joins_by_door_section(events, now):
    """Which of the six doors actually brings members in.

    OIUEEI has six ways to acquire one — the owner's own invite, a bulk CSV
    invite, a share link/QR, a public collection's login-to-act, a member's
    recommendation, and the /popin demo — and until `Event.source` existed they
    were all counted as the same join. That made "is any of these earning its
    place?" unanswerable from the data, which is exactly the question worth
    asking of a product that means to stay small.

    Rows written before the field are counted as `unknown` rather than folded
    into a bucket they might not belong to.
    """
    d30 = now - timedelta(days=30)
    labels = {
        Event.Source.INVITE: "Owner invite",
        Event.Source.RECOMMENDATION: "Member recommendation",
        Event.Source.SHARE: "Share link / QR",
        Event.Source.PUBLIC: "Public collection (login to act)",
        Event.Source.ONBOARDING: "Pop-in / onboarding",
    }

    joins = [e for e in events if e.kind == Event.Kind.MEMBER_JOINED]

    def counts(rows):
        found = {}
        for e in rows:
            found[e.source] = found.get(e.source, 0) + 1
        return found

    all_time, recent = counts(joins), counts(e for e in joins if e.created >= d30)
    rows = [
        (label, f"{all_time.get(source, 0)} ({recent.get(source, 0)} in 30d)")
        for source, label in labels.items()
    ]
    unknown = all_time.get("", 0)
    if unknown:
        rows.append(("Unrecorded (joined before this was measured)", unknown))
    return {
        "title": "Members joined, by door",
        "rows": rows,
        "note": "A door with no joins over several months is a candidate for removal.",
    }


def _conversion_section(events):
    """Guest→creator: an actor with a MEMBER_JOINED that predates their first
    COLLECTION_CREATED — i.e. someone who arrived as a guest and later started
    their own collection. Derived, never stored (per the spec)."""

    def first(kind):
        found = {}
        for e in events:  # oldest first
            if e.kind == kind:
                found.setdefault(e.actor_code, e.created)
        return found

    joined, created = first(Event.Kind.MEMBER_JOINED), first(Event.Kind.COLLECTION_CREATED)
    deltas = [
        (created[a] - joined[a]).total_seconds()
        for a in joined
        if a in created and created[a] > joined[a]
    ]
    avg_days = _avg(sum(deltas) / 86400, len(deltas), unit="d") if deltas else "—"
    return {
        "title": "Conversion",
        "rows": [
            ("Guest → creator conversions", len(deltas)),
            ("Avg time guest → first collection", avg_days),
        ],
    }


def _retention_section(real, creators, guests, today):
    cut7, cut30 = today - timedelta(days=7), today - timedelta(days=30)
    active7 = set(DailyActivity.objects.filter(date__gte=cut7).values_list("user_id", flat=True))
    active30 = set(DailyActivity.objects.filter(date__gte=cut30).values_list("user_id", flat=True))

    day_counts = dict(
        DailyActivity.objects.values("user_id")
        .annotate(n=Count("date", distinct=True))
        .values_list("user_id", "n")
    )
    returners = {c for c, days in day_counts.items() if days >= 2}
    one_visit = {c for c, days in day_counts.items() if days == 1}

    def split(codes):
        return f"{len(codes & creators)} creators / {len(codes & guests)} guests"

    def returns_for(role):
        role_returners = returners & role
        avg_days = _avg(sum(day_counts[c] for c in role_returners), len(role_returners))
        return f"{len(role_returners)} returned (avg {avg_days} active days)"

    return {
        "title": "Retention (from DailyActivity)",
        "rows": [
            ("WAU — active last 7d", f"{len(active7 & real)} ({split(active7 & real)})"),
            ("MAU — active last 30d", f"{len(active30 & real)} ({split(active30 & real)})"),
            ("Creator returns (active ≥2 days)", returns_for(creators)),
            ("Guest returns (active ≥2 days)", returns_for(guests)),
            ("Guests who never came back after 1st visit", len(one_visit & guests)),
        ],
    }


# --- The weekly series ------------------------------------------------------------

_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
BACKFILL_HINT = "record_weekly_snapshot --backfill-from 2026-09-07"
PHASE_LABELS = {"PRE": "Before the first milestone", **dict(Milestone.Phase.choices)}
# A percentage over fewer people than this says more than the sample can bear.
MIN_FOR_PERCENT = 10


def _fraction(part, whole):
    """``n/N``, with the percentage only once N is big enough to mean something."""
    if whole >= MIN_FOR_PERCENT:
        return f"{part}/{whole} ({_pct(part, whole)})"
    return f"{part}/{whole}"


def _delta(now, before):
    if before is None:
        return ""
    diff = now - before
    return f" ({diff:+d})" if diff else " (±0)"


def _evolution_section():
    """The last twelve weeks, newest first, read from the stored snapshots."""
    snapshots = list(WeeklySnapshot.objects.order_by("-week_start")[:13])
    if not snapshots:
        return {
            "title": "Weekly evolution (last 12 weeks)",
            "rows": [("No weeks recorded yet", f"run `{BACKFILL_HINT}`")],
        }
    by_week = {s.week_start: s.metrics for s in snapshots}
    rows = []
    for snap in snapshots[:12]:
        m = snap.metrics
        before = by_week.get(snap.week_start - timedelta(days=7))

        def moved(key, m=m, before=before):
            return _delta(m[key], before[key] if before else None)

        label = (
            f"W{snap.week_start.isocalendar().week} · "
            f"{snap.week_start.day} {_MONTHS[snap.week_start.month - 1]}"
        )
        for milestone in Milestone.labels_of_week(snap.week_start):
            label += f" ◆ {milestone}"
        rows.append(
            (
                label,
                f"creators {m['creators']}{moved('creators')} · "
                f"guests {m['guests']}{moved('guests')} · "
                f"collections {m['collections']} · "
                f"things {m['things']}{moved('things')} · "
                f"requests {m['requests']} ({m['requests_accepted']} ok) · "
                f"reservations {m['reservations']}",
            )
        )
    return {"title": "Weekly evolution (last 12 weeks)", "rows": rows}


def _cohort_row(week, cohort):
    n = cohort["size"]
    windows = " · ".join(
        f"{w}w {cohort['owner_within'][str(w)]}/{n}"
        if str(w) in cohort["owner_within"]
        else f"{w}w —"
        for w in (1, 2, 4, 8)
    )
    return f"W{date.fromisoformat(week).isocalendar().week} (n={n})", windows


def _cycle_section(now):
    """Guest → owner, live: the funnel, the two medians, K per generation and the cohorts."""
    cycle = cycle_as_of(now)
    entered = cycle["cycle_entered"]
    asked = CreatorValidation.objects.count()
    approved = CreatorValidation.objects.filter(status=CreatorValidation.Status.APPROVED).count()

    def median(value):
        return "—" if value is None else f"{value:g} days"

    rows = [
        ("Entered as a guest", entered),
        ("  came back (a second day)", _fraction(cycle["cycle_returned"], entered)),
        ("  asked for something", _fraction(cycle["cycle_requested"], entered)),
        ("  became an owner", _fraction(cycle["cycle_owner"], entered)),
        ("  added their first thing", _fraction(cycle["cycle_first_thing"], entered)),
        ("  brought somebody in", _fraction(cycle["cycle_closed"], entered)),
        ("Median guest → owner", median(cycle["median_days_to_owner"])),
        ("Median owner → first request received", median(cycle["median_days_to_first_request"])),
        ("Creator validation (asked / approved)", f"{asked} / {approved}"),
    ]
    for row in cycle["generations"]:
        owners, brought = row["owners"], row["brought"]
        rows.append(
            (
                f"K, generation {row['generation']} → {row['generation'] + 1}",
                f"{row['next_owners']}/{owners} = {row['k']:.2f} · "
                f"{brought / owners:.1f} guests brought per owner ({brought}/{owners}) · "
                f"{_fraction(row['converted'], brought)} became owners",
            )
        )
    local = now.astimezone(WEEK_TZ).date()
    since = local - timedelta(days=local.weekday()) - timedelta(weeks=7)
    for week, cohort in cohorts_as_of(now).items():
        if date.fromisoformat(week) >= since:
            rows.append(_cohort_row(week, cohort))
    return {
        "title": "Organic cycle: guest → owner",
        "rows": rows,
        "note": (
            "K above 1 means every owner brings at least one new owner. Creator validation is "
            "optional (giving and selling are open) and its date is the day the row was created "
            "from the form, not the day the person asked."
        ),
    }


def _phases_section():
    """What a typical week looks like in each phase, from the snapshots and their cohorts."""
    snapshots = list(WeeklySnapshot.objects.order_by("week_start"))
    if not snapshots:
        return {
            "title": "By phase",
            "rows": [("No weeks recorded yet", f"run `{BACKFILL_HINT}`")],
        }
    weeks_by_phase = {}
    for snap in snapshots:
        weeks_by_phase.setdefault(Milestone.phase_of_week(snap.week_start), []).append(snap)

    cohorts = snapshots[-1].metrics.get("cohorts", {})
    entered, became = {}, {}
    for week, cohort in cohorts.items():
        phase = Milestone.phase_of_week(date.fromisoformat(week))
        entered[phase] = entered.get(phase, 0) + cohort["size"]
        became[phase] = became.get(phase, 0) + cohort.get("owners", 0)

    rows = []
    for phase, snaps in weeks_by_phase.items():

        def mean(key, snaps=snaps):
            return f"{sum(s.metrics[key] for s in snaps) / len(snaps):.1f}"

        rows.append(
            (
                f"{PHASE_LABELS.get(phase, phase)} ({len(snaps)} weeks)",
                f"per week: new creators {mean('new_creators')} "
                f"({mean('new_creators_organic')} organic) · "
                f"new guests {mean('new_guests')} · requests {mean('requests')} · "
                f"reservations {mean('reservations')} · "
                f"guest → owner {_fraction(became.get(phase, 0), entered.get(phase, 0))}",
            )
        )
    return {"title": "By phase", "rows": rows}


def _devices_section():
    """How much of the last closed ISO week came from a phone — numbers only.

    Reads ``DeviceDay`` through core's own ``weekly_device_share`` (the same sums and
    percentages as ``manage.py device_share``). The question it answers is where
    collections and things get saved, so form saves sit next to the people.
    """
    week = weekly_device_share(2)[0]  # [last closed week, the one running]
    return {
        "title": "Devices (last week)",
        "rows": [
            ("People (mobile / other)", _cell(week, "people")),
            ("Form saves (mobile / other)", _cell(week, "form_saves")),
        ],
        "note": f"ISO week {week['week']}; a tablet counts as other",
    }


def _interest_section():
    """What the request-access page was read for, and pressed for, last week.

    Per need, how many times its section was opened (``SEEN``) and how many times its
    "Request access" button was pressed (``ASKED``), and the share who asked. The two
    counters hold numbers only (``AccessInterest``); the week is the last closed ISO
    week, the one the devices section reads. No arrivals gives a dash, not a division.
    """
    today = timezone.localdate()
    this_monday = today - timedelta(days=today.weekday())
    start = this_monday - timedelta(weeks=1)
    totals = {}
    for need, metric, count in AccessInterest.objects.filter(
        date__gte=start, date__lt=this_monday
    ).values_list("need", "metric", "count"):
        totals[(need, metric)] = totals.get((need, metric), 0) + count
    rows = []
    for need, label in AccessInterest.NEED_CHOICES:
        seen = totals.get((need, AccessInterest.SEEN), 0)
        asked = totals.get((need, AccessInterest.ASKED), 0)
        rows.append((label, f"{seen} seen · {asked} asked ({_pct(asked, seen)})"))
    year, week, _ = start.isocalendar()
    return {
        "title": "Interest in what opens on request (last week)",
        "rows": rows,
        "note": f"ISO week {year}-W{week:02d}; asked / seen",
    }


def _demo_section(demo, demo_collections):
    """Demo funnel — reported apart so it never contaminates the real metrics."""
    onboarding_joins = Event.objects.filter(
        kind=Event.Kind.MEMBER_JOINED, collection_code__in=demo_collections
    ).count()
    demo_holds = Event.objects.filter(kind=Event.Kind.HOLD_REQUESTED, actor_code__in=demo).count()
    return {
        "title": "Demo funnel (NOT real metrics)",
        "rows": [
            ("Seed + onboarding-only users", len(demo)),
            ("Onboarding collections", len(demo_collections)),
            ("Onboarding joins (MEMBER_JOINED)", onboarding_joins),
            ("Holds requested by demo users", demo_holds),
        ],
    }


def render_text(sections):
    """Plain-text rendering for stdout (and the manual/scheduler log)."""
    lines = ["", "=== OIUEEI stats summary ===", ""]
    for section in sections:
        lines.append(section["title"])
        lines.append("-" * len(section["title"]))
        for label, value in section["rows"]:
            lines.append(f"  {label}: {value}")
        if section.get("note"):
            lines.append(f"  ({section['note']})")
        lines.append("")
    return "\n".join(lines)
