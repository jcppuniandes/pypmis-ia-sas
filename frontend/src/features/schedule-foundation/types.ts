export type JsonRecord = Record<string, unknown>;
export type ScheduleObject = JsonRecord & {
  external_id: string;
  code?: string;
  name?: string;
  parent_external_id?: string | null;
};
export type ScheduleSnapshot = {
  project: JsonRecord;
  wbs: ScheduleObject[];
  activities: ScheduleObject[];
  calendars: ScheduleObject[];
  relationships: JsonRecord[];
  constraints: JsonRecord[];
  codes: JsonRecord[];
  code_assignments: JsonRecord[];
  external_links: JsonRecord[];
};
export type ScheduleRegister = {
  id: number;
  version: number;
  schedule_code: string;
  name: string;
  schedule_type: string;
  status: string;
  current_version_id: number | null;
  baseline_version_id: number | null;
  calendar_basis: string;
  timezone: string;
  purpose?: string;
};
export type ScheduleMapping = {
  id?: number;
  schedule_version_id?: number;
  target_kind: "WBS" | "ACTIVITY";
  target_external_id: string;
  plan_item_ids: number[];
  scope_item_ids: number[];
  status?: string;
  reason?: string;
  [key: string]: unknown;
};
export type ScheduleVersion = {
  id: number;
  register_id: number;
  revision: number;
  version: number;
  status: string;
  kind: string;
  data_date: string | null;
  source_file_name: string;
  source_format: string;
  source_hash: string;
  snapshot_json: ScheduleSnapshot;
  validation_json: JsonRecord;
  diff_json: JsonRecord;
  health_json: JsonRecord;
  mappings: ScheduleMapping[];
};
export type ScheduleBaseline = {
  id: number;
  version: number;
  revision?: number;
  status: string;
  schedule_version_id: number;
  register_id?: number;
  baseline_type: string;
  content_hash?: string;
  created_by?: number;
  previous_baseline_id?: number | null;
};
export type ScheduleExport = {
  id: number;
  schedule_version_id: number;
  format?: string;
  source_file_name?: string;
  file_name?: string;
  source_hash?: string;
  manifest_json?: JsonRecord;
  [key: string]: unknown;
};
export type ScheduleProfile = {
  id: number;
  version: number;
  revision: number;
  code: string;
  name: string;
  status: string;
  content_json: JsonRecord;
  content_hash?: string;
};
export type ScheduleOverview = {
  context: JsonRecord;
  configuration: JsonRecord | null;
  allowed_actions: string[];
  current_scope_item_ids?: number[];
  current_scope_baseline_id?: number | null;
  registers: ScheduleRegister[];
  versions: ScheduleVersion[];
  baselines: ScheduleBaseline[];
  mappings: ScheduleMapping[];
  exports: ScheduleExport[];
  period_associations: JsonRecord[];
  scope_items: {
    id: number;
    scope_code: string;
    name: string;
    scope_nature?: string;
    status?: string;
    unit?: string;
  }[];
  plan_items: {
    id: number;
    code: string;
    name: string;
    status?: string;
    allocations?: { scope_item_id: number; quantity: string | number; unit: string }[];
  }[];
  derived_models: { id: number; revision?: number; snapshot_json?: JsonRecord; [key: string]: unknown }[];
  periods: {
    id: number;
    code?: string;
    period_code?: string;
    cutoff_date?: string;
    cutoff_at?: string;
    cutoff?: string;
    status?: string;
    [key: string]: unknown;
  }[];
};
export type ScheduleCommand = (path: string, payload: unknown, version?: number, method?: string) => Promise<unknown>;
export type WorkspaceProps = {
  data: ScheduleOverview;
  register: ScheduleRegister | undefined;
  selected: ScheduleVersion | undefined;
  busy: boolean;
  can: (action: string) => boolean;
  command: ScheduleCommand;
};

export function display(value: unknown): string {
  if (value === null || value === undefined || value === "") return "UNKNOWN";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}
export function policyContent(configuration: JsonRecord | null): JsonRecord {
  if (!configuration) return {};
  return (
    configuration.content_json && typeof configuration.content_json === "object"
      ? configuration.content_json
      : configuration
  ) as JsonRecord;
}
export function policyValues(configuration: JsonRecord | null, key: string, fallback: string[]): string[] {
  const content = policyContent(configuration);
  const values = content[key];
  return Array.isArray(values) ? values.filter((value): value is string => typeof value === "string") : fallback;
}
export function emptySnapshot(timezone = "America/Bogota"): ScheduleSnapshot {
  return {
    project: { external_id: "", code: "", name: "", data_date: "", timezone },
    wbs: [],
    activities: [],
    calendars: [],
    relationships: [],
    constraints: [],
    codes: [],
    code_assignments: [],
    external_links: [],
  };
}
