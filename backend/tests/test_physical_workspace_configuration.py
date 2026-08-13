"""Gate 06A acceptance tests for physical/geographic Workspace configuration."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database.session import SessionLocal
from app.domain.models import (
    AdminConfiguration,
    AdminNumberSequence,
    EnterpriseWorkspace,
    SecurityEvent,
    Tenant,
    UserAccount,
)
from app.main import app
from app.modules.enterprise_structure.models import EnterpriseCoreRelease
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.enterprise_structure.physical_configuration import (
    NUMBERING,
    PHYSICAL_TYPE_CODES,
    PhysicalWorkspaceConfigurationService,
)

ROOT = "/api/v1/admin-configuration/enterprise-structure"


def _headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin", "password": "1234", "tenant_slug": "demo-energy"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture(scope="module")
def gate() -> tuple[TestClient, dict[str, str], dict]:
    with TestClient(app) as client:
        headers = _headers(client)
        response = client.get(f"{ROOT}/physical-workspaces", headers=headers)
        assert response.status_code == 200, response.text
        yield client, headers, response.json()


def _type(overview: dict, code: str) -> dict:
    return next(item for item in overview["workspace_types"] if item["code"] == code)


@pytest.mark.parametrize("code", PHYSICAL_TYPE_CODES)
def test_01_06_active_workspace_types(gate, code: str) -> None:
    _client, _headers_value, overview = gate
    item = _type(overview, code)
    assert item["status"] == "published"
    assert item["content_json"]["active"] is True
    assert item["content_json"]["user_mode_enabled"] is True


def test_07_property_models_real_estate(gate) -> None:
    _client, _headers_value, overview = gate
    assert _type(overview, "property")["content_json"]["domain_description"] == "Real Estate"


def test_08_linear_asset_is_reserved(gate) -> None:
    _client, _headers_value, overview = gate
    item = _type(overview, "linear-asset")
    assert item["content_json"]["reserved"] is True
    assert item["content_json"]["creation_process_supported"] is False


def test_09_asset_is_not_a_workspace_type(gate) -> None:
    _client, _headers_value, overview = gate
    assert "asset" not in {item["code"] for item in overview["workspace_types"]}
    assert overview["exclusions"]["asset_is_workspace_type"] is False


@pytest.mark.parametrize(
    ("parent", "child"),
    [
        ("enterprise", "region"),
        ("region", "district"),
        ("district", "site"),
        ("site", "property"),
        ("property", "facility"),
        ("property", "warehouse"),
        ("facility", "warehouse"),
        ("enterprise", "property"),
    ],
)
def test_10_17_composition_rules(gate, parent: str, child: str) -> None:
    _client, _headers_value, overview = gate
    assert child in overview["composition_rules"][parent]


def test_18_warehouse_children_are_blocked(gate) -> None:
    _client, _headers_value, overview = gate
    assert overview["composition_rules"]["warehouse"] == []


def test_18b_composition_update_preserves_non_physical_children(gate) -> None:
    client, headers, _overview_value = gate
    with SessionLocal() as db:
        tenant_id = db.scalar(select(Tenant.id).where(Tenant.slug == "demo-energy"))
        enterprise = db.scalar(
            select(AdminConfiguration)
            .where(
                AdminConfiguration.tenant_id == tenant_id,
                AdminConfiguration.kind == "workspace_type",
                AdminConfiguration.code == "enterprise",
                AdminConfiguration.status == "published",
            )
            .order_by(AdminConfiguration.revision.desc())
        )
    response = client.put(
        f"{ROOT}/physical-composition/enterprise",
        headers={**headers, "If-Match": f'"{enterprise.version}"'},
        json={"allowed_children": ["region", "site", "property", "facility", "warehouse"]},
    )
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        current = db.scalar(
            select(AdminConfiguration)
            .where(
                AdminConfiguration.tenant_id == tenant_id,
                AdminConfiguration.kind == "workspace_type",
                AdminConfiguration.code == "enterprise",
                AdminConfiguration.status == "published",
            )
            .order_by(AdminConfiguration.revision.desc())
        )
        assert {"business-unit", "portfolio", "program"} <= set(current.content_json["allowed_children"])


def test_19_preview_record_code_and_property_number_is_non_persistent(gate) -> None:
    client, headers, overview = gate
    root = next(item for item in overview["parent_options"] if item["workspace_type_code"] == "enterprise")
    template = next(item for item in overview["templates"] if item["code"] == "PYP-PROP-GENERAL")
    with SessionLocal() as db:
        before = db.scalar(select(func.count()).select_from(EnterpriseWorkspace))
        counter_before = db.scalar(select(func.sum(AdminNumberSequence.next_value)))
    response = client.post(
        f"{ROOT}/physical-workspaces/preview",
        headers=headers,
        json={
            "workspace_type_code": "property",
            "parent_id": root["id"],
            "template_id": template["id"],
            "minimal_attributes": {"name": "Synthetic Property"},
        },
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["allowed"] is True
    assert payload["projected_record_code"].startswith(f"{root['record_code']}.")
    assert payload["projected_business_number"].startswith("PYP-PROP-")
    assert payload["persisted"] is False
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(EnterpriseWorkspace)) == before
        assert db.scalar(select(func.sum(AdminNumberSequence.next_value))) == counter_before


@pytest.mark.parametrize(
    ("type_code", "prefix"),
    [("facility", "PYP-FAC-"), ("warehouse", "PYP-WH-")],
)
def test_20_21_business_number_previews(gate, type_code: str, prefix: str) -> None:
    client, headers, overview = gate
    root = next(item for item in overview["parent_options"] if item["workspace_type_code"] == "enterprise")
    response = client.post(
        f"{ROOT}/physical-workspaces/preview",
        headers=headers,
        json={"workspace_type_code": type_code, "parent_id": root["id"], "minimal_attributes": {"name": "Synthetic"}},
    )
    assert response.status_code == 200
    assert response.json()["projected_business_number"].startswith(prefix)


def test_22_invalid_composition_is_reported(gate) -> None:
    client, headers, overview = gate
    root = next(item for item in overview["parent_options"] if item["workspace_type_code"] == "enterprise")
    response = client.post(
        f"{ROOT}/physical-workspaces/preview",
        headers=headers,
        json={"workspace_type_code": "district", "parent_id": root["id"], "minimal_attributes": {"name": "District"}},
    )
    assert response.status_code == 200
    assert response.json()["allowed"] is False


def test_23_reserved_linear_asset_cannot_be_previewed(gate) -> None:
    client, headers, overview = gate
    root = next(item for item in overview["parent_options"] if item["workspace_type_code"] == "enterprise")
    response = client.post(
        f"{ROOT}/physical-workspaces/preview",
        headers=headers,
        json={"workspace_type_code": "linear_asset", "parent_id": root["id"], "minimal_attributes": {"name": "Road"}},
    )
    assert response.status_code == 409


def test_24_templates_are_seeded_as_draft(gate) -> None:
    _client, _headers_value, overview = gate
    assert {item["code"] for item in overview["templates"]} >= {
        "PYP-PROP-GENERAL",
        "PYP-FAC-GENERAL",
        "PYP-FAC-BUILDING",
        "PYP-FAC-INDUSTRIAL",
        "PYP-WH-GENERAL",
    }
    assert all(item["status"] == "draft" for item in overview["templates"])


def test_25_template_validate_publish_archive_is_isolated(gate) -> None:
    client, headers, _overview_value = gate
    code = f"PYP-PROP-TEST-{uuid4().hex[:8]}"
    created = client.post(
        f"{ROOT}/physical-templates",
        headers=headers,
        json={"code": code, "name": code, "workspace_type_code": "property", "applicable_parent_types": ["enterprise"]},
    )
    assert created.status_code == 201, created.text
    validated = client.post(f"{ROOT}/physical-templates/{created.json()['id']}/validate", headers=headers)
    assert validated.status_code == 200 and validated.json()["valid"] is True
    with SessionLocal() as db:
        template = db.get(AdminConfiguration, created.json()["id"])
        other_actor = db.scalar(
            select(UserAccount).where(
                UserAccount.tenant_id == template.tenant_id,
                UserAccount.id != template.created_by_user_id,
                UserAccount.status == "active",
            )
        )
        assert other_actor is not None
        template.created_by_user_id = other_actor.id
        db.commit()
    published = client.post(
        f"{ROOT}/physical-templates/{created.json()['id']}/publish",
        headers=headers,
        json={"expected_hash": validated.json()["content_hash"]},
    )
    assert published.status_code == 200 and published.json()["status"] == "published"
    archived = client.post(f"{ROOT}/physical-templates/{created.json()['id']}/archive", headers=headers)
    assert archived.status_code == 200 and archived.json()["status"] == "archived"


def test_25b_template_publish_enforces_four_eyes(gate) -> None:
    client, headers, _overview_value = gate
    code = f"PYP-WH-SOD-{uuid4().hex[:8]}"
    created = client.post(
        f"{ROOT}/physical-templates",
        headers=headers,
        json={
            "code": code,
            "name": code,
            "workspace_type_code": "warehouse",
            "applicable_parent_types": ["enterprise"],
        },
    )
    assert created.status_code == 201
    validated = client.post(f"{ROOT}/physical-templates/{created.json()['id']}/validate", headers=headers)
    response = client.post(
        f"{ROOT}/physical-templates/{created.json()['id']}/publish",
        headers=headers,
        json={"expected_hash": validated.json()["content_hash"]},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["reason"] == "FOUR_EYES_VIOLATION"


def test_26_creation_policies_are_draft(gate) -> None:
    _client, _headers_value, overview = gate
    assert len(overview["creation_policies"]) == 3
    assert all(item["status"] == "draft" for item in overview["creation_policies"])
    assert all(item["content_json"]["creation_process_implemented"] is False for item in overview["creation_policies"])


@pytest.mark.parametrize("code", PHYSICAL_TYPE_CODES)
def test_27_32_workspace_attributes_are_configured(gate, code: str) -> None:
    _client, _headers_value, overview = gate
    assert len(_type(overview, code)["content_json"]["workspace_attributes"]) >= 6


def test_33_cross_relationship_contract(gate) -> None:
    _client, _headers_value, overview = gate
    pairs = {(item["source"], item["target"]) for item in overview["relationship_contract"]}
    assert pairs == {("project", "property"), ("project", "facility"), ("project", "warehouse")}


def test_34_cross_tenant_configuration_is_blocked(gate) -> None:
    client, headers, _overview_value = gate
    with SessionLocal() as db:
        actor = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
        tenant = Tenant(name="Gate 06A Other", slug=f"gate-06a-{uuid4().hex[:8]}")
        db.add(tenant)
        db.flush()
        record = AdminConfiguration(
            tenant_id=tenant.id,
            kind="physical_template",
            code="PYP-WH-OTHER",
            name="Other",
            status="draft",
            revision=1,
            version=1,
            content_json={},
            content_hash="0" * 64,
            created_by_user_id=actor.id,
        )
        db.add(record)
        db.commit()
        record_id = record.id
    response = client.post(f"{ROOT}/physical-templates/{record_id}/validate", headers=headers)
    assert response.status_code == 404


def test_35_rbac_permissions_exist_and_viewer_is_blocked(gate) -> None:
    _client, _headers_value, _overview_value = gate
    with SessionLocal() as db:
        admin = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
        viewer = UserAccount(
            tenant_id=admin.tenant_id,
            email=f"g06a-{uuid4().hex[:8]}@demo.local",
            full_name="Gate 06A Viewer",
            status="active",
        )
        db.add(viewer)
        db.commit()
        with pytest.raises(HTTPException) as error:
            require_enterprise_permission(db, admin.tenant_id, viewer.id, "admin.enterprise_structure.property.manage")
        assert error.value.status_code == 403


def test_36_audit_events_are_written(gate) -> None:
    client, headers, overview = gate
    property_type = _type(overview, "property")
    response = client.post(
        f"{ROOT}/physical-workspaces/property/configure",
        headers={**headers, "If-Match": f'"{property_type["version"]}"'},
    )
    assert response.status_code == 200
    expected = {
        "enterprise_structure.property_type_configured",
        "enterprise_structure.physical_template_created",
        "enterprise_structure.physical_numbering_updated",
        "enterprise_structure.physical_creation_policy_updated",
    }
    with SessionLocal() as db:
        found = set(db.scalars(select(SecurityEvent.event_type).where(SecurityEvent.event_type.in_(expected))).all())
    assert expected <= found


def test_37_numbering_is_unique_and_concurrent(gate) -> None:
    _client, _headers_value, _overview_value = gate
    if SessionLocal.kw["bind"].dialect.name != "postgresql":
        pytest.skip("PostgreSQL concurrency coverage")
    with SessionLocal() as db:
        actor = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
        before = db.scalar(
            select(AdminNumberSequence.next_value).where(
                AdminNumberSequence.tenant_id == actor.tenant_id,
                AdminNumberSequence.rule_code == NUMBERING["property"][0],
                AdminNumberSequence.scope_key == "tenant",
            )
        )

    def issue() -> str:
        with SessionLocal() as db:
            actor = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
            return PhysicalWorkspaceConfigurationService(db, actor.tenant_id, actor.id).issue_business_number(
                "property"
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        values = list(executor.map(lambda _item: issue(), range(2)))
    assert len(set(values)) == 2
    with SessionLocal() as db:
        actor = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
        after = db.scalar(
            select(AdminNumberSequence.next_value).where(
                AdminNumberSequence.tenant_id == actor.tenant_id,
                AdminNumberSequence.rule_code == NUMBERING["property"][0],
                AdminNumberSequence.scope_key == "tenant",
            )
        )
    assert after == before + 2


def test_38_baseline_has_no_real_physical_instances_or_core_draft(gate) -> None:
    _client, _headers_value, overview = gate
    before = int(overview["summary"]["real_instances"])
    with SessionLocal() as db:
        tenant_id = db.scalar(select(Tenant.id).where(Tenant.slug == "demo-energy"))
        assert (
            db.scalar(
                select(func.count()).select_from(EnterpriseCoreRelease).where(EnterpriseCoreRelease.state == "draft")
            )
            == 0
        )
        after = db.scalar(
            select(func.count())
            .select_from(EnterpriseWorkspace)
            .where(
                EnterpriseWorkspace.tenant_id == tenant_id,
                EnterpriseWorkspace.workspace_type_code.in_(PHYSICAL_TYPE_CODES),
            )
        )
        assert after == before
        assert all(
            (
                current := db.scalar(
                    select(AdminNumberSequence.next_value).where(AdminNumberSequence.rule_code == rule_code)
                )
            )
            is not None
            and current >= 1
            for rule_code, _prefix_value in NUMBERING.values()
        )
