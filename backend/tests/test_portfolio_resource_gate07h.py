"""Gate 07H acceptance coverage for strategic Portfolio Resource Planning."""

from copy import deepcopy
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from tests.test_portfolio_analysis_gate07f import _complete, _context, _portfolio, _project

from app.database.session import SessionLocal
from app.domain.models import AdminConfiguration, SecurityEvent
from app.main import app
from app.modules.portfolio_analysis.service import PortfolioAnalysisService, _hash
from app.modules.portfolio_evaluation.service import PortfolioEvaluationService
from app.modules.portfolio_resource.schemas import (
    CapacityPeriodIn,
    CapacityPlanCreateIn,
    DemandPeriodIn,
    DemandProfileCreateIn,
    ResourceScenarioCreateIn,
    ScenarioSelectionIn,
    ScenarioTimingIn,
)
from app.modules.portfolio_resource.service import DEFAULT_CONFIGURATION, PortfolioResourceService


@pytest.fixture(scope="module", autouse=True)
def _started_application():
    with TestClient(app):
        yield


def _fixture(*, projects: int = 3, excluded_model: str = "CONTRACTOR_DELIVERY"):
    tenant_id, actor_id, parent = _context()
    db = SessionLocal()
    portfolio = _portfolio(db, tenant_id, actor_id, parent)
    policy = deepcopy(DEFAULT_CONFIGURATION)
    db.add(
        AdminConfiguration(
            tenant_id=tenant_id,
            kind="portfolio_resource_configuration",
            code=f"gate07h-{uuid4().hex[:8]}",
            name="Gate 07H Test Policy",
            description="Published deterministic resource policy",
            status="published",
            revision=1,
            version=1,
            content_json=policy,
            content_hash=_hash(policy),
            created_by_user_id=actor_id,
        )
    )
    included = [
        _project(db, tenant_id, actor_id, parent, portfolio, name=f"Resource Project {index}")[0]
        for index in range(projects)
    ]
    excluded, excluded_membership = _project(
        db,
        tenant_id,
        actor_id,
        parent,
        portfolio,
        name="Excluded Resource Project",
        governance_model=excluded_model,
    )
    # The governance-excluded workspace is intentionally outside the strategic
    # portfolio membership. Gate 07E blocks non-CAPITAL_OWNER memberships before
    # Gate 07F can produce the source contract consumed by Gate 07H.
    db.delete(excluded_membership)
    evaluation = PortfolioEvaluationService(db, tenant_id, actor_id)
    for project, rating in zip(included, range(5, 5 - len(included), -1), strict=False):
        _complete(evaluation, portfolio.id, project.id, max(rating, 3))
    db.commit()
    return db, tenant_id, actor_id, portfolio, included, excluded


def _capacity(service: PortfolioResourceService, portfolio_id: int, *, capacity: str = "2.0", unit: str = "FTE"):
    plan = service.create_capacity_plan(
        portfolio_id,
        CapacityPlanCreateIn(
            plan_name="Strategic Role Capacity",
            planning_horizon_start=date(2027, 1, 1),
            planning_horizon_end=date(2027, 12, 31),
            period_granularity="YEAR",
            source_reference="Corporate workforce plan",
            periods=[
                CapacityPeriodIn(
                    resource_role_key="PROJECT_MANAGER",
                    resource_role_name="Project Manager",
                    role_category="MANAGEMENT",
                    period_key="2027",
                    period_start=date(2027, 1, 1),
                    period_end=date(2027, 12, 31),
                    capacity_value=Decimal(capacity),
                    unit=unit,
                )
            ],
            idempotency_key=f"capacity-{uuid4()}",
        ),
    )
    return service.publish_capacity_plan(plan.id, plan.revision_version, f"capacity-publish-{uuid4()}")


