"""Validate the additive and reversible Gate 07I PostgreSQL migration."""

from __future__ import annotations

import argparse

from sqlalchemy import inspect, text

from app.database.session import engine

EXPECTED_TABLES = {"portfolio_scenario_convergences", "portfolio_converged_alternatives"}


def validate(expected_revision: str) -> None:
    if engine.dialect.name != "postgresql" or engine.url.database != "gate07e":
        raise RuntimeError("Gate 07I schema validation requires disposable PostgreSQL")
    with engine.connect() as connection:
        actual = connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert actual == expected_revision, (actual, expected_revision)
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        if expected_revision == "20260825_0047":
            assert not EXPECTED_TABLES.intersection(tables)
            return
        assert expected_revision == "20260826_0048"
        assert EXPECTED_TABLES.issubset(tables)
        convergence_columns = {
            item["name"] for item in inspector.get_columns("portfolio_scenario_convergences")
        }
        assert {
            "convergence_revision",
            "required_budget_branch",
            "required_resource_branch",
            "convergence_source_hash",
            "recommended_alternative_id",
            "recommendation_hash",
            "revision_version",
        }.issubset(convergence_columns)
        checks = {
            item.get("name")
            for item in inspector.get_check_constraints("portfolio_scenario_convergences")
        }
        alternative_checks = {
            item.get("name")
            for item in inspector.get_check_constraints("portfolio_converged_alternatives")
        }
        assert "ck_portfolio_convergence_branch_required" in checks
        assert "ck_portfolio_convergence_recommended_evidence" in checks
        assert "ck_converged_alternative_alignment" in alternative_checks
        assert "ck_converged_alternative_feasibility" in alternative_checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expect", required=True, choices=("20260825_0047", "20260826_0048"))
    args = parser.parse_args()
    validate(args.expect)
    print(f"Gate07I schema {args.expect}: PASS")


if __name__ == "__main__":
    main()
