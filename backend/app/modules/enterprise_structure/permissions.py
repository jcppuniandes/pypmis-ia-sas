"""Specific RBAC evaluation for Enterprise Structure endpoints."""

from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1._helpers import require_tenant_configurator
from app.core.time import utc_now
from app.domain.models import (
    PermissionCatalog,
    SecurityAccessAssignment,
    SecurityGroupMember,
    SecurityRole,
    SecurityRolePermission,
    Tenant,
    UserAccount,
)
from app.modules.enterprise_structure.constants import PERMISSION_SEED

WORKSPACE_OPERATION_PERMISSIONS = frozenset(
    {
        "workspace.open",
        "workspace.home.read",
        "workspace.navigator.read",
        "workspace.recent.read",
        "workspace.recent.write",
    }
)

STRUCTURE_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "structure_editor": frozenset(
        {
            "admin.enterprise_structure.revision.create",
            "admin.enterprise_structure.revision.edit",
            "admin.enterprise_structure.revision.validate",
            "admin.enterprise_structure.revision.compare",
        }
    ),
    "structure_approver": frozenset(
        {
            "admin.enterprise_structure.revision.compare",
            "admin.enterprise_structure.revision.approve",
        }
    ),
    "structure_publisher": frozenset(
        {
            "admin.enterprise_structure.revision.compare",
            "admin.enterprise_structure.publish",
            "admin.enterprise_structure.rollback",
        }
    ),
}

STRUCTURE_ROLE_DEFINITIONS = {
    "structure_editor": (
        "Structure Editor",
        "Creates, edits, validates and compares governed workspace revisions.",
    ),
    "structure_approver": (
        "Structure Approver",
        "Compares and approves a validated workspace revision.",
    ),
    "structure_publisher": (
        "Structure Publisher",
        "Publishes approved successors and executes logical rollback.",
    ),
}

PROJECT_CREATION_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "project_requestor": frozenset(
        {
            "project_creation.request.create",
            "project_creation.request.edit",
            "project_creation.request.submit",
            "project_creation.request.read",
            "enterprise_structure.read",
        }
    ),
    "project_reviewer": frozenset(
        {
            "project_creation.request.read",
            "project_creation.review",
            "enterprise_structure.read",
        }
    ),
    "project_approver": frozenset(
        {
            "project_creation.request.read",
            "project_creation.approve",
            "enterprise_structure.read",
        }
    ),
    "project_materialization_service": frozenset(
        {
            "project_creation.request.read",
            "project_creation.materialize",
            "enterprise_structure.read",
        }
    ),
    "project_manager": frozenset({"enterprise_structure.read", "project_workspace.initialization.read"})
    | WORKSPACE_OPERATION_PERMISSIONS,
}

PROJECT_CREATION_ROLE_DEFINITIONS = {
    "project_requestor": ("Project Requestor", "Creates and submits governed Project Workspace requests."),
    "project_reviewer": ("Project Reviewer", "Reviews, returns and rejects Project Workspace requests."),
    "project_approver": ("Project Approver", "Approves Project Workspace requests under Four-Eyes."),
    "project_materialization_service": (
        "Project Materialization Service",
        "Highly restricted role that materializes approved Project Workspaces.",
    ),
    "project_manager": ("Project Manager", "Minimum Workspace-scoped access for the assigned Project Manager."),
}

PROJECT_WORKSPACE_LIFECYCLE_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "project_workspace_initializer": frozenset(
        {
            "project_workspace.initialization.read",
            "project_workspace.initialization.execute",
            "enterprise_structure.read",
        }
    ),
    "project_workspace_activator": frozenset(
        {
            "project_workspace.initialization.read",
            "project_workspace.activation.execute",
            "enterprise_structure.read",
        }
    ),
}

PROJECT_WORKSPACE_LIFECYCLE_ROLE_DEFINITIONS = {
    "project_workspace_initializer": (
        "Project Workspace Initializer",
        "Previews, initializes and validates materialized Project Workspaces.",
    ),
    "project_workspace_activator": (
        "Project Workspace Activator",
        "Independently activates Project Workspaces that passed initialization.",
    ),
}

