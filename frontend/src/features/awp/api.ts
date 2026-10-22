import { apiFetch } from "../../api/client";
import { scheduleCommandOptions } from "../schedule-foundation/api";
import type { ScheduleProfile } from "../schedule-foundation/types";
import type { AwpOverview, ProfileList } from "./types";

export const awpRoot = "/api/v1/awp";
export const awpProjectRoot = (workspaceId: number) => `${awpRoot}/projects/${workspaceId}`;
export const awpApi = {
  overview: (token: string, workspaceId: number) =>
    apiFetch<AwpOverview>(`${awpProjectRoot(workspaceId)}/overview`, { token }),
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
      `${awpProjectRoot(workspaceId)}${path}`,
      scheduleCommandOptions(token, key, payload, version, method)
    ),
};
export const governedProfilesApi = {
  list: (token: string, root: string) => apiFetch<ProfileList>(root, { token }),
  command: (
    token: string,
    root: string,
    path: string,
    payload: unknown,
    key: string,
    version?: number,
    method = "POST"
  ) => apiFetch<ScheduleProfile>(`${root}${path}`, scheduleCommandOptions(token, key, payload, version, method)),
};
