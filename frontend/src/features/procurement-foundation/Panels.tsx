import { useState, type FormEvent } from "react";
import { Evidence, Facts, Field, Input, Records, Select } from "../progress-foundation/Fields";
import {
  isRow,
  permission,
  query,
  rows,
  text,
  useProcurementRead,
  version,
  type ProcurementRow,
  type useProcurementCommands,
} from "./api";
import type { EntitySpec, FieldSpec, FormSpec } from "./views";

export type ProcurementScope = ReturnType<typeof useProcurementCommands> & {
  token: string;
  base: string;
  profile: ProcurementRow | null;
  can: (action: string) => boolean;
};

type Values = Record<string, string>;
const defaults = (fields: FieldSpec[]) => Object.fromEntries(fields.map((field) => [field.key, field.initial ?? ""]));

function encodeFields(fields: FieldSpec[], values: Values): ProcurementRow {
  const result: ProcurementRow = {};
  for (const field of fields) {
    const value = values[field.key]?.trim() ?? "";
    if (field.type === "checkbox") {
      result[field.key] = value === "true";
      continue;
    }
    if (!value) {
      if (field.required) throw new Error(`Complete ${field.label}.`);
      continue;
    }
    if (field.type === "number") {
      const number = Number(value);
      if (!Number.isFinite(number)) throw new Error(`${field.label} debe ser numérico.`);
      result[field.key] = number;
    } else if (field.type === "json") {
      try {
        result[field.key] = JSON.parse(value) as unknown;
      } catch {
        throw new Error(`${field.label}: JSON inválido.`);
      }
    } else if (field.type === "ids") {
      const ids = value.split(",").map((entry) => Number(entry.trim()));
      if (ids.some((entry) => !Number.isSafeInteger(entry) || entry < 1))
        throw new Error("Use IDs positivos separados por coma.");
      result[field.key] = ids;
    } else {
      result[field.key] = field.type === "datetime-local" && value.length === 16 ? `${value}:00Z` : value;
    }
  }
  return result;
}

function FormField({
  spec,
  value,
  update,
  profile,
  suffix,
}: {
  spec: FieldSpec;
  value: string;
  update: (value: string) => void;
  profile: ProcurementRow | null;
  suffix?: string;
}) {
  const label = suffix ? `${spec.label} ${suffix}` : spec.label;
  const list = spec.catalog ? profile?.[spec.catalog] : undefined;
  const options = Array.isArray(list)
    ? list.map((entry) => (isRow(entry) ? text(entry.code) : text(entry))).filter(Boolean)
    : spec.choices;
  if (options?.length) {
    return <Select label={label} value={value} onChange={update} values={options} required={spec.required} />;
  }
  if (spec.type === "checkbox") {
    return (
      <label className="progressCheck">
        <input type="checkbox" checked={value === "true"} onChange={(e) => update(String(e.target.checked))} />
        {label}
      </label>
    );
  }
  if (spec.type === "textarea" || spec.type === "json") {
    return (
      <Field label={label}>
        <textarea aria-label={label} value={value} onChange={(e) => update(e.target.value)} required={spec.required} />
        {spec.help ? <small>{spec.help}</small> : null}
      </Field>
    );
  }
  return (
    <Input
      label={label}
      value={value}
      onChange={update}
      type={spec.type === "ids" ? undefined : spec.type}
      required={spec.required}
    />
  );
}

