export type PortfolioReviewStatus =
  | "DRAFT"
  | "PREPARING"
  | "READY_FOR_REVIEW"
  | "IN_REVIEW"
  | "COMPLETED"
  | "RETURNED"
  | "CANCELLED"
  | "SUPERSEDED"
  | "STALE";

export type PortfolioReviewActionStatus = "OPEN" | "ACCEPTED" | "IN_PROGRESS" | "COMPLETED" | "REJECTED" | "CANCELLED";

export type PortfolioReviewPage<T> = {
  items: T[];
  page: number;
  pageSize: number;
  total: number;
  nextCursor: string | null;
};

export type PortfolioReviewReadiness = {
  overall: string;
  ready: boolean;
  dimensions: Record<string, string | boolean | number | null>;
  blockers: string[];
  warnings: string[];
};

export type PortfolioReviewAgendaItem = {
  code: string;
  label: string;
  status?: string;
  required?: boolean;
  notes?: string;
  warnings?: string[];
};

export type PortfolioReviewConclusion = {
  id?: number;
  conclusion_type: string;
  rationale: string;
  conditions?: Array<Record<string, unknown>>;
  recorded_by?: number | string | null;
  recorded_at?: string | null;
  revision_version?: number;
};

export type PortfolioReviewSnapshotSource = {
  source_type: string;
  source_id?: number | string | null;
  source_version?: number | string | null;
  source_hash?: string | null;
  source_current?: boolean;
  as_of?: string | null;
  required?: boolean;
  status?: string;
};

export type PortfolioReviewSnapshot = {
  id?: number;
  snapshot_id?: number;
  snapshot_hash: string | null;
  frozen_at?: string | null;
  generated_at?: string | null;
  source_as_of?: string | null;
  source_current: boolean;
  staleness_status?: string;
  persisted?: boolean;
  portfolio?: Record<string, unknown>;
  membership?: Record<string, unknown>;
  evaluation?: Record<string, unknown>;
  allocation?: PortfolioReviewAllocationContext;
  budget?: Record<string, unknown>;
  resources?: Record<string, unknown>;
  scenario_convergence?: Record<string, unknown>;
  gate?: Record<string, unknown>;
  risk_readiness?: Record<string, unknown>;
  summary?: Record<string, unknown>;
  sources: PortfolioReviewSnapshotSource[];
  warnings: string[];
  blockers: string[];
  changes?: PortfolioReviewSnapshotChange[];
  payload?: Record<string, unknown>;
};

export type PortfolioReviewSnapshotChange = {
  source_type?: string;
  category?: string;
  change_type?: string;
  label?: string;
  before?: unknown;
  after?: unknown;
  material?: boolean;
};

export type PortfolioReviewSession = {
  id: number;
  review_session_id?: number;
  review_number: string;
  name?: string;
  description?: string;
  portfolio_id: number;
  portfolio_workspace_id?: number;
  portfolio_name?: string | null;
  planning_cycle_id: number | null;
  allocation_plan_id: number | null;
  allocation_plan_number?: string | null;
  review_type: string;
  review_date: string;
  planned_review_date?: string | null;
  actual_review_date?: string | null;
  review_period_start: string | null;
  review_period_end: string | null;
  next_planned_review_date: string | null;
  status: PortfolioReviewStatus | string;
  chair?: string | null;
  chair_user_id?: number | null;
  accountable_owner?: string | null;
  secretary?: string | null;
  secretary_user_id?: number | null;
  scope_workspace_id?: number | null;
  agenda: PortfolioReviewAgendaItem[];
  conclusions: PortfolioReviewConclusion[];
  configuration_revision?: number | null;
  configuration_hash?: string | null;
  snapshot_id?: number | null;
  snapshot_hash?: string | null;
  snapshot?: PortfolioReviewSnapshot | null;
  readiness: PortfolioReviewReadiness;
  summary: Record<string, unknown>;
  actions: PortfolioReviewAction[];
  source_current: boolean;
  staleness_status?: string;
  revision_version: number;
  allowed_actions: string[];
  created_by?: number | string | null;
  created_at?: string;
  updated_at?: string;
  completed_at?: string | null;
};

export type PortfolioReviewSessionDraft = {
  portfolio_id: number;
  portfolio_workspace_id?: number;
  planning_cycle_id: number | null;
  allocation_plan_id: number | null;
  review_type: string;
  review_date: string;
  planned_review_date?: string | null;
  review_period_start: string | null;
  review_period_end: string | null;
  next_planned_review_date: string | null;
  title?: string;
  description?: string;
  chair?: string | null;
  chair_user_id?: number | null;
  accountable_owner?: string | null;
  secretary?: string | null;
  secretary_user_id?: number | null;
  agenda?: PortfolioReviewAgendaItem[];
};

export type PortfolioReviewPosition = {
  percentage?: string | number | null;
  amount?: string | number | null;
  amounts_by_currency: Record<string, string | number>;
  count?: number;
  evaluable?: boolean;
};

export type PortfolioReviewAllocationBucket = {
  bucket_code: string;
  bucket_name: string;
  target: PortfolioReviewPosition;
  current_demand: PortfolioReviewPosition;
  current_portfolio: PortfolioReviewPosition;
  recommended: PortfolioReviewPosition;
  approved: PortfolioReviewPosition;
  variance_percentage?: string | number | null;
  variance_amount?: string | number | null;
  status: string;
};

