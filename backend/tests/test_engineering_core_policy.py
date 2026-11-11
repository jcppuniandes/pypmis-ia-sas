"""Focused rules independent of business fixture and deployment."""

from copy import deepcopy
from datetime import date, datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.modules.engineering_foundation.policy import (
    DEFAULT_PROFILE,
    REVIEW_ACTIONS,
    EngineeringProfile,
    normalized_code,
    release_status,
    revision_code,
    validity_end,
)
from app.modules.engineering_foundation.schemas import DeliverableIn, RevisionIn


def test_default_profile_is_strict_and_stable():
    assert EngineeringProfile.model_validate(DEFAULT_PROFILE).model_dump(mode="json") == DEFAULT_PROFILE


@pytest.mark.parametrize(
    "updates",
    [
        {"scope": {"type": "tenant", "workspace_id": 12}},
        {"scope": {"type": "workspace", "workspace_id": None}},
        {"disciplines": ["MECHANICAL", "MECHANICAL"]},
        {"deliverable_types": ["free text"]},
        {"purposes_of_issue": ["FOR_INFORMATION"]},
        {"ifc_release_rules": {"eligible_purposes": ["FOR_CONSTRUCTION"] * 2, "releaser_distinct_from_approver": True}},
        {"readiness_evidence_rules": {"max_age_days": 0}},
        {"readiness_evidence_rules": {"max_age_days": "28"}},
        {"lookahead_days": 121},
        {"status_labels": {"USER_OVERRIDES_APPROVAL": "Misleading"}},
        {"allow_auto_release_on_upload": True},
    ],
)
def test_profile_rejects_invalid_policy(updates):
    payload = deepcopy(DEFAULT_PROFILE)
    payload.update(updates)
    with pytest.raises(ValidationError):
        EngineeringProfile.model_validate(payload)


@pytest.mark.parametrize(
    ("raw", "rule", "expected"),
    [("a.01", "ALPHANUMERIC", "A.01"), ("001", "NUMERIC", "001"), ("b", "ALPHABETIC", "B")],
)
def test_revision_code_is_profile_controlled(raw, rule, expected):
    assert revision_code(raw, rule) == expected


@pytest.mark.parametrize(
    ("raw", "rule"),
    [("a1", "NUMERIC"), ("1a", "ALPHABETIC"), ("space not allowed", "ALPHANUMERIC"), ("..", "ALPHANUMERIC")],
)
def test_bad_revision_code_is_rejected(raw, rule):
    with pytest.raises(ValueError):
        revision_code(raw, rule)


def test_deliverable_and_revision_cannot_claim_approval_or_ifc_in_input():
    deliverable = {
        "reason": "Controlled fixture",
        "code": "DEL-01",
        "title": "Cross section",
        "discipline": "CIVIL",
        "deliverable_type": "DRAWING",
        "responsible_party": "Design Team",
    }
    revision = {"reason": "Controlled fixture", "revision_code": "A", "purpose_of_issue": "FOR_CONSTRUCTION"}
    assert DeliverableIn.model_validate(deliverable).code == "DEL-01"
    assert RevisionIn.model_validate(revision).purpose_of_issue == "FOR_CONSTRUCTION"
    with pytest.raises(ValidationError):
        DeliverableIn.model_validate({**deliverable, "status": "IFC_RELEASED"})
    with pytest.raises(ValidationError):
        RevisionIn.model_validate({**revision, "approved_by": 100, "document_hash": "x" * 64})
    with pytest.raises(ValueError):
        normalized_code("arbitrary / scope")


def test_ifc_release_states_respect_business_and_knowledge_cutoffs():
    a = SimpleNamespace(revision_id=3, effective_date=date(2026, 11, 9), released_at=datetime(2026, 11, 9, 10))
    b = SimpleNamespace(revision_id=4, effective_date=date(2026, 11, 12), released_at=datetime(2026, 11, 10, 11))
    assert release_status(3, a, a, date(2026, 11, 9)) == "CURRENT_IFC"
    assert release_status(4, b, a, date(2026, 11, 10)) == "FUTURE_IFC"
    assert release_status(4, b, a, date(2026, 11, 13), known_at=datetime(2026, 11, 10, 10)) == "NOT_RELEASED"
    assert release_status(3, a, b, date(2026, 11, 13)) == "SUPERSEDED_IFC"
    assert validity_end(date(2026, 11, 9), 28) == "2026-12-07"
    assert validity_end(date(2026, 11, 9), None) is None


def test_review_check_approve_are_distinct_permissions():
    assert REVIEW_ACTIONS["accept"] == "review.perform"
    assert REVIEW_ACTIONS["check"] == "review.check"
    assert REVIEW_ACTIONS["approve"] == "review.approve"
    assert REVIEW_ACTIONS["close"] == "review.close"
