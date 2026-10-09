import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import StrategicBenefitsAdminView from "./StrategicBenefitsAdminView";
import StrategicBenefitsWorkspace from "./StrategicBenefitsWorkspace";

const mocks = vi.hoisted(() => ({
  options: vi.fn(),
  listPage: vi.fn(),
  detail: vi.fn(),
  readiness: vi.fn(),
  history: vi.fn(),
  traceabilityPage: vi.fn(),
  create: vi.fn(),
  updateVersion: vi.fn(),
  addBenefit: vi.fn(),
  updateBenefit: vi.fn(),
  addMeasure: vi.fn(),
  updateMeasure: vi.fn(),
  lifecycle: vi.fn(),
  newRevision: vi.fn(),
  refreshPreview: vi.fn(),
  refreshApply: vi.fn(),
  configurations: vi.fn(),
  effectivePreview: vi.fn(),
  cloneConfiguration: vi.fn(),
  updateConfiguration: vi.fn(),
  publishConfiguration: vi.fn(),
  archiveConfiguration: vi.fn(),
}));

vi.mock("./api", () => ({ strategicBenefitsApi: mocks }));

const measure = {
  id: 401,
  benefit_snapshot_id: 311,
  measure_code: "KPI-01",
  measure_name: "Availability",
  definition: "Service availability",
  unit_of_measure: "%",
  direction: "INCREASE",
  is_primary: true,
  baseline_status: "UNKNOWN",
  baseline_value: null,
  baseline_as_of_date: null,
  baseline_source: "Pending baseline study",
  baseline_evidence_reference: null,
  baseline_confidence: null,
  target_value: "99.5",
  target_date: "2028-12-31",
  target_basis: "Approved service target",
  tolerance: {},
  measurement_method: "Monthly service records",
  measurement_frequency: "MONTHLY",
  data_source_description: "Operations system",
  measurement_owner_reference: { name: "Operations" },
  measure_hash: "measure-hash",
  created_at: "2026-09-16T00:00:00Z",
  updated_at: "2026-09-16T00:00:00Z",
  revision_version: 2,
};

const benefit = {
  id: 301,
  benefit_number: "BEN-000301",
  identity_status: "ACTIVE",
  snapshot_id: 311,
  status: "ACTIVE",
  benefit_name: "Improve service availability",
  benefit_description: "Reduce service interruptions",
  benefit_direction: "BENEFIT",
  benefit_type: "OPERATIONAL",
  benefit_category: "RELIABILITY",
  strategic_objective_refs: [{ code: "STR-01" }],
  source_need_reference: { reference: "NEED-1" },
  source_business_analysis_reference: { reference: "BA-1" },
  source_project_proposal_reference: { reference: "PP-1" },
  source_business_case_reference: { reference: "BC-1" },
  expected_outputs: [{ reference: "New interconnection" }],
  expected_outcomes: [{ reference: "Resilient supply" }],
  benefit_statement: "Availability improves after the interconnection enters service",
  owner: {
    owner_type: "ORGANIZATIONAL_ROLE",
    owner_user_id: null,
    owner_organization_unit_id: null,
    owner_security_role_id: null,
    owner_reference: "OPS-DIRECTOR",
    effective_from: "2026-09-16",
    effective_to: null,
    accountability_statement: "Own sustained service performance",
    acceptance_status: "ACCEPTED",
  },
  expected_value: { description: "Service resilience" },
  monetizable_flag: false,
  dependencies: [],
  assumptions: [],
  constraints: [],
  risk_references: [{ risk_id: "RSK-1" }],
  measures: [measure],
  snapshot_hash: "snapshot-hash",
  revision_version: 2,
};

const version = {
  id: 201,
  benefits_plan_id: 101,
  version_number: 1,
  version_purpose: "FEL_2_UPDATE",
  status: "DRAFT",
  fel_stage_code: "FEL-2",
  overview_json: { purpose: "Investment justification" },
  outputs_json: [{ output_name: "New interconnection" }],
  outcomes_json: [{ outcome_name: "Resilient supply" }],
  assumptions_json: [],
  constraints_json: [],
  benefits: [benefit],
  readiness_json: { BENEFIT_DEFINITION_READINESS: "READY", coverage: { baseline_coverage: 0 } },
  readiness_status: "IN_PROGRESS",
  overall_benefits_readiness: "IN_PROGRESS",
  readiness_warnings_json: [],
  readiness_blockers_json: ["Baseline missing"],
  coverage: { baseline_coverage: 0 },
  source_references_json: { business_case: { id: 9, status: "COMPLETED" } },
  source_hashes_json: { business_case: "hash" },
  source_current: true,
  configuration_current: true,
  configuration_id: 8,
  configuration_revision: 2,
  configuration_hash: "config-hash",
  source_bundle_hash: "source-hash",
  benefits_plan_hash: "plan-hash",
  preparer_user_id: 1,
  reviewer_user_id: 2,
  revision_version: 7,
  allowed_actions: {
    can_edit: true,
    can_add_benefit: true,
    can_edit_benefit: true,
    can_assign_owner: true,
    can_submit: true,
    can_start_review: false,
    can_return: false,
    can_complete: false,
    can_void: true,
    can_create_revision: false,
    can_view_sources: true,
    can_refresh_preview: true,
    can_refresh_apply: true,
  },
  can_supply_investment_gate_evidence: false,
  created_at: "2026-09-16T00:00:00Z",
  updated_at: "2026-09-16T00:00:00Z",
};

