"""Real PostgreSQL/HTTP financial recognition, FX and obligation reconciliation."""

import os
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select, text
from sqlalchemy.exc import DBAPIError
from tests.cost_release_fixture import REASON, account, cbs, cost_code, create_cost_fixture, request
from tests.test_scope_foundation_release import success

from app.database.session import SessionLocal, engine
from app.domain.models import Contract, FundingSource, PurchaseOrder
from app.main import app
from app.modules.cost_foundation.financial_models import CostFXRate


@pytest.fixture(scope="module")
def fixture():
    assert engine.dialect.name == "postgresql" and engine.url.database == "o1bc"
    assert os.getenv("PYPMIS_O1BC_FIXTURE") == "disposable-only"
    with TestClient(app) as client, SessionLocal() as db:
        value = create_cost_fixture(db, client)
        value.financial_cbs = cbs(value)
        value.financial_code = cost_code(value)
        value.financial_account = account(value)
        yield value
        db.rollback()


def actual_payload(f, **changes):
    return {
        **REASON,
        "source_system": "ISOLATED_ACCOUNTING_REFERENCE",
        "source_reference": f"ACT-{uuid4()}",
        "source_type": "CONTROLLED_MANUAL",
        "posting_date": "2026-10-22",
        "recognition_date": "2026-10-22",
        "period_id": f.period["id"],
        "amount": "100",
        "currency": "USD",
        "cbs_id": f.financial_cbs["id"],
        "cost_code_id": f.financial_code["id"],
        "control_account_id": f.financial_account["id"],
        "evidence_ref": "DOC-RECOGNIZED-COST",
        **changes,
    }


def actual(f, recognize=False, **changes):
    row = success(request(f, "POST", "/actuals", payload=actual_payload(f, **changes)), 201)
    return (
        success(
            request(
                f, "POST", f"/actuals/{row['id']}/decision", actor="manager", version=row["version"], payload=REASON
            )
        )
        if recognize
        else row
    )


def fx(f, publish=True, **changes):
    row = success(
        request(
            f,
            "POST",
            "/fx-rates",
            actor="admin",
            payload={
                **REASON,
                "code": f"FX-{uuid4().hex[:12]}",
                "from_currency": "COP",
                "to_currency": "USD",
                "rate": "0.00025",
                "effective_from": "2026-01-01",
                "effective_to": "2026-12-31",
                "conversion_basis": "COP amount multiplied by directly quoted USD per COP",
                "source_reference": "GOVERNED_TEST_FX_REFERENCE",
                **changes,
            },
        ),
        201,
    )
    return (
        success(
            request(
                f, "POST", f"/fx-rates/{row['id']}/publish", actor="publisher", version=row["version"], payload=REASON
            )
        )
        if publish
        else row
    )


def obligation_payload(**changes):
    token = uuid4().hex
    return {
        **REASON,
        "source_system": "EXTERNAL_CONTRACT_AUTHORITY",
        "source_type": "CONTRACT",
        "source_reference": f"LEGAL-{token}",
        "source_revision": "1",
        "source_hash": "a" * 64,
        "source_document": f"SIGNED-EXTERNAL-LEGAL-REFERENCE-{token}",
        "source_approval_status": "APPROVED",
        "economic_origin": f"ECONOMIC-{token}",
        "inclusion_mode": "ADDITIVE",
        "amount": "100",
        "currency": "USD",
        "effective_date": "2026-10-22",
        **changes,
    }


def commitment(f, verify=True, **changes):
    row = success(request(f, "POST", "/commitments", payload=obligation_payload(**changes)), 201)
    return (
        success(
            request(
                f, "POST", f"/commitments/{row['id']}/verify", actor="manager", version=row["version"], payload=REASON
            )
        )
        if verify
        else row
    )


