"""Finish the interrupted same-chain observation after a successful activation.

The canonical activation already happened. Never repeat it or reconstruct its
history; verify current persisted authority, then use the official 07L refresh.
"""

import json
import traceback
from uuid import uuid4

from sqlalchemy import select
from tests.strategic_capital_owner_full_e2e_current import ARTIFACT, assert_disposable, key, ref, service
from tests.strategic_resume_post_fid_initialization import persisted

from app.core.time import utc_now
from app.database.session import SessionLocal
from app.domain.models import EnterpriseWorkspace, SecurityEvent, Tenant
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.investment_decision.models import InvestmentDecision
from app.modules.investment_decision.service import InvestmentDecisionService
from app.modules.investment_gate_preparation.models import InvestmentGatePreparation
from app.modules.post_fid_governance.models import PostFIDProjectEligibility
from app.modules.post_fid_governance.service import NO_REACTIVATION, PostFIDGovernanceService
from app.modules.project_workspace_initialization.service import ProjectWorkspaceInitializationService


def main():
    assert_disposable()
    original = ARTIFACT.read_bytes()
    result = json.loads(original)
    assert result["blocker"]["stage"] == "PROJECT_WORKSPACE_INITIALIZATION_ACTIVATION"
    setup = result["setup"]
    saved = ARTIFACT.with_name(f"fresh-capital-owner-chain-post-activation-attempt-{uuid4().hex}.json")
    assert not saved.exists()
    saved.write_bytes(original)
    prior = result.pop("blocker")
    result.setdefault("attempt_history", []).append(
        {"previous_blocker": prior, "literal_artifact": saved.name, "continuation_started_at": utc_now().isoformat()}
    )
    current = "POST_ACTIVATION_CURRENTNESS_VERIFICATION"

    def checkpoint(stage, data):
        result["stages"].append({"stage": stage, "status": "PASS", "data": data})
        ARTIFACT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        print(f"PASS {stage}", flush=True)

    try:
        with SessionLocal() as db:
            tenant, project_id, actor = setup["tenant_id"], setup["project_id"], setup["actor_id"]
            tenant_record, project = db.get(Tenant, tenant), db.get(EnterpriseWorkspace, project_id)
            assert tenant_record.slug == setup["tenant_slug"]
            assert project.tenant_id == tenant and project.parent_id == setup["portfolio_id"]
            assert project.workspace_type_code == "project" and project.status == "active"
            stages = {stage["stage"]: stage["data"] for stage in result["stages"] if stage["status"] == "PASS"}
            decision = db.get(InvestmentDecision, stages["A30_FID"]["id"])
            assert decision.tenant_id == tenant and decision.is_fid and decision.status == "DECIDED"
            preparation = db.get(InvestmentGatePreparation, decision.investment_gate_preparation_id)
            assert preparation.status == "FROZEN" and preparation.tenant_id == tenant
            frozen_before, decision_before, project_before = (
                persisted(preparation),
                persisted(decision),
                persisted(project),
            )
            fid = service(InvestmentDecisionService, db, tenant, actor, "investment_decision.read")
            fid._assert_current(decision)
            initializer = setup["initializer_id"]
            context = require_enterprise_permission(
                db, tenant, initializer, "project_workspace.initialization.execute", bootstrap=False
            )
            initialized = ProjectWorkspaceInitializationService(db, tenant, initializer).get(project_id, context)
            assert initialized.state == "ACTIVATED" and initialized.activated_by_user_id == setup["activator_id"]
            assert initialized.activated_by_user_id != initializer
            activation_events = list(
                db.scalars(
                    select(SecurityEvent).where(
                        SecurityEvent.tenant_id == tenant,
                        SecurityEvent.target_id == project_id,
                        SecurityEvent.event_type == "project_workspace.activated",
                        SecurityEvent.user_id == setup["activator_id"],
                    )
                )
            )
            assert len(activation_events) == 1, "Never repeat activation or invent a second activation event"
            checkpoint(
                current,
                {
                    "decision_id": decision.id,
                    "decision_hash": decision.decision_hash,
                    "preparation_hash": preparation.preparation_hash,
                    "activation_event_id": activation_events[0].id,
                    "canonical_initialization": ref(initialized),
                    "activation_command_repeated": False,
                },
            )
            post = service(PostFIDGovernanceService, db, tenant, actor, "post_fid_governance.evaluate")
            latest = db.scalar(
                select(PostFIDProjectEligibility)
                .where(
                    PostFIDProjectEligibility.tenant_id == tenant,
                    PostFIDProjectEligibility.project_workspace_id == project_id,
                    PostFIDProjectEligibility.investment_decision_id == decision.id,
                )
                .order_by(PostFIDProjectEligibility.eligibility_round.desc())
                .limit(1)
            )
            current = "PROJECT_WORKSPACE_INITIALIZATION_ACTIVATION"
            refreshed = post.refresh(decision.id, key("same-chain-currentness-revalidation"), latest.eligibility_round)
            assert len(refreshed) == 1 and refreshed[0].eligibility_status == NO_REACTIVATION, [
                ref(row) for row in refreshed
            ]
            assert refreshed[0].fid_current and refreshed[0].source_current
            assert not refreshed[0].can_initialize and not refreshed[0].can_activate
            for record in (project, preparation, decision):
                db.refresh(record)
            assert persisted(project) == project_before
            assert persisted(preparation) == frozen_before and persisted(decision) == decision_before
            checkpoint(
                current,
                {
                    "initialize_actor_id": initializer,
                    "activate_actor_id": setup["activator_id"],
                    "initialized": stages["PROJECT_INITIALIZED_NOT_ACTIVATED"],
                    "validated": stages["PROJECT_INITIALIZED_NOT_ACTIVATED"],
                    "activation_handoff": stages["POST_FID_ACTIVATION_ELIGIBILITY"]["handoff"],
                    "activated": ref(initialized),
                    "activation_observed_not_repeated": True,
                    "activation_event_id": activation_events[0].id,
                    "post_fid_final": [ref(row) for row in refreshed],
                    "project_identity": {
                        field: getattr(project, field) for field in ("id", "code", "external_key", "record_code")
                    },
                    "fid_unchanged": ref(fid.get(decision.id)),
                    "project_frozen_and_fid_rows_unchanged": True,
                },
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
        result["finished_at"] = utc_now().isoformat()
        ARTIFACT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
