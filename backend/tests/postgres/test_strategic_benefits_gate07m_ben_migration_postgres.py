"""Real PostgreSQL up/down/up proof for Gate 07M-BEN migration 0061.

The configured URL must point to a disposable, empty database. The guard
refuses to alter a database that already contains tables.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect, text

REVISION_BEFORE = "20260915_0060"
REVISION_AFTER = "20260916_0061"
BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL = os.getenv("PYPMIS_GATE07M_BEN_MIGRATION_DATABASE_URL", "").strip()
TABLES = {
    "strategic_benefits_plans",
    "strategic_benefits_plan_versions",
    "strategic_benefits",
    "strategic_benefit_version_snapshots",
    "strategic_benefit_measures",
}

pytestmark = pytest.mark.skipif(
    not DATABASE_URL.startswith("postgresql+"),
    reason="Disposable PostgreSQL Gate 07M-BEN migration URL is required",
)


def _run_alembic(*arguments: str) -> None:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = DATABASE_URL
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(BACKEND_ROOT / "alembic.ini"), *arguments],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


def _create_0060_dependency_surface() -> None:
    engine = create_engine(DATABASE_URL)
    try:
        assert inspect(engine).get_table_names() == [], "Migration proof requires an empty disposable database"
        metadata = MetaData()
        for table_name in (
            "tenants",
            "enterprise_workspaces",
            "admin_configurations",
            "user_accounts",
            "organization_units",
            "security_roles",
        ):
            Table(table_name, metadata, Column("id", Integer, primary_key=True))
        version = Table("alembic_version", metadata, Column("version_num", String(32), primary_key=True))
        metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(version.insert().values(version_num=REVISION_BEFORE))
    finally:
        engine.dispose()


def _revision(connection) -> str:
    return str(connection.scalar(text("SELECT version_num FROM alembic_version")))


def _assert_0061_schema(connection) -> None:
    inspector = inspect(connection)
    assert _revision(connection) == REVISION_AFTER
    assert TABLES.issubset(inspector.get_table_names())
    assert {
        "uq_benefits_plan_project",
        "uq_benefits_plan_number",
        "uq_benefits_plan_create_key",
    }.issubset({item["name"] for item in inspector.get_unique_constraints("strategic_benefits_plans")})
    assert {
        "uq_benefits_plan_version",
        "uq_benefits_version_submit_key",
        "uq_benefits_version_complete_key",
        "uq_benefits_version_refresh_key",
    }.issubset({item["name"] for item in inspector.get_unique_constraints("strategic_benefits_plan_versions")})
    assert "uq_benefit_snapshot" in {
        item["name"] for item in inspector.get_unique_constraints("strategic_benefit_version_snapshots")
    }
    assert "uq_benefit_measure_code" in {
        item["name"] for item in inspector.get_unique_constraints("strategic_benefit_measures")
    }
    assert inspect(connection).get_columns("strategic_benefit_measures")
    baseline = next(
        item for item in inspector.get_columns("strategic_benefit_measures") if item["name"] == "baseline_value_json"
    )
    assert baseline["nullable"] is True


def test_gate07m_ben_postgres_upgrade_downgrade_upgrade() -> None:
    _create_0060_dependency_surface()
    _run_alembic("upgrade", REVISION_AFTER)
    engine = create_engine(DATABASE_URL)
    try:
        with engine.connect() as connection:
            _assert_0061_schema(connection)

        _run_alembic("downgrade", REVISION_BEFORE)
        with engine.connect() as connection:
            inspector = inspect(connection)
            assert _revision(connection) == REVISION_BEFORE
            assert TABLES.isdisjoint(inspector.get_table_names())

        _run_alembic("upgrade", REVISION_AFTER)
        with engine.connect() as connection:
            _assert_0061_schema(connection)
    finally:
        engine.dispose()
