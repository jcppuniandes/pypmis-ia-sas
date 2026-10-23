"""Real isolated PostgreSQL/HTTP 4D source, lineage and zero-write proofs."""

import os
from copy import deepcopy
from hashlib import sha256
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from tests.awp_browser_fixture import create_awp_browser_fixture
from tests.test_scope_foundation_release import profile, request, success

from app.database.session import SessionLocal, engine
from app.domain.models import SecurityEvent
from app.main import app
from app.modules.awp.models import AWPHistory, ReadinessAssessment
from app.modules.awp.permissions import ensure_awp_permissions
from app.modules.awp.policy import DEFAULT_PROFILE as AWP_PROFILE
from app.modules.basic_data.service import _hash
from app.modules.operational_context.models import OperationalContextCommand
from app.modules.schedule_foundation.models import ScheduleBaseline, ScheduleVersion
from app.modules.schedule_four_d.permissions import ensure_four_d_permissions
from app.modules.schedule_four_d.service import DEFAULT_PROFILE
from app.modules.scope_foundation.models import DerivedModelVersion, PlanItem, ScopeBaseline, ScopeModelVersion
from app.modules.scope_foundation.service import ScopeFoundationService

REASON = {"reason": "Isolated O1B-B1 source-aware 4D validation"}


def path(f, suffix=""):
    return f"/api/v1/schedule/projects/{f.project_workspace_id}/4d{suffix}"


def awp(f, suffix=""):
    return f"/api/v1/awp/projects/{f.project_workspace_id}{suffix}"


def get(f, suffix="", **params):
    return f.client.get(path(f, suffix), headers=f.headers["admin"], params=params)


@pytest.fixture(scope="module")
def four_d_fixture():
    assert engine.dialect.name == "postgresql" and (
        engine.url.database == "o1bb1"
        or (engine.url.database == "o1bc" and os.getenv("PYPMIS_O1BC_FIXTURE") == "disposable-only")
    )
    with TestClient(app) as client, SessionLocal() as db:
        f = create_awp_browser_fixture(db, client)
        # The foreign actor has actual feature grants. A cross-tenant request
        # must fail canonical identity isolation, not merely a missing role.
        ensure_awp_permissions(db, f.foreign_tenant.id, f.users["foreign"].id)
        ensure_four_d_permissions(db, f.foreign_tenant.id, f.users["foreign"].id)
        db.commit()
        f.awp_profile = profile(f, "/api/v1/awp", AWP_PROFILE)
        f.four_d_profile = profile(f, "/api/v1/schedule/4d", DEFAULT_PROFILE)
        f.cwa = success(
            request(
                f,
                "POST",
                awp(f, "/cwas"),
                payload={**REASON, "code": "4D-NORTH", "name": "North work area", "area": "North", "zone": "A"},
            ),
            201,
        )
        f.packages = []
        for scope, plan, kind in zip(f.scope_items, f.plan_items, ("CWP", "EWP", "IWP", "TWP"), strict=True):
            package = success(
                request(
                    f,
                    "POST",
                    awp(f, "/packages"),
                    payload={
                        **REASON,
                        "package_code": f"4D-{scope['scope_nature']}",
                        "name": scope["name"],
                        "package_type": kind,
                        "cwa_id": f.cwa["id"],
                    },
                ),
                201,
            )
            for target_kind, target_id in (("SCOPE", scope["id"]), ("PLAN", plan["id"])):
                result = success(
                    request(
                        f,
                        "POST",
                        awp(f, f"/packages/{package['id']}/mappings"),
                        version=package["version"],
                        payload={**REASON, "target_kind": target_kind, "target_id": target_id},
                    ),
                    201,
                )
                package = result["package"]
            for version in (f.baseline_schedule_version, f.current_schedule_version):
                for activity in version["snapshot_json"]["activities"]:
                    external = activity["external_id"]
                    if f.activity_plans[external] == plan["id"]:
                        result = success(
                            request(
                                f,
                                "POST",
                                awp(f, f"/packages/{package['id']}/mappings"),
                                version=package["version"],
                                payload={
                                    **REASON,
                                    "target_kind": "ACTIVITY",
                                    "schedule_version_id": version["id"],
                                    "activity_external_id": external,
                                    "phase": f.activity_phases[external],
                                },
                            ),
                            201,
                        )
                        package = result["package"]
            f.packages.append(package)
        f.blocker = success(
            request(
                f,
                "POST",
                awp(f, "/constraints"),
                payload={
                    **REASON,
                    "constraint_type": "MATERIAL",
                    "code": "4D-BLOCKED",
                    "title": "Material delivery outstanding",
                    "blocking": True,
                },
            ),
            201,
        )
        result = success(
            request(
                f,
                "POST",
                awp(f, f"/constraints/{f.blocker['id']}/mappings"),
                version=f.blocker["version"],
                payload={**REASON, "target_kind": "PACKAGE", "target_id": f.packages[0]["id"]},
            ),
            201,
        )
        f.blocker = result.get("constraint", f.blocker)
        yield f, db
        db.rollback()


