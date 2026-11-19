"""Real HTTP/SQL O2B acceptance on a disposable PostgreSQL Project."""

import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from tests.engineering_release_fixture import TODAY, approve, link, release, request, revision_body
from tests.procurement_release_fixture import REASON, call, create_procurement_fixture

from app.database.session import SessionLocal, engine
from app.main import app


@pytest.fixture(scope="module")
def project():
    if os.getenv("PYPMIS_O2B_FIXTURE") != "disposable-only":
        pytest.skip("Dedicated disposable O2B PostgreSQL required")
    assert engine.dialect.name == "postgresql" and engine.url.database == "o2b" and engine.url.port == 5555
    with TestClient(app) as client, SessionLocal() as db:
        yield create_procurement_fixture(db, client)


def expect(response, status):
    assert response.status_code == status, response.text
    return response.json()


def cmd(f, path, body, *, actor="buyer", version=None, status=201, key=None, method="POST"):
    return expect(call(f, method, path, actor=actor, payload={**REASON, **body}, version=version, key=key), status)


def get(f, path, **params):
    return expect(call(f, "GET", path, params=params), 200)


def transition(f, resource, row, action, *, actor="buyer", status=200):
    return cmd(
        f, f"/{resource}/{row['id']}/actions", {"action": action}, actor=actor, version=row["version"], status=status
    )


def mapping(f, kind, identity, target, target_id=None, *, status=201, **kwargs):
    version = get(f, "/mappings", source_kind=kind, source_id=identity)["version"]
    return cmd(
        f,
        "/mappings",
        {"source_kind": kind, "source_id": identity, "target_kind": target, "target_id": target_id, **kwargs},
        version=version,
        status=status,
    )


def authority_counts(f):
    with SessionLocal() as db:
        # All names are fixed; no dynamic untrusted SQL.
        tables = (
            "scope_items",
            "scope_plan_items",
            "schedule_versions",
            "engineering_releases",
            "cost_budget_versions",
            "progress_measurements",
            "forecast_versions",
            "purchase_orders",
            "warehouse_receipts",
            "contracts",
        )
        return {
            table: db.scalar(text(f"SELECT count(*) FROM {table} WHERE tenant_id=:tenant"), {"tenant": f.tenant_id})
            for table in tables
        }


def test_o2b_critical_chain_and_fail_closed_boundaries(project):
    exercise_procurement_chain(project)


