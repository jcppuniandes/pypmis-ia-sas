import type { JsonRecord } from "../schedule-foundation/types";

export type FourDObject = {
  object_id: number;
  model_version_id: number;
  guid: string;
  express_id: number;
  geometry_reference?: unknown;
  source_hash?: string;
};
export type FourDItem = {
  id: string | number;
  scope_item_id: number;
  scope_code: string;
  name: string;
  scope_nature: string;
  plan_item_id: number | null;
  plan_code?: string;
  area?: string;
  zone?: string;
  system?: string;
  state: string;
  semantic_state: string;
  visible: boolean;
  visual_classes: string[];
  activities: JsonRecord[];
  wbs: JsonRecord[];
  packages: JsonRecord[];
  cwas: JsonRecord[];
  readiness: JsonRecord[];
  constraints: JsonRecord[];
  objects: FourDObject[];
  derived_models: JsonRecord[];
  mapping_issues: unknown[];
};
export type FourDView = {
  version: number;
  source: {
    kind: string;
    schedule_version_id: number;
    register_id: number;
    baseline_id: number | null;
    data_date: string | null;
    content_hash: string;
    timezone?: string;
  };
  at: string;
  configuration: JsonRecord;
  items: FourDItem[];
  sources: { current: JsonRecord[]; baselines: JsonRecord[] };
  milestones: { external_id: string; name: string; date: string | null }[];
  timeline: { start: string | null; finish: string | null; data_date: string | null };
  period_associations: JsonRecord[];
  source_hashes: JsonRecord;
  diagnostics: unknown[];
  authority: JsonRecord;
};
export type FourDComparison = {
  baseline: FourDView;
  current: FourDView;
  items: {
    id: string | number;
    scope_item_id: number;
    plan_item_id: number | null;
    baseline_state: string;
    current_state: string;
    variance_classification: string;
  }[];
};
export type FourDFilters = Record<string, string>;
export const fourDFilterLabels: Record<string, string> = {
  wbs: "WBS",
  activity: "Activity",
  scope_item_id: "Scope",
  scope_nature: "Scope Nature",
  plan_item_id: "Plan",
  cwa_id: "CWA",
  package_type: "Package Type",
  work_package_id: "Package",
  area: "Area",
  zone: "Zone",
  system: "System",
  activity_status: "Activity Status",
  critical: "Critical",
  near_critical: "Near Critical",
  execution_readiness: "Execution Readiness",
  blocked: "Blocked",
};
