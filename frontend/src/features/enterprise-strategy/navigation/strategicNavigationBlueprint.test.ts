import { describe, expect, it } from "vitest";
import {
  buildStrategicMacroprocess,
  canAccessStrategicNode,
  orderStrategicWorkspaceNavigator,
  strategicBreadcrumb,
  strategicNavigationBlueprint,
  strategicNodeApplies,
  strategicRouteForView,
  strategicRouteMatch,
  strategicRouteRegistry,
} from "./strategicNavigationBlueprint";
import { STRATEGIC_CONTROL_CLASSIFICATIONS } from "./strategicControlClassification";

const expectedPhases = [
  "Enterprise Foundation",
  "Strategic Capital Planning & Demand",
  "Investment Origination & Shaping",
  "Strategic Gate",
  "Portfolio Planning & Review",
  "Portfolio Scenario Planning",
  "Business Case & Investment Development",
  "Investment Governance",
];

describe("strategic navigation blueprint", () => {
  it("adds governed QRA foundation and execution views to existing phase 6 without mode leakage", () => {
    const user = buildStrategicMacroprocess("user");
    const admin = buildStrategicMacroprocess("admin");
    expect(user.modules).toHaveLength(8);
    expect(user.modules[6].key).toBe("phase-6-project-definition-investment-case");
    expect(user.modules[6].label).toBe("Business Case & Investment Development");
    const qra = user.modules[6].submodules.find((item) => item.label === "QRA")!;
    expect(qra.children?.map((item) => item.label)).toEqual([
      "Cost Source Readiness",
      "Schedule Source Readiness",
      "Model Definition",
      "Foundation History",
      "Approved Models",
      "Runs",
      "Run Overview",
      "Cost Results",
      "Schedule Results",
      "Percentiles",
      "Sensitivity / Drivers",
      "Convergence",
      "Evidence / Traceability",
      "Run Comparison",
      "Run History",
    ]);
    expect(strategicRouteForView("qra-model-definition", "user")).toBe("/app/strategy/qra-model-definition");
    expect(strategicRouteForView("qra-methodology-source-readiness", "user")).toBeNull();
    expect(strategicRouteForView("qra-foundation", "admin")).toBeNull();
    expect(admin.modules[6].submodules.map((item) => item.label)).toContain("QRA Methodology & Source Readiness");
    expect(qra.children?.some((item) => /Integrated/.test(item.label))).toBe(false);
    expect(strategicRouteForView("qra-runs", "user")).toBe("/app/strategy/qra-runs");
    expect(strategicRouteForView("qra-runs", "admin")).toBeNull();
  });
  it("orders USER and ADMIN navigation by business phase with Foundation first", () => {
    const user = buildStrategicMacroprocess("user");
    const admin = buildStrategicMacroprocess("admin");

    expect(user.modules.map((item) => item.label)).toEqual(expectedPhases);
    expect(admin.modules.map((item) => item.label)).toEqual([
      "Enterprise Foundation",
      "Strategic Capital Planning & Demand Configuration",
      "Investment Origination & Shaping Configuration",
      "Strategic Gate Decision Configuration",
      "Portfolio Planning & Review Configuration",
      "Portfolio Scenario Planning Configuration",
      "Project Definition & Investment Case",
      "Investment Governance",
    ]);
    expect(user.modules[0]).toMatchObject({ phase: 0, isFoundation: true, badge: "Foundation / prerequisite" });
    expect(user.modules[1]).toMatchObject({ phase: 1, badge: "Start of capital planning" });
    expect(user.modules[1].submodules.map((item) => item.label)).toEqual([
      "Planning Cycles",
      "Capital Demand Pipeline",
      "My Demands",
      "Demands in Review",
      "Endorsed Demands",
      "Demand History",
      "Strategic Capital Allocation",
      "Allocation History",
    ]);
    expect(user.modules[2]).toMatchObject({ phase: 2, badge: "Demand → Idea is explicit" });
    expect(user.modules[2].submodules.map((item) => item.label)).toEqual([
      "Idea Lifecycle",
      "Business Analysis & Options",
      "Project Proposals",
    ]);
    const shapingPhase = strategicNavigationBlueprint.find(
      (item) => item.mode === "user" && item.id === "phase-1-idea-demand"
    );
    expect(shapingPhase?.children[2].predecessorIds).toEqual(["business-analysis-options"]);
    expect(admin.modules[1].submodules.map((item) => item.label)).toEqual([
      "Strategic Capital Planning & Demand Configuration",
      "Strategic Capital Buckets",
    ]);
    expect(admin.modules[2].submodules.map((item) => item.label)).toEqual([
      "Idea & Demand Configuration",
      "Business Analysis Configuration",
      "Project Proposal Configuration",
    ]);
  });

  it("models Budget and Resources as parallel predecessors of Scenario Convergence", () => {
    const phase = strategicNavigationBlueprint.find(
      (item) => item.mode === "user" && item.id === "phase-5-portfolio-scenario-planning"
    );
    const [budget, resources, convergence] = phase?.children ?? [];

    expect(budget.parallelGroup).toBe("portfolio-scenario-inputs");
    expect(resources.parallelGroup).toBe("portfolio-scenario-inputs");
    expect(budget.convergesInto).toBe(convergence.id);
    expect(resources.convergesInto).toBe(convergence.id);
    expect(convergence.predecessorIds).toEqual([budget.id, resources.id]);
    expect(resources.predecessorIds).not.toContain(budget.id);
  });

  it("registers Periodic Portfolio Review USER sessions and ADMIN policy from the canonical blueprint", () => {
    const userPhase = buildStrategicMacroprocess("user").modules[5];
    const review = userPhase.submodules.find((item) => item.label === "Periodic Portfolio Review");
    const adminPhase = buildStrategicMacroprocess("admin").modules[4];

    expect(userPhase.label).toBe("Portfolio Scenario Planning");
    expect(userPhase.submodules.map((item) => item.label)).toEqual([
      "Budget Planning & Scenarios",
      "Resource Planning & Scenarios",
      "Scenario Convergence & Recommendation",
      "Periodic Portfolio Review",
    ]);
    expect(
      buildStrategicMacroprocess("user").modules[4].submodules.some(
        (item) => item.label === "Periodic Portfolio Review"
      )
    ).toBe(false);
    const reviewNode = strategicNavigationBlueprint.find((item) => item.mode === "user" && item.phase === 5)
      ?.children[3];
    expect(reviewNode?.predecessorIds).toEqual(["scenario-convergence-recommendation"]);
    expect(review?.children?.map((item) => item.label)).toEqual([
      "Review Calendar / Sessions",
      "Overview",
      "Portfolio Snapshot",
      "Strategic Allocation",
      "Project Matrix",
      "Budget & Resources",
      "Gate / FID Status",
      "Exceptions",
      "Conclusions",
      "Actions",
      "History",
      "Trends",
    ]);
    expect(strategicRouteForView("portfolio-review-actions", "user")).toBe("/app/strategy/portfolio-review-actions");
    expect(strategicBreadcrumb("portfolio-review-actions", "user")).toEqual([
      "Enterprise Strategy Manager",
      "Portfolio Scenario Planning",
      "Periodic Portfolio Review",
      "Actions",
    ]);
    expect(adminPhase.submodules.map((item) => item.label)).toContain("Periodic Portfolio Review");
    expect(strategicRouteForView("portfolio-review-configuration", "admin")).toBe(
      "/app/admin/strategy/portfolio-review-configuration"
    );
  });

  it("models existing evidence contributors and QRA preparation in the governed definition phase", () => {
    const definition = strategicNavigationBlueprint.find(
      (item) => item.mode === "user" && item.id === "phase-6-project-definition-investment-case"
    );
    const governance = strategicNavigationBlueprint.find(
      (item) => item.mode === "user" && item.id === "phase-7-investment-governance"
    );

    expect(definition?.children.map((item) => item.label)).toEqual([
      "Project Definition / FEL",
      "Business Case Manager",
      "Strategic Benefits Plan & Traceability",
      "Commercial & Contracting Strategy",
      "Funds & Funding Readiness",
      "Economic & Financial Model",
      "Risk Readiness",
      "Permit Readiness",
      "Basic Data Readiness",
      "Owner Capability Readiness",
      "QRA",
    ]);
    expect(definition?.children.every((item) => item.convergesInto === "investment-gate-preparation")).toBe(true);
    expect(governance?.children[0].predecessorIds).toEqual(definition?.children.map((item) => item.id));
    expect(definition?.children.find((item) => item.id === "business-case-manager")?.longitudinal).toBe(true);
    expect(
      definition?.children.find((item) => item.id === "business-case-manager")?.children.map((item) => item.label)
    ).toEqual([
      "Overview",
      "Strategic Case",
      "Economic Case",
      "Commercial Case",
      "Financial Case",
      "Management Case",
      "Sources & Evidence",
      "Readiness",
      "Decision Snapshots",
      "History",
    ]);
    expect(definition?.children.find((item) => item.id === "strategic-benefits-plan")).toMatchObject({
      classification: "USER_TRANSACTION",
      governanceModels: ["CAPITAL_OWNER"],
      view: "strategic-benefits-my",
    });
    expect(definition?.children.find((item) => item.id === "commercial-contracting-strategy")).toMatchObject({
      classification: "USER_TRANSACTION",
      governanceModels: ["CAPITAL_OWNER"],
      view: "commercial-strategy-my",
    });
  });

  it("keeps route and breadcrumb metadata deterministic for deep links", () => {
    expect(strategicRouteForView("capital-demand-pipeline", "user")).toBe("/app/strategy/capital-demand-pipeline");
    expect(strategicRouteForView("capital-planning-configuration", "admin")).toBe(
      "/app/admin/strategy/capital-planning-configuration"
    );
    expect(strategicRouteForView("idea-lifecycle", "user")).toBe("/app/strategy/idea-lifecycle");
    expect(strategicRouteForView("business-analysis-options", "user")).toBe("/app/strategy/business-analysis-options");
    expect(strategicRouteForView("project-proposal", "user")).toBe("/app/strategy/project-proposal");
    const route = strategicRouteForView("investment-decision-queue", "user");
    expect(route).toBe("/app/strategy/investment-decision-queue");
    expect(strategicRouteMatch(route ?? "")).toEqual({ mode: "user", view: "investment-decision-queue" });
    expect(strategicBreadcrumb("investment-decision-queue", "user")).toEqual([
      "Enterprise Strategy Manager",
      "Investment Governance",
      "Investment Decision / FID",
      "Decision Queue",
    ]);
  });

  it("classifies every strategic control and keeps USER and ADMIN responsibilities separated", () => {
    const flatten = (items: typeof strategicNavigationBlueprint): typeof strategicNavigationBlueprint =>
      items.flatMap((item) => [item, ...flatten(item.children)]);
    const controls = flatten(strategicNavigationBlueprint);

    expect(controls.length).toBeGreaterThan(80);
    expect(controls.every((item) => STRATEGIC_CONTROL_CLASSIFICATIONS.includes(item.classification))).toBe(true);
    expect(
      controls.filter((item) => item.mode === "user").every((item) => item.classification !== "ADMIN_CONFIGURATION")
    ).toBe(true);
    expect(
      controls.filter((item) => item.mode === "admin").every((item) => item.classification !== "USER_TRANSACTION")
    ).toBe(true);
    expect(controls.find((item) => item.id === "foundation-status")?.classification).toBe("READ_ONLY_SHARED");
    expect(controls.find((item) => item.id === "business-analysis-options")?.classification).toBe("USER_TRANSACTION");
    expect(controls.find((item) => item.id === "capital-demand-pipeline")?.classification).toBe("USER_TRANSACTION");
    expect(controls.find((item) => item.id === "admin-capital-planning-configuration")?.classification).toBe(
      "ADMIN_CONFIGURATION"
    );
    expect(controls.find((item) => item.id === "admin-business-analysis-configuration")?.classification).toBe(
      "ADMIN_CONFIGURATION"
    );
  });

  it("enforces the existing can_configure permission on direct ADMIN routes", () => {
    const adminBusinessAnalysis = strategicNavigationBlueprint
      .flatMap((phase) => [phase, ...phase.children])
      .find((item) => item.id === "admin-business-analysis-configuration");
    expect(adminBusinessAnalysis).toBeDefined();
    expect(canAccessStrategicNode(adminBusinessAnalysis!, { authenticated: true, canConfigure: false })).toBe(false);
    expect(canAccessStrategicNode(adminBusinessAnalysis!, { authenticated: true, canConfigure: true })).toBe(true);
    expect(strategicRouteRegistry().get("/app/admin/strategy/business-analysis-configuration")).toEqual({
      mode: "admin",
      view: "business-analysis-configuration",
    });
    expect(strategicRouteRegistry().get("/app/admin/strategy/commercial-strategy-configuration")).toEqual({
      mode: "admin",
      view: "commercial-strategy-configuration",
    });
    expect(strategicRouteRegistry().get("/app/admin/strategy/benefits-configuration")).toEqual({
      mode: "admin",
      view: "benefits-configuration",
    });
  });

  it("places Strategic Benefits between Business Case and Commercial Strategy with canonical deep links", () => {
    expect(strategicRouteForView("strategic-benefits-traceability", "user")).toBe(
      "/app/strategy/strategic-benefits-traceability"
    );
    expect(strategicBreadcrumb("strategic-benefits-traceability", "user")).toEqual([
      "Enterprise Strategy Manager",
      "Business Case & Investment Development",
      "Strategic Benefits Plan & Traceability",
      "Traceability",
    ]);
    const user = buildStrategicMacroprocess("user").modules[6];
    const labels = user.submodules.map((item) => item.label);
    expect(labels.indexOf("Business Case Manager")).toBeLessThan(
      labels.indexOf("Strategic Benefits Plan & Traceability")
    );
    expect(labels.indexOf("Strategic Benefits Plan & Traceability")).toBeLessThan(
      labels.indexOf("Commercial & Contracting Strategy")
    );
    const admin = buildStrategicMacroprocess("admin").modules[6];
    expect(admin.submodules.map((item) => item.label)).toContain("Benefits Configuration");
    expect(admin.submodules.map((item) => item.label)).not.toContain("Strategic Benefits Plan & Traceability");
  });

  it("keeps Commercial Strategy in Phase 6 with canonical USER deep links and ADMIN separation", () => {
    expect(strategicRouteForView("commercial-strategy-risk-allocation", "user")).toBe(
      "/app/strategy/commercial-strategy-risk-allocation"
    );
    expect(strategicBreadcrumb("commercial-strategy-risk-allocation", "user")).toEqual([
      "Enterprise Strategy Manager",
      "Business Case & Investment Development",
      "Commercial & Contracting Strategy",
      "Risk Allocation",
    ]);
    const admin = buildStrategicMacroprocess("admin").modules[6];
    expect(admin.submodules.map((item) => item.label)).toContain("Commercial Strategy Configuration");
    expect(admin.submodules.map((item) => item.label)).not.toContain("Commercial & Contracting Strategy");
  });

  it("preserves CAPITAL_OWNER applicability without forcing owner-only phases on alternate governance models", () => {
    const ownerPhase = strategicNavigationBlueprint.find(
      (item) => item.mode === "user" && item.id === "phase-7-investment-governance"
    );
    expect(ownerPhase).toBeDefined();
    expect(strategicNodeApplies(ownerPhase!, { governanceModel: "CAPITAL_OWNER", workspaceType: "PROJECT" })).toBe(
      true
    );
    expect(
      strategicNodeApplies(ownerPhase!, { governanceModel: "CONTRACTOR_DELIVERY", workspaceType: "PROJECT" })
    ).toBe(false);
    expect(strategicNodeApplies(ownerPhase!, { governanceModel: "DIRECT_INTERNAL", workspaceType: "PROJECT" })).toBe(
      false
    );
  });

  it("orders Workspace Navigator entries without changing backend state or permissions", () => {
    const items = [
      { code: "portfolio-resource-planning", state: "READY" },
      { code: "ideas", state: "READY" },
      { code: "business-analyses", state: "READY" },
      { code: "portfolio-budget-planning", state: "PLANNED" },
      { code: "project-proposals", state: "READY" },
    ];
    const result = orderStrategicWorkspaceNavigator(items, "PORTFOLIO");

    expect(result.map((item) => item.code)).toEqual([
      "ideas",
      "business-analyses",
      "project-proposals",
      "portfolio-budget-planning",
      "portfolio-resource-planning",
    ]);
    expect(result.find((item) => item.code === "portfolio-budget-planning")?.state).toBe("PLANNED");
  });

  it("places Wave 2B policy in ADMIN and technical evidence in USER with canonical scoped routes", () => {
    const admin = buildStrategicMacroprocess("admin");
    expect(admin.modules[0].submodules.map((item) => item.label)).toContain("Risk Governance");
    expect(admin.modules[6].submodules.map((item) => item.label)).toContain("Basic Data Readiness Configuration");
    expect(buildStrategicMacroprocess("user").modules[6].submodules.map((item) => item.label)).toContain(
      "Basic Data Readiness"
    );
    expect(strategicRouteForView("basic-data-readiness", "user")).toBe("/app/strategy/basic-data-readiness");
    expect(strategicRouteForView("basic-data-configuration", "user")).toBeNull();
    expect(strategicRouteForView("risk-governance-configuration", "user")).toBeNull();
    const risk = strategicNavigationBlueprint
      .flatMap((phase) => phase.children)
      .find((item) => item.view === "risk-governance-configuration")!;
    expect(risk.classification).toBe("ADMIN_CONFIGURATION");
    expect(canAccessStrategicNode(risk, { authenticated: true, canConfigure: false })).toBe(false);
    expect(strategicRouteRegistry().get("/app/admin/strategy/risk-governance-configuration")).toEqual({
      mode: "admin",
      view: "risk-governance-configuration",
    });
  });
  it("adds Owner Capability to existing phase 6 only, with canonical ADMIN and USER boundaries", () => {
    const user = buildStrategicMacroprocess("user");
    const admin = buildStrategicMacroprocess("admin");
    expect(user.modules).toHaveLength(8);
    expect(admin.modules).toHaveLength(8);
    expect(user.modules[6].submodules.map((item) => item.label)).toContain("Owner Capability Readiness");
    expect(admin.modules[6].submodules.map((item) => item.label)).toContain("Owner Capability Readiness Configuration");
    expect(strategicRouteForView("owner-capability-readiness", "user")).toBe(
      "/app/strategy/owner-capability-readiness"
    );
    expect(strategicRouteForView("owner-capability-configuration", "user")).toBeNull();
    expect(strategicRouteForView("owner-capability-readiness", "admin")).toBeNull();
    const configuration = strategicNavigationBlueprint
      .flatMap((phase) => phase.children)
      .find((item) => item.view === "owner-capability-configuration")!;
    expect(configuration.classification).toBe("ADMIN_CONFIGURATION");
    expect(canAccessStrategicNode(configuration, { authenticated: true, canConfigure: false })).toBe(false);
    expect(strategicRouteRegistry().get("/app/admin/strategy/owner-capability-configuration")).toEqual({
      mode: "admin",
      view: "owner-capability-configuration",
    });
  });
});
