"""Pure deterministic reporting proof, independent of database authority writers."""

from copy import deepcopy
from datetime import date
from decimal import Decimal

import pytest

from app.modules.forecast_foundation.reporting_policy import (
    business_date,
    cumulative_series,
    dashboard_indicators,
    finish_variance,
    forecast_phase_points,
    latest_report_revisions,
    lookahead_projection,
    narrative_sections,
    near_critical,
    number,
    package_activity_context,
    package_dependency_context,
    physical_progress_variance,
    readiness_rollup,
    snapshot_series,
    trend_series,
)
from app.modules.forecast_foundation.reporting_schemas import LookAheadIn, ReportPublishIn


def activity(identity="A1", **values):
    return {
        "external_id": identity,
        "wbs_external_id": "W2",
        "status": "Not Started",
        "activity_type": "Task Dependent",
        "planned_start": "2026-11-10",
        "planned_finish": "2026-11-12",
        "finish": "2026-11-12",
        "critical": True,
        "total_float": "12",
        "float_unit": "HOUR",
        **values,
    }


WBS = [{"external_id": "W1", "parent_external_id": ""}, {"external_id": "W2", "parent_external_id": "W1"}]


def physical_basis():
    baseline = {
        "id": 10,
        "content_hash": "approved-budget-hash",
        "snapshot_json": {"lines": [{"id": 20, "amount": "100", "currency": "USD", "cost_class": "DIRECT"}]},
    }
    group = {
        "status": "COMPUTABLE",
        "weighting_basis": "BUDGET",
        "progress_value": "50",
        "total_weight": "100",
        "input_ids": [30],
    }
    measurement = {
        "id": 30,
        "status": "APPROVED",
        "progress_type": "PHYSICAL",
        "weighting_basis": "BUDGET",
        "weight": "100",
        "progress_value": "50",
        "source_snapshot": {
            "weight_source": {
                "authority": "APPROVED_COST_BASELINE",
                "cost_baseline_id": 10,
                "cost_baseline_hash": "approved-budget-hash",
                "line_ids": [20],
                "currency": "USD",
                "weight": "100",
            }
        },
    }
    return baseline, {"items": [group]}, [measurement]


def test_physical_variance_requires_matched_disjoint_complete_budget_weighted_authorities():
    baseline, projection, measurements = physical_basis()
    result = physical_progress_variance(baseline, projection, measurements, pv="40", bac="100", currency="USD")
    assert result["status"] == "COMPUTABLE"
    assert Decimal(result["planned_progress"]) == 40
    assert Decimal(result["physical_variance"]) == 10
    assert result["unit"] == "PERCENTAGE_POINT"
    assert result["measurement_ids"] == [30]


@pytest.mark.parametrize(
    "change", ["manual", "currency", "hash", "partial", "overlap", "weight", "missing", "pv", "stale", "aggregate"]
)
def test_physical_variance_does_not_compare_incompatible_percentages(change):
    baseline, projection, measurements = physical_basis()
    kwargs = {"pv": "40", "bac": "100", "currency": "USD"}
    if change == "manual":
        projection["items"][0]["weighting_basis"] = "MANUAL_APPROVED_WEIGHT"
    elif change == "currency":
        measurements[0]["source_snapshot"]["weight_source"]["currency"] = "COP"
    elif change == "hash":
        measurements[0]["source_snapshot"]["weight_source"]["cost_baseline_hash"] = "other"
    elif change == "partial":
        baseline["snapshot_json"]["lines"].append({"id": 21, "amount": "10", "currency": "USD"})
        kwargs["bac"] = "110"
    elif change == "overlap":
        measurements.append(deepcopy(measurements[0]) | {"id": 31})
        projection["items"][0]["input_ids"].append(31)
    elif change == "weight":
        measurements[0]["weight"] = "99"
    elif change == "missing":
        measurements = []
    elif change == "pv":
        kwargs["pv"] = None
    elif change == "stale":
        measurements[0]["status"] = "REJECTED"
    elif change == "aggregate":
        projection["items"][0]["progress_value"] = "60"
    result = physical_progress_variance(baseline, projection, measurements, **kwargs)
    assert result["status"] == "NOT_COMPUTABLE"
    assert result["physical_variance"] is None and result["planned_progress"] is None


