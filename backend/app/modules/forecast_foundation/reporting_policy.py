"""Deterministic report policies, never a Schedule or CPM calculation engine."""

from collections import defaultdict
from copy import deepcopy
from datetime import date, datetime, timedelta
from decimal import Decimal, DecimalException, InvalidOperation

from app.modules.forecast_foundation.policy import number as forecast_number

ZERO = Decimal("0")
SCALE = Decimal("0.00000001")
GROUPS = {"PARENT_WBS", "CWA", "PACKAGE", "AREA", "ZONE", "SYSTEM", "DISCIPLINE"}
SERIES = (
    "PLANNED_PROGRESS",
    "APPROVED_ACTUAL_PROGRESS",
    "EARNED_VALUE",
    "PLANNED_VALUE",
    "ACTUAL_COST",
    "FORECAST_COST",
)
NARRATIVE_SECTIONS = (
    "EXECUTIVE_SUMMARY",
    "SCHEDULE",
    "CRITICAL_NEAR_CRITICAL",
    "COST",
    "PROGRESS",
    "FORECAST",
    "CONSTRAINTS_READINESS",
    "MITIGATION_ACTIONS",
)
TREND_EVENT_LINKAGE = {
    "schema_version": 1,
    "state": "FUTURE_LINKAGE_METADATA_ONLY",
    "allowed_target_kinds": ["TREND", "POTENTIAL_CHANGE", "RISK", "ISSUE", "CLAIM"],
    "source_anchor_fields": [
        "project_workspace_id",
        "period_id",
        "report_id",
        "report_content_hash",
        "forecast_version_id",
        "metric",
    ],
    "future_target_fields": ["target_kind", "external_reference"],
    "write_back_supported": False,
    "creates_target_records": False,
}


def number(value):
    if value is None or isinstance(value, bool):
        raise ValueError("REPORT_NUMERIC_BASIS_REQUIRED")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ValueError("REPORT_NUMERIC_BASIS_REQUIRED") from error
    if not result.is_finite():
        raise ValueError("REPORT_NUMERIC_BASIS_REQUIRED")
    return result


def scalar(value):
    return str(number(value).quantize(SCALE)) if value is not None else None


def business_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None or value == "":
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError as error:
        raise ValueError("REPORT_SOURCE_DATE_INVALID") from error


def finish_variance(reference, projected):
    first, second = business_date(reference), business_date(projected)
    return (second - first).days if first is not None and second is not None else None


def dashboard_indicators(metrics, thresholds):
    """Classify observed values with pinned policy; missing data never reads as zero."""
    rules = (
        ("cpi", "cpi_warning", "RATIO", "BELOW"),
        ("spi", "spi_warning", "RATIO", "BELOW"),
        ("finish_variance_days", "finish_variance_warning_days", "CALENDAR_DAY", "ABOVE"),
    )
    indicators = []
    for metric, threshold_key, unit, direction in rules:
        value = metrics.get(metric)
        threshold = thresholds[threshold_key]
        status, reasons = "NOT_COMPUTABLE", ["DASHBOARD_SOURCE_METRIC_REQUIRED"]
        if value is not None:
            observation, boundary = number(value), number(threshold)
            warning = observation < boundary if direction == "BELOW" else observation > boundary
            status, reasons = "WARNING" if warning else "WITHIN_THRESHOLD", []
        indicators.append(
            {
                "metric": metric,
                "value": value,
                "threshold": threshold,
                "unit": unit,
                "warning_when": direction,
                "status": status,
                "reason_codes": reasons,
            }
        )
    return indicators


