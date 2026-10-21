import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { normalizeScopeOverview, scopeApi } from "./api";
import { canonicalViewerModel, canonicalViewerProvider } from "./viewerAdapter";
import ScopeManagerWorkspace from "./ScopeManagerWorkspace";
import ScopeItemsWorkspace from "./ScopeItemsWorkspace";
import StrategyWorkspace from "./StrategyWorkspace";
import PlanItemsWorkspace from "./PlanItemsWorkspace";
import ScopeProfilesAdminView from "./ScopeProfilesAdminView";
import type { ModelVersion, ScopeItem, ScopeOverview } from "./types";

const empty: ScopeOverview = {
  context: {},
  allowed_actions: [],
  configuration: {},
  models: [],
  imports: [],
  items: [],
  revisions: [],
  baselines: [],
  strategies: [],
  plan_items: [],
  derived_models: [],
  version: 1,
};
const object = {
  id: 5,
  model_version_id: 13,
  source_identity: "guid:original",
  guid: "original",
  express_id: 90,
  ifc_class: "IfcWall",
  name: "Wall A",
  properties: { fire_rating: "2h" },
  quantities: [{ name: "NetVolume", value: 1.2, unit: "m3", source: "IFCELEMENTQUANTITY" }],
  classification: [],
  discipline: "ARCH",
  level: "L1",
  area: "A",
  zone: "Z",
  system: "",
  materials: ["Concrete"],
  geometry_reference: {},
  scope_item_ids: [],
  plan_item_ids: [],
};
const model: ModelVersion = {
  id: 13,
  version: 1,
  status: "STAGED",
  model_id: "ARCH",
  model_code: "ARCH",
  model_version_id: 13,
  revision: 1,
  source_file_name: "source.ifc",
  source_hash: "a".repeat(64),
  schema: "IFC4",
  units: { code: "m", known: true, basis: "PROJECT_UNIT" },
  is_current: false,
  validation_summary: {},
  diff: {},
  object_count: 1,
  imported_at: "2026-10-20",
  imported_by: 2,
  supersedes: null,
  objects_json: [object],
};
const item = {
  id: 70,
  version: 1,
  status: "APPROVED",
  scope_code: "S-1",
  name: "Controlled slab",
  description: "",
  parent_scope_item_id: null,
  scope_item_key: "lineage",
  scope_type: "DELIVERABLE",
  scope_nature: "INSTALL",
  discipline: "",
  area: "",
  zone: "",
  system: "",
  location: "",
  quantity: "20",
  unit: "m2",
  source_type: "MANUAL",
  source_reference: "survey",
  source_revision: "",
  revision: 1,
  model_object_ids: [],
  source_quantity: "20",
  approved_quantity: "20",
  current_quantity: "20",
  measurement_method: "MANUAL",
} as ScopeItem;
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

