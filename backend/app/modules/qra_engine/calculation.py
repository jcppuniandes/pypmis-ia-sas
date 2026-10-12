"""Pure, versioned QRA mathematics; no database, source writes, or implicit policies.

Gaussian copula coefficients describe latent Gaussian Pearson correlation, not
calibrated marginal correlation. PERT v1 uses alpha=1+lambda*(mode-min)/width
and beta=1+lambda*(max-mode)/width. Schedule v1 is an explicitly approved
elapsed-time generalized-precedence DAG, not a work-calendar/P6 CPM engine.
Memory is O(inputs*chunk + iterations*(1 + selected milestones)); individual
input-by-iteration samples are never retained or returned.
"""

from __future__ import annotations

import heapq
import math
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import numpy as np
import scipy
from scipy.special import betaincinv, ndtr, ndtri
from scipy.stats import truncnorm

ENGINE_VERSION = "wave4-qra-v1"
FORMULA_VERSION = "distribution-inverse-cdf-v1"
NETWORK_VERSION = "normalized-generalized-precedence-dag-v1"
PERCENTILE_VERSION = "numpy-linear-hyndman-fan-7-v1"
SENSITIVITY_VERSION = "streaming-centered-pearson-v1"
SUPPORTED_FAMILIES = {"TRIANGULAR", "PERT", "BETA_PERT", "UNIFORM", "NORMAL", "LOGNORMAL", "DISCRETE"}
SUPPORTED_ANALYSES = {"COST_QRA", "SCHEDULE_QRA"}
SUPPORTED_COST_BASES = {"BASE_COST", "COST_WITH_ESTIMATE_ALLOWANCE", "COST_WITH_CONTINGENCY", "OTHER_CONFIGURED_BASIS"}


class EngineCalculationError(ValueError):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class EngineCancelled(EngineCalculationError):
    def __init__(self):
        super().__init__("QRA_RUN_CANCELLED")


def engine_manifest() -> dict:
    return {
        "engine_name": "PPMIS_GOVERNED_QRA",
        "engine_version": ENGINE_VERSION,
        "formula_version": FORMULA_VERSION,
        "network_version": NETWORK_VERSION,
        "percentile_method": PERCENTILE_VERSION,
        "sensitivity_method": SENSITIVITY_VERSION,
        "prng_algorithm": "PCG64",
        "prng_version": "numpy-pcg-xsl-rr-128-64-v1",
        "numpy_version": np.__version__,
        "scipy_version": scipy.__version__,
        "sampling_numeric_type": "float64",
        "aggregation_numeric_type": "float64-centered-batch",
        "raw_samples_retained": False,
        "currency_rounding": "NONE_IN_ENGINE_PRESENTATION_ONLY",
        "date_semantics": "NORMALIZED_ELAPSED_UTC_NOT_WORK_CALENDAR_DATES",
    }


def _number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _integer(value, minimum, maximum) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and minimum <= value <= maximum


def _ref(item) -> str:
    return f"{item.get('source_kind')}:{item.get('source_item_ref')}"


