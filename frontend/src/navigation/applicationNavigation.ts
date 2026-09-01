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
  | "strategic-project-planning-entry"
  | "portfolio-projects"
  | "portfolio-planning-configuration"
  | "portfolio-evaluation"
  | "portfolio-evaluation-configuration"
  | "portfolio-analysis"
  | "portfolio-analysis-configuration"
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
          { key: "strategic-project-planning-entry", label: "Strategic Project Planning Entry" },
          { key: "portfolio-projects", label: "Portfolio Projects" },
          { key: "portfolio-evaluation", label: "Portfolio Evaluation" },
          { key: "portfolio-analysis", label: "Portfolio Analysis" },
          { key: "strategic-prioritization-matrix", label: "Prioritization Matrix" },
          { key: "portfolio-budget-planning", label: "Portfolio Budget Planning" },
          { key: "portfolio-resource-planning", label: "Portfolio Resource Planning" },
          { key: "portfolio-scenario-convergence", label: "Portfolio Scenario Convergence" },
          { key: "investment-gate-preparation", label: "Investment Gate Preparation" },
          { key: "portfolio-cash-flow", label: "Portfolio Cash Flow" },
          { key: "gate-decision", label: "Gate Decision" },
        ],
      },
      {
        key: "project-definition-manager",
        label: "Project Definition / FEL Manager",
        submodules: [{ key: "project-definition-fel", label: "Project Definition / FEL Manager" }],
      },
      {
        key: "funds-manager",
        label: "Funds Manager",
        submodules: [
          { key: "funds-overview", label: "Overview" },
          { key: "funds-sources", label: "Funding Sources" },
          { key: "funds-envelopes", label: "Funds" },
          { key: "funds-assignments", label: "Funding Assignments" },
          { key: "funds-coverage", label: "Funding Coverage" },
          { key: "funds-readiness", label: "Funding Readiness" },
          { key: "funds-history", label: "History / Audit" },
        ],
      },
      {
        key: "investment-governance",
        label: "Investment Governance",
        submodules: [
          { key: "risk-readiness-my", label: "My Risk Work" },
          { key: "risk-readiness-portfolio", label: "Project Set Risk Readiness" },
          { key: "risk-readiness-register", label: "Project Risk Register" },
          { key: "risk-readiness-assessments", label: "Risk Assessments" },
          { key: "risk-readiness-treatments", label: "Treatments" },
          { key: "risk-readiness-residual", label: "Residual Risk & Acceptance" },
          { key: "risk-readiness-dashboard", label: "Risk Readiness Dashboard" },
          { key: "risk-readiness-history", label: "History / Audit" },
          { key: "permit-readiness-my", label: "My Permit Work" },
          { key: "permit-readiness-register", label: "Project Permit Register" },
          { key: "permit-readiness-requirements", label: "Permit Requirements" },
          { key: "permit-readiness-conditions", label: "Permit Conditions" },
          { key: "permit-readiness-project", label: "Project Permit Readiness" },
          { key: "permit-readiness-portfolio", label: "Project Set Permit Readiness" },
          { key: "permit-readiness-history", label: "Permit History / Audit" },
          { key: "investment-decision-queue", label: "Decision Queue" },
          { key: "investment-decision-mine", label: "My Decisions" },
          { key: "investment-decision-package", label: "Investment Decision Package" },
          { key: "investment-decision-evidence", label: "Evidence Summary" },
          { key: "investment-decision-checklist", label: "Decision Checklist" },
          { key: "investment-decision-conditions", label: "Conditions" },
          { key: "investment-decision-committee", label: "Committee / Votes" },
          { key: "investment-decision-history", label: "Decision History" },
          { key: "investment-decision-output", label: "Authorization Output" },
          { key: "post-fid-queue", label: "Post-FID Queue" },
          { key: "post-fid-handoff", label: "FID Handoff" },
          { key: "post-fid-eligibility-matrix", label: "Project Eligibility Matrix" },
          { key: "post-fid-conditions", label: "Post-FID Conditions" },
          { key: "post-fid-initialization-handoff", label: "Initialization Handoff" },
          { key: "post-fid-activation-handoff", label: "Activation Handoff" },
          { key: "post-fid-history", label: "Post-FID History / Audit" },
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
      { key: "portfolio-planning-configuration", label: "Portfolio Planning Entry & Membership" },
      { key: "portfolio-evaluation-configuration", label: "Portfolio Evaluation & Prioritization" },
      { key: "portfolio-analysis-configuration", label: "Portfolio Analysis Configuration" },
      { key: "portfolio-budget-planning-configuration", label: "Portfolio Budget Planning Configuration" },
      { key: "portfolio-resource-planning-configuration", label: "Portfolio Resource Planning Configuration" },
      { key: "portfolio-scenario-convergence-configuration", label: "Portfolio Scenario Convergence Configuration" },
      { key: "investment-gate-preparation-configuration", label: "Investment Gate Preparation Configuration" },
      { key: "investment-decision-evidence-policy", label: "Investment Decision Evidence Policy" },
      { key: "project-definition-configuration", label: "Project Definition / FEL Manager" },
      { key: "funds-manager-configuration", label: "Funds Manager Configuration" },
      { key: "risk-readiness-configuration", label: "Risk Readiness Configuration" },
      { key: "permit-readiness-configuration", label: "Permit Readiness Configuration" },
      { key: "investment-decision-configuration", label: "Investment Decision / FID Governance" },
      { key: "post-fid-governance-configuration", label: "Post-FID Project Governance" },
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
