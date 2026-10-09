"""Validate the additive and reversible Gate 07J PostgreSQL migration."""

from __future__ import annotations

import argparse

from sqlalchemy import inspect, text

from app.database.session import engine

EXPECTED_TABLES = {"investment_gate_preparations", "investment_gate_evidence_items"}


def validate(expected_revision: str) -> None:
    if engine.dialect.name != "postgresql" or engine.url.database != "gate07e":
        raise RuntimeError("Gate 07J schema validation requires disposable PostgreSQL")
    with engine.connect() as connection:
        actual = connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert actual == expected_revision, (actual, expected_revision)
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        if expected_revision == "20260826_0048":
            assert not EXPECTED_TABLES.intersection(tables)
            return
        assert expected_revision == "20260826_0049"
        assert EXPECTED_TABLES.issubset(tables)
        preparation_columns = {item["name"] for item in inspector.get_columns("investment_gate_preparations")}
        assert {
            "portfolio_workspace_id",
            "investment_gate_profile_id",
            "source_recommendation_hash",
            "recommended_project_set_hash",
            "preparation_source_hash",
            "preparation_hash",
            "revision_version",
        }.issubset(preparation_columns)
        evidence_columns = {item["name"] for item in inspector.get_columns("investment_gate_evidence_items")}
        assert {
            "requirement_key",
            "evidence_origin",
            "scope_reference_hash",
            "valid_until",
            "validated_by",
            "revision_version",
        }.issubset(evidence_columns)
        preparation_checks = {
            item.get("name") for item in inspector.get_check_constraints("investment_gate_preparations")
        }
        evidence_checks = {
            item.get("name") for item in inspector.get_check_constraints("investment_gate_evidence_items")
        }
        assert "ck_investment_gate_frozen_package" in preparation_checks
        assert "ck_investment_gate_evidence_origin" in evidence_checks
        assert "ck_investment_gate_evidence_status" in evidence_checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expect", required=True, choices=("20260826_0048", "20260826_0049"))
    args = parser.parse_args()
    validate(args.expect)
    print(f"Gate07J schema {args.expect}: PASS")


if __name__ == "__main__":
    main()
