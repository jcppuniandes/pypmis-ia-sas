"""Actual HTTP and PostgreSQL Schedule command/lifecycle release contracts."""

import os
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError
from tests.schedule_release_fixture import create_schedule_fixture
from tests.test_scope_foundation_release import profile, success

from app.database.session import SessionLocal, engine
from app.main import app
from app.modules.schedule_foundation.exchange import export_schedule_xml, parse_schedule_source
from app.modules.schedule_foundation.service import DEFAULT_PROFILE

REASON = {"reason": "Isolated governed O1B-B release validation"}
FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def fixture():
    assert engine.dialect.name == "postgresql" and (
        engine.url.database == "o1bb"
        or (engine.url.database == "o1bb1" and os.getenv("PYPMIS_O1BB1_FIXTURE") == "disposable-only")
        or (engine.url.database == "o1bc" and os.getenv("PYPMIS_O1BC_FIXTURE") == "disposable-only")
    )
    with TestClient(app) as client, SessionLocal() as db:
        f = create_schedule_fixture(db, client)
        policy = deepcopy(DEFAULT_PROFILE)
        # This test stream explicitly permits preserved external links for review;
        # the shipped default remains fail-closed and is tested separately.
        policy["quality_thresholds"]["external_links"] = "WARN"
        f.schedule_profile = profile(f, "/api/v1/schedule", policy)
        yield f
        db.rollback()


def request(f, method, path, *, payload=None, actor="admin", version=None, key=None, files=None, data=None):
    headers = dict(f.headers[actor])
    if method != "GET":
        headers["Idempotency-Key"] = key or f"o1bb-{uuid4()}"
    if version is not None:
        headers["If-Match"] = f'"{version}"'
    root = f"/api/v1/schedule/projects/{f.project_workspace_id}"
    return f.client.request(
        method, path if path.startswith("/api") else root + path, headers=headers, json=payload, files=files, data=data
    )


def snapshot():
    return deepcopy(
        parse_schedule_source((FIXTURES / "schedule-foundation-p6.xml").read_bytes(), "schedule.xml")["snapshot"]
    )


def register(f, **changes):
    return success(
        request(
            f,
            "POST",
            "/registers",
            payload={
                **REASON,
                "schedule_code": f"SCH-{uuid4().hex[:8]}",
                "name": "Governed Control Schedule",
                "schedule_type": "CONTROL",
                **changes,
            },
        ),
        201,
    )


def version(f, schedule, *, content=None, predecessor=None, kind="INITIAL", key=None, actor="admin"):
    return success(
        request(
            f,
            "POST",
            f"/registers/{schedule['id']}/imports",
            version=schedule["version"],
            key=key,
            actor=actor,
            data={
                **REASON,
                "kind": kind,
                **({"predecessor_version_id": str(predecessor)} if predecessor else {}),
            },
            files={"file": ("release-source.xml", export_schedule_xml(content or snapshot()), "application/xml")},
        ),
        201,
    )


def map_all(f, row, *, plans=None):
    selected = plans or [plan["id"] for plan in f.plan_items]
    for target_kind, rows in (("WBS", row["snapshot_json"]["wbs"]), ("ACTIVITY", row["snapshot_json"]["activities"])):
        for target in rows:
            row = success(
                request(
                    f,
                    "POST",
                    f"/versions/{row['id']}/mappings",
                    version=row["version"],
                    payload={
                        **REASON,
                        "target_kind": target_kind,
                        "target_external_id": target["external_id"],
                        "plan_item_ids": selected,
                    },
                ),
                201,
            )["schedule_version"]
    return row


def accept(f, row):
    for action, actor in (("validate", "admin"), ("review", "publisher"), ("accept", "publisher")):
        row = success(
            request(f, "POST", f"/versions/{row['id']}/{action}", actor=actor, version=row["version"], payload=REASON)
        )
    return row


def baseline(f, row, **changes):
    result = success(
        request(
            f,
            "POST",
            f"/versions/{row['id']}/baselines",
            version=row["version"],
            payload={**REASON, "baseline_type": "CONTROL", **changes},
        ),
        201,
    )
    for action, actor in (("submit", "admin"), ("review", "publisher"), ("approve", "publisher")):
        result = success(
            request(
                f, "POST", f"/baselines/{result['id']}/{action}", version=result["version"], actor=actor, payload=REASON
            )
        )
    return result


def test_register_idempotency_and_policy_type(fixture):
    f = fixture
    key = f"register-{uuid4()}"
    body = {**REASON, "schedule_code": f"IDEM-{uuid4()}", "name": "Idempotent register", "schedule_type": "CONTROL"}
    row = success(request(f, "POST", "/registers", payload=body, key=key), 201)
    assert success(request(f, "POST", "/registers", payload=body, key=key), 201) == row
    body["name"] = "Different command"
    assert request(f, "POST", "/registers", payload=body, key=key).status_code == 409
    assert request(f, "POST", "/registers", payload={**body, "schedule_type": "UNPUBLISHED_TYPE"}).status_code == 422


