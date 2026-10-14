import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import QraEvidenceSummary from "./QraEvidenceSummary";
import QraPolicyEditor from "./QraPolicyEditor";
import type { EvidencePolicyContent } from "./types";

const content: EvidencePolicyContent = {
  policy_code: "existing-policy",
  policy_name: "Existing policy",
  applicable_governance_models: ["CAPITAL_OWNER"],
  gate_profiles: { "PYP-FFA": { allow_valid_with_conditions: false, requirements: [] } },
  project_type_overrides: [],
  blocking_policy: {},
  validity_policy: {},
  coverage_policy: {},
};
function Editor({ disabled = false }: { disabled?: boolean }) {
  const [state, setState] = useState(content);
  return (
    <>
      <QraPolicyEditor content={state} disabled={disabled} onChange={setState} profile="PYP-FFA" />
      <output data-testid="policy">{JSON.stringify(state)}</output>
    </>
  );
}
describe("Contextual QRA policy and provider references", () => {
  it("adds separate nonmandatory Cost and Schedule rows without Integrated or engine controls", () => {
    render(<Editor />);
    fireEvent.click(screen.getByRole("button", { name: "Add Cost QRA requirement" }));
    fireEvent.click(screen.getByRole("button", { name: "Add Schedule QRA requirement" }));
    const policy = JSON.parse(screen.getByTestId("policy").textContent || "{}");
    const rows = policy.gate_profiles["PYP-FFA"].requirements;
    expect(rows.map((row: { evidence_type: string }) => row.evidence_type)).toEqual([
      "COST_QRA_RESULT",
      "SCHEDULE_QRA_RESULT",
    ]);
    expect(
      rows.every(
        (row: { classification: string; required: boolean; provider_key: string }) =>
          row.classification === "C" && !row.required && row.provider_key === "QRA_RESULT_PROVIDER"
      )
    ).toBe(true);
    expect(rows[1].qra_policy.capability_requirements.schedule_state).toBe("NOT_STARTED");
    expect(screen.queryByRole("button", { name: /simulate|execute|run qra/i })).not.toBeInTheDocument();
  });
  it("makes Class A required without manual fallback and persists controlled tailoring", () => {
    render(<Editor />);
    fireEvent.click(screen.getByRole("button", { name: "Add Cost QRA requirement" }));
    fireEvent.change(screen.getByLabelText("Cost QRA evidence class"), { target: { value: "A" } });
    fireEvent.change(screen.getByLabelText("Cost QRA convergence"), { target: { value: "REQUIRED" } });
    fireEvent.click(screen.getByLabelText("Cost QRA BC consistency required"));
    const row = JSON.parse(screen.getByTestId("policy").textContent || "{}").gate_profiles["PYP-FFA"].requirements[0];
    expect(row).toMatchObject({
      classification: "A",
      required: true,
      blocking: true,
      provider_required: true,
      allow_manual_reference: false,
    });
    expect(row.qra_policy).toMatchObject({
      applicability: "REQUIRED",
      governance_model_filter: ["CAPITAL_OWNER"],
      convergence: "REQUIRED",
      bc_consistency_required: true,
    });
  });
  it("does not edit a published revision", () => {
    render(<Editor disabled />);
    expect(screen.getByRole("button", { name: "Add Cost QRA requirement" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Add Schedule QRA requirement" })).toBeDisabled();
  });
  it("keeps existing per-profile criteria when adding a governed QRA hurdle", () => {
    const onChange = vi.fn();
    const next = {
      ...content,
      decision_criterion_policy: {
        criteria_by_profile: {
          "PYP-FFA": [
            {
              criterion_code: "EXISTING",
              criterion_type: "MUST_MEET" as const,
              source_evidence_type: "BUSINESS_CASE_READINESS",
              operator: "IS_READY",
              required: true,
              blocking: true,
            },
          ],
        },
      },
    };
    const { rerender } = render(
      <QraPolicyEditor content={next} disabled={false} profile="PYP-FFA" onChange={onChange} />
    );
    fireEvent.click(screen.getByRole("button", { name: "Add Cost QRA requirement" }));
    const withRow = onChange.mock.calls[0][0];
    rerender(<QraPolicyEditor content={withRow} disabled={false} profile="PYP-FFA" onChange={onChange} />);
    fireEvent.click(screen.getByRole("button", { name: "Add Cost QRA decision criterion" }));
    const criteria = onChange.mock.lastCall?.[0].decision_criterion_policy.criteria_by_profile["PYP-FFA"];
    expect(criteria).toHaveLength(2);
    expect(criteria[0].criterion_code).toBe("EXISTING");
    expect(criteria[1]).toMatchObject({
      source_evidence_type: "COST_QRA_RESULT",
      source_field: "source_payload",
      scope: "EACH_PROJECT",
      criterion_name: "Cost QRA governed evidence criterion",
    });
    expect(criteria[1].qra_criterion).toMatchObject({
      analysis_type: "COST_QRA",
      metric: "PERCENTILE",
      target: { source: "GATE_CRITERION" },
    });
  });
  it("binds new Schedule criteria to the existing governed provider source field", () => {
    render(<Editor />);
    fireEvent.click(screen.getByRole("button", { name: "Add Schedule QRA requirement" }));
    fireEvent.click(screen.getByRole("button", { name: "Add Schedule QRA decision criterion" }));
    const policy = JSON.parse(screen.getByTestId("policy").textContent || "{}");
    expect(policy.decision_criterion_policy.criteria_by_profile["PYP-FFA"][0]).toMatchObject({
      source_evidence_type: "SCHEDULE_QRA_RESULT",
      source_field: "source_payload",
      scope: "EACH_PROJECT",
      criterion_name: "Schedule QRA governed evidence criterion",
      qra_criterion: {
        analysis_type: "SCHEDULE_QRA",
        unit: "DAYS",
        time_basis: "NORMALIZED_ELAPSED_TIME_V1",
      },
    });
  });
  it("discloses accepted/current quality, tail and schedule boundaries without fetching a run", () => {
    const onView = vi.fn();
    render(
      <QraEvidenceSummary
        onView={onView}
        applicability={{
          applicability: "REQUIRED",
          reason: "High-value FFA",
          capability_fit: "SUPPORTED_WITH_LIMITATIONS",
        }}
        summary={{
          analysis_type: "SCHEDULE_QRA",
          run_number: "QRR-6",
          model_definition_id: 9,
          accepted: true,
          source_current: false,
          analytical_readiness: "READY_WITH_WARNINGS",
          convergence_status: "CONVERGED",
          selected_percentiles: [{ percentile: 90, date: "2027-10-12" }],
          target_probabilities: { probability_finish_by_target: 0.83 },
          warnings: ["NOT_CONVERGED"],
          blockers: ["SOURCE_STALE"],
        }}
      />
    );
    expect(screen.getByRole("region", { name: "SCHEDULE_QRA evidence summary" })).toHaveTextContent("STALE");
    expect(screen.getByText(/P90\/P95 and tail convergence are not/)).toBeInTheDocument();
    expect(screen.getByText(/not detailed P6 work calendars/)).toBeInTheDocument();
    expect(screen.getByText("SOURCE_STALE")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "View QRA" }));
    expect(onView).toHaveBeenCalledOnce();
  });
});