def readiness_rollup(packages, current_readiness):
    """Unknown or stale readiness is not evidence that zero packages are ready."""
    states = [current_readiness.get(str(package["id"]), {}) for package in packages]
    valid = [
        row
        for row in states
        if row.get("assessment_id")
        and not row.get("stale")
        and row.get("readiness_state") not in {None, "UNKNOWN", "NOT_ASSESSED"}
    ]
    ready_count = sum(row["readiness_state"] in {"READY", "RELEASED"} for row in valid)
    complete = bool(states) and len(valid) == len(states)
    counts = defaultdict(int)
    for row in states:
        counts[row.get("readiness_state") or "UNKNOWN"] += 1
    return {
        "status": "COMPUTABLE" if complete else "NOT_COMPUTABLE",
        "reason_codes": []
        if complete
        else ["READINESS_ASSESSMENT_COVERAGE_REQUIRED" if states else "READINESS_SOURCE_REQUIRED"],
        "ready_count": ready_count,
        "package_count": len(packages),
        "current_assessment_count": len(valid),
        "stale_or_unassessed_count": len(states) - len(valid),
        "state_counts": dict(sorted(counts.items())),
        "readiness_percent": scalar(number(ready_count) * 100 / number(len(states))) if complete else None,
        "items": [row for row in states if row],
    }


def near_critical(activity, threshold, unit):
    """A P6 float number retains its imported unit; no hours/day assumption."""
    if activity.get("total_float") is None or activity.get("float_unit") != unit:
        return "UNKNOWN"
    return number(activity["total_float"]) <= number(threshold)


def physical_progress_variance(baseline, projection, measurements, *, pv, bac, currency):
    """Compare physical work only when both sides use exactly the same budget weights.

    A quantity/manual physical percentage is not made budget-weighted by merely
    sharing a percent sign. Complete, disjoint approved baseline line coverage and
    matching frozen weight authorities are necessary for the PV/BAC comparison.
    """
    unavailable = {
        "planned_progress": None,
        "physical_variance": None,
        "unit": "PERCENTAGE_POINT",
        "status": "NOT_COMPUTABLE",
        "reason_codes": ["COMPATIBLE_PLANNED_PHYSICAL_CURVE_REQUIRED"],
        "basis": "MATCHED_APPROVED_COST_BASELINE_BUDGET_WEIGHTS_ONLY",
    }
    groups = projection.get("items", [])
    if len(groups) != 1 or groups[0].get("status") != "COMPUTABLE" or groups[0].get("weighting_basis") != "BUDGET":
        return unavailable
    group = groups[0]
    rows = {row["id"]: row for row in measurements}
    lines = baseline.get("snapshot_json", {}).get("lines", [])
    lines = [line for line in lines if line.get("cost_class") != "MANAGEMENT_RESERVE"]
    by_line = {line["id"]: line for line in lines}
    selected, covered = [], set()
    try:
        total_budget = number(bac)
        if (
            total_budget <= ZERO
            or pv is None
            or not lines
            or len(by_line) != len(lines)
            or any(line.get("currency") != currency for line in lines)
            or sum((number(line["amount"]) for line in lines), ZERO) != total_budget
            or number(group.get("total_weight")) != total_budget
        ):
            return unavailable
        for identity in group.get("input_ids", []):
            row = rows.get(identity, {})
            source = row.get("source_snapshot", {}).get("weight_source", {})
            identifiers = source.get("line_ids", [])
            if (
                row.get("progress_type") != "PHYSICAL"
                or row.get("status") != "APPROVED"
                or row.get("weighting_basis") != "BUDGET"
                or source.get("authority") != "APPROVED_COST_BASELINE"
                or source.get("cost_baseline_id") != baseline.get("id")
                or source.get("cost_baseline_hash") != baseline.get("content_hash")
                or source.get("currency") != currency
                or not identifiers
                or len(set(identifiers)) != len(identifiers)
                or not set(identifiers) <= by_line.keys()
                or covered & set(identifiers)
            ):
                return unavailable
            weight = sum((number(by_line[i]["amount"]) for i in identifiers), ZERO)
            if number(row.get("weight")) != weight or number(source.get("weight")) != weight:
                return unavailable
            selected.append(row)
            covered.update(identifiers)
        if not selected or covered != by_line.keys():
            return unavailable
        actual = number(group.get("progress_value"))
        weighted = sum((number(row["progress_value"]) * number(row["weight"]) for row in selected), ZERO) / total_budget
        if actual != weighted.quantize(SCALE):
            return unavailable
        planned = number(pv) * 100 / total_budget
        if not ZERO <= planned <= 100 or not ZERO <= actual <= 100:
            return unavailable
    except (ValueError, KeyError, TypeError):
        return unavailable
    return {
        **unavailable,
        "planned_progress": scalar(planned),
        "physical_variance": scalar(actual - planned),
        "status": "COMPUTABLE",
        "reason_codes": [],
        "cost_baseline_id": baseline["id"],
        "cost_baseline_hash": baseline["content_hash"],
        "measurement_ids": [row["id"] for row in selected],
    }