@pytest.mark.parametrize(
    "actor",
    ["executive", "scope_manager", "bim_manager", "construction_manager", "cost_controller", "unassigned", "foreign"],
)
def test_schedule_register_write_duties_and_project_assignment(fixture, actor):
    response = request(
        fixture,
        "POST",
        "/registers",
        actor=actor,
        payload={**REASON, "schedule_code": f"DENY-{uuid4()}", "name": "Forbidden command"},
    )
    assert response.status_code in {403, 404}, response.text


@pytest.mark.parametrize(
    "actor",
    [
        "manager",
        "second_manager",
        "planner",
        "scope_manager",
        "bim_manager",
        "construction_manager",
        "cost_controller",
        "executive",
    ],
)
def test_schedule_granular_read_roles_reuse_current_operational_context(fixture, actor):
    result = success(request(fixture, "GET", "/overview", actor=actor))
    assert result["context"]["project_workspace_id"] == fixture.project_workspace_id
    if actor not in {"manager", "second_manager"}:
        assert "baseline.approve" not in result["allowed_actions"]


def test_version_create_requires_register_etag_and_preserves_explicit_data_date(fixture):
    f = fixture
    schedule = register(f)
    payload = {**REASON, "snapshot_json": snapshot()}
    missing = request(f, "POST", f"/registers/{schedule['id']}/versions", payload=payload)
    assert missing.status_code == 422 and "If-Match" in missing.text
    assert request(f, "POST", f"/registers/{schedule['id']}/versions", payload=payload, version=999).status_code == 412
    row = version(f, schedule)
    assert row["data_date"] == row["snapshot_json"]["project"]["data_date"]
    assert row["status"] in {"DRAFT", "STAGED"} and row["scope_baseline_id"] == f.scope_baseline["id"]


def test_unmapped_schedule_cannot_accept_or_approve_baseline(fixture):
    f = fixture
    row = version(f, register(f))
    response = request(
        f, "POST", f"/versions/{row['id']}/accept", actor="publisher", version=row["version"], payload=REASON
    )
    assert response.status_code in {409, 422}
    assert request(
        f, "POST", f"/versions/{row['id']}/baselines", payload=REASON, version=row["version"]
    ).status_code in {409, 422}


def test_wbs_plan_and_activity_plan_many_to_many_and_baseline_current_separation(fixture):
    f = fixture
    schedule = register(f)
    original = snapshot()
    row = accept(f, map_all(f, version(f, schedule, content=original)))
    assert row["status"] == "ACCEPTED_CURRENT"
    approved = baseline(f, row)
    assert approved["status"] == "APPROVED_BASELINE"
    prior_hash = approved["content_hash"]
    schedule = success(request(f, "GET", f"/registers/{schedule['id']}"))
    changed = deepcopy(original)
    changed["project"]["data_date"] = "2026-11-15T00:00:00"
    changed["activities"][0]["remaining_duration"] = 73
    updated = accept(f, map_all(f, version(f, schedule, content=changed, predecessor=row["id"], kind="UPDATE")))
    current = success(request(f, "GET", f"/registers/{schedule['id']}"))
    assert current["current_version_id"] == updated["id"]
    assert (
        current["baseline_version_id"] == row["id"] and current["baseline_version_id"] != current["current_version_id"]
    )
    retained = success(request(f, "GET", f"/baselines/{approved['id']}"))
    assert retained["content_hash"] == prior_hash and retained["snapshot_json"] == approved["snapshot_json"]


def test_acceptance_rejects_last_material_mapping_editor_and_importer(fixture):
    f = fixture
    row = map_all(f, version(f, register(f), actor="planner"))
    for action in ("validate", "review"):
        row = success(request(f, "POST", f"/versions/{row['id']}/{action}", version=row["version"], payload=REASON))
    denied = request(f, "POST", f"/versions/{row['id']}/accept", version=row["version"], payload=REASON)
    assert denied.status_code == 403, denied.text


def test_mapping_wrong_tenant_project_and_unknown_external_identity_denied(fixture):
    f = fixture
    row = version(f, register(f))
    for change in ({"target_external_id": "NOT_IN_SOURCE"}, {"plan_item_ids": [14]}, {"scope_item_ids": [14]}):
        body = {
            **REASON,
            "target_kind": "ACTIVITY",
            "target_external_id": row["snapshot_json"]["activities"][0]["external_id"],
            "plan_item_ids": [f.plan_items[0]["id"]],
            **change,
        }
        assert request(
            f, "POST", f"/versions/{row['id']}/mappings", payload=body, version=row["version"]
        ).status_code in {404, 409, 422}
    foreign_url = f"/api/v1/schedule/projects/{f.workspaces['foreign'].id}/versions/{row['id']}"
    assert request(f, "GET", foreign_url).status_code in {403, 404}


