import type { BimViewerSourceProvider } from "../../lib/bimViewerSource";
import type { BimModel, BimElementProperties, QuantityTakeoffLine } from "../../types";
import { scopeApi } from "./api";
import type { ModelObject, ModelVersion } from "./types";

export function modelUnitCode(model: ModelVersion): string {
  return typeof model.units === "string" ? model.units : (model.units.code ?? "");
}

export function canonicalViewerModel(model: ModelVersion, workspaceId: number): BimModel {
  return {
    id: model.id,
    project_id: workspaceId,
    source_file_name: model.source_file_name,
    source_type: "ifc",
    source_sha256: model.source_hash,
    revision_id: `scope-model-${model.id}-r${model.revision}`,
    source_size_bytes: model.source_size_bytes ?? 0,
    status: model.status,
    schema: model.schema,
    units: modelUnitCode(model),
    element_count: model.object_count,
    storey_count: new Set((model.objects_json ?? []).map((o) => o.level).filter(Boolean)).size,
    model_identity: { model_code: model.model_code },
    created_at: model.imported_at,
    updated_at: model.imported_at,
  };
}

export function canonicalViewerLines(objects: ModelObject[], workspaceId: number): QuantityTakeoffLine[] {
  return objects.map((object) => ({
    id: object.id,
    project_id: workspaceId,
    run_id: 0,
    source_row_id: object.source_identity,
    element_id: String(object.express_id),
    element_guid: object.guid,
    ifc_class: object.ifc_class,
    category: object.ifc_class,
    family: "",
    type_name: "",
    instance_name: object.name,
    project_name: "Canonical Scope source",
    site_name: "",
    building_name: "",
    storey: object.level,
    system_name: object.system,
    zone_name: object.zone,
    assembly_name: "",
    classification_system: "",
    classification_code: typeof object.classification === "string" ? object.classification : "",
    quantity: 0,
    unit: "",
    measurement_rule: "SOURCE_METADATA_ONLY",
    wbs_code: "",
    cbs_code: "",
    fbs_code: "",
    package_code: "",
    wbs_id: null,
    cbs_id: null,
    fbs_id: null,
    work_package_id: null,
    mapping_status: object.scope_item_ids?.length ? "mapped" : "unmapped",
    validation_notes: "Read-only IFC source; not approved Scope or quantity.",
    raw_data: {
      ...object.properties,
      source_model_version_id: object.model_version_id,
      scope_item_ids: object.scope_item_ids,
    },
    created_at: "",
    updated_at: "",
  }));
}

function objectProperties(model: ModelVersion, object: ModelObject | undefined, key: string): BimElementProperties {
  return {
    model_id: model.id,
    lookup_key: key,
    found: Boolean(object),
    scan_status: "complete",
    scan_limit_bytes: 0,
    step_id: object ? `#${object.express_id}` : "",
    global_id: object?.guid ?? "",
    ifc_class: object?.ifc_class ?? "",
    name: object?.name ?? "",
    type_name: "",
    predefined_type: "",
    materials: object?.materials ?? [],
    classifications: Array.isArray(object?.classification)
      ? object.classification.map((entry: Record<string, unknown>) => ({
          code: String(entry.code ?? entry.identification ?? ""),
          name: String(entry.name ?? ""),
          step_id: String(entry.step_id ?? ""),
          type: String(entry.type ?? "IFC_CLASSIFICATION"),
        }))
      : [],
    quantities: Array.isArray(object?.quantities)
      ? object.quantities.map((entry: Record<string, unknown>) => ({
          name: String(entry.name ?? ""),
          value: Number.isFinite(Number(entry.value)) ? Number(entry.value) : null,
          unit: String(entry.unit ?? ""),
          set_name: String(entry.set_name ?? ""),
          source: String(entry.source ?? "IFC"),
          step_id: entry.express_id ? `#${entry.express_id}` : "",
        }))
      : [],
    property_sets: object
      ? [
          {
            name: "Immutable source properties",
            step_id: `#${object.express_id}`,
            properties: Object.entries(object.properties ?? {}).map(([name, value]) => ({
              name,
              value: typeof value === "string" ? value : JSON.stringify(value),
              unit: "",
              type: typeof value,
              step_id: "",
            })),
          },
        ]
      : [],
  };
}

export function canonicalViewerProvider(
  token: string,
  workspaceId: number,
  model: ModelVersion
): BimViewerSourceProvider {
  return {
    source: () => scopeApi.source(token, workspaceId, model.id),
    manifest: async () => {
      const { items } = await scopeApi.objects(token, workspaceId, model.id);
      const classes = new Map<string, number>();
      items.forEach((object) => classes.set(object.ifc_class, (classes.get(object.ifc_class) ?? 0) + 1));
      return {
        model_id: model.id,
        project_id: workspaceId,
        source_file_name: model.source_file_name,
        source_size_bytes: model.source_size_bytes ?? 0,
        source_sha256: model.source_hash,
        revision_id: `scope-model-${model.id}-r${model.revision}`,
        engine: "web-ifc / Three.js",
        cache_status: "CANONICAL_SOURCE",
        geometry_strategy: "direct_browser",
        schema: model.schema,
        units: modelUnitCode(model),
        project_name: "Canonical Scope source",
        site_name: "",
        building_name: "",
        georeferencing: {},
        product_count: items.length,
        storey_count: new Set(items.map((o) => o.level).filter(Boolean)).size,
        class_summary: [...classes].map(([ifc_class, count]) => ({ ifc_class, count })),
        property_index: {
          scan_status: "complete",
          scan_limit_bytes: 0,
          indexed_products: items.length,
          property_sets: items.filter((o) => Object.keys(o.properties ?? {}).length).length,
          quantity_sets: 0,
          type_relations: 0,
        },
        limits: { direct_browser_bytes: 100 * 1024 * 1024, backend_cache_required_bytes: 100 * 1024 * 1024 },
        warnings: [],
      };
    },
    elementProperties: async (key: string) => {
      const { items } = await scopeApi.objects(token, workspaceId, model.id);
      return objectProperties(
        model,
        items.find((object) =>
          [object.guid, String(object.express_id), `#${object.express_id}`, object.source_identity].includes(key)
        ),
        key
      );
    },
  };
}
