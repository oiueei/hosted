"""Create the app's own palette and seed its one row.

The values are written out here rather than imported: a migration records what was
true when it ran, and the model's defaults may change. After this, the palette is
edited in the Django admin.
"""

import django.core.validators
import re
from django.db import migrations, models


def seed_braaanding(apps, schema_editor):
    Braaanding = apps.get_model("core", "Braaanding")
    Braaanding.objects.update_or_create(
        code="OIUEEI",
        defaults={
            "color_01": "#191919",
            "color_02": "#F4E5DD",
            "color_03": "#D77452",
            "color_04": "#191919",
            "color_05": "#191919",
            "color_06": "#FAFAFA",
            "koro": "basic",
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0163_founder_out_of_invites'),
    ]

    operations = [
        migrations.CreateModel(
            name='Braaanding',
            fields=[
                ('code', models.CharField(default='OIUEEI', max_length=6, primary_key=True, serialize=False)),
                ('color_01', models.CharField(default='#191919', help_text='#RRGGBB', max_length=7, validators=[django.core.validators.RegexValidator(re.compile('^#[0-9A-Fa-f]{6}$'), 'Use a colour like #RRGGBB.')])),
                ('color_02', models.CharField(default='#F4E5DD', help_text='#RRGGBB', max_length=7, validators=[django.core.validators.RegexValidator(re.compile('^#[0-9A-Fa-f]{6}$'), 'Use a colour like #RRGGBB.')])),
                ('color_03', models.CharField(default='#D77452', help_text='#RRGGBB', max_length=7, validators=[django.core.validators.RegexValidator(re.compile('^#[0-9A-Fa-f]{6}$'), 'Use a colour like #RRGGBB.')])),
                ('color_04', models.CharField(default='#191919', help_text='#RRGGBB', max_length=7, validators=[django.core.validators.RegexValidator(re.compile('^#[0-9A-Fa-f]{6}$'), 'Use a colour like #RRGGBB.')])),
                ('color_05', models.CharField(default='#191919', help_text='#RRGGBB', max_length=7, validators=[django.core.validators.RegexValidator(re.compile('^#[0-9A-Fa-f]{6}$'), 'Use a colour like #RRGGBB.')])),
                ('color_06', models.CharField(default='#FAFAFA', help_text='#RRGGBB', max_length=7, validators=[django.core.validators.RegexValidator(re.compile('^#[0-9A-Fa-f]{6}$'), 'Use a colour like #RRGGBB.')])),
                ('koro', models.CharField(choices=[('basic', 'Basic'), ('beat', 'Beat'), ('calm', 'Calm'), ('pulse', 'Pulse'), ('vibration', 'Vibration'), ('wave', 'Wave')], default='basic', max_length=9)),
            ],
            options={
                'verbose_name': 'Braaanding',
                'verbose_name_plural': 'Braaanding',
                'db_table': 'braaanding',
            },
        ),
        migrations.RunPython(seed_braaanding, migrations.RunPython.noop),
    ]
