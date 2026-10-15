/* eslint-disable react-refresh/only-export-components --
 * The canonical strategic resolver and access guard are exported for focused tests.
 */
import type { ComponentType, ReactNode } from "react";
import AdminConfigurationView, { type AdminConfigurationViewKey } from "../../components/AdminConfigurationView";
import type { ApplicationMode, ControlFlowView } from "../../navigation/applicationNavigation";
import CapitalPlanningAdminView from "../capital-planning/CapitalPlanningAdminView";
import CapitalPlanningWorkspace from "../capital-planning/CapitalPlanningWorkspace";
import StrategicCapitalAllocationWorkspace from "../capital-allocation/StrategicCapitalAllocationWorkspace";
import BusinessAnalysisAdminView from "../business-analysis/BusinessAnalysisAdminView";
import BusinessAnalysisWorkspace from "../business-analysis/BusinessAnalysisWorkspace";
import BasicDataAdminView from "../basic-data/BasicDataAdminView";
import BasicDataWorkspace from "../basic-data/BasicDataWorkspace";
import OwnerCapabilityAdminView from "../owner-capability/OwnerCapabilityAdminView";
import OwnerCapabilityWorkspace from "../owner-capability/OwnerCapabilityWorkspace";
import QraFoundationAdminView from "../qra-foundation/QraFoundationAdminView";
import QraFoundationWorkspace from "../qra-foundation/QraFoundationWorkspace";
import QraEngineWorkspace from "../qra-engine/QraEngineWorkspace";
import BusinessCaseAdminView from "../business-case/BusinessCaseAdminView";
import BusinessCaseWorkspace from "../business-case/BusinessCaseWorkspace";
import CommercialStrategyAdminView from "../commercial-strategy/CommercialStrategyAdminView";
import CommercialStrategyWorkspace from "../commercial-strategy/CommercialStrategyWorkspace";
import EconomicFinancialModelAdminView from "../economic-financial-model/EconomicFinancialModelAdminView";
import EconomicFinancialModelWorkspace from "../economic-financial-model/EconomicFinancialModelWorkspace";
import AdminEnterpriseStructurePage from "../enterprise-structure/pages/AdminEnterpriseStructurePage";
import EnterpriseExplorerPage from "../enterprise-structure/pages/EnterpriseExplorerPage";
import FundsManagerAdminView from "../funds-manager/FundsManagerAdminView";
import FundsManagerWorkspace from "../funds-manager/FundsManagerWorkspace";
import IdeaDemandAdminView from "../idea-demand/IdeaDemandAdminView";
import IdeaLifecycleWorkspace from "../idea-demand/IdeaLifecycleWorkspace";
import InvestmentDecisionAdminView from "../investment-decision/InvestmentDecisionAdminView";
import InvestmentDecisionWorkspace from "../investment-decision/InvestmentDecisionWorkspace";
import InvestmentEvidencePolicyAdminView from "../investment-evidence-policy/InvestmentEvidencePolicyAdminView";
import InvestmentGatePreparationAdminView from "../investment-gate-preparation/InvestmentGatePreparationAdminView";
import InvestmentGatePreparationWorkspace from "../investment-gate-preparation/InvestmentGatePreparationWorkspace";
import PermitReadinessAdminView from "../permit-readiness/PermitReadinessAdminView";
import PermitReadinessWorkspace from "../permit-readiness/PermitReadinessWorkspace";
import PortfolioAnalysisAdminView from "../portfolio-analysis/PortfolioAnalysisAdminView";
import PortfolioAnalysisWorkspace from "../portfolio-analysis/PortfolioAnalysisWorkspace";
import PortfolioBudgetAdminView from "../portfolio-budget/PortfolioBudgetAdminView";
import PortfolioBudgetWorkspace from "../portfolio-budget/PortfolioBudgetWorkspace";
import PortfolioConvergenceAdminView from "../portfolio-convergence/PortfolioConvergenceAdminView";
import PortfolioConvergenceWorkspace from "../portfolio-convergence/PortfolioConvergenceWorkspace";
import PortfolioEvaluationAdminView from "../portfolio-evaluation/PortfolioEvaluationAdminView";
import PortfolioEvaluationWorkspace from "../portfolio-evaluation/PortfolioEvaluationWorkspace";
import PortfolioPlanningAdminView from "../portfolio-planning/PortfolioPlanningAdminView";
import PortfolioProjectsWorkspace from "../portfolio-planning/PortfolioProjectsWorkspace";
import StrategicPlanningEntryWorkspace from "../portfolio-planning/StrategicPlanningEntryWorkspace";
import PortfolioResourceAdminView from "../portfolio-resource/PortfolioResourceAdminView";
import PortfolioResourceWorkspace from "../portfolio-resource/PortfolioResourceWorkspace";
import PortfolioReviewAdminView from "../portfolio-review/PortfolioReviewAdminView";
import PortfolioReviewWorkspace from "../portfolio-review/PortfolioReviewWorkspace";
import PostFIDGovernanceAdminView from "../post-fid-governance/PostFIDGovernanceAdminView";
import PostFIDGovernanceWorkspace from "../post-fid-governance/PostFIDGovernanceWorkspace";
import ProjectDefinitionAdminView from "../project-definition/ProjectDefinitionAdminView";
import ProjectDefinitionWorkspace from "../project-definition/ProjectDefinitionWorkspace";
import ProjectProposalAdminView from "../project-proposal/ProjectProposalAdminView";
import ProjectProposalWorkspace from "../project-proposal/ProjectProposalWorkspace";
import RiskReadinessAdminView from "../risk-readiness/RiskReadinessAdminView";
import RiskReadinessWorkspace from "../risk-readiness/RiskReadinessWorkspace";
import RiskGovernanceAdminView from "../risk-governance/RiskGovernanceAdminView";
import StrategicGateAdminView from "../strategic-gate/StrategicGateAdminView";
import StrategicGateWorkspace from "../strategic-gate/StrategicGateWorkspace";
import StrategicBenefitsAdminView from "../strategic-benefits/StrategicBenefitsAdminView";
import StrategicBenefitsWorkspace from "../strategic-benefits/StrategicBenefitsWorkspace";
import MyWorkspacesPanel from "../workspace-context/MyWorkspacesPanel";
import EnterpriseStrategyLanding, { StrategicBreadcrumb } from "./EnterpriseStrategyLanding";
import { canAccessStrategicNode, strategicNodeForView } from "./navigation/strategicNavigationBlueprint";

