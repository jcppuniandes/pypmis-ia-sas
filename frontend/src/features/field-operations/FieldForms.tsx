import { useState, type FormEvent } from "react";
import { Evidence, Field, Input, Select } from "../progress-foundation/Fields";
import { isRow, positiveId, query, rows, text, useRead, type Row, type Scope } from "./api";
import { encodeFields, type FieldSpec, type FormSpec, type FormValue as Value } from "./formValues";
export type { FieldSpec, FormSpec } from "./formValues";

type Environment = Pick<Scope, "token" | "base" | "profile" | "revision">;

export function ReadState({ error, loading, retry }: { error: string; loading: boolean; retry?: () => void }) {
  return error ? (
    <p role="alert" className="progressError">
      {error}{" "}
      {retry ? (
        <button type="button" onClick={retry}>
          Reintentar lectura
        </button>
      ) : null}
    </p>
  ) : loading ? (
    <p role="status">Consultando hechos de campo…</p>
  ) : null;
}

function ChoiceField({
  field,
  value,
  change,
  environment,
}: {
  field: FieldSpec;
  value: Value;
  change: (value: Value) => void;
  environment: Environment;
}) {
  const [manual, setManual] = useState(false);
  const source = useRead(environment.token, environment.base, field.collection ?? null, environment.revision);
  const identity = (row: Row) => text(row.id ?? row.target_id ?? row.source_entity_id);
  if (manual)
    return (
      <div className="fieldControl">
        <Input label={field.label} type="number" value={text(value)} onChange={change} required={field.required} />
        <button type="button" onClick={() => setManual(false)}>
          Buscar registro
        </button>
      </div>
    );
  return (
    <div className="fieldControl">
      <Field label={field.label}>
        <select
          aria-label={field.label}
          required={field.required}
          value={text(value)}
          onChange={(event) => change(event.target.value)}
        >
          <option value="">{source.loading ? "Cargando…" : "Seleccionar"}</option>
          {rows(source.data).map((row) => (
            <option key={identity(row)} value={identity(row)}>
              {[
                row.code ?? row.workfront_code ?? row.shift_code ?? row.crew_code,
                row.title ?? row.name ?? row.description,
                row.status,
              ]
                .map(text)
                .filter(Boolean)
                .join(" · ") || `#${identity(row)}`}
            </option>
          ))}
        </select>
      </Field>
      <button type="button" onClick={() => setManual(true)}>
        Introducir ID
      </button>
      <ReadState {...source} />
    </div>
  );
}

function DocumentField({
  field,
  value,
  change,
  environment,
}: {
  field: FieldSpec;
  value: Value;
  change: (value: Value) => void;
  environment: Environment;
}) {
  const source = useRead(environment.token, environment.base, "/document-targets", environment.revision);
  const choices = rows(source.data);
  const identity = (row: Row) => `${text(row.document_id)}:${text(row.attachment_id)}`;
  const selected = isRow(value) ? [identity(value)] : Array.isArray(value) ? value.map(identity) : [];
  return (
    <div className="fieldWide">
      <Field label={field.label}>
        <select
          aria-label={field.label}
          multiple={field.multiple}
          value={field.multiple ? selected : (selected[0] ?? "")}
          required={field.required}
          onChange={(event) => {
            const selectedIds = Array.from(event.target.selectedOptions, (item) => item.value);
            const pins = choices
              .filter((row) => selectedIds.includes(identity(row)))
              .map((row) => ({
                document_id: Number(row.document_id),
                attachment_id: Number(row.attachment_id),
                ...(text(row.source_hash ?? row.sha256) ? { source_hash: text(row.source_hash ?? row.sha256) } : {}),
              }));
            change(field.multiple ? pins : (pins[0] ?? ""));
          }}
        >
          {!field.multiple ? <option value="">Seleccionar evidencia CDE</option> : null}
          {choices.map((row) => (
            <option
              key={`${text(row.document_id)}:${text(row.attachment_id)}`}
              value={`${text(row.document_id)}:${text(row.attachment_id)}`}
            >
              {text(row.document_number ?? row.document_id)} · rev {text(row.document_revision ?? row.revision)} ·
              adjunto {text(row.attachment_id)}
            </option>
          ))}
        </select>
      </Field>
      <ReadState {...source} />
    </div>
  );
}

function SourcePinField({
  field,
  value,
  change,
  environment,
}: {
  field: FieldSpec;
  value: Value;
  change: (value: Value) => void;
  environment: Environment;
}) {
  const [kind, setKind] = useState(field.sourceTypes?.[0] ?? "");
  const [identity, setIdentity] = useState("");
  const [path, setPath] = useState<string | null>(null);
  const lookup = useRead(environment.token, environment.base, path, environment.revision);
  const source = isRow(lookup.data?.source) ? lookup.data.source : lookup.data;
  const pin =
    source &&
    positiveId(source.source_id ?? source.source_entity_id) &&
    source.source_version &&
    /^[a-f0-9]{64}$/.test(text(source.source_hash))
      ? {
          source_type: text(source.source_type ?? source.source_entity_type) || kind,
          source_id: Number(source.source_id ?? source.source_entity_id),
          source_version: Number(source.source_version),
          source_hash: text(source.source_hash),
        }
      : null;
  return (
    <fieldset className="fieldWide fieldReference">
      <legend>{field.label}</legend>
      <Select
        label={`Tipo ${field.label}`}
        value={kind}
        onChange={(next) => {
          setKind(next);
          change("");
          setPath(null);
        }}
        values={field.sourceTypes ?? []}
      />
      <Input
        label={`ID ${field.label}`}
        type="number"
        value={identity}
        onChange={(next) => {
          setIdentity(next);
          change("");
          setPath(null);
        }}
      />
      <button
        type="button"
        disabled={!positiveId(identity) || !kind}
        onClick={() => setPath(query("/source", { source_type: kind, source_id: identity }))}
      >
        Consultar {field.label}
      </button>
      <ReadState {...lookup} />
      {pin ? (
        <>
          <Evidence title="Referencia vigente de origen" value={lookup.data} />
          <button type="button" onClick={() => change(pin)}>
            Usar {field.label}
          </button>
        </>
      ) : null}
      {isRow(value) ? (
        <p>
          Referencia fijada: {text(value.source_type)} #{text(value.source_id)} · v{text(value.source_version)}
        </p>
      ) : null}
    </fieldset>
  );
}

