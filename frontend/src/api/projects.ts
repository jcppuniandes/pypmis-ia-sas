import { apiFetch } from "./client";
import type {
  ActivitySheet,
  ActivitySheetRow,
  ActivitySheetWbsRow,
  Project,
  ProjectControlPlan,
  ProjectOperationalSetup,
  ProjectTeamMember,
  RoleProfile,
  ScheduleImport,
} from "../types";

export type ProjectOperationalSetupInput = Omit<
  ProjectOperationalSetup,
  "id" | "project_id" | "readiness_status" | "readiness_notes" | "version" | "created_at" | "updated_at"
> & {
  expected_version?: number;
};

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

  operationalSetup: (token: string, projectId: number) =>
    apiFetch<ProjectOperationalSetup>(`/api/v1/projects/${projectId}/operational-setup`, { token }),

  updateOperationalSetup: (token: string, projectId: number, data: ProjectOperationalSetupInput) =>
    apiFetch<ProjectOperationalSetup>(`/api/v1/projects/${projectId}/operational-setup`, {
      method: "PUT",
      token,
      body: JSON.stringify(data),
    }),

  activitySheets: (token: string, projectId: number) =>
    apiFetch<ActivitySheet[]>(`/api/v1/projects/${projectId}/activity-sheets`, { token }),

  activitySheetRows: (token: string, projectId: number, activitySheetId: number) =>
    apiFetch<ActivitySheetRow[]>(`/api/v1/projects/${projectId}/activity-sheets/${activitySheetId}/rows`, { token }),

  activitySheetWbsRows: (token: string, projectId: number, activitySheetId: number) =>
    apiFetch<ActivitySheetWbsRow[]>(`/api/v1/projects/${projectId}/activity-sheets/${activitySheetId}/wbs-sheet`, {
      token,
    }),

  loadActivitySheetData: (token: string, projectId: number, file: File) => {
    const body = new FormData();
    body.append("file", file);
    return apiFetch<ActivitySheet>(`/api/v1/projects/${projectId}/activity-sheets/get-data`, {
      method: "POST",
      token,
      body,
    });
  },

  controlPlan: (token: string, projectId: number) =>
    apiFetch<ProjectControlPlan>(`/api/v1/projects/${projectId}/control-plan`, { token }),

  team: (token: string, projectId: number) =>
    apiFetch<ProjectTeamMember[]>(`/api/v1/projects/${projectId}/team`, { token }),

  assignTeamMember: (token: string, projectId: number, data: { user_id: number; role: string }) =>
    apiFetch<ProjectTeamMember>(`/api/v1/projects/${projectId}/team`, {
      method: "POST",
      token,
      body: JSON.stringify(data),
    }),

  roleProfiles: (token: string) =>
    apiFetch<RoleProfile[]>("/api/v1/projects/role-profiles", { token }),
};
