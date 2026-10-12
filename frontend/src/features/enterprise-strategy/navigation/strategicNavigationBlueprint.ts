import type {
  ApplicationMode,
  ControlFlowView,
  MacroprocessNavigationItem,
  ModuleNavigationItem,
  NavigationViewItem,
} from "../../../navigation/applicationNavigation";
import {
  STRATEGIC_PERMISSION_BY_CLASSIFICATION,
  type StrategicControlClassification,
} from "./strategicControlClassification";

export type StrategicGovernanceModel =
  | "CAPITAL_OWNER"
  | "CONTRACTOR_DELIVERY"
  | "DIRECT_INTERNAL"
  | "LEGACY_UNCLASSIFIED";

export type StrategicNavigationNode = {
  id: string;
  label: string;
  description: string;
  phase: number;
  order: number;
  route: string;
  mode: ApplicationMode;
  classification: StrategicControlClassification;
  permission: "authenticated" | "can_configure";
  workspaceTypes: string[];
  governanceModels: StrategicGovernanceModel[];
  children: StrategicNavigationNode[];
  isFoundation: boolean;
  predecessorIds: string[];
  parallelGroup: string | null;
  convergesInto: string | null;
  view: ControlFlowView;
  badge?: string;
  longitudinal?: boolean;
};

type NodeInput = Omit<
  StrategicNavigationNode,
  | "children"
  | "classification"
  | "convergesInto"
  | "governanceModels"
  | "isFoundation"
  | "mode"
  | "parallelGroup"
  | "permission"
  | "predecessorIds"
  | "route"
  | "workspaceTypes"
> & {
  children?: StrategicNavigationNode[];
  classification?: StrategicControlClassification;
  convergesInto?: string | null;
  governanceModels?: StrategicGovernanceModel[];
  isFoundation?: boolean;
  parallelGroup?: string | null;
  predecessorIds?: string[];
  route?: string;
  workspaceTypes?: string[];
};

const OWNER_MODELS: StrategicGovernanceModel[] = ["CAPITAL_OWNER"];
const ALL_GOVERNANCE_MODELS: StrategicGovernanceModel[] = [
  "CAPITAL_OWNER",
  "CONTRACTOR_DELIVERY",
  "DIRECT_INTERNAL",
  "LEGACY_UNCLASSIFIED",
];
const ENTERPRISE_CONTEXTS = ["ENTERPRISE", "BUSINESS_UNIT", "PORTFOLIO"];
const PROJECT_CONTEXTS = ["PROJECT"];

function routeFor(mode: ApplicationMode, view: ControlFlowView) {
  const root = mode === "admin" ? "/app/admin/strategy" : "/app/strategy";
  return `${root}/${view}`;
}

function node(mode: ApplicationMode, input: NodeInput): StrategicNavigationNode {
  const classification = input.classification ?? (mode === "admin" ? "ADMIN_CONFIGURATION" : "USER_TRANSACTION");
  return {
    ...input,
    children: input.children ?? [],
    classification,
    convergesInto: input.convergesInto ?? null,
    governanceModels: input.governanceModels ?? ALL_GOVERNANCE_MODELS,
    isFoundation: input.isFoundation ?? input.phase === 0,
    mode,
    parallelGroup: input.parallelGroup ?? null,
    permission: STRATEGIC_PERMISSION_BY_CLASSIFICATION[classification],
    predecessorIds: input.predecessorIds ?? [],
    route: input.route ?? routeFor(mode, input.view),
    workspaceTypes: input.workspaceTypes ?? [...ENTERPRISE_CONTEXTS, ...PROJECT_CONTEXTS],
  };
}

function detailNodes(
  mode: ApplicationMode,
  phase: number,
  prefix: string,
  items: Array<[ControlFlowView, string, StrategicControlClassification?]>,
  governanceModels: StrategicGovernanceModel[] = OWNER_MODELS,
  workspaceTypes: string[] = PROJECT_CONTEXTS
) {
  return items.map(([view, label, classification], index) =>
    node(mode, {
      id: `${prefix}-${view}`,
      label,
      description: `Open the governed ${label} view without changing its existing business rules.`,
      phase,
      order: index + 1,
      view,
      classification,
      governanceModels,
      workspaceTypes,
    })
  );
}

const userFoundation = node("user", {
  id: "phase-0-enterprise-foundation",
  label: "Enterprise Foundation",
  description:
    "Establish the organizational, portfolio and strategic context required before strategic transactions begin.",
  phase: 0,
  order: 0,
  view: "enterprise-strategy-overview",
  classification: "READ_ONLY_SHARED",
  badge: "Foundation / prerequisite",
  isFoundation: true,
  workspaceTypes: ENTERPRISE_CONTEXTS,
  children: [
    node("user", {
      id: "foundation-status",
      label: "Foundation Status",
      description:
        "Review the existing enterprise, owning Workspace, strategic objective and Idea configuration signals.",
      phase: 0,
      order: 1,
      view: "enterprise-strategy-overview",
      classification: "READ_ONLY_SHARED",
      isFoundation: true,
      workspaceTypes: ENTERPRISE_CONTEXTS,
    }),
    node("user", {
      id: "enterprise-explorer",
      label: "Enterprise Explorer",
      description: "Browse the published Enterprise Workspace Structure and its governed relationships.",
      phase: 0,
      order: 2,
      view: "enterprise-explorer",
      classification: "READ_ONLY_SHARED",
      isFoundation: true,
      workspaceTypes: ENTERPRISE_CONTEXTS,
    }),
    node("user", {
      id: "workspace-context",
      label: "Workspace Context",
      description: "Select an authorized owning Workspace before starting a strategic transaction.",
      phase: 0,
      order: 3,
      view: "workspace-context",
      classification: "READ_ONLY_SHARED",
      isFoundation: true,
      workspaceTypes: ENTERPRISE_CONTEXTS,
    }),
  ],
});

