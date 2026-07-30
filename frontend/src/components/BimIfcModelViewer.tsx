/* eslint-disable react-refresh/only-export-components --
 * Geometry/measurement helpers are exported for the vitest suite; they move to
 * src/lib in the frontend refactor wave. HMR degradation is acceptable here.
 */
import { type ChangeEvent, type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Box, Compass, Eye, Maximize2, MousePointer2, RotateCcw, Search, ScanLine, Trash2, Upload } from "lucide-react";
import * as THREE from "three";
import webIfcWasmUrl from "web-ifc/web-ifc.wasm?url";
import { bimModels as bimModelsApi } from "../api/bimModels";
import { projects as projectsApi } from "../api/projects";
import type {
  BimElementProperties,
  BimGeometryCacheArtifact,
  BimModel,
  BimViewerManifest,
  ControlledMeasurementApproval,
  QuantityTakeoffLine,
  QuantityTakeoffRun,
} from "../types";

type SectionAxis = "x" | "y" | "z";
type ViewPreset = "front" | "iso" | "right" | "top";
type NavigationMode = "orbit" | "walk";
type InteractionMode = "measure" | "select";
type IfcVisualStyle = "solid" | "wireframe" | "xray";
type IfcReviewFilter = "all" | "apu-assigned" | "apu-pending" | "mapped" | "unmapped";
type IfcRibbonMenu = "appearance" | "file" | "information" | "tools" | "view";
type IfcViewerTone = "ready" | "review";
type IfcClashResult = {
  classA: string;
  classB: string;
  key: string;
  nameA: string;
  nameB: string;
  penetration: number;
  refA: string;
  refB: string;
};
type IfcClashSummary = {
  checkedProducts: number;
  limited: boolean;
  results: IfcClashResult[];
};
type IfcPointMeasurement = {
  distanceMeters: number;
  end: [number, number, number];
  start: [number, number, number];
};
type ViewerCameraCommands = {
  clashes: (toleranceMeters: number) => IfcClashSummary;
  explode: (factor: number) => void;
  fit: () => void;
  filterRefs: (refs: string[]) => void;
  focusRefs: (refs: string[]) => void;
  isolateRefs: (refs: string[]) => void;
  measurement: (active: boolean) => void;
  resetVisibility: () => void;
  section: (active: boolean, axis: SectionAxis, position: number) => void;
  style: (style: IfcVisualStyle) => void;
  view: (preset: ViewPreset) => void;
};

type Props = {
  approvalDisabled?: boolean;
  clearModelDisabled?: boolean;
  informationContent?: ReactNode;
  projectId: number | null;
  lines?: QuantityTakeoffLine[];
  model?: BimModel | undefined;
  onApproveControlledMeasurement?: (payload: ControlledMeasurementApproval) => void | Promise<void>;
  onClearModel?: () => void;
  onLoadSource?: (event: ChangeEvent<HTMLInputElement>) => void;
  ribbonHostId?: string;
  run?: QuantityTakeoffRun | undefined;
  sourceLoadDisabled?: boolean;
  sourceLoading?: boolean;
  token: string;
};

function IfcRibbonPortal({ children, hostId }: { children: ReactNode; hostId?: string }) {
  const host = hostId && typeof document !== "undefined" ? document.getElementById(hostId) : null;
  return host ? createPortal(children, host) : children;
}

type IfcTreeGroup = {
  apuCount: number;
  count: number;
  id: string;
  ifcClass: string;
  lineIds: number[];
  mappedCount: number;
  quantity: number;
  representative: QuantityTakeoffLine;
  storey: string;
  traceRefs: string[];
  unit: string;
};

export type IfcObjectTreeNode = {
  apuCount: number;
  children: IfcObjectTreeNode[];
  count: number;
  groupId?: string;
  id: string;
  kind: "building" | "class" | "model" | "object" | "project" | "site" | "storey";
  label: string;
  lineIds: number[];
  mappedCount: number;
  reference?: string;
  representative?: QuantityTakeoffLine;
  traceRefs: string[];
};

type SelectedIfcElement = {
  dimensions: IfcElementDimensions | null;
  expressId: number | null;
  globalId: string;
  ifcClass: string;
  name: string;
  realQuantities: RealGeometryQuantities | null;
};

type IfcElementDimensions = {
  x: number;
  y: number;
  z: number;
};

type RealGeometryEstimate = {
  confidence: "Media";
  explanation: string;
  measurementRule: "GeometryMeshArea" | "GeometryMeshLength" | "GeometryMeshVolume";
  quantity: number;
  source: "Geometria triangulada IFC";
  unit: "m" | "m2" | "m3";
};

type RealGeometryQuantities = {
  area: RealGeometryEstimate;
  length: RealGeometryEstimate;
  volume: RealGeometryEstimate;
};

type IfcMeshData = {
  expressId?: number | null;
  globalId?: string;
  ifcClass?: string;
  name?: string;
};

type IfcRenderDiagnostics = {
  conversionErrors: number;
  emptyGeometries: number;
  fileSizeBytes: number;
  invalidGeometryRefs: number;
  invalidMemoryRefs: number;
  limitReached: boolean;
  loadMs: number | null;
  meshesRendered: number;
  productsScanned: number;
  trianglesRendered: number;
};

const IFC_BROWSER_CACHE_THRESHOLD_BYTES = 100 * 1024 * 1024;
const IFC_BROWSER_MODERATE_THRESHOLD_BYTES = 25 * 1024 * 1024;
const IFC_BROWSER_MESH_LIMIT = 15_000;
const IFC_BROWSER_TRIANGLE_LIMIT = 3_000_000;

function emptyIfcRenderDiagnostics(fileSizeBytes = 0): IfcRenderDiagnostics {
  return {
    conversionErrors: 0,
    emptyGeometries: 0,
    fileSizeBytes,
    invalidGeometryRefs: 0,
    invalidMemoryRefs: 0,
    limitReached: false,
    loadMs: null,
    meshesRendered: 0,
    productsScanned: 0,
    trianglesRendered: 0,
  };
}

function compact(value: string | null | undefined) {
  return value?.trim() ?? "";
}

function unique(values: string[]) {
  return Array.from(new Set(values.map(compact).filter(Boolean)));
}

function constructiveLabel(line: QuantityTakeoffLine | undefined) {
  if (!line) return "Elemento IFC no enlazado a cantidad";
  const category = /^Ifc[A-Z]/.test(compact(line.category)) ? "" : line.category;
  return unique([category, line.family, line.type_name, line.instance_name]).slice(0, 3).join(" / ") || line.ifc_class;
}

function formatNumber(value: number) {
  return value.toLocaleString("en-US", {
    maximumFractionDigits: 2,
    minimumFractionDigits: Number.isInteger(value) ? 0 : 2,
  });
}

