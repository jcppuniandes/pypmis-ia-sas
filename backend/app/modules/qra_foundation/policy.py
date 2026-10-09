"""Deterministic validation of modeling definitions, never random sampling."""

from copy import deepcopy
from datetime import date
from math import isfinite

ANALYSIS_TYPES = ("COST_QRA", "SCHEDULE_QRA", "INTEGRATED_COST_SCHEDULE_QRA")
QUALITY_VALUES = ("NOT_AVAILABLE", "UNVERIFIED", "PARTIALLY_VERIFIED", "VERIFIED")
RANGE_TYPES = (
    "MIN_MOST_LIKELY_MAX",
    "LOW_BASE_HIGH",
    "PERCENT_MINUS_PLUS",
    "ABSOLUTE_RANGE",
    "DISCRETE_SCENARIO",
    "OTHER_CONFIGURED_RANGE",
)
DISTRIBUTIONS = ("TRIANGULAR", "PERT", "BETA_PERT", "UNIFORM", "NORMAL", "LOGNORMAL", "DISCRETE", "CUSTOM_CONFIGURED")
CORRELATION_METHODS = (
    "NO_CORRELATION",
    "PAIRWISE_CORRELATION",
    "GROUP_CORRELATION",
    "MATRIX_CORRELATION",
    "OTHER_CONFIGURED_METHOD",
)
DEFAULT_CONFIGURATION = {
    "scope": {"type": "tenant", "workspace_id": None},
    "inherit_to_descendants": True,
    "applicability": {"governance_models": ["CAPITAL_OWNER"], "project_types": ["*"]},
    "methodology": {
        "code": "QRA_FOUNDATION",
        "name": "QRA Methodology & Source Readiness",
        "description": "Neutral DRAFT. No simulation or live evidence.",
    },
    "analysis_types": list(ANALYSIS_TYPES),
    "cost_requirements": [],
    "schedule_requirements": [],
    "schedule_quality_rules": {},
    "range_policies": [],
    "distribution_families": [],
    "distribution_rules": {},
    "correlation_methods": [],
    "correlation_rules": {},
    "model_governance": {
        "required_contexts": [],
        "require_review": True,
        "allow_deterministic": False,
        "deterministic_rationale_required": True,
    },
    "separation_of_duties": {
        "author_cannot_publish": True,
        "preparer_cannot_complete": True,
        "preparer_cannot_approve": True,
        "reviewer_cannot_publish_methodology": False,
        "source_preparer_cannot_approve": False,
        "decision_maker_cannot_sole_approve": False,
    },
    "freshness": {},
    "numbering": {
        "cost_prefix": "CSR",
        "schedule_prefix": "SSR",
        "model_prefix": "QRM",
        "padding": 6,
        "separator": "-",
    },
    "review_approval": {},
    "reserved_engine_settings": {},
}
CONTEXT_KEYS = {
    "risk_readiness",
    "risk_governance",
    "basic_data",
    "owner_capability",
    "fel_pdri",
    "fin",
    "budget",
    "resources",
}
APPLICABILITY_FIELDS = {
    "governance_models": "governance_model",
    "project_types": "project_type",
    "industries": "industry",
    "fel_stages": "fel_stage",
    "gate_profiles": "gate_profile",
    "complexities": "complexity",
    "risks": "risk",
    "uncertainty_levels": "uncertainty",
}


def matches(applicability, context):
    return all(
        not values
        or "*" in values
        or str(context.get(APPLICABILITY_FIELDS[key], "")).upper() in {str(v).upper() for v in values}
        for key, values in applicability.items()
        if key in APPLICABILITY_FIELDS
    )


def reference_valid(ref):
    return isinstance(ref, dict) and any(
        isinstance(ref.get(k), str) and bool(ref[k].strip()) for k in ("reference", "source_reference")
    )


def references_valid(refs):
    return isinstance(refs, list) and bool(refs) and all(reference_valid(r) for r in refs)