def _demand(
    service: PortfolioResourceService,
    project_id: int,
    *,
    demand: str = "0.75",
    unit: str = "FTE",
):
    profile = service.create_demand_profile(
        project_id,
        DemandProfileCreateIn(
            profile_name="Governed strategic demand",
            source_type="PROJECT_RESOURCE_DEMAND_PROFILE",
            source_reference=f"Project {project_id} planning profile",
            as_of_date=date(2026, 8, 25),
            planning_start=date(2027, 1, 1),
            planning_finish=date(2027, 12, 31),
            generation_method="EXPLICIT_PERIOD_PROFILE",
            periods=[
                DemandPeriodIn(
                    resource_role_key="PROJECT_MANAGER",
                    resource_role_name="Project Manager",
                    role_category="MANAGEMENT",
                    period_key="2027",
                    period_start=date(2027, 1, 1),
                    period_end=date(2027, 12, 31),
                    demand_value=Decimal(demand),
                    unit=unit,
                )
            ],
            idempotency_key=f"demand-{project_id}-{uuid4()}",
        ),
    )
    return service.publish_demand_profile(profile.id, profile.revision_version, f"demand-publish-{uuid4()}")


def _scenario(service: PortfolioResourceService, portfolio_id: int, plan_id: int, *, mode="FROM_CURRENT_PRIORITY"):
    analysis = PortfolioAnalysisService(service.db, service.tenant_id, service.actor_id).overview(portfolio_id)
    return service.create_scenario(
        portfolio_id,
        ResourceScenarioCreateIn(
            scenario_name=f"Priority-based resource draft {uuid4().hex[:5]}",
            capacity_plan_id=plan_id,
            creation_mode=mode,
            expected_analysis_hash=analysis.dataset.analysis_hash,
            idempotency_key=f"resource-scenario-{uuid4()}",
        ),
    )


def test_gate07h_happy_path_overload_timing_comparison_and_final_output():
    db, tenant_id, actor_id, portfolio, projects, excluded = _fixture()
    try:
        service = PortfolioResourceService(db, tenant_id, actor_id)
        plan = _capacity(service, portfolio.id, capacity="1.0")
        for project in projects:
            _demand(service, project.id)
        first = _scenario(service, portfolio.id, plan.id)
        assert [item.project_workspace_id for item in first.projects] == [item.id for item in projects]
        assert excluded.id not in {item.project_workspace_id for item in first.projects}
        assert first.summary.overloaded_period_count == 1
        assert first.readiness.status == "READY"
        shifted = service.adjust_timing(
            first.id,
            projects[0].id,
            first.revision_version,
            ScenarioTimingIn(
                timing_method="SHIFT_START_KEEP_DURATION",
                scenario_start=date(2027, 2, 1),
                idempotency_key=f"timing-{uuid4()}",
            ),
        )
        shifted_row = next(item for item in shifted.projects if item.project_workspace_id == projects[0].id)
        assert shifted_row.source_project_start == date(2027, 1, 1)
        assert shifted_row.scenario_start == date(2027, 2, 1)
        frozen_a = service.freeze_scenario(shifted.id, shifted.revision_version, f"freeze-{uuid4()}")

        second = _scenario(service, portfolio.id, plan.id, mode="EMPTY")
        second = service.select_project(
            second.id,
            projects[0].id,
            second.revision_version,
            ScenarioSelectionIn(
                selection_state="FORCED_IN",
                forced_reason="Protect strategic delivery capability",
                idempotency_key=f"force-{uuid4()}",
            ),
        )
        frozen_b = service.freeze_scenario(second.id, second.revision_version, f"freeze-{uuid4()}")
        comparison = service.compare(portfolio.id, [frozen_a.id, frozen_b.id])
        readiness = service.readiness(portfolio.id)
        contract = service.recommendation_contract(portfolio.id)

        assert comparison.pairwise_delta["projects_removed"]
        assert comparison.role_demand_delta
        assert readiness.final_output == "READY_FOR_PORTFOLIO_RESOURCE_RECOMMENDATION"
        assert readiness.can_enter_resource_recommendation is True
        assert contract.final_output == readiness.final_output
        assert contract.ready_frozen_scenario_refs
        assert db.scalar(
            select(func.count(SecurityEvent.id)).where(
                SecurityEvent.tenant_id == tenant_id,
                SecurityEvent.event_type.like("portfolio_resource.%"),
            )
        )
    finally:
        db.close()


