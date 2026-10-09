from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    phase: str
    currency: str
    calendar_base: str = ""
    owner: str = ""
    status: str = "draft"
    authorization_date: date | None = None
    authorization_ref: str = ""
    configuration: dict[str, object] = Field(default_factory=dict)
    start_date: date | None
    finish_date: date | None


class TenantContextOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    slug: str
    base_currency: str = "COP"


class GuidedProjectContextOut(BaseModel):
    id: int
    code: str
    name: str
    status: str
    currency: str


class CostCurrencyGateOut(BaseModel):
    project_id: int
    schedule_import_id: int | None = None
    detected_currency: str = ""
    currency_confidence: str = "unknown"
    currency_source: str = ""
    currency_confirmed: bool = False
    total_imported_cost: float = 0
    cost_loaded_activity_count: int = 0
    cost_loaded_activity_percent: float = 0
    missing_cost_activity_count: int = 0
    cost_source_summary: dict[str, object] = Field(default_factory=dict)
    state: str = "blocked"
    message: str = "Load XER/XML schedule to evaluate cost and currency."


class GuidedFlowStepOut(BaseModel):
    key: str
    label: str
    state: str
    summary: str
    next_action: str
    owner_role: str
    target_view: str
    blocking_count: int = 0


class GuidedNextActionOut(BaseModel):
    key: str
    label: str
    target_view: str
    disabled: bool = False
    reason: str = ""


class GuidedFlowOut(BaseModel):
    tenant: TenantContextOut
    project: GuidedProjectContextOut
    steps: list[GuidedFlowStepOut]
    next_action: GuidedNextActionOut
    cost_currency_gate: CostCurrencyGateOut


class ProcessFlowItemOut(BaseModel):
    key: str
    label: str
    status: str
    owner_role: str
    evidence: str
    next_action: str
    acceptance_criteria: list[str] = Field(default_factory=list)
    target_view: str = ""


class ProcessFlowLaneOut(BaseModel):
    key: str
    label: str
    owner_role: str
    items: list[ProcessFlowItemOut]


class ProcessFlowBoardOut(BaseModel):
    project_id: int
    overall_status: str
    completion_percent: float
    lanes: list[ProcessFlowLaneOut]


class ScheduleCurrencyConfirmIn(BaseModel):
    currency: str


class ProjectCreate(BaseModel):
    code: str
    name: str
    phase: str = "Planning"
    currency: str = "USD"
    calendar_base: str = ""
    owner: str = ""
    status: str = "draft"
    authorization_date: date | None = None
    authorization_ref: str = ""
    configuration: dict[str, object] = Field(default_factory=dict)
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


class ProjectOperationalSetupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    project_number: str
    setup_template: str
    attribute_form: str
    permissions_configured: bool
    modules_configured: bool
    cost_sheet_ready: bool
    funding_sheet_ready: bool
    p6_mapping_ready: bool
    status: str
    readiness_status: str
    readiness_notes: str
    version: int
    created_at: datetime
    updated_at: datetime


class ProjectOperationalSetupUpdate(BaseModel):
    project_number: str = ""
    setup_template: str = ""
    attribute_form: str = ""
    permissions_configured: bool = False
    modules_configured: bool = False
    cost_sheet_ready: bool = False
    funding_sheet_ready: bool = False
    p6_mapping_ready: bool = False
    status: str = "draft"
    expected_version: int | None = None


class ActivitySheetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    schedule_import_id: int | None
    source_file_name: str
    source: str
    status: str
    row_count: int
    data_date: date | None
    baseline_name: str
    validation_summary: str
    version: int
    created_at: datetime
    updated_at: datetime


class ActivitySheetRowOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    activity_sheet_id: int
    external_activity_id: str
    wbs_code: str
    activity_name: str
    planned_start: date | None
    planned_finish: date | None
    total_float_days: float
    critical_path: bool
    planned_cost: float
    planned_value: float = 0
    planned_percent: float = 0
    cbs_code: str = ""
    control_account_id: int | None = None
    control_account_code: str = ""
    mapping_status: str = ""
    review_note: str = ""


class ActivitySheetWbsRowOut(BaseModel):
    wbs_code: str
    wbs_name: str
    activity_count: int
    control_account_count: int
    planned_cost: float
    planned_value: float
    unmapped_activity_count: int
    needs_review_count: int


class QuantityTakeoffRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    bim_model_id: int | None = None
    source_file_name: str
    source_type: str
    source_sha256: str = ""
    bim_revision_id: str = ""
    model_linked_at: datetime | None = None
    status: str
    row_count: int
    mapped_line_count: int
    unmapped_line_count: int
    total_quantity: float
    validation_summary: str
    version: int
    created_at: datetime
    updated_at: datetime


class QuantityTakeoffModelLinkIn(BaseModel):
    model_id: int
    expected_version: int | None = None


class QuantityTakeoffLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    run_id: int
    source_row_id: str
    element_id: str
    element_guid: str
    ifc_class: str
    category: str
    family: str
    type_name: str
    instance_name: str
    project_name: str
    site_name: str
    building_name: str
    storey: str
    system_name: str
    zone_name: str
    assembly_name: str
    classification_system: str
    classification_code: str
    quantity: float
    unit: str
    measurement_rule: str
    wbs_code: str
    cbs_code: str
    fbs_code: str
    package_code: str
    wbs_id: int | None = None
    cbs_id: int | None = None
    fbs_id: int | None = None
    work_package_id: int | None = None
    mapping_status: str
    validation_notes: str
    raw_data: dict
    created_at: datetime
    updated_at: datetime


