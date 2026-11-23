import { useState } from "react";
import { Evidence, Field, Input, Select } from "../progress-foundation/Fields";
import { FieldCommandForm, ReadState } from "../field-operations/FieldForms";
import type { FieldSpec, FormSpec } from "../field-operations/formValues";
import { isRow, positiveId, query, rows, text, useRead, type Row, type Scope } from "./api";

export type PinField = { key: string; label: string; types: string[]; required?: boolean; quality?: boolean };
export type QualityFormSpec = FormSpec & { pins?: PinField[]; capture?: "inspection" | "test" };
type Environment = Pick<Scope, "token" | "base" | "profile" | "revision">;

export function SourceControl({
  field,
  value,
  change,
  environment,
  asOf,
  resolved,
}: {
  field: PinField;
  value: Row | undefined;
  change: (value: Row | undefined) => void;
  environment: Environment;
  asOf: string;
  resolved?: (row: Row) => void;
}) {
  const [kind, setKind] = useState(field.types[0]);
  const [identity, setIdentity] = useState("");
  const [path, setPath] = useState<string | null>(null);
  const [lookupRevision, setLookupRevision] = useState(0);
  const result = useRead(environment.token, environment.base, path, environment.revision + lookupRevision);
  const row = isRow(result.data?.source) ? result.data.source : result.data;
  const pin =
    row &&
    positiveId(row.source_id ?? row.source_entity_id) &&
    Number.isSafeInteger(row.source_version) &&
    /^[a-f0-9]{64}$/.test(text(row.source_hash))
      ? {
          ...(field.quality
            ? {
                source_entity_type: text(row.source_entity_type) || kind,
                source_entity_id: Number(row.source_id ?? row.source_entity_id),
              }
            : { source_type: text(row.source_type) || kind, source_id: Number(row.source_id ?? row.source_entity_id) }),
          source_version: row.source_version,
          source_hash: row.source_hash,
        }
      : null;
  return (
    <fieldset className="qualitySource">
      <legend>
        {field.label}
        {field.required ? " requerido" : ""}
      </legend>
      <Select
        label={`Tipo ${field.label}`}
        value={kind}
        values={field.types}
        onChange={(next) => {
          setKind(next);
          setPath(null);
          change(undefined);
        }}
      />
      <Input
        label={`ID ${field.label}`}
        type="number"
        value={identity}
        onChange={(next) => {
          setIdentity(next);
          setPath(null);
          change(undefined);
        }}
      />
      <button
        type="button"
        disabled={!positiveId(identity) || !kind}
        onClick={() => {
          change(undefined);
          setLookupRevision((revision) => revision + 1);
          setPath(
            query(field.quality ? "/quality-source" : "/source", {
              ...(field.quality
                ? { source_entity_type: kind, source_entity_id: identity }
                : { source_type: kind, source_id: identity }),
              as_of: asOf ? new Date(asOf).toISOString() : undefined,
            })
          );
        }}
      >
        Consultar {field.label}
      </button>
      <ReadState {...result} retry={() => setLookupRevision((revision) => revision + 1)} />
      {pin ? (
        <>
          <Evidence title="Fuente canónica y vigencia consultadas" value={result.data} />
          <button
            type="button"
            onClick={() => {
              change(pin);
              if (row) resolved?.(row);
            }}
          >
            Fijar {field.label}
          </button>
        </>
      ) : null}
      {value ? (
        <p role="status">
          Referencia fijada {text(value.source_type ?? value.source_entity_type)} #
          {text(value.source_id ?? value.source_entity_id)} v{text(value.source_version)}
        </p>
      ) : null}
    </fieldset>
  );
}

