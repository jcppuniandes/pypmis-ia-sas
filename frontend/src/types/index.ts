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
  start_date: string | null;
  finish_date: string | null;
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
  imported_at: string;
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
  code: string;
  name: string;
  responsible: string;
  discipline: string;
  cbs_code: string;
  contract_ref: string;
  measurement_rule: string;
  lifecycle_status: string;
  risk_ref: string;
  closure_note: string;
  version: number;
  updated_at: string;
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
  currency: string;
  status: string;
  version: number;
  created_at: string;
  updated_at: string;
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

export type Contract = {
  id: number;
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
  control_account_id: number | null;
  parent_id: number | null;
  package_type: string;
  code: string;
  title: string;
  discipline: string;
  sequence_no: number;
  path_of_construction: string;
  owner_role: string;
  readiness_status: string;
  planned_start: string | null;
  planned_finish: string | null;
  release_required_on: string | null;
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
