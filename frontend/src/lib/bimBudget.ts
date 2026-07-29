import type { ApuResourceLine, QuantityTakeoffLine } from "../types";

export type BimBudgetGate = "ready" | "review" | "blocked";

export type BimBudgetRow = {
  apuStructure: ApuResourceLine[];
  cbsCode: string;
  code: string;
  currency: string;
  elementRefs: string[];
  fbsCode: string;
  lineIds: number[];
  name: string;
  packageCode: string;
  quantity: number;
  sourceKey: string;
  sourceUrl: string;
  status: string;
  totalAmount: number;
  unit: string;
  unitRate: number;
  wbsCode: string;
};

export type BimBudgetSummary = {
  assignedLineCount: number;
  currencyTotals: Array<{ amount: number; currency: string }>;
  duplicateLineCount: number;
  gate: BimBudgetGate;
  missingAssignmentCount: number;
  rows: BimBudgetRow[];
  sourceLineCount: number;
  unitConflictCount: number;
};

type WorkbookProject = {
  projectCode: string;
  projectName: string;
};

function record(value: unknown) {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function text(source: Record<string, unknown>, key: string) {
  const value = source[key];
  return typeof value === "string" ? value.trim() : "";
}

function number(source: Record<string, unknown>, key: string) {
  const value = source[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function normalizedResourceLine(value: unknown, fallbackUnit: string): ApuResourceLine | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const source = value as Record<string, unknown>;
  const quantity = Number(source.quantity ?? 1);
  const unitRate = Number(source.unit_rate ?? source.amount ?? 0);
  const amount = Number(source.amount ?? quantity * unitRate);
  return {
    amount: Number.isFinite(amount) ? amount : 0,
    code: typeof source.code === "string" ? source.code : undefined,
    component: String(source.component ?? "Costo directo"),
    component_type: typeof source.component_type === "string" ? source.component_type : undefined,
    description: String(source.description ?? "Componente APU"),
    quantity: Number.isFinite(quantity) ? quantity : 0,
    source: typeof source.source === "string" ? source.source : undefined,
    status: typeof source.status === "string" ? source.status : undefined,
    unit: String(source.unit ?? fallbackUnit ?? "und"),
    unit_rate: Number.isFinite(unitRate) ? unitRate : 0,
  };
}

function resourceLines(source: Record<string, unknown>, unit: string, unitRate: number) {
  const values = Array.isArray(source.apu_structure) ? source.apu_structure : [];
  const normalized = values
    .map((value) => normalizedResourceLine(value, unit))
    .filter((value): value is ApuResourceLine => Boolean(value));
  if (normalized.length) return normalized;
  return [
    {
      amount: unitRate,
      component: "Costo directo",
      component_type: "DIRECT_COST",
      description: "Precio unitario asignado; desglose APU pendiente de revision.",
      quantity: 1,
      status: "review",
      unit: unit || "und",
      unit_rate: unitRate,
    },
  ];
}

function controlledQuantity(line: QuantityTakeoffLine, assignment: Record<string, unknown>) {
  const assignedQuantity = number(assignment, "quantity");
  if (assignedQuantity !== null) return assignedQuantity;
  const measurement = record(line.raw_data?.controlled_measurement);
  return number(measurement, "quantity") ?? Number(line.quantity || 0);
}

function sourceElementRef(line: QuantityTakeoffLine) {
  return line.element_guid || line.element_id || line.source_row_id || `LINE-${line.id}`;
}

export function buildBimBudget(lines: QuantityTakeoffLine[], defaultCurrency = "COP"): BimBudgetSummary {
  const rows = new Map<string, BimBudgetRow>();
  const duplicateKeys = new Set<string>();
  const itemUnits = new Map<string, Set<string>>();
  let assignedLineCount = 0;
  let duplicateLineCount = 0;
  let missingAssignmentCount = 0;

  for (const line of lines) {
    const assignment = record(line.raw_data?.budget_item_assignment);
    const code = text(assignment, "cost_item_code");
    const name = text(assignment, "cost_item_name");
    const unitRate = number(assignment, "unit_rate") ?? 0;
    const unit = text(assignment, "budget_unit") || line.unit || "und";
    if (!Object.keys(assignment).length || (!code && !name) || unitRate <= 0) {
      missingAssignmentCount += 1;
      continue;
    }

    const elementRef = sourceElementRef(line);
    const duplicateKey = [elementRef, line.measurement_rule || "measurement", code || name, unit.toLowerCase()].join(
      "|"
    );
    if (duplicateKeys.has(duplicateKey)) {
      duplicateLineCount += 1;
      continue;
    }
    duplicateKeys.add(duplicateKey);

    const quantity = controlledQuantity(line, assignment);
    const currency = text(assignment, "currency") || defaultCurrency;
    const status = text(assignment, "status") || "assigned";
    const wbsCode = text(assignment, "wbs_code") || line.wbs_code;
    const cbsCode = text(assignment, "cbs_code") || line.cbs_code;
    const fbsCode = text(assignment, "fbs_code") || line.fbs_code;
    const packageCode = text(assignment, "package_code") || line.package_code;
    const totalAmount = Math.round(quantity * unitRate * 100) / 100;
    const aggregationKey = [code || name, wbsCode, cbsCode, fbsCode, packageCode, unit, currency, unitRate].join("|");
    const unitKey = [code || name, wbsCode, cbsCode].join("|");
    if (!itemUnits.has(unitKey)) itemUnits.set(unitKey, new Set());
    itemUnits.get(unitKey)?.add(unit.toLowerCase());
    assignedLineCount += 1;

    const current = rows.get(aggregationKey);
    if (current) {
      current.quantity = Math.round((current.quantity + quantity) * 1_000_000) / 1_000_000;
      current.totalAmount = Math.round((current.totalAmount + totalAmount) * 100) / 100;
      current.lineIds.push(line.id);
      if (!current.elementRefs.includes(elementRef)) current.elementRefs.push(elementRef);
      continue;
    }

    rows.set(aggregationKey, {
      apuStructure: resourceLines(assignment, unit, unitRate),
      cbsCode,
      code,
      currency,
      elementRefs: [elementRef],
      fbsCode,
      lineIds: [line.id],
      name,
      packageCode,
      quantity,
      sourceKey: text(assignment, "source_key"),
      sourceUrl: text(assignment, "source_url"),
      status,
      totalAmount,
      unit,
      unitRate,
      wbsCode,
    });
  }

  const consolidatedRows = Array.from(rows.values()).sort(
    (left, right) =>
      left.wbsCode.localeCompare(right.wbsCode, undefined, { numeric: true }) ||
      left.code.localeCompare(right.code, undefined, { numeric: true }) ||
      left.unit.localeCompare(right.unit)
  );
  const unitConflictCount = Array.from(itemUnits.values()).filter((units) => units.size > 1).length;
  const totals = new Map<string, number>();
  for (const row of consolidatedRows) {
    totals.set(row.currency, Math.round(((totals.get(row.currency) ?? 0) + row.totalAmount) * 100) / 100);
  }
  const currencyTotals = Array.from(totals.entries())
    .map(([currency, amount]) => ({ amount, currency }))
    .sort((left, right) => left.currency.localeCompare(right.currency));
  const gate: BimBudgetGate =
    duplicateLineCount > 0 || unitConflictCount > 0
      ? "blocked"
      : !consolidatedRows.length ||
          missingAssignmentCount > 0 ||
          consolidatedRows.some((row) => row.status !== "assigned")
        ? "review"
        : "ready";

  return {
    assignedLineCount,
    currencyTotals,
    duplicateLineCount,
    gate,
    missingAssignmentCount,
    rows: consolidatedRows,
    sourceLineCount: lines.length,
    unitConflictCount,
  };
}

function xmlEscape(value: unknown) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

function xmlCell(value: string | number, type: "Number" | "String" = "String") {
  return `<Cell><Data ss:Type="${type}">${xmlEscape(value)}</Data></Cell>`;
}

function xmlRow(values: Array<string | number>) {
  return `<Row>${values.map((value) => xmlCell(value, typeof value === "number" ? "Number" : "String")).join("")}</Row>`;
}

export function buildBimBudgetExcelXml(summary: BimBudgetSummary, project: WorkbookProject) {
  const budgetRows = [
    xmlRow([
      "Partida",
      "Descripcion",
      "WBS",
      "CBS",
      "FBS",
      "Paquete",
      "Cantidad",
      "Unidad",
      "Precio unitario",
      "Moneda",
      "Total",
      "Elementos IFC",
      "Lineas fuente",
      "Estado",
    ]),
    ...summary.rows.map((row) =>
      xmlRow([
        row.code,
        row.name,
        row.wbsCode,
        row.cbsCode,
        row.fbsCode,
        row.packageCode,
        row.quantity,
        row.unit,
        row.unitRate,
        row.currency,
        row.totalAmount,
        row.elementRefs.join(", "),
        row.lineIds.join(", "),
        row.status,
      ])
    ),
  ].join("");
  const resourceRows = [
    xmlRow(["Partida", "Componente", "Tipo", "Descripcion", "Cantidad APU", "Unidad", "Precio", "Importe"]),
    ...summary.rows.flatMap((row) =>
      row.apuStructure.map((resource) =>
        xmlRow([
          row.code,
          resource.component,
          resource.component_type ?? "",
          resource.description,
          resource.quantity,
          resource.unit,
          resource.unit_rate,
          resource.amount,
        ])
      )
    ),
  ].join("");
  const controlRows = [
    xmlRow(["Proyecto", project.projectName]),
    xmlRow(["Codigo", project.projectCode]),
    xmlRow(["Gate", summary.gate]),
    xmlRow(["Lineas fuente", summary.sourceLineCount]),
    xmlRow(["Lineas asignadas", summary.assignedLineCount]),
    xmlRow(["Sin partida", summary.missingAssignmentCount]),
    xmlRow(["Duplicados excluidos", summary.duplicateLineCount]),
    xmlRow(["Conflictos de unidad", summary.unitConflictCount]),
    ...summary.currencyTotals.map((total) => xmlRow([`Total ${total.currency}`, total.amount])),
  ].join("");

  return `<?xml version="1.0"?>
<?mso-application progid="Excel.Sheet"?>
<Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
 xmlns:o="urn:schemas-microsoft-com:office:office"
 xmlns:x="urn:schemas-microsoft-com:office:excel"
 xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
 <Worksheet ss:Name="Presupuesto BIM"><Table>${budgetRows}</Table></Worksheet>
 <Worksheet ss:Name="Estructura APU"><Table>${resourceRows}</Table></Worksheet>
 <Worksheet ss:Name="Control"><Table>${controlRows}</Table></Worksheet>
</Workbook>`;
}
