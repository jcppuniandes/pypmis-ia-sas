"""Gate 05C acceptance tests for Project Workspace initialization and activation."""

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
    AuthCredential,
    EnterpriseWorkspace,
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
from app.modules.enterprise_structure.permissions import (
    EnterprisePermissionContext,
    ensure_enterprise_permissions,
)
from app.modules.enterprise_structure.record_codes import next_record_code
from app.modules.project_creation.models import ProjectCreationRequest
from app.modules.project_creation.service import ProjectCreationService
from app.modules.project_workspace_initialization.models import ProjectWorkspaceInitialization
from app.modules.project_workspace_initialization.service import ProjectWorkspaceInitializationService

ROOT = "/api/v1/project-workspaces"


@dataclass
class GateC:
    client: TestClient
    headers: dict[str, dict[str, str]]
    tenant_id: int
    parent_id: int
    template_id: int
    template_code: str
    template_revision: int
    template_hash: str
    manager_id: int
    objective_code: str
    actor_ids: dict[str, int]


def _login(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "1234", "tenant_slug": "demo-energy"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture(scope="module")
def gate() -> GateC:
    with TestClient(app) as client:
        admin_headers = _login(client, "admin")
        configured = client.get(
            "/api/v1/admin-configuration/enterprise-structure/project-workspace",
            headers=admin_headers,
        )
        assert configured.status_code == 200, configured.text
        actor_ids: dict[str, int] = {}
        emails: dict[str, str] = {}
        with SessionLocal() as db:
            admin = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
            assert admin is not None
            ensure_enterprise_permissions(db, admin.tenant_id, admin.id)
            roles = {
                row.code: row
                for row in db.scalars(select(SecurityRole).where(SecurityRole.tenant_id == admin.tenant_id)).all()
            }
            if "viewer" not in roles:
                viewer = SecurityRole(
                    tenant_id=admin.tenant_id,
                    code="gate05c_outsider",
                    name="Gate 05C Outsider",
                    description="Role without Gate 05C permissions.",
                    is_system=False,
                    status="active",
                )
                db.add(viewer)
                db.flush()
                roles["viewer"] = viewer
            for name, role_code in {
                "initializer": "project_workspace_initializer",
                "activator": "project_workspace_activator",
                "manager": "project_manager",
                "outsider": "viewer",
                "requestor": "project_requestor",
                "reviewer": "project_reviewer",
                "approver": "project_approver",
                "materializer": "project_materialization_service",
            }.items():
                email = f"gate05c-{name}-{uuid4().hex[:7]}@demo.local"
                user = UserAccount(
                    tenant_id=admin.tenant_id,
                    email=email,
                    full_name=f"Gate 05C {name.title()}",
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
            root = db.scalar(
                select(EnterpriseWorkspace).where(
                    EnterpriseWorkspace.tenant_id == admin.tenant_id,
                    EnterpriseWorkspace.parent_id.is_(None),
                )
            )
            assert root is not None
            parent = EnterpriseWorkspace(
                tenant_id=admin.tenant_id,
                parent_id=root.id,
                workspace_type_code="portfolio",
                code=f"G05C-PF-{uuid4().hex[:7]}",
                external_key=f"G05C-PF-{uuid4()}",
                record_code=next_record_code(
                    root.record_code,
                    list(
                        db.scalars(
                            select(EnterpriseWorkspace.record_code).where(
                                EnterpriseWorkspace.tenant_id == admin.tenant_id,
                                EnterpriseWorkspace.parent_id == root.id,
                            )
                        ).all()
                    ),
                ),
                name="Gate 05C Portfolio",
                status="active",
                defaults_json={},
                sort_order=95,
                version=1,
                created_by_user_id=admin.id,
            )
            db.add(parent)
            db.flush()
            objective = db.scalar(
                select(EnterpriseStrategicObjective).where(
                    EnterpriseStrategicObjective.tenant_id == admin.tenant_id,
                    EnterpriseStrategicObjective.active.is_(True),
                )
            )
            if objective is None:
                objective = EnterpriseStrategicObjective(
                    tenant_id=admin.tenant_id,
                    code=f"g05c-objective-{uuid4().hex[:7]}",
                    name="Gate 05C Strategic Objective",
                    strategic_line="Enterprise",
                    priority="high",
                    horizon="2030",
                    responsible_area="PMO",
                    active=True,
                    description="Gate 05C isolated objective",
                    source_release_code="GATE05C-TEST",
                    created_by_user_id=admin.id,
                )
                db.add(objective)
                db.flush()
            db.add(
                EnterpriseWorkspaceClassification(
                    tenant_id=admin.tenant_id,
                    workspace_id=parent.id,
                    category_set_code="strategic-objective",
                    category_item_code=objective.code,
                    created_by_user_id=admin.id,
                )
            )
            module = db.scalar(
                select(AdminConfiguration).where(
                    AdminConfiguration.tenant_id == admin.tenant_id,
                    AdminConfiguration.kind == "module_definition",
                    AdminConfiguration.code == "scope-manager",
                    AdminConfiguration.status == "published",
                )
            )
            if module is None:
                module = AdminConfiguration(
                    tenant_id=admin.tenant_id,
                    kind="module_definition",
                    code="scope-manager",
                    name="Scope Manager",
                    description="Gate 05C module",
                    status="published",
                    revision=1,
                    version=1,
                    content_json={"mode": "user"},
                    content_hash="5" * 64,
                    created_by_user_id=admin.id,
                )
                db.add(module)
            template_code = f"G05C-TPL-{uuid4().hex[:7]}"
            template_hash = "c" * 64
            template = AdminConfiguration(
                tenant_id=admin.tenant_id,
                kind="project_template",
                code=template_code,
                name="Gate 05C Project Template",
                description="Exact immutable initialization snapshot",
                status="published",
                revision=1,
                version=1,
                content_json={
                    "applicable_parent_types": ["portfolio", "program"],
                    "default_classifications": [],
                    "enabled_modules": ["scope-manager"],
                    "default_attributes": {"currency": "COP", "country": "CO"},
                },
                content_hash=template_hash,
                created_by_user_id=admin.id,
            )
            db.add(template)
            ProjectCreationService(db, admin.tenant_id, admin.id).ensure_seed()
            db.commit()
            tenant_id = admin.tenant_id
            parent_id = parent.id
            objective_code = objective.code
            template_id = template.id
        headers = {name: _login(client, email) for name, email in emails.items()}
        headers["admin"] = admin_headers
        yield GateC(
            client=client,
            headers=headers,
            tenant_id=tenant_id,
            parent_id=parent_id,
            template_id=template_id,
            template_code=template_code,
            template_revision=1,
            template_hash=template_hash,
            manager_id=actor_ids["manager"],
            objective_code=objective_code,
            actor_ids=actor_ids,
        )


def _workspace(
    gate: GateC,
    *,
    status: str = "pending",
    manager_id: int | None | object = ...,
    objective: bool = True,
    manager_assignment: bool = True,
    module_setting: bool = True,
    module_key: str = "scope-manager",
    metadata_overrides: dict | None = None,
) -> int:
    with SessionLocal() as db:
        parent = db.get(EnterpriseWorkspace, gate.parent_id)
        code = f"G05C-PRJ-{uuid4().hex[:9]}"
        actual_manager_id = gate.manager_id if manager_id is ... else manager_id
        metadata = {
            "project_number": code,
            "description": "Gate 05C governed initialization",
            "project_manager_user_id": actual_manager_id,
            "currency_code": "COP",
            "country": "CO",
            "strategic_objective_codes": [gate.objective_code] if objective else [],
            "template_id": gate.template_id,
            "template_code": gate.template_code,
            "template_revision": gate.template_revision,
            "template_content_hash": gate.template_hash,
            "template_defaults_snapshot": {"currency": "COP", "country": "CO"},
            "explicit_fields": ["currency_code", "country", "project_manager_user_id"],
            "enabled_modules": ["scope-manager"],
        }
        metadata.update(metadata_overrides or {})
        workspace = EnterpriseWorkspace(
            tenant_id=gate.tenant_id,
            parent_id=gate.parent_id,
            workspace_type_code="project",
            code=code,
            external_key=f"G05C-{uuid4()}",
            record_code=f"{parent.record_code}.{int(uuid4().hex[:8], 16)}",
            name=f"Gate 05C Project {uuid4().hex[:6]}",
            status=status,
            defaults_json={"_project": metadata},
            sort_order=100,
            version=1,
            created_by_user_id=gate.actor_ids["initializer"],
        )
        db.add(workspace)
        db.flush()
        if objective:
            db.add(
                EnterpriseWorkspaceClassification(
                    tenant_id=gate.tenant_id,
                    workspace_id=workspace.id,
                    category_set_code="strategic-objective",
                    category_item_code=gate.objective_code,
                    created_by_user_id=gate.actor_ids["initializer"],
                )
            )
        if module_setting:
            db.add(
                WorkspaceModuleSetting(
                    tenant_id=gate.tenant_id,
                    workspace_id=workspace.id,
                    module_key=module_key,
                    enabled=True,
                    version=1,
                    updated_by_user_id=gate.actor_ids["initializer"],
                )
            )
        if manager_assignment and actual_manager_id:
            role = db.scalar(
                select(SecurityRole).where(
                    SecurityRole.tenant_id == gate.tenant_id,
                    SecurityRole.code == "project_manager",
                )
            )
            db.add(
                SecurityAccessAssignment(
                    tenant_id=gate.tenant_id,
                    subject_type="user",
                    user_id=actual_manager_id,
                    role_id=role.id,
                    scope_type="workspace",
                    workspace_id=workspace.id,
                    status="active",
                    granted_by_user_id=gate.actor_ids["initializer"],
                )
            )
        db.commit()
        return workspace.id


def _get(gate: GateC, workspace_id: int, actor: str = "initializer"):
    return gate.client.get(f"{ROOT}/{workspace_id}/initialization", headers=gate.headers[actor])


def _preview(gate: GateC, workspace_id: int, actor: str = "initializer"):
    return gate.client.post(f"{ROOT}/{workspace_id}/initialization/preview", headers=gate.headers[actor])


def _start(gate: GateC, workspace_id: int, version: int = 1, actor: str = "initializer"):
    return gate.client.post(
        f"{ROOT}/{workspace_id}/initialization/start",
        headers={**gate.headers[actor], "If-Match": str(version)},
    )


def _activate(gate: GateC, workspace_id: int, version: int, actor: str = "activator"):
    return gate.client.post(
        f"{ROOT}/{workspace_id}/activate",
        headers={**gate.headers[actor], "If-Match": str(version)},
    )


def _ready(gate: GateC, **kwargs) -> tuple[int, dict]:
    workspace_id = _workspace(gate, **kwargs)
    response = _start(gate, workspace_id)
    assert response.status_code == 200, response.text
    return workspace_id, response.json()


def test_01_get_returns_nonpersistent_not_started(gate: GateC) -> None:
    workspace_id = _workspace(gate)
    value = _get(gate, workspace_id).json()
    assert value["state"] == "NOT_STARTED" and value["persisted"] is False


def test_02_preview_is_nonpersistent(gate: GateC) -> None:
    workspace_id = _workspace(gate)
    assert _preview(gate, workspace_id).json()["persisted"] is False
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count(ProjectWorkspaceInitialization.id)).where(
                    ProjectWorkspaceInitialization.workspace_id == workspace_id
                )
            )
            == 0
        )


