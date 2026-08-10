"""Shared tenant-scoped actor authorization for controlled CORE gates."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domain.models import (
    PermissionCatalog,
    SecurityAccessAssignment,
    SecurityGroupMember,
    SecurityRolePermission,
    UserAccount,
)


class ActorAuthorizationError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def require_actor_with_permission(
    db: Session,
    tenant_id: int,
    actor_email: str,
    permission_key: str,
) -> UserAccount:
    normalized_email = actor_email.strip().lower()
    actor = db.scalar(
        select(UserAccount).where(
            UserAccount.tenant_id == tenant_id,
            UserAccount.email == normalized_email,
        )
    )
    if actor is None:
        raise ActorAuthorizationError("ACTOR_NOT_FOUND", actor_email)
    if actor.status != "active":
        raise ActorAuthorizationError("ACTOR_INACTIVE", actor.email)

    group_ids = set(
        db.scalars(
            select(SecurityGroupMember.group_id).where(
                SecurityGroupMember.tenant_id == tenant_id,
                SecurityGroupMember.user_id == actor.id,
            )
        ).all()
    )
    now = utc_now()
    assignments = list(
        db.scalars(
            select(SecurityAccessAssignment).where(
                SecurityAccessAssignment.tenant_id == tenant_id,
                SecurityAccessAssignment.status == "active",
                SecurityAccessAssignment.scope_type == "organization",
            )
        ).all()
    )
    role_ids = {
        assignment.role_id
        for assignment in assignments
        if (assignment.user_id == actor.id or assignment.group_id in group_ids)
        and (assignment.starts_at is None or assignment.starts_at <= now)
        and (assignment.ends_at is None or assignment.ends_at > now)
    }
    permitted = None
    if role_ids:
        permitted = db.scalar(
            select(SecurityRolePermission.id)
            .join(PermissionCatalog, PermissionCatalog.id == SecurityRolePermission.permission_id)
            .where(
                SecurityRolePermission.tenant_id == tenant_id,
                SecurityRolePermission.role_id.in_(role_ids),
                PermissionCatalog.key == permission_key,
                PermissionCatalog.status == "active",
            )
        )
    if permitted is None:
        raise ActorAuthorizationError("ACTOR_NOT_AUTHORIZED", actor.email)
    return actor
