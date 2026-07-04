export type WorkspaceView =
  | "business-processes"
  | "control-dashboard"
  | "schedule"
  | "progress"
  | "cost"
  | "awp"
  | "changes"
  | "claims"
  | "rfq"
  | "contracts"
  | "documents"
  | "roadmap"
  | "bp-entry-forms"
  | "admin";

export type Project = {
  id: number;
  code: string;
  name: string;
  phase: string;
  currency: string;
  calendar_base: string;
  owner: string;
  status: string;
  authorization_date: string | null;
  authorization_ref: string;
  configuration: Record<string, unknown>;
  start_date: string | null;
  finish_date: string | null;
};

export type TenantContext = {
  id: number;
  name: string;
  slug: string;
  base_currency: string;
};

export type GuidedProjectContext = {
  id: number;
  code: string;
  name: string;
  status: string;
  currency: string;
};

export type CostCurrencyGate = {
  project_id: number;
  schedule_import_id: number | null;
  detected_currency: string;
  currency_confidence: string;
  currency_source: string;
  currency_confirmed: boolean;
  total_imported_cost: number;
  cost_loaded_activity_count: number;
  cost_loaded_activity_percent: number;
  missing_cost_activity_count: number;
  cost_source_summary: Record<string, unknown>;
  state: string;
  message: string;
};

export type GuidedFlowStep = {
  key: string;
  label: string;
  state: string;
  summary: string;
  next_action: string;
  owner_role: string;
  target_view: string;
  blocking_count: number;
};

export type GuidedNextAction = {
  key: string;
  label: string;
  target_view: string;
  disabled: boolean;
  reason: string;
};

export type GuidedFlow = {
  tenant: TenantContext;
  project: GuidedProjectContext;
  steps: GuidedFlowStep[];
  next_action: GuidedNextAction;
  cost_currency_gate: CostCurrencyGate;
};

export type ProcessFlowItem = {
  key: string;
  label: string;
  status: string;
  owner_role: string;
  evidence: string;
  next_action: string;
  acceptance_criteria: string[];
  target_view: string;
};

export type ProcessFlowLane = {
  key: string;
  label: string;
  owner_role: string;
  items: ProcessFlowItem[];
};

export type ProcessFlowBoard = {
  project_id: number;
  overall_status: string;
  completion_percent: number;
  lanes: ProcessFlowLane[];
};

export type ProjectControlPlan = {
  id: number;
  project_id: number;
  execution_strategy: string;
  control_strategy: string;
  progress_measurement_rule: string;
  cost_measurement_rule: string;
  change_management_rule: string;
  risk_management_rule: string;
  procurement_strategy: string;
  document_control_rule: string;
  reporting_cadence: string;
  status: string;
  version: number;
  created_at: string;
  updated_at: string;
};

export type ProjectOperationalSetup = {
  id: number;
  project_id: number;
  project_number: string;
  setup_template: string;
  attribute_form: string;
  permissions_configured: boolean;
  modules_configured: boolean;
  cost_sheet_ready: boolean;
  funding_sheet_ready: boolean;
  p6_mapping_ready: boolean;
  status: string;
  readiness_status: string;
  readiness_notes: string;
  version: number;
  created_at: string;
  updated_at: string;
};

export type ActivitySheet = {
  id: number;
  project_id: number;
  schedule_import_id: number | null;
  source_file_name: string;
  source: string;
  status: string;
  row_count: number;
  data_date: string | null;
  baseline_name: string;
  validation_summary: string;
  version: number;
  created_at: string;
  updated_at: string;
};

export type ActivitySheetRow = {
  id: number;
  activity_sheet_id: number;
  external_activity_id: string;
  wbs_code: string;
  activity_name: string;
  planned_start: string | null;
  planned_finish: string | null;
  total_float_days: number;
  critical_path: boolean;
  planned_cost: number;
  planned_value: number;
  planned_percent: number;
  cbs_code: string;
  control_account_id: number | null;
  control_account_code: string;
  mapping_status: string;
  review_note: string;
};

export type ActivitySheetWbsRow = {
  wbs_code: string;
  wbs_name: string;
  activity_count: number;
  control_account_count: number;
  planned_cost: number;
  planned_value: number;
  unmapped_activity_count: number;
  needs_review_count: number;
};

export type QuantityTakeoffRun = {
  id: number;
  project_id: number;
  bim_model_id?: number | null;
  source_file_name: string;
  source_type: string;
  source_sha256?: string;
  bim_revision_id?: string;
  model_linked_at?: string | null;
  status: string;
  row_count: number;
  mapped_line_count: number;
  unmapped_line_count: number;
  total_quantity: number;
  validation_summary: string;
  version: number;
  created_at: string;
  updated_at: string;
};

