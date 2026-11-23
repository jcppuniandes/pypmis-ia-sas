"""Native consumer Quality decisions with actual PostgreSQL upstream lifecycles."""

import json
import os
from copy import deepcopy
from decimal import Decimal
from pathlib import Path
from statistics import median
from time import perf_counter
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event
from tests.engineering_release_fixture import request
from tests.field_operations_release_fixture import approve_report
from tests.quality_release_fixture import REASON, call, command, create_acceptance, setup
from tests.test_field_operations_consumers_release import lookup as field_lookup
from tests.test_field_operations_consumers_release import payload as field_payload
from tests.test_procurement_consumer_release import TABLES, signatures
from tests.test_procurement_o2b_release import expect

from app.database.session import SessionLocal, engine
from app.main import app
from app.modules.contracts_foundation.permissions import ensure_contracts_permissions
from app.modules.progress_foundation.policy import DEFAULT_PROFILE

pytestmark = pytest.mark.skipif(
    os.getenv("PYPMIS_O3B_FIXTURE") != "disposable-only", reason="Dedicated O3B PostgreSQL required"
)
QA = Path(__file__).resolve().parents[2] / "outputs/.qa/wave-o3b-20261119"


def root(f, domain):
    return f"/api/v1/{domain}/projects/{f.project_workspace_id}/quality-adoptions"


def lookup(f, domain, kind, identity, actor="manager", status=200):
    return expect(
        request(
            f,
            "GET",
            root(f, domain) + "/lookup",
            actor=actor,
            params={"source_entity_type": kind, "source_entity_id": identity},
        ),
        status,
    )


def payload(source, **extras):
    return (
        REASON
        | {
            key: source[key]
            for key in ("source_entity_type", "source_entity_id", "source_version", "source_hash", "observed_at")
        }
        | {"decision": "ADOPT"}
        | extras
    )


def decide(f, domain, body, actor="manager", version=0, key=None, status=201):
    return expect(request(f, "POST", root(f, domain), actor=actor, payload=body, version=version, key=key), status)


@pytest.fixture(scope="module")
def governed():
    with TestClient(app) as client, SessionLocal() as db:
        f = setup(db, client)
        workspace = f.workspaces["direct"]
        workspace.defaults_json = workspace.defaults_json | {
            "enabled_modules": [*workspace.defaults_json["enabled_modules"], "contracts"]
        }
        ensure_contracts_permissions(db, f.tenant_id, f.users["admin"].id)
        ensure_contracts_permissions(db, f.foreign_tenant.id, f.users["foreign"].id)
        db.commit()
        policy = deepcopy(DEFAULT_PROFILE) | {"quality_policy": {"require_acceptance_for_approval": True}}
        previous = f.progress_profile
        draft = expect(
            request(
                f,
                "POST",
                f"/api/v1/progress/admin/profiles/{previous['id']}/successor",
                actor="admin",
                version=previous["version"],
                payload=REASON,
            ),
            201,
        )
        draft = expect(
            request(
                f,
                "PUT",
                f"/api/v1/progress/admin/profiles/{draft['id']}",
                actor="admin",
                version=draft["version"],
                payload=REASON | {"name": draft["name"], "content_json": policy},
            ),
            200,
        )
        f.progress_profile = expect(
            request(
                f,
                "POST",
                f"/api/v1/progress/admin/profiles/{draft['id']}/publish",
                actor="publisher",
                version=draft["version"],
                payload=REASON,
            ),
            200,
        )
        approve_report(f)
        field = field_lookup(f, "progress", "PRODUCTION", f.field_production["id"])
        adopted = expect(
            request(
                f,
                "POST",
                f"/api/v1/progress/projects/{f.project_workspace_id}/field-adoptions",
                actor="cost_controller",
                version=0,
                payload=field_payload(
                    field,
                    quantity="1",
                    decision="PARTIAL_ADOPT",
                    period_id=f.current_period["id"],
                    measurement_code="QUALITY-NATIVE-PROGRESS",
                ),
            ),
            201,
        )
        f.quality_native_measurement_id = adopted["linked_entity_id"]
        f.quality_progress_root = f"/api/v1/progress/projects/{f.project_workspace_id}"
        yield f


def measurement(f):
    return expect(
        request(
            f,
            "GET",
            f.quality_progress_root + f"/measurements/{f.quality_native_measurement_id}",
            actor="cost_controller",
        ),
        200,
    )


