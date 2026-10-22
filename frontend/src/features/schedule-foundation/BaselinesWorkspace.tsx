import { useState, type FormEvent } from "react";
import { display, policyValues, type WorkspaceProps } from "./types";

export default function BaselinesWorkspace({ data, register, selected, busy, can, command }: WorkspaceProps) {
  const [reason, setReason] = useState("");
  const [type, setType] = useState("");
  const [period, setPeriod] = useState("");
  const [previousBaseline, setPreviousBaseline] = useState("");
  const configuredTypes = policyValues(data.configuration, "baseline_types", ["ORIGINAL", "CONTROL"]);
  const baselines = data.baselines.filter(
    (row) =>
      !register ||
      row.register_id === register.id ||
      data.versions.some((version) => version.id === row.schedule_version_id && version.register_id === register.id)
  );
  const approvedBaselines = baselines
    .filter((row) => row.status === "APPROVED_BASELINE")
    .sort((a, b) => (b.revision ?? b.id) - (a.revision ?? a.id));
  const types = approvedBaselines.length ? configuredTypes.filter((value) => value !== "ORIGINAL") : configuredTypes;
  const selectedType = types.includes(type) ? type : types[0];
  function prepare(event: FormEvent) {
    event.preventDefault();
    if (selected)
      void command(
        `/versions/${selected.id}/baselines`,
        {
          baseline_type: selectedType,
          reason,
          ...(previousBaseline ? { previous_baseline_id: Number(previousBaseline) } : {}),
        },
        selected.version
      ).catch(() => undefined);
  }
  return (
    <section className="schedulePanel">
      <h3>Baselines y Current · autoridades separadas</h3>
      <p>
        Current #{display(register?.current_version_id)} · Baseline #{display(register?.baseline_version_id)}. Aceptar
        un update no modifica el baseline aprobado. Una rebaseline requiere un candidato y aprobación independiente.
      </p>
      {selected && can("baseline.prepare") ? (
        <form className="scheduleForm" onSubmit={prepare}>
          <label>
            Baseline Type
            <select aria-label="Baseline Type" value={selectedType} onChange={(event) => setType(event.target.value)}>
              {types.map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
          {approvedBaselines.length ? (
            <label>
              Baseline anterior para sucesor
              <select
                aria-label="Baseline anterior para sucesor"
                required
                value={previousBaseline}
                onChange={(event) => setPreviousBaseline(event.target.value)}
              >
                <option value="">Seleccionar baseline aprobado que se reemplaza</option>
                {approvedBaselines.map((row) => (
                  <option key={row.id} value={row.id} disabled={row.id !== approvedBaselines[0].id}>
                    #{row.id} · {row.baseline_type} · Schedule Version #{row.schedule_version_id}
                  </option>
                ))}
              </select>
            </label>
          ) : null}
          <label>
            Motivo Baseline Schedule
            <input required minLength={8} value={reason} onChange={(event) => setReason(event.target.value)} />
          </label>
          <button
            disabled={busy || !types.length || !["ACCEPTED_CURRENT", "SUPERSEDED"].includes(selected.status)}
            type="submit"
          >
            Preparar Schedule Baseline Candidate
          </button>
          {!["ACCEPTED_CURRENT", "SUPERSEDED"].includes(selected.status) ? (
            <p>Solo una versión aceptada puede preparar Baseline; staging no concede autoridad.</p>
          ) : null}
        </form>
      ) : null}
      <label className="scheduleControl">
        Motivo transición Baseline
        <input minLength={8} value={reason} onChange={(event) => setReason(event.target.value)} />
      </label>
      <div className="scheduleTable">
        <table aria-label="Schedule Baselines">
          <thead>
            <tr>
              <th>Baseline</th>
              <th>Schedule Version</th>
              <th>Estado</th>
              <th>Hash inmutable</th>
              <th>Workflow</th>
            </tr>
          </thead>
          <tbody>
            {baselines.map((row) => (
              <tr key={row.id}>
                <td>
                  #{row.id} · {row.baseline_type}
                </td>
                <td>#{row.schedule_version_id}</td>
                <td>{row.status}</td>
                <td>{display(row.content_hash)}</td>
                <td>
                  {(
                    [
                      ["submit", "BASELINE_CANDIDATE", "Enviar Schedule Baseline"],
                      ["review", "SUBMITTED", "Revisar Schedule Baseline"],
                      ["approve", "UNDER_REVIEW", "Aprobar Schedule Baseline"],
                    ] as const
                  )
                    .filter(([action, status]) => row.status === status && can(`baseline.${action}`))
                    .map(([action, , label]) => (
                      <button
                        key={action}
                        disabled={busy || reason.trim().length < 8}
                        type="button"
                        onClick={() =>
                          void command(`/baselines/${row.id}/${action}`, { reason }, row.version).catch(() => undefined)
                        }
                      >
                        {label} #{row.id}
                      </button>
                    ))}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <h4>Asociación explícita con Project Controls Period</h4>
      <p>
        El Data Date de la versión no se iguala al cutoff. La asociación no genera costos, avance ni autoridad de
        período.
      </p>
      {selected && can("period.associate") ? (
        <form
          className="scheduleForm"
          onSubmit={(event) => {
            event.preventDefault();
            void command(
              `/versions/${selected.id}/period-associations`,
              { period_id: Number(period), reason },
              selected.version
            ).catch(() => undefined);
          }}
        >
          <label>
            Project Controls Period
            <select
              aria-label="Project Controls Period"
              required
              value={period}
              onChange={(event) => setPeriod(event.target.value)}
            >
              <option value="">Seleccionar período O1A</option>
              {data.periods
                .filter((row) => ["OPEN", "REVIEW"].includes(row.status ?? ""))
                .map((row) => (
                  <option key={row.id} value={row.id}>
                    {row.period_code ?? row.code ?? row.id} · cutoff{" "}
                    {display(row.cutoff_at ?? row.cutoff_date ?? row.cutoff)} · {row.status}
                  </option>
                ))}
            </select>
          </label>
          <label>
            Motivo asociación Period
            <input required minLength={8} value={reason} onChange={(event) => setReason(event.target.value)} />
          </label>
          <button
            disabled={busy || !period || !["ACCEPTED_CURRENT", "SUPERSEDED"].includes(selected.status)}
            type="submit"
          >
            Asociar Schedule Version a Period
          </button>
        </form>
      ) : null}
      <details className="scheduleDetails">
        <summary>Historial de asociaciones Schedule Period</summary>
        <pre>{JSON.stringify(data.period_associations, null, 2)}</pre>
      </details>
    </section>
  );
}
