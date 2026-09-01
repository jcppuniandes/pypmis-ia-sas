"""Gate 07I acceptance coverage for governed scenario convergence and recommendation."""

from copy import deepcopy
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from tests.test_portfolio_analysis_gate07f import _complete, _context, _portfolio, _project

from app.database.session import SessionLocal
from app.domain.models import AdminConfiguration
from app.main import app
from app.modules.portfolio_analysis.service import PortfolioAnalysisService, _hash
from app.modules.portfolio_budget.schemas import (
    BudgetScenarioCreateIn,
    BudgetTargetCreateIn,
    TargetPeriodIn,
)
from app.modules.portfolio_budget.schemas import (
    ScenarioSelectionIn as BudgetSelectionIn,
)
from app.modules.portfolio_budget.service import (
    DEFAULT_CONFIGURATION as BUDGET_CONFIGURATION,
)
from app.modules.portfolio_budget.service import (
    PortfolioBudgetService,
)
from app.modules.portfolio_convergence.schemas import (
    ConvergenceCreateIn,
    RecommendationIn,
)
from app.modules.portfolio_convergence.service import (
    DEFAULT_CONFIGURATION as CONVERGENCE_CONFIGURATION,
)
from app.modules.portfolio_convergence.service import (
    PortfolioConvergenceService,
)
from app.modules.portfolio_evaluation.service import PortfolioEvaluationService
from app.modules.portfolio_resource.schemas import (
    CapacityPeriodIn,
    CapacityPlanCreateIn,
    DemandPeriodIn,
    DemandProfileCreateIn,
    ResourceScenarioCreateIn,
)
from app.modules.portfolio_resource.schemas import (
    ScenarioSelectionIn as ResourceSelectionIn,
)
from app.modules.portfolio_resource.service import (
    DEFAULT_CONFIGURATION as RESOURCE_CONFIGURATION,
)
from app.modules.portfolio_resource.service import (
    PortfolioResourceService,
)


@pytest.fixture(scope="module", autouse=True)
def _started_application():
    with TestClient(app):
        yield


def _configuration(db, tenant_id: int, actor_id: int, kind: str, content: dict) -> None:
    db.add(
        AdminConfiguration(
            tenant_id=tenant_id,
            kind=kind,
            code=f"gate07i-source-{uuid4().hex[:8]}",
            name=f"Published {kind}",
            description="Isolated Gate 07I acceptance fixture.",
            status="published",
            revision=1,
            version=1,
            content_json=content,
            content_hash=_hash(content),
            created_by_user_id=actor_id,
        )
    )


