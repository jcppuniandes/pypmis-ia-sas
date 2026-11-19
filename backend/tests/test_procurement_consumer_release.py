"""Real O2B chain, consumer-owned decisions, and unchanged upstream authority."""

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
from tests.engineering_release_fixture import TODAY, request
from tests.forecast_release_fixture import approved, draft
from tests.o2b_close_isolation import is_close_consumer_database
from tests.procurement_release_fixture import REASON, create_procurement_fixture
from tests.test_procurement_o2b_release import cmd, exercise_procurement_chain, expect, get, mapping, transition

from app.database.session import SessionLocal
from app.main import app

TABLES = (
    "contracts",
    "purchase_orders",
    "warehouse_receipts",
    "cost_budget_versions",
    "cost_commitment_references",
    "cost_actual_entries",
    "progress_measurements",
    "forecast_versions",
    "forecast_assumptions",
    "forecast_components",
)


def signatures(f, tables=TABLES):
    with SessionLocal() as db:
        return {
            name: db.scalar(
                text(
                    f"SELECT md5(coalesce(string_agg(to_jsonb(t)::text,',' ORDER BY id),'')) FROM {name} t WHERE tenant_id=:tenant"
                ),
                {"tenant": f.tenant_id},
            )
            for name in tables
        }


def close_october(f):
    row = f.period
    for state in ("review", "close"):
        row = expect(
            request(
                f,
                "POST",
                f"/api/v1/operational/projects/{f.project_workspace_id}/periods/{row['id']}/{state}",
                actor="manager",
                version=row["version"],
                payload=REASON,
            ),
            200,
        )
    return row


@pytest.fixture(scope="module")
def governed():
    if os.getenv("PYPMIS_O2B_CLOSE_FIXTURE") != "disposable-only":
        pytest.skip("Dedicated O2B.CLOSE consumer fixture required")
    with SessionLocal() as db:
        assert is_close_consumer_database(db)
        with TestClient(app) as client:
            yield create_governed_fixture(db, client)


def create_governed_fixture(db, client, *, credentials=False):
    assert is_close_consumer_database(db)
    f = create_procurement_fixture(db, client, integrated=True, credentials=credentials)
    assert f.project_workspace_id != 14 and f.legacy_project_id != 14
    f.approved_forecast = approved(f)
    close_october(f)
    start = TODAY - timedelta(days=TODAY.weekday())
    end = start + timedelta(days=6)
    f.current_period = expect(
        request(
            f,
            "POST",
            f"/api/v1/operational/projects/{f.project_workspace_id}/periods",
            actor="manager",
            payload={
                **REASON,
                "period_code": "CLOSE-CURRENT",
                "period_start": start.isoformat(),
                "period_end": end.isoformat(),
                "cutoff_at": end.isoformat() + "T17:00:00-05:00",
                "timezone": "America/Bogota",
            },
        ),
        201,
    )
    f.draft_forecast = draft(f, period_id=f.current_period["id"], as_of=TODAY.isoformat())
    f.signatures_before_procurement = signatures(f)
    # Preserve IFC for positive PO amendment; the unchanged O2B regression separately checks supersession.
    f.chain = exercise_procurement_chain(f, with_quarantine=True, verify_ifc_supersession=False)
    assert signatures(f) == f.signatures_before_procurement
    f.chain["package"] = transition(f, "packages", f.chain["package"], "plan")
    return f


def root(f, consumer, workspace=None):
    return f"/api/v1/{consumer}/projects/{workspace or f.project_workspace_id}/procurement-adoptions"


def lookup(f, consumer, kind, identity, *, actor="manager", status=200, workspace=None, **context):
    return expect(
        request(
            f,
            "GET",
            root(f, consumer, workspace) + "/lookup",
            actor=actor,
            params={"source_entity_type": kind, "source_entity_id": identity, **context},
        ),
        status,
    )


def decision(source, **extras):
    return {
        **REASON,
        "source_entity_type": source["source_type"],
        "source_entity_id": source["source_id"],
        "source_package_id": source["package_id"],
        "source_version": source["source_version"],
        "source_hash": source["source_hash"],
        "observed_at": source["observed_at"],
        "effective_at": TODAY.isoformat(),
        "consumer_status": "ADOPTED",
        **extras,
    }


