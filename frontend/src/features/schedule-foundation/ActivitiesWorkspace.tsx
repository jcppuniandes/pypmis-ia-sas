import { useEffect, useState } from "react";
import MappingPanel from "./MappingPanel";
import { operationalError } from "../operational-context/commands";
import { display, type ScheduleObject, type WorkspaceProps } from "./types";

export default function ActivitiesWorkspace(
  props: WorkspaceProps & { query?: (versionId: number) => Promise<ScheduleObject[]> }
) {
  const [target, setTarget] = useState("");
  const [filter, setFilter] = useState("");
  const [result, setResult] = useState<{
    id: number;
    version: number;
    items?: ScheduleObject[];
    error?: string;
  } | null>(null);
  const { selected, query } = props;
  useEffect(() => {
    if (!selected || !query) return;
    let active = true;
    query(selected.id)
      .then((items) => {
        if (active) setResult({ id: selected.id, version: selected.version, items });
      })
      .catch((caught) => {
        if (active) setResult({ id: selected.id, version: selected.version, error: operationalError(caught) });
      });
    return () => {
      active = false;
    };
  }, [selected, query]);
  const currentResult = result?.id === selected?.id && result?.version === selected?.version ? result : null;
  const rows = (currentResult?.items ?? props.selected?.snapshot_json.activities ?? []).filter((row) =>
    `${row.code} ${row.name} ${row.external_id}`.toLowerCase().includes(filter.toLowerCase())
  );
  const detail = rows.find((row) => row.external_id === target);
  return (
    <section className="schedulePanel">
      <h3>Activities y Milestones</h3>
      <p>
        Fechas, duraciones remanentes, porcentaje, float y criticidad se muestran con su procedencia. UNKNOWN no
        equivale a cero. P6 mantiene la autoridad CPM.
      </p>
      {currentResult?.error ? (
        <p role="alert">
          No se pudo consultar la clasificación actual: {currentResult.error}. Se muestran datos fuente sin inferir
          criticidad.
        </p>
      ) : null}
      <label className="scheduleControl">
        Filtrar actividades
        <input value={filter} onChange={(event) => setFilter(event.target.value)} />
      </label>
      <div className="scheduleTable">
        <table aria-label="Schedule Activities">
          <thead>
            <tr>
              <th>Actividad</th>
              <th>Tipo / Estado</th>
              <th>WBS / Calendar</th>
              <th>Duración original / remanente</th>
              <th>Data Date y fechas</th>
              <th>Float / Criticality</th>
              <th>Mapeo</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.external_id}>
                <td>
                  {row.code ?? row.external_id}
                  <small>{row.name}</small>
                  <small>P6 {row.external_id}</small>
                </td>
                <td>
                  {display(row.activity_type ?? row.type)}
                  <small>{display(row.status)}</small>
                  <small>
                    Fuente % {display(row.percent_complete)} · {display(row.percent_complete_type)} (no Progress
                    aprobado)
                  </small>
                </td>
                <td>
                  {display(row.wbs_external_id)}
                  <small>{display(row.calendar_external_id)}</small>
                </td>
                <td>
                  {display(row.original_duration)} / {display(row.remaining_duration)}
                  <small>{display(row.duration_unit)}</small>
                </td>
                <td>
                  {display(props.selected?.data_date)}
                  <small>Start {display(row.start ?? row.planned_start)}</small>
                  <small>Finish {display(row.finish ?? row.planned_finish)}</small>
                  <small>
                    Actual {display(row.actual_start)} / {display(row.actual_finish)}
                  </small>
                </td>
                <td>
                  Total {display(row.total_float)}
                  <small>Unidad float {display(row.float_unit)}</small>
                  <small>Free {display(row.free_float)}</small>
                  <small>Critical {display(row.critical_flag ?? row.critical)}</small>
                  <small>Near-critical {display(row.near_critical)}</small>
                  <small>Autoridad {display(row.criticality_authority)}</small>
                </td>
                <td>
                  <button type="button" onClick={() => setTarget(row.external_id)}>
                    Inspeccionar Activity {row.code ?? row.external_id}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {detail ? (
        <details className="scheduleDetails">
          <summary>Datos fuente Activity {detail.code ?? detail.external_id}</summary>
          <pre>{JSON.stringify(detail, null, 2)}</pre>
        </details>
      ) : null}
      <MappingPanel key={`${props.selected?.id}:${target}`} {...props} targetKind="ACTIVITY" targetId={target} />
      <p>
        Activity → Plan Item → Scope Item → Derived 3D mantiene trazabilidad. No se activa reproducción 4D ni aprobación
        de Progress.
      </p>
    </section>
  );
}
