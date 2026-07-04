from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

QuantityRuleStatus = str


@dataclass(frozen=True)
class RuleDefinition:
    measure: str
    rule_hint: str
    units: tuple[str, ...]
    element_label: str = ""
    source: str = "system_default"
    allow_fallback_count: bool = False


CLASS_RULES: dict[str, RuleDefinition] = {
    "IFCBEAM": RuleDefinition("volumen o longitud", "NetVolume / NetLength", ("m3", "m")),
    "IFCBUILDINGELEMENTPROXY": RuleDefinition("conteo validado", "ElementCount", ("ea",), allow_fallback_count=True),
    "IFCCOLUMN": RuleDefinition("volumen o longitud", "NetVolume / NetLength", ("m3", "m")),
    "IFCCURTAINWALL": RuleDefinition("area", "NetSideArea / GrossSideArea", ("m2",)),
    "IFCDOOR": RuleDefinition("conteo", "Count / ElementCount", ("ea",), allow_fallback_count=True),
    "IFCFLOWFITTING": RuleDefinition("conteo", "Count / ElementCount", ("ea",), allow_fallback_count=True),
    "IFCFLOWSEGMENT": RuleDefinition("longitud", "NetLength", ("m",)),
    "IFCFLOWTERMINAL": RuleDefinition("conteo", "Count / ElementCount", ("ea",), allow_fallback_count=True),
    "IFCFOOTING": RuleDefinition("volumen", "NetVolume", ("m3",)),
    "IFCFURNISHINGELEMENT": RuleDefinition("conteo", "Count / ElementCount", ("ea",), allow_fallback_count=True),
    "IFCMEMBER": RuleDefinition("longitud", "NetLength", ("m",)),
    "IFCPILE": RuleDefinition("longitud o volumen", "NetLength / NetVolume", ("m", "m3")),
    "IFCPIPEFITTING": RuleDefinition("conteo", "Count / ElementCount", ("ea",), allow_fallback_count=True),
    "IFCPIPESEGMENT": RuleDefinition("longitud", "NetLength", ("m",)),
    "IFCPLATE": RuleDefinition("area", "NetArea / GrossArea", ("m2",)),
    "IFCRAILING": RuleDefinition("longitud", "NetLength", ("m",)),
    "IFCROOF": RuleDefinition("area o volumen", "NetArea / NetVolume", ("m2", "m3")),
    "IFCSLAB": RuleDefinition("area o volumen", "NetArea / NetVolume", ("m2", "m3")),
    "IFCSPACE": RuleDefinition("area o volumen", "NetFloorArea / NetVolume", ("m2", "m3")),
    "IFCSTAIR": RuleDefinition("volumen", "NetVolume", ("m3",)),
    "IFCWALL": RuleDefinition("area o volumen o longitud", "NetSideArea / NetVolume / NetLength", ("m2", "m3", "m")),
    "IFCWALLSTANDARDCASE": RuleDefinition(
        "area o volumen o longitud", "NetSideArea / NetVolume / NetLength", ("m2", "m3", "m")
    ),
    "IFCWINDOW": RuleDefinition("conteo", "Count / ElementCount", ("ea",), allow_fallback_count=True),
}


CLASS_LABELS: dict[str, str] = {
    "IFCBEAM": "Viga",
    "IFCBUILDINGELEMENTPROXY": "Elemento generico",
    "IFCCOLUMN": "Columna",
    "IFCCURTAINWALL": "Muro cortina",
    "IFCDOOR": "Puerta",
    "IFCFLOWFITTING": "Accesorio MEP",
    "IFCFLOWSEGMENT": "Tramo MEP",
    "IFCFLOWTERMINAL": "Terminal MEP",
    "IFCFOOTING": "Cimentacion",
    "IFCFURNISHINGELEMENT": "Mobiliario",
    "IFCMEMBER": "Miembro estructural",
    "IFCPILE": "Pilote",
    "IFCPIPEFITTING": "Accesorio de tuberia",
    "IFCPIPESEGMENT": "Tuberia",
    "IFCPLATE": "Placa",
    "IFCRAILING": "Baranda",
    "IFCROOF": "Cubierta",
    "IFCSLAB": "Losa",
    "IFCSPACE": "Espacio",
    "IFCSTAIR": "Escalera",
    "IFCWALL": "Muro",
    "IFCWALLSTANDARDCASE": "Muro",
    "IFCWINDOW": "Ventana",
}


