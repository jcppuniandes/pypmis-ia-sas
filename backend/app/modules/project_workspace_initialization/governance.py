"""Read-only bridge from a persisted Gate 07L handoff to canonical lifecycle.

The Strategic Gate creation snapshot is historical. A later FID must not be
copied into it merely to initialize or activate the same Project Workspace.
"""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import EnterpriseWorkspace
from app.modules.post_fid_governance.models import PostFIDProjectEligibility
from app.modules.post_fid_governance.service import (
    READY_ACTIVATION,
    READY_INITIALIZATION,
    PostFIDGovernanceService,
    _hash,
)


def post_fid_lifecycle_authorization(
    db: Session,
    tenant_id: int,
    actor_id: int,
    workspace: EnterpriseWorkspace,
    *,
    for_activation: bool = False,
) -> tuple[bool, dict]:
    """Validate authority, scope and conditions without executing any command.

    Initialization itself changes its state before evaluating the checklist.
    Therefore the immutable handoff's *project-state* hash is not re-evaluated
    here. Its FID, policy, scope and conditions are all checked against current
    authority. Activation additionally needs a separately persisted 07L
    activation handoff; an initialization certificate alone never activates.
    """
    if workspace.tenant_id != tenant_id or workspace.workspace_type_code != "project":
        return False, {}
    latest = db.scalar(
        select(PostFIDProjectEligibility)
        .where(
            PostFIDProjectEligibility.tenant_id == tenant_id,
            PostFIDProjectEligibility.project_workspace_id == workspace.id,
        )
        .order_by(PostFIDProjectEligibility.evaluated_at.desc(), PostFIDProjectEligibility.id.desc())
        .limit(1)
    )
    if latest is None:
        return False, {}
    service = PostFIDGovernanceService(db, tenant_id, actor_id)
    try:
        decision = service._decision(latest.investment_decision_id)
        service._project_in_scope(decision, workspace.id)
        config = service._published_configuration()
        applicable, current, blockers, _warnings = service._decision_validity(decision, config)
    except HTTPException:
        return False, {}
    allowed_statuses = {READY_ACTIVATION} if for_activation else {READY_INITIALIZATION, READY_ACTIVATION}
    authorized = bool(
        applicable
        and current
        and not blockers
        and latest.source_current
        and not latest.blockers_json
        and latest.eligibility_status in allowed_statuses
        and (
            latest.eligible_for_activation
            if for_activation
            else latest.eligible_for_initialization or latest.eligible_for_activation
        )
        and latest.fid_decision_hash == decision.decision_hash
        and latest.decision_package_hash == decision.source_package_hash
        and latest.condition_snapshot_hash == _hash(decision.conditions_json or [])
        and latest.configuration_id == config.id
        and latest.configuration_hash == config.content_hash
        and "CAPITAL_OWNER" in config.content_json.get("applicable_governance_models", [])
    )
    # Stable across the separate initialization/activation handoff snapshots,
    # so the existing canonical validation/checklist hashes remain meaningful.
    evidence = {
        "authority": "GATE07K_FID_AND_PERSISTED_GATE07L",
        "investment_decision_id": decision.id,
        "fid_decision_hash": decision.decision_hash,
        "decision_package_hash": decision.source_package_hash,
        "condition_snapshot_hash": latest.condition_snapshot_hash,
        "post_fid_configuration_id": config.id,
        "post_fid_configuration_hash": config.content_hash,
    }
    return authorized, evidence
