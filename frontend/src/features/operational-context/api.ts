import { apiFetch } from "../../api/client";
import type {
  BindingResult,
  OperationalPeriod,
  OperationalProfile,
  OperationalProjectContext,
  PeriodDraft,
} from "./types";

const root = "/api/v1/operational";

function normalizedProfile(profile: OperationalProfile): OperationalProfile {
  return { ...profile, status: profile.status.toUpperCase() as OperationalProfile["status"] };
}

function command(token: string, key: string, body: unknown, version?: number) {
  return {
    method: "POST",
    token,
    headers: {
      "Idempotency-Key": key,
      ...(version === undefined ? {} : { "If-Match": `"${version}"` }),
    },
    body: JSON.stringify(body),
  };
}

export const operationalApi = {
  context: (token: string, workspaceId: number) =>
    apiFetch<OperationalProjectContext>(`${root}/projects/${workspaceId}/context`, { token }),
  binding: (token: string, workspaceId: number) =>
    apiFetch<BindingResult>(`${root}/projects/${workspaceId}/binding`, { token }),
  reconcile: (
    token: string,
    workspaceId: number,
    payload: { legacy_project_id: number | null; reason: string; source: string; expected_binding_version: number },
    key: string
  ) =>
    apiFetch<BindingResult>(
      `${root}/projects/${workspaceId}/binding/reconcile`,
      command(token, key, payload, payload.expected_binding_version)
    ),
  periods: (token: string, workspaceId: number) =>
    apiFetch<{ items: OperationalPeriod[]; total: number }>(`${root}/projects/${workspaceId}/periods`, { token }),
  openPeriod: (token: string, workspaceId: number, draft: PeriodDraft, key: string) =>
    apiFetch<OperationalPeriod>(`${root}/projects/${workspaceId}/periods`, command(token, key, draft)),
  transition: (
    token: string,
    workspaceId: number,
    period: OperationalPeriod,
    action: "review" | "close" | "publish" | "reopen",
    reason: string,
    key: string
  ) =>
    apiFetch<OperationalPeriod>(
      `${root}/projects/${workspaceId}/periods/${period.id}/${action}`,
      command(token, key, { reason }, period.version)
    ),
  profiles: async (token: string) => {
    const result = await apiFetch<{
      items: OperationalProfile[];
      default_content: Record<string, unknown>;
      allowed_actions: string[];
    }>(`${root}/admin/profiles`, { token });
    return { ...result, items: result.items.map(normalizedProfile) };
  },
  createProfile: (
    token: string,
    draft: { code: string; name: string; content_json: Record<string, unknown> },
    key: string
  ) => apiFetch<OperationalProfile>(`${root}/admin/profiles`, command(token, key, draft)).then(normalizedProfile),
  updateProfile: (
    token: string,
    profile: OperationalProfile,
    draft: { name: string; content_json: Record<string, unknown> },
    key: string
  ) =>
    apiFetch<OperationalProfile>(`${root}/admin/profiles/${profile.id}`, {
      ...command(token, key, draft, profile.version),
      method: "PUT",
    }).then(normalizedProfile),
  profileCommand: (
    token: string,
    profile: OperationalProfile,
    action: "publish" | "successor",
    reason: string,
    key: string
  ) =>
    apiFetch<OperationalProfile>(
      `${root}/admin/profiles/${profile.id}/${action}`,
      command(token, key, { reason }, profile.version)
    ).then(normalizedProfile),
};
