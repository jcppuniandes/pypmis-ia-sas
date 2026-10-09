"""Validate the additive and reversible Gate 07J-FEL PostgreSQL migration."""

from __future__ import annotations

import argparse

from sqlalchemy import inspect, text

from app.database.session import engine

EXPECTED_TABLES = {"project_fel_statuses", "project_definition_assessments", "project_definition_actions"}


def validate(expected_revision: str) -> None:
    if engine.dialect.name != "postgresql" or engine.url.database != "gate07e":
        raise RuntimeError("Gate 07J-FEL schema validation requires disposable PostgreSQL")
    with engine.connect() as connection:
        actual = connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert actual == expected_revision, (actual, expected_revision)
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        if expected_revision == "20260826_0049":
            assert not EXPECTED_TABLES.intersection(tables)
            return
        assert expected_revision == "20260826_0050"
        assert EXPECTED_TABLES.issubset(tables)
        assessment_columns = {item["name"] for item in inspector.get_columns("project_definition_assessments")}
        assert {
            "project_workspace_id",
            "assessment_version",
            "framework_type",
            "fel_stage_code",
            "element_results_json",
            "definition_source_hash",
            "assessment_hash",
            "revision_version",
        }.issubset(assessment_columns)
        status_checks = {item.get("name") for item in inspector.get_check_constraints("project_fel_statuses")}
        assessment_checks = {
            item.get("name") for item in inspector.get_check_constraints("project_definition_assessments")
        }
        assert "ck_project_fel_status_lifecycle" in status_checks
        assert "ck_project_definition_framework_type" in assessment_checks
        assert "ck_project_definition_threshold_status" in assessment_checks


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expect", required=True, choices=("20260826_0049", "20260826_0050"))
    args = parser.parse_args()
    validate(args.expect)
    print(f"Gate07J-FEL schema {args.expect}: PASS")


if __name__ == "__main__":
    main()
