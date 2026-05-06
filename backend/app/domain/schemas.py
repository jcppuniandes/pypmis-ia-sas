from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    phase: str
    currency: str
    start_date: date | None
    finish_date: date | None


class ProjectCreate(BaseModel):
    code: str
    name: str
    phase: str = "Planning"
    currency: str = "USD"
    start_date: date | None = None
    finish_date: date | None = None


class ProjectControlPlanOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    execution_strategy: str
    control_strategy: str
    progress_measurement_rule: str
    cost_measurement_rule: str
    change_management_rule: str
    risk_management_rule: str
    procurement_strategy: str
    document_control_rule: str
    reporting_cadence: str
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class ProjectControlPlanUpdate(BaseModel):
    execution_strategy: str | None = None
    control_strategy: str | None = None
    progress_measurement_rule: str | None = None
    cost_measurement_rule: str | None = None
    change_management_rule: str | None = None
    risk_management_rule: str | None = None
    procurement_strategy: str | None = None
    document_control_rule: str | None = None
    reporting_cadence: str | None = None
    status: str | None = None
    expected_version: int | None = None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    full_name: str
    title: str
    status: str


class UserCreate(BaseModel):
    email: str
    full_name: str
    title: str = ""
    password: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str
    tenant_id: int | None = None
    tenant_slug: str = "demo-energy"


class AuthSessionOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    tenant_id: int
    user: UserOut


class RoleProfileOut(BaseModel):
    role: str
    description: str
    can_capture_progress: bool
    can_capture_cost: bool
    can_approve_workflow: bool
    can_manage_contract: bool
    can_configure: bool


class ProjectMembershipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    user_id: int
    role: str
    can_capture_progress: bool
    can_capture_cost: bool
    can_approve_workflow: bool
    can_manage_contract: bool
    can_configure: bool


class ProjectMembershipCreate(BaseModel):
    user_id: int
    role: str


class ProjectTeamMemberOut(BaseModel):
    user: UserOut
    membership: ProjectMembershipOut


class ControlAccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    responsible: str
    discipline: str
    version: int
    updated_at: datetime


class ControlAccountCreate(BaseModel):
    wbs_id: int | None = None
    code: str
    name: str
    responsible: str
    discipline: str


class ControlAccountUpdate(BaseModel):
    code: str | None = None
    name: str | None = None
    responsible: str | None = None
    discipline: str | None = None
    expected_version: int | None = None


class WBSOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    parent_id: int | None
    code: str
    name: str


class ActivityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    control_account_id: int
    code: str
    name: str
    logic_type: str
    baseline_start: date | None
    baseline_finish: date | None
    planned_percent: float
    critical_path: bool
    lookahead_window: str


class ActivityCreate(BaseModel):
    control_account_id: int
    code: str
    name: str
    logic_type: str = "FS"
    baseline_start: date | None = None
    baseline_finish: date | None = None
    planned_percent: float = 0
    critical_path: bool = False
    lookahead_window: str = "6W"


class CostRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    control_account_id: int
    source: str
    amount: float
    incurred_on: date
    description: str


class CostRecordCreate(BaseModel):
    control_account_id: int
    source: str
    amount: float
    incurred_on: date
    description: str


class FundingSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    code: str
    name: str
    amount: float
    currency: str
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class FundingSourceCreate(BaseModel):
    code: str
    name: str
    amount: float
    currency: str = "USD"
    status: str = "approved"


class FundingSourceUpdate(BaseModel):
    name: str | None = None
    amount: float | None = None
    currency: str | None = None
    status: str | None = None
    expected_version: int | None = None


class CashFlowPeriodOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    period_label: str
    planned_inflow: float
    planned_outflow: float
    actual_inflow: float
    actual_outflow: float
    forecast_outflow: float
    version: int
    created_at: datetime
    updated_at: datetime


class CashFlowPeriodCreate(BaseModel):
    period_label: str
    planned_inflow: float = 0
    planned_outflow: float = 0
    actual_inflow: float = 0
    actual_outflow: float = 0
    forecast_outflow: float = 0


class CashFlowPeriodUpdate(BaseModel):
    planned_inflow: float | None = None
    planned_outflow: float | None = None
    actual_inflow: float | None = None
    actual_outflow: float | None = None
    forecast_outflow: float | None = None
    expected_version: int | None = None


class CostSheetLineOut(BaseModel):
    control_account_id: int
    control_account_code: str
    control_account_name: str
    cbs_code: str
    bac: float
    planned_value: float
    actual_cost: float
    committed_cost: float
    earned_value: float
    variance: float
    cpi: float


