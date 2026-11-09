import { apiFetch } from "../../api/client";
import { scheduleCommandOptions } from "../schedule-foundation/api";
import type { ForecastOverview, ForecastRow, ForecastSurface } from "./types";

export { parameters } from "../progress-foundation/api";
export const forecastProjectRoot = (workspaceId: number, surface: ForecastSurface = "forecast") =>
  `/api/v1/${surface}/projects/${workspaceId}`;
export const forecastApi = {
  overview: (token: string, workspaceId: number) =>
    apiFetch<ForecastOverview>(`${forecastProjectRoot(workspaceId)}/overview`, { token }),
  query: (token: string, workspaceId: number, path: string, surface: ForecastSurface = "forecast") =>
    apiFetch<ForecastRow>(`${forecastProjectRoot(workspaceId, surface)}${path}`, { token }),
  command: (
    token: string,
    workspaceId: number,
    path: string,
    payload: unknown,
    key: string,
    version?: number,
    method = "POST",
    surface: ForecastSurface = "forecast"
  ) =>
    apiFetch<ForecastRow>(
      `${forecastProjectRoot(workspaceId, surface)}${path}`,
      scheduleCommandOptions(token, key, payload, version, method)
    ),
};
