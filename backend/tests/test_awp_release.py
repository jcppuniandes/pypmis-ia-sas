"""Actual canonical PostgreSQL/HTTP AWP execution governance contracts."""

import os
from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError
from tests.schedule_release_fixture import create_schedule_fixture
from tests.test_schedule_foundation_release import accept, baseline, map_all, register, version
from tests.test_scope_foundation_release import profile, success

from app.database.session import SessionLocal, engine
from app.domain.models import ProjectMembership
from app.main import app
from app.modules.awp.permissions import ensure_awp_permissions
from app.modules.awp.policy import CONSTRAINT_TYPES, DEFAULT_PROFILE, DIMENSIONS, PACKAGE_TYPES
from app.modules.schedule_foundation.service import DEFAULT_PROFILE as SCHEDULE_POLICY

REASON = {"reason": "Isolated governed O1B-B1 execution validation"}


@pytest.fixture(scope="module")
def fixture():
    assert engine.dialect.name == "postgresql" and (
        engine.url.database == "o1bb1"
        or (engine.url.database == "o1bc" and os.getenv("PYPMIS_O1BC_FIXTURE") == "disposable-only")
    )
    with TestClient(app) as client, SessionLocal() as db:
        f = create_schedule_fixture(db, client)
        ensure_awp_permissions(db, f.tenant_id, f.users["admin"].id)
        ensure_awp_permissions(db, f.foreign_tenant.id, f.users["foreign"].id)
        db.add(
            ProjectMembership(
                tenant_id=f.tenant_id,
                project_id=f.legacy_project_id,
                user_id=f.users["admin"].id,
                role="Legacy Configurator",
                can_configure=True,
            )
        )
        db.commit()
        policy = deepcopy(SCHEDULE_POLICY)
        policy["quality_thresholds"]["external_links"] = "WARN"
        f.schedule_profile = profile(f, "/api/v1/schedule", policy)
        f.awp_profile = profile(f, "/api/v1/awp", DEFAULT_PROFILE)
        f.schedule_register = register(f)
        f.schedule_version = accept(f, map_all(f, version(f, f.schedule_register)))
        f.schedule_baseline = baseline(f, f.schedule_version)
        yield f
        db.rollback()


def request(f, method, path, *, payload=None, actor="planner", version=None, key=None):
    headers = dict(f.headers[actor])
    if method != "GET":
        headers["Idempotency-Key"] = key or f"b1-{uuid4()}"
    if version is not None:
        headers["If-Match"] = f'"{version}"'
    root = f"/api/v1/awp/projects/{f.project_workspace_id}"
    return f.client.request(method, path if path.startswith("/api") else root + path, headers=headers, json=payload)


def cwa(f, **changes):
    return success(
        request(
            f,
            "POST",
            "/cwas",
            payload={**REASON, "code": f"CWA-{uuid4().hex[:8]}", "name": "Area container", **changes},
        ),
        201,
    )


def package(f, kind="IWP", actor="planner", **changes):
    return success(
        request(
            f,
            "POST",
            "/packages",
            actor=actor,
            payload={
                **REASON,
                "package_code": f"PKG-{uuid4().hex[:8]}",
                "package_type": kind,
                "name": "Canonical execution package",
                **changes,
            },
        ),
        201,
    )


def mapped(f, package_row, kind="PLAN", target=None, **changes):
    body = {**REASON, "target_kind": kind, "target_id": target or f.plan_items[0]["id"], **changes}
    return success(
        request(f, "POST", f"/packages/{package_row['id']}/mappings", version=package_row["version"], payload=body), 201
    )["package"]


def constraint(f, kind="ACCESS", **changes):
    return success(
        request(
            f,
            "POST",
            "/constraints",
            payload={
                **REASON,
                "code": f"CON-{uuid4().hex[:8]}",
                "constraint_type": kind,
                "title": "Controlled execution condition",
                **changes,
            },
        ),
        201,
    )


def map_constraint(f, row, kind, target=None, **changes):
    return success(
        request(
            f,
            "POST",
            f"/constraints/{row['id']}/mappings",
            version=row["version"],
            payload={**REASON, "target_kind": kind, "target_id": target, **changes},
        ),
        201,
    )["constraint"]


