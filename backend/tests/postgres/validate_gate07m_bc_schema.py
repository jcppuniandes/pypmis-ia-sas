"""Validate additive/reversible Gate 07M-BC PostgreSQL schema."""

from __future__ import annotations

import argparse

from sqlalchemy import inspect, text

from app.database.session import engine

REVISION_BEFORE = "20260901_0056"
REVISION_AFTER = "20260902_0057"
TABLES = {"business_cases", "business_case_revisions", "business_case_decision_snapshots"}


def validate(expected_revision: str) -> None:
    if engine.dialect.name != "postgresql" or engine.url.database != "gate07e":
        raise RuntimeError("Gate 07M-BC schema validation requires disposable PostgreSQL")
    with engine.connect() as connection:
        actual = connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert actual == expected_revision, (actual, expected_revision)
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        if expected_revision == REVISION_BEFORE:
            assert TABLES.isdisjoint(tables)
            return
        assert expected_revision == REVISION_AFTER
        assert TABLES.issubset(tables)
        case_columns = {item["name"] for item in inspector.get_columns("business_cases")}
        assert {"project_workspace_id", "current_revision_id", "configuration_hash", "revision_version"}.issubset(
            case_columns
        )
        revision_columns = {item["name"] for item in inspector.get_columns("business_case_revisions")}
        assert {
            "purpose",
            "as_of_date",
            "fel_stage_code",
            "source_references_json",
            "source_hashes_json",
            "alternatives_json",
            "unresolved_concerns_json",
            "economic_financial_model_id",
            "economic_financial_model_version",
            "economic_financial_model_hash",
            "financial_model_status",
            "economic_financial_readiness",
            "economic_financial_as_of_date",
            "readiness_status",
            "material_change_status",
            "content_hash",
        }.issubset(revision_columns)
        revision_indexes = {tuple(item["column_names"]) for item in inspector.get_indexes("business_case_revisions")}
        assert {
            ("as_of_date",),
            ("fel_stage_code",),
            ("economic_financial_model_id",),
            ("economic_financial_model_hash",),
        }.issubset(revision_indexes)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expect", required=True, choices=(REVISION_BEFORE, REVISION_AFTER))
    args = parser.parse_args()
    validate(args.expect)
    print(f"Gate07M-BC schema {args.expect}: PASS")


if __name__ == "__main__":
    main()
