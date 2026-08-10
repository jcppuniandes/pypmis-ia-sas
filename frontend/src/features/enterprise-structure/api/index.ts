import { apiFetch } from "../../../api/client";
import type {
  CompositionRule,
  CoreRevision,
  ConfigurationVersion,
  ConfigurationValidation,
  EnterpriseExplorer,
  EnterpriseNode,
  EnterpriseNodeDetail,
  EnterpriseStructureConfiguration,
  ExplorerFilters,
  NodePayload,
  PublicationResult,
  RecordCodePreview,
  RevisionClassification,
  RevisionDiff,
  RevisionValidation,
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

  createCoreRevision: (token: string, publishedId: number) =>
    apiFetch<CoreRevision>(`${adminRoot}/enterprise-core-releases/${publishedId}/clone`, {
      method: "POST",
      token,
    }),

  coreRevision: (token: string, releaseId: number) =>
    apiFetch<CoreRevision>(`${adminRoot}/enterprise-core-releases/${releaseId}`, { token }),

  previewRecordCode: (
    token: string,
    releaseId: number,
    parentKey: string,
    workspaceTypeCode: string,
    workspaceKey?: string
  ) =>
    apiFetch<RecordCodePreview>(`${adminRoot}/enterprise-core-releases/${releaseId}/record-code-preview`, {
      method: "POST",
      token,
      body: JSON.stringify({
        parent_key: parentKey,
        workspace_type_code: workspaceTypeCode,
        workspace_key: workspaceKey,
      }),
    }),

  addRevisionWorkspace: (
    token: string,
    releaseId: number,
    payload: {
      name: string;
      workspace_type_code: string;
      parent_key: string;
      description: string;
      responsible_user_id: number | null;
      status: string;
      applicable_classifications: RevisionClassification[];
    }
  ) =>
    apiFetch<CoreRevision>(`${adminRoot}/enterprise-core-releases/${releaseId}/workspaces`, {
      method: "POST",
      token,
      body: JSON.stringify(payload),
    }),

  editRevisionWorkspace: (
    token: string,
    releaseId: number,
    workspaceKey: string,
    payload: { name?: string; description?: string; responsible_user_id?: number | null; status?: string }
  ) =>
    apiFetch<CoreRevision>(`${adminRoot}/enterprise-core-releases/${releaseId}/workspaces/${workspaceKey}`, {
      method: "PATCH",
      token,
      body: JSON.stringify(payload),
    }),

  moveRevisionWorkspace: (token: string, releaseId: number, workspaceKey: string, newParentKey: string) =>
    apiFetch<CoreRevision>(`${adminRoot}/enterprise-core-releases/${releaseId}/workspaces/${workspaceKey}/move`, {
      method: "POST",
      token,
      body: JSON.stringify({ new_parent_key: newParentKey }),
    }),

  archiveRevisionWorkspace: (token: string, releaseId: number, workspaceKey: string) =>
    apiFetch<CoreRevision>(`${adminRoot}/enterprise-core-releases/${releaseId}/workspaces/${workspaceKey}/archive`, {
      method: "POST",
      token,
    }),

  setRevisionClassifications: (
    token: string,
    releaseId: number,
    workspaceKey: string,
    classifications: RevisionClassification[]
  ) =>
    apiFetch<CoreRevision>(
      `${adminRoot}/enterprise-core-releases/${releaseId}/workspaces/${workspaceKey}/classifications`,
      { method: "PUT", token, body: JSON.stringify({ classifications }) }
    ),

  validateCoreRevision: (token: string, releaseId: number) =>
    apiFetch<RevisionValidation>(`${adminRoot}/enterprise-core-releases/${releaseId}/validate`, {
      method: "POST",
      token,
    }),

  compareCoreRevision: (token: string, releaseId: number) =>
    apiFetch<RevisionDiff>(`${adminRoot}/enterprise-core-releases/${releaseId}/diff`, { token }),

  approveCoreRevision: (token: string, releaseId: number, draftHash: string, diffHash: string) =>
    apiFetch<CoreRevision>(`${adminRoot}/enterprise-core-releases/${releaseId}/approve`, {
      method: "POST",
      token,
      body: JSON.stringify({ draft_hash: draftHash, diff_hash: diffHash }),
    }),

  publishCoreRevision: (token: string, releaseId: number, draftHash: string, diffHash: string) =>
    apiFetch<CoreRevision>(`${adminRoot}/enterprise-core-releases/${releaseId}/publish`, {
      method: "POST",
      token,
      body: JSON.stringify({ draft_hash: draftHash, diff_hash: diffHash }),
    }),

  explorer: (token: string, filters: ExplorerFilters) => {
    const query = queryString(filters);
    return apiFetch<EnterpriseExplorer>(`${userRoot}/overview${query ? `?${query}` : ""}`, { token });
  },

  nodeDetail: (token: string, nodeId: number) =>
    apiFetch<EnterpriseNodeDetail>(`${userRoot}/nodes/${nodeId}`, { token }),
};