PHYSICAL_WORKSPACE_CREATION_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "physical_workspace_requestor": frozenset(
        {
            "physical_workspace_creation.request.create",
            "physical_workspace_creation.request.edit",
            "physical_workspace_creation.request.submit",
            "physical_workspace_creation.request.read",
            "enterprise_structure.read",
        }
    ),
    "physical_workspace_reviewer": frozenset(
        {
            "physical_workspace_creation.request.read",
            "physical_workspace_creation.review",
            "enterprise_structure.read",
        }
    ),
    "physical_workspace_approver": frozenset(
        {
            "physical_workspace_creation.request.read",
            "physical_workspace_creation.approve",
            "enterprise_structure.read",
        }
    ),
    "physical_workspace_materialization_service": frozenset(
        {
            "physical_workspace_creation.request.read",
            "physical_workspace_creation.materialize",
            "enterprise_structure.read",
        }
    ),
    "physical_workspace_responsible": frozenset({"enterprise_structure.read", "physical_workspace.initialization.read"})
    | WORKSPACE_OPERATION_PERMISSIONS,
}

PHYSICAL_WORKSPACE_CREATION_ROLE_DEFINITIONS = {
    "physical_workspace_requestor": (
        "Physical Workspace Requestor",
        "Creates and submits governed Property, Facility and Warehouse requests.",
    ),
    "physical_workspace_reviewer": (
        "Physical Workspace Reviewer",
        "Reviews, returns and rejects governed physical Workspace requests.",
    ),
    "physical_workspace_approver": (
        "Physical Workspace Approver",
        "Approves governed physical Workspace requests under Four-Eyes.",
    ),
    "physical_workspace_materialization_service": (
        "Physical Workspace Materialization Service",
        "Restricted service role that materializes approved physical Workspaces.",
    ),
    "physical_workspace_responsible": (
        "Physical Workspace Responsible",
        "Minimum Workspace-scoped access for the assigned physical Workspace responsible.",
    ),
}

PHYSICAL_WORKSPACE_LIFECYCLE_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "physical_workspace_initializer": frozenset(
        {
            "physical_workspace.initialization.read",
            "physical_workspace.initialization.execute",
            "enterprise_structure.read",
        }
    ),
    "physical_workspace_activator": frozenset(
        {
            "physical_workspace.initialization.read",
            "physical_workspace.activation.execute",
            "enterprise_structure.read",
        }
    ),
}

PHYSICAL_WORKSPACE_LIFECYCLE_ROLE_DEFINITIONS = {
    "physical_workspace_initializer": (
        "Physical Workspace Initializer",
        "Previews, initializes, retries and validates Property, Facility and Warehouse Workspaces.",
    ),
    "physical_workspace_activator": (
        "Physical Workspace Activator",
        "Independently activates physical Workspaces that passed initialization.",
    ),
}

REVISION_DUTY_ROLES: dict[str, frozenset[str]] = {
    "admin.enterprise_structure.revision.create": frozenset({"structure_editor"}),
    "admin.enterprise_structure.revision.edit": frozenset({"structure_editor"}),
    "admin.enterprise_structure.revision.validate": frozenset({"structure_editor"}),
    "admin.enterprise_structure.revision.compare": frozenset(STRUCTURE_ROLE_PERMISSIONS),
    "admin.enterprise_structure.revision.approve": frozenset({"structure_approver"}),
    "admin.enterprise_structure.publish": frozenset({"structure_publisher"}),
    "admin.enterprise_structure.rollback": frozenset({"structure_publisher"}),
}


@dataclass(frozen=True)
class EnterprisePermissionContext:
    user: UserAccount
    organization_wide: bool
    scope_unit_ids: frozenset[int]
    workspace_ids: frozenset[int]
    role_codes: frozenset[str]