class ControlledMeasurementApprovalIn(BaseModel):
    line_ids: list[int] = Field(min_length=1)
    measurement_rule: str
    quantity: float | None = None
    source: str = "Quantity table review"
    note: str = ""
    unit: str | None = None


class BimGeometryMeasurementBatchIn(BaseModel):
    model_id: int
    line_ids: list[int] = Field(default_factory=list)
    apply: bool = False
    replace_valid: bool = False


class BimGeometryMeasurementResultOut(BaseModel):
    line_id: int
    element_guid: str = ""
    ifc_class: str = ""
    element_name: str = ""
    status: str
    current_quantity: float
    current_unit: str
    source_quantity: float
    source_unit: str
    approved_quantity: float | None = None
    approved_unit: str = ""
    geometry_quantity: float
    geometry_unit: str
    measurement_rule: str
    difference: float | None = None
    difference_percent: float | None = None
    confidence: str
    reason: str


class BimGeometryMeasurementBatchOut(BaseModel):
    model_id: int
    run_id: int
    revision_id: str = ""
    total_count: int
    matched_count: int
    ready_count: int
    compare_count: int
    applied_count: int
    unmatched_count: int
    invalid_count: int
    results: list[BimGeometryMeasurementResultOut] = Field(default_factory=list)


class QuantityControlCodeAssignmentIn(BaseModel):
    line_ids: list[int] = Field(min_length=1)
    wbs_code: str
    cbs_code: str
    fbs_code: str
    package_code: str
    cost_item_code: str = ""
    cost_item_name: str = ""
    budget_unit: str = ""
    unit_rate: float | None = None
    catalog_item_id: int | None = None
    currency: str = ""
    source_key: str = ""
    source_url: str = ""
    license_note: str = ""
    apu_structure: list[dict[str, Any]] = Field(default_factory=list)
    structure_note: str = ""
    structure_status: str = ""
    note: str = ""


class ColombiaApuCatalogItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    source_key: str
    external_id: str
    item_code: str
    item_name: str
    unit: str
    unit_rate: float
    currency: str
    group_name: str
    chapter: str
    region: str
    source_url: str
    license_note: str
    update_frequency: str
    status: str
    raw_data: dict
    created_at: datetime
    updated_at: datetime


class ColombiaApuCatalogSyncOut(BaseModel):
    project_id: int
    source_key: str
    source_url: str
    created_count: int
    updated_count: int
    skipped_count: int
    total_count: int
    license_note: str
    update_frequency: str
    synced_at: datetime


class QuantityApuSuggestionIn(BaseModel):
    line_ids: list[int] = Field(min_length=1)
    apply_best: bool = False
    limit_per_line: int = Field(default=3, ge=1, le=10)


class QuantityApuApprovalIn(BaseModel):
    line_ids: list[int] = Field(min_length=1)


class QuantityApuSuggestionOut(BaseModel):
    line_id: int
    catalog_item_id: int
    source_key: str
    cost_item_code: str
    cost_item_name: str
    budget_unit: str
    unit_rate: float
    currency: str
    quantity: float
    budget_amount: float
    match_score: float
    review_note: str
    source_url: str
    license_note: str
    apu_structure: list[dict[str, Any]] = Field(default_factory=list)
    structure_note: str = ""
    structure_status: str = "review_required"


class QuantityRuleRecalculationImpactOut(BaseModel):
    line_id: int
    element_guid: str = ""
    ifc_class: str = ""
    previous_status: str = ""
    new_status: str = ""
    previous_measure: str = ""
    new_measure: str = ""
    previous_units: list[str] = Field(default_factory=list)
    new_units: list[str] = Field(default_factory=list)
    mapping_status: str = ""


class QuantityRuleRecalculationOut(BaseModel):
    project_id: int
    run_id: int
    total_lines: int
    changed_line_count: int
    valid_count: int
    review_count: int
    blocked_count: int
    cost_rollup_gate: str
    affected_classes: list[str] = Field(default_factory=list)
    impacts: list[QuantityRuleRecalculationImpactOut] = Field(default_factory=list)


class BimQuantityRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    ifc_class: str
    element_label: str
    expected_measure: str
    rule_hint: str
    expected_units: list[str] = Field(default_factory=list)
    allow_fallback_count: bool
    source: str
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class BimQuantityRuleUpdate(BaseModel):
    element_label: str | None = None
    expected_measure: str | None = None
    rule_hint: str | None = None
    expected_units: list[str] | None = None
    allow_fallback_count: bool | None = None
    status: str | None = None
    expected_version: int | None = None


class BimModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    source_file_name: str
    source_type: str
    source_sha256: str = ""
    revision_id: str = ""
    source_size_bytes: int
    status: str
    ifc_schema: str = Field(alias="schema", serialization_alias="schema")
    units: str
    element_count: int
    storey_count: int
    model_identity: dict
    created_at: datetime
    updated_at: datetime


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


class UserUpdate(BaseModel):
    email: str | None = None
    full_name: str | None = None
    title: str | None = None


class UserPasswordReset(BaseModel):
    password: str


class OrganizationSecurityOrganizationOut(BaseModel):
    id: int
    code: str
    legal_name: str
    display_name: str
    base_currency: str
    country_code: str = "CO"
    timezone: str = "America/Bogota"
    default_locale: str = "es-CO"
    status: str = "active"


class OrganizationSecurityOrganizationUpdate(BaseModel):
    display_name: str | None = None
    base_currency: str | None = None


class OrganizationUnitCreate(BaseModel):
    code: str
    name: str
    unit_type: str = "department"
    parent_id: int | None = None
    manager_user_id: int | None = None
    sort_order: int = 0


