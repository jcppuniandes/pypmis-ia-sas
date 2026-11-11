"""Fast policy checks; real PostgreSQL/HTTP coverage is separately required."""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.modules.awp.policy import DEFAULT_PROFILE, assess_policy
from app.modules.awp.service import AWPService
from app.modules.basic_data.service import _hash
from app.modules.engineering_foundation import integration

OBSERVED = datetime(2026, 8, 17, 15, 30)
EFFECTIVE = OBSERVED.date()
SHA = "a" * 64


@pytest.mark.parametrize("identity", ["²", "١", "0", "-1"])
def test_engineering_clearance_rejects_malformed_identifiers_before_database_access(identity):
    service = object.__new__(AWPService)
    constraint = SimpleNamespace(constraint_type="ENGINEERING")
    with pytest.raises(HTTPException) as error:
        service._verify_engineering_clearance(31, constraint, None, f"engineering:{identity}:{SHA}")
    assert error.value.status_code == 422
    assert error.value.detail == {"code": "AWP_ENGINEERING_CLEARANCE_REFERENCE_INVALID"}


def link(identity, revision_id, *, version=2, action="SET", target_id=88, kind="EWP", observed=OBSERVED):
    row = SimpleNamespace(
        id=identity,
        tenant_id=6,
        project_workspace_id=31,
        revision_id=revision_id,
        design_package_id=None,
        target_kind=kind,
        target_id=target_id,
        schedule_version_id=None,
        external_id=None,
        action=action,
        version=version,
        target_snapshot_json={"code": "EWP-A"},
        reason="Reviewed applicability",
        created_at=observed,
    )
    row.content_hash = _hash(integration._mapping_content(row))
    return row


def revision(identity, sequence, deliverable=90, *, observed=OBSERVED):
    return SimpleNamespace(
        id=identity,
        deliverable_id=deliverable,
        revision_sequence=sequence,
        status="APPROVED",
        approved_at=observed,
        created_at=observed,
        content_hash=SHA,
        document_hash=SHA,
        document_ref_json={"source_system": integration.CDE_SOURCE, "sha256": SHA},
    )


def release(identity, rev, *, effective=EFFECTIVE, observed=OBSERVED, valid_until=None):
    snapshot = {
        "tenant_id": 6,
        "project_workspace_id": 31,
        "revision_id": rev.id,
        "deliverable_id": rev.deliverable_id,
        "effective_date": effective.isoformat(),
        "valid_until": valid_until,
        "revision_content_hash": rev.content_hash,
        "document_hash": rev.document_hash,
        "document_reference": dict(rev.document_ref_json),
    }
    return SimpleNamespace(
        id=identity,
        tenant_id=6,
        project_workspace_id=31,
        revision_id=rev.id,
        deliverable_id=rev.deliverable_id,
        effective_date=effective,
        released_at=observed,
        snapshot_json=snapshot,
        release_hash=_hash(snapshot),
    )


def reader(mappings, revisions, releases):
    result = integration.EngineeringReadinessReader(None, 6, 31, [])
    result.mappings_by_package[88] = mappings
    result.revision_by_id = {row.id: row for row in revisions}
    for row in releases:
        result.releases_by_deliverable[row.deliverable_id].append(row)
    result._reference_valid = lambda row, instant: True
    return result


@pytest.mark.parametrize("kind", ["WBS", "ACTIVITY", "MILESTONE"])
def test_engineering_schedule_mapping_requires_version_and_exact_external_identity(kind):
    payload = integration.EngineeringMappingIn(
        target_kind=kind, schedule_version_id=8, external_id="P6-002", reason="Verified identity"
    )
    assert payload.external_id == "P6-002" and payload.target_id is None
    with pytest.raises(ValidationError, match="ENGINEERING_SCHEDULE_REFERENCE_REQUIRED"):
        integration.EngineeringMappingIn(target_kind=kind, target_id=10, reason="Ambiguous numeric identity")


@pytest.mark.parametrize("kind", ["EWP", "CWP", "IWP", "CWA", "SCOPE", "PLAN", "CBS", "COST_CODE", "CONTROL_ACCOUNT"])
def test_engineering_mapping_typed_canonical_targets_are_not_schedule_names(kind):
    payload = integration.EngineeringMappingIn(target_kind=kind, target_id=7, reason="Reviewed ID")
    assert payload.target_id == 7 and payload.schedule_version_id is None
    with pytest.raises(ValidationError, match="ENGINEERING_CANONICAL_TARGET_REQUIRED"):
        integration.EngineeringMappingIn(target_kind=kind, target_id=7, external_id="wrong", reason="Mixed identity")


def test_engineering_mapping_set_remove_is_append_only_and_keeps_multiple_targets():
    set_first = link(101, 7)
    set_second = link(102, 7, version=3, target_id=89)
    other_revision = link(103, 8)
    remove = link(104, 7, version=4, action="REMOVE")
    assert [row.id for row in integration._effective([remove, other_revision, set_first, set_second])] == [102, 103]
    assert set_first.action == "SET"


