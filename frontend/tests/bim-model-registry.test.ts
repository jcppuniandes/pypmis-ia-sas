import { afterEach, describe, expect, it, vi } from "vitest";
import { bimModels } from "../src/api/bimModels";

describe("bim model registry api", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("lists and uploads IFC coordination models under the selected project", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify([
            {
              id: 10,
              project_id: 1,
              source_file_name: "wellness.ifc",
              source_type: "ifc",
              source_size_bytes: 2500,
              status: "uploaded",
              schema: "IFC2X3",
              units: "millimeters",
              element_count: 779,
              storey_count: 3,
              model_identity: { project_name: "Wellness Center" },
              created_at: "2026-06-03T10:00:00Z",
              updated_at: "2026-06-03T10:00:00Z",
            },
          ]),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            id: 11,
            project_id: 1,
            source_file_name: "next.ifc",
            source_type: "ifc",
            source_size_bytes: 1800,
            status: "uploaded",
            schema: "IFC4",
            units: "meters",
            element_count: 100,
            storey_count: 1,
            model_identity: {},
            created_at: "2026-06-03T10:00:00Z",
            updated_at: "2026-06-03T10:00:00Z",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);

    const models = await bimModels.list("token", 1);
    const uploaded = await bimModels.upload("token", 1, new File(["ISO-10303-21;"], "next.ifc"));

    expect(models[0].source_file_name).toBe("wellness.ifc");
    expect(uploaded.schema).toBe("IFC4");
    expect(String(fetchMock.mock.calls[0][0])).toContain("/api/v1/projects/1/bim-models");
    expect(fetchMock.mock.calls[0][1]).toMatchObject({
      headers: expect.objectContaining({ Authorization: "Bearer token" }),
    });
    expect(fetchMock.mock.calls[1][1]).toMatchObject({
      method: "POST",
      headers: expect.objectContaining({ Authorization: "Bearer token" }),
    });
    expect(fetchMock.mock.calls[1][1]?.body).toBeInstanceOf(FormData);
  });

  it("fetches viewer manifest and element properties for the stored IFC model", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            model_id: 10,
            project_id: 1,
            source_file_name: "wellness.ifc",
            source_size_bytes: 2500,
            source_sha256: "abc",
            revision_id: "IFC-M10-abc",
            engine: "web-ifc/three",
            cache_status: "metadata_manifest_ready",
            geometry_strategy: "direct_browser",
            schema: "IFC4",
            units: "meters",
            project_name: "Wellness Center",
            site_name: "Default",
            building_name: "Main",
            georeferencing: {},
            product_count: 1,
            storey_count: 1,
            class_summary: [{ ifc_class: "IfcColumn", count: 1 }],
            property_index: {
              scan_status: "complete",
              scan_limit_bytes: 100,
              indexed_products: 1,
              property_sets: 1,
              quantity_sets: 1,
              type_relations: 1,
            },
            limits: { direct_browser_bytes: 10, backend_cache_required_bytes: 20 },
            warnings: [],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      )
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            model_id: 10,
            lookup_key: "GUID-1",
            found: true,
            scan_status: "complete",
            scan_limit_bytes: 100,
            step_id: "#20",
            global_id: "GUID-1",
            ifc_class: "IfcColumn",
            name: "Column A",
            type_name: "Column 40x40",
            predefined_type: "USERDEFINED",
            property_sets: [{ name: "Pset_Column", properties: [{ name: "Reference", value: "C-01", type: "IfcPropertySingleValue" }], step_id: "#30" }],
            quantities: [{ name: "GrossVolume", set_name: "Qto_Column", source: "IFCELEMENTQUANTITY", step_id: "#41", unit: "m3", value: 12.5 }],
            materials: ["Concrete C30"],
            classifications: [],
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      );
    vi.stubGlobal("fetch", fetchMock);

    const manifest = await bimModels.manifest("token", 1, 10);
    const properties = await bimModels.elementProperties("token", 1, 10, "GUID-1");

    expect(manifest.revision_id).toBe("IFC-M10-abc");
    expect(properties.materials).toEqual(["Concrete C30"]);
    expect(String(fetchMock.mock.calls[1][0])).toContain("element_key=GUID-1");
  });

  it("requests backend geometry cache preparation for the stored IFC model", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          status: "ready",
          model_id: 10,
          project_id: 1,
          revision_id: "IFC-M10-abc-GEOM",
          engine: "fake-ifc-converter",
          mesh_count: 1,
          triangle_count: 12,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const cache = await bimModels.prepareGeometryCache("token", 1, 10);

    expect(cache.status).toBe("ready");
    expect(cache.mesh_count).toBe(1);
    expect(String(fetchMock.mock.calls[0][0])).toContain("/api/v1/projects/1/bim-models/10/viewer-cache");
    expect(fetchMock.mock.calls[0][1]).toMatchObject({
      method: "POST",
      headers: expect.objectContaining({ Authorization: "Bearer token" }),
    });
  });

  it("fetches the prepared backend geometry cache artifact", async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          version: 1,
          engine: "ifcopenshell-geometry",
          model_id: 10,
          project_id: 1,
          stats: { product_count: 1, mesh_count: 1, triangle_count: 1 },
          products: [
            {
              express_id: 20,
              global_id: "GUID-1",
              ifc_class: "IfcColumn",
              name: "Column A",
              mesh: { vertices: [0, 0, 0, 1, 0, 0, 0, 1, 0], indices: [0, 1, 2] },
            },
          ],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    const artifact = await bimModels.geometryCache("token", 1, 10);

    expect(artifact.engine).toBe("ifcopenshell-geometry");
    expect(artifact.products[0].global_id).toBe("GUID-1");
    expect(String(fetchMock.mock.calls[0][0])).toContain("/api/v1/projects/1/bim-models/10/geometry-cache");
    expect(fetchMock.mock.calls[0][1]).toMatchObject({
      headers: expect.objectContaining({ Authorization: "Bearer token" }),
    });
  });
});
