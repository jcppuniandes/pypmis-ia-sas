"""Isolated SQLite up/down/up proof for Gate 07M-COMM migration 0060."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect, text

REVISION_BEFORE = "20260910_0059"
REVISION_AFTER = "20260915_0060"
BACKEND_ROOT = Path(__file__).resolve().parents[1]


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


def _create_0059_dependency_surface(database_url: str) -> None:
    engine = create_engine(database_url)
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

    strategy_columns = {item["name"]: item for item in inspector.get_columns("commercial_contracting_strategies")}
    assert {
        "project_workspace_id",
        "current_version_id",
        "configuration_hash",
        "configuration_resolution_chain_json",
        "create_idempotency_key",
        "revision_version",
    }.issubset(strategy_columns)
    assert strategy_columns["current_version_id"]["nullable"] is True
    strategy_uniques = {item["name"] for item in inspector.get_unique_constraints("commercial_contracting_strategies")}
    assert {
        "uq_commercial_strategy_project",
        "uq_commercial_strategy_number",
        "uq_commercial_strategy_create_key",
    }.issubset(strategy_uniques)
    strategy_foreign_tables = {
        item["referred_table"] for item in inspector.get_foreign_keys("commercial_contracting_strategies")
    }
    assert {
        "tenants",
        "enterprise_workspaces",
        "admin_configurations",
        "user_accounts",
    }.issubset(strategy_foreign_tables)
    strategy_indexes = {item["name"] for item in inspector.get_indexes("commercial_contracting_strategies")}
    assert "ix_commercial_strategy_queue" in strategy_indexes
    assert "ck_commercial_strategy_status" in {
        item["name"] for item in inspector.get_check_constraints("commercial_contracting_strategies")
    }

    version_columns = {item["name"] for item in inspector.get_columns("commercial_strategy_versions")}
    assert {
        "content_json",
        "readiness_json",
        "source_hashes_json",
        "source_bundle_hash",
        "commercial_strategy_hash",
        "submit_idempotency_key",
        "review_idempotency_key",
        "complete_idempotency_key",
        "refresh_idempotency_key",
        "revision_version",
    }.issubset(version_columns)
    version_uniques = {item["name"] for item in inspector.get_unique_constraints("commercial_strategy_versions")}
    assert {
        "uq_commercial_strategy_version",
        "uq_commercial_version_create_key",
        "uq_commercial_version_submit_key",
        "uq_commercial_version_review_key",
        "uq_commercial_version_return_key",
        "uq_commercial_version_complete_key",
        "uq_commercial_version_void_key",
        "uq_commercial_version_refresh_key",
    }.issubset(version_uniques)
    version_foreign_tables = {
        item["referred_table"] for item in inspector.get_foreign_keys("commercial_strategy_versions")
    }
    assert {
        "commercial_contracting_strategies",
        "tenants",
        "admin_configurations",
        "user_accounts",
    }.issubset(version_foreign_tables)
    version_indexes = {item["name"] for item in inspector.get_indexes("commercial_strategy_versions")}
    assert "ix_commercial_version_history" in version_indexes
    assert {
        "ck_commercial_version_number",
        "ck_commercial_version_status",
        "ck_commercial_version_readiness",
    }.issubset({item["name"] for item in inspector.get_check_constraints("commercial_strategy_versions")})


def test_gate07m_comm_sqlite_upgrade_downgrade_upgrade(tmp_path: Path) -> None:
    database_path = tmp_path / "gate07m_comm_migration.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    _create_0059_dependency_surface(database_url)

    _run_alembic(database_url, "upgrade", REVISION_AFTER)
    engine = create_engine(database_url)
    with engine.connect() as connection:
        _assert_0060_schema(connection)

    _run_alembic(database_url, "downgrade", REVISION_BEFORE)
    with engine.connect() as connection:
        inspector = inspect(connection)
        assert _revision(connection) == REVISION_BEFORE
        assert {
            "commercial_contracting_strategies",
            "commercial_strategy_versions",
        }.isdisjoint(inspector.get_table_names())

    _run_alembic(database_url, "upgrade", REVISION_AFTER)
    with engine.connect() as connection:
        _assert_0060_schema(connection)
    engine.dispose()
