export const procurementTabs = [
  "Procurement Register",
  "Procurement Packages",
  "Requirements",
  "Requisitions",
  "RFQ",
  "Bid Evaluation",
  "Awards",
  "Purchase Orders",
  "Vendor Progress / Expediting",
  "Inspections",
  "Shipments",
  "Material Receipts",
  "Material Availability",
  "Procurement Look-Ahead",
  "Mappings",
  "History",
] as const;
export type ProcurementTab = (typeof procurementTabs)[number];
export type EntityTab = Exclude<
  ProcurementTab,
  "Procurement Register" | "Procurement Look-Ahead" | "History" | "Mappings" | "Material Availability"
>;

export type FieldSpec = {
  key: string;
  label: string;
  type?: "number" | "date" | "datetime-local" | "textarea" | "checkbox" | "json" | "ids";
  required?: boolean;
  choices?: string[];
  catalog?: string;
  initial?: string;
  help?: string;
};
export type FormSpec = {
  fields?: FieldSpec[];
  lines?: { key: string; label: string; fields: FieldSpec[]; optional?: boolean };
};
export type ActionSpec = FormSpec & {
  path: string;
  permission: string;
  label: string;
  action?: string;
  statuses?: string[];
  method?: "POST" | "PUT";
};
export type EntitySpec = FormSpec & {
  label: string;
  path: string;
  permission: string;
  columns: [string, string][];
  actions?: ActionSpec[];
  hint?: string;
};

const field = (key: string, label: string, type?: FieldSpec["type"], required = true): FieldSpec => ({
  key,
  label,
  type,
  required,
});
const pick = (key: string, label: string, choices: string[], catalog?: string): FieldSpec => ({
  key,
  label,
  choices,
  catalog,
  required: true,
});
const optional = (key: string, label: string, type?: FieldSpec["type"]) => field(key, label, type, false);
const id = (key: string, label: string, required = true) => field(key, label, "number", required);
const qty = (key = "quantity", label = "Cantidad") => field(key, label, "number");
const date = (key: string, label: string, required = true) => field(key, label, "date", required);
const doc = optional("document_reference", "Referencia CDE (document_id, attachment_id)", "json");
const ref = (key: string, label: string) => ({
  ...optional(key, label, "json"),
  help: "Objeto con target_kind, target_id y, si aplica, source_hash.",
});
const transition = (domain: string, action: string, label: string, statuses: string[]): ActionSpec => ({
  path: "/actions",
  action,
  label,
  permission: `${domain}.${action}`,
  statuses,
});
const state: [string, string] = ["status", "Estado"];
const rowsFor = (...fields: [string, string][]): [string, string][] => [["id", "ID"], ...fields];

