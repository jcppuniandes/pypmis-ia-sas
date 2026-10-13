"""Independent deterministic/statistical checks for the governed pure kernel."""

import math
from copy import deepcopy
from datetime import datetime

import numpy as np
import pytest
from scipy.stats import norm

from app.modules.qra_engine.calculation import (
    ENGINE_VERSION,
    EngineCalculationError,
    EngineCancelled,
    _correlation_blocks,
    _Pearson,
    _sample,
    _stats,
    calculate,
    engine_manifest,
    validate_snapshot,
)


def policy(**changes):
    return {
        "engine_version": ENGINE_VERSION,
        "supported_analysis_types": ["COST_QRA", "SCHEDULE_QRA"],
        "percentiles": [10, 50, 80, 90],
        "chunk_size": 256,
        "histogram_bins": 20,
        "max_correlation_dimension": 1000,
        "correlation_sampling": "GAUSSIAN_COPULA_V1",
        "normal_negative_policy": "TRUNCATE_AT_ZERO",
        "schedule_method": "NORMALIZED_ELAPSED_TIME_V1",
        "convergence": {"enabled": True, "min_iterations": 1000, "relative_mean_standard_error_tolerance": 0.01},
        **changes,
    }


def item(ref="A", *, family="TRIANGULAR", minimum=10, base=20, maximum=30, source_kind="COST", **changes):
    return {
        "source_kind": source_kind,
        "source_item_ref": ref,
        "base_value": base,
        "mode": "UNCERTAIN",
        "range_type": "MIN_MOST_LIKELY_MAX",
        "values": {"min": minimum, "base": base, "max": maximum},
        "distribution_family": family,
        "parameters": {},
        "unit": "USD" if source_kind == "COST" else "HOURS",
        "allow_negative": False,
        "risk_refs": [],
        "input_type": "ESTIMATE_UNCERTAINTY" if source_kind == "COST" else "DURATION_UNCERTAINTY",
        **changes,
    }


def cost_snapshot(items=None, **changes):
    items = items or [item()]
    return {
        "analysis_type": "COST_QRA",
        "inputs": items,
        "correlations": {"method": "NO_CORRELATION"},
        "policy": policy(),
        "cost": {
            "basis": "BASE_COST",
            "currency": "USD",
            "deterministic_reference": sum(i["base_value"] for i in items),
        },
        **changes,
    }


def schedule_snapshot(durations=None, relationships=None, **changes):
    durations = durations or {"A": 10, "B": 4, "M": 0}
    entries = [
        item(ref, source_kind="SCHEDULE", base=value, mode="DETERMINISTIC", values={}, distribution_family=None)
        for ref, value in durations.items()
    ]
    return {
        "analysis_type": "SCHEDULE_QRA",
        "inputs": entries,
        "correlations": {"method": "NO_CORRELATION"},
        "policy": policy(),
        "schedule": {
            "unit": "HOURS",
            "unit_seconds": 3600,
            "date_anchor": "2026-01-01T00:00:00+00:00",
            "target_date": "2026-01-01T14:00:00+00:00",
            "activities": [
                {
                    "ref": ref,
                    "duration_unit": "HOURS",
                    "calendar_ref": "CAL",
                    "milestone": value == 0,
                    "status": "Not Started",
                }
                for ref, value in durations.items()
            ],
            "calendars": [{"source_id": "CAL", "work_pattern": "source-preserved-not-interpreted"}],
            "relationships": relationships
            or [
                {"predecessor": "A", "successor": "B", "type": "FS", "lag": 0, "lag_unit": "HOURS"},
                {"predecessor": "B", "successor": "M", "type": "FS", "lag": 0, "lag_unit": "HOURS"},
            ],
            "milestone_refs": [ref for ref, value in durations.items() if value == 0],
        },
        **changes,
    }


def test_engine_manifest_explicit_numeric_versions():
    manifest = engine_manifest()
    assert manifest["engine_version"] == ENGINE_VERSION
    assert manifest["prng_algorithm"] == "PCG64"
    assert manifest["numpy_version"] == np.__version__
    assert manifest["percentile_method"] == "numpy-linear-hyndman-fan-7-v1"
    assert manifest["raw_samples_retained"] is False


def test_deterministic_cost_zero_variance_exact_no_raw_samples():
    snapshot = cost_snapshot([item(mode="DETERMINISTIC", base=3.14)])
    result = calculate(snapshot, 5, 1000)
    assert result["summary"]["mean"] == 3.14
    assert result["summary"]["standard_deviation"] == 0
    assert all(p["value"] == 3.14 for p in result["percentiles"])
    assert result["sensitivity"] == []
    assert result["convergence"]["status"] == "CONVERGED"
    assert sum(h["count"] for h in result["histogram"]) == 1000
    assert result["cdf"][-1]["probability"] == 1


