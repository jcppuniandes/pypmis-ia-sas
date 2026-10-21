"""Explicit provisioning of granular O1A duties; never invoked by a GET."""

from sqlalchemy import select

from app.domain.models import PermissionCatalog, SecurityRole, SecurityRolePermission, Tenant
from app.modules.enterprise_structure.constants import PERMISSION_SEED
from app.modules.enterprise_structure.permissions import WORKSPACE_OPERATION_PERMISSIONS

ACTIONS = (
    "read",
    "binding.manage",
    "legacy.execute",
    "period.open",
    "period.review",
    "period.close",
    "period.publish",
    "period.reopen",
    "admin.configure",
    "admin.publish",
)
READ = {"read"}
OPERATE = READ | {"period.open", "period.review", "legacy.execute"}
ROLE_ACTIONS = {
    "organization_admin": set(ACTIONS),
    "operational_administrator": set(ACTIONS),
    "project_administrator": OPERATE | {"binding.manage"},
    "project_manager": OPERATE | {"period.close", "period.publish", "period.reopen"},
    "project_controls_manager": OPERATE | {"period.close", "period.publish", "period.reopen"},
    "planner_scheduler": OPERATE,
    "cost_controller": OPERATE,
    "progress_engineer": READ,
    "executive_viewer": READ,
}


def ensure_operational_permissions(db, tenant_id, actor_id):
    """Provision catalog/roles only; assign no new actor or Project authority."""
    db.scalar(select(Tenant).where(Tenant.id == tenant_id).with_for_update())
    permissions = {r.key: r for r in db.scalars(select(PermissionCatalog))}
    for action in ACTIONS:
        key = f"operational_context.{action}"
        if key not in permissions:
            row = PermissionCatalog(
                key=key,
                resource="operational_context",
                action=action,
                description=f"Operational Context: {action}",
                risk_level="high" if action in {"binding.manage", "period.publish", "admin.publish"} else "standard",
                status="active",
            )
            db.add(row)
            db.flush()
            permissions[key] = row
    workspace_definitions = {
        definition[0]: definition for definition in PERMISSION_SEED if definition[0] in WORKSPACE_OPERATION_PERMISSIONS
    }
    for key in WORKSPACE_OPERATION_PERMISSIONS:
        if key not in permissions:
            _, resource, action, description, risk_level = workspace_definitions[key]
            row = PermissionCatalog(
                key=key,
                resource=resource,
                action=action,
                description=description,
                risk_level=risk_level,
                status="active",
            )
            db.add(row)
            db.flush()
            permissions[key] = row
    roles = {r.code: r for r in db.scalars(select(SecurityRole).where(SecurityRole.tenant_id == tenant_id))}
    for code, actions in ROLE_ACTIONS.items():
        if code not in roles:
            row = SecurityRole(
                tenant_id=tenant_id,
                code=code,
                name=code.replace("_", " ").title(),
                description="Granular O1A duty; scoped assignment required.",
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
            permission = permissions[f"operational_context.{action}"]
            if permission.id not in existing:
                db.add(
                    SecurityRolePermission(
                        tenant_id=tenant_id,
                        role_id=roles[code].id,
                        permission_id=permission.id,
                        granted_by_user_id=actor_id,
                    )
                )
        for key in WORKSPACE_OPERATION_PERMISSIONS:
            permission = permissions[key]
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