def test_fx_independent_publication_etag_history(fixture):
    f = fixture
    row = fx(f, publish=False)
    assert (
        request(
            f, "POST", f"/fx-rates/{row['id']}/publish", actor="admin", version=row["version"], payload=REASON
        ).status_code
        == 403
    )
    assert (
        request(f, "POST", f"/fx-rates/{row['id']}/publish", actor="publisher", version=99, payload=REASON).status_code
        == 412
    )
    published = success(
        request(f, "POST", f"/fx-rates/{row['id']}/publish", actor="publisher", version=row["version"], payload=REASON)
    )
    successor = fx(f, code=row["code"], rate="0.00026", supersedes_id=row["id"])
    assert successor["revision"] == 2 and published["rate"] == "0.00025000"
    with SessionLocal() as db:
        old = db.scalar(select(CostFXRate).where(CostFXRate.id == row["id"]))
        assert old.rate == Decimal("0.00025")
    history = success(request(f, "GET", f"/history/CostFXRate/{row['id']}"))["items"]
    assert {item["event_type"] for item in history} == {"FX_RATE_CREATED", "FX_RATE_PUBLISHED"}


def test_fx_forbidden_default_and_date_basis(fixture):
    f = fixture
    assert request(f, "POST", "/fx-rates", actor="executive", payload={**REASON}).status_code in {403, 422}
    row = fx(f)
    actual(f, recognize=True, amount="400000", currency="COP", fx_rate_id=row["id"])
    result = success(request(f, "GET", "/actuals?target_currency=USD"))["recognized"]
    conversion = next(row for row in result["conversions"] if row["currency"] == "COP")
    assert conversion["converted_amount"] == "100.00000000"
    assert conversion["exchange_rate_basis"] and conversion["source"] and conversion["conversion_date"]


def test_actual_import_idempotency_duplicate_source_and_approval_sod(fixture):
    f = fixture
    payload, key = actual_payload(f), f"ACTUAL-{uuid4()}"
    row = success(request(f, "POST", "/actuals", payload=payload, key=key), 201)
    assert success(request(f, "POST", "/actuals", payload=payload, key=key), 201) == row
    assert request(f, "POST", "/actuals", payload=payload).status_code == 409
    assert (
        request(
            f, "POST", f"/actuals/{row['id']}/decision", actor="cost_controller", version=row["version"], payload=REASON
        ).status_code
        == 403
    )
    approved = success(
        request(f, "POST", f"/actuals/{row['id']}/decision", actor="manager", version=row["version"], payload=REASON)
    )
    assert approved["status"] == "RECOGNIZED" and approved["approved_by"] != approved["created_by"]
    assert approved["period_id"] == f.period["id"] and approved["source_reference"] == payload["source_reference"]


def test_fx_expiry_and_inverse_are_never_inferred(fixture):
    f = fixture
    expired = fx(f, effective_to="2026-06-30")
    assert (
        request(
            f, "POST", "/actuals", payload=actual_payload(f, amount="4000", currency="COP", fx_rate_id=expired["id"])
        ).status_code
        == 422
    )
    inverse = fx(f, from_currency="USD", to_currency="COP", rate="4000")
    assert (
        request(
            f, "POST", "/actuals", payload=actual_payload(f, amount="4000", currency="COP", fx_rate_id=inverse["id"])
        ).status_code
        == 409
    )


@pytest.mark.parametrize(
    "change", [{"currency": "GBP"}, {"recognition_date": "2027-01-01"}, {"source_type": "COMMITMENT"}]
)
def test_actual_currency_period_and_source_fail_closed(fixture, change):
    assert request(fixture, "POST", "/actuals", payload=actual_payload(fixture, **change)).status_code == 422


def test_actual_adjustment_history_without_double_count(fixture):
    f = fixture
    row = actual(f, recognize=True)
    before = success(request(f, "GET", "/actuals"))["recognized"]["by_currency"]["USD"]
    adjustment = success(
        request(
            f, "POST", f"/actuals/{row['id']}/adjustments", actor="manager", payload=actual_payload(f, amount="-25")
        ),
        201,
    )
    assert (
        request(
            f, "POST", f"/actuals/{adjustment['id']}/decision", actor="manager", version=1, payload=REASON
        ).status_code
        == 403
    )
    result = success(
        request(f, "POST", f"/actuals/{adjustment['id']}/decision", actor="second_manager", version=1, payload=REASON)
    )
    after = success(request(f, "GET", "/actuals"))["recognized"]["by_currency"]["USD"]
    assert Decimal(after) == Decimal(before) - 25 and result["adjusts_entry_id"] == row["id"]
    assert (
        success(request(f, "GET", f"/history/CostActualEntry/{adjustment['id']}"))["items"][-1]["event_type"]
        == "ACTUAL_ADJUSTED"
    )


