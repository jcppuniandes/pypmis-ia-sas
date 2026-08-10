"""Transactional, idempotent and auditable apply for an approved CORE release."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domain.models import (
    EnterpriseWorkspace,
    SecurityEvent,
    Tenant,
    UserAccount,
)
from app.modules.enterprise_structure.importer.inventory import protected_source_hash
from app.modules.enterprise_structure.importer.models import (
    AppliedWorkspace,
    CoreApplyReport,
    DiffAction,
    EnterpriseNodeInput,
    EnterpriseStructureImport,
    TenantIdentityChange,
)
from app.modules.enterprise_structure.importer.normalizer import internal_code
from app.modules.enterprise_structure.importer.security import (
    ActorAuthorizationError,
    require_actor_with_permission,
)
from app.modules.enterprise_structure.importer.snapshot import load_tenant_snapshot
from app.modules.enterprise_structure.importer.validator import build_dry_run
from app.modules.enterprise_structure.models import (
    EnterpriseStrategicObjective,
    EnterpriseWorkspaceClassification,
    EnterpriseWorkspaceLink,
)
from app.modules.enterprise_structure.record_codes import plan_record_codes

MANAGE_PERMISSION = "admin.enterprise_structure.manage"
CORE_EVENT_TYPE = "enterprise_structure.core_applied"
LOCKED_TABLES = (
    "tenants",
    "enterprise_workspaces",
    "enterprise_workspace_classifications",
    "enterprise_workspace_links",
    "workspace_module_settings",
    "admin_configurations",
    "security_events",
    "user_accounts",
    "enterprise_strategic_objectives",
)


class CoreApplyError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


def apply_core(
    db: Session,
    configuration: EnterpriseStructureImport,
    *,
    source_file: str | Path,
    tenant_code: str,
    expected_hash: str,
    expected_source_hash: str,
    actor_email: str,
    approved_tenant_name: str,
    approved_tenant_slug: str,
    failure_injection: str | None = None,
) -> CoreApplyReport:
    """Apply inside the caller-owned transaction; this function never commits."""

    source_path = Path(source_file)
    observed_hash = _file_hash(source_path)
    if observed_hash != expected_hash.strip().lower():
        raise CoreApplyError("INPUT_HASH_MISMATCH", f"expected {expected_hash}, observed {observed_hash}")

    _lock_protected_tables(db)
    if _file_hash(source_path) != observed_hash:
        raise CoreApplyError("INPUT_CHANGED_DURING_APPLY", "The canonical YAML changed after lock acquisition")

    approved_slug = approved_tenant_slug.strip().lower()
    approved_name = approved_tenant_name.strip()
    tenant = _resolve_tenant(db, tenant_code, approved_slug, configuration)
    actor = _require_actor(db, tenant.id, actor_email)
    _validate_gate_approvals(configuration, tenant, approved_name, approved_slug)

    current_source_hash = protected_source_hash(db)
    prior_success = _prior_success_event(db, tenant.id, configuration.metadata.release_code, observed_hash)
    replay_ready = prior_success is not None and not _final_state_errors(
        db,
        tenant,
        configuration,
        approved_name,
        approved_slug,
    )
    if current_source_hash != expected_source_hash.strip().lower() and not replay_ready:
        raise CoreApplyError(
            "SOURCE_SNAPSHOT_CHANGED",
            f"expected {expected_source_hash}, observed {current_source_hash}",
        )

    snapshot = load_tenant_snapshot(db, tenant.slug, actor.email)
    if replay_ready:
        snapshot.tenant_code = configuration.metadata.tenant_code
    dry_run = build_dry_run(configuration, snapshot)
    if not dry_run.valid:
        error_codes = sorted({item.code for item in dry_run.findings if item.severity.value == "ERROR"})
        raise CoreApplyError(
            "DRY_RUN_INVALID",
            f"revalidation produced {dry_run.summary['errors']} errors: {', '.join(error_codes)}",
        )
    if dry_run.summary["conflict"] or dry_run.summary["update"]:
        raise CoreApplyError("DIFF_CHANGED", "Immediate revalidation contains conflict or update actions")
    if not replay_ready:
        _require_first_apply_diff(dry_run.summary)
    elif dry_run.summary["create"] != 0:
        raise CoreApplyError("IDEMPOTENT_DIFF_CHANGED", "An applied release still contains CREATE actions")

    now = utc_now()
    old_tenant_name = tenant.name
    old_tenant_slug = tenant.slug
    tenant_changed = tenant.name != approved_name or tenant.slug != approved_slug
    if tenant_changed:
        slug_owner = db.scalar(select(Tenant.id).where(Tenant.slug == approved_slug, Tenant.id != tenant.id))
        if slug_owner is not None:
            raise CoreApplyError("TENANT_SLUG_CONFLICT", f"slug belongs to tenant {slug_owner}")
        tenant.name = approved_name
        tenant.slug = approved_slug

    planned_codes = plan_record_codes(configuration.nodes)
    nodes_by_key = {item.external_key: item for item in configuration.nodes}
    reconciliation = {item.external_key: item for item in configuration.reconciliation}
    workspaces_by_id = {
        item.id: item
        for item in db.scalars(
            select(EnterpriseWorkspace)
            .where(EnterpriseWorkspace.tenant_id == tenant.id)
            .order_by(EnterpriseWorkspace.id)
            .with_for_update()
        ).all()
    }
    workspaces_by_key = {item.external_key: item for item in workspaces_by_id.values() if item.external_key}
    resolved: dict[str, EnterpriseWorkspace] = {}
    adopted_effective: set[str] = set()

    for external_key, decision in reconciliation.items():
        workspace = workspaces_by_id.get(decision.existing_id)
        if workspace is None:
            raise CoreApplyError("ADOPTION_TARGET_NOT_FOUND", f"workspace {decision.existing_id}")
        if workspace.tenant_id != tenant.id:
            raise CoreApplyError("CROSS_TENANT_ADOPTION", f"workspace {workspace.id}")
        resolved[external_key] = workspace

    for external_key, workspace in resolved.items():
        node = nodes_by_key[external_key]
        if workspace.code != node.code:
            workspace.code = f"__GATE02B_CODE_{workspace.id}"
        if workspace.record_code != planned_codes[external_key]:
            workspace.record_code = f"__GATE02B_RECORD_{workspace.id}"
    db.flush()

    for external_key, workspace in resolved.items():
        node = nodes_by_key[external_key]
        parent = resolved.get(node.parent_external_key) if node.parent_external_key else None
        changed = _apply_workspace_fields(
            workspace,
            node,
            parent_id=parent.id if parent else None,
            record_code=planned_codes[external_key],
            release_code=configuration.metadata.release_code,
            now=now,
        )
        if changed:
            adopted_effective.add(external_key)
    db.flush()

    created_ids: list[int] = []
    for external_key in dry_run.topological_order:
        if external_key in resolved:
            continue
        node = nodes_by_key[external_key]
        existing = workspaces_by_key.get(external_key)
        if existing is not None:
            resolved[external_key] = existing
            continue
        parent = resolved.get(node.parent_external_key) if node.parent_external_key else None
        if node.parent_external_key and parent is None:
            raise CoreApplyError("PARENT_NOT_RESOLVED", node.parent_external_key)
        workspace = EnterpriseWorkspace(
            tenant_id=tenant.id,
            parent_id=parent.id if parent else None,
            workspace_type_code=internal_code(node.node_type.value),
            code=node.code,
            external_key=node.external_key,
            record_code=planned_codes[external_key],
            name=node.name,
            status=node.status.value.lower(),
            defaults_json={"_enterprise": _node_metadata(node, configuration.metadata.release_code)},
            sort_order=node.sort_order or 0,
            version=1,
            created_by_user_id=actor.id,
            created_at=now,
            updated_at=now,
        )
        db.add(workspace)
        db.flush()
        resolved[external_key] = workspace
        created_ids.append(workspace.id)

    if failure_injection == "after_workspaces":
        raise CoreApplyError("INJECTED_FAILURE", "after_workspaces")

    objective_created = 0
    objectives_by_code = {
        item.code: item
        for item in db.scalars(
            select(EnterpriseStrategicObjective).where(EnterpriseStrategicObjective.tenant_id == tenant.id)
        ).all()
    }
    for objective in configuration.strategic_objectives:
        existing = objectives_by_code.get(objective.code)
        if existing is not None:
            if _objective_values(existing) != _objective_input_values(objective, configuration.metadata.release_code):
                raise CoreApplyError("OBJECTIVE_CONFLICT", objective.code)
            continue
        record = EnterpriseStrategicObjective(
            tenant_id=tenant.id,
            code=objective.code,
            name=objective.name,
            strategic_line=objective.strategic_line,
            priority=objective.priority,
            horizon=objective.horizon,
            responsible_area=objective.responsible_area,
            active=objective.active,
            description=objective.description or "",
            source_release_code=configuration.metadata.release_code,
            created_by_user_id=actor.id,
            created_at=now,
            updated_at=now,
        )
        db.add(record)
        objectives_by_code[objective.code] = record
        objective_created += 1
    db.flush()

    existing_classifications = {
        (item.workspace_id, item.category_set_code, item.category_item_code)
        for item in db.scalars(
            select(EnterpriseWorkspaceClassification).where(EnterpriseWorkspaceClassification.tenant_id == tenant.id)
        ).all()
    }
    classification_created = 0
    classification_keys: list[str] = []
    for classification in configuration.classifications:
        workspace = resolved[classification.workspace_external_key]
        category_code = internal_code(classification.category_set_code)
        item_code = internal_code(classification.category_item_code)
        identity = (workspace.id, category_code, item_code)
        classification_keys.append(f"{classification.workspace_external_key}:{category_code}:{item_code}")
        if identity in existing_classifications:
            continue
        db.add(
            EnterpriseWorkspaceClassification(
                tenant_id=tenant.id,
                workspace_id=workspace.id,
                category_set_code=category_code,
                category_item_code=item_code,
                created_by_user_id=actor.id,
                created_at=now,
            )
        )
        existing_classifications.add(identity)
        classification_created += 1
    db.flush()

    if failure_injection == "after_classifications":
        raise CoreApplyError("INJECTED_FAILURE", "after_classifications")

    final_errors = _final_state_errors(db, tenant, configuration, approved_name, approved_slug)
    if final_errors:
        raise CoreApplyError("FINAL_INTEGRITY_FAILED", "; ".join(final_errors))

    adopted_ids = {key: decision.existing_id for key, decision in reconciliation.items()}
    idempotent_replay = (
        not tenant_changed
        and not adopted_effective
        and not created_ids
        and objective_created == 0
        and classification_created == 0
    )
    unchanged = (
        len(configuration.nodes)
        + len(configuration.strategic_objectives)
        + len(configuration.classifications)
        - len(adopted_effective)
        - len(created_ids)
        - objective_created
        - classification_created
    )
    summary = {
        "adopt": len(adopted_effective),
        "create": len(created_ids) + objective_created + classification_created,
        "workspace_create": len(created_ids),
        "objective_create": objective_created,
        "classification_create": classification_created,
        "tenant_update": int(tenant_changed),
        "update": 0,
        "unchanged": unchanged,
        "conflict": 0,
    }
    reconciliation_hash = _reconciliation_hash(configuration)
    event = SecurityEvent(
        tenant_id=tenant.id,
        user_id=actor.id,
        event_type=CORE_EVENT_TYPE,
        outcome="success",
        target_type="EnterpriseStructureCore",
        target_id=tenant.id,
        metadata_json={
            "actor": actor.email,
            "tenant_id": tenant.id,
            "release_code": configuration.metadata.release_code,
            "input_hash": observed_hash,
            "canonical_input_hash": dry_run.input_hash,
            "reconciliation_hash": reconciliation_hash,
            "source_snapshot_hash": current_source_hash,
            "approved_source_snapshot_hash": expected_source_hash.strip().lower(),
            "adopted_ids": adopted_ids,
            "created_workspace_ids": created_ids,
            "objectives_count": len(configuration.strategic_objectives),
            "classifications_count": len(configuration.classifications),
            "old_tenant_name": old_tenant_name,
            "new_tenant_name": tenant.name,
            "old_tenant_slug": old_tenant_slug,
            "new_tenant_slug": tenant.slug,
            "timestamp": now.isoformat(),
            "outcome": "success",
            "idempotent_replay": idempotent_replay,
            "summary": summary,
        },
        occurred_at=now,
    )
    db.add(event)
    db.flush()

    workspace_results = []
    for external_key in dry_run.topological_order:
        workspace = resolved[external_key]
        if workspace.id in created_ids:
            action = DiffAction.CREATE
        elif external_key in adopted_effective:
            action = DiffAction.ADOPT
        else:
            action = DiffAction.UNCHANGED
        workspace_results.append(
            AppliedWorkspace(
                id=workspace.id,
                external_key=external_key,
                record_code=workspace.record_code,
                workspace_type=workspace.workspace_type_code,
                name=workspace.name,
                action=action,
            )
        )

    return CoreApplyReport(
        outcome="SUCCESS",
        release_code=configuration.metadata.release_code,
        tenant_code=tenant.slug,
        actor=actor.email,
        input_hash=observed_hash,
        canonical_input_hash=dry_run.input_hash,
        reconciliation_hash=reconciliation_hash,
        source_snapshot_hash=current_source_hash,
        approved_source_snapshot_hash=expected_source_hash.strip().lower(),
        idempotent_replay=idempotent_replay,
        tenant_change=TenantIdentityChange(
            tenant_id=tenant.id,
            old_name=old_tenant_name,
            new_name=tenant.name,
            old_slug=old_tenant_slug,
            new_slug=tenant.slug,
            currency=tenant.base_currency,
            changed=tenant_changed,
        ),
        adopted_ids=adopted_ids,
        created_workspace_ids=created_ids,
        objective_codes=sorted(objective.code for objective in configuration.strategic_objectives),
        classification_keys=sorted(classification_keys),
        workspaces=workspace_results,
        summary=summary,
        audit_event_id=event.id,
        occurred_at=now,
    )


def _lock_protected_tables(db: Session) -> None:
    if db.get_bind().dialect.name != "postgresql":
        return
    db.execute(text(f"LOCK TABLE {', '.join(LOCKED_TABLES)} IN SHARE ROW EXCLUSIVE MODE"))


def _resolve_tenant(
    db: Session,
    tenant_code: str,
    approved_slug: str,
    configuration: EnterpriseStructureImport,
) -> Tenant:
    normalized = tenant_code.strip().lower().replace("_", "-")
    tenant = db.scalar(
        select(Tenant).where(Tenant.slug.in_({normalized, approved_slug})).order_by(Tenant.id).with_for_update()
    )
    if tenant is not None:
        return tenant
    root_decision = next(
        (
            decision
            for decision in configuration.reconciliation
            if next(
                (node for node in configuration.nodes if node.external_key == decision.external_key),
                None,
            )
            and next(
                node for node in configuration.nodes if node.external_key == decision.external_key
            ).parent_external_key
            is None
        ),
        None,
    )
    if root_decision is not None:
        tenant = db.scalar(
            select(Tenant)
            .join(EnterpriseWorkspace, EnterpriseWorkspace.tenant_id == Tenant.id)
            .where(EnterpriseWorkspace.id == root_decision.existing_id)
            .with_for_update()
        )
    if tenant is None:
        raise CoreApplyError("TENANT_NOT_FOUND", tenant_code)
    return tenant


def _require_actor(db: Session, tenant_id: int, actor_email: str) -> UserAccount:
    try:
        return require_actor_with_permission(db, tenant_id, actor_email, MANAGE_PERMISSION)
    except ActorAuthorizationError as exc:
        raise CoreApplyError(exc.code, str(exc)) from exc


def _validate_gate_approvals(
    configuration: EnterpriseStructureImport,
    tenant: Tenant,
    approved_name: str,
    approved_slug: str,
) -> None:
    roots = [node for node in configuration.nodes if node.parent_external_key is None]
    if len(roots) != 1 or roots[0].external_key != "ENT-PYP":
        raise CoreApplyError("APPROVAL_ROOT_MISMATCH", "Expected the approved ENT-PYP root")
    if approved_name != roots[0].name or approved_slug != "pyp-ingenieria-proyectos":
        raise CoreApplyError("TENANT_APPROVAL_MISMATCH", "Approved final tenant identity is not exact")
    if tenant.id != 1 or tenant.base_currency != "COP":
        raise CoreApplyError("TENANT_APPROVAL_MISMATCH", "Expected tenant 1 with currency COP")
    expected_reconciliation = {"ENT-PYP": 1, "BU-PYP-PMO": 3, "BU-PYP-CONST": 2}
    observed_reconciliation = {item.external_key: item.existing_id for item in configuration.reconciliation}
    if observed_reconciliation != expected_reconciliation:
        raise CoreApplyError("ADOPTION_APPROVAL_MISMATCH", str(observed_reconciliation))
    if len(configuration.nodes) != 14 or len(configuration.nodes) - len(configuration.reconciliation) != 11:
        raise CoreApplyError("CREATE_APPROVAL_MISMATCH", "Expected 14 final nodes with exactly 11 creates")
    if len(configuration.strategic_objectives) != 7 or len(configuration.classifications) != 26:
        raise CoreApplyError("CONTENT_APPROVAL_MISMATCH", "Expected 7 objectives and 26 classifications")
    if configuration.links:
        raise CoreApplyError("LINK_APPROVAL_MISMATCH", "CORE apply expects zero links")
    if any(node.node_type.value in {"PROPERTY", "FACILITY"} for node in configuration.nodes):
        raise CoreApplyError("OUT_OF_SCOPE_NODE", "PROPERTY and FACILITY are outside CORE")


def _require_first_apply_diff(summary: dict[str, int]) -> None:
    expected = {
        "adopt": 3,
        "create": 44,
        "update": 0,
        "conflict": 0,
        "errors": 0,
        "warnings": 0,
        "hierarchy_errors": 0,
        "identity_conflicts": 0,
        "required_classification_missing": 0,
        "category_not_applicable": 0,
        "base_mutations": 0,
    }
    differences = {key: summary.get(key) for key, value in expected.items() if summary.get(key) != value}
    if differences:
        raise CoreApplyError("DIFF_CHANGED", f"Immediate dry-run differs: {differences}")


def _apply_workspace_fields(
    workspace: EnterpriseWorkspace,
    node: EnterpriseNodeInput,
    *,
    parent_id: int | None,
    record_code: str,
    release_code: str,
    now: Any,
) -> bool:
    before = _workspace_values(workspace)
    workspace.parent_id = parent_id
    workspace.workspace_type_code = internal_code(node.node_type.value)
    workspace.code = node.code
    workspace.external_key = node.external_key
    workspace.record_code = record_code
    workspace.name = node.name
    workspace.status = node.status.value.lower()
    workspace.sort_order = node.sort_order or 0
    defaults = dict(workspace.defaults_json or {})
    metadata = dict(defaults.get("_enterprise", {})) if isinstance(defaults.get("_enterprise", {}), dict) else {}
    metadata.update(_node_metadata(node, release_code))
    defaults["_enterprise"] = metadata
    workspace.defaults_json = defaults
    changed = before != _workspace_values(workspace)
    if changed:
        workspace.version += 1
        workspace.updated_at = now
    return changed


def _workspace_values(workspace: EnterpriseWorkspace) -> tuple[Any, ...]:
    return (
        workspace.parent_id,
        workspace.workspace_type_code,
        workspace.code,
        workspace.external_key,
        workspace.record_code,
        workspace.name,
        workspace.status,
        workspace.sort_order,
        json.dumps(workspace.defaults_json or {}, ensure_ascii=False, sort_keys=True),
    )


def _node_metadata(node: EnterpriseNodeInput, release_code: str) -> dict[str, Any]:
    return {
        "external_key": node.external_key,
        "description": node.description or "",
        "organization_unit_code": node.organization_unit_code,
        "responsible_email": node.responsible_email,
        "region_code": node.region_code or "",
        "valid_from": node.valid_from.isoformat() if node.valid_from else None,
        "valid_to": node.valid_to.isoformat() if node.valid_to else None,
        "source_release_code": release_code,
    }


def _objective_values(objective: EnterpriseStrategicObjective) -> tuple[Any, ...]:
    return (
        objective.name,
        objective.strategic_line,
        objective.priority,
        objective.horizon,
        objective.responsible_area,
        objective.active,
        objective.description,
        objective.source_release_code,
    )


def _objective_input_values(objective: Any, release_code: str) -> tuple[Any, ...]:
    return (
        objective.name,
        objective.strategic_line,
        objective.priority,
        objective.horizon,
        objective.responsible_area,
        objective.active,
        objective.description or "",
        release_code,
    )


def _prior_success_event(db: Session, tenant_id: int, release_code: str, input_hash: str) -> SecurityEvent | None:
    events = list(
        db.scalars(
            select(SecurityEvent)
            .where(
                SecurityEvent.tenant_id == tenant_id,
                SecurityEvent.event_type == CORE_EVENT_TYPE,
                SecurityEvent.outcome == "success",
            )
            .order_by(SecurityEvent.id.desc())
        ).all()
    )
    return next(
        (
            event
            for event in events
            if event.metadata_json.get("release_code") == release_code
            and event.metadata_json.get("input_hash") == input_hash
        ),
        None,
    )


def _final_state_errors(
    db: Session,
    tenant: Tenant,
    configuration: EnterpriseStructureImport,
    approved_name: str,
    approved_slug: str,
) -> list[str]:
    errors: list[str] = []
    if (tenant.id, tenant.name, tenant.slug, tenant.base_currency) != (1, approved_name, approved_slug, "COP"):
        errors.append("tenant identity")
    workspaces = list(
        db.scalars(
            select(EnterpriseWorkspace)
            .where(EnterpriseWorkspace.tenant_id == tenant.id)
            .order_by(EnterpriseWorkspace.id)
        ).all()
    )
    if len(workspaces) != len(configuration.nodes):
        errors.append(f"workspace count {len(workspaces)}")
    by_key = {item.external_key: item for item in workspaces if item.external_key}
    planned_codes = plan_record_codes(configuration.nodes)
    nodes_by_key = {node.external_key: node for node in configuration.nodes}
    for key, node in nodes_by_key.items():
        workspace = by_key.get(key)
        if workspace is None:
            errors.append(f"missing workspace {key}")
            continue
        parent_key = None
        if workspace.parent_id is not None:
            parent = next((item for item in workspaces if item.id == workspace.parent_id), None)
            parent_key = parent.external_key if parent else None
        if (
            workspace.code != node.code
            or workspace.record_code != planned_codes[key]
            or workspace.workspace_type_code != internal_code(node.node_type.value)
            or workspace.name != node.name
            or workspace.status != node.status.value.lower()
            or parent_key != node.parent_external_key
        ):
            errors.append(f"workspace mismatch {key}")
    if len(by_key) != len(configuration.nodes):
        errors.append("external_key completeness")
    roots = [item for item in workspaces if item.parent_id is None and item.status != "archived"]
    if len(roots) != 1:
        errors.append(f"root count {len(roots)}")
    if len({item.record_code for item in workspaces}) != len(workspaces):
        errors.append("record_code duplicates")
    if len({item.external_key for item in workspaces}) != len(workspaces):
        errors.append("external_key duplicates")

    objectives = list(
        db.scalars(
            select(EnterpriseStrategicObjective).where(EnterpriseStrategicObjective.tenant_id == tenant.id)
        ).all()
    )
    expected_objectives = {
        item.code: _objective_input_values(item, configuration.metadata.release_code)
        for item in configuration.strategic_objectives
    }
    observed_objectives = {item.code: _objective_values(item) for item in objectives}
    if observed_objectives != expected_objectives:
        errors.append("strategic objectives")

    classifications = {
        (item.workspace_id, item.category_set_code, item.category_item_code)
        for item in db.scalars(
            select(EnterpriseWorkspaceClassification).where(EnterpriseWorkspaceClassification.tenant_id == tenant.id)
        ).all()
    }
    expected_classifications = {
        (
            by_key[item.workspace_external_key].id,
            internal_code(item.category_set_code),
            internal_code(item.category_item_code),
        )
        for item in configuration.classifications
        if item.workspace_external_key in by_key
    }
    if classifications != expected_classifications:
        errors.append("classifications")
    link_count = db.scalar(
        select(func.count()).select_from(EnterpriseWorkspaceLink).where(EnterpriseWorkspaceLink.tenant_id == tenant.id)
    )
    if int(link_count or 0) != 0:
        errors.append("links")

    parent_by_id = {item.id: item.parent_id for item in workspaces}
    for workspace in workspaces:
        visited: set[int] = set()
        current_id: int | None = workspace.id
        while current_id is not None:
            if current_id in visited:
                errors.append("hierarchy cycle")
                break
            visited.add(current_id)
            current_id = parent_by_id.get(current_id)
    return sorted(set(errors))


def _file_hash(path: Path) -> str:
    if not path.is_file():
        raise CoreApplyError("INPUT_NOT_FOUND", str(path))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _reconciliation_hash(configuration: EnterpriseStructureImport) -> str:
    payload = [item.model_dump(mode="json") for item in configuration.reconciliation]
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
