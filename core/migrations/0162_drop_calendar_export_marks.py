from django.db import migrations


class Migration(migrations.Migration):
    """Second of two steps that retire ``CalendarExportMark``.

    The previous step took the model out of the state and emptied the table; this
    one, a release later, removes the table. There is no ``DeleteModel`` because
    the model no longer exists. On a fresh database 0145 still creates the table
    and this step drops it; ``IF EXISTS`` only protects a database where the
    table is already gone (dropped by hand, or restored without it).
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
