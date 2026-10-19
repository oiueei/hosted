from django.db import migrations


class Migration(migrations.Migration):
    """First of two steps that retire ``CalendarExportMark``.

    The model leaves the migration state, so nothing in this release reads,
    writes or cascades into it. The table stays, emptied: the previous release's
    dynos still run while the release phase does, and their deletes of a
    collection or a booking name it. The next release drops the table.
    """

    dependencies = [
        ("core", "0158_device_day"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.DeleteModel(name="CalendarExportMark"),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="DELETE FROM calendar_export_marks",
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
        ),
    ]
