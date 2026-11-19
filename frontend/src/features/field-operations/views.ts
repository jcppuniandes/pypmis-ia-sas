import type { Row } from "./api";
import type { FieldSpec, FormSpec } from "./FieldForms";
export type Action = { name: string; duty: string; states: string[]; endpoint?: string; body?: Row; spec?: FormSpec };
export type Entity = {
  path: string;
  columns: [string, string][];
  create?: { name: string; duty: string; spec: FormSpec };
  actions?: Action[];
  details?: boolean;
};
const f = (key: string, label: string, options: Omit<FieldSpec, "key" | "label"> = {}): FieldSpec => ({
  key,
  label,
  required: true,
  ...options,
});
const id = (key: string, label: string, collection?: string, required = true) =>
  f(key, label, { kind: "id", collection, required });
const date = (key: string, label: string, required = true) => f(key, label, { kind: "date", required });
const instant = (key: string, label: string, required = true) => f(key, label, { kind: "datetime", required });
const number = (key: string, label: string, required = true) => f(key, label, { kind: "decimal", required });
const notes = (key: string, label: string, required = true) => f(key, label, { kind: "notes", required });
const json = (key: string, label: string, help: string, required = false) =>
  f(key, label, { kind: "json", help, required });
const catalog = (key: string, label: string, code: string, required = true) =>
  f(key, label, { catalog: code, required });
const doc = (key = "document_reference", label = "Evidencia CDE", required = true) =>
  f(key, label, { kind: "document", required });
const ref = (key: string, label: string, required = true) =>
  f(key, label, { kind: "reference", required, targetKinds: ["SCOPE", "CWA", "GEOGRAPHIC_WORKSPACE"] });
const source = (key: string, label: string, sourceTypes: string[], required = false) =>
  f(key, label, { kind: "pin", required, sourceTypes });
const native = (key: string, label: string, kind: string, required = false) =>
  id(key, label, `/reference-targets?target_kind=${kind}`, required);
