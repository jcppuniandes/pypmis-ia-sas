import { apiFetch } from "../../api/client";
import type { DecisionOutcome, FrozenPreparation, InvestmentDecision, InvestmentDecisionConfiguration } from "./types";

const key = (prefix: string) => `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;

export const investmentDecisionApi = {
  list: (token: string, queue = "") =>
    apiFetch<InvestmentDecision[]>(`/api/v1/investment-decisions${queue ? `?queue=${queue}` : ""}`, { token }),
  preparations: (token: string) => apiFetch<FrozenPreparation[]>("/api/v1/investment-gate-preparations", { token }),
  create: (token: string, preparationId: number, title: string) =>
    apiFetch<InvestmentDecision>("/api/v1/investment-decisions", {
      method: "POST",
      token,
      body: JSON.stringify({
        investment_gate_preparation_id: preparationId,
        title,
        executive_summary: "Formal decision over the frozen Gate 07J package.",
        idempotency_key: key("investment-decision-create"),
      }),
    }),
  assignMaker: (token: string, item: InvestmentDecision, userId: number) =>
    apiFetch<InvestmentDecision>(`/api/v1/investment-decisions/${item.id}`, {
      method: "PUT",
      token,
      headers: { "If-Match": `"${item.revision_version}"` },
      body: JSON.stringify({ decision_maker_user_id: userId }),
    }),
  transition: (token: string, item: InvestmentDecision, action: "submit" | "start-review" | "void") =>
    apiFetch<InvestmentDecision>(`/api/v1/investment-decisions/${item.id}/${action}`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${item.revision_version}"` },
      body: JSON.stringify({ idempotency_key: key(`investment-decision-${action}`) }),
    }),
  ready: (token: string, item: InvestmentDecision) =>
    apiFetch<InvestmentDecision>(`/api/v1/investment-decisions/${item.id}/ready`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${item.revision_version}"` },
      body: JSON.stringify({
        idempotency_key: key("investment-decision-ready"),
        checklist: item.checklist.map((check) => ({ code: check.code, acknowledged: true, note: "Reviewed" })),
      }),
    }),
  decide: (
    token: string,
    item: InvestmentDecision,
    outcome: DecisionOutcome,
    values: { amount?: number; currency?: string; holdReason?: string; recycleTarget?: string } = {}
  ) =>
    apiFetch<InvestmentDecision>(`/api/v1/investment-decisions/${item.id}/decide`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${item.revision_version}"` },
      body: JSON.stringify({
        outcome,
        rationale: `Formal governed ${outcome} decision.`,
        conditions: [],
        hold_reason: values.holdReason,
        recycle_target: values.recycleTarget,
        authorized_amount: values.amount,
        authorized_currency: values.currency,
        idempotency_key: key("investment-decision-decide"),
      }),
    }),
  vote: (token: string, item: InvestmentDecision, vote: DecisionOutcome | "ABSTAIN") =>
    apiFetch<InvestmentDecision>(`/api/v1/investment-decisions/${item.id}/votes`, {
      method: "POST",
      token,
      body: JSON.stringify({ vote, rationale: "Formal committee vote.", idempotency_key: key("decision-vote") }),
    }),
  history: (token: string, decisionId: number) =>
    apiFetch<Array<Record<string, unknown>>>(`/api/v1/investment-decisions/${decisionId}/history`, { token }),
  configurations: (token: string) =>
    apiFetch<InvestmentDecisionConfiguration[]>("/api/v1/investment-decision/admin/configurations", { token }),
  previewConfiguration: (token: string, configurationId: number, content: Record<string, unknown>) =>
    apiFetch<Record<string, unknown>>("/api/v1/investment-decision/admin/configurations/preview", {
      method: "POST",
      token,
      body: JSON.stringify({ configuration_id: configurationId, content_json: content }),
    }),
  cloneConfiguration: (token: string, item: InvestmentDecisionConfiguration) =>
    apiFetch<InvestmentDecisionConfiguration>(`/api/v1/investment-decision/admin/configurations/${item.id}/clone`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${item.version}"` },
    }),
  updateConfiguration: (token: string, item: InvestmentDecisionConfiguration, content: Record<string, unknown>) =>
    apiFetch<InvestmentDecisionConfiguration>(`/api/v1/investment-decision/admin/configurations/${item.id}`, {
      method: "PUT",
      token,
      headers: { "If-Match": `"${item.version}"` },
      body: JSON.stringify({ name: item.name, description: item.description, content_json: content }),
    }),
  publishConfiguration: (token: string, item: InvestmentDecisionConfiguration) =>
    apiFetch<InvestmentDecisionConfiguration>(`/api/v1/investment-decision/admin/configurations/${item.id}/publish`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${item.version}"` },
    }),
};