type RendererProps = {
  canConfigure: boolean;
  mode: ApplicationMode;
  onNavigate: (view: ControlFlowView) => void;
  token: string;
  view: ControlFlowView;
};

type StrategicViewRenderer = (props: RendererProps) => ReactNode;

const tokenOnly =
  (Component: ComponentType<{ token: string }>): StrategicViewRenderer =>
  ({ token }) => <Component token={token} />;

const withInitialView =
  (Component: ComponentType<{ initialView?: string; token: string }>): StrategicViewRenderer =>
  ({ token, view }) => <Component initialView={view} token={token} />;

const strategicViewRenderers: Partial<Record<ControlFlowView, StrategicViewRenderer>> = {
  "enterprise-strategy-overview": ({ mode, onNavigate, token }) => (
    <EnterpriseStrategyLanding mode={mode} onNavigate={onNavigate} token={token} />
  ),
  "workspace-context": tokenOnly(MyWorkspacesPanel),
  "enterprise-explorer": tokenOnly(EnterpriseExplorerPage),
  "enterprise-structure-configuration": ({ canConfigure, token }) => (
    <AdminEnterpriseStructurePage canConfigure={canConfigure} token={token} />
  ),
  "foundation-strategic-objectives": ({ canConfigure, token }) => (
    <AdminEnterpriseStructurePage canConfigure={canConfigure} initialTab="catalogs" token={token} />
  ),
  "enterprise-workspace-structure": ({ canConfigure, token }) => (
    <AdminEnterpriseStructurePage
      canConfigure={canConfigure}
      initialTab="rules"
      key="composition-rules"
      token={token}
    />
  ),
  "capital-planning-cycles": ({ onNavigate, token, view }) => (
    <CapitalPlanningWorkspace initialView={view} onNavigate={onNavigate} token={token} />
  ),
  "capital-demand-pipeline": ({ onNavigate, token, view }) => (
    <CapitalPlanningWorkspace initialView={view} onNavigate={onNavigate} token={token} />
  ),
  "capital-demand-my": ({ onNavigate, token, view }) => (
    <CapitalPlanningWorkspace initialView={view} onNavigate={onNavigate} token={token} />
  ),
  "capital-demand-review": ({ onNavigate, token, view }) => (
    <CapitalPlanningWorkspace initialView={view} onNavigate={onNavigate} token={token} />
  ),
  "capital-demand-endorsed": ({ onNavigate, token, view }) => (
    <CapitalPlanningWorkspace initialView={view} onNavigate={onNavigate} token={token} />
  ),
  "capital-demand-history": ({ onNavigate, token, view }) => (
    <CapitalPlanningWorkspace initialView={view} onNavigate={onNavigate} token={token} />
  ),
  "capital-planning-configuration": tokenOnly(CapitalPlanningAdminView),
  "strategic-capital-allocation": withInitialView(StrategicCapitalAllocationWorkspace),
  "strategic-capital-allocation-history": withInitialView(StrategicCapitalAllocationWorkspace),
  "strategic-capital-bucket-configuration": ({ token }) => (
    <CapitalPlanningAdminView focus="buckets" initialSection="strategic_capital_buckets" token={token} />
  ),
  "idea-lifecycle": tokenOnly(IdeaLifecycleWorkspace),
  "idea-demand-configuration": tokenOnly(IdeaDemandAdminView),
  "business-analysis-options": tokenOnly(BusinessAnalysisWorkspace),
  "business-analysis-configuration": tokenOnly(BusinessAnalysisAdminView),
  "risk-governance-configuration": tokenOnly(RiskGovernanceAdminView),
  "basic-data-configuration": tokenOnly(BasicDataAdminView),
  "basic-data-readiness": tokenOnly(BasicDataWorkspace),
  "owner-capability-configuration": tokenOnly(OwnerCapabilityAdminView),
  "owner-capability-readiness": tokenOnly(OwnerCapabilityWorkspace),
  "qra-foundation": withInitialView(QraFoundationWorkspace),
  "qra-schedule-source-readiness": withInitialView(QraFoundationWorkspace),
  "qra-model-definition": withInitialView(QraFoundationWorkspace),
  "qra-foundation-history": withInitialView(QraFoundationWorkspace),
  "qra-approved-models": withInitialView(QraEngineWorkspace),
  "qra-runs": withInitialView(QraEngineWorkspace),
  "qra-run-overview": withInitialView(QraEngineWorkspace),
  "qra-cost-results": withInitialView(QraEngineWorkspace),
  "qra-schedule-results": withInitialView(QraEngineWorkspace),
  "qra-percentiles": withInitialView(QraEngineWorkspace),
  "qra-sensitivity": withInitialView(QraEngineWorkspace),
  "qra-convergence": withInitialView(QraEngineWorkspace),
  "qra-run-evidence": withInitialView(QraEngineWorkspace),
  "qra-run-comparison": withInitialView(QraEngineWorkspace),
  "qra-run-history": withInitialView(QraEngineWorkspace),
  "qra-methodology-source-readiness": tokenOnly(QraFoundationAdminView),
  "project-proposal": tokenOnly(ProjectProposalWorkspace),
  "project-proposal-configuration": tokenOnly(ProjectProposalAdminView),
  "strategic-gate-decision": tokenOnly(StrategicGateWorkspace),
  "strategic-gate-configuration": tokenOnly(StrategicGateAdminView),
  "strategic-project-planning-entry": tokenOnly(StrategicPlanningEntryWorkspace),
  "portfolio-projects": tokenOnly(PortfolioProjectsWorkspace),
  "portfolio-planning-configuration": tokenOnly(PortfolioPlanningAdminView),
  "portfolio-evaluation": tokenOnly(PortfolioEvaluationWorkspace),
  "strategic-prioritization-matrix": ({ token }) => (
    <PortfolioEvaluationWorkspace token={token} view="prioritization" />
  ),
  "portfolio-evaluation-configuration": tokenOnly(PortfolioEvaluationAdminView),
  "portfolio-analysis": tokenOnly(PortfolioAnalysisWorkspace),
  "portfolio-investor-map": ({ token }) => <PortfolioAnalysisWorkspace initialView="investor-map" token={token} />,
  "portfolio-scorecard": ({ token }) => <PortfolioAnalysisWorkspace initialView="scorecard" token={token} />,
  "portfolio-analysis-configuration": tokenOnly(PortfolioAnalysisAdminView),
  "portfolio-review-configuration": tokenOnly(PortfolioReviewAdminView),
  "portfolio-budget-planning": tokenOnly(PortfolioBudgetWorkspace),
  "portfolio-budget-planning-configuration": tokenOnly(PortfolioBudgetAdminView),
  "portfolio-resource-planning": tokenOnly(PortfolioResourceWorkspace),
  "portfolio-resource-planning-configuration": tokenOnly(PortfolioResourceAdminView),
  "portfolio-scenario-convergence": tokenOnly(PortfolioConvergenceWorkspace),
  "portfolio-scenario-convergence-configuration": tokenOnly(PortfolioConvergenceAdminView),
  "investment-gate-preparation": tokenOnly(InvestmentGatePreparationWorkspace),
  "investment-gate-preparation-configuration": tokenOnly(InvestmentGatePreparationAdminView),
  "investment-decision-evidence-policy": tokenOnly(InvestmentEvidencePolicyAdminView),
  "project-definition-fel": tokenOnly(ProjectDefinitionWorkspace),
  "project-definition-configuration": tokenOnly(ProjectDefinitionAdminView),
  "funds-manager-configuration": tokenOnly(FundsManagerAdminView),
  "risk-readiness-configuration": tokenOnly(RiskReadinessAdminView),
  "permit-readiness-configuration": tokenOnly(PermitReadinessAdminView),
  "investment-decision-configuration": tokenOnly(InvestmentDecisionAdminView),
  "post-fid-governance-configuration": tokenOnly(PostFIDGovernanceAdminView),
  "business-case-configuration": tokenOnly(BusinessCaseAdminView),
  "benefits-configuration": tokenOnly(StrategicBenefitsAdminView),
  "commercial-strategy-configuration": tokenOnly(CommercialStrategyAdminView),
  "financial-model-configuration": tokenOnly(EconomicFinancialModelAdminView),
};