def _date(value) -> datetime:
    if not isinstance(value, str):
        raise EngineCalculationError("SCHEDULE_DATE_ANCHOR_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EngineCalculationError("SCHEDULE_DATE_ANCHOR_INVALID") from exc
    # Date-only source data dates are midnight UTC under the approved v1 method.
    if parsed.tzinfo is None:
        if len(value) != 10:
            raise EngineCalculationError("SCHEDULE_DATE_TIMEZONE_REQUIRED")
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _bounds(item) -> tuple[float, float, float]:
    values = item.get("values", {})
    representation = item.get("range_type")
    if representation == "PERCENT_MINUS_PLUS":
        if not all(_number(values.get(k)) for k in ("base", "minus", "plus")):
            raise EngineCalculationError("DISTRIBUTION_PARAMETERS_INVALID")
        if values["minus"] < 0 or values["plus"] < 0:
            raise EngineCalculationError("DISTRIBUTION_PARAMETERS_INVALID")
        base = float(values["base"])
        return base * (1 - values["minus"] / 100), base, base * (1 + values["plus"] / 100)
    lo, hi = values.get("min"), values.get("max")
    mode = values.get("base", values.get("mode", values.get("most_likely")))
    if not _number(lo) or not _number(hi):
        raise EngineCalculationError("DISTRIBUTION_PARAMETERS_INVALID")
    if item.get("distribution_family") in {"TRIANGULAR", "PERT", "BETA_PERT"} and not _number(mode):
        raise EngineCalculationError("DISTRIBUTION_PARAMETERS_INVALID")
    return float(lo), float(mode if _number(mode) else lo), float(hi)


def _distribution_issues(item, policy) -> list[str]:
    issues = []
    family = item.get("distribution_family")
    if family not in SUPPORTED_FAMILIES:
        return ["ENGINE_METHOD_NOT_SUPPORTED"]
    params = item.get("parameters", {})
    values = item.get("values", {})
    if not isinstance(params, dict) or not isinstance(values, dict):
        return ["DISTRIBUTION_PARAMETERS_INVALID"]
    signed = item.get("allow_negative") is True
    if item.get("source_kind") == "SCHEDULE" and signed:
        issues.append("SCHEDULE_NEGATIVE_DURATION_NOT_ALLOWED")
    if family in {"TRIANGULAR", "PERT", "BETA_PERT", "UNIFORM"}:
        try:
            lo, mode, hi = _bounds(item)
        except EngineCalculationError as exc:
            return [exc.code]
        if lo > hi or family != "UNIFORM" and not lo <= mode <= hi:
            issues.append("DISTRIBUTION_PARAMETERS_INVALID")
        if not signed and lo < 0:
            issues.append("DISTRIBUTION_NEGATIVE_NOT_ALLOWED")
        if family in {"PERT", "BETA_PERT"} and (not _number(params.get("lambda")) or params["lambda"] <= 0):
            issues.append("PERT_LAMBDA_REQUIRED")
    elif family == "NORMAL":
        if not _number(params.get("mean")) or not _number(params.get("stddev")) or params["stddev"] <= 0:
            issues.append("DISTRIBUTION_PARAMETERS_INVALID")
        if not signed and policy.get("normal_negative_policy") != "TRUNCATE_AT_ZERO":
            issues.append("NORMAL_NEGATIVE_SUPPORT_NOT_ALLOWED")
    elif family == "LOGNORMAL":
        if not _number(params.get("mu")) or not _number(params.get("sigma")) or params["sigma"] <= 0:
            issues.append("DISTRIBUTION_PARAMETERS_INVALID")
        # mu and sigma are log-space parameters; there is no implicit conversion.
    elif family == "DISCRETE":
        scenarios = values.get("scenarios")
        tolerance = policy.get("probability_tolerance", 1e-9)
        if not isinstance(scenarios, list) or not scenarios or len(scenarios) > 1000:
            return ["DISCRETE_PARAMETERS_INVALID"]
        if any(
            not isinstance(s, dict)
            or not _number(s.get("value"))
            or not _number(s.get("probability"))
            or not 0 <= s["probability"] <= 1
            for s in scenarios
        ):
            return ["DISCRETE_PARAMETERS_INVALID"]
        if abs(math.fsum(s["probability"] for s in scenarios) - 1) > tolerance:
            issues.append("DISCRETE_PROBABILITY_SUM_INVALID")
        if not signed and any(s["value"] < 0 for s in scenarios):
            issues.append("DISTRIBUTION_NEGATIVE_NOT_ALLOWED")
    return issues


def _policy_issues(policy, analysis_type) -> list[str]:
    if not isinstance(policy, dict) or not policy:
        return ["ENGINE_CONFIGURATION_NOT_READY"]
    issues = []
    if policy.get("engine_version") != ENGINE_VERSION:
        issues.append("ENGINE_VERSION_NOT_SUPPORTED")
    if analysis_type not in policy.get("supported_analysis_types", []):
        issues.append("ENGINE_METHOD_NOT_SUPPORTED")
    percentiles = policy.get("percentiles")
    if (
        not isinstance(percentiles, list)
        or not percentiles
        or len(percentiles) > 25
        or any(not _number(p) or not 0 <= p <= 100 for p in percentiles)
        or len(set(percentiles)) != len(percentiles)
    ):
        issues.append("ENGINE_PERCENTILE_POLICY_INVALID")
    for key, minimum, maximum in (
        ("chunk_size", 16, 1024),
        ("histogram_bins", 1, 100),
        ("max_correlation_dimension", 2, 1000),
    ):
        if not _integer(policy.get(key), minimum, maximum):
            issues.append("ENGINE_CONFIGURATION_INVALID")
    for key, maximum in (("probability_tolerance", 1e-6), ("psd_tolerance", 1e-8)):
        value = policy.get(key, 1e-9 if key == "probability_tolerance" else 1e-10)
        if not _number(value) or not 0 < value <= maximum:
            issues.append("ENGINE_CONFIGURATION_INVALID")
    convergence = policy.get("convergence")
    if not isinstance(convergence, dict) or not isinstance(convergence.get("enabled"), bool):
        issues.append("ENGINE_CONVERGENCE_POLICY_INVALID")
    elif convergence["enabled"] and (
        not _integer(convergence.get("min_iterations"), 2, 1000000)
        or not _number(convergence.get("relative_mean_standard_error_tolerance"))
        or not 0 < convergence["relative_mean_standard_error_tolerance"] <= 1
    ):
        issues.append("ENGINE_CONVERGENCE_POLICY_INVALID")
    indicator = policy.get("analytical_indicator_percentile")
    if indicator is not None and (
        not _number(indicator) or not isinstance(percentiles, list) or indicator not in percentiles
    ):
        issues.append("ENGINE_ANALYTICAL_INDICATOR_POLICY_INVALID")
    if policy.get("retain_raw_samples", False):
        issues.append("ENGINE_METHOD_NOT_SUPPORTED")
    return sorted(set(issues))


def _correlation_blocks(correlations, refs, policy) -> tuple[list[tuple[np.ndarray, np.ndarray]], dict]:
    """Validate sparse connected components, never create a full independent matrix."""
    if not isinstance(correlations, dict):
        raise EngineCalculationError("CORRELATION_DEFINITION_INVALID")
    method = correlations.get("method")
    if method == "NO_CORRELATION":
        if any(correlations.get(k) for k in ("pairs", "groups", "matrix")):
            raise EngineCalculationError("NO_CORRELATION_HAS_ENTRIES")
        return [], {"method": "NO_CORRELATION", "blocks": [], "no_psd_repair": True}
    if method not in {"MATRIX_CORRELATION", "PAIRWISE_CORRELATION", "GROUP_CORRELATION"}:
        raise EngineCalculationError("ENGINE_METHOD_NOT_SUPPORTED")
    allowed_content = {"MATRIX_CORRELATION": "matrix", "PAIRWISE_CORRELATION": "pairs", "GROUP_CORRELATION": "groups"}[
        method
    ]
    if any(correlations.get(key) for key in {"matrix", "pairs", "groups"} - {allowed_content}):
        raise EngineCalculationError("CORRELATION_METHOD_CONTENT_MISMATCH")
    if policy.get("correlation_sampling") != "GAUSSIAN_COPULA_V1":
        raise EngineCalculationError("ENGINE_METHOD_NOT_SUPPORTED")
    positions = {ref: index for index, ref in enumerate(refs)}
    edges: dict[tuple[int, int], float] = {}
    adjacency: dict[int, set[int]] = {}

    def add(left, right, coefficient):
        if left not in positions or right not in positions or left == right:
            raise EngineCalculationError("CORRELATION_REFERENCE_INVALID")
        if not _number(coefficient) or not -1 <= coefficient <= 1:
            raise EngineCalculationError("CORRELATION_COEFFICIENT_INVALID")
        i, j = sorted((positions[left], positions[right]))
        if (i, j) in edges:
            raise EngineCalculationError("CORRELATION_DUPLICATE_PAIR")
        edges[i, j] = float(coefficient)
        if coefficient != 0:
            adjacency.setdefault(i, set()).add(j)
            adjacency.setdefault(j, set()).add(i)

    if method == "MATRIX_CORRELATION":
        matrix_refs, matrix = correlations.get("refs"), correlations.get("matrix")
        if (
            not isinstance(matrix_refs, list)
            or not matrix_refs
            or any(not isinstance(ref, str) or not ref for ref in matrix_refs)
            or len(set(matrix_refs)) != len(matrix_refs)
            or any(r not in positions for r in matrix_refs)
            or not isinstance(matrix, list)
            or len(matrix) != len(matrix_refs)
            or any(not isinstance(row, list) or len(row) != len(matrix_refs) for row in matrix)
        ):
            raise EngineCalculationError("CORRELATION_MATRIX_DIMENSION_INVALID")
        if len(matrix_refs) > policy["max_correlation_dimension"]:
            raise EngineCalculationError("CORRELATION_BLOCK_LIMIT_EXCEEDED")
        for i, row in enumerate(matrix):
            for j, coefficient in enumerate(row):
                if not _number(coefficient) or not -1 <= coefficient <= 1:
                    raise EngineCalculationError("CORRELATION_COEFFICIENT_INVALID")
                if i == j and coefficient != 1:
                    raise EngineCalculationError("CORRELATION_DIAGONAL_INVALID")
                if coefficient != matrix[j][i]:
                    raise EngineCalculationError("CORRELATION_MATRIX_ASYMMETRIC")
                if i < j:
                    add(matrix_refs[i], matrix_refs[j], coefficient)
    elif method == "PAIRWISE_CORRELATION":
        pairs = correlations.get("pairs", [])
        if not isinstance(pairs, list) or len(pairs) > 20000:
            raise EngineCalculationError("CORRELATION_DEFINITION_INVALID")
        for pair in pairs:
            if not isinstance(pair, dict):
                raise EngineCalculationError("CORRELATION_DEFINITION_INVALID")
            add(pair.get("left"), pair.get("right"), pair.get("coefficient"))
    else:
        groups = correlations.get("groups", [])
        if not isinstance(groups, list) or len(groups) > 1000:
            raise EngineCalculationError("CORRELATION_DEFINITION_INVALID")
        seen = set()
        for group in groups:
            members = group.get("members") if isinstance(group, dict) else None
            if (
                not isinstance(members, list)
                or len(members) < 2
                or len(set(members)) != len(members)
                or seen.intersection(members)
            ):
                raise EngineCalculationError("CORRELATION_GROUP_INVALID")
            if len(members) > policy["max_correlation_dimension"]:
                raise EngineCalculationError("CORRELATION_BLOCK_LIMIT_EXCEEDED")
            seen.update(members)
            for i, left in enumerate(members):
                for right in members[i + 1 :]:
                    add(left, right, group.get("coefficient"))
    blocks, diagnostics, remaining = [], [], set(adjacency)
    while remaining:
        todo, component = [min(remaining)], set()
        while todo:
            i = todo.pop()
            if i not in component:
                component.add(i)
                todo.extend(adjacency.get(i, set()) - component)
        remaining -= component
        indices = sorted(component)
        if len(indices) > policy["max_correlation_dimension"]:
            raise EngineCalculationError("CORRELATION_BLOCK_LIMIT_EXCEEDED")
        matrix = np.eye(len(indices), dtype=np.float64)
        local = {index: position for position, index in enumerate(indices)}
        for (i, j), coefficient in edges.items():
            if i in local and j in local:
                matrix[local[i], local[j]] = matrix[local[j], local[i]] = coefficient
        eigenvalues, eigenvectors = np.linalg.eigh(matrix)
        tolerance = policy.get("psd_tolerance", 1e-10)
        if float(eigenvalues[0]) < -tolerance:
            raise EngineCalculationError("CORRELATION_MATRIX_NOT_PSD")
        # Only floating-point roundoff inside the approved numeric PSD tolerance
        # is zeroed for a real square root; the input matrix is never replaced.
        roundoff_count = int(np.count_nonzero(eigenvalues < 0))
        factor = eigenvectors * np.sqrt(np.maximum(eigenvalues, 0))[None, :]
        blocks.append((np.asarray(indices, dtype=np.int64), factor))
        diagnostics.append(
            {
                "input_refs": [refs[i] for i in indices],
                "dimension": len(indices),
                "minimum_eigenvalue": float(eigenvalues[0]),
                "numeric_psd_tolerance": tolerance,
                "roundoff_eigenvalues_zeroed": roundoff_count,
            }
        )
    return blocks, {
        "method": "GAUSSIAN_COPULA_V1",
        "definition_method": method,
        "coefficient_semantics": "LATENT_GAUSSIAN_PEARSON_NOT_MARGINAL_CALIBRATION",
        "blocks": diagnostics,
        "no_psd_repair": True,
    }


def _network(snapshot, inputs):
    schedule, policy = snapshot.get("schedule", {}), snapshot["policy"]
    if policy.get("schedule_method") != "NORMALIZED_ELAPSED_TIME_V1":
        raise EngineCalculationError("ENGINE_METHOD_NOT_SUPPORTED")
    unit = schedule.get("unit")
    if unit not in {"HOURS", "DAYS"} or schedule.get("unit_seconds") != {"HOURS": 3600, "DAYS": 86400}[unit]:
        raise EngineCalculationError("SCHEDULE_UNIT_NORMALIZATION_NOT_APPROVED")
    _date(schedule.get("date_anchor"))
    if schedule.get("target_date") is not None:
        _date(schedule["target_date"])
    activities, relationships = schedule.get("activities"), schedule.get("relationships")
    if not isinstance(activities, list) or not isinstance(relationships, list) or len(relationships) > 100000:
        raise EngineCalculationError("SCHEDULE_NETWORK_INVALID")
    refs = [item["source_item_ref"] for item in inputs]
    positions = {ref: index for index, ref in enumerate(refs)}
    if len(activities) != len(inputs) or {a.get("ref") for a in activities} != set(refs):
        raise EngineCalculationError("SCHEDULE_NETWORK_POPULATION_MISMATCH")
    calendars = schedule.get("calendars")
    if not isinstance(calendars, list) or not calendars:
        raise EngineCalculationError("SCHEDULE_CALENDAR_NOT_AVAILABLE")
    calendar_refs = {str(c.get("source_id")) for c in calendars if isinstance(c, dict)}
    base_durations = {item["source_item_ref"]: item["base_value"] for item in inputs}
    if any(i.get("unit") != unit for i in inputs):
        raise EngineCalculationError("SCHEDULE_UNIT_NORMALIZATION_NOT_APPROVED")
    for activity in activities:
        if activity.get("duration_unit") != unit:
            raise EngineCalculationError("SCHEDULE_UNIT_NORMALIZATION_NOT_APPROVED")
        if str(activity.get("calendar_ref")) not in calendar_refs:
            raise EngineCalculationError("SCHEDULE_CALENDAR_NOT_AVAILABLE")
        if any(
            str(activity.get(key) or "").strip().upper() not in {"", "NONE", "CS_NONE"}
            for key in ("primary_constraint_type", "secondary_constraint_type")
        ):
            raise EngineCalculationError("SCHEDULE_CONSTRAINT_NOT_SUPPORTED")
        if activity.get("actual_start") or activity.get("actual_finish"):
            raise EngineCalculationError("SCHEDULE_ACTUAL_PROGRESS_NOT_SUPPORTED")
        status = str(activity.get("status") or "").strip().upper().replace(" ", "").replace("_", "").replace("-", "")
        if not status:
            raise EngineCalculationError("SCHEDULE_ACTIVITY_STATUS_REQUIRED")
        if status not in {"NOTSTARTED", "TKNOTSTART"}:
            raise EngineCalculationError("SCHEDULE_STARTED_ACTIVITY_NOT_SUPPORTED")
        remaining = activity.get("remaining_duration")
        if remaining is not None:
            try:
                value = float(remaining)
            except (TypeError, ValueError) as exc:
                raise EngineCalculationError("SCHEDULE_REMAINING_DURATION_INVALID") from exc
            if isinstance(remaining, bool) or not math.isfinite(value) or value < 0:
                raise EngineCalculationError("SCHEDULE_REMAINING_DURATION_INVALID")
            if not math.isclose(value, base_durations[activity["ref"]], rel_tol=1e-12, abs_tol=1e-12):
                raise EngineCalculationError("SCHEDULE_REMAINING_DURATION_MODEL_NOT_SUPPORTED")
    incoming = [[] for _ in inputs]
    outgoing = [[] for _ in inputs]
    indegrees = [0] * len(inputs)
    seen = set()
    for relationship in relationships:
        if not isinstance(relationship, dict):
            raise EngineCalculationError("SCHEDULE_NETWORK_INVALID")
        predecessor, successor = relationship.get("predecessor"), relationship.get("successor")
        kind, lag = relationship.get("type"), relationship.get("lag")
        if kind not in {"FS", "SS", "FF", "SF"}:
            raise EngineCalculationError("UNSUPPORTED_RELATIONSHIP_FOR_QRA_ENGINE")
        if predecessor not in positions or successor not in positions or predecessor == successor:
            raise EngineCalculationError("SCHEDULE_RELATIONSHIP_REFERENCE_INVALID")
        if not _number(lag) or relationship.get("lag_unit") != unit:
            raise EngineCalculationError("SCHEDULE_LAG_UNIT_NOT_APPROVED")
        edge = (predecessor, successor, kind)
        if edge in seen:
            raise EngineCalculationError("SCHEDULE_RELATIONSHIP_DUPLICATE")
        seen.add(edge)
        i, j = positions[predecessor], positions[successor]
        incoming[j].append((i, kind, float(lag)))
        outgoing[i].append(j)
        indegrees[j] += 1
    ready = [i for i, degree in enumerate(indegrees) if degree == 0]
    heapq.heapify(ready)
    order = []
    while ready:
        i = heapq.heappop(ready)
        order.append(i)
        for j in outgoing[i]:
            indegrees[j] -= 1
            if indegrees[j] == 0:
                heapq.heappush(ready, j)
    if len(order) != len(inputs):
        raise EngineCalculationError("SCHEDULE_NETWORK_CYCLE")
    milestones = schedule.get("milestone_refs", [])
    if (
        not isinstance(milestones, list)
        or len(milestones) > 25
        or len(set(milestones)) != len(milestones)
        or any(ref not in positions for ref in milestones)
    ):
        raise EngineCalculationError("SCHEDULE_MILESTONE_SELECTION_INVALID")
    for edges in incoming:
        edges.sort(key=lambda edge: (edge[0], edge[1], edge[2]))
    return incoming, order, [(ref, positions[ref]) for ref in sorted(milestones)]


def validate_snapshot(snapshot: dict) -> list[str]:
    if not isinstance(snapshot, dict):
        return ["ENGINE_SNAPSHOT_INVALID"]
    analysis_type, policy = snapshot.get("analysis_type"), snapshot.get("policy")
    issues = _policy_issues(policy, analysis_type)
    if analysis_type not in SUPPORTED_ANALYSES:
        issues.append("ENGINE_METHOD_NOT_SUPPORTED")
    if issues:
        return sorted(set(issues))
    inputs = snapshot.get("inputs")
    if (
        not isinstance(inputs, list)
        or not inputs
        or len(inputs) > 20000
        or any(not isinstance(i, dict) for i in inputs)
    ):
        return ["ENGINE_INPUT_POPULATION_INVALID"]
    refs = [_ref(item) for item in inputs]
    if len(set(refs)) != len(refs):
        issues.append("ENGINE_INPUT_REFERENCE_DUPLICATE")
    expected_kind = "COST" if analysis_type == "COST_QRA" else "SCHEDULE"
    for item in inputs:
        if item.get("source_kind") != expected_kind or not isinstance(item.get("source_item_ref"), str):
            issues.append("ENGINE_INPUT_SCOPE_INVALID")
        if (
            item.get("input_type")
            != {"COST": "ESTIMATE_UNCERTAINTY", "SCHEDULE": "DURATION_UNCERTAINTY"}[expected_kind]
        ):
            issues.append("ENGINE_METHOD_NOT_SUPPORTED")
        if not _number(item.get("base_value")) or not isinstance(item.get("allow_negative"), bool):
            issues.append("ENGINE_INPUT_BASE_INVALID")
        elif not item["allow_negative"] and item["base_value"] < 0:
            issues.append("DISTRIBUTION_NEGATIVE_NOT_ALLOWED")
        if expected_kind == "SCHEDULE" and item.get("allow_negative") is True:
            issues.append("SCHEDULE_NEGATIVE_DURATION_NOT_ALLOWED")
        if not isinstance(item.get("risk_refs", []), list):
            issues.append("ENGINE_RISK_LINKAGE_INVALID")
        if item.get("mode") == "UNCERTAIN":
            issues.extend(_distribution_issues(item, policy))
        elif item.get("mode") != "DETERMINISTIC":
            issues.append("ENGINE_INPUT_MODE_INVALID")
    if analysis_type == "COST_QRA":
        cost = snapshot.get("cost", {})
        if not isinstance(cost, dict) or cost.get("basis") not in SUPPORTED_COST_BASES:
            issues.append("COST_BASIS_NOT_EXPLICIT")
        else:
            currency = cost.get("currency")
            if not isinstance(currency, str) or not currency or any(i.get("unit") != currency for i in inputs):
                issues.append("COST_CURRENCY_OR_UNIT_MISMATCH")
            if not _number(cost.get("deterministic_reference")):
                issues.append("COST_DETERMINISTIC_REFERENCE_INVALID")
            if cost.get("target_amount") is not None and not _number(cost["target_amount"]):
                issues.append("COST_TARGET_INVALID")
    if not issues:
        try:
            _correlation_blocks(
                snapshot.get("correlations", {}),
                [r for r, i in zip(refs, inputs, strict=True) if i["mode"] == "UNCERTAIN"],
                policy,
            )
            if analysis_type == "SCHEDULE_QRA":
                _network(snapshot, sorted(inputs, key=_ref))
        except EngineCalculationError as exc:
            issues.append(exc.code)
    return sorted(set(issues))


def _sample(uniforms: np.ndarray, items: list[dict], policy: dict) -> np.ndarray:
    output = np.empty_like(uniforms)
    grouped: dict[str, list[int]] = {}
    for index, item in enumerate(items):
        grouped.setdefault(item["distribution_family"], []).append(index)
    for family, indices in grouped.items():
        u = uniforms[indices]
        definitions = [items[i] for i in indices]
        if family in {"TRIANGULAR", "PERT", "BETA_PERT", "UNIFORM"}:
            triples = np.asarray([_bounds(item) for item in definitions], dtype=np.float64)
            lo, mode, hi = (triples[:, i, None] for i in range(3))
            width = hi - lo
            if family == "UNIFORM":
                values = lo + width * u
            elif family == "TRIANGULAR":
                safe_width = np.where(width == 0, 1, width)
                threshold = (mode - lo) / safe_width
                values = np.where(
                    u <= threshold, lo + np.sqrt(u * width * (mode - lo)), hi - np.sqrt((1 - u) * width * (hi - mode))
                )
            else:
                lam = np.asarray([item["parameters"]["lambda"] for item in definitions])[:, None]
                safe_width = np.where(width == 0, 1, width)
                alpha, beta = 1 + lam * (mode - lo) / safe_width, 1 + lam * (hi - mode) / safe_width
                values = lo + width * betaincinv(alpha, beta, u)
            output[indices] = values
        elif family == "NORMAL":
            mean = np.asarray([item["parameters"]["mean"] for item in definitions])[:, None]
            stddev = np.asarray([item["parameters"]["stddev"] for item in definitions])[:, None]
            values = mean + stddev * ndtri(u)
            unsigned = np.asarray([not item["allow_negative"] for item in definitions])
            if np.any(unsigned):
                values[unsigned] = truncnorm.ppf(
                    u[unsigned], -mean[unsigned] / stddev[unsigned], np.inf, loc=mean[unsigned], scale=stddev[unsigned]
                )
            output[indices] = values
        elif family == "LOGNORMAL":
            mu = np.asarray([item["parameters"]["mu"] for item in definitions])[:, None]
            sigma = np.asarray([item["parameters"]["sigma"] for item in definitions])[:, None]
            with np.errstate(over="ignore", under="ignore"):
                output[indices] = np.exp(mu + sigma * ndtri(u))
            if np.any(output[indices] == 0):
                raise EngineCalculationError("DISTRIBUTION_NUMERIC_UNDERFLOW")
        else:
            for row, definition in zip(indices, definitions, strict=True):
                scenarios = definition["values"]["scenarios"]
                probability = np.asarray([s["probability"] for s in scenarios], dtype=np.float64)
                # Only already validated roundoff-within-tolerance weights normalize.
                cumulative = np.cumsum(probability / probability.sum(dtype=np.float64))
                choices = np.searchsorted(cumulative, uniforms[row], side="right")
                output[row] = np.asarray([s["value"] for s in scenarios])[np.minimum(choices, len(scenarios) - 1)]
    if not np.all(np.isfinite(output)):
        raise EngineCalculationError("DISTRIBUTION_NUMERIC_OVERFLOW")
    return output


class _Pearson:
    def __init__(self, count):
        self.n = 0
        self.mean_x = np.zeros(count)
        self.m2_x = np.zeros(count)
        self.mean_y = 0.0
        self.m2_y = 0.0
        self.cov = np.zeros(count)

    def update(self, x, y):
        size = y.size
        mx, my = np.mean(x, axis=1), float(np.mean(y))
        constant_x = np.min(x, axis=1) == np.max(x, axis=1)
        mx[constant_x] = x[constant_x, 0]
        if np.min(y) == np.max(y):
            my = float(y[0])
        dx, dy = mx - self.mean_x, my - self.mean_y
        weight = self.n * size / (self.n + size)
        centered_x, centered_y = x - mx[:, None], y - my
        self.m2_x += np.sum(centered_x * centered_x, axis=1) + dx * dx * weight
        self.m2_y += float(np.sum(centered_y * centered_y)) + dy * dy * weight
        self.cov += np.sum(centered_x * centered_y[None, :], axis=1) + dx * dy * weight
        self.mean_x += dx * size / (self.n + size)
        self.mean_y += dy * size / (self.n + size)
        self.n += size

    def results(self, refs):
        denominator = np.sqrt(self.m2_x * self.m2_y)
        coefficients = np.divide(self.cov, denominator, out=np.zeros_like(self.cov), where=denominator > 0)
        indices = sorted(range(len(refs)), key=lambda i: (-abs(coefficients[i]), refs[i]))
        return [
            {
                "input_ref": refs[i],
                "method": SENSITIVITY_VERSION,
                "coefficient": float(np.clip(coefficients[i], -1, 1)) if denominator[i] > 0 else None,
                "rank": rank + 1,
                "direction": "NOT_EVALUABLE"
                if denominator[i] == 0
                else "POSITIVE"
                if coefficients[i] > 0
                else "NEGATIVE"
                if coefficients[i] < 0
                else "ZERO",
            }
            for rank, i in enumerate(indices)
        ]


def _stats(values, policy):
    constant = bool(np.min(values) == np.max(values))
    stddev = 0.0 if constant else float(np.std(values, ddof=0))
    mean = float(values[0]) if constant else float(np.mean(values))
    percentile_values = np.percentile(values, policy["percentiles"], method="linear")
    counts, edges = np.histogram(values, bins=policy["histogram_bins"])
    histogram = [
        {"lower": float(edges[i]), "upper": float(edges[i + 1]), "count": int(c), "probability": float(c / values.size)}
        for i, c in enumerate(counts)
    ]
    # Explicit empirical probabilities at bounded histogram upper edges.
    cdf = [
        {"value": row["upper"], "probability": float(np.count_nonzero(values <= row["upper"]) / values.size)}
        for row in histogram
    ]
    return {
        "summary": {
            "mean": mean,
            "standard_deviation": stddev,
            "minimum_sampled": float(np.min(values)),
            "maximum_sampled": float(np.max(values)),
            "coefficient_of_variation": stddev / abs(mean) if mean != 0 else None,
        },
        "percentiles": [
            {"percentile": float(p), "value": float(v)}
            for p, v in zip(policy["percentiles"], percentile_values, strict=True)
        ],
        "histogram": histogram,
        "cdf": cdf,
    }


def _convergence(values, policy):
    settings = policy["convergence"]
    if not settings["enabled"]:
        return {
            "status": "NOT_EVALUATED",
            "method": "RELATIVE_MEAN_STANDARD_ERROR_V1",
            "reason": "METHODOLOGY_DISABLED",
        }
    constant = bool(np.min(values) == np.max(values))
    mean = float(values[0]) if constant else float(np.mean(values))
    stddev = 0.0 if constant else float(np.std(values, ddof=1))
    standard_error = stddev / math.sqrt(values.size)
    relative = standard_error / abs(mean) if mean != 0 else (0.0 if stddev == 0 else None)
    converged = (
        values.size >= settings["min_iterations"]
        and relative is not None
        and relative <= settings["relative_mean_standard_error_tolerance"]
    )
    return {
        "status": "CONVERGED" if converged else "NOT_CONVERGED",
        "method": "RELATIVE_MEAN_STANDARD_ERROR_V1",
        "iterations": int(values.size),
        "minimum_iterations": settings["min_iterations"],
        "standard_error": standard_error,
        "relative_standard_error": relative,
        "tolerance": settings["relative_mean_standard_error_tolerance"],
        "percentile_convergence_evaluated": False,
        "limitation": "MEAN_STABILITY_ONLY_NOT_TAIL_OR_UNIVERSAL_CONVERGENCE",
    }


def calculate(
    snapshot: dict, seed: int, iterations: int, progress_callback: Callable[[int], bool | None] | None = None
) -> dict:
    """Execute a previously frozen contract; callback False cancels atomically."""
    issues = validate_snapshot(snapshot)
    if issues:
        raise EngineCalculationError(issues[0])
    if not _integer(seed, 0, 2**64 - 1):
        raise EngineCalculationError("ENGINE_SEED_INVALID")
    if not _integer(iterations, 2, 1000000):
        raise EngineCalculationError("ENGINE_ITERATIONS_INVALID")
    inputs = sorted(snapshot["inputs"], key=_ref)
    policy = snapshot["policy"]
    uncertain_positions = [i for i, item in enumerate(inputs) if item["mode"] == "UNCERTAIN"]
    uncertain = [inputs[i] for i in uncertain_positions]
    uncertain_refs = [_ref(item) for item in uncertain]
    correlation_blocks, correlation = _correlation_blocks(snapshot["correlations"], uncertain_refs, policy)
    generator = np.random.Generator(np.random.PCG64(seed))
    output = np.empty(iterations, dtype=np.float64)
    sensitivity = _Pearson(len(uncertain))
    schedule_mode = snapshot["analysis_type"] == "SCHEDULE_QRA"
    if schedule_mode:
        incoming, order, milestone_indices = _network(snapshot, inputs)
        milestone_values = {ref: np.empty(iterations) for ref, _ in milestone_indices}
    else:
        milestone_values = {}
    deterministic_sum = math.fsum(item["base_value"] for item in inputs if item["mode"] == "DETERMINISTIC")
    warnings = []
    if snapshot["analysis_type"] == "COST_QRA" and snapshot["cost"]["basis"] != "BASE_COST":
        warnings.append("POTENTIAL_OVERLAP_EXISTING_ALLOWANCE_OR_CONTINGENCY_REVIEW_REQUIRED")
    if any(item.get("risk_refs") for item in inputs):
        warnings.append("EXPLICIT_RISK_LINKS_TRACE_ONLY_NOT_AUTOMATIC_RISK_EVENTS")
    if schedule_mode:
        warnings.append("NORMALIZED_ELAPSED_TIME_NOT_WORK_CALENDAR_OR_CONTRACTUAL_DATES")
    if correlation_blocks:
        warnings.append("COPULA_COEFFICIENTS_ARE_LATENT_NOT_CALIBRATED_MARGINAL_CORRELATIONS")
    if any(b["roundoff_eigenvalues_zeroed"] for b in correlation["blocks"]):
        warnings.append("PSD_FLOAT64_ROUNDOFF_WITHIN_RECORDED_NUMERIC_TOLERANCE")
    if progress_callback and progress_callback(0) is False:
        raise EngineCancelled()
    for start in range(0, iterations, policy["chunk_size"]):
        stop = min(start + policy["chunk_size"], iterations)
        size = stop - start
        uniforms = generator.random((size, len(uncertain)), dtype=np.float64).T
        uniforms = np.clip(uniforms, np.finfo(np.float64).eps, 1 - np.finfo(np.float64).eps)
        for indices, factor in correlation_blocks:
            uniforms[indices] = ndtr(factor @ ndtri(uniforms[indices]))
        uniforms = np.clip(uniforms, np.finfo(np.float64).eps, 1 - np.finfo(np.float64).eps)
        sampled = _sample(uniforms, uncertain, policy)
        if schedule_mode:
            durations = np.asarray([item["base_value"] for item in inputs])[:, None] * np.ones((1, size))
            durations[uncertain_positions] = sampled
            starts = np.zeros_like(durations)
            completion = np.zeros(size)
            for j in order:
                for i, kind, lag in incoming[j]:
                    lower = starts[i] + lag
                    if kind in {"FS", "FF"}:
                        lower = lower + durations[i]
                    if kind in {"FF", "SF"}:
                        lower = lower - durations[j]
                    starts[j] = np.maximum(starts[j], lower)
                completion = np.maximum(completion, starts[j] + durations[j])
            for ref, index in milestone_indices:
                milestone_values[ref][start:stop] = starts[index] + durations[index]
        else:
            completion = deterministic_sum + np.sum(sampled, axis=0, dtype=np.float64)
        if not np.all(np.isfinite(completion)):
            raise EngineCalculationError("ENGINE_NUMERIC_OVERFLOW")
        output[start:stop] = completion
        sensitivity.update(sampled, completion)
        if progress_callback and progress_callback(stop) is False:
            raise EngineCancelled()
    results = _stats(output, policy)
    convergence = _convergence(output, policy)
    if convergence["status"] != "CONVERGED":
        warnings.append("CONVERGENCE_NOT_DEMONSTRATED")
    results.update(
        {
            "execution_status": "COMPLETED",
            "analysis_type": snapshot["analysis_type"],
            "engine_manifest": engine_manifest(),
            "iterations_completed": iterations,
            "canonical_input_order": [_ref(item) for item in inputs],
            "seed": seed,
            "correlation": correlation,
            "convergence": convergence,
            "sensitivity": sensitivity.results(uncertain_refs),
            "milestones": [],
            "warnings": sorted(set(warnings)),
            "blockers": [],
            "analytical_readiness": "READY_WITH_WARNINGS" if warnings else "READY",
            "result_quality": "BOUNDED_GOVERNED_ANALYTICAL_OUTPUT_NOT_INVESTMENT_APPROVAL",
            "criticality": {"status": "NOT_IMPLEMENTED", "operational_flags_reused": False},
            "risk_event_modeling": "NOT_IMPLEMENTED_EXPLICIT_TRACE_LINKS_ONLY",
            "raw_samples": {"persisted": False, "reproduction": "FROZEN_INPUT_SEED_ENGINE_VERSION"},
        }
    )
    if schedule_mode:
        schedule = snapshot["schedule"]
        anchor, seconds = _date(schedule["date_anchor"]), schedule["unit_seconds"]

        def date_value(value):
            try:
                return (anchor + timedelta(seconds=float(value) * seconds)).isoformat()
            except (OverflowError, ValueError) as exc:
                raise EngineCalculationError("SCHEDULE_DATE_OVERFLOW") from exc

        results["summary"].update(
            {
                "unit": schedule["unit"],
                "mean_completion_date": date_value(results["summary"]["mean"]),
                "date_anchor": anchor.isoformat(),
                "schedule_method": policy["schedule_method"],
                "authority": "QRA_ANALYTICAL_ONLY_P6_REMAINS_OPERATIONAL_AUTHORITY",
            }
        )
        for row in results["percentiles"]:
            row["completion_date"] = date_value(row["value"])
        if schedule.get("target_date"):
            target_duration = (_date(schedule["target_date"]) - anchor).total_seconds() / seconds
            results["summary"]["target_date"] = schedule["target_date"]
            results["summary"]["probability_meeting_target_date"] = float(
                np.count_nonzero(output <= target_duration) / iterations
            )
        for ref, values in milestone_values.items():
            milestone = _stats(values, policy)
            for row in milestone["percentiles"]:
                row["completion_date"] = date_value(row["value"])
            milestone["summary"]["mean_completion_date"] = date_value(milestone["summary"]["mean"])
            results["milestones"].append({"activity_ref": ref, **milestone})
    else:
        cost = snapshot["cost"]
        results["summary"].update(
            {
                "cost_basis": cost["basis"],
                "currency": cost["currency"],
                "deterministic_reference": cost["deterministic_reference"],
                "probability_exceeding_deterministic_reference": float(
                    np.count_nonzero(output > cost["deterministic_reference"]) / iterations
                ),
            }
        )
        if cost.get("target_amount") is not None:
            results["summary"]["target_amount"] = cost["target_amount"]
            results["summary"]["probability_meeting_target_amount"] = float(
                np.count_nonzero(output <= cost["target_amount"]) / iterations
            )
        if policy.get("analytical_indicator_percentile") is not None:
            selected = next(
                row for row in results["percentiles"] if row["percentile"] == policy["analytical_indicator_percentile"]
            )
            results["analytical_contingency_indicator"] = {
                "percentile": selected["percentile"],
                "value": selected["value"] - cost["deterministic_reference"],
                "interpretation": "ANALYTICAL_INDICATOR_ONLY_NOT_APPROVED_CONTINGENCY",
            }
    return results
