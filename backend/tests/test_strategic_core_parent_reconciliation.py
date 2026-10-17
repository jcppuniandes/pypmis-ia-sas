"""Controlled CORE reconciliation, using disposable structural fixtures only.

These are not Project Creation lifecycle UAT cases: the focused fixture models
rows that already exist legitimately after an older CORE publication.
"""

import copy

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from tests.test_enterprise_structure_revisions import _seed, _service_as, _workspace
from tests.test_strategic_final_uat_core_project_authority import _live_project_after_publication, no_dml

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.domain.models import (
    EnterpriseWorkspace,
    PermissionCatalog,
    SecurityAccessAssignment,
    SecurityRole,
    SecurityRolePermission,
    Tenant,
)
from app.modules.enterprise_structure import router_admin
from app.modules.enterprise_structure.models import EnterpriseCoreRelease, EnterpriseWorkspaceClassification
from app.modules.enterprise_structure.schemas import (
    RevisionApprovalRequest,
    RevisionParentReconciliationRequest,
    RevisionPublishRequest,
    RevisionWorkspaceUpdate,
)
from app.modules.project_creation.models import ProjectCreationRequest


@pytest.fixture
def core():
    db, service, published = _seed()
    try:
        yield db, service, published
    finally:
        db.close()


def _new_parent(db, service, *, portfolio=None, key="PRG-MISSING"):
    portfolio = portfolio or db.scalar(select(EnterpriseWorkspace).where(EnterpriseWorkspace.external_key == "PF-TWO"))
    segment = 1 + db.scalar(
        select(func.count()).select_from(EnterpriseWorkspace).where(EnterpriseWorkspace.parent_id == portfolio.id)
    )
    parent = _workspace(
        service.tenant_id,
        service.actor_id,
        key,
        key,
        f"{portfolio.record_code}.{segment:02d}",
        "Existing parent absent from historical CORE",
        "program",
        portfolio.id,
        10,
    )
    db.add(parent)
    db.flush()
    db.add(
        EnterpriseWorkspaceClassification(
            tenant_id=service.tenant_id,
            workspace_id=parent.id,
            category_set_code="strategic-objective",
            category_item_code="growth",
            created_by_user_id=service.actor_id,
        )
    )
    db.commit()
    return parent


def _payload(*identities):
    return RevisionParentReconciliationRequest(parent_workspace_ids=list(identities))


def _live_state(db):
    return [
        (
            row.id,
            row.parent_id,
            row.external_key,
            row.record_code,
            row.status,
            row.version,
            copy.deepcopy(row.defaults_json),
        )
        for row in db.scalars(select(EnterpriseWorkspace).order_by(EnterpriseWorkspace.id))
    ]


def test_missing_parent_default_clone_stays_409_before_dml(core):
    db, service, published = core
    parent = _new_parent(db, service)
    project = _live_project_after_publication(db, service, parent=parent)
    with no_dml(db), pytest.raises(HTTPException) as error:
        service.create_revision(published.id)
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "PROJECT_PARENT_RECONCILIATION_REQUIRED"
    assert service.repository.latest_draft_release() is None
    assert project.status == "pending"


def test_parent_diagnosis_is_read_only_and_exact(core):
    db, service, published = core
    parent = _new_parent(db, service)
    project = _live_project_after_publication(db, service, parent=parent)
    with no_dml(db):
        diagnosis = service.parent_reconciliation(published.id)
    assert diagnosis.project_workspace_ids == [project.id]
    assert [item.workspace_id for item in diagnosis.required_parent_workspaces] == [parent.id]
    item = diagnosis.required_parent_workspaces[0]
    assert item.external_key == parent.external_key
    assert item.parent_workspace_id == parent.parent_id
    assert item.record_code == parent.record_code
    assert service.repository.latest_draft_release() is None


