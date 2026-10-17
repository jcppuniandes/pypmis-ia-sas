"""Historical Gate package protection against a controlled-reference successor."""

from copy import deepcopy
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from tests.test_investment_gate_preparation_gate07j import (
    _add_fel,
    _preparation,
    _profile,
    _reviewer,
    _source,
    _validate_latest_fel,
)

from app.main import app
from app.modules.investment_gate_preparation.schemas import EvidenceValidationIn, ManualEvidenceUpdateIn
from app.modules.investment_gate_preparation.service import InvestmentGatePreparationService


@pytest.fixture(scope="module", autouse=True)
def _started_application():
    with TestClient(app):
        yield


def test_controlled_successor_does_not_mutate_frozen_historical_package():
    """Exercise the shared freeze/reference model on its legacy minimal fixture.

    This is deliberately separate from the selected modern UAT chain: it does
    not weaken that chain's published nineteen-requirement policy or mutate its
    happy-path sources merely to produce a negative test.
    """
    db, tenant, actor, portfolio, projects, _ = _source()
    try:
        profile = _profile(db, tenant, actor)
        author = InvestmentGatePreparationService(db, tenant, actor)
        reviewer = InvestmentGatePreparationService(db, tenant, _reviewer(db, tenant).id)
        original = _preparation(author, portfolio.id, profile.id)
        for project in projects:
            original = _add_fel(author, original, project.id)
            original = _validate_latest_fel(reviewer, original, project.id)
        original = author.ready_for_review(original.id, original.revision_version, f"successor-ready-{uuid4()}")
        original = reviewer.freeze(original.id, original.revision_version, f"successor-freeze-{uuid4()}")
        captured = deepcopy(original.model_dump(mode="json"))

        successor = author.clone(original.id, original.revision_version, f"successor-clone-{uuid4()}")
        target = next(item for item in successor.evidence if item.requirement_key == "fel-stage-readiness")
        successor = author.update_evidence(
            target.id,
            successor.revision_version,
            ManualEvidenceUpdateIn(
                summary="UAT controlled reference successor revision 2; original freeze must remain immutable.",
                evidence_refs=[{**target.evidence_refs[0], "document_revision": "2"}],
            ),
        )
        successor = reviewer.validate_evidence(
            target.id,
            successor.revision_version,
            EvidenceValidationIn(
                decision="VALID",
                validation_note="Independent review of the separate controlled successor.",
                idempotency_key=f"successor-review-{uuid4()}",
            ),
        )
        changed = next(item for item in successor.evidence if item.id == target.id)
        assert changed.status == "VALID" and changed.source_hash != target.source_hash
        assert successor.id != original.id and successor.revision == original.revision + 1
        unchanged = reviewer.preparation(original.id).model_dump(mode="json")
        assert unchanged == captured
        assert unchanged["status"] == "FROZEN" and unchanged["preparation_hash"] == captured["preparation_hash"]
    finally:
        db.close()
