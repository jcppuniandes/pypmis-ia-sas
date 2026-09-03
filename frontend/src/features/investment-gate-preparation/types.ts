export type InvestmentGateEvidence = {
  id: number;
  preparation_id: number;
  requirement_key: string;
  evidence_type: string;
  classification: "A" | "B" | "C" | null;
  blocking: boolean;
  provider_key: string | null;
  coverage_requirement: number | null;
  scope_type: string;
  scope_id: number | null;
  evidence_origin: "GOVERNED_SOURCE" | "MANUAL_REFERENCE";
  status: string;
  source_record_id: string | null;
  scope_reference_hash: string | null;
  evidence_date: string | null;
  valid_until: string | null;
  issuer: string | null;
  owner: string | null;
  summary: string;
  evidence_refs: Array<Record<string, unknown>>;
  validation_note: string | null;
  warnings: string[];
  blockers: string[];
  source_current: boolean | null;
  source_readiness_status: string | null;
  resolution_status: string;
  revision_version: number;
};

export type InvestmentGateReadiness = {
  preparation_id: number;
  status: string;
  readiness_status: "READY" | "BLOCKED" | "STALE";
  source_current: boolean;
  required_requirement_count: number;
  valid_requirement_count: number;
  required_project_count: number;
  valid_project_count: number;
  blocked_project_count: number;
  coverage_percent: number;
  category_summary: Record<string, Record<string, unknown>>;
  evidence_coverage: Record<string, Record<string, unknown>>;
  warnings: string[];
  blockers: string[];
  investment_gate_preparation_ready: boolean;
  can_enter_investment_decision: boolean;
  can_enter_fid: false;
  final_output: string;
};

export type InvestmentGatePreparation = {
  id: number;
  portfolio_workspace_id: number;
  preparation_number: string;
  revision: number;
  name: string;
  description: string;
  investment_gate_profile_id: number;
  profile_code: string;
  profile_revision: number;
  profile_hash: string;
  status: "DRAFT" | "IN_PREPARATION" | "READY_FOR_REVIEW" | "FROZEN" | "SUPERSEDED" | "VOIDED";
  readiness_status: "READY" | "BLOCKED" | "STALE";
  source_snapshot: Record<string, unknown>;
  evidence_summary: Record<string, Record<string, unknown>>;
  conditions: Array<Record<string, unknown>>;
  warnings: string[];
  blockers: string[];
  preparation_source_hash: string;
  preparation_hash: string | null;
  revision_version: number;
  evidence: InvestmentGateEvidence[];
  readiness: InvestmentGateReadiness;
  allowed_actions: string[];
};

export type InvestmentGateOverview = {
  portfolio_workspace_id: number;
  governance_eligible: boolean;
  source_contract: Record<string, unknown> | null;
  profiles: Array<Record<string, unknown>>;
  preparations: InvestmentGatePreparation[];
  boundaries: string[];
};

export type ProjectReadiness = {
  preparation_id: number;
  required_project_count: number;
  valid_project_count: number;
  blocked_project_count: number;
  coverage_percent: number;
  projects: Array<Record<string, unknown>>;
};

export type InvestmentGateConfiguration = {
  id: number;
  name: string;
  description: string;
  status: string;
  revision: number;
  version: number;
  content_json: Record<string, unknown>;
  content_hash: string;
};
