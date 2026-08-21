"""Gate 07D acceptance tests for Portfolio Planning stage entry."""

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import func, inspect, select
from tests.test_project_proposal_gate07b import _accepted_idea, _complete_payload, _headers
from tests.test_strategic_gate_gate07c import (
    _create_decision,
    _decision_action,
    _proposal_action,
)

from app.database.session import SessionLocal, engine
from app.domain.models import EnterpriseWorkspace, SecurityAccessAssignment, SecurityRole, UserAccount
from app.main import app
from app.modules.enterprise_structure.record_codes import next_record_code
from app.modules.idea_demand.models import Idea
from app.modules.portfolio_planning.models import PortfolioProjectMembership
from app.modules.project_creation.models import ProjectCreationRequest
from app.modules.project_creation.service import ProjectCreationService


def _ensure_published_project_template(client: TestClient, headers: dict[str, str]) -> None:
    configured = client.get(
        "/api/v1/admin-configuration/enterprise-structure/project-workspace",
        headers=headers,
    )
    assert configured.status_code == 200, configured.text
    if any(item["status"] == "published" for item in configured.json()["templates"]):
        return
    created = client.post(
        "/api/v1/admin-configuration/enterprise-structure/project-templates",
        headers=headers,
        json={
            "code": f"gate07d-{uuid4().hex[:8]}",
            "name": "Gate 07D Portfolio Planning",
            "description": "Acceptance template for strategic planning stage entry",
            "applicable_parent_types": ["portfolio", "program"],
            "default_classifications": [],
            "enabled_modules": [],
            "default_role_codes": [],
            "default_group_codes": [],
            "numbering_rule_code": "project-workspace",
            "default_attributes": {"currency": "COP"},
            "creation_policy_code": "project-creation",
        },
    )
    assert created.status_code == 201, created.text
    template = created.json()
    validation = client.post(
        f"/api/v1/admin-configuration/enterprise-structure/project-templates/{template['id']}/validate",
        headers=headers,
    )
    assert validation.status_code == 200, validation.text
    published = client.post(
        f"/api/v1/admin-configuration/enterprise-structure/project-templates/{template['id']}/publish",
        headers=headers,
        json={"expected_hash": validation.json()["content_hash"]},
    )
    assert published.status_code == 200, published.text


def _target_portfolio() -> tuple[int, int, int]:
    with SessionLocal() as db:
        admin = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
        assert admin is not None
        portfolio = db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.tenant_id == admin.tenant_id,
                EnterpriseWorkspace.workspace_type_code == "portfolio",
                EnterpriseWorkspace.status == "active",
            )
        )
        if portfolio is None:
            parent = db.scalar(
                select(EnterpriseWorkspace)
                .where(
                    EnterpriseWorkspace.tenant_id == admin.tenant_id,
                    EnterpriseWorkspace.workspace_type_code == "enterprise",
                    EnterpriseWorkspace.status == "active",
                )
                .order_by(EnterpriseWorkspace.id)
            )
            assert parent is not None
            sibling_codes = list(
                db.scalars(
                    select(EnterpriseWorkspace.record_code).where(
                        EnterpriseWorkspace.tenant_id == admin.tenant_id,
                        EnterpriseWorkspace.parent_id == parent.id,
                    )
                ).all()
            )
            portfolio = EnterpriseWorkspace(
                tenant_id=admin.tenant_id,
                parent_id=parent.id,
                workspace_type_code="portfolio",
                code=f"G07D-PF-{uuid4().hex[:6]}",
                external_key=f"G07D-PF-{uuid4()}",
                record_code=next_record_code(parent.record_code, sibling_codes),
                name="Gate 07D Target Portfolio",
                status="active",
                defaults_json={},
                sort_order=98,
                version=1,
                created_by_user_id=admin.id,
            )
            db.add(portfolio)
            db.flush()
        other = db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.tenant_id == admin.tenant_id,
                EnterpriseWorkspace.workspace_type_code == "portfolio",
                EnterpriseWorkspace.status == "active",
                EnterpriseWorkspace.id != portfolio.id,
            )
        )
        if other is None:
            sibling_codes = list(
                db.scalars(
                    select(EnterpriseWorkspace.record_code).where(
                        EnterpriseWorkspace.tenant_id == admin.tenant_id,
                        EnterpriseWorkspace.parent_id == portfolio.parent_id,
                    )
                ).all()
            )
            parent_record = portfolio.record_code.rsplit(".", 1)[0]
            other = EnterpriseWorkspace(
                tenant_id=admin.tenant_id,
                parent_id=portfolio.parent_id,
                workspace_type_code="portfolio",
                code=f"G07D-PF-{uuid4().hex[:6]}",
                external_key=f"G07D-PF-{uuid4()}",
                record_code=next_record_code(parent_record, sibling_codes),
                name="Gate 07D Secondary Portfolio",
                status="active",
                defaults_json={},
                sort_order=99,
                version=1,
                created_by_user_id=admin.id,
            )
            db.add(other)
            db.commit()
            db.refresh(other)
        return admin.tenant_id, portfolio.id, other.id


