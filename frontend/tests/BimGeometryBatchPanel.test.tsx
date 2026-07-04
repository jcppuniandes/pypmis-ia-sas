import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import BimGeometryBatchPanel from "../src/components/BimGeometryBatchPanel";
import type { BimGeometryMeasurementBatch } from "../src/types";

const preview: BimGeometryMeasurementBatch = {
  model_id: 8,
  run_id: 3,
  revision_id: "IFC-M8-REV",
  total_count: 2,
  matched_count: 2,
  ready_count: 1,
  compare_count: 1,
  applied_count: 0,
  unmatched_count: 0,
  invalid_count: 0,
  results: [
    {
      line_id: 11,
      element_guid: "SLAB-GUID",
      ifc_class: "IfcSlab",
      element_name: "Losa",
      status: "ready",
      current_quantity: 1,
      current_unit: "ea",
      source_quantity: 1,
      source_unit: "ea",
      approved_quantity: null,
      approved_unit: "",
      geometry_quantity: 18.5,
      geometry_unit: "m2",
      measurement_rule: "GeometryMeshArea",
      difference: 17.5,
      difference_percent: null,
      confidence: "Media",
      reason: "Medicion dimensional calculada",
    },
    {
      line_id: 12,
      element_guid: "DOOR-GUID",
      ifc_class: "IfcDoor",
      element_name: "Puerta",
      status: "compare",
      current_quantity: 1,
      current_unit: "ea",
      source_quantity: 1,
      source_unit: "ea",
      approved_quantity: null,
      approved_unit: "",
      geometry_quantity: 2.1,
      geometry_unit: "m",
      measurement_rule: "GeometryMeshLength",
      difference: 0,
      difference_percent: null,
      confidence: "Media",
      reason: "Cantidad actual valida; solo comparacion",
    },
  ],
};

describe("BimGeometryBatchPanel", () => {
  it("previews and approves only ready geometry measurements", async () => {
    const user = userEvent.setup();
    const onAnalyze = vi.fn();
    const onApply = vi.fn();

    render(
      <BimGeometryBatchPanel
        actionDisabled={false}
        modelAvailable
        onAnalyze={onAnalyze}
        onApply={onApply}
        preview={preview}
      />,
    );

    const panel = screen.getByRole("region", { name: /medicion geometrica masiva/i });
    expect(within(panel).getByText(/1 lista/i)).toBeInTheDocument();
    expect(within(panel).getByText(/18,5 m2/i)).toBeInTheDocument();
    expect(within(panel).getByText(/cantidad actual valida/i)).toBeInTheDocument();

    await user.click(within(panel).getByRole("button", { name: /calcular geometria/i }));
    await user.click(within(panel).getByRole("button", { name: /aprobar 1 medicion/i }));

    expect(onAnalyze).toHaveBeenCalledTimes(1);
    expect(onApply).toHaveBeenCalledTimes(1);
  });

  it("blocks cross-model calculations with a clear source message", () => {
    render(
      <BimGeometryBatchPanel
        modelAvailable={false}
        modelStatusMessage="La tabla y el modelo visible provienen de archivos IFC distintos."
        onAnalyze={vi.fn()}
        onApply={vi.fn()}
        preview={null}
      />,
    );

    expect(screen.getByText(/archivos IFC distintos/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /calcular geometria/i })).toBeDisabled();
  });

  it("links a takeoff run to the selected IFC revision", async () => {
    const user = userEvent.setup();
    const onLinkModel = vi.fn();
    render(
      <BimGeometryBatchPanel
        modelAvailable={false}
        models={[
          {
            id: 14,
            project_id: 1,
            source_file_name: "building.ifc",
            source_type: "ifc",
            source_sha256: "abcdef1234567890",
            revision_id: "IFC-M14-abcdef123456",
            source_size_bytes: 100,
            status: "uploaded",
            schema: "IFC4",
            units: "meters",
            element_count: 10,
            storey_count: 2,
            model_identity: {},
            created_at: "2026-06-19T00:00:00",
            updated_at: "2026-06-19T00:00:00",
          },
        ]}
        onAnalyze={vi.fn()}
        onApply={vi.fn()}
        onLinkModel={onLinkModel}
        preview={null}
        run={{
          id: 3,
          project_id: 1,
          bim_model_id: null,
          source_file_name: "quantities.xlsx",
          source_type: "xlsx",
          source_sha256: "1234567890abcdef",
          bim_revision_id: "",
          model_linked_at: null,
          status: "needs_mapping",
          row_count: 2,
          mapped_line_count: 0,
          unmapped_line_count: 2,
          total_quantity: 2,
          validation_summary: "",
          version: 1,
          created_at: "2026-06-19T00:00:00",
          updated_at: "2026-06-19T00:00:00",
        }}
      />,
    );

    await user.selectOptions(screen.getByLabelText(/modelo \/ revision ifc/i), "14");
    await user.click(screen.getByRole("button", { name: /vincular revision/i }));

    expect(onLinkModel).toHaveBeenCalledWith(14);
    expect(screen.getByText(/SHA-256 1234567890ab/i)).toBeInTheDocument();
  });
});
