"""Pure execution policy boundaries; no Schedule or date arithmetic."""

from copy import deepcopy

import pytest

from app.modules.awp.policy import DEFAULT_PROFILE, DIMENSIONS, PACKAGE_TYPES, assess_policy, has_cycle
from app.modules.awp.schemas import ConstraintIn, MappingIn, PackageIn


def assessment(kind="IWP", **changes):
    arguments = {
        "package_type": kind,
        "policy": deepcopy(DEFAULT_PROFILE),
        "constraints": [],
        "dependencies": [],
        "evidence": dict.fromkeys(DIMENSIONS, "DOC-APPROVED"),
        "has_scope": True,
        "has_activity": True,
    }
    arguments.update(changes)
    return assess_policy(**arguments)


@pytest.mark.parametrize("kind", PACKAGE_TYPES)
def test_tailored_types_are_ready_without_auto_release(kind):
    assert assessment(kind)["readiness_state"] == "READY"


@pytest.mark.parametrize("status", ["OPEN", "IN_PROGRESS"])
def test_due_date_never_clears_blocker(status):
    result = assessment(
        constraints=[
            {"id": 1, "status": status, "blocking": True, "constraint_type": "ACCESS", "due_date": "2000-01-01"}
        ]
    )
    assert result["readiness_state"] == "NOT_READY"
    assert result["blocking_constraints"] == [1]


@pytest.mark.parametrize("status", ["CLEARED", "WAIVED", "CANCELLED"])
def test_resolved_constraint_no_longer_blocks(status):
    assert (
        assessment(constraints=[{"id": 1, "status": status, "blocking": True, "constraint_type": "HSE"}])[
            "readiness_state"
        ]
        == "READY"
    )


def test_nonblocking_is_visible_without_false_block():
    result = assessment(constraints=[{"id": 2, "status": "OPEN", "blocking": False, "constraint_type": "ENGINEERING"}])
    assert result["readiness_state"] == "READY"
    assert result["open_nonblocking_constraints"] == [2]


def test_missing_mandatory_evidence_is_not_ready():
    result = assessment(evidence={})
    assert result["readiness_state"] == "PARTIALLY_READY"
    assert set(result["evidence_state"]["missing_dimensions"]) == {"ENGINEERING", "MATERIAL", "ACCESS", "HSE"}


def test_dependency_is_execution_not_cpm():
    result = assessment(
        dependencies=[{"id": 5, "status": "ACTIVE", "blocking": True, "predecessor_status": "RELEASED"}]
    )
    assert result["readiness_state"] == "NOT_READY"
    assert result["dependency_state"]["blocking_ids"] == [5]


def test_no_scope_mapping_blocks_and_profile_can_require_activity():
    assert assessment(has_scope=False)["readiness_state"] == "NOT_READY"
    policy = deepcopy(DEFAULT_PROFILE)
    policy["readiness_requirements"]["IWP"]["require_activity"] = True
    assert assessment(policy=policy, has_activity=False)["evidence_state"]["missing_mappings"] == ["ACTIVITY"]


@pytest.mark.parametrize(
    "edges,expected", [([(1, 2), (2, 3)], False), ([(1, 2), (2, 1)], True), ([(1, 1)], True), ([(1, 2), (3, 2)], False)]
)
def test_cycle_detection_not_a_false_package_type_hierarchy(edges, expected):
    assert has_cycle(edges) is expected


def test_large_dependency_graph_has_no_recursive_stack_limit():
    edges = [(node, node + 1) for node in range(2500)]
    assert has_cycle(edges) is False
    assert has_cycle([*edges, (2500, 0)]) is True


@pytest.mark.parametrize(
    "model,body",
    [
        (
            PackageIn,
            {"package_code": "X", "package_type": "IWP", "name": "X", "reason": "test", "planned_start": "2026-01-01"},
        ),
        (ConstraintIn, {"code": "X", "constraint_type": "ACCESS", "title": "X", "reason": "test", "lag": 2}),
        (MappingIn, {"target_kind": "ACTIVITY", "activity_external_id": "A", "reason": "test", "duration": 2}),
    ],
)
def test_commands_cannot_smuggle_cpm_mutations(model, body):
    with pytest.raises(ValueError):
        model.model_validate(body)
