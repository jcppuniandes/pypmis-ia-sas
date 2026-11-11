"""Engineering permissions are provisioned explicitly; never assign users here."""

from fastapi import HTTPException
from sqlalchemy import inspect, select

from app.domain.models import PermissionCatalog, SecurityRole, SecurityRolePermission, Tenant
from app.modules.enterprise_structure.permissions import WORKSPACE_OPERATION_PERMISSIONS

ACTIONS = (
    "read",
    "deliverable.create",
    "deliverable.edit",
    "revision.create",
    "revision.edit",
    "revision.supersede",
    "document.link",
    "review.submit",
    "review.perform",
    "review.comment",
    "review.respond",
    "review.close",
    "review.check",
    "review.approve",
    "ifc.release",
    "mapping.edit",
    "design_package.manage",
    "interface.manage",
    "admin.configure",
    "admin.publish",
)
AUTHOR = {
    "deliverable.create",
    "deliverable.edit",
    "revision.create",
    "revision.edit",
    "revision.supersede",
    "document.link",
    "review.submit",
    "review.respond",
    "mapping.edit",
    "design_package.manage",
    "interface.manage",
}
ROLE_ACTIONS = {
    "organization_admin": set(ACTIONS),
    "operational_administrator": set(ACTIONS),
    "engineering_author": AUTHOR | {"read"},
    "engineering_reviewer": {"read", "review.perform", "review.comment", "review.close"},
    "engineering_checker": {"read", "review.check"},
    "engineering_approver": {"read", "review.approve"},
    "engineering_ifc_releaser": {"read", "ifc.release"},
    "project_manager": {"read"},
    "project_controls_manager": {"read"},
    "executive_viewer": {"read"},
}


def require_engineering_schema(db):
    # Use this session's connection, not another pooled checkout. Installation
    # never bootstraps a missing migration as a side effect of a read.
    if not inspect(db.connection()).has_table("engineering_releases"):
        raise HTTPException(409, detail={"code": "ENGINEERING_MIGRATION_REQUIRED"})


def ensure_engineering_permissions(db, tenant_id, actor_id):
    require_engineering_schema(db)
    if db.scalar(select(Tenant).where(Tenant.id == tenant_id).with_for_update()) is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND"})
    keys = {f"engineering.{a}" for a in ACTIONS}
    prerequisites = {
        "enterprise_structure.read",
        "operational_context.read",
        *WORKSPACE_OPERATION_PERMISSIONS,
    }
    permissions = {row.key: row for row in db.scalars(select(PermissionCatalog))}
    for key in sorted(keys | prerequisites):
        if key not in permissions:
            resource, action = key.rsplit(".", 1)
            row = PermissionCatalog(
                key=key,
                resource=resource,
                action=action,
                description=f"Governed Engineering prerequisite or duty {key}",
                risk_level="high" if key.endswith(("approve", "publish", "release")) else "standard",
                status="active",
            )
            db.add(row)
            db.flush()
            permissions[key] = row
    roles = {row.code: row for row in db.scalars(select(SecurityRole).where(SecurityRole.tenant_id == tenant_id))}
    for code, actions in ROLE_ACTIONS.items():
        role = roles.get(code)
        if role is None:
            # Create only new Engineering roles. Unrelated roles remain under
            # their own provisioning workflows.
            if not code.startswith("engineering_"):
                continue
            role = SecurityRole(
                tenant_id=tenant_id,
                code=code,
                name=code.replace("_", " ").title(),
                description="Governed Engineering scoped duty",
                is_system=True,
                status="active",
            )
            db.add(role)
            db.flush()
        assigned = set(
            db.scalars(
                select(SecurityRolePermission.permission_id).where(
                    SecurityRolePermission.tenant_id == tenant_id,
                    SecurityRolePermission.role_id == role.id,
                )
            )
        )
        for key in sorted({*(f"engineering.{a}" for a in actions), *prerequisites}):
            if permissions[key].id not in assigned:
                db.add(
                    SecurityRolePermission(
                        tenant_id=tenant_id,
                        role_id=role.id,
                        permission_id=permissions[key].id,
                        granted_by_user_id=actor_id,
                    )
                )
    db.flush()