class CostManagerSummaryOut(BaseModel):
    total_bac: float
    total_planned_value: float
    total_earned_value: float
    total_actual_cost: float
    total_committed_cost: float
    total_funding: float
    planned_inflow: float
    actual_inflow: float
    planned_outflow: float
    actual_outflow: float
    forecast_outflow: float
    cost_variance: float
    funding_variance: float
    funding_coverage_percent: float
    cash_flow_variance: float


class ProgressRecordOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    control_account_id: int
    physical_percent: float
    quantity_installed: float
    labor_hours: float
    reported_on: date
    evidence_ref: str


class ProgressRecordCreate(BaseModel):
    control_account_id: int
    physical_percent: float
    quantity_installed: float
    labor_hours: float
    reported_on: date
    evidence_ref: str = ""


class DataQualityGateOut(BaseModel):
    name: str
    status: str
    score: float
    finding: str
    owner_role: str


class KPIOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    control_account_id: int | None
    period: str
    pv: float
    ev: float
    ac: float
    spi: float
    cpi: float
    sv: float
    cv: float
    bac: float
    eac: float
    etc: float
    vac: float
    created_at: datetime


class ControlSnapshotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    control_account_id: int | None
    period_label: str
    data_date: date | None
    pv: float
    ev: float
    ac: float
    spi: float
    cpi: float
    sv: float
    cv: float
    bac: float
    eac: float
    etc: float
    vac: float
    productivity_index: float | None
    created_at: datetime


class ForecastScenarioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    period_label: str
    name: str
    method: str
    cpi_factor: float
    spi_factor: float
    eac: float
    etc: float
    vac: float
    completion_risk: str
    summary: str
    created_at: datetime


class ProductivitySummary(BaseModel):
    total_quantity: float
    total_labor_hours: float
    productivity_rate: float
    productivity_index: float
    low_productivity_accounts: int


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    control_account_id: int | None
    severity: str
    rule: str
    message: str
    recommendation: str
    status: str
    created_at: datetime


class ScheduleImportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source: str
    file_name: str
    status: str
    data_date: date | None
    baseline_name: str
    quality_score: float
    validation_summary: str
    imported_at: datetime


class ScheduleActivityMapOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    schedule_import_id: int
    activity_id: int | None
    external_activity_id: str
    wbs_code: str
    activity_name: str
    planned_start: date | None
    planned_finish: date | None
    total_float_days: float
    critical_path: bool


class ControlAccountMappingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    schedule_import_id: int
    schedule_activity_map_id: int
    activity_id: int | None
    control_account_id: int | None
    wbs_code: str
    wbs_name: str
    cbs_code: str
    mapping_rule: str
    planned_cost: float
    planned_value: float
    planned_percent: float
    status: str
    review_note: str


class ControlAccountMappingSummary(BaseModel):
    total_schedule_activities: int
    mapped_activities: int
    unmapped_activities: int
    control_account_count: int
    cost_loaded_activities: int
    total_bac: float
    total_planned_value: float
    mapping_score: float
    cost_loading_score: float
    baseline_status: str


class ScheduleValidationFindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    schedule_import_id: int
    check_code: str
    severity: str
    message: str
    item_count: int
    weight: float


class BaselineVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    schedule_import_id: int
    version_no: int
    name: str
    status: str
    data_date: date | None
    quality_score: float
    created_at: datetime


class ControlPeriodOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    period_label: str
    data_date: date | None
    status: str
    created_at: datetime


class BusinessProcessInstanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    process_code: str
    process_name: str
    record_no: str
    title: str
    status: str
    current_step: str
    ball_in_court: str
    trigger_entity_type: str
    trigger_entity_id: int
    created_at: datetime
    updated_at: datetime
    version: int


class WorkflowStepInstanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    process_instance_id: int
    step_order: int
    name: str
    detail: str
    owner_role: str
    status: str
    tone: str


class WorkflowActionIn(BaseModel):
    action: str
    actor: str = "Project Controls"
    expected_version: int | None = None


class ProcessStepTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    step_order: int
    name: str
    detail: str
    owner_role: str
    status: str
    tone: str


class ProcessTransitionTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | None = None
    action: str
    label: str
    from_step: str
    to_step: str
    process_status: str
    ball_in_court: str
    from_status: str
    from_tone: str
    to_status: str
    to_tone: str
    requires_approval: bool
    permission_key: str


class ProcessStepTemplateCreate(BaseModel):
    name: str
    detail: str = ""
    owner_role: str = ""
    status: str = "Queued"
    tone: str = "queued"


class ProcessTransitionTemplateCreate(BaseModel):
    action: str
    label: str = ""
    from_step: str = ""
    to_step: str = ""
    process_status: str = "in_review"
    ball_in_court: str = ""
    from_status: str = "Complete"
    from_tone: str = "complete"
    to_status: str = "Active"
    to_tone: str = "active"
    requires_approval: bool = False
    permission_key: str = ""


