"""Actual Quality core lifecycles and security in the guarded O3B PostgreSQL fixture."""

import json
import os
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from tests.quality_release_fixture import (
    REASON,
    action,
    call,
    close_inspection,
    close_test,
    command,
    create_inspection,
    create_itp,
    create_test,
    release_control,
    root,
    setup,
    source,
)
from tests.test_procurement_consumer_release import signatures
from tests.test_procurement_o2b_release import expect

from app.database.session import SessionLocal
from app.main import app
from app.modules.quality.policy import DEFAULT_PROFILE

QA_ROOT = Path(__file__).resolve().parents[2] / "outputs/.qa/wave-o3b-20261119"
QA = QA_ROOT / os.getenv("O3B_CORE_CUT", "backend-core")
assert QA.parent == QA_ROOT


@pytest.fixture(scope="module")
def quality():
    if os.getenv("PYPMIS_O3B_FIXTURE") != "disposable-only":
        pytest.skip("Dedicated O3B PostgreSQL fixture required")
    with SessionLocal() as db, TestClient(app) as client:
        f = setup(db, client)
        other = f.workspaces["other_project"]
        other.defaults_json = {**other.defaults_json, "enabled_modules": ["quality-manager"]}
        db.commit()
        f.native_before_quality = signatures(f)
        create_itp(f, test_required=True)
        inspection = close_inspection(f, create_inspection(f))
        test_record = close_test(f, create_test(f))
        f.baseline_inspection, f.baseline_test = inspection, test_record
        f.before_control = expect(
            call(
                f,
                "GET",
                "/readiness",
                params={
                    "itp_id": f.quality_itp["id"],
                    "source_type": "FIELD_PRODUCTION",
                    "source_id": f.field_production["id"],
                },
            ),
            200,
        )
        f.failed_acceptance_without_hold = call(
            f,
            "POST",
            "/acceptances",
            actor="quality_approver",
            payload=REASON
            | {
                "acceptance_code": "BYPASS-HOLD",
                "subject_reference": f.quality_subject,
                "itp_id": f.quality_itp["id"],
                "quantity": "1",
                "uom": f.scope_items[0]["unit"],
                "effective_at": datetime.now(UTC).isoformat(),
                "document_reference": f.quality_document_pin,
            },
        )
        release_control(f, inspection, test_record)
        yield f
        QA.mkdir(parents=True, exist_ok=True)
        (QA / "fixture-proof.json").write_text(
            json.dumps(
                {
                    "tenant_id": f.tenant_id,
                    "workspace_id": f.project_workspace_id,
                    "itp_id": f.quality_itp["id"],
                    "inspection_id": inspection["id"],
                    "test_id": test_record["id"],
                    "control_decision_id": f.quality_control["id"],
                    "hold_bypass_http": f.failed_acceptance_without_hold.status_code,
                    "downstream_unchanged": signatures(f) == f.native_before_quality,
                    "actual_database": "127.0.0.1:5567/o3b",
                    "ordinary_database_used": False,
                },
                indent=2,
            ),
            encoding="utf-8",
        )


def test_actual_plan_itp_inspection_test_hold_and_pure_readiness(quality):
    f = quality
    assert f.quality_plan["status"] == f.quality_itp["status"] == "APPROVED"
    assert f.baseline_inspection["status"] == f.baseline_test["status"] == "CLOSED"
    assert len(f.baseline_test["measurements"]) == 2
    assert (
        f.baseline_inspection["checklist_template"]["template_hash"]
        == f.quality_item["checklist_template"]["template_hash"]
    )
    assert f.before_control["state"] != "READY"
    expect(f.failed_acceptance_without_hold, 409)
    before = signatures(f)
    with SessionLocal() as db:
        quality_rows = db.scalar(
            text("SELECT count(*) FROM quality_history WHERE tenant_id=:tenant"), {"tenant": f.tenant_id}
        )
    for _ in range(2):
        ready = expect(
            call(
                f,
                "GET",
                "/readiness",
                params={
                    "itp_id": f.quality_itp["id"],
                    "source_type": "FIELD_PRODUCTION",
                    "source_id": f.field_production["id"],
                },
            ),
            200,
        )
        assert ready["state"] == "READY" and ready["awp_release_changed"] is False
    with SessionLocal() as db:
        assert (
            db.scalar(text("SELECT count(*) FROM quality_history WHERE tenant_id=:tenant"), {"tenant": f.tenant_id})
            == quality_rows
        )
    assert signatures(f) == before == f.native_before_quality


