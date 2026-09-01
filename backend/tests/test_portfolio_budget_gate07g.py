"""Gate 07G acceptance coverage for governed Portfolio Budget Planning."""

from copy import deepcopy
from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select
from tests.test_portfolio_analysis_gate07f import _complete, _context, _portfolio, _project

from app.database.session import SessionLocal
from app.domain.models import AdminConfiguration, SecurityEvent
from app.main import app
from app.modules.portfolio_analysis.service import _hash
from app.modules.portfolio_budget.schemas import (
    BudgetScenarioCreateIn,
    BudgetTargetCreateIn,
    ScenarioSelectionIn,
    TargetPeriodIn,
)
from app.modules.portfolio_budget.service import DEFAULT_CONFIGURATION, PortfolioBudgetService
from app.modules.portfolio_evaluation.service import PortfolioEvaluationService


@pytest.fixture(scope="module", autouse=True)
def _started_application():
    with TestClient(app):
        yield


def _fixture(*, currencies: tuple[str, ...] = ("COP", "COP", "COP"), include_excluded: bool = False):
    tenant_id, actor_id, parent = _context()
    db = SessionLocal()
    portfolio = _portfolio(db, tenant_id, actor_id, parent)
    policy = deepcopy(DEFAULT_CONFIGURATION)
    policy["scope"] = {"type": "portfolio", "workspace_id": portfolio.id}
    db.add(
        AdminConfiguration(
            tenant_id=tenant_id,
            kind="portfolio_budget_configuration",
            code=f"gate07g-{uuid4().hex[:10]}",
            name="Gate 07G Budget Policy",
            description="Isolated acceptance fixture.",
            status="published",
            revision=1,
            version=1,
            content_json=policy,
            content_hash=_hash(policy),
            created_by_user_id=actor_id,
        )
    )
    projects = [
        _project(db, tenant_id, actor_id, parent, portfolio, name=f"Budget Project {index}", currency=currency)
        for index, currency in enumerate(currencies, start=1)
    ]
    excluded = None
    if include_excluded:
        excluded = _project(
            db,
            tenant_id,
            actor_id,
            parent,
            portfolio,
            name="Contractor Project",
            governance_model="CONTRACTOR_DELIVERY",
        )
    db.commit()
    evaluation = PortfolioEvaluationService(db, tenant_id, actor_id)
    for (project, _membership), rating in zip(projects, (5, 4, 3, 2, 1), strict=False):
        _complete(evaluation, portfolio.id, project.id, rating)
    return db, tenant_id, actor_id, portfolio, projects, excluded


