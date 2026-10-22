import { useState, type FormEvent } from "react";
import { Field, MappingTarget, NamedSelect } from "./Fields";
import { packageTypes, type AwpPanelProps, type WorkPackage } from "./types";
import { policyValues } from "../schedule-foundation/types";

export default function PackagesPanel({ data, busy, reason, can, command }: AwpPanelProps) {
  const [selectedId, setSelectedId] = useState(0);
  const [draft, setDraft] = useState({
    package_code: "",
    package_type: "IWP",
    name: "",
    description: "",
    cwa_id: "",
    owner_user_id: "",
    responsible_role: "",
  });
  const [transition, setTransition] = useState("PLANNED");
  const [kind, setKind] = useState("PLAN");
  const [target, setTarget] = useState("");
  const [versionId, setVersionId] = useState("");
  const [activity, setActivity] = useState("");
  const [phase, setPhase] = useState("EXECUTE");
  const [action, setAction] = useState("SET");
  const selected = data.packages.find((row) => row.id === selectedId);
  function select(row?: WorkPackage) {
    setSelectedId(row?.id ?? 0);
    setDraft({
      package_code: row?.package_code ?? "",
      package_type: row?.package_type ?? "IWP",
      name: row?.name ?? "",
      description: String(row?.description ?? ""),
      cwa_id: row?.cwa_id ? String(row.cwa_id) : "",
      owner_user_id: row?.owner_user_id ? String(row.owner_user_id) : "",
      responsible_role: row?.responsible_role ?? "",
    });
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    const result = await command(
      `/packages${selected ? `/${selected.id}` : ""}`,
      {
        ...draft,
        cwa_id: draft.cwa_id ? Number(draft.cwa_id) : null,
        owner_user_id: draft.owner_user_id ? Number(draft.owner_user_id) : null,
        reason,
      },
      selected?.version,
      selected ? "PUT" : "POST"
    );
    select(result as WorkPackage);
  }
  async function map(event: FormEvent) {
    event.preventDefault();
    if (!selected) return;
    await command(
      `/packages/${selected.id}/mappings`,
      {
        target_kind: kind,
        target_id: kind === "ACTIVITY" ? null : Number(target),
        schedule_version_id: kind === "ACTIVITY" ? Number(versionId) : null,
        activity_external_id: kind === "ACTIVITY" ? activity : null,
        phase,
        action,
        reason,
      },
      selected.version
    );
  }
  return (
    <section className="awpPanel">
      <h3>Work Packages</h3>
      <p>
        Scope define WHAT. Los paquetes son agrupaciones de ejecución M:N; las fechas pertenecen a Activities de P6.
      </p>
      <div className="awpTable">
        <table aria-label="Work Packages">
          <thead>
            <tr>
              <th>Código</th>
              <th>Tipo</th>
              <th>Nombre</th>
              <th>CWA</th>
              <th>Estado</th>
              <th>Readiness</th>
              <th>Release</th>
              <th>Revisión</th>
              <th>Detalle</th>
            </tr>
          </thead>
          <tbody>
            {data.packages.map((row) => (
              <tr key={row.id}>
                <td>{row.package_code}</td>
                <td>{row.package_type}</td>
                <td>{row.name}</td>
                <td>{data.cwas.find((cwa) => cwa.id === row.cwa_id)?.code ?? "—"}</td>
                <td>{row.status}</td>
                <td>
                  {String(
                    (!Array.isArray(data.current_readiness)
                      ? data.current_readiness[String(row.id)]?.readiness_state
                      : undefined) ??
                      row.readiness_state ??
                      "NOT_ASSESSED"
                  )}
                </td>
                <td>{row.release_state}</td>
                <td>{row.revision ?? row.version}</td>
                <td>
                  <button type="button" onClick={() => select(row)}>
                    Ver Package {row.package_code}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {can("package.edit") ? (
        <>
          <button type="button" onClick={() => select()}>
            Nuevo Work Package
          </button>
          <form onSubmit={(e) => void save(e).catch(() => undefined)} className="awpForm">
            <Field label="Package code">
              <input
                aria-label="Package code"
                required
                value={draft.package_code}
                onChange={(e) => setDraft({ ...draft, package_code: e.target.value })}
              />
            </Field>
            <NamedSelect
              label="Package type"
              value={draft.package_type}
              onChange={(value) => setDraft({ ...draft, package_type: value })}
              optional={false}
              options={policyValues(data.configuration, "package_types", packageTypes).map((value) => ({
                value,
                label: value,
              }))}
            />
            <Field label="Package name">
              <input
                aria-label="Package name"
                required
                value={draft.name}
                onChange={(e) => setDraft({ ...draft, name: e.target.value })}
              />
            </Field>
            <Field label="Package description">
              <input
                aria-label="Package description"
                value={draft.description}
                onChange={(e) => setDraft({ ...draft, description: e.target.value })}
              />
            </Field>
            <NamedSelect
              label="Package CWA"
              value={draft.cwa_id}
              onChange={(value) => setDraft({ ...draft, cwa_id: value })}
              options={data.cwas.map((row) => ({ value: row.id, label: `${row.code} · ${row.name}` }))}
            />
            <Field label="Package owner user ID">
              <input
                aria-label="Package owner user ID"
                type="number"
                min="1"
                value={draft.owner_user_id}
                onChange={(e) => setDraft({ ...draft, owner_user_id: e.target.value })}
              />
            </Field>
            <Field label="Package responsible role">
              <input
                aria-label="Package responsible role"
                value={draft.responsible_role}
                onChange={(e) => setDraft({ ...draft, responsible_role: e.target.value })}
              />
            </Field>
            <button type="submit" disabled={busy || reason.trim().length < 8}>
              {selected ? "Guardar revisión Package" : "Crear Work Package"}
            </button>
          </form>
        </>
      ) : null}
      {selected ? (
        <>
          <h4>Paquete seleccionado · {selected.package_code}</h4>
          {can("package.edit") || can("package.review") ? (
            <div className="awpForm">
              <NamedSelect
                label="Package lifecycle action"
                value={transition}
                onChange={setTransition}
                optional={false}
                options={[
                  "DRAFT",
                  "PLANNED",
                  "UNDER_REVIEW",
                  "READY",
                  "IN_PROGRESS",
                  "COMPLETED",
                  "CLOSED",
                  "SUPERSEDED",
                ].map((value) => ({ value, label: value }))}
              />
              <button
                type="button"
                disabled={busy || reason.trim().length < 8}
                onClick={() =>
                  void command(
                    `/packages/${selected.id}/transition`,
                    { status: transition, reason },
                    selected.version
                  ).catch(() => undefined)
                }
              >
                Aplicar estado Package
              </button>
            </div>
          ) : null}
          {can("mapping.edit") ? (
            <form className="awpForm" onSubmit={(e) => void map(e).catch(() => undefined)}>
              <NamedSelect
                label="Package mapping kind"
                value={kind}
                onChange={(value) => {
                  setKind(value);
                  setTarget("");
                }}
                optional={false}
                options={["SCOPE", "PLAN", "ACTIVITY"].map((value) => ({ value, label: value }))}
              />
              <MappingTarget
                data={data}
                kind={kind}
                target={target}
                setTarget={setTarget}
                versionId={versionId}
                setVersionId={setVersionId}
                activity={activity}
                setActivity={setActivity}
              />
              <NamedSelect
                label="Package Activity phase"
                value={phase}
                onChange={setPhase}
                optional={false}
                options={["EXECUTE", "INSTALL", "USE", "REMOVE"].map((value) => ({ value, label: value }))}
              />
              <NamedSelect
                label="Package mapping action"
                value={action}
                onChange={setAction}
                optional={false}
                options={["SET", "REMOVE"].map((value) => ({ value, label: value }))}
              />
              <button type="submit" disabled={busy || reason.trim().length < 8}>
                Guardar Package mapping
              </button>
            </form>
          ) : null}
          <details open>
            <summary>Historial de mapeos · no modifica Schedule Version</summary>
            <pre>
              {JSON.stringify(
                data.mappings.filter((row) => Number(row.work_package_id ?? row.package_id) === selected.id),
                null,
                2
              )}
            </pre>
          </details>
          <details>
            <summary>Historial y trazabilidad del paquete</summary>
            <pre>{JSON.stringify(selected, null, 2)}</pre>
          </details>
        </>
      ) : (
        <p>Selecciona un paquete para editar su ciclo y vínculos.</p>
      )}
    </section>
  );
}