def rows_by_nature(result):
    return {row["scope_nature"]: row for row in result["items"]}


def test_current_source_explicit_data_date_and_governed_sources_only(four_d_fixture):
    f, _ = four_d_fixture
    result = success(get(f))
    assert result["source"]["kind"] == "CURRENT"
    assert result["source"]["schedule_version_id"] == f.current_schedule_version["id"]
    assert result["at"] == result["source"]["data_date"] == "2026-10-22T08:00:00"
    assert result["source"]["approved_baseline_reference"] == f.schedule_baseline["id"]
    assert result["authority"]["business_writes_performed"] is False
    assert result["authority"]["cpm_calculation_performed"] is False
    assert {row["id"] for row in result["sources"]["current"]} == {f.current_schedule_version["id"]}
    assert get(f, version_id=f.baseline_schedule_version["id"]).status_code == 409
    assert get(f, source="BASELINE").status_code == 422


def test_explicit_control_period_association_does_not_substitute_cutoff_for_data_date(four_d_fixture):
    from tests.test_operational_context_foundation import _period_payload

    f, _ = four_d_fixture
    prefix = f"/api/v1/schedule/projects/{f.project_workspace_id}/versions/{f.current_schedule_version['id']}"
    current = success(request(f, "GET", prefix))
    frozen = deepcopy(current["snapshot_json"])
    content_hash = current["content_hash"]
    period = success(
        request(
            f,
            "POST",
            f"/api/v1/operational/projects/{f.project_workspace_id}/periods",
            actor="manager",
            payload=_period_payload(
                period_start="2026-10-19",
                period_end="2026-10-25",
                cutoff_at="2026-10-25T18:00:00-05:00",
                schedule_data_date="2026-10-22",
            ),
        ),
        201,
    )
    association = success(
        request(
            f,
            "POST",
            f"{prefix}/period-associations",
            actor="manager",
            version=current["version"],
            payload={**REASON, "period_id": period["id"]},
        ),
        201,
    )
    view = success(get(f))
    linked = next(row for row in view["period_associations"] if row["id"] == association["id"])
    assert linked["period_id"] == period["id"]
    assert (
        linked["snapshot_json"]["schedule_data_date"]
        == view["at"]
        == view["source"]["data_date"]
        == "2026-10-22T08:00:00"
    )
    assert linked["snapshot_json"]["period_cutoff_at"].startswith("2026-10-25")
    assert linked["snapshot_json"]["period_cutoff_at"] != view["source"]["data_date"]
    assert linked["snapshot_json"]["period_timezone"] == "America/Bogota"
    assert linked["snapshot_json"]["data_date_is_not_cutoff"] is True
    preserved = success(request(f, "GET", prefix))
    assert preserved["snapshot_json"] == frozen and preserved["content_hash"] == content_hash


def test_approved_baseline_reuses_frozen_snapshot_even_version_superseded(four_d_fixture):
    f, _ = four_d_fixture
    result = success(get(f, source="BASELINE", baseline_id=f.schedule_baseline["id"]))
    assert result["source"]["schedule_version_id"] == f.baseline_schedule_version["id"]
    assert result["source"]["baseline_id"] == f.schedule_baseline["id"]
    assert result["at"] == "2026-10-20T08:00:00"
    assert rows_by_nature(result)["INSTALL"]["state"] == "NOT_STARTED"


