import { useState, type FormEvent } from "react";
import { Field, MappingTarget, NamedSelect } from "./Fields";
import { constraintTypes, type AwpPanelProps, type ExecutionConstraint } from "./types";
import { policyContent } from "../schedule-foundation/types";

export default function ConstraintsPanel({ data, busy, reason, can, command }: AwpPanelProps) {
  const [selectedId, setSelectedId] = useState(0);
  const [draft, setDraft] = useState({
    constraint_type: "ENGINEERING",
    code: "",
    title: "",
    description: "",
    blocking: true,
    owner_user_id: "",
    due_date: "",
    source_domain: "AWP",
    source_reference: "",
    evidence_reference: "",
  });
  const [transition, setTransition] = useState("CLEARED");
  const [evidence, setEvidence] = useState("");
  const [waiver, setWaiver] = useState("");
  const [kind, setKind] = useState("PACKAGE");
  const [target, setTarget] = useState("");
  const [versionId, setVersionId] = useState("");
  const [activity, setActivity] = useState("");
  const selected = data.constraints.find((row) => row.id === selectedId);
  const configuredTypes = policyContent(data.configuration).constraint_types as
    | Record<string, { enabled: boolean }>
    | undefined;
  function select(row?: ExecutionConstraint) {
    setSelectedId(row?.id ?? 0);
    setDraft({
      constraint_type: row?.constraint_type ?? "ENGINEERING",
      code: row?.code ?? "",
      title: row?.title ?? "",
      description: String(row?.description ?? ""),
      blocking: row ? row.blocking : true,
      owner_user_id: row?.owner_user_id ? String(row.owner_user_id) : "",
      due_date: row?.due_date ?? "",
      source_domain: String(row?.source_domain ?? "AWP"),
      source_reference: String(row?.source_reference ?? ""),
      evidence_reference: row?.evidence_reference ?? "",
    });
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    const result = await command(
      `/constraints${selected ? `/${selected.id}` : ""}`,
      {
        ...draft,
        owner_user_id: draft.owner_user_id ? Number(draft.owner_user_id) : null,
        due_date: draft.due_date || null,
        reason,
      },
      selected?.version,
      selected ? "PUT" : "POST"
    );
    select(result as ExecutionConstraint);
  }
  const run = (path: string, payload: unknown) => {
    if (selected) void command(path, payload, selected.version).catch(() => undefined);
  };
  return (
    <section className="awpPanel">
      <h3>Execution Constraints</h3>
      <p>
        Condiciones de ejecución independientes de las restricciones P6 de Codes &amp; Constraints. Vencer la fecha no
        limpia un bloqueo ni cambia CPM.
      </p>
      <div className="awpTable">
        <table aria-label="Execution Constraints">
          <thead>
            <tr>
              <th>Código</th>
              <th>Tipo</th>
              <th>Título</th>
              <th>Bloquea</th>
              <th>Estado</th>
              <th>Vencimiento</th>
              <th>Detalle</th>
            </tr>
          </thead>
          <tbody>
            {data.constraints.map((row) => (
              <tr key={row.id}>
                <td>{row.code}</td>
                <td>{row.constraint_type}</td>
                <td>{row.title}</td>
                <td>{row.blocking ? "BLOCKING" : "NONBLOCKING"}</td>
                <td>{row.status}</td>
                <td>{row.due_date ?? "—"}</td>
                <td>
                  <button type="button" onClick={() => select(row)}>
                    Ver Constraint {row.code}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {can("constraint.raise") ? (
        <>
          <button type="button" onClick={() => select()}>
            Nueva Execution Constraint
          </button>
          <form className="awpForm" onSubmit={(e) => void save(e).catch(() => undefined)}>
            <NamedSelect
              label="Constraint type"
              value={draft.constraint_type}
              onChange={(value) => setDraft({ ...draft, constraint_type: value })}
              optional={false}
              options={constraintTypes
                .filter((value) => !configuredTypes || configuredTypes[value]?.enabled)
                .map((value) => ({ value, label: value }))}
            />
            {(["code", "title", "description", "source_domain", "source_reference", "evidence_reference"] as const).map(
              (key) => (
                <Field key={key} label={`Constraint ${key}`}>
                  <input
                    aria-label={`Constraint ${key}`}
                    required={key === "code" || key === "title"}
                    value={draft[key]}
                    onChange={(e) => setDraft({ ...draft, [key]: e.target.value })}
                  />
                </Field>
              )
            )}
            <Field label="Constraint blocking">
              <input
                aria-label="Constraint blocking"
                type="checkbox"
                checked={draft.blocking}
                onChange={(e) => setDraft({ ...draft, blocking: e.target.checked })}
              />
            </Field>
            <Field label="Constraint owner user ID">
              <input
                aria-label="Constraint owner user ID"
                type="number"
                min="1"
                value={draft.owner_user_id}
                onChange={(e) => setDraft({ ...draft, owner_user_id: e.target.value })}
              />
            </Field>
            <Field label="Constraint due date">
              <input
                aria-label="Constraint due date"
                type="date"
                value={draft.due_date}
                onChange={(e) => setDraft({ ...draft, due_date: e.target.value })}
              />
            </Field>
            <button type="submit" disabled={busy || reason.trim().length < 8}>
              {selected ? "Guardar Execution Constraint" : "Crear Execution Constraint"}
            </button>
          </form>
        </>
      ) : null}
      {selected ? (
        <>
          <h4>Constraint seleccionada · {selected.code}</h4>
          {can("constraint.clear") || can("constraint.waive") ? (
            <div className="awpForm">
              <NamedSelect
                label="Constraint transition"
                value={transition}
                onChange={setTransition}
                optional={false}
                options={["IN_PROGRESS", "CLEARED", ...(can("constraint.waive") ? ["WAIVED"] : []), "CANCELLED"].map(
                  (value) => ({ value, label: value })
                )}
              />
              <Field label="Constraint clearance evidence">
                <input
                  aria-label="Constraint clearance evidence"
                  value={evidence}
                  onChange={(e) => setEvidence(e.target.value)}
                />
              </Field>
              <Field label="Constraint waiver reference">
                <input
                  aria-label="Constraint waiver reference"
                  value={waiver}
                  onChange={(e) => setWaiver(e.target.value)}
                />
              </Field>
              <button
                disabled={busy || reason.trim().length < 8}
                type="button"
                onClick={() =>
                  run(`/constraints/${selected.id}/transition`, {
                    status: transition,
                    evidence_reference: evidence,
                    waiver_reference: waiver,
                    reason,
                  })
                }
              >
                Aplicar transición Constraint
              </button>
            </div>
          ) : null}
          {can("constraint.raise") ? (
            <form
              className="awpForm"
              onSubmit={(e) => {
                e.preventDefault();
                run(`/constraints/${selected.id}/mappings`, {
                  target_kind: kind,
                  target_id: kind === "ACTIVITY" ? null : Number(target),
                  schedule_version_id: kind === "ACTIVITY" ? Number(versionId) : null,
                  activity_external_id: kind === "ACTIVITY" ? activity : null,
                  action: "SET",
                  reason,
                });
              }}
            >
              <NamedSelect
                label="Constraint mapping kind"
                value={kind}
                onChange={(value) => {
                  setKind(value);
                  setTarget("");
                }}
                optional={false}
                options={["PACKAGE", "PLAN", "SCOPE", "ACTIVITY", "CWA"].map((value) => ({ value, label: value }))}
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
              <button type="submit" disabled={busy || reason.trim().length < 8}>
                Guardar Constraint mapping
              </button>
            </form>
          ) : null}
          <details open>
            <summary>Constraint evidence, history y vínculos</summary>
            <pre>
              {JSON.stringify(
                {
                  constraint: selected,
                  mappings: data.constraint_mappings.filter((row) => Number(row.constraint_id) === selected.id),
                },
                null,
                2
              )}
            </pre>
          </details>
        </>
      ) : null}
    </section>
  );
}
