import { useState } from "react";
import { Field, NamedSelect } from "./Fields";
import type { AwpPanelProps } from "./types";
import { policyContent } from "../schedule-foundation/types";

const dimensions = [
  "ENGINEERING",
  "MATERIAL",
  "LOGISTICS",
  "ACCESS",
  "PERMIT",
  "QUALITY",
  "HSE",
  "RESOURCE",
  "PREDECESSOR",
];
export default function ReadinessPanel({ data, busy, reason, can, command }: AwpPanelProps) {
  const [selectedId, setSelectedId] = useState("");
  const [asOf, setAsOf] = useState("");
  const [evidence, setEvidence] = useState<Record<string, string>>({});
  const selected = data.packages.find((row) => row.id === Number(selectedId)) ?? data.packages[0];
  const current = Array.isArray(data.current_readiness)
    ? data.current_readiness.find((row) => Number(row.work_package_id) === selected?.id)
    : data.current_readiness[String(selected?.id)];
  const content = policyContent(data.configuration);
  const required = content.readiness_requirements as Record<string, { required_dimensions: string[] }> | undefined;
  const configured = required?.[selected?.package_type ?? ""]?.required_dimensions ?? [];
  const availableDimensions = [...new Set([...dimensions, ...configured])];
  const run = (path: string, payload: unknown) => {
    if (selected) void command(path, payload, selected.version).catch(() => undefined);
  };
  return (
    <section className="awpPanel">
      <h3>Workfront Readiness</h3>
      <p>
        Scheduled ≠ Ready. READY requiere requisitos satisfechos; RELEASED exige otra acción autorizada e independiente.
        As of es explícito, no se deduce de las fechas P6.
      </p>
      <div className="awpTable">
        <table aria-label="Workfront Readiness">
          <thead>
            <tr>
              <th>CWA</th>
              <th>Paquete</th>
              <th>Tipo</th>
              <th>Estado Schedule</th>
              <th>Overall readiness</th>
              <th>Bloqueos</th>
              <th>Release</th>
            </tr>
          </thead>
          <tbody>
            {data.packages.map((row) => {
              const readiness = Array.isArray(data.current_readiness)
                ? data.current_readiness.find((item) => Number(item.work_package_id) === row.id)
                : data.current_readiness[String(row.id)];
              return (
                <tr key={row.id}>
                  <td>{data.cwas.find((item) => item.id === row.cwa_id)?.code ?? "—"}</td>
                  <td>{row.package_code}</td>
                  <td>{row.package_type}</td>
                  <td>
                    {data.effective_mappings.some(
                      (item) =>
                        Number(item.work_package_id ?? item.package_id) === row.id && item.target_kind === "ACTIVITY"
                    )
                      ? "SCHEDULED"
                      : "UNMAPPED"}
                  </td>
                  <td>{String(readiness?.readiness_state ?? row.readiness_state ?? "NOT_ASSESSED")}</td>
                  <td>
                    {Array.isArray(readiness?.blocking_constraints) ? readiness.blocking_constraints.length : "—"}
                  </td>
                  <td>{row.release_state ?? "NOT_RELEASED"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <NamedSelect
        label="Readiness Package"
        value={String(selected?.id ?? "")}
        onChange={(value) => {
          setSelectedId(value);
          setEvidence({});
        }}
        optional={false}
        options={data.packages.map((row) => ({ value: row.id, label: `${row.package_code} · ${row.package_type}` }))}
      />
      {selected ? (
        <>
          <div className="awpFacts">
            <div>
              <strong>Overall</strong>
              <span>{String(current?.readiness_state ?? "NOT_ASSESSED")}</span>
            </div>
            <div>
              <strong>Evaluación vigente</strong>
              <span>{current?.stale ? "STALE · reevaluar" : "Revisar source hashes"}</span>
            </div>
            <div>
              <strong>Release</strong>
              <span>{selected.release_state ?? "NOT_RELEASED"}</span>
            </div>
          </div>
          <div className="awpTable">
            <table aria-label="Readiness dimensions">
              <thead>
                <tr>
                  <th>Dimensión</th>
                  <th>Requisito publicado</th>
                  <th>Estado</th>
                </tr>
              </thead>
              <tbody>
                {availableDimensions.map((dimension) => (
                  <tr key={dimension}>
                    <td>
                      {dimension === "MATERIAL"
                        ? "MATERIAL / PROCUREMENT"
                        : dimension === "RESOURCE"
                          ? "RESOURCE / EQUIPMENT"
                          : dimension}
                    </td>
                    <td>{configured.includes(dimension) ? "MANDATORY" : "Según perfil / restricciones"}</td>
                    <td>
                      {JSON.stringify(
                        (current?.dimensions as Record<string, unknown> | undefined)?.[dimension] ?? "NOT_ASSESSED"
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {can("readiness.assess") ? (
            <form
              className="awpForm"
              onSubmit={(e) => {
                e.preventDefault();
                run(`/packages/${selected.id}/assess`, {
                  as_of: asOf,
                  evidence_json: Object.fromEntries(
                    Object.entries(evidence).filter(([, reference]) => reference.trim())
                  ),
                  reason,
                });
              }}
            >
              <Field label="Readiness as of">
                <input
                  required
                  aria-label="Readiness as of"
                  type="date"
                  value={asOf}
                  onChange={(e) => setAsOf(e.target.value)}
                />
              </Field>
              {availableDimensions.map((dimension) => (
                <Field key={dimension} label={`Readiness evidence ${dimension}`}>
                  <input
                    aria-label={`Readiness evidence ${dimension}`}
                    value={evidence[dimension] ?? ""}
                    onChange={(e) => setEvidence({ ...evidence, [dimension]: e.target.value })}
                  />
                </Field>
              ))}
              <button type="submit" disabled={busy || !asOf || reason.trim().length < 8}>
                Evaluar Package Readiness
              </button>
            </form>
          ) : null}
          {can("package.release") ? (
            <button
              type="button"
              disabled={
                busy || reason.trim().length < 8 || current?.readiness_state !== "READY" || Boolean(current?.stale)
              }
              onClick={() => run(`/packages/${selected.id}/release`, { reason })}
            >
              Release Package independiente
            </button>
          ) : null}
          <details open>
            <summary>Assessment y dimensiones · fuente / política</summary>
            <pre>{JSON.stringify(current, null, 2)}</pre>
          </details>
          <details>
            <summary>Readiness history inmutable</summary>
            <pre>
              {JSON.stringify(
                data.assessments.filter((row) => Number(row.work_package_id) === selected.id),
                null,
                2
              )}
            </pre>
          </details>
        </>
      ) : (
        <p>No hay paquetes. Crear paquetes no crea Activities ni readiness.</p>
      )}
    </section>
  );
}
