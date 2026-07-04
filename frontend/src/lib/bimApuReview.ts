import type { QuantityTakeoffLine } from "../types";
import { evaluateQuantityRule } from "./bimQuantityRules";

export type BimApuReviewStatus = "assigned" | "ready" | "review" | "blocked" | "pending";

export type BimApuReviewGroup = {
  budgetQuantity: number;
  budgetUnit: string;
  blockReason: string;
  confidence: number;
  costItemCode: string;
  costItemName: string;
  currency: string;
  elementName: string;
  groupKey: string;
  ifcClasses: string[];
  ifcQuantity: number;
  lineIds: number[];
  hasBudgetComparison: boolean;
  measurementValid: boolean;
  quantityVariance: number;
  sourceKey: string;
  status: BimApuReviewStatus;
  unit: string;
  unitCompatible: boolean;
  unitRate: number;
  expectedMeasure: string;
  expectedUnits: string[];
};

export type BimApuReview = {
  assignedGroupCount: number;
  blockedGroupCount: number;
  groups: BimApuReviewGroup[];
  pendingLineCount: number;
  pendingLineIds: number[];
  readyGroupCount: number;
  readyLineIds: number[];
  reviewGroupCount: number;
};

function compact(value: string | null | undefined) {
  return value?.trim() ?? "";
}

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

function unique(values: string[]) {
  return Array.from(new Set(values.map(compact).filter(Boolean)));
}

export function normalizedBudgetUnit(unit: string) {
  const normalized = compact(unit).toLowerCase().replace(/\s+/g, "");
  const aliases: Record<string, string> = {
    u: "ea",
    un: "ea",
    und: "ea",
    unidad: "ea",
    unidades: "ea",
    "m²": "m2",
    "m³": "m3",
  };
  return aliases[normalized] ?? normalized;
}

function pbsBasis(line: QuantityTakeoffLine) {
  return unique([line.project_name, line.site_name, line.building_name, line.storey, line.zone_name, line.system_name]).join(
    " / ",
  );
}

function elementName(line: QuantityTakeoffLine) {
  const category = /^Ifc[A-Z]/.test(compact(line.category)) ? "" : line.category;
  return unique([category, line.family, line.type_name]).join(" / ") || line.ifc_class || "Elemento pendiente";
}

function groupingKey(line: QuantityTakeoffLine) {
  return [
    pbsBasis(line),
    elementName(line),
    normalizedBudgetUnit(controlledUnit(line)),
    compact(line.measurement_rule),
    compact(line.cbs_code),
  ].join("|");
}

function sourceFor(line: QuantityTakeoffLine) {
  const assignment = record(line.raw_data?.budget_item_assignment);
  if (Object.keys(assignment).length) return { kind: "assignment" as const, record: assignment };
  const suggestion = record(line.raw_data?.apu_suggestion);
  if (Object.keys(suggestion).length) return { kind: "suggestion" as const, record: suggestion };
  return null;
}

function controlledQuantity(line: QuantityTakeoffLine) {
  const measurement = record(line.raw_data?.controlled_measurement);
  return number(measurement, "quantity") ?? Number(line.quantity || 0);
}

function controlledUnit(line: QuantityTakeoffLine) {
  const measurement = record(line.raw_data?.controlled_measurement);
  return text(measurement, "unit") || line.unit;
}

