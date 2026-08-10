from __future__ import annotations

import copy

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.time import utc_now
from app.database.session import Base
from app.domain.models import AdminConfiguration, EnterpriseWorkspace, SecurityEvent, Tenant, UserAccount
from app.modules.enterprise_structure.constants import CATEGORY_SEED, PERMISSION_SEED, WORKSPACE_TYPE_SEED
from app.modules.enterprise_structure.models import (
    EnterpriseCoreRelease,
    EnterpriseWorkspaceClassification,
)
from app.modules.enterprise_structure.revisions import EnterpriseStructureRevisionService
from app.modules.enterprise_structure.schemas import (
    RevisionApprovalRequest,
    RevisionClassificationIn,
    RevisionClassificationsUpdate,
    RevisionMoveRequest,
    RevisionPublishRequest,
    RevisionRecordCodePreviewRequest,
    RevisionRollbackRequest,
    RevisionWorkspaceCreate,
    RevisionWorkspaceUpdate,
)


def _configuration(
    tenant_id: int,
    actor_id: int,
    kind: str,
    code: str,
    content: dict,
) -> AdminConfiguration:
    return AdminConfiguration(
        tenant_id=tenant_id,
        kind=kind,
        code=code,
        name=code.replace("-", " ").title(),
        description="Gate 04 fixture",
        status="published",
        revision=1,
        version=1,
        content_json=content,
        content_hash="c" * 64,
        published_at=utc_now(),
        created_by_user_id=actor_id,
    )


def _workspace(
    tenant_id: int,
    actor_id: int,
    external_key: str,
    code: str,
    record_code: str,
    name: str,
    workspace_type: str,
    parent_id: int | None,
    sort_order: int,
) -> EnterpriseWorkspace:
    return EnterpriseWorkspace(
        tenant_id=tenant_id,
        parent_id=parent_id,
        workspace_type_code=workspace_type,
        code=code,
        external_key=external_key,
        record_code=record_code,
        name=name,
        status="active",
        defaults_json={"_enterprise": {"description": f"Baseline {name}", "external_key": external_key}},
        sort_order=sort_order,
        version=1,
        created_by_user_id=actor_id,
    )