def test_seed_reproduction_and_canonical_order_without_input_mutation():
    snapshot = cost_snapshot([item("Z"), item("A", family="UNIFORM", minimum=100, base=150, maximum=200)])
    frozen = deepcopy(snapshot)
    first = calculate(snapshot, 501, 5000)
    assert calculate(snapshot, 501, 5000) == first
    snapshot["inputs"].reverse()
    assert calculate(snapshot, 501, 5000) == first
    assert first["summary"] != calculate(snapshot, 502, 5000)["summary"]
    snapshot["inputs"].reverse()
    assert snapshot == frozen


def test_uint64_seed_boundary_is_explicit_and_reproducible():
    first = calculate(cost_snapshot(), 2**64 - 1, 1000)
    assert first == calculate(cost_snapshot(), 2**64 - 1, 1000)
    with pytest.raises(EngineCalculationError, match="ENGINE_SEED_INVALID"):
        calculate(cost_snapshot(), 2**64, 1000)


@pytest.mark.parametrize("family", ["TRIANGULAR", "PERT", "BETA_PERT", "UNIFORM", "NORMAL", "LOGNORMAL", "DISCRETE"])
def test_every_distribution_seeded_large_n_moments_domain(family):
    definition = item(family=family)
    if family in {"PERT", "BETA_PERT"}:
        definition["parameters"] = {"lambda": 2.5}
        expected_mean, expected_variance = 20, 400 / (4 * (2.5 + 3))
    elif family == "TRIANGULAR":
        expected_mean, expected_variance = 20, 400 / 24
    elif family == "UNIFORM":
        expected_mean, expected_variance = 20, 400 / 12
    elif family == "NORMAL":
        definition["parameters"] = {"mean": 20, "stddev": 3}
        definition["allow_negative"] = True
        expected_mean, expected_variance = 20, 9
    elif family == "LOGNORMAL":
        definition["parameters"] = {"mu": math.log(20), "sigma": 0.3}
        expected_mean = math.exp(math.log(20) + 0.3**2 / 2)
        expected_variance = (math.exp(0.3**2) - 1) * math.exp(2 * math.log(20) + 0.3**2)
    else:
        definition["values"] = {"scenarios": [{"value": 0, "probability": 0.75}, {"value": 40, "probability": 0.25}]}
        definition["range_type"] = "DISCRETE_SCENARIO"
        expected_mean, expected_variance = 10, 300
    snapshot = cost_snapshot([definition])
    assert validate_snapshot(snapshot) == []
    result = calculate(snapshot, 1123, 40000)
    assert result["summary"]["mean"] == pytest.approx(expected_mean, abs=0.22)
    assert result["summary"]["standard_deviation"] ** 2 == pytest.approx(expected_variance, rel=0.035)
    assert calculate(snapshot, 1123, 40000) == result
    if family != "NORMAL":
        assert result["summary"]["minimum_sampled"] >= 0
    if family in {"PERT", "BETA_PERT", "TRIANGULAR", "UNIFORM"}:
        assert 10 <= result["summary"]["minimum_sampled"] <= result["summary"]["maximum_sampled"] <= 30


def test_uniform_quantiles_targets_and_indicator_not_contingency_approval():
    snapshot = cost_snapshot([item(family="UNIFORM", minimum=0, base=50, maximum=100)])
    snapshot["cost"]["target_amount"] = 80
    snapshot["policy"]["analytical_indicator_percentile"] = 80
    result = calculate(snapshot, 9381, 50000)
    assert next(p["value"] for p in result["percentiles"] if p["percentile"] == 80) == pytest.approx(80, abs=0.9)
    assert result["summary"]["probability_meeting_target_amount"] == pytest.approx(0.8, abs=0.009)
    assert result["summary"]["probability_exceeding_deterministic_reference"] == pytest.approx(0.5, abs=0.009)
    assert (
        result["analytical_contingency_indicator"]["interpretation"]
        == "ANALYTICAL_INDICATOR_ONLY_NOT_APPROVED_CONTINGENCY"
    )


