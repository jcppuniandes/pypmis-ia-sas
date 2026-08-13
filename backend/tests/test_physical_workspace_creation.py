"""Gate 06B acceptance tests for the generic physical Workspace creation engine."""

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.security import hash_password
from app.database.session import SessionLocal
from app.domain.models import (
    AdminConfiguration,
    AdminNumberSequence,
    AuthCredential,
    EnterpriseWorkspace,
    SecurityAccessAssignment,
    SecurityEvent,
    SecurityRole,
    UserAccount,
    WorkspaceModuleSetting,
)
from app.main import app
from app.modules.enterprise_structure.models import EnterpriseCoreRelease, EnterpriseWorkspaceClassification
from app.modules.enterprise_structure.permissions import ensure_enterprise_permissions
from app.modules.enterprise_structure.physical_configuration import PhysicalWorkspaceConfigurationService
from app.modules.enterprise_structure.record_codes import next_record_code
from app.modules.physical_workspace_creation.models import PhysicalWorkspaceCreationRequest
from app.modules.physical_workspace_creation.service import PhysicalWorkspaceCreationService

ROOT = "/api/v1/physical-workspace-creation-requests"
ADMIN_ROOT = "/api/v1/admin-configuration/enterprise-structure"


@dataclass
class Gate:
    client: TestClient
    headers: dict[str, dict[str, str]]
    tenant_id: int
    actor_ids: dict[str, int]
    parent_ids: dict[str, int]
    template_ids: dict[str, int]
    draft_template_id: int
    baseline: dict[str, int | str | None]


