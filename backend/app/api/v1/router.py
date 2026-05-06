import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from fastapi.responses import PlainTextResponse
from redis import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.core.config import get_settings
from app.core.observability import METRICS
from app.core.security import create_access_token, hash_password, verify_password
from app.database.session import get_db
from app.domain.models import (
    Activity,
    ActivityRelationship,
    Alert,
    AuthCredential,
    AuditLog,
    BaselineVersion,
    Budget,
    BusinessProcessInstance,
    BusinessProcessStepTemplate,
    BusinessProcessTemplate,
    BusinessProcessTransitionTemplate,
    ChangeRequest,
    Claim,
    ClaimEntitlementItem,
    ClaimImpactAnalysis,
    Contract,
    ContractCommunication,
    ContractNotice,
    ControlAccount,
    ControlAccountMapping,
    ControlPeriod,
    ControlSnapshot,
    CashFlowPeriod,
    CostRecord,
    CostSource,
    Document,
    DocumentReview,
    DocumentTransmittal,
    DocumentTransmittalItem,
    ForecastScenario,
    FundingSource,
    ImportStatus,
    KPI,
    PaymentCertificate,
    ProgressRecord,
    ProjectMail,
    Project,
    ProjectControlPlan,
    ProjectMembership,
    PurchaseOrder,
    RFQBid,
    RFQPackage,
    ScheduleActivityMap,
    ScheduleImport,
    ScheduleValidationFinding,
    Tenant,
    UserAccount,
    WarehouseReceipt,
    WorkPackage,
    WorkPackageConstraint,
    WBS,
    WorkflowStepInstance,
)
from app.domain.process_catalog import DEFAULT_PROCESS_TEMPLATES
from app.domain.schemas import (
    ActivityCreate,
    ActivityOut,
    AlertOut,
    AuditLogOut,
    BaselineVersionOut,
    BusinessProcessInstanceOut,
    CashFlowPeriodCreate,
    CashFlowPeriodOut,
    CashFlowPeriodUpdate,
    ChangeRequestCreate,
    ChangeRequestOut,
    ClaimOut,
    ClaimEntitlementItemCreate,
    ClaimEntitlementItemOut,
    ClaimEntitlementItemUpdate,
    ClaimEntitlementSummary,
    ClaimImpactAnalysisCreate,
    ClaimImpactAnalysisOut,
    ClaimImpactAnalysisUpdate,
    ClaimsForensicSummary,
    ContractCommunicationCreate,
    ContractCommunicationOut,
    ContractCreate,
    ContractNoticeCreate,
    ContractNoticeOut,
    ContractOut,
    ControlAccountCreate,
    ControlAccountMappingOut,
    ControlAccountMappingSummary,
    ControlAccountOut,
    ControlAccountUpdate,
    ControlCoreLoop,
    ControlPeriodOut,
    ControlSnapshotOut,
    CostRecordCreate,
    CostRecordOut,
    CostManagerSummaryOut,
    CostSheetLineOut,
    DataQualityGateOut,
    DashboardOut,
    DocumentOut,
    DocumentCreate,
    DocumentControlSummary,
    DocumentReviewCreate,
    DocumentReviewOut,
    DocumentReviewUpdate,
    DocumentTransmittalCreate,
    DocumentTransmittalItemOut,
    DocumentTransmittalOut,
    DocumentUpdate,
    ForecastScenarioOut,
    FundingSourceCreate,
    FundingSourceOut,
    FundingSourceUpdate,
    AuthSessionOut,
    KPIOut,
    LoginRequest,
    PaymentCertificateCreate,
    PaymentCertificateOut,
    PaymentCertificateUpdate,
    PilotReadinessItem,
    PilotReadinessOut,
    ProcessStepTemplateOut,
    ProcessTemplateCreate,
    ProcessTemplateOut,
    ProcessTransitionTemplateOut,
    ProjectCreate,
    ProjectMailCreate,
    ProjectMailOut,
    ProjectMailUpdate,
    ProjectControlPlanOut,
    ProjectControlPlanUpdate,
    ProjectMembershipOut,
    ProjectMembershipCreate,
    ProjectTeamMemberOut,
    ProgressRecordCreate,
    ProgressRecordOut,
    ProductivitySummary,
    PurchaseOrderCreate,
    PurchaseOrderOut,
    PurchaseOrderUpdate,
    RFQBidCreate,
    RFQBidOut,
    RFQBidUpdate,
    RFQPackageCreate,
    RFQPackageOut,
    RFQPackageUpdate,
    RFQSummary,
    ProjectOut,
    ScheduleActivityMapOut,
    ScheduleImportOut,
    ScheduleValidationFindingOut,
    TCMFlowStep,
    RoleProfileOut,
    UserCreate,
    UserOut,
    AWPReadinessSummary,
    WarehouseReceiptCreate,
    WarehouseReceiptOut,
    WarehouseReceiptUpdate,
    WBSOut,
    WorkPackageConstraintCreate,
    WorkPackageConstraintOut,
    WorkPackageConstraintUpdate,
    WorkPackageCreate,
    WorkPackageOut,
    WorkPackageReadinessUpdate,
    WorkflowActionIn,
    WorkflowStepInstanceOut,
)
from app.services.ai_insights import AIInsightService
from app.services.control_core import ControlCoreService
from app.services.schedule_ingestion import ScheduleIngestionService
from app.services.workflow_routing import WorkflowRoutingService
from app.workers.tasks import run_control_cycle as run_control_cycle_task

router = APIRouter(prefix="/api/v1")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/live")
def liveness() -> dict[str, object]:
    settings = get_settings()
    return {
        "status": "live",
        "environment": settings.app_environment,
        "version": settings.app_version,
        "commit": settings.commit_sha,
        "uptime_seconds": METRICS.snapshot()["uptime_seconds"],
    }


@router.get("/health/ready")
def readiness(db: Session = Depends(get_db)) -> dict[str, object]:
    checks: dict[str, str] = {"api": "ok"}
    try:
        db.execute(select(1)).scalar_one()
        checks["database"] = "ok"
    except SQLAlchemyError:
        checks["database"] = "error"

    try:
        redis = Redis.from_url(get_settings().redis_url, socket_connect_timeout=1, socket_timeout=1)
        redis.ping()
        checks["redis"] = "ok"
    except RedisError:
        checks["redis"] = "error"

    status = "ready" if all(value == "ok" for value in checks.values()) else "degraded"
    if status != "ready":
        raise HTTPException(status_code=503, detail={"status": status, "checks": checks})
    settings = get_settings()
    return {
        "status": status,
        "checks": checks,
        "environment": settings.app_environment,
        "version": settings.app_version,
        "commit": settings.commit_sha,
    }


@router.get("/ops/metrics", response_class=PlainTextResponse)
def metrics(x_metrics_token: str = Header(default="", alias="X-Metrics-Token")) -> PlainTextResponse:
    settings = get_settings()
    if not settings.metrics_enabled:
        raise HTTPException(status_code=404, detail="Metrics endpoint disabled")
    if settings.metrics_token and not x_metrics_token:
        raise HTTPException(status_code=401, detail="Metrics token is required")
    if settings.metrics_token and x_metrics_token != settings.metrics_token:
        raise HTTPException(status_code=403, detail="Invalid metrics token")
    payload = METRICS.prometheus(settings.app_name, settings.app_environment, settings.app_version)
    return PlainTextResponse(payload, media_type="text/plain; version=0.0.4")


@router.post("/auth/login", response_model=AuthSessionOut)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> AuthSessionOut:
    tenant_filter = Tenant.id == payload.tenant_id if payload.tenant_id else Tenant.slug == payload.tenant_slug
    tenant = db.scalar(select(Tenant).where(tenant_filter))
    if not tenant:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user = db.scalar(
        select(UserAccount).where(
            UserAccount.tenant_id == tenant.id,
            UserAccount.email == payload.email.strip().lower(),
            UserAccount.status == "active",
        )
    )
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

    settings = get_settings()
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


