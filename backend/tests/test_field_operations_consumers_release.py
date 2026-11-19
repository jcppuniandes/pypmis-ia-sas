"""Native owner adoption of actual governed Field facts on isolated PostgreSQL."""

import json
import os
import statistics
import time
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from tests.engineering_release_fixture import TODAY, request
from tests.field_operations_release_fixture import (
    REASON,
    action,
    approve_report,
    command,
    create_core_chain,
    create_verified_production,
    setup,
)
from tests.test_procurement_consumer_release import signatures
from tests.test_procurement_o2b_release import expect

from app.database.session import SessionLocal
from app.main import app
from app.modules.contracts_foundation.permissions import ensure_contracts_permissions
from app.modules.field_operations.consumer_models import FieldConsumerDecision

pytestmark = pytest.mark.skipif(
    os.getenv("PYPMIS_O3A_FIXTURE") != "disposable-only", reason="Isolated O3A PostgreSQL required"
)


def root(f, consumer):
    return f"/api/v1/{consumer}/projects/{f.project_workspace_id}/field-adoptions"


def lookup(f, consumer, kind, identity, *, actor="manager", status=200):
    return expect(
        request(
            f,
            "GET",
            root(f, consumer) + "/lookup",
            actor=actor,
            params={
                "source_entity_type": kind,
                "source_entity_id": identity,
            },
        ),
        status,
    )


def payload(source, **extras):
    return (
        REASON
        | {
            key: source[key]
            for key in (
                "source_entity_type",
                "source_entity_id",
                "source_version",
                "source_hash",
                "observed_at",
            )
        }
        | {"decision": "ADOPT"}
        | extras
    )


def decide(f, consumer, body, *, actor="manager", version=0, key=None, status=201):
    return expect(request(f, "POST", root(f, consumer), actor=actor, payload=body, version=version, key=key), status)


@pytest.fixture(scope="module")
def governed():
    with TestClient(app) as client, SessionLocal() as db:
        f = create_core_chain(setup(db, client))
        workspace = f.workspaces["direct"]
        workspace.defaults_json = workspace.defaults_json | {
            "enabled_modules": [*workspace.defaults_json["enabled_modules"], "contracts"],
        }
        ensure_contracts_permissions(db, f.tenant_id, f.users["admin"].id)
        db.commit()
        create_verified_production(f)
        # Creating and verifying Field facts has not inserted a consumer decision.
        assert (
            db.scalar(
                select(func.count())
                .select_from(FieldConsumerDecision)
                .where(
                    FieldConsumerDecision.tenant_id == f.tenant_id,
                )
            )
            == 0
        )
        approve_report(f)
        yield f


def test_field_progress_explicit_adoption_is_draft_and_idempotent(governed):
    f = governed
    source = lookup(f, "progress", "PRODUCTION", f.field_production["id"])
    body = payload(
        source,
        quantity="1",
        decision="PARTIAL_ADOPT",
        period_id=f.current_period["id"],
        measurement_code="FIELD-PROGRESS",
    )
    key = "o3a-progress-" + uuid4().hex
    result = decide(f, "progress", body, actor="cost_controller", key=key)
    assert decide(f, "progress", body, actor="cost_controller", key=key) == result
    decide(f, "progress", body | {"quantity": "0.5"}, actor="cost_controller", key=key, status=409)
    row = expect(
        request(
            f,
            "GET",
            f"/api/v1/progress/projects/{f.project_workspace_id}/measurements/{result['linked_entity_id']}",
            actor="cost_controller",
        ),
        200,
    )
    assert row["status"] == "DRAFT" and row["source_domain"] == "FIELD_OPERATIONS"
    assert row["source_snapshot"]["field_operations"][0]["source_hash"] == source["source_hash"]
    # A second reservation cannot strand quantity in a parallel native draft.
    source2 = lookup(f, "progress", "PRODUCTION", f.field_production["id"])
    decide(
        f,
        "progress",
        payload(source2, quantity="1", period_id=f.current_period["id"], measurement_code="FIELD-PROGRESS-2"),
        actor="cost_controller",
        version=1,
        status=409,
    )
    progress_root = f"/api/v1/progress/projects/{f.project_workspace_id}"
    for endpoint, actor, data in (
        ("transition", "cost_controller", {"status": "SUBMITTED"}),
        ("certify", "manager", {"evidence_reference": "Independent field inspection"}),
        ("transition", "manager", {"status": "UNDER_REVIEW"}),
        ("transition", "manager", {"status": "APPROVED"}),
    ):
        row = expect(
            request(
                f,
                "POST",
                progress_root + f"/measurements/{row['id']}/{endpoint}",
                actor=actor,
                payload=REASON | data,
                version=row["version"],
            ),
            200,
        )
    assert row["status"] == "APPROVED"
    source2 = lookup(f, "progress", "PRODUCTION", f.field_production["id"])
    second = decide(
        f,
        "progress",
        payload(source2, quantity="1", period_id=f.current_period["id"], measurement_code="FIELD-PROGRESS-2"),
        actor="cost_controller",
        version=1,
    )
    successor = expect(
        request(f, "GET", progress_root + f"/measurements/{second['linked_entity_id']}", actor="cost_controller"), 200
    )
    assert successor["supersedes_id"] == row["id"]
    assert Decimal(successor["numerator"]) == Decimal(row["numerator"]) + 1
    assert len(successor["source_snapshot"]["field_operations"]) == 2
    decide(
        f,
        "progress",
        payload(source2, quantity="1", period_id=f.current_period["id"], measurement_code="FIELD-OVER"),
        actor="cost_controller",
        version=2,
        status=409,
    )
    f.field_progress = row