def test_percentiles_type7_known_nonconstant_unsorted_series():
    # Sorted [2, 7, 11, 19, 31], h=(N-1)*p: these references are
    # hand-calculated order-statistic interpolations, not numpy.percentile.
    expected = {0: 2, 10: 4, 25: 7, 50: 11, 75: 19, 80: 21.4, 90: 26.2, 100: 31}
    result = _stats(np.asarray([31.0, 2.0, 7.0, 11.0, 19.0]), policy(percentiles=list(expected)))
    assert {p["percentile"]: p["value"] for p in result["percentiles"]} == pytest.approx(expected, abs=1e-12)
    assert result["summary"]["mean"] == 14
    assert result["summary"]["standard_deviation"] == pytest.approx(math.sqrt(103.2), abs=1e-12)


def test_lognormal_quantiles_against_analytic_reference_with_explicit_sampling_band():
    count, alpha = 40000, 1e-6
    mu, sigma = math.log(20), 0.3
    definition = item(family="LOGNORMAL", parameters={"mu": mu, "sigma": sigma})
    uniforms = np.random.Generator(np.random.PCG64(720145)).random((1, count))
    samples = _sample(uniforms, [definition], policy())[0]
    quantiles = (10, 50, 80, 90)
    result = _stats(samples, policy(percentiles=list(quantiles)))
    # DKW simultaneous CDF band, failure probability alpha, with one order
    # statistic/N allowance for type-7 interpolation. The analytic lognormal
    # reference exp(mu+sigma*Phi^-1(p)) is independent of the kernel sampler.
    epsilon = math.sqrt(math.log(2 / alpha) / (2 * count)) + 1 / count
    for row in result["percentiles"]:
        probability = row["percentile"] / 100
        reference = math.exp(mu + sigma * float(norm.ppf(probability)))
        lower = math.exp(mu + sigma * float(norm.ppf(probability - epsilon)))
        upper = math.exp(mu + sigma * float(norm.ppf(probability + epsilon)))
        assert lower <= row["value"] <= upper, (row, reference, lower, upper)
    assert math.exp(mu + sigma * float(norm.ppf(0.5))) == pytest.approx(20, abs=1e-12)


@pytest.mark.parametrize("base", [0.0, 1e12])
def test_streaming_pearson_matches_independent_numpy_full_sample_with_large_base(base):
    count = 4099
    generator = np.random.Generator(np.random.PCG64(81721))
    centered = generator.normal(0, 250, (3, count))
    x = base + centered
    y = base + 0.7 * centered[0] - 0.3 * centered[1] + 0.15 * centered[2] + generator.normal(0, 40, count)
    expected = np.corrcoef(np.vstack((x, y)))[:3, 3]
    refs = ["COST:A", "COST:B", "COST:C"]
    scale = min(float(np.min(np.std(x, axis=1))), float(np.std(y)))
    # Centering a 1e12-offset float64 series loses low-order bits: allow 16
    # input ULPs relative to the observed scale for batch-mean/merge rounding.
    # At zero offset the reference must match to 1e-12, not a statistical band.
    tolerance = max(1e-12, 16 * float(np.spacing(base)) / scale)
    for chunk_size in (128, 257):
        accumulator = _Pearson(3)
        for start in range(0, count, chunk_size):
            accumulator.update(x[:, start : start + chunk_size], y[start : start + chunk_size])
        actual = {row["input_ref"]: row["coefficient"] for row in accumulator.results(refs)}
        assert [actual[ref] for ref in refs] == pytest.approx(expected, abs=tolerance)
        assert accumulator.n == count


def test_independent_sum_theoretical_moments_and_dominant_pearson_driver():
    snapshot = cost_snapshot(
        [
            item("Small", family="UNIFORM", minimum=0, base=1, maximum=2),
            item("Large", family="UNIFORM", minimum=0, base=50, maximum=100),
        ]
    )
    result = calculate(snapshot, 42, 40000)
    assert result["summary"]["mean"] == pytest.approx(51, abs=0.5)
    assert result["summary"]["standard_deviation"] ** 2 == pytest.approx((4 + 10000) / 12, rel=0.025)
    assert result["sensitivity"][0]["input_ref"] == "COST:Large"
    assert result["sensitivity"][0]["coefficient"] > 0.999


