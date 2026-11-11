import { apiFetch } from "../../api/client";
import { scheduleCommandOptions } from "../schedule-foundation/api";

export type EngineeringRow = Record<string, unknown>;
export type EngineeringCommand = (
  path: string,
  payload: EngineeringRow,
  version?: number,
  method?: "POST" | "PUT" | "PATCH" | "DELETE"
) => Promise<EngineeringRow | null>;

export const engineeringProjectRoot = (workspaceId: number) => `/api/v1/engineering/projects/${workspaceId}`;
export const engineeringAdminRoot = "/api/v1/engineering/admin/profiles";

export function engineeringQuery(path: string, fields: Record<string, string | number | undefined>) {
  const params = new URLSearchParams();
  Object.entries(fields).forEach(([key, value]) => {
    if (value !== undefined && value !== "") params.set(key, String(value));
  });
  const suffix = params.toString();
  return suffix ? `${path}?${suffix}` : path;
}

export function engineeringRead(token: string, base: string, path: string, signal?: AbortSignal) {
  return apiFetch<EngineeringRow>(`${base}${path}`, { token, signal });
}

export function engineeringWrite(
  token: string,
  base: string,
  path: string,
  payload: EngineeringRow,
  key: string,
  version?: number,
  method = "POST"
) {
  return apiFetch<EngineeringRow>(`${base}${path}`, scheduleCommandOptions(token, key, payload, version, method));
}

export const isEngineeringRow = (value: unknown): value is EngineeringRow =>
  Boolean(value && typeof value === "object" && !Array.isArray(value));

export const rows = (value: unknown): EngineeringRow[] => (Array.isArray(value) ? value.filter(isEngineeringRow) : []);

export const items = (value: unknown): EngineeringRow[] => (isEngineeringRow(value) ? rows(value.items) : rows(value));

export const text = (value: unknown) => (typeof value === "string" || typeof value === "number" ? String(value) : "");
export const recordId = (row: EngineeringRow | null | undefined, key = "id") => text(row?.[key]);
export const labelOf = (row: EngineeringRow) =>
  [text(row.code ?? row.deliverable_code ?? row.revision_code ?? row.external_id), text(row.title ?? row.name)]
    .filter(Boolean)
    .join(" · ") || `#${recordId(row)}`;
export const versionOf = (row: EngineeringRow | null | undefined) =>
  Number.isSafeInteger(row?.version) && Number(row?.version) > 0 ? Number(row?.version) : undefined;
export const optionalId = (value: string) =>
  /^\d+$/.test(value) && Number.isSafeInteger(Number(value)) && Number(value) > 0 ? Number(value) : null;

export function permission(actions: unknown, action: string) {
  return (
    Array.isArray(actions) && actions.some((candidate) => candidate === action || candidate === `engineering.${action}`)
  );
}
