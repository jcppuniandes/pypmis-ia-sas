import { apiFetch } from "../../api/client";
import type { Idea, IdeaDraft, IdeaOptions } from "./types";

const root = "/api/v1/ideas";
const versionHeaders = (version: number) => ({ "If-Match": `"${version}"` });

export const ideaDemandApi = {
  options: (token: string, workspaceId?: number) =>
    apiFetch<IdeaOptions>(`${root}/options${workspaceId ? `?owning_workspace_id=${workspaceId}` : ""}`, { token }),
  list: (token: string, query = "") => apiFetch<Idea[]>(`${root}${query ? `?${query}` : ""}`, { token }),
  create: (token: string, payload: IdeaDraft) =>
    apiFetch<Idea>(root, { method: "POST", token, body: JSON.stringify(payload) }),
  update: (token: string, idea: Idea, payload: IdeaDraft) =>
    apiFetch<Idea>(`${root}/${idea.id}`, {
      method: "PUT",
      token,
      headers: versionHeaders(idea.revision_version),
      body: JSON.stringify(payload),
    }),
  action: (token: string, idea: Idea, action: string, body?: unknown) =>
    apiFetch<Idea>(`${root}/${idea.id}/${action}`, {
      method: "POST",
      token,
      headers: versionHeaders(idea.revision_version),
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  configurations: (token: string) =>
    apiFetch<Array<Record<string, unknown>>>(`${root}/admin/configurations/list`, { token }),
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
      body: JSON.stringify({ name: item.name, description: item.description || "", content_json: content }),
    }),
  publishConfiguration: (token: string, item: Record<string, unknown>) =>
    apiFetch<Record<string, unknown>>(`${root}/admin/configurations/${String(item.id)}/publish`, {
      method: "POST",
      token,
      headers: versionHeaders(Number(item.version)),
    }),
};