@pytest.mark.parametrize("coefficient", [-1, -0.65, 0.0, 0.65, 1])
def test_psd_gaussian_copula_observed_latent_normal_correlation(coefficient):
    entries = [
        item(ref, family="NORMAL", parameters={"mean": 0, "stddev": 1}, allow_negative=True) for ref in ("A", "B")
    ]
    correlations = {
        "method": "MATRIX_CORRELATION",
        "refs": ["COST:A", "COST:B"],
        "matrix": [[1, coefficient], [coefficient, 1]],
    }
    blocks, diagnostic = _correlation_blocks(correlations, ["COST:A", "COST:B"], policy())
    uniforms = np.random.Generator(np.random.PCG64(77)).random((50000, 2)).T
    from scipy.special import ndtr, ndtri

    for indices, factor in blocks:
        uniforms[indices] = ndtr(factor @ ndtri(uniforms[indices]))
    samples = _sample(np.clip(uniforms, np.finfo(float).eps, 1 - np.finfo(float).eps), entries, policy())
    assert np.corrcoef(samples)[0, 1] == pytest.approx(coefficient, abs=0.012)
    assert diagnostic["no_psd_repair"] is True
    assert "LATENT" in diagnostic["coefficient_semantics"]


@pytest.mark.parametrize(
    "matrix,code",
    [
        ([[1, 0.9, 0.9], [0.9, 1, -0.9], [0.9, -0.9, 1]], "CORRELATION_MATRIX_NOT_PSD"),
        ([[1, 0.2], [0.3, 1]], "CORRELATION_MATRIX_ASYMMETRIC"),
        ([[0.9, 0], [0, 1]], "CORRELATION_DIAGONAL_INVALID"),
        ([[1, 1.1], [1.1, 1]], "CORRELATION_COEFFICIENT_INVALID"),
        ([[1, float("nan")], [float("nan"), 1]], "CORRELATION_COEFFICIENT_INVALID"),
    ],
)
def test_psd_structural_and_indefinite_blocked_without_repair(matrix, code):
    entries = [item(str(i)) for i in range(len(matrix))]
    snapshot = cost_snapshot(entries)
    snapshot["correlations"] = {
        "method": "MATRIX_CORRELATION",
        "refs": [f"COST:{i}" for i in range(len(matrix))],
        "matrix": matrix,
    }
    assert code in validate_snapshot(snapshot)
    with pytest.raises(EngineCalculationError, match=code):
        calculate(snapshot, 1, 1000)


def test_pairwise_sparse_components_and_group_semantics():
    refs = [f"COST:{i}" for i in range(10000)]
    pairs = {"method": "PAIRWISE_CORRELATION", "pairs": [{"left": "COST:1", "right": "COST:9000", "coefficient": 0.3}]}
    blocks, diagnostic = _correlation_blocks(pairs, refs, policy())
    assert len(blocks) == 1 and blocks[0][1].shape == (2, 2)
    assert diagnostic["blocks"][0]["dimension"] == 2
    groups = {
        "method": "GROUP_CORRELATION",
        "groups": [{"code": "G", "members": ["COST:1", "COST:2", "COST:3"], "coefficient": -0.8}],
    }
    with pytest.raises(EngineCalculationError, match="CORRELATION_MATRIX_NOT_PSD"):
        _correlation_blocks(groups, refs, policy())


def test_semidefinite_perfect_correlation_and_factor_reproduce_matrix():
    correlations = {
        "method": "MATRIX_CORRELATION",
        "refs": ["COST:A", "COST:B", "COST:C"],
        "matrix": [[1, 1, 1], [1, 1, 1], [1, 1, 1]],
    }
    blocks, diagnostic = _correlation_blocks(correlations, correlations["refs"], policy())
    assert np.allclose(blocks[0][1] @ blocks[0][1].T, np.ones((3, 3)), atol=1e-14)
    assert diagnostic["blocks"][0]["minimum_eigenvalue"] >= -1e-10
    assert diagnostic["no_psd_repair"]


def test_correlated_non_normal_families_are_governed_copula_not_marginal_claim():
    snapshot = cost_snapshot(
        [
            item("A", family="TRIANGULAR"),
            item("B", family="PERT", parameters={"lambda": 5}),
            item(
                "C",
                family="DISCRETE",
                values={"scenarios": [{"value": 0, "probability": 0.7}, {"value": 50, "probability": 0.3}]},
            ),
        ]
    )
    snapshot["correlations"] = {
        "method": "GROUP_CORRELATION",
        "groups": [{"code": "G", "members": ["COST:A", "COST:B", "COST:C"], "coefficient": 0.4}],
    }
    result = calculate(snapshot, 37, 5000)
    assert result["correlation"]["coefficient_semantics"] == "LATENT_GAUSSIAN_PEARSON_NOT_MARGINAL_CALIBRATION"
    assert all(math.isfinite(row["coefficient"]) for row in result["sensitivity"])
    snapshot["policy"].pop("correlation_sampling")
    assert "ENGINE_METHOD_NOT_SUPPORTED" in validate_snapshot(snapshot)