def test_actual_adjustment_cannot_over_reverse_original(fixture):
    f = fixture
    row = actual(f, recognize=True)
    adjustment = success(
        request(
            f, "POST", f"/actuals/{row['id']}/adjustments", actor="manager", payload=actual_payload(f, amount="-101")
        ),
        201,
    )
    assert (
        request(
            f, "POST", f"/actuals/{adjustment['id']}/decision", actor="second_manager", version=1, payload=REASON
        ).status_code
        == 409
    )


def test_adjustments_cannot_backdate_negative_historical_actual(fixture):
    f = fixture
    row = actual(f, recognize=True)
    assert (
        request(
            f,
            "POST",
            f"/actuals/{row['id']}/adjustments",
            actor="manager",
            payload=actual_payload(f, amount="-10", recognition_date="2026-10-21"),
        ).status_code
        == 422
    )
    positive = success(
        request(
            f,
            "POST",
            f"/actuals/{row['id']}/adjustments",
            actor="manager",
            payload=actual_payload(f, amount="100", recognition_date="2026-10-25"),
        ),
        201,
    )
    success(
        request(f, "POST", f"/actuals/{positive['id']}/decision", actor="second_manager", version=1, payload=REASON)
    )
    negative = success(
        request(
            f,
            "POST",
            f"/actuals/{row['id']}/adjustments",
            actor="manager",
            payload=actual_payload(f, amount="-150", recognition_date="2026-10-23"),
        ),
        201,
    )
    assert (
        request(
            f, "POST", f"/actuals/{negative['id']}/decision", actor="second_manager", version=1, payload=REASON
        ).status_code
        == 409
    )


def test_actual_recognition_revalidates_active_mapping(fixture):
    f = fixture
    target = cbs(f)
    row = actual(f, cbs_id=target["id"], cost_code_id=None, control_account_id=None)
    success(
        request(
            f,
            "PUT",
            f"/cbs/{target['id']}",
            version=target["version"],
            payload={**REASON, "code": target["code"], "name": target["name"], "status": "INACTIVE"},
        )
    )
    assert (
        request(f, "POST", f"/actuals/{row['id']}/decision", actor="manager", version=1, payload=REASON).status_code
        == 409
    )


def test_actual_foreign_project_fx_reference_cannot_be_consumed(fixture):
    f = fixture
    foreign = CostFXRate(
        tenant_id=f.tenant_id,
        project_workspace_id=f.workspaces["other_project"].id,
        created_by=f.users["admin"].id,
        updated_by=f.users["admin"].id,
        code=f"FOREIGN-{uuid4()}",
        from_currency="COP",
        to_currency="USD",
        rate=Decimal("0.00025"),
        effective_from=date(2026, 1, 1),
        conversion_basis="Direct basis",
        source_reference="Other project fixture source",
        content_hash="b" * 64,
    )
    f.db.add(foreign)
    f.db.commit()
    assert (
        request(
            f, "POST", "/actuals", payload=actual_payload(f, currency="COP", amount="400000", fx_rate_id=foreign.id)
        ).status_code
        == 404
    )


def test_actual_two_currencies_no_conversion_never_zero(fixture):
    f = fixture
    actual(f, recognize=True, currency="EUR", amount="75")
    totals = success(request(f, "GET", "/actuals"))["recognized"]
    assert totals["status"] == "NO_AGGREGATION" and totals["amount"] is None
    assert request(f, "GET", "/actuals?target_currency=USD").status_code == 409


@pytest.mark.parametrize("kind", ["CONTRACT", "PO", "SUBCONTRACT", "CONTRACT_CHANGE_ORDER"])
def test_external_verified_legal_reference_projection_not_second_authority(fixture, kind):
    row = commitment(fixture, source_type=kind)
    assert row["status"] == "VERIFIED" and row["verified_by"] != row["created_by"]
    item = next(
        item
        for item in success(request(fixture, "GET", "/commitments/reconciliation"))["items"]
        if item["id"] == row["id"]
    )
    assert item["reconciliation_decision"] == "ADDITIVE_ONCE"


