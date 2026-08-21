export type PlanningReadiness = {
  status: "READY" | "BLOCKED";
  can_enter: boolean;
  required_source_data: string[];
  available_source_data: string[];
  blocking_issues: string[];
  warnings: string[];
  project_type?: string | null;
  suggested_definition_framework?: string | null;
};

export type PortfolioMembership = {
  id: number;
  tenant_id: number;
  portfolio_workspace_id: number;
  portfolio_name: string;
  project_workspace_id: number;
  project_name: string;
  membership_source: string;
  source_strategic_gate_decision_id: number | null;
  source_project_proposal_id: number | null;
  is_target_portfolio: boolean;
  status: string;
  effective_from: string;
  effective_to: string | null;
  revision_version: number;
};

export type ProjectCreationRequestSummary = {
  id: number;
  request_number: string;
  state: string;
  revision_version: number;
  parent_workspace_id: number;
  project_template_config_id: number;
  project_manager_user_id: number;
  project_name: string;
  project_type: string | null;
  materialized_workspace_id: number | null;
  materialized_project_number: string | null;
};

export type StrategicPlanningEntry = {
  status: "READY_FOR_PORTFOLIO_PLANNING" | "GATE07D_REWORK_REQUIRED";
  can_enter_portfolio_evaluation: boolean;
  can_enter_project_definition: boolean;
  decision: Record<string, unknown>;
  proposal: Record<string, unknown>;
  source_idea: Record<string, unknown>;
  target_portfolio: Record<string, unknown> | null;
  project_creation_request: ProjectCreationRequestSummary | null;
  project_workspace: Record<string, unknown> | null;
  portfolio_memberships: PortfolioMembership[];
  planning_entry_snapshot: Record<string, unknown>;
  planning_entry_hash: string | null;
  portfolio_evaluation_readiness: PlanningReadiness;
  project_definition_readiness: PlanningReadiness;
  allowed_actions: string[];
  blocking_issues: string[];
  warnings: string[];
};

export type StrategicPlanningPreview = {
  decision: Record<string, unknown>;
  proposal: Record<string, unknown>;
  source_idea: Record<string, unknown>;
  target_portfolio: Record<string, unknown> | null;
  project_name: string;
  project_number_preview: string;
  record_code_preview: string | null;
  allowed_project_parents: Array<Record<string, unknown>>;
  default_project_parent: Record<string, unknown> | null;
  strategic_objectives: Array<Record<string, unknown>>;
  suggested_project_type: string | null;
  suggested_template: Record<string, unknown> | null;
  template_options: Array<Record<string, unknown>>;
  project_manager_required: boolean;
  project_manager_candidate: Record<string, unknown> | null;
  project_manager_options: Array<Record<string, unknown>>;
  mapped_fields: Record<string, unknown>;
  portfolio_planning_entry_preview: Record<string, unknown>;
  portfolio_evaluation_readiness_preview: PlanningReadiness;
  project_definition_readiness_preview: PlanningReadiness;
  creation_policy: Record<string, unknown>;
  source_decision_hash: string;
  source_readiness_hash: string;
  configuration: Record<string, unknown>;
  blocking_issues: string[];
  warnings: string[];
  persisted: false;
};

export type PlanningOption = {
  id: number;
  decision_number: string;
  project_proposal_id: number;
  project_name: string;
  target_portfolio_workspace_id: number | null;
  project_creation_request_id: number | null;
  project_creation_request_state: string | null;
  can_create: boolean;
};

export type PortfolioProject = {
  project_workspace_id: number;
  project_number: string;
  project_name: string;
  workspace_status: string;
  planning_stage: string;
  membership: PortfolioMembership;
  strategic_gate_decision_id: number | null;
  decision_number: string | null;
  project_proposal_id: number | null;
  proposal_number: string | null;
  source_idea_id: number | null;
  proposal_score: string | null;
  strategic_objectives: Array<Record<string, unknown>>;
  rom_cost: string | null;
  target_start: string | null;
  target_finish: string | null;
  expected_benefits: string;
  risk_summary: Array<Record<string, unknown>>;
  sponsor_user_id: number | null;
  project_manager_user_id: number | null;
  portfolio_evaluation_readiness: PlanningReadiness;
  project_definition_readiness: PlanningReadiness;
};

export type PlanningCreatePayload = {
  strategic_gate_decision_id: number;
  project_parent_workspace_id: number;
  project_template_config_id: number;
  project_manager_user_id: number;
  project_type: string;
  project_phase?: string | null;
  priority?: string | null;
  country?: string | null;
  region?: string | null;
  expected_decision_hash: string;
  expected_readiness_hash: string;
};