def test_hidden_scope_and_quality_actors_cannot_mutate_native_domains(quality):
    f = quality
    expect(call(f, "GET", f"/itps/{f.quality_itp['id']}", actor="foreign"), 404)
    expect(
        call(f, "GET", root(f, f.workspaces["other_project"].id) + f"/itps/{f.quality_itp['id']}", actor="admin"), 404
    )
    expect(call(f, "GET", "/itps", actor="field_reporter"), 403)
    for path in (
        "/api/v1/progress/projects/{}/measurements",
        "/api/v1/cost/projects/{}/actuals",
        "/api/v1/awp/projects/{}/packages",
        "/api/v1/contracts/projects/{}/contracts",
        "/api/v1/schedule/projects/{}/versions",
    ):
        response = call(f, "POST", path.format(f.project_workspace_id), payload=REASON, actor="quality_reporter")
        assert response.status_code in {403, 405, 422}, response.text
        # Schema/method rejection cannot be mistaken for an authorized mutation.
    assert signatures(f) == f.native_before_quality


def test_if_match_and_terminal_facts_are_not_editable(quality):
    f = quality
    submitted = call(
        f, "POST", f"/itps/{f.quality_itp['id']}/actions", version=999, payload=REASON | {"action": "submit"}
    )
    expect(submitted, 412)
    for resource, row, body, actor in (
        ("plans", f.quality_plan, f.quality_plan_body, "quality_reporter"),
        ("itps", f.quality_itp, f.quality_itp_body, "quality_reporter"),
        ("itp-items", f.quality_item, f.quality_item_body, "quality_reporter"),
        ("inspections", f.baseline_inspection, f.quality_inspection_body, "quality_inspector"),
        ("tests", f.baseline_test, f.quality_test_body, "quality_inspector"),
    ):
        expect(
            call(f, "PUT", f"/{resource}/{row['id']}", payload=REASON | body, version=row["version"], actor=actor), 409
        )
    expect(
        call(
            f,
            "POST",
            f"/plans/{f.quality_plan['id']}/actions",
            payload=REASON | {"action": "approve"},
            actor="quality_approver",
        ),
        422,
    )


def test_request_idempotency_replay_and_payload_misuse(quality):
    f = quality
    body = REASON | f.quality_request_body | {"request_number": "REPLAY-REQUEST"}
    key = f"o3b-request-replay-{f.token}"
    first = expect(call(f, "POST", "/inspection-requests", payload=body, key=key), 201)
    replay = expect(call(f, "POST", "/inspection-requests", payload=body, key=key), 201)
    assert first == replay
    expect(call(f, "POST", "/inspection-requests", payload=body | {"request_number": "MISUSE-REQUEST"}, key=key), 409)
    foreign = body | {
        "request_number": "BAD-SUBJECT",
        "subject_reference": f.quality_subject | {"source_id": f.workspaces["foreign"].id},
    }
    response = call(f, "POST", "/inspection-requests", payload=foreign)
    assert response.status_code in {404, 409}, response.text


def test_subject_units_quantities_and_future_observations_fail_closed(quality):
    f = quality
    for extra in ({"uom": "INVALID-UOM"}, {"quantity": "999999999999"}):
        body = REASON | f.quality_request_body | {"request_number": "BAD-QUANTITY"} | extra
        expect(call(f, "POST", "/inspection-requests", payload=body), 422)
    expect(
        call(
            f,
            "GET",
            "/source",
            params={
                "source_type": "IFC_RELEASE",
                "source_id": f.ifc["id"],
                "as_of": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            },
        ),
        422,
    )
    expect(
        call(
            f,
            "GET",
            "/source",
            params={
                "source_type": "IFC_RELEASE",
                "source_id": f.ifc["id"],
                "as_of": (datetime.now(UTC) - timedelta(days=30)).isoformat(),
            },
        ),
        409,
    )


def test_future_inspection_slot_uses_known_current_evidence_not_future_observations(quality):
    f = quality
    future = datetime.now(UTC) + timedelta(days=2)
    planned = command(
        f,
        "/inspection-requests",
        f.quality_request_body
        | {
            "request_number": "PLANNED-FUTURE-INSPECTION",
            "requested_for": future.isoformat(),
        },
    )
    assert planned["status"] == "DRAFT"
    with SessionLocal() as db:
        created, verified = db.execute(
            text("SELECT created_at,verified_at FROM field_production_records WHERE id=:id"),
            {"id": f.field_production["id"]},
        ).one()
    if created < verified:
        between = created + (verified - created) / 2
        expect(
            call(
                f,
                "GET",
                "/source",
                params={
                    "source_type": "FIELD_PRODUCTION",
                    "source_id": f.field_production["id"],
                    "as_of": between.replace(tzinfo=UTC).isoformat(),
                },
            ),
            409,
        )


