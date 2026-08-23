"""`help_text` only — this migration emits no SQL.

The field used to describe its contents as Cloudinary public_ids, which stopped
being true when uploads moved to object storage. `help_text` is Django-side
metadata (the admin renders it; the database has never seen it), so `AlterField`
here changes nothing about the column. It exists so `makemigrations --check`
stays clean and the next real schema change does not silently carry this along.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0136_user_inactivity_notified"),
    ]

    operations = [
        migrations.AlterField(
            model_name="thing",
            name="gallery",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Additional photos beyond the cover thumbnail: an ordered list of storage keys. Max 8. Things only (not collections).",
            ),
        ),
    ]
