import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import QraFoundationAdminView from "./QraFoundationAdminView";
import { QRA_POLICY_SECTIONS } from "./policySections";
const editor = vi.hoisted(() => vi.fn());
vi.mock("../risk-governance/GovernedPolicyEditor", () => ({
  default: (props: { title: string; boundary: string }) => {
    editor(props);
    return (
      <section aria-label={props.title}>
        <p>{props.boundary}</p>
      </section>
    );
  },
}));
describe("QRA Foundation ADMIN", () => {
  it("reuses the versioned policy editor, never approving live models", () => {
    render(<QraFoundationAdminView token="config" />);
    expect(editor).toHaveBeenCalledWith(
      expect.objectContaining({ token: "config", root: "/api/v1/qra-foundation", sections: QRA_POLICY_SECTIONS })
    );
    expect(screen.getByRole("region", { name: "QRA Methodology & Source Readiness" })).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Approve for analysis|Create model definition/ })
    ).not.toBeInTheDocument();
  });
  it("exposes the required 25 source/methodology tailoring and lifecycle sections without simulation", () => {
    expect(QRA_POLICY_SECTIONS.map(([label]) => label)).toEqual([
      "General",
      "Analysis Types",
      "Cost Source Requirements",
      "Schedule Source Requirements",
      "Schedule Quality Rules",
      "Uncertainty Range Policies",
      "Distribution Families",
      "Distribution Rules",
      "Correlation Methods",
      "Correlation Rules",
      "Methodology Profiles",
      "Applicability",
      "FEL Stage Rules",
      "Gate Profile Rules",
      "Project Type Rules",
      "Governance Model Rules",
      "Risk / Complexity Rules",
      "Model Governance",
      "SoD",
      "Validity / Freshness",
      "Numbering",
      "Inheritance",
      "Review / Approval",
      "Preview",
      "History",
    ]);
  });
});
