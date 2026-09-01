export type DecisionOutcome = "GO" | "HOLD" | "RECYCLE" | "KILL";

export type DecisionReadiness = {
  investment_decision_id: number;
  readiness_status: "READY" | "BLOCKED" | "STALE";
  source_current: boolean;
  package_frozen: boolean;
  exact_scope: boolean;
  checklist_complete: boolean;
  authority_valid: boolean;
  quorum_met: boolean;
  voting_rule_met: boolean;
  segregation_of_duties_valid: boolean;
  blockers: string[];
  warnings: string[];
  final_output: string;
};

export type DecisionVote = {
  id: number;
  voter_user_id: number;
  vote: DecisionOutcome | "ABSTAIN";
  rationale: string;
  cast_at: string;
  revision_version: number;
};

export type InvestmentDecision = {
  id: number;
  decision_number: string;
  investment_gate_preparation_id: number;
  portfolio_workspace_id: number;
  profile_code: "PYP-INV-SELECT" | "PYP-FFA";
  decision_round: number;
  decision_scope_hash: string;
  status: "DRAFT" | "SUBMITTED" | "IN_REVIEW" | "READY_FOR_DECISION" | "DECIDED" | "VOIDED";
  outcome: DecisionOutcome | null;
  title: string;
  executive_summary: string;
  rationale: string;
  conditions: Array<Record<string, unknown>>;
  hold_reason: string | null;
  recycle_target: string | null;
  source_preparation_hash: string;
  source_package_hash: string;
  source_profile_hash: string;
  source_policy_hash: string | null;
  decision_package_snapshot: Record<string, unknown>;
  configuration_hash: string;
  configuration_snapshot: Record<string, unknown>;
  authority_model: "SINGLE_DECISION_MAKER" | "COMMITTEE";
  authority: Record<string, unknown>;
  committee: Record<string, unknown>;
  quorum: Record<string, unknown>;
  voting_rule: Record<string, unknown>;
  checklist: Array<Record<string, unknown>>;
  authorized_amount: string | null;
  authorized_currency: string | null;
  authorization_valid_until: string | null;
  decision_maker_user_id: number | null;
  decided_at: string | null;
  decided_by: number | null;
  is_fid: boolean;
  full_funds_authorized: boolean;
  investment_authorized: boolean;
  can_activate_project: false;
  decision_hash: string | null;
  revision_version: number;
  votes: DecisionVote[];
  readiness: DecisionReadiness;
  allowed_actions: string[];
  authorization_output: Record<string, unknown>;
};

export type FrozenPreparation = {
  id: number;
  preparation_number: string;
  name: string;
  profile_code: string;
  status: string;
  readiness_status: string;
  preparation_hash: string | null;
};

export type InvestmentDecisionConfiguration = {
  id: number;
  name: string;
  description: string;
  status: string;
  revision: number;
  version: number;
  content_json: Record<string, unknown>;
  content_hash: string;
};