def evaluate_quantity_rule(
    line: Mapping[str, Any] | object,
    catalog: Mapping[str, RuleDefinition] | None = None,
) -> dict[str, Any]:
    line = effective_quantity_line(line)
    ifc_class = _field(line, "ifc_class") or _field(line, "category")
    definition = _rule_for(ifc_class, _field(line, "unit"), catalog)
    source = _source_for(line)
    findings: list[str] = []
    normalized_unit = normalize_unit(_field(line, "unit"))
    expected_units = list(definition.units)
    preferred_measure = definition.measure.split(" o ")[0].strip() or definition.measure
    preferred_unit = expected_units[0] if expected_units else ""
    inferred_rule_unit = _measurement_unit(_field(line, "measurement_rule"))
    fallback_count_allowed = definition.allow_fallback_count and "ea" in expected_units
    quantity = _float_field(line, "quantity")

    if quantity <= 0:
        findings.append("Cantidad debe ser mayor que cero.")
    if not normalized_unit:
        findings.append("Unidad pendiente.")
    if expected_units and normalized_unit and normalized_unit not in expected_units:
        findings.append(
            f"Unidad {_field(line, 'unit')} no coincide con la regla esperada ({' / '.join(expected_units)})."
        )
    if inferred_rule_unit and normalized_unit and inferred_rule_unit != normalized_unit:
        findings.append(
            f"La regla {_field(line, 'measurement_rule')} requiere {inferred_rule_unit}, no {_field(line, 'unit')}."
        )
    if source == "Conteo fallback" and not fallback_count_allowed:
        findings.append(
            f"Medicion dimensional requerida: {_field(line, 'ifc_class') or 'la clase IFC'} "
            f"debe medirse por {preferred_measure} ({preferred_unit})."
        )

    status: QuantityRuleStatus = "blocked" if findings else "valid"
    confidence = (
        "Alta"
        if status == "valid" and source in {"IFC Quantity Set publicado", "Calculo geometrico desde IFC"}
        else "Media"
    )

    display_class = _field(line, "ifc_class") or "Clase IFC pendiente"
    measurement_rule = _field(line, "measurement_rule") or "Sin regla"
    source_text = "conteo de elementos sin Quantity Set" if source == "Conteo fallback" else source
    return {
        "allow_fallback_count": fallback_count_allowed,
        "status": status,
        "confidence": confidence,
        "source": source,
        "policy_version": 2,
        "rule_source": definition.source,
        "element_label": definition.element_label or CLASS_LABELS.get(normalize_ifc_class(ifc_class), display_class),
        "expected_measure": definition.measure,
        "expected_units": expected_units,
        "preferred_measure": preferred_measure,
        "preferred_unit": preferred_unit,
        "accepted_rules": [item.strip() for item in definition.rule_hint.split("/")],
        "findings": findings,
        "explanation": (
            f"{display_class}: regla esperada {definition.measure}; {definition.rule_hint}. "
            f"{measurement_rule} viene de {source_text}."
        ),
    }


def summarize_quantity_rules(
    lines: list[Mapping[str, Any] | object],
    catalog: Mapping[str, RuleDefinition] | None = None,
) -> dict[str, int]:
    summary = {"authoritative": 0, "blocked": 0, "review": 0, "total": 0, "valid": 0}
    for line in lines:
        result = evaluate_quantity_rule(line, catalog)
        summary["total"] += 1
        summary[result["status"]] += 1
        if result["source"] == "IFC Quantity Set publicado" and result["status"] == "valid":
            summary["authoritative"] += 1
    return summary


def normalize_ifc_class(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "", _compact(value)).upper()


def normalize_unit(value: str | None) -> str:
    text = _compact(str(value or "")).lower().replace(" ", "")
    if text in {"m2", "sqm", "sq.m", "m^2"}:
        return "m2"
    if text in {"m3", "cum", "cu.m", "m^3"}:
        return "m3"
    if text in {"ea", "each", "und", "u", "un", "unidad", "unidades"}:
        return "ea"
    if text in {"ml", "lm", "m"}:
        return "m"
    if text in {"kg", "kilogram", "kilograms"}:
        return "kg"
    return text


def default_quantity_rule_records() -> list[dict[str, Any]]:
    return [
        {
            "ifc_class": ifc_class,
            "element_label": CLASS_LABELS.get(ifc_class, _humanize_ifc_class(ifc_class)),
            "expected_measure": rule.measure,
            "rule_hint": rule.rule_hint,
            "expected_units": list(rule.units),
            "allow_fallback_count": rule.allow_fallback_count,
            "source": "system_default",
            "status": "active",
        }
        for ifc_class, rule in sorted(CLASS_RULES.items())
    ]


def build_quantity_rule_catalog(records: Iterable[Mapping[str, Any] | object]) -> dict[str, RuleDefinition]:
    catalog: dict[str, RuleDefinition] = {}
    for record in records:
        status = _field(record, "status") or "active"
        if status != "active":
            continue
        ifc_class = normalize_ifc_class(_field(record, "ifc_class"))
        if not ifc_class:
            continue
        units = tuple(filter(None, (normalize_unit(unit) for unit in _list_field(record, "expected_units"))))
        catalog[ifc_class] = RuleDefinition(
            measure=_field(record, "expected_measure") or "cantidad controlada",
            rule_hint=_field(record, "rule_hint") or "Quantity / Unit",
            units=units,
            element_label=_field(record, "element_label")
            or CLASS_LABELS.get(ifc_class, _humanize_ifc_class(ifc_class)),
            source=_field(record, "source") or "project",
            allow_fallback_count=_bool_field(record, "allow_fallback_count", False),
        )
    return catalog


