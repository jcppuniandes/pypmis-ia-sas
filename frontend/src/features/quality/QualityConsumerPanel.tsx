import { useState, type FormEvent } from "react";
import { Evidence, Facts, Input, Records, Select } from "../progress-foundation/Fields";
import { FieldCommandForm, ReadState } from "../field-operations/FieldForms";
import type { FieldSpec } from "../field-operations/formValues";
import { isRow, positiveId, query, rows, text, useCommands, useRead, versionOf, type Row } from "./api";

type Domain = "progress" | "awp" | "cost" | "contracts" | "field-operations" | "schedule";
const types: Record<Domain, string[]> = {
  progress: ["ACCEPTANCE"],
  awp: ["READINESS", "ACCEPTANCE", "NCR"],
  cost: ["NCR", "ACCEPTANCE", "INSPECTION", "TEST"],
  contracts: ["NCR", "ACCEPTANCE", "INSPECTION", "TEST"],
  "field-operations": ["ACCEPTANCE", "READINESS"],
  schedule: ["NCR", "ACCEPTANCE", "READINESS"],
};
const duties: Partial<Record<Domain, string[]>> = {
  progress: ["progress.capture"],
  awp: ["awp.readiness.assess"],
  cost: ["cost.mapping.edit"],
};
const fields: Partial<Record<Domain, FieldSpec[]>> = {
  progress: [{ key: "measurement_id", label: "Medición Progress pendiente ID", kind: "id", required: true }],
  awp: [{ key: "work_package_id", label: "Paquete AWP a evaluar ID", kind: "id", required: true }],
  cost: [
    { key: "cbs_id", label: "CBS de Cost", kind: "id", required: false },
    { key: "cost_code_id", label: "Cost Code", kind: "id", required: false },
    { key: "control_account_id", label: "Control Account", kind: "id", required: false },
  ],
};
export default function QualityConsumerPanel({
  token,
  workspaceId,
  initialDomain = "progress",
  readOnly = false,
  onCommitted,
}: {
  token: string;
  workspaceId: number;
  initialDomain?: Domain;
  readOnly?: boolean;
  onCommitted?: () => void | Promise<unknown>;
}) {
  const [domain, setDomain] = useState<Domain>(initialDomain);
  const [kind, setKind] = useState(types[initialDomain][0]);
  const [identity, setIdentity] = useState("");
  const [selected, setSelected] = useState<{ kind: string; id: string } | null>(null);
  const [notice, setNotice] = useState("");
  const base = `/api/v1/${domain}/projects/${workspaceId}/quality-adoptions`;
  const commands = useCommands(token, base, readOnly);
  const lookup = useRead(
    token,
    base,
    selected ? query("/lookup", { source_entity_type: selected.kind, source_entity_id: selected.id }) : null,
    commands.revision
  );
  const history = useRead(token, base, "", commands.revision);
  const source = isRow(lookup.data?.source) ? lookup.data.source : lookup.data;
  const version = versionOf(lookup.data?.version, true);
  const allowed = lookup.data?.consumer_allowed_actions;
  const canDecide =
    !readOnly &&
    duties[domain] &&
    Array.isArray(allowed) &&
    allowed.some((entry) => duties[domain]?.includes(text(entry)));
  const pinned =
    positiveId(source?.source_entity_id) &&
    versionOf(source?.source_version) !== undefined &&
    /^[a-f0-9]{64}$/.test(text(source?.source_hash)) &&
    Boolean(text(source?.observed_at));
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!positiveId(identity)) return;
    if (selected?.kind === kind && selected.id === identity) commands.reload();
    setSelected({ kind, id: identity });
  };
  return (
    <section className="progressPanel qualityManager" aria-label="Quality evidence consumer">
      <h2>Evidencia Quality en el dominio consumidor</h2>
      <p className="qualityBoundary">
        Quality decide cumplimiento. Progress decide avance, AWP decide restricciones y paquetes, Contracts decide
        consecuencias contractuales. Consultar o adoptar evidencia no crea costos, pagos ni fechas P6.
      </p>
      <form className="progressForm" onSubmit={submit}>
        <Select
          label="Dominio consumidor Quality"
          value={domain}
          values={Object.keys(types)}
          onChange={(value) => {
            const next = value as Domain;
            if (!types[next]) return;
            setDomain(next);
            setKind(types[next][0]);
            setSelected(null);
            setNotice("");
          }}
          required
        />
        <Select
          label="Tipo de evidencia Quality"
          value={kind}
          values={types[domain]}
          onChange={(value) => {
            setKind(value);
            setSelected(null);
          }}
          required
        />
        <Input label="Evidencia Quality ID" type="number" value={identity} onChange={setIdentity} required />
        <button type="submit">Consultar evidencia Quality</button>
      </form>
      <ReadState {...lookup} retry={commands.reload} />
      {commands.error ? (
        <p role="alert" className="progressError">
          {commands.error}
        </p>
      ) : null}
      {commands.message ? <p role="status">{commands.message}</p> : null}
      {notice ? <p role="status">{notice}</p> : null}
      {source ? (
        <>
          <Facts
            values={[
              ["Dominio", source.source_domain],
              ["Entidad", source.source_entity_type],
              ["ID", source.source_entity_id],
              ["Versión", source.source_version],
              ["Estado consumidor", lookup.data?.consumer_status ?? lookup.data?.decision],
            ]}
          />
          <Evidence title="Quality y fuentes fijadas verificadas" value={lookup.data} />
        </>
      ) : null}
      {source && canDecide && pinned && version !== undefined ? (
        <FieldCommandForm
          key={`${domain}:${selected?.id}:${source.source_hash}`}
          label={`Registrar decisión Quality ${domain.toUpperCase()}`}
          spec={{
            fields: [
              {
                key: "decision",
                label: "Decisión sobre evidencia Quality",
                choices: ["ADOPT", "REJECT", "RECONCILE"],
                required: true,
              },
              ...(fields[domain] ?? []),
            ],
          }}
          environment={{ token, base, profile: null, revision: commands.revision }}
          busy={commands.busy || lookup.loading}
          submit={async (body: Row) => {
            const result = await commands.command(
              "",
              {
                ...body,
                source_entity_type: source.source_entity_type,
                source_entity_id: source.source_entity_id,
                source_version: source.source_version,
                source_hash: source.source_hash,
                observed_at: source.observed_at,
              },
              version
            );
            if (result) {
              setNotice("");
              try {
                await onCommitted?.();
              } catch {
                setNotice("Decisión guardada. No se pudo refrescar el resumen; use Actualizar en el módulo nativo.");
              }
            }
            return result;
          }}
        />
      ) : null}
      <ReadState {...history} retry={commands.reload} />
      {history.data ? (
        <Records
          label="Decisiones consumidoras de Quality"
          items={rows(history.data)}
          columns={[
            ["id", "ID"],
            ["source_entity_type", "Entidad"],
            ["source_entity_id", "Fuente"],
            ["source_version", "Versión"],
            ["decision", "Decisión"],
            ["linked_entity_id", "Objeto nativo"],
            ["created_by", "Actor"],
          ]}
        />
      ) : null}
    </section>
  );
}
