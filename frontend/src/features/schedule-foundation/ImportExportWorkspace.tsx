import { useState, type FormEvent } from "react";
import { display, type WorkspaceProps } from "./types";
import { saveScheduleBlob } from "./download";

export default function ImportExportWorkspace({
  data,
  register,
  selected,
  busy,
  can,
  command,
  upload,
  download,
}: WorkspaceProps & {
  upload: (file: File, reason: string, kind: string) => Promise<void>;
  download: (id: number, filename: string) => Promise<void>;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [reason, setReason] = useState("");
  const [kind, setKind] = useState("UPDATE");
  const [purpose, setPurpose] = useState("CURRENT");
  const [baselineId, setBaselineId] = useState("");
  function stage(event: FormEvent) {
    event.preventDefault();
    if (file) void upload(file, reason, kind);
  }
  const action = (name: string) => {
    if (selected) void command(`/versions/${selected.id}/${name}`, { reason }, selected.version).catch(() => undefined);
  };
  const exports = data.exports.filter((row) => !selected || row.schedule_version_id === selected.id);
  return (
    <section className="schedulePanel">
      <h3>Import / Export · intercambio manual con P6</h3>
      <p>
        XML/XER se carga a staging. Validar y aceptar no aprueba un Baseline. El export XML usa únicamente el
        subconjunto admitido; no se afirma paridad completa con P6 ni export XER. No existe sincronización directa.
      </p>
      {register && can("import") ? (
        <form onSubmit={stage} className="scheduleForm">
          <label>
            Archivo P6 XML o XER
            <input
              required
              aria-label="Archivo P6 XML o XER"
              type="file"
              accept=".xml,.xer"
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
          </label>
          <label>
            Tipo import Schedule
            <select aria-label="Tipo import Schedule" value={kind} onChange={(event) => setKind(event.target.value)}>
              {["INITIAL", "UPDATE", "CORRECTION", "FORECAST", "SCENARIO"].map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
          <label>
            Motivo import Schedule
            <input required minLength={8} value={reason} onChange={(event) => setReason(event.target.value)} />
          </label>
          <button type="submit" disabled={busy || !file}>
            Importar P6 a staging
          </button>
        </form>
      ) : null}
      {!register ? <p>Crea o selecciona un Schedule Register antes de importar.</p> : null}
      {selected ? (
        <>
          <div className="scheduleVersionFacts">
            <span>
              Schedule Version #{selected.id} · r{selected.revision} · {selected.status}
            </span>
            <span>Data Date {display(selected.data_date)}</span>
            <span>Fuente {selected.source_file_name || selected.source_format}</span>
            <span>SHA256 {display(selected.source_hash)}</span>
          </div>
          <p>Data Date es un dato explícito del cronograma; no se reemplaza por el cutoff de Project Controls.</p>
          <div className="scheduleActions">
            <label className="scheduleControl">
              Motivo revisión Schedule
              <input minLength={8} value={reason} onChange={(event) => setReason(event.target.value)} />
            </label>
            {can("validate") && ["DRAFT", "STAGED", "VALIDATED"].includes(selected.status) ? (
              <button disabled={busy || reason.trim().length < 8} type="button" onClick={() => action("validate")}>
                Validar Schedule Version
              </button>
            ) : null}
            {can("review") && selected.status === "VALIDATED" ? (
              <button disabled={busy || reason.trim().length < 8} type="button" onClick={() => action("review")}>
                Revisar Schedule Version
              </button>
            ) : null}
            {can("accept") && selected.status === "UNDER_REVIEW" ? (
              <button disabled={busy || reason.trim().length < 8} type="button" onClick={() => action("accept")}>
                Aceptar Schedule Current
              </button>
            ) : null}
            {can("review") && ["DRAFT", "STAGED", "VALIDATED", "UNDER_REVIEW"].includes(selected.status) ? (
              <button disabled={busy || reason.trim().length < 8} type="button" onClick={() => action("reject")}>
                Rechazar Schedule Version
              </button>
            ) : null}
          </div>
          <details className="scheduleDetails" open>
            <summary>Validación y subconjunto admitido</summary>
            <pre>{JSON.stringify(selected.validation_json, null, 2)}</pre>
          </details>
          <details className="scheduleDetails" open>
            <summary>Diff y reconciliación con versión anterior</summary>
            <pre>{JSON.stringify(selected.diff_json, null, 2)}</pre>
          </details>
          {can("export") ? (
            <form
              className="scheduleForm"
              onSubmit={(event) => {
                event.preventDefault();
                void command(
                  `/versions/${selected.id}/exports`,
                  {
                    format: "XML",
                    purpose,
                    ...(purpose === "BASELINE" ? { baseline_id: Number(baselineId) } : {}),
                    reason,
                  },
                  selected.version
                ).catch(() => undefined);
              }}
            >
              <label>
                Export purpose
                <select
                  aria-label="Export purpose"
                  value={purpose}
                  onChange={(event) => setPurpose(event.target.value)}
                >
                  <option>CURRENT</option>
                  <option>BASELINE</option>
                  <option>DRAFT_FOR_P6</option>
                </select>
              </label>
              {purpose === "BASELINE" ? (
                <label>
                  Baseline para export
                  <select
                    aria-label="Baseline para export"
                    required
                    value={baselineId}
                    onChange={(event) => setBaselineId(event.target.value)}
                  >
                    <option value="">Seleccionar baseline aprobado</option>
                    {data.baselines
                      .filter((row) => row.schedule_version_id === selected.id && row.status === "APPROVED_BASELINE")
                      .map((row) => (
                        <option key={row.id} value={row.id}>
                          {row.baseline_type} · #{row.id}
                        </option>
                      ))}
                  </select>
                </label>
              ) : null}
              <label>
                Motivo export Schedule
                <input required minLength={8} value={reason} onChange={(event) => setReason(event.target.value)} />
              </label>
              <button
                disabled={
                  busy ||
                  (purpose === "CURRENT" && selected.status !== "ACCEPTED_CURRENT") ||
                  (purpose === "BASELINE" && !baselineId)
                }
                type="submit"
              >
                Generar P6 XML y manifest
              </button>
              {purpose === "CURRENT" && selected.status !== "ACCEPTED_CURRENT" ? (
                <p>
                  CURRENT requiere la versión vigente aceptada. Para preparar intercambio sin autoridad usa
                  DRAFT_FOR_P6.
                </p>
              ) : null}
            </form>
          ) : null}
        </>
      ) : null}
      <div className="scheduleTable">
        <table aria-label="Schedule export manifests">
          <thead>
            <tr>
              <th>Export</th>
              <th>Formato / Versión</th>
              <th>Manifiesto</th>
              <th>Archivo</th>
            </tr>
          </thead>
          <tbody>
            {exports.map((row) => (
              <tr key={row.id}>
                <td>#{row.id}</td>
                <td>
                  {row.format ?? display(row.manifest_json?.format)} · #{row.schedule_version_id}
                </td>
                <td>
                  <details>
                    <summary>Ver manifest #{row.id}</summary>
                    <pre>{JSON.stringify(row.manifest_json ?? row, null, 2)}</pre>
                  </details>
                  <button
                    type="button"
                    onClick={() =>
                      saveScheduleBlob(
                        new Blob([JSON.stringify(row.manifest_json ?? row, null, 2)], { type: "application/json" }),
                        `schedule-export-${row.id}-manifest.json`
                      )
                    }
                  >
                    Descargar manifest #{row.id}
                  </button>
                </td>
                <td>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() =>
                      void download(row.id, row.source_file_name || row.file_name || `schedule-export-${row.id}.xml`)
                    }
                  >
                    Descargar P6 XML #{row.id}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
