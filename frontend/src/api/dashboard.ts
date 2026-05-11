import { apiFetch } from "./client";
import type { Dashboard, PilotReadiness } from "../types";

export const dashboard = {
  get: (token: string, projectId: number) =>
    apiFetch<Dashboard>(`/api/v1/projects/${projectId}/dashboard`, { token }),

  pilotReadiness: (token: string, projectId: number) =>
    apiFetch<PilotReadiness>(`/api/v1/projects/${projectId}/pilot-readiness`, { token }),
};
