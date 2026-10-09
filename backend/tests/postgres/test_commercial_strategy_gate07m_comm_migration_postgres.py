"""Real PostgreSQL up/down/up proof for Gate 07M-COMM migration 0060.

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

REVISION_BEFORE = "20260910_0059"
REVISION_AFTER = "20260915_0060"
BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL = os.getenv("PYPMIS_GATE07M_COMM_MIGRATION_DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DATABASE_URL.startswith("postgresql+"),
    reason="Disposable PostgreSQL Gate 07M-COMM migration URL is required",
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


def _create_0059_dependency_surface() -> None:
    engine = create_engine(DATABASE_URL)
    try:
        assert inspect(engine).get_table_names() == [], "Migration proof requires an empty disposable database"
        metadata = MetaData()
        for table_name in (
            "tenants",
            "enterprise_workspaces",
            "admin_configurations",
            "user_accounts",
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


def _assert_0060_schema(connection) -> None:
    inspector = inspect(connection)
    assert _revision(connection) == REVISION_AFTER
    assert {
        "commercial_contracting_strategies",
        "commercial_strategy_versions",
    }.issubset(inspector.get_table_names())
    strategy_uniques = {item["name"] for item in inspector.get_unique_constraints("commercial_contracting_strategies")}
    assert {
        "uq_commercial_strategy_project",
        "uq_commercial_strategy_number",
        "uq_commercial_strategy_create_key",
    }.issubset(strategy_uniques)
    version_uniques = {item["name"] for item in inspector.get_unique_constraints("commercial_strategy_versions")}
    assert {
        "uq_commercial_strategy_version",
        "uq_commercial_version_submit_key",
        "uq_commercial_version_complete_key",
        "uq_commercial_version_refresh_key",
    }.issubset(version_uniques)
    version_foreign_tables = {
        item["referred_table"] for item in inspector.get_foreign_keys("commercial_strategy_versions")
    }
    assert "commercial_contracting_strategies" in version_foreign_tables
    assert "ix_commercial_version_history" in {
        item["name"] for item in inspector.get_indexes("commercial_strategy_versions")
    }
    assert {
        "ck_commercial_version_number",
        "ck_commercial_version_status",
        "ck_commercial_version_readiness",
    }.issubset({item["name"] for item in inspector.get_check_constraints("commercial_strategy_versions")})


def test_gate07m_comm_postgres_upgrade_downgrade_upgrade() -> None:
    _create_0059_dependency_surface()
    _run_alembic("upgrade", REVISION_AFTER)
    engine = create_engine(DATABASE_URL)
    try:
        with engine.connect() as connection:
            _assert_0060_schema(connection)

        _run_alembic("downgrade", REVISION_BEFORE)
        with engine.connect() as connection:
            inspector = inspect(connection)
            assert _revision(connection) == REVISION_BEFORE
            assert {
                "commercial_contracting_strategies",
                "commercial_strategy_versions",
            }.isdisjoint(inspector.get_table_names())

        _run_alembic("upgrade", REVISION_AFTER)
        with engine.connect() as connection:
            _assert_0060_schema(connection)
    finally:
        engine.dispose()