@router.get("/auth/me", response_model=UserOut)
def current_user(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> UserAccount:
    return _require_user(db, tenant_id, user_id)


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
    _audit(db, tenant_id, project.id, "create_project_shell", "Project", project.id, f'{{"code":"{project.code}"}}', current_user.full_name)
    db.commit()
    db.refresh(project)
    return project


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
    _audit(db, tenant_id, None, "create_user", "UserAccount", user.id, f'{{"email":"{user.email}"}}', current_user.full_name)
    db.commit()
    db.refresh(user)
    return user


@router.get("/roles", response_model=list[RoleProfileOut])
def list_roles(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[RoleProfileOut]:
    _require_user(db, tenant_id, user_id)
    return _role_profiles()


@router.get("/process-templates", response_model=list[ProcessTemplateOut])
def list_process_templates(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ProcessTemplateOut]:
    _require_user(db, tenant_id, user_id)
    return _configured_process_templates(db, tenant_id)


@router.post("/process-templates", response_model=ProcessTemplateOut)
def create_process_template(
    payload: ProcessTemplateCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProcessTemplateOut:
    current_user = _require_tenant_configurator(db, tenant_id, user_id)
    code = payload.code.strip().upper()
    if not code:
        raise HTTPException(status_code=400, detail="Process code is required")
    existing = db.scalar(select(BusinessProcessTemplate).where(BusinessProcessTemplate.tenant_id == tenant_id, BusinessProcessTemplate.code == code))
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
        ProcessStepTemplateOut(step_order=1, name="Creation", detail="Record is created and validated.", owner_role="Originator", status="Active", tone="active"),
        ProcessStepTemplateOut(step_order=2, name="Review", detail="Responsible role reviews business impact.", owner_role="Project Controls", status="Queued", tone="queued"),
        ProcessStepTemplateOut(step_order=3, name="Approval", detail="Governance approval is captured.", owner_role="Control Manager", status="Queued", tone="queued"),
        ProcessStepTemplateOut(step_order=4, name="Action", detail="Approved decision is converted into execution action.", owner_role="Execution Lead", status="Queued", tone="queued"),
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

    _audit(db, tenant_id, None, "create_process_template", "BusinessProcessTemplate", template.id, f'{{"code":"{template.code}"}}', current_user.full_name)
    db.commit()
    return _process_template_out(db, template)


@router.get("/projects/{project_id}/team", response_model=list[ProjectTeamMemberOut])
def list_project_team(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ProjectTeamMemberOut]:
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
    _audit(db, tenant_id, project_id, "assign_project_role", "ProjectMembership", target_membership.id, f'{{"user_id":{target_user.id},"role":"{payload.role}"}}', current_user.full_name)
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


@router.get("/projects/{project_id}/wbs", response_model=list[WBSOut])
def list_wbs(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[WBS]:
    _require_membership(db, tenant_id, project_id, user_id)
    return list(
        db.scalars(
            select(WBS)
            .where(WBS.project_id == project_id, WBS.tenant_id == tenant_id)
            .order_by(WBS.code)
        ).all()
    )


@router.get("/projects/{project_id}/activities", response_model=list[ActivityOut])
def list_activities(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[Activity]:
    _require_membership(db, tenant_id, project_id, user_id)
    return list(
        db.scalars(
            select(Activity)
            .where(Activity.project_id == project_id, Activity.tenant_id == tenant_id)
            .order_by(Activity.code)
        ).all()
    )


@router.post("/projects/{project_id}/activities", response_model=ActivityOut)
def create_activity(
    project_id: int,
    payload: ActivityCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> Activity:
    _require_membership(db, tenant_id, project_id, user_id)
    _require_control_ready(db, tenant_id, project_id)
    account = _require_control_account(db, tenant_id, project_id, payload.control_account_id)
    activity = Activity(
        tenant_id=tenant_id,
        project_id=project_id,
        control_account_id=account.id,
        code=payload.code,
        name=payload.name,
        logic_type=payload.logic_type,
        baseline_start=payload.baseline_start,
        baseline_finish=payload.baseline_finish,
        planned_percent=payload.planned_percent,
        critical_path=payload.critical_path,
        lookahead_window=payload.lookahead_window,
    )
    db.add(activity)
    db.flush()
    _audit(db, tenant_id, project_id, "create_activity", "Activity", activity.id, f'{{"code":"{activity.code}"}}')
    db.commit()
    db.refresh(activity)
    return activity


@router.get("/projects/{project_id}/control-accounts", response_model=list[ControlAccountOut])
def list_control_accounts(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ControlAccount]:
    _require_membership(db, tenant_id, project_id, user_id)
    return list(
        db.scalars(
            select(ControlAccount)
            .where(ControlAccount.project_id == project_id, ControlAccount.tenant_id == tenant_id)
            .order_by(ControlAccount.code)
        ).all()
    )


@router.post("/projects/{project_id}/control-accounts", response_model=ControlAccountOut)
def create_control_account(
    project_id: int,
    payload: ControlAccountCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ControlAccount:
    _require_membership(db, tenant_id, project_id, user_id)
    _require_control_ready(db, tenant_id, project_id)
    wbs_id = payload.wbs_id or _default_wbs(db, tenant_id, project_id).id
    wbs = db.scalar(select(WBS).where(WBS.id == wbs_id, WBS.tenant_id == tenant_id, WBS.project_id == project_id))
    if not wbs:
        raise HTTPException(status_code=404, detail="WBS not found")
    account = ControlAccount(
        tenant_id=tenant_id,
        project_id=project_id,
        wbs_id=wbs.id,
        code=payload.code,
        name=payload.name,
        responsible=payload.responsible,
        discipline=payload.discipline,
    )
    db.add(account)
    db.flush()
    _audit(db, tenant_id, project_id, "create_control_account", "ControlAccount", account.id, f'{{"code":"{account.code}"}}')
    db.commit()
    db.refresh(account)
    return account


@router.patch("/projects/{project_id}/control-accounts/{account_id}", response_model=ControlAccountOut)
def update_control_account(
    project_id: int,
    account_id: int,
    payload: ControlAccountUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ControlAccount:
    _require_membership(db, tenant_id, project_id, user_id)
    account = _require_control_account(db, tenant_id, project_id, account_id)
    _require_current_version(account, payload.expected_version)
    for field, value in payload.model_dump(exclude_unset=True, exclude={"expected_version"}).items():
        setattr(account, field, value)
    _touch_collaborative_record(account)
    _audit(db, tenant_id, project_id, "update_control_account", "ControlAccount", account.id, f'{{"code":"{account.code}"}}')
    db.commit()
    db.refresh(account)
    return account


@router.get("/projects/{project_id}/control-account-mappings", response_model=list[ControlAccountMappingOut])
def list_control_account_mappings(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ControlAccountMapping]:
    _require_membership(db, tenant_id, project_id, user_id)
    latest_import = _latest_schedule_import(db, tenant_id, project_id)
    if not latest_import:
        return []
    return list(
        db.scalars(
            select(ControlAccountMapping)
            .where(
                ControlAccountMapping.tenant_id == tenant_id,
                ControlAccountMapping.project_id == project_id,
                ControlAccountMapping.schedule_import_id == latest_import.id,
            )
            .order_by(ControlAccountMapping.wbs_code, ControlAccountMapping.cbs_code, ControlAccountMapping.id)
        ).all()
    )


@router.post("/projects/{project_id}/control-account-mapping/approve", response_model=BaselineVersionOut)
def approve_control_account_mapping(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> BaselineVersion:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_approve_workflow", "Current role cannot approve the control baseline")
    current_user = _require_user(db, tenant_id, user_id)
    latest_import = _latest_schedule_import(db, tenant_id, project_id)
    if not latest_import:
        raise HTTPException(status_code=409, detail="Load a source schedule before approving the control baseline")
    baseline = db.scalar(
        select(BaselineVersion).where(
            BaselineVersion.tenant_id == tenant_id,
            BaselineVersion.project_id == project_id,
            BaselineVersion.schedule_import_id == latest_import.id,
        )
    )
    if not baseline:
        raise HTTPException(status_code=404, detail="Baseline version not found")
    mappings = list(
        db.scalars(
            select(ControlAccountMapping).where(
                ControlAccountMapping.tenant_id == tenant_id,
                ControlAccountMapping.project_id == project_id,
                ControlAccountMapping.schedule_import_id == latest_import.id,
            )
        ).all()
    )
    summary = _control_account_mapping_summary(mappings, baseline.status)
    if summary.total_schedule_activities == 0 or summary.mapping_score < 100:
        raise HTTPException(status_code=409, detail="All schedule activities must be mapped before baseline approval")
    if summary.cost_loading_score < 80:
        raise HTTPException(status_code=409, detail="Cost loading coverage must be at least 80% before baseline approval")
    baseline.status = "approved"
    _audit(db, tenant_id, project_id, "approve_control_baseline", "BaselineVersion", baseline.id, f'{{"mapping_score":{summary.mapping_score},"cost_loading_score":{summary.cost_loading_score}}}', current_user.full_name)
    db.commit()
    db.refresh(baseline)
    return baseline


@router.get("/projects/{project_id}/progress-records", response_model=list[ProgressRecordOut])
def list_progress_records(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ProgressRecord]:
    _require_membership(db, tenant_id, project_id, user_id)
    return list(
        db.scalars(
            select(ProgressRecord)
            .where(ProgressRecord.project_id == project_id, ProgressRecord.tenant_id == tenant_id)
            .order_by(ProgressRecord.reported_on.desc(), ProgressRecord.id.desc())
        ).all()
    )


@router.post("/projects/{project_id}/progress-records", response_model=ProgressRecordOut)
def create_progress_record(
    project_id: int,
    payload: ProgressRecordCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProgressRecord:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_capture_progress", "Current role cannot capture progress")
    _require_control_ready(db, tenant_id, project_id)
    _require_control_account(db, tenant_id, project_id, payload.control_account_id)
    current_user = _require_user(db, tenant_id, user_id)
    if payload.physical_percent < 0 or payload.physical_percent > 100:
        raise HTTPException(status_code=400, detail="Physical percent must be between 0 and 100")
    record = ProgressRecord(
        tenant_id=tenant_id,
        project_id=project_id,
        control_account_id=payload.control_account_id,
        physical_percent=payload.physical_percent,
        quantity_installed=payload.quantity_installed,
        labor_hours=payload.labor_hours,
        reported_on=payload.reported_on,
        evidence_ref=payload.evidence_ref,
    )
    db.add(record)
    db.flush()
    _audit(db, tenant_id, project_id, "capture_progress", "ProgressRecord", record.id, f'{{"control_account_id":{record.control_account_id}}}', current_user.full_name)
    db.commit()
    ControlCoreService(db).run_project_cycle(tenant_id, project_id)
    db.refresh(record)
    return record


@router.get("/projects/{project_id}/cost-records", response_model=list[CostRecordOut])
def list_cost_records(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[CostRecord]:
    _require_membership(db, tenant_id, project_id, user_id)
    return list(
        db.scalars(
            select(CostRecord)
            .where(CostRecord.project_id == project_id, CostRecord.tenant_id == tenant_id)
            .order_by(CostRecord.incurred_on.desc(), CostRecord.id.desc())
        ).all()
    )


@router.post("/projects/{project_id}/cost-records", response_model=CostRecordOut)
def create_cost_record(
    project_id: int,
    payload: CostRecordCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> CostRecord:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_capture_cost", "Current role cannot capture actual cost")
    _require_control_ready(db, tenant_id, project_id)
    _require_control_account(db, tenant_id, project_id, payload.control_account_id)
    current_user = _require_user(db, tenant_id, user_id)
    try:
        source = CostSource(payload.source)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid cost source") from exc
    if source == CostSource.commitment:
        raise HTTPException(status_code=400, detail="Commitments are created from contracts or purchase orders, not from actual cost records")
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be greater than zero")
    record = CostRecord(
        tenant_id=tenant_id,
        project_id=project_id,
        control_account_id=payload.control_account_id,
        source=source,
        amount=payload.amount,
        incurred_on=payload.incurred_on,
        description=payload.description,
    )
    db.add(record)
    db.flush()
    _audit(db, tenant_id, project_id, "capture_actual_cost", "CostRecord", record.id, f'{{"control_account_id":{record.control_account_id},"amount":{record.amount}}}', current_user.full_name)
    db.commit()
    ControlCoreService(db).run_project_cycle(tenant_id, project_id)
    db.refresh(record)
    return record


@router.get("/projects/{project_id}/cost-sheet", response_model=list[CostSheetLineOut])
def get_cost_sheet(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[CostSheetLineOut]:
    _require_project(db, tenant_id, project_id)
    _require_membership(db, tenant_id, project_id, user_id)
    return _cost_sheet_lines(db, tenant_id, project_id)


@router.get("/projects/{project_id}/funding-sources", response_model=list[FundingSourceOut])
def list_funding_sources(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[FundingSource]:
    _require_project(db, tenant_id, project_id)
    _require_membership(db, tenant_id, project_id, user_id)
    return _funding_sources(db, tenant_id, project_id)


@router.post("/projects/{project_id}/funding-sources", response_model=FundingSourceOut)
def create_funding_source(
    project_id: int,
    payload: FundingSourceCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> FundingSource:
    project = _require_project(db, tenant_id, project_id)
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_capture_cost", "Current role cannot manage project funding")
    current_user = _require_user(db, tenant_id, user_id)
    if not payload.code.strip() or not payload.name.strip():
        raise HTTPException(status_code=400, detail="Funding code and name are required")
    if payload.amount < 0:
        raise HTTPException(status_code=400, detail="Funding amount cannot be negative")
    existing = db.scalar(
        select(FundingSource).where(
            FundingSource.tenant_id == tenant_id,
            FundingSource.project_id == project_id,
            FundingSource.code == payload.code.strip(),
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Funding source code already exists for this project")
    funding = FundingSource(
        tenant_id=tenant_id,
        project_id=project_id,
        code=payload.code.strip(),
        name=payload.name.strip(),
        amount=payload.amount,
        currency=(payload.currency or project.currency).upper(),
        status=payload.status.strip() or "approved",
    )
    db.add(funding)
    db.flush()
    _audit(db, tenant_id, project_id, "create_funding_source", "FundingSource", funding.id, f'{{"code":"{funding.code}","amount":{funding.amount}}}', current_user.full_name)
    db.commit()
    db.refresh(funding)
    return funding


@router.patch("/projects/{project_id}/funding-sources/{funding_id}", response_model=FundingSourceOut)
def update_funding_source(
    project_id: int,
    funding_id: int,
    payload: FundingSourceUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> FundingSource:
    _require_project(db, tenant_id, project_id)
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_capture_cost", "Current role cannot manage project funding")
    current_user = _require_user(db, tenant_id, user_id)
    funding = db.scalar(
        select(FundingSource).where(
            FundingSource.tenant_id == tenant_id,
            FundingSource.project_id == project_id,
            FundingSource.id == funding_id,
        )
    )
    if not funding:
        raise HTTPException(status_code=404, detail="Funding source not found")
    _require_current_version(funding, payload.expected_version)
    if payload.amount is not None and payload.amount < 0:
        raise HTTPException(status_code=400, detail="Funding amount cannot be negative")
    for field in ("name", "amount", "currency", "status"):
        value = getattr(payload, field)
        if value is not None:
            setattr(funding, field, value.strip() if isinstance(value, str) else value)
    if funding.currency:
        funding.currency = funding.currency.upper()
    _touch_collaborative_record(funding)
    _audit(db, tenant_id, project_id, "update_funding_source", "FundingSource", funding.id, f'{{"version":{funding.version}}}', current_user.full_name)
    db.commit()
    db.refresh(funding)
    return funding


@router.get("/projects/{project_id}/cash-flow", response_model=list[CashFlowPeriodOut])
def list_cash_flow(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[CashFlowPeriod]:
    _require_project(db, tenant_id, project_id)
    _require_membership(db, tenant_id, project_id, user_id)
    return _cash_flow_periods(db, tenant_id, project_id)


@router.post("/projects/{project_id}/cash-flow", response_model=CashFlowPeriodOut)
def create_cash_flow_period(
    project_id: int,
    payload: CashFlowPeriodCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> CashFlowPeriod:
    _require_project(db, tenant_id, project_id)
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_capture_cost", "Current role cannot manage cash flow")
    current_user = _require_user(db, tenant_id, user_id)
    _validate_cash_flow_values(payload)
    if not payload.period_label.strip():
        raise HTTPException(status_code=400, detail="Cash flow period label is required")
    existing = db.scalar(
        select(CashFlowPeriod).where(
            CashFlowPeriod.tenant_id == tenant_id,
            CashFlowPeriod.project_id == project_id,
            CashFlowPeriod.period_label == payload.period_label.strip(),
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Cash flow period already exists for this project")
    period = CashFlowPeriod(
        tenant_id=tenant_id,
        project_id=project_id,
        period_label=payload.period_label.strip(),
        planned_inflow=payload.planned_inflow,
        planned_outflow=payload.planned_outflow,
        actual_inflow=payload.actual_inflow,
        actual_outflow=payload.actual_outflow,
        forecast_outflow=payload.forecast_outflow,
    )
    db.add(period)
    db.flush()
    _audit(db, tenant_id, project_id, "create_cash_flow_period", "CashFlowPeriod", period.id, f'{{"period_label":"{period.period_label}"}}', current_user.full_name)
    db.commit()
    db.refresh(period)
    return period


@router.patch("/projects/{project_id}/cash-flow/{period_id}", response_model=CashFlowPeriodOut)
def update_cash_flow_period(
    project_id: int,
    period_id: int,
    payload: CashFlowPeriodUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> CashFlowPeriod:
    _require_project(db, tenant_id, project_id)
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_capture_cost", "Current role cannot manage cash flow")
    current_user = _require_user(db, tenant_id, user_id)
    _validate_cash_flow_values(payload)
    period = db.scalar(
        select(CashFlowPeriod).where(
            CashFlowPeriod.tenant_id == tenant_id,
            CashFlowPeriod.project_id == project_id,
            CashFlowPeriod.id == period_id,
        )
    )
    if not period:
        raise HTTPException(status_code=404, detail="Cash flow period not found")
    _require_current_version(period, payload.expected_version)
    for field in ("planned_inflow", "planned_outflow", "actual_inflow", "actual_outflow", "forecast_outflow"):
        value = getattr(payload, field)
        if value is not None:
            setattr(period, field, value)
    _touch_collaborative_record(period)
    _audit(db, tenant_id, project_id, "update_cash_flow_period", "CashFlowPeriod", period.id, f'{{"version":{period.version}}}', current_user.full_name)
    db.commit()
    db.refresh(period)
    return period


@router.get("/projects/{project_id}/cost-manager-summary", response_model=CostManagerSummaryOut)
def get_cost_manager_summary(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> CostManagerSummaryOut:
    _require_project(db, tenant_id, project_id)
    _require_membership(db, tenant_id, project_id, user_id)
    return _cost_manager_summary(db, tenant_id, project_id)


@router.get("/projects/{project_id}/contracts", response_model=list[ContractOut])
def list_contracts(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[Contract]:
    _require_membership(db, tenant_id, project_id, user_id)
    return list(
        db.scalars(
            select(Contract)
            .where(Contract.project_id == project_id, Contract.tenant_id == tenant_id)
            .order_by(Contract.code)
        ).all()
    )


@router.post("/projects/{project_id}/contracts", response_model=ContractOut)
def create_contract(
    project_id: int,
    payload: ContractCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> Contract:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_manage_contract", "Current role cannot create or update contracts")
    current_user = _require_user(db, tenant_id, user_id)
    if payload.control_account_id is not None:
        _require_control_account(db, tenant_id, project_id, payload.control_account_id)
    if payload.value < 0:
        raise HTTPException(status_code=400, detail="Contract value cannot be negative")
    contract_code = payload.code.strip()
    if not contract_code:
        raise HTTPException(status_code=400, detail="Contract code is required")
    existing = db.scalar(select(Contract).where(Contract.tenant_id == tenant_id, Contract.project_id == project_id, Contract.code == contract_code))
    if existing:
        raise HTTPException(status_code=409, detail="Contract code already exists in this project")
    contract = Contract(
        tenant_id=tenant_id,
        project_id=project_id,
        control_account_id=payload.control_account_id,
        code=contract_code,
        title=payload.title.strip(),
        counterparty=payload.counterparty.strip(),
        contract_type=payload.contract_type.strip() or "EPC",
        value=payload.value,
        status=payload.status.strip() or "active",
    )
    db.add(contract)
    db.flush()
    _audit(db, tenant_id, project_id, "create_contract", "Contract", contract.id, f'{{"code":"{contract.code}"}}', current_user.full_name)
    db.commit()
    db.refresh(contract)
    return contract


@router.get("/projects/{project_id}/purchase-orders", response_model=list[PurchaseOrderOut])
def list_purchase_orders(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[PurchaseOrder]:
    _require_membership(db, tenant_id, project_id, user_id)
    return _purchase_orders(db, tenant_id, project_id)


@router.post("/projects/{project_id}/purchase-orders", response_model=PurchaseOrderOut)
def create_purchase_order(
    project_id: int,
    payload: PurchaseOrderCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PurchaseOrder:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_manage_contract", "Current role cannot create purchase orders")
    current_user = _require_user(db, tenant_id, user_id)
    if payload.control_account_id is not None:
        _require_control_account(db, tenant_id, project_id, payload.control_account_id)
    if payload.contract_id is not None:
        _require_contract(db, tenant_id, project_id, payload.contract_id)
    if payload.committed_amount <= 0:
        raise HTTPException(status_code=400, detail="Purchase order committed amount must be greater than zero")
    po_number = payload.po_number.strip()
    if not po_number:
        raise HTTPException(status_code=400, detail="Purchase order number is required")
    existing = db.scalar(
        select(PurchaseOrder).where(
            PurchaseOrder.tenant_id == tenant_id,
            PurchaseOrder.project_id == project_id,
            PurchaseOrder.po_number == po_number,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Purchase order number already exists in this project")
    order = PurchaseOrder(
        tenant_id=tenant_id,
        project_id=project_id,
        control_account_id=payload.control_account_id,
        contract_id=payload.contract_id,
        po_number=po_number,
        description=payload.description.strip(),
        vendor=payload.vendor.strip(),
        committed_amount=payload.committed_amount,
        status=payload.status.strip() or "issued",
        issued_on=payload.issued_on or datetime.utcnow().date(),
    )
    db.add(order)
    db.flush()
    _audit(db, tenant_id, project_id, "create_purchase_order", "PurchaseOrder", order.id, json.dumps({"po_number": order.po_number, "committed_amount": order.committed_amount}), current_user.full_name)
    db.commit()
    db.refresh(order)
    return order


@router.patch("/projects/{project_id}/purchase-orders/{purchase_order_id}", response_model=PurchaseOrderOut)
def update_purchase_order(
    project_id: int,
    purchase_order_id: int,
    payload: PurchaseOrderUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PurchaseOrder:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_manage_contract", "Current role cannot update purchase orders")
    current_user = _require_user(db, tenant_id, user_id)
    order = db.scalar(
        select(PurchaseOrder).where(
            PurchaseOrder.tenant_id == tenant_id,
            PurchaseOrder.project_id == project_id,
            PurchaseOrder.id == purchase_order_id,
        )
    )
    if not order:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    _require_current_version(order, payload.expected_version)
    if payload.control_account_id is not None:
        _require_control_account(db, tenant_id, project_id, payload.control_account_id)
    if payload.contract_id is not None:
        _require_contract(db, tenant_id, project_id, payload.contract_id)
    if payload.committed_amount is not None and payload.committed_amount <= 0:
        raise HTTPException(status_code=400, detail="Purchase order committed amount must be greater than zero")
    for field in ("control_account_id", "contract_id", "description", "vendor", "committed_amount", "status", "issued_on"):
        value = getattr(payload, field)
        if value is not None:
            setattr(order, field, value.strip() if isinstance(value, str) else value)
    _touch_collaborative_record(order)
    _audit(db, tenant_id, project_id, "update_purchase_order", "PurchaseOrder", order.id, json.dumps({"status": order.status, "version": order.version}), current_user.full_name)
    db.commit()
    db.refresh(order)
    return order


@router.get("/projects/{project_id}/payment-certificates", response_model=list[PaymentCertificateOut])
def list_payment_certificates(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[PaymentCertificate]:
    _require_membership(db, tenant_id, project_id, user_id)
    return _payment_certificates(db, tenant_id, project_id)


@router.post("/projects/{project_id}/payment-certificates", response_model=PaymentCertificateOut)
def create_payment_certificate(
    project_id: int,
    payload: PaymentCertificateCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PaymentCertificate:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_contract_or_cost_role(membership, "Current role cannot certify incurred cost")
    current_user = _require_user(db, tenant_id, user_id)
    if payload.control_account_id is not None:
        _require_control_account(db, tenant_id, project_id, payload.control_account_id)
    if payload.contract_id is not None:
        _require_contract(db, tenant_id, project_id, payload.contract_id)
    if payload.purchase_order_id is not None:
        _require_purchase_order(db, tenant_id, project_id, payload.purchase_order_id)
    if payload.certified_amount <= 0:
        raise HTTPException(status_code=400, detail="Certified amount must be greater than zero")
    if payload.retained_amount < 0:
        raise HTTPException(status_code=400, detail="Retained amount cannot be negative")
    certificate_no = payload.certificate_no.strip()
    if not certificate_no:
        raise HTTPException(status_code=400, detail="Payment certificate number is required")
    existing = db.scalar(
        select(PaymentCertificate).where(
            PaymentCertificate.tenant_id == tenant_id,
            PaymentCertificate.project_id == project_id,
            PaymentCertificate.certificate_no == certificate_no,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Payment certificate number already exists in this project")
    certificate = PaymentCertificate(
        tenant_id=tenant_id,
        project_id=project_id,
        control_account_id=payload.control_account_id,
        contract_id=payload.contract_id,
        purchase_order_id=payload.purchase_order_id,
        certificate_no=certificate_no,
        period_label=payload.period_label.strip(),
        certified_amount=payload.certified_amount,
        retained_amount=payload.retained_amount,
        status=payload.status.strip() or "certified",
        certified_on=payload.certified_on or datetime.utcnow().date(),
    )
    db.add(certificate)
    db.flush()
    _audit(db, tenant_id, project_id, "certify_incurred_cost", "PaymentCertificate", certificate.id, json.dumps({"certificate_no": certificate.certificate_no, "certified_amount": certificate.certified_amount}), current_user.full_name)
    db.commit()
    ControlCoreService(db).run_project_cycle(tenant_id, project_id)
    db.refresh(certificate)
    return certificate


@router.patch("/projects/{project_id}/payment-certificates/{certificate_id}", response_model=PaymentCertificateOut)
def update_payment_certificate(
    project_id: int,
    certificate_id: int,
    payload: PaymentCertificateUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PaymentCertificate:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_contract_or_cost_role(membership, "Current role cannot update payment certificates")
    current_user = _require_user(db, tenant_id, user_id)
    certificate = db.scalar(
        select(PaymentCertificate).where(
            PaymentCertificate.tenant_id == tenant_id,
            PaymentCertificate.project_id == project_id,
            PaymentCertificate.id == certificate_id,
        )
    )
    if not certificate:
        raise HTTPException(status_code=404, detail="Payment certificate not found")
    _require_current_version(certificate, payload.expected_version)
    if payload.control_account_id is not None:
        _require_control_account(db, tenant_id, project_id, payload.control_account_id)
    if payload.contract_id is not None:
        _require_contract(db, tenant_id, project_id, payload.contract_id)
    if payload.purchase_order_id is not None:
        _require_purchase_order(db, tenant_id, project_id, payload.purchase_order_id)
    if payload.certified_amount is not None and payload.certified_amount <= 0:
        raise HTTPException(status_code=400, detail="Certified amount must be greater than zero")
    if payload.retained_amount is not None and payload.retained_amount < 0:
        raise HTTPException(status_code=400, detail="Retained amount cannot be negative")
    for field in ("control_account_id", "contract_id", "purchase_order_id", "period_label", "certified_amount", "retained_amount", "status", "certified_on"):
        value = getattr(payload, field)
        if value is not None:
            setattr(certificate, field, value.strip() if isinstance(value, str) else value)
    _touch_collaborative_record(certificate)
    _audit(db, tenant_id, project_id, "update_payment_certificate", "PaymentCertificate", certificate.id, json.dumps({"status": certificate.status, "version": certificate.version}), current_user.full_name)
    db.commit()
    ControlCoreService(db).run_project_cycle(tenant_id, project_id)
    db.refresh(certificate)
    return certificate


@router.get("/projects/{project_id}/warehouse-receipts", response_model=list[WarehouseReceiptOut])
def list_warehouse_receipts(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[WarehouseReceipt]:
    _require_membership(db, tenant_id, project_id, user_id)
    return _warehouse_receipts(db, tenant_id, project_id)


@router.post("/projects/{project_id}/warehouse-receipts", response_model=WarehouseReceiptOut)
def create_warehouse_receipt(
    project_id: int,
    payload: WarehouseReceiptCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> WarehouseReceipt:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_contract_or_cost_role(membership, "Current role cannot register warehouse receipts")
    current_user = _require_user(db, tenant_id, user_id)
    if payload.control_account_id is not None:
        _require_control_account(db, tenant_id, project_id, payload.control_account_id)
    if payload.contract_id is not None:
        _require_contract(db, tenant_id, project_id, payload.contract_id)
    if payload.purchase_order_id is not None:
        _require_purchase_order(db, tenant_id, project_id, payload.purchase_order_id)
    _validate_warehouse_receipt_values(payload.received_quantity, payload.unit_cost, payload.received_value)
    receipt_no = payload.receipt_no.strip()
    if not receipt_no:
        raise HTTPException(status_code=400, detail="Warehouse receipt number is required")
    existing = db.scalar(
        select(WarehouseReceipt).where(
            WarehouseReceipt.tenant_id == tenant_id,
            WarehouseReceipt.project_id == project_id,
            WarehouseReceipt.receipt_no == receipt_no,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Warehouse receipt number already exists in this project")
    received_value = _warehouse_received_value(payload.received_quantity, payload.unit_cost, payload.received_value)
    receipt = WarehouseReceipt(
        tenant_id=tenant_id,
        project_id=project_id,
        control_account_id=payload.control_account_id,
        contract_id=payload.contract_id,
        purchase_order_id=payload.purchase_order_id,
        receipt_no=receipt_no,
        description=payload.description.strip(),
        received_quantity=payload.received_quantity,
        unit_cost=payload.unit_cost,
        received_value=received_value,
        status=payload.status.strip() or "accepted",
        received_on=payload.received_on or datetime.utcnow().date(),
    )
    db.add(receipt)
    db.flush()
    _audit(db, tenant_id, project_id, "register_warehouse_receipt", "WarehouseReceipt", receipt.id, json.dumps({"receipt_no": receipt.receipt_no, "received_value": receipt.received_value}), current_user.full_name)
    db.commit()
    ControlCoreService(db).run_project_cycle(tenant_id, project_id)
    db.refresh(receipt)
    return receipt


@router.patch("/projects/{project_id}/warehouse-receipts/{receipt_id}", response_model=WarehouseReceiptOut)
def update_warehouse_receipt(
    project_id: int,
    receipt_id: int,
    payload: WarehouseReceiptUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> WarehouseReceipt:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_contract_or_cost_role(membership, "Current role cannot update warehouse receipts")
    current_user = _require_user(db, tenant_id, user_id)
    receipt = db.scalar(
        select(WarehouseReceipt).where(
            WarehouseReceipt.tenant_id == tenant_id,
            WarehouseReceipt.project_id == project_id,
            WarehouseReceipt.id == receipt_id,
        )
    )
    if not receipt:
        raise HTTPException(status_code=404, detail="Warehouse receipt not found")
    _require_current_version(receipt, payload.expected_version)
    if payload.control_account_id is not None:
        _require_control_account(db, tenant_id, project_id, payload.control_account_id)
    if payload.contract_id is not None:
        _require_contract(db, tenant_id, project_id, payload.contract_id)
    if payload.purchase_order_id is not None:
        _require_purchase_order(db, tenant_id, project_id, payload.purchase_order_id)
    received_quantity = payload.received_quantity if payload.received_quantity is not None else receipt.received_quantity
    unit_cost = payload.unit_cost if payload.unit_cost is not None else receipt.unit_cost
    received_value = payload.received_value if payload.received_value is not None else receipt.received_value
    _validate_warehouse_receipt_values(received_quantity, unit_cost, received_value)
    for field in ("control_account_id", "contract_id", "purchase_order_id", "description", "received_quantity", "unit_cost", "status", "received_on"):
        value = getattr(payload, field)
        if value is not None:
            setattr(receipt, field, value.strip() if isinstance(value, str) else value)
    if payload.received_value is not None or payload.received_quantity is not None or payload.unit_cost is not None:
        receipt.received_value = _warehouse_received_value(receipt.received_quantity, receipt.unit_cost, payload.received_value if payload.received_value is not None else 0)
    _touch_collaborative_record(receipt)
    _audit(db, tenant_id, project_id, "update_warehouse_receipt", "WarehouseReceipt", receipt.id, json.dumps({"status": receipt.status, "version": receipt.version}), current_user.full_name)
    db.commit()
    ControlCoreService(db).run_project_cycle(tenant_id, project_id)
    db.refresh(receipt)
    return receipt


@router.get("/projects/{project_id}/rfq-packages", response_model=list[RFQPackageOut])
def list_rfq_packages(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[RFQPackage]:
    _require_membership(db, tenant_id, project_id, user_id)
    return _rfq_packages(db, tenant_id, project_id)


@router.post("/projects/{project_id}/rfq-packages", response_model=RFQPackageOut)
def create_rfq_package(
    project_id: int,
    payload: RFQPackageCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> RFQPackage:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_manage_contract", "Current role cannot create RFQ packages")
    current_user = _require_user(db, tenant_id, user_id)
    if payload.control_account_id is not None:
        _require_control_account(db, tenant_id, project_id, payload.control_account_id)
    if payload.budget_amount < 0:
        raise HTTPException(status_code=400, detail="RFQ budget cannot be negative")
    package_no = payload.package_no.strip()
    if not package_no:
        raise HTTPException(status_code=400, detail="RFQ package number is required")
    existing = db.scalar(
        select(RFQPackage).where(
            RFQPackage.tenant_id == tenant_id,
            RFQPackage.project_id == project_id,
            RFQPackage.package_no == package_no,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="RFQ package number already exists in this project")
    package = RFQPackage(
        tenant_id=tenant_id,
        project_id=project_id,
        control_account_id=payload.control_account_id,
        package_no=package_no,
        title=payload.title.strip(),
        scope_summary=payload.scope_summary.strip(),
        procurement_method=payload.procurement_method.strip() or "RFQ",
        status=payload.status.strip() or "draft",
        budget_amount=payload.budget_amount,
        issue_date=payload.issue_date,
        due_date=payload.due_date,
    )
    db.add(package)
    db.flush()
    _audit(db, tenant_id, project_id, "create_rfq_package", "RFQPackage", package.id, json.dumps({"package_no": package.package_no, "budget_amount": package.budget_amount}), current_user.full_name)
    db.commit()
    db.refresh(package)
    return package


@router.patch("/projects/{project_id}/rfq-packages/{rfq_package_id}", response_model=RFQPackageOut)
def update_rfq_package(
    project_id: int,
    rfq_package_id: int,
    payload: RFQPackageUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> RFQPackage:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_manage_contract", "Current role cannot update RFQ packages")
    current_user = _require_user(db, tenant_id, user_id)
    package = _require_rfq_package(db, tenant_id, project_id, rfq_package_id)
    _require_current_version(package, payload.expected_version)
    if payload.control_account_id is not None:
        _require_control_account(db, tenant_id, project_id, payload.control_account_id)
    if payload.budget_amount is not None and payload.budget_amount < 0:
        raise HTTPException(status_code=400, detail="RFQ budget cannot be negative")
    for field in ("control_account_id", "title", "scope_summary", "procurement_method", "status", "budget_amount", "issue_date", "due_date"):
        value = getattr(payload, field)
        if value is not None:
            setattr(package, field, value.strip() if isinstance(value, str) else value)
    _touch_collaborative_record(package)
    _audit(db, tenant_id, project_id, "update_rfq_package", "RFQPackage", package.id, json.dumps({"status": package.status, "version": package.version}), current_user.full_name)
    db.commit()
    db.refresh(package)
    return package


@router.get("/projects/{project_id}/rfq-packages/{rfq_package_id}/bids", response_model=list[RFQBidOut])
def list_rfq_bids(
    project_id: int,
    rfq_package_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[RFQBid]:
    _require_membership(db, tenant_id, project_id, user_id)
    _require_rfq_package(db, tenant_id, project_id, rfq_package_id)
    return _rfq_bids(db, tenant_id, project_id, rfq_package_id)


@router.post("/projects/{project_id}/rfq-packages/{rfq_package_id}/bids", response_model=RFQBidOut)
def create_rfq_bid(
    project_id: int,
    rfq_package_id: int,
    payload: RFQBidCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> RFQBid:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_manage_contract", "Current role cannot create RFQ bids")
    current_user = _require_user(db, tenant_id, user_id)
    _require_rfq_package(db, tenant_id, project_id, rfq_package_id)
    _validate_rfq_bid_values(payload.bid_amount, payload.technical_score, payload.commercial_score, payload.schedule_score, payload.risk_score)
    bidder_name = payload.bidder_name.strip()
    if not bidder_name:
        raise HTTPException(status_code=400, detail="Bidder name is required")
    existing = db.scalar(
        select(RFQBid).where(
            RFQBid.tenant_id == tenant_id,
            RFQBid.project_id == project_id,
            RFQBid.rfq_package_id == rfq_package_id,
            RFQBid.bidder_name == bidder_name,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Bidder already exists for this RFQ package")
    bid = RFQBid(
        tenant_id=tenant_id,
        project_id=project_id,
        rfq_package_id=rfq_package_id,
        bidder_name=bidder_name,
        bid_amount=payload.bid_amount,
        technical_score=payload.technical_score,
        commercial_score=payload.commercial_score,
        schedule_score=payload.schedule_score,
        risk_score=payload.risk_score,
        weighted_score=_rfq_weighted_score(payload.technical_score, payload.commercial_score, payload.schedule_score, payload.risk_score),
        status=payload.status.strip() or "received",
        submitted_on=payload.submitted_on or datetime.utcnow().date(),
        notes=payload.notes.strip(),
    )
    db.add(bid)
    db.flush()
    _audit(db, tenant_id, project_id, "create_rfq_bid", "RFQBid", bid.id, json.dumps({"bidder_name": bid.bidder_name, "weighted_score": bid.weighted_score}), current_user.full_name)
    db.commit()
    db.refresh(bid)
    return bid


@router.patch("/projects/{project_id}/rfq-bids/{bid_id}", response_model=RFQBidOut)
def update_rfq_bid(
    project_id: int,
    bid_id: int,
    payload: RFQBidUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> RFQBid:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_manage_contract", "Current role cannot update RFQ bids")
    current_user = _require_user(db, tenant_id, user_id)
    bid = db.scalar(
        select(RFQBid).where(
            RFQBid.tenant_id == tenant_id,
            RFQBid.project_id == project_id,
            RFQBid.id == bid_id,
        )
    )
    if not bid:
        raise HTTPException(status_code=404, detail="RFQ bid not found")
    _require_current_version(bid, payload.expected_version)
    bid_amount = payload.bid_amount if payload.bid_amount is not None else bid.bid_amount
    technical_score = payload.technical_score if payload.technical_score is not None else bid.technical_score
    commercial_score = payload.commercial_score if payload.commercial_score is not None else bid.commercial_score
    schedule_score = payload.schedule_score if payload.schedule_score is not None else bid.schedule_score
    risk_score = payload.risk_score if payload.risk_score is not None else bid.risk_score
    _validate_rfq_bid_values(bid_amount, technical_score, commercial_score, schedule_score, risk_score)
    for field in ("bidder_name", "bid_amount", "technical_score", "commercial_score", "schedule_score", "risk_score", "status", "submitted_on", "notes"):
        value = getattr(payload, field)
        if value is not None:
            setattr(bid, field, value.strip() if isinstance(value, str) else value)
    bid.weighted_score = _rfq_weighted_score(bid.technical_score, bid.commercial_score, bid.schedule_score, bid.risk_score)
    _touch_collaborative_record(bid)
    _audit(db, tenant_id, project_id, "update_rfq_bid", "RFQBid", bid.id, json.dumps({"status": bid.status, "weighted_score": bid.weighted_score}), current_user.full_name)
    db.commit()
    db.refresh(bid)
    return bid


@router.get("/projects/{project_id}/communications", response_model=list[ContractCommunicationOut])
def list_contract_communications(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ContractCommunication]:
    _require_membership(db, tenant_id, project_id, user_id)
    return list(
        db.scalars(
            select(ContractCommunication)
            .where(ContractCommunication.project_id == project_id, ContractCommunication.tenant_id == tenant_id)
            .order_by(ContractCommunication.sent_on.desc(), ContractCommunication.id.desc())
        ).all()
    )


@router.post("/projects/{project_id}/communications", response_model=ContractCommunicationOut)
def create_contract_communication(
    project_id: int,
    payload: ContractCommunicationCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ContractCommunication:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_manage_contract", "Current role cannot issue contractual communications")
    current_user = _require_user(db, tenant_id, user_id)
    if payload.contract_id is not None:
        contract = db.scalar(select(Contract).where(Contract.id == payload.contract_id, Contract.tenant_id == tenant_id, Contract.project_id == project_id))
        if not contract:
            raise HTTPException(status_code=404, detail="Contract not found")
    communication = ContractCommunication(
        tenant_id=tenant_id,
        project_id=project_id,
        contract_id=payload.contract_id,
        communication_type=payload.communication_type,
        subject=payload.subject,
        reference=payload.reference,
        sent_on=payload.sent_on,
        status=payload.status,
    )
    db.add(communication)
    db.flush()
    _audit(db, tenant_id, project_id, "create_contract_communication", "ContractCommunication", communication.id, f'{{"subject":"{communication.subject}"}}', current_user.full_name)
    db.commit()
    db.refresh(communication)
    return communication


@router.get("/projects/{project_id}/contract-notices", response_model=list[ContractNoticeOut])
def list_contract_notices(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ContractNotice]:
    _require_membership(db, tenant_id, project_id, user_id)
    return list(
        db.scalars(
            select(ContractNotice)
            .where(ContractNotice.project_id == project_id, ContractNotice.tenant_id == tenant_id)
            .order_by(ContractNotice.notice_date.desc(), ContractNotice.id.desc())
        ).all()
    )


@router.post("/projects/{project_id}/contract-notices", response_model=ContractNoticeOut)
def create_contract_notice(
    project_id: int,
    payload: ContractNoticeCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ContractNotice:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_manage_contract", "Current role cannot issue contractual notices")
    current_user = _require_user(db, tenant_id, user_id)
    if payload.contract_id is not None:
        contract = db.scalar(select(Contract).where(Contract.id == payload.contract_id, Contract.tenant_id == tenant_id, Contract.project_id == project_id))
        if not contract:
            raise HTTPException(status_code=404, detail="Contract not found")
    if payload.claim_id is not None:
        _require_claim(db, tenant_id, project_id, payload.claim_id)
    if payload.change_request_id is not None:
        change = db.scalar(
            select(ChangeRequest).where(
                ChangeRequest.id == payload.change_request_id,
                ChangeRequest.tenant_id == tenant_id,
                ChangeRequest.project_id == project_id,
            )
        )
        if not change:
            raise HTTPException(status_code=404, detail="Change request not found")

    days_late = 0
    compliance_status = "pending"
    if payload.notice_date and payload.due_date:
        days_late = max((payload.notice_date - payload.due_date).days, 0)
        compliance_status = "late" if days_late else "compliant"
    notice = ContractNotice(
        tenant_id=tenant_id,
        project_id=project_id,
        contract_id=payload.contract_id,
        claim_id=payload.claim_id,
        change_request_id=payload.change_request_id,
        notice_type=payload.notice_type,
        subject=payload.subject,
        reference=payload.reference,
        event_date=payload.event_date,
        notice_date=payload.notice_date,
        due_date=payload.due_date,
        status=payload.status,
        days_late=days_late,
        compliance_status=compliance_status,
    )
    db.add(notice)
    db.flush()
    _audit(
        db,
        tenant_id,
        project_id,
        "create_contract_notice",
        "ContractNotice",
        notice.id,
        json.dumps({"subject": notice.subject, "compliance_status": notice.compliance_status}),
        current_user.full_name,
    )
    db.commit()
    db.refresh(notice)
    return notice


@router.post("/projects/{project_id}/changes", response_model=ChangeRequestOut)
def create_change_request(
    project_id: int,
    payload: ChangeRequestCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ChangeRequest:
    _require_membership(db, tenant_id, project_id, user_id)
    current_user = _require_user(db, tenant_id, user_id)
    if payload.control_account_id is not None:
        _require_control_account(db, tenant_id, project_id, payload.control_account_id)
    change = ChangeRequest(
        tenant_id=tenant_id,
        project_id=project_id,
        control_account_id=payload.control_account_id,
        title=payload.title,
        deviation=payload.deviation,
        cost_impact=payload.cost_impact,
        schedule_impact_days=payload.schedule_impact_days,
    )
    db.add(change)
    db.flush()
    _start_business_process(
        db,
        tenant_id,
        project_id,
        trigger_entity_type="ChangeRequest",
        trigger_entity_id=change.id,
        process_code="CR-CONTROL",
        process_name="Change Request",
        record_no=f"CR-{change.id:05d}",
        title=f"Change Request - {change.title}",
        current_step="Impact Review",
        ball_in_court="Project Controls",
        steps=[
            ("Initiation", "Deviation captured with cost, schedule and contractual context.", "Originator", "Complete", "complete"),
            ("Impact Review", "Evaluate cost, schedule, progress and risk exposure.", "Project Controls", "Active", "active"),
            ("Contract Review", "Confirm notice, entitlement and contract position.", "Contract Manager", "Pending", "pending"),
            ("Approval", "Control Manager decision on disposition.", "Control Manager", "Queued", "queued"),
            ("Implementation", "Approved disposition updates forecast, budget and action log.", "Execution Lead", "Queued", "queued"),
        ],
    )
    _audit(db, tenant_id, project_id, "create_change_request", "ChangeRequest", change.id, f'{{"title":"{change.title}"}}', current_user.full_name)
    db.commit()
    db.refresh(change)
    return change


@router.get("/projects/{project_id}/claim-entitlement-items", response_model=list[ClaimEntitlementItemOut])
def list_claim_entitlement_items(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ClaimEntitlementItem]:
    _require_membership(db, tenant_id, project_id, user_id)
    return list(
        db.scalars(
            select(ClaimEntitlementItem)
            .where(ClaimEntitlementItem.tenant_id == tenant_id, ClaimEntitlementItem.project_id == project_id)
            .order_by(ClaimEntitlementItem.claim_id, ClaimEntitlementItem.sequence_no, ClaimEntitlementItem.id)
        ).all()
    )


@router.post("/projects/{project_id}/claims/{claim_id}/entitlement-items", response_model=ClaimEntitlementItemOut)
def create_claim_entitlement_item(
    project_id: int,
    claim_id: int,
    payload: ClaimEntitlementItemCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ClaimEntitlementItem:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    if membership.role not in {"Control Manager", "Contract Manager", "Claims Analyst", "Project Controls"}:
        raise HTTPException(status_code=403, detail="Current role cannot update claim entitlement analysis")
    current_user = _require_user(db, tenant_id, user_id)
    claim = _require_claim(db, tenant_id, project_id, claim_id)
    item = ClaimEntitlementItem(
        tenant_id=tenant_id,
        project_id=project_id,
        claim_id=claim.id,
        practice_source=payload.practice_source,
        category=payload.category,
        element=payload.element,
        requirement=payload.requirement,
        assessment=payload.assessment,
        evidence_ref=payload.evidence_ref,
        status=payload.status,
        weight=payload.weight,
        score=payload.score,
        sequence_no=payload.sequence_no,
    )
    db.add(item)
    db.flush()
    _audit(db, tenant_id, project_id, "create_claim_entitlement_item", "ClaimEntitlementItem", item.id, f'{{"claim_id":{claim.id},"element":"{item.element}"}}', current_user.full_name)
    db.commit()
    db.refresh(item)
    return item


@router.patch("/projects/{project_id}/claims/{claim_id}/entitlement-items/{item_id}", response_model=ClaimEntitlementItemOut)
def update_claim_entitlement_item(
    project_id: int,
    claim_id: int,
    item_id: int,
    payload: ClaimEntitlementItemUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ClaimEntitlementItem:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    if membership.role not in {"Control Manager", "Contract Manager", "Claims Analyst", "Project Controls"}:
        raise HTTPException(status_code=403, detail="Current role cannot update claim entitlement analysis")
    current_user = _require_user(db, tenant_id, user_id)
    claim = _require_claim(db, tenant_id, project_id, claim_id)
    item = db.scalar(
        select(ClaimEntitlementItem).where(
            ClaimEntitlementItem.tenant_id == tenant_id,
            ClaimEntitlementItem.project_id == project_id,
            ClaimEntitlementItem.claim_id == claim.id,
            ClaimEntitlementItem.id == item_id,
        )
    )
    if not item:
        raise HTTPException(status_code=404, detail="Claim entitlement item not found")
    _require_current_version(item, payload.expected_version)
    for field, value in payload.model_dump(exclude_unset=True, exclude={"expected_version"}).items():
        setattr(item, field, value)
    _touch_collaborative_record(item)
    _audit(db, tenant_id, project_id, "update_claim_entitlement_item", "ClaimEntitlementItem", item.id, f'{{"status":"{item.status}"}}', current_user.full_name)
    db.commit()
    db.refresh(item)
    return item


@router.get("/projects/{project_id}/claim-impact-analyses", response_model=list[ClaimImpactAnalysisOut])
def list_claim_impact_analyses(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ClaimImpactAnalysis]:
    _require_membership(db, tenant_id, project_id, user_id)
    return list(
        db.scalars(
            select(ClaimImpactAnalysis)
            .where(ClaimImpactAnalysis.tenant_id == tenant_id, ClaimImpactAnalysis.project_id == project_id)
            .order_by(ClaimImpactAnalysis.claim_id, ClaimImpactAnalysis.id)
        ).all()
    )


@router.post("/projects/{project_id}/claims/{claim_id}/impact-analyses", response_model=ClaimImpactAnalysisOut)
def create_claim_impact_analysis(
    project_id: int,
    claim_id: int,
    payload: ClaimImpactAnalysisCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ClaimImpactAnalysis:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    if membership.role not in {"Control Manager", "Contract Manager", "Claims Analyst", "Project Controls"}:
        raise HTTPException(status_code=403, detail="Current role cannot update claim impact analysis")
    current_user = _require_user(db, tenant_id, user_id)
    claim = _require_claim(db, tenant_id, project_id, claim_id)
    analysis = ClaimImpactAnalysis(
        tenant_id=tenant_id,
        project_id=project_id,
        claim_id=claim.id,
        method=payload.method,
        impacted_activity=payload.impacted_activity,
        cause=payload.cause,
        effect=payload.effect,
        schedule_impact_days=payload.schedule_impact_days,
        cost_impact=payload.cost_impact,
        productivity_loss_percent=payload.productivity_loss_percent,
        evidence_ref=payload.evidence_ref,
        confidence_score=payload.confidence_score,
        status=payload.status,
    )
    db.add(analysis)
    db.flush()
    _audit(
        db,
        tenant_id,
        project_id,
        "create_claim_impact_analysis",
        "ClaimImpactAnalysis",
        analysis.id,
        json.dumps({"claim_id": claim.id, "method": analysis.method, "cost_impact": analysis.cost_impact}),
        current_user.full_name,
    )
    db.commit()
    db.refresh(analysis)
    return analysis


@router.patch("/projects/{project_id}/claims/{claim_id}/impact-analyses/{analysis_id}", response_model=ClaimImpactAnalysisOut)
def update_claim_impact_analysis(
    project_id: int,
    claim_id: int,
    analysis_id: int,
    payload: ClaimImpactAnalysisUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ClaimImpactAnalysis:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    if membership.role not in {"Control Manager", "Contract Manager", "Claims Analyst", "Project Controls"}:
        raise HTTPException(status_code=403, detail="Current role cannot update claim impact analysis")
    current_user = _require_user(db, tenant_id, user_id)
    claim = _require_claim(db, tenant_id, project_id, claim_id)
    analysis = db.scalar(
        select(ClaimImpactAnalysis).where(
            ClaimImpactAnalysis.tenant_id == tenant_id,
            ClaimImpactAnalysis.project_id == project_id,
            ClaimImpactAnalysis.claim_id == claim.id,
            ClaimImpactAnalysis.id == analysis_id,
        )
    )
    if not analysis:
        raise HTTPException(status_code=404, detail="Claim impact analysis not found")
    _require_current_version(analysis, payload.expected_version)
    for field, value in payload.model_dump(exclude_unset=True, exclude={"expected_version"}).items():
        setattr(analysis, field, value)
    _touch_collaborative_record(analysis)
    _audit(
        db,
        tenant_id,
        project_id,
        "update_claim_impact_analysis",
        "ClaimImpactAnalysis",
        analysis.id,
        json.dumps({"status": analysis.status, "confidence_score": analysis.confidence_score}),
        current_user.full_name,
    )
    db.commit()
    db.refresh(analysis)
    return analysis


@router.get("/projects/{project_id}/documents", response_model=list[DocumentOut])
def list_documents(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[Document]:
    _require_membership(db, tenant_id, project_id, user_id)
    return _documents(db, tenant_id, project_id)


@router.post("/projects/{project_id}/documents", response_model=DocumentOut)
def create_document(
    project_id: int,
    payload: DocumentCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> Document:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_document_control_role(membership)
    project = _require_project(db, tenant_id, project_id)
    current_user = _require_user(db, tenant_id, user_id)
    document_number = payload.document_number.strip() or _next_document_number(db, tenant_id, project)
    revision = payload.revision.strip() or "A"
    _ensure_document_revision_available(db, tenant_id, project_id, document_number, revision)
    document = Document(
        tenant_id=tenant_id,
        project_id=project_id,
        document_number=document_number,
        revision=revision,
        revision_date=payload.revision_date,
        linked_entity_type=payload.linked_entity_type,
        linked_entity_id=payload.linked_entity_id,
        title=payload.title,
        doc_type=payload.doc_type,
        discipline=payload.discipline,
        organization=payload.organization,
        status=payload.status,
        review_status=payload.review_status,
        confidentiality=payload.confidentiality,
        file_name=payload.file_name,
        uri=payload.uri,
    )
    db.add(document)
    db.flush()
    _audit(
        db,
        tenant_id,
        project_id,
        "register_document",
        "Document",
        document.id,
        json.dumps({"document_number": document.document_number, "revision": document.revision, "title": document.title}),
        current_user.full_name,
    )
    db.commit()
    db.refresh(document)
    return document


@router.patch("/projects/{project_id}/documents/{document_id}", response_model=DocumentOut)
def update_document(
    project_id: int,
    document_id: int,
    payload: DocumentUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> Document:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_document_control_role(membership)
    current_user = _require_user(db, tenant_id, user_id)
    document = _require_document(db, tenant_id, project_id, document_id)
    _require_current_version(document, payload.expected_version)
    next_document_number = payload.document_number.strip() if payload.document_number is not None else document.document_number
    next_revision = payload.revision.strip() if payload.revision is not None else document.revision
    if next_document_number != document.document_number or next_revision != document.revision:
        _ensure_document_revision_available(db, tenant_id, project_id, next_document_number, next_revision, exclude_id=document.id)
    for field, value in payload.model_dump(exclude_unset=True, exclude={"expected_version"}).items():
        if isinstance(value, str):
            value = value.strip()
        setattr(document, field, value)
    if not document.document_number:
        document.document_number = _next_document_number(db, tenant_id, _require_project(db, tenant_id, project_id))
    if not document.revision:
        document.revision = "A"
    _touch_collaborative_record(document)
    _audit(
        db,
        tenant_id,
        project_id,
        "update_document",
        "Document",
        document.id,
        json.dumps({"document_number": document.document_number, "revision": document.revision, "status": document.status}),
        current_user.full_name,
    )
    db.commit()
    db.refresh(document)
    return document


@router.get("/projects/{project_id}/document-transmittals", response_model=list[DocumentTransmittalOut])
def list_document_transmittals(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[DocumentTransmittal]:
    _require_membership(db, tenant_id, project_id, user_id)
    return _document_transmittals(db, tenant_id, project_id)


@router.post("/projects/{project_id}/document-transmittals", response_model=DocumentTransmittalOut)
def create_document_transmittal(
    project_id: int,
    payload: DocumentTransmittalCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> DocumentTransmittal:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_document_control_role(membership)
    project = _require_project(db, tenant_id, project_id)
    current_user = _require_user(db, tenant_id, user_id)
    if not payload.document_ids:
        raise HTTPException(status_code=400, detail="At least one document is required for a transmittal")
    transmittal_no = payload.transmittal_no.strip() or _next_transmittal_no(db, tenant_id, project)
    existing = db.scalar(
        select(DocumentTransmittal).where(
            DocumentTransmittal.tenant_id == tenant_id,
            DocumentTransmittal.project_id == project_id,
            DocumentTransmittal.transmittal_no == transmittal_no,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Transmittal number already exists for this project")
    documents = [_require_document(db, tenant_id, project_id, document_id) for document_id in payload.document_ids]
    transmittal = DocumentTransmittal(
        tenant_id=tenant_id,
        project_id=project_id,
        transmittal_no=transmittal_no,
        subject=payload.subject,
        purpose=payload.purpose,
        recipient_org=payload.recipient_org,
        recipient_contact=payload.recipient_contact,
        status=payload.status,
        sent_on=payload.sent_on or datetime.utcnow().date(),
        due_date=payload.due_date,
        created_by=current_user.full_name,
    )
    db.add(transmittal)
    db.flush()
    for document in documents:
        db.add(
            DocumentTransmittalItem(
                tenant_id=tenant_id,
                project_id=project_id,
                transmittal_id=transmittal.id,
                document_id=document.id,
                document_number=document.document_number,
                revision=document.revision,
                action_required=payload.action_required,
                response_status="outstanding" if payload.purpose in {"for_review", "for_approval"} else "issued",
            )
        )
    _audit(
        db,
        tenant_id,
        project_id,
        "issue_document_transmittal",
        "DocumentTransmittal",
        transmittal.id,
        json.dumps({"transmittal_no": transmittal.transmittal_no, "documents": [document.id for document in documents]}),
        current_user.full_name,
    )
    db.commit()
    db.refresh(transmittal)
    return transmittal


@router.get("/projects/{project_id}/document-transmittal-items", response_model=list[DocumentTransmittalItemOut])
def list_document_transmittal_items(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[DocumentTransmittalItem]:
    _require_membership(db, tenant_id, project_id, user_id)
    return _document_transmittal_items(db, tenant_id, project_id)


@router.get("/projects/{project_id}/document-reviews", response_model=list[DocumentReviewOut])
def list_document_reviews(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[DocumentReview]:
    _require_membership(db, tenant_id, project_id, user_id)
    return _document_reviews(db, tenant_id, project_id)


@router.post("/projects/{project_id}/documents/{document_id}/reviews", response_model=DocumentReviewOut)
def create_document_review(
    project_id: int,
    document_id: int,
    payload: DocumentReviewCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> DocumentReview:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_document_control_role(membership)
    current_user = _require_user(db, tenant_id, user_id)
    document = _require_document(db, tenant_id, project_id, document_id)
    review = DocumentReview(
        tenant_id=tenant_id,
        project_id=project_id,
        document_id=document.id,
        reviewer_role=payload.reviewer_role,
        review_status=payload.review_status,
        comments=payload.comments,
        due_date=payload.due_date,
    )
    document.review_status = payload.review_status
    _touch_collaborative_record(document)
    db.add(review)
    db.flush()
    _audit(db, tenant_id, project_id, "create_document_review", "DocumentReview", review.id, json.dumps({"document_id": document.id, "reviewer_role": review.reviewer_role}), current_user.full_name)
    db.commit()
    db.refresh(review)
    return review


@router.patch("/projects/{project_id}/document-reviews/{review_id}", response_model=DocumentReviewOut)
def update_document_review(
    project_id: int,
    review_id: int,
    payload: DocumentReviewUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> DocumentReview:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_document_control_role(membership)
    current_user = _require_user(db, tenant_id, user_id)
    review = db.scalar(
        select(DocumentReview).where(
            DocumentReview.tenant_id == tenant_id,
            DocumentReview.project_id == project_id,
            DocumentReview.id == review_id,
        )
    )
    if not review:
        raise HTTPException(status_code=404, detail="Document review not found")
    _require_current_version(review, payload.expected_version)
    for field, value in payload.model_dump(exclude_unset=True, exclude={"expected_version"}).items():
        setattr(review, field, value.strip() if isinstance(value, str) else value)
    _touch_collaborative_record(review)
    document = _require_document(db, tenant_id, project_id, review.document_id)
    document.review_status = review.review_status
    _touch_collaborative_record(document)
    _audit(db, tenant_id, project_id, "update_document_review", "DocumentReview", review.id, json.dumps({"review_status": review.review_status}), current_user.full_name)
    db.commit()
    db.refresh(review)
    return review


@router.get("/projects/{project_id}/project-mail", response_model=list[ProjectMailOut])
def list_project_mail(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ProjectMail]:
    _require_membership(db, tenant_id, project_id, user_id)
    return _project_mail(db, tenant_id, project_id)


@router.post("/projects/{project_id}/project-mail", response_model=ProjectMailOut)
def create_project_mail(
    project_id: int,
    payload: ProjectMailCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectMail:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_document_control_role(membership)
    project = _require_project(db, tenant_id, project_id)
    current_user = _require_user(db, tenant_id, user_id)
    if payload.document_id is not None:
        _require_document(db, tenant_id, project_id, payload.document_id)
    mail_no = payload.mail_no.strip() or _next_mail_no(db, tenant_id, project)
    existing = db.scalar(
        select(ProjectMail).where(
            ProjectMail.tenant_id == tenant_id,
            ProjectMail.project_id == project_id,
            ProjectMail.mail_no == mail_no,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Mail number already exists for this project")
    mail = ProjectMail(
        tenant_id=tenant_id,
        project_id=project_id,
        mail_no=mail_no,
        mail_type=payload.mail_type,
        subject=payload.subject,
        from_role=payload.from_role or membership.role,
        to_role=payload.to_role,
        status=payload.status,
        response_required=payload.response_required,
        sent_on=payload.sent_on or datetime.utcnow().date(),
        due_date=payload.due_date,
        body=payload.body,
        linked_entity_type=payload.linked_entity_type,
        linked_entity_id=payload.linked_entity_id,
        document_id=payload.document_id,
    )
    db.add(mail)
    db.flush()
    _audit(db, tenant_id, project_id, "send_project_mail", "ProjectMail", mail.id, json.dumps({"mail_no": mail.mail_no, "mail_type": mail.mail_type}), current_user.full_name)
    db.commit()
    db.refresh(mail)
    return mail


@router.patch("/projects/{project_id}/project-mail/{mail_id}", response_model=ProjectMailOut)
def update_project_mail(
    project_id: int,
    mail_id: int,
    payload: ProjectMailUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectMail:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_document_control_role(membership)
    current_user = _require_user(db, tenant_id, user_id)
    mail = db.scalar(
        select(ProjectMail).where(
            ProjectMail.tenant_id == tenant_id,
            ProjectMail.project_id == project_id,
            ProjectMail.id == mail_id,
        )
    )
    if not mail:
        raise HTTPException(status_code=404, detail="Project mail not found")
    _require_current_version(mail, payload.expected_version)
    for field, value in payload.model_dump(exclude_unset=True, exclude={"expected_version"}).items():
        setattr(mail, field, value.strip() if isinstance(value, str) else value)
    _touch_collaborative_record(mail)
    _audit(db, tenant_id, project_id, "update_project_mail", "ProjectMail", mail.id, json.dumps({"status": mail.status}), current_user.full_name)
    db.commit()
    db.refresh(mail)
    return mail


@router.get("/projects/{project_id}/work-packages", response_model=list[WorkPackageOut])
def list_work_packages(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[WorkPackage]:
    _require_membership(db, tenant_id, project_id, user_id)
    return list(
        db.scalars(
            select(WorkPackage)
            .where(WorkPackage.tenant_id == tenant_id, WorkPackage.project_id == project_id)
            .order_by(WorkPackage.sequence_no, WorkPackage.code)
        ).all()
    )


@router.post("/projects/{project_id}/work-packages", response_model=WorkPackageOut)
def create_work_package(
    project_id: int,
    payload: WorkPackageCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> WorkPackage:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    if membership.role not in {"Control Manager", "Planner", "Project Controls", "Field Engineer", "Workface Planner"}:
        raise HTTPException(status_code=403, detail="Current role cannot configure AWP work packages")
    _require_control_ready(db, tenant_id, project_id)
    current_user = _require_user(db, tenant_id, user_id)
    package_type = payload.package_type.upper()
    if package_type not in {"CWA", "EWA", "EWP", "CWP", "PWP", "IWP"}:
        raise HTTPException(status_code=400, detail="Unsupported AWP package type")
    if payload.control_account_id is not None:
        _require_control_account(db, tenant_id, project_id, payload.control_account_id)
    if payload.parent_id is not None:
        _require_work_package(db, tenant_id, project_id, payload.parent_id)
    existing = db.scalar(
        select(WorkPackage).where(
            WorkPackage.tenant_id == tenant_id,
            WorkPackage.project_id == project_id,
            WorkPackage.code == payload.code,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Work package code already exists in this project")
    package = WorkPackage(
        tenant_id=tenant_id,
        project_id=project_id,
        control_account_id=payload.control_account_id,
        parent_id=payload.parent_id,
        package_type=package_type,
        code=payload.code,
        title=payload.title,
        discipline=payload.discipline,
        sequence_no=payload.sequence_no,
        path_of_construction=payload.path_of_construction,
        owner_role=payload.owner_role,
        readiness_status=payload.readiness_status,
        planned_start=payload.planned_start,
        planned_finish=payload.planned_finish,
        progress_percent=payload.progress_percent,
    )
    db.add(package)
    db.flush()
    _start_business_process(
        db,
        tenant_id,
        project_id,
        trigger_entity_type="WorkPackage",
        trigger_entity_id=package.id,
        process_code="AWP-READY",
        process_name="AWP Readiness",
        record_no=f"AWP-{package.id:05d}",
        title=f"AWP Readiness - {package.code}",
        current_step="Constraint Review",
        ball_in_court=package.owner_role,
        steps=[
            ("Path Definition", "Path of construction, area and sequence are defined from the approved schedule.", "Planner", "Complete", "complete"),
            ("Package Scope", "CWP/EWP/PWP/IWP scope is tied to control account and deliverables.", "Workface Planner", "Complete", "complete"),
            ("Constraint Review", "Engineering, materials, access, permit, safety and document constraints are checked.", package.owner_role, "Active", "active"),
            ("Release", "Ready package can be released to field execution.", "Construction Manager", "Queued", "queued"),
            ("Execute", "Progress capture feeds Control Core and package status.", "Field Engineer", "Queued", "queued"),
        ],
    )
    _audit(db, tenant_id, project_id, "create_awp_work_package", "WorkPackage", package.id, f'{{"code":"{package.code}","type":"{package.package_type}"}}', current_user.full_name)
    db.commit()
    db.refresh(package)
    return package


@router.patch("/projects/{project_id}/work-packages/{package_id}", response_model=WorkPackageOut)
def update_work_package_readiness(
    project_id: int,
    package_id: int,
    payload: WorkPackageReadinessUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> WorkPackage:
    _require_membership(db, tenant_id, project_id, user_id)
    current_user = _require_user(db, tenant_id, user_id)
    package = _require_work_package(db, tenant_id, project_id, package_id)
    _require_current_version(package, payload.expected_version)
    if payload.readiness_status is not None:
        package.readiness_status = payload.readiness_status
    if payload.progress_percent is not None:
        if payload.progress_percent < 0 or payload.progress_percent > 100:
            raise HTTPException(status_code=400, detail="Progress percent must be between 0 and 100")
        package.progress_percent = payload.progress_percent
    _touch_collaborative_record(package)
    _audit(db, tenant_id, project_id, "update_awp_readiness", "WorkPackage", package.id, f'{{"code":"{package.code}"}}', current_user.full_name)
    db.commit()
    db.refresh(package)
    return package


@router.get("/projects/{project_id}/work-package-constraints", response_model=list[WorkPackageConstraintOut])
def list_work_package_constraints(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[WorkPackageConstraint]:
    _require_membership(db, tenant_id, project_id, user_id)
    return list(
        db.scalars(
            select(WorkPackageConstraint)
            .where(WorkPackageConstraint.tenant_id == tenant_id, WorkPackageConstraint.project_id == project_id)
            .order_by(WorkPackageConstraint.status, WorkPackageConstraint.required_by, WorkPackageConstraint.id)
        ).all()
    )


@router.post("/projects/{project_id}/work-packages/{package_id}/constraints", response_model=WorkPackageConstraintOut)
def create_work_package_constraint(
    project_id: int,
    package_id: int,
    payload: WorkPackageConstraintCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> WorkPackageConstraint:
    _require_membership(db, tenant_id, project_id, user_id)
    current_user = _require_user(db, tenant_id, user_id)
    package = _require_work_package(db, tenant_id, project_id, package_id)
    constraint = WorkPackageConstraint(
        tenant_id=tenant_id,
        project_id=project_id,
        work_package_id=package.id,
        constraint_type=payload.constraint_type,
        description=payload.description,
        owner_role=payload.owner_role,
        required_by=payload.required_by,
        status=payload.status,
        blocking=payload.blocking,
    )
    db.add(constraint)
    if constraint.blocking and constraint.status == "open":
        package.readiness_status = "blocked"
    db.flush()
    _audit(db, tenant_id, project_id, "create_awp_constraint", "WorkPackageConstraint", constraint.id, f'{{"work_package":"{package.code}","type":"{constraint.constraint_type}"}}', current_user.full_name)
    db.commit()
    db.refresh(constraint)
    return constraint


@router.patch("/projects/{project_id}/work-packages/{package_id}/constraints/{constraint_id}", response_model=WorkPackageConstraintOut)
def update_work_package_constraint(
    project_id: int,
    package_id: int,
    constraint_id: int,
    payload: WorkPackageConstraintUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> WorkPackageConstraint:
    _require_membership(db, tenant_id, project_id, user_id)
    current_user = _require_user(db, tenant_id, user_id)
    package = _require_work_package(db, tenant_id, project_id, package_id)
    constraint = db.scalar(
        select(WorkPackageConstraint).where(
            WorkPackageConstraint.tenant_id == tenant_id,
            WorkPackageConstraint.project_id == project_id,
            WorkPackageConstraint.work_package_id == package.id,
            WorkPackageConstraint.id == constraint_id,
        )
    )
    if not constraint:
        raise HTTPException(status_code=404, detail="AWP constraint not found")
    _require_current_version(constraint, payload.expected_version)
    for field, value in payload.model_dump(exclude_unset=True, exclude={"expected_version"}).items():
        setattr(constraint, field, value)
    open_blockers = db.scalar(
        select(func.count(WorkPackageConstraint.id)).where(
            WorkPackageConstraint.tenant_id == tenant_id,
            WorkPackageConstraint.project_id == project_id,
            WorkPackageConstraint.work_package_id == package.id,
            WorkPackageConstraint.blocking.is_(True),
            WorkPackageConstraint.status == "open",
        )
    )
    if not open_blockers and package.readiness_status == "blocked":
        package.readiness_status = "ready_to_release"
        _touch_collaborative_record(package)
    _touch_collaborative_record(constraint)
    _audit(db, tenant_id, project_id, "update_awp_constraint", "WorkPackageConstraint", constraint.id, f'{{"status":"{constraint.status}"}}', current_user.full_name)
    db.commit()
    db.refresh(constraint)
    return constraint


@router.get("/projects/{project_id}/schedule-imports", response_model=list[ScheduleImportOut])
def list_schedule_imports(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ScheduleImport]:
    _require_membership(db, tenant_id, project_id, user_id)
    return list(
        db.scalars(
            select(ScheduleImport)
            .where(ScheduleImport.project_id == project_id, ScheduleImport.tenant_id == tenant_id)
            .order_by(ScheduleImport.imported_at.desc())
        ).all()
    )


@router.get("/projects/{project_id}/schedule-activities", response_model=list[ScheduleActivityMapOut])
def list_schedule_activities(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ScheduleActivityMap]:
    _require_membership(db, tenant_id, project_id, user_id)
    latest_import = _latest_schedule_import(db, tenant_id, project_id)
    if not latest_import:
        return []
    return list(
        db.scalars(
            select(ScheduleActivityMap)
            .where(ScheduleActivityMap.schedule_import_id == latest_import.id, ScheduleActivityMap.tenant_id == tenant_id)
            .order_by(ScheduleActivityMap.external_activity_id)
        ).all()
    )


@router.get("/projects/{project_id}/schedule-findings", response_model=list[ScheduleValidationFindingOut])
def list_schedule_findings(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ScheduleValidationFinding]:
    _require_membership(db, tenant_id, project_id, user_id)
    latest_import = _latest_schedule_import(db, tenant_id, project_id)
    if not latest_import:
        return []
    return list(
        db.scalars(
            select(ScheduleValidationFinding)
            .where(
                ScheduleValidationFinding.tenant_id == tenant_id,
                ScheduleValidationFinding.project_id == project_id,
                ScheduleValidationFinding.schedule_import_id == latest_import.id,
            )
            .order_by(ScheduleValidationFinding.severity, ScheduleValidationFinding.check_code)
        ).all()
    )


@router.get("/projects/{project_id}/baselines", response_model=list[BaselineVersionOut])
def list_baselines(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[BaselineVersion]:
    _require_membership(db, tenant_id, project_id, user_id)
    return list(
        db.scalars(
            select(BaselineVersion)
            .where(BaselineVersion.tenant_id == tenant_id, BaselineVersion.project_id == project_id)
            .order_by(BaselineVersion.version_no.desc())
        ).all()
    )


@router.get("/projects/{project_id}/control-periods", response_model=list[ControlPeriodOut])
def list_control_periods(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ControlPeriod]:
    _require_membership(db, tenant_id, project_id, user_id)
    return list(
        db.scalars(
            select(ControlPeriod)
            .where(ControlPeriod.tenant_id == tenant_id, ControlPeriod.project_id == project_id)
            .order_by(ControlPeriod.data_date.desc(), ControlPeriod.created_at.desc())
        ).all()
    )


@router.post("/projects/{project_id}/schedule-imports", response_model=ScheduleImportOut)
async def import_schedule(
    project_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ScheduleImport:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    if membership.role not in {"Planner", "Control Manager"}:
        raise HTTPException(status_code=403, detail="Current role cannot upload schedule baselines")
    project = db.scalar(select(Project).where(Project.id == project_id, Project.tenant_id == tenant_id))
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="Schedule file is empty")
    return ScheduleIngestionService(db).ingest(tenant_id, project_id, file.filename or "schedule.xml", content)


@router.post("/projects/{project_id}/control-cycle", response_model=KPIOut)
def run_control_cycle(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> KPI:
    _require_membership(db, tenant_id, project_id, user_id)
    return ControlCoreService(db).run_project_cycle(tenant_id, project_id)


@router.post("/projects/{project_id}/control-cycle/jobs")
def enqueue_control_cycle(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> dict[str, str]:
    _require_membership(db, tenant_id, project_id, user_id)
    task = run_control_cycle_task.apply_async(args=[tenant_id, project_id])
    return {"task_id": task.id, "status": "queued", "queue": "control-core"}


@router.get("/projects/{project_id}/control-snapshots", response_model=list[ControlSnapshotOut])
def list_control_snapshots(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ControlSnapshot]:
    _require_membership(db, tenant_id, project_id, user_id)
    return list(
        db.scalars(
            select(ControlSnapshot)
            .where(
                ControlSnapshot.tenant_id == tenant_id,
                ControlSnapshot.project_id == project_id,
                ControlSnapshot.control_account_id.is_(None),
            )
            .order_by(ControlSnapshot.period_label, ControlSnapshot.created_at)
        ).all()
    )


@router.get("/projects/{project_id}/forecast-scenarios", response_model=list[ForecastScenarioOut])
def list_forecast_scenarios(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ForecastScenario]:
    _require_membership(db, tenant_id, project_id, user_id)
    return list(
        db.scalars(
            select(ForecastScenario)
            .where(ForecastScenario.tenant_id == tenant_id, ForecastScenario.project_id == project_id)
            .order_by(ForecastScenario.period_label.desc(), ForecastScenario.name)
        ).all()
    )


@router.get("/projects/{project_id}/pilot-readiness", response_model=PilotReadinessOut)
def get_pilot_readiness(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> PilotReadinessOut:
    _require_membership(db, tenant_id, project_id, user_id)
    project = _require_project(db, tenant_id, project_id)
    return _pilot_readiness(db, tenant_id, project)


@router.post("/projects/{project_id}/workflow-instances/{process_id}/actions", response_model=BusinessProcessInstanceOut)
def apply_workflow_action(
    project_id: int,
    process_id: int,
    payload: WorkflowActionIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> BusinessProcessInstance:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    transition_permission = _workflow_transition_permission(db, tenant_id, process_id, payload.action)
    if transition_permission:
        _require_permission(membership, transition_permission, "Current role cannot execute this workflow transition")
    elif payload.action in {"approve_baseline", "reject_baseline", "close_action"}:
        _require_permission(membership, "can_approve_workflow", "Current role cannot approve or close workflow actions")
    current_user = _require_user(db, tenant_id, user_id)
    project = db.scalar(select(Project).where(Project.id == project_id, Project.tenant_id == tenant_id))
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    process = db.scalar(
        select(BusinessProcessInstance).where(
            BusinessProcessInstance.id == process_id,
            BusinessProcessInstance.tenant_id == tenant_id,
            BusinessProcessInstance.project_id == project_id,
        )
    )
    if not process:
        raise HTTPException(status_code=404, detail="Workflow process not found")
    _require_current_version(process, payload.expected_version)
    try:
        return WorkflowRoutingService(db).apply_action(
            tenant_id=tenant_id,
            project_id=project_id,
            process_id=process_id,
            action=payload.action,
            actor=f"{current_user.full_name} ({membership.role})",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/projects/{project_id}/dashboard", response_model=DashboardOut)
def get_dashboard(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> DashboardOut:
    project = _require_project(db, tenant_id, project_id)
    current_user = _require_user(db, tenant_id, user_id)
    current_membership = _require_membership(db, tenant_id, project_id, user_id)
    control_plan = _ensure_project_control_plan(db, tenant_id, project_id)

    project_kpi = db.scalars(
        select(KPI)
        .where(KPI.project_id == project_id, KPI.tenant_id == tenant_id, KPI.control_account_id.is_(None))
        .order_by(KPI.created_at.desc())
    ).first()
    if not project_kpi:
        project_kpi = ControlCoreService(db).run_project_cycle(tenant_id, project_id)
    active_period = project_kpi.period

    account_kpis = list(
        db.scalars(
            select(KPI)
            .where(
                KPI.project_id == project_id,
                KPI.tenant_id == tenant_id,
                KPI.control_account_id.is_not(None),
                KPI.period == active_period,
            )
            .order_by(KPI.control_account_id)
        ).all()
    )
    has_control_history = db.scalar(
        select(ControlSnapshot.id).where(
            ControlSnapshot.tenant_id == tenant_id,
            ControlSnapshot.project_id == project_id,
            ControlSnapshot.control_account_id.is_(None),
        )
    )
    if not has_control_history:
        project_kpi = ControlCoreService(db).run_project_cycle(tenant_id, project_id)
        active_period = project_kpi.period
        account_kpis = list(
            db.scalars(
                select(KPI)
                .where(
                    KPI.project_id == project_id,
                    KPI.tenant_id == tenant_id,
                    KPI.control_account_id.is_not(None),
                    KPI.period == active_period,
                )
                .order_by(KPI.control_account_id)
            ).all()
        )
    alerts = list(
        db.scalars(
            select(Alert).where(Alert.project_id == project_id, Alert.tenant_id == tenant_id).order_by(Alert.created_at.desc())
        ).all()
    )
    changes = list(
        db.scalars(select(ChangeRequest).where(ChangeRequest.project_id == project_id, ChangeRequest.tenant_id == tenant_id)).all()
    )
    claims = list(db.scalars(select(Claim).where(Claim.project_id == project_id, Claim.tenant_id == tenant_id)).all())
    claim_entitlement_items = list(
        db.scalars(
            select(ClaimEntitlementItem)
            .where(ClaimEntitlementItem.project_id == project_id, ClaimEntitlementItem.tenant_id == tenant_id)
            .order_by(ClaimEntitlementItem.claim_id, ClaimEntitlementItem.sequence_no, ClaimEntitlementItem.id)
        ).all()
    )
    contract_notices = list(
        db.scalars(
            select(ContractNotice)
            .where(ContractNotice.project_id == project_id, ContractNotice.tenant_id == tenant_id)
            .order_by(ContractNotice.notice_date.desc(), ContractNotice.id.desc())
        ).all()
    )
    claim_impact_analyses = list(
        db.scalars(
            select(ClaimImpactAnalysis)
            .where(ClaimImpactAnalysis.project_id == project_id, ClaimImpactAnalysis.tenant_id == tenant_id)
            .order_by(ClaimImpactAnalysis.claim_id, ClaimImpactAnalysis.id)
        ).all()
    )
    contracts = list(db.scalars(select(Contract).where(Contract.project_id == project_id, Contract.tenant_id == tenant_id).order_by(Contract.code)).all())
    purchase_orders = _purchase_orders(db, tenant_id, project_id)
    payment_certificates = _payment_certificates(db, tenant_id, project_id)
    warehouse_receipts = _warehouse_receipts(db, tenant_id, project_id)
    rfq_packages = _rfq_packages(db, tenant_id, project_id)
    rfq_bids = _rfq_bids(db, tenant_id, project_id)
    communications = list(
        db.scalars(
            select(ContractCommunication)
            .where(ContractCommunication.project_id == project_id, ContractCommunication.tenant_id == tenant_id)
            .order_by(ContractCommunication.sent_on.desc(), ContractCommunication.id.desc())
        ).all()
    )
    documents = _documents(db, tenant_id, project_id)
    document_transmittals = _document_transmittals(db, tenant_id, project_id)
    document_transmittal_items = _document_transmittal_items(db, tenant_id, project_id)
    document_reviews = _document_reviews(db, tenant_id, project_id)
    project_mail = _project_mail(db, tenant_id, project_id)
    work_packages = list(
        db.scalars(
            select(WorkPackage)
            .where(WorkPackage.project_id == project_id, WorkPackage.tenant_id == tenant_id)
            .order_by(WorkPackage.sequence_no, WorkPackage.code)
        ).all()
    )
    work_package_constraints = list(
        db.scalars(
            select(WorkPackageConstraint)
            .where(WorkPackageConstraint.project_id == project_id, WorkPackageConstraint.tenant_id == tenant_id)
            .order_by(WorkPackageConstraint.status, WorkPackageConstraint.required_by, WorkPackageConstraint.id)
        ).all()
    )
    accounts = list(
        db.scalars(select(ControlAccount).where(ControlAccount.project_id == project_id, ControlAccount.tenant_id == tenant_id)).all()
    )
    schedule_import = _latest_schedule_import(db, tenant_id, project_id)
    control_account_mappings = (
        list(
            db.scalars(
                select(ControlAccountMapping)
                .where(
                    ControlAccountMapping.tenant_id == tenant_id,
                    ControlAccountMapping.project_id == project_id,
                    ControlAccountMapping.schedule_import_id == schedule_import.id,
                )
                .order_by(ControlAccountMapping.wbs_code, ControlAccountMapping.cbs_code, ControlAccountMapping.id)
            ).all()
        )
        if schedule_import
        else []
    )
    schedule_activity_count = (
        db.scalar(
            select(func.count(ScheduleActivityMap.id)).where(
                ScheduleActivityMap.tenant_id == tenant_id,
                ScheduleActivityMap.project_id == project_id,
                ScheduleActivityMap.schedule_import_id == schedule_import.id if schedule_import else False,
            )
        )
        if schedule_import
        else 0
    )
    schedule_relationship_count = (
        db.scalar(
            select(func.count(ActivityRelationship.id)).where(
                ActivityRelationship.tenant_id == tenant_id,
                ActivityRelationship.project_id == project_id,
                ActivityRelationship.schedule_import_id == schedule_import.id if schedule_import else False,
            )
        )
        if schedule_import
        else 0
    )
    schedule_findings = (
        list(
            db.scalars(
                select(ScheduleValidationFinding)
                .where(
                    ScheduleValidationFinding.tenant_id == tenant_id,
                    ScheduleValidationFinding.project_id == project_id,
                    ScheduleValidationFinding.schedule_import_id == schedule_import.id,
                )
                .order_by(ScheduleValidationFinding.severity, ScheduleValidationFinding.check_code)
            ).all()
        )
        if schedule_import
        else []
    )
    baseline_versions = list(
        db.scalars(
            select(BaselineVersion)
            .where(BaselineVersion.tenant_id == tenant_id, BaselineVersion.project_id == project_id)
            .order_by(BaselineVersion.version_no.desc())
        ).all()
    )
    control_periods = list(
        db.scalars(
            select(ControlPeriod)
            .where(ControlPeriod.tenant_id == tenant_id, ControlPeriod.project_id == project_id)
            .order_by(ControlPeriod.data_date.desc(), ControlPeriod.created_at.desc())
        ).all()
    )
    workflow_instance = _latest_schedule_workflow(db, tenant_id, project_id, schedule_import.id) if schedule_import else None
    workflow_steps = (
        list(
            db.scalars(
                select(WorkflowStepInstance)
                .where(
                    WorkflowStepInstance.tenant_id == tenant_id,
                    WorkflowStepInstance.project_id == project_id,
                    WorkflowStepInstance.process_instance_id == workflow_instance.id,
                )
                .order_by(WorkflowStepInstance.step_order)
            ).all()
        )
        if workflow_instance
        else []
    )
    business_processes = list(
        db.scalars(
            select(BusinessProcessInstance)
            .where(BusinessProcessInstance.tenant_id == tenant_id, BusinessProcessInstance.project_id == project_id)
            .order_by(BusinessProcessInstance.created_at.desc())
        ).all()
    )
    audit_logs = list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.tenant_id == tenant_id, AuditLog.project_id == project_id)
            .order_by(AuditLog.created_at.desc())
        ).all()
    )
    latest_progress_records = list(
        db.scalars(
            select(ProgressRecord)
            .where(ProgressRecord.tenant_id == tenant_id, ProgressRecord.project_id == project_id)
            .order_by(ProgressRecord.reported_on.desc(), ProgressRecord.id.desc())
        ).all()
    )
    latest_cost_records = list(
        db.scalars(
            select(CostRecord)
            .where(CostRecord.tenant_id == tenant_id, CostRecord.project_id == project_id)
            .order_by(CostRecord.incurred_on.desc(), CostRecord.id.desc())
        ).all()
    )
    control_snapshots = list(
        db.scalars(
            select(ControlSnapshot)
            .where(
                ControlSnapshot.tenant_id == tenant_id,
                ControlSnapshot.project_id == project_id,
                ControlSnapshot.control_account_id.is_(None),
            )
            .order_by(ControlSnapshot.period_label, ControlSnapshot.created_at)
        ).all()
    )
    forecast_scenarios = list(
        db.scalars(
            select(ForecastScenario)
            .where(
                ForecastScenario.tenant_id == tenant_id,
                ForecastScenario.project_id == project_id,
                ForecastScenario.period_label == active_period,
            )
            .order_by(ForecastScenario.name)
        ).all()
    )
    cost_sheet = _cost_sheet_lines(db, tenant_id, project_id)
    funding_sources = _funding_sources(db, tenant_id, project_id)
    cash_flow = _cash_flow_periods(db, tenant_id, project_id)

    flow = [
        TCMFlowStep(name="Planeacion", purpose="WBS, baseline, logic, critical path and lookahead.", state="baselined"),
        TCMFlowStep(name="Cuentas de Control", purpose="Integrated schedule/cost/progress control objects.", state="active"),
        TCMFlowStep(name="Ejecucion", purpose="Field progress, actual cost, resources and evidence capture.", state="capturing"),
        TCMFlowStep(name="Control Core", purpose="EVM, changes, claims and early warning analysis.", state="running"),
        TCMFlowStep(name="Decision", purpose="Prioritized recommendations with governance.", state="open"),
        TCMFlowStep(name="Retroalimentacion", purpose="Actions update lookahead, forecast and contractual traceability.", state="continuous"),
    ]
    loop = [
        ControlCoreLoop(step="CAPTURAR", description="Progress, cost, resources, documents and field events."),
        ControlCoreLoop(step="VALIDAR", description="Data quality, contractual support and cross-discipline consistency."),
        ControlCoreLoop(step="ANALIZAR", description="EVM, productivity, change exposure and forensic signals."),
        ControlCoreLoop(step="ALERTAR", description="Threshold-based early warning with recommended response."),
        ControlCoreLoop(step="DECIDIR", description="Decision layer separates recommendations from execution workflows."),
        ControlCoreLoop(step="ACTUAR", description="Approved action updates forecast, lookahead, communications and audit."),
        ControlCoreLoop(step="REPETIR", description="Next control period starts from the updated project reality."),
    ]

    return DashboardOut(
        project=ProjectOut.model_validate(project),
        control_plan=ProjectControlPlanOut.model_validate(control_plan),
        current_user=UserOut.model_validate(current_user),
        current_membership=ProjectMembershipOut.model_validate(current_membership),
        project_team=_project_team(db, tenant_id, project_id),
        schedule_import=ScheduleImportOut.model_validate(schedule_import) if schedule_import else None,
        schedule_activity_count=schedule_activity_count or 0,
        schedule_relationship_count=schedule_relationship_count or 0,
        schedule_findings=[ScheduleValidationFindingOut.model_validate(finding) for finding in schedule_findings],
        baseline_versions=[BaselineVersionOut.model_validate(baseline) for baseline in baseline_versions[:6]],
        control_periods=[ControlPeriodOut.model_validate(period) for period in control_periods[:6]],
        workflow_instance=BusinessProcessInstanceOut.model_validate(workflow_instance) if workflow_instance else None,
        workflow_steps=[WorkflowStepInstanceOut.model_validate(step) for step in workflow_steps],
        business_processes=[BusinessProcessInstanceOut.model_validate(process) for process in business_processes],
        process_templates=_configured_process_templates(db, tenant_id),
        audit_logs=[AuditLogOut.model_validate(log) for log in audit_logs[:8]],
        data_quality_gates=_data_quality_gates(schedule_import, schedule_activity_count or 0, schedule_relationship_count or 0, schedule_findings),
        flow=flow,
        loop=loop,
        control_accounts=[ControlAccountOut.model_validate(account) for account in accounts],
        control_account_mappings=[ControlAccountMappingOut.model_validate(mapping) for mapping in control_account_mappings[:100]],
        control_account_mapping_summary=_control_account_mapping_summary(control_account_mappings, baseline_versions[0].status if baseline_versions else "pending"),
        latest_progress_records=[ProgressRecordOut.model_validate(record) for record in latest_progress_records[:6]],
        latest_cost_records=[CostRecordOut.model_validate(record) for record in latest_cost_records[:6]],
        cost_sheet=cost_sheet,
        funding_sources=[FundingSourceOut.model_validate(source) for source in funding_sources],
        cash_flow=[CashFlowPeriodOut.model_validate(period) for period in cash_flow],
        cost_manager_summary=_cost_manager_summary_from(cost_sheet, funding_sources, cash_flow),
        project_kpi=KPIOut.model_validate(project_kpi),
        account_kpis=[KPIOut.model_validate(kpi) for kpi in account_kpis],
        control_snapshots=[ControlSnapshotOut.model_validate(snapshot) for snapshot in control_snapshots[-12:]],
        forecast_scenarios=[ForecastScenarioOut.model_validate(scenario) for scenario in forecast_scenarios],
        productivity_summary=_productivity_summary(latest_progress_records),
        alerts=[AlertOut.model_validate(alert) for alert in alerts],
        changes=[ChangeRequestOut.model_validate(change) for change in changes],
        claims=[ClaimOut.model_validate(claim) for claim in claims],
        claim_entitlement_items=[ClaimEntitlementItemOut.model_validate(item) for item in claim_entitlement_items],
        claim_entitlement_summary=_claim_entitlement_summary(claim_entitlement_items),
        contract_notices=[ContractNoticeOut.model_validate(notice) for notice in contract_notices],
        claim_impact_analyses=[ClaimImpactAnalysisOut.model_validate(analysis) for analysis in claim_impact_analyses],
        claims_forensic_summary=_claims_forensic_summary(claims, contract_notices, claim_impact_analyses, claim_entitlement_items),
        contracts=[ContractOut.model_validate(contract) for contract in contracts],
        purchase_orders=[PurchaseOrderOut.model_validate(order) for order in purchase_orders],
        payment_certificates=[PaymentCertificateOut.model_validate(certificate) for certificate in payment_certificates],
        warehouse_receipts=[WarehouseReceiptOut.model_validate(receipt) for receipt in warehouse_receipts],
        rfq_packages=[RFQPackageOut.model_validate(package) for package in rfq_packages],
        rfq_bids=[RFQBidOut.model_validate(bid) for bid in rfq_bids],
        rfq_summary=_rfq_summary(rfq_packages, rfq_bids),
        communications=[ContractCommunicationOut.model_validate(communication) for communication in communications[:6]],
        documents=[DocumentOut.model_validate(document) for document in documents],
        document_transmittals=[DocumentTransmittalOut.model_validate(transmittal) for transmittal in document_transmittals],
        document_transmittal_items=[DocumentTransmittalItemOut.model_validate(item) for item in document_transmittal_items],
        document_reviews=[DocumentReviewOut.model_validate(review) for review in document_reviews],
        project_mail=[ProjectMailOut.model_validate(mail) for mail in project_mail],
        document_control_summary=_document_control_summary(documents, document_transmittals, document_reviews, project_mail),
        work_packages=[WorkPackageOut.model_validate(package) for package in work_packages],
        work_package_constraints=[WorkPackageConstraintOut.model_validate(constraint) for constraint in work_package_constraints],
        awp_summary=_awp_summary(work_packages, work_package_constraints),
        ai_brief=AIInsightService().explain_project_variance(project_kpi, alerts),
    )


def _cost_sheet_lines(db: Session, tenant_id: int, project_id: int) -> list[CostSheetLineOut]:
    accounts = list(
        db.scalars(
            select(ControlAccount)
            .where(ControlAccount.tenant_id == tenant_id, ControlAccount.project_id == project_id)
            .order_by(ControlAccount.code)
        ).all()
    )
    budgets = list(
        db.scalars(
            select(Budget)
            .where(Budget.tenant_id == tenant_id, Budget.project_id == project_id)
            .order_by(Budget.cbs_code)
        ).all()
    )
    cost_records = list(
        db.scalars(
            select(CostRecord).where(CostRecord.tenant_id == tenant_id, CostRecord.project_id == project_id)
        ).all()
    )
    contracts = list(
        db.scalars(
            select(Contract).where(Contract.tenant_id == tenant_id, Contract.project_id == project_id)
        ).all()
    )
    purchase_orders = _purchase_orders(db, tenant_id, project_id)
    payment_certificates = _payment_certificates(db, tenant_id, project_id)
    warehouse_receipts = _warehouse_receipts(db, tenant_id, project_id)
    latest_project_kpi = db.scalars(
        select(KPI)
        .where(KPI.tenant_id == tenant_id, KPI.project_id == project_id, KPI.control_account_id.is_(None))
        .order_by(KPI.created_at.desc())
    ).first()
    active_period = latest_project_kpi.period if latest_project_kpi else "current"
    kpis_by_account = {
        kpi.control_account_id: kpi
        for kpi in db.scalars(
            select(KPI).where(
                KPI.tenant_id == tenant_id,
                KPI.project_id == project_id,
                KPI.control_account_id.is_not(None),
                KPI.period == active_period,
            )
        ).all()
    }

    budgets_by_account: dict[int, list[Budget]] = {}
    for budget in budgets:
        budgets_by_account.setdefault(budget.control_account_id, []).append(budget)

    payment_certificates_by_account: dict[int, float] = {}
    for certificate in payment_certificates:
        if certificate.control_account_id and certificate.status not in {"cancelled", "rejected", "void", "draft"}:
            payment_certificates_by_account[certificate.control_account_id] = payment_certificates_by_account.get(certificate.control_account_id, 0) + certificate.certified_amount

    warehouse_receipts_by_account: dict[int, float] = {}
    for receipt in warehouse_receipts:
        if receipt.control_account_id and receipt.status not in {"cancelled", "rejected", "void", "draft"}:
            warehouse_receipts_by_account[receipt.control_account_id] = warehouse_receipts_by_account.get(receipt.control_account_id, 0) + receipt.received_value

    legacy_actual_by_account: dict[int, float] = {}
    for record in cost_records:
        if record.source != CostSource.commitment:
            legacy_actual_by_account[record.control_account_id] = legacy_actual_by_account.get(record.control_account_id, 0) + record.amount

    contract_commitments_by_account: dict[int, float] = {}
    for contract in contracts:
        if contract.control_account_id and contract.status not in {"cancelled", "rejected", "void", "draft"}:
            contract_commitments_by_account[contract.control_account_id] = contract_commitments_by_account.get(contract.control_account_id, 0) + contract.value

    po_commitments_by_account: dict[int, float] = {}
    for order in purchase_orders:
        if order.control_account_id and order.status not in {"cancelled", "rejected", "void", "draft"}:
            po_commitments_by_account[order.control_account_id] = po_commitments_by_account.get(order.control_account_id, 0) + order.committed_amount

    lines: list[CostSheetLineOut] = []
    for account in accounts:
        account_budgets = budgets_by_account.get(account.id, [])
        bac = sum(budget.bac for budget in account_budgets)
        budget_pv = sum(budget.cost_loaded_pv for budget in account_budgets)
        kpi = kpis_by_account.get(account.id)
        planned_value = kpi.pv if kpi else budget_pv
        earned_value = kpi.ev if kpi else 0
        incurred_payment_certificate_value = payment_certificates_by_account.get(account.id, 0)
        incurred_warehouse_receipt_value = warehouse_receipts_by_account.get(account.id, 0)
        source_actual_cost = incurred_payment_certificate_value + incurred_warehouse_receipt_value
        actual_cost = source_actual_cost or legacy_actual_by_account.get(account.id, 0)
        committed_contract_value = contract_commitments_by_account.get(account.id, 0)
        committed_purchase_order_value = po_commitments_by_account.get(account.id, 0)
        committed_cost = committed_contract_value + committed_purchase_order_value
        variance = earned_value - actual_cost
        cpi = earned_value / actual_cost if actual_cost else 0
        cbs_codes = ", ".join(sorted({budget.cbs_code for budget in account_budgets if budget.cbs_code}))
        lines.append(
            CostSheetLineOut(
                control_account_id=account.id,
                control_account_code=account.code,
                control_account_name=account.name,
                cbs_code=cbs_codes,
                bac=_money(bac),
                planned_value=_money(planned_value),
                actual_cost=_money(actual_cost),
                incurred_payment_certificate_value=_money(incurred_payment_certificate_value),
                incurred_warehouse_receipt_value=_money(incurred_warehouse_receipt_value),
                committed_contract_value=_money(committed_contract_value),
                committed_purchase_order_value=_money(committed_purchase_order_value),
                committed_cost=_money(committed_cost),
                earned_value=_money(earned_value),
                variance=_money(variance),
                cpi=round(cpi, 3),
            )
        )
    return lines


def _funding_sources(db: Session, tenant_id: int, project_id: int) -> list[FundingSource]:
    return list(
        db.scalars(
            select(FundingSource)
            .where(FundingSource.tenant_id == tenant_id, FundingSource.project_id == project_id)
            .order_by(FundingSource.code)
        ).all()
    )


def _cash_flow_periods(db: Session, tenant_id: int, project_id: int) -> list[CashFlowPeriod]:
    return list(
        db.scalars(
            select(CashFlowPeriod)
            .where(CashFlowPeriod.tenant_id == tenant_id, CashFlowPeriod.project_id == project_id)
            .order_by(CashFlowPeriod.period_label)
        ).all()
    )


def _purchase_orders(db: Session, tenant_id: int, project_id: int) -> list[PurchaseOrder]:
    return list(
        db.scalars(
            select(PurchaseOrder)
            .where(PurchaseOrder.tenant_id == tenant_id, PurchaseOrder.project_id == project_id)
            .order_by(PurchaseOrder.issued_on.desc(), PurchaseOrder.po_number)
        ).all()
    )


def _require_contract(db: Session, tenant_id: int, project_id: int, contract_id: int) -> Contract:
    contract = db.scalar(
        select(Contract).where(
            Contract.tenant_id == tenant_id,
            Contract.project_id == project_id,
            Contract.id == contract_id,
        )
    )
    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")
    return contract


def _payment_certificates(db: Session, tenant_id: int, project_id: int) -> list[PaymentCertificate]:
    return list(
        db.scalars(
            select(PaymentCertificate)
            .where(PaymentCertificate.tenant_id == tenant_id, PaymentCertificate.project_id == project_id)
            .order_by(PaymentCertificate.certified_on.desc(), PaymentCertificate.certificate_no)
        ).all()
    )


def _require_purchase_order(db: Session, tenant_id: int, project_id: int, purchase_order_id: int) -> PurchaseOrder:
    order = db.scalar(
        select(PurchaseOrder).where(
            PurchaseOrder.tenant_id == tenant_id,
            PurchaseOrder.project_id == project_id,
            PurchaseOrder.id == purchase_order_id,
        )
    )
    if not order:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    return order


def _warehouse_receipts(db: Session, tenant_id: int, project_id: int) -> list[WarehouseReceipt]:
    return list(
        db.scalars(
            select(WarehouseReceipt)
            .where(WarehouseReceipt.tenant_id == tenant_id, WarehouseReceipt.project_id == project_id)
            .order_by(WarehouseReceipt.received_on.desc(), WarehouseReceipt.receipt_no)
        ).all()
    )


def _require_contract_or_cost_role(membership: ProjectMembership, message: str) -> None:
    if not (membership.can_manage_contract or membership.can_capture_cost):
        raise HTTPException(status_code=403, detail=message)


def _validate_warehouse_receipt_values(received_quantity: float, unit_cost: float, received_value: float) -> None:
    if received_quantity < 0:
        raise HTTPException(status_code=400, detail="Received quantity cannot be negative")
    if unit_cost < 0:
        raise HTTPException(status_code=400, detail="Unit cost cannot be negative")
    if received_value < 0:
        raise HTTPException(status_code=400, detail="Received value cannot be negative")
    if received_value <= 0 and received_quantity * unit_cost <= 0:
        raise HTTPException(status_code=400, detail="Warehouse receipt must have received value or quantity times unit cost")


def _warehouse_received_value(received_quantity: float, unit_cost: float, received_value: float) -> float:
    return _money(received_value if received_value > 0 else received_quantity * unit_cost)


def _rfq_packages(db: Session, tenant_id: int, project_id: int) -> list[RFQPackage]:
    return list(
        db.scalars(
            select(RFQPackage)
            .where(RFQPackage.tenant_id == tenant_id, RFQPackage.project_id == project_id)
            .order_by(RFQPackage.due_date, RFQPackage.package_no)
        ).all()
    )


def _rfq_bids(db: Session, tenant_id: int, project_id: int, rfq_package_id: int | None = None) -> list[RFQBid]:
    query = select(RFQBid).where(RFQBid.tenant_id == tenant_id, RFQBid.project_id == project_id)
    if rfq_package_id is not None:
        query = query.where(RFQBid.rfq_package_id == rfq_package_id)
    return list(db.scalars(query.order_by(RFQBid.weighted_score.desc(), RFQBid.bid_amount, RFQBid.bidder_name)).all())


def _require_rfq_package(db: Session, tenant_id: int, project_id: int, rfq_package_id: int) -> RFQPackage:
    package = db.scalar(
        select(RFQPackage).where(
            RFQPackage.tenant_id == tenant_id,
            RFQPackage.project_id == project_id,
            RFQPackage.id == rfq_package_id,
        )
    )
    if not package:
        raise HTTPException(status_code=404, detail="RFQ package not found")
    return package


def _validate_rfq_bid_values(bid_amount: float, technical_score: float, commercial_score: float, schedule_score: float, risk_score: float) -> None:
    if bid_amount <= 0:
        raise HTTPException(status_code=400, detail="Bid amount must be greater than zero")
    for field, value in {
        "technical_score": technical_score,
        "commercial_score": commercial_score,
        "schedule_score": schedule_score,
        "risk_score": risk_score,
    }.items():
        if value < 0 or value > 100:
            raise HTTPException(status_code=400, detail=f"{field} must be between 0 and 100")


def _rfq_weighted_score(technical_score: float, commercial_score: float, schedule_score: float, risk_score: float) -> float:
    return round(technical_score * 0.35 + commercial_score * 0.35 + schedule_score * 0.15 + risk_score * 0.15, 1)


def _rfq_summary(packages: list[RFQPackage], bids: list[RFQBid]) -> RFQSummary:
    scored_bids = [bid for bid in bids if bid.status not in {"withdrawn", "disqualified", "void"}]
    recommended = max(scored_bids, key=lambda bid: (bid.weighted_score, -bid.bid_amount), default=None)
    return RFQSummary(
        total_packages=len(packages),
        issued_packages=sum(1 for package in packages if package.status in {"issued", "open", "under_evaluation", "awarded"}),
        bids_received=len(scored_bids),
        average_weighted_score=round(sum(bid.weighted_score for bid in scored_bids) / len(scored_bids), 1) if scored_bids else 0,
        recommended_bidder=recommended.bidder_name if recommended else "",
        recommended_bid_amount=_money(recommended.bid_amount) if recommended else 0,
    )


def _cost_manager_summary(db: Session, tenant_id: int, project_id: int) -> CostManagerSummaryOut:
    return _cost_manager_summary_from(
        _cost_sheet_lines(db, tenant_id, project_id),
        _funding_sources(db, tenant_id, project_id),
        _cash_flow_periods(db, tenant_id, project_id),
    )


def _cost_manager_summary_from(
    cost_sheet: list[CostSheetLineOut],
    funding_sources: list[FundingSource],
    cash_flow: list[CashFlowPeriod],
) -> CostManagerSummaryOut:
    total_bac = sum(line.bac for line in cost_sheet)
    total_planned_value = sum(line.planned_value for line in cost_sheet)
    total_earned_value = sum(line.earned_value for line in cost_sheet)
    total_actual_cost = sum(line.actual_cost for line in cost_sheet)
    total_incurred_from_payment_certificates = sum(line.incurred_payment_certificate_value for line in cost_sheet)
    total_incurred_from_warehouse_receipts = sum(line.incurred_warehouse_receipt_value for line in cost_sheet)
    total_contract_commitments = sum(line.committed_contract_value for line in cost_sheet)
    total_purchase_order_commitments = sum(line.committed_purchase_order_value for line in cost_sheet)
    total_committed_cost = sum(line.committed_cost for line in cost_sheet)
    total_funding = sum(source.amount for source in funding_sources if source.status not in {"cancelled", "rejected"})
    planned_inflow = sum(period.planned_inflow for period in cash_flow)
    actual_inflow = sum(period.actual_inflow for period in cash_flow)
    planned_outflow = sum(period.planned_outflow for period in cash_flow)
    actual_outflow = sum(period.actual_outflow for period in cash_flow)
    forecast_outflow = sum(period.forecast_outflow for period in cash_flow)
    planned_net = planned_inflow - planned_outflow
    actual_net = actual_inflow - actual_outflow
    return CostManagerSummaryOut(
        total_bac=_money(total_bac),
        total_planned_value=_money(total_planned_value),
        total_earned_value=_money(total_earned_value),
        total_actual_cost=_money(total_actual_cost),
        total_incurred_from_payment_certificates=_money(total_incurred_from_payment_certificates),
        total_incurred_from_warehouse_receipts=_money(total_incurred_from_warehouse_receipts),
        total_contract_commitments=_money(total_contract_commitments),
        total_purchase_order_commitments=_money(total_purchase_order_commitments),
        total_committed_cost=_money(total_committed_cost),
        total_funding=_money(total_funding),
        planned_inflow=_money(planned_inflow),
        actual_inflow=_money(actual_inflow),
        planned_outflow=_money(planned_outflow),
        actual_outflow=_money(actual_outflow),
        forecast_outflow=_money(forecast_outflow),
        cost_variance=_money(total_earned_value - total_actual_cost),
        funding_variance=_money(total_funding - total_bac),
        funding_coverage_percent=round((total_funding / total_bac) * 100, 1) if total_bac else 0,
        cash_flow_variance=_money(actual_net - planned_net),
    )


def _validate_cash_flow_values(payload: CashFlowPeriodCreate | CashFlowPeriodUpdate) -> None:
    for field in ("planned_inflow", "planned_outflow", "actual_inflow", "actual_outflow", "forecast_outflow"):
        value = getattr(payload, field)
        if value is not None and value < 0:
            raise HTTPException(status_code=400, detail=f"{field} cannot be negative")


def _money(value: float) -> float:
    return round(float(value or 0), 2)


def _documents(db: Session, tenant_id: int, project_id: int) -> list[Document]:
    return list(
        db.scalars(
            select(Document)
            .where(Document.tenant_id == tenant_id, Document.project_id == project_id)
            .order_by(Document.document_number, Document.revision.desc(), Document.id)
        ).all()
    )


def _document_transmittals(db: Session, tenant_id: int, project_id: int) -> list[DocumentTransmittal]:
    return list(
        db.scalars(
            select(DocumentTransmittal)
            .where(DocumentTransmittal.tenant_id == tenant_id, DocumentTransmittal.project_id == project_id)
            .order_by(DocumentTransmittal.sent_on.desc(), DocumentTransmittal.id.desc())
        ).all()
    )


def _document_transmittal_items(db: Session, tenant_id: int, project_id: int) -> list[DocumentTransmittalItem]:
    return list(
        db.scalars(
            select(DocumentTransmittalItem)
            .where(DocumentTransmittalItem.tenant_id == tenant_id, DocumentTransmittalItem.project_id == project_id)
            .order_by(DocumentTransmittalItem.transmittal_id, DocumentTransmittalItem.id)
        ).all()
    )


def _document_reviews(db: Session, tenant_id: int, project_id: int) -> list[DocumentReview]:
    return list(
        db.scalars(
            select(DocumentReview)
            .where(DocumentReview.tenant_id == tenant_id, DocumentReview.project_id == project_id)
            .order_by(DocumentReview.review_status, DocumentReview.due_date, DocumentReview.id)
        ).all()
    )


def _project_mail(db: Session, tenant_id: int, project_id: int) -> list[ProjectMail]:
    return list(
        db.scalars(
            select(ProjectMail)
            .where(ProjectMail.tenant_id == tenant_id, ProjectMail.project_id == project_id)
            .order_by(ProjectMail.sent_on.desc(), ProjectMail.id.desc())
        ).all()
    )


def _document_control_summary(
    documents: list[Document],
    transmittals: list[DocumentTransmittal],
    reviews: list[DocumentReview],
    mail: list[ProjectMail],
) -> DocumentControlSummary:
    today = datetime.utcnow().date()
    current_documents = sum(1 for document in documents if document.status in {"current", "approved", "issued"})
    superseded_documents = sum(1 for document in documents if document.status in {"superseded", "void"})
    outstanding_reviews = sum(1 for review in reviews if review.review_status in {"outstanding", "in_review", "revise_and_resubmit"})
    overdue_reviews = sum(
        1
        for review in reviews
        if review.due_date and review.due_date < today and review.review_status in {"outstanding", "in_review", "revise_and_resubmit"}
    )
    open_mail = sum(1 for item in mail if item.status in {"outstanding", "open", "in_review"})
    overdue_mail = sum(1 for item in mail if item.due_date and item.due_date < today and item.status in {"outstanding", "open", "in_review"})
    total_documents = len(documents)
    score = 0.0
    if total_documents:
        numbered = sum(1 for document in documents if document.document_number and document.revision)
        reviewed = sum(1 for document in documents if document.review_status in {"approved", "reviewed", "closed"})
        transmitted = len(transmittals)
        score = min((numbered / total_documents) * 45 + (reviewed / total_documents) * 35 + (transmitted > 0) * 20, 100)
        score = max(score - overdue_reviews * 5 - overdue_mail * 3, 0)
    return DocumentControlSummary(
        total_documents=total_documents,
        current_documents=current_documents,
        superseded_documents=superseded_documents,
        outstanding_reviews=outstanding_reviews,
        overdue_reviews=overdue_reviews,
        transmittals_sent=len([item for item in transmittals if item.status in {"sent", "closed"}]),
        open_mail=open_mail,
        overdue_mail=overdue_mail,
        controlled_document_score=round(score, 1),
    )


def _require_document(db: Session, tenant_id: int, project_id: int, document_id: int) -> Document:
    document = db.scalar(
        select(Document).where(
            Document.tenant_id == tenant_id,
            Document.project_id == project_id,
            Document.id == document_id,
        )
    )
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    return document


def _require_document_control_role(membership: ProjectMembership) -> None:
    if membership.role not in {"Control Manager", "Project Controls", "Document Controller", "Contract Manager", "Planner"}:
        raise HTTPException(status_code=403, detail="Current role cannot manage document control")


def _ensure_document_revision_available(
    db: Session,
    tenant_id: int,
    project_id: int,
    document_number: str,
    revision: str,
    exclude_id: int | None = None,
) -> None:
    query = select(Document).where(
        Document.tenant_id == tenant_id,
        Document.project_id == project_id,
        Document.document_number == document_number,
        Document.revision == revision,
    )
    if exclude_id is not None:
        query = query.where(Document.id != exclude_id)
    if db.scalar(query):
        raise HTTPException(status_code=409, detail="Document number and revision already exist for this project")


def _next_document_number(db: Session, tenant_id: int, project: Project) -> str:
    count = _count(db, Document, tenant_id, project.id) + 1
    return f"{project.code}-DOC-{count:04d}"


def _next_transmittal_no(db: Session, tenant_id: int, project: Project) -> str:
    count = _count(db, DocumentTransmittal, tenant_id, project.id) + 1
    return f"{project.code}-TR-{count:04d}"


def _next_mail_no(db: Session, tenant_id: int, project: Project) -> str:
    count = _count(db, ProjectMail, tenant_id, project.id) + 1
    return f"{project.code}-MAIL-{count:04d}"


def _latest_schedule_import(db: Session, tenant_id: int, project_id: int) -> ScheduleImport | None:
    return db.scalars(
        select(ScheduleImport)
        .where(ScheduleImport.project_id == project_id, ScheduleImport.tenant_id == tenant_id)
        .order_by(ScheduleImport.imported_at.desc())
    ).first()


def _ensure_project_control_plan(db: Session, tenant_id: int, project_id: int) -> ProjectControlPlan:
    _require_project(db, tenant_id, project_id)
    plan = db.scalar(
        select(ProjectControlPlan).where(
            ProjectControlPlan.tenant_id == tenant_id,
            ProjectControlPlan.project_id == project_id,
        )
    )
    if plan:
        return plan
    plan = _default_project_control_plan(tenant_id, project_id)
    db.add(plan)
    db.flush()
    return plan


def _default_project_control_plan(tenant_id: int, project_id: int) -> ProjectControlPlan:
    return ProjectControlPlan(
        tenant_id=tenant_id,
        project_id=project_id,
        execution_strategy="Execute through approved baseline, control accounts, weekly control cycle and exception-based decisions.",
        control_strategy="Use schedule intake, data quality gates, WBS/CBS/activity mapping, EVM, AWP readiness and workflow approvals.",
        progress_measurement_rule="Capture physical percent, installed quantities, labor hours and evidence by control account each control period.",
        cost_measurement_rule="Capture actual and committed costs by control account; reconcile against BAC, PV, EV, AC, CPI and EAC.",
        change_management_rule="Register deviations, evaluate cost/schedule impact, route workflow decisions and preserve audit trail.",
        risk_management_rule="Review schedule quality, productivity, cost variance, open constraints, notices and claim exposure every cycle.",
        procurement_strategy="Track procurement and contracting constraints that affect workface readiness, schedule logic and contractual notices.",
        document_control_rule="Link field reports, communications, notices, claim evidence and decision records to the controlled entity.",
        reporting_cadence="Weekly",
        status="draft",
    )


def _require_current_version(entity: object, expected_version: int | None) -> None:
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


def _touch_collaborative_record(entity: object) -> None:
    current_version = int(getattr(entity, "version", 1) or 1)
    setattr(entity, "version", current_version + 1)
    if hasattr(entity, "updated_at"):
        setattr(entity, "updated_at", datetime.utcnow())


def _pilot_readiness(db: Session, tenant_id: int, project: Project) -> PilotReadinessOut:
    project_id = project.id
    latest_import = _latest_schedule_import(db, tenant_id, project_id)
    control_plan = db.scalar(
        select(ProjectControlPlan).where(
            ProjectControlPlan.tenant_id == tenant_id,
            ProjectControlPlan.project_id == project_id,
        )
    )
    findings = _schedule_findings_for_import(db, tenant_id, project_id, latest_import.id) if latest_import else []
    finding_errors = sum(item.item_count for item in findings if item.severity == "error")
    finding_warnings = sum(item.item_count for item in findings if item.severity == "warning")

    team = _project_team(db, tenant_id, project_id)
    roles = {member.membership.role for member in team}
    audit_count = db.scalar(
        select(func.count(AuditLog.id)).where(AuditLog.tenant_id == tenant_id, AuditLog.project_id == project_id)
    ) or 0
    schedule_activity_count = _count(db, ScheduleActivityMap, tenant_id, project_id)
    relationship_count = _count(db, ActivityRelationship, tenant_id, project_id)
    control_account_count = _count(db, ControlAccount, tenant_id, project_id)
    progress_count = _count(db, ProgressRecord, tenant_id, project_id)
    payment_certificate_count = _count(db, PaymentCertificate, tenant_id, project_id)
    warehouse_receipt_count = _count(db, WarehouseReceipt, tenant_id, project_id)
    funding_count = _count(db, FundingSource, tenant_id, project_id)
    cash_flow_count = _count(db, CashFlowPeriod, tenant_id, project_id)
    snapshot_count = _count(db, ControlSnapshot, tenant_id, project_id)
    forecast_count = _count(db, ForecastScenario, tenant_id, project_id)
    contract_count = _count(db, Contract, tenant_id, project_id)
    purchase_order_count = _count(db, PurchaseOrder, tenant_id, project_id)
    rfq_package_count = _count(db, RFQPackage, tenant_id, project_id)
    rfq_bid_count = _count(db, RFQBid, tenant_id, project_id)
    notice_count = _count(db, ContractNotice, tenant_id, project_id)
    claim_count = _count(db, Claim, tenant_id, project_id)
    entitlement_count = _count(db, ClaimEntitlementItem, tenant_id, project_id)
    impact_count = _count(db, ClaimImpactAnalysis, tenant_id, project_id)
    document_count = _count(db, Document, tenant_id, project_id)
    transmittal_count = _count(db, DocumentTransmittal, tenant_id, project_id)
    review_count = _count(db, DocumentReview, tenant_id, project_id)
    project_mail_count = _count(db, ProjectMail, tenant_id, project_id)
    package_count = _count(db, WorkPackage, tenant_id, project_id)
    constraint_count = _count(db, WorkPackageConstraint, tenant_id, project_id)
    open_blocking_constraints = db.scalar(
        select(func.count(WorkPackageConstraint.id)).where(
            WorkPackageConstraint.tenant_id == tenant_id,
            WorkPackageConstraint.project_id == project_id,
            WorkPackageConstraint.blocking.is_(True),
            WorkPackageConstraint.status == "open",
        )
    ) or 0
    workflow_count = _count(db, BusinessProcessInstance, tenant_id, project_id)
    template_count = db.scalar(
        select(func.count(BusinessProcessTemplate.id)).where(BusinessProcessTemplate.tenant_id == tenant_id)
    ) or 0
    latest_baseline = db.scalars(
        select(BaselineVersion)
        .where(BaselineVersion.tenant_id == tenant_id, BaselineVersion.project_id == project_id)
        .order_by(BaselineVersion.version_no.desc())
    ).first()
    latest_kpi = db.scalars(
        select(KPI)
        .where(KPI.tenant_id == tenant_id, KPI.project_id == project_id, KPI.control_account_id.is_(None))
        .order_by(KPI.created_at.desc())
    ).first()

    mapping_score = 0.0
    cost_loading_score = 0.0
    if latest_import:
        mappings = list(
            db.scalars(
                select(ControlAccountMapping).where(
                    ControlAccountMapping.tenant_id == tenant_id,
                    ControlAccountMapping.project_id == project_id,
                    ControlAccountMapping.schedule_import_id == latest_import.id,
                )
            ).all()
        )
        mapping_summary = _control_account_mapping_summary(mappings, latest_baseline.status if latest_baseline else "missing")
        mapping_score = mapping_summary.mapping_score
        cost_loading_score = mapping_summary.cost_loading_score

    items = [
        _readiness_item(
            "Fase 1",
            "Schedule Intake / Data Quality",
            100 if latest_import and latest_import.status == ImportStatus.validated and latest_import.quality_score >= 70 and finding_errors == 0 else max(latest_import.quality_score if latest_import else 0, 0),
            f"{schedule_activity_count} actividades, {relationship_count} relaciones, {finding_errors} errores y {finding_warnings} advertencias.",
            "Cargar cronograma fuente y cerrar errores DCMA/AACE antes del piloto.",
        ),
        _readiness_item(
            "Fase 2",
            "Business Process Engine / Plan de Control",
            min((100 if workflow_count and template_count else 45) * 0.65 + _control_plan_score(control_plan) * 0.35, 100),
            f"{workflow_count} instancias workflow, {template_count} plantillas y plan de control {control_plan.status if control_plan else 'missing'}.",
            "Aprobar el PEP/Plan de Control y validar ball-in-court por rol.",
        ),
        _readiness_item(
            "Fase 3",
            "Control Accounts / Mapping",
            min((mapping_score * 0.65) + (cost_loading_score * 0.35), 100),
            f"{control_account_count} cuentas de control, mapeo {mapping_score:.1f}% y cost loading {cost_loading_score:.1f}%.",
            "Completar mapping WBS/CBS/Activity y aprobar baseline de control.",
        ),
        _readiness_item(
            "Fase 4",
            "EVM / Forecast / Cost Manager",
            100 if latest_kpi and snapshot_count and forecast_count and progress_count and payment_certificate_count and warehouse_receipt_count and purchase_order_count and funding_count and cash_flow_count else 55,
            f"{progress_count} avances, {payment_certificate_count} actas de pago, {warehouse_receipt_count} entradas de almacen, {purchase_order_count} ordenes de compra, {funding_count} fondos, {cash_flow_count} periodos cash flow, {snapshot_count} snapshots y {forecast_count} forecasts.",
            "Ejecutar ciclo de control con datos de avance, incurrido por actas de pago y entradas de almacen, comprometido contractual/OC, funding, cash flow y escenarios EAC.",
        ),
        _readiness_item(
            "Fase 5",
            "RFQ / Contracts / Claims / Aconex-style Document Control",
            min(
                (rfq_package_count > 0) * 8
                + (rfq_bid_count > 0) * 7
                + (contract_count > 0) * 16
                + (notice_count > 0) * 13
                + (claim_count > 0) * 13
                + (entitlement_count > 0) * 11
                + (impact_count > 0) * 9
                + (document_count > 0) * 10
                + (transmittal_count > 0) * 8
                + (review_count > 0) * 3
                + (project_mail_count > 0) * 2,
                100,
            ),
            f"{rfq_package_count} RFQ, {rfq_bid_count} ofertas, {contract_count} contratos, {notice_count} notices, {claim_count} claims, {document_count} documentos, {transmittal_count} transmittals, {review_count} revisiones y {project_mail_count} mails.",
            "Operar RFQ, evaluacion de ofertas, registro documental, transmittals, mail, revisiones y evidencia contractual.",
        ),
        _readiness_item(
            "Fase 6",
            "SaaS colaborativo / Operacion",
            min((len(team) >= 5) * 30 + (len(roles) >= 5) * 25 + (audit_count > 0) * 20 + (package_count > 0) * 15 + (constraint_count >= 0) * 10, 100),
            f"{len(team)} usuarios, {len(roles)} roles, {audit_count} eventos auditados, {package_count} work packages y {open_blocking_constraints} restricciones bloqueantes abiertas.",
            "Cerrar usuarios/roles del piloto, probar concurrencia y acordar rutina semanal.",
        ),
    ]
    score = round(sum(item.score for item in items) / len(items), 1)
    blockers = [f"{item.phase}: {item.area}" for item in items if item.status == "blocked"]
    if score >= 80 and not blockers:
        status = "ready"
    elif score >= 65:
        status = "pilot_candidate"
    else:
        status = "needs_preparation"
    return PilotReadinessOut(
        project_id=project.id,
        project_code=project.code,
        status=status,
        score=score,
        blockers=blockers,
        items=items,
    )


def _readiness_item(phase: str, area: str, score: float, finding: str, next_action: str) -> PilotReadinessItem:
    rounded_score = round(float(score), 1)
    if rounded_score >= 80:
        status = "ready"
    elif rounded_score >= 60:
        status = "watch"
    else:
        status = "blocked"
    return PilotReadinessItem(
        phase=phase,
        area=area,
        status=status,
        score=rounded_score,
        finding=finding,
        next_action=next_action,
    )


def _control_plan_score(plan: ProjectControlPlan | None) -> float:
    if not plan:
        return 0
    fields = [
        plan.execution_strategy,
        plan.control_strategy,
        plan.progress_measurement_rule,
        plan.cost_measurement_rule,
        plan.change_management_rule,
        plan.risk_management_rule,
        plan.procurement_strategy,
        plan.document_control_rule,
    ]
    completeness = sum(1 for field in fields if field and field.strip()) / len(fields)
    status_bonus = 20 if plan.status in {"approved", "active"} else 10 if plan.status == "in_review" else 0
    return min((completeness * 80) + status_bonus, 100)


def _count(db: Session, model: type, tenant_id: int, project_id: int) -> int:
    return db.scalar(
        select(func.count(model.id)).where(
            model.tenant_id == tenant_id,
            model.project_id == project_id,
        )
    ) or 0


def _schedule_findings_for_import(
    db: Session,
    tenant_id: int,
    project_id: int,
    schedule_import_id: int,
) -> list[ScheduleValidationFinding]:
    return list(
        db.scalars(
            select(ScheduleValidationFinding).where(
                ScheduleValidationFinding.tenant_id == tenant_id,
                ScheduleValidationFinding.project_id == project_id,
                ScheduleValidationFinding.schedule_import_id == schedule_import_id,
            )
        ).all()
    )


def _role_permissions(role: str) -> dict[str, bool]:
    catalog = {profile.role: profile for profile in _role_profiles()}
    if role not in catalog:
        raise HTTPException(status_code=400, detail="Unsupported role")
    profile = catalog[role]
    return {
        "can_capture_progress": profile.can_capture_progress,
        "can_capture_cost": profile.can_capture_cost,
        "can_approve_workflow": profile.can_approve_workflow,
        "can_manage_contract": profile.can_manage_contract,
        "can_configure": profile.can_configure,
    }


def _role_profiles() -> list[RoleProfileOut]:
    return [
        RoleProfileOut(
            role="Control Manager",
            description="Owns governance, approvals, project setup and Control Core decisions.",
            can_capture_progress=True,
            can_capture_cost=True,
            can_approve_workflow=True,
            can_manage_contract=True,
            can_configure=True,
        ),
        RoleProfileOut(
            role="Planner",
            description="Loads source schedules and supports logic, baseline and lookahead quality.",
            can_capture_progress=True,
            can_capture_cost=False,
            can_approve_workflow=False,
            can_manage_contract=False,
            can_configure=False,
        ),
        RoleProfileOut(
            role="Controls Engineer",
            description="Performs schedule/data quality review and control account analysis.",
            can_capture_progress=True,
            can_capture_cost=False,
            can_approve_workflow=False,
            can_manage_contract=False,
            can_configure=False,
        ),
        RoleProfileOut(
            role="Project Controls",
            description="Analyzes EVM, trends, changes and early warnings across the control cycle.",
            can_capture_progress=True,
            can_capture_cost=True,
            can_approve_workflow=False,
            can_manage_contract=False,
            can_configure=False,
        ),
        RoleProfileOut(
            role="Cost Controller",
            description="Captures ERP actuals, commitments, invoices and cost records.",
            can_capture_progress=False,
            can_capture_cost=True,
            can_approve_workflow=False,
            can_manage_contract=False,
            can_configure=False,
        ),
        RoleProfileOut(
            role="Contract Manager",
            description="Manages contracts, notices, communications and entitlement evidence.",
            can_capture_progress=False,
            can_capture_cost=False,
            can_approve_workflow=False,
            can_manage_contract=True,
            can_configure=False,
        ),
        RoleProfileOut(
            role="Document Controller",
            description="Manages the controlled document register, transmittals, project mail and review closeout.",
            can_capture_progress=False,
            can_capture_cost=False,
            can_approve_workflow=False,
            can_manage_contract=False,
            can_configure=False,
        ),
        RoleProfileOut(
            role="Field Engineer",
            description="Captures physical progress, quantities, resources and field evidence.",
            can_capture_progress=True,
            can_capture_cost=False,
            can_approve_workflow=False,
            can_manage_contract=False,
            can_configure=False,
        ),
        RoleProfileOut(
            role="Workface Planner",
            description="Owns AWP package readiness, constraints, IWP release and workface planning.",
            can_capture_progress=True,
            can_capture_cost=False,
            can_approve_workflow=False,
            can_manage_contract=False,
            can_configure=False,
        ),
        RoleProfileOut(
            role="Claims Analyst",
            description="Supports forensic analysis, causality, impact and evidence packages.",
            can_capture_progress=False,
            can_capture_cost=False,
            can_approve_workflow=False,
            can_manage_contract=True,
            can_configure=False,
        ),
        RoleProfileOut(
            role="Executive",
            description="Reads project, portfolio and decision dashboards without transactional rights.",
            can_capture_progress=False,
            can_capture_cost=False,
            can_approve_workflow=False,
            can_manage_contract=False,
            can_configure=False,
        ),
    ]


def _require_tenant_configurator(db: Session, tenant_id: int, user_id: int) -> UserAccount:
    user = _require_user(db, tenant_id, user_id)
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


def _start_business_process(
    db: Session,
    tenant_id: int,
    project_id: int,
    trigger_entity_type: str,
    trigger_entity_id: int,
    process_code: str,
    process_name: str,
    record_no: str,
    title: str,
    current_step: str,
    ball_in_court: str,
    steps: list[tuple[str, str, str, str, str]],
) -> BusinessProcessInstance:
    process = BusinessProcessInstance(
        tenant_id=tenant_id,
        project_id=project_id,
        trigger_entity_type=trigger_entity_type,
        trigger_entity_id=trigger_entity_id,
        process_code=process_code,
        process_name=process_name,
        record_no=record_no,
        title=title,
        status="in_review",
        current_step=current_step,
        ball_in_court=ball_in_court,
    )
    db.add(process)
    db.flush()
    configured_steps = _template_step_rows(db, tenant_id, process_code)
    materialized_steps = _initial_process_steps(configured_steps, current_step) if configured_steps else steps
    for order, (name, detail, owner_role, status, tone) in enumerate(materialized_steps, start=1):
        db.add(
            WorkflowStepInstance(
                tenant_id=tenant_id,
                project_id=project_id,
                process_instance_id=process.id,
                step_order=order,
                name=name,
                detail=detail,
                owner_role=owner_role,
                status=status,
                tone=tone,
            )
        )
    return process


def _require_project(db: Session, tenant_id: int, project_id: int) -> Project:
    project = db.scalar(select(Project).where(Project.id == project_id, Project.tenant_id == tenant_id))
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


def _require_user(db: Session, tenant_id: int, user_id: int) -> UserAccount:
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


def _require_membership(db: Session, tenant_id: int, project_id: int, user_id: int) -> ProjectMembership:
    _require_project(db, tenant_id, project_id)
    _require_user(db, tenant_id, user_id)
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


def _require_permission(membership: ProjectMembership, permission: str, message: str) -> None:
    if not bool(getattr(membership, permission)):
        raise HTTPException(status_code=403, detail=message)


def _project_team(db: Session, tenant_id: int, project_id: int) -> list[ProjectTeamMemberOut]:
    rows = db.execute(
        select(UserAccount, ProjectMembership)
        .join(ProjectMembership, ProjectMembership.user_id == UserAccount.id)
        .where(
            UserAccount.tenant_id == tenant_id,
            ProjectMembership.tenant_id == tenant_id,
            ProjectMembership.project_id == project_id,
        )
        .order_by(ProjectMembership.role, UserAccount.full_name)
    ).all()
    return [
        ProjectTeamMemberOut(
            user=UserOut.model_validate(user),
            membership=ProjectMembershipOut.model_validate(membership),
        )
        for user, membership in rows
    ]


def _require_control_account(db: Session, tenant_id: int, project_id: int, account_id: int) -> ControlAccount:
    account = db.scalar(
        select(ControlAccount).where(
            ControlAccount.id == account_id,
            ControlAccount.project_id == project_id,
            ControlAccount.tenant_id == tenant_id,
        )
    )
    if not account:
        raise HTTPException(status_code=404, detail="Control account not found")
    return account


def _require_work_package(db: Session, tenant_id: int, project_id: int, package_id: int) -> WorkPackage:
    package = db.scalar(
        select(WorkPackage).where(
            WorkPackage.id == package_id,
            WorkPackage.project_id == project_id,
            WorkPackage.tenant_id == tenant_id,
        )
    )
    if not package:
        raise HTTPException(status_code=404, detail="AWP work package not found")
    return package


def _require_claim(db: Session, tenant_id: int, project_id: int, claim_id: int) -> Claim:
    claim = db.scalar(
        select(Claim).where(
            Claim.id == claim_id,
            Claim.project_id == project_id,
            Claim.tenant_id == tenant_id,
        )
    )
    if not claim:
        raise HTTPException(status_code=404, detail="Claim not found")
    return claim


def _require_control_ready(db: Session, tenant_id: int, project_id: int) -> ScheduleImport:
    _require_project(db, tenant_id, project_id)
    latest_import = _latest_schedule_import(db, tenant_id, project_id)
    if not latest_import:
        raise HTTPException(status_code=409, detail="Load a source schedule before capturing project control data")
    if latest_import.status != ImportStatus.validated or latest_import.quality_score < 70:
        raise HTTPException(status_code=409, detail="Schedule data quality gate must pass before control capture")
    return latest_import


def _claim_entitlement_summary(items: list[ClaimEntitlementItem]) -> ClaimEntitlementSummary:
    total_weight = sum(item.weight for item in items) or 0
    weighted_score = sum(item.weight * item.score for item in items)
    cumulative_items = [item for item in items if item.practice_source == "RP130R-23"]
    return ClaimEntitlementSummary(
        total_items=len(items),
        satisfied_items=sum(1 for item in items if item.status == "satisfied"),
        partial_items=sum(1 for item in items if item.status == "partial"),
        gap_items=sum(1 for item in items if item.status == "gap"),
        cumulative_items=len(cumulative_items),
        cumulative_gap_items=sum(1 for item in cumulative_items if item.status == "gap"),
        entitlement_score=round((weighted_score / total_weight) * 100, 1) if total_weight else 0,
    )


def _claims_forensic_summary(
    claims: list[Claim],
    notices: list[ContractNotice],
    analyses: list[ClaimImpactAnalysis],
    entitlement_items: list[ClaimEntitlementItem],
) -> ClaimsForensicSummary:
    claim_count = len(claims)
    compliant_notices = sum(1 for notice in notices if notice.compliance_status == "compliant")
    late_notices = sum(1 for notice in notices if notice.compliance_status == "late")
    quantified_claim_ids = {
        analysis.claim_id
        for analysis in analyses
        if analysis.cost_impact > 0 or analysis.schedule_impact_days > 0 or analysis.productivity_loss_percent > 0
    }
    entitlement_score = _claim_entitlement_summary(entitlement_items).entitlement_score
    denominator = claim_count or 1
    notice_score = min((compliant_notices / denominator) * 100, 100) if notices else 0
    impact_score = min((len(quantified_claim_ids) / denominator) * 100, 100) if analyses else 0
    readiness_score = (notice_score * 0.30) + (impact_score * 0.35) + (entitlement_score * 0.35)
    return ClaimsForensicSummary(
        total_claims=claim_count,
        notice_count=len(notices),
        compliant_notices=compliant_notices,
        late_notices=late_notices,
        impact_analyses=len(analyses),
        quantified_claims=len(quantified_claim_ids),
        total_claimed_cost=round(sum(analysis.cost_impact for analysis in analyses), 2),
        total_schedule_impact_days=sum(analysis.schedule_impact_days for analysis in analyses),
        forensic_readiness_score=round(readiness_score, 1),
    )


def _control_account_mapping_summary(
    mappings: list[ControlAccountMapping],
    baseline_status: str,
) -> ControlAccountMappingSummary:
    total = len(mappings)
    mapped = sum(1 for mapping in mappings if mapping.control_account_id and mapping.status in {"mapped", "approved", "needs_cost_loading"})
    cost_loaded = sum(1 for mapping in mappings if mapping.planned_cost > 0)
    control_account_ids = {mapping.control_account_id for mapping in mappings if mapping.control_account_id}
    return ControlAccountMappingSummary(
        total_schedule_activities=total,
        mapped_activities=mapped,
        unmapped_activities=max(total - mapped, 0),
        control_account_count=len(control_account_ids),
        cost_loaded_activities=cost_loaded,
        total_bac=round(sum(mapping.planned_cost for mapping in mappings), 2),
        total_planned_value=round(sum(mapping.planned_value for mapping in mappings), 2),
        mapping_score=round((mapped / total) * 100, 1) if total else 0,
        cost_loading_score=round((cost_loaded / total) * 100, 1) if total else 0,
        baseline_status=baseline_status,
    )


def _productivity_summary(records: list[ProgressRecord]) -> ProductivitySummary:
    latest_by_account: dict[int, ProgressRecord] = {}
    for record in records:
        if record.control_account_id not in latest_by_account:
            latest_by_account[record.control_account_id] = record
    latest_records = list(latest_by_account.values())
    total_quantity = sum(record.quantity_installed for record in latest_records)
    total_hours = sum(record.labor_hours for record in latest_records)
    productivity_rate = total_quantity / total_hours if total_hours else 0
    productivity_index = min(productivity_rate / 0.12, 1.2) if productivity_rate else 0
    low_productivity_accounts = sum(
        1
        for record in latest_records
        if record.labor_hours and ((record.quantity_installed / record.labor_hours) / 0.12) < 0.85
    )
    return ProductivitySummary(
        total_quantity=round(total_quantity, 2),
        total_labor_hours=round(total_hours, 2),
        productivity_rate=round(productivity_rate, 4),
        productivity_index=round(productivity_index, 3),
        low_productivity_accounts=low_productivity_accounts,
    )


def _awp_summary(
    packages: list[WorkPackage],
    constraints: list[WorkPackageConstraint],
) -> AWPReadinessSummary:
    total_packages = len(packages)
    open_constraints = [constraint for constraint in constraints if constraint.status == "open"]
    blocking_constraints = [constraint for constraint in open_constraints if constraint.blocking]
    blocked_package_ids = {constraint.work_package_id for constraint in blocking_constraints}
    ready_statuses = {"ready_to_release", "released", "executing", "complete"}
    ready_for_release = sum(1 for package in packages if package.readiness_status in ready_statuses and package.id not in blocked_package_ids)
    readiness_score = round((ready_for_release / total_packages) * 100, 1) if total_packages else 0
    return AWPReadinessSummary(
        total_packages=total_packages,
        cwp_count=sum(1 for package in packages if package.package_type == "CWP"),
        iwp_count=sum(1 for package in packages if package.package_type == "IWP"),
        ready_for_release=ready_for_release,
        blocked_packages=len(blocked_package_ids),
        open_constraints=len(open_constraints),
        blocking_constraints=len(blocking_constraints),
        readiness_score=readiness_score,
    )


def _default_wbs(db: Session, tenant_id: int, project_id: int) -> WBS:
    wbs = db.scalars(
        select(WBS)
        .where(WBS.tenant_id == tenant_id, WBS.project_id == project_id)
        .order_by(WBS.code)
    ).first()
    if wbs:
        return wbs
    wbs = WBS(tenant_id=tenant_id, project_id=project_id, parent_id=None, code="1.0", name="Project Control Baseline")
    db.add(wbs)
    db.flush()
    return wbs


def _audit(
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


def _data_quality_gates(
    schedule_import: ScheduleImport | None,
    activity_count: int,
    relationship_count: int,
    findings: list[ScheduleValidationFinding] | None = None,
) -> list[DataQualityGateOut]:
    if not schedule_import:
        return [
            DataQualityGateOut(
                name="Schedule Intake",
                status="Waiting",
                score=0,
                finding="No source schedule has been loaded.",
                owner_role="Planner",
            ),
            DataQualityGateOut(
                name="Control Capture",
                status="Blocked",
                score=0,
                finding="Progress, actual cost and EVM are blocked until the schedule gate passes.",
                owner_role="Controls Engineer",
            ),
        ]

    schedule_passed = schedule_import.status == ImportStatus.validated and schedule_import.quality_score >= 70
    logic_passed = activity_count > 0 and relationship_count >= max(activity_count - 1, 0)
    mapping_passed = activity_count > 0
    findings = findings or []
    error_count = sum(finding.item_count for finding in findings if finding.severity == "error")
    warning_count = sum(finding.item_count for finding in findings if finding.severity == "warning")
    cost_loaded = not any(finding.check_code == "NO_COST_LOADING" for finding in findings)
    return [
        DataQualityGateOut(
            name="Schedule Intake",
            status="Pass" if schedule_passed else "Fail",
            score=schedule_import.quality_score,
            finding=schedule_import.validation_summary,
            owner_role="Planner",
        ),
        DataQualityGateOut(
            name="Logic Integrity",
            status="Pass" if logic_passed else "Review",
            score=100 if logic_passed else 65,
            finding=f"{activity_count} activities and {relationship_count} relationships in the active schedule import.",
            owner_role="Controls Engineer",
        ),
        DataQualityGateOut(
            name="DCMA / AACE Quality",
            status="Pass" if not error_count and warning_count <= 5 else "Review",
            score=schedule_import.quality_score,
            finding=f"{error_count} error items and {warning_count} warning items found in schedule QA.",
            owner_role="Controls Engineer",
        ),
        DataQualityGateOut(
            name="Control Account Mapping",
            status="Pass" if mapping_passed else "Blocked",
            score=100 if mapping_passed else 0,
            finding="Imported schedule activities are available for control account mapping." if mapping_passed else "No imported activities are available.",
            owner_role="Project Controls",
        ),
        DataQualityGateOut(
            name="Cost Loading",
            status="Pass" if cost_loaded else "Review",
            score=100 if cost_loaded else 60,
            finding="Cost-loaded schedule values were found." if cost_loaded else "No cost-loaded activity values found; budget loading is required before reliable EVM.",
            owner_role="Cost Controller",
        ),
        DataQualityGateOut(
            name="Control Capture",
            status="Open" if schedule_passed else "Blocked",
            score=85 if schedule_passed else 0,
            finding="Progress and actual cost capture can feed the Control Core." if schedule_passed else "Control capture waits for an accepted baseline.",
            owner_role="Execution Lead",
        ),
    ]


def _configured_process_templates(db: Session, tenant_id: int) -> list[ProcessTemplateOut]:
    templates = list(
        db.scalars(
            select(BusinessProcessTemplate)
            .where(BusinessProcessTemplate.tenant_id == tenant_id)
            .order_by(BusinessProcessTemplate.category, BusinessProcessTemplate.code)
        ).all()
    )
    if templates:
        return [_process_template_out(db, template) for template in templates]
    return [_catalog_process_template_out(template) for template in DEFAULT_PROCESS_TEMPLATES]


def _process_template_out(db: Session, template: BusinessProcessTemplate) -> ProcessTemplateOut:
    steps = list(
        db.scalars(
            select(BusinessProcessStepTemplate)
            .where(BusinessProcessStepTemplate.tenant_id == template.tenant_id, BusinessProcessStepTemplate.template_id == template.id)
            .order_by(BusinessProcessStepTemplate.step_order)
        ).all()
    )
    transitions = list(
        db.scalars(
            select(BusinessProcessTransitionTemplate)
            .where(BusinessProcessTransitionTemplate.tenant_id == template.tenant_id, BusinessProcessTransitionTemplate.template_id == template.id)
            .order_by(BusinessProcessTransitionTemplate.id)
        ).all()
    )
    form_schema = _parse_form_schema(template.form_schema)
    roles = sorted({step.owner_role for step in steps if step.owner_role})
    return ProcessTemplateOut(
        id=template.id,
        code=template.code,
        name=template.name,
        category=template.category,
        description=template.description,
        version_no=template.version_no,
        form_schema=form_schema,
        workflow_steps=[step.name for step in steps],
        roles=roles,
        status=template.status,
        step_templates=[ProcessStepTemplateOut.model_validate(step) for step in steps],
        transitions=[ProcessTransitionTemplateOut.model_validate(transition) for transition in transitions],
    )


def _catalog_process_template_out(template: dict) -> ProcessTemplateOut:
    step_templates = [
        ProcessStepTemplateOut(
            id=None,
            step_order=index,
            name=step["name"],
            detail=step.get("detail", ""),
            owner_role=step.get("owner_role", ""),
            status=step.get("status", "Queued"),
            tone=step.get("tone", "queued"),
        )
        for index, step in enumerate(template.get("steps", []), start=1)
    ]
    transitions = [
        ProcessTransitionTemplateOut(
            id=None,
            action=transition["action"],
            label=transition.get("label", transition["action"].replace("_", " ").title()),
            from_step=transition.get("from_step", ""),
            to_step=transition.get("to_step", ""),
            process_status=transition.get("process_status", "in_review"),
            ball_in_court=transition.get("ball_in_court", ""),
            from_status=transition.get("from_status", "Complete"),
            from_tone=transition.get("from_tone", "complete"),
            to_status=transition.get("to_status", "Active"),
            to_tone=transition.get("to_tone", "active"),
            requires_approval=transition.get("requires_approval", False),
            permission_key=transition.get("permission_key", ""),
        )
        for transition in template.get("transitions", [])
    ]
    roles = sorted({step.owner_role for step in step_templates if step.owner_role})
    return ProcessTemplateOut(
        id=None,
        code=template["code"],
        name=template["name"],
        category=template.get("category", "Custom"),
        description=template.get("description", ""),
        version_no=template.get("version_no", 1),
        form_schema=template.get("form_schema", []),
        workflow_steps=[step.name for step in step_templates],
        roles=roles,
        status=template.get("status", "Draft"),
        step_templates=step_templates,
        transitions=transitions,
    )


def _parse_form_schema(raw_schema: str) -> list[str]:
    try:
        loaded = json.loads(raw_schema or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(loaded, list):
        return []
    return [str(item) for item in loaded]


def _template_step_rows(
    db: Session,
    tenant_id: int,
    process_code: str,
) -> list[tuple[str, str, str, str, str]]:
    template = db.scalar(
        select(BusinessProcessTemplate).where(
            BusinessProcessTemplate.tenant_id == tenant_id,
            BusinessProcessTemplate.code == process_code,
        )
    )
    if not template:
        return []
    steps = list(
        db.scalars(
            select(BusinessProcessStepTemplate)
            .where(BusinessProcessStepTemplate.tenant_id == tenant_id, BusinessProcessStepTemplate.template_id == template.id)
            .order_by(BusinessProcessStepTemplate.step_order)
        ).all()
    )
    return [(step.name, step.detail, step.owner_role, step.status, step.tone) for step in steps]


def _initial_process_steps(
    step_rows: list[tuple[str, str, str, str, str]],
    current_step: str,
) -> list[tuple[str, str, str, str, str]]:
    active_index = next((index for index, row in enumerate(step_rows) if row[0] == current_step), None)
    if active_index is None:
        return step_rows
    materialized: list[tuple[str, str, str, str, str]] = []
    for index, (name, detail, owner_role, status, tone) in enumerate(step_rows):
        if index < active_index:
            materialized.append((name, detail, owner_role, "Complete", "complete"))
        elif index == active_index:
            materialized.append((name, detail, owner_role, "Active", "active"))
        else:
            materialized.append((name, detail, owner_role, status, tone))
    return materialized


def _workflow_transition_permission(
    db: Session,
    tenant_id: int,
    process_id: int,
    action: str,
) -> str:
    process = db.scalar(select(BusinessProcessInstance).where(BusinessProcessInstance.tenant_id == tenant_id, BusinessProcessInstance.id == process_id))
    if not process:
        return ""
    transition = _configured_transition(db, tenant_id, process.process_code, process.current_step, action)
    if not transition:
        return ""
    if transition.permission_key:
        return transition.permission_key
    return "can_approve_workflow" if transition.requires_approval else ""


def _configured_transition(
    db: Session,
    tenant_id: int,
    process_code: str,
    current_step: str,
    action: str,
) -> BusinessProcessTransitionTemplate | None:
    normalized = action.strip().lower()
    template = db.scalar(
        select(BusinessProcessTemplate).where(
            BusinessProcessTemplate.tenant_id == tenant_id,
            BusinessProcessTemplate.code == process_code,
        )
    )
    if not template:
        return None
    exact = db.scalar(
        select(BusinessProcessTransitionTemplate).where(
            BusinessProcessTransitionTemplate.tenant_id == tenant_id,
            BusinessProcessTransitionTemplate.template_id == template.id,
            BusinessProcessTransitionTemplate.action == normalized,
            BusinessProcessTransitionTemplate.from_step == current_step,
        )
    )
    if exact:
        return exact
    return db.scalar(
        select(BusinessProcessTransitionTemplate).where(
            BusinessProcessTransitionTemplate.tenant_id == tenant_id,
            BusinessProcessTransitionTemplate.template_id == template.id,
            BusinessProcessTransitionTemplate.action == normalized,
            BusinessProcessTransitionTemplate.from_step == "",
        )
    )


def _latest_schedule_workflow(
    db: Session,
    tenant_id: int,
    project_id: int,
    schedule_import_id: int,
) -> BusinessProcessInstance | None:
    return db.scalars(
        select(BusinessProcessInstance)
        .where(
            BusinessProcessInstance.tenant_id == tenant_id,
            BusinessProcessInstance.project_id == project_id,
            BusinessProcessInstance.trigger_entity_type == "ScheduleImport",
            BusinessProcessInstance.trigger_entity_id == schedule_import_id,
        )
        .order_by(BusinessProcessInstance.created_at.desc())
    ).first()