def assess(f, row, actor="planner", **changes):
    return success(
        request(
            f,
            "POST",
            f"/packages/{row['id']}/assess",
            actor=actor,
            version=row["version"],
            payload={
                **REASON,
                "as_of": "2026-10-21",
                "evidence_json": dict.fromkeys(DIMENSIONS, "DOC-approved"),
                **changes,
            },
        ),
        201,
    )


def lifecycle(f, row, state, actor="manager"):
    return success(
        request(
            f,
            "POST",
            f"/packages/{row['id']}/transition",
            actor=actor,
            version=row["version"],
            payload={**REASON, "status": state},
        )
    )


def test_cwa_container_hierarchy_and_cycle_etag(fixture):
    f = fixture
    parent = cwa(f)
    child = cwa(f, parent_cwa_id=parent["id"])
    body = {
        **REASON,
        **{field: parent[field] for field in ("code", "name", "description", "area", "zone", "location", "status")},
        "parent_cwa_id": child["id"],
    }
    assert request(f, "PUT", f"/cwas/{parent['id']}", payload=body, version=parent["version"]).status_code == 422
    body["parent_cwa_id"] = None
    assert request(f, "PUT", f"/cwas/{parent['id']}", payload=body, version=99).status_code == 412


@pytest.mark.parametrize("kind", PACKAGE_TYPES)
def test_governed_package_types_without_dates(fixture, kind):
    row = package(fixture, kind)
    assert row["package_type"] == kind and row["status"] == "DRAFT"
    assert row["readiness_state"] == "NOT_ASSESSED" and row["release_state"] == "NOT_RELEASED"
    assert "planned_start" not in row


@pytest.mark.parametrize("kind", CONSTRAINT_TYPES)
def test_governed_constraint_types_preserve_due_date_no_auto_clear(fixture, kind):
    row = constraint(fixture, kind, due_date="2000-01-01")
    assert row["constraint_type"] == kind and row["status"] == "OPEN"


def test_package_idempotency_rbac_tenant_project_and_missing_ifmatch(fixture):
    f = fixture
    key, code = f"idem-{uuid4()}", f"PKG-{uuid4()}"
    body = {**REASON, "package_code": code, "package_type": "EWP", "name": "Idempotency"}
    row = success(request(f, "POST", "/packages", payload=body, key=key), 201)
    assert success(request(f, "POST", "/packages", payload=body, key=key), 201) == row
    assert request(f, "POST", "/packages", payload={**body, "name": "Other"}, key=key).status_code == 409
    assert (
        request(f, "POST", "/packages", payload={**body, "package_code": "DENIED"}, actor="executive").status_code
        == 403
    )
    assert request(f, "GET", f"/packages/{row['id']}", actor="foreign").status_code == 404
    assert (
        request(f, "GET", f"/api/v1/awp/projects/{f.workspaces['other_project'].id}/packages/{row['id']}").status_code
        == 403
    )
    assert request(f, "PUT", f"/packages/{row['id']}", payload=body).status_code == 422


def test_package_scope_plan_activity_many_to_many_without_source_mutation(fixture):
    f = fixture
    before = f.db if hasattr(f, "db") else None
    with SessionLocal() as db:
        source = db.execute(
            text("SELECT snapshot_json::text,content_hash FROM schedule_versions WHERE id=:id"),
            {"id": f.schedule_version["id"]},
        ).one()
    rows = [package(f, "CWP"), package(f, "IWP")]
    activities = [item["external_id"] for item in f.schedule_version["snapshot_json"]["activities"][:2]]
    for index, row in enumerate(rows):
        row = mapped(f, row, "SCOPE", f.scope_items[index]["id"])
        for plan in f.plan_items:
            row = mapped(f, row, "PLAN", plan["id"])
        for activity in activities:
            row = mapped(
                f,
                row,
                "ACTIVITY",
                target=None,
                target_id=None,
                schedule_version_id=f.schedule_version["id"],
                activity_external_id=activity,
                phase="INSTALL" if index == 0 else "REMOVE",
            )
    model = success(request(f, "GET", "/overview"))
    selected = [item for item in model["effective_mappings"] if item["work_package_id"] in {row["id"] for row in rows}]
    assert len(selected) == 10
    with SessionLocal() as db:
        assert (
            db.execute(
                text("SELECT snapshot_json::text,content_hash FROM schedule_versions WHERE id=:id"),
                {"id": f.schedule_version["id"]},
            ).one()
            == source
        )
    assert before is None


