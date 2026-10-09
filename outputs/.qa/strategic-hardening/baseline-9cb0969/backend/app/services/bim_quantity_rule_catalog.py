from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.models import BimQuantityRule
from app.services.bim_quantity_rules import (
    build_quantity_rule_catalog,
    default_quantity_rule_records,
    normalize_ifc_class,
    normalize_unit,
)


def ensure_project_quantity_rules(db: Session, tenant_id: int, project_id: int) -> list[BimQuantityRule]:
    rules = _list_rules(db, tenant_id, project_id)
    existing_by_class = {normalize_ifc_class(rule.ifc_class): rule for rule in rules}
    for record in default_quantity_rule_records():
        ifc_class = normalize_ifc_class(str(record["ifc_class"]))
        existing = existing_by_class.get(ifc_class)
        if existing and existing.source != "system_default":
            continue
        if existing:
            existing.element_label = str(record["element_label"])
            existing.expected_measure = str(record["expected_measure"])
            existing.rule_hint = str(record["rule_hint"])
            existing.expected_units = list(record["expected_units"])
            existing.allow_fallback_count = bool(record["allow_fallback_count"])
            existing.status = str(record["status"])
            continue
        rule = BimQuantityRule(
            tenant_id=tenant_id,
            project_id=project_id,
            ifc_class=ifc_class,
            element_label=str(record["element_label"]),
            expected_measure=str(record["expected_measure"]),
            rule_hint=str(record["rule_hint"]),
            expected_units=list(record["expected_units"]),
            allow_fallback_count=bool(record["allow_fallback_count"]),
            source=str(record["source"]),
            status=str(record["status"]),
        )
        db.add(rule)
        existing_by_class[ifc_class] = rule
    db.flush()
    return _list_rules(db, tenant_id, project_id)


def project_quantity_rule_catalog(db: Session, tenant_id: int, project_id: int) -> dict:
    rules = ensure_project_quantity_rules(db, tenant_id, project_id)
    return build_quantity_rule_catalog(rules)


def normalize_expected_units(values: list[str]) -> list[str]:
    units: list[str] = []
    for value in values:
        unit = normalize_unit(value)
        if unit and unit not in units:
            units.append(unit)
    return units


def _list_rules(db: Session, tenant_id: int, project_id: int) -> list[BimQuantityRule]:
    return list(
        db.scalars(
            select(BimQuantityRule)
            .where(BimQuantityRule.tenant_id == tenant_id, BimQuantityRule.project_id == project_id)
            .order_by(BimQuantityRule.ifc_class)
        ).all()
    )