class OrganizationUnitUpdate(BaseModel):
    name: str | None = None
    unit_type: str | None = None
    parent_id: int | None = None
    manager_user_id: int | None = None
    status: str | None = None
    sort_order: int | None = None
    expected_version: int | None = None


class OrganizationUnitOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    parent_id: int | None
    code: str
    name: str
    unit_type: str
    manager_user_id: int | None
    status: str
    sort_order: int
    version: int


class SecurityGroupCreate(BaseModel):
    code: str
    name: str
    description: str = ""
    owner_user_id: int | None = None


class SecurityGroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    description: str
    owner_user_id: int | None
    status: str
    version: int
    member_ids: list[int] = Field(default_factory=list)


class PermissionCatalogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    key: str
    resource: str
    action: str
    description: str
    risk_level: str
    status: str


class SecurityRoleCreate(BaseModel):
    code: str
    name: str
    description: str = ""
    permission_keys: list[str] = Field(default_factory=list)


class SecurityRoleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    description: str
    is_system: bool
    status: str
    version: int
    permission_keys: list[str] = Field(default_factory=list)


class SecurityAccessAssignmentCreate(BaseModel):
    subject_type: str
    subject_id: int
    role_id: int
    scope_type: str = "organization"
    scope_unit_id: int | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class SecurityAccessAssignmentOut(BaseModel):
    id: int
    subject_type: str
    subject_id: int
    subject_name: str
    role_id: int
    role_code: str
    role_name: str
    scope_type: str
    scope_unit_id: int | None
    scope_name: str
    starts_at: datetime | None
    ends_at: datetime | None
    status: str


class EffectiveAccessOut(BaseModel):
    user_id: int
    user_name: str
    permission_keys: list[str]
    assignments: list[SecurityAccessAssignmentOut]


class SecurityEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int | None
    event_type: str
    outcome: str
    target_type: str
    target_id: int | None
    metadata_json: dict
    occurred_at: datetime


class AuthenticationPostureOut(BaseModel):
    local_authentication: bool
    oidc_available: bool
    access_token_minutes: int
    refresh_sessions: bool
    password_hash_policy: str
    active_user_count: int


class OrganizationSecurityOverviewOut(BaseModel):
    organization: OrganizationSecurityOrganizationOut
    units: list[OrganizationUnitOut]
    users: list[UserOut]
    groups: list[SecurityGroupOut]
    permissions: list[PermissionCatalogOut]
    roles: list[SecurityRoleOut]
    assignments: list[SecurityAccessAssignmentOut]
    security_events: list[SecurityEventOut]
    authentication: AuthenticationPostureOut


class AdminConfigurationCreate(BaseModel):
    kind: str
    code: str
    name: str
    description: str = ""
    content_json: dict[str, Any] = Field(default_factory=dict)


class AdminConfigurationUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    content_json: dict[str, Any] | None = None
    expected_version: int | None = None


class AdminConfigurationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    kind: str
    code: str
    name: str
    description: str
    status: str
    revision: int
    version: int
    content_json: dict[str, Any]
    content_hash: str
    published_at: datetime | None
    created_by_user_id: int
    created_at: datetime
    updated_at: datetime


class EnterpriseWorkspaceCreate(BaseModel):
    code: str
    name: str
    workspace_type_code: str
    parent_id: int | None = None
    sort_order: int = 0


class EnterpriseWorkspaceUpdate(BaseModel):
    name: str | None = None
    parent_id: int | None = None
    status: str | None = None
    sort_order: int | None = None
    expected_version: int | None = None


class WorkspaceDefaultsUpdate(BaseModel):
    values: dict[str, Any] = Field(default_factory=dict)
    expected_version: int | None = None


class EnterpriseWorkspaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    parent_id: int | None
    workspace_type_code: str
    code: str
    name: str
    status: str
    defaults_json: dict[str, Any]
    sort_order: int
    version: int


class WorkspaceModuleSettingUpdate(BaseModel):
    enabled: bool
    expected_version: int | None = None


class WorkspaceModuleSettingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workspace_id: int
    module_key: str
    enabled: bool
    version: int


class WorkspaceEffectiveConfigurationOut(BaseModel):
    workspace_id: int
    inheritance_path: list[int]
    defaults: dict[str, Any]
    modules: dict[str, bool]


class AdminConfigurationOverviewOut(BaseModel):
    configurations: list[AdminConfigurationOut]
    workspaces: list[EnterpriseWorkspaceOut]
    module_settings: list[WorkspaceModuleSettingOut]
    summary: dict[str, int]


class NumberingRequest(BaseModel):
    scope_key: str = "tenant"
    context: dict[str, str] = Field(default_factory=dict)


class NumberingResultOut(BaseModel):
    rule_code: str
    scope_key: str
    value: str
    sequence: int
    committed: bool


class LoginRequest(BaseModel):
    email: str
    password: str
    tenant_id: int | None = None
    tenant_slug: str | None = None


class AuthSessionOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    tenant_id: int
    user: UserOut


class IntegrationTokenCreate(BaseModel):
    name: str
    datasets: list[str] = Field(default_factory=lambda: ["cost_sheet", "funding_sources", "cash_flow"])
    formats: list[str] = Field(default_factory=lambda: ["json", "csv", "both", "xlsx"])
    expires_in_days: int = 30


class IntegrationTokenOut(BaseModel):
    id: int
    project_id: int
    name: str
    token_prefix: str
    datasets: list[str]
    formats: list[str]
    status: str
    created_by_user_id: int
    created_at: datetime
    expires_at: datetime
    last_used_at: datetime | None


class IntegrationTokenCreated(IntegrationTokenOut):
    token: str


