import { apiFetch } from "../../api/client";
import { scheduleCommandOptions } from "../schedule-foundation/api";
import type { CostOverview, CostRow } from "./types";

export const costRoot = "/api/v1/cost";
export const costProjectRoot = (workspaceId: number) => `${costRoot}/projects/${workspaceId}`;
export const costApi = {
  overview: async (token: string, workspaceId: number): Promise<CostOverview> => {
    const root = costProjectRoot(workspaceId);
    const [overview, actuals, commitments, fx] = await Promise.all([
      apiFetch<CostOverview>(`${root}/overview`, { token }),
      apiFetch<{ items: CostOverview["actuals"] }>(`${root}/actuals`, { token }),
      apiFetch<{ items: CostOverview["commitment_references"] }>(`${root}/commitments/reconciliation`, { token }),
      apiFetch<{ items: NonNullable<CostOverview["fx_rates"]> }>(`${root}/fx-rates`, { token }),
    ]);
    return { ...overview, actuals: actuals.items, commitment_references: commitments.items, fx_rates: fx.items };
  },
  query: (token: string, workspaceId: number, path: string) =>
    apiFetch<CostRow>(`${costProjectRoot(workspaceId)}${path}`, { token }),
  command: (
    token: string,
    workspaceId: number,
    path: string,
    payload: unknown,
    key: string,
    version?: number,
    method = "POST"
  ) =>
    apiFetch<CostRow>(
      `${costProjectRoot(workspaceId)}${path}`,
      scheduleCommandOptions(token, key, payload, version, method)
    ),
};
