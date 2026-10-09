"""PostgreSQL up/down/up proof for the additive Wave 1 migration.

The historical Alembic chain starts after the original SQLAlchemy-managed
schema, so a new empty database cannot replay revision 0001 directly. This
test creates only the dependency surface that exists at revision 0061, stamps
that baseline, and then exercises revision 0062 in both directions.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect, select, text

REVISION_BEFORE = "20260916_0061"
REVISION_AFTER = "20260929_0062"
BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL = os.getenv("PYPMIS_WAVE1_MIGRATION_DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DATABASE_URL.startswith("postgresql+"),
    reason="Disposable PostgreSQL Wave 1 migration URL is required",
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


def _create_0061_dependency_surface() -> None:
    engine = create_engine(DATABASE_URL)
    try:
        assert inspect(engine).get_table_names() == [], "Migration proof requires an empty disposable database"
        metadata = MetaData()
        Table("tenants", metadata, Column("id", Integer, primary_key=True))
        Table("enterprise_workspaces", metadata, Column("id", Integer, primary_key=True))
        Table("user_accounts", metadata, Column("id", Integer, primary_key=True))
        ideas = Table("ideas", metadata, Column("id", Integer, primary_key=True))
        version = Table("alembic_version", metadata, Column("version_num", String(32), primary_key=True))
        metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(ideas.insert().values(id=7001))
            connection.execute(version.insert().values(version_num=REVISION_BEFORE))
    finally:
        engine.dispose()


def _revision(connection) -> str:
    return str(connection.scalar(text("SELECT version_num FROM alembic_version")))


def _assert_upgrade_shape(connection) -> None:
    inspector = inspect(connection)
    assert _revision(connection) == REVISION_AFTER
    assert {
        "capital_planning_cycles",
        "capital_planning_cycle_themes",
        "strategic_capital_demands",
        "strategic_capital_demand_themes",
        "strategic_capital_demand_objectives",
        "capital_demand_idea_origins",
    }.issubset(inspector.get_table_names())

    idea_columns = {item["name"]: item for item in inspector.get_columns("ideas")}
    assert idea_columns["source_capital_demand_id"]["nullable"] is True
    assert idea_columns["source_capital_demand_snapshot_hash"]["nullable"] is True
    historical = connection.execute(
        select(
            text("source_capital_demand_id"),
            text("source_capital_demand_snapshot_hash"),
        )
        .select_from(text("ideas"))
        .where(text("id = 7001"))
    ).one()
    assert historical == (None, None)

    demand_indexes = {item["name"] for item in inspector.get_indexes("strategic_capital_demands")}
    assert {
        "ix_strategic_capital_demand_queue",
        "ix_strategic_capital_demand_cycle_status",
        "ix_strategic_capital_demands_tenant_id",
        "ix_strategic_capital_demands_status",
    }.issubset(demand_indexes)


def test_wave1_capital_planning_postgres_upgrade_downgrade_upgrade() -> None:
    _create_0061_dependency_surface()
    _run_alembic("upgrade", REVISION_AFTER)
    engine = create_engine(DATABASE_URL)
    try:
        with engine.connect() as connection:
            _assert_upgrade_shape(connection)

        _run_alembic("downgrade", REVISION_BEFORE)
        with engine.connect() as connection:
            inspector = inspect(connection)
            assert _revision(connection) == REVISION_BEFORE
            assert not {
                "capital_planning_cycles",
                "capital_planning_cycle_themes",
                "strategic_capital_demands",
                "strategic_capital_demand_themes",
                "strategic_capital_demand_objectives",
                "capital_demand_idea_origins",
            }.intersection(inspector.get_table_names())
            idea_columns = {item["name"] for item in inspector.get_columns("ideas")}
            assert "source_capital_demand_id" not in idea_columns
            assert "source_capital_demand_snapshot_hash" not in idea_columns
            assert connection.scalar(text("SELECT count(*) FROM ideas WHERE id = 7001")) == 1

        _run_alembic("upgrade", REVISION_AFTER)
        with engine.connect() as connection:
            _assert_upgrade_shape(connection)
    finally:
        engine.dispose()
