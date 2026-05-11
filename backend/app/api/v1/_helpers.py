"""Shared helpers used by the API v1 routers.

Endpoints in the per-domain routers (under ``backend/app/api/v1/routers/``)
need a handful of small lookup utilities that previously lived inside the
monolithic ``router.py``. Centralising them here avoids cross-module
duplication while the split progresses.
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import UserAccount


def require_active_user(db: Session, tenant_id: int, user_id: int) -> UserAccount:
    """Return the active user for ``(tenant_id, user_id)`` or raise 404."""

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
