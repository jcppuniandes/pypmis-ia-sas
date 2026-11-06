"""Progress permissions are explicitly provisioned without assigning any actor."""

from sqlalchemy import select

from app.domain.models import PermissionCatalog, SecurityRole, SecurityRolePermission, Tenant
from app.modules.enterprise_structure.constants import PERMISSION_SEED
from app.modules.enterprise_structure.permissions import WORKSPACE_OPERATION_PERMISSIONS

ACTIONS = (
    "read",
    "capture",
    "submit",
    "review",
    "approve",
    "quantity.certify",
    "milestone.certify",
    "rule.manage",
    "rule.publish",
    "admin.configure",
    "admin.publish",
    "baseline.prepare",
    "baseline.approve",
    "period.freeze",
    "period.publish",
    "evm.view",
)
EDITOR = {"read", "capture", "submit", "rule.manage", "baseline.prepare", "evm.view"}
MANAGER = EDITOR | {
    "review",
    "approve",
    "quantity.certify",
    "milestone.certify",
    "rule.publish",
    "baseline.approve",
    "period.freeze",
    "period.publish",
}
ROLE_ACTIONS = {
    "organization_admin": set(ACTIONS),
    "operational_administrator": set(ACTIONS),
    "project_manager": MANAGER,
    "project_controls_manager": MANAGER,
    "progress_controller": EDITOR,
    "progress_engineer": EDITOR,
    "progress_manager": MANAGER,
    "cost_controller": EDITOR,
    "cost_manager": {"read", "evm.view"},
    "scope_manager": {"read", "evm.view"},
    "planner_scheduler": {"read", "evm.view"},
    "executive_viewer": {"read", "evm.view"},
}


def ensure_progress_permissions(db, tenant_id, actor_id):
    db.scalar(select(Tenant).where(Tenant.id == tenant_id).with_for_update())
    permissions = {row.key: row for row in db.scalars(select(PermissionCatalog))}
    for action in ACTIONS:
        key = f"progress.{action}"
        if key not in permissions:
            row = PermissionCatalog(
                key=key,
                resource="progress",
                action=action,
                description=f"Governed Progress {action}",
                risk_level="high" if action.endswith(("approve", "publish", "certify", "freeze")) else "standard",
                status="active",
            )
            db.add(row)
            db.flush()
            permissions[key] = row
    # Canonical source/context reads are explicit prerequisites, not write duties.
    prerequisites = {"scope_foundation.read", "operational_context.read", *WORKSPACE_OPERATION_PERMISSIONS}
    definitions = {definition[0]: definition for definition in PERMISSION_SEED}
    for key in prerequisites:
        if key not in permissions:
            if key in definitions:
                _, resource, action, description, risk = definitions[key]
            else:
                resource, action = key.rsplit(".", 1)
                description, risk = "Read canonical Progress prerequisite", "standard"
            permission = PermissionCatalog(
                key=key, resource=resource, action=action, description=description, risk_level=risk, status="active"
            )
            db.add(permission)
            db.flush()
            permissions[key] = permission
    roles = {row.code: row for row in db.scalars(select(SecurityRole).where(SecurityRole.tenant_id == tenant_id))}
    for code, actions in ROLE_ACTIONS.items():
        if code not in roles:
            row = SecurityRole(
                tenant_id=tenant_id,
                code=code,
                name=code.replace("_", " ").title(),
                description="Canonical Progress scoped duty",
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
        for key in {*(f"progress.{action}" for action in actions), *prerequisites}:
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
