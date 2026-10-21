import { apiFetch, apiFetchFile } from "../../api/client";
import type { ModelObject, ScopeOverview, ScopeProfile } from "./types";

/** Presentation-only aliases of immutable server snapshots, never new authority. */
export function normalizeScopeOverview(data: ScopeOverview): ScopeOverview {
  const current = Math.max(0, ...data.baselines.map((row) => row.revision));
  return {
    ...data,
    baselines: data.baselines.map((row) => ({
      ...row,
      revision_id: row.scope_revision_id ?? row.revision_id,
      is_original: !row.original_baseline_id,
      is_current: row.revision === current,
      status: "APPROVED",
    })),
    plan_items: data.plan_items.map((row) => ({ ...row, revision: row.revision ?? 1 })),
    derived_models: data.derived_models.map((row) => ({
      ...row,
      status: "IMMUTABLE",
      split_rule: row.snapshot_json?.split_rule ?? row.split_rule,
      plan_item_ids: row.snapshot_json?.memberships?.map((item) => item.plan_item_id) ?? row.plan_item_ids ?? [],
      model_object_ids: row.snapshot_json?.objects?.map((item) => item.object_id) ?? row.model_object_ids ?? [],
    })),
  };
}

export const scopeRoot = "/api/v1/scope";
export function projectRoot(workspaceId: number) {
  return `${scopeRoot}/projects/${workspaceId}`;
}
export function scopeCommandOptions(token: string, key: string, payload: unknown, version?: number, method = "POST") {
  return {
    token,
    method,
    headers: { "Idempotency-Key": key, ...(version === undefined ? {} : { "If-Match": `"${version}"` }) },
    body: JSON.stringify(payload),
  };
}
export const scopeApi = {
  overview: (token: string, workspaceId: number) =>
    apiFetch<ScopeOverview>(`${projectRoot(workspaceId)}/overview`, { token }).then(normalizeScopeOverview),
  command: (
    token: string,
    workspaceId: number,
    path: string,
    payload: unknown,
    key: string,
    version?: number,
    method = "POST"
  ) =>
    apiFetch<unknown>(`${projectRoot(workspaceId)}${path}`, scopeCommandOptions(token, key, payload, version, method)),
  upload: (
    token: string,
    workspaceId: number,
    kind: "models" | "excel-imports",
    file: File,
    reason: string,
    key: string,
    modelCode: string,
    fieldMapping: string
  ) => {
    const body = new FormData();
    body.append("file", file);
    body.append("reason", reason);
    if (kind === "models") body.append("model_code", modelCode);
    else body.append("field_mapping", fieldMapping);
    return apiFetch<unknown>(`${projectRoot(workspaceId)}/${kind}`, {
      token,
      method: "POST",
      headers: { "Idempotency-Key": key },
      body,
    });
  },
  objects: (token: string, workspaceId: number, modelId: number) =>
    apiFetch<{ items: ModelObject[]; total: number }>(`${projectRoot(workspaceId)}/models/${modelId}/objects`, {
      token,
    }),
  source: (token: string, workspaceId: number, modelId: number) =>
    apiFetchFile(`${projectRoot(workspaceId)}/models/${modelId}/source`, { token }),
  profiles: (token: string) =>
    apiFetch<{ items: ScopeProfile[]; default_content: Record<string, unknown>; allowed_actions: string[] }>(
      `${scopeRoot}/admin/profiles`,
      { token }
    ),
  profileCommand: (token: string, path: string, payload: unknown, key: string, version?: number, method = "POST") =>
    apiFetch<ScopeProfile>(
      `${scopeRoot}/admin/profiles${path}`,
      scopeCommandOptions(token, key, payload, version, method)
    ),
};
