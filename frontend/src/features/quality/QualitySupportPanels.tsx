import { useState } from "react";
import { Facts, Input, Records } from "../progress-foundation/Fields";
import { FieldCommandForm, ReadState } from "../field-operations/FieldForms";
import { SourceControl } from "./QualityForms";
import { positiveId, query, rows, text, useRead, versionOf, type Row, type Scope } from "./api";

export function LotLinksPanel({ scope }: { scope: Scope }) {
  const [receipt, setReceipt] = useState<Row | undefined>();
  const [production, setProduction] = useState<Row | undefined>();
  const complete = receipt && production;
  const result = useRead(
    scope.token,
    scope.base,
    complete
      ? query("/lot-links", { receipt_line_id: text(receipt.source_id), production_id: text(production.source_id) })
      : null,
    scope.revision
  );
  const version = versionOf(result.data?.version, true);
  return (
    <section className="progressPanel" aria-label="Material Lot Traceability">
      <h2>Material Lot Traceability</h2>
      <p>
        Relacione líneas de recepción existentes con producción verificada y sus identificadores de lote, batch, heat o
        serial. Este registro no crea inventario ni modifica cantidades de Procurement.
      </p>
      <SourceControl
        field={{
          key: "receipt_reference",
          label: "Línea de recepción",
          types: ["MATERIAL_RECEIPT_LINE"],
          required: true,
        }}
        value={receipt}
        change={setReceipt}
        environment={scope}
        asOf=""
      />
      <SourceControl
        field={{
          key: "production_reference",
          label: "Producción Field",
          types: ["FIELD_PRODUCTION", "FIELD_REWORK"],
          required: true,
        }}
        value={production}
        change={setProduction}
        environment={scope}
        asOf=""
      />
      <ReadState {...result} retry={scope.reload} />
      {result.data ? (
        <Records
          label="Historial de vínculos material producción"
          items={rows(result.data)}
          columns={[
            ["id", "ID"],
            ["version", "Versión"],
            ["receipt_line_id", "Recepción"],
            ["production_record_id", "Producción"],
            ["action", "Decisión"],
            ["quantity", "Cantidad"],
            ["uom", "Unidad"],
          ]}
        />
      ) : null}
      {complete && version !== undefined && scope.can("mapping.edit") ? (
        <FieldCommandForm
          key={`${receipt.source_id}:${production.source_id}:${version}`}
          label="Registrar vínculo material producción"
          spec={{
            fields: [
              {
                key: "action",
                label: "Decisión del vínculo",
                choices: ["SET", "REMOVE"],
                initial: "SET",
                required: true,
              },
              { key: "lot", label: "Lote", required: false },
              { key: "batch", label: "Batch", required: false },
              { key: "heat", label: "Heat", required: false },
              { key: "serial", label: "Serial", required: false },
              { key: "quantity", label: "Cantidad vinculada", kind: "decimal", required: false },
              { key: "uom", label: "Unidad vinculada", required: false },
              { key: "document_reference", label: "Evidencia CDE", kind: "document", required: true },
            ],
          }}
          environment={scope}
          busy={scope.busy || result.loading}
          submit={(body) => {
            const { lot, batch, heat, serial, ...values } = body;
            return scope.command(
              "/lot-links",
              {
                ...values,
                receipt_reference: receipt,
                production_reference: production,
                lot_identifiers: Object.fromEntries(
                  Object.entries({ lot, batch, heat, serial }).filter(([, value]) => Boolean(text(value)))
                ),
                ...(positiveId(result.data?.latest_id) ? { supersedes_id: result.data?.latest_id } : {}),
              },
              version
            );
          }}
        />
      ) : null}
    </section>
  );
}

export function ReadinessAssessmentPanel({ scope }: { scope: Scope }) {
  const [itp, setItp] = useState("");
  const [subject, setSubject] = useState<Row | undefined>();
  const [metadata, setMetadata] = useState<Row | null>(null);
  const path =
    positiveId(itp) && subject && text(metadata?.subject_key)
      ? query("/readiness/assessments", { itp_id: itp, subject_key: text(metadata?.subject_key) })
      : null;
  const result = useRead(scope.token, scope.base, path, scope.revision);
  const version = versionOf(result.data?.version, true);
  return (
    <section className="progressPanel" aria-label="Readiness Evidence Assessments">
      <h2>Readiness Evidence Assessments</h2>
      <p>
        Consultar readiness no guarda decisiones. Esta acción explícita crea una evaluación versionada que AWP puede
        consultar y adoptar bajo su propia autoridad; nunca libera un paquete.
      </p>
      <Input label="ITP de evaluación ID" type="number" value={itp} onChange={setItp} required />
      <SourceControl
        field={{
          key: "subject_reference",
          label: "Objeto de evaluación",
          types: [
            "FIELD_PRODUCTION",
            "FIELD_REWORK",
            "FIELD_WORKFRONT",
            "MATERIAL_RECEIPT_LINE",
            "MATERIAL_ACCEPTANCE",
            "MATERIAL_ALLOCATION",
          ],
          required: true,
        }}
        value={subject}
        change={(value) => {
          setSubject(value);
          setMetadata(null);
        }}
        resolved={setMetadata}
        environment={scope}
        asOf=""
      />
      <ReadState {...result} retry={scope.reload} />
      {result.data ? (
        <>
          <Facts values={[["Versión actual del flujo", result.data.version]]} />
          <Records
            label="Evaluaciones Quality guardadas"
            items={rows(result.data)}
            columns={[
              ["id", "ID para consumidor"],
              ["version", "Versión"],
              ["itp_id", "ITP"],
              ["readiness_state", "Readiness"],
              ["as_of", "Fecha"],
              ["created_by", "Evaluador"],
            ]}
          />
        </>
      ) : null}
      {subject && positiveId(itp) && version !== undefined && scope.can("readiness.assess") ? (
        <FieldCommandForm
          key={`${itp}:${text(metadata?.subject_key)}:${version}`}
          label="Guardar evaluación Quality"
          spec={{}}
          environment={scope}
          busy={scope.busy || result.loading}
          submit={(body) =>
            scope.command("/readiness/assess", { ...body, itp_id: Number(itp), subject_reference: subject }, version)
          }
        />
      ) : null}
    </section>
  );
}
