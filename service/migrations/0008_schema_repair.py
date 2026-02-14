# service/migrations/0008_schema_repair.py

from django.db import migrations


def _table_exists(schema_editor, table_name: str) -> bool:
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = %s",
            [table_name],
        )
        return cursor.fetchone() is not None


def _column_exists(schema_editor, table_name: str, column_name: str) -> bool:
    with schema_editor.connection.cursor() as cursor:
        cursor.execute(f'PRAGMA table_info("{table_name}")')
        rows = cursor.fetchall()
    cols = {r[1] for r in rows}
    return column_name in cols


def _add_column_sqlite(schema_editor, table_name: str, column_name: str, column_sql: str) -> None:
    schema_editor.execute(f'ALTER TABLE "{table_name}" ADD COLUMN "{column_name}" {column_sql}')


def repair_schema(apps, schema_editor):
    if schema_editor.connection.vendor != "sqlite":
        return

    serviceorder_table = "service_serviceorder"
    ticket_table = "service_ticket"
    ticketmessage_table = "service_ticketmessage"
    serviceorderlog_table = "service_serviceorderlog"

    if _table_exists(schema_editor, serviceorder_table):
        if not _column_exists(schema_editor, serviceorder_table, "promised_date"):
            _add_column_sqlite(schema_editor, serviceorder_table, "promised_date", "DATE NULL")

        if not _column_exists(schema_editor, serviceorder_table, "checklist"):
            _add_column_sqlite(schema_editor, serviceorder_table, "checklist", "TEXT NOT NULL DEFAULT '{}'")

    if _table_exists(schema_editor, ticket_table):
        if not _column_exists(schema_editor, ticket_table, "updated_at"):
            _add_column_sqlite(schema_editor, ticket_table, "updated_at", "DATETIME NOT NULL DEFAULT (CURRENT_TIMESTAMP)")

    if not _table_exists(schema_editor, ticketmessage_table):
        TicketMessage = apps.get_model("service", "TicketMessage")
        schema_editor.create_model(TicketMessage)

    if not _table_exists(schema_editor, serviceorderlog_table):
        ServiceOrderLog = apps.get_model("service", "ServiceOrderLog")
        schema_editor.create_model(ServiceOrderLog)


class Migration(migrations.Migration):

    dependencies = [
        ("service", "0007_merge_0002_0006"),
    ]

    operations = [
        migrations.RunPython(repair_schema, migrations.RunPython.noop),
    ]