def test_correlation_method_content_mismatch_and_block_limit_rejected():
    snapshot = cost_snapshot([item("A"), item("B"), item("C")])
    snapshot["correlations"] = {
        "method": "MATRIX_CORRELATION",
        "refs": ["COST:A", "COST:B", "COST:C"],
        "matrix": [[1, 0.3, 0.3], [0.3, 1, 0.3], [0.3, 0.3, 1]],
        "pairs": [{"left": "COST:A", "right": "COST:B", "coefficient": 0.1}],
    }
    assert "CORRELATION_METHOD_CONTENT_MISMATCH" in validate_snapshot(snapshot)
    snapshot["correlations"].pop("pairs")
    snapshot["policy"]["max_correlation_dimension"] = 2
    assert "CORRELATION_BLOCK_LIMIT_EXCEEDED" in validate_snapshot(snapshot)


@pytest.mark.parametrize(
    "family,change,code",
    [
        ("TRIANGULAR", {"values": {"min": 30, "base": 20, "max": 10}}, "DISTRIBUTION_PARAMETERS_INVALID"),
        ("UNIFORM", {"values": {"min": -1, "max": 1}}, "DISTRIBUTION_NEGATIVE_NOT_ALLOWED"),
        ("PERT", {"parameters": {}}, "PERT_LAMBDA_REQUIRED"),
        ("BETA_PERT", {"parameters": {"lambda": 0}}, "PERT_LAMBDA_REQUIRED"),
        ("NORMAL", {"parameters": {"mean": 2, "stddev": 0}}, "DISTRIBUTION_PARAMETERS_INVALID"),
        ("NORMAL", {"parameters": {"mean": 2}}, "DISTRIBUTION_PARAMETERS_INVALID"),
        ("LOGNORMAL", {"parameters": {"mu": 2, "sigma": -1}}, "DISTRIBUTION_PARAMETERS_INVALID"),
        ("DISCRETE", {"values": {"scenarios": [{"value": 1, "probability": 0.6}]}}, "DISCRETE_PROBABILITY_SUM_INVALID"),
        ("DISCRETE", {"values": {"scenarios": [{"value": -1, "probability": 1}]}}, "DISTRIBUTION_NEGATIVE_NOT_ALLOWED"),
        ("CUSTOM_CONFIGURED", {}, "ENGINE_METHOD_NOT_SUPPORTED"),
    ],
)
def test_each_distribution_rejects_invalid_governed_parameters(family, change, code):
    assert code in validate_snapshot(cost_snapshot([item(family=family, **change)]))


def test_pert_lambda_not_implicitly_four_changes_distribution():
    first = cost_snapshot([item(family="PERT", minimum=0, base=2, maximum=10, parameters={"lambda": 1})])
    second = deepcopy(first)
    second["inputs"][0]["parameters"]["lambda"] = 8
    a, b = calculate(first, 19, 15000), calculate(second, 19, 15000)
    assert a["summary"]["mean"] == pytest.approx(4, abs=0.1)
    assert b["summary"]["mean"] == pytest.approx(2.6, abs=0.1)
    assert a["summary"] != b["summary"]


def test_unsigned_normal_requires_explicit_approved_truncation_not_clamping():
    snapshot = cost_snapshot([item(family="NORMAL", parameters={"mean": -1, "stddev": 1})])
    snapshot["policy"].pop("normal_negative_policy")
    assert "NORMAL_NEGATIVE_SUPPORT_NOT_ALLOWED" in validate_snapshot(snapshot)
    snapshot["policy"]["normal_negative_policy"] = "TRUNCATE_AT_ZERO"
    result = calculate(snapshot, 42, 20000)
    assert result["summary"]["minimum_sampled"] > 0
    # Conditional normal E[X|X>=0] = -1 + phi(1)/(1-Phi(1)).
    assert result["summary"]["mean"] == pytest.approx(0.525135276, abs=0.02)


def test_discrete_roundoff_within_explicit_tolerance_and_occurrence_rate():
    snapshot = cost_snapshot(
        [
            item(
                family="DISCRETE",
                values={"scenarios": [{"value": 0, "probability": 0.7}, {"value": 1, "probability": 0.3 + 1e-10}]},
            )
        ]
    )
    result = calculate(snapshot, 661, 30000)
    assert result["summary"]["mean"] == pytest.approx(0.3, abs=0.012)
    snapshot["inputs"][0]["values"]["scenarios"][1]["probability"] = 0.30001
    assert "DISCRETE_PROBABILITY_SUM_INVALID" in validate_snapshot(snapshot)


