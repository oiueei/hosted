"""0159 — the calendar-export mark leaves the model state; its table stays, emptied.

The first of two releases that retire ``CalendarExportMark``. The previous
release's dynos still name the table in their cascading deletes while the
release phase runs, so this one only forgets the model and clears the rows; the
next release drops the table.

These tests run the real migration through ``MigrationExecutor`` (one step back
and forward), because what matters is the pair of effects that a state-only or a
database-only reading would miss: the model is gone from the app registry, the
table is still in the database and empty, and the step reverses.
"""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("core", "0158_device_day")]
AFTER = [("core", "0159_forget_calendar_export_marks")]
TABLE = "calendar_export_marks"

pytestmark = pytest.mark.django_db(transaction=True)


def _migrate(targets):
    executor = MigrationExecutor(connection)
    executor.migrate(targets)
    return MigrationExecutor(connection).loader.project_state(targets).apps


def _tables():
    with connection.cursor() as cursor:
        return connection.introspection.table_names(cursor)


def _count():
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT COUNT(*) FROM {TABLE}")  # noqa: S608 - fixed constant
        return cursor.fetchone()[0]


@pytest.fixture
def at_before():
    """Land on 0158, and always come back to the latest migration."""
    apps = _migrate(BEFORE)
    # Going back past the step that drops the table does not bring it back (that
    # step has no reverse), so it is rebuilt from the model as 0158 knew it.
    if TABLE not in _tables():
        with connection.schema_editor() as editor:
            editor.create_model(apps.get_model("core", "CalendarExportMark"))
    try:
        yield apps
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())


def _seed_a_mark(apps):
    User = apps.get_model("core", "User")
    Collection = apps.get_model("core", "Collection")
    Thing = apps.get_model("core", "Thing")
    BookingPeriod = apps.get_model("core", "BookingPeriod")
    Mark = apps.get_model("core", "CalendarExportMark")
    owner = User.objects.create(code="MGOWN1", email="lala1@your-domain.test", name="Owner")
    group = Collection.objects.create(code="MGCOL1", owner=owner, headline="Group")
    thing = Thing.objects.create(code="MGTHG1", owner=owner, headline="Drill", type="LEND_THING")
    booking = BookingPeriod.objects.create(
        code="MGBKG1",
        thing_code=thing,
        thing_type="LEND_THING",
        requester_code=owner,
        requester_email=owner.email,
        owner_code=owner,
        start_date="2026-12-01",
        end_date="2026-12-03",
        status="ACCEPTED",
    )
    Mark.objects.create(collection=group, booking=booking)


def test_the_model_leaves_the_state_but_the_table_stays_and_is_empty(at_before):
    _seed_a_mark(at_before)
    assert _count() == 1

    after = _migrate(AFTER)

    with pytest.raises(LookupError):
        after.get_model("core", "CalendarExportMark")
    assert TABLE in _tables()
    assert _count() == 0


def test_it_reverses_and_the_model_is_back_in_the_state(at_before):
    _migrate(AFTER)

    back = _migrate(BEFORE)

    assert back.get_model("core", "CalendarExportMark")
    assert TABLE in _tables()


def test_deleting_a_collection_and_a_booking_still_works_without_the_model():
    # Nothing cascades into the leftover table any more: with the model gone from
    # the registry the collector never names it, and the table is empty, so the
    # database's own foreign keys have nothing to object to.
    from core.models import BookingPeriod, Collection, Thing, User

    owner = User.objects.create(code="DLOWN1", email="lele2@your-domain.test", name="Owner")
    group = Collection.objects.create(code="DLCOL1", owner=owner, headline="Group")
    thing = Thing.objects.create(code="DLTHG1", owner=owner, headline="Drill", type="LEND_THING")
    group.things.add(thing)
    booking = BookingPeriod.objects.create(
        code="DLBKG1",
        thing_code=thing,
        thing_type="LEND_THING",
        requester_code=owner,
        requester_email=owner.email,
        owner_code=owner,
        start_date="2026-12-01",
        end_date="2026-12-03",
        status="ACCEPTED",
    )

    booking.delete()
    group.delete()

    assert not BookingPeriod.objects.filter(code="DLBKG1").exists()
    assert not Collection.objects.filter(code="DLCOL1").exists()


def test_the_following_migration_drops_the_table(at_before):
    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())

    assert TABLE not in _tables()
