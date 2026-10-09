"""Real additive Owner Capability up/down/up, preserving authority markers."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect, text

BEFORE = "20261008_0065"
AFTER = "20261008_0066"
ROOT = Path(__file__).resolve().parents[2]
TABLES = {"owner_capability_assessments", "owner_capability_commands"}
AUTHORITIES = (
    "project_fel_status",
    "risk_readiness_history_marker",
    "basic_data_history_marker",
    "commercial_history_marker",
    "resource_history_marker",
    "investment_decision_history_marker",
)


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
        assert inspect(engine).get_table_names() == [], "An empty disposable migration database is mandatory"
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
                completed = inspector.get_check_constraints("owner_capability_assessments")
                assert any(
                    "COMPLETED" in item["sqltext"] and "assessment_hash" in item["sqltext"] for item in completed
                )
                assert any(
                    "idempotency_key" in item["column_names"]
                    for item in inspector.get_unique_constraints("owner_capability_commands")
                )

        _alembic(url, "upgrade", AFTER)
        assert_shape(True)
        _alembic(url, "downgrade", BEFORE)
        assert_shape(False)
        _alembic(url, "upgrade", AFTER)
        assert_shape(True)
    finally:
        engine.dispose()


def test_wave3b_postgres_upgrade_downgrade_upgrade() -> None:
    url = os.getenv("PYPMIS_WAVE3B_MIGRATION_DATABASE_URL", "").strip()
    if not url.startswith("postgresql+"):
        pytest.skip("Disposable Wave 3B PostgreSQL migration URL is required")
    assert create_engine(url).url.database == "wave3b_migration", "Proof restricted to wave3b_migration"
    verify_round_trip(url)