def test_exact_parent_clone_validate_approve_publish_preserves_project_and_history(core):
    db, service, published = core
    parent = _new_parent(db, service)
    project = _live_project_after_publication(db, service, parent=parent)
    historical = copy.deepcopy(published.snapshot_json)
    historical_hash = published.content_fingerprint
    original_project = (project.id, project.external_key, project.record_code, project.status, project.parent_id)
    live_before = _live_state(db)
    draft = service.reconcile_live_parents(
        published.id, _payload(parent.id), expected_version=published.revision_version
    )
    assert draft.state == "draft"
    assert draft.previous_release_id == published.id
    assert _live_state(db) == live_before
    assert published.snapshot_json == historical
    assert published.content_fingerprint == historical_hash
    assert (
        next(item for item in draft.workspaces if item.technical_id == parent.id).workspace_key == parent.external_key
    )
    assert next(item for item in draft.workspaces if item.technical_id == project.id).parent_key == parent.external_key
    validation = service.validate_revision(draft.id)
    assert validation.valid, validation.errors
    service.approve_revision(
        draft.id, RevisionApprovalRequest(draft_hash=validation.draft_hash, diff_hash=validation.diff_hash)
    )
    publisher = _service_as(db, service, "controlled.parent.publisher@gate04.local")
    successor = publisher.publish_revision(
        draft.id, RevisionPublishRequest(draft_hash=validation.draft_hash, diff_hash=validation.diff_hash)
    )
    assert successor.state == "published"
    assert (
        project.id,
        project.external_key,
        project.record_code,
        project.status,
        project.parent_id,
    ) == original_project
    assert published.snapshot_json == historical
    assert published.content_fingerprint == historical_hash
    assert db.scalar(select(func.count()).select_from(ProjectCreationRequest)) == 0


@pytest.mark.parametrize("wrong_identity", ["foreign", "invented", "project", "unrelated", "duplicate"])
def test_bad_parent_identities_rejected_before_any_dml(core, wrong_identity):
    db, service, published = core
    parent = _new_parent(db, service)
    project = _live_project_after_publication(db, service, parent=parent)
    supplied = [parent.id]
    expected_status = 409
    expected_code = "PARENT_RECONCILIATION_SCOPE_MISMATCH"
    if wrong_identity == "foreign":
        tenant = Tenant(name="Other isolated tenant", slug="core-parent-foreign", base_currency="COP")
        db.add(tenant)
        db.flush()
        other = _workspace(tenant.id, service.actor_id, "FOREIGN", "FOREIGN", "99", "Foreign", "portfolio", None, 0)
        db.add(other)
        db.commit()
        supplied.append(other.id)
        expected_status, expected_code = 404, "PARENT_WORKSPACE_NOT_FOUND"
    elif wrong_identity == "invented":
        supplied.append(987654321)
        expected_status, expected_code = 404, "PARENT_WORKSPACE_NOT_FOUND"
    elif wrong_identity == "project":
        supplied.append(project.id)
        expected_code = "PROJECT_PARENT_IDENTITY_REQUIRED"
    elif wrong_identity == "unrelated":
        unrelated = _new_parent(db, service, key="PRG-UNRELATED")
        supplied.append(unrelated.id)
    else:
        supplied.append(parent.id)
        expected_status, expected_code = 422, "UNIQUE_EXISTING_PARENT_IDS_REQUIRED"
    before = _live_state(db)
    with no_dml(db), pytest.raises(HTTPException) as error:
        service.reconcile_live_parents(published.id, _payload(*supplied), expected_version=published.revision_version)
    assert error.value.status_code == expected_status
    assert error.value.detail["code"] == expected_code
    assert _live_state(db) == before
    assert service.repository.latest_draft_release() is None


def test_every_missing_ancestor_must_be_explicit_no_invented_ancestry(core):
    db, service, published = core
    business_unit = db.scalar(select(EnterpriseWorkspace).where(EnterpriseWorkspace.external_key == "BU-CORE"))
    portfolio = _workspace(
        service.tenant_id,
        service.actor_id,
        "PF-MISSING",
        "PF-MISSING",
        "01.01.03",
        "Existing portfolio",
        "portfolio",
        business_unit.id,
        30,
    )
    db.add(portfolio)
    db.flush()
    db.add(
        EnterpriseWorkspaceClassification(
            tenant_id=service.tenant_id,
            workspace_id=portfolio.id,
            category_set_code="strategic-objective",
            category_item_code="growth",
            created_by_user_id=service.actor_id,
        )
    )
    db.commit()
    parent = _new_parent(db, service, portfolio=portfolio)
    _live_project_after_publication(db, service, parent=parent)
    with no_dml(db), pytest.raises(HTTPException) as error:
        service.reconcile_live_parents(published.id, _payload(parent.id), expected_version=published.revision_version)
    assert error.value.detail["code"] == "PROJECT_PARENT_RECONCILIATION_REQUIRED"
    assert set(error.value.detail["required_parent_workspace_ids"]) == {portfolio.id, parent.id}
    draft = service.reconcile_live_parents(
        published.id, _payload(portfolio.id, parent.id), expected_version=published.revision_version
    )
    assert service.validate_revision(draft.id).valid


