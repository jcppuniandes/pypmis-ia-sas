"""Final strategic UAT route proofs, with explicit governance and real HTTP commands.

The reused Gate 05C fixture creates only actors, reusable configuration and the
owning Portfolio.  Every Idea, BA, Proposal, Strategic Gate decision, creation
request and Project below is produced by its normal public lifecycle.  These
tests prove compact B/C and the A upstream route, not a single A0-A31 execution.
"""

import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from tests.test_business_analysis_gate07a_ba import _complete_payload as business_analysis_payload
from tests.test_gate07m_fid_e2e import _project_14_hash
from tests.test_idea_demand_gate07a import _action as idea_action
from tests.test_project_proposal_gate07b import _complete_payload as proposal_payload
from tests.test_project_workspace_initialization import GateC
from tests.test_project_workspace_initialization import gate as _initialization_gate
from tests.test_strategic_gate_gate07c import _create_decision, _decision_action, _proposal_action

from app.database.session import SessionLocal, engine
from app.domain.models import EnterpriseWorkspace, SecurityAccessAssignment, SecurityRole, UserAccount
from app.modules.investment_decision.models import InvestmentDecision
from app.modules.portfolio_planning.models import PortfolioProjectMembership

route_gate = _initialization_gate


def _command(gate: GateC, root: str, item: dict, action: str, actor: str, body=None) -> dict:
    response = gate.client.post(
        f"/api/v1/{root}/{item['id']}/{action}",
        headers={**gate.headers[actor], "If-Match": f'"{item["revision_version"]}"'},
        json=body,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _decision_count() -> int:
    with SessionLocal() as db:
        return int(db.scalar(select(func.count()).select_from(InvestmentDecision)) or 0)


def _protected_hash() -> str | None:
    with SessionLocal() as db:
        return _project_14_hash(db)


def _evidence(case: str, data: dict) -> None:
    directory = os.getenv("STRATEGIC_FINAL_UAT_ROUTES_EVIDENCE_DIR", "").strip()
    if directory:
        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        (target / f"scenario-route-{case}.json").write_text(
            json.dumps({"case": case, "status": "PASS", "database_dialect": engine.dialect.name, **data}, indent=2),
            encoding="utf-8",
        )


def _materialize(gate: GateC, request: dict, owner: str) -> dict:
    request = _command(gate, "project-creation-requests", request, "submit", owner)
    assert request["state"] == "submitted"
    request = _command(gate, "project-creation-requests", request, "start-review", "reviewer")
    request = _command(gate, "project-creation-requests", request, "approve", "approver")
    assert request["state"] == "approved"
    response = gate.client.post(
        f"/api/v1/project-creation-requests/{request['id']}/materialize",
        headers=gate.headers["materializer"],
    )
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize(
    ("model", "source", "adapter", "source_snapshot"),
    [
        (
            "CONTRACTOR_DELIVERY",
            "CONTRACT_AWARD",
            "from-contract",
            {
                "client": "Capital infrastructure owner",
                "contract_number": "UAT-CONTRACT",
                "contractual_scope": "Engineering delivery for copper processing expansion",
                "contract_value": "4500000.00",
                "mobilization_authorized": True,
            },
        ),
        (
            "DIRECT_INTERNAL",
            "DIRECT_AUTHORIZATION",
            "direct",
            {
                "authorization_reference": "UAT-DIRECT",
                "sponsor": "Internal Project Sponsor",
                "business_purpose": "Improve internal engineering information quality",
                "authorization_approved": True,
            },
        ),
    ],
)
def test_compact_governance_source_to_independent_activation(
    route_gate: GateC, model: str, source: str, adapter: str, source_snapshot: dict
) -> None:
    gate = route_gate
    protected_before = _protected_hash()
    fid_before = _decision_count()
    reference = f"UAT-{model}-{uuid4().hex[:10]}"
    source_snapshot = {**source_snapshot}
    key = "contract_number" if model == "CONTRACTOR_DELIVERY" else "authorization_reference"
    source_snapshot[key] = reference
    payload = {
        "parent_workspace_id": gate.parent_id,
        "project_template_config_id": gate.template_id,
        "project_name": f"Final UAT {model} {uuid4().hex[:8]}",
        "description": "Disposable explicit governance route; no operational execution",
        "project_manager_user_id": gate.manager_id,
        "planned_start": "2027-01-01",
        "planned_finish": "2027-12-31",
        "currency_code": "COP",
        "estimated_budget": "4500000.00",
        "country": "CO",
        "strategic_objective_codes": [],
        "governance_model": model,
        "source_context_type": source,
        "source_external_key": reference,
        "idempotency_key": reference,
        "source_snapshot": source_snapshot,
    }
    preview = gate.client.post(
        f"/api/v1/project-creation/{adapter}/preview", headers=gate.headers["requestor"], json=payload
    )
    assert preview.status_code == 200, preview.text
    effective = preview.json()["effective_policy"]
    assert preview.json()["persisted"] is False
    for flag in ("portfolio_required", "fel_required", "pdri_required", "fid_required_for_creation"):
        assert effective[flag] is False
    assert preview.json()["blockers"] == []

    created = gate.client.post(f"/api/v1/project-creation/{adapter}", headers=gate.headers["requestor"], json=payload)
    assert created.status_code == 201, created.text
    request = created.json()
    assert request["governance_model"] == model and request["source_context_type"] == source
    assert request["source_hash"] and request["creation_policy_hash"]
    replay = gate.client.post(f"/api/v1/project-creation/{adapter}", headers=gate.headers["requestor"], json=payload)
    assert replay.status_code == 201 and replay.json()["id"] == request["id"]
    materialized = _materialize(gate, request, "requestor")
    workspace_id = materialized["materialized_workspace_id"]
    with SessionLocal() as db:
        workspace = db.get(EnterpriseWorkspace, workspace_id)
        assert workspace.workspace_type_code == "project" and workspace.status == "pending"
        identity = (workspace.id, workspace.code, workspace.external_key, workspace.record_code)
        assert workspace.defaults_json["_project"]["governance_model"] == model
        assert workspace.defaults_json["_project"]["source_hash"] == request["source_hash"]

    # Activation is a separate controlled action, not a side effect of creation.
    premature = gate.client.post(
        f"/api/v1/project-workspaces/{workspace_id}/activate",
        headers={**gate.headers["activator"], "If-Match": '"1"'},
    )
    assert premature.status_code == 409
    initialization = gate.client.post(
        f"/api/v1/project-workspaces/{workspace_id}/initialization/start",
        headers={**gate.headers["initializer"], "If-Match": '"1"'},
    )
    assert initialization.status_code == 200, initialization.text
    ready = initialization.json()
    assert ready["state"] == "READY_FOR_ACTIVATION", ready
    activated = gate.client.post(
        f"/api/v1/project-workspaces/{workspace_id}/activate",
        headers={**gate.headers["activator"], "If-Match": f'"{ready["revision_version"]}"'},
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["state"] == "ACTIVATED"
    with SessionLocal() as db:
        workspace = db.get(EnterpriseWorkspace, workspace_id)
        assert workspace.status == "active"
        assert (workspace.id, workspace.code, workspace.external_key, workspace.record_code) == identity
        assert not db.scalar(
            select(PortfolioProjectMembership.id).where(PortfolioProjectMembership.project_workspace_id == workspace_id)
        )
    assert _decision_count() == fid_before, "Compact routes must not require or manufacture FID"
    assert _protected_hash() == protected_before
    _evidence(
        model,
        {
            "governance_model": model,
            "source_context_type": source,
            "request_id": request["id"],
            "source_hash": request["source_hash"],
            "creation_policy_hash": request["creation_policy_hash"],
            "project_identity": identity,
            "initialization_state": ready["state"],
            "activation_state": activated.json()["state"],
            "fid_count_before_after": [fid_before, _decision_count()],
            "project14_hash_before_after": [protected_before, _protected_hash()],
            "proof_boundary": "Real HTTP compact route through independent activation; no operational delivery",
        },
    )


def _grant_upstream_review_roles(gate: GateC) -> None:
    # Permission/configuration setup only; never a transaction-state shortcut.
    for path in ("business-analyses/options", "strategic-gate-decisions/options"):
        response = gate.client.get(f"/api/v1/{path}", headers=gate.headers["admin"])
        assert response.status_code == 200, response.text
    with SessionLocal() as db:
        admin = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
        for actor, code in (("reviewer", "business_analysis_reviewer"), ("approver", "gate_decision_maker")):
            role = db.scalar(
                select(SecurityRole).where(SecurityRole.tenant_id == gate.tenant_id, SecurityRole.code == code)
            )
            assert role is not None
            db.add(
                SecurityAccessAssignment(
                    tenant_id=gate.tenant_id,
                    subject_type="user",
                    user_id=gate.actor_ids[actor],
                    role_id=role.id,
                    scope_type="organization",
                    status="active",
                    granted_by_user_id=admin.id,
                )
            )
        db.commit()


def test_capital_owner_idea_business_analysis_proposal_gate_to_pending_project(route_gate: GateC) -> None:
    gate = route_gate
    protected_before = _protected_hash()
    fid_before = _decision_count()
    _grant_upstream_review_roles(gate)
    headers = gate.headers["admin"]
    options = gate.client.get("/api/v1/ideas/options", headers=headers).json()
    created = gate.client.post(
        "/api/v1/ideas",
        headers=headers,
        json={
            "title": f"Copper Processing Expansion {uuid4().hex[:8]}",
            "description": "Governed copper-processing capacity investment; isolated final strategic UAT.",
            "idea_type": options["idea_types"][0]["code"],
            "category": options["categories"][0]["code"],
            "expected_benefit": "Increase processing capacity while maintaining controlled lifecycle exposure.",
            "estimated_value": "4500000.00",
            "currency_code": "COP",
            "owning_workspace_id": gate.parent_id,
            "target_portfolio_workspace_id": gate.parent_id,
            "strategic_objective_codes": [gate.objective_code],
            "attachment_refs": [{"document_id": "FINAL-UAT-OPPORTUNITY"}],
        },
    )
    assert created.status_code == 201, created.text
    idea = idea_action(gate.client, headers, created.json(), "submit")
    idea = idea_action(
        gate.client,
        headers,
        idea,
        "screen",
        {"checklist": {item["code"]: True for item in options["screening_checklist"]}, "notes": "Reviewed"},
    )
    idea = idea_action(gate.client, headers, idea, "route", {"route_code": "default", "notes": "Capital route"})
    with SessionLocal() as db:
        admin_id = db.scalar(select(UserAccount.id).where(UserAccount.email == "admin@demo.local"))
    idea = idea_action(gate.client, headers, idea, "assign-owner", {"owner_user_id": admin_id})
    idea = idea_action(gate.client, headers, idea, "evaluation/start")
    matrix = next(
        item
        for item in gate.client.get("/api/v1/ideas/admin/configurations/list", headers=headers).json()
        if item["kind"] == "idea_evaluation_matrix" and item["status"] == "published"
    )
    idea = idea_action(
        gate.client,
        headers,
        idea,
        "evaluation/complete",
        {
            "ratings": [
                {"criterion_code": item["code"], "rating": 4, "comment": "Governed UAT source"}
                for item in matrix["content_json"]["criteria"]
            ],
            "comments": "Ready for independent options analysis",
        },
    )
    idea = idea_action(gate.client, headers, idea, "accept", {"reason": "Proceed with governed Business Analysis"})
    assert idea["state"] == "ACCEPTED" and idea["accepted_evaluation_id"]
    readiness = gate.client.get(f"/api/v1/ideas/{idea['id']}/proposal-readiness", headers=headers).json()
    assert readiness["status"] == "READY_FOR_BUSINESS_ANALYSIS"

    options = gate.client.get("/api/v1/business-analyses/options", headers=headers).json()
    response = gate.client.post(
        "/api/v1/business-analyses",
        headers={**headers, "Idempotency-Key": f"final-uat-ba-{uuid4()}"},
        json={"source_idea_id": idea["id"]},
    )
    assert response.status_code == 201, response.text
    analysis = response.json()
    updated = gate.client.put(
        f"/api/v1/business-analyses/{analysis['id']}",
        headers={**headers, "If-Match": f'"{analysis["revision_version"]}"'},
        json=business_analysis_payload(options, gate.objective_code),
    )
    assert updated.status_code == 200, updated.text
    analysis = _command(gate, "business-analyses", updated.json(), "submit", "admin")
    analysis = _command(gate, "business-analyses", analysis, "start-review", "reviewer")
    analysis = _command(gate, "business-analyses", analysis, "complete", "reviewer")
    assert analysis["status"] == "COMPLETED" and analysis["completion_hash"]
    readiness = gate.client.get(f"/api/v1/ideas/{idea['id']}/proposal-readiness", headers=headers).json()
    assert readiness["status"] == "READY_FOR_PROJECT_PROPOSAL" and readiness["can_create_project_proposal"]

    response = gate.client.post("/api/v1/project-proposals", headers=headers, json={"source_idea_id": idea["id"]})
    assert response.status_code == 201, response.text
    proposal = response.json()
    response = gate.client.put(
        f"/api/v1/project-proposals/{proposal['id']}",
        headers={**headers, "If-Match": f'"{proposal["revision_version"]}"'},
        json=proposal_payload(proposal),
    )
    assert response.status_code == 200, response.text
    proposal = response.json()
    for action in ("submit", "start-review", "start-evaluation"):
        proposal = _proposal_action(gate.client, headers, proposal, action)
    matrix = next(
        item
        for item in gate.client.get("/api/v1/project-proposals/admin/configurations/list", headers=headers).json()
        if item["kind"] == "project_proposal_evaluation_matrix" and item["status"] == "published"
    )
    proposal = _proposal_action(
        gate.client,
        headers,
        proposal,
        "complete-evaluation",
        {
            "ratings": [
                {"criterion_code": item["code"], "rating": 4, "comment": "Final UAT source"}
                for item in matrix["content_json"]["criteria"]
            ],
            "comments": "Ready for governed Strategic Gate",
        },
    )
    proposal = _proposal_action(gate.client, headers, proposal, "mark-gate-ready")
    assert proposal["status"] == "READY_FOR_STRATEGIC_GATE"
    decision = _create_decision(gate.client, headers, proposal)
    response = gate.client.put(
        f"/api/v1/strategic-gate-decisions/{decision['id']}",
        headers={**headers, "If-Match": f'"{decision["revision_version"]}"'},
        json={
            "decision_reason": "Authorize portfolio and definition planning, not investment execution.",
            "decision_comments": "Final UAT upstream route",
            "decision_maker_user_id": gate.actor_ids["approver"],
            "conditions": [],
            "evidence_refs": [{"reference": "FINAL-UAT-STRATEGIC-GATE"}],
            "committee": None,
        },
    )
    assert response.status_code == 200, response.text
    decision = _decision_action(gate.client, headers, response.json(), "submit")
    decision = _decision_action(gate.client, headers, decision, "start-review")
    decision = _decision_action(
        gate.client,
        gate.headers["approver"],
        decision,
        "decide",
        {"outcome": "APPROVE", "reason": "Portfolio Intake only; no FID or automatic activation", "conditions": []},
    )
    assert decision["state"] == "DECIDED" and decision["outcome"] == "APPROVE"
    response = gate.client.post(
        "/api/v1/strategic-project-planning/preview",
        headers=headers,
        json={"strategic_gate_decision_id": decision["id"]},
    )
    assert response.status_code == 200, response.text
    preview = response.json()
    creation_options = gate.client.get(
        "/api/v1/project-creation-requests/options",
        headers=headers,
        params={"parent_workspace_id": gate.parent_id},
    )
    assert creation_options.status_code == 200, creation_options.text
    project_type = creation_options.json()["classifications"]["project-type"][0]["code"]
    response = gate.client.post(
        "/api/v1/strategic-project-planning",
        headers=headers,
        json={
            "strategic_gate_decision_id": decision["id"],
            "project_parent_workspace_id": gate.parent_id,
            "project_template_config_id": gate.template_id,
            "project_manager_user_id": gate.manager_id,
            "project_type": project_type,
            "expected_decision_hash": preview["source_decision_hash"],
            "expected_readiness_hash": preview["source_readiness_hash"],
        },
    )
    assert response.status_code == 201, response.text
    request = response.json()["project_creation_request"]
    assert request["governance_model"] == "CAPITAL_OWNER"
    materialized = _materialize(gate, request, "admin")
    project_id = materialized["materialized_workspace_id"]
    with SessionLocal() as db:
        project = db.get(EnterpriseWorkspace, project_id)
        assert project.workspace_type_code == "project" and project.status == "pending"
        assert project.defaults_json["_project"]["governance_model"] == "CAPITAL_OWNER"
        membership = db.scalar(
            select(PortfolioProjectMembership).where(
                PortfolioProjectMembership.project_workspace_id == project_id,
                PortfolioProjectMembership.portfolio_workspace_id == gate.parent_id,
                PortfolioProjectMembership.status == "ACTIVE",
            )
        )
        assert membership is not None and membership.membership_source == "STRATEGIC_INTAKE"
    final = gate.client.get(f"/api/v1/strategic-project-planning/{decision['id']}", headers=headers)
    assert final.status_code == 200, final.text
    assert final.json()["can_enter_portfolio_evaluation"] and final.json()["can_enter_project_definition"]
    assert _decision_count() == fid_before, "Strategic Gate approval is not Gate07K/FID"
    assert _protected_hash() == protected_before
    _evidence(
        "CAPITAL_OWNER_UPSTREAM",
        {
            "idea_id": idea["id"],
            "accepted_evaluation_id": idea["accepted_evaluation_id"],
            "business_analysis_id": analysis["id"],
            "business_analysis_completion_hash": analysis["completion_hash"],
            "proposal_id": proposal["id"],
            "strategic_gate_id": decision["id"],
            "strategic_gate_hash": decision["decision_hash"],
            "request_id": request["id"],
            "project_workspace_id": project_id,
            "project_type": project_type,
            "project_status": "pending",
            "membership_source": "STRATEGIC_INTAKE",
            "fid_count_before_after": [fid_before, _decision_count()],
            "project14_hash_before_after": [protected_before, _protected_hash()],
            "proof_boundary": "Real HTTP Idea→evaluation→BA→Proposal→Strategic Gate→Project/membership only; not A0-A31",
        },
    )