const userCapitalPlanning = node("user", {
  id: "phase-1-strategic-capital-planning-demand",
  label: "Strategic Capital Planning & Demand",
  description: "Capture, review and endorse governed capital needs before any solution or Project is selected.",
  phase: 1,
  order: 1,
  view: "capital-demand-pipeline",
  badge: "Start of capital planning",
  predecessorIds: [userFoundation.id],
  governanceModels: OWNER_MODELS,
  workspaceTypes: ENTERPRISE_CONTEXTS,
  children: [
    node("user", {
      id: "capital-planning-cycles",
      label: "Planning Cycles",
      description: "Open and close governed periods for capital need capture, review and endorsement.",
      phase: 1,
      order: 1,
      view: "capital-planning-cycles",
      predecessorIds: [userFoundation.id],
      governanceModels: OWNER_MODELS,
      workspaceTypes: ENTERPRISE_CONTEXTS,
    }),
    node("user", {
      id: "capital-demand-pipeline",
      label: "Capital Demand Pipeline",
      description: "Review strategic capital needs without treating indicative values as Budget or Funding.",
      phase: 1,
      order: 2,
      view: "capital-demand-pipeline",
      predecessorIds: ["capital-planning-cycles"],
      governanceModels: OWNER_MODELS,
      workspaceTypes: ENTERPRISE_CONTEXTS,
    }),
    node("user", {
      id: "capital-demand-my",
      label: "My Demands",
      description: "Create and maintain the capital needs the current user is authorized to own.",
      phase: 1,
      order: 3,
      view: "capital-demand-my",
      predecessorIds: ["capital-planning-cycles"],
      governanceModels: OWNER_MODELS,
      workspaceTypes: ENTERPRISE_CONTEXTS,
    }),
    node("user", {
      id: "capital-demand-review",
      label: "Demands in Review",
      description: "Review submitted needs with governed separation of duties before endorsement.",
      phase: 1,
      order: 4,
      view: "capital-demand-review",
      predecessorIds: ["capital-demand-pipeline"],
      governanceModels: OWNER_MODELS,
      workspaceTypes: ENTERPRISE_CONTEXTS,
    }),
    node("user", {
      id: "capital-demand-endorsed",
      label: "Endorsed Demands",
      description: "Open recognized capital needs that are eligible for explicit Idea origination.",
      phase: 1,
      order: 5,
      view: "capital-demand-endorsed",
      predecessorIds: ["capital-demand-review"],
      governanceModels: OWNER_MODELS,
      workspaceTypes: ENTERPRISE_CONTEXTS,
    }),
    node("user", {
      id: "capital-demand-history",
      label: "Demand History",
      description: "Inspect historically stable Demand revisions and Idea origin snapshots.",
      phase: 1,
      order: 6,
      view: "capital-demand-history",
      classification: "READ_ONLY_SHARED",
      predecessorIds: ["capital-demand-pipeline"],
      governanceModels: OWNER_MODELS,
      workspaceTypes: ENTERPRISE_CONTEXTS,
    }),
    node("user", {
      id: "strategic-capital-allocation",
      label: "Strategic Capital Allocation",
      description:
        "Set strategic Bucket targets and compare them with Demand, Portfolio, Recommended and Approved positions without approving Budget or Funding.",
      phase: 1,
      order: 7,
      view: "strategic-capital-allocation",
      predecessorIds: ["capital-demand-pipeline"],
      governanceModels: OWNER_MODELS,
      workspaceTypes: ENTERPRISE_CONTEXTS,
    }),
    node("user", {
      id: "strategic-capital-allocation-history",
      label: "Allocation History",
      description: "Read immutable endorsed Allocation Plan snapshots and superseded revisions.",
      phase: 1,
      order: 8,
      view: "strategic-capital-allocation-history",
      classification: "READ_ONLY_SHARED",
      predecessorIds: ["strategic-capital-allocation"],
      governanceModels: OWNER_MODELS,
      workspaceTypes: ENTERPRISE_CONTEXTS,
    }),
  ],
});

const userIdea = node("user", {
  id: "phase-1-idea-demand",
  label: "Investment Origination & Shaping",
  description:
    "Originate or directly capture policy-eligible Ideas, analyze options and develop the governed Project Proposal.",
  phase: 2,
  order: 2,
  view: "idea-lifecycle",
  badge: "Demand → Idea is explicit",
  predecessorIds: [userCapitalPlanning.id],
  workspaceTypes: ENTERPRISE_CONTEXTS,
  children: [
    node("user", {
      id: "idea-lifecycle",
      label: "Idea Lifecycle",
      description: "Create and govern Ideas in a backend-authorized owning Workspace.",
      phase: 2,
      order: 1,
      view: "idea-lifecycle",
      predecessorIds: [userCapitalPlanning.id],
      workspaceTypes: ENTERPRISE_CONTEXTS,
    }),
    node("user", {
      id: "business-analysis-options",
      label: "Business Analysis & Options",
      description: "Define the need, compare alternatives and complete a governed recommendation.",
      phase: 2,
      order: 2,
      view: "business-analysis-options",
      predecessorIds: ["idea-lifecycle"],
      workspaceTypes: ENTERPRISE_CONTEXTS,
    }),
    node("user", {
      id: "project-proposals",
      label: "Project Proposals",
      description: "Develop the governed proposal linked to an accepted Idea.",
      phase: 2,
      order: 3,
      view: "project-proposal",
      predecessorIds: ["business-analysis-options"],
      workspaceTypes: ENTERPRISE_CONTEXTS,
    }),
  ],
});

