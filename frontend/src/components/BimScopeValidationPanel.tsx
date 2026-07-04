import { useState } from "react";
import { Calculator, ClipboardCheck, GitBranch, Network } from "lucide-react";
import BimApuReviewPanel from "./BimApuReviewPanel";
import BimGeometryBatchPanel from "./BimGeometryBatchPanel";
import { evaluateQuantityRule, summarizeQuantityRules, type QuantityRuleResult } from "../lib/bimQuantityRules";
import type {
  BimQuantityRule,
  BimQuantityRuleUpdate,
  BimGeometryMeasurementBatch,
  BimModel,
  ApuResourceLine,
  ColombiaApuCatalogItem,
  ColombiaApuCatalogSync,
  CostBreakdownStructure,
  ControlledMeasurementApproval,
  FundingSource,
  QuantityControlCodeAssignment,
  QuantityRuleRecalculation,
  QuantityTakeoffLine,
  QuantityTakeoffRun,
  WbsNode,
  WorkPackage,
} from "../types";

type ScopeCandidate = {
  assignedQuantity: number;
  budgetItem: BudgetItemAssignment | null;
  blockers: string[];
  calculation: QuantityCalculationSummary;
  cbsCodes: string[];
  controlledMeasurementLabel: string;
  elementRefs: string[];
  fbsCodes: string[];
  id: string;
  ifcClasses: string[];
  lineIds: number[];
  measurementRules: string[];
  name: string;
  packageCodes: string[];
  pbsBasis: string;
  pendingQuantity: number;
  quantity: number;
  quantityRule: QuantityRuleResult;
  sourceCount: number;
  status: string;
  unit: string;
  wbsCodes: string[];
};

type BudgetItemAssignment = {
  apuStructure: ApuResourceLine[];
  budgetAmount: number;
  budgetUnit: string;
  catalogItemId?: number | null;
  code: string;
  currency?: string;
  isSuggestion?: boolean;
  licenseNote?: string;
  matchScore?: number | null;
  name: string;
  quantity: number;
  sourceKey?: string;
  sourceUrl?: string;
  status?: string;
  structureNote?: string;
  structureStatus?: string;
  unitRate: number;
};

type BimScopeValidationPanelProps = {
  lines: QuantityTakeoffLine[];
  wbsCatalog?: WbsNode[];
  cbsCatalog?: CostBreakdownStructure[];
  fbsFundingSources?: FundingSource[];
  workPackages?: WorkPackage[];
  quantityRules?: BimQuantityRule[];
  colombiaApuCatalog?: ColombiaApuCatalogItem[];
  colombiaApuSync?: ColombiaApuCatalogSync | null;
  showApuCatalogBridge?: boolean;
  approvalDisabled?: boolean;
  assignmentDisabled?: boolean;
  apuActionDisabled?: boolean;
  geometryBatch?: BimGeometryMeasurementBatch | null;
  geometryBatchDisabled?: boolean;
  geometryModelAvailable?: boolean;
  geometryModels?: BimModel[];
  geometryModelStatusMessage?: string;
  geometryRun?: QuantityTakeoffRun;
  onApproveControlledMeasurement?: (payload: ControlledMeasurementApproval) => void | Promise<void>;
  onAssignControlCodes?: (payload: QuantityControlCodeAssignment) => void | Promise<void>;
  onApproveApuForLines?: (lineIds: number[]) => void | Promise<void>;
  onAnalyzeGeometryBatch?: () => void | Promise<void>;
  onApplyGeometryBatch?: () => void | Promise<void>;
  onLinkGeometryModel?: (modelId: number) => void | Promise<void>;
  onOpenBimBudget?: () => void;
  onSuggestApuForLines?: (lineIds: number[]) => void | Promise<void>;
  onSyncColombiaApuCatalog?: () => void | Promise<void>;
  onUpdateQuantityRule?: (ruleId: number, payload: BimQuantityRuleUpdate) => void | Promise<void>;
  onRecalculateQuantityRules?: () => void | Promise<void>;
  recalculationSummary?: QuantityRuleRecalculation | null;
  recalculateDisabled?: boolean;
};

type QuantityRuleDraft = {
  element_label: string;
  expected_measure: string;
  rule_hint: string;
  expected_units: string;
  status: string;
};

type QuantityApprovalDraft = {
  quantity: string;
  unit: string;
};

type ControlCodeAssignmentDraft = {
  budget_unit: string;
  wbs_code: string;
  cbs_code: string;
  fbs_code: string;
  package_code: string;
  cost_item_code: string;
  cost_item_name: string;
  unit_rate: string;
};

type QuantityCalculationSummary = {
  confidence: string;
  fallbackLabel: string;
  recommendedLabel: string;
  source: string;
  sourceLabel: string;
  status: string;
};

function compact(value: string | null | undefined) {
  return value?.trim() ?? "";
}

function unique(values: string[]) {
  return Array.from(new Set(values.map(compact).filter(Boolean)));
}

function pbsBasisFor(line: QuantityTakeoffLine) {
  const productLocation = unique([line.project_name, line.site_name, line.building_name, line.storey, line.zone_name]);
  const systemGrouping = unique([line.system_name, line.assembly_name]);
  return [...productLocation.slice(-3), ...systemGrouping].join(" / ") || "Ubicacion pendiente";
}

function isTechnicalIfcLabel(value: string) {
  return /^Ifc[A-Z]/.test(compact(value));
}

function scopeNameFor(line: QuantityTakeoffLine) {
  const category = isTechnicalIfcLabel(line.category) ? "" : line.category;
  return unique([category, line.family, line.type_name]).join(" / ") || compact(line.ifc_class) || "Elemento pendiente";
}

function isUnknownWbs(code: string) {
  const normalized = code.trim().toUpperCase();
  return !normalized || normalized.startsWith("UNKNOWN") || normalized === "WBS-PENDING";
}