def _fixture(*, conditional: bool = False):
    tenant_id, actor_id, parent = _context()
    db = SessionLocal()
    portfolio = _portfolio(db, tenant_id, actor_id, parent)
    projects = [
        _project(db, tenant_id, actor_id, parent, portfolio, name=f"Convergence Project {index}")[0]
        for index in range(1, 4)
    ]
    budget_policy = deepcopy(BUDGET_CONFIGURATION)
    budget_policy["scope"] = {"type": "portfolio", "workspace_id": portfolio.id}
    resource_policy = deepcopy(RESOURCE_CONFIGURATION)
    resource_policy["scope"] = {"type": "tenant", "workspace_id": None}
    convergence_policy = deepcopy(CONVERGENCE_CONFIGURATION)
    convergence_policy["scope"] = {"type": "portfolio", "workspace_id": portfolio.id}
    convergence_policy["allow_conditional_recommendation"] = conditional
    _configuration(db, tenant_id, actor_id, "portfolio_budget_configuration", budget_policy)
    _configuration(db, tenant_id, actor_id, "portfolio_resource_configuration", resource_policy)
    _configuration(db, tenant_id, actor_id, "portfolio_convergence_configuration", convergence_policy)
    db.commit()

    evaluator = PortfolioEvaluationService(db, tenant_id, actor_id)
    for project, rating in zip(projects, (5, 4, 3), strict=True):
        _complete(evaluator, portfolio.id, project.id, rating)

    budget = PortfolioBudgetService(db, tenant_id, actor_id)
    target = budget.create_target(
        portfolio.id,
        BudgetTargetCreateIn(
            planning_horizon_start=date(2027, 1, 1),
            planning_horizon_end=date(2027, 12, 31),
            period_granularity="YEAR",
            budget_currency="COP",
            total_budget_target="10000000",
            periods=[
                TargetPeriodIn(
                    period_key="2027",
                    period_start=date(2027, 1, 1),
                    period_end=date(2027, 12, 31),
                    amount="10000000",
                )
            ],
            source_reference="Approved planning envelope",
            idempotency_key=f"budget-target-{uuid4()}",
        ),
    )
    target = budget.publish_target(target.id, target.revision_version, f"budget-publish-{uuid4()}")
    analysis_hash = PortfolioAnalysisService(db, tenant_id, actor_id).overview(portfolio.id).dataset.analysis_hash
    budget_scenario = budget.create_scenario(
        portfolio.id,
        BudgetScenarioCreateIn(
            scenario_name="Aligned Budget Scenario",
            budget_target_id=target.id,
            creation_mode="FROM_CURRENT_PRIORITY",
            time_phasing_method="UNPHASED",
            expected_analysis_hash=analysis_hash,
            idempotency_key=f"budget-scenario-{uuid4()}",
        ),
    )
    budget_scenario = budget.freeze_scenario(
        budget_scenario.id, budget_scenario.revision_version, f"budget-freeze-{uuid4()}"
    )

    resource = PortfolioResourceService(db, tenant_id, actor_id)
    capacity = resource.create_capacity_plan(
        portfolio.id,
        CapacityPlanCreateIn(
            plan_name="Strategic Capacity",
            planning_horizon_start=date(2027, 1, 1),
            planning_horizon_end=date(2027, 12, 31),
            period_granularity="YEAR",
            source_reference="Workforce plan",
            periods=[
                CapacityPeriodIn(
                    resource_role_key="PROJECT_MANAGER",
                    resource_role_name="Project Manager",
                    role_category="MANAGEMENT",
                    period_key="2027",
                    period_start=date(2027, 1, 1),
                    period_end=date(2027, 12, 31),
                    capacity_value=Decimal("10"),
                    unit="FTE",
                )
            ],
            idempotency_key=f"capacity-{uuid4()}",
        ),
    )
    capacity = resource.publish_capacity_plan(capacity.id, capacity.revision_version, f"capacity-publish-{uuid4()}")
    for project in projects:
        demand = resource.create_demand_profile(
            project.id,
            DemandProfileCreateIn(
                profile_name="Strategic demand",
                source_type="PROJECT_RESOURCE_DEMAND_PROFILE",
                source_reference=f"Demand {project.id}",
                as_of_date=date(2026, 8, 26),
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
                        demand_value=Decimal("0.5"),
                        unit="FTE",
                    )
                ],
                idempotency_key=f"demand-{project.id}-{uuid4()}",
            ),
        )
        resource.publish_demand_profile(demand.id, demand.revision_version, f"demand-publish-{uuid4()}")
    resource_scenario = resource.create_scenario(
        portfolio.id,
        ResourceScenarioCreateIn(
            scenario_name="Aligned Resource Scenario",
            capacity_plan_id=capacity.id,
            creation_mode="FROM_CURRENT_PRIORITY",
            expected_analysis_hash=analysis_hash,
            idempotency_key=f"resource-scenario-{uuid4()}",
        ),
    )
    resource_scenario = resource.freeze_scenario(
        resource_scenario.id,
        resource_scenario.revision_version,
        f"resource-freeze-{uuid4()}",
    )
    return db, tenant_id, actor_id, portfolio, projects, budget_scenario, resource_scenario


def _convergence(service, portfolio_id: int, budget_id: int, resource_id: int):
    record = service.create_convergence(
        portfolio_id,
        ConvergenceCreateIn(
            name="Executive scenario convergence",
            description="Budget and resource alternatives for formal recommendation.",
            idempotency_key=f"convergence-{uuid4()}",
        ),
    )
    return service.add_alternative(
        record.id,
        record.revision_version,
        "Aligned baseline",
        budget_id,
        resource_id,
        f"alternative-{uuid4()}",
    )


def test_happy_path_formal_recommendation_and_downstream_contract() -> None:
    db, tenant_id, actor_id, portfolio, _projects, budget_scenario, resource_scenario = _fixture()
    try:
        service = PortfolioConvergenceService(db, tenant_id, actor_id)
        convergence = _convergence(service, portfolio.id, budget_scenario.id, resource_scenario.id)
        alternative = convergence.alternatives[0]
        assert alternative.alignment_status == "ALIGNED"
        assert alternative.feasibility_status == "FEASIBLE"

        convergence = service.submit_review(convergence.id, convergence.revision_version, f"submit-{uuid4()}")
        convergence = service.recommend(
            convergence.id,
            convergence.revision_version,
            RecommendationIn(
                recommended_alternative_id=alternative.id,
                recommendation_reason="Best governed balance of strategic value, budget and role capacity.",
                risks_acknowledged=["Delivery sequencing remains subject to the investment gate."],
                decision_support_summary="The aligned alternative remains feasible in both independent source branches.",
                idempotency_key=f"recommend-{uuid4()}",
            ),
        )
        readiness = service.readiness(portfolio.id)
        contract = service.preparation_contract(portfolio.id)

        assert convergence.status == "RECOMMENDED"
        assert readiness.final_output == "READY_FOR_INVESTMENT_GATE_PREPARATION"
        assert readiness.portfolio_recommendation_ready is True
        assert readiness.can_enter_fid is False
        assert contract.recommendation_hash == convergence.recommendation_hash
        assert contract.can_enter_fid is False
        assert contract.selected_project_set_reference
    finally:
        db.close()


