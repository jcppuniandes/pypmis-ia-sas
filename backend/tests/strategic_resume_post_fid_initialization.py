"""Resume only the recorded blocked initialization through canonical commands.

No upstream reconstruction, new preparation, decision, or terminal-state write.
The literal failed attempt remains archived before any command is executed.
"""

import json
import traceback
from copy import deepcopy
from time import perf_counter
from uuid import uuid4

from sqlalchemy import select
from tests.strategic_capital_owner_full_e2e_current import (
    ARTIFACT,
    assert_disposable,
    key,
    ref,
    service,
)

from app.core.time import utc_now
from app.database.session import SessionLocal
from app.domain.models import EnterpriseWorkspace, Tenant
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.investment_decision.models import InvestmentDecision
from app.modules.investment_decision.service import InvestmentDecisionService
from app.modules.investment_gate_preparation.models import InvestmentGatePreparation
from app.modules.post_fid_governance.models import PostFIDProjectEligibility
from app.modules.post_fid_governance.service import NO_REACTIVATION, READY_ACTIVATION, PostFIDGovernanceService
from app.modules.project_workspace_initialization.schemas import InitializationState
from app.modules.project_workspace_initialization.service import ProjectWorkspaceInitializationService


def persisted(record):
    return deepcopy({column.name: getattr(record, column.name) for column in record.__table__.columns})


