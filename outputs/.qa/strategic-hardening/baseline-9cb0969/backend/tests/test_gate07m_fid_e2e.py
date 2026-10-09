"""Gate 07M-FID full-stack service revalidation on one PYP-FFA Project.

The fixture intentionally uses the public domain services end to end.  Direct
ORM writes are limited to identities and upstream proposal/configuration seed
records that have no dedicated factory outside HTTP authentication/bootstrap.
"""

from __future__ import annotations

import json
import os
from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from tests.test_funds_manager_gate07j_fund import _published_policy as published_funds_policy
from tests.test_investment_decision_gate07k import _maker
from tests.test_investment_gate_preparation_gate07j import _profile, _reviewer
from tests.test_portfolio_analysis_gate07f import _complete, _context, _portfolio, _project
from tests.test_project_definition_gate07j_fel import _complete_current, _framework
from tests.test_risk_readiness_gate07j_risk import _complete as complete_risk
from tests.test_risk_readiness_gate07j_risk import _low_risk
from tests.test_risk_readiness_gate07j_risk import _publish as publish_risk

from app.core.time import utc_now
from app.database.session import SessionLocal
from app.domain.models import AdminConfiguration, EnterpriseWorkspace, UserAccount
from app.main import app
from app.modules.business_case.service import (
    CONFIGURATION_KIND as BUSINESS_CASE_CONFIGURATION_KIND,
)
from app.modules.business_case.service import (
    DEFAULT_CONFIGURATION as BUSINESS_CASE_CONFIGURATION,
)
from app.modules.business_case.service import BusinessCaseService
from app.modules.economic_financial_model.service import EconomicFinancialModelService
from app.modules.funds_manager.models import StrategicFundingSource
from app.modules.funds_manager.schemas import FundCreateIn, FundingAssignmentCreateIn, FundingSourceCreateIn
from app.modules.funds_manager.service import FundsManagerService
from app.modules.idea_demand.models import Idea, IdeaEvaluation
from app.modules.investment_decision.schemas import (
    ChecklistAcknowledgement,
    DecisionCreateIn,
    DecisionDecideIn,
    DecisionReadyIn,
    DecisionUpdateIn,
)
from app.modules.investment_decision.service import InvestmentDecisionService
from app.modules.investment_evidence_policy.service import (
    CONFIGURATION_KIND as EVIDENCE_POLICY_KIND,
)
from app.modules.investment_evidence_policy.service import (
    DEFAULT_POLICY,
    InvestmentEvidencePolicyService,
    gate07m_evid_policy_update,
)
from app.modules.investment_evidence_policy.service import (
    _hash as evidence_policy_hash,
)
from app.modules.investment_gate_preparation.schemas import EvidenceValidationIn, ManualEvidenceIn
from app.modules.investment_gate_preparation.service import InvestmentGatePreparationService
from app.modules.portfolio_analysis.service import PortfolioAnalysisService, _hash
from app.modules.portfolio_budget.schemas import BudgetScenarioCreateIn, BudgetTargetCreateIn, TargetPeriodIn
from app.modules.portfolio_budget.service import DEFAULT_CONFIGURATION as BUDGET_CONFIGURATION
from app.modules.portfolio_budget.service import PortfolioBudgetService
from app.modules.portfolio_convergence.schemas import ConvergenceCreateIn, RecommendationIn
from app.modules.portfolio_convergence.service import DEFAULT_CONFIGURATION as CONVERGENCE_CONFIGURATION
from app.modules.portfolio_convergence.service import PortfolioConvergenceService
from app.modules.portfolio_evaluation.service import PortfolioEvaluationService
from app.modules.portfolio_resource.schemas import (
    CapacityPeriodIn,
    CapacityPlanCreateIn,
    DemandPeriodIn,
    DemandProfileCreateIn,
    ResourceScenarioCreateIn,
)
from app.modules.portfolio_resource.service import DEFAULT_CONFIGURATION as RESOURCE_CONFIGURATION
from app.modules.portfolio_resource.service import PortfolioResourceService
from app.modules.post_fid_governance.service import READY_INITIALIZATION, PostFIDGovernanceService
from app.modules.project_definition.schemas import StartFELIn
from app.modules.project_definition.service import ProjectDefinitionService
from app.modules.project_proposal.models import ProjectProposal
from app.modules.risk_readiness.service import RiskReadinessService

POLICY_ID = 787
POLICY_EFFECTIVE_FROM = "2026-09-03T12:34:44.035309"
TOTAL_INVESTMENT = Decimal("100000000")
FUNDING_PLAN = (
    ("SPONSOR", "CORPORATE_CAPEX", "SPONSOR_EQUITY", Decimal("20000000")),
    ("EXTERNAL", "JV_CONTRIBUTION", "EXTERNAL_INVESTOR_EQUITY", Decimal("15000000")),
    ("SENIOR", "BANK_LOAN", "BANK_LOAN", Decimal("50000000")),
    ("DEVELOPMENT", "DEVELOPMENT_BANK", "DEVELOPMENT_BANK_LOAN", Decimal("10000000")),
    ("GRANT", "GRANT", "GRANT", Decimal("5000000")),
)


@pytest.fixture(scope="module", autouse=True)
def _started_application():
    with TestClient(app):
        yield


def _configuration(db, tenant_id: int, actor_id: int, kind: str, content: dict, code: str) -> AdminConfiguration:
    record = AdminConfiguration(
        tenant_id=tenant_id,
        kind=kind,
        code=code,
        name=f"Gate 07M-FID {kind}",
        description="Dedicated full-stack revalidation fixture.",
        status="published",
        revision=1,
        version=1,
        content_json=content,
        content_hash=_hash(content),
        published_at=utc_now(),
        created_by_user_id=actor_id,
    )
    db.add(record)
    db.flush()
    return record


