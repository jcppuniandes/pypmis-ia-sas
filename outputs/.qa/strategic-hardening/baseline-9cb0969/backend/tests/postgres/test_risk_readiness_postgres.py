"""PostgreSQL-specific constraints for Gate 07J-RISK."""

from sqlalchemy import inspect

from app.database.session import engine


def test_risk_readiness_partial_unique_index_and_checks_exist() -> None:
    assert engine.dialect.name == "postgresql"
    inspector = inspect(engine)
    indexes = {item["name"]: item for item in inspector.get_indexes("risk_readiness_assessments")}
    assert indexes["uq_risk_readiness_active_project"]["unique"] is True
    assert "postgresql_where" in indexes["uq_risk_readiness_active_project"]["dialect_options"]
    checks = {item["name"] for item in inspector.get_check_constraints("project_risks")}
    assert "ck_project_risk_status" in checks
    assert "ck_project_risk_acceptance_pair" in checks
