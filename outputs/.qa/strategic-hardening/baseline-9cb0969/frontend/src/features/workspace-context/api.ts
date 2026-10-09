import { apiFetch } from "../../api/client";
import type { MyWorkspace, RecentWorkspace, WorkspaceContext, WorkspaceHome } from "./types";

const root = "/api/v1/workspaces";

export type MyWorkspaceFilters = Partial<
  Record<"workspace_type" | "status" | "responsible" | "parent" | "business_number" | "name", string>
>;

function filteredPath(filters: MyWorkspaceFilters = {}) {
  const query = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value?.trim()) query.set(key, value.trim());
  });
  const suffix = query.toString();
  return suffix ? `${root}?${suffix}` : root;
}

export const workspaceContextApi = {
  list: (token: string, filters: MyWorkspaceFilters = {}) => apiFetch<MyWorkspace[]>(filteredPath(filters), { token }),
  recent: (token: string) => apiFetch<RecentWorkspace[]>(`${root}/recent`, { token }),
  context: (token: string, workspaceId: number) =>
    apiFetch<WorkspaceContext>(`${root}/${workspaceId}/context`, { token }),
  open: (token: string, workspaceId: number, route = "") =>
    apiFetch<WorkspaceContext>(`${root}/${workspaceId}/open`, {
      method: "POST",
      token,
      body: JSON.stringify({ route }),
    }),
  home: (token: string, workspaceId: number) => apiFetch<WorkspaceHome>(`${root}/${workspaceId}/home`, { token }),
  updateLastRoute: (token: string, workspaceId: number, route: string) =>
    apiFetch<RecentWorkspace>(`${root}/${workspaceId}/last-route`, {
      method: "PUT",
      token,
      body: JSON.stringify({ route }),
    }),
};
