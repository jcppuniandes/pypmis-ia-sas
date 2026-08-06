"""Level 1 organization and security administration.

This module extends the existing tenant/user foundation without replacing the
project authorization model. New records are tenant scoped and every mutation
requires the current tenant configurator during the migration period.
"""

from __future__ import annotations

from collections.abc import Iterable

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.api.v1._helpers import (
    require_current_version,
    require_tenant_configurator,
    touch_collaborative_record,
)
from app.core.config import get_settings
from app.core.time import utc_now
from app.database.session import get_db
from app.domain.models import (
    OrganizationUnit,
    PermissionCatalog,
    SecurityAccessAssignment,
    SecurityEvent,
    SecurityGroup,
    SecurityGroupMember,
    SecurityRole,
    SecurityRolePermission,
    Tenant,
    UserAccount,
)
from app.domain.schemas import (
    AuthenticationPostureOut,
    EffectiveAccessOut,
    OrganizationSecurityOrganizationOut,
    OrganizationSecurityOrganizationUpdate,
    OrganizationSecurityOverviewOut,
    OrganizationUnitCreate,
    OrganizationUnitOut,
    OrganizationUnitUpdate,
    PermissionCatalogOut,
    SecurityAccessAssignmentCreate,
    SecurityAccessAssignmentOut,
    SecurityEventOut,
    SecurityGroupCreate,
    SecurityGroupOut,
    SecurityRoleCreate,
    SecurityRoleOut,
    UserOut,
)

router = APIRouter(prefix="/organization-security")

PERMISSION_SEED = (
    ("organization.read", "organization", "read", "Consultar la información de la empresa.", "standard"),
    ("organization.update", "organization", "update", "Actualizar la configuración de la empresa.", "high"),
    ("organization_unit.manage", "organization_unit", "manage", "Administrar unidades organizacionales.", "high"),
    ("user.invite", "user", "invite", "Invitar usuarios a la empresa.", "high"),
    ("user.read", "user", "read", "Consultar usuarios y membresías.", "standard"),
    ("user.update", "user", "update", "Actualizar datos organizacionales de usuarios.", "high"),
    ("user.suspend", "user", "suspend", "Suspender o reactivar usuarios.", "critical"),
    ("group.manage", "group", "manage", "Administrar grupos y miembros.", "high"),
    ("role.read", "role", "read", "Consultar roles y permisos.", "standard"),
    ("role.manage", "role", "manage", "Crear roles y configurar permisos.", "critical"),
    ("access.read", "access", "read", "Consultar asignaciones y acceso efectivo.", "standard"),
    ("access.manage", "access", "manage", "Asignar o revocar acceso.", "critical"),
    ("security_event.read", "security_event", "read", "Consultar eventos mínimos de seguridad.", "high"),
    ("admin.workspace_type.read", "workspace_type", "read", "Consultar tipos de workspace.", "standard"),
    ("admin.workspace_type.manage", "workspace_type", "manage", "Administrar tipos de workspace.", "high"),
    ("admin.workspace_type.publish", "workspace_type", "publish", "Publicar tipos de workspace.", "critical"),
    ("admin.workspace_structure.read", "workspace_structure", "read", "Consultar estructura empresarial.", "standard"),
    (
        "admin.workspace_structure.manage",
        "workspace_structure",
        "manage",
        "Administrar estructura empresarial.",
        "high",
    ),
    ("admin.workspace_defaults.read", "workspace_defaults", "read", "Consultar valores heredados.", "standard"),
    ("admin.workspace_defaults.manage", "workspace_defaults", "manage", "Administrar valores heredados.", "high"),
    ("admin.module_activation.read", "module_activation", "read", "Consultar activación de módulos.", "standard"),
    ("admin.module_activation.manage", "module_activation", "manage", "Administrar activación de módulos.", "critical"),
    ("admin.catalog.read", "catalog", "read", "Consultar catálogos maestros.", "standard"),
    ("admin.catalog.manage", "catalog", "manage", "Administrar catálogos maestros.", "high"),
    ("admin.catalog.publish", "catalog", "publish", "Publicar catálogos maestros.", "critical"),
    ("admin.numbering.read", "numbering", "read", "Consultar reglas de numeración.", "standard"),
    ("admin.numbering.manage", "numbering", "manage", "Administrar reglas de numeración.", "high"),
    ("admin.numbering.publish", "numbering", "publish", "Publicar reglas de numeración.", "critical"),
    ("admin.process_definition.read", "process_definition", "read", "Consultar definiciones de proceso.", "standard"),
    ("admin.process_definition.manage", "process_definition", "manage", "Administrar procesos declarativos.", "high"),
    (
        "admin.process_definition.publish",
        "process_definition",
        "publish",
        "Publicar definiciones de proceso.",
        "critical",
    ),
)

