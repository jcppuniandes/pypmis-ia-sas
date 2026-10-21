"""One fresh Capital Owner current-release chain on isolated PostgreSQL.

This is deliberately not the historical seeded FID fixture. Command failures
are retained verbatim and block downstream phases; no rule is downgraded.
"""

from __future__ import annotations

import json
import os
import traceback
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from tests.helpers.strategic_capital_financing import complete_fin, complete_funding
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
from tests.helpers.strategic_fresh_class_b import complete_controlled_references, reconcile_requirements
from tests.provision_strategic_fresh_uat import assert_disposable
from tests.test_project_definition_gate07j_fel import _complete_current
from tests.test_risk_readiness_gate07j_risk import _low_risk

from app.core.time import utc_now
from app.database.session import SessionLocal
from app.domain.models import EnterpriseWorkspace, Tenant
from app.modules.business_case.service import BusinessCaseService
from app.modules.commercial_strategy.service import CommercialStrategyService
from app.modules.economic_financial_model.service import EconomicFinancialModelService
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.funds_manager.service import FundsManagerService
from app.modules.investment_decision.schemas import (
    ChecklistAcknowledgement,
    DecisionCreateIn,
    DecisionDecideIn,
    DecisionReadyIn,
    DecisionUpdateIn,
)
from app.modules.investment_decision.service import InvestmentDecisionService
from app.modules.investment_evidence_policy.service import InvestmentEvidencePolicyService
from app.modules.investment_gate_preparation.schemas import PreparationCreateIn
from app.modules.investment_gate_preparation.service import InvestmentGatePreparationService
from app.modules.permit_readiness.service import PermitReadinessService
from app.modules.post_fid_governance.service import (
    NO_REACTIVATION,
    READY_ACTIVATION,
    READY_INITIALIZATION,
    PostFIDGovernanceService,
)
from app.modules.project_definition.schemas import StartFELIn
from app.modules.project_definition.service import ProjectDefinitionService
from app.modules.project_workspace_initialization.schemas import InitializationState
from app.modules.project_workspace_initialization.service import ProjectWorkspaceInitializationService
from app.modules.risk_readiness.schemas import AssessmentActionIn, AssessmentCreateIn
from app.modules.risk_readiness.service import RiskReadinessService
from app.modules.strategic_benefits.service import StrategicBenefitsService

ARTIFACT = Path("/artifacts/fresh-capital-owner-chain.json")


def key(action):
    return f"fresh-capital-current-{action}-{uuid4().hex}"


def ref(record):
    if hasattr(record, "model_dump"):
        return record.model_dump(mode="json")
    return {
        name: getattr(record, name)
        for name in ("id", "revision", "version", "status", "content_hash")
        if hasattr(record, name)
    }


def service(cls, db, tenant, actor, permission):
    ctx = require_enterprise_permission(db, tenant, actor, permission, bootstrap=False)
    return cls(db, tenant, actor, ctx)


def publish_starter(cls, db, tenant, author, publisher, permission, *, code=None):
    """Real publication with unchanged defaults and independent actors."""
    assert author != publisher
    preparer = service(cls, db, tenant, author, permission)
    preparer.ensure_seed()
    records = preparer.configurations()
    source = next(record for record in records if code is None or record.code == code)
    draft = source if source.status == "draft" else preparer.clone_configuration(source.id, source.version)
    validator = service(cls, db, tenant, publisher, permission)
    published = validator.publish_configuration(draft.id, draft.version)
    assert published.status == "published"
    return published


def complete_case(business, reviewer, case, revision, purpose):
    revision = business.update_revision(
        revision.id,
        revision.revision_version,
        {
            "unresolved_concerns": [],
            "recommendation": {
                "selected_alternative": "PREFERRED",
                "status": "RECOMMENDED",
                "is_decision": False,
                "rationale": f"Governed {purpose}; not investment authorization",
            },
        },
    )
    readiness = business.readiness(case.id)
    assert readiness.status == "READY", readiness.model_dump(mode="json")
    revision = business.submit_review(revision.id, revision.revision_version, key("bc-submit"))
    return reviewer.complete_revision(revision.id, revision.revision_version, key("bc-complete"), reviewer.actor_id)


