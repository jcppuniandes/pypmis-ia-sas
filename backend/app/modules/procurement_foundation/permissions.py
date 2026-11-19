"""Explicit, additive role registration. Never assigns a user or opens a project."""

from fastapi import HTTPException
from sqlalchemy import inspect, select

from app.domain.models import PermissionCatalog, SecurityRole, SecurityRolePermission, Tenant
from app.modules.enterprise_structure.permissions import WORKSPACE_OPERATION_PERMISSIONS
from app.modules.procurement_foundation.policy import TRANSITIONS

CORE_ACTIONS = {
    "read",
    "admin.configure",
    "admin.publish",
    "package.create",
    "package.edit",
    "package.item.add",
    "requirement.create",
    "requisition.create",
    "rfq.create",
    "rfq.invite",
    "vendor.create",
    "bid.create",
    "evaluation.technical",
    "evaluation.commercial",
    "award.approve",
    "po.create",
    "po.revise",
    "po.revision.approve",
    "mapping.edit",
    *(f"{domain}.{action}" for domain, rules in TRANSITIONS.items() for action in rules),
}
MATERIAL_ACTIONS = {
    "material.catalog",
    "material.requirement",
    "expediting.record",
    "inspection.plan",
    "inspection.decide",
    "shipment.manage",
    "receipt.record",
    "receipt.accept",
    "allocation.manage",
}
ACTIONS = tuple(sorted(CORE_ACTIONS | MATERIAL_ACTIONS))
AUTHOR = {
    "package.create",
    "package.edit",
    "package.plan",
    "package.close",
    "package.cancel",
    "package.item.add",
    "requirement.create",
    "requirement.activate",
    "requirement.cancel",
    "requisition.create",
    "requisition.submit",
    "requisition.cancel",
    "rfq.create",
    "rfq.invite",
    "rfq.cancel",
    "bid.create",
    "po.create",
    "po.cancel",
    "po.revise",
    "mapping.edit",
}
ROLE_ACTIONS = {
    "organization_admin": set(ACTIONS),
    "operational_administrator": set(ACTIONS),
    "procurement_configurator": {
        "read",
        "admin.configure",
        "vendor.create",
        "vendor.suspend",
        "vendor.activate",
        "vendor.retire",
    },
    "procurement_publisher": {"read", "admin.configure", "admin.publish"},
    "procurement_buyer": AUTHOR | {"read"},
    "procurement_requisition_approver": {"read", "requisition.approve", "requisition.reject"},
    "procurement_rfq_issuer": {"read", "rfq.issue", "rfq.close"},
    "procurement_technical_evaluator": {"read", "evaluation.technical"},
    "procurement_commercial_evaluator": {"read", "evaluation.commercial"},
    "procurement_award_approver": {"read", "award.approve"},
    "procurement_po_approver": {"read", "po.approve", "po.issue", "po.revision.approve"},
    "procurement_materials_controller": {
        "read",
        "material.catalog",
        "material.requirement",
        "allocation.manage",
        "expediting.record",
    },
    "procurement_inspector": {"read", "inspection.plan"},
    "procurement_acceptor": {"read", "inspection.decide", "receipt.accept"},
    "procurement_logistician": {"read", "shipment.manage"},
    "procurement_receiver": {"read", "receipt.record"},
    "project_manager": {"read"},
    "project_controls_manager": {"read"},
    "executive_viewer": {"read"},
}


def require_procurement_schema(db):
    if not inspect(db.connection()).has_table("procurement_purchase_orders"):
        raise HTTPException(409, detail={"code": "PROCUREMENT_MIGRATION_REQUIRED"})


def ensure_procurement_permissions(db, tenant_id, actor_id):
    require_procurement_schema(db)
    if db.scalar(select(Tenant).where(Tenant.id == tenant_id).with_for_update()) is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND"})
    keys = {f"procurement.{action}" for action in ACTIONS}
    prerequisites = {"enterprise_structure.read", "operational_context.read", *WORKSPACE_OPERATION_PERMISSIONS}
    permissions = {row.key: row for row in db.scalars(select(PermissionCatalog))}
    for key in sorted(keys | prerequisites):
        if key not in permissions:
            resource, action = key.rsplit(".", 1)
            row = PermissionCatalog(
                key=key,
                resource=resource,
                action=action,
                description=f"Governed Procurement duty {key}",
                risk_level="high" if action in {"approve", "publish", "issue", "accept"} else "standard",
                status="active",
            )
            db.add(row)
            db.flush()
            permissions[key] = row
    roles = {row.code: row for row in db.scalars(select(SecurityRole).where(SecurityRole.tenant_id == tenant_id))}
    for code, actions in ROLE_ACTIONS.items():
        role = roles.get(code)
        if role is None:
            if not code.startswith("procurement_"):
                continue
            role = SecurityRole(
                tenant_id=tenant_id,
                code=code,
                name=code.replace("_", " ").title(),
                description="Governed Procurement duty",
                is_system=True,
                status="active",
            )
            db.add(role)
            db.flush()
        assigned = set(
            db.scalars(
                select(SecurityRolePermission.permission_id).where(
                    SecurityRolePermission.tenant_id == tenant_id, SecurityRolePermission.role_id == role.id
                )
            )
        )
        for key in sorted({*(f"procurement.{action}" for action in actions), *prerequisites}):
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