def package_activity_context(mappings, *, plan_ids, scope_ids, schedule_version_id, activity_external_id):
    """Explicit identity joins are context, not Schedule assignments or quantities."""
    proofs = []
    for mapping in mappings:
        if mapping.get("status") != "ACTIVE" or mapping.get("mapping_health", "VALID") != "VALID":
            continue
        kind = mapping.get("target_kind")
        direct = (
            kind == "ACTIVITY"
            and mapping.get("schedule_version_id") == schedule_version_id
            and str(mapping.get("activity_external_id")) == str(activity_external_id)
        )
        plan = kind == "PLAN" and mapping.get("target_id") in plan_ids
        scope = kind == "SCOPE" and mapping.get("target_id") in scope_ids
        if direct or plan or scope:
            proofs.append(
                {
                    "work_package_id": mapping["work_package_id"],
                    "mapping_id": mapping["id"],
                    "mapping_hash": mapping.get("content_hash"),
                    "target_kind": kind,
                    "target_id": mapping.get("target_id"),
                    "phase": mapping.get("phase"),
                    "via": "DIRECT_ACTIVITY" if direct else "SHARED_PLAN_ID" if plan else "SHARED_SCOPE_ID",
                }
            )
    identities = sorted({proof["work_package_id"] for proof in proofs})
    return {
        "work_package_ids": identities,
        "proofs": proofs,
        "ambiguous_context": len(identities) > 1,
        "authority": "READ_ONLY_CONTEXT_NOT_SCHEDULE_ASSIGNMENT",
        "quantity_allocation_inferred": False,
        "execution_phase_inferred": False,
    }


def package_dependency_context(dependencies, packages, package_ids):
    """Expose AWP dependencies without interpreting them as Schedule relationships."""
    rows = [
        deepcopy(row) | {"predecessor_status": packages.get(row["predecessor_package_id"], {}).get("status")}
        for row in dependencies
        if row["successor_package_id"] in package_ids
    ]
    return {
        "authority": "FROZEN_AWP_PACKAGE_DEPENDENCY_CONTEXT_NOT_SCHEDULE_LOGIC",
        "items": rows,
        "blocking_ids": sorted(
            row["id"]
            for row in rows
            if row.get("status") == "ACTIVE"
            and row.get("blocking")
            and row.get("predecessor_status") not in {"COMPLETED", "CLOSED"}
        ),
    }


def forecast_phase_points(components, *, as_of, currency):
    """Malformed Draft data produces N/C, never an unhandled preview exception."""
    future, errors = [], []
    cutoff = business_date(as_of)
    for component in components:
        points = component.get("phasing", [])
        try:
            expected = forecast_number(component.get("amount"))
        except (ValueError, DecimalException):
            expected = None
        if not isinstance(points, list):
            errors.append("FORECAST_COST_PHASING_INVALID")
            continue
        if not points and expected != ZERO:
            errors.append("FORECAST_COST_PHASING_REQUIRED")
            continue
        total = ZERO
        for point in points:
            if not isinstance(point, dict):
                errors.append("FORECAST_COST_PHASING_INVALID")
                continue
            try:
                day = business_date(point.get("date"))
                amount = number(point.get("amount"))
                if amount < ZERO:
                    errors.append("FORECAST_COST_PHASING_NEGATIVE_AMOUNT")
                    continue
                amount = forecast_number(amount)
            except (ValueError, DecimalException):
                errors.append("FORECAST_COST_PHASING_NUMERIC_OR_DATE_INVALID")
                continue
            if day is None or cutoff is None or day <= cutoff:
                errors.append("FORECAST_COST_PHASING_AFTER_AS_OF_REQUIRED")
            point_currency = point.get("currency", component.get("currency") or currency)
            if point_currency != currency:
                errors.append("SERIES_UNIT_CURRENCY_MISMATCH")
            total += amount
            future.append(
                {
                    "date": day.isoformat() if day else None,
                    "value": amount,
                    "currency": point_currency,
                    "unit": "MONEY",
                    "source_refs": [{"forecast_component_id": component["id"], "hash": component.get("content_hash")}],
                }
            )
        if expected is None or total != expected:
            errors.append("FORECAST_COST_PHASING_ETC_RECONCILIATION_REQUIRED")
    return ([] if errors else future), sorted(set(errors))


