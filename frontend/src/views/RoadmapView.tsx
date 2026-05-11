import { ClipboardCheck } from "lucide-react";
import type { AppShellCtx } from "../components/AppShellCtx";
import { statusLabel } from "../components/utils";

export default function RoadmapView({ ctx }: { ctx: AppShellCtx }) {
  const {
    activeView,
    dashboard,
    pilotReadiness,
    roadmapStatus,
    overallRoadmapScore,
    canConfigure,
    captureAction,
    controlPlanDraft,
    setControlPlanDraft,
    handleControlPlanSubmit,
  } = ctx;
  return (
    <section
      className={activeView === "roadmap" ? "viewPanel workspaceSection" : "viewPanel workspaceSection hidden"}
    >
      <div className="panelHeader">
        <h2>Roadmap Maturity Assessment</h2>
        <span>Estado global {overallRoadmapScore}%</span>
      </div>
      <div className="appAssessment">
        <article>
          <span>Calificacion actual</span>
          <strong>
            {pilotReadiness ? `${pilotReadiness.score.toFixed(1)}/100` : `${overallRoadmapScore}/100`}
          </strong>
          <small>
            {pilotReadiness
              ? statusLabel(pilotReadiness.status)
              : "Demo funcional avanzada, todavia no produccion empresarial."}
          </small>
        </article>
        <article>
          <span>TCM / Control Core</span>
          <strong>7/10</strong>
          <small>Flujo TCM, EVM, alertas, BP y trazabilidad ya estan conectados.</small>
        </article>
        <article>
          <span>Work Packages</span>
          <strong>4/10</strong>
          <small>CWA/CWP/EWP/PWP/IWP, readiness y constraints quedan integrados como MVP inicial.</small>
        </article>
        <article>
          <span>Produccion SaaS</span>
          <strong>3/10</strong>
          <small>Faltan auth real, migraciones, hardening, observabilidad y pruebas amplias.</small>
        </article>
      </div>
      {dashboard.control_plan && (
        <form className="adminPanel controlPlanPanel" onSubmit={handleControlPlanSubmit}>
          <div className="panelHeader">
            <h2>
              <ClipboardCheck size={18} /> Project Control Plan / PEP
            </h2>
            <span>
              {statusLabel(dashboard.control_plan.status)} / v{dashboard.control_plan.version}
            </span>
          </div>
          <div className="formColumns">
            <label>
              <span>Reporting Cadence</span>
              <input
                disabled={!canConfigure}
                onChange={(event) =>
                  setControlPlanDraft((current) => ({ ...current, reporting_cadence: event.target.value }))
                }
                value={controlPlanDraft.reporting_cadence}
              />
            </label>
            <label>
              <span>Status</span>
              <select
                disabled={!canConfigure}
                onChange={(event) =>
                  setControlPlanDraft((current) => ({ ...current, status: event.target.value }))
                }
                value={controlPlanDraft.status}
              >
                <option value="draft">Draft</option>
                <option value="in_review">In Review</option>
                <option value="approved">Approved</option>
                <option value="active">Active</option>
              </select>
            </label>
          </div>
          <label>
            <span>Execution Strategy</span>
            <textarea
              disabled={!canConfigure}
              onChange={(event) =>
                setControlPlanDraft((current) => ({ ...current, execution_strategy: event.target.value }))
              }
              rows={2}
              value={controlPlanDraft.execution_strategy}
            />
          </label>
          <label>
            <span>Control Strategy</span>
            <textarea
              disabled={!canConfigure}
              onChange={(event) =>
                setControlPlanDraft((current) => ({ ...current, control_strategy: event.target.value }))
              }
              rows={2}
              value={controlPlanDraft.control_strategy}
            />
          </label>
          <div className="formColumns">
            <label>
              <span>Progress Measurement</span>
              <textarea
                disabled={!canConfigure}
                onChange={(event) =>
                  setControlPlanDraft((current) => ({
                    ...current,
                    progress_measurement_rule: event.target.value,
                  }))
                }
                rows={3}
                value={controlPlanDraft.progress_measurement_rule}
              />
            </label>
            <label>
              <span>Cost Measurement</span>
              <textarea
                disabled={!canConfigure}
                onChange={(event) =>
                  setControlPlanDraft((current) => ({ ...current, cost_measurement_rule: event.target.value }))
                }
                rows={3}
                value={controlPlanDraft.cost_measurement_rule}
              />
            </label>
          </div>
          <div className="formColumns">
            <label>
              <span>Change Rules</span>
              <textarea
                disabled={!canConfigure}
                onChange={(event) =>
                  setControlPlanDraft((current) => ({ ...current, change_management_rule: event.target.value }))
                }
                rows={3}
                value={controlPlanDraft.change_management_rule}
              />
            </label>
            <label>
              <span>Risk Rules</span>
              <textarea
                disabled={!canConfigure}
                onChange={(event) =>
                  setControlPlanDraft((current) => ({ ...current, risk_management_rule: event.target.value }))
                }
                rows={3}
                value={controlPlanDraft.risk_management_rule}
              />
            </label>
          </div>
          <div className="formColumns">
            <label>
              <span>Procurement Strategy</span>
              <textarea
                disabled={!canConfigure}
                onChange={(event) =>
                  setControlPlanDraft((current) => ({ ...current, procurement_strategy: event.target.value }))
                }
                rows={3}
                value={controlPlanDraft.procurement_strategy}
              />
            </label>
            <label>
              <span>Document Control</span>
              <textarea
                disabled={!canConfigure}
                onChange={(event) =>
                  setControlPlanDraft((current) => ({ ...current, document_control_rule: event.target.value }))
                }
                rows={3}
                value={controlPlanDraft.document_control_rule}
              />
            </label>
          </div>
          <button
            className="workflowAction primary"
            disabled={!canConfigure || captureAction !== null}
            type="submit"
          >
            {captureAction === "control-plan" ? "Saving..." : "Save Control Plan"}
          </button>
        </form>
      )}
      {pilotReadiness && (
        <div className="roadmapGrid">
          {pilotReadiness.items.map((item) => (
            <article className="roadmapPhase" key={`${item.phase}-${item.area}`}>
              <div>
                <span>{item.phase}</span>
                <strong>{item.area}</strong>
              </div>
              <div className="scoreBar">
                <span style={{ width: `${item.score}%` }} />
              </div>
              <div className="phaseMeta">
                <strong>{item.score.toFixed(1)}%</strong>
                <span>{statusLabel(item.status)}</span>
              </div>
              <p>{item.finding}</p>
              <small>{item.next_action}</small>
            </article>
          ))}
        </div>
      )}
      <div className="roadmapGrid">
        {roadmapStatus.map((item) => (
          <article className="roadmapPhase" key={item.phase}>
            <div>
              <span>{item.phase}</span>
              <strong>{item.title}</strong>
            </div>
            <div className="scoreBar">
              <span style={{ width: `${item.score}%` }} />
            </div>
            <div className="phaseMeta">
              <strong>{item.score}%</strong>
              <span>{item.state}</span>
            </div>
            <p>{item.detail}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