class IntegrationTokenAlertOut(BaseModel):
    id: int
    project_id: int
    name: str
    token_prefix: str
    status: str
    datasets: list[str]
    formats: list[str]
    expires_at: datetime
    days_to_expiry: int
    severity: str
    message: str
    last_used_at: datetime | None


class IntegrationTokenAlertSummary(BaseModel):
    project_id: int
    warning_days: int
    generated_at: datetime
    active_count: int
    expiring_count: int
    expired_count: int
    revoked_count: int
    alerts: list[IntegrationTokenAlertOut]


class IntegrationExportLogOut(BaseModel):
    id: int
    project_id: int
    requested_by_user_id: int
    integration_token_id: int | None
    actor: str
    artifact_type: str
    datasets: list[str]
    format: str
    file_name: str
    sha256: str
    size_bytes: int
    row_count: int
    status: str
    created_at: datetime


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


class RoleMatrixPolicyOut(BaseModel):
    process_code: str
    action: str
    required_role: str
    permission_key: str
    status: str


class RoleMatrixEntryOut(BaseModel):
    role: str
    description: str
    permissions: dict[str, bool]
    assigned_users: list[UserOut]
    assigned_user_count: int
    business_process_actions: list[RoleMatrixPolicyOut]


class ProjectRoleMatrixOut(BaseModel):
    project_id: int
    generated_at: datetime
    role_count: int
    entries: list[RoleMatrixEntryOut]


class ControlAccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    wbs_id: int | None = None
    awp_package_id: int | None = None
    code: str
    name: str
    responsible: str
    discipline: str
    scope: str = ""
    budget: float = 0
    start_date: date | None = None
    finish_date: date | None = None
    cbs_code: str
    contract_ref: str
    measurement_rule: str
    earned_value: float = 0
    actual_cost: float = 0
    forecast: float = 0
    lifecycle_status: str
    risk_ref: str
    closure_note: str
    version: int
    updated_at: datetime


class ControlAccountCreate(BaseModel):
    wbs_id: int | None = None
    awp_package_id: int | None = None
    code: str
    name: str
    responsible: str
    discipline: str
    scope: str = ""
    budget: float = 0
    start_date: date | None = None
    finish_date: date | None = None
    cbs_code: str = ""
    contract_ref: str = ""
    measurement_rule: str = ""
    earned_value: float = 0
    actual_cost: float = 0
    forecast: float = 0
    lifecycle_status: str = "active"
    risk_ref: str = ""
    closure_note: str = ""


class ControlAccountUpdate(BaseModel):
    wbs_id: int | None = None
    awp_package_id: int | None = None
    code: str | None = None
    name: str | None = None
    responsible: str | None = None
    discipline: str | None = None
    scope: str | None = None
    budget: float | None = None
    start_date: date | None = None
    finish_date: date | None = None
    cbs_code: str | None = None
    contract_ref: str | None = None
    measurement_rule: str | None = None
    earned_value: float | None = None
    actual_cost: float | None = None
    forecast: float | None = None
    lifecycle_status: str | None = None
    risk_ref: str | None = None
    closure_note: str | None = None
    expected_version: int | None = None


class WBSOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    parent_id: int | None
    code: str
    name: str
    level: int = 1
    description: str = ""
    dictionary: str = ""
    responsible: str = ""
    status: str = "draft"


class WBSCreate(BaseModel):
    parent_id: int | None = None
    code: str
    name: str
    level: int = 1
    description: str = ""
    dictionary: str = ""
    responsible: str = ""
    status: str = "draft"


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
    approved_amount: float = 0
    source_of_funds: str = ""
    funding_type: str = ""
    authorization_ref: str = ""
    usage_restrictions: str = ""
    funds_available: float = 0
    funds_committed: float = 0
    funds_executed: float = 0
    balance: float = 0
    currency: str
    status: str
    usage_rules: str = ""
    version: int
    created_at: datetime
    updated_at: datetime


class FundingSourceCreate(BaseModel):
    code: str
    name: str = ""
    source_of_funds: str = ""
    funding_type: str = ""
    authorization_ref: str = ""
    usage_restrictions: str = ""
    usage_rules: str = ""
    amount: float | None = None
    approved_amount: float | None = None
    currency: str = "USD"
    status: str = "approved"


class FundingSourceUpdate(BaseModel):
    name: str | None = None
    source_of_funds: str | None = None
    funding_type: str | None = None
    authorization_ref: str | None = None
    usage_restrictions: str | None = None
    usage_rules: str | None = None
    amount: float | None = None
    approved_amount: float | None = None
    currency: str | None = None
    status: str | None = None
    expected_version: int | None = None


class FundingAvailabilityOut(BaseModel):
    project_id: int
    funding_source_id: int
    fbs_code: str
    approved_amount: float
    funds_available: float
    funds_committed: float
    funds_executed: float
    requested_amount: float
    is_available: bool
    status: str


class CostBreakdownStructureOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    parent_id: int | None
    code: str
    level: int
    cost_category: str
    description: str
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class CostBreakdownStructureCreate(BaseModel):
    parent_id: int | None = None
    code: str
    level: int = 1
    cost_category: str
    description: str = ""
    status: str = "draft"


class CostCodeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    wbs_id: int
    control_account_id: int
    cbs_id: int
    fbs_id: int
    contract_ref: str
    code: str
    budget: float
    funds_available: float
    commitments: float
    actual_costs: float
    forecast: float
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class CostCodeCreate(BaseModel):
    code: str
    wbs_id: int
    control_account_id: int
    cbs_id: int
    fbs_id: int
    contract_ref: str = ""
    budget: float = 0
    funds_available: float = 0
    commitments: float = 0
    actual_costs: float = 0
    forecast: float = 0
    status: str = "draft"


