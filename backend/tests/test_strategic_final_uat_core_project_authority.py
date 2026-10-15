"""CORE commands cannot replace Project Creation/Initialization/Activation.

All databases are disposable SQLite memory fixtures. Historical canonical
Projects deliberately have no creation/initialization records: adopting and
reading them remains supported, but CORE cannot create or change live states.
"""

import copy
from contextlib import contextmanager

import pytest
from fastapi import HTTPException
from sqlalchemy import event, func, select
from tests.test_enterprise_structure_revisions import _seed, _service_as, _workspace

from app.core.time import utc_now
from app.domain.models import EnterpriseWorkspace, Tenant
from app.main import app as _registered_models  # noqa: F401 -- metadata only, no lifespan/startup/database access
from app.modules.enterprise_structure.models import EnterpriseCoreRelease, EnterpriseWorkspaceClassification
from app.modules.enterprise_structure.revisions import _snapshot_hash
from app.modules.enterprise_structure.schemas import (
    RevisionApprovalRequest,
    RevisionPublishRequest,
    RevisionRollbackRequest,
    RevisionWorkspaceCreate,
    RevisionWorkspaceUpdate,
)
from app.modules.project_creation.models import ProjectCreationRequest
from app.modules.project_workspace_initialization.models import ProjectWorkspaceInitialization


@pytest.fixture
def core():
    db, service, published = _seed(with_historical_project=True)
    try:
        yield db, service, published
    finally:
        db.close()


