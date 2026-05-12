import { apiFetch } from "./client";
import type { Project, ProjectControlPlan, ProjectTeamMember, RoleProfile, ScheduleImport } from "../types";

export const projects = {
  list: (token: string) =>
    apiFetch<Project[]>("/api/v1/projects", { token }),

  get: (token: string, id: number) =>
    apiFetch<Project>(`/api/v1/projects/${id}`, { token }),

  create: (token: string, data: Omit<Project, "id">) =>
    apiFetch<Project>("/api/v1/projects", {
      method: "POST",
      token,
      body: JSON.stringify(data),
    }),

  uploadSchedule: (token: string, projectId: number, file: File) => {
    const body = new FormData();
    body.append("file", file);
    return apiFetch<ScheduleImport>(`/api/v1/projects/${projectId}/schedule-imports`, {
      method: "POST",
      token,
      body,
    });
  },

  controlPlan: (token: string, projectId: number) =>
    apiFetch<ProjectControlPlan>(`/api/v1/projects/${projectId}/control-plan`, { token }),

  team: (token: string, projectId: number) =>
    apiFetch<ProjectTeamMember[]>(`/api/v1/projects/${projectId}/team`, { token }),

  roleProfiles: (token: string) =>
    apiFetch<RoleProfile[]>("/api/v1/projects/role-profiles", { token }),
};