def test_engineering_schedule_activity_wbs_and_milestone_use_imported_identity():
    schedule = SimpleNamespace(
        snapshot_json={
            "activities": [
                {"external_id": "170", "name": "Same display name", "activity_type": "Task Dependent"},
                {"external_id": "171", "name": "Same display name", "activity_type": "Finish Milestone"},
            ],
            "wbs": [{"external_id": "21", "name": "Control account 21"}],
        }
    )
    assert integration._schedule_item(schedule, "ACTIVITY", "170")["external_id"] == "170"
    assert integration._schedule_item(schedule, "MILESTONE", "170") is None
    assert integration._schedule_item(schedule, "MILESTONE", "171")["external_id"] == "171"
    assert integration._schedule_item(schedule, "WBS", "21") is not None
    assert integration._schedule_item(schedule, "WBS", "Control account 21") is None


def test_engineering_readiness_future_and_superseded_sources_are_not_used_early():
    old = revision(4, 1)
    new = revision(5, 2)
    a = release(44, old)
    b = release(45, new, effective=EFFECTIVE + timedelta(days=1))
    facts = reader([link(100, old.id), link(101, new.id)], [old, new], [a, b])
    package = SimpleNamespace(id=88, package_type="EWP")
    before = facts.evidence(package, EFFECTIVE)
    assert before["status"] == "ELIGIBLE"
    assert before["sources"][0]["release_id"] == a.id
    assert before["coverage"] == {"required": 1, "covered": 1}
    after = facts.evidence(package, b.effective_date)
    assert after["sources"][0]["release_id"] == b.id
    assert after["evidence_hash"] != before["evidence_hash"]
    # A successor that has not been explicitly mapped to this package cannot be used.
    facts.mappings_by_package[88].pop()
    stale = facts.evidence(package, b.effective_date)
    assert stale["status"] == "NOT_ELIGIBLE"
    assert stale["reason_codes"] == ["ENGINEERING_MAPPING_REVISION_SUPERSEDED"]
    assert _hash(a.snapshot_json) == a.release_hash


def test_engineering_readiness_records_timestamp_not_just_effective_calendar_day():
    rev = revision(7, 1)
    issued = release(45, rev, observed=OBSERVED + timedelta(hours=2))
    facts = reader([link(100, rev.id)], [rev], [issued])
    package = SimpleNamespace(id=88, package_type="EWP")
    assert facts.evidence(package, OBSERVED)["reason_codes"] == ["ENGINEERING_IFC_NOT_EFFECTIVE_AT_CUTOFF"]
    assert facts.evidence(package, OBSERVED + timedelta(hours=3))["status"] == "ELIGIBLE"


def test_engineering_readiness_coverage_rejects_expiry_corruption_and_stale_cde():
    rev = revision(7, 1)
    other = revision(8, 1, deliverable=91)
    expires = release(45, rev, valid_until=EFFECTIVE.isoformat())
    facts = reader([link(100, rev.id), link(101, other.id)], [rev, other], [expires])
    package = SimpleNamespace(id=88, package_type="EWP")
    partial = facts.evidence(package, EFFECTIVE)
    assert partial["coverage"] == {"required": 2, "covered": 1}
    assert partial["reason_codes"] == ["ENGINEERING_IFC_REQUIRED"]
    assert "ENGINEERING_EVIDENCE_EXPIRED" in facts.evidence(package, EFFECTIVE + timedelta(days=1))["reason_codes"]
    facts._reference_valid = lambda row, instant: False
    assert "ENGINEERING_RELEASE_OR_CDE_INTEGRITY_INVALID" in facts.evidence(package, EFFECTIVE)["reason_codes"]
    facts._reference_valid = lambda row, instant: True
    expires.snapshot_json["revision_content_hash"] = "b" * 64
    assert "ENGINEERING_RELEASE_OR_CDE_INTEGRITY_INVALID" in facts.evidence(package, EFFECTIVE)["reason_codes"]


