"""Drop the retired `users.user_theeeme` and `users.koro` columns for real.

This is the second half of the two-release change 0165 opened: that migration
took `User.theeeme` and `User.koro` out of Django's state but deliberately left
the columns in the database, each with a database-level default, because
Heroku's release phase runs `migrate` while the previous release's dynos are
still serving, and they named both columns in every User query and INSERT. With
0165 deployed, no running code declares the fields any more, so the columns can
finally go.

The fields return to the state first (`SeparateDatabaseAndState`, no database
operation — the columns already exist) purely so the `RemoveField`s that follow
have something to remove. The net effect on the state is zero, so
`makemigrations --check` stays clean, while the database gets its DROP COLUMN
through Django's schema editor, which knows the table is `users` and speaks both
SQLite and PostgreSQL. The koro choices are written out here rather than
imported: a migration records what was true when it ran.

Reversible: backwards, the columns come back carrying the database defaults they
held since 0165 (`BUU331` and `basic`), not the palettes users had before — those
moved to the collections in 0165.
"""

import django.db.models.deletion
from django.db import migrations, models

import core.models.theeeme


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0165_collection_theeeme"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="user",
                    name="koro",
                    field=models.CharField(
                        choices=[
                            ("basic", "Basic"),
                            ("beat", "Beat"),
                            ("calm", "Calm"),
                            ("pulse", "Pulse"),
                            ("vibration", "Vibration"),
                            ("wave", "Wave"),
                        ],
                        db_default="basic",
                        default="basic",
                        max_length=9,
                    ),
                ),
                migrations.AddField(
                    model_name="user",
                    name="theeeme",
                    field=models.ForeignKey(
                        db_column="user_theeeme",
                        db_default="BUU331",
                        default=core.models.theeeme.random_theeeme,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="users",
                        to="core.theeeme",
                    ),
                ),
            ],
        ),
        migrations.RemoveField(model_name="user", name="koro"),
        migrations.RemoveField(model_name="user", name="theeeme"),
    ]
