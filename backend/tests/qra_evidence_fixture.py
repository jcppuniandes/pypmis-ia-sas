"""Real strategic source stack plus actual QRA results, for isolated tests only.

This reuses the previously validated FFA/FID fixture instead of replacing its
mandatory BC/FIN providers with synthetic readiness or weakening Class A.
"""

from copy import deepcopy
from uuid import uuid4

from sqlalchemy import select
from tests import test_gate07m_fid_e2e as fid_fixture
from tests.provision_qra_foundation_browser import prepare_imported_schedule
from tests.test_capital_allocation_wave2a import _context
from tests.test_investment_gate_preparation_gate07j import _reviewer
from tests.test_owner_capability_wave3b import _grant
from tests.test_qra_engine import _approved_model, _publish_engine_policy, _run_completed
from tests.test_qra_foundation import _key, _policy, _ready_sources

from app.core.time import utc_now
from app.domain.models import AdminConfiguration, ControlAccount, EnterpriseWorkspace, Project, UserAccount
from app.modules.basic_data.service import _hash
from app.modules.business_case.models import BusinessCase, BusinessCaseRevision
from app.modules.investment_decision.models import InvestmentDecision
from app.modules.investment_evidence_policy.service import InvestmentEvidencePolicyService
from app.modules.investment_gate_preparation.models import InvestmentGatePreparation
from app.modules.investment_gate_preparation.service import InvestmentGatePreparationService
from app.modules.portfolio_planning.models import PortfolioProjectMembership
from app.modules.post_fid_governance.models import PostFIDProjectEligibility
from app.modules.project_proposal.models import ProjectProposal
from app.modules.qra_engine.models import QraRun, QraRunReview
from app.modules.qra_engine.schemas import RunActionIn
from app.modules.qra_engine.service import QraEngineService
from app.modules.qra_foundation.schemas import ConfigurationCloneIn, ConfigurationUpdateIn
from app.modules.qra_foundation.service import QraFoundationService


def historical_hashes(db):
    """Stored immutable records, not live recomputed readiness contracts."""
    output = {}
    for model, field in (
        (InvestmentGatePreparation, "preparation_hash"),
        (InvestmentDecision, "decision_hash"),
        (PostFIDProjectEligibility, "eligibility_hash"),
        (BusinessCaseRevision, "content_hash"),
    ):
        rows = db.scalars(select(model).order_by(model.id)).all()
        output[model.__tablename__] = {
            str(row.id): {
                "hash": getattr(row, field),
                "stored_row_hash": _hash(
                    {column.name: getattr(row, column.name) for column in model.__table__.columns}
                ),
            }
            for row in rows
            if getattr(row, "status", "") in {"FROZEN", "DECIDED", "COMPLETED"} or model is PostFIDProjectEligibility
        }
    return output


def qra_requirement(kind, *, classification="A", applicability="REQUIRED"):
    analysis_type = "COST_QRA" if kind == "cost" else "SCHEDULE_QRA"
    policy = {
        "analysis_type": analysis_type,
        "applicability": applicability,
        "governance_model_filter": ["CAPITAL_OWNER"],
        "project_type_filter": ["COMMERCIAL"],
        "fel_stage_filter": ["FEL-3"],
        "analytical_readiness": "WARNINGS_ALLOWED",
        "convergence": "WARNING_ALLOWED",
        "scope_requirement": "WHOLE_PROJECT",
        "selected_percentiles": [50, 80, 90],
        "bc_consistency_required": False,
    }
    if kind == "schedule":
        policy["capability_requirements"] = {
            "schedule_state": "NOT_STARTED",
            "remaining_duration": "SOURCE_DURATION",
            "calendar_mode": "NORMALIZED_ELAPSED_TIME_V1",
        }
    elif applicability in {"REQUIRED", "CONDITIONAL"}:
        policy.update(
            project_risk_filter=["HIGH"],
            value_band={
                "source": "PROJECT_CREATION_ESTIMATED_BUDGET",
                "currency": "USD",
                "minimum": 50000000,
            },
        )
    return {
        "requirement_key": f"{kind}-qra-result",
        "evidence_type": f"{analysis_type}_RESULT",
        "classification": classification,
        "required": classification != "C",
        "blocking": classification == "A",
        "scope": "EACH_PROJECT",
        "provider_key": "QRA_RESULT_PROVIDER",
        "provider_required": classification == "A",
        "validity_period_days": 180,
        "coverage_requirement": 100,
        "allow_manual_reference": classification == "B",
        "manual_validation_required": classification == "B",
        "rationale": f"Contextual governed {analysis_type}; not a universal requirement or investment decision.",
        "order": 900 if kind == "cost" else 910,
        "qra_policy": policy,
    }


