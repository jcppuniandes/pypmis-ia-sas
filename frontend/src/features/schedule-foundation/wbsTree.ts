import type { ScheduleObject } from "./types";

export function wbsHierarchy(rows: ScheduleObject[]) {
  const ids = new Set(rows.map((row) => row.external_id));
  const roots = rows.filter((row) => !row.parent_external_id || !ids.has(row.parent_external_id));
  return { roots, children: (id: string) => rows.filter((row) => row.parent_external_id === id) };
}
