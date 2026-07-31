import csv
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta
from io import BytesIO, StringIO
from uuid import uuid4
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

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
    require_project as _require_project,
)
from app.api.v1._helpers import (
    touch_collaborative_record as _touch_collaborative_record,
)
from app.api.v1._helpers import (
    write_audit_log as _audit,
)
from app.api.v1.routers import admin as admin_router
from app.api.v1.routers import auth as auth_router
from app.api.v1.routers import documents as documents_domain
from app.api.v1.routers import health as health_router
from app.api.v1.routers import projects as projects_router
from app.api.v1.routers import rfq as rfq_domain
from app.core.config import get_settings
from app.core.security import TokenError, decode_access_token
from app.core.time import utc_now
from app.database.session import get_db
from app.domain.models import (
    KPI,
    WBS,
    Activity,
    ActivityRelationship,
    ActivitySheet,
    ActivitySheetRecostRun,
    ActivitySheetRecostRunLine,
    ActivitySheetRow,
    Alert,
    AuditLog,
    BaselineVersion,
    Budget,
    BusinessProcessInstance,
    BusinessProcessLineItem,
    BusinessProcessLineItemRevision,
    BusinessProcessPolicy,
    BusinessProcessStepTemplate,
    BusinessProcessTemplate,
    BusinessProcessTransitionTemplate,
    CashFlowPeriod,
    ChangeRequest,
    Claim,
    ClaimEntitlementItem,
    ClaimImpactAnalysis,
    CommitmentFundingLine,
    Contract,
    ContractCommunication,
    ContractNotice,
    ControlAccount,
    ControlAccountFundingAllocation,
    ControlAccountMapping,
    ControlAgentFinding,
    ControlAgentRun,
    ControlPeriod,
    ControlSnapshot,
    CostBreakdownStructure,
    CostCode,
    CostRecord,
    CostSource,
    Document,
    DocumentReview,
    DocumentTransmittal,
    ForecastScenario,
    FundingSource,
    ImportStatus,
    IntegrationExportLog,
    IntegrationToken,
    PaymentCertificate,
    ProgressRecord,
    Project,
    ProjectControlPlan,
    ProjectMail,
    ProjectMembership,
    PurchaseOrder,
    RateSheet,
    RateSheetLine,
    RFQBid,
    RFQPackage,
    ScheduleActivityMap,
    ScheduleImport,
    ScheduleOfValueLine,
    ScheduleValidationFinding,
    UserAccount,
    WarehouseReceipt,
    WorkflowStatus,
    WorkflowStepInstance,
    WorkPackage,
    WorkPackageConstraint,
)
from app.domain.process_catalog import DEFAULT_PROCESS_TEMPLATES
from app.domain.schemas import (
    ActivityCreate,
    ActivityOut,
    ActivityRelationshipOut,
    ActivitySheetRecostIn,
    ActivitySheetRecostOut,
    ActivitySheetRecostRunLineOut,
    ActivitySheetRecostRunOut,
    AlertOut,
    AuditLogOut,
    AWPReadinessSummary,
    BaselineApprovalOut,
    BaselineVersionOut,
    BusinessProcessCreate,
    BusinessProcessInstanceOut,
    BusinessProcessLineItemOut,
    BusinessProcessLineItemRevisionOut,
    BusinessProcessLineItemUpdate,
    BusinessProcessPolicyCreate,
    BusinessProcessPolicyOut,
    CashFlowPeriodCreate,
    CashFlowPeriodOut,
    CashFlowPeriodUpdate,
    ChangeRequestCreate,
    ChangeRequestOut,
    ClaimCreate,
    ClaimEntitlementItemCreate,
    ClaimEntitlementItemOut,
    ClaimEntitlementItemUpdate,
    ClaimEntitlementSummary,
    ClaimImpactAnalysisCreate,
    ClaimImpactAnalysisOut,
    ClaimImpactAnalysisUpdate,
    ClaimOut,
    ClaimsForensicSummary,
    CloseoutReportOut,
    CommitmentFundingLineCreate,
    CommitmentFundingLineOut,
    ContractCommunicationCreate,
    ContractCommunicationOut,
    ContractCreate,
    ContractNoticeCreate,
    ContractNoticeOut,
    ContractOut,
    ControlAccountCreate,
    ControlAccountFundingAllocationCreate,
    ControlAccountFundingAllocationOut,
    ControlAccountMappingOut,
    ControlAccountMappingSummary,
    ControlAccountOut,
    ControlAccountUpdate,
    ControlAgentFindingOut,
    ControlAgentRunOut,
    ControlCoreLoop,
    ControlPeriodOut,
    ControlSnapshotOut,
    CostBreakdownStructureCreate,
    CostBreakdownStructureOut,
    CostCodeCreate,
    CostCodeOut,
    CostManagerSummaryOut,
    CostRecordCreate,
    CostRecordOut,
    CostSheetLineOut,
    DashboardOut,
    DataQualityGateOut,
    DocumentAttachmentOut,
    DocumentOut,
    DocumentReviewOut,
    DocumentTransmittalItemOut,
    DocumentTransmittalOut,
    ForecastFundingReport,
    ForecastScenarioOut,
    ForensicDossierAnalysisOut,
    ForensicRagSourceOut,
    ForensicWindowAnalysisOut,
    FundingAvailabilityOut,
    FundingSourceCreate,
    FundingSourceOut,
    FundingSourceUpdate,
    IntegratedControlMatrixRow,
    IntegrationExportLogOut,
    IntegrationTokenAlertOut,
    IntegrationTokenAlertSummary,
    IntegrationTokenCreate,
    IntegrationTokenCreated,
    IntegrationTokenOut,
    KPIOut,
    PaymentCertificateCreate,
    PaymentCertificateOut,
    PaymentCertificateUpdate,
    PilotReadinessItem,
    PilotReadinessOut,
    ProcessStepTemplateOut,
    ProcessTemplateOut,
    ProcessTransitionTemplateOut,
    ProductivitySummary,
    ProgressRecordCreate,
    ProgressRecordOut,
    ProjectControlPlanOut,
    ProjectMailOut,
    ProjectMembershipOut,
    ProjectOut,
    ProjectTeamMemberOut,
    PurchaseOrderCreate,
    PurchaseOrderOut,
    PurchaseOrderUpdate,
    RateSheetCreate,
    RateSheetLineOut,
    RateSheetOut,
    ReconciliationReportOut,
    ReconciliationReportRow,
    RFQBidOut,
    RFQPackageOut,
    RoleProfileOut,
    ScheduleActivityMapOut,
    ScheduleImportOut,
    ScheduleOfValueLineCreate,
    ScheduleOfValueLineOut,
    ScheduleQualityMetricOut,
    ScheduleValidationFindingOut,
    TCMFlowStep,
    UserOut,
    WarehouseReceiptCreate,
    WarehouseReceiptOut,
    WarehouseReceiptUpdate,
    WBSCreate,
    WBSOut,
    WorkflowActionIn,
    WorkflowStepInstanceOut,
    WorkPackageConstraintCreate,
    WorkPackageConstraintOut,
    WorkPackageConstraintUpdate,
    WorkPackageCreate,
    WorkPackageOut,
    WorkPackageReadinessUpdate,
)
from app.services.ai_insights import AIInsightService
from app.services.claims_forensic import ClaimsForensicDossierService
from app.services.control_audit_agent import ControlAuditAgentService
from app.services.control_core import ControlCoreService
from app.services.forensic_window_analysis import ForensicWindowAnalysisService
from app.services.integrated_control import IntegratedControlService
from app.services.schedule_ingestion import ScheduleIngestionService
from app.services.workflow_routing import WorkflowRoutingService
from app.workers.tasks import run_control_cycle as run_control_cycle_task

router = APIRouter(prefix="/api/v1")
router.include_router(health_router.router, tags=["health"])
router.include_router(auth_router.router, tags=["auth"])
router.include_router(admin_router.router, tags=["admin"])
router.include_router(projects_router.router, tags=["projects"])
router.include_router(documents_domain.router, tags=["documents"])
router.include_router(rfq_domain.router, tags=["rfq"])


INTEGRATION_TOKEN_PREFIX = "pypmis_it_"
INTEGRATION_TOKEN_MAX_DAYS = 90

AWP_PACKAGE_TYPES = {"CWA", "CWP", "EWP", "PWP", "IWP", "TWP", "TOP"}
AWP_PACKAGE_LEVELS = {
    "CWA": 10,
    "CWP": 20,
    "EWP": 30,
    "PWP": 30,
    "IWP": 40,
    "TWP": 50,
    "TOP": 50,
}
AWP_CONSTRAINT_PRIORITIES = {"low", "medium", "high", "critical"}
CONTROL_ACCOUNT_STATUSES = {"draft", "active", "under_change", "closed"}


@dataclass(frozen=True)
class IntegrationAccess:
    tenant_id: int
    project: Project
    membership: ProjectMembership
    allowed_datasets: list[str]
    allowed_formats: list[str]
    actor_user_id: int
    actor: str
    token: IntegrationToken | None = None


INTEGRATION_DATASETS = {
    "wbs": {
        "label": "WBS",
        "description": "Work breakdown structure catalog for downstream BI or ERP staging.",
        "schema": WBSOut,
    },
    "control_accounts": {
        "label": "Control accounts",
        "description": "Control account catalog used to join schedule, cost, contracts and documents.",
        "schema": ControlAccountOut,
    },
    "schedule_imports": {
        "label": "Schedule imports",
        "description": "Imported schedule files, quality scores and data dates.",
        "schema": ScheduleImportOut,
    },
    "schedule_validation_findings": {
        "label": "Schedule validation findings",
        "description": "Validation findings for the latest schedule import.",
        "schema": ScheduleValidationFindingOut,
    },
    "control_account_mappings": {
        "label": "Control account mappings",
        "description": "Latest schedule-to-control-account mapping register.",
        "schema": ControlAccountMappingOut,
    },
    "cost_sheet": {
        "label": "Cost sheet",
        "description": "Calculated BAC, PV, EV, AC, commitments, incurred cost, variance and CPI by control account.",
        "schema": CostSheetLineOut,
    },
    "funding_sources": {
        "label": "Funding sources",
        "description": "Approved and draft funding records for the project.",
        "schema": FundingSourceOut,
    },
    "cash_flow": {
        "label": "Cash flow",
        "description": "Planned, actual and forecast cash-flow periods.",
        "schema": CashFlowPeriodOut,
    },
    "progress_records": {
        "label": "Progress records",
        "description": "Field progress captures by control account.",
        "schema": ProgressRecordOut,
    },
    "cost_records": {
        "label": "Cost records",
        "description": "Legacy or direct cost captures by source and control account.",
        "schema": CostRecordOut,
    },
    "contracts": {
        "label": "Contracts",
        "description": "Contract register for commitments and commercial traceability.",
        "schema": ContractOut,
    },
    "purchase_orders": {
        "label": "Purchase orders",
        "description": "Purchase-order commitments issued against control accounts and contracts.",
        "schema": PurchaseOrderOut,
    },
    "payment_certificates": {
        "label": "Payment certificates",
        "description": "Certified incurred cost records.",
        "schema": PaymentCertificateOut,
    },
    "warehouse_receipts": {
        "label": "Warehouse receipts",
        "description": "Received goods/services evidence used as incurred cost.",
        "schema": WarehouseReceiptOut,
    },
    "documents": {
        "label": "Documents",
        "description": "Document register filtered by the caller's confidentiality access.",
        "schema": DocumentOut,
    },
    "document_attachments": {
        "label": "Document attachments",
        "description": "Stored files filtered by the caller's confidentiality access.",
        "schema": DocumentAttachmentOut,
    },
}


