"""Isolated SQLite proof for the additive Gate 07A-BA migration.

The repository's earliest migrations predate SQLite batch-mode support, so this
test deliberately builds the immediate 0058 dependency surface and exercises
the new migration itself through Alembic's real command path.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect, text

REVISION_BEFORE = "20260902_0058"
REVISION_AFTER = "20260910_0059"
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


def _create_0058_dependency_surface(database_url: str) -> None:
    engine = create_engine(database_url)
    metadata = MetaData()
    for table_name in (
        "tenants",
        "ideas",
        "idea_evaluations",
        "enterprise_workspaces",
        "admin_configurations",
        "user_accounts",
        "project_proposals",
    ):
        Table(table_name, metadata, Column("id", Integer, primary_key=True))
    version = Table("alembic_version", metadata, Column("version_num", String(32), primary_key=True))
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(version.insert().values(version_num=REVISION_BEFORE))
    engine.dispose()


def _revision(connection) -> str:
    return str(connection.scalar(text("SELECT version_num FROM alembic_version")))


def test_gate07a_ba_sqlite_upgrade_downgrade_upgrade(tmp_path: Path) -> None:
    database_path = tmp_path / "gate07a_ba_migration.sqlite"
    database_url = f"sqlite:///{database_path.as_posix()}"
    _create_0058_dependency_surface(database_url)

    _run_alembic(database_url, "upgrade", REVISION_AFTER)
    engine = create_engine(database_url)
    with engine.connect() as connection:
        inspector = inspect(connection)
        assert _revision(connection) == REVISION_AFTER
        assert {"business_analyses", "business_analysis_revisions"}.issubset(inspector.get_table_names())
        proposal_columns = {item["name"]: item for item in inspector.get_columns("project_proposals")}
        lineage_columns = {
            "source_business_analysis_id",
            "source_business_analysis_hash",
            "business_analysis_configuration_id",
            "business_analysis_configuration_revision",
            "business_analysis_configuration_hash",
        }
        assert lineage_columns.issubset(proposal_columns)
        assert all(proposal_columns[column]["nullable"] for column in lineage_columns)
        proposal_indexes = {item["name"] for item in inspector.get_indexes("project_proposals")}
        assert "ix_project_proposals_source_business_analysis_id" in proposal_indexes
        analysis_uniques = {item["name"] for item in inspector.get_unique_constraints("business_analyses")}
        assert {
            "uq_business_analysis_tenant_number",
            "uq_business_analysis_idempotency",
        }.issubset(analysis_uniques)
        analysis_foreign_keys = {item["referred_table"] for item in inspector.get_foreign_keys("business_analyses")}
        assert {
            "tenants",
            "ideas",
            "idea_evaluations",
            "enterprise_workspaces",
            "admin_configurations",
            "user_accounts",
            "business_analyses",
        }.issubset(analysis_foreign_keys)
        revision_uniques = {item["name"] for item in inspector.get_unique_constraints("business_analysis_revisions")}
        assert "uq_business_analysis_revision_number" in revision_uniques

    _run_alembic(database_url, "downgrade", REVISION_BEFORE)
    with engine.connect() as connection:
        inspector = inspect(connection)
        assert _revision(connection) == REVISION_BEFORE
        assert {"business_analyses", "business_analysis_revisions"}.isdisjoint(inspector.get_table_names())
        proposal_columns = {item["name"] for item in inspector.get_columns("project_proposals")}
        assert not {item for item in proposal_columns if "business_analysis" in item}

    _run_alembic(database_url, "upgrade", REVISION_AFTER)
    with engine.connect() as connection:
        inspector = inspect(connection)
        assert _revision(connection) == REVISION_AFTER
        assert {"business_analyses", "business_analysis_revisions"}.issubset(inspector.get_table_names())
    engine.dispose()