def test_percentage_bounds_explicit_percent_representation():
    definition = item(range_type="PERCENT_MINUS_PLUS", values={"base": 100, "minus": 10, "plus": 20})
    result = calculate(cost_snapshot([definition]), 10, 10000)
    assert 90 <= result["summary"]["minimum_sampled"] <= result["summary"]["maximum_sampled"] <= 120
    assert result["summary"]["mean"] == pytest.approx((90 + 100 + 120) / 3, abs=0.2)


def test_schedule_all_deterministic_equivalence_and_utc_dates():
    snapshot = schedule_snapshot()
    before = deepcopy(snapshot)
    result = calculate(snapshot, 5, 1000)
    assert result["summary"]["mean"] == 14
    assert result["summary"]["standard_deviation"] == 0
    assert result["summary"]["mean_completion_date"] == "2026-01-01T14:00:00+00:00"
    assert result["summary"]["probability_meeting_target_date"] == 1
    assert result["milestones"][0]["summary"]["mean"] == 14
    assert snapshot == before


@pytest.mark.parametrize(
    "kind,lag,duration_b,expected",
    [
        ("FS", 3, 4, 17),
        ("SS", 3, 4, 10),
        ("FF", 3, 4, 13),
        ("SF", 3, 4, 10),
        ("FS", -3, 4, 11),
        ("SS", 9, 4, 13),
        ("FF", -3, 4, 10),
        ("SF", 15, 4, 15),
    ],
)
def test_independent_generalized_precedence_network_relationships(kind, lag, duration_b, expected):
    # Independently verified starts: FS=max(0,10+lag), SS=max(0,lag),
    # FF=max(0,10+lag-4), SF=max(0,lag-4); completion=max(10,startB+4).
    snapshot = schedule_snapshot(
        {"A": 10, "B": duration_b},
        [{"predecessor": "A", "successor": "B", "type": kind, "lag": lag, "lag_unit": "HOURS"}],
    )
    result = calculate(snapshot, 14, 1000)
    assert result["summary"]["mean"] == expected
    assert result["summary"]["standard_deviation"] == 0


def test_generalized_network_branch_merge_and_zero_milestone():
    snapshot = schedule_snapshot(
        {"A": 5, "B": 10, "C": 3, "M": 0},
        [
            {"predecessor": "A", "successor": "B", "type": "SS", "lag": 2, "lag_unit": "HOURS"},
            {"predecessor": "A", "successor": "C", "type": "FS", "lag": 1, "lag_unit": "HOURS"},
            {"predecessor": "B", "successor": "M", "type": "FF", "lag": 1, "lag_unit": "HOURS"},
            {"predecessor": "C", "successor": "M", "type": "FS", "lag": 0, "lag_unit": "HOURS"},
        ],
    )
    assert calculate(snapshot, 1, 1000)["summary"]["mean"] == 13


def test_schedule_duration_uncertainty_drivers_dates_no_p6_flags():
    snapshot = schedule_snapshot({"A": 10, "B": 4, "M": 0})
    snapshot["inputs"][0].update(
        mode="UNCERTAIN", distribution_family="UNIFORM", range_type="ABSOLUTE_RANGE", values={"min": 1, "max": 20}
    )
    snapshot["schedule"]["activities"][0]["critical_path_imported"] = False
    result = calculate(snapshot, 43, 30000)
    assert result["summary"]["mean"] == pytest.approx(14.5, abs=0.1)
    assert result["sensitivity"][0]["coefficient"] == pytest.approx(1, abs=1e-12)
    assert result["criticality"]["status"] == "NOT_IMPLEMENTED"
    assert result["criticality"]["operational_flags_reused"] is False
    p80 = next(p for p in result["percentiles"] if p["percentile"] == 80)
    assert p80["value"] == pytest.approx(20.2, abs=0.15)
    assert datetime.fromisoformat(p80["completion_date"]).year == 2026


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("method", "ENGINE_METHOD_NOT_SUPPORTED"),
        ("unit", "SCHEDULE_UNIT_NORMALIZATION_NOT_APPROVED"),
        ("lag_unit", "SCHEDULE_LAG_UNIT_NOT_APPROVED"),
        ("calendar", "SCHEDULE_CALENDAR_NOT_AVAILABLE"),
        ("constraint", "SCHEDULE_CONSTRAINT_NOT_SUPPORTED"),
        ("actual", "SCHEDULE_ACTUAL_PROGRESS_NOT_SUPPORTED"),
        ("cycle", "SCHEDULE_NETWORK_CYCLE"),
        ("relationship", "UNSUPPORTED_RELATIONSHIP_FOR_QRA_ENGINE"),
        ("anchor", "SCHEDULE_DATE_TIMEZONE_REQUIRED"),
    ],
)
def test_schedule_unsupported_semantics_block_without_approximations(mutation, code):
    snapshot = schedule_snapshot()
    if mutation == "method":
        snapshot["policy"].pop("schedule_method")
    elif mutation == "unit":
        snapshot["schedule"]["unit_seconds"] = 28800
    elif mutation == "lag_unit":
        snapshot["schedule"]["relationships"][0]["lag_unit"] = "DAYS"
    elif mutation == "calendar":
        snapshot["schedule"]["calendars"] = []
    elif mutation == "constraint":
        snapshot["schedule"]["activities"][0]["primary_constraint_type"] = "START_ON"
    elif mutation == "actual":
        snapshot["schedule"]["activities"][0]["actual_start"] = "2025-12-01"
    elif mutation == "cycle":
        snapshot["schedule"]["relationships"].append(
            {"predecessor": "M", "successor": "A", "type": "FS", "lag": 0, "lag_unit": "HOURS"}
        )
    elif mutation == "relationship":
        snapshot["schedule"]["relationships"][0]["type"] = "UNKNOWN"
    elif mutation == "anchor":
        snapshot["schedule"]["date_anchor"] = "2026-01-01T12:00:00"
    assert code in validate_snapshot(snapshot)