def _status(value):
    return str(value or "").replace(" ", "_").upper()


def _truth(value):
    return value is True or isinstance(value, str) and value.strip().upper() in {"TRUE", "YES", "Y", "1"}


def _driver(activity_id, relationships, activity_index):
    predecessors, drivers = [], []
    for relation in relationships:
        if str(relation.get("successor_external_id")) != str(activity_id):
            continue
        identity = str(relation.get("predecessor_external_id") or "")
        predecessor = activity_index.get(identity, {})
        facts = {
            "predecessor_external_id": identity,
            "predecessor_wbs_external_id": predecessor.get("wbs_external_id"),
            "relationship_type": relation.get("relationship_type"),
            "lag": relation.get("lag"),
            "lag_unit": relation.get("lag_unit"),
            "relationship_external_id": relation.get("external_id"),
            "authority": "IMPORTED_SCHEDULE_RELATIONSHIP",
        }
        predecessors.append(facts)
        raw = relation.get("source_fields") or {}
        # Relationship membership is not proof that it is a driving relation.
        if any(_truth(raw.get(key)) for key in ("IsDriving", "Driving", "driving_flag")):
            drivers.append(facts)
    return {"state": "IMPORTED" if drivers else "UNKNOWN", "drivers": drivers, "predecessors": predecessors}


