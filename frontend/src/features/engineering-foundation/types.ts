import type { EngineeringCommand, EngineeringRow } from "./api";

export type EngineeringScope = {
  token: string;
  base: string;
  refreshKey: number;
  reload: () => void;
  can: (action: string) => boolean;
  busy: boolean;
  command: EngineeringCommand;
};

export type EngineeringPanel = EngineeringScope & {
  config: EngineeringRow | null;
  deliverable: EngineeringRow | null;
  revision: EngineeringRow | null;
  setDeliverableId: (id: string) => void;
  setRevisionId: (id: string) => void;
};

export type CodeOption = { code: string; label: string };

export const engineeringTabs = [
  "Deliverable Register",
  "Revisions",
  "Reviews & Approvals",
  "IFC Release",
  "Engineering Groups",
  "Interfaces",
  "Engineering Readiness",
  "Engineering Progress",
  "Engineering Look-Ahead",
  "History",
] as const;
