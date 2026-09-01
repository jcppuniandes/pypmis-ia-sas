import { apiFetch } from "../../api/client";
import type { Fund, FundingAssignment, FundsConfiguration, FundsOverview, FundingSource } from "./types";

const key = (prefix: string) => `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;

export const fundsManagerApi = {
  overview: (token: string, portfolioId: number) =>
    apiFetch<FundsOverview>(`/api/v1/portfolios/${portfolioId}/funding`, { token }),
  createSource: (token: string, name: string, type: string, currency: string) =>
    apiFetch<FundingSource>("/api/v1/funding-sources", {
      method: "POST",
      token,
      body: JSON.stringify({
        source_name: name,
        source_type: type,
        currency,
        description: "Governed strategic capital funding origin.",
        restrictions: {},
        evidence_refs: [],
        idempotency_key: key("funding-source"),
      }),
    }),
  sourceAction: (token: string, source: FundingSource, action: "activate" | "suspend" | "close") =>
    apiFetch<FundingSource>(`/api/v1/funding-sources/${source.id}/${action}`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${source.revision_version}"` },
      body: JSON.stringify({ idempotency_key: key(`funding-source-${action}`) }),
    }),
  createFund: (token: string, sourceId: number | null, name: string, currency: string, amount: number) =>
    apiFetch<Fund>("/api/v1/funds", {
      method: "POST",
      token,
      body: JSON.stringify({
        fund_name: name,
        funding_source_id: sourceId,
        description: "Governed strategic funding envelope.",
        currency,
        authorized_amount: amount,
        period_granularity: "TOTAL",
        authorized_amount_by_period: [],
        restrictions: {},
        applicable_workspace_scope: {},
        evidence_refs: [],
        idempotency_key: key("fund"),
      }),
    }),
  fundAction: (token: string, fund: Fund, action: "authorize" | "activate" | "suspend" | "close") =>
    apiFetch<Fund>(`/api/v1/funds/${fund.id}/${action}`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${fund.revision_version}"` },
      body: JSON.stringify({ idempotency_key: key(`fund-${action}`) }),
    }),
  createAssignment: (token: string, fund: Fund, overview: FundsOverview, amount: number) =>
    apiFetch<FundingAssignment>("/api/v1/funding-assignments", {
      method: "POST",
      token,
      body: JSON.stringify({
        fund_id: fund.id,
        scope_type: "RECOMMENDED_PROJECT_SET",
        portfolio_workspace_id: overview.portfolio_workspace_id,
        recommended_project_set_hash: overview.readiness?.recommended_project_set_hash,
        source_convergence_id: overview.readiness?.source_convergence_id,
        source_recommendation_hash: overview.readiness?.source_recommendation_hash,
        amount,
        currency: fund.currency,
        period_profile: [],
        assignment_purpose: "Fund the current governed recommended Project Set.",
        conditions: [],
        evidence_refs: [],
        idempotency_key: key("funding-assignment"),
      }),
    }),
  assignmentAction: (
    token: string,
    assignment: FundingAssignment,
    action: "reserve" | "confirm" | "release" | "cancel"
  ) =>
    apiFetch<FundingAssignment>(`/api/v1/funding-assignments/${assignment.id}/${action}`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${assignment.revision_version}"` },
      body: JSON.stringify({ idempotency_key: key(`funding-assignment-${action}`) }),
    }),
  refreshPreview: (token: string, portfolioId: number) =>
    apiFetch<Record<string, unknown>>(`/api/v1/portfolios/${portfolioId}/funding/readiness/refresh/preview`, {
      method: "POST",
      token,
    }),
  refresh: (token: string, portfolioId: number, sourceHash: string) =>
    apiFetch(`/api/v1/portfolios/${portfolioId}/funding/readiness/refresh`, {
      method: "POST",
      token,
      body: JSON.stringify({ expected_source_hash: sourceHash, idempotency_key: key("funding-readiness") }),
    }),
  evidence: (token: string, portfolioId: number) =>
    apiFetch<Record<string, unknown>>(`/api/v1/portfolios/${portfolioId}/funding/investment-gate-evidence`, {
      token,
    }),
  configurations: (token: string) => apiFetch<FundsConfiguration[]>("/api/v1/funds/admin/configurations", { token }),
  previewConfiguration: (
    token: string,
    portfolioId: number | null,
    configurationId: number,
    content: Record<string, unknown>
  ) =>
    apiFetch<Record<string, unknown>>("/api/v1/funds/admin/configurations/preview", {
      method: "POST",
      token,
      body: JSON.stringify({
        portfolio_workspace_id: portfolioId,
        configuration_id: configurationId,
        content_json: content,
        fund_assumptions: [],
      }),
    }),
  cloneConfiguration: (token: string, item: FundsConfiguration) =>
    apiFetch<FundsConfiguration>(`/api/v1/funds/admin/configurations/${item.id}/clone`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${item.version}"` },
    }),
  updateConfiguration: (token: string, item: FundsConfiguration, content: Record<string, unknown>) =>
    apiFetch<FundsConfiguration>(`/api/v1/funds/admin/configurations/${item.id}`, {
      method: "PUT",
      token,
      headers: { "If-Match": `"${item.version}"` },
      body: JSON.stringify({ name: item.name, description: item.description, content_json: content }),
    }),
  publishConfiguration: (token: string, item: FundsConfiguration) =>
    apiFetch<FundsConfiguration>(`/api/v1/funds/admin/configurations/${item.id}/publish`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${item.version}"` },
    }),
};
