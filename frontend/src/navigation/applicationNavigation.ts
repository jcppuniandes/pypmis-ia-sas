import { buildStrategicMacroprocess } from "../features/enterprise-strategy/navigation/strategicNavigationBlueprint";
import type { StrategicControlClassification } from "../features/enterprise-strategy/navigation/strategicControlClassification";

export const SCOPE_MANAGER_MODULE_LABEL = "Scope Manager";
export const BIM_MANAGER_SUBMODULE_LABEL = "BIM Manager";

export type ControlFlowView =
  | "dashboard"
  | "opc-gap"
  | "enterprise-strategy-overview"
  | "workspace-context"
  | "foundation-strategic-objectives"
  | "risk-governance-configuration"
  | "basic-data-readiness"
  | "basic-data-configuration"
  | "owner-capability-readiness"
  | "owner-capability-configuration"
  | "qra-foundation"
  | "qra-schedule-source-readiness"
  | "qra-model-definition"
  | "qra-foundation-history"
  | "qra-methodology-source-readiness"
  | "capital-planning-cycles"
  | "capital-demand-pipeline"
  | "capital-demand-my"
  | "capital-demand-review"
  | "capital-demand-endorsed"
  | "capital-demand-history"
  | "strategic-capital-allocation"
  | "strategic-capital-allocation-history"
  | "capital-planning-configuration"
  | "strategic-capital-bucket-configuration"
  | "idea-lifecycle"
  | "idea-demand-configuration"
  | "business-analysis-options"
  | "business-analysis-configuration"
  | "project-proposal"
  | "project-proposal-configuration"
  | "strategic-gate-decision"
  | "strategic-gate-configuration"
  | "strategic-project-planning-entry"
  | "portfolio-projects"
  | "portfolio-planning-configuration"
  | "portfolio-evaluation"
  | "portfolio-evaluation-configuration"
  | "portfolio-analysis"
  | "portfolio-investor-map"
  | "portfolio-scorecard"
  | "portfolio-analysis-configuration"
  | "portfolio-review-sessions"
  | "portfolio-review-overview"
  | "portfolio-review-snapshot"
  | "portfolio-review-allocation"
  | "portfolio-review-project-matrix"
  | "portfolio-review-budget-resources"
  | "portfolio-review-gate-fid"
  | "portfolio-review-exceptions"
  | "portfolio-review-conclusions"
  | "portfolio-review-actions"
  | "portfolio-review-history"
  | "portfolio-review-trends"
  | "portfolio-review-configuration"
  | "portfolio-budget-planning-configuration"
  | "portfolio-resource-planning-configuration"
  | "portfolio-scenario-convergence-configuration"
  | "investment-gate-preparation-configuration"
  | "investment-decision-evidence-policy"
  | "project-definition-configuration"
  | "portfolio-structure"
  | "project-intake-from-ideas"
  | "portfolio-budget-planning"
  | "portfolio-resource-planning"
  | "portfolio-scenario-convergence"
  | "investment-gate-preparation"
  | "investment-decision-queue"
  | "investment-decision-mine"
  | "investment-decision-package"
  | "investment-decision-evidence"
  | "investment-decision-checklist"
  | "investment-decision-conditions"
  | "investment-decision-committee"
  | "investment-decision-history"
  | "investment-decision-output"
  | "investment-decision-configuration"
  | "post-fid-queue"
  | "post-fid-handoff"
  | "post-fid-eligibility-matrix"
  | "post-fid-conditions"
  | "post-fid-initialization-handoff"
  | "post-fid-activation-handoff"
  | "post-fid-history"
  | "post-fid-governance-configuration"
  | "business-case-my"
  | "business-case-overview"
  | "business-case-economic"
  | "business-case-commercial"
  | "business-case-management"
  | "business-case-sources-evidence"
  | "business-case-current-revision"
  | "business-case-strategic"
  | "business-case-alternatives"
  | "business-case-benefits"
  | "business-case-project-definition"
  | "business-case-financial"
  | "business-case-budget-resources"
  | "business-case-funding"
  | "business-case-risk-permits"
  | "business-case-execution"
  | "business-case-assumptions"
  | "business-case-recommendation"
  | "business-case-readiness"
  | "business-case-material-changes"
  | "business-case-decision-snapshots"
  | "business-case-history"
  | "business-case-configuration"
  | "strategic-benefits-my"
  | "strategic-benefits-overview"
  | "strategic-benefits-strategic-alignment"
  | "strategic-benefits-outputs"
  | "strategic-benefits-outcomes"
  | "strategic-benefits-register"
  | "strategic-benefits-measures"
  | "strategic-benefits-owners"
  | "strategic-benefits-baselines-targets"
  | "strategic-benefits-expected-value"
  | "strategic-benefits-dependencies"
  | "strategic-benefits-assumptions-constraints"
  | "strategic-benefits-risk-references"
  | "strategic-benefits-traceability"
  | "strategic-benefits-readiness"
  | "strategic-benefits-history"
  | "benefits-configuration"
  | "commercial-strategy-my"
  | "commercial-strategy-overview"
  | "commercial-strategy-context"
  | "commercial-strategy-procurement"
  | "commercial-strategy-packages"
  | "commercial-strategy-contracting-model"
  | "commercial-strategy-market"
  | "commercial-strategy-supply-chain"
  | "commercial-strategy-risk-allocation"
  | "commercial-strategy-payment-incentives"
  | "commercial-strategy-assumptions"
  | "commercial-strategy-recommendation"
  | "commercial-strategy-readiness"
  | "commercial-strategy-history"
  | "commercial-strategy-configuration"
  | "financial-model-my-models"
  | "financial-model-overview"
  | "financial-model-current-version"
  | "financial-model-assumptions"
  | "financial-model-economic-case"
  | "financial-model-financial-case"
  | "financial-model-capex-opex"
  | "financial-model-revenue-benefits"
  | "financial-model-capital-structure"
  | "financial-model-funding-linkage"
  | "financial-model-investors"
  | "financial-model-debt"
  | "financial-model-cash-flow"
  | "financial-model-debt-service"
  | "financial-model-indicators"
  | "financial-model-covenants"
  | "financial-model-scenarios"
  | "financial-model-sensitivities"
  | "financial-model-break-even"
  | "financial-model-readiness"
  | "financial-model-source-lineage"
  | "financial-model-compare-versions"
  | "financial-model-history-audit"
  | "financial-model-configuration"
  | "project-definition-fel"
  | "funds-overview"
  | "funds-envelopes"
  | "funds-coverage"
  | "funds-readiness"
  | "funds-history"
  | "funds-manager-configuration"
  | "risk-readiness-my"
  | "risk-readiness-portfolio"
  | "risk-readiness-register"
  | "risk-readiness-assessments"
  | "risk-readiness-treatments"
  | "risk-readiness-residual"
  | "risk-readiness-dashboard"
  | "risk-readiness-history"
  | "risk-readiness-configuration"
  | "permit-readiness-my"
  | "permit-readiness-register"
  | "permit-readiness-requirements"
  | "permit-readiness-conditions"
  | "permit-readiness-project"
  | "permit-readiness-portfolio"
  | "permit-readiness-history"
  | "permit-readiness-configuration"
  | "portfolio-cash-flow"
  | "strategic-prioritization-matrix"
  | "project-creator"
  | "process-flow"
  | "setup"
  | "join-venture"
  | "vendors-list"
  | "sales-contracts"
  | "sc-changes"
  | "sc-payments"
  | "commitment-purchase-order"
  | "commitment-po-changes"
  | "commitment-po-payments"
  | "funds-sources"
  | "funds-assignments"
  | "scope-items"
  | "plan-items"
  | "schedule-intake"
  | "schedule-control"
  | "schedule-4d"
  | "schedule-changes"
  | "quantity-takeoff"
  | "bim-budget"
  | "estimates"
  | "cash-flow"
  | "budget-changes"
  | "budget-transfer"
  | "apu-catalog"
  | "claims-audit"
  | "window-analysis-37"
  | "risk-register"
  | "risk-evaluation-matrix"
  | "risk-quantification-analysis"
  | "contingency-quantification"
  | "request-for-bid"
  | "contracts"
  | "contracts-changes"
  | "contract-payments"
  | "purchase-order"
  | "po-changes"
  | "po-payments"
  | "earned-value-analysis"
  | "strategic-investment-map"
  | "gate-decision"
  | "meeting-minutes"
  | "communications"
  | "issues"
  | "lessons-learned"
  | "punch-list-items"
  | "ai-assistant"
  | "document-approval"
  | "submittals"
  | "asset-warranty"
  | "asset-meter"
  | "asset-inventory"
  | "service-request"
  | "work-order-request"
  | "preventive-work-order"
  | "corrective-work-order"
  | "preventive-maintenance"
  | "job-plans"
  | "facility-inspections"
  | "facility-condition-assessment"
  | "lease"
  | "lease-contact"
  | "lease-invoice"
  | "lease-payment"
  | "lease-termination"
  | "prospective-property"
  | "prospective-selection"
  | "prospective-disposition"
  | "prospective-creation"
  | "deed"
  | "easements"
  | "parcels"
  | "property-tax"
  | "property-payments"
  | "energy-meter"
  | "water-meter"
  | "baseline"
  | "progress"
  | "costs"
  | "integrated-control"
  | "decisions"
  | "evidence"
  | "work-packages"
  | "company-organization"
  | "authentication-sessions"
  | "group-creator"
  | "permissions"
  | "access-control"
  | "workspace-types"
  | "enterprise-workspace-structure"
  | "enterprise-structure-configuration"
  | "enterprise-explorer"
  | "workspace-defaults"
  | "module-catalog-activation"
  | "workspace-navigation-profiles"
  | "master-catalogs"
  | "numbering-rules"
  | "process-definitions"
  | "admin";

