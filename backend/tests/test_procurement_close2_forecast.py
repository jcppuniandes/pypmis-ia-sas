"""Two native Procurement forecasts through adoption, succession and retirement."""

import json
import os
from datetime import timedelta
from pathlib import Path

from sqlalchemy import select
from tests.engineering_release_fixture import TODAY, request
from tests.test_procurement_consumer_release import (
    decide,
    decision,
    lookup,
    root,
    signatures,
)
from tests.test_procurement_consumer_release import (
    governed as governed,
)
from tests.test_procurement_o2b_release import cmd, expect, get

from app.database.session import SessionLocal
from app.modules.procurement_consumers.models import ProcurementAdoption

MILESTONE = "MILESTONE_FORECAST"
EXPEDITING = "EXPEDITING_FORECAST"


def day(offset):
    return (TODAY + timedelta(days=offset)).isoformat()


def lookup_forecast(f, kind, identity, context, **kwargs):
    return lookup(f, "forecast", kind, identity, **context, **kwargs)


def adopt_current(f, kind, record, context, expected_date, plan_date):
    source = lookup_forecast(f, kind, record["id"], context)
    assert source["source_id"] == record["id"]
    assert source["source_version"] == record["version"]
    assert source["facts"]["signals"]["forecast_date"] == expected_date != plan_date
    assert source["consumer_status"] == "NOT_ADOPTED"
    command = decision(source, **context, consumer_version=f.draft_forecast["version"])
    for bad_pin, error in (
        ({"source_hash": "0" * 64}, "SOURCE_HASH_MISMATCH"),
        ({"source_version": command["source_version"] + 1}, "SOURCE_VERSION_MISMATCH"),
    ):
        assert decide(f, "forecast", command | bad_pin, status=409)["detail"] == f"PROCUREMENT_CONSUMER_{error}"
    adopted = decide(f, "forecast", command)
    assert adopted["source_forecast_date"] == expected_date
    assert adopted["consumer_status"] == "ADOPTED"
    assert adopted["source_hash"] == command["source_hash"]
    assert lookup_forecast(f, kind, record["id"], context)["consumer_status"] == "ADOPTED"
    return command, adopted


def rejected(f, kind, identity, context, command, error, *, version):
    detail = f"PROCUREMENT_CONSUMER_{error}"
    assert lookup_forecast(f, kind, identity, context, status=409)["detail"] == detail
    assert decide(f, "forecast", command, version=version, status=409)["detail"] == detail


def forecast_context(f):
    return {
        "period_id": f.current_period["id"],
        "consumer_version_id": f.draft_forecast["id"],
        "signal_key": "forecast_date",
    }


def forecast_state(f):
    base = f"/api/v1/forecast/projects/{f.project_workspace_id}/versions"
    return (
        signatures(f),
        expect(request(f, "GET", f"{base}/{f.approved_forecast['id']}", actor="manager"), 200),
        expect(request(f, "GET", f"{base}/{f.draft_forecast['id']}", actor="manager"), 200),
    )


def check_history(f, kind, *adopted):
    ids = {row["id"] for row in adopted}
    response = expect(request(f, "GET", root(f, "forecast"), actor="manager"), 200)
    items = {row["id"]: row for row in response["items"] if row["source_entity_type"] == kind}
    assert set(items) == ids
    with SessionLocal() as db:
        rows = list(
            db.scalars(
                select(ProcurementAdoption).where(
                    ProcurementAdoption.tenant_id == f.tenant_id,
                    ProcurementAdoption.project_workspace_id == f.project_workspace_id,
                    ProcurementAdoption.consumer == "FORECAST",
                    ProcurementAdoption.source_entity_type == kind,
                )
            )
        )
    assert {row.id for row in rows} == ids
    for row in rows:
        saved = items[row.id]
        assert saved == next(expected for expected in adopted if expected["id"] == row.id)
        assert row.source_entity_id == saved["source_entity_id"]
        assert row.source_version == saved["source_version"]
        assert row.source_hash == saved["source_hash"]
        assert row.source_forecast_date.isoformat() == saved["source_forecast_date"]
        assert row.period_id == f.current_period["id"]
        assert row.consumer_version_id == f.draft_forecast["id"]


def record_evidence(f, name, field, plan, old, new, retired, before, after):
    evidence = os.getenv("PYPMIS_CLOSE2_EVIDENCE")
    if evidence:
        with (Path(evidence) / f"{name}-forecast-evidence.json").open("x", encoding="utf-8") as stream:
            json.dump(
                {
                    "workspace_id": f.project_workspace_id,
                    "approved_forecast_id": f.approved_forecast["id"],
                    "draft_forecast_id": f.draft_forecast["id"],
                    "source_field": field,
                    "planned_reference": plan,
                    "initial": {
                        key: old[key]
                        for key in ("id", "source_entity_id", "source_version", "source_hash", "source_forecast_date")
                    },
                    "successor": {
                        key: new[key]
                        for key in ("id", "source_entity_id", "source_version", "source_hash", "source_forecast_date")
                    },
                    "inactive_source_id": retired["id"],
                    "authority_sql_before": before[0],
                    "authority_sql_after": after[0],
                    "approved_forecast_http_unchanged": before[1] == after[1],
                    "draft_forecast_http_unchanged": before[2] == after[2],
                },
                stream,
                indent=2,
            )


