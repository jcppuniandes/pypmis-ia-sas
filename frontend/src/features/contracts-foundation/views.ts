import type { FieldSpec, FormSpec } from "./formValues";
import type { Row } from "./api";

type Column = [string, string];
export type Action = { name: string; duty: string; states: string[]; endpoint?: string; body?: Row; spec?: FormSpec };
export type Entity = {
  path: string;
  columns: Column[];
  create?: { name: string; duty: string; spec: FormSpec; initialVersion?: number };
  actions?: Action[];
  details?: boolean;
};
export const statuses: Column = ["status", "Estado"];
const field = (key: string, label: string, options: Omit<FieldSpec, "key" | "label"> = {}): FieldSpec => ({
  key,
  label,
  required: true,
  ...options,
});
const id = (key: string, label: string, collection?: string, required = true) =>
  field(key, label, { kind: "id", collection, required });
const date = (key: string, label: string, required = true) => field(key, label, { kind: "date", required });
const decimal = (key: string, label: string, required = true) => field(key, label, { kind: "decimal", required });
const notes = (key: string, label: string, required = true) => field(key, label, { kind: "notes", required });
const catalog = (key: string, label: string, catalogKey: string, required = true) =>
  field(key, label, { catalog: catalogKey, required });
const doc = (key = "document_reference", label = "Evidencia CDE", required = true, multiple = false) =>
  field(key, label, { kind: "document", required, multiple });
const procurement = (key: string, label: string, multiple = false) =>
  field(key, label, { kind: "source", required: false, multiple });
const json = (key: string, label: string, help: string, required = false) =>
  field(key, label, { kind: "json", help, required });
const contract = id("contract_id", "Contrato", "/contracts");
const version = id("contract_version_id", "Versión de contrato", "/versions");
const action = (name: string, duty: string, states: string[], code: string, fields?: FieldSpec[]): Action => ({
  name,
  duty,
  states,
  body: { action: code },
  spec: { fields },
});