function Checklist({
  template,
  values,
  change,
  environment,
}: {
  template: Row;
  values: Row[];
  change: (value: Row[]) => void;
  environment: Environment;
}) {
  const documents = useRead(environment.token, environment.base, "/document-targets", environment.revision);
  const update = (code: string, value: Row) =>
    change([
      ...values.filter((item) => item.item_code !== code),
      { item_code: code, ...values.find((item) => item.item_code === code), ...value },
    ]);
  return (
    <fieldset className="qualityChecklist">
      <legend>Checklist fijado {text(template.code)}</legend>
      <Evidence title="Versión y hash de plantilla" value={template} />
      {rows(template.items).map((item) => {
        const code = text(item.code);
        const value = values.find((record) => record.item_code === code) ?? {};
        const type = text(item.response_type);
        const evidence = rows(value.evidence_references)[0];
        return (
          <section className="qualityCheckItem" key={code}>
            <h4>
              {code} {text(item.label)}
            </h4>
            <p>
              {item.required ? "Respuesta requerida" : "Respuesta opcional"} · {text(item.uom)}{" "}
              {item.lower_limit !== undefined ? `mínimo ${text(item.lower_limit)}` : ""}{" "}
              {item.upper_limit !== undefined ? `máximo ${text(item.upper_limit)}` : ""}
            </p>
            {type === "PASS_FAIL_NA" ? (
              <Select
                label={`${code} Resultado`}
                value={text(value.response_code)}
                onChange={(next) => update(code, { response_code: next })}
                values={item.allow_na ? ["PASS", "FAIL", "NOT_APPLICABLE"] : ["PASS", "FAIL"]}
                required={Boolean(item.required)}
              />
            ) : type === "BOOLEAN" ? (
              <Select
                label={`${code} Respuesta`}
                value={value.boolean_value === true ? "true" : value.boolean_value === false ? "false" : ""}
                onChange={(next) => update(code, { boolean_value: next === "true" })}
                values={["true", "false"]}
                required={Boolean(item.required)}
              />
            ) : (
              <Input
                label={`${code} Respuesta`}
                value={text(value[type === "NUMBER" ? "numeric_value" : "text_value"])}
                onChange={(next) =>
                  update(code, {
                    [type === "NUMBER" ? "numeric_value" : "text_value"]: next,
                    ...(item.uom ? { uom: item.uom } : {}),
                  })
                }
                required={Boolean(item.required)}
              />
            )}
            <Input
              label={`${code} Comentario`}
              value={text(value.comment)}
              onChange={(next) => update(code, { comment: next })}
            />
            <Field label={`${code} Evidencia CDE`}>
              <select
                aria-label={`${code} Evidencia CDE`}
                value={evidence ? `${text(evidence.document_id)}:${text(evidence.attachment_id)}` : ""}
                onChange={(event) => {
                  const record = rows(documents.data).find(
                    (doc) => `${text(doc.document_id)}:${text(doc.attachment_id)}` === event.target.value
                  );
                  update(code, {
                    evidence_references: record
                      ? [
                          {
                            document_id: record.document_id,
                            attachment_id: record.attachment_id,
                            ...((record.source_hash ?? record.sha256)
                              ? { source_hash: record.source_hash ?? record.sha256 }
                              : {}),
                          },
                        ]
                      : [],
                  });
                }}
              >
                <option value="">Seleccionar evidencia existente</option>
                {rows(documents.data).map((doc) => (
                  <option
                    key={`${text(doc.document_id)}:${text(doc.attachment_id)}`}
                    value={`${text(doc.document_id)}:${text(doc.attachment_id)}`}
                  >
                    {text(doc.document_number ?? doc.document_id)} · rev {text(doc.document_revision ?? doc.revision)}
                  </option>
                ))}
              </select>
            </Field>
          </section>
        );
      })}
      <ReadState {...documents} />
    </fieldset>
  );
}

function Measurements({ values, change }: { values: Row[]; change: (value: Row[]) => void }) {
  return (
    <fieldset className="qualityChecklist">
      <legend>Mediciones del ensayo</legend>
      <p>Los valores se conservan como decimales exactos. El resultado no constituye aprobación Engineering.</p>
      {values.map((value, index) => (
        <section className="qualityCheckItem" key={index}>
          <h4>Medición {index + 1}</h4>
          {[
            ["code", "Código"],
            ["numeric_value", "Valor numérico"],
            ["qualitative_value", "Valor cualitativo"],
            ["uom", "Unidad"],
            ["lower_limit", "Límite inferior"],
            ["upper_limit", "Límite superior"],
          ].map(([key, label]) => (
            <Input
              key={key}
              label={`Medición ${index + 1} ${label}`}
              value={text(value[key])}
              onChange={(next) => change(values.map((row, i) => (i === index ? { ...row, [key]: next } : row)))}
            />
          ))}
          <Select
            label={`Medición ${index + 1} Resultado`}
            value={text(value.result)}
            values={["PASS", "FAIL", "CONDITIONAL", "NOT_APPLICABLE"]}
            onChange={(next) => change(values.map((row, i) => (i === index ? { ...row, result: next } : row)))}
          />
          <button type="button" onClick={() => change(values.filter((_, i) => i !== index))}>
            Eliminar medición {index + 1}
          </button>
        </section>
      ))}
      <button type="button" onClick={() => change([...values, { code: "", result: "PASS" }])}>
        Añadir medición
      </button>
    </fieldset>
  );
}

