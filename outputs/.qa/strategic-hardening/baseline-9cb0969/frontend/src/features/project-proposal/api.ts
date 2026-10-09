import { apiFetch } from "../../api/client";
import type { GateReadiness, ProjectProposal, ProposalDraft, ProposalOptions, ProposalPreview } from "./types";

const root = "/api/v1/project-proposals";
const versionHeaders = (version: number) => ({ "If-Match": `"${version}"` });

export const projectProposalApi = {
  options: (token: string) => apiFetch<ProposalOptions>(`${root}/options`, { token }),
  list: (token: string, query = "") => apiFetch<ProjectProposal[]>(`${root}${query ? `?${query}` : ""}`, { token }),
  get: (token: string, id: number) => apiFetch<ProjectProposal>(`${root}/${id}`, { token }),
  preview: (token: string, sourceIdeaId: number) =>
    apiFetch<ProposalPreview>(`${root}/preview`, {
      method: "POST",
      token,
      body: JSON.stringify({ source_idea_id: sourceIdeaId }),
    }),
  previewFromIdea: (token: string, sourceIdeaId: number) =>
    apiFetch<ProposalPreview>(`/api/v1/ideas/${sourceIdeaId}/project-proposals/preview`, {
      method: "POST",
      token,
    }),
  create: (token: string, sourceIdeaId: number) =>
    apiFetch<ProjectProposal>(root, {
      method: "POST",
      token,
      body: JSON.stringify({ source_idea_id: sourceIdeaId }),
    }),
  update: (token: string, proposal: ProjectProposal, payload: ProposalDraft) =>
    apiFetch<ProjectProposal>(`${root}/${proposal.id}`, {
      method: "PUT",
      token,
      headers: versionHeaders(proposal.revision_version),
      body: JSON.stringify(payload),
    }),
  action: (token: string, proposal: ProjectProposal, action: string, body?: unknown) =>
    apiFetch<ProjectProposal>(`${root}/${proposal.id}/${action}`, {
      method: "POST",
      token,
      headers: versionHeaders(proposal.revision_version),
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
  readiness: (token: string, id: number) => apiFetch<GateReadiness>(`${root}/${id}/gate-readiness`, { token }),
  history: (token: string, id: number) => apiFetch<Array<Record<string, unknown>>>(`${root}/${id}/history`, { token }),
  relatedToIdea: (token: string, ideaId: number) =>
    apiFetch<ProjectProposal[]>(`/api/v1/ideas/${ideaId}/project-proposals`, { token }),
  configurations: (token: string) =>
    apiFetch<Array<Record<string, unknown>>>(`${root}/admin/configurations/list`, { token }),
  previewConfiguration: (token: string, sourceIdeaId: number) =>
    apiFetch<Record<string, unknown>>(`${root}/admin/configuration/preview`, {
      method: "POST",
      token,
      body: JSON.stringify({ source_idea_id: sourceIdeaId }),
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
