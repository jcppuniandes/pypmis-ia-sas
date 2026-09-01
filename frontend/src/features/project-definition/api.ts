import { apiFetch } from "../../api/client";
import type {
  DefinitionAction,
  DefinitionAssessment,
  DefinitionConfiguration,
  DefinitionOverview,
  FELStatus,
} from "./types";

const key = (prefix: string) => `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2)}`;

export const projectDefinitionApi = {
  overview: (token: string, projectId?: number) =>
    apiFetch<DefinitionOverview>(`/api/v1/project-definition${projectId ? `?project_workspace_id=${projectId}` : ""}`, {
      token,
    }),
  startFEL: (token: string, projectId: number, stageCode = "FEL-1") =>
    apiFetch<FELStatus>(`/api/v1/projects/${projectId}/fel/start`, {
      method: "POST",
      token,
      body: JSON.stringify({ stage_code: stageCode, idempotency_key: key("fel-start") }),
    }),
  startAssessment: (token: string, projectId: number) =>
    apiFetch<DefinitionAssessment>(`/api/v1/projects/${projectId}/definition-assessments`, {
      method: "POST",
      token,
      body: JSON.stringify({ idempotency_key: key("definition-assessment") }),
    }),
  updateAssessment: (
    token: string,
    assessment: DefinitionAssessment,
    elements: DefinitionAssessment["element_results"]
  ) =>
    apiFetch<DefinitionAssessment>(`/api/v1/project-definition-assessments/${assessment.id}`, {
      method: "PUT",
      token,
      headers: { "If-Match": `"${assessment.revision_version}"` },
      body: JSON.stringify({ status: "IN_PROGRESS", element_results: elements, evidence_refs: [] }),
    }),
  completeAssessment: (token: string, assessment: DefinitionAssessment) =>
    apiFetch<DefinitionAssessment>(`/api/v1/project-definition-assessments/${assessment.id}/complete`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${assessment.revision_version}"` },
      body: JSON.stringify({ idempotency_key: key("assessment-complete") }),
    }),
  reevaluate: (token: string, assessmentId: number) =>
    apiFetch<DefinitionAssessment>(`/api/v1/project-definition-assessments/${assessmentId}/reevaluate`, {
      method: "POST",
      token,
      body: JSON.stringify({ idempotency_key: key("assessment-reevaluate") }),
    }),
  createAction: (token: string, projectId: number, assessmentId: number, elementKey: string) =>
    apiFetch<DefinitionAction>(`/api/v1/projects/${projectId}/definition-actions`, {
      method: "POST",
      token,
      body: JSON.stringify({
        assessment_id: assessmentId,
        element_key: elementKey,
        title: `Close definition gap: ${elementKey}`,
        description: "Controlled Project Definition action; no operational execution control.",
        blocking: true,
        evidence_refs: [],
        idempotency_key: key("definition-action"),
      }),
    }),
  updateAction: (token: string, action: DefinitionAction, status: string) =>
    apiFetch<DefinitionAction>(`/api/v1/project-definition-actions/${action.id}`, {
      method: "PUT",
      token,
      headers: { "If-Match": `"${action.revision_version}"` },
      body: JSON.stringify({ status }),
    }),
  stageTransition: (
    token: string,
    projectId: number,
    status: FELStatus,
    action: "submit-review" | "complete" | "return"
  ) =>
    apiFetch<FELStatus>(`/api/v1/projects/${projectId}/fel-stage/${action}`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${status.revision_version}"` },
      body: JSON.stringify({ idempotency_key: key(`fel-stage-${action}`), note: "Governed FEL stage review." }),
    }),
  refreshPreview: (token: string, projectId: number) =>
    apiFetch<Record<string, unknown>>(`/api/v1/projects/${projectId}/definition/refresh/preview`, {
      method: "POST",
      token,
    }),
  investmentEvidence: (token: string, projectId: number) =>
    apiFetch<Record<string, unknown>>(`/api/v1/projects/${projectId}/definition/investment-gate-evidence`, { token }),
  configurations: (token: string) =>
    apiFetch<DefinitionConfiguration[]>("/api/v1/project-definition/admin/configurations", { token }),
  previewConfiguration: (token: string, item: DefinitionConfiguration, content: Record<string, unknown>) =>
    apiFetch<Record<string, unknown>>("/api/v1/project-definition/admin/configurations/preview", {
      method: "POST",
      token,
      body: JSON.stringify({
        governance_model: "CAPITAL_OWNER",
        current_FEL_stage: "FEL-2",
        configuration_id: item.id,
        content_json: content,
      }),
    }),
  cloneConfiguration: (token: string, item: DefinitionConfiguration) =>
    apiFetch<DefinitionConfiguration>(`/api/v1/project-definition/admin/configurations/${item.id}/clone`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${item.version}"` },
    }),
  updateConfiguration: (token: string, item: DefinitionConfiguration, content: Record<string, unknown>) =>
    apiFetch<DefinitionConfiguration>(`/api/v1/project-definition/admin/configurations/${item.id}`, {
      method: "PUT",
      token,
      headers: { "If-Match": `"${item.version}"` },
      body: JSON.stringify({ name: item.name, description: item.description, content_json: content }),
    }),
  publishConfiguration: (token: string, item: DefinitionConfiguration) =>
    apiFetch<DefinitionConfiguration>(`/api/v1/project-definition/admin/configurations/${item.id}/publish`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${item.version}"` },
    }),
};