def test_03_preview_does_not_change_workspace(gate: GateC) -> None:
    workspace_id = _workspace(gate)
    _preview(gate, workspace_id)
    with SessionLocal() as db:
        row = db.get(EnterpriseWorkspace, workspace_id)
        assert row.status == "pending" and row.version == 1


def test_04_start_reaches_ready(gate: GateC) -> None:
    _workspace_id, value = _ready(gate)
    assert value["state"] == "READY_FOR_ACTIVATION"


def test_05_start_keeps_workspace_pending(gate: GateC) -> None:
    workspace_id, _value = _ready(gate)
    with SessionLocal() as db:
        assert db.get(EnterpriseWorkspace, workspace_id).status == "pending"


def test_06_activation_changes_workspace_to_active(gate: GateC) -> None:
    workspace_id, ready = _ready(gate)
    value = _activate(gate, workspace_id, ready["revision_version"]).json()
    assert value["state"] == "ACTIVATED" and value["workspace_status"] == "active"


def test_07_direct_activation_is_rejected(gate: GateC) -> None:
    workspace_id = _workspace(gate)
    response = _activate(gate, workspace_id, 1)
    assert response.status_code == 409 and "INITIALIZATION_NOT_STARTED" in response.text


def test_08_stale_start_is_rejected(gate: GateC) -> None:
    workspace_id = _workspace(gate)
    response = _start(gate, workspace_id, 9)
    assert response.status_code == 409 and "PROJECT_WORKSPACE_VERSION_CONFLICT" in response.text


