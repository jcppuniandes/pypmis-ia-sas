import { apiFetch } from "../../api/client";
import { scheduleCommandOptions } from "../schedule-foundation/api";
import type { ProgressOverview, ProgressRow } from "./types";

export const progressRoot = "/api/v1/progress";
export const progressProjectRoot = (workspaceId: number) => `${progressRoot}/projects/${workspaceId}`;
export const progressApi = {
  overview: async (token: string, workspaceId: number): Promise<ProgressOverview> => {
    const root = progressProjectRoot(workspaceId);
    const [overview, bundles, history] = await Promise.all([
      apiFetch<ProgressOverview>(`${root}/overview`, { token }),
      apiFetch<{ items: NonNullable<ProgressOverview["baseline_bundles"]> }>(`${root}/baseline-bundles`, { token }),
      apiFetch<{ items: NonNullable<ProgressOverview["history"]> }>(`${root}/history`, { token }),
    ]);
    return { ...overview, baseline_bundles: bundles.items, history: history.items };
  },
  query: (token: string, workspaceId: number, path: string) =>
    apiFetch<ProgressRow>(`${progressProjectRoot(workspaceId)}${path}`, { token }),
  command: (
    token: string,
    workspaceId: number,
    path: string,
    payload: unknown,
    key: string,
    version?: number,
    method = "POST"
  ) =>
    apiFetch<ProgressRow>(
      `${progressProjectRoot(workspaceId)}${path}`,
      scheduleCommandOptions(token, key, payload, version, method)
    ),
};
export function parameters(values: Record<string, string | number | null | undefined>): string {
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(values))
    if (value !== null && value !== undefined && value !== "") query.set(key, String(value));
  return query.toString();
}
