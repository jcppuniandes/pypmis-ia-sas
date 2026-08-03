import {
  Component,
  Suspense,
  lazy,
  useEffect,
  useMemo,
  useState,
  type ChangeEvent,
  type ComponentType,
  type FormEvent,
  type ReactNode,
} from "react";
import {
  Building2,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Database,
  Download,
  FileSearch,
  FileUp,
  GitBranch,
  PackagePlus,
  Ruler,
  Save,
  ShieldCheck,
  Trash2,
} from "lucide-react";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { admin as adminApi } from "./api/admin";
import { ApiError } from "./api/client";
import { dashboard as dashboardApi } from "./api/dashboard";
import { bimModels as bimModelsApi } from "./api/bimModels";
import { integratedControl as integratedControlApi } from "./api/integratedControl";
import { projects as projectsApi } from "./api/projects";
import BimBudgetPanel from "./components/BimBudgetPanel";
import BimScopeValidationPanel from "./components/BimScopeValidationPanel";
import CostCurrencyGate from "./components/CostCurrencyGate";
import GuidedProcessRail from "./components/GuidedProcessRail";
import NextActionPanel from "./components/NextActionPanel";
import OpcGapReadinessPanel from "./components/OpcGapReadinessPanel";
import ProductLogo from "./components/ProductLogo";
import ProjectControlsHandbook from "./components/ProjectControlsHandbook";
import ProjectCreateDrawer from "./components/ProjectCreateDrawer";
import TenantCommandBar from "./components/TenantCommandBar";
import { buildBimBudget } from "./lib/bimBudget";
import { buildCumulativeEvmCurve, deriveProjectEvm, formatEvmRatio } from "./lib/evm";
import { buildOpcGapAnalysis } from "./lib/opcGap";
import { useAuthStore } from "./store/auth";
import { useProjectStore } from "./store/project";
import type {
  ActivitySheet,
  ActivitySheetRecostRun,
  ActivitySheetRow,
  ActivitySheetWbsRow,
  BusinessProcessLineItem,
  BusinessProcessLineItemRevision,
  BusinessProcessPolicy,
  BimGeometryMeasurementBatch,
  BimQuantityRule,
  BimQuantityRuleUpdate,
  ColombiaApuCatalogItem,
  ColombiaApuCatalogSync,
  CloseoutReport,
  ControlAccount,
  ControlAgentRun,
  ControlledMeasurementApproval,
  CostBreakdownStructure,
  CostCode,
  CostSheetLine,
  Dashboard,
  ForecastFundingReport,
  ForensicDossierAnalysis,
  ForensicRagSource,
  ForensicWindowAnalysis,
  FundingSource,
  GuidedFlow,
  IntegratedControlMatrixRow,
  ProcessFlowBoard,
  Project,
  ProjectOperationalSetup,
  BimModel,
  QuantityControlCodeAssignment,
  QuantityRuleRecalculation,
  QuantityTakeoffLine,
  QuantityTakeoffRun,
  RateSheet,
  ReconciliationReport,
  RoleProfile,
  ScheduleActivityMap,
  ScheduleRelationship,
  User,
  WorkPackage,
  WbsNode,
} from "./types";
import LoginView from "./views/LoginView";

const BIM_VIEWER_MODULE_RELOAD_KEY = "pypmis:bim-viewer-module-reload";
const SCOPE_MANAGER_MODULE_LABEL = "Scope Manager";
const BIM_MANAGER_SUBMODULE_LABEL = "BIM Manager";

function lazyWithModuleRecovery<TProps>(factory: () => Promise<{ default: ComponentType<TProps> }>) {
  return lazy(async () => {
    try {
      const module = await factory();
      window.sessionStorage.removeItem(BIM_VIEWER_MODULE_RELOAD_KEY);
      return module;
    } catch (error) {
      const alreadyReloaded = window.sessionStorage.getItem(BIM_VIEWER_MODULE_RELOAD_KEY) === "1";
      if (!alreadyReloaded) {
        window.sessionStorage.setItem(BIM_VIEWER_MODULE_RELOAD_KEY, "1");
        window.location.reload();
        return new Promise<{ default: ComponentType<TProps> }>(() => undefined);
      }
      throw error;
    }
  });
}

type LazyModuleErrorBoundaryProps = {
  children: ReactNode;
  moduleName: string;
};

type LazyModuleErrorBoundaryState = {
  errorMessage: string;
  hasError: boolean;
};

class LazyModuleErrorBoundary extends Component<LazyModuleErrorBoundaryProps, LazyModuleErrorBoundaryState> {
  state: LazyModuleErrorBoundaryState = { errorMessage: "", hasError: false };

  static getDerivedStateFromError(error: unknown): LazyModuleErrorBoundaryState {
    return {
      errorMessage: error instanceof Error ? error.message : "Modulo no disponible",
      hasError: true,
    };
  }

  render() {
    if (!this.state.hasError) return this.props.children;
    return (
      <section aria-label={this.props.moduleName} className="bimViewer bimViewerWide ifcGeometryViewer">
        <div className="panelHeader compactHeader bimViewerHeader">
          <div className="bimViewerTitle">
            <h3>{this.props.moduleName}</h3>
            <span>No se pudo cargar el modulo BIM en esta sesion.</span>
          </div>
          <button
            className="workflowAction"
            onClick={() => {
              window.sessionStorage.removeItem(BIM_VIEWER_MODULE_RELOAD_KEY);
              window.location.reload();
            }}
            type="button"
          >
            Recargar modulo
          </button>
        </div>
        <div className="bimViewerCanvasWrap ifcGeometryCanvasWrap loadingCanvas">
          <strong>Visor IFC temporalmente no disponible</strong>
          <span>{this.state.errorMessage}</span>
        </div>
      </section>
    );
  }
}

const BimIfcModelViewer = lazyWithModuleRecovery(() => import("./components/BimIfcModelViewer"));

