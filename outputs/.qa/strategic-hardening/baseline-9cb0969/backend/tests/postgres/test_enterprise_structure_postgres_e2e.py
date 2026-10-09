"""Gate 04H transactional and authorization checks against ephemeral PostgreSQL only."""

from __future__ import annotations

import copy
import json
import os
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domain.models import (
    AdminConfiguration,
    EnterpriseWorkspace,
    OrganizationUnit,
    PermissionCatalog,
    SecurityAccessAssignment,
    SecurityEvent,
    SecurityRole,
    Tenant,
    UserAccount,
)
from app.modules.enterprise_structure.constants import CATEGORY_SEED, WORKSPACE_TYPE_SEED
from app.modules.enterprise_structure.models import EnterpriseCoreRelease, EnterpriseWorkspaceClassification
from app.modules.enterprise_structure.permissions import (
    REVISION_DUTY_ROLES,
    STRUCTURE_ROLE_PERMISSIONS,
    ensure_enterprise_permissions,
    require_enterprise_permission,
    require_organization_scope,
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

DATABASE_URL = os.getenv("GATE04H_DATABASE_URL", "")
if not DATABASE_URL:
    pytest.skip("Gate 04H requires GATE04H_DATABASE_URL for ephemeral PostgreSQL", allow_module_level=True)
if not DATABASE_URL.startswith("postgresql+"):
    raise RuntimeError("Gate 04H refuses non-PostgreSQL databases")
if os.getenv("GATE04H_EPHEMERAL") != "true":
    raise RuntimeError("Set GATE04H_EPHEMERAL=true only for a disposable PostgreSQL database")

ARTIFACT_DIR = Path(os.getenv("GATE04H_ARTIFACT_DIR", "artifacts/enterprise_structure/gate04h"))
ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)


def _write_json(name: str, payload: dict[str, Any]) -> None:
    (ARTIFACT_DIR / name).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )


@pytest.fixture
def engine():
    candidate = create_engine(DATABASE_URL, pool_pre_ping=True)
    if candidate.dialect.name != "postgresql":
        candidate.dispose()
        raise RuntimeError("Gate 04H requires PostgreSQL")
    yield candidate
    candidate.dispose()


def _configuration(tenant_id: int, actor_id: int, kind: str, code: str, content: dict[str, Any]):
    return AdminConfiguration(
        tenant_id=tenant_id,
        kind=kind,
        code=code,
        name=code.replace("-", " ").title(),
        description="Gate 04H synthetic fixture",
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
):
    return EnterpriseWorkspace(
        tenant_id=tenant_id,
        parent_id=parent_id,
        workspace_type_code=workspace_type,
        code=code,
        external_key=external_key,
        record_code=record_code,
        name=name,
        status="active",
        defaults_json={"_enterprise": {"description": f"Synthetic {name}", "external_key": external_key}},
        sort_order=sort_order,
        version=1,
        created_by_user_id=actor_id,
    )