@pytest.mark.parametrize(
    "nature,at,state,semantic",
    [
        ("INSTALL", "2026-10-22T08:00:00", "NOT_STARTED", "FUTURE_NOT_INSTALLED"),
        ("INSTALL", "2026-10-23T12:00:00", "IN_PROGRESS", "INSTALLATION"),
        ("INSTALL", "2026-10-25T08:00:00", "COMPLETED", "INSTALLED"),
        ("REMOVE", "2026-10-22T08:00:00", "NOT_STARTED", "EXISTING"),
        ("REMOVE", "2026-10-23T12:00:00", "IN_PROGRESS", "REMOVAL"),
        ("REMOVE", "2026-10-25T08:00:00", "REMOVED", "REMOVED"),
        ("TEMPORARY", "2026-10-20T08:00:00", "NOT_STARTED", "ABSENT_BEFORE_INSTALL"),
        ("TEMPORARY", "2026-10-21T12:00:00", "IN_PROGRESS", "TEMPORARY_INSTALLATION"),
        ("TEMPORARY", "2026-10-22T12:00:00", "TEMPORARY", "TEMPORARY_IN_USE"),
        ("TEMPORARY", "2026-10-25T12:00:00", "IN_PROGRESS", "TEMPORARY_REMOVAL"),
        ("TEMPORARY", "2026-10-26T08:00:00", "REMOVED", "ABSENT_AFTER_REMOVAL"),
        ("MAINTENANCE", "2026-10-22T08:00:00", "NOT_STARTED", "EXISTING_IN_SERVICE"),
        ("MAINTENANCE", "2026-10-23T12:00:00", "MAINTENANCE", "MAINTENANCE_INTERVENTION"),
        ("MAINTENANCE", "2026-10-25T08:00:00", "COMPLETED", "RESTORED_IN_SERVICE"),
    ],
)
def test_four_nature_semantics_real_ifc_plan_awp_activity_chain(four_d_fixture, nature, at, state, semantic):
    f, _ = four_d_fixture
    result = success(get(f, scope_nature=nature, at=at))
    assert len(result["items"]) == 1
    row = result["items"][0]
    assert (row["state"], row["semantic_state"]) == (state, semantic)
    assert row["objects"] and row["objects"][0]["guid"]
    assert row["derived_models"][0]["id"] == f.derived["id"]
    assert row["plan_item_id"] and row["packages"] and row["activities"] and row["wbs"]
    if nature == "TEMPORARY":
        assert {activity["phase"] for activity in row["activities"]} == {"INSTALL", "USE", "REMOVE"}
        assert len(row["activities"]) == 3
    assert not row["mapping_issues"], row["mapping_issues"]


def test_baseline_current_same_date_comparison_exposes_variance_no_cpm(four_d_fixture):
    f, _ = four_d_fixture
    result = success(get(f, "/compare", baseline_id=f.schedule_baseline["id"], at="2026-10-23T12:00:00"))
    row = next(row for row in result["items"] if row["scope_item_id"] == f.scope_items[0]["id"])
    assert row["baseline_state"] == "COMPLETED" and row["current_state"] == "IN_PROGRESS"
    assert row["variance_classification"] == "BEHIND_BASELINE"
    assert result["baseline"]["at"] == result["current"]["at"] == result["at"]
    current = rows_by_nature(result["current"])["INSTALL"]
    assert "DELAYED" in current["visual_classes"]
    assert result["cpm_calculation_performed"] is False
    filtered = success(
        get(f, "/compare", baseline_id=f.schedule_baseline["id"], at="2026-10-23T12:00:00", scope_nature="INSTALL")
    )
    assert len(filtered["items"]) == 1
    assert filtered["items"][0]["scope_item_id"] == f.scope_items[0]["id"]