export type PortfolioReviewAllocationContext = {
  allocation_plan_id?: number | null;
  allocation_plan_number?: string | null;
  allocation_plan_version?: number | null;
  allocation_plan_hash?: string | null;
  source_current: boolean;
  multi_currency: boolean;
  normalization_warning?: string | null;
  buckets: PortfolioReviewAllocationBucket[];
  unclassified: PortfolioReviewPosition;
  unclassified_by_position?: Record<string, PortfolioReviewPosition>;
  warnings: string[];
};

export type PortfolioReviewProjectRow = {
  project_id: number | string;
  project_number?: string | null;
  project_name: string;
  portfolio_rank?: number | string | null;
  strategic_bucket?: string | null;
  allocation_variance_contribution?: string | number | Record<string, unknown> | null;
  budget_status?: string | null;
  resource_status?: string | null;
  gate_stage?: string | null;
  gate_readiness?: string | null;
  investment_decision?: string | null;
  fid_status?: string | null;
  risk_readiness?: string | null;
  recommended_status?: string | null;
  approved_amounts_by_currency?: Record<string, string | number>;
  review_action?: string | null;
  review_actions?: PortfolioReviewAction[];
  action_owner?: string | null;
  action_due_date?: string | null;
  blocked?: boolean;
  stale?: boolean;
  unclassified?: boolean;
};

export type PortfolioReviewProjectMatrix = PortfolioReviewPage<PortfolioReviewProjectRow> & {
  filters?: Record<string, unknown>;
  generated_at?: string;
  source_current?: boolean;
};

export type PortfolioReviewBudgetResources = {
  budget: Record<string, unknown>;
  resources: Record<string, unknown>;
  compatibility: Record<string, unknown>;
  source_current: boolean;
  warnings: string[];
  blockers: string[];
};

export type PortfolioReviewGateStatus = {
  preparation?: Record<string, unknown>;
  summary: Record<string, unknown>;
  projects: Array<Record<string, unknown>>;
  source_current: boolean;
  warnings: string[];
  blockers: string[];
};

export type PortfolioReviewAction = {
  id: number;
  action_id?: number;
  review_session_id: number;
  subject_type: string;
  subject_id: string | number | null;
  subject_key?: string | null;
  subject_name?: string | null;
  action_type: string;
  rationale: string;
  priority: string;
  owner?: string | null;
  owner_user_id?: number | null;
  due_date: string | null;
  status: PortfolioReviewActionStatus | string;
  source_evidence_references?: Array<Record<string, unknown>>;
  requested_source_authority?: string | null;
  execution_reference?: string | null;
  approved_by?: number | string | null;
  approved_at?: string | null;
  revision_version: number;
  allowed_actions: string[];
  created_at?: string;
  updated_at?: string;
};

export type PortfolioReviewActionDraft = {
  subject_type: string;
  subject_id: string | number | null;
  subject_key?: string | null;
  action_type: string;
  rationale: string;
  priority: string;
  owner?: string | null;
  owner_user_id?: number | null;
  due_date: string | null;
  requested_source_authority?: string | null;
};

export type PortfolioReviewHistoryEvent = {
  id?: number;
  event_type: string;
  occurred_at?: string;
  actor_name?: string | null;
  from_status?: string | null;
  to_status?: string | null;
  detail?: Record<string, unknown>;
};

export type PortfolioReviewComparison = {
  current_review_id: number;
  previous_review_id: number;
  current_review_number?: string;
  previous_review_number?: string;
  deltas: Record<string, unknown>;
  membership_changes?: Array<Record<string, unknown>>;
  allocation_changes?: Array<Record<string, unknown>>;
  gate_changes?: Array<Record<string, unknown>>;
  action_changes?: Array<Record<string, unknown>>;
  warnings: string[];
};

export type PortfolioReviewTrendPoint = {
  review_id?: number;
  review_number?: string;
  review_date: string;
  allocation_variance?: string | number | Record<string, unknown> | null;
  unclassified_exposure?: string | number | Record<string, unknown> | null;
  portfolio_count?: number | null;
  portfolio_value_by_currency?: Record<string, string | number>;
  blocked_project_count?: number | null;
  resource_overload_count?: number | null;
  open_action_count?: number | null;
  fid_count?: number | null;
  [key: string]: unknown;
};

export type PortfolioReviewTrends = {
  items: PortfolioReviewTrendPoint[];
  warnings: string[];
  generated_at?: string;
};

export type PortfolioReviewConfiguration = {
  id: number;
  code?: string;
  name: string;
  description: string;
  status: string;
  revision: number;
  version: number;
  content_json: Record<string, unknown>;
  content_hash?: string;
  scope_workspace_id?: number | null;
};

export type PortfolioReviewConfigurationPreview = {
  persisted: false;
  effective_configuration?: Record<string, unknown>;
  source?: Record<string, unknown>;
  readiness?: PortfolioReviewReadiness;
  warnings?: string[];
  [key: string]: unknown;
};

export type PortfolioReviewOptions = {
  review_types: Array<{ code: string; label?: string }>;
  conclusion_types: Array<{ code: string; label?: string }>;
  action_types: Array<{ code: string; label?: string; authority?: string }>;
  agenda_template: Array<Record<string, unknown>>;
  portfolios: Array<{ id: number; code: string; name: string }>;
  allocation_plans: Array<{ id: number; code: string; name?: string; portfolio_workspace_id?: number | null }>;
  users: Array<{ id: number; name?: string; email?: string }>;
  effective_configuration: Record<string, unknown>;
};
