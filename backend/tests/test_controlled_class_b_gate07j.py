"""Class B governed lifecycle negatives, separate from the selected UAT journey."""

from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from tests.helpers.strategic_fresh_class_b import CONTROLLED_REFERENCES
from tests.test_investment_evidence_policy_gate07j_evid import _policy
from tests.test_investment_gate_preparation_gate07j import _preparation, _profile, _reviewer, _source

from app.core.time import utc_now
from app.main import app
from app.modules.investment_evidence_policy.service import InvestmentEvidencePolicyService
from app.modules.investment_gate_preparation.schemas import EvidenceValidationIn, ManualEvidenceIn
from app.modules.investment_gate_preparation.service import InvestmentGatePreparationService


@pytest.fixture(scope="module", autouse=True)
def _started_application():
    with TestClient(app):
        yield


def _controlled_case():
    db, tenant, author, portfolio, projects, _ = _source()
    policy = InvestmentEvidencePolicyService(db, tenant, author)
    record = _policy(policy)
    policy.publish_configuration(record.id, record.version)
    profile = _profile(db, tenant, author, funding=True)
    preparer = InvestmentGatePreparationService(db, tenant, author)
    preparation = _preparation(preparer, portfolio.id, profile.id)
    reviewer = _reviewer(db, tenant)
    return (
        db,
        tenant,
        author,
        projects,
        preparer,
        InvestmentGatePreparationService(db, tenant, reviewer.id),
        preparation,
    )


def _payload(preparation, specification, project_id, *, expired=False):
    requirement_key, _, days, _ = specification
    as_of = utc_now() - timedelta(days=days + 1) if expired else utc_now()
    return ManualEvidenceIn(
        requirement_key=requirement_key,
        scope_type="EACH_PROJECT",
        scope_id=project_id,
        reference_id=f"UAT-CONTROLLED-{requirement_key}-{uuid4().hex[:8]}",
        evidence_date=as_of,
        valid_until=as_of + timedelta(days=days),
        issuer="UAT representative evidence author",
        owner="UAT governance",
        summary="UAT CONTROLLED EVIDENCE, representative only, not a real-world approval.",
        evidence_refs=[{"classification_label": "UAT CONTROLLED EVIDENCE", "revision": "1", "evidence_hash": "a" * 64}],
        scope_reference_hash=preparation.recommended_project_set_hash,
        idempotency_key=f"class-b-submit-{uuid4()}",
    )


@pytest.mark.parametrize("specification", CONTROLLED_REFERENCES, ids=lambda spec: spec[0])
def test_controlled_class_b_requires_independent_validator(specification):
    db, _, author, projects, preparer, validator, preparation = _controlled_case()
    try:
        preparation = preparer.add_evidence(
            preparation.id, preparation.revision_version, _payload(preparation, specification, projects[0].id)
        )
        item = next(
            value
            for value in preparation.evidence
            if value.requirement_key == specification[0] and value.scope_id == projects[0].id
        )
        assert item.classification == "B" and item.provider_key is None and item.status == "SUBMITTED"
        with pytest.raises(HTTPException) as denied:
            preparer.validate_evidence(
                item.id,
                preparation.revision_version,
                EvidenceValidationIn(
                    decision="VALID",
                    validation_note="Self validation must be denied for Class B.",
                    idempotency_key=f"class-b-self-{uuid4()}",
                ),
            )
        assert denied.value.detail["code"] == "EVIDENCE_VALIDATION_SOD_VIOLATION"
        db.rollback()
        preparation = validator.validate_evidence(
            item.id,
            preparation.revision_version,
            EvidenceValidationIn(
                decision="VALID",
                validation_note="Independent scope and representative document review.",
                idempotency_key=f"class-b-independent-{uuid4()}",
            ),
        )
        validated = next(value for value in preparation.evidence if value.id == item.id)
        assert validated.status == "VALID" and validated.submitted_by == author
        assert validated.validated_by == validator.actor_id != author
    finally:
        db.close()


@pytest.mark.parametrize("specification", CONTROLLED_REFERENCES, ids=lambda spec: spec[0])
def test_expired_controlled_class_b_cannot_validate_or_supply_coverage(specification):
    db, _, _, projects, preparer, validator, preparation = _controlled_case()
    try:
        preparation = preparer.add_evidence(
            preparation.id,
            preparation.revision_version,
            _payload(preparation, specification, projects[0].id, expired=True),
        )
        item = next(
            value
            for value in preparation.evidence
            if value.requirement_key == specification[0] and value.scope_id == projects[0].id
        )
        preparation = validator.validate_evidence(
            item.id,
            preparation.revision_version,
            EvidenceValidationIn(
                decision="VALID",
                validation_note="Expiry must remain a blocking negative outcome.",
                idempotency_key=f"class-b-expiry-{uuid4()}",
            ),
        )
        item = next(value for value in preparation.evidence if value.id == item.id)
        assert item.status == "EXPIRED" and "EVIDENCE_EXPIRED" in item.blockers
        assert "EVIDENCE_EXPIRED" in preparation.readiness.blockers
        assert validator.project_readiness(preparation.id).coverage_percent == 0
    finally:
        db.close()


def test_controlled_class_b_wrong_project_and_cross_tenant_are_rejected():
    db, tenant, author, projects, preparer, _, preparation = _controlled_case()
    try:
        payload = _payload(preparation, CONTROLLED_REFERENCES[0], projects[0].id)
        payload.scope_id = max(item.id for item in projects) + 100000
        with pytest.raises(HTTPException) as wrong_project:
            preparer.add_evidence(preparation.id, preparation.revision_version, payload)
        assert wrong_project.value.detail["code"] == "EVIDENCE_SCOPE_MISMATCH"
        db.rollback()
        with pytest.raises(HTTPException) as wrong_tenant:
            InvestmentGatePreparationService(db, tenant + 100000, author).preparation(preparation.id)
        assert wrong_tenant.value.status_code == 404
    finally:
        db.close()