const action = (name: string, duty: string, states: string[], code: string, fields: FieldSpec[] = []): Action => ({
  name,
  duty,
  states,
  body: { action: code },
  spec: { fields },
});
const state: [string, string] = ["status", "Estado"];
const workfront = id("workfront_id", "Frente de trabajo", "/workfronts");
const shift = id("shift_id", "Turno", "/shifts");
const usage = [
  f("record_code", "Código del uso"),
  shift,
  workfront,
  json(
    "activity_reference",
    "Actividad referenciada",
    "Referencia canónica; Schedule requiere schedule_version_id y external_id."
  ),
  id("supersedes_id", "Uso anterior ID", undefined, false),
];
const productionFields: FieldSpec[] = [
  f("production_code", "Código de producción"),
  workfront,
  shift,
  id("report_id", "Reporte diario", "/daily-reports", false),
  native("scope_item_id", "Elemento Scope", "SCOPE", true),
  native("plan_item_id", "Plan item", "PLAN"),
  native("iwp_id", "IWP", "IWP"),
  number("quantity", "Cantidad observada"),
  number("planned_quantity", "Cantidad planificada", false),
  f("uom", "Unidad de producción"),
  catalog("production_type", "Tipo de producción", "production_types"),
  instant("observed_at", "Fecha y hora de observación"),
  f("source_reference", "Referencia de origen"),
  ref("location_reference", "Ubicación de producción", false),
  source("engineering_reference", "Revisión IFC de ejecución", ["IFC_RELEASE"]),
  source("material_reference", "Referencia de material", ["MATERIAL_ITEM", "MATERIAL_ALLOCATION"]),
  doc(),
  f("execution_condition", "Condición de ejecución", {
    choices: [
      "IWP_RELEASED",
      "ENABLING_WORKS",
      "EMERGENCY_WORK",
      "SURVEY",
      "TEMPORARY_WORKS",
      "SUPPORT_ACTIVITY",
      "CORRECTIVE_WORK",
      "NON_IWP_ACTIVITY",
    ],
    initial: "IWP_RELEASED",
  }),
  notes("exception_reason", "Motivo de excepción IWP", false),
  notes("variance_reason", "Motivo de variación", false),
  id("supersedes_id", "Producción sustituida", "/production", false),
];
const productionActions = [
  action("Verificar producción", "production.verify", ["RECORDED"], "verify"),
  action("Rechazar producción", "production.verify", ["RECORDED"], "reject"),
];
export const entities: Record<string, Entity> = {
  Workfronts: {
    path: "/workfronts",
    columns: [
      ["workfront_code", "Código"],
      ["title", "Frente"],
      ["planned_start", "Inicio previsto"],
      ["planned_finish", "Fin previsto"],
      state,
    ],
    create: {
      name: "Crear frente de trabajo",
      duty: "workfront.edit",
      spec: {
        fields: [
          f("workfront_code", "Código del frente"),
          f("title", "Título del frente"),
          notes("description", "Descripción", false),
          ref("location_reference", "Ubicación canónica"),
          native("cwa_id", "CWA", "CWA"),
          native("cwp_id", "CWP", "CWP"),
          native("iwp_id", "IWP", "IWP"),
          id("responsible_user_id", "Responsable ID", undefined, false),
          date("planned_start", "Inicio previsto"),
          date("planned_finish", "Fin previsto"),
        ],
      },
    },
    actions: [
      action("Activar frente", "workfront.activate", ["PLANNED"], "activate", [
        date("actual_date", "Fecha real", false),
      ]),
      action("Suspender frente", "workfront.activate", ["ACTIVE"], "suspend"),
      action("Reanudar frente", "workfront.activate", ["SUSPENDED"], "resume"),
      action("Completar frente", "workfront.activate", ["ACTIVE"], "complete", [
        date("actual_date", "Fecha real", false),
      ]),
    ],
  },
  Shifts: {
    path: "/shifts",
    columns: [
      ["shift_code", "Código"],
      ["shift_date", "Fecha"],
      ["workfront_id", "Frente ID"],
      ["start_time", "Inicio"],
      ["end_time", "Fin"],
      state,
    ],
    create: {
      name: "Abrir turno",
      duty: "shift.edit",
      spec: {
        fields: [
          f("shift_code", "Código del turno"),
          catalog("shift_type", "Tipo de turno", "shift_types"),
          date("shift_date", "Fecha del turno"),
          instant("start_time", "Inicio del turno"),
          instant("end_time", "Fin del turno"),
          workfront,
          id("supervisor_user_id", "Supervisor ID", undefined, false),
          f("weather_reference", "Referencia meteorológica", { required: false }),
        ],
      },
    },
    actions: [
      action("Enviar turno", "shift.submit", ["OPEN"], "submit"),
      action("Aprobar turno", "shift.approve", ["SUBMITTED"], "approve"),
      action("Cerrar turno", "shift.close", ["APPROVED"], "close"),
    ],
  },
  "Daily Reports": {
    path: "/daily-reports",
    columns: [
      ["report_number", "Reporte"],
      ["report_date", "Fecha"],
      ["shift_id", "Turno ID"],
      ["reporting_party", "Reportante"],
      state,
    ],
    create: {
      name: "Crear reporte diario",
      duty: "daily.prepare",
      spec: {
        fields: [
          f("report_number", "Número de reporte"),
          date("report_date", "Fecha del reporte"),
          shift,
          f("reporting_party", "Parte reportante"),
          json("workfront_ids", "Frentes adicionales", "Lista de IDs canónicos del mismo proyecto."),
          json("weather", "Condiciones meteorológicas", "Objeto de observación del turno."),
          notes("work_conditions", "Condiciones de trabajo", false),
          notes("comments", "Comentarios", false),
          f("document_references", "Adjuntos CDE", { kind: "document", multiple: true, required: false }),
        ],
      },
    },
    actions: [
      action("Enviar reporte", "daily.submit", ["DRAFT"], "submit"),
      action("Revisar reporte", "daily.review", ["SUBMITTED"], "review"),
      action("Aprobar reporte", "daily.approve", ["REVIEWED"], "approve"),
      action("Cerrar reporte", "daily.close", ["APPROVED"], "close"),
      {
        name: "Crear revisión sucesora",
        duty: "daily.prepare",
        states: ["APPROVED", "CLOSED"],
        endpoint: "/successor",
      },
    ],
  },
  Crews: {
    path: "/crews",
    columns: [
      ["crew_code", "Código"],
      ["description", "Cuadrilla"],
      ["trade", "Oficio"],
      ["vendor_id", "Proveedor ID"],
      state,
    ],
    create: {
      name: "Registrar cuadrilla",
      duty: "crew.edit",
      spec: {
        fields: [
          f("crew_code", "Código de cuadrilla"),
          notes("description", "Descripción de cuadrilla"),
          catalog("trade", "Oficio", "crew_trades"),
          id("vendor_id", "Proveedor Procurement ID", undefined, false),
          id("supervisor_user_id", "Supervisor ID", undefined, false),
        ],
      },
    },
    actions: [
      action("Activar cuadrilla", "crew.edit", ["INACTIVE"], "activate"),
      action("Inactivar cuadrilla", "crew.edit", ["ACTIVE"], "inactivate"),
    ],
  },
  "Equipment References": {
    path: "/equipment-references",
    columns: [
      ["source_system", "Maestro externo"],
      ["external_id", "ID externo"],
      ["description", "Equipo"],
      ["equipment_type", "Tipo"],
      state,
    ],
    create: {
      name: "Vincular referencia de equipo",
      duty: "equipment.edit",
      spec: {
        fields: [
          f("source_system", "Sistema maestro"),
          f("external_id", "Identidad externa del equipo"),
          notes("description", "Descripción del equipo"),
          catalog("equipment_type", "Tipo de equipo", "equipment_types"),
        ],
      },
    },
    actions: [
      action("Marcar equipo disponible", "equipment.edit", ["UNAVAILABLE"], "available"),
      action("Marcar equipo no disponible", "equipment.edit", ["AVAILABLE"], "unavailable"),
    ],
  },
  Labor: {
    path: "/labor",
    columns: [
      ["record_code", "Código"],
      ["crew_id", "Cuadrilla ID"],
      ["shift_id", "Turno"],
      ["headcount", "Personas"],
      ["regular_hours", "Horas regulares"],
      ["overtime_hours", "Horas extra"],
      state,
    ],
    create: {
      name: "Registrar uso de mano de obra",
      duty: "labor.record",
      spec: {
        fields: [
          ...usage,
          id("crew_id", "Cuadrilla", "/crews"),
          catalog("trade", "Oficio", "crew_trades"),
          f("headcount", "Número de personas", { kind: "integer" }),
          number("regular_hours", "Horas regulares"),
          number("overtime_hours", "Horas extra", false),
          number("productive_hours", "Horas productivas", false),
          number("nonproductive_hours", "Horas no productivas", false),
        ],
      },
    },
  },
  "Equipment Usage": {
    path: "/equipment",
    columns: [
      ["record_code", "Código"],
      ["equipment_id", "Equipo ID"],
      ["shift_id", "Turno"],
      ["operating_hours", "Horas operativas"],
      ["idle_hours", "Horas inactivas"],
      state,
    ],
    create: {
      name: "Registrar uso de equipo",
      duty: "equipment.record",
      spec: {
        fields: [
          ...usage,
          id("equipment_id", "Referencia de equipo", "/equipment-references"),
          catalog("usage_type", "Tipo de uso de equipo", "equipment_usage_types"),
          number("operating_hours", "Horas operativas"),
          number("idle_hours", "Horas inactivas", false),
          number("standby_hours", "Horas en espera", false),
          number("downtime_hours", "Horas fuera de servicio", false),
        ],
      },
    },
  },
  "Production Records": {
    path: "/production",
    columns: [
      ["production_code", "Código"],
      ["workfront_id", "Frente"],
      ["shift_id", "Turno"],
      ["scope_item_id", "Scope"],
      ["quantity", "Cantidad"],
      ["uom", "Unidad"],
      state,
    ],
    create: { name: "Registrar producción observada", duty: "production.record", spec: { fields: productionFields } },
    actions: productionActions,
  },
  "Installed Quantity Evidence": {
    path: "/quantity-evidence",
    columns: [
      ["production_code", "Código"],
      ["scope_item_id", "Scope"],
      ["plan_item_id", "Plan"],
      ["iwp_id", "IWP"],
      ["quantity", "Cantidad"],
      ["uom", "Unidad"],
      state,
    ],
  },
  "Field Events": {
    path: "/events",
    columns: [
      ["event_code", "Código"],
      ["event_type", "Tipo"],
      ["title", "Hecho"],
      ["observed_at", "Observado"],
      ["severity", "Severidad"],
      state,
    ],
    create: {
      name: "Registrar evento de campo",
      duty: "event.record",
      spec: {
        fields: [
          f("event_code", "Código del evento"),
          workfront,
          id("shift_id", "Turno", "/shifts", false),
          catalog("event_type", "Tipo de evento", "field_event_types"),
          instant("observed_at", "Fecha y hora del evento"),
          f("title", "Título del evento"),
          notes("description", "Descripción del evento"),
          f("severity", "Severidad", { choices: ["LOW", "MEDIUM", "HIGH", "CRITICAL"], initial: "MEDIUM" }),
          number("duration_hours", "Duración horas", false),
          doc(),
        ],
      },
    },
    actions: [
      action("Revisar evento", "event.classify", ["RECORDED"], "review"),
      action("Cerrar evento", "event.classify", ["REVIEWED"], "close"),
    ],
  },
  "Site Instructions": {
    path: "/instructions",
    columns: [
      ["instruction_number", "Número"],
      ["instruction_type", "Tipo"],
      ["instruction_date", "Fecha"],
      ["issuer", "Emisor"],
      ["recipient", "Receptor"],
      state,
    ],
    create: {
      name: "Preparar instrucción de sitio",
      duty: "instruction.record",
      spec: {
        fields: [
          f("instruction_number", "Número de instrucción"),
          catalog("instruction_type", "Tipo de instrucción", "instruction_types"),
          date("instruction_date", "Fecha de instrucción"),
          f("issuer", "Emisor"),
          f("recipient", "Receptor"),
          workfront,
          native("scope_item_id", "Scope relacionado", "SCOPE"),
          native("iwp_id", "IWP relacionado", "IWP"),
          notes("description", "Descripción de instrucción"),
          doc(),
        ],
      },
    },
    actions: [
      action("Emitir instrucción", "instruction.issue", ["DRAFT"], "issue"),
      action("Acusar instrucción", "instruction.issue", ["ISSUED"], "acknowledge"),
      action("Cerrar instrucción", "instruction.issue", ["ACKNOWLEDGED"], "close"),
    ],
  },
  Rework: {
    path: "/rework",
    columns: [
      ["production_code", "Código"],
      ["original_production_id", "Trabajo original"],
      ["rework_reason", "Motivo"],
      ["quantity", "Cantidad"],
      ["uom", "Unidad"],
      state,
    ],
    create: {
      name: "Registrar retrabajo",
      duty: "rework.record",
      spec: {
        fields: [
          ...productionFields.filter((item) => item.key !== "production_type"),
          id("original_production_id", "Producción original", "/production"),
          catalog("rework_reason", "Motivo de retrabajo", "rework_reasons"),
          f("responsible_party", "Parte responsable referenciada", { required: false }),
        ],
        body: { production_type: "REWORKED" },
      },
    },
    actions: [
      action("Aprobar retrabajo", "rework.approve", ["RECORDED"], "verify"),
      action("Rechazar retrabajo", "rework.approve", ["RECORDED"], "reject"),
    ],
  },
  "Constraints Observed": {
    path: "/constraints",
    columns: [
      ["observation_code", "Código"],
      ["constraint_type", "Tipo"],
      ["workfront_id", "Frente"],
      ["iwp_id", "IWP"],
      ["observation_date", "Fecha"],
      ["severity", "Severidad"],
      state,
    ],
    create: {
      name: "Registrar restricción observada",
      duty: "constraint.record",
      spec: {
        fields: [
          f("observation_code", "Código de observación"),
          catalog("constraint_type", "Tipo de restricción observada", "constraint_observation_types"),
          workfront,
          native("iwp_id", "IWP observado", "IWP"),
          date("observation_date", "Fecha de observación"),
          notes("description", "Descripción de restricción"),
          f("severity", "Severidad", { choices: ["LOW", "MEDIUM", "HIGH", "CRITICAL"], initial: "MEDIUM" }),
          doc(),
        ],
      },
    },
    actions: [
      action("Verificar observación", "constraint.verify", ["REPORTED"], "verify"),
      action("Rechazar observación", "constraint.verify", ["REPORTED"], "reject"),
    ],
  },
  Conditions: {
    path: "/conditions",
    columns: [
      ["condition_code", "Código"],
      ["condition_date", "Fecha"],
      ["weather_condition", "Clima"],
      ["access_condition", "Acceso"],
      ["site_condition", "Sitio"],
      state,
    ],
    create: {
      name: "Registrar condiciones de campo",
      duty: "condition.record",
      spec: {
        fields: [
          f("condition_code", "Código de condición"),
          date("condition_date", "Fecha de condición"),
          shift,
          workfront,
          ref("location_reference", "Ubicación de condición"),
          catalog("weather_condition", "Condición meteorológica", "weather_conditions"),
          number("temperature", "Temperatura", false),
          number("rainfall", "Lluvia", false),
          number("wind", "Viento", false),
          catalog("access_condition", "Condición de acceso", "site_condition_types"),
          notes("site_condition", "Condiciones del sitio"),
          f("source", "Fuente de observación"),
        ],
      },
    },
  },
  "Material Consumption": {
    path: "/material-consumption",
    columns: [
      ["consumption_code", "Código"],
      ["production_record_id", "Producción"],
      ["material_item_id", "Material"],
      ["quantity", "Cantidad"],
      ["uom", "Unidad"],
      state,
    ],
    create: {
      name: "Registrar material consumido",
      duty: "material.record",
      spec: {
        fields: [
          f("consumption_code", "Código de consumo"),
          id("production_record_id", "Producción verificada", "/production"),
          native("material_item_id", "Material Procurement", "MATERIAL_ITEM", true),
          source("allocation_reference", "Asignación material", ["MATERIAL_ALLOCATION"], true),
          date("consumption_date", "Fecha de consumo"),
          number("quantity", "Cantidad consumida"),
          f("uom", "Unidad de material"),
          doc(),
        ],
      },
    },
  },
  Mappings: {
    path: "/mappings",
    columns: [
      ["source_kind", "Origen"],
      ["source_id", "ID de origen"],
      ["action", "Decisión"],
      ["version", "Revisión"],
    ],
    create: {
      name: "Registrar vínculo de campo",
      duty: "mapping.edit",
      spec: {
        fields: [
          f("source_kind", "Clase de origen", {
            choices: ["WORKFRONT", "PRODUCTION", "EVENT", "INSTRUCTION", "CONSTRAINT"],
          }),
          id("source_id", "ID de origen"),
          json(
            "target_reference",
            "Referencia de destino",
            "Objeto target_kind/target_id; para Schedule, schedule_version_id y external_id.",
            true
          ),
          f("action", "Decisión de vínculo", { choices: ["SET", "REMOVE"], initial: "SET" }),
        ],
      },
    },
    details: false,
  },
};
export const tabs = [
  "Field Dashboard",
  ...Object.keys(entities),
  "Field Readiness",
  "Field Look-Ahead",
  "Consumers",
  "Trace",
  "History",
] as const;
