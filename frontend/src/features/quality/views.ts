import type { FieldSpec } from "../field-operations/formValues";
import type { QualityFormSpec, PinField } from "./QualityForms";
import type { Row } from "./api";

export type Action = {
  name: string;
  duty: string;
  states: string[];
  body?: Row;
  endpoint?: string;
  spec?: QualityFormSpec;
};
export type Entity = {
  path: string;
  columns: [string, string][];
  create?: { name: string; duty: string; spec: QualityFormSpec };
  actions?: Action[];
  details?: boolean;
  reinspectionOnly?: boolean;
};
const f = (key: string, label: string, options: Omit<FieldSpec, "key" | "label"> = {}): FieldSpec => ({
  key,
  label,
  required: true,
  ...options,
});
const id = (key: string, label: string, collection?: string, required = true) =>
  f(key, label, { kind: "id", collection, required });
const date = (key: string, label: string) => f(key, label, { kind: "date" });
const instant = (key: string, label: string) => f(key, label, { kind: "datetime" });
const catalog = (key: string, label: string, name: string) => f(key, label, { catalog: name });
const doc = (multiple = false) =>
  f(multiple ? "document_references" : "document_reference", "Evidencia CDE", { kind: "document", multiple });
const notes = (key: string, label: string, required = true) => f(key, label, { kind: "notes", required });
const subject: PinField = {
  key: "subject_reference",
  label: "Objeto inspeccionado",
  types: [
    "FIELD_PRODUCTION",
    "FIELD_REWORK",
    "FIELD_WORKFRONT",
    "MATERIAL_RECEIPT_LINE",
    "MATERIAL_ACCEPTANCE",
    "MATERIAL_ALLOCATION",
  ],
  required: true,
};
const engineering: PinField = {
  key: "engineering_reference",
  label: "Requisito Engineering",
  types: ["IFC_RELEASE", "ENGINEERING_REVISION"],
  required: true,
};
const action = (name: string, duty: string, states: string[], value: string, spec: QualityFormSpec = {}): Action => ({
  name,
  duty,
  states,
  body: { action: value },
  spec,
});
const status: [string, string] = ["status", "Estado"];
const versionActions = (noun: string, base: string) => [
  action(`Enviar ${noun}`, `${base}.submit`, ["DRAFT"], "submit"),
  action(`Devolver ${noun} a borrador`, `${base}.edit`, ["SUBMITTED"], "return_to_draft"),
  action(`Aprobar ${noun}`, `${base}.approve`, ["SUBMITTED"], "approve"),
  { name: `Crear sucesor de ${noun}`, duty: `${base}.edit`, states: ["APPROVED"], endpoint: "/successor" },
];
const requestFields = [
  f("request_number", "Número de solicitud"),
  id("itp_item_id", "Punto ITP", "/itp-items"),
  instant("requested_at", "Fecha de solicitud"),
  instant("requested_for", "Fecha prevista"),
  id("inspector_user_id", "Inspector ID"),
  f("quantity", "Cantidad objeto", { kind: "decimal", required: false }),
  f("uom", "Unidad objeto", { required: false }),
  doc(true),
];
const requestActions = (type: string) => [
  action("Enviar solicitud", `${type}.request`, ["DRAFT"], "submit"),
  action("Programar solicitud", `${type}.schedule`, ["SUBMITTED"], "schedule"),
  action("Iniciar inspección o ensayo", `${type}.perform`, ["SCHEDULED"], "start"),
  action("Cancelar solicitud", `${type}.request`, ["DRAFT", "SUBMITTED", "SCHEDULED"], "cancel"),
];
const resultFields = [
  f("record_number", "Número de registro"),
  catalog("result", "Resultado declarado", "result_codes"),
  notes("comments", "Comentarios", false),
  doc(true),
];
const resultActions = (type: string) => [
  action("Enviar resultado", `${type}.perform`, ["DRAFT"], "submit"),
  action("Cerrar resultado", `${type}.close`, ["SUBMITTED"], "close"),
];
export const entities: Record<string, Entity> = {
  "Quality Plans": {
    path: "/plans",
    columns: [["code", "Código"], ["title", "Plan"], ["revision", "Revisión"], ["effective_date", "Vigencia"], status],
    create: {
      name: "Crear plan de calidad",
      duty: "plan.edit",
      spec: {
        fields: [
          f("code", "Código del plan"),
          f("title", "Título del plan"),
          notes("scope", "Alcance del plan"),
          id("responsible_user_id", "Responsable ID"),
          date("effective_date", "Vigente desde"),
          f("source_references", "Ámbitos canónicos del plan", {
            kind: "json",
            required: false,
            help: "Lista de referencias tipadas Scope, Plan, CWP, IWP, Workfront geográfico o actividad P6 aceptada.",
          }),
          doc(true),
        ],
      },
    },
    actions: versionActions("plan", "plan"),
  },
  ITP: {
    path: "/itps",
    columns: [["code", "Código"], ["title", "ITP"], ["revision", "Revisión"], ["effective_date", "Vigencia"], status],
    create: {
      name: "Crear ITP",
      duty: "itp.edit",
      spec: {
        fields: [
          f("code", "Código ITP"),
          f("title", "Título ITP"),
          id("quality_plan_id", "Plan de calidad", "/plans"),
          notes("description", "Descripción ITP", false),
          f("discipline", "Disciplina", { initial: "GENERAL" }),
          date("effective_date", "Vigente desde"),
          f("source_references", "Ámbitos canónicos ITP", {
            kind: "json",
            required: false,
            help: "Lista target_kind y target_id; P6 usa schedule_version_id y external_id.",
          }),
          doc(true),
        ],
        pins: [engineering],
      },
    },
    actions: versionActions("ITP", "itp"),
  },
  "ITP Control Points": {
    path: "/itp-items",
    columns: [
      ["itp_item_code", "Punto"],
      ["itp_id", "ITP"],
      ["sequence", "Secuencia"],
      ["control_type", "Control"],
      ["activity", "Actividad"],
      status,
    ],
    create: {
      name: "Crear punto de control ITP",
      duty: "itp.edit",
      spec: {
        fields: [
          id("itp_id", "ITP", "/itps"),
          f("itp_item_code", "Código del punto"),
          f("sequence", "Secuencia", { kind: "integer" }),
          f("activity", "Actividad inspeccionada"),
          catalog("control_type", "Tipo de control", "control_point_types"),
          notes("requirement_reference", "Requisito técnico"),
          notes("acceptance_criteria", "Criterio de aceptación"),
          f("responsible_party", "Parte responsable"),
          f("witness_party", "Parte testigo", { required: false }),
          catalog("checklist_template_code", "Plantilla de checklist", "checklist_templates"),
          f("evidence_required", "Exige evidencia", { kind: "boolean", initial: "true" }),
          f("required", "Punto obligatorio", { kind: "boolean", initial: "true" }),
          f("inspection_required", "Exige inspección", { kind: "boolean", initial: "true" }),
          f("test_required", "Exige ensayo", { kind: "boolean", initial: "false" }),
          f("test_type", "Tipo de ensayo", { catalog: "test_types", when: { key: "test_required", values: ["true"] } }),
          f("test_uom", "Unidad de ensayo", { required: false }),
          f("test_lower_limit", "Límite inferior de ensayo", { kind: "decimal", required: false }),
          f("test_upper_limit", "Límite superior de ensayo", { kind: "decimal", required: false }),
          f("next_step_rule", "Regla de continuidad", { required: false }),
        ],
      },
    },
  },
  "Inspection Requests": {
    path: "/inspection-requests",
    columns: [
      ["request_number", "Solicitud"],
      ["itp_item_id", "Punto ITP"],
      ["requested_for", "Programada"],
      ["inspector_user_id", "Inspector"],
      status,
    ],
    create: {
      name: "Crear solicitud de inspección",
      duty: "inspection.request",
      spec: {
        fields: [
          ...requestFields,
          catalog("inspection_type", "Tipo de inspección", "inspection_types"),
          id("reinspection_of_id", "Inspección original", "/inspections", false),
          id("corrective_action_id", "Acción correctiva", "/corrective-actions", false),
        ],
        pins: [subject],
      },
    },
    actions: requestActions("inspection"),
  },
  Inspections: {
    path: "/inspections",
    columns: [
      ["record_number", "Registro"],
      ["request_id", "Solicitud"],
      ["inspected_at", "Inspección"],
      ["result", "Resultado"],
      status,
    ],
    create: {
      name: "Registrar inspección",
      duty: "inspection.perform",
      spec: {
        capture: "inspection",
        fields: [...resultFields, instant("inspected_at", "Fecha real de inspección")],
        pins: [engineering],
      },
    },
    actions: resultActions("inspection"),
  },
  "Test Requests": {
    path: "/test-requests",
    columns: [["request_number", "Solicitud"], ["test_type", "Tipo"], ["requested_for", "Programada"], status],
    create: {
      name: "Crear solicitud de ensayo",
      duty: "test.request",
      spec: {
        fields: [
          ...requestFields,
          catalog("test_type", "Tipo de ensayo", "test_types"),
          id("laboratory_vendor_id", "Laboratorio Vendor ID", undefined, false),
        ],
        pins: [subject],
      },
    },
    actions: requestActions("test"),
  },
  Tests: {
    path: "/tests",
    columns: [
      ["record_number", "Registro"],
      ["request_id", "Solicitud"],
      ["tested_at", "Ensayo"],
      ["result", "Resultado"],
      status,
    ],
    create: {
      name: "Registrar ensayo",
      duty: "test.perform",
      spec: {
        capture: "test",
        fields: [
          ...resultFields,
          instant("tested_at", "Fecha real de ensayo"),
          f("method", "Método"),
          f("standard", "Estándar"),
          id("laboratory_vendor_id", "Laboratorio Vendor ID", undefined, false),
          f("equipment_valid_from", "Calibración válida desde", { kind: "datetime", required: false }),
          f("equipment_valid_to", "Calibración válida hasta", { kind: "datetime", required: false }),
          f("equipment_calibration_document", "Evidencia CDE de calibración", { kind: "document", required: false }),
        ],
        pins: [
          engineering,
          {
            key: "equipment_source_reference",
            label: "Equipo Field para ensayo",
            types: ["FIELD_EQUIPMENT_REFERENCE"],
            required: false,
          },
        ],
      },
    },
    actions: resultActions("test"),
  },
  NCR: {
    path: "/ncrs",
    columns: [
      ["ncr_number", "NCR"],
      ["title", "No conformidad"],
      ["severity", "Severidad"],
      ["detected_at", "Detección"],
      status,
    ],
    create: {
      name: "Registrar NCR",
      duty: "ncr.record",
      spec: {
        fields: [
          f("ncr_number", "Número NCR"),
          f("title", "Título NCR"),
          notes("description", "Descripción NCR"),
          catalog("category", "Categoría NCR", "ncr_categories"),
          catalog("severity", "Severidad NCR", "severities"),
          id("responsible_user_id", "Responsable ID"),
          id("inspection_record_id", "Inspección relacionada", "/inspections", false),
          id("test_record_id", "Ensayo relacionado", "/tests", false),
          notes("requirement_reference", "Requisito incumplido"),
          instant("detected_at", "Fecha de detección"),
          f("due_date", "Vencimiento NCR", { kind: "date", required: false }),
          doc(),
        ],
        pins: [subject],
      },
    },
    actions: [
      action("Emitir NCR", "ncr.issue", ["DRAFT"], "issue"),
      action("Revisar NCR", "ncr.review", ["ISSUED"], "review"),
      action("Aplicar disposición NCR", "ncr.disposition", ["UNDER_REVIEW"], "disposition", {
        fields: [id("disposition_id", "Disposición aprobada", "/dispositions")],
      }),
      action("Confirmar corrección NCR", "ncr.correct", ["DISPOSITIONED"], "correct"),
      action("Verificar NCR", "ncr.verify", ["CORRECTED"], "verify"),
      action("Cerrar NCR", "ncr.close", ["VERIFIED"], "close"),
      action("Cancelar NCR", "ncr.review", ["DRAFT", "ISSUED", "UNDER_REVIEW"], "cancel"),
      action("Rechazar NCR", "ncr.review", ["ISSUED", "UNDER_REVIEW"], "reject"),
    ],
  },
  Dispositions: {
    path: "/dispositions",
    columns: [["disposition_code", "Código"], ["ncr_id", "NCR"], ["disposition_type", "Disposición"], status],
    create: {
      name: "Preparar disposición NCR",
      duty: "ncr.disposition",
      spec: {
        fields: [
          id("ncr_id", "NCR", "/ncrs"),
          f("disposition_code", "Código de disposición"),
          catalog("disposition_type", "Tipo de disposición", "dispositions"),
          notes("description", "Descripción de disposición"),
          doc(),
        ],
        pins: [
          {
            ...engineering,
            key: "engineering_decision_reference",
            label: "Decisión técnica Engineering",
            required: false,
          },
        ],
      },
    },
    actions: [
      action("Aprobar disposición", "ncr.disposition", ["PROPOSED"], "approve"),
      action("Rechazar disposición", "ncr.disposition", ["PROPOSED"], "reject"),
    ],
  },
  "Corrective Actions": {
    path: "/corrective-actions",
    columns: [
      ["action_code", "Acción"],
      ["action_kind", "Tipo"],
      ["ncr_id", "NCR"],
      ["owner_user_id", "Responsable"],
      ["due_date", "Vencimiento"],
      status,
    ],
    create: {
      name: "Registrar acción de calidad",
      duty: "action.record",
      spec: {
        fields: [
          f("action_code", "Código de acción"),
          f("action_kind", "Tipo de acción", {
            choices: ["CORRECTIVE", "PREVENTIVE", "IMPROVEMENT"],
            initial: "CORRECTIVE",
          }),
          id("ncr_id", "NCR", "/ncrs", false),
          notes("description", "Descripción de acción"),
          id("owner_user_id", "Dueño ID"),
          date("due_date", "Vencimiento"),
          doc(),
        ],
        pins: [subject],
      },
    },
    actions: [
      action("Iniciar acción", "action.record", ["OPEN"], "start"),
      action("Completar acción", "action.complete", ["IN_PROGRESS"], "complete", {
        fields: [doc()],
        pins: [
          {
            key: "completion_field_reference",
            label: "Evidencia Field de corrección",
            types: ["FIELD_REWORK", "FIELD_PRODUCTION"],
            required: true,
          },
        ],
      }),
      action("Verificar acción", "action.verify", ["COMPLETED"], "verify", {
        fields: [doc()],
        pins: [
          {
            key: "verification_reference",
            label: "Resultado verificado Quality",
            types: ["INSPECTION", "TEST"],
            quality: true,
            required: true,
          },
        ],
      }),
      action("Cerrar acción", "action.verify", ["VERIFIED"], "close"),
    ],
  },
  Reinspections: {
    path: "/inspection-requests",
    reinspectionOnly: true,
    columns: [
      ["request_number", "Solicitud"],
      ["reinspection_of_id", "Resultado original"],
      ["corrective_action_id", "Acción"],
      status,
    ],
    create: {
      name: "Solicitar reinspección",
      duty: "inspection.request",
      spec: {
        fields: [
          ...requestFields,
          catalog("inspection_type", "Tipo de inspección", "inspection_types"),
          id("reinspection_of_id", "Inspección original", "/inspections"),
          id("corrective_action_id", "Acción correctiva", "/corrective-actions"),
        ],
        pins: [subject],
      },
    },
    actions: requestActions("inspection"),
  },
  "Quality Acceptance": {
    path: "/acceptances",
    columns: [
      ["acceptance_code", "Aceptación"],
      ["itp_id", "ITP"],
      ["quantity", "Cantidad"],
      ["uom", "Unidad"],
      ["effective_at", "Vigencia"],
      status,
    ],
    create: {
      name: "Registrar aceptación de calidad",
      duty: "acceptance.approve",
      spec: {
        fields: [
          f("acceptance_code", "Código de aceptación"),
          id("itp_id", "ITP aplicable", "/itps"),
          catalog("acceptance_profile_code", "Perfil de aceptación", "acceptance_profiles"),
          f("quantity", "Cantidad aceptada", { kind: "decimal" }),
          f("uom", "Unidad aceptada"),
          instant("effective_at", "Fecha efectiva de aceptación"),
          id("supersedes_id", "Aceptación sustituida", "/acceptances", false),
          doc(),
        ],
        pins: [subject],
      },
    },
  },
  "Punch and Deficiencies": {
    path: "/punch-items",
    columns: [
      ["item_number", "Ítem"],
      ["description", "Deficiencia"],
      ["category", "Categoría"],
      ["responsible_user_id", "Responsable"],
      ["due_date", "Vencimiento"],
      status,
    ],
    create: {
      name: "Registrar deficiencia",
      duty: "punch.record",
      spec: {
        fields: [
          f("item_number", "Número de deficiencia"),
          notes("description", "Descripción de deficiencia"),
          catalog("category", "Categoría de deficiencia", "punch_categories"),
          id("responsible_user_id", "Responsable ID"),
          date("due_date", "Vencimiento"),
          doc(),
        ],
        pins: [subject],
      },
    },
    actions: [
      action("Iniciar corrección de deficiencia", "punch.record", ["OPEN"], "start"),
      action("Enviar deficiencia a verificación", "punch.record", ["IN_PROGRESS"], "ready", { fields: [doc()] }),
      action("Cerrar deficiencia", "punch.verify", ["READY_FOR_VERIFICATION"], "close", {
        fields: [f("verification_result", "Resultado de verificación", { choices: ["PASS"] }), doc()],
      }),
    ],
  },
};
export const tabs = [
  "Quality Dashboard",
  ...Object.keys(entities),
  "Hold and Witness Decisions",
  "Quality Readiness",
  "Quality Look-Ahead",
  "Material Lot Traceability",
  "Readiness Evidence Assessments",
  "Consumers",
  "Trace",
  "History",
];
