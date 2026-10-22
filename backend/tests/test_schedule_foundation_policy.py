"""Independent PostgreSQL policy, source-health and approval-race contracts."""

import os
from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from tests.schedule_release_fixture import create_schedule_fixture
from tests.test_schedule_foundation_release import (
    REASON,
    accept,
    baseline,
    map_all,
    register,
    request,
    snapshot,
    version,
)
from tests.test_scope_foundation_release import profile, success

from app.database.session import SessionLocal, engine
from app.domain.models import ProjectMembership
from app.main import app
from app.modules.schedule_foundation.service import DEFAULT_PROFILE
from app.modules.scope_foundation.models import DerivedModelVersion, PlanItem, ScopeItem


@pytest.fixture(scope="module")
def policy_fixture():
    assert engine.dialect.name == "postgresql" and (
        engine.url.database == "o1bb"
        or (engine.url.database == "o1bb1" and os.getenv("PYPMIS_O1BB1_FIXTURE") == "disposable-only")
    )
    with TestClient(app) as client, SessionLocal() as db:
        fixture = create_schedule_fixture(db, client)
        # The bypass test must first satisfy the legacy configurator boundary;
        # otherwise a preliminary 403 would not exercise the dedicated API guard.
        db.add(
            ProjectMembership(
                tenant_id=fixture.tenant_id,
                project_id=fixture.legacy_project_id,
                user_id=fixture.users["admin"].id,
                role="Legacy Configurator",
                can_configure=True,
            )
        )
        db.commit()
        fixture.schedule_profile = profile(fixture, "/api/v1/schedule", DEFAULT_PROFILE)
        yield fixture
        db.rollback()


def policy(fixture, **changes):
    content = deepcopy(DEFAULT_PROFILE)
    for key, value in changes.items():
        if isinstance(value, dict):
            content[key].update(value)
        else:
            content[key] = value
    prior = fixture.schedule_profile
    draft = success(
        request(
            fixture,
            "POST",
            f"/api/v1/schedule/admin/profiles/{prior['id']}/successor",
            version=prior["version"],
            payload=REASON,
        )
    )
    draft = success(
        request(
            fixture,
            "PUT",
            f"/api/v1/schedule/admin/profiles/{draft['id']}",
            version=draft["version"],
            payload={"name": draft["name"], "content_json": content},
        )
    )
    fixture.schedule_profile = success(
        request(
            fixture,
            "POST",
            f"/api/v1/schedule/admin/profiles/{draft['id']}/publish",
            version=draft["version"],
            actor="publisher",
            payload=REASON,
        )
    )
    return fixture.schedule_profile


def clean_source():
    result = snapshot()
    result["relationships"] = [item for item in result["relationships"] if not item["is_external"]]
    result["external_links"] = []
    return result


def manual(fixture, content):
    content = deepcopy(content)
    # A manual definition cannot manufacture imported P6 CPM results.
    for activity in content["activities"]:
        for field in (
            "total_float",
            "free_float",
            "critical",
            "early_start",
            "early_finish",
            "late_start",
            "late_finish",
        ):
            activity[field] = None
    schedule = register(fixture)
    return success(
        request(
            fixture,
            "POST",
            f"/registers/{schedule['id']}/versions",
            version=schedule["version"],
            payload={**REASON, "kind": "INITIAL", "snapshot_json": content},
        ),
        201,
    )


def codes(items):
    return {item if isinstance(item, str) else item["code"] for item in items}


def health(fixture, row):
    return success(request(fixture, "GET", f"/versions/{row['id']}/health"))


def test_default_unresolved_external_links_are_fail_closed(policy_fixture):
    f = policy_fixture
    policy(f)
    row = map_all(f, version(f, register(f)))
    result = health(f, row)
    assert "SCHEDULE_UNRESOLVED_EXTERNAL_LINKS" in codes(result["errors"])
    assert not result["can_accept"] and result["quality_is_not_cpm"]
    assert (
        request(f, "POST", f"/versions/{row['id']}/validate", version=row["version"], payload=REASON).status_code == 409
    )


