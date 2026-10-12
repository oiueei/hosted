"""Store the weekly series: one `WeeklySnapshot` per closed week.

Run daily in the Heroku Scheduler, **before** `stats_summary`, so on Monday the week
that has just closed is already saved when the email is built. Without arguments it
records the last closed week if it is missing and otherwise does nothing, which makes
the daily run idempotent. The week in progress is never stored.

    ... && python manage.py record_weekly_snapshot && python manage.py stats_summary

The first time, rebuild the past from the event log:

    heroku run --app <app> "python manage.py record_weekly_snapshot --backfill-from 2026-09-07"

Backfill fills in the weeks that are missing and leaves the ones that exist alone;
`--rebuild` recomputes those too, and refuses to go back further than the log still
has people in it (`RETENTION_EVENT_ANONYMISE_MONTHS`).
"""

from datetime import date, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.management.commands.purge_expired_data import months_ago
from hosted.metrics import (
    FIRST_WEEK,
    LIVE_ONLY_KEYS,
    SCHEMA_VERSION,
    WEEK_TZ,
    snapshot_metrics,
)
from hosted.models import WeeklySnapshot


def last_closed_week(now=None):
    """The Monday of the most recent week that has closed (never the one in progress)."""
    local = (now or timezone.now()).astimezone(WEEK_TZ).date()
    return local - timedelta(days=local.weekday()) - timedelta(days=7)


class Command(BaseCommand):
    help = "Record the last closed week of the series (and, with --backfill-from, the past)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--backfill-from",
            metavar="YYYY-MM-DD",
            help=f"Record every closed week that is missing from this date's week on "
            f"(default week: {FIRST_WEEK.isoformat()}).",
        )
        parser.add_argument(
            "--rebuild",
            action="store_true",
            help="With --backfill-from: recompute the weeks that already exist as well.",
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Say what would be done and write nothing."
        )

    def handle(self, *args, **options):
        last = last_closed_week()
        if options["rebuild"] and not options["backfill_from"]:
            raise CommandError("--rebuild goes with --backfill-from.")

        if options["backfill_from"]:
            first = self._monday(options["backfill_from"])
        else:
            first = last

        stored = dict(WeeklySnapshot.objects.values_list("week_start", "origin"))
        weeks = [first + timedelta(weeks=n) for n in range(((last - first).days // 7) + 1)]

        if options["rebuild"]:
            self._refuse_beyond_the_log(weeks)

        done = 0
        for week in weeks:
            exists = week in stored
            if exists and not options["rebuild"]:
                continue
            origin = stored.get(week) or (
                WeeklySnapshot.Origin.LIVE if week == last else WeeklySnapshot.Origin.BACKFILL
            )
            verb = "would record" if options["dry_run"] else "recorded"
            if not options["dry_run"]:
                self._store(week, origin, week == last)
            self.stdout.write(f"{verb} week of {week.isoformat()} ({origin})")
            done += 1

        if not done:
            self.stdout.write("Nothing to do: the series is up to date.")

    @staticmethod
    def _monday(text):
        try:
            day = date.fromisoformat(text)
        except ValueError as exc:
            raise CommandError(f"--backfill-from wants YYYY-MM-DD, got {text!r}.") from exc
        return day - timedelta(days=day.weekday())

    @staticmethod
    def _refuse_beyond_the_log(weeks):
        months = settings.RETENTION_EVENT_ANONYMISE_MONTHS
        if not months or not weeks:
            return
        limit = months_ago(months).astimezone(WEEK_TZ).date()
        too_old = [w for w in weeks if w < limit]
        if too_old:
            raise CommandError(
                f"--rebuild would recompute {too_old[0].isoformat()}, which is older than the "
                f"{months} months after which the event log no longer says who did what. "
                "Those weeks keep what was recorded; start from "
                f"{(limit + timedelta(days=7 - limit.weekday())).isoformat()} or later."
            )

    @staticmethod
    @transaction.atomic
    def _store(week, origin, is_last):
        live = origin == WeeklySnapshot.Origin.LIVE and is_last
        metrics = snapshot_metrics(week, live=live)
        existing = WeeklySnapshot.objects.filter(week_start=week).first()
        if existing and origin == WeeklySnapshot.Origin.LIVE and not live:
            # A week recorded live keeps what it said then about the state of that day.
            for key in LIVE_ONLY_KEYS:
                metrics[key] = existing.metrics.get(key)
        WeeklySnapshot.objects.update_or_create(
            week_start=week,
            defaults={
                "metrics": metrics,
                "schema_version": SCHEMA_VERSION,
                "origin": origin,
                "computed_at": timezone.now(),
            },
        )