def test_09_stale_activation_is_rejected(gate: GateC) -> None:
    workspace_id, _ready_value = _ready(gate)
    response = _activate(gate, workspace_id, 99)
    assert response.status_code == 409 and "PROJECT_WORKSPACE_VERSION_CONFLICT" in response.text


def test_10_repeat_start_is_idempotent(gate: GateC) -> None:
    workspace_id, ready = _ready(gate)
    repeat = _start(gate, workspace_id, ready["revision_version"]).json()
    assert repeat["result"] == "ALREADY_INITIALIZED" and repeat["mutation_count"] == 0


def test_11_repeat_activation_is_idempotent(gate: GateC) -> None:
    workspace_id, ready = _ready(gate)
    active = _activate(gate, workspace_id, ready["revision_version"]).json()
    repeat = _activate(gate, workspace_id, active["revision_version"]).json()
    assert repeat["result"] == "ALREADY_ACTIVE" and repeat["mutation_count"] == 0


def test_12_legacy_active_workspace_is_not_backfilled(gate: GateC) -> None:
    workspace_id = _workspace(gate, status="active")
    value = _get(gate, workspace_id).json()
    assert value["state"] == "ACTIVATED" and value["persisted"] is False
    assert value["progress_percent"] == 100


def test_13_outsider_cannot_read(gate: GateC) -> None:
    assert _get(gate, _workspace(gate), "outsider").status_code == 403