export type ApplicationMode = "user" | "admin";

export type NavigationViewItem = {
  key: ControlFlowView;
  label: string;
  classification?: StrategicControlClassification;
  count?: string | number;
  description?: string;
  route?: string;
  phase?: number;
  isFoundation?: boolean;
  badge?: string;
  children?: NavigationViewItem[];
};

export type ModuleNavigationItem = {
  key: string;
  label: string;
  classification?: StrategicControlClassification;
  submodules: NavigationViewItem[];
  description?: string;
  phase?: number;
  isFoundation?: boolean;
  badge?: string;
};

export type MacroprocessNavigationItem = {
  key: string;
  label: string;
  classification?: StrategicControlClassification;
  modules: ModuleNavigationItem[];
  description?: string;
};

const PROJECT_WORKSPACE_GOVERNANCE_MODULES: ModuleNavigationItem[] = [
  {
    key: "workspaces-manager",
    label: "Workspaces Manager",
    submodules: [
      { key: "project-creator", label: "Project Creator" },
      { key: "setup", label: "Asset Creator/Receipt" },
    ],
  },
  {
    key: "partners",
    label: "Partners",
    submodules: [{ key: "join-venture", label: "Join Venture" }],
  },
  {
    key: "vendors",
    label: "Vendors",
    submodules: [{ key: "vendors-list", label: "Vendors List" }],
  },
  {
    key: "commitments",
    label: "Commitments",
    submodules: [
      { key: "sales-contracts", label: "Sales Contracts" },
      { key: "sc-changes", label: "SC Changes" },
      { key: "sc-payments", label: "SC Payments" },
      { key: "commitment-purchase-order", label: "Purchase Order" },
      { key: "commitment-po-changes", label: "PO Changes" },
      { key: "commitment-po-payments", label: "PO Payments" },
    ],
  },
];

