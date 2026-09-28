"""Drop the retired `reservation_max_hours` column for real.

This is the second half of the two-release change 0152 opened: that migration
took the field out of Django's state but deliberately left the column in the
database, because Heroku's release phase runs `migrate` while the previous
release's dynos are still serving, and they named the column in every
Collection query. With 0152 deployed, no running code declares the field any
more, so the column can finally go.

The field returns to the state first (`SeparateDatabaseAndState`, no database
operation — the column already exists) purely so the `RemoveField` that
follows has something to remove. The net effect on the state is zero, so
`makemigrations --check` stays clean, while the database gets its DROP COLUMN
through Django's schema editor, which knows the table is `collections` and
speaks both SQLite and PostgreSQL.

Reversible: backwards, the column comes back carrying the database default of
3 it has held since 0152 — not the values anyone configured before 0150,
which 0150 already converted into `reservation_max_minutes`.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0152_retire_reservation_max_hours"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="collection",
                    name="reservation_max_hours",
                    field=models.PositiveSmallIntegerField(default=3, db_default=3),
                ),
            ],
        ),
        migrations.RemoveField(model_name="collection", name="reservation_max_hours"),
    ]