def _target(service: PortfolioBudgetService, portfolio_id: int, *, total: str = "5000000"):
    created = service.create_target(
        portfolio_id,
        BudgetTargetCreateIn(
            planning_horizon_start=date(2027, 1, 1),
            planning_horizon_end=date(2028, 12, 31),
            period_granularity="YEAR",
            budget_currency="COP",
            total_budget_target=total,
            periods=[
                TargetPeriodIn(
                    period_key="2027",
                    period_start=date(2027, 1, 1),
                    period_end=date(2027, 12, 31),
                    amount=str(int(total) // 2),
                ),
                TargetPeriodIn(
                    period_key="2028",
                    period_start=date(2028, 1, 1),
                    period_end=date(2028, 12, 31),
                    amount=str(int(total) - int(total) // 2),
                ),
            ],
            source_reference="Management target 2027-2028",
            idempotency_key=f"target-create-{uuid4()}",
        ),
    )
    return service.publish_target(created.id, created.revision_version, f"target-publish-{uuid4()}")


def test_happy_path_target_scenarios_comparison_and_final_contract() -> None:
    db, tenant_id, actor_id, portfolio, projects, _excluded = _fixture()
    try:
        service = PortfolioBudgetService(db, tenant_id, actor_id)
        target = _target(service, portfolio.id)
        analysis = service._analysis(portfolio.id, require_budget=True)
        first = service.create_scenario(
            portfolio.id,
            BudgetScenarioCreateIn(
                scenario_name="Priority-based draft",
                budget_target_id=target.id,
                creation_mode="FROM_CURRENT_PRIORITY",
                time_phasing_method="UNPHASED",
                expected_analysis_hash=analysis.dataset.analysis_hash,
                idempotency_key=f"scenario-a-{uuid4()}",
            ),
        )
        assert [row.portfolio_rank for row in first.projects] == [1, 2, 3]
        assert first.summary.selected_count == 2
        frozen_a = service.freeze_scenario(first.id, first.revision_version, f"freeze-a-{uuid4()}")
        assert frozen_a.status == "FROZEN"

        second = service.create_scenario(
            portfolio.id,
            BudgetScenarioCreateIn(
                scenario_name="Manual alternative",
                budget_target_id=target.id,
                creation_mode="EMPTY",
                time_phasing_method="UNPHASED",
                expected_analysis_hash=analysis.dataset.analysis_hash,
                idempotency_key=f"scenario-b-{uuid4()}",
            ),
        )
        second = service.select_project(
            second.id,
            projects[2][0].id,
            second.revision_version,
            ScenarioSelectionIn(
                selection_state="FORCED_IN",
                forced_reason="Mandatory strategic commitment",
                authority_reference="BOARD-MEMO-01",
                idempotency_key=f"force-in-{uuid4()}",
            ),
        )
        second = service.select_project(
            second.id,
            projects[0][0].id,
            second.revision_version,
            ScenarioSelectionIn(
                selection_state="FORCED_OUT",
                forced_reason="Governed deferral",
                idempotency_key=f"force-out-{uuid4()}",
            ),
        )
        frozen_b = service.freeze_scenario(second.id, second.revision_version, f"freeze-b-{uuid4()}")
        comparison = service.compare(portfolio.id, [frozen_a.id, frozen_b.id])
        readiness = service.readiness(portfolio.id)
        contract = service.recommendation_contract(portfolio.id)

        assert len(comparison.scenarios) == 2
        assert comparison.pairwise_delta["projects_added"]
        assert readiness.final_output == "READY_FOR_PORTFOLIO_BUDGET_RECOMMENDATION"
        assert readiness.can_enter_budget_recommendation is True
        assert contract.final_output == readiness.final_output
        assert len(contract.ready_frozen_scenario_refs) == 2
        events = set(
            db.scalars(
                select(SecurityEvent.event_type).where(
                    SecurityEvent.tenant_id == tenant_id,
                    SecurityEvent.event_type.like("portfolio_budget.%"),
                )
            ).all()
        )
        assert "portfolio_budget.project_forced_in" in events
        assert "portfolio_budget.scenario_frozen" in events
    finally:
        db.close()


def test_over_budget_and_explicit_linear_period_view_are_analytical_not_rejected() -> None:
    db, tenant_id, actor_id, portfolio, projects, _ = _fixture(currencies=("COP", "COP"))
    try:
        service = PortfolioBudgetService(db, tenant_id, actor_id)
        target = _target(service, portfolio.id, total="2500000")
        analysis = service._analysis(portfolio.id, require_budget=True)
        scenario = service.create_scenario(
            portfolio.id,
            BudgetScenarioCreateIn(
                scenario_name="Over budget scenario",
                budget_target_id=target.id,
                creation_mode="EMPTY",
                time_phasing_method="LINEAR_BY_PROJECT_DATES",
                expected_analysis_hash=analysis.dataset.analysis_hash,
                idempotency_key=f"over-budget-{uuid4()}",
            ),
        )
        for project, _membership in projects:
            scenario = service.select_project(
                scenario.id,
                project.id,
                scenario.revision_version,
                ScenarioSelectionIn(selection_state="SELECTED", idempotency_key=f"select-{uuid4()}"),
            )
        assert scenario.summary.analytical_status == "OVER_BUDGET"
        assert "SCENARIO_OVER_BUDGET" in scenario.warnings
        assert len(scenario.period_view) == 2
        assert all(item.approximation for item in scenario.period_view)
        frozen = service.freeze_scenario(scenario.id, scenario.revision_version, f"freeze-over-{uuid4()}")
        assert frozen.status == "FROZEN"
        with pytest.raises(HTTPException) as immutable:
            service.select_project(
                frozen.id,
                projects[0][0].id,
                frozen.revision_version,
                ScenarioSelectionIn(selection_state="UNSELECTED", idempotency_key=f"late-{uuid4()}"),
            )
        assert immutable.value.detail["code"] == "FROZEN_BUDGET_SCENARIO_IMMUTABLE"
    finally:
        db.close()


def test_currency_guardrail_and_forced_reason_validation() -> None:
    db, tenant_id, actor_id, portfolio, _projects, _ = _fixture(currencies=("COP", "USD"))
    try:
        service = PortfolioBudgetService(db, tenant_id, actor_id)
        with pytest.raises(HTTPException) as blocked:
            _target(service, portfolio.id)
        assert blocked.value.detail["code"] == "MULTI_CURRENCY_NOT_NORMALIZED"

        with pytest.raises(ValueError):
            ScenarioSelectionIn(selection_state="FORCED_IN", idempotency_key=f"missing-reason-{uuid4()}")
    finally:
        db.close()


def test_draft_refresh_is_explicit_and_frozen_history_stays_immutable() -> None:
    db, tenant_id, actor_id, portfolio, projects, _ = _fixture(currencies=("COP", "COP"))
    try:
        service = PortfolioBudgetService(db, tenant_id, actor_id)
        target = _target(service, portfolio.id)
        analysis = service._analysis(portfolio.id, require_budget=True)
        scenario = service.create_scenario(
            portfolio.id,
            BudgetScenarioCreateIn(
                scenario_name="Refresh candidate",
                budget_target_id=target.id,
                creation_mode="EMPTY",
                time_phasing_method="UNPHASED",
                expected_analysis_hash=analysis.dataset.analysis_hash,
                idempotency_key=f"refresh-scenario-{uuid4()}",
            ),
        )
        projects[0][1].membership_source = "MANUAL"
        db.commit()
        preview = service.refresh_preview(scenario.id)
        assert preview.persisted is False
        assert preview.proposed_source_hash != preview.current_source_hash
        refreshed = service.apply_refresh(
            scenario.id,
            scenario.revision_version,
            preview.proposed_source_hash,
            f"refresh-apply-{uuid4()}",
        )
        assert refreshed.readiness.status == "READY"
        frozen = service.freeze_scenario(refreshed.id, refreshed.revision_version, f"freeze-refresh-{uuid4()}")
        projects[1][1].membership_source = "MANUAL"
        db.commit()
        historical = service.scenario(frozen.id)
        assert historical.status == "FROZEN"
        assert historical.readiness.status == "STALE"
        with pytest.raises(HTTPException):
            service.refresh_preview(frozen.id)
    finally:
        db.close()


def test_admin_preview_etag_inheritance_and_downstream_terms_are_controlled() -> None:
    db, tenant_id, actor_id, portfolio, _projects, _ = _fixture(currencies=("COP",))
    try:
        service = PortfolioBudgetService(db, tenant_id, actor_id)
        published = db.scalar(
            select(AdminConfiguration).where(
                AdminConfiguration.tenant_id == tenant_id,
                AdminConfiguration.kind == "portfolio_budget_configuration",
                AdminConfiguration.status == "published",
            )
        )
        assert published is not None
        clone = service.clone_configuration(published.id, published.version)
        changed = deepcopy(clone.content_json)
        changed["scenario_max_count"] = 5
        preview = service.configuration_preview(portfolio.id, clone.id, changed, None)
        assert preview.persisted is False
        assert preview.publishable is True
        assert preview.source["resolution_chain"]
        stale_version = clone.version
        updated = service.update_configuration(clone.id, stale_version, clone.name, clone.description, changed)
        with pytest.raises(HTTPException) as stale:
            service.update_configuration(clone.id, stale_version, clone.name, clone.description, changed)
        assert stale.value.status_code == 412
        service.publish_configuration(updated.id, updated.version)

        forbidden = deepcopy(DEFAULT_CONFIGURATION)
        forbidden["recommended_scenario_id"] = 99
        assert "DOWNSTREAM_CAPABILITY_NOT_ALLOWED_IN_GATE07G" in service._configuration_issues(forbidden)
    finally:
        db.close()
