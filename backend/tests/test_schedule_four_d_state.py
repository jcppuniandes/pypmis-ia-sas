"""Pure 4D semantic tests do not certify PostgreSQL/API/browser release gates."""

from copy import deepcopy

import pytest

from app.modules.schedule_four_d.service import DEFAULT_PROFILE, FourDService
from app.modules.schedule_four_d.state import activity_dates, compare_states, instant, near_critical, resolve_state


def activity(start="2026-10-21T08:00:00", finish="2026-10-23T08:00:00", phase="EXECUTE", **fields):
    return {"external_id": "1001", "planned_start": start, "planned_finish": finish, "phase": phase, **fields}


@pytest.mark.parametrize(
    "nature,at,state,semantic,visible",
    [
        ("INSTALL", "2026-10-20", "NOT_STARTED", "FUTURE_NOT_INSTALLED", False),
        ("INSTALL", "2026-10-22", "IN_PROGRESS", "INSTALLATION", True),
        ("INSTALL", "2026-10-24", "COMPLETED", "INSTALLED", True),
        ("REMOVE", "2026-10-20", "NOT_STARTED", "EXISTING", True),
        ("REMOVE", "2026-10-22", "IN_PROGRESS", "REMOVAL", True),
        ("REMOVE", "2026-10-24", "REMOVED", "REMOVED", False),
        ("MAINTENANCE", "2026-10-20", "NOT_STARTED", "EXISTING_IN_SERVICE", True),
        ("MAINTENANCE", "2026-10-22", "MAINTENANCE", "MAINTENANCE_INTERVENTION", True),
        ("MAINTENANCE", "2026-10-24", "COMPLETED", "RESTORED_IN_SERVICE", True),
    ],
)
def test_all_non_temporary_nature_states(nature, at, state, semantic, visible):
    result = resolve_state(nature, [activity()], at)
    assert (result["state"], result["semantic_state"], result["visible"]) == (state, semantic, visible)
    assert not result["mapping_issues"]


def temporary():
    return [
        activity("2026-10-01", "2026-10-03", "INSTALL"),
        activity("2026-10-03", "2026-10-10", "USE", external_id="1002"),
        activity("2026-10-10", "2026-10-12", "REMOVE", external_id="1003"),
    ]


@pytest.mark.parametrize(
    "at,state,semantic,visible",
    [
        ("2026-09-30", "NOT_STARTED", "ABSENT_BEFORE_INSTALL", False),
        ("2026-10-01", "IN_PROGRESS", "TEMPORARY_INSTALLATION", True),
        ("2026-10-03", "TEMPORARY", "TEMPORARY_IN_USE", True),
        ("2026-10-09", "TEMPORARY", "TEMPORARY_IN_USE", True),
        ("2026-10-10", "IN_PROGRESS", "TEMPORARY_REMOVAL", True),
        ("2026-10-12", "REMOVED", "ABSENT_AFTER_REMOVAL", False),
    ],
)
def test_temporary_explicit_multi_activity_boundaries(at, state, semantic, visible):
    result = resolve_state("TEMPORARY", temporary(), at)
    assert (result["state"], result["semantic_state"], result["visible"]) == (state, semantic, visible)
    assert not result["mapping_issues"]


@pytest.mark.parametrize(
    "activities,issue",
    [
        ([activity()], "TEMPORARY_INSTALL_REMOVE_PHASES_REQUIRED"),
        (temporary() + [activity()], "TEMPORARY_EXPLICIT_PHASE_REQUIRED"),
        (
            [activity("2026-10-10", "2026-10-15", "INSTALL"), activity("2026-10-01", "2026-10-02", "REMOVE")],
            "TEMPORARY_PHASE_ORDER_INVALID",
        ),
    ],
)
def test_temporary_never_guesses_names_or_missing_phases(activities, issue):
    result = resolve_state("TEMPORARY", activities, "2026-10-11")
    assert result["state"] == "UNKNOWN" and issue in result["mapping_issues"]