def trend_point(identity, **changes):
    return {
        "id": identity,
        "period_id": identity,
        "as_of": f"2026-11-{identity:02d}",
        "content_hash": str(identity),
        "forecast_version_id": identity,
        "currency": "USD",
        "metrics": {
            "eac": "100",
            "physical_progress": "50",
            "cpi": "1",
            "readiness": "0",
            "forecast_finish": "2026-12-01",
            "open_constraints": 2,
        },
        "source_refs": {"bundle": {"id": 10, "hash": "approved-bundle"}, "cost_period_snapshot": {"baseline_id": 20}},
        **changes,
    }


def test_trend_points_keep_explicit_units_currency_and_immutable_control_basis():
    rows = [trend_point(1), trend_point(2)]
    before = deepcopy(rows)
    series = trend_series(rows, ("eac", "physical_progress", "cpi", "readiness", "forecast_finish", "open_constraints"))
    assert [row["unit"] for row in series] == ["MONEY", "%", "RATIO", "%", "DATE", "COUNT"]
    assert all(row["status"] == "COMPUTABLE" and len(row["points"]) == 2 for row in series)
    assert series[0]["currency"] == "USD" and series[1]["currency"] is None
    assert series[0]["points"][1]["basis"]["cost_baseline_id"] == 20
    assert all(point["source_hash"] for row in series for point in row["points"])
    assert rows == before


@pytest.mark.parametrize("change", ["currency", "missing_currency", "bundle", "missing_value"])
def test_trends_do_not_connect_mixed_currencies_or_control_bases(change):
    first, second = trend_point(1), trend_point(2)
    if change == "currency":
        second["currency"] = "COP"
    elif change == "missing_currency":
        second["currency"] = None
    elif change == "bundle":
        second["source_refs"]["bundle"] = {"id": 11, "hash": "successor-bundle"}
    else:
        second["metrics"]["eac"] = None
    series = trend_series([first, second], ("eac",))[0]
    assert series["status"] == "NOT_COMPUTABLE"
    assert series["points"] == [] and len(series["not_computable_points"]) == 2
    assert series["reason_codes"]


def test_package_context_joins_only_explicit_activity_plan_scope_identities_and_preserves_phases():
    mappings = [
        {
            "id": 1,
            "work_package_id": 20,
            "target_kind": "PLAN",
            "target_id": 11,
            "phase": "INSTALL",
            "status": "ACTIVE",
        },
        {
            "id": 2,
            "work_package_id": 21,
            "target_kind": "SCOPE",
            "target_id": 12,
            "phase": "REMOVE",
            "status": "ACTIVE",
        },
        {
            "id": 3,
            "work_package_id": 22,
            "target_kind": "ACTIVITY",
            "activity_external_id": "A1",
            "schedule_version_id": 13,
            "phase": "INSTALL",
            "status": "ACTIVE",
        },
        {
            "id": 4,
            "work_package_id": 23,
            "target_kind": "PLAN",
            "target_id": 99,
            "phase": "INSTALL",
            "status": "ACTIVE",
        },
        {
            "id": 5,
            "work_package_id": 24,
            "target_kind": "ACTIVITY",
            "activity_external_id": "A1",
            "schedule_version_id": 14,
            "phase": "INSTALL",
            "status": "ACTIVE",
        },
        {
            "id": 6,
            "work_package_id": 25,
            "target_kind": "SCOPE",
            "target_id": 12,
            "phase": "INSTALL",
            "status": "ACTIVE",
            "mapping_health": "STALE",
        },
    ]
    before = deepcopy(mappings)
    result = package_activity_context(
        mappings, plan_ids={11}, scope_ids={12}, schedule_version_id=13, activity_external_id="A1"
    )
    assert result["work_package_ids"] == [20, 21, 22]
    assert {row["via"] for row in result["proofs"]} == {"DIRECT_ACTIVITY", "SHARED_PLAN_ID", "SHARED_SCOPE_ID"}
    assert {row["phase"] for row in result["proofs"]} == {"INSTALL", "REMOVE"}
    assert result["ambiguous_context"] is True
    assert result["quantity_allocation_inferred"] is False and result["execution_phase_inferred"] is False
    assert mappings == before


