"""Validate the additive and reversible Gate 07G PostgreSQL migration."""

from __future__ import annotations

import argparse

from sqlalchemy import inspect, text

from app.database.session import engine

EXPECTED_TABLES = {
    "portfolio_budget_targets",
    "portfolio_budget_target_periods",
    "portfolio_budget_scenarios",
    "portfolio_budget_scenario_projects",
}

EXPECTED_SCENARIO_COLUMNS = {
    "tenant_id",
    "portfolio_workspace_id",
    "budget_target_id",
    "source_analysis_hash",
    "source_prioritization_hash",
    "membership_set_hash",
    "evaluation_set_hash",
    "source_configuration_hash",
    "budget_target_hash",
    "source_hash",
    "scenario_hash",
    "creation_mode",
    "time_phasing_method",
    "scenario_revision",
    "revision_version",
}


def validate(expected_revision: str) -> None:
    if engine.dialect.name != "postgresql" or engine.url.database != "gate07e":
        raise RuntimeError("Gate 07G schema validation requires disposable PostgreSQL")
    with engine.connect() as connection:
        actual = connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert actual == expected_revision, (actual, expected_revision)
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        if expected_revision == "20260820_0045":
            assert not EXPECTED_TABLES.intersection(tables)
            return
        assert expected_revision == "20260825_0046"
        assert EXPECTED_TABLES.issubset(tables)
        columns = {item["name"] for item in inspector.get_columns("portfolio_budget_scenarios")}
        assert EXPECTED_SCENARIO_COLUMNS.issubset(columns)
        target_uniques = {
            tuple(item.get("column_names") or [])
            for item in inspector.get_unique_constraints("portfolio_budget_targets")
        }
        scenario_uniques = {
            tuple(item.get("column_names") or [])
            for item in inspector.get_unique_constraints("portfolio_budget_scenarios")
        }
        row_checks = {
            item.get("name") for item in inspector.get_check_constraints("portfolio_budget_scenario_projects")
        }
        assert ("tenant_id", "portfolio_workspace_id", "target_code", "target_revision") in target_uniques
        assert ("tenant_id", "portfolio_workspace_id", "logical_code", "scenario_revision") in scenario_uniques
        assert "ck_budget_scenario_project_forced_reason" in row_checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expect", required=True, choices=("20260820_0045", "20260825_0046"))
    args = parser.parse_args()
    validate(args.expect)
    print(f"Gate07G schema {args.expect}: PASS")


if __name__ == "__main__":
    main()