export default function QualityCommandForm({
  label,
  spec,
  environment,
  busy,
  submit,
}: {
  label: string;
  spec: QualityFormSpec;
  environment: Environment;
  busy: boolean;
  submit: (body: Row) => Promise<Row | null>;
}) {
  const [pins, setPins] = useState<Record<string, Row | undefined>>({});
  const [asOf, setAsOf] = useState("");
  const [requestId, setRequestId] = useState("");
  const [responses, setResponses] = useState<Row[]>([]);
  const [measurements, setMeasurements] = useState<Row[]>([]);
  const [error, setError] = useState("");
  const requests = useRead(
    environment.token,
    environment.base,
    spec.capture ? `/${spec.capture === "inspection" ? "inspection" : "test"}-requests` : null,
    environment.revision
  );
  const selected = useRead(
    environment.token,
    environment.base,
    spec.capture && positiveId(requestId)
      ? `/${spec.capture === "inspection" ? "inspection" : "test"}-requests/${requestId}`
      : null,
    environment.revision
  );
  const template = isRow(selected.data?.checklist_template) ? selected.data.checklist_template : null;
  return (
    <section className="qualityForm">
      {spec.pins?.length ? (
        <>
          <Input
            label="Fecha de consulta de referencias"
            type="datetime-local"
            value={asOf}
            onChange={(next) => {
              setAsOf(next);
              setPins({});
            }}
          />
          <p>
            Deje la fecha vacía para consultar vigencia actual. La fecha real de inspección o ensayo se valida
            independientemente en el servidor.
          </p>
          {spec.pins.map((field) => (
            <SourceControl
              key={`${field.key}:${asOf}`}
              field={field}
              value={pins[field.key]}
              change={(value) => setPins((old) => ({ ...old, [field.key]: value }))}
              environment={environment}
              asOf={asOf}
            />
          ))}
        </>
      ) : null}
      {spec.capture ? (
        <>
          <Select
            label={spec.capture === "inspection" ? "Solicitud de inspección" : "Solicitud de ensayo"}
            value={requestId}
            onChange={(next) => {
              setRequestId(next);
              setResponses([]);
              setMeasurements([]);
            }}
            options={rows(requests.data).map((row) => ({
              ...row,
              name: [row.request_number, row.status].map(text).join(" · "),
            }))}
          />
          <ReadState {...requests} />
          <ReadState {...selected} />
          {spec.capture === "inspection" && template ? (
            <Checklist template={template} values={responses} change={setResponses} environment={environment} />
          ) : null}
          {spec.capture === "test" ? <Measurements values={measurements} change={setMeasurements} /> : null}
        </>
      ) : null}
      {error ? (
        <p role="alert" className="progressError">
          {error}
        </p>
      ) : null}
      <FieldCommandForm
        label={label}
        spec={{ fields: spec.fields as FieldSpec[], body: spec.body }}
        environment={environment}
        busy={busy || selected.loading}
        submit={async (body) => {
          setError("");
          try {
            for (const field of spec.pins ?? [])
              if (field.required && !pins[field.key]) throw new Error(`Consulte y fije ${field.label}.`);
            if (spec.capture && (!positiveId(requestId) || !selected.data))
              throw new Error("Seleccione una solicitud canónica disponible.");
            if (spec.capture === "inspection" && template)
              for (const item of rows(template.items)) {
                const response = responses.find((row) => row.item_code === item.code);
                if (
                  item.required &&
                  (!response ||
                    !["response_code", "numeric_value", "text_value", "boolean_value"].some(
                      (key) => response[key] !== undefined && response[key] !== ""
                    ))
                )
                  throw new Error(`Complete el punto ${text(item.code)}.`);
                if (item.evidence_required && !rows(response?.evidence_references).length)
                  throw new Error(`Seleccione evidencia CDE para ${text(item.code)}.`);
              }
            const cleanMeasurements = measurements.map((row) =>
              Object.fromEntries(Object.entries(row).filter(([, value]) => value !== ""))
            );
            if (spec.capture === "test") {
              if (!cleanMeasurements.length) throw new Error("Añada al menos una medición del ensayo.");
              for (const row of cleanMeasurements)
                if (
                  !text(row.code) ||
                  !text(row.result) ||
                  Boolean(text(row.numeric_value)) === Boolean(text(row.qualitative_value))
                )
                  throw new Error("Cada medición necesita código, resultado y un valor numérico o cualitativo.");
            }
            const cleanBody = { ...body };
            const cleanPins = Object.fromEntries(Object.entries(pins).filter(([, value]) => value));
            if (spec.capture === "test") {
              if (pins.equipment_source_reference) {
                if (
                  !body.equipment_valid_from ||
                  !body.equipment_valid_to ||
                  !isRow(body.equipment_calibration_document)
                )
                  throw new Error("Fije las fechas y evidencia CDE de calibración del equipo seleccionado.");
                cleanBody.equipment_reference = {
                  source_reference: pins.equipment_source_reference,
                  calibration_status: "VALID",
                  valid_from: body.equipment_valid_from,
                  valid_to: body.equipment_valid_to,
                  document_reference: body.equipment_calibration_document,
                };
              }
              delete cleanBody.equipment_valid_from;
              delete cleanBody.equipment_valid_to;
              delete cleanBody.equipment_calibration_document;
              delete cleanPins.equipment_source_reference;
            }
            return await submit({
              ...cleanBody,
              ...cleanPins,
              ...(spec.capture
                ? {
                    request_id: Number(requestId),
                    ...(spec.capture === "inspection"
                      ? { checklist_responses: responses }
                      : { measurements: cleanMeasurements }),
                  }
                : {}),
            });
          } catch (cause) {
            setError(cause instanceof Error ? cause.message : "Datos Quality inválidos.");
            return null;
          }
        }}
      />
    </section>
  );
}
