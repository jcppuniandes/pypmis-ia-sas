"""Material currentness of a consumed FID after its canonical activation.

This is not planning re-entry authorization. All reads remain tenant scoped and
the pending-only entry policy and frozen decision artifacts remain untouched.
"""

from copy import deepcopy

from sqlalchemy import select

from app.core.time import utc_now
from app.domain.models import EnterpriseWorkspace, SecurityEvent
from app.modules.investment_decision.models import InvestmentDecision
from app.modules.portfolio_convergence.models import PortfolioScenarioConvergence
from app.modules.portfolio_convergence.service import PortfolioConvergenceService
from app.modules.portfolio_evaluation.service import PortfolioEvaluationService
from app.modules.post_fid_governance.models import PostFIDProjectEligibility
from app.modules.project_workspace_initialization.models import ProjectWorkspaceInitialization

ENTRY_ONLY_BLOCKERS = frozenset(
    {
        "GATE07E_NO_ELIGIBLE_CAPITAL_OWNER_PROJECTS",
        "GATE07E_PORTFOLIO_HAS_BLOCKED_PROJECTS",
        "READY_FOR_PORTFOLIO_ANALYSIS_REQUIRED",
        "READY_FOR_PORTFOLIO_BUDGET_RECOMMENDATION_REQUIRED",
        "READY_FOR_PORTFOLIO_RESOURCE_PLANNING_REQUIRED",
        "READY_FOR_PORTFOLIO_RESOURCE_RECOMMENDATION_REQUIRED",
        "READY_FOR_PORTFOLIO_SCENARIO_PLANNING_WITH_BUDGET_REQUIRED",
    }
)


