import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import PermitReadinessAdminView from "./PermitReadinessAdminView";
import PermitReadinessWorkspace from "./PermitReadinessWorkspace";

const mocks = vi.hoisted(() => ({
  portfolioOptions: vi.fn(),
  portfolioProjects: vi.fn(),
  portfolioReadiness: vi.fn(),
  projectReadiness: vi.fn(),
  permits: vi.fn(),
  assessments: vi.fn(),
  conditions: vi.fn(),
  configurations: vi.fn(),
  previewConfiguration: vi.fn(),
}));

vi.mock("./api", () => ({ permitReadinessApi: mocks }));
vi.mock("../portfolio-planning/api", () => ({
  portfolioPlanningApi: { portfolioOptions: mocks.portfolioOptions, portfolioProjects: mocks.portfolioProjects },
}));

const projectReadiness = {
  project_workspace_id: 101,
  project_type_code: "MINING",
  permit_classification: "A",
  gate_profile: "PYP-FFA",
  assessment_id: 11,
  assessment_hash: "a".repeat(64),
  as_of_date: "2026-08-31T00:00:00",
  valid_until: "2027-02-27T00:00:00",
  required_count: 3,
  approved_count: 2,
  conditional_count: 1,
  missing_count: 0,
  rejected_count: 0,
  suspended_count: 0,
  expired_count: 0,
  open_blocking_conditions: 0,
  evidence_coverage_percent: 100,
  warnings: [],
  blockers: [],
  readiness_status: "READY",
  permit_readiness_hash: "b".repeat(64),
  source_current: true,
  allowed_actions: {},
};

describe("Gate 07J-PERMIT Permit Readiness", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.portfolioOptions.mockResolvedValue([{ id: 71, name: "Capital Portfolio" }]);
    mocks.portfolioProjects.mockResolvedValue([{ project_workspace_id: 101, project_name: "Mine Expansion" }]);
    mocks.permits.mockResolvedValue([
      {
        id: 91,
        project_workspace_id: 101,
        permit_number: "PRM-00001",
        permit_type_code: "ENVIRONMENTAL_LICENSE",
        requirement_key: "MINING_ENVIRONMENTAL_LICENSE",
        title: "Environmental licence",
        issuing_authority: "Configured authority",
        jurisdiction: "CO-ANT",
        status: "APPROVED_WITH_CONDITIONS",
        application_reference: "APP-01",
        valid_until: "2027-08-31",
        permit_identifier: "AUTH-01",
        evidence_refs_json: [{ reference: "EVID-1" }],
        responsible_user_id: 1,
        next_action: "Monitor conditions",
        target_date: "2026-09-30",
        revision_version: 1,
      },
    ]);
    mocks.conditions.mockResolvedValue([
      {
        id: 81,
        permit_id: 91,
        condition_key: "MONITORING_REPORT",
        description: "Periodic report",
        condition_type: "MONITORING",
        blocking: false,
        owner_id: 1,
        target_date: "2026-09-30",
        status: "OPEN",
        evidence_refs_json: [],
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
      aggregate_required_permit_count: 3,
      aggregate_approved_count: 2,
      aggregate_conditional_count: 1,
      aggregate_missing_count: 0,
      aggregate_rejected_count: 0,
      aggregate_suspended_count: 0,
      aggregate_expired_count: 0,
      aggregate_blocking_condition_count: 0,
      warnings: [],
      blockers: [],
      readiness_status: "READY",
      permit_readiness_hash: "d".repeat(64),
      project_readiness: [projectReadiness],
    });
    mocks.configurations.mockResolvedValue([
      {
        id: 7,
        name: "Permit Readiness Configuration",
        description: "Controlled",
        status: "draft",
        revision: 1,
        version: 1,
        content_hash: "e".repeat(64),
        content_json: {
          configuration_code: "PYP-PERMIT-READINESS",
          applicable_governance_models: ["CAPITAL_OWNER"],
          permit_types: [
            { code: "ENVIRONMENTAL_LICENSE", name: "Environmental License", authority_type: "CONFIGURED" },
          ],
          requirements: [
            {
              requirement_key: "MINING_ENVIRONMENTAL_LICENSE",
              permit_type_code: "ENVIRONMENTAL_LICENSE",
              applicable_project_types: ["MINING"],
              applicable_geographies: ["*"],
              applicable_gate_profiles: ["PYP-FFA"],
              blocking: true,
            },
          ],
          qualifying_statuses: { "PYP-FFA": ["APPROVED", "APPROVED_WITH_CONDITIONS"] },
          condition_policy: "BLOCK_ONLY_ON_BLOCKING_CONDITIONS",
          evidence_coverage_percent: 100,
          class_a_project_coverage_percent: 100,
          validity_days: 180,
          inheritance: ["TENANT", "PORTFOLIO"],
          separation_of_duties: {},
        },
      },
    ]);
    mocks.previewConfiguration.mockResolvedValue({ persisted: false, can_enter_fid: false });
  });

  it("shows the governed permit register columns and no regulatory or FID action", async () => {
    render(<PermitReadinessWorkspace initialView="permit-readiness-register" token="token" />);
    expect(await screen.findByRole("heading", { name: "Permit register" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Type / requirement" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Authority" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Valid until" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Next action" })).toBeInTheDocument();
    expect(await screen.findByText("PRM-00001")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /file with authority|approve investment|enter fid/i })
    ).not.toBeInTheDocument();
  });

  it("shows normalized conditions with blocking and evidence columns", async () => {
    render(<PermitReadinessWorkspace initialView="permit-readiness-conditions" token="token" />);
    expect(await screen.findByRole("heading", { name: "Normalized permit conditions" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Blocking" })).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Evidence" })).toBeInTheDocument();
    expect(await screen.findByText("MONITORING_REPORT")).toBeInTheDocument();
  });

  it("exposes all 17 ADMIN sections and a non-persistent preview", async () => {
    const user = userEvent.setup();
    render(<PermitReadinessAdminView token="token" />);
    const admin = await screen.findByRole("region", { name: "Permit Readiness Configuration" });
    expect(
      within(admin)
        .getAllByRole("button")
        .filter((button) =>
          [
            "Configuration Overview",
            "Permit Types",
            "Requirement Catalog",
            "Project Type Applicability",
            "Geography Applicability",
            "Gate Profile Rules",
            "Permit Status Rules",
            "Condition Rules",
            "Evidence Rules",
            "Validity / Expiry",
            "Renewal Rules",
            "Readiness Criteria",
            "Project Set Coverage",
            "Provider Contract",
            "Inheritance / Overrides",
            "Segregation of Duties",
            "Versioning / Publish",
          ].includes(button.textContent || "")
        )
    ).toHaveLength(17);
    await user.click(within(admin).getByRole("button", { name: "Dry-run" }));
    await waitFor(() => expect(mocks.previewConfiguration).toHaveBeenCalled());
    expect(within(admin).getByRole("status")).toHaveTextContent("persisted=false");
  });
});