const NON_STRATEGIC_USER_MODE_NAVIGATION_BLUEPRINT: MacroprocessNavigationItem[] = [
  {
    key: "project-control-manager",
    label: "Project Control Manager",
    modules: [
      {
        key: "project-manager",
        label: "Project Manager",
        submodules: [
          { key: "meeting-minutes", label: "Meeting Minutes" },
          { key: "communications", label: "Communications" },
          { key: "issues", label: "Issues" },
          { key: "lessons-learned", label: "Lessons Learned" },
          { key: "punch-list-items", label: "Punch List Items" },
          { key: "ai-assistant", label: "AI Assistant" },
        ],
      },
      {
        key: "scope-manager",
        label: SCOPE_MANAGER_MODULE_LABEL,
        submodules: [
          { key: "quantity-takeoff", label: BIM_MANAGER_SUBMODULE_LABEL },
          { key: "scope-items", label: "Scope Items" },
          { key: "process-flow", label: "Strategy&Path of Execution" },
          { key: "plan-items", label: "Plan Items" },
          { key: "work-packages", label: "Work Packages" },
          { key: "decisions", label: "Scope Changes" },
        ],
      },
      {
        key: "schedule-manager",
        label: "Schedule Manager",
        submodules: [
          { key: "schedule-intake", label: "Activity Sheet" },
          { key: "schedule-control", label: "Schedule" },
          { key: "schedule-4d", label: "4D Model" },
          { key: "schedule-changes", label: "Schedule Changes" },
        ],
      },
      {
        key: "cost-manager",
        label: "Cost Manager",
        submodules: [
          { key: "costs", label: "Cost Items" },
          { key: "estimates", label: "Estimates" },
          { key: "bim-budget", label: "Budget" },
          { key: "integrated-control", label: "Fund" },
          { key: "cash-flow", label: "Cash Flow" },
          { key: "budget-changes", label: "Budget Changes" },
          { key: "budget-transfer", label: "Budget Transfer" },
        ],
      },
      {
        key: "risk-manager",
        label: "Risk Manager",
        submodules: [
          { key: "risk-register", label: "Risk Register" },
          { key: "risk-evaluation-matrix", label: "Risk Evaluation Matrix" },
          { key: "risk-quantification-analysis", label: "Risk Quantification Analysis" },
          { key: "contingency-quantification", label: "Contingency Quantification" },
        ],
      },
      {
        key: "procurement-manager",
        label: "Procurement Manager",
        submodules: [
          { key: "request-for-bid", label: "Request for Bid" },
          { key: "contracts", label: "Contracts" },
          { key: "contracts-changes", label: "Contracts Changes" },
          { key: "contract-payments", label: "Contract Payments" },
          { key: "purchase-order", label: "Purchase Order" },
          { key: "po-changes", label: "PO Changes" },
          { key: "po-payments", label: "PO Payments" },
        ],
      },
      {
        key: "progress-performance-manager",
        label: "Progress&Performance Manager",
        submodules: [
          { key: "progress", label: "Measuring Progress" },
          { key: "earned-value-analysis", label: "Earned Value Analysis" },
        ],
      },
      {
        key: "resource-manager",
        label: "Resource Manager",
        submodules: [{ key: "apu-catalog", label: "Master Rate Sheet" }],
      },
      {
        key: "claim-manager",
        label: "Claim Manager",
        submodules: [
          { key: "claims-audit", label: "Reclamaciones" },
          { key: "window-analysis-37", label: "Ventanas 3.7" },
        ],
      },
      {
        key: "document-manager",
        label: "Document Manager",
        submodules: [
          { key: "document-approval", label: "Document Approval" },
          { key: "submittals", label: "Submittals" },
        ],
      },
    ],
  },
  {
    key: "facility-manager",
    label: "Facility Manager",
    modules: [
      {
        key: "asset-manager",
        label: "Asset Manager",
        submodules: [
          { key: "asset-inventory", label: "Asset Inventory" },
          { key: "asset-warranty", label: "Asset Warranty" },
          { key: "asset-meter", label: "Asset Meter" },
        ],
      },
      {
        key: "maintenance-manager",
        label: "Maintenance Manager",
        submodules: [
          { key: "service-request", label: "Service Request" },
          { key: "work-order-request", label: "Work Order Request" },
          { key: "preventive-work-order", label: "Preventive Work order" },
          { key: "corrective-work-order", label: "Corrective Work order" },
          { key: "preventive-maintenance", label: "Preventive Maintenance" },
          { key: "job-plans", label: "Job Plans" },
        ],
      },
      {
        key: "condition-assessment-manager",
        label: "Condition Assessment Manager",
        submodules: [
          { key: "facility-inspections", label: "Facility Inspections" },
          { key: "facility-condition-assessment", label: "Facility Condiction Assessment" },
        ],
      },
    ],
  },
  {
    key: "property-manager",
    label: "Property Manager",
    modules: [
      {
        key: "lease-manager",
        label: "Lease Manager",
        submodules: [
          { key: "lease", label: "Lease" },
          { key: "lease-contact", label: "Lease Contact" },
          { key: "lease-invoice", label: "Lease Invoice" },
          { key: "lease-payment", label: "Lease Payment" },
          { key: "lease-termination", label: "Lease Termination" },
        ],
      },
      {
        key: "property-transaction-manager",
        label: "Property Transaction Manager",
        submodules: [
          { key: "prospective-property", label: "Prospective Property" },
          { key: "prospective-selection", label: "Prospective Selection" },
          { key: "prospective-disposition", label: "Prospective Disposition" },
          { key: "prospective-creation", label: "Prospective Creation" },
        ],
      },
      {
        key: "property-information-manager",
        label: "Property Information Manager",
        submodules: [
          { key: "deed", label: "Deed" },
          { key: "easements", label: "Easements" },
          { key: "parcels", label: "Parcels" },
          { key: "property-tax", label: "Property Tax" },
          { key: "property-payments", label: "Property Payments" },
        ],
      },
      {
        key: "property-utilities-manager",
        label: "Property Utilities Manager",
        submodules: [
          { key: "energy-meter", label: "Energy Meter" },
          { key: "water-meter", label: "Water Meter" },
        ],
      },
    ],
  },
];

