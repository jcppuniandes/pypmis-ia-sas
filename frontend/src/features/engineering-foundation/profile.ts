import { isEngineeringRow, text, type EngineeringRow } from "./api";
import type { CodeOption } from "./types";

export function profileContent(config: EngineeringRow | null) {
  const profile = config?.profile;
  return isEngineeringRow(profile) && isEngineeringRow(profile.content_json) ? profile.content_json : {};
}

export function codeOptions(value: unknown): CodeOption[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((entry: unknown) => {
    if (typeof entry === "string" && entry) return [{ code: entry, label: entry }];
    if (isEngineeringRow(entry) && text(entry.code))
      return [{ code: text(entry.code), label: text(entry.label) || text(entry.code) }];
    return [];
  });
}

export const revisionCoding = ["ALPHANUMERIC", "NUMERIC", "ALPHABETIC"];
export const progressMethods = [
  "DELIVERABLE_MILESTONE",
  "WEIGHTED_DELIVERABLES",
  "RULE_OF_CREDIT",
  "STEP_METHOD",
  "ENGINEERING_HOURS",
];

const dateValue = (value: unknown) => {
  const date = typeof value === "string" ? new Date(value) : null;
  return date && Number.isFinite(date.getTime()) ? date.toISOString().slice(0, 16) : "";
};
const nested = (row: EngineeringRow, key: string) => (isEngineeringRow(row[key]) ? row[key] : {});

export function profileDraft(content: EngineeringRow) {
  const scope = nested(content, "scope");
  const reviews = nested(content, "review_rules");
  const release = nested(content, "ifc_release_rules");
  const readiness = nested(content, "readiness_evidence_rules");
  const labels = nested(content, "status_labels");
  return {
    scopeType: text(scope.type) || "tenant",
    workspaceId: text(scope.workspace_id),
    inherit: content.inherit_to_descendants === true,
    from: dateValue(content.effective_from),
    to: dateValue(content.effective_to),
    types: codeOptions(content.deliverable_types).map((row) => row.code),
    disciplines: codeOptions(content.disciplines).map((row) => row.code),
    purposes: codeOptions(content.purposes_of_issue).map((row) => row.code),
    revisionRule: text(content.revision_code_rule) || "ALPHANUMERIC",
    requireCheck: reviews.require_technical_check !== false,
    requireDocument: reviews.require_document_before_submit === true,
    releasePurposes: codeOptions(release.eligible_purposes).map((row) => row.code),
    independentReleaser: release.releaser_distinct_from_approver !== false,
    maxAge: text(readiness.max_age_days),
    progressMethod: text(content.progress_default_method) || progressMethods[0],
    horizon: text(content.lookahead_days) || "28",
    labels: Object.entries(labels).flatMap(([key, value]) => (text(value) ? [{ code: key, label: text(value) }] : [])),
  };
}

export type ProfileDraft = ReturnType<typeof profileDraft>;

function boundedInteger(value: string, min: number, max: number, label: string) {
  const parsed = Number(value);
  if (!/^\d+$/.test(value) || !Number.isSafeInteger(parsed) || parsed < min || parsed > max)
    throw new Error(`${label} debe ser un entero de ${min} a ${max}.`);
  return parsed;
}

export function profilePayload(draft: ProfileDraft): EngineeringRow {
  const workspaceId =
    draft.scopeType === "workspace" ? boundedInteger(draft.workspaceId, 1, Number.MAX_SAFE_INTEGER, "Workspace") : null;
  if (!(draft.types.length && draft.disciplines.length && draft.purposes.length && draft.releasePurposes.length))
    throw new Error("Configure tipos, disciplinas, propósitos y propósitos elegibles de IFC.");
  if (draft.releasePurposes.some((entry) => !draft.purposes.includes(entry)))
    throw new Error("Los propósitos elegibles para IFC deben existir en el perfil.");
  if (draft.from && draft.to && draft.from >= draft.to)
    throw new Error("La vigencia final debe ser posterior a la inicial.");
  return {
    scope: { type: draft.scopeType, workspace_id: workspaceId },
    inherit_to_descendants: draft.inherit,
    effective_from: draft.from ? new Date(`${draft.from}Z`).toISOString() : null,
    effective_to: draft.to ? new Date(`${draft.to}Z`).toISOString() : null,
    deliverable_types: draft.types,
    disciplines: draft.disciplines,
    purposes_of_issue: draft.purposes,
    revision_code_rule: draft.revisionRule,
    review_rules: {
      require_technical_check: draft.requireCheck,
      require_document_before_submit: draft.requireDocument,
    },
    ifc_release_rules: {
      eligible_purposes: draft.releasePurposes,
      releaser_distinct_from_approver: draft.independentReleaser,
    },
    readiness_evidence_rules: {
      max_age_days: draft.maxAge ? boundedInteger(draft.maxAge, 1, 3650, "Vigencia de evidencia") : null,
    },
    progress_default_method: draft.progressMethod,
    lookahead_days: boundedInteger(draft.horizon, 1, 120, "Horizonte"),
    status_labels: Object.fromEntries(draft.labels.map((row) => [row.code, row.label])),
  };
}
