import { apiFetch, apiFetchFile } from "./client";
import type {
  ActivitySheetRecostRun,
  ActivitySheetRecostResult,
  BusinessProcessInstance,
  BusinessProcessLineItem,
  BusinessProcessLineItemRevision,
  BusinessProcessPolicy,
  CloseoutReport,
  CommitmentFundingLine,
  ControlAccount,
  ControlAgentRun,
  CostBreakdownStructure,
  CostCode,
  ForecastFundingReport,
  ForensicDossierAnalysis,
  ForensicRagSource,
  ForensicWindowAnalysis,
  FundingSource,
  IntegratedControlMatrixRow,
  RateSheet,
  ReconciliationReport,
  ScheduleOfValueLine,
  WorkPackageConstraint,
  WbsNode,
} from "../types";

export type FbsCreatePayload = {
  code: string;
  name?: string;
  source_of_funds: string;
  funding_type: string;
  authorization_ref: string;
  usage_restrictions?: string;
  usage_rules?: string;
  approved_amount: number;
  currency: string;
  status: string;
};

export type CbsCreatePayload = {
  parent_id?: number | null;
  code: string;
  level?: number;
  cost_category: string;
  description?: string;
  status?: string;
};

export type WbsCreatePayload = {
  parent_id?: number | null;
  code: string;
  name: string;
  level?: number;
  description?: string;
  dictionary?: string;
  responsible?: string;
  status?: string;
};

export type BusinessProcessLineInput = {
  wbs_id?: number | null;
  cbs_id: number;
  funding_source_id?: number | null;
  control_account_id?: number | null;
  amount: number;
  quantity?: number;
  description?: string;
};

export type BusinessProcessPayload = {
  title: string;
  line_items: BusinessProcessLineInput[];
};

export type BusinessProcessPolicyPayload = {
  process_code: string;
  action: string;
  required_role?: string;
  permission_key?: string;
  status?: string;
};

export type BusinessProcessLineItemUpdatePayload = {
  amount?: number;
  quantity?: number;
  description?: string;
  status?: string;
  change_note?: string;
  expected_version?: number;
};

export type SovLinePayload = {
  line_no: string;
  description?: string;
  amount: number;
  cbs_id?: number | null;
  wbs_id?: number | null;
  control_account_id?: number | null;
  status?: string;
};

export type CommitmentFundingPayload = {
  contract_id: number;
  sov_line_id?: number | null;
  funding_source_id: number;
  amount: number;
  consumed_amount?: number;
  status?: string;
};

export type RateSheetPayload = {
  code: string;
  name?: string;
  status?: string;
  line_items: Array<{ cbs_code: string; unit_rate?: number; multiplier?: number; status?: string }>;
};

export type WorkPackageConstraintPayload = {
  constraint_type: string;
  description: string;
  owner_role?: string;
  required_by?: string | null;
  status?: string;
  priority?: string;
  evidence_ref?: string;
  closure_note?: string;
  exception_ref?: string;
  blocking?: boolean;
};

