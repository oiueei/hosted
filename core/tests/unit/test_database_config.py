"""
The development settings pick the database the environment asks for.

This guards a failure that is invisible by construction. CI sets ``DATABASE_URL``
so the suite runs on PostgreSQL, because on SQLite Django reports
``has_select_for_update = False`` and **silently drops** the FOR UPDATE clause —
every row-locked path in the app (booking accept/reject/cancel, the capacity
recheck) then tests its logic without ever testing its lock.

If someone removes or breaks that branch, nothing goes red: CI quietly falls
back to SQLite, all 1100 tests still pass, and the guarantee evaporates behind a
green build. The only thing that can notice is a test on the branch itself.

The module is re-imported under a patched environment rather than inspected as
text: what matters is the ``DATABASES`` dict it actually produces.
``django.conf.settings`` already holds its own copy, so reloading the module
does not disturb the run in progress.
"""

import importlib
import os
from unittest import mock

import config.settings.development as dev_settings

CI_URL = "postgres://oiueei:oiueei@localhost:5432/oiueei_test"


def _databases_with(env):
    """The DATABASES dict development.py builds under ``env``."""
    with mock.patch.dict(os.environ, env, clear=False):
        for key in ("DATABASE_URL", "DEV_DB_NAME"):
            if key not in env:
                os.environ.pop(key, None)
        return importlib.reload(dev_settings).DATABASES


def teardown_module():
    """Leave the module holding the real environment's answer again."""
    importlib.reload(dev_settings)


def test_a_database_url_points_the_suite_at_postgres():
    """What CI relies on. Lose this and the row locks stop being tested."""
    default = _databases_with({"DATABASE_URL": CI_URL})["default"]

    assert default["ENGINE"] == "django.db.backends.postgresql"
    assert default["NAME"] == "oiueei_test"


def test_without_one_it_is_sqlite_exactly_as_before():
    """A local `pytest` must not need a database server running."""
    default = _databases_with({})["default"]

    assert default["ENGINE"] == "django.db.backends.sqlite3"
    assert str(default["NAME"]).endswith("db.sqlite3")


def test_dev_db_name_still_redirects_the_sqlite_file():
    """The migration-rehearsal escape hatch, unchanged by the Postgres branch:
    seed the "before" rows in a throwaway file, migrate, inspect, delete."""
    default = _databases_with({"DEV_DB_NAME": "/tmp/rehearsal.sqlite3"})["default"]

    assert default["ENGINE"] == "django.db.backends.sqlite3"
    assert default["NAME"] == "/tmp/rehearsal.sqlite3"


def test_a_database_url_wins_over_the_sqlite_override():
    """Both set is CI on a machine that also has DEV_DB_NAME exported. The
    server must win — falling back to a local file there would be the silent
    failure this whole module exists to catch."""
    default = _databases_with({"DATABASE_URL": CI_URL, "DEV_DB_NAME": "/tmp/x.sqlite3"})["default"]

    assert default["ENGINE"] == "django.db.backends.postgresql"
