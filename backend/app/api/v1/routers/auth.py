"""Authentication endpoints: local login, current user, available providers."""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.api.v1._helpers import require_active_user
from app.core.config import get_settings
from app.core.oidc import OIDCValidationError, get_oidc_validator
from app.core.security import create_access_token, verify_password
from app.database.session import get_db
from app.domain.models import AuthCredential, ProjectMembership, Tenant, UserAccount
from app.domain.schemas import AuthSessionOut, LoginRequest, UserOut


class OIDCTokenExchange(BaseModel):
    id_token: str
    tenant_slug: str | None = None
    tenant_id: int | None = None


router = APIRouter()


@router.post("/auth/login", response_model=AuthSessionOut)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> AuthSessionOut:
    settings = get_settings()
    tenant = _resolve_tenant(db, payload.tenant_id, payload.tenant_slug)
    if not tenant:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    login_name = payload.email.strip().lower()
    login_email = settings.demo_admin_email if login_name == settings.demo_admin_username else login_name
    user = db.scalar(
        select(UserAccount).where(
            UserAccount.tenant_id == tenant.id,
            UserAccount.email == login_email,
            UserAccount.status == "active",
        )
    )
    if not user and login_name == settings.demo_admin_username and not settings.is_production:
        user = _ensure_local_demo_admin(db, tenant, settings.demo_admin_email, settings.demo_user_password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    credential = db.scalar(
        select(AuthCredential).where(
            AuthCredential.tenant_id == tenant.id,
            AuthCredential.user_id == user.id,
            AuthCredential.provider == "local",
            AuthCredential.is_active.is_(True),
        )
    )
    if not credential or not verify_password(payload.password, credential.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    token, expires_in = create_access_token(
        claims={"sub": user.id, "tenant_id": tenant.id, "email": user.email},
        secret_key=settings.auth_secret_key,
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
    return AuthSessionOut(
        access_token=token,
        expires_in=expires_in,
        tenant_id=tenant.id,
        user=UserOut.model_validate(user),
    )


def _ensure_local_demo_admin(
    db: Session,
    tenant: Tenant,
    admin_email: str,
    password: str,
) -> UserAccount:
    from app.database.seed import ensure_local_credential, ensure_membership

    user = db.scalar(
        select(UserAccount).where(
            UserAccount.tenant_id == tenant.id,
            UserAccount.email == admin_email,
        )
    )
    if not user:
        user = UserAccount(
            tenant_id=tenant.id,
            email=admin_email,
            full_name="Pypmis Admin",
            title="Tenant Administrator",
            status="active",
        )
        db.add(user)
        db.flush()
    else:
        user.status = "active"
        user.full_name = user.full_name or "Pypmis Admin"
        user.title = user.title or "Tenant Administrator"

    ensure_local_credential(db, tenant.id, user.id, password)
    configurable_memberships = db.scalars(
        select(ProjectMembership).where(
            ProjectMembership.tenant_id == tenant.id,
            ProjectMembership.can_configure.is_(True),
        )
    ).all()
    seen_projects: set[int] = set()
    for membership in configurable_memberships:
        if membership.project_id in seen_projects:
            continue
        ensure_membership(db, tenant.id, membership.project_id, user.id, "Control Manager")
        seen_projects.add(membership.project_id)
    db.commit()
    db.refresh(user)
    return user


@router.get("/auth/me", response_model=UserOut)
def current_user(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> UserAccount:
    return require_active_user(db, tenant_id, user_id)


@router.post("/auth/oidc/token", response_model=AuthSessionOut)
def oidc_token_exchange(payload: OIDCTokenExchange, db: Session = Depends(get_db)) -> AuthSessionOut:
    """Exchange a provider-issued OIDC id_token for a local session token."""

    settings = get_settings()
    if not settings.oidc_enabled:
        raise HTTPException(status_code=404, detail="OIDC is not enabled on this deployment")
    if not settings.oidc_issuer_url or not settings.oidc_client_id:
        raise HTTPException(status_code=500, detail="OIDC issuer/client not configured")

    validator = get_oidc_validator(settings.oidc_issuer_url, settings.oidc_client_id)
    try:
        claims = validator.decode_and_validate(payload.id_token)
    except OIDCValidationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    email = (claims.get("email") or claims.get("preferred_username") or claims.get("sub") or "").strip().lower()
    if not email:
        raise HTTPException(status_code=401, detail="OIDC token is missing an email claim")

    tenant = _resolve_tenant(db, payload.tenant_id, payload.tenant_slug)
    if not tenant:
        raise HTTPException(status_code=401, detail="Tenant not recognised")

    user = db.scalar(
        select(UserAccount).where(
            UserAccount.tenant_id == tenant.id,
            UserAccount.email == email,
            UserAccount.status == "active",
        )
    )
    if not user:
        raise HTTPException(status_code=403, detail="OIDC user is not provisioned in this tenant")

    token, expires_in = create_access_token(
        claims={"sub": user.id, "tenant_id": tenant.id, "email": user.email},
        secret_key=settings.auth_secret_key,
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
    return AuthSessionOut(
        access_token=token,
        expires_in=expires_in,
        tenant_id=tenant.id,
        user=UserOut.model_validate(user),
    )


@router.get("/auth/providers")
def auth_providers() -> dict[str, object]:
    settings = get_settings()
    return {
        "local": {"enabled": True},
        "oidc": {
            "enabled": settings.oidc_enabled,
            "issuer_url": settings.oidc_issuer_url if settings.oidc_enabled else "",
            "client_id": settings.oidc_client_id if settings.oidc_enabled else "",
            "authorization_url": settings.oidc_authorization_url if settings.oidc_enabled else "",
        },
    }


def _resolve_tenant(db: Session, tenant_id: int | None, tenant_slug: str | None) -> Tenant | None:
    if tenant_id is not None:
        return db.scalar(select(Tenant).where(Tenant.id == tenant_id))
    if tenant_slug:
        return db.scalar(select(Tenant).where(Tenant.slug == tenant_slug.strip().lower()))
    tenants = list(db.scalars(select(Tenant).order_by(Tenant.id).limit(2)).all())
    return tenants[0] if len(tenants) == 1 else None
