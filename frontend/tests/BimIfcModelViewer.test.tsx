import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, vi } from "vitest";
import * as THREE from "three";
import BimIfcModelViewer from "../src/components/BimIfcModelViewer";
import {
  applyIfcSelectionVisuals,
  buildBackendCacheGeometryMeshes,
  buildControlledMeasurementPayloadFromRealGeometry,
  calculateRealGeometryQuantities,
  clearIfcSelectionVisuals,
  createIfcSelectionBoxHelper,
  detectIfcLengthUnitsFromText,
  formatRealGeometryDimensions,
  friendlyIfcRenderStatus,
  isValidIfcExpressId,
  isValidIfcMemoryRef,
  primaryRealGeometryEstimate,
  walkCameraStep,
} from "../src/components/BimIfcModelViewer";
import type { BimModel, QuantityTakeoffLine } from "../src/types";

const ifcModel: BimModel = {
  id: 77,
  project_id: 1,
  source_file_name: "wellness-center.ifc",
  source_type: "ifc",
  source_size_bytes: 987654,
  status: "uploaded",
  schema: "IFC2X3",
  units: "millimeters",
  element_count: 788,
  storey_count: 3,
  model_identity: {
    project_name: "Wellness Center",
    site_name: "Default",
    building_name: "Main Building",
    georeferencing: {
      latitude_decimal: 4.64,
      longitude_decimal: -74.086667,
      elevation: 2600.5,
      projected_crs: "EPSG:3116",
      map_conversion: {
        eastings: 1000.25,
        northings: 2000.5,
        orthogonal_height: 2600.5,
        scale: 1,
      },
    },
  },
  created_at: "2026-05-22T13:35:57Z",
  updated_at: "2026-05-22T13:35:57Z",
};

const tracedLines: QuantityTakeoffLine[] = [
  {
    id: 301,
    project_id: 1,
    run_id: 20,
    source_row_id: "#120:GrossVolume",
    element_id: "#120",
    element_guid: "2IRuU8Tqz92AICLQuWall01",
    ifc_class: "IfcWallStandardCase",
    category: "Muro arquitectonico",
    family: "Basic Wall",
    type_name: "Exterior 200mm",
    instance_name: "Basic Wall:Exterior 200mm:120",
    project_name: "Wellness Center",
    site_name: "Default",
    building_name: "Main Building",
    storey: "Ground floor",
    system_name: "",
    zone_name: "",
    assembly_name: "",
    classification_system: "",
    classification_code: "",
    quantity: 14.25,
    unit: "m2",
    measurement_rule: "NetSideArea",
    wbs_code: "01-ARQ",
    cbs_code: "CBS-01-ARQ-MUR",
    fbs_code: "FBS-OWN-01",
    package_code: "IWP-ARQ-001",
    wbs_id: 11,
    cbs_id: 22,
    fbs_id: 33,
    work_package_id: 44,
    mapping_status: "mapped",
    validation_notes: "",
    raw_data: {},
    created_at: "2026-05-22T13:35:57Z",
    updated_at: "2026-05-22T13:35:57Z",
  },
];

