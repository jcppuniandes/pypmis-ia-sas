"""Independent definition-validation probes; no stochastic execution exists."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.modules.qra_foundation.policy import (
    DEFAULT_CONFIGURATION,
    configuration_issues,
    correlation_issues,
    input_issues,
    tailored_requirements,
)
from app.modules.qra_foundation.schemas import ModelUpdateIn


def _policy():
    policy = deepcopy(DEFAULT_CONFIGURATION)
    policy["range_policies"] = [
        {
            "code": "MIN_MOST_LIKELY_MAX",
            "allow_negative": False,
            "require_evidence": True,
            "require_rationale": True,
        }
    ]
    policy["distribution_families"] = [
        {"code": "TRIANGULAR", "allowed_range_types": ["MIN_MOST_LIKELY_MAX"]},
        {
            "code": "PERT",
            "allowed_range_types": ["MIN_MOST_LIKELY_MAX"],
            "require_lambda": True,
            "parameter_bounds": {"lambda": {"min": 1, "max": 10}},
        },
    ]
    policy["correlation_methods"] = [
        "NO_CORRELATION",
        "PAIRWISE_CORRELATION",
        "GROUP_CORRELATION",
        "MATRIX_CORRELATION",
    ]
    return policy


def _input():
    return {
        "source_kind": "COST",
        "source_item_ref": "mine-development",
        "mode": "UNCERTAIN",
        "range_type": "MIN_MOST_LIKELY_MAX",
        "values": {"min": 800, "base": 1000, "max": 1300},
        "distribution_family": "TRIANGULAR",
        "parameters": {},
        "rationale": "Three-point estimate with governed evidence; no calibration claimed.",
        "evidence_refs": [{"reference": "BoE:mine-development", "version": "1"}],
        "quality": "VERIFIED",
        "status": "VALIDATED",
    }


def test_qra_valid_definition_is_not_a_simulation_result():
    item = _input()
    assert input_issues(item, _policy(), {"governance_model": "CAPITAL_OWNER"}) == []
    assert not any(key in item for key in ("p50", "p80", "p90", "contingency", "simulation_results"))


@pytest.mark.parametrize("quality", ["READY", "HIGH", "unverified", "", "FAKE"])
def test_qra_quality_codes_are_typed_and_never_trigger_internal_index_errors(quality):
    item = _input() | {"quality": quality}
    with pytest.raises(ValidationError):
        ModelUpdateIn(inputs=[item])


@pytest.mark.parametrize(
    ("method", "foreign_key"),
    [
        ("PAIRWISE_CORRELATION", "groups"),
        ("PAIRWISE_CORRELATION", "matrix"),
        ("GROUP_CORRELATION", "pairs"),
        ("GROUP_CORRELATION", "matrix"),
        ("MATRIX_CORRELATION", "pairs"),
        ("MATRIX_CORRELATION", "groups"),
    ],
)
def test_qra_correlation_methods_cannot_hide_unvalidated_foreign_content(method, foreign_key):
    correlations = {"method": method, "pairs": [], "groups": [], "matrix": []}
    correlations[foreign_key] = [{"unvalidated": "must not be ignored"}]
    issues = correlation_issues(correlations, {"COST:mine-development", "SCHEDULE:A-MINE"}, _policy())
    assert "CORRELATION_METHOD_CONTENT_MISMATCH" in issues


@pytest.mark.parametrize("bad_value", [True, float("nan"), float("inf"), "1000", None])
def test_qra_ranges_reject_non_finite_or_untyped_values_without_repair(bad_value):
    item = _input()
    item["values"]["base"] = bad_value
    assert any("RANGE_PARAMETERS_INVALID" in issue for issue in input_issues(item, _policy(), {}))


@pytest.mark.parametrize("parameters", [{}, {"lambda": 0}, {"lambda": -1}, {"lambda": 11}])
def test_qra_pert_parameters_are_governed_definitions_only(parameters):
    item = _input() | {"distribution_family": "PERT", "parameters": parameters}
    assert input_issues(item, _policy(), {})


def test_qra_correlation_matrix_requires_exact_symmetry_diagonal_and_known_refs():
    refs = ["COST:mine-development", "SCHEDULE:A-MINE"]
    valid = {
        "method": "MATRIX_CORRELATION",
        "pairs": [],
        "groups": [],
        "refs": refs,
        "matrix": [[1, 0.25], [0.25, 1]],
        "rationale": "Independent governed correlation evidence, without random sampling.",
    }
    assert correlation_issues(valid, set(refs), _policy()) == []
    asymmetric = deepcopy(valid)
    asymmetric["matrix"][1][0] = 0.5
    assert "CORRELATION_MATRIX_ASYMMETRIC" in correlation_issues(asymmetric, set(refs), _policy())
    diagonal = deepcopy(valid)
    diagonal["matrix"][0][0] = 0
    assert "CORRELATION_MATRIX_COEFFICIENT_INVALID" in correlation_issues(diagonal, set(refs), _policy())
    unknown = deepcopy(valid)
    unknown["refs"][0] = "COST:unrelated-source"
    assert "CORRELATION_MATRIX_REFERENCES_INVALID" in correlation_issues(unknown, set(refs), _policy())


@pytest.mark.parametrize(
    "definition",
    [
        {"method": "PAIRWISE_CORRELATION", "pairs": [{"left": {}, "right": [], "coefficient": 0.5}]},
        {"method": "GROUP_CORRELATION", "groups": [{"code": "bad", "members": [{}, []], "coefficient": 0.5}]},
        {"method": "MATRIX_CORRELATION", "refs": [{}, []], "matrix": [[1, 0], [0, 1]]},
    ],
)
def test_qra_correlation_references_must_be_scalar_identifiers_not_internal_errors(definition):
    assert correlation_issues(definition, {"COST:mine-development", "SCHEDULE:A-MINE"}, _policy())


@pytest.mark.parametrize("scenario_value", [-1, 101])
def test_qra_discrete_scenario_quantities_obey_range_and_distribution_policy(scenario_value):
    policy = _policy()
    policy["range_policies"] = [
        {"code": "DISCRETE_SCENARIO", "allow_negative": False, "zero_floor": True, "min": 0, "max": 100}
    ]
    policy["distribution_families"] = [
        {"code": "DISCRETE", "allowed_range_types": ["DISCRETE_SCENARIO"], "allow_negative": False}
    ]
    item = _input() | {
        "range_type": "DISCRETE_SCENARIO",
        "distribution_family": "DISCRETE",
        "values": {"scenarios": [{"value": scenario_value, "probability": 0.5}, {"value": 50, "probability": 0.5}]},
    }
    issues = input_issues(item, policy, {})
    assert any("RANGE_POLICY_BOUNDS" in issue for issue in issues)
    if scenario_value < 0:
        assert any("RANGE_NEGATIVE_NOT_ALLOWED" in issue for issue in issues)
        assert any("DISTRIBUTION_NEGATIVE_NOT_ALLOWED" in issue for issue in issues)


def test_qra_discrete_scenario_probabilities_are_not_quantity_bounds():
    policy = _policy()
    policy["range_policies"] = [{"code": "DISCRETE_SCENARIO", "min": 10, "max": 100}]
    policy["distribution_families"] = [{"code": "DISCRETE", "allowed_range_types": ["DISCRETE_SCENARIO"]}]
    item = _input() | {
        "range_type": "DISCRETE_SCENARIO",
        "distribution_family": "DISCRETE",
        "values": {"scenarios": [{"value": 10, "probability": 0.25}, {"value": 100, "probability": 0.75}]},
    }
    assert input_issues(item, policy, {}) == []


@pytest.mark.parametrize(
    ("section", "field", "invalid"),
    [
        ("distribution_families", "parameter_bounds", []),
        ("distribution_families", "parameter_bounds", None),
        ("distribution_families", "allowed_range_types", None),
        ("distribution_families", "parameters", [None]),
        ("distribution_families", "optional_parameters", {}),
        ("range_policies", "required_parameters", [None]),
        ("range_policies", "allowed_sources", None),
        ("range_policies", "maximum_percent", "100"),
        ("cost_requirements", "field", ["currency"]),
        ("cost_requirements", "stage_rules", None),
        ("cost_requirements", "stage_rules", {"FEL-3": {"field": []}}),
        ("cost_requirements", "stage_rules", {"FEL-3": {"applicability": False}}),
        ("schedule_requirements", "minimum_quality", "FAKE"),
    ],
)
def test_qra_nested_policy_types_are_rejected_without_internal_errors(section, field, invalid):
    policy = _policy()
    if section.endswith("requirements"):
        policy[section] = [{"code": "currency", "field": "currency", "dimension": "CURRENCY"}]
    policy[section][0][field] = invalid
    assert configuration_issues(policy)


@pytest.mark.parametrize(
    ("section", "field", "invalid"),
    [
        ("scope", "type", []),
        ("scope", "workspace_id", True),
        ("methodology", "name", []),
        ("model_governance", "required_contexts", [{}]),
        ("model_governance", "reconciliation_tolerance_percent", "5"),
        ("model_governance", "allow_deterministic", "false"),
        ("model_governance", "require_review", False),
        ("correlation_rules", "require_complete_coverage", "false"),
        ("schedule_quality_rules", "allowed_open_end_refs", [{}]),
        ("freshness", "maximum_model_age_days", True),
        ("numbering", "padding", True),
    ],
)
def test_qra_governance_policy_types_are_rejected_without_internal_errors(section, field, invalid):
    policy = _policy()
    policy[section][field] = invalid
    assert configuration_issues(policy)


def test_qra_analysis_type_entries_cannot_crash_policy_validation():
    policy = _policy()
    policy["analysis_types"] = [{}]
    assert "ANALYSIS_TYPES_INVALID" in configuration_issues(policy)


@pytest.mark.parametrize(
    "section",
    [
        "distribution_rules",
        "review_approval",
        "fel_stage_rules",
        "gate_profile_rules",
        "project_type_rules",
        "governance_model_rules",
        "risk_complexity_rules",
    ],
)
def test_qra_unimplemented_global_rule_sections_cannot_be_published_as_enforced(section):
    policy = _policy()
    policy[section] = {"ignored_rule": True}
    assert f"UNSUPPORTED_CONFIGURATION_SECTION:{section}" in configuration_issues(policy)
    policy[section] = {}
    assert configuration_issues(policy) == []


@pytest.mark.parametrize(("base_active", "stage_active"), [(True, False), (False, True)])
def test_qra_stage_tailoring_resolves_active_before_selecting_denominator(base_active, stage_active):
    policy = _policy()
    policy["cost_requirements"] = [
        {
            "code": "currency",
            "field": "currency",
            "dimension": "CURRENCY",
            "active": base_active,
            "stage_rules": {"FEL-3": {"active": stage_active}},
        }
    ]
    assert configuration_issues(policy) == []
    resolved = tailored_requirements(policy, "cost", {"fel_stage": "FEL-3"})
    assert bool(resolved) is stage_active
    assert tailored_requirements(policy, "cost", {"fel_stage": "FEL-2"}) == (
        policy["cost_requirements"] if base_active else []
    )
