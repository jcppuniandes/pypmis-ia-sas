import { useState, type FormEvent } from "react";
import { Evidence, Field, Input, Select } from "../progress-foundation/Fields";
import { isRow, positiveId, query, rows, text, useRead, versionOf, type Row, type Scope } from "./api";
import { encodeFields, type FieldSpec, type FormSpec, type FormValue, type Values } from "./formValues";

type FormEnvironment = Pick<Scope, "token" | "base" | "revision" | "profile">;

const initialValues = (fields: FieldSpec[]) =>
  Object.fromEntries(fields.map((field) => [field.key, field.initial ?? ""]));

export function ReadState({ error, loading, retry }: { error: string; loading: boolean; retry?: () => void }) {
  return error ? (
    <p className="progressError" role="alert">
      {error}{" "}
      {retry ? (
        <button type="button" onClick={retry}>
          Reintentar lectura
        </button>
      ) : null}
    </p>
  ) : loading ? (
    <p role="status">Consultando datos del proyecto…</p>
  ) : null;
}

function optionTitle(item: Row) {
  return (
    [
      item.code ?? item.contract_number ?? item.package_code ?? item.application_number,
      item.title ?? item.name,
      item.status,
    ]
      .map(text)
      .filter(Boolean)
      .join(" · ") || `#${text(item.id)}`
  );
}

function CollectionField({
  field,
  label,
  value,
  change,
  environment,
}: {
  field: FieldSpec;
  label: string;
  value: FormValue;
  change: (value: FormValue) => void;
  environment: FormEnvironment;
}) {
  const [manual, setManual] = useState(false);
  const lookup = useRead(environment.token, environment.base, field.collection ?? null, environment.revision);
  if (manual)
    return (
      <div className="contractSourceInline">
        <Input label={label} type="number" value={text(value)} onChange={change} required={field.required} />
        <button type="button" onClick={() => setManual(false)}>
          Buscar por registro
        </button>
      </div>
    );
  return (
    <div className="contractSourceInline">
      <Field label={label}>
        <select
          aria-label={label}
          value={text(value)}
          onChange={(e) => change(e.target.value)}
          required={field.required}
        >
          <option value="">{lookup.loading ? "Cargando…" : "Seleccionar"}</option>
          {rows(lookup.data).map((item) => (
            <option key={text(item.id)} value={text(item.id)}>
              {optionTitle(item)}
            </option>
          ))}
        </select>
      </Field>
      <button type="button" onClick={() => setManual(true)}>
        Introducir ID
      </button>
      <ReadState {...lookup} />
    </div>
  );
}

function DocumentField({
  label,
  field,
  value,
  change,
  environment,
}: {
  field: FieldSpec;
  label: string;
  value: FormValue;
  change: (value: FormValue) => void;
  environment: FormEnvironment;
}) {
  const lookup = useRead(environment.token, environment.base, "/document-targets", environment.revision);
  const current = isRow(value) ? [value] : Array.isArray(value) ? value : [];
  const identity = (row: Row) => `${text(row.document_id)}:${text(row.attachment_id)}`;
  const selected = current.map(identity);
  return (
    <div className="contractSourceInline">
      <Field label={label}>
        <select
          aria-label={label}
          multiple={field.multiple}
          value={field.multiple ? selected : (selected[0] ?? "")}
          required={field.required}
          onChange={(e) => {
            const values = Array.from(e.target.selectedOptions, (item) => item.value);
            const pins = rows(lookup.data)
              .filter((item) => values.includes(identity(item)))
              .map((item) => ({
                document_id: Number(item.document_id),
                attachment_id: Number(item.attachment_id),
                ...(text(item.sha256 ?? item.source_hash)
                  ? { source_hash: text(item.sha256 ?? item.source_hash) }
                  : {}),
              }));
            change(field.multiple ? pins : (pins[0] ?? ""));
          }}
        >
          {!field.multiple ? <option value="">Seleccionar adjunto</option> : null}
          {rows(lookup.data).map((row) => (
            <option key={identity(row)} value={identity(row)}>
              {text(row.document_number ?? row.document_id)} · rev. {text(row.document_revision ?? row.revision)} ·
              adjunto {text(row.attachment_id)}
            </option>
          ))}
        </select>
      </Field>
      <ReadState {...lookup} />
    </div>
  );
}

const procurementTypes = ["PACKAGE", "AWARD", "PURCHASE_ORDER", "PO_REVISION", "VENDOR"];