function RequireAuth({ children }: { children: ReactNode }) {
  const { token } = useAuthStore();
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

type ControlFlowView =
  | "dashboard"
  | "opc-gap"
  | "idea-register"
  | "idea-intake"
  | "idea-evaluation-matrix"
  | "project-proposal-creation"
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
  | "secop-bidder"
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
  | "baseline"
  | "progress"
  | "costs"
  | "integrated-control"
  | "decisions"
  | "evidence"
  | "work-packages"
  | "group-creator"
  | "permissions"
  | "access-control"
  | "admin";

type ApplicationMode = "user" | "admin";

type NavigationViewItem = {
  key: ControlFlowView;
  label: string;
  count?: string | number;
};

type ModuleNavigationItem = {
  key: string;
  label: string;
  submodules: NavigationViewItem[];
};

type MacroprocessNavigationItem = {
  key: string;
  label: string;
  modules: ModuleNavigationItem[];
};

const USER_MODE_NAVIGATION_BLUEPRINT: MacroprocessNavigationItem[] = [
  {
    key: "enterprise-strategy-manager",
    label: "Enterprise Strategy Manager",
    modules: [
      {
        key: "idea-demand-manager",
        label: "Idea & Demand Manager",
        submodules: [
          { key: "secop-bidder", label: "SECOP Bidder" },
          { key: "idea-register", label: "Idea Register" },
          { key: "idea-intake", label: "Idea Intake" },
          { key: "idea-evaluation-matrix", label: "Idea Evaluation Matrix" },
          { key: "project-proposal-creation", label: "Project Proposal Creation" },
        ],
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
    key: "facilities-asset-manager",
    label: "Facilities&Asset Manager",
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
];

const ADMIN_MODE_NAVIGATION_BLUEPRINT: ModuleNavigationItem[] = [
  {
    key: "admistration",
    label: "Admistration",
    submodules: [
      { key: "admin", label: "User Creator" },
      { key: "group-creator", label: "Group Creator" },
      { key: "permissions", label: "Permissions" },
      { key: "access-control", label: "Access Control" },
    ],
  },
];

const EMPTY_SUBMODULE_VIEWS = new Set<ControlFlowView>([
  "idea-register",
  "idea-intake",
  "idea-evaluation-matrix",
  "project-proposal-creation",
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
  "secop-bidder",
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
  "group-creator",
  "permissions",
  "access-control",
]);

// Validation mode narrows the UI to Dashboard + BIM while field validation is
// running. Runtime default stays on; tests set VITE_FRONTEND_VALIDATION_MODE
// to "false" (or the globalThis override, per test) to exercise both layouts.
type ValidationModeGlobal = typeof globalThis & { __PYPMIS_VALIDATION_MODE__?: boolean };

function frontendValidationMode(): boolean {
  const override = (globalThis as ValidationModeGlobal).__PYPMIS_VALIDATION_MODE__;
  if (override !== undefined) return override;
  return import.meta.env.VITE_FRONTEND_VALIDATION_MODE !== "false";
}
const FRONTEND_VALIDATION_VIEWS: ControlFlowView[] = [
  "dashboard",
  "opc-gap",
  ...USER_MODE_NAVIGATION_BLUEPRINT.flatMap((macroprocess) =>
    macroprocess.modules.flatMap((module) => module.submodules.map((item) => item.key))
  ),
  ...ADMIN_MODE_NAVIGATION_BLUEPRINT.flatMap((module) => module.submodules.map((item) => item.key)),
];
const APU_SOURCE_OPTIONS = [
  { key: "", label: "Todas las fuentes" },
  { key: "datacauca_public_apu", label: "DataCauca" },
  { key: "invias_reference_apu", label: "INVIAS" },
  { key: "idu_reference_apu", label: "IDU" },
  { key: "local_starter_colombia_apu", label: "Starter local" },
];

function focusedControlView(view: ControlFlowView): ControlFlowView {
  return FRONTEND_VALIDATION_VIEWS.includes(view) ? view : "dashboard";
}

function ModuleNavigationGroups({
  activeView,
  items,
  onNavigate,
}: {
  activeView: ControlFlowView;
  items: ModuleNavigationItem[];
  onNavigate: (view: ControlFlowView) => void;
}) {
  const activeModuleKey = items.find((module) =>
    module.submodules.some((submodule) => submodule.key === activeView)
  )?.key;
  const [expandedModules, setExpandedModules] = useState<Record<string, boolean>>({});

  return items.map((module) => {
    const moduleActive = module.submodules.some((submodule) => submodule.key === activeView);
    const moduleExpanded = expandedModules[module.key] ?? module.key === activeModuleKey;
    const submoduleListId = `${module.key}-submodules`;
    return (
      <div className={moduleActive ? "navigatorModule active" : "navigatorModule"} key={module.key}>
        <button
          aria-controls={submoduleListId}
          aria-expanded={moduleExpanded}
          className="navigatorModuleButton"
          onClick={() =>
            setExpandedModules((current) => ({
              ...current,
              [module.key]: !moduleExpanded,
            }))
          }
          type="button"
        >
          <span className="navigatorModuleCopy">{module.label}</span>
          <ChevronDown aria-hidden="true" className={moduleExpanded ? "expanded" : ""} size={17} />
        </button>
        <div
          aria-label={`Submódulos de ${module.label}`}
          className="navigatorSubmoduleList"
          hidden={!moduleExpanded}
          id={submoduleListId}
          role="group"
        >
          {module.submodules.map((submodule) => {
            const submoduleActive = submodule.key === activeView;
            return (
              <button
                aria-current={submoduleActive ? "page" : undefined}
                className={submoduleActive ? "navigatorSubmoduleItem active" : "navigatorSubmoduleItem"}
                key={submodule.key}
                onClick={() => onNavigate(submodule.key)}
                type="button"
              >
                <span>{submodule.label}</span>
                {submodule.count !== undefined ? <strong>{submodule.count}</strong> : null}
              </button>
            );
          })}
        </div>
      </div>
    );
  });
}

function ModuleNavigationItems({
  activeView,
  items,
  onNavigate,
}: {
  activeView: ControlFlowView;
  items: MacroprocessNavigationItem[];
  onNavigate: (view: ControlFlowView) => void;
}) {
  const activeMacroprocessKey = items.find((macroprocess) =>
    macroprocess.modules.some((module) => module.submodules.some((submodule) => submodule.key === activeView))
  )?.key;
  const [expandedMacroprocesses, setExpandedMacroprocesses] = useState<Record<string, boolean>>({});

  return items.map((macroprocess) => {
    const macroprocessActive = macroprocess.modules.some((module) =>
      module.submodules.some((submodule) => submodule.key === activeView)
    );
    const macroprocessExpanded =
      expandedMacroprocesses[macroprocess.key] ??
      (macroprocess.key === activeMacroprocessKey ||
        macroprocess.key === items[0]?.key ||
        macroprocess.key === "project-control-manager");
    const moduleListId = `${macroprocess.key}-modules`;

    return (
      <div
        className={macroprocessActive ? "navigatorMacroprocess active" : "navigatorMacroprocess"}
        key={macroprocess.key}
      >
        <button
          aria-controls={moduleListId}
          aria-expanded={macroprocessExpanded}
          className="navigatorMacroprocessButton"
          onClick={() =>
            setExpandedMacroprocesses((current) => ({
              ...current,
              [macroprocess.key]: !macroprocessExpanded,
            }))
          }
          type="button"
        >
          <span className="navigatorMacroprocessCopy">{macroprocess.label}</span>
          <ChevronDown aria-hidden="true" className={macroprocessExpanded ? "expanded" : ""} size={17} />
        </button>
        <div
          aria-label={`Módulos de ${macroprocess.label}`}
          className="navigatorModuleList"
          hidden={!macroprocessExpanded}
          id={moduleListId}
          role="group"
        >
          <ModuleNavigationGroups activeView={activeView} items={macroprocess.modules} onNavigate={onNavigate} />
        </div>
      </div>
    );
  });
}

function ApplicationModeToggle({ mode, onToggle }: { mode: ApplicationMode; onToggle: () => void }) {
  const nextModeLabel = mode === "user" ? "ADMIN MODE" : "USER MODE";
  return (
    <button
      aria-label={`Cambiar a ${nextModeLabel}`}
      aria-pressed={mode === "admin"}
      className={`applicationModeToggle ${mode}`}
      onClick={onToggle}
      title={`Cambiar a ${nextModeLabel}`}
      type="button"
    >
      <span>Modo actual</span>
      <strong>{mode === "user" ? "USER MODE" : "ADMIN MODE"}</strong>
    </button>
  );
}

function WorkspaceNavigation({
  activeView,
  adminItems,
  applicationMode,
  baselineOnlyEvm,
  onNavigate,
  readinessScore,
  spiLabel,
  userItems,
  validationMode,
}: {
  activeView: ControlFlowView;
  adminItems: ModuleNavigationItem[];
  applicationMode: ApplicationMode;
  baselineOnlyEvm: boolean;
  onNavigate: (view: ControlFlowView) => void;
  readinessScore: number;
  spiLabel: string;
  userItems: MacroprocessNavigationItem[];
  validationMode: boolean;
}) {
  const adminMode = applicationMode === "admin";
  return (
    <nav
      aria-label={adminMode ? "Admin mode navigation" : validationMode ? "Validation focus" : "Control Flow"}
      className="navigatorRail"
    >
      <div className="navigatorHeader">
        <strong>{adminMode ? "ADMIN MODE" : "USER MODE"}</strong>
        <span>{adminMode ? "Módulos + submódulos" : "Macroprocesos + módulos"}</span>
      </div>
      {adminMode ? (
        <>
          <div className="navigatorDivider">
            <span>Módulos</span>
          </div>
          <div aria-label="Módulos de ADMIN MODE" className="navigatorModuleList navigatorAdminModuleList" role="group">
            <ModuleNavigationGroups activeView={activeView} items={adminItems} onNavigate={onNavigate} />
          </div>
        </>
      ) : (
        <>
          <button
            aria-current={activeView === "dashboard" ? "page" : undefined}
            className={activeView === "dashboard" ? "navigatorItem active" : "navigatorItem"}
            onClick={() => onNavigate("dashboard")}
            type="button"
          >
            <span>Dashboard</span>
            <strong>{baselineOnlyEvm ? "N/A SPI" : `${spiLabel} SPI`}</strong>
          </button>
          <button
            aria-current={activeView === "opc-gap" ? "page" : undefined}
            className={activeView === "opc-gap" ? "navigatorItem active" : "navigatorItem"}
            onClick={() => onNavigate("opc-gap")}
            type="button"
          >
            <span>Diagnóstico de Control</span>
            <strong>{readinessScore}%</strong>
          </button>
          <div className="navigatorDivider">
            <span>Macroprocesos</span>
          </div>
          <ModuleNavigationItems activeView={activeView} items={userItems} onNavigate={onNavigate} />
        </>
      )}
    </nav>
  );
}

function routeControlView(pathname: string): ControlFlowView | null {
  return pathname.replace(/\/+$/, "").endsWith("/app/schedule-control") ? "schedule-control" : null;
}

const emptyManagedUserDraft = { email: "", full_name: "", title: "", password: "" };

function managedDraftForUser(user: User | undefined) {
  if (!user) return emptyManagedUserDraft;
  return {
    email: user.email,
    full_name: user.full_name,
    title: user.title,
    password: "",
  };
}

function isUnauthorizedApiError(err: unknown) {
  return err instanceof ApiError && err.status === 401;
}

const BIM_TAKEOFF_MAX_BYTES = 100 * 1024 * 1024;
const BIM_TAKEOFF_MAX_MB = BIM_TAKEOFF_MAX_BYTES / (1024 * 1024);

function apiErrorDetail(err: unknown): string {
  if (!(err instanceof Error)) return "";
  if (!(err instanceof ApiError)) return err.message;
  try {
    const parsed = JSON.parse(err.message) as { detail?: unknown };
    return typeof parsed.detail === "string" ? parsed.detail : err.message;
  } catch {
    return err.message;
  }
}

function quantityTakeoffErrorMessage(err: unknown): string {
  const detail = apiErrorDetail(err);
  if (err instanceof TypeError && /failed to fetch/i.test(detail)) {
    return "El procesamiento IFC se interrumpio antes de terminar. El modelo quedo guardado; reintenta el takeoff o carga un Excel/CSV controlado.";
  }
  if (err instanceof ApiError && err.status === 413) return detail;
  return detail || "Could not load quantity takeoff data";
}

function isIfcModel(file: File) {
  return file.name.toLowerCase().endsWith(".ifc");
}

function geometryModelForRun(run: QuantityTakeoffRun | undefined, models: BimModel[]) {
  if (!run?.bim_model_id) return undefined;
  return models.find((model) => model.id === run.bim_model_id);
}

type SetupDraftState = {
  project_number: string;
  setup_template: string;
  attribute_form: string;
  permissions_configured: boolean;
  modules_configured: boolean;
  cost_sheet_ready: boolean;
  funding_sheet_ready: boolean;
  p6_mapping_ready: boolean;
  status: string;
};

type WbsTreeNode = WbsNode & {
  children: WbsTreeNode[];
};

type WorkPackageTreeNode = WorkPackage & {
  children: WorkPackageTreeNode[];
};

type WbsTraceabilityRow = {
  id: string;
  awpPackageTitle: string;
  wbsCode: string;
  sourceWbsCode: string;
  wbsName: string;
  controlAccountCode: string;
  sourceControlAccountCode: string;
  controlAccountName: string;
  cbsCode: string;
  fbsCode: string;
  awpPackageCode: string;
  costCode: string;
  status: string;
  budget: number;
};

type CostFundingTraceabilityRow = {
  id: string;
  wbsCode: string;
  wbsName: string;
  controlAccountCode: string;
  controlAccountName: string;
  cbsCode: string;
  costCode: string;
  bac: number;
  ev: number;
  ac: number;
  cpi: number | null;
  fbsCode: string;
  fundingName: string;
  fundingStatus: string;
  fundingAmount: number;
  status: string;
};

function isSetupDraftReady(draft: SetupDraftState) {
  return (
    Boolean(draft.project_number.trim()) &&
    Boolean(draft.setup_template.trim()) &&
    Boolean(draft.attribute_form.trim()) &&
    draft.permissions_configured &&
    draft.modules_configured &&
    draft.cost_sheet_ready &&
    draft.funding_sheet_ready &&
    draft.p6_mapping_ready &&
    ["ready", "active"].includes(draft.status)
  );
}

function isDefaultProjectBaselineNode(node: WbsNode) {
  return node.code.trim() === "1.0" && node.name.trim().toLowerCase() === "project control baseline";
}

function inferWbsParentId(node: WbsNode, nodes: WbsNode[]) {
  if (node.parent_id) return node.parent_id;
  if (isDefaultProjectBaselineNode(node)) return null;
  const normalizedCode = node.code.trim();
  if (!normalizedCode) return null;
  const hasMeaningfulLevels = new Set(nodes.map((item) => item.level)).size > 1;
  const candidates = nodes
    .filter((candidate) => candidate.id !== node.id && !isDefaultProjectBaselineNode(candidate))
    .filter((candidate) => {
      const candidateCode = candidate.code.trim();
      if (!candidateCode || candidateCode.length >= normalizedCode.length) return false;
      const isCodeParent = ["-", ".", "/", "_"].some((separator) =>
        normalizedCode.startsWith(`${candidateCode}${separator}`)
      );
      if (!isCodeParent) return false;
      return node.level > candidate.level || !hasMeaningfulLevels;
    })
    .sort((left, right) => right.code.length - left.code.length || right.level - left.level);
  return candidates[0]?.id ?? null;
}

function buildWbsTree(nodes: WbsNode[]) {
  const effectiveNodes = nodes.map((node) => ({
    ...node,
    parent_id: inferWbsParentId(node, nodes),
  }));
  const byId = new Map<number, WbsTreeNode>();
  effectiveNodes.forEach((node) => byId.set(node.id, { ...node, children: [] }));
  const roots: WbsTreeNode[] = [];
  byId.forEach((node) => {
    const parent = node.parent_id ? byId.get(node.parent_id) : undefined;
    if (parent) {
      parent.children.push(node);
      return;
    }
    roots.push(node);
  });
  const sortTree = (items: WbsTreeNode[]) => {
    items.sort((left, right) => left.code.localeCompare(right.code, undefined, { numeric: true }));
    items.forEach((item) => sortTree(item.children));
  };
  sortTree(roots);
  return roots;
}

function flattenWbsTree(nodes: WbsTreeNode[], depth = 0): Array<{ node: WbsTreeNode; depth: number }> {
  return nodes.flatMap((node) => [{ node, depth }, ...flattenWbsTree(node.children, depth + 1)]);
}

function countWbsTreeNodes(node: WbsTreeNode): number {
  return 1 + node.children.reduce((total, child) => total + countWbsTreeNodes(child), 0);
}

function selectPrimaryWbsTree(nodes: WbsTreeNode[]) {
  const candidates = nodes
    .filter((node) => node.children.length > 0)
    .sort((left, right) => countWbsTreeNodes(right) - countWbsTreeNodes(left));
  return candidates[0] && countWbsTreeNodes(candidates[0]) >= 3 ? [candidates[0]] : nodes;
}

function sortWorkPackages(packages: WorkPackage[]) {
  return [...packages].sort(
    (left, right) =>
      left.sequence_no - right.sequence_no ||
      left.package_type.localeCompare(right.package_type) ||
      left.code.localeCompare(right.code, undefined, { numeric: true })
  );
}

function buildWorkPackageTree(packages: WorkPackage[]) {
  const byId = new Map<number, WorkPackageTreeNode>();
  sortWorkPackages(packages).forEach((workPackage) => byId.set(workPackage.id, { ...workPackage, children: [] }));
  const roots: WorkPackageTreeNode[] = [];
  byId.forEach((node) => {
    const parent = node.parent_id ? byId.get(node.parent_id) : undefined;
    if (parent) {
      parent.children.push(node);
      return;
    }
    roots.push(node);
  });
  const sortNodes = (items: WorkPackageTreeNode[]) => {
    items.sort(
      (left, right) =>
        left.sequence_no - right.sequence_no ||
        left.package_type.localeCompare(right.package_type) ||
        left.code.localeCompare(right.code, undefined, { numeric: true })
    );
    items.forEach((item) => sortNodes(item.children));
  };
  sortNodes(roots);
  return roots;
}

function workPackageWbsNode(wbsCatalog: WbsNode[], workPackage: WorkPackage) {
  return workPackage.wbs_id ? wbsCatalog.find((item) => item.id === workPackage.wbs_id) : undefined;
}

function workPackageWbsName(wbsCatalog: WbsNode[], workPackage: WorkPackage) {
  return workPackageWbsNode(wbsCatalog, workPackage)?.name || "WBS pending";
}

function workPackageDisplayLabel(wbsCatalog: WbsNode[], workPackage: WorkPackage) {
  const wbsName = workPackageWbsName(wbsCatalog, workPackage);
  const discipline =
    workPackage.discipline && workPackage.discipline !== "Multi-discipline" ? ` - ${workPackage.discipline}` : "";
  return `${workPackage.package_type} / ${wbsName}${discipline}`;
}

function humanizePackageText(text: string, wbsCatalog: WbsNode[], packages: WorkPackage[] = []) {
  if (!text) return "";
  let result = text;
  [...wbsCatalog]
    .filter((wbs) => wbs.code && wbs.name)
    .sort((left, right) => right.code.length - left.code.length)
    .forEach((wbs) => {
      result = result.split(wbs.code).join(wbs.name);
    });
  [...packages]
    .filter((workPackage) => workPackage.code && workPackage.title)
    .sort((left, right) => right.code.length - left.code.length)
    .forEach((workPackage) => {
      result = result.split(workPackage.code).join(workPackage.title);
    });
  return result;
}

function wbsTreeDisplay(node: WbsTreeNode, project: Project, depth: number) {
  const displayCode = publicWbsCode(node.code, project);
  if (depth === 0) {
    return {
      detail: project.code ? `Project ${project.code}` : "Project root",
      label: `${node.name || project.name} ${project.code}`,
      primary: node.name || project.name,
      secondary: project.code ? `Project ${project.code}` : "Project root",
    };
  }
  return {
    detail: node.code ? `WBS code ${displayCode}` : `Level ${node.level}`,
    label: node.name || node.code,
    primary: node.name || node.code,
    secondary: displayCode || `Level ${node.level}`,
  };
}

function emptyActivityWbsRollup(node: WbsTreeNode): ActivitySheetWbsRow {
  return {
    activity_count: 0,
    control_account_count: 0,
    needs_review_count: 0,
    planned_cost: 0,
    planned_value: 0,
    unmapped_activity_count: 0,
    wbs_code: node.code,
    wbs_name: node.name,
  };
}

function addActivityRollup(left: ActivitySheetWbsRow, right: ActivitySheetWbsRow): ActivitySheetWbsRow {
  return {
    ...left,
    activity_count: left.activity_count + right.activity_count,
    control_account_count: left.control_account_count + right.control_account_count,
    needs_review_count: left.needs_review_count + right.needs_review_count,
    planned_cost: left.planned_cost + right.planned_cost,
    planned_value: left.planned_value + right.planned_value,
    unmapped_activity_count: left.unmapped_activity_count + right.unmapped_activity_count,
  };
}

function buildActivityWbsRollupMap(
  nodes: WbsTreeNode[],
  directRowsByCode: Map<string, ActivitySheetWbsRow>
): Map<string, ActivitySheetWbsRow> {
  const rollups = new Map<string, ActivitySheetWbsRow>();
  const visit = (node: WbsTreeNode): ActivitySheetWbsRow => {
    const direct = directRowsByCode.get(node.code);
    let rollup = direct ? { ...direct } : emptyActivityWbsRollup(node);
    node.children.forEach((child) => {
      rollup = addActivityRollup(rollup, visit(child));
    });
    if (rollup.activity_count || rollup.planned_cost || rollup.planned_value) {
      rollups.set(node.code, rollup);
    }
    return rollup;
  };
  nodes.forEach(visit);
  return rollups;
}

function workPackageTechnicalCode(workPackage: WorkPackage) {
  return workPackage.code ? `Package ID: ${workPackage.code}` : "Package ID pending";
}

function importedWbsSuffix(code: string) {
  const trimmed = code.trim();
  const parts = trimmed.split("-").filter(Boolean);
  const firstNumericPart = parts.findIndex((part) => /^\d/.test(part));
  if (firstNumericPart >= 0) return parts.slice(firstNumericPart).join("-");
  return trimmed;
}

function hasImportedPmisPrefix(code: string) {
  return /p\s*[&-]\s*p?mis|pypmis|pmis/i.test(code);
}

function publicWbsCode(code: string | undefined, project: Project) {
  const trimmed = code?.trim() ?? "";
  if (!trimmed) return "WBS pending";
  if (project.code && (trimmed === project.code || trimmed.startsWith(`${project.code}-`))) return trimmed;
  if (!hasImportedPmisPrefix(trimmed)) return trimmed;
  const suffix = importedWbsSuffix(trimmed);
  return project.code ? `${project.code}-${suffix}` : suffix;
}

function publicControlAccountCode(code: string, project: Project) {
  const trimmed = code.trim();
  if (!trimmed) return "Control account pending";
  if (!hasImportedPmisPrefix(trimmed)) return trimmed;
  const accountPrefix = /^CA-/i.test(trimmed) ? "CA-" : "";
  const sourceWbsCode = accountPrefix ? trimmed.slice(3) : trimmed;
  return `${accountPrefix}${publicWbsCode(sourceWbsCode, project)}`;
}

function publicControlAccountName(name: string, wbsName: string, sourceCode: string) {
  if (hasImportedPmisPrefix(name) || hasImportedPmisPrefix(sourceCode)) {
    return wbsName && wbsName !== "Pending WBS assignment" ? `Control Account - ${wbsName}` : "Control Account";
  }
  return name;
}

function publicPackageCode(code: string | undefined, project: Project) {
  const trimmed = code?.trim() ?? "";
  if (!trimmed) return "AWP pending";
  const parts = trimmed.split("-").filter(Boolean);
  const pmisIndex = parts.findIndex((part, index) => {
    const current = part.toUpperCase();
    const next = parts[index + 1]?.toUpperCase();
    return (current === "P" && next === "PMIS") || current === "PYPMIS" || current === "PMIS";
  });
  if (pmisIndex < 0 || !project.code) return trimmed;
  const firstNumericPart = parts.findIndex((part, index) => index > pmisIndex && /^\d/.test(part));
  if (firstNumericPart < 0) return trimmed;
  return [...parts.slice(0, pmisIndex), project.code, ...parts.slice(firstNumericPart)].join("-");
}

function publicPackageTitle(
  title: string | undefined,
  project: Project,
  wbsName: string,
  sourceWbsCode: string,
  sourceControlAccountCode: string
) {
  const trimmed = title?.trim() ?? "";
  if (!trimmed) return "AWP pending";
  if (!hasImportedPmisPrefix(trimmed)) return trimmed;
  return trimmed
    .split(sourceControlAccountCode)
    .join(publicControlAccountCode(sourceControlAccountCode, project))
    .split(sourceWbsCode)
    .join(publicWbsCode(sourceWbsCode, project))
    .replace(/Control Account\s+CA-/i, "Control Account ")
    .replace(/Control Account\s+[^\s]+/i, wbsName ? `Control Account - ${wbsName}` : "Control Account");
}

function bimModelGeoreferenceMessage(model: BimModel) {
  const georef = model.model_identity?.georeferencing;
  if (!georef || typeof georef !== "object" || Array.isArray(georef)) return "";
  const record = georef as Record<string, unknown>;
  const latitude = typeof record.latitude_decimal === "number" ? record.latitude_decimal : Number.NaN;
  const longitude = typeof record.longitude_decimal === "number" ? record.longitude_decimal : Number.NaN;
  const crs = typeof record.projected_crs === "string" ? record.projected_crs.trim() : "";
  const coordinates =
    Number.isFinite(latitude) && Number.isFinite(longitude) ? `${latitude.toFixed(6)}, ${longitude.toFixed(6)}` : "";
  return [coordinates, crs].filter(Boolean).length
    ? ` Georreferenciacion detectada: ${[coordinates, crs].filter(Boolean).join(" / ")}.`
    : " Georreferenciacion detectada en el IFC.";
}

function isPathOfConstructionStep(workPackage: WorkPackage) {
  const packageType = workPackage.package_type.toUpperCase();
  return Boolean(workPackage.path_of_construction?.trim()) && (packageType === "CWA" || packageType === "CWP");
}

function isActiveControlAccount(account: ControlAccount) {
  return account.lifecycle_status.toLowerCase() !== "closed";
}

function buildWbsTraceabilityRows(
  project: Project,
  wbsCatalog: WbsNode[],
  controlAccounts: ControlAccount[],
  workPackages: WorkPackage[],
  integratedMatrix: IntegratedControlMatrixRow[],
  cbsCatalog: CostBreakdownStructure[],
  costCodes: CostCode[],
  fundingSources: FundingSource[]
): WbsTraceabilityRow[] {
  const wbsById = new Map(wbsCatalog.map((node) => [node.id, node]));
  const wbsByCode = new Map(wbsCatalog.map((node) => [node.code, node]));
  const cbsById = new Map(cbsCatalog.map((node) => [node.id, node]));
  const fundingById = new Map(fundingSources.map((source) => [source.id, source]));
  const accountRows = controlAccounts.filter(isActiveControlAccount).map((account) => {
    const wbs = account.wbs_id ? wbsById.get(account.wbs_id) : undefined;
    const matrixRow = integratedMatrix.find(
      (row) =>
        row.control_account_code === account.code ||
        (wbs ? row.wbs_code === wbs.code : false) ||
        row.cbs_code === account.cbs_code
    );
    const linkedPackage =
      workPackages.find(
        (workPackage) =>
          workPackage.control_account_id === account.id && workPackage.package_type.toUpperCase() === "CWP"
      ) ??
      workPackages.find((workPackage) => workPackage.control_account_id === account.id) ??
      (wbs ? workPackages.find((workPackage) => workPackage.wbs_id === wbs.id) : undefined);
    const linkedCostCode =
      costCodes.find((costCode) => costCode.control_account_id === account.id) ??
      (wbs ? costCodes.find((costCode) => costCode.wbs_id === wbs.id) : undefined);
    const cbsFromCostCode = linkedCostCode ? cbsById.get(linkedCostCode.cbs_id) : undefined;
    const fbsFromCostCode = linkedCostCode ? fundingById.get(linkedCostCode.fbs_id) : undefined;
    const sourceWbsCode = wbs?.code || matrixRow?.wbs_code || "WBS pending";
    const publicWbsName = wbs?.name || "Pending WBS assignment";

    return {
      awpPackageTitle: publicPackageTitle(linkedPackage?.title, project, publicWbsName, sourceWbsCode, account.code),
      id: `${account.id}-${wbs?.id ?? "pending"}`,
      wbsCode: publicWbsCode(sourceWbsCode, project),
      sourceWbsCode,
      wbsName: publicWbsName,
      controlAccountCode: publicControlAccountCode(account.code, project),
      sourceControlAccountCode: account.code,
      controlAccountName: publicControlAccountName(account.name, publicWbsName, account.code),
      cbsCode: matrixRow?.cbs_code || cbsFromCostCode?.code || account.cbs_code || "CBS pending",
      fbsCode: matrixRow?.fbs_code || fbsFromCostCode?.code || "FBS pending",
      awpPackageCode: publicPackageCode(linkedPackage?.code || matrixRow?.awp_package_code, project),
      costCode: matrixRow?.cost_code || linkedCostCode?.code || "Cost code pending",
      status: statusLabel(account.lifecycle_status || matrixRow?.status || "active"),
      budget: matrixRow?.budget ?? linkedCostCode?.budget ?? account.budget ?? 0,
    };
  });
  const hasAccountRowForMatrix = (matrixRow: IntegratedControlMatrixRow) =>
    accountRows.some(
      (row) =>
        (matrixRow.control_account_code && row.sourceControlAccountCode === matrixRow.control_account_code) ||
        (matrixRow.cost_code && row.costCode === matrixRow.cost_code) ||
        (matrixRow.wbs_code && row.sourceWbsCode === matrixRow.wbs_code && row.cbsCode === matrixRow.cbs_code)
    );
  const matrixRows = integratedMatrix
    .filter((matrixRow) => !hasAccountRowForMatrix(matrixRow))
    .map((matrixRow) => {
      const wbs = wbsByCode.get(matrixRow.wbs_code);
      const linkedPackage = workPackages.find((workPackage) => workPackage.code === matrixRow.awp_package_code);
      const publicWbsName = wbs?.name || matrixRow.wbs_code || "Pending WBS assignment";
      return {
        awpPackageTitle:
          publicPackageTitle(
            linkedPackage?.title,
            project,
            publicWbsName,
            matrixRow.wbs_code,
            matrixRow.control_account_code
          ) || publicPackageCode(matrixRow.awp_package_code, project),
        id: `matrix-${matrixRow.cost_code || matrixRow.control_account_code || matrixRow.wbs_code}`,
        wbsCode: publicWbsCode(matrixRow.wbs_code, project),
        sourceWbsCode: matrixRow.wbs_code || "WBS pending",
        wbsName: publicWbsName,
        controlAccountCode: publicControlAccountCode(matrixRow.control_account_code, project),
        sourceControlAccountCode: matrixRow.control_account_code || "Control account pending",
        controlAccountName: matrixRow.control_account_code
          ? `Formal CostCode link ${publicControlAccountCode(matrixRow.control_account_code, project)}`
          : "Control account pending",
        cbsCode: matrixRow.cbs_code || "CBS pending",
        fbsCode: matrixRow.fbs_code || "FBS pending",
        awpPackageCode: publicPackageCode(matrixRow.awp_package_code, project),
        costCode: matrixRow.cost_code || "Cost code pending",
        status: statusLabel(matrixRow.status || "active"),
        budget: matrixRow.budget ?? 0,
      };
    });
  return [...accountRows, ...matrixRows].sort(
    (left, right) =>
      left.wbsCode.localeCompare(right.wbsCode, undefined, { numeric: true }) ||
      left.controlAccountCode.localeCompare(right.controlAccountCode, undefined, { numeric: true })
  );
}

function buildCostFundingTraceabilityRows(
  traceabilityRows: WbsTraceabilityRow[],
  costLines: CostSheetLine[],
  fundingSources: FundingSource[],
  baselineOnly: boolean
): CostFundingTraceabilityRow[] {
  const costByControlAccount = new Map(costLines.map((line) => [line.control_account_code, line]));
  const fundingByCode = new Map(fundingSources.map((source) => [source.code, source]));
  const linkedControlAccounts = new Set<string>();

  const rows = traceabilityRows.map((row) => {
    const costLine =
      costByControlAccount.get(row.sourceControlAccountCode) ??
      costByControlAccount.get(row.controlAccountCode) ??
      costLines.find((line) => line.cbs_code && line.cbs_code === row.cbsCode);
    if (costLine) linkedControlAccounts.add(costLine.control_account_code);
    const funding = fundingByCode.get(row.fbsCode);

    return {
      ac: baselineOnly ? 0 : (costLine?.actual_cost ?? 0),
      bac: costLine?.bac ?? row.budget,
      cbsCode: costLine?.cbs_code || row.cbsCode,
      controlAccountCode: row.controlAccountCode,
      controlAccountName: row.controlAccountName,
      costCode: row.costCode,
      cpi: baselineOnly ? null : (costLine?.cpi ?? null),
      ev: baselineOnly ? 0 : (costLine?.earned_value ?? 0),
      fbsCode: row.fbsCode,
      fundingAmount: funding?.amount ?? 0,
      fundingName: funding?.name ?? (row.fbsCode === "FBS pending" ? "Funding pending" : "Funding source linked"),
      fundingStatus: funding ? statusLabel(funding.status) : "Pending",
      id: row.id,
      status: row.status,
      wbsCode: row.wbsCode,
      wbsName: row.wbsName,
    };
  });

  const unmatchedCostRows = costLines
    .filter((line) => !linkedControlAccounts.has(line.control_account_code))
    .map((line) => ({
      ac: baselineOnly ? 0 : line.actual_cost,
      bac: line.bac,
      cbsCode: line.cbs_code || "CBS pending",
      controlAccountCode: line.control_account_code,
      controlAccountName: line.control_account_name,
      costCode: "Cost code pending",
      cpi: baselineOnly ? null : line.cpi,
      ev: baselineOnly ? 0 : line.earned_value,
      fbsCode: "FBS pending",
      fundingAmount: 0,
      fundingName: "Funding pending",
      fundingStatus: "Pending",
      id: `cost-${line.control_account_id}`,
      status: "Cost line only",
      wbsCode: "WBS pending",
      wbsName: "Pending WBS assignment",
    }));

  return [...rows, ...unmatchedCostRows];
}

function AppShell() {
  const FRONTEND_VALIDATION_MODE = frontendValidationMode();
  const location = useLocation();
  const navigate = useNavigate();
  const { token, user, logout } = useAuthStore();
  const { dashboard, selectedProjectId, setDashboard, setSelectedProject } = useProjectStore();
  const [projectList, setProjectList] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [guidedFlow, setGuidedFlow] = useState<GuidedFlow | null>(null);
  const [processFlowBoard, setProcessFlowBoard] = useState<ProcessFlowBoard | null>(null);
  const [projectDrawerOpen, setProjectDrawerOpen] = useState(false);
  const [moduleNavigationCollapsed, setModuleNavigationCollapsed] = useState(false);
  const [applicationMode, setApplicationMode] = useState<ApplicationMode>("user");
  const [currencyAction, setCurrencyAction] = useState(false);
  const [projectDraft, setProjectDraft] = useState({
    calendar_base: "5x8 Colombia",
    code: "",
    control_level: "control_account",
    funding_required: true,
    authorization_date: "",
    authorization_ref: "",
    name: "",
    owner: "",
    phase: "Planning",
    currency: "USD",
    status: "draft",
    start_date: "",
    finish_date: "",
  });
  const [projectAction, setProjectAction] = useState(false);
  const [projectDeleteAction, setProjectDeleteAction] = useState(false);
  const [projectMessage, setProjectMessage] = useState<string | null>(null);
  const [projectError, setProjectError] = useState<string | null>(null);
  const [showProjectCreate, setShowProjectCreate] = useState(false);
  const [operationalSetup, setOperationalSetup] = useState<ProjectOperationalSetup | null>(null);
  const [activitySheets, setActivitySheets] = useState<ActivitySheet[]>([]);
  const [activitySheetRows, setActivitySheetRows] = useState<ActivitySheetRow[]>([]);
  const [activitySheetWbsRows, setActivitySheetWbsRows] = useState<ActivitySheetWbsRow[]>([]);
  const [scheduleActivities, setScheduleActivities] = useState<ScheduleActivityMap[]>([]);
  const [scheduleRelationships, setScheduleRelationships] = useState<ScheduleRelationship[]>([]);
  const [quantityTakeoffRuns, setQuantityTakeoffRuns] = useState<QuantityTakeoffRun[]>([]);
  const [quantityTakeoffLines, setQuantityTakeoffLines] = useState<QuantityTakeoffLine[]>([]);
  const [geometryMeasurementBatch, setGeometryMeasurementBatch] = useState<BimGeometryMeasurementBatch | null>(null);
  const [bimQuantityRules, setBimQuantityRules] = useState<BimQuantityRule[]>([]);
  const [quantityRuleRecalculation, setQuantityRuleRecalculation] = useState<QuantityRuleRecalculation | null>(null);
  const [colombiaApuCatalog, setColombiaApuCatalog] = useState<ColombiaApuCatalogItem[]>([]);
  const [colombiaApuSync, setColombiaApuSync] = useState<ColombiaApuCatalogSync | null>(null);
  const [colombiaApuSearch, setColombiaApuSearch] = useState("");
  const [colombiaApuSource, setColombiaApuSource] = useState("");
  const [claimsAuditFiles, setClaimsAuditFiles] = useState<File[]>([]);
  const [claimsAuditMode, setClaimsAuditMode] = useState("review");
  const [claimsAuditResult, setClaimsAuditResult] = useState<ForensicDossierAnalysis | null>(null);
  const [claimsAuditAction, setClaimsAuditAction] = useState(false);
  const [claimsAuditMessage, setClaimsAuditMessage] = useState<string | null>(null);
  const [claimsAuditError, setClaimsAuditError] = useState<string | null>(null);
  const [windowAnalysisFiles, setWindowAnalysisFiles] = useState<File[]>([]);
  const [windowAnalysisThreshold, setWindowAnalysisThreshold] = useState(10);
  const [windowAnalysisResult, setWindowAnalysisResult] = useState<ForensicWindowAnalysis | null>(null);
  const [windowAnalysisRagSources, setWindowAnalysisRagSources] = useState<ForensicRagSource[]>([]);
  const [windowAnalysisAction, setWindowAnalysisAction] = useState(false);
  const [windowAnalysisMessage, setWindowAnalysisMessage] = useState<string | null>(null);
  const [windowAnalysisError, setWindowAnalysisError] = useState<string | null>(null);
  const [bimModelRuns, setBimModelRuns] = useState<BimModel[]>([]);
  const [setupDraft, setSetupDraft] = useState({
    project_number: "",
    setup_template: "Capital Project Controls Template",
    attribute_form: "Project Attribute Form",
    permissions_configured: true,
    modules_configured: true,
    cost_sheet_ready: true,
    funding_sheet_ready: true,
    p6_mapping_ready: true,
    status: "ready",
  });
  const [setupAction, setSetupAction] = useState(false);
  const [setupMessage, setSetupMessage] = useState<string | null>(null);
  const [setupError, setSetupError] = useState<string | null>(null);
  const [activityAction, setActivityAction] = useState(false);
  const [quantityAction, setQuantityAction] = useState(false);
  const [quantityMessage, setQuantityMessage] = useState<string | null>(null);
  const [quantityError, setQuantityError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [users, setUsers] = useState<User[]>([]);
  const [roles, setRoles] = useState<RoleProfile[]>([]);
  const [userDraft, setUserDraft] = useState({
    email: "",
    full_name: "",
    password: "1234",
    role: "Control Manager",
    title: "",
  });
  const [selectedIamUserId, setSelectedIamUserId] = useState("");
  const [managedUserDraft, setManagedUserDraft] = useState(emptyManagedUserDraft);
  const [userAction, setUserAction] = useState(false);
  const [iamAction, setIamAction] = useState<"update" | "reset" | "assign" | "remove" | "deactivate" | null>(null);
  const [userMessage, setUserMessage] = useState<string | null>(null);
  const [userError, setUserError] = useState<string | null>(null);
  const [integratedMatrix, setIntegratedMatrix] = useState<IntegratedControlMatrixRow[]>([]);
  const [forecastFunding, setForecastFunding] = useState<ForecastFundingReport | null>(null);
  const [closeoutReport, setCloseoutReport] = useState<CloseoutReport | null>(null);
  const [wbsCatalog, setWbsCatalog] = useState<WbsNode[]>([]);
  const [wbsDraft, setWbsDraft] = useState({
    parent_id: "",
    code: "",
    name: "",
    level: "1",
    description: "",
    dictionary: "",
    responsible: "",
    status: "active",
  });
  const [wbsAction, setWbsAction] = useState(false);
  const [controlAccounts, setControlAccounts] = useState<ControlAccount[]>([]);
  const [cbsCatalog, setCbsCatalog] = useState<CostBreakdownStructure[]>([]);
  const [costCodes, setCostCodes] = useState<CostCode[]>([]);
  const [rateSheets, setRateSheets] = useState<RateSheet[]>([]);
  const [reconciliationReport, setReconciliationReport] = useState<ReconciliationReport | null>(null);
  const [bpPolicies, setBpPolicies] = useState<BusinessProcessPolicy[]>([]);
  const [bpLineItems, setBpLineItems] = useState<BusinessProcessLineItem[]>([]);
  const [bpLineItemRevisions, setBpLineItemRevisions] = useState<BusinessProcessLineItemRevision[]>([]);
  const [recostRuns, setRecostRuns] = useState<ActivitySheetRecostRun[]>([]);
  const [controlAgentRuns, setControlAgentRuns] = useState<ControlAgentRun[]>([]);
  const [integratedError, setIntegratedError] = useState<string | null>(null);
  const [fbsDraft, setFbsDraft] = useState({
    code: "",
    source_of_funds: "",
    funding_type: "AFE",
    authorization_ref: "",
    approved_amount: "",
    currency: "USD",
    status: "approved",
  });
  const [fbsAction, setFbsAction] = useState(false);
  const [cbsDraft, setCbsDraft] = useState({
    code: "",
    level: "3",
    cost_category: "",
    description: "",
    status: "active",
  });
  const [priorityDraft, setPriorityDraft] = useState({
    wbs_id: "",
    control_account_id: "",
    cbs_id: "",
    funding_source_id: "",
    amount: "",
    quantity: "",
    description: "",
  });
  const [sovDraft, setSovDraft] = useState({
    contract_id: "",
    line_no: "10",
    description: "",
    amount: "",
  });
  const [rateDraft, setRateDraft] = useState({
    code: "",
    name: "",
    cbs_code: "",
    multiplier: "1.0",
    unit_rate: "0",
  });
  const [policyDraft, setPolicyDraft] = useState({
    process_code: "BP-CBS-WBS",
    action: "approve_baseline",
    required_role: "Control Manager",
    permission_key: "can_approve_workflow",
  });
  const [lineEditDraft, setLineEditDraft] = useState({
    line_item_id: "",
    amount: "",
    quantity: "",
    description: "",
    change_note: "Controlled production edit",
  });
  const [priorityAction, setPriorityAction] = useState<"cbs" | "fund" | "wbs" | "sov" | "rate" | "recost" | null>(null);
  const [hardeningAction, setHardeningAction] = useState<"policy" | "line" | "export-xlsx" | "export-pdf" | null>(null);
  const [agentAction, setAgentAction] = useState(false);
  const [constraintAction, setConstraintAction] = useState(false);
  const [baselineAction, setBaselineAction] = useState(false);
  const [integratedMessage, setIntegratedMessage] = useState<string | null>(null);
  const [activeControlView, setActiveControlView] = useState<ControlFlowView>(
    () => routeControlView(location.pathname) ?? "dashboard"
  );
  const routedControlView = routeControlView(location.pathname);
  const requestedControlView =
    routedControlView ?? (activeControlView === "schedule-control" ? "dashboard" : activeControlView);
  const visibleControlView = FRONTEND_VALIDATION_MODE ? focusedControlView(requestedControlView) : requestedControlView;
  const [constraintDraft, setConstraintDraft] = useState({
    work_package_id: "",
    constraint_type: "Engineering Documents",
    description: "",
    owner_role: "Workface Planner",
    required_by: "",
    priority: "medium",
    evidence_ref: "",
    blocking: true,
  });

  useEffect(() => {
    let cancelled = false;
    async function loadProjects() {
      setLoading(true);
      setError(null);
      try {
        const records = await projectsApi.list(token);
        if (cancelled) return;
        setProjectList(records);
        const selectedStillVisible = selectedProjectId
          ? records.some((record) => record.id === selectedProjectId)
          : false;
        const nextProjectId = selectedStillVisible ? selectedProjectId : (records[0]?.id ?? null);
        if (nextProjectId) {
          setSelectedProject(nextProjectId);
        } else {
          if (selectedProjectId !== null) {
            setSelectedProject(null);
          }
          setDashboard(null);
          setGuidedFlow(null);
          setProcessFlowBoard(null);
          setLoading(false);
        }
      } catch (err) {
        if (!cancelled) {
          if (isUnauthorizedApiError(err)) {
            logout();
            return;
          }
          setError(err instanceof Error ? err.message : "Could not load projects");
          setLoading(false);
        }
      }
    }
    loadProjects();
    return () => {
      cancelled = true;
    };
  }, [token, selectedProjectId, setDashboard, setSelectedProject, logout]);

  useEffect(() => {
    if (!selectedProjectId) return;
    const projectId = selectedProjectId;
    let cancelled = false;
    async function loadDashboard() {
      setLoading(true);
      setError(null);
      try {
        const [nextDashboard, flow, processBoard, importedActivities, importedRelationships] = await Promise.all([
          dashboardApi.get(token, projectId),
          projectsApi.guidedFlow(token, projectId),
          projectsApi.processFlowBoard(token, projectId),
          projectsApi.scheduleActivities(token, projectId).catch(() => []),
          projectsApi.scheduleRelationships(token, projectId).catch(() => []),
        ]);
        if (!cancelled) {
          setDashboard(nextDashboard);
          setGuidedFlow(flow);
          setProcessFlowBoard(processBoard);
          setScheduleActivities(importedActivities);
          setScheduleRelationships(importedRelationships);
          setLoading(false);
          const firstFunding = nextDashboard.funding_sources?.[0];
          const firstContract = nextDashboard.contracts?.[0];
          setPriorityDraft((current) => ({
            ...current,
            funding_source_id: current.funding_source_id || (firstFunding ? String(firstFunding.id) : ""),
          }));
          setSovDraft((current) => ({
            ...current,
            contract_id: current.contract_id || (firstContract ? String(firstContract.id) : ""),
          }));
        }
        const businessProcesses = nextDashboard.business_processes ?? [];
        const priorityProcess =
          businessProcesses.find((process) => process.process_code === "BP-CBS-WBS") ??
          businessProcesses.find((process) => process.process_code === "BP-CBS-FUND");
        if (priorityProcess) {
          const lineItems = await integratedControlApi
            .businessProcessLineItems(token, projectId, priorityProcess.id)
            .catch(() => []);
          const revisions = lineItems[0]
            ? await integratedControlApi
                .businessProcessLineItemRevisions(token, projectId, lineItems[0].id)
                .catch(() => [])
            : [];
          if (!cancelled) {
            setBpLineItems(lineItems);
            setBpLineItemRevisions(revisions);
            const selectedLine = lineItems[0];
            if (selectedLine) {
              setLineEditDraft((current) => ({
                ...current,
                line_item_id: String(selectedLine.id),
                amount: String(selectedLine.amount),
                quantity: String(selectedLine.quantity),
                description: selectedLine.description,
              }));
            }
          }
        } else if (!cancelled) {
          setBpLineItems([]);
          setBpLineItemRevisions([]);
        }
      } catch (err) {
        if (!cancelled) {
          if (isUnauthorizedApiError(err)) {
            logout();
            return;
          }
          setError(err instanceof Error ? err.message : "Could not load dashboard");
          setLoading(false);
        }
      }
    }
    loadDashboard();
    return () => {
      cancelled = true;
    };
  }, [token, selectedProjectId, setDashboard, logout]);

  useEffect(() => {
    if (!selectedProjectId) return;
    const projectId = selectedProjectId;
    let cancelled = false;
    async function loadWindowAnalysisRagSources() {
      try {
        const sources = await integratedControlApi.windowAnalysis37RagSources(token, projectId);
        if (!cancelled) {
          setWindowAnalysisRagSources(sources);
        }
      } catch {
        if (!cancelled) {
          setWindowAnalysisRagSources([]);
        }
      }
    }
    loadWindowAnalysisRagSources();
    return () => {
      cancelled = true;
    };
  }, [token, selectedProjectId]);

  useEffect(() => {
    if (!selectedProjectId) return;
    const projectId = selectedProjectId;
    let cancelled = false;
    async function loadIntegratedControl() {
      setIntegratedError(null);
      try {
        const [
          matrix,
          forecast,
          closeout,
          wbsRows,
          accounts,
          cbsRows,
          codeRows,
          sheets,
          reconciliation,
          policies,
          agentRuns,
        ] = await Promise.all([
          integratedControlApi.matrix(token, projectId),
          integratedControlApi.forecastVsFunding(token, projectId),
          integratedControlApi.closeoutReport(token, projectId),
          integratedControlApi.wbs(token, projectId),
          integratedControlApi.controlAccounts(token, projectId),
          integratedControlApi.cbs(token, projectId),
          integratedControlApi.costCodes(token, projectId),
          integratedControlApi.rateSheets(token, projectId),
          integratedControlApi.reconciliationReport(token, projectId),
          integratedControlApi.businessProcessPolicies(token, projectId),
          integratedControlApi.controlAuditAgentRuns(token, projectId).catch(() => []),
        ]);
        if (!cancelled) {
          setIntegratedMatrix(matrix);
          setForecastFunding(forecast);
          setCloseoutReport(closeout);
          setWbsCatalog(wbsRows);
          setControlAccounts(accounts);
          setCbsCatalog(cbsRows);
          setCostCodes(codeRows);
          setRateSheets(sheets);
          setReconciliationReport(reconciliation);
          setBpPolicies(policies);
          setControlAgentRuns(agentRuns);
          const firstAccount = accounts.find(isActiveControlAccount) ?? accounts[0];
          const accountWbs = firstAccount?.wbs_id ? wbsRows.find((item) => item.id === firstAccount.wbs_id) : undefined;
          const firstWbs = accountWbs ?? wbsRows.find((item) => item.code !== "1.0") ?? wbsRows[0];
          const firstCbs = cbsRows[0];
          setPriorityDraft((current) => ({
            ...current,
            wbs_id: current.wbs_id || (firstWbs ? String(firstWbs.id) : ""),
            control_account_id: current.control_account_id || (firstAccount ? String(firstAccount.id) : ""),
            cbs_id: current.cbs_id || (firstCbs ? String(firstCbs.id) : ""),
          }));
          setRateDraft((current) => ({
            ...current,
            cbs_code: current.cbs_code || firstCbs?.code || "",
          }));
        }
      } catch (err) {
        if (!cancelled) {
          if (isUnauthorizedApiError(err)) {
            logout();
            return;
          }
          setIntegratedError(err instanceof Error ? err.message : "Could not load integrated control data");
        }
      }
    }
    loadIntegratedControl();
    return () => {
      cancelled = true;
    };
  }, [token, selectedProjectId, logout]);

  useEffect(() => {
    if (!selectedProjectId) return;
    const projectId = selectedProjectId;
    let cancelled = false;
    async function loadOperationalSetup() {
      setSetupError(null);
      try {
        const setupPromise = projectsApi.operationalSetup(token, projectId).catch((err: unknown) => {
          if (err instanceof ApiError && err.status === 404) return null;
          throw err;
        });
        const [setup, sheets, quantityRuns, bimModels, quantityRules, apuCatalog] = await Promise.all([
          setupPromise,
          projectsApi.activitySheets(token, projectId),
          projectsApi.quantityTakeoffRuns(token, projectId).catch(() => []),
          bimModelsApi.list(token, projectId).catch(() => []),
          projectsApi.bimQuantityRules(token, projectId).catch(() => []),
          projectsApi.colombiaApuCatalog(token, projectId).catch(() => []),
        ]);
        const latestSheet = sheets[0];
        const [wbsRows, detailRows] = latestSheet
          ? await Promise.all([
              projectsApi.activitySheetWbsRows(token, projectId, latestSheet.id).catch(() => []),
              projectsApi.activitySheetRows(token, projectId, latestSheet.id).catch(() => []),
            ])
          : [[], []];
        const latestQuantityRun = quantityRuns[0];
        const quantityRows = latestQuantityRun
          ? await projectsApi.quantityTakeoffLines(token, projectId, latestQuantityRun.id).catch(() => [])
          : [];
        if (cancelled) return;
        setOperationalSetup(setup);
        setActivitySheets(sheets);
        setActivitySheetWbsRows(wbsRows);
        setActivitySheetRows(detailRows);
        setQuantityTakeoffRuns(quantityRuns);
        setQuantityTakeoffLines(quantityRows);
        setGeometryMeasurementBatch(null);
        setBimQuantityRules(quantityRules);
        setColombiaApuCatalog(apuCatalog);
        setColombiaApuSync(null);
        setQuantityRuleRecalculation(null);
        setBimModelRuns(bimModels);
        setRecostRuns([]);
        if (latestSheet) {
          const firstActivityCbs = detailRows[0]?.cbs_code;
          if (firstActivityCbs) {
            setRateDraft((current) => ({ ...current, cbs_code: current.cbs_code || firstActivityCbs }));
          }
          integratedControlApi
            .recostRuns(token, projectId, latestSheet.id)
            .then((history) => {
              if (!cancelled) setRecostRuns(history);
            })
            .catch(() => undefined);
        }
        const selectedProject = projectList.find((item) => item.id === projectId);
        setSetupDraft({
          project_number: setup?.project_number || selectedProject?.code || "",
          setup_template: setup?.setup_template || "Capital Project Controls Template",
          attribute_form: setup?.attribute_form || "Project Attribute Form",
          permissions_configured: setup?.permissions_configured ?? true,
          modules_configured: setup?.modules_configured ?? true,
          cost_sheet_ready: setup?.cost_sheet_ready ?? true,
          funding_sheet_ready: setup?.funding_sheet_ready ?? true,
          p6_mapping_ready: setup?.p6_mapping_ready ?? true,
          status: setup?.status || "ready",
        });
      } catch (err) {
        if (!cancelled) {
          if (isUnauthorizedApiError(err)) {
            logout();
            return;
          }
          setSetupError(err instanceof Error ? err.message : "Could not load project setup");
          setActivitySheetWbsRows([]);
          setActivitySheetRows([]);
          setQuantityTakeoffRuns([]);
          setQuantityTakeoffLines([]);
          setGeometryMeasurementBatch(null);
          setBimQuantityRules([]);
          setColombiaApuCatalog([]);
          setColombiaApuSync(null);
          setQuantityRuleRecalculation(null);
          setBimModelRuns([]);
        }
      }
    }
    loadOperationalSetup();
    return () => {
      cancelled = true;
    };
  }, [token, selectedProjectId, projectList, logout]);

  useEffect(() => {
    let cancelled = false;
    async function loadAdminData() {
      try {
        const [nextUsers, nextRoles] = await Promise.all([adminApi.listUsers(token), adminApi.listRoles(token)]);
        if (!cancelled) {
          const selectedUser = nextUsers[0];
          setUsers(nextUsers);
          setRoles(nextRoles);
          setSelectedIamUserId(selectedUser ? String(selectedUser.id) : "");
          setManagedUserDraft(managedDraftForUser(selectedUser));
          setUserDraft((current) => ({
            ...current,
            role: nextRoles.some((role) => role.role === current.role)
              ? current.role
              : nextRoles[0]?.role || current.role,
          }));
        }
      } catch (err) {
        if (!cancelled) {
          if (isUnauthorizedApiError(err)) {
            logout();
            return;
          }
          setUserError(err instanceof Error ? err.message : "Could not load users and roles");
        }
      }
    }
    loadAdminData();
    return () => {
      cancelled = true;
    };
  }, [token, logout]);

  async function refreshGuidedFlow(projectId: number) {
    const [flow, processBoard] = await Promise.all([
      projectsApi.guidedFlow(token, projectId),
      projectsApi.processFlowBoard(token, projectId),
    ]);
    setGuidedFlow(flow);
    setProcessFlowBoard(processBoard);
  }

  async function refreshDashboard(projectId: number) {
    const [nextDashboard, importedActivities, importedRelationships] = await Promise.all([
      dashboardApi.get(token, projectId),
      projectsApi.scheduleActivities(token, projectId).catch(() => []),
      projectsApi.scheduleRelationships(token, projectId).catch(() => []),
    ]);
    setDashboard(nextDashboard);
    setScheduleActivities(importedActivities);
    setScheduleRelationships(importedRelationships);
    const firstFunding = nextDashboard.funding_sources?.[0];
    const firstContract = nextDashboard.contracts?.[0];
    setPriorityDraft((current) => ({
      ...current,
      funding_source_id: current.funding_source_id || (firstFunding ? String(firstFunding.id) : ""),
    }));
    setSovDraft((current) => ({
      ...current,
      contract_id: current.contract_id || (firstContract ? String(firstContract.id) : ""),
    }));
    await refreshGuidedFlow(projectId);
  }

  async function refreshIntegratedControl(projectId: number) {
    const [
      matrix,
      forecast,
      closeout,
      wbsRows,
      accounts,
      cbsRows,
      codeRows,
      sheets,
      reconciliation,
      policies,
      agentRuns,
    ] = await Promise.all([
      integratedControlApi.matrix(token, projectId),
      integratedControlApi.forecastVsFunding(token, projectId),
      integratedControlApi.closeoutReport(token, projectId),
      integratedControlApi.wbs(token, projectId),
      integratedControlApi.controlAccounts(token, projectId),
      integratedControlApi.cbs(token, projectId),
      integratedControlApi.costCodes(token, projectId),
      integratedControlApi.rateSheets(token, projectId),
      integratedControlApi.reconciliationReport(token, projectId),
      integratedControlApi.businessProcessPolicies(token, projectId),
      integratedControlApi.controlAuditAgentRuns(token, projectId).catch(() => []),
    ]);
    setIntegratedMatrix(matrix);
    setForecastFunding(forecast);
    setCloseoutReport(closeout);
    setWbsCatalog(wbsRows);
    setControlAccounts(accounts);
    setCbsCatalog(cbsRows);
    setCostCodes(codeRows);
    setRateSheets(sheets);
    setReconciliationReport(reconciliation);
    setBpPolicies(policies);
    setControlAgentRuns(agentRuns);
    const firstAccount = accounts.find(isActiveControlAccount) ?? accounts[0];
    const accountWbs = firstAccount?.wbs_id ? wbsRows.find((item) => item.id === firstAccount.wbs_id) : undefined;
    const firstWbs = accountWbs ?? wbsRows.find((item) => item.code !== "1.0") ?? wbsRows[0];
    const firstCbs = cbsRows[0];
    setPriorityDraft((current) => ({
      ...current,
      wbs_id: current.wbs_id || (firstWbs ? String(firstWbs.id) : ""),
      control_account_id: current.control_account_id || (firstAccount ? String(firstAccount.id) : ""),
      cbs_id: current.cbs_id || (firstCbs ? String(firstCbs.id) : ""),
    }));
    setRateDraft((current) => ({
      ...current,
      cbs_code: current.cbs_code || firstCbs?.code || "",
    }));
  }

  async function refreshProcessLineItems(projectId: number, processId: number, preferredLineId?: number) {
    const lines = await integratedControlApi.businessProcessLineItems(token, projectId, processId);
    const selectedLine = lines.find((line) => line.id === preferredLineId) ?? lines[0];
    const revisions = selectedLine
      ? await integratedControlApi.businessProcessLineItemRevisions(token, projectId, selectedLine.id)
      : [];
    setBpLineItems(lines);
    setBpLineItemRevisions(revisions);
    if (selectedLine) {
      setLineEditDraft((current) => ({
        ...current,
        line_item_id: String(selectedLine.id),
        amount: String(selectedLine.amount),
        quantity: String(selectedLine.quantity),
        description: selectedLine.description,
      }));
    }
  }

  async function handleProjectCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setProjectAction(true);
    setProjectError(null);
    setProjectMessage(null);
    try {
      const created = await projectsApi.create(token, {
        code: projectDraft.code.trim(),
        name: projectDraft.name.trim(),
        phase: projectDraft.phase,
        currency: projectDraft.currency.trim().toUpperCase() || "USD",
        calendar_base: projectDraft.calendar_base.trim(),
        owner: projectDraft.owner.trim(),
        status: projectDraft.status,
        authorization_date: projectDraft.authorization_date || null,
        authorization_ref: projectDraft.authorization_ref.trim(),
        configuration: {
          control_level: projectDraft.control_level,
          funding_required: projectDraft.funding_required,
        },
        start_date: projectDraft.start_date || null,
        finish_date: projectDraft.finish_date || null,
      });
      setProjectList((current) =>
        current.some((projectItem) => projectItem.id === created.id)
          ? current.map((projectItem) => (projectItem.id === created.id ? created : projectItem))
          : [...current, created]
      );
      setSelectedProject(created.id);
      setProjectDraft({
        calendar_base: created.calendar_base || "5x8 Colombia",
        code: "",
        control_level: "control_account",
        funding_required: true,
        authorization_date: "",
        authorization_ref: "",
        name: "",
        owner: "",
        phase: "Planning",
        currency: created.currency || "USD",
        status: "draft",
        start_date: "",
        finish_date: "",
      });
      setShowProjectCreate(false);
      setProjectDrawerOpen(false);
      setProjectMessage(`Project ${created.code} created and selected.`);
    } catch (err) {
      setProjectError(err instanceof Error ? err.message : "Could not create project");
    } finally {
      setProjectAction(false);
    }
  }

  async function handleProjectDelete() {
    if (!selectedProjectId || !dashboard) return;
    const projectToDelete = dashboard.project;
    const confirmed = window.confirm(
      `Delete project ${projectToDelete.code}? This will remove the project workspace and its control records.`
    );
    if (!confirmed) return;
    setProjectDeleteAction(true);
    setProjectError(null);
    setProjectMessage(null);
    try {
      await projectsApi.deleteProject(token, selectedProjectId);
      const remainingProjects = projectList.filter((item) => item.id !== selectedProjectId);
      setProjectList(remainingProjects);
      const nextProjectId = remainingProjects[0]?.id ?? null;
      setProjectMessage(`Project ${projectToDelete.code} deleted.`);
      if (nextProjectId) {
        setSelectedProject(nextProjectId);
      } else {
        setSelectedProject(null);
        setDashboard(null);
        setScheduleActivities([]);
        setScheduleRelationships([]);
        setGuidedFlow(null);
        setProcessFlowBoard(null);
        setLoading(false);
      }
    } catch (err) {
      if (isUnauthorizedApiError(err)) {
        logout();
        return;
      }
      setProjectError(err instanceof Error ? err.message : "Could not delete project");
    } finally {
      setProjectDeleteAction(false);
    }
  }

  async function handleScheduleUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file || !selectedProjectId) return;
    setUploading(true);
    setUploadError(null);
    setUploadMessage(null);
    try {
      await projectsApi.uploadSchedule(token, selectedProjectId, file);
      await refreshDashboard(selectedProjectId);
      setUploadMessage(`${file.name} uploaded. Data Quality Gate refreshed.`);
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : "Could not upload schedule");
    } finally {
      setUploading(false);
      event.target.value = "";
    }
  }

  async function handleConfirmCurrency(currency: string) {
    const scheduleImportId = dashboard?.schedule_import?.id;
    if (!selectedProjectId || !scheduleImportId) return;
    setCurrencyAction(true);
    setIntegratedError(null);
    try {
      await projectsApi.confirmScheduleCurrency(token, selectedProjectId, scheduleImportId, currency);
      await refreshDashboard(selectedProjectId);
      setIntegratedMessage(`Schedule currency ${currency} confirmed.`);
    } catch (err) {
      setIntegratedError(err instanceof Error ? err.message : "Could not confirm schedule currency");
    } finally {
      setCurrencyAction(false);
    }
  }

  async function handleOperationalSetupSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId) return;
    setSetupAction(true);
    setSetupError(null);
    setSetupMessage(null);
    try {
      const updated = await projectsApi.updateOperationalSetup(token, selectedProjectId, {
        ...setupDraft,
        expected_version: operationalSetup?.version,
      });
      setOperationalSetup(updated);
      setSetupMessage(`Project setup ${statusLabel(updated.readiness_status)}.`);
    } catch (err) {
      setSetupError(err instanceof Error ? err.message : "Could not update project setup");
    } finally {
      setSetupAction(false);
    }
  }

  async function handleActivitySheetUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file || !selectedProjectId) return;
    setActivityAction(true);
    setSetupError(null);
    setSetupMessage(null);
    try {
      if (operationalSetup?.readiness_status !== "ready") {
        if (!isSetupDraftReady(setupDraft)) {
          throw new Error("Complete Asset Creator/Receipt before loading activity data");
        }
        const updatedSetup = await projectsApi.updateOperationalSetup(token, selectedProjectId, {
          ...setupDraft,
          expected_version: operationalSetup?.version,
        });
        setOperationalSetup(updatedSetup);
        if (updatedSetup.readiness_status !== "ready") {
          throw new Error(`Project operational setup is not ready: ${updatedSetup.readiness_notes}`);
        }
      }
      const created = await projectsApi.loadActivitySheetData(token, selectedProjectId, file);
      const [sheets, wbsRows, detailRows] = await Promise.all([
        projectsApi.activitySheets(token, selectedProjectId),
        projectsApi.activitySheetWbsRows(token, selectedProjectId, created.id),
        projectsApi.activitySheetRows(token, selectedProjectId, created.id),
      ]);
      await refreshDashboard(selectedProjectId);
      await refreshIntegratedControl(selectedProjectId);
      setActivitySheets(sheets);
      setActivitySheetWbsRows(wbsRows);
      setActivitySheetRows(detailRows);
      setRecostRuns([]);
      setSetupMessage(`Activity data loaded from ${created.source_file_name}.`);
    } catch (err) {
      setSetupError(err instanceof Error ? err.message : "Could not load activity data");
    } finally {
      setActivityAction(false);
      event.target.value = "";
    }
  }

  async function handleQuantityTakeoffUpload(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file || !selectedProjectId) return;
    setSetupError(null);
    setSetupMessage(null);
    setQuantityError(null);
    setQuantityMessage(null);
    setQuantityRuleRecalculation(null);
    setGeometryMeasurementBatch(null);
    setQuantityAction(true);
    try {
      if (isIfcModel(file)) {
        const registeredModel = await bimModelsApi.upload(token, selectedProjectId, file);
        if (file.size > BIM_TAKEOFF_MAX_BYTES) {
          setBimModelRuns((current) => [registeredModel, ...current.filter((item) => item.id !== registeredModel.id)]);
          setQuantityTakeoffRuns([]);
          setQuantityTakeoffLines([]);
          setGeometryMeasurementBatch(null);
          setQuantityRuleRecalculation(null);
          setQuantityMessage(
            `${file.name} quedo registrado para coordinacion BIM.${bimModelGeoreferenceMessage(registeredModel)} El archivo supera ${BIM_TAKEOFF_MAX_MB} MB, por eso se omitio el takeoff sincrono; carga una exportacion IFC de cantidades o Excel/CSV para la tabla controlada.`
          );
          return;
        }
        try {
          const created = await projectsApi.loadQuantityTakeoff(token, selectedProjectId, file, registeredModel.id);
          const [runs, lines] = await Promise.all([
            projectsApi.quantityTakeoffRuns(token, selectedProjectId),
            projectsApi.quantityTakeoffLines(token, selectedProjectId, created.id),
          ]);
          setQuantityTakeoffRuns(runs);
          setQuantityTakeoffLines(lines);
          setBimModelRuns((current) => [registeredModel, ...current.filter((item) => item.id !== registeredModel.id)]);
          setGeometryMeasurementBatch(null);
          setQuantityRuleRecalculation(null);
          setQuantityMessage(
            `${registeredModel.source_file_name} quedo registrado como modelo IFC y se cargaron ${lines.length} linea(s) de cantidades.${bimModelGeoreferenceMessage(registeredModel)}`
          );
        } catch (err) {
          if (isUnauthorizedApiError(err)) {
            logout();
            return;
          }
          setQuantityTakeoffRuns([]);
          setQuantityTakeoffLines([]);
          setBimModelRuns((current) => [registeredModel, ...current.filter((item) => item.id !== registeredModel.id)]);
          setGeometryMeasurementBatch(null);
          setQuantityRuleRecalculation(null);
          setQuantityMessage(
            `${registeredModel.source_file_name} quedo registrado para coordinacion BIM.${bimModelGeoreferenceMessage(registeredModel)} La extraccion de cantidades no termino; carga una exportacion IFC de cantidades o Excel/CSV para la tabla controlada.`
          );
          setQuantityError(quantityTakeoffErrorMessage(err));
        }
        return;
      }
      const created = await projectsApi.loadQuantityTakeoff(token, selectedProjectId, file);
      const [runs, lines] = await Promise.all([
        projectsApi.quantityTakeoffRuns(token, selectedProjectId),
        projectsApi.quantityTakeoffLines(token, selectedProjectId, created.id),
      ]);
      setQuantityTakeoffRuns(runs);
      setQuantityTakeoffLines(lines);
      setGeometryMeasurementBatch(null);
      setQuantityRuleRecalculation(null);
      setQuantityMessage(`Quantity takeoff loaded from ${created.source_file_name}.`);
    } catch (err) {
      if (isUnauthorizedApiError(err)) {
        logout();
        return;
      }
      setQuantityError(quantityTakeoffErrorMessage(err));
    } finally {
      setQuantityAction(false);
      event.target.value = "";
    }
  }

  async function handleQuantityTakeoffClear() {
    if (!selectedProjectId) return;
    setQuantityAction(true);
    setQuantityError(null);
    try {
      const latestModel = bimModelRuns[0];
      if (latestModel) {
        await bimModelsApi.remove(token, selectedProjectId, latestModel.id);
        setBimModelRuns((current) => current.filter((item) => item.id !== latestModel.id));
      }
      setQuantityTakeoffRuns([]);
      setQuantityTakeoffLines([]);
      setGeometryMeasurementBatch(null);
      setQuantityRuleRecalculation(null);
      setQuantityMessage("Modelo IFC y tabla local despejados. Puedes cargar otro IFC, Excel o CSV.");
    } catch (err) {
      if (isUnauthorizedApiError(err)) {
        logout();
        return;
      }
      setQuantityError(apiErrorDetail(err) || "No se pudo limpiar el modelo BIM cargado");
    } finally {
      setQuantityAction(false);
    }
  }

  async function handleBimQuantityRuleUpdate(ruleId: number, payload: BimQuantityRuleUpdate) {
    if (!selectedProjectId) return;
    setQuantityAction(true);
    setQuantityError(null);
    setQuantityMessage(null);
    try {
      const updated = await projectsApi.updateBimQuantityRule(token, selectedProjectId, ruleId, payload);
      setBimQuantityRules((current) => current.map((rule) => (rule.id === updated.id ? updated : rule)));
      setQuantityMessage(`Regla BIM actualizada para ${updated.element_label || updated.ifc_class}.`);
    } catch (err) {
      if (isUnauthorizedApiError(err)) {
        logout();
        return;
      }
      setQuantityError(apiErrorDetail(err) || "No se pudo actualizar la regla BIM");
    } finally {
      setQuantityAction(false);
    }
  }

  async function handleQuantityRuleRecalculation() {
    if (!selectedProjectId) return;
    const run = quantityTakeoffRuns[0];
    if (!run) {
      setQuantityError("Carga primero cantidades BIM, Excel o CSV antes de recalcular reglas.");
      return;
    }
    setQuantityAction(true);
    setQuantityError(null);
    setQuantityMessage(null);
    try {
      const result = await projectsApi.recalculateQuantityRules(token, selectedProjectId, run.id);
      const [runs, lines] = await Promise.all([
        projectsApi.quantityTakeoffRuns(token, selectedProjectId),
        projectsApi.quantityTakeoffLines(token, selectedProjectId, run.id),
      ]);
      setQuantityTakeoffRuns(runs);
      setQuantityTakeoffLines(lines);
      setQuantityRuleRecalculation(result);
      setQuantityMessage(
        `Reglas recalculadas: ${result.changed_line_count} linea(s) cambiadas. Gate de costos: ${result.cost_rollup_gate}.`
      );
    } catch (err) {
      if (isUnauthorizedApiError(err)) {
        logout();
        return;
      }
      setQuantityError(apiErrorDetail(err) || "No se pudieron recalcular las reglas BIM");
    } finally {
      setQuantityAction(false);
    }
  }

  async function handleColombiaApuCatalogSync() {
    if (!selectedProjectId) return;
    setQuantityAction(true);
    setQuantityError(null);
    setQuantityMessage(null);
    try {
      const syncResult = await projectsApi.syncColombiaApuCatalog(token, selectedProjectId);
      const catalog = await projectsApi.colombiaApuCatalog(
        token,
        selectedProjectId,
        colombiaApuSearch.trim(),
        colombiaApuSource
      );
      setColombiaApuSync(syncResult);
      setColombiaApuCatalog(catalog);
      setQuantityMessage(
        `Base APU Colombia actualizada: ${syncResult.created_count} nueva(s), ${syncResult.updated_count} actualizada(s), ${syncResult.total_count} disponible(s).`
      );
    } catch (err) {
      if (isUnauthorizedApiError(err)) {
        logout();
        return;
      }
      setQuantityError(apiErrorDetail(err) || "No se pudo actualizar la base APU Colombia");
    } finally {
      setQuantityAction(false);
    }
  }

  async function handleColombiaApuCatalogSearch(event?: FormEvent<HTMLFormElement>) {
    event?.preventDefault();
    if (!selectedProjectId) return;
    setQuantityAction(true);
    setQuantityError(null);
    setQuantityMessage(null);
    try {
      const catalog = await projectsApi.colombiaApuCatalog(
        token,
        selectedProjectId,
        colombiaApuSearch.trim(),
        colombiaApuSource
      );
      setColombiaApuCatalog(catalog);
      setQuantityMessage(
        colombiaApuSearch.trim()
          ? `Consulta APU: ${catalog.length} resultado(s) para "${colombiaApuSearch.trim()}".`
          : `Consulta APU: ${catalog.length} registro(s) visibles.`
      );
    } catch (err) {
      if (isUnauthorizedApiError(err)) {
        logout();
        return;
      }
      setQuantityError(apiErrorDetail(err) || "No se pudo consultar la base APU Colombia");
    } finally {
      setQuantityAction(false);
    }
  }

  async function handleColombiaApuCatalogClearSearch() {
    setColombiaApuSearch("");
    if (!selectedProjectId) return;
    setQuantityAction(true);
    setQuantityError(null);
    setQuantityMessage(null);
    try {
      const catalog = await projectsApi.colombiaApuCatalog(token, selectedProjectId, "", colombiaApuSource);
      setColombiaApuCatalog(catalog);
      setQuantityMessage(`Consulta APU limpia: ${catalog.length} registro(s) visibles.`);
    } catch (err) {
      if (isUnauthorizedApiError(err)) {
        logout();
        return;
      }
      setQuantityError(apiErrorDetail(err) || "No se pudo limpiar la consulta APU Colombia");
    } finally {
      setQuantityAction(false);
    }
  }

  async function handleQuantityApuSuggestion(lineIds: number[]) {
    if (!selectedProjectId) return;
    const run = quantityTakeoffRuns[0];
    if (!run) {
      setQuantityError("Carga primero cantidades BIM, Excel o CSV antes de sugerir APU.");
      return;
    }
    const uniqueLineIds = Array.from(new Set(lineIds)).filter(Boolean);
    if (!uniqueLineIds.length) {
      setQuantityError("No hay lineas de cantidad para sugerir APU.");
      return;
    }
    setQuantityAction(true);
    setQuantityError(null);
    setQuantityMessage(null);
    try {
      if (!colombiaApuCatalog.length) {
        const syncResult = await projectsApi.syncColombiaApuCatalog(token, selectedProjectId);
        setColombiaApuSync(syncResult);
      }
      const suggestions = await projectsApi.suggestQuantityApuItems(token, selectedProjectId, run.id, {
        apply_best: true,
        line_ids: uniqueLineIds,
        limit_per_line: 1,
      });
      const [catalog, updatedLines] = await Promise.all([
        projectsApi.colombiaApuCatalog(token, selectedProjectId, "", colombiaApuSource),
        projectsApi.quantityTakeoffLines(token, selectedProjectId, run.id),
      ]);
      setColombiaApuCatalog(catalog);
      setQuantityTakeoffLines(updatedLines);
      setQuantityMessage(
        suggestions.length
          ? `APU Colombia sugirio ${suggestions.length} partida(s). Revisa alcance, AIU, region y vigencia antes de aprobar presupuesto.`
          : "No se encontro una partida APU con coincidencia suficiente para esas cantidades."
      );
    } catch (err) {
      if (isUnauthorizedApiError(err)) {
        logout();
        return;
      }
      setQuantityError(apiErrorDetail(err) || "No se pudo sugerir APU Colombia para las cantidades");
    } finally {
      setQuantityAction(false);
    }
  }

  async function handleQuantityApuApproval(lineIds: number[]) {
    if (!selectedProjectId) return;
    const run = quantityTakeoffRuns[0];
    if (!run) {
      setQuantityError("Carga primero cantidades BIM, Excel o CSV antes de aprobar APU.");
      return;
    }
    const uniqueLineIds = Array.from(new Set(lineIds)).filter(Boolean);
    if (!uniqueLineIds.length) {
      setQuantityError("Selecciona al menos un grupo APU listo para aprobar.");
      return;
    }
    setQuantityAction(true);
    setQuantityError(null);
    setQuantityMessage(null);
    try {
      const updatedLines = await projectsApi.approveQuantityApuItems(token, selectedProjectId, run.id, {
        line_ids: uniqueLineIds,
      });
      const updatedById = new Map(updatedLines.map((line) => [line.id, line]));
      setQuantityTakeoffLines((current) => current.map((line) => updatedById.get(line.id) ?? line));
      setQuantityMessage(`${updatedLines.length} linea(s) aprobadas en grupos APU. Ya estan disponibles en Budget.`);
    } catch (err) {
      if (isUnauthorizedApiError(err)) {
        logout();
        return;
      }
      setQuantityError(apiErrorDetail(err) || "No se pudieron aprobar los grupos APU seleccionados");
    } finally {
      setQuantityAction(false);
    }
  }

  async function handleClaimsForensicSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId) return;
    if (!claimsAuditFiles.length) {
      setClaimsAuditError("Selecciona al menos un expediente, soporte o ZIP de reclamacion.");
      return;
    }
    setClaimsAuditAction(true);
    setClaimsAuditError(null);
    setClaimsAuditMessage(null);
    try {
      const result = await integratedControlApi.runClaimsForensicDossier(
        token,
        selectedProjectId,
        claimsAuditMode,
        claimsAuditFiles
      );
      setClaimsAuditResult(result);
      await refreshDashboard(selectedProjectId);
      setClaimsAuditMessage(
        `${result.created_claims.length} claim(s), ${result.created_entitlement_items.length} punto(s) de entitlement y ${result.created_impact_analyses.length} impacto(s) creados.`
      );
    } catch (err) {
      if (isUnauthorizedApiError(err)) {
        logout();
        return;
      }
      setClaimsAuditError(apiErrorDetail(err) || "No se pudo analizar el expediente de reclamacion");
    } finally {
      setClaimsAuditAction(false);
    }
  }

  async function handleWindowAnalysis37Submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId) return;
    if (windowAnalysisFiles.length < 2) {
      setWindowAnalysisError("Carga al menos dos cronogramas para formar ventanas comparables.");
      return;
    }
    setWindowAnalysisAction(true);
    setWindowAnalysisError(null);
    setWindowAnalysisMessage(null);
    try {
      const result = await integratedControlApi.runWindowAnalysis37(
        token,
        selectedProjectId,
        windowAnalysisThreshold,
        windowAnalysisFiles
      );
      setWindowAnalysisResult(result);
      setWindowAnalysisMessage(
        `${result.windows.length} ventana(s), ${result.summary.total_critical_delay_days ?? 0} dia(s) de impacto critico neto.`
      );
    } catch (err) {
      if (isUnauthorizedApiError(err)) {
        logout();
        return;
      }
      setWindowAnalysisError(apiErrorDetail(err) || "No se pudo ejecutar el analisis de ventanas 3.7");
    } finally {
      setWindowAnalysisAction(false);
    }
  }

  async function handleControlledMeasurementApproval(payload: ControlledMeasurementApproval) {
    if (!selectedProjectId) return;
    const run = quantityTakeoffRuns[0];
    if (!run) {
      setQuantityError("Carga primero cantidades BIM, Excel o CSV antes de aprobar mediciones.");
      return;
    }
    setQuantityAction(true);
    setQuantityError(null);
    setQuantityMessage(null);
    try {
      const updatedLines = await projectsApi.approveControlledMeasurements(token, selectedProjectId, run.id, payload);
      const updatedById = new Map(updatedLines.map((line) => [line.id, line]));
      setQuantityTakeoffLines((current) => current.map((line) => updatedById.get(line.id) ?? line));
      setQuantityMessage(
        `Medicion controlada aprobada para ${updatedLines.length} linea(s). Regla: ${payload.measurement_rule}.`
      );
    } catch (err) {
      if (isUnauthorizedApiError(err)) {
        logout();
        return;
      }
      setQuantityError(apiErrorDetail(err) || "No se pudo aprobar la medicion controlada");
    } finally {
      setQuantityAction(false);
    }
  }

  async function handleGeometryMeasurementBatch(apply: boolean) {
    if (!selectedProjectId) return;
    const run = quantityTakeoffRuns[0];
    const model = geometryModelForRun(run, bimModelRuns);
    if (!run || !model) {
      setQuantityError(
        run && bimModelRuns.length
          ? "Vincula la corrida de cantidades a la revision IFC correcta antes de calcular la geometria."
          : "Carga el modelo IFC y su tabla de cantidades antes de calcular la geometria masiva."
      );
      return;
    }
    setQuantityAction(true);
    setQuantityError(null);
    setQuantityMessage(null);
    try {
      const result = await projectsApi.processGeometryMeasurements(token, selectedProjectId, run.id, {
        apply,
        model_id: model.id,
        replace_valid: false,
      });
      setGeometryMeasurementBatch(result);
      if (apply) {
        const [updatedLines, updatedRuns] = await Promise.all([
          projectsApi.quantityTakeoffLines(token, selectedProjectId, run.id),
          projectsApi.quantityTakeoffRuns(token, selectedProjectId),
        ]);
        setQuantityTakeoffLines(updatedLines);
        setQuantityTakeoffRuns(updatedRuns);
        setQuantityMessage(
          result.applied_count
            ? `${result.applied_count} medicion(es) geometricas aprobadas y versionadas. Las cantidades validas se conservaron.`
            : "No habia mediciones geometricas listas para aprobar."
        );
      } else {
        setQuantityMessage(
          `Calculo geometrico terminado: ${result.ready_count} lista(s), ${result.compare_count} para comparar y ${
            result.unmatched_count + result.invalid_count
          } sin resultado.`
        );
      }
    } catch (err) {
      if (isUnauthorizedApiError(err)) {
        logout();
        return;
      }
      setQuantityError(apiErrorDetail(err) || "No se pudo calcular la geometria masiva del modelo IFC");
    } finally {
      setQuantityAction(false);
    }
  }

  async function handleQuantityTakeoffModelLink(modelId: number) {
    if (!selectedProjectId) return;
    const run = quantityTakeoffRuns[0];
    if (!run) return;
    setQuantityAction(true);
    setQuantityError(null);
    setQuantityMessage(null);
    try {
      const updated = await projectsApi.linkQuantityTakeoffBimModel(token, selectedProjectId, run.id, {
        model_id: modelId,
        expected_version: run.version,
      });
      setQuantityTakeoffRuns((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setGeometryMeasurementBatch(null);
      setQuantityMessage(`Corrida vinculada a la revision ${updated.bim_revision_id || `modelo ${modelId}`}.`);
    } catch (err) {
      if (isUnauthorizedApiError(err)) {
        logout();
        return;
      }
      setQuantityError(apiErrorDetail(err) || "No se pudo vincular la revision IFC a la tabla de cantidades");
    } finally {
      setQuantityAction(false);
    }
  }

  async function handleQuantityControlCodeAssignment(payload: QuantityControlCodeAssignment) {
    if (!selectedProjectId) return;
    const run = quantityTakeoffRuns[0];
    if (!run) {
      setQuantityError("Carga primero cantidades BIM, Excel o CSV antes de asignar codigos de control.");
      return;
    }
    setQuantityAction(true);
    setQuantityError(null);
    setQuantityMessage(null);
    try {
      const updatedLines = await projectsApi.assignQuantityControlCodes(token, selectedProjectId, run.id, payload);
      const updatedRuns = await projectsApi.quantityTakeoffRuns(token, selectedProjectId);
      const updatedById = new Map(updatedLines.map((line) => [line.id, line]));
      setQuantityTakeoffLines((current) => current.map((line) => updatedById.get(line.id) ?? line));
      setQuantityTakeoffRuns(updatedRuns);
      setQuantityMessage(
        `Codigos de control asignados a ${updatedLines.length} linea(s): ${payload.wbs_code} / ${payload.cbs_code} / ${payload.fbs_code} / ${payload.package_code}.`
      );
    } catch (err) {
      if (isUnauthorizedApiError(err)) {
        logout();
        return;
      }
      setQuantityError(apiErrorDetail(err) || "No se pudieron asignar los codigos de control");
    } finally {
      setQuantityAction(false);
    }
  }

  async function handleUserCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId) return;
    setUserAction(true);
    setUserError(null);
    setUserMessage(null);
    try {
      const created = await adminApi.createUser(token, {
        email: userDraft.email.trim().toLowerCase(),
        full_name: userDraft.full_name.trim(),
        password: userDraft.password,
        title: userDraft.title.trim(),
      });
      await projectsApi.assignTeamMember(token, selectedProjectId, {
        role: userDraft.role,
        user_id: created.id,
      });
      setUsers((current) =>
        current.some((item) => item.id === created.id)
          ? current.map((item) => (item.id === created.id ? created : item))
          : [...current, created]
      );
      setSelectedIamUserId(String(created.id));
      setManagedUserDraft(managedDraftForUser(created));
      await refreshDashboard(selectedProjectId);
      setUserDraft((current) => ({
        ...current,
        email: "",
        full_name: "",
        password: "1234",
        title: "",
      }));
      setUserMessage(`${created.full_name} created and assigned as ${userDraft.role}.`);
    } catch (err) {
      setUserError(err instanceof Error ? err.message : "Could not create user or assign role");
    } finally {
      setUserAction(false);
    }
  }

  function handleManagedUserSelect(userId: string) {
    setSelectedIamUserId(userId);
    const selected = users.find((item) => String(item.id) === userId);
    if (selected) {
      setManagedUserDraft((current) => ({
        ...current,
        email: selected.email,
        full_name: selected.full_name,
        title: selected.title,
      }));
    }
  }

  async function handleManagedUserUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const userId = Number(selectedIamUserId);
    if (!userId) return;
    setIamAction("update");
    setUserError(null);
    setUserMessage(null);
    try {
      const updated = await adminApi.updateUser(token, userId, {
        email: managedUserDraft.email.trim().toLowerCase(),
        full_name: managedUserDraft.full_name.trim(),
        title: managedUserDraft.title.trim(),
      });
      setUsers((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      setManagedUserDraft(managedDraftForUser(updated));
      setUserMessage(`${updated.full_name} updated.`);
    } catch (err) {
      setUserError(err instanceof Error ? err.message : "Could not update user");
    } finally {
      setIamAction(null);
    }
  }

  async function handleManagedPasswordReset() {
    const userId = Number(selectedIamUserId);
    if (!userId) return;
    setIamAction("reset");
    setUserError(null);
    setUserMessage(null);
    try {
      const updated = await adminApi.resetUserPassword(token, userId, managedUserDraft.password.trim());
      setManagedUserDraft((current) => ({ ...current, password: "" }));
      setUserMessage(`${updated.full_name} password reset.`);
    } catch (err) {
      setUserError(err instanceof Error ? err.message : "Could not reset password");
    } finally {
      setIamAction(null);
    }
  }

  async function handleAssignExistingUser() {
    if (!selectedProjectId) return;
    const userId = Number(selectedIamUserId);
    if (!userId) return;
    setIamAction("assign");
    setUserError(null);
    setUserMessage(null);
    try {
      await projectsApi.assignTeamMember(token, selectedProjectId, {
        role: userDraft.role,
        user_id: userId,
      });
      await refreshDashboard(selectedProjectId);
      const selected = users.find((item) => item.id === userId);
      setUserMessage(`${selected?.full_name ?? "User"} assigned as ${userDraft.role}.`);
    } catch (err) {
      setUserError(err instanceof Error ? err.message : "Could not assign project access");
    } finally {
      setIamAction(null);
    }
  }

  async function handleRemoveProjectAccess(userId?: number) {
    if (!selectedProjectId) return;
    const targetUserId = userId ?? Number(selectedIamUserId);
    if (!targetUserId) return;
    setIamAction("remove");
    setUserError(null);
    setUserMessage(null);
    try {
      await projectsApi.removeTeamMember(token, selectedProjectId, targetUserId);
      await refreshDashboard(selectedProjectId);
      const selected = users.find((item) => item.id === targetUserId);
      setUserMessage(`${selected?.full_name ?? "User"} removed from this project.`);
    } catch (err) {
      setUserError(err instanceof Error ? err.message : "Could not remove project access");
    } finally {
      setIamAction(null);
    }
  }

  async function handleDeactivateUser() {
    const userId = Number(selectedIamUserId);
    if (!userId) return;
    setIamAction("deactivate");
    setUserError(null);
    setUserMessage(null);
    try {
      const deactivated = await adminApi.deactivateUser(token, userId);
      const nextUsers = users.filter((item) => item.id !== deactivated.id);
      const nextSelectedUser = nextUsers[0];
      setUsers(nextUsers);
      setSelectedIamUserId(nextSelectedUser ? String(nextSelectedUser.id) : "");
      setManagedUserDraft(managedDraftForUser(nextSelectedUser));
      if (selectedProjectId) {
        await refreshDashboard(selectedProjectId);
      }
      setUserMessage(`${deactivated.full_name} deactivated.`);
    } catch (err) {
      setUserError(err instanceof Error ? err.message : "Could not deactivate user");
    } finally {
      setIamAction(null);
    }
  }

  async function handleWbsCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId) return;
    setWbsAction(true);
    setIntegratedError(null);
    setIntegratedMessage(null);
    try {
      const created = await integratedControlApi.createWbs(token, selectedProjectId, {
        parent_id: wbsDraft.parent_id ? Number(wbsDraft.parent_id) : null,
        code: wbsDraft.code.trim(),
        name: wbsDraft.name.trim(),
        level: Number(wbsDraft.level || 1),
        description: wbsDraft.description.trim(),
        dictionary: wbsDraft.dictionary.trim(),
        responsible: wbsDraft.responsible.trim(),
        status: wbsDraft.status,
      });
      await refreshIntegratedControl(selectedProjectId);
      setWbsCatalog((current) =>
        [...current.filter((item) => item.id !== created.id), created].sort((left, right) =>
          left.code.localeCompare(right.code)
        )
      );
      setPriorityDraft((current) => ({ ...current, wbs_id: current.wbs_id || String(created.id) }));
      setWbsDraft((current) => ({
        ...current,
        parent_id: "",
        code: "",
        name: "",
        description: "",
        dictionary: "",
        responsible: "",
      }));
      setIntegratedMessage(`WBS ${created.code} created.`);
    } catch (err) {
      if (isUnauthorizedApiError(err)) {
        logout();
        return;
      }
      setIntegratedError(err instanceof Error ? err.message : "Could not create WBS");
    } finally {
      setWbsAction(false);
    }
  }

  async function handleFbsCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId) return;
    setFbsAction(true);
    setIntegratedError(null);
    setIntegratedMessage(null);
    try {
      const created = await integratedControlApi.createFbs(token, selectedProjectId, {
        code: fbsDraft.code.trim(),
        source_of_funds: fbsDraft.source_of_funds.trim(),
        funding_type: fbsDraft.funding_type.trim(),
        authorization_ref: fbsDraft.authorization_ref.trim(),
        approved_amount: Number(fbsDraft.approved_amount),
        currency: fbsDraft.currency.trim().toUpperCase() || project.currency,
        status: fbsDraft.status,
      });
      await refreshDashboard(selectedProjectId);
      await refreshIntegratedControl(selectedProjectId);
      setFbsDraft({
        code: "",
        source_of_funds: "",
        funding_type: created.funding_type || "AFE",
        authorization_ref: "",
        approved_amount: "",
        currency: created.currency || project.currency,
        status: "approved",
      });
      setIntegratedMessage(`FBS ${created.code} created.`);
    } catch (err) {
      setIntegratedError(err instanceof Error ? err.message : "Could not create FBS");
    } finally {
      setFbsAction(false);
    }
  }

  async function handleCbsCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId) return;
    setPriorityAction("cbs");
    setIntegratedError(null);
    setIntegratedMessage(null);
    try {
      const created = await integratedControlApi.createCbs(token, selectedProjectId, {
        code: cbsDraft.code.trim(),
        level: Number(cbsDraft.level || 1),
        cost_category: cbsDraft.cost_category.trim(),
        description: cbsDraft.description.trim(),
        status: cbsDraft.status,
      });
      await refreshIntegratedControl(selectedProjectId);
      setPriorityDraft((current) => ({ ...current, cbs_id: String(created.id) }));
      setRateDraft((current) => ({ ...current, cbs_code: created.code }));
      setCbsDraft({
        code: "",
        level: "3",
        cost_category: created.cost_category || "",
        description: "",
        status: "active",
      });
      setIntegratedMessage(`CBS ${created.code} created.`);
    } catch (err) {
      setIntegratedError(err instanceof Error ? err.message : "Could not create CBS");
    } finally {
      setPriorityAction(null);
    }
  }

  async function handlePriorityBusinessProcess(kind: "fund" | "wbs") {
    if (!selectedProjectId) return;
    setPriorityAction(kind);
    setIntegratedError(null);
    setIntegratedMessage(null);
    try {
      const selectedAccount = activeControlAccounts.find(
        (account) => account.id === Number(priorityDraft.control_account_id)
      );
      const wbsId = Number(priorityDraft.wbs_id || selectedAccount?.wbs_id || 0);
      const payload = {
        title: kind === "fund" ? "CBS + Fund Code allocation" : "CBS + WBS Code transaction",
        line_items: [
          {
            wbs_id: kind === "wbs" ? wbsId : null,
            cbs_id: Number(priorityDraft.cbs_id),
            funding_source_id: Number(priorityDraft.funding_source_id),
            control_account_id: Number(priorityDraft.control_account_id),
            amount: Number(priorityDraft.amount),
            quantity: Number(priorityDraft.quantity || 0),
            description: priorityDraft.description.trim(),
          },
        ],
      };
      const process =
        kind === "fund"
          ? await integratedControlApi.createCbsFundBusinessProcess(token, selectedProjectId, payload)
          : await integratedControlApi.createCbsWbsBusinessProcess(token, selectedProjectId, payload);
      await refreshDashboard(selectedProjectId);
      await refreshIntegratedControl(selectedProjectId);
      await refreshProcessLineItems(selectedProjectId, process.id);
      setPriorityDraft((current) => ({ ...current, amount: "", quantity: "", description: "" }));
      setIntegratedMessage(`${process.record_no} created at ${statusLabel(process.current_step)}.`);
    } catch (err) {
      setIntegratedError(err instanceof Error ? err.message : "Could not create the business process");
    } finally {
      setPriorityAction(null);
    }
  }

  async function handleSovAndFundingCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId) return;
    setPriorityAction("sov");
    setIntegratedError(null);
    setIntegratedMessage(null);
    try {
      const contractId = Number(sovDraft.contract_id);
      const sovLine = await integratedControlApi.createSovLine(token, selectedProjectId, contractId, {
        line_no: sovDraft.line_no.trim(),
        description: sovDraft.description.trim(),
        amount: Number(sovDraft.amount),
        cbs_id: Number(priorityDraft.cbs_id),
        wbs_id: Number(priorityDraft.wbs_id),
        control_account_id: Number(priorityDraft.control_account_id),
        status: "active",
      });
      await integratedControlApi.createCommitmentFundingLine(token, selectedProjectId, {
        contract_id: contractId,
        sov_line_id: sovLine.id,
        funding_source_id: Number(priorityDraft.funding_source_id),
        amount: Number(sovDraft.amount),
        status: "active",
      });
      await refreshDashboard(selectedProjectId);
      await refreshIntegratedControl(selectedProjectId);
      setSovDraft((current) => ({
        ...current,
        line_no: String(Number(current.line_no || 0) + 10),
        description: "",
        amount: "",
      }));
      setIntegratedMessage(`SOV ${sovLine.line_no} funded.`);
    } catch (err) {
      setIntegratedError(err instanceof Error ? err.message : "Could not create SOV funding");
    } finally {
      setPriorityAction(null);
    }
  }

  async function handleRateSheetCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId) return;
    setPriorityAction("rate");
    setIntegratedError(null);
    setIntegratedMessage(null);
    try {
      const created = await integratedControlApi.createRateSheet(token, selectedProjectId, {
        code: rateDraft.code.trim(),
        name: rateDraft.name.trim(),
        status: "active",
        line_items: [
          {
            cbs_code: rateDraft.cbs_code.trim(),
            multiplier: Number(rateDraft.multiplier || 1),
            unit_rate: Number(rateDraft.unit_rate || 0),
            status: "active",
          },
        ],
      });
      await refreshIntegratedControl(selectedProjectId);
      setRateDraft((current) => ({ ...current, code: "", name: "", multiplier: "1.0", unit_rate: "0" }));
      setIntegratedMessage(`Rate Sheet ${created.code} created.`);
    } catch (err) {
      setIntegratedError(err instanceof Error ? err.message : "Could not create Rate Sheet");
    } finally {
      setPriorityAction(null);
    }
  }

  async function handlePolicySubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId) return;
    setHardeningAction("policy");
    setIntegratedError(null);
    setIntegratedMessage(null);
    try {
      const policy = await integratedControlApi.upsertBusinessProcessPolicy(token, selectedProjectId, {
        process_code: policyDraft.process_code,
        action: policyDraft.action,
        required_role: policyDraft.required_role,
        permission_key: policyDraft.permission_key,
        status: "active",
      });
      await refreshIntegratedControl(selectedProjectId);
      setIntegratedMessage(
        `${policy.process_code} ${policy.action} policy saved for ${policy.required_role || "permission key"}.`
      );
    } catch (err) {
      setIntegratedError(err instanceof Error ? err.message : "Could not save business process policy");
    } finally {
      setHardeningAction(null);
    }
  }

  async function handleLineItemSelect(line: BusinessProcessLineItem) {
    if (!selectedProjectId) return;
    setLineEditDraft((current) => ({
      ...current,
      line_item_id: String(line.id),
      amount: String(line.amount),
      quantity: String(line.quantity),
      description: line.description,
    }));
    try {
      const revisions = await integratedControlApi.businessProcessLineItemRevisions(token, selectedProjectId, line.id);
      setBpLineItemRevisions(revisions);
    } catch (err) {
      setIntegratedError(err instanceof Error ? err.message : "Could not load line item revisions");
    }
  }

  async function handleLineItemUpdate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId) return;
    const selectedLine = bpLineItems.find((line) => String(line.id) === lineEditDraft.line_item_id);
    if (!selectedLine) return;
    setHardeningAction("line");
    setIntegratedError(null);
    setIntegratedMessage(null);
    try {
      const updated = await integratedControlApi.updateBusinessProcessLineItem(
        token,
        selectedProjectId,
        selectedLine.id,
        {
          amount: Number(lineEditDraft.amount),
          quantity: Number(lineEditDraft.quantity || 0),
          description: lineEditDraft.description,
          change_note: lineEditDraft.change_note,
          expected_version: selectedLine.version,
        }
      );
      await refreshDashboard(selectedProjectId);
      await refreshIntegratedControl(selectedProjectId);
      await refreshProcessLineItems(selectedProjectId, updated.process_instance_id, updated.id);
      setIntegratedMessage(`Line item version ${updated.version} saved.`);
    } catch (err) {
      setIntegratedError(err instanceof Error ? err.message : "Could not update line item");
    } finally {
      setHardeningAction(null);
    }
  }

  async function handleReconciliationExport(format: "xlsx" | "pdf") {
    if (!selectedProjectId) return;
    setHardeningAction(format === "xlsx" ? "export-xlsx" : "export-pdf");
    setIntegratedError(null);
    setIntegratedMessage(null);
    try {
      const blob = await integratedControlApi.exportReconciliationReport(token, selectedProjectId, format);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `reconciliation-${project.code}.${format}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
      setIntegratedMessage(`Reconciliation ${format.toUpperCase()} export generated.`);
    } catch (err) {
      setIntegratedError(err instanceof Error ? err.message : "Could not export reconciliation report");
    } finally {
      setHardeningAction(null);
    }
  }

  async function handleControlAuditAgentRun() {
    if (!selectedProjectId) return;
    setAgentAction(true);
    setIntegratedError(null);
    setIntegratedMessage(null);
    try {
      const run = await integratedControlApi.runControlAuditAgent(token, selectedProjectId);
      const history = await integratedControlApi.controlAuditAgentRuns(token, selectedProjectId);
      setControlAgentRuns(history.length ? history : [run]);
      setIntegratedMessage(`${run.agent_name} completed with score ${run.score}.`);
    } catch (err) {
      setIntegratedError(err instanceof Error ? err.message : "Could not run Control Audit Agent");
    } finally {
      setAgentAction(false);
    }
  }

  async function handleCreateAwpDraftPackages() {
    if (!selectedProjectId) return;
    setAgentAction(true);
    setIntegratedError(null);
    setIntegratedMessage(null);
    try {
      const run = await integratedControlApi.createAwpDraftPackages(token, selectedProjectId);
      await refreshDashboard(selectedProjectId);
      await refreshIntegratedControl(selectedProjectId);
      const history = await integratedControlApi.controlAuditAgentRuns(token, selectedProjectId);
      setControlAgentRuns(history.length ? history : [run]);
      setIntegratedMessage(`${run.summary} Review the draft packages in Work Packages.`);
    } catch (err) {
      setIntegratedError(err instanceof Error ? err.message : "Could not create AWP draft packages");
    } finally {
      setAgentAction(false);
    }
  }

  async function handleRecostLatestActivitySheet() {
    if (!selectedProjectId || !activitySheets[0] || !rateSheets[0]) return;
    setPriorityAction("recost");
    setIntegratedError(null);
    setIntegratedMessage(null);
    try {
      const result = await integratedControlApi.recostActivitySheet(
        token,
        selectedProjectId,
        activitySheets[0].id,
        rateSheets[0].id
      );
      const [wbsRows, detailRows] = await Promise.all([
        projectsApi.activitySheetWbsRows(token, selectedProjectId, activitySheets[0].id),
        projectsApi.activitySheetRows(token, selectedProjectId, activitySheets[0].id),
      ]);
      const history = await integratedControlApi.recostRuns(token, selectedProjectId, activitySheets[0].id);
      await refreshDashboard(selectedProjectId);
      await refreshIntegratedControl(selectedProjectId);
      setActivitySheetWbsRows(wbsRows);
      setActivitySheetRows(detailRows);
      setRecostRuns(history);
      setIntegratedMessage(`${result.updated_rows} activity rows recosted in run ${result.recost_run_id ?? "latest"}.`);
    } catch (err) {
      setIntegratedError(err instanceof Error ? err.message : "Could not recost Activity Sheet");
    } finally {
      setPriorityAction(null);
    }
  }

  async function handleBaselineApproval() {
    if (!selectedProjectId) return;
    setBaselineAction(true);
    setIntegratedError(null);
    setIntegratedMessage(null);
    try {
      const result = await integratedControlApi.approveBaseline(token, selectedProjectId);
      await refreshDashboard(selectedProjectId);
      await refreshIntegratedControl(selectedProjectId);
      setIntegratedMessage(`Baseline status: ${statusLabel(result.project_status)}.`);
    } catch (err) {
      setIntegratedError(err instanceof Error ? err.message : "Could not approve integrated baseline");
    } finally {
      setBaselineAction(false);
    }
  }

  async function handleCreateWorkPackageConstraint(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selectedProjectId || !dashboard) return;
    const packageId = Number(constraintDraft.work_package_id || dashboard.work_packages[0]?.id || 0);
    if (!packageId || !constraintDraft.description.trim()) {
      setIntegratedError("Select a work package and describe the constraint.");
      return;
    }
    setConstraintAction(true);
    setIntegratedError(null);
    setIntegratedMessage(null);
    try {
      await integratedControlApi.createWorkPackageConstraint(token, selectedProjectId, packageId, {
        constraint_type: constraintDraft.constraint_type,
        description: constraintDraft.description.trim(),
        owner_role: constraintDraft.owner_role,
        required_by: constraintDraft.required_by || null,
        status: "open",
        priority: constraintDraft.priority,
        evidence_ref: constraintDraft.evidence_ref,
        blocking: constraintDraft.blocking,
      });
      await refreshDashboard(selectedProjectId);
      setIntegratedMessage("Constraint added to the selected draft package.");
      setConstraintDraft((draft) => ({
        ...draft,
        description: "",
        required_by: "",
        evidence_ref: "",
      }));
    } catch (err) {
      setIntegratedError(err instanceof Error ? err.message : "Could not create work package constraint");
    } finally {
      setConstraintAction(false);
    }
  }

  function handleControlFlowNavigate(view: ControlFlowView) {
    const nextView = FRONTEND_VALIDATION_MODE ? focusedControlView(view) : view;
    setActiveControlView(nextView);
    const routedView = routeControlView(location.pathname);
    if (!FRONTEND_VALIDATION_MODE && nextView === "schedule-control" && routedView !== "schedule-control") {
      navigate("/app/schedule-control");
    }
    if ((FRONTEND_VALIDATION_MODE || nextView !== "schedule-control") && routedView) {
      navigate("/app");
    }
    document.getElementById("control-flow-content")?.scrollIntoView?.({ block: "start", behavior: "smooth" });
  }

  function handleApplicationModeToggle() {
    const nextMode: ApplicationMode = applicationMode === "user" ? "admin" : "user";
    setApplicationMode(nextMode);
    handleControlFlowNavigate(nextMode === "admin" ? "admin" : "dashboard");
  }

  const constraintsByPackage = useMemo(() => {
    return (dashboard?.work_package_constraints ?? []).reduce<Record<number, number>>((acc, constraint) => {
      if (constraint.status === "open" && constraint.blocking) {
        acc[constraint.work_package_id] = (acc[constraint.work_package_id] ?? 0) + 1;
      }
      return acc;
    }, {});
  }, [dashboard?.work_package_constraints]);
  const workPackageTree = useMemo(
    () => buildWorkPackageTree(dashboard?.work_packages ?? []),
    [dashboard?.work_packages]
  );
  const workPackagePocRoute = useMemo(
    () => sortWorkPackages(dashboard?.work_packages ?? []).filter(isPathOfConstructionStep),
    [dashboard?.work_packages]
  );
  const evmDataDate = dashboard?.schedule_import?.data_date ?? activitySheets[0]?.data_date ?? null;
  const baselineOnlyEvm =
    Boolean(dashboard?.schedule_import || activitySheets.length) &&
    !(dashboard?.latest_progress_records?.length ?? 0) &&
    !(dashboard?.latest_cost_records?.length ?? 0);
  const projectEvmSnapshot = useMemo(
    () =>
      dashboard
        ? deriveProjectEvm(dashboard.project_kpi, dashboard.cost_sheet ?? [], activitySheetRows, evmDataDate, {
            baselineOnly: baselineOnlyEvm,
          })
        : null,
    [activitySheetRows, baselineOnlyEvm, dashboard, evmDataDate]
  );

  const evmCurveData = useMemo(() => {
    if (!dashboard) return [];
    const currentEvm = deriveProjectEvm(
      dashboard.project_kpi,
      dashboard.cost_sheet ?? [],
      activitySheetRows,
      evmDataDate,
      {
        baselineOnly: baselineOnlyEvm,
      }
    );
    return buildCumulativeEvmCurve(dashboard.control_snapshots ?? [], currentEvm, activitySheetRows, evmDataDate, {
      baselineOnly: baselineOnlyEvm,
    });
  }, [activitySheetRows, baselineOnlyEvm, dashboard, evmDataDate]);
  const colombiaApuStructure = useMemo(() => buildApuCatalogStructure(colombiaApuCatalog), [colombiaApuCatalog]);
  const colombiaApuSourceLabel = sourceLabel(colombiaApuSource);

  if (loading && !dashboard) {
    return <div className="loading">Loading workspace...</div>;
  }

  if (!error && !dashboard && projectList.length === 0) {
    return (
      <main>
        <header className="appBrandBar" aria-label="Application brand">
          <ProductLogo compact />
          <span>Project Controls Intelligence Platform</span>
        </header>
        <section className="panel workspaceEmpty">
          <h1>Create your first project</h1>
          <p>Start with a clean project workspace. The creator will be assigned as Control Manager.</p>
          <button className="iconTextButton" onClick={() => setProjectDrawerOpen(true)} type="button">
            New Project
          </button>
        </section>
        <ProjectCreateDrawer
          canConfigure
          draft={projectDraft}
          error={projectError}
          message={projectMessage}
          open={projectDrawerOpen}
          pending={projectAction}
          onClose={() => setProjectDrawerOpen(false)}
          onDraftChange={setProjectDraft}
          onSubmit={handleProjectCreate}
        />
      </main>
    );
  }

  if (error || !dashboard || !projectEvmSnapshot) {
    return (
      <main>
        <section className="panel workspaceEmpty">
          <h1>Workspace unavailable</h1>
          <p>{error ?? "No project dashboard is available."}</p>
        </section>
      </main>
    );
  }

  const project = dashboard.project;
  const projectEvm = projectEvmSnapshot;
  const spiLabel = formatEvmRatio(projectEvm.spi);
  const cpiLabel = formatEvmRatio(projectEvm.cpi);
  const currentMembership = dashboard.project_team.find((member) => member.user.id === user?.id)?.membership;
  const canConfigure = Boolean(currentMembership?.can_configure);
  const canCaptureCost = Boolean(currentMembership?.can_capture_cost);
  const canManageContract = Boolean(currentMembership?.can_manage_contract);
  const canUploadSchedule = currentMembership?.role === "Planner" || currentMembership?.role === "Control Manager";
  const canLoadQuantities = canConfigure || canCaptureCost;
  const activeImport = dashboard.schedule_import;
  const scheduleQualityMetrics = dashboard.schedule_quality_metrics ?? [];
  const nextActionStep =
    guidedFlow?.steps.find((step) => step.key === guidedFlow.next_action.key) ?? guidedFlow?.steps[0];
  const cbsCostLines = dashboard.cost_sheet ?? [];
  const fbsFundingSources = dashboard.funding_sources ?? [];
  const contractRows = dashboard.contracts ?? [];
  const activeControlAccounts = controlAccounts.filter(isActiveControlAccount);
  const selectedControlAccount = activeControlAccounts.find(
    (account) => account.id === Number(priorityDraft.control_account_id)
  );
  const selectedWbsForAccount = selectedControlAccount
    ? wbsCatalog.find((wbs) => wbs.id === selectedControlAccount.wbs_id)
    : undefined;
  const selectedCbs = cbsCatalog.find((cbs) => cbs.id === Number(priorityDraft.cbs_id));
  const rateCbsOptions = Array.from(
    new Set([...cbsCatalog.map((cbs) => cbs.code), ...activitySheetRows.map((row) => row.cbs_code).filter(Boolean)])
  );
  const latestActivitySheet = activitySheets[0];
  const latestQuantityTakeoff = quantityTakeoffRuns[0];
  const latestBimModel = bimModelRuns[0];
  const geometryMeasurementModel = geometryModelForRun(latestQuantityTakeoff, bimModelRuns);
  const displayedBimModel = geometryMeasurementModel ?? latestBimModel;
  const geometryModelStatusMessage =
    latestQuantityTakeoff && !geometryMeasurementModel
      ? "Esta corrida aun no tiene una revision IFC vinculada. Selecciona el modelo de origen y confirma el vinculo antes de calcular."
      : "";
  const quantityRuleValidCount = bimQuantityRules.filter((rule) => rule.status === "valid").length;
  const quantityRuleBlockedCount = bimQuantityRules.filter((rule) => rule.status === "blocked").length;
  const quantityRuleReviewCount = Math.max(
    bimQuantityRules.length - quantityRuleValidCount - quantityRuleBlockedCount,
    0
  );
  const hasRenderableIfcGeometry = Boolean(
    latestBimModel &&
    latestBimModel.element_count > 0 &&
    !["failed", "geometry_failed", "error"].includes(latestBimModel.status.toLowerCase())
  );
  const reconciliationRows = reconciliationReport?.rows ?? [];
  const latestAgentRun = controlAgentRuns[0];
  const agentFindings = latestAgentRun?.findings ?? [];
  const selectedLineItem = bpLineItems.find((line) => String(line.id) === lineEditDraft.line_item_id);
  const policyRoleOptions = roles.length ? roles.map((role) => role.role) : ["Control Manager"];
  const canRunPriority =
    Boolean(
      priorityDraft.cbs_id &&
      priorityDraft.funding_source_id &&
      priorityDraft.control_account_id &&
      priorityDraft.amount
    ) && Number(priorityDraft.amount) > 0;
  const totalFunding = fbsFundingSources.reduce((total, source) => total + source.amount, 0);
  const quantityNeedsMapping = quantityTakeoffLines.filter((line) => line.mapping_status !== "mapped").length;
  const latestBimIdentity = latestBimModel?.model_identity ?? {};
  const quantityModelIdentity =
    [latestBimIdentity.project_name, latestBimIdentity.site_name, latestBimIdentity.building_name]
      .filter(Boolean)
      .map(String)
      .join(" / ") ||
    [
      quantityTakeoffLines.find((line) => line.project_name)?.project_name,
      quantityTakeoffLines.find((line) => line.site_name)?.site_name,
      quantityTakeoffLines.find((line) => line.building_name)?.building_name,
    ]
      .filter(Boolean)
      .join(" / ");
  const quantityElementCount = new Set(
    quantityTakeoffLines.map((line) => line.element_guid || line.element_id).filter(Boolean)
  ).size;
  const quantityClassCount = new Set(
    quantityTakeoffLines.map((line) => line.ifc_class || line.category).filter(Boolean)
  ).size;
  const quantityRuleSummary = Array.from(
    new Set(quantityTakeoffLines.map((line) => line.measurement_rule).filter(Boolean))
  )
    .slice(0, 4)
    .join(" / ");
  const quantitySourceBasis =
    latestBimModel && latestQuantityTakeoff?.source_type === "ifc"
      ? "Modelo IFC + tabla controlada"
      : latestBimModel
        ? "Modelo IFC registrado"
        : latestQuantityTakeoff?.source_type === "ifc"
          ? "IFC Quantity Sets"
          : latestQuantityTakeoff
            ? "Spreadsheet quantity columns"
            : "Waiting for source";
  const scopeManagerInformationContent = (
    <>
      <div className="quantityModuleHeader">
        <div className="mappingSummary quantitySummary">
          <article>
            <span>Cargas</span>
            <strong>{bimModelRuns.length || quantityTakeoffRuns.length || 0}</strong>
            <small>
              {latestBimModel
                ? "Modelo IFC registrado"
                : latestQuantityTakeoff
                  ? "Ultima fuente controlada"
                  : "Sin archivo"}
            </small>
          </article>
          <article>
            <span>Lineas</span>
            <strong>{latestQuantityTakeoff?.row_count ?? 0}</strong>
            <small>{latestQuantityTakeoff?.source_type.toUpperCase() ?? "BIM/Excel"}</small>
          </article>
          <article>
            <span>Codificadas</span>
            <strong>{latestQuantityTakeoff?.mapped_line_count ?? 0}</strong>
            <small>WBS + CBS + FBS</small>
          </article>
          <article>
            <span>Por revisar</span>
            <strong>{quantityNeedsMapping}</strong>
            <small>Lineas sin codificacion completa</small>
          </article>
        </div>
      </div>
      <div className="bimScopeNote" role="note">
        <strong>Objetivo del modulo</strong>
        <span>
          Carga el modelo o la plantilla de cantidades, verifica que cada elemento tenga cantidad y trazabilidad, y deja
          una sola tabla para asignarlo a WBS, CBS, FBS y paquete de trabajo.
        </span>
      </div>
      <section aria-label="Quantity provenance" className="bimEvidencePanel">
        <article>
          <span>Archivo fuente</span>
          <strong>
            {latestBimModel?.source_file_name ?? latestQuantityTakeoff?.source_file_name ?? "Sin fuente cargada"}
          </strong>
          <small>
            {latestBimModel
              ? `Modelo #${latestBimModel.id} / ${latestBimModel.schema || "IFC"} / ${(
                  latestBimModel.source_size_bytes /
                  (1024 * 1024)
                ).toFixed(2)} MB`
              : latestQuantityTakeoff
                ? `Run #${latestQuantityTakeoff.id} / v${latestQuantityTakeoff.version} / ${latestQuantityTakeoff.source_type.toUpperCase()}`
                : "Carga IFC, Excel o CSV"}
          </small>
        </article>
        <article>
          <span>Identidad del modelo</span>
          <strong>{quantityModelIdentity || "Se leera desde las cantidades"}</strong>
          <small>
            {latestBimModel && !quantityTakeoffLines.length
              ? "Faltan las lineas de cantidad extraidas"
              : `${quantityElementCount} referencia(s) / ${quantityClassCount} clase(s) IFC`}
          </small>
        </article>
        <article>
          <span>Base de cantidad</span>
          <strong>{quantitySourceBasis}</strong>
          <small>{quantityRuleSummary || "Reglas de medicion pendientes"}</small>
        </article>
        <article>
          <span>Vista y control</span>
          <strong>
            {latestBimModel
              ? "Modelo IFC registrado"
              : latestQuantityTakeoff?.source_type === "ifc"
                ? "Modelo IFC y tabla controlada"
                : "Tabla unica de cantidades"}
          </strong>
          <small>
            El visor muestra la geometria guardada; la tabla concentra cantidad, elemento y codigos de control.
          </small>
        </article>
      </section>
      <div className="bimAwpGateGrid">
        <article>
          <span>Ubicacion</span>
          <strong>{quantityTakeoffLines.length ? "Leida" : "Pendiente"}</strong>
          <small>Nivel, zona, sistema o conjunto ayudan a ordenar las cantidades.</small>
        </article>
        <article>
          <span>Elementos</span>
          <strong>
            {
              new Set(
                quantityTakeoffLines.map((line) =>
                  [line.ifc_class, line.type_name, line.unit, line.cbs_code].filter(Boolean).join("|")
                )
              ).size
            }
          </strong>
          <small>Agrupados por tipo, unidad, costo y ubicacion de control.</small>
        </article>
        <article>
          <span>Paquetes</span>
          <strong>{quantityTakeoffLines.filter((line) => line.package_code).length}</strong>
          <small>Listo cuando cada elemento tenga paquete de trabajo.</small>
        </article>
      </div>
    </>
  );
  const bimBudgetSummary = buildBimBudget(quantityTakeoffLines, project.currency);
  const setupReadyForActivityLoad = operationalSetup?.readiness_status === "ready" || isSetupDraftReady(setupDraft);
  const displayWbsCatalog =
    wbsCatalog.length > 1 ? wbsCatalog.filter((node) => !isDefaultProjectBaselineNode(node)) : wbsCatalog;
  const wbsTree = buildWbsTree(displayWbsCatalog);
  const primaryWbsTree = selectPrimaryWbsTree(wbsTree);
  const wbsTableRows = flattenWbsTree(primaryWbsTree);
  const shouldRenderProjectRoot = primaryWbsTree.length !== 1 || primaryWbsTree[0].children.length === 0;
  const backendActivityWbsByCode = new Map(activitySheetWbsRows.map((row) => [row.wbs_code, row]));
  const backendHasWbsRollups = activitySheetWbsRows.some((row) => {
    const node = displayWbsCatalog.find((candidate) => candidate.code === row.wbs_code);
    if (!node) return false;
    const childCodes = displayWbsCatalog
      .filter((candidate) => candidate.parent_id === node.id)
      .map((candidate) => candidate.code);
    const childActivityCount = childCodes.reduce(
      (total, code) => total + (backendActivityWbsByCode.get(code)?.activity_count ?? 0),
      0
    );
    return childActivityCount > 0 && row.activity_count >= childActivityCount;
  });
  const activityWbsByCode = backendHasWbsRollups
    ? backendActivityWbsByCode
    : buildActivityWbsRollupMap(primaryWbsTree, backendActivityWbsByCode);
  const activitySheetDisplayRows = wbsTableRows
    .map(({ node, depth }) => ({ depth, node, row: activityWbsByCode.get(node.code) }))
    .filter((item): item is { depth: number; node: WbsTreeNode; row: ActivitySheetWbsRow } => Boolean(item.row));
  const activitySheetUnmatchedRows = activitySheetWbsRows.filter(
    (row) => !displayWbsCatalog.some((node) => node.code === row.wbs_code)
  );
  const activitySheetTotalRows =
    primaryWbsTree.length > 0
      ? primaryWbsTree.map((node) => activityWbsByCode.get(node.code)).filter(Boolean)
      : activitySheetWbsRows;
  const activitySheetPlannedCost = activitySheetTotalRows.reduce((total, row) => total + (row?.planned_cost ?? 0), 0);
  const activitySheetNeedsReview = activitySheetTotalRows.reduce(
    (total, row) => total + (row?.needs_review_count ?? 0),
    0
  );
  const wbsTraceabilityRows = buildWbsTraceabilityRows(
    project,
    displayWbsCatalog,
    activeControlAccounts,
    dashboard.work_packages ?? [],
    integratedMatrix,
    cbsCatalog,
    costCodes,
    fbsFundingSources
  );
  const costFundingTraceabilityRows = buildCostFundingTraceabilityRows(
    wbsTraceabilityRows,
    cbsCostLines,
    fbsFundingSources,
    baselineOnlyEvm
  );
  const opcGapAnalysis = buildOpcGapAnalysis({
    activitySheetRowCount: activitySheetRows.length,
    activitySheetWbsCount: activitySheetWbsRows.length,
    apuCatalogCount: colombiaApuCatalog.length,
    bimModelCount: bimModelRuns.length,
    blockingConstraintCount: dashboard.awp_summary.blocking_constraints,
    controlAccountCount: activeControlAccounts.length,
    controlSnapshotCount: dashboard.control_snapshots.length,
    costLoadedActivityPercent: activeImport?.cost_loaded_activity_percent ?? 0,
    costSheetLineCount: cbsCostLines.length,
    evidenceScore: dashboard.document_control_summary.controlled_document_score,
    fundingSourceCount: fbsFundingSources.length,
    hasCostBaseline: projectEvm.bac > 0 || (activeImport?.total_imported_cost ?? 0) > 0,
    hasRenderableIfcGeometry,
    integratedMatrixRowCount: integratedMatrix.length,
    latestCostRecordCount: dashboard.latest_cost_records?.length ?? 0,
    latestProgressRecordCount: dashboard.latest_progress_records?.length ?? 0,
    processFlowCompletion: processFlowBoard?.completion_percent ?? 0,
    projectCode: project.code,
    quantityLineCount: quantityTakeoffLines.length,
    quantityMappedLineCount:
      latestQuantityTakeoff?.mapped_line_count ??
      quantityTakeoffLines.filter((line) => line.mapping_status === "mapped").length,
    quantityRuleBlockedCount,
    quantityRuleReviewCount,
    quantityRuleValidCount,
    scheduleActivityCount: dashboard.schedule_activity_count,
    scheduleQualityScore: activeImport?.quality_score ?? 0,
    scheduleRelationshipCount: dashboard.schedule_relationship_count,
    teamRoleCount: dashboard.project_team.length,
    workPackageCount: dashboard.awp_summary.total_packages,
    workPackageReadyCount: dashboard.awp_summary.ready_for_release,
  });
  const evmSummaryCards = [
    { label: "PV", value: currency(projectEvm.pv, project.currency), detail: "Valor planeado a la fecha de corte" },
    {
      label: "EV",
      value: currency(projectEvm.ev, project.currency),
      detail: "Valor ganado por avance fisico aprobado",
    },
    { label: "AC", value: currency(projectEvm.ac, project.currency), detail: "Costo real certificado o incurrido" },
    { label: "SPI", value: spiLabel, detail: "EV / PV", risk: projectEvm.spi !== null && projectEvm.spi < 0.95 },
    { label: "CPI", value: cpiLabel, detail: "EV / AC", risk: projectEvm.cpi !== null && projectEvm.cpi < 0.95 },
    { label: "SV", value: currency(projectEvm.sv, project.currency), detail: "EV - PV", risk: projectEvm.sv < 0 },
    { label: "CV", value: currency(projectEvm.cv, project.currency), detail: "EV - AC", risk: projectEvm.cv < 0 },
    { label: "BAC", value: currency(projectEvm.bac, project.currency), detail: "Presupuesto aprobado al completar" },
    { label: "EAC", value: currency(projectEvm.eac, project.currency), detail: "Estimado al completar" },
    { label: "VAC", value: currency(projectEvm.vac, project.currency), detail: "BAC - EAC", risk: projectEvm.vac < 0 },
  ];
  const forecastFundingRows = forecastFunding?.rows ?? [];
  const fundingAlerts = forecastFundingRows.filter((row) => row.forecast_vs_available < 0);
  const navigationStatusByView: Partial<Record<ControlFlowView, string | number>> = {
    "apu-catalog": colombiaApuCatalog.length ? colombiaApuCatalog.length : "sync",
    admin: users.length,
    "bim-budget": bimBudgetSummary.rows.length ? `${bimBudgetSummary.rows.length} partidas` : "open",
    "claims-audit": dashboard.claims_forensic_summary.total_claims
      ? `${dashboard.claims_forensic_summary.total_claims} claims`
      : "open",
    costs: dashboard.cost_sheet.length,
    decisions: dashboard.changes.length,
    "integrated-control": integratedMatrix.length,
    "process-flow": processFlowBoard ? `${processFlowBoard.completion_percent.toFixed(0)}%` : "open",
    progress: dashboard.latest_progress_records.length,
    "quantity-takeoff": latestQuantityTakeoff ? `${latestQuantityTakeoff.row_count} lines` : "open",
    "schedule-control": dashboard.schedule_activity_count ? `${dashboard.schedule_activity_count} activities` : "open",
    "schedule-intake": activeImport ? `${dashboard.schedule_activity_count} activities` : "open",
    setup: operationalSetup?.readiness_status === "ready" ? "ready" : "open",
    "window-analysis-37": windowAnalysisResult ? `${windowAnalysisResult.summary.net_delay_days ?? 0} dias` : "open",
    "work-packages": dashboard.awp_summary.total_packages,
  };
  const templateUserNavigationItems = USER_MODE_NAVIGATION_BLUEPRINT.map((macroprocess) => ({
    ...macroprocess,
    modules: macroprocess.modules.map((module) => ({
      ...module,
      submodules: module.submodules.map((submodule) => ({
        ...submodule,
        count: navigationStatusByView[submodule.key],
      })),
    })),
  }));
  const templateAdminNavigationItems = ADMIN_MODE_NAVIGATION_BLUEPRINT.map((module) => ({
    ...module,
    submodules: module.submodules.map((submodule) => ({
      ...submodule,
      count: navigationStatusByView[submodule.key],
    })),
  }));
  const activeModuleGuide: Partial<
    Record<ControlFlowView, { action: string; objective: string; state: string; title: string }>
  > = {
    admin: {
      action: "Create users, assign roles and configure project permissions.",
      objective: "Control who can configure, load, approve and operate each project workflow.",
      state: `${dashboard.project_team.length} project member(s)`,
      title: "User Creator",
    },
    "apu-catalog": {
      action: "Actualizar la base gratuita y revisar partidas antes de usarlas como sugerencias de presupuesto.",
      objective:
        "Mantener visible la base APU Colombia que conecta cantidades BIM con partida, unidad y precio unitario.",
      state: colombiaApuCatalog.length ? `${colombiaApuCatalog.length} partida(s)` : "Sin sincronizar",
      title: "Master Rate Sheet",
    },
    "claims-audit": {
      action: "Cargar expediente, revisar señales contractuales y completar la matriz antes de presentar el claim.",
      objective: "Convertir soportes de reclamacion en registros auditables: claim, aviso, entitlement e impacto.",
      state: `${dashboard.claims_forensic_summary.total_claims} claim(s) / ${dashboard.claims_forensic_summary.forensic_readiness_score.toFixed(0)}% readiness`,
      title: "Reclamaciones",
    },
    "window-analysis-37": {
      action:
        "Cargar dos o mas actualizaciones XER/XML ordenadas por fecha de corte y revisar las ventanas con impacto.",
      objective: "Identificar deslizamientos CPM entre bases multiples bajo el enfoque AACE RP29R MIP 3.7.",
      state: windowAnalysisResult
        ? `${windowAnalysisResult.windows.length} ventana(s) / ${windowAnalysisResult.summary.net_delay_days ?? 0} dia(s) netos`
        : "Sin corrida",
      title: "Ventanas 3.7",
    },
    "bim-budget": {
      action: bimBudgetSummary.rows.length
        ? "Revisar partidas, unidades, duplicados y trazabilidad antes de exportar el presupuesto."
        : `Asignar partida APU y precio unitario desde ${BIM_MANAGER_SUBMODULE_LABEL}.`,
      objective:
        "Consolidar cantidades IFC en partidas presupuestales trazables a WBS, CBS, FBS y elementos del modelo.",
      state: `${bimBudgetSummary.rows.length} partida(s) / ${
        bimBudgetSummary.gate === "ready" ? "listo" : bimBudgetSummary.gate === "review" ? "pendiente" : "bloqueado"
      }`,
      title: "Budget",
    },
    baseline: {
      action: "Resolve cost/currency blocks, review quality findings and approve the controlled baseline.",
      objective: "Freeze an approved schedule baseline only when the data quality and cost gates are ready.",
      state: activeImport ? `${activeImport.quality_score.toFixed(0)}% quality` : "Waiting for schedule",
      title: "Baseline Control",
    },
    costs: {
      action: "Review CBS, FBS, SOV, commitments, rates and funding exposure.",
      objective: "Keep cost and funding structures aligned to control accounts and business processes.",
      state: `${dashboard.cost_sheet.length} cost line(s)`,
      title: "Cost Items",
    },
    dashboard: {
      action: "Use the Next Controlled Action panel to open the next blocked or review-required module.",
      objective: "Read project health across baseline, progress, cost, funding, AWP and evidence.",
      state: `${spiLabel} SPI / ${cpiLabel} CPI`,
      title: "Dashboard",
    },
    "opc-gap": {
      action:
        opcGapAnalysis.nextActions[0] ??
        "Mantener el flujo BIM -> APU -> presupuesto -> EVM trazable antes de operar paquetes.",
      objective: "Evaluar la madurez del flujo de planificacion, BIM, costos, EVM y AWP con datos reales del proyecto.",
      state: `${opcGapAnalysis.readinessScore}% readiness / ${opcGapAnalysis.criticalGapCount} P1 gap(s)`,
      title: "Diagnóstico de Control",
    },
    decisions: {
      action: "Review open changes and decisions before they affect baseline, cost or package release.",
      objective: "Track project control decisions with visible status and ownership.",
      state: `${dashboard.changes.length} decision(s)`,
      title: "Scope Changes",
    },
    evidence: {
      action: "Review controlled documents and closeout evidence readiness.",
      objective: "Keep the documentary trail ready for approvals, handover and audit.",
      state: `${dashboard.document_control_summary.controlled_document_score.toFixed(0)}% controlled`,
      title: "Evidence",
    },
    "integrated-control": {
      action: "Run recost, review BP permissions, export reconciliation and audit exceptions.",
      objective: "Reconcile schedule, cost, commitments, funding and governance in one control layer.",
      state: `${integratedMatrix.length} matrix row(s)`,
      title: "Fund",
    },
    "process-flow": {
      action: "Open the lane item that is blocked or review-required.",
      objective: "See the full project control process by role, gate, evidence and next action.",
      state: processFlowBoard ? `${processFlowBoard.completion_percent.toFixed(0)}% complete` : "Loading",
      title: "Strategy&Path of Execution",
    },
    progress: {
      action: "Capture progress against the approved baseline and control account structure.",
      objective: "Convert field progress into earned value and productivity signals.",
      state: `${dashboard.latest_progress_records.length} progress record(s)`,
      title: "Measuring Progress",
    },
    "quantity-takeoff": {
      action: "Load prepared IFC quantity exports or Excel/CSV takeoff, then map WBS, CBS, FBS and packages.",
      objective:
        "Convert BIM/Excel data into controlled physical quantity items with source evidence before package assignment.",
      state: latestQuantityTakeoff ? `${latestQuantityTakeoff.row_count} quantity line(s)` : "Waiting for takeoff",
      title: BIM_MANAGER_SUBMODULE_LABEL,
    },
    "schedule-intake": {
      action: "Load P6 XML/XER, review data quality and confirm that Activity Sheet rows are controlled.",
      objective: "Bring the schedule source into the controlled baseline and Activity Sheet workflow.",
      state: activeImport ? `${dashboard.schedule_activity_count} activities loaded` : "Waiting for XML/XER",
      title: "Activity Sheet",
    },
    "schedule-control": {
      action: "Review WBS, baseline activities, CPM, progress, delays, lookahead constraints and recovery actions.",
      objective: "Use the imported P6 XML/XER data as the planning backbone: WBS, baseline, CPM, updates and recovery.",
      state: dashboard.schedule_activity_count
        ? `${dashboard.schedule_activity_count} imported activities`
        : "Waiting for schedule",
      title: "Schedule",
    },
    setup: {
      action: "Confirm operational readiness and maintain the WBS catalog before downstream loads.",
      objective: "Prepare project identity, roles, modules, cost/funding sheets and WBS controls.",
      state: operationalSetup?.readiness_status === "ready" ? "Ready" : "Open",
      title: "Asset Creator/Receipt",
    },
    "work-packages": {
      action: "Create or review package drafts and clear blocking constraints.",
      objective: "Move AWP package candidates toward release with visible constraints and evidence.",
      state: `${dashboard.awp_summary.total_packages} package(s)`,
      title: "Work Packages",
    },
    "project-creator": {
      action: "Crear un proyecto o administrar el proyecto seleccionado.",
      objective: "Crear y mantener los espacios de trabajo de proyectos.",
      state: `${projectList.length} project(s) available`,
      title: "Project Creator",
    },
  };
  const activeTemplateSubmodule = [
    ...USER_MODE_NAVIGATION_BLUEPRINT.flatMap((macroprocess) =>
      macroprocess.modules.flatMap((module) => module.submodules)
    ),
    ...ADMIN_MODE_NAVIGATION_BLUEPRINT.flatMap((module) => module.submodules),
  ].find((submodule) => submodule.key === visibleControlView);
  const currentModuleGuide =
    activeModuleGuide[visibleControlView] ??
    (activeTemplateSubmodule
      ? {
          action: "",
          objective: "",
          state: "",
          title: activeTemplateSubmodule.label,
        }
      : activeModuleGuide.dashboard!);
  const emptySubmoduleActive = EMPTY_SUBMODULE_VIEWS.has(visibleControlView);
  const formallyLinkedControlRows = wbsTraceabilityRows.filter(
    (row) => row.costCode !== "Cost code pending" && row.fbsCode !== "FBS pending"
  ).length;
  const informationFlowSteps: Array<{
    detail: string;
    label: string;
    status: string;
    targetView: ControlFlowView;
  }> = [
    {
      detail: "Project identity, roles and WBS establish the control backbone.",
      label: "Project and WBS",
      status: `${wbsTableRows.length} WBS / ${currentMembership?.role ?? "role pending"}`,
      targetView: "setup",
    },
    {
      detail: "P6 XML/XER and BIM/Excel quantities feed planning and physical progress.",
      label: "Schedule and quantities",
      status: `${dashboard.schedule_activity_count} activities / ${latestQuantityTakeoff?.row_count ?? 0} qty`,
      targetView: "schedule-intake",
    },
    {
      detail: "Quality, currency and cost loading decide whether the baseline can be approved.",
      label: "Baseline gate",
      status: activeImport ? `${activeImport.quality_score.toFixed(0)}% quality` : "waiting for schedule",
      targetView: "baseline",
    },
    {
      detail: "WBS connects to control accounts, CostCodes, CBS, FBS and commitments.",
      label: "CBS FBS CostCode",
      status: `${formallyLinkedControlRows}/${wbsTraceabilityRows.length} linked`,
      targetView: "integrated-control",
    },
    {
      detail: "Approved progress becomes EV, while AWP packages move by constraints and POC.",
      label: "EVM and AWP",
      status: `${spiLabel} SPI / ${dashboard.awp_summary.total_packages} packages`,
      targetView: "progress",
    },
    {
      detail: "Controlled documents, decisions and closeout evidence complete the audit trail.",
      label: "Evidence and closeout",
      status: `${dashboard.document_control_summary.controlled_document_score.toFixed(0)}% controlled`,
      targetView: "evidence",
    },
  ];
  const showOverviewChrome =
    !FRONTEND_VALIDATION_MODE && (visibleControlView === "dashboard" || visibleControlView === "process-flow");
  const guidedRailActiveKey =
    guidedFlow && visibleControlView === "dashboard" ? guidedFlow.next_action.target_view : visibleControlView;

  return (
    <main>
      {guidedFlow && (
        <header className="appBrandBar" aria-label="Application brand">
          <ProductLogo compact />
          <div className="appBrandActions">
            <ApplicationModeToggle mode={applicationMode} onToggle={handleApplicationModeToggle} />
            <span className="appBrandTagline">Project Controls Intelligence Platform</span>
          </div>
        </header>
      )}
      {guidedFlow ? (
        <TenantCommandBar
          project={guidedFlow.project}
          projects={projectList}
          selectedProjectId={selectedProjectId ?? project.id}
          onProjectChange={setSelectedProject}
          userEmail={user?.email ?? "Signed in"}
          userName={user?.full_name ?? ""}
          userTitle={user?.title ?? ""}
          onLogout={logout}
        />
      ) : (
        <header className="topbar">
          <div className="brandBlock">
            <ProductLogo compact />
            <p className="eyebrow">Project Controls</p>
            <h1>{project.name}</h1>
            <p className="productStatement">
              {project.code} / {project.phase} / {project.currency}
            </p>
          </div>
          <div className="headerActions">
            <ApplicationModeToggle mode={applicationMode} onToggle={handleApplicationModeToggle} />
            <div className="contextSwitch">
              <label>
                <span>Project</span>
                <select
                  onChange={(event) => setSelectedProject(Number(event.target.value))}
                  value={selectedProjectId ?? project.id}
                >
                  {projectList.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.code}
                    </option>
                  ))}
                </select>
              </label>
              <strong>{user?.email ?? "Signed in"}</strong>
              <button className="quickNavButton" onClick={logout} type="button">
                Logout
              </button>
              <button
                className="quickNavButton dangerButton"
                disabled={!canConfigure || projectDeleteAction}
                onClick={handleProjectDelete}
                type="button"
              >
                {projectDeleteAction ? "Deleting..." : "Delete Project"}
              </button>
            </div>
          </div>
        </header>
      )}

      <ProjectCreateDrawer
        canConfigure={canConfigure}
        draft={projectDraft}
        error={projectError}
        message={projectMessage}
        open={projectDrawerOpen}
        pending={projectAction}
        onClose={() => setProjectDrawerOpen(false)}
        onDraftChange={setProjectDraft}
        onSubmit={handleProjectCreate}
      />

      <section
        className={`${guidedFlow ? "projectWorkspace guidedWorkspace" : "projectWorkspace"}${
          moduleNavigationCollapsed ? " moduleRailCollapsed" : ""
        }`}
        aria-label="Project workspace and control flow"
      >
        <div className="projectWorkspaceRailDock">
          <div className="projectWorkspaceRailToggleDock">
            <button
              aria-controls="project-module-navigation"
              aria-expanded={!moduleNavigationCollapsed}
              aria-label={moduleNavigationCollapsed ? "Mostrar barra de módulos" : "Ocultar barra de módulos"}
              className="projectWorkspaceRailToggle"
              onClick={() => setModuleNavigationCollapsed((current) => !current)}
              title={moduleNavigationCollapsed ? "Mostrar barra de módulos" : "Ocultar barra de módulos"}
              type="button"
            >
              {moduleNavigationCollapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
            </button>
          </div>
          <aside className="projectWorkspaceRail" hidden={moduleNavigationCollapsed} id="project-module-navigation">
            {guidedFlow ? (
              <>
                <WorkspaceNavigation
                  activeView={visibleControlView}
                  adminItems={templateAdminNavigationItems}
                  applicationMode={applicationMode}
                  baselineOnlyEvm={baselineOnlyEvm}
                  onNavigate={handleControlFlowNavigate}
                  readinessScore={opcGapAnalysis.readinessScore}
                  spiLabel={spiLabel}
                  userItems={templateUserNavigationItems}
                  validationMode={FRONTEND_VALIDATION_MODE}
                />
                {!FRONTEND_VALIDATION_MODE && applicationMode === "user" && (
                  <GuidedProcessRail
                    activeKey={guidedRailActiveKey}
                    steps={guidedFlow.steps}
                    onNavigate={(targetView) => handleControlFlowNavigate(targetView as ControlFlowView)}
                  />
                )}
                {!FRONTEND_VALIDATION_MODE && applicationMode === "user" && (
                  <details className="projectAdminDetails" role="group" aria-label="Administrative actions">
                    <summary>
                      <span>
                        <Building2 size={16} /> Proyecto
                      </span>
                      <strong>Crear o borrar proyectos</strong>
                    </summary>
                    <div className="projectAdminBody">
                      <div className="projectCurrentProject">
                        <span>Selected project</span>
                        <strong>{project.code}</strong>
                        <small>{projectList.length} projects available</small>
                      </div>
                      <button
                        className="workflowAction"
                        disabled={!canConfigure}
                        onClick={() => setProjectDrawerOpen(true)}
                        type="button"
                      >
                        New Project
                      </button>
                      <button
                        className="workflowAction subtleDanger"
                        disabled={!canConfigure || projectDeleteAction}
                        onClick={handleProjectDelete}
                        type="button"
                      >
                        <Trash2 size={15} /> {projectDeleteAction ? "Deleting..." : "Delete Project"}
                      </button>
                      <p className="projectHint">
                        Project creation and deletion are administrative actions, separated from the daily control flow.
                      </p>
                    </div>
                  </details>
                )}
              </>
            ) : (
              <WorkspaceNavigation
                activeView={visibleControlView}
                adminItems={templateAdminNavigationItems}
                applicationMode={applicationMode}
                baselineOnlyEvm={baselineOnlyEvm}
                onNavigate={handleControlFlowNavigate}
                readinessScore={opcGapAnalysis.readinessScore}
                spiLabel={spiLabel}
                userItems={templateUserNavigationItems}
                validationMode={FRONTEND_VALIDATION_MODE}
              />
            )}

            {!guidedFlow && applicationMode === "user" && (
              <section className="adminPanel projectCreatePanel" aria-label="Project">
                <div className="panelHeader">
                  <h2>
                    <Building2 size={18} /> Project
                  </h2>
                  {!guidedFlow && (
                    <button
                      className="quickNavButton"
                      disabled={!canConfigure}
                      onClick={() => setShowProjectCreate((current) => !current)}
                      type="button"
                    >
                      {showProjectCreate ? "Close" : "New Project"}
                    </button>
                  )}
                </div>
                <div className="projectCurrentProject">
                  <span>Selected project</span>
                  <strong>{project.code}</strong>
                  <small>{projectList.length} projects available</small>
                  <button
                    className="workflowAction subtleDanger"
                    disabled={!canConfigure || projectDeleteAction}
                    onClick={handleProjectDelete}
                    type="button"
                  >
                    <Trash2 size={15} /> {projectDeleteAction ? "Deleting..." : "Delete Project"}
                  </button>
                </div>

                {!guidedFlow && showProjectCreate ? (
                  <form className="projectCreateForm" onSubmit={handleProjectCreate}>
                    <div className="formColumns">
                      <label>
                        <span>Code</span>
                        <input
                          disabled={!canConfigure || projectAction}
                          onChange={(event) => setProjectDraft((current) => ({ ...current, code: event.target.value }))}
                          placeholder="PRJ-001"
                          required
                          value={projectDraft.code}
                        />
                      </label>
                      <label>
                        <span>Phase</span>
                        <select
                          disabled={!canConfigure || projectAction}
                          onChange={(event) =>
                            setProjectDraft((current) => ({ ...current, phase: event.target.value }))
                          }
                          value={projectDraft.phase}
                        >
                          <option value="Planning">Planning</option>
                          <option value="Execution">Execution</option>
                          <option value="Closeout">Closeout</option>
                        </select>
                      </label>
                    </div>
                    <label>
                      <span>Name</span>
                      <input
                        disabled={!canConfigure || projectAction}
                        onChange={(event) => setProjectDraft((current) => ({ ...current, name: event.target.value }))}
                        placeholder="Project control name"
                        required
                        value={projectDraft.name}
                      />
                    </label>
                    <div className="formColumns">
                      <label>
                        <span>Owner</span>
                        <input
                          disabled={!canConfigure || projectAction}
                          onChange={(event) =>
                            setProjectDraft((current) => ({ ...current, owner: event.target.value }))
                          }
                          value={projectDraft.owner}
                        />
                      </label>
                      <label>
                        <span>Base Calendar</span>
                        <input
                          disabled={!canConfigure || projectAction}
                          onChange={(event) =>
                            setProjectDraft((current) => ({ ...current, calendar_base: event.target.value }))
                          }
                          value={projectDraft.calendar_base}
                        />
                      </label>
                    </div>
                    <div className="formColumns">
                      <label>
                        <span>Status</span>
                        <select
                          disabled={!canConfigure || projectAction}
                          onChange={(event) =>
                            setProjectDraft((current) => ({ ...current, status: event.target.value }))
                          }
                          value={projectDraft.status}
                        >
                          <option value="draft">Draft</option>
                          <option value="authorized">Authorized</option>
                          <option value="baseline_approved">Baseline Approved</option>
                          <option value="in_execution">In Execution</option>
                          <option value="closed">Closed</option>
                        </select>
                      </label>
                      <label>
                        <span>Authorization Reference</span>
                        <input
                          disabled={!canConfigure || projectAction}
                          onChange={(event) =>
                            setProjectDraft((current) => ({ ...current, authorization_ref: event.target.value }))
                          }
                          value={projectDraft.authorization_ref}
                        />
                      </label>
                      <label>
                        <span>Authorization Date</span>
                        <input
                          disabled={!canConfigure || projectAction}
                          onChange={(event) =>
                            setProjectDraft((current) => ({ ...current, authorization_date: event.target.value }))
                          }
                          type="date"
                          value={projectDraft.authorization_date}
                        />
                      </label>
                    </div>
                    <div className="formColumns">
                      <label>
                        <span>Currency</span>
                        <input
                          disabled={!canConfigure || projectAction}
                          maxLength={3}
                          onChange={(event) =>
                            setProjectDraft((current) => ({ ...current, currency: event.target.value.toUpperCase() }))
                          }
                          value={projectDraft.currency}
                        />
                      </label>
                      <label>
                        <span>Start</span>
                        <input
                          disabled={!canConfigure || projectAction}
                          onChange={(event) =>
                            setProjectDraft((current) => ({ ...current, start_date: event.target.value }))
                          }
                          type="date"
                          value={projectDraft.start_date}
                        />
                      </label>
                      <label>
                        <span>Finish</span>
                        <input
                          disabled={!canConfigure || projectAction}
                          onChange={(event) =>
                            setProjectDraft((current) => ({ ...current, finish_date: event.target.value }))
                          }
                          type="date"
                          value={projectDraft.finish_date}
                        />
                      </label>
                    </div>
                    <div className="formColumns">
                      <label>
                        <span>Control Level</span>
                        <select
                          disabled={!canConfigure || projectAction}
                          onChange={(event) =>
                            setProjectDraft((current) => ({ ...current, control_level: event.target.value }))
                          }
                          value={projectDraft.control_level}
                        >
                          <option value="control_account">Control Account</option>
                          <option value="cost_code">Cost Code</option>
                          <option value="awp_package">AWP Package</option>
                        </select>
                      </label>
                      <label className="checkboxLine">
                        <input
                          checked={projectDraft.funding_required}
                          disabled={!canConfigure || projectAction}
                          onChange={(event) =>
                            setProjectDraft((current) => ({ ...current, funding_required: event.target.checked }))
                          }
                          type="checkbox"
                        />
                        <span>Funding Required</span>
                      </label>
                    </div>
                    <button className="workflowAction primary" disabled={!canConfigure || projectAction} type="submit">
                      {projectAction ? "Creating..." : "Create Project"}
                    </button>
                  </form>
                ) : (
                  <p className="projectHint">
                    The selected project dashboard is open. Create a project only when onboarding a new project.
                  </p>
                )}
                {projectMessage && <div className="uploadMessage success">{projectMessage}</div>}
                {projectError && <div className="uploadMessage error">{projectError}</div>}
              </section>
            )}
          </aside>
        </div>

        <section className="projectDashboardArea" aria-label="Control dashboard">
          {showOverviewChrome && (
            <section className="controlSummary">
              <div>
                <span>PV</span>
                <strong>{currency(projectEvm.pv, project.currency)}</strong>
              </div>
              <div>
                <span>EV</span>
                <strong>{currency(projectEvm.ev, project.currency)}</strong>
              </div>
              <div>
                <span>AC</span>
                <strong>{currency(projectEvm.ac, project.currency)}</strong>
              </div>
              <div>
                <span>SPI</span>
                <strong>{spiLabel}</strong>
              </div>
              <div>
                <span>CPI</span>
                <strong>{cpiLabel}</strong>
              </div>
              <div>
                <span>AWP Ready</span>
                <strong>{dashboard.awp_summary.readiness_score.toFixed(1)}%</strong>
              </div>
            </section>
          )}

          {showOverviewChrome && (
            <section className="flowBand informationFlowBand" aria-label="Project information flow map">
              <div className="flowBandHeader">
                <span>Project Information Flow</span>
                <strong>Follow the data, not the menus</strong>
              </div>
              <div className="informationFlowTrack">
                {informationFlowSteps.map((step, index) => (
                  <button
                    aria-label={`${index + 1} ${step.label}`}
                    className={
                      visibleControlView === step.targetView ? "informationFlowStep active" : "informationFlowStep"
                    }
                    key={step.label}
                    onClick={() => handleControlFlowNavigate(step.targetView)}
                    type="button"
                  >
                    <em>{index + 1}</em>
                    <span>{step.label}</span>
                    <strong>{step.status}</strong>
                    <small>{step.detail}</small>
                  </button>
                ))}
              </div>
            </section>
          )}

          {guidedFlow && nextActionStep && !FRONTEND_VALIDATION_MODE && (
            <NextActionPanel
              action={guidedFlow.next_action}
              step={nextActionStep}
              onNavigate={(targetView) => handleControlFlowNavigate(targetView as ControlFlowView)}
            />
          )}

          {!emptySubmoduleActive && (
            <section className="moduleGuide" aria-label="Current module guide">
              <div className="moduleGuideIntro">
                <span>Current module</span>
                <strong className="moduleGuideTitle">{currentModuleGuide.title}</strong>
                <p>{currentModuleGuide.objective}</p>
              </div>
              <div className="moduleGuideFacts">
                <article>
                  <span>Status</span>
                  <strong>{currentModuleGuide.state}</strong>
                </article>
                <article>
                  <span>Next action</span>
                  <strong>{currentModuleGuide.action}</strong>
                </article>
              </div>
            </section>
          )}

          <section aria-live="polite" className="viewPanel workspaceSection" id="control-flow-content">
            {visibleControlView === "opc-gap" && <OpcGapReadinessPanel analysis={opcGapAnalysis} />}

            {visibleControlView === "project-creator" && (
              <section aria-label="Project Creator Module" className="projectCreatorModule">
                <div className="panelHeader">
                  <h2>
                    <Building2 size={20} /> Project Creator
                  </h2>
                  <span>{projectList.length} projects available</span>
                </div>
                <div className="projectCreatorWorkspace">
                  <article className="projectCreatorCurrent">
                    <span>Selected project</span>
                    <strong>{project.code}</strong>
                    <small>{project.name}</small>
                  </article>
                  <div className="projectCreatorActions">
                    <button
                      className="workflowAction"
                      disabled={!canConfigure}
                      onClick={() => setProjectDrawerOpen(true)}
                      type="button"
                    >
                      New Project
                    </button>
                    <button
                      className="workflowAction subtleDanger"
                      disabled={!canConfigure || projectDeleteAction}
                      onClick={handleProjectDelete}
                      type="button"
                    >
                      <Trash2 size={15} /> {projectDeleteAction ? "Deleting..." : "Delete Project"}
                    </button>
                  </div>
                </div>
              </section>
            )}

            {emptySubmoduleActive && activeTemplateSubmodule ? (
              <section aria-label={`${activeTemplateSubmodule.label} Module`} className="emptySubmoduleScreen">
                <h2>{activeTemplateSubmodule.label}</h2>
              </section>
            ) : null}

            {visibleControlView === "schedule-intake" && (
              <section className="scheduleGate scheduleIntakeModule" aria-label="Activity Sheet">
                <div className="gateHeader">
                  <div className="gateIntro">
                    <GitBranch size={20} />
                    <div>
                      <strong>Activity Sheet</strong>
                      <span>Upload the source XML/XER to open the Data Quality Gate and baseline workflow.</span>
                    </div>
                  </div>
                  <label className={uploading ? "uploadButton disabled" : "uploadButton"}>
                    <FileUp size={18} />
                    <span>{uploading ? "Uploading..." : "Schedule XML or XER"}</span>
                    <input
                      aria-label="Schedule XML or XER"
                      accept=".xml,.xer"
                      disabled={!canUploadSchedule || uploading}
                      onChange={handleScheduleUpload}
                      type="file"
                    />
                  </label>
                </div>
                <div className="gateFacts">
                  <div>
                    <span>Current Baseline</span>
                    <strong>{activeImport?.baseline_name ?? "Pending upload"}</strong>
                  </div>
                  <div>
                    <span>Data Quality Gate</span>
                    <strong>
                      {activeImport ? `${activeImport.quality_score.toFixed(0)}% / ${activeImport.status}` : "Open"}
                    </strong>
                  </div>
                  <div>
                    <span>Data Date</span>
                    <strong>{activeImport?.data_date ?? "Pending"}</strong>
                  </div>
                  <div>
                    <span>Activities</span>
                    <strong>{dashboard.schedule_activity_count}</strong>
                  </div>
                  <div>
                    <span>Findings</span>
                    <strong>{dashboard.schedule_findings.length}</strong>
                  </div>
                </div>
                <p>
                  The approved baseline feeds Activity Sheet rows, control accounts, AWP packages, progress capture,
                  cost loading and Control Core decisions.
                </p>
                <div className="viewSplit">
                  <div className="panel">
                    <div className="panelHeader compactHeader">
                      <h2>
                        <FileUp size={18} /> Activity Sheet
                      </h2>
                      <span>{activitySheets.length} loads</span>
                    </div>
                    <label
                      className={
                        activityAction || !setupReadyForActivityLoad ? "uploadButton disabled" : "uploadButton"
                      }
                    >
                      <input
                        accept=".xml,.xer"
                        disabled={!canUploadSchedule || activityAction || !setupReadyForActivityLoad}
                        onChange={handleActivitySheetUpload}
                        type="file"
                      />
                      <span>{activityAction ? "Loading..." : "Load XML/XER"}</span>
                    </label>
                    <div className="workList compactList">
                      {activitySheets.slice(0, 6).map((sheet) => (
                        <article key={sheet.id}>
                          <strong>{sheet.source_file_name}</strong>
                          <span>
                            {sheet.row_count} rows / {statusLabel(sheet.status)}
                          </span>
                          <small>{sheet.data_date ?? "No data date"}</small>
                        </article>
                      ))}
                      {!activitySheets.length && (
                        <article>
                          <strong>No activity loads</strong>
                          <span>Activity data will appear after controlled load.</span>
                        </article>
                      )}
                    </div>
                  </div>
                  <div className="panel">
                    <div className="panelHeader compactHeader">
                      <h2>WBS Sheet</h2>
                      <span>
                        {activitySheetDisplayRows.length || activitySheetWbsRows.length} WBS /{" "}
                        {currency(activitySheetPlannedCost, project.currency)}
                      </span>
                    </div>
                    {activitySheetDisplayRows.length || activitySheetUnmatchedRows.length ? (
                      <table>
                        <thead>
                          <tr>
                            <th>WBS</th>
                            <th>Activities</th>
                            <th>PV</th>
                            <th>Review</th>
                          </tr>
                        </thead>
                        <tbody>
                          {[
                            ...activitySheetDisplayRows,
                            ...activitySheetUnmatchedRows.map((row) => ({ depth: 0, node: null, row })),
                          ]
                            .slice(0, 6)
                            .map(({ depth, node, row }) => (
                              <tr key={row.wbs_code}>
                                <td className="wbsNameCell" style={{ paddingLeft: `${12 + depth * 18}px` }}>
                                  <strong>{node?.name ?? row.wbs_name}</strong>
                                  <span>{publicWbsCode(node?.code ?? row.wbs_code, project)}</span>
                                </td>
                                <td>{row.activity_count}</td>
                                <td>{currency(row.planned_value, project.currency)}</td>
                                <td>{row.needs_review_count}</td>
                              </tr>
                            ))}
                        </tbody>
                      </table>
                    ) : (
                      <div className="workspaceEmpty compactEmpty">
                        <strong>WBS Sheet pending</strong>
                      </div>
                    )}
                  </div>
                </div>
                {uploadMessage && <div className="uploadMessage success">{uploadMessage}</div>}
                {uploadError && <div className="uploadMessage error">{uploadError}</div>}
                {setupMessage && <div className="uploadMessage success">{setupMessage}</div>}
                {setupError && <div className="uploadMessage error">{setupError}</div>}
                {!canUploadSchedule && (
                  <div className="uploadMessage error">Only Planner or Control Manager roles can upload baselines.</div>
                )}
              </section>
            )}
            {visibleControlView === "schedule-control" && (
              <ProjectControlsHandbook
                currencyCode={project.currency}
                key={project.id}
                projectCode={project.code}
                projectId={project.id}
                scheduleActivities={scheduleActivities}
                scheduleDataDate={dashboard.schedule_import?.data_date ?? null}
                scheduleRelationships={scheduleRelationships}
                wbsCatalog={wbsCatalog}
              />
            )}
            {visibleControlView === "process-flow" && (
              <>
                <div className="panelHeader">
                  <h2>Strategy&amp;Path of Execution</h2>
                  <span>
                    {processFlowBoard
                      ? `${statusLabel(processFlowBoard.overall_status)} / ${processFlowBoard.completion_percent.toFixed(1)}%`
                      : "Loading"}
                  </span>
                </div>
                {processFlowBoard ? (
                  <div className="processFlowBoard">
                    {processFlowBoard.lanes.map((lane) => (
                      <section className="processLane" key={lane.key} aria-label={lane.label}>
                        <div className="processLaneHeader">
                          <strong>{lane.label}</strong>
                          <span>{lane.owner_role}</span>
                        </div>
                        <div className="processLaneItems">
                          {lane.items.map((item) => (
                            <article
                              aria-label={`Open ${item.label}`}
                              className={`processFlowItem ${item.status}`}
                              key={item.key}
                              onClick={() => handleControlFlowNavigate(item.target_view as ControlFlowView)}
                              onKeyDown={(event) => {
                                if (event.key === "Enter" || event.key === " ") {
                                  event.preventDefault();
                                  handleControlFlowNavigate(item.target_view as ControlFlowView);
                                }
                              }}
                              role="button"
                              tabIndex={0}
                            >
                              <div className="processItemHeader">
                                <strong>{item.label}</strong>
                                <span className={`qualityStatus ${processStatusTone(item.status)}`}>
                                  {statusLabel(item.status)}
                                </span>
                              </div>
                              <p>{item.evidence}</p>
                              <small>{item.next_action}</small>
                              <ul>
                                {item.acceptance_criteria.map((criterion) => (
                                  <li key={criterion}>{criterion}</li>
                                ))}
                              </ul>
                            </article>
                          ))}
                        </div>
                      </section>
                    ))}
                  </div>
                ) : (
                  <div className="emptyState compactEmpty">
                    <strong>Process board pending</strong>
                    <p>The BPM process board will load after the project context is available.</p>
                  </div>
                )}
              </>
            )}
            {visibleControlView === "setup" && (
              <>
                <div className="panelHeader">
                  <h2>Asset Creator/Receipt</h2>
                  <span>{operationalSetup?.readiness_status === "ready" ? "Ready" : "Open"}</span>
                </div>
                <section aria-label="WBS Structure" className="panel wide wbsStructurePanel">
                  <div className="panelHeader compactHeader">
                    <h2>
                      <GitBranch size={18} /> WBS Structure
                    </h2>
                    <span>{wbsTableRows.length} nodes</span>
                  </div>
                  {primaryWbsTree.length ? (
                    <div aria-label={`WBS tree for ${project.code}`} className="wbsTreeCanvas" role="tree">
                      {shouldRenderProjectRoot ? (
                        <div className="wbsProjectTreeRoot">
                          <article
                            aria-label={`${project.code} ${project.name}`}
                            aria-level={1}
                            className="wbsNodeCard projectRoot"
                            role="treeitem"
                          >
                            <strong>{project.code}</strong>
                            <span>{project.name}</span>
                            <small>Project</small>
                          </article>
                          <div className="wbsChildren wbsProjectChildren">
                            {primaryWbsTree.map((node) => (
                              <WbsTreeBranch
                                activityByCode={activityWbsByCode}
                                currencyCode={project.currency}
                                depth={1}
                                key={node.id}
                                node={node}
                                project={project}
                              />
                            ))}
                          </div>
                        </div>
                      ) : (
                        <div className="wbsTreeRoots">
                          {primaryWbsTree.map((node) => (
                            <WbsTreeBranch
                              activityByCode={activityWbsByCode}
                              currencyCode={project.currency}
                              depth={0}
                              key={node.id}
                              node={node}
                              project={project}
                            />
                          ))}
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="workspaceEmpty compactEmpty">
                      <strong>No WBS nodes</strong>
                    </div>
                  )}
                  <section aria-label="WBS Table" className="wbsTablePanel">
                    <div className="panelHeader compactHeader">
                      <h2>WBS Table</h2>
                      <span>{wbsTableRows.length} rows</span>
                    </div>
                    {wbsTableRows.length ? (
                      <table>
                        <thead>
                          <tr>
                            <th>WBS</th>
                            <th>Parent</th>
                            <th>Level</th>
                            <th>Status</th>
                            <th>Activities</th>
                            <th>Planned</th>
                          </tr>
                        </thead>
                        <tbody>
                          {wbsTableRows.map(({ node, depth }) => {
                            const parent = node.parent_id
                              ? wbsTableRows.find((item) => item.node.id === node.parent_id)?.node
                              : null;
                            const activityRollup = activityWbsByCode.get(node.code);
                            const visualDepth = depth + 1;
                            return (
                              <tr key={node.id}>
                                <td className="wbsNameCell" style={{ paddingLeft: `${12 + visualDepth * 18}px` }}>
                                  <strong>{node.name}</strong>
                                  <span>{publicWbsCode(node.code, project)}</span>
                                </td>
                                <td>{parent?.name ?? "Project"}</td>
                                <td>{node.level}</td>
                                <td>{statusLabel(node.status)}</td>
                                <td>{activityRollup?.activity_count ?? 0}</td>
                                <td>{currency(activityRollup?.planned_cost ?? 0, project.currency)}</td>
                              </tr>
                            );
                          })}
                        </tbody>
                      </table>
                    ) : (
                      <div className="workspaceEmpty compactEmpty">
                        <strong>WBS table pending</strong>
                      </div>
                    )}
                  </section>
                </section>
                <div className="viewSplit">
                  <form className="adminPanel" onSubmit={handleOperationalSetupSubmit}>
                    <div className="panelHeader compactHeader">
                      <h2>Operational Readiness</h2>
                      <span>{operationalSetup?.readiness_notes ?? "Pending setup"}</span>
                    </div>
                    <div className="formColumns">
                      <label>
                        <span>Project Number</span>
                        <input
                          disabled={!canConfigure || setupAction}
                          onChange={(event) =>
                            setSetupDraft((current) => ({ ...current, project_number: event.target.value }))
                          }
                          required
                          value={setupDraft.project_number}
                        />
                      </label>
                      <label>
                        <span>Status</span>
                        <select
                          disabled={!canConfigure || setupAction}
                          onChange={(event) => setSetupDraft((current) => ({ ...current, status: event.target.value }))}
                          value={setupDraft.status}
                        >
                          <option value="draft">Draft</option>
                          <option value="in_review">In Review</option>
                          <option value="ready">Ready</option>
                          <option value="active">Active</option>
                        </select>
                      </label>
                    </div>
                    <details className="advancedFields">
                      <summary>Advanced setup template</summary>
                      <div className="advancedFieldsBody">
                        <label>
                          <span>Setup Template</span>
                          <input
                            disabled={!canConfigure || setupAction}
                            onChange={(event) =>
                              setSetupDraft((current) => ({ ...current, setup_template: event.target.value }))
                            }
                            required
                            value={setupDraft.setup_template}
                          />
                        </label>
                        <label>
                          <span>Attribute Form</span>
                          <input
                            disabled={!canConfigure || setupAction}
                            onChange={(event) =>
                              setSetupDraft((current) => ({ ...current, attribute_form: event.target.value }))
                            }
                            required
                            value={setupDraft.attribute_form}
                          />
                        </label>
                      </div>
                    </details>
                    <div className="formColumns">
                      {[
                        ["permissions_configured", "Permissions"],
                        ["modules_configured", "Modules"],
                        ["cost_sheet_ready", "Cost Sheet"],
                        ["funding_sheet_ready", "Funding Sheet"],
                        ["p6_mapping_ready", "P6 Mapping"],
                      ].map(([field, label]) => (
                        <label className="checkboxLine" key={field}>
                          <input
                            checked={Boolean(setupDraft[field as keyof typeof setupDraft])}
                            disabled={!canConfigure || setupAction}
                            onChange={(event) =>
                              setSetupDraft((current) => ({ ...current, [field]: event.target.checked }))
                            }
                            type="checkbox"
                          />
                          <span>{label}</span>
                        </label>
                      ))}
                    </div>
                    <button className="workflowAction primary" disabled={!canConfigure || setupAction} type="submit">
                      {setupAction ? "Saving..." : "Save Setup"}
                    </button>
                  </form>

                  <div className="panel">
                    <div className="panelHeader compactHeader">
                      <h2>
                        <FileUp size={18} /> Activity Sheet
                      </h2>
                      <span>{activitySheets.length} loads</span>
                    </div>
                    <label
                      className={
                        activityAction || !setupReadyForActivityLoad ? "uploadButton disabled" : "uploadButton"
                      }
                    >
                      <input
                        accept=".xml,.xer"
                        disabled={!canUploadSchedule || activityAction || !setupReadyForActivityLoad}
                        onChange={handleActivitySheetUpload}
                        type="file"
                      />
                      <span>{activityAction ? "Loading..." : "Load XML/XER"}</span>
                    </label>
                    <div className="workList compactList">
                      {activitySheets.slice(0, 6).map((sheet) => (
                        <article key={sheet.id}>
                          <strong>{sheet.source_file_name}</strong>
                          <span>
                            {sheet.row_count} rows / {statusLabel(sheet.status)}
                          </span>
                          <small>{sheet.data_date ?? "No data date"}</small>
                        </article>
                      ))}
                      {!activitySheets.length && (
                        <article>
                          <strong>No activity loads</strong>
                          <span>Activity data will appear after controlled load.</span>
                        </article>
                      )}
                    </div>
                  </div>
                </div>
                <section aria-label="WBS Catalog" className="panel wide">
                  <div className="panelHeader compactHeader">
                    <h2>
                      <GitBranch size={18} /> WBS Catalog
                    </h2>
                    <span>{wbsCatalog.length} nodes</span>
                  </div>
                  <div className="viewSplit">
                    <form className="adminPanel compactForm wbsCatalogForm" onSubmit={handleWbsCreate}>
                      <label>
                        <span>WBS Code</span>
                        <input
                          disabled={!canConfigure || wbsAction}
                          onChange={(event) => setWbsDraft((current) => ({ ...current, code: event.target.value }))}
                          required
                          value={wbsDraft.code}
                        />
                      </label>
                      <label>
                        <span>WBS Name</span>
                        <input
                          disabled={!canConfigure || wbsAction}
                          onChange={(event) => setWbsDraft((current) => ({ ...current, name: event.target.value }))}
                          required
                          value={wbsDraft.name}
                        />
                      </label>
                      <label>
                        <span>Parent WBS</span>
                        <select
                          disabled={!canConfigure || wbsAction}
                          onChange={(event) => {
                            const nextParentId = event.target.value;
                            const parentNode = wbsCatalog.find((node) => String(node.id) === nextParentId);
                            setWbsDraft((current) => ({
                              ...current,
                              parent_id: nextParentId,
                              level: parentNode ? String(parentNode.level + 1) : "1",
                            }));
                          }}
                          value={wbsDraft.parent_id}
                        >
                          <option value="">Root WBS</option>
                          {wbsCatalog.map((node) => (
                            <option key={node.id} value={node.id}>
                              {publicWbsCode(node.code, project)} - {node.name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <details className="advancedFields">
                        <summary>Advanced WBS metadata</summary>
                        <div className="advancedFieldsBody">
                          <div className="formColumns">
                            <label>
                              <span>Level</span>
                              <input
                                disabled={!canConfigure || wbsAction}
                                min="1"
                                onChange={(event) =>
                                  setWbsDraft((current) => ({ ...current, level: event.target.value }))
                                }
                                type="number"
                                value={wbsDraft.level}
                              />
                            </label>
                            <label>
                              <span>Status</span>
                              <select
                                disabled={!canConfigure || wbsAction}
                                onChange={(event) =>
                                  setWbsDraft((current) => ({ ...current, status: event.target.value }))
                                }
                                value={wbsDraft.status}
                              >
                                <option value="active">Active</option>
                                <option value="draft">Draft</option>
                                <option value="in_review">In Review</option>
                              </select>
                            </label>
                          </div>
                          <label>
                            <span>Responsible</span>
                            <input
                              disabled={!canConfigure || wbsAction}
                              onChange={(event) =>
                                setWbsDraft((current) => ({ ...current, responsible: event.target.value }))
                              }
                              value={wbsDraft.responsible}
                            />
                          </label>
                          <label>
                            <span>Description</span>
                            <textarea
                              disabled={!canConfigure || wbsAction}
                              onChange={(event) =>
                                setWbsDraft((current) => ({ ...current, description: event.target.value }))
                              }
                              rows={3}
                              value={wbsDraft.description}
                            />
                          </label>
                        </div>
                      </details>
                      <button className="workflowAction primary" disabled={!canConfigure || wbsAction} type="submit">
                        {wbsAction ? "Creating..." : "Create WBS"}
                      </button>
                    </form>
                    <div className="workList compactList">
                      {wbsCatalog.slice(0, 10).map((node) => {
                        const parent = node.parent_id ? wbsCatalog.find((item) => item.id === node.parent_id) : null;
                        return (
                          <article key={node.id}>
                            <strong>{node.name}</strong>
                            <span>{publicWbsCode(node.code, project)}</span>
                            <small>
                              Level {node.level} / {parent ? `Parent ${parent.name}` : "Root"} /{" "}
                              {statusLabel(node.status)}
                            </small>
                            {node.responsible && <small>{node.responsible}</small>}
                          </article>
                        );
                      })}
                      {!wbsCatalog.length && (
                        <article>
                          <strong>No WBS nodes</strong>
                          <span>Create the first WBS or load a P6 XML/XER source.</span>
                        </article>
                      )}
                    </div>
                  </div>
                </section>
                {integratedMessage && <div className="uploadMessage success">{integratedMessage}</div>}
                {integratedError && <div className="uploadMessage error">{integratedError}</div>}
                <div className="panel wide">
                  <div className="panelHeader compactHeader">
                    <h2>WBS Sheet</h2>
                    <span>
                      {activitySheetDisplayRows.length || activitySheetWbsRows.length} WBS /{" "}
                      {currency(activitySheetPlannedCost, project.currency)}
                    </span>
                  </div>
                  {activitySheetDisplayRows.length || activitySheetUnmatchedRows.length ? (
                    <table>
                      <thead>
                        <tr>
                          <th>WBS</th>
                          <th>Activities</th>
                          <th>Control Accounts</th>
                          <th>PV</th>
                          <th>Review</th>
                        </tr>
                      </thead>
                      <tbody>
                        {[
                          ...activitySheetDisplayRows,
                          ...activitySheetUnmatchedRows.map((row) => ({ depth: 0, node: null, row })),
                        ]
                          .slice(0, 8)
                          .map(({ depth, node, row }) => (
                            <tr key={row.wbs_code}>
                              <td className="wbsNameCell" style={{ paddingLeft: `${12 + depth * 18}px` }}>
                                <strong>{node?.name ?? row.wbs_name}</strong>
                                <span>{publicWbsCode(node?.code ?? row.wbs_code, project)}</span>
                              </td>
                              <td>{row.activity_count}</td>
                              <td>{row.control_account_count}</td>
                              <td>
                                <strong>{currency(row.planned_value, project.currency)}</strong>
                                <span>{currency(row.planned_cost, project.currency)} planned</span>
                              </td>
                              <td>
                                <strong>{row.needs_review_count}</strong>
                                <span>{row.unmapped_activity_count} unmapped</span>
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  ) : (
                    <div className="workspaceEmpty compactEmpty">
                      <strong>WBS Sheet pending</strong>
                      <p>WBS roll-up will appear after the first controlled Activity Sheet load.</p>
                    </div>
                  )}
                  {activitySheetNeedsReview > 0 && (
                    <div className="uploadMessage error">
                      {activitySheetNeedsReview} activity rows need CBS, cost or control-account review.
                    </div>
                  )}
                </div>
                <div className="panel wide">
                  <div className="panelHeader compactHeader">
                    <h2>Activity Rows</h2>
                    <span>{activitySheetRows.length} lines</span>
                  </div>
                  {activitySheetRows.length ? (
                    <table>
                      <thead>
                        <tr>
                          <th>Activity</th>
                          <th>WBS / CA</th>
                          <th>CBS</th>
                          <th>Planned</th>
                          <th>PV</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {activitySheetRows.slice(0, 10).map((row) => {
                          const rowWbs = displayWbsCatalog.find((node) => node.code === row.wbs_code);
                          return (
                            <tr key={row.id}>
                              <td>
                                <strong>{row.external_activity_id}</strong>
                                <span>{row.activity_name}</span>
                              </td>
                              <td>
                                <strong>{rowWbs?.name ?? row.wbs_code}</strong>
                                <span>
                                  {publicControlAccountCode(row.control_account_code || "CA pending", project)} /{" "}
                                  {publicWbsCode(rowWbs?.code ?? row.wbs_code, project)}
                                </span>
                              </td>
                              <td>{row.cbs_code || "CBS pending"}</td>
                              <td>{currency(row.planned_cost, project.currency)}</td>
                              <td>
                                <strong>{currency(row.planned_value, project.currency)}</strong>
                                <span>{row.planned_percent.toFixed(1)}%</span>
                              </td>
                              <td>{statusLabel(row.mapping_status)}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  ) : (
                    <div className="workspaceEmpty compactEmpty">
                      <strong>No activity rows</strong>
                    </div>
                  )}
                </div>
                {setupMessage && <div className="uploadMessage success">{setupMessage}</div>}
                {setupError && <div className="uploadMessage error">{setupError}</div>}
              </>
            )}
            {visibleControlView === "apu-catalog" && (
              <section aria-label="Master Rate Sheet Module" className="quantityModule">
                <div className="panelHeader">
                  <h2>
                    <Database size={20} /> Master Rate Sheet
                  </h2>
                  <span>
                    Base gratuita sincronizable con DataCauca, INVIAS e IDU para revisar partidas antes de sugerir APU
                    desde cantidades BIM.
                  </span>
                </div>
                <section aria-label="Base de datos APU Colombia" className="colombiaApuBridge visibleApuCatalog">
                  <div className="panelHeader compactHeader registerHeader">
                    <div>
                      <h3>Base de datos APU Colombia</h3>
                      <span>
                        Estructura: fuente oficial, grupo, capitulo, partida/APU, unidad y costo directo de referencia.
                      </span>
                    </div>
                    <div className="apuBridgeActions">
                      <button
                        className="secondaryAction"
                        disabled={quantityAction}
                        onClick={handleColombiaApuCatalogSync}
                        type="button"
                      >
                        Actualizar base gratis
                      </button>
                      <button
                        className="primaryAction"
                        disabled={quantityAction || !latestQuantityTakeoff || !quantityTakeoffLines.length}
                        onClick={() => handleQuantityApuSuggestion(quantityTakeoffLines.map((line) => line.id))}
                        type="button"
                      >
                        Sugerir APU
                      </button>
                    </div>
                  </div>
                  <div className="apuBridgeSummary">
                    <article>
                      <span>Registros visibles</span>
                      <strong>{colombiaApuCatalog.length}</strong>
                      <small>
                        {colombiaApuSearch.trim()
                          ? `${colombiaApuSourceLabel} / Filtro: ${colombiaApuSearch.trim()}`
                          : colombiaApuCatalog.length
                            ? `${colombiaApuSourceLabel} / partida(s) disponibles`
                            : "sin sincronizar"}
                      </small>
                    </article>
                    <article>
                      <span>Ultima sincronizacion</span>
                      <strong>
                        {colombiaApuSync
                          ? `${colombiaApuSync.created_count} nuevas / ${colombiaApuSync.updated_count} actualizadas`
                          : "Pendiente"}
                      </strong>
                      <small>{colombiaApuSync?.source_key ?? "DataCauca/public source"}</small>
                    </article>
                    <article>
                      <span>Uso permitido</span>
                      <strong>Revision</strong>
                      <small>
                        {colombiaApuSync?.license_note ??
                          colombiaApuCatalog[0]?.license_note ??
                          "Validar vigencia, region, AIU y alcance antes de aprobar presupuesto."}
                      </small>
                    </article>
                  </div>
                  <form className="apuCatalogSearch" onSubmit={handleColombiaApuCatalogSearch}>
                    <label>
                      <span>Fuente</span>
                      <select
                        aria-label="Fuente APU Colombia"
                        disabled={quantityAction}
                        onChange={(event) => setColombiaApuSource(event.target.value)}
                        value={colombiaApuSource}
                      >
                        {APU_SOURCE_OPTIONS.map((source) => (
                          <option key={source.key || "all"} value={source.key}>
                            {source.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      <span>Consultar base</span>
                      <input
                        aria-label="Consultar base APU Colombia"
                        disabled={quantityAction}
                        onChange={(event) => setColombiaApuSearch(event.target.value)}
                        placeholder="Buscar por codigo, partida, capitulo o grupo"
                        type="search"
                        value={colombiaApuSearch}
                      />
                    </label>
                    <button className="primaryAction" disabled={quantityAction} type="submit">
                      Buscar
                    </button>
                    <button
                      className="secondaryAction"
                      disabled={quantityAction}
                      onClick={handleColombiaApuCatalogClearSearch}
                      type="button"
                    >
                      Limpiar
                    </button>
                  </form>
                  {colombiaApuCatalog.length ? (
                    <>
                      <div className="apuCatalogStructure" aria-label="Estructura visible de catalogo APU">
                        {colombiaApuStructure.map((source) => (
                          <article key={source.sourceKey}>
                            <div>
                              <strong>{source.sourceLabel}</strong>
                              <span>
                                {source.totalItems} partida(s) / {source.groups.length} grupo(s)
                              </span>
                            </div>
                            <ul>
                              {source.groups.slice(0, 4).map((group) => (
                                <li key={`${source.sourceKey}-${group.groupName}`}>
                                  <strong>{group.groupName}</strong>
                                  <span>
                                    {group.totalItems} partida(s) en {group.chapters.length} capitulo(s):{" "}
                                    {group.chapters
                                      .slice(0, 3)
                                      .map((chapter) => chapter.chapterName)
                                      .join(" / ")}
                                  </span>
                                </li>
                              ))}
                            </ul>
                          </article>
                        ))}
                      </div>
                      <div className="mappingTable apuCatalogTable">
                        <table>
                          <thead>
                            <tr>
                              <th>Codigo</th>
                              <th>Partida / APU</th>
                              <th>Estructura</th>
                              <th>Unidad</th>
                              <th>Precio unitario</th>
                              <th>Region / fuente</th>
                              <th>Estado</th>
                            </tr>
                          </thead>
                          <tbody>
                            {colombiaApuCatalog.map((item) => {
                              const structureLines = apuStructureLines(item);
                              return (
                                <tr key={item.id}>
                                  <td data-label="Codigo">
                                    <strong>{item.item_code}</strong>
                                    <span>{item.chapter || item.group_name || "Capitulo pendiente"}</span>
                                  </td>
                                  <td data-label="Partida / APU">
                                    <strong>{item.item_name}</strong>
                                    <span>{item.group_name || "Grupo pendiente"}</span>
                                  </td>
                                  <td data-label="Estructura">
                                    <div className="apuStructureStack">
                                      {structureLines.map((line, index) => (
                                        <span key={`${item.id}-${line.component}-${index}`}>
                                          <strong>{line.component}</strong>
                                          <small>{line.description}</small>
                                          <em>
                                            {line.quantity} {line.unit} x {currency(line.unitRate, item.currency)}
                                            {line.amount ? ` = ${currency(line.amount, item.currency)}` : ""}
                                          </em>
                                        </span>
                                      ))}
                                      <small>{apuStructureNote(item)}</small>
                                    </div>
                                  </td>
                                  <td data-label="Unidad">{item.unit}</td>
                                  <td data-label="Precio unitario">
                                    <strong>{currency(item.unit_rate, item.currency)}</strong>
                                    <span>{item.currency}</span>
                                  </td>
                                  <td data-label="Region / fuente">
                                    <strong>{item.region || "Region pendiente"}</strong>
                                    <span>{sourceLabel(item.source_key)}</span>
                                  </td>
                                  <td data-label="Estado">
                                    <strong>{statusLabel(item.status)}</strong>
                                    <span>Validar antes de aprobar</span>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </>
                  ) : (
                    <div className="workspaceEmpty compactEmpty">
                      <strong>Base APU sin registros visibles</strong>
                      <span>
                        Usa Actualizar base gratis para traer partidas publicas al proyecto antes de cargar cantidades.
                      </span>
                    </div>
                  )}
                  {quantityMessage && <div className="uploadMessage success">{quantityMessage}</div>}
                  {quantityError && <div className="uploadMessage error">{quantityError}</div>}
                </section>
              </section>
            )}
            {visibleControlView === "claims-audit" && (
              <section aria-label="Reclamaciones Module" className="quantityModule">
                <div className="panelHeader">
                  <h2>
                    <FileSearch size={20} /> Reclamaciones
                  </h2>
                  <span>
                    Convierte expedientes contractuales en claim, aviso, matriz de entitlement e impacto auditable.
                  </span>
                </div>
                <div className="claimSummary">
                  <article>
                    <span>Claims</span>
                    <strong>{dashboard.claims_forensic_summary.total_claims}</strong>
                    <small>Registro contractual del proyecto</small>
                  </article>
                  <article>
                    <span>Avisos</span>
                    <strong>
                      {dashboard.claims_forensic_summary.compliant_notices}/
                      {dashboard.claims_forensic_summary.notice_count}
                    </strong>
                    <small>Compliant / total</small>
                  </article>
                  <article>
                    <span>Impacto costo</span>
                    <strong>{currency(dashboard.claims_forensic_summary.total_claimed_cost, project.currency)}</strong>
                    <small>Reclamado o detectado</small>
                  </article>
                  <article className={dashboard.claims_forensic_summary.forensic_readiness_score < 70 ? "risk" : ""}>
                    <span>Readiness</span>
                    <strong>{dashboard.claims_forensic_summary.forensic_readiness_score.toFixed(0)}%</strong>
                    <small>Notice + impacto + entitlement</small>
                  </article>
                </div>
                <form className="adminPanel compactForm" onSubmit={handleClaimsForensicSubmit}>
                  <label>
                    <span>Modo de analisis</span>
                    <select value={claimsAuditMode} onChange={(event) => setClaimsAuditMode(event.target.value)}>
                      <option value="review">Review del dossier</option>
                      <option value="discovery">Descubrir eventos compensables</option>
                      <option value="rebuttal">Rebatir reclamacion</option>
                      <option value="shielding">Blindar informe</option>
                      <option value="interrogatory">Preguntas al expediente</option>
                    </select>
                  </label>
                  <label>
                    <span>Expediente</span>
                    <input
                      accept=".csv,.docx,.json,.md,.pdf,.txt,.xml,.zip"
                      multiple
                      onChange={(event) => setClaimsAuditFiles(Array.from(event.target.files ?? []))}
                      type="file"
                    />
                  </label>
                  <button
                    className="primaryAction"
                    disabled={claimsAuditAction || !claimsAuditFiles.length}
                    type="submit"
                  >
                    {claimsAuditAction ? "Analizando..." : "Analizar expediente"}
                  </button>
                  <small>
                    Soporta texto, CSV, JSON, XML, DOCX simple y ZIP. PDF queda registrado como evidencia si no hay
                    texto extraible.
                  </small>
                </form>
                {claimsAuditFiles.length ? (
                  <div className="uploadMessage success">{claimsAuditFiles.map((file) => file.name).join(" / ")}</div>
                ) : null}
                {claimsAuditResult && (
                  <div className="uploadMessage success">
                    {claimsAuditResult.summary} Readiness {claimsAuditResult.readiness_score.toFixed(0)}%.
                  </div>
                )}
                {claimsAuditMessage && <div className="uploadMessage success">{claimsAuditMessage}</div>}
                {claimsAuditError && <div className="uploadMessage error">{claimsAuditError}</div>}
                <div className="mappingTable">
                  <div className="panelHeader compactHeader registerHeader">
                    <div>
                      <h3>Claim register</h3>
                      <span>Una tabla para revisar causacion, impacto, soporte y estado de cada reclamo.</span>
                    </div>
                    <span>{dashboard.claims.length} claim(s)</span>
                  </div>
                  {dashboard.claims.length ? (
                    <table>
                      <thead>
                        <tr>
                          <th>Claim</th>
                          <th>Causacion</th>
                          <th>Impacto</th>
                          <th>Entitlement</th>
                          <th>Estado</th>
                        </tr>
                      </thead>
                      <tbody>
                        {dashboard.claims.map((claim) => {
                          const items = dashboard.claim_entitlement_items.filter((item) => item.claim_id === claim.id);
                          const satisfied = items.filter((item) => item.status === "satisfied").length;
                          return (
                            <tr key={claim.id}>
                              <td data-label="Claim">
                                <strong>{claim.title}</strong>
                                <span>{claim.evidence_summary || "Sin evidencia vinculada"}</span>
                              </td>
                              <td data-label="Causacion">{claim.causality || "Pendiente"}</td>
                              <td data-label="Impacto">{claim.impact || "Pendiente"}</td>
                              <td data-label="Entitlement">
                                <strong>
                                  {satisfied}/{items.length}
                                </strong>
                                <span>{items.length ? "puntos soportados" : "sin matriz"}</span>
                              </td>
                              <td data-label="Estado">{statusLabel(claim.status)}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  ) : (
                    <div className="workspaceEmpty compactEmpty">
                      <strong>Sin claims registrados</strong>
                      <span>Carga un expediente para crear el primer claim auditable.</span>
                    </div>
                  )}
                </div>
                <div className="mappingTable">
                  <div className="panelHeader compactHeader registerHeader">
                    <div>
                      <h3>Impactos y avisos</h3>
                      <span>Resumen de dias, costos, metodo de analisis y trazabilidad contractual.</span>
                    </div>
                    <span>{dashboard.claim_impact_analyses.length} impacto(s)</span>
                  </div>
                  {dashboard.claim_impact_analyses.length || dashboard.contract_notices.length ? (
                    <table>
                      <thead>
                        <tr>
                          <th>Tipo</th>
                          <th>Metodo / asunto</th>
                          <th>Dias</th>
                          <th>Costo</th>
                          <th>Estado</th>
                        </tr>
                      </thead>
                      <tbody>
                        {dashboard.claim_impact_analyses.map((analysis) => (
                          <tr key={`impact-${analysis.id}`}>
                            <td data-label="Tipo">Impacto</td>
                            <td data-label="Metodo / asunto">
                              <strong>{analysis.method}</strong>
                              <span>{analysis.evidence_ref || "Sin referencia"}</span>
                            </td>
                            <td data-label="Dias">{analysis.schedule_impact_days}</td>
                            <td data-label="Costo">{currency(analysis.cost_impact, project.currency)}</td>
                            <td data-label="Estado">{statusLabel(analysis.status)}</td>
                          </tr>
                        ))}
                        {dashboard.contract_notices.map((notice) => (
                          <tr key={`notice-${notice.id}`}>
                            <td data-label="Tipo">Aviso</td>
                            <td data-label="Metodo / asunto">
                              <strong>{notice.subject}</strong>
                              <span>{notice.reference || "Sin referencia"}</span>
                            </td>
                            <td data-label="Dias">{notice.days_late}</td>
                            <td data-label="Costo">N/A</td>
                            <td data-label="Estado">{statusLabel(notice.compliance_status)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <div className="workspaceEmpty compactEmpty">
                      <strong>Sin impactos ni avisos</strong>
                      <span>El analisis creara registros cuando detecte aviso, demora, costo o productividad.</span>
                    </div>
                  )}
                </div>
              </section>
            )}
            {visibleControlView === "window-analysis-37" && (
              <section aria-label="Ventanas 3.7 Module" className="quantityModule">
                <div className="panelHeader">
                  <h2>
                    <GitBranch size={20} /> Ventanas 3.7
                  </h2>
                  <span>
                    Compara multiples bases o actualizaciones CPM bajo AACE RP29R MIP 3.7 para detectar ventanas,
                    deslizamientos y candidatos de causa-efecto.
                  </span>
                </div>
                <div className="claimSummary">
                  <article>
                    <span>Cronogramas</span>
                    <strong>{windowAnalysisResult?.summary.valid_schedule_count ?? 0}</strong>
                    <small>Validados para comparar</small>
                  </article>
                  <article>
                    <span>Ventanas</span>
                    <strong>{windowAnalysisResult?.windows.length ?? 0}</strong>
                    <small>Entre bases sucesivas</small>
                  </article>
                  <article
                    className={(Number(windowAnalysisResult?.summary.net_delay_days ?? 0) || 0) > 0 ? "risk" : ""}
                  >
                    <span>Impacto neto</span>
                    <strong>{windowAnalysisResult?.summary.net_delay_days ?? 0} dias</strong>
                    <small>Demora critica menos mitigacion</small>
                  </article>
                  <article>
                    <span>RAG</span>
                    <strong>{windowAnalysisResult?.rag_sources.length ?? windowAnalysisRagSources.length}</strong>
                    <small>AACE + guias adjuntas</small>
                  </article>
                </div>
                <form className="adminPanel compactForm" onSubmit={handleWindowAnalysis37Submit}>
                  <label>
                    <span>Actualizaciones CPM</span>
                    <input
                      accept=".xer,.xml,.mpp"
                      multiple
                      onChange={(event) => setWindowAnalysisFiles(Array.from(event.target.files ?? []))}
                      type="file"
                    />
                  </label>
                  <label>
                    <span>Umbral near-critical dias</span>
                    <input
                      min="0"
                      onChange={(event) => setWindowAnalysisThreshold(Number(event.target.value || 0))}
                      type="number"
                      value={windowAnalysisThreshold}
                    />
                  </label>
                  <button
                    className="primaryAction"
                    disabled={windowAnalysisAction || windowAnalysisFiles.length < 2}
                    type="submit"
                  >
                    {windowAnalysisAction ? "Analizando..." : "Ejecutar ventanas 3.7"}
                  </button>
                  <small>
                    Soporta XER, Primavera XML y Microsoft Project XML. MPP binario debe exportarse a XML mientras se
                    integra conversor nativo.
                  </small>
                </form>
                {windowAnalysisFiles.length ? (
                  <div className="uploadMessage success">
                    {windowAnalysisFiles.map((file) => file.name).join(" / ")}
                  </div>
                ) : null}
                {windowAnalysisMessage && <div className="uploadMessage success">{windowAnalysisMessage}</div>}
                {windowAnalysisError && <div className="uploadMessage error">{windowAnalysisError}</div>}
                <div className="mappingTable">
                  <div className="panelHeader compactHeader registerHeader">
                    <div>
                      <h3>Fuentes y calidad CPM</h3>
                      <span>El analisis ordena las bases por fecha de corte y valida actividad, logica y fuente.</span>
                    </div>
                    <span>{windowAnalysisResult?.schedule_sources.length ?? 0} archivo(s)</span>
                  </div>
                  {windowAnalysisResult?.schedule_sources.length ? (
                    <table>
                      <thead>
                        <tr>
                          <th>Archivo</th>
                          <th>Fuente</th>
                          <th>Fecha de corte</th>
                          <th>Actividades</th>
                          <th>Logica</th>
                          <th>Calidad</th>
                        </tr>
                      </thead>
                      <tbody>
                        {windowAnalysisResult.schedule_sources.map((source) => (
                          <tr key={source.file_name}>
                            <td data-label="Archivo">
                              <strong>{source.file_name}</strong>
                              <span>{source.message || source.finding_code || "Fuente valida"}</span>
                            </td>
                            <td data-label="Fuente">{source.source}</td>
                            <td data-label="Fecha de corte">{source.data_date ?? "N/A"}</td>
                            <td data-label="Actividades">{source.activity_count}</td>
                            <td data-label="Logica">{source.relationship_count}</td>
                            <td data-label="Calidad">
                              <strong>{source.quality_score.toFixed(0)}%</strong>
                              <span>{statusLabel(source.status)}</span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <div className="workspaceEmpty compactEmpty">
                      <strong>Sin corrida de ventanas</strong>
                      <span>Carga dos o mas cronogramas XER/XML para crear las ventanas comparables.</span>
                    </div>
                  )}
                </div>
                <div className="mappingTable">
                  <div className="panelHeader compactHeader registerHeader">
                    <div>
                      <h3>Ventanas detectadas</h3>
                      <span>Cada fila compara una base contra la siguiente actualizacion CPM.</span>
                    </div>
                    <span>{windowAnalysisResult?.windows.length ?? 0} ventana(s)</span>
                  </div>
                  {windowAnalysisResult?.windows.length ? (
                    <table>
                      <thead>
                        <tr>
                          <th>Ventana</th>
                          <th>Periodo</th>
                          <th>Terminacion</th>
                          <th>Impacto</th>
                          <th>Cambios</th>
                          <th>Lectura</th>
                        </tr>
                      </thead>
                      <tbody>
                        {windowAnalysisResult.windows.map((window) => (
                          <tr key={`${window.window_no}-${window.start_schedule}-${window.finish_schedule}`}>
                            <td data-label="Ventana">
                              <strong>W{window.window_no}</strong>
                              <span>
                                {window.start_schedule} {"->"} {window.finish_schedule}
                              </span>
                            </td>
                            <td data-label="Periodo">
                              {window.start_data_date ?? "N/A"} {"->"} {window.finish_data_date ?? "N/A"}
                            </td>
                            <td data-label="Terminacion">
                              <strong>
                                {window.start_completion ?? "N/A"} {"->"} {window.finish_completion ?? "N/A"}
                              </strong>
                              <span>{window.completion_slip_days} dia(s)</span>
                            </td>
                            <td data-label="Impacto">
                              <strong>
                                {window.critical_delay_days} demora / {window.mitigation_days} mitigacion
                              </strong>
                              <span>{window.critical_or_near_critical_delay_count} candidato(s) criticos</span>
                            </td>
                            <td data-label="Cambios">
                              <strong>
                                +{window.added_activity_count} / -{window.removed_activity_count} act
                              </strong>
                              <span>
                                Logica +{window.logic_delta.added_relationships} / -
                                {window.logic_delta.removed_relationships} / {window.logic_delta.changed_relationships}{" "}
                                mod
                              </span>
                            </td>
                            <td data-label="Lectura">{window.interpretation}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <div className="workspaceEmpty compactEmpty">
                      <strong>No hay ventanas calculadas</strong>
                      <span>Se necesita minimo dos schedules validos con actividades comparables.</span>
                    </div>
                  )}
                </div>
                <div className="mappingTable">
                  <div className="panelHeader compactHeader registerHeader">
                    <div>
                      <h3>Actividades candidatas de impacto</h3>
                      <span>Primero se revisan actividades criticas o near-critical con deslizamiento de finish.</span>
                    </div>
                    <span>
                      {windowAnalysisResult?.windows.reduce(
                        (total, window) => total + window.top_delay_events.length,
                        0
                      ) ?? 0}{" "}
                      candidato(s)
                    </span>
                  </div>
                  {windowAnalysisResult?.windows.some((window) => window.top_delay_events.length) ? (
                    <table>
                      <thead>
                        <tr>
                          <th>Ventana</th>
                          <th>Actividad</th>
                          <th>WBS</th>
                          <th>Deslizamiento</th>
                          <th>Float</th>
                          <th>Clasificacion</th>
                        </tr>
                      </thead>
                      <tbody>
                        {windowAnalysisResult.windows.flatMap((window) =>
                          window.top_delay_events.map((event) => (
                            <tr key={`${window.window_no}-${event.activity_id}`}>
                              <td data-label="Ventana">W{window.window_no}</td>
                              <td data-label="Actividad">
                                <strong>{event.activity_id}</strong>
                                <span>{event.activity_name}</span>
                              </td>
                              <td data-label="WBS">
                                <strong>{event.wbs_code || "Sin WBS"}</strong>
                                <span>{event.wbs_name}</span>
                              </td>
                              <td data-label="Deslizamiento">
                                {event.finish_slip_days} finish / {event.start_slip_days} start
                              </td>
                              <td data-label="Float">{event.total_float_delta_days} dia(s)</td>
                              <td data-label="Clasificacion">{statusLabel(event.classification)}</td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  ) : (
                    <div className="workspaceEmpty compactEmpty">
                      <strong>Sin candidatos criticos</strong>
                      <span>La corrida no detecto deslizamientos criticos o near-critical en actividades comunes.</span>
                    </div>
                  )}
                </div>
                <div className="mappingTable">
                  <div className="panelHeader compactHeader registerHeader">
                    <div>
                      <h3>Lineamientos RAG aplicados</h3>
                      <span>Referencias cargadas para orientar el analisis y sus limitaciones.</span>
                    </div>
                    <span>{(windowAnalysisResult?.rag_sources ?? windowAnalysisRagSources).length} fuente(s)</span>
                  </div>
                  <div className="apuCatalogSources">
                    {(windowAnalysisResult?.rag_sources ?? windowAnalysisRagSources).map((source) => (
                      <article key={`${source.file_name}-${source.source_type}`}>
                        <strong>{source.title}</strong>
                        <span>{source.relevance}</span>
                        <small>{source.file_name}</small>
                      </article>
                    ))}
                  </div>
                  {windowAnalysisResult?.source_validation?.length ? (
                    <div className="apuCatalogSources" role="region" aria-label="Validacion de fuentes SVP">
                      {windowAnalysisResult.source_validation.map((check) => (
                        <article
                          className={check.status === "warn" ? "risk" : ""}
                          key={`${check.protocol}-${check.check}-${check.detail}`}
                        >
                          <strong>
                            {check.protocol} / {check.status === "warn" ? "Revisar" : "OK"}
                          </strong>
                          <span>{check.check}</span>
                          <small>{check.detail}</small>
                        </article>
                      ))}
                    </div>
                  ) : null}
                  {windowAnalysisResult?.limitations.length ? (
                    <div className="uploadMessage success">{windowAnalysisResult.limitations.join(" ")}</div>
                  ) : null}
                </div>
              </section>
            )}
            {visibleControlView === "quantity-takeoff" && (
              <section aria-label={`${BIM_MANAGER_SUBMODULE_LABEL} Module`} className="quantityModule">
                <div className="panelHeader">
                  <h2>
                    <Ruler size={20} /> {BIM_MANAGER_SUBMODULE_LABEL}
                  </h2>
                  <span>
                    {latestQuantityTakeoff?.validation_summary ??
                      (latestBimModel
                        ? `Modelo IFC registrado: ${latestBimModel.source_file_name}. Cantidades pendientes de tabla controlada.`
                        : null) ??
                      "Carga un IFC, Excel o CSV para iniciar"}
                  </span>
                </div>
                <div className="scopeManagerRibbonHost" id="scope-manager-ifc-ribbon-root" />
                <LazyModuleErrorBoundary moduleName="Modelo IFC">
                  <Suspense
                    fallback={
                      <section aria-label="Modelo IFC" className="bimViewer bimViewerWide ifcGeometryViewer">
                        <div className="panelHeader compactHeader bimViewerHeader">
                          <div className="bimViewerTitle">
                            <h3>Modelo IFC</h3>
                            <span>Cargando visor IFC bajo demanda...</span>
                          </div>
                        </div>
                        <div className="bimViewerCanvasWrap ifcGeometryCanvasWrap loadingCanvas">
                          <strong>Preparando visor geometrico</strong>
                        </div>
                      </section>
                    }
                  >
                    <BimIfcModelViewer
                      approvalDisabled={quantityAction || !latestQuantityTakeoff}
                      clearModelDisabled={
                        quantityAction ||
                        (!bimModelRuns.length && !quantityTakeoffRuns.length && !quantityTakeoffLines.length)
                      }
                      informationContent={scopeManagerInformationContent}
                      lines={quantityTakeoffLines}
                      onApproveControlledMeasurement={handleControlledMeasurementApproval}
                      onClearModel={handleQuantityTakeoffClear}
                      onLoadSource={handleQuantityTakeoffUpload}
                      projectId={selectedProjectId}
                      model={displayedBimModel}
                      ribbonHostId="scope-manager-ifc-ribbon-root"
                      run={latestQuantityTakeoff}
                      sourceLoadDisabled={!canLoadQuantities || quantityAction}
                      sourceLoading={quantityAction}
                      token={token}
                    />
                  </Suspense>
                </LazyModuleErrorBoundary>
                <BimScopeValidationPanel
                  cbsCatalog={cbsCatalog}
                  colombiaApuCatalog={colombiaApuCatalog}
                  colombiaApuSync={colombiaApuSync}
                  fbsFundingSources={fbsFundingSources}
                  geometryBatch={geometryMeasurementBatch}
                  geometryBatchDisabled={quantityAction || !latestQuantityTakeoff}
                  geometryModelAvailable={Boolean(
                    geometryMeasurementModel && latestQuantityTakeoff && quantityTakeoffLines.length
                  )}
                  geometryModels={bimModelRuns}
                  geometryModelStatusMessage={geometryModelStatusMessage}
                  geometryRun={latestQuantityTakeoff}
                  lines={quantityTakeoffLines}
                  quantityRules={bimQuantityRules}
                  showApuCatalogBridge={false}
                  apuActionDisabled={quantityAction}
                  approvalDisabled={quantityAction || !latestQuantityTakeoff}
                  assignmentDisabled={quantityAction || !latestQuantityTakeoff}
                  onApproveControlledMeasurement={handleControlledMeasurementApproval}
                  onApproveApuForLines={handleQuantityApuApproval}
                  onAnalyzeGeometryBatch={() => handleGeometryMeasurementBatch(false)}
                  onApplyGeometryBatch={() => handleGeometryMeasurementBatch(true)}
                  onLinkGeometryModel={handleQuantityTakeoffModelLink}
                  onAssignControlCodes={handleQuantityControlCodeAssignment}
                  onOpenBimBudget={() => handleControlFlowNavigate("bim-budget")}
                  onSuggestApuForLines={handleQuantityApuSuggestion}
                  onSyncColombiaApuCatalog={handleColombiaApuCatalogSync}
                  onUpdateQuantityRule={handleBimQuantityRuleUpdate}
                  onRecalculateQuantityRules={handleQuantityRuleRecalculation}
                  recalculationSummary={quantityRuleRecalculation}
                  recalculateDisabled={quantityAction || !latestQuantityTakeoff}
                  wbsCatalog={wbsCatalog}
                  workPackages={dashboard.work_packages ?? []}
                />
                {quantityMessage && <div className="uploadMessage success">{quantityMessage}</div>}
                {quantityError && <div className="uploadMessage error">{quantityError}</div>}
              </section>
            )}
            {visibleControlView === "bim-budget" && (
              <BimBudgetPanel
                currency={project.currency}
                lines={quantityTakeoffLines}
                onOpenQuantities={() => handleControlFlowNavigate("quantity-takeoff")}
                onUpdateBudgetItem={handleQuantityControlCodeAssignment}
                projectCode={project.code}
                projectName={project.name}
              />
            )}
            {visibleControlView === "dashboard" && (
              <>
                <div className="panelHeader">
                  <h2>Dashboard EVM</h2>
                  <span>
                    Earned Value Management / {project.code} / {project.phase}
                  </span>
                </div>
                <div className="dashboardOverviewPanel evmDashboardPanel">
                  <div className="panelHeader compactHeader">
                    <h2>Resumen EVM</h2>
                    <span>Valor ganado, variacion y forecast del proyecto</span>
                  </div>
                  <div className="awpSummary evmSummaryGrid">
                    {evmSummaryCards.map((item) => (
                      <article className={item.risk ? "risk" : ""} key={item.label}>
                        <span>{item.label}</span>
                        <strong>{item.value}</strong>
                        <small>{item.detail}</small>
                      </article>
                    ))}
                  </div>
                  <p className="projectHint">
                    {baselineOnlyEvm
                      ? "Solo existe linea base: la curva muestra el plan acumulado y las tarjetas PV, EV y AC quedan en cero hasta cargar un corte de avance/costo."
                      : "El control se calcula por EVM: PV es el valor planeado acumulado por fecha de corte desde Activity Sheet o cost loading, EV viene del avance fisico aprobado y AC de costos certificados o incurridos. SPI y CPI solo son confiables cuando existen PV, EV y AC del periodo."}
                  </p>
                </div>
                <div className="panel wide evmCurvePanel">
                  <div className="panelHeader compactHeader">
                    <h2>Curva S acumulada</h2>
                    <span>PV / EV / AC por periodo de control</span>
                  </div>
                  <p className="projectHint">
                    {baselineOnlyEvm
                      ? "Fuente: Activity Sheet / linea base aprobada. Sin corte de control no se dibujan EV ni AC."
                      : "Fuente: Activity Sheet para la curva PV planificada y snapshots de Control Core para EV/AC. Si el backend no trae PV por periodo, la app lo reconstruye desde fechas y costos planificados de actividades."}
                  </p>
                  <ResponsiveContainer width="100%" height={270}>
                    <LineChart data={evmCurveData} margin={{ bottom: 8, left: 6, right: 26, top: 14 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#d8dee5" />
                      <XAxis
                        dataKey="timestamp"
                        domain={["dataMin", "dataMax"]}
                        scale="time"
                        tickFormatter={dateAxis}
                        type="number"
                      />
                      <YAxis
                        domain={[0, "dataMax"]}
                        tickFormatter={(value) => currencyAxis(Number(value), project.currency)}
                      />
                      <Tooltip
                        formatter={(value, name) => [currency(Number(value), project.currency), name]}
                        labelFormatter={tooltipDate}
                      />
                      <ReferenceLine
                        ifOverflow="extendDomain"
                        label={{
                          position: "insideBottomLeft",
                          value: `BAC ${currency(projectEvm.bac, project.currency)}`,
                        }}
                        stroke="#52616f"
                        strokeDasharray="4 4"
                        y={projectEvm.bac}
                      />
                      <ReferenceLine
                        ifOverflow="extendDomain"
                        label={{
                          position: "insideTopRight",
                          value: `EAC ${currency(projectEvm.eac, project.currency)}`,
                        }}
                        stroke="#7c3aed"
                        strokeDasharray="6 4"
                        y={projectEvm.eac}
                      />
                      <Line
                        dataKey="PV"
                        dot={false}
                        name="PV planned"
                        stroke="#52616f"
                        strokeWidth={2.4}
                        type="monotone"
                      />
                      <Line
                        connectNulls={false}
                        dataKey="EV"
                        dot={{ r: 3 }}
                        name="EV earned"
                        stroke="#0f8b8d"
                        strokeWidth={2.4}
                        type="monotone"
                      />
                      <Line
                        connectNulls={false}
                        dataKey="AC"
                        dot={{ r: 3 }}
                        name="AC actual"
                        stroke="#c85a3a"
                        strokeWidth={2.4}
                        type="monotone"
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
                <div className="viewSplit">
                  <div className="panel">
                    <div className="panelHeader compactHeader">
                      <h2>Control Core Status</h2>
                      <span>{dashboard.control_accounts.length} accounts</span>
                    </div>
                    <div className="workList">
                      <article>
                        <strong>{activeImport ? "Baseline loaded" : "Baseline pending"}</strong>
                        <span>
                          {activeImport
                            ? `${activeImport.baseline_name} / quality ${activeImport.quality_score.toFixed(0)}%`
                            : "Upload XML/XER to start the baseline and control workflow."}
                        </span>
                        <small>
                          {dashboard.schedule_activity_count} activities / {dashboard.schedule_findings.length} findings
                        </small>
                      </article>
                      <article>
                        <strong>AWP readiness {dashboard.awp_summary.readiness_score.toFixed(1)}%</strong>
                        <span>
                          {dashboard.awp_summary.ready_for_release} ready / {dashboard.awp_summary.blocked_packages}{" "}
                          blocked
                        </span>
                        <small>{dashboard.awp_summary.total_packages} work packages</small>
                      </article>
                    </div>
                  </div>
                  <div className="panel">
                    <div className="panelHeader compactHeader">
                      <h2>Control Flow Snapshot</h2>
                      <span>Live project controls</span>
                    </div>
                    <div className="loopList">
                      {(dashboard.flow ?? []).length ? (
                        dashboard.flow.map((item) => (
                          <div key={item.name}>
                            <strong>{item.name}</strong>
                            <span>
                              {item.state} / {item.purpose}
                            </span>
                          </div>
                        ))
                      ) : (
                        <>
                          <div>
                            <strong>Baseline</strong>
                            <span>{dashboard.schedule_activity_count} activities loaded</span>
                          </div>
                          <div>
                            <strong>Progress</strong>
                            <span>{dashboard.latest_progress_records.length} records captured</span>
                          </div>
                          <div>
                            <strong>Costs</strong>
                            <span>{dashboard.cost_sheet.length} cost lines available</span>
                          </div>
                        </>
                      )}
                    </div>
                  </div>
                </div>
              </>
            )}
            {visibleControlView === "integrated-control" && (
              <>
                <div className="panelHeader">
                  <h2>Fund</h2>
                  <span>{integratedMatrix.length} WBS-CBS-FBS trace rows</span>
                </div>
                <section className="moduleGuide" aria-label="CBS FBS relation guide">
                  <strong className="moduleGuideTitle">Como se vincula WBS, CBS y FBS</strong>
                  <span>
                    FBS es fuente de financiacion; CBS es estructura de costo. Se relacionan con WBS por cuenta de
                    control, Cost Code y procesos BP CBS-Fund / BP CBS-WBS, no como listas sueltas.
                  </span>
                  <span>
                    Convencion: CBS-{"{Proyecto}"}-{"{WBS}"}-{"{Familia de costo}"}. La Activity Sheet propone drafts
                    por WBS y familia; el usuario valida el catalogo antes del rollup de costos.
                  </span>
                </section>
                <section aria-label="WBS Master Structure" className="panel wide wbsStructurePanel">
                  <div className="panelHeader compactHeader">
                    <h2>
                      <GitBranch size={18} /> WBS Master Structure
                    </h2>
                    <span>{wbsTableRows.length} active nodes</span>
                  </div>
                  {primaryWbsTree.length ? (
                    <div aria-label={`WBS mapping tree for ${project.code}`} className="wbsTreeCanvas" role="tree">
                      {shouldRenderProjectRoot ? (
                        <div className="wbsProjectTreeRoot">
                          <article
                            aria-label={`${project.code} ${project.name}`}
                            aria-level={1}
                            className="wbsNodeCard projectRoot"
                            role="treeitem"
                          >
                            <strong>{project.code}</strong>
                            <span>{project.name}</span>
                            <small>Project</small>
                          </article>
                          <div className="wbsChildren wbsProjectChildren">
                            {primaryWbsTree.map((node) => (
                              <WbsTreeBranch
                                activityByCode={activityWbsByCode}
                                currencyCode={project.currency}
                                depth={1}
                                key={node.id}
                                node={node}
                                project={project}
                              />
                            ))}
                          </div>
                        </div>
                      ) : (
                        <div className="wbsTreeRoots">
                          {primaryWbsTree.map((node) => (
                            <WbsTreeBranch
                              activityByCode={activityWbsByCode}
                              currencyCode={project.currency}
                              depth={0}
                              key={node.id}
                              node={node}
                              project={project}
                            />
                          ))}
                        </div>
                      )}
                    </div>
                  ) : (
                    <div className="workspaceEmpty compactEmpty">
                      <strong>No WBS nodes</strong>
                      <p>Load the schedule or create WBS nodes before mapping CBS and FBS.</p>
                    </div>
                  )}
                </section>
                <section aria-label="WBS Control Alignment" className="panel wide wbsControlAlignment">
                  <div className="panelHeader compactHeader">
                    <h2>WBS Control Alignment</h2>
                    <span>{wbsTraceabilityRows.length} linked control chain(s)</span>
                  </div>
                  {wbsTraceabilityRows.length ? (
                    <div className="wbsAlignmentList">
                      {wbsTraceabilityRows.map((row) => (
                        <article
                          aria-label={`${row.wbsName} control alignment`}
                          className="wbsAlignmentCard"
                          key={row.id}
                        >
                          <div className="wbsAlignmentNode primary">
                            <span>WBS</span>
                            <strong>{row.wbsName}</strong>
                            <small>{row.wbsCode}</small>
                          </div>
                          <div className="wbsAlignmentNode">
                            <span>Control Account</span>
                            <strong>{row.controlAccountName}</strong>
                            <small>{row.controlAccountCode}</small>
                          </div>
                          <div className="wbsAlignmentNode">
                            <span>CBS</span>
                            <strong>{row.cbsCode}</strong>
                            <small>{row.costCode !== "Cost code pending" ? row.costCode : "CostCode pending"}</small>
                          </div>
                          <div className="wbsAlignmentNode">
                            <span>FBS</span>
                            <strong>{row.fbsCode}</strong>
                            <small>
                              {row.fbsCode !== "FBS pending" ? "Funding source linked" : "BP CBS-Fund pending"}
                            </small>
                          </div>
                          <div className="wbsAlignmentNode">
                            <span>AWP</span>
                            <strong>{row.awpPackageTitle}</strong>
                            <small>{row.awpPackageCode}</small>
                          </div>
                          <div className="wbsAlignmentNode budget">
                            <span>Budget</span>
                            <strong>{currency(row.budget, project.currency)}</strong>
                            <small>{row.status}</small>
                          </div>
                        </article>
                      ))}
                    </div>
                  ) : (
                    <div className="workspaceEmpty compactEmpty">
                      <strong>No control alignment yet</strong>
                      <p>Create an active control account and link CBS/FBS funding to the WBS.</p>
                    </div>
                  )}
                </section>
                <section aria-label="WBS Traceability Matrix" className="panel wide">
                  <div className="panelHeader compactHeader">
                    <h2>WBS Traceability Matrix</h2>
                    <span>{wbsTraceabilityRows.length} active account(s)</span>
                  </div>
                  <table>
                    <thead>
                      <tr>
                        <th>WBS</th>
                        <th>Control Account</th>
                        <th>CBS</th>
                        <th>FBS</th>
                        <th>AWP Package</th>
                        <th>Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {wbsTraceabilityRows.map((row) => (
                        <tr key={row.id}>
                          <td>
                            <strong>{row.wbsName}</strong>
                            <span>{row.wbsCode}</span>
                          </td>
                          <td>
                            <strong>{row.controlAccountCode}</strong>
                            <span>{row.controlAccountName}</span>
                          </td>
                          <td>{row.cbsCode}</td>
                          <td>{row.fbsCode}</td>
                          <td>
                            <strong>{row.awpPackageTitle}</strong>
                            <span>{row.awpPackageCode}</span>
                          </td>
                          <td>{row.status}</td>
                        </tr>
                      ))}
                      {!wbsTraceabilityRows.length && (
                        <tr>
                          <td colSpan={6}>
                            <strong>No active WBS traceability yet</strong>
                            <span>Create an active control account and link CBS/FBS funding to the WBS.</span>
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </section>
                <div className="viewSplit">
                  <form className="adminPanel" onSubmit={handleFbsCreate}>
                    <div className="panelHeader compactHeader">
                      <h2>Crear FBS</h2>
                      <span>{fbsFundingSources.length} sources</span>
                    </div>
                    <label>
                      <span>FBS Code</span>
                      <input
                        disabled={!canConfigure || fbsAction}
                        onChange={(event) => setFbsDraft((current) => ({ ...current, code: event.target.value }))}
                        placeholder="FBS-OWN-AFE002-PLT"
                        required
                        value={fbsDraft.code}
                      />
                    </label>
                    <label>
                      <span>Source</span>
                      <input
                        disabled={!canConfigure || fbsAction}
                        onChange={(event) =>
                          setFbsDraft((current) => ({ ...current, source_of_funds: event.target.value }))
                        }
                        required
                        value={fbsDraft.source_of_funds}
                      />
                    </label>
                    <div className="formColumns">
                      <label>
                        <span>Type</span>
                        <select
                          disabled={!canConfigure || fbsAction}
                          onChange={(event) =>
                            setFbsDraft((current) => ({ ...current, funding_type: event.target.value }))
                          }
                          value={fbsDraft.funding_type}
                        >
                          <option value="AFE">AFE</option>
                          <option value="Debt">Debt</option>
                          <option value="Public funding">Public funding</option>
                          <option value="Reserve">Reserve</option>
                        </select>
                      </label>
                      <label>
                        <span>Authorization</span>
                        <input
                          disabled={!canConfigure || fbsAction}
                          onChange={(event) =>
                            setFbsDraft((current) => ({ ...current, authorization_ref: event.target.value }))
                          }
                          value={fbsDraft.authorization_ref}
                        />
                      </label>
                    </div>
                    <div className="formColumns">
                      <label>
                        <span>Approved</span>
                        <input
                          disabled={!canConfigure || fbsAction}
                          min="0"
                          onChange={(event) =>
                            setFbsDraft((current) => ({ ...current, approved_amount: event.target.value }))
                          }
                          required
                          type="number"
                          value={fbsDraft.approved_amount}
                        />
                      </label>
                      <label>
                        <span>Currency</span>
                        <input
                          disabled={!canConfigure || fbsAction}
                          maxLength={3}
                          onChange={(event) =>
                            setFbsDraft((current) => ({ ...current, currency: event.target.value.toUpperCase() }))
                          }
                          value={fbsDraft.currency}
                        />
                      </label>
                    </div>
                    <button className="workflowAction primary" disabled={!canConfigure || fbsAction} type="submit">
                      {fbsAction ? "Creating..." : "Create FBS"}
                    </button>
                  </form>

                  <div className="panel">
                    <div className="panelHeader compactHeader">
                      <h2>Funding Alerts</h2>
                      <span>{fundingAlerts.length} alerts</span>
                    </div>
                    <div className="awpSummary">
                      <article className={fundingAlerts.length ? "risk" : ""}>
                        <span>Forecast Gaps</span>
                        <strong>{fundingAlerts.length}</strong>
                        <small>FBS below forecast</small>
                      </article>
                      <article>
                        <span>Unused Balance</span>
                        <strong>{currency(closeoutReport?.unused_balance ?? 0, project.currency)}</strong>
                        <small>{closeoutReport?.open_commitments ?? 0} open commitments</small>
                      </article>
                    </div>
                    <div className="workList compactList">
                      {forecastFundingRows.slice(0, 6).map((row) => (
                        <article
                          className={row.forecast_vs_available < 0 ? "blockedPackage" : undefined}
                          key={row.fbs_code}
                        >
                          <strong>
                            {row.fbs_code} / {currency(row.funds_available, project.currency)}
                          </strong>
                          <span>{currency(row.forecast, project.currency)} forecast</span>
                          <small>{currency(row.forecast_vs_available, project.currency)} vs available</small>
                        </article>
                      ))}
                      {!forecastFundingRows.length && (
                        <article>
                          <strong>No funding rows</strong>
                          <span>FBS records will appear after funding is configured.</span>
                        </article>
                      )}
                    </div>
                    <button
                      className="workflowAction"
                      disabled={!canConfigure || baselineAction}
                      onClick={handleBaselineApproval}
                      type="button"
                    >
                      {baselineAction ? "Approving..." : "Approve Baseline"}
                    </button>
                  </div>
                </div>

                <div className="viewSplit">
                  <form className="adminPanel" onSubmit={handleCbsCreate}>
                    <div className="panelHeader compactHeader">
                      <h2>Crear CBS</h2>
                      <span>
                        {cbsCatalog.length} codes / {costCodes.length} cost codes
                      </span>
                    </div>
                    <label>
                      <span>CBS Code</span>
                      <input
                        disabled={!canCaptureCost || priorityAction === "cbs"}
                        onChange={(event) => setCbsDraft((current) => ({ ...current, code: event.target.value }))}
                        placeholder={activitySheetRows[0]?.cbs_code || "CBS-PIL-PLT-CIV-EARTH"}
                        required
                        value={cbsDraft.code}
                      />
                    </label>
                    <div className="formColumns">
                      <label>
                        <span>Category</span>
                        <input
                          disabled={!canCaptureCost || priorityAction === "cbs"}
                          onChange={(event) =>
                            setCbsDraft((current) => ({ ...current, cost_category: event.target.value }))
                          }
                          required
                          value={cbsDraft.cost_category}
                        />
                      </label>
                      <label>
                        <span>Level</span>
                        <input
                          disabled={!canCaptureCost || priorityAction === "cbs"}
                          min="1"
                          onChange={(event) => setCbsDraft((current) => ({ ...current, level: event.target.value }))}
                          type="number"
                          value={cbsDraft.level}
                        />
                      </label>
                    </div>
                    <label>
                      <span>Description</span>
                      <input
                        disabled={!canCaptureCost || priorityAction === "cbs"}
                        onChange={(event) =>
                          setCbsDraft((current) => ({ ...current, description: event.target.value }))
                        }
                        value={cbsDraft.description}
                      />
                    </label>
                    <button
                      className="workflowAction primary"
                      disabled={!canCaptureCost || priorityAction === "cbs"}
                      type="submit"
                    >
                      {priorityAction === "cbs" ? "Creating..." : "Create CBS"}
                    </button>
                  </form>

                  <div className="panel">
                    <div className="panelHeader compactHeader">
                      <h2>Vincular WBS + CBS + FBS</h2>
                      <span>{selectedCbs?.code || "CBS pending"}</span>
                    </div>
                    <div className="formColumns">
                      <label>
                        <span>CBS</span>
                        <select
                          disabled={!canCaptureCost || Boolean(priorityAction)}
                          onChange={(event) => {
                            const nextCbs = cbsCatalog.find((item) => item.id === Number(event.target.value));
                            setPriorityDraft((current) => ({ ...current, cbs_id: event.target.value }));
                            if (nextCbs) setRateDraft((current) => ({ ...current, cbs_code: nextCbs.code }));
                          }}
                          value={priorityDraft.cbs_id}
                        >
                          <option value="">Select CBS</option>
                          {cbsCatalog.map((cbs) => (
                            <option key={cbs.id} value={cbs.id}>
                              {cbs.code}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        <span>FBS</span>
                        <select
                          disabled={!canCaptureCost || Boolean(priorityAction)}
                          onChange={(event) =>
                            setPriorityDraft((current) => ({ ...current, funding_source_id: event.target.value }))
                          }
                          value={priorityDraft.funding_source_id}
                        >
                          <option value="">Select FBS</option>
                          {fbsFundingSources.map((source) => (
                            <option key={source.id} value={source.id}>
                              {source.code}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>
                    <div className="formColumns">
                      <label>
                        <span>Control Account</span>
                        <select
                          disabled={!canCaptureCost || Boolean(priorityAction)}
                          onChange={(event) => {
                            const account = activeControlAccounts.find(
                              (item) => item.id === Number(event.target.value)
                            );
                            setPriorityDraft((current) => ({
                              ...current,
                              control_account_id: event.target.value,
                              wbs_id: account?.wbs_id ? String(account.wbs_id) : current.wbs_id,
                            }));
                          }}
                          value={priorityDraft.control_account_id}
                        >
                          <option value="">Select CA</option>
                          {activeControlAccounts.map((account) => (
                            <option key={account.id} value={account.id}>
                              {account.name} - {account.code}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        <span>WBS</span>
                        <select
                          disabled={!canCaptureCost || Boolean(priorityAction)}
                          onChange={(event) =>
                            setPriorityDraft((current) => ({ ...current, wbs_id: event.target.value }))
                          }
                          value={
                            priorityDraft.wbs_id || (selectedWbsForAccount ? String(selectedWbsForAccount.id) : "")
                          }
                        >
                          <option value="">Select WBS</option>
                          {displayWbsCatalog.map((wbs) => (
                            <option key={wbs.id} value={wbs.id}>
                              {wbs.name} - {wbs.code}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>
                    <div className="formColumns">
                      <label>
                        <span>Amount</span>
                        <input
                          disabled={!canCaptureCost || Boolean(priorityAction)}
                          min="0"
                          onChange={(event) =>
                            setPriorityDraft((current) => ({ ...current, amount: event.target.value }))
                          }
                          type="number"
                          value={priorityDraft.amount}
                        />
                      </label>
                      <label>
                        <span>Quantity</span>
                        <input
                          disabled={!canCaptureCost || Boolean(priorityAction)}
                          min="0"
                          onChange={(event) =>
                            setPriorityDraft((current) => ({ ...current, quantity: event.target.value }))
                          }
                          type="number"
                          value={priorityDraft.quantity}
                        />
                      </label>
                    </div>
                    <label>
                      <span>Description</span>
                      <input
                        disabled={!canCaptureCost || Boolean(priorityAction)}
                        onChange={(event) =>
                          setPriorityDraft((current) => ({ ...current, description: event.target.value }))
                        }
                        value={priorityDraft.description}
                      />
                    </label>
                    <div className="actionRow">
                      <button
                        className="workflowAction"
                        disabled={!canCaptureCost || !canRunPriority || Boolean(priorityAction)}
                        onClick={() => handlePriorityBusinessProcess("fund")}
                        type="button"
                      >
                        {priorityAction === "fund" ? "Creating..." : "BP CBS-Fund"}
                      </button>
                      <button
                        className="workflowAction primary"
                        disabled={
                          !canCaptureCost || !canRunPriority || !priorityDraft.wbs_id || Boolean(priorityAction)
                        }
                        onClick={() => handlePriorityBusinessProcess("wbs")}
                        type="button"
                      >
                        {priorityAction === "wbs" ? "Creating..." : "BP CBS-WBS"}
                      </button>
                    </div>
                  </div>
                </div>

                <div className="viewSplit">
                  <form className="adminPanel" onSubmit={handleSovAndFundingCreate}>
                    <div className="panelHeader compactHeader">
                      <h2>SOV Funding</h2>
                      <span>{contractRows.length} contracts</span>
                    </div>
                    <label>
                      <span>Contract</span>
                      <select
                        disabled={!canManageContract || priorityAction === "sov"}
                        onChange={(event) =>
                          setSovDraft((current) => ({ ...current, contract_id: event.target.value }))
                        }
                        required
                        value={sovDraft.contract_id}
                      >
                        <option value="">Select contract</option>
                        {contractRows.map((contract) => (
                          <option key={contract.id} value={contract.id}>
                            {contract.code}
                          </option>
                        ))}
                      </select>
                    </label>
                    <div className="formColumns">
                      <label>
                        <span>Line</span>
                        <input
                          disabled={!canManageContract || priorityAction === "sov"}
                          onChange={(event) => setSovDraft((current) => ({ ...current, line_no: event.target.value }))}
                          required
                          value={sovDraft.line_no}
                        />
                      </label>
                      <label>
                        <span>Amount</span>
                        <input
                          disabled={!canManageContract || priorityAction === "sov"}
                          min="0"
                          onChange={(event) => setSovDraft((current) => ({ ...current, amount: event.target.value }))}
                          required
                          type="number"
                          value={sovDraft.amount}
                        />
                      </label>
                    </div>
                    <label>
                      <span>Description</span>
                      <input
                        disabled={!canManageContract || priorityAction === "sov"}
                        onChange={(event) =>
                          setSovDraft((current) => ({ ...current, description: event.target.value }))
                        }
                        value={sovDraft.description}
                      />
                    </label>
                    <button
                      className="workflowAction primary"
                      disabled={
                        !canManageContract ||
                        !sovDraft.contract_id ||
                        !sovDraft.amount ||
                        !canRunPriority ||
                        priorityAction === "sov"
                      }
                      type="submit"
                    >
                      {priorityAction === "sov" ? "Funding..." : "Create SOV Funding"}
                    </button>
                  </form>

                  <form className="panel" onSubmit={handleRateSheetCreate}>
                    <div className="panelHeader compactHeader">
                      <h2>Rate / Recost</h2>
                      <span>{rateSheets.length} sheets</span>
                    </div>
                    <div className="formColumns">
                      <label>
                        <span>Rate Code</span>
                        <input
                          disabled={!canCaptureCost || priorityAction === "rate"}
                          onChange={(event) => setRateDraft((current) => ({ ...current, code: event.target.value }))}
                          required
                          value={rateDraft.code}
                        />
                      </label>
                      <label>
                        <span>CBS Code</span>
                        <select
                          disabled={!canCaptureCost || priorityAction === "rate"}
                          onChange={(event) =>
                            setRateDraft((current) => ({ ...current, cbs_code: event.target.value }))
                          }
                          value={rateDraft.cbs_code}
                        >
                          <option value="">Select CBS code</option>
                          {rateCbsOptions.map((code) => (
                            <option key={code} value={code}>
                              {code}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>
                    <label>
                      <span>Name</span>
                      <input
                        disabled={!canCaptureCost || priorityAction === "rate"}
                        onChange={(event) => setRateDraft((current) => ({ ...current, name: event.target.value }))}
                        value={rateDraft.name}
                      />
                    </label>
                    <div className="formColumns">
                      <label>
                        <span>Multiplier</span>
                        <input
                          disabled={!canCaptureCost || priorityAction === "rate"}
                          min="0.01"
                          onChange={(event) =>
                            setRateDraft((current) => ({ ...current, multiplier: event.target.value }))
                          }
                          step="0.01"
                          type="number"
                          value={rateDraft.multiplier}
                        />
                      </label>
                      <label>
                        <span>Unit Rate</span>
                        <input
                          disabled={!canCaptureCost || priorityAction === "rate"}
                          min="0"
                          onChange={(event) =>
                            setRateDraft((current) => ({ ...current, unit_rate: event.target.value }))
                          }
                          type="number"
                          value={rateDraft.unit_rate}
                        />
                      </label>
                    </div>
                    <div className="actionRow">
                      <button
                        className="workflowAction"
                        disabled={!canCaptureCost || priorityAction === "rate"}
                        type="submit"
                      >
                        {priorityAction === "rate" ? "Creating..." : "Create Rate"}
                      </button>
                      <button
                        className="workflowAction primary"
                        disabled={
                          !canCaptureCost || !latestActivitySheet || !rateSheets.length || priorityAction === "recost"
                        }
                        onClick={handleRecostLatestActivitySheet}
                        type="button"
                      >
                        {priorityAction === "recost" ? "Recosting..." : "Recost Latest"}
                      </button>
                    </div>
                    <div className="workList compactWorkList">
                      {recostRuns.slice(0, 3).map((run) => (
                        <article key={run.id}>
                          <strong>
                            Run {run.run_no} / {currency(run.total_planned_cost, project.currency)}
                          </strong>
                          <span>
                            {run.updated_rows} rows by {run.created_by || "Project Controls"}
                          </span>
                        </article>
                      ))}
                      {!recostRuns.length && (
                        <article>
                          <strong>Recost History</strong>
                          <span>No runs</span>
                        </article>
                      )}
                    </div>
                  </form>
                </div>

                <div className="viewSplit">
                  <form className="adminPanel" onSubmit={handlePolicySubmit}>
                    <div className="panelHeader compactHeader">
                      <h2>BP Permissions</h2>
                      <span>{bpPolicies.length} policies</span>
                    </div>
                    <div className="formColumns">
                      <label>
                        <span>Process</span>
                        <select
                          disabled={!canConfigure || hardeningAction === "policy"}
                          onChange={(event) =>
                            setPolicyDraft((current) => ({ ...current, process_code: event.target.value }))
                          }
                          value={policyDraft.process_code}
                        >
                          <option value="BP-CBS-WBS">BP CBS-WBS</option>
                          <option value="BP-CBS-FUND">BP CBS-Fund</option>
                        </select>
                      </label>
                      <label>
                        <span>Action</span>
                        <select
                          disabled={!canConfigure || hardeningAction === "policy"}
                          onChange={(event) =>
                            setPolicyDraft((current) => ({ ...current, action: event.target.value }))
                          }
                          value={policyDraft.action}
                        >
                          <option value="approve_baseline">Approve</option>
                          <option value="reject_baseline">Reject</option>
                          <option value="close_action">Close</option>
                        </select>
                      </label>
                    </div>
                    <div className="formColumns">
                      <label>
                        <span>Role</span>
                        <select
                          disabled={!canConfigure || hardeningAction === "policy"}
                          onChange={(event) =>
                            setPolicyDraft((current) => ({ ...current, required_role: event.target.value }))
                          }
                          value={policyDraft.required_role}
                        >
                          {policyRoleOptions.map((role) => (
                            <option key={role} value={role}>
                              {role}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        <span>Permission</span>
                        <select
                          disabled={!canConfigure || hardeningAction === "policy"}
                          onChange={(event) =>
                            setPolicyDraft((current) => ({ ...current, permission_key: event.target.value }))
                          }
                          value={policyDraft.permission_key}
                        >
                          <option value="can_approve_workflow">Approve Workflow</option>
                          <option value="can_capture_cost">Capture Cost</option>
                          <option value="can_configure">Configure</option>
                        </select>
                      </label>
                    </div>
                    <button
                      className="workflowAction primary"
                      disabled={!canConfigure || hardeningAction === "policy"}
                      type="submit"
                    >
                      <ShieldCheck size={15} />
                      {hardeningAction === "policy" ? "Saving..." : "Save Policy"}
                    </button>
                    <div className="workList compactWorkList">
                      {bpPolicies.slice(0, 3).map((policy) => (
                        <article key={policy.id}>
                          <strong>
                            {policy.process_code} / {statusLabel(policy.action)}
                          </strong>
                          <span>
                            {policy.required_role || "Any role"} / v{policy.version}
                          </span>
                        </article>
                      ))}
                    </div>
                  </form>

                  <form className="panel" onSubmit={handleLineItemUpdate}>
                    <div className="panelHeader compactHeader">
                      <h2>Line Versions</h2>
                      <span>{bpLineItems.length} items</span>
                    </div>
                    <label>
                      <span>Line Item</span>
                      <select
                        disabled={!canCaptureCost || hardeningAction === "line" || !bpLineItems.length}
                        onChange={(event) => {
                          const nextLine = bpLineItems.find((line) => String(line.id) === event.target.value);
                          if (nextLine) void handleLineItemSelect(nextLine);
                        }}
                        value={lineEditDraft.line_item_id}
                      >
                        {bpLineItems.map((line) => (
                          <option key={line.id} value={line.id}>
                            #{line.id} / {currency(line.amount, project.currency)} / v{line.version}
                          </option>
                        ))}
                      </select>
                    </label>
                    <div className="formColumns">
                      <label>
                        <span>Amount</span>
                        <input
                          disabled={!canCaptureCost || hardeningAction === "line" || !selectedLineItem}
                          min="0"
                          onChange={(event) =>
                            setLineEditDraft((current) => ({ ...current, amount: event.target.value }))
                          }
                          type="number"
                          value={lineEditDraft.amount}
                        />
                      </label>
                      <label>
                        <span>Quantity</span>
                        <input
                          disabled={!canCaptureCost || hardeningAction === "line" || !selectedLineItem}
                          min="0"
                          onChange={(event) =>
                            setLineEditDraft((current) => ({ ...current, quantity: event.target.value }))
                          }
                          type="number"
                          value={lineEditDraft.quantity}
                        />
                      </label>
                    </div>
                    <label>
                      <span>Description</span>
                      <input
                        disabled={!canCaptureCost || hardeningAction === "line" || !selectedLineItem}
                        onChange={(event) =>
                          setLineEditDraft((current) => ({ ...current, description: event.target.value }))
                        }
                        value={lineEditDraft.description}
                      />
                    </label>
                    <label>
                      <span>Change Note</span>
                      <input
                        disabled={!canCaptureCost || hardeningAction === "line" || !selectedLineItem}
                        onChange={(event) =>
                          setLineEditDraft((current) => ({ ...current, change_note: event.target.value }))
                        }
                        value={lineEditDraft.change_note}
                      />
                    </label>
                    <button
                      className="workflowAction primary"
                      disabled={!canCaptureCost || !selectedLineItem || hardeningAction === "line"}
                      type="submit"
                    >
                      <Save size={15} />
                      {hardeningAction === "line" ? "Saving..." : "Save Version"}
                    </button>
                    <div className="workList compactWorkList">
                      {bpLineItemRevisions.slice(0, 3).map((revision) => (
                        <article key={revision.id}>
                          <strong>
                            v{revision.previous_version} to v{revision.new_version}
                          </strong>
                          <span>
                            {currency(revision.previous_amount, project.currency)} to{" "}
                            {currency(revision.new_amount, project.currency)}
                          </span>
                        </article>
                      ))}
                    </div>
                  </form>
                </div>

                <div className="panel wide">
                  <div className="panelHeader compactHeader">
                    <div className="agentProfileBlock">
                      <h2>AI Control Auditor</h2>
                      <small>Senior AWP Packaging Advisor</small>
                    </div>
                    <span>{latestAgentRun ? `${latestAgentRun.score}/100` : "No run"}</span>
                  </div>
                  <div className="gateFacts">
                    <div>
                      <span>Mode</span>
                      <strong>{latestAgentRun?.run_mode || "deterministic"}</strong>
                    </div>
                    <div>
                      <span>Model</span>
                      <strong>{latestAgentRun?.model_name || "low-cost audit rules"}</strong>
                    </div>
                    <div>
                      <span>Findings</span>
                      <strong>{agentFindings.length}</strong>
                    </div>
                  </div>
                  <div className="actionRow">
                    <button
                      className="workflowAction primary"
                      disabled={agentAction}
                      onClick={handleControlAuditAgentRun}
                      type="button"
                    >
                      <ShieldCheck size={15} />
                      {agentAction ? "Auditing..." : "Run Audit"}
                    </button>
                    <button
                      className="workflowAction"
                      disabled={agentAction}
                      onClick={handleCreateAwpDraftPackages}
                      type="button"
                    >
                      <PackagePlus size={15} />
                      {agentAction ? "Creating..." : "Create Draft Packages"}
                    </button>
                  </div>
                  <div className="workList compactWorkList">
                    {latestAgentRun && (
                      <article>
                        <strong>{latestAgentRun.summary}</strong>
                        <span>
                          {latestAgentRun.agent_name} by {latestAgentRun.created_by || "Project Controls"}
                        </span>
                      </article>
                    )}
                    {agentFindings.slice(0, 5).map((finding) => (
                      <article key={finding.id} className={finding.severity === "high" ? "risk" : ""}>
                        <strong>
                          {statusLabel(finding.severity)} / {finding.title}
                        </strong>
                        <span>{finding.evidence}</span>
                        <span>{finding.recommendation}</span>
                      </article>
                    ))}
                    {!latestAgentRun && (
                      <article>
                        <strong>No agent audit yet</strong>
                        <span>Run the read-only audit to prioritize BP policy, recost and funding checks.</span>
                      </article>
                    )}
                  </div>
                </div>

                <div className="panel wide">
                  <div className="panelHeader compactHeader">
                    <h2>Traceability</h2>
                    <span>FBS-WBS-AWP-CA-CBS-Cost Code</span>
                  </div>
                  <table>
                    <thead>
                      <tr>
                        <th>Project / FBS</th>
                        <th>WBS / AWP</th>
                        <th>Control Account / CBS</th>
                        <th>Cost Code / Contract</th>
                        <th>Budget</th>
                        <th>Funding</th>
                        <th>Forecast</th>
                      </tr>
                    </thead>
                    <tbody>
                      {integratedMatrix.map((row) => {
                        const rowWbs = displayWbsCatalog.find((node) => node.code === row.wbs_code);
                        return (
                          <tr key={row.cost_code}>
                            <td>
                              <strong>{row.project_code}</strong>
                              <span>{row.fbs_code}</span>
                            </td>
                            <td>
                              <strong>{rowWbs?.name ?? row.wbs_code}</strong>
                              <span>
                                {row.awp_package_type || "AWP"} {row.awp_package_code || "pending"} /{" "}
                                {publicWbsCode(rowWbs?.code ?? row.wbs_code, project)}
                              </span>
                            </td>
                            <td>
                              <strong>{publicControlAccountCode(row.control_account_code, project)}</strong>
                              <span>{row.cbs_code}</span>
                            </td>
                            <td>
                              <strong>{row.cost_code}</strong>
                              <span>{row.contract_ref || "Commitment pending"}</span>
                            </td>
                            <td>{currency(row.budget, project.currency)}</td>
                            <td>
                              <strong>{currency(row.funds_available, project.currency)}</strong>
                              <span>{currency(row.committed, project.currency)} committed</span>
                            </td>
                            <td>
                              <strong>{currency(row.forecast, project.currency)}</strong>
                              <span>{currency(row.balance, project.currency)} balance</span>
                            </td>
                          </tr>
                        );
                      })}
                      {!integratedMatrix.length && (
                        <tr>
                          <td colSpan={7}>
                            <strong>No integrated matrix rows</strong>
                            <span>Create cost codes linked to FBS, WBS, control accounts and CBS.</span>
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
                <div className="panel wide">
                  <div className="panelHeader compactHeader">
                    <h2>Reconciliation</h2>
                    <span>{reconciliationRows.length} rows</span>
                  </div>
                  <div className="actionRow">
                    <button
                      className="workflowAction"
                      disabled={hardeningAction === "export-xlsx"}
                      onClick={() => void handleReconciliationExport("xlsx")}
                      type="button"
                    >
                      <Download size={15} />
                      {hardeningAction === "export-xlsx" ? "Exporting..." : "Export XLSX"}
                    </button>
                    <button
                      className="workflowAction"
                      disabled={hardeningAction === "export-pdf"}
                      onClick={() => void handleReconciliationExport("pdf")}
                      type="button"
                    >
                      <Download size={15} />
                      {hardeningAction === "export-pdf" ? "Exporting..." : "Export PDF"}
                    </button>
                  </div>
                  <table>
                    <thead>
                      <tr>
                        <th>WBS / CBS</th>
                        <th>FBS / CA</th>
                        <th>Contract</th>
                        <th>Budget</th>
                        <th>SOV</th>
                        <th>Funding</th>
                        <th>Forecast</th>
                      </tr>
                    </thead>
                    <tbody>
                      {reconciliationRows.slice(0, 8).map((row) => {
                        const rowWbs = displayWbsCatalog.find((node) => node.code === row.wbs_code);
                        return (
                          <tr key={`${row.wbs_code}-${row.cbs_code}-${row.contract_ref}`}>
                            <td>
                              <strong>{rowWbs?.name ?? row.wbs_code ?? "WBS pending"}</strong>
                              <span>
                                {row.cbs_code || "CBS pending"} / {publicWbsCode(rowWbs?.code ?? row.wbs_code, project)}
                              </span>
                            </td>
                            <td>
                              <strong>{row.fbs_code || "FBS pending"}</strong>
                              <span>{publicControlAccountCode(row.control_account_code || "CA pending", project)}</span>
                            </td>
                            <td>{row.contract_ref || "Pending"}</td>
                            <td>{currency(row.budget, project.currency)}</td>
                            <td>{currency(row.sov_amount, project.currency)}</td>
                            <td>{currency(row.funded_amount, project.currency)}</td>
                            <td>
                              <strong>{currency(row.forecast, project.currency)}</strong>
                              <span>{currency(row.variance, project.currency)} variance</span>
                            </td>
                          </tr>
                        );
                      })}
                      {!reconciliationRows.length && (
                        <tr>
                          <td colSpan={7}>
                            <strong>No reconciliation rows</strong>
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>
                {integratedMessage && <div className="uploadMessage success">{integratedMessage}</div>}
                {integratedError && <div className="uploadMessage error">{integratedError}</div>}
              </>
            )}
            {visibleControlView === "baseline" && (
              <>
                <div className="panelHeader">
                  <h2>Baseline Control</h2>
                  <span>
                    {dashboard.schedule_activity_count} activities / {dashboard.schedule_relationship_count} links
                  </span>
                </div>
                {guidedFlow && (
                  <CostCurrencyGate
                    gate={guidedFlow.cost_currency_gate}
                    projectCurrency={project.currency}
                    pending={currencyAction}
                    onConfirm={handleConfirmCurrency}
                  />
                )}
                <div className="gateFacts">
                  <div>
                    <span>Current Baseline</span>
                    <strong>{activeImport?.baseline_name ?? "Pending upload"}</strong>
                  </div>
                  <div>
                    <span>Data Quality Gate</span>
                    <strong>
                      {activeImport ? `${activeImport.quality_score.toFixed(0)}% / ${activeImport.status}` : "Open"}
                    </strong>
                  </div>
                  <div>
                    <span>Data Date</span>
                    <strong>{activeImport?.data_date ?? "Pending"}</strong>
                  </div>
                  <div>
                    <span>Baseline Versions</span>
                    <strong>{dashboard.baseline_versions.length}</strong>
                  </div>
                </div>
                <div className="panel dcmaMetricsPanel">
                  <div className="panelHeader compactHeader">
                    <h2>DCMA Metrics</h2>
                    <span>{scheduleQualityMetrics.length} checks</span>
                  </div>
                  <div className="dcmaMetricsTable" aria-label="DCMA schedule quality metrics">
                    <table>
                      <thead>
                        <tr>
                          <th>Standard</th>
                          <th>Metric</th>
                          <th>Status</th>
                          <th>Count</th>
                          <th>Percent</th>
                          <th>Threshold</th>
                        </tr>
                      </thead>
                      <tbody>
                        {scheduleQualityMetrics.length ? (
                          scheduleQualityMetrics.map((metric) => (
                            <tr key={metric.key}>
                              <td>{metric.standard}</td>
                              <td>
                                <strong>{metric.label}</strong>
                                <span>{metric.description}</span>
                              </td>
                              <td>
                                <span className={`qualityStatus ${metric.status}`}>{statusLabel(metric.status)}</span>
                              </td>
                              <td>{metric.total_count ? `${metric.item_count} / ${metric.total_count}` : "N/A"}</td>
                              <td>{metric.total_count ? `${metric.percent.toFixed(1)}%` : "N/A"}</td>
                              <td>{metric.threshold}</td>
                            </tr>
                          ))
                        ) : (
                          <tr>
                            <td colSpan={6}>
                              <strong>No DCMA metrics</strong>
                              <span>Load a schedule baseline to calculate quality metrics.</span>
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
                <div className="viewSplit">
                  <div className="panel">
                    <div className="panelHeader compactHeader">
                      <h2>Baseline Versions</h2>
                      <span>{dashboard.baseline_versions.length} records</span>
                    </div>
                    <div className="workList">
                      {dashboard.baseline_versions.length ? (
                        dashboard.baseline_versions.map((baseline) => (
                          <article key={baseline.id}>
                            <strong>
                              BL-{baseline.version_no.toString().padStart(2, "0")} / {statusLabel(baseline.status)}
                            </strong>
                            <span>{baseline.name}</span>
                            <small>
                              {baseline.data_date ?? "No data date"} / Quality {baseline.quality_score.toFixed(0)}%
                            </small>
                          </article>
                        ))
                      ) : (
                        <article>
                          <strong>No baseline versions yet</strong>
                          <span>Upload XML/XER to create the first controlled schedule baseline.</span>
                        </article>
                      )}
                    </div>
                  </div>
                  <div className="panel">
                    <div className="panelHeader compactHeader">
                      <h2>Quality Findings</h2>
                      <span>{dashboard.schedule_findings.length} records</span>
                    </div>
                    <div className="qualityList">
                      {dashboard.schedule_findings.length ? (
                        dashboard.schedule_findings.map((finding) => (
                          <article key={finding.id}>
                            <div>
                              <strong>{finding.check_code}</strong>
                              <span className={`qualityStatus ${finding.severity.toLowerCase()}`}>
                                {statusLabel(finding.severity)}
                              </span>
                            </div>
                            <p>{finding.message}</p>
                            <small>{finding.item_count} items</small>
                          </article>
                        ))
                      ) : (
                        <article>
                          <div>
                            <strong>No findings</strong>
                            <span className="qualityStatus pass">Pass</span>
                          </div>
                          <p>The active schedule has no stored QA findings.</p>
                        </article>
                      )}
                    </div>
                  </div>
                </div>
              </>
            )}
            {visibleControlView === "progress" && (
              <>
                <div className="panelHeader">
                  <h2>Measuring Progress</h2>
                  <span>{dashboard.latest_progress_records.length} records</span>
                </div>
                <div className="workList">
                  {dashboard.latest_progress_records.length ? (
                    dashboard.latest_progress_records.map((record) => (
                      <article key={record.id}>
                        <strong>{controlAccountLabel(dashboard, record.control_account_id)}</strong>
                        <span>{record.physical_percent.toFixed(1)}% physical progress</span>
                        <small>
                          {record.quantity_installed} installed / {record.labor_hours} hours /{" "}
                          {record.reported_on ?? "No report date"}
                        </small>
                      </article>
                    ))
                  ) : (
                    <article>
                      <strong>No progress captured</strong>
                      <span>Progress records will appear here after field updates are captured.</span>
                    </article>
                  )}
                </div>
              </>
            )}
            {visibleControlView === "costs" && (
              <>
                <div className="panelHeader">
                  <h2>Cost Items</h2>
                  <span>
                    {costFundingTraceabilityRows.length} linked row(s) / {currency(totalFunding, project.currency)}{" "}
                    funding
                  </span>
                </div>
                <section aria-label="Cost and Funding Traceability" className="panel wide">
                  <div className="panelHeader compactHeader">
                    <h2>Cost and Funding Traceability</h2>
                    <span>{baselineOnlyEvm ? "baseline only" : "period control"}</span>
                  </div>
                  <p className="projectHint">
                    Esta tabla muestra la cadena operativa: WBS del cronograma, cuenta de control, CBS/cost code,
                    presupuesto BAC, valores EVM del corte y fuente FBS. Si solo existe linea base, EV y AC quedan en
                    cero.
                  </p>
                  {costFundingTraceabilityRows.length ? (
                    <table>
                      <thead>
                        <tr>
                          <th>WBS</th>
                          <th>Control Account</th>
                          <th>CBS / Cost Code</th>
                          <th>BAC</th>
                          <th>EV</th>
                          <th>AC</th>
                          <th>CPI</th>
                          <th>FBS / Funding</th>
                          <th>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {costFundingTraceabilityRows.map((row) => (
                          <tr key={row.id}>
                            <td>
                              <strong>{row.wbsName}</strong>
                              <span>{row.wbsCode}</span>
                            </td>
                            <td>
                              <strong>{row.controlAccountCode}</strong>
                              <span>{row.controlAccountName}</span>
                            </td>
                            <td>
                              <strong>{row.cbsCode}</strong>
                              <span>{row.costCode}</span>
                            </td>
                            <td>{currency(row.bac, project.currency)}</td>
                            <td>{currency(row.ev, project.currency)}</td>
                            <td>{currency(row.ac, project.currency)}</td>
                            <td>{row.cpi === null ? "N/A" : row.cpi.toFixed(3)}</td>
                            <td>
                              <strong>{row.fbsCode}</strong>
                              <span>
                                {row.fundingName}
                                {row.fundingAmount ? ` / ${currency(row.fundingAmount, project.currency)}` : ""}
                              </span>
                            </td>
                            <td>
                              <strong>{row.status}</strong>
                              <span>{row.fundingStatus}</span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <div className="workspaceEmpty">
                      <strong>No cost and funding traceability yet</strong>
                      <p>Load cost lines and link WBS, control accounts, CBS and FBS before using this module.</p>
                    </div>
                  )}
                </section>
              </>
            )}
            {visibleControlView === "decisions" && (
              <>
                <div className="panelHeader">
                  <h2>Scope Changes</h2>
                  <span>{dashboard.changes.length} changes</span>
                </div>
                <div className="workList">
                  {dashboard.changes.length ? (
                    dashboard.changes.map((change) => (
                      <article key={change.id}>
                        <strong>{change.title}</strong>
                        <span>{change.deviation}</span>
                        <small>
                          {currency(change.cost_impact, project.currency)} / {change.schedule_impact_days} days /{" "}
                          {statusLabel(change.status)}
                        </small>
                      </article>
                    ))
                  ) : (
                    <article>
                      <strong>No decisions pending</strong>
                      <span>Change and deviation decisions will be listed here.</span>
                    </article>
                  )}
                </div>
              </>
            )}
            {visibleControlView === "evidence" && (
              <>
                <div className="panelHeader">
                  <h2>Evidence Register</h2>
                  <span>{dashboard.document_control_summary.controlled_document_score.toFixed(0)}% controlled</span>
                </div>
                <div className="awpSummary">
                  <article>
                    <span>Documents</span>
                    <strong>{dashboard.document_control_summary.total_documents ?? 0}</strong>
                    <small>{dashboard.document_control_summary.current_documents ?? 0} current</small>
                  </article>
                  <article className={dashboard.document_control_summary.overdue_reviews ? "risk" : ""}>
                    <span>Reviews</span>
                    <strong>{dashboard.document_control_summary.outstanding_reviews ?? 0}</strong>
                    <small>{dashboard.document_control_summary.overdue_reviews ?? 0} overdue</small>
                  </article>
                  <article>
                    <span>Transmittals</span>
                    <strong>{dashboard.document_control_summary.transmittals_sent ?? 0}</strong>
                    <small>{dashboard.document_control_summary.open_mail ?? 0} open mail</small>
                  </article>
                  <article>
                    <span>Attachments</span>
                    <strong>{dashboard.document_attachments.length}</strong>
                    <small>Evidence files</small>
                  </article>
                </div>
                <div className="workList">
                  {dashboard.documents.length ? (
                    dashboard.documents.slice(0, 12).map((document) => (
                      <article key={document.id}>
                        <strong>
                          {document.document_number} / Rev {document.revision}
                        </strong>
                        <span>{document.title}</span>
                        <small>
                          {document.doc_type} / {statusLabel(document.review_status)} / {document.file_name}
                        </small>
                      </article>
                    ))
                  ) : (
                    <article>
                      <strong>No evidence documents yet</strong>
                      <span>Controlled documents and attachments will appear here.</span>
                    </article>
                  )}
                </div>
              </>
            )}
            {visibleControlView === "work-packages" && (
              <>
                <div className="panelHeader">
                  <h2>Work Packages</h2>
                  <span>
                    {dashboard.awp_summary.cwp_count} CWP / {dashboard.awp_summary.iwp_count} IWP /{" "}
                    {dashboard.awp_summary.twp_count} TWP / {dashboard.awp_summary.top_count} TOP
                  </span>
                </div>

                <div className="awpSummary">
                  <article className={dashboard.awp_summary.blocking_constraints ? "risk" : ""}>
                    <span>Open Constraints</span>
                    <strong>{dashboard.awp_summary.open_constraints}</strong>
                    <small>{dashboard.awp_summary.blocking_constraints} blocking</small>
                  </article>
                  <article className={dashboard.awp_summary.high_priority_constraints ? "risk" : ""}>
                    <span>High Priority</span>
                    <strong>{dashboard.awp_summary.high_priority_constraints}</strong>
                    <small>Before release</small>
                  </article>
                  <article>
                    <span>Closure Evidence</span>
                    <strong>{dashboard.awp_summary.closure_evidence_count}</strong>
                    <small>Closed constraints</small>
                  </article>
                  <article>
                    <span>Ready Packages</span>
                    <strong>{dashboard.awp_summary.ready_for_release}</strong>
                    <small>{dashboard.awp_summary.blocked_packages} blocked</small>
                  </article>
                </div>

                <section aria-label="Package coding rule" className="panel packageCodingPanel">
                  <div className="panelHeader compactHeader">
                    <h2>Package Coding Rule</h2>
                    <span>Project and WBS name to CWA to CWP to IWP</span>
                  </div>
                  <div className="packageCodeLegend">
                    <article>
                      <strong>CWA-[PROJECT]-[WBS NAME]</strong>
                      <span>Construction Work Area from the project and WBS boundary name.</span>
                    </article>
                    <article>
                      <strong>CWP-[PROJECT]-[WBS NAME]-[DISC]-[NN]</strong>
                      <span>Construction Work Package with discipline and sequence inside the WBS name.</span>
                    </article>
                    <article>
                      <strong>IWP-[PROJECT]-[WBS NAME]-[DISC]-[NN]-IW##</strong>
                      <span>
                        Installation Work Package that inherits the CWP path and is released by workface constraints.
                      </span>
                    </article>
                  </div>
                </section>

                <div className="awpVisualGrid">
                  <section aria-label="AWP package tree" className="panel awpTreePanel">
                    <div className="panelHeader compactHeader">
                      <h2>
                        <GitBranch size={18} /> AWP Package Tree
                      </h2>
                      <span>WBS names to CWA, CWP and IWP hierarchy</span>
                    </div>
                    {workPackageTree.length ? (
                      <div className="awpPackageTree" role="tree">
                        {workPackageTree.map((workPackage) => (
                          <AwpPackageTreeBranch
                            allPackages={dashboard.work_packages}
                            constraintsByPackage={constraintsByPackage}
                            depth={0}
                            key={workPackage.id}
                            node={workPackage}
                            wbsCatalog={wbsCatalog}
                          />
                        ))}
                      </div>
                    ) : (
                      <div className="emptyState">
                        <strong>No package hierarchy yet</strong>
                        <span>Create AWP drafts to see CWA, CWP and IWP relationships.</span>
                      </div>
                    )}
                  </section>

                  <section aria-label="Path of Construction route" className="panel awpPocPanel">
                    <div className="panelHeader compactHeader">
                      <h2>Path of Construction Route</h2>
                      <span>{workPackagePocRoute.length} steps</span>
                    </div>
                    {workPackagePocRoute.length ? (
                      <ol className="pocRoute">
                        {workPackagePocRoute.map((workPackage, index) => (
                          <li key={workPackage.id}>
                            <strong>{index + 1}</strong>
                            <div>
                              <span>{workPackageDisplayLabel(wbsCatalog, workPackage)}</span>
                              <p>
                                {humanizePackageText(
                                  workPackage.path_of_construction,
                                  wbsCatalog,
                                  dashboard.work_packages
                                )}
                              </p>
                              <small>
                                {statusLabel(workPackage.readiness_status)} /{" "}
                                {constraintsByPackage[workPackage.id] ?? 0} blockers
                              </small>
                            </div>
                          </li>
                        ))}
                      </ol>
                    ) : (
                      <div className="emptyState">
                        <strong>No Path of Construction defined</strong>
                        <span>Add POC text to packages to build the route.</span>
                      </div>
                    )}
                  </section>
                </div>

                <div className="viewSplit">
                  <div className="panel">
                    <div className="panelHeader compactHeader">
                      <h2>Package Definition Register</h2>
                      <span>{dashboard.work_packages.length} records</span>
                    </div>
                    <div className="workList">
                      {dashboard.work_packages.map((workPackage) => (
                        <article
                          className={constraintsByPackage[workPackage.id] ? "blockedPackage" : ""}
                          key={workPackage.id}
                        >
                          <strong>{workPackageDisplayLabel(wbsCatalog, workPackage)}</strong>
                          <span>{workPackage.title}</span>
                          <small>{workPackageTechnicalCode(workPackage)}</small>
                          <small>
                            POC:{" "}
                            {humanizePackageText(
                              workPackage.path_of_construction,
                              wbsCatalog,
                              dashboard.work_packages
                            ) || "No path defined"}
                          </small>
                          <div className="awpEvidence">
                            <span>Agent evidence</span>
                            <p>
                              {humanizePackageText(workPackage.main_constraints, wbsCatalog, dashboard.work_packages) ||
                                "No agent evidence recorded yet. Review package boundary, schedule, quantities and funding before release."}
                            </p>
                            <small>Draft generated by agent; requires human validation before release.</small>
                          </div>
                          <div className="packageFacts">
                            <span>{statusLabel(workPackage.readiness_status)}</span>
                            <span>{controlAccountLabel(dashboard, workPackage.control_account_id)}</span>
                            <span>WBS: {workPackageWbsName(wbsCatalog, workPackage)}</span>
                            <span>
                              Release {workPackage.release_required_on ?? workPackage.planned_start ?? "Pending"}
                            </span>
                            <span>{constraintsByPackage[workPackage.id] ?? 0} blockers</span>
                          </div>
                        </article>
                      ))}
                    </div>
                  </div>

                  <div className="panel">
                    <div className="panelHeader compactHeader">
                      <h2>Constraint Register</h2>
                      <span>{dashboard.work_package_constraints.length} records</span>
                    </div>
                    <form className="captureForm compactForm" onSubmit={handleCreateWorkPackageConstraint}>
                      <label>
                        <span>Package</span>
                        <select
                          value={constraintDraft.work_package_id}
                          onChange={(event) =>
                            setConstraintDraft((draft) => ({ ...draft, work_package_id: event.target.value }))
                          }
                        >
                          <option value="">Select package</option>
                          {dashboard.work_packages.map((workPackage) => (
                            <option key={workPackage.id} value={workPackage.id}>
                              {workPackageDisplayLabel(wbsCatalog, workPackage)} - {workPackage.title}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        <span>Type</span>
                        <select
                          value={constraintDraft.constraint_type}
                          onChange={(event) =>
                            setConstraintDraft((draft) => ({ ...draft, constraint_type: event.target.value }))
                          }
                        >
                          <option>Engineering Documents</option>
                          <option>Materials</option>
                          <option>Safety / Quality</option>
                          <option>Permits / Access</option>
                          <option>Recost / Funding</option>
                          <option>Field Execution</option>
                        </select>
                      </label>
                      <label>
                        <span>Owner Role</span>
                        <input
                          value={constraintDraft.owner_role}
                          onChange={(event) =>
                            setConstraintDraft((draft) => ({ ...draft, owner_role: event.target.value }))
                          }
                        />
                      </label>
                      <label>
                        <span>Required</span>
                        <input
                          type="date"
                          value={constraintDraft.required_by}
                          onChange={(event) =>
                            setConstraintDraft((draft) => ({ ...draft, required_by: event.target.value }))
                          }
                        />
                      </label>
                      <label>
                        <span>Priority</span>
                        <select
                          value={constraintDraft.priority}
                          onChange={(event) =>
                            setConstraintDraft((draft) => ({ ...draft, priority: event.target.value }))
                          }
                        >
                          <option value="medium">Medium</option>
                          <option value="high">High</option>
                          <option value="low">Low</option>
                        </select>
                      </label>
                      <label>
                        <span>Evidence</span>
                        <input
                          placeholder="Document, RFI or checklist reference"
                          value={constraintDraft.evidence_ref}
                          onChange={(event) =>
                            setConstraintDraft((draft) => ({ ...draft, evidence_ref: event.target.value }))
                          }
                        />
                      </label>
                      <label className="checkboxLine">
                        <input
                          checked={constraintDraft.blocking}
                          type="checkbox"
                          onChange={(event) =>
                            setConstraintDraft((draft) => ({ ...draft, blocking: event.target.checked }))
                          }
                        />
                        <span>Blocking</span>
                      </label>
                      <label className="fullWidth">
                        <span>Description</span>
                        <textarea
                          placeholder="Describe what must be resolved before package release"
                          value={constraintDraft.description}
                          onChange={(event) =>
                            setConstraintDraft((draft) => ({ ...draft, description: event.target.value }))
                          }
                        />
                      </label>
                      <button
                        className="workflowAction primary"
                        disabled={constraintAction || !dashboard.work_packages.length}
                        type="submit"
                      >
                        {constraintAction ? "Adding..." : "Add Constraint"}
                      </button>
                    </form>
                    <div className="workList">
                      {dashboard.work_package_constraints.map((constraint) => (
                        <article
                          className={constraint.status === "open" && constraint.blocking ? "blockedPackage" : undefined}
                          key={constraint.id}
                        >
                          <strong>
                            {statusLabel(constraint.priority)} / {packageLabel(dashboard, constraint.work_package_id)}
                          </strong>
                          <span>{constraint.description}</span>
                          <small>
                            {constraint.constraint_type} / Required {constraint.required_by ?? "Pending"} /{" "}
                            {statusLabel(constraint.status)}
                          </small>
                          <div className="packageFacts">
                            <span>{constraint.owner_role}</span>
                            <span>{constraint.evidence_ref || "Evidence pending"}</span>
                            <span>{constraint.closed_on ? `Closed ${constraint.closed_on}` : "Open"}</span>
                          </div>
                        </article>
                      ))}
                    </div>
                  </div>
                </div>
              </>
            )}
            {visibleControlView === "admin" && (
              <>
                <div className="panelHeader">
                  <h2>User Creator</h2>
                  <span>{dashboard.project_team.length} project assignments</span>
                </div>
                <div className="viewSplit">
                  <form className="adminPanel" onSubmit={handleUserCreate}>
                    <div className="panelHeader compactHeader">
                      <h2>Create User</h2>
                      <span>{users.length} tenant users / default password 1234</span>
                    </div>
                    <label>
                      <span>Full Name</span>
                      <input
                        disabled={!canConfigure || userAction}
                        onChange={(event) => setUserDraft((current) => ({ ...current, full_name: event.target.value }))}
                        required
                        value={userDraft.full_name}
                      />
                    </label>
                    <label>
                      <span>Login Email</span>
                      <input
                        disabled={!canConfigure || userAction}
                        onChange={(event) => setUserDraft((current) => ({ ...current, email: event.target.value }))}
                        required
                        type="email"
                        value={userDraft.email}
                      />
                    </label>
                    <div className="formColumns">
                      <label>
                        <span>Temporary Password</span>
                        <input
                          disabled={!canConfigure || userAction}
                          onChange={(event) =>
                            setUserDraft((current) => ({ ...current, password: event.target.value }))
                          }
                          required
                          type="text"
                          value={userDraft.password}
                        />
                      </label>
                      <label>
                        <span>Role Profile</span>
                        <select
                          disabled={!canConfigure || userAction}
                          onChange={(event) => setUserDraft((current) => ({ ...current, role: event.target.value }))}
                          value={userDraft.role}
                        >
                          {roles.map((role) => (
                            <option key={role.role} value={role.role}>
                              {role.role}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>
                    <label>
                      <span>Title</span>
                      <input
                        disabled={!canConfigure || userAction}
                        onChange={(event) => setUserDraft((current) => ({ ...current, title: event.target.value }))}
                        value={userDraft.title}
                      />
                    </label>
                    <div className="permissionStrip">
                      {roles.find((role) => role.role === userDraft.role)?.can_capture_progress && (
                        <span>Progress</span>
                      )}
                      {roles.find((role) => role.role === userDraft.role)?.can_capture_cost && <span>Cost</span>}
                      {roles.find((role) => role.role === userDraft.role)?.can_approve_workflow && <span>Approve</span>}
                      {roles.find((role) => role.role === userDraft.role)?.can_manage_contract && <span>Contract</span>}
                      {roles.find((role) => role.role === userDraft.role)?.can_configure && <span>Admin</span>}
                    </div>
                    <button className="workflowAction primary" disabled={!canConfigure || userAction} type="submit">
                      {userAction ? "Creating..." : "Create User & Assign Role"}
                    </button>
                    {userMessage && <div className="uploadMessage success">{userMessage}</div>}
                    {userError && <div className="uploadMessage error">{userError}</div>}
                  </form>

                  <form className="adminPanel" onSubmit={handleManagedUserUpdate}>
                    <div className="panelHeader compactHeader">
                      <h2>Manage User Access</h2>
                      <span>{selectedIamUserId ? "tenant user selected" : "no user selected"}</span>
                    </div>
                    <label>
                      <span>Manage Tenant User</span>
                      <select
                        disabled={!canConfigure || iamAction !== null || users.length < 1}
                        onChange={(event) => handleManagedUserSelect(event.target.value)}
                        value={selectedIamUserId}
                      >
                        {users.map((item) => (
                          <option key={item.id} value={item.id}>
                            {item.full_name}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label>
                      <span>Managed Full Name</span>
                      <input
                        disabled={!canConfigure || iamAction !== null || !selectedIamUserId}
                        onChange={(event) =>
                          setManagedUserDraft((current) => ({ ...current, full_name: event.target.value }))
                        }
                        required
                        value={managedUserDraft.full_name}
                      />
                    </label>
                    <label>
                      <span>Managed Email</span>
                      <input
                        disabled={!canConfigure || iamAction !== null || !selectedIamUserId}
                        onChange={(event) =>
                          setManagedUserDraft((current) => ({ ...current, email: event.target.value }))
                        }
                        required
                        type="email"
                        value={managedUserDraft.email}
                      />
                    </label>
                    <label>
                      <span>Managed Title</span>
                      <input
                        disabled={!canConfigure || iamAction !== null || !selectedIamUserId}
                        onChange={(event) =>
                          setManagedUserDraft((current) => ({ ...current, title: event.target.value }))
                        }
                        value={managedUserDraft.title}
                      />
                    </label>
                    <button
                      className="workflowAction primary"
                      disabled={!canConfigure || iamAction !== null || !selectedIamUserId}
                      type="submit"
                    >
                      {iamAction === "update" ? "Updating..." : "Update User"}
                    </button>
                    <div className="formColumns">
                      <label>
                        <span>New Temporary Password</span>
                        <input
                          disabled={!canConfigure || iamAction !== null || !selectedIamUserId}
                          onChange={(event) =>
                            setManagedUserDraft((current) => ({ ...current, password: event.target.value }))
                          }
                          type="text"
                          value={managedUserDraft.password}
                        />
                      </label>
                      <label>
                        <span>Assign Role</span>
                        <select
                          disabled={!canConfigure || iamAction !== null}
                          onChange={(event) => setUserDraft((current) => ({ ...current, role: event.target.value }))}
                          value={userDraft.role}
                        >
                          {roles.map((role) => (
                            <option key={role.role} value={role.role}>
                              {role.role}
                            </option>
                          ))}
                        </select>
                      </label>
                    </div>
                    <div className="actionRow">
                      <button
                        className="workflowAction"
                        disabled={
                          !canConfigure || iamAction !== null || !selectedIamUserId || !managedUserDraft.password
                        }
                        onClick={handleManagedPasswordReset}
                        type="button"
                      >
                        {iamAction === "reset" ? "Resetting..." : "Reset Password"}
                      </button>
                      <button
                        className="workflowAction"
                        disabled={!canConfigure || iamAction !== null || !selectedIamUserId}
                        onClick={handleAssignExistingUser}
                        type="button"
                      >
                        {iamAction === "assign" ? "Assigning..." : "Assign Existing User"}
                      </button>
                      <button
                        className="workflowAction danger"
                        disabled={!canConfigure || iamAction !== null || !selectedIamUserId}
                        onClick={handleDeactivateUser}
                        type="button"
                      >
                        {iamAction === "deactivate" ? "Deactivating..." : "Deactivate User"}
                      </button>
                    </div>
                  </form>

                  <div className="panel">
                    <div className="panelHeader compactHeader">
                      <h2>Project Team</h2>
                      <span>{dashboard.project_team.length} assigned</span>
                    </div>
                    <div className="workList compactList">
                      {dashboard.project_team.map((member) => (
                        <article key={member.membership.id}>
                          <strong>
                            {member.user.full_name} / {member.membership.role}
                          </strong>
                          <span>{member.user.email}</span>
                          <small>{member.user.title || "No title"}</small>
                          {canConfigure && (
                            <button
                              className="workflowAction danger"
                              disabled={iamAction !== null}
                              onClick={() => handleRemoveProjectAccess(member.user.id)}
                              type="button"
                            >
                              {iamAction === "remove" ? "Removing..." : "Remove Access"}
                            </button>
                          )}
                        </article>
                      ))}
                    </div>
                  </div>
                </div>

                <div className="panel wide">
                  <div className="panelHeader compactHeader">
                    <h2>Role Profiles</h2>
                    <span>{roles.length} profiles</span>
                  </div>
                  <table>
                    <thead>
                      <tr>
                        <th>Role</th>
                        <th>Description</th>
                        <th>Permissions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {roles.map((role) => (
                        <tr key={role.role}>
                          <td>
                            <strong>{role.role}</strong>
                          </td>
                          <td>{role.description}</td>
                          <td>
                            <div className="permissionStrip">
                              {role.can_capture_progress && <span>Progress</span>}
                              {role.can_capture_cost && <span>Cost</span>}
                              {role.can_approve_workflow && <span>Approve</span>}
                              {role.can_manage_contract && <span>Contract</span>}
                              {role.can_configure && <span>Admin</span>}
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </section>
        </section>
      </section>
    </main>
  );
}

function currency(value: number, code: string) {
  return new Intl.NumberFormat("en-US", {
    currency: code || "USD",
    maximumFractionDigits: 0,
    style: "currency",
  }).format(value || 0);
}

function currencyAxis(value: number, code: string) {
  return new Intl.NumberFormat("en-US", {
    currency: code || "USD",
    maximumFractionDigits: 1,
    notation: "compact",
    style: "currency",
  }).format(value || 0);
}

function dateAxis(value: number | string) {
  const timestamp = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(timestamp)) return "";
  return new Intl.DateTimeFormat("en-US", { day: "2-digit", month: "short" }).format(new Date(timestamp));
}

function tooltipDate(value: unknown) {
  const timestamp = typeof value === "number" || typeof value === "string" ? Number(value) : Number.NaN;
  if (!Number.isFinite(timestamp)) return "";
  return new Intl.DateTimeFormat("en-US", { day: "2-digit", month: "short", year: "numeric" }).format(
    new Date(timestamp)
  );
}

function statusLabel(value: string) {
  const neutralValue = value === "create_project_shell" ? "create_project" : value;
  return neutralValue
    ? neutralValue
        .split("_")
        .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
        .join(" ")
    : "Pending";
}

function sourceLabel(sourceKey: string) {
  return APU_SOURCE_OPTIONS.find((source) => source.key === sourceKey)?.label ?? sourceKey;
}

function buildApuCatalogStructure(items: ColombiaApuCatalogItem[]) {
  const sourceMap = new Map<
    string,
    {
      sourceKey: string;
      sourceLabel: string;
      totalItems: number;
      groups: Map<string, { groupName: string; totalItems: number; chapters: Map<string, number> }>;
    }
  >();
  for (const item of items) {
    const sourceKey = item.source_key || "unknown";
    if (!sourceMap.has(sourceKey)) {
      sourceMap.set(sourceKey, {
        sourceKey,
        sourceLabel: sourceLabel(sourceKey),
        totalItems: 0,
        groups: new Map(),
      });
    }
    const source = sourceMap.get(sourceKey);
    if (!source) continue;
    const groupName = item.group_name || "Grupo pendiente";
    const chapterName = item.chapter || "Capitulo pendiente";
    source.totalItems += 1;
    if (!source.groups.has(groupName)) {
      source.groups.set(groupName, { groupName, totalItems: 0, chapters: new Map() });
    }
    const group = source.groups.get(groupName);
    if (!group) continue;
    group.totalItems += 1;
    group.chapters.set(chapterName, (group.chapters.get(chapterName) ?? 0) + 1);
  }
  return Array.from(sourceMap.values()).map((source) => ({
    ...source,
    groups: Array.from(source.groups.values()).map((group) => ({
      ...group,
      chapters: Array.from(group.chapters.entries()).map(([chapterName, totalItems]) => ({ chapterName, totalItems })),
    })),
  }));
}

function apuStructureLines(item: ColombiaApuCatalogItem) {
  const rawStructure = Array.isArray(item.raw_data?.apu_structure) ? item.raw_data.apu_structure : [];
  const lines = rawStructure
    .map((rawLine) => {
      if (!rawLine || typeof rawLine !== "object") return null;
      const line = rawLine as Record<string, unknown>;
      return {
        component: String(line.component ?? "Costo directo"),
        description: String(line.description ?? item.item_name),
        quantity: Number(line.quantity ?? 1) || 1,
        unit: String(line.unit ?? item.unit),
        unitRate: Number(line.unit_rate ?? item.unit_rate) || 0,
        amount: Number(line.amount ?? item.unit_rate) || 0,
      };
    })
    .filter(
      (
        line
      ): line is {
        component: string;
        description: string;
        quantity: number;
        unit: string;
        unitRate: number;
        amount: number;
      } => Boolean(line)
    );
  return lines.length
    ? lines
    : [
        {
          amount: Number(item.unit_rate) || 0,
          component: "Costo directo",
          description: item.item_name,
          quantity: 1,
          unit: item.unit,
          unitRate: Number(item.unit_rate) || 0,
        },
      ];
}

function apuStructureNote(item: ColombiaApuCatalogItem) {
  const note = item.raw_data?.structure_note;
  return typeof note === "string" && note.trim()
    ? note
    : "Estructura minima visible: costo directo de referencia. Validar APU completo antes de aprobar.";
}

function processStatusTone(status: string) {
  if (status === "complete" || status === "ready") return "pass";
  if (status === "blocked") return "blocked";
  return "review";
}

function WbsTreeBranch({
  activityByCode,
  currencyCode,
  depth,
  node,
  project,
}: {
  activityByCode: Map<string, ActivitySheetWbsRow>;
  currencyCode: string;
  depth: number;
  node: WbsTreeNode;
  project: Project;
}) {
  const activityRollup = activityByCode.get(node.code);
  const display = wbsTreeDisplay(node, project, depth);
  return (
    <div className="wbsTreeBranch">
      <article
        aria-label={display.label}
        aria-level={depth + 1}
        className={depth <= 1 ? "wbsNodeCard root" : "wbsNodeCard"}
        role="treeitem"
      >
        <strong>{display.primary}</strong>
        <span>{display.secondary}</span>
        <small>{node.responsible || display.detail}</small>
        {activityRollup && (
          <em>
            {activityRollup.activity_count} act / {currency(activityRollup.planned_cost, currencyCode)}
          </em>
        )}
      </article>
      {node.children.length > 0 && (
        <div className="wbsChildren">
          {node.children.map((child) => (
            <WbsTreeBranch
              activityByCode={activityByCode}
              currencyCode={currencyCode}
              depth={depth + 1}
              key={child.id}
              node={child}
              project={project}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function AwpPackageTreeBranch({
  allPackages,
  constraintsByPackage,
  depth,
  node,
  wbsCatalog,
}: {
  allPackages: WorkPackage[];
  constraintsByPackage: Record<number, number>;
  depth: number;
  node: WorkPackageTreeNode;
  wbsCatalog: WbsNode[];
}) {
  const isWorkfacePackage = node.package_type.toUpperCase() === "IWP";
  const displayLabel = workPackageDisplayLabel(wbsCatalog, node);
  return (
    <div className="awpTreeBranch">
      <article
        aria-label={`${displayLabel} ${node.title}`}
        aria-level={depth + 1}
        className={constraintsByPackage[node.id] ? "awpTreeNode blockedPackage" : "awpTreeNode"}
        role="treeitem"
      >
        <strong>{displayLabel}</strong>
        <span>{node.title}</span>
        <small className="wbsTrace">WBS: {workPackageWbsName(wbsCatalog, node)}</small>
        <small>
          Seq {node.sequence_no || depth + 1} / {statusLabel(node.readiness_status)} /{" "}
          {constraintsByPackage[node.id] ?? 0} blockers
        </small>
        {isWorkfacePackage && <em>Workface release constraints: inherits Path of Construction from parent CWP.</em>}
      </article>
      {node.children.length > 0 && (
        <div className="awpTreeChildren" role="group">
          {node.children.map((child) => (
            <AwpPackageTreeBranch
              allPackages={allPackages}
              constraintsByPackage={constraintsByPackage}
              depth={depth + 1}
              key={child.id}
              node={child}
              wbsCatalog={wbsCatalog}
            />
          ))}
        </div>
      )}
    </div>
  );
}

function packageLabel(dashboard: Dashboard, packageId: number) {
  const workPackage = dashboard.work_packages.find((item) => item.id === packageId);
  return workPackage ? workPackage.code : `WP-${packageId}`;
}

function controlAccountLabel(dashboard: Dashboard, accountId: number | null) {
  if (!accountId) return "Area level";
  const account = dashboard.control_accounts.find((item) => item.id === accountId);
  return account ? account.name || account.code : `CA-${accountId}`;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/app" replace />} />
      <Route path="/login" element={<LoginView />} />
      <Route
        path="/app/*"
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      />
    </Routes>
  );
}
