"""Real isolated O1B-A additive upgrade/downgrade/re-upgrade proof."""

import json
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

import app.main  # noqa: F401
from app.core.config import get_settings
from app.database.session import Base

O1A_TABLES = {"operational_project_bindings", "project_controls_periods", "operational_context_commands"}


def test_o1ba_postgresql_single_successor_roundtrip(monkeypatch):
    url = os.getenv("PYPMIS_O1BA_MIGRATION_DATABASE_URL", "").strip()
    if not url:
        pytest.skip("Dedicated O1B-A migration PostgreSQL not configured")
    assert os.getenv("PYPMIS_O1BA_FIXTURE") == "disposable-only"
    migration_engine = create_engine(url)
    assert migration_engine.dialect.name == "postgresql"
    assert migration_engine.url.database == "o1ba_migration", "Never migrate a runtime/user database"
    scope_tables = {
        mapper.local_table.name
        for mapper in Base.registry.mappers
        if mapper.class_.__module__.startswith("app.modules.scope_foundation")
    }
    assert scope_tables, "Scope model registration required"
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    assert len(heads) == 1 and heads[0] != "20261019_0069"
    assert script.get_revision(heads[0]).down_revision == "20261019_0069"
    initial = set(inspect(migration_engine).get_table_names())
    if initial:
        with migration_engine.connect() as connection:
            for name in scope_tables & initial:
                assert connection.scalar(text(f'SELECT count(*) FROM "{name}"')) == 0
    else:
        Base.metadata.create_all(
            migration_engine,
            tables=[table for table in Base.metadata.sorted_tables if table.name not in scope_tables | O1A_TABLES],
        )
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        if not initial:
            command.stamp(config, "20261011_0068")
            command.upgrade(config, "20261019_0069")
        command.upgrade(config, heads[0])
        assert scope_tables <= set(inspect(migration_engine).get_table_names())
        with migration_engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == heads[0]
            assert connection.scalar(text(
                "SELECT count(*) FROM pg_trigger t JOIN pg_proc p ON p.oid=t.tgfoid "
                "WHERE p.proname='scope_o1ba_guard' AND NOT t.tgisinternal"
            )) == len(scope_tables)
        command.downgrade(config, "20261019_0069")
        assert not scope_tables & set(inspect(migration_engine).get_table_names())
        assert O1A_TABLES <= set(inspect(migration_engine).get_table_names())
        with migration_engine.connect() as connection:
            assert (
                connection.scalar(
                    text(
                        "SELECT count(*) FROM pg_trigger WHERE tgname IN ('o1a_scope','o1a_immutable') AND NOT tgisinternal"
                    )
                )
                == 6
            )
        command.upgrade(config, heads[0])
        assert scope_tables <= set(inspect(migration_engine).get_table_names())
        evidence = {
            "engine": "PostgreSQL",
            "database": "o1ba_migration",
            "single_head": heads[0],
            "initial_orm_bootstrap": True,
            "empty_to_head_claimed": False,
            "steps": ["UPGRADE_0069_TO_0070_PASS", "SAFE_EMPTY_SCOPE_DOWNGRADE_0069_PASS", "REUPGRADE_PASS"],
            "new_tables": sorted(scope_tables),
            "o1a_preserved": True,
            "production_database_touched": False,
        }
        target = Path("/artifacts/migration-roundtrip.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    finally:
        migration_engine.dispose()
        monkeypatch.undo()
        get_settings.cache_clear()