const userStrategicGate = node("user", {
  id: "phase-3-strategic-gate",
  label: "Strategic Gate",
  description: "Approve, return, reject or defer the Proposal before Portfolio Intake.",
  phase: 3,
  order: 3,
  view: "strategic-gate-decision",
  predecessorIds: [userIdea.id],
  workspaceTypes: ENTERPRISE_CONTEXTS,
  children: [
    node("user", {
      id: "strategic-gate-decision",
      label: "Strategic Gate Decision",
      description: "Record the authorized strategic decision on a governed Project Proposal.",
      phase: 3,
      order: 1,
      view: "strategic-gate-decision",
      predecessorIds: ["project-proposals"],
      workspaceTypes: ENTERPRISE_CONTEXTS,
    }),
  ],
});

const portfolioAnalysisChildren = [
  node("user", {
    id: "portfolio-investor-map",
    label: "Investor Map",
    description: "Compare eligible Projects on the governed investor map.",
    phase: 4,
    order: 1,
    view: "portfolio-investor-map",
    classification: "READ_ONLY_SHARED",
    governanceModels: OWNER_MODELS,
    workspaceTypes: ["PORTFOLIO"],
  }),
  node("user", {
    id: "portfolio-scorecard",
    label: "Portfolio Scorecard",
    description: "Review the accessible analytical scorecard for the same governed dataset.",
    phase: 4,
    order: 2,
    view: "portfolio-scorecard",
    classification: "READ_ONLY_SHARED",
    governanceModels: OWNER_MODELS,
    workspaceTypes: ["PORTFOLIO"],
  }),
];

const userPortfolioPlanning = node("user", {
  id: "phase-4-portfolio-planning",
  label: "Portfolio Planning & Review",
  description:
    "Admit, evaluate, prioritize and analyze Projects, then govern the Portfolio through recurring review sessions.",
  phase: 4,
  order: 4,
  view: "strategic-project-planning-entry",
  predecessorIds: [userStrategicGate.id],
  governanceModels: OWNER_MODELS,
  workspaceTypes: ["PORTFOLIO"],
  children: [
    node("user", {
      id: "portfolio-intake-planning",
      label: "Portfolio Intake & Planning",
      description: "Bridge an approved Strategic Gate decision into Portfolio planning and governed Project creation.",
      phase: 4,
      order: 1,
      view: "strategic-project-planning-entry",
      predecessorIds: ["strategic-gate-decision"],
      governanceModels: OWNER_MODELS,
      workspaceTypes: ["PORTFOLIO"],
      children: detailNodes(
        "user",
        4,
        "portfolio-intake",
        [
          ["portfolio-structure", "Portfolio Structure"],
          ["strategic-project-planning-entry", "Strategic Planning Entry"],
          ["portfolio-projects", "Portfolio Projects"],
        ],
        OWNER_MODELS,
        ["PORTFOLIO"]
      ),
    }),
    node("user", {
      id: "portfolio-evaluation-prioritization",
      label: "Evaluation & Prioritization",
      description: "Evaluate eligible Projects and maintain the governed prioritization view.",
      phase: 4,
      order: 2,
      view: "portfolio-evaluation",
      predecessorIds: ["portfolio-intake-planning"],
      governanceModels: OWNER_MODELS,
      workspaceTypes: ["PORTFOLIO"],
      children: detailNodes(
        "user",
        4,
        "portfolio-evaluation",
        [
          ["portfolio-evaluation", "Portfolio Evaluation"],
          ["strategic-prioritization-matrix", "Prioritization Matrix", "READ_ONLY_SHARED"],
        ],
        OWNER_MODELS,
        ["PORTFOLIO"]
      ),
    }),
    node("user", {
      id: "portfolio-analysis",
      label: "Portfolio Analysis",
      description: "Analyze the governed Project set before scenario planning begins.",
      phase: 4,
      order: 3,
      view: "portfolio-analysis",
      classification: "READ_ONLY_SHARED",
      predecessorIds: ["portfolio-evaluation-prioritization"],
      governanceModels: OWNER_MODELS,
      workspaceTypes: ["PORTFOLIO"],
      children: [
        node("user", {
          id: "portfolio-analysis-overview",
          label: "Analysis Overview",
          description: "Review Portfolio Analysis readiness and dataset lineage.",
          phase: 4,
          order: 1,
          view: "portfolio-analysis",
          classification: "READ_ONLY_SHARED",
          governanceModels: OWNER_MODELS,
          workspaceTypes: ["PORTFOLIO"],
        }),
        ...portfolioAnalysisChildren,
      ],
    }),
    node("user", {
      id: "periodic-portfolio-review",
      label: "Periodic Portfolio Review",
      description:
        "Run recurring Portfolio-level governance sessions from frozen source evidence without replacing Project Gates or source-authority decisions.",
      phase: 4,
      order: 4,
      view: "portfolio-review-sessions",
      predecessorIds: ["scenario-convergence-recommendation"],
      governanceModels: OWNER_MODELS,
      workspaceTypes: ["PORTFOLIO"],
      longitudinal: true,
      children: detailNodes(
        "user",
        4,
        "portfolio-review",
        [
          ["portfolio-review-sessions", "Review Calendar / Sessions"],
          ["portfolio-review-overview", "Overview"],
          ["portfolio-review-snapshot", "Portfolio Snapshot"],
          ["portfolio-review-allocation", "Strategic Allocation", "READ_ONLY_SHARED"],
          ["portfolio-review-project-matrix", "Project Matrix", "READ_ONLY_SHARED"],
          ["portfolio-review-budget-resources", "Budget & Resources", "READ_ONLY_SHARED"],
          ["portfolio-review-gate-fid", "Gate / FID Status", "READ_ONLY_SHARED"],
          ["portfolio-review-exceptions", "Exceptions", "READ_ONLY_SHARED"],
          ["portfolio-review-conclusions", "Conclusions"],
          ["portfolio-review-actions", "Actions"],
          ["portfolio-review-history", "History", "READ_ONLY_SHARED"],
          ["portfolio-review-trends", "Trends", "READ_ONLY_SHARED"],
        ],
        OWNER_MODELS,
        ["PORTFOLIO"]
      ),
    }),
  ],
});