ROLE_SEED = {
    "organization_admin": {
        "name": "Organization Administrator",
        "description": "Administración integral de la empresa.",
        "permissions": [item[0] for item in PERMISSION_SEED],
    },
    "security_admin": {
        "name": "Security Administrator",
        "description": "Gobierno de roles, permisos y accesos.",
        "permissions": ["role.read", "role.manage", "access.read", "access.manage", "user.read"],
    },
    "user_manager": {
        "name": "User Manager",
        "description": "Altas, bajas y organización de usuarios.",
        "permissions": ["user.invite", "user.read", "user.update", "user.suspend", "group.manage"],
    },
    "auditor": {
        "name": "Auditor",
        "description": "Consulta de organización, usuarios, roles, accesos y eventos.",
        "permissions": [
            "organization.read",
            "user.read",
            "role.read",
            "access.read",
            "security_event.read",
        ],
    },
    "viewer": {
        "name": "Viewer",
        "description": "Lectura básica de la organización.",
        "permissions": ["organization.read"],
    },
    "configuration_admin": {
        "name": "Configuration Administrator",
        "description": "Gobierno de estructuras, catálogos, reglas y procesos reutilizables.",
        "permissions": [item[0] for item in PERMISSION_SEED if item[0].startswith("admin.")],
    },
}


