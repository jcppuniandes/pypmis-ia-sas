"""Real empty-safe additive Scope-to-Schedule PostgreSQL migration roundtrip."""

import json
import os
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

import app.main  # noqa: F401
from app.core.config import get_settings
from app.database.session import Base

O1A = {"operational_project_bindings", "project_controls_periods", "operational_context_commands"}


def test_schedule_postgresql_single_successor_roundtrip_preserves_scope_and_o1a(monkeypatch):
    url = os.getenv("PYPMIS_O1BB_MIGRATION_DATABASE_URL", "")
    assert url, "Requires the explicit disposable Schedule migration database"
    assert os.getenv("PYPMIS_O1BB_FIXTURE") == "disposable-only"
    migration_engine = create_engine(url)
    assert migration_engine.dialect.name == "postgresql" and migration_engine.url.database == "o1bb_migration"
    schedule = {
        mapper.local_table.name
        for mapper in Base.registry.mappers
        if mapper.class_.__module__.startswith("app.modules.schedule_foundation")
    }
    scope = {
        mapper.local_table.name
        for mapper in Base.registry.mappers
        if mapper.class_.__module__.startswith("app.modules.scope_foundation")
    }
    future = {
        mapper.local_table.name
        for mapper in Base.registry.mappers
        if mapper.class_.__module__.startswith(("app.modules.awp", "app.modules.cost_foundation"))
    }
    assert schedule and scope
    config = Config("alembic.ini")
    script = ScriptDirectory.from_config(config)
    heads = script.get_heads()
    assert len(heads) == 1
    target_revision = "20261021_0071"
    assert script.get_revision(target_revision).down_revision == "20261020_0070"
    initial = set(inspect(migration_engine).get_table_names())
    if initial:
        with migration_engine.connect() as connection:
            for name in schedule & initial:
                assert connection.scalar(text(f'SELECT count(*) FROM "{name}"')) == 0
    else:
        Base.metadata.create_all(
            migration_engine,
            tables=[
                table for table in Base.metadata.sorted_tables if table.name not in O1A | scope | schedule | future
            ],
        )
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        if not initial:
            command.stamp(config, "20261011_0068")
            command.upgrade(config, "20261019_0069")
            command.upgrade(config, "20261020_0070")
        command.upgrade(config, target_revision)
        assert O1A | scope | schedule <= set(inspect(migration_engine).get_table_names())
        with migration_engine.connect() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == target_revision
            before_triggers = connection.scalar(text("SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal"))
        command.downgrade(config, "20261020_0070")
        assert not schedule & set(inspect(migration_engine).get_table_names())
        assert O1A | scope <= set(inspect(migration_engine).get_table_names())
        command.upgrade(config, target_revision)
        with migration_engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal")) == before_triggers
        evidence = {
            "engine": "PostgreSQL",
            "database": "o1bb_migration",
            "single_head": heads[0],
            "parent": "20261020_0070",
            "initial_orm_bootstrap": True,
            "empty_to_head_claimed": False,
            "steps": ["UPGRADE_0070_TO_0071_PASS", "SAFE_EMPTY_SCHEDULE_DOWNGRADE_0070_PASS", "REUPGRADE_PASS"],
            "new_tables": sorted(schedule),
            "scope_tables_preserved": sorted(scope),
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