const userScenarioPlanning = node("user", {
  id: "phase-5-portfolio-scenario-planning",
  label: "Portfolio Scenario Planning",
  description: "Test Budget and Resource alternatives and converge them into a Portfolio Recommendation.",
  phase: 5,
  order: 5,
  view: "portfolio-scenario-convergence",
  predecessorIds: [userPortfolioPlanning.id],
  governanceModels: OWNER_MODELS,
  workspaceTypes: ["PORTFOLIO"],
  children: [
    node("user", {
      id: "budget-planning-scenarios",
      label: "Budget Planning & Scenarios",
      description: "Evaluate governed budget envelopes and scenario alternatives.",
      phase: 5,
      order: 1,
      view: "portfolio-budget-planning",
      predecessorIds: ["portfolio-analysis"],
      parallelGroup: "portfolio-scenario-inputs",
      convergesInto: "scenario-convergence-recommendation",
      governanceModels: OWNER_MODELS,
      workspaceTypes: ["PORTFOLIO"],
      children: detailNodes(
        "user",
        5,
        "portfolio-budget",
        [
          ["portfolio-budget-planning", "Budget Planning Workspace"],
          ["portfolio-cash-flow", "Portfolio Cash Flow", "READ_ONLY_SHARED"],
        ],
        OWNER_MODELS,
        ["PORTFOLIO"]
      ),
    }),
    node("user", {
      id: "resource-planning-scenarios",
      label: "Resource Planning & Scenarios",
      description: "Evaluate governed resource capacity and scenario alternatives in parallel with Budget planning.",
      phase: 5,
      order: 2,
      view: "portfolio-resource-planning",
      predecessorIds: ["portfolio-analysis"],
      parallelGroup: "portfolio-scenario-inputs",
      convergesInto: "scenario-convergence-recommendation",
      governanceModels: OWNER_MODELS,
      workspaceTypes: ["PORTFOLIO"],
    }),
    node("user", {
      id: "scenario-convergence-recommendation",
      label: "Scenario Convergence & Recommendation",
      description: "Converge Budget and Resource evidence into the governed Portfolio Recommendation.",
      phase: 5,
      order: 3,
      view: "portfolio-scenario-convergence",
      predecessorIds: ["budget-planning-scenarios", "resource-planning-scenarios"],
      governanceModels: OWNER_MODELS,
      workspaceTypes: ["PORTFOLIO"],
    }),
  ],
});

const businessCaseDetails = detailNodes("user", 6, "business-case", [
  ["business-case-overview", "Overview"],
  ["business-case-strategic", "Strategic Case"],
  ["business-case-economic", "Economic Case"],
  ["business-case-commercial", "Commercial Case"],
  ["business-case-financial", "Financial Case"],
  ["business-case-management", "Management Case"],
  ["business-case-sources-evidence", "Sources & Evidence"],
  ["business-case-readiness", "Readiness"],
  ["business-case-decision-snapshots", "Decision Snapshots"],
  ["business-case-history", "History"],
]);

const strategicBenefitsDetails = detailNodes("user", 6, "strategic-benefits", [
  ["strategic-benefits-my", "My Plans"],
  ["strategic-benefits-overview", "Overview"],
  ["strategic-benefits-strategic-alignment", "Strategic Alignment"],
  ["strategic-benefits-outputs", "Outputs"],
  ["strategic-benefits-outcomes", "Outcomes"],
  ["strategic-benefits-register", "Benefits Register"],
  ["strategic-benefits-measures", "Measures / KPIs"],
  ["strategic-benefits-owners", "Benefit Owners"],
  ["strategic-benefits-baselines-targets", "Baselines & Targets"],
  ["strategic-benefits-expected-value", "Expected Value"],
  ["strategic-benefits-dependencies", "Dependencies"],
  ["strategic-benefits-assumptions-constraints", "Assumptions / Constraints"],
  ["strategic-benefits-risk-references", "Risk References"],
  ["strategic-benefits-traceability", "Traceability"],
  ["strategic-benefits-readiness", "Readiness"],
  ["strategic-benefits-history", "History"],
]);

