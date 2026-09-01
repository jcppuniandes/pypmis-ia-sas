"""Validate additive/reversible Gate 07K PostgreSQL schema."""

from __future__ import annotations

import argparse

from sqlalchemy import inspect, text

from app.database.session import engine

REVISION_BEFORE = "20260831_0054"
REVISION_AFTER = "20260831_0055"


def validate(expected_revision: str) -> None:
    if engine.dialect.name != "postgresql" or engine.url.database != "gate07e":
        raise RuntimeError("Gate 07K schema validation requires disposable PostgreSQL")
    with engine.connect() as connection:
        actual = connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert actual == expected_revision, (actual, expected_revision)
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        if expected_revision == REVISION_BEFORE:
            assert "investment_decisions" not in tables
            assert "investment_decision_votes" not in tables
            return
        assert expected_revision == REVISION_AFTER
        assert {"investment_decisions", "investment_decision_votes"}.issubset(tables)
        columns = {item["name"] for item in inspector.get_columns("investment_decisions")}
        assert {
            "decision_number",
            "investment_gate_preparation_id",
            "decision_round",
            "decision_scope_hash",
            "source_preparation_hash",
            "source_package_hash",
            "configuration_hash",
            "authority_model",
            "decision_hash",
            "is_fid",
            "full_funds_authorized",
            "investment_authorized",
            "revision_version",
        }.issubset(columns)
        checks = {item["name"] for item in inspector.get_check_constraints("investment_decisions")}
        assert {
            "ck_investment_decision_status",
            "ck_investment_decision_outcome",
            "ck_investment_decision_closed_fields",
            "ck_investment_decision_fid_semantics",
            "ck_investment_decision_hold_reason",
            "ck_investment_decision_recycle_target",
        }.issubset(checks)
        indexes = {item["name"]: item for item in inspector.get_indexes("investment_decisions")}
        assert indexes["uq_investment_decision_active_preparation_profile"]["unique"] is True
        assert "postgresql_where" in indexes["uq_investment_decision_active_preparation_profile"]["dialect_options"]
        vote_checks = {item["name"] for item in inspector.get_check_constraints("investment_decision_votes")}
        assert "ck_investment_vote_value" in vote_checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expect", required=True, choices=(REVISION_BEFORE, REVISION_AFTER))
    args = parser.parse_args()
    validate(args.expect)
    print(f"Gate07K schema {args.expect}: PASS")


if __name__ == "__main__":
    main()
