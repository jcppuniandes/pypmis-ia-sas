import { apiFetch } from "../../api/client";
import type { FourDComparison, FourDFilters, FourDView } from "./types";

export function fourDQuery(parameters: FourDFilters): string {
  const query = new URLSearchParams(Object.entries(parameters).filter(([, value]) => value !== ""));
  return query.toString();
}
const root = (workspaceId: number) => `/api/v1/schedule/projects/${workspaceId}/4d`;
export const fourDApi = {
  view: (token: string, workspaceId: number, parameters: FourDFilters) =>
    apiFetch<FourDView>(`${root(workspaceId)}?${fourDQuery(parameters)}`, { token }),
  traceability: (token: string, workspaceId: number, scopeId: number, parameters: FourDFilters) =>
    apiFetch<FourDView & { traceability?: unknown }>(
      `${root(workspaceId)}/traceability/${scopeId}?${fourDQuery(parameters)}`,
      { token }
    ),
  compare: (token: string, workspaceId: number, parameters: FourDFilters) =>
    apiFetch<FourDComparison>(`${root(workspaceId)}/compare?${fourDQuery(parameters)}`, { token }),
};
