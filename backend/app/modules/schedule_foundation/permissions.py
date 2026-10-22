"""Explicit minimal Schedule duties, scoped to canonical Workspaces."""

from sqlalchemy import select

from app.domain.models import PermissionCatalog, SecurityRole, SecurityRolePermission, Tenant
from app.modules.enterprise_structure.constants import PERMISSION_SEED
from app.modules.enterprise_structure.permissions import WORKSPACE_OPERATION_PERMISSIONS

ACTIONS = (
    "read",
    "register.edit",
    "version.edit",
    "import",
    "validate",
    "review",
    "accept",
    "mapping.edit",
    "baseline.prepare",
    "baseline.submit",
    "baseline.review",
    "baseline.approve",
    "export",
    "period.associate",
    "admin.configure",
    "admin.publish",
)
EDITOR = {
    "read",
    "register.edit",
    "version.edit",
    "import",
    "validate",
    "review",
    "mapping.edit",
    "baseline.prepare",
    "baseline.submit",
    "export",
    "period.associate",
}
MANAGER = EDITOR | {"accept", "baseline.review", "baseline.approve"}
ROLE_ACTIONS = {
    "organization_admin": set(ACTIONS),
    "operational_administrator": set(ACTIONS),
    "project_manager": MANAGER,
    "project_controls_manager": MANAGER,
    "planner_scheduler": EDITOR,
    "scope_manager": {"read"},
    "bim_manager": {"read"},
    "bim_coordinator": {"read"},
    "construction_manager": {"read"},
    "cost_controller": {"read"},
    "document_controller": {"read"},
    "executive_viewer": {"read"},
}


def ensure_schedule_permissions(db, tenant_id, actor_id):
    db.scalar(select(Tenant).where(Tenant.id == tenant_id).with_for_update())
    permissions = {row.key: row for row in db.scalars(select(PermissionCatalog))}
    definitions = {
        definition[0]: definition[1:]
        for definition in PERMISSION_SEED
        if definition[0] in WORKSPACE_OPERATION_PERMISSIONS
    }
    definitions.update(
        {
            "operational_context.read": ("operational_context", "read", "Read canonical context", "standard"),
            "scope_foundation.read": ("scope_foundation", "read", "Read governed Scope foundation", "standard"),
        }
    )
    definitions.update(
        {
            f"schedule_foundation.{action}": (
                "schedule_foundation",
                action,
                f"Schedule foundation {action}",
                "high" if action.endswith(("accept", "approve", "publish")) else "standard",
            )
            for action in ACTIONS
        }
    )
    for key, (resource, action, description, risk) in definitions.items():
        if key not in permissions:
            row = PermissionCatalog(
                key=key, resource=resource, action=action, description=description, risk_level=risk, status="active"
            )
            db.add(row)
            db.flush()
            permissions[key] = row
    roles = {row.code: row for row in db.scalars(select(SecurityRole).where(SecurityRole.tenant_id == tenant_id))}
    read_keys = {"scope_foundation.read", "operational_context.read", *WORKSPACE_OPERATION_PERMISSIONS}
    for code, actions in ROLE_ACTIONS.items():
        if code not in roles:
            row = SecurityRole(
                tenant_id=tenant_id,
                code=code,
                name=code.replace("_", " ").title(),
                description="Granular Schedule duty; explicit scoped assignment required",
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
        for key in read_keys | {f"schedule_foundation.{action}" for action in actions}:
            if permissions[key].id not in existing:
                db.add(
                    SecurityRolePermission(
                        tenant_id=tenant_id,
                        role_id=roles[code].id,
                        permission_id=permissions[key].id,
                        granted_by_user_id=actor_id,
                    )
                )
    db.flush()