const initialViewRenderers: Array<
  [readonly ControlFlowView[], ComponentType<{ initialView?: string; token: string }>]
> = [
  [
    [
      "portfolio-review-sessions",
      "portfolio-review-overview",
      "portfolio-review-snapshot",
      "portfolio-review-allocation",
      "portfolio-review-project-matrix",
      "portfolio-review-budget-resources",
      "portfolio-review-gate-fid",
      "portfolio-review-exceptions",
      "portfolio-review-conclusions",
      "portfolio-review-actions",
      "portfolio-review-history",
      "portfolio-review-trends",
    ],
    PortfolioReviewWorkspace,
  ],
  [
    [
      "strategic-benefits-my",
      "strategic-benefits-overview",
      "strategic-benefits-strategic-alignment",
      "strategic-benefits-outputs",
      "strategic-benefits-outcomes",
      "strategic-benefits-register",
      "strategic-benefits-measures",
      "strategic-benefits-owners",
      "strategic-benefits-baselines-targets",
      "strategic-benefits-expected-value",
      "strategic-benefits-dependencies",
      "strategic-benefits-assumptions-constraints",
      "strategic-benefits-risk-references",
      "strategic-benefits-traceability",
      "strategic-benefits-readiness",
      "strategic-benefits-history",
    ],
    StrategicBenefitsWorkspace,
  ],
  [
    [
      "commercial-strategy-my",
      "commercial-strategy-overview",
      "commercial-strategy-context",
      "commercial-strategy-procurement",
      "commercial-strategy-packages",
      "commercial-strategy-contracting-model",
      "commercial-strategy-market",
      "commercial-strategy-supply-chain",
      "commercial-strategy-risk-allocation",
      "commercial-strategy-payment-incentives",
      "commercial-strategy-assumptions",
      "commercial-strategy-recommendation",
      "commercial-strategy-readiness",
      "commercial-strategy-history",
    ],
    CommercialStrategyWorkspace,
  ],
  [
    [
      "funds-overview",
      "funds-sources",
      "funds-envelopes",
      "funds-assignments",
      "funds-coverage",
      "funds-readiness",
      "funds-history",
    ],
    FundsManagerWorkspace,
  ],
  [
    [
      "risk-readiness-my",
      "risk-readiness-portfolio",
      "risk-readiness-register",
      "risk-readiness-assessments",
      "risk-readiness-treatments",
      "risk-readiness-residual",
      "risk-readiness-dashboard",
      "risk-readiness-history",
    ],
    RiskReadinessWorkspace,
  ],
  [
    [
      "permit-readiness-my",
      "permit-readiness-register",
      "permit-readiness-requirements",
      "permit-readiness-conditions",
      "permit-readiness-project",
      "permit-readiness-portfolio",
      "permit-readiness-history",
    ],
    PermitReadinessWorkspace,
  ],
  [
    [
      "investment-decision-queue",
      "investment-decision-mine",
      "investment-decision-package",
      "investment-decision-evidence",
      "investment-decision-checklist",
      "investment-decision-conditions",
      "investment-decision-committee",
      "investment-decision-history",
      "investment-decision-output",
    ],
    InvestmentDecisionWorkspace,
  ],
  [
    [
      "post-fid-queue",
      "post-fid-handoff",
      "post-fid-eligibility-matrix",
      "post-fid-conditions",
      "post-fid-initialization-handoff",
      "post-fid-activation-handoff",
      "post-fid-history",
    ],
    PostFIDGovernanceWorkspace,
  ],
  [
    [
      "business-case-my",
      "business-case-overview",
      "business-case-economic",
      "business-case-commercial",
      "business-case-management",
      "business-case-sources-evidence",
      "business-case-current-revision",
      "business-case-strategic",
      "business-case-alternatives",
      "business-case-benefits",
      "business-case-project-definition",
      "business-case-financial",
      "business-case-budget-resources",
      "business-case-funding",
      "business-case-risk-permits",
      "business-case-execution",
      "business-case-assumptions",
      "business-case-recommendation",
      "business-case-readiness",
      "business-case-material-changes",
      "business-case-decision-snapshots",
      "business-case-history",
    ],
    BusinessCaseWorkspace,
  ],
];

