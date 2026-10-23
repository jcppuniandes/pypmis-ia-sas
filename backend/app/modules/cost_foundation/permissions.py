"""Cost duties are provisioned explicitly; no actor assignment or GET seeding."""

from sqlalchemy import select

from app.domain.models import PermissionCatalog, SecurityRole, SecurityRolePermission, Tenant

ACTIONS = (
    "read",
    "cbs.edit",
    "code.edit",
    "account.edit",
    "mapping.edit",
    "rate.edit",
    "rate.publish",
    "apu.edit",
    "apu.publish",
    "budget.prepare",
    "budget.submit",
    "budget.review",
    "budget.approve",
    "baseline.prepare",
    "baseline.approve",
    "phasing.edit",
    "period.close",
    "reserve.manage",
    "admin.configure",
    "admin.publish",
    "fx.edit",
    "fx.publish",
    "actual.import",
    "actual.approve",
    "actual.adjust",
    "commitment.reconcile",
    "commitment.verify",
)
EDITOR = {
    "read",
    "cbs.edit",
    "code.edit",
    "account.edit",
    "mapping.edit",
    "rate.edit",
    "apu.edit",
    "budget.prepare",
    "budget.submit",
    "baseline.prepare",
    "phasing.edit",
    "actual.import",
    "commitment.reconcile",
}
MANAGER = EDITOR | {
    "budget.review",
    "budget.approve",
    "baseline.approve",
    "rate.publish",
    "apu.publish",
    "actual.approve",
    "actual.adjust",
    "commitment.verify",
    "period.close",
}
ROLE_ACTIONS = {
    "organization_admin": set(ACTIONS),
    "operational_administrator": set(ACTIONS),
    "project_manager": MANAGER,
    "project_controls_manager": MANAGER,
    "cost_controller": EDITOR,
    "cost_manager": MANAGER,
    "planner_scheduler": {"read"},
    "scope_manager": {"read"},
    "executive_viewer": {"read"},
}


def ensure_cost_permissions(db, tenant_id, actor_id):
    db.scalar(select(Tenant).where(Tenant.id == tenant_id).with_for_update())
    permissions = {r.key: r for r in db.scalars(select(PermissionCatalog))}
    for action in ACTIONS:
        key = f"cost.{action}"
        if key not in permissions:
            row = PermissionCatalog(
                key=key,
                resource="cost",
                action=action,
                description=f"Cost {action}",
                risk_level="high"
                if action == "reserve.manage" or action.endswith(("approve", "publish", "adjust", "verify"))
                else "standard",
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
                description="Canonical Cost scoped duty",
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
            permission = permissions[f"cost.{action}"]
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
