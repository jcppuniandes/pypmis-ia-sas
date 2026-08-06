"""Idempotent dry-run diff against the existing tenant structure."""

from __future__ import annotations

from app.modules.enterprise_structure.importer.models import (
    DiffAction,
    DiffEntry,
    EnterpriseNodeInput,
    EnterpriseStructureImport,
    ExistingNode,
    NodeType,
    TenantSnapshot,
)
from app.modules.enterprise_structure.importer.normalizer import internal_code


def build_diff(configuration: EnterpriseStructureImport, snapshot: TenantSnapshot | None) -> list[DiffEntry]:
    if snapshot is None:
        return [
            DiffEntry(entity="node", key=item.external_key, action=DiffAction.CREATE, reason="Tenant not resolved")
            for item in configuration.nodes
        ]

    result: list[DiffEntry] = []
    matched_nodes: dict[str, ExistingNode] = {}
    existing_by_id = {item.id: item for item in snapshot.nodes}
    by_external = {item.external_key: item for item in snapshot.nodes if item.external_key}
    by_code = {item.code.upper(): item for item in snapshot.nodes}
    active_root = next(
        (
            item
            for item in snapshot.nodes
            if item.parent_id is None and item.node_type == "enterprise" and item.status != "archived"
        ),
        None,
    )

    for node in configuration.nodes:
        existing = by_external.get(node.external_key)
        if existing is None and node.node_type == NodeType.ENTERPRISE and node.parent_external_key is None:
            existing = active_root
        code_owner = by_code.get(node.code)
        if existing is None and code_owner is not None:
            result.append(
                DiffEntry(
                    entity="node",
                    key=node.external_key,
                    action=DiffAction.CONFLICT,
                    reason=f"Code {node.code} belongs to another declarative identity",
                )
            )
            continue
        if existing is not None and code_owner is not None and code_owner.id != existing.id:
            result.append(
                DiffEntry(
                    entity="node",
                    key=node.external_key,
                    action=DiffAction.CONFLICT,
                    reason=f"Code {node.code} is already used by workspace {code_owner.id}",
                )
            )
            continue
        if existing is None:
            result.append(
                DiffEntry(entity="node", key=node.external_key, action=DiffAction.CREATE, reason="New external_key")
            )
            continue
        matched_nodes[node.external_key] = existing
        action = DiffAction.UNCHANGED if _node_matches(node, existing, existing_by_id) else DiffAction.UPDATE
        reason = "All controlled fields match" if action == DiffAction.UNCHANGED else "Controlled fields differ"
        result.append(DiffEntry(entity="node", key=node.external_key, action=action, reason=reason))

    objective_items = snapshot.published_categories.get("strategic-objective", {}).get("items", [])
    objectives_by_code = {str(item.get("code", "")).upper(): item for item in objective_items}
    for objective in configuration.strategic_objectives:
        existing = objectives_by_code.get(objective.code)
        if existing is None:
            action, reason = DiffAction.CREATE, "New strategic objective"
        elif str(existing.get("label", "")).strip() == objective.name:
            action, reason = DiffAction.UNCHANGED, "Objective code and name match"
        else:
            action, reason = DiffAction.UPDATE, "Objective label differs"
        result.append(DiffEntry(entity="strategic_objective", key=objective.code, action=action, reason=reason))

    for item in configuration.classifications:
        workspace = matched_nodes.get(item.workspace_external_key)
        identity = (workspace.id, internal_code(item.category_set_code), internal_code(item.category_item_code)) if workspace else None
        action = DiffAction.UNCHANGED if identity in snapshot.classifications else DiffAction.CREATE
        result.append(
            DiffEntry(
                entity="classification",
                key=f"{item.workspace_external_key}:{item.category_set_code}:{item.category_item_code}",
                action=action,
                reason="Existing assignment" if action == DiffAction.UNCHANGED else "New assignment",
            )
        )

    for item in configuration.links:
        source = matched_nodes.get(item.source_external_key)
        target = matched_nodes.get(item.target_external_key)
        identity = (source.id, target.id, item.relationship_type) if source and target else None
        action = DiffAction.UNCHANGED if identity in snapshot.links else DiffAction.CREATE
        result.append(
            DiffEntry(
                entity="link",
                key=f"{item.source_external_key}:{item.target_external_key}:{item.relationship_type}",
                action=action,
                reason="Existing relationship" if action == DiffAction.UNCHANGED else "New relationship",
            )
        )
    return result


def _node_matches(
    node: EnterpriseNodeInput,
    existing: ExistingNode,
    existing_by_id: dict[int, ExistingNode],
) -> bool:
    metadata = existing.metadata
    current_parent = existing_by_id.get(existing.parent_id) if existing.parent_id is not None else None
    current_parent_key = ""
    if current_parent is not None:
        current_parent_key = current_parent.external_key or current_parent.code.upper()
    return all(
        (
            existing.code.upper() == node.code,
            existing.name.strip() == node.name,
            existing.node_type == internal_code(node.node_type.value),
            existing.status.upper() == node.status.value,
            existing.sort_order == (node.sort_order or 0),
            str(metadata.get("description") or "").strip() == (node.description or ""),
            str(metadata.get("region_code") or "").upper() == (node.region_code or ""),
            str(metadata.get("external_key") or "").upper() == node.external_key,
            current_parent_key == (node.parent_external_key or ""),
        )
    )
