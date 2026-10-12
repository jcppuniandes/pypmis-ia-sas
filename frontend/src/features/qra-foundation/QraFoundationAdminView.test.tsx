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
  it("reuses source/methodology tailoring and adds the governed execution policy without USER operations", () => {
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
      "Execution Policy",
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
  it("maps visible rule groups to backend-consumed settings instead of unsupported top-level aliases", () => {
    const paths = Object.fromEntries(QRA_POLICY_SECTIONS);
    expect(paths["Distribution Rules"]).toBe("distribution_families");
    expect(paths["Review / Approval"]).toBe("model_governance");
    expect(paths["FEL Stage Rules"]).toBe("applicability.fel_stages");
    expect(paths["Gate Profile Rules"]).toBe("applicability.gate_profiles");
    expect(paths["Project Type Rules"]).toBe("applicability.project_types");
    expect(paths["Governance Model Rules"]).toBe("applicability.governance_models");
    expect(paths["Risk / Complexity Rules"]).toBe("applicability");
    expect(QRA_POLICY_SECTIONS.map(([, path]) => path)).not.toContain("distribution_rules");
    expect(QRA_POLICY_SECTIONS.map(([, path]) => path)).not.toContain("review_approval");
    render(<QraFoundationAdminView token="config" />);
    expect(screen.getByRole("region", { name: "QRA Methodology & Source Readiness" })).toHaveTextContent(
      "source-specific stage overrides belong inside each requirement's stage_rules"
    );
  });
});
