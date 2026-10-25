"""0166 — the user's retired palette columns are dropped for real.

Run through ``MigrationExecutor`` because only the database can tell a DROP COLUMN
from a state-only change: 0165 left `users.user_theeeme` and `users.koro` in place
for the previous release's dynos, and this migration is the one that removes them —
and, backwards, brings them back with the database defaults they held.
"""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

BEFORE = [("core", "0165_collection_theeeme")]
AFTER = [("core", "0166_drop_user_theeeme_and_koro")]

pytestmark = pytest.mark.django_db(transaction=True)


def _migrate(targets):
    MigrationExecutor(connection).migrate(targets)
    return MigrationExecutor(connection).loader.project_state(targets).apps


def _columns(table):
    with connection.cursor() as cursor:
        return {c.name for c in connection.introspection.get_table_description(cursor, table)}


@pytest.fixture
def at_before():
    """Land on 0165, and always come back to the latest migration."""
    _migrate(BEFORE)
    try:
        yield
    finally:
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())


def _insert_user(code):
    # Without the two retired columns: that is how the current code inserts a user.
    with connection.cursor() as cursor:
        cursor.execute(
            "INSERT INTO users (code, email, name, created, headline, about, photo,"
            " notify_activity, notify_news, age_range, postal_code, language, password,"
            " is_staff, is_superuser, is_active) VALUES"
            " (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [code, f"{code.lower()}@your-domain.test", "", "2026-10-26", "", "", ""]
            + [True, True, "", "", "", "", False, False, True],
        )


def test_the_columns_are_still_there_before_and_gone_after(at_before):
    assert {"user_theeeme", "koro"} <= _columns("users")

    _migrate(AFTER)

    assert not {"user_theeeme", "koro"} & _columns("users")


def test_users_survive_the_drop_with_their_other_data(at_before):
    _insert_user("DROPU1")

    _migrate(AFTER)

    with connection.cursor() as cursor:
        cursor.execute("SELECT email FROM users WHERE code = 'DROPU1'")
        assert cursor.fetchone() == ("dropu1@your-domain.test",)


def test_reversing_brings_the_columns_back_with_their_database_defaults(at_before):
    _migrate(AFTER)
    _insert_user("DROPU2")

    _migrate(BEFORE)

    assert {"user_theeeme", "koro"} <= _columns("users")
    with connection.cursor() as cursor:
        cursor.execute("SELECT user_theeeme, koro FROM users WHERE code = 'DROPU2'")
        assert cursor.fetchone() == ("BUU331", "basic")
