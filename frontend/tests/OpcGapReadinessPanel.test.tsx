import { render, screen, within } from "@testing-library/react";
import OpcGapReadinessPanel from "../src/components/OpcGapReadinessPanel";
import type { OpcGapAnalysis } from "../src/lib/opcGap";

const analysis: OpcGapAnalysis = {
  criticalGapCount: 1,
  gaps: [
    {
      appEvidence: "90 quantity line(s)",
      id: "bim-apu-budget",
      nextAction: "Mapear cantidades BIM a WBS/CBS/FBS/APU.",
      controlReference: "Differential: IFC quantities to local APU budget and control codes.",
      priority: "P2",
      status: "partial",
      title: "BIM -> APU -> controlled budget bridge",
    },
  ],
  nextActions: ["Cargar P6 XML/XER, validar DCMA/calidad y mantener la logica CPM como fuente contractual."],
  overallStatus: "partial",
  readinessScore: 58,
  spine: [
    {
      detail: "The contractual schedule must provide activities, dates and logic.",
      evidence: "0 act / 0 link(s)",
      id: "p6-cpm",
      label: "P6 CPM",
      status: "gap",
    },
  ],
};

describe("OpcGapReadinessPanel", () => {
  it("shows the control diagnostic score, data spine and prioritized actions without naming external products", () => {
    render(<OpcGapReadinessPanel analysis={analysis} />);

    const panel = screen.getByRole("region", { name: /diagnóstico de control/i });

    expect(within(panel).getByRole("heading", { name: /Diagnóstico de Control/i })).toBeInTheDocument();
    expect(panel).not.toHaveTextContent(/\bOPC\b|Oracle|Primavera Cloud/i);
    expect(within(panel).getAllByText("58%")).toHaveLength(2);
    expect(within(panel).getByText(/P6 CPM/i)).toBeInTheDocument();
    expect(within(panel).getByRole("columnheader", { name: /Capacidad de control/i })).toBeInTheDocument();
    expect(within(panel).getByText(/BIM -> APU -> controlled budget bridge/i)).toBeInTheDocument();
    expect(within(panel).getByText(/Cargar P6 XML\/XER/i)).toBeInTheDocument();
  });
});