export function CommandForm({
  spec,
  label,
  busy,
  profile,
  submit,
}: {
  spec: FormSpec;
  label: string;
  busy: boolean;
  profile: ProcurementRow | null;
  submit: (body: ProcurementRow) => Promise<ProcurementRow | null>;
}) {
  const fields = spec.fields ?? [];
  const lines = spec.lines;
  const [values, setValues] = useState<Values>(() => defaults(fields));
  const [lineValues, setLineValues] = useState<Values[]>(() =>
    lines && !lines.optional ? [defaults(lines.fields)] : []
  );
  const [reason, setReason] = useState("");
  const [error, setError] = useState("");
  async function save(event: FormEvent) {
    event.preventDefault();
    setError("");
    try {
      const body = { ...encodeFields(fields, values), reason: reason.trim() } as ProcurementRow;
      if (lines) body[lines.key] = lineValues.map((line) => encodeFields(lines.fields, line));
      if (await submit(body)) {
        setValues(defaults(fields));
        setReason("");
        setLineValues(lines && !lines.optional ? [defaults(lines.fields)] : []);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Datos inválidos.");
    }
  }
  return (
    <form aria-label={label} onSubmit={(event) => void save(event)}>
      <fieldset className="progressForm procurementFieldset" disabled={busy}>
        {fields.map((field) => (
          <FormField
            key={field.key}
            spec={field}
            value={values[field.key] ?? ""}
            update={(value) => setValues((current) => ({ ...current, [field.key]: value }))}
            profile={profile}
          />
        ))}
        {lines ? (
          <div className="progressWide">
            {lineValues.map((line, index) => (
              <fieldset className="procurementLine" key={index}>
                <legend>
                  {lines.label} {index + 1}
                </legend>
                <div className="progressForm">
                  {lines.fields.map((field) => (
                    <FormField
                      key={field.key}
                      spec={field}
                      value={line[field.key] ?? ""}
                      suffix={String(index + 1)}
                      update={(value) =>
                        setLineValues((current) =>
                          current.map((entry, position) =>
                            position === index ? { ...entry, [field.key]: value } : entry
                          )
                        )
                      }
                      profile={profile}
                    />
                  ))}
                  <button
                    type="button"
                    disabled={!lines.optional && lineValues.length === 1}
                    onClick={() => setLineValues((current) => current.filter((_, position) => position !== index))}
                  >
                    Quitar línea {index + 1}
                  </button>
                </div>
              </fieldset>
            ))}
            <button type="button" onClick={() => setLineValues((current) => [...current, defaults(lines.fields)])}>
              Agregar {lines.label.toLowerCase()}
            </button>
          </div>
        ) : null}
        <Field label="Motivo de Procurement">
          <input
            aria-label="Motivo de Procurement"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            minLength={8}
            maxLength={1000}
            required
          />
        </Field>
        {error ? (
          <p className="progressError" role="alert">
            {error}
          </p>
        ) : null}
        <button type="submit">{label}</button>
      </fieldset>
    </form>
  );
}

export function ReadState({ loading, error, reload }: { loading: boolean; error: string; reload: () => void }) {
  if (error)
    return (
      <div className="progressError" role="alert">
        {error}{" "}
        <button type="button" onClick={reload}>
          Reintentar lectura
        </button>
      </div>
    );
  return loading ? <p role="status">Consultando Procurement…</p> : null;
}

export function Pager({
  cursors,
  next,
  setCursors,
  disabled,
}: {
  cursors: string[];
  next: string;
  setCursors: (value: string[]) => void;
  disabled: boolean;
}) {
  if (!cursors.length && !next) return null;
  return (
    <div className="progressActions">
      <button type="button" disabled={disabled || !cursors.length} onClick={() => setCursors(cursors.slice(0, -1))}>
        Página anterior
      </button>
      <button type="button" disabled={disabled || !next} onClick={() => setCursors([...cursors, next])}>
        Página siguiente
      </button>
    </div>
  );
}

export function EntityPanel({ scope, entity }: { scope: ProcurementScope; entity: EntitySpec }) {
  const [selected, setSelected] = useState("");
  const [create, setCreate] = useState(false);
  const [selectedAction, setSelectedAction] = useState("");
  const [selectedRevision, setSelectedRevision] = useState("");
  const [cursors, setCursors] = useState<string[]>([]);
  const collection = useProcurementRead(
    scope.token,
    scope.base,
    query(entity.path, { limit: 50, after_id: cursors[cursors.length - 1] }),
    scope.revision
  );
  const itemPath = selected ? `${entity.path}/${selected}` : null;
  const detail = useProcurementRead(scope.token, scope.base, itemPath, scope.revision);
  const item = detail.value;
  const itemVersion = version(item);
  const poRevision = rows(item?.revisions).find((entry) => text(entry.id) === selectedRevision) ?? null;
  const poRevisionVersion = version(poRevision);
  const actions = (entity.actions ?? []).filter(
    (action) =>
      scope.can(action.permission) &&
      (!Array.isArray(item?.allowed_actions) || permission(item.allowed_actions, action.permission)) &&
      (!action.statuses || action.statuses.includes(text(item?.status)))
  );
  const action = actions.find((entry) => entry.label === selectedAction);
  const allowedCreate =
    !collection.error &&
    (scope.can(entity.permission) ||
      (entity.path === "/evaluations" && (scope.can("evaluation.technical") || scope.can("evaluation.commercial"))));
  return (
    <section
      className="progressPanel"
      aria-label={entity.label}
      aria-busy={scope.busy || collection.loading || detail.loading}
    >
      <h3>{entity.label}</h3>
      {entity.hint ? <p>{entity.hint}</p> : null}
      <ReadState {...collection} reload={scope.reload} />
      {collection.value && !collection.error ? (
        <>
          <Records
            label={entity.label}
            items={rows(collection.value)}
            columns={entity.columns}
            select={(row) => {
              setSelected(text(row.id));
              setSelectedAction("");
              setSelectedRevision("");
              setCreate(false);
            }}
          />
          <Pager
            cursors={cursors}
            setCursors={setCursors}
            next={text(collection.value.next_after_id ?? collection.value.next_cursor)}
            disabled={collection.loading}
          />
        </>
      ) : null}
      {allowedCreate ? (
        <button type="button" aria-expanded={create} onClick={() => setCreate(!create)}>
          {create ? "Cerrar formulario" : `Nuevo registro · ${entity.label}`}
        </button>
      ) : null}
      {allowedCreate && create ? (
        <CommandForm
          label={`Crear · ${entity.label}`}
          spec={entity}
          busy={scope.busy || collection.loading}
          profile={scope.profile}
          submit={async (body) => {
            if (
              entity.path === "/evaluations" &&
              !scope.can(body.evaluation_type === "TECHNICAL" ? "evaluation.technical" : "evaluation.commercial")
            ) {
              throw new Error("No tiene permiso para este tipo de evaluación.");
            }
            const result = await scope.command(entity.path, body);
            if (result && text(result.id)) {
              setSelected(text(result.id));
              setSelectedAction("");
              setCreate(false);
            }
            return result;
          }}
        />
      ) : null}
      <ReadState {...detail} reload={scope.reload} />
      {item && itemPath && !detail.error ? (
        <div className="progressPanel">
          <h4>
            Detalle · {entity.label} #{selected}
          </h4>
          <Facts values={entity.columns.map(([key, title]) => [title, item[key]])} />
          {["lines", "invited_vendors", "revisions", "acceptances", "package_items"].map((key) => {
            const records = rows(item[key]);
            if (!records.length) return null;
            const names: Record<string, string> = {
              lines: "Líneas",
              invited_vendors: "Invitaciones",
              revisions: "Revisiones",
              acceptances: "Aceptaciones",
              package_items: "Ítems del paquete",
            };
            const keys = [
              "id",
              "line_number",
              "vendor_id",
              "po_line_id",
              "shipment_line_id",
              "receipt_line_id",
              "requirement_id",
              "material_requirement_id",
              "description",
              "quantity",
              "accepted_quantity",
              "rejected_quantity",
              "quarantine_quantity",
              "uom",
              "revision",
              "effective_date",
              "status",
            ];
            const columns = keys
              .filter((field) => records.some((record) => field in record))
              .map((field): [string, string] => [field, field.replace(/_/g, " ")]);
            return columns.length ? (
              <Records
                key={key}
                label={names[key]}
                items={records}
                columns={columns}
                select={
                  key === "revisions" && entity.path === "/purchase-orders"
                    ? (row) => setSelectedRevision(text(row.id))
                    : undefined
                }
              />
            ) : null;
          })}
          {poRevision ? (
            <div className="progressPanel">
              <h5>Revisión de PO #{selectedRevision}</h5>
              <Evidence title="Snapshot de revisión de PO" value={poRevision} />
              {text(poRevision.status) === "DRAFT" &&
              poRevisionVersion !== undefined &&
              scope.can("po.revision.approve") ? (
                <CommandForm
                  key={`${selectedRevision}-${poRevisionVersion}`}
                  label="Aprobar revisión de PO"
                  spec={{
                    fields: [
                      { key: "approval_reference", label: "Referencia de aprobación de revisión", required: true },
                    ],
                  }}
                  busy={scope.busy || detail.loading}
                  profile={scope.profile}
                  submit={(body) =>
                    scope.command(`${itemPath}/revisions/${selectedRevision}/approve`, body, poRevisionVersion)
                  }
                />
              ) : null}
            </div>
          ) : null}
          {itemVersion !== undefined ? (
            <div className="progressActions">
              {actions.map((entry) => (
                <button
                  key={entry.label}
                  type="button"
                  aria-pressed={selectedAction === entry.label}
                  disabled={scope.busy || detail.loading}
                  onClick={() => setSelectedAction(entry.label)}
                >
                  {entry.label}
                </button>
              ))}
            </div>
          ) : null}
          {action && itemVersion !== undefined ? (
            <CommandForm
              key={`${action.label}-${itemVersion}`}
              label={`Confirmar · ${action.label}`}
              spec={action}
              busy={scope.busy || detail.loading}
              profile={scope.profile}
              submit={(body) =>
                scope.command(
                  `${itemPath}${action.path}`,
                  action.action ? { ...body, action: action.action } : body,
                  itemVersion,
                  action.method
                )
              }
            />
          ) : null}
          <Evidence title="Datos de origen y trazabilidad" value={item} />
          <button
            type="button"
            onClick={() => {
              setSelected("");
              setSelectedAction("");
            }}
          >
            Cerrar detalle
          </button>
        </div>
      ) : null}
    </section>
  );
}