def test_misaligned_and_forced_conflict_alternative_is_not_recommendable() -> None:
    db, tenant_id, actor_id, portfolio, projects, budget_scenario, resource_scenario = _fixture()
    try:
        budget = PortfolioBudgetService(db, tenant_id, actor_id)
        source = budget.clone_scenario(budget_scenario.id, budget_scenario.revision_version, f"budget-clone-{uuid4()}")
        source = budget.select_project(
            source.id,
            projects[0].id,
            source.revision_version,
            BudgetSelectionIn(
                selection_state="FORCED_OUT",
                forced_reason="Governed budget deferral",
                idempotency_key=f"budget-force-{uuid4()}",
            ),
        )
        source = budget.freeze_scenario(source.id, source.revision_version, f"budget-freeze-{uuid4()}")

        resource = PortfolioResourceService(db, tenant_id, actor_id)
        resource_draft = resource.clone_scenario(
            resource_scenario.id,
            resource_scenario.revision_version,
            f"resource-clone-{uuid4()}",
        )
        resource_draft = resource.select_project(
            resource_draft.id,
            projects[0].id,
            resource_draft.revision_version,
            ResourceSelectionIn(
                selection_state="FORCED_IN",
                forced_reason="Required specialist capacity",
                idempotency_key=f"resource-force-{uuid4()}",
            ),
        )
        resource_draft = resource.freeze_scenario(
            resource_draft.id, resource_draft.revision_version, f"resource-freeze-{uuid4()}"
        )

        service = PortfolioConvergenceService(db, tenant_id, actor_id)
        convergence = _convergence(service, portfolio.id, source.id, resource_draft.id)
        alternative = convergence.alternatives[0]
        assert alternative.alignment_status == "PARTIALLY_ALIGNED"
        assert alternative.forced_conflicts
        assert alternative.feasibility_status == "BLOCKED"
        convergence = service.submit_review(convergence.id, convergence.revision_version, f"submit-{uuid4()}")
        with pytest.raises(HTTPException) as blocked:
            service.recommend(
                convergence.id,
                convergence.revision_version,
                RecommendationIn(
                    recommended_alternative_id=alternative.id,
                    recommendation_reason="Attempt to recommend a blocked pair must be rejected.",
                    risks_acknowledged=["Known forced conflict"],
                    decision_support_summary="The test deliberately supplies contradictory forced states.",
                    idempotency_key=f"recommend-{uuid4()}",
                ),
            )
        assert blocked.value.detail["code"] == "ALTERNATIVE_NOT_ELIGIBLE_FOR_RECOMMENDATION"
    finally:
        db.close()


def test_recommended_revision_is_immutable_and_clone_starts_clean_draft() -> None:
    db, tenant_id, actor_id, portfolio, _projects, budget_scenario, resource_scenario = _fixture()
    try:
        service = PortfolioConvergenceService(db, tenant_id, actor_id)
        convergence = _convergence(service, portfolio.id, budget_scenario.id, resource_scenario.id)
        alternative = convergence.alternatives[0]
        convergence = service.submit_review(convergence.id, convergence.revision_version, f"submit-{uuid4()}")
        convergence = service.recommend(
            convergence.id,
            convergence.revision_version,
            RecommendationIn(
                recommended_alternative_id=alternative.id,
                recommendation_reason="Governed recommendation ready for investment gate preparation.",
                risks_acknowledged=["Formal approval remains downstream"],
                decision_support_summary="All required source contracts are current and mutually compatible.",
                idempotency_key=f"recommend-{uuid4()}",
            ),
        )
        with pytest.raises(HTTPException) as immutable:
            service.update_convergence(
                convergence.id,
                convergence.revision_version,
                payload={"name": "Forbidden mutation"},
            )
        assert immutable.value.detail["code"] == "RECOMMENDED_CONVERGENCE_IMMUTABLE"
        clone = service.clone(convergence.id, convergence.revision_version, f"clone-{uuid4()}")
        assert clone.status == "DRAFT"
        assert clone.convergence_revision == convergence.convergence_revision + 1
        assert clone.recommended_alternative_id is None
        assert clone.alternatives == []
    finally:
        db.close()


def test_configuration_rejects_no_source_branches_and_preview_is_non_persistent() -> None:
    db, tenant_id, actor_id, portfolio, _projects, _budget_scenario, _resource_scenario = _fixture()
    try:
        service = PortfolioConvergenceService(db, tenant_id, actor_id)
        invalid = deepcopy(CONVERGENCE_CONFIGURATION)
        invalid["required_budget_branch"] = False
        invalid["required_resource_branch"] = False
        preview = service.configuration_preview(portfolio.id, None, invalid)
        assert preview.persisted is False
        assert "AT_LEAST_ONE_SOURCE_BRANCH_REQUIRED" in preview.validation_issues
        assert preview.publishable is False
        with pytest.raises(ValueError):
            ConvergenceCreateIn(
                name="Invalid branch policy",
                required_budget_branch=False,
                required_resource_branch=False,
                idempotency_key=f"invalid-{uuid4()}",
            )
    finally:
        db.close()
