"""Real additive QRA up/down/up; only an empty disposable database is allowed."""

import os

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect, text
from tests.postgres.test_wave3b_migration_postgres import _alembic

BEFORE, AFTER = "20261008_0066", "20261009_0067"
TABLES = {"qra_cost_source_assessments", "qra_schedule_source_assessments", "qra_model_definitions", "qra_commands"}
AUTHORITIES = ("owner_capability_history_marker", "gate07j_history_marker", "fid_history_marker")


def _round_trip(url):
    engine = create_engine(url)
    try:
        assert inspect(engine).get_table_names() == [], "An empty disposable migration database is mandatory"
        metadata = MetaData()
        for name in ("tenants", "enterprise_workspaces", "user_accounts", "admin_configurations", *AUTHORITIES):
            Table(name, metadata, Column("id", Integer, primary_key=True))
        imports = Table(
            "schedule_imports", metadata, Column("id", Integer, primary_key=True), Column("source", String(40))
        )
        version = Table("alembic_version", metadata, Column("version_num", String(32), primary_key=True))
        metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(version.insert().values(version_num=BEFORE))
            connection.execute(imports.insert().values(id=7001, source="historical-P6-XML"))
            for name in AUTHORITIES:
                connection.execute(text(f'INSERT INTO "{name}" (id) VALUES (7001)'))

        def verify(up):
            inspector = inspect(engine)
            present = set(inspector.get_table_names())
            assert TABLES.issubset(present) if up else not TABLES.intersection(present)
            assert ("source_metadata" in {c["name"] for c in inspector.get_columns("schedule_imports")}) is up
            with engine.connect() as connection:
                assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (AFTER if up else BEFORE)
                assert (
                    connection.scalar(text("SELECT source FROM schedule_imports WHERE id=7001")) == "historical-P6-XML"
                )
                for name in AUTHORITIES:
                    assert connection.scalar(text(f'SELECT count(*) FROM "{name}" WHERE id=7001')) == 1
                if up:
                    assert str(
                        connection.scalar(text("SELECT source_metadata FROM schedule_imports WHERE id=7001"))
                    ) in ("{}",)
            if up:
                for table in TABLES:
                    assert all(len(i["name"]) <= 63 for i in inspector.get_indexes(table))
                assert any(
                    "model_number" in u["column_names"] and "version" in u["column_names"]
                    for u in inspector.get_unique_constraints("qra_model_definitions")
                )
                assert any(
                    "idempotency_key" in u["column_names"] for u in inspector.get_unique_constraints("qra_commands")
                )
                for table in TABLES - {"qra_commands"}:
                    assert any("hash IS NOT NULL" in c["sqltext"] for c in inspector.get_check_constraints(table))

        _alembic(url, "upgrade", AFTER)
        verify(True)
        _alembic(url, "downgrade", BEFORE)
        verify(False)
        _alembic(url, "upgrade", AFTER)
        verify(True)
    finally:
        engine.dispose()


def test_qra_sqlite_upgrade_downgrade_upgrade(tmp_path):
    _round_trip(f"sqlite:///{(tmp_path / 'qra-migration.sqlite').as_posix()}")


def test_qra_postgres_upgrade_downgrade_upgrade():
    url = os.getenv("PYPMIS_QRA_MIGRATION_DATABASE_URL", "").strip()
    if not url.startswith("postgresql+"):
        pytest.skip("Disposable QRA PostgreSQL migration URL is required")
    assert create_engine(url).url.database == "qra_foundation_migration", "Proof restricted to qra_foundation_migration"
    _round_trip(url)