@pytest.mark.parametrize(
    "points",
    [
        "bad",
        [None],
        ["bad"],
        [{"date": "bad", "amount": "2"}],
        [{"date": "2026-11-01", "amount": "bad"}],
        [{"date": "2026-11-01", "amount": "NaN"}],
        [{"date": "2026-11-01", "amount": "1e30"}],
        [{"date": "2026-11-01", "amount": "1e1000000000"}],
        [{"date": "2026-11-01", "amount": "-2"}],
    ],
)
def test_malformed_draft_forecast_phasing_is_not_computable_instead_of_exception(points):
    components = [{"id": 1, "amount": "2", "currency": "USD", "phasing": points}]
    before = deepcopy(components)
    usable, reasons = forecast_phase_points(components, as_of="2026-10-22", currency="USD")
    assert usable == [] and reasons
    assert components == before


def test_forecast_phasing_normalizes_valid_dates_and_keeps_frozen_component_refs():
    components = [
        {
            "id": 1,
            "content_hash": "frozen-component",
            "amount": "2",
            "currency": "USD",
            "phasing": [{"date": "2026-11-01", "amount": "2"}],
        }
    ]
    points, reasons = forecast_phase_points(components, as_of="2026-10-22", currency="USD")
    assert reasons == [] and points[0]["date"] == "2026-11-01"
    assert points[0]["value"] == 2 and points[0]["currency"] == "USD"
    assert points[0]["source_refs"][0]["hash"] == "frozen-component"


def test_dashboard_thresholds_keep_units_and_unknowns_without_zero_filling():
    indicators = dashboard_indicators(
        {"cpi": "0.91", "spi": None, "finish_variance_days": 3},
        {"cpi_warning": "0.92", "spi_warning": "1.04", "finish_variance_warning_days": 3},
    )
    assert [(item["status"], item["unit"], item["warning_when"]) for item in indicators] == [
        ("WARNING", "RATIO", "BELOW"),
        ("NOT_COMPUTABLE", "RATIO", "BELOW"),
        ("WITHIN_THRESHOLD", "CALENDAR_DAY", "ABOVE"),
    ]
    assert indicators[1]["value"] is None and indicators[1]["reason_codes"]


def test_readiness_rollup_distinguishes_assessed_not_ready_from_no_evidence():
    packages = [{"id": 1}, {"id": 2}]
    states = {
        "1": {"assessment_id": 9, "readiness_state": "READY", "stale": False},
        "2": {"assessment_id": 8, "readiness_state": "NOT_READY", "stale": False},
    }
    assert readiness_rollup(packages, states)["readiness_percent"] == "50.00000000"
    states["2"]["stale"] = True
    partial = readiness_rollup(packages, states)
    assert partial["status"] == "NOT_COMPUTABLE" and partial["readiness_percent"] is None
    assert partial["ready_count"] == 1 and partial["stale_or_unassessed_count"] == 1
    empty = readiness_rollup(packages, {})
    assert empty["readiness_percent"] is None and empty["state_counts"] == {"UNKNOWN": 2}


def lookahead(rows, **kwargs):
    return lookahead_projection(rows, WBS, [], as_of=date(2026, 11, 6), **kwargs)


@pytest.mark.parametrize("value", [None, True, False, "NaN", "Infinity", "x"])
def test_reporting_numeric_source_rejects_missing_boolean_nonfinite(value):
    with pytest.raises(ValueError, match="REPORT_NUMERIC_BASIS_REQUIRED"):
        number(value)


def test_reporting_decimal_zero_and_negative_adjustment_preserved():
    assert number("0") == Decimal("0")
    assert number("-1.25") == Decimal("-1.25")


def test_reporting_business_date_preserves_calendar_day_without_timezone_conversion():
    assert business_date("2026-11-06T23:59:00-05:00") == date(2026, 11, 6)
    assert business_date(None) is None
    assert finish_variance("2026-11-06", "2026-11-10") == 4
    assert finish_variance("2026-11-06", None) is None


