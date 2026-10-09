import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import StrategicCapitalAllocationWorkspace from "./StrategicCapitalAllocationWorkspace";
import type { StrategicAllocationComparison, StrategicAllocationOptions, StrategicAllocationPlan } from "./types";

const mocks = vi.hoisted(() => ({
  options: vi.fn(),
  listPlans: vi.fn(),
  createPlan: vi.fn(),
  readPlan: vi.fn(),
  updatePlan: vi.fn(),
  replaceLines: vi.fn(),
  action: vi.fn(),
  newRevision: vi.fn(),
  replaceClassifications: vi.fn(),
  comparison: vi.fn(),
  history: vi.fn(),
}));

vi.mock("./api", () => ({ strategicAllocationApi: mocks }));

const options: StrategicAllocationOptions = {
  planning_cycles: [{ id: 7, cycle_number: "CPC-00007", name: "FY27 cycle", status: "OPEN" }],
  workspaces: [
    { id: 11, name: "P&P Enterprise", workspace_type_code: "ENTERPRISE" },
    { id: 12, name: "Operations BU", workspace_type_code: "BUSINESS_UNIT" },
    { id: 13, name: "Growth Portfolio", workspace_type_code: "PORTFOLIO" },
  ],
  portfolios: [{ id: 13, name: "Growth Portfolio" }],
  buckets: [
    { bucket_code: "sustaining", bucket_name: "Sustaining Capital", active: true, display_order: 1 },
    { bucket_code: "growth", bucket_name: "Growth Capital", active: true, display_order: 2 },
  ],
  allocation_basis_options: ["PERCENTAGE", "INDICATIVE_AMOUNT", "PERCENTAGE_AND_AMOUNT"],
  scope_options: ["ENTERPRISE", "BUSINESS_UNIT", "PORTFOLIO"],
};

const plan: StrategicAllocationPlan = {
  id: 51,
  allocation_plan_number: "SCA-00051",
  name: "FY27 strategic allocation",
  description: "Governed intent",
  planning_cycle_id: 7,
  planning_cycle_number: "CPC-00007",
  planning_cycle_name: "FY27 cycle",
  scope_type: "ENTERPRISE",
  scope_workspace_id: 11,
  scope_workspace_name: "P&P Enterprise",
  portfolio_id: null,
  base_currency: "COP",
  allocation_basis: "PERCENTAGE",
  status: "DRAFT",
  revision_version: 3,
  configuration_revision: 8,
  configuration_hash: "abcdef1234567890",
  source_current: true,
  lines: [
    {
      id: 1,
      bucket_code: "sustaining",
      bucket_name: "Sustaining Capital",
      minimum_percentage: 45,
      target_percentage: 60,
      maximum_percentage: 70,
      minimum_amount: null,
      target_amount: null,
      maximum_amount: null,
      currency: "COP",
      rationale: "Protect base assets",
      strategic_objective_codes: [],
      assumptions: [],
      constraints: [],
    },
    {
      id: 2,
      bucket_code: "growth",
      bucket_name: "Growth Capital",
      minimum_percentage: 30,
      target_percentage: 40,
      maximum_percentage: 55,
      minimum_amount: null,
      target_amount: null,
      maximum_amount: null,
      currency: "COP",
      rationale: "Selective growth",
      strategic_objective_codes: [],
      assumptions: [],
      constraints: [],
    },
  ],
  readiness: { overall: "ATTENTION", ready: false },
  allowed_actions: ["edit", "replace_lines", "classify", "submit"],
};

const comparison: StrategicAllocationComparison = {
  allocation_plan_id: 51,
  population_definition: "Eligible submitted, in-review and endorsed Capital Demands.",
  classification_precedence: ["EXPLICIT", "DEMAND", "THEME_DEFAULT", "UNCLASSIFIED"],
  warnings: ["COP and USD remain separate; no silent FX normalization was applied."],
  unclassified: {
    percentage: 10,
    amount: null,
    amounts_by_currency: { USD: 250000 },
    item_count: 1,
    count: 1,
  },
  buckets: [
    {
      bucket_code: "sustaining",
      bucket_name: "Sustaining Capital",
      target: { percentage: 60, amount: null, amounts_by_currency: {}, item_count: 1 },
      current_demand: { percentage: 55, amount: null, amounts_by_currency: { COP: 850000000 }, item_count: 2 },
      current_portfolio: { percentage: 52, amount: null, amounts_by_currency: { COP: 810000000 }, item_count: 2 },
      recommended: { percentage: 50, amount: null, amounts_by_currency: { COP: 780000000 }, item_count: 1 },
      approved: { percentage: 48, amount: null, amounts_by_currency: { COP: 750000000 }, item_count: 1 },
      variance_percentage: -5,
      variance_amount: null,
      status: "UNDER_TARGET",
    },
    {
      bucket_code: "growth",
      bucket_name: "Growth Capital",
      target: { percentage: 40, amount: null, amounts_by_currency: {}, item_count: 1 },
      current_demand: { percentage: 35, amount: null, amounts_by_currency: { COP: 540000000 }, item_count: 1 },
      current_portfolio: { percentage: 48, amount: null, amounts_by_currency: { COP: 740000000 }, item_count: 1 },
      recommended: { percentage: 50, amount: null, amounts_by_currency: { COP: 780000000 }, item_count: 1 },
      approved: { percentage: 52, amount: null, amounts_by_currency: { COP: 810000000 }, item_count: 1 },
      variance_percentage: -5,
      variance_amount: null,
      status: "WITHIN_RANGE",
    },
  ],
  classifications: [
    {
      demand_id: 91,
      demand_number: "CD-00091",
      demand_name: "Terminal integrity",
      target_type: "DEMAND",
      target_id: 91,
      bucket_code: null,
      resolution_source: "UNCLASSIFIED",
      rationale: "",
      indicative_capital_need: 250000,
      currency_code: "USD",
      classified: false,
    },
  ],
};

