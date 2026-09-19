"""
0150 replaces the HOUR-unit duration cap's unit (hours -> minutes) and adds a
configurable floor next to it. `reservation_max_hours` stays as a dormant
column; the data migration is what keeps an already-configured collection's
cap unchanged in the new unit.

Same scope note as `test_migrations.py`: these exercise the migration's two
`RunPython` functions directly, not a `MigrationExecutor` round-trip — the
repo has no migration-test harness, and this is what the module's own
docstring promises checking (an exact, lossless unit conversion, forward and
back).

They run against the app registry **as of 0150**, not the live one: since
0152 the live `Collection` no longer declares `reservation_max_hours`, while
its column is still in the database (with a DB default of 3) until a later
release drops it — so the historical model can still read and write it. Rows
are created through the live model, as the running app creates them, and the
dormant column is set and read through the historical one. When the column
is finally dropped these tests go with it: 0150 will then only ever run as
part of a full `migrate` from scratch.
"""

import importlib
from functools import lru_cache

import pytest
from django.db import connection
from django.db.migrations.loader import MigrationLoader

from core.models import Collection, User

MIGRATION = importlib.import_module("core.migrations.0150_reservation_minutes")


@lru_cache(maxsize=1)
def state_apps():
    """The app registry as 0150 left it — `reservation_max_hours` included."""
    loader = MigrationLoader(None, ignore_no_migrations=True)
    return loader.project_state(("core", "0150_reservation_minutes")).apps


def historical(code):
    return state_apps().get_model("core", "Collection").objects.get(code=code)


@pytest.mark.django_db
class TestReservationMinutesMigration:
    def _collection(self, max_hours=None, **kwargs):
        owner_code = kwargs.pop("owner_code", "MIG001")
        owner = User.objects.create(code=owner_code, email=f"{owner_code.lower()}@test.com")
        coll = Collection.objects.create(
            code=kwargs.pop("code", "MIGCOL"),
            owner=owner,
            headline="X",
            allowed_thing_types=["RESERVE_THING"],
            **kwargs,
        )
        if max_hours is not None:
            state_apps().get_model("core", "Collection").objects.filter(code=coll.code).update(
                reservation_max_hours=max_hours
            )
        return coll

    def test_forward_copies_hours_to_minutes(self):
        coll = self._collection(max_hours=5)

        MIGRATION.copy_max_hours_to_minutes(state_apps(), None)

        coll.refresh_from_db()
        assert coll.reservation_max_minutes == 300

    def test_forward_leaves_the_new_minimum_at_its_own_default(self):
        """`reservation_min_minutes` has no prior data to migrate — every
        existing collection starts at 60, the same fixed floor it already
        lived under, so nothing changes until an owner deliberately lowers it."""
        coll = self._collection(max_hours=5)

        MIGRATION.copy_max_hours_to_minutes(state_apps(), None)

        coll.refresh_from_db()
        assert coll.reservation_min_minutes == 60

    def test_forward_handles_several_collections_at_once(self):
        one = self._collection(code="MIGC01", owner_code="MIGO01", max_hours=1)
        two = self._collection(code="MIGC02", owner_code="MIGO02", max_hours=12)

        MIGRATION.copy_max_hours_to_minutes(state_apps(), None)

        one.refresh_from_db()
        two.refresh_from_db()
        assert one.reservation_max_minutes == 60
        assert two.reservation_max_minutes == 720

    def test_backward_is_the_exact_inverse(self):
        self._collection(reservation_max_minutes=300)

        MIGRATION.copy_minutes_to_max_hours(state_apps(), None)

        assert historical("MIGCOL").reservation_max_hours == 5

    def test_round_trip_is_lossless_for_a_value_already_in_whole_hours(self):
        self._collection(max_hours=7)

        MIGRATION.copy_max_hours_to_minutes(state_apps(), None)
        MIGRATION.copy_minutes_to_max_hours(state_apps(), None)

        assert historical("MIGCOL").reservation_max_hours == 7


@pytest.mark.django_db
def test_0152_keeps_the_retired_column_filled_by_the_database():
    """0152 takes `reservation_max_hours` out of the model but leaves its NOT
    NULL column in place for the release in which the previous code — which
    still names it in every query — is still serving. What makes that safe is
    the database default: the new code inserts without the column, and the
    row still gets a value instead of a NOT NULL violation."""
    owner = User.objects.create(code="MIG152", email="mig152@test.com")
    Collection.objects.create(code="MIGC52", owner=owner, headline="X")

    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT reservation_max_hours FROM {Collection._meta.db_table} WHERE code = %s",
            ["MIGC52"],
        )
        assert cursor.fetchone() == (3,)
