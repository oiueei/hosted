"""
Show, week by week, how much of the use comes from a phone.

    python manage.py device_share              # the last 4 ISO weeks
    python manage.py device_share --weeks 8
    python manage.py device_share --csv        # the same columns, as CSV

Two numbers per week, each as ``mobile / other (% mobile)``: signed-in people (per
day and device, summed over the week) and collection/thing saves. The second is the
one that answers whether a phone-friendlier form is worth building; the first only
says where people look. Reads ``DeviceDay`` and nothing else.
"""

import csv
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import DeviceDay

NO_SHARE = "—"


def percent_mobile(mobile, other):
    """Whole-number share of mobile, or ``None`` when the week holds nothing."""
    total = mobile + other
    return round(100 * mobile / total) if total else None


def weekly_device_share(weeks, today=None):
    """One dict per ISO week, oldest first, the current week last.

    ``today`` is the local date by default. Every week in the window is present,
    zeros included, so a quiet week reads as quiet and not as missing.
    """
    today = today or timezone.localdate()
    monday = today - timedelta(days=today.weekday())
    starts = [monday - timedelta(weeks=n) for n in range(weeks - 1, -1, -1)]
    totals = {
        start.isocalendar()[:2]: {
            ("PEOPLE", "MOBILE"): 0,
            ("PEOPLE", "OTHER"): 0,
            ("FORM_SAVES", "MOBILE"): 0,
            ("FORM_SAVES", "OTHER"): 0,
        }
        for start in starts
    }
    rows = DeviceDay.objects.filter(date__gte=starts[0], date__lt=monday + timedelta(weeks=1))
    for row in rows.values_list("date", "device", "metric", "count"):
        week = totals.get(row[0].isocalendar()[:2])
        if week is not None:
            week[(row[2], row[1])] += row[3]
    result = []
    for start in starts:
        year, number, _ = start.isocalendar()
        week = totals[(year, number)]
        entry = {"week": f"{year}-W{number:02d}"}
        for metric, key in (("PEOPLE", "people"), ("FORM_SAVES", "form_saves")):
            mobile, other = week[(metric, "MOBILE")], week[(metric, "OTHER")]
            entry[f"{key}_mobile"] = mobile
            entry[f"{key}_other"] = other
            entry[f"{key}_pct_mobile"] = percent_mobile(mobile, other)
        result.append(entry)
    return result


def _cell(entry, key):
    pct = entry[f"{key}_pct_mobile"]
    share = NO_SHARE if pct is None else f"{pct} %"
    return f"{entry[f'{key}_mobile']} / {entry[f'{key}_other']} ({share})"


class Command(BaseCommand):
    help = "Show, per ISO week, the share of mobile among signed-in people and form saves."

    def add_arguments(self, parser):
        parser.add_argument("--weeks", type=int, default=4, help="Weeks to show (default 4).")
        parser.add_argument("--csv", action="store_true", help="Write CSV to standard output.")

    def handle(self, *args, **options):
        weeks = max(1, options["weeks"])
        data = weekly_device_share(weeks)
        if options["csv"]:
            writer = csv.writer(self.stdout, lineterminator="\n")
            writer.writerow(
                [
                    "week",
                    "people_mobile",
                    "people_other",
                    "people_pct_mobile",
                    "form_saves_mobile",
                    "form_saves_other",
                    "form_saves_pct_mobile",
                ]
            )
            for entry in data:
                writer.writerow(
                    [
                        entry["week"],
                        entry["people_mobile"],
                        entry["people_other"],
                        "" if entry["people_pct_mobile"] is None else entry["people_pct_mobile"],
                        entry["form_saves_mobile"],
                        entry["form_saves_other"],
                        ""
                        if entry["form_saves_pct_mobile"] is None
                        else entry["form_saves_pct_mobile"],
                    ]
                )
            return
        cells = [(e["week"], _cell(e, "people"), _cell(e, "form_saves")) for e in data]
        width = max(len(c[1]) for c in cells + [("", "people: mobile / other (% mobile)", "")])
        self.stdout.write(
            f"{'week':<10}{'people: mobile / other (% mobile)':<{width + 3}}"
            "form saves: mobile / other (% mobile)"
        )
        for week, people, saves in cells:
            self.stdout.write(f"{week:<10}{people:<{width + 3}}{saves}")