def _seed() -> tuple[Session, EnterpriseStructureRevisionService, EnterpriseCoreRelease]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    tenant = Tenant(name="P&P Ingenieria y Proyectos", slug="pyp-gate04", base_currency="COP")
    db.add(tenant)
    db.flush()
    actor = UserAccount(tenant_id=tenant.id, email="admin@gate04.local", full_name="Gate 04 Admin", status="active")
    db.add(actor)
    db.flush()
    for code, definition in WORKSPACE_TYPE_SEED.items():
        db.add(
            _configuration(
                tenant.id,
                actor.id,
                "workspace_type",
                code,
                {
                    "allowed_children": definition["allowed_children"],
                    "can_be_root": definition["can_be_root"],
                    "required_categories": definition["required_categories"],
                    "required_fields": definition["required_fields"],
                },
            )
        )
    for code, definition in CATEGORY_SEED.items():
        content = copy.deepcopy(definition)
        if code == "responsible-area":
            content["items"] = [{"code": "corporate", "label": "Corporate"}]
        if code == "strategic-objective":
            content["items"] = [
                {"code": "growth", "label": "Growth"},
                {"code": "operational-excellence", "label": "Operational Excellence"},
            ]
        db.add(_configuration(tenant.id, actor.id, "catalog", code, content))
    db.flush()

    root = _workspace(tenant.id, actor.id, "ENT-PYP", "ENT", "01", "P&P Enterprise", "enterprise", None, 0)
    db.add(root)
    db.flush()
    business_unit = _workspace(
        tenant.id,
        actor.id,
        "BU-CORE",
        "BU-CORE",
        "01.01",
        "Core Business Unit",
        "business-unit",
        root.id,
        10,
    )
    db.add(business_unit)
    db.flush()
    portfolio_one = _workspace(
        tenant.id,
        actor.id,
        "PF-ONE",
        "PF-ONE",
        "01.01.01",
        "Portfolio One",
        "portfolio",
        business_unit.id,
        10,
    )
    portfolio_two = _workspace(
        tenant.id,
        actor.id,
        "PF-TWO",
        "PF-TWO",
        "01.01.02",
        "Portfolio Two",
        "portfolio",
        business_unit.id,
        20,
    )
    db.add_all([portfolio_one, portfolio_two])
    db.flush()
    classifications = [
        (business_unit, "responsible-area", "corporate"),
        (portfolio_one, "strategic-objective", "growth"),
        (portfolio_two, "strategic-objective", "growth"),
    ]
    for workspace, category, item in classifications:
        db.add(
            EnterpriseWorkspaceClassification(
                tenant_id=tenant.id,
                workspace_id=workspace.id,
                category_set_code=category,
                category_item_code=item,
                created_by_user_id=actor.id,
            )
        )
    snapshot = {
        "tenant": {"id": tenant.id, "name": tenant.name, "slug": tenant.slug, "currency": "COP"},
        "workspaces": [
            {
                "id": item.id,
                "external_key": item.external_key,
                "record_code": item.record_code,
                "code": item.code,
                "name": item.name,
                "workspace_type": item.workspace_type_code,
                "parent_id": item.parent_id,
                "status": item.status,
                "sort_order": item.sort_order,
            }
            for item in (root, business_unit, portfolio_one, portfolio_two)
        ],
        "strategic_objectives": [],
        "classifications": [
            {
                "workspace_id": workspace.id,
                "workspace_external_key": workspace.external_key,
                "category_set_code": category,
                "category_item_code": item,
            }
            for workspace, category, item in classifications
        ],
        "links": [],
    }
    now = utc_now()
    release = EnterpriseCoreRelease(
        tenant_id=tenant.id,
        release_code="ES-PYP-CORE-RECONCILED-20260809",
        release_name="Published CORE",
        revision_number=1,
        state="published",
        source_hash="a" * 64,
        canonical_hash="b" * 64,
        content_fingerprint="d" * 64,
        source_release_code="ES-PYP-CORE-RECONCILED-20260809",
        previous_release_id=None,
        base_content_fingerprint="d" * 64,
        snapshot_json=snapshot,
        workspace_count=4,
        objective_count=0,
        classification_count=3,
        link_count=0,
        validation_json={"valid": True, "errors": [], "conflicts": [], "checks": {}, "draft_hash": "", "diff_hash": ""},
        diff_hash="e" * 64,
        created_at=now,
        created_by_user_id=actor.id,
        updated_at=now,
        published_at=now,
        published_by_user_id=actor.id,
    )
    db.add(release)
    db.commit()
    return db, EnterpriseStructureRevisionService(db, tenant.id, actor.id), release


def test_create_revision_preserves_published_baseline_and_identity() -> None:
    db, service, published = _seed()
    draft = service.create_revision(published.id)

    assert draft.state == "draft"
    assert draft.previous_release_id == published.id
    assert draft.release_code == "ES-PYP-CORE-REV-002"
    assert draft.workspace_count == 4
    assert {item.workspace_key for item in draft.workspaces} == {"ENT-PYP", "BU-CORE", "PF-ONE", "PF-TWO"}
    assert service.create_revision(published.id).id == draft.id
    assert db.get(EnterpriseCoreRelease, published.id).state == "published"
    assert db.get(EnterpriseCoreRelease, published.id).snapshot_json == published.snapshot_json
    assert db.scalar(select(SecurityEvent).where(SecurityEvent.event_type == "enterprise_structure.revision_created"))
    db.close()


