import { apiFetch } from "../../api/client";
import type {
  EvidencePolicyConfiguration,
  EvidencePolicyContent,
  EvidencePolicyOverview,
  EvidencePolicyPreview,
} from "./types";

export const investmentEvidencePolicyApi = {
  overview: (token: string) =>
    apiFetch<EvidencePolicyOverview>("/api/v1/investment-evidence-policy/overview", { token }),
  preview: (
    token: string,
    configuration: EvidencePolicyConfiguration,
    portfolioId: number | null,
    gateProfileCode: string,
    content: EvidencePolicyContent,
    projectTypeCode?: string,
    governanceModel?: string
  ) =>
    apiFetch<EvidencePolicyPreview>(`/api/v1/investment-evidence-policy/configurations/${configuration.id}/preview`, {
      method: "POST",
      token,
      body: JSON.stringify({
        portfolio_workspace_id: portfolioId,
        gate_profile_code: gateProfileCode,
        project_workspace_ids: [],
        configuration_id: configuration.id,
        content_json: content,
        project_type_code: projectTypeCode || null,
        governance_model: governanceModel || null,
      }),
    }),
  clone: (token: string, configuration: EvidencePolicyConfiguration) =>
    apiFetch<EvidencePolicyConfiguration>(
      `/api/v1/investment-evidence-policy/configurations/${configuration.id}/clone`,
      { method: "POST", token, headers: { "If-Match": `"${configuration.version}"` } }
    ),
  cloneGate07jEvid2: (token: string, configuration: EvidencePolicyConfiguration) =>
    apiFetch<EvidencePolicyConfiguration>(
      `/api/v1/investment-evidence-policy/configurations/${configuration.id}/clone-gate07j-evid2`,
      { method: "POST", token, headers: { "If-Match": `"${configuration.version}"` } }
    ),
  save: (token: string, configuration: EvidencePolicyConfiguration, content: EvidencePolicyContent) =>
    apiFetch<EvidencePolicyConfiguration>(`/api/v1/investment-evidence-policy/configurations/${configuration.id}`, {
      method: "PUT",
      token,
      headers: { "If-Match": `"${configuration.version}"` },
      body: JSON.stringify({
        name: configuration.name,
        description: configuration.description,
        content_json: content,
      }),
    }),
  publish: (token: string, configuration: EvidencePolicyConfiguration) =>
    apiFetch<EvidencePolicyConfiguration>(
      `/api/v1/investment-evidence-policy/configurations/${configuration.id}/publish`,
      { method: "POST", token, headers: { "If-Match": `"${configuration.version}"` } }
    ),
};
