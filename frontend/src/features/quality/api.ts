import { useCommands, useRead } from "../contracts-foundation/api";
export { useCommands, useRead };
export { isRow, positiveId, query, rows, text, versionOf } from "../contracts-foundation/api";
export type { Row, Scope } from "../contracts-foundation/api";
export const projectRoot = (id: number) => `/api/v1/quality/projects/${id}`;
export const profilesRoot = "/api/v1/quality/admin/profiles";
export const permits = (actions: unknown, duty: string) =>
  Array.isArray(actions) && actions.some((value) => value === duty || value === `quality.${duty}`);