describe("StrategicCapitalAllocationWorkspace", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.options.mockResolvedValue(options);
    mocks.listPlans.mockResolvedValue({ items: [plan], page: 1, pageSize: 100, total: 1, nextCursor: null });
    mocks.readPlan.mockResolvedValue(plan);
    mocks.comparison.mockResolvedValue(comparison);
    mocks.history.mockResolvedValue([]);
    mocks.replaceLines.mockResolvedValue({ ...plan, revision_version: 4 });
    mocks.replaceClassifications.mockResolvedValue({ ...plan, revision_version: 4 });
    mocks.action.mockResolvedValue({ ...plan, status: "SUBMITTED", revision_version: 4, allowed_actions: [] });
  });

  it("renders backend-derived positions, explicit unclassified exposure and the no-authority boundary", async () => {
    const user = userEvent.setup();
    render(<StrategicCapitalAllocationWorkspace token="token" />);

    expect(await screen.findByText("SCA-00051")).toBeVisible();
    expect(screen.getByRole("note")).toHaveTextContent("amounts are never silently normalized across currencies");
    expect(screen.getByText(/does not rank Projects or approve Budget, Funding, resources or FID/i)).toBeVisible();
    expect(screen.getByText("COP and USD remain separate; no silent FX normalization was applied.")).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Demand Position" }));
    expect(await screen.findByRole("row", { name: /UNCLASSIFIED/ })).toHaveTextContent(/USD 250[.,]000/);
    expect(screen.getByRole("table", { name: "Demand Position by Strategic Capital Bucket" })).toBeVisible();
  });

  it("edits and saves an exact 100 percent target without silently changing Bucket values", async () => {
    const user = userEvent.setup();
    render(<StrategicCapitalAllocationWorkspace token="token" />);
    expect(await screen.findByText("SCA-00051")).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Target Allocation" }));
    expect(screen.getByText("Target total 100%")).toBeVisible();
    const growthTarget = screen.getByLabelText("growth target percentage");
    await user.clear(growthTarget);
    await user.type(growthTarget, "35");
    expect(screen.getByText("Target total 95%")).toBeVisible();
    await user.click(screen.getByRole("button", { name: "Save target allocation" }));

    await waitFor(() => expect(mocks.replaceLines).toHaveBeenCalledTimes(1));
    expect(mocks.replaceLines).toHaveBeenCalledWith(
      "token",
      expect.objectContaining({ id: 51, revision_version: 3 }),
      expect.arrayContaining([
        expect.objectContaining({ bucket_code: "sustaining", target_percentage: 60 }),
        expect.objectContaining({ bucket_code: "growth", target_percentage: "35" }),
      ])
    );
  });

  it("persists one explicit primary Bucket classification and keeps lineage identifiers", async () => {
    const user = userEvent.setup();
    render(<StrategicCapitalAllocationWorkspace token="token" />);
    expect(await screen.findByText("SCA-00051")).toBeVisible();

    await user.click(screen.getByRole("button", { name: "Classification" }));
    const table = screen.getByRole("table", { name: "Strategic Bucket classifications" });
    await user.selectOptions(within(table).getByLabelText("CD-00091 primary Bucket"), "growth");
    await user.type(within(table).getByLabelText("CD-00091 classification rationale"), "Explicit sponsor choice");
    await user.click(screen.getByRole("button", { name: "Save primary classifications" }));

    await waitFor(() => expect(mocks.replaceClassifications).toHaveBeenCalledTimes(1));
    expect(mocks.replaceClassifications).toHaveBeenCalledWith("token", expect.objectContaining({ id: 51 }), [
      expect.objectContaining({
        demand_id: 91,
        target_id: 91,
        target_type: "DEMAND",
        bucket_code: "growth",
        rationale: "Explicit sponsor choice",
      }),
    ]);
  });

  it("creates a governed plan only after an explicit scope Workspace is selected", async () => {
    const user = userEvent.setup();
    mocks.listPlans.mockResolvedValue({ items: [], page: 1, pageSize: 100, total: 0, nextCursor: null });
    mocks.createPlan.mockResolvedValue(plan);
    render(<StrategicCapitalAllocationWorkspace token="token" />);

    await screen.findByText("No Allocation Plan selected");
    await user.click(screen.getByRole("button", { name: "New Allocation Plan" }));
    const form = screen.getByRole("form", { name: "New Strategic Capital Allocation Plan form" });
    await user.type(within(form).getByLabelText("Plan name"), "FY27 strategic allocation");
    await user.selectOptions(within(form).getByLabelText("Planning Cycle"), "7");
    await user.selectOptions(within(form).getByLabelText("Scope Workspace"), "11");
    await user.click(within(form).getByRole("button", { name: "Create governed DRAFT" }));

    await waitFor(() => expect(mocks.createPlan).toHaveBeenCalledTimes(1));
    expect(mocks.createPlan).toHaveBeenCalledWith(
      "token",
      expect.objectContaining({
        planning_cycle_id: 7,
        scope_type: "ENTERPRISE",
        scope_workspace_id: 11,
        portfolio_id: null,
      })
    );
  });

  it("exposes only governed lifecycle actions returned by the backend", async () => {
    const user = userEvent.setup();
    render(<StrategicCapitalAllocationWorkspace token="token" />);
    expect(await screen.findByRole("button", { name: "Submit plan" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Endorse strategic plan" })).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Submit plan" }));
    await waitFor(() => expect(mocks.action).toHaveBeenCalledWith("token", plan, "submit"));
  });
});
