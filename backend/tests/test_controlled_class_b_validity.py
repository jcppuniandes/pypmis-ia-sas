"""Reject future dates or validity beyond the captured published Class B rule."""

from datetime import timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from tests.helpers.strategic_fresh_class_b import CONTROLLED_REFERENCES
from tests.test_controlled_class_b_gate07j import _controlled_case, _payload

from app.core.time import utc_now
from app.main import app
from app.modules.investment_gate_preparation.schemas import ManualEvidenceUpdateIn
from app.modules.investment_gate_preparation.service import InvestmentGatePreparationService


@pytest.fixture(scope="module", autouse=True)
def _started_application():
    with TestClient(app):
        yield


@pytest.mark.parametrize("operation", ["add", "update"])
@pytest.mark.parametrize("invalid_kind", ["future_date", "overlong_validity"])
def test_class_b_submission_cannot_bypass_policy_validity(operation, invalid_kind):
    db, _, _, projects, preparer, _, preparation = _controlled_case()
    try:
        payload = _payload(preparation, CONTROLLED_REFERENCES[0], projects[0].id)
        if operation == "update":
            preparation = preparer.add_evidence(preparation.id, preparation.revision_version, payload)
        before = preparer.preparation(preparation.id)
        if invalid_kind == "future_date":
            payload.evidence_date = utc_now() + timedelta(days=1)
            payload.valid_until = payload.evidence_date + timedelta(days=180)
            expected_code = "EVIDENCE_DATE_IN_FUTURE"
        else:
            payload.valid_until = payload.evidence_date + timedelta(days=181)
            expected_code = "EVIDENCE_VALIDITY_EXCEEDS_POLICY"
        with pytest.raises(HTTPException) as rejected:
            if operation == "add":
                preparer.add_evidence(preparation.id, preparation.revision_version, payload)
            else:
                item = next(
                    value
                    for value in preparation.evidence
                    if value.requirement_key == payload.requirement_key and value.scope_id == payload.scope_id
                )
                preparer.update_evidence(
                    item.id,
                    preparation.revision_version,
                    ManualEvidenceUpdateIn(
                        evidence_date=payload.evidence_date,
                        valid_until=payload.valid_until,
                    ),
                )
        assert rejected.value.status_code == 422 and rejected.value.detail["code"] == expected_code
        db.rollback()
        after = preparer.preparation(preparation.id)
        assert after.revision_version == before.revision_version
        assert [
            (item.id, item.evidence_date, item.valid_until, item.status, item.source_hash) for item in after.evidence
        ] == [
            (item.id, item.evidence_date, item.valid_until, item.status, item.source_hash) for item in before.evidence
        ]
    finally:
        db.close()


@pytest.mark.parametrize("specification", CONTROLLED_REFERENCES, ids=lambda spec: spec[0])
def test_exact_captured_validity_window_is_accepted_but_not_extended(specification):
    as_of = utc_now()
    requirement = {"classification": "B", "validity_period_days": specification[2]}
    limit = as_of + timedelta(days=specification[2])
    assert InvestmentGatePreparationService._manual_validity_issue(as_of, limit, requirement) is None
    assert (
        InvestmentGatePreparationService._manual_validity_issue(as_of, limit + timedelta(seconds=1), requirement)
        == "EVIDENCE_VALIDITY_EXCEEDS_POLICY"
    )
