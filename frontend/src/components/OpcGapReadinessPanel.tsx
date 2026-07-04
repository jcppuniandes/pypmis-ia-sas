import { CheckCircle2, CircleAlert, GitBranch, Radar } from "lucide-react";
import type { OpcGapAnalysis, OpcGapStatus } from "../lib/opcGap";

type OpcGapReadinessPanelProps = {
  analysis: OpcGapAnalysis;
};

function statusLabel(status: OpcGapStatus) {
  if (status === "ready") return "Ready";
  if (status === "partial") return "Partial";
  return "Gap";
}

function statusIcon(status: OpcGapStatus) {
  if (status === "ready") return <CheckCircle2 size={16} />;
  return <CircleAlert size={16} />;
}

export default function OpcGapReadinessPanel({ analysis }: OpcGapReadinessPanelProps) {
  return (
    <section aria-label="Diagnóstico de Control" className="opcGapPanel workspaceSection">
      <div className="panelHeader compactHeader">
        <div>
          <h2>
            <Radar size={20} /> Diagnóstico de Control
          </h2>
          <span>Lectura de madurez del flujo de planificación, BIM, costos, EVM y AWP</span>
        </div>
        <strong>{analysis.readinessScore}%</strong>
      </div>

      <div className="opcGapSummary">
        <article className={`opcGapScore ${analysis.overallStatus}`}>
          <span>Readiness</span>
          <strong>{analysis.readinessScore}%</strong>
          <small>{statusLabel(analysis.overallStatus)} / {analysis.criticalGapCount} critical gap(s)</small>
        </article>
        <article>
          <span>Posición del producto</span>
          <strong>BIM + APU + AWP como columna de control</strong>
          <small>Conecta cantidades IFC con APU Colombia, presupuesto, WBS/CBS/FBS y paquetes controlables.</small>
        </article>
        <article>
          <span>Regla de ejecución</span>
          <strong>Seguir la columna de datos</strong>
          <small>No liberar EVM ni paquetes AWP sin la evidencia previa lista.</small>
        </article>
      </div>

      <section aria-label="Columna de datos de control" className="opcDataSpine">
        <div className="panelHeader compactHeader">
          <h3>
            <GitBranch size={18} /> Columna de datos de control
          </h3>
          <span>{analysis.spine.length} pasos enlazados</span>
        </div>
        <div className="opcDataSpineTrack">
          {analysis.spine.map((step, index) => (
            <article className={`opcSpineStep ${step.status}`} key={step.id}>
              <em>{index + 1}</em>
              <strong>{step.label}</strong>
              <span>{step.evidence}</span>
              <small>{step.detail}</small>
            </article>
          ))}
        </div>
      </section>

      <section aria-label="Registro de brechas" className="opcGapRegister">
        <div className="panelHeader compactHeader">
          <h3>Registro de brechas</h3>
          <span>{analysis.gaps.length} area(s) de capacidad</span>
        </div>
        <table>
          <thead>
            <tr>
              <th>Capacidad de control</th>
              <th>Status</th>
              <th>Evidencia en la app</th>
              <th>Siguiente acción</th>
            </tr>
          </thead>
          <tbody>
            {analysis.gaps.map((gap) => (
              <tr key={gap.id}>
                <td>
                  <strong>{gap.title}</strong>
                  <span>{gap.controlReference}</span>
                </td>
                <td>
                  <span className={`opcGapStatus ${gap.status}`}>
                    {statusIcon(gap.status)} {gap.priority} / {statusLabel(gap.status)}
                  </span>
                </td>
                <td>{gap.appEvidence}</td>
                <td>{gap.nextAction}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section aria-label="Acciones controladas" className="opcNextActions">
        <div className="panelHeader compactHeader">
          <h3>Acciones controladas</h3>
          <span>{analysis.nextActions.length || 0} acción(es)</span>
        </div>
        {analysis.nextActions.length ? (
          <ol>
            {analysis.nextActions.map((action) => (
              <li key={action}>{action}</li>
            ))}
          </ol>
        ) : (
          <p>No hay acciones criticas abiertas para la evidencia actual.</p>
        )}
      </section>
    </section>
  );
}
