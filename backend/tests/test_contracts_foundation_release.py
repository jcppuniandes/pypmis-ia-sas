"""Real PostgreSQL governed Contracts and Cost handoff; never on the user's DB."""

import json
import os
from datetime import timedelta
from pathlib import Path
from statistics import median
from time import perf_counter

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from tests.contracts_release_fixture import REASON, contract_root, setup
from tests.engineering_release_fixture import TODAY, request
from tests.test_procurement_consumer_release import signatures
from tests.test_procurement_o2b_release import expect

from app.database.session import SessionLocal
from app.main import app

CORE_SNAPSHOTS = (
    "contracts",
    "purchase_orders",
    "procurement_purchase_orders",
    "cost_commitment_references",
    "cost_budget_versions",
    "cost_actual_entries",
    "progress_measurements",
    "forecast_versions",
    "schedule_versions",
    "schedule_baselines",
    "payment_certificates",
)


def hit(f, method, path, *, actor="contract_preparer", data=None, version=None, status=200, key=None, params=None):
    uri = path if path.startswith("/api") else contract_root(f) + path
    response = request(f, method, uri, actor=actor, payload=data, version=version, key=key, params=params)
    return expect(response, status)


def create_chain(f, *, negative=False):
    po = f.chain["po"]
    source = hit(f, "GET", "/procurement-source", params={"source_type": "PO", "source_id": po["id"]})
    pin = {key: source[key] for key in ("source_type", "source_id", "source_version", "source_hash", "package_id")}
    pkg = {
        **REASON,
        "package_code": "PKG-O2C",
        "title": "Contracts validation package",
        "contract_type": "PURCHASE_ORDER_BASED_AGREEMENT",
        "commercial_model": "LUMP_SUM",
        "currency": po["currency"],
        "estimated_value": "100",
        "procurement_sources": [pin],
    }
    if negative:
        hit(f, "POST", "/packages", data=pkg, actor="buyer", status=403)
    package = hit(f, "POST", "/packages", data=pkg, status=201, key="o2c-package-governed")
    assert hit(f, "POST", "/packages", data=pkg, status=201, key="o2c-package-governed") == package
    if negative:
        hit(f, "POST", "/packages", data=pkg | {"title": "Changed"}, status=409, key="o2c-package-governed")
    package = hit(
        f, "POST", f"/packages/{package['id']}/actions", data=REASON | {"action": "plan"}, version=package["version"]
    )
    doc = {"document_id": f.document["id"], "attachment_id": f.attachment["id"]}
    contract_data = {
        **REASON,
        "contract_number": "AGREEMENT-O2C",
        "contract_package_id": package["id"],
        "title": "Governed PO-backed agreement",
        "vendor_id": po["vendor_id"],
        "governing_reference": "RFP package",
        "original_contract_value": "100",
        "effective_date": TODAY.isoformat(),
        "commencement_date": TODAY.isoformat(),
        "planned_completion_date": (TODAY + timedelta(days=90)).isoformat(),
        "terms_reference": "Signed terms",
        "document_reference": doc,
        "source_instrument": pin,
    }
    if negative:
        hit(
            f,
            "POST",
            "/contracts",
            data=contract_data | {"document_reference": doc | {"source_hash": "0" * 64}},
            status=409,
        )
    contract = hit(f, "POST", "/contracts", data=contract_data, status=201)
    route = f"/contracts/{contract['id']}/actions"
    execute = REASON | {"action": "execute", "execution_date": TODAY.isoformat(), "document_reference": doc}
    approve = REASON | {"action": "approve"}
    if negative:
        hit(f, "POST", route, data=execute, actor="contract_executor", version=contract["version"], status=409)
        hit(f, "POST", route, data=approve, actor="contract_approver", version=9999, status=412)
        # A broadly privileged admin is still prevented from approving their own draft.
        own = hit(
            f, "POST", "/contracts", actor="admin", data=contract_data | {"contract_number": "SELF-O2C"}, status=201
        )
        hit(
            f,
            "POST",
            f"/contracts/{own['id']}/actions",
            data=approve,
            actor="admin",
            version=own["version"],
            status=403,
        )
        hit(f, "GET", f"/contracts/{contract['id']}", actor="foreign", status=404)
    for actor, payload, state in (
        ("contract_approver", approve, "APPROVED"),
        ("contract_executor", execute, "EXECUTED"),
        ("contract_executor", REASON | {"action": "effect"}, "EFFECTIVE"),
    ):
        contract = hit(f, "POST", route, actor=actor, data=payload, version=contract["version"])
        assert contract["status"] == state
    version = hit(f, "GET", f"/versions/{contract['current_version_id']}")
    data = {
        **REASON,
        "commitment_code": "COM-O2C",
        "contract_id": contract["id"],
        "contract_version_id": version["id"],
        "committed_amount": "80",
        "effective_date": TODAY.isoformat(),
        "commercial_basis": "Signed pricing terms",
    }
    if negative:
        hit(f, "POST", "/commitments", data=data | {"contract_version_id": 2147483647}, status=404)
    row = hit(f, "POST", "/commitments", data=data, status=201)
    row = hit(
        f, "POST", f"/commitments/{row['id']}/approve", actor="contract_approver", data=REASON, version=row["version"]
    )
    assert row["status"] == "APPROVED"
    return contract, version, row, doc


