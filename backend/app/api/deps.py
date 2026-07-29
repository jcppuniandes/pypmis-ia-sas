from dataclasses import dataclass

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import TokenError, decode_access_token
from app.database.session import get_db
from app.domain.models import UserAccount


@dataclass(frozen=True)
class AuthPrincipal:
    tenant_id: int
    user_id: int
    email: str


def get_current_principal(
    authorization: str = Header(default="", alias="Authorization"),
    db: Session = Depends(get_db),
) -> AuthPrincipal:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Bearer token is required")
    token = authorization.split(" ", 1)[1].strip()
    try:
        claims = decode_access_token(token, get_settings().auth_secret_key)
        tenant_id = int(claims["tenant_id"])
        user_id = int(claims["sub"])
        email = str(claims.get("email", ""))
    except (KeyError, TypeError, ValueError, TokenError) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    user = db.scalar(
        select(UserAccount).where(
            UserAccount.tenant_id == tenant_id,
            UserAccount.id == user_id,
            UserAccount.status == "active",
        )
    )
    if not user:
        raise HTTPException(status_code=401, detail="Authenticated user is not active")
    return AuthPrincipal(tenant_id=tenant_id, user_id=user_id, email=email or user.email)


def get_tenant_id(principal: AuthPrincipal = Depends(get_current_principal)) -> int:
    return principal.tenant_id


def get_user_id(principal: AuthPrincipal = Depends(get_current_principal)) -> int:
    return principal.user_id
