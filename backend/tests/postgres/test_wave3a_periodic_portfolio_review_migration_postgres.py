"""Disposable PostgreSQL up/down/up proof for the additive 0063 -> 0064."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect, text

REVISION_BEFORE = "20261001_0063"
REVISION_AFTER = "20261005_0064"
BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL = os.getenv("PYPMIS_WAVE3A_MIGRATION_DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DATABASE_URL.startswith("postgresql+"),
    reason="Disposable PostgreSQL Wave 3A migration URL is required",
)

TABLES = {
    "portfolio_review_sessions",
    "portfolio_review_snapshots",
    "portfolio_review_conclusions",
    "portfolio_review_actions",
    "portfolio_review_commands",
}


def _run_alembic(*arguments: str):
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


def _create_0063_dependency_surface():
    """Only the previous revision's FK surface; never modify a developer DB."""
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
            "strategic_capital_allocation_plans",
            "portfolio_project_memberships",
            "investment_decisions",
        ):
            Table(name, metadata, Column("id", Integer, primary_key=True))
        version = Table("alembic_version", metadata, Column("version_num", String(32), primary_key=True))
        metadata.create_all(engine)
        with engine.begin() as connection:
            for name in ("strategic_capital_allocation_plans", "portfolio_project_memberships", "investment_decisions"):
                connection.execute(text(f'INSERT INTO "{name}" (id) VALUES (7001)'))
            connection.execute(version.insert().values(version_num=REVISION_BEFORE))
    finally:
        engine.dispose()


def _revision(connection):
    return str(connection.scalar(text("SELECT version_num FROM alembic_version")))


def _assert_prior_authorities_preserved(connection):
    for name in ("strategic_capital_allocation_plans", "portfolio_project_memberships", "investment_decisions"):
        assert connection.scalar(text(f'SELECT count(*) FROM "{name}" WHERE id = 7001')) == 1


def _assert_upgrade_shape(connection):
    inspector = inspect(connection)
    assert _revision(connection) == REVISION_AFTER
    assert TABLES.issubset(inspector.get_table_names())
    assert all(len(item["name"]) <= 63 for table in TABLES for item in inspector.get_indexes(table))
    session_columns = {item["name"]: item for item in inspector.get_columns("portfolio_review_sessions")}
    assert session_columns["allocation_plan_id"]["nullable"] is True
    assert session_columns["planning_cycle_id"]["nullable"] is True
    assert session_columns["current_snapshot_id"]["nullable"] is True
    assert session_columns["completion_snapshot_json"]["nullable"] is False
    snapshot_columns = {item["name"]: item for item in inspector.get_columns("portfolio_review_snapshots")}
    assert snapshot_columns["snapshot_json"]["nullable"] is False
    assert snapshot_columns["source_index_json"]["nullable"] is False
    assert {"ix_portfolio_review_queue", "ix_portfolio_review_history"}.issubset(
        {item["name"] for item in inspector.get_indexes("portfolio_review_sessions")}
    )
    assert "ck_portfolio_review_completed" in {
        item["name"] for item in inspector.get_check_constraints("portfolio_review_sessions")
    }
    _assert_prior_authorities_preserved(connection)


def test_wave3a_periodic_portfolio_review_postgres_upgrade_downgrade_upgrade():
    _create_0063_dependency_surface()
    _run_alembic("upgrade", REVISION_AFTER)
    engine = create_engine(DATABASE_URL)
    try:
        with engine.connect() as connection:
            _assert_upgrade_shape(connection)
        _run_alembic("downgrade", REVISION_BEFORE)
        with engine.connect() as connection:
            assert _revision(connection) == REVISION_BEFORE
            assert not TABLES.intersection(inspect(connection).get_table_names())
            _assert_prior_authorities_preserved(connection)
        _run_alembic("upgrade", REVISION_AFTER)
        with engine.connect() as connection:
            _assert_upgrade_shape(connection)
    finally:
        engine.dispose()
