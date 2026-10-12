"""`record_weekly_snapshot`: the series is written once a week and can be rebuilt.

**Tests code that is not in the standalone** (see `test_hosted_popin.py` for why the
file sits here).

Pinned: running it twice stores one row; the week in progress is never stored; a
backfill from the first week creates every closed week in order and leaves existing ones
alone; `--rebuild` recomputes them but not beyond what the log still knows; `--dry-run`
writes nothing; and a week recorded live reads the same as the same week rebuilt later.
"""

from datetime import UTC, date, datetime
from io import StringIO

import pytest
import time_machine
from django.core.management import CommandError, call_command

from core.models import Collection, Event, User
from hosted.metrics import LIVE_ONLY_KEYS, METRIC_KEYS, WEEK_TZ
from hosted.models import WeeklySnapshot

K = Event.Kind


def madrid(year, month, day, hour=12):
    return datetime(year, month, day, hour, tzinfo=WEEK_TZ)


def run(*args):
    out = StringIO()
    call_command("record_weekly_snapshot", *args, stdout=out)
    return out.getvalue()


def weeks():
    return list(WeeklySnapshot.objects.order_by("week_start").values_list("week_start", "origin"))


@pytest.mark.django_db
class TestTheDailyRun:
    def test_running_it_twice_on_the_same_monday_leaves_one_row(self):
        with time_machine.travel(madrid(2026, 10, 12, 9), tick=False):
            run()
            second = run()

        assert weeks() == [(date(2026, 10, 5), "LIVE")]
        assert "Nothing to do" in second

    def test_sunday_night_stores_the_week_before_and_never_the_one_in_progress(self):
        with time_machine.travel(madrid(2026, 10, 11, 23), tick=False):
            run()

        assert weeks() == [(date(2026, 9, 28), "LIVE")]

    def test_the_live_week_carries_the_state_of_the_day(self):
        owner = User.objects.create(code="AAAAAA", email="lala@your-domain.test")
        Collection.objects.create(
            code="COL001",
            owner=owner,
            headline="Real",
            visibility=Collection.Visibility.PUBLIC,
        )
        with time_machine.travel(madrid(2026, 10, 12, 9), tick=False):
            run()

        metrics = WeeklySnapshot.objects.get().metrics
        assert metrics["collections_public"] == 1
        assert metrics["things_available"] == 0