@pytest.mark.parametrize("value", ["not-date", "2026-13-05"])
def test_reporting_invalid_source_date_is_not_replaced_by_today(value):
    with pytest.raises(ValueError, match="REPORT_SOURCE_DATE_INVALID"):
        business_date(value)


def test_lookahead_default_four_weeks_includes_boundary_not_completed():
    result = lookahead(
        [
            activity("A1"),
            activity("A2", planned_start="2026-12-04"),
            activity("A3", planned_start="2026-12-05"),
            activity("A4", actual_finish="2026-11-05"),
        ]
    )
    assert result["horizon_days"] == 28
    assert result["horizon_end"] == "2026-12-04"
    assert [r["external_id"] for r in result["items"]] == ["A1", "A2"]
    assert result["authority"]["cpm_calculation_performed"] is False


def test_lookahead_in_progress_overlaps_horizon_even_when_started_before():
    row = activity(status="In Progress", actual_start="2026-10-01", planned_start="2026-10-01")
    result = lookahead([row])
    assert result["items"][0]["selection_reason"] == "IN_PROGRESS"


def test_lookahead_overdue_blocked_work_is_visible_and_explicit():
    result = lookahead([activity(planned_start="2026-10-01", finish="2026-10-15", blocking_constraint_ids=[7])])
    assert result["items"][0]["overdue"] is True
    assert result["items"][0]["selection_reason"] == "OVERDUE"
    assert lookahead([activity(planned_start="2026-10-01")], include_overdue=False)["items"] == []


def test_lookahead_unknown_date_blocker_is_not_silently_hidden():
    result = lookahead([activity(planned_start=None, start=None, blocking_constraint_ids=[7])])
    assert result["items"][0]["selection_reason"] == "BLOCKED_WITH_UNKNOWN_DATES"


def test_lookahead_keeps_explicit_awp_dependency_blockers_separate_from_cpm():
    dependencies = [
        {"id": 3, "predecessor_package_id": 1, "successor_package_id": 2, "status": "ACTIVE", "blocking": True},
        {"id": 4, "predecessor_package_id": 5, "successor_package_id": 2, "status": "ACTIVE", "blocking": True},
        {"id": 5, "predecessor_package_id": 1, "successor_package_id": 6, "status": "ACTIVE", "blocking": True},
    ]
    before = deepcopy(dependencies)
    context = package_dependency_context(dependencies, {1: {"status": "OPEN"}, 5: {"status": "CLOSED"}}, {2})
    assert [row["id"] for row in context["items"]] == [3, 4]
    assert context["blocking_ids"] == [3]
    result = lookahead([activity(planned_start=None, start=None, blocking_dependency_ids=context["blocking_ids"])])
    assert result["items"][0]["selection_reason"] == "BLOCKED_WITH_UNKNOWN_DATES"
    assert result["items"][0]["driving_predecessor"]["state"] == "UNKNOWN"
    assert dependencies == before


def test_lookahead_custom_horizon_changes_selection_without_source_mutation():
    rows = [activity("A1"), activity("A2", planned_start="2026-12-02")]
    original = deepcopy(rows)
    assert len(lookahead(rows, horizon_days=7)["items"]) == 1
    assert len(lookahead(rows, horizon_days=28)["items"]) == 2
    assert rows == original


@pytest.mark.parametrize(
    "kwargs",
    [
        {"horizon_days": 0},
        {"horizon_days": 367},
        {"group_by": "UNKNOWN"},
        {"top_n": 0},
        {"near_critical_unit": "UNKNOWN"},
        {"near_critical_value": "-1"},
    ],
)
def test_lookahead_invalid_policy_inputs_fail_explicitly(kwargs):
    with pytest.raises(ValueError):
        lookahead([activity()], **kwargs)


