"""Real additive 0064/0065 up/down/up proof on an isolated FK surface."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect, text

BEFORE = "20261005_0064"
AFTER = "20261008_0065"
ROOT = Path(__file__).resolve().parents[2]
TABLES = {"project_basic_data_items", "basic_data_readiness_assessments", "basic_data_commands"}
AUTHORITIES = ("project_fel_status", "risk_readiness_history_marker", "investment_decision_history_marker")


def _alembic(url: str, *arguments: str) -> None:
    environment = {**os.environ, "DATABASE_URL": url, "AUTO_CREATE_SCHEMA": "false", "SEED_DEMO_DATA": "false"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ROOT / "alembic.ini"), *arguments],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


def verify_round_trip(url: str) -> None:
    engine = create_engine(url)
    try:
        assert inspect(engine).get_table_names() == [], "Use an empty disposable database, never a developer database"
        metadata = MetaData()
        for name in ("tenants", "enterprise_workspaces", "user_accounts", "admin_configurations", *AUTHORITIES):
            Table(name, metadata, Column("id", Integer, primary_key=True))
        version = Table("alembic_version", metadata, Column("version_num", String(32), primary_key=True))
        metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(version.insert().values(version_num=BEFORE))
            for name in AUTHORITIES:
                connection.execute(text(f'INSERT INTO "{name}" (id) VALUES (7001)'))

        def assert_shape(upgraded: bool) -> None:
            inspector = inspect(engine)
            present = set(inspector.get_table_names())
            assert TABLES.issubset(present) if upgraded else not TABLES.intersection(present)
            with engine.connect() as connection:
                assert connection.scalar(text("SELECT version_num FROM alembic_version")) == (
                    AFTER if upgraded else BEFORE
                )
                for name in AUTHORITIES:
                    assert connection.scalar(text(f'SELECT count(*) FROM "{name}" WHERE id = 7001')) == 1
            if upgraded:
                for table in TABLES:
                    assert all(len(item["name"]) <= 63 for item in inspector.get_indexes(table))
                assert "uq_basic_data_project_requirement" in {
                    item["name"] for item in inspector.get_unique_constraints("project_basic_data_items")
                }
                assert "ck_basic_data_assessment_completed" in {
                    item["name"] for item in inspector.get_check_constraints("basic_data_readiness_assessments")
                }
                assert "uq_basic_data_command_key" in {
                    item["name"] for item in inspector.get_unique_constraints("basic_data_commands")
                }
                assert not any(name.startswith("risk_governance_") for name in present)

        _alembic(url, "upgrade", AFTER)
        assert_shape(True)
        _alembic(url, "downgrade", BEFORE)
        assert_shape(False)
        _alembic(url, "upgrade", AFTER)
        assert_shape(True)
    finally:
        engine.dispose()


def test_wave2b_postgres_upgrade_downgrade_upgrade() -> None:
    url = os.getenv("PYPMIS_WAVE2B_MIGRATION_DATABASE_URL", "").strip()
    if not url.startswith("postgresql+"):
        pytest.skip("Disposable Wave 2B PostgreSQL migration URL is required")
    assert create_engine(url).url.database == "wave2b_migration", "Migration proof is restricted to wave2b_migration"
    verify_round_trip(url)