function slug(value: string) {
  return value
    .toUpperCase()
    .replace(/[^A-Z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "")
    .slice(0, 28);
}

function candidateStatus(lines: QuantityTakeoffLine[]) {
  const blockers = new Set<string>();
  for (const line of lines) {
    if (pbsBasisFor(line) === "Ubicacion pendiente") blockers.add("Falta ubicacion");
    if (!line.quantity || line.quantity <= 0 || !compact(line.unit)) blockers.add("Falta cantidad/unidad");
    if (!compact(line.cbs_code) || isUnknownWbs(line.wbs_code)) blockers.add("Falta CBS/WBS");
    if (!compact(line.fbs_code)) blockers.add("Falta FBS");
    if (!compact(line.package_code)) blockers.add("Falta paquete");
    if (!compact(line.element_guid) && !compact(line.element_id)) blockers.add("Falta trazabilidad BIM");
  }
  if (!blockers.size) return { blockers: [], status: "Listo para asignar" };
  const ordered = [
    "Falta ubicacion",
    "Falta cantidad/unidad",
    "Falta CBS/WBS",
    "Falta FBS",
    "Falta paquete",
    "Falta trazabilidad BIM",
  ].filter((item) => blockers.has(item));
  return { blockers: ordered, status: ordered[0] };
}

function buildScopeCandidates(lines: QuantityTakeoffLine[]) {
  const groups = new Map<string, QuantityTakeoffLine[]>();
  lines.forEach((line) => {
    const key = [
      pbsBasisFor(line),
      scopeNameFor(line),
      compact(line.unit) || "UOM_PENDING",
      compact(line.measurement_rule) || "RULE_PENDING",
      compact(line.cbs_code) || "CBS_PENDING",
    ].join("|");
    groups.set(key, [...(groups.get(key) ?? []), line]);
  });

  return Array.from(groups.values()).map<ScopeCandidate>((candidateLines, index) => {
    const first = candidateLines[0];
    const quantity = candidateLines.reduce((total, line) => total + (Number.isFinite(line.quantity) ? line.quantity : 0), 0);
    const assignedQuantity = candidateLines.reduce(
      (total, line) => total + (compact(line.package_code) ? line.quantity || 0 : 0),
      0,
    );
    const cbsCodes = unique(candidateLines.map((line) => line.cbs_code));
    const fbsCodes = unique(candidateLines.map((line) => line.fbs_code));
    const wbsCodes = unique(candidateLines.map((line) => line.wbs_code).filter((code) => !isUnknownWbs(code)));
    const packageCodes = unique(candidateLines.map((line) => line.package_code));
    const measurementLabel = controlledMeasurementLabel(candidateLines);
    const { blockers, status } = candidateStatus(candidateLines);
    const codeSeed = cbsCodes[0] || first.classification_code || first.ifc_class || first.category || `ROW-${index + 1}`;
    const quantityRule = evaluateQuantityRule(first);
    const budgetAssignments = candidateLines
      .map(budgetAssignmentFor)
      .filter((assignment): assignment is BudgetItemAssignment => Boolean(assignment));
    const firstBudgetAssignment = budgetAssignments[0] ?? null;

    return {
      assignedQuantity,
      budgetItem: firstBudgetAssignment
        ? {
            ...firstBudgetAssignment,
            budgetAmount: budgetAssignments.reduce((total, item) => total + item.budgetAmount, 0),
            quantity: budgetAssignments.reduce((total, item) => total + item.quantity, 0),
          }
        : null,
      blockers,
      calculation: quantityCalculationSummary(candidateLines),
      cbsCodes,
      controlledMeasurementLabel: measurementLabel,
      elementRefs: unique(candidateLines.map((line) => line.element_guid || line.element_id || line.source_row_id)),
      fbsCodes,
      id: `SI-${slug(codeSeed) || "ITEM"}-${String(index + 1).padStart(2, "0")}`,
      ifcClasses: unique(candidateLines.map((line) => line.ifc_class)),
      lineIds: candidateLines.map((line) => line.id),
      measurementRules: unique(candidateLines.map((line) => line.measurement_rule)),
      name: scopeNameFor(first),
      packageCodes,
      pbsBasis: pbsBasisFor(first),
      pendingQuantity: Math.max(0, quantity - assignedQuantity),
      quantity,
      quantityRule,
      sourceCount: candidateLines.length,
      status,
      unit: compact(first.unit) || "UOM pending",
      wbsCodes,
    };
  });
}

function formatQuantity(value: number, unit: string) {
  return `${value.toLocaleString("en-US", { maximumFractionDigits: 2 })} ${unit}`;
}

function formatCurrency(value: number, currency = "USD") {
  return value.toLocaleString("en-US", { maximumFractionDigits: 2, minimumFractionDigits: Number.isInteger(value) ? 0 : 2, style: "currency", currency });
}

function catalogStatusLabel(value: string) {
  return compact(value)
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase()) || "Review";
}

function normalizeUnitDraft(value: string) {
  return unique(value.split(/[,/;]+/).map((item) => item.trim().toLowerCase()));
}

function controlledMeasurementFor(line: QuantityTakeoffLine) {
  const record = line.raw_data?.controlled_measurement;
  return record && typeof record === "object" && !Array.isArray(record) ? (record as Record<string, unknown>) : null;
}

function controlledMeasurementLabel(lines: QuantityTakeoffLine[]) {
  const approved = lines
    .map(controlledMeasurementFor)
    .filter((record): record is Record<string, unknown> => Boolean(record && record.status === "approved"));
  if (!approved.length) return "Pendiente";
  const version = Math.max(...approved.map((record) => Number(record.version) || 0));
  return approved.length === lines.length ? `Aprobada v${version}` : `Parcial ${approved.length}/${lines.length}`;
}

function rawRecord(value: unknown) {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : {};
}

function rawText(record: Record<string, unknown>, key: string) {
  const value = record[key];
  return typeof value === "string" ? compact(value) : "";
}

