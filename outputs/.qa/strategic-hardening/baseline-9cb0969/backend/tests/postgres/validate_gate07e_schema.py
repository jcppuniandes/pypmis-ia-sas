"""Validate the additive/reversible Gate 07E PostgreSQL migration."""

from __future__ import annotations

import argparse

from sqlalchemy import inspect, text

from app.database.session import engine

EXPECTED_COLUMNS = {
    "tenant_id",
    "portfolio_workspace_id",
    "project_workspace_id",
    "portfolio_membership_id",
    "evaluation_version",
    "status",
    "matrix_configuration_id",
    "matrix_revision",
    "matrix_hash",
    "matrix_snapshot_json",
    "source_snapshot_json",
    "source_snapshot_hash",
    "planning_entry_hash",
    "ratings_json",
    "score_components_json",
    "normalized_score",
    "strategic_alignment_score",
    "risk_score",
    "start_idempotency_key",
    "complete_idempotency_key",
    "reevaluation_idempotency_key",
    "revision_version",
}


def validate(expected_revision: str) -> None:
    if engine.dialect.name != "postgresql" or engine.url.database != "gate07e":
        raise RuntimeError("Gate 07E schema validation requires disposable PostgreSQL")
    with engine.connect() as connection:
        actual = connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert actual == expected_revision, (actual, expected_revision)
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        if expected_revision == "20260820_0044":
            assert "portfolio_project_evaluations" not in tables
            return
        assert expected_revision == "20260820_0045"
        assert "portfolio_project_evaluations" in tables
        columns = {item["name"] for item in inspector.get_columns("portfolio_project_evaluations")}
        assert EXPECTED_COLUMNS.issubset(columns)
        foreign_keys = {
            item.get("referred_table") for item in inspector.get_foreign_keys("portfolio_project_evaluations")
        }
        assert {
            "tenants",
            "enterprise_workspaces",
            "portfolio_project_memberships",
            "admin_configurations",
            "user_accounts",
        }.issubset(foreign_keys)
        unique_sets = {
            tuple(item.get("column_names") or [])
            for item in inspector.get_unique_constraints("portfolio_project_evaluations")
        }
        assert ("tenant_id", "portfolio_workspace_id", "project_workspace_id", "evaluation_version") in unique_sets
        assert ("tenant_id", "start_idempotency_key") in unique_sets
        assert ("tenant_id", "complete_idempotency_key") in unique_sets
        assert ("tenant_id", "reevaluation_idempotency_key") in unique_sets


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expect", required=True, choices=("20260820_0044", "20260820_0045"))
    args = parser.parse_args()
    validate(args.expect)
    print(f"Gate07E schema {args.expect}: PASS")


if __name__ == "__main__":
    main()