@pytest.mark.parametrize(
    "activities,issue",
    [
        ([], "ACTIVITY_MAPPING_REQUIRED"),
        ([activity(None, None)], "ACTIVITY_DATES_INCOMPLETE"),
        ([activity("bad", "bad")], "ACTIVITY_DATES_INCOMPLETE"),
        ([activity("2026-11-10", "2026-10-10")], "ACTIVITY_DATE_ORDER_INVALID"),
        ([activity(phase="INVENTED")], "ACTIVITY_PHASE_INVALID"),
    ],
)
def test_missing_broken_date_or_phase_is_not_healthy_completion(activities, issue):
    result = resolve_state("INSTALL", activities, "2026-10-25")
    assert result["state"] == "UNKNOWN" and issue in result["mapping_issues"]


def test_many_activities_resolve_membership_envelope_without_creating_dates():
    data = [activity("2026-10-01", "2026-10-03"), activity("2026-10-06", "2026-10-09", external_id="2002")]
    original = deepcopy(data)
    assert resolve_state("INSTALL", data, "2026-10-05")["state"] == "IN_PROGRESS"
    assert resolve_state("INSTALL", data, "2026-10-10")["state"] == "COMPLETED"
    assert data == original


def test_actual_dates_current_and_planned_baseline_are_distinct_sources():
    data = [activity(actual_start="2026-10-25", actual_finish="2026-10-26")]
    assert resolve_state("INSTALL", data, "2026-10-24", baseline=True)["state"] == "COMPLETED"
    assert resolve_state("INSTALL", data, "2026-10-24")["state"] == "NOT_STARTED"


def test_imported_critical_float_remain_unknown_when_not_supplied():
    threshold = {"unit": "HOUR", "value": 40}
    assert near_critical(activity(total_float=None, float_unit="HOUR"), threshold) is None
    assert near_critical(activity(total_float=1, float_unit="DAY"), threshold) is None
    assert near_critical(activity(total_float=0, float_unit="HOUR"), threshold) is True
    assert near_critical(activity(total_float=41, float_unit="HOUR"), threshold) is False
    result = resolve_state(
        "INSTALL", [activity(total_float=0, float_unit="HOUR", critical=None)], "2026-10-22", threshold=threshold
    )
    assert "NEAR_CRITICAL" in result["visual_classes"] and "CRITICAL" not in result["visual_classes"]


def test_scheduled_readiness_overlay_does_not_modify_schedule_state_or_logic():
    data = [activity(critical=True, total_float=-1, float_unit="HOUR")]
    original = deepcopy(data)
    result = resolve_state("INSTALL", data, "2026-10-22", blocked=True)
    assert result["state"] == "IN_PROGRESS" and "BLOCKED_BY_READINESS" in result["visual_classes"]
    assert data == original


def test_registered_timezone_not_machine_today_or_implicit_utc():
    assert instant("2026-10-21T08:00:00", "America/Bogota").isoformat() == "2026-10-21T13:00:00+00:00"
    result = resolve_state("INSTALL", [activity()], "2026-10-21T12:00:00Z", timezone_name="America/Bogota")
    assert result["state"] == "NOT_STARTED"


@pytest.mark.parametrize("status", ["Not Started", "NOT_STARTED", "In Progress", "IN_PROGRESS"])
def test_delayed_overlay_only_explicit_data_date_and_known_imported_status(status):
    data = [activity(status=status)]
    result = resolve_state("INSTALL", data, "2026-10-24T00:00:00Z", data_date="2026-10-24")
    assert "DELAYED" in result["visual_classes"]
    assert "DELAYED" not in resolve_state("INSTALL", data, "2026-10-25", data_date="2026-10-24")["visual_classes"]
    assert (
        "DELAYED"
        not in resolve_state("INSTALL", data, "2026-10-24", data_date="2026-10-24", baseline=True)["visual_classes"]
    )


def test_unknown_completed_status_or_actual_finish_never_invents_late_flag():
    for data in (
        [activity(status="UNKNOWN")],
        [activity(status="Completed")],
        [activity(status="In Progress", actual_finish="2026-10-23")],
    ):
        assert "DELAYED" not in resolve_state("INSTALL", data, "2026-10-24", data_date="2026-10-24")["visual_classes"]