def _canonical_activation(db, tenant, decision, project, configuration):
    # Use the certificate owner's serialization (not Gate07J's Unicode hash).
    from app.modules.post_fid_governance.service import _hash

    initialization = db.scalar(
        select(ProjectWorkspaceInitialization).where(
            ProjectWorkspaceInitialization.tenant_id == tenant,
            ProjectWorkspaceInitialization.workspace_id == project.id,
        )
    )
    certificate = db.scalar(
        select(PostFIDProjectEligibility)
        .where(
            PostFIDProjectEligibility.tenant_id == tenant,
            PostFIDProjectEligibility.investment_decision_id == decision.id,
            PostFIDProjectEligibility.project_workspace_id == project.id,
            PostFIDProjectEligibility.eligibility_status == "READY_FOR_PROJECT_WORKSPACE_ACTIVATION",
        )
        .order_by(PostFIDProjectEligibility.eligibility_round.desc())
    )
    if initialization is None or certificate is None:
        return False
    summary = dict(certificate.project_state_snapshot or {})
    if not (
        initialization.tenant_id == certificate.tenant_id == tenant
        and initialization.workspace_id == certificate.project_workspace_id == project.id
        and certificate.investment_decision_id == decision.id
        and certificate.eligibility_status == "READY_FOR_PROJECT_WORKSPACE_ACTIVATION"
        and initialization.state == "ACTIVATED"
        and initialization.started_by_user_id
        and initialization.activated_by_user_id
        and initialization.activated_by_user_id
        not in {initialization.started_by_user_id, initialization.last_modified_by_user_id}
        and initialization.activated_at
        and initialization.ready_at
        and initialization.validation_hash
        and initialization.checklist_hash
        and initialization.ready_at <= initialization.activated_at
        and initialization.ready_at <= certificate.evaluated_at
        and certificate.evaluated_at <= initialization.activated_at
        and certificate.source_current
        and certificate.eligible_for_activation
        and not certificate.eligible_for_initialization
        and not certificate.blockers_json
        and certificate.fid_decision_hash == decision.decision_hash
        and certificate.decision_package_hash == decision.source_package_hash
        and certificate.condition_snapshot_hash == _hash(decision.conditions_json or [])
        and certificate.configuration_id == configuration.id
        and certificate.configuration_hash == configuration.content_hash
        and summary.get("workspace_status") == "pending"
        and summary.get("classified_state") == "INITIALIZED_NOT_ACTIVE"
        and summary.get("initialization_state") == "READY_FOR_ACTIVATION"
        and project.version > 1
        and initialization.revision_version > 1
    ):
        return False
    # 07L persists a three-field state summary, but its original hash includes
    # the full canonical state. 05C activation increments these two versions
    # exactly once. Reconstruct that predecessor only after proving the real
    # transition below, and require the existing immutable hash to authenticate
    # every reconstructed value. Any later version change fails closed.
    state = {
        "workspace_id": project.id,
        "workspace_type_code": project.workspace_type_code,
        "workspace_status": "pending",
        "workspace_version": project.version - 1,
        "initialization_id": initialization.id,
        "initialization_state": "READY_FOR_ACTIVATION",
        "initialization_revision": initialization.revision_version - 1,
        "classified_state": "INITIALIZED_NOT_ACTIVE",
    }
    expected_certificate = _hash(
        {
            "investment_decision_id": decision.id,
            "fid_decision_hash": decision.decision_hash,
            "decision_package_hash": decision.source_package_hash,
            "project": state,
            "conditions": decision.conditions_json or [],
            "authorization_valid_until": decision.authorization_valid_until,
            "configuration_hash": certificate.configuration_hash,
            "eligibility_status": certificate.eligibility_status,
            "warnings": certificate.warnings_json or [],
            "blockers": certificate.blockers_json or [],
        }
    )
    if certificate.eligibility_hash != expected_certificate:
        return False
    handoffs = db.scalars(
        select(SecurityEvent).where(
            SecurityEvent.tenant_id == tenant,
            SecurityEvent.event_type == "post_fid_governance.activation_handoff_invoked",
            SecurityEvent.target_type == "InvestmentDecision",
            SecurityEvent.target_id == decision.id,
            SecurityEvent.outcome == "success",
            SecurityEvent.occurred_at >= certificate.evaluated_at,
            SecurityEvent.occurred_at <= initialization.activated_at,
        )
    )
    if not any(
        event.metadata_json.get("investment_decision_id") == decision.id
        and event.metadata_json.get("project_workspace_id") == project.id
        and event.metadata_json.get("delegated") is True
        for event in handoffs
    ):
        return False
    events = db.scalars(
        select(SecurityEvent).where(
            SecurityEvent.tenant_id == tenant,
            SecurityEvent.event_type == "project_workspace.activated",
            SecurityEvent.target_type == "project_workspace",
            SecurityEvent.target_id == project.id,
            SecurityEvent.user_id == initialization.activated_by_user_id,
            SecurityEvent.outcome == "success",
            SecurityEvent.occurred_at >= certificate.evaluated_at,
        )
    )
    return any(
        event.metadata_json.get("initialization_id") == initialization.id
        and event.metadata_json.get("workspace_id") == project.id
        and event.metadata_json.get("actor_id") == initialization.activated_by_user_id
        and event.metadata_json.get("state_before") == "READY_FOR_ACTIVATION"
        and event.metadata_json.get("state_after") == "ACTIVATED"
        and event.metadata_json.get("validation_hash") == initialization.validation_hash
        and event.metadata_json.get("checklist_hash") == initialization.checklist_hash
        for event in events
    )