@pytest.mark.parametrize(
    "dimension",
    [
        "wbs",
        "activity",
        "scope_item_id",
        "scope_nature",
        "plan_item_id",
        "cwa_id",
        "package_type",
        "work_package_id",
        "area",
        "zone",
        "system",
        "activity_status",
        "critical",
        "near_critical",
        "execution_readiness",
        "blocked",
    ],
)
def test_all_required_filter_dimensions_real_source(four_d_fixture, dimension):
    f, _ = four_d_fixture
    values = {
        "wbs": "101",
        "activity": "5001",
        "scope_item_id": f.scope_items[0]["id"],
        "scope_nature": "INSTALL",
        "plan_item_id": f.plan_items[0]["id"],
        "cwa_id": f.cwa["id"],
        "package_type": "CWP",
        "work_package_id": f.packages[0]["id"],
        "area": "North",
        "zone": "A",
        "system": "Structural",
        "activity_status": "NOT_STARTED",
        "critical": True,
        "near_critical": True,
        "execution_readiness": "NOT_READY",
        "blocked": True,
    }
    result = success(get(f, **{dimension: values[dimension]}))
    assert any(row["scope_nature"] == "INSTALL" for row in result["items"]), result


def test_readiness_blocker_is_separate_from_imported_scheduled_state(four_d_fixture):
    f, _ = four_d_fixture
    row = rows_by_nature(success(get(f)))["INSTALL"]
    assert row["state"] == "NOT_STARTED" and row["blocked"]
    assert "BLOCKED_BY_READINESS" in row["visual_classes"]
    assert any(constraint["id"] == f.blocker["id"] for constraint in row["constraints"])
    assert row["activities"][0]["planned_start"]
    assert row["readiness"][0]["readiness_state"] == "NOT_READY"
    assert "CRITICAL" in row["visual_classes"] and row["activities"][0]["criticality_authority"] == "P6_IMPORTED"


def test_selected_traceability_reuses_original_ifc_source_and_derived_membership(four_d_fixture):
    f, _ = four_d_fixture
    result = success(get(f, f"/traceability/{f.scope_items[0]['id']}"))
    row = result["traceability"][0]
    original = row["objects"][0]
    assert original["model_version_id"] == f.model["id"] and original["source_hash"] == f.model["source_hash"]
    assert original["guid"] == f.objects[0]["guid"] and original["express_id"] == f.objects[0]["express_id"]
    assert row["scope_item_id"] == f.scope_items[0]["id"] and row["plan_item_id"] == f.plan_items[0]["id"]
    assert row["activities"][0]["external_id"] == "5001" and row["cwas"][0]["id"] == f.cwa["id"]
    assert result["source_hashes"]["scope_baseline"] == f.scope_baseline["content_hash"]


def test_read_queries_are_zero_business_writes_and_preserve_all_source_authorities(four_d_fixture):
    f, db = four_d_fixture

    def capture():
        db.expire_all()
        result = {}
        for model in (
            ScopeModelVersion,
            ScopeBaseline,
            PlanItem,
            DerivedModelVersion,
            ScheduleVersion,
            ScheduleBaseline,
        ):
            rows = list(db.scalars(select(model).where(model.tenant_id == f.tenant_id)))
            result[model.__tablename__] = [
                ScopeFoundationService._out(row)
                | (
                    {"source_bytes_sha256": sha256(row.source_content).hexdigest()}
                    if hasattr(row, "source_content")
                    else {}
                )
                for row in rows
            ]
        result["facts"] = {
            model.__tablename__: db.scalar(
                select(func.count()).select_from(model).where(model.tenant_id == f.tenant_id)
            )
            for model in (SecurityEvent, OperationalContextCommand, AWPHistory, ReadinessAssessment)
        }
        return _hash(result)

    before = capture()
    first = success(get(f, at="2026-10-23T12:00:00"))
    second = success(get(f, at="2026-10-23T12:00:00"))
    success(get(f, source="BASELINE", baseline_id=f.schedule_baseline["id"]))
    success(get(f, "/compare", baseline_id=f.schedule_baseline["id"], at="2026-10-23T12:00:00"))
    success(get(f, f"/traceability/{f.scope_items[0]['id']}"))
    assert first["read_model_hash"] == second["read_model_hash"] and first["items"] == second["items"]
    assert capture() == before


