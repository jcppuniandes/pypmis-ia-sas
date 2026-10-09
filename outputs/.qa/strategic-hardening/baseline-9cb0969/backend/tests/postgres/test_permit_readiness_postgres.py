"""PostgreSQL-specific constraints for Gate 07J-PERMIT."""

from sqlalchemy import inspect

from app.database.session import engine


def test_permit_readiness_partial_unique_index_and_checks_exist() -> None:
    assert engine.dialect.name == "postgresql"
    inspector = inspect(engine)
    indexes = {item["name"]: item for item in inspector.get_indexes("permit_readiness_assessments")}
    assert indexes["uq_permit_readiness_active_project_profile"]["unique"] is True
    assert "postgresql_where" in indexes["uq_permit_readiness_active_project_profile"]["dialect_options"]
    permit_checks = {item["name"] for item in inspector.get_check_constraints("project_permits")}
    assessment_checks = {item["name"] for item in inspector.get_check_constraints("permit_readiness_assessments")}
    assert {"ck_project_permit_status", "ck_project_permit_validity"}.issubset(permit_checks)
    assert {"ck_permit_readiness_status", "ck_permit_readiness_completed"}.issubset(assessment_checks)