def test_14_activator_cannot_start(gate: GateC) -> None:
    assert _start(gate, _workspace(gate), actor="activator").status_code == 403


def test_15_initializer_cannot_activate(gate: GateC) -> None:
    workspace_id, ready = _ready(gate)
    assert _activate(gate, workspace_id, ready["revision_version"], "initializer").status_code == 403


def test_16_manager_can_read_own_workspace(gate: GateC) -> None:
    assert _get(gate, _workspace(gate), "manager").status_code == 200


def test_17_missing_manager_blocks_preview(gate: GateC) -> None:
    value = _preview(gate, _workspace(gate, manager_id=None, manager_assignment=False)).json()
    assert any(item["code"] == "project_manager_assigned" and item["status"] == "FAIL" for item in value["checklist"])


def test_18_missing_objective_blocks_start(gate: GateC) -> None:
    value = _start(gate, _workspace(gate, objective=False)).json()
    assert value["state"] == "BLOCKED"


def test_19_invalid_parent_blocks(gate: GateC) -> None:
    workspace_id = _workspace(gate)
    with SessionLocal() as db:
        row = db.get(EnterpriseWorkspace, workspace_id)
        row.parent_id = None
        db.commit()
    assert _start(gate, workspace_id).json()["state"] == "BLOCKED"


def test_20_invalid_record_code_blocks(gate: GateC) -> None:
    workspace_id = _workspace(gate)
    with SessionLocal() as db:
        row = db.get(EnterpriseWorkspace, workspace_id)
        row.record_code = f"999.{uuid4().hex[:8]}"
        db.commit()
    assert _start(gate, workspace_id).json()["state"] == "BLOCKED"


def test_21_project_number_mismatch_blocks(gate: GateC) -> None:
    workspace_id = _workspace(gate, metadata_overrides={"project_number": "WRONG"})
    assert _start(gate, workspace_id).json()["state"] == "BLOCKED"


def test_22_missing_template_blocks_start_without_creating_identity(gate: GateC) -> None:
    workspace_id = _workspace(gate, metadata_overrides={"template_id": None})
    response = _start(gate, workspace_id)
    assert response.status_code == 409 and "PROJECT_TEMPLATE_SNAPSHOT_NOT_FOUND" in response.text


def test_23_template_revision_mismatch_blocks(gate: GateC) -> None:
    value = _start(gate, _workspace(gate, metadata_overrides={"template_revision": 999})).json()
    assert value["state"] == "BLOCKED"


def test_24_template_hash_mismatch_blocks(gate: GateC) -> None:
    value = _start(gate, _workspace(gate, metadata_overrides={"template_content_hash": "0" * 64})).json()
    assert value["state"] == "BLOCKED"


def test_25_missing_required_module_setting_blocks(gate: GateC) -> None:
    value = _start(gate, _workspace(gate, module_setting=False)).json()
    assert value["state"] == "BLOCKED"


def test_26_unrecognized_module_blocks(gate: GateC) -> None:
    value = _start(gate, _workspace(gate, module_key="unknown-module")).json()
    assert value["state"] == "BLOCKED"


def test_27_missing_manager_access_is_completed_idempotently(gate: GateC) -> None:
    workspace_id = _workspace(gate, manager_assignment=False)
    value = _start(gate, workspace_id).json()
    assert value["state"] == "READY_FOR_ACTIVATION" and len(value["assignments"]) == 1


def test_28_existing_manager_access_is_not_duplicated(gate: GateC) -> None:
    workspace_id, value = _ready(gate)
    assert value["assignments"] == []
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count(SecurityAccessAssignment.id)).where(
                    SecurityAccessAssignment.workspace_id == workspace_id
                )
            )
            == 1
        )