def test_checklist_and_inspector_result_separation(quality):
    f = quality
    draft = create_inspection(f, result="FAIL", code="DRAFT-FAIL-CONTROL")
    pending = expect(
        call(
            f,
            "GET",
            "/readiness",
            params={
                "itp_id": f.quality_itp["id"],
                "source_type": "FIELD_PRODUCTION",
                "source_id": f.field_production["id"],
            },
        ),
        200,
    )
    assert pending["state"] != "READY"
    assert "inspection_record_not_passed" in pending["items"][0]["issues"]
    assert "inspection_record_independent_review_pending" in pending["items"][0]["issues"]
    expect(
        call(
            f,
            "PUT",
            f"/inspections/{draft['id']}",
            payload=REASON | f.quality_inspection_body | {"result": "PASS"},
            actor="quality_inspector",
            version=draft["version"],
        ),
        422,
    )
    submitted = action(f, "inspections", draft, "submit", actor="quality_inspector")
    expect(
        call(
            f,
            "POST",
            f"/inspections/{submitted['id']}/actions",
            payload=REASON | {"action": "close"},
            actor="quality_inspector",
            version=submitted["version"],
        ),
        403,
    )
    expect(
        call(
            f,
            "POST",
            f"/inspections/{submitted['id']}/actions",
            payload=REASON | {"action": "close"},
            actor="quality_reporter",
            version=submitted["version"],
        ),
        403,
    )
    # Leave the failed draft under review. It is never rewritten as a historical PASS.


def test_configured_measurement_limits_units_and_numeric_evidence_cannot_be_bypassed(quality):
    f = quality
    draft = create_test(f, code="DRAFT-TEST-LIMITS")
    for measurements in (
        [
            {
                "code": "BAD",
                "numeric_value": "999",
                "uom": "MPa",
                "lower_limit": "30",
                "upper_limit": "80",
                "result": "PASS",
            }
        ],
        [
            {
                "code": "BAD",
                "numeric_value": "40",
                "uom": "kPa",
                "lower_limit": "30",
                "upper_limit": "80",
                "result": "PASS",
            }
        ],
        [
            {
                "code": "BAD",
                "numeric_value": "40",
                "uom": "MPa",
                "lower_limit": "0",
                "upper_limit": "1000",
                "result": "PASS",
            }
        ],
        [{"code": "BAD", "qualitative_value": "Looks satisfactory", "result": "PASS"}],
    ):
        expect(
            call(
                f,
                "PUT",
                f"/tests/{draft['id']}",
                payload=REASON | f.quality_test_body | {"measurements": measurements},
                actor="quality_inspector",
                version=draft["version"],
            ),
            422,
        )
    equipment = source(f, "FIELD_EQUIPMENT_REFERENCE", f.field_equipment_ref["id"])
    calibration = {
        "source_reference": {
            key: equipment[key] for key in ("source_type", "source_id", "source_version", "source_hash")
        },
        "calibration_status": "VALID",
        "valid_from": (datetime.now(UTC) - timedelta(days=30)).isoformat(),
        "valid_to": (datetime.now(UTC) - timedelta(days=1)).isoformat(),
        "document_reference": f.quality_document_pin,
    }
    expect(
        call(
            f,
            "PUT",
            f"/tests/{draft['id']}",
            payload=REASON | f.quality_test_body | {"equipment_reference": calibration},
            actor="quality_inspector",
            version=draft["version"],
        ),
        409,
    )