def numeric(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and isfinite(value)


def _applicability_issues(value):
    if not isinstance(value, dict):
        return ["APPLICABILITY_OBJECT_REQUIRED"]
    return [
        f"APPLICABILITY_INVALID:{k}"
        for k, v in value.items()
        if k not in APPLICABILITY_FIELDS or not isinstance(v, list) or any(not isinstance(s, str) or not s for s in v)
    ]


def configuration_issues(content):
    if not isinstance(content, dict):
        return ["CONFIGURATION_OBJECT_REQUIRED"]
    issues = []
    unknown = (
        set(content)
        - set(DEFAULT_CONFIGURATION)
        - {
            "effective_from",
            "effective_to",
            "fel_stage_rules",
            "gate_profile_rules",
            "project_type_rules",
            "governance_model_rules",
            "risk_complexity_rules",
        }
    )
    issues += [f"UNKNOWN_CONFIGURATION_SECTION:{key}" for key in sorted(unknown)]
    for key, default in DEFAULT_CONFIGURATION.items():
        if key not in content or not isinstance(content[key], type(default)):
            issues.append(f"CONFIGURATION_SECTION_INVALID:{key}")
    if issues:
        return issues
    scope = content["scope"]
    if scope.get("type") not in {"tenant", "enterprise", "business-unit", "portfolio"} or (
        scope.get("type") == "tenant"
    ) != (scope.get("workspace_id") is None):
        issues.append("CONFIGURATION_SCOPE_INVALID")
    issues += _applicability_issues(content["applicability"])
    if not content["methodology"].get("code") or not content["methodology"].get("name"):
        issues.append("METHODOLOGY_IDENTITY_REQUIRED")
    if (
        not content["analysis_types"]
        or len(set(content["analysis_types"])) != len(content["analysis_types"])
        or any(v not in ANALYSIS_TYPES for v in content["analysis_types"])
    ):
        issues.append("ANALYSIS_TYPES_INVALID")
    for key in ("cost_requirements", "schedule_requirements", "range_policies", "distribution_families"):
        entries = content[key]
        if len(entries) > 2000 or any(
            not isinstance(r, dict) or not isinstance(r.get("code"), str) or not r["code"].strip() for r in entries
        ):
            issues.append(f"CODED_ENTRIES_INVALID:{key}")
            continue
        codes = [r["code"] for r in entries]
        if len(set(codes)) != len(codes):
            issues.append(f"DUPLICATE_CODE:{key}")
        for entry in entries:
            issues += _applicability_issues(entry.get("applicability", {}))
            if key.endswith("requirements") and (not entry.get("field") or not entry.get("dimension")):
                issues.append(f"REQUIREMENT_FIELD_DIMENSION_REQUIRED:{entry['code']}")
            if entry.get("minimum_quality", "NOT_AVAILABLE") not in QUALITY_VALUES:
                issues.append(f"QUALITY_INVALID:{entry['code']}")
            for flag in (
                "blocking",
                "required",
                "allow_negative",
                "zero_floor",
                "require_evidence",
                "require_rationale",
            ):
                if flag in entry and not isinstance(entry[flag], bool):
                    issues.append(f"BOOLEAN_REQUIRED:{entry['code']}:{flag}")
    for entry in content["range_policies"]:
        if not isinstance(entry, dict) or entry.get("code") not in RANGE_TYPES:
            issues.append("RANGE_POLICY_UNSUPPORTED")
        elif any(k in entry and not numeric(entry[k]) for k in ("min", "max")) or (
            numeric(entry.get("min")) and numeric(entry.get("max")) and entry["min"] > entry["max"]
        ):
            issues.append(f"RANGE_BOUNDS_INVALID:{entry['code']}")
    for entry in content["distribution_families"]:
        if not isinstance(entry, dict) or entry.get("code") not in DISTRIBUTIONS:
            issues.append("DISTRIBUTION_FAMILY_UNSUPPORTED")
            continue
        if any(t not in RANGE_TYPES for t in entry.get("allowed_range_types", [])):
            issues.append(f"DISTRIBUTION_RANGE_INVALID:{entry['code']}")
        for parameter, bounds in entry.get("parameter_bounds", {}).items():
            if (
                not isinstance(bounds, dict)
                or any(k in bounds and not numeric(bounds[k]) for k in ("min", "max"))
                or (numeric(bounds.get("min")) and numeric(bounds.get("max")) and bounds["min"] > bounds["max"])
            ):
                issues.append(f"PARAMETER_BOUNDS_INVALID:{entry['code']}:{parameter}")
    if any(m not in CORRELATION_METHODS for m in content["correlation_methods"]):
        issues.append("CORRELATION_METHOD_UNSUPPORTED")
    rules = content["correlation_rules"]
    lo, hi = rules.get("minimum_coefficient", -1), rules.get("maximum_coefficient", 1)
    if not numeric(lo) or not numeric(hi) or not -1 <= lo <= hi <= 1:
        issues.append("CORRELATION_COEFFICIENT_POLICY_INVALID")
    if any(c not in CONTEXT_KEYS for c in content["model_governance"].get("required_contexts", [])):
        issues.append("MODEL_CONTEXT_UNKNOWN")
    for flag, value in content["separation_of_duties"].items():
        if flag not in DEFAULT_CONFIGURATION["separation_of_duties"] or not isinstance(value, bool):
            issues.append(f"SOD_RULE_INVALID:{flag}")
    if content["separation_of_duties"].get("author_cannot_publish") is not True:
        issues.append("INDEPENDENT_METHODOLOGY_PUBLICATION_REQUIRED")
    numbering = content["numbering"]
    if (
        not isinstance(numbering.get("padding"), int)
        or not 1 <= numbering["padding"] <= 12
        or any(
            not isinstance(numbering.get(f"{kind}_prefix"), str) or not 1 <= len(numbering[f"{kind}_prefix"]) <= 12
            for kind in ("cost", "schedule", "model")
        )
    ):
        issues.append("NUMBERING_INVALID")
    for key in ("effective_from", "effective_to"):
        if content.get(key) is not None:
            try:
                date.fromisoformat(content[key])
            except (TypeError, ValueError):
                issues.append(f"EFFECTIVE_DATE_INVALID:{key}")
    if (
        content.get("effective_from")
        and content.get("effective_to")
        and str(content["effective_from"]) > str(content["effective_to"])
    ):
        issues.append("EFFECTIVE_DATES_REVERSED")
    for key, value in content["schedule_quality_rules"].items():
        if key in {
            "maximum_open_ends",
            "maximum_constraints",
            "maximum_negative_lags",
            "maximum_lag_days",
            "maximum_lag_value",
            "minimum_duration",
            "maximum_duration",
            "maximum_status_findings",
        } and (not numeric(value) or value < 0):
            issues.append(f"SCHEDULE_THRESHOLD_INVALID:{key}")
        if key.startswith("require_") and not isinstance(value, bool):
            issues.append(f"SCHEDULE_BOOLEAN_INVALID:{key}")
    for key in ("maximum_source_age_days", "maximum_model_age_days"):
        value = content["freshness"].get(key)
        if value is not None and (not isinstance(value, int) or value < 0):
            issues.append(f"FRESHNESS_INVALID:{key}")
    if (
        "minimum_duration" in content["schedule_quality_rules"]
        or "maximum_duration" in content["schedule_quality_rules"]
    ) and not content["schedule_quality_rules"].get("duration_threshold_unit"):
        issues.append("SCHEDULE_DURATION_POLICY_UNIT_REQUIRED")
    if "maximum_lag_value" in content["schedule_quality_rules"] and not content["schedule_quality_rules"].get(
        "lag_unit"
    ):
        issues.append("SCHEDULE_LAG_POLICY_UNIT_REQUIRED")
    return sorted(set(issues))


def tailored_requirements(policy, kind, context):
    result = []
    for original in policy.get(f"{kind}_requirements", []):
        if not original.get("active", True) or not matches(original.get("applicability", {}), context):
            continue
        entry = deepcopy(original)
        entry.update(entry.get("stage_rules", {}).get(context.get("fel_stage"), {}))
        result.append(entry)
    return result


def input_issues(item, policy, context):
    ref = f"{item.get('source_kind')}:{item.get('source_item_ref')}"
    issues = []
    governance = policy["model_governance"]
    if item.get("status") != "VALIDATED":
        issues.append(f"INPUT_NOT_VALIDATED:{ref}")
    if item.get("mode") == "DETERMINISTIC":
        if not governance.get("allow_deterministic", False):
            issues.append(f"DETERMINISTIC_NOT_ALLOWED:{ref}")
        if governance.get("deterministic_rationale_required", True) and not str(item.get("rationale", "")).strip():
            issues.append(f"DETERMINISTIC_RATIONALE_REQUIRED:{ref}")
        if governance.get("deterministic_evidence_required", True) and not references_valid(item.get("evidence_refs")):
            issues.append(f"DETERMINISTIC_EVIDENCE_REQUIRED:{ref}")
        if item.get("range_type") or item.get("distribution_family") or item.get("values") or item.get("parameters"):
            issues.append(f"DETERMINISTIC_UNCERTAINTY_CONFLICT:{ref}")
        return issues
    representation = item.get("range_type")
    range_policy = next(
        (
            p
            for p in policy["range_policies"]
            if p["code"] == representation and matches(p.get("applicability", {}), context)
        ),
        None,
    )
    family = next(
        (
            p
            for p in policy["distribution_families"]
            if p["code"] == item.get("distribution_family") and matches(p.get("applicability", {}), context)
        ),
        None,
    )
    if not range_policy:
        return [f"RANGE_NOT_ALLOWED:{ref}"]
    if not family:
        issues.append(f"DISTRIBUTION_NOT_ALLOWED:{ref}")
    values = item.get("values", {})
    required_keys = {
        "MIN_MOST_LIKELY_MAX": ["min", "base", "max"],
        "LOW_BASE_HIGH": ["min", "base", "max"],
        "ABSOLUTE_RANGE": ["min", "max"],
        "PERCENT_MINUS_PLUS": ["base", "minus", "plus"],
        "DISCRETE_SCENARIO": [],
        "OTHER_CONFIGURED_RANGE": range_policy.get("required_parameters", []),
    }[representation]
    if any(not numeric(values.get(k)) for k in required_keys):
        issues.append(f"RANGE_PARAMETERS_INVALID:{ref}")
    if (
        representation in {"MIN_MOST_LIKELY_MAX", "LOW_BASE_HIGH"}
        and all(numeric(values.get(k)) for k in ("min", "base", "max"))
        and not values["min"] <= values["base"] <= values["max"]
    ):
        issues.append(f"RANGE_ORDER_INVALID:{ref}")
    if (
        representation == "ABSOLUTE_RANGE"
        and all(numeric(values.get(k)) for k in ("min", "max"))
        and values["min"] > values["max"]
    ):
        issues.append(f"RANGE_ORDER_INVALID:{ref}")
    if representation == "PERCENT_MINUS_PLUS" and all(numeric(values.get(k)) for k in ("base", "minus", "plus")):
        if (
            values["minus"] < 0
            or values["plus"] < 0
            or values["minus"] > range_policy.get("maximum_percent", 100)
            or values["plus"] > range_policy.get("maximum_percent", 100)
        ):
            issues.append(f"PERCENT_RANGE_INVALID:{ref}")
        if range_policy.get("zero_floor", True) and values["base"] * (1 - values["minus"] / 100) < 0:
            issues.append(f"RANGE_ZERO_FLOOR:{ref}")
    if representation == "DISCRETE_SCENARIO":
        scenarios = values.get("scenarios", [])
        if (
            not isinstance(scenarios, list)
            or not scenarios
            or any(
                not isinstance(s, dict)
                or not numeric(s.get("value"))
                or not numeric(s.get("probability"))
                or not 0 <= s["probability"] <= 1
                for s in scenarios
            )
            or abs(sum(s.get("probability", 0) for s in scenarios if isinstance(s, dict)) - 1) > 1e-9
        ):
            issues.append(f"DISCRETE_PARAMETERS_INVALID:{ref}")
    numbers = [v for v in values.values() if numeric(v)]
    if (not range_policy.get("allow_negative", False) or range_policy.get("zero_floor", False)) and any(
        v < 0 for v in numbers
    ):
        issues.append(f"RANGE_NEGATIVE_NOT_ALLOWED:{ref}")
    if any(v < range_policy.get("min", float("-inf")) or v > range_policy.get("max", float("inf")) for v in numbers):
        issues.append(f"RANGE_POLICY_BOUNDS:{ref}")
    if range_policy.get("require_evidence", True) and not references_valid(item.get("evidence_refs")):
        issues.append(f"RANGE_EVIDENCE_REQUIRED:{ref}")
    if range_policy.get("require_rationale", True) and not str(item.get("rationale", "")).strip():
        issues.append(f"RANGE_RATIONALE_REQUIRED:{ref}")
    if range_policy.get("allowed_sources") and item.get("range_source") not in range_policy["allowed_sources"]:
        issues.append(f"RANGE_SOURCE_INVALID:{ref}")
    if range_policy.get("unit") and item.get("unit") != range_policy["unit"]:
        issues.append(f"RANGE_UNIT_INVALID:{ref}")
    if item.get("quality") not in QUALITY_VALUES or QUALITY_VALUES.index(item["quality"]) < QUALITY_VALUES.index(
        range_policy.get("minimum_quality", "NOT_AVAILABLE")
    ):
        issues.append(f"RANGE_QUALITY_INSUFFICIENT:{ref}")
    if family:
        if family.get("allowed_range_types") and representation not in family["allowed_range_types"]:
            issues.append(f"DISTRIBUTION_RANGE_PROHIBITED:{ref}")
        parameters = item.get("parameters", {})
        mandatory = {"NORMAL": ["mean", "stddev"], "LOGNORMAL": ["mu", "sigma"]}.get(family["code"], []) + family.get(
            "parameters", []
        )
        allowed_parameters = (
            set(mandatory) | set(family.get("parameter_bounds", {})) | set(family.get("optional_parameters", []))
        )
        if family["code"] in {"PERT", "BETA_PERT"}:
            allowed_parameters.add("lambda")
        if set(parameters) - allowed_parameters:
            issues.append(f"DISTRIBUTION_UNKNOWN_PARAMETERS:{ref}")
        if any(not numeric(parameters.get(k)) for k in mandatory):
            issues.append(f"DISTRIBUTION_PARAMETERS_INVALID:{ref}")
        for k in ("stddev", "sigma", "lambda"):
            if k in parameters and (not numeric(parameters[k]) or parameters[k] <= 0):
                issues.append(f"DISTRIBUTION_PARAMETER_NONPOSITIVE:{ref}:{k}")
        if (
            family["code"] in {"PERT", "BETA_PERT"}
            and family.get("require_lambda", True)
            and "lambda" not in parameters
        ):
            issues.append(f"PERT_LAMBDA_REQUIRED:{ref}")
        for k, bounds in family.get("parameter_bounds", {}).items():
            if k in parameters and (
                not numeric(parameters[k])
                or parameters[k] < bounds.get("min", float("-inf"))
                or parameters[k] > bounds.get("max", float("inf"))
            ):
                issues.append(f"DISTRIBUTION_PARAMETER_BOUNDS:{ref}:{k}")
        if family.get("unit") and item.get("unit") != family["unit"]:
            issues.append(f"DISTRIBUTION_UNIT_INVALID:{ref}")
        if not family.get("allow_negative", False) and any(v < 0 for v in numbers):
            issues.append(f"DISTRIBUTION_NEGATIVE_NOT_ALLOWED:{ref}")
    return issues


def correlation_issues(correlations, input_refs, policy):
    issues = []
    if not isinstance(correlations, dict):
        return ["CORRELATION_OBJECT_REQUIRED"]
    method = correlations.get("method")
    if method not in policy["correlation_methods"]:
        return ["CORRELATION_METHOD_NOT_ALLOWED"]
    pairs, groups, matrix = (correlations.get(k, []) for k in ("pairs", "groups", "matrix"))
    if any(not isinstance(v, list) or len(v) > 20000 for v in (pairs, groups, matrix)):
        return ["CORRELATION_POPULATION_INVALID"]
    rules = policy["correlation_rules"]
    lo, hi = rules.get("minimum_coefficient", -1), rules.get("maximum_coefficient", 1)
    covered = set()
    seen = set()
    if method == "NO_CORRELATION" and (pairs or groups or matrix):
        issues.append("NO_CORRELATION_HAS_ENTRIES")
    if method == "PAIRWISE_CORRELATION":
        if groups or matrix:
            issues.append("CORRELATION_METHOD_CONTENT_MISMATCH")
        for pair in pairs:
            if not isinstance(pair, dict):
                issues.append("CORRELATION_PAIR_INVALID")
                continue
            a, b, coefficient = pair.get("left"), pair.get("right"), pair.get("coefficient")
            if any(not isinstance(ref, str) or not ref.strip() for ref in (a, b)):
                issues.append("CORRELATION_PAIR_REFERENCE_INVALID")
                continue
            if a not in input_refs or b not in input_refs:
                issues.append("CORRELATION_UNKNOWN_REFERENCE")
            if a == b:
                issues.append("CORRELATION_SELF_REFERENCE")
            key = tuple(sorted((str(a), str(b))))
            if key in seen:
                issues.append("CORRELATION_DUPLICATE_PAIR")
            seen.add(key)
            covered.update((a, b))
            if not numeric(coefficient) or not lo <= coefficient <= hi:
                issues.append("CORRELATION_COEFFICIENT_INVALID")
            if rules.get("require_rationale", True) and not str(pair.get("rationale", "")).strip():
                issues.append("CORRELATION_RATIONALE_REQUIRED")
    if method == "GROUP_CORRELATION":
        if pairs or matrix:
            issues.append("CORRELATION_METHOD_CONTENT_MISMATCH")
        for group in groups:
            if (
                not isinstance(group, dict)
                or not group.get("code")
                or not isinstance(group.get("members"), list)
                or len(group["members"]) < 2
            ):
                issues.append("CORRELATION_GROUP_INVALID")
                continue
            members = group["members"]
            if any(not isinstance(ref, str) or not ref.strip() for ref in members):
                issues.append("CORRELATION_GROUP_MEMBERSHIP_INVALID")
                continue
            if len(set(members)) != len(members) or any(m not in input_refs for m in members):
                issues.append("CORRELATION_GROUP_MEMBERSHIP_INVALID")
            if seen.intersection(members):
                issues.append("CORRELATION_DUPLICATE_GROUP_MEMBERSHIP")
            seen.update(members)
            covered.update(members)
            if not numeric(group.get("coefficient")) or not lo <= group["coefficient"] <= hi:
                issues.append("CORRELATION_COEFFICIENT_INVALID")
            if rules.get("require_rationale", True) and not str(group.get("rationale", "")).strip():
                issues.append("CORRELATION_RATIONALE_REQUIRED")
    if method == "MATRIX_CORRELATION":
        if pairs or groups:
            issues.append("CORRELATION_METHOD_CONTENT_MISMATCH")
        refs = correlations.get("refs", [])
        if (
            not isinstance(refs, list)
            or not refs
            or len(refs) > 1000
            or any(not isinstance(ref, str) or not ref.strip() for ref in refs)
            or len(set(refs)) != len(refs)
            or any(r not in input_refs for r in refs)
            or len(matrix) != len(refs)
            or any(not isinstance(row, list) or len(row) != len(refs) for row in matrix)
        ):
            issues.append("CORRELATION_MATRIX_REFERENCES_INVALID")
        else:
            covered.update(refs)
            for i, row in enumerate(matrix):
                for j, coefficient in enumerate(row):
                    if (
                        not numeric(coefficient)
                        or (i != j and not lo <= coefficient <= hi)
                        or (i == j and coefficient != 1)
                    ):
                        issues.append("CORRELATION_MATRIX_COEFFICIENT_INVALID")
                    if coefficient != matrix[j][i]:
                        issues.append("CORRELATION_MATRIX_ASYMMETRIC")
            if rules.get("require_rationale", True) and not str(correlations.get("rationale", "")).strip():
                issues.append("CORRELATION_RATIONALE_REQUIRED")
    if method == "OTHER_CONFIGURED_METHOD":
        if pairs or groups or matrix:
            issues.append("CORRELATION_METHOD_CONTENT_MISMATCH")
        if not correlations.get("reference"):
            issues.append("CORRELATION_CONFIGURED_REFERENCE_REQUIRED")
    if rules.get("require_complete_coverage", False) and method != "NO_CORRELATION" and set(input_refs) - covered:
        issues.append("CORRELATION_COVERAGE_INCOMPLETE")
    return sorted(set(issues))
