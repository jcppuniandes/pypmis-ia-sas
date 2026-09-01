"""Validate additive/reversible Gate 07L PostgreSQL schema."""

from __future__ import annotations

import argparse

from sqlalchemy import inspect, text

from app.database.session import engine

REVISION_BEFORE = "20260831_0055"
REVISION_AFTER = "20260901_0056"


def validate(expected_revision: str) -> None:
    if engine.dialect.name != "postgresql" or engine.url.database != "gate07e":
        raise RuntimeError("Gate 07L schema validation requires disposable PostgreSQL")
    with engine.connect() as connection:
        actual = connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert actual == expected_revision, (actual, expected_revision)
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        if expected_revision == REVISION_BEFORE:
            assert "post_fid_project_eligibilities" not in tables
            return
        assert expected_revision == REVISION_AFTER
        assert "post_fid_project_eligibilities" in tables
        columns = {item["name"] for item in inspector.get_columns("post_fid_project_eligibilities")}
        assert {
            "investment_decision_id",
            "project_workspace_id",
            "eligibility_round",
            "fid_decision_hash",
            "decision_package_hash",
            "project_state_snapshot",
            "condition_snapshot_hash",
            "eligibility_status",
            "eligible_for_initialization",
            "eligible_for_activation",
            "source_current",
            "eligibility_hash",
            "revision_version",
        }.issubset(columns)
        checks = {item["name"] for item in inspector.get_check_constraints("post_fid_project_eligibilities")}
        assert {"ck_post_fid_eligibility_status", "ck_post_fid_single_handoff"}.issubset(checks)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expect", required=True, choices=(REVISION_BEFORE, REVISION_AFTER))
    args = parser.parse_args()
    validate(args.expect)
    print(f"Gate07L schema {args.expect}: PASS")


if __name__ == "__main__":
    main()
