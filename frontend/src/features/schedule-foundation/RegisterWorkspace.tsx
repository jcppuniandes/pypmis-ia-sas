import { useState, type FormEvent } from "react";
import { display, emptySnapshot, policyValues, type WorkspaceProps } from "./types";

export default function RegisterWorkspace({ data, register, selected, busy, can, command }: WorkspaceProps) {
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const types = policyValues(data.configuration, "schedule_types", ["CONTROL"]);
  const [scheduleType, setScheduleType] = useState("");
  const [purpose, setPurpose] = useState("");
  const [timezone, setTimezone] = useState("America/Bogota");
  const [calendar, setCalendar] = useState("EXPLICIT_SOURCE");
  const [reason, setReason] = useState("");
  const [snapshot, setSnapshot] = useState("");
  const [kind, setKind] = useState("INITIAL");
  const [error, setError] = useState("");
  async function create(event: FormEvent) {
    event.preventDefault();
    try {
      await command("/registers", {
        schedule_code: code,
        name,
        schedule_type: scheduleType || types[0],
        purpose,
        timezone,
        calendar_basis: calendar,
        reason,
      });
    } catch {
      /* The shared command displays the server error. */
    }
  }
  function createVersion(event: FormEvent) {
    event.preventDefault();
    if (!register) return;
    try {
      const parsed: unknown = JSON.parse(snapshot);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
        throw new Error("La versión requiere un objeto de Schedule completo.");
      setError("");
      void command(
        `/registers/${register.id}/versions`,
        { snapshot_json: parsed, kind, reason, ...(selected ? { predecessor_version_id: selected.id } : {}) },
        register.version
      ).catch(() => undefined);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "JSON inválido");
    }
  }
  return (
    <section className="schedulePanel">
      <h3>Schedule Register · corrientes gobernadas</h3>
      <p>
        El registro pertenece al Proyecto canónico. Current y Baseline son referencias independientes; crear o importar
        Schedule nunca crea Scope.
      </p>
      <div className="scheduleTable">
        <table aria-label="Schedule Register">
          <thead>
            <tr>
              <th>Registro</th>
              <th>Tipo</th>
              <th>Current</th>
              <th>Baseline</th>
              <th>Base de calendario</th>
              <th>Zona horaria</th>
            </tr>
          </thead>
          <tbody>
            {data.registers.map((row) => (
              <tr key={row.id}>
                <td>
                  {row.schedule_code}
                  <small>
                    {row.name} · v{row.version}
                  </small>
                </td>
                <td>{row.schedule_type}</td>
                <td>{display(row.current_version_id)}</td>
                <td>{display(row.baseline_version_id)}</td>
                <td>{display(row.calendar_basis)}</td>
                <td>{row.timezone}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {can("register.edit") ? (
        <form className="scheduleForm" onSubmit={(event) => void create(event)}>
          <label>
            Schedule Code
            <input required value={code} onChange={(event) => setCode(event.target.value)} />
          </label>
          <label>
            Schedule Name
            <input required value={name} onChange={(event) => setName(event.target.value)} />
          </label>
          <label>
            Schedule Type
            <select
              aria-label="Schedule Type"
              value={scheduleType || types[0]}
              onChange={(event) => setScheduleType(event.target.value)}
            >
              {types.map((type) => (
                <option key={type}>{type}</option>
              ))}
            </select>
          </label>
          <label>
            Purpose
            <input value={purpose} onChange={(event) => setPurpose(event.target.value)} />
          </label>
          <label>
            Calendar Basis
            <input
              required
              value={calendar}
              onChange={(event) => setCalendar(event.target.value)}
              placeholder="Referencia explícita; no asumir 8h/día"
            />
          </label>
          <label>
            Schedule Timezone
            <input required value={timezone} onChange={(event) => setTimezone(event.target.value)} />
          </label>
          <label>
            Motivo Schedule Register
            <input required minLength={8} value={reason} onChange={(event) => setReason(event.target.value)} />
          </label>
          <button disabled={busy} type="submit">
            Crear Schedule Register
          </button>
        </form>
      ) : null}
      {register && can("version.edit") ? (
        <details className="scheduleDetails">
          <summary>Nueva versión manual o sucesora</summary>
          <p>
            Se crea una versión distinta; la versión seleccionada y el Scope aprobado no se editan. Fechas, holguras y
            criticidad de P6 no se recalculan aquí.
          </p>
          <button
            type="button"
            onClick={() =>
              setSnapshot(JSON.stringify(selected?.snapshot_json ?? emptySnapshot(register.timezone), null, 2))
            }
          >
            Preparar copia de versión seleccionada
          </button>
          <form onSubmit={createVersion} className="scheduleForm">
            <label>
              Tipo de nueva versión
              <select aria-label="Tipo de nueva versión" value={kind} onChange={(event) => setKind(event.target.value)}>
                {["INITIAL", "UPDATE", "CORRECTION", "FORECAST", "SCENARIO"].map((value) => (
                  <option key={value}>{value}</option>
                ))}
              </select>
            </label>
            <label>
              Motivo nueva versión
              <input required minLength={8} value={reason} onChange={(event) => setReason(event.target.value)} />
            </label>
            <label className="scheduleWide">
              Schedule Snapshot JSON
              <textarea
                aria-label="Schedule Snapshot JSON"
                required
                rows={18}
                spellCheck={false}
                value={snapshot}
                onChange={(event) => setSnapshot(event.target.value)}
              />
            </label>
            <button disabled={busy || !snapshot} type="submit">
              Crear nueva Schedule Version
            </button>
          </form>
          {error ? <p role="alert">{error}</p> : null}
        </details>
      ) : null}
    </section>
  );
}