def test_29_optional_attributes_warn_without_blocking(gate: GateC) -> None:
    _workspace_id, value = _ready(gate)
    assert value["warning_count"] >= 1 and value["blocker_count"] == 0


def test_30_template_default_is_applied_when_missing(gate: GateC) -> None:
    workspace_id = _workspace(
        gate, metadata_overrides={"country": None, "explicit_fields": ["currency_code", "project_manager_user_id"]}
    )
    value = _start(gate, workspace_id).json()
    assert value["defaults_applied"]["country"]["source"] == "template"


def test_31_explicit_value_is_never_overwritten(gate: GateC) -> None:
    workspace_id, value = _ready(gate)
    assert "currency_code" not in value["defaults_applied"]
    with SessionLocal() as db:
        assert db.get(EnterpriseWorkspace, workspace_id).defaults_json["_project"]["currency_code"] == "COP"


def test_32_scope_container_is_initialized_only_minimally(gate: GateC) -> None:
    _workspace_id, value = _ready(gate)
    module = value["modules"][0]
    assert module["state"] == "INITIALIZED" and module["evidence"]["deep_configuration_created"] is False


def test_33_validation_hash_is_persisted(gate: GateC) -> None:
    _workspace_id, value = _ready(gate)
    assert len(value["validation_hash"]) == 64


def test_34_checklist_hash_is_persisted(gate: GateC) -> None:
    _workspace_id, value = _ready(gate)
    assert len(value["checklist_hash"]) == 64


def test_35_checklist_contains_all_mandatory_codes(gate: GateC) -> None:
    value = _preview(gate, _workspace(gate)).json()
    codes = {item["code"] for item in value["checklist"]}
    assert {
        "workspace_identity_valid",
        "workspace_type_project",
        "workspace_status_pending",
        "parent_valid",
        "record_code_valid",
        "project_number_valid",
        "template_assigned",
        "template_snapshot_valid",
        "project_manager_assigned",
        "strategic_objective_present",
        "required_classifications_valid",
        "required_attributes_complete",
        "module_settings_valid",
        "security_assignments_valid",
        "tenant_scope_valid",
        "no_core_revision_required",
    } <= codes


def test_36_audit_records_started_validated_and_ready(gate: GateC) -> None:
    workspace_id, _value = _ready(gate)
    with SessionLocal() as db:
        events = set(db.scalars(select(SecurityEvent.event_type).where(SecurityEvent.target_id == workspace_id)).all())
    assert {
        "project_workspace.initialization_started",
        "project_workspace.initialization_validated",
        "project_workspace.ready_for_activation",
    } <= events


def test_37_activation_audit_is_unique_under_retry(gate: GateC) -> None:
    workspace_id, ready = _ready(gate)
    active = _activate(gate, workspace_id, ready["revision_version"]).json()
    _activate(gate, workspace_id, active["revision_version"])
    with SessionLocal() as db:
        count = db.scalar(
            select(func.count(SecurityEvent.id)).where(
                SecurityEvent.target_id == workspace_id, SecurityEvent.event_type == "project_workspace.activated"
            )
        )
    assert count == 1


def test_38_identity_is_immutable_across_full_cycle(gate: GateC) -> None:
    workspace_id = _workspace(gate)
    with SessionLocal() as db:
        row = db.get(EnterpriseWorkspace, workspace_id)
        before = (row.code, row.record_code, row.external_key, row.parent_id)
    ready = _start(gate, workspace_id).json()
    _activate(gate, workspace_id, ready["revision_version"])
    with SessionLocal() as db:
        row = db.get(EnterpriseWorkspace, workspace_id)
        assert (row.code, row.record_code, row.external_key, row.parent_id) == before


def test_39_no_core_release_is_created(gate: GateC) -> None:
    with SessionLocal() as db:
        before = db.scalar(
            select(func.count(EnterpriseCoreRelease.id)).where(EnterpriseCoreRelease.tenant_id == gate.tenant_id)
        )
    _ready(gate)
    with SessionLocal() as db:
        after = db.scalar(
            select(func.count(EnterpriseCoreRelease.id)).where(EnterpriseCoreRelease.tenant_id == gate.tenant_id)
        )
    assert after == before


def test_40_list_filters_pending(gate: GateC) -> None:
    workspace_id = _workspace(gate)
    response = gate.client.get(f"{ROOT}?status=PENDING", headers=gate.headers["initializer"])
    assert response.status_code == 200 and any(item["workspace_id"] == workspace_id for item in response.json())


