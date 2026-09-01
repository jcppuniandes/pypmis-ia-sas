"""Real PostgreSQL acceptance checks for Gate 07I convergence and recommendation."""

from uuid import uuid4

import pytest
from sqlalchemy import inspect, select
from tests.test_portfolio_convergence_gate07i import _convergence, _fixture

from app.database.session import engine
from app.domain.models import SecurityEvent
from app.modules.portfolio_convergence.schemas import RecommendationIn
from app.modules.portfolio_convergence.service import PortfolioConvergenceService

pytestmark = pytest.mark.skipif(engine.dialect.name != "postgresql", reason="PostgreSQL Gate 07I evidence required")


def test_gate07i_postgresql_schema_and_formal_recommendation_lifecycle() -> None:
    assert {
        "portfolio_scenario_convergences",
        "portfolio_converged_alternatives",
    }.issubset(set(inspect(engine).get_table_names()))
    db, tenant_id, actor_id, portfolio, _projects, budget_scenario, resource_scenario = _fixture()
    try:
        service = PortfolioConvergenceService(db, tenant_id, actor_id)
        convergence = _convergence(service, portfolio.id, budget_scenario.id, resource_scenario.id)
        alternative = convergence.alternatives[0]
        convergence = service.submit_review(
            convergence.id, convergence.revision_version, f"pg-submit-{uuid4()}"
        )
        convergence = service.recommend(
            convergence.id,
            convergence.revision_version,
            RecommendationIn(
                recommended_alternative_id=alternative.id,
                recommendation_reason="PostgreSQL governed recommendation for downstream preparation.",
                risks_acknowledged=["Investment approval remains outside Gate 07I"],
                decision_support_summary="Both independent source branches are current, aligned and feasible.",
                idempotency_key=f"pg-recommend-{uuid4()}",
            ),
        )
        assert convergence.status == "RECOMMENDED"
        assert service.readiness(portfolio.id).can_enter_fid is False
        event_types = set(
            db.scalars(
                select(SecurityEvent.event_type).where(
                    SecurityEvent.tenant_id == tenant_id,
                    SecurityEvent.event_type.in_(
                        [
                            "portfolio_convergence.created",
                            "portfolio_convergence.alternative_added",
                            "portfolio_recommendation.submitted",
                            "portfolio_recommendation.recommended",
                        ]
                    ),
                )
            )
        )
        assert event_types == {
            "portfolio_convergence.created",
            "portfolio_convergence.alternative_added",
            "portfolio_recommendation.submitted",
            "portfolio_recommendation.recommended",
        }
    finally:
        db.close()
