"""Reapply the final additive revision only inside the owned O1A fixture DB."""

import hashlib
import json
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.database.session import engine


def main():
    assert os.getenv("PYPMIS_O1A_FIXTURE") == "disposable-only"
    assert engine.dialect.name == "postgresql" and engine.url.database == "o1a"
    tables = ("operational_project_bindings", "project_controls_periods", "operational_context_commands")
    with engine.connect() as connection:
        before = {table: connection.scalar(text(f"SELECT count(*) FROM {table}")) for table in tables}
    configuration = Config("alembic.ini")
    command.downgrade(configuration, "20261011_0068")
    command.upgrade(configuration, "20261019_0069")
    with engine.connect() as connection:
        after = {table: connection.scalar(text(f"SELECT count(*) FROM {table}")) for table in tables}
        triggers = list(
            connection.scalars(
                text(
                    "SELECT trigger_name FROM information_schema.triggers WHERE trigger_name LIKE 'o1a_%' ORDER BY event_object_table,trigger_name"
                )
            )
        )
    manifest = {
        "database": "o1a",
        "isolated_fixture_only": True,
        "discarded_test_rows": before,
        "new_table_counts": after,
        "triggers": triggers,
        "migration_sha256": hashlib.sha256(
            Path("alembic/versions/20261019_0069_operational_context.py").read_bytes()
        ).hexdigest(),
    }
    Path("/artifacts/final-ddl-refresh.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest))


if __name__ == "__main__":
    main()