class BusinessProcessLineItemCreate(BaseModel):
    wbs_id: int | None = None
    cbs_id: int
    funding_source_id: int | None = None
    control_account_id: int | None = None
    amount: float
    quantity: float = 0
    description: str = ""


class BusinessProcessLineItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    process_instance_id: int
    line_type: str
    wbs_id: int | None
    cbs_id: int
    funding_source_id: int | None
    control_account_id: int | None
    cost_code_id: int | None
    amount: float
    quantity: float
    description: str
    status: str
    version: int = 1
    created_at: datetime
    updated_at: datetime


class BusinessProcessCreate(BaseModel):
    title: str
    line_items: list[BusinessProcessLineItemCreate]


class BusinessProcessPolicyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    process_code: str
    action: str
    required_role: str
    permission_key: str
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class BusinessProcessPolicyCreate(BaseModel):
    process_code: str
    action: str
    required_role: str = ""
    permission_key: str = ""
    status: str = "active"


class BusinessProcessLineItemUpdate(BaseModel):
    amount: float | None = None
    quantity: float | None = None
    description: str | None = None
    status: str | None = None
    change_note: str = ""
    expected_version: int | None = None


class BusinessProcessLineItemRevisionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    line_item_id: int
    process_instance_id: int
    previous_version: int
    new_version: int
    previous_amount: float
    new_amount: float
    previous_quantity: float
    new_quantity: float
    previous_description: str
    new_description: str
    previous_status: str
    new_status: str
    change_note: str
    changed_by: str
    created_at: datetime


class ControlAccountFundingAllocationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    control_account_id: int
    funding_source_id: int
    allocated_amount: float
    committed_amount: float
    actual_amount: float
    forecast_amount: float
    distribution_note: str
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class ControlAccountFundingAllocationCreate(BaseModel):
    control_account_id: int
    funding_source_id: int
    allocated_amount: float = 0
    committed_amount: float = 0
    actual_amount: float = 0
    forecast_amount: float = 0
    distribution_note: str = ""
    status: str = "active"


class IntegratedControlMatrixRow(BaseModel):
    project_id: int
    project_code: str
    project_name: str
    fbs_code: str
    wbs_code: str
    awp_package_code: str
    awp_package_type: str
    control_account_code: str
    cbs_code: str
    cost_code: str
    contract_ref: str
    budget: float
    funds_available: float
    committed: float
    actual: float
    forecast: float
    balance: float
    status: str


class ForecastFundingRow(BaseModel):
    funding_source_id: int
    fbs_code: str
    approved_amount: float
    funds_available: float
    funds_committed: float
    funds_executed: float
    forecast: float
    forecast_vs_available: float
    forecast_vs_approved: float
    status: str


class ForecastFundingReport(BaseModel):
    project_id: int
    rows: list[ForecastFundingRow]


class BaselineApprovalOut(BaseModel):
    project_id: int
    project_status: str
    fbs_count: int
    wbs_count: int
    control_account_count: int
    cbs_count: int
    cost_code_count: int


class CloseoutReportOut(BaseModel):
    project_id: int
    funding_source_id: int | None = None
    approved_amount: float
    committed: float
    actual: float
    forecast: float
    unused_balance: float
    open_commitments: int
    closed_commitments: int = 0
    funding_status: str = ""


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
    incurred_payment_certificate_value: float
    incurred_warehouse_receipt_value: float
    committed_contract_value: float
    committed_purchase_order_value: float
    committed_cost: float
    earned_value: float
    variance: float
    cpi: float


class CostManagerSummaryOut(BaseModel):
    total_bac: float
    total_planned_value: float
    total_earned_value: float
    total_actual_cost: float
    total_incurred_from_payment_certificates: float
    total_incurred_from_warehouse_receipts: float
    total_contract_commitments: float
    total_purchase_order_commitments: float
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
    detected_currency: str = ""
    currency_confidence: str = "unknown"
    currency_source: str = ""
    currency_confirmed: bool = False
    total_imported_cost: float = 0
    cost_loaded_activity_count: int = 0
    cost_loaded_activity_percent: float = 0
    cost_source_summary: dict[str, object] = Field(default_factory=dict)
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


class ActivityRelationshipOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    schedule_import_id: int
    predecessor_external_id: str
    successor_external_id: str
    relationship_type: str
    lag_days: float


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


class ScheduleQualityMetricOut(BaseModel):
    key: str
    standard: str
    label: str
    status: str
    item_count: int
    total_count: int
    percent: float
    threshold: str
    description: str


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


class ClaimCreate(BaseModel):
    control_account_id: int | None = None
    title: str
    causality: str = ""
    impact: str = ""
    evidence_summary: str = ""
    status: str = "analyzing"


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


class ForensicDossierAnalysisOut(BaseModel):
    mode: str
    summary: str
    source_files: list[str] = Field(default_factory=list)
    signals: list[str] = Field(default_factory=list)
    readiness_score: float
    created_claims: list[ClaimOut] = Field(default_factory=list)
    created_notices: list[ContractNoticeOut] = Field(default_factory=list)
    created_entitlement_items: list[ClaimEntitlementItemOut] = Field(default_factory=list)
    created_impact_analyses: list[ClaimImpactAnalysisOut] = Field(default_factory=list)


class ForensicRagSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str
    file_name: str
    source_type: str
    relevance: str
    tags: list[str] = Field(default_factory=list)


class ForensicWindowScheduleSourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    file_name: str
    source: str
    status: str
    data_date: date | None = None
    baseline_name: str = ""
    activity_count: int = 0
    relationship_count: int = 0
    quality_score: float = 0
    finding_code: str = ""
    message: str = ""


class ForensicWindowActivityDeltaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    activity_id: str
    activity_name: str
    wbs_code: str
    wbs_name: str
    start_slip_days: int
    finish_slip_days: int
    total_float_delta_days: float
    critical_in_start: bool
    critical_in_finish: bool
    classification: str
    alv_type: str = ""


class ForensicSourceValidationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    protocol: str
    check: str
    status: str
    detail: str


class ForensicWindowLogicDeltaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    added_relationships: int
    removed_relationships: int
    changed_relationships: int


class ForensicWindowResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    window_no: int
    start_schedule: str
    finish_schedule: str
    start_data_date: date | None = None
    finish_data_date: date | None = None
    start_completion: date | None = None
    finish_completion: date | None = None
    completion_slip_days: int
    critical_delay_days: int
    mitigation_days: int
    common_activity_count: int
    added_activity_count: int
    removed_activity_count: int
    delayed_activity_count: int
    critical_or_near_critical_delay_count: int
    logic_delta: ForensicWindowLogicDeltaOut
    top_delay_events: list[ForensicWindowActivityDeltaOut] = Field(default_factory=list)
    interpretation: str = ""


class ForensicWindowAnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    method_id: str
    method_name: str
    standard_reference: str
    methodology_note: str
    schedule_sources: list[ForensicWindowScheduleSourceOut] = Field(default_factory=list)
    windows: list[ForensicWindowResultOut] = Field(default_factory=list)
    rag_sources: list[ForensicRagSourceOut] = Field(default_factory=list)
    summary: dict[str, int | float | str] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    source_validation: list[ForensicSourceValidationOut] = Field(default_factory=list)


class ContractOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    funding_source_id: int | None = None
    control_account_id: int | None
    code: str
    title: str
    counterparty: str
    contract_type: str
    value: float
    status: str


class ContractCreate(BaseModel):
    funding_source_id: int | None = None
    control_account_id: int | None = None
    code: str
    title: str
    counterparty: str
    contract_type: str = "EPC"
    value: float = 0
    status: str = "active"


class ScheduleOfValueLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    contract_id: int
    line_no: str
    description: str
    amount: float
    cbs_id: int
    wbs_id: int | None
    control_account_id: int | None
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class ScheduleOfValueLineCreate(BaseModel):
    line_no: str
    description: str = ""
    amount: float
    cbs_id: int | None = None
    wbs_id: int | None = None
    control_account_id: int | None = None
    status: str = "active"


class CommitmentFundingLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    contract_id: int
    sov_line_id: int | None
    funding_source_id: int
    amount: float
    consumed_amount: float
    status: str
    version: int
    created_at: datetime
    updated_at: datetime


class CommitmentFundingLineCreate(BaseModel):
    contract_id: int
    sov_line_id: int | None = None
    funding_source_id: int
    amount: float
    consumed_amount: float = 0
    status: str = "active"


class RateSheetLineCreate(BaseModel):
    cbs_code: str
    unit_rate: float = 0
    multiplier: float = 1
    status: str = "active"


class RateSheetLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rate_sheet_id: int
    cbs_code: str
    unit_rate: float
    multiplier: float
    status: str
    created_at: datetime
    updated_at: datetime


class RateSheetCreate(BaseModel):
    code: str
    name: str = ""
    status: str = "draft"
    line_items: list[RateSheetLineCreate]


class RateSheetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    name: str
    status: str
    version: int
    created_at: datetime
    updated_at: datetime
    line_items: list[RateSheetLineOut] = []


class ActivitySheetRecostIn(BaseModel):
    rate_sheet_id: int


class ActivitySheetRecostOut(BaseModel):
    project_id: int
    activity_sheet_id: int
    rate_sheet_id: int
    recost_run_id: int | None = None
    updated_rows: int
    total_planned_cost: float
    total_planned_value: float


class ActivitySheetRecostRunLineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    recost_run_id: int
    activity_sheet_row_id: int
    external_activity_id: str
    cbs_code: str
    previous_planned_cost: float
    new_planned_cost: float
    previous_planned_value: float
    new_planned_value: float
    created_at: datetime


class ActivitySheetRecostRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    activity_sheet_id: int
    rate_sheet_id: int
    run_no: int
    updated_rows: int
    total_planned_cost: float
    total_planned_value: float
    created_by: str
    created_at: datetime
    lines: list[ActivitySheetRecostRunLineOut] = []


class ReconciliationReportRow(BaseModel):
    wbs_code: str
    cbs_code: str
    fbs_code: str
    control_account_code: str
    contract_ref: str
    budget: float
    committed: float
    funded_amount: float
    sov_amount: float
    forecast: float
    variance: float


class ReconciliationReportOut(BaseModel):
    project_id: int
    rows: list[ReconciliationReportRow]


class ControlAgentFindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int
    severity: str
    category: str
    title: str
    evidence: str
    recommendation: str
    owner_role: str
    entity_type: str
    entity_id: int | None
    status: str
    created_at: datetime


class ControlAgentRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    agent_code: str
    agent_name: str
    run_mode: str
    model_name: str
    status: str
    score: int
    summary: str
    created_by: str
    created_at: datetime
    findings: list[ControlAgentFindingOut] = []


class PurchaseOrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    funding_source_id: int | None = None
    control_account_id: int | None
    contract_id: int | None
    po_number: str
    description: str
    vendor: str
    committed_amount: float
    status: str
    issued_on: date | None
    version: int
    created_at: datetime
    updated_at: datetime


class PurchaseOrderCreate(BaseModel):
    funding_source_id: int | None = None
    control_account_id: int | None = None
    contract_id: int | None = None
    po_number: str
    description: str = ""
    vendor: str = ""
    committed_amount: float
    status: str = "issued"
    issued_on: date | None = None