def _gate07d_approver(client: TestClient) -> tuple[int, dict[str, str]]:
    with SessionLocal() as db:
        admin = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
        approver = db.scalar(select(UserAccount).where(UserAccount.email == "ana.control@demo.local"))
        assert admin is not None and approver is not None
        role = db.scalar(
            select(SecurityRole).where(
                SecurityRole.tenant_id == admin.tenant_id,
                SecurityRole.code == "organization_admin",
                SecurityRole.status == "active",
            )
        )
        assert role is not None
        assignment = db.scalar(
            select(SecurityAccessAssignment).where(
                SecurityAccessAssignment.tenant_id == admin.tenant_id,
                SecurityAccessAssignment.user_id == approver.id,
                SecurityAccessAssignment.role_id == role.id,
                SecurityAccessAssignment.scope_type == "organization",
                SecurityAccessAssignment.status == "active",
            )
        )
        if assignment is None:
            db.add(
                SecurityAccessAssignment(
                    tenant_id=admin.tenant_id,
                    subject_type="user",
                    user_id=approver.id,
                    role_id=role.id,
                    scope_type="organization",
                    status="active",
                    granted_by_user_id=admin.id,
                )
            )
            db.commit()
        approver_id = approver.id
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "ana.control@demo.local", "password": "1234", "tenant_slug": "demo-energy"},
    )
    assert login.status_code == 200, login.text
    return approver_id, {"Authorization": f"Bearer {login.json()['access_token']}"}


