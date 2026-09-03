"""Validate the additive and reversible Gate 07G-A PostgreSQL migration."""

from __future__ import annotations

import argparse

from sqlalchemy import inspect, text

from app.database.session import engine

REVISION_BEFORE = "20260827_0051"
REVISION_AFTER = "20260830_0052"


def validate(expected_revision: str) -> None:
    if engine.dialect.name != "postgresql" or engine.url.database != "gate07e":
        raise RuntimeError("Gate 07G-A schema validation requires disposable PostgreSQL")
    with engine.connect() as connection:
        actual = connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert actual == expected_revision, (actual, expected_revision)
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        if expected_revision == REVISION_BEFORE:
            assert "project_dependencies" not in tables
            assert "capex_budget_target" not in {
                item["name"] for item in inspector.get_columns("portfolio_budget_targets")
            }
            return

        assert expected_revision == REVISION_AFTER
        assert "project_dependencies" in tables
        target_columns = {item["name"] for item in inspector.get_columns("portfolio_budget_targets")}
        period_columns = {item["name"] for item in inspector.get_columns("portfolio_budget_target_periods")}
        scenario_columns = {item["name"] for item in inspector.get_columns("portfolio_budget_scenario_projects")}
        assert {"capex_budget_target", "expense_budget_target"}.issubset(target_columns)
        assert {"capex_amount", "expense_amount"}.issubset(period_columns)
        assert {
            "capex_amount",
            "expense_amount",
            "unclassified_amount",
            "budget_breakdown_source",
        }.issubset(scenario_columns)
        indexes = {item["name"] for item in inspector.get_indexes("project_dependencies")}
        checks = {item["name"] for item in inspector.get_check_constraints("project_dependencies")}
        assert "uq_project_dependency_active" in indexes
        assert {
            "ck_project_dependency_not_self",
            "ck_project_dependency_type",
            "ck_project_dependency_strength",
            "ck_project_dependency_status",
        }.issubset(checks)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expect", required=True, choices=(REVISION_BEFORE, REVISION_AFTER))
    args = parser.parse_args()
    validate(args.expect)
    print(f"Gate07G-A schema {args.expect}: PASS")


if __name__ == "__main__":
    main()
