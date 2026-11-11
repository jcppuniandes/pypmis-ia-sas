"""O2A consumer regressions on real scoped PostgreSQL O1 authorities."""

import os
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from tests import engineering_release_fixture as engineering
from tests import forecast_release_fixture as forecast
from tests.progress_release_fixture import request as progress_request
from tests.test_progress_foundation_release import approve as approve_progress
from tests.test_progress_foundation_release import measurement_body, rule
from tests.test_scope_foundation_release import success

from app.database.session import SessionLocal, engine
from app.main import app
from app.modules.cost_foundation.financial_models import CostActualEntry
from app.modules.cost_foundation.models import BudgetVersion, CostBaseline
from app.modules.forecast_foundation.models import ForecastVersion
from app.modules.progress_foundation.models import ProgressMeasurement
from app.modules.schedule_foundation.models import ScheduleBaseline, ScheduleRegister, ScheduleVersion
from app.modules.scope_foundation.models import PlanItem, ScopeBaseline, ScopeItem


@pytest.fixture(scope="module")
def project():
    if os.getenv("PYPMIS_O2A_FIXTURE") != "disposable-only":
        pytest.skip("O2A isolated PostgreSQL fixture required")
    assert engine.dialect.name == "postgresql" and engine.url.database == "o2a"
    with TestClient(app) as client, SessionLocal() as db:
        yield engineering.create_engineering_fixture(db, client, integrated=True)


@pytest.fixture(scope="module")
def current_period(project):
    # The real O1 inputs remain pinned to the original policy. The new common
    # period lets current Engineering facts be consumed without backdating them.
    prior = project.period
    for action, actor in (("review", "manager"), ("close", "admin")):
        prior = success(
            progress_request(
                project,
                "POST",
                f"/periods/{prior['id']}/transition",
                actor=actor,
                version=prior["version"],
                payload={**engineering.REASON, "action": action},
            )
        )["period"]
    today = engineering.TODAY
    end = today + timedelta(days=6)
    return success(
        progress_request(
            project,
            "POST",
            f"/api/v1/operational/projects/{project.project_workspace_id}/periods",
            actor="manager",
            payload={
                **engineering.REASON,
                "period_code": "O2A-CONSUMER-CONTROL",
                "period_start": today.isoformat(),
                "period_end": end.isoformat(),
                "cutoff_at": f"{end.isoformat()}T17:00:00-05:00",
                "timezone": "America/Bogota",
                "schedule_data_date": prior["schedule_data_date"],
            },
        ),
        201,
    )


def _authority_snapshot(f):
    """Persisted O1 data, not only flags on the Engineering response."""
    sources = (
        ScopeItem,
        PlanItem,
        ScopeBaseline,
        ScheduleRegister,
        ScheduleVersion,
        ScheduleBaseline,
        BudgetVersion,
        CostBaseline,
        CostActualEntry,
        ProgressMeasurement,
        ForecastVersion,
    )
    tenant, workspace = f.tenant_id, f.project_workspace_id
    try:
        return {
            table.name: [
                dict(row)
                for row in f.db.execute(
                    select(table)
                    .where(table.c.tenant_id == tenant, table.c.project_workspace_id == workspace)
                    .order_by(table.c.id)
                ).mappings()
            ]
            for table in (source.__table__ for source in sources)
        }
    finally:
        f.db.rollback()


def _map_scope(f, revision):
    path = f"/revisions/{revision['id']}/mappings"
    before = success(engineering.request(f, "GET", path))
    return success(
        engineering.request(
            f,
            "POST",
            path,
            version=before["version"],
            payload={**engineering.REASON, "target_kind": "SCOPE", "target_id": f.scope_items[0]["id"]},
        ),
        201,
    )


def _assert_denied(response, status, code):
    assert response.status_code == status, response.text
    assert response.json()["detail"]["code"] == code, response.text


def test_engineering_release_is_only_explicit_milestone_evidence(project, current_period):
    f = project
    upstream_before = _authority_snapshot(f)
    _, revision = engineering.draft(f)
    revision = engineering.release(f, engineering.approve(f, revision))
    release = revision["release"]
    assert revision["ifc_release_status"] == "CURRENT_IFC"
    facts = success(engineering.request(f, "GET", "/source-facts"))["progress"]
    exported = next(row for row in facts["items"] if row["revision_id"] == revision["id"])
    assert facts["evidence_only"] is True and exported["milestone"] == "IFC_RELEASED"
    assert exported["source_hash"] == release["release_hash"]
    assert _authority_snapshot(f) == upstream_before

    date = engineering.TODAY.isoformat()
    common = {
        "period_id": current_period["id"],
        "measurement_date": date,
        "as_of": date,
        "evidence_refs": [
            {"kind": "DOCUMENT", "reference": exported["source_reference"], "content_hash": release["release_hash"]}
        ],
    }
    published = rule(f, "MILESTONE_BASED", ("100",))
    payload = measurement_body(
        f,
        progress_type="MILESTONE",
        method="MILESTONE_BASED",
        rule_id=published["id"],
        completed_steps=["0"],
        numerator="0",
        unit="%",
        **common,
    )
    _assert_denied(
        progress_request(f, "POST", "/measurements", payload=payload),
        409,
        "ENGINEERING_SOURCE_SUBJECT_MAPPING_REQUIRED",
    )
    mapping = _map_scope(f, revision)
    for kind in ("PHYSICAL", "QUANTITY"):
        _assert_denied(
            progress_request(f, "POST", "/measurements", payload=measurement_body(f, progress_type=kind, **common)),
            422,
            "PROGRESS_ENGINEERING_RELEASE_NOT_PHYSICAL_QUANTITY_EVIDENCE",
        )
    assert _authority_snapshot(f) == upstream_before
    row = success(progress_request(f, "POST", "/measurements", payload=payload), 201)
    assert row["status"] == "DRAFT"
    evidence = row["source_snapshot"]["engineering_release_evidence"]
    assert len(evidence) == 1
    assert evidence[0]["revision_id"] == revision["id"] and evidence[0]["release_id"] == release["id"]
    assert evidence[0]["release_hash"] == release["release_hash"] and evidence[0]["effective_date"] == date
    assert evidence[0]["mappings"] == [{"mapping_id": mapping["id"], "mapping_hash": mapping["content_hash"]}]
    accepted = approve_progress(f, row)
    assert accepted["status"] == "APPROVED"
    assert accepted["source_snapshot"]["engineering_release_evidence"] == evidence