const commercialStrategyDetails = detailNodes("user", 6, "commercial-strategy", [
  ["commercial-strategy-my", "My Strategies"],
  ["commercial-strategy-overview", "Overview"],
  ["commercial-strategy-context", "Commercial Context"],
  ["commercial-strategy-procurement", "Procurement Approach"],
  ["commercial-strategy-packages", "Packages"],
  ["commercial-strategy-contracting-model", "Contracting Model"],
  ["commercial-strategy-market", "Market Assessment"],
  ["commercial-strategy-supply-chain", "Supply Chain"],
  ["commercial-strategy-risk-allocation", "Risk Allocation"],
  ["commercial-strategy-payment-incentives", "Payment & Incentives"],
  ["commercial-strategy-assumptions", "Assumptions / Constraints"],
  ["commercial-strategy-recommendation", "Recommendation"],
  ["commercial-strategy-readiness", "Readiness"],
  ["commercial-strategy-history", "History"],
]);

const financialModelDetails = detailNodes("user", 6, "financial-model", [
  ["financial-model-my-models", "My Models"],
  ["financial-model-overview", "Overview"],
  ["financial-model-current-version", "Current Version"],
  ["financial-model-assumptions", "Assumptions"],
  ["financial-model-economic-case", "Economic Case"],
  ["financial-model-financial-case", "Financial Case"],
  ["financial-model-capex-opex", "CAPEX / OPEX"],
  ["financial-model-revenue-benefits", "Revenue / Benefits"],
  ["financial-model-capital-structure", "Capital Structure"],
  ["financial-model-funding-linkage", "Funding Linkage"],
  ["financial-model-investors", "Investors"],
  ["financial-model-debt", "Debt"],
  ["financial-model-cash-flow", "Cash Flow"],
  ["financial-model-debt-service", "Debt Service"],
  ["financial-model-indicators", "Indicators"],
  ["financial-model-covenants", "Covenants"],
  ["financial-model-scenarios", "Scenarios"],
  ["financial-model-sensitivities", "Sensitivities"],
  ["financial-model-break-even", "Break-Even"],
  ["financial-model-readiness", "Readiness"],
  ["financial-model-source-lineage", "Source Lineage"],
  ["financial-model-compare-versions", "Compare Versions"],
  ["financial-model-history-audit", "History / Audit"],
]);

const fundsDetails = detailNodes("user", 6, "funds", [
  ["funds-overview", "Overview"],
  ["funds-sources", "Funding Sources"],
  ["funds-envelopes", "Funds"],
  ["funds-assignments", "Funding Assignments"],
  ["funds-coverage", "Funding Coverage"],
  ["funds-readiness", "Funding Readiness"],
  ["funds-history", "History / Audit"],
]);

const riskDetails = detailNodes("user", 6, "risk", [
  ["risk-readiness-my", "My Risk Work"],
  ["risk-readiness-portfolio", "Project Set Risk Readiness"],
  ["risk-readiness-register", "Project Risk Register"],
  ["risk-readiness-assessments", "Risk Assessments"],
  ["risk-readiness-treatments", "Treatments"],
  ["risk-readiness-residual", "Residual Risk & Acceptance"],
  ["risk-readiness-dashboard", "Risk Readiness Dashboard"],
  ["risk-readiness-history", "History / Audit"],
]);

const permitDetails = detailNodes("user", 6, "permit", [
  ["permit-readiness-my", "My Permit Work"],
  ["permit-readiness-register", "Project Permit Register"],
  ["permit-readiness-requirements", "Permit Requirements"],
  ["permit-readiness-conditions", "Permit Conditions"],
  ["permit-readiness-project", "Project Permit Readiness"],
  ["permit-readiness-portfolio", "Project Set Permit Readiness"],
  ["permit-readiness-history", "Permit History / Audit"],
]);

const evidenceContributor = (
  id: string,
  label: string,
  view: ControlFlowView,
  order: number,
  children: StrategicNavigationNode[] = []
) =>
  node("user", {
    id,
    label,
    description: `${label} contributes governed evidence to Investment Gate Preparation.`,
    phase: 6,
    order,
    view,
    predecessorIds: [userScenarioPlanning.id],
    convergesInto: "investment-gate-preparation",
    governanceModels: OWNER_MODELS,
    workspaceTypes: PROJECT_CONTEXTS,
    children,
    longitudinal: id === "business-case-manager",
  });

const userDefinition = node("user", {
  id: "phase-6-project-definition-investment-case",
  label: "Business Case & Investment Development",
  description: "Develop Project maturity and investment evidence required for decision making.",
  phase: 6,
  order: 6,
  view: "project-definition-fel",
  predecessorIds: [userScenarioPlanning.id],
  governanceModels: OWNER_MODELS,
  workspaceTypes: PROJECT_CONTEXTS,
  children: [
    evidenceContributor("project-definition-fel", "Project Definition / FEL", "project-definition-fel", 1),
    evidenceContributor("business-case-manager", "Business Case Manager", "business-case-my", 2, businessCaseDetails),
    evidenceContributor(
      "strategic-benefits-plan",
      "Strategic Benefits Plan & Traceability",
      "strategic-benefits-my",
      3,
      strategicBenefitsDetails
    ),
    evidenceContributor(
      "commercial-contracting-strategy",
      "Commercial & Contracting Strategy",
      "commercial-strategy-my",
      4,
      commercialStrategyDetails
    ),
    evidenceContributor("funds-funding-readiness", "Funds & Funding Readiness", "funds-overview", 5, fundsDetails),
    evidenceContributor(
      "economic-financial-model",
      "Economic & Financial Model",
      "financial-model-my-models",
      6,
      financialModelDetails
    ),
    evidenceContributor("risk-readiness", "Risk Readiness", "risk-readiness-my", 7, riskDetails),
    evidenceContributor("permit-readiness", "Permit Readiness", "permit-readiness-my", 8, permitDetails),
    evidenceContributor("basic-data-readiness", "Basic Data Readiness", "basic-data-readiness", 9),
    evidenceContributor("owner-capability-readiness", "Owner Capability Readiness", "owner-capability-readiness", 10),
    evidenceContributor("qra-foundation", "QRA", "qra-foundation", 11, [
      node("user", {
        id: "qra-cost-source-readiness",
        label: "Cost Source Readiness",
        description: "Review governed cost source evidence without changing Budget, FIN or Cost Control.",
        phase: 6,
        order: 1,
        view: "qra-foundation",
        governanceModels: OWNER_MODELS,
        workspaceTypes: PROJECT_CONTEXTS,
      }),
      ...detailNodes("user", 6, "qra-foundation", [
        ["qra-schedule-source-readiness", "Schedule Source Readiness"],
        ["qra-model-definition", "Model Definition"],
        ["qra-foundation-history", "Foundation History"],
        ["qra-approved-models", "Approved Models"],
        ["qra-runs", "Runs"],
        ["qra-run-overview", "Run Overview"],
        ["qra-cost-results", "Cost Results"],
        ["qra-schedule-results", "Schedule Results"],
        ["qra-percentiles", "Percentiles"],
        ["qra-sensitivity", "Sensitivity / Drivers"],
        ["qra-convergence", "Convergence"],
        ["qra-run-evidence", "Evidence / Traceability"],
        ["qra-run-comparison", "Run Comparison"],
        ["qra-run-history", "Run History"],
      ]).map((item, index) => ({ ...item, order: index + 2 })),
    ]),
  ],
});