def _approved_decision(client: TestClient, headers: dict[str, str]) -> dict:
    _ensure_published_project_template(client, headers)
    _tenant_id, portfolio_id, _other = _target_portfolio()
    idea_id, _snapshot = _accepted_idea()
    with SessionLocal() as db:
        idea = db.get(Idea, idea_id)
        assert idea is not None
        idea.target_portfolio_workspace_id = portfolio_id
        db.commit()
    created = client.post(
        "/api/v1/project-proposals",
        headers=headers,
        json={"source_idea_id": idea_id},
    )
    assert created.status_code == 201, created.text
    proposal = created.json()
    updated = client.put(
        f"/api/v1/project-proposals/{proposal['id']}",
        headers={**headers, "If-Match": f'"{proposal["revision_version"]}"'},
        json=_complete_payload(proposal),
    )
    assert updated.status_code == 200, updated.text
    proposal = _proposal_action(client, headers, updated.json(), "submit")
    proposal = _proposal_action(client, headers, proposal, "start-review")
    proposal = _proposal_action(client, headers, proposal, "start-evaluation")
    configurations = client.get(
        "/api/v1/project-proposals/admin/configurations/list",
        headers=headers,
    ).json()
    matrix = next(item for item in configurations if item["kind"] == "project_proposal_evaluation_matrix")
    ratings = [
        {"criterion_code": item["code"], "rating": 4, "comment": "Gate 07D source"}
        for item in matrix["content_json"]["criteria"]
    ]
    proposal = _proposal_action(
        client,
        headers,
        proposal,
        "complete-evaluation",
        {"ratings": ratings, "comments": "Ready for Gate 07D source"},
    )
    proposal = _proposal_action(client, headers, proposal, "mark-gate-ready")
    approver_id, approver_headers = _gate07d_approver(client)
    decision = _create_decision(client, headers, proposal)
    updated_decision = client.put(
        f"/api/v1/strategic-gate-decisions/{decision['id']}",
        headers={**headers, "If-Match": f'"{decision["revision_version"]}"'},
        json={
            "decision_reason": "Strategic case reviewed and ready for formal decision.",
            "decision_comments": "Prepared under Gate 07C for Gate 07D.",
            "decision_maker_user_id": approver_id,
            "conditions": [],
            "evidence_refs": [{"reference": "SGD-EVIDENCE-GATE07D"}],
            "committee": None,
        },
    )
    assert updated_decision.status_code == 200, updated_decision.text
    decision = _decision_action(client, headers, updated_decision.json(), "submit")
    decision = _decision_action(client, headers, decision, "start-review")
    return _decision_action(
        client,
        approver_headers,
        decision,
        "decide",
        {
            "outcome": "APPROVE",
            "reason": "Authorize Portfolio Planning and Project Definition only.",
            "conditions": [{"code": "NO_EXECUTION_BEFORE_FID"}],
            "comments": "No FID, initialization or activation.",
        },
    )


def test_gate07d_preview_reuses_project_creation_without_consuming_numbers() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        decision = _approved_decision(client, headers)
        before = client.get("/api/v1/project-creation-requests", headers=headers).json()
        preview = client.post(
            "/api/v1/strategic-project-planning/preview",
            headers=headers,
            json={"strategic_gate_decision_id": decision["id"]},
        )
        assert preview.status_code == 200, preview.text
        payload = preview.json()
        assert payload["persisted"] is False
        assert payload["source_decision_hash"] == decision["decision_hash"]
        assert payload["target_portfolio"]["workspace_type_code"] == "portfolio"
        assert payload["project_number_preview"]
        assert payload["creation_policy"]["project_creation_process"] == "GATE_05B"
        assert payload["creation_policy"]["activation"] is False
        assert client.get("/api/v1/project-creation-requests", headers=headers).json() == before
        assert "portfolio_candidates" not in inspect(engine).get_table_names()


