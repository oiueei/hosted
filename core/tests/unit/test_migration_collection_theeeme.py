"""0165 — the palette moves from the user to the collection, in two releases.

Run through ``MigrationExecutor`` (one step back and forward) because what matters
is the pair of effects a state-only or a database-only reading would miss: every
collection starts with its **founder's** palette, and the user's two columns leave
the model but stay in the database, with a default of their own, so the previous
release's dynos (which still name them in every User query) keep working while the
release phase runs.
"""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("core", "0164_braaanding")]
AFTER = [("core", "0165_collection_theeeme")]

pytestmark = pytest.mark.django_db(transaction=True)


def _migrate(targets):
    executor = MigrationExecutor(connection)
    executor.migrate(targets)
    return MigrationExecutor(connection).loader.project_state(targets).apps


def _columns(table):
    with connection.cursor() as cursor:
        return {c.name for c in connection.introspection.get_table_description(cursor, table)}


@pytest.fixture
def at_before():
    """Land on 0164, and always come back to the latest migration."""
    apps = _migrate(BEFORE)
    try:
        yield apps
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())


def _founders(apps):
    User = apps.get_model("core", "User")
    Collection = apps.get_model("core", "Collection")
    wave = User.objects.create(
        code="PFWAVE", email="lala@your-domain.test", theeeme_id="JMPA01", koro="wave"
    )
    plain = User.objects.create(
        code="PFPLAI", email="lele@your-domain.test", theeeme_id="BUU331", koro="basic"
    )
    Collection.objects.create(code="PFCOL1", owner=wave, headline="One")
    Collection.objects.create(code="PFCOL2", owner=wave, headline="Two")
    Collection.objects.create(code="PFCOL3", owner=plain, headline="Three")


def test_each_collection_starts_with_the_palette_and_koro_of_its_founder(at_before):
    _founders(at_before)

    after = _migrate(AFTER)

    Collection = after.get_model("core", "Collection")
    palettes = {c.code: (c.theeeme_id, c.koro) for c in Collection.objects.all()}
    assert palettes == {
        "PFCOL1": ("JMPA01", "wave"),
        "PFCOL2": ("JMPA01", "wave"),
        "PFCOL3": ("BUU331", "basic"),
    }


def test_the_user_leaves_the_model_but_keeps_its_columns(at_before):
    after = _migrate(AFTER)

    user_fields = {f.name for f in after.get_model("core", "User")._meta.get_fields()}
    assert not {"theeeme", "koro"} & user_fields
    assert {"user_theeeme", "koro"} <= _columns("users")


def test_a_user_created_by_the_new_code_gets_a_palette_from_the_database(at_before):
    """The new code does not know the columns, so it inserts without them: the
    database default is what keeps NOT NULL and the foreign key satisfied."""
    _migrate(AFTER)

    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO users (code, email, name, created, headline, about, photo,"
            " notify_activity, notify_news, age_range, postal_code, language, password,"
            " is_staff, is_superuser, is_active) VALUES"
            " ('PFNEW1', 'lolo@your-domain.test', '', '2026-10-24', '', '', '', 1, 1, '',"
            " '', '', '', 0, 0, 1)"
        )
        cursor.execute("SELECT user_theeeme, koro FROM users WHERE code = 'PFNEW1'")
        assert cursor.fetchone() == ("BUU331", "basic")


def test_it_reverses_and_the_user_has_its_fields_in_the_state_again(at_before):
    _founders(at_before)
    _migrate(AFTER)

    back = _migrate(BEFORE)

    user_fields = {f.name for f in back.get_model("core", "User")._meta.get_fields()}
    assert {"theeeme", "koro"} <= user_fields
    assert not {"theeeme", "koro"} & {
        f.name for f in back.get_model("core", "Collection")._meta.get_fields()
    }
