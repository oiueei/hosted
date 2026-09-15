"""Replace the HOUR-unit duration cap's unit — hours -> minutes — and add a
configurable floor next to it.

`reservation_max_hours` (0147) was a single, hour-granular cap: 1-12, no
minimum below it besides a fixed, non-configurable 60 minutes hardcoded in
`Collection.reservation_hour_violation`. An early adopter running a fab lab
wants reservations shorter than an hour (a quick machine slot), which needs
two things at once: a minimum the owner can actually lower, and a unit fine
enough to express it in.

`reservation_max_hours` is left in place, dormant — not read or written by any
code after this migration, dropped in a later one, the same caution a feature
removal gets. The data migration below is what keeps an already-configured
collection's cap unchanged in the new unit: without it, every HOUR-unit
collection would silently reset to the new field's bare default (180) instead
of keeping whatever the owner actually set.

**Genuinely reversible, unlike 0127's one-shot backfill**: this is an exact,
lossless unit conversion in both directions (multiply by 60 forward, integer-
divide by 60 back), not a preference migration that could destroy someone's
deliberate choice on a second pass. `reservation_min_minutes` has no prior
data to migrate — it's a new floor, and it starts at 60 for every row (the
same fixed floor every collection already lived under), so no existing
collection's behaviour changes until an owner deliberately lowers it.
"""

from django.db import migrations, models
from django.db.models import F


def copy_max_hours_to_minutes(apps, schema_editor):
    Collection = apps.get_model("core", "Collection")
    Collection.objects.update(reservation_max_minutes=F("reservation_max_hours") * 60)


def copy_minutes_to_max_hours(apps, schema_editor):
    # A plain Python loop, not `F("reservation_max_minutes") / 60`: integer
    # division through an ORM `F()` expression is not portable across
    # backends (Postgres and SQLite don't agree on the result type of
    # integer/integer), and this table is small enough that it doesn't need
    # to be a single UPDATE.
    Collection = apps.get_model("core", "Collection")
    for collection in Collection.objects.all():
        collection.reservation_max_hours = collection.reservation_max_minutes // 60
        collection.save(update_fields=["reservation_max_hours"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0149_widen_request_info"),
    ]

    operations = [
        migrations.AddField(
            model_name="collection",
            name="reservation_min_minutes",
            field=models.PositiveSmallIntegerField(default=60),
        ),
        migrations.AddField(
            model_name="collection",
            name="reservation_max_minutes",
            field=models.PositiveSmallIntegerField(default=180),
        ),
        migrations.RunPython(copy_max_hours_to_minutes, copy_minutes_to_max_hours),
    ]
