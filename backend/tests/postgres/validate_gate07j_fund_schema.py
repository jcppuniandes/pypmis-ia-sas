"""Validate the additive and reversible Gate 07J-FUND PostgreSQL migration."""

from __future__ import annotations

import argparse

from sqlalchemy import inspect, text

from app.database.session import engine

EXPECTED_TABLES = {
    "strategic_funding_sources",
    "funds",
    "funding_assignments",
    "funding_readiness_snapshots",
}


def validate(expected_revision: str) -> None:
    if engine.dialect.name != "postgresql" or engine.url.database != "gate07e":
        raise RuntimeError("Gate 07J-FUND schema validation requires disposable PostgreSQL")
    with engine.connect() as connection:
        actual = connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert actual == expected_revision, (actual, expected_revision)
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        if expected_revision == "20260826_0050":
            assert not EXPECTED_TABLES.intersection(tables)
            return
        assert expected_revision == "20260827_0051"
        assert EXPECTED_TABLES.issubset(tables)
        assignment_columns = {item["name"] for item in inspector.get_columns("funding_assignments")}
        assert {
            "parent_assignment_id",
            "recommended_project_set_hash",
            "source_recommendation_hash",
            "normalized_amount",
            "fx_source_reference",
            "conditions_json",
            "assignment_hash",
            "revision_version",
        }.issubset(assignment_columns)
        snapshot_columns = {item["name"] for item in inspector.get_columns("funding_readiness_snapshots")}
        assert {
            "funding_requirement_hash",
            "source_hash",
            "configuration_hash",
            "funding_readiness_hash",
            "source_current",
            "can_supply_investment_gate_evidence",
        }.issubset(snapshot_columns)
        assignment_checks = {item.get("name") for item in inspector.get_check_constraints("funding_assignments")}
        snapshot_checks = {item.get("name") for item in inspector.get_check_constraints("funding_readiness_snapshots")}
        assert "ck_funding_assignment_status" in assignment_checks
        assert "ck_funding_assignment_scope" in assignment_checks
        assert "ck_funding_readiness_status" in snapshot_checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expect", required=True, choices=("20260826_0050", "20260827_0051"))
    args = parser.parse_args()
    validate(args.expect)
    print(f"Gate07J-FUND schema {args.expect}: PASS")


if __name__ == "__main__":
    main()
