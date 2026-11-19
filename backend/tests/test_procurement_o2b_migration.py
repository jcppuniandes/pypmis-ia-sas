"""Verify 0077 on a distinct empty PostgreSQL schema; never on the app database."""

import os
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect, text

import app.main as application
from app.core.config import get_settings
from app.database.session import Base
from app.modules.procurement_foundation.migration_schema import PROCUREMENT_MIGRATION_TABLE_NAMES

NEW, PARENT = "20261111_0077", "20261109_0076"


def test_procurement_is_migration_only_at_startup(monkeypatch):
    seen = []
    monkeypatch.setattr(application, "engine", SimpleNamespace(dialect=SimpleNamespace(name="sqlite")))
    monkeypatch.setattr(
        Base.metadata, "create_all", lambda *, bind, tables: seen.append({table.name for table in tables})
    )
    application._create_schema_for_local_runtime()
    names = PROCUREMENT_MIGRATION_TABLE_NAMES
    assert len(names) == 27 and names <= set(Base.metadata.tables)
    assert len(seen) == 1 and seen[0] and not names & seen[0]


def test_procurement_postgresql_upgrade_downgrade_upgrade(monkeypatch):
    url = os.getenv("PYPMIS_O2B_MIGRATION_DATABASE_URL")
    if not url:
        pytest.skip("Dedicated empty PostgreSQL O2B migration fixture required")
    assert os.getenv("PYPMIS_O2B_FIXTURE") == "disposable-only"
    parsed = urlsplit(url)
    assert (parsed.scheme, parsed.hostname, parsed.port, parsed.username, parsed.path) == (
        "postgresql+psycopg",
        "127.0.0.1",
        5556,
        "o2b",
        "/o2b_migration",
    )
    engine = create_engine(url)
    config = Config("alembic.ini")
    scripts = ScriptDirectory.from_config(config)
    assert scripts.get_heads() == [NEW] and scripts.get_revision(NEW).down_revision == PARENT
    names = PROCUREMENT_MIGRATION_TABLE_NAMES
    initial_tables = set(inspect(engine).get_table_names())
    upstream = initial_tables - names

    def columns(inventory, name):
        return {column["name"]: (str(column["type"]), column["nullable"]) for column in inventory.get_columns(name)}

    protected = {name: columns(inspect(engine), name) for name in upstream}
    with engine.connect() as connection:
        initial = connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert initial in {NEW, PARENT}
        assert not connection.scalar(text("SELECT count(*) FROM enterprise_workspaces"))
        assert not connection.scalar(text("SELECT count(*) FROM tenants"))
        if initial == NEW:
            assert not connection.scalar(text("SELECT count(*) FROM procurement_purchase_orders"))
    previous = os.environ.get("DATABASE_URL")
    monkeypatch.setenv("DATABASE_URL", url)
    get_settings.cache_clear()
    try:
        if initial == NEW:
            command.downgrade(config, PARENT)
        assert set(inspect(engine).get_table_names()) == upstream
        for index in range(2):
            command.upgrade(config, NEW)
            inventory = inspect(engine)
            assert set(inventory.get_table_names()) == upstream | names
            for name in names:
                model = Base.metadata.tables[name]
                assert columns(inventory, name) == {
                    c.name: (
                        str(c.type.compile(dialect=engine.dialect)).replace("TIMESTAMP WITHOUT TIME ZONE", "TIMESTAMP"),
                        c.nullable,
                    )
                    for c in model.columns
                }, name
                indexes = {i["name"] for i in inventory.get_indexes(name) if not i.get("duplicates_constraint")}
                assert indexes == {i.name for i in model.indexes}, name
            assert {name: columns(inventory, name) for name in upstream} == protected
            with engine.connect() as connection:
                assert connection.scalar(text("SELECT version_num FROM alembic_version")) == NEW
                guarded = connection.scalar(
                    text(
                        "SELECT count(*) FROM pg_trigger WHERE NOT tgisinternal AND "
                        "tgfoid IN ('o2b_procurement_record_guard()'::regprocedure, 'o2b_procurement_profile_guard()'::regprocedure)"
                    )
                )
                assert guarded == 28
            if index == 0:
                command.downgrade(config, PARENT)
                assert set(inspect(engine).get_table_names()) == upstream
    finally:
        if previous is None:
            monkeypatch.delenv("DATABASE_URL")
        else:
            monkeypatch.setenv("DATABASE_URL", previous)
        get_settings.cache_clear()
        engine.dispose()