def _proposal(db, tenant_id: int, actor_id: int, parent_id: int, project_id: int) -> ProjectProposal:
    suffix = uuid4().hex[:10]
    matrix = _configuration(db, tenant_id, actor_id, "idea_evaluation_matrix", {"criteria": []}, f"fid-{suffix}")
    mapping = _configuration(
        db,
        tenant_id,
        actor_id,
        "project_proposal_configuration",
        {"mapping": {}},
        f"fid-{suffix}",
    )
    idea = Idea(
        tenant_id=tenant_id,
        idea_number=f"IDEA-FID-{suffix}",
        title="Commercial revenue Project for PYP-FFA",
        description="Dedicated disposable full-stack validation source.",
        idea_type="CAPITAL",
        category="investment",
        expected_benefit="Governed commercial returns.",
        currency_code="USD",
        owning_workspace_id=parent_id,
        strategic_objective_codes=["GROWTH"],
        requestor_user_id=actor_id,
        owner_user_id=actor_id,
        state="ACCEPTED",
        screening_json={},
        routing_json={},
        configuration_snapshot_json={},
        attachment_refs_json=[],
        decision_reason="Accepted for deterministic FID validation.",
        decision_by_user_id=actor_id,
        readiness_json={},
        revision_version=1,
        last_modified_by_user_id=actor_id,
    )
    db.add(idea)
    db.flush()
    evaluation = IdeaEvaluation(
        tenant_id=tenant_id,
        idea_id=idea.id,
        evaluation_version=1,
        matrix_configuration_id=matrix.id,
        matrix_revision=1,
        matrix_snapshot_json={},
        ratings_json=[],
        total_score="95.0000",
        result="RECOMMENDED",
        comments="Commercial PYP-FFA source approved.",
        evaluator_user_id=actor_id,
    )
    db.add(evaluation)
    db.flush()
    idea.accepted_evaluation_id = evaluation.id
    proposal = ProjectProposal(
        tenant_id=tenant_id,
        proposal_number=f"PROP-FID-{suffix}",
        source_idea_id=idea.id,
        accepted_idea_evaluation_id=evaluation.id,
        owning_workspace_id=parent_id,
        name="PYP-FFA Commercial Revenue Project",
        business_need="Deploy a governed commercial asset with auditable investment authority.",
        business_justification="Deterministic USD 100 million validation of the strategic investment chain.",
        project_objectives_json=[{"description": "Reach governed FID without automatic activation"}],
        preliminary_scope="Commercial asset definition, financing and investment decision.",
        out_of_scope="Procurement, contracting, commitments, payments and operations.",
        expected_benefits="Positive risk-adjusted commercial cash flows.",
        currency_code="USD",
        rom_cost=TOTAL_INVESTMENT,
        key_risks_json=[{"description": "Controlled construction and market exposure"}],
        assumptions_json=[],
        constraints_json=[],
        strategic_objective_codes=["GROWTH"],
        sponsor_user_id=actor_id,
        proposal_owner_user_id=actor_id,
        status="READY_FOR_STRATEGIC_GATE",
        mapping_configuration_id=mapping.id,
        mapping_revision=mapping.revision,
        mapping_hash=mapping.content_hash,
        source_values_snapshot_json={"project_workspace_id": project_id},
        mapped_values_snapshot_json={},
        configuration_snapshot_json={},
        review_snapshot_json={},
        attachment_refs_json=[],
        revision_version=1,
        created_by=actor_id,
        updated_by=actor_id,
    )
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    return proposal


def _publish_policy_787(db, tenant_id: int, actor_id: int) -> AdminConfiguration:
    for item in db.scalars(
        select(AdminConfiguration).where(
            AdminConfiguration.tenant_id == tenant_id,
            AdminConfiguration.kind == EVIDENCE_POLICY_KIND,
            AdminConfiguration.status == "published",
        )
    ).all():
        item.status = "superseded"
        item.version += 1
    occupied = db.get(AdminConfiguration, POLICY_ID)
    if occupied is not None:
        assert occupied.kind == EVIDENCE_POLICY_KIND
        db.delete(occupied)
        db.flush()
    content = gate07m_evid_policy_update(deepcopy(DEFAULT_POLICY))
    content["effective_from"] = POLICY_EFFECTIVE_FROM
    record = AdminConfiguration(
        id=POLICY_ID,
        tenant_id=tenant_id,
        kind=EVIDENCE_POLICY_KIND,
        code="default",
        name="Gate 07M-EVID effective PYP-FFA policy",
        description="Policy 787 revision 1 reused by the disposable full-stack validation.",
        status="draft",
        revision=1,
        version=1,
        content_json=content,
        content_hash=evidence_policy_hash(content),
        created_by_user_id=actor_id,
    )
    db.add(record)
    db.commit()
    return InvestmentEvidencePolicyService(db, tenant_id, actor_id).publish_configuration(record.id, record.version)


def _advance_to_fel3(db, tenant_id: int, actor_id: int, project_id: int) -> tuple[UserAccount, dict]:
    framework = _framework(db, tenant_id, actor_id, threshold=65)
    reviewer = _reviewer(db, tenant_id)
    service = ProjectDefinitionService(db, tenant_id, actor_id)
    service.start_fel(
        project_id,
        StartFELIn(
            framework_configuration_id=framework.id,
            stage_code="FEL-1",
            idempotency_key=f"fid-fel-start-{uuid4()}",
        ),
    )
    stages: dict[str, str] = {}
    for stage in ("FEL-1", "FEL-2"):
        completed = _complete_current(service, project_id, score=92)
        stages[f"{stage}_assessment_hash"] = completed.assessment_hash
        submitted = service.submit_stage_review(
            project_id,
            service.fel_status(project_id).revision_version,
            f"fid-fel-submit-{stage}-{uuid4()}",
        )
        ProjectDefinitionService(db, tenant_id, reviewer.id).complete_stage(
            project_id,
            submitted.revision_version,
            f"fid-fel-review-{stage}-{uuid4()}",
        )
    completed = _complete_current(service, project_id, score=94)
    stages["FEL-3_assessment_hash"] = completed.assessment_hash
    evidence = service.investment_gate_evidence(project_id)
    assert evidence.FEL_stage_code == "FEL-3"
    assert evidence.can_supply_investment_gate_evidence is True
    return reviewer, stages


