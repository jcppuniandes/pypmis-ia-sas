"""Real PostgreSQL structural evidence for Gate 07A-BA."""

import pytest
from sqlalchemy import inspect

from app.database.session import engine

pytestmark = pytest.mark.skipif(engine.dialect.name != "postgresql", reason="PostgreSQL Gate 07A-BA evidence required")


def test_gate07a_ba_tables_constraints_indexes_and_proposal_lineage_exist() -> None:
    inspector = inspect(engine)
    assert {"business_analyses", "business_analysis_revisions"}.issubset(inspector.get_table_names())

    analysis_foreign_keys = {item["referred_table"] for item in inspector.get_foreign_keys("business_analyses")}
    assert {
        "tenants",
        "ideas",
        "idea_evaluations",
        "enterprise_workspaces",
        "admin_configurations",
        "user_accounts",
        "business_analyses",
    }.issubset(analysis_foreign_keys)
    analysis_uniques = {item["name"] for item in inspector.get_unique_constraints("business_analyses")}
    assert {
        "uq_business_analysis_tenant_number",
        "uq_business_analysis_idempotency",
    }.issubset(analysis_uniques)

    revision_uniques = {item["name"] for item in inspector.get_unique_constraints("business_analysis_revisions")}
    assert "uq_business_analysis_revision_number" in revision_uniques

    proposal_columns = {item["name"]: item for item in inspector.get_columns("project_proposals")}
    for column_name in (
        "source_business_analysis_id",
        "source_business_analysis_hash",
        "business_analysis_configuration_id",
        "business_analysis_configuration_revision",
        "business_analysis_configuration_hash",
    ):
        assert column_name in proposal_columns
        assert proposal_columns[column_name]["nullable"] is True
    proposal_foreign_keys = {
        (item["referred_table"], tuple(item["constrained_columns"]))
        for item in inspector.get_foreign_keys("project_proposals")
    }
    assert {
        ("business_analyses", ("source_business_analysis_id",)),
        ("admin_configurations", ("business_analysis_configuration_id",)),
    }.issubset(proposal_foreign_keys)
    proposal_indexes = {item["name"] for item in inspector.get_indexes("project_proposals")}
    assert "ix_project_proposals_source_business_analysis_id" in proposal_indexes
