"""Real O1A upgrade/downgrade/re-upgrade on the dedicated migration database.

The historical project requires an initial ORM schema before its Alembic chain.
This proves the additive 0068 -> 0069 successor, not empty-to-head history.
"""

import json
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

import app.main  # noqa: F401 - register all pre-existing model tables
from app.core.config import get_settings
from app.database.session import Base

TABLES = {"operational_project_bindings", "project_controls_periods", "operational_context_commands"}


def test_postgresql_additive_successor_roundtrip(monkeypatch):
    url = os.getenv("PYPMIS_O1A_MIGRATION_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("Dedicated PostgreSQL migration database not configured")
    assert os.getenv("PYPMIS_O1A_FIXTURE") == "disposable-only"
    migration_engine = create_engine(url)
    assert migration_engine.dialect.name == "postgresql"
    assert migration_engine.url.database == "o1a_migration", "Never migrate a runtime/user database from this test"
    configuration = Config("alembic.ini")
    script = ScriptDirectory.from_config(configuration)
    heads = script.get_heads()
    assert len(heads) == 1
    assert "20261019_0069" in {revision.revision for revision in script.walk_revisions(head=heads[0], base="base")}
    later_tables = {
        mapper.local_table.name
        for mapper in Base.registry.mappers
        if mapper.class_.__module__.startswith(
            ("app.modules.scope_foundation", "app.modules.schedule_foundation", "app.modules.awp")
        )
    }
    initial = set(inspect(migration_engine).get_table_names())
    if initial:
        # Re-runs are allowed only for this explicitly named disposable DB and
        # only if the prior validation left all new O1A business tables empty.
        with migration_engine.connect() as connection:
            for name in TABLES & initial:
                assert connection.scalar(text(f"SELECT count(*) FROM {name}")) == 0
    else:
        Base.metadata.create_all(
            migration_engine,
            tables=[table for table in Base.metadata.sorted_tables if table.name not in TABLES | later_tables],
        )
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    steps = []
    try:
        if not initial:
            command.stamp(configuration, "20261011_0068")
        command.upgrade(configuration, "20261019_0069")
        assert TABLES <= set(inspect(migration_engine).get_table_names())
        assert not later_tables & set(inspect(migration_engine).get_table_names())
        with migration_engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "20261019_0069"
            guard_count = connection.scalar(
                text(
                    "SELECT count(*) FROM pg_trigger WHERE tgname IN ('o1a_immutable','o1a_scope') AND NOT tgisinternal"
                )
            )
            assert guard_count == 6
        steps.append("UPGRADE_0068_TO_0069_PASS")
        command.downgrade(configuration, "20261011_0068")
        assert not TABLES & set(inspect(migration_engine).get_table_names())
        assert "admin_configurations" in inspect(migration_engine).get_table_names()
        with migration_engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "20261011_0068"
        steps.append("SAFE_EMPTY_O1A_DOWNGRADE_TO_0068_PASS")
        command.upgrade(configuration, "20261019_0069")
        assert TABLES <= set(inspect(migration_engine).get_table_names())
        steps.append("REUPGRADE_0069_PASS")
        evidence = {
            "database": "o1a_migration",
            "engine": "PostgreSQL",
            "initial_orm_bootstrap": True,
            "historical_empty_database_upgrade_claimed": False,
            "single_head": heads[0],
            "target_revision": "20261019_0069",
            "later_tables_excluded": sorted(later_tables),
            "steps": steps,
            "new_tables": sorted(TABLES),
            "postgresql_guard_trigger_count": guard_count,
            "production_database_touched": False,
        }
        destination = Path(os.getenv("PYPMIS_O1A_ARTIFACTS", "/artifacts")) / "migration-roundtrip.json"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    finally:
        migration_engine.dispose()
        monkeypatch.undo()
        get_settings.cache_clear()