def _portfolio_sources(db, tenant_id: int, actor_id: int, parent: EnterpriseWorkspace):
    portfolio = _portfolio(db, tenant_id, actor_id, parent)
    project, _membership = _project(
        db,
        tenant_id,
        actor_id,
        parent,
        portfolio,
        name="Gate 07M-FID PYP-FFA Commercial Project",
        currency="USD",
    )
    defaults = deepcopy(project.defaults_json or {})
    defaults["_project"] = {
        **dict(defaults.get("_project", {})),
        "governance_model": "CAPITAL_OWNER",
        "project_type": "COMMERCIAL",
        "project_type_code": "COMMERCIAL",
        "planning_origin": "STRATEGIC_GATE",
    }
    planning = deepcopy(defaults["_portfolio_planning"])
    planning["snapshot"] = {
        **dict(planning["snapshot"]),
        "rom_cost": str(TOTAL_INVESTMENT),
        "currency": "USD",
        "project_type": "COMMERCIAL",
    }
    planning["planning_entry_hash"] = _hash(planning["snapshot"])
    defaults["_portfolio_planning"] = planning
    project.defaults_json = defaults

    budget_config = deepcopy(BUDGET_CONFIGURATION)
    budget_config["scope"] = {"type": "portfolio", "workspace_id": portfolio.id}
    budget_config["budget_currency_policy"] = {
        **dict(budget_config.get("budget_currency_policy", {})),
        "mode": "FIXED",
        "budget_currency": "USD",
        "fx_conversion": False,
    }
    resource_config = deepcopy(RESOURCE_CONFIGURATION)
    resource_config["scope"] = {"type": "tenant", "workspace_id": None}
    convergence_config = deepcopy(CONVERGENCE_CONFIGURATION)
    convergence_config["scope"] = {"type": "portfolio", "workspace_id": portfolio.id}
    _configuration(db, tenant_id, actor_id, "portfolio_budget_configuration", budget_config, f"fid-{uuid4()}")
    _configuration(db, tenant_id, actor_id, "portfolio_resource_configuration", resource_config, f"fid-{uuid4()}")
    _configuration(
        db,
        tenant_id,
        actor_id,
        "portfolio_convergence_configuration",
        convergence_config,
        f"fid-{uuid4()}",
    )
    db.commit()

    _complete(PortfolioEvaluationService(db, tenant_id, actor_id), portfolio.id, project.id, 5)
    analysis_hash = PortfolioAnalysisService(db, tenant_id, actor_id).overview(portfolio.id).dataset.analysis_hash

    budget = PortfolioBudgetService(db, tenant_id, actor_id)
    target = budget.create_target(
        portfolio.id,
        BudgetTargetCreateIn(
            planning_horizon_start=date(2027, 1, 1),
            planning_horizon_end=date(2030, 12, 31),
            period_granularity="YEAR",
            budget_currency="USD",
            total_budget_target=TOTAL_INVESTMENT,
            periods=[
                TargetPeriodIn(
                    period_key="2027",
                    period_start=date(2027, 1, 1),
                    period_end=date(2027, 12, 31),
                    amount=TOTAL_INVESTMENT,
                )
            ],
            source_reference="Board-approved commercial investment envelope",
            idempotency_key=f"fid-budget-target-{uuid4()}",
        ),
    )
    target = budget.publish_target(target.id, target.revision_version, f"fid-budget-publish-{uuid4()}")
    budget_scenario = budget.create_scenario(
        portfolio.id,
        BudgetScenarioCreateIn(
            scenario_name="PYP-FFA USD 100M governed baseline",
            budget_target_id=target.id,
            creation_mode="FROM_CURRENT_PRIORITY",
            time_phasing_method="UNPHASED",
            expected_analysis_hash=analysis_hash,
            idempotency_key=f"fid-budget-scenario-{uuid4()}",
        ),
    )
    budget_scenario = budget.freeze_scenario(
        budget_scenario.id,
        budget_scenario.revision_version,
        f"fid-budget-freeze-{uuid4()}",
    )

    resource = PortfolioResourceService(db, tenant_id, actor_id)
    capacity = resource.create_capacity_plan(
        portfolio.id,
        CapacityPlanCreateIn(
            plan_name="PYP-FFA commercial delivery capacity",
            planning_horizon_start=date(2027, 1, 1),
            planning_horizon_end=date(2030, 12, 31),
            period_granularity="YEAR",
            source_reference="Approved workforce plan",
            periods=[
                CapacityPeriodIn(
                    resource_role_key="PROJECT_MANAGER",
                    resource_role_name="Project Manager",
                    role_category="MANAGEMENT",
                    period_key="2027",
                    period_start=date(2027, 1, 1),
                    period_end=date(2027, 12, 31),
                    capacity_value=Decimal("5"),
                    unit="FTE",
                )
            ],
            idempotency_key=f"fid-capacity-{uuid4()}",
        ),
    )
    capacity = resource.publish_capacity_plan(
        capacity.id,
        capacity.revision_version,
        f"fid-capacity-publish-{uuid4()}",
    )
    demand = resource.create_demand_profile(
        project.id,
        DemandProfileCreateIn(
            profile_name="PYP-FFA Project demand",
            source_type="PROJECT_RESOURCE_DEMAND_PROFILE",
            source_reference="Commercial Project resource plan",
            as_of_date=date(2026, 9, 3),
            planning_start=date(2027, 1, 1),
            planning_finish=date(2030, 12, 31),
            generation_method="EXPLICIT_PERIOD_PROFILE",
            periods=[
                DemandPeriodIn(
                    resource_role_key="PROJECT_MANAGER",
                    resource_role_name="Project Manager",
                    role_category="MANAGEMENT",
                    period_key="2027",
                    period_start=date(2027, 1, 1),
                    period_end=date(2027, 12, 31),
                    demand_value=Decimal("1"),
                    unit="FTE",
                )
            ],
            idempotency_key=f"fid-demand-{uuid4()}",
        ),
    )
    resource.publish_demand_profile(demand.id, demand.revision_version, f"fid-demand-publish-{uuid4()}")
    resource_scenario = resource.create_scenario(
        portfolio.id,
        ResourceScenarioCreateIn(
            scenario_name="PYP-FFA governed resource scenario",
            capacity_plan_id=capacity.id,
            creation_mode="FROM_CURRENT_PRIORITY",
            expected_analysis_hash=analysis_hash,
            idempotency_key=f"fid-resource-scenario-{uuid4()}",
        ),
    )
    resource_scenario = resource.freeze_scenario(
        resource_scenario.id,
        resource_scenario.revision_version,
        f"fid-resource-freeze-{uuid4()}",
    )

    convergence_service = PortfolioConvergenceService(db, tenant_id, actor_id)
    convergence = convergence_service.create_convergence(
        portfolio.id,
        ConvergenceCreateIn(
            name="PYP-FFA commercial convergence",
            description="Single deterministic Project aligned across budget and capacity.",
            idempotency_key=f"fid-convergence-{uuid4()}",
        ),
    )
    convergence = convergence_service.add_alternative(
        convergence.id,
        convergence.revision_version,
        "Commercial USD 100M baseline",
        budget_scenario.id,
        resource_scenario.id,
        f"fid-alternative-{uuid4()}",
    )
    alternative = convergence.alternatives[0]
    convergence = convergence_service.submit_review(
        convergence.id,
        convergence.revision_version,
        f"fid-convergence-submit-{uuid4()}",
    )
    convergence = convergence_service.recommend(
        convergence.id,
        convergence.revision_version,
        RecommendationIn(
            recommended_alternative_id=alternative.id,
            recommendation_reason="Budget and resource sources are aligned for FFA.",
            risks_acknowledged=["Execution remains outside this validation."],
            decision_support_summary="One commercial Project is feasible and fully governed.",
            idempotency_key=f"fid-convergence-recommend-{uuid4()}",
        ),
    )
    assert convergence.recommendation_hash
    return portfolio, project, budget_scenario, resource_scenario, convergence