const plan = {
  id: 101,
  plan_number: "BPL-000101",
  project_workspace_id: 501,
  project_workspace_name: "Interconnection",
  status: "DRAFT",
  current_version_id: 201,
  current_version: version,
  configuration_id: 8,
  configuration_revision: 2,
  configuration_hash: "config-hash",
  revision_version: 7,
  allowed_actions: version.allowed_actions,
  final_output: "IN_PROGRESS",
  next_process: "COMPLETE_BENEFITS_PLAN",
  created_at: "2026-09-16T00:00:00Z",
  updated_at: "2026-09-16T00:00:00Z",
};

const readiness = {
  benefits_plan_id: 101,
  version_id: 201,
  status: "IN_PROGRESS",
  overall_benefits_readiness: "IN_PROGRESS",
  dimensions: { BENEFIT_DEFINITION_READINESS: "READY", BASELINE_READINESS: "BLOCKED" },
  coverage: { owner_coverage: 100, baseline_coverage: 0 },
  warnings: [],
  blockers: ["Baseline missing"],
  source_current: true,
  configuration_current: true,
  can_supply_investment_gate_evidence: false,
  benefits_plan_hash: "plan-hash",
  source_bundle_hash: "source-hash",
  configuration_hash: "config-hash",
  persisted: true,
};

