"""Isolated PostgreSQL validation of typed field facts and authority boundaries."""

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from tests.field_operations_release_fixture import (
    action,
    approve_report,
    call,
    command,
    create_core_chain,
    production_body,
    provider_reference,
    setup,
)
from tests.test_procurement_consumer_release import signatures
from tests.test_procurement_o2b_release import expect

from app.database.session import SessionLocal
from app.main import app


def test_execution_facts_negatives_corrections_and_no_automatic_consumers():
    if os.getenv("PYPMIS_O3A_FIXTURE") != "disposable-only":
        pytest.skip("Dedicated O3A disposable PostgreSQL required")
    with SessionLocal() as db, TestClient(app) as client:
        f = create_core_chain(setup(db, client, material_required=True))
        before = signatures(f)
        body = production_body(f)
        unreleased_iwp = command(
            f,
            f.awp_root + "/packages",
            {
                "package_code": "FIELD-UNRELEASED-IWP",
                "name": "Native unreleased package",
                "package_type": "IWP",
                "cwa_id": f.cwas[1]["id"],
            },
            actor="admin",
        )
        command(
            f,
            "/workfronts",
            f.field_front_body
            | {
                "workfront_code": "INVALID-AREA-PAIR",
                "cwa_id": None,
                "cwp_id": f.engineering_packages["CWP"][0]["id"],
                "iwp_id": unreleased_iwp["id"],
            },
            status=409,
        )
        unreleased_front = command(
            f,
            "/workfronts",
            f.field_front_body
            | {
                "workfront_code": "UNRELEASED-FRONT",
                "cwa_id": f.cwas[1]["id"],
                "iwp_id": unreleased_iwp["id"],
            },
        )
        unreleased_front = action(f, "workfronts", unreleased_front, "activate", actor="field_supervisor")
        unreleased_shift = command(
            f,
            "/shifts",
            f.field_shift_body
            | {
                "shift_code": "UNRELEASED-SHIFT",
                "workfront_id": unreleased_front["id"],
            },
        )
        unreleased_result = command(
            f,
            "/production",
            body
            | {
                "production_code": "UNRELEASED-PRODUCTION",
                "workfront_id": unreleased_front["id"],
                "shift_id": unreleased_shift["id"],
                "report_id": None,
                "iwp_id": unreleased_iwp["id"],
            },
            status=409,
        )
        assert unreleased_result["detail"]["code"] == "FIELD_RELEASED_IWP_REQUIRED"
        for changes, status in (
            ({"uom": "INVALID-UOM"}, 422),
            ({"engineering_reference": None}, 409),
            ({"material_reference": None}, 409),
            ({"engineering_reference": body["engineering_reference"] | {"source_hash": "0" * 64}}, 409),
            (
                {
                    "engineering_reference": body["engineering_reference"]
                    | {"source_version": body["engineering_reference"]["source_version"] + 1}
                },
                409,
            ),
            ({"document_reference": f.field_document_pin | {"attachment_id": 2147483647}}, 404),
            ({"scope_item_id": 2147483647}, 404),
            ({"observed_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()}, 422),
            ({"execution_condition": "SILENT_BYPASS", "exception_reason": "Invalid unconfigured exception"}, 422),
            ({"material_reference": body["engineering_reference"]}, 422),
        ):
            command(f, "/production", body | changes, status=status)
        command(f, "/production", body, actor="field_supervisor", status=403)
        original = command(f, "/production", body, actor="admin", key="field-record-idempotent")
        repeated = command(f, "/production", body, actor="admin", key="field-record-idempotent")
        assert repeated["id"] == original["id"]
        command(f, "/production", body | {"quantity": "9"}, actor="admin", key="field-record-idempotent", status=409)
        command(f, "/production", body | {"production_code": "DUPLICATE-EVIDENCE"}, status=409)
        action(f, "production", original, "verify", actor="field_reporter", status=403)
        action(f, "production", original, "verify", actor="admin", status=403)
        production = action(f, "production", original, "verify", actor="field_supervisor")
        assert production["status"] == "VERIFIED"
        action(f, "production", production, "reject", actor="field_supervisor", status=409)
        expect(call(f, "GET", f"/production/{production['id']}", actor="foreign"), 404)

        event = command(
            f,
            "/events",
            {
                "event_code": "FIELD-EVENT",
                "workfront_id": f.field_front["id"],
                "shift_id": f.field_shift["id"],
                "event_type": "ACCESS_ISSUE",
                "observed_at": body["observed_at"],
                "title": "Observed access restriction",
                "description": "Evidence only without contractual conclusion",
                "severity": "MEDIUM",
                "document_reference": f.field_document_pin,
            },
        )
        event = action(f, "events", event, "review", actor="field_supervisor")
        instruction = command(
            f,
            "/instructions",
            {
                "instruction_number": "FIELD-INSTRUCTION",
                "instruction_type": "GENERAL",
                "instruction_date": f.field_shift_body["shift_date"],
                "issuer": "Site supervision",
                "recipient": "Crew",
                "workfront_id": f.field_front["id"],
                "scope_item_id": f.scope_items[0]["id"],
                "iwp_id": f.field_released_iwp["id"],
                "description": "Operational instruction without change order",
                "document_reference": f.field_document_pin,
            },
        )
        action(f, "instructions", instruction, "issue", actor="field_reporter", status=403)
        instruction = action(f, "instructions", instruction, "issue", actor="field_instruction_issuer")
        observation = command(
            f,
            "/constraints",
            {
                "observation_code": "FIELD-OBSERVATION",
                "constraint_type": "ACCESS",
                "workfront_id": f.field_front["id"],
                "iwp_id": f.field_released_iwp["id"],
                "observation_date": f.field_shift_body["shift_date"],
                "description": "Unadopted access restriction fact",
                "document_reference": f.field_document_pin,
            },
        )
        observation = action(f, "constraints", observation, "verify", actor="field_supervisor")
        assert observation["status"] == "VERIFIED"
        action(f, "constraints", observation, "reject", actor="field_supervisor", status=409)

        rework = command(
            f,
            "/rework",
            body
            | {
                "production_code": "FIELD-REWORK",
                "production_type": "REWORKED",
                "original_production_id": production["id"],
                "rework_reason": "INSTALLATION",
                "responsible_party": "Operational crew",
                "quantity": "1",
            },
        )
        rework = action(f, "rework", rework, "verify", actor="field_approver")
        assert rework["original_production_id"] == production["id"] and rework["status"] == "VERIFIED"
        installed = expect(call(f, "GET", "/quantity-evidence"), 200)["items"]
        assert [row["id"] for row in installed] == [production["id"]]

        allocations = expect(call(f, "GET", "/reference-targets", params={"target_kind": "MATERIAL_ALLOCATION"}), 200)
        allocation_id = allocations["items"][0]["source_entity_id"]
        allocation = expect(
            call(f, "GET", "/source", params={"source_type": "MATERIAL_ALLOCATION", "source_id": allocation_id}), 200
        )
        material = command(
            f,
            "/material-consumption",
            {
                "consumption_code": "FIELD-CONSUMPTION",
                "production_record_id": production["id"],
                "material_item_id": allocation["facts"]["material_item_id"],
                "allocation_reference": provider_reference(f, "MATERIAL_ALLOCATION", allocation_id),
                "consumption_date": f.field_shift_body["shift_date"],
                "quantity": "1",
                "uom": allocation["facts"]["uom"],
                "document_reference": f.field_document_pin,
            },
        )
        assert material["status"] == "RECORDED"
        assert signatures(f) == before
        submitted = action(f, "daily-reports", f.field_report, "submit", actor="field_reporter")
        action(f, "events", event, "close", actor="field_supervisor", status=409)
        reviewed = action(f, "daily-reports", submitted, "review", actor="field_supervisor")
        approved = action(f, "daily-reports", reviewed, "approve", actor="field_approver")
        f.field_report = approved
        assert any(
            row["source_entity_id"] == material["id"]
            for row in approved["source_references"]
            if row["source_entity_type"] == "MATERIAL_CONSUMPTION"
        )
        assert any(
            row["source_entity_id"] == production["id"]
            for row in approved["source_references"]
            if row["source_entity_type"] == "PRODUCTION"
        )
        command(f, "/production", body | {"production_code": "LATE-UNCONTROLLED"}, status=409)
        successor_report = command(f, f"/daily-reports/{approved['id']}/successor", version=approved["version"])
        f.field_report = successor_report
        correction_body = body | {
            "report_id": successor_report["id"],
            "supersedes_id": production["id"],
            "quantity": "1.5",
        }
        correction = command(f, "/production", correction_body)
        correction = action(f, "production", correction, "verify", actor="field_supervisor")
        corrected_report = approve_report(f)
        production_pins = [
            row for row in corrected_report["source_references"] if row["source_entity_type"] == "PRODUCTION"
        ]
        assert {row["source_entity_id"] for row in production_pins} == {correction["id"], rework["id"]}
        dashboard = expect(call(f, "GET", "/dashboard"), 200)
        assert float(dashboard["verified_production_by_uom"][body["uom"]]) == 1.5
        assert signatures(f) == before

        for table, identity in (
            ("field_production_records", production["id"]),
            ("field_production_records", correction["id"]),
            ("field_constraint_observations", observation["id"]),
            ("field_material_consumption", material["id"]),
        ):
            with SessionLocal() as connection, pytest.raises(DBAPIError):
                connection.execute(text(f"UPDATE {table} SET version=version+1 WHERE id=:id"), {"id": identity})
        for endpoint, params in (
            ("/dashboard", {}),
            ("/lookahead", {}),
            ("/readiness", {"workfront_id": f.field_front["id"]}),
            ("/trace", {"entity_type": "PRODUCTION", "entity_id": correction["id"]}),
            ("/history", {}),
        ):
            expect(call(f, "GET", endpoint, params=params), 200)
        target = Path(__file__).resolve().parents[2] / "outputs/.qa/wave-o3a-20261118/execution-evidence.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {
                    "result": "PASS",
                    "tenant_id": f.tenant_id,
                    "project_workspace_id": f.project_workspace_id,
                    "iwp_id": f.field_released_iwp["id"],
                    "production_id": production["id"],
                    "correction_id": correction["id"],
                    "rework_id": rework["id"],
                    "approved_report_id": approved["id"],
                    "corrected_report_id": corrected_report["id"],
                    "event_id": event["id"],
                    "instruction_id": instruction["id"],
                    "constraint_observation_id": observation["id"],
                    "material_consumption_id": material["id"],
                    "downstream_hashes": before,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