@pytest.mark.parametrize(
    "case,expected,blocked",
    [
        ("negative_lag", "SCHEDULE_NEGATIVE_LAG", True),
        ("hard_constraint", "SCHEDULE_HARD_CONSTRAINT", True),
        ("open_ends", "SCHEDULE_OPEN_ENDS", True),
        ("missing_calendar", "SCHEDULE_CALENDAR_REFERENCE_MISSING", True),
        ("long_duration", "SCHEDULE_LONG_DURATION", False),
        ("excessive_lag", "SCHEDULE_EXCESSIVE_LAG", False),
    ],
)
def test_published_health_policy_checks_without_cpm(policy_fixture, case, expected, blocked):
    f = policy_fixture
    thresholds = {}
    content = clean_source()
    if case == "negative_lag":
        thresholds["negative_lag"] = "BLOCK"
    elif case == "hard_constraint":
        thresholds["hard_constraint"] = "BLOCK"
    elif case == "open_ends":
        thresholds["max_open_ends"] = 0
        content["relationships"] = []
    elif case == "missing_calendar":
        content["activities"][0]["calendar_external_id"] = "99999"
    elif case == "long_duration":
        content["activities"][0]["original_duration"] = 300
    elif case == "excessive_lag":
        content["relationships"][0]["lag"] = 100
    policy(f, quality_thresholds=thresholds)
    row = map_all(f, version(f, register(f), content=content))
    result = health(f, row)
    assert expected in codes(result["errors"] if blocked else result["warnings"])
    assert result["can_accept"] is not blocked
    assert result["quality_is_not_cpm"]
    if case == "open_ends":
        assert result["metrics"]["open_ends"] == 2  # Authorized milestones exempt, not all nodes.
    if case == "negative_lag":
        assert any(item["lag"] == -1 for item in row["snapshot_json"]["relationships"])


@pytest.mark.parametrize("declared_hours,blocked", [(None, True), (10, False)])
def test_day_duration_requires_declared_calendar_never_eight_hour_default(policy_fixture, declared_hours, blocked):
    f = policy_fixture
    policy(f)
    content = clean_source()
    content["activities"][0].update(duration_unit="DAY", original_duration=2, remaining_duration=1)
    content["calendars"][0]["hours_per_day"] = declared_hours
    row = map_all(f, manual(f, content))
    result = health(f, row)
    assert ("SCHEDULE_DURATION_BASIS_UNKNOWN_NO_8H_ASSUMPTION" in codes(result["errors"])) is blocked
    assert row["snapshot_json"]["activities"][0]["original_duration"] == 2
    assert row["snapshot_json"]["activities"][0]["duration_unit"] == "DAY"
    assert row["snapshot_json"]["calendars"][0]["hours_per_day"] == declared_hours


def test_mandatory_wbs_mappings_are_distinct_from_activity_mappings(policy_fixture):
    f = policy_fixture
    policy(f, mapping_policy={"wbs_required": True})
    row = version(f, register(f), content=clean_source())
    result = health(f, row)
    assert "SCHEDULE_WBS_MAPPING_REQUIRED" in codes(result["errors"])
    assert "SCHEDULE_SCOPE_PLAN_MAPPING_REQUIRED" in codes(result["errors"])


@pytest.mark.parametrize(
    "field,value",
    [
        ("calendar_handling", "ASSUME_8_HOURS"),
        ("lookahead_default_days", True),
        ("inherit_to_descendants", "yes"),
        ("near_critical_threshold", {"unit": "DAY", "value": 5}),
        ("near_critical_threshold", {"unit": "HOUR", "value": -1}),
        ("open_end_policy", {"authorized_milestone_types": ["Task Dependent"]}),
        ("mapping_policy", {"activities_required": "yes"}),
        ("allowed_constraints", ["Calculate CPM Locally"]),
        ("supported_exchange", {"imports": ["CSV"], "exports": ["XER"]}),
        ("scope", {"type": "workspace", "workspace_id": True}),
    ],
)
def test_invalid_authority_or_policy_is_rejected_before_persistence(policy_fixture, field, value):
    f = policy_fixture
    content = deepcopy(DEFAULT_PROFILE)
    content[field] = value
    response = request(
        f,
        "POST",
        "/api/v1/schedule/admin/profiles",
        payload={"code": f"INVALID-{uuid4()}", "name": "Invalid unpublished policy", "content_json": content},
    )
    assert response.status_code == 422, response.text


