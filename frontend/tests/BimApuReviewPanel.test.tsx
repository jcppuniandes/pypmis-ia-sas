import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import BimApuReviewPanel from "../src/components/BimApuReviewPanel";
import type { QuantityTakeoffLine } from "../src/types";

const suggestedLine: QuantityTakeoffLine = {
  id: 1,
  project_id: 1,
  run_id: 20,
  source_row_id: "#1:NetArea",
  element_id: "#1",
  element_guid: "GUID-1",
  ifc_class: "IfcWall",
  category: "Muros",
  family: "Concreto",
  type_name: "Muro 15 cm",
  instance_name: "Muro 1",
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
  raw_data: {
    apu_suggestion: {
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
      status: "suggested",
      unit_rate: 45200,
    },
  },
  created_at: "2026-06-19T00:00:00Z",
  updated_at: "2026-06-19T00:00:00Z",
};

describe("BimApuReviewPanel", () => {
  it("approves ready groups in one controlled action", async () => {
    const onApproveLines = vi.fn();
    const onOpenBudget = vi.fn();
    const user = userEvent.setup();

    render(
      <BimApuReviewPanel
        lines={[suggestedLine]}
        onApproveLines={onApproveLines}
        onOpenBudget={onOpenBudget}
        onSuggestLines={vi.fn()}
      />
    );

    const panel = screen.getByRole("region", { name: /revisi.n masiva de apu/i });
    expect(within(panel).getByText(/92%/i)).toBeInTheDocument();
    expect(within(panel).getByText(/invias_reference_apu/i)).toBeInTheDocument();
    expect(within(panel).getByText(/^0 m2$/i)).toBeInTheDocument();

    await user.click(within(panel).getByRole("button", { name: /seleccionar listos/i }));
    await user.click(within(panel).getByRole("button", { name: /aprobar grupos seleccionados/i }));

    expect(onApproveLines).toHaveBeenCalledWith([1]);
    await user.click(within(panel).getByRole("button", { name: /abrir budget/i }));
    expect(onOpenBudget).toHaveBeenCalledTimes(1);
  });

  it("requests suggestions for pending groups", async () => {
    const onSuggestLines = vi.fn();
    const user = userEvent.setup();

    render(
      <BimApuReviewPanel
        lines={[{ ...suggestedLine, raw_data: {} }]}
        onApproveLines={vi.fn()}
        onOpenBudget={vi.fn()}
        onSuggestLines={onSuggestLines}
      />
    );

    const panel = screen.getByRole("region", { name: /revisi.n masiva de apu/i });
    await user.click(within(panel).getByRole("button", { name: /sugerir apu para pendientes/i }));

    expect(onSuggestLines).toHaveBeenCalledWith([1]);
  });
});
