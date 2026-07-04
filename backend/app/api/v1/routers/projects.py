"""Project endpoints: list + create + team + control plan.

The richer ``/projects/{id}/...`` surface (dashboard, schedule, cost,
documents, AWP, etc.) still lives in the monolithic router.py during
the ongoing split.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.core.time import utc_now
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
    require_project as _require_project,
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
from app.domain.models import (
    WBS,
    ActivitySheet,
    ActivitySheetRow,
    BimModel,
    BimQuantityRule,
    BusinessProcessPolicy,
    ColombiaApuCatalogItem,
    ControlAccount,
    ControlAccountMapping,
    CostBreakdownStructure,
    FundingSource,
    Project,
    ProjectControlPlan,
    ProjectMembership,
    ProjectOperationalSetup,
    QuantityTakeoffLine,
    QuantityTakeoffRun,
    ScheduleActivityMap,
    ScheduleImport,
    WorkPackage,
)
from app.domain.schemas import (
    ActivitySheetOut,
    ActivitySheetRowOut,
    ActivitySheetWbsRowOut,
    BimModelOut,
    BimGeometryMeasurementBatchIn,
    BimGeometryMeasurementBatchOut,
    BimQuantityRuleOut,
    BimQuantityRuleUpdate,
    ColombiaApuCatalogItemOut,
    ColombiaApuCatalogSyncOut,
    ControlledMeasurementApprovalIn,
    GuidedFlowOut,
    ProcessFlowBoardOut,
    ProjectControlPlanOut,
    ProjectControlPlanUpdate,
    ProjectCreate,
    ProjectMembershipCreate,
    ProjectMembershipOut,
    ProjectOperationalSetupOut,
    ProjectOperationalSetupUpdate,
    QuantityControlCodeAssignmentIn,
    QuantityApuApprovalIn,
    QuantityApuSuggestionIn,
    QuantityApuSuggestionOut,
    ProjectOut,
    QuantityRuleRecalculationOut,
    QuantityTakeoffLineOut,
    QuantityTakeoffModelLinkIn,
    QuantityTakeoffRunOut,
    ProjectRoleMatrixOut,
    ProjectTeamMemberOut,
    RoleMatrixEntryOut,
    RoleMatrixPolicyOut,
    ScheduleCurrencyConfirmIn,
    ScheduleImportOut,
    UserOut,
)
from app.services.bim_models import BimModelService
from app.services.bim_geometry_quantities import BimGeometryQuantityService
from app.services.bim_quantity_rule_catalog import (
    ensure_project_quantity_rules,
    normalize_expected_units,
    project_quantity_rule_catalog,
)
from app.services.bim_quantity_rules import (
    effective_quantity_line,
    evaluate_effective_quantity_rule,
    evaluate_quantity_rule,
)
from app.services.colombia_apu_catalog import ColombiaApuCatalogService
from app.services.guided_flow import GuidedFlowService
from app.services.process_flow_board import ProcessFlowBoardService
from app.services.project_deletion import ProjectDeletionService
from app.services.quantity_takeoff import QuantityTakeoffService
from app.services.schedule_ingestion import ScheduleIngestionService

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
        calendar_base=payload.calendar_base,
        owner=payload.owner,
        status=payload.status,
        authorization_date=payload.authorization_date,
        authorization_ref=payload.authorization_ref,
        configuration=payload.configuration,
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
        "create_project",
        "Project",
        project.id,
        f'{{"code":"{project.code}"}}',
        current_user.full_name,
    )
    db.commit()
    db.refresh(project)
    return project


@router.delete("/projects/{project_id}")
def delete_project(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> dict[str, int | str]:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_configure", "Current role cannot delete projects")
    project = db.scalar(select(Project).where(Project.tenant_id == tenant_id, Project.id == project_id))
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    current_user = _require_user(db, tenant_id, user_id)
    _audit(
        db,
        tenant_id,
        None,
        "delete_project",
        "Project",
        project.id,
        json.dumps({"code": project.code, "name": project.name}),
        current_user.full_name,
    )
    try:
        ProjectDeletionService(db).delete(project_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.commit()
    return {"status": "deleted", "project_id": project_id}


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


@router.get("/projects/{project_id}/role-matrix", response_model=ProjectRoleMatrixOut)
def get_project_role_matrix(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectRoleMatrixOut:
    from app.api.v1.router import _project_team, _role_profiles  # late import

    _require_membership(db, tenant_id, project_id, user_id)
    team = _project_team(db, tenant_id, project_id)
    policies = list(
        db.scalars(
            select(BusinessProcessPolicy)
            .where(
                BusinessProcessPolicy.tenant_id == tenant_id,
                BusinessProcessPolicy.project_id == project_id,
                BusinessProcessPolicy.status == "active",
            )
            .order_by(BusinessProcessPolicy.process_code, BusinessProcessPolicy.action)
        ).all()
    )
    entries: list[RoleMatrixEntryOut] = []
    for profile in _role_profiles():
        assigned_users = [member.user for member in team if member.membership.role == profile.role]
        role_policies = [
            RoleMatrixPolicyOut(
                process_code=policy.process_code,
                action=policy.action,
                required_role=policy.required_role,
                permission_key=policy.permission_key,
                status=policy.status,
            )
            for policy in policies
            if policy.required_role == profile.role
        ]
        entries.append(
            RoleMatrixEntryOut(
                role=profile.role,
                description=profile.description,
                permissions={
                    "can_capture_progress": profile.can_capture_progress,
                    "can_capture_cost": profile.can_capture_cost,
                    "can_approve_workflow": profile.can_approve_workflow,
                    "can_manage_contract": profile.can_manage_contract,
                    "can_configure": profile.can_configure,
                },
                assigned_users=assigned_users,
                assigned_user_count=len(assigned_users),
                business_process_actions=role_policies,
            )
        )
    return ProjectRoleMatrixOut(
        project_id=project_id,
        generated_at=utc_now(),
        role_count=len(entries),
        entries=entries,
    )


@router.get("/projects/{project_id}/guided-flow", response_model=GuidedFlowOut)
def get_guided_flow(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> GuidedFlowOut:
    _require_membership(db, tenant_id, project_id, user_id)
    try:
        return GuidedFlowService(db).build(tenant_id, project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/projects/{project_id}/process-flow-board", response_model=ProcessFlowBoardOut)
def get_process_flow_board(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProcessFlowBoardOut:
    _require_membership(db, tenant_id, project_id, user_id)
    try:
        return ProcessFlowBoardService(db).build(tenant_id, project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/projects/{project_id}/schedule-imports/{schedule_import_id}/confirm-currency",
    response_model=ScheduleImportOut,
)
def confirm_schedule_currency(
    project_id: int,
    schedule_import_id: int,
    payload: ScheduleCurrencyConfirmIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ScheduleImport:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    if membership.role not in {"Planner", "Control Manager", "Cost Controller"}:
        raise HTTPException(status_code=403, detail="Current role cannot confirm schedule currency")
    currency = payload.currency.strip().upper()
    if len(currency) != 3 or not currency.isalpha():
        raise HTTPException(status_code=400, detail="Currency must be a three-letter ISO code")
    project = db.scalar(select(Project).where(Project.tenant_id == tenant_id, Project.id == project_id))
    schedule_import = db.scalar(
        select(ScheduleImport).where(
            ScheduleImport.tenant_id == tenant_id,
            ScheduleImport.project_id == project_id,
            ScheduleImport.id == schedule_import_id,
        )
    )
    if not project or not schedule_import:
        raise HTTPException(status_code=404, detail="Schedule import not found")
    current_user = _require_user(db, tenant_id, user_id)
    schedule_import.detected_currency = currency
    schedule_import.currency_confidence = "confirmed"
    schedule_import.currency_source = schedule_import.currency_source or "user_confirmation"
    schedule_import.currency_confirmed = True
    project.currency = currency
    _audit(
        db,
        tenant_id,
        project_id,
        "confirm_schedule_currency",
        "ScheduleImport",
        schedule_import.id,
        json.dumps({"currency": currency}),
        current_user.full_name,
    )
    db.commit()
    db.refresh(schedule_import)
    return schedule_import


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


@router.delete("/projects/{project_id}/team/{target_user_id}")
def remove_project_member(
    project_id: int,
    target_user_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> dict[str, object]:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_configure", "Current role cannot configure project users and roles")
    target_membership = db.scalar(
        select(ProjectMembership).where(
            ProjectMembership.tenant_id == tenant_id,
            ProjectMembership.project_id == project_id,
            ProjectMembership.user_id == target_user_id,
        )
    )
    if not target_membership:
        raise HTTPException(status_code=404, detail="Project membership not found")
    if target_membership.user_id == user_id:
        raise HTTPException(status_code=400, detail="Current user cannot remove their own project access")
    if target_membership.can_configure:
        other_configurators = int(
            db.scalar(
                select(func.count(ProjectMembership.id)).where(
                    ProjectMembership.tenant_id == tenant_id,
                    ProjectMembership.project_id == project_id,
                    ProjectMembership.can_configure.is_(True),
                    ProjectMembership.user_id != target_user_id,
                )
            )
            or 0
        )
        if other_configurators < 1:
            raise HTTPException(status_code=400, detail="Cannot remove the last project configurator")
    current_user = _require_user(db, tenant_id, user_id)
    target_user = _require_user(db, tenant_id, target_user_id)
    membership_id = target_membership.id
    role = target_membership.role
    db.delete(target_membership)
    _audit(
        db,
        tenant_id,
        project_id,
        "remove_project_role",
        "ProjectMembership",
        membership_id,
        json.dumps({"user_id": target_user_id, "role": role}),
        current_user.full_name,
    )
    db.commit()
    return {
        "status": "removed",
        "project_id": project_id,
        "user_id": target_user.id,
        "membership_id": membership_id,
        "role": role,
    }


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


@router.get("/projects/{project_id}/operational-setup", response_model=ProjectOperationalSetupOut)
def get_project_operational_setup(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectOperationalSetup:
    _require_membership(db, tenant_id, project_id, user_id)
    setup = _get_project_operational_setup(db, tenant_id, project_id)
    if not setup:
        raise HTTPException(status_code=404, detail="Project operational setup not found")
    return setup


@router.put("/projects/{project_id}/operational-setup", response_model=ProjectOperationalSetupOut)
def update_project_operational_setup(
    project_id: int,
    payload: ProjectOperationalSetupUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectOperationalSetup:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_configure", "Current role cannot configure the project operational setup")
    current_user = _require_user(db, tenant_id, user_id)
    setup = _get_project_operational_setup(db, tenant_id, project_id)
    is_new = setup is None
    if setup is None:
        setup = ProjectOperationalSetup(tenant_id=tenant_id, project_id=project_id)
        db.add(setup)
        db.flush()
    else:
        _require_current_version(setup, payload.expected_version)

    for field, value in payload.model_dump(exclude={"expected_version"}).items():
        setattr(setup, field, value.strip() if isinstance(value, str) else value)
    if setup.status not in {"draft", "in_review", "ready", "active"}:
        raise HTTPException(status_code=400, detail="Unsupported project operational setup status")
    _apply_operational_setup_readiness(setup)
    if not is_new:
        _touch_collaborative_record(setup)
    _audit(
        db,
        tenant_id,
        project_id,
        "update_project_operational_setup",
        "ProjectOperationalSetup",
        setup.id,
        json.dumps({"status": setup.status, "readiness_status": setup.readiness_status}),
        current_user.full_name,
    )
    db.commit()
    db.refresh(setup)
    return setup


@router.get("/projects/{project_id}/activity-sheets", response_model=list[ActivitySheetOut])
def list_activity_sheets(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ActivitySheet]:
    _require_membership(db, tenant_id, project_id, user_id)
    return list(
        db.scalars(
            select(ActivitySheet)
            .where(ActivitySheet.tenant_id == tenant_id, ActivitySheet.project_id == project_id)
            .order_by(ActivitySheet.created_at.desc(), ActivitySheet.id.desc())
        ).all()
    )


@router.post("/projects/{project_id}/activity-sheets/get-data", response_model=ActivitySheetOut)
async def get_activity_sheet_data(
    project_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ActivitySheet:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    if membership.role not in {"Planner", "Control Manager"}:
        raise HTTPException(status_code=403, detail="Current role cannot load activity data")
    _require_operational_setup_ready(db, tenant_id, project_id)
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Activity source file is empty")

    schedule_import = ScheduleIngestionService(db).ingest(tenant_id, project_id, file.filename or "activity-data.xml", content)
    rows = list(
        db.scalars(
            select(ScheduleActivityMap)
            .where(
                ScheduleActivityMap.tenant_id == tenant_id,
                ScheduleActivityMap.project_id == project_id,
                ScheduleActivityMap.schedule_import_id == schedule_import.id,
            )
            .order_by(ScheduleActivityMap.external_activity_id)
        ).all()
    )
    mappings_by_schedule_row_id = {
        mapping.schedule_activity_map_id: mapping
        for mapping in db.scalars(
            select(ControlAccountMapping).where(
                ControlAccountMapping.tenant_id == tenant_id,
                ControlAccountMapping.project_id == project_id,
                ControlAccountMapping.schedule_import_id == schedule_import.id,
            )
        ).all()
    }
    activity_sheet = ActivitySheet(
        tenant_id=tenant_id,
        project_id=project_id,
        schedule_import_id=schedule_import.id,
        source_file_name=schedule_import.file_name,
        source=_enum_value(schedule_import.source),
        status=_enum_value(schedule_import.status),
        row_count=len(rows),
        data_date=schedule_import.data_date,
        baseline_name=schedule_import.baseline_name,
        validation_summary=schedule_import.validation_summary,
    )
    db.add(activity_sheet)
    db.flush()
    for row in rows:
        mapping = mappings_by_schedule_row_id.get(row.id)
        db.add(
            ActivitySheetRow(
                tenant_id=tenant_id,
                project_id=project_id,
                activity_sheet_id=activity_sheet.id,
                external_activity_id=row.external_activity_id,
                wbs_code=row.wbs_code,
                activity_name=row.activity_name,
                planned_start=row.planned_start,
                planned_finish=row.planned_finish,
                total_float_days=row.total_float_days,
                critical_path=row.critical_path,
                planned_cost=mapping.planned_cost if mapping else 0,
            )
        )
    current_user = _require_user(db, tenant_id, user_id)
    _audit(
        db,
        tenant_id,
        project_id,
        "get_activity_sheet_data",
        "ActivitySheet",
        activity_sheet.id,
        json.dumps({"source_file_name": activity_sheet.source_file_name, "row_count": activity_sheet.row_count}),
        current_user.full_name,
    )
    db.commit()
    db.refresh(activity_sheet)
    return activity_sheet


@router.get(
    "/projects/{project_id}/activity-sheets/{activity_sheet_id}/rows",
    response_model=list[ActivitySheetRowOut],
)
def list_activity_sheet_rows(
    project_id: int,
    activity_sheet_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ActivitySheetRow]:
    _require_membership(db, tenant_id, project_id, user_id)
    activity_sheet = db.scalar(
        select(ActivitySheet).where(
            ActivitySheet.tenant_id == tenant_id,
            ActivitySheet.project_id == project_id,
            ActivitySheet.id == activity_sheet_id,
        )
    )
    if not activity_sheet:
        raise HTTPException(status_code=404, detail="Activity sheet not found")
    return _activity_sheet_enriched_rows(db, tenant_id, project_id, activity_sheet)


@router.get(
    "/projects/{project_id}/activity-sheets/{activity_sheet_id}/wbs-sheet",
    response_model=list[ActivitySheetWbsRowOut],
)
def get_activity_sheet_wbs_sheet(
    project_id: int,
    activity_sheet_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ActivitySheetWbsRowOut]:
    _require_membership(db, tenant_id, project_id, user_id)
    activity_sheet = db.scalar(
        select(ActivitySheet).where(
            ActivitySheet.tenant_id == tenant_id,
            ActivitySheet.project_id == project_id,
            ActivitySheet.id == activity_sheet_id,
        )
    )
    if not activity_sheet:
        raise HTTPException(status_code=404, detail="Activity sheet not found")

    wbs_nodes = list(
        db.scalars(
            select(WBS)
            .where(WBS.tenant_id == tenant_id, WBS.project_id == project_id)
            .order_by(WBS.level, WBS.code)
        ).all()
    )
    wbs_by_code = {wbs.code: wbs for wbs in wbs_nodes}
    children_by_parent: dict[int | None, list[WBS]] = {}
    for wbs in wbs_nodes:
        children_by_parent.setdefault(wbs.parent_id, []).append(wbs)

    def empty_group() -> dict[str, object]:
        return {
            "activity_count": 0,
            "control_account_ids": set(),
            "planned_cost": 0.0,
            "planned_value": 0.0,
            "unmapped_activity_count": 0,
            "needs_review_count": 0,
        }

    def add_group(left: dict[str, object], right: dict[str, object]) -> dict[str, object]:
        control_account_ids = set()
        for value in (left["control_account_ids"], right["control_account_ids"]):
            if isinstance(value, set):
                control_account_ids.update(value)
        return {
            "activity_count": int(left["activity_count"]) + int(right["activity_count"]),
            "control_account_ids": control_account_ids,
            "planned_cost": float(left["planned_cost"]) + float(right["planned_cost"]),
            "planned_value": float(left["planned_value"]) + float(right["planned_value"]),
            "unmapped_activity_count": int(left["unmapped_activity_count"]) + int(right["unmapped_activity_count"]),
            "needs_review_count": int(left["needs_review_count"]) + int(right["needs_review_count"]),
        }

    grouped: dict[str, dict[str, object]] = {}
    for row in _activity_sheet_enriched_rows(db, tenant_id, project_id, activity_sheet):
        wbs_code = row["wbs_code"] or "UNMAPPED"
        group = grouped.setdefault(wbs_code, empty_group())
        group["activity_count"] = int(group["activity_count"]) + 1
        group["planned_cost"] = float(group["planned_cost"]) + float(row["planned_cost"] or 0)
        group["planned_value"] = float(group["planned_value"]) + float(row["planned_value"] or 0)
        control_account_ids = group["control_account_ids"]
        if isinstance(control_account_ids, set) and row["control_account_id"]:
            control_account_ids.add(row["control_account_id"])
        if not row["control_account_id"]:
            group["unmapped_activity_count"] = int(group["unmapped_activity_count"]) + 1
        if row["mapping_status"] != "mapped":
            group["needs_review_count"] = int(group["needs_review_count"]) + 1

    rollups: dict[str, dict[str, object]] = {}
    visiting: set[int] = set()

    def rollup_for(wbs: WBS) -> dict[str, object]:
        if wbs.id in visiting:
            return grouped.get(wbs.code, empty_group())
        visiting.add(wbs.id)
        rollup = grouped.get(wbs.code, empty_group())
        for child in children_by_parent.get(wbs.id, []):
            rollup = add_group(rollup, rollup_for(child))
        visiting.discard(wbs.id)
        if (
            int(rollup["activity_count"])
            or float(rollup["planned_cost"])
            or float(rollup["planned_value"])
            or int(rollup["needs_review_count"])
        ):
            rollups[wbs.code] = rollup
        return rollup

    for root in children_by_parent.get(None, []):
        rollup_for(root)
    for wbs in wbs_nodes:
        if wbs.code not in rollups and wbs.code in grouped:
            rollups[wbs.code] = grouped[wbs.code]
    for wbs_code, group in grouped.items():
        if wbs_code not in wbs_by_code:
            rollups[wbs_code] = group

    def wbs_sort_key(wbs_code: str) -> tuple[int, str]:
        wbs = wbs_by_code.get(wbs_code)
        return (wbs.level if wbs else 999, wbs_code)

    rows: list[ActivitySheetWbsRowOut] = []
    for wbs_code in sorted(rollups, key=wbs_sort_key):
        group = rollups[wbs_code]
        wbs = wbs_by_code.get(wbs_code)
        control_account_ids = group["control_account_ids"]
        rows.append(
            ActivitySheetWbsRowOut(
                wbs_code=wbs_code,
                wbs_name=wbs.name if wbs else wbs_code,
                activity_count=int(group["activity_count"]),
                control_account_count=len(control_account_ids) if isinstance(control_account_ids, set) else 0,
                planned_cost=round(float(group["planned_cost"]), 2),
                planned_value=round(float(group["planned_value"]), 2),
                unmapped_activity_count=int(group["unmapped_activity_count"]),
                needs_review_count=int(group["needs_review_count"]),
            )
        )
    return rows


@router.get("/projects/{project_id}/bim-quantity-rules", response_model=list[BimQuantityRuleOut])
def list_bim_quantity_rules(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[BimQuantityRule]:
    _require_project(db, tenant_id, project_id)
    _require_membership(db, tenant_id, project_id, user_id)
    rules = ensure_project_quantity_rules(db, tenant_id, project_id)
    db.commit()
    return rules


@router.put("/projects/{project_id}/bim-quantity-rules/{rule_id}", response_model=BimQuantityRuleOut)
def update_bim_quantity_rule(
    project_id: int,
    rule_id: int,
    payload: BimQuantityRuleUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> BimQuantityRule:
    _require_project(db, tenant_id, project_id)
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_configure", "Current role cannot configure BIM quantity rules")
    current_user = _require_user(db, tenant_id, user_id)
    ensure_project_quantity_rules(db, tenant_id, project_id)
    rule = db.scalar(
        select(BimQuantityRule).where(
            BimQuantityRule.tenant_id == tenant_id,
            BimQuantityRule.project_id == project_id,
            BimQuantityRule.id == rule_id,
        )
    )
    if not rule:
        raise HTTPException(status_code=404, detail="BIM quantity rule not found")
    _require_current_version(rule, payload.expected_version)

    for field, value in payload.model_dump(exclude_unset=True, exclude={"expected_version"}).items():
        if value is None:
            continue
        if field == "expected_units":
            rule.expected_units = normalize_expected_units(value)
            continue
        setattr(rule, field, value.strip() if isinstance(value, str) else value)
    if rule.status not in {"active", "inactive"}:
        raise HTTPException(status_code=400, detail="Unsupported BIM quantity rule status")
    if not rule.expected_units:
        raise HTTPException(status_code=400, detail="At least one expected unit is required")
    rule.source = "project_custom"
    _touch_collaborative_record(rule)
    _audit(
        db,
        tenant_id,
        project_id,
        "update_bim_quantity_rule",
        "BimQuantityRule",
        rule.id,
        json.dumps(
            {
                "ifc_class": rule.ifc_class,
                "expected_measure": rule.expected_measure,
                "expected_units": rule.expected_units,
            }
        ),
        current_user.full_name,
    )
    db.commit()
    db.refresh(rule)
    return rule


@router.get("/projects/{project_id}/quantity-takeoff-runs", response_model=list[QuantityTakeoffRunOut])
def list_quantity_takeoff_runs(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[QuantityTakeoffRun]:
    _require_project(db, tenant_id, project_id)
    _require_membership(db, tenant_id, project_id, user_id)
    runs = list(
        db.scalars(
            select(QuantityTakeoffRun)
            .where(QuantityTakeoffRun.tenant_id == tenant_id, QuantityTakeoffRun.project_id == project_id)
            .order_by(QuantityTakeoffRun.created_at.desc(), QuantityTakeoffRun.id.desc())
        ).all()
    )
    service = QuantityTakeoffService(db)
    changed = False
    for run in runs:
        changed = service.ensure_source_identity(run) or changed
    if changed:
        db.commit()
    return runs


@router.post("/projects/{project_id}/colombia-apu-catalog/sync", response_model=ColombiaApuCatalogSyncOut)
def sync_colombia_apu_catalog(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> dict:
    _require_project(db, tenant_id, project_id)
    membership = _require_membership(db, tenant_id, project_id, user_id)
    if not (membership.can_capture_cost or membership.can_configure):
        raise HTTPException(status_code=403, detail="Current role cannot sync Colombia APU catalog")
    current_user = _require_user(db, tenant_id, user_id)
    result = ColombiaApuCatalogService(db).sync_public_catalog(tenant_id, project_id)
    _audit(
        db,
        tenant_id,
        project_id,
        "sync_colombia_apu_catalog",
        "ColombiaApuCatalogItem",
        None,
        json.dumps(
            {
                "source_key": result["source_key"],
                "created_count": result["created_count"],
                "updated_count": result["updated_count"],
                "skipped_count": result["skipped_count"],
            }
        ),
        current_user.full_name,
    )
    db.commit()
    return result


@router.get("/projects/{project_id}/colombia-apu-catalog", response_model=list[ColombiaApuCatalogItemOut])
def list_colombia_apu_catalog(
    project_id: int,
    search: str = "",
    source_key: str = "",
    limit: int = 50,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ColombiaApuCatalogItem]:
    _require_project(db, tenant_id, project_id)
    _require_membership(db, tenant_id, project_id, user_id)
    return ColombiaApuCatalogService(db).list_items(
        tenant_id,
        project_id,
        search=search,
        limit=limit,
        source_key=source_key,
    )


@router.post(
    "/projects/{project_id}/quantity-takeoff-runs/{run_id}/apu-suggestions",
    response_model=list[QuantityApuSuggestionOut],
)
def suggest_quantity_apu_items(
    project_id: int,
    run_id: int,
    payload: QuantityApuSuggestionIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[dict]:
    _require_project(db, tenant_id, project_id)
    membership = _require_membership(db, tenant_id, project_id, user_id)
    if not (membership.can_capture_cost or membership.can_configure):
        raise HTTPException(status_code=403, detail="Current role cannot generate BIM APU suggestions")
    run = db.scalar(
        select(QuantityTakeoffRun).where(
            QuantityTakeoffRun.tenant_id == tenant_id,
            QuantityTakeoffRun.project_id == project_id,
            QuantityTakeoffRun.id == run_id,
        )
    )
    if not run:
        raise HTTPException(status_code=404, detail="Quantity takeoff run not found")
    line_ids = sorted({line_id for line_id in payload.line_ids if line_id > 0})
    if not line_ids:
        raise HTTPException(status_code=400, detail="At least one quantity line must be selected")
    lines = list(
        db.scalars(
            select(QuantityTakeoffLine)
            .where(
                QuantityTakeoffLine.tenant_id == tenant_id,
                QuantityTakeoffLine.project_id == project_id,
                QuantityTakeoffLine.run_id == run_id,
                QuantityTakeoffLine.id.in_(line_ids),
            )
            .order_by(QuantityTakeoffLine.id)
        ).all()
    )
    if len(lines) != len(line_ids):
        raise HTTPException(status_code=404, detail="One or more quantity takeoff lines were not found")
    quantity_catalog = project_quantity_rule_catalog(db, tenant_id, project_id)
    blocked_lines = [
        line.id for line in lines if evaluate_effective_quantity_rule(line, quantity_catalog).get("status") != "valid"
    ]
    if blocked_lines:
        raise HTTPException(
            status_code=400,
            detail=f"Lines {blocked_lines} require a valid IFC measurement before APU suggestion",
        )
    suggestions = ColombiaApuCatalogService(db).suggest_for_lines(
        tenant_id,
        project_id,
        lines,
        apply_best=payload.apply_best,
        limit_per_line=payload.limit_per_line,
    )
    current_user = _require_user(db, tenant_id, user_id)
    _audit(
        db,
        tenant_id,
        project_id,
        "suggest_bim_apu_items",
        "QuantityTakeoffRun",
        run_id,
        json.dumps({"line_ids": line_ids, "suggestion_count": len(suggestions), "apply_best": payload.apply_best}),
        current_user.full_name,
    )
    db.commit()
    return [suggestion.as_dict() for suggestion in suggestions]


@router.post(
    "/projects/{project_id}/quantity-takeoff-runs/{run_id}/apu-approvals",
    response_model=list[QuantityTakeoffLineOut],
)
def approve_quantity_apu_items(
    project_id: int,
    run_id: int,
    payload: QuantityApuApprovalIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[QuantityTakeoffLine]:
    _require_project(db, tenant_id, project_id)
    membership = _require_membership(db, tenant_id, project_id, user_id)
    if not (membership.can_capture_cost or membership.can_configure):
        raise HTTPException(status_code=403, detail="Current role cannot approve BIM APU groups")
    run = db.scalar(
        select(QuantityTakeoffRun).where(
            QuantityTakeoffRun.tenant_id == tenant_id,
            QuantityTakeoffRun.project_id == project_id,
            QuantityTakeoffRun.id == run_id,
        )
    )
    if not run:
        raise HTTPException(status_code=404, detail="Quantity takeoff run not found")
    line_ids = sorted({line_id for line_id in payload.line_ids if line_id > 0})
    if not line_ids:
        raise HTTPException(status_code=400, detail="At least one quantity line must be selected")
    lines = list(
        db.scalars(
            select(QuantityTakeoffLine)
            .where(
                QuantityTakeoffLine.tenant_id == tenant_id,
                QuantityTakeoffLine.project_id == project_id,
                QuantityTakeoffLine.run_id == run_id,
                QuantityTakeoffLine.id.in_(line_ids),
            )
            .order_by(QuantityTakeoffLine.id)
        ).all()
    )
    if len(lines) != len(line_ids):
        raise HTTPException(status_code=404, detail="One or more quantity takeoff lines were not found")

    prepared: list[tuple[QuantityTakeoffLine, dict, float, str]] = []
    quantity_catalog = project_quantity_rule_catalog(db, tenant_id, project_id)
    for line in lines:
        quantity_rule = evaluate_effective_quantity_rule(line, quantity_catalog)
        if quantity_rule.get("status") != "valid":
            raise HTTPException(
                status_code=400,
                detail=f"Line {line.id} requires a valid IFC measurement before APU approval",
            )
        effective_line = effective_quantity_line(line)
        effective_unit = str(effective_line.get("unit") or line.unit)
        effective_quantity = float(effective_line.get("quantity") or 0)
        raw_data = dict(line.raw_data or {})
        suggestion_value = raw_data.get("apu_suggestion")
        suggestion = dict(suggestion_value) if isinstance(suggestion_value, dict) else {}
        code = str(suggestion.get("cost_item_code") or "").strip()
        name = str(suggestion.get("cost_item_name") or "").strip()
        budget_unit = str(suggestion.get("budget_unit") or "").strip()
        unit_rate = float(suggestion.get("unit_rate") or 0)
        match_score = float(suggestion.get("match_score") or 0)
        if not code or not name or not budget_unit or unit_rate <= 0:
            raise HTTPException(status_code=400, detail=f"Line {line.id} has no complete APU suggestion")
        if _quantity_unit_key(effective_unit) != _quantity_unit_key(budget_unit):
            raise HTTPException(
                status_code=400,
                detail=f"Line {line.id} quantity unit {effective_unit} is incompatible with APU unit {budget_unit}",
            )
        if match_score < 70:
            raise HTTPException(status_code=400, detail=f"Line {line.id} APU suggestion confidence is below 70%")
        quantity = effective_quantity
        prepared.append((line, suggestion, quantity, budget_unit))

    current_user = _require_user(db, tenant_id, user_id)
    approved_at = utc_now().isoformat()
    for line, suggestion, quantity, budget_unit in prepared:
        raw_data = dict(line.raw_data or {})
        unit_rate = float(suggestion.get("unit_rate") or 0)
        raw_data["budget_item_assignment"] = {
            **suggestion,
            "assigned_at": approved_at,
            "assigned_by": current_user.full_name,
            "assigned_by_user_id": current_user.id,
            "budget_amount": round(quantity * unit_rate, 2),
            "budget_unit": budget_unit,
            "cbs_code": line.cbs_code,
            "fbs_code": line.fbs_code,
            "line_id": line.id,
            "measurement_rule": line.measurement_rule,
            "package_code": line.package_code,
            "quantity": quantity,
            "source": "Approved BIM APU suggestion",
            "status": "assigned",
            "wbs_code": line.wbs_code,
        }
        line.raw_data = raw_data
        line.updated_at = utc_now()

    run.version += 1
    run.updated_at = utc_now()
    _audit(
        db,
        tenant_id,
        project_id,
        "approve_bim_apu_groups",
        "QuantityTakeoffRun",
        run_id,
        json.dumps({"line_count": len(lines), "line_ids": line_ids}),
        current_user.full_name,
    )
    db.commit()
    for line in lines:
        db.refresh(line)
    return lines


@router.post(
    "/projects/{project_id}/quantity-takeoff-runs/{run_id}/recalculate-rules",
    response_model=QuantityRuleRecalculationOut,
)
def recalculate_quantity_takeoff_rules(
    project_id: int,
    run_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> dict:
    _require_project(db, tenant_id, project_id)
    membership = _require_membership(db, tenant_id, project_id, user_id)
    if not (membership.can_capture_cost or membership.can_configure):
        raise HTTPException(status_code=403, detail="Current role cannot recalculate BIM quantity rules")
    result = QuantityTakeoffService(db).recalculate_rules(tenant_id, project_id, run_id)
    current_user = _require_user(db, tenant_id, user_id)
    _audit(
        db,
        tenant_id,
        project_id,
        "recalculate_quantity_rules",
        "QuantityTakeoffRun",
        run_id,
        json.dumps(
            {
                "changed_line_count": result["changed_line_count"],
                "blocked_count": result["blocked_count"],
                "cost_rollup_gate": result["cost_rollup_gate"],
            }
        ),
        current_user.full_name,
    )
    db.commit()
    return result


@router.get(
    "/projects/{project_id}/quantity-takeoff-runs/{run_id}/lines",
    response_model=list[QuantityTakeoffLineOut],
)
def list_quantity_takeoff_lines(
    project_id: int,
    run_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[QuantityTakeoffLine]:
    _require_project(db, tenant_id, project_id)
    _require_membership(db, tenant_id, project_id, user_id)
    run = db.scalar(
        select(QuantityTakeoffRun).where(
            QuantityTakeoffRun.tenant_id == tenant_id,
            QuantityTakeoffRun.project_id == project_id,
            QuantityTakeoffRun.id == run_id,
        )
    )
    if not run:
        raise HTTPException(status_code=404, detail="Quantity takeoff run not found")
    return list(
        db.scalars(
            select(QuantityTakeoffLine)
            .where(
                QuantityTakeoffLine.tenant_id == tenant_id,
                QuantityTakeoffLine.project_id == project_id,
                QuantityTakeoffLine.run_id == run_id,
            )
            .order_by(QuantityTakeoffLine.id)
        ).all()
    )


@router.post(
    "/projects/{project_id}/quantity-takeoff-runs/{run_id}/controlled-measurements",
    response_model=list[QuantityTakeoffLineOut],
)
def approve_controlled_measurements(
    project_id: int,
    run_id: int,
    payload: ControlledMeasurementApprovalIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[QuantityTakeoffLine]:
    _require_project(db, tenant_id, project_id)
    membership = _require_membership(db, tenant_id, project_id, user_id)
    if not (membership.can_capture_cost or membership.can_configure):
        raise HTTPException(status_code=403, detail="Current role cannot approve controlled BIM measurements")
    run = db.scalar(
        select(QuantityTakeoffRun).where(
            QuantityTakeoffRun.tenant_id == tenant_id,
            QuantityTakeoffRun.project_id == project_id,
            QuantityTakeoffRun.id == run_id,
        )
    )
    if not run:
        raise HTTPException(status_code=404, detail="Quantity takeoff run not found")
    line_ids = sorted({line_id for line_id in payload.line_ids if line_id > 0})
    measurement_rule = payload.measurement_rule.strip()
    if not line_ids:
        raise HTTPException(status_code=400, detail="At least one quantity line must be selected")
    if not measurement_rule:
        raise HTTPException(status_code=400, detail="Measurement rule is required")

    lines = list(
        db.scalars(
            select(QuantityTakeoffLine)
            .where(
                QuantityTakeoffLine.tenant_id == tenant_id,
                QuantityTakeoffLine.project_id == project_id,
                QuantityTakeoffLine.run_id == run_id,
                QuantityTakeoffLine.id.in_(line_ids),
            )
            .order_by(QuantityTakeoffLine.id)
        ).all()
    )
    if len(lines) != len(line_ids):
        raise HTTPException(status_code=404, detail="One or more quantity takeoff lines were not found")

    quantity_catalog = project_quantity_rule_catalog(db, tenant_id, project_id)
    approved_at = utc_now().isoformat()
    current_user = _require_user(db, tenant_id, user_id)
    source = payload.source.strip() or "Quantity table review"
    note = payload.note.strip()
    for line in lines:
        approved_quantity = float(payload.quantity) if payload.quantity is not None else line.quantity
        approved_unit = payload.unit.strip() if payload.unit and payload.unit.strip() else line.unit
        if approved_quantity <= 0:
            raise HTTPException(status_code=400, detail="Controlled quantity must be greater than zero")
        raw_data = dict(line.raw_data or {})
        candidate_raw_data = dict(raw_data)
        candidate_raw_data.pop("controlled_measurement", None)
        candidate_rule = evaluate_quantity_rule(
            {
                "category": line.category,
                "ifc_class": line.ifc_class,
                "measurement_rule": measurement_rule,
                "quantity": approved_quantity,
                "raw_data": candidate_raw_data,
                "unit": approved_unit,
                "validation_notes": "",
            },
            quantity_catalog,
        )
        if candidate_rule.get("status") != "valid":
            findings = "; ".join(str(item) for item in candidate_rule.get("findings", []))
            raise HTTPException(status_code=400, detail=f"Line {line.id} controlled measurement is invalid: {findings}")
        previous = raw_data.get("controlled_measurement")
        history = list(raw_data.get("controlled_measurement_history") or [])
        next_version = int(previous.get("version", 0)) + 1 if isinstance(previous, dict) else 1
        if isinstance(previous, dict):
            history.insert(0, previous)
        raw_data["controlled_measurement"] = {
            "approved_at": approved_at,
            "approved_by": current_user.full_name,
            "approved_by_user_id": current_user.id,
            "element_guid": line.element_guid,
            "line_id": line.id,
            "measurement_rule": measurement_rule,
            "note": note,
            "quantity": approved_quantity,
            "source": source,
            "source_quantity": line.quantity,
            "source_unit": line.unit,
            "status": "approved",
            "unit": approved_unit,
            "version": next_version,
        }
        raw_data["quantity_rule"] = evaluate_quantity_rule(
            {
                "category": line.category,
                "ifc_class": line.ifc_class,
                "measurement_rule": measurement_rule,
                "quantity": approved_quantity,
                "raw_data": raw_data,
                "unit": approved_unit,
                "validation_notes": "",
            },
            quantity_catalog,
        )
        raw_data["controlled_measurement_history"] = history[:20]
        line.raw_data = raw_data
        line.measurement_rule = measurement_rule
        line.validation_notes = _replace_controlled_measurement_note(line.validation_notes, next_version, source)
        line.updated_at = utc_now()

    run.version += 1
    run.updated_at = utc_now()
    _audit(
        db,
        tenant_id,
        project_id,
        "approve_controlled_bim_measurement",
        "QuantityTakeoffRun",
        run_id,
        json.dumps(
            {
                "line_count": len(lines),
                "line_ids": line_ids,
                "measurement_rule": measurement_rule,
                "source": source,
            }
        ),
        current_user.full_name,
    )
    db.commit()
    for line in lines:
        db.refresh(line)
    return lines


@router.post(
    "/projects/{project_id}/quantity-takeoff-runs/{run_id}/geometry-measurements",
    response_model=BimGeometryMeasurementBatchOut,
)
def process_geometry_measurements(
    project_id: int,
    run_id: int,
    payload: BimGeometryMeasurementBatchIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> dict:
    _require_project(db, tenant_id, project_id)
    membership = _require_membership(db, tenant_id, project_id, user_id)
    if not (membership.can_capture_cost or membership.can_configure):
        raise HTTPException(status_code=403, detail="Current role cannot process BIM geometry measurements")
    current_user = _require_user(db, tenant_id, user_id)
    result = BimGeometryQuantityService(db).process(
        tenant_id,
        project_id,
        run_id,
        payload.model_id,
        apply=payload.apply,
        line_ids=payload.line_ids,
        replace_valid=payload.replace_valid,
        approved_by=current_user.full_name,
        approved_by_user_id=current_user.id,
    )
    if payload.apply and result["applied_count"]:
        _audit(
            db,
            tenant_id,
            project_id,
            "approve_bulk_bim_geometry_measurements",
            "QuantityTakeoffRun",
            run_id,
            json.dumps(
                {
                    "model_id": payload.model_id,
                    "revision_id": result["revision_id"],
                    "applied_count": result["applied_count"],
                }
            ),
            current_user.full_name,
        )
    db.commit()
    return result


@router.post(
    "/projects/{project_id}/quantity-takeoff-runs/{run_id}/control-code-assignments",
    response_model=list[QuantityTakeoffLineOut],
)
def assign_quantity_control_codes(
    project_id: int,
    run_id: int,
    payload: QuantityControlCodeAssignmentIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[QuantityTakeoffLine]:
    _require_project(db, tenant_id, project_id)
    membership = _require_membership(db, tenant_id, project_id, user_id)
    if not (membership.can_capture_cost or membership.can_configure):
        raise HTTPException(status_code=403, detail="Current role cannot assign BIM quantity control codes")
    run = db.scalar(
        select(QuantityTakeoffRun).where(
            QuantityTakeoffRun.tenant_id == tenant_id,
            QuantityTakeoffRun.project_id == project_id,
            QuantityTakeoffRun.id == run_id,
        )
    )
    if not run:
        raise HTTPException(status_code=404, detail="Quantity takeoff run not found")
    line_ids = sorted({line_id for line_id in payload.line_ids if line_id > 0})
    if not line_ids:
        raise HTTPException(status_code=400, detail="At least one quantity line must be selected")

    wbs_code = payload.wbs_code.strip()
    cbs_code = payload.cbs_code.strip()
    fbs_code = payload.fbs_code.strip()
    package_code = payload.package_code.strip()
    cost_item_code = payload.cost_item_code.strip()
    cost_item_name = payload.cost_item_name.strip()
    budget_unit = payload.budget_unit.strip()
    unit_rate = float(payload.unit_rate) if payload.unit_rate is not None else None
    if unit_rate is not None and unit_rate < 0:
        raise HTTPException(status_code=400, detail="Unit rate cannot be negative")
    wbs, cbs, fbs, work_package = _require_quantity_assignment_catalog_codes(
        db,
        tenant_id,
        project_id,
        wbs_code,
        cbs_code,
        fbs_code,
        package_code,
    )

    lines = list(
        db.scalars(
            select(QuantityTakeoffLine)
            .where(
                QuantityTakeoffLine.tenant_id == tenant_id,
                QuantityTakeoffLine.project_id == project_id,
                QuantityTakeoffLine.run_id == run_id,
                QuantityTakeoffLine.id.in_(line_ids),
            )
            .order_by(QuantityTakeoffLine.id)
        ).all()
    )
    if len(lines) != len(line_ids):
        raise HTTPException(status_code=404, detail="One or more quantity takeoff lines were not found")

    current_user = _require_user(db, tenant_id, user_id)
    assigned_at = utc_now().isoformat()
    note = payload.note.strip()
    for line in lines:
        raw_data = dict(line.raw_data or {})
        controlled_measurement = raw_data.get("controlled_measurement")
        controlled_record = controlled_measurement if isinstance(controlled_measurement, dict) else {}
        controlled_quantity = controlled_record.get("quantity")
        budget_quantity = (
            float(controlled_quantity)
            if isinstance(controlled_quantity, int | float) and float(controlled_quantity) > 0
            else float(line.quantity or 0)
        )
        effective_budget_unit = budget_unit or str(controlled_record.get("unit") or line.unit or "").strip()
        budget_amount = round(budget_quantity * unit_rate, 2) if unit_rate is not None else 0
        raw_data["control_code_assignment"] = {
            "assigned_at": assigned_at,
            "assigned_by": current_user.full_name,
            "assigned_by_user_id": current_user.id,
            "cbs_code": cbs_code,
            "cbs_id": cbs.id,
            "fbs_code": fbs_code,
            "fbs_id": fbs.id,
            "line_id": line.id,
            "note": note,
            "package_code": package_code,
            "work_package_id": work_package.id,
            "status": "assigned",
            "wbs_code": wbs_code,
            "wbs_id": wbs.id,
        }
        if cost_item_code or cost_item_name or unit_rate is not None:
            raw_data["budget_item_assignment"] = {
                "apu_structure": payload.apu_structure,
                "assigned_at": assigned_at,
                "assigned_by": current_user.full_name,
                "assigned_by_user_id": current_user.id,
                "budget_amount": budget_amount,
                "budget_unit": effective_budget_unit,
                "catalog_item_id": payload.catalog_item_id,
                "cbs_code": cbs_code,
                "cost_item_code": cost_item_code,
                "cost_item_name": cost_item_name,
                "currency": payload.currency.strip(),
                "fbs_code": fbs_code,
                "license_note": payload.license_note.strip(),
                "line_id": line.id,
                "measurement_rule": line.measurement_rule,
                "package_code": package_code,
                "quantity": budget_quantity,
                "source": "BIM quantity controlled budget item",
                "source_key": payload.source_key.strip(),
                "source_url": payload.source_url.strip(),
                "status": "assigned" if cost_item_code and unit_rate is not None else "draft",
                "structure_note": payload.structure_note.strip(),
                "structure_status": payload.structure_status.strip(),
                "unit_rate": unit_rate or 0,
                "wbs_code": wbs_code,
            }
        line.raw_data = raw_data
        line.wbs_code = wbs_code
        line.cbs_code = cbs_code
        line.fbs_code = fbs_code
        line.package_code = package_code
        line.wbs_id = wbs.id
        line.cbs_id = cbs.id
        line.fbs_id = fbs.id
        line.work_package_id = work_package.id
        line.mapping_status = "mapped" if line.quantity > 0 else "needs_mapping"
        line.validation_notes = _replace_control_code_assignment_notes(line.validation_notes, line.mapping_status)
        line.updated_at = utc_now()

    db.flush()
    _refresh_quantity_run_mapping_counts(db, run)
    run.version += 1
    run.updated_at = utc_now()
    _audit(
        db,
        tenant_id,
        project_id,
        "assign_bim_quantity_control_codes",
        "QuantityTakeoffRun",
        run_id,
        json.dumps(
            {
                "cbs_code": cbs_code,
                "cbs_id": cbs.id,
                "fbs_code": fbs_code,
                "fbs_id": fbs.id,
                "line_count": len(lines),
                "line_ids": line_ids,
                "package_code": package_code,
                "work_package_id": work_package.id,
                "cost_item_code": cost_item_code,
                "cost_item_name": cost_item_name,
                "unit_rate": unit_rate,
                "wbs_code": wbs_code,
                "wbs_id": wbs.id,
            }
        ),
        current_user.full_name,
    )
    db.commit()
    for line in lines:
        db.refresh(line)
    return lines


@router.get("/projects/{project_id}/quantity-takeoff-runs/{run_id}/ifc-file")
def get_quantity_takeoff_ifc_file(
    project_id: int,
    run_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> FileResponse:
    _require_project(db, tenant_id, project_id)
    _require_membership(db, tenant_id, project_id, user_id)
    run = db.scalar(
        select(QuantityTakeoffRun).where(
            QuantityTakeoffRun.tenant_id == tenant_id,
            QuantityTakeoffRun.project_id == project_id,
            QuantityTakeoffRun.id == run_id,
        )
    )
    if not run:
        raise HTTPException(status_code=404, detail="Quantity takeoff run not found")
    path = QuantityTakeoffService.ifc_source_path(run)
    if path is None:
        raise HTTPException(status_code=404, detail="Stored IFC source file not found")
    return FileResponse(path, media_type="application/octet-stream", filename=run.source_file_name)


@router.get("/projects/{project_id}/bim-models", response_model=list[BimModelOut])
def list_bim_models(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[BimModel]:
    _require_project(db, tenant_id, project_id)
    _require_membership(db, tenant_id, project_id, user_id)
    models = list(
        db.scalars(
            select(BimModel)
            .where(BimModel.tenant_id == tenant_id, BimModel.project_id == project_id)
            .order_by(BimModel.created_at.desc(), BimModel.id.desc())
        ).all()
    )
    service = BimModelService(db)
    changed = False
    for model in models:
        changed = service.ensure_revision_identity(model) or changed
    if changed:
        db.commit()
    return models


@router.post("/projects/{project_id}/bim-models", response_model=BimModelOut)
async def upload_bim_model(
    project_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> BimModel:
    _require_project(db, tenant_id, project_id)
    membership = _require_membership(db, tenant_id, project_id, user_id)
    if not (membership.can_capture_cost or membership.can_configure):
        raise HTTPException(status_code=403, detail="Current role cannot load BIM model data")
    content = await file.read()
    model = BimModelService(db).create_ifc_model(
        tenant_id,
        project_id,
        user_id,
        file.filename or "model.ifc",
        content,
    )
    current_user = _require_user(db, tenant_id, user_id)
    _audit(
        db,
        tenant_id,
        project_id,
        "upload_bim_model",
        "BimModel",
        model.id,
        json.dumps(
            {
                "source_file_name": model.source_file_name,
                "source_size_bytes": model.source_size_bytes,
                "viewer_engine": model.model_identity.get("viewer_engine", ""),
            }
        ),
        current_user.full_name,
    )
    db.commit()
    db.refresh(model)
    return model


@router.get("/projects/{project_id}/bim-models/{model_id}/source")
def get_bim_model_source(
    project_id: int,
    model_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> FileResponse:
    _require_project(db, tenant_id, project_id)
    _require_membership(db, tenant_id, project_id, user_id)
    model = db.scalar(
        select(BimModel).where(
            BimModel.tenant_id == tenant_id,
            BimModel.project_id == project_id,
            BimModel.id == model_id,
        )
    )
    if not model:
        raise HTTPException(status_code=404, detail="BIM model not found")
    path = BimModelService.source_path(model)
    if path is None:
        raise HTTPException(status_code=404, detail="Stored IFC model source file not found")
    return FileResponse(path, media_type="application/octet-stream", filename=model.source_file_name)


@router.get("/projects/{project_id}/bim-models/{model_id}/viewer-manifest")
def get_bim_model_viewer_manifest(
    project_id: int,
    model_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> dict:
    _require_project(db, tenant_id, project_id)
    _require_membership(db, tenant_id, project_id, user_id)
    manifest = BimModelService(db).viewer_manifest(tenant_id, project_id, model_id)
    db.commit()
    return manifest


@router.get("/projects/{project_id}/bim-models/{model_id}/element-properties")
def get_bim_model_element_properties(
    project_id: int,
    model_id: int,
    element_key: str = Query(min_length=1),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> dict:
    _require_project(db, tenant_id, project_id)
    _require_membership(db, tenant_id, project_id, user_id)
    return BimModelService(db).element_properties(tenant_id, project_id, model_id, element_key)


@router.post("/projects/{project_id}/bim-models/{model_id}/viewer-cache")
def prepare_bim_model_viewer_cache(
    project_id: int,
    model_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> dict:
    _require_project(db, tenant_id, project_id)
    membership = _require_membership(db, tenant_id, project_id, user_id)
    if not (membership.can_capture_cost or membership.can_configure):
        raise HTTPException(status_code=403, detail="Current role cannot prepare BIM geometry cache")
    summary = BimModelService(db).prepare_geometry_cache(tenant_id, project_id, model_id)
    current_user = _require_user(db, tenant_id, user_id)
    _audit(
        db,
        tenant_id,
        project_id,
        "prepare_bim_geometry_cache",
        "BimModel",
        model_id,
        json.dumps(
            {
                "engine": summary.get("engine", ""),
                "mesh_count": summary.get("mesh_count", 0),
                "triangle_count": summary.get("triangle_count", 0),
            }
        ),
        current_user.full_name,
    )
    db.commit()
    return summary


@router.get("/projects/{project_id}/bim-models/{model_id}/geometry-cache")
def get_bim_model_geometry_cache(
    project_id: int,
    model_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> FileResponse:
    _require_project(db, tenant_id, project_id)
    _require_membership(db, tenant_id, project_id, user_id)
    path = BimModelService(db).geometry_cache(tenant_id, project_id, model_id)
    return FileResponse(path, media_type="application/json", filename="geometry_cache.json")


@router.delete("/projects/{project_id}/bim-models/{model_id}")
def delete_bim_model(
    project_id: int,
    model_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> dict[str, str | int]:
    _require_project(db, tenant_id, project_id)
    membership = _require_membership(db, tenant_id, project_id, user_id)
    if not (membership.can_capture_cost or membership.can_configure):
        raise HTTPException(status_code=403, detail="Current role cannot clear BIM model data")
    BimModelService(db).delete_model(tenant_id, project_id, model_id)
    current_user = _require_user(db, tenant_id, user_id)
    _audit(
        db,
        tenant_id,
        project_id,
        "delete_bim_model",
        "BimModel",
        model_id,
        json.dumps({"status": "deleted"}),
        current_user.full_name,
    )
    db.commit()
    return {"status": "deleted", "model_id": model_id}


@router.post("/projects/{project_id}/quantity-takeoffs/import", response_model=QuantityTakeoffRunOut)
async def import_quantity_takeoff(
    project_id: int,
    file: UploadFile = File(...),
    bim_model_id: int | None = Form(default=None),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> QuantityTakeoffRun:
    _require_project(db, tenant_id, project_id)
    membership = _require_membership(db, tenant_id, project_id, user_id)
    if not (membership.can_capture_cost or membership.can_configure):
        raise HTTPException(status_code=403, detail="Current role cannot load quantity takeoff data")
    content = await file.read()
    run = QuantityTakeoffService(db).import_file(
        tenant_id,
        project_id,
        file.filename or "quantity-takeoff",
        content,
        bim_model_id=bim_model_id,
    )
    current_user = _require_user(db, tenant_id, user_id)
    _audit(
        db,
        tenant_id,
        project_id,
        "import_quantity_takeoff",
        "QuantityTakeoffRun",
        run.id,
        json.dumps(
            {
                "source_file_name": run.source_file_name,
                "source_type": run.source_type,
                "row_count": run.row_count,
                "mapped_line_count": run.mapped_line_count,
            }
        ),
        current_user.full_name,
    )
    db.commit()
    db.refresh(run)
    return run


@router.put(
    "/projects/{project_id}/quantity-takeoff-runs/{run_id}/bim-model",
    response_model=QuantityTakeoffRunOut,
)
def link_quantity_takeoff_bim_model(
    project_id: int,
    run_id: int,
    payload: QuantityTakeoffModelLinkIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> QuantityTakeoffRun:
    _require_project(db, tenant_id, project_id)
    membership = _require_membership(db, tenant_id, project_id, user_id)
    if not (membership.can_capture_cost or membership.can_configure):
        raise HTTPException(status_code=403, detail="Current role cannot link BIM model revisions")
    run = QuantityTakeoffService(db).link_model(
        tenant_id,
        project_id,
        run_id,
        payload.model_id,
        payload.expected_version,
    )
    current_user = _require_user(db, tenant_id, user_id)
    _audit(
        db,
        tenant_id,
        project_id,
        "link_quantity_takeoff_bim_model",
        "QuantityTakeoffRun",
        run.id,
        json.dumps(
            {
                "bim_model_id": run.bim_model_id,
                "bim_revision_id": run.bim_revision_id,
                "source_sha256": run.source_sha256,
            }
        ),
        current_user.full_name,
    )
    db.commit()
    db.refresh(run)
    return run


def _activity_sheet_enriched_rows(
    db: Session,
    tenant_id: int,
    project_id: int,
    activity_sheet: ActivitySheet,
) -> list[dict[str, object]]:
    activity_rows = list(
        db.scalars(
            select(ActivitySheetRow)
            .where(
                ActivitySheetRow.tenant_id == tenant_id,
                ActivitySheetRow.project_id == project_id,
                ActivitySheetRow.activity_sheet_id == activity_sheet.id,
            )
            .order_by(ActivitySheetRow.external_activity_id)
        ).all()
    )
    if not activity_rows:
        return []

    schedule_rows = list(
        db.scalars(
            select(ScheduleActivityMap).where(
                ScheduleActivityMap.tenant_id == tenant_id,
                ScheduleActivityMap.project_id == project_id,
                ScheduleActivityMap.schedule_import_id == activity_sheet.schedule_import_id,
            )
        ).all()
    )
    schedule_row_by_external_id = {row.external_activity_id: row for row in schedule_rows}
    mappings = list(
        db.scalars(
            select(ControlAccountMapping).where(
                ControlAccountMapping.tenant_id == tenant_id,
                ControlAccountMapping.project_id == project_id,
                ControlAccountMapping.schedule_import_id == activity_sheet.schedule_import_id,
            )
        ).all()
    )
    mapping_by_schedule_row_id = {mapping.schedule_activity_map_id: mapping for mapping in mappings}
    account_ids = {mapping.control_account_id for mapping in mappings if mapping.control_account_id}
    accounts_by_id = {
        account.id: account
        for account in db.scalars(
            select(ControlAccount).where(
                ControlAccount.tenant_id == tenant_id,
                ControlAccount.project_id == project_id,
                ControlAccount.id.in_(account_ids),
            )
        ).all()
    } if account_ids else {}

    enriched: list[dict[str, object]] = []
    for row in activity_rows:
        schedule_row = schedule_row_by_external_id.get(row.external_activity_id)
        mapping = mapping_by_schedule_row_id.get(schedule_row.id) if schedule_row else None
        account = accounts_by_id.get(mapping.control_account_id) if mapping and mapping.control_account_id else None
        planned_cost = row.planned_cost or (mapping.planned_cost if mapping else 0)
        enriched.append(
            {
                "id": row.id,
                "activity_sheet_id": row.activity_sheet_id,
                "external_activity_id": row.external_activity_id,
                "wbs_code": row.wbs_code,
                "activity_name": row.activity_name,
                "planned_start": row.planned_start,
                "planned_finish": row.planned_finish,
                "total_float_days": row.total_float_days,
                "critical_path": row.critical_path,
                "planned_cost": round(float(planned_cost or 0), 2),
                "planned_value": round(float(mapping.planned_value if mapping else 0), 2),
                "planned_percent": round(float(mapping.planned_percent if mapping else 0), 2),
                "cbs_code": mapping.cbs_code if mapping else "",
                "control_account_id": mapping.control_account_id if mapping else None,
                "control_account_code": account.code if account else "",
                "mapping_status": mapping.status if mapping else "unmapped",
                "review_note": mapping.review_note if mapping else "Activity has no control account mapping.",
            }
        )
    return enriched


def _get_project_operational_setup(
    db: Session, tenant_id: int, project_id: int
) -> ProjectOperationalSetup | None:
    return db.scalar(
        select(ProjectOperationalSetup).where(
            ProjectOperationalSetup.tenant_id == tenant_id,
            ProjectOperationalSetup.project_id == project_id,
        )
    )


def _replace_controlled_measurement_note(validation_notes: str, version: int, source: str) -> str:
    notes = [
        note.strip()
        for note in (validation_notes or "").split(";")
        if note.strip() and not note.strip().startswith("Controlled measurement approved")
    ]
    notes.append(f"Controlled measurement approved v{version} from {source}.")
    return "; ".join(notes)


def _require_quantity_assignment_catalog_codes(
    db: Session,
    tenant_id: int,
    project_id: int,
    wbs_code: str,
    cbs_code: str,
    fbs_code: str,
    package_code: str,
) -> tuple[WBS, CostBreakdownStructure, FundingSource, WorkPackage]:
    required = {
        "WBS code is required": wbs_code,
        "CBS code is required": cbs_code,
        "FBS code is required": fbs_code,
        "Package code is required": package_code,
    }
    for message, value in required.items():
        if not value:
            raise HTTPException(status_code=400, detail=message)
    wbs = db.scalar(
        select(WBS).where(WBS.tenant_id == tenant_id, WBS.project_id == project_id, WBS.code == wbs_code)
    )
    if not wbs:
        raise HTTPException(status_code=404, detail="WBS code not found")
    cbs = db.scalar(
        select(CostBreakdownStructure).where(
            CostBreakdownStructure.tenant_id == tenant_id,
            CostBreakdownStructure.project_id == project_id,
            CostBreakdownStructure.code == cbs_code,
        )
    )
    if not cbs:
        raise HTTPException(status_code=404, detail="CBS code not found")
    fbs = db.scalar(
        select(FundingSource).where(
            FundingSource.tenant_id == tenant_id,
            FundingSource.project_id == project_id,
            FundingSource.code == fbs_code,
        )
    )
    if not fbs:
        raise HTTPException(status_code=404, detail="FBS code not found")
    work_package = db.scalar(
        select(WorkPackage).where(
            WorkPackage.tenant_id == tenant_id,
            WorkPackage.project_id == project_id,
            WorkPackage.code == package_code,
        )
    )
    if not work_package:
        raise HTTPException(status_code=404, detail="Package code not found")
    return wbs, cbs, fbs, work_package


def _replace_control_code_assignment_notes(validation_notes: str, mapping_status: str) -> str:
    stale_prefixes = (
        "Missing WBS",
        "Unknown WBS",
        "Missing CBS",
        "Unknown CBS",
        "Missing FBS",
        "Unknown FBS",
        "Missing package",
        "Unknown package",
        "Control codes assigned",
        "Quantity must be greater than zero",
    )
    notes = [
        note.strip()
        for note in (validation_notes or "").split(";")
        if note.strip() and not note.strip().startswith(stale_prefixes)
    ]
    if mapping_status == "mapped":
        notes.append("Control codes assigned.")
    else:
        notes.extend(["Control codes assigned.", "Quantity must be greater than zero"])
    return "; ".join(notes)


def _quantity_unit_key(unit: str) -> str:
    normalized = unit.strip().lower().replace(" ", "")
    aliases = {
        "u": "ea",
        "un": "ea",
        "und": "ea",
        "unidad": "ea",
        "unidades": "ea",
        "m²": "m2",
        "m³": "m3",
    }
    return aliases.get(normalized, normalized)


def _refresh_quantity_run_mapping_counts(db: Session, run: QuantityTakeoffRun) -> None:
    mapped_count = int(
        db.scalar(
            select(func.count(QuantityTakeoffLine.id)).where(
                QuantityTakeoffLine.tenant_id == run.tenant_id,
                QuantityTakeoffLine.project_id == run.project_id,
                QuantityTakeoffLine.run_id == run.id,
                QuantityTakeoffLine.mapping_status == "mapped",
            )
        )
        or 0
    )
    total_count = int(
        db.scalar(
            select(func.count(QuantityTakeoffLine.id)).where(
                QuantityTakeoffLine.tenant_id == run.tenant_id,
                QuantityTakeoffLine.project_id == run.project_id,
                QuantityTakeoffLine.run_id == run.id,
            )
        )
        or 0
    )
    run.mapped_line_count = mapped_count
    run.unmapped_line_count = max(total_count - mapped_count, 0)


def _require_operational_setup_ready(db: Session, tenant_id: int, project_id: int) -> ProjectOperationalSetup:
    setup = _get_project_operational_setup(db, tenant_id, project_id)
    if not setup:
        raise HTTPException(
            status_code=409,
            detail="Project operational setup must be completed before loading activity data",
        )
    _apply_operational_setup_readiness(setup)
    if setup.readiness_status != "ready":
        raise HTTPException(
            status_code=409,
            detail=f"Project operational setup is not ready: {setup.readiness_notes}",
        )
    return setup


def _apply_operational_setup_readiness(setup: ProjectOperationalSetup) -> None:
    missing = _operational_setup_missing_items(setup)
    setup.readiness_status = "ready" if not missing and setup.status in {"ready", "active"} else "not_ready"
    setup.readiness_notes = "Ready for controlled data loading." if not missing else ", ".join(missing)


def _operational_setup_missing_items(setup: ProjectOperationalSetup) -> list[str]:
    missing: list[str] = []
    for field, label in (
        ("project_number", "project number"),
        ("setup_template", "setup template"),
        ("attribute_form", "attribute form"),
    ):
        if not str(getattr(setup, field, "") or "").strip():
            missing.append(label)
    for field, label in (
        ("permissions_configured", "permissions"),
        ("modules_configured", "modules"),
        ("cost_sheet_ready", "cost sheet"),
        ("funding_sheet_ready", "funding sheet"),
        ("p6_mapping_ready", "P6 mapping"),
    ):
        if not bool(getattr(setup, field)):
            missing.append(label)
    return missing


def _enum_value(value: object) -> str:
    return str(getattr(value, "value", value))
