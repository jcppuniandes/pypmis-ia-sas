import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import RiskReadinessAdminView from "./RiskReadinessAdminView";
import RiskReadinessWorkspace from "./RiskReadinessWorkspace";

const mocks = vi.hoisted(() => ({
  portfolioOptions: vi.fn(),
  portfolioProjects: vi.fn(),
  portfolioReadiness: vi.fn(),
  projectReadiness: vi.fn(),
  risks: vi.fn(),
  assessments: vi.fn(),
  configurations: vi.fn(),
  previewConfiguration: vi.fn(),
}));

vi.mock("./api", () => ({ riskReadinessApi: mocks }));
vi.mock("../portfolio-planning/api", () => ({
  portfolioPlanningApi: { portfolioOptions: mocks.portfolioOptions, portfolioProjects: mocks.portfolioProjects },
}));

const projectReadiness = {
  project_workspace_id: 101,
  assessment_id: 11,
  assessment_hash: "a".repeat(64),
  as_of_date: "2026-08-30T00:00:00",
  valid_until: "2026-11-28T00:00:00",
  active_risk_count: 1,
  high_count: 0,
  critical_count: 0,
  unowned_high_critical_count: 0,
  untreated_high_critical_count: 0,
  overdue_treatment_count: 0,
  unaccepted_residual_count: 0,
  evidence_coverage: 100,
  warnings: [],
  blockers: [],
  readiness_status: "READY",
  risk_readiness_hash: "b".repeat(64),
  source_current: true,
  allowed_actions: {},
};

describe("Gate 07J-RISK Risk Readiness", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.portfolioOptions.mockResolvedValue([{ id: 71, name: "Capital Portfolio" }]);
    mocks.portfolioProjects.mockResolvedValue([{ project_workspace_id: 101, project_name: "Project Alpha" }]);
    mocks.risks.mockResolvedValue([
      {
        id: 91,
        risk_number: "RSK-00001",
        title: "Controlled interface risk",
        description: "",
        risk_category: "TECHNICAL",
        status: "MONITORING",
        identified_date: "2026-08-30",
        risk_owner_id: 1,
        cause: "Cause",
        event: "Event",
        impact_description: "Impact",
        likelihood_before: 2,
        impact_before: 2,
        inherent_rating: "LOW",
        treatment_required: false,
        treatment_strategy: null,
        treatment_description: null,
        treatment_owner_id: null,
        target_treatment_date: null,
        treatment_status: null,
        likelihood_after: null,
        impact_after: null,
        residual_rating: null,
        residual_acceptance_required: false,
        accepted_by: null,
        accepted_at: null,
        acceptance_comment: null,
        acceptance_authority_level: null,
        due_date: null,
        source_reference: null,
        evidence_refs_json: [{ reference: "EVID-1" }],
        revision_version: 1,
      },
    ]);
    mocks.assessments.mockResolvedValue([]);
    mocks.projectReadiness.mockResolvedValue(projectReadiness);
    mocks.portfolioReadiness.mockResolvedValue({
      portfolio_workspace_id: 71,
      recommended_project_set_hash: "c".repeat(64),
      required_project_count: 1,
      valid_project_count: 1,
      blocked_project_count: 0,
      stale_project_count: 0,
      expired_project_count: 0,
      coverage_percent: 100,
      aggregate_high_count: 0,
      aggregate_critical_count: 0,
      aggregate_unaccepted_residual_count: 0,
      warnings: [],
      blockers: [],
      readiness_status: "READY",
      risk_readiness_hash: "d".repeat(64),
      project_readiness: [projectReadiness],
    });
    mocks.configurations.mockResolvedValue([
      {
        id: 7,
        name: "Risk Readiness Configuration",
        description: "Controlled",
        status: "draft",
        revision: 1,
        version: 1,
        content_hash: "e".repeat(64),
        content_json: {
          configuration_code: "PYP-RISK-READINESS",
          applicable_governance_models: ["CAPITAL_OWNER"],
          risk_categories: ["TECHNICAL"],
          likelihood_scale: [],
          impact_scale: [],
          risk_matrix: {},
          rating_bands: ["LOW", "MODERATE", "HIGH", "CRITICAL"],
          owner_required_threshold: "HIGH",
          treatment_required_threshold: "HIGH",
          residual_assessment_threshold: "HIGH",
          acceptance_threshold: "HIGH",
          acceptance_authority: {},
          readiness_criteria: {},
          evidence_coverage_percent: 100,
          validity_days: 90,
          pyp_ffa: { classification: "A", validity_days: 90 },
          inheritance: [],
        },
      },
    ]);
    mocks.previewConfiguration.mockResolvedValue({ persisted: false, can_enter_fid: false, would_be_ready: true });
  });

  it("shows the governed Project Risk Register columns and no FID action", async () => {
    render(<RiskReadinessWorkspace initialView="risk-readiness-register" token="token" />);
    expect(await screen.findByRole("heading", { name: "Project Risk Register" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Inherent Rating" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Acceptance" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Due Date" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Evidence" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Warnings" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "High / Critical" })).toBeInTheDocument();
    expect((await screen.findAllByText("RSK-00001")).length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: /approve investment|enter fid/i })).not.toBeInTheDocument();
  });

  it("exposes all 16 ADMIN sections and a non-persistent preview", async () => {
    const user = userEvent.setup();
    render(<RiskReadinessAdminView token="token" />);
    const admin = await screen.findByRole("region", { name: "Risk Readiness Configuration" });
    expect(
      within(admin)
        .getAllByRole("button")
        .filter((button) =>
          [
            "Configuration Overview",
            "Risk Categories",
            "Likelihood Scale",
            "Impact Scale",
            "Risk Matrix",
            "Rating Bands",
            "Owner Rules",
            "Treatment Rules",
            "Residual Risk Rules",
            "Acceptance Authority",
            "Readiness Criteria",
            "Evidence Rules",
            "Validity / Expiry",
            "Gate Compatibility",
            "Inheritance / Overrides",
            "Versioning / Publish",
          ].includes(button.textContent || "")
        )
    ).toHaveLength(16);
    await user.click(within(admin).getByRole("button", { name: "Preview" }));
    await waitFor(() => expect(mocks.previewConfiguration).toHaveBeenCalled());
    expect(within(admin).getByRole("status")).toHaveTextContent("persisted=false");
  });
});
