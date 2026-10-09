"""Real PostgreSQL up/down/up proof for the additive Gate 07A-BA migration.

The target URL must identify a disposable, empty database created solely for
this test. The guard deliberately refuses to touch a database with any tables.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect, text

REVISION_BEFORE = "20260902_0058"
REVISION_AFTER = "20260910_0059"
BACKEND_ROOT = Path(__file__).resolve().parents[2]
DATABASE_URL = os.getenv("PYPMIS_GATE07A_MIGRATION_DATABASE_URL", "").strip()

pytestmark = pytest.mark.skipif(
    not DATABASE_URL.startswith("postgresql+"),
    reason="Disposable PostgreSQL migration URL is required",
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


def _create_0058_dependency_surface() -> None:
    engine = create_engine(DATABASE_URL)
    try:
        assert inspect(engine).get_table_names() == [], "Migration proof requires an empty disposable database"
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
    finally:
        engine.dispose()


def _revision(connection) -> str:
    return str(connection.scalar(text("SELECT version_num FROM alembic_version")))


def test_gate07a_ba_postgres_upgrade_downgrade_upgrade() -> None:
    _create_0058_dependency_surface()
    _run_alembic("upgrade", REVISION_AFTER)
    engine = create_engine(DATABASE_URL)
    try:
        with engine.connect() as connection:
            inspector = inspect(connection)
            assert _revision(connection) == REVISION_AFTER
            assert {"business_analyses", "business_analysis_revisions"}.issubset(inspector.get_table_names())
            proposal_foreign_keys = {item["name"] for item in inspector.get_foreign_keys("project_proposals")}
            assert {
                "fk_project_proposals_business_analysis",
                "fk_project_proposals_business_analysis_configuration",
            }.issubset(proposal_foreign_keys)

        _run_alembic("downgrade", REVISION_BEFORE)
        with engine.connect() as connection:
            inspector = inspect(connection)
            assert _revision(connection) == REVISION_BEFORE
            assert {"business_analyses", "business_analysis_revisions"}.isdisjoint(inspector.get_table_names())
            assert not {
                item["name"]
                for item in inspector.get_columns("project_proposals")
                if "business_analysis" in item["name"]
            }

        _run_alembic("upgrade", REVISION_AFTER)
        with engine.connect() as connection:
            inspector = inspect(connection)
            assert _revision(connection) == REVISION_AFTER
            assert {"business_analyses", "business_analysis_revisions"}.issubset(inspector.get_table_names())
    finally:
        engine.dispose()
