"""Explicit catalog provisioning does not assign actors or mutate source authorities."""

from fastapi import HTTPException
from sqlalchemy import inspect, select

from app.domain.models import PermissionCatalog, SecurityRole, SecurityRolePermission, Tenant
from app.modules.enterprise_structure.permissions import WORKSPACE_OPERATION_PERMISSIONS

ACTIONS = (
    "read",
    "create",
    "edit",
    "submit",
    "review",
    "approve",
    "assumption.edit",
    "etc.calculate",
    "eac.view",
    "dashboard.view",
    "executive.view",
    "lookahead.view",
    "lookahead.generate",
    "report.read",
    "report.publish",
    "report.republish",
    "admin.configure",
    "admin.publish",
)
EDITOR = {
    "read",
    "create",
    "edit",
    "submit",
    "assumption.edit",
    "etc.calculate",
    "eac.view",
    "dashboard.view",
    "lookahead.view",
    "lookahead.generate",
    "report.read",
}
MANAGER = EDITOR | {"review", "approve", "executive.view", "report.publish", "report.republish"}
ROLE_ACTIONS = {
    "organization_admin": set(ACTIONS),
    "operational_administrator": set(ACTIONS),
    "project_manager": MANAGER,
    "project_controls_manager": MANAGER,
    "forecast_manager": MANAGER,
    "forecast_controller": EDITOR,
    "cost_controller": EDITOR,
    "planner_scheduler": EDITOR,
    "progress_engineer": EDITOR,
    "executive_viewer": {"read", "eac.view", "dashboard.view", "executive.view", "lookahead.view", "report.read"},
}


def require_forecast_schema(db):
    if not inspect(db.get_bind()).has_table("forecast_versions"):
        raise HTTPException(409, detail={"code": "FORECAST_MIGRATION_REQUIRED"})


def ensure_forecast_permissions(db, tenant_id, actor_id):
    require_forecast_schema(db)
    db.scalar(select(Tenant).where(Tenant.id == tenant_id).with_for_update())
    keys = {f"forecast.{a}" for a in ACTIONS}
    prerequisites = {
        "scope_foundation.read",
        "operational_context.read",
        "progress.read",
        "progress.evm.view",
        "cost.read",
        "schedule_foundation.read",
        "awp.read",
        *WORKSPACE_OPERATION_PERMISSIONS,
    }
    permissions = {row.key: row for row in db.scalars(select(PermissionCatalog))}
    for key in keys | prerequisites:
        if key not in permissions:
            resource, action = key.rsplit(".", 1)
            row = PermissionCatalog(
                key=key,
                resource=resource,
                action=action,
                description=f"Governed Forecast prerequisite or duty {key}",
                risk_level="high" if key.endswith(("approve", "publish", "republish")) else "standard",
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
                description="Governed Forecast scoped duty",
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
        for key in {*(f"forecast.{a}" for a in actions), *prerequisites}:
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
