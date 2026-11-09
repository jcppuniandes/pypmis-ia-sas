import { useCallback, useState, type FormEvent } from "react";
import { parameters } from "./api";
import { Evidence, Facts, Field, Input, ReasonCodes, Records, Select } from "./Fields";
import { useForecastQuery } from "./useForecastQuery";
import { Narratives } from "./ReadPanels";
import { object, revision, rows, text, type ForecastPanelProps, type ForecastRecord } from "./types";

export function LookAheadPanel(props: ForecastPanelProps) {
  const policy = object(object(props.data.configuration?.content_json).lookahead);
  const threshold = object(policy.near_critical_threshold);
  const [horizon, setHorizon] = useState(text(policy, "default_horizon_days", "28"));
  const [groupBy, setGroupBy] = useState(text(policy, "group_by", "PARENT_WBS"));
  const [topN, setTopN] = useState("");
  const [criticalOnly, setCriticalOnly] = useState(false);
  const [thresholdValue, setThresholdValue] = useState(text(threshold, "value", "40"));
  const [thresholdUnit, setThresholdUnit] = useState(text(threshold, "unit", "HOUR"));
  const [wbs, setWbs] = useState("");
  const [packageId, setPackageId] = useState("");
  const [excludeMilestones, setExcludeMilestones] = useState(policy.exclude_milestones !== false);
  const [request, setRequest] = useState<{ forecastId: number; path: string } | null>(null);
  const [saved, setSaved] = useState("");
  const baseQuery = props.query;
  const query = useCallback((value: string) => baseQuery(value, "performance"), [baseQuery]);
  const path = request?.forecastId === props.selected?.id ? (request?.path ?? null) : null;
  const result = useForecastQuery(path, query, props.selected);
  function run(event: FormEvent) {
    event.preventDefault();
    if (!props.selected) return;
    setSaved("");
    const next = `/lookahead?${parameters({
      forecast_version_id: props.selected.id,
      period_id: props.periodId,
      as_of: props.asOf,
      horizon_days: horizon,
      group_by: groupBy,
      top_n: topN,
      critical_only: String(criticalOnly),
      near_critical_value: thresholdValue,
      near_critical_unit: thresholdUnit,
      wbs_external_id: wbs,
      work_package_id: packageId,
      exclude_milestones: String(excludeMilestones),
    })}`;
    if (next === path) result.reload();
    else setRequest({ forecastId: props.selected.id, path: next });
  }
  async function saveSnapshot() {
    if (!props.selected) return;
    const snapshot = await props.command(
      "/lookahead/snapshots",
      {
        forecast_version_id: props.selected.id,
        horizon_days: Number(horizon),
        group_by: groupBy,
        top_n: topN ? Number(topN) : null,
        critical_only: criticalOnly,
        near_critical_value: thresholdValue,
        near_critical_unit: thresholdUnit,
        wbs_external_id: wbs || null,
        work_package_id: packageId ? Number(packageId) : null,
        exclude_milestones: excludeMilestones,
        reason: props.reason,
      },
      undefined,
      "POST",
      "performance"
    );
    setSaved(`Snapshot Look-Ahead ${text(snapshot, "id")} guardado sin modificar Schedule.`);
  }
  const value = result.result;
  const activities = rows(value?.items).map((row) => ({
    ...row,
    activity_external_id: row.activity_external_id ?? row.external_id,
    current_finish: row.current_finish ?? row.finish,
    driving_state: object(row.driving_predecessor).state,
  }));
  const relationships = [...rows(value?.items), ...rows(value?.milestones)].flatMap((row) =>
    rows(object(row.driving_predecessor).predecessors).map((relation) => ({
      successor_external_id: row.activity_external_id ?? row.external_id,
      ...relation,
    }))
  );
  return (
    <section className="progressPanel" aria-label="4-Week Look-Ahead">
      <h3>4-Week Look-Ahead</h3>
      <p>
        Horizonte por defecto de cuatro semanas, configurable por política. Schedule mantiene fechas, float y
        criticality importados de P6. Un predecesor conductor no demostrable se muestra UNKNOWN.
      </p>
      <form className="progressForm" onSubmit={run}>
        <Field label="Look-Ahead Horizon days">
          <input
            aria-label="Look-Ahead Horizon days"
            type="number"
            min="1"
            max={text(policy, "maximum_horizon_days", "366")}
            required
            value={horizon}
            onChange={(event) => setHorizon(event.target.value)}
          />
        </Field>
        <Select
          label="Look-Ahead Group by"
          value={groupBy}
          onChange={setGroupBy}
          values={["PARENT_WBS", "CWA", "PACKAGE", "AREA", "ZONE", "SYSTEM", "DISCIPLINE"]}
          required
        />
        <Field label="Look-Ahead Top N">
          <input
            aria-label="Look-Ahead Top N"
            type="number"
            min="1"
            value={topN}
            onChange={(event) => setTopN(event.target.value)}
          />
        </Field>
        <Input
          label="Look-Ahead Near-critical value"
          type="number"
          value={thresholdValue}
          onChange={setThresholdValue}
          required
        />
        <Select
          label="Look-Ahead Float unit"
          value={thresholdUnit}
          onChange={setThresholdUnit}
          values={["HOUR", "DAY"]}
          required
        />
        <Input label="Look-Ahead WBS external ID" value={wbs} onChange={setWbs} />
        <Select
          label="Look-Ahead Work Package"
          value={packageId}
          onChange={setPackageId}
          options={props.data.packages}
        />
        <label className="progressCheck">
          <input
            aria-label="Look-Ahead Critical only"
            type="checkbox"
            checked={criticalOnly}
            onChange={(event) => setCriticalOnly(event.target.checked)}
          />
          Solo críticas
        </label>
        <label className="progressCheck">
          <input
            aria-label="Look-Ahead Separate milestones"
            type="checkbox"
            checked={excludeMilestones}
            onChange={(event) => setExcludeMilestones(event.target.checked)}
          />
          Separar hitos puros de la lista detallada
        </label>
        <button type="submit" disabled={props.busy || !props.selected || !props.can("lookahead.view")}>
          Ejecutar Look-Ahead
        </button>
      </form>
      <p>
        Sin Top N se conserva el trabajo relevante, incluido el bloqueado. No se convierten horas a días ni se recalcula
        una ruta conductora en la UI.
      </p>
      {result.error ? (
        <p className="progressError" role="alert">
          {result.error}
        </p>
      ) : null}
      {value ? (
        <>
          {saved ? (
            <p role="status" className="progressNotice">
              {saved}
            </p>
          ) : null}
          {props.can("lookahead.generate") ? (
            <button
              type="button"
              disabled={props.busy || !props.selected || props.reason.trim().length < 8}
              onClick={() => void saveSnapshot().catch(() => undefined)}
            >
              Guardar snapshot Look-Ahead
            </button>
          ) : null}
          <Facts
            values={[
              ["Resultado", value.status],
              ["Horizonte días", value.horizon_days],
              ["As-of", value.as_of],
              ["Agrupación", groupBy],
            ]}
          />
          <ReasonCodes codes={value.reason_codes} />
          <Records
            label="Look-Ahead Activities"
            items={activities}
            columns={[
              ["activity_external_id", "Activity"],
              ["name", "Nombre"],
              ["status", "Estado"],
              ["planned_start", "Planned Start"],
              ["planned_finish", "Planned Finish"],
              ["current_finish", "Current Finish"],
              ["forecast_finish", "Forecast Finish"],
              ["total_float", "Float"],
              ["float_unit", "Unidad float"],
              ["critical", "Critical"],
              ["near_critical", "Near-Critical"],
              ["wbs_external_id", "WBS"],
              ["plan_item_ids", "Plan"],
              ["work_package_ids", "Package"],
              ["scope_item_ids", "Scope"],
              ["readiness", "Readiness"],
              ["constraints", "Constraints"],
              ["driving_state", "Driving predecessor"],
            ]}
          />
          <Records
            label="Look-Ahead Separate Milestones"
            items={rows(value.milestones).map((row) => ({
              ...row,
              activity_external_id: row.activity_external_id ?? row.external_id,
            }))}
            columns={[
              ["activity_external_id", "Hito"],
              ["name", "Nombre"],
              ["planned_finish", "Fecha"],
              ["critical", "Critical"],
              ["total_float", "Float"],
            ]}
          />
          <Records
            label="Look-Ahead Groups"
            items={rows(value.groups)}
            columns={[
              ["key", "Grupo"],
              ["activity_count", "Actividades"],
              ["activity_ids", "Activity IDs"],
            ]}
          />
          <Records
            label="Look-Ahead Imported Relationships"
            items={relationships}
            columns={[
              ["successor_external_id", "Sucesor"],
              ["predecessor_external_id", "Predecesor"],
              ["predecessor_wbs_external_id", "WBS predecesor"],
              ["relationship_type", "Tipo"],
              ["lag", "Lag"],
              ["lag_unit", "Unidad lag"],
              ["authority", "Autoridad"],
            ]}
          />
          <Evidence title="Look-Ahead fuentes constraints readiness y autoridad" value={value} />
        </>
      ) : null}
    </section>
  );
}