@pytest.mark.parametrize("mode", ["INCLUDED", "CALL_OFF", "ADDITIVE", "REFERENCE_ONLY"])
def test_contract_po_inclusion_semantics(fixture, mode):
    f = fixture
    root = commitment(f)
    row = commitment(
        f,
        source_type="PO",
        amount="20",
        economic_origin=f"PO-{uuid4()}",
        parent_economic_origin=root["economic_origin"],
        inclusion_mode=mode,
    )
    item = next(
        item for item in success(request(f, "GET", "/commitments/reconciliation"))["items"] if item["id"] == row["id"]
    )
    assert Decimal(item["net_contribution"]) == (20 if mode == "ADDITIVE" else 0)


def test_duplicate_obligation_source_and_economic_origin_are_rejected(fixture):
    f = fixture
    payload = obligation_payload()
    success(request(f, "POST", "/commitments", payload=payload), 201)
    assert request(f, "POST", "/commitments", payload=payload).status_code == 409
    assert (
        request(
            f, "POST", "/commitments", payload={**obligation_payload(), "economic_origin": payload["economic_origin"]}
        ).status_code
        == 409
    )


def test_included_po_without_parent_and_draft_external_source_rejected(fixture):
    assert (
        request(fixture, "POST", "/commitments", payload=obligation_payload(inclusion_mode="INCLUDED")).status_code
        == 422
    )
    assert (
        request(fixture, "POST", "/commitments", payload=obligation_payload(source_approval_status="DRAFT")).status_code
        == 422
    )


