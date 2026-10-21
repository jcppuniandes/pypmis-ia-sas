"""Real HTTP/DB Scope lifecycles and security against isolated PostgreSQL."""

from copy import deepcopy
from hashlib import sha256
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError
from tests.scope_foundation_fixture import scope_ifc, scope_xlsx
from tests.scope_release_fixture import create_scope_fixture

from app.database.session import SessionLocal, engine
from app.domain.models import ChangeRequest, ProjectMembership, WorkflowStatus
from app.main import app
from app.modules.operational_context.service import DEFAULT_PROFILE as OPERATIONAL_PROFILE
from app.modules.scope_foundation.models import ScopeBaseline, ScopeModelVersion
from app.modules.scope_foundation.service import DEFAULT_PROFILE

REASON = {"reason": "Isolated governed O1B-A release validation"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as value:
        yield value


def request(f, method, path, *, payload=None, actor="admin", version=None, key=None, files=None, data=None):
    headers = dict(f.headers[actor])
    if method != "GET":
        headers["Idempotency-Key"] = key or f"o1ba-{uuid4()}"
    if version is not None:
        headers["If-Match"] = f'"{version}"'
    url = path if path.startswith("/api") else f"/api/v1/scope/projects/{f.project_workspace_id}{path}"
    return f.client.request(method, url, headers=headers, json=payload, files=files, data=data)


def success(response, expected=200):
    assert response.status_code == expected, response.text
    return response.json()


def profile(f, prefix, content):
    row = success(
        request(
            f,
            "POST",
            prefix + "/admin/profiles",
            payload={
                "code": f"O1BA-{uuid4().hex[:10]}",
                "name": "Governed isolated Scope profile",
                "content_json": deepcopy(content),
            },
        ),
        201,
    )
    return success(
        request(
            f,
            "POST",
            f"{prefix}/admin/profiles/{row['id']}/publish",
            payload=REASON,
            actor="publisher",
            version=row["version"],
        )
    )


@pytest.fixture
def fixture(client):
    with SessionLocal() as db:
        f = create_scope_fixture(db)
        f.client = client
        f.operational_profile = profile(f, "/api/v1/operational", OPERATIONAL_PROFILE)
        f.scope_profile = profile(f, "/api/v1/scope", DEFAULT_PROFILE)
        yield f
        db.rollback()


def item(f, code=None, **changes):
    payload = {
        "scope_code": code or f"SC-{uuid4().hex[:8]}",
        "name": "Governed Scope Item",
        "quantity": "10",
        "unit": "m3",
        "scope_nature": "INSTALL",
        **REASON,
        **changes,
    }
    return success(request(f, "POST", "/items", payload=payload), 201)


def revision(f, items):
    row = success(
        request(
            f,
            "POST",
            "/revisions",
            payload={**REASON, "revision_code": f"REV-{uuid4().hex[:8]}", "item_ids": [row["id"] for row in items]},
        ),
        201,
    )
    for action, actor in (("submit", "admin"), ("review", "publisher"), ("approve", "publisher")):
        row = success(
            request(f, "POST", f"/revisions/{row['id']}/{action}", actor=actor, payload=REASON, version=row["version"])
        )
    return row


def accepted_model(f):
    content = scope_ifc()
    row = success(
        request(
            f,
            "POST",
            "/models",
            files={"file": ("scope.ifc", content, "application/octet-stream")},
            data={**REASON, "model_code": f"MODEL-{uuid4().hex[:8]}"},
        ),
        201,
    )
    assert row["source_hash"] == sha256(content).hexdigest()
    for action, actor in (("review", "admin"), ("accept", "publisher")):
        row = success(
            request(f, "POST", f"/models/{row['id']}/{action}", actor=actor, payload=REASON, version=row["version"])
        )
    objects = success(request(f, "GET", f"/models/{row['id']}/objects"))["items"]
    return row, [obj for obj in objects if obj["ifc_class"] == "IfcWall"], content


@pytest.mark.parametrize("nature", ["INSTALL", "REMOVE", "TEMPORARY", "MAINTENANCE"])
def test_manual_scope_natures_and_quantities(fixture, nature):
    row = item(fixture, scope_nature=nature)
    assert row["scope_nature"] == nature and row["source_type"] == "MANUAL"
    assert float(row["quantity"]) == float(row["source_quantity"]) == float(row["current_quantity"]) == 10
    assert row["approved_quantity"] is None and row["status"] == "DRAFT"


@pytest.mark.parametrize(
    "changes",
    [
        {"unit": "unknown"},
        {"quantity": "-1"},
        {"quantity": "NaN"},
        {"scope_nature": "BUILD"},
        {"parent_scope_item_id": 14},
        {"source_type": "APPROVED_CHANGE", "approved_change_id": 14},
        {"source_type": "IFC", "model_object_ids": [14]},
    ],
)
def test_scope_invalid_input_and_untrusted_references_fail_closed(fixture, changes):
    payload = {"scope_code": "BAD", "name": "Invalid candidate", "unit": "m3", "quantity": "1", **REASON, **changes}
    assert request(fixture, "POST", "/items", payload=payload).status_code in {404, 409, 422}


@pytest.mark.parametrize(
    "actor", ["executive", "cost_controller", "progress_engineer", "planner", "unassigned", "foreign"]
)
def test_scope_write_requires_scope_duty_and_workspace_assignment(fixture, actor):
    response = request(
        fixture,
        "POST",
        "/items",
        actor=actor,
        payload={"scope_code": "DENIED", "name": "Must not persist", "quantity": 1, "unit": "m3", **REASON},
    )
    assert response.status_code in {403, 404}, response.text


@pytest.mark.parametrize(
    "actor",
    [
        "scope_manager",
        "bim_manager",
        "bim_coordinator",
        "construction_manager",
        "document_controller",
        "manager",
        "executive",
    ],
)
def test_granular_roles_can_read_canonical_scope_without_broad_admin(fixture, actor):
    result = success(request(fixture, "GET", "/overview", actor=actor))
    assert result["context"]["project_workspace_id"] == fixture.project_workspace_id
    assert "admin.configure" not in result["allowed_actions"]


def test_scope_hierarchy_draft_etag_and_immutable_baseline_successor(fixture):
    f = fixture
    parent = item(f, "PARENT")
    child = item(f, "CHILD", parent_scope_item_id=parent["id"])
    stale = request(
        f,
        "PUT",
        f"/items/{child['id']}",
        payload={"scope_code": child["scope_code"], "name": "Stale edit", "quantity": 12, "unit": "m3", **REASON},
        version=99,
    )
    assert stale.status_code == 412
    first = revision(f, [parent, child])
    original = first["baseline"]
    assert original["content_hash"] == first["content_hash"]
    forbidden = request(
        f,
        "PUT",
        f"/items/{child['id']}",
        payload={
            "scope_code": child["scope_code"],
            "name": "Forbidden baseline edit",
            "quantity": 20,
            "unit": "m3",
            **REASON,
        },
        version=child["version"] + 1,
    )
    assert forbidden.status_code == 409
    successor = item(
        f, "CHILD", predecessor_id=child["id"], parent_scope_item_id=parent["id"], quantity=12, scope_nature="REMOVE"
    )
    second = revision(f, [successor])
    assert second["baseline"]["previous_baseline_id"] == original["id"]
    with SessionLocal() as db:
        persisted = db.get(ScopeBaseline, original["id"])
        assert persisted.content_hash == original["content_hash"]
        assert persisted.snapshot_json == original["snapshot_json"]


def test_revision_sod_and_candidate_edit_after_preparation(fixture):
    f = fixture
    candidate = item(f)
    row = success(
        request(f, "POST", "/revisions", payload={**REASON, "revision_code": "R1", "item_ids": [candidate["id"]]}), 201
    )
    for action in ("submit", "review"):
        row = success(request(f, "POST", f"/revisions/{row['id']}/{action}", payload=REASON, version=row["version"]))
    assert (
        request(f, "POST", f"/revisions/{row['id']}/approve", payload=REASON, version=row["version"]).status_code == 403
    )


def test_real_ifc_version_acceptance_source_bytes_and_mn_scope_mapping(fixture):
    f = fixture
    model, walls, source = accepted_model(f)
    assert len(walls) == 2 and model["is_current"]
    one = item(f, "IFC-ONE", source_type="IFC", model_object_ids=[walls[0]["id"], walls[1]["id"]])
    two = item(f, "IFC-TWO", source_type="IFC", model_object_ids=[walls[0]["id"]], scope_nature="REMOVE")
    assert len(one["model_object_ids"]) == 2 and two["model_object_ids"] == [walls[0]["id"]]
    download = request(f, "GET", f"/models/{model['id']}/source")
    assert download.status_code == 200 and download.content == source
    with SessionLocal() as db:
        persisted = db.get(ScopeModelVersion, model["id"])
        assert sha256(persisted.source_content).hexdigest() == model["source_hash"]


def test_plan_many_to_many_group_split_recompose_and_derived_lineage(fixture):
    f = fixture
    model, walls, source = accepted_model(f)
    objects = [wall["id"] for wall in walls]
    scopes = [item(f, f"S{i}", source_type="IFC", model_object_ids=objects) for i in (1, 2)]
    revision(f, scopes)

    def payload(code, quantity):
        return {
            "code": code,
            "name": code,
            **REASON,
            "model_object_ids": objects,
            "allocations": [{"scope_item_id": row["id"], "quantity": quantity, "unit": "m3"} for row in scopes],
        }

    plans = [success(request(f, "POST", "/plan-items", payload=payload(f"P{i}", 5)), 201) for i in (1, 2)]
    assert all(len(plan["allocations"]) == 2 for plan in plans)
    for operation, outputs in (
        ("GROUP", [payload("GROUPED", 10)]),
        ("SPLIT", [payload("SPLIT-A", 4), payload("SPLIT-B", 6)]),
        ("RECOMPOSE", [payload("RECOMPOSED", 10)]),
    ):
        result = success(
            request(
                f,
                "POST",
                "/plan-items/transform",
                payload={
                    **REASON,
                    "operation": operation,
                    "source_plan_item_ids": [r["id"] for r in plans],
                    "expected_versions": {str(r["id"]): r["version"] for r in plans},
                    "outputs": outputs,
                },
            ),
            201,
        )
        plans = result["items"]
    key = f"derived-{uuid4()}"
    body = {**REASON, "plan_item_ids": [row["id"] for row in plans], "split_rule": "LOGICAL"}
    derived = success(request(f, "POST", "/derived-models", payload=body, key=key), 201)
    again = success(request(f, "POST", "/derived-models", payload=body, key=key), 201)
    assert again == derived
    snapshot = derived["snapshot_json"]
    assert not snapshot["physical_geometry_modified"] and snapshot["future_4d"] == "NOT_ACTIVE"
    assert len(snapshot["objects"]) == 2 and all(
        row["source_hash"] == model["source_hash"] for row in snapshot["objects"]
    )
    assert request(f, "GET", f"/models/{model['id']}/source").content == source


def test_get_scope_queries_write_no_business_rows_or_security_receipts(fixture):
    f = fixture
    writes = []

    def observe(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
            writes.append(statement)

    event.listen(engine, "before_cursor_execute", observe)
    try:
        success(request(f, "GET", "/overview", actor="executive"))
        success(request(f, "GET", "/api/v1/scope/admin/profiles"))
    finally:
        event.remove(engine, "before_cursor_execute", observe)
    assert not writes


def test_postgresql_baseline_raw_update_rejected(fixture):
    if engine.dialect.name != "postgresql":
        pytest.skip("Requires actual PostgreSQL immutable trigger")
    row = revision(fixture, [item(fixture)])["baseline"]
    with engine.connect() as connection:
        with pytest.raises(DBAPIError):
            connection.execute(
                text("UPDATE scope_baselines SET content_hash='tampered' WHERE id=:id"), {"id": row["id"]}
            )
        connection.rollback()
    with SessionLocal() as db:
        assert db.get(ScopeBaseline, row["id"]).content_hash == row["content_hash"]


@pytest.mark.parametrize("command", ["create", "edit", "publish", "clone"])
def test_generic_admin_cannot_bypass_governed_scope_profile(fixture, command):
    f = fixture
    with SessionLocal() as db:
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
    base = "/api/v1/admin-configuration/configurations"
    identity = f.scope_profile["id"]
    if command == "create":
        response = request(
            f,
            "POST",
            base,
            payload={"kind": "scope_profile", "code": "BYPASS", "name": "Forbidden", "content_json": DEFAULT_PROFILE},
        )
    elif command == "edit":
        response = request(
            f,
            "PATCH",
            f"{base}/{identity}",
            payload={"name": "Forbidden", "expected_version": f.scope_profile["version"]},
        )
    else:
        response = request(f, "POST", f"{base}/{identity}/{command}")
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["dedicated_api"] == "/api/v1/scope/admin/profiles"


def test_scope_profile_latest_material_editor_cannot_self_publish(fixture):
    f = fixture
    row = success(
        request(
            f,
            "POST",
            "/api/v1/scope/admin/profiles",
            payload={
                "code": f"SOD-{uuid4().hex[:8]}",
                "name": "Independent edited policy",
                "content_json": deepcopy(DEFAULT_PROFILE),
            },
        ),
        201,
    )
    changed = deepcopy(DEFAULT_PROFILE)
    changed["quantity_tolerance"] = "0.00001"
    row = success(
        request(
            f,
            "PUT",
            f"/api/v1/scope/admin/profiles/{row['id']}",
            actor="publisher",
            version=row["version"],
            payload={"name": row["name"], "content_json": changed},
        )
    )
    assert (
        request(
            f,
            "POST",
            f"/api/v1/scope/admin/profiles/{row['id']}/publish",
            actor="publisher",
            payload=REASON,
            version=row["version"],
        ).status_code
        == 403
    )


def test_excel_native_staging_idempotent_candidate_and_preserved_source_quantity(fixture):
    f = fixture
    content = scope_xlsx()
    key = f"excel-{uuid4()}"
    row = success(
        request(
            f,
            "POST",
            "/excel-imports",
            files={
                "file": ("scope.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            },
            data=REASON,
            key=key,
        ),
        201,
    )
    assert row["validation_summary"]["can_accept"]
    retry = success(
        request(
            f,
            "POST",
            "/excel-imports",
            files={
                "file": ("scope.xlsx", content, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            },
            data=REASON,
            key=key,
        ),
        201,
    )
    assert retry == row
    candidate = success(
        request(f, "POST", f"/excel-imports/{row['id']}/candidate", payload=REASON, version=row["version"])
    )
    overview = success(request(f, "GET", "/overview"))
    assert len(candidate["candidate_item_ids"]) == 4
    assert {r["scope_nature"] for r in overview["items"]} == {"INSTALL", "REMOVE", "TEMPORARY", "MAINTENANCE"}
    original = overview["items"][0]
    payload = {
        "scope_code": original["scope_code"],
        "name": original["name"],
        "quantity": 999,
        "unit": original["unit"],
        "scope_nature": original["scope_nature"],
        "source_type": "EXCEL",
        "source_reference": original["source_reference"],
        "source_revision": original["source_revision"],
        "excel_import_id": row["id"],
        "excel_row_number": original["lineage_json"]["excel"]["row_number"],
        **REASON,
    }
    edited = success(request(f, "PUT", f"/items/{original['id']}", payload=payload, version=original["version"]))
    assert float(edited["quantity"]) == 999 and edited["source_quantity"] == original["source_quantity"]


def test_excel_direct_item_creation_rejects_silent_source_unit_conversion(fixture):
    f = fixture
    staged = success(
        request(
            f,
            "POST",
            "/excel-imports",
            files={
                "file": (
                    "scope.xlsx",
                    scope_xlsx(),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            },
            data=REASON,
        ),
        201,
    )
    source = staged["rows_json"][0]
    payload = {
        "scope_code": source["scope_code"],
        "name": source["name"],
        "quantity": source["quantity"],
        "unit": "ea" if source["unit"] != "ea" else "m",
        "scope_nature": source["scope_nature"],
        "source_type": "EXCEL",
        "excel_import_id": staged["id"],
        "excel_row_number": source["lineage"]["row_number"],
        **REASON,
    }
    denied = request(f, "POST", "/items", payload=payload)
    assert denied.status_code == 422, denied.text
    assert "SCOPE_EXCEL_UNIT_MISMATCH_NO_SILENT_CONVERSION" in denied.text
    assert success(request(f, "GET", "/overview"))["items"] == []
    payload["unit"] = source["unit"]
    actual = success(request(f, "POST", "/items", payload=payload), 201)
    assert actual["unit"] == source["unit"]
    assert float(actual["source_quantity"]) == float(source["quantity"])


def test_plan_publication_revalidates_current_scope_after_approved_successor(fixture):
    f = fixture
    original = item(f, "CURRENT")
    revision(f, [original])
    plan = success(
        request(
            f,
            "POST",
            "/plan-items",
            payload={
                "code": "PENDING",
                "name": "Draft prepared against original Scope",
                **REASON,
                "allocations": [{"scope_item_id": original["id"], "quantity": 10, "unit": "m3"}],
            },
        ),
        201,
    )
    successor = item(f, "CURRENT", predecessor_id=original["id"], quantity=12)
    revision(f, [successor])
    denied = request(
        f, "POST", f"/plan-items/{plan['id']}/publish", actor="publisher", payload=REASON, version=plan["version"]
    )
    assert denied.status_code == 409, denied.text
    assert "PLAN_CURRENT_APPROVED_SCOPE_REQUIRED" in denied.text
    persisted = next(row for row in success(request(f, "GET", "/overview"))["plan_items"] if row["id"] == plan["id"])
    assert persisted["status"] == "DRAFT" and persisted["version"] == plan["version"]


@pytest.mark.parametrize("kind", ["AREA", "ZONE", "SYSTEM", "QUANTITY_RANGE"])
def test_strategy_ordered_parallel_publication_successor_and_candidate_segmentation(fixture, kind):
    f = fixture
    scope = item(f, area="North", zone="A", system="Structural")
    revision(f, [scope])
    row = success(
        request(
            f,
            "POST",
            "/strategies",
            payload={
                **REASON,
                "code": "STRATEGY",
                "name": "Controlled strategy",
                "paths": [
                    {"code": "ORDERED", "name": "Ordered path", "mode": "ORDERED", "sequence": 1},
                    {"code": "PARALLEL", "name": "Parallel path", "mode": "PARALLEL", "sequence": 2},
                ],
                "segmentation_rules": [{"kind": kind, **({"quantity": 5} if kind == "QUANTITY_RANGE" else {})}],
            },
        ),
        201,
    )
    assert (
        request(f, "POST", f"/strategies/{row['id']}/publish", payload=REASON, version=row["version"]).status_code
        == 403
    )
    published = success(
        request(
            f, "POST", f"/strategies/{row['id']}/publish", actor="publisher", payload=REASON, version=row["version"]
        )
    )
    segmented = success(
        request(
            f,
            "POST",
            f"/strategies/{row['id']}/segment",
            version=published["version"],
            payload={**REASON, "scope_item_ids": [scope["id"]], "rule_index": 0, "code_prefix": "CAND"},
        ),
        201,
    )
    assert all(plan["status"] == "DRAFT" for plan in segmented["items"])
    assert sum(float(a["quantity"]) for plan in segmented["items"] for a in plan["allocations"]) == 10
    successor = success(
        request(f, "POST", f"/strategies/{row['id']}/successor", payload=REASON, version=published["version"])
    )
    assert successor["status"] == "DRAFT" and successor["predecessor_id"] == row["id"]


def test_model_successor_diff_reject_and_prior_source_immutable(fixture):
    f = fixture
    model, _walls, source = accepted_model(f)
    changed = scope_ifc(length=3.0)
    next_model = success(
        request(
            f,
            "POST",
            "/models",
            files={"file": ("scope-v2.ifc", changed, "application/octet-stream")},
            data={**REASON, "model_code": model["model_code"]},
        ),
        201,
    )
    assert next_model["supersedes"] == model["id"] and next_model["revision"] == 2
    assert next_model["source_hash"] != model["source_hash"]
    rejected = success(
        request(f, "POST", f"/models/{next_model['id']}/reject", payload=REASON, version=next_model["version"])
    )
    assert rejected["status"] == "REJECTED" and not rejected["is_current"]
    assert request(f, "GET", f"/models/{model['id']}/source").content == source


def test_source_model_cross_project_and_tenant_queries_denied(fixture):
    f = fixture
    model, _walls, _source = accepted_model(f)
    for workspace in (f.workspaces["other_project"], f.workspaces["foreign"]):
        response = request(f, "GET", f"/api/v1/scope/projects/{workspace.id}/models/{model['id']}/source")
        assert response.status_code == 404, response.text
    assert request(f, "GET", f"/models/{model['id']}/source", actor="foreign").status_code == 404


def test_approved_change_source_contract_consumes_bound_existing_authority_only(fixture):
    f = fixture
    with SessionLocal() as db:
        source = ChangeRequest(
            tenant_id=f.tenant_id,
            project_id=f.legacy_project_id,
            title="Existing approved source fixture",
            deviation="Existing approved variation, not a new workflow",
            status=WorkflowStatus.approved,
        )
        db.add(source)
        db.commit()
        source_id = source.id
    success(
        request(
            f,
            "POST",
            f"/api/v1/operational/projects/{f.project_workspace_id}/binding",
            version=0,
            payload={**REASON, "legacy_project_id": f.legacy_project_id},
        ),
        201,
    )
    scope = item(f, "CHANGE-SCOPE", source_type="APPROVED_CHANGE", approved_change_id=source_id)
    assert scope["lineage_json"]["approved_change_id"] == source_id
    assert scope["status"] == "DRAFT" and scope["baseline_reference"] is None
    with SessionLocal() as db:
        assert db.get(ChangeRequest, source_id).status == WorkflowStatus.approved
