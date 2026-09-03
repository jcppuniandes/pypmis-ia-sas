"""Real PostgreSQL structural evidence for Gate 07M-BC."""

import pytest
from sqlalchemy import inspect

from app.database.session import engine

pytestmark = pytest.mark.skipif(engine.dialect.name != "postgresql", reason="PostgreSQL Gate 07M-BC evidence required")


def test_gate07m_bc_core_tables_constraints_and_indexes_exist() -> None:
    inspector = inspect(engine)
    assert {
        "business_cases",
        "business_case_revisions",
        "business_case_decision_snapshots",
    }.issubset(inspector.get_table_names())
    revision_checks = {item["name"] for item in inspector.get_check_constraints("business_case_revisions")}
    assert {
        "ck_business_case_revision_status",
        "ck_business_case_revision_purpose",
        "ck_business_case_revision_readiness",
        "ck_business_case_material_change",
        "ck_business_case_financial_status",
    }.issubset(revision_checks)
    snapshot_uniques = {item["name"] for item in inspector.get_unique_constraints("business_case_decision_snapshots")}
    assert {"uq_business_case_snapshot_key", "uq_business_case_revision_snapshot_type"}.issubset(snapshot_uniques)
    case_indexes = {item["name"] for item in inspector.get_indexes("business_cases")}
    assert "ix_business_case_queue" in case_indexes
    revision_indexes = {item["name"] for item in inspector.get_indexes("business_case_revisions")}
    assert {
        "ix_business_case_revisions_as_of",
        "ix_business_case_revisions_fel_stage",
        "ix_business_case_revisions_financial_model",
        "ix_business_case_revisions_financial_hash",
    }.issubset(revision_indexes)
