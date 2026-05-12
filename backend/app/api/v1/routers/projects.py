"""Project endpoints: list + create + team + control plan.

The richer ``/projects/{id}/...`` surface (dashboard, schedule, cost,
documents, AWP, etc.) still lives in the monolithic router.py during
the ongoing split.
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
    require_current_version as _require_current_version,
)
from app.api.v1._helpers import (
    require_membership as _require_membership,
)
from app.api.v1._helpers import (
    require_permission as _require_permission,
)
from app.api.v1._helpers import (
    require_tenant_configurator as _require_tenant_configurator,
)
from app.api.v1._helpers import (
    touch_collaborative_record as _touch_collaborative_record,
)
from app.api.v1._helpers import (
    write_audit_log as _audit,
)
from app.database.session import get_db
from app.domain.models import WBS, Project, ProjectControlPlan, ProjectMembership
from app.domain.schemas import (
    ProjectControlPlanOut,
    ProjectControlPlanUpdate,
    ProjectCreate,
    ProjectMembershipCreate,
    ProjectMembershipOut,
    ProjectOut,
    ProjectTeamMemberOut,
    UserOut,
)

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


@router.get("/projects/{project_id}/team", response_model=list[ProjectTeamMemberOut])
def list_project_team(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ProjectTeamMemberOut]:
    from app.api.v1.router import _project_team  # late import

    _require_membership(db, tenant_id, project_id, user_id)
    return _project_team(db, tenant_id, project_id)


@router.post("/projects/{project_id}/team", response_model=ProjectTeamMemberOut)
def assign_project_member(
    project_id: int,
    payload: ProjectMembershipCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectTeamMemberOut:
    from app.api.v1.router import _role_permissions  # late import

    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_configure", "Current role cannot configure project users and roles")
    target_user = _require_user(db, tenant_id, payload.user_id)
    permissions = _role_permissions(payload.role)
    target_membership = db.scalar(
        select(ProjectMembership).where(
            ProjectMembership.tenant_id == tenant_id,
            ProjectMembership.project_id == project_id,
            ProjectMembership.user_id == target_user.id,
        )
    )
    if target_membership:
        target_membership.role = payload.role
        for key, value in permissions.items():
            setattr(target_membership, key, value)
    else:
        target_membership = ProjectMembership(
            tenant_id=tenant_id,
            project_id=project_id,
            user_id=target_user.id,
            role=payload.role,
            **permissions,
        )
        db.add(target_membership)
        db.flush()
    current_user = _require_user(db, tenant_id, user_id)
    _audit(
        db,
        tenant_id,
        project_id,
        "assign_project_role",
        "ProjectMembership",
        target_membership.id,
        f'{{"user_id":{target_user.id},"role":"{payload.role}"}}',
        current_user.full_name,
    )
    db.commit()
    db.refresh(target_membership)
    return ProjectTeamMemberOut(
        user=UserOut.model_validate(target_user),
        membership=ProjectMembershipOut.model_validate(target_membership),
    )


@router.get("/projects/{project_id}/control-plan", response_model=ProjectControlPlanOut)
def get_project_control_plan(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectControlPlan:
    from app.api.v1.router import _ensure_project_control_plan  # late import

    _require_membership(db, tenant_id, project_id, user_id)
    plan = _ensure_project_control_plan(db, tenant_id, project_id)
    db.commit()
    db.refresh(plan)
    return plan


@router.put("/projects/{project_id}/control-plan", response_model=ProjectControlPlanOut)
def update_project_control_plan(
    project_id: int,
    payload: ProjectControlPlanUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectControlPlan:
    from app.api.v1.router import _ensure_project_control_plan  # late import

    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_configure", "Current role cannot update the project control plan")
    current_user = _require_user(db, tenant_id, user_id)
    plan = _ensure_project_control_plan(db, tenant_id, project_id)
    _require_current_version(plan, payload.expected_version)
    for field, value in payload.model_dump(exclude_unset=True, exclude={"expected_version"}).items():
        if value is not None:
            setattr(plan, field, value.strip() if isinstance(value, str) else value)
    if plan.status not in {"draft", "in_review", "approved", "active"}:
        raise HTTPException(status_code=400, detail="Unsupported project control plan status")
    _touch_collaborative_record(plan)
    _audit(
        db,
        tenant_id,
        project_id,
        "update_project_control_plan",
        "ProjectControlPlan",
        plan.id,
        json.dumps({"status": plan.status, "reporting_cadence": plan.reporting_cadence}),
        current_user.full_name,
    )
    db.commit()
    db.refresh(plan)
    return plan