def test_draft_add_edit_preview_move_archive_and_classification_operations() -> None:
    db, service, published = _seed()
    draft = service.create_revision(published.id)
    preview = service.record_code_preview(
        draft.id,
        RevisionRecordCodePreviewRequest(parent_key="PF-ONE", workspace_type_code="program"),
    )
    assert preview.record_code == "01.01.01.01"

    updated = service.add_workspace(
        draft.id,
        RevisionWorkspaceCreate(
            name="AI Program",
            workspace_type_code="program",
            parent_key="PF-ONE",
            applicable_classifications=[
                RevisionClassificationIn(category_set_code="strategic-objective", category_item_code="growth")
            ],
        ),
    )
    added = next(item for item in updated.workspaces if item.name == "AI Program")
    assert added.technical_id is None
    assert added.record_code == preview.record_code

    updated = service.edit_workspace(
        draft.id,
        added.workspace_key,
        RevisionWorkspaceUpdate(name="AI SaaS Program", description="Controlled draft edit"),
    )
    assert (
        next(item for item in updated.workspaces if item.workspace_key == added.workspace_key).name == "AI SaaS Program"
    )

    updated = service.set_classifications(
        draft.id,
        "PF-ONE",
        RevisionClassificationsUpdate(
            classifications=[
                RevisionClassificationIn(
                    category_set_code="strategic-objective",
                    category_item_code="operational-excellence",
                )
            ]
        ),
    )
    assert (
        next(item for item in updated.workspaces if item.workspace_key == "PF-ONE")
        .classifications[0]
        .category_item_code
        == "operational-excellence"
    )

    with pytest.raises(HTTPException, match="not allowed"):
        service.move_workspace(draft.id, "PF-TWO", RevisionMoveRequest(new_parent_key="PF-ONE"))
    archived = service.archive_workspace(draft.id, added.workspace_key)
    assert next(item for item in archived.workspaces if item.workspace_key == added.workspace_key).status == "archived"
    assert db.get(EnterpriseCoreRelease, published.id).snapshot_json == published.snapshot_json
    db.close()


def test_move_preserves_external_key_and_recodes_descendants() -> None:
    db, service, published = _seed()
    draft = service.create_revision(published.id)
    draft = service.add_workspace(
        draft.id,
        RevisionWorkspaceCreate(
            name="Portfolio Program",
            workspace_type_code="program",
            parent_key="PF-ONE",
            status="active",
            applicable_classifications=[
                RevisionClassificationIn(category_set_code="strategic-objective", category_item_code="growth")
            ],
        ),
    )
    program = next(item for item in draft.workspaces if item.name == "Portfolio Program")
    draft = service.add_workspace(
        draft.id,
        RevisionWorkspaceCreate(
            name="Program Project",
            workspace_type_code="project",
            parent_key=program.workspace_key,
            status="active",
            applicable_classifications=[
                RevisionClassificationIn(category_set_code="strategic-objective", category_item_code="growth")
            ],
        ),
    )
    project = next(item for item in draft.workspaces if item.name == "Program Project")
    draft = service.add_workspace(
        draft.id,
        RevisionWorkspaceCreate(
            name="Second Business Unit",
            workspace_type_code="business-unit",
            parent_key="ENT-PYP",
            status="active",
            applicable_classifications=[
                RevisionClassificationIn(category_set_code="responsible-area", category_item_code="corporate")
            ],
        ),
    )
    target = next(item for item in draft.workspaces if item.name == "Second Business Unit")
    preview = service.record_code_preview(
        draft.id,
        RevisionRecordCodePreviewRequest(
            parent_key=target.workspace_key,
            workspace_type_code="portfolio",
            workspace_key="PF-ONE",
        ),
    )
    moved = service.move_workspace(draft.id, "PF-ONE", RevisionMoveRequest(new_parent_key=target.workspace_key))
    portfolio = next(item for item in moved.workspaces if item.workspace_key == "PF-ONE")
    moved_program = next(item for item in moved.workspaces if item.workspace_key == program.workspace_key)
    moved_project = next(item for item in moved.workspaces if item.workspace_key == project.workspace_key)

    assert portfolio.workspace_key == "PF-ONE"
    assert portfolio.technical_id is not None
    assert portfolio.record_code == preview.record_code
    assert [(item.before, item.after) for item in preview.affected_descendants] == [
        ("01.01.01.01", "01.02.01.01"),
        ("01.01.01.01.01", "01.02.01.01.01"),
    ]
    assert moved_program.record_code == "01.02.01.01"
    assert moved_project.record_code == "01.02.01.01.01"
    with pytest.raises(HTTPException, match="cycles"):
        service.move_workspace(draft.id, target.workspace_key, RevisionMoveRequest(new_parent_key="PF-ONE"))
    db.close()


