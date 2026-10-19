from django.db import migrations


class Migration(migrations.Migration):
    """Second of two steps that retire ``CalendarExportMark``.

    The previous step took the model out of the state and emptied the table; this
    one, a release later, removes the table. There is no ``DeleteModel`` because
    the model no longer exists, and ``IF EXISTS`` keeps a fresh database (which
    created and dropped nothing of the kind) from failing.
    """

    dependencies = [
        ("core", "0161_join_summary_sent_on"),
    ]

    operations = [
        migrations.RunSQL(
            "DROP TABLE IF EXISTS calendar_export_marks",
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
