"""Current-source fixture for the retained Gate07M FID regression.

The historical test keeps its FID, immutable-history and FIN-recovery assertions.
This adapter replaces only its outdated upstream construction, using the same
real command helpers as the separately proven current-release journey. It is
not activated by importing this module and never writes terminal business state
or an already-published policy through the ORM.

The fixture is intentionally restricted to pytest's invocation-owned SQLite
database. The persistent PostgreSQL release journey is a separate proof and must
not be reused or reset by a broad regression run.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from tests.helpers.strategic_capital_financing import complete_fin, complete_funding
from tests.helpers.strategic_capital_fresh_setup import setup_fresh_capital_owner
from tests.helpers.strategic_capital_portfolio import (
    complete_periodic_review,
    configure_portfolio_policies,
    prepare_portfolio_sources,
)
from tests.helpers.strategic_capital_sources_current import (
    complete_basic_data,
    complete_benefits,
    complete_commercial,
    complete_owner_capability,
    complete_permits,
    configure_current_sources,
)
from tests.sqlite_isolation import owned_database_path
from tests.strategic_capital_owner_full_e2e_current import complete_case, key, publish_starter, ref, service
from tests.test_project_definition_gate07j_fel import _complete_current
from tests.test_risk_readiness_gate07j_risk import _low_risk

from app.database.session import engine
from app.domain.models import EnterpriseWorkspace, UserAccount
from app.modules.business_case.service import BusinessCaseService
from app.modules.commercial_strategy.service import CommercialStrategyService
from app.modules.economic_financial_model.service import EconomicFinancialModelService
from app.modules.funds_manager.service import FundsManagerService
from app.modules.investment_decision.service import InvestmentDecisionService
from app.modules.investment_evidence_policy.service import InvestmentEvidencePolicyService
from app.modules.investment_gate_preparation.service import InvestmentGatePreparationService
from app.modules.post_fid_governance.service import PostFIDGovernanceService
from app.modules.project_definition.schemas import StartFELIn
from app.modules.project_definition.service import ProjectDefinitionService
from app.modules.risk_readiness.schemas import AssessmentActionIn, AssessmentCreateIn
from app.modules.risk_readiness.service import RiskReadinessService
from app.modules.strategic_benefits.service import StrategicBenefitsService


def _assert_owned_sqlite() -> None:
    # conftest sets tempfile.tempdir to its owned runtime even when the explicit
    # override is omitted by an ordinary local pytest invocation.
    runtime = os.environ.get("PYPMIS_PYTEST_RUNTIME_DIR", "").strip() or tempfile.gettempdir()
    if not os.environ.get("PYTEST_CURRENT_TEST") or os.environ.get("PYPMIS_TEST_DATABASE_URL", "").strip():
        raise RuntimeError("The legacy fixture only runs in the invocation-owned implicit SQLite profile")
    if engine.dialect.name != "sqlite" or not engine.url.database:
        raise RuntimeError("Refusing to build regression fixtures in a non-SQLite application database")
    owned_database_path(Path(engine.url.database), Path(runtime))


def prepare_current_fid_sources(db) -> dict:
    """Build actual upstream lifecycles, without freezing or deciding Gate07J/K.

    The initial Business Case completes at FEL-1, where its policy requires the
    Proposal. It is not falsely completed at FEL-3 before FIN/Benefits/Commercial
    exist. Final FEL-3 includes the independent stage review; a later normal
    refresh captures all five cases and their real, completed source versions.
    """
    _assert_owned_sqlite()
    setup = setup_fresh_capital_owner(db)
    tenant, author, reviewer = setup["tenant_id"], setup["actor_id"], setup["reviewer_id"]
    admin, publisher = setup["admin_author_id"], setup["admin_publisher_id"]
    portfolio = db.get(EnterpriseWorkspace, setup["portfolio_id"])
    project = db.get(EnterpriseWorkspace, setup["project_id"])
    assert portfolio is not None and project is not None and project.status == "pending"
    configs = configure_current_sources(
        db, tenant, admin, publisher, setup["enterprise_id"], project_type_code=setup["project_type"]
    )
    for label, cls, permission, code in (
        ("fel", ProjectDefinitionService, "project_definition.admin.configure", "pyp-custom-definition"),
        ("business_case", BusinessCaseService, "business_case.admin.configure", None),
        ("funding", FundsManagerService, "funds.admin.configure", None),
        ("risk", RiskReadinessService, "risk_readiness.admin.configure", None),
        ("financial", EconomicFinancialModelService, "economic_financial_model.admin.configure", None),
        ("evidence_policy", InvestmentEvidencePolicyService, "investment_evidence_policy.configure", None),
        (
            "ffa_profile",
            InvestmentGatePreparationService,
            "investment_gate_preparation.admin.configure",
            "pyp-ffa",
        ),
        ("decision_authority", InvestmentDecisionService, "investment_decision.admin.configure", None),
        ("post_fid", PostFIDGovernanceService, "post_fid_governance.admin.configure", None),
    ):
        configs[label] = ref(publish_starter(cls, db, tenant, admin, publisher, permission, code=code))

    fel = service(ProjectDefinitionService, db, tenant, author, "project_definition.status.manage")
    fel.start_fel(
        project.id,
        StartFELIn(
            stage_code="FEL-1", framework_configuration_id=configs["fel"]["id"], idempotency_key=key("legacy-fel1")
        ),
    )
    business = service(BusinessCaseService, db, tenant, author, "business_case.create")
    independent_business = service(BusinessCaseService, db, tenant, reviewer, "business_case.complete")
    case = business.create(project.id, setup["proposal_id"], author, reviewer, key("legacy-bc-initial"))
    assert case.current_revision is not None
    initial_revision = complete_case(business, independent_business, case, case.current_revision, "FEL-1")

    planning_policies = configure_portfolio_policies(db, tenant, admin, publisher, portfolio)
    planning = prepare_portfolio_sources(db, tenant, author, reviewer, portfolio, project, policies=planning_policies)
    periodic = complete_periodic_review(
        db,
        tenant,
        author,
        reviewer,
        portfolio,
        project,
        planning_cycle_id=setup["capital_cycle_id"],
        allocation_plan_id=setup["allocation_plan_id"],
        configuration_author=admin,
        configuration_publisher=publisher,
    )
    fel_reviewer = service(ProjectDefinitionService, db, tenant, reviewer, "project_definition_stage.review")
    fel_hashes = {}
    for stage in ("FEL-1", "FEL-2", "FEL-3"):
        assert fel.fel_status(project.id).current_stage_code == stage
        assessment = _complete_current(fel, project.id, score=92)
        fel_hashes[f"{stage}_assessment_hash"] = assessment.assessment_hash
        submitted = fel.submit_stage_review(
            project.id, fel.fel_status(project.id).revision_version, key("legacy-fel-submit")
        )
        fel_reviewer.complete_stage(project.id, submitted.revision_version, key("legacy-fel-review"))
    fel_evidence = fel.investment_gate_evidence(project.id)
    assert fel_evidence.can_supply_investment_gate_evidence is True

    risk = service(RiskReadinessService, db, tenant, author, "project_risk.create")
    _low_risk(risk, project.id, title="UAT CONTROLLED EVIDENCE — full-stack delivery risk")
    risk_assessment = risk.create_assessment(project.id, AssessmentCreateIn(idempotency_key=key("legacy-risk")))
    risk_assessment = service(
        RiskReadinessService, db, tenant, reviewer, "risk_readiness_assessment.complete"
    ).complete_assessment(
        risk_assessment.id,
        risk_assessment.revision_version,
        AssessmentActionIn(idempotency_key=key("legacy-risk-complete")),
    )
    sources = {
        "permit": complete_permits(db, tenant, author, reviewer, project.id),
        "basic_data": complete_basic_data(db, tenant, author, reviewer, project.id),
        "owner_capability": complete_owner_capability(db, tenant, author, reviewer, project.id),
    }
    funding, assignments = complete_funding(db, tenant, author, reviewer, portfolio.id, project.id)
    model, fin, instruments = complete_fin(
        db,
        tenant,
        author,
        reviewer,
        project,
        case,
        planning["budget_scenario"].id,
        funding.snapshot_id,
        assignments,
    )
    sources["commercial"] = complete_commercial(db, tenant, author, reviewer, project.id)
    sources["benefits"] = complete_benefits(
        db,
        tenant,
        author,
        reviewer,
        project.id,
        idea_id=setup["idea_id"],
        analysis_id=setup["analysis_id"],
        proposal_id=setup["proposal_id"],
        business_case_id=case.id,
        objective_code=setup["objective_code"],
    )
    case = business.get(case.id)
    revision = business.refresh(case.id, case.revision_version, key("legacy-bc-final-refresh"))
    revision = complete_case(business, independent_business, case, revision, "FFA")
    assert revision.five_case_readiness_json["overall_business_case_readiness"] == "READY"
    assert revision.source_current is True
    for cls, permission in (
        (StrategicBenefitsService, "benefits_plan.read"),
        (CommercialStrategyService, "commercial_strategy.read"),
    ):
        assert service(cls, db, tenant, author, permission).provider_evidence(project.id).source_current is True
    db.refresh(project)
    assert project.status == "pending", "Completed sources do not authorize investment or activate the Project"
    return {
        "setup": setup,
        "configs": configs,
        "tenant_id": tenant,
        "actor": db.get(UserAccount, author),
        "reviewer": db.get(UserAccount, reviewer),
        "parent": db.get(EnterpriseWorkspace, setup["enterprise_id"]),
        "portfolio": portfolio,
        "project": project,
        "budget": planning["budget_scenario"],
        "resource": planning["resource_scenario"],
        "convergence": planning["convergence"],
        "periodic_review": periodic,
        "fel_hashes": fel_hashes,
        "risk_assessment": risk_assessment,
        "funding": funding,
        "assignments": assignments,
        "case": business.get(case.id),
        "case_revision": revision,
        "initial_case_revision": initial_revision,
        "model": model,
        "fin_version": fin,
        "instruments": instruments,
        "sources": sources,
    }
