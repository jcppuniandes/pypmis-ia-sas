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
  PhysicalConfiguration,
  PhysicalPreview,
  PublicationResult,
  ProjectConfiguration,
  ProjectCreationOptions,
  ProjectCreationRequest,
  ProjectRequestPayload,
  ProjectRequestPreview,
  ProjectPreview,
  ProjectTemplatePayload,
  ProjectWorkspaceOverview,
  ProjectWorkspaceInitialization,
  ProjectWorkspaceListItem,
  RecordCodePreview,
  RevisionClassification,
  RevisionDiff,
  RevisionValidation,
} from "../types";

const adminRoot = "/api/v1/admin-configuration/enterprise-structure";
const userRoot = "/api/v1/enterprise-structure";
const projectCreationRoot = "/api/v1/project-creation-requests";

function queryString(filters: ExplorerFilters) {
  const query = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value) query.set(key, value);
  });
  return query.toString();
}

export const enterpriseStructureApi = {
  configuration: (token: string) => apiFetch<EnterpriseStructureConfiguration>(`${adminRoot}/configuration`, { token }),

  projectConfiguration: (token: string) => apiFetch<ProjectConfiguration>(`${adminRoot}/project-workspace`, { token }),

  physicalConfiguration: (token: string) =>
    apiFetch<PhysicalConfiguration>(`${adminRoot}/physical-workspaces`, { token }),

  previewPhysicalWorkspace: (
    token: string,
    payload: { workspace_type_code: string; parent_id: number; template_id: number | null; minimal_attributes: object }
  ) =>
    apiFetch<PhysicalPreview>(`${adminRoot}/physical-workspaces/preview`, {
      method: "POST",
      token,
      body: JSON.stringify(payload),
    }),

  updatePhysicalComposition: (token: string, parentTypeCode: string, version: number, allowedChildren: string[]) =>
    apiFetch<Record<string, string[]>>(`${adminRoot}/physical-composition/${parentTypeCode}`, {
      method: "PUT",
      token,
      headers: { "If-Match": `"${version}"` },
      body: JSON.stringify({ allowed_children: allowedChildren }),
    }),

  updatePhysicalNumbering: (token: string, typeCode: string, version: number, prefix: string, padding: number) =>
    apiFetch<ConfigurationVersion>(`${adminRoot}/physical-numbering/${typeCode}`, {
      method: "PUT",
      token,
      headers: { "If-Match": `"${version}"` },
      body: JSON.stringify({ prefix, padding, start: 1, no_reuse: true }),
    }),

  updatePhysicalCreationPolicy: (token: string, typeCode: string, version: number, payload: Record<string, unknown>) =>
    apiFetch<ConfigurationVersion>(`${adminRoot}/physical-creation-policies/${typeCode}`, {
      method: "PUT",
      token,
      headers: { "If-Match": `"${version}"` },
      body: JSON.stringify(payload),
    }),

  previewProject: (token: string, parentId: number, templateId: number) =>
    apiFetch<ProjectPreview>(`${adminRoot}/project-workspace/preview`, {
      method: "POST",
      token,
      body: JSON.stringify({ parent_id: parentId, template_id: templateId }),
    }),

  createProjectTemplate: (token: string, payload: ProjectTemplatePayload) =>
    apiFetch<ConfigurationVersion>(`${adminRoot}/project-templates`, {
      method: "POST",
      token,
      body: JSON.stringify(payload),
    }),

  updateProjectTemplate: (
    token: string,
    configurationId: number,
    payload: ProjectTemplatePayload & { expected_version: number }
  ) =>
    apiFetch<ConfigurationVersion>(`${adminRoot}/project-templates/${configurationId}`, {
      method: "PUT",
      token,
      body: JSON.stringify(payload),
    }),

  validateProjectTemplate: (token: string, configurationId: number) =>
    apiFetch<ConfigurationValidation & { content_hash: string }>(
      `${adminRoot}/project-templates/${configurationId}/validate`,
      { method: "POST", token }
    ),

  publishProjectTemplate: (token: string, configurationId: number, expectedHash: string) =>
    apiFetch<ConfigurationVersion>(`${adminRoot}/project-templates/${configurationId}/publish`, {
      method: "POST",
      token,
      body: JSON.stringify({ expected_hash: expectedHash }),
    }),

  cloneProjectTemplate: (token: string, configurationId: number) =>
    apiFetch<ConfigurationVersion>(`${adminRoot}/project-templates/${configurationId}/clone`, {
      method: "POST",
      token,
    }),

  archiveProjectTemplate: (token: string, configurationId: number) =>
    apiFetch<ConfigurationVersion>(`${adminRoot}/project-templates/${configurationId}/archive`, {
      method: "POST",
      token,
    }),

  updateProjectNumbering: (token: string, prefix: string, padding: number) =>
    apiFetch<ConfigurationVersion>(`${adminRoot}/project-numbering`, {
      method: "PUT",
      token,
      body: JSON.stringify({ prefix, padding, start: 1, no_reuse: true }),
    }),

  updateProjectCreationPolicy: (token: string, payload: Record<string, unknown>) =>
    apiFetch<ConfigurationVersion>(`${adminRoot}/project-creation-policy`, {
      method: "PUT",
      token,
      body: JSON.stringify(payload),
    }),

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

  updateCoreRevision: (token: string, releaseId: number, releaseName: string, revisionVersion: number) =>
    apiFetch<CoreRevision>(`${adminRoot}/enterprise-core-releases/${releaseId}`, {
      method: "PATCH",
      token,
      headers: { "If-Match": `"${revisionVersion}"` },
      body: JSON.stringify({ release_name: releaseName }),
    }),

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
    revisionVersion: number,
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
      headers: { "If-Match": `"${revisionVersion}"` },
      body: JSON.stringify(payload),
    }),

  editRevisionWorkspace: (
    token: string,
    releaseId: number,
    workspaceKey: string,
    revisionVersion: number,
    payload: { name?: string; description?: string; responsible_user_id?: number | null; status?: string }
  ) =>
    apiFetch<CoreRevision>(`${adminRoot}/enterprise-core-releases/${releaseId}/workspaces/${workspaceKey}`, {
      method: "PATCH",
      token,
      headers: { "If-Match": `"${revisionVersion}"` },
      body: JSON.stringify(payload),
    }),

  moveRevisionWorkspace: (
    token: string,
    releaseId: number,
    workspaceKey: string,
    newParentKey: string,
    revisionVersion: number
  ) =>
    apiFetch<CoreRevision>(`${adminRoot}/enterprise-core-releases/${releaseId}/workspaces/${workspaceKey}/move`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${revisionVersion}"` },
      body: JSON.stringify({ new_parent_key: newParentKey }),
    }),

  archiveRevisionWorkspace: (token: string, releaseId: number, workspaceKey: string, revisionVersion: number) =>
    apiFetch<CoreRevision>(`${adminRoot}/enterprise-core-releases/${releaseId}/workspaces/${workspaceKey}/archive`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${revisionVersion}"` },
    }),

  setRevisionClassifications: (
    token: string,
    releaseId: number,
    workspaceKey: string,
    revisionVersion: number,
    classifications: RevisionClassification[]
  ) =>
    apiFetch<CoreRevision>(
      `${adminRoot}/enterprise-core-releases/${releaseId}/workspaces/${workspaceKey}/classifications`,
      {
        method: "PUT",
        token,
        headers: { "If-Match": `"${revisionVersion}"` },
        body: JSON.stringify({ classifications }),
      }
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

  projectCreationOptions: (token: string, parentWorkspaceId?: number) =>
    apiFetch<ProjectCreationOptions>(
      `${projectCreationRoot}/options${parentWorkspaceId ? `?parent_workspace_id=${parentWorkspaceId}` : ""}`,
      { token }
    ),

  createProjectRequest: (token: string, payload: ProjectRequestPayload) =>
    apiFetch<ProjectCreationRequest>(projectCreationRoot, {
      method: "POST",
      token,
      body: JSON.stringify(payload),
    }),

  updateProjectRequest: (token: string, requestId: number, version: number, payload: ProjectRequestPayload) =>
    apiFetch<ProjectCreationRequest>(`${projectCreationRoot}/${requestId}`, {
      method: "PUT",
      token,
      headers: { "If-Match": `"${version}"` },
      body: JSON.stringify(payload),
    }),

  projectRequestPreview: (token: string, requestId: number) =>
    apiFetch<ProjectRequestPreview>(`${projectCreationRoot}/${requestId}/preview`, { method: "POST", token }),

  projectRequests: (token: string, reviewQueue = false) =>
    apiFetch<ProjectCreationRequest[]>(`${projectCreationRoot}${reviewQueue ? "?review_queue=true" : ""}`, {
      token,
    }),

  transitionProjectRequest: (
    token: string,
    request: ProjectCreationRequest,
    action: "submit" | "cancel" | "start-review" | "return" | "reject" | "approve",
    reason?: string
  ) =>
    apiFetch<ProjectCreationRequest>(`${projectCreationRoot}/${request.id}/${action}`, {
      method: "POST",
      token,
      headers: { "If-Match": `"${request.revision_version}"` },
      body: reason ? JSON.stringify({ reason }) : undefined,
    }),

  materializeProjectRequest: (token: string, requestId: number) =>
    apiFetch<{
      result: "CREATED" | "ALREADY_CREATED";
      materialized_workspace_id: number;
      project_number: string;
      record_code: string;
      mutation_count: number;
    }>(`${projectCreationRoot}/${requestId}/materialize`, { method: "POST", token }),

  projectWorkspaceOverview: (token: string, workspaceId: number) =>
    apiFetch<ProjectWorkspaceOverview>(`/api/v1/project-workspaces/${workspaceId}/overview`, { token }),

  projectWorkspaces: (token: string, status = "") =>
    apiFetch<ProjectWorkspaceListItem[]>(`/api/v1/project-workspaces${status ? `?status=${status}` : ""}`, { token }),

  projectWorkspaceInitialization: (token: string, workspaceId: number) =>
    apiFetch<ProjectWorkspaceInitialization>(`/api/v1/project-workspaces/${workspaceId}/initialization`, { token }),

  previewProjectWorkspaceInitialization: (token: string, workspaceId: number) =>
    apiFetch<ProjectWorkspaceInitialization>(`/api/v1/project-workspaces/${workspaceId}/initialization/preview`, {
      method: "POST",
      token,
    }),

  transitionProjectWorkspace: (
    token: string,
    workspaceId: number,
    version: number,
    action: "start" | "validate" | "activate"
  ) =>
    apiFetch<ProjectWorkspaceInitialization>(
      action === "activate"
        ? `/api/v1/project-workspaces/${workspaceId}/activate`
        : `/api/v1/project-workspaces/${workspaceId}/initialization/${action}`,
      {
        method: "POST",
        token,
        headers: { "If-Match": `"${version}"` },
      }
    ),
};
