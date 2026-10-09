"""Real PostgreSQL acceptance checks for Gate 07J Investment Gate Preparation."""

import pytest
from sqlalchemy import inspect
from tests.test_investment_gate_preparation_gate07j import (
    _add_fel,
    _preparation,
    _profile,
    _reviewer,
    _source,
    _validate_latest_fel,
)

from app.database.session import engine
from app.modules.investment_gate_preparation.service import InvestmentGatePreparationService

pytestmark = pytest.mark.skipif(engine.dialect.name != "postgresql", reason="PostgreSQL Gate 07J evidence required")


def test_gate07j_postgresql_schema_and_frozen_handoff_lifecycle() -> None:
    assert {"investment_gate_preparations", "investment_gate_evidence_items"}.issubset(
        set(inspect(engine).get_table_names())
    )
    db, tenant_id, actor_id, portfolio, projects, _convergence = _source()
    try:
        profile = _profile(db, tenant_id, actor_id)
        reviewer = _reviewer(db, tenant_id)
        preparer = InvestmentGatePreparationService(db, tenant_id, actor_id)
        preparation = _preparation(preparer, portfolio.id, profile.id)
        for project in projects:
            preparation = _add_fel(preparer, preparation, project.id)
        validator = InvestmentGatePreparationService(db, tenant_id, reviewer.id)
        for project in projects:
            preparation = _validate_latest_fel(validator, preparation, project.id)
        preparation = preparer.ready_for_review(preparation.id, preparation.revision_version, "postgres-gate07j-ready")
        preparation = validator.freeze(preparation.id, preparation.revision_version, "postgres-gate07j-freeze")
        handoff = validator.handoff(preparation.id)
        assert handoff.final_output == "READY_FOR_INVESTMENT_DECISION"
        assert handoff.can_enter_fid is False
    finally:
        db.close()
