"""`stats_history`: the series as a CSV that opens in a spreadsheet.

**Tests code that is not in the standalone** (see `test_hosted_popin.py` for why the
file sits here).

Pinned: the header, the order of the rows, an empty cell for a missing value, the
milestone column, the `--since` filter, the cohort triangle, and that stdout holds the
CSV and nothing else, so `heroku run --no-tty … > serie.csv` is usable as it comes.
"""

import csv
from datetime import date
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from hosted.metrics import METRIC_KEYS
from hosted.models import Milestone, WeeklySnapshot

LEAD = ["week_start", "iso_week", "phase", "milestone", "origin"]


def snapshot(week_start, origin="BACKFILL", **values):
    metrics = dict.fromkeys(METRIC_KEYS, 0)
    metrics.update(values)
    metrics["cohorts"] = {}
    return WeeklySnapshot.objects.create(
        week_start=week_start, metrics=metrics, schema_version=1, origin=origin
    )


def history(*args):
    out = StringIO()
    call_command("stats_history", *args, stdout=out)
    return out.getvalue()


def rows(*args):
    return list(csv.DictReader(StringIO(history(*args))))


@pytest.mark.django_db
class TestTheSeries:
    def test_the_header_is_the_lead_columns_and_then_every_metric_in_catalogue_order(self):
        header = next(csv.reader(StringIO(history())))

        assert header == [*LEAD, *METRIC_KEYS]

    def test_weeks_come_oldest_first(self):
        snapshot(date(2026, 9, 21))
        snapshot(date(2026, 9, 7))
        snapshot(date(2026, 9, 14))

        assert [r["week_start"] for r in rows()] == ["2026-09-07", "2026-09-14", "2026-09-21"]

    def test_a_value_the_week_does_not_have_is_an_empty_cell_and_zero_is_zero(self):
        snapshot(date(2026, 9, 7), collections_public=None, creators=0)

        row = rows()[0]

        assert row["collections_public"] == ""
        assert row["creators"] == "0"

    def test_a_week_recorded_before_a_metric_existed_has_an_empty_cell_for_it(self):
        old = snapshot(date(2026, 9, 7))
        del old.metrics["collections_network"]
        old.save()

        row = rows()[0]

        assert row["collections_network"] == ""
        assert row["creators"] == "0"

    def test_each_week_names_its_iso_week_phase_and_milestones(self):
        snapshot(date(2026, 9, 7), origin="LIVE")
        Milestone.objects.create(
            date=date(2026, 9, 8), phase=Milestone.Phase.EARLY_ADOPTERS, label="Early adopters"
        )
        Milestone.objects.create(
            date=date(2026, 9, 10), phase=Milestone.Phase.EARLY_ADOPTERS, label="Second wave"
        )

        row = rows()[0]

        assert row["iso_week"] == "2026-W37"
        assert row["phase"] == "EARLY_ADOPTERS"
        assert row["milestone"] == "Early adopters; Second wave"
        assert row["origin"] == "LIVE"

    def test_a_week_before_any_milestone_is_pre_with_no_milestone(self):
        snapshot(date(2026, 9, 7))

        row = rows()[0]

        assert (row["phase"], row["milestone"]) == ("PRE", "")

    def test_since_keeps_the_weeks_from_that_day_on(self):
        for day in (date(2026, 9, 7), date(2026, 9, 14), date(2026, 9, 21)):
            snapshot(day)

        assert [r["week_start"] for r in rows("--since", "2026-09-14")] == [
            "2026-09-14",
            "2026-09-21",
        ]

    def test_a_since_that_is_not_a_date_is_refused(self):
        with pytest.raises(CommandError, match="YYYY-MM-DD"):
            history("--since", "soon")

    def test_stdout_is_the_csv_and_nothing_else(self):
        snapshot(date(2026, 9, 7))

        text = history()

        assert len(text.splitlines()) == 2
        assert "\r" not in text
        assert not text.endswith("\n\n")


@pytest.mark.django_db
class TestTheTriangle:
    def test_it_prints_the_cohorts_of_the_last_snapshot(self):
        snapshot(date(2026, 9, 7))
        last = snapshot(date(2026, 9, 14))
        last.metrics["cohorts"] = {
            "2026-09-07": {"size": 4, "owners": 2, "owner_within": {"1": 1, "2": 2}},
            "2026-09-14": {"size": 3, "owners": 0, "owner_within": {}},
        }
        last.save()

        got = rows("--cohorts")

        assert list(got[0]) == [
            "cohort_week",
            "size",
            "owner_within_1w",
            "owner_within_2w",
            "owner_within_4w",
            "owner_within_8w",
        ]
        assert got[0] == {
            "cohort_week": "2026-09-07",
            "size": "4",
            "owner_within_1w": "1",
            "owner_within_2w": "2",
            "owner_within_4w": "",
            "owner_within_8w": "",
        }
        assert got[1]["owner_within_1w"] == ""

    def test_with_no_snapshots_it_is_just_the_header(self):
        assert rows("--cohorts") == []
        assert history("--cohorts").startswith("cohort_week,size,owner_within_1w")