def test_existing_draft_reconciliation_invalidates_approval_preserves_edits_and_replay(core):
    db, service, published = core
    draft = service.create_revision(published.id)
    edited = service.edit_workspace(
        draft.id,
        "PF-TWO",
        RevisionWorkspaceUpdate(description="Keep my draft edit"),
        expected_version=draft.revision_version,
    )
    validation = service.validate_revision(draft.id)
    approved = service.approve_revision(
        draft.id, RevisionApprovalRequest(draft_hash=validation.draft_hash, diff_hash=validation.diff_hash)
    )
    assert approved.approved_at is not None
    parent = _new_parent(db, service)
    _live_project_after_publication(db, service, parent=parent)
    before = _live_state(db)
    with no_dml(db), pytest.raises(HTTPException) as error:
        service.create_revision(published.id)
    assert error.value.detail["code"] == "PROJECT_PARENT_RECONCILIATION_REQUIRED"
    with no_dml(db), pytest.raises(HTTPException) as conflict:
        service.reconcile_live_parents(draft.id, _payload(parent.id), expected_version=edited.revision_version)
    assert conflict.value.detail["reason"] == "REVISION_VERSION_CONFLICT"
    reconciled = service.reconcile_live_parents(
        draft.id, _payload(parent.id), expected_version=approved.revision_version
    )
    assert reconciled.approved_at is None
    assert reconciled.validation is None
    assert reconciled.validated_at is None
    assert reconciled.draft_hash != approved.draft_hash
    assert (
        next(item for item in reconciled.workspaces if item.workspace_key == "PF-TWO").description
        == "Keep my draft edit"
    )
    assert _live_state(db) == before
    with no_dml(db):
        replay = service.reconcile_live_parents(
            draft.id, _payload(parent.id), expected_version=reconciled.revision_version
        )
    assert replay.revision_version == reconciled.revision_version


def test_published_entrypoint_never_silently_edits_existing_draft(core):
    db, service, published = core
    draft = service.create_revision(published.id)
    parent = _new_parent(db, service)
    _live_project_after_publication(db, service, parent=parent)
    with no_dml(db), pytest.raises(HTTPException) as error:
        service.reconcile_live_parents(published.id, _payload(parent.id), expected_version=published.revision_version)
    assert error.value.detail == {"code": "DRAFT_ALREADY_EXISTS", "draft_release_id": draft.id}


def test_reconciliation_http_contract_requires_etag_and_existing_capabilities(core, monkeypatch):
    """HTTP wiring contract only; actual RBAC is covered by authority regression."""
    db, service, published = core
    parent = _new_parent(db, service)
    _live_project_after_publication(db, service, parent=parent)
    permissions = []

    def revision_service(_db, _tenant, _actor, permission, **_kwargs):
        permissions.append(permission)
        return service

    def require_permission(_db, _tenant, _actor, permission, **_kwargs):
        permissions.append(permission)

    monkeypatch.setattr(router_admin, "_revision_service", revision_service)
    monkeypatch.setattr(router_admin, "require_enterprise_permission", require_permission)
    app = FastAPI()
    app.include_router(router_admin.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_tenant_id] = lambda: service.tenant_id
    app.dependency_overrides[get_user_id] = lambda: service.actor_id
    prefix = f"/api/v1/admin-configuration/enterprise-structure/enterprise-core-releases/{published.id}"
    with TestClient(app) as client:
        with no_dml(db):
            assert client.get(f"{prefix}/parent-reconciliation").status_code == 200
            assert (
                client.post(f"{prefix}/reconcile-live-parents", json={"parent_workspace_ids": [parent.id]}).status_code
                == 422
            )
        response = client.post(
            f"{prefix}/reconcile-live-parents",
            headers={"If-Match": f'"{published.revision_version}"'},
            json={"parent_workspace_ids": [parent.id]},
        )
    assert response.status_code == 200, response.text
    assert response.headers["ETag"] == f'"{response.json()["revision_version"]}"'
    assert "admin.enterprise_structure.revision.create" in permissions
    assert "admin.enterprise_structure.revision.edit" in permissions
    assert db.get(EnterpriseCoreRelease, response.json()["id"]).state == "draft"