def test_normalized_days_are_elapsed_not_five_day_week():
    snapshot = schedule_snapshot({"A": 10, "B": 4, "M": 0})
    for definition in snapshot["inputs"]:
        definition["unit"] = "DAYS"
    for activity in snapshot["schedule"]["activities"]:
        activity["duration_unit"] = "DAYS"
    for relationship in snapshot["schedule"]["relationships"]:
        relationship["lag_unit"] = "DAYS"
    snapshot["schedule"].update(unit="DAYS", unit_seconds=86400, date_anchor="2026-01-01")
    assert calculate(snapshot, 1, 1000)["summary"]["mean_completion_date"] == "2026-01-15T00:00:00+00:00"


@pytest.mark.parametrize("status", ["In Progress", "Completed", "TK_Active", "TK_Complete", "UNDECLARED"])
def test_started_or_completed_status_without_actual_dates_is_still_blocked(status):
    snapshot = schedule_snapshot()
    snapshot["schedule"]["activities"][0]["status"] = status
    assert "SCHEDULE_STARTED_ACTIVITY_NOT_SUPPORTED" in validate_snapshot(snapshot)


def test_missing_activity_status_never_assumes_not_started():
    snapshot = schedule_snapshot()
    snapshot["schedule"]["activities"][0].pop("status")
    assert "SCHEDULE_ACTIVITY_STATUS_REQUIRED" in validate_snapshot(snapshot)


@pytest.mark.parametrize(
    "remaining,code",
    [
        (8, "SCHEDULE_REMAINING_DURATION_MODEL_NOT_SUPPORTED"),
        ("NaN", "SCHEDULE_REMAINING_DURATION_INVALID"),
        ("", "SCHEDULE_REMAINING_DURATION_INVALID"),
        (-1, "SCHEDULE_REMAINING_DURATION_INVALID"),
    ],
)
def test_remaining_duration_requires_supported_inception_relative_semantics(remaining, code):
    snapshot = schedule_snapshot()
    snapshot["schedule"]["activities"][0]["remaining_duration"] = remaining
    assert code in validate_snapshot(snapshot)


def test_explicit_not_started_xer_alias_and_equal_remaining_duration_are_valid():
    snapshot = schedule_snapshot()
    snapshot["schedule"]["activities"][0].update(status="TK_NotStart", remaining_duration="10")
    assert validate_snapshot(snapshot) == []
    assert calculate(snapshot, 2, 1000)["summary"]["mean"] == 14


def test_convergence_disabled_insufficient_and_stable_mean_distinct():
    snapshot = cost_snapshot([item(family="UNIFORM", minimum=0, base=50, maximum=100)])
    short = calculate(snapshot, 31, 200)
    assert short["convergence"]["status"] == "NOT_CONVERGED"
    long = calculate(snapshot, 31, 20000)
    assert long["convergence"]["status"] == "CONVERGED"
    assert long["convergence"]["standard_error"] < short["convergence"]["standard_error"]
    assert long["convergence"]["percentile_convergence_evaluated"] is False
    snapshot["policy"]["convergence"] = {"enabled": False}
    assert calculate(snapshot, 31, 20000)["convergence"]["status"] == "NOT_EVALUATED"