def lookahead_projection(
    activities,
    wbs,
    relationships,
    *,
    as_of,
    horizon_days=28,
    include_overdue=True,
    exclude_milestones=True,
    group_by="PARENT_WBS",
    top_n=None,
    critical_only=False,
    near_critical_value="40",
    near_critical_unit="HOUR",
    wbs_external_id=None,
    work_package_id=None,
):
    if not 1 <= horizon_days <= 366:
        raise ValueError("LOOKAHEAD_HORIZON_INVALID")
    if group_by not in GROUPS:
        raise ValueError("LOOKAHEAD_GROUP_INVALID")
    if top_n is not None and not 1 <= top_n <= 10000:
        raise ValueError("LOOKAHEAD_TOP_N_INVALID")
    if near_critical_unit not in {"HOUR", "DAY"} or number(near_critical_value) < ZERO:
        raise ValueError("LOOKAHEAD_FLOAT_THRESHOLD_INVALID")
    start = business_date(as_of)
    if start is None:
        raise ValueError("LOOKAHEAD_AS_OF_REQUIRED")
    end = start + timedelta(days=horizon_days)
    by_wbs = {str(row["external_id"]): row for row in wbs}
    by_activity = {str(row["external_id"]): row for row in activities}

    def inside_wbs(identity):
        visited = set()
        while identity and identity not in visited:
            if identity == str(wbs_external_id):
                return True
            visited.add(identity)
            identity = str(by_wbs.get(identity, {}).get("parent_external_id") or "")
        return False

    selected, milestones, excluded = [], [], defaultdict(int)
    for activity in activities:
        row = deepcopy(activity)
        if row.get("actual_finish") or _status(row.get("status")) in {"COMPLETED", "COMPLETE", "TK_COMPLETE"}:
            excluded["COMPLETED"] += 1
            continue
        if wbs_external_id and not inside_wbs(str(row.get("wbs_external_id") or "")):
            excluded["WBS_FILTER"] += 1
            continue
        if work_package_id is not None and work_package_id not in row.get("work_package_ids", []):
            excluded["PACKAGE_FILTER"] += 1
            continue
        row["near_critical"] = near_critical(row, near_critical_value, near_critical_unit)
        row["criticality_authority"] = "P6_IMPORTED" if isinstance(row.get("critical"), bool) else "UNKNOWN"
        if critical_only and row.get("critical") is not True:
            excluded["CRITICAL_FILTER"] += 1
            continue
        planned = business_date(row.get("planned_start") or row.get("start"))
        finish = business_date(row.get("finish") or row.get("planned_finish"))
        active = bool(row.get("actual_start")) or _status(row.get("status")) in {"IN_PROGRESS", "TK_ACTIVE"}
        overdue = (
            planned is not None and planned < start and not active or active and finish is not None and finish < start
        )
        blocked = bool(row.get("blocking_constraint_ids") or row.get("blocking_dependency_ids"))
        in_window = planned is not None and start <= planned <= end
        active_in_window = active and (planned is None or planned <= end) and (finish is None or finish >= start)
        keep_overdue = include_overdue and overdue
        unknown_blocked = include_overdue and blocked and planned is None
        if not (in_window or active_in_window or keep_overdue or unknown_blocked):
            excluded["OUTSIDE_HORIZON_OR_UNKNOWN_DATE"] += 1
            continue
        row["overdue"] = bool(overdue)
        row["selection_reason"] = (
            "BLOCKED_WITH_UNKNOWN_DATES"
            if unknown_blocked
            else "OVERDUE"
            if keep_overdue
            else "IN_PROGRESS"
            if active
            else "WITHIN_HORIZON"
        )
        row["driving_predecessor"] = _driver(row["external_id"], relationships, by_activity)
        current_wbs = by_wbs.get(str(row.get("wbs_external_id")), {})
        row["parent_wbs_external_id"] = current_wbs.get("parent_external_id") or row.get("wbs_external_id")
        if exclude_milestones and "MILESTONE" in _status(row.get("activity_type")):
            milestones.append(row)
        else:
            selected.append(row)
    selected.sort(
        key=lambda row: (
            not bool(row.get("blocking_constraint_ids") or row.get("blocking_dependency_ids")),
            row.get("critical") is not True,
            not row["overdue"],
            row.get("planned_start") or row.get("start") or "9999",
            str(row["external_id"]),
        )
    )
    total = len(selected)
    limited = selected[:top_n] if top_n is not None else selected
    grouped = defaultdict(list)
    for row in limited:
        if group_by == "PARENT_WBS":
            keys = [row.get("parent_wbs_external_id") or "UNASSIGNED"]
        elif group_by == "PACKAGE":
            keys = row.get("work_package_ids") or ["UNASSIGNED"]
        elif group_by == "CWA":
            keys = row.get("cwa_ids") or ["UNASSIGNED"]
        else:
            keys = row.get(group_by.lower() + "s") or [row.get(group_by.lower()) or "UNASSIGNED"]
        for key in sorted(set(map(str, keys))):
            grouped[key].append(str(row["external_id"]))
    return {
        "status": "COMPUTABLE",
        "reason_codes": [],
        "as_of": start.isoformat(),
        "horizon_days": horizon_days,
        "horizon_end": end.isoformat(),
        "items": limited,
        "milestones": milestones,
        "total_before_limit": total,
        "truncated": len(limited) < total,
        "excluded_counts": dict(excluded),
        "group_by": group_by,
        "groups": [
            {"key": key, "activity_ids": ids, "activity_count": len(ids)} for key, ids in sorted(grouped.items())
        ],
        "authority": {
            "schedule": "ACCEPTED_IMPORTED_SCHEDULE",
            "cpm_calculation_performed": False,
            "schedule_mutated": False,
            "driver_inference_performed": False,
        },
    }