export const USER_MODE_NAVIGATION_BLUEPRINT: MacroprocessNavigationItem[] = [
  buildStrategicMacroprocess("user"),
  {
    key: "project-workspace-governance",
    label: "Project Workspace Governance",
    description:
      "Alternate Project creation and commercial Workspace capabilities kept outside the universal strategic Idea flow.",
    modules: PROJECT_WORKSPACE_GOVERNANCE_MODULES,
  },
  ...NON_STRATEGIC_USER_MODE_NAVIGATION_BLUEPRINT,
];

const PLATFORM_ADMINISTRATION_MODULES: ModuleNavigationItem[] = [
  {
    key: "organization-security",
    label: "Organization & Security",
    submodules: [
      { key: "company-organization", label: "Company & Organization Manager" },
      { key: "authentication-sessions", label: "Authentication & Session Management" },
      { key: "admin", label: "User Creator" },
      { key: "group-creator", label: "Group Creator" },
      { key: "permissions", label: "Permissions" },
      { key: "access-control", label: "Access Control" },
    ],
  },
  {
    key: "general-configuration",
    label: "General Configuration",
    submodules: [
      { key: "master-catalogs", label: "Master Catalogs" },
      { key: "numbering-rules", label: "Numbering & Coding Rules" },
    ],
  },
  {
    key: "process-configuration",
    label: "Process Configuration",
    submodules: [{ key: "process-definitions", label: "Process Definitions" }],
  },
];

