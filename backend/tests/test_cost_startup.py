"""The local runtime cannot create Cost authority without Alembic guards."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from sqlalchemy import Column, Integer, MetaData, Table, create_engine, inspect

from app.modules.cost_foundation import financial_models, models
from app.modules.cost_foundation.migration_schema import COST_MIGRATION_TABLE_NAMES


def _metadata():
    metadata = MetaData()
    Table("legacy_project", metadata, Column("id", Integer, primary_key=True))
    for name in COST_MIGRATION_TABLE_NAMES:
        Table(name, metadata, Column("id", Integer, primary_key=True))
    return metadata


def test_migration_only_inventory_matches_all_cost_models():
    actual = {
        value.__tablename__
        for module in (models, financial_models)
        for value in vars(module).values()
        if isinstance(value, type) and value.__module__ == module.__name__ and hasattr(value, "__tablename__")
    }
    assert len(actual) == 14
    assert actual == COST_MIGRATION_TABLE_NAMES


def test_sqlite_local_bootstrap_preserves_legacy_without_cost(monkeypatch):
    import app.main as main

    metadata = _metadata()
    engine = create_engine("sqlite://")
    monkeypatch.setattr(main, "Base", SimpleNamespace(metadata=metadata))
    monkeypatch.setattr(main, "engine", engine)
    try:
        main._create_schema_for_local_runtime()
        assert inspect(engine).get_table_names() == ["legacy_project"]
    finally:
        engine.dispose()


def test_postgres_local_bootstrap_excludes_cost_and_retains_advisory_lock(monkeypatch):
    import app.main as main

    metadata = _metadata()
    engine = MagicMock()
    engine.dialect.name = "postgresql"
    connection = engine.begin.return_value.__enter__.return_value
    create_all = MagicMock()
    monkeypatch.setattr(metadata, "create_all", create_all)
    monkeypatch.setattr(main, "Base", SimpleNamespace(metadata=metadata))
    monkeypatch.setattr(main, "engine", engine)
    main._create_schema_for_local_runtime()
    connection.exec_driver_sql.assert_called_once_with("SELECT pg_advisory_xact_lock(202606030021)")
    assert create_all.call_args.kwargs["bind"] is connection
    assert [table.name for table in create_all.call_args.kwargs["tables"]] == ["legacy_project"]
