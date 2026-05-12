"""Tenant-level admin endpoints: users, roles, business-process templates.

Domain helpers that still live in the monolithic ``router.py``
(``_role_profiles``, ``_configured_process_templates``,
``_process_template_out``) are imported lazily inside the endpoint
functions to avoid an import-time cycle with the aggregator router.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.api.v1._helpers import (
    require_active_user as _require_user,
)
from app.api.v1._helpers import (
    require_tenant_configurator as _require_tenant_configurator,
)
from app.api.v1._helpers import (
    write_audit_log as _audit,
)
from app.core.cache import cache_key, get_cached, invalidate, set_cached
from app.core.config import get_settings
from app.core.security import hash_password
from app.database.session import get_db
from app.domain.models import (
    AuthCredential,
    BusinessProcessStepTemplate,
    BusinessProcessTemplate,
    BusinessProcessTransitionTemplate,
    UserAccount,
)
from app.domain.schemas import (
    ProcessStepTemplateOut,
    ProcessTemplateCreate,
    ProcessTemplateOut,
    RoleProfileOut,
    UserCreate,
    UserOut,
)

router = APIRouter()


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), tenant_id: int = Depends(get_tenant_id)) -> list[UserAccount]:
    return list(
        db.scalars(
            select(UserAccount)
            .where(UserAccount.tenant_id == tenant_id, UserAccount.status == "active")
            .order_by(UserAccount.full_name)
        ).all()
    )


@router.post("/users", response_model=UserOut)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> UserAccount:
    current_user = _require_tenant_configurator(db, tenant_id, user_id)
    email = payload.email.strip().lower()
    existing = db.scalar(select(UserAccount).where(UserAccount.tenant_id == tenant_id, UserAccount.email == email))
    if existing:
        raise HTTPException(status_code=409, detail="User email already exists")
    user = UserAccount(
        tenant_id=tenant_id,
        email=email,
        full_name=payload.full_name,
        title=payload.title,
        status="active",
    )
    db.add(user)
    db.flush()
    db.add(
        AuthCredential(
            tenant_id=tenant_id,
            user_id=user.id,
            provider="local",
            password_hash=hash_password(payload.password or get_settings().demo_user_password),
            is_active=True,
        )
    )
    _audit(
        db,
        tenant_id,
        None,
        "create_user",
        "UserAccount",
        user.id,
        f'{{"email":"{user.email}"}}',
        current_user.full_name,
    )
    db.commit()
    db.refresh(user)
    return user


@router.get("/roles", response_model=list[RoleProfileOut])
def list_roles(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[RoleProfileOut]:
    from app.api.v1.router import _role_profiles  # late import — avoid circular at module load

    _require_user(db, tenant_id, user_id)
    return _role_profiles()


@router.get("/process-templates", response_model=list[ProcessTemplateOut])
def list_process_templates(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ProcessTemplateOut]:
    from app.api.v1.router import _configured_process_templates  # late import

    _require_user(db, tenant_id, user_id)
    key = cache_key("proc_tpl", tenant_id)
    cached = get_cached(key)
    if cached is not None:
        return [ProcessTemplateOut(**item) for item in cached]
    result = _configured_process_templates(db, tenant_id)
    set_cached(key, [item.model_dump() for item in result], ttl=600)
    return result


@router.post("/process-templates", response_model=ProcessTemplateOut)
def create_process_template(
    payload: ProcessTemplateCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProcessTemplateOut:
    from app.api.v1.router import _process_template_out  # late import

    current_user = _require_tenant_configurator(db, tenant_id, user_id)
    code = payload.code.strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="Process code is required")
    existing = db.scalar(
        select(BusinessProcessTemplate).where(
            BusinessProcessTemplate.tenant_id == tenant_id, BusinessProcessTemplate.code == code
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Business process template code already exists")

    template = BusinessProcessTemplate(
        tenant_id=tenant_id,
        code=code,
        name=payload.name.strip(),
        category=payload.category.strip() or "Custom",
        description=payload.description.strip(),
        form_schema=json.dumps([field.strip() for field in payload.form_schema if field.strip()]),
        status=payload.status.strip() or "Draft",
        version_no=payload.version_no,
    )
    db.add(template)
    db.flush()

    step_payloads = payload.steps or [
        ProcessStepTemplateOut(
            step_order=1,
            name="Creation",
            detail="Record is created and validated.",
            owner_role="Originator",
            status="Active",
            tone="active",
        ),
        ProcessStepTemplateOut(
            step_order=2,
            name="Review",
            detail="Responsible role reviews business impact.",
            owner_role="Project Controls",
            status="Queued",
            tone="queued",
        ),
        ProcessStepTemplateOut(
            step_order=3,
            name="Approval",
            detail="Governance approval is captured.",
            owner_role="Control Manager",
            status="Queued",
            tone="queued",
        ),
        ProcessStepTemplateOut(
            step_order=4,
            name="Action",
            detail="Approved decision is converted into execution action.",
            owner_role="Execution Lead",
            status="Queued",
            tone="queued",
        ),
    ]
    for index, step in enumerate(step_payloads, start=1):
        db.add(
            BusinessProcessStepTemplate(
                tenant_id=tenant_id,
                template_id=template.id,
                step_order=index,
                name=step.name.strip(),
                detail=step.detail.strip(),
                owner_role=step.owner_role.strip(),
                status=step.status.strip() or "Queued",
                tone=step.tone.strip() or "queued",
            )
        )

    for transition in payload.transitions:
        db.add(
            BusinessProcessTransitionTemplate(
                tenant_id=tenant_id,
                template_id=template.id,
                action=transition.action.strip().lower(),
                label=transition.label.strip() or transition.action.strip().replace("_", " ").title(),
                from_step=transition.from_step.strip(),
                to_step=transition.to_step.strip(),
                process_status=transition.process_status.strip() or "in_review",
                ball_in_court=transition.ball_in_court.strip(),
                from_status=transition.from_status.strip() or "Complete",
                from_tone=transition.from_tone.strip() or "complete",
                to_status=transition.to_status.strip() or "Active",
                to_tone=transition.to_tone.strip() or "active",
                requires_approval=transition.requires_approval,
                permission_key=transition.permission_key.strip(),
            )
        )

    _audit(
        db,
        tenant_id,
        None,
        "create_process_template",
        "BusinessProcessTemplate",
        template.id,
        f'{{"code":"{template.code}"}}',
        current_user.full_name,
    )
    db.commit()
    invalidate(cache_key("proc_tpl", tenant_id))
    return _process_template_out(db, template)
