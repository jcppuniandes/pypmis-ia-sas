export type ProjectSummary = {
  id: number;
  code: string;
  name: string;
  status: string;
  project_type?: string | null;
  governance_model: string;
};

export type FELStatus = {
  id: number;
  project_workspace_id: number;
  current_stage_code: string;
  status: string;
  effective_framework_id: number;
  effective_framework_revision: number;
  effective_framework_hash: string;
  current_assessment_id: number | null;
  latest_completed_assessment_id: number | null;
  readiness_status: string;
  definition_source_hash: string;
  revision_version: number;
  allowed_actions: string[];
};

export type ElementResult = {
  element_key: string;
  category_key: string;
  name?: string;
  applicable: boolean;
  score: number | null;
  maturity_status?: string | null;
  comment: string;
  evidence_refs: Array<Record<string, unknown>>;
  blocking: boolean;
  action_required: boolean;
};

export type DefinitionAssessment = {
  id: number;
  project_workspace_id: number;
  assessment_number: string;
  assessment_version: number;
  framework_code: string;
  framework_type: string;
  framework_version: string;
  fel_stage_code: string;
  assessment_date: string;
  status: string;
  raw_score: number | null;
  normalized_score: number | null;
  maturity_level: string | null;
  threshold_status: string;
  category_results: Array<Record<string, unknown>>;
  element_results: ElementResult[];
  blocking_items: Array<Record<string, unknown>>;
  warnings: string[];
  actions_summary: Record<string, number>;
  evidence_refs: Array<Record<string, unknown>>;
  source_snapshot: Record<string, unknown>;
  definition_source_hash: string;
  assessed_by: number;
  completed_by: number | null;
  assessment_hash: string | null;
  revision_version: number;
  allowed_actions: string[];
};

export type DefinitionAction = {
  id: number;
  project_workspace_id: number;
  assessment_id: number;
  element_key: string;
  title: string;
  description: string;
  status: string;
  blocking: boolean;
  evidence_refs: Array<Record<string, unknown>>;
  revision_version: number;
};

export type DefinitionReadiness = {
  status: "READY" | "BLOCKED" | "STALE" | "NOT_STARTED";
  project_workspace_id: number;
  current_FEL_stage: string | null;
  latest_completed_assessment_id: number | null;
  framework_code: string | null;
  framework_version: string | null;
  assessment_hash: string | null;
  maturity_level: string | null;
  threshold_status: string;
  required_maturity: string | null;
  required_stage: string | null;
  required_maturity_met: boolean;
  blocking_item_count: number;
  open_blocking_action_count: number;
  evidence_coverage: number;
  warnings: string[];
  blockers: string[];
  definition_readiness_hash: string;
  source_current: boolean;
  can_supply_investment_gate_evidence: boolean;
};

export type DefinitionOverview = {
  projects: ProjectSummary[];
  selected_project: ProjectSummary | null;
  fel_status: FELStatus | null;
  latest_assessment: DefinitionAssessment | null;
  readiness: DefinitionReadiness | null;
  actions: DefinitionAction[];
  history: DefinitionAssessment[];
  maturity_trend: Array<Record<string, unknown>>;
  framework: Record<string, unknown> | null;
  boundaries: Record<string, boolean>;
};

export type DefinitionConfiguration = {
  id: number;
  kind: string;
  code: string;
  name: string;
  description: string;
  status: string;
  revision: number;
  version: number;
  content_json: Record<string, unknown>;
  content_hash: string;
};