def performance(f, contract, commitment):
    destination = os.getenv("PYPMIS_O2C_PERFORMANCE")
    if not destination:
        return
    target = Path(destination).resolve()
    qa = Path(__file__).resolve().parents[2] / "outputs/.qa"
    assert target.is_relative_to(qa) and target.relative_to(qa).parts[0] in {"wave-o2c-20261113", "wave-o2c-20261118"}
    paths = (
        ("contracts", "/contracts", {}),
        ("detail", f"/contracts/{contract['id']}", {}),
        ("commitments", "/commitments", {"contract_id": contract["id"]}),
        ("changes", "/changes", {}),
        ("applications", "/payment-applications", {}),
        ("certificates", "/payment-certificates", {}),
        ("readiness", f"/readiness/{contract['id']}", {}),
        ("lookahead", "/lookahead", {}),
        ("trace", f"/trace/{contract['id']}", {}),
        (
            "cost lookup",
            f"/api/v1/cost/projects/{f.project_workspace_id}/commercial-commitment-adoptions/lookup",
            {"source_entity_id": commitment["id"]},
        ),
    )
    samples = {}
    for name, path, params in paths:
        readings = []
        for _ in range(3):
            started = perf_counter()
            uri = path if path.startswith("/api") else contract_root(f) + path
            response = request(f, "GET", uri, actor="manager", params=params)
            expect(response, 200)
            readings.append(round((perf_counter() - started) * 1000, 2))
        samples[name] = {
            "ms": readings,
            "median_ms": median(readings),
            "max_ms": max(readings),
            "response_bytes": len(response.content),
        }
    target.write_text(json.dumps(samples, indent=2), encoding="utf-8")


