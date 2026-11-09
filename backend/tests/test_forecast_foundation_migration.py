"""Real PostgreSQL additive upgrade/downgrade/re-upgrade in a migration-only DB."""

import os

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from app.modules.forecast_foundation.migration_schema import FORECAST_MIGRATION_TABLE_NAMES


def test_forecast_single_successor_and_real_postgres_roundtrip():
    url = os.getenv("PYPMIS_O1C_MIGRATION_DATABASE_URL")
    if not url:
        pytest.skip("Dedicated disposable O1C migration PostgreSQL required")
    assert os.getenv("PYPMIS_O1C_FIXTURE") == "disposable-only"
    isolated = create_engine(url)
    assert isolated.dialect.name == "postgresql" and isolated.url.database == "o1c_migration"
    config = Config("alembic.ini")
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == ["20261106_0075"]
    assert scripts.get_revision("20261106_0075").down_revision == "20261104_0074"
    initial_tables = set(inspect(isolated).get_table_names())
    protected = {
        name: [(c["name"], str(c["type"]), c["nullable"]) for c in inspect(isolated).get_columns(name)]
        for name in initial_tables - FORECAST_MIGRATION_TABLE_NAMES
    }
    with isolated.connect() as connection:
        initial_revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert initial_revision in {"20261104_0074", "20261106_0075"}
        assert connection.scalar(text("SELECT count(*) FROM enterprise_workspaces")) == 0
        assert connection.scalar(text("SELECT count(*) FROM enterprise_workspaces WHERE id=14")) == 0
    previous = os.environ.get("DATABASE_URL")
    from app.core.config import get_settings

    try:
        os.environ["DATABASE_URL"] = url
        get_settings.cache_clear()
        if initial_revision == "20261106_0075":
            assert FORECAST_MIGRATION_TABLE_NAMES <= initial_tables
            with isolated.connect() as connection:
                assert all(
                    connection.scalar(text(f'SELECT count(*) FROM "{name}"')) == 0
                    for name in FORECAST_MIGRATION_TABLE_NAMES
                )
            command.downgrade(config, "20261104_0074")
        before_tables = set(inspect(isolated).get_table_names())
        assert not FORECAST_MIGRATION_TABLE_NAMES & before_tables
        assert before_tables == initial_tables - FORECAST_MIGRATION_TABLE_NAMES
        command.upgrade(config, "20261106_0075")
        new = set(inspect(isolated).get_table_names()) - before_tables
        assert len(new) == 6 and new == FORECAST_MIGRATION_TABLE_NAMES
        from app.database.session import Base

        def type_signature(value):
            result = str(value).upper()
            return "TIMESTAMP" if result == "TIMESTAMP WITHOUT TIME ZONE" else result

        for name in new:
            actual_columns = {
                c["name"]: (type_signature(c["type"]), c["nullable"]) for c in inspect(isolated).get_columns(name)
            }
            expected_columns = {
                c.name: (type_signature(c.type.compile(dialect=isolated.dialect)), c.nullable)
                for c in Base.metadata.tables[name].columns
            }
            assert actual_columns == expected_columns, f"Frozen migration/ORM mismatch in {name}"
        for name, columns in protected.items():
            assert [(c["name"], str(c["type"]), c["nullable"]) for c in inspect(isolated).get_columns(name)] == columns
        with isolated.connect() as connection:
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal AND tgname LIKE 'tr_%_o1c'")
                )
                == 7
            )
            assert all(connection.scalar(text(f'SELECT count(*) FROM "{name}"')) == 0 for name in new)
        command.downgrade(config, "20261104_0074")
        assert set(inspect(isolated).get_table_names()) == before_tables
        with isolated.connect() as connection:
            assert (
                connection.scalar(
                    text("SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal AND tgname LIKE 'tr_%_o1c'")
                )
                == 0
            )
        command.upgrade(config, "20261106_0075")
        assert set(inspect(isolated).get_table_names()) == before_tables | new
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        get_settings.cache_clear()
        isolated.dispose()
