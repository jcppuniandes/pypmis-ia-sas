"""Validate additive/reversible Gate 07J-PERMIT PostgreSQL schema."""

from __future__ import annotations

import argparse

from sqlalchemy import inspect, text

from app.database.session import engine

REVISION_BEFORE = "20260830_0053"
REVISION_AFTER = "20260831_0054"


def validate(expected_revision: str) -> None:
    if engine.dialect.name != "postgresql" or engine.url.database != "gate07e":
        raise RuntimeError("Gate 07J-PERMIT schema validation requires disposable PostgreSQL")
    with engine.connect() as connection:
        actual = connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert actual == expected_revision, (actual, expected_revision)
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        if expected_revision == REVISION_BEFORE:
            assert "project_permits" not in tables
            assert "permit_conditions" not in tables
            assert "permit_readiness_assessments" not in tables
            return

        assert expected_revision == REVISION_AFTER
        assert {"project_permits", "permit_conditions", "permit_readiness_assessments"}.issubset(tables)
        permit_columns = {item["name"] for item in inspector.get_columns("project_permits")}
        condition_columns = {item["name"] for item in inspector.get_columns("permit_conditions")}
        assessment_columns = {item["name"] for item in inspector.get_columns("permit_readiness_assessments")}
        assert {
            "permit_number",
            "permit_type_code",
            "requirement_key",
            "status",
            "valid_until",
            "renewal_of_permit_id",
            "revision_version",
        }.issubset(permit_columns)
        assert {"condition_key", "blocking", "status", "evidence_refs_json", "revision_version"}.issubset(
            condition_columns
        )
        assert {
            "assessment_version",
            "requirement_set_hash",
            "permit_register_hash",
            "permit_source_hash",
            "permit_readiness_hash",
            "readiness_status",
            "revision_version",
        }.issubset(assessment_columns)
        indexes = {item["name"] for item in inspector.get_indexes("permit_readiness_assessments")}
        permit_checks = {item["name"] for item in inspector.get_check_constraints("project_permits")}
        assessment_checks = {item["name"] for item in inspector.get_check_constraints("permit_readiness_assessments")}
        assert "uq_permit_readiness_active_project_profile" in indexes
        assert {"ck_project_permit_status", "ck_project_permit_validity"}.issubset(permit_checks)
        assert {"ck_permit_readiness_status", "ck_permit_readiness_completed"}.issubset(assessment_checks)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expect", required=True, choices=(REVISION_BEFORE, REVISION_AFTER))
    args = parser.parse_args()
    validate(args.expect)
    print(f"Gate07J-PERMIT schema {args.expect}: PASS")


if __name__ == "__main__":
    main()