def evidence_fixture(db, *, calculate=True):
    """All writes are confined to the caller's disposable test database."""
    # The older 07M fixture predates mandatory Benefits/Commercial/BA sources.
    # Its explicitly governed isolated policy tailors Five Case requirements
    # to actual available authorities. No provider is fabricated and BC/FIN
    # remain Class A. This is not validation of the universal current default.
    original_bc_policy = fid_fixture.BUSINESS_CASE_CONFIGURATION
    tailored = deepcopy(original_bc_policy)
    for stage in ("FEL-3", "FFA"):
        tailored["five_case"]["source_requirements_by_stage"][stage] = {
            "strategic_case": ["proposal"],
            "economic_case": ["proposal", "risk"],
            "commercial_case": [],
            "financial_case": ["budget"] + (["funding"] if stage == "FFA" else []),
            "management_case": ["resource", "risk"],
        }
    fid_fixture.BUSINESS_CASE_CONFIGURATION = tailored
    try:
        fid_fixture.test_new_pyp_ffa_fid_path_full_stack_revalidation()
    finally:
        fid_fixture.BUSINESS_CASE_CONFIGURATION = original_bc_policy
    db.expire_all()
    author = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
    project = db.scalar(
        select(EnterpriseWorkspace)
        .where(EnterpriseWorkspace.name == "Gate 07M-FID PYP-FFA Commercial Project")
        .order_by(EnterpriseWorkspace.id.desc())
    )
    # The historical 07M fixture chooses FFA at Gate creation, but predates
    # the governed per-Project profile metadata used by BC source resolution.
    # Declare that actual test context explicitly; never make missing-profile
    # production Projects implicitly FFA or universally QRA-mandatory.
    defaults = deepcopy(project.defaults_json or {})
    metadata = dict(defaults.get("_project", {}))
    metadata.update(
        gate_profile="PYP-FFA",
        fel_stage="FEL-3",
        # Explicit isolated creation metadata: the existing declared investment
        # magnitude is reused, not derived from a QRA result or a new risk score.
        estimated_budget=str(fid_fixture.TOTAL_INVESTMENT),
        currency_code="USD",
        project_risk="HIGH",
    )
    defaults["_project"] = metadata
    project.defaults_json = defaults
    db.commit()
    historical = db.scalar(
        select(InvestmentGatePreparation)
        .where(InvestmentGatePreparation.status == "FROZEN")
        .order_by(InvestmentGatePreparation.id.desc())
    )
    reviewer = _reviewer(db, author.tenant_id)
    for role in (
        "definition_reviewer",
        "configuration_admin",
        "investment_evidence_reviewer",
        "business_case_reviewer",
    ):
        _grant(db, reviewer, role)
    f = {
        "db": db,
        "author": author,
        "reviewer": reviewer,
        "project": project,
        "enterprise": db.get(EnterpriseWorkspace, project.parent_id),
        "portfolio": db.get(EnterpriseWorkspace, historical.portfolio_workspace_id),
        "profile": db.get(AdminConfiguration, historical.investment_gate_profile_id),
        "historical_preparation": historical,
        "historical_hashes": historical_hashes(db),
    }
    f.update(prepare_imported_schedule(db, f, suffix=uuid4().hex[:10]))
    for account in db.scalars(select(ControlAccount).where(ControlAccount.project_id == f["operational_project"].id)):
        account.budget = 1000.0
        account.version += 1
    metadata = deepcopy(f["schedule_import"].source_metadata)
    for relationship in metadata["relationships"]:
        relationship["lag_unit"] = "HOURS"
    f["schedule_import"].source_metadata = metadata
    db.commit()
    f["preparer"] = QraFoundationService(
        db, author.tenant_id, author.id, _context(author, "project_definition_manager")
    )
    f["final"] = QraFoundationService(db, author.tenant_id, reviewer.id, _context(reviewer, "definition_reviewer"))
    seed = f["preparer"].ensure_seed()
    draft = f["preparer"].clone_configuration(
        seed.id,
        seed.version,
        ConfigurationCloneIn(code=f"evidence-{uuid4().hex[:12]}", target_workspace_id=f["enterprise"].id),
        _key("evidence-method-clone"),
    )
    content = _policy(f["enterprise"].id)
    content["methodology"] = {
        "code": "COMMERCIAL_EVIDENCE_DISPOSABLE",
        "name": "Governed disposable contextual QRA evidence",
        "description": "Actual Cost/Schedule kernel; no Gate recomputation.",
    }
    draft = f["preparer"].update_configuration(
        draft["id"],
        draft["version"],
        ConfigurationUpdateIn(name="Contextual QRA evidence test method", content_json=content),
        _key("evidence-method-update"),
    )
    f["configuration"] = f["final"].publish_configuration(
        draft["id"], draft["version"], _key("evidence-method-publish")
    )
    _publish_engine_policy(f)
    f["sources"] = _ready_sources(f)
    f["models"] = {kind: _approved_model(f, f["sources"], kind) for kind in ("cost", "schedule")}
    f["engine"] = QraEngineService(db, author.tenant_id, author.id, dispatcher=lambda *_: None)
    f["review_engine"] = QraEngineService(db, author.tenant_id, reviewer.id)
    f["runs"] = {}
    if calculate:
        for kind in ("cost", "schedule"):
            run = _run_completed(f, kind)
            reviewed = f["review_engine"].review_action(
                run["id"], run["revision_version"], RunActionIn(), _key("evidence-result-review"), "review"
            )
            f["runs"][kind] = f["review_engine"].review_action(
                run["id"], reviewed["revision_version"], RunActionIn(), _key("evidence-result-accept"), "accept"
            )
    f["policy_service"] = InvestmentEvidencePolicyService(db, author.tenant_id, author.id)
    f["gate"] = InvestmentGatePreparationService(db, author.tenant_id, author.id)
    f["validator"] = InvestmentGatePreparationService(db, author.tenant_id, reviewer.id)
    f["baseline_policy"] = db.get(AdminConfiguration, historical.source_snapshot_json["evidence_policy"]["policy_id"])
    f["business_case"] = db.scalar(select(BusinessCase).where(BusinessCase.project_workspace_id == project.id))
    return f