def test_native_consumers_do_not_cross_authority(governed):
    f = governed
    event = command(
        f,
        "/events",
        {
            "event_code": "FIELD-EVENT",
            "workfront_id": f.field_front["id"],
            "event_type": "OTHER",
            "observed_at": f.field_production_body["observed_at"],
            "title": "Reported site condition",
            "description": "Observed access condition, not a contractual notice",
            "document_reference": f.field_document_pin,
        },
    )
    assert lookup(f, "contracts", "EVENT", event["id"])["facts"]["description"]
    constraint = command(
        f,
        "/constraints",
        {
            "observation_code": "FIELD-CONSTRAINT",
            "constraint_type": "ACCESS",
            "workfront_id": f.field_front["id"],
            "iwp_id": f.field_released_iwp["id"],
            "observation_date": TODAY.isoformat(),
            "description": "Observed access restriction for native AWP evaluation",
            "document_reference": f.field_document_pin,
        },
    )
    lookup(f, "awp", "CONSTRAINT", constraint["id"], status=409)
    constraint = action(f, "constraints", constraint, "verify", actor="field_supervisor")
    source = lookup(f, "awp", "CONSTRAINT", constraint["id"])
    result = decide(
        f,
        "awp",
        payload(source, constraint_type="ACCESS", constraint_code="ADOPTED-FIELD", blocking=True),
        actor="awp_manager",
    )
    assert result["linked_entity_type"] == "AWPExecutionConstraint"
    labor = lookup(f, "cost", "LABOR", f.field_labor["id"])
    body = payload(
        labor, cbs_id=f.cost_cbs["id"], cost_code_id=f.cost_code["id"], control_account_id=f.cost_account["id"]
    )
    cost = decide(f, "cost", body, actor="cost_controller")
    assert cost["linked_entity_id"] is None and cost["mapping_reference"]["cbs_id"]["id"] == f.cost_cbs["id"]
    decide(f, "cost", body, actor="cost_controller", version=1, status=409)
    assert lookup(f, "schedule", "WORKFRONT", f.field_front["id"])["facts"]["status"] == "ACTIVE"
    f.field_event, f.field_constraint = event, constraint


@pytest.mark.parametrize(
    "consumer,kind,attr",
    [
        ("progress", "PRODUCTION", "field_production"),
        ("cost", "LABOR", "field_labor"),
    ],
)
def test_consumer_auth_hash_period_and_shape_negatives(governed, consumer, kind, attr):
    f = governed
    identity = getattr(f, attr)["id"]
    lookup(f, consumer, kind, identity, actor="foreign", status=404)
    source = lookup(f, consumer, kind, identity)
    body = payload(source)
    decide(f, consumer, body, actor="field_reporter", status=403)
    decide(f, consumer, body | {"source_hash": "0" * 64}, status=409, version=source["version"])
    unrelated = {"cbs_id": f.cost_cbs["id"]} if consumer == "progress" else {"period_id": f.current_period["id"]}
    decide(f, consumer, body | unrelated, status=422, version=source["version"])


def test_field_read_performance_and_no_business_writes(governed):
    f = governed
    before = signatures(f)
    measurements = []
    paths = {
        "Dashboard": "/dashboard",
        "Workfronts": "/workfronts",
        "DailyReports": "/daily-reports",
        "Production": "/production",
        "Events": "/events",
        "Readiness": f"/readiness?workfront_id={f.field_front['id']}",
        "Lookahead": "/lookahead",
        "Trace": f"/trace?entity_type=PRODUCTION&entity_id={f.field_production['id']}",
    }
    paths["ProgressLookup"] = (
        root(f, "progress") + f"/lookup?source_entity_type=PRODUCTION&source_entity_id={f.field_production['id']}"
    )
    for name, path in paths.items():
        timings, sizes = [], []
        for _ in range(3):
            started = time.perf_counter()
            response = request(
                f,
                "GET",
                path
                if path.startswith("/api")
                else f"/api/v1/field-operations/projects/{f.project_workspace_id}" + path,
                actor="manager" if name == "ProgressLookup" else "field_reporter",
            )
            assert response.status_code == 200, response.text
            timings.append(round((time.perf_counter() - started) * 1000, 2))
            sizes.append(len(response.content))
        measurements.append(
            {"query": name, "samples_ms": timings, "median_ms": statistics.median(timings), "bytes": sizes}
        )
    output = Path(__file__).resolve().parents[2] / "outputs/.qa/wave-o3a-20261118/consumer-performance.json"
    output.write_text(
        json.dumps({"tenant_id": f.tenant_id, "workspace_id": f.project_workspace_id, "reads": measurements}, indent=2),
        encoding="utf-8",
    )
    assert signatures(f) == before