def _funding(db, tenant_id: int, actor_id: int, portfolio_id: int, project_id: int):
    published_funds_policy(
        db,
        tenant_id,
        actor_id,
        fund_creator_cannot_authorize=False,
        assignment_preparer_cannot_confirm=False,
    )
    service = FundsManagerService(db, tenant_id, actor_id)
    assignments = []
    for key, source_type, _instrument_type, amount in FUNDING_PLAN:
        source = service.create_funding_source(
            FundingSourceCreateIn(
                source_name=f"{key} governed source",
                source_type=source_type,
                currency="USD",
                effective_from=date(2027, 1, 1),
                effective_to=date(2030, 12, 31),
                evidence_refs=[{"reference": f"AUTH-{key}-2026"}],
                source_reference=f"Controlled source {key}",
                idempotency_key=f"fid-source-{key}-{uuid4()}",
            )
        )
        source = service.transition_funding_source(
            source.id,
            source.revision_version,
            "activate",
            f"fid-source-activate-{key}-{uuid4()}",
        )
        fund = service.create_fund(
            FundCreateIn(
                fund_name=f"{key} commercial commitment",
                funding_source_id=source.id,
                currency="USD",
                authorized_amount=amount,
                available_from=date(2027, 1, 1),
                available_to=date(2030, 12, 31),
                period_granularity="TOTAL",
                evidence_refs=[{"reference": f"FUND-{key}-AUTH"}],
                source_reference=f"Approved {key} funding",
                idempotency_key=f"fid-fund-{key}-{uuid4()}",
            )
        )
        fund = service.transition_fund(
            fund.id,
            fund.revision_version,
            "authorize",
            f"fid-fund-authorize-{key}-{uuid4()}",
        )
        fund = service.transition_fund(
            fund.id,
            fund.revision_version,
            "activate",
            f"fid-fund-activate-{key}-{uuid4()}",
        )
        assignment = service.create_funding_assignment(
            FundingAssignmentCreateIn(
                fund_id=fund.id,
                scope_type="PROJECT",
                portfolio_workspace_id=portfolio_id,
                project_workspace_id=project_id,
                amount=amount,
                currency="USD",
                period_start=date(2027, 1, 1),
                period_end=date(2030, 12, 31),
                period_profile=[{"period_key": "2027", "amount": amount}],
                assignment_purpose=f"{key} share of the deterministic investment plan.",
                evidence_refs=[{"reference": f"ASSIGN-{key}-2026"}],
                idempotency_key=f"fid-assignment-{key}-{uuid4()}",
            )
        )
        assignment = service.transition_funding_assignment(
            assignment.id,
            assignment.revision_version,
            "confirm",
            f"fid-assignment-confirm-{key}-{uuid4()}",
        )
        assignments.append(assignment)
    preview = service.refresh_preview(portfolio_id)
    readiness = service.refresh(
        portfolio_id,
        preview.proposed_source_hash,
        f"fid-funding-refresh-{uuid4()}",
    )
    assert readiness.required_amount == TOTAL_INVESTMENT
    assert readiness.confirmed_funding_amount == TOTAL_INVESTMENT
    assert readiness.confirmed_coverage_percent == 100
    assert readiness.can_supply_investment_gate_evidence is True
    return readiness, assignments