def run():
    assert_disposable()
    result = {
        "scenario": "strategic_capital_owner_full_e2e_current",
        "started_at": utc_now().isoformat(),
        "database": "strategic_fresh_uat",
        "database_dialect": "postgresql",
        "head": "20261011_0068",
        "release_status": "STRATEGIC_MACROPROCESS_NOT_VALIDATED",
        "human_signoff": "PENDING_NOT_ASSUMED",
        "stages": [],
    }
    current = "FRESH_UPSTREAM"
    started = perf_counter()

    def checkpoint(stage, data):
        result["stages"].append({"stage": stage, "status": "PASS", "data": data})
        ARTIFACT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        print(f"PASS {stage}", flush=True)

    try:
        from tests.helpers.strategic_capital_fresh_setup import setup_fresh_capital_owner

        with SessionLocal() as db:
            continued = os.environ.get("PYPMIS_FRESH_UPSTREAM_MANIFEST")
            if continued:
                setup_path = Path(continued).resolve()
                if not setup_path.is_relative_to(Path("/artifacts")):
                    raise ValueError("Only the isolated current-execution artifact directory is allowed")
                setup = json.loads(setup_path.read_text(encoding="utf-8"))
                assert setup["status"] == "UPSTREAM_COMPLETE" and not setup.get("error"), setup.get("error")
                tenant_record = db.get(Tenant, setup["tenant_id"])
                assert tenant_record and tenant_record.slug == setup["tenant_slug"]
                canonical = db.get(EnterpriseWorkspace, setup["project_id"])
                assert canonical and canonical.tenant_id == tenant_record.id
                assert canonical.parent_id == setup["portfolio_id"] and canonical.status == "pending"
                result["continued_from_current_execution"] = str(setup_path)
            else:
                setup = setup_fresh_capital_owner(db)
            setup_evidence = {name: value for name, value in setup.items() if name not in {"db", "client", "headers"}}
            result["setup"] = setup_evidence
            checkpoint(current, setup_evidence)
            tenant, author, reviewer = setup["tenant_id"], setup["actor_id"], setup["reviewer_id"]
            admin, publisher = setup["admin_author_id"], setup["admin_publisher_id"]
            portfolio, project = (
                db.get(EnterpriseWorkspace, setup["portfolio_id"]),
                db.get(EnterpriseWorkspace, setup["project_id"]),
            )
            assert project.status == "pending"
            identity_before = {
                field: getattr(project, field) for field in ("id", "code", "external_key", "record_code")
            }
            current = "CURRENT_SOURCE_CONFIGURATION"
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
            checkpoint(current, configs)

            current = "FEL1_PRELIMINARY_BUSINESS_CASE"
            fel = service(ProjectDefinitionService, db, tenant, author, "project_definition.status.manage")
            fel.start_fel(
                project.id,
                StartFELIn(
                    stage_code="FEL-1", framework_configuration_id=configs["fel"]["id"], idempotency_key=key("fel1")
                ),
            )
            business = service(BusinessCaseService, db, tenant, author, "business_case.create")
            business_reviewer = service(BusinessCaseService, db, tenant, reviewer, "business_case.complete")
            case = business.create(project.id, setup["proposal_id"], author, reviewer, key("bc-initial"))
            initial = complete_case(business, business_reviewer, case, case.current_revision, "FEL-1")
            checkpoint(current, ref(initial))

            current = "A8_A12_PORTFOLIO_SOURCES"
            planning_policies = configure_portfolio_policies(db, tenant, admin, publisher, portfolio)
            planning = prepare_portfolio_sources(
                db, tenant, author, reviewer, portfolio, project, policies=planning_policies
            )
            checkpoint(
                current,
                {
                    "hashes": planning["hashes"],
                    "budget": ref(planning["budget_scenario"]),
                    "resources": ref(planning["resource_scenario"]),
                    "convergence": ref(planning["convergence"]),
                },
            )

            current = "A13_PERIODIC_PORTFOLIO_REVIEW"
            periodic_review = complete_periodic_review(
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
            checkpoint(current, periodic_review)

            current = "FEL1_TO_FEL3"
            fel_reviewer = service(ProjectDefinitionService, db, tenant, reviewer, "project_definition_stage.review")
            fel_records = []
            for stage in ("FEL-1", "FEL-2", "FEL-3"):
                assert fel.fel_status(project.id).current_stage_code == stage
                assessment = _complete_current(fel, project.id, score=92)
                fel_records.append(ref(assessment))
                # Assessment readiness is only admission to independent stage
                # review. The final FEL-3 stage must be reviewed too, before
                # source domains or the final Business Case capture its state.
                status = fel.submit_stage_review(
                    project.id, fel.fel_status(project.id).revision_version, key("fel-submit")
                )
                fel_reviewer.complete_stage(project.id, status.revision_version, key("fel-review"))
            checkpoint(current, {"assessments": fel_records, "evidence": ref(fel.investment_gate_evidence(project.id))})

            current = "RISK_PERMIT_BASIC_DATA_OWNER"
            risk = service(RiskReadinessService, db, tenant, author, "project_risk.create")
            risk_reviewer = service(RiskReadinessService, db, tenant, reviewer, "risk_readiness_assessment.complete")
            _low_risk(risk, project.id, title="Fresh capital expansion controlled delivery risk")
            assessment = risk.create_assessment(project.id, AssessmentCreateIn(idempotency_key=key("risk-assess")))
            assessment = risk_reviewer.complete_assessment(
                assessment.id, assessment.revision_version, AssessmentActionIn(idempotency_key=key("risk-complete"))
            )
            sources = {"risk": ref(assessment)}
            sources["permit"] = complete_permits(db, tenant, author, reviewer, project.id)
            sources["basic_data"] = complete_basic_data(db, tenant, author, reviewer, project.id)
            sources["owner_capability"] = complete_owner_capability(db, tenant, author, reviewer, project.id)
            checkpoint(current, sources)

            current = "FUNDING_AND_FINANCIAL_MODEL"
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
            checkpoint(
                current,
                {
                    "funding": ref(funding),
                    "model": ref(model),
                    "version": ref(fin),
                    "instruments": {name: record.id for name, record in instruments.items()},
                },
            )

            current = "COMMERCIAL_BENEFITS_FINAL_FIVE_CASE"
            commercial = complete_commercial(db, tenant, author, reviewer, project.id)
            benefits = complete_benefits(
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
            revision = business.refresh(case.id, case.revision_version, key("bc-ffa-refresh"))
            revision = complete_case(business, business_reviewer, case, revision, "FFA")
            # Check live providers after the final BC reverse-link changes, not stored flags.
            benefit_provider = service(
                StrategicBenefitsService, db, tenant, author, "benefits_plan.read"
            ).provider_evidence(project.id)
            commercial_provider = service(
                CommercialStrategyService, db, tenant, author, "commercial_strategy.read"
            ).provider_evidence(project.id)
            assert benefit_provider.source_current is True
            assert commercial_provider.source_current is True
            checkpoint(
                current,
                {
                    "commercial": commercial,
                    "benefits": benefits,
                    "business_case": ref(revision),
                    "benefit_provider": ref(benefit_provider),
                    "commercial_provider": ref(commercial_provider),
                },
            )

            def set_stage(value):
                nonlocal current
                current = value

            finish_investment_lifecycle(db, setup, configs, project, portfolio, identity_before, checkpoint, set_stage)
            # Backend chain is necessary, not sufficient for release: browser,
            # negative/history and complete A0–A31 mapping remain independently required.
            result["backend_chain"] = "PASS"
    except Exception as exc:
        result["blocker"] = {
            "stage": current,
            "exception": type(exc).__name__,
            "detail": getattr(exc, "detail", str(exc)),
            "traceback": traceback.format_exc(),
        }
        print(json.dumps(result["blocker"], indent=2, default=str), flush=True)
        raise
    finally:
        result["elapsed_seconds"] = round(perf_counter() - started, 3)
        result["finished_at"] = utc_now().isoformat()
        ARTIFACT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")


def finish_investment_lifecycle(
    db, setup, configs, project, portfolio, identity_before, checkpoint, set_stage, *, operational_conditions=None
):
    """The shared original A27-A31 command tail; no parallel implementation."""
    tenant, author, reviewer = setup["tenant_id"], setup["actor_id"], setup["reviewer_id"]
    stage = "A27_A29_GATE_PREPARATION_FREEZE"
    set_stage(stage)
    # Effective reusable policy preview belongs to the actual ADMIN actor.
    # Do not grant policy configuration/view authority to the USER preparer.
    policy = service(
        InvestmentEvidencePolicyService, db, tenant, setup["admin_author_id"], "investment_evidence_policy.read"
    )
    preview = policy.preview(
        portfolio_id=portfolio.id,
        gate_profile_code="PYP-FFA",
        project_ids=[project.id],
        configuration_id=configs["evidence_policy"]["id"],
        content_override=None,
    )
    checkpoint("EFFECTIVE_POLICY_PREVIEW", ref(preview))
    preparer = service(InvestmentGatePreparationService, db, tenant, author, "investment_gate_preparation.create")
    validator = service(InvestmentGatePreparationService, db, tenant, reviewer, "investment_gate_evidence.validate")
    candidates = [
        record
        for record in preparer.preparations(portfolio.id)
        if record.investment_gate_profile_id == configs["ffa_profile"]["id"]
        and record.source_snapshot.get("selected_project_ids") == [project.id]
        and record.status not in {"VOIDED", "SUPERSEDED"}
    ]
    assert len(candidates) <= 1, "Resolve the exact existing preparation; do not bypass an interrupted lifecycle"
    preparation = (
        candidates[0]
        if candidates
        else preparer.create(
            PreparationCreateIn(
                portfolio_workspace_id=portfolio.id,
                investment_gate_profile_id=configs["ffa_profile"]["id"],
                name="Fresh Capital Owner FFA current baseline",
                description="Governed UAT chain; representative controlled Class B references require independent review",
                idempotency_key=key("preparation"),
            )
        )
    )
    checkpoint("GATE_BEFORE_CONTROLLED_CLASS_B", ref(preparation))
    if preparation.status != "FROZEN":
        set_stage("A27_CONTROLLED_CLASS_B_EVIDENCE")
        permit = service(
            PermitReadinessService, db, tenant, author, "permit_readiness.read"
        ).project_investment_gate_evidence(project.id)
        commercial = service(
            CommercialStrategyService, db, tenant, author, "commercial_strategy.read"
        ).provider_evidence(project.id)
        assert permit.source_current and permit.readiness_status == "READY", ref(permit)
        assert commercial.source_current and commercial.can_supply_investment_gate_evidence, ref(commercial)
        # These remain supporting material in explicitly labelled documents.
        # They do not become providers for the published Class B requirements.
        supporting_sources = {
            "permit-readiness": {
                name: getattr(permit, name)
                for name in (
                    "assessment_id",
                    "permit_source_hash",
                    "permit_readiness_hash",
                    "required_permit_count",
                    "approved_permit_count",
                    "source_current",
                    "readiness_status",
                )
            },
            "contracting-strategy-readiness": {
                name: getattr(commercial, name)
                for name in (
                    "commercial_strategy_id",
                    "version_id",
                    "commercial_strategy_hash",
                    "source_current",
                )
            },
        }
        preparation = complete_controlled_references(
            service(InvestmentGatePreparationService, db, tenant, author, "investment_gate_evidence.add"),
            validator,
            preparation,
            setup,
            ARTIFACT.parent,
            supporting_sources,
            checkpoint,
        )
    readiness = validator.readiness(preparation.id)
    preparation = validator.preparation(preparation.id)
    reconciliation = reconcile_requirements(preparation)
    required_rows = [row for row in reconciliation if row["required"]]
    optional_rows = [row for row in reconciliation if not row["required"]]
    checkpoint(
        "A27_ALL_REQUIREMENTS_RECONCILIATION",
        {
            "preparation_id": preparation.id,
            "rows": reconciliation,
            "required_row_count": len(required_rows),
            "optional_row_count": len(optional_rows),
            "readiness": ref(readiness),
            "project_readiness": ref(validator.project_readiness(preparation.id)),
        },
    )
    assert len(required_rows) == 19, reconciliation
    assert readiness.readiness_status == "READY", readiness.model_dump(mode="json")
    assert readiness.source_current and readiness.coverage_percent == 100
    assert readiness.required_project_count == readiness.valid_project_count == 1
    checkpoint(
        "A28_CURRENT_SOURCE_CONSISTENCY",
        {
            "source_current": readiness.source_current,
            "cross_source_consistency": readiness.cross_source_consistency,
            "criterion_evaluations": readiness.criterion_evaluations,
            "policy": preparation.source_snapshot["evidence_policy"],
            "provider_evidence": [ref(row) for row in preparation.evidence if row.provider_key],
        },
    )
    set_stage(stage)
    if preparation.status != "FROZEN":
        if preparation.status != "READY_FOR_REVIEW":
            preparation = preparer.ready_for_review(preparation.id, preparation.revision_version, key("ready"))
        preparation = service(
            InvestmentGatePreparationService, db, tenant, reviewer, "investment_gate_preparation.freeze"
        ).freeze(preparation.id, preparation.revision_version, key("freeze"))
    handoff = validator.handoff(preparation.id)
    assert handoff.final_output == "READY_FOR_INVESTMENT_DECISION"
    assert handoff.can_enter_investment_decision and not handoff.can_enter_fid
    checkpoint("A29_FROZEN_PACKAGE", {"preparation": ref(preparation), "handoff": ref(handoff)})
    checkpoint(stage, {"preparation": ref(preparation), "readiness": ref(readiness)})

    stage = "A30_FID"
    set_stage(stage)
    decision_service = service(InvestmentDecisionService, db, tenant, author, "investment_decision.create")
    reviewer_service = service(InvestmentDecisionService, db, tenant, reviewer, "investment_decision.read")
    existing = [
        record
        for record in decision_service.list(portfolio_workspace_id=portfolio.id)
        if record.investment_gate_preparation_id == preparation.id and record.status != "VOIDED"
    ]
    assert len(existing) <= 1, "Never create a new decision to bypass a current decision lifecycle"
    decision = (
        existing[0]
        if existing
        else decision_service.create(
            DecisionCreateIn(
                investment_gate_preparation_id=preparation.id,
                title="Fresh capital owner FFA",
                executive_summary="Independent formal authorization of governed USD100M expansion",
                idempotency_key=key("decision"),
            )
        )
    )
    if decision.status == "DRAFT":
        decision = decision_service.update(
            decision.id,
            decision.revision_version,
            DecisionUpdateIn(decision_maker_user_id=setup["decision_maker_id"], rationale="Independent FID authority"),
        )
        decision = decision_service.submit(decision.id, decision.revision_version, key("decision-submit"))
    if decision.status == "SUBMITTED":
        decision = reviewer_service.start_review(decision.id, decision.revision_version, key("decision-review"))
    if decision.status == "IN_REVIEW":
        decision = reviewer_service.ready(
            decision.id,
            decision.revision_version,
            DecisionReadyIn(
                idempotency_key=key("decision-ready"),
                checklist=[
                    ChecklistAcknowledgement(code=item["code"], acknowledged=True, note="Fresh source chain verified")
                    for item in decision.checklist
                ],
            ),
        )
    maker = service(InvestmentDecisionService, db, tenant, setup["decision_maker_id"], "investment_decision.decide")
    if decision.status == "READY_FOR_DECISION":
        decision = maker.decide(
            decision.id,
            decision.revision_version,
            DecisionDecideIn(
                outcome="GO",
                rationale="Formal FID, not operational activation",
                conditions=operational_conditions or [],
                authorized_amount="100000000",
                authorized_currency="USD",
                idempotency_key=key("decide"),
            ),
        )
    assert decision.status == "DECIDED" and decision.outcome == "GO" and decision.profile_code == "PYP-FFA"
    assert decision.is_fid and decision.full_funds_authorized and decision.investment_authorized
    assert decision.authorization_output["can_activate_project"] is False
    assert decision.source_preparation_hash == preparation.preparation_hash
    assert decision.decision_hash and decision.decided_by == setup["decision_maker_id"]
    db.refresh(project)
    assert project.status == "pending", "FID must not activate the Project automatically"
    checkpoint(stage, ref(decision))

    stage = "A31_POST_FID"
    set_stage(stage)
    post = service(PostFIDGovernanceService, db, tenant, author, "post_fid_governance.evaluate")
    eligibility = post.evaluate(decision.id, key("post-fid"), 1)
    assert len(eligibility) == 1 and eligibility[0].eligibility_status == READY_INITIALIZATION
    db.refresh(project)
    assert project.status == "pending"
    assert identity_before == {field: getattr(project, field) for field in identity_before}
    checkpoint(stage, [ref(item) for item in eligibility])
    stage = "PROJECT_WORKSPACE_INITIALIZATION_ACTIVATION"
    set_stage(stage)
    initializer, activator = setup["initializer_id"], setup["activator_id"]
    assert len({initializer, activator, author, setup["decision_maker_id"]}) == 4
    initial_handoff = post.initialization_handoff(decision.id, project.id, key("initialization-handoff"))
    assert initial_handoff.can_initialize and not initial_handoff.can_activate
    init_context = require_enterprise_permission(
        db, tenant, initializer, "project_workspace.initialization.execute", bootstrap=False
    )
    init_service = ProjectWorkspaceInitializationService(db, tenant, initializer)
    initialized = init_service.start(project.id, init_context, initial_handoff.delegated_revision_version)
    assert initialized.state == InitializationState.ready and initialized.workspace_status == "pending", ref(
        initialized
    )
    checkpoint("PROJECT_INITIALIZED_NOT_ACTIVATED", ref(initialized))
    validated = init_service.validate(project.id, init_context, initialized.revision_version)
    assert validated.state == InitializationState.ready, ref(validated)
    refreshed = post.refresh(decision.id, key("post-initialization-refresh"), eligibility[0].eligibility_round)
    assert len(refreshed) == 1 and refreshed[0].eligibility_status == READY_ACTIVATION, [
        ref(item) for item in refreshed
    ]
    activation_handoff = post.activation_handoff(decision.id, project.id, key("activation-handoff"))
    assert activation_handoff.can_activate and not activation_handoff.can_initialize
    activate_context = require_enterprise_permission(
        db, tenant, activator, "project_workspace.activation.execute", bootstrap=False
    )
    activated = ProjectWorkspaceInitializationService(db, tenant, activator).activate(
        project.id, activate_context, activation_handoff.delegated_revision_version
    )
    assert activated.state == InitializationState.activated and activated.activated_by_user_id == activator, ref(
        activated
    )
    db.refresh(project)
    assert project.status == "active"
    assert identity_before == {field: getattr(project, field) for field in identity_before}
    final_eligibility = post.refresh(decision.id, key("post-activation-refresh"), refreshed[0].eligibility_round)
    assert len(final_eligibility) == 1 and final_eligibility[0].eligibility_status == NO_REACTIVATION
    checkpoint(
        stage,
        {
            "initialize_actor_id": initializer,
            "activate_actor_id": activator,
            "initialization_handoff": ref(initial_handoff),
            "initialized": ref(initialized),
            "validated": ref(validated),
            "activation_handoff": ref(activation_handoff),
            "activated": ref(activated),
            "post_fid_final": [ref(item) for item in final_eligibility],
            "project_identity": identity_before,
            "fid_unchanged": ref(maker.get(decision.id)),
        },
    )


def continue_investment_tail():
    """Resume the recorded same-chain tail; never rely on historical numeric IDs."""
    assert_disposable()
    original = ARTIFACT.read_bytes()
    result = json.loads(original)
    setup = result["setup"]
    assert result.get("blocker"), "Continuation requires a literal interrupted attempt"
    assert result["blocker"]["stage"] in {
        "A27_A29_GATE_PREPARATION_FREEZE",
        "A27_CONTROLLED_CLASS_B_EVIDENCE",
        "A30_FID",
        "A31_POST_FID",
        "PROJECT_WORKSPACE_INITIALIZATION_ACTIVATION",
    }
    saved = ARTIFACT.with_name(f"fresh-capital-owner-chain-project{setup['project_id']}-attempt-{uuid4().hex}.json")
    assert not saved.exists(), "Do not replace the literal previous attempt"
    saved.write_bytes(original)
    prior = result.pop("blocker")
    result.setdefault("attempt_history", []).append(
        {"previous_blocker": prior, "literal_artifact": saved.name, "continuation_started_at": utc_now().isoformat()}
    )
    result["continuation"] = (
        f"Same verified tenant {setup['tenant_id']} / Project {setup['project_id']}; shared governed A27-A31 tail"
    )
    current = "CONTINUATION_VALIDATE_SAME_PROJECT_AND_SOURCES"
    started = perf_counter()

    def set_stage(value):
        nonlocal current
        current = value

    def checkpoint(stage, data):
        result["stages"].append({"stage": stage, "status": "PASS", "data": data})
        ARTIFACT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        print(f"PASS {stage}", flush=True)

    try:
        with SessionLocal() as db:
            tenant, author = setup["tenant_id"], setup["actor_id"]
            project, portfolio = (
                db.get(EnterpriseWorkspace, setup["project_id"]),
                db.get(EnterpriseWorkspace, setup["portfolio_id"]),
            )
            tenant_record = db.get(Tenant, tenant)
            assert tenant_record is not None and tenant_record.slug == setup["tenant_slug"]
            assert project and portfolio and project.tenant_id == portfolio.tenant_id == tenant
            assert (
                project.workspace_type_code == "project"
                and project.parent_id == portfolio.id
                and project.status == "pending"
            )
            recorded = next(event["project"] for event in setup["events"] if event["case"] == "A6")
            identity = {field: getattr(project, field) for field in ("id", "code", "external_key", "record_code")}
            assert identity == {field: recorded[field] for field in identity}
            stages = {stage["stage"]: stage["data"] for stage in result["stages"]}
            business = service(BusinessCaseService, db, tenant, author, "business_case.read")
            case = business.by_project(project.id)
            captured_bc = stages["COMMERCIAL_BENEFITS_FINAL_FIVE_CASE"]["business_case"]
            assert case.current_revision.id == captured_bc["id"] and case.current_revision.status == "COMPLETED"
            assert business.readiness(case.id).status == "READY"
            sources = {}
            for name, cls, permission, source_id in (
                (
                    "financial",
                    EconomicFinancialModelService,
                    "economic_financial_model.read",
                    stages["FUNDING_AND_FINANCIAL_MODEL"]["model"]["id"],
                ),
                ("commercial", CommercialStrategyService, "commercial_strategy.read", project.id),
                ("benefits", StrategicBenefitsService, "benefits_plan.read", project.id),
            ):
                source = service(cls, db, tenant, author, permission).provider_evidence(source_id)
                assert source.source_current and source.can_supply_investment_gate_evidence, ref(source)
                sources[name] = ref(source)
            checkpoint(
                current, {"tenant_id": tenant, "project_id": project.id, "identity": identity, "providers": sources}
            )
            finish_investment_lifecycle(
                db, setup, stages["CURRENT_SOURCE_CONFIGURATION"], project, portfolio, identity, checkpoint, set_stage
            )
            result["backend_chain"] = "PASS"
    except Exception as exc:
        result["blocker"] = {
            "stage": current,
            "exception": type(exc).__name__,
            "detail": getattr(exc, "detail", str(exc)),
            "traceback": traceback.format_exc(),
        }
        print(json.dumps(result["blocker"], indent=2, default=str), flush=True)
        raise
    finally:
        result["continuation_elapsed_seconds"] = round(perf_counter() - started, 3)
        result["finished_at"] = utc_now().isoformat()
        ARTIFACT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")


def continue_final_fel_review():
    """Diagnose the existing Project-12 interrupted journey through real commands.

    This is deliberately not a new chain or a replacement for the normal run.
    It never repairs captured source/hash fields or writes source final states.
    An open BC revision must use its supported lifecycle, or remain blocked.
    """
    assert_disposable()
    original = ARTIFACT.read_bytes()
    result = json.loads(original)
    setup = result["setup"]
    assert (setup["tenant_id"], setup["project_id"], setup["portfolio_id"]) == (3, 12, 11)
    assert result["blocker"]["stage"] == "COMMERCIAL_BENEFITS_FINAL_FIVE_CASE"
    saved = ARTIFACT.with_name("fresh-capital-owner-chain-project12-fel-review-blocker.json")
    assert not saved.exists(), "Do not replace the literal previous attempt"
    saved.write_bytes(original)
    prior = result.pop("blocker")
    result.setdefault("attempt_history", []).append(
        {"previous_blocker": prior, "literal_artifact": saved.name, "continuation_started_at": utc_now().isoformat()}
    )
    result["continuation"] = "Same tenant 3 / Project 12; official final FEL stage review only"
    started = perf_counter()
    current = "CONTINUE_FEL3_INDEPENDENT_REVIEW"

    def checkpoint(stage, data):
        result["stages"].append({"stage": stage, "status": "PASS", "data": data})
        ARTIFACT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        print(f"PASS {stage}", flush=True)

    try:
        with SessionLocal() as db:
            tenant, author, reviewer = setup["tenant_id"], setup["actor_id"], setup["reviewer_id"]
            project = db.get(EnterpriseWorkspace, setup["project_id"])
            assert project is not None and project.tenant_id == tenant
            assert project.workspace_type_code == "project" and project.parent_id == setup["portfolio_id"]
            assert project.status == "pending" and author != reviewer
            recorded = next(event["project"] for event in setup["events"] if event["case"] == "A6")
            identity = {field: getattr(project, field) for field in ("id", "code", "external_key", "record_code")}
            assert identity == {field: recorded[field] for field in identity}
            fel = service(ProjectDefinitionService, db, tenant, author, "project_definition_stage.submit")
            fel_reviewer = service(ProjectDefinitionService, db, tenant, reviewer, "project_definition_stage.review")
            before = fel.fel_status(project.id)
            assert before.current_stage_code == "FEL-3" and before.status == "IN_STAGE"
            actual_readiness = fel.readiness(project.id)
            assert actual_readiness.status == "READY" and actual_readiness.source_current
            submitted = fel.submit_stage_review(project.id, before.revision_version, key("continue-fel3-submit"))
            completed = fel_reviewer.complete_stage(
                project.id, submitted.revision_version, key("continue-fel3-independent-review")
            )
            assert completed.status == "STAGE_COMPLETED" and completed.readiness_status == "READY"
            checkpoint(current, {"before": ref(before), "submitted": ref(submitted), "completed": ref(completed)})

            current = "CONTINUATION_CURRENT_SOURCE_DIAGNOSIS"
            financing = next(
                stage["data"] for stage in result["stages"] if stage["stage"] == "FUNDING_AND_FINANCIAL_MODEL"
            )
            providers = {}
            for name, cls, permission, source_id in (
                ("financial", EconomicFinancialModelService, "economic_financial_model.read", financing["model"]["id"]),
                ("commercial", CommercialStrategyService, "commercial_strategy.read", project.id),
                ("benefits", StrategicBenefitsService, "benefits_plan.read", project.id),
            ):
                try:
                    providers[name] = ref(service(cls, db, tenant, author, permission).provider_evidence(source_id))
                except Exception as exc:
                    providers[name] = {
                        "status": "BLOCKED",
                        "exception": type(exc).__name__,
                        "detail": getattr(exc, "detail", str(exc)),
                    }
            checkpoint(current, {"providers": providers, "source_business_commands": 0})

            current = "CONTINUATION_EXISTING_DRAFT_BUSINESS_CASE_REFRESH"
            business = service(BusinessCaseService, db, tenant, author, "business_case.refresh")
            case = business.by_project(project.id)
            assert case.id == 3 and case.current_revision.id == 4 and case.current_revision.status == "DRAFT"
            # The actual official command decides whether an open revision can
            # capture new sources. Never inject source snapshots via a generic
            # update, mark it VOIDED through ORM, or complete it while blocked.
            business.refresh(case.id, case.revision_version, key("continue-existing-draft-refresh"))
            raise AssertionError("Unexpected DRAFT refresh acceptance; review actual lifecycle before continuing")
    except Exception as exc:
        result["blocker"] = {
            "stage": current,
            "exception": type(exc).__name__,
            "detail": getattr(exc, "detail", str(exc)),
            "traceback": traceback.format_exc(),
        }
        print(json.dumps(result["blocker"], indent=2, default=str), flush=True)
        raise
    finally:
        result["continuation_elapsed_seconds"] = round(perf_counter() - started, 3)
        result["finished_at"] = utc_now().isoformat()
        ARTIFACT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    if os.environ.get("PYPMIS_FRESH_CONTINUE_INVESTMENT_TAIL") == "same-chain":
        continue_investment_tail()
    elif os.environ.get("PYPMIS_FRESH_CONTINUE_FINAL_FEL") == "tenant-3-project-12":
        continue_final_fel_review()
    else:
        run()
