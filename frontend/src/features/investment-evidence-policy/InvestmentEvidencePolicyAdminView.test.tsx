import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import InvestmentEvidencePolicyAdminView from "./InvestmentEvidencePolicyAdminView";

const mocks = vi.hoisted(() => ({
  overview: vi.fn(),
  preview: vi.fn(),
  clone: vi.fn(),
  cloneGate07jEvid2: vi.fn(),
  save: vi.fn(),
  publish: vi.fn(),
  portfolioOptions: vi.fn(),
}));

vi.mock("./api", () => ({ investmentEvidencePolicyApi: mocks }));
vi.mock("../portfolio-planning/api", () => ({
  portfolioPlanningApi: { portfolioOptions: mocks.portfolioOptions },
}));

const requirement = (evidenceType: string, classification: "A" | "B" | "C", providerKey?: string) => ({
  requirement_key: evidenceType.toLowerCase().replace(/_/g, "-"),
  evidence_type: evidenceType,
  classification,
  required: classification !== "C",
  blocking: classification === "A",
  scope: evidenceType === "PERMIT_READINESS" ? "EACH_PROJECT" : "PORTFOLIO",
  provider_key: providerKey || null,
  provider_required: classification === "A",
  validity_period_days: classification === "C" ? null : 180,
  coverage_requirement: evidenceType === "PERMIT_READINESS" ? 100 : null,
  allow_manual_reference: classification === "B",
  manual_validation_required: classification === "B",
  rationale: `Controlled ${evidenceType} decision.`,
  order: 10,
});

const content = {
  policy_code: "PYP-INVESTMENT-EVIDENCE",
  policy_name: "Investment Decision Evidence Policy",
  applicable_governance_models: ["CAPITAL_OWNER"],
  gate_profiles: {
    "PYP-INV-SELECT": {
      allow_valid_with_conditions: true,
      requirements: [
        requirement("PORTFOLIO_RECOMMENDATION", "A", "GATE07I_PORTFOLIO_RECOMMENDATION"),
        requirement("RISK_READINESS", "B"),
        requirement("LAND_ACCESS_READINESS", "C"),
      ],
    },
    "PYP-FFA": {
      allow_valid_with_conditions: false,
      requirements: [
        requirement("PORTFOLIO_RECOMMENDATION", "A", "GATE07I_PORTFOLIO_RECOMMENDATION"),
        requirement("RISK_READINESS", "A", "RISK_READINESS_PROVIDER"),
        requirement("PERMIT_READINESS", "B"),
      ],
    },
  },
  project_type_overrides: [
    {
      gate_profile_code: "PYP-FFA",
      project_type_filter: ["MINING"],
      evidence_type: "PERMIT_READINESS",
      classification: "A",
      provider_key: "PERMIT_READINESS_PROVIDER",
      rationale: "Mining FFA requires a governed permit provider.",
    },
  ],
  blocking_policy: { class_A_failure: "BLOCK" },
  validity_policy: { no_global_expiration: true },
  coverage_policy: { do_not_average_missing_projects: true },
};

const draft = {
  id: 801,
  tenant_id: 1,
  kind: "investment_evidence_policy",
  code: "pyp-investment-decision-evidence-policy",
  name: "Investment Decision Evidence Policy",
  description: "Controlled A/B/C matrix",
  status: "draft" as const,
  revision: 1,
  version: 1,
  content_json: content,
  content_hash: "a".repeat(64),
};

const providers = [
  {
    provider_key: "GATE07I_PORTFOLIO_RECOMMENDATION",
    evidence_type: "PORTFOLIO_RECOMMENDATION",
    source_module: "PORTFOLIO_SCENARIO_CONVERGENCE",
    source_contract: "InvestmentGatePreparationContractOut",
    status: "AVAILABLE",
    version: "1.0",
    supports_portfolio_scope: true,
    supports_project_scope: false,
    supports_project_set_scope: true,
    supports_hash: true,
    supports_current_flag: true,
    supports_readiness: true,
    notes: "Validated source",
    contract_valid: true,
    contract_issues: [],
  },
  {
    provider_key: "RISK_READINESS_PROVIDER",
    evidence_type: "RISK_READINESS",
    source_module: "RESERVED",
    source_contract: "Not implemented",
    status: "UNAVAILABLE",
    version: "1.0",
    supports_portfolio_scope: true,
    supports_project_scope: true,
    supports_project_set_scope: true,
    supports_hash: false,
    supports_current_flag: false,
    supports_readiness: false,
    notes: "Missing provider",
    contract_valid: false,
    contract_issues: ["PROVIDER_UNAVAILABLE"],
  },
];