def exercise_procurement_chain(f, *, with_quarantine=False, verify_ifc_supersession=True):
    before = authority_counts(f)
    today = TODAY.isoformat()
    due = (TODAY + timedelta(days=14)).isoformat()
    pin = {"target_kind": "IFC_RELEASE", "target_id": f.ifc["id"], "source_hash": f.ifc["release_hash"]}
    cde = {"document_id": f.document["id"], "attachment_id": f.attachment["id"]}
    pack = {
        "package_code": "O2B-PACKAGE",
        "title": "Controlled steel supply",
        "procurement_type": "MATERIAL",
        "category": "GENERAL",
        "discipline": "STRUCTURAL",
        "sourcing_method": "RFQ",
        "required_on_site_date": due,
        "planned_rfq_date": today,
        "planned_award_date": today,
        "planned_po_date": today,
        "forecast_delivery_date": due,
    }
    cmd(f, "/packages", pack, actor="receiver", status=403)
    assert call(f, "GET", "/packages", actor="foreign").status_code in {403, 404}
    other = f.workspaces["other_project"].id
    assert call(f, "GET", f"/api/v1/procurement/projects/{other}/packages").status_code in {403, 404}
    replay = "o2b-package-" + uuid4().hex
    package = cmd(f, "/packages", pack, key=replay)
    assert cmd(f, "/packages", pack, key=replay) == package
    cmd(f, "/packages", pack | {"title": "Not an idempotent retry"}, key=replay, status=409)
    cmd(f, f"/packages/{package['id']}", pack, version=999, method="PUT", status=412)
    assert package["id"] != f.pwp["id"] or package["package_code"] != f.pwp["package_code"]
    edge = mapping(f, "PACKAGE", package["id"], "PWP", f.pwp["id"])
    mapping(f, "PACKAGE", package["id"], "CWP", f.engineering_packages["CWP"][0]["id"])
    assert edge["target_snapshot_json"]["target_id"] == f.pwp["id"]
    version = f.current_schedule_version["id"]
    mapping(
        f, "PACKAGE", package["id"], "ACTIVITY", schedule_version_id=version, external_id="unknown-object", status=422
    )
    mapping(f, "PACKAGE", package["id"], "ACTIVITY", schedule_version_id=version, external_id="5001")

    need = {
        "requirement_code": "BUY-STEEL",
        "package_id": package["id"],
        "description": "Specified steel",
        "item_type": "MATERIAL",
        "required_quantity": "10",
        "uom": "EA",
        "required_on_site_date": due,
        "source_reference": pin,
    }
    cmd(f, "/requirements", need | {"source_reference": pin | {"source_hash": "0" * 64}}, status=409)
    requirement = cmd(f, "/requirements", need)
    requirement = transition(f, "requirements", requirement, "activate")
    assert requirement["source_hash"] == f.ifc["release_hash"]
    mapping(f, "REQUIREMENT", requirement["id"], "IWP", f.iwp["id"])
    requisition = cmd(
        f,
        "/requisitions",
        {
            "requisition_number": "REQ-O2B",
            "package_id": package["id"],
            "issue_date": today,
            "required_date": due,
            "currency": "USD",
            "technical_reference": pin,
            "document_reference": cde,
            "lines": [
                {
                    "line_number": 1,
                    "requirement_id": requirement["id"],
                    "description": "Steel",
                    "quantity": "10",
                    "uom": "EA",
                    "required_date": due,
                }
            ],
        },
    )
    rfq_body = {
        "rfq_number": "RFQ-O2B",
        "package_id": package["id"],
        "requisition_id": requisition["id"],
        "issue_date": today,
        "closing_date": today,
        "technical_package_reference": pin,
        "document_reference": cde,
    }
    cmd(f, "/rfqs", rfq_body, status=409)
    requisition = transition(f, "requisitions", requisition, "submit")
    transition(f, "requisitions", requisition, "approve", status=403)
    requisition = transition(f, "requisitions", requisition, "approve", actor="req_approver")
    rfq = cmd(f, "/rfqs", rfq_body)
    transition(f, "rfqs", rfq, "issue", actor="rfq_issuer", status=409)
    vendors = [
        cmd(
            f,
            "/vendors",
            {
                "vendor_code": f"O2B-V-{i}",
                "legal_name": f"Synthetic Steel {i}",
                "display_name": f"Steel {i}",
                "business_identifier": f"O2B-{i}",
                "country": "CO",
            },
            actor="admin",
        )
        for i in (1, 2)
    ]
    for vendor in vendors:
        rfq = cmd(f, f"/rfqs/{rfq['id']}/invitations", {"vendor_id": vendor["id"]}, version=rfq["version"])
    rfq = transition(f, "rfqs", rfq, "issue", actor="rfq_issuer")
    bids = [
        cmd(
            f,
            "/bids",
            {
                "rfq_id": rfq["id"],
                "vendor_id": vendor["id"],
                "currency": "USD",
                "total_bid_value": str(100 + index * 20),
                "validity_date": due,
                "document_reference": cde,
            },
        )
        for index, vendor in enumerate(vendors)
    ]
    rfq = transition(f, "rfqs", rfq, "close", actor="rfq_issuer")
    award_body = {"rfq_id": rfq["id"], "bid_id": bids[0]["id"], "approval_reference": "Independent sourcing decision"}
    cmd(f, "/awards", award_body, actor="award_approver", status=409)
    for kind, actor in (("TECHNICAL", "technical"), ("COMMERCIAL", "commercial")):
        body = {"bid_id": bids[0]["id"], "evaluation_type": kind, "result": "ACCEPTED", "recommendation": "RECOMMEND"}
        if kind == "TECHNICAL":
            body["engineering_reference"] = pin
        cmd(f, "/evaluations", body, actor=actor)
    award = cmd(f, "/awards", award_body, actor="award_approver")
    po_body = {
        "po_number": "PO-O2B",
        "package_id": package["id"],
        "vendor_id": vendors[0]["id"],
        "currency": "USD",
        "issue_date": today,
        "effective_date": today,
        "expected_delivery_date": due,
        "document_reference": cde,
        "lines": [
            {
                "line_number": 1,
                "requirement_id": requirement["id"],
                "description": "Specified steel",
                "quantity": "10",
                "uom": "EA",
                "unit_price": "10",
                "requested_date": due,
            }
        ],
    }
    cmd(f, "/purchase-orders", po_body, status=409)
    po = cmd(f, "/purchase-orders", po_body | {"award_id": award["id"]})
    transition(f, "purchase-orders", po, "approve", status=403)
    po = transition(f, "purchase-orders", po, "approve", actor="po_approver")
    po = transition(f, "purchase-orders", po, "issue", actor="po_approver")
    po_line = get(f, f"/purchase-orders/{po['id']}")["lines"][0]
    assert Decimal(po["current_value"]) == 100

    item = cmd(
        f,
        "/material-items",
        {"material_code": "STEEL-PHYSICAL", "description": "Steel", "uom": "EA", "category": "GENERAL"},
        actor="material",
    )
    material = cmd(
        f,
        "/material-requirements",
        {
            "requirement_code": "IWP-STEEL",
            "material_item_id": item["id"],
            "procurement_requirement_id": requirement["id"],
            "required_quantity": "9",
            "uom": "EA",
            "required_on_site_date": due,
            "source_type": "BOM",
            "evidence": cde,
        },
        actor="material",
    )
    mapping(f, "MATERIAL_REQUIREMENT", material["id"], "IWP", f.iwp["id"])
    cmd(
        f,
        "/vendor-milestones",
        {
            "po_line_id": po_line["id"],
            "code": "MANUFACTURING_COMPLETE",
            "planned_date": today,
            "forecast_date": today,
            "actual_date": today,
        },
        actor="material",
    )
    inspection = cmd(
        f,
        "/inspections",
        {"po_line_id": po_line["id"], "inspection_type": "FACTORY", "inspection_date": today},
        actor="inspector",
    )
    inspection = cmd(
        f,
        f"/inspections/{inspection['id']}/decision",
        {"result": "ACCEPTED", "evidence": cde},
        actor="acceptor",
        version=inspection["version"],
        status=200,
    )
    shipment = cmd(
        f,
        "/shipments",
        {
            "shipment_number": "SHIP-O2B",
            "vendor_id": vendors[0]["id"],
            "origin": "Factory",
            "destination": "Site",
            "transport_mode": "ROAD",
            "planned_arrival": today,
            "forecast_arrival": today,
            "evidence": cde,
            "lines": [
                {"po_line_id": po_line["id"], "material_requirement_id": material["id"], "quantity": "10", "uom": "EA"}
            ],
        },
        actor="logistician",
    )
    for status in ("READY_FOR_DISPATCH", "DISPATCHED", "IN_TRANSIT", "ARRIVED"):
        shipment = cmd(
            f,
            f"/shipments/{shipment['id']}/transition",
            {"status": status, "event_date": today},
            actor="logistician",
            version=shipment["version"],
            status=200,
        )
    assert shipment["status"] == "ARRIVED" and not get(f, "/material-receipts")["items"]

    def availability():
        return get(f, "/material-availability", work_package_id=f.iwp["id"], as_of=today)

    assert availability()["status"] != "READY"
    receipt_line = {"shipment_line_id": shipment["lines"][0]["id"], "quantity": "10", "uom": "EA"}
    receipt_body = {
        "receipt_number": "RECEIPT-O2B",
        "shipment_id": shipment["id"],
        "location": "Site stock",
        "received_at": datetime.now(UTC).isoformat(),
        "evidence": cde,
        "lines": [receipt_line],
    }
    cmd(
        f,
        "/material-receipts",
        receipt_body | {"lines": [receipt_line | {"quantity": "11"}]},
        actor="receiver",
        status=409,
    )
    receipt = cmd(f, "/material-receipts", receipt_body, actor="receiver")
    assert not receipt.get("acceptances") and availability()["status"] != "READY"
    line = receipt["lines"][0]
    acceptance = {
        "receipt_line_id": line["id"],
        "inspection_id": inspection["id"],
        "accepted_quantity": "9",
        "rejected_quantity": "0.5" if with_quarantine else "1",
        "quarantine_quantity": "0.5" if with_quarantine else "0",
    }
    cmd(
        f,
        f"/material-receipts/{receipt['id']}/acceptance",
        acceptance,
        actor="receiver",
        version=receipt["version"],
        status=403,
    )
    cmd(f, f"/material-receipts/{receipt['id']}/acceptance", acceptance, actor="acceptor", version=receipt["version"])
    allocation = {
        "receipt_line_id": line["id"],
        "material_requirement_id": material["id"],
        "work_package_id": f.iwp["id"],
        "quantity": "9",
        "uom": "EA",
        "allocation_date": today,
        "source_location": "Site stock",
    }
    cmd(f, "/material-allocations", allocation | {"quantity": "10"}, actor="material", status=409)
    cmd(f, "/material-allocations", allocation, actor="material")
    ready = availability()
    assert ready["status"] == "READY" and len(ready["evidence_hash"]) == 64, ready
    assert authority_counts(f) == before
    overview = expect(request(f, "GET", f.awp_root + "/overview", actor="awp_manager"), 200)
    iwp = next(row for row in overview["packages"] if row["id"] == f.iwp["id"])
    assert iwp["release_state"] == "NOT_RELEASED"
    assessment = expect(
        request(
            f,
            "POST",
            f.awp_root + f"/packages/{iwp['id']}/assess",
            actor="awp_manager",
            version=iwp["version"],
            payload={**REASON, "as_of": today, "evidence_json": {}},
        ),
        201,
    )
    assert assessment["source_hashes"]["material"] == ready["evidence_hash"]
    assert assessment["package"]["release_state"] == "NOT_RELEASED"
    assert get(f, "/trace", package_id=package["id"])["records"]["ACCEPTANCE"][0]["id"]
    facts = get(f, "/source-facts", package_id=package["id"])
    assert {row["kind"] for row in facts["progress"]} == {"MANUFACTURING", "DISPATCH", "RECEIPT", "ACCEPTANCE"}
    assert {row["kind"] for row in facts["cost"]} == {"AWARD", "PO"}
    assert get(f, "/lookahead", package_id=package["id"], start=today, end=due)["items"]
    assert get(f, "/readiness", package_id=package["id"])["status"] == "READY"

    with SessionLocal() as db:
        for statement, identity in (
            ("UPDATE procurement_requisitions SET notes='overwrite' WHERE id=:identity", requisition["id"]),
            ("UPDATE procurement_purchase_orders SET current_value=0 WHERE id=:identity", po["id"]),
            ("UPDATE procurement_purchase_orders SET status='DRAFT' WHERE id=:identity", po["id"]),
            ("UPDATE procurement_purchase_orders SET issued_by=NULL WHERE id=:identity", po["id"]),
            ("UPDATE procurement_awards SET approval_reference='overwrite' WHERE id=:identity", award["id"]),
            ("DELETE FROM procurement_mappings WHERE id=:identity", edge["id"]),
        ):
            with pytest.raises(DBAPIError), db.begin_nested():
                db.execute(text(statement), {"identity": identity})

    if verify_ifc_supersession:
        successor = expect(
            request(
                f,
                "POST",
                f"/revisions/{f.engineering_revision['id']}/successor",
                version=f.engineering_revision["version"],
                payload=revision_body(revision_code="B"),
            ),
            201,
        )
        release(f, approve(f, link(f, successor, successor=True)))
        cmd(f, "/requirements", need | {"requirement_code": "STALE-TECH"}, status=409)
    return {
        "package": package,
        "requirement": requirement,
        "award": award,
        "po": po,
        "po_line": po_line,
        "shipment": shipment,
        "receipt": receipt,
        "inspection": inspection,
        "material_requirement": material,
    }
