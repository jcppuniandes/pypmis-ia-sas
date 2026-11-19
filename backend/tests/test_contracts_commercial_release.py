"""Commercial controls against governed, isolated PostgreSQL fixtures and real sources."""

import json
import os
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from tests.contracts_release_fixture import REASON, contract_root, setup
from tests.engineering_release_fixture import TODAY, request
from tests.procurement_release_fixture import REASON as PROCUREMENT_REASON
from tests.progress_release_fixture import request as progress_request
from tests.test_procurement_consumer_release import signatures
from tests.test_procurement_o2b_release import expect
from tests.test_progress_foundation_release import approve, measurement_body

from app.database.session import SessionLocal
from app.main import app
from app.modules.contracts_foundation.service import ContractsService


@pytest.mark.parametrize("delta", ["-100.01", "100.01"])
def test_change_threshold_checks_impact_magnitude(delta):
    service = ContractsService.__new__(ContractsService)
    policy = {"approval_thresholds": {"change_approval_limit": "100"}}
    with pytest.raises(HTTPException) as failure:
        service._threshold(policy, "change_approval_limit", Decimal(delta))
    assert failure.value.status_code == 409
    assert failure.value.detail["code"] == "CONTRACTS_APPROVAL_THRESHOLD_EXCEEDED"
    for boundary in (Decimal("-100"), Decimal("100")):
        service._threshold(policy, "change_approval_limit", boundary)


def api(f, method, path, *, actor="contract_preparer", status=200, version=None, **kwargs):
    return expect(
        request(f, method, contract_root(f) + path, actor=actor, version=version, **kwargs),
        status,
    )


def create(f, path, payload, **kwargs):
    kwargs.setdefault("status", 201)
    return api(f, "POST", path, payload=REASON | payload, **kwargs)


def transition(f, resource, row, operation, *, actor="contract_approver", endpoint="actions", **kwargs):
    return api(
        f,
        "POST",
        f"/{resource}/{row['id']}/{endpoint}",
        version=row["version"],
        actor=actor,
        payload=REASON | operation,
        **kwargs,
    )


def executed_contract(f, document):
    package = create(
        f,
        "/packages",
        {
            "package_code": "COM-PACKAGE",
            "title": "Commercial proof package",
            "contract_type": "SUBCONTRACT",
            "commercial_model": "UNIT_RATE",
            "currency": "USD",
            "estimated_value": "10000",
        },
    )
    package = transition(f, "packages", package, {"action": "plan"}, actor="contract_preparer")
    contract = create(
        f,
        "/contracts",
        {
            "contract_number": "COM-0001",
            "contract_package_id": package["id"],
            "title": "Governed commercial proof",
            "vendor_id": f.chain["po"]["vendor_id"],
            "governing_reference": "O2C evidence controlled contract",
            "original_contract_value": "10000",
            "effective_date": TODAY.isoformat(),
            "commencement_date": TODAY.isoformat(),
            "planned_completion_date": (TODAY + timedelta(days=90)).isoformat(),
            "terms_reference": "Executed unit rates and payment terms",
            "document_reference": document,
        },
    )
    contract = transition(f, "contracts", contract, {"action": "approve"})
    contract = transition(
        f,
        "contracts",
        contract,
        {
            "action": "execute",
            "execution_date": TODAY.isoformat(),
            "document_reference": document,
        },
        actor="contract_executor",
    )
    return transition(f, "contracts", contract, {"action": "effect"}, actor="contract_executor")


def progress_fixture(f):
    scope = f.scope_items[0]
    body = measurement_body(
        f,
        period_id=f.current_period["id"],
        measurement_date=TODAY.isoformat(),
        as_of=TODAY.isoformat(),
        numerator=str(Decimal(scope["quantity"]) * Decimal("0.75")),
        reason=PROCUREMENT_REASON["reason"],
    )
    draft = expect(progress_request(f, "POST", "/measurements", payload=body), 201)
    return approve(f, draft)


