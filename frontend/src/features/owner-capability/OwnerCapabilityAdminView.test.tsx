import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import OwnerCapabilityAdminView from "./OwnerCapabilityAdminView";
import { OWNER_CAPABILITY_POLICY_SECTIONS } from "./policySections";
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
describe("Owner Capability ADMIN", () => {
  it("reuses existing versioned configuration lifecycle, never USER operations", () => {
    render(<OwnerCapabilityAdminView token="configuration" />);
    expect(editor).toHaveBeenCalledWith(
      expect.objectContaining({
        token: "configuration",
        root: "/api/v1/owner-capability",
        sections: OWNER_CAPABILITY_POLICY_SECTIONS,
      })
    );
    expect(screen.getByRole("region", { name: "Owner Capability Readiness Configuration" })).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Create capability assessment|Complete assessment/ })
    ).not.toBeInTheDocument();
  });
  it("exposes all governed framework and review sections without confusing quality and confidence", () => {
    expect(OWNER_CAPABILITY_POLICY_SECTIONS.map(([label]) => label)).toEqual([
      "General",
      "Capability Framework",
      "Dimensions",
      "Requirements",
      "Maturity Scale",
      "Evidence Quality",
      "Applicability",
      "FEL Stage Rules",
      "Gate Profile Rules",
      "Project Type Rules",
      "Governance Model Rules",
      "Complexity Rules",
      "Risk Rules",
      "Uncertainty Rules",
      "Commercial Strategy Rules",
      "Blocking Rules",
      "Coverage Rules",
      "Mitigation Acceptance Rules",
      "Freshness",
      "Numbering",
      "Inheritance",
      "Review / SoD",
      "Preview",
      "History",
    ]);
  });
});
