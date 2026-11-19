import { useCommands, useRead } from "../contracts-foundation/api";
import type { Row } from "../contracts-foundation/api";

// Transport, retries and ETags are shared; domain permissions and endpoints are not.
export { useCommands, useRead };
export { isRow, positiveId, query, rows, text, versionOf } from "../contracts-foundation/api";
export type { Row };
export const projectRoot = (id: number) => `/api/v1/field-operations/projects/${id}`;
export const profilesRoot = "/api/v1/field-operations/admin/profiles";
export const permits = (actions: unknown, duty: string) =>
  Array.isArray(actions) && actions.some((value) => value === duty || value === `field_operations.${duty}`);
export type Scope = ReturnType<typeof useCommands> & {
  token: string;
  base: string;
  workspaceId: number;
  profile: Row | null;
  can: (action: string) => boolean;
};
