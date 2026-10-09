"""PostgreSQL up/down/up proof for the additive Wave 2A migration."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect, text

REVISION_BEFORE = "20260929_0062"
REVISION_AFTER = "20261001_0063"
BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL = os.getenv("PYPMIS_WAVE2A_MIGRATION_DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DATABASE_URL.startswith("postgresql+"),
    reason="Disposable PostgreSQL Wave 2A migration URL is required",
)

WAVE2A_TABLES = {
    "strategic_capital_allocation_plans",
    "strategic_capital_allocation_lines",
    "strategic_bucket_classifications",
    "strategic_capital_allocation_commands",
}


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


def _create_0062_dependency_surface() -> None:
    engine = create_engine(DATABASE_URL)
    try:
        assert inspect(engine).get_table_names() == [], "Migration proof requires an empty disposable database"
        metadata = MetaData()
        for name in (
            "tenants",
            "enterprise_workspaces",
            "user_accounts",
            "admin_configurations",
            "capital_planning_cycles",
            "strategic_capital_demands",
            "portfolio_project_memberships",
        ):
            Table(name, metadata, Column("id", Integer, primary_key=True))
        version = Table("alembic_version", metadata, Column("version_num", String(32), primary_key=True))
        metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(text("INSERT INTO strategic_capital_demands (id) VALUES (7001)"))
            connection.execute(version.insert().values(version_num=REVISION_BEFORE))
    finally:
        engine.dispose()


def _revision(connection) -> str:
    return str(connection.scalar(text("SELECT version_num FROM alembic_version")))


def _assert_upgrade_shape(connection) -> None:
    inspector = inspect(connection)
    assert _revision(connection) == REVISION_AFTER
    assert WAVE2A_TABLES.issubset(inspector.get_table_names())
    for table in WAVE2A_TABLES:
        assert all(len(item["name"]) <= 63 for item in inspector.get_indexes(table))

    plan_columns = {item["name"]: item for item in inspector.get_columns("strategic_capital_allocation_plans")}
    assert plan_columns["portfolio_workspace_id"]["nullable"] is True
    assert plan_columns["endorsed_snapshot_hash"]["nullable"] is True
    classification_columns = {item["name"]: item for item in inspector.get_columns("strategic_bucket_classifications")}
    assert classification_columns["capital_demand_id"]["nullable"] is True
    assert classification_columns["project_workspace_id"]["nullable"] is True
    assert classification_columns["portfolio_membership_id"]["nullable"] is True

    plan_indexes = {item["name"] for item in inspector.get_indexes("strategic_capital_allocation_plans")}
    assert {
        "ix_capital_allocation_plan_queue",
        "ix_capital_allocation_plan_cycle_scope",
        "uq_capital_allocation_plan_current_no_portfolio",
        "uq_capital_allocation_plan_current_portfolio",
    }.issubset(plan_indexes)
    classification_indexes = {item["name"] for item in inspector.get_indexes("strategic_bucket_classifications")}
    assert {
        "uq_strategic_bucket_classification_demand",
        "uq_strategic_bucket_classification_project",
        "uq_strategic_bucket_classification_membership",
    }.issubset(classification_indexes)
    assert connection.scalar(text("SELECT count(*) FROM strategic_capital_demands WHERE id = 7001")) == 1


def test_wave2a_strategic_capital_allocation_postgres_upgrade_downgrade_upgrade() -> None:
    _create_0062_dependency_surface()
    _run_alembic("upgrade", REVISION_AFTER)
    engine = create_engine(DATABASE_URL)
    try:
        with engine.connect() as connection:
            _assert_upgrade_shape(connection)

        _run_alembic("downgrade", REVISION_BEFORE)
        with engine.connect() as connection:
            inspector = inspect(connection)
            assert _revision(connection) == REVISION_BEFORE
            assert not WAVE2A_TABLES.intersection(inspector.get_table_names())
            assert connection.scalar(text("SELECT count(*) FROM strategic_capital_demands WHERE id = 7001")) == 1

        _run_alembic("upgrade", REVISION_AFTER)
        with engine.connect() as connection:
            _assert_upgrade_shape(connection)
    finally:
        engine.dispose()
