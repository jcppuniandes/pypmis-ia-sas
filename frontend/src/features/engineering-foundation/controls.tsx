import type { FormEvent, ReactNode } from "react";
import { Field, Input, Select } from "../progress-foundation/Fields";
import type { EngineeringRow } from "./api";
import { recordId } from "./api";

export { Evidence, Facts, Field, Input, ReasonCodes, Records, Select } from "../progress-foundation/Fields";

export function SubmitForm({
  onSubmit,
  children,
  disabled = false,
}: {
  onSubmit: () => void | Promise<void>;
  children: ReactNode;
  disabled?: boolean;
}) {
  const submit = (event: FormEvent) => {
    event.preventDefault();
    void onSubmit();
  };
  return (
    <form onSubmit={submit}>
      <fieldset className="progressForm engineeringFieldset" disabled={disabled}>
        {children}
      </fieldset>
    </form>
  );
}

export function Notes({
  label,
  value,
  onChange,
  required = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  required?: boolean;
}) {
  return (
    <Field label={label}>
      <textarea
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        required={required}
        rows={3}
      />
    </Field>
  );
}

export function Reason({
  value,
  onChange,
  label = "Motivo de Ingeniería",
}: {
  value: string;
  onChange: (value: string) => void;
  label?: string;
}) {
  return (
    <Field label={label}>
      <input
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        minLength={8}
        maxLength={1000}
        required
      />
    </Field>
  );
}

export function Options({
  label,
  value,
  onChange,
  records,
  valueKey = "id",
  render,
  required = false,
  disabled = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  records: EngineeringRow[];
  valueKey?: string;
  render: (row: EngineeringRow) => string;
  required?: boolean;
  disabled?: boolean;
}) {
  return (
    <Field label={label}>
      <select
        aria-label={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        required={required}
        disabled={disabled}
      >
        <option value="">{required ? "Seleccionar" : "Sin selección"}</option>
        {records.map((row) => {
          const id = recordId(row, valueKey);
          return id ? (
            <option key={id} value={id}>
              {render(row)}
            </option>
          ) : null;
        })}
      </select>
    </Field>
  );
}

export function ReadState({ loading, error, reload }: { loading: boolean; error: string; reload?: () => void }) {
  if (error)
    return (
      <div className="progressError" role="alert">
        {error}{" "}
        {reload ? (
          <button type="button" onClick={reload}>
            Reintentar lectura
          </button>
        ) : null}
      </div>
    );
  if (loading) return <p role="status">Consultando fuentes de Ingeniería…</p>;
  return null;
}

export function DateFilters({
  asOf,
  setAsOf,
  horizon,
  setHorizon,
  horizonOptions,
}: {
  asOf: string;
  setAsOf: (value: string) => void;
  horizon?: string;
  setHorizon?: (value: string) => void;
  horizonOptions?: string[];
}) {
  return (
    <div className="progressForm">
      <Input label="Fecha de corte Ingeniería" type="date" value={asOf} onChange={setAsOf} />
      {horizon !== undefined && setHorizon ? (
        <Select label="Horizonte (días)" value={horizon} onChange={setHorizon} values={horizonOptions} />
      ) : null}
    </div>
  );
}
