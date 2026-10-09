"""Independent definition-validation probes; no stochastic execution exists."""

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.modules.qra_foundation.policy import DEFAULT_CONFIGURATION, correlation_issues, input_issues
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
