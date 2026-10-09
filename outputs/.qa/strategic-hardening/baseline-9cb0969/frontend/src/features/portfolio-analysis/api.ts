import { apiFetch } from "../../api/client";
import type { AnalysisConfiguration, AnalysisFilters, PortfolioAnalysisOverview, ProjectAnalysisDetail } from "./types";

function query(filters: AnalysisFilters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value) params.set(key, value);
  });
  const encoded = params.toString();
  return encoded ? `?${encoded}` : "";
}

export const portfolioAnalysisApi = {
  overview: (token: string, portfolioId: number, filters: AnalysisFilters = {}) =>
    apiFetch<PortfolioAnalysisOverview>(`/api/v1/portfolios/${portfolioId}/analysis${query(filters)}`, { token }),
  projectDetail: (token: string, portfolioId: number, projectId: number) =>
    apiFetch<ProjectAnalysisDetail>(`/api/v1/portfolios/${portfolioId}/analysis/projects/${projectId}`, { token }),
  preview: (token: string, portfolioId: number, filters: AnalysisFilters, expectedAnalysisHash?: string) =>
    apiFetch<{ persisted: boolean; overview: PortfolioAnalysisOverview }>(
      `/api/v1/portfolios/${portfolioId}/analysis/preview`,
      {
        method: "POST",
        token,
        body: JSON.stringify({ filters, expected_analysis_hash: expectedAnalysisHash || null }),
      }
    ),
  configurations: (token: string) =>
    apiFetch<AnalysisConfiguration[]>("/api/v1/portfolio-analysis/admin/configurations", { token }),
  previewConfiguration: (
    token: string,
    portfolioWorkspaceId?: number,
    configurationId?: number,
    contentJson?: Record<string, unknown>
  ) =>
    apiFetch<Record<string, unknown>>("/api/v1/portfolio-analysis/admin/configurations/preview", {
      method: "POST",
      token,
      body: JSON.stringify({
        portfolio_workspace_id: portfolioWorkspaceId || null,
        configuration_id: configurationId || null,
        content_json: contentJson,
      }),
    }),
  cloneConfiguration: (token: string, item: AnalysisConfiguration) =>
    apiFetch<AnalysisConfiguration>(`/api/v1/portfolio-analysis/admin/configurations/${item.id}/clone`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${item.version}"` },
    }),
  updateConfiguration: (token: string, item: AnalysisConfiguration, content: Record<string, unknown>) =>
    apiFetch<AnalysisConfiguration>(`/api/v1/portfolio-analysis/admin/configurations/${item.id}`, {
      method: "PUT",
      token,
      headers: { "If-Match": `"${item.version}"` },
      body: JSON.stringify({ name: item.name, description: item.description, content_json: content }),
    }),
  publishConfiguration: (token: string, item: AnalysisConfiguration) =>
    apiFetch<AnalysisConfiguration>(`/api/v1/portfolio-analysis/admin/configurations/${item.id}/publish`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${item.version}"` },
    }),
};