def main():
    assert_disposable()
    original = ARTIFACT.read_bytes()
    result = json.loads(original)
    assert result["blocker"]["stage"] in {
        "PROJECT_WORKSPACE_INITIALIZATION_ACTIVATION",
        "VERIFY_EXISTING_FID_AND_BLOCKED_INITIALIZATION",
    }
    setup = result["setup"]
    saved = ARTIFACT.with_name(f"fresh-capital-owner-chain-init-blocked-attempt-{uuid4().hex}.json")
    assert not saved.exists()
    saved.write_bytes(original)
    prior = result.pop("blocker")
    result.setdefault("attempt_history", []).append(
        {"previous_blocker": prior, "literal_artifact": saved.name, "continuation_started_at": utc_now().isoformat()}
    )
    # Correct the old harness's premature PASS without deleting its literal record.
    for stage in result["stages"]:
        if stage["stage"] == "PROJECT_INITIALIZED_NOT_ACTIVATED" and stage["data"].get("state") != "READY":
            stage["status"] = "FAIL"
            stage["recording_correction"] = "Premature checkpoint before READY assertion; literal original archived"
    result["continuation"] = "Same persistent tenant and Project; official validate of existing BLOCKED initialization"
    current = "VERIFY_EXISTING_FID_AND_BLOCKED_INITIALIZATION"
    started = perf_counter()

    def checkpoint(stage, data):
        result["stages"].append({"stage": stage, "status": "PASS", "data": data})
        ARTIFACT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
        print(f"PASS {stage}", flush=True)

    try:
        with SessionLocal() as db:
            tenant, project_id, author = setup["tenant_id"], setup["project_id"], setup["actor_id"]
            project, tenant_record = db.get(EnterpriseWorkspace, project_id), db.get(Tenant, tenant)
            assert tenant_record and tenant_record.slug == setup["tenant_slug"]
            assert project and project.tenant_id == tenant and project.parent_id == setup["portfolio_id"]
            assert project.workspace_type_code == "project" and project.status == "pending"
            recorded = next(event["project"] for event in setup["events"] if event["case"] == "A6")
            identity = {field: getattr(project, field) for field in ("id", "code", "external_key", "record_code")}
            assert identity == {field: recorded[field] for field in identity}
            metadata_before = deepcopy(ProjectWorkspaceInitializationService._metadata(project))
            stages = {stage["stage"]: stage["data"] for stage in result["stages"] if stage["status"] == "PASS"}
            decision_id = stages["A30_FID"]["id"]
            decision = db.get(InvestmentDecision, decision_id)
            assert decision and decision.tenant_id == tenant
            assert decision.status == "DECIDED" and decision.profile_code == "PYP-FFA" and decision.outcome == "GO"
            assert decision.is_fid and decision.full_funds_authorized and decision.investment_authorized
            preparation = db.get(InvestmentGatePreparation, decision.investment_gate_preparation_id)
            assert preparation.status == "FROZEN" and preparation.tenant_id == tenant
            frozen_before, decision_before = persisted(preparation), persisted(decision)
            post = service(PostFIDGovernanceService, db, tenant, author, "post_fid_governance.evaluate")
            latest = db.scalar(
                select(PostFIDProjectEligibility)
                .where(
                    PostFIDProjectEligibility.tenant_id == tenant,
                    PostFIDProjectEligibility.project_workspace_id == project_id,
                    PostFIDProjectEligibility.investment_decision_id == decision_id,
                )
                .order_by(PostFIDProjectEligibility.eligibility_round.desc())
                .limit(1)
            )
            assert latest and latest.eligibility_status == "READY_FOR_PROJECT_WORKSPACE_INITIALIZATION"
            initializer, activator = setup["initializer_id"], setup["activator_id"]
            assert len({initializer, activator, author, setup["decision_maker_id"]}) == 4
            init_context = require_enterprise_permission(
                db, tenant, initializer, "project_workspace.initialization.execute", bootstrap=False
            )
            init_service = ProjectWorkspaceInitializationService(db, tenant, initializer)
            before = init_service.get(project_id, init_context)
            assert before.state == InitializationState.blocked and before.workspace_status == "pending", ref(before)
            checkpoint(
                current, {"project_identity": identity, "initialization": ref(before), "eligibility_id": latest.id}
            )

            current = "PROJECT_INITIALIZED_NOT_ACTIVATED"
            initialized = init_service.validate(project_id, init_context, before.revision_version)
            assert initialized.state == InitializationState.ready and initialized.workspace_status == "pending", ref(
                initialized
            )
            checkpoint(current, ref(initialized))
            current = "POST_FID_ACTIVATION_ELIGIBILITY"
            refreshed = post.refresh(decision_id, key("resume-after-initialization"), latest.eligibility_round)
            assert len(refreshed) == 1 and refreshed[0].eligibility_status == READY_ACTIVATION, [
                ref(row) for row in refreshed
            ]
            handoff = post.activation_handoff(decision_id, project_id, key("resume-activation-handoff"))
            assert handoff.can_activate and not handoff.can_initialize
            checkpoint(current, {"eligibility": [ref(row) for row in refreshed], "handoff": ref(handoff)})
            current = "PROJECT_WORKSPACE_INITIALIZATION_ACTIVATION"
            activate_context = require_enterprise_permission(
                db, tenant, activator, "project_workspace.activation.execute", bootstrap=False
            )
            activated = ProjectWorkspaceInitializationService(db, tenant, activator).activate(
                project_id, activate_context, handoff.delegated_revision_version
            )
            assert activated.state == InitializationState.activated and activated.activated_by_user_id == activator, (
                ref(activated)
            )
            db.refresh(project)
            assert (
                project.status == "active"
                and ProjectWorkspaceInitializationService._metadata(project) == metadata_before
            )
            assert identity == {field: getattr(project, field) for field in identity}
            final_eligibility = post.refresh(decision_id, key("resume-post-activation"), refreshed[0].eligibility_round)
            assert len(final_eligibility) == 1 and final_eligibility[0].eligibility_status == NO_REACTIVATION, [
                ref(row) for row in final_eligibility
            ]
            db.refresh(preparation)
            db.refresh(decision)
            assert persisted(preparation) == frozen_before and persisted(decision) == decision_before
            checkpoint(
                current,
                {
                    "initialize_actor_id": initializer,
                    "activate_actor_id": activator,
                    "initialized": ref(initialized),
                    "validated": ref(initialized),
                    "activation_handoff": ref(handoff),
                    "activated": ref(activated),
                    "post_fid_final": [ref(row) for row in final_eligibility],
                    "project_identity": identity,
                    "fid_unchanged": ref(
                        service(InvestmentDecisionService, db, tenant, author, "investment_decision.read").get(
                            decision_id
                        )
                    ),
                    "creation_metadata_unchanged": True,
                    "frozen_package_and_fid_rows_unchanged": True,
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
        result["initialization_continuation_elapsed_seconds"] = round(perf_counter() - started, 3)
        result["finished_at"] = utc_now().isoformat()
        ARTIFACT.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")


if __name__ == "__main__":
    main()
