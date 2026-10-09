"""Wave 3A acceptance: frozen portfolio governance, never source authority.

The same suite is exercised by the PostgreSQL release wrapper. Source fixtures
are existing domain records, not a second ranking, scenario or Gate engine.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select, text
from tests.test_capital_allocation_wave2a import (
    _allocation_lines,
    _allocation_payload,
    _context,
    _cycle,
    _foundation,
    _project_with_membership,
    _publish_configuration,
    _token_headers,
    _user,
)

from app.core.time import utc_now
from app.database.session import SessionLocal
from app.domain.models import (
    AdminConfiguration,
    EnterpriseWorkspace,
    SecurityAccessAssignment,
    SecurityRole,
    Tenant,
)
from app.main import app
from app.modules.capital_planning.models import CapitalPlanningCycle, StrategicCapitalAllocationPlan
from app.modules.capital_planning.schemas import BucketClassificationIn, BucketClassificationsReplaceIn
from app.modules.capital_planning.service import CONFIG_KIND as CAPITAL_CONFIG_KIND
from app.modules.capital_planning.service import CapitalPlanningService
from app.modules.enterprise_structure.permissions import ensure_enterprise_permissions
from app.modules.investment_decision.models import InvestmentDecision
from app.modules.investment_gate_preparation.models import InvestmentGatePreparation
from app.modules.portfolio_budget.models import (
    PortfolioBudgetScenario,
    PortfolioBudgetScenarioProject,
    PortfolioBudgetTarget,
)
from app.modules.portfolio_convergence.models import PortfolioConvergedAlternative, PortfolioScenarioConvergence
from app.modules.portfolio_evaluation.models import PortfolioProjectEvaluation
from app.modules.portfolio_evaluation.service import PortfolioEvaluationService
from app.modules.portfolio_resource.models import (
    PortfolioResourceCapacityPeriod,
    PortfolioResourceCapacityPlan,
    PortfolioResourceScenario,
    PortfolioResourceScenarioProject,
    ProjectResourceDemandPeriod,
    ProjectResourceDemandProfile,
)
from app.modules.portfolio_review.models import PortfolioReviewAction, PortfolioReviewSession, PortfolioReviewSnapshot
from app.modules.portfolio_review.schemas import (
    ActionApprovalIn,
    ActionDispatchIn,
    CompleteReviewIn,
    PortfolioReviewActionCreate,
    PortfolioReviewActionUpdate,
    PortfolioReviewConclusionCreate,
    PortfolioReviewConclusionUpdate,
    PortfolioReviewCreate,
    PortfolioReviewUpdate,
    ReviewTransitionIn,
    SnapshotCommandIn,
)
from app.modules.portfolio_review.service import CONFIGURATION_KIND, PortfolioReviewService
from app.modules.project_creation.models import ProjectCreationRequest
from app.modules.risk_readiness.models import RiskReadinessAssessment


def _key(command: str) -> str:
    return f"wave3a-{command}-{uuid4()}"


def _portfolio(db, author, enterprise, label="governed portfolio", governance_model="CAPITAL_OWNER"):
    token = uuid4().hex[:10]
    record = EnterpriseWorkspace(
        tenant_id=author.tenant_id,
        parent_id=enterprise.id,
        workspace_type_code="portfolio",
        code=f"W3A-PF-{token}",
        external_key=f"wave3a-portfolio-{token}",
        record_code=f"{enterprise.record_code}.PF.{token}",
        name=f"Wave 3A {label}",
        status="active",
        defaults_json={"governance_model": governance_model},
        sort_order=2,
        version=1,
        created_by_user_id=author.id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _fixture(db, *, sources=True, currencies=None, unclassified_project_indexes=()):
    author, enterprise, objective = _foundation(db)
    authority = _user(db, author.tenant_id, "wave3a-authority")
    portfolio = _portfolio(db, author, enterprise)
    CapitalPlanningService(db, author.tenant_id, author.id, _context(author)).ensure_seed()
    template = db.scalar(
        select(AdminConfiguration)
        .where(
            AdminConfiguration.tenant_id == author.tenant_id,
            AdminConfiguration.kind == CAPITAL_CONFIG_KIND,
            AdminConfiguration.code == "default",
            AdminConfiguration.status == "published",
        )
        .order_by(AdminConfiguration.revision.desc())
    )
    assert template is not None
    projects, memberships = [], []
    for index in range(3):
        project, membership = _project_with_membership(
            db,
            author=author,
            enterprise=enterprise,
            portfolio=portfolio,
            template_configuration_id=template.id,
            label=f"Wave 3A standalone Project {index + 1}",
            amount=str((index + 1) * 1000000),
        )
        projects.append(project)
        memberships.append(membership)
        if currencies is not None:
            request = db.scalar(
                select(ProjectCreationRequest).where(
                    ProjectCreationRequest.tenant_id == author.tenant_id,
                    ProjectCreationRequest.materialized_workspace_id == project.id,
                )
            )
            assert request is not None
            request.currency_code = currencies[index]
    db.commit()
    preparer = PortfolioReviewService(db, author.tenant_id, author.id, _context(author, "portfolio_review_preparer"))
    reviewer = PortfolioReviewService(
        db, author.tenant_id, authority.id, _context(authority, "portfolio_review_authority")
    )
    preparer.ensure_seed()
    result = {
        "author": author,
        "authority": authority,
        "enterprise": enterprise,
        "portfolio": portfolio,
        "projects": projects,
        "memberships": memberships,
        "preparer": preparer,
        "reviewer": reviewer,
        "cycle": None,
        "plan": None,
        "unclassified_project_indexes": frozenset(unclassified_project_indexes),
    }
    if sources:
        _source_authorities(db, result, objective, template)
    return result


def _source_authorities(db, fixture, objective, template):
    author, authority = fixture["author"], fixture["authority"]
    enterprise, portfolio = fixture["enterprise"], fixture["portfolio"]
    projects, memberships = fixture["projects"], fixture["memberships"]
    capital = CapitalPlanningService(
        db,
        author.tenant_id,
        author.id,
        _context(author, "capital_planning_allocation_author", "capital_planning_cycle_manager"),
    )
    _publish_configuration(capital, objective)
    cycle = _cycle(capital, enterprise)
    plan = capital.create_allocation_plan(
        _allocation_payload(cycle.id, enterprise.id).model_copy(update={"portfolio_workspace_id": portfolio.id}),
        _key("allocation"),
    )
    plan = capital.replace_allocation_lines(plan.id, _allocation_lines(), plan.revision_version)
    plan = capital.replace_bucket_classifications(
        plan.id,
        BucketClassificationsReplaceIn(
            classifications=[
                BucketClassificationIn(target_type="PROJECT", target_id=project.id, bucket_code="grow")
                for index, project in enumerate(projects)
                if index not in fixture["unclassified_project_indexes"]
            ]
        ),
        plan.revision_version,
        _key("classification"),
    ).allocation_plan
    plan = capital.transition_allocation_plan(plan.id, "submit", plan.revision_version, _key("allocation-submit"))
    allocation_reviewer = CapitalPlanningService(
        db, author.tenant_id, authority.id, _context(authority, "capital_planning_allocation_reviewer")
    )
    plan = allocation_reviewer.transition_allocation_plan(
        plan.id, "review", plan.revision_version, _key("allocation-review")
    )
    endorser = _user(db, author.tenant_id, "wave3a-allocation-endorser")
    allocation_endorser = CapitalPlanningService(
        db, author.tenant_id, endorser.id, _context(endorser, "capital_planning_allocation_endorser")
    )
    plan = allocation_endorser.transition_allocation_plan(
        plan.id, "endorse", plan.revision_version, _key("allocation-endorse")
    )
    fixture.update(cycle=cycle, plan=plan)
    token = uuid4().hex[:10]
    for index, (project, membership) in enumerate(zip(projects, memberships, strict=True)):
        db.add(
            PortfolioProjectEvaluation(
                tenant_id=author.tenant_id,
                portfolio_workspace_id=portfolio.id,
                project_workspace_id=project.id,
                portfolio_membership_id=membership.id,
                evaluation_version=1,
                status="COMPLETED",
                matrix_configuration_id=template.id,
                matrix_revision=template.revision,
                matrix_hash=template.content_hash,
                source_snapshot_hash="1" * 64,
                planning_entry_hash="2" * 64,
                normalized_score=Decimal(90 - index * 10),
                strategic_alignment_score=Decimal("90"),
                risk_score=Decimal("20"),
                evaluator_user_id=author.id,
                completed_at=utc_now(),
            )
        )
    target = PortfolioBudgetTarget(
        tenant_id=author.tenant_id,
        portfolio_workspace_id=portfolio.id,
        target_code=f"W3A-TARGET-{token}",
        planning_horizon_start=date(2027, 1, 1),
        planning_horizon_end=date(2030, 12, 31),
        period_granularity="YEAR",
        budget_currency="COP",
        total_budget_target=Decimal("10000000"),
        status="PUBLISHED",
        target_hash="3" * 64,
        created_by=author.id,
        updated_by=author.id,
    )
    capacity = PortfolioResourceCapacityPlan(
        tenant_id=author.tenant_id,
        portfolio_workspace_id=portfolio.id,
        logical_code=f"W3A-CAPACITY-{token}",
        plan_name="Wave 3A existing capacity source",
        planning_horizon_start=date(2027, 1, 1),
        planning_horizon_end=date(2030, 12, 31),
        status="PUBLISHED",
        capacity_hash="4" * 64,
        created_by=author.id,
        updated_by=author.id,
    )
    db.add_all([target, capacity])
    db.flush()
    common = {
        "tenant_id": author.tenant_id,
        "portfolio_workspace_id": portfolio.id,
        "status": "FROZEN",
        "source_analysis_hash": "5" * 64,
        "source_prioritization_hash": "6" * 64,
        "membership_set_hash": "7" * 64,
        "evaluation_set_hash": "8" * 64,
        "source_configuration_hash": "9" * 64,
        "source_hash": "a" * 64,
        "scenario_hash": "b" * 64,
        "created_by": author.id,
        "updated_by": author.id,
    }
    budget = PortfolioBudgetScenario(
        **common,
        logical_code=f"W3A-BUDGET-{token}",
        scenario_code=f"W3A-{token}",
        scenario_name="Wave 3A existing frozen Budget",
        analytical_status="UNDER_BUDGET",
        budget_target_id=target.id,
        budget_target_hash=target.target_hash,
    )
    resource = PortfolioResourceScenario(
        **common,
        logical_code=f"W3A-RESOURCE-{token}",
        scenario_name="Wave 3A existing frozen Resource Scenario",
        capacity_plan_id=capacity.id,
        capacity_plan_hash=capacity.capacity_hash,
    )
    db.add_all([budget, resource])
    db.flush()
    db.add(
        PortfolioResourceCapacityPeriod(
            tenant_id=author.tenant_id,
            capacity_plan_id=capacity.id,
            resource_role_key="engineering",
            resource_role_name="Engineering",
            period_key="2027-01",
            period_start=date(2027, 1, 1),
            period_end=date(2027, 1, 31),
            capacity_value=Decimal("10"),
            unit="FTE",
        )
    )
    for index, (project, membership) in enumerate(zip(projects, memberships, strict=True)):
        demand = ProjectResourceDemandProfile(
            tenant_id=author.tenant_id,
            project_workspace_id=project.id,
            logical_code=f"W3A-DEMAND-{token}-{index}",
            profile_name="Existing published engineering demand",
            status="PUBLISHED",
            source_type="MANUAL_PORTFOLIO_PLANNING_PROFILE",
            as_of_date=date(2026, 10, 1),
            planning_start=date(2027, 1, 1),
            planning_finish=date(2027, 1, 31),
            demand_hash=str(index + 1) * 64,
            created_by=author.id,
            updated_by=author.id,
        )
        db.add(demand)
        db.flush()
        db.add_all(
            [
                ProjectResourceDemandPeriod(
                    tenant_id=author.tenant_id,
                    demand_profile_id=demand.id,
                    resource_role_key="engineering",
                    resource_role_name="Engineering",
                    period_key="2027-01",
                    period_start=date(2027, 1, 1),
                    period_end=date(2027, 1, 31),
                    demand_value=Decimal("1"),
                    unit="FTE",
                ),
                PortfolioResourceScenarioProject(
                    tenant_id=author.tenant_id,
                    scenario_id=resource.id,
                    project_workspace_id=project.id,
                    portfolio_membership_id=membership.id,
                    project_number=project.code,
                    project_name=project.name,
                    portfolio_evaluation_score=Decimal(90 - index * 10),
                    portfolio_rank=index + 1,
                    strategic_alignment_score=Decimal("90"),
                    risk_score=Decimal("20"),
                    risk_bucket="LOW",
                    gate07f_analysis_hash="c" * 64,
                    resource_demand_profile_id=demand.id,
                    resource_demand_hash=demand.demand_hash,
                    selection_state="SELECTED",
                    row_hash="e" * 64,
                    updated_by=author.id,
                ),
            ]
        )
        db.add(
            PortfolioBudgetScenarioProject(
                tenant_id=author.tenant_id,
                scenario_id=budget.id,
                project_workspace_id=project.id,
                portfolio_membership_id=membership.id,
                project_number=project.code,
                project_name=project.name,
                portfolio_evaluation_score=Decimal(90 - index * 10),
                portfolio_rank=index + 1,
                strategic_alignment_score=Decimal("90"),
                risk_score=Decimal("20"),
                risk_bucket="LOW",
                gate07f_analysis_hash="c" * 64,
                cost_source_type="PROJECT_CREATION_REQUEST",
                cost_source_reference=str(project.id),
                cost_source_hash="d" * 64,
                cost_value=Decimal("1000000"),
                unclassified_amount=Decimal("1000000"),
                budget_breakdown_source="LEGACY_UNCLASSIFIED",
                currency="COP",
                cost_as_of_date=date(2026, 10, 1),
                expected_benefits="Governed source",
                project_type="CAPITAL",
                planning_stage="STRATEGIC",
                selection_state="SELECTED",
                row_hash="e" * 64,
                updated_by=author.id,
            )
        )
    convergence = PortfolioScenarioConvergence(
        tenant_id=author.tenant_id,
        portfolio_workspace_id=portfolio.id,
        logical_code=f"W3A-CONVERGENCE-{token}",
        name="Wave 3A existing recommendation",
        status="DRAFT",
        required_budget_branch=True,
        required_resource_branch=True,
        source_analysis_hash="1" * 64,
        source_membership_set_hash="2" * 64,
        source_evaluation_set_hash="3" * 64,
        budget_planning_hash=budget.scenario_hash,
        configuration_id=template.id,
        configuration_revision=template.revision,
        configuration_hash=template.content_hash,
        convergence_source_hash="4" * 64,
        created_by=author.id,
        updated_by=author.id,
    )
    db.add(convergence)
    db.flush()
    alternative = PortfolioConvergedAlternative(
        tenant_id=author.tenant_id,
        convergence_id=convergence.id,
        alternative_name="Wave 3A existing alternative",
        budget_scenario_id=budget.id,
        budget_scenario_hash=budget.scenario_hash,
        resource_scenario_id=resource.id,
        resource_scenario_hash=resource.scenario_hash,
        alignment_status="ALIGNED",
        budget_feasibility="BUDGET_FEASIBLE",
        resource_feasibility="RESOURCE_FEASIBLE",
        feasibility_status="FEASIBLE",
        selected_project_set_hash="5" * 64,
        project_matrix_json=[{"project_workspace_id": project.id} for project in projects],
        alternative_hash="6" * 64,
        created_by=author.id,
        updated_by=author.id,
    )
    db.add(alternative)
    db.flush()
    convergence.recommended_alternative_id = alternative.id
    convergence.status = "RECOMMENDED"
    convergence.recommendation_hash = "7" * 64
    convergence.recommended_by = authority.id
    convergence.recommended_at = utc_now()
    db.flush()
    preparation = InvestmentGatePreparation(
        tenant_id=author.tenant_id,
        portfolio_workspace_id=portfolio.id,
        preparation_number=f"W3A-PREP-{token}",
        logical_code=f"W3A-PREP-{token}",
        name="Wave 3A existing Gate07J package",
        investment_gate_profile_id=template.id,
        profile_code="PYP-FFA",
        profile_revision=template.revision,
        profile_hash=template.content_hash,
        source_convergence_id=convergence.id,
        source_convergence_revision=convergence.convergence_revision,
        source_recommendation_hash=convergence.recommendation_hash,
        recommended_alternative_id=alternative.id,
        recommended_project_set_hash=alternative.selected_project_set_hash,
        status="FROZEN",
        readiness_status="READY",
        preparation_source_hash="8" * 64,
        preparation_hash="9" * 64,
        created_by=author.id,
        updated_by=author.id,
        frozen_by=authority.id,
        frozen_at=utc_now(),
    )
    db.add(preparation)
    db.flush()
    db.add(
        RiskReadinessAssessment(
            tenant_id=author.tenant_id,
            project_workspace_id=projects[-1].id,
            assessment_number=f"W3A-RISK-{token}",
            as_of_date=utc_now(),
            valid_until=utc_now() + timedelta(days=90),
            status="COMPLETED",
            risk_register_hash="a" * 64,
            configuration_id=template.id,
            configuration_revision=template.revision,
            configuration_hash=template.content_hash,
            readiness_status="BLOCKED",
            blockers_json=["An existing Project requires further evidence."],
            risk_readiness_hash="b" * 64,
            assessed_by=author.id,
            completed_by=authority.id,
            completed_at=utc_now(),
        )
    )
    for index, profile in enumerate(("PYP-INV-SELECT", "PYP-FFA")):
        db.add(
            InvestmentDecision(
                tenant_id=author.tenant_id,
                investment_gate_preparation_id=preparation.id,
                portfolio_workspace_id=portfolio.id,
                investment_gate_profile_id=template.id,
                decision_number=f"W3A-DEC-{token}-{index}",
                profile_code=profile,
                decision_round=1,
                decision_scope_type="EXACT_PROJECT_SET",
                decision_scope_hash=str(index) * 64,
                status="DECIDED",
                outcome="GO",
                title=f"Existing {profile} authority",
                executive_summary="Governed source",
                rationale="Existing source authority",
                source_preparation_hash=preparation.preparation_hash,
                source_package_hash=preparation.preparation_hash,
                source_profile_hash=template.content_hash,
                decision_package_snapshot_json={"project_workspace_ids": [projects[index].id]},
                configuration_id=template.id,
                configuration_revision=template.revision,
                configuration_hash=template.content_hash,
                configuration_snapshot_json=template.content_json,
                authority_model="SINGLE_DECISION_MAKER",
                decision_maker_user_id=authority.id,
                decided_at=utc_now(),
                decided_by=authority.id,
                authorized_amount=Decimal("500000"),
                authorized_currency="COP",
                is_fid=index == 1,
                full_funds_authorized=index == 1,
                investment_authorized=True,
                decision_hash=str(index + 1) * 64,
                created_by=author.id,
                updated_by=author.id,
            )
        )
    db.commit()


def _payload(fixture, *, review_date=date(2026, 10, 6)):
    return PortfolioReviewCreate(
        portfolio_workspace_id=fixture["portfolio"].id,
        scope_workspace_id=fixture["enterprise"].id,
        planning_cycle_id=fixture["cycle"].id if fixture["cycle"] else None,
        allocation_plan_id=fixture["plan"].id if fixture["plan"] else None,
        review_type="QUARTERLY",
        review_date=review_date,
        title="Wave 3A collective governance review",
        chair_user_id=fixture["authority"].id,
        next_planned_review_date=review_date + timedelta(days=90),
    )


def _ready(fixture, *, review_date=date(2026, 10, 6)):
    service = fixture["preparer"]
    review = service.create_session(_payload(fixture, review_date=review_date), _key("create"))
    review = service.prepare_session(review.id, review.revision_version)
    service.freeze_snapshot(
        review.id, SnapshotCommandIn(reason="Freeze governed sources"), review.revision_version, _key("freeze")
    )
    return service.get_session(review.id)


def _open(fixture, **kwargs):
    review = _ready(fixture, **kwargs)
    return fixture["reviewer"].start_review(review.id, review.revision_version)


def _complete(fixture, review):
    service = fixture["reviewer"]
    service.create_conclusion(
        review.id,
        PortfolioReviewConclusionCreate(
            conclusion_type="NO_MATERIAL_CHANGE", rationale="Source authorities remain governed independently."
        ),
        service.get_session(review.id).revision_version,
    )
    return service.complete_review(
        review.id,
        CompleteReviewIn(completion_note="Collective governance concluded; follow-up remains separate."),
        service.get_session(review.id).revision_version,
        _key("complete"),
    )


def _authorities(db):
    """Persisted row values, not merely counts, protect every existing authority."""
    tables = (
        "portfolio_project_memberships",
        "portfolio_project_evaluations",
        "portfolio_budget_targets",
        "portfolio_budget_scenarios",
        "portfolio_budget_scenario_projects",
        "portfolio_resource_capacity_plans",
        "portfolio_resource_scenarios",
        "portfolio_resource_scenario_projects",
        "portfolio_resource_capacity_periods",
        "project_resource_demand_profiles",
        "project_resource_demand_periods",
        "portfolio_scenario_convergences",
        "portfolio_converged_alternatives",
        "investment_gate_preparations",
        "investment_decisions",
        "risk_readiness_assessments",
        "capital_planning_cycles",
        "strategic_capital_demands",
        "strategic_capital_allocation_plans",
        "strategic_capital_allocation_lines",
        "strategic_bucket_classifications",
    )
    available = set(inspect(db.bind).get_table_names())
    return {
        name: list(db.execute(text(f'SELECT * FROM "{name}" ORDER BY id')).mappings())
        for name in tables
        if name in available
    }


def test_wave3a_multicurrency_allocation_is_grouped_and_unclassified_membership_is_preserved():
    with TestClient(app):
        with SessionLocal() as db:
            fixture = _fixture(db, currencies=("COP", "USD", "COP"), unclassified_project_indexes=(2,))
            before = _authorities(db)
            review = _ready(fixture)
            service = fixture["preparer"]
            allocation = service.allocation(review.id)
            assert allocation.source == "WAVE2A_FROZEN_REFERENCE"
            assert allocation.multi_currency is True and allocation.normalization_warning
            positions = {item["bucket_code"]: item for item in allocation.comparison["positions"]}
            grow = positions["grow"]["current_portfolio"]
            assert grow["amount_by_currency"] == {"COP": "1000000.00", "USD": "2000000.00"}
            assert grow["item_count"] == 2 and grow["evaluable"] is False
            assert grow["percentage"] is None
            assert all(position["status"] == "NOT_EVALUABLE" for position in positions.values())
            unclassified = allocation.comparison["unclassified"]["portfolio"]
            assert unclassified["amount_by_currency"] == {"COP": "3000000.00"}
            assert unclassified["item_count"] == 1 and unclassified["evaluable"] is False
            assert unclassified["percentage"] is None
            assert sum(item["current_portfolio"]["item_count"] for item in positions.values()) + 1 == 3

            matrix = service.project_matrix(review.id)
            unclassified_matrix = service.project_matrix(review.id, unclassified=True)
            classified_matrix = service.project_matrix(review.id, unclassified=False)
            assert matrix.total == 3 and unclassified_matrix.total == 1 and classified_matrix.total == 2
            standalone = unclassified_matrix.items[0]
            assert standalone.project_workspace_id == fixture["projects"][2].id
            assert standalone.membership_id == fixture["memberships"][2].id
            assert standalone.strategic_bucket == "UNCLASSIFIED"
            assert standalone.allocation_variance_contribution["bucket_status"] == "NOT_EVALUABLE"
            assert {item.project_workspace_id for item in matrix.items} == {
                project.id for project in fixture["projects"]
            }
            request = db.scalar(
                select(ProjectCreationRequest).where(
                    ProjectCreationRequest.materialized_workspace_id == standalone.project_workspace_id
                )
            )
            assert request is not None and request.source_context_type == "STANDALONE"
            assert request.source_idea_id is None
            frozen = db.get(PortfolioReviewSnapshot, review.current_snapshot_id)
            assert frozen is not None
            assert frozen.snapshot_json["allocation"] == allocation.comparison
            frozen_row = next(
                item
                for item in frozen.snapshot_json["project_matrix"]
                if item["project_workspace_id"] == standalone.project_workspace_id
            )
            assert frozen_row["strategic_bucket"] == "UNCLASSIFIED"
            assert _authorities(db) == before


def test_wave3a_two_actor_lifecycle_snapshot_preview_freeze_idempotency_and_sod():
    with TestClient(app):
        with SessionLocal() as db:
            fixture = _fixture(db)
            service, reviewer = fixture["preparer"], fixture["reviewer"]
            before = _authorities(db)
            payload, create_key = _payload(fixture), _key("create")
            review = service.create_session(payload, create_key)
            assert service.create_session(payload, create_key).id == review.id
            assert review.review_number.startswith("PRV-") and review.status == "DRAFT"
            with pytest.raises(HTTPException) as drift:
                service.create_session(payload.model_copy(update={"title": "Different payload"}), create_key)
            assert drift.value.status_code == 409 and drift.value.detail["code"] == "IDEMPOTENCY_KEY_REUSED"
            review = service.prepare_session(review.id, review.revision_version)
            preview = service.snapshot_preview(review.id)
            assert preview.persisted is False and preview.readiness["status"] == "READY"
            assert preview.snapshot["contract_version"] == "WAVE3A_PORTFOLIO_REVIEW_SNAPSHOT_V1"
            assert preview.source_index["STRATEGIC_ALLOCATION"]["record_id"] == fixture["plan"].id
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(PortfolioReviewSnapshot)
                    .where(PortfolioReviewSnapshot.review_session_id == review.id)
                )
                == 0
            )
            freeze_key, freeze_payload = _key("freeze"), SnapshotCommandIn(reason="Governance evidence")
            snapshot = service.freeze_snapshot(review.id, freeze_payload, review.revision_version, freeze_key)
            assert (
                service.freeze_snapshot(review.id, freeze_payload, review.revision_version, freeze_key).id
                == snapshot.id
            )
            assert snapshot.snapshot_hash == preview.candidate_snapshot_hash
            assert snapshot.snapshot_json["portfolio_ranking"]["items"]
            ready = service.get_session(review.id)
            assert ready.status == "READY_FOR_REVIEW" and ready.source_current
            matrix = service.project_matrix(review.id)
            stale_matrix = service.project_matrix(review.id, stale=True)
            current_matrix = service.project_matrix(review.id, stale=False)
            assert all(item.stale for item in stale_matrix.items)
            assert all(not item.stale for item in current_matrix.items)
            stale_ids = {item.project_workspace_id for item in stale_matrix.items}
            current_ids = {item.project_workspace_id for item in current_matrix.items}
            assert stale_ids.isdisjoint(current_ids)
            assert stale_ids | current_ids == {item.project_workspace_id for item in matrix.items}
            assert stale_matrix.total + current_matrix.total == matrix.total
            opened = reviewer.start_review(review.id, ready.revision_version)
            reviewer.create_conclusion(
                review.id,
                PortfolioReviewConclusionCreate(
                    conclusion_type="PORTFOLIO_BALANCED", rationale="No domain authority is overridden."
                ),
                opened.revision_version,
            )
            version = reviewer.get_session(review.id).revision_version
            with pytest.raises(HTTPException) as sod:
                service.complete_review(review.id, CompleteReviewIn(), version, _key("self-complete"))
            assert sod.value.status_code == 409 and sod.value.detail["code"] == "SOD_REVIEW_PREPARER_CANNOT_COMPLETE"
            complete_key = _key("complete")
            completed = reviewer.complete_review(review.id, CompleteReviewIn(), version, complete_key)
            assert completed.status == "COMPLETED" and "update" not in completed.allowed_actions
            assert reviewer.complete_review(review.id, CompleteReviewIn(), version, complete_key).id == review.id
            assert _authorities(db) == before
            assert any(item.event_type == "portfolio_review.snapshot.frozen" for item in reviewer.history(review.id))


@pytest.mark.parametrize(
    "action_type",
    [
        "HOLD_FOR_CAPACITY",
        "REQUEST_REASSESSMENT",
        "REBALANCE_CAPITAL",
        "MOVE_BETWEEN_BUCKETS",
        "REQUEST_GATE_REVALIDATION",
    ],
)
def test_wave3a_action_semantics_are_request_only_without_source_mutations(action_type):
    with TestClient(app):
        with SessionLocal() as db:
            fixture = _fixture(db)
            service, reviewer = fixture["preparer"], fixture["reviewer"]
            review = _open(fixture)
            before = _authorities(db)
            ranking = PortfolioEvaluationService(
                db, fixture["author"].tenant_id, fixture["author"].id, _context(fixture["author"])
            ).ranking_projection(fixture["portfolio"].id)
            payload = PortfolioReviewActionCreate(
                subject_type="PROJECT",
                subject_id=fixture["projects"][0].id,
                action_type=action_type,
                rationale="Request source authority; no implicit execution.",
                owner_user_id=fixture["authority"].id,
                due_date=date.today() - timedelta(days=1),
            )
            key = _key("action")
            action = service.create_action(review.id, payload, review.revision_version, key)
            assert service.create_action(review.id, payload, review.revision_version, key).id == action.id
            with pytest.raises(HTTPException) as sod:
                service.approve_action(action.id, ActionApprovalIn(), action.revision_version, _key("self-approve"))
            assert sod.value.detail["code"] == "SOD_ACTION_CREATOR_CANNOT_APPROVE"
            approval_key = _key("approve")
            accepted = reviewer.approve_action(action.id, ActionApprovalIn(), action.revision_version, approval_key)
            assert (
                reviewer.approve_action(action.id, ActionApprovalIn(), action.revision_version, approval_key).id
                == action.id
            )
            assert accepted.approved_by_user_id == fixture["authority"].id
            dispatch_key = _key("dispatch")
            dispatched = reviewer.dispatch_action(
                action.id, ActionDispatchIn(), accepted.revision_version, dispatch_key
            )
            assert (
                reviewer.dispatch_action(
                    action.id, ActionDispatchIn(), accepted.revision_version, dispatch_key
                ).execution_reference
                == dispatched.execution_reference
            )
            assert dispatched.dispatch_status == "REQUEST_RECORDED"
            assert (
                dispatched.source_mutation_performed is False
                and dispatched.authority_effect == "GOVERNANCE_REQUEST_ONLY"
            )
            assert dispatched.execution_reference.startswith("PORTFOLIO_REVIEW_REQUEST:")
            assert dispatched.status == "ACCEPTED" and dispatched.overdue
            assert _authorities(db) == before
            assert (
                PortfolioEvaluationService(
                    db, fixture["author"].tenant_id, fixture["author"].id, _context(fixture["author"])
                ).ranking_projection(fixture["portfolio"].id)
                == ranking
            )
            gate = reviewer.gate_status(review.id)
            assert gate.semantic_boundary == "GATE07K_HOLD_IS_NOT_PORTFOLIO_HOLD_FOR_CAPACITY"
            assert {item["outcome"] for item in gate.investment_decisions} == {"GO"}
            assert reviewer.list_actions(review_session_id=review.id, overdue=True).total == 1


def test_wave3a_action_acceptance_cannot_bypass_approval_through_update():
    with TestClient(app):
        with SessionLocal() as db:
            fixture = _fixture(db, sources=False)
            review = _open(fixture)
            action = fixture["preparer"].create_action(
                review.id,
                PortfolioReviewActionCreate(
                    action_type="HOLD_FOR_CAPACITY",
                    rationale="Governed approval is mandatory.",
                    owner_user_id=fixture["authority"].id,
                ),
                review.revision_version,
                _key("action"),
            )
            with pytest.raises(HTTPException) as bypass:
                fixture["preparer"].update_action(
                    action.id, PortfolioReviewActionUpdate(status="ACCEPTED"), action.revision_version
                )
            assert bypass.value.status_code in {403, 409, 422}
            stored = db.get(PortfolioReviewAction, action.id)
            assert stored.status == "OPEN" and stored.approved_by_user_id is None


@pytest.mark.parametrize(
    "source_key",
    [
        "PORTFOLIO_RANK",
        "STRATEGIC_ALLOCATION",
        "BUDGET_SCENARIO",
        "RESOURCE_SCENARIO",
        "SCENARIO_RECOMMENDATION",
        "GATE_CONTEXT",
        "RISK_READINESS",
    ],
)
def test_wave3a_required_missing_sources_block_readiness_and_freeze(source_key):
    with TestClient(app):
        with SessionLocal() as db:
            fixture = _fixture(db, sources=False)
            service = fixture["preparer"]
            published = next(
                item for item in service.configurations() if item.code == "default" and item.status == "published"
            )
            draft = service.clone_configuration(
                published.id, published.version, target_workspace_id=fixture["portfolio"].id
            )
            content = deepcopy(draft.content_json)
            content["snapshot_policy"]["required_sources"] = ["PORTFOLIO_MEMBERSHIP", source_key]
            draft = service.update_configuration(
                draft.id,
                draft.version,
                name="Required source policy",
                description="Missing authority must block.",
                content=content,
            )
            service.publish_configuration(draft.id, draft.version)
            review = service.create_session(_payload(fixture), _key("create"))
            review = service.prepare_session(review.id, review.revision_version)
            preview = service.snapshot_preview(review.id)
            assert preview.persisted is False and preview.readiness["status"] == "BLOCKED"
            assert any(source_key in item and "not available" in item for item in preview.blockers)
            with pytest.raises(HTTPException) as blocked:
                service.freeze_snapshot(review.id, SnapshotCommandIn(), review.revision_version, _key("freeze"))
            assert blocked.value.status_code == 409 and blocked.value.detail["code"] == "PORTFOLIO_REVIEW_NOT_READY"


def test_wave3a_snapshot_staleness_refresh_and_source_history_remain_immutable():
    with TestClient(app):
        with SessionLocal() as db:
            fixture = _fixture(db)
            service = fixture["preparer"]
            review = _ready(fixture)
            snapshot = db.get(PortfolioReviewSnapshot, review.current_snapshot_id)
            before = deepcopy(snapshot.snapshot_json)
            membership = fixture["memberships"][-1]
            membership.status = "INACTIVE"
            membership.updated_by = fixture["author"].id
            db.commit()
            stale = service.get_session(review.id)
            assert stale.snapshot_stale and stale.effective_status == "STALE" and not stale.source_current
            assert db.get(PortfolioReviewSnapshot, snapshot.id).snapshot_json == before
            preview = service.snapshot_preview(review.id)
            assert preview.persisted is False and preview.stale
            assert any(
                item["category"] == "PORTFOLIO_MEMBERSHIP"
                and membership.project_workspace_id in item["removed_project_ids"]
                for item in preview.changes
            )
            with pytest.raises(HTTPException) as blocked:
                fixture["reviewer"].start_review(review.id, stale.revision_version)
            assert blocked.value.detail["code"] == "PORTFOLIO_REVIEW_SNAPSHOT_STALE"
            refreshed = service.freeze_snapshot(
                review.id, SnapshotCommandIn(reason="Governed refresh"), stale.revision_version, _key("refreeze")
            )
            assert refreshed.id != snapshot.id and refreshed.snapshot_version == snapshot.snapshot_version + 1
            assert db.get(PortfolioReviewSnapshot, snapshot.id).snapshot_json == before
            assert service.get_session(review.id).source_current


def test_wave3a_completed_history_trends_and_comparison_never_reinterpret_live_sources():
    with TestClient(app):
        with SessionLocal() as db:
            fixture = _fixture(db)
            service, reviewer = fixture["preparer"], fixture["reviewer"]
            first = _open(fixture, review_date=date(2026, 7, 6))
            action = service.create_action(
                first.id,
                PortfolioReviewActionCreate(
                    action_type="REQUEST_REASSESSMENT",
                    rationale="Follow-up remains open after the Review closes.",
                    owner_user_id=fixture["authority"].id,
                ),
                first.revision_version,
                _key("action"),
            )
            first = _complete(fixture, first)
            root = db.get(PortfolioReviewSession, first.id)
            completion, completion_hash = deepcopy(root.completion_snapshot_json), root.completion_hash
            frozen = deepcopy(db.get(PortfolioReviewSnapshot, first.current_snapshot_id).snapshot_json)
            before_history = [item.model_dump(mode="json") for item in reviewer.history(first.id)]
            with pytest.raises(HTTPException) as immutable:
                service.update_session(
                    first.id, PortfolioReviewUpdate(title="Historical overwrite"), first.revision_version
                )
            assert immutable.value.status_code == 409
            with pytest.raises(HTTPException):
                service.snapshot_preview(first.id)
            with pytest.raises(HTTPException):
                reviewer.update_conclusion(
                    first.conclusions[0].id,
                    PortfolioReviewConclusionUpdate(
                        conclusion_type="CAPITAL_CONSTRAINED", rationale="A completed conclusion cannot change."
                    ),
                    first.conclusions[0].revision_version,
                )
            accepted = reviewer.approve_action(
                action.id, ActionApprovalIn(), action.revision_version, _key("approve-followup")
            )
            service.update_action(action.id, PortfolioReviewActionUpdate(status="COMPLETED"), accepted.revision_version)
            membership = fixture["memberships"][-1]
            membership.status = "INACTIVE"
            db.commit()
            second = _complete(fixture, _open(fixture, review_date=date(2026, 10, 6)))
            comparison = reviewer.compare(second.id, first.id)
            assert comparison.historical_only
            assert comparison.deltas["portfolio_membership"]["removed_project_ids"] == [membership.project_workspace_id]
            assert comparison.other_snapshot_hash == first.current_snapshot_hash
            trends = reviewer.trends(fixture["portfolio"].id)
            assert trends.interpolation_applied is False
            assert [item.portfolio_project_count for item in trends.points] == [3, 2]
            assert trends.points[0].open_action_count_at_close == 1
            assert [item.model_dump(mode="json") for item in reviewer.history(first.id)] == before_history
            db.refresh(root)
            assert root.completion_snapshot_json == completion and root.completion_hash == completion_hash
            assert db.get(PortfolioReviewSnapshot, first.current_snapshot_id).snapshot_json == frozen
            historical = reviewer.get_session(first.id)
            assert historical.status == "COMPLETED" and not historical.snapshot_stale
            assert reviewer.project_matrix(first.id).total == 3
            assert reviewer.project_matrix(second.id).total == 2


def _assign(db, admin, user, role_code, *, workspace_id=None):
    ensure_enterprise_permissions(db, user.tenant_id, user.id)
    role = db.scalar(
        select(SecurityRole).where(SecurityRole.tenant_id == user.tenant_id, SecurityRole.code == role_code)
    )
    assert role is not None, role_code
    db.add(
        SecurityAccessAssignment(
            tenant_id=user.tenant_id,
            subject_type="user",
            user_id=user.id,
            role_id=role.id,
            scope_type="workspace" if workspace_id else "organization",
            workspace_id=workspace_id,
            status="active",
            granted_by_user_id=admin.id if admin.tenant_id == user.tenant_id else user.id,
        )
    )
    db.commit()


def test_wave3a_http_etag_idempotency_and_admin_user_approval_dispatch_rbac():
    with TestClient(app) as client:
        with SessionLocal() as db:
            fixture = _fixture(db, sources=False)
            admin = fixture["author"]
            preparer = _user(db, admin.tenant_id, "wave3a-http-preparer")
            config_admin = _user(db, admin.tenant_id, "wave3a-http-config")
            _assign(db, admin, preparer, "portfolio_review_preparer")
            _assign(db, admin, config_admin, "portfolio_review_configuration_admin")
            headers, config_headers = _token_headers(preparer), _token_headers(config_admin)
            payload = _payload(fixture).model_dump(mode="json")
            assert client.post("/api/v1/portfolio-reviews", headers=headers, json=payload).status_code == 422
            created = client.post(
                "/api/v1/portfolio-reviews", headers={**headers, "Idempotency-Key": _key("http-create")}, json=payload
            )
            assert created.status_code == 201, created.text
            review_id, etag = created.json()["id"], created.headers["etag"]
            assert etag == f'"{created.json()["revision_version"]}"'
            assert (
                client.put(
                    f"/api/v1/portfolio-reviews/{review_id}", headers=headers, json={"title": "Missing precondition"}
                ).status_code
                == 422
            )
            updated = client.put(
                f"/api/v1/portfolio-reviews/{review_id}",
                headers={**headers, "If-Match": etag},
                json={"title": "Governed header update"},
            )
            assert updated.status_code == 200, updated.text
            mismatch = client.put(
                f"/api/v1/portfolio-reviews/{review_id}",
                headers={**headers, "If-Match": etag},
                json={"title": "Stale request"},
            )
            assert mismatch.status_code == 412 and mismatch.json()["detail"]["code"] == "ETAG_MISMATCH"
            assert client.get("/api/v1/portfolio-reviews/admin/configurations", headers=headers).status_code == 403
            assert (
                client.get("/api/v1/portfolio-reviews/admin/configurations", headers=config_headers).status_code == 200
            )
            assert (
                client.post(
                    "/api/v1/portfolio-reviews",
                    headers={**config_headers, "Idempotency-Key": _key("config-live")},
                    json=payload,
                ).status_code
                == 403
            )
            review = fixture["preparer"].prepare_session(review_id, updated.json()["revision_version"])
            action = fixture["preparer"].create_action(
                review.id,
                PortfolioReviewActionCreate(
                    action_type="REBALANCE_CAPITAL", rationale="Explicit permission needed.", owner_user_id=preparer.id
                ),
                review.revision_version,
                _key("rbac-action"),
            )
            command_headers = {
                **headers,
                "If-Match": f'"{action.revision_version}"',
                "Idempotency-Key": _key("rbac-command"),
            }
            assert (
                client.post(
                    f"/api/v1/portfolio-review-actions/{action.id}/approve", headers=command_headers, json={}
                ).status_code
                == 403
            )
            assert (
                client.post(
                    f"/api/v1/portfolio-review-actions/{action.id}/dispatch", headers=command_headers, json={}
                ).status_code
                == 403
            )


def test_wave3a_http_tenant_and_workspace_scope_are_enforced_for_all_read_models():
    with TestClient(app) as client:
        with SessionLocal() as db:
            fixture = _fixture(db, sources=False)
            review = _ready(fixture)
            admin = fixture["author"]
            other_portfolio = _portfolio(db, admin, fixture["enterprise"], label="unrelated scope")
            scoped = _user(db, admin.tenant_id, "wave3a-scoped-viewer")
            _assign(db, admin, scoped, "portfolio_review_viewer", workspace_id=other_portfolio.id)
            tenant = Tenant(name="Wave 3A other tenant", slug=f"wave3a-other-{uuid4().hex[:10]}")
            db.add(tenant)
            db.commit()
            outsider = _user(db, tenant.id, "wave3a-other-tenant")
            _assign(db, outsider, outsider, "portfolio_review_viewer")
            read_paths = [
                f"/api/v1/portfolio-reviews/{review.id}",
                f"/api/v1/portfolio-reviews/{review.id}/project-matrix",
                f"/api/v1/portfolio-reviews/{review.id}/allocation",
                f"/api/v1/portfolio-reviews/{review.id}/budget-resources",
                f"/api/v1/portfolio-reviews/{review.id}/gate-status",
                f"/api/v1/portfolio-reviews/{review.id}/history",
            ]
            for path in read_paths:
                assert client.get(path, headers=_token_headers(scoped)).status_code == 403, path
                assert client.get(path, headers=_token_headers(outsider)).status_code == 404, path
            listing = client.get("/api/v1/portfolio-reviews", headers=_token_headers(scoped))
            assert listing.status_code == 200 and listing.json()["total"] == 0
            assert (
                client.get(
                    f"/api/v1/portfolio-reviews/trends?portfolio_workspace_id={fixture['portfolio'].id}",
                    headers=_token_headers(scoped),
                ).status_code
                == 403
            )


def test_wave3a_options_do_not_disclose_allocation_plans_outside_workspace_or_tenant_scope():
    with TestClient(app) as client:
        with SessionLocal() as db:
            fixture = _fixture(db)
            admin = fixture["author"]
            portfolio = fixture["portfolio"]
            other_portfolio = _portfolio(db, admin, fixture["enterprise"], label="other options scope")
            permitted = _user(db, admin.tenant_id, "wave3a-options-permitted")
            denied = _user(db, admin.tenant_id, "wave3a-options-denied")
            _assign(db, admin, permitted, "portfolio_review_viewer", workspace_id=portfolio.id)
            _assign(db, admin, denied, "portfolio_review_viewer", workspace_id=other_portfolio.id)
            tenant = Tenant(name="Wave 3A options other tenant", slug=f"wave3a-options-{uuid4().hex[:10]}")
            db.add(tenant)
            db.commit()
            outsider = _user(db, tenant.id, "wave3a-options-outsider")
            _assign(db, outsider, outsider, "portfolio_review_viewer")
            PortfolioReviewService(db, tenant.id, outsider.id, _context(outsider, "organization_admin")).ensure_seed()

            endpoint = "/api/v1/portfolio-reviews/options"
            allowed = client.get(endpoint, headers=_token_headers(permitted))
            assert allowed.status_code == 200, allowed.text
            assert [item["id"] for item in allowed.json()["allocation_plans"]] == [fixture["plan"].id]
            assert {item["id"] for item in allowed.json()["portfolios"]} == {portfolio.id}
            for actor in (denied, outsider):
                response = client.get(endpoint, headers=_token_headers(actor))
                assert response.status_code == 200, response.text
                assert response.json()["allocation_plans"] == []
            explicit = client.get(f"{endpoint}?portfolio_workspace_id={portfolio.id}", headers=_token_headers(denied))
            assert explicit.status_code == 403
            organization_wide = client.get(endpoint, headers=_token_headers(admin))
            assert organization_wide.status_code == 200, organization_wide.text
            assert fixture["plan"].id in {item["id"] for item in organization_wide.json()["allocation_plans"]}


def test_wave3a_automatic_allocation_selection_never_uses_another_portfolios_enterprise_plan():
    with TestClient(app):
        with SessionLocal() as db:
            fixture = _fixture(db)
            service = fixture["preparer"]
            own_plan = db.get(StrategicCapitalAllocationPlan, fixture["plan"].id)
            other_portfolio = _portfolio(db, fixture["author"], fixture["enterprise"], label="other plan scope")
            plan_values = {
                column.name: deepcopy(getattr(own_plan, column.name))
                for column in StrategicCapitalAllocationPlan.__table__.columns
                if column.name != "id"
            }
            token = uuid4().hex[:10]
            plan_values.update(
                allocation_plan_number=f"W3A-OTHER-{token}",
                logical_code=f"W3A-OTHER-{token}",
                portfolio_workspace_id=other_portfolio.id,
                create_idempotency_key=_key("other-plan"),
                submit_idempotency_key=None,
                review_idempotency_key=None,
                endorse_idempotency_key=None,
                endorsed_at=own_plan.endorsed_at + timedelta(days=1),
            )
            other_plan = StrategicCapitalAllocationPlan(**plan_values)
            db.add(other_plan)
            db.commit()
            before = _authorities(db)
            review = service.create_session(
                _payload(fixture).model_copy(update={"allocation_plan_id": None}), _key("automatic-plan")
            )
            review = service.prepare_session(review.id, review.revision_version)
            candidate = service.snapshot_preview(review.id)
            assert candidate.snapshot["allocation_plan"]["id"] == own_plan.id
            frozen = service.freeze_snapshot(
                review.id, SnapshotCommandIn(), review.revision_version, _key("freeze-automatic-plan")
            )
            assert service.get_session(review.id).allocation_plan_id == own_plan.id
            assert frozen.snapshot_json["allocation_plan"]["id"] != other_plan.id
            assert _authorities(db) == before

            # A portfolio-less plan still belongs to its own workspace authority.
            generic_plan = StrategicCapitalAllocationPlan(
                **{
                    **plan_values,
                    "allocation_plan_number": f"W3A-GENERIC-{token}",
                    "logical_code": f"W3A-GENERIC-{token}",
                    "portfolio_workspace_id": None,
                    "scope_workspace_id": other_portfolio.id,
                    "create_idempotency_key": _key("generic-plan"),
                }
            )
            db.add(generic_plan)
            db.commit()
            scoped = PortfolioReviewService(
                db,
                fixture["author"].tenant_id,
                fixture["author"].id,
                replace(
                    _context(fixture["author"], "portfolio_review_preparer"),
                    organization_wide=False,
                    workspace_ids=frozenset({fixture["portfolio"].id, *(item.id for item in fixture["projects"])}),
                ),
            )
            with pytest.raises(HTTPException) as outside_scope:
                scoped.create_session(
                    _payload(fixture).model_copy(update={"allocation_plan_id": generic_plan.id}),
                    _key("foreign-generic-plan"),
                )
            assert outside_scope.value.status_code == 403
            with pytest.raises(HTTPException) as incompatible_scope:
                service.create_session(
                    _payload(fixture).model_copy(update={"allocation_plan_id": generic_plan.id}),
                    _key("incompatible-generic-plan"),
                )
            assert incompatible_scope.value.detail["code"] == "PORTFOLIO_REVIEW_SCOPE_INCOMPATIBLE"

            # Cycle lineage must be compatible without demanding an ancestor grant.
            own_cycle = db.get(CapitalPlanningCycle, fixture["cycle"].id)
            cycle_values = {
                column.name: deepcopy(getattr(own_cycle, column.name))
                for column in CapitalPlanningCycle.__table__.columns
                if column.name != "id"
            }
            cycles = {}
            for label, scope_id in (("global", None), ("sibling", other_portfolio.id)):
                cycle = CapitalPlanningCycle(
                    **{
                        **cycle_values,
                        "cycle_number": f"W3A-{label}-{token}",
                        "scope_workspace_id": scope_id,
                        "create_idempotency_key": _key(f"{label}-cycle"),
                        "open_idempotency_key": None,
                        "review_idempotency_key": None,
                        "close_idempotency_key": None,
                    }
                )
                db.add(cycle)
                cycles[label] = cycle
            db.commit()
            for cycle in (fixture["cycle"], cycles["global"]):
                valid = scoped.create_session(
                    _payload(fixture).model_copy(update={"planning_cycle_id": cycle.id, "allocation_plan_id": None}),
                    _key("compatible-cycle"),
                )
                assert valid.planning_cycle_id == cycle.id
                assert scoped.snapshot_preview(valid.id).snapshot["planning_cycle_id"] == cycle.id
            with pytest.raises(HTTPException) as sibling_cycle:
                scoped.create_session(
                    _payload(fixture).model_copy(
                        update={"planning_cycle_id": cycles["sibling"].id, "allocation_plan_id": None}
                    ),
                    _key("sibling-cycle"),
                )
            assert sibling_cycle.value.detail["code"] == "PORTFOLIO_REVIEW_SCOPE_INCOMPATIBLE"

            bad_cycle_plan = StrategicCapitalAllocationPlan(
                **{
                    **plan_values,
                    "allocation_plan_number": f"W3A-CYCLE-{token}",
                    "logical_code": f"W3A-CYCLE-{token}",
                    "portfolio_workspace_id": fixture["portfolio"].id,
                    "planning_cycle_id": cycles["sibling"].id,
                    "create_idempotency_key": _key("incompatible-cycle-plan"),
                    "endorsed_at": own_plan.endorsed_at + timedelta(days=2),
                }
            )
            db.add(bad_cycle_plan)
            db.commit()
            before_cycles = _authorities(db)
            with pytest.raises(HTTPException) as inferred_cycle:
                scoped.create_session(
                    _payload(fixture).model_copy(
                        update={"planning_cycle_id": None, "allocation_plan_id": bad_cycle_plan.id}
                    ),
                    _key("inferred-sibling-cycle"),
                )
            assert inferred_cycle.value.detail["code"] == "PORTFOLIO_REVIEW_SCOPE_INCOMPATIBLE"
            automatic = scoped.create_session(
                _payload(fixture).model_copy(update={"planning_cycle_id": None, "allocation_plan_id": None}),
                _key("automatic-sibling-cycle"),
            )
            with pytest.raises(HTTPException) as automatic_cycle:
                scoped.snapshot_preview(automatic.id)
            assert automatic_cycle.value.detail["code"] == "PORTFOLIO_REVIEW_SCOPE_INCOMPATIBLE"

            # Revalidate old malformed sessions during automatic snapshot selection.
            legacy = db.get(PortfolioReviewSession, valid.id)
            legacy.planning_cycle_id = cycles["sibling"].id
            db.commit()
            with pytest.raises(HTTPException) as legacy_cycle:
                scoped.snapshot_preview(legacy.id)
            assert legacy_cycle.value.detail["code"] == "PORTFOLIO_REVIEW_SCOPE_INCOMPATIBLE"
            assert _authorities(db) == before_cycles


def test_wave3a_governance_model_is_opt_in_and_empty_portfolio_cannot_freeze():
    with TestClient(app):
        with SessionLocal() as db:
            fixture = _fixture(db, sources=False)
            service = fixture["preparer"]
            contractor = _portfolio(
                db, fixture["author"], fixture["enterprise"], governance_model="CONTRACTOR_DELIVERY"
            )
            with pytest.raises(HTTPException) as policy:
                service.create_session(
                    _payload(fixture).model_copy(update={"portfolio_workspace_id": contractor.id}), _key("contractor")
                )
            assert policy.value.detail["code"] == "PORTFOLIO_REVIEW_GOVERNANCE_MODEL_NOT_APPLICABLE"
            empty = _portfolio(db, fixture["author"], fixture["enterprise"], label="empty")
            review = service.create_session(
                _payload(fixture).model_copy(update={"portfolio_workspace_id": empty.id}), _key("empty")
            )
            review = service.prepare_session(review.id, review.revision_version)
            assert service.snapshot_preview(review.id).readiness["status"] == "BLOCKED"
            with pytest.raises(HTTPException) as blocked:
                service.freeze_snapshot(review.id, SnapshotCommandIn(), review.revision_version, _key("empty-freeze"))
            assert blocked.value.detail["code"] == "PORTFOLIO_REVIEW_NOT_READY"


def test_wave3a_admin_preview_is_nonpersisted_clone_keeps_scope_and_scoped_admin_cannot_escape():
    with TestClient(app) as client:
        with SessionLocal() as db:
            fixture = _fixture(db, sources=False)
            service = fixture["preparer"]
            admin = fixture["author"]
            published = next(
                item for item in service.configurations() if item.code == "default" and item.status == "published"
            )
            draft = service.clone_configuration(
                published.id, published.version, target_workspace_id=fixture["portfolio"].id
            )
            content = deepcopy(draft.content_json)
            content["cadence"]["frequency_days"] = 120
            baseline = (draft.version, deepcopy(draft.content_json), draft.content_hash)
            before_count = db.scalar(
                select(func.count())
                .select_from(AdminConfiguration)
                .where(AdminConfiguration.kind == CONFIGURATION_KIND)
            )
            preview = service.configuration_preview(fixture["portfolio"].id, configuration_id=draft.id, content=content)
            assert preview.persisted is False and preview.effective["cadence"]["frequency_days"] == 120
            db.refresh(draft)
            assert (draft.version, draft.content_json, draft.content_hash) == baseline
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(AdminConfiguration)
                    .where(AdminConfiguration.kind == CONFIGURATION_KIND)
                )
                == before_count
            )
            published_scoped = service.publish_configuration(draft.id, draft.version)
            clone = service.clone_configuration(published_scoped.id, published_scoped.version)
            assert clone.code == f"workspace-{fixture['portfolio'].id}"
            assert clone.content_json["scope"] == {"type": "workspace", "workspace_id": fixture["portfolio"].id}
            scoped_actor = _user(db, admin.tenant_id, "wave3a-scoped-config")
            _assign(
                db, admin, scoped_actor, "portfolio_review_configuration_admin", workspace_id=fixture["portfolio"].id
            )
            scoped_context = replace(
                _context(scoped_actor, "portfolio_review_configuration_admin"),
                organization_wide=False,
                workspace_ids=frozenset({fixture["portfolio"].id}),
            )
            scoped_service = PortfolioReviewService(db, admin.tenant_id, scoped_actor.id, scoped_context)
            assert (
                scoped_service.configuration_preview(fixture["portfolio"].id, configuration_id=clone.id).persisted
                is False
            )
            with pytest.raises(HTTPException) as escape:
                scoped_service.clone_configuration(published.id, published.version)
            assert escape.value.status_code == 403
            unrelated = _portfolio(db, admin, fixture["enterprise"], label="unrelated configuration scope")
            with pytest.raises(HTTPException) as unrelated_scope:
                scoped_service.clone_configuration(published.id, published.version, target_workspace_id=unrelated.id)
            assert unrelated_scope.value.status_code == 403
            headers = _token_headers(scoped_actor)
            response = client.post(
                "/api/v1/portfolio-reviews/admin/preview",
                headers=headers,
                json={
                    "portfolio_workspace_id": fixture["portfolio"].id,
                    "configuration_id": clone.id,
                    "content_json": content,
                },
            )
            assert response.status_code == 200, response.text
            assert response.json()["persisted"] is False
            denied = client.post(
                f"/api/v1/portfolio-reviews/admin/configurations/{published.id}/clone",
                headers={**headers, "If-Match": f'"{published.version}"'},
                json={},
            )
            assert denied.status_code == 403


@pytest.mark.parametrize("field", ["title", "review_date", "chair_user_id", "agenda"])
def test_wave3a_http_null_required_update_is_validation_error_and_does_not_mutate(field):
    with TestClient(app) as client:
        with SessionLocal() as db:
            fixture = _fixture(db, sources=False)
            review = fixture["preparer"].create_session(_payload(fixture), _key("null-create"))
            baseline = review.model_dump(mode="json")
            response = client.put(
                f"/api/v1/portfolio-reviews/{review.id}",
                headers={**_token_headers(fixture["author"]), "If-Match": f'"{review.revision_version}"'},
                json={field: None},
            )
            assert response.status_code == 422, response.text
            db.expire_all()
            assert fixture["preparer"].get_session(review.id).model_dump(mode="json") == baseline


def test_wave3a_bucket_subject_and_source_authority_are_controlled_not_arbitrary():
    with TestClient(app):
        with SessionLocal() as db:
            fixture = _fixture(db)
            review = _open(fixture)
            service = fixture["preparer"]
            before = _authorities(db)
            payload = PortfolioReviewActionCreate(
                subject_type="BUCKET",
                subject_key="grow",
                action_type="MOVE_BETWEEN_BUCKETS",
                rationale="Explicit bucket request through Wave 2A authority.",
                owner_user_id=fixture["authority"].id,
            )
            for invalid in (
                payload.model_copy(update={"subject_key": "unknown-bucket"}),
                payload.model_copy(update={"subject_key": None}),
                payload.model_copy(update={"subject_id": fixture["projects"][0].id}),
                payload.model_copy(update={"requested_source_authority": "INVESTMENT_GATE"}),
            ):
                with pytest.raises(HTTPException) as blocked:
                    service.create_action(review.id, invalid, review.revision_version, _key("invalid-bucket"))
                assert blocked.value.status_code == 422
            action = service.create_action(review.id, payload, review.revision_version, _key("bucket"))
            assert action.subject_type == "BUCKET" and action.subject_key == "grow" and action.subject_id is None
            assert action.requested_source_authority == "STRATEGIC_CAPITAL_ALLOCATION"
            assert _authorities(db) == before


def test_wave3a_controlled_return_cancel_supersede_transitions_are_idempotent_and_terminal():
    with TestClient(app):
        with SessionLocal() as db:
            fixture = _fixture(db, sources=False)
            service, reviewer = fixture["preparer"], fixture["reviewer"]
            ready = _ready(fixture)
            transition = ReviewTransitionIn(reason="Package returned for governed corrections.")
            key = _key("return")
            returned = reviewer.transition_session(ready.id, "RETURNED", transition, ready.revision_version, key)
            assert returned.status == "RETURNED"
            assert (
                reviewer.transition_session(
                    ready.id, "RETURNED", transition, ready.revision_version, key
                ).revision_version
                == returned.revision_version
            )
            preparing = service.prepare_session(returned.id, returned.revision_version)
            cancel_key = _key("cancel")
            cancelled = reviewer.transition_session(
                preparing.id,
                "CANCELLED",
                ReviewTransitionIn(reason="Review no longer required."),
                preparing.revision_version,
                cancel_key,
            )
            assert cancelled.status == "CANCELLED"
            with pytest.raises(HTTPException):
                service.prepare_session(cancelled.id, cancelled.revision_version)
            old = service.create_session(_payload(fixture), _key("old"))
            replacement = service.create_session(_payload(fixture, review_date=date(2027, 1, 6)), _key("replacement"))
            with pytest.raises(HTTPException) as self_replacement:
                reviewer.transition_session(
                    old.id,
                    "SUPERSEDED",
                    ReviewTransitionIn(reason="Invalid self successor.", replacement_review_session_id=old.id),
                    old.revision_version,
                    _key("self-replacement"),
                )
            assert self_replacement.value.status_code == 422
            supersede_key = _key("supersede")
            supersede_payload = ReviewTransitionIn(
                reason="Successor review uses corrected period.", replacement_review_session_id=replacement.id
            )
            superseded = reviewer.transition_session(
                old.id, "SUPERSEDED", supersede_payload, old.revision_version, supersede_key
            )
            assert superseded.status == "SUPERSEDED"
            assert (
                reviewer.transition_session(
                    old.id, "SUPERSEDED", supersede_payload, old.revision_version, supersede_key
                ).id
                == old.id
            )
            with pytest.raises(HTTPException):
                service.update_session(
                    old.id, PortfolioReviewUpdate(title="No historical overwrite"), superseded.revision_version
                )
            completed = _complete(fixture, _open(fixture))
            with pytest.raises(HTTPException):
                reviewer.transition_session(
                    completed.id,
                    "CANCELLED",
                    ReviewTransitionIn(reason="Completed cannot cancel."),
                    completed.revision_version,
                    _key("completed-cancel"),
                )


@pytest.mark.parametrize("terminal_status", ["CANCELLED", "SUPERSEDED"])
def test_wave3a_cancelled_and_superseded_reviews_do_not_allow_action_mutations(terminal_status):
    with TestClient(app):
        with SessionLocal() as db:
            fixture = _fixture(db, sources=False)
            service, reviewer = fixture["preparer"], fixture["reviewer"]
            review = _open(fixture)
            actions = []
            for index in range(2):
                actions.append(
                    service.create_action(
                        review.id,
                        PortfolioReviewActionCreate(
                            action_type="HOLD_FOR_CAPACITY",
                            rationale=f"Governed request {index}.",
                            owner_user_id=fixture["authority"].id,
                        ),
                        service.get_session(review.id).revision_version,
                        _key("terminal-action"),
                    )
                )
            accepted = reviewer.approve_action(
                actions[1].id, ActionApprovalIn(), actions[1].revision_version, _key("terminal-approve-before")
            )
            replacement = (
                service.create_session(_payload(fixture), _key("terminal-replacement"))
                if terminal_status == "SUPERSEDED"
                else None
            )
            transition = ReviewTransitionIn(
                reason="Governed terminal transition.",
                replacement_review_session_id=replacement.id if replacement else None,
            )
            reviewer.transition_session(
                review.id,
                terminal_status,
                transition,
                service.get_session(review.id).revision_version,
                _key("terminal-parent"),
            )
            commands = [
                lambda: reviewer.approve_action(
                    actions[0].id, ActionApprovalIn(), actions[0].revision_version, _key("terminal-approve-after")
                ),
                lambda: reviewer.dispatch_action(
                    accepted.id, ActionDispatchIn(), accepted.revision_version, _key("terminal-dispatch-after")
                ),
                lambda: service.update_action(
                    actions[0].id,
                    PortfolioReviewActionUpdate(rationale="Must remain unchanged."),
                    actions[0].revision_version,
                ),
            ]
            for command in commands:
                with pytest.raises(HTTPException) as blocked:
                    command()
                assert blocked.value.status_code == 409
                assert blocked.value.detail["code"] == "PORTFOLIO_REVIEW_ACTION_PARENT_IMMUTABLE"
            db.expire_all()
            assert db.get(PortfolioReviewAction, actions[0].id).status == "OPEN"
            assert db.get(PortfolioReviewAction, actions[1].id).dispatch_status == "NOT_REQUESTED"


def test_wave3a_action_owner_with_other_nonprivileged_role_cannot_edit_someone_elses_action():
    with TestClient(app):
        with SessionLocal() as db:
            fixture = _fixture(db, sources=False)
            review = _open(fixture)
            actor = _user(db, fixture["author"].tenant_id, "wave3a-owner-with-approver")
            action = fixture["preparer"].create_action(
                review.id,
                PortfolioReviewActionCreate(
                    action_type="HOLD_FOR_CAPACITY",
                    rationale="Owned by another actor.",
                    owner_user_id=fixture["authority"].id,
                ),
                review.revision_version,
                _key("owner-role-action"),
            )
            owner_service = PortfolioReviewService(
                db,
                actor.tenant_id,
                actor.id,
                _context(actor, "portfolio_review_action_owner", "portfolio_review_action_approver"),
            )
            with pytest.raises(HTTPException) as denied:
                owner_service.update_action(
                    action.id,
                    PortfolioReviewActionUpdate(rationale="No privilege implied by an unrelated role."),
                    action.revision_version,
                )
            assert denied.value.status_code == 403 and denied.value.detail["code"] == "REVIEW_ACTION_OWNER_SCOPE_DENIED"


def test_wave3a_http_owner_organization_and_preparer_scoped_grants_do_not_cross_multiply():
    with TestClient(app) as client:
        with SessionLocal() as db:
            fixture = _fixture(db, sources=False)
            review_b = _open(fixture)
            actor = _user(db, fixture["author"].tenant_id, "wave3a-mixed-scope-owner")
            portfolio_a = _portfolio(db, fixture["author"], fixture["enterprise"], label="preparer-only scope A")
            _assign(db, fixture["author"], actor, "portfolio_review_action_owner")
            _assign(db, fixture["author"], actor, "portfolio_review_preparer", workspace_id=portfolio_a.id)
            service = fixture["preparer"]
            other_b = service.create_action(
                review_b.id,
                PortfolioReviewActionCreate(
                    action_type="HOLD_FOR_CAPACITY",
                    rationale="Portfolio B action owned by someone else.",
                    owner_user_id=fixture["authority"].id,
                ),
                service.get_session(review_b.id).revision_version,
                _key("mixed-other-b"),
            )
            own_b = service.create_action(
                review_b.id,
                PortfolioReviewActionCreate(
                    action_type="HOLD_FOR_CAPACITY",
                    rationale="Portfolio B action owned by the actor.",
                    owner_user_id=actor.id,
                ),
                service.get_session(review_b.id).revision_version,
                _key("mixed-own-b"),
            )
            fixture_a = {**fixture, "portfolio": portfolio_a}
            review_a = service.create_session(_payload(fixture_a), _key("mixed-review-a"))
            review_a = service.prepare_session(review_a.id, review_a.revision_version)
            other_a = service.create_action(
                review_a.id,
                PortfolioReviewActionCreate(
                    action_type="HOLD_FOR_CAPACITY",
                    rationale="Portfolio A action under preparer scope.",
                    owner_user_id=fixture["authority"].id,
                ),
                review_a.revision_version,
                _key("mixed-other-a"),
            )
            for action, expected in ((other_b, 403), (own_b, 200), (other_a, 200)):
                response = client.put(
                    f"/api/v1/portfolio-review-actions/{action.id}",
                    headers={**_token_headers(actor), "If-Match": f'"{action.revision_version}"'},
                    json={"rationale": "Scope-specific governed update."},
                )
                assert response.status_code == expected, response.text
            db.expire_all()
            assert db.get(PortfolioReviewAction, other_b.id).rationale == "Portfolio B action owned by someone else."