class PurchaseOrderUpdate(BaseModel):
    funding_source_id: int | None = None
    control_account_id: int | None = None
    contract_id: int | None = None
    description: str | None = None
    vendor: str | None = None
    committed_amount: float | None = None
    status: str | None = None
    issued_on: date | None = None
    expected_version: int | None = None


class PaymentCertificateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    control_account_id: int | None
    contract_id: int | None
    purchase_order_id: int | None
    certificate_no: str
    period_label: str
    certified_amount: float
    retained_amount: float
    status: str
    certified_on: date | None
    version: int
    created_at: datetime
    updated_at: datetime


class PaymentCertificateCreate(BaseModel):
    control_account_id: int | None = None
    contract_id: int | None = None
    purchase_order_id: int | None = None
    certificate_no: str
    period_label: str = ""
    certified_amount: float
    retained_amount: float = 0
    status: str = "certified"
    certified_on: date | None = None


class PaymentCertificateUpdate(BaseModel):
    control_account_id: int | None = None
    contract_id: int | None = None
    purchase_order_id: int | None = None
    period_label: str | None = None
    certified_amount: float | None = None
    retained_amount: float | None = None
    status: str | None = None
    certified_on: date | None = None
    expected_version: int | None = None


class WarehouseReceiptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    control_account_id: int | None
    contract_id: int | None
    purchase_order_id: int | None
    receipt_no: str
    description: str
    received_quantity: float
    unit_cost: float
    received_value: float
    status: str
    received_on: date | None
    version: int
    created_at: datetime
    updated_at: datetime


class WarehouseReceiptCreate(BaseModel):
    control_account_id: int | None = None
    contract_id: int | None = None
    purchase_order_id: int | None = None
    receipt_no: str
    description: str = ""
    received_quantity: float = 0
    unit_cost: float = 0
    received_value: float = 0
    status: str = "accepted"
    received_on: date | None = None


class WarehouseReceiptUpdate(BaseModel):
    control_account_id: int | None = None
    contract_id: int | None = None
    purchase_order_id: int | None = None
    description: str | None = None
    received_quantity: float | None = None
    unit_cost: float | None = None
    received_value: float | None = None
    status: str | None = None
    received_on: date | None = None
    expected_version: int | None = None


class RFQPackageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    control_account_id: int | None
    package_no: str
    title: str
    scope_summary: str
    procurement_method: str
    status: str
    budget_amount: float
    issue_date: date | None
    due_date: date | None
    version: int
    created_at: datetime
    updated_at: datetime


class RFQPackageCreate(BaseModel):
    control_account_id: int | None = None
    package_no: str
    title: str
    scope_summary: str = ""
    procurement_method: str = "RFQ"
    status: str = "draft"
    budget_amount: float = 0
    issue_date: date | None = None
    due_date: date | None = None


class RFQPackageUpdate(BaseModel):
    control_account_id: int | None = None
    title: str | None = None
    scope_summary: str | None = None
    procurement_method: str | None = None
    status: str | None = None
    budget_amount: float | None = None
    issue_date: date | None = None
    due_date: date | None = None
    expected_version: int | None = None


class RFQBidOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rfq_package_id: int
    bidder_name: str
    bid_amount: float
    technical_score: float
    commercial_score: float
    schedule_score: float
    risk_score: float
    weighted_score: float
    status: str
    submitted_on: date | None
    notes: str
    version: int
    created_at: datetime
    updated_at: datetime


class RFQBidCreate(BaseModel):
    bidder_name: str
    bid_amount: float
    technical_score: float = 0
    commercial_score: float = 0
    schedule_score: float = 0
    risk_score: float = 0
    status: str = "received"
    submitted_on: date | None = None
    notes: str = ""


class RFQBidUpdate(BaseModel):
    bidder_name: str | None = None
    bid_amount: float | None = None
    technical_score: float | None = None
    commercial_score: float | None = None
    schedule_score: float | None = None
    risk_score: float | None = None
    status: str | None = None
    submitted_on: date | None = None
    notes: str | None = None
    expected_version: int | None = None


class RFQSummary(BaseModel):
    total_packages: int
    issued_packages: int
    bids_received: int
    average_weighted_score: float
    recommended_bidder: str
    recommended_bid_amount: float


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
    document_number: str
    revision: str
    revision_date: date | None
    linked_entity_type: str
    linked_entity_id: int
    title: str
    doc_type: str
    discipline: str
    organization: str
    status: str
    review_status: str
    confidentiality: str
    file_name: str
    uri: str
    version: int
    created_at: datetime
    updated_at: datetime


class DocumentAttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    original_file_name: str
    stored_file_name: str
    content_type: str
    extension: str
    size_bytes: int
    sha256: str
    source: str
    uploaded_by: str
    scan_status: str
    validation_message: str
    version: int
    created_at: datetime
    updated_at: datetime


class DocumentCreate(BaseModel):
    document_number: str = ""
    revision: str = "A"
    revision_date: date | None = None
    linked_entity_type: str
    linked_entity_id: int
    title: str
    doc_type: str
    discipline: str = ""
    organization: str = ""
    status: str = "current"
    review_status: str = "not_started"
    confidentiality: str = "project"
    file_name: str = ""
    uri: str


class DocumentUpdate(BaseModel):
    document_number: str | None = None
    revision: str | None = None
    revision_date: date | None = None
    title: str | None = None
    doc_type: str | None = None
    discipline: str | None = None
    organization: str | None = None
    status: str | None = None
    review_status: str | None = None
    confidentiality: str | None = None
    file_name: str | None = None
    uri: str | None = None
    expected_version: int | None = None


class DocumentTransmittalItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    transmittal_id: int
    document_id: int
    document_number: str
    revision: str
    action_required: str
    response_status: str


class DocumentTransmittalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    transmittal_no: str
    subject: str
    purpose: str
    recipient_org: str
    recipient_contact: str
    status: str
    sent_on: date | None
    due_date: date | None
    created_by: str
    version: int
    created_at: datetime
    updated_at: datetime


class DocumentTransmittalCreate(BaseModel):
    transmittal_no: str = ""
    subject: str
    purpose: str = "for_review"
    recipient_org: str = ""
    recipient_contact: str = ""
    status: str = "sent"
    sent_on: date | None = None
    due_date: date | None = None
    document_ids: list[int] = Field(default_factory=list)
    action_required: str = "review"


class DocumentReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    document_id: int
    reviewer_role: str
    review_status: str
    comments: str
    due_date: date | None
    closed_on: date | None
    version: int
    created_at: datetime
    updated_at: datetime


class DocumentReviewCreate(BaseModel):
    reviewer_role: str = "Document Control"
    review_status: str = "outstanding"
    comments: str = ""
    due_date: date | None = None


class DocumentReviewUpdate(BaseModel):
    reviewer_role: str | None = None
    review_status: str | None = None
    comments: str | None = None
    due_date: date | None = None
    closed_on: date | None = None
    expected_version: int | None = None


class ProjectMailOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    mail_no: str
    mail_type: str
    subject: str
    from_role: str
    to_role: str
    status: str
    response_required: bool
    sent_on: date | None
    due_date: date | None
    closed_on: date | None
    body: str
    linked_entity_type: str
    linked_entity_id: int | None
    document_id: int | None
    version: int
    created_at: datetime
    updated_at: datetime


class ProjectMailCreate(BaseModel):
    mail_no: str = ""
    mail_type: str = "letter"
    subject: str
    from_role: str = ""
    to_role: str = ""
    status: str = "outstanding"
    response_required: bool = True
    sent_on: date | None = None
    due_date: date | None = None
    body: str = ""
    linked_entity_type: str = ""
    linked_entity_id: int | None = None
    document_id: int | None = None


class ProjectMailUpdate(BaseModel):
    status: str | None = None
    response_required: bool | None = None
    due_date: date | None = None
    closed_on: date | None = None
    body: str | None = None
    expected_version: int | None = None


class DocumentControlSummary(BaseModel):
    total_documents: int
    current_documents: int
    superseded_documents: int
    outstanding_reviews: int
    overdue_reviews: int
    transmittals_sent: int
    open_mail: int
    overdue_mail: int
    controlled_document_score: float


class WorkPackageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    wbs_id: int | None = None
    control_account_id: int | None
    parent_id: int | None
    package_type: str
    code: str
    title: str
    description: str = ""
    discipline: str
    sequence_no: int
    path_of_construction: str
    owner_role: str
    readiness_status: str
    planned_release_date: date | None = None
    planned_start: date | None
    planned_finish: date | None
    release_required_on: date | None
    main_constraints: str = ""
    progress_percent: float
    version: int
    updated_at: datetime


class WorkPackageCreate(BaseModel):
    wbs_id: int | None = None
    control_account_id: int | None = None
    parent_id: int | None = None
    package_type: str
    code: str
    title: str
    description: str = ""
    discipline: str = ""
    sequence_no: int = 0
    path_of_construction: str = ""
    owner_role: str = "Workface Planner"
    readiness_status: str = "constraint_review"
    planned_release_date: date | None = None
    planned_start: date | None = None
    planned_finish: date | None = None
    release_required_on: date | None = None
    main_constraints: str = ""
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
    priority: str
    evidence_ref: str
    closure_note: str
    exception_ref: str
    closed_by: str
    closed_on: date | None
    blocking: bool
    version: int
    updated_at: datetime


class WorkPackageConstraintCreate(BaseModel):
    constraint_type: str
    description: str
    owner_role: str = "Workface Planner"
    required_by: date | None = None
    status: str = "open"
    priority: str = "medium"
    evidence_ref: str = ""
    closure_note: str = ""
    exception_ref: str = ""
    blocking: bool = True


class WorkPackageConstraintUpdate(BaseModel):
    status: str | None = None
    blocking: bool | None = None
    priority: str | None = None
    evidence_ref: str | None = None
    closure_note: str | None = None
    exception_ref: str | None = None
    expected_version: int | None = None


class AWPReadinessSummary(BaseModel):
    total_packages: int
    cwp_count: int
    iwp_count: int
    twp_count: int
    top_count: int
    ready_for_release: int
    blocked_packages: int
    open_constraints: int
    blocking_constraints: int
    high_priority_constraints: int
    closure_evidence_count: int
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
    schedule_quality_metrics: list[ScheduleQualityMetricOut]
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
    purchase_orders: list[PurchaseOrderOut]
    payment_certificates: list[PaymentCertificateOut]
    warehouse_receipts: list[WarehouseReceiptOut]
    rfq_packages: list[RFQPackageOut]
    rfq_bids: list[RFQBidOut]
    rfq_summary: RFQSummary
    communications: list[ContractCommunicationOut]
    documents: list[DocumentOut]
    document_attachments: list[DocumentAttachmentOut]
    document_transmittals: list[DocumentTransmittalOut]
    document_transmittal_items: list[DocumentTransmittalItemOut]
    document_reviews: list[DocumentReviewOut]
    project_mail: list[ProjectMailOut]
    document_control_summary: DocumentControlSummary
    work_packages: list[WorkPackageOut]
    work_package_constraints: list[WorkPackageConstraintOut]
    awp_summary: AWPReadinessSummary
    ai_brief: str