def test_lookahead_critical_not_inferred_from_float():
    rows = [
        activity("A1", critical=None, total_float="0"),
        activity("A2", critical=False, total_float="0"),
        activity("A3", critical=True, total_float="99"),
    ]
    result = lookahead(rows, critical_only=True)
    assert [r["external_id"] for r in result["items"]] == ["A3"]
    assert near_critical(rows[0], "40", "HOUR") is True
    assert near_critical(rows[0], "5", "DAY") == "UNKNOWN"


def test_lookahead_no_implicit_hours_to_day_conversion():
    result = lookahead(
        [activity(total_float="8", float_unit="HOUR")], near_critical_value="1", near_critical_unit="DAY"
    )
    assert result["items"][0]["near_critical"] == "UNKNOWN"


def test_lookahead_pure_milestones_separate_from_ranked_activities():
    result = lookahead([activity("A1"), activity("M1", activity_type="Finish Milestone")])
    assert len(result["items"]) == len(result["milestones"]) == 1
    assert len(lookahead([activity("M1", activity_type="Start Milestone")], exclude_milestones=False)["items"]) == 1


@pytest.mark.parametrize(
    "group,key,extra",
    [
        ("PARENT_WBS", "W1", {}),
        ("PACKAGE", "8", {"work_package_ids": [8]}),
        ("CWA", "9", {"cwa_ids": [9]}),
        ("AREA", "A", {"areas": ["A"]}),
        ("ZONE", "Z", {"zones": ["Z"]}),
        ("SYSTEM", "S", {"systems": ["S"]}),
        ("DISCIPLINE", "CIVIL", {"disciplines": ["CIVIL"]}),
    ],
)
def test_lookahead_all_configurable_groupings_preserve_unique_activity_membership(group, key, extra):
    result = lookahead([activity(**extra)], group_by=group)
    assert result["groups"] == [{"key": key, "activity_ids": ["A1"], "activity_count": 1}]


def test_lookahead_wbs_descendant_and_package_filters_are_scoped_not_name_matching():
    rows = [activity("A1", work_package_ids=[8]), activity("A2", work_package_ids=[9])]
    assert len(lookahead(rows, wbs_external_id="W1", work_package_id=8)["items"]) == 1
    assert lookahead(rows, wbs_external_id="OTHER")["items"] == []


def test_lookahead_top_n_is_explicit_and_keeps_blocked_work_priority():
    result = lookahead([activity("A1"), activity("A2", critical=False, blocking_constraint_ids=[9])], top_n=1)
    assert result["total_before_limit"] == 2 and result["truncated"] is True
    assert result["items"][0]["external_id"] == "A2"


def test_lookahead_predecessor_relationship_does_not_imply_driving_path():
    relation = {
        "external_id": "R1",
        "predecessor_external_id": "A1",
        "successor_external_id": "A2",
        "relationship_type": "FS",
        "lag": "8",
        "lag_unit": "HOUR",
    }
    rows = [activity("A1"), activity("A2")]
    result = lookahead_projection(rows, WBS, [relation], as_of="2026-11-06")
    driver = result["items"][1]["driving_predecessor"]
    assert driver["state"] == "UNKNOWN" and driver["drivers"] == []
    assert driver["predecessors"][0]["lag_unit"] == "HOUR"
    relation["source_fields"] = {"IsDriving": "true"}
    result = lookahead_projection(rows, WBS, [relation], as_of="2026-11-06")
    assert result["items"][1]["driving_predecessor"]["state"] == "IMPORTED"


def test_lookahead_cyclic_wbs_filter_is_bounded_without_cpm_path_calculation():
    wbs = [{"external_id": "W2", "parent_external_id": "W3"}, {"external_id": "W3", "parent_external_id": "W2"}]
    result = lookahead_projection([activity()], wbs, [], as_of="2026-11-06", wbs_external_id="UNKNOWN")
    assert result["items"] == []


def test_actual_cost_curve_sums_recognized_period_amounts_not_balances():
    result = cumulative_series(
        [
            {"date": "2026-11-01", "value": "25"},
            {"date": "2026-11-02", "value": "15"},
            {"date": "2026-11-02", "value": "-5"},
        ],
        code="ACTUAL_COST",
        unit="MONEY",
        currency="USD",
        basis="RECOGNIZED",
    )
    assert result["status"] == "COMPUTABLE"
    assert result["points"][-1]["period_value"] == "10.00000000"
    assert result["points"][-1]["cumulative_value"] == "35.00000000"


