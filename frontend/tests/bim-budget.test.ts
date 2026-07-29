import { buildBimBudget, buildBimBudgetExcelXml } from "../src/lib/bimBudget";
import type { QuantityTakeoffLine } from "../src/types";

function quantityLine(
  id: number,
  overrides: Partial<QuantityTakeoffLine> = {},
  budgetAssignment: Record<string, unknown> | null = null
): QuantityTakeoffLine {
  return {
    id,
    project_id: 1,
    run_id: 10,
    source_row_id: `#${id}:NetArea`,
    element_id: `#${id}`,
    element_guid: `GUID-${id}`,
    ifc_class: "IfcWall",
    category: "Muro",
    family: "Muro concreto",
    type_name: "20 cm",
    instance_name: `Muro ${id}`,
    project_name: "Proyecto Piloto",
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
    measurement_rule: "NetArea",
    wbs_code: "01-01",
    cbs_code: "CBS-01-01-CON",
    fbs_code: "FBS-CAPEX",
    package_code: "IWP-01",
    wbs_id: 1,
    cbs_id: 2,
    fbs_id: 3,
    work_package_id: 4,
    mapping_status: "mapped",
    validation_notes: "",
    raw_data: budgetAssignment ? { budget_item_assignment: budgetAssignment } : {},
    created_at: "2026-06-18T00:00:00Z",
    updated_at: "2026-06-18T00:00:00Z",
    ...overrides,
  };
}

describe("BIM budget consolidation", () => {
  it("consolidates assigned BIM quantities by item and control codes", () => {
    const assignment = {
      apu_structure: [
        {
          amount: 70000,
          component: "Materiales",
          description: "Concreto y refuerzo",
          quantity: 1,
          unit: "m2",
          unit_rate: 70000,
        },
        {
          amount: 30000,
          component: "Mano de obra",
          description: "Cuadrilla",
          quantity: 1,
          unit: "m2",
          unit_rate: 30000,
        },
      ],
      budget_amount: 1_000_000,
      budget_unit: "m2",
      cost_item_code: "APU-MUR-01",
      cost_item_name: "Muro en concreto",
      currency: "COP",
      quantity: 10,
      status: "assigned",
      unit_rate: 100_000,
    };
    const secondAssignment = { ...assignment, budget_amount: 500_000, quantity: 5 };

    const result = buildBimBudget([
      quantityLine(1, {}, assignment),
      quantityLine(2, { quantity: 5 }, secondAssignment),
    ]);

    expect(result.rows).toHaveLength(1);
    expect(result.rows[0]).toMatchObject({
      code: "APU-MUR-01",
      quantity: 15,
      unit: "m2",
      unitRate: 100_000,
      totalAmount: 1_500_000,
      wbsCode: "01-01",
      cbsCode: "CBS-01-01-CON",
      fbsCode: "FBS-CAPEX",
    });
    expect(result.rows[0].elementRefs).toEqual(["GUID-1", "GUID-2"]);
    expect(result.currencyTotals).toEqual([{ currency: "COP", amount: 1_500_000 }]);
    expect(result.gate).toBe("ready");
  });

  it("excludes exact repeated element measurements and flags incompatible units", () => {
    const baseAssignment = {
      budget_amount: 1_000_000,
      budget_unit: "m2",
      cost_item_code: "APU-MUR-01",
      cost_item_name: "Muro en concreto",
      currency: "COP",
      quantity: 10,
      status: "assigned",
      unit_rate: 100_000,
    };

    const result = buildBimBudget([
      quantityLine(1, {}, baseAssignment),
      quantityLine(2, { element_guid: "GUID-1" }, baseAssignment),
      quantityLine(
        3,
        { unit: "m3", measurement_rule: "NetVolume", quantity: 2 },
        { ...baseAssignment, budget_amount: 240_000, budget_unit: "m3", quantity: 2, unit_rate: 120_000 }
      ),
      quantityLine(4, { raw_data: {} }),
    ]);

    expect(result.duplicateLineCount).toBe(1);
    expect(result.unitConflictCount).toBe(1);
    expect(result.missingAssignmentCount).toBe(1);
    expect(result.rows).toHaveLength(2);
    expect(result.gate).toBe("blocked");
  });

  it("marks an unpriced takeoff as pending instead of blocked", () => {
    const result = buildBimBudget([quantityLine(1)]);

    expect(result.rows).toHaveLength(0);
    expect(result.missingAssignmentCount).toBe(1);
    expect(result.gate).toBe("review");
  });

  it("generates an Excel-compatible workbook with traceability and APU structure", () => {
    const result = buildBimBudget([
      quantityLine(
        1,
        {},
        {
          apu_structure: [
            {
              amount: 100000,
              component: "Costo directo",
              description: "Muro",
              quantity: 1,
              unit: "m2",
              unit_rate: 100000,
            },
          ],
          budget_amount: 1_000_000,
          budget_unit: "m2",
          cost_item_code: "APU-MUR-01",
          cost_item_name: "Muro en concreto",
          currency: "COP",
          quantity: 10,
          status: "assigned",
          unit_rate: 100_000,
        }
      ),
    ]);

    const workbook = buildBimBudgetExcelXml(result, {
      projectCode: "01",
      projectName: "Proyecto Piloto",
    });

    expect(workbook).toContain("Presupuesto BIM");
    expect(workbook).toContain("APU-MUR-01");
    expect(workbook).toContain("GUID-1");
    expect(workbook).toContain("Costo directo");
    expect(workbook).not.toContain("1500000");
    expect(workbook).toContain("1000000");
  });
});