def test_contract_commercial_payment_change_and_no_upstream_mutation():
    if os.getenv("PYPMIS_O2C_FIXTURE") != "disposable-only":
        pytest.skip("Dedicated O2C contracts fixture required")
    with SessionLocal() as db, TestClient(app) as client:
        f = setup(db, client)
        progress = progress_fixture(f)
        upstream = signatures(f)
        doc = {"document_id": f.document["id"], "attachment_id": f.attachment["id"]}
        contract = executed_contract(f, doc)
        base_version = contract["current_version_id"]
        scope = f.scope_items[0]
        commercial = create(
            f,
            "/commitments",
            {
                "commitment_code": "COMMERCIAL-CH-1",
                "contract_id": contract["id"],
                "contract_version_id": base_version,
                "committed_amount": "8000",
                "effective_date": TODAY.isoformat(),
                "commercial_basis": "Independent signed commercial obligation",
            },
        )
        commercial = transition(f, "commitments", commercial, {}, endpoint="approve")
        original_pin = api(f, "GET", "/commitment-source", params={"commitment_id": commercial["id"]})
        assert original_pin["source_entity_id"] == commercial["id"]

        mappings = {
            "source_kind": "CONTRACT",
            "source_id": contract["id"],
            "target_kind": "PROCUREMENT_PACKAGE",
            "target_id": f.chain["package"]["id"],
        }
        mapping = create(f, "/mappings", mappings, version=0)
        assert mapping["version"] == 1
        create(f, "/mappings", mappings | {"action": "REMOVE"}, version=0, status=412)
        assert create(f, "/mappings", mappings | {"action": "REMOVE"}, version=1)["version"] == 2
        assert (
            api(f, "GET", "/mappings", params={"source_kind": "CONTRACT", "source_id": contract["id"]})["version"] == 2
        )

        sov = create(
            f,
            "/sovs",
            {
                "code": "SOV-0001",
                "contract_id": contract["id"],
                "contract_version_id": base_version,
                "lines": [
                    {
                        "line_number": "10",
                        "description": "Verified installation quantity",
                        "uom": scope["unit"],
                        "quantity": scope["quantity"],
                        "unit_rate": "10",
                        "retention_rule": "STANDARD",
                        "mappings": [{"target_kind": "SCOPE", "target_id": scope["id"]}],
                    }
                ],
            },
        )
        sov_line = sov["lines"][0]
        transition(f, "sovs", sov, {}, actor="contract_preparer", endpoint="publish", status=403)
        sov = transition(f, "sovs", sov, {}, endpoint="publish")
        assert sov["status"] == "PUBLISHED"
        choices = api(
            f,
            "GET",
            "/progress-sources",
            params={
                "period_id": f.current_period["id"],
                "sov_line_id": sov_line["id"],
            },
        )
        (evidence,) = [item for item in choices["items"] if item["measurement_id"] == progress["id"]]
        quantity = Decimal(evidence["quantity"])
        progress_pin = {field: evidence[field] for field in ("measurement_id", "version", "source_hash")}
        app_body = {
            "contract_id": contract["id"],
            "sov_id": sov["id"],
            "period_id": f.current_period["id"],
            "application_number": "PA-1",
            "document_reference": doc,
            "effective_date": TODAY.isoformat(),
            "lines": [{"sov_line_id": sov_line["id"], "progress": progress_pin, "quantity": str(quantity)}],
        }
        tampered = deepcopy(app_body)
        tampered["lines"][0]["progress"]["source_hash"] = "0" * 64
        assert (
            create(f, "/payment-applications", tampered, status=409)["detail"]["code"]
            == "CONTRACTS_PROGRESS_PIN_MISMATCH"
        )
        excess = deepcopy(app_body)
        excess["lines"][0]["quantity"] = str(quantity + Decimal("0.1"))
        assert (
            create(f, "/payment-applications", excess, status=409)["detail"]["code"]
            == "CONTRACTS_PAYMENT_APPLICATION_EXCEEDS_EVIDENCE"
        )
        application = create(f, "/payment-applications", app_body, key="o2c-commercial-application")
        assert create(f, "/payment-applications", app_body, key="o2c-commercial-application") == application
        create(f, "/payment-applications", app_body | {"application_number": "PA-DUPLICATE"}, status=409)
        transition(f, "payment-applications", application, {"action": "review"}, actor="contract_preparer", status=403)
        line = application["lines"][0]
        application = transition(f, "payment-applications", application, {"action": "review"})
        assert application["status"] == "REVIEWED"

        cert_body = {
            "application_id": application["id"],
            "certificate_number": "PC-1",
            "document_reference": doc,
            "effective_date": TODAY.isoformat(),
            "lines": [
                {
                    "application_line_id": line["id"],
                    "quantity": str(quantity / 2),
                    "deductions": "0.01",
                }
            ],
        }
        certificate = create(f, "/payment-certificates", cert_body)
        competing_body = deepcopy(cert_body)
        competing_body["certificate_number"] = "PC-COMPETING"
        competing_body["lines"][0]["quantity"] = str(quantity)
        competing = create(f, "/payment-certificates", competing_body)
        finance = {
            "source_system": "ERP-REFERENCE",
            "invoice_reference": "INV-01",
            "source_version": 1,
            "source_hash": "1" * 64,
            "amount": "0.1",
            "status_reference": "REGISTERED",
        }
        transition(
            f,
            "payment-certificates",
            certificate,
            finance,
            actor="contract_executor",
            endpoint="finance-references",
            status=409,
        )
        transition(f, "payment-certificates", certificate, {"action": "approve"}, actor="contract_preparer", status=403)
        certificate = transition(f, "payment-certificates", certificate, {"action": "approve"})
        assert certificate["status"] == "APPROVED"
        assert Decimal(certificate["gross_amount"]) == quantity / 2 * Decimal(10)
        assert Decimal(certificate["net_amount"]) == quantity / 2 * Decimal(9) - Decimal("0.01")
        assert Decimal(certificate["gross_amount"]) < Decimal(application["applied_amount"])
        assert (
            transition(f, "payment-certificates", competing, {"action": "approve"}, status=409)["detail"]["code"]
            == "CONTRACTS_CERTIFICATE_EXCEEDS_APPLICATION"
        )
        first = transition(
            f, "payment-certificates", certificate, finance, actor="contract_executor", endpoint="finance-references"
        )
        assert first["certificate_id"] == certificate["id"]
        second = transition(
            f,
            "payment-certificates",
            certificate,
            finance
            | {
                "source_version": 2,
                "source_hash": "2" * 64,
                "payment_status": "OBSERVED",
            },
            actor="contract_executor",
            endpoint="finance-references",
        )
        assert second["supersedes_id"] == first["id"]
        transition(
            f,
            "payment-certificates",
            certificate,
            finance
            | {
                "invoice_reference": "INV-02",
                "amount": "10000",
            },
            actor="contract_executor",
            endpoint="finance-references",
            status=422,
        )

        notice = create(
            f,
            "/notices",
            {
                "contract_id": contract["id"],
                "notice_number": "NT-1",
                "notice_type": "CHANGE",
                "sender": "Owner",
                "recipient": "Contractor",
                "issue_date": TODAY.isoformat(),
                "subject": "Governed scope instruction",
                "document_reference": doc,
            },
        )
        notice = transition(f, "notices", notice, {"action": "receive"}, actor="contract_preparer")
        claim = create(
            f,
            "/claims",
            {
                "contract_id": contract["id"],
                "claim_number": "CL-1",
                "claim_type": "COST",
                "cause": "Registered claim only; no autonomous contractual obligation",
                "notice_id": notice["id"],
                "claimed_amount": "250",
                "effective_date": TODAY.isoformat(),
                "documents": [doc],
            },
        )
        assert transition(f, "claims", claim, {"action": "accept"})["status"] == "ACCEPTED"
        assert api(f, "GET", f"/contracts/{contract['id']}")["current_version_id"] == base_version

        change_body = {
            "contract_id": contract["id"],
            "base_version_id": base_version,
            "change_number": "CH-1",
            "change_type": "SCOPE",
            "description": "Approved increase in commercial scope",
            "value_delta": "250",
            "time_delta": 7,
            "effective_date": TODAY.isoformat(),
            "notice_id": notice["id"],
            "document_reference": doc,
        }
        future = create(
            f,
            "/changes",
            change_body | {"change_number": "CH-FUTURE", "effective_date": (TODAY + timedelta(days=1)).isoformat()},
        )
        future = transition(f, "changes", future, {"action": "request"}, actor="contract_preparer")
        future = transition(f, "changes", future, {"action": "review"})
        assert (
            transition(f, "changes", future, {"action": "approve"}, status=409)["detail"]["code"]
            == "CONTRACTS_FUTURE_CHANGE_ACTIVATION_UNSUPPORTED"
        )
        assert api(f, "GET", f"/contracts/{contract['id']}")["current_version_id"] == base_version
        assert api(f, "GET", "/commitment-source", params={"commitment_id": commercial["id"]}) == original_pin
        change = create(f, "/changes", change_body)
        stale = create(f, "/changes", change_body | {"change_number": "CH-STALE"})
        transition(f, "changes", change, {"action": "approve"}, status=409)
        change = transition(f, "changes", change, {"action": "request"}, actor="contract_preparer")
        change = transition(f, "changes", change, {"action": "review"})
        order = transition(f, "changes", change, {"action": "approve"})
        assert order["status"] == "ORDER_APPROVED"
        current = api(f, "GET", f"/contracts/{contract['id']}")
        assert current["current_version_id"] == order["resulting_version_id"] != base_version
        successor = api(f, "GET", f"/versions/{current['current_version_id']}")
        assert Decimal(successor["value"]) == Decimal("10250") and successor["source_change_id"] == change["id"]
        assert Decimal(api(f, "GET", f"/versions/{base_version}")["value"]) == Decimal("10000")
        create(
            f,
            "/commitments",
            {
                "commitment_code": "STALE-COMMERCIAL",
                "contract_id": contract["id"],
                "contract_version_id": base_version,
                "committed_amount": "1",
                "effective_date": TODAY.isoformat(),
                "commercial_basis": "Must reject a superseded contractual version",
            },
            status=409,
        )
        successor_commitment = create(
            f,
            "/commitments",
            {
                "commitment_code": commercial["commitment_code"],
                "contract_id": contract["id"],
                "contract_version_id": successor["id"],
                "committed_amount": "8250",
                "effective_date": TODAY.isoformat(),
                "commercial_basis": "Signed commercial obligation after governed change",
                "supersedes_id": commercial["id"],
            },
        )
        successor_commitment = transition(f, "commitments", successor_commitment, {}, endpoint="approve")
        new_pin = api(f, "GET", "/commitment-source", params={"commitment_id": successor_commitment["id"]})
        assert new_pin["supersedes_id"] == commercial["id"] and new_pin["source_hash"] != original_pin["source_hash"]
        api(f, "GET", "/commitment-source", params={"commitment_id": commercial["id"]}, status=409)
        assert api(f, "GET", f"/commitments/{commercial['id']}")["committed_amount"] == commercial["committed_amount"]
        assert (
            transition(f, "changes", stale, {"action": "request"}, actor="contract_preparer", status=409)["detail"][
                "code"
            ]
            == "CONTRACTS_CURRENT_CONTRACT_VERSION_REQUIRED"
        )
        assert signatures(f) == upstream
        evidence = os.getenv("PYPMIS_O2C_COMMERCIAL_EVIDENCE")
        if evidence:
            target = Path(evidence).resolve()
            assert target.is_relative_to(Path(__file__).resolve().parents[2] / "outputs/.qa/wave-o2c-20261118")
            with target.open("x", encoding="utf-8") as output:
                json.dump(
                    {
                        "result": "PASS",
                        "tenant_id": f.tenant_id,
                        "project_workspace_id": f.project_workspace_id,
                        "contract_id": contract["id"],
                        "version_1_id": base_version,
                        "version_2_id": successor["id"],
                        "commitment_1_id": commercial["id"],
                        "commitment_2_id": successor_commitment["id"],
                        "sov_id": sov["id"],
                        "progress_id": progress["id"],
                        "progress_quantity": str(quantity),
                        "application_id": application["id"],
                        "application_amount": application["applied_amount"],
                        "certificate_id": certificate["id"],
                        "certificate_gross": certificate["gross_amount"],
                        "certificate_net": certificate["net_amount"],
                        "finance_reference_ids": [first["id"], second["id"]],
                        "notice_id": notice["id"],
                        "claim_id": claim["id"],
                        "approved_change_id": order["id"],
                        "unchanged_upstream_hashes": upstream,
                    },
                    output,
                    indent=2,
                )
