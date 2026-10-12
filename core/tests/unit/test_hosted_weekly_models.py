"""The two tables of the weekly series: the milestones that name phases, and the snapshots.

**Tests code that is not in the standalone** (see `test_hosted_popin.py` for why the
file sits here).

Pinned: which phase a week belongs to (the last milestone dated before the week closes,
`PRE` before the first), that a week is stored once, and that the snapshot admin lets
nobody create, edit or delete a row — a closed week is the record.
"""

import html
from datetime import date

import pytest
from django.contrib import admin as django_admin
from django.db import IntegrityError, transaction
from django.test import RequestFactory

from core.models import User
from hosted.admin import MilestoneAdmin, WeeklySnapshotAdmin
from hosted.models import Milestone, WeeklySnapshot

MONDAY = date(2026, 9, 14)  # the week runs 14 – 20 Sep; its cutoff is Monday 21 Sep
Phase = Milestone.Phase


def milestone(day, phase, label="x"):
    return Milestone.objects.create(date=day, phase=phase, label=label)


@pytest.mark.django_db
class TestPhaseOfAWeek:
    def test_it_is_pre_before_any_milestone(self):
        assert Milestone.phase_of_week(MONDAY) == Milestone.PRE

    def test_it_is_pre_when_the_first_milestone_starts_after_the_week_closes(self):
        milestone(date(2026, 9, 21), Phase.EARLY_ADOPTERS)  # the very next Monday

        assert Milestone.phase_of_week(MONDAY) == Milestone.PRE

    def test_a_milestone_on_the_closing_sunday_belongs_to_that_week(self):
        milestone(date(2026, 9, 20), Phase.EARLY_ADOPTERS)

        assert Milestone.phase_of_week(MONDAY) == Phase.EARLY_ADOPTERS

    def test_a_milestone_on_the_first_monday_belongs_to_that_week(self):
        milestone(MONDAY, Phase.EARLY_ADOPTERS)

        assert Milestone.phase_of_week(MONDAY) == Phase.EARLY_ADOPTERS

    def test_the_last_milestone_before_the_cutoff_wins(self):
        milestone(date(2026, 9, 7), Phase.EARLY_ADOPTERS)
        milestone(date(2026, 9, 16), Phase.DEV_LAUNCH)
        milestone(date(2026, 9, 30), Phase.PRODUCT_LAUNCH)

        assert Milestone.phase_of_week(MONDAY) == Phase.DEV_LAUNCH
        assert Milestone.phase_of_week(date(2026, 9, 7)) == Phase.EARLY_ADOPTERS
        assert Milestone.phase_of_week(date(2026, 9, 28)) == Phase.PRODUCT_LAUNCH

    def test_the_labels_of_a_week_are_the_milestones_inside_it(self):
        milestone(date(2026, 9, 13), Phase.EARLY_ADOPTERS, "Sunday before")
        milestone(date(2026, 9, 14), Phase.DEV_LAUNCH, "Monday")
        milestone(date(2026, 9, 20), Phase.DEV_LAUNCH, "Sunday")
        milestone(date(2026, 9, 21), Phase.PRODUCT_LAUNCH, "Next Monday")

        assert Milestone.labels_of_week(MONDAY) == ["Monday", "Sunday"]


@pytest.mark.django_db
class TestOneRowPerWeek:
    def test_a_week_is_stored_once(self):
        WeeklySnapshot.objects.create(
            week_start=MONDAY, metrics={}, schema_version=1, origin=WeeklySnapshot.Origin.LIVE
        )

        with pytest.raises(IntegrityError), transaction.atomic():
            WeeklySnapshot.objects.create(
                week_start=MONDAY,
                metrics={},
                schema_version=1,
                origin=WeeklySnapshot.Origin.BACKFILL,
            )


@pytest.mark.django_db
class TestTheSnapshotAdminIsReadOnly:
    @pytest.fixture
    def request_as_operator(self):
        request = RequestFactory().get("/oiueei-admin/")
        request.user = User.objects.create(
            code="OPER01", email="lala@your-domain.test", is_staff=True, is_superuser=True
        )
        return request

    @pytest.fixture
    def snapshot(self):
        return WeeklySnapshot.objects.create(
            week_start=MONDAY,
            metrics={"creators": 3},
            schema_version=1,
            origin=WeeklySnapshot.Origin.LIVE,
        )

    def test_nobody_creates_edits_or_deletes_a_week(self, request_as_operator, snapshot):
        snapshots = WeeklySnapshotAdmin(WeeklySnapshot, django_admin.site)

        assert snapshots.has_add_permission(request_as_operator) is False
        assert snapshots.has_change_permission(request_as_operator, snapshot) is False
        assert snapshots.has_delete_permission(request_as_operator, snapshot) is False

    def test_the_detail_shows_the_metrics_as_formatted_json(self, snapshot):
        snapshots = WeeklySnapshotAdmin(WeeklySnapshot, django_admin.site)

        shown = html.unescape(str(snapshots.formatted_metrics(snapshot)))

        assert shown.startswith("<pre>") and '"creators": 3' in shown

    def test_both_tables_live_in_the_one_admin_site(self):
        assert isinstance(django_admin.site._registry[Milestone], MilestoneAdmin)
        assert isinstance(django_admin.site._registry[WeeklySnapshot], WeeklySnapshotAdmin)
