"""Explicit field duties; catalog provisioning never assigns a user."""

from fastapi import HTTPException
from sqlalchemy import inspect, select

from app.domain.models import PermissionCatalog, SecurityRole, SecurityRolePermission, Tenant
from app.modules.enterprise_structure.permissions import WORKSPACE_OPERATION_PERMISSIONS

CORE_ACTIONS = {
    "read",
    "workfront.edit",
    "workfront.activate",
    "shift.edit",
    "shift.submit",
    "shift.approve",
    "shift.close",
    "daily.prepare",
    "daily.submit",
    "daily.review",
    "daily.approve",
    "daily.close",
    "crew.edit",
    "equipment.edit",
    "labor.record",
    "equipment.record",
    "condition.record",
    "admin.configure",
    "admin.publish",
}
EXECUTION_ACTIONS = {
    "production.record",
    "production.verify",
    "event.record",
    "event.classify",
    "instruction.record",
    "instruction.issue",
    "rework.record",
    "rework.approve",
    "constraint.record",
    "constraint.verify",
    "material.record",
    "mapping.edit",
}
ACTIONS = tuple(sorted(CORE_ACTIONS | EXECUTION_ACTIONS))
RECORDING = {
    "read",
    "workfront.edit",
    "shift.edit",
    "shift.submit",
    "daily.prepare",
    "daily.submit",
    "crew.edit",
    "equipment.edit",
    "labor.record",
    "equipment.record",
    "condition.record",
    "production.record",
    "event.record",
    "instruction.record",
    "rework.record",
    "constraint.record",
    "material.record",
    "mapping.edit",
}
ROLE_ACTIONS = {
    "organization_admin": set(ACTIONS),
    "operational_administrator": set(ACTIONS),
    "project_manager": {"read"},
    "project_controls_manager": {"read"},
    "executive_viewer": {"read"},
    "field_reporter": RECORDING,
    "field_supervisor": {
        "read",
        "workfront.activate",
        "daily.review",
        "production.verify",
        "event.classify",
        "constraint.verify",
    },
    "field_approver": {"read", "shift.approve", "shift.close", "daily.approve", "daily.close", "rework.approve"},
    "field_instruction_issuer": {"read", "instruction.issue"},
    "field_configurator": {"read", "admin.configure"},
    "field_publisher": {"read", "admin.configure", "admin.publish"},
}


def require_field_schema(db):
    if not inspect(db.connection()).has_table("field_history"):
        raise HTTPException(409, detail={"code": "FIELD_OPERATIONS_MIGRATION_REQUIRED"})


def ensure_field_permissions(db, tenant_id, actor_id):
    require_field_schema(db)
    if db.scalar(select(Tenant.id).where(Tenant.id == tenant_id).with_for_update()) is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND"})
    keys = {f"field_operations.{action}" for action in ACTIONS}
    prerequisites = {"enterprise_structure.read", "operational_context.read", *WORKSPACE_OPERATION_PERMISSIONS}
    permissions = {row.key: row for row in db.scalars(select(PermissionCatalog))}
    for key in sorted(keys | prerequisites):
        if key not in permissions:
            resource, action = key.rsplit(".", 1)
            record = PermissionCatalog(
                key=key,
                resource=resource,
                action=action,
                description=f"Governed Field Operations duty {key}",
                risk_level="high" if action in {"approve", "publish", "verify", "issue"} else "standard",
                status="active",
            )
            db.add(record)
            db.flush()
            permissions[key] = record
    roles = {row.code: row for row in db.scalars(select(SecurityRole).where(SecurityRole.tenant_id == tenant_id))}
    for code, actions in ROLE_ACTIONS.items():
        role = roles.get(code)
        if role is None:
            if not code.startswith("field_"):
                continue
            role = SecurityRole(
                tenant_id=tenant_id,
                code=code,
                name=code.replace("_", " ").title(),
                description="Governed Field Operations duty",
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
        for key in sorted(prerequisites | {f"field_operations.{action}" for action in actions}):
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


ensure_field_operations_permissions = ensure_field_permissions
