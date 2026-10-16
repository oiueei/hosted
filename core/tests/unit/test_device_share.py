"""device_share — the week-by-week share of mobile, read from DeviceDay alone."""

import csv
import io
from datetime import date

import pytest
import time_machine
from django.core.management import call_command

from core.models import DeviceDay


def put(day, device, metric, count):
    DeviceDay.objects.create(date=day, device=device, metric=metric, count=count)


def run(*args):
    out = io.StringIO()
    call_command("device_share", *args, stdout=out)
    return out.getvalue()


@pytest.fixture
def two_weeks(db):
    # Today is Wednesday of ISO week 43; week 42 is the one before.
    put(date(2026, 10, 13), "MOBILE", "PEOPLE", 30)  # W42
    put(date(2026, 10, 14), "MOBILE", "PEOPLE", 11)  # W42
    put(date(2026, 10, 14), "OTHER", "PEOPLE", 9)
    put(date(2026, 10, 15), "MOBILE", "FORM_SAVES", 3)
    put(date(2026, 10, 15), "OTHER", "FORM_SAVES", 11)
    put(date(2026, 10, 20), "MOBILE", "PEOPLE", 5)  # W43
    put(date(2026, 10, 20), "OTHER", "PEOPLE", 15)
    put(date(2026, 10, 21), "OTHER", "FORM_SAVES", 4)


@pytest.fixture(autouse=True)
def wednesday_of_week_43():
    with time_machine.travel("2026-10-21 12:00", tick=False):
        yield


class TestDeviceShare:
    def test_each_week_shows_its_sums_and_the_share_of_mobile(self, two_weeks):
        lines = run("--weeks", "2").splitlines()
        w42 = next(line for line in lines if line.startswith("2026-W42"))
        w43 = next(line for line in lines if line.startswith("2026-W43"))
        assert "41 / 9 (82 %)" in w42
        assert "3 / 11 (21 %)" in w42
        assert "5 / 15 (25 %)" in w43
        assert "0 / 4 (0 %)" in w43

    def test_weeks_run_from_the_oldest_to_the_latest(self, two_weeks):
        out = run("--weeks", "2")
        assert out.index("2026-W42") < out.index("2026-W43")

    def test_a_week_with_no_data_shows_zeros_and_a_dash_not_a_division(self, db):
        out = run("--weeks", "1")
        assert "2026-W43" in out
        assert "0 / 0 (—)" in out

    def test_weeks_one_shows_only_the_latest(self, two_weeks):
        out = run("--weeks", "1")
        assert "2026-W43" in out
        assert "2026-W42" not in out

    def test_four_weeks_by_default(self, db):
        out = run()
        for week in ("W40", "W41", "W42", "W43"):
            assert f"2026-{week}" in out
        assert "2026-W39" not in out

    def test_csv_has_a_header_and_one_row_per_week(self, two_weeks):
        rows = list(csv.reader(io.StringIO(run("--weeks", "2", "--csv"))))
        assert rows[0] == [
            "week",
            "people_mobile",
            "people_other",
            "people_pct_mobile",
            "form_saves_mobile",
            "form_saves_other",
            "form_saves_pct_mobile",
        ]
        assert rows[1] == ["2026-W42", "41", "9", "82", "3", "11", "21"]
        assert rows[2] == ["2026-W43", "5", "15", "25", "0", "4", "0"]

    def test_csv_leaves_the_share_empty_for_a_week_with_no_data(self, db):
        rows = list(csv.reader(io.StringIO(run("--weeks", "1", "--csv"))))
        assert rows[1] == ["2026-W43", "0", "0", "", "0", "0", ""]

    def test_a_week_older_than_the_window_is_left_out(self, two_weeks):
        put(date(2026, 8, 3), "MOBILE", "PEOPLE", 99)
        assert "99" not in run("--weeks", "2")