def _business_case_and_fin(
    db,
    tenant_id: int,
    actor_id: int,
    reviewer_id: int,
    parent_id: int,
    project: EnterpriseWorkspace,
    budget_scenario_id: int,
    funding_readiness_id: int,
    assignments,
):
    proposal = _proposal(db, tenant_id, actor_id, parent_id, project.id)
    content = deepcopy(BUSINESS_CASE_CONFIGURATION)
    content["scope"] = {"workspace_id": project.id, "inherit_to_descendants": False}
    # Permit Readiness is Class B for this commercial Project.  The governed
    # Business Case therefore records it at Gate 07J as an independently
    # validated reference instead of importing mining-only permit rules.
    content["required_sources_by_stage"]["FEL-3"] = [
        value for value in content["required_sources_by_stage"]["FEL-3"] if value != "permit"
    ]
    _configuration(
        db,
        tenant_id,
        actor_id,
        BUSINESS_CASE_CONFIGURATION_KIND,
        content,
        f"fid-commercial-{uuid4()}",
    )
    db.commit()
    business = BusinessCaseService(db, tenant_id, actor_id)
    case = business.create(
        project.id,
        proposal.id,
        actor_id,
        actor_id,
        f"fid-business-case-{uuid4()}",
    )
    revision = case.current_revision
    assert revision is not None
    revision = business.update_revision(
        revision.id,
        revision.revision_version,
        {
            "unresolved_concerns": [
                {
                    "description": "Commercial delivery risk is governed in the Risk Readiness source.",
                    "blocking": False,
                    "status": "CLOSED",
                }
            ],
            "recommendation": {
                "selected_alternative": "COMMERCIAL-BASE",
                "status": "RECOMMENDED",
                "is_decision": False,
            },
        },
    )
    revision = business.submit_review(revision.id, revision.revision_version, f"fid-bc-submit-{uuid4()}")
    revision = business.complete_revision(
        revision.id,
        revision.revision_version,
        f"fid-bc-complete-{uuid4()}",
        reviewer_id,
    )
    assert revision.readiness_status == "READY"

    financial = EconomicFinancialModelService(db, tenant_id, actor_id)
    financial.ensure_seed()
    model = financial.create(
        {
            "project_workspace_id": project.id,
            "business_case_id": case.id,
            "model_type": "COMMERCIAL_PROJECT",
            "base_currency": "USD",
            "cash_flow_basis": "NOMINAL",
            "periodicity": "ANNUAL",
            "model_start_date": date(2027, 1, 1),
            "model_end_date": date(2030, 12, 31),
            "construction_start": date(2027, 1, 1),
            "operations_start": date(2028, 1, 1),
            "operations_end": date(2030, 12, 31),
            "terminal_date": date(2030, 12, 31),
            "budget_scenario_id": budget_scenario_id,
            "funding_readiness_id": funding_readiness_id,
            "idempotency_key": f"fid-fin-model-{uuid4()}",
        }
    )
    version = model.current_version
    assert version is not None
    for key, value in {
        "project_discount_rate": Decimal("0.10"),
        "cost_of_equity": Decimal("0.14"),
        "cost_of_debt": Decimal("0.05"),
        "tax_rate": Decimal("0.25"),
        "inflation_rate": Decimal("0.03"),
    }.items():
        financial.upsert_assumption(
            version.id,
            version.revision_version,
            {
                "assumption_key": key,
                "name": key.replace("_", " ").title(),
                "category": "DISCOUNT_RATE" if "rate" in key else "GENERAL",
                "numeric_value": value,
                "text_value": None,
                "unit": "RATE",
                "periodicity": "ANNUAL",
                "effective_from": None,
                "effective_to": None,
                "source": "GOVERNED_POLICY",
                "source_reference": "PYP-FFA deterministic fixture",
                "rationale": "Controlled full-stack validation input.",
                "is_override": False,
            },
        )
        version = financial._version(version.id)
    period_values = (
        {
            "capex": "100000000",
            "revenue": "0",
            "opex": "0",
            "draw": "60000000",
            "interest": "0",
            "principal": "0",
            "equity": "35000000",
            "distribution": "0",
        },
        {
            "capex": "0",
            "revenue": "55000000",
            "opex": "15000000",
            "draw": "0",
            "interest": "3000000",
            "principal": "20000000",
            "equity": "0",
            "distribution": "5000000",
        },
        {
            "capex": "0",
            "revenue": "60000000",
            "opex": "15000000",
            "draw": "0",
            "interest": "2000000",
            "principal": "20000000",
            "equity": "0",
            "distribution": "15000000",
        },
        {
            "capex": "0",
            "revenue": "65000000",
            "opex": "15000000",
            "draw": "0",
            "interest": "1000000",
            "principal": "20000000",
            "equity": "0",
            "distribution": "50000000",
        },
    )
    for index, row in enumerate(period_values):
        year = 2027 + index
        financial.upsert_period(
            version.id,
            version.revision_version,
            {
                "period_index": index,
                "period_label": f"FY{year}",
                "period_start": date(year, 1, 1),
                "period_end": date(year, 12, 31),
                "currency": "USD",
                "revenue": Decimal(row["revenue"]),
                "economic_benefits": Decimal("0"),
                "opex": Decimal(row["opex"]),
                "taxes": Decimal("0"),
                "working_capital_change": Decimal("0"),
                "capex": Decimal(row["capex"]),
                "debt_drawdown": Decimal(row["draw"]),
                "interest": Decimal(row["interest"]),
                "principal": Decimal(row["principal"]),
                "equity_contribution": Decimal(row["equity"]),
                "distribution": Decimal(row["distribution"]),
                "source_reference": "Commercial cash-flow model",
                "source_hash": _hash(row),
            },
        )
        version = financial._version(version.id)

    instruments = {}
    for (key, _source_type, instrument_type, amount), assignment in zip(FUNDING_PLAN, assignments, strict=True):
        instrument = financial.create_instrument(
            version.id,
            version.revision_version,
            {
                "instrument_key": key,
                "name": f"{key} financing instrument",
                "instrument_type": instrument_type,
                "currency": "USD",
                "committed_amount": amount,
                "drawn_amount": amount if instrument_type in {"BANK_LOAN", "DEVELOPMENT_BANK_LOAN"} else Decimal("0"),
                "funding_assignment_id": assignment.id,
                "interest_basis": "FIXED" if instrument_type in {"BANK_LOAN", "DEVELOPMENT_BANK_LOAN"} else None,
                "fixed_rate": Decimal("0.05")
                if instrument_type == "BANK_LOAN"
                else (Decimal("0.03") if instrument_type == "DEVELOPMENT_BANK_LOAN" else None),
                "principal_grace_periods": 1,
                "interest_grace_periods": 0,
                "tenor_periods": 4 if instrument_type in {"BANK_LOAN", "DEVELOPMENT_BANK_LOAN"} else None,
                "drawdown_method": "CUSTOM",
                "amortization_method": "CUSTOM",
                "interest_during_construction": "CASH_PAY",
                "covenants_json": [],
                "idempotency_key": f"fid-instrument-{key}-{uuid4()}",
            },
        )
        instruments[key] = instrument
        version = financial._version(version.id)
    for key, investor_type, ownership in (
        ("SPONSOR", "SPONSOR", "57.142857"),
        ("EXTERNAL", "EXTERNAL_INSTITUTIONAL", "42.857143"),
    ):
        instrument = instruments[key]
        financial.create_investor(
            version.id,
            version.revision_version,
            {
                "financing_instrument_id": instrument.id,
                "investor_key": key,
                "name": f"{key} governed investor",
                "investor_type": investor_type,
                "committed_equity": instrument.committed_amount,
                "ownership_percent": Decimal(ownership),
                "preferred_return": Decimal("0.08"),
                "distribution_priority": 1 if key == "EXTERNAL" else 2,
                "capital_call_profile_json": [{"period": "2027", "amount": str(instrument.committed_amount)}],
                "distribution_profile_json": [{"period": "2030", "priority": 1 if key == "EXTERNAL" else 2}],
                "hurdle_rate": Decimal("0.12"),
                "idempotency_key": f"fid-investor-{key}-{uuid4()}",
            },
        )
        version = financial._version(version.id)
    calculated = financial.calculate(version.id, version.revision_version, f"fid-fin-calculate-{uuid4()}")
    assert calculated.overall_readiness == "READY"
    assert calculated.total_investment_requirement == TOTAL_INVESTMENT
    assert calculated.total_model_financing == TOTAL_INVESTMENT
    assert calculated.governed_funding_assigned == TOTAL_INVESTMENT
    assert calculated.funding_gap == 0
    assert calculated.project_financial_npv is not None
    assert calculated.project_irr is not None
    calculated = financial.submit_review(
        calculated.id,
        calculated.revision_version,
        f"fid-fin-submit-{uuid4()}",
    )
    completed = financial.complete(
        calculated.id,
        calculated.revision_version,
        f"fid-fin-complete-{uuid4()}",
        reviewer_id,
    )

    case_current = business.get(case.id)
    linked = business.refresh(case.id, case_current.revision_version, f"fid-bc-fin-link-{uuid4()}")
    linked = business.submit_review(linked.id, linked.revision_version, f"fid-bc-link-submit-{uuid4()}")
    linked = business.complete_revision(
        linked.id,
        linked.revision_version,
        f"fid-bc-link-complete-{uuid4()}",
        reviewer_id,
    )
    assert linked.economic_financial_model_hash == completed.model_hash
    assert business.readiness(case.id).status == "READY"
    fin_provider = financial.provider_evidence(model.id)
    assert fin_provider.can_supply_investment_gate_evidence is True
    assert fin_provider.source_current is True
    return case, linked, model, completed, instruments


