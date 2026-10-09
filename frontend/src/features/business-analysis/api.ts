import { apiFetch, apiFetchWithResponse } from "../../api/client";
import type {
  BusinessAnalysis,
  BusinessAnalysisContent,
  BusinessAnalysisOptions,
  BusinessAnalysisReadiness,
} from "./types";

const root = "/api/v1/business-analyses";
const versionHeaders = (version: number) => ({ "If-Match": `"${version}"` });

export type BusinessAnalysisPage = {
  items: BusinessAnalysis[];
  nextCursor: string | null;
};

export const businessAnalysisApi = {
  options: (token: string) => apiFetch<BusinessAnalysisOptions>(`${root}/options`, { token }),
  list: (token: string, query = "") => apiFetch<BusinessAnalysis[]>(`${root}${query ? `?${query}` : ""}`, { token }),
  listPage: async (token: string, query = ""): Promise<BusinessAnalysisPage> => {
    const result = await apiFetchWithResponse<BusinessAnalysis[]>(`${root}${query ? `?${query}` : ""}`, { token });
    return {
      items: result.data,
      nextCursor: result.response.headers?.get("X-Next-Cursor") ?? null,
    };
  },
  create: (token: string, sourceIdeaId: number) =>
    apiFetch<BusinessAnalysis>(root, {
      method: "POST",
      token,
      headers: { "Idempotency-Key": crypto.randomUUID() },
      body: JSON.stringify({ source_idea_id: sourceIdeaId }),
    }),
  update: (token: string, analysis: BusinessAnalysis, content: BusinessAnalysisContent) =>
    apiFetch<BusinessAnalysis>(`${root}/${analysis.id}`, {
      method: "PUT",
      token,
      headers: versionHeaders(analysis.revision_version),
      body: JSON.stringify(content),
    }),
  action: (token: string, analysis: BusinessAnalysis, action: string, body?: unknown) =>
    apiFetch<BusinessAnalysis>(`${root}/${analysis.id}/${action}`, {
      method: "POST",
      token,
      headers: versionHeaders(analysis.revision_version),
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  newRevision: (token: string, analysis: BusinessAnalysis) =>
    apiFetch<BusinessAnalysis>(`${root}/${analysis.id}/new-revision`, {
      method: "POST",
      token,
      headers: { "Idempotency-Key": crypto.randomUUID() },
    }),
  readiness: (token: string, analysisId: number) =>
    apiFetch<BusinessAnalysisReadiness>(`${root}/${analysisId}/readiness`, { token }),
  history: (token: string, analysisId: number) =>
    apiFetch<Array<Record<string, unknown>>>(`${root}/${analysisId}/history`, { token }),
  configurations: (token: string) =>
    apiFetch<Array<Record<string, unknown>>>(`${root}/admin/configurations`, { token }),
  previewConfiguration: (token: string, owningWorkspaceId: number) =>
    apiFetch<Record<string, unknown>>(`${root}/admin/configuration/preview`, {
      method: "POST",
      token,
      body: JSON.stringify({ owning_workspace_id: owningWorkspaceId }),
    }),
  cloneConfiguration: (token: string, item: Record<string, unknown>) =>
    apiFetch<Record<string, unknown>>(`${root}/admin/configurations/${String(item.id)}/clone`, {
      method: "POST",
      token,
      headers: versionHeaders(Number(item.version)),
    }),
  updateConfiguration: (token: string, item: Record<string, unknown>, content: Record<string, unknown>) =>
    apiFetch<Record<string, unknown>>(`${root}/admin/configurations/${String(item.id)}`, {
      method: "PUT",
      token,
      headers: versionHeaders(Number(item.version)),
      body: JSON.stringify({
        name: item.name,
        description: item.description || "",
        content_json: content,
      }),
    }),
  publishConfiguration: (token: string, item: Record<string, unknown>) =>
    apiFetch<Record<string, unknown>>(`${root}/admin/configurations/${String(item.id)}/publish`, {
      method: "POST",
      token,
      headers: versionHeaders(Number(item.version)),
    }),
};
