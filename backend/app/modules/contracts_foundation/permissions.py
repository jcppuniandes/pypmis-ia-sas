"""Explicit role registration for O2C. No assignments or startup side effects."""

from fastapi import HTTPException
from sqlalchemy import inspect, select

from app.domain.models import PermissionCatalog, SecurityRole, SecurityRolePermission, Tenant
from app.modules.enterprise_structure.permissions import WORKSPACE_OPERATION_PERMISSIONS

CORE_ACTIONS = {
    "package.prepare",
    "contract.prepare",
    "contract.approve",
    "contract.execute",
    "contract.effect",
    "commitment.prepare",
    "commitment.approve",
    "admin.configure",
    "admin.publish",
}
COMMERCIAL_ACTIONS = {
    "sov.edit",
    "sov.publish",
    "change.prepare",
    "change.review",
    "change.approve",
    "application.prepare",
    "application.review",
    "certificate.prepare",
    "certificate.approve",
    "notice.record",
    "claim.prepare",
    "claim.decide",
    "mapping.edit",
    "invoice.reference",
}
ACTIONS = tuple(sorted({"read"} | CORE_ACTIONS | COMMERCIAL_ACTIONS))
ROLE_ACTIONS = {
    "organization_admin": set(ACTIONS),
    "operational_administrator": set(ACTIONS),
    "project_manager": {"read"},
    "project_controls_manager": {"read"},
    "executive_viewer": {"read"},
    "contracts_preparer": {
        "read",
        "package.prepare",
        "contract.prepare",
        "commitment.prepare",
        "sov.edit",
        "change.prepare",
        "application.prepare",
        "certificate.prepare",
        "notice.record",
        "claim.prepare",
        "mapping.edit",
    },
    "contracts_approver": {
        "read",
        "contract.approve",
        "commitment.approve",
        "sov.publish",
        "change.review",
        "change.approve",
        "application.review",
        "certificate.approve",
        "claim.decide",
    },
    "contracts_executor": {"read", "contract.execute", "contract.effect", "invoice.reference"},
    "contracts_configurator": {"read", "admin.configure"},
    "contracts_publisher": {"read", "admin.configure", "admin.publish"},
}


def require_contracts_schema(db):
    if not inspect(db.connection()).has_table("contract_history"):
        raise HTTPException(409, detail={"code": "CONTRACTS_MIGRATION_REQUIRED"})


def ensure_contracts_permissions(db, tenant_id, actor_id):
    require_contracts_schema(db)
    if db.scalar(select(Tenant.id).where(Tenant.id == tenant_id).with_for_update()) is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND"})
    keys = {f"contracts.{action}" for action in ACTIONS}
    prerequisites = {"enterprise_structure.read", "operational_context.read", *WORKSPACE_OPERATION_PERMISSIONS}
    permissions = {row.key: row for row in db.scalars(select(PermissionCatalog))}
    for key in sorted(keys | prerequisites):
        if key not in permissions:
            resource, action = key.rsplit(".", 1)
            row = PermissionCatalog(
                key=key,
                resource=resource,
                action=action,
                description=f"Governed Contracts duty {key}",
                risk_level="high" if action in {"approve", "publish", "execute", "decide"} else "standard",
                status="active",
            )
            db.add(row)
            db.flush()
            permissions[key] = row
    roles = {row.code: row for row in db.scalars(select(SecurityRole).where(SecurityRole.tenant_id == tenant_id))}
    for code, actions in ROLE_ACTIONS.items():
        role = roles.get(code)
        if role is None:
            if not code.startswith("contracts_"):
                continue
            role = SecurityRole(
                tenant_id=tenant_id,
                code=code,
                name=code.replace("_", " ").title(),
                description="Governed Contracts duty",
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
        for key in sorted(prerequisites | {f"contracts.{action}" for action in actions}):
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
