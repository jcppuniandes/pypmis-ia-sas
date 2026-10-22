import { apiFetch, apiFetchFile } from "../../api/client";
import type { JsonRecord, ScheduleObject, ScheduleOverview, ScheduleProfile } from "./types";

export const scheduleRoot = "/api/v1/schedule";
export const scheduleProjectRoot = (workspaceId: number) => `${scheduleRoot}/projects/${workspaceId}`;
export function scheduleCommandOptions(
  token: string,
  key: string,
  payload: unknown,
  version?: number,
  method = "POST"
) {
  return {
    token,
    method,
    headers: { "Idempotency-Key": key, ...(version === undefined ? {} : { "If-Match": `"${version}"` }) },
    body: JSON.stringify(payload),
  };
}
export const scheduleApi = {
  overview: (token: string, workspaceId: number) =>
    apiFetch<ScheduleOverview>(`${scheduleProjectRoot(workspaceId)}/overview`, { token }),
  activities: async (token: string, workspaceId: number, versionId: number) => {
    const result = await apiFetch<{ items: ScheduleObject[] }>(
      `${scheduleProjectRoot(workspaceId)}/versions/${versionId}/activities`,
      { token }
    );
    return result.items;
  },
  health: (token: string, workspaceId: number, versionId: number) =>
    apiFetch<JsonRecord>(`${scheduleProjectRoot(workspaceId)}/versions/${versionId}/health`, { token }),
  command: (
    token: string,
    workspaceId: number,
    path: string,
    payload: unknown,
    key: string,
    version?: number,
    method = "POST"
  ) =>
    apiFetch<unknown>(
      `${scheduleProjectRoot(workspaceId)}${path}`,
      scheduleCommandOptions(token, key, payload, version, method)
    ),
  upload: (
    token: string,
    workspaceId: number,
    registerId: number,
    file: File,
    reason: string,
    kind: string,
    key: string,
    version: number,
    predecessorId?: number
  ) => {
    const body = new FormData();
    body.append("file", file);
    body.append("reason", reason);
    body.append("kind", kind);
    if (predecessorId) body.append("predecessor_version_id", String(predecessorId));
    return apiFetch<unknown>(`${scheduleProjectRoot(workspaceId)}/registers/${registerId}/imports`, {
      token,
      method: "POST",
      headers: { "Idempotency-Key": key, "If-Match": `"${version}"` },
      body,
    });
  },
  download: (token: string, workspaceId: number, exportId: number) =>
    apiFetchFile(`${scheduleProjectRoot(workspaceId)}/exports/${exportId}/download`, { token }),
  profiles: (token: string) =>
    apiFetch<{ items: ScheduleProfile[]; default_content: Record<string, unknown>; allowed_actions: string[] }>(
      `${scheduleRoot}/admin/profiles`,
      { token }
    ),
  profileCommand: (token: string, path: string, payload: unknown, key: string, version?: number, method = "POST") =>
    apiFetch<ScheduleProfile>(
      `${scheduleRoot}/admin/profiles${path}`,
      scheduleCommandOptions(token, key, payload, version, method)
    ),
};
