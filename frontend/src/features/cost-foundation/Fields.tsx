import type { ReactNode } from "react";
import { display, rowLabel, text, type CostRow } from "./types";

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label className="costField">
      <span>{label}</span>
      {children}
    </label>
  );
}
export function Input({
  label,
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
    <Field label={label}>
      <input
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        type={type}
        required={required}
        disabled={disabled}
        step={type === "number" ? "any" : undefined}
      />
    </Field>
  );
}
export function Select({
  label,
  value,
  onChange,
  rows,
  values,
  required = false,
  disabled = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  rows?: CostRow[];
  values?: string[];
  required?: boolean;
  disabled?: boolean;
}) {
  return (
    <Field label={label}>
      <select
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        required={required}
        disabled={disabled}
      >
        <option value="">{required ? "Seleccionar" : "Sin asignación"}</option>
        {rows?.map((row) => (
          <option key={text(row, "id")} value={text(row, "id")}>
            {rowLabel(row)}
          </option>
        ))}
        {values?.map((entry) => (
          <option key={entry} value={entry}>
            {entry}
          </option>
        ))}
      </select>
    </Field>
  );
}
export function Records({
  label,
  rows,
  columns,
  select,
  format,
}: {
  label: string;
  rows: CostRow[];
  columns: [string, string][];
  select?: (row: CostRow) => void;
  format?: (key: string, value: unknown, row: CostRow) => ReactNode;
}) {
  return (
    <div className="costTable">
      <table aria-label={label}>
        <thead>
          <tr>
            {columns.map(([key, title]) => (
              <th key={key} scope="col">
                {title}
              </th>
            ))}
            {select ? <th scope="col">Detalle</th> : null}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={text(row, "id", String(index))}>
              {columns.map(([key]) => (
                <td key={key}>{format ? format(key, row[key], row) : display(row[key])}</td>
              ))}
              {select ? (
                <td>
                  <button type="button" onClick={() => select(row)}>
                    Ver {label} {text(row, "code", text(row, "id"))}
                  </button>
                </td>
              ) : null}
            </tr>
          ))}
          {!rows.length ? (
            <tr>
              <td colSpan={columns.length + (select ? 1 : 0)}>Sin registros Cost en este Project.</td>
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}
export function Evidence({ label, value }: { label: string; value: unknown }) {
  return (
    <details className="costEvidence">
      <summary>{label}</summary>
      <pre>{JSON.stringify(value, null, 2)}</pre>
    </details>
  );
}
