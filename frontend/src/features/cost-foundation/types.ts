export type CostValue = string | number | boolean | null | CostRow | CostValue[];
export type CostRow = { [key: string]: CostValue | undefined };
export type CostRecord = CostRow & { id: number; version: number; status: string };
export type CostOverview = {
  context: CostRow;
  configuration: CostRow | null;
  allowed_actions: string[];
  cbs: CostRecord[];
  cost_codes: CostRecord[];
  control_accounts: CostRecord[];
  mappings: CostRecord[];
  rates: CostRecord[];
  apus: CostRecord[];
  budgets: CostRecord[];
  budget_lines: CostRecord[];
  baselines: CostRecord[];
  phasing: CostRecord[];
  actuals: CostRecord[];
  commitment_references: CostRecord[];
  history: CostRecord[];
  scope_items: CostRow[];
  plan_items: CostRow[];
  packages: CostRow[];
  schedule_versions: CostRow[];
  periods: CostRow[];
  summary?: CostRow;
  accrual?: CostRow;
  fx_rates?: CostRecord[];
  budget_semantics?: CostRow;
};
export type CostCommand = (path: string, payload: unknown, version?: number, method?: string) => Promise<CostRow>;
export type CostPanelProps = {
  data: CostOverview;
  busy: boolean;
  reason: string;
  command: CostCommand;
  can: (action: string) => boolean;
  query: (path: string) => Promise<CostRow>;
};
export function display(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}
export function text(row: CostRow | undefined | null, key: string, fallback = ""): string {
  const value = row?.[key];
  return typeof value === "string" || typeof value === "number" ? String(value) : fallback;
}
export function collection(value: unknown): CostRow[] {
  return Array.isArray(value) ? value.filter((row) => row && typeof row === "object") : [];
}
export function rowLabel(row: CostRow): string {
  return `${text(row, "code", text(row, "package_code", text(row, "scope_code", text(row, "period_code", text(row, "id")))))} · ${text(row, "name", text(row, "title", text(row, "status")))}`;
}
export function policyValues(data: CostOverview, key: string, fallback: string[]): string[] {
  const content = data.configuration?.content_json;
  if (!content || typeof content !== "object" || Array.isArray(content)) return fallback;
  const value = content[key];
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : fallback;
}
export function moneyDisplay(value: unknown): string {
  if (!value || typeof value !== "object" || Array.isArray(value)) return display(value);
  const row = value as CostRow;
  if (row.status === "NO_AGGREGATION") return "NO_AGGREGATION · revisar monedas y FX";
  const amount = row.amount ?? row.net_commitment;
  return amount !== null && amount !== undefined
    ? `${display(amount)} ${text(row, "currency")}`.trim()
    : text(row, "status", "—");
}