def test_validate_and_diff_cover_added_modified_moved_archived_and_classifications() -> None:
    db, service, published = _seed()
    draft = service.create_revision(published.id)
    draft = service.add_workspace(
        draft.id,
        RevisionWorkspaceCreate(
            name="Second Business Unit",
            workspace_type_code="business-unit",
            parent_key="ENT-PYP",
            status="active",
            applicable_classifications=[
                RevisionClassificationIn(category_set_code="responsible-area", category_item_code="corporate")
            ],
        ),
    )
    target = next(item for item in draft.workspaces if item.name == "Second Business Unit")
    service.edit_workspace(draft.id, "BU-CORE", RevisionWorkspaceUpdate(name="Construction Management"))
    service.move_workspace(draft.id, "PF-ONE", RevisionMoveRequest(new_parent_key=target.workspace_key))
    service.archive_workspace(draft.id, "PF-TWO")
    service.set_classifications(
        draft.id,
        "PF-ONE",
        RevisionClassificationsUpdate(
            classifications=[
                RevisionClassificationIn(
                    category_set_code="strategic-objective", category_item_code="operational-excellence"
                )
            ]
        ),
    )
    validation = service.validate_revision(draft.id)
    diff = service.compare_revision(draft.id)

    assert validation.valid is True
    assert validation.errors == []
    assert validation.conflicts == []
    assert all(validation.checks.values())
    assert diff.summary == {
        "added": 1,
        "modified": 1,
        "moved": 1,
        "archived": 1,
        "classification_changes": 1,
        "unchanged": 1,
    }
    assert {item.action for item in diff.items} == {"ADD", "MODIFY", "MOVE", "ARCHIVE", "CLASSIFICATION"}
    db.close()


def test_invalid_revision_detects_duplicate_codes_orphans_cycles_and_cross_tenant() -> None:
    db, service, published = _seed()
    draft = service.create_revision(published.id)
    release = db.get(EnterpriseCoreRelease, draft.id)
    snapshot = copy.deepcopy(release.snapshot_json)
    snapshot["tenant"]["id"] = 999
    snapshot["workspaces"][1]["code"] = snapshot["workspaces"][0]["code"]
    snapshot["workspaces"][1]["record_code"] = snapshot["workspaces"][0]["record_code"]
    snapshot["workspaces"][1]["parent_external_key"] = "PF-ONE"
    snapshot["workspaces"][2]["parent_external_key"] = "BU-CORE"
    snapshot["workspaces"][3]["parent_external_key"] = "MISSING"
    release.snapshot_json = snapshot
    db.commit()

    validation = service.validate_revision(draft.id)
    assert validation.valid is False
    assert validation.checks["cross_tenant_zero"] is False
    assert validation.checks["codes_unique"] is False
    assert validation.checks["record_code_unique"] is False
    assert validation.checks["no_orphans"] is False
    assert validation.checks["acyclic"] is False
    db.close()


def test_approval_hash_guards_publish_successor_idempotency_and_immutability() -> None:
    db, service, published = _seed()
    draft = service.create_revision(published.id)
    service.edit_workspace(draft.id, "BU-CORE", RevisionWorkspaceUpdate(name="Construction Management"))
    validation = service.validate_revision(draft.id)

    with pytest.raises(HTTPException, match="approval"):
        service.publish_revision(
            draft.id,
            RevisionPublishRequest(draft_hash=validation.draft_hash, diff_hash=validation.diff_hash),
        )
    with pytest.raises(HTTPException, match="HASH_MISMATCH"):
        service.approve_revision(
            draft.id,
            RevisionApprovalRequest(draft_hash="0" * 64, diff_hash=validation.diff_hash),
        )
    service.approve_revision(
        draft.id,
        RevisionApprovalRequest(draft_hash=validation.draft_hash, diff_hash=validation.diff_hash),
    )
    successor = service.publish_revision(
        draft.id,
        RevisionPublishRequest(draft_hash=validation.draft_hash, diff_hash=validation.diff_hash),
    )
    replay = service.publish_revision(
        draft.id,
        RevisionPublishRequest(draft_hash=validation.draft_hash, diff_hash=validation.diff_hash),
    )

    assert successor.state == "published"
    assert successor.previous_release_id == published.id
    assert replay.id == successor.id
    assert db.get(EnterpriseCoreRelease, published.id).state == "superseded"
    persisted = db.scalar(select(EnterpriseWorkspace).where(EnterpriseWorkspace.external_key == "BU-CORE"))
    assert persisted.name == "Construction Management"
    release = db.get(EnterpriseCoreRelease, draft.id)
    release.release_name = "Forbidden published edit"
    with pytest.raises(ValueError, match="immutable"):
        db.commit()
    db.rollback()
    db.close()


