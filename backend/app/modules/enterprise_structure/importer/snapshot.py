"""Read-only tenant snapshot used by Nivel 2B dry-run validation."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domain.models import (
    AdminConfiguration,
    EnterpriseWorkspace,
    OrganizationUnit,
    PermissionCatalog,
    SecurityAccessAssignment,
    SecurityEvent,
    SecurityGroupMember,
    SecurityRolePermission,
    Tenant,
    UserAccount,
    WorkspaceModuleSetting,
)
from app.modules.enterprise_structure.importer.models import (
    ExistingNode,
    SnapshotIntegrityIssue,
    TenantSnapshot,
)
from app.modules.enterprise_structure.models import (
    EnterpriseStrategicObjective,
    EnterpriseWorkspaceClassification,
    EnterpriseWorkspaceLink,
)


def load_tenant_snapshot(db: Session, tenant_code: str, requested_by: str | None = None) -> TenantSnapshot:
    normalized_tenant = tenant_code.strip().lower().replace("_", "-")
    tenant = next(
        (item for item in db.scalars(select(Tenant)).all() if item.slug.lower().replace("_", "-") == normalized_tenant),
        None,
    )
    if tenant is None:
        raise LookupError(f"Tenant not found: {tenant_code}")

    all_workspaces = list(db.scalars(select(EnterpriseWorkspace).order_by(EnterpriseWorkspace.id)).all())
    workspace_tenant_ids = {item.id: item.tenant_id for item in all_workspaces}
    workspaces = [item for item in all_workspaces if item.tenant_id == tenant.id]
    child_ids: dict[int, list[int]] = {}
    for item in all_workspaces:
        if item.parent_id is not None:
            child_ids.setdefault(item.parent_id, []).append(item.id)

    all_classifications = list(db.scalars(select(EnterpriseWorkspaceClassification)).all())
    all_links = list(db.scalars(select(EnterpriseWorkspaceLink)).all())
    all_module_settings = list(db.scalars(select(WorkspaceModuleSetting)).all())
    integrity_issues: list[SnapshotIntegrityIssue] = []
    for item in all_classifications:
        owner_tenant = workspace_tenant_ids.get(item.workspace_id)
        if owner_tenant is None and item.tenant_id == tenant.id:
            integrity_issues.append(
                SnapshotIntegrityIssue(
                    code="BROKEN_CLASSIFICATION_REFERENCE",
                    reference=str(item.id),
                    message=f"Classification references missing workspace {item.workspace_id}.",
                )
            )
        elif owner_tenant != item.tenant_id and tenant.id in {owner_tenant, item.tenant_id}:
            integrity_issues.append(
                SnapshotIntegrityIssue(
                    code="CROSS_TENANT_CLASSIFICATION",
                    reference=str(item.id),
                    message=f"Classification tenant {item.tenant_id} does not match workspace tenant {owner_tenant}.",
                )
            )
    for item in all_links:
        source_tenant = workspace_tenant_ids.get(item.source_workspace_id)
        target_tenant = workspace_tenant_ids.get(item.target_workspace_id)
        if (source_tenant is None or target_tenant is None) and item.tenant_id == tenant.id:
            integrity_issues.append(
                SnapshotIntegrityIssue(
                    code="BROKEN_LINK_REFERENCE",
                    reference=str(item.id),
                    message="Link source or target workspace does not exist.",
                )
            )
        elif (
            source_tenant != target_tenant or item.tenant_id not in {source_tenant, target_tenant}
        ) and tenant.id in {item.tenant_id, source_tenant, target_tenant}:
            integrity_issues.append(
                SnapshotIntegrityIssue(
                    code="CROSS_TENANT_LINK",
                    reference=str(item.id),
                    message="Link tenant and endpoint tenants are inconsistent.",
                )
            )
    nodes = []
    for item in workspaces:
        defaults = item.defaults_json or {}
        metadata = defaults.get("_enterprise", {}) if isinstance(defaults, dict) else {}
        if not isinstance(metadata, dict):
            metadata = {}
        nodes.append(
            ExistingNode(
                id=item.id,
                parent_id=item.parent_id,
                external_key=str(item.external_key or metadata.get("external_key") or "").strip().upper(),
                code=item.code,
                name=item.name,
                node_type=item.workspace_type_code,
                status=item.status,
                sort_order=item.sort_order,
                metadata=metadata,
                record_code=item.record_code,
                references={
                    "children": len(child_ids.get(item.id, [])),
                    "classifications": sum(1 for ref in all_classifications if ref.workspace_id == item.id),
                    "links": sum(
                        1
                        for ref in all_links
                        if ref.source_workspace_id == item.id or ref.target_workspace_id == item.id
                    ),
                    "module_settings": sum(1 for ref in all_module_settings if ref.workspace_id == item.id),
                },
                child_ids=tuple(sorted(child_ids.get(item.id, []))),
            )
        )

    configurations = list(
        db.scalars(
            select(AdminConfiguration).where(
                AdminConfiguration.tenant_id == tenant.id,
                AdminConfiguration.status == "published",
            )
        ).all()
    )
    latest: dict[tuple[str, str], AdminConfiguration] = {}
    for item in configurations:
        key = (item.kind, item.code)
        if key not in latest or latest[key].revision < item.revision:
            latest[key] = item

    strategic_objectives = list(
        db.scalars(
            select(EnterpriseStrategicObjective).where(
                EnterpriseStrategicObjective.tenant_id == tenant.id,
                EnterpriseStrategicObjective.active.is_(True),
            )
        ).all()
    )
    published_categories = {
        code: dict(item.content_json)
        for (kind, code), item in latest.items()
        if kind == "catalog"
    }
    if strategic_objectives:
        strategic_category = dict(published_categories.get("strategic-objective", {}))
        strategic_category["items"] = [
            {"code": item.code, "label": item.name}
            for item in sorted(strategic_objectives, key=lambda objective: objective.code)
        ]
        published_categories["strategic-objective"] = strategic_category

    classifications = {
        (item.workspace_id, item.category_set_code, item.category_item_code)
        for item in all_classifications
        if item.tenant_id == tenant.id
    }
    links = {
        (item.source_workspace_id, item.target_workspace_id, item.relationship_type)
        for item in all_links
        if item.tenant_id == tenant.id
    }
    events = list(
        db.scalars(
            select(SecurityEvent).where(
                SecurityEvent.tenant_id == tenant.id,
                SecurityEvent.event_type.in_(
                    {"enterprise_structure.import_applied", "enterprise_structure.import_published"}
                ),
            )
        ).all()
    )
    release_codes = {
        str(item.metadata_json.get("release_code", "")).strip().upper()
        for item in events
        if isinstance(item.metadata_json, dict) and item.metadata_json.get("release_code")
    }
    user_emails = {
        item.email.strip().lower()
        for item in db.scalars(select(UserAccount).where(UserAccount.tenant_id == tenant.id)).all()
    }
    organization_unit_codes = {
        item.code.strip().upper()
        for item in db.scalars(select(OrganizationUnit).where(OrganizationUnit.tenant_id == tenant.id)).all()
    }
    requester_permission = _has_manage_permission(db, tenant.id, requested_by) if requested_by else None
    return TenantSnapshot(
        tenant_id=tenant.id,
        tenant_code=tenant.slug.upper(),
        nodes=nodes,
        classifications=classifications,
        links=links,
        published_type_codes={code for (kind, code), _ in latest.items() if kind == "workspace_type"},
        published_categories=published_categories,
        user_emails=user_emails,
        organization_unit_codes=organization_unit_codes,
        existing_release_codes=release_codes,
        requester_has_manage_permission=requester_permission,
        workspace_tenant_ids=workspace_tenant_ids,
        integrity_issues=integrity_issues,
    )


def _has_manage_permission(db: Session, tenant_id: int, email: str) -> bool | None:
    user = db.scalar(
        select(UserAccount).where(
            UserAccount.tenant_id == tenant_id,
            UserAccount.email == email.strip().lower(),
            UserAccount.status == "active",
        )
    )
    if user is None:
        return None
    group_ids = set(
        db.scalars(
            select(SecurityGroupMember.group_id).where(
                SecurityGroupMember.tenant_id == tenant_id,
                SecurityGroupMember.user_id == user.id,
            )
        ).all()
    )
    now = utc_now()
    assignments = [
        item
        for item in db.scalars(
            select(SecurityAccessAssignment).where(
                SecurityAccessAssignment.tenant_id == tenant_id,
                SecurityAccessAssignment.status == "active",
            )
        ).all()
        if (item.user_id == user.id or item.group_id in group_ids)
        and (item.starts_at is None or item.starts_at <= now)
        and (item.ends_at is None or item.ends_at > now)
    ]
    if not assignments:
        return False
    role_ids = {item.role_id for item in assignments}
    return (
        db.scalar(
            select(SecurityRolePermission.id)
            .join(PermissionCatalog, PermissionCatalog.id == SecurityRolePermission.permission_id)
            .where(
                SecurityRolePermission.tenant_id == tenant_id,
                SecurityRolePermission.role_id.in_(role_ids),
                PermissionCatalog.key == "admin.enterprise_structure.manage",
                PermissionCatalog.status == "active",
            )
        )
        is not None
    )