class ProcessTemplateCreate(BaseModel):
    code: str
    name: str
    category: str = "Custom"
    description: str = ""
    form_schema: list[str] = Field(default_factory=list)
    status: str = "Draft"
    version_no: int = 1
    steps: list[ProcessStepTemplateCreate] = Field(default_factory=list)
    transitions: list[ProcessTransitionTemplateCreate] = Field(default_factory=list)


class ProcessTemplateOut(BaseModel):
    id: int | None = None
    code: str
    name: str
    category: str
    description: str = ""
    version_no: int = 1
    form_schema: list[str]
    workflow_steps: list[str]
    roles: list[str]
    status: str
    step_templates: list[ProcessStepTemplateOut] = Field(default_factory=list)
    transitions: list[ProcessTransitionTemplateOut] = Field(default_factory=list)


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    actor: str
    action: str
    entity_type: str
    entity_id: int | None
    payload: str
    created_at: datetime


class ChangeRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    control_account_id: int | None
    title: str
    deviation: str
    cost_impact: float
    schedule_impact_days: int
    status: str


class ChangeRequestCreate(BaseModel):
    control_account_id: int | None = None
    title: str
    deviation: str
    cost_impact: float = 0
    schedule_impact_days: int = 0


class ClaimOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    control_account_id: int | None
    title: str
    causality: str
    impact: str
    evidence_summary: str
    status: str


class ClaimEntitlementItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    claim_id: int
    practice_source: str
    category: str
    element: str
    requirement: str
    assessment: str
    evidence_ref: str
    status: str
    weight: float
    score: float
    sequence_no: int
    version: int
    updated_at: datetime


class ClaimEntitlementItemCreate(BaseModel):
    practice_source: str = "RP120R-21"
    category: str
    element: str
    requirement: str
    assessment: str = ""
    evidence_ref: str = ""
    status: str = "gap"
    weight: float = 1
    score: float = 0
    sequence_no: int = 0


class ClaimEntitlementItemUpdate(BaseModel):
    assessment: str | None = None
    evidence_ref: str | None = None
    status: str | None = None
    score: float | None = None
    expected_version: int | None = None


class ClaimEntitlementSummary(BaseModel):
    total_items: int
    satisfied_items: int
    partial_items: int
    gap_items: int
    cumulative_items: int
    cumulative_gap_items: int
    entitlement_score: float


class ContractNoticeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    contract_id: int | None
    claim_id: int | None
    change_request_id: int | None
    notice_type: str
    subject: str
    reference: str
    event_date: date | None
    notice_date: date | None
    due_date: date | None
    status: str
    days_late: int
    compliance_status: str
    created_at: datetime


class ContractNoticeCreate(BaseModel):
    contract_id: int | None = None
    claim_id: int | None = None
    change_request_id: int | None = None
    notice_type: str = "notice"
    subject: str
    reference: str = ""
    event_date: date | None = None
    notice_date: date | None = None
    due_date: date | None = None
    status: str = "issued"


class ClaimImpactAnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    claim_id: int
    method: str
    impacted_activity: str
    cause: str
    effect: str
    schedule_impact_days: int
    cost_impact: float
    productivity_loss_percent: float
    evidence_ref: str
    confidence_score: float
    status: str
    created_at: datetime
    version: int
    updated_at: datetime


class ClaimImpactAnalysisCreate(BaseModel):
    method: str
    impacted_activity: str = ""
    cause: str = ""
    effect: str = ""
    schedule_impact_days: int = 0
    cost_impact: float = 0
    productivity_loss_percent: float = 0
    evidence_ref: str = ""
    confidence_score: float = 0
    status: str = "draft"


class ClaimImpactAnalysisUpdate(BaseModel):
    method: str | None = None
    impacted_activity: str | None = None
    cause: str | None = None
    effect: str | None = None
    schedule_impact_days: int | None = None
    cost_impact: float | None = None
    productivity_loss_percent: float | None = None
    evidence_ref: str | None = None
    confidence_score: float | None = None
    status: str | None = None
    expected_version: int | None = None


class ClaimsForensicSummary(BaseModel):
    total_claims: int
    notice_count: int
    compliant_notices: int
    late_notices: int
    impact_analyses: int
    quantified_claims: int
    total_claimed_cost: float
    total_schedule_impact_days: int
    forensic_readiness_score: float


class ContractOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    title: str
    counterparty: str
    contract_type: str
    value: float
    status: str


class ContractCreate(BaseModel):
    code: str
    title: str
    counterparty: str
    contract_type: str = "EPC"
    value: float = 0
    status: str = "active"


class ContractCommunicationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    contract_id: int | None
    communication_type: str
    subject: str
    reference: str
    sent_on: date
    status: str


class ContractCommunicationCreate(BaseModel):
    contract_id: int | None = None
    communication_type: str = "letter"
    subject: str
    reference: str = ""
    sent_on: date
    status: str = "issued"


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    linked_entity_type: str
    linked_entity_id: int
    title: str
    doc_type: str
    uri: str