def test_forecast_native_milestone_successor_and_inactivation(governed):
    f = governed
    context, before = forecast_context(f), forecast_state(f)
    planned = day(4)
    original = cmd(
        f,
        "/vendor-milestones",
        {
            "po_line_id": f.chain["po_line"]["id"],
            "code": "MANUFACTURING_FORECAST_CLOSE2",
            "planned_date": planned,
            "forecast_date": day(2),
        },
        actor="material",
    )
    old_pin, old = adopt_current(f, MILESTONE, original, context, day(2), planned)
    assert old["source_snapshot"]["facts"]["signals"]["planned_date"] == planned

    def successor(row, payload):
        return cmd(f, f"/vendor-milestones/{row['id']}/successor", payload, actor="material", version=row["version"])

    current = successor(original, {"forecast_date": day(5)})
    assert current["supersedes_id"] == original["id"]
    assert current["version"] == original["version"] + 1
    rejected(f, MILESTONE, original["id"], context, old_pin, "MILESTONE_SUPERSEDED", version=old["version"])
    current_pin, new = adopt_current(f, MILESTONE, current, context, day(5), planned)
    assert new["source_hash"] != old["source_hash"]
    assert (
        decide(
            f, "forecast", current_pin | {"source_version": original["version"]}, version=new["version"], status=409
        )["detail"]
        == "PROCUREMENT_CONSUMER_SOURCE_VERSION_MISMATCH"
    )

    completed = successor(current, {"actual_date": day(0)})
    assert completed["actual_date"] == day(0) and completed["planned_date"] == planned
    assert completed["forecast_date"] is None
    rejected(f, MILESTONE, current["id"], context, current_pin, "MILESTONE_SUPERSEDED", version=new["version"])
    completed_pin = current_pin | {"source_entity_id": completed["id"], "source_version": completed["version"]}
    rejected(f, MILESTONE, completed["id"], context, completed_pin, "MILESTONE_FORECAST_INVALID", version=0)
    check_history(f, MILESTONE, old, new)
    after = forecast_state(f)
    assert after == before
    record_evidence(
        f, "milestone", "procurement_vendor_milestones.forecast_date", planned, old, new, completed, before, after
    )


def test_forecast_native_expediting_successor_and_withdrawal(governed):
    f = governed
    context, before = forecast_context(f), forecast_state(f)
    native_line = f.chain["po_line"]
    planned = native_line["requested_date"]

    def observation(forecast_date, detail, observed=None):
        return cmd(
            f,
            "/expediting-events",
            {
                "po_line_id": native_line["id"],
                "event_type": "DISPATCH_FORECAST",
                "observation_date": observed or day(0),
                "forecast_date": forecast_date,
                "detail": detail,
            },
            actor="material",
        )

    stale = observation(day(1), "Obsolete vendor observation", day(-31))
    assert lookup_forecast(f, EXPEDITING, stale["id"], context, status=409)["detail"] == (
        "PROCUREMENT_CONSUMER_FORECAST_OBSERVATION_STALE"
    )
    initial = observation(day(3), "Initial dispatch forecast")
    initial_pin, old = adopt_current(f, EXPEDITING, initial, context, day(3), planned)
    assert old["source_snapshot"]["facts"]["signals"] == {"forecast_date": day(3)}

    current = observation(day(6), "Current dispatch forecast supersedes the preceding observation")
    assert current["id"] > initial["id"]
    assert current["observation_date"] == initial["observation_date"]
    rejected(
        f, EXPEDITING, initial["id"], context, initial_pin, "EXPEDITING_FORECAST_SUPERSEDED", version=old["version"]
    )
    current_pin, new = adopt_current(f, EXPEDITING, current, context, day(6), planned)
    assert new["source_hash"] != old["source_hash"]
    assert (
        decide(
            f, "forecast", current_pin | {"source_hash": initial_pin["source_hash"]}, version=new["version"], status=409
        )["detail"]
        == "PROCUREMENT_CONSUMER_SOURCE_HASH_MISMATCH"
    )

    withdrawn = observation(None, "Vendor withdrew the estimate; no current date available")
    assert withdrawn["forecast_date"] is None and withdrawn["id"] > current["id"]
    assert get(f, f"/purchase-orders/{f.chain['po']['id']}")["lines"][0]["requested_date"] == planned
    rejected(
        f, EXPEDITING, current["id"], context, current_pin, "EXPEDITING_FORECAST_SUPERSEDED", version=new["version"]
    )
    withdrawn_pin = current_pin | {"source_entity_id": withdrawn["id"], "source_version": withdrawn["version"]}
    rejected(f, EXPEDITING, withdrawn["id"], context, withdrawn_pin, "EXPEDITING_FORECAST_INVALID", version=0)
    check_history(f, EXPEDITING, old, new)
    after = forecast_state(f)
    assert after == before
    record_evidence(
        f, "expediting", "procurement_expediting_events.forecast_date", planned, old, new, withdrawn, before, after
    )