def test_missing_demand_is_not_fabricated_and_unit_mismatch_blocks():
    db, tenant_id, actor_id, portfolio, projects, _ = _fixture(projects=2)
    try:
        service = PortfolioResourceService(db, tenant_id, actor_id)
        plan = _capacity(service, portfolio.id)
        _demand(service, projects[0].id, unit="HOURS")
        scenario = _scenario(service, portfolio.id, plan.id)
        assert scenario.summary.demand_coverage_percent == Decimal("50.00")
        assert "INSUFFICIENT_RESOURCE_DEMAND_COVERAGE" in scenario.blockers
        assert any(item.startswith("UNIT_MISMATCH") for item in scenario.blockers)
        assert "MISSING_DEMAND_NOT_FABRICATED" in scenario.warnings
        assert scenario.readiness.status == "BLOCKED"
    finally:
        db.close()


def test_draft_staleness_refresh_and_frozen_history_are_controlled():
    db, tenant_id, actor_id, portfolio, projects, _ = _fixture(projects=1)
    try:
        service = PortfolioResourceService(db, tenant_id, actor_id)
        plan = _capacity(service, portfolio.id)
        _demand(service, projects[0].id)
        draft = _scenario(service, portfolio.id, plan.id)
        frozen = service.freeze_scenario(draft.id, draft.revision_version, f"freeze-{uuid4()}")
        replacement = _demand(service, projects[0].id, demand="1.25")
        assert replacement.profile_revision == 2
        assert service.scenario(frozen.id).readiness.status == "READY"

        editable = _scenario(service, portfolio.id, plan.id)
        another = _demand(service, projects[0].id, demand="1.5")
        assert another.profile_revision == 3
        stale = service.scenario(editable.id)
        assert stale.readiness.status == "STALE"
        preview = service.refresh_preview(editable.id)
        assert preview.persisted is False
        refreshed = service.apply_refresh(
            editable.id,
            editable.revision_version,
            preview.proposed_source_hash,
            f"refresh-{uuid4()}",
        )
        assert refreshed.readiness.status == "READY"
        with pytest.raises(HTTPException) as exc:
            service.refresh_preview(frozen.id)
        assert exc.value.status_code == 409
    finally:
        db.close()


@pytest.mark.parametrize("governance_model", ["CONTRACTOR_DELIVERY", "DIRECT_INTERNAL", "LEGACY"])
def test_non_capital_owner_demand_and_resource_planning_are_excluded(governance_model: str):
    db, tenant_id, actor_id, portfolio, _projects, excluded = _fixture(projects=1, excluded_model=governance_model)
    try:
        service = PortfolioResourceService(db, tenant_id, actor_id)
        with pytest.raises(HTTPException) as exc:
            _demand(service, excluded.id)
        assert exc.value.status_code == 409
        analysis = PortfolioAnalysisService(db, tenant_id, actor_id).overview(portfolio.id)
        assert excluded.id not in {item.project_workspace_id for item in analysis.dataset.rows}
    finally:
        db.close()


def test_admin_preview_is_non_persistent_and_stale_etag_is_rejected():
    db, tenant_id, actor_id, portfolio, _projects, _ = _fixture(projects=1)
    try:
        service = PortfolioResourceService(db, tenant_id, actor_id)
        records = service.configurations()
        published = next(item for item in records if item.status == "published")
        clone = service.clone_configuration(published.id, published.version)
        changed = deepcopy(clone.content_json)
        changed["required_demand_coverage_percent"] = 80
        changed["overload_policy"] = "BLOCK_READY_STATE"
        preview = service.configuration_preview(portfolio.id, clone.id, changed)
        assert preview.persisted is False
        assert preview.publishable is True
        clone_version = clone.version
        updated = service.update_configuration(clone.id, clone_version, clone.name, clone.description, changed)
        with pytest.raises(HTTPException) as exc:
            service.update_configuration(updated.id, clone_version, updated.name, updated.description, changed)
        assert exc.value.status_code == 412
    finally:
        db.close()