export const entities: Record<EntityTab, EntitySpec[]> = {
  "Procurement Packages": [
    {
      label: "Paquetes de Procurement",
      path: "/packages",
      permission: "package.create",
      columns: rowsFor(
        ["package_code", "Código"],
        ["title", "Título"],
        ["required_on_site_date", "Necesario en sitio"],
        state
      ),
      fields: [
        field("package_code", "Código del paquete"),
        field("title", "Título"),
        optional("description", "Descripción", "textarea"),
        pick("procurement_type", "Tipo de compra", ["MATERIAL"], "procurement_types"),
        pick("category", "Categoría", ["GENERAL"], "categories"),
        pick("sourcing_method", "Método de compra", ["RFQ"], "sourcing_methods"),
        optional("strategy", "Estrategia", "textarea"),
        optional("long_lead_flag", "Long lead", "checkbox"),
        optional("discipline", "Disciplina"),
        { ...pick("priority", "Prioridad", ["LOW", "NORMAL", "HIGH", "CRITICAL"]), initial: "NORMAL" },
        id("responsible_user_id", "ID del responsable", false),
        id("procurement_manager_id", "ID del gerente de compras", false),
        date("required_on_site_date", "Necesario en sitio"),
        date("planned_rfq_date", "RFQ prevista", false),
        date("planned_award_date", "Award previsto", false),
        date("planned_po_date", "PO prevista", false),
        date("forecast_delivery_date", "Pronóstico de entrega", false),
      ],
      actions: [
        transition("package", "plan", "Planificar paquete", ["DRAFT"]),
        transition("package", "close", "Cerrar paquete", ["PLANNED"]),
        transition("package", "cancel", "Cancelar paquete", ["DRAFT", "PLANNED"]),
        {
          path: "/items",
          permission: "package.item.add",
          label: "Agregar ítem al paquete",
          statuses: ["DRAFT", "PLANNED"],
          fields: [id("requirement_id", "ID del requisito"), qty(), field("uom", "UOM")],
        },
      ],
      hint: "El paquete de Procurement no sustituye al PWP de AWP. Vincule sus IDs en Mappings.",
    },
  ],
  Requirements: [
    {
      label: "Requisitos de Procurement",
      path: "/requirements",
      permission: "requirement.create",
      columns: rowsFor(
        ["requirement_code", "Código"],
        ["description", "Descripción"],
        ["required_quantity", "Cantidad"],
        ["uom", "UOM"],
        state
      ),
      fields: [
        field("requirement_code", "Código del requisito"),
        field("description", "Descripción"),
        field("item_type", "Tipo de ítem"),
        qty("required_quantity", "Cantidad requerida"),
        field("uom", "UOM"),
        id("package_id", "ID de paquete Procurement"),
        date("required_on_site_date", "Necesario en sitio"),
        { ...pick("priority", "Prioridad", ["LOW", "NORMAL", "HIGH", "CRITICAL"]), initial: "NORMAL" },
        ref("source_reference", "Referencia canónica de origen"),
      ],
      actions: [
        transition("requirement", "activate", "Activar requisito", ["DRAFT"]),
        transition("requirement", "cancel", "Cancelar requisito", ["DRAFT"]),
      ],
    },
    {
      label: "Catálogo físico de materiales",
      path: "/material-items",
      permission: "material.catalog",
      columns: rowsFor(
        ["material_code", "Código"],
        ["description", "Descripción"],
        ["category", "Categoría"],
        ["uom", "UOM"]
      ),
      fields: [
        field("material_code", "Código de material"),
        field("description", "Descripción"),
        field("uom", "UOM"),
        pick("category", "Categoría de material", ["GENERAL"], "material_categories"),
        optional("specification", "Especificación", "textarea"),
      ],
    },
    {
      label: "Necesidades físicas de material",
      path: "/material-requirements",
      permission: "material.requirement",
      columns: rowsFor(
        ["requirement_code", "Código"],
        ["material_item_id", "Material ID"],
        ["required_quantity", "Cantidad"],
        ["uom", "UOM"]
      ),
      fields: [
        field("requirement_code", "Código del requisito físico"),
        id("material_item_id", "ID del material"),
        id("procurement_requirement_id", "ID del requisito de Procurement", false),
        qty("required_quantity", "Cantidad requerida"),
        field("uom", "UOM"),
        date("required_on_site_date", "Necesario en sitio", false),
        { ...pick("source_type", "Tipo de referencia física", ["MTO", "BOM"]), required: false },
        optional("evidence", "Evidencia MTO/BOM CDE (document_id, attachment_id)", "json"),
      ],
      actions: [
        {
          path: "/procurement-link",
          method: "PUT",
          permission: "material.requirement",
          label: "Vincular requisito de compra",
          fields: [id("procurement_requirement_id", "ID del requisito de Procurement")],
        },
      ],
    },
  ],
  Requisitions: [
    {
      label: "Requisiciones",
      path: "/requisitions",
      permission: "requisition.create",
      columns: rowsFor(["requisition_number", "Número"], ["package_id", "Paquete"], ["currency", "Moneda"], state),
      fields: [
        field("requisition_number", "Número de requisición"),
        id("package_id", "ID del paquete"),
        field("currency", "Moneda"),
        date("issue_date", "Fecha de emisión"),
        date("required_date", "Fecha requerida"),
        optional("estimated_value", "Valor estimado", "number"),
        ref("technical_reference", "Referencia técnica"),
        optional("notes", "Notas", "textarea"),
        doc,
      ],
      lines: {
        key: "lines",
        label: "Línea de requisición",
        fields: [
          id("line_number", "Número de línea"),
          id("requirement_id", "ID del requisito"),
          field("description", "Descripción"),
          qty(),
          field("uom", "UOM"),
          date("required_date", "Fecha requerida"),
          optional("destination", "Destino"),
          optional("technical_specification_reference", "Especificación técnica"),
          ref("engineering_revision_reference", "Referencia de revisión de Ingeniería"),
        ],
      },
      actions: [
        transition("requisition", "submit", "Enviar requisición", ["DRAFT"]),
        transition("requisition", "approve", "Aprobar requisición", ["SUBMITTED"]),
        transition("requisition", "reject", "Rechazar requisición", ["SUBMITTED"]),
        transition("requisition", "cancel", "Cancelar requisición", ["DRAFT", "SUBMITTED"]),
      ],
    },
  ],
  RFQ: [
    {
      label: "RFQs",
      path: "/rfqs",
      permission: "rfq.create",
      columns: rowsFor(["rfq_number", "Número"], ["requisition_id", "Requisición"], ["closing_date", "Cierre"], state),
      fields: [
        field("rfq_number", "Número de RFQ"),
        id("package_id", "ID del paquete"),
        id("requisition_id", "ID de requisición"),
        date("issue_date", "Fecha de emisión"),
        date("closing_date", "Fecha de cierre"),
        optional("commercial_terms_reference", "Referencia comercial"),
        ref("technical_package_reference", "Referencia técnica"),
        doc,
      ],
      actions: [
        {
          path: "/invitations",
          permission: "rfq.invite",
          label: "Invitar proveedor",
          statuses: ["DRAFT"],
          fields: [id("vendor_id", "ID del proveedor")],
        },
        transition("rfq", "issue", "Emitir RFQ", ["DRAFT"]),
        transition("rfq", "close", "Cerrar RFQ", ["ISSUED"]),
        transition("rfq", "cancel", "Cancelar RFQ", ["DRAFT"]),
      ],
    },
    {
      label: "Proveedores",
      path: "/vendors",
      permission: "vendor.create",
      columns: rowsFor(["vendor_code", "Código"], ["legal_name", "Razón social"], ["country", "País"], state),
      fields: [
        field("vendor_code", "Código del proveedor"),
        field("legal_name", "Razón social"),
        field("display_name", "Nombre comercial"),
        field("business_identifier", "Identificación fiscal"),
        field("country", "País (ISO de dos letras)"),
        optional("contact_reference", "Contacto"),
        optional("qualification_reference", "Referencia de calificación"),
      ],
      actions: [
        transition("vendor", "suspend", "Suspender proveedor", ["ACTIVE"]),
        transition("vendor", "activate", "Reactivar proveedor", ["SUSPENDED"]),
        transition("vendor", "retire", "Retirar proveedor", ["ACTIVE", "SUSPENDED"]),
      ],
    },
  ],
  "Bid Evaluation": [
    {
      label: "Ofertas",
      path: "/bids",
      permission: "bid.create",
      columns: rowsFor(
        ["rfq_id", "RFQ"],
        ["vendor_id", "Proveedor"],
        ["currency", "Moneda"],
        ["total_bid_value", "Valor"],
        state
      ),
      fields: [
        id("rfq_id", "ID de RFQ"),
        id("vendor_id", "ID de proveedor"),
        field("currency", "Moneda"),
        qty("total_bid_value", "Valor ofertado"),
        date("validity_date", "Válida hasta"),
        optional("received_at", "Recepción de oferta UTC", "datetime-local"),
        id("supersedes_id", "ID de oferta predecesora", false),
        doc,
      ],
    },
    {
      label: "Evaluaciones",
      path: "/evaluations",
      permission: "evaluation.record",
      columns: rowsFor(
        ["bid_id", "Oferta"],
        ["evaluation_type", "Tipo"],
        ["result", "Resultado"],
        ["score", "Puntaje"]
      ),
      fields: [
        id("bid_id", "ID de oferta"),
        pick("evaluation_type", "Tipo de evaluación", ["TECHNICAL", "COMMERCIAL"]),
        pick("result", "Resultado", ["ACCEPTED", "REJECTED", "CONDITIONAL"]),
        optional("score", "Puntaje", "number"),
        optional("comments", "Comentarios", "textarea"),
        pick("recommendation", "Recomendación", ["RECOMMEND", "HOLD", "REJECT"]),
        date("evaluated_on", "Fecha de evaluación", false),
        ref("engineering_reference", "Referencia de Ingeniería"),
        doc,
      ],
    },
  ],
  Awards: [
    {
      label: "Adjudicaciones",
      path: "/awards",
      permission: "award.approve",
      columns: rowsFor(["rfq_id", "RFQ"], ["bid_id", "Oferta"], ["vendor_id", "Proveedor"], state),
      fields: [
        id("rfq_id", "ID de RFQ"),
        id("bid_id", "ID de oferta seleccionada"),
        field("approval_reference", "Referencia de aprobación"),
        date("decision_date", "Fecha de adjudicación", false),
      ],
      hint: "Adjudicar no emite una orden de compra. La PO se prepara mediante un comando independiente.",
    },
  ],
  "Purchase Orders": [
    {
      label: "Órdenes de compra",
      path: "/purchase-orders",
      permission: "po.create",
      columns: rowsFor(
        ["po_number", "Número"],
        ["award_id", "Award"],
        ["vendor_id", "Proveedor"],
        ["current_value", "Valor vigente"],
        state
      ),
      fields: [
        field("po_number", "Número de PO"),
        id("award_id", "ID de adjudicación", false),
        id("vendor_id", "ID del proveedor"),
        id("package_id", "ID del paquete"),
        field("currency", "Moneda"),
        date("issue_date", "Fecha de emisión"),
        date("effective_date", "Fecha efectiva"),
        date("expected_delivery_date", "Entrega prevista"),
        id("legacy_purchase_order_id", "ID de PO legacy de referencia", false),
        id("reference_contract_id", "ID de contrato de referencia", false),
        id("reference_commitment_id", "ID de compromiso de referencia", false),
        doc,
      ],
      lines: {
        key: "lines",
        label: "Línea de PO",
        fields: [
          id("line_number", "Número de línea"),
          id("requirement_id", "ID del requisito"),
          field("description", "Descripción"),
          qty(),
          field("uom", "UOM"),
          qty("unit_price", "Precio unitario"),
          date("requested_date", "Fecha solicitada"),
          date("promised_date", "Fecha prometida", false),
          date("forecast_date", "Fecha forecast", false),
        ],
      },
      actions: [
        transition("po", "approve", "Aprobar PO", ["DRAFT"]),
        transition("po", "issue", "Emitir PO", ["APPROVED"]),
        transition("po", "cancel", "Cancelar PO", ["DRAFT"]),
        {
          path: "/revisions",
          permission: "po.revise",
          label: "Preparar revisión de PO",
          statuses: ["ISSUED"],
          fields: [
            date("effective_date", "Fecha efectiva de revisión"),
            ref("schedule_impact_reference", "Referencia a impacto de cronograma"),
          ],
          lines: {
            key: "changed_lines",
            label: "Línea modificada",
            fields: [
              id("line_id", "ID de línea de PO"),
              qty(),
              qty("unit_price", "Precio unitario"),
              date("promised_date", "Fecha prometida", false),
              date("forecast_date", "Fecha forecast", false),
            ],
          },
        },
      ],
    },
  ],
  "Vendor Progress / Expediting": [
    {
      label: "Hitos de fabricación",
      path: "/vendor-milestones",
      permission: "expediting.record",
      columns: rowsFor(
        ["code", "Código"],
        ["po_line_id", "Línea PO"],
        ["planned_date", "Plan"],
        ["forecast_date", "Forecast"],
        ["actual_date", "Real"]
      ),
      fields: [
        id("po_line_id", "ID de línea PO"),
        field("code", "Código del hito"),
        date("planned_date", "Fecha prevista"),
        date("forecast_date", "Fecha forecast", false),
        date("actual_date", "Fecha real", false),
      ],
      actions: [
        {
          path: "/successor",
          permission: "expediting.record",
          label: "Registrar sucesor del hito",
          fields: [date("forecast_date", "Fecha forecast", false), date("actual_date", "Fecha real", false)],
        },
      ],
    },
    {
      label: "Eventos de expediting",
      path: "/expediting-events",
      permission: "expediting.record",
      columns: rowsFor(
        ["event_type", "Tipo"],
        ["po_line_id", "Línea PO"],
        ["observation_date", "Fecha"],
        ["forecast_date", "Forecast"]
      ),
      fields: [
        id("po_line_id", "ID de línea PO"),
        pick("event_type", "Tipo de evento", [
          "MANUFACTURING_STARTED",
          "FABRICATION_PROGRESS",
          "VENDOR_DELAY",
          "RECOVERY_ACTION",
          "INSPECTION_PLANNED",
          "INSPECTION_COMPLETED",
          "DISPATCH_FORECAST",
          "DELIVERY_FORECAST",
        ]),
        date("observation_date", "Fecha de observación"),
        date("forecast_date", "Fecha forecast", false),
        optional("progress_percent", "Porcentaje de fabricación", "number"),
        field("detail", "Detalle", "textarea"),
      ],
    },
  ],
  Inspections: [
    {
      label: "Inspecciones",
      path: "/inspections",
      permission: "inspection.plan",
      columns: rowsFor(["inspection_type", "Tipo"], ["po_line_id", "Línea PO"], ["inspection_date", "Fecha"], state),
      fields: [
        id("po_line_id", "ID de línea PO"),
        pick("inspection_type", "Tipo de inspección", ["FACTORY"], "inspection_types"),
        date("inspection_date", "Fecha de inspección"),
      ],
      actions: [
        {
          path: "/decision",
          permission: "inspection.decide",
          label: "Decidir inspección",
          statuses: ["PLANNED", "SCHEDULED", "COMPLETED"],
          fields: [
            pick("result", "Resultado de inspección", ["ACCEPTED", "REJECTED", "CONDITIONAL"]),
            optional("detail", "Detalle", "textarea"),
            optional("ncr_reference", "Referencia de no conformidad"),
            optional("evidence", "Evidencia documental", "json"),
          ],
        },
      ],
    },
  ],
  Shipments: [
    {
      label: "Embarques",
      path: "/shipments",
      permission: "shipment.manage",
      columns: rowsFor(
        ["shipment_number", "Número"],
        ["vendor_id", "Proveedor"],
        ["destination", "Destino"],
        ["planned_arrival", "Arribo previsto"],
        state
      ),
      fields: [
        field("shipment_number", "Número de embarque"),
        id("vendor_id", "ID de proveedor"),
        field("origin", "Origen"),
        field("destination", "Destino"),
        pick("transport_mode", "Modo de transporte", ["ROAD"], "shipment_modes"),
        date("planned_arrival", "Arribo previsto", false),
        date("forecast_arrival", "Arribo forecast", false),
        optional("carrier_reference", "Referencia de transportista"),
        optional("customs_reference", "Referencia de aduana"),
        optional("evidence", "Documento de embarque CDE", "json"),
      ],
      lines: {
        key: "lines",
        label: "Línea de embarque",
        fields: [
          id("po_line_id", "ID de línea PO"),
          id("material_requirement_id", "ID del requisito físico"),
          qty(),
          field("uom", "UOM"),
        ],
      },
      actions: [
        {
          path: "/transition",
          permission: "shipment.manage",
          label: "Registrar transición de embarque",
          fields: [
            pick("status", "Nuevo estado del embarque", [
              "READY_FOR_DISPATCH",
              "DISPATCHED",
              "IN_TRANSIT",
              "ARRIVED",
              "CANCELLED",
            ]),
            date("event_date", "Fecha del evento"),
            optional("reference", "Referencia"),
          ],
        },
      ],
      hint: "El arribo no registra ni acepta una recepción.",
    },
  ],
  "Material Receipts": [
    {
      label: "Recepciones de material",
      path: "/material-receipts",
      permission: "receipt.record",
      columns: rowsFor(
        ["receipt_number", "Número"],
        ["shipment_id", "Embarque"],
        ["location", "Ubicación"],
        ["received_at", "Recibido"],
        state
      ),
      fields: [
        field("receipt_number", "Número de recepción"),
        id("shipment_id", "ID de embarque"),
        field("location", "Ubicación"),
        field("received_at", "Recepción UTC", "datetime-local"),
        optional("evidence", "Evidencia de recepción CDE", "json"),
      ],
      lines: {
        key: "lines",
        label: "Línea de recepción",
        fields: [id("shipment_line_id", "ID de línea de embarque"), qty(), field("uom", "UOM")],
      },
      actions: [
        {
          path: "/acceptance",
          permission: "receipt.accept",
          label: "Clasificar recepción",
          fields: [
            id("receipt_line_id", "ID de línea de recepción"),
            id("inspection_id", "ID de inspección", false),
            qty("accepted_quantity", "Cantidad aceptada"),
            qty("rejected_quantity", "Cantidad rechazada"),
            qty("quarantine_quantity", "Cantidad en cuarentena"),
            optional("detail", "Detalle", "textarea"),
          ],
        },
      ],
    },
    {
      label: "Asignaciones físicas",
      path: "/material-allocations",
      permission: "allocation.manage",
      columns: rowsFor(
        ["receipt_line_id", "Línea recibida"],
        ["work_package_id", "Paquete AWP"],
        ["quantity", "Cantidad"],
        ["uom", "UOM"],
        state
      ),
      fields: [
        id("receipt_line_id", "ID de línea aceptada"),
        id("material_requirement_id", "ID del requisito físico"),
        id("work_package_id", "ID del CWP o IWP"),
        qty(),
        field("uom", "UOM"),
        date("allocation_date", "Fecha de asignación"),
        field("source_location", "Ubicación de origen"),
      ],
      actions: [
        {
          path: "/release",
          permission: "allocation.manage",
          label: "Liberar asignación física",
          statuses: ["ACTIVE", "ALLOCATED"],
        },
      ],
    },
  ],
};