def test_gate07d_full_lifecycle_creates_one_pending_project_and_target_membership() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        decision = _approved_decision(client, headers)
        preview = client.post(
            "/api/v1/strategic-project-planning/preview",
            headers=headers,
            json={"strategic_gate_decision_id": decision["id"]},
        ).json()
        project_options = client.get(
            "/api/v1/project-creation-requests/options",
            headers=headers,
            params={"parent_workspace_id": preview["default_project_parent"]["id"]},
        ).json()
        project_types = project_options["classifications"]["project-type"]
        assert project_types
        create_payload = {
            "strategic_gate_decision_id": decision["id"],
            "project_parent_workspace_id": preview["default_project_parent"]["id"],
            "project_template_config_id": preview["template_options"][0]["id"],
            "project_manager_user_id": preview["project_manager_options"][0]["id"],
            "project_type": project_types[0]["code"],
            "expected_decision_hash": preview["source_decision_hash"],
            "expected_readiness_hash": preview["source_readiness_hash"],
        }
        stale = client.post(
            "/api/v1/strategic-project-planning",
            headers=headers,
            json={**create_payload, "expected_decision_hash": "0" * 64},
        )
        assert stale.status_code == 412
        stale_readiness = client.post(
            "/api/v1/strategic-project-planning",
            headers=headers,
            json={**create_payload, "expected_readiness_hash": "0" * 64},
        )
        assert stale_readiness.status_code == 412
        created = client.post("/api/v1/strategic-project-planning", headers=headers, json=create_payload)
        assert created.status_code == 201, created.text
        entry = created.json()
        request = entry["project_creation_request"]
        assert request["source_context_type"] == "STRATEGIC_GATE_DECISION"
        assert request["strategic_gate_decision_id"] == decision["id"]
        duplicate = client.post("/api/v1/strategic-project-planning", headers=headers, json=create_payload)
        assert duplicate.status_code == 201
        assert duplicate.json()["project_creation_request"]["id"] == request["id"]

        with SessionLocal() as db:
            admin = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
            approver = db.scalar(
                select(UserAccount).where(UserAccount.id != admin.id, UserAccount.tenant_id == admin.tenant_id)
            )
            assert admin is not None and approver is not None
            service = ProjectCreationService(db, admin.tenant_id, admin.id)
            submitted = service.submit(request["id"], request["revision_version"])
            reviewed = service.start_review(request["id"], submitted.revision_version)
            approved = ProjectCreationService(db, admin.tenant_id, approver.id).approve(
                request["id"], reviewed.revision_version
            )
            assert approved.state == "approved"
            materialized = service.materialize(request["id"])
            assert materialized.portfolio_planning_status == "READY_FOR_PORTFOLIO_PLANNING"
            project_id = materialized.materialized_workspace_id

        final = client.get(f"/api/v1/strategic-project-planning/{decision['id']}", headers=headers)
        assert final.status_code == 200, final.text
        payload = final.json()
        assert payload["status"] == "READY_FOR_PORTFOLIO_PLANNING"
        assert payload["can_enter_portfolio_evaluation"] is True
        assert payload["can_enter_project_definition"] is True
        assert payload["project_workspace"]["status"] == "pending"
        assert len(payload["portfolio_memberships"]) == 1
        assert payload["portfolio_memberships"][0]["membership_source"] == "STRATEGIC_INTAKE"
        assert payload["portfolio_memberships"][0]["is_target_portfolio"] is True
        assert payload["planning_entry_hash"]
        with SessionLocal() as db:
            project = db.get(EnterpriseWorkspace, project_id)
            request_row = db.get(ProjectCreationRequest, request["id"])
            assert project is not None and request_row is not None
            assert project.parent_id == request_row.parent_workspace_id
            expected_parent_id = request_row.parent_workspace_id
            assert project.status == "pending"
            assert (
                db.scalar(
                    select(func.count(PortfolioProjectMembership.id)).where(
                        PortfolioProjectMembership.project_workspace_id == project_id,
                        PortfolioProjectMembership.status == "ACTIVE",
                    )
                )
                == 1
            )

        readiness = client.get(
            f"/api/v1/projects/{project_id}/project-definition-readiness",
            headers=headers,
        )
        assert readiness.status_code == 200
        assert readiness.json()["status"] == "READY"
        context = client.get(f"/api/v1/workspaces/{project_id}/context", headers=headers)
        assert context.status_code == 200, context.text
        navigator = {item["code"] for item in context.json()["navigator"]}
        assert "strategic-context" in navigator
        assert "portfolio-planning-readiness" in navigator
        assert "scope" not in navigator

        _tenant_id, _target, other_portfolio = _target_portfolio()
        project_version = payload["project_workspace"]["version"]
        second = client.post(
            f"/api/v1/projects/{project_id}/portfolio-memberships",
            headers={**headers, "If-Match": f'"{project_version}"'},
            json={"portfolio_workspace_id": other_portfolio, "membership_source": "MANUAL"},
        )
        assert second.status_code == 200, second.text
        memberships = client.get(f"/api/v1/projects/{project_id}/portfolio-memberships", headers=headers).json()
        assert len([item for item in memberships if item["status"] == "ACTIVE"]) == 2
        with SessionLocal() as db:
            assert db.get(EnterpriseWorkspace, project_id).parent_id == expected_parent_id
