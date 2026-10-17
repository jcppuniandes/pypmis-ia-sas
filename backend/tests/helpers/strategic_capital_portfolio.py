"""Real Portfolio lifecycles for an existing fresh canonical Capital Owner Project.

Only policy payload shape and planning inputs are reused from the historical FID
fixture. This adapter never creates a Portfolio/Project/membership, writes an ORM
terminal state, or inserts an already-published configuration. Callers provide
the real actors and canonical identities produced by their upstream lifecycle.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select

from app.domain.models import EnterpriseWorkspace, SecurityEvent
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.portfolio_analysis.service import PortfolioAnalysisService
from app.modules.portfolio_budget.schemas import BudgetScenarioCreateIn, BudgetTargetCreateIn, TargetPeriodIn
from app.modules.portfolio_budget.service import PortfolioBudgetService
from app.modules.portfolio_convergence.schemas import ConvergenceCreateIn, RecommendationIn
from app.modules.portfolio_convergence.service import PortfolioConvergenceService
from app.modules.portfolio_evaluation.schemas import CriterionRatingIn, EvaluationUpdateIn
from app.modules.portfolio_evaluation.service import PortfolioEvaluationService
from app.modules.portfolio_planning.models import PortfolioProjectMembership
from app.modules.portfolio_resource.schemas import (
    CapacityPeriodIn,
    CapacityPlanCreateIn,
    DemandPeriodIn,
    DemandProfileCreateIn,
    ResourceScenarioCreateIn,
)
from app.modules.portfolio_resource.service import PortfolioResourceService
from app.modules.portfolio_review.models import PortfolioReviewSession
from app.modules.portfolio_review.schemas import (
    ActionApprovalIn,
    CompleteReviewIn,
    PortfolioReviewActionCreate,
    PortfolioReviewActionUpdate,
    PortfolioReviewConclusionCreate,
    PortfolioReviewCreate,
    SnapshotCommandIn,
)
from app.modules.portfolio_review.service import PortfolioReviewService


def _key(action: str) -> str:
    return f"fresh-capital-portfolio-{action}-{uuid4().hex}"


def _id(actor) -> int:
    return int(actor if isinstance(actor, int) else actor.id)


def _service(cls, db, tenant_id: int, actor_id: int, permission: str):
    context = require_enterprise_permission(db, tenant_id, actor_id, permission, bootstrap=False)
    return cls(db, tenant_id, actor_id, context)


def _ref(record) -> dict:
    return {
        "id": record.id,
        "revision": record.revision,
        "status": record.status,
        "content_hash": record.content_hash,
        "created_by_user_id": record.created_by_user_id,
    }


def configure_portfolio_policies(db, tenant_id: int, author, reviewer, portfolio, *, currency: str = "USD") -> dict:
    """Publish successors without editing history, at their actual source scope.

    Project demand profiles use the Resource tenant policy; a Portfolio-scoped
    policy alone is not a valid replacement for that contract. Other planning
    policies remain scoped to the caller's actual Portfolio.
    """
    author_id, reviewer_id, portfolio_id = _id(author), _id(reviewer), _id(portfolio)
    assert author_id != reviewer_id
    policies = {}
    for label, cls in (
        ("evaluation", PortfolioEvaluationService),
        ("analysis", PortfolioAnalysisService),
        ("budget", PortfolioBudgetService),
        ("resource", PortfolioResourceService),
        ("convergence", PortfolioConvergenceService),
    ):
        permission = f"portfolio_{label}.admin.configure"
        preparer = _service(cls, db, tenant_id, author_id, permission)
        preparer.ensure_seed()
        sources = preparer.configurations()
        assert sources, f"Missing reusable {label} starter configuration"
        source = sources[0]
        original_content = deepcopy(source.content_json)
        original_hash = source.content_hash
        draft = preparer.clone_configuration(source.id, source.version)
        content = deepcopy(draft.content_json)
        content["scope"] = (
            {"type": "tenant", "workspace_id": None}
            if label == "resource"
            else {"type": "portfolio", "workspace_id": portfolio_id}
        )
        if label == "budget":
            content["budget_currency_policy"] = {
                **dict(content.get("budget_currency_policy", {})),
                "mode": "FIXED",
                "budget_currency": currency,
                "fx_conversion": False,
            }
        draft = preparer.update_configuration(
            draft.id,
            draft.version,
            f"Fresh Capital Owner UAT {label}",
            "Scoped reusable UAT configuration; no live business execution on publication.",
            content,
        )
        preview_args = (None, draft.id, None, None) if label == "budget" else (None, draft.id, None)
        preview = preparer.configuration_preview(*preview_args)
        assert preview.validation_issues == [], preview.validation_issues
        assert preview.publishable is True
        publisher = _service(cls, db, tenant_id, reviewer_id, f"portfolio_{label}.admin.publish")
        published = publisher.publish_configuration(draft.id, draft.version)
        assert published.status == "published"
        assert published.created_by_user_id == author_id
        assert publisher.actor_id == reviewer_id
        db.refresh(source)
        assert source.content_json == original_content
        assert source.content_hash == original_hash
        policies[label] = published
    return policies


def prepare_portfolio_sources(
    db,
    tenant_id: int,
    author,
    reviewer,
    portfolio,
    project,
    *,
    policies: dict | None = None,
    currency: str = "USD",
    total_investment: Decimal = Decimal("100000000"),
    horizon_start: date = date(2027, 1, 1),
    horizon_end: date = date(2030, 12, 31),
    time_phasing_method: str = "UNPHASED",
) -> dict:
    """Complete A8–A12 using only real grants and normal command services.

    The independent reviewer publishes planning targets/capacity and freezes both
    scenarios, then recommends the alternative. Every policy's existing SoD,
    currentness, scope and feasibility rules remain enabled and unchanged.
    """
    author_id, reviewer_id = _id(author), _id(reviewer)
    portfolio_id, project_id = _id(portfolio), _id(project)
    assert author_id != reviewer_id
    canonical = db.get(EnterpriseWorkspace, project_id)
    owning_portfolio = db.get(EnterpriseWorkspace, portfolio_id)
    assert canonical is not None and canonical.tenant_id == tenant_id
    assert owning_portfolio is not None and owning_portfolio.tenant_id == tenant_id
    assert canonical.workspace_type_code == "project" and canonical.status == "pending"
    assert owning_portfolio.workspace_type_code == "portfolio"
    membership = db.scalar(
        select(PortfolioProjectMembership).where(
            PortfolioProjectMembership.tenant_id == tenant_id,
            PortfolioProjectMembership.project_workspace_id == project_id,
            PortfolioProjectMembership.portfolio_workspace_id == portfolio_id,
            PortfolioProjectMembership.membership_source == "STRATEGIC_INTAKE",
            PortfolioProjectMembership.status == "ACTIVE",
        )
    )
    assert membership is not None, "Upstream governed intake must produce this Project membership"
    project_before = {
        "id": canonical.id,
        "external_key": canonical.external_key,
        "record_code": canonical.record_code,
        "status": canonical.status,
        "version": canonical.version,
        "defaults_json": deepcopy(canonical.defaults_json),
    }
    policies = policies or configure_portfolio_policies(
        db, tenant_id, author_id, reviewer_id, portfolio_id, currency=currency
    )

    evaluator = _service(PortfolioEvaluationService, db, tenant_id, author_id, "portfolio_evaluation.create")
    evaluation = evaluator.start_evaluation(portfolio_id, project_id, _key("evaluation-start"))
    ratings = [
        CriterionRatingIn(
            criterion_code=str(item["code"]),
            rating=Decimal("2") if item["code"] == "risk" else Decimal("5"),
            evidence=f"UAT-COPPER-{project_id}-{item['code']}",
            comment="Current canonical investment evaluated against its effective contextual matrix.",
        )
        for item in evaluation.matrix_snapshot["criteria"]
    ]
    evaluation = _service(
        PortfolioEvaluationService, db, tenant_id, author_id, "portfolio_evaluation.edit"
    ).update_evaluation(
        evaluation.id,
        evaluation.revision_version,
        EvaluationUpdateIn(ratings=ratings, comments="Fresh Copper Processing Expansion contextual evaluation."),
    )
    evaluation = _service(
        PortfolioEvaluationService, db, tenant_id, author_id, "portfolio_evaluation.complete"
    ).complete_evaluation(evaluation.id, evaluation.revision_version, _key("evaluation-complete"))
    assert evaluation.status == "COMPLETED"
    evaluation_before_denial = evaluation.model_dump(mode="json")
    try:
        _service(PortfolioEvaluationService, db, tenant_id, author_id, "portfolio_evaluation.edit").update_evaluation(
            evaluation.id,
            evaluation.revision_version,
            EvaluationUpdateIn(ratings=ratings, comments="Attempt to rewrite a completed evaluation must be denied."),
        )
    except HTTPException as denied:
        assert denied.status_code == 409 and denied.detail["code"] == "EVALUATION_IMMUTABLE"
    else:
        raise AssertionError("Completed contextual evaluation unexpectedly accepted a rewrite")
    evaluation_reader = _service(PortfolioEvaluationService, db, tenant_id, author_id, "portfolio_evaluation.read")
    assert evaluation_reader.get_evaluation(evaluation.id).model_dump(mode="json") == evaluation_before_denial
    ranking = _service(
        PortfolioEvaluationService, db, tenant_id, author_id, "portfolio_prioritization.read"
    ).prioritization(portfolio_id)
    assert ranking.portfolio_workspace_id == portfolio_id
    assert [(item.project_workspace_id, item.evaluation_id, item.rank) for item in ranking.items] == [
        (project_id, evaluation.id, 1)
    ]
    evaluation_history = list(
        db.scalars(
            select(SecurityEvent)
            .where(
                SecurityEvent.tenant_id == tenant_id,
                SecurityEvent.target_type == "PortfolioProjectEvaluation",
                SecurityEvent.target_id == evaluation.id,
            )
            .order_by(SecurityEvent.id)
        ).all()
    )
    assert {item.event_type for item in evaluation_history} >= {
        "portfolio_evaluation.started",
        "portfolio_evaluation.updated",
        "portfolio_evaluation.completed",
    }

    analyst = _service(PortfolioAnalysisService, db, tenant_id, author_id, "portfolio_analysis.read")
    analysis = analyst.overview(portfolio_id)
    assert {row.project_workspace_id for row in analysis.dataset.rows} == {project_id}
    assert analysis.dataset.rows[0].rom_cost == total_investment
    assert analysis.dataset.rows[0].currency == currency, {
        "code": "PLANNING_CURRENCY_MISSING_OR_MISMATCH",
        "tenant_id": tenant_id,
        "portfolio_workspace_id": portfolio_id,
        "project_workspace_id": project_id,
        "evaluation_id": evaluation.id,
        "expected_currency": currency,
        "actual_currency": analysis.dataset.rows[0].currency,
        "analysis_hash": analysis.dataset.analysis_hash,
        "warnings": analysis.dataset.warnings,
    }
    assert analysis.summary.rom_cost_currency == currency
    assert analysis.summary.rom_cost_coverage_percent == Decimal("100")
    assert analysis.summary.distributions
    assert analysis.readiness.can_enter_budget_planning is True, analysis.readiness.model_dump(mode="json")
    assert analysis.readiness.can_enter_resource_planning is True, analysis.readiness.model_dump(mode="json")
    investor_map, scorecard = analyst.investor_map(portfolio_id), analyst.scorecard(portfolio_id)
    analysis_project = analyst.project_detail(portfolio_id, project_id)
    assert analysis_project.evaluation_history[0]["id"] == evaluation.id
    analysis_hash = analysis.dataset.analysis_hash

    budget = _service(PortfolioBudgetService, db, tenant_id, author_id, "portfolio_budget_target.create")
    target = budget.create_target(
        portfolio_id,
        BudgetTargetCreateIn(
            planning_horizon_start=horizon_start,
            planning_horizon_end=horizon_end,
            period_granularity="YEAR",
            budget_currency=currency,
            total_budget_target=total_investment,
            capex_budget_target=total_investment,
            expense_budget_target=Decimal("0"),
            periods=[
                TargetPeriodIn(
                    period_key=str(horizon_start.year),
                    period_start=horizon_start,
                    period_end=date(horizon_start.year, 12, 31),
                    amount=total_investment,
                    capex_amount=total_investment,
                    expense_amount=Decimal("0"),
                )
            ],
            source_reference="Copper processing expansion UAT planning envelope; not an investment decision.",
            idempotency_key=_key("budget-target"),
        ),
    )
    target = _service(
        PortfolioBudgetService, db, tenant_id, reviewer_id, "portfolio_budget_target.publish"
    ).publish_target(target.id, target.revision_version, _key("budget-target-publish"))
    scenario = _service(
        PortfolioBudgetService, db, tenant_id, author_id, "portfolio_budget_scenario.create"
    ).create_scenario(
        portfolio_id,
        BudgetScenarioCreateIn(
            scenario_name="Fresh Copper Processing Expansion Budget alternative",
            budget_target_id=target.id,
            creation_mode="FROM_CURRENT_PRIORITY",
            time_phasing_method=time_phasing_method,
            expected_analysis_hash=analysis_hash,
            idempotency_key=_key("budget-scenario"),
        ),
    )
    budget_reviewer = _service(PortfolioBudgetService, db, tenant_id, reviewer_id, "portfolio_budget_scenario.freeze")
    budget_scenario = budget_reviewer.freeze_scenario(scenario.id, scenario.revision_version, _key("budget-freeze"))
    assert budget_scenario.status == "FROZEN"
    waterline = _service(PortfolioBudgetService, db, tenant_id, reviewer_id, "portfolio_budget.read").waterline(
        budget_scenario.id
    )

    resource = _service(PortfolioResourceService, db, tenant_id, author_id, "portfolio_resource_capacity.create")
    years = range(horizon_start.year, horizon_end.year + 1)
    capacity = resource.create_capacity_plan(
        portfolio_id,
        CapacityPlanCreateIn(
            plan_name="Copper expansion governed strategic delivery capacity",
            planning_horizon_start=horizon_start,
            planning_horizon_end=horizon_end,
            period_granularity="YEAR",
            source_reference="UAT workforce capacity planning evidence, not Project staffing execution.",
            periods=[
                CapacityPeriodIn(
                    resource_role_key="PROJECT_MANAGER",
                    resource_role_name="Project Manager",
                    role_category="MANAGEMENT",
                    period_key=str(year),
                    period_start=date(year, 1, 1),
                    period_end=date(year, 12, 31),
                    capacity_value=Decimal("5"),
                    unit="FTE",
                )
                for year in years
            ],
            idempotency_key=_key("capacity"),
        ),
    )
    capacity = _service(
        PortfolioResourceService, db, tenant_id, reviewer_id, "portfolio_resource_capacity.publish"
    ).publish_capacity_plan(capacity.id, capacity.revision_version, _key("capacity-publish"))
    demand = _service(
        PortfolioResourceService, db, tenant_id, author_id, "portfolio_resource_demand.create"
    ).create_demand_profile(
        project_id,
        DemandProfileCreateIn(
            profile_name="Copper expansion explicit strategic resource demand",
            source_type="PROJECT_RESOURCE_DEMAND_PROFILE",
            source_reference="Current canonical Copper Processing Expansion planning profile.",
            as_of_date=date.today(),
            planning_start=horizon_start,
            planning_finish=horizon_end,
            generation_method="EXPLICIT_PERIOD_PROFILE",
            periods=[
                DemandPeriodIn(
                    resource_role_key="PROJECT_MANAGER",
                    resource_role_name="Project Manager",
                    role_category="MANAGEMENT",
                    period_key=str(year),
                    period_start=date(year, 1, 1),
                    period_end=date(year, 12, 31),
                    demand_value=Decimal("1"),
                    unit="FTE",
                )
                for year in years
            ],
            idempotency_key=_key("resource-demand"),
        ),
    )
    demand = _service(
        PortfolioResourceService, db, tenant_id, reviewer_id, "portfolio_resource_demand.publish"
    ).publish_demand_profile(demand.id, demand.revision_version, _key("demand-publish"))
    scenario = _service(
        PortfolioResourceService, db, tenant_id, author_id, "portfolio_resource_scenario.create"
    ).create_scenario(
        portfolio_id,
        ResourceScenarioCreateIn(
            scenario_name="Fresh Copper Processing Expansion Resource alternative",
            capacity_plan_id=capacity.id,
            creation_mode="FROM_CURRENT_PRIORITY",
            expected_analysis_hash=analysis_hash,
            idempotency_key=_key("resource-scenario"),
        ),
    )
    resource_scenario = _service(
        PortfolioResourceService, db, tenant_id, reviewer_id, "portfolio_resource_scenario.freeze"
    ).freeze_scenario(scenario.id, scenario.revision_version, _key("resource-freeze"))
    assert resource_scenario.status == "FROZEN"

    convergence_service = _service(
        PortfolioConvergenceService, db, tenant_id, author_id, "portfolio_convergence.create"
    )
    convergence = convergence_service.create_convergence(
        portfolio_id,
        ConvergenceCreateIn(
            name="Fresh Copper Processing Expansion aligned alternatives",
            description="One actual Capital Owner Project aligned across frozen budget and resources.",
            idempotency_key=_key("convergence"),
        ),
    )
    convergence = _service(
        PortfolioConvergenceService, db, tenant_id, author_id, "portfolio_convergence.edit"
    ).add_alternative(
        convergence.id,
        convergence.revision_version,
        "Copper expansion budget and capacity baseline",
        budget_scenario.id,
        resource_scenario.id,
        _key("alternative"),
    )
    convergence = _service(
        PortfolioConvergenceService, db, tenant_id, author_id, "portfolio_recommendation.submit"
    ).submit_review(convergence.id, convergence.revision_version, _key("convergence-submit"))
    alternative = convergence.alternatives[0]
    assert alternative.feasibility_status == "FEASIBLE"
    convergence_reviewer = _service(
        PortfolioConvergenceService, db, tenant_id, reviewer_id, "portfolio_recommendation.recommend"
    )
    convergence = convergence_reviewer.recommend(
        convergence.id,
        convergence.revision_version,
        RecommendationIn(
            recommended_alternative_id=alternative.id,
            recommendation_reason="Current frozen budget and resource sources are aligned for the same investment.",
            risks_acknowledged=["Planning recommendation does not authorize investment or Project execution."],
            decision_support_summary="One canonical Copper expansion Project has a feasible governed alternative.",
            idempotency_key=_key("recommend"),
        ),
    )
    assert convergence.status == "RECOMMENDED" and convergence.recommendation_hash
    assert convergence.source_current is True
    readiness = convergence_reviewer.readiness(portfolio_id)
    assert readiness.final_output == "READY_FOR_INVESTMENT_GATE_PREPARATION"

    db.refresh(canonical)
    project_after = {key: deepcopy(getattr(canonical, key)) for key in project_before}
    assert project_after == project_before, "Portfolio planning must not mutate canonical Project sources or lifecycle"
    return {
        "policies": {key: _ref(record) for key, record in policies.items()},
        "evaluation": evaluation,
        "evaluation_history": evaluation_history,
        "ranking": ranking,
        "analysis": analysis,
        "analysis_project": analysis_project,
        "investor_map": investor_map,
        "scorecard": scorecard,
        "budget_target": target,
        "budget_scenario": budget_scenario,
        "waterline": waterline,
        "capacity_plan": capacity,
        "resource_demand": demand,
        "resource_scenario": resource_scenario,
        "convergence": convergence,
        "readiness": readiness,
        "project_before": project_before,
        "project_after": project_after,
        "hashes": {
            "planning_entry": evaluation.planning_entry_hash,
            "evaluation_source": evaluation.source_snapshot_hash,
            "analysis": analysis_hash,
            "budget_target": target.target_hash,
            "budget_scenario": budget_scenario.scenario_hash,
            "capacity_plan": capacity.capacity_hash,
            "resource_demand": demand.demand_hash,
            "resource_scenario": resource_scenario.scenario_hash,
            "convergence_source": convergence.convergence_source_hash,
            "recommendation": convergence.recommendation_hash,
        },
    }


def complete_periodic_review(
    db,
    tenant_id: int,
    author,
    reviewer,
    portfolio,
    project,
    *,
    planning_cycle_id: int | None = None,
    allocation_plan_id: int | None = None,
    configuration_author=None,
    configuration_publisher=None,
) -> dict:
    """Complete A13 over the caller's actual A8–A12 sources and identities.

    Review is a read-only Portfolio governance consumer, not a Gate, FID or
    Project lifecycle authority. Its independent completion and action approval
    use persisted role grants. The scoped policy retains all starter controls;
    missing/stale source blockers are surfaced, never bypassed or rewritten.
    """
    author_id, reviewer_id = _id(author), _id(reviewer)
    portfolio_id, project_id = _id(portfolio), _id(project)
    config_author_id = _id(configuration_author) if configuration_author is not None else author_id
    config_publisher_id = _id(configuration_publisher) if configuration_publisher is not None else reviewer_id
    assert author_id != reviewer_id
    assert config_author_id != config_publisher_id
    canonical = db.get(EnterpriseWorkspace, project_id)
    owning_portfolio = db.get(EnterpriseWorkspace, portfolio_id)
    assert canonical is not None and canonical.tenant_id == tenant_id
    assert owning_portfolio is not None and owning_portfolio.tenant_id == tenant_id
    assert canonical.workspace_type_code == "project" and canonical.status == "pending"
    assert owning_portfolio.workspace_type_code == "portfolio"
    membership = db.scalar(
        select(PortfolioProjectMembership).where(
            PortfolioProjectMembership.tenant_id == tenant_id,
            PortfolioProjectMembership.project_workspace_id == project_id,
            PortfolioProjectMembership.portfolio_workspace_id == portfolio_id,
            PortfolioProjectMembership.membership_source == "STRATEGIC_INTAKE",
            PortfolioProjectMembership.status == "ACTIVE",
        )
    )
    assert membership is not None, "A13 must consume the original governed intake membership"
    project_before = {
        "id": canonical.id,
        "external_key": canonical.external_key,
        "record_code": canonical.record_code,
        "status": canonical.status,
        "version": canonical.version,
        "defaults_json": deepcopy(canonical.defaults_json),
    }
    membership_before = {
        column.name: deepcopy(getattr(membership, column.name)) for column in membership.__table__.columns
    }

    configurator = _service(PortfolioReviewService, db, tenant_id, config_author_id, "portfolio_review.admin.configure")
    configurator.ensure_seed()
    source = next(
        item for item in configurator.configurations() if item.code == "default" and item.status == "published"
    )
    source_before = (deepcopy(source.content_json), source.content_hash, source.version, source.status)
    draft = configurator.clone_configuration(source.id, source.version, target_workspace_id=portfolio_id)
    draft = configurator.update_configuration(
        draft.id,
        draft.version,
        name="Fresh Copper Processing Expansion periodic governance",
        description="Scoped reuse of the current review policy; no source authority or FID is delegated.",
        content=deepcopy(draft.content_json),
    )
    policy_preview = configurator.configuration_preview(portfolio_id, configuration_id=draft.id)
    assert policy_preview.persisted is False
    assert policy_preview.effective["separation_of_duties"]["preparer_cannot_complete"] is True
    assert policy_preview.effective["separation_of_duties"]["action_creator_cannot_approve"] is True
    policy = _service(
        PortfolioReviewService, db, tenant_id, config_publisher_id, "portfolio_review.admin.publish"
    ).publish_configuration(draft.id, draft.version)
    assert policy.status == "published" and policy.created_by_user_id == config_author_id
    db.refresh(source)
    assert (source.content_json, source.content_hash, source.version, source.status) == source_before

    today = date.today()
    review = _service(PortfolioReviewService, db, tenant_id, author_id, "portfolio_review.create").create_session(
        PortfolioReviewCreate(
            portfolio_workspace_id=portfolio_id,
            scope_workspace_id=portfolio_id,
            planning_cycle_id=planning_cycle_id,
            allocation_plan_id=allocation_plan_id,
            review_type="QUARTERLY",
            review_date=today,
            next_planned_review_date=today + timedelta(days=90),
            title="Copper Processing Expansion collective Portfolio governance",
            description="Review of the same fresh Capital Owner investment, before any investment authorization.",
            chair_user_id=reviewer_id,
            secretary_user_id=author_id,
        ),
        _key("review-create"),
    )
    assert review.status == "DRAFT" and review.configuration_id == policy.id
    review = _service(PortfolioReviewService, db, tenant_id, author_id, "portfolio_review.prepare").prepare_session(
        review.id, review.revision_version
    )
    assert review.status == "PREPARING"
    action = _service(PortfolioReviewService, db, tenant_id, author_id, "portfolio_review.action.create").create_action(
        review.id,
        PortfolioReviewActionCreate(
            subject_type="PROJECT",
            subject_id=project_id,
            action_type="RETAIN_PRIORITY",
            rationale="Retain the evaluated investment in the planning recommendation; Gate07J and FID remain separate.",
            priority="MEDIUM",
            owner_user_id=author_id,
            due_date=today + timedelta(days=30),
            source_evidence_references=[
                {"type": "PORTFOLIO_PROJECT_MEMBERSHIP", "id": membership.id, "project_workspace_id": project_id}
            ],
            requested_source_authority="PORTFOLIO_REVIEW",
        ),
        review.revision_version,
        _key("review-action"),
    )
    assert action.status == "OPEN" and action.dispatch_status == "NOT_REQUESTED"
    freezer = _service(PortfolioReviewService, db, tenant_id, author_id, "portfolio_review.freeze_snapshot")
    review = freezer.get_session(review.id)
    preview = freezer.snapshot_preview(review.id)
    assert preview.persisted is False and not preview.blockers, preview.blockers
    assert preview.readiness["status"] == "READY"
    assert {item["project_workspace_id"] for item in preview.snapshot["project_matrix"]} == {project_id}
    for key in (
        "PORTFOLIO_MEMBERSHIP",
        "PORTFOLIO_RANK",
        "BUDGET_SCENARIO",
        "RESOURCE_SCENARIO",
        "SCENARIO_RECOMMENDATION",
    ):
        assert preview.source_index[key]["source_current"] is True, preview.source_index[key]
    if allocation_plan_id is not None:
        assert preview.source_index["STRATEGIC_ALLOCATION"]["record_id"] == allocation_plan_id
    frozen = freezer.freeze_snapshot(
        review.id,
        SnapshotCommandIn(reason="Freeze the actual canonical investment and current planning authorities for A13."),
        review.revision_version,
        _key("review-freeze"),
    )
    assert frozen.snapshot_hash == preview.candidate_snapshot_hash
    frozen_identity = (frozen.id, frozen.snapshot_hash, deepcopy(frozen.source_index_json))
    review = freezer.get_session(review.id)
    assert review.status == "READY_FOR_REVIEW" and review.source_current is True
    conductor = _service(PortfolioReviewService, db, tenant_id, reviewer_id, "portfolio_review.conduct")
    review = conductor.start_review(review.id, review.revision_version)
    assert review.status == "IN_REVIEW"
    conclusion = conductor.create_conclusion(
        review.id,
        PortfolioReviewConclusionCreate(
            conclusion_type="NO_MATERIAL_CHANGE",
            rationale="The current canonical investment and frozen planning recommendation remain governed independently. "
            "This conclusion is not an investment decision, FID, or permission to activate the Project.",
        ),
        review.revision_version,
    )
    action = _service(
        PortfolioReviewService, db, tenant_id, reviewer_id, "portfolio_review.action.approve"
    ).approve_action(
        action.id,
        ActionApprovalIn(approval_note="Independent acceptance of the Portfolio-only follow-up instruction."),
        action.revision_version,
        _key("review-action-approve"),
    )
    owner = _service(PortfolioReviewService, db, tenant_id, author_id, "portfolio_review.action.update")
    action = owner.update_action(action.id, PortfolioReviewActionUpdate(status="IN_PROGRESS"), action.revision_version)
    action = owner.update_action(
        action.id,
        PortfolioReviewActionUpdate(
            status="COMPLETED",
            rationale="The Portfolio planning priority has been acknowledged; no source command or investment was executed.",
        ),
        action.revision_version,
    )
    assert action.status == "COMPLETED" and action.dispatch_status == "NOT_REQUESTED"
    assert action.created_by_user_id == author_id and action.approved_by_user_id == reviewer_id
    assert action.source_mutation_performed is False and action.execution_reference is None
    completer = _service(PortfolioReviewService, db, tenant_id, reviewer_id, "portfolio_review.complete")
    review = completer.get_session(review.id)
    assert review.source_current is True
    completed = completer.complete_review(
        review.id,
        CompleteReviewIn(
            actual_review_date=today,
            next_planned_review_date=today + timedelta(days=90),
            completion_note="Independent collective Portfolio review closed; all Project/Gate/FID source authorities preserved.",
        ),
        review.revision_version,
        _key("review-complete"),
    )
    assert completed.status == "COMPLETED" and completed.source_current is True
    assert completed.prepared_by_user_id == author_id and completed.review_authority_user_id == reviewer_id
    assert completed.current_snapshot_id == frozen_identity[0]
    assert completed.current_snapshot_hash == frozen_identity[1]
    assert completed.snapshot["source_index_json"] == frozen_identity[2]
    assert completed.conclusions[0].id == conclusion.id
    assert completed.actions[0].id == action.id and completed.actions[0].status == "COMPLETED"
    assert completed.snapshot_status == "FROZEN_HISTORICAL"
    persisted_review = db.get(PortfolioReviewSession, completed.id)
    assert persisted_review is not None and persisted_review.tenant_id == tenant_id
    assert persisted_review.completion_hash
    completion_snapshot = deepcopy(persisted_review.completion_snapshot_json)
    assert completion_snapshot["completed_by_user_id"] == reviewer_id
    assert completion_snapshot["snapshot_id"] == frozen.id
    assert completion_snapshot["snapshot_hash"] == frozen.snapshot_hash
    assert completion_snapshot["open_action_count"] == 0
    matrix = completer.project_matrix(completed.id)
    assert {item.project_workspace_id for item in matrix.items} == {project_id}
    db.refresh(canonical)
    db.refresh(membership)
    project_after = {key: deepcopy(getattr(canonical, key)) for key in project_before}
    membership_after = {
        column.name: deepcopy(getattr(membership, column.name)) for column in membership.__table__.columns
    }
    assert project_after == project_before, "A13 Review must not mutate the canonical Project or lifecycle"
    assert membership_after == membership_before, "A13 Review must not change Portfolio intake membership"
    return {
        "policy": _ref(policy),
        "policy_preview": policy_preview,
        "review": completed,
        "snapshot_preview": preview,
        "snapshot": frozen,
        "conclusion": conclusion,
        "action": action,
        "project_matrix": matrix,
        "history": completer.history(completed.id),
        "completion_snapshot": completion_snapshot,
        "project_before": project_before,
        "project_after": project_after,
        "membership_before": membership_before,
        "membership_after": membership_after,
        "hashes": {
            "review_snapshot": frozen.snapshot_hash,
            "review_completion": persisted_review.completion_hash,
            "configuration": policy.content_hash,
        },
    }
