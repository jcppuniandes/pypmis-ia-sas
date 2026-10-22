import { display, type JsonRecord, type WorkspaceProps } from "./types";

export function CollectionTable({
  title,
  rows,
  fields,
}: {
  title: string;
  rows: JsonRecord[];
  fields: [string, string][];
}) {
  return (
    <>
      <h4>{title}</h4>
      {rows.length ? (
        <div className="scheduleTable">
          <table aria-label={title}>
            <thead>
              <tr>
                {fields.map(([key, label]) => (
                  <th key={key}>{label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={String(row.external_id ?? row.id ?? index)}>
                  {fields.map(([key]) => (
                    <td key={key}>{display(row[key])}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p>Sin datos publicados para esta colección.</p>
      )}
    </>
  );
}
export default function ReferenceWorkspace({
  selected,
  kind,
}: WorkspaceProps & { kind: "Calendars" | "Relationships" | "Codes & Constraints" }) {
  const snapshot = selected?.snapshot_json;
  return (
    <section className="schedulePanel">
      <h3>{kind}</h3>
      {kind === "Calendars" ? (
        <>
          <p>
            Calendarios importados con jornadas, turnos, excepciones y zona horaria. No se asumen ocho horas por día ni
            se recalculan fechas.
          </p>
          <CollectionTable
            title="Schedule Calendars"
            rows={snapshot?.calendars ?? []}
            fields={[
              ["external_id", "P6 ID"],
              ["name", "Nombre"],
              ["type", "Tipo"],
              ["hours_per_day", "Horas por día fuente"],
              ["workweek", "Semana"],
              ["shifts", "Turnos"],
              ["holidays", "Festivos"],
              ["exceptions", "Excepciones"],
              ["timezone", "Timezone"],
            ]}
          />
        </>
      ) : null}
      {kind === "Relationships" ? (
        <>
          <p>
            FS, SS, FF y SF conservan su tipo y lag, incluidos valores negativos. Las referencias externas no crean
            actividades internas ficticias.
          </p>
          <CollectionTable
            title="Schedule Relationships"
            rows={snapshot?.relationships ?? []}
            fields={[
              ["external_id", "P6 ID"],
              ["predecessor_external_id", "Predecessor"],
              ["successor_external_id", "Successor"],
              ["relationship_type", "Tipo"],
              ["lag", "Lag"],
              ["lag_unit", "Unidad lag"],
              ["is_external", "Externa"],
              ["resolution", "Resolución"],
            ]}
          />
          <CollectionTable
            title="External Schedule Links"
            rows={snapshot?.external_links ?? []}
            fields={[
              ["predecessor_external_id", "Predecessor"],
              ["successor_external_id", "Successor"],
              ["project_external_id", "Proyecto externo"],
              ["resolution", "Resolución"],
              ["reason", "Observación"],
            ]}
          />
        </>
      ) : null}
      {kind === "Codes & Constraints" ? (
        <>
          <p>
            Activity Codes y restricciones preservan la semántica fuente; no se convierten en Scope, WBS ni autoridad de
            costos.
          </p>
          <CollectionTable
            title="Schedule Constraints"
            rows={snapshot?.constraints ?? []}
            fields={[
              ["activity_external_id", "Actividad"],
              ["type", "Tipo de restricción"],
              ["date", "Fecha fuente"],
            ]}
          />
          <CollectionTable
            title="Activity Codes"
            rows={snapshot?.codes ?? []}
            fields={[
              ["external_id", "P6 ID"],
              ["code_type", "Tipo"],
              ["code", "Código"],
              ["name", "Nombre"],
              ["description", "Descripción"],
            ]}
          />
          <CollectionTable
            title="Activity Code Assignments"
            rows={snapshot?.code_assignments ?? []}
            fields={[
              ["activity_external_id", "Actividad"],
              ["code_external_id", "Código"],
              ["code_type_external_id", "Tipo de código"],
            ]}
          />
        </>
      ) : null}
      <details className="scheduleDetails">
        <summary>Definiciones fuente preservadas</summary>
        <pre>
          {JSON.stringify(
            kind === "Calendars"
              ? snapshot?.calendars
              : kind === "Relationships"
                ? { relationships: snapshot?.relationships, external_links: snapshot?.external_links }
                : {
                    codes: snapshot?.codes,
                    constraints: snapshot?.constraints,
                    assignments: snapshot?.code_assignments,
                  },
            null,
            2
          )}
        </pre>
      </details>
    </section>
  );
}
