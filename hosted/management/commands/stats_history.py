"""Print the weekly series as CSV, for a spreadsheet.

Nothing but the CSV goes to stdout, so it can be redirected:

    heroku run --no-tty --app <app> "python manage.py stats_history" > serie.csv

One row per stored week, oldest first: the week, its phase and milestones, how it was
recorded, and then every metric in `METRIC_KEYS` order (an empty cell is a value the
week does not have, such as the three that only a live recording knows).
`--cohorts` prints instead the conversion triangle of the last snapshot.
"""

import csv
from datetime import date

from django.core.management.base import BaseCommand, CommandError

from hosted.metrics import COHORT_WINDOWS, METRIC_KEYS
from hosted.models import Milestone, WeeklySnapshot

LEAD_COLUMNS = ("week_start", "iso_week", "phase", "milestone", "origin")


def _cell(value):
    return "" if value is None else value


class Command(BaseCommand):
    help = "Print the weekly series (or, with --cohorts, the conversion triangle) as CSV."

    def add_arguments(self, parser):
        parser.add_argument(
            "--csv",
            action="store_true",
            help="One row per week (the default).",
        )
        parser.add_argument(
            "--cohorts",
            action="store_true",
            help="The triangle of the last snapshot instead: one row per week of entry.",
        )
        parser.add_argument(
            "--since", metavar="YYYY-MM-DD", help="Only the weeks that start on or after this day."
        )

    def handle(self, *args, **options):
        writer = csv.writer(self.stdout, lineterminator="\n")
        snapshots = WeeklySnapshot.objects.order_by("week_start")
        if options["since"]:
            try:
                snapshots = snapshots.filter(week_start__gte=date.fromisoformat(options["since"]))
            except ValueError as exc:
                raise CommandError(f"--since wants YYYY-MM-DD, got {options['since']!r}.") from exc

        if options["cohorts"]:
            self._cohorts(writer, snapshots.last())
        else:
            self._series(writer, snapshots)

    @staticmethod
    def _series(writer, snapshots):
        writer.writerow([*LEAD_COLUMNS, *METRIC_KEYS])
        for snap in snapshots:
            iso = snap.week_start.isocalendar()
            writer.writerow(
                [
                    snap.week_start.isoformat(),
                    f"{iso.year}-W{iso.week:02d}",
                    Milestone.phase_of_week(snap.week_start),
                    "; ".join(Milestone.labels_of_week(snap.week_start)),
                    snap.origin,
                    *[_cell(snap.metrics.get(key)) for key in METRIC_KEYS],
                ]
            )

    @staticmethod
    def _cohorts(writer, snapshot):
        writer.writerow(["cohort_week", "size", *[f"owner_within_{w}w" for w in COHORT_WINDOWS]])
        if snapshot is None:
            return
        for week, cohort in sorted(snapshot.metrics.get("cohorts", {}).items()):
            within = cohort["owner_within"]
            writer.writerow(
                [week, cohort["size"], *[within.get(str(w), "") for w in COHORT_WINDOWS]]
            )