def _manual_blocking_class_b(preparer, reviewer, preparation):
    for item in list(preparation.evidence):
        if item.classification != "B" or not item.blocking or item.status == "VALID":
            continue
        preparation = preparer.add_evidence(
            preparation.id,
            preparation.revision_version,
            ManualEvidenceIn(
                requirement_key=item.requirement_key,
                scope_type=item.scope_type,
                scope_id=item.scope_id,
                reference_id=f"CONTROLLED-{item.evidence_type}-{item.scope_id or 'PORTFOLIO'}",
                evidence_date=utc_now(),
                valid_until=utc_now() + timedelta(days=180),
                issuer="P&P Investment Governance Office",
                owner="Commercial Project Sponsor",
                summary=f"Independently controlled {item.evidence_type} reference for PYP-FFA.",
                evidence_refs=[{"origin": "CONTROLLED_DOCUMENT", "evidence_type": item.evidence_type}],
                idempotency_key=f"fid-manual-{item.requirement_key}-{item.scope_id}-{uuid4()}",
            ),
        )
        refreshed = next(value for value in preparation.evidence if value.id == item.id)
        preparation = reviewer.validate_evidence(
            refreshed.id,
            preparation.revision_version,
            EvidenceValidationIn(
                decision="VALID",
                validation_note="Independent validation confirms scope, currency/date and controlled reference.",
                idempotency_key=f"fid-manual-validation-{item.id}-{uuid4()}",
            ),
        )
    return preparation


def _project_14_hash(db) -> str | None:
    project = db.get(EnterpriseWorkspace, 14)
    if project is None:
        return None
    return _hash(
        {
            "id": project.id,
            "code": project.code,
            "name": project.name,
            "status": project.status,
            "defaults": project.defaults_json,
            "version": project.version,
        }
    )


