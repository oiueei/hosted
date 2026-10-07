from django.db import migrations, models


class Migration(migrations.Migration):
    """Additive only: BookingPeriod.return_reminded_at, a nullable timestamp.

    Null = never reminded, so no data migration and nothing to backfill — every
    existing row simply starts as "never nudged"."""

    dependencies = [
        ("core", "0155_member_proposals_default_off"),
    ]

    operations = [
        migrations.AddField(
            model_name="bookingperiod",
            name="return_reminded_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