def _login(client: TestClient, email: str) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "1234", "tenant_slug": "demo-energy"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _configuration_hash(record: AdminConfiguration) -> str:
    payload = {
        "kind": record.kind,
        "code": record.code,
        "revision": record.revision,
        "name": record.name,
        "description": record.description,
        "content": record.content_json,
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _new_configuration(
    db,
    tenant_id: int,
    actor_id: int,
    *,
    kind: str,
    code: str,
    name: str,
    status: str,
    content: dict,
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
        name=name,
        description="Synthetic Gate 06B ephemeral-only fixture",
        status=status,
        revision=revision,
        version=1,
        content_json=content,
        created_by_user_id=actor_id,
    )
    record.content_hash = _configuration_hash(record)
    db.add(record)
    db.flush()
    return record


def _baseline(db, tenant_id: int) -> dict[str, int | str | None]:
    release = db.scalar(
        select(EnterpriseCoreRelease).where(
            EnterpriseCoreRelease.tenant_id == tenant_id,
            EnterpriseCoreRelease.state == "published",
        )
    )
    return {
        "release_id": release.id if release else None,
        "release_code": release.release_code if release else None,
        "core_drafts": int(
            db.scalar(
                select(func.count())
                .select_from(EnterpriseCoreRelease)
                .where(
                    EnterpriseCoreRelease.tenant_id == tenant_id,
                    EnterpriseCoreRelease.state == "draft",
                )
            )
            or 0
        ),
        "project_workspaces": int(
            db.scalar(
                select(func.count())
                .select_from(EnterpriseWorkspace)
                .where(
                    EnterpriseWorkspace.tenant_id == tenant_id,
                    EnterpriseWorkspace.workspace_type_code == "project",
                )
            )
            or 0
        ),
    }


@pytest.fixture(scope="module")
def gate() -> Gate:
    with TestClient(app) as client:
        admin_headers = _login(client, "admin")
        seeded = client.get(f"{ADMIN_ROOT}/physical-workspaces", headers=admin_headers)
        assert seeded.status_code == 200, seeded.text
        with SessionLocal() as db:
            admin = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
            assert admin is not None
            ensure_enterprise_permissions(db, admin.tenant_id, admin.id)
            physical = PhysicalWorkspaceConfigurationService(db, admin.tenant_id, admin.id)
            physical.ensure_seed()
            baseline = _baseline(db, admin.tenant_id)
            root = db.scalar(
                select(EnterpriseWorkspace).where(
                    EnterpriseWorkspace.tenant_id == admin.tenant_id,
                    EnterpriseWorkspace.workspace_type_code == "enterprise",
                    EnterpriseWorkspace.parent_id.is_(None),
                )
            )
            assert root is not None
            synthetic_property = EnterpriseWorkspace(
                tenant_id=admin.tenant_id,
                parent_id=root.id,
                workspace_type_code="property",
                code=f"G06B-PROP-PARENT-{uuid4().hex[:6]}",
                external_key=f"G06B-PROP-PARENT-{uuid4()}",
                record_code=next_record_code(
                    root.record_code,
                    db.scalars(
                        select(EnterpriseWorkspace.record_code).where(
                            EnterpriseWorkspace.tenant_id == admin.tenant_id,
                            EnterpriseWorkspace.parent_id == root.id,
                        )
                    ).all(),
                ),
                name="Gate 06B Active Property Parent",
                status="active",
                defaults_json={"_fixture": "ephemeral-only"},
                sort_order=90,
                version=1,
                created_by_user_id=admin.id,
            )
            db.add(synthetic_property)
            db.flush()
            synthetic_facility = EnterpriseWorkspace(
                tenant_id=admin.tenant_id,
                parent_id=synthetic_property.id,
                workspace_type_code="facility",
                code=f"G06B-FAC-PARENT-{uuid4().hex[:6]}",
                external_key=f"G06B-FAC-PARENT-{uuid4()}",
                record_code=next_record_code(synthetic_property.record_code, []),
                name="Gate 06B Active Facility Parent",
                status="active",
                defaults_json={"_fixture": "ephemeral-only"},
                sort_order=90,
                version=1,
                created_by_user_id=admin.id,
            )
            db.add(synthetic_facility)
            db.flush()
            module = db.scalar(
                select(AdminConfiguration).where(
                    AdminConfiguration.tenant_id == admin.tenant_id,
                    AdminConfiguration.kind == "module_definition",
                    AdminConfiguration.status == "published",
                )
            )
            if module is None:
                module = _new_configuration(
                    db,
                    admin.tenant_id,
                    admin.id,
                    kind="module_definition",
                    code="scope-manager",
                    name="Scope Manager",
                    status="published",
                    content={"mode": "user", "enabled": True},
                )
            for type_code in ("property", "facility", "warehouse"):
                catalog_code = f"{type_code}-type"
                _new_configuration(
                    db,
                    admin.tenant_id,
                    admin.id,
                    kind="catalog",
                    code=catalog_code,
                    name=f"{type_code.title()} Type",
                    status="published",
                    content={
                        "applicable_types": [type_code],
                        "items": [{"code": "general", "label": "General"}],
                    },
                )
                _new_configuration(
                    db,
                    admin.tenant_id,
                    admin.id,
                    kind="creation_policy",
                    code=f"physical-{type_code}-creation",
                    name=f"{type_code.title()} Creation Policy",
                    status="published",
                    content={
                        "workspace_type_code": type_code,
                        "allowed_parent_types": {
                            "property": ["enterprise", "region", "district", "site"],
                            "facility": ["enterprise", "region", "district", "site", "property"],
                            "warehouse": ["enterprise", "region", "district", "site", "property", "facility"],
                        }[type_code],
                        "template_required": True,
                        "responsible_required": True,
                        "approval_required": True,
                        "auto_business_number": True,
                        "auto_record_code": True,
                        "initial_workspace_status": "pending",
                    },
                )
            template_ids: dict[str, int] = {}
            for type_code in ("property", "facility", "warehouse"):
                template = _new_configuration(
                    db,
                    admin.tenant_id,
                    admin.id,
                    kind="physical_template",
                    code=f"G06B-{type_code.upper()}-{uuid4().hex[:6]}",
                    name=f"Gate 06B {type_code.title()}",
                    status="published",
                    content={
                        "workspace_type_code": type_code,
                        "applicable_parent_types": {
                            "property": ["enterprise", "region", "district", "site"],
                            "facility": ["enterprise", "region", "district", "site", "property"],
                            "warehouse": ["enterprise", "region", "district", "site", "property", "facility"],
                        }[type_code],
                        "default_classifications": [],
                        "enabled_modules": [module.code],
                        "default_attributes": {},
                        "numbering_rule_code": f"physical-{type_code}",
                        "creation_policy_code": f"physical-{type_code}-creation",
                    },
                )
                template_ids[type_code] = template.id
            draft_template_id = db.scalar(
                select(AdminConfiguration.id).where(
                    AdminConfiguration.tenant_id == admin.tenant_id,
                    AdminConfiguration.kind == "physical_template",
                    AdminConfiguration.status == "draft",
                )
            )
            assert draft_template_id is not None
            actor_ids: dict[str, int] = {}
            emails: dict[str, str] = {}
            roles = {
                item.code: item
                for item in db.scalars(select(SecurityRole).where(SecurityRole.tenant_id == admin.tenant_id)).all()
            }
            for name, role_code in {
                "requestor": "physical_workspace_requestor",
                "reviewer": "physical_workspace_reviewer",
                "approver": "physical_workspace_approver",
                "materializer": "physical_workspace_materialization_service",
                "responsible": "physical_workspace_responsible",
            }.items():
                email = f"gate06b-{name}-{uuid4().hex[:6]}@demo.local"
                user = UserAccount(
                    tenant_id=admin.tenant_id,
                    email=email,
                    full_name=f"Gate 06B {name.title()}",
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
            PhysicalWorkspaceCreationService(db, admin.tenant_id, admin.id).ensure_seed()
            db.commit()
            tenant_id = admin.tenant_id
            parent_ids = {
                "enterprise": root.id,
                "facility": synthetic_property.id,
                "warehouse": synthetic_facility.id,
            }
        headers = {name: _login(client, email) for name, email in emails.items()}
        headers["admin"] = admin_headers
        yield Gate(
            client=client,
            headers=headers,
            tenant_id=tenant_id,
            actor_ids=actor_ids,
            parent_ids=parent_ids,
            template_ids=template_ids,
            draft_template_id=draft_template_id,
            baseline=baseline,
        )


def _payload(gate: Gate, type_code: str = "property", **overrides) -> dict:
    with SessionLocal() as db:
        choices = PhysicalWorkspaceCreationService(
            db, gate.tenant_id, gate.actor_ids["requestor"]
        )._classification_options(type_code)[f"{type_code}-type"]
        classification_code = str(choices[0]["code"])
    value = {
        "workspace_type_code": type_code,
        "parent_workspace_id": gate.parent_ids.get(type_code, gate.parent_ids["enterprise"]),
        "template_config_id": gate.template_ids[type_code],
        "workspace_name": f"Gate 06B {type_code.title()} {uuid4().hex[:6]}",
        "description": "Governed Gate 06B acceptance fixture",
        "responsible_user_id": gate.actor_ids["responsible"],
        "attributes": {f"{type_code}_type": classification_code, "operational_status": "planned"},
        "classifications": [{"category_set_code": f"{type_code}-type", "category_item_code": classification_code}],
    }
    value.update(overrides)
    return value


def _create(gate: Gate, type_code: str = "property", **overrides) -> dict:
    response = gate.client.post(ROOT, headers=gate.headers["requestor"], json=_payload(gate, type_code, **overrides))
    assert response.status_code == 201, response.text
    return response.json()


def _transition(gate: Gate, request: dict, action: str, actor: str, payload: dict | None = None):
    return gate.client.post(
        f"{ROOT}/{request['id']}/{action}",
        headers={**gate.headers[actor], "If-Match": str(request["revision_version"])},
        json=payload,
    )


def _approved(gate: Gate, type_code: str = "property", **overrides) -> dict:
    request = _create(gate, type_code, **overrides)
    request = _transition(gate, request, "submit", "requestor").json()
    request = _transition(gate, request, "start-review", "reviewer").json()
    response = _transition(gate, request, "approve", "approver")
    assert response.status_code == 200, response.text
    return response.json()


def _materialize(gate: Gate, request: dict):
    return gate.client.post(
        f"{ROOT}/{request['id']}/materialize",
        headers={**gate.headers["materializer"], "If-Match": str(request["revision_version"])},
    )


def test_01_options_expose_only_operational_physical_types(gate: Gate) -> None:
    response = gate.client.get(ROOT + "/options", headers=gate.headers["requestor"])
    assert response.status_code == 200
    assert [item["code"] for item in response.json()["workspace_types"]] == ["property", "facility", "warehouse"]


@pytest.mark.parametrize("blocked", ["region", "district", "site", "linear-asset", "asset", "project"])
def test_02_07_non_operational_types_are_blocked(gate: Gate, blocked: str) -> None:
    payload = _payload(gate)
    payload["workspace_type_code"] = blocked
    response = gate.client.post(ROOT, headers=gate.headers["requestor"], json=payload)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "WORKSPACE_TYPE_NOT_CREATABLE"


@pytest.mark.parametrize("type_code", ["property", "facility", "warehouse"])
def test_08_10_generic_request_supports_three_types(gate: Gate, type_code: str) -> None:
    response = gate.client.get(ROOT + f"/options?workspace_type_code={type_code}", headers=gate.headers["requestor"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["selected_workspace_type"] == type_code
    assert body["blocked_reason"] is None
    assert body["dynamic_attributes"]


def test_11_parent_options_are_calculated_by_backend(gate: Gate) -> None:
    response = gate.client.get(ROOT + "/options?workspace_type_code=property", headers=gate.headers["requestor"])
    assert response.status_code == 200
    assert {item["workspace_type_code"] for item in response.json()["locations"]} <= {
        "enterprise",
        "region",
        "district",
        "site",
    }


def test_12_draft_template_is_blocked(gate: Gate) -> None:
    response = gate.client.post(
        ROOT,
        headers=gate.headers["requestor"],
        json=_payload(gate, template_config_id=gate.draft_template_id),
    )
    assert response.status_code == 422
    assert "NO_PUBLISHED_PHYSICAL_WORKSPACE_TEMPLATE" in response.text


def test_12b_draft_policy_is_blocked(gate: Gate) -> None:
    with SessionLocal() as db:
        policies = db.scalars(
            select(AdminConfiguration).where(
                AdminConfiguration.tenant_id == gate.tenant_id,
                AdminConfiguration.kind == "creation_policy",
                AdminConfiguration.code == "physical-property-creation",
                AdminConfiguration.status == "published",
            )
        ).all()
        assert policies
        for policy in policies:
            policy.status = "draft"
        db.flush()
        options = PhysicalWorkspaceCreationService(db, gate.tenant_id, gate.actor_ids["requestor"]).options("property")
        assert options.blocked_reason == "PHYSICAL_CREATION_POLICY_NOT_PUBLISHED"
        db.rollback()


def test_12c_wrong_type_template_and_invalid_parent_are_blocked(gate: Gate) -> None:
    wrong_template = gate.client.post(
        ROOT,
        headers=gate.headers["requestor"],
        json=_payload(gate, template_config_id=gate.template_ids["facility"]),
    )
    assert wrong_template.status_code == 422
    assert "PHYSICAL_TEMPLATE_WRONG_WORKSPACE_TYPE" in wrong_template.text
    invalid_parent = gate.client.post(
        ROOT,
        headers=gate.headers["requestor"],
        json=_payload(gate, parent_workspace_id=gate.parent_ids["warehouse"]),
    )
    assert invalid_parent.status_code == 422
    assert "PHYSICAL_CREATION_POLICY_BLOCKS_PARENT" in invalid_parent.text


def test_13_missing_responsible_is_blocked(gate: Gate) -> None:
    response = gate.client.post(
        ROOT, headers=gate.headers["requestor"], json=_payload(gate, responsible_user_id=999999)
    )
    assert response.status_code == 422
    assert "PHYSICAL_WORKSPACE_RESPONSIBLE_REQUIRED" in response.text


def test_14_request_number_is_separate_and_unique(gate: Gate) -> None:
    first, second = _create(gate), _create(gate)
    assert first["request_number"].startswith("PWR-")
    assert first["request_number"] != second["request_number"]
    assert first["materialized_business_number"] is None


def test_15_preview_is_non_persistent_and_does_not_consume_business_number(gate: Gate) -> None:
    request = _create(gate)
    with SessionLocal() as db:
        workspace_count = db.scalar(select(func.count()).select_from(EnterpriseWorkspace))
        sequence_before = db.scalar(
            select(AdminNumberSequence.next_value).where(
                AdminNumberSequence.tenant_id == gate.tenant_id,
                AdminNumberSequence.rule_code == "physical-property",
            )
        )
    first = gate.client.post(f"{ROOT}/{request['id']}/preview", headers=gate.headers["requestor"])
    second = gate.client.post(f"{ROOT}/{request['id']}/preview", headers=gate.headers["requestor"])
    assert first.status_code == second.status_code == 200
    assert first.json()["projected_business_number"] == second.json()["projected_business_number"]
    assert first.json()["persisted"] is False
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(EnterpriseWorkspace)) == workspace_count
        assert (
            db.scalar(
                select(AdminNumberSequence.next_value).where(
                    AdminNumberSequence.tenant_id == gate.tenant_id,
                    AdminNumberSequence.rule_code == "physical-property",
                )
            )
            == sequence_before
        )


def test_16_stale_if_match_is_rejected(gate: Gate) -> None:
    request = _create(gate)
    response = gate.client.post(
        f"{ROOT}/{request['id']}/submit",
        headers={**gate.headers["requestor"], "If-Match": "999"},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "PHYSICAL_WORKSPACE_REQUEST_VERSION_CONFLICT"


def test_17_return_resubmit_and_reject(gate: Gate) -> None:
    request = _create(gate)
    request = _transition(gate, request, "submit", "requestor").json()
    returned = _transition(gate, request, "return", "reviewer", {"reason": "Complete evidence"})
    assert returned.status_code == 200 and returned.json()["state"] == "returned"
    update = gate.client.put(
        f"{ROOT}/{request['id']}",
        headers={**gate.headers["requestor"], "If-Match": str(returned.json()["revision_version"])},
        json=_payload(gate, workspace_name="Returned Property Updated"),
    )
    assert update.status_code == 200 and update.json()["state"] == "draft"
    request = _transition(gate, update.json(), "submit", "requestor").json()
    request = _transition(gate, request, "start-review", "reviewer").json()
    rejected = _transition(gate, request, "reject", "reviewer", {"reason": "Not approved"})
    assert rejected.status_code == 200 and rejected.json()["state"] == "rejected"


def test_17b_cancel_from_draft(gate: Gate) -> None:
    request = _create(gate)
    cancelled = _transition(gate, request, "cancel", "requestor")
    assert cancelled.status_code == 200
    assert cancelled.json()["state"] == "cancelled"


def test_18_four_eyes_is_enforced(gate: Gate) -> None:
    request = _create(gate)
    request = _transition(gate, request, "submit", "requestor").json()
    request = _transition(gate, request, "start-review", "reviewer").json()
    response = _transition(gate, request, "approve", "requestor")
    assert response.status_code == 403


def test_19_materialization_requires_approval(gate: Gate) -> None:
    request = _create(gate)
    response = _materialize(gate, request)
    assert response.status_code == 409


def test_20_property_materializes_atomically(gate: Gate) -> None:
    request = _approved(gate)
    response = _materialize(gate, request)
    assert response.status_code == 200, response.text
    created = response.json()
    assert created["business_number"].startswith("PYP-PROP-")
    with SessionLocal() as db:
        workspace = db.get(EnterpriseWorkspace, created["materialized_workspace_id"])
        assert workspace.workspace_type_code == "property"
        assert workspace.status == "pending"
        assert workspace.defaults_json["_physical"]["creation_request_id"] == request["id"]
        assert (
            db.scalar(
                select(func.count())
                .select_from(WorkspaceModuleSetting)
                .where(WorkspaceModuleSetting.workspace_id == workspace.id)
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(EnterpriseWorkspaceClassification)
                .where(EnterpriseWorkspaceClassification.workspace_id == workspace.id)
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(SecurityAccessAssignment)
                .where(
                    SecurityAccessAssignment.workspace_id == workspace.id,
                    SecurityAccessAssignment.user_id == gate.actor_ids["responsible"],
                )
            )
            == 1
        )


def test_21_facility_and_warehouse_materialize_below_physical_parents(gate: Gate) -> None:
    facility_request = _approved(gate, "facility")
    facility_response = _materialize(gate, facility_request)
    assert facility_response.status_code == 200, facility_response.text
    assert facility_response.json()["business_number"].startswith("PYP-FAC-")
    warehouse_request = _approved(gate, "warehouse")
    warehouse_response = _materialize(gate, warehouse_request)
    assert warehouse_response.status_code == 200, warehouse_response.text
    assert warehouse_response.json()["business_number"].startswith("PYP-WH-")


def test_22_second_materialization_is_idempotent(gate: Gate) -> None:
    request = _approved(gate)
    first = _materialize(gate, request)
    second = _materialize(gate, request)
    assert first.status_code == second.status_code == 200
    assert second.json()["result"] == "ALREADY_CREATED"
    assert second.json()["mutation_count"] == 0
    assert second.json()["materialized_workspace_id"] == first.json()["materialized_workspace_id"]


def test_22b_approval_hash_detects_post_approval_mutation(gate: Gate) -> None:
    request = _approved(gate)
    with SessionLocal() as db:
        model = db.get(PhysicalWorkspaceCreationRequest, request["id"])
        assert model is not None
        model.workspace_name = "Unauthorized post-approval mutation"
        db.flush()
        service = PhysicalWorkspaceCreationService(db, gate.tenant_id, gate.actor_ids["materializer"])
        with pytest.raises(HTTPException) as caught:
            service.materialize(request["id"], request["revision_version"])
        assert caught.value.status_code == 409
        assert caught.value.detail == "PHYSICAL_WORKSPACE_APPROVAL_INVALIDATED"


def test_23_failure_injection_rolls_back_workspace_and_number(gate: Gate) -> None:
    request = _approved(gate)
    with SessionLocal() as db:
        workspace_count = db.scalar(select(func.count()).select_from(EnterpriseWorkspace))
        sequence_before = db.scalar(
            select(AdminNumberSequence.next_value).where(
                AdminNumberSequence.tenant_id == gate.tenant_id,
                AdminNumberSequence.rule_code == "physical-property",
            )
        )
        service = PhysicalWorkspaceCreationService(db, gate.tenant_id, gate.actor_ids["materializer"])
        with pytest.raises(RuntimeError):
            service.materialize(
                request["id"],
                request["revision_version"],
                failure_injector=lambda _workspace: (_ for _ in ()).throw(RuntimeError("fail")),
            )
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(EnterpriseWorkspace)) == workspace_count
        assert (
            db.scalar(
                select(AdminNumberSequence.next_value).where(
                    AdminNumberSequence.tenant_id == gate.tenant_id,
                    AdminNumberSequence.rule_code == "physical-property",
                )
            )
            == sequence_before
        )


def test_24_overview_and_enterprise_explorer_include_created_workspace(gate: Gate) -> None:
    request = _approved(gate)
    created = _materialize(gate, request).json()
    overview = gate.client.get(
        f"/api/v1/physical-workspaces/{created['materialized_workspace_id']}/overview",
        headers=gate.headers["requestor"],
    )
    assert overview.status_code == 200, overview.text
    assert overview.json()["workspace_type_code"] == "property"
    assert overview.json()["creation_request_number"] == request["request_number"]
    explorer = gate.client.get("/api/v1/enterprise-structure/overview", headers=gate.headers["requestor"])
    assert explorer.status_code == 200
    assert any(item["id"] == created["materialized_workspace_id"] for item in explorer.json()["nodes"])


def test_25_audit_rbac_and_core_invariance(gate: Gate) -> None:
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(SecurityEvent)
                .where(
                    SecurityEvent.tenant_id == gate.tenant_id,
                    SecurityEvent.event_type.like("physical_workspace_creation.%"),
                )
            )
            > 0
        )
        assert _baseline(db, gate.tenant_id) == gate.baseline
        assert (
            db.scalar(
                select(func.count())
                .select_from(PhysicalWorkspaceCreationRequest)
                .where(PhysicalWorkspaceCreationRequest.tenant_id == gate.tenant_id)
            )
            > 0
        )


def test_26_cross_tenant_request_is_not_visible(gate: Gate) -> None:
    with SessionLocal() as db:
        request = db.scalar(
            select(PhysicalWorkspaceCreationRequest).where(PhysicalWorkspaceCreationRequest.tenant_id == gate.tenant_id)
        )
        assert request is not None
        other_tenant_id = db.scalar(select(func.max(UserAccount.tenant_id))) + 1
        outsider = UserAccount(
            tenant_id=gate.tenant_id,
            email=f"gate06b-outsider-{uuid4().hex[:6]}@demo.local",
            full_name="Gate 06B Outsider",
            status="active",
        )
        db.add(outsider)
        db.flush()
        assert request.id > 0
        assert other_tenant_id != gate.tenant_id
        service = PhysicalWorkspaceCreationService(db, other_tenant_id, outsider.id)
        with pytest.raises(Exception) as caught:
            service._request(request.id)
        assert "not found" in str(caught.value).lower()


@pytest.mark.skipif(SessionLocal.kw.get("bind").dialect.name != "postgresql", reason="PostgreSQL concurrency contract")
def test_27_concurrent_materialization_produces_unique_numbers_and_record_codes(gate: Gate) -> None:
    first = _approved(gate)
    second = _approved(gate)

    def materialize(request_id: int) -> tuple[str, str]:
        with SessionLocal() as db:
            result = PhysicalWorkspaceCreationService(db, gate.tenant_id, gate.actor_ids["materializer"]).materialize(
                request_id, first["revision_version"] if request_id == first["id"] else second["revision_version"]
            )
            return result.business_number, result.record_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(materialize, [first["id"], second["id"]]))
    assert len({item[0] for item in results}) == 2
    assert len({item[1] for item in results}) == 2
