"""Real field profile and daily-report lifecycles in isolated PostgreSQL."""

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from tests.field_operations_release_fixture import (
    REASON,
    action,
    call,
    command,
    create_core_chain,
    setup,
)
from tests.test_procurement_consumer_release import signatures
from tests.test_procurement_o2b_release import expect

from app.database.session import SessionLocal
from app.main import app


def test_field_core_report_and_shift_preserve_downstream_authority():
    if os.getenv("PYPMIS_O3A_FIXTURE") != "disposable-only":
        pytest.skip("Dedicated O3A PostgreSQL fixture required")
    with SessionLocal() as db, TestClient(app) as client:
        f = setup(db, client)
        before = signatures(f)
        create_core_chain(f)
        assert signatures(f) == before
        expect(call(f, "GET", f"/workfronts/{f.field_front['id']}", actor="foreign"), 404)
        expect(
            call(
                f,
                "POST",
                f"/workfronts/{f.field_front['id']}/actions",
                actor="field_supervisor",
                version=999,
                payload=REASON | {"action": "suspend"},
            ),
            412,
        )
        row = action(f, "daily-reports", f.field_report, "submit", actor="field_reporter")
        expect(
            call(
                f,
                "POST",
                "/labor",
                payload=REASON
                | {
                    "record_code": "LATE-LABOR",
                    "shift_id": f.field_shift["id"],
                    "workfront_id": f.field_front["id"],
                    "crew_id": f.field_crew["id"],
                    "trade": "CIVIL",
                    "headcount": 1,
                    "regular_hours": "1",
                },
            ),
            409,
        )
        row = action(f, "daily-reports", row, "review", actor="field_supervisor")
        expect(
            call(
                f,
                "POST",
                f"/daily-reports/{row['id']}/actions",
                actor="field_reporter",
                version=row["version"],
                payload=REASON | {"action": "approve"},
            ),
            403,
        )
        f.field_report = action(f, "daily-reports", row, "approve", actor="field_approver")
        assert f.field_report["status"] == "APPROVED"
        assert {pin["source_entity_type"] for pin in f.field_report["source_references"]} >= {"LABOR", "EQUIPMENT"}
        expect(
            call(
                f,
                "PUT",
                f"/daily-reports/{row['id']}",
                payload=REASON | f.field_report_body,
                version=f.field_report["version"],
            ),
            409,
        )
        closed = action(f, "daily-reports", f.field_report, "close", actor="field_approver")
        assert closed["status"] == "CLOSED" and closed["source_status"] == "APPROVED"
        with SessionLocal() as reader:
            raw = reader.execute(
                text("SELECT status,source_hash FROM field_daily_reports WHERE id=:id"), {"id": closed["id"]}
            ).one()
            assert raw.status == "APPROVED" and raw.source_hash == f.field_report["source_hash"]
        successor = command(f, f"/daily-reports/{closed['id']}/successor", version=closed["version"])
        assert successor["revision"] == 2 and successor["supersedes_id"] == closed["id"]
        assert signatures(f) == before
        shift = f.field_shift
        for value, actor in (("submit", "field_reporter"), ("approve", "field_approver"), ("close", "field_approver")):
            shift = action(f, "shifts", shift, value, actor=actor)
        assert shift["status"] == "CLOSED"
        expect(
            call(f, "PUT", f"/shifts/{shift['id']}", payload=REASON | f.field_shift_body, version=shift["version"]), 409
        )
        for table, identity in (
            ("field_daily_reports", closed["id"]),
            ("field_labor_usage", f.field_labor["id"]),
            ("field_shifts", shift["id"]),
        ):
            with SessionLocal() as connection, pytest.raises(DBAPIError):
                connection.execute(text(f"UPDATE {table} SET version=version+1 WHERE id=:id"), {"id": identity})
        target = Path(__file__).resolve().parents[2] / "outputs/.qa/wave-o3a-20261118/core-evidence.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {
                    "result": "PASS",
                    "tenant_id": f.tenant_id,
                    "project_workspace_id": f.project_workspace_id,
                    "iwp_id": f.field_released_iwp["id"],
                    "awp_release_state": f.field_released_iwp["release_state"],
                    "workfront_id": f.field_front["id"],
                    "shift_id": shift["id"],
                    "report_id": closed["id"],
                    "report_source_status": raw.status,
                    "report_effective_status": closed["status"],
                    "labor_id": f.field_labor["id"],
                    "equipment_id": f.field_equipment["id"],
                    "report_successor_id": successor["id"],
                    "downstream_hashes": before,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
