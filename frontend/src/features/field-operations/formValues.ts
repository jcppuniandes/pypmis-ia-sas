import { encodeFields as encodeCommon, type FieldSpec as CommonField } from "../contracts-foundation/formValues";
import { text, type Row } from "./api";

export type FieldSpec = Omit<CommonField, "kind"> & {
  kind?: CommonField["kind"] | "datetime" | "time" | "boolean" | "pin" | "reference";
  sourceTypes?: string[];
  targetKinds?: string[];
  when?: { key: string; values: string[] };
};
export type FormSpec = { fields?: FieldSpec[]; body?: Row };
export type FormValue = string | Row | Row[];

export function encodeFields(fields: FieldSpec[], values: Record<string, FormValue>): Row {
  const plain = fields.filter((field) => !["datetime", "boolean"].includes(field.kind ?? ""));
  const body = encodeCommon(plain as CommonField[], values);
  for (const field of fields) {
    const raw = text(values[field.key]).trim();
    if (field.kind === "datetime") {
      if (!raw && !field.required) continue;
      const instant = new Date(raw);
      if (!raw || Number.isNaN(instant.valueOf())) throw new Error(`${field.label}: indique fecha y hora válidas.`);
      body[field.key] = instant.toISOString();
    }
    if (field.kind === "boolean") {
      if (!raw && !field.required) continue;
      body[field.key] = raw === "true";
    }
  }
  return body;
}
