import type { QuantityTakeoffLine } from "../types";

export type QuantityRuleStatus = "valid" | "review" | "blocked";

export type QuantityRuleResult = {
  allowFallbackCount: boolean;
  confidence: "Alta" | "Media" | "Baja";
  expectedMeasure: string;
  expectedUnits: string[];
  explanation: string;
  findings: string[];
  policyVersion: number;
  preferredMeasure: string;
  preferredUnit: string;
  source:
    | "IFC Quantity Set publicado"
    | "Plantilla Excel/CSV controlada"
    | "Conteo fallback"
    | "Calculo geometrico desde IFC";
  status: QuantityRuleStatus;
};

export type QuantityRuleSummary = {
  authoritative: number;
  blocked: number;
  review: number;
  total: number;
  valid: number;
};

export type IfcGeometryDimensions = {
  x: number;
  y: number;
  z: number;
};

export type GeometricQuantityEstimate = {
  confidence: "Media";
  explanation: string;
  measurementRule: "GeometryAreaBBox" | "GeometryLengthBBox" | "GeometryVolumeBBox";
  quantity: number;
  source: "Calculo geometrico desde IFC";
  unit: "m" | "m2" | "m3";
};

type RuleDefinition = {
  allowFallbackCount?: boolean;
  measure: string;
  ruleHint: string;
  units: string[];
};

const CLASS_RULES: Record<string, RuleDefinition> = {
  IFCBEAM: { measure: "volumen o longitud", ruleHint: "NetVolume / NetLength", units: ["m3", "m"] },
  IFCBUILDINGELEMENTPROXY: {
    allowFallbackCount: true,
    measure: "conteo validado",
    ruleHint: "ElementCount",
    units: ["ea", "und"],
  },
  IFCCOLUMN: { measure: "volumen o longitud", ruleHint: "NetVolume / NetLength", units: ["m3", "m"] },
  IFCCURTAINWALL: { measure: "area", ruleHint: "NetSideArea / GrossSideArea", units: ["m2"] },
  IFCDOOR: { allowFallbackCount: true, measure: "conteo", ruleHint: "Count / ElementCount", units: ["ea", "und"] },
  IFCFLOWFITTING: {
    allowFallbackCount: true,
    measure: "conteo",
    ruleHint: "Count / ElementCount",
    units: ["ea", "und"],
  },
  IFCFLOWSEGMENT: { measure: "longitud", ruleHint: "NetLength", units: ["m"] },
  IFCFLOWTERMINAL: {
    allowFallbackCount: true,
    measure: "conteo",
    ruleHint: "Count / ElementCount",
    units: ["ea", "und"],
  },
  IFCFOOTING: { measure: "volumen", ruleHint: "NetVolume", units: ["m3"] },
  IFCMEMBER: { measure: "longitud", ruleHint: "NetLength", units: ["m"] },
  IFCPILE: { measure: "longitud o volumen", ruleHint: "NetLength / NetVolume", units: ["m", "m3"] },
  IFCPIPEFITTING: {
    allowFallbackCount: true,
    measure: "conteo",
    ruleHint: "Count / ElementCount",
    units: ["ea", "und"],
  },
  IFCPIPESEGMENT: { measure: "longitud", ruleHint: "NetLength", units: ["m"] },
  IFCPLATE: { measure: "area", ruleHint: "NetArea / GrossArea", units: ["m2"] },
  IFCRAILING: { measure: "longitud", ruleHint: "NetLength", units: ["m"] },
  IFCROOF: { measure: "area o volumen", ruleHint: "NetArea / NetVolume", units: ["m2", "m3"] },
  IFCSLAB: { measure: "area o volumen", ruleHint: "NetArea / NetVolume", units: ["m2", "m3"] },
  IFCSPACE: { measure: "area o volumen", ruleHint: "NetFloorArea / NetVolume", units: ["m2", "m3"] },
  IFCSTAIR: { measure: "volumen", ruleHint: "NetVolume", units: ["m3"] },
  IFCWALL: {
    measure: "area o volumen o longitud",
    ruleHint: "NetSideArea / NetVolume / NetLength",
    units: ["m2", "m3", "m"],
  },
  IFCWALLSTANDARDCASE: {
    measure: "area o volumen o longitud",
    ruleHint: "NetSideArea / NetVolume / NetLength",
    units: ["m2", "m3", "m"],
  },
  IFCWINDOW: { allowFallbackCount: true, measure: "conteo", ruleHint: "Count / ElementCount", units: ["ea", "und"] },
};

