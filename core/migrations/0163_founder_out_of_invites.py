from django.db import migrations
from django.db.models import F


def forget_founders_membership(apps, schema_editor):
    """Take each collection's founder out of its ``invites`` and ``co_owners``.

    The founder is an FK on the collection, never a member; a row of theirs in
    either set lets "removing the member" delete things the founder's own rules
    keep from a curator. Only those two rows go: no thing is deleted, nobody else
    is touched and no event is written. Idempotent.
    """
    Collection = apps.get_model("core", "Collection")
    for collection in Collection.objects.filter(invites=F("owner")).distinct():
        collection.invites.remove(collection.owner_id)
        collection.co_owners.remove(collection.owner_id)
    for collection in Collection.objects.filter(co_owners=F("owner")).distinct():
        collection.co_owners.remove(collection.owner_id)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0162_drop_calendar_export_marks"),
    ]

    operations = [
        migrations.RunPython(forget_founders_membership, migrations.RunPython.noop),
    ]
