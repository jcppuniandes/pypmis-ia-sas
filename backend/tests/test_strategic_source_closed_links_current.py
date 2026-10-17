"""Pure resolver contracts, not seeded final-state business UAT evidence.

The fresh PostgreSQL E2E owns the actual lifecycles. These small record doubles
exercise every reverse-link rejection independently, without writing any domain
state or constructing an Investment Decision/Business Case through the ORM.
"""

from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.modules.business_case.source_links import current_bundle_matches_completed_case_link


class _ReadOnlyResult:
    def __init__(self, record):
        self.record = record

    def first(self):
        return self.record


class _ReadOnlySession:
    def __init__(self, record):
        self.record = record
        self.statements = []

    def execute(self, statement):
        self.statements.append(str(statement))
        return _ReadOnlyResult(self.record)


def _contract(source_key):
    case = SimpleNamespace(id=10, tenant_id=2, project_workspace_id=30, current_revision_id=12)
    revision = SimpleNamespace(
        id=12,
        tenant_id=2,
        business_case_id=10,
        status="COMPLETED",
        readiness_status="READY",
        content_hash="new-reviewed-bc-hash",
        source_references_json={
            source_key: {
                "id": 40,
                "version_id": 41,
                "version": 3,
                "status": "COMPLETED",
                "readiness": "READY",
                "source_current": True,
            }
        },
        source_hashes_json={source_key: "approved-source-hash"},
    )
    db = _ReadOnlySession((case, revision))
    kwargs = {
        "tenant_id": 2,
        "project_id": 30,
        "source_key": source_key,
        "aggregate_id": 40,
        "version_id": 41,
        "version_number": 3,
        "source_hash": "approved-source-hash",
        "source_status": "COMPLETED",
        "captured_references": {"business_case": {"id": 10, "revision_id": 11}},
        "captured_hashes": {"business_case": "old-reviewed-bc-hash", "fel": "fel-a", "risk": "risk-a"},
        "current_hashes": {"business_case": "new-reviewed-bc-hash", "fel": "fel-a", "risk": "risk-a"},
    }
    return db, case, revision, kwargs


@pytest.mark.parametrize("source_key", ["benefits", "commercial_strategy"])
def test_completed_exact_reverse_link_is_current_and_read_only(source_key):
    db, case, revision, kwargs = _contract(source_key)
    before = deepcopy((vars(case), vars(revision), kwargs))
    assert current_bundle_matches_completed_case_link(db, **kwargs) is True
    assert (vars(case), vars(revision), kwargs) == before
    assert len(db.statements) == 1
    assert "business_cases.tenant_id" in db.statements[0]
    assert "business_cases.project_workspace_id" in db.statements[0]
    assert "business_case_revisions.business_case_id" in db.statements[0]


@pytest.mark.parametrize("source_key", ["benefits", "commercial_strategy"])
@pytest.mark.parametrize(
    ("target", "field", "value"),
    [
        ("case", "tenant_id", 99),
        ("case", "project_workspace_id", 99),
        ("case", "id", 99),
        ("case", "current_revision_id", 99),
        ("revision", "tenant_id", 99),
        ("revision", "business_case_id", 99),
        ("revision", "status", "DRAFT"),
        ("revision", "status", "IN_REVIEW"),
        ("revision", "readiness_status", "BLOCKED"),
        ("revision", "content_hash", "unrelated-bc-hash"),
        ("reference", "id", 99),
        ("reference", "id", "40"),
        ("reference", "version_id", 99),
        ("reference", "version_id", "41"),
        ("reference", "version", 99),
        ("reference", "version", "3"),
        ("reference", "status", "DRAFT"),
        ("reference", "readiness", "STALE"),
        ("reference", "source_current", False),
        ("reference", "source_current", "true"),
        ("reference", "source_current", 1),
        ("hash", "source_hash", "different-source-hash"),
    ],
)
def test_mismatched_or_unreviewed_reverse_link_stays_stale(source_key, target, field, value):
    db, case, revision, kwargs = _contract(source_key)
    if target == "case":
        setattr(case, field, value)
    elif target == "revision":
        setattr(revision, field, value)
    elif target == "reference":
        revision.source_references_json[source_key][field] = value
    else:
        revision.source_hashes_json[source_key] = value
    assert current_bundle_matches_completed_case_link(db, **kwargs) is False


@pytest.mark.parametrize("source_key", ["benefits", "commercial_strategy"])
@pytest.mark.parametrize(
    "change", ["changed", "added", "removed", "source_draft", "no_captured_bc", "wrong_captured_bc_type", "no_live_bc"]
)
def test_any_other_source_change_or_unbound_case_stays_stale(source_key, change):
    db, _case, _revision, kwargs = _contract(source_key)
    if change == "changed":
        kwargs["current_hashes"]["fel"] = "different-fel"
    elif change == "added":
        kwargs["current_hashes"]["permit"] = "new-permit"
    elif change == "removed":
        kwargs["current_hashes"].pop("risk")
    elif change == "source_draft":
        kwargs["source_status"] = "DRAFT"
    elif change == "no_captured_bc":
        kwargs["captured_references"] = {}
    elif change == "wrong_captured_bc_type":
        kwargs["captured_references"]["business_case"]["id"] = "10"
    else:
        db.record = None
    assert current_bundle_matches_completed_case_link(db, **kwargs) is False


@pytest.mark.parametrize("source_key", ["benefits", "commercial_strategy"])
def test_unchanged_source_bundle_keeps_existing_semantics_without_query(source_key):
    db, _case, _revision, kwargs = _contract(source_key)
    kwargs["current_hashes"] = dict(kwargs["captured_hashes"])
    kwargs["source_status"] = "DRAFT"
    assert current_bundle_matches_completed_case_link(db, **kwargs) is True
    assert db.statements == []