@router.get("/projects/{project_id}/wbs", response_model=list[WBSOut])
def list_wbs(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[WBS]:
    _require_membership(db, tenant_id, project_id, user_id)
    return list(
        db.scalars(select(WBS).where(WBS.project_id == project_id, WBS.tenant_id == tenant_id).order_by(WBS.code)).all()
    )


@router.post("/projects/{project_id}/wbs", response_model=WBSOut)
def create_wbs(
    project_id: int,
    payload: WBSCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> WBS:
    _require_project(db, tenant_id, project_id)
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_configure", "Current role cannot configure WBS")
    current_user = _require_user(db, tenant_id, user_id)
    if payload.parent_id is not None:
        parent = db.scalar(
            select(WBS).where(WBS.tenant_id == tenant_id, WBS.project_id == project_id, WBS.id == payload.parent_id)
        )
        if not parent:
            raise HTTPException(status_code=404, detail="Parent WBS not found")
    code = payload.code.strip()
    if not code or not payload.name.strip():
        raise HTTPException(status_code=400, detail="WBS code and name are required")
    existing = db.scalar(select(WBS).where(WBS.tenant_id == tenant_id, WBS.project_id == project_id, WBS.code == code))
    if existing:
        raise HTTPException(status_code=409, detail="WBS code already exists in this project")
    wbs = WBS(
        tenant_id=tenant_id,
        project_id=project_id,
        parent_id=payload.parent_id,
        code=code,
        name=payload.name.strip(),
        level=payload.level,
        description=payload.description.strip(),
        dictionary=payload.dictionary.strip(),
        responsible=payload.responsible.strip(),
        status=payload.status.strip().lower() or "draft",
    )
    db.add(wbs)
    db.flush()
    _audit(
        db, tenant_id, project_id, "create_wbs", "WBS", wbs.id, json.dumps({"code": wbs.code}), current_user.full_name
    )
    db.commit()
    db.refresh(wbs)
    return wbs


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
    if payload.awp_package_id is not None:
        _require_work_package(db, tenant_id, project_id, payload.awp_package_id)
    account = ControlAccount(
        tenant_id=tenant_id,
        project_id=project_id,
        wbs_id=wbs.id,
        awp_package_id=payload.awp_package_id,
        code=payload.code,
        name=payload.name,
        responsible=payload.responsible,
        discipline=payload.discipline,
        scope=payload.scope,
        budget=payload.budget,
        start_date=payload.start_date,
        finish_date=payload.finish_date,
        cbs_code=payload.cbs_code,
        contract_ref=payload.contract_ref,
        measurement_rule=payload.measurement_rule,
        earned_value=payload.earned_value,
        actual_cost=payload.actual_cost,
        forecast=payload.forecast,
        lifecycle_status=payload.lifecycle_status.strip().lower(),
        risk_ref=payload.risk_ref,
        closure_note=payload.closure_note,
    )
    _validate_control_account_status(account.lifecycle_status)
    db.add(account)
    db.flush()
    _audit(
        db,
        tenant_id,
        project_id,
        "create_control_account",
        "ControlAccount",
        account.id,
        f'{{"code":"{account.code}"}}',
    )
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
        if field == "lifecycle_status" and value is not None:
            value = value.strip().lower()
        if field == "wbs_id" and value is not None:
            wbs = db.scalar(
                select(WBS).where(WBS.id == value, WBS.tenant_id == tenant_id, WBS.project_id == project_id)
            )
            if not wbs:
                raise HTTPException(status_code=404, detail="WBS not found")
        if field == "awp_package_id" and value is not None:
            _require_work_package(db, tenant_id, project_id, value)
        setattr(account, field, value)
    _validate_control_account_status(account.lifecycle_status)
    _touch_collaborative_record(account)
    _audit(
        db,
        tenant_id,
        project_id,
        "update_control_account",
        "ControlAccount",
        account.id,
        f'{{"code":"{account.code}"}}',
    )
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
        raise HTTPException(
            status_code=409, detail="Cost loading coverage must be at least 80% before baseline approval"
        )
    baseline.status = "approved"
    _audit(
        db,
        tenant_id,
        project_id,
        "approve_control_baseline",
        "BaselineVersion",
        baseline.id,
        f'{{"mapping_score":{summary.mapping_score},"cost_loading_score":{summary.cost_loading_score}}}',
        current_user.full_name,
    )
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
    _audit(
        db,
        tenant_id,
        project_id,
        "capture_progress",
        "ProgressRecord",
        record.id,
        f'{{"control_account_id":{record.control_account_id}}}',
        current_user.full_name,
    )
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
        raise HTTPException(
            status_code=400,
            detail="Commitments are created from contracts or purchase orders, not from actual cost records",
        )
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
    _audit(
        db,
        tenant_id,
        project_id,
        "capture_actual_cost",
        "CostRecord",
        record.id,
        f'{{"control_account_id":{record.control_account_id},"amount":{record.amount}}}',
        current_user.full_name,
    )
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
    amount = payload.amount if payload.amount is not None else payload.approved_amount
    amount = float(amount or 0)
    funding_name = payload.name.strip() or payload.source_of_funds.strip() or payload.code.strip()
    if not payload.code.strip() or not funding_name:
        raise HTTPException(status_code=400, detail="Funding code and name are required")
    if amount < 0:
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
        name=funding_name,
        source_of_funds=payload.source_of_funds.strip(),
        funding_type=payload.funding_type.strip(),
        authorization_ref=payload.authorization_ref.strip(),
        usage_restrictions=payload.usage_restrictions.strip(),
        usage_rules=payload.usage_rules.strip(),
        amount=amount,
        funds_available=amount,
        funds_committed=0,
        funds_executed=0,
        currency=(payload.currency or project.currency).upper(),
        status=payload.status.strip() or "approved",
    )
    db.add(funding)
    db.flush()
    _audit(
        db,
        tenant_id,
        project_id,
        "create_funding_source",
        "FundingSource",
        funding.id,
        json.dumps({"code": funding.code, "amount": funding.amount}),
        current_user.full_name,
    )
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
    amount = payload.amount if payload.amount is not None else payload.approved_amount
    if amount is not None and amount < 0:
        raise HTTPException(status_code=400, detail="Funding amount cannot be negative")
    for field in (
        "name",
        "source_of_funds",
        "funding_type",
        "authorization_ref",
        "usage_restrictions",
        "usage_rules",
        "currency",
        "status",
    ):
        value = getattr(payload, field)
        if value is not None:
            setattr(funding, field, value.strip() if isinstance(value, str) else value)
    if amount is not None:
        funding.amount = amount
    IntegratedControlService(db).refresh_funding_balance(tenant_id, project_id, funding)
    if funding.currency:
        funding.currency = funding.currency.upper()
    _touch_collaborative_record(funding)
    _audit(
        db,
        tenant_id,
        project_id,
        "update_funding_source",
        "FundingSource",
        funding.id,
        f'{{"version":{funding.version}}}',
        current_user.full_name,
    )
    db.commit()
    db.refresh(funding)
    return funding


@router.get("/projects/{project_id}/fbs", response_model=list[FundingSourceOut])
def list_fbs(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[FundingSource]:
    _require_project(db, tenant_id, project_id)
    _require_membership(db, tenant_id, project_id, user_id)
    service = IntegratedControlService(db)
    sources = _funding_sources(db, tenant_id, project_id)
    for source in sources:
        service.refresh_funding_balance(tenant_id, project_id, source)
    return sources


@router.post("/projects/{project_id}/fbs", response_model=FundingSourceOut)
def create_fbs(
    project_id: int,
    payload: FundingSourceCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> FundingSource:
    return create_funding_source(project_id, payload, db, tenant_id, user_id)


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
    _audit(
        db,
        tenant_id,
        project_id,
        "create_cash_flow_period",
        "CashFlowPeriod",
        period.id,
        f'{{"period_label":"{period.period_label}"}}',
        current_user.full_name,
    )
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
    _audit(
        db,
        tenant_id,
        project_id,
        "update_cash_flow_period",
        "CashFlowPeriod",
        period.id,
        f'{{"version":{period.version}}}',
        current_user.full_name,
    )
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


@router.get("/projects/{project_id}/cbs", response_model=list[CostBreakdownStructureOut])
def list_cbs(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[CostBreakdownStructure]:
    _require_project(db, tenant_id, project_id)
    _require_membership(db, tenant_id, project_id, user_id)
    return list(
        db.scalars(
            select(CostBreakdownStructure)
            .where(CostBreakdownStructure.tenant_id == tenant_id, CostBreakdownStructure.project_id == project_id)
            .order_by(CostBreakdownStructure.code)
        ).all()
    )


@router.post("/projects/{project_id}/cbs", response_model=CostBreakdownStructureOut)
def create_cbs(
    project_id: int,
    payload: CostBreakdownStructureCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> CostBreakdownStructure:
    _require_project(db, tenant_id, project_id)
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_capture_cost", "Current role cannot configure CBS")
    current_user = _require_user(db, tenant_id, user_id)
    if payload.parent_id is not None:
        parent = db.scalar(
            select(CostBreakdownStructure).where(
                CostBreakdownStructure.tenant_id == tenant_id,
                CostBreakdownStructure.project_id == project_id,
                CostBreakdownStructure.id == payload.parent_id,
            )
        )
        if not parent:
            raise HTTPException(status_code=404, detail="Parent CBS not found")
    code = payload.code.strip()
    if not code:
        raise HTTPException(status_code=400, detail="CBS code is required")
    existing = db.scalar(
        select(CostBreakdownStructure).where(
            CostBreakdownStructure.tenant_id == tenant_id,
            CostBreakdownStructure.project_id == project_id,
            CostBreakdownStructure.code == code,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="CBS code already exists in this project")
    cbs = CostBreakdownStructure(
        tenant_id=tenant_id,
        project_id=project_id,
        parent_id=payload.parent_id,
        code=code,
        level=payload.level,
        cost_category=payload.cost_category.strip(),
        description=payload.description.strip(),
        status=payload.status.strip().lower() or "draft",
    )
    db.add(cbs)
    db.flush()
    _audit(
        db,
        tenant_id,
        project_id,
        "create_cbs",
        "CostBreakdownStructure",
        cbs.id,
        json.dumps({"code": cbs.code}),
        current_user.full_name,
    )
    db.commit()
    db.refresh(cbs)
    return cbs


@router.get("/projects/{project_id}/cost-codes", response_model=list[CostCodeOut])
def list_cost_codes(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[CostCode]:
    _require_project(db, tenant_id, project_id)
    _require_membership(db, tenant_id, project_id, user_id)
    return list(
        db.scalars(
            select(CostCode)
            .where(CostCode.tenant_id == tenant_id, CostCode.project_id == project_id)
            .order_by(CostCode.code)
        ).all()
    )


@router.post("/projects/{project_id}/cost-codes", response_model=CostCodeOut)
def create_cost_code(
    project_id: int,
    payload: CostCodeCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> CostCode:
    _require_project(db, tenant_id, project_id)
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_capture_cost", "Current role cannot configure cost codes")
    current_user = _require_user(db, tenant_id, user_id)
    wbs = db.scalar(
        select(WBS).where(WBS.tenant_id == tenant_id, WBS.project_id == project_id, WBS.id == payload.wbs_id)
    )
    if not wbs:
        raise HTTPException(status_code=404, detail="WBS not found")
    account = _require_control_account(db, tenant_id, project_id, payload.control_account_id)
    cbs = db.scalar(
        select(CostBreakdownStructure).where(
            CostBreakdownStructure.tenant_id == tenant_id,
            CostBreakdownStructure.project_id == project_id,
            CostBreakdownStructure.id == payload.cbs_id,
        )
    )
    if not cbs:
        raise HTTPException(status_code=404, detail="CBS not found")
    fbs = IntegratedControlService(db).require_funding_source(tenant_id, project_id, payload.fbs_id)
    if cbs.code == fbs.code:
        raise HTTPException(status_code=400, detail="FBS cannot be used as a CBS substitute")
    code = payload.code.strip()
    if not code:
        raise HTTPException(status_code=400, detail="Cost code is required")
    existing = db.scalar(
        select(CostCode).where(
            CostCode.tenant_id == tenant_id, CostCode.project_id == project_id, CostCode.code == code
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Cost code already exists in this project")
    cost_code = CostCode(
        tenant_id=tenant_id,
        project_id=project_id,
        wbs_id=wbs.id,
        control_account_id=account.id,
        cbs_id=cbs.id,
        fbs_id=fbs.id,
        contract_ref=payload.contract_ref.strip(),
        code=code,
        budget=payload.budget,
        funds_available=payload.funds_available,
        commitments=payload.commitments,
        actual_costs=payload.actual_costs,
        forecast=payload.forecast,
        status=payload.status.strip().lower() or "draft",
    )
    db.add(cost_code)
    db.flush()
    _audit(
        db,
        tenant_id,
        project_id,
        "create_cost_code",
        "CostCode",
        cost_code.id,
        json.dumps({"code": cost_code.code}),
        current_user.full_name,
    )
    db.commit()
    db.refresh(cost_code)
    return cost_code


@router.post("/projects/{project_id}/business-processes/cbs-fund", response_model=BusinessProcessInstanceOut)
def create_cbs_fund_business_process(
    project_id: int,
    payload: BusinessProcessCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> BusinessProcessInstance:
    _require_project(db, tenant_id, project_id)
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_capture_cost", "Current role cannot allocate CBS funding")
    current_user = _require_user(db, tenant_id, user_id)
    if not payload.line_items:
        raise HTTPException(status_code=400, detail="At least one CBS funding line item is required")

    service = IntegratedControlService(db)
    funding_totals: dict[int, float] = {}
    funding_by_id: dict[int, FundingSource] = {}
    validated: list[tuple[object, CostBreakdownStructure, FundingSource, ControlAccount | None]] = []
    for line in payload.line_items:
        if line.funding_source_id is None:
            raise HTTPException(status_code=400, detail="FBS funding source is required for CBS funding")
        if line.amount <= 0:
            raise HTTPException(status_code=400, detail="CBS funding amount must be greater than zero")
        cbs = _require_cbs(db, tenant_id, project_id, line.cbs_id)
        funding = service.require_funding_source(tenant_id, project_id, line.funding_source_id)
        account = (
            _require_control_account(db, tenant_id, project_id, line.control_account_id)
            if line.control_account_id is not None
            else None
        )
        funding_totals[funding.id] = funding_totals.get(funding.id, 0.0) + float(line.amount)
        funding_by_id[funding.id] = funding
        validated.append((line, cbs, funding, account))

    for funding_id, total_amount in funding_totals.items():
        service.ensure_available(tenant_id, project_id, funding_by_id[funding_id], total_amount)

    process = _start_business_process(
        db,
        tenant_id,
        project_id,
        trigger_entity_type="Project",
        trigger_entity_id=project_id,
        process_code="BP-CBS-FUND",
        process_name="CBS + Fund Code",
        record_no=f"BP-CBS-FUND-{uuid4().hex[:8].upper()}",
        title=payload.title.strip() or "CBS + Fund Code",
        current_step="Control Review",
        ball_in_court="Project Controls",
        steps=[
            (
                "Creation",
                "CBS funding lines were captured from the cost form.",
                "Cost Engineer",
                "Complete",
                "complete",
            ),
            (
                "Control Review",
                "Validate FBS availability and control account funding split.",
                "Project Controls",
                "Active",
                "active",
            ),
            ("Approval", "Approve the funding allocation for execution.", "Control Manager", "Queued", "queued"),
        ],
    )
    for line, cbs, funding, account in validated:
        db.add(
            BusinessProcessLineItem(
                tenant_id=tenant_id,
                project_id=project_id,
                process_instance_id=process.id,
                line_type="cbs_fund",
                cbs_id=cbs.id,
                funding_source_id=funding.id,
                control_account_id=account.id if account else None,
                amount=line.amount,
                quantity=line.quantity,
                description=line.description.strip(),
            )
        )
        if account:
            allocation = db.scalar(
                select(ControlAccountFundingAllocation).where(
                    ControlAccountFundingAllocation.tenant_id == tenant_id,
                    ControlAccountFundingAllocation.project_id == project_id,
                    ControlAccountFundingAllocation.control_account_id == account.id,
                    ControlAccountFundingAllocation.funding_source_id == funding.id,
                )
            )
            if allocation:
                allocation.allocated_amount = _money(allocation.allocated_amount + line.amount)
                allocation.forecast_amount = _money(allocation.forecast_amount + line.amount)
                _touch_collaborative_record(allocation)
            else:
                db.add(
                    ControlAccountFundingAllocation(
                        tenant_id=tenant_id,
                        project_id=project_id,
                        control_account_id=account.id,
                        funding_source_id=funding.id,
                        allocated_amount=line.amount,
                        forecast_amount=line.amount,
                        distribution_note=f"CBS {cbs.code}",
                        status="active",
                    )
                )

    _audit(
        db,
        tenant_id,
        project_id,
        "create_bp_cbs_fund",
        "BusinessProcessInstance",
        process.id,
        json.dumps({"line_count": len(validated)}),
        current_user.full_name,
    )
    db.commit()
    db.refresh(process)
    return process


@router.post("/projects/{project_id}/business-processes/cbs-wbs", response_model=BusinessProcessInstanceOut)
def create_cbs_wbs_business_process(
    project_id: int,
    payload: BusinessProcessCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> BusinessProcessInstance:
    _require_project(db, tenant_id, project_id)
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_capture_cost", "Current role cannot create CBS/WBS transactions")
    current_user = _require_user(db, tenant_id, user_id)
    if not payload.line_items:
        raise HTTPException(status_code=400, detail="At least one CBS/WBS line item is required")

    service = IntegratedControlService(db)
    funding_totals: dict[int, float] = {}
    funding_by_id: dict[int, FundingSource] = {}
    validated: list[tuple[object, WBS, CostBreakdownStructure, FundingSource, ControlAccount]] = []
    for line in payload.line_items:
        if line.wbs_id is None:
            raise HTTPException(status_code=400, detail="WBS is required for CBS/WBS transactions")
        if line.funding_source_id is None:
            raise HTTPException(status_code=400, detail="FBS funding source is required for CBS/WBS transactions")
        if line.control_account_id is None:
            raise HTTPException(status_code=400, detail="Control account is required for CBS/WBS transactions")
        if line.amount <= 0:
            raise HTTPException(status_code=400, detail="CBS/WBS amount must be greater than zero")
        wbs = _require_wbs(db, tenant_id, project_id, line.wbs_id)
        cbs = _require_cbs(db, tenant_id, project_id, line.cbs_id)
        funding = service.require_funding_source(tenant_id, project_id, line.funding_source_id)
        account = _require_control_account(db, tenant_id, project_id, line.control_account_id)
        if account.wbs_id != wbs.id:
            raise HTTPException(status_code=400, detail="Control account must belong to the selected WBS")
        funding_totals[funding.id] = funding_totals.get(funding.id, 0.0) + float(line.amount)
        funding_by_id[funding.id] = funding
        validated.append((line, wbs, cbs, funding, account))

    for funding_id, total_amount in funding_totals.items():
        service.ensure_available(tenant_id, project_id, funding_by_id[funding_id], total_amount)

    process = _start_business_process(
        db,
        tenant_id,
        project_id,
        trigger_entity_type="Project",
        trigger_entity_id=project_id,
        process_code="BP-CBS-WBS",
        process_name="CBS + WBS Code",
        record_no=f"BP-CBS-WBS-{uuid4().hex[:8].upper()}",
        title=payload.title.strip() or "CBS + WBS Code",
        current_step="Budget Review",
        ball_in_court="Project Controls",
        steps=[
            ("Creation", "Cost-scope line items were captured.", "Cost Engineer", "Complete", "complete"),
            (
                "Budget Review",
                "Validate WBS, CBS, FBS and control account alignment.",
                "Project Controls",
                "Active",
                "active",
            ),
            ("Approval", "Approve dual WBS/CBS roll-up to cost codes.", "Control Manager", "Queued", "queued"),
        ],
    )
    for line, wbs, cbs, funding, account in validated:
        code = _cost_code_from_parts(wbs.code, account.code, cbs.code)
        cost_code = db.scalar(
            select(CostCode).where(
                CostCode.tenant_id == tenant_id,
                CostCode.project_id == project_id,
                CostCode.code == code,
            )
        )
        if cost_code:
            cost_code.budget = _money(cost_code.budget + line.amount)
            cost_code.funds_available = _money(cost_code.funds_available + line.amount)
            cost_code.forecast = _money(cost_code.forecast + line.amount)
            cost_code.status = "active"
            _touch_collaborative_record(cost_code)
        else:
            cost_code = CostCode(
                tenant_id=tenant_id,
                project_id=project_id,
                wbs_id=wbs.id,
                control_account_id=account.id,
                cbs_id=cbs.id,
                fbs_id=funding.id,
                contract_ref=account.contract_ref or "",
                code=code,
                budget=line.amount,
                funds_available=line.amount,
                forecast=line.amount,
                status="active",
            )
            db.add(cost_code)
            db.flush()
        budget = db.scalar(
            select(Budget).where(
                Budget.tenant_id == tenant_id,
                Budget.project_id == project_id,
                Budget.control_account_id == account.id,
                Budget.cbs_code == cbs.code,
            )
        )
        if budget:
            budget.bac = _money(budget.bac + line.amount)
            budget.cost_loaded_pv = _money(budget.cost_loaded_pv + line.amount)
        else:
            db.add(
                Budget(
                    tenant_id=tenant_id,
                    project_id=project_id,
                    control_account_id=account.id,
                    cbs_code=cbs.code,
                    bac=line.amount,
                    cost_loaded_pv=line.amount,
                )
            )
        account.budget = _money(account.budget + line.amount)
        account.forecast = _money(account.forecast + line.amount)
        if not account.cbs_code:
            account.cbs_code = cbs.code
        db.add(
            BusinessProcessLineItem(
                tenant_id=tenant_id,
                project_id=project_id,
                process_instance_id=process.id,
                line_type="cbs_wbs",
                wbs_id=wbs.id,
                cbs_id=cbs.id,
                funding_source_id=funding.id,
                control_account_id=account.id,
                cost_code_id=cost_code.id,
                amount=line.amount,
                quantity=line.quantity,
                description=line.description.strip(),
            )
        )

    _audit(
        db,
        tenant_id,
        project_id,
        "create_bp_cbs_wbs",
        "BusinessProcessInstance",
        process.id,
        json.dumps({"line_count": len(validated)}),
        current_user.full_name,
    )
    db.commit()
    db.refresh(process)
    return process


@router.get("/projects/{project_id}/business-process-policies", response_model=list[BusinessProcessPolicyOut])
def list_business_process_policies(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[BusinessProcessPolicy]:
    _require_project(db, tenant_id, project_id)
    _require_membership(db, tenant_id, project_id, user_id)
    return list(
        db.scalars(
            select(BusinessProcessPolicy)
            .where(BusinessProcessPolicy.tenant_id == tenant_id, BusinessProcessPolicy.project_id == project_id)
            .order_by(BusinessProcessPolicy.process_code, BusinessProcessPolicy.action)
        ).all()
    )


@router.post("/projects/{project_id}/business-process-policies", response_model=BusinessProcessPolicyOut)
def upsert_business_process_policy(
    project_id: int,
    payload: BusinessProcessPolicyCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> BusinessProcessPolicy:
    _require_project(db, tenant_id, project_id)
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_configure", "Current role cannot configure business process policies")
    current_user = _require_user(db, tenant_id, user_id)
    process_code = payload.process_code.strip()
    action = payload.action.strip().lower()
    if not process_code or not action:
        raise HTTPException(status_code=400, detail="Process code and action are required")
    policy = db.scalar(
        select(BusinessProcessPolicy).where(
            BusinessProcessPolicy.tenant_id == tenant_id,
            BusinessProcessPolicy.project_id == project_id,
            BusinessProcessPolicy.process_code == process_code,
            BusinessProcessPolicy.action == action,
        )
    )
    details = {
        "process_code": process_code,
        "action": action,
        "required_role": payload.required_role.strip(),
        "permission_key": payload.permission_key.strip(),
        "status": payload.status.strip().lower() or "active",
    }
    if policy:
        policy.required_role = details["required_role"]
        policy.permission_key = details["permission_key"]
        policy.status = details["status"]
        policy.version += 1
        policy.updated_at = utc_now()
        action_name = "update_business_process_policy"
    else:
        policy = BusinessProcessPolicy(
            tenant_id=tenant_id,
            project_id=project_id,
            process_code=process_code,
            action=action,
            required_role=details["required_role"],
            permission_key=details["permission_key"],
            status=details["status"],
        )
        db.add(policy)
        db.flush()
        action_name = "create_business_process_policy"
    _audit(
        db,
        tenant_id,
        project_id,
        action_name,
        "BusinessProcessPolicy",
        policy.id,
        json.dumps(details),
        current_user.full_name,
    )
    db.commit()
    db.refresh(policy)
    return policy


@router.get(
    "/projects/{project_id}/business-processes/{process_id}/line-items",
    response_model=list[BusinessProcessLineItemOut],
)
def list_business_process_line_items(
    project_id: int,
    process_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[BusinessProcessLineItemOut]:
    _require_membership(db, tenant_id, project_id, user_id)
    _require_business_process(db, tenant_id, project_id, process_id)
    lines = list(
        db.scalars(
            select(BusinessProcessLineItem)
            .where(
                BusinessProcessLineItem.tenant_id == tenant_id,
                BusinessProcessLineItem.project_id == project_id,
                BusinessProcessLineItem.process_instance_id == process_id,
            )
            .order_by(BusinessProcessLineItem.id)
        ).all()
    )
    return [_business_process_line_item_out(db, tenant_id, project_id, line) for line in lines]


@router.patch(
    "/projects/{project_id}/business-process-line-items/{line_item_id}",
    response_model=BusinessProcessLineItemOut,
)
def update_business_process_line_item(
    project_id: int,
    line_item_id: int,
    payload: BusinessProcessLineItemUpdate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> BusinessProcessLineItemOut:
    _require_project(db, tenant_id, project_id)
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_capture_cost", "Current role cannot edit business process line items")
    current_user = _require_user(db, tenant_id, user_id)
    line = _require_business_process_line_item(db, tenant_id, project_id, line_item_id)
    current_version = _business_process_line_item_version(db, tenant_id, project_id, line.id)
    if payload.expected_version is not None and payload.expected_version != current_version:
        raise HTTPException(status_code=409, detail="Business process line item has changed")
    if payload.amount is not None and payload.amount < 0:
        raise HTTPException(status_code=400, detail="Amount cannot be negative")
    if payload.quantity is not None and payload.quantity < 0:
        raise HTTPException(status_code=400, detail="Quantity cannot be negative")

    previous_amount = float(line.amount or 0)
    previous_quantity = float(line.quantity or 0)
    previous_description = line.description or ""
    previous_status = line.status or ""
    if payload.amount is not None:
        line.amount = payload.amount
    if payload.quantity is not None:
        line.quantity = payload.quantity
    if payload.description is not None:
        line.description = payload.description.strip()
    if payload.status is not None:
        line.status = payload.status.strip().lower() or "active"
    line.updated_at = utc_now()
    next_version = current_version + 1

    revision = BusinessProcessLineItemRevision(
        tenant_id=tenant_id,
        project_id=project_id,
        line_item_id=line.id,
        process_instance_id=line.process_instance_id,
        previous_version=current_version,
        new_version=next_version,
        previous_amount=previous_amount,
        new_amount=float(line.amount or 0),
        previous_quantity=previous_quantity,
        new_quantity=float(line.quantity or 0),
        previous_description=previous_description,
        new_description=line.description or "",
        previous_status=previous_status,
        new_status=line.status or "",
        change_note=payload.change_note.strip(),
        changed_by=current_user.full_name,
    )
    db.add(revision)
    if line.cost_code_id and payload.amount is not None:
        cost_code = db.scalar(
            select(CostCode).where(
                CostCode.tenant_id == tenant_id,
                CostCode.project_id == project_id,
                CostCode.id == line.cost_code_id,
            )
        )
        if cost_code:
            amount_delta = float(line.amount or 0) - previous_amount
            cost_code.budget = _money(cost_code.budget + amount_delta)
            cost_code.funds_available = _money(cost_code.funds_available + amount_delta)
            cost_code.forecast = _money(cost_code.forecast + amount_delta)
            _touch_collaborative_record(cost_code)
    _audit(
        db,
        tenant_id,
        project_id,
        "update_business_process_line_item",
        "BusinessProcessLineItem",
        line.id,
        json.dumps({"previous_version": current_version, "new_version": next_version}),
        current_user.full_name,
    )
    db.commit()
    db.refresh(line)
    return _business_process_line_item_out(db, tenant_id, project_id, line)


@router.get(
    "/projects/{project_id}/business-process-line-items/{line_item_id}/revisions",
    response_model=list[BusinessProcessLineItemRevisionOut],
)
def list_business_process_line_item_revisions(
    project_id: int,
    line_item_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[BusinessProcessLineItemRevision]:
    _require_membership(db, tenant_id, project_id, user_id)
    _require_business_process_line_item(db, tenant_id, project_id, line_item_id)
    return list(
        db.scalars(
            select(BusinessProcessLineItemRevision)
            .where(
                BusinessProcessLineItemRevision.tenant_id == tenant_id,
                BusinessProcessLineItemRevision.project_id == project_id,
                BusinessProcessLineItemRevision.line_item_id == line_item_id,
            )
            .order_by(BusinessProcessLineItemRevision.new_version)
        ).all()
    )


@router.post(
    "/projects/{project_id}/control-account-funding-allocations",
    response_model=ControlAccountFundingAllocationOut,
)
def create_control_account_funding_allocation(
    project_id: int,
    payload: ControlAccountFundingAllocationCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ControlAccountFundingAllocation:
    _require_project(db, tenant_id, project_id)
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_capture_cost", "Current role cannot configure funding allocations")
    current_user = _require_user(db, tenant_id, user_id)
    account = _require_control_account(db, tenant_id, project_id, payload.control_account_id)
    funding = IntegratedControlService(db).require_funding_source(tenant_id, project_id, payload.funding_source_id)
    existing = db.scalar(
        select(ControlAccountFundingAllocation).where(
            ControlAccountFundingAllocation.tenant_id == tenant_id,
            ControlAccountFundingAllocation.project_id == project_id,
            ControlAccountFundingAllocation.control_account_id == account.id,
            ControlAccountFundingAllocation.funding_source_id == funding.id,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Control account already has this FBS allocation")
    allocation = ControlAccountFundingAllocation(
        tenant_id=tenant_id,
        project_id=project_id,
        control_account_id=account.id,
        funding_source_id=funding.id,
        allocated_amount=payload.allocated_amount,
        committed_amount=payload.committed_amount,
        actual_amount=payload.actual_amount,
        forecast_amount=payload.forecast_amount,
        distribution_note=payload.distribution_note.strip(),
        status=payload.status.strip().lower() or "active",
    )
    db.add(allocation)
    db.flush()
    _audit(
        db,
        tenant_id,
        project_id,
        "create_control_account_funding_allocation",
        "ControlAccountFundingAllocation",
        allocation.id,
        json.dumps({"control_account_id": account.id, "funding_source_id": funding.id}),
        current_user.full_name,
    )
    db.commit()
    db.refresh(allocation)
    return allocation


@router.get("/projects/{project_id}/integrated-control-matrix", response_model=list[IntegratedControlMatrixRow])
def get_integrated_control_matrix(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[IntegratedControlMatrixRow]:
    _require_project(db, tenant_id, project_id)
    _require_membership(db, tenant_id, project_id, user_id)
    return IntegratedControlService(db).matrix(tenant_id, project_id)


@router.get("/projects/{project_id}/funding-availability-check", response_model=FundingAvailabilityOut)
def get_funding_availability_check(
    project_id: int,
    funding_source_id: int,
    requested_amount: float = 0,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> FundingAvailabilityOut:
    _require_project(db, tenant_id, project_id)
    _require_membership(db, tenant_id, project_id, user_id)
    return IntegratedControlService(db).availability(tenant_id, project_id, funding_source_id, requested_amount)


@router.get("/projects/{project_id}/forecast-vs-funding-report", response_model=ForecastFundingReport)
def get_forecast_vs_funding_report(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ForecastFundingReport:
    _require_project(db, tenant_id, project_id)
    _require_membership(db, tenant_id, project_id, user_id)
    return IntegratedControlService(db).forecast_report(tenant_id, project_id)


@router.post("/projects/{project_id}/baseline-approval", response_model=BaselineApprovalOut)
def approve_integrated_baseline(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> BaselineApprovalOut:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_approve_workflow", "Current role cannot approve the integrated baseline")
    result = IntegratedControlService(db).approve_baseline(tenant_id, project_id)
    _audit(
        db, tenant_id, project_id, "approve_integrated_baseline", "Project", project_id, json.dumps(result.model_dump())
    )
    db.commit()
    return result


@router.get("/projects/{project_id}/closeout-report", response_model=CloseoutReportOut)
def get_closeout_report(
    project_id: int,
    funding_source_id: int | None = None,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> CloseoutReportOut:
    _require_project(db, tenant_id, project_id)
    _require_membership(db, tenant_id, project_id, user_id)
    return IntegratedControlService(db).closeout_report(tenant_id, project_id, funding_source_id)


@router.post("/projects/{project_id}/financial-closeout", response_model=CloseoutReportOut)
def close_financial_funding(
    project_id: int,
    funding_source_id: int | None = None,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> CloseoutReportOut:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_capture_cost", "Current role cannot close financial funding")
    result = IntegratedControlService(db).financial_closeout(tenant_id, project_id, funding_source_id)
    _audit(
        db,
        tenant_id,
        project_id,
        "financial_closeout",
        "FundingSource",
        funding_source_id,
        json.dumps(result.model_dump()),
    )
    db.commit()
    return result


@router.get("/projects/{project_id}/rate-sheets", response_model=list[RateSheetOut])
def list_rate_sheets(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[RateSheetOut]:
    _require_project(db, tenant_id, project_id)
    _require_membership(db, tenant_id, project_id, user_id)
    sheets = list(
        db.scalars(
            select(RateSheet)
            .where(RateSheet.tenant_id == tenant_id, RateSheet.project_id == project_id)
            .order_by(RateSheet.code)
        ).all()
    )
    return [_rate_sheet_out(db, tenant_id, project_id, sheet) for sheet in sheets]


@router.post("/projects/{project_id}/rate-sheets", response_model=RateSheetOut)
def create_rate_sheet(
    project_id: int,
    payload: RateSheetCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> RateSheetOut:
    _require_project(db, tenant_id, project_id)
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_capture_cost", "Current role cannot manage rate sheets")
    current_user = _require_user(db, tenant_id, user_id)
    code = payload.code.strip()
    if not code:
        raise HTTPException(status_code=400, detail="Rate sheet code is required")
    if not payload.line_items:
        raise HTTPException(status_code=400, detail="At least one rate sheet line is required")
    existing = db.scalar(
        select(RateSheet).where(
            RateSheet.tenant_id == tenant_id, RateSheet.project_id == project_id, RateSheet.code == code
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Rate sheet code already exists in this project")
    sheet = RateSheet(
        tenant_id=tenant_id,
        project_id=project_id,
        code=code,
        name=payload.name.strip() or code,
        status=payload.status.strip().lower() or "draft",
    )
    db.add(sheet)
    db.flush()
    seen_codes: set[str] = set()
    for line in payload.line_items:
        cbs_code = line.cbs_code.strip()
        if not cbs_code:
            raise HTTPException(status_code=400, detail="Rate sheet CBS code is required")
        if cbs_code in seen_codes:
            raise HTTPException(status_code=409, detail="Rate sheet cannot contain duplicate CBS codes")
        if line.multiplier <= 0:
            raise HTTPException(status_code=400, detail="Rate sheet multiplier must be greater than zero")
        if line.unit_rate < 0:
            raise HTTPException(status_code=400, detail="Rate sheet unit rate cannot be negative")
        seen_codes.add(cbs_code)
        db.add(
            RateSheetLine(
                tenant_id=tenant_id,
                project_id=project_id,
                rate_sheet_id=sheet.id,
                cbs_code=cbs_code,
                unit_rate=line.unit_rate,
                multiplier=line.multiplier,
                status=line.status.strip().lower() or "active",
            )
        )
    db.flush()
    _audit(
        db,
        tenant_id,
        project_id,
        "create_rate_sheet",
        "RateSheet",
        sheet.id,
        json.dumps({"code": sheet.code, "line_count": len(payload.line_items)}),
        current_user.full_name,
    )
    db.commit()
    db.refresh(sheet)
    return _rate_sheet_out(db, tenant_id, project_id, sheet)


@router.post(
    "/projects/{project_id}/activity-sheets/{activity_sheet_id}/recost",
    response_model=ActivitySheetRecostOut,
)
def recost_activity_sheet(
    project_id: int,
    activity_sheet_id: int,
    payload: ActivitySheetRecostIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ActivitySheetRecostOut:
    _require_project(db, tenant_id, project_id)
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_capture_cost", "Current role cannot recost activity sheets")
    current_user = _require_user(db, tenant_id, user_id)
    activity_sheet = _require_activity_sheet(db, tenant_id, project_id, activity_sheet_id)
    rate_sheet = _require_rate_sheet(db, tenant_id, project_id, payload.rate_sheet_id)
    rate_lines = list(
        db.scalars(
            select(RateSheetLine).where(
                RateSheetLine.tenant_id == tenant_id,
                RateSheetLine.project_id == project_id,
                RateSheetLine.rate_sheet_id == rate_sheet.id,
                RateSheetLine.status == "active",
            )
        ).all()
    )
    rates_by_cbs_code = {line.cbs_code: line for line in rate_lines}
    mappings_by_external_id = _activity_sheet_mappings_by_external_id(db, tenant_id, project_id, activity_sheet)
    updated_rows = 0
    total_planned_cost = 0.0
    total_planned_value = 0.0
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
    next_run_no = (
        int(
            db.scalar(
                select(func.coalesce(func.max(ActivitySheetRecostRun.run_no), 0)).where(
                    ActivitySheetRecostRun.tenant_id == tenant_id,
                    ActivitySheetRecostRun.project_id == project_id,
                    ActivitySheetRecostRun.activity_sheet_id == activity_sheet.id,
                )
            )
            or 0
        )
        + 1
    )
    recost_run = ActivitySheetRecostRun(
        tenant_id=tenant_id,
        project_id=project_id,
        activity_sheet_id=activity_sheet.id,
        rate_sheet_id=rate_sheet.id,
        run_no=next_run_no,
        created_by=current_user.full_name,
    )
    db.add(recost_run)
    db.flush()
    for row in activity_rows:
        mapping = mappings_by_external_id.get(row.external_activity_id)
        rate = rates_by_cbs_code.get(mapping.cbs_code) if mapping else None
        if not mapping or not rate:
            total_planned_cost += float(row.planned_cost or 0)
            total_planned_value += float(mapping.planned_value if mapping else 0)
            continue
        previous_cost = float(row.planned_cost or 0)
        previous_value = float(mapping.planned_value or 0)
        base_cost = float(row.planned_cost or mapping.planned_cost or 0)
        new_cost = _money(base_cost * rate.multiplier if base_cost else rate.unit_rate * rate.multiplier)
        new_value = _money(new_cost * float(mapping.planned_percent or 0) / 100)
        row.planned_cost = new_cost
        mapping.planned_cost = new_cost
        mapping.planned_value = new_value
        mapping.review_note = f"Recosted with rate sheet {rate_sheet.code}"
        db.add(
            ActivitySheetRecostRunLine(
                tenant_id=tenant_id,
                project_id=project_id,
                recost_run_id=recost_run.id,
                activity_sheet_row_id=row.id,
                external_activity_id=row.external_activity_id,
                cbs_code=mapping.cbs_code,
                previous_planned_cost=_money(previous_cost),
                new_planned_cost=new_cost,
                previous_planned_value=_money(previous_value),
                new_planned_value=new_value,
            )
        )
        updated_rows += 1
        total_planned_cost += new_cost
        total_planned_value += new_value
    recost_run.updated_rows = updated_rows
    recost_run.total_planned_cost = _money(total_planned_cost)
    recost_run.total_planned_value = _money(total_planned_value)
    activity_sheet.updated_at = utc_now()
    _audit(
        db,
        tenant_id,
        project_id,
        "recost_activity_sheet",
        "ActivitySheet",
        activity_sheet.id,
        json.dumps({"rate_sheet_id": rate_sheet.id, "updated_rows": updated_rows}),
        current_user.full_name,
    )
    db.commit()
    return ActivitySheetRecostOut(
        project_id=project_id,
        activity_sheet_id=activity_sheet.id,
        rate_sheet_id=rate_sheet.id,
        recost_run_id=recost_run.id,
        updated_rows=updated_rows,
        total_planned_cost=_money(total_planned_cost),
        total_planned_value=_money(total_planned_value),
    )


@router.get(
    "/projects/{project_id}/activity-sheets/{activity_sheet_id}/recost-runs",
    response_model=list[ActivitySheetRecostRunOut],
)
def list_activity_sheet_recost_runs(
    project_id: int,
    activity_sheet_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ActivitySheetRecostRunOut]:
    _require_project(db, tenant_id, project_id)
    _require_membership(db, tenant_id, project_id, user_id)
    _require_activity_sheet(db, tenant_id, project_id, activity_sheet_id)
    runs = list(
        db.scalars(
            select(ActivitySheetRecostRun)
            .where(
                ActivitySheetRecostRun.tenant_id == tenant_id,
                ActivitySheetRecostRun.project_id == project_id,
                ActivitySheetRecostRun.activity_sheet_id == activity_sheet_id,
            )
            .order_by(ActivitySheetRecostRun.run_no.desc())
        ).all()
    )
    return [_recost_run_out(db, tenant_id, project_id, run) for run in runs]


@router.get("/projects/{project_id}/reconciliation-report", response_model=ReconciliationReportOut)
def get_reconciliation_report(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ReconciliationReportOut:
    _require_project(db, tenant_id, project_id)
    _require_membership(db, tenant_id, project_id, user_id)
    return ReconciliationReportOut(project_id=project_id, rows=_reconciliation_report_rows(db, tenant_id, project_id))


@router.get("/projects/{project_id}/reconciliation-report/export")
def export_reconciliation_report(
    project_id: int,
    format: str = Query(default="xlsx"),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> Response:
    _require_project(db, tenant_id, project_id)
    _require_membership(db, tenant_id, project_id, user_id)
    rows = _reconciliation_report_rows(db, tenant_id, project_id)
    normalized = format.strip().lower()
    if normalized in {"xlsx", "excel"}:
        return Response(
            content=_reconciliation_xlsx_bytes(rows),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="reconciliation-project-{project_id}.xlsx"'},
        )
    if normalized == "pdf":
        return Response(
            content=_reconciliation_pdf_bytes(project_id, rows),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="reconciliation-project-{project_id}.pdf"'},
        )
    raise HTTPException(status_code=400, detail="Unsupported export format")


@router.post("/projects/{project_id}/agents/control-audit/run", response_model=ControlAgentRunOut)
def run_control_audit_agent(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ControlAgentRunOut:
    _require_project(db, tenant_id, project_id)
    _require_membership(db, tenant_id, project_id, user_id)
    current_user = _require_user(db, tenant_id, user_id)
    run = ControlAuditAgentService(db).run(tenant_id, project_id, current_user.full_name)
    return _control_agent_run_out(db, tenant_id, project_id, run)


@router.post("/projects/{project_id}/agents/control-audit/awp-draft-packages", response_model=ControlAgentRunOut)
def create_awp_draft_packages_from_agent(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ControlAgentRunOut:
    _require_project(db, tenant_id, project_id)
    membership = _require_membership(db, tenant_id, project_id, user_id)
    if membership.role not in {"Control Manager", "Planner", "Project Controls", "Field Engineer", "Workface Planner"}:
        raise HTTPException(status_code=403, detail="Current role cannot configure AWP work packages")
    _require_control_ready(db, tenant_id, project_id)
    current_user = _require_user(db, tenant_id, user_id)
    run = ControlAuditAgentService(db).create_awp_draft_packages(tenant_id, project_id, current_user.full_name)
    return _control_agent_run_out(db, tenant_id, project_id, run)


@router.get("/projects/{project_id}/agents/control-audit/runs", response_model=list[ControlAgentRunOut])
def list_control_audit_agent_runs(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ControlAgentRunOut]:
    _require_project(db, tenant_id, project_id)
    _require_membership(db, tenant_id, project_id, user_id)
    runs = list(
        db.scalars(
            select(ControlAgentRun)
            .where(
                ControlAgentRun.tenant_id == tenant_id,
                ControlAgentRun.project_id == project_id,
                ControlAgentRun.agent_code == "control_audit",
            )
            .order_by(ControlAgentRun.created_at.desc(), ControlAgentRun.id.desc())
            .limit(5)
        ).all()
    )
    return [_control_agent_run_out(db, tenant_id, project_id, run) for run in runs]


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
    funding = IntegratedControlService(db).resolve_commitment_funding(
        tenant_id, project_id, payload.funding_source_id, payload.control_account_id
    )
    IntegratedControlService(db).ensure_available(tenant_id, project_id, funding, payload.value)
    contract_code = payload.code.strip()
    if not contract_code:
        raise HTTPException(status_code=400, detail="Contract code is required")
    existing = db.scalar(
        select(Contract).where(
            Contract.tenant_id == tenant_id, Contract.project_id == project_id, Contract.code == contract_code
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="Contract code already exists in this project")
    contract = Contract(
        tenant_id=tenant_id,
        project_id=project_id,
        funding_source_id=funding.id,
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
    IntegratedControlService(db).refresh_funding_balance(tenant_id, project_id, funding)
    _audit(
        db,
        tenant_id,
        project_id,
        "create_contract",
        "Contract",
        contract.id,
        f'{{"code":"{contract.code}"}}',
        current_user.full_name,
    )
    db.commit()
    db.refresh(contract)
    return contract


@router.get("/projects/{project_id}/contracts/{contract_id}/sov-lines", response_model=list[ScheduleOfValueLineOut])
def list_schedule_of_value_lines(
    project_id: int,
    contract_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ScheduleOfValueLine]:
    _require_membership(db, tenant_id, project_id, user_id)
    _require_contract(db, tenant_id, project_id, contract_id)
    return list(
        db.scalars(
            select(ScheduleOfValueLine)
            .where(
                ScheduleOfValueLine.tenant_id == tenant_id,
                ScheduleOfValueLine.project_id == project_id,
                ScheduleOfValueLine.contract_id == contract_id,
            )
            .order_by(ScheduleOfValueLine.line_no)
        ).all()
    )


@router.post("/projects/{project_id}/contracts/{contract_id}/sov-lines", response_model=ScheduleOfValueLineOut)
def create_schedule_of_value_line(
    project_id: int,
    contract_id: int,
    payload: ScheduleOfValueLineCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ScheduleOfValueLine:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_manage_contract", "Current role cannot manage schedule of values")
    current_user = _require_user(db, tenant_id, user_id)
    contract = _require_contract(db, tenant_id, project_id, contract_id)
    if payload.cbs_id is None:
        raise HTTPException(status_code=400, detail="CBS is required for every SOV line")
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="SOV amount must be greater than zero")
    cbs = _require_cbs(db, tenant_id, project_id, payload.cbs_id)
    wbs = _require_wbs(db, tenant_id, project_id, payload.wbs_id) if payload.wbs_id is not None else None
    account = (
        _require_control_account(db, tenant_id, project_id, payload.control_account_id)
        if payload.control_account_id is not None
        else None
    )
    if contract.control_account_id and account is None:
        raise HTTPException(status_code=400, detail="Control account is required for this contract SOV line")
    if contract.control_account_id and account and account.id != contract.control_account_id:
        raise HTTPException(status_code=400, detail="SOV control account must match the contract control account")
    if wbs and account and account.wbs_id != wbs.id:
        raise HTTPException(status_code=400, detail="SOV WBS must match the selected control account")
    line_no = payload.line_no.strip()
    if not line_no:
        raise HTTPException(status_code=400, detail="SOV line number is required")
    existing = db.scalar(
        select(ScheduleOfValueLine).where(
            ScheduleOfValueLine.tenant_id == tenant_id,
            ScheduleOfValueLine.project_id == project_id,
            ScheduleOfValueLine.contract_id == contract.id,
            ScheduleOfValueLine.line_no == line_no,
        )
    )
    if existing:
        raise HTTPException(status_code=409, detail="SOV line number already exists for this contract")
    sov_line = ScheduleOfValueLine(
        tenant_id=tenant_id,
        project_id=project_id,
        contract_id=contract.id,
        line_no=line_no,
        description=payload.description.strip(),
        amount=payload.amount,
        cbs_id=cbs.id,
        wbs_id=wbs.id if wbs else None,
        control_account_id=account.id if account else None,
        status=payload.status.strip().lower() or "active",
    )
    db.add(sov_line)
    db.flush()
    _audit(
        db,
        tenant_id,
        project_id,
        "create_sov_line",
        "ScheduleOfValueLine",
        sov_line.id,
        json.dumps({"contract_id": contract.id, "line_no": sov_line.line_no, "cbs_code": cbs.code}),
        current_user.full_name,
    )
    db.commit()
    db.refresh(sov_line)
    return sov_line


@router.post("/projects/{project_id}/commitment-funding-lines", response_model=CommitmentFundingLineOut)
def create_commitment_funding_line(
    project_id: int,
    payload: CommitmentFundingLineCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> CommitmentFundingLine:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_manage_contract", "Current role cannot manage commitment funding")
    current_user = _require_user(db, tenant_id, user_id)
    contract = _require_contract(db, tenant_id, project_id, payload.contract_id)
    funding = IntegratedControlService(db).require_funding_source(tenant_id, project_id, payload.funding_source_id)
    if payload.amount <= 0:
        raise HTTPException(status_code=400, detail="Commitment funding amount must be greater than zero")
    sov_line = None
    if payload.sov_line_id is not None:
        sov_line = db.scalar(
            select(ScheduleOfValueLine).where(
                ScheduleOfValueLine.tenant_id == tenant_id,
                ScheduleOfValueLine.project_id == project_id,
                ScheduleOfValueLine.contract_id == contract.id,
                ScheduleOfValueLine.id == payload.sov_line_id,
            )
        )
        if not sov_line:
            raise HTTPException(status_code=404, detail="SOV line not found for this contract")
        allocated = (
            db.scalar(
                select(func.coalesce(func.sum(CommitmentFundingLine.amount), 0)).where(
                    CommitmentFundingLine.tenant_id == tenant_id,
                    CommitmentFundingLine.project_id == project_id,
                    CommitmentFundingLine.sov_line_id == sov_line.id,
                    CommitmentFundingLine.status != "cancelled",
                )
            )
            or 0
        )
        if allocated + payload.amount > sov_line.amount:
            raise HTTPException(status_code=409, detail="Commitment funding exceeds the SOV line amount")
    line = CommitmentFundingLine(
        tenant_id=tenant_id,
        project_id=project_id,
        contract_id=contract.id,
        sov_line_id=sov_line.id if sov_line else None,
        funding_source_id=funding.id,
        amount=payload.amount,
        consumed_amount=payload.consumed_amount,
        status=payload.status.strip().lower() or "active",
    )
    db.add(line)
    if contract.control_account_id:
        allocation = db.scalar(
            select(ControlAccountFundingAllocation).where(
                ControlAccountFundingAllocation.tenant_id == tenant_id,
                ControlAccountFundingAllocation.project_id == project_id,
                ControlAccountFundingAllocation.control_account_id == contract.control_account_id,
                ControlAccountFundingAllocation.funding_source_id == funding.id,
            )
        )
        if allocation:
            allocation.committed_amount = _money(allocation.committed_amount + payload.amount)
            _touch_collaborative_record(allocation)
    db.flush()
    _audit(
        db,
        tenant_id,
        project_id,
        "create_commitment_funding_line",
        "CommitmentFundingLine",
        line.id,
        json.dumps({"contract_id": contract.id, "funding_source_id": funding.id}),
        current_user.full_name,
    )
    db.commit()
    db.refresh(line)
    return line


@router.get(
    "/projects/{project_id}/contracts/{contract_id}/commitment-funding-lines",
    response_model=list[CommitmentFundingLineOut],
)
def list_commitment_funding_lines(
    project_id: int,
    contract_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[CommitmentFundingLine]:
    _require_membership(db, tenant_id, project_id, user_id)
    _require_contract(db, tenant_id, project_id, contract_id)
    return list(
        db.scalars(
            select(CommitmentFundingLine)
            .where(
                CommitmentFundingLine.tenant_id == tenant_id,
                CommitmentFundingLine.project_id == project_id,
                CommitmentFundingLine.contract_id == contract_id,
            )
            .order_by(CommitmentFundingLine.id)
        ).all()
    )


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
    contract: Contract | None = None
    if payload.contract_id is not None:
        contract = _require_contract(db, tenant_id, project_id, payload.contract_id)
    if payload.committed_amount <= 0:
        raise HTTPException(status_code=400, detail="Purchase order committed amount must be greater than zero")
    funding_source_id = payload.funding_source_id or (contract.funding_source_id if contract else None)
    funding = IntegratedControlService(db).resolve_commitment_funding(
        tenant_id, project_id, funding_source_id, payload.control_account_id
    )
    IntegratedControlService(db).ensure_available(tenant_id, project_id, funding, payload.committed_amount)
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
        funding_source_id=funding.id,
        control_account_id=payload.control_account_id,
        contract_id=payload.contract_id,
        po_number=po_number,
        description=payload.description.strip(),
        vendor=payload.vendor.strip(),
        committed_amount=payload.committed_amount,
        status=payload.status.strip() or "issued",
        issued_on=payload.issued_on or utc_now().date(),
    )
    db.add(order)
    db.flush()
    IntegratedControlService(db).refresh_funding_balance(tenant_id, project_id, funding)
    _audit(
        db,
        tenant_id,
        project_id,
        "create_purchase_order",
        "PurchaseOrder",
        order.id,
        json.dumps({"po_number": order.po_number, "committed_amount": order.committed_amount}),
        current_user.full_name,
    )
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
    contract: Contract | None = None
    if payload.contract_id is not None:
        contract = _require_contract(db, tenant_id, project_id, payload.contract_id)
    if payload.committed_amount is not None and payload.committed_amount <= 0:
        raise HTTPException(status_code=400, detail="Purchase order committed amount must be greater than zero")
    funding_source_id = payload.funding_source_id or (
        contract.funding_source_id if contract else order.funding_source_id
    )
    funding = IntegratedControlService(db).resolve_commitment_funding(
        tenant_id, project_id, funding_source_id, payload.control_account_id or order.control_account_id
    )
    requested_amount = payload.committed_amount if payload.committed_amount is not None else order.committed_amount
    IntegratedControlService(db).ensure_available(
        tenant_id,
        project_id,
        funding,
        requested_amount,
        exclude_purchase_order_id=order.id,
    )
    for field in (
        "funding_source_id",
        "control_account_id",
        "contract_id",
        "description",
        "vendor",
        "committed_amount",
        "status",
        "issued_on",
    ):
        value = getattr(payload, field)
        if value is not None:
            setattr(order, field, value.strip() if isinstance(value, str) else value)
    order.funding_source_id = funding.id
    IntegratedControlService(db).refresh_funding_balance(tenant_id, project_id, funding)
    _touch_collaborative_record(order)
    _audit(
        db,
        tenant_id,
        project_id,
        "update_purchase_order",
        "PurchaseOrder",
        order.id,
        json.dumps({"status": order.status, "version": order.version}),
        current_user.full_name,
    )
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
        certified_on=payload.certified_on or utc_now().date(),
    )
    db.add(certificate)
    db.flush()
    _audit(
        db,
        tenant_id,
        project_id,
        "certify_incurred_cost",
        "PaymentCertificate",
        certificate.id,
        json.dumps({"certificate_no": certificate.certificate_no, "certified_amount": certificate.certified_amount}),
        current_user.full_name,
    )
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
    for field in (
        "control_account_id",
        "contract_id",
        "purchase_order_id",
        "period_label",
        "certified_amount",
        "retained_amount",
        "status",
        "certified_on",
    ):
        value = getattr(payload, field)
        if value is not None:
            setattr(certificate, field, value.strip() if isinstance(value, str) else value)
    _touch_collaborative_record(certificate)
    _audit(
        db,
        tenant_id,
        project_id,
        "update_payment_certificate",
        "PaymentCertificate",
        certificate.id,
        json.dumps({"status": certificate.status, "version": certificate.version}),
        current_user.full_name,
    )
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
        received_on=payload.received_on or utc_now().date(),
    )
    db.add(receipt)
    db.flush()
    _audit(
        db,
        tenant_id,
        project_id,
        "register_warehouse_receipt",
        "WarehouseReceipt",
        receipt.id,
        json.dumps({"receipt_no": receipt.receipt_no, "received_value": receipt.received_value}),
        current_user.full_name,
    )
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
    received_quantity = (
        payload.received_quantity if payload.received_quantity is not None else receipt.received_quantity
    )
    unit_cost = payload.unit_cost if payload.unit_cost is not None else receipt.unit_cost
    received_value = payload.received_value if payload.received_value is not None else receipt.received_value
    _validate_warehouse_receipt_values(received_quantity, unit_cost, received_value)
    for field in (
        "control_account_id",
        "contract_id",
        "purchase_order_id",
        "description",
        "received_quantity",
        "unit_cost",
        "status",
        "received_on",
    ):
        value = getattr(payload, field)
        if value is not None:
            setattr(receipt, field, value.strip() if isinstance(value, str) else value)
    if payload.received_value is not None or payload.received_quantity is not None or payload.unit_cost is not None:
        receipt.received_value = _warehouse_received_value(
            receipt.received_quantity,
            receipt.unit_cost,
            payload.received_value if payload.received_value is not None else 0,
        )
    _touch_collaborative_record(receipt)
    _audit(
        db,
        tenant_id,
        project_id,
        "update_warehouse_receipt",
        "WarehouseReceipt",
        receipt.id,
        json.dumps({"status": receipt.status, "version": receipt.version}),
        current_user.full_name,
    )
    db.commit()
    ControlCoreService(db).run_project_cycle(tenant_id, project_id)
    db.refresh(receipt)
    return receipt


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
        contract = db.scalar(
            select(Contract).where(
                Contract.id == payload.contract_id, Contract.tenant_id == tenant_id, Contract.project_id == project_id
            )
        )
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
    _audit(
        db,
        tenant_id,
        project_id,
        "create_contract_communication",
        "ContractCommunication",
        communication.id,
        f'{{"subject":"{communication.subject}"}}',
        current_user.full_name,
    )
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
        contract = db.scalar(
            select(Contract).where(
                Contract.id == payload.contract_id, Contract.tenant_id == tenant_id, Contract.project_id == project_id
            )
        )
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


@router.get("/projects/{project_id}/claims", response_model=list[ClaimOut])
def list_claims(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[Claim]:
    _require_membership(db, tenant_id, project_id, user_id)
    return list(
        db.scalars(
            select(Claim).where(Claim.project_id == project_id, Claim.tenant_id == tenant_id).order_by(Claim.id.desc())
        ).all()
    )


@router.post("/projects/{project_id}/claims", response_model=ClaimOut)
def create_claim(
    project_id: int,
    payload: ClaimCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> Claim:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_manage_contract", "Current role cannot create claims")
    current_user = _require_user(db, tenant_id, user_id)
    if payload.control_account_id is not None:
        account = db.scalar(
            select(ControlAccount).where(
                ControlAccount.id == payload.control_account_id,
                ControlAccount.tenant_id == tenant_id,
                ControlAccount.project_id == project_id,
            )
        )
        if not account:
            raise HTTPException(status_code=404, detail="Control account not found")
    try:
        status = WorkflowStatus(payload.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Unsupported claim status") from exc
    claim = Claim(
        tenant_id=tenant_id,
        project_id=project_id,
        control_account_id=payload.control_account_id,
        title=payload.title,
        causality=payload.causality,
        impact=payload.impact,
        evidence_summary=payload.evidence_summary,
        status=status,
    )
    db.add(claim)
    db.flush()
    _audit(
        db,
        tenant_id,
        project_id,
        "create_claim",
        "Claim",
        claim.id,
        json.dumps({"title": claim.title, "status": str(claim.status)}),
        current_user.full_name,
    )
    db.commit()
    db.refresh(claim)
    return claim


@router.post("/projects/{project_id}/claims/forensic-runs", response_model=ForensicDossierAnalysisOut)
async def create_claims_forensic_run(
    project_id: int,
    mode: str = Form("review"),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ForensicDossierAnalysisOut:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_manage_contract", "Current role cannot run forensic claims analysis")
    current_user = _require_user(db, tenant_id, user_id)
    uploads: list[tuple[str, bytes]] = []
    for upload in files:
        payload = await upload.read()
        if payload:
            uploads.append((upload.filename or "dossier", payload))
    if not uploads:
        raise HTTPException(status_code=400, detail="Upload at least one dossier file")
    service = ClaimsForensicDossierService(db)
    try:
        result = service.analyze(tenant_id=tenant_id, project_id=project_id, mode=mode, uploads=uploads)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    primary_claim_id = result.created_claims[0].id if result.created_claims else None
    _audit(
        db,
        tenant_id,
        project_id,
        "run_claims_forensic_dossier",
        "Claim",
        primary_claim_id,
        json.dumps(
            {
                "mode": mode,
                "source_files": result.source_files,
                "signals": result.signals,
                "readiness_score": result.readiness_score,
            }
        ),
        current_user.full_name,
    )
    db.commit()
    created_objects = (
        result.created_claims
        + result.created_notices
        + result.created_entitlement_items
        + result.created_impact_analyses
    )
    for created in created_objects:
        db.refresh(created)
    return ForensicDossierAnalysisOut(
        mode=mode if mode in ClaimsForensicDossierService.modes else "review",
        summary=result.summary,
        source_files=result.source_files,
        signals=result.signals,
        readiness_score=result.readiness_score,
        created_claims=[ClaimOut.model_validate(claim) for claim in result.created_claims],
        created_notices=[ContractNoticeOut.model_validate(notice) for notice in result.created_notices],
        created_entitlement_items=[
            ClaimEntitlementItemOut.model_validate(item) for item in result.created_entitlement_items
        ],
        created_impact_analyses=[
            ClaimImpactAnalysisOut.model_validate(analysis) for analysis in result.created_impact_analyses
        ],
    )


@router.get("/projects/{project_id}/claims/window-analysis-37/rag-sources", response_model=list[ForensicRagSourceOut])
def list_window_analysis_37_rag_sources(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ForensicRagSourceOut]:
    _require_membership(db, tenant_id, project_id, user_id)
    return [ForensicRagSourceOut.model_validate(source) for source in ForensicWindowAnalysisService().rag_sources()]


@router.post("/projects/{project_id}/claims/window-analysis-37", response_model=ForensicWindowAnalysisOut)
async def create_window_analysis_37_run(
    project_id: int,
    near_critical_threshold_days: float = Form(10),
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ForensicWindowAnalysisOut:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_manage_contract", "Current role cannot run forensic schedule analysis")
    current_user = _require_user(db, tenant_id, user_id)
    uploads: list[tuple[str, bytes]] = []
    for upload in files:
        payload = await upload.read()
        if payload:
            uploads.append((upload.filename or "schedule", payload))
    if not uploads:
        raise HTTPException(status_code=400, detail="Upload at least one schedule file")

    result = ForensicWindowAnalysisService().analyze(
        uploads=uploads,
        near_critical_threshold_days=near_critical_threshold_days,
    )
    _audit(
        db,
        tenant_id,
        project_id,
        "run_window_analysis_37",
        "ClaimImpactAnalysis",
        None,
        json.dumps(
            {
                "method_id": result.method_id,
                "source_files": [row.file_name for row in result.schedule_sources],
                "summary": result.summary,
            }
        ),
        current_user.full_name,
    )
    db.commit()
    return ForensicWindowAnalysisOut.model_validate(result)


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
            (
                "Initiation",
                "Deviation captured with cost, schedule and contractual context.",
                "Originator",
                "Complete",
                "complete",
            ),
            (
                "Impact Review",
                "Evaluate cost, schedule, progress and risk exposure.",
                "Project Controls",
                "Active",
                "active",
            ),
            (
                "Contract Review",
                "Confirm notice, entitlement and contract position.",
                "Contract Manager",
                "Pending",
                "pending",
            ),
            ("Approval", "Control Manager decision on disposition.", "Control Manager", "Queued", "queued"),
            (
                "Implementation",
                "Approved disposition updates forecast, budget and action log.",
                "Execution Lead",
                "Queued",
                "queued",
            ),
        ],
    )
    _audit(
        db,
        tenant_id,
        project_id,
        "create_change_request",
        "ChangeRequest",
        change.id,
        f'{{"title":"{change.title}"}}',
        current_user.full_name,
    )
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
    _audit(
        db,
        tenant_id,
        project_id,
        "create_claim_entitlement_item",
        "ClaimEntitlementItem",
        item.id,
        f'{{"claim_id":{claim.id},"element":"{item.element}"}}',
        current_user.full_name,
    )
    db.commit()
    db.refresh(item)
    return item


@router.patch(
    "/projects/{project_id}/claims/{claim_id}/entitlement-items/{item_id}", response_model=ClaimEntitlementItemOut
)
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
    _audit(
        db,
        tenant_id,
        project_id,
        "update_claim_entitlement_item",
        "ClaimEntitlementItem",
        item.id,
        f'{{"status":"{item.status}"}}',
        current_user.full_name,
    )
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


@router.patch(
    "/projects/{project_id}/claims/{claim_id}/impact-analyses/{analysis_id}", response_model=ClaimImpactAnalysisOut
)
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
    package_type = payload.package_type.strip().upper()
    if package_type not in AWP_PACKAGE_TYPES:
        raise HTTPException(status_code=400, detail="Unsupported AWP package type")
    if payload.wbs_id is not None:
        wbs = db.scalar(
            select(WBS).where(WBS.id == payload.wbs_id, WBS.tenant_id == tenant_id, WBS.project_id == project_id)
        )
        if not wbs:
            raise HTTPException(status_code=404, detail="WBS not found")
    if payload.control_account_id is not None:
        _require_control_account(db, tenant_id, project_id, payload.control_account_id)
    parent_package: WorkPackage | None = None
    if payload.parent_id is not None:
        parent_package = _require_work_package(db, tenant_id, project_id, payload.parent_id)
    _validate_awp_package_hierarchy(parent_package, package_type)
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
        wbs_id=payload.wbs_id,
        control_account_id=payload.control_account_id,
        parent_id=payload.parent_id,
        package_type=package_type,
        code=payload.code,
        title=payload.title,
        description=payload.description,
        discipline=payload.discipline,
        sequence_no=payload.sequence_no,
        path_of_construction=payload.path_of_construction,
        owner_role=payload.owner_role,
        readiness_status=payload.readiness_status,
        planned_release_date=payload.planned_release_date,
        planned_start=payload.planned_start,
        planned_finish=payload.planned_finish,
        release_required_on=payload.release_required_on,
        main_constraints=payload.main_constraints,
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
            (
                "Path Definition",
                "Path of construction, area and sequence are defined from the approved schedule.",
                "Planner",
                "Complete",
                "complete",
            ),
            (
                "Package Scope",
                "CWP/EWP/PWP/IWP scope is tied to control account and deliverables.",
                "Workface Planner",
                "Complete",
                "complete",
            ),
            (
                "Constraint Review",
                "Engineering, materials, access, permit, safety and document constraints are checked.",
                package.owner_role,
                "Active",
                "active",
            ),
            (
                "Release",
                "Ready package can be released to field execution.",
                "Construction Manager",
                "Queued",
                "queued",
            ),
            (
                "Execute",
                "Progress capture feeds Control Core and package status.",
                "Field Engineer",
                "Queued",
                "queued",
            ),
        ],
    )
    _audit(
        db,
        tenant_id,
        project_id,
        "create_awp_work_package",
        "WorkPackage",
        package.id,
        f'{{"code":"{package.code}","type":"{package.package_type}"}}',
        current_user.full_name,
    )
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
    _audit(
        db,
        tenant_id,
        project_id,
        "update_awp_readiness",
        "WorkPackage",
        package.id,
        f'{{"code":"{package.code}"}}',
        current_user.full_name,
    )
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
    priority = _normalize_awp_constraint_priority(payload.priority)
    constraint = WorkPackageConstraint(
        tenant_id=tenant_id,
        project_id=project_id,
        work_package_id=package.id,
        constraint_type=payload.constraint_type,
        description=payload.description,
        owner_role=payload.owner_role,
        required_by=payload.required_by,
        status=payload.status,
        priority=priority,
        evidence_ref=payload.evidence_ref,
        closure_note=payload.closure_note,
        exception_ref=payload.exception_ref,
        blocking=payload.blocking,
    )
    _apply_awp_constraint_closure(constraint, current_user.full_name)
    db.add(constraint)
    if constraint.blocking and constraint.status == "open":
        package.readiness_status = "blocked"
    db.flush()
    _audit(
        db,
        tenant_id,
        project_id,
        "create_awp_constraint",
        "WorkPackageConstraint",
        constraint.id,
        f'{{"work_package":"{package.code}","type":"{constraint.constraint_type}"}}',
        current_user.full_name,
    )
    db.commit()
    db.refresh(constraint)
    return constraint


@router.patch(
    "/projects/{project_id}/work-packages/{package_id}/constraints/{constraint_id}",
    response_model=WorkPackageConstraintOut,
)
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
        if field == "priority" and value is not None:
            value = _normalize_awp_constraint_priority(value)
        setattr(constraint, field, value)
    _apply_awp_constraint_closure(constraint, current_user.full_name)
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
    _audit(
        db,
        tenant_id,
        project_id,
        "update_awp_constraint",
        "WorkPackageConstraint",
        constraint.id,
        f'{{"status":"{constraint.status}"}}',
        current_user.full_name,
    )
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
            .where(
                ScheduleActivityMap.schedule_import_id == latest_import.id, ScheduleActivityMap.tenant_id == tenant_id
            )
            .order_by(ScheduleActivityMap.external_activity_id)
        ).all()
    )


@router.get("/projects/{project_id}/schedule-relationships", response_model=list[ActivityRelationshipOut])
def list_schedule_relationships(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ActivityRelationship]:
    _require_membership(db, tenant_id, project_id, user_id)
    latest_import = _latest_schedule_import(db, tenant_id, project_id)
    if not latest_import:
        return []
    return list(
        db.scalars(
            select(ActivityRelationship)
            .where(
                ActivityRelationship.tenant_id == tenant_id,
                ActivityRelationship.project_id == project_id,
                ActivityRelationship.schedule_import_id == latest_import.id,
            )
            .order_by(ActivityRelationship.id)
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


@router.post(
    "/projects/{project_id}/workflow-instances/{process_id}/actions", response_model=BusinessProcessInstanceOut
)
def apply_workflow_action(
    project_id: int,
    process_id: int,
    payload: WorkflowActionIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> BusinessProcessInstance:
    membership = _require_membership(db, tenant_id, project_id, user_id)
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
    policy = _workflow_process_policy(db, tenant_id, project_id, process.process_code, payload.action)
    if policy:
        if policy.required_role and membership.role != policy.required_role:
            raise HTTPException(status_code=403, detail=f"Workflow action requires role {policy.required_role}")
        if policy.permission_key:
            _require_permission(membership, policy.permission_key, "Current role cannot execute this workflow policy")
    else:
        transition_permission = _workflow_transition_permission(db, tenant_id, process_id, payload.action)
        if transition_permission:
            _require_permission(
                membership, transition_permission, "Current role cannot execute this workflow transition"
            )
        elif payload.action in {"approve_baseline", "reject_baseline", "close_action"}:
            _require_permission(
                membership, "can_approve_workflow", "Current role cannot approve or close workflow actions"
            )
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
            select(Alert)
            .where(Alert.project_id == project_id, Alert.tenant_id == tenant_id)
            .order_by(Alert.created_at.desc())
        ).all()
    )
    changes = list(
        db.scalars(
            select(ChangeRequest).where(ChangeRequest.project_id == project_id, ChangeRequest.tenant_id == tenant_id)
        ).all()
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
    contracts = list(
        db.scalars(
            select(Contract)
            .where(Contract.project_id == project_id, Contract.tenant_id == tenant_id)
            .order_by(Contract.code)
        ).all()
    )
    purchase_orders = _purchase_orders(db, tenant_id, project_id)
    payment_certificates = _payment_certificates(db, tenant_id, project_id)
    warehouse_receipts = _warehouse_receipts(db, tenant_id, project_id)
    rfq_packages = rfq_domain.rfq_packages(db, tenant_id, project_id)
    rfq_bids = rfq_domain.rfq_bids(db, tenant_id, project_id)
    communications = list(
        db.scalars(
            select(ContractCommunication)
            .where(ContractCommunication.project_id == project_id, ContractCommunication.tenant_id == tenant_id)
            .order_by(ContractCommunication.sent_on.desc(), ContractCommunication.id.desc())
        ).all()
    )
    documents = documents_domain._accessible_documents(db, tenant_id, project_id, current_membership)
    document_attachments = documents_domain._accessible_document_attachments(
        db, tenant_id, project_id, current_membership
    )
    document_transmittals = documents_domain._document_transmittals(db, tenant_id, project_id)
    document_transmittal_items = documents_domain._document_transmittal_items(db, tenant_id, project_id)
    document_reviews = documents_domain._document_reviews(db, tenant_id, project_id)
    project_mail = documents_domain._project_mail(db, tenant_id, project_id)
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
        db.scalars(
            select(ControlAccount).where(ControlAccount.project_id == project_id, ControlAccount.tenant_id == tenant_id)
        ).all()
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
    schedule_activities = (
        list(
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
        if schedule_import
        else []
    )
    schedule_relationships = (
        list(
            db.scalars(
                select(ActivityRelationship)
                .where(
                    ActivityRelationship.tenant_id == tenant_id,
                    ActivityRelationship.project_id == project_id,
                    ActivityRelationship.schedule_import_id == schedule_import.id,
                )
                .order_by(ActivityRelationship.id)
            ).all()
        )
        if schedule_import
        else []
    )
    schedule_activity_count = len(schedule_activities)
    schedule_relationship_count = len(schedule_relationships)
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
    workflow_instance = (
        _latest_schedule_workflow(db, tenant_id, project_id, schedule_import.id) if schedule_import else None
    )
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
        TCMFlowStep(
            name="Cuentas de Control", purpose="Integrated schedule/cost/progress control objects.", state="active"
        ),
        TCMFlowStep(
            name="Ejecucion", purpose="Field progress, actual cost, resources and evidence capture.", state="capturing"
        ),
        TCMFlowStep(name="Control Core", purpose="EVM, changes, claims and early warning analysis.", state="running"),
        TCMFlowStep(name="Decision", purpose="Prioritized recommendations with governance.", state="open"),
        TCMFlowStep(
            name="Retroalimentacion",
            purpose="Actions update lookahead, forecast and contractual traceability.",
            state="continuous",
        ),
    ]
    loop = [
        ControlCoreLoop(step="CAPTURAR", description="Progress, cost, resources, documents and field events."),
        ControlCoreLoop(
            step="VALIDAR", description="Data quality, contractual support and cross-discipline consistency."
        ),
        ControlCoreLoop(step="ANALIZAR", description="EVM, productivity, change exposure and forensic signals."),
        ControlCoreLoop(step="ALERTAR", description="Threshold-based early warning with recommended response."),
        ControlCoreLoop(
            step="DECIDIR", description="Decision layer separates recommendations from execution workflows."
        ),
        ControlCoreLoop(
            step="ACTUAR", description="Approved action updates forecast, lookahead, communications and audit."
        ),
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
        schedule_quality_metrics=_schedule_quality_metrics(
            schedule_import, schedule_activities, schedule_relationships
        ),
        baseline_versions=[BaselineVersionOut.model_validate(baseline) for baseline in baseline_versions[:6]],
        control_periods=[ControlPeriodOut.model_validate(period) for period in control_periods[:6]],
        workflow_instance=BusinessProcessInstanceOut.model_validate(workflow_instance) if workflow_instance else None,
        workflow_steps=[WorkflowStepInstanceOut.model_validate(step) for step in workflow_steps],
        business_processes=[BusinessProcessInstanceOut.model_validate(process) for process in business_processes],
        process_templates=_configured_process_templates(db, tenant_id),
        audit_logs=[AuditLogOut.model_validate(log) for log in audit_logs[:8]],
        data_quality_gates=_data_quality_gates(
            schedule_import, schedule_activity_count or 0, schedule_relationship_count or 0, schedule_findings
        ),
        flow=flow,
        loop=loop,
        control_accounts=[ControlAccountOut.model_validate(account) for account in accounts],
        control_account_mappings=[
            ControlAccountMappingOut.model_validate(mapping) for mapping in control_account_mappings[:100]
        ],
        control_account_mapping_summary=_control_account_mapping_summary(
            control_account_mappings, baseline_versions[0].status if baseline_versions else "pending"
        ),
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
        claims_forensic_summary=_claims_forensic_summary(
            claims, contract_notices, claim_impact_analyses, claim_entitlement_items
        ),
        contracts=[ContractOut.model_validate(contract) for contract in contracts],
        purchase_orders=[PurchaseOrderOut.model_validate(order) for order in purchase_orders],
        payment_certificates=[
            PaymentCertificateOut.model_validate(certificate) for certificate in payment_certificates
        ],
        warehouse_receipts=[WarehouseReceiptOut.model_validate(receipt) for receipt in warehouse_receipts],
        rfq_packages=[RFQPackageOut.model_validate(package) for package in rfq_packages],
        rfq_bids=[RFQBidOut.model_validate(bid) for bid in rfq_bids],
        rfq_summary=rfq_domain.rfq_summary(rfq_packages, rfq_bids),
        communications=[ContractCommunicationOut.model_validate(communication) for communication in communications[:6]],
        documents=[DocumentOut.model_validate(document) for document in documents],
        document_attachments=[DocumentAttachmentOut.model_validate(attachment) for attachment in document_attachments],
        document_transmittals=[
            DocumentTransmittalOut.model_validate(transmittal) for transmittal in document_transmittals
        ],
        document_transmittal_items=[
            DocumentTransmittalItemOut.model_validate(item) for item in document_transmittal_items
        ],
        document_reviews=[DocumentReviewOut.model_validate(review) for review in document_reviews],
        project_mail=[ProjectMailOut.model_validate(mail) for mail in project_mail],
        document_control_summary=documents_domain._document_control_summary(
            documents, document_transmittals, document_reviews, project_mail
        ),
        work_packages=[WorkPackageOut.model_validate(package) for package in work_packages],
        work_package_constraints=[
            WorkPackageConstraintOut.model_validate(constraint) for constraint in work_package_constraints
        ],
        awp_summary=_awp_summary(work_packages, work_package_constraints),
        ai_brief=AIInsightService().explain_project_variance(project_kpi, alerts),
    )


@router.get("/projects/{project_id}/audit-logs", response_model=list[AuditLogOut])
def list_project_audit_logs(
    project_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[AuditLog]:
    _require_membership(db, tenant_id, project_id, user_id)
    return list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.tenant_id == tenant_id, AuditLog.project_id == project_id)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(limit)
        ).all()
    )


@router.get("/projects/{project_id}/integration-tokens", response_model=list[IntegrationTokenOut])
def list_integration_tokens(
    project_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[IntegrationTokenOut]:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_configure", "Current role cannot manage integration tokens")
    tokens = list(
        db.scalars(
            select(IntegrationToken)
            .where(IntegrationToken.tenant_id == tenant_id, IntegrationToken.project_id == project_id)
            .order_by(IntegrationToken.created_at.desc(), IntegrationToken.id.desc())
        ).all()
    )
    return [_integration_token_out(token) for token in tokens]


@router.get("/projects/{project_id}/integration-token-alerts", response_model=IntegrationTokenAlertSummary)
def list_integration_token_alerts(
    project_id: int,
    warning_days: int = Query(default=14, ge=1, le=90),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> IntegrationTokenAlertSummary:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_configure", "Current role cannot view integration token alerts")
    tokens = list(
        db.scalars(
            select(IntegrationToken)
            .where(IntegrationToken.tenant_id == tenant_id, IntegrationToken.project_id == project_id)
            .order_by(IntegrationToken.expires_at.asc(), IntegrationToken.id.desc())
        ).all()
    )
    return _integration_token_alert_summary(project_id, tokens, warning_days)


@router.post("/projects/{project_id}/integration-tokens", response_model=IntegrationTokenCreated)
def create_integration_token(
    project_id: int,
    payload: IntegrationTokenCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> IntegrationTokenCreated:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_configure", "Current role cannot manage integration tokens")
    current_user = _require_user(db, tenant_id, user_id)
    datasets = _validate_integration_token_datasets(payload.datasets)
    formats = _validate_integration_token_formats(payload.formats)
    expires_in_days = _validate_integration_token_expiry(payload.expires_in_days)
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Integration token name is required")

    raw_token = _generate_integration_token()
    token = IntegrationToken(
        tenant_id=tenant_id,
        project_id=project_id,
        created_by_user_id=user_id,
        name=name,
        token_prefix=_integration_token_public_prefix(raw_token),
        token_hash=_integration_token_hash(raw_token),
        allowed_datasets=",".join(datasets),
        allowed_formats=",".join(formats),
        status="active",
        expires_at=utc_now() + timedelta(days=expires_in_days),
    )
    db.add(token)
    db.flush()
    _audit(
        db,
        tenant_id,
        project_id,
        "create_integration_token",
        "IntegrationToken",
        token.id,
        json.dumps({"name": token.name, "datasets": datasets, "formats": formats, "expires_in_days": expires_in_days}),
        current_user.full_name,
    )
    db.commit()
    db.refresh(token)
    return _integration_token_created(token, raw_token)


@router.post("/projects/{project_id}/integration-tokens/{token_id}/revoke", response_model=IntegrationTokenOut)
def revoke_integration_token(
    project_id: int,
    token_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> IntegrationTokenOut:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_configure", "Current role cannot manage integration tokens")
    current_user = _require_user(db, tenant_id, user_id)
    token = db.scalar(
        select(IntegrationToken).where(
            IntegrationToken.tenant_id == tenant_id,
            IntegrationToken.project_id == project_id,
            IntegrationToken.id == token_id,
        )
    )
    if not token:
        raise HTTPException(status_code=404, detail="Integration token not found")
    token.status = "revoked"
    token.updated_at = utc_now()
    _audit(
        db,
        tenant_id,
        project_id,
        "revoke_integration_token",
        "IntegrationToken",
        token.id,
        json.dumps({"name": token.name}),
        current_user.full_name,
    )
    db.commit()
    db.refresh(token)
    return _integration_token_out(token)


@router.get("/projects/{project_id}/integration-downloads", response_model=list[IntegrationExportLogOut])
def list_integration_downloads(
    project_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[IntegrationExportLogOut]:
    membership = _require_membership(db, tenant_id, project_id, user_id)
    _require_permission(membership, "can_configure", "Current role cannot view integration download logs")
    logs = list(
        db.scalars(
            select(IntegrationExportLog)
            .where(IntegrationExportLog.tenant_id == tenant_id, IntegrationExportLog.project_id == project_id)
            .order_by(IntegrationExportLog.created_at.desc(), IntegrationExportLog.id.desc())
            .limit(limit)
        ).all()
    )
    return [_integration_export_log_out(log) for log in logs]


@router.get("/projects/{project_id}/integration-manifest")
def get_integration_manifest(
    project_id: int,
    db: Session = Depends(get_db),
    authorization: str = Header(default="", alias="Authorization"),
) -> dict[str, object]:
    access = _require_integration_access(db, project_id, authorization)
    datasets = []
    for dataset_key in access.allowed_datasets:
        metadata = INTEGRATION_DATASETS[dataset_key]
        rows = _integration_dataset_rows(db, access.tenant_id, project_id, access.membership, dataset_key)
        datasets.append(
            {
                "key": dataset_key,
                "label": metadata["label"],
                "description": metadata["description"],
                "formats": ["json", "csv"],
                "row_count": len(rows),
                "fields": _integration_dataset_fields(dataset_key),
            }
        )
    return {
        "project": ProjectOut.model_validate(access.project).model_dump(mode="json"),
        "generated_at": _integration_generated_at(),
        "mode": "read_only",
        "datasets": datasets,
    }


@router.get("/projects/{project_id}/integration-export")
def export_integration_dataset(
    project_id: int,
    dataset: str = Query(..., min_length=1),
    export_format: str = Query(default="json", alias="format"),
    db: Session = Depends(get_db),
    authorization: str = Header(default="", alias="Authorization"),
):
    dataset_key = _normalize_integration_dataset(dataset)
    if dataset_key not in INTEGRATION_DATASETS:
        raise HTTPException(status_code=400, detail=f"Unsupported integration dataset: {dataset}")
    normalized_format = export_format.strip().lower()
    if normalized_format not in {"json", "csv"}:
        raise HTTPException(status_code=400, detail=f"Unsupported integration export format: {export_format}")
    access = _require_integration_access(db, project_id, authorization, [dataset_key], normalized_format)

    rows = _integration_dataset_rows(db, access.tenant_id, project_id, access.membership, dataset_key)
    fields = _integration_dataset_fields(dataset_key)
    if normalized_format == "csv":
        filename = f"{access.project.code}-{dataset_key}.csv"
        csv_content = _integration_rows_to_csv(rows, fields).encode("utf-8")
        download_log = _record_integration_download(
            db, access, "export", [dataset_key], normalized_format, filename, csv_content, len(rows)
        )
        response = PlainTextResponse(csv_content.decode("utf-8"), media_type="text/csv")
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        response.headers["X-Integration-Download-Id"] = str(download_log.id)
        return response

    payload = {
        "project": ProjectOut.model_validate(access.project).model_dump(mode="json"),
        "dataset": dataset_key,
        "format": "json",
        "generated_at": _integration_generated_at(),
        "row_count": len(rows),
        "fields": fields,
        "rows": rows,
    }
    _record_integration_download(
        db,
        access,
        "export",
        [dataset_key],
        normalized_format,
        f"{access.project.code}-{dataset_key}.json",
        _integration_manifest_to_json_bytes(payload),
        len(rows),
    )
    return payload


@router.get("/projects/{project_id}/integration-package")
def export_integration_package(
    project_id: int,
    datasets: str = Query(default="cost_sheet,funding_sources,cash_flow,documents,document_attachments"),
    package_format: str = Query(default="both", alias="format"),
    db: Session = Depends(get_db),
    authorization: str = Header(default="", alias="Authorization"),
) -> Response:
    dataset_keys = _parse_integration_dataset_list(datasets)
    normalized_format = package_format.strip().lower()
    if normalized_format not in {"json", "csv", "both"}:
        raise HTTPException(status_code=400, detail=f"Unsupported integration package format: {package_format}")
    access = _require_integration_access(db, project_id, authorization, dataset_keys, normalized_format)

    generated_at = _integration_generated_at()
    package_id = f"{access.project.code}-{generated_at.replace(':', '').replace('-', '').replace('Z', 'Z')}"
    zip_buffer = BytesIO()
    package_files: list[dict[str, object]] = []
    dataset_summaries: list[dict[str, object]] = []

    with ZipFile(zip_buffer, "w", ZIP_DEFLATED) as archive:
        for dataset_key in dataset_keys:
            rows = _integration_dataset_rows(db, access.tenant_id, project_id, access.membership, dataset_key)
            fields = _integration_dataset_fields(dataset_key)
            dataset_summaries.append(
                {
                    "key": dataset_key,
                    "label": INTEGRATION_DATASETS[dataset_key]["label"],
                    "row_count": len(rows),
                    "fields": fields,
                }
            )
            if normalized_format in {"json", "both"}:
                json_path = f"datasets/{dataset_key}.json"
                json_content = _integration_rows_to_json_bytes(rows)
                archive.writestr(json_path, json_content)
                package_files.append(
                    _integration_package_file_metadata(dataset_key, "json", json_path, rows, fields, json_content)
                )
            if normalized_format in {"csv", "both"}:
                csv_path = f"datasets/{dataset_key}.csv"
                csv_content = _integration_rows_to_csv(rows, fields).encode("utf-8")
                archive.writestr(csv_path, csv_content)
                package_files.append(
                    _integration_package_file_metadata(dataset_key, "csv", csv_path, rows, fields, csv_content)
                )

        manifest = {
            "package_id": package_id,
            "project": ProjectOut.model_validate(access.project).model_dump(mode="json"),
            "generated_at": generated_at,
            "mode": "read_only",
            "format": normalized_format,
            "datasets": dataset_summaries,
            "files": package_files,
        }
        archive.writestr("package_manifest.json", _integration_manifest_to_json_bytes(manifest))

    package_bytes = zip_buffer.getvalue()
    package_sha256 = hashlib.sha256(package_bytes).hexdigest()
    filename = f"{_safe_integration_file_stem(access.project.code)}-integration-package.zip"
    download_log = _record_integration_download(
        db,
        access,
        "package",
        dataset_keys,
        normalized_format,
        filename,
        package_bytes,
        sum(int(dataset["row_count"]) for dataset in dataset_summaries),
    )
    return Response(
        content=package_bytes,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Package-Id": package_id,
            "X-Package-Sha256": package_sha256,
            "X-Integration-Download-Id": str(download_log.id),
        },
    )


@router.get("/projects/{project_id}/integration-workbook")
def export_integration_workbook(
    project_id: int,
    datasets: str = Query(default="cost_sheet,funding_sources,cash_flow,documents"),
    db: Session = Depends(get_db),
    authorization: str = Header(default="", alias="Authorization"),
) -> Response:
    dataset_keys = _parse_integration_dataset_list(datasets)
    access = _require_integration_access(db, project_id, authorization, dataset_keys, "xlsx")
    generated_at = _integration_generated_at()
    workbook_datasets: list[dict[str, object]] = []
    for dataset_key in dataset_keys:
        rows = _integration_dataset_rows(db, access.tenant_id, project_id, access.membership, dataset_key)
        workbook_datasets.append(
            {
                "key": dataset_key,
                "label": INTEGRATION_DATASETS[dataset_key]["label"],
                "fields": _integration_dataset_fields(dataset_key),
                "rows": rows,
            }
        )
    workbook_bytes = _integration_workbook_bytes(access.project, generated_at, workbook_datasets)
    workbook_sha256 = hashlib.sha256(workbook_bytes).hexdigest()
    filename = f"{_safe_integration_file_stem(access.project.code)}-integration-workbook.xlsx"
    download_log = _record_integration_download(
        db,
        access,
        "workbook",
        dataset_keys,
        "xlsx",
        filename,
        workbook_bytes,
        sum(len(list(dataset["rows"])) for dataset in workbook_datasets),
    )
    return Response(
        content=workbook_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Workbook-Sha256": workbook_sha256,
            "X-Workbook-Datasets": ",".join(dataset_keys),
            "X-Integration-Download-Id": str(download_log.id),
        },
    )


def _require_integration_access(
    db: Session,
    project_id: int,
    authorization: str,
    datasets: list[str] | None = None,
    export_format: str | None = None,
) -> IntegrationAccess:
    if not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Bearer token is required")
    raw_token = authorization.split(" ", 1)[1].strip()
    if raw_token.startswith(INTEGRATION_TOKEN_PREFIX):
        access = _require_integration_token_access(db, project_id, raw_token)
    else:
        access = _require_jwt_integration_access(db, project_id, raw_token)
    if datasets:
        _require_integration_dataset_scope(access, datasets)
    if export_format:
        _require_integration_format_scope(access, export_format)
    return access


def _require_jwt_integration_access(db: Session, project_id: int, raw_token: str) -> IntegrationAccess:
    try:
        claims = decode_access_token(raw_token, get_settings().auth_secret_key)
        tenant_id = int(claims["tenant_id"])
        user_id = int(claims["sub"])
    except (KeyError, TypeError, ValueError, TokenError) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc
    project = _require_project(db, tenant_id, project_id)
    membership = _require_membership(db, tenant_id, project_id, user_id)
    user = _require_user(db, tenant_id, user_id)
    return IntegrationAccess(
        tenant_id=tenant_id,
        project=project,
        membership=membership,
        allowed_datasets=list(INTEGRATION_DATASETS.keys()),
        allowed_formats=["json", "csv", "both", "xlsx"],
        actor_user_id=user_id,
        actor=user.email,
    )


def _require_integration_token_access(db: Session, project_id: int, raw_token: str) -> IntegrationAccess:
    token_hash = _integration_token_hash(raw_token)
    token = db.scalar(select(IntegrationToken).where(IntegrationToken.token_hash == token_hash))
    if not token or not hmac.compare_digest(token.token_hash, token_hash):
        raise HTTPException(status_code=401, detail="Invalid or expired integration token")
    if token.project_id != project_id:
        raise HTTPException(status_code=403, detail="Integration token is not scoped to this project")
    if token.status != "active" or token.expires_at <= utc_now():
        raise HTTPException(status_code=401, detail="Invalid or expired integration token")
    project = _require_project(db, token.tenant_id, project_id)
    membership = _require_membership(db, token.tenant_id, project_id, token.created_by_user_id)
    creator = _require_user(db, token.tenant_id, token.created_by_user_id)
    token.last_used_at = utc_now()
    token.updated_at = token.last_used_at
    db.commit()
    db.refresh(token)
    return IntegrationAccess(
        tenant_id=token.tenant_id,
        project=project,
        membership=membership,
        allowed_datasets=_split_csv(token.allowed_datasets),
        allowed_formats=_split_csv(token.allowed_formats),
        actor_user_id=token.created_by_user_id,
        actor=f"integration_token:{token.token_prefix}:{creator.email}",
        token=token,
    )


def _require_integration_dataset_scope(access: IntegrationAccess, datasets: list[str]) -> None:
    allowed = set(access.allowed_datasets)
    for dataset in datasets:
        if dataset not in allowed:
            raise HTTPException(status_code=403, detail=f"Integration token cannot access dataset: {dataset}")


def _require_integration_format_scope(access: IntegrationAccess, export_format: str) -> None:
    allowed = set(access.allowed_formats)
    if export_format == "both":
        if "both" in allowed or {"json", "csv"} <= allowed:
            return
    elif export_format in allowed or "both" in allowed:
        return
    raise HTTPException(status_code=403, detail=f"Integration token cannot use format: {export_format}")


def _validate_integration_token_datasets(datasets: list[str]) -> list[str]:
    normalized: list[str] = []
    for dataset in datasets:
        dataset_key = _normalize_integration_dataset(dataset)
        if not dataset_key:
            continue
        if dataset_key not in INTEGRATION_DATASETS:
            raise HTTPException(status_code=400, detail=f"Unsupported integration dataset: {dataset}")
        if dataset_key not in normalized:
            normalized.append(dataset_key)
    if not normalized:
        raise HTTPException(status_code=400, detail="At least one integration token dataset is required")
    if len(normalized) > 16:
        raise HTTPException(status_code=400, detail="Integration token cannot contain more than 16 datasets")
    return normalized


def _validate_integration_token_formats(formats: list[str]) -> list[str]:
    normalized: list[str] = []
    for item in formats:
        value = item.strip().lower()
        if not value:
            continue
        if value not in {"json", "csv", "both", "xlsx"}:
            raise HTTPException(status_code=400, detail=f"Unsupported integration token format: {item}")
        if value not in normalized:
            normalized.append(value)
    if not normalized:
        raise HTTPException(status_code=400, detail="At least one integration token format is required")
    return normalized


def _validate_integration_token_expiry(expires_in_days: int) -> int:
    if expires_in_days < 1:
        raise HTTPException(status_code=400, detail="Integration token expiry must be at least 1 day")
    if expires_in_days > INTEGRATION_TOKEN_MAX_DAYS:
        raise HTTPException(
            status_code=400, detail=f"Integration token expiry cannot exceed {INTEGRATION_TOKEN_MAX_DAYS} days"
        )
    return expires_in_days


def _integration_token_out(token: IntegrationToken) -> IntegrationTokenOut:
    return IntegrationTokenOut(
        id=token.id,
        project_id=token.project_id,
        name=token.name,
        token_prefix=token.token_prefix,
        datasets=_split_csv(token.allowed_datasets),
        formats=_split_csv(token.allowed_formats),
        status=token.status,
        created_by_user_id=token.created_by_user_id,
        created_at=token.created_at,
        expires_at=token.expires_at,
        last_used_at=token.last_used_at,
    )


def _integration_token_created(token: IntegrationToken, raw_token: str) -> IntegrationTokenCreated:
    token_out = _integration_token_out(token)
    return IntegrationTokenCreated(**token_out.model_dump(), token=raw_token)


def _integration_token_alert_summary(
    project_id: int,
    tokens: list[IntegrationToken],
    warning_days: int,
) -> IntegrationTokenAlertSummary:
    now = utc_now()
    alerts: list[IntegrationTokenAlertOut] = []
    active_count = 0
    expired_count = 0
    expiring_count = 0
    revoked_count = 0

    for token in tokens:
        if token.status == "revoked":
            revoked_count += 1
            continue
        if token.status != "active":
            continue

        active_count += 1
        days_to_expiry = _integration_token_days_to_expiry(token.expires_at, now)
        severity = ""
        message = ""
        if token.expires_at <= now:
            expired_count += 1
            severity = "critical"
            message = "Token expired; revoke or rotate immediately."
        elif days_to_expiry <= warning_days:
            expiring_count += 1
            severity = "warning"
            message = f"Token expires within {warning_days} days; rotate before expiry."

        if severity:
            alerts.append(
                IntegrationTokenAlertOut(
                    id=token.id,
                    project_id=token.project_id,
                    name=token.name,
                    token_prefix=token.token_prefix,
                    status=token.status,
                    datasets=_split_csv(token.allowed_datasets),
                    formats=_split_csv(token.allowed_formats),
                    expires_at=token.expires_at,
                    days_to_expiry=days_to_expiry,
                    severity=severity,
                    message=message,
                    last_used_at=token.last_used_at,
                )
            )

    return IntegrationTokenAlertSummary(
        project_id=project_id,
        warning_days=warning_days,
        generated_at=now,
        active_count=active_count,
        expiring_count=expiring_count,
        expired_count=expired_count,
        revoked_count=revoked_count,
        alerts=alerts,
    )


def _integration_token_days_to_expiry(expires_at: datetime, now: datetime) -> int:
    seconds = int((expires_at - now).total_seconds())
    if seconds >= 0:
        return (seconds + 86399) // 86400
    return -((-seconds + 86399) // 86400)


def _integration_export_log_out(log: IntegrationExportLog) -> IntegrationExportLogOut:
    return IntegrationExportLogOut(
        id=log.id,
        project_id=log.project_id,
        requested_by_user_id=log.requested_by_user_id,
        integration_token_id=log.integration_token_id,
        actor=log.actor,
        artifact_type=log.artifact_type,
        datasets=_split_csv(log.datasets),
        format=log.format,
        file_name=log.file_name,
        sha256=log.sha256,
        size_bytes=log.size_bytes,
        row_count=log.row_count,
        status=log.status,
        created_at=log.created_at,
    )


def _record_integration_download(
    db: Session,
    access: IntegrationAccess,
    artifact_type: str,
    datasets: list[str],
    export_format: str,
    file_name: str,
    content: bytes,
    row_count: int,
) -> IntegrationExportLog:
    log = IntegrationExportLog(
        tenant_id=access.tenant_id,
        project_id=access.project.id,
        requested_by_user_id=access.actor_user_id,
        integration_token_id=access.token.id if access.token else None,
        actor=access.actor,
        artifact_type=artifact_type,
        datasets=",".join(datasets),
        format=export_format,
        file_name=file_name,
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
        row_count=row_count,
        status="completed",
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def _generate_integration_token() -> str:
    return f"{INTEGRATION_TOKEN_PREFIX}{uuid4().hex[:8]}_{secrets.token_urlsafe(32)}"


def _integration_token_hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _integration_token_public_prefix(raw_token: str) -> str:
    return raw_token[:24]


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _integration_generated_at() -> str:
    return f"{utc_now().isoformat(timespec='seconds')}Z"


def _normalize_integration_dataset(dataset: str) -> str:
    return dataset.strip().lower().replace("-", "_")


def _parse_integration_dataset_list(datasets: str) -> list[str]:
    if datasets.strip().lower() == "all":
        return list(INTEGRATION_DATASETS.keys())
    dataset_keys: list[str] = []
    for raw_dataset in datasets.split(","):
        dataset_key = _normalize_integration_dataset(raw_dataset)
        if not dataset_key:
            continue
        if dataset_key not in INTEGRATION_DATASETS:
            raise HTTPException(status_code=400, detail=f"Unsupported integration dataset: {raw_dataset.strip()}")
        if dataset_key not in dataset_keys:
            dataset_keys.append(dataset_key)
    if not dataset_keys:
        raise HTTPException(status_code=400, detail="At least one integration dataset is required")
    if len(dataset_keys) > 16:
        raise HTTPException(status_code=400, detail="Integration package cannot contain more than 16 datasets")
    return dataset_keys


def _integration_dataset_fields(dataset: str) -> list[str]:
    schema = INTEGRATION_DATASETS[dataset]["schema"]
    return list(schema.model_fields.keys())


def _integration_dataset_rows(
    db: Session,
    tenant_id: int,
    project_id: int,
    membership: ProjectMembership,
    dataset: str,
) -> list[dict[str, object]]:
    if dataset == "wbs":
        records = db.scalars(
            select(WBS).where(WBS.tenant_id == tenant_id, WBS.project_id == project_id).order_by(WBS.code)
        ).all()
        return _integration_records_to_rows(WBSOut, records)
    if dataset == "control_accounts":
        records = db.scalars(
            select(ControlAccount)
            .where(ControlAccount.tenant_id == tenant_id, ControlAccount.project_id == project_id)
            .order_by(ControlAccount.code)
        ).all()
        return _integration_records_to_rows(ControlAccountOut, records)
    if dataset == "schedule_imports":
        records = db.scalars(
            select(ScheduleImport)
            .where(ScheduleImport.tenant_id == tenant_id, ScheduleImport.project_id == project_id)
            .order_by(ScheduleImport.imported_at.desc(), ScheduleImport.id.desc())
        ).all()
        return _integration_records_to_rows(ScheduleImportOut, records)
    if dataset == "schedule_validation_findings":
        latest_import = _latest_schedule_import(db, tenant_id, project_id)
        if not latest_import:
            return []
        records = db.scalars(
            select(ScheduleValidationFinding)
            .where(
                ScheduleValidationFinding.tenant_id == tenant_id,
                ScheduleValidationFinding.project_id == project_id,
                ScheduleValidationFinding.schedule_import_id == latest_import.id,
            )
            .order_by(ScheduleValidationFinding.severity, ScheduleValidationFinding.check_code)
        ).all()
        return _integration_records_to_rows(ScheduleValidationFindingOut, records)
    if dataset == "control_account_mappings":
        latest_import = _latest_schedule_import(db, tenant_id, project_id)
        if not latest_import:
            return []
        records = db.scalars(
            select(ControlAccountMapping)
            .where(
                ControlAccountMapping.tenant_id == tenant_id,
                ControlAccountMapping.project_id == project_id,
                ControlAccountMapping.schedule_import_id == latest_import.id,
            )
            .order_by(ControlAccountMapping.wbs_code, ControlAccountMapping.cbs_code, ControlAccountMapping.id)
        ).all()
        return _integration_records_to_rows(ControlAccountMappingOut, records)
    if dataset == "cost_sheet":
        return _integration_records_to_rows(CostSheetLineOut, _cost_sheet_lines(db, tenant_id, project_id))
    if dataset == "funding_sources":
        return _integration_records_to_rows(FundingSourceOut, _funding_sources(db, tenant_id, project_id))
    if dataset == "cash_flow":
        return _integration_records_to_rows(CashFlowPeriodOut, _cash_flow_periods(db, tenant_id, project_id))
    if dataset == "progress_records":
        records = db.scalars(
            select(ProgressRecord)
            .where(ProgressRecord.tenant_id == tenant_id, ProgressRecord.project_id == project_id)
            .order_by(ProgressRecord.reported_on.desc(), ProgressRecord.id.desc())
        ).all()
        return _integration_records_to_rows(ProgressRecordOut, records)
    if dataset == "cost_records":
        records = db.scalars(
            select(CostRecord)
            .where(CostRecord.tenant_id == tenant_id, CostRecord.project_id == project_id)
            .order_by(CostRecord.incurred_on.desc(), CostRecord.id.desc())
        ).all()
        return _integration_records_to_rows(CostRecordOut, records)
    if dataset == "contracts":
        records = db.scalars(
            select(Contract)
            .where(Contract.tenant_id == tenant_id, Contract.project_id == project_id)
            .order_by(Contract.code)
        ).all()
        return _integration_records_to_rows(ContractOut, records)
    if dataset == "purchase_orders":
        return _integration_records_to_rows(PurchaseOrderOut, _purchase_orders(db, tenant_id, project_id))
    if dataset == "payment_certificates":
        return _integration_records_to_rows(PaymentCertificateOut, _payment_certificates(db, tenant_id, project_id))
    if dataset == "warehouse_receipts":
        return _integration_records_to_rows(WarehouseReceiptOut, _warehouse_receipts(db, tenant_id, project_id))
    if dataset == "documents":
        return _integration_records_to_rows(
            DocumentOut, documents_domain._accessible_documents(db, tenant_id, project_id, membership)
        )
    if dataset == "document_attachments":
        return _integration_records_to_rows(
            DocumentAttachmentOut,
            documents_domain._accessible_document_attachments(db, tenant_id, project_id, membership),
        )
    raise HTTPException(status_code=400, detail=f"Unsupported integration dataset: {dataset}")


def _integration_records_to_rows(schema, records) -> list[dict[str, object]]:
    return [schema.model_validate(record).model_dump(mode="json") for record in records]


def _integration_rows_to_csv(rows: list[dict[str, object]], fields: list[str]) -> str:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _integration_workbook_bytes(project: Project, generated_at: str, datasets: list[dict[str, object]]) -> bytes:
    sheets: list[dict[str, object]] = []
    summary_rows = [
        ["P&Pmis Construction AI Integration Workbook"],
        ["Project code", project.code],
        ["Project name", project.name],
        ["Generated at", generated_at],
        ["Mode", "read_only"],
        [],
        ["Dataset", "Label", "Rows", "Fields"],
    ]
    for dataset in datasets:
        fields = list(dataset["fields"])
        rows = list(dataset["rows"])
        summary_rows.append([dataset["key"], dataset["label"], len(rows), ", ".join(fields)])
    sheets.append({"name": "Summary", "rows": summary_rows, "freeze_header": False})

    used_names = {"Summary"}
    for dataset in datasets:
        fields = list(dataset["fields"])
        data_rows = [
            fields,
            *[[row.get(field, "") for field in fields] for row in list(dataset["rows"])],
        ]
        sheet_name = _xlsx_unique_sheet_name(_xlsx_sheet_name(str(dataset["key"])), used_names)
        used_names.add(sheet_name)
        sheets.append({"name": sheet_name, "rows": data_rows, "freeze_header": True})

    workbook = BytesIO()
    with ZipFile(workbook, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _xlsx_content_types(len(sheets)))
        archive.writestr("_rels/.rels", _xlsx_root_relationships())
        archive.writestr("xl/workbook.xml", _xlsx_workbook_xml([str(sheet["name"]) for sheet in sheets]))
        archive.writestr("xl/_rels/workbook.xml.rels", _xlsx_workbook_relationships(len(sheets)))
        archive.writestr("xl/styles.xml", _xlsx_styles_xml())
        archive.writestr("docProps/core.xml", _xlsx_core_properties(generated_at))
        archive.writestr("docProps/app.xml", _xlsx_app_properties([str(sheet["name"]) for sheet in sheets]))
        for index, sheet in enumerate(sheets, start=1):
            archive.writestr(
                f"xl/worksheets/sheet{index}.xml",
                _xlsx_worksheet_xml(list(sheet["rows"]), bool(sheet["freeze_header"])),
            )
    return workbook.getvalue()


def _xlsx_content_types(sheet_count: int) -> str:
    worksheet_overrides = "".join(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in range(1, sheet_count + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        f"{worksheet_overrides}"
        "</Types>"
    )


def _xlsx_root_relationships() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        "</Relationships>"
    )


def _xlsx_workbook_xml(sheet_names: list[str]) -> str:
    sheets = "".join(
        f'<sheet name="{_xml_attr(name)}" sheetId="{index}" r:id="rId{index}"/>'
        for index, name in enumerate(sheet_names, start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{sheets}</sheets>"
        "</workbook>"
    )


def _xlsx_workbook_relationships(sheet_count: int) -> str:
    relationships = "".join(
        f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, sheet_count + 1)
    )
    styles_id = sheet_count + 1
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{relationships}"
        f'<Relationship Id="rId{styles_id}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        "</Relationships>"
    )


def _xlsx_styles_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="3">'
        '<font><sz val="10"/><name val="Calibri"/></font>'
        '<font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font>'
        '<font><b/><sz val="13"/><color rgb="FF17324D"/><name val="Calibri"/></font>'
        "</fonts>"
        '<fills count="3">'
        '<fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill>'
        '<fill><patternFill patternType="solid"><fgColor rgb="FF0F6B78"/><bgColor indexed="64"/></patternFill></fill>'
        "</fills>"
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="3">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>'
        '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
        "</cellXfs>"
        '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
        "</styleSheet>"
    )


def _xlsx_core_properties(generated_at: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        "<dc:creator>Codex</dc:creator>"
        "<cp:lastModifiedBy>Codex</cp:lastModifiedBy>"
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{_xml_text(generated_at)}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{_xml_text(generated_at)}</dcterms:modified>'
        "</cp:coreProperties>"
    )


def _xlsx_app_properties(sheet_names: list[str]) -> str:
    titles = "".join(f"<vt:lpstr>{_xml_text(name)}</vt:lpstr>" for name in sheet_names)
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        "<Application>P&amp;Pmis Construction AI</Application>"
        '<HeadingPairs><vt:vector size="2" baseType="variant"><vt:variant><vt:lpstr>Worksheets</vt:lpstr></vt:variant>'
        f"<vt:variant><vt:i4>{len(sheet_names)}</vt:i4></vt:variant></vt:vector></HeadingPairs>"
        f'<TitlesOfParts><vt:vector size="{len(sheet_names)}" baseType="lpstr">{titles}</vt:vector></TitlesOfParts>'
        "</Properties>"
    )


def _xlsx_worksheet_xml(rows: list[list[object]], freeze_header: bool) -> str:
    max_columns = max((len(row) for row in rows), default=1)
    column_widths = _xlsx_column_widths(rows, max_columns)
    columns = "".join(
        f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
        for index, width in enumerate(column_widths, start=1)
    )
    sheet_view = (
        '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        if freeze_header and rows
        else '<sheetViews><sheetView workbookViewId="0"/></sheetViews>'
    )
    xml_rows = []
    for row_index, row in enumerate(rows, start=1):
        cells = "".join(
            _xlsx_cell(value, row_index, column_index, _xlsx_cell_style(row_index, freeze_header))
            for column_index, value in enumerate(row, start=1)
        )
        xml_rows.append(f'<row r="{row_index}">{cells}</row>')
    auto_filter = ""
    if freeze_header and len(rows) > 1 and max_columns > 0:
        last_cell = f"{_excel_column_name(max_columns)}{len(rows)}"
        auto_filter = f'<autoFilter ref="A1:{last_cell}"/>'
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"{sheet_view}<cols>{columns}</cols><sheetData>{''.join(xml_rows)}</sheetData>{auto_filter}"
        "</worksheet>"
    )


def _xlsx_cell(value: object, row_index: int, column_index: int, style: int) -> str:
    ref = f"{_excel_column_name(column_index)}{row_index}"
    style_attr = f' s="{style}"' if style else ""
    if value is None:
        return f'<c r="{ref}"{style_attr}/>'
    if isinstance(value, bool):
        return f'<c r="{ref}" t="b"{style_attr}><v>{1 if value else 0}</v></c>'
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{ref}"{style_attr}><v>{value}</v></c>'
    return f'<c r="{ref}" t="inlineStr"{style_attr}><is><t>{_xml_text(str(value))}</t></is></c>'


def _xlsx_cell_style(row_index: int, freeze_header: bool) -> int:
    if row_index == 1:
        return 1 if freeze_header else 2
    return 0


def _xlsx_column_widths(rows: list[list[object]], max_columns: int) -> list[float]:
    widths: list[float] = []
    for column_index in range(max_columns):
        longest = 10
        for row in rows[:200]:
            if column_index < len(row) and row[column_index] is not None:
                longest = max(longest, min(len(str(row[column_index])), 48))
        widths.append(float(min(max(longest + 2, 12), 52)))
    return widths


def _xlsx_sheet_name(value: str) -> str:
    cleaned = "".join("_" if character in "[]:*?/\\'" else character for character in value.strip())
    return (cleaned or "Sheet")[:31]


def _xlsx_unique_sheet_name(value: str, used_names: set[str]) -> str:
    candidate = value[:31]
    suffix = 2
    while candidate in used_names:
        marker = f"_{suffix}"
        candidate = f"{value[: 31 - len(marker)]}{marker}"
        suffix += 1
    return candidate


def _excel_column_name(index: int) -> str:
    name = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        name = chr(65 + remainder) + name
    return name or "A"


def _xml_text(value: str) -> str:
    return escape(value, {"'": "&apos;", '"': "&quot;"})


def _xml_attr(value: str) -> str:
    return _xml_text(value)


def _integration_rows_to_json_bytes(rows: list[dict[str, object]]) -> bytes:
    return json.dumps(rows, indent=2, ensure_ascii=False).encode("utf-8")


def _integration_manifest_to_json_bytes(manifest: dict[str, object]) -> bytes:
    return json.dumps(manifest, indent=2, ensure_ascii=False).encode("utf-8")


def _integration_package_file_metadata(
    dataset: str,
    file_format: str,
    path: str,
    rows: list[dict[str, object]],
    fields: list[str],
    content: bytes,
) -> dict[str, object]:
    return {
        "dataset": dataset,
        "format": file_format,
        "path": path,
        "row_count": len(rows),
        "fields": fields,
        "size_bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _safe_integration_file_stem(value: str) -> str:
    safe = "".join(character if character.isalnum() or character in {"-", "_"} else "-" for character in value.strip())
    return safe.strip("-_") or "project"


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
        db.scalars(select(Contract).where(Contract.tenant_id == tenant_id, Contract.project_id == project_id)).all()
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
            payment_certificates_by_account[certificate.control_account_id] = (
                payment_certificates_by_account.get(certificate.control_account_id, 0) + certificate.certified_amount
            )

    warehouse_receipts_by_account: dict[int, float] = {}
    for receipt in warehouse_receipts:
        if receipt.control_account_id and receipt.status not in {"cancelled", "rejected", "void", "draft"}:
            warehouse_receipts_by_account[receipt.control_account_id] = (
                warehouse_receipts_by_account.get(receipt.control_account_id, 0) + receipt.received_value
            )

    legacy_actual_by_account: dict[int, float] = {}
    for record in cost_records:
        if record.source != CostSource.commitment:
            legacy_actual_by_account[record.control_account_id] = (
                legacy_actual_by_account.get(record.control_account_id, 0) + record.amount
            )

    contract_commitments_by_account: dict[int, float] = {}
    for contract in contracts:
        if contract.control_account_id and contract.status not in {"cancelled", "rejected", "void", "draft"}:
            contract_commitments_by_account[contract.control_account_id] = (
                contract_commitments_by_account.get(contract.control_account_id, 0) + contract.value
            )

    po_commitments_by_account: dict[int, float] = {}
    for order in purchase_orders:
        if order.control_account_id and order.status not in {"cancelled", "rejected", "void", "draft"}:
            po_commitments_by_account[order.control_account_id] = (
                po_commitments_by_account.get(order.control_account_id, 0) + order.committed_amount
            )

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
        raise HTTPException(
            status_code=400, detail="Warehouse receipt must have received value or quantity times unit cost"
        )


def _warehouse_received_value(received_quantity: float, unit_cost: float, received_value: float) -> float:
    return _money(received_value if received_value > 0 else received_quantity * unit_cost)


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
    audit_count = (
        db.scalar(
            select(func.count(AuditLog.id)).where(AuditLog.tenant_id == tenant_id, AuditLog.project_id == project_id)
        )
        or 0
    )
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
    open_blocking_constraints = (
        db.scalar(
            select(func.count(WorkPackageConstraint.id)).where(
                WorkPackageConstraint.tenant_id == tenant_id,
                WorkPackageConstraint.project_id == project_id,
                WorkPackageConstraint.blocking.is_(True),
                WorkPackageConstraint.status == "open",
            )
        )
        or 0
    )
    workflow_count = _count(db, BusinessProcessInstance, tenant_id, project_id)
    template_count = (
        db.scalar(select(func.count(BusinessProcessTemplate.id)).where(BusinessProcessTemplate.tenant_id == tenant_id))
        or 0
    )
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
        mapping_summary = _control_account_mapping_summary(
            mappings, latest_baseline.status if latest_baseline else "missing"
        )
        mapping_score = mapping_summary.mapping_score
        cost_loading_score = mapping_summary.cost_loading_score

    items = [
        _readiness_item(
            "Fase 1",
            "Schedule Intake / Data Quality",
            100
            if latest_import
            and latest_import.status == ImportStatus.validated
            and latest_import.quality_score >= 70
            and finding_errors == 0
            else max(latest_import.quality_score if latest_import else 0, 0),
            f"{schedule_activity_count} actividades, {relationship_count} relaciones, {finding_errors} errores y {finding_warnings} advertencias.",
            "Cargar cronograma fuente y cerrar errores DCMA/AACE antes del piloto.",
        ),
        _readiness_item(
            "Fase 2",
            "Business Process Engine / Plan de Control",
            min(
                (100 if workflow_count and template_count else 45) * 0.65 + _control_plan_score(control_plan) * 0.35,
                100,
            ),
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
            100
            if latest_kpi
            and snapshot_count
            and forecast_count
            and progress_count
            and payment_certificate_count
            and warehouse_receipt_count
            and purchase_order_count
            and funding_count
            and cash_flow_count
            else 55,
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
            min(
                (len(team) >= 5) * 30
                + (len(roles) >= 5) * 25
                + (audit_count > 0) * 20
                + (package_count > 0) * 15
                + (constraint_count >= 0) * 10,
                100,
            ),
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
    return (
        db.scalar(
            select(func.count(model.id)).where(
                model.tenant_id == tenant_id,
                model.project_id == project_id,
            )
        )
        or 0
    )


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


def _require_wbs(db: Session, tenant_id: int, project_id: int, wbs_id: int) -> WBS:
    wbs = db.scalar(select(WBS).where(WBS.id == wbs_id, WBS.project_id == project_id, WBS.tenant_id == tenant_id))
    if not wbs:
        raise HTTPException(status_code=404, detail="WBS not found")
    return wbs


def _require_cbs(db: Session, tenant_id: int, project_id: int, cbs_id: int) -> CostBreakdownStructure:
    cbs = db.scalar(
        select(CostBreakdownStructure).where(
            CostBreakdownStructure.id == cbs_id,
            CostBreakdownStructure.project_id == project_id,
            CostBreakdownStructure.tenant_id == tenant_id,
        )
    )
    if not cbs:
        raise HTTPException(status_code=404, detail="CBS not found")
    return cbs


def _require_activity_sheet(db: Session, tenant_id: int, project_id: int, activity_sheet_id: int) -> ActivitySheet:
    activity_sheet = db.scalar(
        select(ActivitySheet).where(
            ActivitySheet.id == activity_sheet_id,
            ActivitySheet.project_id == project_id,
            ActivitySheet.tenant_id == tenant_id,
        )
    )
    if not activity_sheet:
        raise HTTPException(status_code=404, detail="Activity sheet not found")
    return activity_sheet


def _require_rate_sheet(db: Session, tenant_id: int, project_id: int, rate_sheet_id: int) -> RateSheet:
    rate_sheet = db.scalar(
        select(RateSheet).where(
            RateSheet.id == rate_sheet_id,
            RateSheet.project_id == project_id,
            RateSheet.tenant_id == tenant_id,
        )
    )
    if not rate_sheet:
        raise HTTPException(status_code=404, detail="Rate sheet not found")
    return rate_sheet


def _require_business_process(
    db: Session,
    tenant_id: int,
    project_id: int,
    process_id: int,
) -> BusinessProcessInstance:
    process = db.scalar(
        select(BusinessProcessInstance).where(
            BusinessProcessInstance.id == process_id,
            BusinessProcessInstance.project_id == project_id,
            BusinessProcessInstance.tenant_id == tenant_id,
        )
    )
    if not process:
        raise HTTPException(status_code=404, detail="Business process not found")
    return process


def _require_business_process_line_item(
    db: Session,
    tenant_id: int,
    project_id: int,
    line_item_id: int,
) -> BusinessProcessLineItem:
    line = db.scalar(
        select(BusinessProcessLineItem).where(
            BusinessProcessLineItem.id == line_item_id,
            BusinessProcessLineItem.project_id == project_id,
            BusinessProcessLineItem.tenant_id == tenant_id,
        )
    )
    if not line:
        raise HTTPException(status_code=404, detail="Business process line item not found")
    return line


def _business_process_line_item_version(
    db: Session,
    tenant_id: int,
    project_id: int,
    line_item_id: int,
) -> int:
    latest_version = db.scalar(
        select(func.coalesce(func.max(BusinessProcessLineItemRevision.new_version), 1)).where(
            BusinessProcessLineItemRevision.tenant_id == tenant_id,
            BusinessProcessLineItemRevision.project_id == project_id,
            BusinessProcessLineItemRevision.line_item_id == line_item_id,
        )
    )
    return int(latest_version or 1)


def _business_process_line_item_out(
    db: Session,
    tenant_id: int,
    project_id: int,
    line: BusinessProcessLineItem,
) -> BusinessProcessLineItemOut:
    return BusinessProcessLineItemOut(
        id=line.id,
        process_instance_id=line.process_instance_id,
        line_type=line.line_type,
        wbs_id=line.wbs_id,
        cbs_id=line.cbs_id,
        funding_source_id=line.funding_source_id,
        control_account_id=line.control_account_id,
        cost_code_id=line.cost_code_id,
        amount=_money(line.amount),
        quantity=float(line.quantity or 0),
        description=line.description,
        status=line.status,
        version=_business_process_line_item_version(db, tenant_id, project_id, line.id),
        created_at=line.created_at,
        updated_at=line.updated_at,
    )


def _cost_code_from_parts(wbs_code: str, control_account_code: str, cbs_code: str) -> str:
    code = f"{wbs_code}-{control_account_code}-{cbs_code}".replace(" ", "-")
    while "--" in code:
        code = code.replace("--", "-")
    return code[:160]


def _rate_sheet_out(db: Session, tenant_id: int, project_id: int, sheet: RateSheet) -> RateSheetOut:
    lines = list(
        db.scalars(
            select(RateSheetLine)
            .where(
                RateSheetLine.tenant_id == tenant_id,
                RateSheetLine.project_id == project_id,
                RateSheetLine.rate_sheet_id == sheet.id,
            )
            .order_by(RateSheetLine.cbs_code)
        ).all()
    )
    return RateSheetOut(
        id=sheet.id,
        code=sheet.code,
        name=sheet.name,
        status=sheet.status,
        version=sheet.version,
        created_at=sheet.created_at,
        updated_at=sheet.updated_at,
        line_items=[RateSheetLineOut.model_validate(line) for line in lines],
    )


def _recost_run_out(
    db: Session,
    tenant_id: int,
    project_id: int,
    run: ActivitySheetRecostRun,
) -> ActivitySheetRecostRunOut:
    lines = list(
        db.scalars(
            select(ActivitySheetRecostRunLine)
            .where(
                ActivitySheetRecostRunLine.tenant_id == tenant_id,
                ActivitySheetRecostRunLine.project_id == project_id,
                ActivitySheetRecostRunLine.recost_run_id == run.id,
            )
            .order_by(ActivitySheetRecostRunLine.external_activity_id)
        ).all()
    )
    return ActivitySheetRecostRunOut(
        id=run.id,
        activity_sheet_id=run.activity_sheet_id,
        rate_sheet_id=run.rate_sheet_id,
        run_no=run.run_no,
        updated_rows=run.updated_rows,
        total_planned_cost=_money(run.total_planned_cost),
        total_planned_value=_money(run.total_planned_value),
        created_by=run.created_by,
        created_at=run.created_at,
        lines=[ActivitySheetRecostRunLineOut.model_validate(line) for line in lines],
    )


def _activity_sheet_mappings_by_external_id(
    db: Session,
    tenant_id: int,
    project_id: int,
    activity_sheet: ActivitySheet,
) -> dict[str, ControlAccountMapping]:
    schedule_rows = list(
        db.scalars(
            select(ScheduleActivityMap).where(
                ScheduleActivityMap.tenant_id == tenant_id,
                ScheduleActivityMap.project_id == project_id,
                ScheduleActivityMap.schedule_import_id == activity_sheet.schedule_import_id,
            )
        ).all()
    )
    schedule_row_by_id = {row.id: row for row in schedule_rows}
    mappings_by_external_id: dict[str, ControlAccountMapping] = {}
    for mapping in db.scalars(
        select(ControlAccountMapping).where(
            ControlAccountMapping.tenant_id == tenant_id,
            ControlAccountMapping.project_id == project_id,
            ControlAccountMapping.schedule_import_id == activity_sheet.schedule_import_id,
        )
    ).all():
        schedule_row = schedule_row_by_id.get(mapping.schedule_activity_map_id)
        if schedule_row:
            mappings_by_external_id[schedule_row.external_activity_id] = mapping
    return mappings_by_external_id


def _reconciliation_report_rows(db: Session, tenant_id: int, project_id: int) -> list[ReconciliationReportRow]:
    cost_codes = list(
        db.scalars(
            select(CostCode)
            .where(CostCode.tenant_id == tenant_id, CostCode.project_id == project_id)
            .order_by(CostCode.code)
        ).all()
    )
    wbs_by_id = {
        row.id: row
        for row in db.scalars(select(WBS).where(WBS.tenant_id == tenant_id, WBS.project_id == project_id)).all()
    }
    account_by_id = {
        row.id: row
        for row in db.scalars(
            select(ControlAccount).where(ControlAccount.tenant_id == tenant_id, ControlAccount.project_id == project_id)
        ).all()
    }
    cbs_by_id = {
        row.id: row
        for row in db.scalars(
            select(CostBreakdownStructure).where(
                CostBreakdownStructure.tenant_id == tenant_id,
                CostBreakdownStructure.project_id == project_id,
            )
        ).all()
    }
    fbs_by_id = {
        row.id: row
        for row in db.scalars(
            select(FundingSource).where(FundingSource.tenant_id == tenant_id, FundingSource.project_id == project_id)
        ).all()
    }
    contracts_by_code = {
        row.code: row
        for row in db.scalars(
            select(Contract).where(Contract.tenant_id == tenant_id, Contract.project_id == project_id)
        ).all()
    }
    rows: list[ReconciliationReportRow] = []
    for cost_code in cost_codes:
        wbs = wbs_by_id.get(cost_code.wbs_id)
        account = account_by_id.get(cost_code.control_account_id)
        cbs = cbs_by_id.get(cost_code.cbs_id)
        fbs = fbs_by_id.get(cost_code.fbs_id)
        contract = contracts_by_code.get(cost_code.contract_ref)
        sov_amount = 0.0
        funded_amount = 0.0
        if contract:
            sov_amount = float(
                db.scalar(
                    select(func.coalesce(func.sum(ScheduleOfValueLine.amount), 0)).where(
                        ScheduleOfValueLine.tenant_id == tenant_id,
                        ScheduleOfValueLine.project_id == project_id,
                        ScheduleOfValueLine.contract_id == contract.id,
                        ScheduleOfValueLine.cbs_id == cost_code.cbs_id,
                        ScheduleOfValueLine.status != "cancelled",
                    )
                )
                or 0
            )
            funded_amount = float(
                db.scalar(
                    select(func.coalesce(func.sum(CommitmentFundingLine.amount), 0)).where(
                        CommitmentFundingLine.tenant_id == tenant_id,
                        CommitmentFundingLine.project_id == project_id,
                        CommitmentFundingLine.contract_id == contract.id,
                        CommitmentFundingLine.funding_source_id == cost_code.fbs_id,
                        CommitmentFundingLine.status != "cancelled",
                    )
                )
                or 0
            )
        rows.append(
            ReconciliationReportRow(
                wbs_code=wbs.code if wbs else "",
                cbs_code=cbs.code if cbs else "",
                fbs_code=fbs.code if fbs else "",
                control_account_code=account.code if account else "",
                contract_ref=cost_code.contract_ref,
                budget=_money(cost_code.budget),
                committed=_money(cost_code.commitments),
                funded_amount=_money(funded_amount),
                sov_amount=_money(sov_amount),
                forecast=_money(cost_code.forecast),
                variance=_money(cost_code.budget - cost_code.forecast),
            )
        )
    return sorted(rows, key=lambda row: (row.wbs_code, row.cbs_code, row.contract_ref))


def _control_agent_run_out(
    db: Session,
    tenant_id: int,
    project_id: int,
    run: ControlAgentRun,
) -> ControlAgentRunOut:
    severity_order = {"high": 0, "medium": 1, "low": 2, "info": 3}
    findings = list(
        db.scalars(
            select(ControlAgentFinding).where(
                ControlAgentFinding.tenant_id == tenant_id,
                ControlAgentFinding.project_id == project_id,
                ControlAgentFinding.run_id == run.id,
            )
        ).all()
    )
    findings.sort(key=lambda finding: (severity_order.get(finding.severity, 9), finding.id))
    return ControlAgentRunOut(
        id=run.id,
        project_id=run.project_id,
        agent_code=run.agent_code,
        agent_name=run.agent_name,
        run_mode=run.run_mode,
        model_name=run.model_name,
        status=run.status,
        score=run.score,
        summary=run.summary,
        created_by=run.created_by,
        created_at=run.created_at,
        findings=[ControlAgentFindingOut.model_validate(finding) for finding in findings],
    )


def _reconciliation_xlsx_bytes(rows: list[ReconciliationReportRow]) -> bytes:
    headers = [
        "WBS",
        "CBS",
        "FBS",
        "Control Account",
        "Contract",
        "Budget",
        "Committed",
        "Funding",
        "SOV",
        "Forecast",
        "Variance",
    ]
    values = [
        [
            row.wbs_code,
            row.cbs_code,
            row.fbs_code,
            row.control_account_code,
            row.contract_ref,
            row.budget,
            row.committed,
            row.funded_amount,
            row.sov_amount,
            row.forecast,
            row.variance,
        ]
        for row in rows
    ]
    sheet_rows = [headers, *values]

    def col_name(index: int) -> str:
        name = ""
        while index:
            index, remainder = divmod(index - 1, 26)
            name = chr(65 + remainder) + name
        return name

    def cell(row_index: int, column_index: int, value: object) -> str:
        cell_ref = f"{col_name(column_index)}{row_index}"
        if isinstance(value, int | float):
            return f'<c r="{cell_ref}"><v>{float(value):.2f}</v></c>'
        text = escape(str(value or ""), {'"': "&quot;"})
        return f'<c r="{cell_ref}" t="inlineStr"><is><t>{text}</t></is></c>'

    sheet_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
        + "".join(
            f'<row r="{row_index}">'
            + "".join(cell(row_index, column_index, value) for column_index, value in enumerate(row_values, start=1))
            + "</row>"
            for row_index, row_values in enumerate(sheet_rows, start=1)
        )
        + "</sheetData></worksheet>"
    )
    workbook_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="Reconciliation" sheetId="1" r:id="rId1"/></sheets></workbook>'
    )
    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        'Target="worksheets/sheet1.xml"/></Relationships>'
    )
    package_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
        'Target="xl/workbook.xml"/></Relationships>'
    )
    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        "</Types>"
    )
    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", package_rels)
        archive.writestr("xl/workbook.xml", workbook_xml)
        archive.writestr("xl/_rels/workbook.xml.rels", workbook_rels)
        archive.writestr("xl/worksheets/sheet1.xml", sheet_xml)
    return buffer.getvalue()


def _reconciliation_pdf_bytes(project_id: int, rows: list[ReconciliationReportRow]) -> bytes:
    def pdf_text(value: object, limit: int = 120) -> str:
        text = str(value or "")[:limit]
        return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    lines = [
        f"Reconciliation Report - Project {project_id}",
        f"Rows: {len(rows)}",
        "",
        "WBS | CBS | FBS | Contract | Budget | Forecast | Variance",
    ]
    for row in rows[:32]:
        lines.append(
            " | ".join(
                [
                    row.wbs_code,
                    row.cbs_code,
                    row.fbs_code,
                    row.contract_ref,
                    f"{row.budget:.2f}",
                    f"{row.forecast:.2f}",
                    f"{row.variance:.2f}",
                ]
            )
        )
    if len(rows) > 32:
        lines.append(f"... {len(rows) - 32} more rows")

    content = "BT\n/F1 10 Tf\n13 TL\n40 792 Td\n" + "\n".join(f"({pdf_text(line)}) Tj\nT*" for line in lines) + "\nET"
    content_bytes = content.encode("latin-1", errors="replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(content_bytes)).encode("ascii") + b" >>\nstream\n" + content_bytes + b"\nendstream",
    ]
    output = BytesIO()
    output.write(b"%PDF-1.4\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(output.tell())
        output.write(f"{index} 0 obj\n".encode("ascii"))
        output.write(obj)
        output.write(b"\nendobj\n")
    xref_offset = output.tell()
    output.write(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    output.write(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        output.write(f"{offset:010d} 00000 n \n".encode("ascii"))
    output.write(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return output.getvalue()


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


def _validate_awp_package_hierarchy(parent: WorkPackage | None, package_type: str) -> None:
    if parent is None:
        return
    parent_type = parent.package_type.upper()
    if parent_type not in AWP_PACKAGE_LEVELS:
        raise HTTPException(status_code=400, detail="Parent AWP package type is not supported")
    if AWP_PACKAGE_LEVELS[package_type] <= AWP_PACKAGE_LEVELS[parent_type]:
        raise HTTPException(
            status_code=400, detail="AWP package hierarchy must move from area to more detailed package"
        )


def _normalize_awp_constraint_priority(priority: str) -> str:
    normalized = priority.strip().lower()
    if normalized not in AWP_CONSTRAINT_PRIORITIES:
        raise HTTPException(status_code=400, detail="Unsupported AWP constraint priority")
    return normalized


def _apply_awp_constraint_closure(constraint: WorkPackageConstraint, actor: str) -> None:
    if constraint.status == "closed":
        constraint.closed_by = constraint.closed_by or actor
        constraint.closed_on = constraint.closed_on or utc_now().date()
        return
    constraint.closed_by = ""
    constraint.closed_on = None


def _validate_control_account_status(status: str) -> None:
    if status not in CONTROL_ACCOUNT_STATUSES:
        raise HTTPException(status_code=400, detail="Unsupported control account lifecycle status")


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
    mapped = sum(
        1
        for mapping in mappings
        if mapping.control_account_id and mapping.status in {"mapped", "approved", "needs_cost_loading"}
    )
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
    ready_for_release = sum(
        1
        for package in packages
        if package.readiness_status in ready_statuses and package.id not in blocked_package_ids
    )
    readiness_score = round((ready_for_release / total_packages) * 100, 1) if total_packages else 0
    return AWPReadinessSummary(
        total_packages=total_packages,
        cwp_count=sum(1 for package in packages if package.package_type == "CWP"),
        iwp_count=sum(1 for package in packages if package.package_type == "IWP"),
        twp_count=sum(1 for package in packages if package.package_type == "TWP"),
        top_count=sum(1 for package in packages if package.package_type == "TOP"),
        ready_for_release=ready_for_release,
        blocked_packages=len(blocked_package_ids),
        open_constraints=len(open_constraints),
        blocking_constraints=len(blocking_constraints),
        high_priority_constraints=sum(
            1 for constraint in open_constraints if constraint.priority in {"high", "critical"}
        ),
        closure_evidence_count=sum(
            1 for constraint in constraints if constraint.status == "closed" and bool(constraint.evidence_ref.strip())
        ),
        readiness_score=readiness_score,
    )


def _default_wbs(db: Session, tenant_id: int, project_id: int) -> WBS:
    wbs = db.scalars(
        select(WBS).where(WBS.tenant_id == tenant_id, WBS.project_id == project_id).order_by(WBS.code)
    ).first()
    if wbs:
        return wbs
    wbs = WBS(tenant_id=tenant_id, project_id=project_id, parent_id=None, code="1.0", name="Project Control Baseline")
    db.add(wbs)
    db.flush()
    return wbs


def _schedule_quality_metrics(
    schedule_import: ScheduleImport | None,
    activities: list[ScheduleActivityMap],
    relationships: list[ActivityRelationship],
) -> list[ScheduleQualityMetricOut]:
    if not schedule_import:
        return []

    total_activities = len(activities)
    total_relationships = len(relationships)
    activity_ids = {activity.external_activity_id for activity in activities if activity.external_activity_id}
    logic_ids = {
        external_id
        for relationship in relationships
        for external_id in (relationship.predecessor_external_id, relationship.successor_external_id)
        if external_id
    }
    missing_logic = len(activity_ids - logic_ids) if total_activities else 0
    leads = sum(1 for relationship in relationships if relationship.lag_days < 0)
    lags = sum(1 for relationship in relationships if relationship.lag_days > 0)
    non_finish_start = sum(1 for relationship in relationships if _relationship_type_value(relationship) != "FS")
    high_float = sum(1 for activity in activities if activity.total_float_days > 44)
    negative_float = sum(1 for activity in activities if activity.total_float_days < 0)
    high_duration = sum(
        1
        for activity in activities
        if activity.planned_start
        and activity.planned_finish
        and (activity.planned_finish - activity.planned_start).days > 44
    )
    invalid_dates = sum(
        1
        for activity in activities
        if not activity.planned_start
        or not activity.planned_finish
        or (activity.planned_start and activity.planned_finish and activity.planned_finish < activity.planned_start)
    )
    cost_loaded = schedule_import.cost_loaded_activity_count or 0
    cost_missing = max(total_activities - cost_loaded, 0)

    return [
        _quality_metric(
            "dcma_logic",
            "DCMA 01",
            "Logic",
            missing_logic,
            total_activities,
            "<= 5% missing logic",
            "Activities not connected by predecessor or successor logic.",
            _threshold_status(_percent(missing_logic, total_activities), 5, 10),
        ),
        _quality_metric(
            "dcma_leads",
            "DCMA 02",
            "Leads",
            leads,
            total_relationships,
            "0 leads",
            "Relationships with negative lag.",
            "pass" if leads == 0 else "fail",
        ),
        _quality_metric(
            "dcma_lags",
            "DCMA 03",
            "Lags",
            lags,
            total_relationships,
            "<= 5% lagged relationships",
            "Relationships with positive lag.",
            _threshold_status(_percent(lags, total_relationships), 5, 10),
        ),
        _quality_metric(
            "dcma_relationship_types",
            "DCMA 04",
            "Relationship Types",
            non_finish_start,
            total_relationships,
            "<= 10% non-FS relationships",
            "Relationships that are not finish-to-start.",
            _threshold_status(_percent(non_finish_start, total_relationships), 10, 20),
        ),
        ScheduleQualityMetricOut(
            key="dcma_hard_constraints",
            standard="DCMA 05",
            label="Hard Constraints",
            status="not_available",
            item_count=0,
            total_count=0,
            percent=0,
            threshold="Requires constraint fields in source export",
            description="Hard constraint dates are not exposed by the current XER/XML mapper.",
        ),
        _quality_metric(
            "dcma_high_float",
            "DCMA 06",
            "High Float",
            high_float,
            total_activities,
            "<= 5% over 44 days",
            "Activities with total float greater than 44 days.",
            _threshold_status(_percent(high_float, total_activities), 5, 10),
        ),
        _quality_metric(
            "dcma_negative_float",
            "DCMA 07",
            "Negative Float",
            negative_float,
            total_activities,
            "0 activities",
            "Activities with negative total float.",
            "pass" if negative_float == 0 else "fail",
        ),
        _quality_metric(
            "dcma_high_duration",
            "DCMA 08",
            "High Duration",
            high_duration,
            total_activities,
            "<= 5% over 44 days",
            "Activities with baseline duration greater than 44 calendar days.",
            _threshold_status(_percent(high_duration, total_activities), 5, 10),
        ),
        _quality_metric(
            "dcma_invalid_dates",
            "DCMA 09",
            "Invalid Dates",
            invalid_dates,
            total_activities,
            "0 missing or invalid dates",
            "Activities missing start/finish dates or with finish before start.",
            "pass" if invalid_dates == 0 else "fail",
        ),
        _quality_metric(
            "dcma_cost_loading",
            "DCMA 10",
            "Cost / Resource Loading",
            cost_missing,
            total_activities,
            ">= 80% activities cost-loaded",
            "Activities without cost-loaded values from the schedule import.",
            _coverage_status(schedule_import.cost_loaded_activity_percent),
            percent=round(100 - schedule_import.cost_loaded_activity_percent, 2),
        ),
    ]


def _quality_metric(
    key: str,
    standard: str,
    label: str,
    item_count: int,
    total_count: int,
    threshold: str,
    description: str,
    status: str,
    percent: float | None = None,
) -> ScheduleQualityMetricOut:
    return ScheduleQualityMetricOut(
        key=key,
        standard=standard,
        label=label,
        status=status,
        item_count=item_count,
        total_count=total_count,
        percent=_percent(item_count, total_count) if percent is None else percent,
        threshold=threshold,
        description=description,
    )


def _percent(item_count: int, total_count: int) -> float:
    return round(item_count / total_count * 100, 2) if total_count else 0


def _threshold_status(percent: float, pass_threshold: float, review_threshold: float) -> str:
    if percent <= pass_threshold:
        return "pass"
    if percent <= review_threshold:
        return "review"
    return "fail"


def _coverage_status(percent: float) -> str:
    if percent >= 80:
        return "pass"
    if percent >= 50:
        return "review"
    return "fail"


def _relationship_type_value(relationship: ActivityRelationship) -> str:
    value = getattr(relationship.relationship_type, "value", relationship.relationship_type)
    return str(value or "").upper()


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
            finding="Imported schedule activities are available for control account mapping."
            if mapping_passed
            else "No imported activities are available.",
            owner_role="Project Controls",
        ),
        DataQualityGateOut(
            name="Cost Loading",
            status="Pass" if cost_loaded else "Review",
            score=100 if cost_loaded else 60,
            finding="Cost-loaded schedule values were found."
            if cost_loaded
            else "No cost-loaded activity values found; budget loading is required before reliable EVM.",
            owner_role="Cost Controller",
        ),
        DataQualityGateOut(
            name="Control Capture",
            status="Open" if schedule_passed else "Blocked",
            score=85 if schedule_passed else 0,
            finding="Progress and actual cost capture can feed the Control Core."
            if schedule_passed
            else "Control capture waits for an accepted baseline.",
            owner_role="Execution Lead",
        ),
    ]


def _configured_process_templates(db: Session, tenant_id: int) -> list[ProcessTemplateOut]:
    templates = list(
        db.scalars(
            select(BusinessProcessTemplate)
            .where(BusinessProcessTemplate.tenant_id == tenant_id)
            .options(
                selectinload(BusinessProcessTemplate.steps),
                selectinload(BusinessProcessTemplate.transitions),
            )
            .order_by(BusinessProcessTemplate.category, BusinessProcessTemplate.code)
        ).all()
    )
    if templates:
        return [_process_template_out(db, template) for template in templates]
    return [_catalog_process_template_out(template) for template in DEFAULT_PROCESS_TEMPLATES]


def _process_template_out(db: Session, template: BusinessProcessTemplate) -> ProcessTemplateOut:
    steps = sorted(template.steps, key=lambda s: s.step_order)
    transitions = sorted(template.transitions, key=lambda t: t.id)
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
            .where(
                BusinessProcessStepTemplate.tenant_id == tenant_id,
                BusinessProcessStepTemplate.template_id == template.id,
            )
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
    process = db.scalar(
        select(BusinessProcessInstance).where(
            BusinessProcessInstance.tenant_id == tenant_id, BusinessProcessInstance.id == process_id
        )
    )
    if not process:
        return ""
    transition = _configured_transition(db, tenant_id, process.process_code, process.current_step, action)
    if not transition:
        return ""
    if transition.permission_key:
        return transition.permission_key
    return "can_approve_workflow" if transition.requires_approval else ""


def _workflow_process_policy(
    db: Session,
    tenant_id: int,
    project_id: int,
    process_code: str,
    action: str,
) -> BusinessProcessPolicy | None:
    return db.scalar(
        select(BusinessProcessPolicy).where(
            BusinessProcessPolicy.tenant_id == tenant_id,
            BusinessProcessPolicy.project_id == project_id,
            BusinessProcessPolicy.process_code == process_code,
            BusinessProcessPolicy.action == action.strip().lower(),
            BusinessProcessPolicy.status == "active",
        )
    )


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