function ProcurementField({
  label,
  field,
  value,
  change,
  environment,
}: {
  label: string;
  field: FieldSpec;
  value: FormValue;
  change: (value: FormValue) => void;
  environment: FormEnvironment;
}) {
  const [kind, setKind] = useState("");
  const [identity, setIdentity] = useState("");
  const [packageId, setPackageId] = useState("");
  const [path, setPath] = useState<string | null>(null);
  const result = useRead(environment.token, environment.base, path, environment.revision);
  const record = isRow(result.data?.source) ? result.data.source : result.data;
  const sourceId = record?.source_id ?? record?.source_entity_id ?? record?.id;
  const sourceVersion = versionOf(record?.source_version ?? record?.version);
  const hash = text(record?.source_hash);
  const pin =
    positiveId(sourceId) && sourceVersion !== undefined && /^[a-f0-9]{64}$/.test(hash)
      ? {
          source_type: text(record?.source_type) || kind,
          source_id: Number(sourceId),
          source_version: sourceVersion,
          source_hash: hash,
          ...(kind === "VENDOR" && positiveId(packageId) ? { package_id: Number(packageId) } : {}),
        }
      : null;
  const pinned = isRow(value) ? [value] : Array.isArray(value) ? value : [];
  const changeInput = (setter: (value: string) => void) => (next: string) => {
    setter(next);
    setPath(null);
  };
  return (
    <fieldset className="contractPin">
      <legend>{label}</legend>
      <div className="progressForm">
        <Select
          label="Tipo de fuente Procurement"
          value={kind}
          onChange={changeInput(setKind)}
          values={procurementTypes}
        />
        <Input label="ID de fuente Procurement" value={identity} onChange={changeInput(setIdentity)} type="number" />
        {kind === "VENDOR" ? (
          <Input label="Paquete para proveedor" value={packageId} onChange={changeInput(setPackageId)} type="number" />
        ) : null}
        <button
          type="button"
          disabled={!kind || !positiveId(identity)}
          onClick={() =>
            setPath(
              query("/procurement-source", {
                source_type: kind,
                source_id: identity,
                package_id: kind === "VENDOR" ? packageId : undefined,
              })
            )
          }
        >
          Consultar fuente Procurement
        </button>
        <ReadState {...result} />
        {pin && !result.loading ? (
          <button
            type="button"
            onClick={() => {
              if (
                field.multiple &&
                pinned.some((item) => item.source_type === pin.source_type && item.source_id === pin.source_id)
              )
                return;
              change(field.multiple ? [...pinned, pin] : pin);
            }}
          >
            Fijar fuente Procurement
          </button>
        ) : null}
      </div>
      {pinned.map((item, index) => (
        <div key={`${text(item.source_type)}:${text(item.source_id)}`} className="contractPinBadge">
          <span>
            {text(item.source_type)} #{text(item.source_id)} · v{text(item.source_version)}
          </span>
          <button
            type="button"
            onClick={() => change(field.multiple ? pinned.filter((_, position) => index !== position) : "")}
          >
            Quitar referencia
          </button>
        </div>
      ))}
      {pinned.length ? <Evidence title="Huellas de fuentes seleccionadas" value={pinned} /> : null}
    </fieldset>
  );
}

function ProgressField({
  label,
  field,
  value,
  change,
  environment,
  values,
}: {
  label: string;
  field: FieldSpec;
  value: FormValue;
  change: (value: FormValue) => void;
  environment: FormEnvironment;
  values: Values;
}) {
  const period = text(values.period_id);
  const line = text(values.sov_line_id);
  const lookup = useRead(
    environment.token,
    environment.base,
    positiveId(period) && positiveId(line)
      ? query("/progress-sources", { period_id: period, sov_line_id: line })
      : null,
    environment.revision
  );
  const pin = isRow(value) ? value : null;
  return (
    <div className="contractSourceInline">
      <Field label={label}>
        <select
          aria-label={label}
          required={field.required}
          value={text(pin?.measurement_id)}
          onChange={(e) => {
            const item = rows(lookup.data).find((row) => text(row.measurement_id) === e.target.value);
            const version = versionOf(item?.version);
            change(
              item && version !== undefined && /^[a-f0-9]{64}$/.test(text(item.source_hash))
                ? {
                    measurement_id: Number(item.measurement_id),
                    version,
                    source_hash: text(item.source_hash),
                  }
                : ""
            );
          }}
        >
          <option value="">
            {positiveId(period) && positiveId(line) ? "Seleccionar medición aprobada" : "Indique periodo y línea SOV"}
          </option>
          {rows(lookup.data).map((item) => (
            <option key={text(item.measurement_id)} value={text(item.measurement_id)}>
              #{text(item.measurement_id)} · {text(item.quantity)} {text(item.unit)} · v{text(item.version)}
            </option>
          ))}
        </select>
      </Field>
      <ReadState {...lookup} />
    </div>
  );
}