def measured_reads(f, queries):
    results, mutations = [], []

    def observe(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith(("INSERT ", "UPDATE ", "DELETE ", "MERGE ")):
            mutations.append(statement.splitlines()[0][:120])

    event.listen(engine, "before_cursor_execute", observe)
    try:
        for name, path, params, actor in queries:
            samples, sizes, counts = [], [], []
            for _ in range(3):
                start = perf_counter()
                response = call(f, "GET", path, actor=actor, params=params)
                assert response.status_code == 200, response.text
                samples.append(round((perf_counter() - start) * 1000, 3))
                sizes.append(len(response.content))
                value = response.json()
                counts.append(
                    len(value["items"])
                    if isinstance(value, dict) and isinstance(value.get("items"), list)
                    else len(value)
                    if isinstance(value, list)
                    else 1
                )
            results.append(
                {"query": name, "samples_ms": samples, "median_ms": median(samples), "bytes": sizes, "rows": counts}
            )
    finally:
        event.remove(engine, "before_cursor_execute", observe)
    assert not mutations, mutations
    return results


def test_progress_native_policy_requires_quality_but_quality_does_not_write_progress(governed):
    f = governed
    row = measurement(f)
    for endpoint, actor, data in (
        ("transition", "cost_controller", {"status": "SUBMITTED"}),
        ("certify", "manager", {"evidence_reference": "Independent native quantity certification"}),
        ("transition", "manager", {"status": "UNDER_REVIEW"}),
    ):
        row = expect(
            request(
                f,
                "POST",
                f.quality_progress_root + f"/measurements/{row['id']}/{endpoint}",
                actor=actor,
                payload=REASON | data,
                version=row["version"],
            ),
            200,
        )
    failure = expect(
        request(
            f,
            "POST",
            f.quality_progress_root + f"/measurements/{row['id']}/transition",
            actor="manager",
            payload=REASON | {"status": "APPROVED"},
            version=row["version"],
        ),
        409,
    )
    assert "QUALITY_ACCEPTANCE_REQUIRED" in str(failure)
    before = signatures(f)
    acceptance = create_acceptance(f)
    assert signatures(f) == before
    # This fixture already has native approved progress. Quality covers only the
    # newly reserved Field unit, not that historical cumulative quantity again.
    assert Decimal(row["numerator"]) > Decimal(acceptance["quantity"])
    source = lookup(f, "progress", "ACCEPTANCE", acceptance["id"], actor="cost_controller")
    before = signatures(f)
    key = "o3b-quality-progress-" + uuid4().hex
    body = payload(source, measurement_id=row["id"])
    result = decide(f, "progress", body, actor="cost_controller", key=key)
    assert decide(f, "progress", body, actor="cost_controller", key=key) == result
    assert signatures(f) == before
    decide(
        f,
        "progress",
        body | {"reason": "Changed idempotent content is refused"},
        actor="cost_controller",
        key=key,
        status=409,
    )
    decide(f, "progress", body, actor="cost_controller", version=1, status=409)
    decide(f, "progress", body | {"decision": "RECONCILE"}, actor="cost_controller", version=0, status=412)
    f.quality_progress_decision = result
    # A successor acceptance requires a new native decision, not silent readoption.
    successor = command(
        f, "/acceptances", f.quality_acceptance_body | {"supersedes_id": acceptance["id"]}, actor="quality_approver"
    )
    stale = measurement(f)
    assert stale["source_state"] == "REQUIRES_REVIEW"
    decide(f, "progress", body | {"decision": "RECONCILE"}, actor="cost_controller", version=1, status=409)
    fresh = lookup(f, "progress", "ACCEPTANCE", successor["id"], actor="cost_controller")
    f.quality_progress_decision = decide(
        f,
        "progress",
        payload(fresh, measurement_id=row["id"], decision="RECONCILE"),
        actor="cost_controller",
        version=1,
    )
    f.quality_acceptance = successor
    approved = expect(
        request(
            f,
            "POST",
            f.quality_progress_root + f"/measurements/{row['id']}/transition",
            actor="manager",
            payload=REASON | {"status": "APPROVED"},
            version=row["version"],
        ),
        200,
    )
    assert approved["status"] == "APPROVED"
    assert approved["numerator"] == row["numerator"]
    f.quality_progress_approved = approved
    decide(
        f,
        "progress",
        payload(fresh, measurement_id=row["id"], decision="RECONCILE"),
        actor="cost_controller",
        version=2,
        status=409,
    )


def test_awp_explicit_quality_assessment_does_not_release_or_clear(governed):
    f = governed
    assessment = command(
        f,
        "/readiness/assess",
        {"itp_id": f.quality_itp["id"], "subject_reference": f.quality_subject},
        actor="quality_manager",
        version=0,
    )
    assert assessment["readiness_state"] == "READY"
    source = lookup(f, "awp", "READINESS", assessment["id"], actor="awp_manager")
    before = signatures(f, ("awp_execution_constraints", *TABLES))
    decision = decide(f, "awp", payload(source, work_package_id=f.field_released_iwp["id"]), actor="awp_manager")
    assert decision["linked_entity_type"] == "WorkPackage"
    assert signatures(f, ("awp_execution_constraints", *TABLES)) == before
    f.quality_assessment, f.quality_awp_decision = assessment, decision
    native = expect(request(f, "GET", f.awp_root + "/overview", actor="awp_manager"), 200)["current_readiness"][
        str(f.field_released_iwp["id"])
    ]
    assert native["dimensions"]["QUALITY"]["state"] == "READY"
    assert "quality" in native["source_hashes"]
    # Assessing AWP cannot invalidate the Quality proof which it just consumed.
    assert lookup(f, "awp", "READINESS", assessment["id"], actor="awp_manager")["source_state"] == "CURRENT"
    assert (
        lookup(f, "progress", "ACCEPTANCE", f.quality_acceptance["id"], actor="cost_controller")["source_state"]
        == "CURRENT"
    )


def test_consumers_are_native_scoped_and_information_only_when_required(governed):
    f = governed
    acceptance = f.quality_acceptance
    source = lookup(f, "contracts", "ACCEPTANCE", acceptance["id"])
    before = signatures(f)
    for domain in ("progress", "awp", "cost", "contracts", "schedule"):
        lookup(f, domain, "ACCEPTANCE", acceptance["id"], actor="quality_inspector", status=403)
    expect(request(f, "POST", root(f, "contracts"), payload=payload(source)), 405)
    expect(request(f, "POST", root(f, "schedule"), payload=payload(source)), 405)
    assert signatures(f) == before
    lookup(f, "contracts", "ACCEPTANCE", acceptance["id"], actor="foreign", status=404)
    lookup(f, "contracts", "ACCEPTANCE", acceptance["id"], actor="quality_reporter", status=403)
    f.quality_contracts_source = source


def test_cost_classification_is_explicit_and_never_an_actual(governed):
    f = governed
    source = lookup(f, "cost", "ACCEPTANCE", f.quality_acceptance["id"], actor="cost_controller")
    before = signatures(
        f, ("cost_actual_entries", "cost_budget_versions", "commercial_commitments", "progress_measurements")
    )
    row = decide(
        f,
        "cost",
        payload(
            source, cbs_id=f.cost_cbs["id"], cost_code_id=f.cost_code["id"], control_account_id=f.cost_account["id"]
        ),
        actor="cost_controller",
    )
    assert row["linked_entity_id"] is None and row["mapping_reference"]["cbs_id"] == f.cost_cbs["id"]
    assert (
        signatures(
            f, ("cost_actual_entries", "cost_budget_versions", "commercial_commitments", "progress_measurements")
        )
        == before
    )


def test_populated_quality_downgrade_refuses_before_any_ddl(governed):
    import importlib.util

    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import text

    path = Path(__file__).resolve().parents[1] / "alembic/versions/20261120_0081_quality_management.py"
    spec = importlib.util.spec_from_file_location("o3b_populated_downgrade", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as connection:
        assert connection.scalar(text("SELECT EXISTS (SELECT 1 FROM quality_plans)"))
        with (
            Operations.context(MigrationContext.configure(connection)),
            pytest.raises(RuntimeError, match="Refusing to discard governed Quality"),
        ):
            migration.downgrade()
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "20261120_0081"
    (QA / "migration/populated-refusal.json").write_text(
        json.dumps(
            {
                "status": "PASS",
                "real_alembic_operations": True,
                "revision_unchanged": "20261120_0081",
                "ddl_executed": False,
            }
        ),
        encoding="utf-8",
    )


def test_quality_lot_link_and_readiness_assessment_streams(governed):
    f = governed
    receipt = expect(
        call(
            f,
            "GET",
            "/source",
            params={"source_type": "MATERIAL_RECEIPT_LINE", "source_id": f.chain["receipt"]["lines"][0]["id"]},
        ),
        200,
    )
    body = {
        "receipt_reference": {
            key: receipt[key] for key in ("source_type", "source_id", "source_version", "source_hash")
        },
        "production_reference": f.quality_subject,
        "lot_identifiers": {"lot": "O3B-LOT", "heat": "O3B-HEAT"},
        "quantity": "1",
        "uom": receipt["facts"]["uom"],
        "document_reference": f.quality_document_pin,
    }
    before = signatures(
        f, ("procurement_material_receipt_lines", "procurement_material_acceptances", "field_production_records")
    )
    row = command(f, "/lot-links", body, actor="quality_manager", version=0)
    data = expect(
        call(
            f,
            "GET",
            "/lot-links",
            params={"receipt_line_id": receipt["source_id"], "production_id": f.field_production["id"]},
        ),
        200,
    )
    assert data["version"] == 1 and data["latest_id"] == row["id"]
    command(
        f,
        "/lot-links",
        body | {"supersedes_id": row["id"], "action": "REMOVE"},
        actor="quality_manager",
        version=0,
        status=412,
    )
    command(
        f,
        "/lot-links",
        body | {"uom": "WRONG", "supersedes_id": row["id"]},
        actor="quality_manager",
        version=1,
        status=422,
    )
    assert (
        signatures(
            f, ("procurement_material_receipt_lines", "procurement_material_acceptances", "field_production_records")
        )
        == before
    )


def test_quality_performance_reads_are_pure_and_measured_three_times(governed):
    f = governed
    queries = [
        ("Dashboard", "/dashboard", {}, "quality_reporter"),
        ("ITP Register", "/itps", {}, "quality_reporter"),
        ("Inspection Queue", "/inspection-requests", {}, "quality_reporter"),
        ("Test Register", "/tests", {}, "quality_reporter"),
        ("NCR Register", "/ncrs", {}, "quality_reporter"),
        (
            "Readiness",
            "/readiness",
            {"itp_id": f.quality_itp["id"], "source_type": "FIELD_PRODUCTION", "source_id": f.field_production["id"]},
            "quality_reporter",
        ),
        ("Lookahead", "/lookahead", {}, "quality_reporter"),
        ("Trace", "/trace", {"entity_type": "ACCEPTANCE", "entity_id": f.quality_acceptance["id"]}, "quality_reporter"),
        (
            "Progress lookup",
            root(f, "progress") + "/lookup",
            {"source_entity_type": "ACCEPTANCE", "source_entity_id": f.quality_acceptance["id"]},
            "cost_controller",
        ),
        (
            "AWP lookup",
            root(f, "awp") + "/lookup",
            {"source_entity_type": "READINESS", "source_entity_id": f.quality_assessment["id"]},
            "awp_manager",
        ),
    ]
    before = signatures(f, (*TABLES, "quality_history", "quality_consumer_decisions", "quality_readiness_assessments"))
    results = measured_reads(f, queries)
    assert (
        signatures(f, (*TABLES, "quality_history", "quality_consumer_decisions", "quality_readiness_assessments"))
        == before
    )
    QA.mkdir(parents=True, exist_ok=True)
    (QA / "consumer-performance.json").write_text(
        json.dumps(
            {
                "environment": "PostgreSQL 16 isolated loopback5567 ASGI TestClient Windows",
                "reads": results,
                "no_sql_writes": True,
                "no_sla": True,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (QA / "consumer-evidence.json").write_text(
        json.dumps(
            {
                "status": "PASS" if getattr(f, "quality_progress_approved", None) else "INCOMPLETE",
                "native_progress_approved": bool(getattr(f, "quality_progress_approved", None)),
                "tenant_id": f.tenant_id,
                "workspace_id": f.project_workspace_id,
                "acceptance_id": f.quality_acceptance["id"],
                "progress_decision_id": f.quality_progress_decision["id"],
                "awp_decision_id": f.quality_awp_decision["id"],
                "assessment_id": f.quality_assessment["id"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
