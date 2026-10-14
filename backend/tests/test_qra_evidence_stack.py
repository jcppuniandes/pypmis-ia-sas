"""Actual QRA -> evidence policy -> Five Case -> frozen FFA -> independent FID.

No mocked provider payloads, Monte Carlo inside Gate, or operational DB writes.
"""

import json
import os
from pathlib import Path
from time import perf_counter
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from tests.qra_evidence_fixture import draft_qra_policy, evidence_fixture, historical_hashes, reuse_evidence_fixture
from tests.test_gate07m_fid_e2e import TOTAL_INVESTMENT, _manual_blocking_class_b
from tests.test_investment_decision_gate07k import _decision_ready, _maker
from tests.test_investment_gate_preparation_gate07j import _preparation
from tests.test_qra_engine import _run_completed
from tests.test_qra_foundation import _key

from app.database.session import SessionLocal
from app.domain.models import ControlAccount
from app.main import app
from app.modules.business_case.service import BusinessCaseService
from app.modules.investment_decision.schemas import DecisionDecideIn
from app.modules.investment_decision.service import InvestmentDecisionService
from app.modules.investment_gate_preparation.schemas import ManualEvidenceIn
from app.modules.qra_engine.models import QraRun
from app.modules.qra_engine.schemas import RunActionIn


@pytest.fixture(scope="module")
def governed():
    bind = SessionLocal.kw.get("bind")
    if (
        not os.getenv("PYPMIS_TEST_DATABASE_URL", "").strip()
        or bind is None
        or bind.dialect.name != "postgresql"
        or bind.url.database != "qra_evidence"
    ):
        pytest.skip(
            "Dedicated QRA evidence full stack requires the explicit disposable PostgreSQL qra_evidence database"
        )
    with TestClient(app), SessionLocal() as db:
        reused_project = os.getenv("PYPMIS_QRA_EVIDENCE_REUSE_PROJECT_ID")
        yield reuse_evidence_fixture(db, int(reused_project)) if reused_project else evidence_fixture(db)