for (const [views, Component] of initialViewRenderers) {
  for (const view of views) strategicViewRenderers[view] = withInitialView(Component);
}

// Business Case source links stay inside the canonical strategic navigator. The
// legacy deep-link views remain registered above and are rendered through the
// compact Five Case workspace without expanding App.tsx.
for (const view of [
  "business-case-my",
  "business-case-overview",
  "business-case-economic",
  "business-case-commercial",
  "business-case-management",
  "business-case-sources-evidence",
  "business-case-current-revision",
  "business-case-strategic",
  "business-case-alternatives",
  "business-case-benefits",
  "business-case-project-definition",
  "business-case-financial",
  "business-case-budget-resources",
  "business-case-funding",
  "business-case-risk-permits",
  "business-case-execution",
  "business-case-assumptions",
  "business-case-recommendation",
  "business-case-readiness",
  "business-case-material-changes",
  "business-case-decision-snapshots",
  "business-case-history",
] as const satisfies readonly ControlFlowView[]) {
  strategicViewRenderers[view] = ({ onNavigate, token, view: initialView }) => (
    <BusinessCaseWorkspace initialView={initialView} onNavigate={onNavigate} token={token} />
  );
}

const financialViews = [
  "financial-model-my-models",
  "financial-model-overview",
  "financial-model-current-version",
  "financial-model-assumptions",
  "financial-model-economic-case",
  "financial-model-financial-case",
  "financial-model-capex-opex",
  "financial-model-revenue-benefits",
  "financial-model-capital-structure",
  "financial-model-funding-linkage",
  "financial-model-investors",
  "financial-model-debt",
  "financial-model-cash-flow",
  "financial-model-debt-service",
  "financial-model-indicators",
  "financial-model-covenants",
  "financial-model-scenarios",
  "financial-model-sensitivities",
  "financial-model-break-even",
  "financial-model-readiness",
  "financial-model-source-lineage",
  "financial-model-compare-versions",
  "financial-model-history-audit",
] as const satisfies readonly ControlFlowView[];

