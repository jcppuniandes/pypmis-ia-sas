"""Isolated SQLite up/down/up proof for Gate 07M-BEN migration 0061."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect, text

REVISION_BEFORE = "20260915_0060"
REVISION_AFTER = "20260916_0061"
BACKEND_ROOT = Path(__file__).resolve().parents[1]
TABLES = {
    "strategic_benefits_plans",
    "strategic_benefits_plan_versions",
    "strategic_benefits",
    "strategic_benefit_version_snapshots",
    "strategic_benefit_measures",
}


def _run_alembic(database_url: str, *arguments: str) -> None:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(BACKEND_ROOT / "alembic.ini"), *arguments],
        cwd=BACKEND_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"


def _create_0060_dependency_surface(database_url: str) -> None:
    engine = create_engine(database_url)
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
    engine.dispose()


def _revision(connection) -> str:
    return str(connection.scalar(text("SELECT version_num FROM alembic_version")))


def _assert_0061_schema(connection) -> None:
    inspector = inspect(connection)
    assert _revision(connection) == REVISION_AFTER
    assert TABLES.issubset(inspector.get_table_names())

    plan_columns = {item["name"]: item for item in inspector.get_columns("strategic_benefits_plans")}
    assert {
        "project_workspace_id",
        "plan_number",
        "current_version_id",
        "configuration_hash",
        "configuration_resolution_chain_json",
        "create_idempotency_key",
        "revision_version",
    }.issubset(plan_columns)
    assert plan_columns["current_version_id"]["nullable"] is True
    assert {
        "uq_benefits_plan_project",
        "uq_benefits_plan_number",
        "uq_benefits_plan_create_key",
    }.issubset({item["name"] for item in inspector.get_unique_constraints("strategic_benefits_plans")})
    assert "ix_benefits_plan_queue" in {item["name"] for item in inspector.get_indexes("strategic_benefits_plans")}

    version_columns = {item["name"] for item in inspector.get_columns("strategic_benefits_plan_versions")}
    assert {
        "overview_json",
        "outputs_json",
        "outcomes_json",
        "readiness_json",
        "source_hashes_json",
        "source_bundle_hash",
        "benefit_set_hash",
        "traceability_hash",
        "benefits_plan_hash",
        "submit_idempotency_key",
        "review_idempotency_key",
        "complete_idempotency_key",
        "refresh_idempotency_key",
        "revision_version",
    }.issubset(version_columns)
    assert {
        "uq_benefits_plan_version",
        "uq_benefits_version_create_key",
        "uq_benefits_version_submit_key",
        "uq_benefits_version_review_key",
        "uq_benefits_version_return_key",
        "uq_benefits_version_complete_key",
        "uq_benefits_version_void_key",
        "uq_benefits_version_refresh_key",
    }.issubset({item["name"] for item in inspector.get_unique_constraints("strategic_benefits_plan_versions")})
    assert "ix_benefits_version_history" in {
        item["name"] for item in inspector.get_indexes("strategic_benefits_plan_versions")
    }

    benefit_columns = {item["name"] for item in inspector.get_columns("strategic_benefits")}
    assert {
        "benefits_plan_id",
        "benefit_number",
        "status",
        "create_idempotency_key",
        "revision_version",
    }.issubset(benefit_columns)
    assert {
        "uq_strategic_benefit_number",
        "uq_strategic_benefit_create_key",
    }.issubset({item["name"] for item in inspector.get_unique_constraints("strategic_benefits")})

    snapshot_columns = {item["name"] for item in inspector.get_columns("strategic_benefit_version_snapshots")}
    assert {
        "plan_version_id",
        "strategic_benefit_id",
        "strategic_objective_refs_json",
        "expected_outputs_json",
        "expected_outcomes_json",
        "owner_snapshot_json",
        "expected_value_json",
        "snapshot_hash",
        "revision_version",
    }.issubset(snapshot_columns)
    assert "uq_benefit_snapshot" in {
        item["name"] for item in inspector.get_unique_constraints("strategic_benefit_version_snapshots")
    }

    measure_columns = {item["name"]: item for item in inspector.get_columns("strategic_benefit_measures")}
    assert {
        "benefit_snapshot_id",
        "measure_code",
        "is_primary",
        "baseline_status",
        "baseline_value_json",
        "target_value_json",
        "target_date",
        "measure_hash",
        "create_idempotency_key",
        "revision_version",
    }.issubset(measure_columns)
    assert measure_columns["baseline_value_json"]["nullable"] is True
    assert {
        "uq_benefit_measure_code",
        "uq_benefit_measure_create_key",
    }.issubset({item["name"] for item in inspector.get_unique_constraints("strategic_benefit_measures")})

    assert {
        "ck_benefits_plan_status",
    }.issubset({item["name"] for item in inspector.get_check_constraints("strategic_benefits_plans")})
    assert {
        "ck_benefits_version_number",
        "ck_benefits_version_status",
        "ck_benefits_version_readiness",
    }.issubset({item["name"] for item in inspector.get_check_constraints("strategic_benefits_plan_versions")})
    assert "ck_benefit_baseline_status" in {
        item["name"] for item in inspector.get_check_constraints("strategic_benefit_measures")
    }


def test_gate07m_ben_sqlite_upgrade_downgrade_upgrade(tmp_path: Path) -> None:
    database_path = tmp_path / "gate07m_ben_migration.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    _create_0060_dependency_surface(database_url)

    _run_alembic(database_url, "upgrade", REVISION_AFTER)
    engine = create_engine(database_url)
    with engine.connect() as connection:
        _assert_0061_schema(connection)

    _run_alembic(database_url, "downgrade", REVISION_BEFORE)
    with engine.connect() as connection:
        inspector = inspect(connection)
        assert _revision(connection) == REVISION_BEFORE
        assert TABLES.isdisjoint(inspector.get_table_names())

    _run_alembic(database_url, "upgrade", REVISION_AFTER)
    with engine.connect() as connection:
        _assert_0061_schema(connection)
    engine.dispose()
