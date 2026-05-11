"""Shared helpers used by the API v1 routers.

Endpoints in the per-domain routers (under ``backend/app/api/v1/routers/``)
need a handful of small lookup and bookkeeping utilities that previously
lived inside the monolithic ``router.py``. Centralising them here avoids
cross-module duplication while the router split progresses.

All functions are private to the API package — they expect to receive an
already-authenticated tenant/user pair and a session that the caller is
responsible for committing.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import (
    AuditLog,
    Project,
    ProjectMembership,
    UserAccount,
)


def require_project(db: Session, tenant_id: int, project_id: int) -> Project:
    project = db.scalar(select(Project).where(Project.id == project_id, Project.tenant_id == tenant_id))
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def require_active_user(db: Session, tenant_id: int, user_id: int) -> UserAccount:
    user = db.scalar(
        select(UserAccount).where(
            UserAccount.id == user_id,
            UserAccount.tenant_id == tenant_id,
            UserAccount.status == "active",
        )
    )
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def require_membership(
    db: Session, tenant_id: int, project_id: int, user_id: int
) -> ProjectMembership:
    require_project(db, tenant_id, project_id)
    require_active_user(db, tenant_id, user_id)
    membership = db.scalar(
        select(ProjectMembership).where(
            ProjectMembership.tenant_id == tenant_id,
            ProjectMembership.project_id == project_id,
            ProjectMembership.user_id == user_id,
        )
    )
    if not membership:
        raise HTTPException(status_code=403, detail="User is not assigned to this project")
    return membership


def require_permission(membership: ProjectMembership, permission: str, message: str) -> None:
    if not bool(getattr(membership, permission)):
        raise HTTPException(status_code=403, detail=message)


def require_tenant_configurator(db: Session, tenant_id: int, user_id: int) -> UserAccount:
    """Require that the user can configure tenant-wide resources.

    Configurator authority is derived from project memberships where
    ``can_configure`` is true. Any active membership with that flag is
    sufficient for tenant-level admin actions (user creation, process
    templates, etc.).
    """

    user = require_active_user(db, tenant_id, user_id)
    membership = db.scalars(
        select(ProjectMembership).where(
            ProjectMembership.tenant_id == tenant_id,
            ProjectMembership.user_id == user_id,
            ProjectMembership.can_configure.is_(True),
        )
    ).first()
    if not membership:
        raise HTTPException(status_code=403, detail="Current user cannot configure tenant projects or users")
    return user


def require_current_version(entity: object, expected_version: int | None) -> None:
    if expected_version is None:
        return
    current_version = int(getattr(entity, "version", 1) or 1)
    if current_version != expected_version:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Record was updated by another user. Refresh before retrying.",
                "current_version": current_version,
                "expected_version": expected_version,
            },
        )


def touch_collaborative_record(entity: object) -> None:
    current_version = int(getattr(entity, "version", 1) or 1)
    entity.version = current_version + 1
    if hasattr(entity, "updated_at"):
        entity.updated_at = datetime.utcnow()


def write_audit_log(
    db: Session,
    tenant_id: int,
    project_id: int | None,
    action: str,
    entity_type: str,
    entity_id: int | None,
    payload: str = "{}",
    actor: str = "Project Controls",
) -> None:
    db.add(
        AuditLog(
            tenant_id=tenant_id,
            project_id=project_id,
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
        )
    )