function ReferenceField({
  field,
  value,
  change,
  environment,
}: {
  field: FieldSpec;
  value: Value;
  change: (value: Value) => void;
  environment: Environment;
}) {
  const [kind, setKind] = useState(field.targetKinds?.[0] ?? "SCOPE");
  const lookup = useRead(
    environment.token,
    environment.base,
    query("/reference-targets", { target_kind: kind, limit: 100 }),
    environment.revision
  );
  return (
    <fieldset className="fieldWide fieldReference">
      <legend>{field.label}</legend>
      <Select
        label={`Clase ${field.label}`}
        value={kind}
        values={field.targetKinds ?? ["SCOPE", "CWA", "GEOGRAPHIC_WORKSPACE"]}
        onChange={(next) => {
          setKind(next);
          change("");
        }}
        required={field.required}
      />
      <Field label={field.label}>
        <select
          aria-label={field.label}
          value={isRow(value) ? text(value.target_id) : ""}
          required={field.required}
          onChange={(event) => {
            const row = rows(lookup.data).find((item) => text(item.id ?? item.target_id) === event.target.value);
            change(row ? { target_kind: kind, target_id: Number(row.id ?? row.target_id) } : "");
          }}
        >
          <option value="">Seleccionar identidad canónica</option>
          {rows(lookup.data).map((row) => (
            <option key={text(row.id ?? row.target_id)} value={text(row.id ?? row.target_id)}>
              {[row.code, row.name ?? row.title, row.status].map(text).filter(Boolean).join(" · ") ||
                `#${text(row.id ?? row.target_id)}`}
            </option>
          ))}
        </select>
      </Field>
      <ReadState {...lookup} />
    </fieldset>
  );
}

function Control({
  field,
  value,
  change,
  environment,
}: {
  field: FieldSpec;
  value: Value;
  change: (value: Value) => void;
  environment: Environment;
}) {
  if (field.collection) return <ChoiceField {...{ field, value, change, environment }} />;
  if (field.kind === "document") return <DocumentField {...{ field, value, change, environment }} />;
  if (field.kind === "pin") return <SourcePinField {...{ field, value, change, environment }} />;
  if (field.kind === "reference") return <ReferenceField {...{ field, value, change, environment }} />;
  const catalog = field.catalog ? environment.profile?.[field.catalog] : undefined;
  const values = Array.isArray(catalog)
    ? catalog.map((item) => (isRow(item) ? text(item.code) : text(item))).filter(Boolean)
    : isRow(catalog)
      ? Object.keys(catalog)
      : field.choices;
  if (values?.length)
    return (
      <Select label={field.label} value={text(value)} onChange={change} values={values} required={field.required} />
    );
  if (field.kind === "boolean")
    return (
      <Select
        label={field.label}
        value={text(value)}
        onChange={change}
        values={["true", "false"]}
        required={field.required}
      />
    );
  if (["json", "notes"].includes(field.kind ?? ""))
    return (
      <Field label={field.label}>
        <textarea
          aria-label={field.label}
          value={text(value)}
          required={field.required}
          onChange={(event) => change(event.target.value)}
        />
        {field.help ? <small>{field.help}</small> : null}
      </Field>
    );
  const type =
    field.kind === "datetime"
      ? "datetime-local"
      : field.kind === "date"
        ? "date"
        : field.kind === "time"
          ? "time"
          : ["id", "integer"].includes(field.kind ?? "")
            ? "number"
            : "text";
  return <Input label={field.label} type={type} value={text(value)} required={field.required} onChange={change} />;
}

export function FieldCommandForm({
  label,
  spec,
  environment,
  busy,
  submit,
}: {
  label: string;
  spec: FormSpec;
  environment: Environment;
  busy: boolean;
  submit: (body: Row) => Promise<Row | null>;
}) {
  const fields = spec.fields ?? [];
  const initial = () => Object.fromEntries(fields.map((field) => [field.key, field.initial ?? ""]));
  const [values, setValues] = useState<Record<string, Value>>(initial);
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const activeFields = fields.filter(
    (field) => !field.when || field.when.values.includes(text(values[field.when.key]))
  );
  async function save(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      if (await submit({ ...encodeFields(activeFields, values), ...spec.body, reason: reason.trim() })) {
        setValues(initial());
        setReason("");
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Datos inválidos.");
    }
  }
  return (
    <form aria-label={label} onSubmit={(event) => void save(event)}>
      <fieldset className="progressForm fieldReference" disabled={busy}>
        {activeFields.map((field) => (
          <Control
            key={field.key}
            field={field}
            value={values[field.key] ?? ""}
            change={(value) => setValues((old) => ({ ...old, [field.key]: value }))}
            environment={environment}
          />
        ))}
        <Field label="Motivo operacional">
          <input
            aria-label="Motivo operacional"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            minLength={8}
            maxLength={1000}
            required
          />
        </Field>
        {error ? (
          <p role="alert" className="progressError">
            {error}
          </p>
        ) : null}
        <button type="submit">{label}</button>
      </fieldset>
    </form>
  );
}