describe("Gate 07M-BEN frontend", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.listPage.mockResolvedValue({ items: [plan], nextCursor: null, pageLimit: 50, resultCount: 1 });
    mocks.detail.mockResolvedValue(plan);
    mocks.options.mockResolvedValue({
      version_purposes: ["INITIAL_BENEFITS_PLAN", "FEL_2_UPDATE"],
      queues: [],
      readiness_states: [],
      provider_key: "BENEFITS_READINESS_PROVIDER",
      provider_status: "AVAILABLE",
      configuration_id: 8,
      configuration_revision: 2,
      configuration_hash: "config-hash",
      benefit_types: ["OPERATIONAL", "FINANCIAL"],
      benefit_categories: ["RELIABILITY"],
      units_of_measure: ["%"],
      measurement_frequencies: ["MONTHLY"],
      measure_directions: ["INCREASE"],
      owner_types: ["ORGANIZATIONAL_ROLE"],
      owner_acceptance_statuses: ["ACCEPTED"],
      benefit_directions: ["BENEFIT", "DISBENEFIT"],
    });
    mocks.readiness.mockResolvedValue(readiness);
    mocks.history.mockResolvedValue([{ version, lifecycle_events: [] }]);
    mocks.traceabilityPage.mockResolvedValue({
      items: [
        {
          strategic_objectives: [{ name: "Reliable service" }],
          need_opportunity: { reference: "Reduce outages" },
          business_analysis: { reference: "BA-1" },
          recommended_option: { name: "Interconnection" },
          project: { name: "Project 501" },
          business_case: { reference: "BC-1" },
          expected_outputs: [{ name: "New interconnection" }],
          expected_outcomes: [{ name: "Resilient supply" }],
          benefit_id: 301,
          benefit_number: "BEN-000301",
          benefit_name: "Improve service availability",
          measures: [
            {
              name: "Availability",
              baseline_status: "UNKNOWN",
              baseline: null,
              target: "99.5",
              target_date: "2028-12-31",
            },
          ],
          owner: benefit.owner,
          target_dates: ["2028-12-31"],
          expected_value: {},
          status: "IN_PROGRESS",
        },
      ],
      nextCursor: null,
      pageLimit: 50,
      resultCount: 1,
    });
    mocks.updateVersion.mockResolvedValue(version);
    mocks.updateBenefit.mockResolvedValue(benefit);
    mocks.updateMeasure.mockResolvedValue(measure);
    mocks.refreshPreview.mockResolvedValue({
      persisted: false,
      source_delta: [],
      benefit_delta: [],
      owner_delta: [],
      measure_delta: [],
      target_delta: [],
      policy_delta: [],
      readiness_delta: {},
      warnings: [],
      blockers: [],
    });
    mocks.configurations.mockResolvedValue([
      {
        id: 8,
        name: "Capital Owner Benefits",
        description: "Governed policy",
        status: "DRAFT",
        revision: 2,
        version: 3,
        content_json: {
          configuration_code: "BEN-CAPITAL",
          required_fields: {},
          enabled_by_governance_model: { CAPITAL_OWNER: true },
        },
      },
    ]);
    mocks.effectivePreview.mockResolvedValue({ persisted: false, configuration_hash: "config-hash" });
  });

  it("renders 8 USER queues and 16 governed views without ADMIN controls", async () => {
    render(<StrategicBenefitsWorkspace token="token" />);
    expect(await screen.findByRole("heading", { name: "Strategic Benefits Plan & Traceability" })).toBeInTheDocument();
    expect(
      within(screen.getByRole("group", { name: "Strategic Benefits queues" })).getAllByRole("button")
    ).toHaveLength(8);
    expect(
      within(screen.getByRole("navigation", { name: "Strategic Benefits views" })).getAllByRole("button")
    ).toHaveLength(16);
    expect(await screen.findByText("BPL-000101 · Version 1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Save Plan/ })).toBeEnabled();
    expect(screen.queryByRole("button", { name: /Publish|Archive|Clone/ })).not.toBeInTheDocument();
    expect(screen.getByText(/Output is what the Project delivers/)).toBeInTheDocument();
  });

  it("preserves UNKNOWN baseline as null and never silently converts it to zero", async () => {
    render(<StrategicBenefitsWorkspace initialView="strategic-benefits-measures" token="token" />);
    expect(await screen.findByLabelText("Baseline status")).toHaveValue("UNKNOWN");
    expect(screen.getByLabelText("Baseline value")).toBeDisabled();
    expect(screen.getByText(/never silently converted to zero/i)).toBeInTheDocument();
    const saveMeasure = screen.getByRole("button", { name: "Save measure" });
    await waitFor(() => expect(saveMeasure).toBeEnabled());
    fireEvent.click(saveMeasure);
    await waitFor(() => expect(mocks.updateMeasure).toHaveBeenCalled());
    expect(mocks.updateMeasure.mock.calls[0][5]).toEqual(
      expect.objectContaining({ baseline_status: "UNKNOWN", baseline_value: null, baseline_as_of_date: null })
    );
  });

  it("loads the derived traceability matrix with one paginated API request", async () => {
    render(<StrategicBenefitsWorkspace initialView="strategic-benefits-traceability" token="token" />);
    expect(await screen.findByRole("columnheader", { name: "Benefit ID" })).toBeInTheDocument();
    expect(screen.getByText("BEN-000301")).toBeInTheDocument();
    expect(mocks.traceabilityPage).toHaveBeenCalledTimes(1);
    expect(mocks.traceabilityPage).toHaveBeenCalledWith("token", 101);
  });

  it("exposes 23 ADMIN policy sections and no live Plan actions", async () => {
    render(<StrategicBenefitsAdminView token="token" />);
    const admin = await screen.findByRole("region", { name: "Benefits Configuration" });
    expect(
      within(admin).getByRole("navigation", { name: "Benefits configuration sections" }).querySelectorAll("button")
    ).toHaveLength(23);
    expect(within(admin).getByRole("button", { name: "Save draft" })).toBeEnabled();
    expect(within(admin).getByRole("button", { name: "Publish" })).toBeEnabled();
    expect(within(admin).queryByRole("button", { name: /^Submit$/ })).not.toBeInTheDocument();
    expect(within(admin).queryByRole("button", { name: /^Complete$/ })).not.toBeInTheDocument();
    expect(admin).toHaveTextContent(/cannot create, edit, assign owners, submit, review, complete or revise/i);
  });

  it("blocks ADMIN save and publish when governed JSON is invalid", async () => {
    render(<StrategicBenefitsAdminView token="token" />);
    const admin = await screen.findByRole("region", { name: "Benefits Configuration" });
    fireEvent.click(within(admin).getByRole("button", { name: "Required Fields" }));
    fireEvent.change(within(admin).getByLabelText("Required Fields"), { target: { value: "{invalid}" } });
    expect(within(admin).getByRole("alert")).toHaveTextContent(/json|expected/i);
    expect(within(admin).getByRole("button", { name: "Save draft" })).toBeDisabled();
    expect(within(admin).getByRole("button", { name: "Publish" })).toBeDisabled();
  });
});