def test_41_list_exposes_initializer_capability(gate: GateC) -> None:
    workspace_id = _workspace(gate)
    rows = gate.client.get(ROOT, headers=gate.headers["initializer"]).json()
    row = next(item for item in rows if item["workspace_id"] == workspace_id)
    assert row["can_initialize"] is True and row["can_activate"] is False


def test_42_validate_can_recover_a_blocked_workspace(gate: GateC) -> None:
    workspace_id = _workspace(gate, objective=False)
    blocked = _start(gate, workspace_id).json()
    with SessionLocal() as db:
        db.add(
            EnterpriseWorkspaceClassification(
                tenant_id=gate.tenant_id,
                workspace_id=workspace_id,
                category_set_code="strategic-objective",
                category_item_code=gate.objective_code,
                created_by_user_id=gate.actor_ids["initializer"],
            )
        )
        row = db.get(EnterpriseWorkspace, workspace_id)
        metadata = dict(row.defaults_json["_project"])
        metadata["strategic_objective_codes"] = [gate.objective_code]
        row.defaults_json = {"_project": metadata}
        db.commit()
    response = gate.client.post(
        f"{ROOT}/{workspace_id}/initialization/validate",
        headers={**gate.headers["initializer"], "If-Match": str(blocked["revision_version"])},
    )
    assert response.status_code == 200 and response.json()["state"] == "READY_FOR_ACTIVATION"


def test_43_start_technical_failure_is_recorded(gate: GateC) -> None:
    workspace_id = _workspace(gate)
    with SessionLocal() as db:
        user = db.get(UserAccount, gate.actor_ids["initializer"])
        context = EnterprisePermissionContext(
            user=user,
            organization_wide=True,
            scope_unit_ids=frozenset(),
            workspace_ids=frozenset(),
            role_codes=frozenset({"project_workspace_initializer"}),
        )
        service = ProjectWorkspaceInitializationService(db, gate.tenant_id, user.id)
        with pytest.raises(RuntimeError):
            service.start(
                workspace_id, context, 1, failure_injector=lambda _row: (_ for _ in ()).throw(RuntimeError("boom"))
            )
    with SessionLocal() as db:
        row = db.scalar(
            select(ProjectWorkspaceInitialization).where(ProjectWorkspaceInitialization.workspace_id == workspace_id)
        )
        assert row.state == "FAILED" and db.get(EnterpriseWorkspace, workspace_id).status == "pending"


def test_44_activation_failure_rolls_back_to_pending(gate: GateC) -> None:
    workspace_id, ready = _ready(gate)
    with SessionLocal() as db:
        user = db.get(UserAccount, gate.actor_ids["activator"])
        context = EnterprisePermissionContext(
            user=user,
            organization_wide=True,
            scope_unit_ids=frozenset(),
            workspace_ids=frozenset(),
            role_codes=frozenset({"project_workspace_activator"}),
        )
        service = ProjectWorkspaceInitializationService(db, gate.tenant_id, user.id)
        with pytest.raises(RuntimeError):
            service.activate(
                workspace_id,
                context,
                ready["revision_version"],
                failure_injector=lambda _row: (_ for _ in ()).throw(RuntimeError("boom")),
            )
    with SessionLocal() as db:
        assert db.get(EnterpriseWorkspace, workspace_id).status == "pending"
        assert (
            db.scalar(
                select(ProjectWorkspaceInitialization).where(
                    ProjectWorkspaceInitialization.workspace_id == workspace_id
                )
            ).state
            == "READY_FOR_ACTIVATION"
        )


def test_45_concurrent_activation_has_single_functional_event_on_postgresql(gate: GateC) -> None:
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL row-lock acceptance case")
    workspace_id, ready = _ready(gate)

    def activate_once() -> int:
        with TestClient(app) as client:
            return client.post(
                f"{ROOT}/{workspace_id}/activate",
                headers={**gate.headers["activator"], "If-Match": str(ready["revision_version"])},
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(lambda _index: activate_once(), range(2)))
    assert statuses.count(200) == 2
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count(SecurityEvent.id)).where(
                    SecurityEvent.target_id == workspace_id,
                    SecurityEvent.event_type == "project_workspace.activated",
                )
            )
            == 1
        )


def test_46_preview_after_start_remains_nonmutating(gate: GateC) -> None:
    workspace_id, ready = _ready(gate)
    preview = _preview(gate, workspace_id).json()
    assert preview["persisted"] is False and preview["revision_version"] == ready["revision_version"]


