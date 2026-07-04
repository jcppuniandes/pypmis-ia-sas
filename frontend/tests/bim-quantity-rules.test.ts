import { describe, expect, it } from "vitest";
import { estimateQuantityFromGeometry, evaluateQuantityRule, summarizeQuantityRules } from "../src/lib/bimQuantityRules";
import type { QuantityTakeoffLine } from "../src/types";

function line(overrides: Partial<QuantityTakeoffLine>): QuantityTakeoffLine {
  return {
    id: 1,
    project_id: 1,
    run_id: 1,
    source_row_id: "#10:NetSideArea",
    element_id: "#10",
    element_guid: "GUID-10",
    ifc_class: "IfcWallStandardCase",
    category: "Muro",
    family: "Basic Wall",
    type_name: "Exterior",
    instance_name: "Wall 10",
    project_name: "Project",
    site_name: "Site",
    building_name: "Building",
    storey: "Level 1",
    system_name: "",
    zone_name: "",
    assembly_name: "",
    classification_system: "",
    classification_code: "",
    quantity: 12.5,
    unit: "m2",
    measurement_rule: "NetSideArea",
    wbs_code: "",
    cbs_code: "",
    fbs_code: "",
    package_code: "",
    wbs_id: null,
    cbs_id: null,
    fbs_id: null,
    work_package_id: null,
    mapping_status: "needs_mapping",
    validation_notes: "",
    raw_data: { ifc_entity: "IFCWALLSTANDARDCASE" },
    created_at: "2026-06-03T00:00:00Z",
    updated_at: "2026-06-03T00:00:00Z",
    ...overrides,
  };
}

describe("bim quantity rules", () => {
  it("estimates wall area from metric geometry dimensions", () => {
    const estimate = estimateQuantityFromGeometry("IfcWallStandardCase", { x: 0.2, y: 3, z: 4 }, "meters");

    expect(estimate?.quantity).toBe(12);
    expect(estimate?.unit).toBe("m2");
    expect(estimate?.measurementRule).toBe("GeometryAreaBBox");
  });

  it("converts millimeter model dimensions before estimating area", () => {
    const estimate = estimateQuantityFromGeometry("IfcWall", { x: 200, y: 3000, z: 4000 }, "millimeters");

    expect(estimate?.quantity).toBe(12);
    expect(estimate?.unit).toBe("m2");
  });

  it("does not estimate geometry quantities when the model unit is unknown", () => {
    const estimate = estimateQuantityFromGeometry("IfcWall", { x: 0.2, y: 3, z: 4 }, "unidades IFC");

    expect(estimate).toBeNull();
  });

  it("marks published IFC wall area quantities as reliable", () => {
    const result = evaluateQuantityRule(line({}));

    expect(result.status).toBe("valid");
    expect(result.confidence).toBe("Alta");
    expect(result.source).toBe("IFC Quantity Set publicado");
    expect(result.expectedUnits).toContain("m2");
    expect(result.explanation).toMatch(/IfcWallStandardCase.*area/i);
  });

  it("accepts wall length when the budget measurement is linear", () => {
    const result = evaluateQuantityRule(
      line({
        measurement_rule: "NetLength",
        quantity: 12,
        unit: "m",
      }),
    );

    expect(result.status).toBe("valid");
    expect(result.expectedUnits).toEqual(["m2", "m3", "m"]);
    expect(result.preferredUnit).toBe("m2");
  });

  it("accepts inventory count for naturally countable IFC classes", () => {
    const result = evaluateQuantityRule(
      line({
        ifc_class: "IfcDoor",
        category: "Puerta",
        measurement_rule: "ElementCount",
        quantity: 1,
        unit: "ea",
        validation_notes: "No published IFC quantity found",
      }),
    );

    expect(result.status).toBe("valid");
    expect(result.confidence).toBe("Media");
    expect(result.source).toBe("Conteo fallback");
    expect(result.preferredUnit).toBe("ea");
  });

  it("blocks dimensional IFC classes when only ElementCount is available", () => {
    const result = evaluateQuantityRule(
      line({
        ifc_class: "IfcSlab",
        category: "Losa",
        measurement_rule: "ElementCount",
        quantity: 1,
        unit: "ea",
        validation_notes: "No published IFC quantity found",
      }),
    );

    expect(result.status).toBe("blocked");
    expect(result.source).toBe("Conteo fallback");
    expect(result.preferredMeasure).toBe("area");
    expect(result.preferredUnit).toBe("m2");
    expect(result.findings.join(" ")).toMatch(/medicion dimensional/i);
  });

  it("accepts approved real geometry for columns and rejects count units", () => {
    const result = evaluateQuantityRule(
      line({
        ifc_class: "IfcColumn",
        category: "Columna",
        measurement_rule: "GeometryMeshVolume",
        quantity: 0.27,
        unit: "m3",
        raw_data: {
          controlled_measurement: {
            measurement_rule: "GeometryMeshVolume",
            quantity: 0.27,
            source: "IFC geometry inspection",
            status: "approved",
            unit: "m3",
          },
        },
      }),
    );

    expect(result.status).toBe("valid");
    expect(result.source).toBe("Calculo geometrico desde IFC");
    expect(result.preferredUnit).toBe("m3");
  });

  it("detects unit mismatches against the expected IFC class rule", () => {
    const result = evaluateQuantityRule(
      line({
        ifc_class: "IfcPipeSegment",
        category: "Tuberia",
        measurement_rule: "NetLength",
        quantity: 20,
        unit: "m3",
      }),
    );

    expect(result.status).toBe("blocked");
    expect(result.confidence).toBe("Media");
    expect(result.expectedUnits).toContain("m");
    expect(result.findings.join(" ")).toMatch(/unidad/i);
  });

  it("uses the backend audited quantity rule when the API provides it", () => {
    const result = evaluateQuantityRule(
      line({
        raw_data: {
          quantity_rule: {
            confidence: "Alta",
            expected_measure: "area o volumen",
            expected_units: ["m2", "m3"],
            explanation: "Backend audited rule",
            findings: [],
            policy_version: 2,
            source: "IFC Quantity Set publicado",
            status: "valid",
          },
        },
      }),
    );

    expect(result.explanation).toBe("Backend audited rule");
    expect(result.expectedUnits).toEqual(["m2", "m3"]);
    expect(result.source).toBe("IFC Quantity Set publicado");
  });

  it("summarizes valid, review and blocked quantity lines", () => {
    const summary = summarizeQuantityRules([
      line({}),
      line({ id: 2, ifc_class: "IfcSlab", measurement_rule: "ElementCount", unit: "ea", validation_notes: "No published IFC quantity found" }),
      line({ id: 3, ifc_class: "IfcPipeSegment", measurement_rule: "NetLength", unit: "m3" }),
    ]);

    expect(summary.valid).toBe(1);
    expect(summary.review).toBe(0);
    expect(summary.blocked).toBe(2);
    expect(summary.authoritative).toBe(1);
  });
});
