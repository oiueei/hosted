"""Take the dormant `reservation_max_hours` out of the model, keeping its column.

0150 replaced it with `reservation_min_minutes`/`reservation_max_minutes` and
left it dormant: unread and unwritten by the app, but still declared on the
model — so the ORM still names it in every Collection SELECT and INSERT.
Dropping the column outright in the release that removes the field would break
exactly that: Heroku's release phase runs `migrate` while the dynos of the
previous release are still serving, and every query they make about a
collection would name a column that no longer exists until they restart.

So this release does the half that is safe with both codebases running:

1. The column gets a **database-level** default of 3 (`db_default`). The old
   code keeps writing its own value; the new code, which no longer knows the
   column, inserts without it and the database fills it in — so the NOT NULL
   constraint never trips.
2. The field leaves Django's **state only** (`SeparateDatabaseAndState`, no
   database operation), so the model, the serializers and every query stop
   mentioning it.

A later release — once no running code declares the field — drops the column
with a plain `RemoveField` equivalent in SQL. Reversible: backwards, the field
returns to the state and the database default is removed again, which is the
exact schema 0151 left.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0151_collection_email_note"),
    ]

    operations = [
        migrations.AlterField(
            model_name="collection",
            name="reservation_max_hours",
            field=models.PositiveSmallIntegerField(default=3, db_default=3),
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(model_name="collection", name="reservation_max_hours"),
            ],
        ),
    ]
