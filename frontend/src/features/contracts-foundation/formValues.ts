import { isRow, positiveId, text, type Row } from "./api";

export type FieldSpec = {
  key: string;
  label: string;
  kind?: "id" | "integer" | "decimal" | "date" | "notes" | "json" | "document" | "source" | "progress";
  required?: boolean;
  choices?: string[];
  catalog?: string;
  collection?: string;
  initial?: string;
  multiple?: boolean;
  help?: string;
};
export type FormSpec = {
  fields?: FieldSpec[];
  lines?: { key: string; label: string; fields: FieldSpec[]; optional?: boolean };
};
export type FormValue = string | Row | Row[];
export type Values = Record<string, FormValue>;

export function encodeFields(fields: FieldSpec[], values: Values): Row {
  return Object.fromEntries(
    fields.flatMap<[string, unknown]>((field) => {
      const raw = values[field.key];
      const value = typeof raw === "string" ? raw.trim() : raw;
      if (value === "" || value === undefined || (Array.isArray(value) && value.length === 0)) {
        if (field.required) throw new Error(`Complete ${field.label}.`);
        return [];
      }
      if (field.kind === "id" || field.kind === "integer") {
        if (
          field.kind === "id"
            ? !positiveId(value)
            : !/^[-+]?\d+$/.test(text(value)) || !Number.isSafeInteger(Number(value))
        ) {
          throw new Error(`${field.label}: indique un entero válido.`);
        }
        return [[field.key, Number(value)]];
      }
      if (field.kind === "decimal") {
        if (!/^[-+]?\d+(\.\d+)?$/.test(text(value))) throw new Error(`${field.label}: use un decimal sin separadores.`);
        return [[field.key, value]]; // Never convert legal amounts to binary floating point.
      }
      if (field.kind === "json") {
        const object: unknown = JSON.parse(text(value));
        if (!isRow(object) && !Array.isArray(object))
          throw new Error(`${field.label}: se requiere un objeto o lista JSON.`);
        return [[field.key, object]];
      }
      return [[field.key, value]];
    })
  );
}
