"""Add Collection.email_note — the owner's note in the two requester emails.

Purely additive (blank default), no data movement: existing collections
simply have no note, which sends the same emails as before.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0150_reservation_minutes'),
    ]

    operations = [
        migrations.AddField(
            model_name='collection',
            name='email_note',
            field=models.CharField(blank=True, default='', max_length=2048),
        ),
    ]
