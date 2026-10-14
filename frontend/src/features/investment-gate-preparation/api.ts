import { apiFetch } from "../../api/client";
import type {
  InvestmentGateConfiguration,
  InvestmentGateOverview,
  InvestmentGatePreparation,
  ProjectReadiness,
} from "./types";

const key = (prefix: string) => `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;

export const investmentGatePreparationApi = {
  overview: (token: string, portfolioId: number) =>
    apiFetch<InvestmentGateOverview>(`/api/v1/portfolios/${portfolioId}/investment-gate-preparation`, { token }),
  create: (token: string, portfolioId: number, profileId: number, name: string) =>
    apiFetch<InvestmentGatePreparation>("/api/v1/investment-gate-preparations", {
      method: "POST",
      token,
      body: JSON.stringify({
        portfolio_workspace_id: portfolioId,
        investment_gate_profile_id: profileId,
        name,
        description: "Governed evidence package for a downstream investment decision.",
        idempotency_key: key("investment-gate-preparation"),
      }),
    }),
  addFelEvidence: (
    token: string,
    preparation: InvestmentGatePreparation,
    projectId: number,
    felStage: string,
    referenceId: string
  ) =>
    apiFetch<InvestmentGatePreparation>(`/api/v1/investment-gate-preparations/${preparation.id}/evidence`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${preparation.revision_version}"` },
      body: JSON.stringify({
        requirement_key: "fel-stage-readiness",
        scope_type: "EACH_PROJECT",
        scope_id: projectId,
        reference_id: referenceId,
        evidence_date: new Date().toISOString(),
        issuer: "Project Definition Office",
        owner: "Capital Projects Governance",
        summary: "Reference to a governed FEL or equivalent project-definition assessment.",
        evidence_refs: [{ fel_stage: felStage, assessment_id: referenceId, evidence_hash: "0".repeat(64) }],
        idempotency_key: key("fel-evidence"),
      }),
    }),
  validateEvidence: (token: string, preparation: InvestmentGatePreparation, evidenceId: number, valid = true) =>
    apiFetch<InvestmentGatePreparation>(`/api/v1/investment-gate-evidence/${evidenceId}/validate`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${preparation.revision_version}"` },
      body: JSON.stringify({
        decision: valid ? "VALID" : "INVALID",
        validation_note: valid
          ? "Independent evidence review confirms validity, scope and maturity."
          : "Independent evidence review rejected the reference.",
        idempotency_key: key("evidence-validation"),
      }),
    }),
  removeEvidence: (token: string, preparation: InvestmentGatePreparation, evidenceId: number) =>
    apiFetch<InvestmentGatePreparation>(`/api/v1/investment-gate-evidence/${evidenceId}`, {
      method: "DELETE",
      token,
      headers: { "If-Match": `"${preparation.revision_version}"` },
    }),
  projectReadiness: (token: string, preparationId: number) =>
    apiFetch<ProjectReadiness>(`/api/v1/investment-gate-preparations/${preparationId}/project-readiness`, { token }),
  refreshPreview: (token: string, preparationId: number) =>
    apiFetch<Record<string, unknown>>(`/api/v1/investment-gate-preparations/${preparationId}/refresh/preview`, {
      method: "POST",
      token,
    }),
  refresh: (token: string, preparation: InvestmentGatePreparation, sourceHash: string, idempotencyKey: string) =>
    apiFetch<InvestmentGatePreparation>(`/api/v1/investment-gate-preparations/${preparation.id}/refresh`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${preparation.revision_version}"` },
      body: JSON.stringify({ expected_source_hash: sourceHash, idempotency_key: idempotencyKey }),
    }),
  updateCondition: (token: string, preparation: InvestmentGatePreparation, conditionIndex: number, status: string) =>
    apiFetch<InvestmentGatePreparation>(
      `/api/v1/investment-gate-preparations/${preparation.id}/conditions/${conditionIndex}`,
      {
        method: "PUT",
        token,
        headers: { "If-Match": `"${preparation.revision_version}"` },
        body: JSON.stringify({ preparation_status: status }),
      }
    ),
  transition: (
    token: string,
    preparation: InvestmentGatePreparation,
    action: "ready-for-review" | "freeze" | "clone" | "void"
  ) =>
    apiFetch<InvestmentGatePreparation>(`/api/v1/investment-gate-preparations/${preparation.id}/${action}`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${preparation.revision_version}"` },
      body: JSON.stringify({ idempotency_key: key(`investment-gate-${action}`) }),
    }),
  handoff: (token: string, preparationId: number) =>
    apiFetch<Record<string, unknown>>(`/api/v1/investment-gate-preparations/${preparationId}/handoff`, { token }),
  configurations: (token: string) =>
    apiFetch<InvestmentGateConfiguration[]>("/api/v1/investment-gate-preparation/admin/configurations", { token }),
  previewConfiguration: (
    token: string,
    portfolioId: number | null,
    configurationId: number,
    content: Record<string, unknown>
  ) =>
    apiFetch<Record<string, unknown>>("/api/v1/investment-gate-preparation/admin/configurations/preview", {
      method: "POST",
      token,
      body: JSON.stringify({
        portfolio_workspace_id: portfolioId,
        configuration_id: configurationId,
        content_json: content,
      }),
    }),
  cloneConfiguration: (token: string, item: InvestmentGateConfiguration) =>
    apiFetch<InvestmentGateConfiguration>(`/api/v1/investment-gate-preparation/admin/configurations/${item.id}/clone`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${item.version}"` },
    }),
  updateConfiguration: (token: string, item: InvestmentGateConfiguration, content: Record<string, unknown>) =>
    apiFetch<InvestmentGateConfiguration>(`/api/v1/investment-gate-preparation/admin/configurations/${item.id}`, {
      method: "PUT",
      token,
      headers: { "If-Match": `"${item.version}"` },
      body: JSON.stringify({ name: item.name, description: item.description, content_json: content }),
    }),
  publishConfiguration: (token: string, item: InvestmentGateConfiguration) =>
    apiFetch<InvestmentGateConfiguration>(
      `/api/v1/investment-gate-preparation/admin/configurations/${item.id}/publish`,
      { method: "POST", token, headers: { "If-Match": `"${item.version}"` } }
    ),
};