def test_47_exact_template_revision_survives_newer_revision(gate: GateC) -> None:
    workspace_id = _workspace(gate)
    with SessionLocal() as db:
        source = db.get(AdminConfiguration, gate.template_id)
        db.add(
            AdminConfiguration(
                tenant_id=gate.tenant_id,
                kind="project_template",
                code=gate.template_code,
                name=source.name,
                description="newer",
                status="published",
                revision=2,
                version=1,
                content_json=source.content_json,
                content_hash="d" * 64,
                created_by_user_id=gate.actor_ids["initializer"],
            )
        )
        db.commit()
    value = _start(gate, workspace_id).json()
    assert value["template_revision"] == 1 and value["state"] == "READY_FOR_ACTIVATION"


def test_48_initialization_does_not_create_creation_request(gate: GateC) -> None:
    with SessionLocal() as db:
        before = db.scalar(
            select(func.count(ProjectCreationRequest.id)).where(ProjectCreationRequest.tenant_id == gate.tenant_id)
        )
    _ready(gate)
    with SessionLocal() as db:
        after = db.scalar(
            select(func.count(ProjectCreationRequest.id)).where(ProjectCreationRequest.tenant_id == gate.tenant_id)
        )
    assert after == before


def test_49_revision_version_advances_on_revalidation(gate: GateC) -> None:
    workspace_id, ready = _ready(gate)
    response = gate.client.post(
        f"{ROOT}/{workspace_id}/initialization/validate",
        headers={**gate.headers["initializer"], "If-Match": str(ready["revision_version"])},
    )
    assert response.json()["revision_version"] == ready["revision_version"] + 1


def test_50_full_cycle_returns_only_governed_states(gate: GateC) -> None:
    workspace_id = _workspace(gate)
    assert _get(gate, workspace_id).json()["state"] == "NOT_STARTED"
    ready = _start(gate, workspace_id).json()
    assert ready["state"] == "READY_FOR_ACTIVATION"
    assert _activate(gate, workspace_id, ready["revision_version"]).json()["state"] == "ACTIVATED"


def test_51_disabled_optional_module_does_not_block(gate: GateC) -> None:
    workspace_id = _workspace(gate)
    with SessionLocal() as db:
        db.add(
            WorkspaceModuleSetting(
                tenant_id=gate.tenant_id,
                workspace_id=workspace_id,
                module_key="future-optional-module",
                enabled=False,
                version=1,
                updated_by_user_id=gate.actor_ids["initializer"],
            )
        )
        db.commit()
    assert _start(gate, workspace_id).json()["state"] == "READY_FOR_ACTIVATION"


def test_52_same_actor_cannot_initialize_and_activate(gate: GateC) -> None:
    workspace_id = _workspace(gate)
    ready = _start(gate, workspace_id, actor="admin").json()
    response = _activate(gate, workspace_id, ready["revision_version"], actor="admin")
    assert response.status_code == 403
    assert "ACTIVATION_SEPARATION_OF_DUTIES_VIOLATION" in response.text


def test_53_cross_tenant_workspace_is_not_visible(gate: GateC) -> None:
    workspace_id = _workspace(gate)
    with SessionLocal() as db:
        user = db.get(UserAccount, gate.actor_ids["initializer"])
        context = EnterprisePermissionContext(
            user=user,
            organization_wide=True,
            scope_unit_ids=frozenset(),
            workspace_ids=frozenset(),
            role_codes=frozenset({"project_workspace_initializer"}),
        )
        service = ProjectWorkspaceInitializationService(db, gate.tenant_id + 999999, user.id)
        with pytest.raises(Exception) as error:
            service.get(workspace_id, context)
    assert getattr(error.value, "status_code", None) == 404


def test_54_gate05b_materialization_to_gate05c_activation(gate: GateC) -> None:
    created = gate.client.post(
        "/api/v1/project-creation-requests",
        headers=gate.headers["requestor"],
        json={
            "parent_workspace_id": gate.parent_id,
            "project_template_config_id": gate.template_id,
            "project_name": f"Gate 05C Integrated Project {uuid4().hex[:8]}",
            "description": "Gate 05B materialization through Gate 05C activation",
            "project_manager_user_id": gate.manager_id,
            "planned_start": "2026-09-01",
            "planned_finish": "2027-08-31",
            "currency_code": "COP",
            "estimated_budget": "1250000.00",
            "country": "CO",
            "strategic_objective_codes": [gate.objective_code],
        },
    )
    assert created.status_code == 201, created.text
    request = created.json()
    for action, actor in (
        ("submit", "requestor"),
        ("start-review", "reviewer"),
        ("approve", "approver"),
    ):
        response = gate.client.post(
            f"/api/v1/project-creation-requests/{request['id']}/{action}",
            headers={**gate.headers[actor], "If-Match": str(request["revision_version"])},
        )
        assert response.status_code == 200, response.text
        request = response.json()
    materialized = gate.client.post(
        f"/api/v1/project-creation-requests/{request['id']}/materialize",
        headers=gate.headers["materializer"],
    )
    assert materialized.status_code == 200, materialized.text
    workspace_id = materialized.json()["materialized_workspace_id"]
    ready = _start(gate, workspace_id).json()
    assert ready["state"] == "READY_FOR_ACTIVATION"
    activated = _activate(gate, workspace_id, ready["revision_version"])
    assert activated.status_code == 200, activated.text
    assert activated.json()["state"] == "ACTIVATED"