def test_accepted_schedule_mapping_and_source_snapshot_immutable(fixture):
    f = fixture
    row = accept(f, map_all(f, version(f, register(f))))
    body = {
        **REASON,
        "target_kind": "ACTIVITY",
        "target_external_id": row["snapshot_json"]["activities"][0]["external_id"],
        "plan_item_ids": [f.plan_items[0]["id"]],
    }
    assert (
        request(f, "POST", f"/versions/{row['id']}/mappings", payload=body, version=row["version"]).status_code == 409
    )
    with engine.connect() as connection:
        with pytest.raises(DBAPIError):
            connection.execute(text("UPDATE schedule_versions SET snapshot_json='{}' WHERE id=:id"), {"id": row["id"]})
        connection.rollback()


def test_xml_export_manifest_and_actual_source_roundtrip_with_no_cpm_claim(fixture):
    f = fixture
    row = accept(f, map_all(f, version(f, register(f))))
    exported = success(
        request(
            f,
            "POST",
            f"/versions/{row['id']}/exports",
            version=row["version"],
            payload={**REASON, "format": "XML", "purpose": "CURRENT"},
        ),
        201,
    )
    source = request(f, "GET", f"/exports/{exported['id']}/download")
    assert source.status_code == 200 and source.content.startswith(b"<?xml")
    assert sha256(source.content).hexdigest() == exported["source_hash"]
    parsed = parse_schedule_source(source.content, "schedule.xml")
    assert parsed["validation"]["can_accept"]
    assert len(parsed["snapshot"]["activities"]) == len(row["snapshot_json"]["activities"])
    assert request(
        f,
        "POST",
        f"/versions/{row['id']}/exports",
        version=row["version"],
        payload={**REASON, "format": "XER", "purpose": "CURRENT"},
    ).status_code in {409, 422}


def test_get_schedule_overview_and_profiles_have_no_sql_writes(fixture):
    writes = []

    def observe(_conn, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
            writes.append(statement)

    event.listen(engine, "before_cursor_execute", observe)
    try:
        success(request(fixture, "GET", "/overview", actor="executive"))
        success(request(fixture, "GET", "/api/v1/schedule/admin/profiles"))
    finally:
        event.remove(engine, "before_cursor_execute", observe)
    assert not writes


@pytest.mark.parametrize("suffix", ["xml", "xer"])
def test_actual_file_upload_staging_hash_and_rejection_history(fixture, suffix):
    f = fixture
    schedule = register(f)
    raw = (FIXTURES / f"schedule-foundation-p6.{suffix}").read_bytes()
    row = success(
        request(
            f,
            "POST",
            f"/registers/{schedule['id']}/imports",
            version=schedule["version"],
            files={"file": (f"actual.{suffix}", raw, "application/octet-stream")},
            data=REASON,
        ),
        201,
    )
    assert row["status"] == "STAGED" and row["source_hash"] == sha256(raw).hexdigest()
    assert row["import_manifest_json"]["cpm_authority"] == "PRIMAVERA_P6_EXTERNAL"
    assert len(row["snapshot_json"]["calendars"]) == 2
    rejected = success(
        request(f, "POST", f"/versions/{row['id']}/reject", actor="publisher", version=row["version"], payload=REASON)
    )
    assert rejected["status"] == "REJECTED"
    assert success(request(f, "GET", f"/registers/{schedule['id']}"))["current_version_id"] is None
    assert any(
        item["id"] == row["id"] and item["status"] == "REJECTED"
        for item in success(request(f, "GET", "/versions"))["items"]
    )


def test_manual_creation_cannot_forge_cpm_results_and_updates_create_new_version(fixture):
    f = fixture
    schedule = register(f)
    original = snapshot()
    forged = request(
        f,
        "POST",
        f"/registers/{schedule['id']}/versions",
        version=schedule["version"],
        payload={**REASON, "snapshot_json": original},
    )
    assert forged.status_code == 422 and "CPM_RESULTS_REQUIRE_IMPORTED_SOURCE" in forged.text
    for activity in original["activities"]:
        for name in (
            "total_float",
            "free_float",
            "critical",
            "early_start",
            "early_finish",
            "late_start",
            "late_finish",
        ):
            activity[name] = None
    first = success(
        request(
            f,
            "POST",
            f"/registers/{schedule['id']}/versions",
            version=schedule["version"],
            payload={**REASON, "snapshot_json": original},
        ),
        201,
    )
    schedule = success(request(f, "GET", f"/registers/{schedule['id']}"))
    changed = deepcopy(original)
    changed["wbs"][1]["parent_external_id"] = ""
    changed["activities"][0]["name"] = "Governed revised staged work"
    second = success(
        request(
            f,
            "POST",
            f"/registers/{schedule['id']}/versions",
            version=schedule["version"],
            payload={**REASON, "snapshot_json": changed, "predecessor_version_id": first["id"], "kind": "CORRECTION"},
        ),
        201,
    )
    assert first["id"] != second["id"] and second["diff_json"]["wbs"]["changed"]
    assert success(request(f, "GET", f"/versions/{first['id']}"))["snapshot_json"] == first["snapshot_json"]


def test_broken_identity_mapping_retained_and_blocks_successor(fixture):
    f = fixture
    schedule = register(f)
    first = accept(f, map_all(f, version(f, schedule)))
    schedule = success(request(f, "GET", f"/registers/{schedule['id']}"))
    changed = deepcopy(first["snapshot_json"])
    removed = changed["activities"].pop()["external_id"]
    changed["relationships"] = [
        r for r in changed["relationships"] if removed not in {r["predecessor_external_id"], r["successor_external_id"]}
    ]
    second = version(f, schedule, content=changed, predecessor=first["id"], kind="UPDATE")
    mappings = success(request(f, "GET", f"/versions/{second['id']}/mappings"))["items"]
    assert any(m["target_external_id"] == removed and m["status"] == "BROKEN" for m in mappings)
    assert not success(request(f, "GET", f"/versions/{second['id']}/health"))["can_accept"]
    assert first["id"] != second["id"]


def test_explicit_period_association_preserves_data_date_distinct_from_cutoff(fixture):
    f = fixture
    from tests.test_operational_context_foundation import _period_payload

    row = accept(f, map_all(f, version(f, register(f))))
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
                schedule_data_date="2026-10-20",
            ),
        ),
        201,
    )
    associated = success(
        request(
            f,
            "POST",
            f"/versions/{row['id']}/period-associations",
            version=row["version"],
            payload={**REASON, "period_id": period["id"]},
        ),
        201,
    )
    assert associated["snapshot_json"]["schedule_data_date"] == row["data_date"]
    assert associated["snapshot_json"]["period_cutoff_at"] != row["data_date"]
    assert associated["snapshot_json"]["data_date_is_not_cutoff"]


