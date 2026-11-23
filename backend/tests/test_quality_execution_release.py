"""PostgreSQL Quality remediation using real Field and Procurement authorities."""

import json
import os
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from tests.engineering_release_fixture import TODAY
from tests.field_operations_release_fixture import action as field_action
from tests.field_operations_release_fixture import command as field_command
from tests.field_operations_release_fixture import production_body
from tests.quality_release_fixture import (
    REASON,
    action,
    call,
    close_inspection,
    command,
    create_inspection,
    create_itp,
    pin,
    release_control,
    setup,
    source,
)
from tests.test_procurement_consumer_release import TABLES, signatures
from tests.test_procurement_o2b_release import expect

from app.database.session import SessionLocal
from app.main import app

pytestmark = pytest.mark.skipif(
    os.getenv("PYPMIS_O3B_FIXTURE") != "disposable-only", reason="Dedicated O3B PostgreSQL required"
)
QA = Path(__file__).resolve().parents[2] / "outputs/.qa/wave-o3b-20261119"
UNTOUCHED = (
    *TABLES,
    "awp_work_packages",
    "awp_execution_constraints",
    "procurement_material_receipt_lines",
    "procurement_material_acceptances",
    "procurement_material_allocations",
    "operational_contracts",
    "commercial_commitments",
)


def readiness(f):
    return expect(
        call(
            f,
            "GET",
            "/readiness",
            params={
                "itp_id": f.quality_itp["id"],
                "source_type": f.quality_subject["source_type"],
                "source_id": f.quality_subject["source_id"],
            },
        ),
        200,
    )


def lookahead(f, **filters):
    return expect(
        call(
            f,
            "GET",
            "/lookahead",
            params={
                "iwp_id": f.field_released_iwp["id"],
                "workfront_id": f.field_front["id"],
                "discipline": "CIVIL",
                "inspector_user_id": f.users["quality_inspector"].id,
                **filters,
            },
        ),
        200,
    )


def acceptance_body(f, **changes):
    return {
        "acceptance_code": "QUALITY-ACCEPT",
        "subject_reference": f.quality_subject,
        "itp_id": f.quality_itp["id"],
        "quantity": "1",
        "uom": f.scope_items[0]["unit"],
        "effective_at": datetime.now(UTC).isoformat(),
        "document_reference": f.quality_document_pin,
        **changes,
    }


def ncr_body(f, failed):
    return {
        "ncr_number": "QUALITY-NCR",
        "title": "Installation outside approved tolerance",
        "description": "Actual failed Quality inspection requires governed Field rework",
        "category": "WORKMANSHIP",
        "severity": "HIGH",
        "responsible_user_id": f.users["ncr_owner"].id,
        "subject_reference": f.quality_subject,
        "inspection_record_id": failed["id"],
        "requirement_reference": "Current IFC installation tolerance",
        "detected_at": datetime.now(UTC).isoformat(),
        "due_date": TODAY.isoformat(),
        "document_reference": f.quality_document_pin,
    }


def sql_immutable(f, table, identity):
    with SessionLocal() as db:
        with pytest.raises(DBAPIError):
            with db.begin_nested():
                db.execute(
                    text(f"UPDATE {table} SET source_hash=:hash WHERE id=:identity AND tenant_id=:tenant"),
                    {"hash": "0" * 64, "identity": identity, "tenant": f.tenant_id},
                )