def test_legacy_contract_and_included_po_consume_existing_authority_only(fixture):
    f = fixture
    binding_root = f"/api/v1/operational/projects/{f.project_workspace_id}/binding"
    binding = success(request(f, "GET", binding_root, actor="admin"))
    if binding["state"] != "ACTIVE":
        success(
            request(
                f,
                "POST",
                binding_root,
                actor="admin",
                version=binding["version"],
                payload={**REASON, "legacy_project_id": f.legacy_project_id, "source": "AUTHORIZED_ONBOARDING"},
            ),
            201,
        )
    token = uuid4().hex[:10]
    # Existing legal rows are fixture inputs, not created by the Cost service.
    funding = FundingSource(
        tenant_id=f.tenant_id,
        project_id=f.legacy_project_id,
        code=f"F-{token}",
        name="Existing legal source funding",
        amount=10000,
        currency="USD",
    )
    f.db.add(funding)
    f.db.flush()
    contract = Contract(
        tenant_id=f.tenant_id,
        project_id=f.legacy_project_id,
        funding_source_id=funding.id,
        code=f"LEGAL-C-{token}",
        title="Existing legal Contract",
        counterparty="Independent supplier",
        contract_type="EPC",
        value=1000,
        status="active",
    )
    f.db.add(contract)
    f.db.flush()
    order = PurchaseOrder(
        tenant_id=f.tenant_id,
        project_id=f.legacy_project_id,
        funding_source_id=funding.id,
        contract_id=contract.id,
        po_number=f"LEGAL-PO-{token}",
        committed_amount=200,
        status="issued",
    )
    f.db.add(order)
    f.db.commit()
    sources = success(request(f, "GET", "/commitments/sources"))["items"]

    def project_source(kind, source_id, **changes):
        source = next(item for item in sources if item["source_type"] == kind and item["source_record_id"] == source_id)
        projected = {
            key: source[key]
            for key in (
                "source_system",
                "source_type",
                "source_record_id",
                "source_reference",
                "source_revision",
                "source_hash",
                "source_approval_status",
                "amount",
            )
        }
        return commitment(f, **projected, **changes)

    root = project_source("CONTRACT", contract.id)
    child = project_source("PO", order.id, inclusion_mode="INCLUDED", parent_economic_origin=root["economic_origin"])
    reconciliation = success(request(f, "GET", "/commitments/reconciliation"))
    selected = [item for item in reconciliation["items"] if item["id"] in {root["id"], child["id"]}]
    assert sum(Decimal(item["net_contribution"]) for item in selected) == 1000
    f.db.refresh(contract)
    f.db.refresh(order)
    assert contract.value == 1000 and order.committed_amount == 200
    changed_payload = obligation_payload(
        source_system="LEGACY",
        source_type="CONTRACT",
        source_record_id=contract.id,
        amount="999",
        source_reference="WRONG",
        source_revision="1",
    )
    assert request(f, "POST", "/commitments", payload=changed_payload).status_code == 409
    old_hash = root["source_hash"]
    # Source authority changes independently; Cost only observes and reconciles it.
    contract.value = 1200
    f.db.commit()
    stale = success(request(f, "GET", "/commitments/reconciliation"))
    assert stale["status"] == "RECONCILIATION_REQUIRED" and stale["net_commitment"] is None
    refreshed_source = next(
        item
        for item in success(request(f, "GET", "/commitments/sources"))["items"]
        if item["source_type"] == "CONTRACT" and item["source_record_id"] == contract.id
    )
    successor_body = {
        **obligation_payload(),
        **{
            key: refreshed_source[key]
            for key in (
                "source_system",
                "source_type",
                "source_record_id",
                "source_reference",
                "source_revision",
                "source_hash",
                "source_approval_status",
                "amount",
            )
        },
        "economic_origin": root["economic_origin"],
        "supersedes_id": root["id"],
    }
    proposal = success(request(f, "POST", "/commitments", payload=successor_body), 201)
    assert success(request(f, "GET", "/commitments/reconciliation"))["status"] == "RECONCILIATION_REQUIRED"
    successor = success(
        request(
            f,
            "POST",
            f"/commitments/{proposal['id']}/verify",
            actor="manager",
            version=proposal["version"],
            payload=REASON,
        )
    )
    result = success(request(f, "GET", "/commitments/reconciliation"))
    old_projection = next(item for item in result["items"] if item["id"] == root["id"])
    new_projection = next(item for item in result["items"] if item["id"] == successor["id"])
    assert old_projection["status"] == "SUPERSEDED_PROJECTION" and old_projection["source_hash"] == old_hash
    assert Decimal(old_projection["amount"]) == 1000 and Decimal(old_projection["net_contribution"]) == 0
    assert Decimal(new_projection["net_contribution"]) == 1200 and successor["revision"] == 2
    subcontract = Contract(
        tenant_id=f.tenant_id,
        project_id=f.legacy_project_id,
        funding_source_id=funding.id,
        code=f"LEGAL-S-{token}",
        title="Existing legal Subcontract",
        counterparty="Independent subcontractor",
        contract_type="SUBCONTRACT",
        value=300,
        status="active",
    )
    foreign_project_contract = Contract(
        tenant_id=f.tenant_id,
        project_id=f.legacy["second"].id,
        code=f"OTHER-C-{token}",
        title="Other Project legal source",
        counterparty="Other Project supplier",
        value=500,
        status="active",
    )
    f.db.add_all([subcontract, foreign_project_contract])
    f.db.commit()
    source = next(
        item
        for item in success(request(f, "GET", "/commitments/sources"))["items"]
        if item["source_type"] == "SUBCONTRACT" and item["source_record_id"] == subcontract.id
    )
    canonical_source = {
        key: source[key]
        for key in (
            "source_system",
            "source_type",
            "source_record_id",
            "source_reference",
            "source_revision",
            "source_hash",
            "source_approval_status",
            "amount",
        )
    }
    wrong_kind = {**obligation_payload(), **canonical_source, "source_type": "CONTRACT"}
    assert request(f, "POST", "/commitments", payload=wrong_kind).status_code == 422
    commitment(f, **canonical_source)
    assert (
        request(
            f,
            "POST",
            "/commitments",
            payload=obligation_payload(source_system="LEGACY", source_record_id=foreign_project_contract.id),
        ).status_code
        == 404
    )