def test_engineering_issue_date_is_explicit_forecast_input_and_approval_stays_frozen(project, current_period):
    f = project
    today = engineering.TODAY
    issue = (today + timedelta(days=5)).isoformat()
    upstream_before = _authority_snapshot(f)
    deliverable = success(engineering.request(f, "POST", "/deliverables", payload=engineering.deliverable_body()), 201)
    revision = success(
        engineering.request(
            f,
            "POST",
            f"/deliverables/{deliverable['id']}/revisions",
            payload=engineering.revision_body(forecast_issue_date=issue),
        ),
        201,
    )
    mapping = _map_scope(f, revision)
    revision = engineering.approve(f, engineering.link(f, revision, successor=True))
    facts = success(engineering.request(f, "GET", "/source-facts"))["forecast"]
    exported = next(row for row in facts["items"] if row["revision_id"] == revision["id"])
    assert facts["candidate_only"] is True and exported["forecast_issue_date"] == issue
    assert exported["revision_content_hash"] == revision["content_hash"]
    assert _authority_snapshot(f) == upstream_before

    amount = forecast.assumption(f, "REMAINING-COST", "75", "USD", effective_date=today.isoformat())
    finish = forecast.assumption(
        f,
        "ENGINEERING-FINISH",
        issue,
        "date",
        kind="FORECAST_DATE",
        currency=None,
        source_reference=exported["source_reference"],
        effective_date=today.isoformat(),
    )
    payload = forecast.body(
        f,
        period_id=current_period["id"],
        as_of=today.isoformat(),
        assumptions=[amount, finish],
        cost_items=[
            forecast.component(
                f,
                "REMAINING-WORK",
                inputs={
                    "amount_assumption_code": "REMAINING-COST",
                    "cost_bucket": "UNCOMMITTED",
                    "phasing": [{"date": issue, "amount": "75", "currency": "USD"}],
                },
            )
        ],
        time_items=[
            forecast.component(
                f,
                "PROJECT-FINISH",
                activity_external_id=f.schedule_version["snapshot_json"]["activities"][0]["external_id"],
                assumption_codes=["ENGINEERING-FINISH"],
                inputs={"date_assumption_code": "ENGINEERING-FINISH"},
            )
        ],
    )
    _assert_denied(
        forecast.request(
            f,
            "POST",
            "/versions",
            payload={**payload, "assumptions": [amount, {**finish, "value": today.isoformat()}]},
        ),
        422,
        "FORECAST_ENGINEERING_DATE_MISMATCH",
    )
    candidate = success(forecast.request(f, "POST", "/versions", payload=payload), 201)
    assert candidate["status"] == "DRAFT" and not candidate["result_json"]
    approved = forecast.approved(f, candidate)
    assert approved["status"] == "APPROVED"
    time = approved["result_json"]["time"]["items"][0]
    assert time["source"] == "GOVERNED_ENGINEERING_ISSUE_ASSUMPTION"
    assert time["forecast_finish"] == issue and time["cpm_calculated"] is False
    fact = time["engineering_source"]
    assert fact["revision_id"] == revision["id"] and fact["content_hash"] == revision["content_hash"]
    assert fact["mappings"] == [{"mapping_id": mapping["id"], "mapping_hash": mapping["content_hash"]}]
    assert approved["source_snapshot_json"]["engineering_issue_facts"]["TIME:PROJECT-FINISH"] == fact
    assert approved["source_hashes_json"]["engineering_issue_facts"]

    frozen = _authority_snapshot(f)
    changed = (today + timedelta(days=10)).isoformat()
    successor = success(
        engineering.request(
            f,
            "POST",
            f"/revisions/{revision['id']}/successor",
            version=revision["version"],
            payload=engineering.revision_body(revision_code="B", forecast_issue_date=changed),
        ),
        201,
    )
    assert successor["forecast_issue_date"] == changed
    _assert_denied(
        forecast.request(f, "POST", "/versions", payload={**payload, "code": f"FC-{uuid4().hex[:10]}"}),
        409,
        "ENGINEERING_FORECAST_REVISION_SUPERSEDED",
    )
    assert _authority_snapshot(f) == frozen
    assert success(forecast.request(f, "GET", f"/versions/{approved['id']}")) == approved