const investmentDecisionDetails = detailNodes("user", 7, "investment-decision", [
  ["investment-decision-queue", "Decision Queue"],
  ["investment-decision-mine", "My Decisions"],
  ["investment-decision-package", "Investment Decision Package"],
  ["investment-decision-evidence", "Evidence Summary"],
  ["investment-decision-checklist", "Decision Checklist"],
  ["investment-decision-conditions", "Conditions"],
  ["investment-decision-committee", "Committee / Votes"],
  ["investment-decision-history", "Decision History"],
  ["investment-decision-output", "Authorization Output"],
]);

const postFidDetails = detailNodes("user", 7, "post-fid", [
  ["post-fid-queue", "Post-FID Queue"],
  ["post-fid-handoff", "FID Handoff"],
  ["post-fid-eligibility-matrix", "Project Eligibility Matrix"],
  ["post-fid-conditions", "Post-FID Conditions"],
  ["post-fid-initialization-handoff", "Initialization Handoff"],
  ["post-fid-activation-handoff", "Activation Handoff"],
  ["post-fid-history", "Post-FID History / Audit"],
]);

const userInvestmentGovernance = node("user", {
  id: "phase-7-investment-governance",
  label: "Investment Governance",
  description: "Prepare the evidence package, make the investment decision and manage the post-FID governance handoff.",
  phase: 7,
  order: 7,
  view: "investment-gate-preparation",
  predecessorIds: [userDefinition.id],
  governanceModels: OWNER_MODELS,
  workspaceTypes: PROJECT_CONTEXTS,
  children: [
    node("user", {
      id: "investment-gate-preparation",
      label: "Investment Gate Preparation",
      description: "Converge the governed evidence required for the investment decision.",
      phase: 7,
      order: 1,
      view: "investment-gate-preparation",
      predecessorIds: userDefinition.children.map((item) => item.id),
      governanceModels: OWNER_MODELS,
      workspaceTypes: PROJECT_CONTEXTS,
    }),
    node("user", {
      id: "investment-decision-fid",
      label: "Investment Decision / FID",
      description: "Record the governed investment decision without implying Project Activation.",
      phase: 7,
      order: 2,
      view: "investment-decision-queue",
      predecessorIds: ["investment-gate-preparation"],
      governanceModels: OWNER_MODELS,
      workspaceTypes: PROJECT_CONTEXTS,
      children: investmentDecisionDetails,
    }),
    node("user", {
      id: "post-fid-project-governance",
      label: "Post-FID Project Governance",
      description: "Govern the downstream handoff after FID without performing Project Activation.",
      phase: 7,
      order: 3,
      view: "post-fid-queue",
      predecessorIds: ["investment-decision-fid"],
      governanceModels: OWNER_MODELS,
      workspaceTypes: PROJECT_CONTEXTS,
      children: postFidDetails,
    }),
  ],
});

function adminPhase(
  phase: number,
  id: string,
  label: string,
  description: string,
  items: Array<[ControlFlowView, string, string?, StrategicControlClassification?, string?]>,
  options: { badge?: string; predecessorIds?: string[]; isFoundation?: boolean } = {}
) {
  return node("admin", {
    id,
    label,
    description,
    phase,
    order: phase,
    view: items[0][0],
    badge: options.badge,
    isFoundation: options.isFoundation,
    predecessorIds: options.predecessorIds,
    children: items.map(([view, itemLabel, itemDescription, classification, itemId], index) =>
      node("admin", {
        id: itemId ?? `admin-${view}`,
        label: itemLabel,
        description: itemDescription ?? `Configure the governed ${itemLabel} capability.`,
        phase,
        order: index + 1,
        view,
        classification,
        isFoundation: phase === 0,
      })
    ),
  });
}