def cumulative_series(points, *, code, unit, currency=None, basis, source_refs=None):
    """One additive series must keep one unit/currency and one source basis."""
    errors, by_day = [], defaultdict(lambda: ZERO)
    references = defaultdict(list)
    for point in points:
        if point.get("unit", unit) != unit or point.get("currency", currency) != currency:
            errors.append("SERIES_UNIT_CURRENCY_MISMATCH")
            continue
        day = business_date(point.get("date"))
        if day is None:
            errors.append("SERIES_DATE_REQUIRED")
            continue
        try:
            amount = number(point.get("value", point.get("period_value")))
        except ValueError:
            errors.append("SERIES_NUMERIC_BASIS_REQUIRED")
            continue
        by_day[day.isoformat()] += amount
        references[day.isoformat()].extend(point.get("source_refs", []))
    running, result = ZERO, []
    if not errors:
        for day, amount in sorted(by_day.items()):
            running += amount
            result.append(
                {
                    "date": day,
                    "period_value": scalar(amount),
                    "cumulative_value": scalar(running),
                    "source_refs": references[day],
                }
            )
    return {
        "code": code,
        "unit": unit,
        "currency": currency,
        "basis": basis,
        "status": "NOT_COMPUTABLE" if errors or not points else "COMPUTABLE",
        "reason_codes": sorted(set(errors or ([] if points else ["SERIES_SOURCE_REQUIRED"]))),
        "source_refs": source_refs or {},
        "points": result,
    }


def snapshot_series(points, *, code, unit, currency=None, basis, source_refs=None):
    """Snapshot percentages and balances are never added across periods."""
    errors, result = [], []
    seen = set()
    for point in sorted(points, key=lambda row: str(row.get("date"))):
        day = business_date(point.get("date"))
        if day is None or day in seen:
            errors.append("SERIES_DATE_MISSING_OR_AMBIGUOUS")
            continue
        seen.add(day)
        if point.get("unit", unit) != unit or point.get("currency", currency) != currency:
            errors.append("SERIES_UNIT_CURRENCY_MISMATCH")
            continue
        if point.get("value") is None:
            errors.append("SERIES_NUMERIC_BASIS_REQUIRED")
            continue
        result.append(
            {
                "date": day.isoformat(),
                "period_value": None,
                "cumulative_value": scalar(point["value"]),
                "source_refs": point.get("source_refs", []),
            }
        )
    return {
        "code": code,
        "unit": unit,
        "currency": currency,
        "basis": basis,
        "status": "NOT_COMPUTABLE" if errors or not points else "COMPUTABLE",
        "reason_codes": sorted(set(errors or ([] if points else ["SERIES_SOURCE_REQUIRED"]))),
        "source_refs": source_refs or {},
        "points": [] if errors else result,
    }


def latest_report_revisions(rows, period_families=None):
    """One latest published report per period family, without erasing its history."""
    period_families = period_families or {}
    latest = {}
    for row in rows:
        if row.get("status") != "PUBLISHED":
            continue
        period = row["period_id"]
        family = period_families.get(period, period)
        order = (row.get("period_revision", 1), row.get("revision", 1), row.get("id", 0))
        if family not in latest or order > latest[family][0]:
            latest[family] = (order, row)
    return sorted((deepcopy(value[1]) for value in latest.values()), key=lambda row: (row["as_of"], row["period_id"]))


