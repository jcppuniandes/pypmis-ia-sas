import { apiFetch, apiFetchFile } from "./client";
import type {
  BimElementProperties,
  BimGeometryCacheArtifact,
  BimGeometryCacheSummary,
  BimModel,
  BimViewerManifest,
} from "../types";

export const bimModels = {
  list: (token: string, projectId: number) =>
    apiFetch<BimModel[]>(`/api/v1/projects/${projectId}/bim-models`, { token }),

  upload: (token: string, projectId: number, file: File) => {
    const body = new FormData();
    body.append("file", file);
    return apiFetch<BimModel>(`/api/v1/projects/${projectId}/bim-models`, {
      method: "POST",
      token,
      body,
    });
  },

  source: (token: string, projectId: number, modelId: number) =>
    apiFetchFile(`/api/v1/projects/${projectId}/bim-models/${modelId}/source`, { token }),

  manifest: (token: string, projectId: number, modelId: number) =>
    apiFetch<BimViewerManifest>(`/api/v1/projects/${projectId}/bim-models/${modelId}/viewer-manifest`, { token }),

  prepareGeometryCache: (token: string, projectId: number, modelId: number) =>
    apiFetch<BimGeometryCacheSummary>(`/api/v1/projects/${projectId}/bim-models/${modelId}/viewer-cache`, {
      method: "POST",
      token,
    }),

  geometryCache: (token: string, projectId: number, modelId: number) =>
    apiFetch<BimGeometryCacheArtifact>(`/api/v1/projects/${projectId}/bim-models/${modelId}/geometry-cache`, {
      token,
    }),

  elementProperties: (token: string, projectId: number, modelId: number, elementKey: string) =>
    apiFetch<BimElementProperties>(
      `/api/v1/projects/${projectId}/bim-models/${modelId}/element-properties?element_key=${encodeURIComponent(elementKey)}`,
      { token },
    ),

  remove: (token: string, projectId: number, modelId: number) =>
    apiFetch<{ status: string; model_id: number }>(`/api/v1/projects/${projectId}/bim-models/${modelId}`, {
      method: "DELETE",
      token,
    }),
};