@contextmanager
def no_dml(db):
    """Inspect emitted SQL, not only final row counts after rollback."""
    statements = []

    def observe(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().split(maxsplit=1)[0].upper() in {"INSERT", "UPDATE", "DELETE"}:
            statements.append(statement)

    bind = db.get_bind()
    event.listen(bind, "before_cursor_execute", observe)
    try:
        yield
    finally:
        event.remove(bind, "before_cursor_execute", observe)
        assert statements == [], statements


def _snapshot(service, release):
    return service._normalized_snapshot(release)


def _add_legacy_project(snapshot, *, status="active", key="PRJ-BYPASS", identity=None):
    snapshot["workspaces"].append(
        {
            "id": identity,
            "external_key": key,
            "parent_external_key": "PF-TWO",
            "workspace_type_code": "project",
            "workspace_type": "project",
            "code": "PRJ-BYPASS",
            "record_code": "01.01.02.01",
            "name": "Legacy approved bypass candidate",
            "status": status,
            "sort_order": 10,
        }
    )
    snapshot["classifications"].append(
        {"workspace_external_key": key, "category_set_code": "strategic-objective", "category_item_code": "growth"}
    )


def _historically_approved_draft(db, service, published, mutate):
    """Simulate a pre-hardening persisted draft, not a new public command."""
    draft = service.create_revision(published.id)
    release = db.get(EnterpriseCoreRelease, draft.id)
    snapshot = _snapshot(service, release)
    mutate(snapshot)
    release.snapshot_json = snapshot
    release.content_fingerprint = _snapshot_hash(release.release_code, snapshot, release.release_name)
    difference = service.compare_revision(release.id)
    release.diff_hash = difference.diff_hash
    release.validation_json = {"valid": True}
    release.validated_draft_hash = release.content_fingerprint
    release.approved_at = utc_now()
    release.approved_by_user_id = service.actor_id
    release.approved_draft_hash = release.content_fingerprint
    release.approved_diff_hash = difference.diff_hash
    db.commit()
    publisher = _service_as(db, service, "publisher.prehardening@gate04.local")
    return (
        release,
        publisher,
        RevisionPublishRequest(draft_hash=release.content_fingerprint, diff_hash=difference.diff_hash),
    )


@pytest.mark.parametrize("type_code", ["project", "PROJECT", " ProJect "])
@pytest.mark.parametrize("status", ["draft", "pending", "active", "inactive", "archived"])
def test_core_add_project_is_denied_before_draft_mutation_or_dml(core, type_code, status):
    db, service, published = core
    draft = service.create_revision(published.id)
    before = copy.deepcopy(db.get(EnterpriseCoreRelease, draft.id).snapshot_json)
    with no_dml(db), pytest.raises(HTTPException) as caught:
        service.add_workspace(
            draft.id,
            RevisionWorkspaceCreate(name="Bypass", workspace_type_code=type_code, parent_key="PF-TWO", status=status),
            expected_version=draft.revision_version,
        )
    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == "PROJECT_CREATION_PROCESS_REQUIRED"
    assert db.get(EnterpriseCoreRelease, draft.id).snapshot_json == before
    assert service.get_revision(draft.id).revision_version == draft.revision_version


@pytest.mark.parametrize("requested", ["draft", "inactive", "archived"])
def test_core_edit_project_status_denied_before_any_mutation(core, requested):
    db, service, published = core
    draft = service.create_revision(published.id)
    before = copy.deepcopy(db.get(EnterpriseCoreRelease, draft.id).snapshot_json)
    with no_dml(db), pytest.raises(HTTPException) as caught:
        service.edit_workspace(
            draft.id,
            "PRJ-HISTORY",
            RevisionWorkspaceUpdate(name="Must not leak", status=requested),
            expected_version=draft.revision_version,
        )
    assert caught.value.detail["code"] == "PROJECT_WORKSPACE_LIFECYCLE_REQUIRED"
    assert db.get(EnterpriseCoreRelease, draft.id).snapshot_json == before


def test_core_archive_project_is_a_guarded_lifecycle_change(core):
    db, service, published = core
    draft = service.create_revision(published.id)
    with no_dml(db), pytest.raises(HTTPException) as caught:
        service.archive_workspace(draft.id, "PRJ-HISTORY", expected_version=draft.revision_version)
    assert caught.value.detail["code"] == "PROJECT_WORKSPACE_LIFECYCLE_REQUIRED"


@pytest.mark.parametrize("status", ["draft", "pending", "active", "inactive", "archived"])
def test_legacy_draft_project_is_invalid_and_cannot_materialize(core, status):
    db, service, published = core
    draft = service.create_revision(published.id)
    release = db.get(EnterpriseCoreRelease, draft.id)
    snapshot = _snapshot(service, release)
    _add_legacy_project(snapshot, status=status)
    release.snapshot_json = snapshot
    db.commit()
    validation = service.validate_revision(draft.id)
    assert not validation.valid
    assert not validation.checks["project_lifecycle_authority"]
    with no_dml(db), pytest.raises(HTTPException) as caught:
        service._materialize_snapshot(snapshot)
    assert caught.value.detail["code"] == "PROJECT_CREATION_PROCESS_REQUIRED"
    assert db.scalar(select(EnterpriseWorkspace).where(EnterpriseWorkspace.external_key == "PRJ-BYPASS")) is None


@pytest.mark.parametrize(
    "mutation,reason",
    [
        (lambda snapshot: _add_legacy_project(snapshot), "PROJECT_CREATION_PROCESS_REQUIRED"),
        (
            lambda snapshot: next(w for w in snapshot["workspaces"] if w["external_key"] == "PRJ-HISTORY").update(
                status="inactive"
            ),
            "PROJECT_WORKSPACE_LIFECYCLE_REQUIRED",
        ),
        (
            lambda snapshot: next(w for w in snapshot["workspaces"] if w["external_key"] == "PRJ-HISTORY").update(
                workspace_type_code="program"
            ),
            "PROJECT_WORKSPACE_TYPE_IMMUTABLE",
        ),
        (
            lambda snapshot: next(w for w in snapshot["workspaces"] if w["external_key"] == "PRG-HISTORY").update(
                workspace_type_code="project"
            ),
            "PROJECT_CREATION_PROCESS_REQUIRED",
        ),
    ],
)
def test_previously_approved_bypass_cannot_publish_any_dml(core, mutation, reason):
    db, service, published = core
    draft, publisher, payload = _historically_approved_draft(db, service, published, mutation)
    before = copy.deepcopy(draft.snapshot_json)
    with no_dml(db), pytest.raises(HTTPException) as caught:
        publisher.publish_revision(draft.id, payload)
    assert caught.value.status_code == 409
    assert caught.value.detail["code"] == reason
    assert published.state == "published"
    assert draft.state == "draft"
    assert draft.snapshot_json == before


def test_omitted_live_project_cannot_be_archived_by_materializer(core):
    db, service, published = core
    snapshot = _snapshot(service, published)
    snapshot["workspaces"] = [w for w in snapshot["workspaces"] if w["external_key"] != "PRJ-HISTORY"]
    with no_dml(db), pytest.raises(HTTPException) as caught:
        service._materialize_snapshot(snapshot)
    assert caught.value.detail["code"] == "PROJECT_WORKSPACE_LIFECYCLE_REQUIRED"


def test_user_lifecycle_change_after_approval_cannot_be_reverted_by_core(core):
    db, service, published = core
    draft, publisher, payload = _historically_approved_draft(db, service, published, lambda _: None)
    row = db.scalar(select(EnterpriseWorkspace).where(EnterpriseWorkspace.external_key == "PRJ-HISTORY"))
    # Simulated concurrent domain state; this is not claimed as a USER lifecycle E2E.
    row.status = "inactive"
    db.commit()
    with no_dml(db), pytest.raises(HTTPException) as caught:
        publisher.publish_revision(draft.id, payload)
    assert caught.value.detail["code"] == "PROJECT_WORKSPACE_LIFECYCLE_REQUIRED"
    assert row.status == "inactive"


def test_materializer_rejects_foreign_snapshot_before_any_dml(core):
    db, service, published = core
    snapshot = _snapshot(service, published)
    snapshot["tenant"]["id"] = 999
    with no_dml(db), pytest.raises(HTTPException) as caught:
        service._materialize_snapshot(snapshot)
    assert caught.value.detail["code"] == "CROSS_TENANT_CORE_SNAPSHOT"


def test_foreign_tenant_project_id_and_key_cannot_authorize_creation(core):
    db, service, published = core
    foreign = Tenant(name="Foreign", slug="foreign-core-uat", base_currency="COP")
    db.add(foreign)
    db.flush()
    row = _workspace(
        foreign.id, service.actor_id, "PRJ-FOREIGN", "PRJ-FOREIGN", "99", "Foreign Project", "project", None, 0
    )
    db.add(row)
    db.commit()
    snapshot = _snapshot(service, published)
    _add_legacy_project(snapshot, key=row.external_key, identity=row.id)
    with no_dml(db), pytest.raises(HTTPException) as caught:
        service._materialize_snapshot(snapshot)
    assert caught.value.detail["code"] == "PROJECT_CREATION_PROCESS_REQUIRED"
    assert row.status == "active"
    assert row.tenant_id == foreign.id


@pytest.mark.parametrize("entrypoint", ["materialize", "publish"])
def test_project_canonical_key_cannot_carry_another_tenants_id(core, entrypoint):
    db, service, published = core
    foreign = Tenant(name="Foreign identity", slug="foreign-core-identity", base_currency="COP")
    db.add(foreign)
    db.flush()
    foreign_row = _workspace(
        foreign.id, service.actor_id, "PRJ-FOREIGN", "PRJ-FOREIGN", "99", "Foreign Project", "project", None, 0
    )
    db.add(foreign_row)
    db.commit()

    def spoof(snapshot):
        next(w for w in snapshot["workspaces"] if w["external_key"] == "PRJ-HISTORY")["id"] = foreign_row.id

    if entrypoint == "publish":
        draft, publisher, payload = _historically_approved_draft(db, service, published, spoof)

        def command():
            return publisher.publish_revision(draft.id, payload)
    else:
        snapshot = _snapshot(service, published)
        spoof(snapshot)

        def command():
            return service._materialize_snapshot(snapshot)

    with no_dml(db), pytest.raises(HTTPException) as caught:
        command()
    assert caught.value.detail["code"] == "PROJECT_WORKSPACE_IDENTITY_MISMATCH"
    assert foreign_row.tenant_id == foreign.id
    assert foreign_row.status == "active"


def test_historical_project_adoption_publish_replay_and_rollback_preserve_identity_and_status(core):
    db, service, published = core
    original_snapshot = copy.deepcopy(published.snapshot_json)
    row = db.scalar(select(EnterpriseWorkspace).where(EnterpriseWorkspace.external_key == "PRJ-HISTORY"))
    original_id = row.id
    draft = service.create_revision(published.id)
    service.edit_workspace(
        draft.id,
        "PRJ-HISTORY",
        RevisionWorkspaceUpdate(description="Metadata only", status="active"),
        expected_version=draft.revision_version,
    )
    validation = service.validate_revision(draft.id)
    assert validation.valid, validation.errors
    service.approve_revision(
        draft.id, RevisionApprovalRequest(draft_hash=validation.draft_hash, diff_hash=validation.diff_hash)
    )
    publisher = _service_as(db, service, "publisher.historical@gate04.local")
    payload = RevisionPublishRequest(draft_hash=validation.draft_hash, diff_hash=validation.diff_hash)
    successor = publisher.publish_revision(draft.id, payload)
    assert row.defaults_json["_enterprise"]["description"] == "Metadata only"
    with no_dml(db):
        assert publisher.publish_revision(draft.id, payload).id == successor.id
        assert publisher.get_revision(published.id).content_fingerprint == published.content_fingerprint
        assert db.scalar(select(func.count()).select_from(ProjectCreationRequest)) == 0
        assert db.scalar(select(func.count()).select_from(ProjectWorkspaceInitialization)) == 0
    restored = publisher.rollback_revision(
        successor.id, RevisionRollbackRequest(reason="Historical metadata rollback", confirm=True)
    )
    assert restored.id == published.id
    assert row.id == original_id
    assert row.status == "active"
    assert row.workspace_type_code == "project"
    assert published.snapshot_json == original_snapshot


def test_rollback_cannot_revert_project_lifecycle_after_publication(core):
    db, service, published = core
    draft = service.create_revision(published.id)
    validation = service.validate_revision(draft.id)
    service.approve_revision(
        draft.id, RevisionApprovalRequest(draft_hash=validation.draft_hash, diff_hash=validation.diff_hash)
    )
    publisher = _service_as(db, service, "publisher.rollback.guard@gate04.local")
    successor = publisher.publish_revision(
        draft.id, RevisionPublishRequest(draft_hash=validation.draft_hash, diff_hash=validation.diff_hash)
    )
    row = db.scalar(select(EnterpriseWorkspace).where(EnterpriseWorkspace.external_key == "PRJ-HISTORY"))
    row.status = "inactive"
    db.commit()
    with no_dml(db), pytest.raises(HTTPException) as caught:
        publisher.rollback_revision(
            successor.id, RevisionRollbackRequest(reason="Forbidden state restore", confirm=True)
        )
    assert caught.value.detail["code"] == "PROJECT_WORKSPACE_LIFECYCLE_REQUIRED"
    assert db.get(EnterpriseCoreRelease, successor.id).state == "published"
    assert row.status == "inactive"


def test_core_adopts_existing_pending_project_without_lifecycle_change():
    db, service, published = _seed(with_historical_project=True, historical_project_status="pending")
    try:
        row = db.scalar(select(EnterpriseWorkspace).where(EnterpriseWorkspace.external_key == "PRJ-HISTORY"))
        original_id = row.id
        draft = service.create_revision(published.id)
        service.edit_workspace(
            draft.id,
            "PRJ-HISTORY",
            RevisionWorkspaceUpdate(description="Pending metadata", status="pending"),
            expected_version=draft.revision_version,
        )
        validation = service.validate_revision(draft.id)
        assert validation.valid, validation.errors
        service.approve_revision(
            draft.id, RevisionApprovalRequest(draft_hash=validation.draft_hash, diff_hash=validation.diff_hash)
        )
        publisher = _service_as(db, service, "publisher.pending@gate04.local")
        successor = publisher.publish_revision(
            draft.id, RevisionPublishRequest(draft_hash=validation.draft_hash, diff_hash=validation.diff_hash)
        )
        assert successor.state == "published"
        assert row.id == original_id
        assert row.status == "pending"
        assert db.scalar(select(func.count()).select_from(ProjectCreationRequest)) == 0
        assert db.scalar(select(func.count()).select_from(ProjectWorkspaceInitialization)) == 0
    finally:
        db.close()


def test_core_cannot_activate_existing_pending_project():
    db, service, published = _seed(with_historical_project=True, historical_project_status="pending")
    try:
        draft = service.create_revision(published.id)
        with no_dml(db), pytest.raises(HTTPException) as caught:
            service.edit_workspace(
                draft.id,
                "PRJ-HISTORY",
                RevisionWorkspaceUpdate(status="active"),
                expected_version=draft.revision_version,
            )
        assert caught.value.detail["code"] == "PROJECT_WORKSPACE_LIFECYCLE_REQUIRED"
        assert caught.value.detail["dedicated_api"].endswith("/activate")
    finally:
        db.close()


def _live_project_after_publication(db, service, *, status="pending", parent=None):
    """Fixture for a USER-owned row created after CORE; not a lifecycle E2E."""
    parent = parent or db.scalar(select(EnterpriseWorkspace).where(EnterpriseWorkspace.external_key == "PF-TWO"))
    row = _workspace(
        service.tenant_id,
        service.actor_id,
        "PRJ-AFTER-CORE",
        "PRJ-AFTER-CORE",
        f"{parent.record_code}.01",
        "Project created after CORE publication",
        "project",
        parent.id,
        10,
    )
    row.status = status
    db.add(row)
    db.flush()
    db.add(
        EnterpriseWorkspaceClassification(
            tenant_id=service.tenant_id,
            workspace_id=row.id,
            category_set_code="strategic-objective",
            category_item_code="growth",
            created_by_user_id=service.actor_id,
        )
    )
    db.commit()
    return row


@pytest.mark.parametrize("status", ["pending", "active"])
def test_new_revision_adopts_project_created_after_core_without_changing_live_identity(status):
    db, service, published = _seed()
    try:
        historical = copy.deepcopy(published.snapshot_json)
        historical_hash = published.content_fingerprint
        row = _live_project_after_publication(db, service, status=status)
        original = (row.id, row.status, row.version, copy.deepcopy(row.defaults_json))
        draft = service.create_revision(published.id)
        adopted = next(item for item in draft.workspaces if item.workspace_key == row.external_key)
        assert (adopted.technical_id, adopted.status) == (row.id, status)
        assert any(item.category_set_code == "strategic-objective" for item in adopted.classifications)
        assert (row.id, row.status, row.version, row.defaults_json) == original
        assert published.snapshot_json == historical
        assert published.content_fingerprint == historical_hash
        validation = service.validate_revision(draft.id)
        assert validation.valid, validation.errors
        service.approve_revision(
            draft.id, RevisionApprovalRequest(draft_hash=validation.draft_hash, diff_hash=validation.diff_hash)
        )
        publisher = _service_as(db, service, f"publisher.adopt.{status}@gate04.local")
        assert (
            publisher.publish_revision(
                draft.id, RevisionPublishRequest(draft_hash=validation.draft_hash, diff_hash=validation.diff_hash)
            ).state
            == "published"
        )
        assert (row.id, row.status) == original[:2]
        assert published.snapshot_json == historical
    finally:
        db.close()


def test_new_revision_adopts_actual_activation_without_rewriting_published_pending_snapshot():
    db, service, published = _seed(with_historical_project=True, historical_project_status="pending")
    try:
        historical = copy.deepcopy(published.snapshot_json)
        row = db.scalar(select(EnterpriseWorkspace).where(EnterpriseWorkspace.external_key == "PRJ-HISTORY"))
        row.status = "active"
        db.commit()
        draft = service.create_revision(published.id)
        assert next(item for item in draft.workspaces if item.workspace_key == "PRJ-HISTORY").status == "active"
        validation = service.validate_revision(draft.id)
        assert validation.valid, validation.errors
        assert published.snapshot_json == historical
        assert row.status == "active"
    finally:
        db.close()


def test_explicit_create_reconciles_existing_draft_preserving_edits_and_invalidating_approval():
    db, service, published = _seed()
    try:
        historical = copy.deepcopy(published.snapshot_json)
        draft = service.create_revision(published.id)
        edited = service.edit_workspace(
            draft.id,
            "PF-TWO",
            RevisionWorkspaceUpdate(description="Preserve this ADMIN edit"),
            expected_version=draft.revision_version,
        )
        validation = service.validate_revision(draft.id)
        service.approve_revision(
            draft.id, RevisionApprovalRequest(draft_hash=validation.draft_hash, diff_hash=validation.diff_hash)
        )
        row = _live_project_after_publication(db, service)
        original = (row.id, row.status, row.version, copy.deepcopy(row.defaults_json))
        before_version = db.get(EnterpriseCoreRelease, edited.id).revision_version
        reconciled = service.create_revision(published.id)
        assert reconciled.id == draft.id
        assert reconciled.revision_version > before_version
        assert reconciled.approved_at is None
        assert reconciled.validation is None
        assert next(item for item in reconciled.workspaces if item.workspace_key == "PF-TWO").description == (
            "Preserve this ADMIN edit"
        )
        assert any(item.workspace_key == row.external_key for item in reconciled.workspaces)
        assert (row.id, row.status, row.version, row.defaults_json) == original
        assert published.snapshot_json == historical
        with no_dml(db):
            assert service.create_revision(published.id).revision_version == reconciled.revision_version
    finally:
        db.close()


@pytest.mark.parametrize("existing_draft", [False, True])
def test_reconcile_never_masks_foreign_project_identity(existing_draft):
    db, service, published = _seed(with_historical_project=True)
    try:
        foreign = Tenant(name="Foreign adoption", slug="foreign-adoption", base_currency="COP")
        db.add(foreign)
        db.flush()
        row = _workspace(
            foreign.id, service.actor_id, "PRJ-FOREIGN", "PRJ-FOREIGN", "99", "Foreign", "project", None, 0
        )
        db.add(row)
        db.commit()
        holder = (
            db.get(EnterpriseCoreRelease, service.create_revision(published.id).id) if existing_draft else published
        )
        corrupted = copy.deepcopy(holder.snapshot_json)
        next(item for item in corrupted["workspaces"] if item["external_key"] == "PRJ-HISTORY")["id"] = row.id
        if existing_draft:
            holder.snapshot_json = corrupted
            db.commit()
        before = copy.deepcopy(holder.snapshot_json)
        with no_dml(db), pytest.raises(HTTPException) as caught:
            if existing_draft:
                service.create_revision(published.id)
            else:
                # Exercise the new-draft copy preflight without bypassing the
                # immutable published-release model guard to corrupt history.
                service._adopt_live_projects_for_draft(corrupted)
        assert caught.value.detail["code"] == "PROJECT_WORKSPACE_IDENTITY_MISMATCH"
        assert holder.snapshot_json == before
        assert row.tenant_id == foreign.id
    finally:
        db.close()


def test_reconcile_does_not_adopt_another_tenants_project():
    db, service, published = _seed()
    try:
        foreign = Tenant(name="Foreign adoption", slug="foreign-project-not-adopted", base_currency="COP")
        db.add(foreign)
        db.flush()
        row = _workspace(
            foreign.id, service.actor_id, "PRJ-FOREIGN", "PRJ-FOREIGN", "99", "Foreign", "project", None, 0
        )
        db.add(row)
        db.commit()
        draft = service.create_revision(published.id)
        assert all(item.technical_id != row.id for item in draft.workspaces)
        assert service.validate_revision(draft.id).valid
    finally:
        db.close()


def test_project_with_missing_core_parent_requires_reconciliation_before_any_draft_dml():
    db, service, published = _seed()
    try:
        portfolio = db.scalar(select(EnterpriseWorkspace).where(EnterpriseWorkspace.external_key == "PF-TWO"))
        parent = _workspace(
            service.tenant_id,
            service.actor_id,
            "PRG-AFTER-CORE",
            "PRG-AFTER-CORE",
            "01.01.02.01",
            "Program not in published snapshot",
            "program",
            portfolio.id,
            10,
        )
        db.add(parent)
        db.commit()
        row = _live_project_after_publication(db, service, parent=parent)
        with no_dml(db), pytest.raises(HTTPException) as caught:
            service.create_revision(published.id)
        assert caught.value.detail["code"] == "PROJECT_PARENT_RECONCILIATION_REQUIRED"
        assert row.status == "pending"
        assert service.repository.latest_draft_release() is None
    finally:
        db.close()