def test_recognition_and_projection_tenant_rbac_etag(fixture):
    f = fixture
    row = actual(f)
    assert (
        request(f, "POST", f"/actuals/{row['id']}/decision", actor="manager", version=99, payload=REASON).status_code
        == 412
    )
    assert request(f, "POST", "/actuals", actor="executive", payload=actual_payload(f)).status_code == 403
    assert request(f, "GET", "/actuals", actor="foreign").status_code in {403, 404}
    assert request(
        f, "GET", f"/api/v1/cost/projects/{f.workspaces['other_project'].id}/actuals", actor="cost_controller"
    ).status_code in {403, 404}
    obligation = commitment(f, verify=False)
    assert (
        request(
            f, "POST", f"/commitments/{obligation['id']}/verify", actor="cost_controller", version=1, payload=REASON
        ).status_code
        == 403
    )


def test_financial_gets_emit_no_business_writes(fixture):
    writes = []

    def observe(_connection, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
            writes.append(statement)

    event.listen(engine, "before_cursor_execute", observe)
    try:
        for path in (
            "/financial-overview",
            "/cash-flow",
            "/actuals",
            "/fx-rates",
            "/commitments/reconciliation",
            "/accruals",
        ):
            success(request(fixture, "GET", path))
    finally:
        event.remove(engine, "before_cursor_execute", observe)
    assert writes == []


def test_deferred_accrual_and_eac_interface_never_add_commitments(fixture):
    f = fixture
    contract = success(request(f, "GET", "/accruals"))
    assert (
        contract["status"] == "DEFERRED_WITH_CONTRACT"
        and not contract["functional"]
        and not contract["mutations_available"]
    )
    assert request(f, "POST", "/accruals", payload=REASON).status_code == 405
    # Before any recognized entry date, EAC only contains the externally accepted ETC.
    eac = success(
        request(
            f,
            "POST",
            "/eac-reference-preview",
            payload={
                "etc_amount": "50",
                "currency": "USD",
                "method": "COMMITMENT_BASED",
                "acceptance_reference": "EXTERNAL-ACCEPTED-ETC",
                "includes_commitments": True,
                "as_of": "2026-01-01",
            },
        )
    )
    assert Decimal(eac["eac_amount"]) == 50 and eac["commitment_added_separately"] is False
    assert eac["forecast_approval_created"] is False


@pytest.mark.parametrize(
    "table,field,value", [("cost_fx_rates", "rate", "99"), ("cost_actual_entries", "amount", "999")]
)
def test_postgresql_published_financial_inputs_immutable(fixture, table, field, value):
    f = fixture
    row = fx(f) if table == "cost_fx_rates" else actual(f, recognize=True)
    with engine.begin() as connection:
        transaction = connection.begin_nested()
        with pytest.raises(DBAPIError):
            connection.execute(
                text(f"UPDATE {table} SET {field} = :value, version = version + 1 WHERE id = :id"),
                {"value": value, "id": row["id"]},
            )
        transaction.rollback()


def test_z_period_close_prevents_actual_import_and_recognition(fixture):
    f = fixture
    row = actual(f)
    root = f"/api/v1/operational/projects/{f.project_workspace_id}/periods/{f.period['id']}"
    period = success(request(f, "POST", root + "/review", actor="manager", version=f.period["version"], payload=REASON))
    period = success(request(f, "POST", root + "/close", actor="manager", version=period["version"], payload=REASON))
    assert request(f, "POST", "/actuals", payload=actual_payload(f)).status_code == 409
    assert (
        request(
            f, "POST", f"/actuals/{row['id']}/decision", actor="manager", version=row["version"], payload=REASON
        ).status_code
        == 409
    )
    published = success(
        request(f, "POST", root + "/publish", actor="second_manager", version=period["version"], payload=REASON)
    )
    assert published["status"] == "PUBLISHED"
    assert request(f, "POST", "/actuals", payload=actual_payload(f)).status_code == 409
    periods = success(
        request(f, "GET", f"/api/v1/operational/projects/{f.project_workspace_id}/periods", actor="manager")
    )["items"]
    assert (
        next(value for value in periods if value["id"] == published["id"])["snapshot_json"]
        == published["snapshot_json"]
    )
