"""Governed execution configuration, separate from numerical implementation.

The existing Foundation section remains optional. An empty section preserves
historical configuration validity, but cannot authorize execution.
"""

from math import isfinite

ENGINE_VERSION = "wave4-qra-v1"
ANALYSIS_TYPES = {"COST_QRA", "SCHEDULE_QRA"}
_KEYS = {
    "engine_version",
    "supported_analysis_types",
    "percentiles",
    "histogram_bins",
    "chunk_size",
    "max_correlation_dimension",
    "correlation_sampling",
    "probability_tolerance",
    "psd_tolerance",
    "normal_negative_policy",
    "schedule_method",
    "schedule_unit",
    "schedule_unit_seconds",
    "convergence",
    "analytical_indicator_percentile",
    "iteration_policy",
    "seed_policy",
    "fixed_seed",
    "result_review",
    "run_numbering",
    "worker_lease_seconds",
    "selected_milestone_refs",
    "raw_samples",
    "sensitivity_method",
}


def _number(value):
    return type(value) in (int, float) and isfinite(value)


def engine_configuration_issues(settings):
    if settings == {}:
        return []
    if not isinstance(settings, dict):
        return ["ENGINE_CONFIGURATION_OBJECT_REQUIRED"]
    issues = [f"ENGINE_CONFIGURATION_UNKNOWN_KEY:{key}" for key in sorted(set(settings) - _KEYS)]
    if settings.get("engine_version") != ENGINE_VERSION:
        issues.append("ENGINE_VERSION_NOT_SUPPORTED")
    analyses = settings.get("supported_analysis_types")
    if (
        not isinstance(analyses, list)
        or not analyses
        or any(not isinstance(v, str) or v not in ANALYSIS_TYPES for v in analyses)
    ):
        issues.append("ENGINE_ANALYSIS_TYPES_INVALID")
    values = settings.get("percentiles")
    if (
        not isinstance(values, list)
        or not values
        or len(values) > 25
        or any(not _number(v) or not 0 <= v <= 100 for v in values)
    ):
        issues.append("ENGINE_PERCENTILES_INVALID")
    elif len(set(values)) != len(values):
        issues.append("ENGINE_PERCENTILES_DUPLICATED")
    for key, low, high in (
        ("histogram_bins", 1, 100),
        ("chunk_size", 16, 1024),
        ("max_correlation_dimension", 2, 1000),
    ):
        if type(settings.get(key)) is not int or not low <= settings[key] <= high:
            issues.append(f"ENGINE_INTEGER_POLICY_INVALID:{key}")
    for key, ceiling in (("probability_tolerance", 1e-6), ("psd_tolerance", 1e-8)):
        if key in settings and (not _number(settings[key]) or not 0 < settings[key] <= ceiling):
            issues.append(f"ENGINE_NUMERIC_TOLERANCE_INVALID:{key}")
    if "correlation_sampling" in settings and settings["correlation_sampling"] != "GAUSSIAN_COPULA_V1":
        issues.append("ENGINE_CORRELATION_METHOD_NOT_SUPPORTED")
    if "normal_negative_policy" in settings and settings["normal_negative_policy"] != "TRUNCATE_AT_ZERO":
        issues.append("ENGINE_NORMAL_DOMAIN_POLICY_NOT_SUPPORTED")
    if isinstance(analyses, list) and "SCHEDULE_QRA" in analyses:
        if settings.get("schedule_method") != "NORMALIZED_ELAPSED_TIME_V1":
            issues.append("ENGINE_SCHEDULE_METHOD_NOT_SUPPORTED")
        if settings.get("schedule_unit") not in ("HOURS", "DAYS"):
            issues.append("ENGINE_SCHEDULE_UNIT_INVALID")
        if type(settings.get("schedule_unit_seconds")) is not int or settings["schedule_unit_seconds"] <= 0:
            issues.append("ENGINE_SCHEDULE_UNIT_SECONDS_REQUIRED")
        elif settings["schedule_unit_seconds"] != {"HOURS": 3600, "DAYS": 86400}.get(settings.get("schedule_unit")):
            issues.append("ENGINE_NORMALIZED_TIME_CONVERSION_NOT_SUPPORTED")
    convergence = settings.get("convergence")
    if not isinstance(convergence, dict):
        issues.append("ENGINE_CONVERGENCE_POLICY_REQUIRED")
    else:
        if set(convergence) - {"enabled", "min_iterations", "relative_mean_standard_error_tolerance"}:
            issues.append("ENGINE_CONVERGENCE_UNKNOWN_KEY")
        if (
            type(convergence.get("enabled")) is not bool
            or type(convergence.get("min_iterations")) is not int
            or convergence.get("min_iterations", 0) < 2
        ):
            issues.append("ENGINE_CONVERGENCE_POLICY_INVALID")
        tolerance = convergence.get("relative_mean_standard_error_tolerance")
        if not _number(tolerance) or not 0 < tolerance <= 1:
            issues.append("ENGINE_CONVERGENCE_TOLERANCE_INVALID")
    iterations = settings.get("iteration_policy")
    if not isinstance(iterations, dict):
        issues.append("ENGINE_ITERATION_POLICY_REQUIRED")
    else:
        if set(iterations) - {"minimum", "default", "maximum", "allow_override"}:
            issues.append("ENGINE_ITERATION_UNKNOWN_KEY")
        quantities = [iterations.get(key) for key in ("minimum", "default", "maximum")]
        if (
            any(type(value) is not int for value in quantities)
            or not 2 <= quantities[0] <= quantities[1] <= quantities[2] <= 1000000
        ):
            issues.append("ENGINE_ITERATION_BOUNDS_INVALID")
        if type(iterations.get("allow_override")) is not bool:
            issues.append("ENGINE_ITERATION_OVERRIDE_INVALID")
    seed = settings.get("seed_policy")
    if seed not in ("USER_SPECIFIED", "SYSTEM_GENERATED_AND_PERSISTED", "FIXED_FOR_REPRODUCIBILITY"):
        issues.append("ENGINE_SEED_POLICY_INVALID")
    if seed == "FIXED_FOR_REPRODUCIBILITY" and (
        type(settings.get("fixed_seed")) is not int or not 0 <= settings["fixed_seed"] < 2**64
    ):
        issues.append("ENGINE_FIXED_SEED_INVALID")
    review = settings.get("result_review")
    if not isinstance(review, dict) or review != {"require_review": True, "executor_cannot_accept": True}:
        issues.append("ENGINE_INDEPENDENT_RESULT_REVIEW_REQUIRED")
    numbering = settings.get("run_numbering")
    if numbering is None:
        issues.append("ENGINE_RUN_NUMBERING_REQUIRED")
    elif (
        not isinstance(numbering, dict)
        or set(numbering) - {"prefix", "padding", "separator"}
        or not isinstance(numbering.get("prefix"), str)
        or not numbering["prefix"]
        or len(numbering["prefix"]) > 16
        or type(numbering.get("padding")) is not int
        or not 1 <= numbering["padding"] <= 12
        or not isinstance(numbering.get("separator"), str)
        or len(numbering["separator"]) > 3
    ):
        issues.append("ENGINE_RUN_NUMBERING_INVALID")
    if "worker_lease_seconds" in settings and (
        type(settings["worker_lease_seconds"]) is not int or not 120 <= settings["worker_lease_seconds"] <= 86400
    ):
        issues.append("ENGINE_WORKER_LEASE_INVALID")
    if "selected_milestone_refs" in settings and (
        not isinstance(settings["selected_milestone_refs"], list)
        or any(not isinstance(ref, str) or not ref for ref in settings["selected_milestone_refs"])
    ):
        issues.append("ENGINE_MILESTONE_SELECTION_INVALID")
    if settings.get("raw_samples", False) is not False:
        issues.append("ENGINE_RAW_SAMPLE_STORAGE_NOT_SUPPORTED")
    if settings.get("sensitivity_method", "PEARSON_ONLINE_V1") != "PEARSON_ONLINE_V1":
        issues.append("ENGINE_SENSITIVITY_METHOD_NOT_SUPPORTED")
    indicator = settings.get("analytical_indicator_percentile")
    if indicator is not None and (not _number(indicator) or not isinstance(values, list) or indicator not in values):
        issues.append("ENGINE_ANALYTICAL_INDICATOR_PERCENTILE_INVALID")
    return issues