function FormField({
  field,
  value,
  change,
  environment,
  values,
  ordinal,
}: {
  field: FieldSpec;
  value: FormValue;
  change: (value: FormValue) => void;
  environment: FormEnvironment;
  values: Values;
  ordinal?: number;
}) {
  const label = ordinal === undefined ? field.label : `${field.label} ${ordinal}`;
  const control = { field, label, value, change, environment };
  if (field.collection) return <CollectionField {...control} />;
  if (field.kind === "document") return <DocumentField {...control} />;
  if (field.kind === "source") return <ProcurementField {...control} />;
  if (field.kind === "progress") return <ProgressField {...control} values={values} />;
  const catalog = field.catalog ? environment.profile?.[field.catalog] : undefined;
  const valuesList = Array.isArray(catalog)
    ? catalog.map((item) => (isRow(item) ? text(item.code) : text(item))).filter(Boolean)
    : isRow(catalog)
      ? Object.keys(catalog)
      : field.choices;
  if (valuesList?.length)
    return <Select label={label} value={text(value)} onChange={change} values={valuesList} required={field.required} />;
  if (field.kind === "notes" || field.kind === "json") {
    return (
      <Field label={label}>
        <textarea
          aria-label={label}
          value={text(value)}
          required={field.required}
          onChange={(e) => change(e.target.value)}
        />
        {field.help ? <small>{field.help}</small> : null}
      </Field>
    );
  }
  return (
    <Input
      label={label}
      value={text(value)}
      onChange={change}
      required={field.required}
      type={field.kind === "date" ? "date" : field.kind === "id" || field.kind === "integer" ? "number" : "text"}
    />
  );
}

export function CommandForm({
  label,
  spec,
  environment,
  busy,
  submit,
}: {
  label: string;
  spec: FormSpec;
  environment: FormEnvironment;
  busy: boolean;
  submit: (body: Row) => Promise<Row | null>;
}) {
  const fields = spec.fields ?? [];
  const lines = spec.lines;
  const [values, setValues] = useState<Values>(() => initialValues(fields));
  const [lineValues, setLineValues] = useState<Values[]>(() =>
    lines && !lines.optional ? [initialValues(lines.fields)] : []
  );
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  const update = (key: string, value: FormValue) => {
    setValues((old) => ({ ...old, [key]: value }));
    if (key === "period_id") setLineValues((old) => old.map((line) => ({ ...line, progress: "" })));
  };
  async function save(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const body: Row = { ...encodeFields(fields, values), reason: reason.trim() };
      if (lines) body[lines.key] = lineValues.map((line) => encodeFields(lines.fields, line));
      if (await submit(body)) {
        setValues(initialValues(fields));
        setReason("");
        setLineValues(lines && !lines.optional ? [initialValues(lines.fields)] : []);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Datos inválidos.");
    }
  }
  return (
    <form aria-label={label} onSubmit={(event) => void save(event)}>
      <fieldset className="progressForm contractFieldset" disabled={busy}>
        {fields.map((field) => (
          <FormField
            key={field.key}
            field={field}
            value={values[field.key] ?? ""}
            change={(value) => update(field.key, value)}
            environment={environment}
            values={values}
          />
        ))}
        {lines ? (
          <div className="progressWide">
            {lineValues.map((line, index) => (
              <fieldset className="contractPin" key={index}>
                <legend>
                  {lines.label} {index + 1}
                </legend>
                <div className="progressForm">
                  {lines.fields.map((field) => (
                    <FormField
                      key={field.key}
                      ordinal={index + 1}
                      field={field}
                      environment={environment}
                      values={{ ...values, ...line }}
                      value={line[field.key] ?? ""}
                      change={(value) =>
                        setLineValues((old) =>
                          old.map((item, position) =>
                            position === index
                              ? {
                                  ...item,
                                  [field.key]: value,
                                  ...(field.key === "sov_line_id" ? { progress: "" } : {}),
                                }
                              : item
                          )
                        )
                      }
                    />
                  ))}
                  <button
                    type="button"
                    disabled={!lines.optional && lineValues.length === 1}
                    onClick={() => setLineValues((old) => old.filter((_, position) => position !== index))}
                  >
                    Quitar línea {index + 1}
                  </button>
                </div>
              </fieldset>
            ))}
            <button type="button" onClick={() => setLineValues((old) => [...old, initialValues(lines.fields)])}>
              Agregar {lines.label.toLowerCase()}
            </button>
          </div>
        ) : null}
        <Field label="Motivo contractual">
          <input
            aria-label="Motivo contractual"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
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