describe("BimIfcModelViewer", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("detects metric length units from IFC source text", () => {
    const units = detectIfcLengthUnitsFromText("#20=IFCSIUNIT(*,.LENGTHUNIT.,.MILLI.,.METRE.);");

    expect(units).toBe("millimeters");
  });

  it("rejects invalid web-ifc express ids before geometry calls", () => {
    expect(isValidIfcExpressId(1)).toBe(true);
    expect(isValidIfcExpressId(-1)).toBe(false);
    expect(isValidIfcExpressId(0)).toBe(false);
    expect(isValidIfcExpressId(1.5)).toBe(false);
    expect(isValidIfcExpressId(undefined)).toBe(false);
  });

  it("rejects invalid web-ifc memory references before array calls", () => {
    expect(isValidIfcMemoryRef(0, 12)).toBe(true);
    expect(isValidIfcMemoryRef(-1, 12)).toBe(false);
    expect(isValidIfcMemoryRef(10, 0)).toBe(false);
    expect(isValidIfcMemoryRef(10, -1)).toBe(false);
    expect(isValidIfcMemoryRef(10.5, 12)).toBe(false);
  });

  it("builds selectable Three meshes from the backend geometry cache artifact", () => {
    const materialCache = new Map<string, THREE.MeshStandardMaterial>();
    const result = buildBackendCacheGeometryMeshes(
      {
        version: 1,
        engine: "ifcopenshell-geometry",
        model_id: 77,
        project_id: 1,
        source_file_name: "wellness-center.ifc",
        source_sha256: "abc",
        revision_id: "IFC-M77-abc-GEOM",
        schema: "IFC2X3",
        units: "meters",
        generated_at: "2026-06-17T10:00:00",
        stats: { product_count: 1, mesh_count: 1, triangle_count: 1 },
        products: [
          {
            express_id: 20,
            global_id: "GUID-COLUMN-001",
            ifc_class: "IfcColumn",
            name: "Concrete Column",
            mesh: {
              vertices: [0, 0, 0, 1, 0, 0, 0, 1, 0],
              indices: [0, 1, 2],
            },
          },
        ],
      },
      materialCache
    );

    expect(result.meshes).toHaveLength(1);
    expect(result.diagnostics.meshesRendered).toBe(1);
    expect(result.diagnostics.trianglesRendered).toBe(1);
    expect(result.diagnostics.productsScanned).toBe(1);
    expect(result.meshes[0].geometry.getAttribute("position").count).toBe(3);
    expect(result.meshes[0].geometry.getIndex()?.count).toBe(3);
    expect(result.meshes[0].userData.ifc).toMatchObject({
      expressId: 20,
      globalId: "GUID-COLUMN-001",
      ifcClass: "IfcColumn",
      name: "Concrete Column",
    });
  });

  it("translates web-ifc invalid geometry references into an operational status", () => {
    const status = friendlyIfcRenderStatus(
      new Error('Passing a number "-1" from JS side to C/C++ side to an argument of type "unsigned int"')
    );

    expect(status).toMatch(/IFC registrado/i);
    expect(status).toMatch(/referencias geometricas invalidas/i);
    expect(status).not.toMatch(/unsigned int|-1/);
  });

  it("translates browser memory failures into a safe IFC viewer status", () => {
    const status = friendlyIfcRenderStatus(new Error("RuntimeError: memory access out of bounds"));

    expect(status).toMatch(/memoria del navegador/i);
    expect(status).toMatch(/cache backend/i);
    expect(status).not.toMatch(/RuntimeError|out of bounds/i);
  });

  it("shows a clear empty geometry overlay for registered georeferenced IFC files without renderable meshes", () => {
    const emptyModel = { ...ifcModel, element_count: 0 };

    render(<BimIfcModelViewer projectId={1} model={emptyModel} token="tok" />);

    const viewer = screen.getByRole("region", { name: /modelo ifc/i });
    expect(within(viewer).getByRole("status")).toHaveTextContent(/Modelo registrado sin geometria renderizable/i);
    expect(within(viewer).getByRole("status")).toHaveTextContent(/Geo 4.640000, -74.086667 \/ EPSG:3116/i);
  });

  it("presents the stored IFC as real model geometry, separate from inventory preview", () => {
    render(<BimIfcModelViewer projectId={1} model={ifcModel} token="tok" />);

    const viewer = screen.getByRole("region", { name: /modelo ifc/i });

    expect(within(viewer).getByRole("heading", { name: /modelo ifc/i })).toBeInTheDocument();
    expect(within(viewer).getByText(/geometria real del archivo ifc guardado/i)).toBeInTheDocument();
    expect(within(viewer).getAllByText(/wellness-center.ifc/i).length).toBeGreaterThan(0);
    expect(within(viewer).getAllByText(/IFC2X3 \/ millimeters \/ 3 nivel/i).length).toBeGreaterThan(0);
    expect(within(viewer).getByText(/Estado comercial/i)).toBeInTheDocument();
    expect(within(viewer).getByText(/Comercial beta/i)).toBeInTheDocument();
    expect(within(viewer).getAllByText(/Trazabilidad/i).length).toBeGreaterThan(0);
    expect(within(viewer).getByRole("region", { name: /panel de operacion bim/i })).toBeInTheDocument();
    expect(within(viewer).getByText(/web-ifc \/ Three.js/i)).toBeInTheDocument();
    expect(within(viewer).getByText(/ISO \/ Orbitar/i)).toBeInTheDocument();
    const viewerHealth = within(viewer).getByRole("region", { name: /salud del visor ifc/i });
    expect(within(viewerHealth).getByText(/Capacidad navegador/i)).toBeInTheDocument();
    expect(within(viewerHealth).getByText(/Modelo liviano/i)).toBeInTheDocument();
    expect(within(viewerHealth).getByText(/Archivo IFC pequeño/i)).toBeInTheDocument();
    expect(within(viewerHealth).getByText(/Trazabilidad BIM/i)).toBeInTheDocument();
    expect(within(viewer).getByText(/Wellness Center/i)).toBeInTheDocument();
    expect(within(viewer).getByText(/Geo 4.640000, -74.086667 \/ EPSG:3116/i)).toBeInTheDocument();
    const georefPanel = within(viewer).getByRole("region", { name: /georreferenciacion del modelo/i });
    expect(georefPanel).toBeInTheDocument();
    expect(within(georefPanel).getByText(/Georreferenciacion detectada/i)).toBeInTheDocument();
    expect(within(georefPanel).getByText(/Lat \/ Long/i)).toBeInTheDocument();
    expect(within(georefPanel).getByText(/4.640000, -74.086667/i)).toBeInTheDocument();
    expect(within(georefPanel).getByText(/Este \/ Norte/i)).toBeInTheDocument();
    expect(within(georefPanel).getByText(/1,000.25, 2,000.50/i)).toBeInTheDocument();
    expect(within(viewer).getByTestId("ifc-geometry-viewer-canvas")).toBeInTheDocument();
    expect(within(viewer).queryByText(/inventory preview/i)).not.toBeInTheDocument();
  });

  it("warns when an IFC is too large for direct browser rendering", () => {
    const largeModel = { ...ifcModel, source_size_bytes: 145 * 1024 * 1024 };

    render(<BimIfcModelViewer projectId={1} model={largeModel} token="tok" />);

    const viewer = screen.getByRole("region", { name: /modelo ifc/i });
    const viewerHealth = within(viewer).getByRole("region", { name: /salud del visor ifc/i });

    expect(within(viewerHealth).getByText(/Requiere cache backend/i)).toBeInTheDocument();
    expect(within(viewerHealth).getByText(/preprocesar geometria/i)).toBeInTheDocument();
  });

  it("lets the user prepare a backend geometry cache from the IFC viewer health panel", async () => {
    const largeModel = { ...ifcModel, source_size_bytes: 145 * 1024 * 1024 };
    const manifestBase = {
      model_id: 77,
      project_id: 1,
      source_file_name: "wellness-center.ifc",
      source_size_bytes: largeModel.source_size_bytes,
      source_sha256: "abc",
      revision_id: "IFC-M77-abc",
      engine: "web-ifc/three",
      schema: "IFC2X3",
      units: "millimeters",
      project_name: "Wellness Center",
      site_name: "Default",
      building_name: "Main Building",
      georeferencing: {},
      product_count: 788,
      storey_count: 3,
      class_summary: [{ ifc_class: "IfcWallStandardCase", count: 41 }],
      property_index: {
        scan_status: "complete",
        scan_limit_bytes: 100,
        indexed_products: 788,
        property_sets: 1,
        quantity_sets: 1,
        type_relations: 1,
      },
      limits: { direct_browser_bytes: 10, backend_cache_required_bytes: 20 },
      warnings: [],
    };
    const fetchMock = vi.fn((url: string, init?: RequestInit) => {
      if (String(url).includes("viewer-cache")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              status: "ready",
              model_id: 77,
              project_id: 1,
              revision_id: "IFC-M77-abc-GEOM",
              engine: "fake-ifc-converter",
              mesh_count: 2,
              triangle_count: 24,
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          )
        );
      }
      if (String(url).includes("viewer-manifest")) {
        const hasPreparedCache = fetchMock.mock.calls.some((call) => String(call[0]).includes("viewer-cache"));
        return Promise.resolve(
          new Response(
            JSON.stringify({
              ...manifestBase,
              cache_status: hasPreparedCache ? "geometry_cache_ready" : "metadata_manifest_ready",
              geometry_strategy: hasPreparedCache ? "backend_cache" : "backend_cache_required",
              geometry_cache: hasPreparedCache
                ? {
                    status: "ready",
                    revision_id: "IFC-M77-abc-GEOM",
                    engine: "fake-ifc-converter",
                    mesh_count: 2,
                    triangle_count: 24,
                  }
                : {},
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          )
        );
      }
      return Promise.resolve(new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } }));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<BimIfcModelViewer projectId={1} model={largeModel} token="tok" />);

    const viewer = screen.getByRole("region", { name: /modelo ifc/i });
    const viewerHealth = within(viewer).getByRole("region", { name: /salud del visor ifc/i });
    await waitFor(() => expect(within(viewerHealth).getByText(/Cache backend requerido/i)).toBeInTheDocument());

    fireEvent.click(within(viewerHealth).getByRole("button", { name: /Preparar cache backend/i }));

    await waitFor(() => expect(within(viewerHealth).getByText(/Cache backend listo/i)).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/api/v1/projects/1/bim-models/77/viewer-cache"),
      expect.objectContaining({ method: "POST" })
    );
  });

  it("offers orbit and walk navigation modes without leaving the IFC viewer", () => {
    render(<BimIfcModelViewer projectId={1} model={ifcModel} token="tok" />);

    const viewer = screen.getByRole("region", { name: /modelo ifc/i });
    const toolbar = within(viewer).getByLabelText(/IFC viewer controls/i);

    expect(within(toolbar).getByRole("button", { name: /Orbit IFC navigation/i })).toHaveClass("active");
    expect(within(toolbar).getByRole("button", { name: /Front IFC view/i })).toBeInTheDocument();
    expect(within(toolbar).getByRole("button", { name: /Right IFC view/i })).toBeInTheDocument();
    expect(within(toolbar).getByRole("button", { name: /Walk IFC navigation/i })).toBeInTheDocument();
    expect(within(viewer).getByText(/Modo orbitar/i)).toBeInTheDocument();

    fireEvent.click(within(toolbar).getByRole("button", { name: /Front IFC view/i }));
    expect(within(toolbar).getByRole("button", { name: /Front IFC view/i })).toHaveClass("active");
    expect(within(viewer).getByText(/FRONT \/ Orbitar/i)).toBeInTheDocument();

    fireEvent.click(within(toolbar).getByRole("button", { name: /Walk IFC navigation/i }));

    expect(within(toolbar).getByRole("button", { name: /Walk IFC navigation/i })).toHaveClass("active");
    expect(within(viewer).getByText(/Modo recorrido/i)).toBeInTheDocument();
    expect(within(viewer).getByText(/WASD \/ flechas para avanzar/i)).toBeInTheDocument();
  });

  it("exposes controlled section axes for professional model inspection", () => {
    render(<BimIfcModelViewer projectId={1} model={ifcModel} token="tok" />);

    const viewer = screen.getByRole("region", { name: /modelo ifc/i });
    const toolbar = within(viewer).getByLabelText(/IFC viewer controls/i);

    fireEvent.click(within(toolbar).getByRole("button", { name: /Section IFC model/i }));

    const axisControls = within(toolbar).getByRole("group", { name: /Section axis/i });
    expect(within(axisControls).getByRole("button", { name: /Section axis X/i })).toHaveClass("active");
    expect(within(viewer).getByText(/Seccion X/i)).toBeInTheDocument();

    fireEvent.click(within(axisControls).getByRole("button", { name: /Section axis Z/i }));

    expect(within(axisControls).getByRole("button", { name: /Section axis Z/i })).toHaveClass("active");
    expect(within(viewer).getByText(/Seccion Z/i)).toBeInTheDocument();
  });

  it("moves the camera forward in walk navigation mode", () => {
    const camera = new THREE.PerspectiveCamera();
    camera.position.set(0, 1.7, 10);
    camera.lookAt(new THREE.Vector3(0, 1.7, 0));
    const target = new THREE.Vector3(0, 1.7, 0);

    walkCameraStep(camera, target, new Set(["w"]), 2);

    expect(camera.position.z).toBeLessThan(10);
    expect(target.z).toBeLessThan(0);
  });

  it("shows a model tree and selected element properties linked to controlled quantities", () => {
    render(<BimIfcModelViewer lines={tracedLines} projectId={1} model={ifcModel} token="tok" />);

    const viewer = screen.getByRole("region", { name: /modelo ifc/i });
    const tree = within(viewer).getByRole("region", { name: /arbol ifc/i });
    const properties = within(viewer).getByRole("region", { name: /propiedades del elemento ifc/i });

    expect(within(tree).getByRole("heading", { name: /arbol ifc/i })).toBeInTheDocument();
    expect(within(tree).getByLabelText(/buscar en arbol ifc/i)).toBeInTheDocument();
    expect(within(tree).getByText(/Ground floor/i)).toBeInTheDocument();
    expect(within(tree).getByText(/IfcWallStandardCase/i)).toBeInTheDocument();
    expect(within(tree).getByRole("button", { name: /Aislar Ground floor IfcWallStandardCase/i })).toBeInTheDocument();

    fireEvent.click(within(tree).getByRole("button", { name: /^Ground floor IfcWallStandardCase 1 elemento/i }));

    expect(within(properties).getByText(/Muro arquitectonico \/ Basic Wall \/ Exterior 200mm/i)).toBeInTheDocument();
    expect(within(properties).getByText(/2IRuU8Tqz92AICLQuWall01/i)).toBeInTheDocument();
    expect(within(properties).getByText(/Cantidad controlada/i)).toBeInTheDocument();
    expect(within(properties).getByText(/14.25 m2/i)).toBeInTheDocument();
    expect(within(properties).getByText(/Regla de medicion/i)).toBeInTheDocument();
    expect(within(properties).getAllByText(/NetSideArea/i).length).toBeGreaterThan(0);
    expect(within(properties).getByText(/CBS-01-ARQ-MUR \/ 01-ARQ \/ FBS-OWN-01 \/ IWP-ARQ-001/i)).toBeInTheDocument();
  });

  it("shows IFC published properties from the backend manifest for the selected element", async () => {
    const fetchMock = vi.fn((url: string) => {
      if (String(url).includes("viewer-manifest")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              model_id: 77,
              project_id: 1,
              source_file_name: "wellness-center.ifc",
              source_size_bytes: 987654,
              source_sha256: "abc",
              revision_id: "IFC-M77-abc",
              engine: "web-ifc/three",
              cache_status: "metadata_manifest_ready",
              geometry_strategy: "direct_browser",
              schema: "IFC2X3",
              units: "millimeters",
              project_name: "Wellness Center",
              site_name: "Default",
              building_name: "Main Building",
              georeferencing: {},
              product_count: 1,
              storey_count: 3,
              class_summary: [{ ifc_class: "IfcWallStandardCase", count: 1 }],
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
            { status: 200, headers: { "Content-Type": "application/json" } }
          )
        );
      }
      if (String(url).includes("element-properties")) {
        return Promise.resolve(
          new Response(
            JSON.stringify({
              model_id: 77,
              lookup_key: "2IRuU8Tqz92AICLQuWall01",
              found: true,
              scan_status: "complete",
              scan_limit_bytes: 100,
              step_id: "#120",
              global_id: "2IRuU8Tqz92AICLQuWall01",
              ifc_class: "IfcWallStandardCase",
              name: "Exterior Wall",
              type_name: "Exterior 200mm",
              predefined_type: "STANDARD",
              property_sets: [
                {
                  name: "Pset_WallCommon",
                  properties: [{ name: "FireRating", type: "IfcPropertySingleValue", value: "2h" }],
                  step_id: "#30",
                },
              ],
              quantities: [
                {
                  name: "NetSideArea",
                  set_name: "Qto_WallBaseQuantities",
                  source: "IFCELEMENTQUANTITY",
                  step_id: "#41",
                  unit: "m2",
                  value: 14.25,
                },
              ],
              materials: ["Concrete C30"],
              classifications: [],
            }),
            { status: 200, headers: { "Content-Type": "application/json" } }
          )
        );
      }
      return Promise.resolve(new Response("{}", { status: 200, headers: { "Content-Type": "application/json" } }));
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<BimIfcModelViewer lines={tracedLines} projectId={1} model={ifcModel} token="tok" />);

    const viewer = screen.getByRole("region", { name: /modelo ifc/i });
    await waitFor(() => expect(within(viewer).getByText(/IFC-M77-abc/i)).toBeInTheDocument());

    fireEvent.click(
      within(within(viewer).getByRole("region", { name: /arbol ifc/i })).getByRole("button", {
        name: /^Ground floor IfcWallStandardCase 1 elemento/i,
      })
    );

    const properties = within(viewer).getByRole("region", { name: /propiedades del elemento ifc/i });
    await waitFor(() => expect(within(properties).getByText(/1 Pset \/ 1 Qto \/ 1 material/i)).toBeInTheDocument());
    expect(within(properties).getByText(/Tipo: Exterior 200mm \/ STANDARD/i)).toBeInTheDocument();
    expect(within(properties).getByText(/Materiales: Concrete C30/i)).toBeInTheDocument();
    expect(within(properties).getByText(/Qto_WallBaseQuantities \/ NetSideArea: 14.25 m2/i)).toBeInTheDocument();
    expect(within(properties).getByText(/Pset_WallCommon: FireRating=2h/i)).toBeInTheDocument();
  });

  it("marks a selected IFC mesh with a distinct material and visible outline", () => {
    const originalMaterial = new THREE.MeshStandardMaterial({ color: 0x73828f });
    const selectedMaterial = new THREE.MeshStandardMaterial({ color: 0xffd166 });
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(1, 1, 1), originalMaterial);

    applyIfcSelectionVisuals([mesh], selectedMaterial);

    expect(mesh.material).toBe(selectedMaterial);
    expect(mesh.userData.selectionOriginalMaterial).toBe(originalMaterial);
    expect(mesh.children.some((child) => child.userData.ifcSelectionOutline === true)).toBe(true);

    clearIfcSelectionVisuals([mesh]);

    expect(mesh.material).toBe(originalMaterial);
    expect(mesh.children.some((child) => child.userData.ifcSelectionOutline === true)).toBe(false);
  });

  it("creates a high contrast selection box around the selected IFC product", () => {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(2, 3, 4), new THREE.MeshStandardMaterial());
    mesh.position.set(10, 5, -2);
    mesh.updateMatrixWorld(true);

    const helper = createIfcSelectionBoxHelper([mesh]);

    expect(helper.userData.ifcSelectionBox).toBe(true);
    expect(helper.renderOrder).toBeGreaterThan(50);
    expect(helper.box.containsPoint(new THREE.Vector3(10, 5, -2))).toBe(true);
  });

  it("calculates real mesh area, volume and length from selected IFC geometry", () => {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(2, 2, 2), new THREE.MeshStandardMaterial());

    const quantities = calculateRealGeometryQuantities([mesh], "meters");

    expect(quantities?.area.quantity).toBeCloseTo(24, 3);
    expect(quantities?.area.unit).toBe("m2");
    expect(quantities?.area.measurementRule).toBe("GeometryMeshArea");
    expect(quantities?.volume.quantity).toBeCloseTo(8, 3);
    expect(quantities?.volume.unit).toBe("m3");
    expect(quantities?.volume.measurementRule).toBe("GeometryMeshVolume");
    expect(quantities?.length.quantity).toBeCloseTo(2, 3);
    expect(quantities?.length.unit).toBe("m");
    expect(quantities?.length.measurementRule).toBe("GeometryMeshLength");
  });

  it("converts IFC millimeter geometry to metric quantities", () => {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(2000, 2000, 2000), new THREE.MeshStandardMaterial());

    const quantities = calculateRealGeometryQuantities([mesh], "millimeters");

    expect(quantities?.area.quantity).toBeCloseTo(24, 3);
    expect(quantities?.volume.quantity).toBeCloseTo(8, 3);
    expect(quantities?.length.quantity).toBeCloseTo(2, 3);
  });

  it("keeps already-normalized web-ifc geometry in meters when the IFC declares millimeters", () => {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(2, 2, 2), new THREE.MeshStandardMaterial());

    const quantities = calculateRealGeometryQuantities([mesh], "millimeters");

    expect(quantities?.area.quantity).toBeCloseTo(24, 3);
    expect(quantities?.volume.quantity).toBeCloseTo(8, 3);
    expect(quantities?.length.quantity).toBeCloseTo(2, 3);
  });

  it("formats real geometry dimensions in meters when web-ifc normalizes millimeter models", () => {
    const dimensions = formatRealGeometryDimensions({ x: 4.67, y: 0.45, z: 25.31 }, "millimeters");

    expect(dimensions).toBe("4.67 x 0.45 x 25.31 m");
  });

  it("uses real mesh area as the primary geometry quantity for walls", () => {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(2, 2, 2), new THREE.MeshStandardMaterial());
    const quantities = calculateRealGeometryQuantities([mesh], "meters");

    const primary = primaryRealGeometryEstimate("IfcWallStandardCase", quantities);

    expect(primary?.measurementRule).toBe("GeometryMeshArea");
    expect(primary?.quantity).toBeCloseTo(24, 3);
    expect(primary?.unit).toBe("m2");
  });

  it("builds a controlled measurement payload from the selected real geometry", () => {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(2, 2, 2), new THREE.MeshStandardMaterial());
    const quantities = calculateRealGeometryQuantities([mesh], "meters");
    const primary = primaryRealGeometryEstimate("IfcWallStandardCase", quantities);

    const payload = buildControlledMeasurementPayloadFromRealGeometry(
      tracedLines[0],
      primary,
      "2IRuU8Tqz92AICLQuWall01"
    );

    expect(payload).toEqual({
      line_ids: [301],
      measurement_rule: "GeometryMeshArea",
      note: "Medicion geometrica real desde malla IFC para 2IRuU8Tqz92AICLQuWall01",
      quantity: 24,
      source: "Geometria triangulada IFC",
      unit: "m2",
    });
  });
});
