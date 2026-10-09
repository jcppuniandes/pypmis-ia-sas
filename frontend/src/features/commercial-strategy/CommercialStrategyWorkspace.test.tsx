import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CommercialStrategyAdminView from "./CommercialStrategyAdminView";
import CommercialStrategyWorkspace from "./CommercialStrategyWorkspace";

const mocks = vi.hoisted(() => ({
  options: vi.fn(),
  listPage: vi.fn(),
  readiness: vi.fn(),
  history: vi.fn(),
  create: vi.fn(),
  update: vi.fn(),
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

vi.mock("./api", () => ({ commercialStrategyApi: mocks }));

const content = {
  commercial_context: "Deliver a governed infrastructure program",
  procurement_approach: "DESIGN_BUILD",
  procurement_rationale: "Single point accountability",
  packaging_strategy_summary: "Two coordinated packages",
  packages: [
    {
      package_code: "PKG-001",
      package_name: "Main works",
      package_type: "WORK",
      scope_summary: "Main construction scope",
      interface_summary: "Interface with owner furnished equipment",
      anticipated_procurement_approach: "DESIGN_BUILD",
      anticipated_contracting_model: "LUMP_SUM",
      key_dependencies: [],
      critical_interfaces: [],
      market_risk: "MODERATE",
      commercial_risk: "MODERATE",
      status: "DRAFT",
    },
  ],
  contracting_model: "LUMP_SUM",
  contracting_model_rationale: "Mature scope",
  market_assessment: { overall_score: 80, summary: "Market has adequate depth", criteria: { supplier_depth: 80 } },
  supply_chain_constraints: [{ statement: "Long lead equipment" }],
  risk_allocations: [
    {
      commercial_risk_category: "DESIGN",
      risk_description: "Design integration",
      preferred_owner: "CONTRACTOR",
      allocation_rationale: "Best able to manage",
      transferability: "TRANSFERABLE",
      pricing_implication: "Risk premium",
      contractual_treatment: "Performance requirements",
      residual_concern: "Interface risk",
      status: "OPEN",
    },
  ],
  payment_mechanism: "MILESTONE",
  payment_mechanism_rationale: "Aligned to deliverables",
  incentive_strategy: { mechanism: "PAIN_GAIN_SHARE", philosophy: "Shared outcome" },
  guarantees_securities_strategy: {},
  commercial_assumptions: [{ statement: "Competitive market" }],
  commercial_constraints: [{ statement: "Permit timing" }],
  dependencies: [],
  legal_regulatory_considerations: [],
  alternatives: [],
  recommendation: {
    recommended_procurement_approach: "DESIGN_BUILD",
    recommended_packaging_strategy: "TWO_PACKAGES",
    recommended_contracting_model: "LUMP_SUM",
    recommended_payment_mechanism: "MILESTONE",
    recommended_incentive_strategy: "PAIN_GAIN",
    rationale: "Best market fit",
    tradeoffs: [],
    commercial_recommendation_status: "RECOMMENDED",
  },
  conditions_open_issues: [],
};

const strategy = {
  id: 51,
  strategy_number: "CCS-000051",
  project_workspace_id: 101,
  current_version_id: 501,
  current_version: {
    id: 501,
    commercial_strategy_id: 51,
    version_number: 1,
    version_purpose: "FEL_2_UPDATE",
    fel_stage_code: "FEL-2",
    status: "DRAFT",
    content_json: content,
    readiness_dimensions: { PROCUREMENT_APPROACH_READINESS: "READY" },
    overall_commercial_readiness: "IN_PROGRESS",
    readiness_warnings: [],
    readiness_blockers: ["payment mechanism review pending"],
    source_current: true,
    configuration_id: 8,
    configuration_revision: 2,
    configuration_hash: "configuration-hash",
    source_bundle_hash: "source-hash",
    commercial_strategy_hash: "strategy-hash",
    revision_version: 3,
    reviewer_user_id: 22,
    created_at: "2026-09-15T10:00:00Z",
    updated_at: "2026-09-15T10:10:00Z",
  },
  allowed_actions: {
    can_edit: true,
    can_submit: true,
    can_start_review: false,
    can_return: false,
    can_complete: false,
    can_void: true,
    can_create_revision: false,
    can_refresh_preview: true,
  },
  revision_version: 3,
  created_at: "2026-09-15T10:00:00Z",
  updated_at: "2026-09-15T10:10:00Z",
};

const readiness = {
  commercial_strategy_id: 51,
  version_id: 501,
  overall_commercial_readiness: "IN_PROGRESS",
  dimensions: {
    PROCUREMENT_APPROACH_READINESS: "READY",
    RISK_ALLOCATION_READINESS: "IN_PROGRESS",
  },
  warnings: [],
  blockers: ["payment mechanism review pending"],
  source_current: true,
  configuration_current: true,
  can_supply_investment_gate_evidence: false,
  commercial_strategy_hash: "strategy-hash",
  source_bundle_hash: "source-hash",
  configuration_hash: "configuration-hash",
};

describe("Gate 07M-COMM frontend", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.listPage.mockResolvedValue({ items: [strategy], nextCursor: null, pageLimit: 50, resultCount: 1 });
    mocks.options.mockResolvedValue({
      version_purposes: ["INITIAL_COMMERCIAL_ASSESSMENT", "FEL_2_UPDATE"],
      readiness_states: ["READY", "BLOCKED", "STALE"],
      queues: ["mine", "draft", "in_review", "returned", "ready", "completed", "stale", "all_authorized"],
      provider_key: "COMMERCIAL_READINESS_PROVIDER",
      provider_status: "AVAILABLE",
      configuration_id: 8,
      configuration_revision: 2,
      configuration_hash: "configuration-hash",
      operational_procurement_excluded: true,
      procurement_approaches: ["DESIGN_BUILD"],
      contracting_models: ["LUMP_SUM"],
      package_types: ["WORK"],
      risk_allocation_categories: ["DESIGN"],
      payment_mechanisms: ["MILESTONE"],
      incentive_mechanisms: ["PAIN_GAIN_SHARE"],
      market_assessment_criteria: ["supplier_depth"],
      supply_chain_criteria: ["long_lead"],
    });
    mocks.readiness.mockResolvedValue(readiness);
    mocks.history.mockResolvedValue([
      {
        version: strategy.current_version,
        lifecycle_events: [{ event_type: "commercial_strategy.created", occurred_at: "2026-09-15" }],
      },
    ]);
    mocks.refreshPreview.mockResolvedValue({
      persisted: false,
      source_delta: [],
      policy_delta: [],
      readiness_delta: {},
      warnings: [],
      blockers: [],
    });
    mocks.update.mockResolvedValue(strategy.current_version);
    mocks.lifecycle.mockResolvedValue(strategy.current_version);
    mocks.newRevision.mockResolvedValue(strategy.current_version);
    mocks.refreshApply.mockResolvedValue(strategy.current_version);
    mocks.configurations.mockResolvedValue([
      {
        id: 8,
        name: "Capital Owner Commercial Strategy",
        description: "Governed policy",
        status: "DRAFT",
        revision: 2,
        version: 3,
        content_json: {
          configuration_code: "COMM-CAPITAL-OWNER",
          applicable_governance_models: [{ code: "CAPITAL_OWNER", label: "CAPITAL_OWNER" }],
          procurement_approaches: [{ code: "DESIGN_BUILD", label: "Design-Build" }],
          readiness_rules: { required_evidence_coverage_percent: 100 },
          review_sod_policy: { require_review: true, require_independent_final_reviewer: true },
        },
      },
    ]);
    mocks.effectivePreview.mockResolvedValue({ persisted: false, configuration_hash: "configuration-hash" });
  });

  it("renders all USER queues and governed tabs without ADMIN configuration controls", async () => {
    render(<CommercialStrategyWorkspace token="token" />);

    expect(await screen.findByRole("heading", { name: "Commercial & Contracting Strategy" })).toBeInTheDocument();
    const queue = screen.getByRole("region", { name: "Commercial Strategy queue" });
    expect(within(queue).getAllByRole("button")).toHaveLength(9);
    expect(
      screen.getByRole("navigation", { name: "Commercial Strategy views" }).querySelectorAll("button")
    ).toHaveLength(14);
    expect(await screen.findByText("CCS-000051 · Version 1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Save$/ })).toBeEnabled();
    expect(screen.getByRole("button", { name: /^Complete$/ })).toBeDisabled();
    expect(screen.queryByRole("button", { name: /Publish|Archive|Clone/ })).not.toBeInTheDocument();
    expect(screen.getByText(/never creates a Tender, Bid, Vendor, Contract/)).toBeInTheDocument();
    await waitFor(() => expect(mocks.options).toHaveBeenCalledWith("token", 101));
  });

  it("normalizes historical object-shaped commercial context for the text editor", async () => {
    mocks.listPage.mockResolvedValue({
      items: [
        {
          ...strategy,
          current_version: {
            ...strategy.current_version,
            content_json: {
              ...content,
              commercial_context: {
                business_need: "Deliver the governed project",
                scope_summary: "Capital works",
              },
            },
          },
        },
      ],
      nextCursor: null,
      pageLimit: 50,
      resultCount: 1,
    });

    render(<CommercialStrategyWorkspace initialView="commercial-strategy-context" token="token" />);

    await waitFor(() =>
      expect(screen.getByLabelText("Commercial context")).toHaveValue(
        '{\n  "business_need": "Deliver the governed project",\n  "scope_summary": "Capital works"\n}'
      )
    );
  });

  it("loads a bounded cursor page and preserves existing rows", async () => {
    mocks.listPage
      .mockResolvedValueOnce({ items: [strategy], nextCursor: "cursor-2", pageLimit: 1, resultCount: 1 })
      .mockResolvedValueOnce({
        items: [{ ...strategy, id: 52, strategy_number: "CCS-000052" }],
        nextCursor: null,
        pageLimit: 1,
        resultCount: 1,
      });

    render(<CommercialStrategyWorkspace token="token" />);
    fireEvent.click(await screen.findByRole("button", { name: "Load more strategies" }));

    await waitFor(() =>
      expect(mocks.listPage).toHaveBeenLastCalledWith(
        "token",
        expect.objectContaining({ cursor: "cursor-2", limit: 50 })
      )
    );
    expect(screen.getByRole("combobox", { name: "Commercial Strategy" })).toHaveTextContent("CCS-000051");
    expect(screen.getByRole("combobox", { name: "Commercial Strategy" })).toHaveTextContent("CCS-000052");
  });

  it("shows non-persistent source, policy and readiness deltas", async () => {
    render(<CommercialStrategyWorkspace token="token" />);
    fireEvent.click(await screen.findByRole("button", { name: "Refresh Preview" }));
    expect(await screen.findByRole("region", { name: "Commercial Strategy refresh preview" })).toHaveTextContent(
      "persisted=false"
    );
    expect(mocks.refreshPreview).toHaveBeenCalledWith("token", 51);
  });

  it("edits every backend-required readiness field with the canonical content contract", async () => {
    render(<CommercialStrategyWorkspace token="token" />);
    await screen.findByText("CCS-000051 · Version 1");

    fireEvent.click(screen.getByRole("button", { name: "Market Assessment" }));
    fireEvent.change(screen.getByLabelText("Overall market capability score"), { target: { value: "85" } });
    fireEvent.change(screen.getByLabelText("Market criterion supplier_depth"), { target: { value: "90" } });

    fireEvent.click(screen.getByRole("button", { name: "Packages" }));
    expect(screen.getByLabelText("Package type 1")).toHaveValue("WORK");
    expect(screen.getByLabelText("Package scope 1")).toHaveValue("Main construction scope");

    fireEvent.click(screen.getByRole("button", { name: "Risk Allocation" }));
    fireEvent.change(screen.getByLabelText("Contractual treatment 1"), {
      target: { value: "Performance requirements and governed security" },
    });
    expect(screen.getByLabelText("Transferability 1")).toBeEnabled();
    expect(screen.getByLabelText("Pricing implication 1")).toBeEnabled();
    expect(screen.getByLabelText("Residual concern 1")).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "Payment & Incentives" }));
    expect(screen.getByLabelText("Payment mechanism")).toHaveValue("MILESTONE");
    expect(screen.getByLabelText("Incentive mechanism")).toHaveValue("PAIN_GAIN_SHARE");

    fireEvent.click(screen.getByRole("button", { name: "Recommendation" }));
    expect(screen.getByLabelText("recommended procurement approach")).toHaveValue("DESIGN_BUILD");
    expect(screen.getByLabelText("commercial recommendation status")).toHaveValue("RECOMMENDED");
    fireEvent.click(screen.getByRole("button", { name: "Add alternative" }));
    fireEvent.change(screen.getByLabelText("Alternative name 1"), { target: { value: "EPC route" } });
    fireEvent.change(screen.getByLabelText("Alternative procurement approach 1"), {
      target: { value: "DESIGN_BUILD" },
    });
    fireEvent.change(screen.getByLabelText("Alternative contracting model 1"), {
      target: { value: "LUMP_SUM" },
    });
    fireEvent.change(screen.getByLabelText("Alternative risk allocation 1"), {
      target: { value: "Contractor-led design integration" },
    });
    fireEvent.change(screen.getByLabelText("Alternative payment mechanism 1"), {
      target: { value: "MILESTONE" },
    });
    fireEvent.change(screen.getByLabelText("Alternative market fit 1"), { target: { value: "Strong" } });
    fireEvent.change(screen.getByLabelText("Alternative commercial risk 1"), {
      target: { value: "Moderate" },
    });
    fireEvent.change(screen.getByLabelText("Alternative pros 1"), { target: { value: "Single accountability" } });
    fireEvent.change(screen.getByLabelText("Alternative cons 1"), { target: { value: "Risk premium" } });
    fireEvent.change(screen.getByLabelText("Alternative rating 1"), { target: { value: "82" } });

    fireEvent.click(screen.getByRole("button", { name: /^Save$/ }));
    await waitFor(() => expect(mocks.update).toHaveBeenCalled());
    const saved = mocks.update.mock.calls[0][3] as Record<string, unknown>;
    expect(saved.market_assessment).toEqual(expect.objectContaining({ overall_score: 85 }));
    expect(saved.risk_allocations).toEqual([
      expect.objectContaining({ contractual_treatment: "Performance requirements and governed security" }),
    ]);
    expect(saved).toHaveProperty("commercial_assumptions");
    expect(saved).toHaveProperty("commercial_constraints");
    expect(saved).toHaveProperty("conditions_open_issues");
    expect(saved.alternatives).toEqual([
      {
        alternative_code: "ALT-1",
        name: "EPC route",
        procurement_approach: "DESIGN_BUILD",
        contracting_model: "LUMP_SUM",
        risk_allocation: "Contractor-led design integration",
        payment_mechanism: "MILESTONE",
        market_fit: "Strong",
        commercial_risk: "Moderate",
        pros: ["Single accountability"],
        cons: ["Risk premium"],
        rating: 82,
      },
    ]);
    expect(saved).not.toHaveProperty("assumptions");
    expect(saved).not.toHaveProperty("incentive_mechanism");
  });

  it("renders ADMIN catalogs and policy controls without live Project transactions", async () => {
    render(<CommercialStrategyAdminView token="token" />);

    const admin = await screen.findByRole("region", { name: "Commercial Strategy Configuration" });
    expect(
      within(admin)
        .getByRole("navigation", { name: "Commercial Strategy configuration sections" })
        .querySelectorAll("button")
    ).toHaveLength(20);
    expect(within(admin).getByRole("button", { name: "Save draft" })).toBeEnabled();
    expect(within(admin).getByRole("button", { name: "Publish" })).toBeEnabled();
    expect(within(admin).queryByRole("button", { name: /^Submit$/ })).not.toBeInTheDocument();
    expect(within(admin).queryByRole("button", { name: /^Complete$/ })).not.toBeInTheDocument();
    expect(within(admin).getByLabelText("Advanced Commercial Strategy configuration read only").tagName).toBe("PRE");
  });

  it("validates governed tailoring JSON before ADMIN save or publish", async () => {
    render(<CommercialStrategyAdminView token="token" />);
    const admin = await screen.findByRole("region", { name: "Commercial Strategy Configuration" });

    fireEvent.click(within(admin).getByRole("button", { name: "Project Type Overrides" }));
    const tailoring = within(admin).getByLabelText("Tailoring rules");
    fireEvent.change(tailoring, { target: { value: "{not-an-array}" } });
    expect(within(admin).getByRole("alert")).toHaveTextContent(/json|expected/i);
    expect(within(admin).getByRole("button", { name: "Save draft" })).toBeDisabled();
    expect(within(admin).getByRole("button", { name: "Publish" })).toBeDisabled();

    fireEvent.change(tailoring, {
      target: {
        value: JSON.stringify([
          {
            match: { project_size: ["LARGE"], fel_stage: ["FEL-3"] },
            overrides: { minimum_alternatives: 3 },
          },
        ]),
      },
    });
    expect(within(admin).queryByRole("alert")).not.toBeInTheDocument();
    expect(within(admin).getByRole("button", { name: "Save draft" })).toBeEnabled();

    fireEvent.click(within(admin).getByRole("button", { name: "FEL / Gate Requirements" }));
    expect(within(admin).getByLabelText("Applicable Gate Profiles")).toBeInTheDocument();
  });

  it("resolves ADMIN inheritance preview without persisting a live record", async () => {
    render(<CommercialStrategyAdminView token="token" />);
    fireEvent.change(await screen.findByLabelText("Project Workspace ID (optional)"), { target: { value: "101" } });
    fireEvent.click(screen.getByRole("button", { name: "Preview persisted=false" }));
    await waitFor(() =>
      expect(mocks.effectivePreview).toHaveBeenCalledWith(
        "token",
        101,
        8,
        expect.objectContaining({ configuration_code: "COMM-CAPITAL-OWNER" })
      )
    );
    expect(screen.getByText("persisted=false", { selector: "strong" })).toBeInTheDocument();
  });
});