function compact(value: string | null | undefined) {
  return value?.trim() ?? "";
}

function normalizeIfcClass(value: string) {
  return compact(value)
    .replace(/[^A-Za-z0-9]/g, "")
    .toUpperCase();
}

function normalizeLengthScaleToMeters(value: string | null | undefined) {
  const text = compact(value)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "");
  if (!text) return null;
  if (["mm", "milli", "millimeter", "millimeters", "millimetre", "millimetres"].includes(text)) return 0.001;
  if (["cm", "centi", "centimeter", "centimeters", "centimetre", "centimetres"].includes(text)) return 0.01;
  if (["m", "meter", "meters", "metre", "metres"].includes(text)) return 1;
  if (text.includes("millimeter") || text.includes("millimetre")) return 0.001;
  if (text.includes("centimeter") || text.includes("centimetre")) return 0.01;
  if (text.includes("meter") || text.includes("metre")) return 1;
  return null;
}

function normalizeUnit(value: string) {
  const text = compact(value).toLowerCase().replace(/\s+/g, "");
  if (["m2", "m²", "sqm", "sq.m", "m^2"].includes(text)) return "m2";
  if (["m3", "m³", "cum", "cu.m", "m^3"].includes(text)) return "m3";
  if (["ea", "each", "und", "u", "un", "unidad", "unidades"].includes(text)) return "ea";
  if (["ml", "lm", "m"].includes(text)) return "m";
  if (["kg", "kilogram", "kilograms"].includes(text)) return "kg";
  return text;
}

function roundQuantity(value: number) {
  return Number(value.toFixed(3));
}

function metricDimensions(dimensions: IfcGeometryDimensions | null | undefined, units: string | null | undefined) {
  if (!dimensions) return null;
  const scale = normalizeLengthScaleToMeters(units);
  if (!scale) return null;
  const values = [dimensions.x, dimensions.y, dimensions.z].map((value) => Number(value) * scale);
  if (values.some((value) => !Number.isFinite(value) || value <= 0)) return null;
  return values.sort((left, right) => right - left);
}

export function estimateQuantityFromGeometry(
  ifcClass: string,
  dimensions: IfcGeometryDimensions | null | undefined,
  modelUnits?: string | null
): GeometricQuantityEstimate | null {
  const normalizedClass = normalizeIfcClass(ifcClass);
  const dims = metricDimensions(dimensions, modelUnits);
  if (!normalizedClass || !dims) return null;

  const areaClasses = new Set([
    "IFCCURTAINWALL",
    "IFCPLATE",
    "IFCROOF",
    "IFCSLAB",
    "IFCSPACE",
    "IFCWALL",
    "IFCWALLSTANDARDCASE",
  ]);
  const volumeClasses = new Set(["IFCBEAM", "IFCCOLUMN", "IFCFOOTING", "IFCPILE", "IFCSTAIR"]);
  const lengthClasses = new Set(["IFCFLOWSEGMENT", "IFCMEMBER", "IFCPIPESEGMENT", "IFCRAILING"]);

  if (areaClasses.has(normalizedClass)) {
    return {
      confidence: "Media",
      explanation: "Area sugerida con las dos mayores dimensiones del bounding box IFC seleccionado.",
      measurementRule: "GeometryAreaBBox",
      quantity: roundQuantity(dims[0] * dims[1]),
      source: "Calculo geometrico desde IFC",
      unit: "m2",
    };
  }
  if (volumeClasses.has(normalizedClass)) {
    return {
      confidence: "Media",
      explanation: "Volumen sugerido con largo, ancho y alto del bounding box IFC seleccionado.",
      measurementRule: "GeometryVolumeBBox",
      quantity: roundQuantity(dims[0] * dims[1] * dims[2]),
      source: "Calculo geometrico desde IFC",
      unit: "m3",
    };
  }
  if (lengthClasses.has(normalizedClass)) {
    return {
      confidence: "Media",
      explanation: "Longitud sugerida con la mayor dimension del bounding box IFC seleccionado.",
      measurementRule: "GeometryLengthBBox",
      quantity: roundQuantity(dims[0]),
      source: "Calculo geometrico desde IFC",
      unit: "m",
    };
  }

  return null;
}

