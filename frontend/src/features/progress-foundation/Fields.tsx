import type { ReactNode } from "react";
import { display, label, text, type ProgressRow } from "./types";

export function Field({ label: title, children }: { label: string; children: ReactNode }) {
  return (
    <label className="progressField">
      <span>{title}</span>
      {children}
    </label>
  );
}
export function Input({
  label: title,
  value,
  onChange,
  type = "text",
  required = false,
  disabled = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  required?: boolean;
  disabled?: boolean;
}) {
  return (
    <Field label={title}>
      <input
        aria-label={title}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        type={type}
        step={type === "number" ? "any" : undefined}
        required={required}
        disabled={disabled}
      />
    </Field>
  );
}
export function Select({
  label: title,
  value,
  onChange,
  values,
  options,
  required = false,
  disabled = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  values?: string[];
  options?: ProgressRow[];
  required?: boolean;
  disabled?: boolean;
}) {
  return (
    <Field label={title}>
      <select
        aria-label={title}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        required={required}
        disabled={disabled}
      >
        <option value="">{required ? "Seleccionar" : "Sin asignación"}</option>
        {values?.map((entry) => (
          <option key={entry} value={entry}>
            {entry}
          </option>
        ))}
        {options?.map((row) => (
          <option key={text(row, "id")} value={text(row, "id")}>
            {label(row)}
          </option>
        ))}
      </select>
    </Field>
  );
}
export function Records({
  label: title,
  items,
  columns,
  select,
  format,
}: {
  label: string;
  items: ProgressRow[];
  columns: [string, string][];
  select?: (row: ProgressRow) => void;
  format?: (key: string, value: unknown, row: ProgressRow) => ReactNode;
}) {
  return (
    <div className="progressTable">
      <table aria-label={title}>
        <thead>
          <tr>
            {columns.map(([key, name]) => (
              <th key={key} scope="col">
                {name}
              </th>
            ))}
            {select ? <th scope="col">Detalle</th> : null}
          </tr>
        </thead>
        <tbody>
          {items.map((row, index) => (
            <tr key={`${text(row, "id", String(index))}-${index}`}>
              {columns.map(([key]) => (
                <td key={key}>{format ? format(key, row[key], row) : display(row[key])}</td>
              ))}
              {select ? (
                <td>
                  <button type="button" onClick={() => select(row)}>
                    Ver {title} {text(row, "code", text(row, "id"))}
                  </button>
                </td>
              ) : null}
            </tr>
          ))}
          {!items.length ? (
            <tr>
              <td colSpan={columns.length + (select ? 1 : 0)}>Sin registros en este Project.</td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}
export function Facts({ values }: { values: [string, unknown][] }) {
  return (
    <dl className="progressFacts">
      {values.map(([title, value]) => (
        <div key={title}>
          <dt>{title}</dt>
          <dd>{display(value)}</dd>
        </div>
      ))}
    </dl>
  );
}
export function Evidence({ title, value }: { title: string; value: unknown }) {
  return (
    <details className="progressEvidence">
      <summary>{title}</summary>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}
export function ReasonCodes({ codes }: { codes: unknown }) {
  if (!Array.isArray(codes) || !codes.length) return null;
  return (
    <ul className="progressReasons" aria-label="Motivos de validación">
      {codes.map((code, index) => (
        <li key={index}>{display(code)}</li>
      ))}
    </ul>
  );
}