export function buildBimApuReview(lines: QuantityTakeoffLine[]): BimApuReview {
  const grouped = new Map<string, QuantityTakeoffLine[]>();
  for (const line of lines) {
    const key = groupingKey(line);
    grouped.set(key, [...(grouped.get(key) ?? []), line]);
  }

  const pendingLineIds: number[] = [];
  const groups = Array.from(grouped.entries()).map<BimApuReviewGroup>(([groupKey, groupLines]) => {
    const sources = groupLines.map(sourceFor);
    const quantityRules = groupLines.map(evaluateQuantityRule);
    const records = sources.filter((source): source is NonNullable<typeof source> => Boolean(source));
    groupLines.forEach((line, index) => {
      if (!sources[index] && quantityRules[index].status === "valid") pendingLineIds.push(line.id);
    });
    const firstRecord = records[0]?.record ?? {};
    const costItemCodes = unique(records.map((source) => text(source.record, "cost_item_code")));
    const costItemNames = unique(records.map((source) => text(source.record, "cost_item_name")));
    const budgetUnits = unique(records.map((source) => text(source.record, "budget_unit")));
    const sourcesKeys = unique(records.map((source) => text(source.record, "source_key")));
    const currencies = unique(records.map((source) => text(source.record, "currency")));
    const unitRates = records.map((source) => number(source.record, "unit_rate") ?? 0);
    const confidences = records
      .map((source) => number(source.record, "match_score"))
      .filter((value): value is number => value !== null);
    const ifcQuantity = groupLines.reduce((total, line) => total + controlledQuantity(line), 0);
    const budgetQuantity = groupLines.reduce((total, line, index) => {
      const source = sources[index];
      return total + (source ? number(source.record, "quantity") ?? controlledQuantity(line) : 0);
    }, 0);
    const unit = compact(controlledUnit(groupLines[0])) || "und";
    const budgetUnit = budgetUnits[0] || unit;
    const measurementValid = quantityRules.every((rule) => rule.status === "valid");
    const blockingRule = quantityRules.find((rule) => rule.status !== "valid");
    const expectedMeasure = blockingRule?.preferredMeasure || quantityRules[0]?.preferredMeasure || "";
    const expectedUnits = unique(quantityRules.flatMap((rule) => rule.expectedUnits));
    const unitCompatible =
      records.length > 0 &&
      groupLines.every((line, index) => {
        const source = sources[index];
        return source
          ? normalizedBudgetUnit(controlledUnit(line)) === normalizedBudgetUnit(text(source.record, "budget_unit") || controlledUnit(line))
          : true;
      });
    const allAssigned = records.length === groupLines.length && records.every((source) => source.kind === "assignment");
    const allSuggested = records.length === groupLines.length && records.every((source) => source.kind === "suggestion");
    const consistentItem = costItemCodes.length === 1 && budgetUnits.length === 1 && unitRates.every((rate) => rate > 0);
    const confidence = confidences.length ? Math.min(...confidences) : allAssigned && consistentItem ? 100 : 0;
    const hasBudgetComparison = records.length === groupLines.length && consistentItem;
    let status: BimApuReviewStatus = "pending";
    if (!measurementValid) status = "blocked";
    else if (!unitCompatible && records.length) status = "blocked";
    else if (allAssigned && consistentItem) status = "assigned";
    else if (allSuggested && consistentItem && confidence >= 70) status = "ready";
    else if (records.length) status = "review";
    const blockReason = !measurementValid
      ? `Medicion IFC pendiente: se espera ${expectedMeasure} (${expectedUnits.join(" / ")}).`
      : !unitCompatible && records.length
        ? `Unidad IFC ${unit} incompatible con APU ${budgetUnit}.`
        : "";

    return {
      budgetQuantity,
      budgetUnit,
      blockReason,
      confidence,
      costItemCode: costItemCodes[0] ?? "",
      costItemName: costItemNames[0] ?? "",
      currency: currencies[0] || "COP",
      elementName: elementName(groupLines[0]),
      groupKey,
      ifcClasses: unique(groupLines.map((line) => line.ifc_class)),
      ifcQuantity,
      hasBudgetComparison,
      lineIds: groupLines.map((line) => line.id),
      measurementValid,
      quantityVariance: hasBudgetComparison ? Math.round((budgetQuantity - ifcQuantity) * 1_000_000) / 1_000_000 : 0,
      sourceKey: sourcesKeys[0] ?? text(firstRecord, "source_key"),
      status,
      unit,
      unitCompatible,
      unitRate: unitRates[0] ?? 0,
      expectedMeasure,
      expectedUnits,
    };
  });

  const readyLineIds = groups.filter((group) => group.status === "ready").flatMap((group) => group.lineIds);
  return {
    assignedGroupCount: groups.filter((group) => group.status === "assigned").length,
    blockedGroupCount: groups.filter((group) => group.status === "blocked").length,
    groups,
    pendingLineCount: pendingLineIds.length,
    pendingLineIds,
    readyGroupCount: groups.filter((group) => group.status === "ready").length,
    readyLineIds,
    reviewGroupCount: groups.filter((group) => group.status === "review").length,
  };
}