def test_real_failed_work_rework_reinspection_acceptance_and_receiving_quality():
    with SessionLocal() as db, TestClient(app) as client:
        f = setup(db, client)
        create_itp(f)
        before = signatures(f, UNTOUCHED)
        original_subject = deepcopy(f.quality_subject)
        initial_ready = readiness(f)
        assert initial_ready["state"] == "NOT_READY" and initial_ready["awp_release_changed"] is False
        command(f, "/acceptances", acceptance_body(f), actor="quality_approver", status=409)

        passed = close_inspection(f, create_inspection(f, code="QUALITY-PASS-FIRST"))
        # A closed PASS is still not a HOLD release.
        command(f, "/acceptances", acceptance_body(f), actor="quality_approver", status=409)
        pending_hold = lookahead(f, status="PENDING_RELEASE")
        assert [row["itp_item_id"] for row in pending_hold["hold_witness_pending"]] == [f.quality_item["id"]]
        assert pending_hold["hold_witness_pending"][0]["request_id"] == passed["request_id"]
        assert pending_hold["hold_witness_pending"][0]["control_type"] == "HOLD"
        assert not lookahead(f, discipline="OTHER-DISCIPLINE")["hold_witness_pending"]
        vendor_pending = lookahead(
            f,
            vendor_id=f.chain["po"]["vendor_id"],
            date_from=datetime.now(UTC).date().isoformat(),
            location="SCOPE",
        )
        assert [row["request_id"] for row in vendor_pending["hold_witness_pending"]] == [passed["request_id"]]
        release_control(f, passed)
        assert readiness(f)["state"] == "READY"
        ready_acceptance = lookahead(f, status="READY_FOR_ACCEPTANCE")
        assert ready_acceptance["hold_witness_pending"] == []
        assert [row["itp_id"] for row in ready_acceptance["acceptance_pending"]] == [f.quality_itp["id"]]
        assert float(ready_acceptance["acceptance_pending"][0]["controlled_quantity"]) == 1
        assert ready_acceptance["acceptance_pending"][0]["accepted_quantity"] in {"0", 0}
        for change in ({"uom": "INVALID"}, {"quantity": "999"}):
            command(f, "/acceptances", acceptance_body(f, **change), actor="quality_approver", status=422)
        # The actual Production is 2 EA but the closed request/result covers only
        # 1 EA. A current PASS must not silently approve the uninspected balance.
        over_coverage = command(
            f, "/acceptances", acceptance_body(f, quantity="2"), actor="quality_approver", status=409
        )
        assert over_coverage["detail"]["code"] == "QUALITY_ACCEPTANCE_QUANTITY_EXCEEDS_INSPECTED_OR_TESTED_COVERAGE"
        first_acceptance = command(
            f, "/acceptances", acceptance_body(f), actor="quality_approver", key="quality-acceptance-idempotent"
        )
        assert first_acceptance["quantity"] == "1" or float(first_acceptance["quantity"]) == 1
        accepted_lookahead = lookahead(f)
        assert accepted_lookahead["hold_witness_pending"] == []
        assert accepted_lookahead["acceptance_pending"] == []
        assert signatures(f, UNTOUCHED) == before

        failed = close_inspection(f, create_inspection(f, result="FAIL", code="QUALITY-FAIL-SECOND"))
        old = expect(call(f, "GET", f"/acceptances/{first_acceptance['id']}"), 200)
        assert old["source_state"] == "STALE"
        command(
            f,
            "/acceptances",
            acceptance_body(f, supersedes_id=first_acceptance["id"]),
            actor="quality_approver",
            status=409,
        )
        action(f, "inspections", failed, "close", actor="quality_reviewer", status=409)
        sql_immutable(f, "quality_inspection_records", failed["id"])

        ncr_input = ncr_body(f, failed)
        ncr = command(f, "/ncrs", ncr_input, key="quality-ncr-idempotent")
        replay = command(f, "/ncrs", ncr_input, key="quality-ncr-idempotent")
        assert replay["id"] == ncr["id"]
        conflict = command(
            f,
            "/ncrs",
            ncr_input | {"description": "A materially different NCR command"},
            key="quality-ncr-idempotent",
            status=409,
        )
        assert conflict["detail"]["code"]
        stale = call(
            f,
            "POST",
            f"/ncrs/{ncr['id']}/actions",
            actor="quality_reporter",
            payload=REASON | {"action": "issue"},
            version=ncr["version"] + 1,
        )
        expect(stale, 412)
        ncr = action(f, "ncrs", ncr, "issue", actor="quality_reporter")
        ncr = action(f, "ncrs", ncr, "review", actor="quality_reviewer")
        disposition = command(
            f,
            "/dispositions",
            {
                "ncr_id": ncr["id"],
                "disposition_code": "QUALITY-REWORK",
                "disposition_type": "REWORK",
                "description": "Remove and reinstall the rejected connection using the current IFC",
                "document_reference": f.quality_document_pin,
            },
            actor="quality_approver",
        )
        action(f, "dispositions", disposition, "approve", actor="quality_approver", status=403)
        disposition = action(f, "dispositions", disposition, "approve", actor="quality_manager")
        ncr = action(f, "ncrs", ncr, "disposition", actor="quality_approver", disposition_id=disposition["id"])
        assert ncr["status"] == "DISPOSITIONED"
        action(f, "ncrs", ncr, "correct", actor="ncr_owner", status=409)
        corrective = command(
            f,
            "/corrective-actions",
            {
                "action_code": "QUALITY-CORRECTIVE",
                "ncr_id": ncr["id"],
                "description": "Execute actual Field rework and submit an independent reinspection",
                "owner_user_id": f.users["ncr_owner"].id,
                "due_date": TODAY.isoformat(),
                "subject_reference": original_subject,
                "document_reference": f.quality_document_pin,
            },
            actor="ncr_owner",
        )
        corrective = action(f, "corrective-actions", corrective, "start", actor="ncr_owner")
        action(
            f,
            "corrective-actions",
            corrective,
            "complete",
            actor="ncr_owner",
            document_reference=f.quality_document_pin,
            status=422,
        )
        unrelated_material = pin(source(f, "MATERIAL_RECEIPT_LINE", f.chain["receipt"]["lines"][0]["id"]))
        action(
            f,
            "corrective-actions",
            corrective,
            "complete",
            actor="ncr_owner",
            completion_field_reference=unrelated_material,
            document_reference=f.quality_document_pin,
            status=409,
        )
        # Quality cannot post the physical correction. A Field reporter and independent
        # Field verifier create the actual retrabajo after the disposition decision.
        body = production_body(
            f,
            production_code="QUALITY-ACTUAL-REWORK",
            production_type="REWORKED",
            original_production_id=f.field_production["id"],
            rework_reason="INSTALLATION",
            responsible_party="Actual installation crew",
            quantity="1",
        )
        field_command(f, "/rework", body, actor="quality_reporter", status=403)
        rework = field_command(f, "/rework", body)
        rework = field_action(f, "rework", rework, "verify", actor="field_approver")
        assert rework["created_at"] >= disposition["approved_at"]
        rework_pin = pin(source(f, "FIELD_REWORK", rework["id"]))
        corrective = action(
            f,
            "corrective-actions",
            corrective,
            "complete",
            actor="ncr_owner",
            completion_field_reference=rework_pin,
            document_reference=f.quality_document_pin,
        )
        ncr = action(f, "ncrs", ncr, "correct", actor="ncr_owner")
        assert ncr["status"] == "CORRECTED"
        action(f, "ncrs", ncr, "verify", actor="quality_approver", status=409)

        reinspected = close_inspection(
            f,
            create_inspection(
                f, reinspection_of_id=failed["id"], corrective_action_id=corrective["id"], code="QUALITY-REINSPECTION"
            ),
        )
        assert reinspected["result"] == "PASS" and reinspected["id"] != failed["id"]
        verification = expect(
            call(
                f,
                "GET",
                "/quality-source",
                params={"source_entity_type": "INSPECTION", "source_entity_id": reinspected["id"]},
            ),
            200,
        )
        verification = {
            key: verification[key]
            for key in ("source_entity_type", "source_entity_id", "source_version", "source_hash")
        }
        action(
            f,
            "corrective-actions",
            corrective,
            "verify",
            actor="ncr_owner",
            verification_reference=verification,
            document_reference=f.quality_document_pin,
            status=403,
        )
        corrective = action(
            f,
            "corrective-actions",
            corrective,
            "verify",
            actor="quality_reviewer",
            verification_reference=verification,
            document_reference=f.quality_document_pin,
        )
        action(f, "ncrs", ncr, "verify", actor="quality_manager", status=403)
        ncr = action(f, "ncrs", ncr, "verify", actor="quality_approver")
        ncr = action(f, "ncrs", ncr, "close", actor="quality_approver")
        assert ncr["status"] == "CLOSED"
        action(f, "ncrs", ncr, "issue", actor="quality_reporter", status=409)
        sql_immutable(f, "quality_ncrs", ncr["id"])
        release_control(f, reinspected, version=f.quality_control["version"])
        punch = command(
            f,
            "/punch-items",
            {
                "item_number": "QUALITY-PUNCH",
                "subject_reference": original_subject,
                "description": "Complete the installation identification before quality acceptance",
                "category": "DOCUMENTATION",
                "responsible_user_id": f.users["ncr_owner"].id,
                "due_date": TODAY.isoformat(),
                "document_reference": f.quality_document_pin,
            },
        )
        assert readiness(f)["state"] != "READY"
        command(
            f,
            "/acceptances",
            acceptance_body(f, supersedes_id=first_acceptance["id"]),
            actor="quality_approver",
            status=409,
        )
        due = expect(
            call(
                f,
                "GET",
                "/lookahead",
                params={"iwp_id": f.field_released_iwp["id"], "workfront_id": f.field_front["id"], "status": "OPEN"},
            ),
            200,
        )
        assert [item["id"] for item in due["punch_items"]] == [punch["id"]]
        action(
            f,
            "punch-items",
            punch,
            "ready",
            actor="quality_reporter",
            document_reference=f.quality_document_pin,
            status=409,
        )
        punch = action(f, "punch-items", punch, "start", actor="quality_reporter")
        punch = action(
            f, "punch-items", punch, "ready", actor="quality_reporter", document_reference=f.quality_document_pin
        )
        action(
            f,
            "punch-items",
            punch,
            "close",
            actor="quality_reporter",
            verification_result="PASS",
            document_reference=f.quality_document_pin,
            status=403,
        )
        punch = action(
            f,
            "punch-items",
            punch,
            "close",
            actor="quality_reviewer",
            verification_result="PASS",
            document_reference=f.quality_document_pin,
        )
        assert punch["status"] == "CLOSED"
        assert readiness(f)["state"] == "READY"
        accepted = command(
            f, "/acceptances", acceptance_body(f, supersedes_id=first_acceptance["id"]), actor="quality_approver"
        )
        assert accepted["revision"] == 2 and accepted["supersedes_id"] == first_acceptance["id"]
        sql_immutable(f, "quality_acceptances", accepted["id"])
        historical = expect(call(f, "GET", f"/inspections/{failed['id']}"), 200)
        assert historical["result"] == "FAIL" and historical["source_hash"] == failed["source_hash"]
        assert expect(call(f, "GET", f"/acceptances/{first_acceptance['id']}"), 200)["source_state"] == "SUPERSEDED"
        trace = expect(call(f, "GET", "/trace", params={"entity_type": "ACCEPTANCE", "entity_id": accepted["id"]}), 200)
        assert trace["ncrs"] and trace["corrective_actions"]
        expect(call(f, "GET", f"/ncrs/{ncr['id']}", actor="foreign"), 404)
        assert signatures(f, UNTOUCHED) == before

        # Receiving inspection consumes the existing receipt line, without mutating
        # receipt quantities, logistic acceptance, stock or native material allocation.
        receipt_line = f.chain["receipt"]["lines"][0]
        receiving_subject = pin(source(f, "MATERIAL_RECEIPT_LINE", receipt_line["id"]))
        receiving_itp = command(
            f,
            "/itps",
            f.quality_itp_body
            | {
                "code": "QUALITY-RECEIVING-ITP",
                "title": "Material receiving technical quality",
                "source_references": [],
            },
        )
        receiving_item = command(
            f,
            "/itp-items",
            f.quality_item_body
            | {"itp_id": receiving_itp["id"], "itp_item_code": "RECEIVING-TECHNICAL", "control_type": "RECORD"},
        )
        receiving_itp = action(f, "itps", receiving_itp, "submit", actor="quality_reporter")
        receiving_itp = action(f, "itps", receiving_itp, "approve", actor="quality_approver")
        f.quality_itp, f.quality_item, f.quality_subject = receiving_itp, receiving_item, receiving_subject
        receiving = close_inspection(
            f,
            create_inspection(
                f,
                subject_reference=receiving_subject,
                code="QUALITY-RECEIVING",
                inspection_type="RECEIVING",
                uom=receipt_line["uom"],
            ),
        )
        receiving_acceptance = command(
            f,
            "/acceptances",
            acceptance_body(f, acceptance_code="QUALITY-MATERIAL-ACCEPT", uom=receipt_line["uom"]),
            actor="quality_approver",
        )
        assert receiving_acceptance["subject_reference"]["source_id"] == receipt_line["id"]
        assert receiving_acceptance["subject_reference"]["source_domain"] == "PROCUREMENT"
        assert signatures(f, UNTOUCHED) == before
        successor_itp = command(
            f, f"/itps/{receiving_itp['id']}/successor", version=receiving_itp["version"], status=201
        )
        successor_itp = action(f, "itps", successor_itp, "submit", actor="quality_reporter")
        successor_itp = action(f, "itps", successor_itp, "approve", actor="quality_approver")
        stale_readiness = readiness(f)
        assert stale_readiness["state"] == "STALE" and stale_readiness["awp_release_changed"] is False
        assert expect(call(f, "GET", f"/acceptances/{receiving_acceptance['id']}"), 200)["source_state"] == "STALE"
        (QA / "execution").mkdir(parents=True, exist_ok=True)
        (QA / "execution/real-remediation.json").write_text(
            json.dumps(
                {
                    "tenant_id": f.tenant_id,
                    "project_workspace_id": f.project_workspace_id,
                    "original_production_id": f.field_production["id"],
                    "first_acceptance_id": first_acceptance["id"],
                    "failed_inspection_id": failed["id"],
                    "ncr_id": ncr["id"],
                    "disposition_id": disposition["id"],
                    "real_field_rework_id": rework["id"],
                    "corrective_action_id": corrective["id"],
                    "reinspection_id": reinspected["id"],
                    "successor_acceptance_id": accepted["id"],
                    "receiving_inspection_id": receiving["id"],
                    "receiving_acceptance_id": receiving_acceptance["id"],
                    "unchanged_native_signatures_before": before,
                    "unchanged_native_signatures_after": signatures(f, UNTOUCHED),
                    "historical_fail_preserved": True,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