export function ReportsPanel(props: ForecastPanelProps) {
  const baseQuery = props.query;
  const query = useCallback((value: string) => baseQuery(value, "reporting"), [baseQuery]);
  const reports = useForecastQuery(props.can("report.read") ? "/reports" : null, query, props.data);
  const analytics = useForecastQuery(props.can("report.read") ? "/analytics-contract" : null, query, props.data);
  const [selected, setSelected] = useState<ForecastRecord | null>(null);
  const [evidence, setEvidence] = useState("");
  const [success, setSuccess] = useState("");
  const records = rows(reports.result?.items);
  async function publish(successor = false) {
    if (!props.selected) return;
    const value = await props.command(
      successor && selected ? `/reports/${selected.id}/successor` : "/reports",
      {
        forecast_version_id: props.selected.id,
        evidence_reference: evidence,
        reason: props.reason,
      },
      successor && selected ? revision(selected) : undefined,
      "POST",
      "reporting"
    );
    setSelected(value as ForecastRecord);
    reports.reload();
    setSuccess(
      successor
        ? "Reporte republicado mediante una revisión sucesora. La revisión anterior permanece intacta."
        : "Reporte publicado con referencias gobernadas y narrativa factual."
    );
  }
  return (
    <section className="progressPanel" aria-label="Reporting History">
      <h3>Reporting History</h3>
      <p>
        La publicación exige período PUBLISHED, Forecast aprobado y las evidencias de las autoridades de origen.
        Corregir un reporte crea una revisión sucesora; nunca sobrescribe su historia.
      </p>
      {!props.can("report.read") ? (
        <p className="progressWarning">Sin permiso para consultar reportes publicados.</p>
      ) : null}
      {reports.error ? (
        <p role="alert" className="progressError">
          {reports.error}
        </p>
      ) : null}
      {success ? (
        <p role="status" className="progressNotice">
          {success}
        </p>
      ) : null}
      <Records
        label="Published Period Reports"
        items={records}
        columns={[
          ["id", "ID"],
          ["period_id", "Período"],
          ["forecast_version_id", "Forecast"],
          ["as_of", "As-of"],
          ["status", "Estado"],
          ["revision", "Revisión"],
          ["supersedes_id", "Sucesor de"],
          ["published_by", "Publicador"],
          ["content_hash", "Hash"],
        ]}
        select={(row) => {
          setSelected(row as ForecastRecord);
          setSuccess("");
        }}
      />
      <div className="progressForm">
        <Input label="Report Evidence reference" value={evidence} onChange={setEvidence} required />
        {props.can("report.publish") ? (
          <button
            type="button"
            disabled={
              props.busy ||
              !props.selected ||
              props.selected.status !== "APPROVED" ||
              props.reason.trim().length < 8 ||
              !evidence.trim()
            }
            onClick={() => void publish().catch(() => undefined)}
          >
            Publicar reporte del período
          </button>
        ) : null}
        {props.can("report.republish") && selected ? (
          <button
            type="button"
            disabled={
              props.busy ||
              !props.selected ||
              props.selected.status !== "APPROVED" ||
              props.reason.trim().length < 8 ||
              !evidence.trim()
            }
            onClick={() => void publish(true).catch(() => undefined)}
          >
            Republicar reporte mediante sucesor
          </button>
        ) : null}
      </div>
      {selected ? (
        <>
          <Facts
            values={[
              ["Reporte", selected.id],
              ["Estado", selected.status],
              ["Revisión", selected.revision],
              ["Hash publicado", selected.content_hash],
            ]}
          />
          <Narratives items={rows(selected.narratives_json)} />
          <Evidence
            title="Referencias inmutables del reporte"
            value={{
              source_refs: selected.source_refs_json,
              source_snapshot: selected.source_snapshot_json,
              metrics: selected.metrics_json,
            }}
          />
        </>
      ) : null}
      <p>
        Power BI consume estos read models con período, versión y hash explícitos. El refresh analítico no escribe en
        Forecast ni en las autoridades de origen.
      </p>
      <Evidence title="Contrato de lectura analítica Power BI" value={analytics.result} />
      <Records
        label="Forecast Audit History"
        items={(props.data.history ?? []).map((row) => ({
          ...row,
          forecast_version_id:
            row.entity_type === "ForecastVersion" ? row.entity_id : object(row.snapshot_json).forecast_version_id,
          actor_id: row.created_by,
        }))}
        columns={[
          ["event_type", "Evento"],
          ["forecast_version_id", "Forecast"],
          ["revision", "Revisión"],
          ["actor_id", "Actor"],
          ["created_at", "Fecha"],
          ["reason", "Motivo"],
        ]}
      />
    </section>
  );
}
