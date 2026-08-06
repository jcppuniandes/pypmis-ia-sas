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
)
from app.modules.enterprise_structure.importer.models import ExistingNode, TenantSnapshot
from app.modules.enterprise_structure.models import EnterpriseWorkspaceClassification, EnterpriseWorkspaceLink


def load_tenant_snapshot(db: Session, tenant_code: str, requested_by: str | None = None) -> TenantSnapshot:
    normalized_tenant = tenant_code.strip().lower().replace("_", "-")
    tenant = next(
        (item for item in db.scalars(select(Tenant)).all() if item.slug.lower().replace("_", "-") == normalized_tenant),
        None,
    )
    if tenant is None:
        raise LookupError(f"Tenant not found: {tenant_code}")

    workspaces = list(
        db.scalars(
            select(EnterpriseWorkspace)
            .where(EnterpriseWorkspace.tenant_id == tenant.id)
            .order_by(EnterpriseWorkspace.sort_order, EnterpriseWorkspace.id)
        ).all()
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
                external_key=str(metadata.get("external_key") or "").strip().upper(),
                code=item.code,
                name=item.name,
                node_type=item.workspace_type_code,
                status=item.status,
                sort_order=item.sort_order,
                metadata=metadata,
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

    classifications = {
        (item.workspace_id, item.category_set_code, item.category_item_code)
        for item in db.scalars(
            select(EnterpriseWorkspaceClassification).where(EnterpriseWorkspaceClassification.tenant_id == tenant.id)
        ).all()
    }
    links = {
        (item.source_workspace_id, item.target_workspace_id, item.relationship_type)
        for item in db.scalars(
            select(EnterpriseWorkspaceLink).where(EnterpriseWorkspaceLink.tenant_id == tenant.id)
        ).all()
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
        published_categories={code: item.content_json for (kind, code), item in latest.items() if kind == "catalog"},
        user_emails=user_emails,
        organization_unit_codes=organization_unit_codes,
        existing_release_codes=release_codes,
        requester_has_manage_permission=requester_permission,
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
