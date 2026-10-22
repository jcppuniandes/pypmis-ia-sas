import type { JsonRecord, ScheduleProfile, ScheduleVersion } from "../schedule-foundation/types";

export type AwpRecord = JsonRecord & { id: number; version: number; status: string };
export type Cwa = AwpRecord & {
  code: string;
  name: string;
  parent_cwa_id?: number | null;
  description?: string;
  area?: string;
  zone?: string;
  location?: string;
};
export type WorkPackage = AwpRecord & {
  package_code: string;
  package_type: string;
  name: string;
  cwa_id?: number | null;
  owner_user_id?: number | null;
  responsible_role?: string;
  readiness_state?: string;
  release_state?: string;
  revision?: number;
};
export type ExecutionConstraint = AwpRecord & {
  code: string;
  title: string;
  constraint_type: string;
  blocking: boolean;
  owner_user_id?: number | null;
  due_date?: string | null;
  evidence_reference?: string;
  waiver_reference?: string;
};
export type AwpOverview = {
  version: number;
  context: JsonRecord;
  configuration: JsonRecord | null;
  allowed_actions: string[];
  cwas: Cwa[];
  packages: WorkPackage[];
  mappings: AwpRecord[];
  effective_mappings: AwpRecord[];
  dependencies: AwpRecord[];
  constraints: ExecutionConstraint[];
  constraint_mappings: AwpRecord[];
  assessments: AwpRecord[];
  current_readiness: JsonRecord[] | Record<string, JsonRecord>;
  scope_items: { id: number; scope_code: string; name: string; scope_nature?: string }[];
  plan_items: { id: number; code: string; name: string; status?: string }[];
  schedule_versions: ScheduleVersion[];
  current_scope_item_ids: number[];
};
export type ProfileList = { items: ScheduleProfile[]; default_content: JsonRecord; allowed_actions: string[] };
export type AwpCommand = (path: string, payload: unknown, version?: number, method?: string) => Promise<unknown>;
export type AwpPanelProps = {
  data: AwpOverview;
  busy: boolean;
  reason: string;
  command: AwpCommand;
  can: (action: string) => boolean;
};
export const packageTypes = ["EWP", "PWP", "CWP", "IWP", "TWP", "SUPPORT", "LOGISTICS", "TEMPORARY_WORKS"];
export const constraintTypes = [
  "ENGINEERING",
  "PROCUREMENT",
  "MATERIAL",
  "LOGISTICS",
  "ACCESS",
  "WORKFRONT",
  "PREDECESSOR",
  "PERMIT",
  "QUALITY",
  "HSE",
  "RESOURCE",
  "EQUIPMENT",
  "TEMPORARY_WORKS",
  "INTERFACE",
  "CLIENT_DECISION",
  "CONTRACTUAL",
  "OTHER",
];