def trend_series(rows, metrics):
    """Expose immutable points without drawing comparable series across control bases."""
    units = {
        "forecast_finish": "DATE",
        "eac": "MONEY",
        "etc": "MONEY",
        "vac": "MONEY",
        "physical_progress": "%",
        "spi": "RATIO",
        "cpi": "RATIO",
        "readiness": "%",
        "open_constraints": "COUNT",
    }
    result = []
    for name in metrics:
        unit = units[name]
        points = [
            {
                "date": row["as_of"],
                "value": row["metrics"].get(name),
                "unit": unit,
                "currency": row.get("currency") if unit == "MONEY" else None,
                "period_id": row["period_id"],
                "report_id": row["id"],
                "source_hash": row["content_hash"],
                "basis": {
                    "bundle_id": row.get("source_refs", {}).get("bundle", {}).get("id"),
                    "bundle_hash": row.get("source_refs", {}).get("bundle", {}).get("hash"),
                    "cost_baseline_id": row.get("source_refs", {}).get("cost_period_snapshot", {}).get("baseline_id"),
                    "forecast_version_id": row.get("forecast_version_id"),
                },
            }
            for row in rows
        ]
        currencies = {point["currency"] for point in points} if unit == "MONEY" else set()
        bases = {(p["basis"]["bundle_id"], p["basis"]["bundle_hash"]) for p in points}
        reasons = []
        if not points:
            reasons.append("PUBLISHED_PERIOD_REPORT_REQUIRED")
        if unit == "MONEY" and (None in currencies or len(currencies) > 1):
            reasons.append("TREND_CURRENCY_MISMATCH_OR_REQUIRED")
        if len(bases) > 1 and name not in {"readiness", "open_constraints"}:
            reasons.append("TREND_CONTROL_BASIS_CHANGED")
        if any(point["value"] is None for point in points):
            reasons.append("TREND_SOURCE_METRIC_NOT_COMPUTABLE")
        result.append(
            {
                "metric": name,
                "unit": unit,
                "currency": next(iter(currencies)) if len(currencies) == 1 else None,
                "status": "NOT_COMPUTABLE" if reasons else "COMPUTABLE",
                "reason_codes": reasons,
                "basis": "IMMUTABLE_REPORT_POINTS_EXPLICIT_CONTROL_BASIS_NOT_PERIOD_SUM",
                "points": [] if reasons else points,
                "not_computable_points": points if reasons else [],
            }
        )
    return result


def narrative_sections(metrics, source_refs, sections=None):
    """Factual, deterministic statements with internal source-fact locators."""
    sections = sections or NARRATIVE_SECTIONS
    facts = {
        "forecast": source_refs.get("forecast"),
        "evm": source_refs.get("evm_snapshot"),
        "schedule": source_refs.get("schedule"),
        "progress": source_refs.get("progress_snapshot"),
        "cost": source_refs.get("cost_period_snapshot"),
        "awp": source_refs.get("readiness"),
    }
    text = {
        "EXECUTIVE_SUMMARY": f"Forecast finish {metrics.get('forecast_finish')}; EAC {metrics.get('eac')}; VAC {metrics.get('vac')}.",
        "SCHEDULE": f"Baseline finish {metrics.get('baseline_finish')}; current finish {metrics.get('current_finish')}; forecast finish {metrics.get('forecast_finish')}.",
        "CRITICAL_NEAR_CRITICAL": f"Imported critical activities {metrics.get('critical_count')}; compatible near-critical activities {metrics.get('near_critical_count')}.",
        "COST": f"Recognized actual {metrics.get('actual')}; ETC {metrics.get('etc')}; EAC {metrics.get('eac')}; currency {metrics.get('currency')}.",
        "PROGRESS": f"Approved physical progress {metrics.get('physical_progress')}; quantity progress {metrics.get('quantity_progress')}. These remain distinct from Schedule and Cost.",
        "FORECAST": f"Forecast projection {metrics.get('forecast_finish')}; forecast ETC {metrics.get('etc')}; no source baseline is overwritten.",
        "CONSTRAINTS_READINESS": f"Open constraints {metrics.get('open_constraints')}; readiness {metrics.get('readiness')}.",
        "MITIGATION_ACTIONS": "No mitigation effectiveness or action completion is asserted without an approved source fact.",
    }
    refs = {
        "EXECUTIVE_SUMMARY": ["forecast", "cost"],
        "SCHEDULE": ["schedule", "forecast"],
        "CRITICAL_NEAR_CRITICAL": ["schedule"],
        "COST": ["cost", "forecast"],
        "PROGRESS": ["progress"],
        "FORECAST": ["forecast"],
        "CONSTRAINTS_READINESS": ["awp"],
        "MITIGATION_ACTIONS": ["forecast"],
    }
    return [
        {
            "section": section,
            "text": text[section],
            "fact_references": [name for name in refs[section] if facts.get(name) is not None],
        }
        for section in sections
        if section in text
    ]