@pytest.mark.parametrize("point", [{"unit": "HOUR"}, {"currency": "COP"}])
def test_curves_never_mix_incompatible_units_or_currencies(point):
    result = cumulative_series(
        [{"date": "2026-11-01", "value": "25", **point}], code="COST", unit="MONEY", currency="USD", basis="APPROVED"
    )
    assert result["status"] == "NOT_COMPUTABLE"
    assert result["reason_codes"] == ["SERIES_UNIT_CURRENCY_MISMATCH"]
    assert result["points"] == []


def test_snapshot_physical_percentages_and_earned_balances_are_not_added_across_periods():
    result = snapshot_series(
        [{"date": "2026-10-31", "value": "35"}, {"date": "2026-11-06", "value": "60"}],
        code="PHYSICAL",
        unit="%",
        basis="APPROVED",
    )
    assert result["points"][-1]["cumulative_value"] == "60.00000000"
    assert result["points"][-1]["period_value"] is None


@pytest.mark.parametrize("method", [cumulative_series, snapshot_series])
def test_missing_curve_source_not_replaced_with_healthy_zero(method):
    result = method([], code="COST", unit="MONEY", currency="USD", basis="APPROVED")
    assert result["status"] == "NOT_COMPUTABLE"
    assert result["reason_codes"] == ["SERIES_SOURCE_REQUIRED"]


def test_snapshot_curve_duplicate_dates_are_explicitly_ambiguous():
    result = snapshot_series(
        [{"date": "2026-11-06", "value": "35"}, {"date": "2026-11-06", "value": "60"}],
        code="PHYSICAL",
        unit="%",
        basis="APPROVED",
    )
    assert result["status"] == "NOT_COMPUTABLE" and result["points"] == []


def test_trend_republish_selects_latest_revision_not_sum_and_preserves_input():
    rows = [
        {"id": 1, "period_id": 7, "as_of": "2026-10-31", "revision": 1, "status": "PUBLISHED", "eac": "100"},
        {"id": 2, "period_id": 7, "as_of": "2026-10-31", "revision": 2, "status": "PUBLISHED", "eac": "110"},
        {"id": 3, "period_id": 8, "as_of": "2026-11-06", "revision": 1, "status": "PUBLISHED", "eac": "120"},
    ]
    original = deepcopy(rows)
    result = latest_report_revisions(rows)
    assert [r["eac"] for r in result] == ["110", "120"]
    assert rows == original


def test_trend_reopened_period_family_uses_successor_without_duplicate_period_point():
    rows = [
        {"id": 1, "period_id": 7, "as_of": "2026-10-31", "revision": 9, "period_revision": 1, "status": "PUBLISHED"},
        {"id": 2, "period_id": 8, "as_of": "2026-10-31", "revision": 1, "period_revision": 2, "status": "PUBLISHED"},
    ]
    assert [r["id"] for r in latest_report_revisions(rows, {7: 7, 8: 7})] == [2]


def test_trend_unpublished_rows_do_not_become_history_proof():
    assert latest_report_revisions([{"id": 1, "period_id": 7, "as_of": "2026-10-31", "status": "DRAFT"}]) == []


def test_report_narratives_cite_internal_governed_fact_locators():
    result = narrative_sections(
        {"eac": "100", "forecast_finish": "2026-12-01"},
        {"forecast": {"id": 1}, "cost_period_snapshot": {"content_hash": "abc"}},
    )
    assert result[0]["fact_references"] == ["forecast", "cost"]
    assert "100" in result[0]["text"]
    assert all("statistical" not in r["text"].lower() for r in result)


def test_report_and_lookahead_commands_reject_extra_fields():
    with pytest.raises(ValueError):
        ReportPublishIn(
            forecast_version_id=1, reason="Publish controlled snapshot", evidence_reference="UAT", status="PUBLISHED"
        )
    with pytest.raises(ValueError):
        LookAheadIn(forecast_version_id=1, cpm_recalculate=True)