function formatFileSize(value: number | undefined) {
  if (!value || !Number.isFinite(value)) return "Sin archivo";
  if (value >= 1024 * 1024) return `${(value / (1024 * 1024)).toFixed(2)} MB`;
  if (value >= 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${value} bytes`;
}

function browserCapacityForIfc(sourceSizeBytes: number | undefined): {
  detail: string;
  label: string;
  tone: IfcViewerTone;
} {
  if (!sourceSizeBytes || !Number.isFinite(sourceSizeBytes)) {
    return {
      detail: "Carga un IFC para evaluar si conviene render directo o cache backend.",
      label: "Sin archivo",
      tone: "review",
    };
  }
  if (sourceSizeBytes > IFC_BROWSER_CACHE_THRESHOLD_BYTES) {
    return {
      detail: "Modelo pesado: preprocesar geometria y servir cache backend antes de uso comercial continuo.",
      label: "Requiere cache backend",
      tone: "review",
    };
  }
  if (sourceSizeBytes > IFC_BROWSER_MODERATE_THRESHOLD_BYTES) {
    return {
      detail: "Modelo mediano: render directo permitido, con monitoreo de memoria y tiempo de carga.",
      label: "Modelo moderado",
      tone: "review",
    };
  }
  return {
    detail: "Archivo IFC pequeño: apto para render directo en navegador.",
    label: "Modelo liviano",
    tone: "ready",
  };
}

function formatIfcRenderDiagnostics(diagnostics: IfcRenderDiagnostics) {
  const skipped =
    diagnostics.invalidGeometryRefs +
    diagnostics.invalidMemoryRefs +
    diagnostics.emptyGeometries +
    diagnostics.conversionErrors;
  if (!diagnostics.productsScanned && !diagnostics.meshesRendered) return "Pendiente de conversion web-ifc.";
  const parts = [
    `${diagnostics.trianglesRendered.toLocaleString()} triangulo(s)`,
    skipped ? `${skipped.toLocaleString()} geometria(s) omitida(s)` : "sin omisiones criticas",
    diagnostics.loadMs !== null ? `${Math.round(diagnostics.loadMs).toLocaleString()} ms` : "",
  ].filter(Boolean);
  return diagnostics.limitReached ? `${parts.join(" / ")} / render parcial por limite navegador` : parts.join(" / ");
}

function formatQuantity(line: QuantityTakeoffLine | undefined) {
  if (!line || !Number.isFinite(line.quantity)) return "Cantidad pendiente";
  return `${formatNumber(line.quantity)} ${compact(line.unit) || "unidad pendiente"}`;
}

function formatGeometryEstimate(estimate: RealGeometryEstimate | null) {
  if (!estimate) return "No calculada; falta unidad geometrica confiable";
  return `${formatNumber(estimate.quantity)} ${estimate.unit} / ${estimate.measurementRule}`;
}

function modelUnitLabel(units: string | undefined) {
  const normalized = compact(units).toLowerCase();
  if (normalized.includes("millimeter") || normalized === "mm") return "mm";
  if (normalized.includes("meter") || normalized === "m") return "m";
  if (normalized.includes("centimeter") || normalized === "cm") return "cm";
  return compact(units) || "unidades IFC";
}

function formatDimensions(dimensions: IfcElementDimensions | null | undefined, units: string | undefined) {
  if (!dimensions) return "Selecciona geometria para ver L x A x H";
  return `${formatNumber(dimensions.x)} x ${formatNumber(dimensions.y)} x ${formatNumber(dimensions.z)} ${modelUnitLabel(units)}`;
}

export function formatRealGeometryDimensions(
  dimensions: IfcElementDimensions | null | undefined,
  units: string | undefined
) {
  if (!dimensions) return "Selecciona geometria para ver L x A x H";
  const declaredScale = geometryUnitScaleToMeters(units);
  if (!declaredScale) return formatDimensions(dimensions, units);
  const maxDimension = Math.max(dimensions.x, dimensions.y, dimensions.z);
  const scale = geometryCoordinateScaleToMeters(declaredScale, maxDimension);
  return `${formatNumber(dimensions.x * scale)} x ${formatNumber(dimensions.y * scale)} x ${formatNumber(dimensions.z * scale)} m`;
}

function modelIdentityText(identity: Record<string, unknown>, key: string, fallback: string) {
  const value = identity[key];
  return typeof value === "string" && compact(value) ? value : fallback;
}

function modelGeoreferenceLabel(identity: Record<string, unknown>) {
  const details = modelGeoreferenceDetails(identity);
  const coordinates = details.find((item) => item.label === "Lat / Long")?.value ?? "";
  const crs = details.find((item) => item.label === "CRS")?.value ?? "";
  const label = unique([coordinates, crs]).join(" / ");
  return label ? `Geo ${label}` : "";
}

export function modelGeoreferenceDetails(identity: Record<string, unknown>) {
  const rawGeoref = identity.georeferencing;
  if (!rawGeoref || typeof rawGeoref !== "object" || Array.isArray(rawGeoref)) return [];
  const georef = rawGeoref as Record<string, unknown>;
  const latitude = typeof georef.latitude_decimal === "number" ? georef.latitude_decimal : Number.NaN;
  const longitude = typeof georef.longitude_decimal === "number" ? georef.longitude_decimal : Number.NaN;
  const elevation = typeof georef.elevation === "number" ? georef.elevation : Number.NaN;
  const crs = typeof georef.projected_crs === "string" ? compact(georef.projected_crs) : "";
  const mapConversion =
    georef.map_conversion && typeof georef.map_conversion === "object" && !Array.isArray(georef.map_conversion)
      ? (georef.map_conversion as Record<string, unknown>)
      : {};
  const eastings = typeof mapConversion.eastings === "number" ? mapConversion.eastings : Number.NaN;
  const northings = typeof mapConversion.northings === "number" ? mapConversion.northings : Number.NaN;
  const orthogonalHeight =
    typeof mapConversion.orthogonal_height === "number" ? mapConversion.orthogonal_height : Number.NaN;
  const scale = typeof mapConversion.scale === "number" ? mapConversion.scale : Number.NaN;
  return [
    Number.isFinite(latitude) && Number.isFinite(longitude)
      ? { label: "Lat / Long", value: `${latitude.toFixed(6)}, ${longitude.toFixed(6)}` }
      : null,
    crs ? { label: "CRS", value: crs } : null,
    Number.isFinite(eastings) && Number.isFinite(northings)
      ? { label: "Este / Norte", value: `${formatNumber(eastings)}, ${formatNumber(northings)}` }
      : null,
    Number.isFinite(elevation) || Number.isFinite(orthogonalHeight)
      ? {
          label: "Altura",
          value: `${formatNumber(Number.isFinite(orthogonalHeight) ? orthogonalHeight : elevation)} m`,
        }
      : null,
    Number.isFinite(scale) ? { label: "Escala mapa", value: formatNumber(scale) } : null,
  ].filter((item): item is { label: string; value: string } => Boolean(item));
}

function traceRefsForLine(line: QuantityTakeoffLine) {
  return unique([line.element_guid, line.element_id, line.source_row_id]);
}

function hasApuAssignment(line: QuantityTakeoffLine) {
  const assignment = line.raw_data?.budget_item_assignment;
  return Boolean(
    assignment &&
    typeof assignment === "object" &&
    !Array.isArray(assignment) &&
    Object.keys(assignment as Record<string, unknown>).length
  );
}

function lineMatchesReviewFilter(line: QuantityTakeoffLine, filter: IfcReviewFilter) {
  if (filter === "mapped") return line.mapping_status === "mapped";
  if (filter === "unmapped") return line.mapping_status !== "mapped";
  if (filter === "apu-assigned") return hasApuAssignment(line);
  if (filter === "apu-pending") return !hasApuAssignment(line);
  return true;
}

function lineSearchBasis(line: QuantityTakeoffLine) {
  const assignment =
    line.raw_data?.budget_item_assignment &&
    typeof line.raw_data.budget_item_assignment === "object" &&
    !Array.isArray(line.raw_data.budget_item_assignment)
      ? (line.raw_data.budget_item_assignment as Record<string, unknown>)
      : {};
  return [
    line.project_name,
    line.site_name,
    line.building_name,
    line.storey,
    line.zone_name,
    line.system_name,
    line.ifc_class,
    line.category,
    line.family,
    line.type_name,
    line.instance_name,
    line.element_guid,
    line.element_id,
    line.measurement_rule,
    line.wbs_code,
    line.cbs_code,
    line.fbs_code,
    line.package_code,
    assignment.cost_item_code,
    assignment.cost_item_name,
    assignment.source_key,
  ]
    .filter((value) => value !== null && value !== undefined)
    .join(" ")
    .toLowerCase();
}

function lineMatchesIfcElement(line: QuantityTakeoffLine, element: SelectedIfcElement) {
  const expressRef = element.expressId ? `#${element.expressId}` : "";
  return Boolean(
    (element.globalId && traceRefsForLine(line).includes(element.globalId)) ||
    (expressRef && traceRefsForLine(line).includes(expressRef)) ||
    (element.expressId && traceRefsForLine(line).includes(String(element.expressId)))
  );
}

function selectedIfcPropertyLookupKey(line: QuantityTakeoffLine | undefined, element: SelectedIfcElement | null) {
  if (element?.globalId) return element.globalId;
  if (line?.element_guid) return line.element_guid;
  if (element?.expressId) return `#${element.expressId}`;
  if (line?.element_id) return line.element_id;
  const sourceRef = compact(line?.source_row_id);
  const match = sourceRef.match(/#\d+/);
  return match?.[0] ?? "";
}

function manifestStrategyLabel(manifest: BimViewerManifest | null) {
  if (!manifest) return "Manifiesto pendiente";
  if (manifest.geometry_strategy === "backend_cache") return "Cache backend listo";
  if (manifest.geometry_strategy === "backend_cache_required") return "Cache backend requerido";
  if (manifest.geometry_strategy === "browser_limited_cache_recommended") return "Cache backend recomendado";
  return "Directo navegador";
}

function manifestPropertySummary(manifest: BimViewerManifest | null) {
  if (!manifest) return "Sin manifiesto de revision.";
  const index = manifest.property_index;
  if (!index) return "Manifiesto geometrico sin indice de propiedades publicado.";
  return `${index.scan_status} / ${index.indexed_products.toLocaleString()} elementos / ${index.property_sets} Pset / ${index.quantity_sets} Qto`;
}

function elementPropertiesStatus(properties: BimElementProperties | null, status: string) {
  if (status) return status;
  if (!properties) return "Selecciona un elemento para consultar propiedades IFC publicadas.";
  if (!properties.found) return "El elemento seleccionado no aparece en el indice IFC cacheado.";
  return `${properties.property_sets.length} Pset / ${properties.quantities.length} Qto / ${properties.materials.length} material(es)`;
}

function buildIfcTreeGroups(lines: QuantityTakeoffLine[]) {
  const groups = new Map<string, QuantityTakeoffLine[]>();
  for (const line of lines) {
    const storey = compact(line.storey) || "Nivel pendiente";
    const ifcClass = compact(line.ifc_class) || compact(line.category) || "Clase IFC pendiente";
    const key = `${storey}|${ifcClass}`;
    groups.set(key, [...(groups.get(key) ?? []), line]);
  }
  return Array.from(groups.entries())
    .map<IfcTreeGroup>(([key, groupLines]) => {
      const [storey, ifcClass] = key.split("|");
      const representative = groupLines[0];
      return {
        apuCount: groupLines.filter(hasApuAssignment).length,
        count: groupLines.length,
        id: key,
        ifcClass,
        lineIds: groupLines.map((line) => line.id),
        mappedCount: groupLines.filter((line) => line.mapping_status === "mapped").length,
        quantity: groupLines.reduce((total, line) => total + (Number.isFinite(line.quantity) ? line.quantity : 0), 0),
        representative,
        storey,
        traceRefs: unique(groupLines.flatMap(traceRefsForLine)),
        unit: compact(representative.unit) || "uom",
      };
    })
    .sort((left, right) => `${left.storey}|${left.ifcClass}`.localeCompare(`${right.storey}|${right.ifcClass}`));
}

function ifcObjectKey(line: QuantityTakeoffLine) {
  const sourceObjectRef = compact(line.source_row_id).split(":")[0];
  return compact(line.element_guid) || compact(line.element_id) || sourceObjectRef || `line-${line.id}`;
}

function ifcObjectLabel(line: QuantityTakeoffLine) {
  return constructiveLabel(line).split(" / ").join(":");
}

function countIfcObjects(lines: QuantityTakeoffLine[]) {
  return new Set(lines.map(ifcObjectKey)).size;
}

export function buildIfcObjectTree(
  lines: QuantityTakeoffLine[],
  sourceName = "Modelo IFC",
  modelIdentity: Record<string, unknown> = {}
): IfcObjectTreeNode {
  const levels: Array<{
    fallback: string;
    kind: Exclude<IfcObjectTreeNode["kind"], "model" | "object">;
    value: (line: QuantityTakeoffLine) => string;
  }> = [
    {
      fallback: modelIdentityText(modelIdentity, "project_name", "IfcProject"),
      kind: "project",
      value: (line) => compact(line.project_name),
    },
    {
      fallback: modelIdentityText(modelIdentity, "site_name", "Default"),
      kind: "site",
      value: (line) => compact(line.site_name),
    },
    {
      fallback: modelIdentityText(modelIdentity, "building_name", "IfcBuilding"),
      kind: "building",
      value: (line) => compact(line.building_name),
    },
    {
      fallback: "Nivel pendiente",
      kind: "storey",
      value: (line) => compact(line.storey),
    },
    {
      fallback: "Clase IFC pendiente",
      kind: "class",
      value: (line) => compact(line.ifc_class) || compact(line.category),
    },
  ];

  const summarizeNode = (
    id: string,
    kind: IfcObjectTreeNode["kind"],
    label: string,
    nodeLines: QuantityTakeoffLine[],
    children: IfcObjectTreeNode[],
    extra: Partial<IfcObjectTreeNode> = {}
  ): IfcObjectTreeNode => ({
    apuCount: nodeLines.filter(hasApuAssignment).length,
    children,
    count: countIfcObjects(nodeLines),
    id,
    kind,
    label,
    lineIds: nodeLines.map((line) => line.id),
    mappedCount: nodeLines.filter((line) => line.mapping_status === "mapped").length,
    traceRefs: unique(nodeLines.flatMap(traceRefsForLine)),
    ...extra,
  });

  const buildObjects = (nodeLines: QuantityTakeoffLine[], path: string[]): IfcObjectTreeNode[] => {
    const objects = new Map<string, QuantityTakeoffLine[]>();
    for (const line of nodeLines) {
      const key = ifcObjectKey(line);
      objects.set(key, [...(objects.get(key) ?? []), line]);
    }
    return Array.from(objects.entries())
      .map(([reference, objectLines]) => {
        const representative = objectLines[0];
        return summarizeNode(
          [...path, `object:${reference}`].join("\u001f"),
          "object",
          ifcObjectLabel(representative),
          objectLines,
          [],
          { reference, representative }
        );
      })
      .sort((left, right) => `${left.label}|${left.reference}`.localeCompare(`${right.label}|${right.reference}`));
  };

  const buildLevel = (nodeLines: QuantityTakeoffLine[], levelIndex: number, path: string[]): IfcObjectTreeNode[] => {
    if (levelIndex >= levels.length) return buildObjects(nodeLines, path);
    const level = levels[levelIndex];
    const groups = new Map<string, QuantityTakeoffLine[]>();
    for (const line of nodeLines) {
      const label = level.value(line) || level.fallback;
      groups.set(label, [...(groups.get(label) ?? []), line]);
    }
    return Array.from(groups.entries())
      .map(([label, groupLines]) => {
        const id = [...path, `${level.kind}:${label}`].join("\u001f");
        const children = buildLevel(groupLines, levelIndex + 1, [...path, `${level.kind}:${label}`]);
        const groupId =
          level.kind === "class" ? `${compact(groupLines[0]?.storey) || "Nivel pendiente"}|${label}` : undefined;
        return summarizeNode(id, level.kind, label, groupLines, children, { groupId });
      })
      .sort((left, right) => left.label.localeCompare(right.label));
  };

  const rootLabel = compact(sourceName) || "Modelo IFC";
  return summarizeNode(`model:${rootLabel}`, "model", rootLabel, lines, buildLevel(lines, 0, [`model:${rootLabel}`]));
}

function readIfcText(value: unknown) {
  if (typeof value === "string") return value;
  if (value && typeof value === "object" && "value" in value) {
    const nested = (value as { value?: unknown }).value;
    return typeof nested === "string" || typeof nested === "number" ? String(nested) : "";
  }
  return "";
}

export function detectIfcLengthUnitsFromText(text: string) {
  const match = text.match(/IFCSIUNIT\s*\(\s*\*?\s*,\s*\.LENGTHUNIT\.\s*,\s*(?:\.([A-Z]+)\.|\$)\s*,\s*\.([A-Z]+)\./i);
  if (!match) return "";
  const prefix = compact(match[1]).toUpperCase();
  const unitName = compact(match[2]).toUpperCase();
  if (unitName !== "METRE" && unitName !== "METER") return "";
  if (prefix === "MILLI") return "millimeters";
  if (prefix === "CENTI") return "centimeters";
  return "meters";
}

function reliableModelUnits(units: string | undefined) {
  const normalized = compact(units);
  return /^lengthunit$/i.test(normalized) ? "" : normalized;
}

function geometryUnitScaleToMeters(units: string | undefined) {
  const normalized = compact(units)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "");
  if (!normalized) return null;
  if (["mm", "milli", "millimeter", "millimeters", "millimetre", "millimetres"].includes(normalized)) return 0.001;
  if (["cm", "centi", "centimeter", "centimeters", "centimetre", "centimetres"].includes(normalized)) return 0.01;
  if (["m", "meter", "meters", "metre", "metres"].includes(normalized)) return 1;
  if (normalized.includes("millimeter") || normalized.includes("millimetre")) return 0.001;
  if (normalized.includes("centimeter") || normalized.includes("centimetre")) return 0.01;
  if (normalized.includes("meter") || normalized.includes("metre")) return 1;
  return null;
}

function geometryCoordinateScaleToMeters(declaredScale: number, maxDimension: number) {
  if (declaredScale === 0.001 && maxDimension < 100) return 1;
  if (declaredScale === 0.01 && maxDimension < 100) return 1;
  return declaredScale;
}

function roundGeometryQuantity(value: number) {
  return Number(value.toFixed(3));
}

function vertexFromGeometry(
  position: THREE.BufferAttribute | THREE.InterleavedBufferAttribute,
  index: THREE.BufferAttribute | null,
  triangleIndex: number,
  mesh: THREE.Mesh,
  scale: number,
  origin: THREE.Vector3,
  target: THREE.Vector3
) {
  const vertexIndex = index ? index.getX(triangleIndex) : triangleIndex;
  target.fromBufferAttribute(position, vertexIndex);
  target.applyMatrix4(mesh.matrixWorld);
  target.multiplyScalar(scale);
  target.sub(origin);
  return target;
}

export function calculateRealGeometryQuantities(
  meshes: THREE.Mesh[],
  units: string | undefined
): RealGeometryQuantities | null {
  const declaredScale = geometryUnitScaleToMeters(units);
  if (!declaredScale || !meshes.length) return null;

  const worldBox = new THREE.Box3();
  for (const mesh of meshes) {
    mesh.updateMatrixWorld(true);
    worldBox.union(new THREE.Box3().setFromObject(mesh));
  }
  if (worldBox.isEmpty()) return null;

  const size = worldBox.getSize(new THREE.Vector3());
  const scale = geometryCoordinateScaleToMeters(declaredScale, Math.max(size.x, size.y, size.z));
  const origin = worldBox.getCenter(new THREE.Vector3()).multiplyScalar(scale);
  let surfaceArea = 0;
  let signedVolume = 0;
  const a = new THREE.Vector3();
  const b = new THREE.Vector3();
  const c = new THREE.Vector3();
  const cross = new THREE.Vector3();

  for (const mesh of meshes) {
    const geometry = mesh.geometry;
    const position = geometry.getAttribute("position");
    if (!position) continue;
    const index = geometry.getIndex();
    const vertexCount = index ? index.count : position.count;
    for (let vertexOffset = 0; vertexOffset + 2 < vertexCount; vertexOffset += 3) {
      vertexFromGeometry(position, index, vertexOffset, mesh, scale, origin, a);
      vertexFromGeometry(position, index, vertexOffset + 1, mesh, scale, origin, b);
      vertexFromGeometry(position, index, vertexOffset + 2, mesh, scale, origin, c);
      surfaceArea += cross.subVectors(b, a).cross(c.clone().sub(a)).length() / 2;
      signedVolume += a.dot(b.clone().cross(c)) / 6;
    }
  }

  const length = Math.max(size.x, size.y, size.z) * scale;
  return {
    area: {
      confidence: "Media",
      explanation: "Area real calculada sumando los triangulos de la malla IFC seleccionada.",
      measurementRule: "GeometryMeshArea",
      quantity: roundGeometryQuantity(surfaceArea),
      source: "Geometria triangulada IFC",
      unit: "m2",
    },
    length: {
      confidence: "Media",
      explanation: "Longitud real calculada con la mayor dimension del elemento IFC seleccionado.",
      measurementRule: "GeometryMeshLength",
      quantity: roundGeometryQuantity(length),
      source: "Geometria triangulada IFC",
      unit: "m",
    },
    volume: {
      confidence: "Media",
      explanation: "Volumen real calculado con la malla triangulada IFC; es confiable cuando la malla es cerrada.",
      measurementRule: "GeometryMeshVolume",
      quantity: roundGeometryQuantity(Math.abs(signedVolume)),
      source: "Geometria triangulada IFC",
      unit: "m3",
    },
  };
}

export function primaryRealGeometryEstimate(
  ifcClass: string,
  quantities: RealGeometryQuantities | null | undefined
): RealGeometryEstimate | null {
  if (!quantities) return null;
  const normalizedClass = compact(ifcClass)
    .replace(/[^A-Za-z0-9]/g, "")
    .toUpperCase();
  const areaClasses = new Set([
    "IFCCURTAINWALL",
    "IFCPLATE",
    "IFCROOF",
    "IFCSLAB",
    "IFCSPACE",
    "IFCWALL",
    "IFCWALLSTANDARDCASE",
  ]);
  const volumeClasses = new Set(["IFCBEAM", "IFCCOLUMN", "IFCFOOTING", "IFCPILE", "IFCSTAIR"]);
  const lengthClasses = new Set(["IFCFLOWSEGMENT", "IFCMEMBER", "IFCPIPESEGMENT", "IFCRAILING"]);
  if (areaClasses.has(normalizedClass)) return quantities.area;
  if (volumeClasses.has(normalizedClass)) return quantities.volume;
  if (lengthClasses.has(normalizedClass)) return quantities.length;
  return quantities.length;
}

export function buildControlledMeasurementPayloadFromRealGeometry(
  line: QuantityTakeoffLine,
  estimate: RealGeometryEstimate | null,
  traceReference: string
): ControlledMeasurementApproval | null {
  if (!estimate || !Number.isFinite(estimate.quantity) || estimate.quantity <= 0) return null;
  return {
    line_ids: [line.id],
    measurement_rule: estimate.measurementRule,
    note: `Medicion geometrica real desde malla IFC para ${compact(traceReference) || line.element_guid || line.element_id}`,
    quantity: estimate.quantity,
    source: estimate.source,
    unit: estimate.unit,
  };
}

function colorKey(color: { x: number; y: number; z: number; w: number }) {
  return [color.x, color.y, color.z, color.w].map((value) => value.toFixed(3)).join("|");
}

function materialForColor(
  cache: Map<string, THREE.MeshStandardMaterial>,
  color: { x: number; y: number; z: number; w: number }
) {
  const key = colorKey(color);
  const cached = cache.get(key);
  if (cached) return cached;
  const material = new THREE.MeshStandardMaterial({
    color: new THREE.Color(Math.max(0.08, color.x), Math.max(0.08, color.y), Math.max(0.08, color.z)),
    metalness: 0.02,
    opacity: Math.max(0.55, Math.min(1, color.w || 1)),
    roughness: 0.68,
    side: THREE.DoubleSide,
    transparent: color.w < 0.999,
  });
  cache.set(key, material);
  return material;
}

function colorForBackendCacheClass(ifcClass: string) {
  const normalized = compact(ifcClass) || "IfcProduct";
  let hash = 0;
  for (let index = 0; index < normalized.length; index += 1) {
    hash = (hash * 31 + normalized.charCodeAt(index)) % 360;
  }
  return new THREE.Color().setHSL(hash / 360, 0.42, 0.56);
}

function materialForBackendCacheProduct(cache: Map<string, THREE.MeshStandardMaterial>, ifcClass: string) {
  const key = `backend-cache:${compact(ifcClass) || "IfcProduct"}`;
  const cached = cache.get(key);
  if (cached) return cached;
  const material = new THREE.MeshStandardMaterial({
    color: colorForBackendCacheClass(ifcClass),
    metalness: 0.02,
    roughness: 0.62,
    side: THREE.DoubleSide,
  });
  cache.set(key, material);
  return material;
}

export function buildBackendCacheGeometryMeshes(
  artifact: BimGeometryCacheArtifact,
  materialCache: Map<string, THREE.MeshStandardMaterial>
) {
  const diagnostics = emptyIfcRenderDiagnostics(0);
  const meshes: THREE.Mesh[] = [];
  const bounds: THREE.Box3[] = [];
  diagnostics.productsScanned = artifact.products.length;
  for (const product of artifact.products) {
    const vertices = product.mesh?.vertices ?? [];
    const indices = product.mesh?.indices ?? [];
    if (!vertices.length || !indices.length || vertices.length % 3 !== 0 || indices.length % 3 !== 0) {
      diagnostics.emptyGeometries += 1;
      continue;
    }
    const geometry = new THREE.BufferGeometry();
    geometry.setAttribute("position", new THREE.BufferAttribute(new Float32Array(vertices), 3));
    geometry.setIndex(new THREE.BufferAttribute(new Uint32Array(indices), 1));
    geometry.computeVertexNormals();
    geometry.computeBoundingBox();
    if (geometry.boundingBox) bounds.push(geometry.boundingBox.clone());
    const mesh = new THREE.Mesh(geometry, materialForBackendCacheProduct(materialCache, product.ifc_class));
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    mesh.userData.ifc = {
      expressId: product.express_id,
      globalId: product.global_id,
      ifcClass: product.ifc_class,
      name: product.name,
    };
    meshes.push(mesh);
    diagnostics.meshesRendered += 1;
    diagnostics.trianglesRendered += indices.length / 3;
  }
  return { bounds, diagnostics, meshes };
}

function selectionKeyForIfcData(data: IfcMeshData | undefined) {
  if (!data) return "";
  if (compact(data.globalId)) return compact(data.globalId);
  return data.expressId ? `#${data.expressId}` : "";
}

function selectionKeysForIfcData(data: IfcMeshData | undefined) {
  if (!data) return [];
  return unique([
    compact(data.globalId),
    data.expressId ? `#${data.expressId}` : "",
    data.expressId ? String(data.expressId) : "",
  ]);
}

export function measureIfcPointDistance(
  start: THREE.Vector3,
  end: THREE.Vector3,
  units: string | undefined,
  modelMaxDimension: number
) {
  const declaredScale = geometryUnitScaleToMeters(units) ?? 1;
  const scale = geometryCoordinateScaleToMeters(declaredScale, modelMaxDimension);
  return roundGeometryQuantity(start.distanceTo(end) * scale);
}

export function applyIfcVisualStyle(materials: Iterable<THREE.Material>, style: IfcVisualStyle) {
  for (const material of materials) {
    const baseOpacity =
      typeof material.userData.openIfcBaseOpacity === "number"
        ? material.userData.openIfcBaseOpacity
        : material.opacity;
    material.userData.openIfcBaseOpacity = baseOpacity;
    material.transparent = style === "xray" || baseOpacity < 1;
    material.opacity = style === "xray" ? Math.min(baseOpacity, 0.24) : baseOpacity;
    material.depthWrite = style !== "xray";
    if (material instanceof THREE.MeshStandardMaterial) {
      material.wireframe = style === "wireframe";
    }
    material.needsUpdate = true;
  }
}

export function detectIfcBoxClashes(
  meshes: THREE.Mesh[],
  units: string | undefined,
  toleranceMeters: number,
  maxResults = 120
): IfcClashSummary {
  const candidates = new Map<string, { box: THREE.Box3; data: IfcMeshData; key: string; meshes: THREE.Mesh[] }>();
  const modelBox = new THREE.Box3();
  for (const mesh of meshes) {
    if (!mesh.visible) continue;
    mesh.updateMatrixWorld(true);
    const box = new THREE.Box3().setFromObject(mesh);
    if (box.isEmpty()) continue;
    modelBox.union(box);
    const data = mesh.userData.ifc as IfcMeshData | undefined;
    const key = selectionKeyForIfcData(data) || mesh.uuid;
    const candidate = candidates.get(key);
    if (candidate) {
      candidate.box.union(box);
      candidate.meshes.push(mesh);
    } else {
      candidates.set(key, { box: box.clone(), data: data ?? {}, key, meshes: [mesh] });
    }
  }
  const modelMaxDimension = modelBox.isEmpty() ? 1 : Math.max(...modelBox.getSize(new THREE.Vector3()).toArray(), 1);
  const declaredScale = geometryUnitScaleToMeters(units) ?? 1;
  const scale = geometryCoordinateScaleToMeters(declaredScale, modelMaxDimension);
  const toleranceInCoordinates = Math.max(0, toleranceMeters) / Math.max(scale, Number.EPSILON);
  const ordered = Array.from(candidates.values()).sort((left, right) => left.box.min.x - right.box.min.x);
  const results: IfcClashResult[] = [];
  let limited = false;

  outer: for (let leftIndex = 0; leftIndex < ordered.length; leftIndex += 1) {
    const left = ordered[leftIndex];
    for (let rightIndex = leftIndex + 1; rightIndex < ordered.length; rightIndex += 1) {
      const right = ordered[rightIndex];
      if (right.box.min.x >= left.box.max.x - toleranceInCoordinates) break;
      const overlapX = Math.min(left.box.max.x, right.box.max.x) - Math.max(left.box.min.x, right.box.min.x);
      const overlapY = Math.min(left.box.max.y, right.box.max.y) - Math.max(left.box.min.y, right.box.min.y);
      const overlapZ = Math.min(left.box.max.z, right.box.max.z) - Math.max(left.box.min.z, right.box.min.z);
      const penetrationCoordinates = Math.min(overlapX, overlapY, overlapZ);
      if (
        overlapX <= toleranceInCoordinates ||
        overlapY <= toleranceInCoordinates ||
        overlapZ <= toleranceInCoordinates
      ) {
        continue;
      }
      const refA = selectionKeyForIfcData(left.data);
      const refB = selectionKeyForIfcData(right.data);
      if (!refA || !refB || refA === refB) continue;
      results.push({
        classA: compact(left.data.ifcClass) || "IfcProduct",
        classB: compact(right.data.ifcClass) || "IfcProduct",
        key: `${left.key}|${right.key}`,
        nameA: compact(left.data.name) || refA,
        nameB: compact(right.data.name) || refB,
        penetration: roundGeometryQuantity(penetrationCoordinates * scale),
        refA,
        refB,
      });
      if (results.length >= maxResults) {
        limited = true;
        break outer;
      }
    }
  }
  return { checkedProducts: ordered.length, limited, results };
}

export function isValidIfcExpressId(value: unknown) {
  return typeof value === "number" && Number.isInteger(value) && value > 0;
}

export function isValidIfcMemoryRef(value: unknown, size: unknown) {
  return (
    typeof value === "number" &&
    Number.isInteger(value) &&
    value >= 0 &&
    typeof size === "number" &&
    Number.isInteger(size) &&
    size > 0
  );
}

export function friendlyIfcRenderStatus(error: unknown) {
  const message = error instanceof Error ? error.message : String(error ?? "");
  if (/unsigned int|valid range|number\s+"?-1"?|outside the valid range/i.test(message)) {
    return "IFC registrado. web-ifc no pudo convertir algunas mallas por referencias geometricas invalidas; se conservan metadatos, georreferenciacion y cantidades disponibles.";
  }
  if (/memory|out of bounds|allocation|cannot enlarge|abort|oom/i.test(message)) {
    return "IFC registrado. La memoria del navegador no fue suficiente para convertir toda la geometria; conserva metadatos y cantidades, y recomienda cache backend para visualizacion comercial.";
  }
  return "IFC registrado. No se encontro geometria renderizable compatible; se conservan metadatos, georreferenciacion y cantidades disponibles.";
}

function closestProjectedIfcMesh(meshes: THREE.Mesh[], camera: THREE.Camera, pointer: THREE.Vector2) {
  const center = new THREE.Vector3();
  const projected = new THREE.Vector3();
  let selected: THREE.Mesh | undefined;
  let selectedDistance = Number.POSITIVE_INFINITY;
  for (const mesh of meshes) {
    new THREE.Box3().setFromObject(mesh).getCenter(center);
    projected.copy(center).project(camera);
    if (projected.z < -1 || projected.z > 1) continue;
    const distance = Math.hypot(projected.x - pointer.x, projected.y - pointer.y);
    if (distance < selectedDistance) {
      selectedDistance = distance;
      selected = mesh;
    }
  }
  return selected;
}

function createIfcSelectedMaterial() {
  const material = new THREE.MeshStandardMaterial({
    color: new THREE.Color(0xffd166),
    emissive: new THREE.Color(0xffb703),
    emissiveIntensity: 0.42,
    metalness: 0.02,
    roughness: 0.34,
    side: THREE.DoubleSide,
  });
  material.polygonOffset = true;
  material.polygonOffsetFactor = -1;
  material.polygonOffsetUnits = -1;
  return material;
}

function disposeMaterial(material: THREE.Material | THREE.Material[]) {
  if (Array.isArray(material)) {
    material.forEach((item) => item.dispose());
    return;
  }
  material.dispose();
}

export function createIfcSelectionBoxHelper(meshes: THREE.Mesh[]) {
  const box = new THREE.Box3();
  for (const mesh of meshes) {
    mesh.updateMatrixWorld(true);
    box.union(new THREE.Box3().setFromObject(mesh));
  }
  if (box.isEmpty()) {
    box.setFromCenterAndSize(new THREE.Vector3(), new THREE.Vector3(1, 1, 1));
  }
  const size = box.getSize(new THREE.Vector3());
  const padding = Math.max(Math.max(size.x, size.y, size.z) * 0.025, 0.08);
  box.expandByScalar(padding);
  const helper = new THREE.Box3Helper(box, 0xffd166);
  helper.userData.ifcSelectionBox = true;
  helper.renderOrder = 90;
  if (helper.material instanceof THREE.LineBasicMaterial) {
    helper.material.depthTest = false;
    helper.material.depthWrite = false;
    helper.material.toneMapped = false;
    helper.material.transparent = false;
  }
  return helper;
}

function disposeIfcSelectionBoxHelper(helper: THREE.Box3Helper | null) {
  if (!helper) return;
  helper.geometry.dispose();
  disposeMaterial(helper.material);
}

function dimensionsForMeshes(meshes: THREE.Mesh[]): IfcElementDimensions | null {
  const box = new THREE.Box3();
  for (const mesh of meshes) {
    mesh.updateMatrixWorld(true);
    box.union(new THREE.Box3().setFromObject(mesh));
  }
  if (box.isEmpty()) return null;
  const size = box.getSize(new THREE.Vector3());
  return {
    x: size.x,
    y: size.y,
    z: size.z,
  };
}

export function clearIfcSelectionVisuals(meshes: THREE.Mesh[]) {
  for (const mesh of meshes) {
    const originalMaterial = mesh.userData.selectionOriginalMaterial as THREE.Material | THREE.Material[] | undefined;
    if (originalMaterial) {
      mesh.material = originalMaterial;
      delete mesh.userData.selectionOriginalMaterial;
    }
    if (typeof mesh.userData.selectionOriginalRenderOrder === "number") {
      mesh.renderOrder = mesh.userData.selectionOriginalRenderOrder;
      delete mesh.userData.selectionOriginalRenderOrder;
    }
    const outlines = mesh.children.filter((child) => child.userData.ifcSelectionOutline === true);
    for (const outline of outlines) {
      mesh.remove(outline);
      if (outline instanceof THREE.LineSegments) {
        outline.geometry.dispose();
        disposeMaterial(outline.material);
      }
    }
  }
}

export function applyIfcSelectionVisuals(meshes: THREE.Mesh[], selectedMaterial: THREE.MeshStandardMaterial) {
  for (const mesh of meshes) {
    clearIfcSelectionVisuals([mesh]);
    mesh.userData.selectionOriginalMaterial = mesh.material;
    mesh.userData.selectionOriginalRenderOrder = mesh.renderOrder;
    mesh.material = selectedMaterial;
    mesh.renderOrder = 50;

    const outline = new THREE.LineSegments(
      new THREE.EdgesGeometry(mesh.geometry),
      new THREE.LineBasicMaterial({
        color: 0xffd166,
        depthTest: false,
        depthWrite: false,
        linewidth: 2,
      })
    );
    outline.userData.ifcSelectionOutline = true;
    outline.renderOrder = 60;
    outline.scale.setScalar(1.003);
    mesh.add(outline);
  }
}

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function orbitCameraAroundTarget(
  camera: THREE.PerspectiveCamera,
  target: THREE.Vector3,
  deltaX: number,
  deltaY: number
) {
  const offset = camera.position.clone().sub(target);
  const spherical = new THREE.Spherical().setFromVector3(offset);
  spherical.theta -= deltaX * 0.006;
  spherical.phi = clamp(spherical.phi + deltaY * 0.0045, 0.08, Math.PI - 0.08);
  offset.setFromSpherical(spherical);
  camera.position.copy(target).add(offset);
  camera.lookAt(target);
}

function panCameraTarget(camera: THREE.PerspectiveCamera, target: THREE.Vector3, deltaX: number, deltaY: number) {
  const distance = Math.max(camera.position.distanceTo(target), 1);
  const scale = distance * 0.0016;
  const forward = target.clone().sub(camera.position).normalize();
  const right = new THREE.Vector3().crossVectors(forward, camera.up).normalize();
  const up = camera.up.clone().normalize();
  const move = right.multiplyScalar(-deltaX * scale).add(up.multiplyScalar(deltaY * scale));
  camera.position.add(move);
  target.add(move);
  camera.lookAt(target);
}

function lookCameraFromWalkMode(
  camera: THREE.PerspectiveCamera,
  target: THREE.Vector3,
  deltaX: number,
  deltaY: number
) {
  const offset = target.clone().sub(camera.position);
  const spherical = new THREE.Spherical().setFromVector3(offset.lengthSq() ? offset : new THREE.Vector3(0, 0, -1));
  spherical.radius = Math.max(spherical.radius, 1);
  spherical.theta -= deltaX * 0.004;
  spherical.phi = clamp(spherical.phi + deltaY * 0.003, 0.08, Math.PI - 0.08);
  target.copy(camera.position).add(new THREE.Vector3().setFromSpherical(spherical));
  camera.lookAt(target);
}

export function walkCameraStep(
  camera: THREE.PerspectiveCamera,
  target: THREE.Vector3,
  pressedKeys: Set<string>,
  distance: number
) {
  const normalizedKeys = new Set(Array.from(pressedKeys, (key) => key.toLowerCase()));
  const forward = new THREE.Vector3();
  camera.getWorldDirection(forward);
  forward.y = 0;
  if (!forward.lengthSq()) forward.set(0, 0, -1);
  forward.normalize();
  const right = new THREE.Vector3().crossVectors(forward, camera.up).normalize();
  const up = camera.up.clone().normalize();
  const move = new THREE.Vector3();
  if (normalizedKeys.has("w") || normalizedKeys.has("arrowup")) move.add(forward);
  if (normalizedKeys.has("s") || normalizedKeys.has("arrowdown")) move.sub(forward);
  if (normalizedKeys.has("a") || normalizedKeys.has("arrowleft")) move.sub(right);
  if (normalizedKeys.has("d") || normalizedKeys.has("arrowright")) move.add(right);
  if (normalizedKeys.has("e") || normalizedKeys.has("pageup")) move.add(up);
  if (normalizedKeys.has("q") || normalizedKeys.has("pagedown")) move.sub(up);
  if (!move.lengthSq()) return;
  move.normalize().multiplyScalar(distance);
  camera.position.add(move);
  target.add(move);
  camera.lookAt(target);
}

type IfcObjectTreeBranchProps = {
  depth?: number;
  forceOpen: boolean;
  node: IfcObjectTreeNode;
  onIsolate: (node: IfcObjectTreeNode) => void;
  onSelect: (node: IfcObjectTreeNode) => void;
  selectedLineId: number | null;
};

function IfcObjectTreeBranch({
  depth = 0,
  forceOpen,
  node,
  onIsolate,
  onSelect,
  selectedLineId,
}: IfcObjectTreeBranchProps) {
  const [expanded, setExpanded] = useState(depth <= 5);
  const isExpanded = forceOpen || expanded;
  const isSelected = selectedLineId !== null && node.lineIds.includes(selectedLineId);

  if (node.kind === "object") {
    return (
      <div
        aria-label={`Objeto IFC ${node.label}`}
        aria-selected={isSelected}
        className={`bimObjectTreeLeaf${isSelected ? " active" : ""}`}
        role="treeitem"
      >
        <button
          aria-label={`Seleccionar objeto IFC ${node.label}`}
          onClick={() => onSelect(node)}
          title={`${node.label} / ${node.reference || "Referencia pendiente"}`}
          type="button"
        >
          <span aria-hidden="true" className="bimObjectTreeGlyph">
            +
          </span>
          <span>
            <strong>{node.label}</strong>
            <small>
              {node.reference || "Referencia pendiente"} / {node.lineIds.length} medicion(es)
              {node.apuCount ? ` / ${node.apuCount} con APU` : ""}
            </small>
          </span>
        </button>
        <button
          aria-label={`Aislar objeto IFC ${node.label}`}
          className="bimObjectTreeIsolate"
          disabled={!node.traceRefs.length}
          onClick={() => onIsolate(node)}
          title="Aislar objeto"
          type="button"
        >
          <Eye size={12} />
        </button>
      </div>
    );
  }

  return (
    <div
      aria-expanded={isExpanded}
      aria-label={`${node.kind} ${node.label}`}
      className={`bimObjectTreeNode kind-${node.kind}`}
      role="treeitem"
    >
      <div className="bimObjectTreeBranchRow">
        <button
          aria-label={`${isExpanded ? "Contraer" : "Expandir"} ${node.kind} ${node.label}`}
          className="bimObjectTreeToggle"
          onClick={() => setExpanded((current) => !current)}
          title={node.label}
          type="button"
        >
          <span aria-hidden="true" className="bimObjectTreeGlyph">
            {isExpanded ? "−" : "+"}
          </span>
          <span>{node.label}</span>
          <small>({node.count})</small>
        </button>
        {node.kind === "class" || node.kind === "storey" ? (
          <button
            aria-label={`Aislar ${node.kind} ${node.label}`}
            className="bimObjectTreeIsolate"
            disabled={!node.traceRefs.length}
            onClick={() => onIsolate(node)}
            title={`Aislar ${node.label}`}
            type="button"
          >
            <Eye size={12} />
          </button>
        ) : null}
      </div>
      {isExpanded ? (
        <div className="bimObjectTreeChildren" role="group">
          {node.children.map((child) => (
            <IfcObjectTreeBranch
              depth={depth + 1}
              forceOpen={forceOpen}
              key={child.id}
              node={child}
              onIsolate={onIsolate}
              onSelect={onSelect}
              selectedLineId={selectedLineId}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}

export default function BimIfcModelViewer({
  approvalDisabled = false,
  clearModelDisabled = false,
  informationContent,
  projectId,
  lines = [],
  model,
  onApproveControlledMeasurement,
  onClearModel,
  onLoadSource,
  ribbonHostId,
  run,
  sourceLoadDisabled = false,
  sourceLoading = false,
  token,
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const viewerCommandsRef = useRef<ViewerCameraCommands | null>(null);
  const navigationModeRef = useRef<NavigationMode>("orbit");
  const interactionModeRef = useRef<InteractionMode>("select");
  const viewPresetRef = useRef<ViewPreset>("iso");
  const pressedKeysRef = useRef(new Set<string>());
  const [viewPreset, setViewPreset] = useState<ViewPreset>("iso");
  const [navigationMode, setNavigationMode] = useState<NavigationMode>("orbit");
  const [interactionMode, setInteractionMode] = useState<InteractionMode>("select");
  const [activeRibbonMenu, setActiveRibbonMenu] = useState<IfcRibbonMenu>("view");
  const [ribbonExpanded, setRibbonExpanded] = useState(true);
  const [visualStyle, setVisualStyle] = useState<IfcVisualStyle>("solid");
  const [explodeFactor, setExplodeFactor] = useState(0);
  const [status, setStatus] = useState("Listo para cargar geometria IFC guardada.");
  const [renderStats, setRenderStats] = useState("Sin geometria IFC cargada");
  const [renderDiagnostics, setRenderDiagnostics] = useState<IfcRenderDiagnostics>(() =>
    emptyIfcRenderDiagnostics(model?.source_size_bytes ?? 0)
  );
  const [detectedModelUnits, setDetectedModelUnits] = useState("");
  const [selectedLineId, setSelectedLineId] = useState<number | null>(null);
  const [selectedIfcElement, setSelectedIfcElement] = useState<SelectedIfcElement | null>(null);
  const [treeSearch, setTreeSearch] = useState("");
  const [isolatedGroupId, setIsolatedGroupId] = useState("");
  const [sectionEnabled, setSectionEnabled] = useState(false);
  const [sectionAxis, setSectionAxis] = useState<SectionAxis>("x");
  const [sectionPosition, setSectionPosition] = useState(50);
  const [reviewFilter, setReviewFilter] = useState<IfcReviewFilter>("all");
  const [pointMeasurement, setPointMeasurement] = useState<IfcPointMeasurement | null>(null);
  const [measurementStatus, setMeasurementStatus] = useState("Selecciona dos puntos sobre la geometria.");
  const [clashToleranceMm, setClashToleranceMm] = useState(10);
  const [clashSummary, setClashSummary] = useState<IfcClashSummary | null>(null);
  const [objectExplorerOpen, setObjectExplorerOpen] = useState(true);
  const [propertiesPanelOpen, setPropertiesPanelOpen] = useState(true);
  const [viewerManifest, setViewerManifest] = useState<BimViewerManifest | null>(null);
  const [manifestStatus, setManifestStatus] = useState("Manifiesto de visor pendiente.");
  const [manifestRefreshKey, setManifestRefreshKey] = useState(0);
  const [isPreparingGeometryCache, setIsPreparingGeometryCache] = useState(false);
  const [geometryCacheStatus, setGeometryCacheStatus] = useState("");
  const [elementProperties, setElementProperties] = useState<BimElementProperties | null>(null);
  const [elementPropertiesLoadStatus, setElementPropertiesLoadStatus] = useState("");
  const sourceName = model?.source_file_name ?? run?.source_file_name;
  const sourceType = model?.source_type ?? run?.source_type;
  const canLoadModel = Boolean(projectId && sourceType === "ifc" && (model || run));
  const treeGroups = useMemo(() => buildIfcTreeGroups(lines), [lines]);
  const filteredTreeLines = useMemo(() => {
    const query = compact(treeSearch).toLowerCase();
    return lines.filter(
      (line) => lineMatchesReviewFilter(line, reviewFilter) && (!query || lineSearchBasis(line).includes(query))
    );
  }, [lines, reviewFilter, treeSearch]);
  const objectTree = useMemo(
    () => buildIfcObjectTree(lines, sourceName || "Modelo IFC", model?.model_identity ?? {}),
    [lines, model?.model_identity, sourceName]
  );
  const filteredObjectTree = useMemo(
    () => buildIfcObjectTree(filteredTreeLines, sourceName || "Modelo IFC", model?.model_identity ?? {}),
    [filteredTreeLines, model?.model_identity, sourceName]
  );
  const selectedLine = lines.find((line) => line.id === selectedLineId);
  const selectedPropertyKey = selectedIfcPropertyLookupKey(selectedLine, selectedIfcElement);

  useEffect(() => {
    let active = true;
    setElementProperties(null);
    setElementPropertiesLoadStatus("");
    if (!projectId || !model || !selectedPropertyKey) return undefined;
    setElementPropertiesLoadStatus("Consultando propiedades IFC publicadas...");
    bimModelsApi
      .elementProperties(token, projectId, model.id, selectedPropertyKey)
      .then((properties) => {
        if (!active) return;
        setElementProperties(properties);
        setElementPropertiesLoadStatus("");
      })
      .catch(() => {
        if (!active) return;
        setElementPropertiesLoadStatus("Propiedades IFC no disponibles para esta seleccion.");
      });
    return () => {
      active = false;
    };
  }, [model?.id, projectId, selectedPropertyKey, token]);

  useEffect(() => {
    navigationModeRef.current = navigationMode;
    pressedKeysRef.current.clear();
  }, [navigationMode]);

  useEffect(() => {
    interactionModeRef.current = interactionMode;
    viewerCommandsRef.current?.measurement(interactionMode === "measure");
  }, [interactionMode]);

  useEffect(() => {
    viewPresetRef.current = viewPreset;
  }, [viewPreset]);

  useEffect(() => {
    viewerCommandsRef.current?.section(sectionEnabled, sectionAxis, sectionPosition / 100);
  }, [sectionAxis, sectionEnabled, sectionPosition]);

  useEffect(() => {
    viewerCommandsRef.current?.style(visualStyle);
  }, [visualStyle]);

  useEffect(() => {
    viewerCommandsRef.current?.explode(explodeFactor / 100);
  }, [explodeFactor]);

  useEffect(() => {
    let active = true;
    setViewerManifest(null);
    setManifestStatus(model ? "Cargando manifiesto de visor..." : "Sin modelo IFC registrado.");
    if (!projectId || !model) return undefined;
    bimModelsApi
      .manifest(token, projectId, model.id)
      .then((manifest) => {
        if (!active) return;
        setViewerManifest(manifest);
        setManifestStatus("Manifiesto de visor listo.");
      })
      .catch(() => {
        if (!active) return;
        setManifestStatus("Manifiesto no disponible; usando metadatos locales del modelo.");
      });
    return () => {
      active = false;
    };
  }, [manifestRefreshKey, model?.id, projectId, token]);

  useEffect(() => {
    setIsolatedGroupId("");
    setSectionEnabled(false);
    setSectionAxis("x");
    setSectionPosition(50);
    setInteractionMode("select");
    setVisualStyle("solid");
    setExplodeFactor(0);
    setPointMeasurement(null);
    setMeasurementStatus("Selecciona dos puntos sobre la geometria.");
    setClashSummary(null);
    setRenderDiagnostics(emptyIfcRenderDiagnostics(model?.source_size_bytes ?? 0));
    setGeometryCacheStatus("");
  }, [model?.id, run?.id]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !projectId || sourceType !== "ifc" || (!model && !run)) {
      return undefined;
    }
    if (navigator.userAgent.toLowerCase().includes("jsdom")) {
      return undefined;
    }

    let disposed = false;
    let renderer: THREE.WebGLRenderer | undefined;
    let frameId = 0;
    let cleanupScene: (() => void) | undefined;
    const runViewer = async () => {
      setStatus("Cargando geometria IFC guardada...");
      setDetectedModelUnits("");
      setRenderStats(sourceName ?? "IFC");
      setRenderDiagnostics(emptyIfcRenderDiagnostics(model?.source_size_bytes ?? 0));
      try {
        renderer = new THREE.WebGLRenderer({
          antialias: true,
          canvas,
          powerPreference: "high-performance",
          preserveDrawingBuffer: true,
        });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
        renderer.outputColorSpace = THREE.SRGBColorSpace;
        renderer.toneMapping = THREE.ACESFilmicToneMapping;
        renderer.toneMappingExposure = 1.0;
        renderer.shadowMap.enabled = true;
        renderer.localClippingEnabled = false;

        const scene = new THREE.Scene();
        scene.background = new THREE.Color(0xf4f7f8);
        const camera = new THREE.PerspectiveCamera(36, 1, 0.1, 100000);
        const ambient = new THREE.HemisphereLight(0xffffff, 0x9fb0b8, 1.8);
        scene.add(ambient);
        const keyLight = new THREE.DirectionalLight(0xffffff, 2.1);
        keyLight.position.set(12, 18, 10);
        scene.add(keyLight);
        const fillLight = new THREE.DirectionalLight(0xc9e4ef, 0.8);
        fillLight.position.set(-12, 8, -10);
        scene.add(fillLight);

        const root = new THREE.Group();
        scene.add(root);
        const measurementLayer = new THREE.Group();
        measurementLayer.userData.ifcMeasurementLayer = true;
        scene.add(measurementLayer);
        const clippingPlane = new THREE.Plane(new THREE.Vector3(-1, 0, 0), 0);
        const raycaster = new THREE.Raycaster();
        const pointer = new THREE.Vector2();
        const productMeshes = new Map<string, THREE.Mesh[]>();
        const pickableMeshes: THREE.Mesh[] = [];
        const selectedMeshes: THREE.Mesh[] = [];
        const selectedMaterial = createIfcSelectedMaterial();
        let selectionBoxHelper: THREE.Box3Helper | null = null;
        let measurementStart: THREE.Vector3 | null = null;
        const loadStartedAt = performance.now();
        const diagnostics = emptyIfcRenderDiagnostics(model?.source_size_bytes ?? 0);

        const clearSelection = () => {
          clearIfcSelectionVisuals(selectedMeshes);
          selectedMeshes.splice(0, selectedMeshes.length);
          if (selectionBoxHelper) {
            scene.remove(selectionBoxHelper);
            disposeIfcSelectionBoxHelper(selectionBoxHelper);
            selectionBoxHelper = null;
          }
        };

        const materialCache = new Map<string, THREE.MeshStandardMaterial>();
        const meshBounds: THREE.Box3[] = [];
        const renderSource =
          model && viewerManifest?.geometry_strategy === "backend_cache" ? "backend_cache" : "web_ifc";
        let geometryLoadError: unknown = null;
        let geometryUnits = reliableModelUnits(viewerManifest?.units || model?.units);
        let productCount = 0;
        let meshCount = 0;
        let triangleCount = 0;

        if (renderSource === "backend_cache" && model) {
          setStatus("Cargando geometria desde cache backend IfcOpenShell...");
          const artifact = await bimModelsApi.geometryCache(token, projectId, model.id);
          if (disposed) return;
          geometryUnits = reliableModelUnits(artifact.units || viewerManifest?.units || model.units);
          setDetectedModelUnits(geometryUnits);
          const cachedGeometry = buildBackendCacheGeometryMeshes(artifact, materialCache);
          productCount = cachedGeometry.diagnostics.productsScanned;
          meshCount = cachedGeometry.diagnostics.meshesRendered;
          triangleCount = cachedGeometry.diagnostics.trianglesRendered;
          Object.assign(diagnostics, cachedGeometry.diagnostics);
          diagnostics.fileSizeBytes = model.source_size_bytes ?? 0;
          cachedGeometry.bounds.forEach((bounds) => meshBounds.push(bounds));
          cachedGeometry.meshes.forEach((mesh) => {
            const selectionKeys = selectionKeysForIfcData(mesh.userData.ifc as IfcMeshData);
            selectionKeys.forEach((selectionKey) => {
              productMeshes.set(selectionKey, [...(productMeshes.get(selectionKey) ?? []), mesh]);
            });
            pickableMeshes.push(mesh);
            root.add(mesh);
          });
        } else {
          const blob = model
            ? await bimModelsApi.source(token, projectId, model.id)
            : await projectsApi.quantityTakeoffIfcModel(token, projectId, run!.id);
          if (disposed) return;
          const bytes = new Uint8Array(await blob.arrayBuffer());
          diagnostics.fileSizeBytes = bytes.length;
          const headerText = new TextDecoder("utf-8").decode(bytes.slice(0, Math.min(bytes.length, 2_000_000)));
          geometryUnits = detectIfcLengthUnitsFromText(headerText) || reliableModelUnits(model?.units);
          setDetectedModelUnits(geometryUnits);
          const { IfcAPI } = await import("web-ifc");
          const ifcApi = new IfcAPI();
          await ifcApi.Init((path) => (path.endsWith(".wasm") ? webIfcWasmUrl : path), true);
          if (disposed) {
            ifcApi.Dispose();
            return;
          }
          const modelId = ifcApi.OpenModel(bytes);
          let flatMeshes: { size: () => number; get: (index: number) => any } | null = null;
          try {
            flatMeshes = ifcApi.LoadAllGeometry(modelId);
          } catch (error) {
            geometryLoadError = error;
          }

          flatMeshLoop: for (let index = 0; index < (flatMeshes?.size() ?? 0); index += 1) {
            if (!flatMeshes) break;
            const flatMesh = flatMeshes.get(index);
            productCount += 1;
            diagnostics.productsScanned = productCount;
            const expressId = isValidIfcExpressId(flatMesh.expressID) ? flatMesh.expressID : null;
            let globalId = "";
            let lineName = "";
            let lineClass = "";
            if (expressId) {
              try {
                const ifcLine = ifcApi.GetLine(modelId, expressId, false);
                globalId = readIfcText(ifcLine?.GlobalId);
                lineName = readIfcText(ifcLine?.Name);
                lineClass = readIfcText(ifcLine?.type) || "";
              } catch {
                globalId = "";
              }
            }
            for (let geometryIndex = 0; geometryIndex < flatMesh.geometries.size(); geometryIndex += 1) {
              const placed = flatMesh.geometries.get(geometryIndex);
              if (!isValidIfcExpressId(placed.geometryExpressID)) {
                diagnostics.invalidGeometryRefs += 1;
                continue;
              }
              let ifcGeometry: {
                GetVertexData: () => number;
                GetVertexDataSize: () => number;
                GetIndexData: () => number;
                GetIndexDataSize: () => number;
                delete: () => void;
              };
              try {
                ifcGeometry = ifcApi.GetGeometry(modelId, placed.geometryExpressID);
              } catch {
                diagnostics.conversionErrors += 1;
                continue;
              }
              try {
                const vertexDataRef = ifcGeometry.GetVertexData();
                const vertexDataSize = ifcGeometry.GetVertexDataSize();
                const indexDataRef = ifcGeometry.GetIndexData();
                const indexDataSize = ifcGeometry.GetIndexDataSize();
                if (
                  !isValidIfcMemoryRef(vertexDataRef, vertexDataSize) ||
                  !isValidIfcMemoryRef(indexDataRef, indexDataSize)
                ) {
                  diagnostics.invalidMemoryRefs += 1;
                  continue;
                }
                const vertexData = ifcApi.GetVertexArray(vertexDataRef, vertexDataSize);
                const indexData = ifcApi.GetIndexArray(indexDataRef, indexDataSize);
                if (!vertexData.length || !indexData.length) {
                  diagnostics.emptyGeometries += 1;
                  continue;
                }
                const nextTriangleCount = triangleCount + Math.floor(indexData.length / 3);
                if (meshCount >= IFC_BROWSER_MESH_LIMIT || nextTriangleCount > IFC_BROWSER_TRIANGLE_LIMIT) {
                  diagnostics.limitReached = true;
                  break;
                }
                const positions = new Float32Array(vertexData.length / 2);
                const normals = new Float32Array(vertexData.length / 2);
                for (let vertexIndex = 0; vertexIndex < vertexData.length; vertexIndex += 6) {
                  const attributeIndex = vertexIndex / 2;
                  positions[attributeIndex] = vertexData[vertexIndex];
                  positions[attributeIndex + 1] = vertexData[vertexIndex + 1];
                  positions[attributeIndex + 2] = vertexData[vertexIndex + 2];
                  normals[attributeIndex] = vertexData[vertexIndex + 3];
                  normals[attributeIndex + 1] = vertexData[vertexIndex + 4];
                  normals[attributeIndex + 2] = vertexData[vertexIndex + 5];
                }
                const geometry = new THREE.BufferGeometry();
                geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
                geometry.setAttribute("normal", new THREE.BufferAttribute(normals, 3));
                geometry.setIndex(new THREE.BufferAttribute(indexData, 1));
                geometry.applyMatrix4(new THREE.Matrix4().fromArray(placed.flatTransformation));
                geometry.computeBoundingBox();
                if (geometry.boundingBox) meshBounds.push(geometry.boundingBox.clone());
                const mesh = new THREE.Mesh(geometry, materialForColor(materialCache, placed.color));
                mesh.castShadow = true;
                mesh.receiveShadow = true;
                mesh.userData.ifc = {
                  expressId,
                  globalId,
                  ifcClass: lineClass,
                  name: lineName,
                };
                const selectionKeys = selectionKeysForIfcData(mesh.userData.ifc as IfcMeshData);
                selectionKeys.forEach((selectionKey) => {
                  productMeshes.set(selectionKey, [...(productMeshes.get(selectionKey) ?? []), mesh]);
                });
                pickableMeshes.push(mesh);
                root.add(mesh);
                meshCount += 1;
                triangleCount = nextTriangleCount;
                diagnostics.meshesRendered = meshCount;
                diagnostics.trianglesRendered = triangleCount;
              } catch {
                diagnostics.conversionErrors += 1;
                continue;
              } finally {
                ifcGeometry.delete();
              }
            }
            if ("delete" in flatMesh && typeof flatMesh.delete === "function") {
              flatMesh.delete();
            }
            if (diagnostics.limitReached) break flatMeshLoop;
          }
          ifcApi.CloseModel(modelId);
          ifcApi.Dispose();
        }
        diagnostics.loadMs = performance.now() - loadStartedAt;
        setRenderDiagnostics({ ...diagnostics });

        const modelBox = new THREE.Box3().setFromObject(root);
        if (modelBox.isEmpty()) modelBox.setFromCenterAndSize(new THREE.Vector3(), new THREE.Vector3(10, 10, 10));
        const modelCenter = modelBox.getCenter(new THREE.Vector3());
        const modelSize = modelBox.getSize(new THREE.Vector3());
        const modelMaxDimension = Math.max(modelSize.x, modelSize.y, modelSize.z, 1);
        const focusBox = new THREE.Box3();
        meshBounds.forEach((bounds) => {
          const size = bounds.getSize(new THREE.Vector3());
          const isLargeFlatSite =
            (size.x > modelSize.x * 0.45 || size.z > modelSize.z * 0.45) && size.y < Math.max(modelSize.y * 0.18, 1);
          if (!isLargeFlatSite) focusBox.union(bounds);
        });
        if (focusBox.isEmpty()) focusBox.copy(modelBox);
        const explodeGroups = new Map<string, THREE.Mesh[]>();
        const originalMeshPositions = new Map<THREE.Mesh, THREE.Vector3>();
        for (const mesh of pickableMeshes) {
          const data = mesh.userData.ifc as IfcMeshData | undefined;
          const key = selectionKeyForIfcData(data) || mesh.uuid;
          explodeGroups.set(key, [...(explodeGroups.get(key) ?? []), mesh]);
          originalMeshPositions.set(mesh, mesh.position.clone());
        }
        const clearMeasurementArtifacts = () => {
          measurementLayer.traverse((object) => {
            if (object instanceof THREE.Mesh || object instanceof THREE.Line) {
              object.geometry.dispose();
              disposeMaterial(object.material);
            }
          });
          measurementLayer.clear();
          measurementStart = null;
        };
        const addMeasurementMarker = (point: THREE.Vector3) => {
          const marker = new THREE.Mesh(
            new THREE.SphereGeometry(Math.max(modelMaxDimension * 0.006, 0.025), 16, 12),
            new THREE.MeshBasicMaterial({ color: 0xffd166, depthTest: false })
          );
          marker.position.copy(point);
          marker.renderOrder = 100;
          measurementLayer.add(marker);
        };
        const completePointMeasurement = (start: THREE.Vector3, end: THREE.Vector3) => {
          const lineGeometry = new THREE.BufferGeometry().setFromPoints([start, end]);
          const line = new THREE.Line(
            lineGeometry,
            new THREE.LineBasicMaterial({ color: 0xff7a00, depthTest: false, linewidth: 2 })
          );
          line.renderOrder = 99;
          measurementLayer.add(line);
          const distanceMeters = measureIfcPointDistance(start, end, geometryUnits, modelMaxDimension);
          setPointMeasurement({
            distanceMeters,
            end: end.toArray() as [number, number, number],
            start: start.toArray() as [number, number, number],
          });
          setMeasurementStatus(`Distancia medida: ${formatNumber(distanceMeters)} m.`);
        };
        const gridSize = Math.max(modelSize.x, modelSize.z, 20) * 1.25;
        const grid = new THREE.GridHelper(gridSize, 44, 0x9aacb5, 0xdce6ea);
        grid.position.set(modelCenter.x, modelBox.min.y - Math.max(gridSize * 0.002, 0.03), modelCenter.z);
        scene.add(grid);

        const target = new THREE.Vector3();
        const walkSpeed = Math.max(2, Math.min(18, modelSize.length() * 0.08));
        const applyCameraView = (preset: ViewPreset, sourceBox = focusBox) => {
          const box = sourceBox.clone();
          if (box.isEmpty()) box.setFromCenterAndSize(new THREE.Vector3(), new THREE.Vector3(10, 10, 10));
          const center = box.getCenter(new THREE.Vector3());
          const size = box.getSize(new THREE.Vector3());
          target.copy(center);
          const maxDim = Math.max(size.x, size.y, size.z, 8);
          const distance = maxDim * (preset === "top" ? 1.45 : 1.35);
          if (preset === "top") {
            camera.up.set(0, 0, -1);
            camera.position.set(center.x, center.y + distance, center.z + 0.01);
          } else if (preset === "front") {
            camera.up.set(0, 1, 0);
            camera.position.set(center.x, center.y + size.y * 0.18, center.z + distance);
          } else if (preset === "right") {
            camera.up.set(0, 1, 0);
            camera.position.set(center.x + distance, center.y + size.y * 0.18, center.z);
          } else {
            camera.up.set(0, 1, 0);
            camera.position.set(center.x + distance, center.y + distance * 0.62, center.z + distance * 0.82);
          }
          camera.near = Math.max(0.1, distance / 10000);
          camera.far = distance * 20;
          camera.lookAt(center);
          camera.updateProjectionMatrix();
        };
        const fitCamera = () => applyCameraView(viewPresetRef.current);
        const focusCameraOnMeshes = (meshes: THREE.Mesh[]) => {
          const selectionBox = new THREE.Box3();
          meshes.forEach((mesh) => selectionBox.expandByObject(mesh));
          if (!selectionBox.isEmpty()) applyCameraView("iso", selectionBox);
        };
        const meshesForRefs = (refs: string[]) => {
          const matched = new Set<THREE.Mesh>();
          for (const ref of unique(refs)) {
            const meshes = productMeshes.get(ref) ?? productMeshes.get(ref.replace(/^#?/, "#")) ?? [];
            meshes.forEach((mesh) => matched.add(mesh));
          }
          return Array.from(matched);
        };
        const resetVisibility = () => {
          pickableMeshes.forEach((mesh) => {
            mesh.visible = true;
          });
          setIsolatedGroupId("");
        };
        viewerCommandsRef.current = {
          clashes: (toleranceMeters) => detectIfcBoxClashes(pickableMeshes, geometryUnits, toleranceMeters),
          explode: (factor) => {
            const safeFactor = clamp(factor, 0, 1);
            for (const groupMeshes of explodeGroups.values()) {
              const groupBox = new THREE.Box3();
              groupMeshes.forEach((mesh) => {
                const originalPosition = originalMeshPositions.get(mesh);
                if (originalPosition) mesh.position.copy(originalPosition);
                mesh.updateMatrixWorld(true);
                groupBox.expandByObject(mesh);
              });
              const direction = groupBox.getCenter(new THREE.Vector3()).sub(modelCenter);
              if (!direction.lengthSq()) direction.set(0, 1, 0);
              direction.normalize().multiplyScalar(modelMaxDimension * 0.18 * safeFactor);
              groupMeshes.forEach((mesh) => {
                const originalPosition = originalMeshPositions.get(mesh) ?? new THREE.Vector3();
                mesh.position.copy(originalPosition).add(direction);
                mesh.updateMatrixWorld(true);
              });
            }
          },
          fit: fitCamera,
          filterRefs: (refs) => {
            const matchedMeshes = meshesForRefs(refs);
            const visibleMeshes = new Set(matchedMeshes);
            pickableMeshes.forEach((mesh) => {
              mesh.visible = visibleMeshes.has(mesh);
            });
            setIsolatedGroupId("");
            if (matchedMeshes.length) focusCameraOnMeshes(matchedMeshes);
          },
          focusRefs: (refs) => {
            const matchedMeshes = meshesForRefs(refs);
            if (matchedMeshes.length) focusCameraOnMeshes(matchedMeshes);
          },
          isolateRefs: (refs) => {
            const matchedMeshes = meshesForRefs(refs);
            if (!matchedMeshes.length) return;
            const visibleMeshes = new Set(matchedMeshes);
            pickableMeshes.forEach((mesh) => {
              mesh.visible = visibleMeshes.has(mesh);
            });
            focusCameraOnMeshes(matchedMeshes);
          },
          measurement: (active) => {
            measurementStart = null;
            setMeasurementStatus(
              active
                ? "Selecciona el primer punto sobre una malla IFC."
                : "Activa Medir para seleccionar dos puntos sobre la geometria."
            );
          },
          resetVisibility,
          section: (active, axis, position) => {
            renderer!.localClippingEnabled = active;
            const sectionNormal =
              axis === "y"
                ? new THREE.Vector3(0, -1, 0)
                : axis === "z"
                  ? new THREE.Vector3(0, 0, -1)
                  : new THREE.Vector3(-1, 0, 0);
            const axisMin = axis === "y" ? focusBox.min.y : axis === "z" ? focusBox.min.z : focusBox.min.x;
            const axisMax = axis === "y" ? focusBox.max.y : axis === "z" ? focusBox.max.z : focusBox.max.x;
            const sectionOffset = axisMin + (axisMax - axisMin) * clamp(position, 0, 1);
            clippingPlane.normal.copy(sectionNormal);
            clippingPlane.constant = sectionOffset;
            pickableMeshes.forEach((mesh) => {
              const materials = Array.isArray(mesh.material) ? mesh.material : [mesh.material];
              materials.forEach((material) => {
                material.clippingPlanes = active ? [clippingPlane] : [];
                material.needsUpdate = true;
              });
            });
          },
          style: (style) => applyIfcVisualStyle(materialCache.values(), style),
          view: (preset) => applyCameraView(preset),
        };

        let dragging = false;
        let moved = false;
        let pointerButton = 0;
        let previousX = 0;
        let previousY = 0;
        const interactionTarget = canvas.parentElement ?? canvas;
        interactionTarget.tabIndex = 0;
        const pickIfcHit = (event: PointerEvent | MouseEvent) => {
          const bounds = canvas.getBoundingClientRect();
          pointer.x = ((event.clientX - bounds.left) / bounds.width) * 2 - 1;
          pointer.y = -((event.clientY - bounds.top) / bounds.height) * 2 + 1;
          raycaster.setFromCamera(pointer, camera);
          root.updateMatrixWorld(true);
          const exactHit = raycaster
            .intersectObjects(root.children, true)
            .find(
              (intersection) => intersection.object instanceof THREE.Mesh && Boolean(intersection.object.userData.ifc)
            );
          if (exactHit && exactHit.object instanceof THREE.Mesh) {
            return { mesh: exactHit.object, point: exactHit.point.clone() };
          }
          const fallbackMesh = closestProjectedIfcMesh(
            pickableMeshes.filter((mesh) => mesh.visible),
            camera,
            pointer
          );
          return fallbackMesh
            ? { mesh: fallbackMesh, point: new THREE.Box3().setFromObject(fallbackMesh).getCenter(new THREE.Vector3()) }
            : null;
        };
        const selectMeshFromPointer = (event: PointerEvent | MouseEvent, focusSelected = false) => {
          const hitMesh = pickIfcHit(event)?.mesh;
          const data = hitMesh?.userData.ifc as IfcMeshData | undefined;
          if (data && hitMesh) {
            const selectionKey = selectionKeyForIfcData(data);
            const meshesToHighlight = selectionKey ? (productMeshes.get(selectionKey) ?? [hitMesh]) : [hitMesh];
            const selectedElement = {
              dimensions: dimensionsForMeshes(meshesToHighlight),
              expressId: data.expressId ?? null,
              globalId: data.globalId ?? "",
              ifcClass: data.ifcClass ?? "",
              name: data.name ?? "",
              realQuantities: calculateRealGeometryQuantities(meshesToHighlight, geometryUnits),
            };
            clearSelection();
            selectedMeshes.push(...meshesToHighlight);
            applyIfcSelectionVisuals(selectedMeshes, selectedMaterial);
            root.updateMatrixWorld(true);
            selectionBoxHelper = createIfcSelectionBoxHelper(selectedMeshes);
            scene.add(selectionBoxHelper);
            setSelectedIfcElement(selectedElement);
            const matchedLine = lines.find((line) => lineMatchesIfcElement(line, selectedElement));
            setSelectedLineId(matchedLine?.id ?? null);
            if (focusSelected) focusCameraOnMeshes(meshesToHighlight);
          } else {
            clearSelection();
            setSelectedIfcElement(null);
            setSelectedLineId(null);
          }
        };
        const measurePointFromPointer = (event: PointerEvent | MouseEvent) => {
          const hit = pickIfcHit(event);
          if (!hit) {
            setMeasurementStatus("No se detecto una malla IFC bajo el puntero.");
            return;
          }
          if (!measurementStart) {
            clearMeasurementArtifacts();
            measurementStart = hit.point.clone();
            addMeasurementMarker(measurementStart);
            setPointMeasurement(null);
            setMeasurementStatus("Primer punto fijado. Selecciona el segundo punto.");
            return;
          }
          const start = measurementStart.clone();
          const end = hit.point.clone();
          addMeasurementMarker(end);
          completePointMeasurement(start, end);
          measurementStart = null;
        };
        const onPointerDown = (event: PointerEvent) => {
          event.preventDefault();
          dragging = true;
          moved = false;
          pointerButton = event.button;
          previousX = event.clientX;
          previousY = event.clientY;
          interactionTarget.focus();
          interactionTarget.setPointerCapture?.(event.pointerId);
        };
        const onPointerMove = (event: PointerEvent) => {
          if (!dragging) return;
          const deltaX = event.clientX - previousX;
          const deltaY = event.clientY - previousY;
          if (Math.abs(deltaX) + Math.abs(deltaY) > 4) moved = true;
          previousX = event.clientX;
          previousY = event.clientY;
          if (navigationModeRef.current === "walk") {
            lookCameraFromWalkMode(camera, target, deltaX, deltaY);
          } else if (event.shiftKey || pointerButton === 1 || pointerButton === 2) {
            panCameraTarget(camera, target, deltaX, deltaY);
          } else {
            orbitCameraAroundTarget(camera, target, deltaX, deltaY);
          }
        };
        const onPointerUp = (event: PointerEvent) => {
          if (!moved) {
            if (interactionModeRef.current === "measure") {
              measurePointFromPointer(event);
            } else {
              selectMeshFromPointer(event);
            }
          }
          dragging = false;
          interactionTarget.releasePointerCapture?.(event.pointerId);
        };
        const onDoubleClick = (event: MouseEvent) => {
          event.preventDefault();
          if (interactionModeRef.current === "select") selectMeshFromPointer(event, true);
        };
        const onWheel = (event: WheelEvent) => {
          event.preventDefault();
          const zoom = event.deltaY > 0 ? 1.08 : 0.92;
          const offset = camera.position.clone().sub(target).multiplyScalar(zoom);
          camera.position.copy(target).add(offset);
          camera.lookAt(target);
        };
        const onKeyDown = (event: KeyboardEvent) => {
          if (navigationModeRef.current !== "walk") return;
          const key = event.key.toLowerCase();
          if (
            ![
              "w",
              "a",
              "s",
              "d",
              "q",
              "e",
              "arrowup",
              "arrowdown",
              "arrowleft",
              "arrowright",
              "pageup",
              "pagedown",
            ].includes(key)
          ) {
            return;
          }
          event.preventDefault();
          pressedKeysRef.current.add(key);
        };
        const onKeyUp = (event: KeyboardEvent) => {
          pressedKeysRef.current.delete(event.key.toLowerCase());
        };
        const onContextMenu = (event: MouseEvent) => event.preventDefault();
        const onWebGlContextLost = (event: Event) => {
          event.preventDefault();
          setStatus(
            "El contexto WebGL se perdio por memoria o driver; el IFC queda registrado y se recomienda recargar el visor."
          );
          setRenderStats("Render suspendido por WebGL");
        };
        const onWebGlContextRestored = () => {
          setStatus("Contexto WebGL restaurado. Usa Fit o recarga el modelo si la escena no vuelve a aparecer.");
        };
        interactionTarget.addEventListener("pointerdown", onPointerDown);
        interactionTarget.addEventListener("pointermove", onPointerMove);
        interactionTarget.addEventListener("pointerup", onPointerUp);
        interactionTarget.addEventListener("pointerleave", onPointerUp);
        interactionTarget.addEventListener("dblclick", onDoubleClick);
        interactionTarget.addEventListener("wheel", onWheel, { passive: false });
        interactionTarget.addEventListener("keydown", onKeyDown);
        interactionTarget.addEventListener("keyup", onKeyUp);
        interactionTarget.addEventListener("contextmenu", onContextMenu);
        canvas.addEventListener("webglcontextlost", onWebGlContextLost, false);
        canvas.addEventListener("webglcontextrestored", onWebGlContextRestored, false);

        const resize = () => {
          const bounds = canvas.parentElement?.getBoundingClientRect();
          const width = Math.max(560, Math.floor(bounds?.width ?? canvas.clientWidth ?? 1000));
          const height = Math.max(520, Math.floor(bounds?.height ?? width * 0.52));
          renderer?.setSize(width, height, false);
          camera.aspect = width / height;
          camera.updateProjectionMatrix();
          fitCamera();
        };
        const observer = "ResizeObserver" in window ? new ResizeObserver(resize) : undefined;
        if (canvas.parentElement && observer) observer.observe(canvas.parentElement);
        window.addEventListener("resize", resize);
        resize();

        let lastFrameTime = performance.now();
        const render = () => {
          if (!renderer) return;
          const frameTime = performance.now();
          const deltaSeconds = Math.min(Math.max((frameTime - lastFrameTime) / 1000, 0), 0.08);
          lastFrameTime = frameTime;
          if (navigationModeRef.current === "walk" && pressedKeysRef.current.size) {
            walkCameraStep(camera, target, pressedKeysRef.current, walkSpeed * deltaSeconds);
          }
          renderer.render(scene, camera);
          frameId = window.requestAnimationFrame(render);
        };
        render();
        if (geometryLoadError) {
          setStatus(friendlyIfcRenderStatus(geometryLoadError));
          setRenderStats("Sin mallas IFC renderizables; metadatos disponibles");
        } else if (!meshCount) {
          setStatus(
            renderSource === "backend_cache"
              ? "Cache backend preparado, pero no contiene mallas geometricas renderizables."
              : "IFC registrado. No se encontraron mallas geometricas renderizables en este archivo."
          );
          setRenderStats(`${productCount.toLocaleString()} product(s) / 0 mesh(es)`);
        } else {
          setStatus(
            renderSource === "backend_cache"
              ? "IFC geometry rendered from backend IfcOpenShell cache."
              : diagnostics.limitReached
                ? "IFC renderizado parcialmente por limite seguro del navegador; usa cache backend para el modelo completo."
                : "IFC geometry rendered from stored source file."
          );
          setRenderStats(
            `${productCount.toLocaleString()} product(s) / ${meshCount.toLocaleString()} mesh(es) / ${
              renderSource === "backend_cache" ? "backend cache" : "web-ifc"
            }`
          );
        }

        cleanupScene = () => {
          window.cancelAnimationFrame(frameId);
          window.removeEventListener("resize", resize);
          observer?.disconnect();
          interactionTarget.removeEventListener("pointerdown", onPointerDown);
          interactionTarget.removeEventListener("pointermove", onPointerMove);
          interactionTarget.removeEventListener("pointerup", onPointerUp);
          interactionTarget.removeEventListener("pointerleave", onPointerUp);
          interactionTarget.removeEventListener("dblclick", onDoubleClick);
          interactionTarget.removeEventListener("wheel", onWheel);
          interactionTarget.removeEventListener("keydown", onKeyDown);
          interactionTarget.removeEventListener("keyup", onKeyUp);
          interactionTarget.removeEventListener("contextmenu", onContextMenu);
          canvas.removeEventListener("webglcontextlost", onWebGlContextLost);
          canvas.removeEventListener("webglcontextrestored", onWebGlContextRestored);
          viewerCommandsRef.current = null;
          pressedKeysRef.current.clear();
          clearSelection();
          clearMeasurementArtifacts();
          root.traverse((object) => {
            if (object instanceof THREE.Mesh) object.geometry.dispose();
          });
          selectedMaterial.dispose();
          materialCache.forEach((material) => material.dispose());
        };
      } catch (error) {
        setStatus(friendlyIfcRenderStatus(error));
        setRenderStats("Sin mallas IFC renderizables; metadatos disponibles");
      }
    };

    runViewer();
    return () => {
      disposed = true;
      cleanupScene?.();
      renderer?.dispose();
    };
  }, [
    lines,
    model,
    projectId,
    run,
    sourceName,
    sourceType,
    token,
    viewerManifest?.geometry_strategy,
    viewerManifest?.revision_id,
  ]);

  const displayStatus = canLoadModel
    ? status
    : navigator.userAgent.toLowerCase().includes("jsdom")
      ? "El visor IFC requiere WebGL del navegador."
      : "Carga un IFC para ver la geometria real.";
  const displayStats = canLoadModel ? renderStats : "Sin archivo IFC guardado";
  const hasRenderableGeometry =
    !model || model.element_count > 0
      ? !/sin mallas|0 mesh|no se encontraron mallas/i.test(displayStats + " " + displayStatus)
      : false;
  const modelIdentity = model?.model_identity ?? {};
  const georeferenceLabel = modelGeoreferenceLabel(modelIdentity);
  const georeferenceDetails = modelGeoreferenceDetails(modelIdentity);
  const commercialBlockers = [
    !model ? "Falta modelo IFC registrado" : "",
    model && !hasRenderableGeometry ? "Geometria no renderizable en navegador" : "",
    model && model.source_size_bytes > IFC_BROWSER_CACHE_THRESHOLD_BYTES
      ? "Modelo mayor a 100 MB requiere cache backend"
      : "",
    model && !georeferenceDetails.length ? "Sin georreferenciacion publicada" : "",
    lines.length && !lines.some((line) => compact(line.element_guid) || compact(line.element_id))
      ? "Cantidades sin trazabilidad por elemento"
      : "",
  ].filter(Boolean);
  const commercialReadiness = !model
    ? "Sin modelo"
    : commercialBlockers.length
      ? "Piloto controlado"
      : "Comercial beta";
  const effectiveModelUnits = detectedModelUnits || reliableModelUnits(model?.units);
  const modelSummary = model
    ? [
        model.schema || "IFC",
        effectiveModelUnits || model.units || "units pending",
        model.storey_count ? `${model.storey_count} nivel(es)` : "",
        model.element_count ? `${model.element_count.toLocaleString()} elemento(s)` : "",
      ]
        .filter(Boolean)
        .join(" / ")
    : undefined;
  const selectedCodes = selectedLine
    ? unique([selectedLine.cbs_code, selectedLine.wbs_code, selectedLine.fbs_code, selectedLine.package_code]).join(
        " / "
      )
    : "";
  const selectedApuAssignment =
    selectedLine?.raw_data?.budget_item_assignment &&
    typeof selectedLine.raw_data.budget_item_assignment === "object" &&
    !Array.isArray(selectedLine.raw_data.budget_item_assignment)
      ? (selectedLine.raw_data.budget_item_assignment as Record<string, unknown>)
      : {};
  const selectedApuLabel = [
    selectedApuAssignment.cost_item_code,
    selectedApuAssignment.cost_item_name,
    selectedApuAssignment.source_key,
  ]
    .filter((value) => value !== null && value !== undefined && String(value).trim())
    .map(String)
    .join(" / ");
  const selectedTrace = selectedLine ? traceRefsForLine(selectedLine).join(" / ") : selectedIfcElement?.globalId || "";
  const selectedMeasurementRule =
    compact(selectedLine?.measurement_rule) || compact(selectedIfcElement?.ifcClass) || "Regla pendiente";
  const selectedGeometryEstimate = primaryRealGeometryEstimate(
    compact(selectedLine?.ifc_class) || compact(selectedIfcElement?.ifcClass),
    selectedIfcElement?.realQuantities
  );
  const geometryApprovalPayload =
    selectedLine && selectedGeometryEstimate
      ? buildControlledMeasurementPayloadFromRealGeometry(selectedLine, selectedGeometryEstimate, selectedTrace)
      : null;
  const tracedLineCount = lines.filter((line) => compact(line.element_guid) || compact(line.element_id)).length;
  const mappedLineCount = lines.filter((line) => line.mapping_status === "mapped").length;
  const isolatedGroup = treeGroups.find((group) => group.id === isolatedGroupId);
  const browserCapacity = browserCapacityForIfc(model?.source_size_bytes);
  const manifestStrategy = manifestStrategyLabel(viewerManifest);
  const manifestSummary = manifestPropertySummary(viewerManifest);
  const selectedPropertiesSummary = elementPropertiesStatus(elementProperties, elementPropertiesLoadStatus);
  const renderDiagnosticSummary = formatIfcRenderDiagnostics(renderDiagnostics);
  const omittedGeometryCount =
    renderDiagnostics.invalidGeometryRefs +
    renderDiagnostics.invalidMemoryRefs +
    renderDiagnostics.emptyGeometries +
    renderDiagnostics.conversionErrors;
  const webIfcHealthTone: IfcViewerTone = hasRenderableGeometry && !renderDiagnostics.limitReached ? "ready" : "review";
  const webIfcHealthLabel = hasRenderableGeometry
    ? renderDiagnostics.limitReached
      ? "Render parcial"
      : "Render controlado"
    : "Solo metadatos";
  const viewerEngineLabel =
    viewerManifest?.geometry_strategy === "backend_cache" ? "IfcOpenShell cache / Three.js" : "web-ifc / Three.js";
  const canPrepareGeometryCache = Boolean(
    projectId && model && viewerManifest?.geometry_strategy !== "backend_cache" && !isPreparingGeometryCache
  );
  const handlePrepareGeometryCache = async () => {
    if (!projectId || !model || isPreparingGeometryCache) return;
    setIsPreparingGeometryCache(true);
    setGeometryCacheStatus("Preparando cache backend...");
    try {
      const summary = await bimModelsApi.prepareGeometryCache(token, projectId, model.id);
      setGeometryCacheStatus(
        `Cache backend listo: ${summary.mesh_count.toLocaleString()} malla(s) / ${summary.triangle_count.toLocaleString()} triangulo(s).`
      );
      setManifestRefreshKey((current) => current + 1);
    } catch (error) {
      const message = error instanceof Error ? error.message : "No se pudo preparar el cache backend.";
      setGeometryCacheStatus(message);
    } finally {
      setIsPreparingGeometryCache(false);
    }
  };
  const operationModeLabel = `${viewPreset.toUpperCase()} / ${navigationMode === "walk" ? "Recorrido" : "Orbitar"}`;
  const sectionModeLabel = sectionEnabled
    ? `Seccion ${sectionAxis.toUpperCase()} / ${sectionPosition}%`
    : "Sin seccion";
  const filteredTraceRefs = unique(filteredTreeLines.flatMap(traceRefsForLine));
  const apuAssignedLineCount = lines.filter(hasApuAssignment).length;
  const forceObjectTreeOpen = Boolean(compact(treeSearch) || reviewFilter !== "all");
  const handleApplyVisualFilter = () => {
    if (!filteredTraceRefs.length) return;
    viewerCommandsRef.current?.filterRefs(filteredTraceRefs);
  };
  const handleSelectObjectTreeNode = (node: IfcObjectTreeNode) => {
    if (!node.representative) return;
    setSelectedLineId(node.representative.id);
    setSelectedIfcElement(null);
    viewerCommandsRef.current?.focusRefs(node.traceRefs);
  };
  const handleIsolateObjectTreeNode = (node: IfcObjectTreeNode) => {
    setIsolatedGroupId(node.groupId ?? "");
    viewerCommandsRef.current?.isolateRefs(node.traceRefs);
  };
  const handleClashDetection = () => {
    const summary = viewerCommandsRef.current?.clashes(Math.max(clashToleranceMm, 0) / 1000);
    if (summary) setClashSummary(summary);
  };
  const handleRibbonMenu = (menu: IfcRibbonMenu) => {
    if (menu === activeRibbonMenu) {
      setRibbonExpanded((current) => !current);
      return;
    }
    setActiveRibbonMenu(menu);
    setRibbonExpanded(true);
  };
  const handleRestoreViewer = () => {
    viewerCommandsRef.current?.resetVisibility();
    setSectionEnabled(false);
    setSectionPosition(50);
    setExplodeFactor(0);
    setVisualStyle("solid");
    setInteractionMode("select");
    setClashSummary(null);
  };
  const measurementLabel = pointMeasurement
    ? `${formatNumber(pointMeasurement.distanceMeters)} m`
    : interactionMode === "measure"
      ? "Esperando puntos"
      : "Inactiva";
  const selectionLabel =
    (selectedLine ? constructiveLabel(selectedLine) : "") ||
    selectedIfcElement?.name ||
    selectedIfcElement?.ifcClass ||
    selectedIfcElement?.globalId ||
    "Sin seleccion";
  const workspacePanelClass =
    objectExplorerOpen && propertiesPanelOpen
      ? "panels-both"
      : objectExplorerOpen
        ? "panel-explorer"
        : propertiesPanelOpen
          ? "panel-properties"
          : "panels-hidden";

  return (
    <section aria-label="Modelo IFC" className="bimViewer bimViewerWide ifcGeometryViewer">
      <IfcRibbonPortal hostId={ribbonHostId}>
        <section aria-label="Menus de funcionalidades IFC" className="bimViewerRibbon">
          <nav aria-label="Menus superiores IFC" className="bimRibbonTabs">
            {(
              [
                ["file", "Archivo"],
                ["view", "Vista"],
                ["tools", "Herramientas"],
                ["appearance", "Apariencia"],
                ["information", "Información"],
              ] as Array<[IfcRibbonMenu, string]>
            ).map(([menu, label]) => {
              const isActive = activeRibbonMenu === menu;
              const isOpen = isActive && ribbonExpanded;
              return (
                <button
                  aria-controls={isOpen ? `ifc-ribbon-${menu}` : undefined}
                  aria-expanded={isOpen}
                  className={isActive ? "active" : undefined}
                  key={menu}
                  onClick={() => handleRibbonMenu(menu)}
                  type="button"
                >
                  {label}
                </button>
              );
            })}
          </nav>

          {ribbonExpanded && activeRibbonMenu === "file" ? (
            <div aria-label="Archivo IFC" className="bimRibbonPanel" id="ifc-ribbon-file" role="region">
              {onLoadSource || onClearModel ? (
                <section className="bimRibbonGroup">
                  <div className="bimRibbonActions">
                    {onLoadSource ? (
                      <label
                        className={`bimRibbonAction bimRibbonUploadAction${sourceLoadDisabled ? " disabled" : ""}`}
                      >
                        <Upload size={23} />
                        <span>{sourceLoading ? "Cargando..." : "Cargar IFC o Excel"}</span>
                        <input
                          accept=".ifc,.xlsx,.xls,.csv"
                          aria-label="Load BIM/IFC or Excel quantities"
                          disabled={sourceLoadDisabled}
                          onChange={onLoadSource}
                          type="file"
                        />
                      </label>
                    ) : null}
                    {onClearModel ? (
                      <button
                        aria-label="Limpiar modelo"
                        className="bimRibbonAction"
                        disabled={clearModelDisabled}
                        onClick={onClearModel}
                        type="button"
                      >
                        <Trash2 size={23} />
                        <span>Limpiar modelo</span>
                      </button>
                    ) : null}
                  </div>
                  <span className="bimRibbonGroupLabel">Fuente</span>
                </section>
              ) : null}
              <section className="bimRibbonGroup">
                <div className="bimRibbonActions">
                  <button
                    aria-label="Fit IFC model"
                    className="bimRibbonAction"
                    disabled={!canLoadModel}
                    onClick={() => viewerCommandsRef.current?.fit()}
                    type="button"
                  >
                    <Maximize2 size={23} />
                    <span>Ajustar</span>
                  </button>
                  <button
                    aria-label="Restore IFC visibility"
                    className="bimRibbonAction"
                    disabled={!canLoadModel}
                    onClick={handleRestoreViewer}
                    type="button"
                  >
                    <RotateCcw size={23} />
                    <span>Restaurar</span>
                  </button>
                </div>
                <span className="bimRibbonGroupLabel">Modelo</span>
              </section>
              <section className="bimRibbonGroup bimRibbonFileGroup">
                <div className="bimRibbonFileInfo">
                  <Box size={22} />
                  <span>
                    <strong>{sourceName || "Modelo IFC pendiente"}</strong>
                    <small>{modelSummary || "Carga un IFC desde Scope Manager."}</small>
                  </span>
                </div>
                <span className="bimRibbonGroupLabel">Archivo IFC</span>
              </section>
              <section className="bimRibbonGroup">
                <div className="bimRibbonActions">
                  <button
                    className="bimRibbonAction"
                    disabled={!canPrepareGeometryCache}
                    onClick={handlePrepareGeometryCache}
                    type="button"
                  >
                    <Box size={23} />
                    <span>{isPreparingGeometryCache ? "Preparando" : "Preparar cache"}</span>
                  </button>
                </div>
                <span className="bimRibbonGroupLabel">Geometria</span>
              </section>
            </div>
          ) : null}

          {ribbonExpanded && activeRibbonMenu === "information" ? (
            <div
              aria-label="Información y estado del Scope Manager"
              className="bimRibbonInformationPanel"
              id="ifc-ribbon-information"
              role="region"
            >
              <div className="bimRibbonInformationContent">
                {informationContent ? (
                  <section aria-label="Resumen del Scope Manager" className="scopeManagerInformation">
                    {informationContent}
                  </section>
                ) : null}
                <section aria-label="Detalle tecnico BIM" className="bimModelInformation">
                  <div className="panelHeader compactHeader bimViewerHeader">
                    <div className="bimViewerTitle">
                      <h3>Modelo IFC</h3>
                      <span>Geometria real del archivo IFC guardado</span>
                      <small>{canLoadModel ? sourceName : "Carga un IFC para ver geometria real"}</small>
                      {modelSummary && <small>{modelSummary}</small>}
                      <small>{displayStatus}</small>
                    </div>
                    <span>{displayStats}</span>
                  </div>
                  <section aria-label="Preparacion comercial del visor BIM" className="bimCommercialReadiness">
                    <article className={commercialBlockers.length ? "review" : "ready"}>
                      <span>Estado comercial</span>
                      <strong>{commercialReadiness}</strong>
                      <small>
                        {commercialBlockers.length
                          ? commercialBlockers.slice(0, 3).join(" / ")
                          : "Geometria, seleccion, cantidades y georreferenciacion disponibles para piloto comercial."}
                      </small>
                    </article>
                    <article>
                      <span>Riesgo IFC</span>
                      <strong>{hasRenderableGeometry ? "Renderizable" : "Metadatos solamente"}</strong>
                      <small>{formatFileSize(model?.source_size_bytes)}</small>
                    </article>
                    <article>
                      <span>Trazabilidad</span>
                      <strong>
                        {tracedLineCount}/{lines.length}
                      </strong>
                      <small>Lineas con referencia BIM para seleccion y presupuesto.</small>
                    </article>
                  </section>
                  <section aria-label="Salud del visor IFC" className="bimViewerHealth">
                    <article className={browserCapacity.tone}>
                      <span>Capacidad navegador</span>
                      <strong>{browserCapacity.label}</strong>
                      <small>{browserCapacity.detail}</small>
                    </article>
                    <article
                      className={viewerManifest?.geometry_strategy === "backend_cache_required" ? "review" : "ready"}
                    >
                      <span>Revision/cache</span>
                      <strong>{manifestStrategy}</strong>
                      <small>{geometryCacheStatus || viewerManifest?.revision_id || manifestStatus}</small>
                      {model && viewerManifest?.geometry_strategy !== "backend_cache" ? (
                        <button
                          aria-label="Preparar cache backend"
                          className="bimInlineAction"
                          disabled={!canPrepareGeometryCache}
                          onClick={handlePrepareGeometryCache}
                          type="button"
                        >
                          {isPreparingGeometryCache ? "Preparando..." : "Preparar cache backend"}
                        </button>
                      ) : null}
                    </article>
                    <article className={viewerManifest?.property_index?.scan_status === "partial" ? "review" : "ready"}>
                      <span>Indice IFC</span>
                      <strong>{viewerManifest?.property_index?.scan_status ?? "pendiente"}</strong>
                      <small>{manifestSummary}</small>
                    </article>
                    <article className={webIfcHealthTone}>
                      <span>Estado web-ifc</span>
                      <strong>{webIfcHealthLabel}</strong>
                      <small>{renderDiagnosticSummary}</small>
                    </article>
                    <article className={omittedGeometryCount ? "review" : "ready"}>
                      <span>Mallas omitidas</span>
                      <strong>{omittedGeometryCount.toLocaleString()}</strong>
                      <small>
                        {omittedGeometryCount
                          ? `${renderDiagnostics.invalidGeometryRefs} refs invalidas / ${renderDiagnostics.invalidMemoryRefs} memoria / ${renderDiagnostics.conversionErrors} conversion`
                          : "Sin omisiones reportadas por el motor."}
                      </small>
                    </article>
                    <article className={tracedLineCount === lines.length ? "ready" : "review"}>
                      <span>Trazabilidad BIM</span>
                      <strong>
                        {tracedLineCount}/{lines.length || 0}
                      </strong>
                      <small>Lineas con GUID o Express ID para seleccionar elemento y aprobar cantidades.</small>
                    </article>
                  </section>
                  <section aria-label="Panel de operacion BIM" className="bimOperationStrip">
                    <article>
                      <span>Motor</span>
                      <strong>{viewerEngineLabel}</strong>
                      <small>{displayStats}</small>
                    </article>
                    <article>
                      <span>Modo</span>
                      <strong>{operationModeLabel}</strong>
                      <small>
                        {sectionModeLabel} / {visualStyle} / medir {measurementLabel}
                      </small>
                    </article>
                    <article>
                      <span>Modelo</span>
                      <strong>{sourceName || "Sin archivo IFC"}</strong>
                      <small>{modelSummary || "Sin metadatos de modelo"}</small>
                    </article>
                    <article>
                      <span>Seleccion</span>
                      <strong>{selectionLabel}</strong>
                      <small>
                        {isolatedGroup
                          ? `Aislado: ${isolatedGroup.storey} / ${isolatedGroup.ifcClass}`
                          : "Modelo completo visible"}
                      </small>
                    </article>
                    <article>
                      <span>Control</span>
                      <strong>
                        {mappedLineCount}/{lines.length || 0} codificadas
                      </strong>
                      <small>
                        {tracedLineCount}/{lines.length || 0} trazadas / {apuAssignedLineCount}/{lines.length || 0} con
                        APU / {treeGroups.length} grupo(s) IFC
                      </small>
                    </article>
                  </section>
                </section>
              </div>
            </div>
          ) : null}

          {ribbonExpanded && activeRibbonMenu === "view" ? (
            <div aria-label="IFC viewer controls" className="bimRibbonPanel" id="ifc-ribbon-view" role="region">
              <section className="bimRibbonGroup">
                <div className="bimRibbonActions">
                  <button
                    aria-label="Orbit IFC navigation"
                    className={`bimRibbonAction${navigationMode === "orbit" ? " active" : ""}`}
                    disabled={!canLoadModel}
                    onClick={() => setNavigationMode("orbit")}
                    type="button"
                  >
                    <Compass size={23} />
                    <span>Orbitar</span>
                  </button>
                  <button
                    aria-label="Walk IFC navigation"
                    className={`bimRibbonAction${navigationMode === "walk" ? " active" : ""}`}
                    disabled={!canLoadModel}
                    onClick={() => setNavigationMode("walk")}
                    type="button"
                  >
                    <MousePointer2 size={23} />
                    <span>Recorrer</span>
                  </button>
                </div>
                <span className="bimRibbonGroupLabel">Navegacion</span>
              </section>
              <section className="bimRibbonGroup">
                <div className="bimRibbonActions">
                  <button
                    aria-label="Fit IFC model"
                    className="bimRibbonAction"
                    disabled={!canLoadModel}
                    onClick={() => viewerCommandsRef.current?.fit()}
                    type="button"
                  >
                    <Maximize2 size={23} />
                    <span>Ajustar</span>
                  </button>
                </div>
                <span className="bimRibbonGroupLabel">Camara</span>
              </section>
              <section className="bimRibbonGroup">
                <div className="bimRibbonActions">
                  {(["top", "front", "right", "iso"] as ViewPreset[]).map((preset) => (
                    <button
                      aria-label={`${preset === "iso" ? "Iso" : `${preset[0].toUpperCase()}${preset.slice(1)}`} IFC view`}
                      className={`bimRibbonAction${viewPreset === preset ? " active" : ""}`}
                      disabled={!canLoadModel}
                      key={preset}
                      onClick={() => {
                        setViewPreset(preset);
                        viewerCommandsRef.current?.view(preset);
                      }}
                      type="button"
                    >
                      {preset === "iso" ? <Box size={23} /> : <Compass size={23} />}
                      <span>
                        {preset === "top"
                          ? "Superior"
                          : preset === "front"
                            ? "Frontal"
                            : preset === "right"
                              ? "Derecha"
                              : "Isometrica"}
                      </span>
                    </button>
                  ))}
                </div>
                <span className="bimRibbonGroupLabel">Vistas</span>
              </section>
            </div>
          ) : null}

          {ribbonExpanded && activeRibbonMenu === "tools" ? (
            <div
              aria-label="Herramientas abiertas de revision IFC"
              className="bimRibbonPanel"
              id="ifc-ribbon-tools"
              role="region"
            >
              <section className="bimRibbonGroup">
                <div className="bimRibbonActions">
                  <button
                    aria-label="Measure IFC distance"
                    className={`bimRibbonAction${interactionMode === "measure" ? " active" : ""}`}
                    disabled={!canLoadModel}
                    onClick={() => setInteractionMode((current) => (current === "measure" ? "select" : "measure"))}
                    type="button"
                  >
                    <ScanLine size={23} />
                    <span>Medir</span>
                    <small title={measurementStatus}>{measurementLabel}</small>
                  </button>
                </div>
                <span className="bimRibbonGroupLabel">Medicion</span>
              </section>
              <section className="bimRibbonGroup bimRibbonControlGroup">
                <div className="bimRibbonActions">
                  <button
                    aria-label="Section IFC model"
                    className={`bimRibbonAction${sectionEnabled ? " active" : ""}`}
                    disabled={!canLoadModel}
                    onClick={() => setSectionEnabled((current) => !current)}
                    type="button"
                  >
                    <ScanLine size={23} />
                    <span>Seccion</span>
                  </button>
                  <div aria-label="Section axis" className="bimSectionAxisGroup" role="group">
                    {(["x", "y", "z"] as SectionAxis[]).map((axis) => (
                      <button
                        aria-label={`Section axis ${axis.toUpperCase()}`}
                        className={sectionAxis === axis ? "active" : undefined}
                        disabled={!canLoadModel || !sectionEnabled}
                        key={axis}
                        onClick={() => setSectionAxis(axis)}
                        type="button"
                      >
                        {axis.toUpperCase()}
                      </button>
                    ))}
                  </div>
                  <label className="bimRibbonRange" htmlFor="ifc-section-position">
                    <span>
                      Plano {sectionAxis.toUpperCase()}: {sectionPosition}%
                    </span>
                    <input
                      disabled={!canLoadModel || !sectionEnabled}
                      id="ifc-section-position"
                      max="100"
                      min="0"
                      onChange={(event) => setSectionPosition(Number(event.target.value))}
                      step="1"
                      type="range"
                      value={sectionPosition}
                    />
                  </label>
                </div>
                <span className="bimRibbonGroupLabel">Seccionamiento</span>
              </section>
              <section className="bimRibbonGroup bimRibbonControlGroup">
                <div className="bimRibbonActions">
                  <Box size={23} />
                  <label className="bimRibbonRange" htmlFor="ifc-explode-factor">
                    <span>Explosion: {explodeFactor}%</span>
                    <input
                      disabled={!canLoadModel}
                      id="ifc-explode-factor"
                      max="100"
                      min="0"
                      onChange={(event) => setExplodeFactor(Number(event.target.value))}
                      step="5"
                      type="range"
                      value={explodeFactor}
                    />
                  </label>
                </div>
                <span className="bimRibbonGroupLabel">Explosion</span>
              </section>
              <section className="bimRibbonGroup bimRibbonControlGroup bimRibbonClashGroup">
                <div className="bimRibbonActions">
                  <Eye size={23} />
                  <div className="bimRibbonClashControl">
                    <label className="bimRibbonNumber" htmlFor="ifc-clash-tolerance">
                      <span>Tolerancia (mm)</span>
                      <input
                        disabled={!canLoadModel}
                        id="ifc-clash-tolerance"
                        min="0"
                        onChange={(event) => setClashToleranceMm(Number(event.target.value))}
                        step="1"
                        type="number"
                        value={clashToleranceMm}
                      />
                    </label>
                    <button
                      className="bimRibbonCompactAction"
                      disabled={!canLoadModel}
                      onClick={handleClashDetection}
                      type="button"
                    >
                      Detectar
                    </button>
                  </div>
                </div>
                <span className="bimRibbonGroupLabel">Colisiones</span>
              </section>
            </div>
          ) : null}

          {ribbonExpanded && activeRibbonMenu === "appearance" ? (
            <div aria-label="Apariencia IFC" className="bimRibbonPanel" id="ifc-ribbon-appearance" role="region">
              <section className="bimRibbonGroup">
                <div aria-label="Estilo visual" className="bimRibbonActions" role="group">
                  {(
                    [
                      ["solid", "Solido"],
                      ["xray", "Transparente"],
                      ["wireframe", "Alambrico"],
                    ] as Array<[IfcVisualStyle, string]>
                  ).map(([style, label]) => (
                    <button
                      aria-label={`Estilo visual ${label}`}
                      aria-pressed={visualStyle === style}
                      className={`bimRibbonAction${visualStyle === style ? " active" : ""}`}
                      disabled={!canLoadModel}
                      key={style}
                      onClick={() => setVisualStyle(style)}
                      type="button"
                    >
                      {style === "xray" ? <Eye size={23} /> : <Box size={23} />}
                      <span>{label}</span>
                    </button>
                  ))}
                </div>
                <span className="bimRibbonGroupLabel">Renderizado</span>
              </section>
              <section className="bimRibbonGroup">
                <nav aria-label="IFC viewer panel controls" className="bimRibbonActions">
                  <button
                    aria-label={objectExplorerOpen ? "Ocultar Object Explorer" : "Mostrar Object Explorer"}
                    aria-pressed={objectExplorerOpen}
                    className={`bimRibbonAction${objectExplorerOpen ? " active" : ""}`}
                    onClick={() => setObjectExplorerOpen((current) => !current)}
                    type="button"
                  >
                    <Box size={23} />
                    <span>Object Explorer</span>
                  </button>
                  <button
                    aria-label={propertiesPanelOpen ? "Ocultar Properties" : "Mostrar Properties"}
                    aria-pressed={propertiesPanelOpen}
                    className={`bimRibbonAction${propertiesPanelOpen ? " active" : ""}`}
                    onClick={() => setPropertiesPanelOpen((current) => !current)}
                    type="button"
                  >
                    <MousePointer2 size={23} />
                    <span>Properties</span>
                  </button>
                </nav>
                <span className="bimRibbonGroupLabel">Paneles</span>
              </section>
            </div>
          ) : null}
        </section>
      </IfcRibbonPortal>
      {clashSummary ? (
        <section aria-label="Resultados de interferencias IFC" className="bimClashResults">
          <div className="panelHeader compactHeader">
            <div>
              <h3>Interferencias geometricas</h3>
              <span>
                {clashSummary.results.length} resultado(s) / {clashSummary.checkedProducts} producto(s) revisado(s)
                {clashSummary.limited ? " / listado limitado" : ""}
              </span>
            </div>
            <button onClick={() => setClashSummary(null)} type="button">
              Cerrar
            </button>
          </div>
          {clashSummary.results.length ? (
            <div className="bimClashList">
              {clashSummary.results.slice(0, 24).map((clash, index) => (
                <article key={clash.key}>
                  <div>
                    <strong>
                      {clash.classA} / {clash.classB}
                    </strong>
                    <span>
                      {clash.nameA} ↔ {clash.nameB}
                    </span>
                    <small>Penetracion AABB estimada: {formatNumber(clash.penetration)} m</small>
                  </div>
                  <button
                    aria-label={`Aislar interferencia ${index + 1}`}
                    onClick={() => viewerCommandsRef.current?.isolateRefs([clash.refA, clash.refB])}
                    type="button"
                  >
                    <Eye size={13} /> Revisar
                  </button>
                </article>
              ))}
            </div>
          ) : (
            <p className="projectHint">
              No se detectaron penetraciones superiores a la tolerancia entre los productos visibles.
            </p>
          )}
        </section>
      ) : null}
      <div className={`bimViewerWorkspace ${workspacePanelClass}`}>
        <div
          aria-label="IFC model navigation canvas"
          className="bimViewerCanvasWrap ifcGeometryCanvasWrap"
          tabIndex={canLoadModel ? 0 : -1}
        >
          <canvas aria-label="IFC geometric model viewer" data-testid="ifc-geometry-viewer-canvas" ref={canvasRef} />
          {canLoadModel && !hasRenderableGeometry ? (
            <div className="bimViewerEmptyOverlay" role="status">
              <strong>Modelo registrado sin geometria renderizable</strong>
              <span>{displayStatus}</span>
              {georeferenceLabel ? <small>{georeferenceLabel}</small> : null}
              <small>
                Usa este archivo como evidencia/georreferenciacion o carga un IFC con productos geometricos para ver el
                edificio.
              </small>
            </div>
          ) : null}
          <div className="bimViewerCanvasMeta" aria-label="IFC viewer data basis">
            <strong>{canLoadModel ? "Geometria IFC guardada" : "Sin archivo IFC"}</strong>
            <span>{displayStats}</span>
          </div>
          <div className="bimViewerNavigationHint" aria-label="Modo de navegacion IFC">
            <strong>
              {interactionMode === "measure"
                ? "Modo medir"
                : navigationMode === "walk"
                  ? "Modo recorrido"
                  : "Modo orbitar"}
            </strong>
            <span>
              {interactionMode === "measure"
                ? "Haz clic en dos puntos de las mallas IFC. El resultado se expresa en metros."
                : navigationMode === "walk"
                  ? "WASD / flechas para avanzar. Arrastra para mirar. Doble clic centra un elemento."
                  : "Arrastra para orbitar. Shift + arrastrar desplaza. Rueda para zoom. Doble clic centra un elemento."}
            </span>
          </div>
          {pointMeasurement ? (
            <div className="bimViewerMeasurementBadge" aria-label="Medicion IFC activa">
              <strong>Distancia</strong>
              <span>{formatNumber(pointMeasurement.distanceMeters)} m</span>
            </div>
          ) : null}
          {(selectedLine || selectedIfcElement) && (
            <div className="bimViewerSelectionBadge" aria-label="Elemento IFC seleccionado">
              <strong>Elemento seleccionado</strong>
              <span>
                {constructiveLabel(selectedLine) || selectedIfcElement?.ifcClass || selectedIfcElement?.globalId}
              </span>
            </div>
          )}
        </div>
        {model && (
          <div className="bimViewerMetadata" aria-label="IFC model identity">
            <span>{modelIdentityText(modelIdentity, "project_name", "Proyecto IFC sin nombre publicado")}</span>
            <span>{modelIdentityText(modelIdentity, "site_name", "Sitio pendiente")}</span>
            <span>{modelIdentityText(modelIdentity, "building_name", "Edificio pendiente")}</span>
            {georeferenceLabel ? <span>{georeferenceLabel}</span> : null}
            {model.element_count === 0 ? <span>Sin productos geometricos detectados en metadatos</span> : null}
          </div>
        )}
        {georeferenceDetails.length ? (
          <section aria-label="Georreferenciacion del modelo" className="bimGeorefPanel">
            <div>
              <strong>Georreferenciacion detectada</strong>
              <span>Coordenadas publicadas por el IFC para ubicar el modelo en su sistema de referencia.</span>
            </div>
            <div className="bimGeorefFacts">
              {georeferenceDetails.map((item) => (
                <article key={item.label}>
                  <span>{item.label}</span>
                  <strong>{item.value}</strong>
                </article>
              ))}
            </div>
          </section>
        ) : model ? (
          <section aria-label="Georreferenciacion del modelo" className="bimGeorefPanel muted">
            <div>
              <strong>Sin georreferenciacion publicada</strong>
              <span>El IFC cargado no expone IFCSITE con latitud/longitud ni IFCMAPCONVERSION legible.</span>
            </div>
          </section>
        ) : null}
        <div className="bimViewerInspector">
          {objectExplorerOpen ? (
            <section aria-label="Arbol IFC" className="bimModelTree bimDockPanel">
              <div className="panelHeader compactHeader">
                <h3 aria-label="Object Explorer Arbol IFC">Object Explorer</h3>
                <span>
                  {objectTree.count
                    ? `${filteredObjectTree.count}/${objectTree.count} objeto(s)${isolatedGroupId ? " / aislado" : ""}`
                    : "Esperando cantidades trazadas"}
                </span>
              </div>
              {objectTree.count ? (
                <>
                  <label className="bimTreeSearch">
                    <Search size={14} />
                    <input
                      aria-label="Buscar en arbol IFC"
                      onChange={(event) => setTreeSearch(event.target.value)}
                      placeholder="Nivel, GUID, propiedad, CBS/WBS o APU"
                      type="search"
                      value={treeSearch}
                    />
                  </label>
                  <div className="bimTreeFilters">
                    <label>
                      <span>Filtro de control</span>
                      <select
                        aria-label="Filtro de control IFC"
                        onChange={(event) => setReviewFilter(event.target.value as IfcReviewFilter)}
                        value={reviewFilter}
                      >
                        <option value="all">Todos</option>
                        <option value="mapped">Con codificacion</option>
                        <option value="unmapped">Sin codificacion</option>
                        <option value="apu-assigned">Con APU</option>
                        <option value="apu-pending">APU pendiente</option>
                      </select>
                    </label>
                    <button disabled={!filteredTraceRefs.length} onClick={handleApplyVisualFilter} type="button">
                      <Eye size={13} /> Aplicar al modelo
                    </button>
                    <button onClick={() => viewerCommandsRef.current?.resetVisibility()} type="button">
                      Ver todo
                    </button>
                  </div>
                </>
              ) : null}
              {objectTree.count && filteredObjectTree.count ? (
                <div aria-label="Jerarquia de objetos IFC" className="bimTreeList bimObjectTree" role="tree">
                  <IfcObjectTreeBranch
                    forceOpen={forceObjectTreeOpen}
                    node={filteredObjectTree}
                    onIsolate={handleIsolateObjectTreeNode}
                    onSelect={handleSelectObjectTreeNode}
                    selectedLineId={selectedLineId}
                  />
                </div>
              ) : objectTree.count ? (
                <p className="projectHint">No hay objetos IFC que coincidan con la busqueda y el filtro actual.</p>
              ) : (
                <p className="projectHint">
                  El arbol se activa cuando la tabla de cantidades trae referencias de objetos IFC.
                </p>
              )}
            </section>
          ) : null}
          {propertiesPanelOpen ? (
            <section aria-label="Propiedades del elemento IFC" className="bimElementProperties bimDockPanel">
              <div className="panelHeader compactHeader">
                <h3>
                  <MousePointer2 size={16} /> Properties
                </h3>
                <span>{selectedLine || selectedIfcElement ? "Elemento seleccionado" : "Sin seleccion"}</span>
              </div>
              {selectedLine || selectedIfcElement ? (
                <div className="bimElementFacts">
                  <article>
                    <span>Elemento constructivo</span>
                    <strong>{constructiveLabel(selectedLine)}</strong>
                  </article>
                  <article>
                    <span>Referencia BIM</span>
                    <strong>{selectedTrace || selectedLine?.element_id || "Referencia pendiente"}</strong>
                  </article>
                  <article>
                    <span>Clase / Regla</span>
                    <strong>
                      {unique([
                        compact(selectedLine?.ifc_class),
                        compact(selectedLine?.measurement_rule),
                        compact(selectedIfcElement?.ifcClass),
                      ]).join(" / ") || "Clase IFC pendiente"}
                    </strong>
                  </article>
                  <article>
                    <span>Cantidad controlada</span>
                    <strong>{formatQuantity(selectedLine)}</strong>
                  </article>
                  <article>
                    <span>Regla de medicion</span>
                    <strong>{selectedMeasurementRule}</strong>
                  </article>
                  <article>
                    <span>Dimensiones geometricas L x A x H</span>
                    <strong>
                      {formatRealGeometryDimensions(
                        selectedIfcElement?.dimensions,
                        effectiveModelUnits || model?.units
                      )}
                    </strong>
                  </article>
                  <article>
                    <span>Cantidad geometrica real</span>
                    <strong title={selectedGeometryEstimate?.explanation}>
                      {formatGeometryEstimate(selectedGeometryEstimate)}
                    </strong>
                    {geometryApprovalPayload && onApproveControlledMeasurement ? (
                      <button
                        className="primaryAction geometryApprovalAction"
                        disabled={approvalDisabled}
                        onClick={() => onApproveControlledMeasurement(geometryApprovalPayload)}
                        type="button"
                      >
                        Usar cantidad geometrica
                      </button>
                    ) : null}
                  </article>
                  <article className="wideFact">
                    <span>Area / Volumen / Longitud reales</span>
                    <strong>
                      {selectedIfcElement?.realQuantities
                        ? [
                            formatGeometryEstimate(selectedIfcElement.realQuantities.area),
                            formatGeometryEstimate(selectedIfcElement.realQuantities.volume),
                            formatGeometryEstimate(selectedIfcElement.realQuantities.length),
                          ].join(" / ")
                        : "Selecciona geometria para calcular cantidades reales"}
                    </strong>
                  </article>
                  <article className="wideFact ifcPublishedProperties">
                    <span>Propiedades IFC publicadas</span>
                    <strong>{selectedPropertiesSummary}</strong>
                    {elementProperties?.found ? (
                      <div className="ifcPublishedPropertyGrid">
                        {elementProperties.type_name || elementProperties.predefined_type ? (
                          <small>
                            Tipo: {unique([elementProperties.type_name, elementProperties.predefined_type]).join(" / ")}
                          </small>
                        ) : null}
                        {elementProperties.materials.length ? (
                          <small>Materiales: {elementProperties.materials.slice(0, 4).join(" / ")}</small>
                        ) : null}
                        {elementProperties.quantities.slice(0, 4).map((quantity) => (
                          <small key={`${quantity.set_name}-${quantity.name}`}>
                            {quantity.set_name} / {quantity.name}:{" "}
                            {quantity.value === null
                              ? "sin valor"
                              : `${formatNumber(quantity.value)} ${quantity.unit || ""}`.trim()}
                          </small>
                        ))}
                        {elementProperties.property_sets.slice(0, 3).map((propertySet) => (
                          <small key={propertySet.step_id}>
                            {propertySet.name}:{" "}
                            {propertySet.properties
                              .slice(0, 4)
                              .map((property) => `${property.name}=${property.value || "sin valor"}`)
                              .join(" / ") || "sin propiedades simples publicadas"}
                          </small>
                        ))}
                      </div>
                    ) : null}
                  </article>
                  <article>
                    <span>Nivel / ubicacion</span>
                    <strong>
                      {unique([
                        compact(selectedLine?.project_name),
                        compact(selectedLine?.building_name),
                        compact(selectedLine?.storey),
                        compact(selectedLine?.zone_name),
                      ]).join(" / ") || "Ubicacion pendiente"}
                    </strong>
                  </article>
                  <article className="wideFact">
                    <span>Integracion APU</span>
                    <strong>{selectedApuLabel || "APU pendiente de asignacion"}</strong>
                    {selectedApuLabel ? (
                      <small>
                        {[
                          selectedApuAssignment.budget_unit
                            ? `Unidad ${String(selectedApuAssignment.budget_unit)}`
                            : "",
                          Number.isFinite(Number(selectedApuAssignment.unit_rate))
                            ? `PU ${formatNumber(Number(selectedApuAssignment.unit_rate))}`
                            : "",
                          selectedApuAssignment.currency ? String(selectedApuAssignment.currency) : "",
                        ]
                          .filter(Boolean)
                          .join(" / ")}
                      </small>
                    ) : null}
                  </article>
                  <article className="wideFact">
                    <span>CBS / WBS / FBS / Paquete</span>
                    <strong>{selectedCodes || "Codigos de control pendientes"}</strong>
                  </article>
                </div>
              ) : (
                <p className="projectHint">
                  Selecciona un grupo del arbol o haz clic sobre la geometria para ver propiedades y trazabilidad.
                </p>
              )}
            </section>
          ) : null}
        </div>
      </div>
      <div className="bimViewerLegend" aria-label="IFC geometry viewer legend">
        <span>
          <i className="legendDot classColor" /> Geometria desde malla IFC
        </span>
        <span>
          <i className="legendDot mapped" /> web-ifc
        </span>
        <span>
          <i className="legendDot review" /> Archivo fuente retenido por la carga
        </span>
      </div>
    </section>
  );
}
