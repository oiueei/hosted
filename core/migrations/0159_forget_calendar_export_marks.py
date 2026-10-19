from django.db import migrations

# The foreign keys of the emptied table go with the model. Kept, they would stop
# Postgres from truncating the tables they point at (a test flush truncates every
# table Django knows, and this one it no longer does), and a mark a previous-release
# dyno writes during the release phase would block deleting its collection or
# booking once nothing cascades into it. The previous release's own deletes still
# work without them. SQLite cannot drop a constraint in place and needs neither.
DROP_FOREIGN_KEYS = """
DO $$
DECLARE fk record;
BEGIN
    FOR fk IN
        SELECT conname FROM pg_constraint
        WHERE conrelid = 'calendar_export_marks'::regclass AND contype = 'f'
    LOOP
        EXECUTE 'ALTER TABLE calendar_export_marks DROP CONSTRAINT ' || quote_ident(fk.conname);
    END LOOP;
END $$;
"""


def drop_foreign_keys(apps, schema_editor):
    if schema_editor.connection.vendor == "postgresql":
        schema_editor.execute(DROP_FOREIGN_KEYS, params=None)


class Migration(migrations.Migration):
    """First of two steps that retire ``CalendarExportMark``.

    The model leaves the migration state, so nothing in this release reads,
    writes or cascades into it. The table stays, emptied and without its foreign
    keys: the previous release's dynos still run while the release phase does,
    and their deletes of a collection or a booking name it. The next release
    drops the table.
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
                migrations.RunPython(drop_foreign_keys, migrations.RunPython.noop),
            ],
        ),
    ]
