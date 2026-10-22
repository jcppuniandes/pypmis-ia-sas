"""Explicit role duties. Provision catalogs, never actor assignments or GET facts."""

from sqlalchemy import select

from app.domain.models import PermissionCatalog, SecurityRole, SecurityRolePermission, Tenant

ACTIONS = (
    "read",
    "cwa.manage",
    "package.edit",
    "package.review",
    "package.release",
    "mapping.edit",
    "dependency.edit",
    "constraint.raise",
    "constraint.clear",
    "constraint.waive",
    "readiness.assess",
    "admin.configure",
    "admin.publish",
)
EDITOR = {
    "read",
    "cwa.manage",
    "package.edit",
    "mapping.edit",
    "dependency.edit",
    "constraint.raise",
    "readiness.assess",
}
MANAGER = EDITOR | {"package.review", "package.release", "constraint.clear", "constraint.waive"}
ROLE_ACTIONS = {
    "organization_admin": set(ACTIONS),
    "operational_administrator": set(ACTIONS),
    "project_manager": MANAGER,
    "project_controls_manager": MANAGER,
    "construction_manager": MANAGER,
    "planner_scheduler": EDITOR,
    "scope_manager": EDITOR,
    "bim_manager": {"read"},
    "bim_coordinator": {"read"},
    "cost_controller": {"read"},
    "document_controller": {"read", "constraint.raise"},
    "executive_viewer": {"read"},
}


def ensure_awp_permissions(db, tenant_id, actor_id):
    db.scalar(select(Tenant).where(Tenant.id == tenant_id).with_for_update())
    permissions = {row.key: row for row in db.scalars(select(PermissionCatalog))}
    for action in ACTIONS:
        key = f"awp.{action}"
        if key not in permissions:
            row = PermissionCatalog(
                key=key,
                resource="awp",
                action=action,
                description=f"AWP {action}",
                risk_level="high" if action.endswith(("release", "waive", "publish")) else "standard",
                status="active",
            )
            db.add(row)
            db.flush()
            permissions[key] = row
    roles = {row.code: row for row in db.scalars(select(SecurityRole).where(SecurityRole.tenant_id == tenant_id))}
    for code, actions in ROLE_ACTIONS.items():
        if code not in roles:
            row = SecurityRole(
                tenant_id=tenant_id,
                code=code,
                name=code.replace("_", " ").title(),
                description="Canonical AWP scoped duty",
                is_system=True,
                status="active",
            )
            db.add(row)
            db.flush()
            roles[code] = row
        existing = set(
            db.scalars(
                select(SecurityRolePermission.permission_id).where(
                    SecurityRolePermission.tenant_id == tenant_id, SecurityRolePermission.role_id == roles[code].id
                )
            )
        )
        for action in actions:
            permission = permissions[f"awp.{action}"]
            if permission.id not in existing:
                db.add(
                    SecurityRolePermission(
                        tenant_id=tenant_id,
                        role_id=roles[code].id,
                        permission_id=permission.id,
                        granted_by_user_id=actor_id,
                    )
                )
    db.flush()
