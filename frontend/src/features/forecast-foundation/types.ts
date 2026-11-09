import type { ProgressRow } from "../progress-foundation/types";

export { display, label, object, revision, rows, text } from "../progress-foundation/types";
export type ForecastRow = ProgressRow;
export type ForecastRecord = ForecastRow & { id: number; version: number; status: string };
export type ForecastSurface = "forecast" | "performance" | "reporting";
export type ForecastOverview = {
  context: ForecastRow;
  configuration: ForecastRow | null;
  allowed_actions: string[];
  versions: ForecastRecord[];
  baseline_bundles: ForecastRow[];
  periods: ForecastRow[];
  schedule_versions: ForecastRow[];
  scope_items: ForecastRow[];
  plan_items: ForecastRow[];
  packages: ForecastRow[];
  control_accounts: ForecastRow[];
  cbs?: ForecastRow[];
  cost_codes?: ForecastRow[];
  users?: ForecastRow[];
  commitments?: ForecastRow[];
  history?: ForecastRow[];
  methods?: string[];
};
export type ForecastAssumption = {
  code: string;
  name: string;
  kind: string;
  value: string;
  unit: string;
  currency?: string | null;
  source_reference: string;
  owner_id: number;
  effective_date: string;
  confidence: string;
  status: string;
  evidence_ref: string;
  rationale: string;
};
export type ForecastComponent = {
  code: string;
  name: string;
  method: string;
  assumption_codes: string[];
  scope_item_id?: number | null;
  plan_item_id?: number | null;
  work_package_id?: number | null;
  control_account_id?: number | null;
  cbs_id?: number | null;
  cost_code_id?: number | null;
  schedule_version_id?: number | null;
  activity_external_id: string;
  wbs_external_id: string;
  area: string;
  zone: string;
  system: string;
  discipline: string;
  currency?: string | null;
  unit: string;
  inputs: ForecastRow;
};
export const componentFamilies = ["cost_items", "time_items", "milestones", "resource_items"] as const;
export type ComponentFamily = (typeof componentFamilies)[number];
export type ForecastDraft = {
  code: string;
  name: string;
  bundle_id: number | null;
  period_id: number | null;
  as_of: string;
  schedule_version_id: number | null;
  currency: string;
  method: string;
  confidence: string;
  confidence_rationale: string;
  data_completeness: string;
  assumption_maturity: string;
  evidence_ref: string;
  assumptions: ForecastAssumption[];
  cost_items: ForecastComponent[];
  time_items: ForecastComponent[];
  milestones: ForecastComponent[];
  resource_items: ForecastComponent[];
};
export type ForecastCommand = (
  path: string,
  payload: unknown,
  version?: number,
  method?: string,
  surface?: ForecastSurface
) => Promise<ForecastRow>;
export type ForecastQuery = (path: string, surface?: ForecastSurface) => Promise<ForecastRow>;
export type ForecastPanelProps = {
  data: ForecastOverview;
  selected: ForecastRecord | null;
  periodId: string;
  asOf: string;
  busy: boolean;
  reason: string;
  query: ForecastQuery;
  command: ForecastCommand;
  can: (action: string) => boolean;
};
export type ForecastEditorProps = ForecastPanelProps & {
  draft: ForecastDraft;
  setDraft: (value: ForecastDraft) => void;
  editable: boolean;
};
export const forecastMethods = [
  "BOTTOM_UP",
  "QUANTITY_RATE",
  "ACTIVITY_REMAINING_DURATION",
  "PRODUCTIVITY_BASED",
  "COMMITMENT_BASED",
  "CONTROL_ACCOUNT",
  "TREND_BASED",
  "MANUAL_GOVERNED",
];
export const forecastTabs = [
  "Forecast Overview",
  "ETC / EAC",
  "Time Forecast",
  "Milestones",
  "Resource Forecast",
  "Assumptions",
  "Variance & Trends",
  "S-Curves",
  "Project Controls Dashboard",
  "Executive Dashboard",
  "4-Week Look-Ahead",
  "Reporting History",
] as const;
export function emptyDraft(): ForecastDraft {
  return {
    code: "",
    name: "",
    bundle_id: null,
    period_id: null,
    as_of: "",
    schedule_version_id: null,
    currency: "",
    method: "BOTTOM_UP",
    confidence: "MEDIUM",
    confidence_rationale: "",
    data_completeness: "NOT_ASSESSED",
    assumption_maturity: "NOT_ASSESSED",
    evidence_ref: "",
    assumptions: [],
    cost_items: [],
    time_items: [],
    milestones: [],
    resource_items: [],
  };
}
export function draftFromVersion(row: ForecastRecord): ForecastDraft {
  const sourceInput = row.input_json;
  const input =
    sourceInput && typeof sourceInput === "object" && !Array.isArray(sourceInput) ? (sourceInput as ForecastRow) : {};
  const source = Object.keys(input).length ? input : row;
  return Object.fromEntries(
    Object.entries(emptyDraft()).map(([key, fallback]) => [key, source[key] ?? fallback])
  ) as ForecastDraft;
}
