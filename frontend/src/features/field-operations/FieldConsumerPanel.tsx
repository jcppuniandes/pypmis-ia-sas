import { useState, type FormEvent } from "react";
import { Evidence, Facts, Input, Records, Select } from "../progress-foundation/Fields";
import { FieldCommandForm, ReadState, type FieldSpec } from "./FieldForms";
import { isRow, positiveId, query, rows, text, useCommands, useRead, versionOf, type Row } from "./api";

type Domain = "progress" | "awp" | "cost" | "contracts" | "schedule";
const kinds: Record<Domain, string[]> = {
  progress: ["PRODUCTION"],
  awp: ["CONSTRAINT"],
  cost: ["LABOR", "EQUIPMENT", "PRODUCTION"],
  contracts: ["EVENT", "INSTRUCTION", "DAILY_REPORT", "PRODUCTION"],
  schedule: ["WORKFRONT", "PRODUCTION", "EVENT"],
};
const duties: Partial<Record<Domain, string>> = {
  progress: "progress.capture",
  awp: "awp.constraint.raise",
  cost: "cost.mapping.edit",
};
const idField = (key: string, label: string): FieldSpec => ({ key, label, kind: "id", required: true });
const adopting = { key: "decision", values: ["ADOPT", "PARTIAL_ADOPT"] };
const fields: Partial<Record<Domain, FieldSpec[]>> = {
  progress: [
    { key: "decision", label: "Decisión Progress", choices: ["ADOPT", "PARTIAL_ADOPT", "REJECT"], required: true },
    { key: "quantity", label: "Cantidad a adoptar", kind: "decimal", required: true, when: adopting },
    { ...idField("period_id", "Período de Progress"), when: adopting },
    { key: "measurement_code", label: "Código de medición borrador", required: true, when: adopting },
  ],
  awp: [
    { key: "decision", label: "Decisión AWP", choices: ["ADOPT", "REJECT"], required: true },
    { key: "constraint_type", label: "Tipo de restricción AWP", required: true, when: adopting },
    { key: "constraint_code", label: "Código de restricción AWP", required: true, when: adopting },
    {
      key: "blocking",
      label: "Restricción bloqueante",
      kind: "boolean",
      required: true,
      initial: "true",
      when: adopting,
    },
  ],
  cost: [
    { key: "decision", label: "Decisión Cost", choices: ["ADOPT", "REJECT"], required: true },
    { ...idField("cbs_id", "CBS de Cost"), when: adopting },
    { ...idField("cost_code_id", "Cost Code"), when: adopting },
    { ...idField("control_account_id", "Control Account"), when: adopting },
  ],
};

export default function FieldConsumerPanel({
  token,
  workspaceId,
  readOnly = false,
  initialDomain = "progress",
}: {
  token: string;
  workspaceId: number;
  readOnly?: boolean;
  initialDomain?: Domain;
}) {
  const [domain, setDomain] = useState<Domain>(initialDomain);
  const [kind, setKind] = useState(kinds[initialDomain][0]);
  const [identity, setIdentity] = useState("");
  const [selected, setSelected] = useState<{ kind: string; id: string } | null>(null);
  const base = `/api/v1/${domain}/projects/${workspaceId}/field-adoptions`;
  const commands = useCommands(token, base, readOnly);
  const path = selected ? query("/lookup", { source_entity_type: selected.kind, source_entity_id: selected.id }) : null;
  const source = useRead(token, base, path, commands.revision);
  const history = useRead(token, base, "", commands.revision);
  const row = isRow(source.data?.source) ? source.data.source : source.data;
  const version = versionOf(source.data?.version, true);
  const duty = duties[domain];
  const allowed = source.data?.consumer_allowed_actions;
  const canDecide =
    !readOnly &&
    duty &&
    Array.isArray(allowed) &&
    allowed.some((value) => value === duty || value === duty.slice(duty.indexOf(".") + 1));
  const pinReady =
    positiveId(row?.source_entity_id) &&
    versionOf(row?.source_version) !== undefined &&
    /^[a-f0-9]{64}$/.test(text(row?.source_hash)) &&
    Boolean(text(row?.observed_at));
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!positiveId(identity)) return;
    if (selected?.kind === kind && selected.id === identity) commands.reload();
    setSelected({ kind, id: identity });
  };
  return (
    <section className="progressPanel fieldOperations" aria-label="Field evidence consumer">
      <h2>Adopción de evidencia de campo</h2>
      <p className="fieldBoundary">
        Progress crea una medición borrador por decisión propia. AWP adopta una restricción explícita. Cost solo
        conserva evidencia; los hechos de campo no reconocen costos ni certificaciones.
      </p>
      <form className="progressForm" onSubmit={submit}>
        <Select
          label="Dominio consumidor"
          value={domain}
          values={["progress", "awp", "cost", "contracts", "schedule"]}
          onChange={(value) => {
            const next = value as Domain;
            if (!kinds[next]) return;
            setDomain(next);
            setKind(kinds[next][0]);
            setSelected(null);
          }}
          required
        />
        <Select
          label="Tipo de evidencia de campo"
          value={kind}
          values={kinds[domain]}
          onChange={(value) => {
            setKind(value);
            setSelected(null);
          }}
          required
        />
        <Input label="Evidencia de campo ID" value={identity} type="number" onChange={setIdentity} required />
        <button type="submit">Consultar origen de campo</button>
      </form>
      <ReadState {...source} retry={commands.reload} />
      {commands.error ? (
        <p role="alert" className="progressError">
          {commands.error}
        </p>
      ) : null}
      {commands.message ? <p role="status">{commands.message}</p> : null}
      {row ? (
        <>
          <Facts
            values={[
              ["Dominio", row.source_domain],
              ["Entidad", row.source_entity_type],
              ["ID", row.source_entity_id],
              ["Versión", row.source_version],
              ["Decisión", source.data?.consumer_decision ?? source.data?.decision ?? source.data?.consumer_status],
              ["Cantidad", row.quantity ?? row.hours ?? (isRow(row.facts) ? row.facts.quantity : undefined)],
              ["Ya adoptada", source.data?.previously_adopted_quantity],
              ["Disponible", source.data?.remaining_quantity],
            ]}
          />
          <Evidence title="Origen de campo y huella verificada" value={source.data} />
        </>
      ) : null}
      {row && canDecide && pinReady && version !== undefined && fields[domain] ? (
        <FieldCommandForm
          key={`${domain}:${selected?.id}:${row.source_hash}`}
          label={`Registrar decisión ${domain.toUpperCase()}`}
          spec={{ fields: fields[domain] }}
          environment={{ token, base, profile: null, revision: commands.revision }}
          busy={commands.busy || source.loading}
          submit={async (body: Row) =>
            commands.command(
              "",
              {
                ...body,
                source_entity_type: row.source_entity_type,
                source_entity_id: row.source_entity_id,
                source_version: row.source_version,
                source_hash: row.source_hash,
                observed_at: row.observed_at,
              },
              version
            )
          }
        />
      ) : null}
      <ReadState {...history} retry={commands.reload} />
      {history.data ? (
        <Records
          label="Decisiones sobre evidencia de campo"
          items={rows(history.data)}
          columns={[
            ["id", "ID"],
            ["source_entity_type", "Origen"],
            ["source_entity_id", "Hecho"],
            ["source_version", "Versión fuente"],
            ["decision", "Decisión"],
            ["quantity", "Cantidad"],
            ["linked_entity_id", "Registro nativo"],
            ["created_by", "Actor"],
          ]}
        />
      ) : null}
    </section>
  );
}
