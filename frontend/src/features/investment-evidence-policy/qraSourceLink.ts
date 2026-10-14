import { strategicRouteForView } from "../enterprise-strategy/navigation/strategicNavigationBlueprint";

/** An evidence source link identifies one governed Project/run pair, never a latest run. */
export function qraEvidenceSourceHref(source: Record<string, unknown>): string | undefined {
  const projectId = Number(source.project_id || source.project_workspace_id);
  const runId = Number(source.run_id || source.qra_run_id || source.id);
  if (!Number.isSafeInteger(projectId) || projectId <= 0 || !Number.isSafeInteger(runId) || runId <= 0)
    return undefined;
  const route = strategicRouteForView("qra-run-overview", "user");
  return route ? `${route}?project_id=${projectId}&run_id=${runId}` : undefined;
}