def _seed_release(db: Session, label: str, node_count: int = 6) -> dict[str, Any]:
    if node_count < 6:
        raise ValueError("The synthetic hierarchy requires at least six nodes")
    suffix = uuid.uuid4().hex[:10]
    tenant = Tenant(name=f"Gate 04H {label}", slug=f"gate04h-{label}-{suffix}", base_currency="COP")
    db.add(tenant)
    db.flush()
    actors = {}
    for role in ("editor-a", "editor-b", "approver", "publisher", "bootstrap"):
        actor = UserAccount(
            tenant_id=tenant.id,
            email=f"{role}.{suffix}@gate04h.local",
            full_name=role.replace("-", " ").title(),
            status="active",
        )
        db.add(actor)
        db.flush()
        actors[role] = actor

    for code, definition in WORKSPACE_TYPE_SEED.items():
        db.add(
            _configuration(
                tenant.id,
                actors["bootstrap"].id,
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
        db.add(_configuration(tenant.id, actors["bootstrap"].id, "catalog", code, copy.deepcopy(definition)))
    db.flush()

    root = _workspace(tenant.id, actors["editor-a"].id, "ENT", "ENT", "01", "Enterprise", "enterprise", None, 0)
    db.add(root)
    db.flush()
    bu_a = _workspace(
        tenant.id, actors["editor-a"].id, "BU-A", "BU-A", "01.01", "Business Unit A", "business-unit", root.id, 10
    )
    bu_b = _workspace(
        tenant.id, actors["editor-a"].id, "BU-B", "BU-B", "01.02", "Business Unit B", "business-unit", root.id, 20
    )
    db.add_all([bu_a, bu_b])
    db.flush()
    portfolio = _workspace(
        tenant.id, actors["editor-a"].id, "PF-A", "PF-A", "01.01.01", "Portfolio A", "portfolio", bu_a.id, 10
    )
    db.add(portfolio)
    db.flush()
    program = _workspace(
        tenant.id,
        actors["editor-a"].id,
        "PG-A",
        "PG-A",
        "01.01.01.01",
        "Program A",
        "program",
        portfolio.id,
        10,
    )
    db.add(program)
    db.flush()
    project = _workspace(
        tenant.id,
        actors["editor-a"].id,
        "PJ-A",
        "PJ-A",
        "01.01.01.01.01",
        "Project A",
        "project",
        program.id,
        10,
    )
    db.add(project)
    db.flush()
    nodes = [root, bu_a, portfolio, program, project, bu_b]
    extra_portfolios = [
        _workspace(
            tenant.id,
            actors["editor-a"].id,
            f"PF-X-{sequence:05d}",
            f"PF-X-{sequence:05d}",
            f"01.02.{sequence + 1:05d}",
            f"Synthetic Portfolio {sequence:05d}",
            "portfolio",
            bu_b.id,
            (sequence + 1) * 10,
        )
        for sequence in range(1, node_count - 5)
    ]
    db.add_all(extra_portfolios)
    db.flush()
    nodes.extend(extra_portfolios)
    classifications = [
        (bu_a, "responsible-area", "corporate"),
        (bu_b, "responsible-area", "corporate"),
        (portfolio, "strategic-objective", "growth"),
        (program, "strategic-objective", "growth"),
        (project, "strategic-objective", "growth"),
    ] + [(item, "strategic-objective", "growth") for item in extra_portfolios]
    for workspace, category, item in classifications:
        db.add(
            EnterpriseWorkspaceClassification(
                tenant_id=tenant.id,
                workspace_id=workspace.id,
                category_set_code=category,
                category_item_code=item,
                created_by_user_id=actors["editor-a"].id,
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
            for item in nodes
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
        release_code=f"GATE04H-{suffix}-R001",
        release_name="Synthetic Published CORE",
        revision_number=1,
        revision_version=1,
        state="published",
        source_hash="a" * 64,
        canonical_hash="b" * 64,
        content_fingerprint="d" * 64,
        source_release_code=f"GATE04H-{suffix}-R001",
        previous_release_id=None,
        base_content_fingerprint="d" * 64,
        snapshot_json=snapshot,
        workspace_count=len(nodes),
        objective_count=0,
        classification_count=len(classifications),
        link_count=0,
        validation_json={"valid": True, "errors": [], "conflicts": []},
        diff_hash="e" * 64,
        created_at=now,
        created_by_user_id=actors["editor-a"].id,
        updated_at=now,
        last_modified_by_user_id=actors["editor-a"].id,
        published_at=now,
        published_by_user_id=actors["publisher"].id,
    )
    db.add(release)
    db.commit()
    return {"tenant": tenant, "actors": actors, "release": release}


def _service(db: Session, seeded: dict[str, Any], actor: str) -> EnterpriseStructureRevisionService:
    return EnterpriseStructureRevisionService(db, seeded["tenant"].id, seeded["actors"][actor].id)


def _version(service: EnterpriseStructureRevisionService, release_id: int) -> int:
    return service.get_revision(release_id).revision_version


def _reason(exc: pytest.ExceptionInfo[HTTPException]) -> str:
    detail = exc.value.detail
    return detail.get("reason", "") if isinstance(detail, dict) else str(detail)


def test_postgres_clone_publish_rollback_transaction(engine) -> None:
    with Session(engine) as db:
        seeded = _seed_release(db, "cycle")
        editor = _service(db, seeded, "editor-a")
        approver = _service(db, seeded, "approver")
        publisher = _service(db, seeded, "publisher")
        published = seeded["release"]
        original_snapshot = copy.deepcopy(published.snapshot_json)

        draft = editor.create_revision(published.id)
        assert draft.previous_release_id == published.id
        assert db.get(EnterpriseCoreRelease, published.id).snapshot_json == original_snapshot

        draft = editor.add_workspace(
            draft.id,
            RevisionWorkspaceCreate(
                name="Portfolio B",
                workspace_type_code="portfolio",
                parent_key="BU-B",
                status="active",
                applicable_classifications=[
                    RevisionClassificationIn(category_set_code="strategic-objective", category_item_code="growth")
                ],
            ),
            expected_version=draft.revision_version,
        )
        portfolio_b = next(item for item in draft.workspaces if item.name == "Portfolio B")
        draft = editor.add_workspace(
            draft.id,
            RevisionWorkspaceCreate(
                name="Program B",
                workspace_type_code="program",
                parent_key=portfolio_b.workspace_key,
                status="active",
                applicable_classifications=[
                    RevisionClassificationIn(category_set_code="strategic-objective", category_item_code="growth")
                ],
            ),
            expected_version=draft.revision_version,
        )
        program_b = next(item for item in draft.workspaces if item.name == "Program B")
        draft = editor.add_workspace(
            draft.id,
            RevisionWorkspaceCreate(
                name="Project B",
                workspace_type_code="project",
                parent_key=program_b.workspace_key,
                status="active",
                applicable_classifications=[
                    RevisionClassificationIn(category_set_code="strategic-objective", category_item_code="growth")
                ],
            ),
            expected_version=draft.revision_version,
        )
        draft = editor.edit_workspace(
            draft.id,
            program_b.workspace_key,
            RevisionWorkspaceUpdate(name="Program B Controlled"),
            expected_version=draft.revision_version,
        )
        preview = editor.record_code_preview(
            draft.id,
            RevisionRecordCodePreviewRequest(
                parent_key="BU-B",
                workspace_type_code="portfolio",
                workspace_key="PF-A",
            ),
        )
        draft = editor.move_workspace(
            draft.id,
            "PF-A",
            RevisionMoveRequest(new_parent_key="BU-B"),
            expected_version=draft.revision_version,
        )
        assert len(preview.affected_descendants) == 2
        assert next(item for item in draft.workspaces if item.workspace_key == "PG-A").record_code.startswith(
            preview.record_code
        )
        draft = editor.set_classifications(
            draft.id,
            "PF-A",
            RevisionClassificationsUpdate(
                classifications=[
                    RevisionClassificationIn(
                        category_set_code="strategic-objective",
                        category_item_code="operational-excellence",
                    )
                ]
            ),
            expected_version=draft.revision_version,
        )
        draft = editor.archive_workspace(
            draft.id,
            "PJ-A",
            expected_version=draft.revision_version,
        )
        validation = editor.validate_revision(draft.id)
        comparison = editor.compare_revision(draft.id)
        assert validation.valid
        assert comparison.summary["added"] == 3
        assert comparison.summary["moved"] == 1
        assert comparison.summary["archived"] == 1

        approved = approver.approve_revision(
            draft.id,
            RevisionApprovalRequest(draft_hash=validation.draft_hash, diff_hash=validation.diff_hash),
        )
        successor = publisher.publish_revision(
            draft.id,
            RevisionPublishRequest(draft_hash=approved.draft_hash, diff_hash=approved.diff_hash),
        )
        assert successor.state == "published"
        assert successor.previous_release_id == published.id
        assert db.get(EnterpriseCoreRelease, published.id).state == "superseded"

        version_before_replay = successor.revision_version
        replay = publisher.publish_revision(
            successor.id,
            RevisionPublishRequest(draft_hash=successor.draft_hash, diff_hash=successor.diff_hash),
        )
        assert replay.revision_version == version_before_replay

        second_draft = editor.create_revision(successor.id)
        second_draft = editor.edit_workspace(
            second_draft.id,
            "BU-A",
            RevisionWorkspaceUpdate(name="Business Unit A Revised"),
            expected_version=second_draft.revision_version,
        )
        second_validation = editor.validate_revision(second_draft.id)
        second_approved = approver.approve_revision(
            second_draft.id,
            RevisionApprovalRequest(
                draft_hash=second_validation.draft_hash,
                diff_hash=second_validation.diff_hash,
            ),
        )
        second_successor = publisher.publish_revision(
            second_draft.id,
            RevisionPublishRequest(draft_hash=second_approved.draft_hash, diff_hash=second_approved.diff_hash),
        )
        restored = publisher.rollback_revision(
            second_successor.id,
            RevisionRollbackRequest(reason="Gate 04H logical rollback", confirm=True),
        )
        assert restored.id == successor.id
        assert db.get(EnterpriseCoreRelease, second_successor.id).state == "unpublished"
        assert db.get(EnterpriseCoreRelease, successor.id).state == "published"

        event_types = set(
            db.scalars(select(SecurityEvent.event_type).where(SecurityEvent.tenant_id == seeded["tenant"].id)).all()
        )
        required_events = {
            "enterprise_structure.revision_created",
            "enterprise_structure.revision_modified",
            "enterprise_structure.revision_validated",
            "enterprise_structure.revision_approved",
            "enterprise_structure.core_published",
            "enterprise_structure.core_unpublished",
        }
        assert required_events <= event_types
        _write_json(
            "postgres_e2e_results.json",
            {
                "database": "ephemeral PostgreSQL",
                "status": "PASS",
                "clone": "PASS",
                "draft_isolation": "PASS",
                "add_edit_move_classify_archive": "PASS",
                "record_code_preview": "PASS",
                "descendant_recoding": "PASS",
                "validate": "PASS",
                "diff": "PASS",
                "approval": "PASS",
                "publish_successor": "PASS",
                "previous_release_preserved": "PASS",
                "second_publish_mutations": 0,
                "rollback": "PASS",
                "no_physical_delete": "PASS",
                "audit_events": "PASS",
            },
        )


def test_postgres_concurrency_invalidation_and_four_eyes(engine) -> None:
    session_a = Session(engine)
    session_b = Session(engine)
    session_approver = Session(engine)
    session_publisher = Session(engine)
    try:
        seeded = _seed_release(session_a, "concurrency")
        tenant_id = seeded["tenant"].id
        release_id = seeded["release"].id
        actor_ids = {name: actor.id for name, actor in seeded["actors"].items()}
        editor_a = EnterpriseStructureRevisionService(session_a, tenant_id, actor_ids["editor-a"])
        draft = editor_a.create_revision(release_id)
        editor_b = EnterpriseStructureRevisionService(session_b, tenant_id, actor_ids["editor-b"])
        approver = EnterpriseStructureRevisionService(session_approver, tenant_id, actor_ids["approver"])
        publisher = EnterpriseStructureRevisionService(session_publisher, tenant_id, actor_ids["publisher"])

        version_n = draft.revision_version
        assert editor_b.get_revision(draft.id).revision_version == version_n
        editor_a.edit_workspace(
            draft.id,
            "BU-A",
            RevisionWorkspaceUpdate(name="Editor A update"),
            expected_version=version_n,
        )
        with pytest.raises(HTTPException) as conflict:
            editor_b.edit_workspace(
                draft.id,
                "BU-B",
                RevisionWorkspaceUpdate(name="Editor B stale update"),
                expected_version=version_n,
            )
        assert conflict.value.status_code == 409
        assert _reason(conflict) == "REVISION_VERSION_CONFLICT"

        validated = editor_a.validate_revision(draft.id)
        current_version = _version(editor_b, draft.id)
        editor_b.edit_workspace(
            draft.id,
            "BU-B",
            RevisionWorkspaceUpdate(name="Editor B current update"),
            expected_version=current_version,
        )
        with pytest.raises(HTTPException) as hash_mismatch:
            approver.approve_revision(
                draft.id,
                RevisionApprovalRequest(draft_hash=validated.draft_hash, diff_hash=validated.diff_hash),
            )
        assert _reason(hash_mismatch) == "HASH_MISMATCH"

        validated = editor_a.validate_revision(draft.id)
        approved = approver.approve_revision(
            draft.id,
            RevisionApprovalRequest(draft_hash=validated.draft_hash, diff_hash=validated.diff_hash),
        )
        editor_b.edit_workspace(
            draft.id,
            "BU-B",
            RevisionWorkspaceUpdate(description="Invalidates approval"),
            expected_version=_version(editor_b, draft.id),
        )
        with pytest.raises(HTTPException) as invalidated:
            publisher.publish_revision(
                draft.id,
                RevisionPublishRequest(draft_hash=approved.draft_hash, diff_hash=approved.diff_hash),
            )
        assert _reason(invalidated) == "APPROVAL_INVALIDATED"

        validated = editor_a.validate_revision(draft.id)
        approved = approver.approve_revision(
            draft.id,
            RevisionApprovalRequest(draft_hash=validated.draft_hash, diff_hash=validated.diff_hash),
        )
        with pytest.raises(HTTPException) as four_eyes:
            approver.publish_revision(
                draft.id,
                RevisionPublishRequest(draft_hash=approved.draft_hash, diff_hash=approved.diff_hash),
            )
        assert _reason(four_eyes) == "FOUR_EYES_VIOLATION"
        publisher.publish_revision(
            draft.id,
            RevisionPublishRequest(draft_hash=approved.draft_hash, diff_hash=approved.diff_hash),
        )
        _write_json(
            "concurrency_results.json",
            {
                "database": "ephemeral PostgreSQL",
                "status": "PASS",
                "stale_writer_status": 409,
                "stale_writer_reason": "REVISION_VERSION_CONFLICT",
                "validate_then_modify_then_approve": "HASH_MISMATCH",
                "approve_then_modify_then_publish": "APPROVAL_INVALIDATED",
                "four_eyes": "PASS",
            },
        )
    finally:
        session_publisher.close()
        session_approver.close()
        session_b.close()
        session_a.close()


def test_postgres_sod_tenant_validity_and_scope(engine) -> None:
    with Session(engine) as db:
        seeded = _seed_release(db, "sod")
        tenant_id = seeded["tenant"].id
        bootstrap_id = seeded["actors"]["bootstrap"].id
        ensure_enterprise_permissions(db, tenant_id, bootstrap_id)
        db.commit()
        roles = {
            item.code: item
            for item in db.scalars(select(SecurityRole).where(SecurityRole.tenant_id == tenant_id)).all()
        }
        users: dict[str, UserAccount] = {}
        for role_code in STRUCTURE_ROLE_PERMISSIONS:
            user = UserAccount(
                tenant_id=tenant_id,
                email=f"{role_code}.{uuid.uuid4().hex[:8]}@gate04h.local",
                full_name=role_code.replace("_", " ").title(),
                status="active",
            )
            db.add(user)
            db.flush()
            users[role_code] = user
            db.add(
                SecurityAccessAssignment(
                    tenant_id=tenant_id,
                    subject_type="user",
                    user_id=user.id,
                    role_id=roles[role_code].id,
                    scope_type="organization",
                    status="active",
                    granted_by_user_id=bootstrap_id,
                )
            )
        db.commit()

        checks = {
            "editor_edit": ("structure_editor", "admin.enterprise_structure.revision.edit", True),
            "editor_approve": ("structure_editor", "admin.enterprise_structure.revision.approve", False),
            "editor_publish": ("structure_editor", "admin.enterprise_structure.publish", False),
            "approver_approve": ("structure_approver", "admin.enterprise_structure.revision.approve", True),
            "approver_edit": ("structure_approver", "admin.enterprise_structure.revision.edit", False),
            "publisher_publish": ("structure_publisher", "admin.enterprise_structure.publish", True),
            "publisher_approve": ("structure_publisher", "admin.enterprise_structure.revision.approve", False),
        }
        results: dict[str, str] = {}
        for name, (role_code, permission, expected) in checks.items():
            try:
                require_enterprise_permission(
                    db,
                    tenant_id,
                    users[role_code].id,
                    permission,
                    allowed_role_codes=REVISION_DUTY_ROLES[permission],
                )
                observed = True
            except HTTPException:
                observed = False
            assert observed is expected
            results[name] = "PASS"

        with pytest.raises(HTTPException):
            require_enterprise_permission(
                db,
                tenant_id,
                bootstrap_id,
                "admin.enterprise_structure.revision.approve",
                allowed_role_codes=REVISION_DUTY_ROLES["admin.enterprise_structure.revision.approve"],
            )
        results["organization_admin_has_no_revision_duty_bypass"] = "PASS"

        other_tenant = Tenant(name="Cross Tenant", slug=f"cross-{uuid.uuid4().hex[:8]}", base_currency="COP")
        db.add(other_tenant)
        db.flush()
        cross_user = UserAccount(
            tenant_id=other_tenant.id,
            email=f"cross.{uuid.uuid4().hex[:8]}@gate04h.local",
            full_name="Cross Tenant",
            status="active",
        )
        db.add(cross_user)
        db.flush()
        with pytest.raises(HTTPException):
            require_enterprise_permission(
                db,
                tenant_id,
                cross_user.id,
                "admin.enterprise_structure.revision.edit",
            )

        expired = UserAccount(
            tenant_id=tenant_id,
            email=f"expired.{uuid.uuid4().hex[:8]}@gate04h.local",
            full_name="Expired Editor",
            status="active",
        )
        db.add(expired)
        db.flush()
        db.add(
            SecurityAccessAssignment(
                tenant_id=tenant_id,
                subject_type="user",
                user_id=expired.id,
                role_id=roles["structure_editor"].id,
                scope_type="organization",
                ends_at=utc_now() - timedelta(minutes=1),
                status="active",
                granted_by_user_id=bootstrap_id,
            )
        )
        unit = OrganizationUnit(
            tenant_id=tenant_id,
            code=f"UNIT-{uuid.uuid4().hex[:6]}",
            name="Scoped Unit",
            status="active",
        )
        db.add(unit)
        db.flush()
        scoped = UserAccount(
            tenant_id=tenant_id,
            email=f"scoped.{uuid.uuid4().hex[:8]}@gate04h.local",
            full_name="Scoped Editor",
            status="active",
        )
        db.add(scoped)
        db.flush()
        db.add(
            SecurityAccessAssignment(
                tenant_id=tenant_id,
                subject_type="user",
                user_id=scoped.id,
                role_id=roles["structure_editor"].id,
                scope_type="organization-unit",
                scope_unit_id=unit.id,
                status="active",
                granted_by_user_id=bootstrap_id,
            )
        )
        db.commit()
        with pytest.raises(HTTPException):
            require_enterprise_permission(
                db,
                tenant_id,
                expired.id,
                "admin.enterprise_structure.revision.edit",
            )
        context = require_enterprise_permission(
            db,
            tenant_id,
            scoped.id,
            "admin.enterprise_structure.revision.edit",
        )
        with pytest.raises(HTTPException):
            require_organization_scope(context)

        permission_keys = {item.key for item in db.scalars(select(PermissionCatalog)).all()}
        assert set().union(*STRUCTURE_ROLE_PERMISSIONS.values()) <= permission_keys
        results.update(
            {
                "same_user_approve_publish": "covered_by_four_eyes_test",
                "cross_tenant": "PASS",
                "expired_assignment": "PASS",
                "invalid_scope": "PASS",
            }
        )
        _write_json("sod_tests.json", {"status": "PASS", "results": results})
        _write_json(
            "sod_matrix.json",
            {
                "status": "PASS",
                "roles": {key: sorted(value) for key, value in STRUCTURE_ROLE_PERMISSIONS.items()},
            },
        )