@pytest.mark.parametrize(
    "role_code,scope,expected_status",
    [
        ("core_viewer", "organization", 403),
        ("structure_editor", "workspace", 403),
        ("structure_editor", "organization", 200),
    ],
)
def test_reconciliation_real_http_rbac_and_no_bootstrap_writes(core, role_code, scope, expected_status):
    db, service, published = core
    parent = _new_parent(db, service)
    outside_scope = _new_parent(db, service, key="PRG-OUTSIDE-READER-SCOPE")
    _live_project_after_publication(db, service, parent=parent)
    db.add(
        _workspace(
            service.tenant_id,
            service.actor_id,
            "PRJ-OUTSIDE-SCOPE",
            "PRJ-OUTSIDE-SCOPE",
            f"{outside_scope.record_code}.01",
            "Project outside reader scope",
            "project",
            outside_scope.id,
            10,
        )
    )
    db.commit()
    role = SecurityRole(tenant_id=service.tenant_id, code=role_code, name=role_code, status="active")
    db.add(role)
    db.flush()
    keys = ["admin.enterprise_structure.read"]
    if role_code == "structure_editor":
        keys.extend(["admin.enterprise_structure.revision.create", "admin.enterprise_structure.revision.edit"])
    for key in keys:
        permission = PermissionCatalog(
            key=key, resource="enterprise_structure", action=key.rsplit(".", 1)[-1], status="active"
        )
        db.add(permission)
        db.flush()
        db.add(
            SecurityRolePermission(
                tenant_id=service.tenant_id,
                role_id=role.id,
                permission_id=permission.id,
                granted_by_user_id=service.actor_id,
            )
        )
    db.add(
        SecurityAccessAssignment(
            tenant_id=service.tenant_id,
            subject_type="user",
            user_id=service.actor_id,
            role_id=role.id,
            scope_type=scope,
            workspace_id=parent.id if scope == "workspace" else None,
            granted_by_user_id=service.actor_id,
            status="active",
        )
    )
    db.commit()
    app = FastAPI()
    app.include_router(router_admin.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_tenant_id] = lambda: service.tenant_id
    app.dependency_overrides[get_user_id] = lambda: service.actor_id
    prefix = f"/api/v1/admin-configuration/enterprise-structure/enterprise-core-releases/{published.id}"
    with TestClient(app) as client:
        with no_dml(db):
            diagnostic = client.get(f"{prefix}/parent-reconciliation")
        assert diagnostic.status_code == (403 if scope == "workspace" else 200)
        if scope == "workspace":
            # A tenant-wide diagnostic must not leak live identities outside
            # the reader's assigned subtree, including parents absent in CORE.
            assert outside_scope.external_key not in diagnostic.text
            assert "missing_live_parents" not in diagnostic.text
        if expected_status == 403:
            with no_dml(db):
                result = client.post(
                    f"{prefix}/reconcile-live-parents",
                    headers={"If-Match": f'"{published.revision_version}"'},
                    json={"parent_workspace_ids": [parent.id, outside_scope.id]},
                )
        else:
            result = client.post(
                f"{prefix}/reconcile-live-parents",
                headers={"If-Match": f'"{published.revision_version}"'},
                json={"parent_workspace_ids": [parent.id, outside_scope.id]},
            )
    assert result.status_code == expected_status, result.text
    if expected_status == 403:
        assert service.repository.latest_draft_release() is None


@pytest.mark.parametrize("entrypoint", ["materialize", "publish"])
def test_concurrent_reconciled_parent_identity_change_rejected_before_dml(core, entrypoint):
    db, service, published = core
    parent = _new_parent(db, service)
    project = _live_project_after_publication(db, service, parent=parent)
    historical = copy.deepcopy(published.snapshot_json)
    draft = service.reconcile_live_parents(
        published.id, _payload(parent.id), expected_version=published.revision_version
    )
    validation = service.validate_revision(draft.id)
    assert validation.valid, validation.errors
    service.approve_revision(
        draft.id, RevisionApprovalRequest(draft_hash=validation.draft_hash, diff_hash=validation.diff_hash)
    )
    publisher = _service_as(db, service, f"publisher.parent.concurrent.{entrypoint}@gate04.local")
    release = db.get(EnterpriseCoreRelease, draft.id)
    frozen_draft = copy.deepcopy(release.snapshot_json)
    # Explicit structural-fixture concurrency, not a claimed normal USER command.
    # A stale key must never be interpreted as authority to create another parent.
    parent.external_key = "PRG-IDENTITY-REPLACED"
    db.commit()
    before = _live_state(db)
    with no_dml(db), pytest.raises(HTTPException) as error:
        if entrypoint == "materialize":
            service._materialize_snapshot(frozen_draft)
        else:
            publisher.publish_revision(
                draft.id, RevisionPublishRequest(draft_hash=validation.draft_hash, diff_hash=validation.diff_hash)
            )
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "PARENT_WORKSPACE_IDENTITY_MISMATCH"
    assert _live_state(db) == before
    assert project.parent_id == parent.id
    assert project.status == "pending"
    assert published.snapshot_json == historical
    assert release.snapshot_json == frozen_draft
    assert release.state == "draft"
