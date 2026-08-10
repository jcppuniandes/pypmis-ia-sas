"""Transactional publication of the already-applied Enterprise Structure CORE."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domain.models import EnterpriseWorkspace, SecurityEvent, Tenant, UserAccount
from app.modules.enterprise_structure.importer.inventory import protected_source_hash
from app.modules.enterprise_structure.importer.models import CorePublishReport, EnterpriseStructureImport
from app.modules.enterprise_structure.importer.normalizer import internal_code
from app.modules.enterprise_structure.importer.security import (
    ActorAuthorizationError,
    require_actor_with_permission,
)
from app.modules.enterprise_structure.importer.validator import build_dry_run
from app.modules.enterprise_structure.models import (
    EnterpriseCoreRelease,
    EnterpriseStrategicObjective,
    EnterpriseWorkspaceClassification,
    EnterpriseWorkspaceLink,
)
from app.modules.enterprise_structure.record_codes import plan_record_codes

PUBLISH_PERMISSION = "admin.enterprise_structure.publish"
PUBLISH_EVENT_TYPE = "enterprise_structure.core_published"
UNPUBLISH_EVENT_TYPE = "enterprise_structure.core_unpublished"
APPROVED_TENANT_ID = 1
APPROVED_TENANT_NAME = "P&P Ingeniería y Proyectos"
APPROVED_TENANT_SLUG = "pyp-ingenieria-proyectos"
APPROVED_CURRENCY = "COP"
APPROVED_RELEASE_CODE = "ES-PYP-CORE-RECONCILED-20260809"
LOCKED_TABLES = (
    "tenants",
    "enterprise_workspaces",
    "enterprise_workspace_classifications",
    "enterprise_workspace_links",
    "enterprise_strategic_objectives",
    "enterprise_core_releases",
    "security_events",
    "user_accounts",
)


class CorePublishError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def publish_core(
    db: Session,
    configuration: EnterpriseStructureImport,
    *,
    source_file: str | Path,
    tenant_code: str,
    release_code: str,
    expected_hash: str,
    expected_canonical_hash: str,
    expected_source_hash: str,
    actor_email: str,
    approved: bool,
    failure_injection: str | None = None,
) -> CorePublishReport:
    """Publish in the caller-owned transaction without reapplying CORE data."""

    if not approved:
        raise CorePublishError("EXPLICIT_APPROVAL_REQUIRED", "Publish requires --approved")
    release_code = release_code.strip().upper()
    if release_code != APPROVED_RELEASE_CODE or configuration.metadata.release_code != release_code:
        raise CorePublishError("RELEASE_APPROVAL_MISMATCH", release_code)

    source_path = Path(source_file)
    raw_hash = _file_hash(source_path)
    if raw_hash != expected_hash.strip().lower():
        raise CorePublishError("EXPECTED_HASH_MISMATCH", f"raw expected {expected_hash}, observed {raw_hash}")
    canonical_hash = build_dry_run(configuration).input_hash
    if canonical_hash != expected_canonical_hash.strip().lower():
        raise CorePublishError(
            "EXPECTED_HASH_MISMATCH",
            f"canonical expected {expected_canonical_hash}, observed {canonical_hash}",
        )

    _lock_publication_tables(db)
    if _file_hash(source_path) != raw_hash:
        raise CorePublishError("INPUT_CHANGED_DURING_PUBLISH", "The approved YAML changed after lock acquisition")

    tenant = _resolve_approved_tenant(db, tenant_code)
    actor = _require_actor(db, tenant.id, actor_email)
    snapshot, errors = _build_and_validate_snapshot(db, tenant, configuration)
    if errors:
        raise CorePublishError("PUBLISH_SOURCE_CHANGED", "; ".join(errors))
    content_fingerprint = _sha256(snapshot)
    source_hash = protected_source_hash(db)

    existing = db.scalar(
        select(EnterpriseCoreRelease).where(
            EnterpriseCoreRelease.tenant_id == tenant.id,
            EnterpriseCoreRelease.release_code == release_code,
        )
    )
    if existing is not None:
        if (
            existing.state == "published"
            and existing.source_hash == raw_hash
            and existing.canonical_hash == canonical_hash
            and existing.content_fingerprint == content_fingerprint
        ):
            return _report(
                existing,
                tenant,
                actor,
                source_hash,
                expected_source_hash,
                outcome="ALREADY_PUBLISHED",
                mutation_count=0,
                audit_event_id=None,
            )
        raise CorePublishError("RELEASE_ALREADY_PUBLISHED", "The release code exists with different state or content")

    if source_hash != expected_source_hash.strip().lower():
        raise CorePublishError(
            "PUBLISH_SOURCE_CHANGED",
            f"expected source {expected_source_hash}, observed {source_hash}",
        )

    previous = db.scalar(
        select(EnterpriseCoreRelease)
        .where(
            EnterpriseCoreRelease.tenant_id == tenant.id,
            EnterpriseCoreRelease.state == "published",
        )
        .order_by(EnterpriseCoreRelease.published_at.desc(), EnterpriseCoreRelease.id.desc())
        .limit(1)
    )
    now = utc_now()
    statuses = Counter(item["status"] for item in snapshot["workspaces"])
    release = EnterpriseCoreRelease(
        tenant_id=tenant.id,
        release_code=release_code,
        release_name=configuration.metadata.release_name,
        revision_number=(previous.revision_number + 1) if previous else 1,
        state="published",
        source_hash=raw_hash,
        canonical_hash=canonical_hash,
        content_fingerprint=content_fingerprint,
        source_release_code=configuration.metadata.release_code,
        previous_release_id=previous.id if previous else None,
        base_content_fingerprint=content_fingerprint,
        snapshot_json=snapshot,
        workspace_count=len(snapshot["workspaces"]),
        objective_count=len(snapshot["strategic_objectives"]),
        classification_count=len(snapshot["classifications"]),
        link_count=len(snapshot["links"]),
        validation_json={"valid": True, "errors": [], "conflicts": []},
        diff_hash=hashlib.sha256(b"[]").hexdigest(),
        created_at=now,
        created_by_user_id=actor.id,
        updated_at=now,
        published_at=now,
        published_by_user_id=actor.id,
    )
    db.add(release)
    db.flush()
    if failure_injection == "after_release":
        raise CorePublishError("INJECTED_FAILURE", "after_release")

    event = SecurityEvent(
        tenant_id=tenant.id,
        user_id=actor.id,
        event_type=PUBLISH_EVENT_TYPE,
        outcome="success",
        target_type="EnterpriseCoreRelease",
        target_id=release.id,
        metadata_json={
            "tenant_id": tenant.id,
            "tenant_slug": tenant.slug,
            "release_code": release.release_code,
            "actor": actor.email,
            "raw_hash": raw_hash,
            "canonical_hash": canonical_hash,
            "content_fingerprint": content_fingerprint,
            "workspace_count": release.workspace_count,
            "objective_count": release.objective_count,
            "classification_count": release.classification_count,
            "link_count": release.link_count,
            "published_at": now.isoformat(),
            "previous_release": previous.release_code if previous else None,
            "status_transitions": [],
            "operational_statuses": dict(sorted(statuses.items())),
            "result": "published",
        },
        occurred_at=now,
    )
    db.add(event)
    db.flush()
    return _report(
        release,
        tenant,
        actor,
        source_hash,
        expected_source_hash,
        outcome="SUCCESS",
        mutation_count=2,
        audit_event_id=event.id,
    )


def rollback_core_publication(
    db: Session,
    *,
    tenant_code: str,
    release_code: str,
    actor_email: str,
    reason: str,
) -> EnterpriseCoreRelease:
    """Logical publication rollback only; applied workspaces are never removed or changed."""

    tenant = _resolve_approved_tenant(db, tenant_code)
    actor = _require_actor(db, tenant.id, actor_email)
    release = db.scalar(
        select(EnterpriseCoreRelease)
        .where(
            EnterpriseCoreRelease.tenant_id == tenant.id,
            EnterpriseCoreRelease.release_code == release_code.strip().upper(),
        )
        .with_for_update()
    )
    if release is None:
        raise CorePublishError("RELEASE_NOT_FOUND", release_code)
    if release.state != "published":
        raise CorePublishError("RELEASE_NOT_PUBLISHED", release.release_code)
    reason = reason.strip()
    if not reason:
        raise CorePublishError("ROLLBACK_REASON_REQUIRED", "A reason is mandatory")
    now = utc_now()
    release.state = "unpublished"
    release.unpublished_at = now
    release.unpublished_by_user_id = actor.id
    release.rollback_reason = reason
    db.add(
        SecurityEvent(
            tenant_id=tenant.id,
            user_id=actor.id,
            event_type=UNPUBLISH_EVENT_TYPE,
            outcome="success",
            target_type="EnterpriseCoreRelease",
            target_id=release.id,
            metadata_json={
                "tenant_id": tenant.id,
                "tenant_slug": tenant.slug,
                "release_code": release.release_code,
                "actor": actor.email,
                "reason": reason,
                "result": "unpublished",
                "workspace_mutations": 0,
            },
            occurred_at=now,
        )
    )
    db.flush()
    return release


def _build_and_validate_snapshot(
    db: Session,
    tenant: Tenant,
    configuration: EnterpriseStructureImport,
) -> tuple[dict[str, Any], list[str]]:
    errors: list[str] = []
    workspaces = list(
        db.scalars(
            select(EnterpriseWorkspace)
            .where(EnterpriseWorkspace.tenant_id == tenant.id)
            .order_by(EnterpriseWorkspace.id)
            .with_for_update()
        ).all()
    )
    objectives = list(
        db.scalars(
            select(EnterpriseStrategicObjective)
            .where(EnterpriseStrategicObjective.tenant_id == tenant.id)
            .order_by(EnterpriseStrategicObjective.code)
        ).all()
    )
    classifications = list(
        db.scalars(
            select(EnterpriseWorkspaceClassification)
            .where(EnterpriseWorkspaceClassification.tenant_id == tenant.id)
            .order_by(
                EnterpriseWorkspaceClassification.workspace_id,
                EnterpriseWorkspaceClassification.category_set_code,
                EnterpriseWorkspaceClassification.category_item_code,
            )
        ).all()
    )
    links = list(
        db.scalars(
            select(EnterpriseWorkspaceLink)
            .where(EnterpriseWorkspaceLink.tenant_id == tenant.id)
            .order_by(EnterpriseWorkspaceLink.id)
        ).all()
    )
    expected_nodes = {item.external_key: item for item in configuration.nodes}
    by_key = {str(item.external_key or "").upper(): item for item in workspaces}
    by_id = {item.id: item for item in workspaces}
    if len(workspaces) != 14:
        errors.append(f"workspaces={len(workspaces)}, expected=14")
    if len(by_key) != len(workspaces) or "" in by_key:
        errors.append("external_key uniqueness/integrity failed")
    if len({item.record_code for item in workspaces}) != len(workspaces):
        errors.append("record_code uniqueness failed")
    if set(by_key) != set(expected_nodes):
        errors.append("external_key set differs from approved YAML")
    roots = [item for item in workspaces if item.parent_id is None]
    if len(roots) != 1 or (roots and roots[0].external_key != "ENT-PYP"):
        errors.append(f"root_count={len(roots)}")
    planned_codes = plan_record_codes(configuration.nodes)
    for key, node in expected_nodes.items():
        workspace = by_key.get(key)
        if workspace is None:
            continue
        parent = by_id.get(workspace.parent_id) if workspace.parent_id else None
        parent_key = parent.external_key if parent else None
        expected = (
            node.code,
            node.name,
            internal_code(node.node_type.value),
            node.parent_external_key,
            node.status.value.lower(),
            node.sort_order or 0,
            planned_codes[key],
        )
        observed = (
            workspace.code,
            workspace.name,
            workspace.workspace_type_code,
            parent_key,
            workspace.status,
            workspace.sort_order,
            workspace.record_code,
        )
        if observed != expected:
            errors.append(f"workspace {key} differs: {observed!r}")
    for workspace in workspaces:
        seen: set[int] = set()
        current = workspace
        while current.parent_id is not None:
            if current.id in seen:
                errors.append(f"hierarchy cycle at workspace {workspace.id}")
                break
            seen.add(current.id)
            parent = by_id.get(current.parent_id)
            if parent is None:
                errors.append(f"broken/cross-tenant parent at workspace {current.id}")
                break
            current = parent
    if any(item.workspace_type_code in {"property", "facility"} for item in workspaces):
        errors.append("PROPERTY/FACILITY is outside Gate 03")

    expected_objectives = {
        item.code: (
            item.name,
            item.strategic_line,
            item.priority,
            item.horizon,
            item.responsible_area,
            item.active,
            item.description or "",
        )
        for item in configuration.strategic_objectives
    }
    observed_objectives = {
        item.code: (
            item.name,
            item.strategic_line,
            item.priority,
            item.horizon,
            item.responsible_area,
            item.active,
            item.description,
        )
        for item in objectives
    }
    if len(objectives) != 7 or observed_objectives != expected_objectives:
        errors.append(f"strategic objectives differ/count={len(objectives)}")

    expected_classifications = {
        (
            item.workspace_external_key,
            internal_code(item.category_set_code),
            internal_code(item.category_item_code),
        )
        for item in configuration.classifications
    }
    observed_classifications = {
        (
            str(by_id[item.workspace_id].external_key),
            item.category_set_code,
            item.category_item_code,
        )
        for item in classifications
        if item.workspace_id in by_id
    }
    if len(classifications) != 26 or observed_classifications != expected_classifications:
        errors.append(f"classifications differ/count={len(classifications)}")
    required_responsible = {
        ("BU-PYP-CONS", "responsible-area", "consulting"),
        ("BU-PYP-PMO", "responsible-area", "pmo-aas"),
        ("BU-PYP-TEC", "responsible-area", "technology"),
        ("BU-PYP-CONST", "responsible-area", "construction"),
    }
    if not required_responsible.issubset(observed_classifications):
        errors.append("required responsible-area classifications differ")
    allowed_strategic_types = {"portfolio", "program", "project"}
    if any(
        category == "strategic-objective" and by_key[key].workspace_type_code not in allowed_strategic_types
        for key, category, _item in observed_classifications
        if key in by_key
    ):
        errors.append("strategic-objective applied outside Portfolio/Program/Project")
    if links or configuration.links:
        errors.append(f"links={len(links)}, expected=0")

    snapshot = {
        "tenant": {
            "id": tenant.id,
            "name": tenant.name,
            "slug": tenant.slug,
            "currency": tenant.base_currency,
        },
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
            for item in workspaces
        ],
        "strategic_objectives": [
            {
                "code": item.code,
                "name": item.name,
                "strategic_line": item.strategic_line,
                "priority": item.priority,
                "horizon": item.horizon,
                "responsible_area": item.responsible_area,
                "active": item.active,
                "description": item.description,
            }
            for item in objectives
        ],
        "classifications": [
            {
                "workspace_id": item.workspace_id,
                "workspace_external_key": by_id[item.workspace_id].external_key,
                "category_set_code": item.category_set_code,
                "category_item_code": item.category_item_code,
            }
            for item in classifications
            if item.workspace_id in by_id
        ],
        "links": [],
    }
    return snapshot, errors


def _resolve_approved_tenant(db: Session, tenant_code: str) -> Tenant:
    normalized = tenant_code.strip().lower().replace("_", "-")
    tenant = db.scalar(select(Tenant).where(Tenant.slug == normalized).with_for_update())
    if tenant is None:
        raise CorePublishError("TENANT_NOT_FOUND", tenant_code)
    identity = (tenant.id, tenant.name, tenant.slug, tenant.base_currency)
    expected = (APPROVED_TENANT_ID, APPROVED_TENANT_NAME, APPROVED_TENANT_SLUG, APPROVED_CURRENCY)
    if identity != expected:
        raise CorePublishError("CROSS_TENANT_PUBLISH_BLOCKED", f"observed tenant identity {identity!r}")
    return tenant


def _require_actor(db: Session, tenant_id: int, actor_email: str) -> UserAccount:
    try:
        return require_actor_with_permission(db, tenant_id, actor_email, PUBLISH_PERMISSION)
    except ActorAuthorizationError as exc:
        raise CorePublishError(exc.code, str(exc)) from exc


def _lock_publication_tables(db: Session) -> None:
    if db.get_bind().dialect.name == "postgresql":
        db.execute(text(f"LOCK TABLE {', '.join(LOCKED_TABLES)} IN SHARE ROW EXCLUSIVE MODE"))


def _report(
    release: EnterpriseCoreRelease,
    tenant: Tenant,
    actor: UserAccount,
    source_hash: str,
    expected_source_hash: str,
    *,
    outcome: str,
    mutation_count: int,
    audit_event_id: int | None,
) -> CorePublishReport:
    snapshot = release.snapshot_json or {}
    statuses = Counter(item.get("status", "") for item in snapshot.get("workspaces", []))
    previous_code = None
    if release.previous_release_id is not None:
        previous = release.previous_release_id
        previous_code = str(previous)
    return CorePublishReport(
        outcome=outcome,
        release_id=release.id,
        release_code=release.release_code,
        release_name=release.release_name,
        state=release.state,
        tenant_id=tenant.id,
        tenant_code=tenant.slug,
        actor=actor.email,
        input_hash=release.source_hash,
        canonical_input_hash=release.canonical_hash,
        source_snapshot_hash=source_hash,
        approved_source_snapshot_hash=expected_source_hash.strip().lower(),
        content_fingerprint=release.content_fingerprint,
        workspace_count=release.workspace_count,
        objective_count=release.objective_count,
        classification_count=release.classification_count,
        link_count=release.link_count,
        operational_statuses=dict(sorted(statuses.items())),
        status_transitions=[],
        previous_release=previous_code,
        mutation_count=mutation_count,
        audit_event_id=audit_event_id,
        published_at=release.published_at,
    )


def _file_hash(path: Path) -> str:
    if not path.is_file():
        raise CorePublishError("INPUT_NOT_FOUND", str(path))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha256(payload: Any) -> str:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()