def draft_qra_policy(f):
    source = f["baseline_policy"]
    service = f["policy_service"]
    draft = service.clone_configuration(source.id, source.version)
    content = deepcopy(draft.content_json)
    content["scope"] = {"type": "portfolio", "workspace_id": f["portfolio"].id}
    content["effective_from"] = utc_now().isoformat()
    content["gate_profiles"]["PYP-FFA"]["requirements"] += [
        qra_requirement("cost", applicability="CONDITIONAL"),
        qra_requirement("schedule"),
    ]
    return service.update_configuration(
        draft.id, draft.version, "Contextual Cost/Schedule QRA evidence", draft.description, content
    )


def reuse_evidence_fixture(db, project_id):
    """Reuse already calculated isolated authorities after a fresh code import.

    This never fabricates provider payloads, rewrites snapshots, accepts results,
    or updates upstream sources. Explicit opt-in is handled by the test caller.
    """
    bind = db.get_bind()
    if bind.dialect.name != "postgresql" or bind.url.database != "qra_evidence":
        raise RuntimeError("Fixture reuse is restricted to the disposable qra_evidence database")
    project = db.get(EnterpriseWorkspace, project_id)
    if project is None or project.workspace_type_code != "project":
        raise RuntimeError("The explicitly selected isolated Project fixture does not exist")
    metadata = dict((project.defaults_json or {}).get("_project", {}))
    if metadata.get("gate_profile") != "PYP-FFA" or metadata.get("project_risk") != "HIGH":
        raise RuntimeError("Fixture reuse requires the explicit governed FFA/high-risk test context")
    case = db.scalar(select(BusinessCase).where(BusinessCase.project_workspace_id == project.id))
    proposal = db.get(ProjectProposal, case.source_project_proposal_id)
    portfolio_id = proposal.target_portfolio_workspace_id
    if portfolio_id is None:
        memberships = db.scalars(
            select(PortfolioProjectMembership).where(
                PortfolioProjectMembership.project_workspace_id == project.id,
                PortfolioProjectMembership.tenant_id == project.tenant_id,
                PortfolioProjectMembership.status == "ACTIVE",
            )
        ).all()
        if len(memberships) != 1:
            raise RuntimeError("Fixture reuse needs one actual active Portfolio membership")
        portfolio_id = memberships[0].portfolio_workspace_id
    portfolio = db.get(EnterpriseWorkspace, portfolio_id)
    historical = db.scalar(
        select(InvestmentGatePreparation)
        .where(
            InvestmentGatePreparation.portfolio_workspace_id == portfolio.id,
            InvestmentGatePreparation.status == "FROZEN",
        )
        .order_by(InvestmentGatePreparation.id)
    )
    if historical is None:
        raise RuntimeError("Fixture reuse requires the actual historical frozen FFA package")
    accepted = db.execute(
        select(QraRun, QraRunReview)
        .join(QraRunReview, QraRunReview.run_id == QraRun.id)
        .where(
            QraRun.project_workspace_id == project.id,
            QraRun.status == "COMPLETED",
            QraRunReview.status == "ACCEPTED",
        )
        .order_by(QraRun.id.desc())
    ).all()
    selected = {}
    for run, review in accepted:
        selected.setdefault(run.analysis_type, (run, review))
    if set(selected) != {"COST_QRA", "SCHEDULE_QRA"}:
        raise RuntimeError("Fixture reuse requires real independently accepted Cost and Schedule QRA")
    author = db.get(UserAccount, selected["COST_QRA"][0].created_by)
    reviewer = db.get(UserAccount, selected["COST_QRA"][1].accepted_by)
    engine_service = QraEngineService(db, author.tenant_id, author.id, dispatcher=lambda *_: None)
    f = {
        "db": db,
        "author": author,
        "reviewer": reviewer,
        "project": project,
        "enterprise": db.get(EnterpriseWorkspace, project.parent_id),
        "portfolio": portfolio,
        "profile": db.get(AdminConfiguration, historical.investment_gate_profile_id),
        "historical_preparation": historical,
        "historical_hashes": historical_hashes(db),
        "operational_project": db.get(Project, metadata["operational_project_id"]),
        "engine": engine_service,
        "review_engine": QraEngineService(db, author.tenant_id, reviewer.id),
        "policy_service": InvestmentEvidencePolicyService(db, author.tenant_id, author.id),
        "gate": InvestmentGatePreparationService(db, author.tenant_id, author.id),
        "validator": InvestmentGatePreparationService(db, author.tenant_id, reviewer.id),
        "baseline_policy": db.get(AdminConfiguration, historical.source_snapshot_json["evidence_policy"]["policy_id"]),
        "business_case": case,
        "fixture_setup": "REUSED_REAL_ISOLATED_AUTHORITIES_AFTER_FRESH_CODE_IMPORT",
        "models": {},
        "runs": {},
    }
    for kind in ("cost", "schedule"):
        analysis = f"{kind.upper()}_QRA"
        provider = engine_service.provider_evidence(project.id, analysis)
        if provider["status"] != "AVAILABLE" or not provider["source_current"]:
            raise RuntimeError(f"The reused actual {analysis} provider is not current: {provider}")
        stored, _review = selected[analysis]
        if provider["run_id"] != stored.id:
            raise RuntimeError("The reused fixture does not match deterministic current provider selection")
        f["models"][kind] = {"id": stored.model_definition_id}
        f["runs"][kind] = engine_service.run(stored.id, summary=False)
    return f
