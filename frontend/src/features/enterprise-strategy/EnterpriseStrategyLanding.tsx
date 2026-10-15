import { ArrowRight, CheckCircle2, CircleAlert, GitMerge, Network, Split, Workflow } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { ApplicationMode, ControlFlowView } from "../../navigation/applicationNavigation";
import { capitalPlanningApi } from "../capital-planning/api";
import { enterpriseStructureApi } from "../enterprise-structure/api";
import { ideaDemandApi } from "../idea-demand/api";
import type { IdeaOptions } from "../idea-demand/types";
import {
  strategicBreadcrumb,
  strategicNavigationBlueprint,
  type StrategicNavigationNode,
} from "./navigation/strategicNavigationBlueprint";
import "./enterpriseStrategy.css";

type FoundationSnapshot = {
  structureAvailable: boolean;
  owningWorkspaces: number;
  strategicObjectives: number;
  ideaConfigurationAvailable: boolean;
  capitalPlanningConfigurationAvailable: boolean;
};

const EMPTY_SNAPSHOT: FoundationSnapshot = {
  structureAvailable: false,
  owningWorkspaces: 0,
  strategicObjectives: 0,
  ideaConfigurationAvailable: false,
  capitalPlanningConfigurationAvailable: false,
};

const explorerFilters = {
  search: "",
  workspace_type: "",
  business_unit_id: "",
  strategic_objective: "",
  region: "",
  status: "",
};

function configurationAvailable(options: IdeaOptions) {
  return Object.keys(options.configuration_source ?? {}).length > 0;
}

function FoundationCheck({ available, detail, label }: { available: boolean; detail: string; label: string }) {
  return (
    <li className={available ? "available" : "attention"}>
      {available ? <CheckCircle2 aria-hidden="true" size={17} /> : <CircleAlert aria-hidden="true" size={17} />}
      <span>
        <strong>{label}</strong>
        <small>{detail}</small>
      </span>
    </li>
  );
}

function PhaseCard({
  item,
  onNavigate,
}: {
  item: StrategicNavigationNode;
  onNavigate: (view: ControlFlowView) => void;
}) {
  return (
    <article className="strategicPhaseCard" data-phase={item.phase}>
      <header>
        <span>Phase {item.phase}</span>
        {item.badge ? <small>{item.badge}</small> : null}
      </header>
      <h3>{item.label}</h3>
      <p>{item.description}</p>
      <button onClick={() => onNavigate(item.children[0]?.view ?? item.view)} type="button">
        Open phase <ArrowRight aria-hidden="true" size={15} />
      </button>
    </article>
  );
}