def test_baseline_sod_and_database_immutability(fixture):
    f = fixture
    row = accept(f, map_all(f, version(f, register(f))))
    candidate = success(
        request(f, "POST", f"/versions/{row['id']}/baselines", version=row["version"], payload=REASON), 201
    )
    for action in ("submit", "review"):
        candidate = success(
            request(f, "POST", f"/baselines/{candidate['id']}/{action}", version=candidate["version"], payload=REASON)
        )
    assert (
        request(
            f, "POST", f"/baselines/{candidate['id']}/approve", version=candidate["version"], payload=REASON
        ).status_code
        == 403
    )
    approved = success(
        request(
            f,
            "POST",
            f"/baselines/{candidate['id']}/approve",
            version=candidate["version"],
            actor="publisher",
            payload=REASON,
        )
    )
    with engine.connect() as connection:
        with pytest.raises(DBAPIError):
            connection.execute(
                text("UPDATE schedule_baselines SET snapshot_json='{}' WHERE id=:id"), {"id": approved["id"]}
            )
        connection.rollback()
    assert (
        request(f, "POST", f"/versions/{row['id']}/baselines", version=row["version"], payload=REASON).status_code
        == 409
    )
    successor = success(
        request(
            f,
            "POST",
            f"/versions/{row['id']}/baselines",
            version=row["version"],
            payload={**REASON, "previous_baseline_id": approved["id"]},
        ),
        201,
    )
    assert successor["previous_baseline_id"] == approved["id"]


def test_lookahead_and_unknown_criticality_are_non_cpm_queries(fixture):
    f = fixture
    row = version(f, register(f))
    items = success(request(f, "GET", f"/versions/{row['id']}/activities"))["items"]
    assert items[2]["near_critical"] == "UNKNOWN" and items[2]["criticality_authority"] == "UNKNOWN"
    assert items[0]["near_critical"] is True and items[1]["critical"] is True
    lookahead = success(request(f, "GET", f"/versions/{row['id']}/look-ahead"))
    assert lookahead["horizon_days"] == 28 and lookahead["query_contract_only"]
    assert not lookahead["cpm_calculation_performed"]
    assert success(request(f, "GET", f"/versions/{row['id']}/look-ahead?horizon_days=14"))["horizon_days"] == 14
    assert request(f, "GET", f"/versions/{row['id']}/look-ahead?horizon_days=367").status_code == 422
