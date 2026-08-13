"""Gate 05B acceptance tests for the governed Project Creation Process."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.security import hash_password
from app.database.session import SessionLocal, engine
from app.domain.models import (
    AdminConfiguration,
    AdminNumberSequence,
    AuthCredential,
    EnterpriseWorkspace,
    Project,
    SecurityAccessAssignment,
    SecurityEvent,
    SecurityRole,
    UserAccount,
    WorkspaceModuleSetting,
)
from app.main import app
from app.modules.enterprise_structure.models import (
    EnterpriseCoreRelease,
    EnterpriseStrategicObjective,
    EnterpriseWorkspaceClassification,
)
from app.modules.enterprise_structure.permissions import ensure_enterprise_permissions
from app.modules.enterprise_structure.record_codes import next_record_code
from app.modules.project_creation.models import ProjectCreationRequest
from app.modules.project_creation.service import ProjectCreationService

ROOT = "/api/v1/project-creation-requests"
ADMIN_ROOT = "/api/v1/admin-configuration/enterprise-structure"


@dataclass
class Gate:
    client: TestClient
    headers: dict[str, dict[str, str]]
    parent_id: int
    other_parent_id: int
    template_id: int
    draft_template_id: int
    manager_id: int
    objective_code: str
    tenant_id: int
    actor_ids: dict[str, int]


def _login(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "1234", "tenant_slug": "demo-energy"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _template_payload(code: str) -> dict:
    return {
        "code": code,
        "name": f"Gate 05B {code}",
        "description": "Isolated Gate 05B acceptance template",
        "applicable_parent_types": ["portfolio", "program"],
        "default_classifications": [],
        "enabled_modules": ["scope-manager"],
        "default_role_codes": [],
        "default_group_codes": [],
        "numbering_rule_code": "project-workspace",
        "default_attributes": {"currency": "COP"},
        "creation_policy_code": "project-creation",
    }


def _workspace(db, tenant_id: int, actor_id: int, code: str, name: str, kind: str, parent) -> EnterpriseWorkspace:
    sibling_codes = list(
        db.scalars(
            select(EnterpriseWorkspace.record_code).where(
                EnterpriseWorkspace.tenant_id == tenant_id,
                EnterpriseWorkspace.parent_id == parent.id,
            )
        ).all()
    )
    row = EnterpriseWorkspace(
        tenant_id=tenant_id,
        parent_id=parent.id,
        workspace_type_code=kind,
        code=code,
        external_key=f"GATE05B-{uuid4()}",
        record_code=next_record_code(parent.record_code, sibling_codes),
        name=name,
        status="active",
        defaults_json={"_enterprise": {"description": "Gate 05B isolated fixture"}},
        sort_order=90,
        version=1,
        created_by_user_id=actor_id,
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture(scope="module")
def gate() -> Gate:
    with TestClient(app) as client:
        admin_headers = _login(client, "admin")
        configured = client.get(f"{ADMIN_ROOT}/project-workspace", headers=admin_headers)
        assert configured.status_code == 200, configured.text
        with SessionLocal() as db:
            admin = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
            module = db.scalar(
                select(AdminConfiguration).where(
                    AdminConfiguration.tenant_id == admin.tenant_id,
                    AdminConfiguration.kind == "module_definition",
                    AdminConfiguration.code == "scope-manager",
                    AdminConfiguration.status == "published",
                )
            )
            if module is None:
                db.add(
                    AdminConfiguration(
                        tenant_id=admin.tenant_id,
                        kind="module_definition",
                        code="scope-manager",
                        name="Scope Manager",
                        description="Gate 05B isolated module definition",
                        status="published",
                        revision=1,
                        version=1,
                        content_json={"mode": "user", "enabled": True},
                        content_hash="5" * 64,
                        created_by_user_id=admin.id,
                    )
                )
                db.commit()
        code = f"G05B-{uuid4().hex[:8]}"
        created_template = client.post(
            f"{ADMIN_ROOT}/project-templates",
            headers=admin_headers,
            json=_template_payload(code),
        )
        assert created_template.status_code == 201, created_template.text
        template = created_template.json()
        validation = client.post(
            f"{ADMIN_ROOT}/project-templates/{template['id']}/validate",
            headers=admin_headers,
        )
        assert validation.status_code == 200, validation.text
        published = client.post(
            f"{ADMIN_ROOT}/project-templates/{template['id']}/publish",
            headers=admin_headers,
            json={"expected_hash": validation.json()["content_hash"]},
        )
        assert published.status_code == 200, published.text

        actor_ids: dict[str, int] = {}
        emails: dict[str, str] = {}
        with SessionLocal() as db:
            admin = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
            assert admin is not None
            ensure_enterprise_permissions(db, admin.tenant_id, admin.id)
            root = db.scalar(
                select(EnterpriseWorkspace).where(
                    EnterpriseWorkspace.tenant_id == admin.tenant_id,
                    EnterpriseWorkspace.parent_id.is_(None),
                )
            )
            assert root is not None
            business = _workspace(
                db,
                admin.tenant_id,
                admin.id,
                f"G05B-BU-{uuid4().hex[:6]}",
                "Gate 05B Business Unit",
                "business-unit",
                root,
            )
            portfolio = _workspace(
                db,
                admin.tenant_id,
                admin.id,
                f"G05B-PF-{uuid4().hex[:6]}",
                "Gate 05B Portfolio",
                "portfolio",
                business,
            )
            program = _workspace(
                db,
                admin.tenant_id,
                admin.id,
                f"G05B-PG-{uuid4().hex[:6]}",
                "Gate 05B Program",
                "program",
                portfolio,
            )
            objective = db.scalar(
                select(EnterpriseStrategicObjective).where(
                    EnterpriseStrategicObjective.tenant_id == admin.tenant_id,
                    EnterpriseStrategicObjective.active.is_(True),
                )
            )
            if objective is None:
                objective = EnterpriseStrategicObjective(
                    tenant_id=admin.tenant_id,
                    code="growth",
                    name="Sustainable Growth",
                    strategic_line="Enterprise",
                    priority="high",
                    horizon="2030",
                    responsible_area="PMO",
                    active=True,
                    description="Gate 05B isolated strategic objective",
                    source_release_code="GATE05B-TEST",
                    created_by_user_id=admin.id,
                )
                db.add(objective)
                db.flush()
            for parent in (portfolio, program):
                db.add(
                    EnterpriseWorkspaceClassification(
                        tenant_id=admin.tenant_id,
                        workspace_id=parent.id,
                        category_set_code="strategic-objective",
                        category_item_code=objective.code,
                        created_by_user_id=admin.id,
                    )
                )
            roles = {
                row.code: row
                for row in db.scalars(select(SecurityRole).where(SecurityRole.tenant_id == admin.tenant_id)).all()
            }
            for name, role_code in {
                "requestor": "project_requestor",
                "reviewer": "project_reviewer",
                "approver": "project_approver",
                "materializer": "project_materialization_service",
                "manager": "project_manager",
                "outsider": "project_manager",
            }.items():
                email = f"gate05b-{name}-{uuid4().hex[:6]}@demo.local"
                user = UserAccount(
                    tenant_id=admin.tenant_id,
                    email=email,
                    full_name=f"Gate 05B {name.title()}",
                    status="active",
                )
                db.add(user)
                db.flush()
                actor_ids[name] = user.id
                emails[name] = email
                db.add(
                    AuthCredential(
                        tenant_id=admin.tenant_id,
                        user_id=user.id,
                        provider="local",
                        password_hash=hash_password("1234"),
                        is_active=True,
                    )
                )
                db.add(
                    SecurityAccessAssignment(
                        tenant_id=admin.tenant_id,
                        subject_type="user",
                        user_id=user.id,
                        role_id=roles[role_code].id,
                        scope_type="organization",
                        status="active",
                        granted_by_user_id=admin.id,
                    )
                )
            ProjectCreationService(db, admin.tenant_id, admin.id).ensure_seed()
            db.commit()
            tenant_id = admin.tenant_id
            parent_id = portfolio.id
            other_parent_id = program.id
            objective_code = objective.code
            draft_template_id = next(
                item.id
                for item in db.scalars(
                    select(AdminConfiguration).where(
                        AdminConfiguration.tenant_id == admin.tenant_id,
                        AdminConfiguration.kind == "project_template",
                        AdminConfiguration.status == "draft",
                    )
                ).all()
            )
        headers = {name: _login(client, email) for name, email in emails.items()}
        headers["admin"] = admin_headers
        yield Gate(
            client=client,
            headers=headers,
            parent_id=parent_id,
            other_parent_id=other_parent_id,
            template_id=published.json()["id"],
            draft_template_id=draft_template_id,
            manager_id=actor_ids["manager"],
            objective_code=objective_code,
            tenant_id=tenant_id,
            actor_ids=actor_ids,
        )


def _payload(gate: Gate, name: str | None = None, **overrides) -> dict:
    value = {
        "parent_workspace_id": gate.parent_id,
        "project_template_config_id": gate.template_id,
        "project_name": name or f"Gate 05B Project {uuid4().hex[:8]}",
        "description": "Governed Project Creation Process acceptance request",
        "project_manager_user_id": gate.manager_id,
        "planned_start": "2026-09-01",
        "planned_finish": "2027-08-31",
        "currency_code": "COP",
        "estimated_budget": "1250000.00",
        "country": "CO",
        "strategic_objective_codes": [gate.objective_code],
    }
    value.update(overrides)
    return value


def _create(gate: Gate, **overrides) -> dict:
    response = gate.client.post(ROOT, headers=gate.headers["requestor"], json=_payload(gate, **overrides))
    assert response.status_code == 201, response.text
    return response.json()


def _post_transition(gate: Gate, request: dict, action: str, actor: str, payload: dict | None = None):
    return gate.client.post(
        f"{ROOT}/{request['id']}/{action}",
        headers={**gate.headers[actor], "If-Match": str(request["revision_version"])},
        json=payload,
    )


def _approved(gate: Gate) -> dict:
    request = _create(gate)
    response = _post_transition(gate, request, "submit", "requestor")
    assert response.status_code == 200, response.text
    request = response.json()
    response = _post_transition(gate, request, "start-review", "reviewer")
    assert response.status_code == 200, response.text
    request = response.json()
    response = _post_transition(gate, request, "approve", "approver")
    assert response.status_code == 200, response.text
    return response.json()


def test_01_options_show_only_published_templates(gate: Gate) -> None:
    response = gate.client.get(ROOT + "/options", headers=gate.headers["requestor"])
    assert response.status_code == 200
    ids = {item["id"] for item in response.json()["templates"]}
    assert gate.template_id in ids
    assert gate.draft_template_id not in ids


def test_02_location_picker_uses_eligible_enterprise_nodes(gate: Gate) -> None:
    response = gate.client.get(ROOT + "/options", headers=gate.headers["requestor"])
    locations = response.json()["locations"]
    assert any(item["id"] == gate.parent_id and item["workspace_type_code"] == "portfolio" for item in locations)
    assert all(item["workspace_type_code"] in {"portfolio", "program"} for item in locations)


def test_03_parent_scoped_template_options(gate: Gate) -> None:
    response = gate.client.get(
        ROOT + f"/options?parent_workspace_id={gate.parent_id}",
        headers=gate.headers["requestor"],
    )
    assert response.status_code == 200
    assert any(item["id"] == gate.template_id for item in response.json()["templates"])


def test_04_create_starts_in_draft_with_separate_request_number(gate: Gate) -> None:
    request = _create(gate)
    assert request["state"] == "draft"
    assert request["request_number"].startswith("PCR-")
    assert request["materialized_project_number"] is None


def test_05_draft_template_cannot_be_selected(gate: Gate) -> None:
    response = gate.client.post(
        ROOT,
        headers=gate.headers["requestor"],
        json=_payload(gate, project_template_config_id=gate.draft_template_id),
    )
    assert response.status_code == 422
    assert "NO_PUBLISHED_PROJECT_TEMPLATE" in response.text


def test_06_strategic_objective_is_required(gate: Gate) -> None:
    response = gate.client.post(
        ROOT,
        headers=gate.headers["requestor"],
        json=_payload(gate, strategic_objective_codes=[]),
    )
    assert response.status_code == 422
    assert "STRATEGIC_OBJECTIVE_REQUIRED" in response.text


def test_07_active_project_manager_is_required(gate: Gate) -> None:
    response = gate.client.post(
        ROOT,
        headers=gate.headers["requestor"],
        json=_payload(gate, project_manager_user_id=99999999),
    )
    assert response.status_code == 422
    assert "PROJECT_MANAGER_REQUIRED" in response.text


def test_08_invalid_parent_type_is_blocked(gate: Gate) -> None:
    with SessionLocal() as db:
        invalid = db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.tenant_id == gate.tenant_id,
                EnterpriseWorkspace.workspace_type_code == "business-unit",
            )
        )
    response = gate.client.post(
        ROOT,
        headers=gate.headers["requestor"],
        json=_payload(gate, parent_workspace_id=invalid.id),
    )
    assert response.status_code == 422
    assert "INVALID_PARENT_WORKSPACE_TYPE" in response.text


def test_09_preview_is_non_persistent_and_does_not_consume_project_number(gate: Gate) -> None:
    request = _create(gate)
    with SessionLocal() as db:
        before_workspaces = db.scalar(select(func.count()).select_from(EnterpriseWorkspace))
        before_number = db.scalar(
            select(AdminNumberSequence.next_value).where(
                AdminNumberSequence.tenant_id == gate.tenant_id,
                AdminNumberSequence.rule_code == "project-workspace",
            )
        )
    response = gate.client.post(f"{ROOT}/{request['id']}/preview", headers=gate.headers["requestor"])
    assert response.status_code == 200, response.text
    assert response.json()["persisted"] is False
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(EnterpriseWorkspace)) == before_workspaces
        assert (
            db.scalar(
                select(AdminNumberSequence.next_value).where(
                    AdminNumberSequence.tenant_id == gate.tenant_id,
                    AdminNumberSequence.rule_code == "project-workspace",
                )
            )
            == before_number
        )


def test_10_preview_uses_hierarchical_code_and_numbering_rule(gate: Gate) -> None:
    request = _create(gate)
    response = gate.client.post(f"{ROOT}/{request['id']}/preview", headers=gate.headers["requestor"])
    payload = response.json()
    assert payload["projected_record_code"].startswith(payload["parent_record_code"] + ".")
    assert payload["projected_project_number"].startswith("PYP-PRJ-")


def test_11_my_requests_is_requestor_scoped(gate: Gate) -> None:
    request = _create(gate)
    response = gate.client.get(ROOT, headers=gate.headers["requestor"])
    assert any(item["id"] == request["id"] for item in response.json())


def test_12_actor_without_request_read_permission_is_denied(gate: Gate) -> None:
    response = gate.client.get(ROOT, headers=gate.headers["outsider"])
    assert response.status_code == 403


def test_13_non_owner_cannot_update_request(gate: Gate) -> None:
    request = _create(gate)
    response = gate.client.put(
        f"{ROOT}/{request['id']}",
        headers={**gate.headers["admin"], "If-Match": str(request["revision_version"])},
        json=_payload(gate, name="Unauthorized update"),
    )
    assert response.status_code == 403


def test_14_owner_update_increments_revision(gate: Gate) -> None:
    request = _create(gate)
    response = gate.client.put(
        f"{ROOT}/{request['id']}",
        headers={**gate.headers["requestor"], "If-Match": str(request["revision_version"])},
        json=_payload(gate, name="Updated governed project"),
    )
    assert response.status_code == 200
    assert response.json()["revision_version"] == request["revision_version"] + 1


def test_15_stale_update_returns_409(gate: Gate) -> None:
    request = _create(gate)
    response = gate.client.put(
        f"{ROOT}/{request['id']}",
        headers={**gate.headers["requestor"], "If-Match": "999"},
        json=_payload(gate, name="Stale update"),
    )
    assert response.status_code == 409
    assert "REQUEST_VERSION_CONFLICT" in response.text


def test_16_missing_if_match_is_rejected(gate: Gate) -> None:
    request = _create(gate)
    response = gate.client.post(f"{ROOT}/{request['id']}/submit", headers=gate.headers["requestor"])
    assert response.status_code == 422


def test_17_submit_creates_immutable_snapshot(gate: Gate) -> None:
    request = _create(gate)
    response = _post_transition(gate, request, "submit", "requestor")
    assert response.status_code == 200
    assert response.json()["state"] == "submitted"
    with SessionLocal() as db:
        row = db.get(ProjectCreationRequest, request["id"])
        assert len(row.submission_hash) == 64
        assert row.submission_snapshot_json["request"]["project_name"] == request["project_name"]


def test_18_duplicate_submit_is_invalid(gate: Gate) -> None:
    request = _create(gate)
    request = _post_transition(gate, request, "submit", "requestor").json()
    response = _post_transition(gate, request, "submit", "requestor")
    assert response.status_code == 409


def test_19_draft_can_be_cancelled(gate: Gate) -> None:
    request = _create(gate)
    response = _post_transition(gate, request, "cancel", "requestor")
    assert response.status_code == 200
    assert response.json()["state"] == "cancelled"


def test_20_submitted_request_can_be_cancelled(gate: Gate) -> None:
    request = _create(gate)
    request = _post_transition(gate, request, "submit", "requestor").json()
    response = _post_transition(gate, request, "cancel", "requestor")
    assert response.status_code == 200
    assert response.json()["state"] == "cancelled"


def test_21_reviewer_starts_review(gate: Gate) -> None:
    request = _create(gate)
    request = _post_transition(gate, request, "submit", "requestor").json()
    response = _post_transition(gate, request, "start-review", "reviewer")
    assert response.status_code == 200
    assert response.json()["state"] == "under_review"


def test_22_review_cannot_start_from_draft(gate: Gate) -> None:
    request = _create(gate)
    response = _post_transition(gate, request, "start-review", "reviewer")
    assert response.status_code == 409


def test_23_reviewer_can_return_with_reason(gate: Gate) -> None:
    request = _create(gate)
    request = _post_transition(gate, request, "submit", "requestor").json()
    request = _post_transition(gate, request, "start-review", "reviewer").json()
    response = _post_transition(gate, request, "return", "reviewer", {"reason": "Please clarify scope"})
    assert response.status_code == 200
    assert response.json()["state"] == "returned"
    assert response.json()["decision_reason"] == "Please clarify scope"


def test_24_returned_request_becomes_draft_after_edit(gate: Gate) -> None:
    request = _create(gate)
    request = _post_transition(gate, request, "submit", "requestor").json()
    request = _post_transition(gate, request, "return", "reviewer", {"reason": "Clarify dates"}).json()
    response = gate.client.put(
        f"{ROOT}/{request['id']}",
        headers={**gate.headers["requestor"], "If-Match": str(request["revision_version"])},
        json=_payload(gate, name="Corrected returned request"),
    )
    assert response.status_code == 200
    assert response.json()["state"] == "draft"


def test_25_reviewer_can_reject_under_review(gate: Gate) -> None:
    request = _create(gate)
    request = _post_transition(gate, request, "submit", "requestor").json()
    request = _post_transition(gate, request, "start-review", "reviewer").json()
    response = _post_transition(gate, request, "reject", "reviewer", {"reason": "Not aligned"})
    assert response.status_code == 200
    assert response.json()["state"] == "rejected"


def test_26_requestor_cannot_approve(gate: Gate) -> None:
    request = _create(gate)
    request = _post_transition(gate, request, "submit", "requestor").json()
    request = _post_transition(gate, request, "start-review", "reviewer").json()
    response = _post_transition(gate, request, "approve", "requestor")
    assert response.status_code == 403


def test_27_approver_completes_four_eyes_approval(gate: Gate) -> None:
    request = _approved(gate)
    assert request["state"] == "approved"
    assert request["approved_by_user_id"] == gate.actor_ids["approver"]


def test_28_approval_captures_governance_hash(gate: Gate) -> None:
    request = _approved(gate)
    with SessionLocal() as db:
        row = db.get(ProjectCreationRequest, request["id"])
        assert len(row.approval_hash) == 64


def test_29_review_queue_is_privileged_and_state_filtered(gate: Gate) -> None:
    request = _approved(gate)
    response = gate.client.get(ROOT + "?review_queue=true", headers=gate.headers["reviewer"])
    assert response.status_code == 200
    assert any(item["id"] == request["id"] for item in response.json())


def test_30_materialization_creates_one_pending_project_workspace(gate: Gate) -> None:
    request = _approved(gate)
    response = gate.client.post(f"{ROOT}/{request['id']}/materialize", headers=gate.headers["materializer"])
    assert response.status_code == 200, response.text
    created = response.json()
    assert created["result"] == "CREATED"
    with SessionLocal() as db:
        workspace = db.get(EnterpriseWorkspace, created["materialized_workspace_id"])
        assert workspace.workspace_type_code == "project"
        assert workspace.status == "pending"


def test_31_materialization_is_idempotent(gate: Gate) -> None:
    request = _approved(gate)
    first = gate.client.post(f"{ROOT}/{request['id']}/materialize", headers=gate.headers["materializer"])
    second = gate.client.post(f"{ROOT}/{request['id']}/materialize", headers=gate.headers["materializer"])
    assert first.status_code == second.status_code == 200
    assert second.json()["result"] == "ALREADY_CREATED"
    assert second.json()["mutation_count"] == 0
    assert second.json()["materialized_workspace_id"] == first.json()["materialized_workspace_id"]


def test_32_no_legacy_project_row_is_created(gate: Gate) -> None:
    request = _approved(gate)
    with SessionLocal() as db:
        before = db.scalar(select(func.count()).select_from(Project))
    response = gate.client.post(f"{ROOT}/{request['id']}/materialize", headers=gate.headers["materializer"])
    assert response.status_code == 200
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(Project)) == before


def test_33_materialization_persists_classification_module_and_manager_scope(gate: Gate) -> None:
    request = _approved(gate)
    created = gate.client.post(
        f"{ROOT}/{request['id']}/materialize",
        headers=gate.headers["materializer"],
    ).json()
    workspace_id = created["materialized_workspace_id"]
    with SessionLocal() as db:
        classifications = db.scalar(
            select(func.count())
            .select_from(EnterpriseWorkspaceClassification)
            .where(EnterpriseWorkspaceClassification.workspace_id == workspace_id)
        )
        modules = db.scalar(
            select(func.count())
            .select_from(WorkspaceModuleSetting)
            .where(
                WorkspaceModuleSetting.workspace_id == workspace_id,
                WorkspaceModuleSetting.enabled.is_(True),
            )
        )
        assignment = db.scalar(
            select(SecurityAccessAssignment).where(
                SecurityAccessAssignment.workspace_id == workspace_id,
                SecurityAccessAssignment.user_id == gate.manager_id,
            )
        )
        assert classifications >= 1
        assert modules == 1
        assert assignment is not None and assignment.scope_type == "workspace"


def test_34_project_overview_reads_canonical_workspace(gate: Gate) -> None:
    request = _approved(gate)
    created = gate.client.post(
        f"{ROOT}/{request['id']}/materialize",
        headers=gate.headers["materializer"],
    ).json()
    response = gate.client.get(
        f"/api/v1/project-workspaces/{created['materialized_workspace_id']}/overview",
        headers=gate.headers["admin"],
    )
    assert response.status_code == 200
    assert response.json()["project_number"] == created["project_number"]
    assert response.json()["template"]


def test_35_created_workspace_is_visible_in_enterprise_explorer(gate: Gate) -> None:
    request = _approved(gate)
    created = gate.client.post(
        f"{ROOT}/{request['id']}/materialize",
        headers=gate.headers["materializer"],
    ).json()
    response = gate.client.get("/api/v1/enterprise-structure/overview", headers=gate.headers["admin"])
    assert response.status_code == 200
    assert any(item["id"] == created["materialized_workspace_id"] for item in response.json()["nodes"])


def test_36_process_events_are_auditable(gate: Gate) -> None:
    request = _approved(gate)
    gate.client.post(f"{ROOT}/{request['id']}/materialize", headers=gate.headers["materializer"])
    with SessionLocal() as db:
        events = list(
            db.scalars(
                select(SecurityEvent).where(
                    SecurityEvent.tenant_id == gate.tenant_id,
                    SecurityEvent.target_type == "project_creation_request",
                    SecurityEvent.target_id == request["id"],
                )
            ).all()
        )
        types = {item.event_type for item in events}
        assert {
            "project_creation.request_created",
            "project_creation.request_submitted",
            "project_creation.review_started",
            "project_creation.request_approved",
            "project_creation.workspace_created",
        } <= types
        assert all(item.metadata_json.get("request_number") == request["request_number"] for item in events)


def test_37_failure_rolls_back_all_materialization_mutations(gate: Gate) -> None:
    request = _approved(gate)
    with SessionLocal() as db:
        before_workspaces = db.scalar(select(func.count()).select_from(EnterpriseWorkspace))
        before_sequence = db.scalar(
            select(AdminNumberSequence.next_value).where(
                AdminNumberSequence.tenant_id == gate.tenant_id,
                AdminNumberSequence.rule_code == "project-workspace",
            )
        )
    with SessionLocal() as db:
        service = ProjectCreationService(db, gate.tenant_id, gate.actor_ids["materializer"])

        def fail(_workspace):
            raise RuntimeError("injected rollback proof")

        with pytest.raises(RuntimeError, match="rollback proof"):
            service.materialize(request["id"], failure_injector=fail)
    with SessionLocal() as db:
        row = db.get(ProjectCreationRequest, request["id"])
        assert row.state == "approved"
        assert db.scalar(select(func.count()).select_from(EnterpriseWorkspace)) == before_workspaces
        assert (
            db.scalar(
                select(AdminNumberSequence.next_value).where(
                    AdminNumberSequence.tenant_id == gate.tenant_id,
                    AdminNumberSequence.rule_code == "project-workspace",
                )
            )
            == before_sequence
        )


def test_38_retry_after_transient_failure_succeeds(gate: Gate) -> None:
    request = _approved(gate)
    with SessionLocal() as db:
        service = ProjectCreationService(db, gate.tenant_id, gate.actor_ids["materializer"])
        with pytest.raises(RuntimeError):
            service.materialize(
                request["id"], failure_injector=lambda _workspace: (_ for _ in ()).throw(RuntimeError())
            )
    response = gate.client.post(f"{ROOT}/{request['id']}/materialize", headers=gate.headers["materializer"])
    assert response.status_code == 200
    assert response.json()["result"] == "CREATED"


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="PostgreSQL row-lock contract")
def test_39_concurrent_materialization_creates_exactly_one_workspace(gate: Gate) -> None:
    request = _approved(gate)

    def materialize() -> tuple[str, int]:
        with SessionLocal() as db:
            result = ProjectCreationService(db, gate.tenant_id, gate.actor_ids["materializer"]).materialize(
                request["id"]
            )
            return result.result, result.materialized_workspace_id

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _value: materialize(), range(2)))
    assert {item[0] for item in results} == {"CREATED", "ALREADY_CREATED"}
    assert len({item[1] for item in results}) == 1


def test_40_materialization_does_not_create_core_revision(gate: Gate) -> None:
    with SessionLocal() as db:
        before = db.scalar(select(func.count()).select_from(EnterpriseCoreRelease))
    request = _approved(gate)
    response = gate.client.post(f"{ROOT}/{request['id']}/materialize", headers=gate.headers["materializer"])
    assert response.status_code == 200
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(EnterpriseCoreRelease)) == before