def test_dependency_graph_no_false_type_chain_cycle_and_history(fixture):
    f = fixture
    first, second = package(f, "LOGISTICS"), package(f, "IWP")
    body = {
        **REASON,
        "predecessor_package_id": first["id"],
        "successor_package_id": second["id"],
        "dependency_type": "SUPPORT",
        "blocking": True,
    }
    row = success(request(f, "POST", "/dependencies", payload=body), 201)
    assert (
        request(
            f,
            "POST",
            "/dependencies",
            payload={**body, "predecessor_package_id": second["id"], "successor_package_id": first["id"]},
        ).status_code
        == 422
    )
    changed = success(
        request(
            f,
            "PUT",
            f"/dependencies/{row['id']}",
            version=row["version"],
            payload={**body, "status": "CLEARED", "evidence_reference": "DOC-done"},
        )
    )
    assert changed["revision"] == 2
    history = success(request(f, "GET", f"/history/PackageDependency/{row['id']}"))["items"]
    assert len(history) == 2 and history[0]["snapshot_json"]["status"] == "ACTIVE"


def test_blocking_clear_evidence_readiness_independent_release_and_history(fixture):
    f = fixture
    row = mapped(f, package(f))
    row = mapped(
        f,
        row,
        "ACTIVITY",
        target=None,
        target_id=None,
        schedule_version_id=f.schedule_version["id"],
        activity_external_id=f.schedule_version["snapshot_json"]["activities"][0]["external_id"],
    )
    blocker = map_constraint(f, constraint(f, owner_user_id=f.users["planner"].id), "PACKAGE", row["id"])
    initial = assess(f, row)
    assert initial["readiness_state"] == "NOT_READY"
    row = initial["package"]
    clear_body = {**REASON, "status": "CLEARED", "evidence_reference": "DOC-access-approved"}
    assert (
        request(
            f,
            "POST",
            f"/constraints/{blocker['id']}/transition",
            version=blocker["version"],
            payload=clear_body,
            actor="planner",
        ).status_code
        == 403
    )
    assert (
        request(
            f,
            "POST",
            f"/constraints/{blocker['id']}/transition",
            version=blocker["version"],
            payload={**clear_body, "evidence_reference": ""},
            actor="manager",
        ).status_code
        == 422
    )
    success(
        request(
            f,
            "POST",
            f"/constraints/{blocker['id']}/transition",
            version=blocker["version"],
            payload=clear_body,
            actor="manager",
        )
    )
    current = success(request(f, "GET", "/overview"))["current_readiness"][str(row["id"])]
    assert current["stale"] is True and current["readiness_state"] == "NOT_ASSESSED"
    ready = assess(f, row)
    assert ready["readiness_state"] == "READY" and ready["package"]["release_state"] == "NOT_RELEASED"
    row = lifecycle(f, ready["package"], "PLANNED")
    row = lifecycle(f, row, "UNDER_REVIEW")
    row = lifecycle(f, row, "READY")
    assert (
        request(
            f, "POST", f"/packages/{row['id']}/release", version=row["version"], payload=REASON, actor="planner"
        ).status_code
        == 403
    )
    row = success(
        request(
            f, "POST", f"/packages/{row['id']}/release", version=row["version"], payload=REASON, actor="second_manager"
        )
    )
    assert row["status"] == "RELEASED" and row["released_by"] == f.users["second_manager"].id
    history = success(request(f, "GET", f"/history/WorkPackage/{row['id']}"))["items"]
    assert any(item["event_type"] == "READINESS_ASSESSED" for item in history)
    assert history[-1]["event_type"] == "WORK_PACKAGE_RELEASED"


