"""Wave4 additive migration round trips only in disposable databases."""

import os

import pytest
from sqlalchemy import JSON, Column, Integer, MetaData, String, Table, create_engine, inspect, text
from sqlalchemy.exc import DBAPIError
from tests.postgres.test_wave3b_migration_postgres import _alembic

BEFORE, AFTER = "20261009_0067", "20261011_0068"
NEW_TABLES = {"qra_runs", "qra_run_reviews"}


def _round_trip(url):
    engine = create_engine(url)
    metadata = MetaData()
    owned = False
    try:
        assert inspect(engine).get_table_names() == [], "Empty disposable migration database required"
        owned = True
        for name in ("tenants", "enterprise_workspaces", "user_accounts", "admin_configurations"):
            Table(name, metadata, Column("id", Integer, primary_key=True))
        history = Table(
            "qra_model_definitions",
            metadata,
            Column("id", Integer, primary_key=True),
            Column("historical_hash", String(64)),
            Column("snapshot_json", JSON),
        )
        marker = Table("fid_budget_schedule_history_marker", metadata, Column("id", Integer, primary_key=True))
        version = Table("alembic_version", metadata, Column("version_num", String(32), primary_key=True))
        metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(version.insert().values(version_num=BEFORE))
            for name in ("tenants", "enterprise_workspaces", "user_accounts", "admin_configurations"):
                connection.execute(metadata.tables[name].insert().values(id=7001))
            connection.execute(
                history.insert().values(id=7001, historical_hash="f" * 64, snapshot_json={"historical": True})
            )
            connection.execute(marker.insert().values(id=7001))

        def verify(up):
            inspector = inspect(engine)
            present = set(inspector.get_table_names())
            assert NEW_TABLES.issubset(present) if up else not NEW_TABLES.intersection(present)
            with engine.connect() as connection:
                assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (AFTER if up else BEFORE)
                assert (
                    connection.scalar(text("SELECT historical_hash FROM qra_model_definitions WHERE id=7001"))
                    == "f" * 64
                )
                assert connection.scalar(text("SELECT count(*) FROM fid_budget_schedule_history_marker")) == 1
            if up:
                assert any(
                    "run_number" in constraint["column_names"]
                    for constraint in inspector.get_unique_constraints("qra_runs")
                )
                assert any(
                    "iterations_completed" in constraint["sqltext"]
                    for constraint in inspector.get_check_constraints("qra_runs")
                )
                assert any(
                    "accepted_by" in constraint["sqltext"]
                    for constraint in inspector.get_check_constraints("qra_run_reviews")
                )

        _alembic(url, "upgrade", AFTER)
        verify(True)
        # Migration-installed DB guards also prevent bulk SQL/ORM bypasses.
        table = Table("qra_runs", MetaData(), autoload_with=engine)
        payload = {
            "id": 7001,
            "tenant_id": 7001,
            "project_workspace_id": 7001,
            "run_number": "QRR-7001",
            "model_definition_id": 7001,
            "model_number": "QRM-7001",
            "model_version": 1,
            "model_hash": "a" * 64,
            "analysis_type": "COST_QRA",
            "engine_name": "PPMIS_QRA_ENGINE",
            "engine_version": "wave4-qra-v1",
            "formula_version": "v1",
            "configuration_id": 7001,
            "configuration_revision": 1,
            "configuration_hash": "b" * 64,
            "seed": "7",
            "iterations_requested": 100,
            "iterations_completed": 0,
            "input_snapshot_hash": "c" * 64,
            "input_snapshot_json": {"frozen": True},
            "title": "Migration guard proof",
            "created_by": 7001,
        }
        from datetime import datetime

        payload.update(created_at=datetime(2026, 10, 11), updated_at=datetime(2026, 10, 11))
        with engine.begin() as connection:
            connection.execute(table.insert().values(**payload))
        for statement in ("UPDATE qra_runs SET seed='8' WHERE id=7001", "DELETE FROM qra_runs WHERE id=7001"):
            with pytest.raises(DBAPIError):
                with engine.begin() as connection:
                    connection.execute(text(statement))
        with engine.begin() as connection:
            connection.execute(
                table.update()
                .where(table.c.id == 7001)
                .values(
                    status="COMPLETED",
                    iterations_completed=100,
                    result_snapshot_hash="d" * 64,
                    trace_hash="e" * 64,
                    completed_at=datetime(2026, 10, 11),
                )
            )
        with pytest.raises(DBAPIError):
            with engine.begin() as connection:
                connection.execute(text("UPDATE qra_runs SET result_json='{}' WHERE id=7001"))
        reviews = Table("qra_run_reviews", MetaData(), autoload_with=engine)
        with engine.begin() as connection:
            connection.execute(
                reviews.insert().values(
                    id=7001,
                    tenant_id=7001,
                    run_id=7001,
                    reviewed_by=7001,
                    reviewed_at=datetime(2026, 10, 11),
                    status="ACCEPTED",
                    accepted_by=7001,
                    accepted_at=datetime(2026, 10, 11),
                    acceptance_hash="a" * 64,
                )
            )
        for statement in (
            "UPDATE qra_run_reviews SET acceptance_comments='rewrite' WHERE id=7001",
            "DELETE FROM qra_run_reviews WHERE id=7001",
        ):
            with pytest.raises(DBAPIError):
                with engine.begin() as connection:
                    connection.execute(text(statement))
        _alembic(url, "downgrade", BEFORE)
        verify(False)
        _alembic(url, "upgrade", AFTER)
        verify(True)
    finally:
        # All targets were created after asserting the isolated database empty.
        if owned:
            if NEW_TABLES.issubset(set(inspect(engine).get_table_names())):
                _alembic(url, "downgrade", BEFORE)
            metadata.drop_all(engine)
        engine.dispose()


def test_qra_engine_sqlite_upgrade_downgrade_upgrade(tmp_path):
    _round_trip(f"sqlite:///{(tmp_path / 'qra-engine.sqlite').as_posix()}")


def test_qra_engine_postgres_upgrade_downgrade_upgrade():
    url = os.getenv("PYPMIS_QRA_ENGINE_MIGRATION_DATABASE_URL", "")
    if not url.startswith("postgresql+"):
        pytest.skip("Disposable QRA Engine PostgreSQL migration URL required")
    assert create_engine(url).url.database == "qra_engine_migration"
    _round_trip(url)
