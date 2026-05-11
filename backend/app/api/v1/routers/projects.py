"""Core project endpoints (list + create).

The richer ``/projects/{id}/...`` surface (team, control plan, dashboard,
etc.) still lives in the monolithic router.py during the ongoing split.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.api.v1._helpers import (
    require_tenant_configurator as _require_tenant_configurator,
    write_audit_log as _audit,
)
from app.database.session import get_db
from app.domain.models import WBS, Project, ProjectMembership
from app.domain.schemas import ProjectCreate, ProjectOut

router = APIRouter()


@router.get("/projects", response_model=list[ProjectOut])
def list_projects(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[Project]:
    return list(
        db.scalars(
            select(Project)
            .join(ProjectMembership, ProjectMembership.project_id == Project.id)
            .where(
                Project.tenant_id == tenant_id,
                ProjectMembership.tenant_id == tenant_id,
                ProjectMembership.user_id == user_id,
            )
            .order_by(Project.code)
        ).all()
    )


@router.post("/projects", response_model=ProjectOut)
def create_project(
    payload: ProjectCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> Project:
    # late imports — _default_project_control_plan / _role_permissions still
    # live in the monolithic router.py; importing eagerly would create a cycle.
    from app.api.v1.router import _default_project_control_plan, _role_permissions

    current_user = _require_tenant_configurator(db, tenant_id, user_id)
    existing = db.scalar(select(Project).where(Project.tenant_id == tenant_id, Project.code == payload.code))
    if existing:
        raise HTTPException(status_code=409, detail="Project code already exists")
    project = Project(
        tenant_id=tenant_id,
        code=payload.code,
        name=payload.name,
        phase=payload.phase,
        currency=payload.currency,
        start_date=payload.start_date,
        finish_date=payload.finish_date,
    )
    db.add(project)
    db.flush()
    db.add(WBS(tenant_id=tenant_id, project_id=project.id, parent_id=None, code="1.0", name="Project Control Baseline"))
    db.add(_default_project_control_plan(tenant_id, project.id))
    creator_membership = ProjectMembership(
        tenant_id=tenant_id,
        project_id=project.id,
        user_id=user_id,
        role="Control Manager",
        **_role_permissions("Control Manager"),
    )
    db.add(creator_membership)
    _audit(
        db,
        tenant_id,
        project.id,
        "create_project_shell",
        "Project",
        project.id,
        f'{{"code":"{project.code}"}}',
        current_user.full_name,
    )
    db.commit()
    db.refresh(project)
    return project