def test_55_scope_schedule_and_cost_minimal_initialization(gate: GateC) -> None:
    with SessionLocal() as db:
        for code, name in (
            ("schedule-manager", "Schedule Manager"),
            ("cost-manager", "Cost Manager"),
        ):
            definition = db.scalar(
                select(AdminConfiguration).where(
                    AdminConfiguration.tenant_id == gate.tenant_id,
                    AdminConfiguration.kind == "module_definition",
                    AdminConfiguration.code == code,
                    AdminConfiguration.status == "published",
                )
            )
            if definition is None:
                db.add(
                    AdminConfiguration(
                        tenant_id=gate.tenant_id,
                        kind="module_definition",
                        code=code,
                        name=name,
                        description=f"Gate 05C {name} definition",
                        status="published",
                        revision=1,
                        version=1,
                        content_json={"mode": "user"},
                        content_hash=code[0] * 64,
                        created_by_user_id=gate.actor_ids["initializer"],
                    )
                )
        template = AdminConfiguration(
            tenant_id=gate.tenant_id,
            kind="project_template",
            code=f"G05C-ALL-{uuid4().hex[:7]}",
            name="Gate 05C All Minimal Modules",
            description="Scope, Schedule and Cost minimal initialization",
            status="published",
            revision=1,
            version=1,
            content_json={
                "applicable_parent_types": ["portfolio", "program"],
                "default_classifications": [],
                "enabled_modules": ["scope-manager", "schedule-manager", "cost-manager"],
                "default_attributes": {"currency": "COP", "country": "CO"},
            },
            content_hash="a" * 64,
            created_by_user_id=gate.actor_ids["initializer"],
        )
        db.add(template)
        db.commit()
        template_id = template.id
        template_code = template.code
    workspace_id = _workspace(
        gate,
        module_setting=False,
        metadata_overrides={
            "template_id": template_id,
            "template_code": template_code,
            "template_revision": 1,
            "template_content_hash": "a" * 64,
            "enabled_modules": ["scope-manager", "schedule-manager", "cost-manager"],
        },
    )
    with SessionLocal() as db:
        for module_key in ("scope-manager", "schedule-manager", "cost-manager"):
            db.add(
                WorkspaceModuleSetting(
                    tenant_id=gate.tenant_id,
                    workspace_id=workspace_id,
                    module_key=module_key,
                    enabled=True,
                    version=1,
                    updated_by_user_id=gate.actor_ids["initializer"],
                )
            )
        db.commit()
    value = _start(gate, workspace_id).json()
    assert value["state"] == "READY_FOR_ACTIVATION"
    modules = {item["module_key"]: item for item in value["modules"]}
    assert set(modules) == {"scope-manager", "schedule-manager", "cost-manager"}
    assert all(item["state"] == "INITIALIZED" for item in modules.values())
    assert modules["cost-manager"]["evidence"]["currency"] == "COP"
    assert all(item["evidence"]["deep_configuration_created"] is False for item in modules.values())


def test_56_concurrent_initialization_is_singleton_on_postgresql(gate: GateC) -> None:
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL row-lock acceptance case")
    workspace_id = _workspace(gate)

    def start_once() -> int:
        with TestClient(app) as client:
            return client.post(
                f"{ROOT}/{workspace_id}/initialization/start",
                headers={**gate.headers["initializer"], "If-Match": "1"},
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(lambda _index: start_once(), range(2)))
    assert statuses.count(200) == 2
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count(ProjectWorkspaceInitialization.id)).where(
                    ProjectWorkspaceInitialization.workspace_id == workspace_id
                )
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count(SecurityEvent.id)).where(
                    SecurityEvent.target_id == workspace_id,
                    SecurityEvent.event_type == "project_workspace.initialization_started",
                )
            )
            == 1
        )