@pytest.mark.django_db
class TestBackfill:
    def test_from_the_first_week_it_creates_every_closed_week_in_order(self):
        with time_machine.travel(madrid(2026, 10, 12, 9), tick=False):
            run("--backfill-from", "2026-09-07")

        assert weeks() == [
            (date(2026, 9, 7), "BACKFILL"),
            (date(2026, 9, 14), "BACKFILL"),
            (date(2026, 9, 21), "BACKFILL"),
            (date(2026, 9, 28), "BACKFILL"),
            (date(2026, 10, 5), "LIVE"),
        ]

    def test_a_past_week_has_no_value_for_what_only_today_can_say_and_the_last_one_has(self):
        with time_machine.travel(madrid(2026, 10, 12, 9), tick=False):
            run("--backfill-from", "2026-09-07")

        first = WeeklySnapshot.objects.get(week_start=date(2026, 9, 7)).metrics
        last = WeeklySnapshot.objects.get(week_start=date(2026, 10, 5)).metrics
        assert all(first[key] is None for key in LIVE_ONLY_KEYS)
        assert all(last[key] is not None for key in LIVE_ONLY_KEYS)

    def test_a_date_in_mid_week_starts_from_its_monday(self):
        with time_machine.travel(madrid(2026, 10, 12, 9), tick=False):
            run("--backfill-from", "2026-09-30")

        assert [w for w, _ in weeks()] == [date(2026, 9, 28), date(2026, 10, 5)]

    def test_it_does_not_touch_a_week_that_exists_and_rebuild_does(self):
        WeeklySnapshot.objects.create(
            week_start=date(2026, 9, 14),
            metrics={"creators": 99},
            schema_version=0,
            origin=WeeklySnapshot.Origin.BACKFILL,
        )
        with time_machine.travel(madrid(2026, 10, 12, 9), tick=False):
            run("--backfill-from", "2026-09-07")
            kept = WeeklySnapshot.objects.get(week_start=date(2026, 9, 14)).metrics["creators"]
            run("--backfill-from", "2026-09-07", "--rebuild")
            rebuilt = WeeklySnapshot.objects.get(week_start=date(2026, 9, 14)).metrics["creators"]

        assert kept == 99
        assert rebuilt == 0

    def test_rebuild_refuses_to_go_back_past_what_the_log_still_knows(self):
        WeeklySnapshot.objects.create(
            week_start=date(2026, 9, 7),
            metrics={"creators": 99},
            schema_version=1,
            origin=WeeklySnapshot.Origin.BACKFILL,
        )
        with time_machine.travel(madrid(2028, 1, 10, 9), tick=False):
            with pytest.raises(CommandError, match="older than the 14 months"):
                run("--backfill-from", "2026-09-07", "--rebuild")

        assert WeeklySnapshot.objects.get().metrics == {"creators": 99}

    def test_with_no_anonymisation_configured_any_week_can_be_rebuilt(self, settings):
        settings.RETENTION_EVENT_ANONYMISE_MONTHS = 0

        with time_machine.travel(madrid(2030, 1, 10, 9), tick=False):
            run("--backfill-from", "2026-09-07", "--rebuild", "--dry-run")

    def test_rebuild_is_only_for_a_backfill(self):
        with pytest.raises(CommandError, match="--backfill-from"):
            run("--rebuild")

    def test_a_date_that_is_not_a_date_is_refused_by_name(self):
        with pytest.raises(CommandError, match="YYYY-MM-DD"):
            run("--backfill-from", "next week")

    def test_dry_run_says_what_it_would_do_and_writes_nothing(self):
        with time_machine.travel(madrid(2026, 10, 12, 9), tick=False):
            said = run("--backfill-from", "2026-09-07", "--dry-run")

        assert said.count("would record") == 5
        assert weeks() == []


@pytest.mark.django_db
class TestLiveAndRebuiltAgree:
    def test_a_week_recorded_live_reads_the_same_when_rebuilt_later(self):
        Event.objects.create(
            kind=K.COLLECTION_CREATED,
            actor_code="AAAAAA",
            collection_code="COL001",
            created=madrid(2026, 10, 6),
        )
        Event.objects.create(
            kind=K.MEMBER_JOINED,
            actor_code="BBBBBB",
            collection_code="COL001",
            source=Event.Source.INVITE,
            created=madrid(2026, 10, 7),
        )
        Event.objects.create(
            kind=K.HOLD_REQUESTED,
            actor_code="BBBBBB",
            thing_code="THG001",
            thing_type="GIFT_THING",
            created=madrid(2026, 10, 8),
        )
        with time_machine.travel(madrid(2026, 10, 12, 9), tick=False):
            run()
        live = WeeklySnapshot.objects.get().metrics

        with time_machine.travel(datetime(2026, 10, 30, 9, tzinfo=UTC), tick=False):
            run("--backfill-from", "2026-10-05", "--rebuild")
        rebuilt_row = WeeklySnapshot.objects.get(week_start=date(2026, 10, 5))

        assert rebuilt_row.origin == WeeklySnapshot.Origin.LIVE
        for key in METRIC_KEYS:
            if key not in LIVE_ONLY_KEYS:
                assert rebuilt_row.metrics[key] == live[key], key
        assert rebuilt_row.metrics["cohorts"] == live["cohorts"]
        # What it said about the state of that day is kept, not replaced by today's.
        assert {k: rebuilt_row.metrics[k] for k in LIVE_ONLY_KEYS} == {
            k: live[k] for k in LIVE_ONLY_KEYS
        }