def test_new_pyp_ffa_fid_path_full_stack_revalidation() -> None:
    timings: dict[str, float] = {}
    with SessionLocal() as db:
        actor = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
        assert actor is not None
        tenant_id = actor.tenant_id
        parent = db.scalar(
            select(EnterpriseWorkspace)
            .where(
                EnterpriseWorkspace.tenant_id == tenant_id,
                EnterpriseWorkspace.workspace_type_code == "enterprise",
            )
            .order_by(EnterpriseWorkspace.id)
        )
        if parent is None:
            _tenant, _actor, parent = _context()
            parent = db.get(EnterpriseWorkspace, parent.id)
            assert parent is not None
        baseline_project_14 = _project_14_hash(db)

        portfolio, project, budget, resource, convergence = _portfolio_sources(
            db,
            tenant_id,
            actor.id,
            parent,
        )
        assert project.id != 14
        reviewer, fel_hashes = _advance_to_fel3(db, tenant_id, actor.id, project.id)
        risk = RiskReadinessService(db, tenant_id, actor.id)
        publish_risk(risk)
        _low_risk(risk, project.id, title="Controlled commercial delivery risk")
        risk_assessment = complete_risk(risk, project.id)
        assert risk_assessment.readiness_status == "READY"

        funding, assignments = _funding(db, tenant_id, actor.id, portfolio.id, project.id)
        case, case_revision, model, fin_version, instruments = _business_case_and_fin(
            db,
            tenant_id,
            actor.id,
            reviewer.id,
            parent.id,
            project,
            budget.id,
            funding.snapshot_id,
            assignments,
        )

        policy = _publish_policy_787(db, tenant_id, actor.id)
        assert policy.id == POLICY_ID
        assert policy.revision == 1
        assert policy.content_json["effective_from"] == POLICY_EFFECTIVE_FROM
        policy_service = InvestmentEvidencePolicyService(db, tenant_id, actor.id)
        started = perf_counter()
        preview = policy_service.preview(
            portfolio_id=portfolio.id,
            gate_profile_code="PYP-FFA",
            project_ids=[project.id],
            configuration_id=policy.id,
            content_override=policy.content_json,
        )
        timings["provider_resolution_ms"] = round((perf_counter() - started) * 1000, 3)
        assert preview.missing_required_provider_count == 0
        assert preview.source_availability["BUSINESS_CASE_READINESS"] == "AVAILABLE"
        assert preview.source_availability["ECONOMIC_FINANCIAL_READINESS"] == "AVAILABLE"

        profile = _profile(db, tenant_id, actor.id, funding=True)
        preparer = InvestmentGatePreparationService(db, tenant_id, actor.id)
        preparation = preparer.create(
            __import__(
                "app.modules.investment_gate_preparation.schemas",
                fromlist=["PreparationCreateIn"],
            ).PreparationCreateIn(
                portfolio_workspace_id=portfolio.id,
                investment_gate_profile_id=profile.id,
                name="PYP-FFA Commercial Full Funds Authorization",
                description="Full-stack evidence package for a new disposable Project.",
                idempotency_key=f"fid-preparation-{uuid4()}",
            )
        )
        validator = InvestmentGatePreparationService(db, tenant_id, reviewer.id)
        preparation = _manual_blocking_class_b(preparer, validator, preparation)
        started = perf_counter()
        readiness = validator.readiness(preparation.id)
        timings["gate07j_readiness_ms"] = round((perf_counter() - started) * 1000, 3)
        assert readiness.readiness_status == "READY", readiness.blockers
        assert readiness.coverage_percent == 100
        class_a = [item for item in preparation.evidence if item.classification == "A" and item.blocking]
        assert class_a and all(item.status == "VALID" for item in class_a)
        assert any(item.evidence_type == "BUSINESS_CASE_READINESS" and item.status == "VALID" for item in class_a)
        assert any(item.evidence_type == "ECONOMIC_FINANCIAL_READINESS" and item.status == "VALID" for item in class_a)
        preparation = preparer.ready_for_review(
            preparation.id,
            preparation.revision_version,
            f"fid-preparation-ready-{uuid4()}",
        )
        started = perf_counter()
        preparation = validator.freeze(
            preparation.id,
            preparation.revision_version,
            f"fid-preparation-freeze-{uuid4()}",
        )
        timings["gate07j_freeze_ms"] = round((perf_counter() - started) * 1000, 3)
        frozen_hash = preparation.preparation_hash
        handoff = validator.handoff(preparation.id)
        assert handoff.final_output == "READY_FOR_INVESTMENT_DECISION"
        assert handoff.preparation_hash == frozen_hash

        decision_service = InvestmentDecisionService(db, tenant_id, actor.id)
        decision_service.ensure_seed()
        started = perf_counter()
        decision = decision_service.create(
            DecisionCreateIn(
                investment_gate_preparation_id=preparation.id,
                title="PYP-FFA Commercial Final Investment Decision",
                executive_summary="USD 100M governed commercial investment package.",
                idempotency_key=f"fid-decision-create-{uuid4()}",
            )
        )
        timings["gate07k_package_load_ms"] = round((perf_counter() - started) * 1000, 3)
        maker = _maker(db, tenant_id, "Independent USD 100M FID Authority")
        decision = decision_service.update(
            decision.id,
            decision.revision_version,
            DecisionUpdateIn(
                decision_maker_user_id=maker.id,
                rationale="Independent authority assigned for formal GO/FID.",
            ),
        )
        decision = decision_service.submit(
            decision.id,
            decision.revision_version,
            f"fid-decision-submit-{uuid4()}",
        )
        decision = InvestmentDecisionService(db, tenant_id, reviewer.id).start_review(
            decision.id,
            decision.revision_version,
            f"fid-decision-review-{uuid4()}",
        )
        checklist = [
            ChecklistAcknowledgement(code=item["code"], acknowledged=True, note="Validated full-stack")
            for item in decision.checklist
        ]
        decision = InvestmentDecisionService(db, tenant_id, reviewer.id).ready(
            decision.id,
            decision.revision_version,
            DecisionReadyIn(idempotency_key=f"fid-decision-ready-{uuid4()}", checklist=checklist),
        )
        decision_count = db.scalar(
            select(func.count()).select_from(
                __import__("app.modules.investment_decision.models", fromlist=["InvestmentDecision"]).InvestmentDecision
            )
        )
        decide_key = f"fid-decision-decide-{uuid4()}"
        decide_payload = DecisionDecideIn(
            outcome="GO",
            rationale="Grant FID and Full Funds Authorization for the governed commercial Project.",
            authorized_amount=TOTAL_INVESTMENT,
            authorized_currency="USD",
            idempotency_key=decide_key,
        )
        maker_service = InvestmentDecisionService(db, tenant_id, maker.id)
        started = perf_counter()
        decided = maker_service.decide(decision.id, decision.revision_version, decide_payload)
        timings["gate07k_decide_ms"] = round((perf_counter() - started) * 1000, 3)
        duplicate = maker_service.decide(decision.id, decision.revision_version, decide_payload)
        assert duplicate.id == decided.id and duplicate.decision_hash == decided.decision_hash
        assert decided.status == "DECIDED"
        assert decided.outcome == "GO"
        assert decided.is_fid is True
        assert decided.full_funds_authorized is True
        assert decided.investment_authorized is True
        assert decided.authorization_output["can_activate_project"] is False
        assert decided.authorization_output["post_fid_handoff"] == "READY_FOR_POST_FID_PROJECT_GOVERNANCE"
        assert (
            db.scalar(
                select(func.count()).select_from(
                    __import__(
                        "app.modules.investment_decision.models",
                        fromlist=["InvestmentDecision"],
                    ).InvestmentDecision
                )
            )
            == decision_count
        )

        post_fid = PostFIDGovernanceService(db, tenant_id, actor.id)
        started = perf_counter()
        eligibility = post_fid.evaluate(decided.id, f"fid-post-evaluate-{uuid4()}", 1)
        timings["gate07l_evaluate_ms"] = round((perf_counter() - started) * 1000, 3)
        assert len(eligibility) == 1
        assert eligibility[0].project_workspace_id == project.id
        assert eligibility[0].eligibility_status == READY_INITIALIZATION, eligibility[0].model_dump(mode="json")
        assert eligibility[0].can_initialize is True
        assert eligibility[0].can_activate is False
        assert project.status == "pending"
        assert _project_14_hash(db) == baseline_project_14

        # Negative A and historical compatibility: a governed Funding Source
        # change must make the live FIN provider stale, while the frozen Gate
        # 07J package and DECIDED Gate 07K record remain byte-for-byte stable.
        funding_service = FundsManagerService(db, tenant_id, actor.id)
        source = db.scalar(
            select(StrategicFundingSource).where(
                StrategicFundingSource.tenant_id == tenant_id,
                StrategicFundingSource.source_name == "SPONSOR governed source",
            )
        )
        assert source is not None
        suspended = funding_service.transition_funding_source(
            source.id,
            source.revision_version,
            "suspend",
            f"fid-negative-suspend-{uuid4()}",
        )
        stale_fin = EconomicFinancialModelService(db, tenant_id, actor.id).provider_evidence(model.id)
        assert stale_fin.source_current is False
        assert stale_fin.overall_readiness == "STALE"
        negative_preview = policy_service.preview(
            portfolio_id=portfolio.id,
            gate_profile_code="PYP-FFA",
            project_ids=[project.id],
            configuration_id=policy.id,
            content_override=policy.content_json,
        )
        assert negative_preview.would_gate07j_be_ready is False
        fin_evidence = [
            item
            for item in negative_preview.current_evidence_status
            if item["evidence_type"] == "ECONOMIC_FINANCIAL_READINESS"
        ]
        assert fin_evidence and all(item["status"] != "VALID" for item in fin_evidence)
        assert validator.handoff(preparation.id).preparation_hash == frozen_hash
        assert decision_service.get(decided.id).decision_hash == decided.decision_hash
        reactivated = funding_service.transition_funding_source(
            suspended.id,
            suspended.revision_version,
            "activate",
            f"fid-negative-reactivate-{uuid4()}",
        )
        assert reactivated.status == "ACTIVE"
        funding_refresh_preview = funding_service.refresh_preview(portfolio.id)
        recovered_funding = funding_service.refresh(
            portfolio.id,
            funding_refresh_preview.proposed_source_hash,
            f"fid-negative-funding-refresh-{uuid4()}",
        )
        assert recovered_funding.source_current is True
        fin_service = EconomicFinancialModelService(db, tenant_id, actor.id)
        recovered_fin = fin_service.refresh(model.id, f"fid-negative-fin-refresh-{uuid4()}")
        recovered_fin = fin_service.calculate(
            recovered_fin.id,
            recovered_fin.revision_version,
            f"fid-negative-fin-calculate-{uuid4()}",
        )
        recovered_fin = fin_service.submit_review(
            recovered_fin.id,
            recovered_fin.revision_version,
            f"fid-negative-fin-submit-{uuid4()}",
        )
        recovered_fin = fin_service.complete(
            recovered_fin.id,
            recovered_fin.revision_version,
            f"fid-negative-fin-complete-{uuid4()}",
            reviewer.id,
        )
        recovered_case_service = BusinessCaseService(db, tenant_id, actor.id)
        current_case = recovered_case_service.get(case.id)
        recovered_case = recovered_case_service.refresh(
            case.id,
            current_case.revision_version,
            f"fid-negative-case-refresh-{uuid4()}",
        )
        recovered_case = recovered_case_service.submit_review(
            recovered_case.id,
            recovered_case.revision_version,
            f"fid-negative-case-submit-{uuid4()}",
        )
        recovered_case = recovered_case_service.complete_revision(
            recovered_case.id,
            recovered_case.revision_version,
            f"fid-negative-case-complete-{uuid4()}",
            reviewer.id,
        )
        recovered_provider = fin_service.provider_evidence(model.id)
        assert recovered_provider.source_current is True
        assert recovered_provider.overall_readiness == "READY"
        assert recovered_case.economic_financial_model_hash == recovered_fin.model_hash

        evidence = {
            "release_status": "GATE07M_FID_E2E_RELEASE_VALIDATED",
            "final_output": "NEW_PYP_FFA_FID_PATH_FULL_STACK_VALIDATED",
            "next": "READY_TO_ENTER_OPERATIONAL_MACROPROCESSES_REVIEW",
            "database_dialect": db.bind.dialect.name,
            "policy": {
                "id": policy.id,
                "revision": policy.revision,
                "hash": policy.content_hash,
                "effective_from": policy.content_json["effective_from"],
            },
            "project": {
                "id": project.id,
                "code": project.code,
                "governance_model": "CAPITAL_OWNER",
                "project_type": "COMMERCIAL",
                "profile": "PYP-FFA",
                "status_after": project.status,
            },
            "portfolio": {"id": portfolio.id, "code": portfolio.code, "name": portfolio.name},
            "budget": {"scenario_id": budget.id, "hash": budget.scenario_hash, "amount": str(TOTAL_INVESTMENT)},
            "resource": {"scenario_id": resource.id, "hash": resource.scenario_hash},
            "convergence": {"id": convergence.id, "hash": convergence.recommendation_hash},
            "funding": {
                "snapshot_id": funding.snapshot_id,
                "hash": funding.funding_readiness_hash,
                "confirmed_amount": str(funding.confirmed_funding_amount),
                "coverage_percent": str(funding.confirmed_coverage_percent),
                "sources": [
                    {
                        "key": key,
                        "source_id": next(
                            item.id
                            for item in db.scalars(
                                select(StrategicFundingSource).where(
                                    StrategicFundingSource.tenant_id == tenant_id,
                                    StrategicFundingSource.source_name == f"{key} governed source",
                                )
                            ).all()
                        ),
                        "source_type": source_type,
                        "instrument_type": instrument_type,
                        "amount": str(amount),
                    }
                    for key, source_type, instrument_type, amount in FUNDING_PLAN
                ],
            },
            "fel": fel_hashes,
            "risk": {"assessment_id": risk_assessment.id, "hash": risk_assessment.risk_readiness_hash},
            "permit": {"classification": "B", "handling": "INDEPENDENTLY_VALIDATED_REFERENCE"},
            "business_case": {
                "id": case.id,
                "revision_id": case_revision.id,
                "hash": case_revision.content_hash,
                "status": case_revision.status,
                "readiness": case_revision.readiness_status,
                "fin_hash": case_revision.economic_financial_model_hash,
            },
            "financial_model": {
                "id": model.id,
                "version_id": fin_version.id,
                "hash": fin_version.model_hash,
                "status": fin_version.status,
                "readiness": fin_version.overall_readiness,
                "npv": str(fin_version.project_financial_npv),
                "irr": str(fin_version.project_irr),
                "equity_irr": str(fin_version.equity_irr),
                "moic": str(fin_version.moic),
                "minimum_dscr": str(fin_version.minimum_dscr),
                "llcr": str(fin_version.llcr),
                "funding_reconciliation": fin_version.funding_reconciliation_status,
                "instruments": {key: value.id for key, value in instruments.items()},
            },
            "gate07j": {
                "preparation_id": preparation.id,
                "status": preparation.status,
                "hash": frozen_hash,
                "readiness": readiness.readiness_status,
                "coverage_percent": readiness.coverage_percent,
                "class_a_count": len(class_a),
                "class_a_valid": sum(item.status == "VALID" for item in class_a),
            },
            "gate07k": {
                "decision_id": decided.id,
                "decision_hash": decided.decision_hash,
                "source_package_hash": decided.source_package_hash,
                "status": decided.status,
                "outcome": decided.outcome,
                "is_fid": decided.is_fid,
                "full_funds_authorized": decided.full_funds_authorized,
                "investment_authorized": decided.investment_authorized,
                "can_activate_project": decided.authorization_output["can_activate_project"],
            },
            "gate07l": {
                "eligibility_status": eligibility[0].eligibility_status,
                "eligibility_hash": eligibility[0].eligibility_hash,
                "can_initialize": eligibility[0].can_initialize,
                "can_activate": eligibility[0].can_activate,
            },
            "negative_fin_stale": {
                "trigger": "SPONSOR_FUNDING_SOURCE_SUSPENDED",
                "source_id": source.id,
                "provider_source_current": stale_fin.source_current,
                "provider_readiness": stale_fin.overall_readiness,
                "gate07j_would_be_ready": negative_preview.would_gate07j_be_ready,
                "frozen_preparation_hash_unchanged": validator.handoff(preparation.id).preparation_hash == frozen_hash,
                "historical_decision_hash_unchanged": (
                    decision_service.get(decided.id).decision_hash == decided.decision_hash
                ),
                "recovery": {
                    "funding_snapshot_id": recovered_funding.snapshot_id,
                    "funding_readiness_hash": recovered_funding.funding_readiness_hash,
                    "financial_model_version_id": recovered_fin.id,
                    "financial_model_hash": recovered_fin.model_hash,
                    "business_case_revision_id": recovered_case.id,
                    "business_case_fin_hash": recovered_case.economic_financial_model_hash,
                    "provider_source_current": recovered_provider.source_current,
                    "provider_readiness": recovered_provider.overall_readiness,
                },
            },
            "project_14_hash_before": baseline_project_14,
            "project_14_hash_after": _project_14_hash(db),
            "performance": timings,
        }
        output = os.getenv("GATE07M_FID_EVIDENCE_PATH", "").strip()
        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(evidence, indent=2, default=str), encoding="utf-8")