@router.get("/overview", response_model=OrganizationSecurityOverviewOut)
def overview(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> OrganizationSecurityOverviewOut:
    require_tenant_configurator(db, tenant_id, user_id)
    _ensure_security_seed(db, tenant_id, user_id)
    db.commit()
    tenant = _tenant(db, tenant_id)
    users = _users(db, tenant_id)
    return OrganizationSecurityOverviewOut(
        organization=_organization_out(tenant),
        units=[OrganizationUnitOut.model_validate(item) for item in _units(db, tenant_id)],
        users=[UserOut.model_validate(item) for item in users],
        groups=_group_outputs(db, tenant_id),
        permissions=[PermissionCatalogOut.model_validate(item) for item in _permissions(db)],
        roles=_role_outputs(db, tenant_id),
        assignments=_assignment_outputs(db, tenant_id),
        security_events=[SecurityEventOut.model_validate(item) for item in _events(db, tenant_id)],
        authentication=_authentication_posture(users),
    )


@router.get("/organization", response_model=OrganizationSecurityOrganizationOut)
def get_organization(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> OrganizationSecurityOrganizationOut:
    require_tenant_configurator(db, tenant_id, user_id)
    return _organization_out(_tenant(db, tenant_id))


@router.patch("/organization", response_model=OrganizationSecurityOrganizationOut)
def update_organization(
    payload: OrganizationSecurityOrganizationUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> OrganizationSecurityOrganizationOut:
    actor = require_tenant_configurator(db, tenant_id, user_id)
    tenant = _tenant(db, tenant_id)
    if payload.display_name is not None:
        display_name = payload.display_name.strip()
        if not display_name:
            raise HTTPException(status_code=400, detail="Organization display name is required")
        tenant.name = display_name
    if payload.base_currency is not None:
        currency = payload.base_currency.strip().upper()
        if len(currency) != 3:
            raise HTTPException(status_code=400, detail="Base currency must use a three-letter code")
        tenant.base_currency = currency
    _event(db, tenant_id, actor.id, "organization.updated", "organization", tenant.id)
    db.commit()
    db.refresh(tenant)
    return _organization_out(tenant)


@router.get("/units", response_model=list[OrganizationUnitOut])
def list_units(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[OrganizationUnitOut]:
    require_tenant_configurator(db, tenant_id, user_id)
    return [OrganizationUnitOut.model_validate(item) for item in _units(db, tenant_id)]


@router.post("/units", response_model=OrganizationUnitOut, status_code=status.HTTP_201_CREATED)
def create_unit(
    payload: OrganizationUnitCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> OrganizationUnit:
    actor = require_tenant_configurator(db, tenant_id, user_id)
    code = payload.code.strip().upper()
    if not code or not payload.name.strip():
        raise HTTPException(status_code=400, detail="Unit code and name are required")
    if db.scalar(
        select(OrganizationUnit.id).where(OrganizationUnit.tenant_id == tenant_id, OrganizationUnit.code == code)
    ):
        raise HTTPException(status_code=409, detail="Organization unit code already exists")
    if payload.parent_id is not None:
        _unit(db, tenant_id, payload.parent_id)
    if payload.manager_user_id is not None:
        _user(db, tenant_id, payload.manager_user_id)
    unit = OrganizationUnit(
        tenant_id=tenant_id,
        parent_id=payload.parent_id,
        code=code,
        name=payload.name.strip(),
        unit_type=payload.unit_type.strip().lower() or "department",
        manager_user_id=payload.manager_user_id,
        sort_order=payload.sort_order,
        status="active",
    )
    db.add(unit)
    db.flush()
    _event(db, tenant_id, actor.id, "organization_unit.created", "organization_unit", unit.id, {"code": code})
    db.commit()
    db.refresh(unit)
    return unit


@router.patch("/units/{unit_id}", response_model=OrganizationUnitOut)
def update_unit(
    unit_id: int,
    payload: OrganizationUnitUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> OrganizationUnit:
    actor = require_tenant_configurator(db, tenant_id, user_id)
    unit = _unit(db, tenant_id, unit_id)
    require_current_version(unit, payload.expected_version)
    changes = payload.model_dump(exclude_unset=True, exclude={"expected_version"})
    if "parent_id" in changes:
        parent_id = changes["parent_id"]
        if parent_id is not None:
            _unit(db, tenant_id, parent_id)
            _ensure_no_unit_cycle(db, tenant_id, unit.id, parent_id)
        unit.parent_id = parent_id
    if "manager_user_id" in changes and changes["manager_user_id"] is not None:
        _user(db, tenant_id, changes["manager_user_id"])
    for field in ("name", "unit_type", "manager_user_id", "status", "sort_order"):
        if field in changes:
            value = changes[field]
            if isinstance(value, str):
                value = value.strip()
            setattr(unit, field, value)
    if not unit.name:
        raise HTTPException(status_code=400, detail="Unit name is required")
    touch_collaborative_record(unit)
    _event(db, tenant_id, actor.id, "organization_unit.updated", "organization_unit", unit.id)
    db.commit()
    db.refresh(unit)
    return unit


@router.delete("/units/{unit_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_unit(
    unit_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> Response:
    actor = require_tenant_configurator(db, tenant_id, user_id)
    unit = _unit(db, tenant_id, unit_id)
    active_child = db.scalar(
        select(OrganizationUnit.id).where(
            OrganizationUnit.tenant_id == tenant_id,
            OrganizationUnit.parent_id == unit.id,
            OrganizationUnit.status == "active",
        )
    )
    if active_child:
        raise HTTPException(status_code=409, detail="Archive child units before archiving this unit")
    unit.status = "archived"
    touch_collaborative_record(unit)
    _event(db, tenant_id, actor.id, "organization_unit.archived", "organization_unit", unit.id)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/groups", response_model=SecurityGroupOut, status_code=status.HTTP_201_CREATED)
def create_group(
    payload: SecurityGroupCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> SecurityGroupOut:
    actor = require_tenant_configurator(db, tenant_id, user_id)
    code = payload.code.strip().upper()
    if not code or not payload.name.strip():
        raise HTTPException(status_code=400, detail="Group code and name are required")
    if db.scalar(select(SecurityGroup.id).where(SecurityGroup.tenant_id == tenant_id, SecurityGroup.code == code)):
        raise HTTPException(status_code=409, detail="Security group code already exists")
    owner_user_id = payload.owner_user_id or actor.id
    _user(db, tenant_id, owner_user_id)
    group = SecurityGroup(
        tenant_id=tenant_id,
        code=code,
        name=payload.name.strip(),
        description=payload.description.strip(),
        owner_user_id=owner_user_id,
        status="active",
    )
    db.add(group)
    db.flush()
    _event(db, tenant_id, actor.id, "group.created", "security_group", group.id, {"code": code})
    db.commit()
    return _group_output(db, group)


@router.post("/groups/{group_id}/members/{target_user_id}", response_model=SecurityGroupOut)
def add_group_member(
    group_id: int,
    target_user_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> SecurityGroupOut:
    actor = require_tenant_configurator(db, tenant_id, user_id)
    group = _group(db, tenant_id, group_id)
    _user(db, tenant_id, target_user_id)
    existing = db.scalar(
        select(SecurityGroupMember).where(
            SecurityGroupMember.tenant_id == tenant_id,
            SecurityGroupMember.group_id == group_id,
            SecurityGroupMember.user_id == target_user_id,
        )
    )
    if not existing:
        db.add(
            SecurityGroupMember(
                tenant_id=tenant_id,
                group_id=group_id,
                user_id=target_user_id,
                added_by_user_id=actor.id,
            )
        )
        _event(db, tenant_id, actor.id, "group.member_added", "security_group", group_id, {"user_id": target_user_id})
        db.commit()
    return _group_output(db, group)


@router.delete("/groups/{group_id}/members/{target_user_id}", response_model=SecurityGroupOut)
def remove_group_member(
    group_id: int,
    target_user_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> SecurityGroupOut:
    actor = require_tenant_configurator(db, tenant_id, user_id)
    group = _group(db, tenant_id, group_id)
    membership = db.scalar(
        select(SecurityGroupMember).where(
            SecurityGroupMember.tenant_id == tenant_id,
            SecurityGroupMember.group_id == group_id,
            SecurityGroupMember.user_id == target_user_id,
        )
    )
    if membership:
        db.delete(membership)
        _event(db, tenant_id, actor.id, "group.member_removed", "security_group", group_id, {"user_id": target_user_id})
        db.commit()
    return _group_output(db, group)


@router.post("/roles", response_model=SecurityRoleOut, status_code=status.HTTP_201_CREATED)
def create_role(
    payload: SecurityRoleCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> SecurityRoleOut:
    actor = require_tenant_configurator(db, tenant_id, user_id)
    _ensure_security_seed(db, tenant_id, actor.id)
    code = payload.code.strip().lower().replace(" ", "_")
    if not code or not payload.name.strip():
        raise HTTPException(status_code=400, detail="Role code and name are required")
    if db.scalar(select(SecurityRole.id).where(SecurityRole.tenant_id == tenant_id, SecurityRole.code == code)):
        raise HTTPException(status_code=409, detail="Security role code already exists")
    permissions = _permission_records(db, payload.permission_keys)
    role = SecurityRole(
        tenant_id=tenant_id,
        code=code,
        name=payload.name.strip(),
        description=payload.description.strip(),
        is_system=False,
        status="active",
    )
    db.add(role)
    db.flush()
    for permission in permissions:
        db.add(
            SecurityRolePermission(
                tenant_id=tenant_id,
                role_id=role.id,
                permission_id=permission.id,
                granted_by_user_id=actor.id,
            )
        )
    _event(db, tenant_id, actor.id, "role.created", "security_role", role.id, {"code": code})
    db.commit()
    return _role_output(db, role)


@router.post("/assignments", response_model=SecurityAccessAssignmentOut, status_code=status.HTTP_201_CREATED)
def create_assignment(
    payload: SecurityAccessAssignmentCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> SecurityAccessAssignmentOut:
    actor = require_tenant_configurator(db, tenant_id, user_id)
    _ensure_security_seed(db, tenant_id, actor.id)
    subject_type = payload.subject_type.strip().lower()
    if subject_type not in {"user", "group"}:
        raise HTTPException(status_code=400, detail="Subject type must be user or group")
    subject_user_id = payload.subject_id if subject_type == "user" else None
    subject_group_id = payload.subject_id if subject_type == "group" else None
    if subject_user_id is not None:
        _user(db, tenant_id, subject_user_id)
    if subject_group_id is not None:
        _group(db, tenant_id, subject_group_id)
    role = _role(db, tenant_id, payload.role_id)
    scope_type = payload.scope_type.strip().lower()
    if scope_type not in {"organization", "organization_unit"}:
        raise HTTPException(status_code=400, detail="Scope type must be organization or organization_unit")
    scope_unit_id = payload.scope_unit_id if scope_type == "organization_unit" else None
    if scope_type == "organization_unit":
        if scope_unit_id is None:
            raise HTTPException(status_code=400, detail="Organization unit scope requires a unit")
        _unit(db, tenant_id, scope_unit_id)
    if payload.starts_at and payload.ends_at and payload.ends_at <= payload.starts_at:
        raise HTTPException(status_code=400, detail="Assignment end must be after its start")
    assignment = SecurityAccessAssignment(
        tenant_id=tenant_id,
        subject_type=subject_type,
        user_id=subject_user_id,
        group_id=subject_group_id,
        role_id=role.id,
        scope_type=scope_type,
        scope_unit_id=scope_unit_id,
        starts_at=payload.starts_at,
        ends_at=payload.ends_at,
        status="active",
        granted_by_user_id=actor.id,
    )
    db.add(assignment)
    db.flush()
    _event(
        db,
        tenant_id,
        actor.id,
        "access.assigned",
        "security_access_assignment",
        assignment.id,
        {"role": role.code, "subject_type": subject_type, "subject_id": payload.subject_id},
    )
    db.commit()
    return _assignment_output(db, assignment)


@router.delete("/assignments/{assignment_id}", response_model=SecurityAccessAssignmentOut)
def revoke_assignment(
    assignment_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> SecurityAccessAssignmentOut:
    actor = require_tenant_configurator(db, tenant_id, user_id)
    assignment = _assignment(db, tenant_id, assignment_id)
    role = _role(db, tenant_id, assignment.role_id)
    if role.code == "organization_admin" and assignment.user_id is not None:
        other_admins = int(
            db.scalar(
                select(func.count(SecurityAccessAssignment.id)).where(
                    SecurityAccessAssignment.tenant_id == tenant_id,
                    SecurityAccessAssignment.role_id == role.id,
                    SecurityAccessAssignment.subject_type == "user",
                    SecurityAccessAssignment.status == "active",
                    SecurityAccessAssignment.id != assignment.id,
                )
            )
            or 0
        )
        if other_admins < 1:
            raise HTTPException(status_code=409, detail="Cannot revoke the last organization administrator")
    assignment.status = "revoked"
    assignment.updated_at = utc_now()
    _event(db, tenant_id, actor.id, "access.revoked", "security_access_assignment", assignment.id)
    db.commit()
    return _assignment_output(db, assignment)


@router.get("/effective/{target_user_id}", response_model=EffectiveAccessOut)
def effective_access(
    target_user_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> EffectiveAccessOut:
    require_tenant_configurator(db, tenant_id, user_id)
    _ensure_security_seed(db, tenant_id, user_id)
    db.commit()
    target = _user(db, tenant_id, target_user_id)
    group_ids = list(
        db.scalars(
            select(SecurityGroupMember.group_id).where(
                SecurityGroupMember.tenant_id == tenant_id,
                SecurityGroupMember.user_id == target.id,
            )
        ).all()
    )
    assignments = list(
        db.scalars(
            select(SecurityAccessAssignment).where(
                SecurityAccessAssignment.tenant_id == tenant_id,
                SecurityAccessAssignment.status == "active",
            )
        ).all()
    )
    now = utc_now()
    effective = [
        item
        for item in assignments
        if (item.user_id == target.id or (item.group_id is not None and item.group_id in group_ids))
        and (item.starts_at is None or item.starts_at <= now)
        and (item.ends_at is None or item.ends_at > now)
    ]
    role_ids = {item.role_id for item in effective}
    permission_keys = []
    if role_ids:
        permission_keys = list(
            db.scalars(
                select(PermissionCatalog.key)
                .join(SecurityRolePermission, SecurityRolePermission.permission_id == PermissionCatalog.id)
                .where(
                    SecurityRolePermission.tenant_id == tenant_id,
                    SecurityRolePermission.role_id.in_(role_ids),
                    PermissionCatalog.status == "active",
                )
                .order_by(PermissionCatalog.key)
            ).all()
        )
    return EffectiveAccessOut(
        user_id=target.id,
        user_name=target.full_name,
        permission_keys=sorted(set(permission_keys)),
        assignments=[_assignment_output(db, item) for item in effective],
    )


def _ensure_security_seed(db: Session, tenant_id: int, user_id: int) -> None:
    permissions_by_key = {item.key: item for item in db.scalars(select(PermissionCatalog)).all()}
    for key, resource, action, description, risk_level in PERMISSION_SEED:
        if key not in permissions_by_key:
            permission = PermissionCatalog(
                key=key,
                resource=resource,
                action=action,
                description=description,
                risk_level=risk_level,
                status="active",
            )
            db.add(permission)
            db.flush()
            permissions_by_key[key] = permission
    roles_by_code = {
        item.code: item for item in db.scalars(select(SecurityRole).where(SecurityRole.tenant_id == tenant_id)).all()
    }
    for code, definition in ROLE_SEED.items():
        role = roles_by_code.get(code)
        if not role:
            role = SecurityRole(
                tenant_id=tenant_id,
                code=code,
                name=definition["name"],
                description=definition["description"],
                is_system=True,
                status="active",
            )
            db.add(role)
            db.flush()
            roles_by_code[code] = role
        existing_permission_ids = set(
            db.scalars(
                select(SecurityRolePermission.permission_id).where(
                    SecurityRolePermission.tenant_id == tenant_id,
                    SecurityRolePermission.role_id == role.id,
                )
            ).all()
        )
        for permission_key in definition["permissions"]:
            permission = permissions_by_key[permission_key]
            if permission.id not in existing_permission_ids:
                db.add(
                    SecurityRolePermission(
                        tenant_id=tenant_id,
                        role_id=role.id,
                        permission_id=permission.id,
                        granted_by_user_id=user_id,
                    )
                )
    organization_admin = roles_by_code["organization_admin"]
    existing_admin = db.scalar(
        select(SecurityAccessAssignment.id).where(
            SecurityAccessAssignment.tenant_id == tenant_id,
            SecurityAccessAssignment.role_id == organization_admin.id,
            SecurityAccessAssignment.status == "active",
        )
    )
    if not existing_admin:
        assignment = SecurityAccessAssignment(
            tenant_id=tenant_id,
            subject_type="user",
            user_id=user_id,
            role_id=organization_admin.id,
            scope_type="organization",
            status="active",
            granted_by_user_id=user_id,
        )
        db.add(assignment)
        db.flush()
        _event(db, tenant_id, user_id, "access.bootstrap", "security_access_assignment", assignment.id)


def _organization_out(tenant: Tenant) -> OrganizationSecurityOrganizationOut:
    return OrganizationSecurityOrganizationOut(
        id=tenant.id,
        code=tenant.slug.upper().replace("-", "_"),
        legal_name=tenant.name,
        display_name=tenant.name,
        base_currency=tenant.base_currency,
    )


def _authentication_posture(users: list[UserAccount]) -> AuthenticationPostureOut:
    settings = get_settings()
    return AuthenticationPostureOut(
        local_authentication=True,
        oidc_available=settings.oidc_enabled,
        access_token_minutes=settings.access_token_expire_minutes,
        refresh_sessions=False,
        password_hash_policy="PBKDF2-SHA256 (migración a Argon2id pendiente)",
        active_user_count=len(users),
    )


def _tenant(db: Session, tenant_id: int) -> Tenant:
    tenant = db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    if not tenant:
        raise HTTPException(status_code=404, detail="Organization not found")
    return tenant


def _user(db: Session, tenant_id: int, user_id: int) -> UserAccount:
    user = db.scalar(select(UserAccount).where(UserAccount.tenant_id == tenant_id, UserAccount.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _unit(db: Session, tenant_id: int, unit_id: int) -> OrganizationUnit:
    unit = db.scalar(
        select(OrganizationUnit).where(OrganizationUnit.tenant_id == tenant_id, OrganizationUnit.id == unit_id)
    )
    if not unit:
        raise HTTPException(status_code=404, detail="Organization unit not found")
    return unit


def _group(db: Session, tenant_id: int, group_id: int) -> SecurityGroup:
    group = db.scalar(select(SecurityGroup).where(SecurityGroup.tenant_id == tenant_id, SecurityGroup.id == group_id))
    if not group:
        raise HTTPException(status_code=404, detail="Security group not found")
    return group


def _role(db: Session, tenant_id: int, role_id: int) -> SecurityRole:
    role = db.scalar(select(SecurityRole).where(SecurityRole.tenant_id == tenant_id, SecurityRole.id == role_id))
    if not role:
        raise HTTPException(status_code=404, detail="Security role not found")
    return role


def _assignment(db: Session, tenant_id: int, assignment_id: int) -> SecurityAccessAssignment:
    assignment = db.scalar(
        select(SecurityAccessAssignment).where(
            SecurityAccessAssignment.tenant_id == tenant_id,
            SecurityAccessAssignment.id == assignment_id,
        )
    )
    if not assignment:
        raise HTTPException(status_code=404, detail="Access assignment not found")
    return assignment


def _users(db: Session, tenant_id: int) -> list[UserAccount]:
    return list(
        db.scalars(
            select(UserAccount)
            .where(UserAccount.tenant_id == tenant_id, UserAccount.status == "active")
            .order_by(UserAccount.full_name)
        ).all()
    )


def _units(db: Session, tenant_id: int) -> list[OrganizationUnit]:
    return list(
        db.scalars(
            select(OrganizationUnit)
            .where(OrganizationUnit.tenant_id == tenant_id)
            .order_by(OrganizationUnit.sort_order, OrganizationUnit.name)
        ).all()
    )


def _permissions(db: Session) -> list[PermissionCatalog]:
    return list(
        db.scalars(select(PermissionCatalog).order_by(PermissionCatalog.resource, PermissionCatalog.action)).all()
    )


def _events(db: Session, tenant_id: int) -> list[SecurityEvent]:
    return list(
        db.scalars(
            select(SecurityEvent)
            .where(SecurityEvent.tenant_id == tenant_id)
            .order_by(SecurityEvent.occurred_at.desc())
            .limit(20)
        ).all()
    )


def _group_outputs(db: Session, tenant_id: int) -> list[SecurityGroupOut]:
    groups = list(
        db.scalars(select(SecurityGroup).where(SecurityGroup.tenant_id == tenant_id).order_by(SecurityGroup.name)).all()
    )
    return [_group_output(db, item) for item in groups]


def _group_output(db: Session, group: SecurityGroup) -> SecurityGroupOut:
    member_ids = list(
        db.scalars(
            select(SecurityGroupMember.user_id)
            .where(SecurityGroupMember.tenant_id == group.tenant_id, SecurityGroupMember.group_id == group.id)
            .order_by(SecurityGroupMember.user_id)
        ).all()
    )
    return SecurityGroupOut(
        id=group.id,
        code=group.code,
        name=group.name,
        description=group.description,
        owner_user_id=group.owner_user_id,
        status=group.status,
        version=group.version,
        member_ids=member_ids,
    )


def _role_outputs(db: Session, tenant_id: int) -> list[SecurityRoleOut]:
    roles = list(
        db.scalars(select(SecurityRole).where(SecurityRole.tenant_id == tenant_id).order_by(SecurityRole.name)).all()
    )
    return [_role_output(db, item) for item in roles]


def _role_output(db: Session, role: SecurityRole) -> SecurityRoleOut:
    keys = list(
        db.scalars(
            select(PermissionCatalog.key)
            .join(SecurityRolePermission, SecurityRolePermission.permission_id == PermissionCatalog.id)
            .where(SecurityRolePermission.tenant_id == role.tenant_id, SecurityRolePermission.role_id == role.id)
            .order_by(PermissionCatalog.key)
        ).all()
    )
    return SecurityRoleOut(
        id=role.id,
        code=role.code,
        name=role.name,
        description=role.description,
        is_system=role.is_system,
        status=role.status,
        version=role.version,
        permission_keys=keys,
    )


def _assignment_outputs(db: Session, tenant_id: int) -> list[SecurityAccessAssignmentOut]:
    assignments = list(
        db.scalars(
            select(SecurityAccessAssignment)
            .where(SecurityAccessAssignment.tenant_id == tenant_id)
            .order_by(SecurityAccessAssignment.created_at.desc())
        ).all()
    )
    return [_assignment_output(db, item) for item in assignments]


def _assignment_output(db: Session, assignment: SecurityAccessAssignment) -> SecurityAccessAssignmentOut:
    role = _role(db, assignment.tenant_id, assignment.role_id)
    if assignment.subject_type == "user" and assignment.user_id is not None:
        subject_id = assignment.user_id
        subject_name = _user(db, assignment.tenant_id, assignment.user_id).full_name
    elif assignment.group_id is not None:
        subject_id = assignment.group_id
        subject_name = _group(db, assignment.tenant_id, assignment.group_id).name
    else:
        subject_id = 0
        subject_name = "Subject unavailable"
    scope_name = "Organization"
    if assignment.scope_unit_id is not None:
        scope_name = _unit(db, assignment.tenant_id, assignment.scope_unit_id).name
    return SecurityAccessAssignmentOut(
        id=assignment.id,
        subject_type=assignment.subject_type,
        subject_id=subject_id,
        subject_name=subject_name,
        role_id=role.id,
        role_code=role.code,
        role_name=role.name,
        scope_type=assignment.scope_type,
        scope_unit_id=assignment.scope_unit_id,
        scope_name=scope_name,
        starts_at=assignment.starts_at,
        ends_at=assignment.ends_at,
        status=assignment.status,
    )


def _permission_records(db: Session, keys: Iterable[str]) -> list[PermissionCatalog]:
    normalized = sorted({item.strip() for item in keys if item.strip()})
    if not normalized:
        return []
    records = list(db.scalars(select(PermissionCatalog).where(PermissionCatalog.key.in_(normalized))).all())
    found = {item.key for item in records}
    missing = [item for item in normalized if item not in found]
    if missing:
        raise HTTPException(status_code=400, detail={"message": "Unknown permission keys", "keys": missing})
    return records


def _ensure_no_unit_cycle(db: Session, tenant_id: int, unit_id: int, candidate_parent_id: int) -> None:
    current_id: int | None = candidate_parent_id
    visited: set[int] = set()
    while current_id is not None:
        if current_id == unit_id:
            raise HTTPException(status_code=409, detail="Organization unit hierarchy cannot contain cycles")
        if current_id in visited:
            raise HTTPException(status_code=409, detail="Existing organization unit hierarchy contains a cycle")
        visited.add(current_id)
        current = _unit(db, tenant_id, current_id)
        current_id = current.parent_id


def _event(
    db: Session,
    tenant_id: int,
    user_id: int,
    event_type: str,
    target_type: str,
    target_id: int | None,
    metadata: dict | None = None,
) -> None:
    db.add(
        SecurityEvent(
            tenant_id=tenant_id,
            user_id=user_id,
            event_type=event_type,
            outcome="success",
            target_type=target_type,
            target_id=target_id,
            metadata_json=metadata or {},
        )
    )
