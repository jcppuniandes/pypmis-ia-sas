"""Explicit Quality duties; catalog provisioning never assigns an actor."""

from fastapi import HTTPException
from sqlalchemy import inspect, select

from app.domain.models import PermissionCatalog, SecurityRole, SecurityRolePermission, Tenant
from app.modules.enterprise_structure.permissions import WORKSPACE_OPERATION_PERMISSIONS

ACTIONS = [
    "read",
    "plan.edit",
    "plan.submit",
    "plan.approve",
    "itp.edit",
    "itp.submit",
    "itp.approve",
    "inspection.request",
    "inspection.schedule",
    "inspection.perform",
    "inspection.close",
    "test.request",
    "test.schedule",
    "test.perform",
    "test.close",
    "control.release",
    "admin.configure",
    "admin.publish",
    "ncr.record",
    "ncr.issue",
    "ncr.review",
    "ncr.disposition",
    "ncr.correct",
    "ncr.verify",
    "ncr.close",
    "action.record",
    "action.complete",
    "action.verify",
    "punch.record",
    "punch.verify",
    "acceptance.approve",
]
ROLE_ACTIONS = {
    "organization_admin": [
        "read",
        "plan.edit",
        "plan.submit",
        "plan.approve",
        "itp.edit",
        "itp.submit",
        "itp.approve",
        "inspection.request",
        "inspection.schedule",
        "inspection.perform",
        "inspection.close",
        "test.request",
        "test.schedule",
        "test.perform",
        "test.close",
        "control.release",
        "admin.configure",
        "admin.publish",
        "ncr.record",
        "ncr.issue",
        "ncr.review",
        "ncr.disposition",
        "ncr.correct",
        "ncr.verify",
        "ncr.close",
        "action.record",
        "action.complete",
        "action.verify",
        "punch.record",
        "punch.verify",
        "acceptance.approve",
    ],
    "operational_administrator": [
        "read",
        "plan.edit",
        "plan.submit",
        "plan.approve",
        "itp.edit",
        "itp.submit",
        "itp.approve",
        "inspection.request",
        "inspection.schedule",
        "inspection.perform",
        "inspection.close",
        "test.request",
        "test.schedule",
        "test.perform",
        "test.close",
        "control.release",
        "admin.configure",
        "admin.publish",
        "ncr.record",
        "ncr.issue",
        "ncr.review",
        "ncr.disposition",
        "ncr.correct",
        "ncr.verify",
        "ncr.close",
        "action.record",
        "action.complete",
        "action.verify",
        "punch.record",
        "punch.verify",
        "acceptance.approve",
    ],
    "project_manager": ["read"],
    "project_controls_manager": ["read"],
    "executive_viewer": ["read"],
    "quality_reporter": [
        "read",
        "plan.edit",
        "plan.submit",
        "itp.edit",
        "itp.submit",
        "inspection.request",
        "test.request",
        "ncr.record",
        "ncr.issue",
        "punch.record",
    ],
    "quality_inspector": [
        "read",
        "inspection.schedule",
        "inspection.perform",
        "test.schedule",
        "test.perform",
        "ncr.record",
    ],
    "quality_reviewer": ["read", "inspection.close", "test.close", "ncr.review", "action.verify", "punch.verify"],
    "quality_approver": [
        "read",
        "plan.approve",
        "itp.approve",
        "control.release",
        "ncr.disposition",
        "ncr.verify",
        "ncr.close",
        "acceptance.approve",
    ],
    "quality_manager": [
        "read",
        "plan.edit",
        "plan.submit",
        "plan.approve",
        "itp.edit",
        "itp.submit",
        "itp.approve",
        "inspection.request",
        "inspection.schedule",
        "inspection.perform",
        "inspection.close",
        "test.request",
        "test.schedule",
        "test.perform",
        "test.close",
        "control.release",
        "ncr.record",
        "ncr.issue",
        "ncr.review",
        "ncr.disposition",
        "ncr.correct",
        "ncr.verify",
        "ncr.close",
        "action.record",
        "action.complete",
        "action.verify",
        "punch.record",
        "punch.verify",
        "acceptance.approve",
    ],
    "quality_configurator": ["read", "admin.configure"],
    "quality_publisher": ["read", "admin.configure", "admin.publish"],
    "ncr_owner": ["read", "action.record", "action.complete", "ncr.correct", "punch.record"],
}

ACTIONS = [*ACTIONS, "mapping.edit", "readiness.assess"]
for _code in ("organization_admin", "operational_administrator", "quality_manager"):
    ROLE_ACTIONS[_code] = [*ROLE_ACTIONS[_code], "mapping.edit", "readiness.assess"]
ROLE_ACTIONS["quality_reporter"] = [*ROLE_ACTIONS["quality_reporter"], "mapping.edit"]
ROLE_ACTIONS["quality_inspector"] = [*ROLE_ACTIONS["quality_inspector"], "readiness.assess"]


def require_quality_schema(db):
    if not inspect(db.connection()).has_table("quality_history"):
        raise HTTPException(409, detail={"code": "QUALITY_MIGRATION_REQUIRED"})


def ensure_quality_permissions(db, tenant_id, actor_id):
    require_quality_schema(db)
    if db.scalar(select(Tenant.id).where(Tenant.id == tenant_id).with_for_update()) is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND"})
    keys = {f"quality.{action}" for action in ACTIONS}
    prerequisites = {"enterprise_structure.read", "operational_context.read", *WORKSPACE_OPERATION_PERMISSIONS}
    permissions = {row.key: row for row in db.scalars(select(PermissionCatalog))}
    for key in sorted(keys | prerequisites):
        if key not in permissions:
            resource, action = key.rsplit(".", 1)
            record = PermissionCatalog(
                key=key,
                resource=resource,
                action=action,
                description=f"Governed Quality Management duty {key}",
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
            if not code.startswith("quality_") and code != "ncr_owner":
                continue
            role = SecurityRole(
                tenant_id=tenant_id,
                code=code,
                name=code.replace("_", " ").title(),
                description="Governed Quality Management duty",
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
        for key in sorted(prerequisites | {f"quality.{action}" for action in actions}):
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


ensure_quality_management_permissions = ensure_quality_permissions