const adminPhases: StrategicNavigationNode[] = [
  adminPhase(
    0,
    "admin-phase-0-enterprise-foundation",
    "Enterprise Foundation",
    "Configure and publish the enterprise context required before strategic transactions begin.",
    [
      [
        "enterprise-strategy-overview",
        "Foundation Configuration / Preview",
        "Read the effective Foundation status before opening an ADMIN configuration surface.",
        "READ_ONLY_SHARED",
      ],
      ["enterprise-structure-configuration", "Enterprise Structure & Workspace Manager"],
      ["workspace-types", "Workspace Types"],
      ["enterprise-workspace-structure", "Composition Rules"],
      ["foundation-strategic-objectives", "Strategic Objectives"],
      ["workspace-defaults", "Workspace Defaults & Inheritance"],
      ["module-catalog-activation", "Module Catalog & Activation"],
      ["workspace-navigation-profiles", "Workspace Navigation Profiles"],
      [
        "risk-governance-configuration",
        "Risk Governance",
        "Configure enterprise Risk Capacity, Appetite and Thresholds without Risk Register transactions, QRA or Gate decisions.",
      ],
    ],
    { badge: "Foundation / prerequisite", isFoundation: true }
  ),
  adminPhase(
    1,
    "admin-phase-1-capital-planning-demand",
    "Strategic Capital Planning & Demand Configuration",
    "Govern reusable Themes, Strategic Capital Buckets and policy consumed by Capital Planning without creating live transactions.",
    [
      ["capital-planning-configuration", "Strategic Capital Planning & Demand Configuration"],
      [
        "strategic-capital-bucket-configuration",
        "Strategic Capital Buckets",
        "Configure, preview, publish and archive the reusable Bucket catalog and strategic allocation policy.",
        undefined,
        "admin-strategic-capital-bucket-configuration",
      ],
    ],
    { badge: "Start of capital planning", predecessorIds: ["admin-phase-0-enterprise-foundation"] }
  ),
  adminPhase(
    2,
    "admin-phase-2-investment-origination-shaping",
    "Investment Origination & Shaping Configuration",
    "Govern Idea, Business Analysis and Project Proposal configuration after Capital Planning.",
    [
      ["idea-demand-configuration", "Idea & Demand Configuration"],
      ["business-analysis-configuration", "Business Analysis Configuration"],
      ["project-proposal-configuration", "Project Proposal Configuration"],
    ],
    { badge: "Demand → Idea is explicit", predecessorIds: ["admin-phase-1-capital-planning-demand"] }
  ),
  adminPhase(
    3,
    "admin-phase-3-strategic-gate",
    "Strategic Gate Decision Configuration",
    "Govern the decision configuration used before Portfolio Intake.",
    [["strategic-gate-configuration", "Strategic Gate Decision Configuration"]],
    { predecessorIds: ["admin-phase-2-investment-origination-shaping"] }
  ),
  adminPhase(
    4,
    "admin-phase-4-portfolio-planning",
    "Portfolio Planning & Review Configuration",
    "Govern Portfolio Intake, Evaluation, Prioritization, Analysis and recurring Portfolio Review policy in business order.",
    [
      ["portfolio-planning-configuration", "Portfolio Intake"],
      ["portfolio-evaluation-configuration", "Evaluation & Prioritization"],
      ["portfolio-analysis-configuration", "Portfolio Analysis"],
      [
        "portfolio-review-configuration",
        "Periodic Portfolio Review",
        "Configure cadence, evidence requirements, conclusions, actions, thresholds, authority and separation of duties without creating live Review Sessions.",
        undefined,
        "admin-portfolio-review-configuration",
      ],
    ],
    { predecessorIds: ["admin-phase-3-strategic-gate"] }
  ),
  adminPhase(
    5,
    "admin-phase-5-portfolio-scenario-planning",
    "Portfolio Scenario Planning Configuration",
    "Govern the parallel Budget and Resource branches and their convergence.",
    [
      ["portfolio-budget-planning-configuration", "Budget Planning"],
      ["portfolio-resource-planning-configuration", "Resource Planning"],
      ["portfolio-scenario-convergence-configuration", "Scenario Convergence"],
    ],
    { predecessorIds: ["admin-phase-4-portfolio-planning"] }
  ),
  adminPhase(
    6,
    "admin-phase-6-project-definition-investment-case",
    "Project Definition & Investment Case",
    "Govern the parallel evidence contributors required for investment decision making.",
    [
      ["project-definition-configuration", "Project Definition / FEL"],
      ["business-case-configuration", "Business Case Manager"],
      ["benefits-configuration", "Benefits Configuration"],
      ["commercial-strategy-configuration", "Commercial Strategy Configuration"],
      ["funds-manager-configuration", "Funds & Funding Readiness"],
      ["financial-model-configuration", "Economic & Financial Model"],
      ["risk-readiness-configuration", "Risk Readiness"],
      ["permit-readiness-configuration", "Permit Readiness"],
      [
        "basic-data-configuration",
        "Basic Data Readiness Configuration",
        "Configure technical input categories, stage-aware requirements, quality, confidence, freshness, coverage and SoD without live assessments.",
      ],
      [
        "owner-capability-configuration",
        "Owner Capability Readiness Configuration",
        "Configure Owner organizational capability frameworks, maturity, evidence quality, stage-aware tailoring, mitigation acceptance, freshness and independent review without live assessments.",
      ],
      [
        "qra-methodology-source-readiness",
        "QRA Methodology & Source Readiness",
        "Configure methodology, source requirements, uncertainty inputs, distributions, correlations, SoD and validity without approving live models or executing simulation.",
      ],
    ],
    { predecessorIds: ["admin-phase-5-portfolio-scenario-planning"] }
  ),
  adminPhase(
    7,
    "admin-phase-7-investment-governance",
    "Investment Governance",
    "Govern evidence policy, Gate preparation, FID and the post-FID handoff in decision order.",
    [
      ["investment-decision-evidence-policy", "Evidence & Decision Policy"],
      ["investment-gate-preparation-configuration", "Investment Gate Preparation"],
      ["investment-decision-configuration", "Investment Decision / FID"],
      ["post-fid-governance-configuration", "Post-FID Project Governance"],
    ],
    { predecessorIds: ["admin-phase-6-project-definition-investment-case"] }
  ),
];

