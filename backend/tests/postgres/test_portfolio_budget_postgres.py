"""Real PostgreSQL acceptance checks for Gate 07G Portfolio Budget Planning."""

from uuid import uuid4

import pytest
from sqlalchemy import inspect, select
from tests.test_portfolio_budget_gate07g import _fixture, _target

from app.database.session import engine
from app.domain.models import SecurityEvent
from app.modules.portfolio_budget.schemas import (
    BudgetScenarioCreateIn,
    ProjectDependencyCreateIn,
    ScenarioSelectionIn,
)
from app.modules.portfolio_budget.service import PortfolioBudgetService

pytestmark = pytest.mark.skipif(engine.dialect.name != "postgresql", reason="PostgreSQL Gate 07G evidence required")


def test_gate07g_postgresql_schema_and_governed_lifecycle() -> None:
    tables = set(inspect(engine).get_table_names())
    assert {
        "portfolio_budget_targets",
        "portfolio_budget_target_periods",
        "portfolio_budget_scenarios",
        "portfolio_budget_scenario_projects",
        "project_dependencies",
    }.issubset(tables)
    # Gate 07H is an additive sibling at the current schema head. Its physical
    # presence must not become a runtime dependency of Gate 07G.
    assert "portfolio_resource_scenarios" in tables
    assert "portfolio_funding_scenarios" not in tables

    db, tenant_id, actor_id, portfolio, projects, _ = _fixture(currencies=("COP", "COP"))
    try:
        service = PortfolioBudgetService(db, tenant_id, actor_id)
        target = _target(service, portfolio.id, total="3000000")
        analysis = service._analysis(portfolio.id, require_budget=True)
        create_key = f"pg-scenario-{uuid4()}"
        payload = BudgetScenarioCreateIn(
            scenario_name="PostgreSQL governed scenario",
            budget_target_id=target.id,
            creation_mode="EMPTY",
            time_phasing_method="UNPHASED",
            expected_analysis_hash=analysis.dataset.analysis_hash,
            idempotency_key=create_key,
        )
        scenario = service.create_scenario(portfolio.id, payload)
        replay = service.create_scenario(portfolio.id, payload)
        assert replay.id == scenario.id
        dependency_key = f"pg-dependency-{uuid4()}"
        dependency_payload = ProjectDependencyCreateIn(
            predecessor_project_workspace_id=projects[0][0].id,
            successor_project_workspace_id=projects[1][0].id,
            dependency_strength="MANDATORY",
            idempotency_key=dependency_key,
        )
        dependency = service.create_project_dependency(portfolio.id, dependency_payload)
        assert service.create_project_dependency(portfolio.id, dependency_payload).id == dependency.id

        forced = service.select_project(
            scenario.id,
            projects[0][0].id,
            scenario.revision_version,
            ScenarioSelectionIn(
                selection_state="FORCED_IN",
                forced_reason="Approved strategic obligation",
                authority_reference="BOARD-2026-07G",
                idempotency_key=f"pg-force-{uuid4()}",
            ),
        )
        frozen = service.freeze_scenario(forced.id, forced.revision_version, f"pg-freeze-{uuid4()}")

        assert frozen.status == "FROZEN"
        assert frozen.projects[0].forced_reason == "Approved strategic obligation"
        event_types = set(
            db.scalars(
                select(SecurityEvent.event_type).where(
                    SecurityEvent.tenant_id == tenant_id,
                    SecurityEvent.event_type.in_(
                        ["portfolio_budget.project_forced_in", "portfolio_budget.scenario_frozen"]
                    ),
                )
            )
        )
        assert event_types == {"portfolio_budget.project_forced_in", "portfolio_budget.scenario_frozen"}
    finally:
        db.close()