def test_scope_tenant_and_read_only_rbac_isolation(four_d_fixture):
    f, _ = four_d_fixture
    assert f.client.get(path(f), headers=f.headers["foreign"]).status_code == 404
    assert f.client.get(path(f), headers=f.headers["unassigned"]).status_code == 403
    assert f.client.get(path(f), headers=f.headers["executive"]).status_code == 200
    denied = request(
        f,
        "POST",
        "/api/v1/schedule/4d/admin/profiles",
        actor="executive",
        payload={"code": "DENIED", "name": "Denied", "content_json": DEFAULT_PROFILE},
    )
    assert denied.status_code == 403
    assert get(f, version_id=2147483647).status_code == 404
    assert get(f, at="not-a-date").status_code == 422
    foreign_project = f.workspaces["foreign"].id
    assert (
        f.client.get(f"/api/v1/schedule/projects/{foreign_project}/4d", headers=f.headers["admin"]).status_code == 404
    )
    other_project = f.workspaces["other_project"].id
    other = f"/api/v1/schedule/projects/{other_project}/4d"
    assert (
        f.client.get(
            other, headers=f.headers["admin"], params={"version_id": f.current_schedule_version["id"]}
        ).status_code
        == 404
    )
    assert (
        f.client.get(
            other, headers=f.headers["admin"], params={"source": "BASELINE", "baseline_id": f.schedule_baseline["id"]}
        ).status_code
        == 404
    )


def test_partial_current_package_membership_fails_closed_without_rewriting_schedule(four_d_fixture):
    f, _ = four_d_fixture
    package = success(request(f, "GET", awp(f, f"/packages/{f.packages[0]['id']}")))
    success(
        request(
            f,
            "POST",
            awp(f, f"/packages/{package['id']}/mappings"),
            version=package["version"],
            payload={
                **REASON,
                "target_kind": "ACTIVITY",
                "schedule_version_id": f.current_schedule_version["id"],
                "activity_external_id": "5001",
                "phase": "EXECUTE",
                "action": "REMOVE",
            },
        ),
        201,
    )
    row = rows_by_nature(success(get(f, at="2026-10-26T08:00:00")))["INSTALL"]
    assert row["state"] == "UNKNOWN" and row["semantic_state"] == "UNKNOWN"
    assert "PACKAGE_ACTIVITY_VERSION_REVIEW_REQUIRED" in row["mapping_issues"]
    historical = rows_by_nature(
        success(get(f, source="BASELINE", baseline_id=f.schedule_baseline["id"], at="2026-10-26T08:00:00"))
    )["INSTALL"]
    assert historical["state"] == "COMPLETED"


def test_configuration_sod_etag_idempotency_and_immutable_publication(four_d_fixture):
    f, _ = four_d_fixture
    prefix = "/api/v1/schedule/4d/admin/profiles"
    key = f"four-d-idempotent-{uuid4()}"
    payload = {
        "code": f"4D-{uuid4().hex[:8]}",
        "name": "Controlled 4D config",
        "content_json": deepcopy(DEFAULT_PROFILE),
    }
    payload["content_json"]["scope"] = {"type": "workspace", "workspace_id": f.project_workspace_id}
    draft = success(request(f, "POST", prefix, key=key, payload=payload), 201)
    assert success(request(f, "POST", prefix, key=key, payload=payload), 201)["id"] == draft["id"]
    assert (
        request(f, "POST", f"{prefix}/{draft['id']}/publish", version=draft["version"], payload=REASON).status_code
        == 403
    )
    assert (
        request(
            f,
            "PUT",
            f"{prefix}/{draft['id']}",
            version=999,
            payload={"name": draft["name"], "content_json": payload["content_json"]},
        ).status_code
        == 412
    )
    published = success(
        request(
            f, "POST", f"{prefix}/{draft['id']}/publish", actor="publisher", version=draft["version"], payload=REASON
        )
    )
    assert published["status"] == "published"
    assert (
        request(
            f,
            "PUT",
            f"{prefix}/{draft['id']}",
            version=published["version"],
            payload={"name": draft["name"], "content_json": payload["content_json"]},
        ).status_code
        == 409
    )
    # The workspace-scoped profile overrides the tenant default without creating
    # an ambiguous pair of tenant-wide published configurations.
