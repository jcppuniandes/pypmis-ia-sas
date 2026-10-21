"""Granular Scope duties. Explicit provisioning only, never in a read endpoint."""

from sqlalchemy import select

from app.domain.models import PermissionCatalog, SecurityRole, SecurityRolePermission, Tenant
from app.modules.enterprise_structure.constants import PERMISSION_SEED
from app.modules.enterprise_structure.permissions import WORKSPACE_OPERATION_PERMISSIONS

ACTIONS = (
    "read",
    "model.import",
    "model.review",
    "model.accept",
    "item.edit",
    "revision.prepare",
    "revision.submit",
    "revision.review",
    "revision.approve",
    "strategy.edit",
    "strategy.publish",
    "plan.edit",
    "plan.publish",
    "derived.edit",
    "admin.configure",
    "admin.publish",
)
READ = {"read"}
EDITOR = READ | {"item.edit", "revision.prepare", "revision.submit", "strategy.edit", "plan.edit", "derived.edit"}
ROLE_ACTIONS = {
    "organization_admin": set(ACTIONS),
    "operational_administrator": set(ACTIONS),
    "project_manager": EDITOR
    | {"revision.review", "revision.approve", "strategy.publish", "plan.publish", "model.review", "model.accept"},
    "project_controls_manager": EDITOR | {"revision.review", "revision.approve", "strategy.publish", "plan.publish"},
    "scope_manager": EDITOR | {"model.import", "model.review", "revision.review"},
    "bim_manager": EDITOR | {"model.import", "model.review", "model.accept"},
    "bim_coordinator": EDITOR | {"model.import", "model.review"},
    "planner_scheduler": READ | {"strategy.edit", "plan.edit", "derived.edit"},
    "cost_controller": READ,
    "construction_manager": READ | {"strategy.edit", "plan.edit", "derived.edit"},
    "document_controller": READ | {"model.import"},
    "executive_viewer": READ,
}


def ensure_scope_permissions(db, tenant_id, actor_id):
    db.scalar(select(Tenant).where(Tenant.id == tenant_id).with_for_update())
    permissions = {row.key: row for row in db.scalars(select(PermissionCatalog))}
    for action in ACTIONS:
        key = f"scope_foundation.{action}"
        if key not in permissions:
            row = PermissionCatalog(
                key=key,
                resource="scope_foundation",
                action=action,
                description=f"Scope Foundation: {action}",
                risk_level="high" if action.endswith(("approve", "publish", "accept")) else "standard",
                status="active",
            )
            db.add(row)
            db.flush()
            permissions[key] = row
    # Scope-specific roles need only O1A context reads and scoped navigation,
    # never implicit period, binding, legacy execution or administration duties.
    navigation = {
        definition[0]: definition for definition in PERMISSION_SEED if definition[0] in WORKSPACE_OPERATION_PERMISSIONS
    }
    read_keys = {"operational_context.read", *WORKSPACE_OPERATION_PERMISSIONS}
    for key in read_keys:
        if key not in permissions:
            if key in navigation:
                _, resource, action, description, risk = navigation[key]
            else:
                resource, action, description, risk = (
                    "operational_context",
                    "read",
                    "Read canonical operational context",
                    "standard",
                )
            row = PermissionCatalog(
                key=key, resource=resource, action=action, description=description, risk_level=risk, status="active"
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
                description="Granular canonical Scope duty; scoped assignment required.",
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
        for key in {*(f"scope_foundation.{action}" for action in actions), *read_keys}:
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