def _rule_for(
    ifc_class: str,
    unit: str,
    catalog: Mapping[str, RuleDefinition] | None = None,
) -> RuleDefinition:
    normalized = normalize_ifc_class(ifc_class)
    if catalog and normalized in catalog:
        return catalog[normalized]
    return CLASS_RULES.get(
        normalized,
        RuleDefinition("cantidad controlada", "Quantity / Unit", tuple(filter(None, [normalize_unit(unit)]))),
    )


def effective_quantity_line(line: Mapping[str, Any] | object) -> dict[str, Any]:
    raw_data = dict(_raw_data(line))
    controlled = raw_data.get("controlled_measurement")
    controlled_record = controlled if isinstance(controlled, dict) else {}
    use_controlled = controlled_record.get("status") == "approved"
    fields = (
        "ifc_class",
        "category",
        "quantity",
        "unit",
        "measurement_rule",
        "validation_notes",
    )
    payload: dict[str, Any] = {}
    for field in fields:
        if isinstance(line, Mapping):
            payload[field] = line.get(field, "")
        else:
            payload[field] = getattr(line, field, "")
    payload["raw_data"] = raw_data
    if use_controlled:
        payload["quantity"] = controlled_record.get("quantity", payload["quantity"])
        payload["unit"] = controlled_record.get("unit", payload["unit"])
        payload["measurement_rule"] = controlled_record.get("measurement_rule", payload["measurement_rule"])
    return payload


def evaluate_effective_quantity_rule(
    line: Mapping[str, Any] | object,
    catalog: Mapping[str, RuleDefinition] | None = None,
) -> dict[str, Any]:
    return evaluate_quantity_rule(effective_quantity_line(line), catalog)


def _measurement_unit(measurement_rule: str) -> str:
    normalized = _compact(measurement_rule).lower()
    if "volume" in normalized:
        return "m3"
    if "area" in normalized:
        return "m2"
    if "length" in normalized:
        return "m"
    if "count" in normalized:
        return "ea"
    return ""


def _source_for(line: Mapping[str, Any] | object) -> str:
    raw_data = _raw_data(line)
    controlled = raw_data.get("controlled_measurement")
    if isinstance(controlled, dict) and controlled.get("status") == "approved":
        controlled_rule = _compact(str(controlled.get("measurement_rule") or "")).lower()
        controlled_source = _compact(str(controlled.get("source") or "")).lower()
        if controlled_rule.startswith("geometry") or "geometry" in controlled_source or "geometr" in controlled_source:
            return "Calculo geometrico desde IFC"
        return "Plantilla Excel/CSV controlada"
    measurement_rule = _field(line, "measurement_rule").lower()
    notes = _field(line, "validation_notes").lower()
    if measurement_rule == "elementcount" or "no published ifc quantity" in notes:
        return "Conteo fallback"
    if _compact(str(raw_data.get("ifc_entity", ""))):
        return "IFC Quantity Set publicado"
    return "Plantilla Excel/CSV controlada"


def _field(line: Mapping[str, Any] | object, name: str) -> str:
    if isinstance(line, Mapping):
        value = line.get(name, "")
    else:
        value = getattr(line, name, "")
    if isinstance(value, list):
        return "; ".join(str(item) for item in value)
    return _compact(str(value or ""))


def _float_field(line: Mapping[str, Any] | object, name: str) -> float:
    try:
        return float(_field(line, name) or 0)
    except ValueError:
        return 0.0


def _raw_data(line: Mapping[str, Any] | object) -> dict[str, Any]:
    if isinstance(line, Mapping):
        value = line.get("raw_data", {})
    else:
        value = getattr(line, "raw_data", {})
    return value if isinstance(value, dict) else {}


def _list_field(line: Mapping[str, Any] | object, name: str) -> list[str]:
    if isinstance(line, Mapping):
        value = line.get(name, [])
    else:
        value = getattr(line, name, [])
    if isinstance(value, (list, tuple)):
        return [_compact(str(item)) for item in value if _compact(str(item))]
    text = _compact(str(value or ""))
    if not text:
        return []
    return [_compact(item) for item in re.split(r"[,/;]+", text) if _compact(item)]


def _bool_field(line: Mapping[str, Any] | object, name: str, default: bool = False) -> bool:
    if isinstance(line, Mapping):
        value = line.get(name, default)
    else:
        value = getattr(line, name, default)
    if isinstance(value, bool):
        return value
    return _compact(str(value)).lower() in {"1", "true", "yes", "si"}


def _humanize_ifc_class(value: str) -> str:
    text = re.sub(r"^IFC", "", value.upper()).title()
    return re.sub(r"([a-z])([A-Z])", r"\1 \2", text).strip() or value


def _compact(value: str) -> str:
    return value.strip()