def test_profile_publication_rejects_author_and_last_material_editor(policy_fixture):
    f = policy_fixture
    content = deepcopy(DEFAULT_PROFILE)
    draft = success(
        request(
            f,
            "POST",
            "/api/v1/schedule/admin/profiles",
            payload={"code": f"SOD-{uuid4()}", "name": "Profile SoD evidence", "content_json": content},
        ),
        201,
    )
    assert (
        request(
            f,
            "POST",
            f"/api/v1/schedule/admin/profiles/{draft['id']}/publish",
            version=draft["version"],
            payload=REASON,
        ).status_code
        == 403
    )
    content["near_critical_threshold"]["value"] = 24
    edited = success(
        request(
            f,
            "PUT",
            f"/api/v1/schedule/admin/profiles/{draft['id']}",
            actor="publisher",
            version=draft["version"],
            payload={"name": draft["name"], "content_json": content},
        )
    )
    for actor in ("admin", "publisher"):
        response = request(
            f,
            "POST",
            f"/api/v1/schedule/admin/profiles/{draft['id']}/publish",
            actor=actor,
            version=edited["version"],
            payload=REASON,
        )
        assert response.status_code == 403, response.text


@pytest.mark.parametrize("action", ["create", "patch", "publish", "clone"])
def test_legacy_admin_cannot_bypass_governed_schedule_profile(policy_fixture, action):
    f = policy_fixture
    row = f.schedule_profile
    root = "/api/v1/admin-configuration/configurations"
    if action == "create":
        response = request(
            f,
            "POST",
            root,
            payload={
                "kind": "schedule_profile",
                "code": f"BYPASS-{uuid4()}",
                "name": "Forbidden generic route",
                "content_json": deepcopy(DEFAULT_PROFILE),
            },
        )
    elif action == "patch":
        response = request(
            f,
            "PATCH",
            f"{root}/{row['id']}",
            payload={"expected_version": row["version"], "name": "Forbidden generic update"},
        )
    else:
        response = request(f, "POST", f"{root}/{row['id']}/{action}")
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "GOVERNED_CONFIGURATION_API_REQUIRED"


def test_two_successor_baselines_same_source_cannot_approve_stale_predecessor(policy_fixture):
    f = policy_fixture
    policy(f)
    row = accept(f, map_all(f, version(f, register(f), content=clean_source())))
    original = baseline(f, row)
    candidates = []
    for _ in range(2):
        candidate = success(
            request(
                f,
                "POST",
                f"/versions/{row['id']}/baselines",
                version=row["version"],
                payload={**REASON, "previous_baseline_id": original["id"]},
            ),
            201,
        )
        for action in ("submit", "review"):
            candidate = success(
                request(
                    f, "POST", f"/baselines/{candidate['id']}/{action}", version=candidate["version"], payload=REASON
                )
            )
        candidates.append(candidate)
    first, stale = candidates
    success(
        request(
            f, "POST", f"/baselines/{first['id']}/approve", actor="publisher", version=first["version"], payload=REASON
        )
    )
    response = request(
        f, "POST", f"/baselines/{stale['id']}/approve", actor="publisher", version=stale["version"], payload=REASON
    )
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "SCHEDULE_BASELINE_PREDECESSOR_CHANGED_REPREPARE"


def test_schedule_commands_do_not_create_scope_plan_or_derived_authorities(policy_fixture):
    f = policy_fixture
    policy(f)

    def counts():
        with SessionLocal() as db:
            return {
                model.__tablename__: db.scalar(
                    select(func.count()).select_from(model).where(model.tenant_id == f.tenant_id)
                )
                for model in (ScopeItem, PlanItem, DerivedModelVersion)
            }

    before = counts()
    row = map_all(f, version(f, register(f), content=clean_source()))
    assert health(f, row)["can_accept"]
    assert counts() == before
