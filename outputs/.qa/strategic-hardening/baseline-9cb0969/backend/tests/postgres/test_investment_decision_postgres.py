"""Real PostgreSQL structural evidence for Gate 07K."""

import pytest
from sqlalchemy import inspect

from app.database.session import engine

pytestmark = pytest.mark.skipif(engine.dialect.name != "postgresql", reason="PostgreSQL Gate 07K evidence required")


def test_gate07k_constraints_and_partial_unique_index_exist() -> None:
    inspector = inspect(engine)
    assert {"investment_decisions", "investment_decision_votes"}.issubset(inspector.get_table_names())
    checks = {item["name"] for item in inspector.get_check_constraints("investment_decisions")}
    assert {"ck_investment_decision_outcome", "ck_investment_decision_fid_semantics"}.issubset(checks)
    indexes = {item["name"]: item for item in inspector.get_indexes("investment_decisions")}
    assert indexes["uq_investment_decision_active_preparation_profile"]["unique"] is True