def consumed_fid_contract(service, preparation, decision):
    """Return the unchanged captured contract only for proven own activation.

    Current convergence fingerprints are recomputed using the existing services.
    Only new-entry readiness is allowed to differ; no actual stale source is ignored.
    """
    # Runtime import avoids the existing 07L -> 07K dependency cycle.
    from app.modules.investment_decision.service import _hash
    from app.modules.post_fid_governance.service import PostFIDGovernanceService

    if decision is None or not (
        decision.tenant_id == preparation.tenant_id == service.tenant_id
        and decision.status == "DECIDED"
        and decision.profile_code == preparation.profile_code == "PYP-FFA"
        and decision.outcome == "GO"
        and decision.is_fid
        and decision.investment_authorized
        and decision.full_funds_authorized
        and decision.decision_hash == service._decision_hash(decision, decision.decided_at)
        and decision.source_package_hash == _hash(decision.decision_package_snapshot_json or {})
        and decision.investment_gate_preparation_id == preparation.id
        and decision.portfolio_workspace_id == preparation.portfolio_workspace_id
        and decision.source_preparation_hash == preparation.preparation_hash
        and decision.decision_scope_hash == preparation.recommended_project_set_hash
        and (decision.authorization_valid_until is None or decision.authorization_valid_until >= utc_now())
    ):
        return None
    db, tenant, actor, context = service.db, service.tenant_id, service.actor_id, service.context
    if db.scalar(
        select(InvestmentDecision.id).where(
            InvestmentDecision.tenant_id == tenant,
            InvestmentDecision.investment_gate_preparation_id == preparation.id,
            InvestmentDecision.profile_code == decision.profile_code,
            InvestmentDecision.decision_round > decision.decision_round,
            InvestmentDecision.status == "DECIDED",
        )
    ):
        return None
    captured = deepcopy(dict(preparation.source_snapshot_json.get("gate07i_contract") or {}))
    selected = set(captured.get("selected_project_set_reference") or [])
    if not selected or selected != set(preparation.source_snapshot_json.get("selected_project_ids") or []):
        return None
    evaluator = PortfolioEvaluationService(db, tenant, actor, context)
    blocked = [item for item in evaluator.evaluation_queue(preparation.portfolio_workspace_id) if not item.eligible]
    if not blocked or any(
        item.project_workspace_id not in selected or item.blocking_issues != ["PROJECT_STATUS_PENDING_REQUIRED"]
        for item in blocked
    ):
        return None
    post = PostFIDGovernanceService(db, tenant, actor, context)
    effective = post._authorization_effective_date(decision)
    if effective is not None and effective > utc_now():
        return None
    configuration = post._published_configuration()
    for item in blocked:
        project = db.get(EnterpriseWorkspace, item.project_workspace_id)
        if (
            project is None
            or project.tenant_id != tenant
            or project.workspace_type_code != "project"
            or project.status != "active"
            or not _canonical_activation(db, tenant, decision, project, configuration)
        ):
            return None
    convergence = PortfolioConvergenceService(db, tenant, actor, context)
    readiness = convergence.readiness(preparation.portfolio_workspace_id)
    if not (
        readiness.source_current
        and set(readiness.blockers).issubset(ENTRY_ONLY_BLOCKERS)
        and readiness.convergence_id == captured.get("convergence_id") == preparation.source_convergence_id
        and readiness.convergence_revision == captured.get("convergence_revision")
        and readiness.recommended_alternative_id == captured.get("recommended_alternative_id")
        and readiness.recommendation_hash
        == captured.get("recommendation_hash")
        == preparation.source_recommendation_hash
    ):
        return None
    record = db.get(PortfolioScenarioConvergence, readiness.convergence_id)
    alternative = convergence._alternative(readiness.recommended_alternative_id)
    if not (
        record.status == "RECOMMENDED"
        and alternative.selected_project_set_hash == preparation.recommended_project_set_hash
        and set(alternative.strategic_summary_json.get("selected_project_ids") or []) == selected
        and record.source_analysis_hash == captured.get("analysis_hash")
        and record.source_membership_set_hash == captured.get("membership_set_hash")
        and record.source_evaluation_set_hash == captured.get("evaluation_set_hash")
        and record.budget_planning_hash == captured.get("budget_planning_hash")
        and record.resource_planning_hash == captured.get("resource_planning_hash")
    ):
        return None
    return captured