class DocumentCreate(BaseModel):
    linked_entity_type: str
    linked_entity_id: int
    title: str
    doc_type: str
    uri: str


class WorkPackageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    control_account_id: int | None
    parent_id: int | None
    package_type: str
    code: str
    title: str
    discipline: str
    sequence_no: int
    path_of_construction: str
    owner_role: str
    readiness_status: str
    planned_start: date | None
    planned_finish: date | None
    progress_percent: float
    version: int
    updated_at: datetime


class WorkPackageCreate(BaseModel):
    control_account_id: int | None = None
    parent_id: int | None = None
    package_type: str
    code: str
    title: str
    discipline: str = ""
    sequence_no: int = 0
    path_of_construction: str = ""
    owner_role: str = "Workface Planner"
    readiness_status: str = "constraint_review"
    planned_start: date | None = None
    planned_finish: date | None = None
    progress_percent: float = 0


class WorkPackageReadinessUpdate(BaseModel):
    readiness_status: str | None = None
    progress_percent: float | None = None
    expected_version: int | None = None


class WorkPackageConstraintOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    work_package_id: int
    constraint_type: str
    description: str
    owner_role: str
    required_by: date | None
    status: str
    blocking: bool
    version: int
    updated_at: datetime


class WorkPackageConstraintCreate(BaseModel):
    constraint_type: str
    description: str
    owner_role: str = "Workface Planner"
    required_by: date | None = None
    status: str = "open"
    blocking: bool = True


class WorkPackageConstraintUpdate(BaseModel):
    status: str | None = None
    blocking: bool | None = None
    expected_version: int | None = None


class AWPReadinessSummary(BaseModel):
    total_packages: int
    cwp_count: int
    iwp_count: int
    ready_for_release: int
    blocked_packages: int
    open_constraints: int
    blocking_constraints: int
    readiness_score: float


class PilotReadinessItem(BaseModel):
    phase: str
    area: str
    status: str
    score: float
    finding: str
    next_action: str


class PilotReadinessOut(BaseModel):
    project_id: int
    project_code: str
    status: str
    score: float
    blockers: list[str]
    items: list[PilotReadinessItem]


class TCMFlowStep(BaseModel):
    name: str
    purpose: str
    state: str


class ControlCoreLoop(BaseModel):
    step: str
    description: str


class DashboardOut(BaseModel):
    project: ProjectOut
    control_plan: ProjectControlPlanOut | None
    current_user: UserOut
    current_membership: ProjectMembershipOut
    project_team: list[ProjectTeamMemberOut]
    schedule_import: ScheduleImportOut | None
    schedule_activity_count: int
    schedule_relationship_count: int
    schedule_findings: list[ScheduleValidationFindingOut]
    baseline_versions: list[BaselineVersionOut]
    control_periods: list[ControlPeriodOut]
    workflow_instance: BusinessProcessInstanceOut | None
    workflow_steps: list[WorkflowStepInstanceOut]
    business_processes: list[BusinessProcessInstanceOut]
    process_templates: list[ProcessTemplateOut]
    audit_logs: list[AuditLogOut]
    data_quality_gates: list[DataQualityGateOut]
    flow: list[TCMFlowStep]
    loop: list[ControlCoreLoop]
    control_accounts: list[ControlAccountOut]
    control_account_mappings: list[ControlAccountMappingOut]
    control_account_mapping_summary: ControlAccountMappingSummary
    latest_progress_records: list[ProgressRecordOut]
    latest_cost_records: list[CostRecordOut]
    cost_sheet: list[CostSheetLineOut]
    funding_sources: list[FundingSourceOut]
    cash_flow: list[CashFlowPeriodOut]
    cost_manager_summary: CostManagerSummaryOut
    project_kpi: KPIOut
    account_kpis: list[KPIOut]
    control_snapshots: list[ControlSnapshotOut]
    forecast_scenarios: list[ForecastScenarioOut]
    productivity_summary: ProductivitySummary
    alerts: list[AlertOut]
    changes: list[ChangeRequestOut]
    claims: list[ClaimOut]
    claim_entitlement_items: list[ClaimEntitlementItemOut]
    claim_entitlement_summary: ClaimEntitlementSummary
    contract_notices: list[ContractNoticeOut]
    claim_impact_analyses: list[ClaimImpactAnalysisOut]
    claims_forensic_summary: ClaimsForensicSummary
    contracts: list[ContractOut]
    communications: list[ContractCommunicationOut]
    documents: list[DocumentOut]
    work_packages: list[WorkPackageOut]
    work_package_constraints: list[WorkPackageConstraintOut]
    awp_summary: AWPReadinessSummary
    ai_brief: str