def test_o2c_contract_and_explicit_cost_adoption():
    if os.getenv("PYPMIS_O2C_FIXTURE") != "disposable-only":
        pytest.skip("O2C isolated PostgreSQL required")
    with SessionLocal() as db, TestClient(app) as client:
        f = setup(db, client)
        before = signatures(f, CORE_SNAPSHOTS)
        contract, version, commitment, _doc = create_chain(f, negative=True)
        assert signatures(f, CORE_SNAPSHOTS) == before
        root = f"/api/v1/cost/projects/{f.project_workspace_id}/commercial-commitment-adoptions"
        source = hit(f, "GET", root + "/lookup", actor="manager", params={"source_entity_id": commitment["id"]})
        assert source["version"] == 0 and source["consumer_status"] == "NOT_ADOPTED"
        data = {
            **REASON,
            **{
                name: source[name]
                for name in ("source_entity_id", "source_version", "source_hash", "observed_at", "effective_at")
            },
            "cbs_id": f.cost_cbs["id"],
            "cost_code_id": f.cost_code["id"],
            "control_account_id": f.cost_account["id"],
            "consumer_status": "ADOPTED",
        }
        finance = f"/api/v1/cost/projects/{f.project_workspace_id}/commitments"
        reference = f"{contract['id']}:{source['commitment_code']}"
        finance_data = {
            **REASON,
            "source_system": "CONTRACTS",
            "source_type": "COMMERCIAL_COMMITMENT",
            "source_reference": reference,
            "source_revision": str(source["revision"]),
            "source_hash": source["source_hash"],
            "source_record_id": commitment["id"],
            "source_document": f"CONTRACTS:{commitment['id']}",
            "source_approval_status": "APPROVED",
            "economic_origin": f"CONTRACTS:{reference}",
            "inclusion_mode": "REFERENCE_ONLY",
            "amount": source["committed_amount"],
            "currency": source["currency"],
            "effective_date": source["effective_at"],
            **{name: data[name] for name in ("cbs_id", "cost_code_id", "control_account_id")},
        }
        hit(f, "POST", finance, actor="cost_controller", data=finance_data, status=409)
        hit(f, "POST", root, actor="contract_preparer", data=data, version=0, status=403)
        hit(f, "POST", root, actor="manager", data=data | {"cbs_id": 2147483647}, version=0, status=404)
        hit(f, "POST", root, actor="manager", data=data | {"source_hash": "0" * 64}, version=0, status=409)
        adopted = hit(f, "POST", root, actor="manager", data=data, version=0, status=201)
        assert adopted["consumer_status"] == "ADOPTED" and adopted["source_version"] == source["source_version"]
        assert adopted["source_hash"] == commitment["source_hash"]
        assert adopted["source_snapshot"]["contract_version_id"] == version["id"]
        hit(f, "POST", root, actor="manager", data=data, version=0, status=412)
        assert signatures(f, CORE_SNAPSHOTS) == before
        assert len(hit(f, "GET", root, actor="manager")["items"]) == 1
        financial = hit(f, "POST", finance, actor="cost_controller", data=finance_data, status=201)
        assert financial["status"] == "PROPOSED"
        verified = hit(
            f,
            "POST",
            f"{finance}/{financial['id']}/verify",
            actor="manager",
            data=REASON | {"status": "VERIFIED"},
            version=financial["version"],
        )
        assert verified["status"] == "VERIFIED" and verified["inclusion_mode"] == "REFERENCE_ONLY"
        destination = os.getenv("PYPMIS_O2C_SCENARIO")
        if destination:
            target = Path(destination).resolve()
            allowed = Path(__file__).resolve().parents[2] / "outputs/.qa/wave-o2c-20261118"
            assert target.is_relative_to(allowed)
            target.write_text(
                json.dumps(
                    {
                        "tenant_id": f.tenant_id,
                        "project_workspace_id": f.project_workspace_id,
                        "legacy_project_id": f.legacy_project_id,
                        "po_id": f.chain["po"]["id"],
                        "contract_package_id": contract["contract_package_id"],
                        "contract_id": contract["id"],
                        "contract_version_id": version["id"],
                        "commercial_commitment": commitment,
                        "cost_source": source,
                        "cost_adoption": adopted,
                        "financial_reference": verified,
                        "upstream_before": before,
                        "upstream_after_commercial_and_adoption": signatures(f, CORE_SNAPSHOTS),
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
        after = signatures(f, CORE_SNAPSHOTS)
        assert after.pop("cost_commitment_references") != before.pop("cost_commitment_references")
        assert after == before
        for table, identity in (
            ("contract_versions", version["id"]),
            ("commercial_commitments", commitment["id"]),
            ("cost_commercial_commitment_adoptions", adopted["id"]),
        ):
            with SessionLocal() as isolated, pytest.raises(DBAPIError, match="immutable"):
                isolated.execute(
                    text(f"UPDATE {table} SET version=version+1 WHERE id=:identity"), {"identity": identity}
                )
        performance(f, contract, commitment)