function controlledMeasurement(line: QuantityTakeoffLine) {
  const value = line.raw_data?.controlled_measurement;
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function effectiveQuantityValues(line: QuantityTakeoffLine) {
  const controlled = controlledMeasurement(line);
  if (controlled && String(controlled.status ?? "") === "approved") {
    return {
      measurementRule: compact(String(controlled.measurement_rule ?? line.measurement_rule)),
      quantity: Number(controlled.quantity ?? line.quantity),
      unit: compact(String(controlled.unit ?? line.unit)),
    };
  }
  return { measurementRule: line.measurement_rule, quantity: Number(line.quantity || 0), unit: line.unit };
}

function sourceFor(line: QuantityTakeoffLine) {
  const controlled = controlledMeasurement(line);
  if (controlled && String(controlled.status ?? "") === "approved") {
    const rule = compact(String(controlled.measurement_rule ?? "")).toLowerCase();
    const source = compact(String(controlled.source ?? "")).toLowerCase();
    if (rule.startsWith("geometry") || source.includes("geometry") || source.includes("geometr")) {
      return "Calculo geometrico desde IFC" as const;
    }
    return "Plantilla Excel/CSV controlada" as const;
  }
  const rule = compact(line.measurement_rule).toLowerCase();
  const notes = compact(line.validation_notes).toLowerCase();
  if (rule === "elementcount" || notes.includes("no published ifc quantity")) {
    return "Conteo fallback" as const;
  }
  if (line.raw_data && typeof line.raw_data === "object" && compact(String(line.raw_data.ifc_entity ?? ""))) {
    return "IFC Quantity Set publicado" as const;
  }
  return "Plantilla Excel/CSV controlada" as const;
}

function ruleFor(line: QuantityTakeoffLine) {
  const ifcClass = normalizeIfcClass(line.ifc_class || line.category);
  return (
    CLASS_RULES[ifcClass] ?? {
      measure: "cantidad controlada",
      ruleHint: "Quantity / Unit",
      units: [normalizeUnit(line.unit)].filter(Boolean),
    }
  );
}

function preferredMeasure(definition: RuleDefinition) {
  return definition.measure.split(" o ")[0]?.trim() || definition.measure;
}

function measurementUnit(measurementRule: string) {
  const normalized = compact(measurementRule).toLowerCase();
  if (normalized.includes("volume")) return "m3";
  if (normalized.includes("area")) return "m2";
  if (normalized.includes("length")) return "m";
  if (normalized.includes("count")) return "ea";
  return "";
}

function auditedRuleFor(line: QuantityTakeoffLine): QuantityRuleResult | null {
  const rawRule = line.raw_data?.quantity_rule;
  if (!rawRule || typeof rawRule !== "object" || Array.isArray(rawRule)) return null;
  const rule = rawRule as Record<string, unknown>;
  if (Number(rule.policy_version ?? 0) < 2) return null;
  const status = String(rule.status ?? "");
  const confidence = String(rule.confidence ?? "");
  const source = String(rule.source ?? "");
  if (!["valid", "review", "blocked"].includes(status)) return null;
  if (!["Alta", "Media", "Baja"].includes(confidence)) return null;
  if (
    ![
      "IFC Quantity Set publicado",
      "Plantilla Excel/CSV controlada",
      "Conteo fallback",
      "Calculo geometrico desde IFC",
    ].includes(source)
  )
    return null;

  return {
    allowFallbackCount: Boolean(rule.allow_fallback_count),
    confidence: confidence as QuantityRuleResult["confidence"],
    expectedMeasure: String(rule.expected_measure ?? rule.expectedMeasure ?? ""),
    expectedUnits: Array.isArray(rule.expected_units)
      ? rule.expected_units.map((unit) => String(unit)).filter(Boolean)
      : Array.isArray(rule.expectedUnits)
        ? rule.expectedUnits.map((unit) => String(unit)).filter(Boolean)
        : [],
    explanation: String(rule.explanation ?? ""),
    findings: Array.isArray(rule.findings) ? rule.findings.map((finding) => String(finding)).filter(Boolean) : [],
    policyVersion: Number(rule.policy_version ?? 2),
    preferredMeasure: String(rule.preferred_measure ?? ""),
    preferredUnit: String(rule.preferred_unit ?? ""),
    source: source as QuantityRuleResult["source"],
    status: status as QuantityRuleStatus,
  };
}

export function evaluateQuantityRule(line: QuantityTakeoffLine): QuantityRuleResult {
  const auditedRule = auditedRuleFor(line);
  if (auditedRule) return auditedRule;

  const definition = ruleFor(line);
  const source = sourceFor(line);
  const effective = effectiveQuantityValues(line);
  const findings: string[] = [];
  const normalizedUnit = normalizeUnit(effective.unit);
  const expectedUnits = definition.units;
  const allowFallbackCount = Boolean(
    definition.allowFallbackCount && expectedUnits.some((unit) => normalizeUnit(unit) === "ea")
  );
  const preferredUnit = normalizeUnit(expectedUnits[0] ?? "");
  const inferredRuleUnit = measurementUnit(effective.measurementRule);

  if (!effective.quantity || effective.quantity <= 0) findings.push("Cantidad debe ser mayor que cero.");
  if (!normalizedUnit) findings.push("Unidad pendiente.");
  if (expectedUnits.length && normalizedUnit && !expectedUnits.map(normalizeUnit).includes(normalizedUnit)) {
    findings.push(`Unidad ${effective.unit} no coincide con la regla esperada (${expectedUnits.join(" / ")}).`);
  }
  if (inferredRuleUnit && normalizedUnit && inferredRuleUnit !== normalizedUnit) {
    findings.push(`La regla ${effective.measurementRule} requiere ${inferredRuleUnit}, no ${effective.unit}.`);
  }
  if (source === "Conteo fallback" && !allowFallbackCount) {
    findings.push(
      `Medicion dimensional requerida: ${compact(line.ifc_class) || "la clase IFC"} debe medirse por ${preferredMeasure(definition)} (${preferredUnit}).`
    );
  }

  const hasBlockingFinding = findings.length > 0;
  const status: QuantityRuleStatus = hasBlockingFinding ? "blocked" : "valid";
  const confidence =
    status === "blocked"
      ? "Media"
      : source === "IFC Quantity Set publicado"
        ? "Alta"
        : source === "Calculo geometrico desde IFC"
          ? "Alta"
          : source === "Plantilla Excel/CSV controlada"
            ? "Media"
            : "Media";
  const ifcClass = compact(line.ifc_class) || "Clase IFC pendiente";
  const sourceText = source === "Conteo fallback" ? "conteo de elementos sin Quantity Set" : source;

  return {
    allowFallbackCount,
    confidence,
    expectedMeasure: definition.measure,
    expectedUnits,
    explanation: `${ifcClass}: regla esperada ${definition.measure}; ${definition.ruleHint}. ${effective.measurementRule || "Sin regla"} viene de ${sourceText}.`,
    findings,
    policyVersion: 2,
    preferredMeasure: preferredMeasure(definition),
    preferredUnit,
    source,
    status,
  };
}

export function summarizeQuantityRules(lines: QuantityTakeoffLine[]): QuantityRuleSummary {
  return lines.reduce<QuantityRuleSummary>(
    (summary, line) => {
      const result = evaluateQuantityRule(line);
      summary.total += 1;
      if (result.status === "valid") summary.valid += 1;
      if (result.status === "review") summary.review += 1;
      if (result.status === "blocked") summary.blocked += 1;
      if (result.source === "IFC Quantity Set publicado" && result.status === "valid") summary.authoritative += 1;
      return summary;
    },
    { authoritative: 0, blocked: 0, review: 0, total: 0, valid: 0 }
  );
}
