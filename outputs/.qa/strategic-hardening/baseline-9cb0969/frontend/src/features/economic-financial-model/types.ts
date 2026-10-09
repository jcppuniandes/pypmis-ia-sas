export type FinancialModelVersion = {
  id: number;
  model_id: number;
  version_number: number;
  version_label: string;
  purpose: string;
  status: string;
  model_type: string;
  base_currency: string;
  cash_flow_basis: string;
  periodicity: string;
  as_of_date: string;
  source_references_json: Record<string, unknown>;
  source_hashes_json: Record<string, string>;
  source_current: boolean;
  total_investment_requirement: string;
  total_model_financing: string;
  governed_funding_assigned: string;
  funding_gap: string;
  funding_reconciliation_status: string;
  project_financial_npv: string | null;
  project_irr: string | null;
  economic_npv: string | null;
  economic_irr: string | null;
  benefit_cost_ratio: string | null;
  simple_payback: string | null;
  equity_irr: string | null;
  moic: string | null;
  minimum_dscr: string | null;
  average_dscr: string | null;
  llcr: string | null;
  debt_to_equity: string | null;
  overall_readiness: string;
  warnings_json: string[];
  blockers_json: string[];
  model_hash: string;
  calculation_engine_version: string;
  revision_version: number;
};

export type FinancialModel = {
  id: number;
  model_number: string;
  project_workspace_id: number;
  business_case_id: number;
  owner_user_id: number;
  status: string;
  current_version_id: number | null;
  revision_version: number;
  current_version: FinancialModelVersion | null;
  final_output: string;
  next_process: string;
};

export type FinancialInput = Record<string, string | number | boolean | null | Record<string, unknown> | unknown[]> & {
  id: number;
};

export type FinancialReadiness = {
  status: string;
  dimensions: Record<string, string>;
  warnings: string[];
  blockers: string[];
  source_current: boolean;
  readiness_hash: string;
  final_output: string;
  persisted: boolean;
};

export type FinancialConfiguration = {
  id: number;
  name: string;
  description: string;
  status: string;
  revision: number;
  version: number;
  content_json: Record<string, unknown>;
  content_hash: string;
};
