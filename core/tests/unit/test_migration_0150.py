"""
0150 replaces the HOUR-unit duration cap's unit (hours -> minutes) and adds a
configurable floor next to it. `reservation_max_hours` stays as a dormant
column; the data migration is what keeps an already-configured collection's
cap unchanged in the new unit.

Same scope note as `test_migrations.py`: these exercise the migration's two
`RunPython` functions directly against the live app registry, not a
`MigrationExecutor` round-trip — the repo has no migration-test harness, and
this is what the module's own docstring promises checking (an exact,
lossless unit conversion, forward and back).
"""

import importlib

import pytest
from django.apps import apps as live_apps

from core.models import Collection, User

MIGRATION = importlib.import_module("core.migrations.0150_reservation_minutes")


@pytest.mark.django_db
class TestReservationMinutesMigration:
    def _collection(self, **kwargs):
        owner_code = kwargs.pop("owner_code", "MIG001")
        owner = User.objects.create(code=owner_code, email=f"{owner_code.lower()}@test.com")
        return Collection.objects.create(
            code=kwargs.pop("code", "MIGCOL"),
            owner=owner,
            headline="X",
            allowed_thing_types=["RESERVE_THING"],
            **kwargs,
        )

    def test_forward_copies_hours_to_minutes(self):
        coll = self._collection(reservation_max_hours=5)

        MIGRATION.copy_max_hours_to_minutes(live_apps, None)

        coll.refresh_from_db()
        assert coll.reservation_max_minutes == 300

    def test_forward_leaves_the_new_minimum_at_its_own_default(self):
        """`reservation_min_minutes` has no prior data to migrate — every
        existing collection starts at 60, the same fixed floor it already
        lived under, so nothing changes until an owner deliberately lowers it."""
        coll = self._collection(reservation_max_hours=5)

        MIGRATION.copy_max_hours_to_minutes(live_apps, None)

        coll.refresh_from_db()
        assert coll.reservation_min_minutes == 60

    def test_forward_handles_several_collections_at_once(self):
        one = self._collection(code="MIGC01", owner_code="MIGO01", reservation_max_hours=1)
        two = self._collection(code="MIGC02", owner_code="MIGO02", reservation_max_hours=12)

        MIGRATION.copy_max_hours_to_minutes(live_apps, None)

        one.refresh_from_db()
        two.refresh_from_db()
        assert one.reservation_max_minutes == 60
        assert two.reservation_max_minutes == 720

    def test_backward_is_the_exact_inverse(self):
        coll = self._collection(reservation_max_minutes=300)

        MIGRATION.copy_minutes_to_max_hours(live_apps, None)

        coll.refresh_from_db()
        assert coll.reservation_max_hours == 5

    def test_round_trip_is_lossless_for_a_value_already_in_whole_hours(self):
        coll = self._collection(reservation_max_hours=7)

        MIGRATION.copy_max_hours_to_minutes(live_apps, None)
        MIGRATION.copy_minutes_to_max_hours(live_apps, None)

        coll.refresh_from_db()
        assert coll.reservation_max_hours == 7
