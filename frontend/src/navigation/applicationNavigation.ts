export const SCOPE_MANAGER_MODULE_LABEL = "Scope Manager";
export const BIM_MANAGER_SUBMODULE_LABEL = "BIM Manager";

export type ControlFlowView =
  | "dashboard"
  | "opc-gap"
  | "idea-lifecycle"
  | "idea-demand-configuration"
  | "project-proposal"
  | "project-proposal-configuration"
  | "strategic-gate-decision"
  | "strategic-gate-configuration"
  | "portfolio-structure"
  | "project-intake-from-ideas"
  | "portfolio-budget-planning"
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
  count?: string | number;
};

export type ModuleNavigationItem = {
  key: string;
  label: string;
  submodules: NavigationViewItem[];
};

export type MacroprocessNavigationItem = {
  key: string;
  label: string;
  modules: ModuleNavigationItem[];
};

export const USER_MODE_NAVIGATION_BLUEPRINT: MacroprocessNavigationItem[] = [
  {
    key: "enterprise-strategy-manager",
    label: "Enterprise Strategy Manager",
    modules: [
      {
        key: "idea-demand-manager",
        label: "Idea & Demand Manager",
        submodules: [
          { key: "idea-lifecycle", label: "Idea Lifecycle" },
          { key: "project-proposal", label: "Project Proposal" },
        ],
      },
      {
        key: "strategic-gate-decision",
        label: "Strategic Gate Decision",
        submodules: [{ key: "strategic-gate-decision", label: "Strategic Gate Decision" }],
      },
      {
        key: "enterprise-structure-workspace-manager",
        label: "Enterprise Structure & Workspace Manager",
        submodules: [{ key: "enterprise-explorer", label: "Enterprise Explorer" }],
      },
      {
        key: "portfolio-manager",
        label: "Portfolio Manager",
        submodules: [
          { key: "portfolio-structure", label: "Portfolio Structure" },
          { key: "project-intake-from-ideas", label: "Project Intake from Ideas" },
          { key: "portfolio-budget-planning", label: "Portfolio Budget Planning" },
          { key: "portfolio-cash-flow", label: "Portfolio Cash Flow" },
          { key: "strategic-investment-map", label: "Strategic Investment Map" },
          { key: "strategic-prioritization-matrix", label: "Strategic Prioritization Matrix" },
          { key: "gate-decision", label: "Gate Decision" },
        ],
      },
      {
        key: "funds",
        label: "Funds",
        submodules: [
          { key: "funds-sources", label: "Funds Sources" },
          { key: "funds-assignments", label: "Funds Assigments" },
        ],
      },
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
    ],
  },
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

export const ADMIN_MODE_NAVIGATION_BLUEPRINT: ModuleNavigationItem[] = [
  {
    key: "enterprise-strategy-manager",
    label: "Enterprise Strategy Manager",
    submodules: [
      { key: "idea-demand-configuration", label: "Idea Lifecycle Configuration" },
      { key: "project-proposal-configuration", label: "Project Proposal Configuration" },
      { key: "strategic-gate-configuration", label: "Strategic Gate Decision" },
    ],
  },
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
    key: "enterprise-structure",
    label: "Enterprise Structure",
    submodules: [
      { key: "enterprise-structure-configuration", label: "Enterprise Structure Configuration" },
      { key: "workspace-defaults", label: "Workspace Defaults & Inheritance" },
      { key: "module-catalog-activation", label: "Module Catalog & Activation" },
      { key: "workspace-navigation-profiles", label: "Workspace Navigation Profiles" },
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

export const EMPTY_SUBMODULE_VIEWS = new Set<ControlFlowView>([
  "portfolio-structure",
  "project-intake-from-ideas",
  "portfolio-budget-planning",
  "portfolio-cash-flow",
  "strategic-prioritization-matrix",
  "join-venture",
  "vendors-list",
  "sales-contracts",
  "sc-changes",
  "sc-payments",
  "commitment-purchase-order",
  "commitment-po-changes",
  "commitment-po-payments",
  "funds-sources",
  "funds-assignments",
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
  "strategic-investment-map",
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