def decide(f, consumer, data, *, version=0, status=201, actor="manager", key=None, workspace=None):
    return expect(
        request(f, "POST", root(f, consumer, workspace), payload=data, version=version, actor=actor, key=key), status
    )


def measure(f, package, order):
    destination = os.getenv("PYPMIS_O2B_CLOSE_PERFORMANCE")
    if not destination:
        return
    target = Path(destination).resolve()
    evidence = Path(__file__).resolve().parents[2] / "outputs/.qa/wave-o2b-close-20261111"
    assert target.is_relative_to(evidence)
    workspace = f.project_workspace_id
    source = f"/api/v1/procurement/projects/{workspace}"
    period = f.current_period["id"]
    items = (
        ("Procurement Register", source + "/packages", {}),
        ("Material Availability", source + "/material-availability", {"work_package_id": f.iwp["id"]}),
        ("Procurement Look-Ahead", source + "/lookahead", {"package_id": package["id"]}),
        ("Cost lookup", root(f, "cost") + "/lookup", {"source_entity_type": "PO", "source_entity_id": order["id"]}),
        (
            "Progress lookup",
            root(f, "progress") + "/lookup",
            {"source_entity_type": "RECEIPT", "source_entity_id": f.chain["receipt"]["id"], "period_id": period},
        ),
        (
            "Forecast lookup",
            root(f, "forecast") + "/lookup",
            {
                "source_entity_type": "PACKAGE_FORECAST",
                "source_entity_id": package["id"],
                "period_id": period,
                "consumer_version_id": f.draft_forecast["id"],
                "signal_key": "forecast_delivery_date",
            },
        ),
    )
    metrics = []
    for name, path, params in items:
        samples = []
        for _ in range(3):
            start = perf_counter()
            response = request(f, "GET", path, actor="manager", params=params)
            samples.append(round(1000 * (perf_counter() - start), 3))
            expect(response, 200)
        metrics.append(
            {
                "operation": name,
                "samples_ms": samples,
                "median_ms": median(samples),
                "response_bytes": len(response.content),
            }
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("x", encoding="utf-8") as file:
        json.dump(
            {
                "scope": "local ASGI HTTP + PostgreSQL 16, no production SLA",
                "workspace": workspace,
                "operations": metrics,
            },
            file,
            indent=2,
        )


def test_procurement_progress_consumer_release(governed):
    f = governed
    period = f.current_period["id"]
    context = {"period_id": period}
    trace = get(f, "/trace", package_id=f.chain["package"]["id"])["records"]
    events = [
        ("ACCEPTED_INSPECTION", f.chain["inspection"]["id"]),
        ("DISPATCH", f.chain["shipment"]["id"]),
        ("ARRIVAL", f.chain["shipment"]["id"]),
        ("RECEIPT", f.chain["receipt"]["id"]),
        ("ACCEPTANCE", trace["ACCEPTANCE"][0]["id"]),
    ]
    for kind, identity in events:
        source = lookup(f, "progress", kind, identity, **context)
        assert source["consumer_status"] == "NOT_ADOPTED"
        if kind == "ACCEPTANCE":
            assert {"ACCEPTED", "REJECTED", "QUARANTINE"} <= set(source["facts"]["classifications"])
        data = decision(source, **context)
        decide(f, "progress", data | {"source_hash": "0" * 64}, status=409)
        row = decide(f, "progress", data)
        assert row["consumer_status"] == "ADOPTED" and row["period_id"] == period
        assert lookup(f, "progress", kind, identity, **context)["consumer_status"] == "ADOPTED"
    assert signatures(f) == f.signatures_before_procurement


def test_procurement_forecast_consumer_release(governed):
    f = governed
    forecast = f.draft_forecast
    package = f.chain["package"]
    context = {
        "period_id": f.current_period["id"],
        "consumer_version_id": forecast["id"],
        "signal_key": "forecast_delivery_date",
    }
    source = lookup(f, "forecast", "PACKAGE_FORECAST", package["id"], **context)
    data = decision(source, **context, consumer_version=forecast["version"])
    decide(f, "forecast", data | {"source_hash": "0" * 64}, status=409)
    decide(f, "forecast", data | {"consumer_version": 99}, status=409)
    decide(f, "forecast", data | {"effective_at": (TODAY + timedelta(days=1)).isoformat()}, status=422)
    row = decide(f, "forecast", data)
    assert row["source_forecast_date"] == source["facts"]["signals"]["forecast_delivery_date"]
    assert row["consumer_version"] == forecast["version"] and row["consumer_status"] == "ADOPTED"
    withdrawn = decide(f, "forecast", data | {"consumer_status": "NOT_ADOPTED"}, version=row["version"])
    assert withdrawn["version"] == row["version"] + 1 and withdrawn["consumer_status"] == "NOT_ADOPTED"
    decide(
        f,
        "forecast",
        data | {"consumer_version_id": f.approved_forecast["id"], "consumer_version": f.approved_forecast["version"]},
        status=409,
    )
    assert signatures(f) == f.signatures_before_procurement


def test_procurement_cost_consumer_release(governed):
    f = governed
    package, order = f.chain["package"], f.chain["po"]
    source = lookup(f, "cost", "PO", order["id"])
    decide(f, "cost", decision(source), status=409)
    mapping(f, "PACKAGE", package["id"], "CBS", f.cost_cbs["id"])
    mapping(f, "PACKAGE", package["id"], "COST_CODE", f.cost_code["id"])
    missing_account = lookup(f, "cost", "PO", order["id"])
    decide(
        f,
        "cost",
        decision(missing_account, mapping_ids=[r["id"] for r in missing_account["cost_mappings"]]),
        status=409,
    )
    mapping(f, "PACKAGE", package["id"], "CONTROL_ACCOUNT", f.cost_account["id"])
    source = lookup(f, "cost", "PO", order["id"])
    data = decision(source, mapping_ids=[r["id"] for r in source["cost_mappings"]])
    decide(f, "cost", data | {"source_version": source["source_version"] + 1}, status=409)
    decide(f, "cost", data | {"source_hash": "0" * 64}, status=409)
    decide(f, "cost", data | {"source_entity_id": 2_000_000_000}, status=404)
    decide(f, "cost", data | {"source_package_id": 2_000_000_000}, status=404)
    decide(f, "cost", data, actor="foreign", status=404)
    decide(f, "cost", data, actor="buyer", status=403)
    decide(f, "cost", data, actor="executive", status=403)
    decide(f, "cost", data, workspace=f.workspaces["other_project"].id, status=403)
    # A consumer-only request cannot masquerade as a Procurement command or mutate a PO.
    decide(f, "cost", data | {"po_status": "CANCELLED"}, status=422)
    before = signatures(f, ("procurement_purchase_orders", "procurement_po_revisions"))
    key = "o2b-close-cost-adoption"
    row = decide(f, "cost", data, key=key)
    assert decide(f, "cost", data, key=key) == row
    decide(f, "cost", data | {"reason": "Attempt to reuse the same decision key"}, key=key, status=409)
    decide(f, "cost", data, status=412)
    assert signatures(f, ("procurement_purchase_orders", "procurement_po_revisions")) == before
    assert signatures(f) == f.signatures_before_procurement
    measure(f, package, order)
    old_revision = order["current_revision_id"]
    revision = cmd(
        f,
        f"/purchase-orders/{order['id']}/revisions",
        {
            "effective_date": TODAY.isoformat(),
            "changed_lines": [{"line_id": f.chain["po_line"]["id"], "quantity": "10", "unit_price": "11"}],
        },
        version=order["version"],
    )
    cmd(
        f,
        f"/purchase-orders/{order['id']}/revisions/{revision['id']}/approve",
        {"approval_reference": "Independent amendment review"},
        actor="po_approver",
        version=revision["version"],
        status=200,
    )
    decide(f, "cost", data, version=1, status=409)
    lookup(f, "cost", "PO_REVISION", old_revision, status=409)
    current = lookup(f, "cost", "PO_REVISION", revision["id"])
    assert current["source_id"] == revision["id"]
    with SessionLocal() as db:
        for verb in (
            "UPDATE operational_procurement_adoptions SET reason='overwrite'",
            "DELETE FROM operational_procurement_adoptions",
        ):
            with pytest.raises(DBAPIError), db.begin_nested():
                db.execute(text(verb + " WHERE id=:identity"), {"identity": row["id"]})
    assert signatures(f) == f.signatures_before_procurement
