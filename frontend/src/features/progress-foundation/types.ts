export type ProgressRow = Record<string, unknown>;
export type ProgressRecord = ProgressRow & { id: number; version: number; status: string };
export type ProgressOverview = {
  context: ProgressRow;
  configuration: ProgressRow | null;
  allowed_actions: string[];
  measurements: ProgressRecord[];
  rules: ProgressRecord[];
  scope_items: ProgressRow[];
  plan_items: ProgressRow[];
  packages: ProgressRow[];
  schedule_versions: ProgressRow[];
  scope_baselines: ProgressRow[];
  schedule_baselines?: ProgressRow[];
  cost_baselines?: ProgressRow[];
  periods: ProgressRow[];
  control_accounts: ProgressRow[];
  baseline_bundles?: ProgressRecord[];
  history?: ProgressRow[];
  types?: string[];
  methods?: string[];
  weighting_bases?: string[];
};
export type ProgressCommand = (
  path: string,
  payload: unknown,
  version?: number,
  method?: string
) => Promise<ProgressRow>;
export type ProgressPanelProps = {
  data: ProgressOverview;
  periodId: string;
  asOf: string;
  busy: boolean;
  reason: string;
  command: ProgressCommand;
  query: (path: string) => Promise<ProgressRow>;
  can: (action: string) => boolean;
};
export const progressTabs = [
  "Progress Overview",
  "Quantity Progress",
  "Physical Progress",
  "Schedule Progress",
  "Cost Progress",
  "Earned Progress",
  "Milestones / Rules of Credit",
  "Period Review",
  "Baseline Integration",
  "Progress History",
] as const;
export const physicalMethods = [
  "QUANTITY_BASED",
  "WEIGHTED_COMPONENTS",
  "MILESTONE_BASED",
  "STEP_METHOD",
  "RULE_OF_CREDIT",
  "MANUAL_EXPERT_ASSESSMENT",
];
export const weightingBases = [
  "QUANTITY",
  "BUDGET",
  "LABOR_HOURS",
  "ENGINEERING_HOURS",
  "CONTRACT_VALUE",
  "MANUAL_APPROVED_WEIGHT",
];
export function text(row: ProgressRow | null | undefined, key: string, fallback = ""): string {
  const value = row?.[key];
  return typeof value === "string" || typeof value === "number" ? String(value) : fallback;
}
export function rows(value: unknown): ProgressRow[] {
  return Array.isArray(value)
    ? value.filter((item): item is ProgressRow => Boolean(item) && typeof item === "object" && !Array.isArray(item))
    : [];
}
export function object(value: unknown): ProgressRow {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as ProgressRow) : {};
}
export function display(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (Array.isArray(value)) return value.map(display).join(", ");
  if (typeof value === "object")
    return Object.entries(value)
      .map(([key, item]) => `${key}: ${display(item)}`)
      .join(" · ");
  return String(value);
}
export function label(row: ProgressRow): string {
  const code = text(
    row,
    "code",
    text(
      row,
      "scope_code",
      text(row, "plan_code", text(row, "package_code", text(row, "period_code", text(row, "id"))))
    )
  );
  return `${code} · ${text(row, "name", text(row, "status"))}`;
}
export function revision(row: ProgressRow): number {
  return Number(row.version ?? row.revision ?? 1);
}
export function effectiveStatus(row: ProgressRow): string {
  return text(row, "effective_status", text(row, "status"));
}
export function percentage(value: unknown): string {
  return value === null || value === undefined || value === "" ? "No disponible" : `${display(value)} %`;
}
