"""Verify the frozen O2A migration against PostgreSQL and the live model metadata."""

import os
from types import SimpleNamespace

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

import app.main as application
from app.core.config import get_settings
from app.database.session import Base
from app.modules.engineering_foundation.migration_schema import ENGINEERING_MIGRATION_TABLE_NAMES


def test_engineering_is_migration_only_at_startup(monkeypatch):
    calls = []
    monkeypatch.setattr(application, "engine", SimpleNamespace(dialect=SimpleNamespace(name="sqlite")))
    monkeypatch.setattr(
        Base.metadata, "create_all", lambda *, bind, tables: calls.append({table.name for table in tables})
    )
    application._create_schema_for_local_runtime()
    assert len(calls) == 1 and calls[0] and not calls[0] & ENGINEERING_MIGRATION_TABLE_NAMES
    assert ENGINEERING_MIGRATION_TABLE_NAMES <= set(Base.metadata.tables)


def test_engineering_migration_single_head_and_postgresql_roundtrip(monkeypatch):
    url = os.getenv("PYPMIS_O2A_MIGRATION_DATABASE_URL")
    if not url:
        pytest.skip("Dedicated disposable O2A migration PostgreSQL required")
    assert os.getenv("PYPMIS_O2A_FIXTURE") == "disposable-only"
    engine = create_engine(url)
    assert engine.dialect.name == "postgresql" and engine.url.database == "o2a_migration"
    assert engine.url.username == "o2a"
    names = ENGINEERING_MIGRATION_TABLE_NAMES
    config = Config("alembic.ini")
    scripts = ScriptDirectory.from_config(config)
    new, parent = "20261109_0076", "20261106_0075"
    assert scripts.get_heads() == [new]
    assert scripts.get_revision(new).down_revision == parent
    tables = set(inspect(engine).get_table_names())
    protected = {
        name: [(c["name"], str(c["type"]), c["nullable"]) for c in inspect(engine).get_columns(name)]
        for name in tables - names
    }
    with engine.connect() as conn:
        initial = conn.scalar(text("SELECT version_num FROM alembic_version"))
        assert initial in {new, parent}
        assert conn.scalar(text("SELECT count(*) FROM enterprise_workspaces")) == 0
    previous = os.environ.get("DATABASE_URL")
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        if initial == new:
            command.downgrade(config, parent)
        assert set(inspect(engine).get_table_names()) == tables - names
        command.upgrade(config, new)
        inventory = inspect(engine)
        assert set(inventory.get_table_names()) == (tables - names) | names

        def type_signature(value):
            return str(value).upper().replace("TIMESTAMP WITHOUT TIME ZONE", "TIMESTAMP")

        for name in names:
            model = Base.metadata.tables[name]
            actual = {c["name"]: (type_signature(c["type"]), c["nullable"]) for c in inventory.get_columns(name)}
            expected = {
                c.name: (type_signature(c.type.compile(dialect=engine.dialect)), c.nullable) for c in model.columns
            }
            assert actual == expected, name
            assert {
                index["name"] for index in inventory.get_indexes(name) if not index.get("duplicates_constraint")
            } == {index.name for index in model.indexes}, name
        for name, signature in protected.items():
            assert [(c["name"], str(c["type"]), c["nullable"]) for c in inventory.get_columns(name)] == signature
        with engine.connect() as conn:
            assert (
                conn.scalar(text("SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal AND tgname LIKE 'tr_%_o2a'"))
                == 10
            )
        command.downgrade(config, parent)
        assert set(inspect(engine).get_table_names()) == tables - names
        command.upgrade(config, new)
        assert set(inspect(engine).get_table_names()) == (tables - names) | names
    finally:
        if previous is None:
            monkeypatch.delenv("DATABASE_URL", raising=False)
        else:
            monkeypatch.setenv("DATABASE_URL", previous)
        get_settings.cache_clear()
        engine.dispose()
