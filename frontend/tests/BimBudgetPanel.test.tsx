import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import BimBudgetPanel from "../src/components/BimBudgetPanel";
import type { QuantityTakeoffLine } from "../src/types";

const budgetLine: QuantityTakeoffLine = {
  id: 1,
  project_id: 1,
  run_id: 10,
  source_row_id: "#1:NetArea",
  element_id: "#1",
  element_guid: "GUID-1",
  ifc_class: "IfcWall",
  category: "Muro",
  family: "Muro concreto",
  type_name: "20 cm",
  instance_name: "Muro 1",
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
  raw_data: {
    budget_item_assignment: {
      apu_structure: [
        {
          amount: 70000,
          component: "Materiales",
          description: "Concreto y refuerzo",
          quantity: 1,
          unit: "m2",
          unit_rate: 70000,
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
    },
  },
  created_at: "2026-06-18T00:00:00Z",
  updated_at: "2026-06-18T00:00:00Z",
};

describe("BimBudgetPanel", () => {
  it("describes missing APU assignments as a pending budget", () => {
    render(
      <BimBudgetPanel
        currency="COP"
        lines={[{ ...budgetLine, raw_data: {} }]}
        onOpenQuantities={vi.fn()}
        projectCode="01"
        projectName="Proyecto Piloto"
      />
    );

    const panel = screen.getByRole("region", { name: /presupuesto bim/i });
    expect(within(panel).getByRole("status")).toHaveTextContent(/Presupuesto pendiente de completar/i);
    expect(within(panel).getByRole("status")).not.toHaveTextContent(/Bloqueado por calidad/i);
  });

  it("shows the consolidated BIM budget and returns to source quantities", async () => {
    const onOpenQuantities = vi.fn();
    const user = userEvent.setup();

    render(
      <BimBudgetPanel
        currency="COP"
        lines={[budgetLine]}
        onOpenQuantities={onOpenQuantities}
        projectCode="01"
        projectName="Proyecto Piloto"
      />
    );

    const panel = screen.getByRole("region", { name: /presupuesto bim/i });
    expect(within(panel).getByRole("heading", { name: /presupuesto bim/i })).toBeInTheDocument();
    expect(within(panel).getByText("APU-MUR-01")).toBeInTheDocument();
    expect(within(panel).getByText(/Muro en concreto/i)).toBeInTheDocument();
    expect(within(panel).getAllByText(/1.000.000/).length).toBeGreaterThan(0);
    expect(within(panel).getByText(/GUID-1/)).toBeInTheDocument();
    expect(within(panel).getByText(/Materiales/)).toBeInTheDocument();

    await user.click(within(panel).getByRole("button", { name: /ver cantidades fuente/i }));
    expect(onOpenQuantities).toHaveBeenCalledTimes(1);
  });

  it("edits the APU structure and persists the recalculated unit rate", async () => {
    const onUpdateBudgetItem = vi.fn();
    const user = userEvent.setup();

    render(
      <BimBudgetPanel
        currency="COP"
        lines={[budgetLine]}
        onOpenQuantities={vi.fn()}
        onUpdateBudgetItem={onUpdateBudgetItem}
        projectCode="01"
        projectName="Proyecto Piloto"
      />
    );

    const panel = screen.getByRole("region", { name: /presupuesto bim/i });
    await user.click(within(panel).getByRole("button", { name: /editar estructura apu-mur-01/i }));
    const rate = within(panel).getByLabelText(/precio recurso 1/i);
    await user.clear(rate);
    await user.type(rate, "100000");
    await user.click(within(panel).getByRole("button", { name: /guardar estructura apu/i }));

    expect(onUpdateBudgetItem).toHaveBeenCalledWith(
      expect.objectContaining({
        line_ids: [1],
        wbs_code: "01-01",
        cbs_code: "CBS-01-01-CON",
        fbs_code: "FBS-CAPEX",
        package_code: "IWP-01",
        cost_item_code: "APU-MUR-01",
        cost_item_name: "Muro en concreto",
        budget_unit: "m2",
        currency: "COP",
        unit_rate: 100000,
        apu_structure: [
          expect.objectContaining({
            amount: 100000,
            component: "Materiales",
            quantity: 1,
            unit_rate: 100000,
          }),
        ],
      })
    );
  });
});