def test_awp_provider_is_authoritative_for_explicit_mapping_but_cannot_clear_constraint():
    package = SimpleNamespace(id=88, package_type="EWP")
    mappings = [
        {"target_kind": "SCOPE", "mapping_health": "VALID"},
        {"target_kind": "ACTIVITY", "mapping_health": "VALID"},
    ]
    manual = {"ENGINEERING": "legacy-approved-doc"}
    unlinked = AWPService._assess_with_engineering(package, DEFAULT_PROFILE, [], [], manual, mappings, None)
    assert unlinked == assess_policy("EWP", DEFAULT_PROFILE, [], [], manual, True, True)
    provider = {"status": "NOT_ELIGIBLE", "work_package_id": package.id, "evidence_hash": SHA}
    blocked = AWPService._assess_with_engineering(package, DEFAULT_PROFILE, [], [], manual, mappings, provider)
    assert blocked["dimensions"]["ENGINEERING"]["state"] == "MISSING_EVIDENCE"
    assert blocked["readiness_state"] != "READY"
    provider["status"] = "ELIGIBLE"
    constraint = {"id": 4, "status": "OPEN", "blocking": True, "constraint_type": "ENGINEERING"}
    assessed = AWPService._assess_with_engineering(package, DEFAULT_PROFILE, [constraint], [], {}, mappings, provider)
    assert assessed["readiness_state"] == "NOT_READY"
    assert constraint["status"] == "OPEN"
    assert assessed["dimensions"]["ENGINEERING"]["evidence_reference"] == f"engineering:88:{SHA}"
    assert assessed["evidence_state"]["engineering_provider"]["evidence_hash"] == SHA


def test_engineering_source_reference_grammar_never_accepts_name_or_unpinned_hash():
    assert integration._typed_ref(f"engineering-revision:17:{SHA}", "engineering-revision") == (17, SHA)
    for reference in (
        f"engineering-release:17:{SHA}",
        f"engineering-revision:Project drawing:{SHA}",
        "engineering-revision:17:not-a-sha",
        f"engineering-revision:0:{SHA}",
    ):
        with pytest.raises(ValueError, match="ENGINEERING_SOURCE_REFERENCE_INVALID"):
            integration._typed_ref(reference, "engineering-revision")


def test_engineering_status_accepts_api_grouping_values(monkeypatch):
    row = {
        "status": "APPROVED",
        "planned_issue_date": EFFECTIVE.isoformat(),
        "release_id": 12,
        "overdue": False,
        "forecast_late": False,
        "superseded_ifc": 0,
        "discipline": "CIVIL",
        "area": "North",
        "mappings": [{"target_kind": "EWP", "target_id": 88, "target": {"area": "North", "cwa_id": 23}}],
    }
    service = integration.EngineeringIntegrationMixin()
    monkeypatch.setattr(service, "_engineering_read_facts", lambda workspace, as_of: (None, EFFECTIVE, [row]))
    dimensions = {"area": "North", "cwa": 23, "discipline": "CIVIL", "ewp": 88, "project": 31}
    unfiltered = service.status_metrics(31)
    assert {item["dimension"] for item in unfiltered["groups"]} == {key.upper() for key in dimensions} - {"PROJECT"}
    for dimension, key in dimensions.items():
        filtered = service.status_metrics(31, group_by=dimension)
        assert filtered["project"] == unfiltered["project"]
        assert filtered["groups"] == [{"dimension": dimension.upper(), "key": key, **filtered["project"]}]


def test_engineering_lookahead_keeps_overdue_successor_while_prior_ifc_is_effective(monkeypatch):
    old = revision(4, 1)
    successor = revision(5, 2)
    header = SimpleNamespace(id=old.deliverable_id, updated_at=OBSERVED)
    old.updated_at = successor.updated_at = OBSERVED
    successor.planned_issue_date = (EFFECTIVE - timedelta(days=1)).isoformat()
    prior_ifc = release(44, old)
    successor_ifc = release(45, successor, effective=EFFECTIVE + timedelta(days=1))
    rows = {
        integration.EngineeringDeliverable: [header],
        integration.EngineeringRevision: [old, successor],
        integration.EngineeringRelease: [prior_ifc, successor_ifc],
        integration.EngineeringMapping: [],
    }
    service = integration.EngineeringIntegrationMixin()
    service.tenant_id = 6
    service.db = SimpleNamespace(scalars=lambda statement: rows[statement.column_descriptions[0]["entity"]])
    service._project = lambda workspace: None
    service._require_schema = lambda: None
    service._out = vars
    service._engineering_profile = lambda project: None
    monkeypatch.setattr(integration, "utc_now", lambda: OBSERVED + timedelta(days=2))

    status = service.status_metrics(31, as_of=EFFECTIVE)
    assert status["project"]["ifc_released"] == 1
    assert status["project"]["overdue"] == 1
    pending = service.lookahead(31, as_of=EFFECTIVE)["items"]
    assert len(pending) == 1
    assert pending[0]["revision_id"] == successor.id
    assert pending[0]["effective_ifc_revision_id"] == old.id
    assert pending[0]["release_id"] == prior_ifc.id
    assert pending[0]["ifc_release_due"] == successor.planned_issue_date

    status = service.status_metrics(31, as_of=successor_ifc.effective_date)
    assert status["project"]["ifc_released"] == 1
    assert status["project"]["overdue"] == 0
    assert status["items"][0]["effective_ifc_revision_id"] == successor.id
    assert service.lookahead(31, as_of=successor_ifc.effective_date)["items"] == []