export type BimModel = {
  id: number;
  project_id: number;
  source_file_name: string;
  source_type: string;
  source_sha256?: string;
  revision_id?: string;
  source_size_bytes: number;
  status: string;
  schema: string;
  units: string;
  element_count: number;
  storey_count: number;
  model_identity: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type BimViewerManifest = {
  model_id: number;
  project_id: number;
  source_file_name: string;
  source_size_bytes: number;
  source_sha256: string;
  revision_id: string;
  engine: string;
  cache_status: string;
  geometry_strategy:
    | "backend_cache"
    | "backend_cache_required"
    | "browser_limited_cache_recommended"
    | "direct_browser"
    | string;
  geometry_cache?: BimGeometryCacheSummary | Record<string, unknown>;
  schema: string;
  units: string;
  project_name: string;
  site_name: string;
  building_name: string;
  georeferencing: Record<string, unknown>;
  product_count: number;
  storey_count: number;
  class_summary: Array<{ ifc_class: string; count: number }>;
  property_index: {
    scan_status: "complete" | "partial" | string;
    scan_limit_bytes: number;
    indexed_products: number;
    property_sets: number;
    quantity_sets: number;
    type_relations: number;
  };
  limits: {
    direct_browser_bytes: number;
    backend_cache_required_bytes: number;
  };
  warnings: string[];
};

export type BimGeometryCacheSummary = {
  status: string;
  model_id: number;
  project_id: number;
  source_sha256?: string;
  revision_id: string;
  engine: string;
  storage_path?: string;
  product_count?: number;
  mesh_count: number;
  triangle_count: number;
  generated_at?: string;
};

export type BimGeometryCacheProduct = {
  express_id: number;
  global_id: string;
  ifc_class: string;
  name: string;
  mesh: {
    vertices: number[];
    indices: number[];
  };
};

export type BimGeometryCacheArtifact = {
  version: number;
  model_id: number;
  project_id: number;
  source_file_name?: string;
  source_sha256?: string;
  revision_id?: string;
  engine: string;
  schema?: string;
  units?: string;
  generated_at?: string;
  stats: {
    product_count: number;
    mesh_count: number;
    triangle_count: number;
  };
  products: BimGeometryCacheProduct[];
};

export type BimElementPropertyValue = {
  name: string;
  type: string;
  value: string;
};

export type BimElementQuantityValue = {
  name: string;
  set_name: string;
  source: string;
  step_id: string;
  unit: string;
  value: number | null;
};

export type BimElementProperties = {
  model_id: number;
  lookup_key: string;
  found: boolean;
  scan_status: "complete" | "partial" | string;
  scan_limit_bytes: number;
  step_id: string;
  global_id: string;
  ifc_class: string;
  name: string;
  type_name: string;
  predefined_type: string;
  property_sets: Array<{
    name: string;
    properties: BimElementPropertyValue[];
    step_id: string;
  }>;
  quantities: BimElementQuantityValue[];
  materials: string[];
  classifications: Array<{ code: string; name: string; step_id: string; type: string }>;
};

export type QuantityTakeoffLine = {
  id: number;
  project_id: number;
  run_id: number;
  source_row_id: string;
  element_id: string;
  element_guid: string;
  ifc_class: string;
  category: string;
  family: string;
  type_name: string;
  instance_name: string;
  project_name: string;
  site_name: string;
  building_name: string;
  storey: string;
  system_name: string;
  zone_name: string;
  assembly_name: string;
  classification_system: string;
  classification_code: string;
  quantity: number;
  unit: string;
  measurement_rule: string;
  wbs_code: string;
  cbs_code: string;
  fbs_code: string;
  package_code: string;
  wbs_id: number | null;
  cbs_id: number | null;
  fbs_id: number | null;
  work_package_id: number | null;
  mapping_status: string;
  validation_notes: string;
  raw_data: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type ControlledMeasurementApproval = {
  line_ids: number[];
  measurement_rule: string;
  quantity?: number;
  source: string;
  note: string;
  unit?: string;
};

export type BimGeometryMeasurementResult = {
  line_id: number;
  element_guid: string;
  ifc_class: string;
  element_name: string;
  status: string;
  current_quantity: number;
  current_unit: string;
  source_quantity: number;
  source_unit: string;
  approved_quantity: number | null;
  approved_unit: string;
  geometry_quantity: number;
  geometry_unit: string;
  measurement_rule: string;
  difference: number | null;
  difference_percent: number | null;
  confidence: string;
  reason: string;
};

export type BimGeometryMeasurementBatch = {
  model_id: number;
  run_id: number;
  revision_id: string;
  total_count: number;
  matched_count: number;
  ready_count: number;
  compare_count: number;
  applied_count: number;
  unmatched_count: number;
  invalid_count: number;
  results: BimGeometryMeasurementResult[];
};

export type BimGeometryMeasurementBatchInput = {
  model_id: number;
  line_ids?: number[];
  apply?: boolean;
  replace_valid?: boolean;
};

export type QuantityControlCodeAssignment = {
  line_ids: number[];
  wbs_code: string;
  cbs_code: string;
  fbs_code: string;
  package_code: string;
  cost_item_code?: string;
  cost_item_name?: string;
  budget_unit?: string;
  unit_rate?: number;
  catalog_item_id?: number;
  currency?: string;
  source_key?: string;
  source_url?: string;
  license_note?: string;
  apu_structure?: ApuResourceLine[];
  structure_note?: string;
  structure_status?: string;
  note: string;
};

export type ColombiaApuCatalogItem = {
  id: number;
  tenant_id: number;
  project_id: number;
  source_key: string;
  external_id: string;
  item_code: string;
  item_name: string;
  unit: string;
  unit_rate: number;
  currency: string;
  group_name: string;
  chapter: string;
  region: string;
  source_url: string;
  license_note: string;
  update_frequency: string;
  status: string;
  raw_data: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type ColombiaApuCatalogSync = {
  project_id: number;
  source_key: string;
  source_url: string;
  created_count: number;
  updated_count: number;
  skipped_count: number;
  total_count: number;
  license_note: string;
  update_frequency: string;
  synced_at: string;
};

export type ApuResourceLine = {
  amount: number;
  code?: string;
  component: string;
  component_type?: string;
  description: string;
  quantity: number;
  source?: string;
  status?: string;
  unit: string;
  unit_rate: number;
};

export type QuantityApuSuggestionInput = {
  line_ids: number[];
  apply_best: boolean;
  limit_per_line?: number;
};

export type QuantityApuApprovalInput = {
  line_ids: number[];
};

export type QuantityApuSuggestion = {
  line_id: number;
  catalog_item_id: number;
  source_key: string;
  cost_item_code: string;
  cost_item_name: string;
  budget_unit: string;
  unit_rate: number;
  currency: string;
  quantity: number;
  budget_amount: number;
  match_score: number;
  review_note: string;
  source_url: string;
  license_note: string;
  apu_structure?: ApuResourceLine[];
  structure_note?: string;
  structure_status?: string;
};

export type BimQuantityRule = {
  id: number;
  project_id: number;
  ifc_class: string;
  element_label: string;
  expected_measure: string;
  rule_hint: string;
  expected_units: string[];
  allow_fallback_count: boolean;
  source: string;
  status: string;
  version: number;
  created_at: string;
  updated_at: string;
};

export type BimQuantityRuleUpdate = {
  element_label: string;
  expected_measure: string;
  rule_hint: string;
  expected_units: string[];
  allow_fallback_count: boolean;
  status: string;
  expected_version: number;
};

export type QuantityRuleRecalculationImpact = {
  line_id: number;
  element_guid: string;
  ifc_class: string;
  previous_status: string;
  new_status: string;
  previous_measure: string;
  new_measure: string;
  previous_units: string[];
  new_units: string[];
  mapping_status: string;
};

export type QuantityRuleRecalculation = {
  project_id: number;
  run_id: number;
  total_lines: number;
  changed_line_count: number;
  valid_count: number;
  review_count: number;
  blocked_count: number;
  cost_rollup_gate: string;
  affected_classes: string[];
  impacts: QuantityRuleRecalculationImpact[];
};

export type User = {
  id: number;
  email: string;
  full_name: string;
  title: string;
  status: string;
};

export type AuthSession = {
  access_token: string;
  token_type: string;
  expires_in: number;
  tenant_id: number;
  user: User;
};

export type ProjectMembership = {
  id: number;
  project_id: number;
  user_id: number;
  role: string;
  can_capture_progress: boolean;
  can_capture_cost: boolean;
  can_approve_workflow: boolean;
  can_manage_contract: boolean;
  can_configure: boolean;
};

export type ProjectTeamMember = {
  user: User;
  membership: ProjectMembership;
};

export type RoleProfile = {
  role: string;
  description: string;
  can_capture_progress: boolean;
  can_capture_cost: boolean;
  can_approve_workflow: boolean;
  can_manage_contract: boolean;
  can_configure: boolean;
};

export type KPI = {
  control_account_id: number | null;
  pv: number;
  ev: number;
  ac: number;
  spi: number;
  cpi: number;
  sv: number;
  cv: number;
  bac: number;
  eac: number;
  etc: number;
  vac: number;
};

export type ControlSnapshot = {
  id: number;
  control_account_id: number | null;
  period_label: string;
  data_date: string | null;
  pv: number;
  ev: number;
  ac: number;
  spi: number;
  cpi: number;
  sv: number;
  cv: number;
  bac: number;
  eac: number;
  etc: number;
  vac: number;
  productivity_index: number | null;
  created_at: string;
};

export type ForecastScenario = {
  id: number;
  period_label: string;
  name: string;
  method: string;
  cpi_factor: number;
  spi_factor: number;
  eac: number;
  etc: number;
  vac: number;
  completion_risk: string;
  summary: string;
  created_at: string;
};

export type ProductivitySummary = {
  total_quantity: number;
  total_labor_hours: number;
  productivity_rate: number;
  productivity_index: number;
  low_productivity_accounts: number;
};

export type Alert = {
  id: number;
  control_account_id: number | null;
  severity: "green" | "amber" | "red";
  rule: string;
  message: string;
  recommendation: string;
  status: string;
};

export type ScheduleImport = {
  id: number;
  source: string;
  file_name: string;
  status: string;
  data_date: string | null;
  baseline_name: string;
  quality_score: number;
  validation_summary: string;
  detected_currency: string;
  currency_confidence: string;
  currency_source: string;
  currency_confirmed: boolean;
  total_imported_cost: number;
  cost_loaded_activity_count: number;
  cost_loaded_activity_percent: number;
  cost_source_summary: Record<string, unknown>;
  imported_at: string;
};

export type ScheduleActivityMap = {
  id: number;
  schedule_import_id: number;
  activity_id: number | null;
  external_activity_id: string;
  wbs_code: string;
  activity_name: string;
  planned_start: string | null;
  planned_finish: string | null;
  total_float_days: number;
  critical_path: boolean;
};

export type ScheduleRelationship = {
  id: number;
  schedule_import_id: number;
  predecessor_external_id: string;
  successor_external_id: string;
  relationship_type: string;
  days_lag?: number;
  lag_days?: number;
};

export type ScheduleFinding = {
  id: number;
  schedule_import_id: number;
  check_code: string;
  severity: string;
  message: string;
  item_count: number;
  weight: number;
};

export type ScheduleQualityMetric = {
  key: string;
  standard: string;
  label: string;
  status: string;
  item_count: number;
  total_count: number;
  percent: number;
  threshold: string;
  description: string;
};

export type BaselineVersion = {
  id: number;
  schedule_import_id: number;
  version_no: number;
  name: string;
  status: string;
  data_date: string | null;
  quality_score: number;
  created_at: string;
};

export type ControlPeriod = {
  id: number;
  period_label: string;
  data_date: string | null;
  status: string;
  created_at: string;
};

export type WorkflowInstance = {
  id: number;
  process_code: string;
  process_name: string;
  record_no: string;
  title: string;
  status: string;
  current_step: string;
  ball_in_court: string;
  trigger_entity_type: string;
  trigger_entity_id: number;
  created_at: string;
  updated_at: string;
  version: number;
};

export type WorkflowStep = {
  id: number;
  process_instance_id: number;
  step_order: number;
  name: string;
  detail: string;
  owner_role: string;
  status: string;
  tone: string;
};

export type ProcessStepTemplate = {
  id: number | null;
  step_order: number;
  name: string;
  detail: string;
  owner_role: string;
  status: string;
  tone: string;
};

export type ProcessTransitionTemplate = {
  id: number | null;
  action: string;
  label: string;
  from_step: string;
  to_step: string;
  process_status: string;
  ball_in_court: string;
  from_status: string;
  from_tone: string;
  to_status: string;
  to_tone: string;
  requires_approval: boolean;
  permission_key: string;
};

export type ProcessTemplate = {
  id: number | null;
  code: string;
  name: string;
  category: string;
  description: string;
  version_no: number;
  form_schema: string[];
  workflow_steps: string[];
  roles: string[];
  status: string;
  step_templates: ProcessStepTemplate[];
  transitions: ProcessTransitionTemplate[];
};

export type AuditLog = {
  id: number;
  actor: string;
  action: string;
  entity_type: string;
  entity_id: number | null;
  payload: string;
  created_at: string;
};

export type ControlAccount = {
  id: number;
  wbs_id?: number;
  awp_package_id?: number | null;
  code: string;
  name: string;
  responsible: string;
  discipline: string;
  scope?: string;
  budget?: number;
  start_date?: string | null;
  finish_date?: string | null;
  cbs_code: string;
  contract_ref: string;
  measurement_rule: string;
  earned_value?: number;
  actual_cost?: number;
  forecast?: number;
  lifecycle_status: string;
  risk_ref: string;
  closure_note: string;
  version: number;
  updated_at: string;
};

export type WbsNode = {
  id: number;
  parent_id: number | null;
  code: string;
  name: string;
  level: number;
  description: string;
  dictionary: string;
  responsible: string;
  status: string;
};

export type ControlAccountMapping = {
  id: number;
  schedule_import_id: number;
  schedule_activity_map_id: number;
  activity_id: number | null;
  control_account_id: number | null;
  wbs_code: string;
  wbs_name: string;
  cbs_code: string;
  mapping_rule: string;
  planned_cost: number;
  planned_value: number;
  planned_percent: number;
  status: string;
  review_note: string;
};

export type ControlAccountMappingSummary = {
  total_schedule_activities: number;
  mapped_activities: number;
  unmapped_activities: number;
  control_account_count: number;
  cost_loaded_activities: number;
  total_bac: number;
  total_planned_value: number;
  mapping_score: number;
  cost_loading_score: number;
  baseline_status: string;
};

export type DataQualityGate = {
  name: string;
  status: string;
  score: number;
  finding: string;
  owner_role: string;
};

export type ProgressRecord = {
  id: number;
  control_account_id: number;
  physical_percent: number;
  quantity_installed: number;
  labor_hours: number;
  reported_on: string;
  evidence_ref: string;
};

export type CostRecord = {
  id: number;
  control_account_id: number;
  source: string;
  amount: number;
  incurred_on: string;
  description: string;
};

export type CostSheetLine = {
  control_account_id: number;
  control_account_code: string;
  control_account_name: string;
  cbs_code: string;
  bac: number;
  planned_value: number;
  actual_cost: number;
  incurred_payment_certificate_value: number;
  incurred_warehouse_receipt_value: number;
  committed_contract_value: number;
  committed_purchase_order_value: number;
  committed_cost: number;
  earned_value: number;
  variance: number;
  cpi: number;
};

export type FundingSource = {
  id: number;
  project_id: number;
  code: string;
  name: string;
  amount: number;
  approved_amount: number;
  source_of_funds: string;
  funding_type: string;
  authorization_ref: string;
  usage_restrictions: string;
  funds_available: number;
  funds_committed: number;
  funds_executed: number;
  balance: number;
  currency: string;
  status: string;
  usage_rules: string;
  version: number;
  created_at: string;
  updated_at: string;
};

export type IntegratedControlMatrixRow = {
  project_id: number;
  project_code: string;
  project_name: string;
  fbs_code: string;
  wbs_code: string;
  awp_package_code: string;
  awp_package_type: string;
  control_account_code: string;
  cbs_code: string;
  cost_code: string;
  contract_ref: string;
  budget: number;
  funds_available: number;
  committed: number;
  actual: number;
  forecast: number;
  balance: number;
  status: string;
};

export type CostBreakdownStructure = {
  id: number;
  project_id: number;
  parent_id: number | null;
  code: string;
  level: number;
  cost_category: string;
  description: string;
  status: string;
  version: number;
  created_at: string;
  updated_at: string;
};

export type CostCode = {
  id: number;
  project_id: number;
  wbs_id: number;
  control_account_id: number;
  cbs_id: number;
  fbs_id: number;
  contract_ref: string;
  code: string;
  budget: number;
  funds_available: number;
  commitments: number;
  actual_costs: number;
  forecast: number;
  status: string;
  version: number;
  created_at: string;
  updated_at: string;
};

export type BusinessProcessInstance = {
  id: number;
  process_code: string;
  process_name: string;
  record_no: string;
  title: string;
  status: string;
  current_step: string;
  ball_in_court: string;
  trigger_entity_type: string;
  trigger_entity_id: number;
  created_at: string;
  updated_at: string;
  version: number;
};

export type BusinessProcessPolicy = {
  id: number;
  project_id: number;
  process_code: string;
  action: string;
  required_role: string;
  permission_key: string;
  status: string;
  version: number;
  created_at: string;
  updated_at: string;
};

export type BusinessProcessLineItem = {
  id: number;
  process_instance_id: number;
  line_type: string;
  wbs_id: number | null;
  cbs_id: number;
  funding_source_id: number | null;
  control_account_id: number | null;
  cost_code_id: number | null;
  amount: number;
  quantity: number;
  description: string;
  status: string;
  version: number;
  created_at: string;
  updated_at: string;
};

export type BusinessProcessLineItemRevision = {
  id: number;
  line_item_id: number;
  process_instance_id: number;
  previous_version: number;
  new_version: number;
  previous_amount: number;
  new_amount: number;
  previous_quantity: number;
  new_quantity: number;
  previous_description: string;
  new_description: string;
  previous_status: string;
  new_status: string;
  change_note: string;
  changed_by: string;
  created_at: string;
};

export type ScheduleOfValueLine = {
  id: number;
  contract_id: number;
  line_no: string;
  description: string;
  amount: number;
  cbs_id: number;
  wbs_id: number | null;
  control_account_id: number | null;
  status: string;
  version: number;
  created_at: string;
  updated_at: string;
};

export type CommitmentFundingLine = {
  id: number;
  contract_id: number;
  sov_line_id: number | null;
  funding_source_id: number;
  amount: number;
  consumed_amount: number;
  status: string;
  version: number;
  created_at: string;
  updated_at: string;
};

export type RateSheetLine = {
  id: number;
  rate_sheet_id: number;
  cbs_code: string;
  unit_rate: number;
  multiplier: number;
  status: string;
  created_at: string;
  updated_at: string;
};

export type RateSheet = {
  id: number;
  code: string;
  name: string;
  status: string;
  version: number;
  created_at: string;
  updated_at: string;
  line_items: RateSheetLine[];
};

export type ActivitySheetRecostResult = {
  project_id: number;
  activity_sheet_id: number;
  rate_sheet_id: number;
  recost_run_id: number | null;
  updated_rows: number;
  total_planned_cost: number;
  total_planned_value: number;
};

export type ActivitySheetRecostRunLine = {
  id: number;
  recost_run_id: number;
  activity_sheet_row_id: number;
  external_activity_id: string;
  cbs_code: string;
  previous_planned_cost: number;
  new_planned_cost: number;
  previous_planned_value: number;
  new_planned_value: number;
  created_at: string;
};

export type ActivitySheetRecostRun = {
  id: number;
  activity_sheet_id: number;
  rate_sheet_id: number;
  run_no: number;
  updated_rows: number;
  total_planned_cost: number;
  total_planned_value: number;
  created_by: string;
  created_at: string;
  lines: ActivitySheetRecostRunLine[];
};

export type ReconciliationReportRow = {
  wbs_code: string;
  cbs_code: string;
  fbs_code: string;
  control_account_code: string;
  contract_ref: string;
  budget: number;
  committed: number;
  funded_amount: number;
  sov_amount: number;
  forecast: number;
  variance: number;
};

export type ReconciliationReport = {
  project_id: number;
  rows: ReconciliationReportRow[];
};

export type ControlAgentFinding = {
  id: number;
  run_id: number;
  severity: string;
  category: string;
  title: string;
  evidence: string;
  recommendation: string;
  owner_role: string;
  entity_type: string;
  entity_id: number | null;
  status: string;
  created_at: string;
};

export type ControlAgentRun = {
  id: number;
  project_id: number;
  agent_code: string;
  agent_name: string;
  run_mode: string;
  model_name: string;
  status: string;
  score: number;
  summary: string;
  created_by: string;
  created_at: string;
  findings: ControlAgentFinding[];
};

export type ForecastFundingRow = {
  funding_source_id: number;
  fbs_code: string;
  approved_amount: number;
  funds_available: number;
  funds_committed: number;
  funds_executed: number;
  forecast: number;
  forecast_vs_available: number;
  forecast_vs_approved: number;
  status: string;
};

export type ForecastFundingReport = {
  project_id: number;
  rows: ForecastFundingRow[];
};

export type CloseoutReport = {
  project_id: number;
  funding_source_id: number | null;
  approved_amount: number;
  committed: number;
  actual: number;
  forecast: number;
  unused_balance: number;
  open_commitments: number;
  closed_commitments: number;
  funding_status: string;
};

export type CashFlowPeriod = {
  id: number;
  project_id: number;
  period_label: string;
  planned_inflow: number;
  planned_outflow: number;
  actual_inflow: number;
  actual_outflow: number;
  forecast_outflow: number;
  version: number;
  created_at: string;
  updated_at: string;
};

export type CostManagerSummary = {
  total_bac: number;
  total_planned_value: number;
  total_earned_value: number;
  total_actual_cost: number;
  total_incurred_from_payment_certificates: number;
  total_incurred_from_warehouse_receipts: number;
  total_contract_commitments: number;
  total_purchase_order_commitments: number;
  total_committed_cost: number;
  total_funding: number;
  planned_inflow: number;
  actual_inflow: number;
  planned_outflow: number;
  actual_outflow: number;
  forecast_outflow: number;
  cost_variance: number;
  funding_variance: number;
  funding_coverage_percent: number;
  cash_flow_variance: number;
};

export type FlowStep = {
  name: string;
  purpose: string;
  state: string;
};

export type WorkItem = {
  id: number;
  control_account_id: number | null;
  title: string;
  status: string;
};

export type ChangeItem = WorkItem & {
  deviation: string;
  cost_impact: number;
  schedule_impact_days: number;
};

export type ClaimItem = WorkItem & {
  causality: string;
  impact: string;
  evidence_summary: string;
};

export type ClaimEntitlementItem = {
  id: number;
  claim_id: number;
  practice_source: string;
  category: string;
  element: string;
  requirement: string;
  assessment: string;
  evidence_ref: string;
  status: string;
  weight: number;
  score: number;
  sequence_no: number;
  version: number;
  updated_at: string;
};

export type ClaimEntitlementSummary = {
  total_items: number;
  satisfied_items: number;
  partial_items: number;
  gap_items: number;
  cumulative_items: number;
  cumulative_gap_items: number;
  entitlement_score: number;
};

export type ContractNotice = {
  id: number;
  contract_id: number | null;
  claim_id: number | null;
  change_request_id: number | null;
  notice_type: string;
  subject: string;
  reference: string;
  event_date: string | null;
  notice_date: string | null;
  due_date: string | null;
  status: string;
  days_late: number;
  compliance_status: string;
  created_at: string;
};

export type ClaimImpactAnalysis = {
  id: number;
  claim_id: number;
  method: string;
  impacted_activity: string;
  cause: string;
  effect: string;
  schedule_impact_days: number;
  cost_impact: number;
  productivity_loss_percent: number;
  evidence_ref: string;
  confidence_score: number;
  status: string;
  created_at: string;
  version: number;
  updated_at: string;
};

export type ClaimsForensicSummary = {
  total_claims: number;
  notice_count: number;
  compliant_notices: number;
  late_notices: number;
  impact_analyses: number;
  quantified_claims: number;
  total_claimed_cost: number;
  total_schedule_impact_days: number;
  forensic_readiness_score: number;
};

export type ForensicDossierAnalysis = {
  mode: string;
  summary: string;
  source_files: string[];
  signals: string[];
  readiness_score: number;
  created_claims: ClaimItem[];
  created_notices: ContractNotice[];
  created_entitlement_items: ClaimEntitlementItem[];
  created_impact_analyses: ClaimImpactAnalysis[];
};

export type ForensicRagSource = {
  title: string;
  file_name: string;
  source_type: string;
  relevance: string;
  tags: string[];
};

export type ForensicWindowScheduleSource = {
  file_name: string;
  source: string;
  status: string;
  data_date: string | null;
  baseline_name: string;
  activity_count: number;
  relationship_count: number;
  quality_score: number;
  finding_code: string;
  message: string;
};

export type ForensicWindowActivityDelta = {
  activity_id: string;
  activity_name: string;
  wbs_code: string;
  wbs_name: string;
  start_slip_days: number;
  finish_slip_days: number;
  total_float_delta_days: number;
  critical_in_start: boolean;
  critical_in_finish: boolean;
  classification: string;
};

export type ForensicWindowLogicDelta = {
  added_relationships: number;
  removed_relationships: number;
  changed_relationships: number;
};

export type ForensicWindowResult = {
  window_no: number;
  start_schedule: string;
  finish_schedule: string;
  start_data_date: string | null;
  finish_data_date: string | null;
  start_completion: string | null;
  finish_completion: string | null;
  completion_slip_days: number;
  critical_delay_days: number;
  mitigation_days: number;
  common_activity_count: number;
  added_activity_count: number;
  removed_activity_count: number;
  delayed_activity_count: number;
  critical_or_near_critical_delay_count: number;
  logic_delta: ForensicWindowLogicDelta;
  top_delay_events: ForensicWindowActivityDelta[];
  interpretation: string;
};

export type ForensicWindowAnalysis = {
  method_id: string;
  method_name: string;
  standard_reference: string;
  methodology_note: string;
  schedule_sources: ForensicWindowScheduleSource[];
  windows: ForensicWindowResult[];
  rag_sources: ForensicRagSource[];
  summary: Record<string, number | string>;
  limitations: string[];
};

export type Contract = {
  id: number;
  funding_source_id?: number | null;
  control_account_id: number | null;
  code: string;
  title: string;
  counterparty: string;
  contract_type: string;
  value: number;
  status: string;
};

export type PurchaseOrder = {
  id: number;
  control_account_id: number | null;
  contract_id: number | null;
  po_number: string;
  description: string;
  vendor: string;
  committed_amount: number;
  status: string;
  issued_on: string | null;
  version: number;
  created_at: string;
  updated_at: string;
};

export type PaymentCertificate = {
  id: number;
  control_account_id: number | null;
  contract_id: number | null;
  purchase_order_id: number | null;
  certificate_no: string;
  period_label: string;
  certified_amount: number;
  retained_amount: number;
  status: string;
  certified_on: string | null;
  version: number;
  created_at: string;
  updated_at: string;
};

export type WarehouseReceipt = {
  id: number;
  control_account_id: number | null;
  contract_id: number | null;
  purchase_order_id: number | null;
  receipt_no: string;
  description: string;
  received_quantity: number;
  unit_cost: number;
  received_value: number;
  status: string;
  received_on: string | null;
  version: number;
  created_at: string;
  updated_at: string;
};

export type RFQPackage = {
  id: number;
  control_account_id: number | null;
  package_no: string;
  title: string;
  scope_summary: string;
  procurement_method: string;
  status: string;
  budget_amount: number;
  issue_date: string | null;
  due_date: string | null;
  version: number;
  created_at: string;
  updated_at: string;
};

export type RFQBid = {
  id: number;
  rfq_package_id: number;
  bidder_name: string;
  bid_amount: number;
  technical_score: number;
  commercial_score: number;
  schedule_score: number;
  risk_score: number;
  weighted_score: number;
  status: string;
  submitted_on: string | null;
  notes: string;
  version: number;
  created_at: string;
  updated_at: string;
};

export type RFQSummary = {
  total_packages: number;
  issued_packages: number;
  bids_received: number;
  average_weighted_score: number;
  recommended_bidder: string;
  recommended_bid_amount: number;
};

export type ContractCommunication = {
  id: number;
  contract_id: number | null;
  communication_type: string;
  subject: string;
  reference: string;
  sent_on: string;
  status: string;
};

export type DocumentItem = {
  id: number;
  document_number: string;
  revision: string;
  revision_date: string | null;
  linked_entity_type: string;
  linked_entity_id: number;
  title: string;
  doc_type: string;
  discipline: string;
  organization: string;
  status: string;
  review_status: string;
  confidentiality: string;
  file_name: string;
  uri: string;
  version: number;
  created_at: string;
  updated_at: string;
};

export type DocumentAttachment = {
  id: number;
  document_id: number;
  original_file_name: string;
  stored_file_name: string;
  content_type: string;
  extension: string;
  size_bytes: number;
  sha256: string;
  source: string;
  uploaded_by: string;
  scan_status: string;
  validation_message: string;
  version: number;
  created_at: string;
  updated_at: string;
};

export type DocumentTransmittal = {
  id: number;
  transmittal_no: string;
  subject: string;
  purpose: string;
  recipient_org: string;
  recipient_contact: string;
  status: string;
  sent_on: string | null;
  due_date: string | null;
  created_by: string;
  version: number;
  created_at: string;
  updated_at: string;
};

export type DocumentTransmittalItem = {
  id: number;
  transmittal_id: number;
  document_id: number;
  document_number: string;
  revision: string;
  action_required: string;
  response_status: string;
};

export type DocumentReview = {
  id: number;
  document_id: number;
  reviewer_role: string;
  review_status: string;
  comments: string;
  due_date: string | null;
  closed_on: string | null;
  version: number;
  created_at: string;
  updated_at: string;
};

export type ProjectMail = {
  id: number;
  mail_no: string;
  mail_type: string;
  subject: string;
  from_role: string;
  to_role: string;
  status: string;
  response_required: boolean;
  sent_on: string | null;
  due_date: string | null;
  closed_on: string | null;
  body: string;
  linked_entity_type: string;
  linked_entity_id: number | null;
  document_id: number | null;
  version: number;
  created_at: string;
  updated_at: string;
};

export type DocumentControlSummary = {
  total_documents: number;
  current_documents: number;
  superseded_documents: number;
  outstanding_reviews: number;
  overdue_reviews: number;
  transmittals_sent: number;
  open_mail: number;
  overdue_mail: number;
  controlled_document_score: number;
};

export type WorkPackage = {
  id: number;
  wbs_id: number | null;
  control_account_id: number | null;
  parent_id: number | null;
  package_type: string;
  code: string;
  title: string;
  description: string;
  discipline: string;
  sequence_no: number;
  path_of_construction: string;
  owner_role: string;
  readiness_status: string;
  planned_release_date: string | null;
  planned_start: string | null;
  planned_finish: string | null;
  release_required_on: string | null;
  main_constraints: string;
  progress_percent: number;
  version: number;
  updated_at: string;
};

export type WorkPackageConstraint = {
  id: number;
  work_package_id: number;
  constraint_type: string;
  description: string;
  owner_role: string;
  required_by: string | null;
  status: string;
  priority: string;
  evidence_ref: string;
  closure_note: string;
  exception_ref: string;
  closed_by: string;
  closed_on: string | null;
  blocking: boolean;
  version: number;
  updated_at: string;
};

export type AWPReadinessSummary = {
  total_packages: number;
  cwp_count: number;
  iwp_count: number;
  twp_count: number;
  top_count: number;
  ready_for_release: number;
  blocked_packages: number;
  open_constraints: number;
  blocking_constraints: number;
  high_priority_constraints: number;
  closure_evidence_count: number;
  readiness_score: number;
};

export type PilotReadinessItem = {
  phase: string;
  area: string;
  status: string;
  score: number;
  finding: string;
  next_action: string;
};

export type PilotReadiness = {
  project_id: number;
  project_code: string;
  status: string;
  score: number;
  blockers: string[];
  items: PilotReadinessItem[];
};

export type Dashboard = {
  project: Project;
  control_plan: ProjectControlPlan | null;
  current_user: User;
  current_membership: ProjectMembership;
  project_team: ProjectTeamMember[];
  schedule_import: ScheduleImport | null;
  schedule_activity_count: number;
  schedule_relationship_count: number;
  schedule_findings: ScheduleFinding[];
  schedule_quality_metrics: ScheduleQualityMetric[];
  baseline_versions: BaselineVersion[];
  control_periods: ControlPeriod[];
  workflow_instance: WorkflowInstance | null;
  workflow_steps: WorkflowStep[];
  business_processes: WorkflowInstance[];
  process_templates: ProcessTemplate[];
  audit_logs: AuditLog[];
  data_quality_gates: DataQualityGate[];
  flow: FlowStep[];
  loop: { step: string; description: string }[];
  control_accounts: ControlAccount[];
  control_account_mappings: ControlAccountMapping[];
  control_account_mapping_summary: ControlAccountMappingSummary;
  latest_progress_records: ProgressRecord[];
  latest_cost_records: CostRecord[];
  cost_sheet: CostSheetLine[];
  funding_sources: FundingSource[];
  cash_flow: CashFlowPeriod[];
  cost_manager_summary: CostManagerSummary;
  project_kpi: KPI;
  account_kpis: KPI[];
  control_snapshots: ControlSnapshot[];
  forecast_scenarios: ForecastScenario[];
  productivity_summary: ProductivitySummary;
  alerts: Alert[];
  changes: ChangeItem[];
  claims: ClaimItem[];
  claim_entitlement_items: ClaimEntitlementItem[];
  claim_entitlement_summary: ClaimEntitlementSummary;
  contract_notices: ContractNotice[];
  claim_impact_analyses: ClaimImpactAnalysis[];
  claims_forensic_summary: ClaimsForensicSummary;
  contracts: Contract[];
  purchase_orders: PurchaseOrder[];
  payment_certificates: PaymentCertificate[];
  warehouse_receipts: WarehouseReceipt[];
  rfq_packages: RFQPackage[];
  rfq_bids: RFQBid[];
  rfq_summary: RFQSummary;
  communications: ContractCommunication[];
  documents: DocumentItem[];
  document_attachments: DocumentAttachment[];
  document_transmittals: DocumentTransmittal[];
  document_transmittal_items: DocumentTransmittalItem[];
  document_reviews: DocumentReview[];
  project_mail: ProjectMail[];
  document_control_summary: DocumentControlSummary;
  work_packages: WorkPackage[];
  work_package_constraints: WorkPackageConstraint[];
  awp_summary: AWPReadinessSummary;
  ai_brief: string;
};
