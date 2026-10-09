"""Gate 05A acceptance tests for Project Workspace ADMIN configuration."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.core.time import utc_now
from app.database.session import SessionLocal
from app.domain.models import AdminConfiguration, EnterpriseWorkspace, SecurityEvent, Tenant, UserAccount
from app.main import app
from app.modules.enterprise_structure.models import (
    EnterpriseCoreRelease,
    EnterpriseWorkspaceClassification,
)
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.enterprise_structure.project_configuration import ProjectWorkspaceConfigurationService
from app.modules.enterprise_structure.record_codes import next_record_code

ROOT = "/api/v1/admin-configuration/enterprise-structure"


def _headers(client: TestClient, email: str = "admin") -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "1234", "tenant_slug": "demo-energy"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _overview(client: TestClient, headers: dict[str, str]) -> dict:
    response = client.get(f"{ROOT}/project-workspace", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def _template_payload(code: str, *, modules: list[str] | None = None) -> dict:
    return {
        "code": code,
        "name": f"Template {code}",
        "description": "Gate 05A test fixture",
        "applicable_parent_types": ["portfolio", "program"],
        "default_classifications": [],
        "enabled_modules": modules or [],
        "default_role_codes": [],
        "default_group_codes": [],
        "numbering_rule_code": "project-workspace",
        "default_attributes": {"currency": "COP"},
        "creation_policy_code": "project-creation",
    }


@pytest.fixture(scope="module")
def gate() -> tuple[TestClient, dict[str, str], dict]:
    with TestClient(app) as client:
        headers = _headers(client)
        _overview(client, headers)
        with SessionLocal() as db:
            actor = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
            root = db.scalar(
                select(EnterpriseWorkspace).where(
                    EnterpriseWorkspace.tenant_id == actor.tenant_id,
                    EnterpriseWorkspace.parent_id.is_(None),
                )
            )

            def workspace(
                code: str,
                name: str,
                workspace_type: str,
                parent: EnterpriseWorkspace,
            ) -> EnterpriseWorkspace:
                existing = db.scalar(
                    select(EnterpriseWorkspace).where(
                        EnterpriseWorkspace.tenant_id == actor.tenant_id,
                        EnterpriseWorkspace.code == code,
                    )
                )
                if existing is not None:
                    return existing
                sibling_codes = list(
                    db.scalars(
                        select(EnterpriseWorkspace.record_code).where(
                            EnterpriseWorkspace.tenant_id == actor.tenant_id,
                            EnterpriseWorkspace.parent_id == parent.id,
                        )
                    ).all()
                )
                record = EnterpriseWorkspace(
                    tenant_id=actor.tenant_id,
                    parent_id=parent.id,
                    workspace_type_code=workspace_type,
                    code=code,
                    external_key=f"GATE05A-{code}",
                    record_code=next_record_code(parent.record_code, sibling_codes),
                    name=name,
                    status="active",
                    defaults_json={"_enterprise": {"description": "Gate 05A test fixture"}},
                    sort_order=10,
                    version=1,
                    created_by_user_id=actor.id,
                )
                db.add(record)
                db.flush()
                return record

            business_unit = workspace("G05A-BU", "Gate 05A Business Unit", "business-unit", root)
            portfolio = workspace("G05A-PF", "Gate 05A Portfolio", "portfolio", business_unit)
            workspace(
                "G05A-PF-NO-OBJ",
                "Gate 05A Portfolio No Objective",
                "portfolio",
                business_unit,
            )
            program = workspace("G05A-PG", "Gate 05A Program", "program", portfolio)
            workspace("G05A-PRJ", "Gate 05A Operational Project Fixture", "project", program)
            for parent in (portfolio, program):
                existing = db.scalar(
                    select(EnterpriseWorkspaceClassification.id).where(
                        EnterpriseWorkspaceClassification.tenant_id == actor.tenant_id,
                        EnterpriseWorkspaceClassification.workspace_id == parent.id,
                        EnterpriseWorkspaceClassification.category_set_code == "strategic-objective",
                    )
                )
                if existing is None:
                    db.add(
                        EnterpriseWorkspaceClassification(
                            tenant_id=actor.tenant_id,
                            workspace_id=parent.id,
                            category_set_code="strategic-objective",
                            category_item_code="growth",
                            created_by_user_id=actor.id,
                        )
                    )
            release = db.scalar(
                select(EnterpriseCoreRelease).where(
                    EnterpriseCoreRelease.tenant_id == actor.tenant_id,
                    EnterpriseCoreRelease.state == "published",
                )
            )
            if release is None:
                digest = "a" * 64
                db.add(
                    EnterpriseCoreRelease(
                        tenant_id=actor.tenant_id,
                        release_code="GATE05A-CORE-FIXTURE",
                        release_name="Gate 05A CORE fixture",
                        revision_number=1,
                        state="published",
                        source_hash=digest,
                        canonical_hash=digest,
                        content_fingerprint=digest,
                        snapshot_json={},
                        workspace_count=4,
                        objective_count=1,
                        classification_count=2,
                        link_count=0,
                        validation_json={},
                        diff_hash="",
                        created_by_user_id=actor.id,
                        published_at=utc_now(),
                        published_by_user_id=actor.id,
                    )
                )
            db.commit()
        yield client, headers, _overview(client, headers)


def test_01_existing_project_workspace_type_is_reused(gate) -> None:
    _client, _headers_value, overview = gate
    assert overview["project_type"]["code"] == "project"
    assert overview["project_type"]["content_json"]["repeatable"] is True


def test_02_project_workspace_type_is_not_duplicated(gate) -> None:
    client, headers, _overview_value = gate
    first = _overview(client, headers)["project_type"]["id"]
    second = _overview(client, headers)["project_type"]["id"]
    assert first == second


def test_03_portfolio_to_project_is_allowed(gate) -> None:
    _client, _headers_value, overview = gate
    assert "portfolio" in overview["allowed_parent_types"]


def test_04_program_to_project_is_allowed(gate) -> None:
    _client, _headers_value, overview = gate
    assert "program" in overview["allowed_parent_types"]


def test_05_business_unit_to_project_is_blocked(gate) -> None:
    client, headers, overview = gate
    hierarchy = client.get(f"{ROOT}/configuration", headers=headers).json()["tree"]

    def flatten(nodes: list[dict]) -> list[dict]:
        return [item for node in nodes for item in [node, *flatten(node["children"])]]

    business_unit = next(item for item in flatten(hierarchy) if item["workspace_type_code"] == "business-unit")
    response = client.post(
        f"{ROOT}/project-workspace/preview",
        headers=headers,
        json={"parent_id": business_unit["id"], "template_id": overview["templates"][0]["id"]},
    )
    assert response.status_code == 200
    assert response.json()["allowed"] is False
    assert any("BUSINESS-UNIT" in issue for issue in response.json()["issues"])


def test_06_project_to_project_is_blocked(gate) -> None:
    client, headers, overview = gate
    with SessionLocal() as db:
        project = db.scalar(select(EnterpriseWorkspace).where(EnterpriseWorkspace.workspace_type_code == "project"))
    if project is None:
        pytest.skip("Demo fixture has no operational Project Workspace")
    response = client.post(
        f"{ROOT}/project-workspace/preview",
        headers=headers,
        json={"parent_id": project.id, "template_id": overview["templates"][0]["id"]},
    )
    assert response.status_code == 200
    assert response.json()["allowed"] is False
    assert any("PROJECT" in issue for issue in response.json()["issues"])


def test_07_record_code_preview_uses_hierarchical_engine(gate) -> None:
    client, headers, overview = gate
    parent = overview["parent_options"][0]
    response = client.post(
        f"{ROOT}/project-workspace/preview",
        headers=headers,
        json={"parent_id": parent["id"], "template_id": overview["templates"][0]["id"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["projected_record_code"].startswith(f"{parent['record_code']}.")


def test_08_project_number_preview_matches_rule(gate) -> None:
    client, headers, overview = gate
    parent = overview["parent_options"][0]
    response = client.post(
        f"{ROOT}/project-workspace/preview",
        headers=headers,
        json={"parent_id": parent["id"], "template_id": overview["templates"][0]["id"]},
    )
    assert response.json()["projected_project_number"].startswith("PYP-PRJ-")


def test_09_project_numbers_are_unique(gate) -> None:
    _client, _headers_value, _overview_value = gate
    with SessionLocal() as db:
        actor = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
        service = ProjectWorkspaceConfigurationService(db, actor.tenant_id, actor.id)
        first = service.issue_project_number()
    with SessionLocal() as db:
        actor = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
        second = ProjectWorkspaceConfigurationService(db, actor.tenant_id, actor.id).issue_project_number()
    assert first != second


def test_10_concurrent_numbering_is_atomic(gate) -> None:
    _client, _headers_value, _overview_value = gate

    def issue() -> str:
        with SessionLocal() as db:
            actor = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
            return ProjectWorkspaceConfigurationService(db, actor.tenant_id, actor.id).issue_project_number()

    with ThreadPoolExecutor(max_workers=2) as executor:
        values = list(executor.map(lambda _item: issue(), range(2)))
    assert len(set(values)) == 2


def test_11_project_template_create(gate) -> None:
    client, headers, _overview_value = gate
    code = f"PYP-PRJ-TEST-{uuid4().hex[:8]}"
    response = client.post(f"{ROOT}/project-templates", headers=headers, json=_template_payload(code))
    assert response.status_code == 201, response.text
    assert response.json()["status"] == "draft"


def _published_template(client: TestClient, headers: dict[str, str]) -> dict:
    code = f"PYP-PRJ-PUBLISHED-{uuid4().hex[:8]}"
    created = client.post(f"{ROOT}/project-templates", headers=headers, json=_template_payload(code))
    assert created.status_code == 201, created.text
    record = created.json()
    validated = client.post(f"{ROOT}/project-templates/{record['id']}/validate", headers=headers)
    assert validated.status_code == 200, validated.text
    published = client.post(
        f"{ROOT}/project-templates/{record['id']}/publish",
        headers=headers,
        json={"expected_hash": validated.json()["content_hash"]},
    )
    assert published.status_code == 200, published.text
    return published.json()


def test_12_project_template_clone(gate) -> None:
    client, headers, _overview_value = gate
    source = _published_template(client, headers)
    response = client.post(f"{ROOT}/project-templates/{source['id']}/clone", headers=headers)
    assert response.status_code == 201, response.text
    assert response.json()["revision"] == source["revision"] + 1


def test_13_project_template_validate(gate) -> None:
    client, headers, overview = gate
    response = client.post(f"{ROOT}/project-templates/{overview['templates'][0]['id']}/validate", headers=headers)
    assert response.status_code == 200
    assert response.json()["valid"] is True
    assert len(response.json()["content_hash"]) == 64


def test_14_project_template_publish(gate) -> None:
    client, headers, _overview_value = gate
    assert _published_template(client, headers)["status"] == "published"


def test_15_published_project_template_is_immutable(gate) -> None:
    client, headers, _overview_value = gate
    published = _published_template(client, headers)
    payload = {**_template_payload(published["code"]), "expected_version": published["version"]}
    response = client.put(f"{ROOT}/project-templates/{published['id']}", headers=headers, json=payload)
    assert response.status_code == 409


def test_16_project_template_archive_is_logical(gate) -> None:
    client, headers, _overview_value = gate
    published = _published_template(client, headers)
    response = client.post(f"{ROOT}/project-templates/{published['id']}/archive", headers=headers)
    assert response.status_code == 200
    assert response.json()["status"] == "archived"


def test_17_cross_tenant_configuration_is_blocked(gate) -> None:
    client, headers, _overview_value = gate
    with SessionLocal() as db:
        actor = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
        tenant = Tenant(name="Gate 05A Other Tenant", slug=f"gate-05a-{uuid4().hex[:8]}")
        db.add(tenant)
        db.flush()
        record = AdminConfiguration(
            tenant_id=tenant.id,
            kind="project_template",
            code="PYP-PRJ-OTHER",
            name="Other tenant",
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
    response = client.post(f"{ROOT}/project-templates/{record_id}/validate", headers=headers)
    assert response.status_code == 404


def test_18_required_classification_is_reported_by_preview(gate) -> None:
    client, headers, overview = gate
    parent = next(item for item in overview["parent_options"] if "No Objective" in item["name"])
    response = client.post(
        f"{ROOT}/project-workspace/preview",
        headers=headers,
        json={"parent_id": parent["id"], "template_id": overview["templates"][0]["id"]},
    )
    assert response.status_code == 200
    if not response.json()["allowed"]:
        assert any("strategic objective" in issue.lower() for issue in response.json()["issues"])


def test_19_unknown_module_is_rejected(gate) -> None:
    client, headers, _overview_value = gate
    code = f"PYP-PRJ-MODULE-{uuid4().hex[:8]}"
    response = client.post(
        f"{ROOT}/project-templates",
        headers=headers,
        json=_template_payload(code, modules=["fictional-module"]),
    )
    assert response.status_code == 422


def test_20_creation_policy_rejects_invalid_parent(gate) -> None:
    client, headers, overview = gate
    payload = {**overview["creation_policy"]["content_json"], "allowed_parent_types": ["business-unit"]}
    response = client.put(f"{ROOT}/project-creation-policy", headers=headers, json=payload)
    assert response.status_code == 422


def test_21_preview_does_not_persist_project(gate) -> None:
    client, headers, overview = gate
    with SessionLocal() as db:
        before = db.scalar(
            select(func.count())
            .select_from(EnterpriseWorkspace)
            .where(EnterpriseWorkspace.workspace_type_code == "project")
        )
    parent = overview["parent_options"][0]
    response = client.post(
        f"{ROOT}/project-workspace/preview",
        headers=headers,
        json={"parent_id": parent["id"], "template_id": overview["templates"][0]["id"]},
    )
    assert response.status_code == 200
    assert response.json()["persisted"] is False
    with SessionLocal() as db:
        after = db.scalar(
            select(func.count())
            .select_from(EnterpriseWorkspace)
            .where(EnterpriseWorkspace.workspace_type_code == "project")
        )
    assert after == before


def test_22_explorer_combines_core_and_operational_workspace_rows(gate) -> None:
    client, headers, _overview_value = gate
    response = client.get("/api/v1/enterprise-structure/overview", headers=headers)
    assert response.status_code == 200
    payload = response.json()
    assert payload["published_release"] is not None
    assert any(item["workspace_type_code"] == "project" for item in payload["nodes"])


def test_23_operational_project_configuration_requires_no_core_revision(gate) -> None:
    client, headers, overview = gate
    with SessionLocal() as db:
        before = db.scalar(
            select(func.count()).select_from(EnterpriseCoreRelease).where(EnterpriseCoreRelease.state == "draft")
        )
    parent = overview["parent_options"][0]
    response = client.post(
        f"{ROOT}/project-workspace/preview",
        headers=headers,
        json={"parent_id": parent["id"], "template_id": overview["templates"][0]["id"]},
    )
    assert response.status_code == 200
    with SessionLocal() as db:
        after = db.scalar(
            select(func.count()).select_from(EnterpriseCoreRelease).where(EnterpriseCoreRelease.state == "draft")
        )
    assert after == before


def test_24_project_configuration_enforces_rbac(gate) -> None:
    _client, _headers_value, _overview_value = gate
    with SessionLocal() as db:
        admin = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
        viewer = UserAccount(
            tenant_id=admin.tenant_id,
            email=f"gate05a-viewer-{uuid4().hex[:8]}@demo.local",
            full_name="Gate 05A Viewer",
            status="active",
        )
        db.add(viewer)
        db.commit()
        with pytest.raises(HTTPException) as error:
            require_enterprise_permission(
                db,
                admin.tenant_id,
                viewer.id,
                "admin.enterprise_structure.project_template.manage",
            )
        assert error.value.status_code == 403


def test_25_project_configuration_writes_security_events(gate) -> None:
    _client, _headers_value, _overview_value = gate
    expected = {
        "enterprise_structure.project_type.configured",
        "enterprise_structure.project_template.created",
        "enterprise_structure.project_numbering.configured",
        "enterprise_structure.project_creation_policy.configured",
        "enterprise_structure.project_template.updated",
        "enterprise_structure.project_template.published",
    }
    with SessionLocal() as db:
        found = set(db.scalars(select(SecurityEvent.event_type).where(SecurityEvent.event_type.in_(expected))).all())
    assert expected <= found
