import { apiFetch, apiFetchFile } from "./client";
import type {
  ActivitySheet,
  ActivitySheetRow,
  ActivitySheetWbsRow,
  BimGeometryMeasurementBatch,
  BimGeometryMeasurementBatchInput,
  BimQuantityRule,
  BimQuantityRuleUpdate,
  ColombiaApuCatalogItem,
  ColombiaApuCatalogSync,
  ControlledMeasurementApproval,
  GuidedFlow,
  ProcessFlowBoard,
  Project,
  ProjectControlPlan,
  ProjectOperationalSetup,
  ProjectTeamMember,
  QuantityApuSuggestion,
  QuantityApuSuggestionInput,
  QuantityApuApprovalInput,
  QuantityControlCodeAssignment,
  QuantityRuleRecalculation,
  QuantityTakeoffLine,
  QuantityTakeoffRun,
  RoleProfile,
  ScheduleActivityMap,
  ScheduleImport,
  ScheduleRelationship,
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

  deleteProject: (token: string, projectId: number) =>
    apiFetch<{ status: string; project_id: number }>(`/api/v1/projects/${projectId}`, {
      method: "DELETE",
      token,
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

  scheduleActivities: (token: string, projectId: number) =>
    apiFetch<ScheduleActivityMap[]>(`/api/v1/projects/${projectId}/schedule-activities`, { token }),

  scheduleRelationships: (token: string, projectId: number) =>
    apiFetch<ScheduleRelationship[]>(`/api/v1/projects/${projectId}/schedule-relationships`, { token }),

  guidedFlow: (token: string, projectId: number) =>
    apiFetch<GuidedFlow>(`/api/v1/projects/${projectId}/guided-flow`, { token }),

  processFlowBoard: (token: string, projectId: number) =>
    apiFetch<ProcessFlowBoard>(`/api/v1/projects/${projectId}/process-flow-board`, { token }),

  confirmScheduleCurrency: (token: string, projectId: number, scheduleImportId: number, currency: string) =>
    apiFetch<ScheduleImport>(`/api/v1/projects/${projectId}/schedule-imports/${scheduleImportId}/confirm-currency`, {
      method: "POST",
      token,
      body: JSON.stringify({ currency }),
    }),

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

  quantityTakeoffRuns: (token: string, projectId: number) =>
    apiFetch<QuantityTakeoffRun[]>(`/api/v1/projects/${projectId}/quantity-takeoff-runs`, { token }),

  quantityTakeoffLines: (token: string, projectId: number, runId: number) =>
    apiFetch<QuantityTakeoffLine[]>(`/api/v1/projects/${projectId}/quantity-takeoff-runs/${runId}/lines`, { token }),

  quantityTakeoffIfcModel: (token: string, projectId: number, runId: number) =>
    apiFetchFile(`/api/v1/projects/${projectId}/quantity-takeoff-runs/${runId}/ifc-file`, { token }),

  recalculateQuantityRules: (token: string, projectId: number, runId: number) =>
    apiFetch<QuantityRuleRecalculation>(`/api/v1/projects/${projectId}/quantity-takeoff-runs/${runId}/recalculate-rules`, {
      method: "POST",
      token,
    }),

  approveControlledMeasurements: (token: string, projectId: number, runId: number, data: ControlledMeasurementApproval) =>
    apiFetch<QuantityTakeoffLine[]>(`/api/v1/projects/${projectId}/quantity-takeoff-runs/${runId}/controlled-measurements`, {
      method: "POST",
      token,
      body: JSON.stringify(data),
    }),

  processGeometryMeasurements: (
    token: string,
    projectId: number,
    runId: number,
    data: BimGeometryMeasurementBatchInput,
  ) =>
    apiFetch<BimGeometryMeasurementBatch>(
      `/api/v1/projects/${projectId}/quantity-takeoff-runs/${runId}/geometry-measurements`,
      {
        method: "POST",
        token,
        body: JSON.stringify(data),
      },
    ),

  assignQuantityControlCodes: (token: string, projectId: number, runId: number, data: QuantityControlCodeAssignment) =>
    apiFetch<QuantityTakeoffLine[]>(`/api/v1/projects/${projectId}/quantity-takeoff-runs/${runId}/control-code-assignments`, {
      method: "POST",
      token,
      body: JSON.stringify(data),
    }),

  linkQuantityTakeoffBimModel: (
    token: string,
    projectId: number,
    runId: number,
    data: { model_id: number; expected_version?: number },
  ) =>
    apiFetch<QuantityTakeoffRun>(`/api/v1/projects/${projectId}/quantity-takeoff-runs/${runId}/bim-model`, {
      method: "PUT",
      token,
      body: JSON.stringify(data),
    }),

  syncColombiaApuCatalog: (token: string, projectId: number) =>
    apiFetch<ColombiaApuCatalogSync>(`/api/v1/projects/${projectId}/colombia-apu-catalog/sync`, {
      method: "POST",
      token,
    }),

  colombiaApuCatalog: (token: string, projectId: number, search = "", sourceKey = "") => {
    const params = new URLSearchParams();
    if (search) params.set("search", search);
    if (sourceKey) params.set("source_key", sourceKey);
    const query = params.toString();
    return apiFetch<ColombiaApuCatalogItem[]>(
      `/api/v1/projects/${projectId}/colombia-apu-catalog${query ? `?${query}` : ""}`,
      { token },
    );
  },

  suggestQuantityApuItems: (token: string, projectId: number, runId: number, data: QuantityApuSuggestionInput) =>
    apiFetch<QuantityApuSuggestion[]>(`/api/v1/projects/${projectId}/quantity-takeoff-runs/${runId}/apu-suggestions`, {
      method: "POST",
      token,
      body: JSON.stringify(data),
    }),

  approveQuantityApuItems: (token: string, projectId: number, runId: number, data: QuantityApuApprovalInput) =>
    apiFetch<QuantityTakeoffLine[]>(`/api/v1/projects/${projectId}/quantity-takeoff-runs/${runId}/apu-approvals`, {
      method: "POST",
      token,
      body: JSON.stringify(data),
    }),

  bimQuantityRules: (token: string, projectId: number) =>
    apiFetch<BimQuantityRule[]>(`/api/v1/projects/${projectId}/bim-quantity-rules`, { token }),

  updateBimQuantityRule: (token: string, projectId: number, ruleId: number, data: BimQuantityRuleUpdate) =>
    apiFetch<BimQuantityRule>(`/api/v1/projects/${projectId}/bim-quantity-rules/${ruleId}`, {
      method: "PUT",
      token,
      body: JSON.stringify(data),
    }),

  loadQuantityTakeoff: (token: string, projectId: number, file: File, bimModelId?: number) => {
    const body = new FormData();
    body.append("file", file);
    if (bimModelId) body.append("bim_model_id", String(bimModelId));
    return apiFetch<QuantityTakeoffRun>(`/api/v1/projects/${projectId}/quantity-takeoffs/import`, {
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

  removeTeamMember: (token: string, projectId: number, userId: number) =>
    apiFetch<{ status: string; project_id: number; user_id: number }>(`/api/v1/projects/${projectId}/team/${userId}`, {
      method: "DELETE",
      token,
    }),

  roleProfiles: (token: string) =>
    apiFetch<RoleProfile[]>("/api/v1/projects/role-profiles", { token }),
};
