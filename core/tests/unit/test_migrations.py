"""
The one migration in this release that changes a preference a person already holds.

0126 flipped ``User.notify_news``'s model default to True, which — as Django
intends — rewrites no existing row. 0127 is the deliberate second half: it
subscribes the accounts that predate the change, so the digest reaches somebody
instead of nobody. That is a data migration writing over a stored answer, and it
runs unattended on every Heroku deploy via the ``release`` command.

**Scope of these tests, stated plainly:** they exercise the migration's data
operation (``subscribe_existing``) against the live app registry, not a
``MigrationExecutor`` round-trip through the historical model state. The repo has
no migration-test harness, and standing one up would migrate the whole app
backwards past six later migrations on a database the rest of the suite shares.
What is pinned here is therefore the part that can actually be got wrong and the
part the migration's own docstring promises: which rows it selects, that it says
what it does, and that running it twice is safe. The migration *graph* — that
0127 follows 0126 and that the backward pass is a no-op — is asserted from the
module's own declarations rather than by executing them.
"""

import importlib

import pytest
from django.apps import apps as live_apps
from django.db import migrations

from core.models import User

MIGRATION = importlib.import_module("core.migrations.0127_subscribe_existing_users_to_digests")


@pytest.mark.django_db
class TestSubscribeExistingUsersToDigests:
    def test_an_account_from_before_the_change_ends_up_subscribed(self):
        """The whole point: without this the digest goes on reaching nobody,
        because 0126 rewrote no existing row."""
        old = User.objects.create(code="OLD001", email="old@example.com", notify_news=False)

        MIGRATION.subscribe_existing(live_apps, None)

        old.refresh_from_db()
        assert old.notify_news is True

    def test_it_leaves_notify_activity_alone(self):
        """It subscribes to Cat. 3 news, not to everything. A migration that
        widened to the other preference would be invisible here otherwise —
        both columns are booleans on the same row."""
        user = User.objects.create(
            code="OLD002",
            email="old2@example.com",
            notify_news=False,
            notify_activity=False,
        )

        MIGRATION.subscribe_existing(live_apps, None)

        user.refresh_from_db()
        assert user.notify_news is True
        assert user.notify_activity is False, (
            "the other preference is not this migration's to touch"
        )

    def test_one_pass_finishes_the_job_so_a_re_run_matches_nothing(self):
        """ "Complete in one pass" — the migration's own claim, and what makes a
        re-run during a half-failed deploy harmless: one pass leaves no row for
        a second to select.

        The claim used to read "Idempotent: re-running matches nothing the
        second time", which is only true of an unchanged database. The filter
        selects on the *current* value, not on a marker of who was migrated, so
        a re-run against a database where somebody has opted out since would
        sweep them back up. That limit is now written into the migration; this
        test pins the half that actually holds.
        """
        User.objects.create(code="OLD003", email="old3@example.com", notify_news=False)
        User.objects.create(code="OLD004", email="old4@example.com", notify_news=False)

        MIGRATION.subscribe_existing(live_apps, None)

        assert not User.objects.filter(notify_news=False).exists(), (
            "one pass must leave nothing behind for a second to find"
        )

    def test_the_backward_pass_is_a_noop_not_a_mass_unsubscribe(self):
        """A reverse that set everyone to False would opt out the people who had
        chosen True themselves — destroying a preference rather than restoring
        one. Rolling back to 0126 must leave the flags where they are."""
        (operation,) = MIGRATION.Migration.operations

        assert isinstance(operation, migrations.RunPython)
        assert operation.reverse_code is migrations.RunPython.noop

    def test_it_runs_after_the_default_flip_it_completes(self):
        """0127 only makes sense once 0126 has changed the default; ordering them
        the other way round would subscribe nobody."""
        assert ("core", "0126_alter_user_notify_news") in MIGRATION.Migration.dependencies