export const entities = {
  "Contract Packages": {
    path: "/packages",
    columns: [
      ["package_code", "Código"],
      ["title", "Título"],
      ["contract_type", "Tipo"],
      ["estimated_value", "Estimado"],
      ["currency", "Moneda"],
      statuses,
    ],
    create: {
      name: "Crear paquete contractual",
      duty: "package.prepare",
      spec: {
        fields: [
          field("package_code", "Código del paquete"),
          field("title", "Título del paquete"),
          notes("description", "Descripción", false),
          notes("contract_strategy", "Estrategia contractual", false),
          catalog("contract_type", "Tipo de contrato", "contract_types"),
          catalog("commercial_model", "Modelo comercial", "commercial_models"),
          id("responsible_user_id", "Responsable (ID)", undefined, false),
          date("planned_award_date", "Adjudicación prevista", false),
          date("planned_execution_date", "Firma prevista", false),
          catalog("currency", "Moneda", "currencies"),
          decimal("estimated_value", "Valor estimado"),
          procurement("procurement_sources", "Fuentes Procurement", true),
        ],
      },
    },
    actions: [
      action("Planificar paquete", "package.prepare", ["DRAFT"], "plan"),
      action("Cancelar paquete", "package.prepare", ["DRAFT", "PLANNED"], "cancel"),
    ],
  },
  Contracts: {
    path: "/contracts",
    columns: [
      ["contract_number", "Contrato"],
      ["title", "Título"],
      ["vendor_id", "Proveedor"],
      ["current_version_id", "Versión vigente"],
      statuses,
    ],
    create: {
      name: "Registrar contrato",
      duty: "contract.prepare",
      spec: {
        fields: [
          field("contract_number", "Número de contrato"),
          id("contract_package_id", "Paquete contractual", "/packages"),
          field("title", "Título del contrato"),
          notes("description", "Descripción", false),
          id("vendor_id", "Proveedor Procurement (ID)"),
          field("governing_reference", "Referencia rectora"),
          decimal("original_contract_value", "Valor original"),
          date("effective_date", "Fecha efectiva"),
          date("commencement_date", "Inicio"),
          date("planned_completion_date", "Terminación prevista"),
          field("terms_reference", "Referencia de términos"),
          doc(),
          doc("insurance_reference", "Seguro CDE", false),
          doc("bond_reference", "Garantía CDE", false),
          procurement("source_instrument", "Instrumento Procurement"),
        ],
      },
    },
    actions: [
      action("Aprobar contrato", "contract.approve", ["DRAFT"], "approve"),
      action("Registrar firma", "contract.execute", ["APPROVED"], "execute", [
        date("execution_date", "Fecha de firma"),
        doc("document_reference", "Documento firmado CDE"),
      ]),
      action("Declarar efectivo", "contract.effect", ["EXECUTED"], "effect"),
    ],
  },
  "Contract Versions": {
    path: "/versions",
    columns: [
      ["contract_id", "Contrato (ID)"],
      ["revision", "Versión"],
      ["value", "Valor contractual"],
      ["effective_date", "Fecha efectiva"],
      statuses,
    ],
  },
  "Commercial Commitments": {
    path: "/commitments",
    columns: [
      ["commitment_code", "Código"],
      ["contract_id", "Contrato (ID)"],
      ["contract_version_id", "Versión"],
      ["committed_amount", "Importe"],
      ["currency", "Moneda"],
      statuses,
    ],
    create: {
      name: "Registrar compromiso comercial",
      duty: "commitment.prepare",
      spec: {
        fields: [
          field("commitment_code", "Código de compromiso"),
          contract,
          version,
          decimal("committed_amount", "Importe comprometido"),
          date("effective_date", "Fecha efectiva"),
          notes("commercial_basis", "Base comercial"),
          id("supersedes_id", "Compromiso anterior (ID)", "/commitments", false),
        ],
      },
    },
    actions: [
      { name: "Aprobar compromiso comercial", duty: "commitment.approve", states: ["DRAFT"], endpoint: "/approve" },
    ],
  },
  SOV: {
    path: "/sovs",
    columns: [
      ["code", "Código"],
      ["contract_id", "Contrato (ID)"],
      ["contract_version_id", "Versión"],
      ["total_value", "Total"],
      statuses,
    ],
    create: {
      name: "Crear SOV",
      duty: "sov.edit",
      spec: {
        fields: [contract, version, field("code", "Código SOV")],
        lines: {
          key: "lines",
          label: "Línea SOV",
          fields: [
            field("line_number", "Número de línea"),
            notes("description", "Descripción de línea"),
            decimal("quantity", "Cantidad"),
            decimal("unit_rate", "Precio unitario"),
            field("uom", "Unidad"),
            json(
              "mappings",
              "Vínculos de la línea",
              "Lista de vínculos con target_kind, target_id y, para Schedule, versión e identidad de origen.",
              true
            ),
            catalog("retention_rule", "Regla de retención", "retention_rules", false),
          ],
        },
      },
    },
    actions: [{ name: "Publicar SOV", duty: "sov.publish", states: ["DRAFT"], endpoint: "/publish" }],
  },
  Changes: {
    path: "/changes",
    columns: [
      ["change_number", "Cambio"],
      ["contract_id", "Contrato (ID)"],
      ["base_version_id", "Versión base"],
      ["resulting_version_id", "Versión resultante"],
      ["value_delta", "Variación"],
      statuses,
    ],
    create: {
      name: "Registrar cambio potencial",
      duty: "change.prepare",
      spec: {
        fields: [
          contract,
          id("base_version_id", "Versión base", "/versions"),
          field("change_number", "Número de cambio"),
          catalog("change_type", "Tipo de cambio", "change_types"),
          notes("description", "Descripción del cambio"),
          decimal("value_delta", "Variación de valor"),
          field("time_delta", "Variación de plazo (días)", { kind: "integer" }),
          date("effective_date", "Fecha efectiva"),
          doc("document_reference", "Evidencia CDE de cambio", false),
          id("notice_id", "Aviso relacionado", "/notices", false),
          json(
            "schedule_references",
            "Referencias Schedule",
            "Lista de versiones y actividades aprobadas; no actualiza Schedule."
          ),
        ],
      },
    },
    actions: [
      action("Solicitar cambio", "change.prepare", ["POTENTIAL"], "request"),
      action("Poner cambio en revisión", "change.review", ["REQUESTED"], "review"),
      action("Aprobar orden de cambio", "change.approve", ["UNDER_REVIEW"], "approve", [
        doc("document_reference", "Evidencia CDE de aprobación", false),
      ]),
      action("Rechazar cambio", "change.approve", ["UNDER_REVIEW"], "reject"),
    ],
  },
  "Payment Applications": {
    path: "/payment-applications",
    columns: [
      ["application_number", "Solicitud"],
      ["contract_id", "Contrato (ID)"],
      ["period_id", "Período"],
      ["effective_date", "Fecha efectiva"],
      statuses,
    ],
    create: {
      name: "Presentar solicitud de pago",
      duty: "application.prepare",
      spec: {
        fields: [
          contract,
          id("sov_id", "SOV publicado", "/sovs"),
          field("application_number", "Número de solicitud"),
          id("period_id", "Período de control (ID)"),
          date("effective_date", "Fecha efectiva"),
          doc(),
        ],
        lines: {
          key: "lines",
          label: "Línea de solicitud",
          fields: [
            id("sov_line_id", "Línea publicada SOV (ID)"),
            field("progress", "Medición aprobada de Progress", { kind: "progress" }),
            decimal("quantity", "Cantidad solicitada"),
          ],
        },
      },
    },
    actions: [
      action("Revisar solicitud", "application.review", ["SUBMITTED"], "review"),
      action("Rechazar solicitud", "application.review", ["SUBMITTED"], "reject"),
    ],
  },
  "Payment Certificates": {
    path: "/payment-certificates",
    columns: [
      ["certificate_number", "Certificado"],
      ["application_id", "Solicitud (ID)"],
      ["effective_date", "Fecha efectiva"],
      ["net_amount", "Importe neto"],
      statuses,
    ],
    create: {
      name: "Preparar certificado",
      duty: "certificate.prepare",
      spec: {
        fields: [
          id("application_id", "Solicitud revisada", "/payment-applications"),
          field("certificate_number", "Número de certificado"),
          date("effective_date", "Fecha efectiva"),
          doc(),
        ],
        lines: {
          key: "lines",
          label: "Línea de certificado",
          fields: [
            id("application_line_id", "Línea de solicitud (ID)"),
            decimal("quantity", "Cantidad certificada"),
            decimal("retention", "Retención", false),
            decimal("advance_recovery", "Amortización de anticipo", false),
            decimal("deductions", "Deducciones", false),
            decimal("withholdings", "Retenciones fiscales", false),
            decimal("other_adjustments", "Otros ajustes", false),
          ],
        },
      },
    },
    actions: [
      action("Aprobar certificado", "certificate.approve", ["DRAFT"], "approve"),
      action("Rechazar certificado", "certificate.approve", ["DRAFT"], "reject"),
      {
        name: "Vincular referencia externa Finance",
        duty: "invoice.reference",
        states: ["APPROVED"],
        endpoint: "/finance-references",
        spec: {
          fields: [
            field("source_system", "Sistema de origen"),
            field("invoice_reference", "Referencia de factura externa"),
            id("source_version", "Versión en origen"),
            field("source_hash", "Hash en origen"),
            decimal("amount", "Importe de referencia"),
            field("status_reference", "Referencia de estado"),
            field("payment_status", "Estado de pago externo"),
          ],
        },
      },
    ],
  },
  "Finance References": {
    path: "/finance-references",
    columns: [
      ["source_system", "Sistema"],
      ["invoice_reference", "Factura externa"],
      ["amount", "Importe"],
      ["payment_status", "Estado externo"],
    ],
  },
  Notices: {
    path: "/notices",
    columns: [
      ["notice_number", "Aviso"],
      ["contract_id", "Contrato (ID)"],
      ["subject", "Asunto"],
      ["response_due_date", "Vencimiento"],
      statuses,
    ],
    create: {
      name: "Registrar aviso",
      duty: "notice.record",
      spec: {
        fields: [
          contract,
          field("notice_number", "Número de aviso"),
          catalog("notice_type", "Tipo de aviso", "notice_types"),
          field("sender", "Remitente"),
          field("recipient", "Destinatario"),
          date("issue_date", "Fecha de emisión"),
          date("received_date", "Fecha de recepción", false),
          field("subject", "Asunto"),
          field("event_reference", "Referencia de evento", { required: false }),
          date("response_due_date", "Plazo de respuesta", false),
          doc(),
        ],
      },
    },
    actions: [
      action("Registrar recepción", "notice.record", ["ISSUED"], "receive", [
        date("received_date", "Fecha de recepción"),
      ]),
      action("Cerrar aviso", "notice.record", ["RECEIVED"], "close"),
    ],
  },
  Claims: {
    path: "/claims",
    columns: [
      ["claim_number", "Reclamación"],
      ["contract_id", "Contrato (ID)"],
      ["notice_id", "Aviso (ID)"],
      ["claimed_amount", "Importe"],
      statuses,
    ],
    create: {
      name: "Registrar reclamación",
      duty: "claim.prepare",
      spec: {
        fields: [
          contract,
          field("claim_number", "Número de reclamación"),
          catalog("claim_type", "Tipo de reclamación", "claim_types"),
          notes("cause", "Causa"),
          id("notice_id", "Aviso relacionado", "/notices", false),
          decimal("claimed_amount", "Importe reclamado"),
          field("claimed_time", "Plazo reclamado (días)", { kind: "integer" }),
          date("effective_date", "Fecha efectiva"),
          doc("documents", "Evidencias CDE", true, true),
        ],
      },
    },
    actions: [
      action("Aceptar reclamación", "claim.decide", ["REGISTERED"], "accept"),
      action("Rechazar reclamación", "claim.decide", ["REGISTERED"], "reject"),
    ],
  },
  Mappings: {
    path: "/mappings",
    columns: [
      ["source_kind", "Origen"],
      ["source_id", "Origen (ID)"],
      ["target_kind", "Destino"],
      ["target_id", "Destino (ID)"],
    ],
    create: {
      name: "Registrar decisión de vínculo",
      duty: "mapping.edit",
      spec: {
        fields: [
          field("target_kind", "Clase de destino", { choices: ["PROCUREMENT_PACKAGE", "CWP", "PWP", "CWA"] }),
          id("target_id", "Destino (ID)"),
          field("source_hash", "Hash fijado en origen", { required: false }),
          field("action", "Acción de vínculo", { choices: ["SET", "REMOVE"], initial: "SET" }),
          date("effective_date", "Fecha efectiva", false),
        ],
      },
    },
  },
} satisfies Record<string, Entity>;

export type EntityTab = keyof typeof entities;
export type Tab = EntityTab | "Contract Readiness" | "Commercial Look-Ahead" | "History";
export const tabs: Tab[] = [
  "Contract Packages",
  "Contracts",
  "Contract Versions",
  "Commercial Commitments",
  "SOV",
  "Changes",
  "Payment Applications",
  "Payment Certificates",
  "Finance References",
  "Notices",
  "Claims",
  "Contract Readiness",
  "Commercial Look-Ahead",
  "Mappings",
  "History",
];
