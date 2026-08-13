"""Gate 06C acceptance tests for physical Workspace initialization and activation."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from uuid import uuid4

import pytest
from fastapi import HTTPException
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
from app.modules.enterprise_structure.models import EnterpriseWorkspaceClassification
from app.modules.enterprise_structure.permissions import EnterprisePermissionContext, ensure_enterprise_permissions
from app.modules.physical_workspace_creation.models import PhysicalWorkspaceCreationRequest
from app.modules.physical_workspace_initialization.models import PhysicalWorkspaceInitialization
from app.modules.physical_workspace_initialization.service import (
    TYPE_CHECKS,
    PhysicalWorkspaceInitializationService,
)

ROOT = "/api/v1/physical-workspaces"
COMMON_CHECKS = {
    "workspace_identity_valid",
    "workspace_type_supported",
    "workspace_status_pending",
    "parent_valid",
    "business_number_valid",
    "record_code_valid",
    "external_key_valid",
    "template_assigned",
    "template_snapshot_valid",
    "responsible_assigned",
    "responsible_access_valid",
    "required_attributes_complete",
    "required_classifications_valid",
    "module_settings_valid",
    "tenant_scope_valid",
    "no_core_revision_required",
}


@dataclass
class Gate:
    client: TestClient
    headers: dict[str, dict[str, str]]
    tenant_id: int
    actor_ids: dict[str, int]
    parent_id: int
    template_ids: dict[str, int]
    template_hashes: dict[str, str]
    template_codes: dict[str, str]


def _login(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "1234", "tenant_slug": "demo-energy"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _configuration(
    db,
    tenant_id: int,
    actor_id: int,
    *,
    kind: str,
    code: str,
    content: dict,
    name: str | None = None,
    content_hash: str | None = None,
) -> AdminConfiguration:
    revision = (
        int(
            db.scalar(
                select(func.max(AdminConfiguration.revision)).where(
                    AdminConfiguration.tenant_id == tenant_id,
                    AdminConfiguration.kind == kind,
                    AdminConfiguration.code == code,
                )
            )
            or 0
        )
        + 1
    )
    record = AdminConfiguration(
        tenant_id=tenant_id,
        kind=kind,
        code=code,
        name=name or code.replace("-", " ").title(),
        description="Synthetic Gate 06C fixture",
        status="published",
        revision=revision,
        version=1,
        content_json=content,
        content_hash=content_hash or uuid4().hex * 2,
        created_by_user_id=actor_id,
    )
    db.add(record)
    db.flush()
    return record


@pytest.fixture(scope="module")
def gate() -> Gate:
    with TestClient(app) as client:
        admin_headers = _login(client, "admin")
        configured = client.get(
            "/api/v1/admin-configuration/enterprise-structure/physical-workspaces",
            headers=admin_headers,
        )
        assert configured.status_code == 200, configured.text
        actor_ids: dict[str, int] = {}
        emails: dict[str, str] = {}
        template_ids: dict[str, int] = {}
        template_hashes: dict[str, str] = {}
        template_codes: dict[str, str] = {}
        with SessionLocal() as db:
            admin = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
            assert admin is not None
            ensure_enterprise_permissions(db, admin.tenant_id, admin.id)
            roles = {
                row.code: row
                for row in db.scalars(select(SecurityRole).where(SecurityRole.tenant_id == admin.tenant_id)).all()
            }
            outsider_role = SecurityRole(
                tenant_id=admin.tenant_id,
                code=f"gate06c-outsider-{uuid4().hex[:6]}",
                name="Gate 06C Outsider",
                description="No physical lifecycle permissions",
                is_system=False,
                status="active",
            )
            db.add(outsider_role)
            db.flush()
            roles["outsider"] = outsider_role
            for name, role_code in {
                "initializer": "physical_workspace_initializer",
                "activator": "physical_workspace_activator",
                "responsible": "physical_workspace_responsible",
                "requestor": "physical_workspace_requestor",
                "outsider": "outsider",
            }.items():
                email = f"gate06c-{name}-{uuid4().hex[:7]}@demo.local"
                user = UserAccount(
                    tenant_id=admin.tenant_id,
                    email=email,
                    full_name=f"Gate 06C {name.title()}",
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
            parent = db.scalar(
                select(EnterpriseWorkspace).where(
                    EnterpriseWorkspace.tenant_id == admin.tenant_id,
                    EnterpriseWorkspace.parent_id.is_(None),
                    EnterpriseWorkspace.workspace_type_code == "enterprise",
                )
            )
            assert parent is not None
            module = db.scalar(
                select(AdminConfiguration).where(
                    AdminConfiguration.tenant_id == admin.tenant_id,
                    AdminConfiguration.kind == "module_definition",
                    AdminConfiguration.code == "scope-manager",
                    AdminConfiguration.status == "published",
                )
            )
            if module is None:
                _configuration(
                    db,
                    admin.tenant_id,
                    admin.id,
                    kind="module_definition",
                    code="scope-manager",
                    content={"mode": "user", "enabled": True},
                )
            for type_code in ("property", "facility", "warehouse"):
                _configuration(
                    db,
                    admin.tenant_id,
                    admin.id,
                    kind="catalog",
                    code=f"{type_code}-type",
                    content={
                        "applicable_types": [type_code],
                        "items": [{"code": "general", "label": "General"}],
                    },
                )
                _configuration(
                    db,
                    admin.tenant_id,
                    admin.id,
                    kind="workspace_type",
                    code=type_code,
                    content={
                        "required_attributes": [f"{type_code}_type"],
                        "required_categories": [f"{type_code}-type"],
                        "default_attributes": {"currency": "COP", "time_zone": "America/Bogota"},
                    },
                )
                template_code = f"G06C-{type_code.upper()}-{uuid4().hex[:7]}"
                template_hash = (type_code[0] + uuid4().hex)[:32] * 2
                template = _configuration(
                    db,
                    admin.tenant_id,
                    admin.id,
                    kind="physical_template",
                    code=template_code,
                    name=f"Gate 06C {type_code.title()} Template",
                    content={
                        "workspace_type_code": type_code,
                        "applicable_parent_types": ["enterprise"],
                        "required_attributes": [f"{type_code}_type"],
                        "default_attributes": {"country": "CO", "time_zone": "UTC"},
                        "default_classifications": [
                            {"category_set_code": f"{type_code}-type", "category_item_code": "general"}
                        ],
                        "enabled_modules": ["scope-manager"],
                    },
                    content_hash=template_hash,
                )
                template_ids[type_code] = template.id
                template_hashes[type_code] = template_hash
                template_codes[type_code] = template_code
            db.commit()
            tenant_id = admin.tenant_id
            parent_id = parent.id
            actor_ids["admin"] = admin.id
        headers = {name: _login(client, email) for name, email in emails.items()}
        headers["admin"] = admin_headers
        yield Gate(
            client=client,
            headers=headers,
            tenant_id=tenant_id,
            actor_ids=actor_ids,
            parent_id=parent_id,
            template_ids=template_ids,
            template_hashes=template_hashes,
            template_codes=template_codes,
        )


def _attributes(type_code: str, *, complete: bool = True) -> dict:
    values: dict[str, dict] = {
        "property": {
            "property_type": "general",
            "ownership_tenure": "owned",
            "legal_status": "clear",
            "country": "CO",
            "land_area": 100,
            "built_area": 80,
            "book_value": 1000,
            "market_value": 1200,
        },
        "facility": {
            "facility_type": "general",
            "operational_status": "planned",
            "country": "CO",
            "capacity": 100,
            "gross_area": 90,
            "usable_area": 70,
            "criticality": "medium",
            "commissioning_date": "2026-08-13",
        },
        "warehouse": {
            "warehouse_type": "general",
            "country": "CO",
            "storage_capacity": 100,
            "capacity_unit": "m3",
            "criticality": "medium",
        },
    }
    return values[type_code] if complete else {f"{type_code}_type": "general"}


def _workspace(
    gate: Gate,
    type_code: str = "property",
    *,
    attributes: dict | None = None,
    classification: bool = True,
    module_setting: bool = True,
    planned_modules: list[str] | None = None,
    status: str = "pending",
    responsible_id: int | None = None,
    template_hash: str | None = None,
) -> int:
    with SessionLocal() as db:
        suffix = uuid4().hex[:10]
        parent = db.get(EnterpriseWorkspace, gate.parent_id)
        template = db.get(AdminConfiguration, gate.template_ids[type_code])
        assert parent is not None and template is not None
        business_number = f"G06C-{type_code[:3].upper()}-{suffix}"
        record_code = f"{parent.record_code}.{int(suffix[:6], 16) % 900000 + 100000}"
        responsible_id = responsible_id or gate.actor_ids["responsible"]
        physical = {
            "workspace_type_code": type_code,
            "business_number": business_number,
            "description": "Gate 06C physical Workspace",
            "responsible_user_id": responsible_id,
            "attributes": _attributes(type_code) if attributes is None else attributes,
            "explicit_attribute_codes": list((_attributes(type_code) if attributes is None else attributes).keys()),
            "template_id": template.id,
            "template_code": template.code,
            "template_revision": template.revision,
            "template_content_hash": template_hash or template.content_hash,
            "enabled_modules": ["scope-manager"],
            "planned_modules": planned_modules or ["asset-manager", "inventory-manager"],
        }
        workspace = EnterpriseWorkspace(
            tenant_id=gate.tenant_id,
            parent_id=parent.id,
            workspace_type_code=type_code,
            code=business_number,
            external_key=f"urn:ppmis:physical:{uuid4()}",
            record_code=record_code,
            name=f"Gate 06C {type_code.title()} {suffix}",
            status=status,
            defaults_json={"_physical": physical},
            sort_order=99,
            version=1,
            created_by_user_id=gate.actor_ids["requestor"],
        )
        db.add(workspace)
        db.flush()
        request = PhysicalWorkspaceCreationRequest(
            tenant_id=gate.tenant_id,
            request_number=f"PWR-G06C-{suffix}",
            workspace_type_code=type_code,
            state="created",
            requestor_user_id=gate.actor_ids["requestor"],
            parent_workspace_id=parent.id,
            template_config_id=template.id,
            workspace_name=workspace.name,
            description="Gate 06C materialized request",
            responsible_user_id=responsible_id,
            business_number_preview=business_number,
            record_code_preview=record_code,
            attributes_json=physical["attributes"],
            classification_values_json=[],
            submitted_snapshot_json={},
            submitted_hash="s" * 64,
            approval_hash="a" * 64,
            materialized_workspace_id=workspace.id,
            materialized_business_number=business_number,
            materialized_record_code=record_code,
            revision_version=1,
            last_modified_by_user_id=gate.actor_ids["requestor"],
        )
        db.add(request)
        db.flush()
        physical["creation_request_id"] = request.id
        physical["creation_request_number"] = request.request_number
        workspace.defaults_json = {"_physical": physical}
        if classification:
            db.add(
                EnterpriseWorkspaceClassification(
                    tenant_id=gate.tenant_id,
                    workspace_id=workspace.id,
                    category_set_code=f"{type_code}-type",
                    category_item_code="general",
                    created_by_user_id=gate.actor_ids["requestor"],
                )
            )
        if module_setting:
            db.add(
                WorkspaceModuleSetting(
                    tenant_id=gate.tenant_id,
                    workspace_id=workspace.id,
                    module_key="scope-manager",
                    enabled=True,
                    version=1,
                    updated_by_user_id=gate.actor_ids["requestor"],
                )
            )
        db.commit()
        return workspace.id


def _context(gate: Gate, actor: str, role: str) -> EnterprisePermissionContext:
    with SessionLocal() as db:
        user = db.get(UserAccount, gate.actor_ids[actor])
        assert user is not None
        db.expunge(user)
    return EnterprisePermissionContext(
        user=user,
        organization_wide=True,
        scope_unit_ids=frozenset(),
        workspace_ids=frozenset(),
        role_codes=frozenset({role}),
    )


def _start(gate: Gate, workspace_id: int, actor: str = "initializer") -> dict:
    current = gate.client.get(f"{ROOT}/{workspace_id}/initialization", headers=gate.headers[actor])
    assert current.status_code == 200, current.text
    response = gate.client.post(
        f"{ROOT}/{workspace_id}/initialization/start",
        headers={**gate.headers[actor], "If-Match": current.headers["etag"]},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_01_preview_is_non_persistent_and_exact(gate: Gate) -> None:
    workspace_id = _workspace(gate)
    with SessionLocal() as db:
        version_before = db.get(EnterpriseWorkspace, workspace_id).version
    response = gate.client.post(f"{ROOT}/{workspace_id}/initialization/preview", headers=gate.headers["initializer"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["result"] == "PREVIEW"
    assert body["persisted"] is False
    assert body["template_content_hash"] == gate.template_hashes["property"]
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(PhysicalWorkspaceInitialization).where(
                    PhysicalWorkspaceInitialization.workspace_id == workspace_id
                )
            )
            is None
        )
        assert db.get(EnterpriseWorkspace, workspace_id).version == version_before


@pytest.mark.parametrize("type_code", ["property", "facility", "warehouse"])
def test_02_04_single_engine_initializes_all_physical_types(gate: Gate, type_code: str) -> None:
    workspace_id = _workspace(gate, type_code)
    body = _start(gate, workspace_id)
    assert body["state"] == "READY_FOR_ACTIVATION"
    assert {item["code"] for item in body["common_checklist"]} == COMMON_CHECKS
    assert [item["code"] for item in body["type_specific_checklist"]] == list(TYPE_CHECKS[type_code])
    planned = {item["module_key"]: item for item in body["modules"] if item["planned"]}
    assert set(planned) == {"asset-manager", "inventory-manager"}
    assert all(item["state"] == "PLANNED" and not item["operational_module_created"] for item in planned.values())


@pytest.mark.parametrize("blocked_type", ["region", "district", "site", "project", "linear-asset", "asset"])
def test_05_10_non_physical_workspace_types_are_excluded(gate: Gate, blocked_type: str) -> None:
    with SessionLocal() as db:
        parent = db.get(EnterpriseWorkspace, gate.parent_id)
        workspace = EnterpriseWorkspace(
            tenant_id=gate.tenant_id,
            parent_id=parent.id,
            workspace_type_code=blocked_type,
            code=f"G06C-X-{uuid4().hex[:8]}",
            external_key=f"G06C-X-{uuid4()}",
            record_code=f"{parent.record_code}.{int(uuid4().hex[:5], 16) % 90000 + 10000}",
            name=f"Gate 06C excluded {blocked_type}",
            status="pending",
            defaults_json={},
            sort_order=99,
            version=1,
            created_by_user_id=gate.actor_ids["admin"],
        )
        db.add(workspace)
        db.commit()
        workspace_id = workspace.id
    response = gate.client.post(f"{ROOT}/{workspace_id}/initialization/preview", headers=gate.headers["initializer"])
    assert response.status_code == 409
    assert "WORKSPACE_TYPE_NOT_ELIGIBLE" in response.text


def test_11_only_pending_workspaces_can_start(gate: Gate) -> None:
    workspace_id = _workspace(gate, status="draft")
    response = gate.client.post(
        f"{ROOT}/{workspace_id}/initialization/start",
        headers={**gate.headers["initializer"], "If-Match": "1"},
    )
    assert response.status_code == 409
    assert "PHYSICAL_WORKSPACE_MUST_BE_PENDING" in response.text


def test_12_missing_required_data_blocks_without_activating(gate: Gate) -> None:
    workspace_id = _workspace(gate, attributes={}, classification=False)
    body = _start(gate, workspace_id)
    assert body["state"] == "BLOCKED"
    assert body["blocker_count"] >= 2
    with SessionLocal() as db:
        assert db.get(EnterpriseWorkspace, workspace_id).status == "pending"


def test_13_optional_type_data_warns_but_does_not_block(gate: Gate) -> None:
    workspace_id = _workspace(gate, attributes={"property_type": "general"})
    body = _start(gate, workspace_id)
    assert body["state"] == "READY_FOR_ACTIVATION"
    assert body["warning_count"] > 0
    assert body["blocker_count"] == 0


def test_14_defaults_respect_explicit_template_tenant_precedence(gate: Gate) -> None:
    workspace_id = _workspace(gate, attributes={"property_type": "general", "country": "US"})
    body = _start(gate, workspace_id)
    assert body["attributes"]["country"] == "US"
    assert body["attributes"]["time_zone"] == "UTC"
    assert body["attributes"]["currency"] == "COP"
    assert body["defaults_applied"]["time_zone"]["source"] == "template"
    assert body["defaults_applied"]["currency"]["source"] == "tenant_workspace_type"


def test_15_responsible_access_is_minimum_and_idempotent(gate: Gate) -> None:
    workspace_id = _workspace(gate)
    first = _start(gate, workspace_id)
    second = gate.client.post(
        f"{ROOT}/{workspace_id}/initialization/start",
        headers={**gate.headers["initializer"], "If-Match": str(first["revision_version"])},
    )
    assert second.status_code == 200
    assert second.json()["result"] == "ALREADY_INITIALIZED"
    with SessionLocal() as db:
        role = db.scalar(
            select(SecurityRole).where(
                SecurityRole.tenant_id == gate.tenant_id,
                SecurityRole.code == "physical_workspace_responsible",
            )
        )
        count = db.scalar(
            select(func.count())
            .select_from(SecurityAccessAssignment)
            .where(
                SecurityAccessAssignment.tenant_id == gate.tenant_id,
                SecurityAccessAssignment.workspace_id == workspace_id,
                SecurityAccessAssignment.user_id == gate.actor_ids["responsible"],
                SecurityAccessAssignment.role_id == role.id,
            )
        )
        assert count == 1


def test_16_template_snapshot_mismatch_blocks(gate: Gate) -> None:
    workspace_id = _workspace(gate, template_hash="0" * 64)
    body = _start(gate, workspace_id)
    assert body["state"] == "BLOCKED"
    item = next(item for item in body["common_checklist"] if item["code"] == "template_snapshot_valid")
    assert item["status"] == "FAIL"


def test_17_enabled_module_without_setting_blocks(gate: Gate) -> None:
    workspace_id = _workspace(gate, module_setting=False)
    body = _start(gate, workspace_id)
    assert body["state"] == "BLOCKED"
    assert (
        next(item for item in body["common_checklist"] if item["code"] == "module_settings_valid")["status"] == "FAIL"
    )


def test_18_blocked_initialization_can_be_fixed_and_revalidated(gate: Gate) -> None:
    workspace_id = _workspace(gate, attributes={}, classification=False)
    blocked = _start(gate, workspace_id)
    with SessionLocal() as db:
        workspace = db.get(EnterpriseWorkspace, workspace_id)
        defaults = dict(workspace.defaults_json)
        physical = dict(defaults["_physical"])
        physical["attributes"] = {"property_type": "general"}
        physical["explicit_attribute_codes"] = ["property_type"]
        defaults["_physical"] = physical
        workspace.defaults_json = defaults
        db.add(
            EnterpriseWorkspaceClassification(
                tenant_id=gate.tenant_id,
                workspace_id=workspace_id,
                category_set_code="property-type",
                category_item_code="general",
                created_by_user_id=gate.actor_ids["initializer"],
            )
        )
        db.commit()
    response = gate.client.post(
        f"{ROOT}/{workspace_id}/initialization/validate",
        headers={**gate.headers["initializer"], "If-Match": str(blocked["revision_version"])},
    )
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "READY_FOR_ACTIVATION"


def test_19_stale_etag_rejected(gate: Gate) -> None:
    workspace_id = _workspace(gate)
    ready = _start(gate, workspace_id)
    response = gate.client.post(
        f"{ROOT}/{workspace_id}/initialization/validate",
        headers={**gate.headers["initializer"], "If-Match": str(ready["revision_version"] + 1)},
    )
    assert response.status_code == 409
    assert "PHYSICAL_WORKSPACE_VERSION_CONFLICT" in response.text


def test_20_separation_of_duties_blocks_same_initializer_and_activator(gate: Gate) -> None:
    workspace_id = _workspace(gate)
    current = gate.client.get(f"{ROOT}/{workspace_id}/initialization", headers=gate.headers["admin"]).json()
    ready = gate.client.post(
        f"{ROOT}/{workspace_id}/initialization/start",
        headers={**gate.headers["admin"], "If-Match": str(current["revision_version"])},
    ).json()
    response = gate.client.post(
        f"{ROOT}/{workspace_id}/activate",
        headers={**gate.headers["admin"], "If-Match": str(ready["revision_version"])},
    )
    assert response.status_code == 403
    assert "SEPARATION_OF_DUTIES" in response.text


@pytest.mark.parametrize("type_code", ["property", "facility", "warehouse"])
def test_21_23_distinct_actor_activates_each_type_atomically(gate: Gate, type_code: str) -> None:
    workspace_id = _workspace(gate, type_code)
    with SessionLocal() as db:
        before = db.get(EnterpriseWorkspace, workspace_id)
        identity = (before.code, before.record_code, before.external_key)
    ready = _start(gate, workspace_id)
    response = gate.client.post(
        f"{ROOT}/{workspace_id}/activate",
        headers={**gate.headers["activator"], "If-Match": str(ready["revision_version"])},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "ACTIVATED"
    assert body["workspace_status"] == "active"
    with SessionLocal() as db:
        after = db.get(EnterpriseWorkspace, workspace_id)
        assert (after.code, after.record_code, after.external_key) == identity


def test_24_activation_revalidates_hashes(gate: Gate) -> None:
    workspace_id = _workspace(gate)
    ready = _start(gate, workspace_id)
    with SessionLocal() as db:
        workspace = db.get(EnterpriseWorkspace, workspace_id)
        defaults = dict(workspace.defaults_json)
        physical = dict(defaults["_physical"])
        physical["attributes"] = {**physical["attributes"], "market_value": 999999}
        defaults["_physical"] = physical
        workspace.defaults_json = defaults
        db.commit()
    response = gate.client.post(
        f"{ROOT}/{workspace_id}/activate",
        headers={**gate.headers["activator"], "If-Match": str(ready["revision_version"])},
    )
    assert response.status_code == 409
    assert "PHYSICAL_WORKSPACE_VALIDATION_CHANGED" in response.text
    with SessionLocal() as db:
        assert db.get(EnterpriseWorkspace, workspace_id).status == "pending"
        assert (
            db.scalar(
                select(func.count())
                .select_from(SecurityEvent)
                .where(
                    SecurityEvent.tenant_id == gate.tenant_id,
                    SecurityEvent.target_id == workspace_id,
                    SecurityEvent.event_type == "physical_workspace.activation_failed",
                )
            )
            >= 1
        )


def test_25_technical_initialization_failure_is_retryable(gate: Gate) -> None:
    workspace_id = _workspace(gate)
    context = _context(gate, "initializer", "physical_workspace_initializer")
    with SessionLocal() as db:
        service = PhysicalWorkspaceInitializationService(db, gate.tenant_id, gate.actor_ids["initializer"])
        with pytest.raises(RuntimeError, match="synthetic failure"):
            service.start(
                workspace_id,
                context,
                1,
                failure_injector=lambda _record: (_ for _ in ()).throw(RuntimeError("synthetic failure")),
            )
    with SessionLocal() as db:
        workspace = db.get(EnterpriseWorkspace, workspace_id)
        initialization = db.scalar(
            select(PhysicalWorkspaceInitialization).where(PhysicalWorkspaceInitialization.workspace_id == workspace_id)
        )
        assert workspace.status == "pending"
        assert initialization.state == "FAILED"
        version = initialization.revision_version
    response = gate.client.post(
        f"{ROOT}/{workspace_id}/initialization/start",
        headers={**gate.headers["initializer"], "If-Match": str(version)},
    )
    assert response.status_code == 200
    assert response.json()["state"] == "READY_FOR_ACTIVATION"


def test_26_activation_failure_rolls_back_everything(gate: Gate) -> None:
    workspace_id = _workspace(gate)
    ready = _start(gate, workspace_id)
    context = _context(gate, "activator", "physical_workspace_activator")
    with SessionLocal() as db:
        service = PhysicalWorkspaceInitializationService(db, gate.tenant_id, gate.actor_ids["activator"])
        with pytest.raises(RuntimeError, match="activation rollback"):
            service.activate(
                workspace_id,
                context,
                ready["revision_version"],
                failure_injector=lambda _record: (_ for _ in ()).throw(RuntimeError("activation rollback")),
            )
    with SessionLocal() as db:
        assert db.get(EnterpriseWorkspace, workspace_id).status == "pending"
        initialization = db.scalar(
            select(PhysicalWorkspaceInitialization).where(PhysicalWorkspaceInitialization.workspace_id == workspace_id)
        )
        assert initialization.state == "READY_FOR_ACTIVATION"


def test_27_rbac_and_workspace_scoped_read(gate: Gate) -> None:
    workspace_id = _workspace(gate)
    forbidden = gate.client.get(f"{ROOT}/{workspace_id}/initialization", headers=gate.headers["outsider"])
    assert forbidden.status_code == 403
    responsible = gate.client.get(f"{ROOT}/{workspace_id}/initialization", headers=gate.headers["responsible"])
    assert responsible.status_code == 200
    _start(gate, workspace_id)
    responsible = gate.client.get(f"{ROOT}/{workspace_id}/initialization", headers=gate.headers["responsible"])
    assert responsible.status_code == 200
    cannot_initialize = gate.client.post(
        f"{ROOT}/{workspace_id}/initialization/validate",
        headers={**gate.headers["responsible"], "If-Match": responsible.headers["etag"]},
    )
    assert cannot_initialize.status_code == 403


def test_28_list_filters_and_capabilities(gate: Gate) -> None:
    workspace_id = _workspace(gate, "warehouse")
    response = gate.client.get(
        f"{ROOT}?workspace_type=warehouse&initialization_status=NOT_STARTED",
        headers=gate.headers["initializer"],
    )
    assert response.status_code == 200, response.text
    row = next(item for item in response.json() if item["workspace_id"] == workspace_id)
    assert row["can_initialize"] is True
    assert row["can_activate"] is False
    ready = _start(gate, workspace_id)
    response = gate.client.get(
        f"{ROOT}?business_number={ready['business_number']}&template={gate.template_codes['warehouse']}",
        headers=gate.headers["activator"],
    )
    row = next(item for item in response.json() if item["workspace_id"] == workspace_id)
    assert row["can_activate"] is True


def test_29_overview_exposes_lifecycle_without_deep_modules(gate: Gate) -> None:
    workspace_id = _workspace(gate, "facility")
    _start(gate, workspace_id)
    response = gate.client.get(f"{ROOT}/{workspace_id}/overview", headers=gate.headers["initializer"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["initialization_state"] == "READY_FOR_ACTIVATION"
    assert body["initialization_progress_percent"] == 100
    assert body["planned_modules"] == ["asset-manager", "inventory-manager"]
    assert all(item["operational_module_created"] is False for item in body["module_states"].values())


def test_30_audit_events_have_required_traceability(gate: Gate) -> None:
    workspace_id = _workspace(gate)
    ready = _start(gate, workspace_id)
    activated = gate.client.post(
        f"{ROOT}/{workspace_id}/activate",
        headers={**gate.headers["activator"], "If-Match": str(ready["revision_version"])},
    )
    assert activated.status_code == 200
    with SessionLocal() as db:
        events = list(
            db.scalars(
                select(SecurityEvent).where(
                    SecurityEvent.tenant_id == gate.tenant_id,
                    SecurityEvent.target_id == workspace_id,
                    SecurityEvent.event_type.in_(
                        {
                            "physical_workspace.initialization_started",
                            "physical_workspace.initialization_validated",
                            "physical_workspace.ready_for_activation",
                            "physical_workspace.activated",
                        }
                    ),
                )
            ).all()
        )
        assert {item.event_type for item in events} == {
            "physical_workspace.initialization_started",
            "physical_workspace.initialization_validated",
            "physical_workspace.ready_for_activation",
            "physical_workspace.activated",
        }
        activated_event = next(item for item in events if item.event_type == "physical_workspace.activated")
        required = {
            "tenant_id",
            "workspace_id",
            "workspace_type",
            "business_number",
            "record_code",
            "actor",
            "responsible",
            "template",
            "template_revision",
            "state_before",
            "state_after",
            "common_checklist_hash",
            "type_specific_checklist_hash",
            "blocking_issues",
            "warnings",
            "enabled_modules",
            "planned_modules",
            "timestamp",
            "result",
        }
        assert required <= set(activated_event.metadata_json)


@pytest.mark.skipif(engine.dialect.name != "postgresql", reason="Requires PostgreSQL row locking")
def test_31_concurrent_activation_allows_single_effective_transition(gate: Gate) -> None:
    workspace_id = _workspace(gate)
    ready = _start(gate, workspace_id)
    context = _context(gate, "activator", "physical_workspace_activator")

    def activate() -> str:
        with SessionLocal() as db:
            service = PhysicalWorkspaceInitializationService(db, gate.tenant_id, gate.actor_ids["activator"])
            try:
                return service.activate(workspace_id, context, ready["revision_version"]).result
            except HTTPException as exc:
                return str(exc.detail)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: activate(), range(2)))
    assert results.count("ACTIVATED") == 1
    assert results.count("ALREADY_ACTIVE") == 1