def test_base_release_change_blocks_publish() -> None:
    db, service, published = _seed()
    draft = service.create_revision(published.id)
    validation = service.validate_revision(draft.id)
    service.approve_revision(
        draft.id,
        RevisionApprovalRequest(draft_hash=validation.draft_hash, diff_hash=validation.diff_hash),
    )
    competing = EnterpriseCoreRelease(
        tenant_id=published.tenant_id,
        release_code="ES-PYP-COMPETING",
        release_name="Competing release",
        revision_number=99,
        state="published",
        source_hash="1" * 64,
        canonical_hash="2" * 64,
        content_fingerprint="3" * 64,
        base_content_fingerprint="3" * 64,
        snapshot_json=copy.deepcopy(published.snapshot_json),
        workspace_count=4,
        objective_count=0,
        classification_count=3,
        link_count=0,
        validation_json={},
        diff_hash="4" * 64,
        created_at=utc_now(),
        created_by_user_id=service.actor_id,
        updated_at=utc_now(),
        published_at=utc_now(),
        published_by_user_id=service.actor_id,
    )
    db.add(competing)
    db.commit()

    with pytest.raises(HTTPException, match="BASE_RELEASE_CHANGED"):
        service.publish_revision(
            draft.id,
            RevisionPublishRequest(draft_hash=validation.draft_hash, diff_hash=validation.diff_hash),
        )
    db.close()


def test_logical_rollback_requires_confirmation_and_restores_previous_release() -> None:
    db, service, published = _seed()
    draft = service.create_revision(published.id)
    service.edit_workspace(draft.id, "BU-CORE", RevisionWorkspaceUpdate(name="Construction Management"))
    validation = service.validate_revision(draft.id)
    service.approve_revision(
        draft.id,
        RevisionApprovalRequest(draft_hash=validation.draft_hash, diff_hash=validation.diff_hash),
    )
    successor = service.publish_revision(
        draft.id,
        RevisionPublishRequest(draft_hash=validation.draft_hash, diff_hash=validation.diff_hash),
    )
    with pytest.raises(HTTPException, match="confirmation"):
        service.rollback_revision(successor.id, RevisionRollbackRequest(reason="QA rollback", confirm=False))
    restored = service.rollback_revision(
        successor.id,
        RevisionRollbackRequest(reason="QA rollback approved", confirm=True),
    )

    assert restored.id == published.id
    assert restored.state == "published"
    assert db.get(EnterpriseCoreRelease, successor.id).state == "unpublished"
    workspace = db.scalar(select(EnterpriseWorkspace).where(EnterpriseWorkspace.external_key == "BU-CORE"))
    assert workspace.name == "Core Business Unit"
    events = set(db.scalars(select(SecurityEvent.event_type)).all())
    assert {
        "enterprise_structure.revision_created",
        "enterprise_structure.revision_modified",
        "enterprise_structure.revision_validated",
        "enterprise_structure.revision_approved",
        "enterprise_structure.core_published",
        "enterprise_structure.core_unpublished",
    }.issubset(events)
    db.close()


def test_gate04_permissions_and_postgresql_revision_are_declared() -> None:
    permissions = {item[0] for item in PERMISSION_SEED}
    assert {
        "admin.enterprise_structure.revision.create",
        "admin.enterprise_structure.revision.edit",
        "admin.enterprise_structure.revision.validate",
        "admin.enterprise_structure.revision.compare",
        "admin.enterprise_structure.revision.approve",
        "admin.enterprise_structure.publish",
        "admin.enterprise_structure.rollback",
    }.issubset(permissions)
    assert EnterpriseCoreRelease.__table__.c.published_at.nullable is True
    assert EnterpriseCoreRelease.__table__.c.previous_release_id.foreign_keys
