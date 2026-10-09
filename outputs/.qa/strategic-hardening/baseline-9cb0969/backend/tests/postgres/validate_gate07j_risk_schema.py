"""Validate additive/reversible Gate 07J-RISK PostgreSQL schema."""

from __future__ import annotations

import argparse

from sqlalchemy import inspect, text

from app.database.session import engine

REVISION_BEFORE = "20260830_0052"
REVISION_AFTER = "20260830_0053"


def validate(expected_revision: str) -> None:
    if engine.dialect.name != "postgresql" or engine.url.database != "gate07e":
        raise RuntimeError("Gate 07J-RISK schema validation requires disposable PostgreSQL")
    with engine.connect() as connection:
        actual = connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert actual == expected_revision, (actual, expected_revision)
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        if expected_revision == REVISION_BEFORE:
            assert "project_risks" not in tables
            assert "risk_readiness_assessments" not in tables
            return

        assert expected_revision == REVISION_AFTER
        assert {"project_risks", "risk_readiness_assessments"}.issubset(tables)
        risk_columns = {item["name"] for item in inspector.get_columns("project_risks")}
        assessment_columns = {item["name"] for item in inspector.get_columns("risk_readiness_assessments")}
        assert {
            "risk_number",
            "inherent_rating",
            "treatment_status",
            "residual_rating",
            "accepted_by",
            "evidence_refs_json",
            "revision_version",
        }.issubset(risk_columns)
        assert {
            "assessment_version",
            "risk_register_hash",
            "configuration_hash",
            "risk_readiness_hash",
            "readiness_status",
            "revision_version",
        }.issubset(assessment_columns)
        indexes = {item["name"] for item in inspector.get_indexes("risk_readiness_assessments")}
        risk_checks = {item["name"] for item in inspector.get_check_constraints("project_risks")}
        assessment_checks = {item["name"] for item in inspector.get_check_constraints("risk_readiness_assessments")}
        assert "uq_risk_readiness_active_project" in indexes
        assert {"ck_project_risk_status", "ck_project_risk_acceptance_pair"}.issubset(risk_checks)
        assert {"ck_risk_readiness_assessment_status", "ck_risk_readiness_completed"}.issubset(assessment_checks)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expect", required=True, choices=(REVISION_BEFORE, REVISION_AFTER))
    args = parser.parse_args()
    validate(args.expect)
    print(f"Gate07J-RISK schema {args.expect}: PASS")


if __name__ == "__main__":
    main()