def test_actual_cost_schedule_policy_bc_gate_and_fid_path(governed):
    f = governed
    db, author, reviewer = f["db"], f["author"], f["reviewer"]
    before = historical_hashes(db)
    source_policy_hash = f["baseline_policy"].content_hash
    source_policy_json = f["baseline_policy"].content_json
    run_count = len(db.scalars(select(QraRun)).all())
    draft = draft_qra_policy(f)
    writes = []

    def collect(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith(("INSERT ", "UPDATE ", "DELETE ")):
            writes.append(statement)

    started = perf_counter()
    event.listen(db.get_bind(), "before_cursor_execute", collect)
    try:
        preview = f["policy_service"].preview(
            portfolio_id=f["portfolio"].id,
            gate_profile_code="PYP-FFA",
            project_ids=[f["project"].id],
            configuration_id=draft.id,
            content_override=draft.content_json,
        )
    finally:
        event.remove(db.get_bind(), "before_cursor_execute", collect)
    assert preview.persisted is False and writes == []
    qra = [
        row for row in preview.effective_matrix if row["evidence_type"] in {"COST_QRA_RESULT", "SCHEDULE_QRA_RESULT"}
    ]
    assert len(qra) == 2
    assert all(row["classification"] == "A" for row in qra)
    qra_status = [
        row
        for row in preview.current_evidence_status
        if row["evidence_type"] in {"COST_QRA_RESULT", "SCHEDULE_QRA_RESULT"}
    ]
    if not (len(qra_status) == 2 and all("source_current" in row for row in qra_status)):
        diagnostic_output = os.getenv("QRA_EVIDENCE_STACK_ARTIFACT")
        if diagnostic_output:
            Path(diagnostic_output).with_suffix(".preview.json").write_text(
                json.dumps(
                    {
                        "qra_status": qra_status,
                        "direct_current_provider": {
                            analysis: f["engine"].provider_evidence(
                                f["project"].id, analysis, scope_requirement="WHOLE_PROJECT"
                            )
                            for analysis in ("COST_QRA", "SCHEDULE_QRA")
                        },
                    },
                    indent=2,
                    default=str,
                ),
                encoding="utf-8",
            )
    assert len(qra_status) == 2 and all("source_current" in row for row in qra_status), qra_status
    assert all(row["source_current"] is True for row in qra_status), qra_status
    preview_ms = round((perf_counter() - started) * 1000, 3)
    published = f["policy_service"].publish_configuration(draft.id, draft.version)
    assert published.content_hash != source_policy_hash
    assert f["baseline_policy"].content_hash == source_policy_hash
    assert f["baseline_policy"].content_json == source_policy_json
    assert historical_hashes(db) == before

    business = BusinessCaseService(db, author.tenant_id, author.id)
    case = business.get(f["business_case"].id)
    revision = business.create_revision(case.id, "REVALIDATION", _key("qra-bc-new-revision"))
    refs = revision.source_references_json
    assert refs["cost_qra_result"]["source_current"] is True
    assert refs["schedule_qra_result"]["source_current"] is True
    assert revision.source_hashes_json["cost_qra_result"]
    assert revision.source_hashes_json["schedule_qra_result"]
    old_hashes = before["business_case_revisions"]
    assert all(historical_hashes(db)["business_case_revisions"][key] == value for key, value in old_hashes.items())
    revision = business.submit_review(revision.id, revision.revision_version, _key("qra-bc-submit"))
    revision = business.complete_revision(revision.id, revision.revision_version, _key("qra-bc-complete"), reviewer.id)
    assert revision.status == "COMPLETED"

    preparation = _preparation(f["gate"], f["portfolio"].id, f["profile"].id)
    preparation = _manual_blocking_class_b(f["gate"], f["validator"], preparation)
    rows = [row for row in preparation.evidence if row.evidence_type in {"COST_QRA_RESULT", "SCHEDULE_QRA_RESULT"}]
    assert len(rows) == 2
    assert all(row.status == "VALID" and row.source_current for row in rows), rows
    readiness = f["gate"].readiness(preparation.id)
    assert readiness.readiness_status == "READY", readiness.blockers
    preparation = f["gate"].ready_for_review(preparation.id, preparation.revision_version, _key("qra-gate-ready"))
    preparation = f["validator"].freeze(preparation.id, preparation.revision_version, _key("qra-gate-freeze"))
    assert preparation.status == "FROZEN"
    assert preparation.source_snapshot["evidence_policy"]["policy_id"] == published.id
    frozen = json.dumps(preparation.source_snapshot, sort_keys=True, default=str)
    assert "histogram" not in frozen and '"cdf"' not in frozen and '"sensitivity"' not in frozen
    assert f["validator"].handoff(preparation.id).can_enter_investment_decision is True
    assert f["validator"].handoff(preparation.id).can_enter_fid is False
    maker = _maker(db, author.tenant_id, "Contextual QRA independent FID authority")
    decision = _decision_ready(db, author.tenant_id, author.id, reviewer.id, preparation, maker.id)
    assert decision.status == "READY_FOR_DECISION" and not decision.is_fid
    decided = InvestmentDecisionService(db, author.tenant_id, maker.id).decide(
        decision.id,
        decision.revision_version,
        DecisionDecideIn(
            outcome="GO",
            rationale="Independent formal FID based on frozen governed evidence, not QRA auto-approval.",
            authorized_amount=TOTAL_INVESTMENT,
            authorized_currency="USD",
            idempotency_key=_key("qra-fid-decide"),
        ),
    )
    assert decided.is_fid is True
    assert len(db.scalars(select(QraRun)).all()) == run_count, "Gate/BC/FID must never create or execute QRA"
    f.update(published_policy=published, qra_preparation=preparation, qra_decision=decided)
    output = os.getenv("QRA_EVIDENCE_STACK_ARTIFACT", "")
    if output:
        Path(output).write_text(
            json.dumps(
                {
                    "database_dialect": db.get_bind().dialect.name,
                    "fixture_setup": f.get("fixture_setup", "FRESH_REAL_SOURCE_AND_KERNEL_STACK"),
                    "project_workspace_id": f["project"].id,
                    "policy_id": published.id,
                    "policy_revision": published.revision,
                    "policy_hash": published.content_hash,
                    "run_ids": {kind: run["id"] for kind, run in f["runs"].items()},
                    "preview_ms": preview_ms,
                    "preview_persisted": False,
                    "preview_dml_count": len(writes),
                    "bc_revision_id": revision.id,
                    "gate_preparation_id": preparation.id,
                    "gate_preparation_hash": preparation.preparation_hash,
                    "decision_id": decided.id,
                    "decision_hash": decided.decision_hash,
                    "is_fid": decided.is_fid,
                    "historical_baseline": before,
                    "run_count_before_after": [run_count, len(db.scalars(select(QraRun)).all())],
                },
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )


def test_actual_accepted_successor_preserves_frozen_gate_and_completed_bc(governed):
    f = governed
    if "qra_preparation" not in f:
        pytest.skip("The full-stack happy path must complete before successor immutability assertions")
    before = historical_hashes(f["db"])
    run = _run_completed(f, "cost", seed=772)
    assert f["engine"].provider_evidence(f["project"].id, "COST_QRA")["run_id"] == f["runs"]["cost"]["id"]
    reviewed = f["review_engine"].review_action(
        run["id"], run["revision_version"], RunActionIn(), _key("successor-review"), "review"
    )
    accepted = f["review_engine"].review_action(
        run["id"], reviewed["revision_version"], RunActionIn(), _key("successor-accept"), "accept"
    )
    assert f["engine"].provider_evidence(f["project"].id, "COST_QRA")["run_id"] == accepted["id"]
    assert historical_hashes(f["db"]) == before
    historical = f["validator"].preparation(f["qra_preparation"].id)
    assert historical.preparation_hash == f["qra_preparation"].preparation_hash


def test_class_a_manual_qra_fallback_remains_forbidden(governed):
    f = governed
    if "published_policy" not in f:
        pytest.skip("The actual policy happy path must complete first")
    preparation = _preparation(f["gate"], f["portfolio"].id, f["profile"].id)
    row = next(item for item in preparation.evidence if item.evidence_type == "COST_QRA_RESULT")
    from app.core.time import utc_now

    with pytest.raises(HTTPException) as denied:
        f["gate"].add_evidence(
            preparation.id,
            preparation.revision_version,
            ManualEvidenceIn(
                requirement_key=row.requirement_key,
                scope_type="EACH_PROJECT",
                scope_id=f["project"].id,
                reference_id="MANUAL-QRA-FILE",
                evidence_date=utc_now(),
                issuer="Test issuer",
                owner="Test owner",
                summary="A document attachment must not substitute accepted QRA Class A",
                evidence_refs=[{"reference": "manual.pdf"}],
                idempotency_key=f"manual-qra-{uuid4()}",
            ),
        )
    assert denied.value.detail["code"] == "MANUAL_REFERENCE_NOT_ALLOWED"


def test_actual_material_cost_source_change_blocks_new_gate_without_rewriting_history(governed):
    f = governed
    if "qra_preparation" not in f:
        pytest.skip("The frozen real-stack package must exist first")
    before = historical_hashes(f["db"])
    # Intentional isolated source-authority mutation, never a Gate write-back.
    account = f["db"].scalar(select(ControlAccount).where(ControlAccount.project_id == f["operational_project"].id))
    account.budget += 25
    account.version += 1
    f["db"].commit()
    provider = f["engine"].provider_evidence(f["project"].id, "COST_QRA")
    assert provider["status"] != "AVAILABLE" and provider["source_current"] is False
    assert provider["blockers"]
    preparation = _preparation(f["gate"], f["portfolio"].id, f["profile"].id)
    row = next(item for item in preparation.evidence if item.evidence_type == "COST_QRA_RESULT")
    assert row.status != "VALID"
    assert f["gate"].readiness(preparation.id).readiness_status != "READY"
    assert historical_hashes(f["db"]) == before