def test_progress_includes_zero_and_complete_and_cancellation_no_partial_result():
    observed = []
    result = calculate(cost_snapshot(), 1, 1000, lambda n: observed.append(n))
    assert observed == [0, 256, 512, 768, 1000]
    assert result["iterations_completed"] == 1000
    with pytest.raises(EngineCancelled):
        calculate(cost_snapshot(), 1, 1000, lambda n: n < 512)


def test_sampling_failure_overflow_not_partial_governed_output():
    snapshot = cost_snapshot([item(family="LOGNORMAL", parameters={"mu": 1000, "sigma": 1})])
    with pytest.raises(EngineCalculationError, match="DISTRIBUTION_NUMERIC_OVERFLOW"):
        calculate(snapshot, 2, 1000)


def test_lognormal_underflow_blocks_zero_nonpositive_realizations():
    snapshot = cost_snapshot([item(family="LOGNORMAL", parameters={"mu": -1000, "sigma": 1})])
    with pytest.raises(EngineCalculationError, match="DISTRIBUTION_NUMERIC_UNDERFLOW"):
        calculate(snapshot, 2, 1000)


def test_degenerate_uncertain_range_does_not_fabricate_pearson_driver():
    snapshot = cost_snapshot([item(family="UNIFORM", minimum=3.14, base=3.14, maximum=3.14)])
    result = calculate(snapshot, 5, 1000)
    assert result["summary"]["standard_deviation"] == 0
    assert result["sensitivity"][0]["coefficient"] is None
    assert result["sensitivity"][0]["direction"] == "NOT_EVALUABLE"


def test_integrated_custom_risk_event_and_raw_sample_persistence_not_faked():
    snapshot = cost_snapshot(analysis_type="INTEGRATED_COST_SCHEDULE_QRA")
    assert "ENGINE_METHOD_NOT_SUPPORTED" in validate_snapshot(snapshot)
    snapshot = cost_snapshot([item(input_type="DISCRETE_RISK_EVENT")])
    assert "ENGINE_METHOD_NOT_SUPPORTED" in validate_snapshot(snapshot)
    snapshot = cost_snapshot()
    snapshot["policy"]["retain_raw_samples"] = True
    assert "ENGINE_METHOD_NOT_SUPPORTED" in validate_snapshot(snapshot)


def test_explicit_non_base_cost_warns_double_counting_but_never_source_write():
    snapshot = cost_snapshot([item(risk_refs=[{"risk_id": 3, "reference": "governed-input-link"}])])
    snapshot["cost"]["basis"] = "COST_WITH_CONTINGENCY"
    before = deepcopy(snapshot)
    result = calculate(snapshot, 3, 1000)
    assert "POTENTIAL_OVERLAP_EXISTING_ALLOWANCE_OR_CONTINGENCY_REVIEW_REQUIRED" in result["warnings"]
    assert "EXPLICIT_RISK_LINKS_TRACE_ONLY_NOT_AUTOMATIC_RISK_EVENTS" in result["warnings"]
    assert result["summary"]["cost_basis"] == "COST_WITH_CONTINGENCY"
    assert snapshot == before


@pytest.mark.parametrize(
    "mutation,code",
    [
        ("empty_policy", "ENGINE_CONFIGURATION_NOT_READY"),
        ("version", "ENGINE_VERSION_NOT_SUPPORTED"),
        ("percentiles", "ENGINE_PERCENTILE_POLICY_INVALID"),
        ("currency", "COST_CURRENCY_OR_UNIT_MISMATCH"),
        ("basis", "COST_BASIS_NOT_EXPLICIT"),
        ("seed", "ENGINE_SEED_INVALID"),
        ("iterations", "ENGINE_ITERATIONS_INVALID"),
    ],
)
def test_governed_policy_and_currency_validation(mutation, code):
    snapshot = cost_snapshot()
    if mutation == "empty_policy":
        snapshot["policy"] = {}
    elif mutation == "version":
        snapshot["policy"]["engine_version"] = "future"
    elif mutation == "percentiles":
        snapshot["policy"]["percentiles"] = [80, 80]
    elif mutation == "currency":
        snapshot["inputs"][0]["unit"] = "COP"
    elif mutation == "basis":
        snapshot["cost"]["basis"] = "UNKNOWN"
    with pytest.raises(EngineCalculationError, match=code):
        calculate(snapshot, -1 if mutation == "seed" else 3, 1 if mutation == "iterations" else 1000)
