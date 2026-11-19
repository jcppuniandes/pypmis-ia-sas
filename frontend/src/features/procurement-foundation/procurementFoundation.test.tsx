import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { apiFetch } from "../../api/client";
import { permission, procurementProject, query } from "./api";
import ProcurementWorkspace from "./ProcurementWorkspace";
import { procurementTabs } from "./views";

vi.mock("../../api/client", () => ({ apiFetch: vi.fn(), ApiError: Error }));

const token = "synthetic-ui-test";
const workspaceId = 31;
const base = procurementProject(workspaceId);
const exampleShipment = {
  id: 77,
  shipment_number: "SH-77",
  vendor_id: 19,
  destination: "Site",
  version: 3,
  status: "ARRIVED",
};
const receipt = {
  id: 92,
  receipt_number: "RC-92",
  shipment_id: 77,
  status: "RECEIVED",
  version: 7,
  lines: [{ id: 93, quantity: 2, uom: "EA" }],
};
const profile = { id: 5, code: "O2B", content_json: { shipment_modes: ["ROAD"] } };
function mockProject(actions: string[]) {
  vi.mocked(apiFetch).mockImplementation(async (route, options) => {
    if (route.endsWith("/configuration")) return { profile, allowed_actions: actions };
    if (route.includes("/shipments/77/transition") && options?.method === "POST") return exampleShipment;
    if (route.endsWith("/shipments/77")) return exampleShipment;
    if (route.includes("/shipments?")) return { items: [exampleShipment] };
    if (route.endsWith("/material-receipts/92/acceptance") && options?.method === "POST") return receipt;
    if (route.endsWith("/material-receipts/92")) return receipt;
    if (route.includes("/material-receipts?")) return { items: [receipt] };
    return { items: [] };
  });
}

describe("Procurement UI authority boundaries", () => {
  beforeEach(() => vi.resetAllMocks());

  it("exposes all 16 scoped views without inventing write permission", async () => {
    mockProject(["procurement.read"]);
    render(<ProcurementWorkspace token={token} workspaceId={workspaceId} />);
    const tabs = within(screen.getByRole("navigation", { name: "Vistas Procurement Manager" })).getAllByRole("button");
    expect(tabs.map((entry) => entry.textContent)).toEqual([...procurementTabs]);
    fireEvent.click(screen.getByRole("button", { name: "Shipments" }));
    const panel = within(await screen.findByRole("table", { name: "Embarques" }));
    expect(panel.getByText("ARRIVED")).toBeInTheDocument();
    fireEvent.click(panel.getByRole("button", { name: "Ver Embarques 77" }));
    await screen.findByRole("heading", { name: "Detalle · Embarques #77" });
    expect(screen.queryByRole("button", { name: "Registrar transición de embarque" })).not.toBeInTheDocument();
    expect(vi.mocked(apiFetch).mock.calls.every(([, init]) => !init?.method)).toBe(true);
  });

  it("sends explicit acceptance with receipt ETag, idempotency and no AWP write", async () => {
    mockProject(["procurement.read", "procurement.receipt.accept"]);
    render(<ProcurementWorkspace token={token} workspaceId={workspaceId} />);
    fireEvent.click(screen.getByRole("button", { name: "Material Receipts" }));
    const table = within(await screen.findByRole("table", { name: "Recepciones de material" }));
    fireEvent.click(table.getByRole("button", { name: "Ver Recepciones de material 92" }));
    fireEvent.click(await screen.findByRole("button", { name: "Clasificar recepción" }));
    const form = within(screen.getByRole("form", { name: "Confirmar · Clasificar recepción" }));
    const data = {
      "ID de línea de recepción": "93",
      "Cantidad aceptada": "2",
      "Cantidad rechazada": "0",
      "Cantidad en cuarentena": "0",
      "Motivo de Procurement": "Aceptación independiente registrada",
    };
    Object.entries(data).forEach(([label, value]) =>
      fireEvent.change(form.getByLabelText(label), { target: { value } })
    );
    fireEvent.click(form.getByRole("button", { name: "Confirmar · Clasificar recepción" }));
    await waitFor(() =>
      expect(apiFetch).toHaveBeenCalledWith(
        `${base}/material-receipts/92/acceptance`,
        expect.objectContaining({
          method: "POST",
          headers: { "Idempotency-Key": expect.any(String), "If-Match": '"7"' },
          body: JSON.stringify({
            receipt_line_id: 93,
            accepted_quantity: 2,
            rejected_quantity: 0,
            quarantine_quantity: 0,
            reason: "Aceptación independiente registrada",
          }),
        })
      )
    );
    expect(vi.mocked(apiFetch).mock.calls.filter(([, init]) => init?.method)).toHaveLength(1);
  });

  it("does not grant Procurement actions from another module and omits empty filters", () => {
    expect(permission(["engineering.package.create"], "package.create")).toBe(false);
    expect(permission(["procurement.package.create"], "package.create")).toBe(true);
    expect(query("/mappings", { target_kind: "IWP", after_id: undefined, effective_date: "" })).toBe(
      "/mappings?target_kind=IWP"
    );
  });
});
