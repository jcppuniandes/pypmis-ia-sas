"""Explicit provisioning only. 4D GETs never create roles or grants."""

from sqlalchemy import select

from app.domain.models import PermissionCatalog, SecurityRole, SecurityRolePermission, Tenant

ACTIONS = {"read", "admin.configure", "admin.publish"}
READERS = {
    "organization_admin",
    "operational_administrator",
    "project_manager",
    "project_controls_manager",
    "planner_scheduler",
    "scope_manager",
    "bim_manager",
    "bim_coordinator",
    "construction_manager",
    "cost_controller",
    "document_controller",
    "executive_viewer",
}


def ensure_four_d_permissions(db, tenant_id, actor_id):
    db.scalar(select(Tenant).where(Tenant.id == tenant_id).with_for_update())
    catalog = {row.key: row for row in db.scalars(select(PermissionCatalog))}
    for action in ACTIONS:
        key = f"four_d.{action}"
        if key not in catalog:
            row = PermissionCatalog(
                key=key,
                resource="four_d",
                action=action,
                description=f"Governed 4D {action}",
                risk_level="high" if action == "admin.publish" else "standard",
                status="active",
            )
            db.add(row)
            db.flush()
            catalog[key] = row
    roles = {row.code: row for row in db.scalars(select(SecurityRole).where(SecurityRole.tenant_id == tenant_id))}
    for code in READERS:
        if code not in roles:
            row = SecurityRole(
                tenant_id=tenant_id,
                code=code,
                name=code.replace("_", " ").title(),
                description="4D visualization duty; scoped assignment required",
                is_system=True,
                status="active",
            )
            db.add(row)
            db.flush()
            roles[code] = row
        actions = ACTIONS if code in {"organization_admin", "operational_administrator"} else {"read"}
        existing = set(
            db.scalars(
                select(SecurityRolePermission.permission_id).where(
                    SecurityRolePermission.tenant_id == tenant_id, SecurityRolePermission.role_id == roles[code].id
                )
            )
        )
        for action in actions:
            permission = catalog[f"four_d.{action}"]
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