def test_nonblocking_waiver_and_constraint_all_level_mappings(fixture):
    f = fixture
    area, row = cwa(f), package(f)
    condition = constraint(f, "PERMIT", blocking=False)
    for kind, target in (
        ("CWA", area["id"]),
        ("PACKAGE", row["id"]),
        ("PLAN", f.plan_items[0]["id"]),
        ("SCOPE", f.scope_items[0]["id"]),
    ):
        condition = map_constraint(f, condition, kind, target)
    condition = map_constraint(
        f,
        condition,
        "ACTIVITY",
        schedule_version_id=f.schedule_version["id"],
        activity_external_id=f.schedule_version["snapshot_json"]["activities"][0]["external_id"],
    )
    body = {**REASON, "status": "WAIVED", "evidence_reference": "DOC-waiver"}
    assert (
        request(
            f,
            "POST",
            f"/constraints/{condition['id']}/transition",
            version=condition["version"],
            payload=body,
            actor="manager",
        ).status_code
        == 422
    )
    condition = success(
        request(
            f,
            "POST",
            f"/constraints/{condition['id']}/transition",
            version=condition["version"],
            payload={**body, "waiver_reference": "WAIVER-001"},
            actor="manager",
        )
    )
    assert condition["status"] == "WAIVED"
    assert (
        request(
            f,
            "POST",
            f"/constraints/{condition['id']}/transition",
            version=condition["version"],
            payload=body,
            actor="manager",
        ).status_code
        == 409
    )