for (const view of financialViews) strategicViewRenderers[view] = withInitialView(EconomicFinancialModelWorkspace);

const genericAdminViews = [
  "workspace-types",
  "workspace-defaults",
  "module-catalog-activation",
  "workspace-navigation-profiles",
] as const satisfies readonly AdminConfigurationViewKey[];

for (const view of genericAdminViews) {
  strategicViewRenderers[view] = ({ canConfigure, token }) => (
    <AdminConfigurationView canConfigure={canConfigure} key={view} token={token} view={view} />
  );
}

export const STRATEGIC_VIEW_RENDERERS = strategicViewRenderers;

export default function StrategicViewOutlet(props: RendererProps) {
  const match = strategicNodeForView(props.view, props.mode);
  const renderer = strategicViewRenderers[props.view];
  if (!match || !renderer) return null;

  const { node } = match;
  if (!canAccessStrategicNode(node, { authenticated: Boolean(props.token), canConfigure: props.canConfigure })) {
    return (
      <section
        aria-label="Strategic configuration access denied"
        className="emptySubmoduleScreen"
        data-control-classification={node.classification}
        role="alert"
      >
        <h2>Configuration access required</h2>
        <p>This ADMIN configuration route requires the existing can_configure permission.</p>
      </section>
    );
  }

  return (
    <div
      data-control-classification={node.classification}
      data-strategic-mode={node.mode}
      data-strategic-view={node.view}
    >
      <StrategicBreadcrumb mode={props.mode} view={props.view} />
      {renderer(props)}
    </div>
  );
}