export const strategicNavigationBlueprint: StrategicNavigationNode[] = [
  userFoundation,
  userCapitalPlanning,
  userIdea,
  userStrategicGate,
  userPortfolioPlanning,
  userScenarioPlanning,
  userDefinition,
  userInvestmentGovernance,
  ...adminPhases,
];

function toNavigationView(item: StrategicNavigationNode): NavigationViewItem {
  return {
    key: item.view,
    label: item.label,
    classification: item.classification,
    description: item.description,
    route: item.route,
    phase: item.phase,
    isFoundation: item.isFoundation,
    badge: item.badge,
    children: item.children.map(toNavigationView),
  };
}

export function buildStrategicMacroprocess(mode: ApplicationMode): MacroprocessNavigationItem {
  const modules: ModuleNavigationItem[] = strategicNavigationBlueprint
    .filter((item) => item.mode === mode)
    .sort((first, second) => first.order - second.order)
    .map((item) => ({
      key: item.id,
      label: item.label,
      classification: item.classification,
      description: item.description,
      phase: item.phase,
      badge: item.badge,
      isFoundation: item.isFoundation,
      submodules: item.children.map(toNavigationView),
    }));
  return {
    key: "enterprise-strategy-manager",
    label: "Enterprise Strategy Manager",
    classification: "READ_ONLY_SHARED",
    description: "Enterprise Foundation and the governed strategic investment workflow.",
    modules,
  };
}

function walk(
  nodes: StrategicNavigationNode[],
  trail: StrategicNavigationNode[] = []
): Array<{
  node: StrategicNavigationNode;
  trail: StrategicNavigationNode[];
}> {
  return nodes.flatMap((item) => [{ node: item, trail: [...trail, item] }, ...walk(item.children, [...trail, item])]);
}

export function strategicNodeForView(view: ControlFlowView, mode: ApplicationMode) {
  return walk(strategicNavigationBlueprint.filter((item) => item.mode === mode)).find(
    ({ node: item }) =>
      item.view === view && (!item.children.length || item.children.every((child) => child.view !== view))
  );
}

export function strategicBreadcrumb(view: ControlFlowView, mode: ApplicationMode) {
  const match = strategicNodeForView(view, mode);
  if (!match) return [];
  return ["Enterprise Strategy Manager", ...match.trail.map((item) => item.label)];
}

export function strategicRouteForView(view: ControlFlowView, mode: ApplicationMode) {
  return strategicNodeForView(view, mode)?.node.route ?? null;
}

export function strategicRouteRegistry() {
  const routes = new Map<string, { mode: ApplicationMode; view: ControlFlowView }>();
  for (const { node: item } of walk(strategicNavigationBlueprint)) {
    const canonical = strategicNodeForView(item.view, item.mode)?.node;
    if (canonical !== item) continue;
    routes.set(item.route, { mode: item.mode, view: item.view });
  }
  return routes;
}

export function strategicRouteMatch(pathname: string): { mode: ApplicationMode; view: ControlFlowView } | null {
  const normalized = pathname.replace(/\/+$/, "");
  return strategicRouteRegistry().get(normalized) ?? null;
}

export function canAccessStrategicNode(
  item: StrategicNavigationNode,
  access: { authenticated: boolean; canConfigure: boolean }
) {
  return item.permission === "can_configure" ? access.canConfigure : access.authenticated;
}

export function strategicNodeApplies(
  item: StrategicNavigationNode,
  context: { governanceModel?: StrategicGovernanceModel; workspaceType?: string }
) {
  const governanceApplies = !context.governanceModel || item.governanceModels.includes(context.governanceModel);
  const workspaceApplies = !context.workspaceType || item.workspaceTypes.includes(context.workspaceType.toUpperCase());
  return governanceApplies && workspaceApplies;
}

const ENTERPRISE_WORKSPACE_ORDER = [
  "home",
  "ideas",
  "business-analyses",
  "project-proposals",
  "strategic-gate-decisions",
  "portfolio-projects",
  "portfolio-evaluation",
  "prioritization-matrix",
  "portfolio-analysis",
  "portfolio-budget-planning",
  "portfolio-resource-planning",
  "portfolio-scenario-convergence",
  "portfolio-reviews",
];

const PROJECT_WORKSPACE_ORDER = [
  "home",
  "strategic-context",
  "project-definition-readiness",
  "business-case",
  "funding",
  "economic-financial-model",
  "risk",
  "permits",
  "investment-gate-preparation",
  "investment-decision",
  "post-fid-governance",
];

export function orderStrategicWorkspaceNavigator<T extends { code: string }>(items: T[], workspaceType: string) {
  const preferred = workspaceType.toUpperCase() === "PROJECT" ? PROJECT_WORKSPACE_ORDER : ENTERPRISE_WORKSPACE_ORDER;
  const index = new Map(preferred.map((code, order) => [code, order]));
  return [...items].sort((first, second) => {
    const firstOrder = index.get(first.code) ?? Number.MAX_SAFE_INTEGER;
    const secondOrder = index.get(second.code) ?? Number.MAX_SAFE_INTEGER;
    return firstOrder - secondOrder;
  });
}