function rawNumber(record: Record<string, unknown>, key: string) {
  const value = record[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function quantityCalculationFor(line: QuantityTakeoffLine) {
  return rawRecord(line.raw_data?.quantity_calculation);
}

function budgetAssignmentFor(line: QuantityTakeoffLine): BudgetItemAssignment | null {
  const assignment = rawRecord(line.raw_data?.budget_item_assignment);
  const suggestion = rawRecord(line.raw_data?.apu_suggestion);
  const isSuggestion = !Object.keys(assignment).length && Boolean(Object.keys(suggestion).length);
  const record = isSuggestion ? suggestion : assignment;
  const code = rawText(record, "cost_item_code");
  const name = rawText(record, "cost_item_name");
  const quantity = rawNumber(record, "quantity") ?? line.quantity;
  const budgetUnit = rawText(record, "budget_unit") || line.unit;
  const unitRate = rawNumber(record, "unit_rate") ?? 0;
  const budgetAmount = rawNumber(record, "budget_amount") ?? quantity * unitRate;
  if (!code && !name && !unitRate && !budgetAmount) return null;
  return {
    apuStructure: apuStructureLinesFromRecord(record, line.unit, unitRate),
    budgetAmount,
    budgetUnit,
    catalogItemId: rawNumber(record, "catalog_item_id"),
    code,
    currency: rawText(record, "currency") || undefined,
    isSuggestion,
    licenseNote: rawText(record, "license_note"),
    matchScore: rawNumber(record, "match_score"),
    name,
    quantity,
    sourceKey: rawText(record, "source_key"),
    sourceUrl: rawText(record, "source_url"),
    status: rawText(record, "status"),
    structureNote: rawText(record, "structure_note"),
    structureStatus: rawText(record, "structure_status"),
    unitRate,
  };
}

function apuStructureLinesFromRecord(record: Record<string, unknown>, fallbackUnit: string, fallbackRate: number) {
  const rawStructure = Array.isArray(record.apu_structure) ? record.apu_structure : [];
  const lines = rawStructure
    .map((rawLine) => normalizeApuResourceLine(rawLine, fallbackUnit, fallbackRate))
    .filter((line): line is ApuResourceLine => Boolean(line));
  return lines.length
    ? lines
    : [
        {
          amount: fallbackRate,
          component: "Costo directo",
          component_type: "DIRECT_COST",
          description: "Costo directo de referencia; falta descomposicion APU por recursos.",
          quantity: 1,
          status: "review",
          unit: fallbackUnit || "und",
          unit_rate: fallbackRate,
        },
      ];
}

function normalizeApuResourceLine(rawLine: unknown, fallbackUnit: string, fallbackRate: number): ApuResourceLine | null {
  if (!rawLine || typeof rawLine !== "object") return null;
  const line = rawLine as Record<string, unknown>;
  return {
    amount: Number(line.amount ?? fallbackRate) || 0,
    code: typeof line.code === "string" ? line.code : undefined,
    component: String(line.component ?? "Costo directo"),
    component_type: typeof line.component_type === "string" ? line.component_type : undefined,
    description: String(line.description ?? "Componente APU pendiente de descripcion"),
    quantity: Number(line.quantity ?? 1) || 1,
    source: typeof line.source === "string" ? line.source : undefined,
    status: typeof line.status === "string" ? line.status : undefined,
    unit: String(line.unit ?? fallbackUnit ?? "und"),
    unit_rate: Number(line.unit_rate ?? fallbackRate) || 0,
  };
}

function apuCatalogStructureLines(item: ColombiaApuCatalogItem) {
  return apuStructureLinesFromRecord(item.raw_data ?? {}, item.unit, Number(item.unit_rate) || 0);
}

function apuCatalogStructureNote(item: ColombiaApuCatalogItem) {
  const note = item.raw_data?.structure_note;
  return typeof note === "string" && compact(note)
    ? note
    : "Estructura de referencia para revision. Validar composicion, rendimiento, AIU y vigencia antes de aprobar.";
}

function quantityCalculationSummary(lines: QuantityTakeoffLine[]): QuantityCalculationSummary {
  const first = lines[0];
  const calculation = quantityCalculationFor(first);
  const sourceQuantity = rawNumber(calculation, "source_quantity") ?? first.quantity;
  const sourceUnit = rawText(calculation, "source_unit") || first.unit;
  const recommendedQuantity = rawNumber(calculation, "recommended_quantity");
  const recommendedUnit = rawText(calculation, "recommended_unit");
  const fallbackRule = rawText(calculation, "fallback_rule");
  const fallbackUnit = rawText(calculation, "fallback_unit");
  return {
    confidence: rawText(calculation, "confidence"),
    fallbackLabel: fallbackRule ? `${fallbackRule}${fallbackUnit ? ` / ${fallbackUnit}` : ""}` : "",
    recommendedLabel: recommendedQuantity !== null ? formatQuantity(recommendedQuantity, recommendedUnit || sourceUnit) : "",
    source: rawText(calculation, "source"),
    sourceLabel: formatQuantity(sourceQuantity, sourceUnit),
    status: rawText(calculation, "status"),
  };
}

export default function BimScopeValidationPanel({
  lines,
  wbsCatalog = [],
  cbsCatalog = [],
  fbsFundingSources = [],
  workPackages = [],
  quantityRules = [],
  colombiaApuCatalog = [],
  colombiaApuSync = null,
  showApuCatalogBridge = true,
  approvalDisabled = false,
  assignmentDisabled = false,
  apuActionDisabled = false,
  geometryBatch = null,
  geometryBatchDisabled = false,
  geometryModelAvailable = false,
  geometryModels = [],
  geometryModelStatusMessage = "",
  geometryRun,
  onApproveControlledMeasurement,
  onAssignControlCodes,
  onApproveApuForLines,
  onAnalyzeGeometryBatch,
  onApplyGeometryBatch,
  onLinkGeometryModel,
  onOpenBimBudget,
  onSuggestApuForLines,
  onSyncColombiaApuCatalog,
  onUpdateQuantityRule,
  onRecalculateQuantityRules,
  recalculationSummary,
  recalculateDisabled = false,
}: BimScopeValidationPanelProps) {
  const candidates = buildScopeCandidates(lines);
  const quantityRuleSummary = summarizeQuantityRules(lines);
  const pbsLocatedLines = lines.filter((line) => pbsBasisFor(line) !== "Ubicacion pendiente").length;
  const tracedLines = lines.filter((line) => compact(line.element_guid) || compact(line.element_id)).length;
  const missingControlCodes = candidates.filter(
    (candidate) => candidate.blockers.includes("Falta CBS/WBS") || candidate.blockers.includes("Falta FBS"),
  ).length;
  const pendingAssignment = candidates.reduce((total, candidate) => total + candidate.pendingQuantity, 0);
  const budgetedCandidates = candidates.filter((candidate) => candidate.budgetItem);
  const bimBudgetAmount = budgetedCandidates.reduce((total, candidate) => total + (candidate.budgetItem?.budgetAmount ?? 0), 0);
  const bimBudgetCurrency = budgetedCandidates[0]?.budgetItem?.currency ?? "USD";
  const [editingRuleId, setEditingRuleId] = useState<number | null>(null);
  const [quantityDrafts, setQuantityDrafts] = useState<Record<string, QuantityApprovalDraft>>({});
  const [assignmentDrafts, setAssignmentDrafts] = useState<Record<string, ControlCodeAssignmentDraft>>({});
  const [ruleDraft, setRuleDraft] = useState<QuantityRuleDraft | null>(null);

  function quantityDraftFor(candidate: ScopeCandidate) {
    return quantityDrafts[candidate.id] ?? { quantity: String(candidate.quantity), unit: candidate.unit };
  }

  function updateQuantityDraft(candidateId: string, draft: Partial<QuantityApprovalDraft>) {
    setQuantityDrafts((current) => ({
      ...current,
      [candidateId]: {
        quantity: draft.quantity ?? current[candidateId]?.quantity ?? "",
        unit: draft.unit ?? current[candidateId]?.unit ?? "",
      },
    }));
  }

  function assignmentDraftFor(candidate: ScopeCandidate) {
    return (
      assignmentDrafts[candidate.id] ?? {
        cbs_code: candidate.cbsCodes[0] ?? "",
        fbs_code: candidate.fbsCodes[0] ?? "",
        package_code: candidate.packageCodes[0] ?? "",
        wbs_code: candidate.wbsCodes[0] ?? "",
        cost_item_code: candidate.budgetItem?.code ?? "",
        cost_item_name: candidate.budgetItem?.name ?? candidate.name,
        budget_unit: candidate.budgetItem?.budgetUnit ?? candidate.unit,
        unit_rate: candidate.budgetItem?.unitRate ? String(candidate.budgetItem.unitRate) : "",
      }
    );
  }

  function updateAssignmentDraft(candidateId: string, draft: Partial<ControlCodeAssignmentDraft>) {
    setAssignmentDrafts((current) => ({
      ...current,
      [candidateId]: {
        cbs_code: draft.cbs_code ?? current[candidateId]?.cbs_code ?? "",
        fbs_code: draft.fbs_code ?? current[candidateId]?.fbs_code ?? "",
        package_code: draft.package_code ?? current[candidateId]?.package_code ?? "",
        wbs_code: draft.wbs_code ?? current[candidateId]?.wbs_code ?? "",
        cost_item_code: draft.cost_item_code ?? current[candidateId]?.cost_item_code ?? "",
        cost_item_name: draft.cost_item_name ?? current[candidateId]?.cost_item_name ?? "",
        budget_unit: draft.budget_unit ?? current[candidateId]?.budget_unit ?? "",
        unit_rate: draft.unit_rate ?? current[candidateId]?.unit_rate ?? "",
      },
    }));
  }

  function startRuleEdit(rule: BimQuantityRule) {
    setEditingRuleId(rule.id);
    setRuleDraft({
      element_label: rule.element_label,
      expected_measure: rule.expected_measure,
      rule_hint: rule.rule_hint,
      expected_units: rule.expected_units.join(", "),
      status: rule.status,
    });
  }

  function saveRuleEdit(rule: BimQuantityRule) {
    if (!ruleDraft || !onUpdateQuantityRule) return;
    onUpdateQuantityRule(rule.id, {
      element_label: ruleDraft.element_label.trim(),
      expected_measure: ruleDraft.expected_measure.trim(),
      rule_hint: ruleDraft.rule_hint.trim(),
      expected_units: normalizeUnitDraft(ruleDraft.expected_units),
      allow_fallback_count: rule.allow_fallback_count,
      status: ruleDraft.status,
      expected_version: rule.version,
    });
    setEditingRuleId(null);
    setRuleDraft(null);
  }

  function approveCandidate(candidate: ScopeCandidate) {
    if (!onApproveControlledMeasurement) return;
    const draft = quantityDraftFor(candidate);
    const controlledQuantity = Number(draft.quantity);
    const quantity = Number.isFinite(controlledQuantity) && controlledQuantity > 0 ? controlledQuantity : candidate.quantity;
    const unit = compact(draft.unit) || candidate.unit;
    onApproveControlledMeasurement({
      line_ids: candidate.lineIds,
      measurement_rule: candidate.measurementRules[0] || candidate.quantityRule.expectedMeasure,
      note: `Aprobacion controlada de ${candidate.id} - ${candidate.name}`,
      quantity,
      source: candidate.quantityRule.source,
      unit,
    });
  }

  function assignCandidate(candidate: ScopeCandidate) {
    if (!onAssignControlCodes) return;
    const draft = assignmentDraftFor(candidate);
    const unitRate = Number(draft.unit_rate);
    onAssignControlCodes({
      line_ids: candidate.lineIds,
      cbs_code: draft.cbs_code,
      fbs_code: draft.fbs_code,
      package_code: draft.package_code,
      wbs_code: draft.wbs_code,
      cost_item_code: draft.cost_item_code.trim(),
      cost_item_name: draft.cost_item_name.trim(),
      budget_unit: draft.budget_unit.trim() || candidate.unit,
      unit_rate: Number.isFinite(unitRate) && unitRate >= 0 ? unitRate : undefined,
      ...(candidate.budgetItem
        ? {
            apu_structure: candidate.budgetItem.apuStructure,
            catalog_item_id: candidate.budgetItem.catalogItemId ?? undefined,
            currency: candidate.budgetItem.currency,
            license_note: candidate.budgetItem.licenseNote,
            source_key: candidate.budgetItem.sourceKey,
            source_url: candidate.budgetItem.sourceUrl,
            structure_note: candidate.budgetItem.structureNote,
            structure_status: candidate.budgetItem.structureStatus,
          }
        : {}),
      note: `Asignacion de codigos de control ${candidate.id}`,
    });
  }

  function canAssignCandidate(candidate: ScopeCandidate) {
    const draft = assignmentDraftFor(candidate);
    return Boolean(draft.wbs_code && draft.cbs_code && draft.fbs_code && draft.package_code);
  }

  function suggestCandidateApu(candidate: ScopeCandidate) {
    if (!onSuggestApuForLines) return;
    onSuggestApuForLines(candidate.lineIds);
  }

  function suggestAllApu() {
    if (!onSuggestApuForLines) return;
    onSuggestApuForLines(candidates.flatMap((candidate) => candidate.lineIds));
  }

  return (
    <section aria-label="Tabla de cantidades controladas" className="bimScopeValidationPanel">
      <div className="panelHeader compactHeader">
        <div className="bimValidationTitle">
          <h3>
            <ClipboardCheck size={18} /> Tabla de cantidades controladas
          </h3>
          <span>Ubicacion -&gt; Elemento -&gt; Codigos de control</span>
        </div>
        <strong>{candidates.length} grupo(s)</strong>
      </div>

      <div className="bimValidationSummary">
        <article>
          <span>Ubicacion del modelo</span>
          <strong>{lines.length ? `${pbsLocatedLines}/${lines.length}` : "0/0"}</strong>
          <small>Nivel, zona, sistema o conjunto deben ubicar cada cantidad.</small>
        </article>
        <article>
          <span>Trazabilidad BIM</span>
          <strong>{lines.length ? `${tracedLines}/${lines.length}` : "0/0"}</strong>
          <small>Las referencias del modelo quedan como evidencia de origen.</small>
        </article>
        <article>
          <span>WBS/CBS/FBS</span>
          <strong>{missingControlCodes ? `${missingControlCodes} por revisar` : "Listo"}</strong>
          <small>Cada grupo debe tener WBS, codigo de costo y fuente de fondos antes del rollup.</small>
        </article>
        <article>
          <span>Saldo por asignar</span>
          <strong>{formatQuantity(pendingAssignment, candidates[0]?.unit ?? "")}</strong>
          <small>Cantidad total menos cantidad asignada a paquete.</small>
        </article>
        <article>
          <span>Presupuesto BIM</span>
          <strong>{formatCurrency(bimBudgetAmount, bimBudgetCurrency)}</strong>
          <small>{budgetedCandidates.length} grupo(s) con partida/APU y precio unitario.</small>
        </article>
      </div>

      <div className="bimValidationPrinciples" aria-label="BIM item rules">
        <span>
          <Network size={14} /> No duplicar elementos por WBS
        </span>
        <span>
          <GitBranch size={14} /> Usar asignaciones para paquetes
        </span>
        <span>CBS antes del rollup de costos</span>
      </div>

      {onAnalyzeGeometryBatch && onApplyGeometryBatch ? (
        <BimGeometryBatchPanel
          actionDisabled={geometryBatchDisabled}
          modelAvailable={geometryModelAvailable}
          models={geometryModels}
          modelStatusMessage={geometryModelStatusMessage}
          onAnalyze={onAnalyzeGeometryBatch}
          onApply={onApplyGeometryBatch}
          onLinkModel={onLinkGeometryModel}
          preview={geometryBatch}
          run={geometryRun}
        />
      ) : null}

      {onApproveApuForLines && onOpenBimBudget && onSuggestApuForLines ? (
        <BimApuReviewPanel
          actionDisabled={apuActionDisabled}
          lines={lines}
          onApproveLines={onApproveApuForLines}
          onOpenBudget={onOpenBimBudget}
          onSuggestLines={onSuggestApuForLines}
        />
      ) : null}

      {showApuCatalogBridge && (onSyncColombiaApuCatalog || onSuggestApuForLines || colombiaApuCatalog.length) ? (
        <section aria-label="Base APU Colombia" className="colombiaApuBridge">
          <div className="panelHeader compactHeader registerHeader">
            <div>
              <h3>Base de datos APU Colombia</h3>
              <span>Partidas e insumos gratuitos sincronizables para sugerir presupuesto desde cantidades BIM.</span>
            </div>
            <div className="apuBridgeActions">
              {onSyncColombiaApuCatalog ? (
                <button className="secondaryAction" disabled={apuActionDisabled} onClick={onSyncColombiaApuCatalog} type="button">
                  Actualizar base gratis
                </button>
              ) : null}
              {onSuggestApuForLines ? (
                <button
                  className="primaryAction"
                  disabled={apuActionDisabled || !candidates.length}
                  onClick={suggestAllApu}
                  type="button"
                >
                  Sugerir APU
                </button>
              ) : null}
            </div>
          </div>
          <div className="apuBridgeSummary">
            <article>
              <span>Registros visibles</span>
              <strong>{colombiaApuCatalog.length}</strong>
              <small>{colombiaApuCatalog.length ? "partida(s) disponibles en el proyecto" : "sin sincronizar"}</small>
            </article>
            <article>
              <span>Ultima sincronizacion</span>
              <strong>{colombiaApuSync ? `${colombiaApuSync.created_count} nuevas / ${colombiaApuSync.updated_count} actualizadas` : "Pendiente"}</strong>
              <small>{colombiaApuSync?.source_key ?? "DataCauca/public source"}</small>
            </article>
            <article>
              <span>Uso permitido</span>
              <strong>Revision</strong>
              <small>{colombiaApuSync?.license_note ?? colombiaApuCatalog[0]?.license_note ?? "Validar vigencia, region, AIU y alcance."}</small>
            </article>
          </div>
          {colombiaApuCatalog.length ? (
            <div className="mappingTable apuCatalogTable">
              <table>
                <thead>
                  <tr>
                    <th>Codigo</th>
                    <th>Partida / insumo</th>
                    <th>Estructura APU</th>
                    <th>Unidad</th>
                    <th>Precio unitario</th>
                    <th>Region / fuente</th>
                    <th>Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {colombiaApuCatalog.slice(0, 12).map((item) => {
                    const structureLines = apuCatalogStructureLines(item);
                    return (
                      <tr key={item.id}>
                        <td data-label="Codigo">
                          <strong>{item.item_code}</strong>
                          <span>{item.chapter || item.group_name || "Capitulo pendiente"}</span>
                        </td>
                        <td data-label="Partida / insumo">
                          <strong>{item.item_name}</strong>
                          <span>{item.group_name || "Grupo pendiente"}</span>
                        </td>
                        <td data-label="Estructura APU">
                          <div className="apuStructureStack compactApuStructure">
                            {structureLines.map((line, index) => (
                              <span key={`${item.id}-${line.component}-${index}`}>
                                <strong>{line.component}</strong>
                                <small>{line.description}</small>
                                <em>
                                  {line.quantity} {line.unit} x {formatCurrency(line.unit_rate, item.currency)}
                                  {line.amount ? ` = ${formatCurrency(line.amount, item.currency)}` : ""}
                                </em>
                              </span>
                            ))}
                            <small>{apuCatalogStructureNote(item)}</small>
                          </div>
                        </td>
                        <td data-label="Unidad">{item.unit}</td>
                        <td data-label="Precio unitario">
                          <strong>{formatCurrency(item.unit_rate, item.currency)}</strong>
                          <span>{item.currency}</span>
                        </td>
                        <td data-label="Region / fuente">
                          <strong>{item.region || "Region pendiente"}</strong>
                          <span>{item.source_key}</span>
                        </td>
                        <td data-label="Estado">
                          <strong>{catalogStatusLabel(item.status)}</strong>
                          <span>Validar antes de aprobar</span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="workspaceEmpty compactEmpty">
              <strong>Base APU sin registros visibles</strong>
              <span>Usa Actualizar base gratis para traer partidas publicas al proyecto.</span>
            </div>
          )}
        </section>
      ) : null}

      {quantityRules.length ? (
        <section aria-label="Catalogo de reglas de cantidad" className="quantityRuleCatalog">
          <div className="panelHeader compactHeader registerHeader">
            <h3>Catalogo de reglas de cantidad</h3>
            <span>Editable por proyecto antes de importar o recalcular cantidades</span>
          </div>
          <div className="quantityRuleCatalogRows">
            {quantityRules.slice(0, 10).map((rule) => {
              const isEditing = editingRuleId === rule.id && ruleDraft;
              return (
                <article key={rule.id} className={rule.status === "inactive" ? "inactive" : ""}>
                  <div className="quantityRuleCatalogIdentity">
                    <strong>{rule.element_label || rule.ifc_class}</strong>
                    <span>{rule.ifc_class}</span>
                  </div>
                  {isEditing ? (
                    <div className="quantityRuleEditForm">
                      <label>
                        <span>Elemento</span>
                        <input
                          aria-label="Elemento"
                          value={ruleDraft.element_label}
                          onChange={(event) => setRuleDraft({ ...ruleDraft, element_label: event.target.value })}
                        />
                      </label>
                      <label>
                        <span>Medida esperada</span>
                        <input
                          aria-label="Medida esperada"
                          value={ruleDraft.expected_measure}
                          onChange={(event) => setRuleDraft({ ...ruleDraft, expected_measure: event.target.value })}
                        />
                      </label>
                      <label>
                        <span>Regla fuente</span>
                        <input
                          aria-label="Regla fuente"
                          value={ruleDraft.rule_hint}
                          onChange={(event) => setRuleDraft({ ...ruleDraft, rule_hint: event.target.value })}
                        />
                      </label>
                      <label>
                        <span>Unidades esperadas</span>
                        <input
                          aria-label="Unidades esperadas"
                          value={ruleDraft.expected_units}
                          onChange={(event) => setRuleDraft({ ...ruleDraft, expected_units: event.target.value })}
                        />
                      </label>
                      <div className="quantityRuleEditActions">
                        <button className="primaryAction" type="button" onClick={() => saveRuleEdit(rule)}>
                          Guardar regla BIM
                        </button>
                        <button
                          className="secondaryAction"
                          type="button"
                          onClick={() => {
                            setEditingRuleId(null);
                            setRuleDraft(null);
                          }}
                        >
                          Cancelar
                        </button>
                      </div>
                    </div>
                  ) : (
                    <>
                      <div className="quantityRuleCatalogMeasure">
                        <span>{rule.expected_measure}</span>
                        <strong>{rule.expected_units.join(" / ")}</strong>
                        <small>{rule.rule_hint}</small>
                      </div>
                      <div className="quantityRuleCatalogActions">
                        <span>{rule.source === "project_custom" ? "Proyecto" : "Estandar"}</span>
                        {onUpdateQuantityRule && (
                          <button
                            className="secondaryAction"
                            type="button"
                            aria-label={`Editar regla ${rule.ifc_class}`}
                            onClick={() => startRuleEdit(rule)}
                          >
                            Editar
                          </button>
                        )}
                      </div>
                    </>
                  )}
                </article>
              );
            })}
          </div>
        </section>
      ) : null}

      <section aria-label="Calculador de cantidades BIM" className="quantityRulePanel">
        <div className="panelHeader compactHeader registerHeader">
          <div>
            <h3>
              <Calculator size={18} /> Calculador de cantidades BIM
            </h3>
            <span>Clase IFC -&gt; regla esperada -&gt; unidad -&gt; fuente -&gt; confianza</span>
          </div>
          {onRecalculateQuantityRules ? (
            <button
              className="primaryAction"
              disabled={recalculateDisabled || !lines.length}
              onClick={() => onRecalculateQuantityRules()}
              type="button"
            >
              Recalcular reglas
            </button>
          ) : null}
        </div>
        <div className="quantityRuleSummary">
          <article>
            <span>Validas</span>
            <strong>{quantityRuleSummary.valid}</strong>
            <small>Regla y unidad consistentes.</small>
          </article>
          <article>
            <span>Por revisar</span>
            <strong>{quantityRuleSummary.review}</strong>
            <small>Reglas personalizadas o fuentes que requieren validacion.</small>
          </article>
          <article>
            <span>Bloqueadas</span>
            <strong>{quantityRuleSummary.blocked}</strong>
            <small>Falta area, volumen, longitud o una unidad coherente.</small>
          </article>
          <article>
            <span>Fuente confiable</span>
            <strong>
              {quantityRuleSummary.authoritative}/{quantityRuleSummary.total}
            </strong>
            <small>Lineas con Quantity Set publicado.</small>
          </article>
        </div>
        {recalculationSummary ? (
          <div className="quantityRuleRecalcSummary" aria-label="Resultado de recálculo de reglas BIM">
            <article>
              <span>Impacto</span>
              <strong>{recalculationSummary.changed_line_count} linea(s) cambiadas</strong>
              <small>{recalculationSummary.total_lines} linea(s) evaluadas</small>
            </article>
            <article>
              <span>Gate de costos</span>
              <strong>Gate de costos: {recalculationSummary.cost_rollup_gate}</strong>
              <small>
                {recalculationSummary.valid_count} validas / {recalculationSummary.review_count} revision /{" "}
                {recalculationSummary.blocked_count} bloqueadas
              </small>
            </article>
            {recalculationSummary.impacts.length ? (
              <div className="quantityRuleRecalcImpacts">
                {recalculationSummary.impacts.slice(0, 4).map((impact) => (
                  <div key={`${impact.line_id}-${impact.ifc_class}`}>
                    <strong>
                      {impact.previous_status} {"->"} {impact.new_status}
                    </strong>
                    <span>
                      {impact.ifc_class} / {impact.previous_measure || "medida anterior"} {"->"}{" "}
                      {impact.new_measure || "medida actual"} / {impact.mapping_status}
                    </span>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        ) : null}
        {candidates.length ? (
          <div className="quantityRuleFindings">
            {candidates.slice(0, 4).map((candidate) => (
              <article className={candidate.quantityRule.status} key={candidate.id}>
                <span>{candidate.id}</span>
                <strong>{candidate.quantityRule.status === "review" ? "Requiere validacion" : candidate.quantityRule.source}</strong>
                <small>{candidate.quantityRule.explanation}</small>
                {candidate.quantityRule.findings.length ? (
                  <em>Corrige o aprueba la medicion geometrica antes de usarla para costo o paquete.</em>
                ) : (
                  <em>Regla consistente para {candidate.quantityRule.expectedUnits.join(" / ") || candidate.unit}.</em>
                )}
              </article>
            ))}
          </div>
        ) : (
          <p className="projectHint">Carga cantidades para activar la validacion por clase IFC.</p>
        )}
      </section>

      <div className="panelHeader compactHeader registerHeader">
        <h3>Elementos constructivos y cantidades</h3>
        <span>Una tabla para validar cantidad, elemento, trazabilidad y codigos de control</span>
      </div>
      {candidates.length ? (
        <div className="mappingTable quantityCandidateTable">
          <table>
            <thead>
              <tr>
                <th>Item ID</th>
                <th>Ubicacion</th>
                <th>Elemento constructivo</th>
                <th>Cantidad</th>
                <th>Partida / APU</th>
                <th>Regla de cantidad</th>
                <th>WBS / CBS / FBS / Package</th>
                <th>Trazabilidad BIM</th>
                <th>Estado</th>
              </tr>
            </thead>
            <tbody>
              {candidates.slice(0, 12).map((candidate) => {
                const assignmentDraft = assignmentDraftFor(candidate);
                const showAssignmentControls = Boolean(
                  onAssignControlCodes &&
                    wbsCatalog.length &&
                    cbsCatalog.length &&
                    fbsFundingSources.length &&
                    workPackages.length,
                );
                return (
                <tr key={candidate.id}>
                  <td data-label="Item ID">
                    <strong>{candidate.id}</strong>
                    <span>{candidate.sourceCount} linea(s) fuente</span>
                  </td>
                  <td data-label="Ubicacion">{candidate.pbsBasis}</td>
                  <td data-label="Elemento constructivo">
                    <strong>{candidate.name}</strong>
                    <span>
                      {[candidate.ifcClasses.join(" / ") || "Clase IFC pendiente", candidate.measurementRules.join(" / ") || "Regla de medicion pendiente"]
                        .filter(Boolean)
                        .join(" / ")}
                    </span>
                  </td>
                  <td data-label="Cantidad">
                    <strong>{formatQuantity(candidate.quantity, candidate.unit)}</strong>
                    <span>
                      Asignado {formatQuantity(candidate.assignedQuantity, candidate.unit)} / Pendiente{" "}
                      {formatQuantity(candidate.pendingQuantity, candidate.unit)}
                    </span>
                    {onApproveControlledMeasurement ? (
                      <div className="quantityApprovalInputs">
                        <input
                          aria-label={`Cantidad controlada ${candidate.id}`}
                          disabled={approvalDisabled}
                          min="0"
                          onChange={(event) => updateQuantityDraft(candidate.id, { quantity: event.target.value })}
                          step="0.01"
                          type="number"
                          value={quantityDraftFor(candidate).quantity}
                        />
                        <input
                          aria-label={`Unidad controlada ${candidate.id}`}
                          disabled={approvalDisabled}
                          onChange={(event) => updateQuantityDraft(candidate.id, { unit: event.target.value })}
                          type="text"
                          value={quantityDraftFor(candidate).unit}
                        />
                      </div>
                    ) : null}
                  </td>
                  <td data-label="Partida / APU">
                    {candidate.budgetItem ? (
                      <>
                        <strong>
                          {[candidate.budgetItem.code, candidate.budgetItem.name].filter(Boolean).join(" / ")}
                        </strong>
                        <span>
                          {formatQuantity(candidate.budgetItem.quantity, candidate.budgetItem.budgetUnit)} x{" "}
                          {formatCurrency(candidate.budgetItem.unitRate, candidate.budgetItem.currency)} ={" "}
                          {formatCurrency(candidate.budgetItem.budgetAmount, candidate.budgetItem.currency)}
                        </span>
                        {candidate.budgetItem.isSuggestion ? (
                          <span className="apuSuggestionBadge">
                            Sugerido / {candidate.budgetItem.matchScore ?? 0}% / validar APU, AIU y region
                          </span>
                        ) : null}
                        {candidate.budgetItem.sourceKey ? (
                          <span>{candidate.budgetItem.sourceKey}</span>
                        ) : null}
                        <div className="apuStructureStack compactApuStructure">
                          {candidate.budgetItem.apuStructure.slice(0, 4).map((line, index) => (
                            <span key={`${candidate.id}-${line.component}-${index}`}>
                              <strong>{line.component}</strong>
                              <small>{line.description}</small>
                              <em>
                                {line.quantity} {line.unit} x {formatCurrency(line.unit_rate, candidate.budgetItem?.currency)}
                                {line.amount ? ` = ${formatCurrency(line.amount, candidate.budgetItem?.currency)}` : ""}
                              </em>
                            </span>
                          ))}
                          <small>
                            {candidate.budgetItem.structureNote ||
                              "Estructura APU visible para revision; validar recursos, rendimiento, AIU y vigencia."}
                          </small>
                        </div>
                      </>
                    ) : (
                      <>
                        <strong>Partida pendiente</strong>
                        <span>Asigna partida/APU y precio unitario para llevar esta cantidad a presupuesto.</span>
                        {onSuggestApuForLines ? (
                          <button
                            className="secondaryAction apuSuggestRowAction"
                            disabled={apuActionDisabled}
                            onClick={() => suggestCandidateApu(candidate)}
                            type="button"
                          >
                            Sugerir APU Colombia
                          </button>
                        ) : null}
                      </>
                    )}
                    {showAssignmentControls ? (
                      <div className="quantityBudgetGrid">
                        <label>
                          <span>Codigo partida</span>
                          <input
                            aria-label={`Codigo de partida para ${candidate.id}`}
                            disabled={assignmentDisabled}
                            onChange={(event) => updateAssignmentDraft(candidate.id, { cost_item_code: event.target.value })}
                            type="text"
                            value={assignmentDraft.cost_item_code}
                          />
                        </label>
                        <label>
                          <span>Partida APU</span>
                          <input
                            aria-label={`Partida APU para ${candidate.id}`}
                            disabled={assignmentDisabled}
                            onChange={(event) => updateAssignmentDraft(candidate.id, { cost_item_name: event.target.value })}
                            type="text"
                            value={assignmentDraft.cost_item_name}
                          />
                        </label>
                        <label>
                          <span>Unidad</span>
                          <input
                            aria-label={`Unidad de presupuesto para ${candidate.id}`}
                            disabled={assignmentDisabled}
                            onChange={(event) => updateAssignmentDraft(candidate.id, { budget_unit: event.target.value })}
                            type="text"
                            value={assignmentDraft.budget_unit}
                          />
                        </label>
                        <label>
                          <span>Precio unitario</span>
                          <input
                            aria-label={`Precio unitario para ${candidate.id}`}
                            disabled={assignmentDisabled}
                            min="0"
                            onChange={(event) => updateAssignmentDraft(candidate.id, { unit_rate: event.target.value })}
                            step="0.01"
                            type="number"
                            value={assignmentDraft.unit_rate}
                          />
                        </label>
                      </div>
                    ) : null}
                  </td>
                  <td data-label="Regla de cantidad">
                    <strong>{candidate.quantityRule.source}</strong>
                    <span>
                      {candidate.quantityRule.confidence} / {candidate.quantityRule.expectedUnits.join(" / ") || "unidad esperada pendiente"}
                    </span>
                    <span>Fuente: {candidate.calculation.sourceLabel}</span>
                    {candidate.calculation.confidence ? <span>Confianza {candidate.calculation.confidence}</span> : null}
                    {candidate.calculation.recommendedLabel ? <span>Recomendada: {candidate.calculation.recommendedLabel}</span> : null}
                    {candidate.calculation.fallbackLabel ? <span>Fallback sugerido: {candidate.calculation.fallbackLabel}</span> : null}
                    <span>{candidate.quantityRule.findings[0] || candidate.quantityRule.expectedMeasure}</span>
                  </td>
                  <td data-label="WBS / CBS / FBS / Package">
                    <strong>{candidate.cbsCodes.join(" / ") || "CBS pendiente"}</strong>
                    <span>
                      {[
                        candidate.wbsCodes.join(" / ") || "WBS pendiente",
                        candidate.fbsCodes.join(" / ") || "FBS pendiente",
                        candidate.packageCodes.join(" / ") || "Paquete pendiente",
                      ]
                        .filter(Boolean)
                        .join(" / ")}
                    </span>
                    {showAssignmentControls ? (
                      <div className="quantityAssignmentGrid">
                        <label>
                          <span>WBS</span>
                          <select
                            aria-label={`WBS para ${candidate.id}`}
                            disabled={assignmentDisabled}
                            onChange={(event) => updateAssignmentDraft(candidate.id, { wbs_code: event.target.value })}
                            value={assignmentDraft.wbs_code}
                          >
                            <option value="">Selecciona WBS</option>
                            {wbsCatalog.map((node) => (
                              <option key={node.id} value={node.code}>
                                {node.code} - {node.name}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label>
                          <span>CBS</span>
                          <select
                            aria-label={`CBS para ${candidate.id}`}
                            disabled={assignmentDisabled}
                            onChange={(event) => updateAssignmentDraft(candidate.id, { cbs_code: event.target.value })}
                            value={assignmentDraft.cbs_code}
                          >
                            <option value="">Selecciona CBS</option>
                            {cbsCatalog.map((cbs) => (
                              <option key={cbs.id} value={cbs.code}>
                                {cbs.code} - {cbs.cost_category}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label>
                          <span>FBS</span>
                          <select
                            aria-label={`FBS para ${candidate.id}`}
                            disabled={assignmentDisabled}
                            onChange={(event) => updateAssignmentDraft(candidate.id, { fbs_code: event.target.value })}
                            value={assignmentDraft.fbs_code}
                          >
                            <option value="">Selecciona FBS</option>
                            {fbsFundingSources.map((source) => (
                              <option key={source.id} value={source.code}>
                                {source.code} - {source.name}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label>
                          <span>Paquete</span>
                          <select
                            aria-label={`Paquete para ${candidate.id}`}
                            disabled={assignmentDisabled}
                            onChange={(event) => updateAssignmentDraft(candidate.id, { package_code: event.target.value })}
                            value={assignmentDraft.package_code}
                          >
                            <option value="">Selecciona paquete</option>
                            {workPackages.map((workPackage) => (
                              <option key={workPackage.id} value={workPackage.code}>
                                {workPackage.code} - {workPackage.title}
                              </option>
                            ))}
                          </select>
                        </label>
                        <button
                          className="secondaryAction quantityAssignmentAction"
                          disabled={assignmentDisabled || !canAssignCandidate(candidate)}
                          onClick={() => assignCandidate(candidate)}
                          type="button"
                        >
                          Guardar codigos
                        </button>
                      </div>
                    ) : null}
                  </td>
                  <td data-label="Trazabilidad BIM">
                    <strong>{candidate.elementRefs.slice(0, 2).join(" / ") || "Trazabilidad pendiente"}</strong>
                    <span>{candidate.elementRefs.length} referencia(s) BIM</span>
                  </td>
                  <td data-label="Estado">
                    <strong>{candidate.status}</strong>
                    <span>{candidate.blockers.join(" / ") || "Validacion completa"}</span>
                    <span>Medicion: {candidate.controlledMeasurementLabel}</span>
                    {onApproveControlledMeasurement ? (
                      <button
                        className="secondaryAction quantityApprovalAction"
                        disabled={approvalDisabled}
                        onClick={() => approveCandidate(candidate)}
                        type="button"
                      >
                        {candidate.controlledMeasurementLabel === "Pendiente" ? "Aprobar medicion" : "Reaprobar medicion"}
                      </button>
                    ) : null}
                  </td>
                </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="workspaceEmpty compactEmpty">
          <strong>No hay elementos candidatos</strong>
          <span>Carga cantidades IFC o la plantilla Excel controlada para ejecutar las reglas.</span>
        </div>
      )}
    </section>
  );
}