export const integratedControl = {
  matrix: (token: string, projectId: number) =>
    apiFetch<IntegratedControlMatrixRow[]>(`/api/v1/projects/${projectId}/integrated-control-matrix`, { token }),

  wbs: (token: string, projectId: number) => apiFetch<WbsNode[]>(`/api/v1/projects/${projectId}/wbs`, { token }),

  createWbs: (token: string, projectId: number, data: WbsCreatePayload) =>
    apiFetch<WbsNode>(`/api/v1/projects/${projectId}/wbs`, {
      method: "POST",
      token,
      body: JSON.stringify(data),
    }),

  controlAccounts: (token: string, projectId: number) =>
    apiFetch<ControlAccount[]>(`/api/v1/projects/${projectId}/control-accounts`, { token }),

  cbs: (token: string, projectId: number) =>
    apiFetch<CostBreakdownStructure[]>(`/api/v1/projects/${projectId}/cbs`, { token }),

  costCodes: (token: string, projectId: number) =>
    apiFetch<CostCode[]>(`/api/v1/projects/${projectId}/cost-codes`, { token }),

  forecastVsFunding: (token: string, projectId: number) =>
    apiFetch<ForecastFundingReport>(`/api/v1/projects/${projectId}/forecast-vs-funding-report`, { token }),

  closeoutReport: (token: string, projectId: number) =>
    apiFetch<CloseoutReport>(`/api/v1/projects/${projectId}/closeout-report`, { token }),

  createFbs: (token: string, projectId: number, data: FbsCreatePayload) =>
    apiFetch<FundingSource>(`/api/v1/projects/${projectId}/fbs`, {
      method: "POST",
      token,
      body: JSON.stringify(data),
    }),

  createCbs: (token: string, projectId: number, data: CbsCreatePayload) =>
    apiFetch<CostBreakdownStructure>(`/api/v1/projects/${projectId}/cbs`, {
      method: "POST",
      token,
      body: JSON.stringify(data),
    }),

  createCbsFundBusinessProcess: (token: string, projectId: number, data: BusinessProcessPayload) =>
    apiFetch<BusinessProcessInstance>(`/api/v1/projects/${projectId}/business-processes/cbs-fund`, {
      method: "POST",
      token,
      body: JSON.stringify(data),
    }),

  createCbsWbsBusinessProcess: (token: string, projectId: number, data: BusinessProcessPayload) =>
    apiFetch<BusinessProcessInstance>(`/api/v1/projects/${projectId}/business-processes/cbs-wbs`, {
      method: "POST",
      token,
      body: JSON.stringify(data),
    }),

  businessProcessPolicies: (token: string, projectId: number) =>
    apiFetch<BusinessProcessPolicy[]>(`/api/v1/projects/${projectId}/business-process-policies`, { token }),

  upsertBusinessProcessPolicy: (token: string, projectId: number, data: BusinessProcessPolicyPayload) =>
    apiFetch<BusinessProcessPolicy>(`/api/v1/projects/${projectId}/business-process-policies`, {
      method: "POST",
      token,
      body: JSON.stringify(data),
    }),

  businessProcessLineItems: (token: string, projectId: number, processId: number) =>
    apiFetch<BusinessProcessLineItem[]>(`/api/v1/projects/${projectId}/business-processes/${processId}/line-items`, {
      token,
    }),

  updateBusinessProcessLineItem: (
    token: string,
    projectId: number,
    lineItemId: number,
    data: BusinessProcessLineItemUpdatePayload
  ) =>
    apiFetch<BusinessProcessLineItem>(`/api/v1/projects/${projectId}/business-process-line-items/${lineItemId}`, {
      method: "PATCH",
      token,
      body: JSON.stringify(data),
    }),

  businessProcessLineItemRevisions: (token: string, projectId: number, lineItemId: number) =>
    apiFetch<BusinessProcessLineItemRevision[]>(
      `/api/v1/projects/${projectId}/business-process-line-items/${lineItemId}/revisions`,
      { token }
    ),

  createSovLine: (token: string, projectId: number, contractId: number, data: SovLinePayload) =>
    apiFetch<ScheduleOfValueLine>(`/api/v1/projects/${projectId}/contracts/${contractId}/sov-lines`, {
      method: "POST",
      token,
      body: JSON.stringify(data),
    }),

  createCommitmentFundingLine: (token: string, projectId: number, data: CommitmentFundingPayload) =>
    apiFetch<CommitmentFundingLine>(`/api/v1/projects/${projectId}/commitment-funding-lines`, {
      method: "POST",
      token,
      body: JSON.stringify(data),
    }),

  rateSheets: (token: string, projectId: number) =>
    apiFetch<RateSheet[]>(`/api/v1/projects/${projectId}/rate-sheets`, { token }),

  createRateSheet: (token: string, projectId: number, data: RateSheetPayload) =>
    apiFetch<RateSheet>(`/api/v1/projects/${projectId}/rate-sheets`, {
      method: "POST",
      token,
      body: JSON.stringify(data),
    }),

  recostActivitySheet: (token: string, projectId: number, activitySheetId: number, rateSheetId: number) =>
    apiFetch<ActivitySheetRecostResult>(`/api/v1/projects/${projectId}/activity-sheets/${activitySheetId}/recost`, {
      method: "POST",
      token,
      body: JSON.stringify({ rate_sheet_id: rateSheetId }),
    }),

  recostRuns: (token: string, projectId: number, activitySheetId: number) =>
    apiFetch<ActivitySheetRecostRun[]>(`/api/v1/projects/${projectId}/activity-sheets/${activitySheetId}/recost-runs`, {
      token,
    }),

  reconciliationReport: (token: string, projectId: number) =>
    apiFetch<ReconciliationReport>(`/api/v1/projects/${projectId}/reconciliation-report`, { token }),

  exportReconciliationReport: (token: string, projectId: number, format: "xlsx" | "pdf") =>
    apiFetchFile(`/api/v1/projects/${projectId}/reconciliation-report/export?format=${format}`, { token }),

  controlAuditAgentRuns: (token: string, projectId: number) =>
    apiFetch<ControlAgentRun[]>(`/api/v1/projects/${projectId}/agents/control-audit/runs`, { token }),

  runControlAuditAgent: (token: string, projectId: number) =>
    apiFetch<ControlAgentRun>(`/api/v1/projects/${projectId}/agents/control-audit/run`, {
      method: "POST",
      token,
    }),

  createAwpDraftPackages: (token: string, projectId: number) =>
    apiFetch<ControlAgentRun>(`/api/v1/projects/${projectId}/agents/control-audit/awp-draft-packages`, {
      method: "POST",
      token,
    }),

  runClaimsForensicDossier: (token: string, projectId: number, mode: string, files: File[]) => {
    const formData = new FormData();
    formData.append("mode", mode);
    files.forEach((file) => formData.append("files", file));
    return apiFetch<ForensicDossierAnalysis>(`/api/v1/projects/${projectId}/claims/forensic-runs`, {
      method: "POST",
      token,
      body: formData,
    });
  },

  windowAnalysis37RagSources: (token: string, projectId: number) =>
    apiFetch<ForensicRagSource[]>(`/api/v1/projects/${projectId}/claims/window-analysis-37/rag-sources`, { token }),

  runWindowAnalysis37: (token: string, projectId: number, nearCriticalThresholdDays: number, files: File[]) => {
    const formData = new FormData();
    formData.append("near_critical_threshold_days", String(nearCriticalThresholdDays));
    files.forEach((file) => formData.append("files", file));
    return apiFetch<ForensicWindowAnalysis>(`/api/v1/projects/${projectId}/claims/window-analysis-37`, {
      method: "POST",
      token,
      body: formData,
    });
  },

  createWorkPackageConstraint: (
    token: string,
    projectId: number,
    packageId: number,
    data: WorkPackageConstraintPayload
  ) =>
    apiFetch<WorkPackageConstraint>(`/api/v1/projects/${projectId}/work-packages/${packageId}/constraints`, {
      method: "POST",
      token,
      body: JSON.stringify(data),
    }),

  approveBaseline: (token: string, projectId: number) =>
    apiFetch<{ project_id: number; project_status: string }>(`/api/v1/projects/${projectId}/baseline-approval`, {
      method: "POST",
      token,
    }),
};