def test_milestone_one_declared_date_is_valid_without_duration_calculation():
    start, finish = activity_dates(activity(finish=None, activity_type="Start Milestone"))
    assert start == finish
    assert (
        resolve_state("INSTALL", [activity(finish=None, activity_type="Start Milestone")], "2026-10-22")["state"]
        == "COMPLETED"
    )


@pytest.mark.parametrize(
    "previous,following,expected",
    [
        ("2026-10-20", "2026-10-20", "ALIGNED"),
        ("2026-10-24", "2026-10-20", "BEHIND_BASELINE"),
        ("2026-10-20", "2026-10-24", "AHEAD_OF_BASELINE"),
    ],
)
def test_semantic_comparison_no_forecast_cpm(previous, following, expected):
    baseline = resolve_state("INSTALL", [activity()], previous)
    current = resolve_state("INSTALL", [activity()], following)
    assert compare_states(baseline, current) == expected


def test_comparison_unresolved_or_missing_source_explicit():
    known = resolve_state("INSTALL", [activity()], "2026-10-22")
    unknown = resolve_state("INSTALL", [], "2026-10-22")
    assert compare_states(known, unknown) == "UNRESOLVED"
    assert compare_states(None, known) == "ADDED_TO_CURRENT"
    assert compare_states(known, None) == "ABSENT_FROM_CURRENT"


def test_profile_permits_presentation_but_not_rewriting_scope_semantics():
    service = FourDService(None, 1, 1)
    service._validate_profile(deepcopy(DEFAULT_PROFILE))
    content = deepcopy(DEFAULT_PROFILE)
    content["display"]["INSTALL"] = {"color": "#ffffff", "opacity": 1}
    with pytest.raises(Exception) as error:
        service._validate_profile(content)
    assert error.value.status_code == 422
    content = deepcopy(DEFAULT_PROFILE)
    content["state_rules"]["REMOVE"] = ["INSTALLED"]
    with pytest.raises(Exception) as error:
        service._validate_profile(content)
    assert error.value.status_code == 422


@pytest.mark.parametrize(
    "field,value",
    [
        ("mapping_completeness_policy", "IGNORE"),
        ("temporary_phase_policy", "GUESS_NAME"),
        ("separation_of_duties", {"author_cannot_publish": False}),
        ("allow_direct_scope_mapping", "yes"),
    ],
)
def test_profile_invalid_authority_flags_rejected(field, value):
    content = deepcopy(DEFAULT_PROFILE)
    content[field] = value
    with pytest.raises(Exception) as error:
        FourDService(None, 1, 1)._validate_profile(content)
    assert error.value.status_code == 422


def test_filter_contract_supports_every_required_dimension_without_mutation():
    item = {
        "scope_item_id": 1,
        "scope_nature": "INSTALL",
        "plan_item_id": 2,
        "area": "A",
        "zone": "Z",
        "system": "S",
        "blocked": True,
        "activities": [{"external_id": "1001", "status": "Not Started", "critical": True, "near_critical": False}],
        "wbs": [{"external_id": "101"}],
        "cwas": [{"id": 4}],
        "packages": [{"id": 3, "package_type": "IWP"}],
        "readiness": [{"readiness_state": "NOT_READY"}],
    }
    filters = {
        "scope_item_id": 1,
        "scope_nature": "INSTALL",
        "plan_item_id": 2,
        "area": "A",
        "zone": "Z",
        "system": "S",
        "blocked": True,
        "activity": "1001",
        "wbs": "101",
        "cwa_id": 4,
        "work_package_id": 3,
        "package_type": "IWP",
        "activity_status": "Not Started",
        "critical": True,
        "near_critical": False,
        "execution_readiness": "NOT_READY",
    }
    assert FourDService._matches(item, filters)
    for key in filters:
        assert not FourDService._matches(item, {key: "missing"})


def test_wbs_filter_membership_includes_source_ancestors_without_tree_rewrite():
    index = {
        "1": {"external_id": "1", "parent_external_id": None},
        "2": {"external_id": "2", "parent_external_id": "1"},
    }
    original = deepcopy(index)
    result = FourDService._wbs_memberships(index, [{"wbs_external_id": "2"}])
    assert {row["external_id"] for row in result} == {"1", "2"}
    assert index == original