describe("O1B-A frontend contracts — component tests, not browser release proof", () => {
  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
  });
  it("uses only canonical project scope API routes", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(response(empty));
    await scopeApi.overview("actor", 701);
    expect(fetch.mock.calls[0][0]).toBe("/api/v1/scope/projects/701/overview");
    expect(fetch.mock.calls).toHaveLength(1);
  });
  it("sends O1A-compatible ETag and idempotency for a draft edit", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(response({}));
    await scopeApi.command("actor", 701, "/items/23", { name: "Changed" }, "stable-retry-key", 4, "PUT");
    expect(fetch.mock.calls[0][1]).toMatchObject({
      method: "PUT",
      headers: { "If-Match": '"4"', "Idempotency-Key": "stable-retry-key", Authorization: "Bearer actor" },
    });
  });
  it("uploads the actual file in multipart form without a guessed content type", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(response({ id: 1 }));
    await scopeApi.upload(
      "actor",
      701,
      "models",
      new File(["ISO-10303-21;"], "source.ifc"),
      "Controlled source upload",
      "upload-retry",
      "ARCH",
      "{}"
    );
    expect(fetch.mock.calls[0][0]).toBe("/api/v1/scope/projects/701/models");
    const options = fetch.mock.calls[0][1];
    expect((options?.body as FormData).get("model_code")).toBe("ARCH");
    expect(options?.headers).not.toHaveProperty("Content-Type");
  });
  it("does not fall back to legacy source routes after a canonical denial", async () => {
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(response({ detail: "DENIED" }, 403));
    await expect(canonicalViewerProvider("actor", 701, model).source()).rejects.toThrow("DENIED");
    expect(fetch.mock.calls).toHaveLength(1);
    expect(fetch.mock.calls[0][0]).toBe("/api/v1/scope/projects/701/models/13/source");
  });
  it("adapts unit metadata without silently assuming metres", () => {
    expect(canonicalViewerModel(model, 701).units).toBe("m");
    expect(canonicalViewerModel({ ...model, units: { known: false } }, 701).units).toBe("");
  });
  it("preserves original source quantity and property information in the reused viewer", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(response({ items: [object], total: 1 }));
    const details = await canonicalViewerProvider("actor", 701, model).elementProperties("original");
    expect(details.global_id).toBe("original");
    expect(details.quantities[0]).toMatchObject({ name: "NetVolume", value: 1.2, unit: "m3" });
    expect(details.property_sets[0].properties[0]).toMatchObject({ name: "fire_rating", value: "2h" });
  });
  it("derives display aliases only from immutable baseline and derived snapshots", () => {
    const normalized = normalizeScopeOverview({
      ...empty,
      baselines: [
        { id: 1, revision: 1, scope_revision_id: 10, original_baseline_id: null },
        { id: 2, revision: 2, scope_revision_id: 11, original_baseline_id: 1 },
      ] as ScopeOverview["baselines"],
      derived_models: [
        {
          id: 8,
          snapshot_json: { objects: [{ object_id: 5 }], memberships: [{ plan_item_id: 9 }], split_rule: "LOGICAL" },
        },
      ] as ScopeOverview["derived_models"],
    });
    expect(normalized.baselines.map((row) => [row.is_original, row.is_current])).toEqual([
      [true, false],
      [false, true],
    ]);
    expect(normalized.derived_models[0]).toMatchObject({
      model_object_ids: [5],
      plan_item_ids: [9],
      status: "IMMUTABLE",
    });
  });
  it("shows four coherent submodules and no mutations for a read-only user", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(response(empty));
    render(<ScopeManagerWorkspace token="viewer" workspaceId={701} />);
    expect(await screen.findByRole("navigation", { name: "Scope Manager submodules" })).toBeInTheDocument();
    for (const name of ["3D Model", "Scope Items", "Strategy & Path of Execution", "Plan Items"])
      expect(screen.getByRole("button", { name })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Importar IFC a staging" })).not.toBeInTheDocument();
  });
  it("exposes a denial without showing a guessed Project or Scope state", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(response({ detail: "SCOPE_PROJECT_DENIED" }, 403));
    render(<ScopeManagerWorkspace token="denied" workspaceId={701} />);
    expect(await screen.findByRole("alert")).toHaveTextContent("SCOPE_PROJECT_DENIED");
    expect(screen.queryByRole("navigation", { name: "Scope Manager submodules" })).not.toBeInTheDocument();
  });
  it("creates manual Scope with explicit nature, quantity and unit", () => {
    const command = vi.fn().mockResolvedValue({});
    render(
      <ScopeItemsWorkspace
        data={empty}
        busy={false}
        command={command}
        can={(action) => action === "item.edit"}
        upload={vi.fn()}
      />
    );
    fireEvent.change(screen.getByLabelText("Scope Code", { exact: true }), { target: { value: "S-NEW" } });
    fireEvent.change(screen.getByLabelText("Scope Name", { exact: true }), { target: { value: "Temporary access" } });
    fireEvent.change(screen.getByLabelText("Scope Nature", { exact: true }), { target: { value: "TEMPORARY" } });
    fireEvent.change(screen.getByLabelText("Motivo Scope", { exact: true }), {
      target: { value: "Reviewed manual definition" },
    });
    fireEvent.submit(screen.getByRole("button", { name: "Crear Scope manual" }).closest("form")!);
    expect(command).toHaveBeenCalledWith(
      "/items",
      expect.objectContaining({
        scope_code: "S-NEW",
        scope_nature: "TEMPORARY",
        quantity: 1,
        unit: "ea",
        source_type: "MANUAL",
      }),
      undefined,
      "POST"
    );
  });
  it("keeps approved Scope read-only and offers a successor rather than editing baseline facts", () => {
    render(
      <ScopeItemsWorkspace
        data={{ ...empty, items: [item] }}
        busy={false}
        command={vi.fn()}
        can={() => true}
        upload={vi.fn()}
      />
    );
    fireEvent.click(screen.getByRole("button", { name: "Ver Scope" }));
    expect(screen.getByLabelText("Quantity", { exact: true })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Preparar Scope sucesor" })).toBeInTheDocument();
    expect(screen.getByLabelText("Incluir Scope S-1")).toBeDisabled();
  });
  it("sends governed AWP applicability rather than an unsupported authority flag", () => {
    const command = vi.fn().mockResolvedValue({});
    render(<StrategyWorkspace data={empty} busy={false} command={command} can={() => true} />);
    for (const [label, value] of [
      ["Strategy Code", "STR-1"],
      ["Strategy Name", "Area sequence"],
      ["Motivo estrategia", "Controlled execution approach"],
      ["Path Code", "P-1"],
      ["Path Name", "Area A"],
    ])
      fireEvent.change(screen.getByLabelText(label, { exact: true }), { target: { value } });
    fireEvent.click(screen.getByRole("button", { name: "Agregar Execution Path" }));
    fireEvent.submit(screen.getByRole("button", { name: "Crear Execution Strategy DRAFT" }).closest("form")!);
    expect(command).toHaveBeenCalledWith(
      "/strategies",
      expect.objectContaining({ awp_applicability: "OPTIONAL" }),
      undefined,
      "POST"
    );
    expect(command.mock.calls[0][1]).not.toHaveProperty("awp_applicable");
  });
  it("clearly marks downstream mappings inactive", () => {
    render(
      <PlanItemsWorkspace
        data={empty}
        token="reader"
        workspaceId={701}
        busy={false}
        command={vi.fn()}
        can={() => false}
      />
    );
    expect(screen.getByRole("heading", { name: "Integraciones futuras · no activas" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Crear Plan Item" })).not.toBeInTheDocument();
  });
  it("does not expose ADMIN profile editing after a backend denial", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValue(response({ detail: "SCOPE_ADMIN_DENIED" }, 403));
    render(<ScopeProfilesAdminView token="reader" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("SCOPE_ADMIN_DENIED");
    expect(screen.queryByRole("button", { name: "Crear Scope Profile DRAFT" })).not.toBeInTheDocument();
  });
});
