"""Runtime bootstrap must not bypass Forecast's additive Alembic guards."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from sqlalchemy import Column, Integer, MetaData, Table, create_engine, inspect

from app.modules.forecast_foundation import models, reporting_models
from app.modules.forecast_foundation.migration_schema import FORECAST_MIGRATION_TABLE_NAMES


def _metadata():
    metadata = MetaData()
    Table("legacy_project", metadata, Column("id", Integer, primary_key=True))
    for name in FORECAST_MIGRATION_TABLE_NAMES:
        Table(name, metadata, Column("id", Integer, primary_key=True))
    return metadata


def test_migration_inventory_matches_all_forecast_models():
    actual = {
        value.__tablename__
        for module in (models, reporting_models)
        for value in vars(module).values()
        if isinstance(value, type) and value.__module__ == module.__name__ and hasattr(value, "__tablename__")
    }
    assert len(actual) == 6
    assert actual == FORECAST_MIGRATION_TABLE_NAMES


def test_sqlite_local_bootstrap_preserves_legacy_without_forecast(monkeypatch):
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


def test_postgres_bootstrap_excludes_forecast_and_retains_advisory_lock(monkeypatch):
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