def test_profile_hard_controls_independent_publish_and_version_frozen_checklist(quality):
    f = quality
    base = "/api/v1/quality/admin/profiles"
    profile = expect(call(f, "GET", base, actor="quality_configurator"), 200)
    published = next(row for row in profile["items"] if row["id"] == f.quality_profile["id"])
    successor = command(
        f, base + f"/{published['id']}/successor", actor="quality_configurator", version=published["version"]
    )
    content = deepcopy(DEFAULT_PROFILE)
    next(point for point in content["control_point_types"] if point["code"] == "HOLD")["allow_waiver"] = True
    expect(
        call(
            f,
            "PUT",
            base + f"/{successor['id']}",
            payload=REASON | {"name": "Unsafe hold waiver", "content_json": content},
            version=successor["version"],
            actor="quality_configurator",
        ),
        422,
    )
    content = deepcopy(DEFAULT_PROFILE)
    content["checklist_templates"][0]["items"][0]["label"] = "New template revision does not rewrite frozen executions"
    successor = expect(
        call(
            f,
            "PUT",
            base + f"/{successor['id']}",
            payload=REASON | {"name": "Second Quality template", "content_json": content},
            version=successor["version"],
            actor="quality_configurator",
        ),
        200,
    )
    expect(
        call(
            f,
            "POST",
            base + f"/{successor['id']}/publish",
            payload=REASON,
            version=successor["version"],
            actor="quality_configurator",
        ),
        403,
    )
    command(
        f, base + f"/{successor['id']}/publish", actor="quality_publisher", version=successor["version"], status=200
    )
    old = expect(call(f, "GET", f"/inspections/{f.baseline_inspection['id']}"), 200)
    assert old["checklist_template"] == f.baseline_inspection["checklist_template"]
    assert old["configuration_id"] == published["id"]


def test_postgresql_immutability_itp_child_and_simple_fk_parent_scope(quality):
    f = quality
    for table, identity in (
        ("quality_plans", f.quality_plan["id"]),
        ("quality_itps", f.quality_itp["id"]),
        ("quality_itp_items", f.quality_item["id"]),
        ("quality_inspection_records", f.baseline_inspection["id"]),
        ("quality_test_records", f.baseline_test["id"]),
        ("quality_control_point_decisions", f.quality_control["id"]),
    ):
        for operation in (f"UPDATE {table} SET version=version WHERE id=:id", f"DELETE FROM {table} WHERE id=:id"):
            with SessionLocal() as db, pytest.raises(DBAPIError):
                db.execute(text(operation), {"id": identity})
                db.commit()
    draft = command(f, "/plans", f.quality_plan_body | {"code": "SQL-PARENT-GUARD"})
    with SessionLocal() as db, pytest.raises(DBAPIError, match="scope mismatch"):
        db.execute(
            text("UPDATE quality_plans SET responsible_user_id=:foreign WHERE id=:id"),
            {"foreign": f.users["foreign"].id, "id": draft["id"]},
        )
        db.commit()
    with SessionLocal() as db, pytest.raises(DBAPIError, match="identity is immutable"):
        db.execute(
            text("UPDATE quality_plans SET project_workspace_id=:workspace WHERE id=:id"),
            {"workspace": f.workspaces["other_project"].id, "id": draft["id"]},
        )
        db.commit()


def test_same_project_subject_cannot_borrow_an_itp_from_another_canonical_scope(quality):
    f = quality
    other = command(
        f,
        "/itps",
        f.quality_itp_body
        | {
            "code": "OTHER-CANONICAL-SCOPE",
            "source_references": [{"target_kind": "SCOPE", "target_id": f.scope_items[1]["id"]}],
        },
    )
    item = command(f, "/itp-items", f.quality_item_body | {"itp_id": other["id"]})
    other = action(f, "itps", other, "submit", actor="quality_reporter")
    action(f, "itps", other, "approve", actor="quality_approver")
    denied = expect(
        call(
            f,
            "POST",
            "/inspection-requests",
            payload=REASON
            | f.quality_request_body
            | {"request_number": "WRONG-CANONICAL-SCOPE", "itp_item_id": item["id"]},
        ),
        409,
    )
    assert denied["detail"]["code"] == "QUALITY_SUBJECT_OUTSIDE_ITP_APPLICABILITY"


def test_itp_successor_keeps_history_and_old_version_rejected_for_new_request(quality):
    f = quality
    successor = command(f, f"/itps/{f.quality_itp['id']}/successor", version=f.quality_itp["version"])
    successor = action(f, "itps", successor, "submit", actor="quality_reporter")
    successor = action(f, "itps", successor, "approve", actor="quality_approver")
    assert successor["revision"] == 2
    old = expect(call(f, "GET", f"/itps/{f.quality_itp['id']}"), 200)
    assert old["status"] == "SUPERSEDED" and old["source_status"] == "APPROVED"
    with SessionLocal() as db:
        assert db.scalar(text("SELECT status FROM quality_itps WHERE id=:id"), {"id": old["id"]}) == "APPROVED"
    expect(
        call(
            f,
            "POST",
            "/inspection-requests",
            payload=REASON | f.quality_request_body | {"request_number": "SUPERSEDED-ITP-REJECTED"},
        ),
        409,
    )
    assert source(f, "FIELD_PRODUCTION", f.field_production["id"])["source_hash"] == f.quality_subject["source_hash"]