function StrategicWorkflowMap({
  mode,
  onNavigate,
}: {
  mode: ApplicationMode;
  onNavigate: (view: ControlFlowView) => void;
}) {
  const phases = useMemo(
    () => strategicNavigationBlueprint.filter((item) => item.mode === mode && item.phase > 0),
    [mode]
  );
  const linear = phases.filter((item) => item.phase <= 4);
  const scenarios = phases.find((item) => item.phase === 5);
  const evidence = phases.find((item) => item.phase === 6);
  const governance = phases.find((item) => item.phase === 7);

  return (
    <section className="strategicWorkflowZone" aria-labelledby="strategic-workflow-title">
      <header className="strategicZoneHeading">
        <Workflow aria-hidden="true" size={21} />
        <div>
          <span>Strategic Workflow</span>
          <h2 id="strategic-workflow-title">Business sequence from Capital Demand to investment governance</h2>
        </div>
      </header>

      <div className="strategicLinearFlow">
        {linear.map((item) => (
          <PhaseCard item={item} key={item.id} onNavigate={onNavigate} />
        ))}
      </div>

      {scenarios ? (
        <section className="strategicRelationship" aria-label="Parallel Budget and Resource scenario branches">
          <header>
            <Split aria-hidden="true" size={19} />
            <div>
              <span>Phase 5</span>
              <h3>{scenarios.label}</h3>
              <p>{scenarios.description}</p>
            </div>
          </header>
          <div className="strategicParallelBranches">
            {scenarios.children.slice(0, 2).map((item) => (
              <button key={item.id} onClick={() => onNavigate(item.view)} type="button">
                <strong>{item.label}</strong>
                <span>Parallel input</span>
              </button>
            ))}
          </div>
          <div className="strategicConvergence">
            <GitMerge aria-hidden="true" size={17} />
            <button onClick={() => onNavigate(scenarios.children[2].view)} type="button">
              {scenarios.children[2].label}
            </button>
          </div>
          {scenarios.children
            .filter((item) => item.longitudinal)
            .map((item) => (
              <div className="strategicConvergence" key={item.id}>
                <button onClick={() => onNavigate(item.view)} type="button">
                  {item.label}
                </button>
              </div>
            ))}
        </section>
      ) : null}

      {evidence ? (
        <section className="strategicRelationship" aria-label="Investment evidence contributors">
          <header>
            <Network aria-hidden="true" size={19} />
            <div>
              <span>Phase 6</span>
              <h3>{evidence.label}</h3>
              <p>{evidence.description}</p>
            </div>
          </header>
          <div className="strategicEvidenceGrid">
            {evidence.children.map((item) => (
              <button key={item.id} onClick={() => onNavigate(item.view)} type="button">
                <strong>{item.label}</strong>
                <span>{item.longitudinal ? "Longitudinal evidence" : "Evidence contributor"}</span>
              </button>
            ))}
          </div>
          {governance ? (
            <div className="strategicConvergence gate">
              <GitMerge aria-hidden="true" size={17} />
              <button onClick={() => onNavigate(governance.children[mode === "admin" ? 1 : 0].view)} type="button">
                Converges into {governance.children[mode === "admin" ? 1 : 0].label}
              </button>
            </div>
          ) : null}
        </section>
      ) : null}

      {governance ? <PhaseCard item={governance} onNavigate={onNavigate} /> : null}
    </section>
  );
}

export function StrategicBreadcrumb({ mode, view }: { mode: ApplicationMode; view: ControlFlowView }) {
  const items = strategicBreadcrumb(view, mode);
  if (!items.length) return null;
  return (
    <nav aria-label="Strategic workflow breadcrumb" className="strategicBreadcrumb">
      {items.map((item, index) => (
        <span aria-current={index === items.length - 1 ? "page" : undefined} key={`${item}-${index}`}>
          {index > 0 ? <b aria-hidden="true">›</b> : null}
          {item}
        </span>
      ))}
    </nav>
  );
}