def require_enterprise_permission(
    db: Session,
    tenant_id: int,
    user_id: int,
    permission_key: str,
    *,
    allowed_role_codes: frozenset[str] | None = None,
) -> EnterprisePermissionContext:
    ensure_enterprise_permissions(db, tenant_id, user_id)
    db.commit()
    user = db.scalar(
        select(UserAccount).where(
            UserAccount.id == user_id,
            UserAccount.tenant_id == tenant_id,
            UserAccount.status == "active",
        )
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    group_ids = list(
        db.scalars(
            select(SecurityGroupMember.group_id).where(
                SecurityGroupMember.tenant_id == tenant_id,
                SecurityGroupMember.user_id == user_id,
            )
        ).all()
    )
    now = utc_now()
    assignments = list(
        db.scalars(
            select(SecurityAccessAssignment).where(
                SecurityAccessAssignment.tenant_id == tenant_id,
                SecurityAccessAssignment.status == "active",
            )
        ).all()
    )
    assignments = [
        item
        for item in assignments
        if (item.user_id == user_id or (item.group_id is not None and item.group_id in group_ids))
        and (item.starts_at is None or item.starts_at <= now)
        and (item.ends_at is None or item.ends_at > now)
    ]
    role_ids = {item.role_id for item in assignments}
    permitted_role_ids: set[int] = set()
    if role_ids:
        permitted_role_ids = set(
            db.scalars(
                select(SecurityRolePermission.role_id)
                .join(PermissionCatalog, PermissionCatalog.id == SecurityRolePermission.permission_id)
                .where(
                    SecurityRolePermission.tenant_id == tenant_id,
                    SecurityRolePermission.role_id.in_(role_ids),
                    PermissionCatalog.key == permission_key,
                    PermissionCatalog.status == "active",
                )
            ).all()
        )
    effective = [item for item in assignments if item.role_id in permitted_role_ids]
    if allowed_role_codes is not None:
        duty_role_ids = set(
            db.scalars(
                select(SecurityRole.id).where(
                    SecurityRole.tenant_id == tenant_id,
                    SecurityRole.code.in_(allowed_role_codes),
                    SecurityRole.status == "active",
                )
            ).all()
        )
        effective = [item for item in effective if item.role_id in duty_role_ids]
    if not effective:
        raise HTTPException(status_code=403, detail=f"Missing required permission: {permission_key}")
    organization_wide = any(item.scope_type == "organization" for item in effective)
    scope_unit_ids = frozenset(item.scope_unit_id for item in effective if item.scope_unit_id is not None)
    workspace_ids = frozenset(item.workspace_id for item in effective if item.workspace_id is not None)
    effective_role_ids = {item.role_id for item in effective}
    role_codes = frozenset(
        db.scalars(
            select(SecurityRole.code).where(
                SecurityRole.tenant_id == tenant_id,
                SecurityRole.id.in_(effective_role_ids),
            )
        ).all()
        if effective_role_ids
        else []
    )
    return EnterprisePermissionContext(
        user=user,
        organization_wide=organization_wide,
        scope_unit_ids=scope_unit_ids,
        workspace_ids=workspace_ids,
        role_codes=role_codes,
    )


def require_organization_scope(context: EnterprisePermissionContext) -> None:
    if not context.organization_wide:
        raise HTTPException(status_code=403, detail="Organization-wide scope is required for this operation")


def ensure_enterprise_permissions(db: Session, tenant_id: int, user_id: int) -> None:
    db.execute(select(Tenant.id).where(Tenant.id == tenant_id).with_for_update()).scalar_one()
    permissions = {item.key: item for item in db.scalars(select(PermissionCatalog)).all()}
    for key, resource, action, description, risk_level in PERMISSION_SEED:
        if key in permissions:
            continue
        record = PermissionCatalog(
            key=key,
            resource=resource,
            action=action,
            description=description,
            risk_level=risk_level,
            status="active",
        )
        db.add(record)
        db.flush()
        permissions[key] = record

    roles = {
        item.code: item for item in db.scalars(select(SecurityRole).where(SecurityRole.tenant_id == tenant_id)).all()
    }
    if "organization_admin" not in roles:
        require_tenant_configurator(db, tenant_id, user_id)
        role = SecurityRole(
            tenant_id=tenant_id,
            code="organization_admin",
            name="Organization Administrator",
            description="Administración integral de la empresa.",
            is_system=True,
            status="active",
        )
        db.add(role)
        db.flush()
        roles[role.code] = role
    if "configuration_admin" not in roles:
        role = SecurityRole(
            tenant_id=tenant_id,
            code="configuration_admin",
            name="Configuration Administrator",
            description="Gobierno de estructuras, catálogos, reglas y procesos reutilizables.",
            is_system=True,
            status="active",
        )
        db.add(role)
        db.flush()
        roles[role.code] = role
    for role_code, (name, description) in STRUCTURE_ROLE_DEFINITIONS.items():
        if role_code in roles:
            continue
        role = SecurityRole(
            tenant_id=tenant_id,
            code=role_code,
            name=name,
            description=description,
            is_system=True,
            status="active",
        )
        db.add(role)
        db.flush()
        roles[role.code] = role
    for role_code, (name, description) in PROJECT_CREATION_ROLE_DEFINITIONS.items():
        if role_code in roles:
            continue
        role = SecurityRole(
            tenant_id=tenant_id,
            code=role_code,
            name=name,
            description=description,
            is_system=True,
            status="active",
        )
        db.add(role)
        db.flush()
        roles[role.code] = role
    for role_code, (name, description) in PROJECT_WORKSPACE_LIFECYCLE_ROLE_DEFINITIONS.items():
        if role_code in roles:
            continue
        role = SecurityRole(
            tenant_id=tenant_id,
            code=role_code,
            name=name,
            description=description,
            is_system=True,
            status="active",
        )
        db.add(role)
        db.flush()
        roles[role.code] = role
    for role_code, (name, description) in PHYSICAL_WORKSPACE_CREATION_ROLE_DEFINITIONS.items():
        if role_code in roles:
            continue
        role = SecurityRole(
            tenant_id=tenant_id,
            code=role_code,
            name=name,
            description=description,
            is_system=True,
            status="active",
        )
        db.add(role)
        db.flush()
        roles[role.code] = role
    for role_code, (name, description) in PHYSICAL_WORKSPACE_LIFECYCLE_ROLE_DEFINITIONS.items():
        if role_code in roles:
            continue
        role = SecurityRole(
            tenant_id=tenant_id,
            code=role_code,
            name=name,
            description=description,
            is_system=True,
            status="active",
        )
        db.add(role)
        db.flush()
        roles[role.code] = role
    grants_by_role = {
        "organization_admin": {item[0] for item in PERMISSION_SEED},
        "configuration_admin": {item[0] for item in PERMISSION_SEED if item[0].startswith("admin.")}
        | {"enterprise_structure.read", "enterprise_structure.read_history", "enterprise_structure.export"},
        "auditor": {"enterprise_structure.read", "enterprise_structure.read_history", "enterprise_structure.export"},
        "viewer": {"enterprise_structure.read"} | WORKSPACE_OPERATION_PERMISSIONS,
        **STRUCTURE_ROLE_PERMISSIONS,
        **PROJECT_CREATION_ROLE_PERMISSIONS,
        **PROJECT_WORKSPACE_LIFECYCLE_ROLE_PERMISSIONS,
        **PHYSICAL_WORKSPACE_CREATION_ROLE_PERMISSIONS,
        **PHYSICAL_WORKSPACE_LIFECYCLE_ROLE_PERMISSIONS,
    }
    for role_code, permission_keys in grants_by_role.items():
        role = roles.get(role_code)
        if role is None:
            continue
        existing = set(
            db.scalars(
                select(SecurityRolePermission.permission_id).where(
                    SecurityRolePermission.tenant_id == tenant_id,
                    SecurityRolePermission.role_id == role.id,
                )
            ).all()
        )
        for permission_key in permission_keys:
            permission = permissions[permission_key]
            if permission.id in existing:
                continue
            db.add(
                SecurityRolePermission(
                    tenant_id=tenant_id,
                    role_id=role.id,
                    permission_id=permission.id,
                    granted_by_user_id=user_id,
                )
            )
    organization_admin = roles["organization_admin"]
    active_admin = db.scalar(
        select(SecurityAccessAssignment.id).where(
            SecurityAccessAssignment.tenant_id == tenant_id,
            SecurityAccessAssignment.role_id == organization_admin.id,
            SecurityAccessAssignment.status == "active",
        )
    )
    if active_admin is None:
        require_tenant_configurator(db, tenant_id, user_id)
        db.add(
            SecurityAccessAssignment(
                tenant_id=tenant_id,
                subject_type="user",
                user_id=user_id,
                role_id=organization_admin.id,
                scope_type="organization",
                status="active",
                granted_by_user_id=user_id,
            )
        )
    structure_editor = roles["structure_editor"]
    active_editor = db.scalar(
        select(SecurityAccessAssignment.id).where(
            SecurityAccessAssignment.tenant_id == tenant_id,
            SecurityAccessAssignment.role_id == structure_editor.id,
            SecurityAccessAssignment.status == "active",
        )
    )
    if active_editor is None:
        bootstrap = db.scalar(
            select(SecurityAccessAssignment).where(
                SecurityAccessAssignment.tenant_id == tenant_id,
                SecurityAccessAssignment.role_id == organization_admin.id,
                SecurityAccessAssignment.status == "active",
            )
        )
        db.add(
            SecurityAccessAssignment(
                tenant_id=tenant_id,
                subject_type=bootstrap.subject_type if bootstrap is not None else "user",
                user_id=bootstrap.user_id if bootstrap is not None else user_id,
                group_id=bootstrap.group_id if bootstrap is not None else None,
                role_id=structure_editor.id,
                scope_type=bootstrap.scope_type if bootstrap is not None else "organization",
                scope_unit_id=bootstrap.scope_unit_id if bootstrap is not None else None,
                starts_at=bootstrap.starts_at if bootstrap is not None else None,
                ends_at=bootstrap.ends_at if bootstrap is not None else None,
                status="active",
                granted_by_user_id=user_id,
            )
        )