export const ADMIN_MODE_NAVIGATION_BLUEPRINT: MacroprocessNavigationItem[] = [
  buildStrategicMacroprocess("admin"),
  {
    key: "platform-administration",
    label: "Platform Administration",
    description: "Organization, security and shared platform configuration.",
    modules: PLATFORM_ADMINISTRATION_MODULES,
  },
];

export function flattenNavigationViews(items: MacroprocessNavigationItem[]) {
  const flattenItem = (item: NavigationViewItem): NavigationViewItem[] => [
    item,
    ...(item.children ?? []).flatMap(flattenItem),
  ];
  return items.flatMap((macroprocess) =>
    macroprocess.modules.flatMap((module) => module.submodules.flatMap(flattenItem))
  );
}

export const EMPTY_SUBMODULE_VIEWS = new Set<ControlFlowView>([
  "portfolio-structure",
  "project-intake-from-ideas",
  "portfolio-cash-flow",
  "join-venture",
  "vendors-list",
  "sales-contracts",
  "sc-changes",
  "sc-payments",
  "commitment-purchase-order",
  "commitment-po-changes",
  "commitment-po-payments",
  "scope-items",
  "plan-items",
  "schedule-4d",
  "schedule-changes",
  "estimates",
  "cash-flow",
  "budget-changes",
  "budget-transfer",
  "risk-register",
  "risk-evaluation-matrix",
  "risk-quantification-analysis",
  "contingency-quantification",
  "request-for-bid",
  "contracts",
  "contracts-changes",
  "contract-payments",
  "purchase-order",
  "po-changes",
  "po-payments",
  "earned-value-analysis",
  "gate-decision",
  "meeting-minutes",
  "communications",
  "issues",
  "lessons-learned",
  "punch-list-items",
  "ai-assistant",
  "document-approval",
  "submittals",
  "asset-warranty",
  "asset-meter",
  "asset-inventory",
  "service-request",
  "work-order-request",
  "preventive-work-order",
  "corrective-work-order",
  "preventive-maintenance",
  "job-plans",
  "facility-inspections",
  "facility-condition-assessment",
  "lease",
  "lease-contact",
  "lease-invoice",
  "lease-payment",
  "lease-termination",
  "prospective-property",
  "prospective-selection",
  "prospective-disposition",
  "prospective-creation",
  "deed",
  "easements",
  "parcels",
  "property-tax",
  "property-payments",
  "energy-meter",
  "water-meter",
]);