export default function EnterpriseStrategyLanding({
  mode,
  onNavigate,
  token,
}: {
  mode: ApplicationMode;
  onNavigate: (view: ControlFlowView) => void;
  token: string;
}) {
  const [snapshot, setSnapshot] = useState(EMPTY_SNAPSHOT);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    let active = true;
    Promise.all([
      enterpriseStructureApi.explorer(token, explorerFilters),
      ideaDemandApi.options(token),
      capitalPlanningApi.options(token),
    ])
      .then(([enterprise, ideaOptions, capitalPlanningOptions]) => {
        if (!active) return;
        const owningWorkspaces = ideaOptions.owning_workspaces.filter((item) =>
          ["ENTERPRISE", "BUSINESS_UNIT", "BUSINESS-UNIT", "PORTFOLIO"].includes(
            String(item.workspace_type_code ?? item.workspace_type ?? "").toUpperCase()
          )
        );
        setSnapshot({
          structureAvailable: Boolean(enterprise.published_release),
          owningWorkspaces: owningWorkspaces.length,
          strategicObjectives: ideaOptions.strategic_objectives.length,
          ideaConfigurationAvailable: configurationAvailable(ideaOptions),
          capitalPlanningConfigurationAvailable:
            Object.keys(capitalPlanningOptions.configuration_source ?? {}).length > 0,
        });
        setLoadError("");
      })
      .catch((caught: unknown) => {
        if (!active) return;
        setSnapshot(EMPTY_SNAPSHOT);
        setLoadError(caught instanceof Error ? caught.message : "Foundation signals are unavailable.");
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
    };
  }, [token]);

  const foundationReady =
    snapshot.structureAvailable &&
    snapshot.owningWorkspaces > 0 &&
    snapshot.strategicObjectives > 0 &&
    snapshot.ideaConfigurationAvailable &&
    snapshot.capitalPlanningConfigurationAvailable;

  return (
    <section aria-label="Enterprise Strategy Manager" className="enterpriseStrategyLanding">
      <header className="enterpriseStrategyHero">
        <div>
          <span>{mode === "admin" ? "ADMIN MODE" : "USER MODE"}</span>
          <h1>Enterprise Strategy Manager</h1>
          <p>
            Enterprise Foundation provides the prerequisite context. Capital Planning governs strategic needs before
            explicit Idea origination and the downstream investment workflow.
          </p>
        </div>
        <strong>{mode === "admin" ? "Configure and govern" : "Operate and consume"}</strong>
      </header>

      <section className="foundationZone" aria-labelledby="foundation-zone-title">
        <header className="strategicZoneHeading">
          <Network aria-hidden="true" size={21} />
          <div>
            <span>Phase 0 · Foundation / prerequisite</span>
            <h2 id="foundation-zone-title">Enterprise Foundation</h2>
          </div>
          <b className={foundationReady ? "ready" : "attention"}>
            {loading ? "CHECKING" : foundationReady ? "READY" : "ATTENTION REQUIRED"}
          </b>
        </header>
        <p>
          Enterprise Workspace Structure, eligible owning Workspaces, Strategic Objectives and published strategic
          configurations must exist before the backend can authorize governed capital needs and downstream Ideas.
        </p>
        <ul className="foundationChecks">
          <FoundationCheck
            available={snapshot.structureAvailable}
            detail={
              snapshot.structureAvailable
                ? "Published structure returned by the existing service"
                : "No published structure returned"
            }
            label="Enterprise Structure"
          />
          <FoundationCheck
            available={snapshot.owningWorkspaces > 0}
            detail={`${snapshot.owningWorkspaces} authorized ENTERPRISE, BUSINESS_UNIT or PORTFOLIO context(s)`}
            label="Eligible owning Workspaces"
          />
          <FoundationCheck
            available={snapshot.strategicObjectives > 0}
            detail={`${snapshot.strategicObjectives} objective(s) from the existing catalog`}
            label="Strategic Objectives"
          />
          <FoundationCheck
            available={snapshot.ideaConfigurationAvailable && snapshot.capitalPlanningConfigurationAvailable}
            detail={
              snapshot.ideaConfigurationAvailable && snapshot.capitalPlanningConfigurationAvailable
                ? "Capital Planning and Idea configuration sources returned"
                : "Capital Planning or Idea configuration source is unavailable"
            }
            label="Published strategic configuration"
          />
        </ul>
        {loadError ? (
          <p className="foundationLoadError" role="status">
            Existing foundation services could not be read. Transaction eligibility remains controlled by the backend.
          </p>
        ) : null}
        <div className="foundationActions">
          <button
            onClick={() => onNavigate(mode === "admin" ? "enterprise-structure-configuration" : "enterprise-explorer")}
            type="button"
          >
            {mode === "admin" ? "Open Foundation configuration" : "Open Enterprise Explorer"}
          </button>
          {mode === "user" ? (
            <button className="secondary" onClick={() => onNavigate("workspace-context")} type="button">
              Choose owning Workspace
            </button>
          ) : null}
          {mode === "user" && foundationReady ? (
            <button className="start" onClick={() => onNavigate("capital-demand-pipeline")} type="button">
              Start Capital Planning · Open Demand Pipeline
            </button>
          ) : null}
        </div>
      </section>

      <StrategicWorkflowMap mode={mode} onNavigate={onNavigate} />
    </section>
  );
}
