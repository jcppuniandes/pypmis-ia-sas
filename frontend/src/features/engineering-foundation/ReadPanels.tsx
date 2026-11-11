import { useState } from "react";
import { Link } from "react-router-dom";
import { engineeringQuery, isEngineeringRow, items, labelOf, recordId, rows, text } from "./api";
import { DateFilters, Evidence, Facts, Options, ReadState, ReasonCodes, Records, Select } from "./controls";
import { useEngineeringData } from "./hooks";
import { profileContent } from "./profile";
import type { EngineeringPanel, EngineeringScope } from "./types";

export function ReadinessPanel({ scope, workspaceId }: { scope: EngineeringScope; workspaceId: number }) {
  const [kind, setKind] = useState("EWP");
  const [packageId, setPackageId] = useState("");
  const [asOf, setAsOf] = useState("");
  const packages = useEngineeringData(
    scope.token,
    scope.base,
    engineeringQuery("/mapping-targets", { target_kind: kind }),
    scope.refreshKey
  );
  const current = useEngineeringData(
    scope.token,
    scope.base,
    packageId ? engineeringQuery("/readiness", { work_package_id: packageId, as_of: asOf }) : null,
    scope.refreshKey
  );
  const evidence = current.value;
  const coverage = isEngineeringRow(evidence?.coverage) ? evidence.coverage : null;
  return (
    <section className="progressPanel" aria-label="Engineering Readiness">
      <h3>Engineering Readiness</h3>
      <p>
        La evidencia de Ingeniería es una fuente. AWP evalúa la preparación, decide el cierre de restricciones y libera
        el paquete mediante comandos independientes. READY ≠ RELEASED.
      </p>
      <div className="progressForm">
        <Select
          label="Tipo de paquete para Readiness"
          value={kind}
          onChange={(value) => {
            setKind(value);
            setPackageId("");
          }}
          values={["EWP", "CWP", "IWP"]}
          required
        />
        <Options
          label="Paquete para Engineering Readiness"
          value={packageId}
          onChange={setPackageId}
          records={items(packages.value)}
          render={(row) => `${labelOf(row)} · ${recordId(row)}`}
        />
      </div>
      <DateFilters asOf={asOf} setAsOf={setAsOf} />
      <ReadState {...packages} reload={scope.reload} />
      <ReadState {...current} reload={scope.reload} />
      {evidence ? (
        <>
          <Facts
            values={[
              ["Proveedor", evidence.provider_key],
              ["Elegibilidad de evidencia", evidence.status],
              ["Corte", evidence.as_of],
              ["Entregables requeridos", coverage?.required],
              ["Entregables cubiertos", coverage?.covered],
              ["Hash de evidencia", evidence.evidence_hash],
              ["Referencia de evidencia", evidence.evidence_reference],
            ]}
          />
          <ReasonCodes codes={evidence.reason_codes} />
          <Records
            label="Evidencia Engineering"
            items={rows(evidence.sources)}
            columns={[
              ["deliverable_id", "Entregable"],
              ["revision_id", "Revisión"],
              ["status", "Elegibilidad"],
              ["effective_date", "Vigencia desde"],
              ["document_hash", "Hash documento"],
              ["release_hash", "Hash liberación"],
            ]}
          />
          <Evidence title="Fuente y criterios de evidencia" value={evidence} />
        </>
      ) : packageId ? null : (
        <p>Seleccione el paquete AWP a evaluar.</p>
      )}
      <Link to={`/workspaces/${workspaceId}/awp`}>Consultar evaluación y restricciones en AWP</Link>
    </section>
  );
}

export function ProgressPanel(scope: EngineeringScope) {
  const [asOf, setAsOf] = useState("");
  const [dimension, setDimension] = useState("");
  const status = useEngineeringData(
    scope.token,
    scope.base,
    engineeringQuery("/status", { as_of: asOf, group_by: dimension }),
    scope.refreshKey
  );
  const sources = useEngineeringData(
    scope.token,
    scope.base,
    engineeringQuery("/source-facts", { as_of: asOf }),
    scope.refreshKey
  );
  const metrics = isEngineeringRow(status.value?.project) ? status.value.project : {};
  const progress = isEngineeringRow(sources.value?.progress) ? sources.value.progress : null;
  const forecast = isEngineeringRow(sources.value?.forecast) ? sources.value.forecast : null;
  const cost = isEngineeringRow(sources.value?.cost) ? sources.value.cost : null;
  return (
    <>
      <section className="progressPanel" aria-label="Engineering Progress">
        <h3>Engineering Progress</h3>
        <p>
          Estados técnicos derivados del registro. Progress conserva la autoridad sobre mediciones, reglas de crédito y
          avance. La tardanza de un entregable no prueba por sí sola un retraso CPM.
        </p>
        <DateFilters asOf={asOf} setAsOf={setAsOf} />
        <Options
          label="Agrupar estado Engineering por"
          value={dimension}
          onChange={setDimension}
          valueKey="code"
          records={[
            { code: "project", label: "Project" },
            { code: "discipline", label: "Disciplina" },
            { code: "area", label: "Área" },
            { code: "cwa", label: "CWA" },
            { code: "ewp", label: "EWP" },
          ]}
          render={(row) => text(row.label)}
        />
        <ReadState {...status} reload={scope.reload} />
        {status.value ? (
          <>
            <Facts
              values={[
                ["Total de entregables", metrics.total_deliverables ?? metrics.total],
                ["Planeados", metrics.planned],
                ["Enviados", metrics.submitted],
                ["En revisión", metrics.under_review],
                ["Aprobados", metrics.approved],
                ["Liberados IFC", metrics.ifc_released],
                ["Vencidos", metrics.overdue],
                ["Pronóstico tardío", metrics.forecast_late],
                ["Sustituidos", metrics.superseded],
              ]}
            />
            <Records
              label="Estado por agrupación"
              items={rows(status.value.groups)}
              columns={[
                ["dimension", "Dimensión"],
                ["key", "Grupo"],
                ["total_deliverables", "Total"],
                ["under_review", "En revisión"],
                ["approved", "Aprobados"],
                ["ifc_released", "Liberados IFC"],
                ["overdue", "Vencidos"],
              ]}
            />
            <Evidence title="Fuentes de la vista de estado" value={status.value} />
          </>
        ) : null}
      </section>
      <section className="progressPanel" aria-label="Fuentes para otros controles">
        <h3>Evidencia para otros controles</h3>
        <p>
          Engineering publica hechos técnicos. No reconoce Actual Cost, no aprueba mediciones y no reescribe un
          Forecast.
        </p>
        <ReadState {...sources} reload={scope.reload} />
        {progress ? (
          <Facts
            values={[
              ["Autoridad de avance", progress.authority],
              ["Método de evidencia configurado", progress.engineering_default_method],
              ["Eventos candidatos", rows(progress.items).length],
            ]}
          />
        ) : null}
        {progress ? <Evidence title="Eventos de Ingeniería para Progress" value={progress.items} /> : null}
        {forecast ? <Evidence title="Hechos candidatos para Forecast" value={forecast.items} /> : null}
        {cost ? <Evidence title="Referencias dimensionales para Cost" value={cost.items} /> : null}
      </section>
    </>
  );
}