describe("Gate 07J-EVID Investment Decision Evidence Policy", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.portfolioOptions.mockResolvedValue([{ id: 71, name: "Capital Portfolio" }]);
    mocks.overview.mockResolvedValue({
      configurations: [draft],
      providers,
      missing_providers: [
        {
          evidence_type: "RISK_READINESS",
          gate_profile: "PYP-FFA",
          project_type: null,
          classification: "A",
          blocking: true,
          provider: "RISK_READINESS_PROVIDER",
          provider_status: "UNAVAILABLE",
          gap_status: "PROVIDER_MISSING",
          recommended_action: "BUILD_MISSING_GOVERNED_PROVIDER",
        },
      ],
      required_adr_decisions: [],
      allowed_actions: [],
      boundaries: ["NO_CLASS_A_TO_CLASS_B_FALLBACK", "NO_INVESTMENT_DECISION_OR_FID"],
    });
    mocks.preview.mockResolvedValue({
      policy: { id: 801, revision: 1, hash: "a".repeat(64), status: "draft" },
      gate_profile_code: "PYP-FFA",
      portfolio_workspace_id: 71,
      project_contexts: [{ project_workspace_id: 101, project_type: "MINING" }],
      effective_matrix: content.gate_profiles["PYP-FFA"].requirements,
      provider_registry_snapshot: providers,
      current_evidence_status: [],
      missing_providers: [
        {
          evidence_type: "RISK_READINESS",
          gate_profile: "PYP-FFA",
          project_type: null,
          classification: "A",
          blocking: true,
          provider: "RISK_READINESS_PROVIDER",
          provider_status: "UNAVAILABLE",
          gap_status: "PROVIDER_MISSING",
          recommended_action: "BUILD_MISSING_GOVERNED_PROVIDER",
        },
      ],
      available_provider_count: 1,
      missing_required_provider_count: 1,
      class_A_count: 2,
      class_B_count: 1,
      class_C_count: 0,
      blocking_missing_sources: ["RISK_READINESS"],
      warnings: [],
      blockers: ["SOURCE_PROVIDER_MISSING"],
      would_gate07j_be_ready: false,
      recommended_next_development: {
        next: "BUILD_MISSING_GOVERNED_PROVIDER",
        provider: "RISK_READINESS_PROVIDER",
      },
      can_design_investment_decision_gate: false,
      can_enter_fid: false,
      persisted: false,
      final_output: "READY_FOR_INVESTMENT_DECISION_EVIDENCE_POLICY",
    });
    mocks.cloneGate07jEvid2.mockResolvedValue({
      ...draft,
      id: 802,
      revision: 2,
      content_json: {
        ...content,
        decision_criterion_policy: { policy_code: "GATE07J-EVID-2", criteria_by_profile: {} },
      },
    });
  });

  it("shows the contextual matrix and controlled provider registry", async () => {
    const user = userEvent.setup();
    render(<InvestmentEvidencePolicyAdminView token="token" />);
    expect(await screen.findByRole("heading", { name: "Evidence & Decision Policy" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Evidence Policy" }));
    const matrix = screen.getByRole("table");
    expect(within(matrix).getAllByText("A · Governed source required").length).toBeGreaterThan(0);
    expect(within(matrix).getByText("C · Not required")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Provider Registry" }));
    expect(screen.getByText("GATE07I_PORTFOLIO_RECOMMENDATION")).toBeInTheDocument();
    expect(screen.getByText("RISK_READINESS_PROVIDER")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /approve investment|\bfid\b|\bgo\b|\bhold\b|\bkill\b/i })
    ).not.toBeInTheDocument();
  });

  it("runs a non-persistent preview and exposes the deterministic next provider", async () => {
    const user = userEvent.setup();
    render(<InvestmentEvidencePolicyAdminView token="token" />);
    await screen.findByRole("heading", { name: "Evidence & Decision Policy" });
    await user.click(
      within(screen.getByRole("group", { name: "Evidence policy actions" })).getByRole("button", {
        name: "Preview",
      })
    );
    await waitFor(() => expect(mocks.preview).toHaveBeenCalled());
    expect(screen.getByRole("status")).toHaveTextContent("persisted=false");
    expect(screen.getByText("SOURCE_PROVIDER_MISSING")).toBeInTheDocument();
    expect(screen.getAllByText(/RISK_READINESS_PROVIDER/)).not.toHaveLength(0);
    expect(screen.getByText("false")).toBeInTheDocument();
  });

  it("uses the dedicated idempotent Gate07J-EVID-2 clone operation", async () => {
    const published = { ...draft, status: "published" as const };
    mocks.overview.mockResolvedValueOnce({
      configurations: [published],
      providers,
      missing_providers: [],
      required_adr_decisions: [],
      allowed_actions: [],
      boundaries: ["NO_CLASS_A_TO_CLASS_B_FALLBACK", "NO_INVESTMENT_DECISION_OR_FID"],
    });
    const user = userEvent.setup();
    render(<InvestmentEvidencePolicyAdminView token="token" />);
    const actions = await screen.findByRole("group", { name: "Evidence policy actions" });
    await user.click(within(actions).getByRole("button", { name: "Clone Gate07J-EVID-2 DRAFT" }));
    await waitFor(() => expect(mocks.cloneGate07jEvid2).toHaveBeenCalledWith("token", published));
    expect(screen.getByRole("status")).toHaveTextContent("clone-evid2 completed");
  });
});
