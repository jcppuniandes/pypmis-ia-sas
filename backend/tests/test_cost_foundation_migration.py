"""Real PostgreSQL additive upgrade/downgrade/re-upgrade, no runtime data."""

import os

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

from app.modules.cost_foundation.migration_schema import COST_MIGRATION_TABLE_NAMES


def test_cost_single_successor_and_real_postgres_roundtrip():
    url = os.getenv("PYPMIS_O1BC_MIGRATION_DATABASE_URL")
    if not url:
        pytest.skip("Dedicated disposable O1B-C migration PostgreSQL required")
    assert os.getenv("PYPMIS_O1BC_FIXTURE") == "disposable-only"
    isolated = create_engine(url)
    assert isolated.dialect.name == "postgresql" and isolated.url.database == "o1bc_migration"
    config = Config("alembic.ini")
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == ["20261022_0073"]
    assert scripts.get_revision("20261022_0073").down_revision == "20261021_0072"
    initial_tables = set(inspect(isolated).get_table_names())
    protected = {
        name: [(c["name"], str(c["type"]), c["nullable"]) for c in inspect(isolated).get_columns(name)]
        for name in initial_tables
        if name not in COST_MIGRATION_TABLE_NAMES
        and name.startswith(("scope_", "schedule_", "awp_", "operational_", "project_controls_", "cost_"))
    }
    with isolated.connect() as connection:
        initial_revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert initial_revision in {"20261021_0072", "20261022_0073"}
        assert connection.scalar(text("SELECT count(*) FROM enterprise_workspaces WHERE id=14")) == 0
    previous = os.environ.get("DATABASE_URL")
    from app.core.config import get_settings

    try:
        os.environ["DATABASE_URL"] = url
        get_settings.cache_clear()
        if initial_revision == "20261022_0073":
            # A completed prior run deliberately leaves this dedicated database
            # upgraded. Never reset it blindly: the exact migration-only Cost
            # inventory must still be present and every table must be empty.
            # Legacy cost_records/cost_codes/cost_breakdown_structures are
            # protected pre-existing tables, not migration-owned reset targets.
            cost_tables = COST_MIGRATION_TABLE_NAMES & initial_tables
            assert len(COST_MIGRATION_TABLE_NAMES) == 14
            assert cost_tables == COST_MIGRATION_TABLE_NAMES
            with isolated.connect() as connection:
                assert all(connection.scalar(text(f'SELECT count(*) FROM "{name}"')) == 0 for name in cost_tables)
            command.downgrade(config, "20261021_0072")
        before_tables = set(inspect(isolated).get_table_names())
        assert not COST_MIGRATION_TABLE_NAMES & before_tables
        assert before_tables == initial_tables - COST_MIGRATION_TABLE_NAMES
        command.upgrade(config, "20261022_0073")
        new = set(inspect(isolated).get_table_names()) - before_tables
        assert len(new) == 14 and new == COST_MIGRATION_TABLE_NAMES
        from app.database.session import Base

        def type_signature(value):
            # PostgreSQL's unqualified TIMESTAMP is precisely WITHOUT TIME ZONE;
            # preserve the distinct WITH TIME ZONE type and all other semantics.
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
                    text("SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal AND tgname LIKE 'tr_%_o1bc'")
                )
                == 15
            )
            assert all(connection.scalar(text(f"SELECT count(*) FROM {name}")) == 0 for name in new)
        command.downgrade(config, "20261021_0072")
        assert set(inspect(isolated).get_table_names()) == before_tables
        command.upgrade(config, "20261022_0073")
        assert set(inspect(isolated).get_table_names()) == before_tables | new
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        get_settings.cache_clear()
        isolated.dispose()