export function LookAheadPanel(scope: EngineeringPanel) {
  const [asOf, setAsOf] = useState("");
  const [horizon, setHorizon] = useState("");
  const defaultDays = text(profileContent(scope.config).lookahead_days) || "28";
  const allowedDays = [...new Set(["7", "14", "21", "28", "42", "56", "90", "120", defaultDays])].sort(
    (a, b) => Number(a) - Number(b)
  );
  const lookahead = useEngineeringData(
    scope.token,
    scope.base,
    engineeringQuery("/lookahead", { as_of: asOf, horizon_days: horizon }),
    scope.refreshKey
  );
  return (
    <section className="progressPanel" aria-label="Engineering Look-Ahead">
      <h3>Engineering Look-Ahead</h3>
      <p>
        Ventana técnica basada en fechas de Ingeniería y referencias al Schedule aceptado. El visor no calcula ni cambia
        el CPM.
      </p>
      <DateFilters
        asOf={asOf}
        setAsOf={setAsOf}
        horizon={horizon || defaultDays}
        setHorizon={setHorizon}
        horizonOptions={allowedDays}
      />
      <ReadState {...lookahead} reload={scope.reload} />
      {lookahead.value ? (
        <>
          <Facts
            values={[
              ["Fecha de corte", lookahead.value.as_of],
              ["Fin de ventana", lookahead.value.through],
              ["Días", lookahead.value.horizon_days],
            ]}
          />
          <Records
            label="Engineering Look-Ahead"
            items={items(lookahead.value)}
            columns={[
              ["deliverable_code", "Código"],
              ["title", "Entregable"],
              ["planned_issue_date", "Emisión planificada"],
              ["forecast_issue_date", "Emisión prevista"],
              ["ifc_release_due", "IFC requerido"],
              ["overdue", "Vencido"],
              ["mappings", "Referencias"],
              ["readiness_impact", "Impacto de preparación"],
            ]}
            format={(key, value) =>
              key === "mappings"
                ? rows(value)
                    .map((item) => `${text(item.target_kind)} · ${text(item.external_id ?? item.target_id)}`)
                    .join(", ") || "—"
                : typeof value === "boolean"
                  ? value
                    ? "Sí"
                    : "No"
                  : text(value) || "—"
            }
          />
          <Evidence title="Trazabilidad de Look-Ahead" value={lookahead.value.items} />
        </>
      ) : null}
    </section>
  );
}

export function HistoryPanel(scope: EngineeringPanel) {
  const [cursor, setCursor] = useState("");
  const [selectedEvent, setSelectedEvent] = useState("");
  const history = useEngineeringData(
    scope.token,
    scope.base,
    engineeringQuery("/history", { after_id: cursor, limit: 50 }),
    scope.refreshKey
  );
  const events = items(history.value);
  const event = events.find((row) => recordId(row) === selectedEvent);
  return (
    <section className="progressPanel" aria-label="History">
      <h3>History</h3>
      <p>Registro de decisiones y fuentes congeladas. Leer historial no crea hechos de negocio.</p>
      <ReadState {...history} reload={scope.reload} />
      {history.value ? (
        <>
          <Records
            label="Historial Engineering"
            items={events}
            columns={[
              ["event_type", "Evento"],
              ["entity_type", "Entidad"],
              ["entity_id", "Identidad"],
              ["entity_version", "Versión"],
              ["created_by", "Actor"],
              ["created_at", "Fecha"],
              ["reason", "Motivo"],
            ]}
            select={(row) => setSelectedEvent(recordId(row))}
          />
          {event ? <Evidence title="Detalle del evento seleccionado" value={event} /> : null}
        </>
      ) : null}
      {cursor || text(history.value?.next_cursor) ? (
        <div className="progressActions">
          {cursor ? (
            <button type="button" onClick={() => setCursor("")}>
              Primera página
            </button>
          ) : null}
          {text(history.value?.next_cursor) ? (
            <button type="button" onClick={() => setCursor(text(history.value?.next_cursor))}>
              Siguiente página
            </button>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
