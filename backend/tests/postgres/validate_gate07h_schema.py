"""Validate the additive and reversible Gate 07H PostgreSQL migration."""

from __future__ import annotations

import argparse

from sqlalchemy import inspect, text

from app.database.session import engine

EXPECTED_TABLES = {
    "portfolio_resource_capacity_plans",
    "portfolio_resource_capacity_periods",
    "project_resource_demand_profiles",
    "project_resource_demand_periods",
    "portfolio_resource_scenarios",
    "portfolio_resource_scenario_projects",
}

EXPECTED_SCENARIO_COLUMNS = {
    "tenant_id",
    "portfolio_workspace_id",
    "capacity_plan_id",
    "capacity_plan_hash",
    "source_analysis_hash",
    "source_prioritization_hash",
    "membership_set_hash",
    "evaluation_set_hash",
    "source_configuration_hash",
    "source_hash",
    "scenario_hash",
    "creation_mode",
    "overload_policy",
    "scenario_revision",
    "revision_version",
}


def validate(expected_revision: str) -> None:
    if engine.dialect.name != "postgresql" or engine.url.database != "gate07e":
        raise RuntimeError("Gate 07H schema validation requires disposable PostgreSQL")
    with engine.connect() as connection:
        actual = connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert actual == expected_revision, (actual, expected_revision)
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        if expected_revision == "20260825_0046":
            assert not EXPECTED_TABLES.intersection(tables)
            return
        assert expected_revision == "20260825_0047"
        assert EXPECTED_TABLES.issubset(tables)
        columns = {item["name"] for item in inspector.get_columns("portfolio_resource_scenarios")}
        assert EXPECTED_SCENARIO_COLUMNS.issubset(columns)
        capacity_uniques = {
            tuple(item.get("column_names") or [])
            for item in inspector.get_unique_constraints("portfolio_resource_capacity_plans")
        }
        scenario_uniques = {
            tuple(item.get("column_names") or [])
            for item in inspector.get_unique_constraints("portfolio_resource_scenarios")
        }
        project_checks = {
            item.get("name") for item in inspector.get_check_constraints("portfolio_resource_scenario_projects")
        }
        assert ("tenant_id", "portfolio_workspace_id", "logical_code", "plan_revision") in capacity_uniques
        assert ("tenant_id", "portfolio_workspace_id", "logical_code", "scenario_revision") in scenario_uniques
        assert "ck_resource_scenario_project_forced_reason" in project_checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expect", required=True, choices=("20260825_0046", "20260825_0047"))
    args = parser.parse_args()
    validate(args.expect)
    print(f"Gate07H schema {args.expect}: PASS")


if __name__ == "__main__":
    main()
