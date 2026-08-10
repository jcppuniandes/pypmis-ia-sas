import { apiFetch } from "../../../api/client";
import type {
  CompositionRule,
  ConfigurationVersion,
  ConfigurationValidation,
  EnterpriseExplorer,
  EnterpriseNode,
  EnterpriseNodeDetail,
  EnterpriseStructureConfiguration,
  ExplorerFilters,
  NodePayload,
  PublicationResult,
} from "../types";

const adminRoot = "/api/v1/admin-configuration/enterprise-structure";
const userRoot = "/api/v1/enterprise-structure";

function queryString(filters: ExplorerFilters) {
  const query = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value) query.set(key, value);
  });
  return query.toString();
}

export const enterpriseStructureApi = {
  configuration: (token: string) => apiFetch<EnterpriseStructureConfiguration>(`${adminRoot}/configuration`, { token }),

  createNode: (token: string, payload: NodePayload) =>
    apiFetch<EnterpriseNode>(`${adminRoot}/nodes`, {
      method: "POST",
      token,
      body: JSON.stringify(payload),
    }),

  updateNode: (token: string, nodeId: number, payload: Partial<NodePayload> & { expected_version: number }) =>
    apiFetch<EnterpriseNode>(`${adminRoot}/nodes/${nodeId}`, {
      method: "PATCH",
      token,
      body: JSON.stringify(payload),
    }),

  archiveNode: (token: string, nodeId: number) =>
    apiFetch<EnterpriseNode>(`${adminRoot}/nodes/${nodeId}`, { method: "DELETE", token }),

  addClassification: (token: string, nodeId: number, categorySetCode: string, categoryItemCode: string) =>
    apiFetch(`${adminRoot}/nodes/${nodeId}/classifications`, {
      method: "POST",
      token,
      body: JSON.stringify({ category_set_code: categorySetCode, category_item_code: categoryItemCode }),
    }),

  removeClassification: (token: string, classificationId: number) =>
    apiFetch<void>(`${adminRoot}/classifications/${classificationId}`, { method: "DELETE", token }),

  addLink: (token: string, sourceId: number, targetId: number, relationshipType: string) =>
    apiFetch(`${adminRoot}/links`, {
      method: "POST",
      token,
      body: JSON.stringify({
        source_workspace_id: sourceId,
        target_workspace_id: targetId,
        relationship_type: relationshipType,
      }),
    }),

  removeLink: (token: string, linkId: number) =>
    apiFetch<void>(`${adminRoot}/links/${linkId}`, { method: "DELETE", token }),

  cloneCategory: (token: string, categoryCode: string) =>
    apiFetch<ConfigurationVersion>(`${adminRoot}/categories/${categoryCode}/clone`, { method: "POST", token }),

  updateCategory: (
    token: string,
    configurationId: number,
    payload: {
      name: string;
      description: string;
      applicable_types: string[];
      items: Array<{ code: string; label: string }>;
    }
  ) =>
    apiFetch(`${adminRoot}/categories/${configurationId}`, {
      method: "PUT",
      token,
      body: JSON.stringify(payload),
    }),

  updateCompositionRule: (
    token: string,
    parentTypeCode: string,
    payload: {
      allowed_children: string[];
      max_depth: number | null;
      can_be_root: boolean;
      required_categories: string[];
      required_fields: string[];
    }
  ) =>
    apiFetch<CompositionRule>(`${adminRoot}/composition-rules/${parentTypeCode}`, {
      method: "PUT",
      token,
      body: JSON.stringify(payload),
    }),

  validate: (token: string, configurationIds: number[] = []) =>
    apiFetch<ConfigurationValidation>(`${adminRoot}/validate`, {
      method: "POST",
      token,
      body: JSON.stringify({ configuration_ids: configurationIds }),
    }),

  publish: (token: string, configurationIds: number[] = [], expectedHashes: Record<number, string> = {}) =>
    apiFetch<PublicationResult>(`${adminRoot}/publish`, {
      method: "POST",
      token,
      body: JSON.stringify({ configuration_ids: configurationIds, expected_hashes: expectedHashes }),
    }),

  cloneRelease: (token: string) => apiFetch<ConfigurationVersion[]>(`${adminRoot}/clone`, { method: "POST", token }),

  explorer: (token: string, filters: ExplorerFilters) => {
    const query = queryString(filters);
    return apiFetch<EnterpriseExplorer>(`${userRoot}/overview${query ? `?${query}` : ""}`, { token });
  },

  nodeDetail: (token: string, nodeId: number) =>
    apiFetch<EnterpriseNodeDetail>(`${userRoot}/nodes/${nodeId}`, { token }),
};
