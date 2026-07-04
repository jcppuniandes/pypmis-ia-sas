import { buildBimApuReview } from "../src/lib/bimApuReview";
import type { QuantityTakeoffLine } from "../src/types";

function line(
  id: number,
  overrides: Partial<QuantityTakeoffLine> = {},
  suggestion: Record<string, unknown> | null = null
): QuantityTakeoffLine {
  return {
    id,
    project_id: 1,
    run_id: 20,
    source_row_id: `#${id}:NetArea`,
    element_id: `#${id}`,
    element_guid: `GUID-${id}`,
    ifc_class: "IfcWall",
    category: "Muros",
    family: "Concreto",
    type_name: "Muro 15 cm",
    instance_name: `Muro ${id}`,
    project_name: "Proyecto",
    site_name: "Site",
    building_name: "Edificio",
    storey: "Nivel 1",
    system_name: "",
    zone_name: "",
    assembly_name: "",
    classification_system: "",
    classification_code: "",
    quantity: 10,
    unit: "m2",
    measurement_rule: "NetSideArea",
    wbs_code: "01-01",
    cbs_code: "CBS-01",
    fbs_code: "FBS-01",
    package_code: "IWP-01",
    wbs_id: 1,
    cbs_id: 2,
    fbs_id: 3,
    work_package_id: 4,
    mapping_status: "mapped",
    validation_notes: "",
    raw_data: suggestion ? { apu_suggestion: suggestion } : {},
    created_at: "2026-06-19T00:00:00Z",
    updated_at: "2026-06-19T00:00:00Z",
    ...overrides,
  };
}

const wallSuggestion = {
  apu_structure: [],
  budget_amount: 452000,
  budget_unit: "m2",
  catalog_item_id: 7,
  cost_item_code: "1.05.0101",
  cost_item_name: "Muro en concreto reforzado",
  currency: "COP",
  match_score: 92,
  quantity: 10,
  source_key: "invias_reference_apu",
  source_url: "https://example.test/apu",
  status: "suggested",
  unit_rate: 45200,
};

describe("BIM APU group review", () => {
  it("groups compatible lines and exposes confidence, source and IFC-budget variance", () => {
    const result = buildBimApuReview([
      line(1, {}, wallSuggestion),
      line(2, { quantity: 5 }, { ...wallSuggestion, budget_amount: 226000, quantity: 5, match_score: 88 }),
    ]);

    expect(result.groups).toHaveLength(1);
    expect(result.groups[0]).toMatchObject({
      status: "ready",
      lineIds: [1, 2],
      ifcQuantity: 15,
      budgetQuantity: 15,
      quantityVariance: 0,
      unit: "m2",
      budgetUnit: "m2",
      costItemCode: "1.05.0101",
      confidence: 88,
      sourceKey: "invias_reference_apu",
    });
    expect(result.readyGroupCount).toBe(1);
  });

  it("accepts unit aliases and blocks incompatible budget units", () => {
    const countSuggestion = { ...wallSuggestion, budget_unit: "und", quantity: 1 };
    const incompatibleSuggestion = { ...wallSuggestion, budget_unit: "m3" };
    const result = buildBimApuReview([
      line(
        1,
        {
          ifc_class: "IfcDoor",
          category: "Puertas",
          family: "",
          measurement_rule: "ElementCount",
          type_name: "",
          unit: "ea",
          quantity: 1,
        },
        countSuggestion
      ),
      line(2, {}, incompatibleSuggestion),
    ]);

    expect(result.groups.find((group) => group.ifcClasses.includes("IfcDoor"))?.status).toBe("ready");
    expect(result.groups.find((group) => group.ifcClasses.includes("IfcWall"))?.status).toBe("blocked");
    expect(result.blockedGroupCount).toBe(1);
  });

  it("does not send dimensional ElementCount fallbacks to APU suggestion or approval", () => {
    const result = buildBimApuReview([
      line(
        1,
        {
          ifc_class: "IfcSlab",
          category: "Losa",
          measurement_rule: "ElementCount",
          quantity: 1,
          unit: "ea",
          validation_notes: "No published IFC quantity found",
        },
        { ...wallSuggestion, budget_unit: "ea", quantity: 1 }
      ),
    ]);

    expect(result.groups[0].status).toBe("blocked");
    expect(result.groups[0].blockReason).toMatch(/area.*m2/i);
    expect(result.pendingLineIds).toEqual([]);
    expect(result.readyLineIds).toEqual([]);
  });

  it("requires review when a group receives different APU items or low confidence", () => {
    const result = buildBimApuReview([
      line(1, {}, { ...wallSuggestion, match_score: 62 }),
      line(2, {}, { ...wallSuggestion, cost_item_code: "1.05.0999", cost_item_name: "Otro muro" }),
      line(3),
    ]);

    expect(result.groups[0].status).toBe("review");
    expect(result.pendingLineCount).toBe(1);
  });
});