def test_get_zero_business_writes(fixture):
    f = fixture
    writes = []

    def observe(_connection, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
            writes.append(statement)

    event.listen(engine, "before_cursor_execute", observe)
    try:
        success(request(f, "GET", "/overview"))
        success(request(f, "GET", f"/api/v1/readiness/projects/{f.project_workspace_id}/workfront"))
    finally:
        event.remove(engine, "before_cursor_execute", observe)
    assert writes == []


@pytest.mark.parametrize(
    "table", ["awp_package_mappings", "awp_constraint_mappings", "awp_readiness_assessments", "awp_history"]
)
def test_postgres_history_immutable(fixture, table):
    with SessionLocal() as db:
        identity = db.execute(text(f"SELECT id FROM {table} ORDER BY id LIMIT 1")).scalar_one()
        with pytest.raises(DBAPIError):
            db.execute(text(f"UPDATE {table} SET version=version+1 WHERE id=:id"), {"id": identity})
            db.flush()
        db.rollback()


def test_profile_sod_and_published_immutable(fixture):
    f = fixture
    body = {
        "code": f"PROF-{uuid4().hex[:8]}",
        "name": "Independent publication",
        "content_json": deepcopy(DEFAULT_PROFILE),
    }
    row = success(request(f, "POST", "/api/v1/awp/admin/profiles", actor="admin", payload=body), 201)
    response = request(
        f,
        "POST",
        f"/api/v1/awp/admin/profiles/{row['id']}/publish",
        actor="admin",
        payload=REASON,
        version=row["version"],
    )
    assert response.status_code == 403
    assert (
        request(
            f,
            "PUT",
            f"/api/v1/awp/admin/profiles/{f.awp_profile['id']}",
            actor="admin",
            version=f.awp_profile["version"],
            payload={"name": "Illegal", "content_json": deepcopy(DEFAULT_PROFILE)},
        ).status_code
        == 409
    )


@pytest.mark.parametrize("action", ["create", "patch", "publish", "clone"])
def test_generic_admin_cannot_bypass_awp_governance(fixture, action):
    f = fixture
    root = "/api/v1/admin-configuration/configurations"
    row = f.awp_profile
    if action == "create":
        response = request(
            f,
            "POST",
            root,
            actor="admin",
            payload={
                "kind": "awp_profile",
                "code": f"BYPASS-{uuid4()}",
                "name": "Forbidden",
                "content_json": deepcopy(DEFAULT_PROFILE),
            },
        )
    elif action == "patch":
        response = request(
            f,
            "PATCH",
            f"{root}/{row['id']}",
            actor="admin",
            payload={"expected_version": row["version"], "name": "Forbidden"},
        )
    else:
        response = request(f, "POST", f"{root}/{row['id']}/{action}", actor="admin")
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "GOVERNED_CONFIGURATION_API_REQUIRED"


def test_last_material_profile_editor_cannot_publish_even_if_not_creator(fixture):
    f = fixture
    row = success(
        request(
            f,
            "POST",
            "/api/v1/awp/admin/profiles",
            actor="admin",
            payload={
                "code": f"EDIT-SOD-{uuid4().hex[:8]}",
                "name": "Policy original",
                "content_json": deepcopy(DEFAULT_PROFILE),
            },
        ),
        201,
    )
    row = success(
        request(
            f,
            "PUT",
            f"/api/v1/awp/admin/profiles/{row['id']}",
            actor="publisher",
            version=row["version"],
            payload={"name": "Policy materially edited", "content_json": deepcopy(DEFAULT_PROFILE)},
        )
    )
    response = request(
        f,
        "POST",
        f"/api/v1/awp/admin/profiles/{row['id']}/publish",
        actor="publisher",
        version=row["version"],
        payload=REASON,
    )
    assert response.status_code == 403 and response.json()["detail"]["code"] == "AWP_PROFILE_PUBLICATION_SOD"


@pytest.mark.parametrize("forbidden_duty", ["preparer", "assessor"])
def test_package_manager_authority_cannot_bypass_release_sod(fixture, forbidden_duty):
    f = fixture
    row = mapped(f, package(f, actor="manager" if forbidden_duty == "preparer" else "planner"))
    row = assess(f, row, actor="manager" if forbidden_duty == "assessor" else "planner")["package"]
    for status in ("PLANNED", "UNDER_REVIEW", "READY"):
        row = lifecycle(f, row, status, actor="second_manager")
    response = request(
        f, "POST", f"/packages/{row['id']}/release", version=row["version"], payload=REASON, actor="manager"
    )
    assert response.status_code == 403, response.text
    assert response.json()["detail"]["code"] == "AWP_PACKAGE_RELEASE_SOD"
    assert (
        success(
            request(
                f, "POST", f"/packages/{row['id']}/release", version=row["version"], payload=REASON, actor="publisher"
            )
        )["status"]
        == "RELEASED"
    )


def test_complete_closed_package_does_not_clear_execution_condition(fixture):
    f = fixture
    row = mapped(f, package(f))
    row = assess(f, row)["package"]
    for status in ("PLANNED", "UNDER_REVIEW", "READY"):
        row = lifecycle(f, row, status)
    row = success(
        request(
            f, "POST", f"/packages/{row['id']}/release", version=row["version"], payload=REASON, actor="second_manager"
        )
    )
    condition = map_constraint(f, constraint(f, "QUALITY", blocking=False), "PACKAGE", row["id"])
    for status in ("IN_PROGRESS", "COMPLETED", "CLOSED"):
        row = lifecycle(f, row, status, actor="manager")
    assert row["status"] == "CLOSED"
    unchanged = success(request(f, "GET", f"/constraints/{condition['id']}"))
    assert unchanged["status"] == "OPEN" and unchanged["cleared_at"] is None


def test_postgres_mapping_rejects_cross_tenant_and_project_references(fixture):
    f = fixture
    row = package(f)
    with SessionLocal() as db:
        for tenant_id, project_id, actor_id in (
            (f.foreign_tenant.id, f.workspaces["foreign"].id, f.users["foreign"].id),
            (f.tenant_id, f.workspaces["other_project"].id, f.users["admin"].id),
        ):
            with pytest.raises(DBAPIError):
                db.execute(
                    text("""INSERT INTO awp_package_mappings
                    (tenant_id,project_workspace_id,version,created_by,created_at,work_package_id,target_kind,target_id,schedule_version_id,activity_external_id,phase,status,revision,lineage_json,reason)
                    VALUES (:tenant,:project,1,:actor,CURRENT_TIMESTAMP,:package,'SCOPE',:scope,NULL,NULL,'EXECUTE','ACTIVE',1,'{}','Cross-boundary negative validation')"""),
                    {
                        "tenant": tenant_id,
                        "project": project_id,
                        "actor": actor_id,
                        "package": row["id"],
                        "scope": f.scope_items[0]["id"],
                    },
                )
                db.flush()
            db.rollback()
