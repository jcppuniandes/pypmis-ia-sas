"""O2A HTTP and PostgreSQL release evidence, using real O1/CDE fixtures."""

import os
from copy import deepcopy
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from tests.engineering_release_fixture import (
    REASON,
    TODAY,
    approve,
    cde_document,
    create_engineering_fixture,
    deliverable_body,
    draft,
    link,
    publish_engineering_profile,
    release,
    request,
    review,
    revision_body,
)
from tests.test_schedule_foundation_release import accept, map_all, version
from tests.test_schedule_foundation_release import request as schedule_request
from tests.test_scope_foundation_release import success

from app.database.session import SessionLocal, engine
from app.main import app
from app.modules.engineering_foundation import integration


@pytest.fixture(scope="module")
def fixture():
    if os.getenv("PYPMIS_O2A_FIXTURE") != "disposable-only":
        pytest.skip("O2A isolated PostgreSQL fixture required")
    assert engine.dialect.name == "postgresql" and engine.url.database == "o2a"
    with TestClient(app) as client, SessionLocal() as db:
        yield create_engineering_fixture(db, client)


def denial(response, status, code=None):
    assert response.status_code == status, response.text
    if code is not None:
        assert response.json()["detail"]["code"] == code, response.text


def mapping(f, revision, **target):
    path = f"/revisions/{revision['id']}/mappings"
    collection = success(request(f, "GET", path))
    return success(request(f, "POST", path, version=collection["version"], payload={**REASON, **target}), 201)


def test_deliverable_identity_catalog_pagination_etag_and_idempotency(fixture):
    f = fixture
    body = deliverable_body()
    key = f"o2a-register-{uuid4()}"
    response = request(f, "POST", "/deliverables", payload=body, key=key)
    row = success(response, 201)
    assert response.headers["etag"] == f'"{row["version"]}"'
    assert success(request(f, "POST", "/deliverables", payload=body, key=key), 201) == row
    denial(request(f, "POST", "/deliverables", payload={**body, "title": "Other"}, key=key), 409)
    denial(request(f, "POST", "/deliverables", payload=deliverable_body(discipline="UNPUBLISHED")), 422)
    endpoint = f"/deliverables/{row['id']}"
    denial(request(f, "PUT", endpoint, version=999, payload=body), 412)
    updated = success(
        request(f, "PUT", endpoint, version=row["version"], payload={**body, "title": "Checked controlled title"})
    )
    assert updated["title"] == "Checked controlled title" and updated["version"] > row["version"]
    page = success(request(f, "GET", "/deliverables", params={"limit": 1}))
    assert len(page["items"]) == 1
    assert isinstance(page["allowed_actions"], list)
    denial(request(f, "GET", endpoint, actor="outsider"), 404)
    other = f.workspaces["other_project"].id
    denial(request(f, "GET", f"/api/v1/engineering/projects/{other}/deliverables", actor="preparer"), 403)
    denial(request(f, "POST", "/deliverables", payload=deliverable_body(), actor="approver"), 403)


def test_cde_link_for_construction_and_upload_are_not_approval_or_release(fixture):
    f = fixture
    _, row = draft(f, doc=False)
    path = f"/revisions/{row['id']}"
    deny_release = {**REASON, "effective_date": TODAY.isoformat(), "release_reference": "signed fixture"}
    denial(
        request(f, "POST", path + "/ifc-release", payload=deny_release, version=row["version"], actor="releaser"), 409
    )
    denial(
        request(
            f,
            "POST",
            path + "/document",
            version=row["version"],
            payload={**REASON, "document_id": f.document["id"], "attachment_id": f.successor_attachment["id"]},
        ),
        404,
    )
    linked = link(f, row)
    assert linked["document_hash"] == f.attachment["sha256"] and linked["status"] == "DRAFT"
    assert linked["ifc_release_status"] == "NOT_RELEASED"
    denial(
        request(f, "POST", path + "/ifc-release", payload=deny_release, version=linked["version"], actor="preparer"),
        403,
    )


def test_review_comments_response_revise_resubmit_check_and_approval(fixture):
    f = fixture
    _, row = draft(f)
    path = f"/revisions/{row['id']}"
    row = review(f, review(f, row, "submit", "preparer"), "start", "reviewer")
    comment = success(
        request(
            f,
            "POST",
            path + "/comments",
            actor="reviewer",
            version=row["version"],
            payload={
                **REASON,
                "discipline": "MECHANICAL",
                "category": "DETAIL",
                "severity": "BLOCKING",
                "text": "Clarify connection sizing",
            },
        ),
        201,
    )
    row = success(request(f, "GET", path))
    assert row["version"] == comment["revision_version"]
    denial(
        request(
            f,
            "POST",
            path + "/review-action",
            actor="reviewer",
            version=row["version"],
            payload={**REASON, "action": "accept"},
        ),
        409,
    )
    row = review(f, row, "request_changes", "reviewer")
    comment_path = f"/review-comments/{comment['id']}/transition"
    responded = success(
        request(
            f,
            "POST",
            comment_path,
            actor="preparer",
            version=comment["version"],
            payload={**REASON, "action": "respond", "response": "Connection sizing updated in the design notes."},
        )
    )
    closed = success(
        request(
            f,
            "POST",
            comment_path,
            actor="reviewer",
            version=responded["version"],
            payload={**REASON, "action": "close"},
        )
    )
    assert closed["status"] == "CLOSED" and closed["closed_by"] == f.users["reviewer"].id
    revised = success(
        request(
            f,
            "PUT",
            path,
            version=closed["revision_version"],
            payload=revision_body(description="Corrected connection sizing"),
        )
    )
    row = approve(f, revised)
    assert row["status"] == "APPROVED" and row["ifc_release_status"] == "NOT_RELEASED"
    assert row["checked_by"] == f.users["checker"].id and row["approved_by"] == f.users["approver"].id
    round_history = success(request(f, "GET", path + "/reviews"))
    assert "REVISE_AND_RESUBMIT" in str(round_history) and "APPROVED" in str(round_history)
    closed_review = review(f, row, "close", "reviewer")
    assert closed_review["review_status"] == "CLOSED" and closed_review["version"] == row["version"]


def test_rejection_is_explicit_and_requires_successor(fixture):
    f = fixture
    parent, row = draft(f)
    row = review(f, review(f, row, "submit", "preparer"), "start", "reviewer")
    rejected = review(f, row, "reject", "approver")
    assert rejected["status"] == "REJECTED"
    denial(request(f, "PUT", f"/revisions/{row['id']}", version=rejected["version"], payload=revision_body()), 409)
    successor = success(
        request(
            f,
            "POST",
            f"/revisions/{row['id']}/successor",
            version=rejected["version"],
            payload=revision_body(revision_code="B"),
        ),
        201,
    )
    assert successor["supersedes_revision_id"] == rejected["id"] and successor["deliverable_id"] == parent["id"]


def test_ifc_release_is_independent_immutable_and_successor_is_effective_by_cutoff(fixture):
    f = fixture
    parent, row = draft(f)
    approved = approve(f, row)
    invalid = request(
        f,
        "POST",
        f"/revisions/{row['id']}/ifc-release",
        actor="releaser",
        version=approved["version"],
        payload={
            **REASON,
            "effective_date": (TODAY - timedelta(days=1)).isoformat(),
            "release_reference": "dated fixture",
        },
    )
    denial(invalid, 422)
    released = release(f, approved)
    assert released["ifc_release_status"] == "CURRENT_IFC" and released["version"] == approved["version"]
    fact = released["release"]
    assert fact["snapshot_json"]["document_hash"] == f.attachment["sha256"]
    assert fact["released_by"] == f.users["releaser"].id
    second = success(
        request(
            f,
            "POST",
            f"/revisions/{row['id']}/successor",
            version=approved["version"],
            payload=revision_body(revision_code="B"),
        ),
        201,
    )
    assert success(request(f, "GET", f"/revisions/{row['id']}"))["release"] == fact
    next_fact = release(f, approve(f, link(f, second, successor=True)), TODAY + timedelta(days=1))
    assert next_fact["ifc_release_status"] == "FUTURE_IFC"
    assert success(request(f, "GET", f"/revisions/{row['id']}"))["ifc_release_status"] == "CURRENT_IFC"
    assert success(request(f, "GET", f"/deliverables/{parent['id']}"))["current_revision_id"] == second["id"]
    with SessionLocal() as db:
        for statement, identity in (
            ("UPDATE engineering_revisions SET description='must not persist' WHERE id=:id", row["id"]),
            ("UPDATE engineering_releases SET release_reference='must not persist' WHERE id=:id", fact["id"]),
            ("UPDATE admin_configurations SET name='must not persist' WHERE id=:id", f.engineering_profile["id"]),
        ):
            with pytest.raises(DBAPIError, match="immutable"):
                with db.begin_nested():
                    db.execute(text(statement), {"id": identity})
    assert success(request(f, "GET", f"/revisions/{row['id']}"))["release"] == fact


def test_mapping_is_many_to_many_typed_append_only_and_project_scoped(fixture):
    f = fixture
    _, row = draft(f)
    targets = [
        *({"target_kind": "EWP", "target_id": item["id"]} for item in f.engineering_packages["EWP"]),
        *({"target_kind": "CWA", "target_id": item["id"]} for item in f.cwas),
        *({"target_kind": "SCOPE", "target_id": item["id"]} for item in f.scope_items[:2]),
        *({"target_kind": "PLAN", "target_id": item["id"]} for item in f.plan_items[:2]),
        *({"target_kind": kind, "target_id": f.engineering_packages[kind][0]["id"]} for kind in ("CWP", "IWP")),
        {"target_kind": "ACTIVITY", "schedule_version_id": f.current_schedule_version["id"], "external_id": "5001"},
    ]
    for target in targets:
        mapping(f, row, **target)
    path = f"/revisions/{row['id']}/mappings"
    before = success(request(f, "GET", path))
    assert len(before["items"]) == len(targets)
    denial(request(f, "POST", path, version=1, payload={**REASON, **targets[0]}), 412)
    with SessionLocal() as db, pytest.raises(DBAPIError, match="immutable"):
        with db.begin_nested():
            db.execute(
                text("UPDATE engineering_mappings SET reason='tamper' WHERE id=:id"), {"id": before["items"][0]["id"]}
            )
    for target in targets[:2]:
        mapping(f, row, action="REMOVE", **target)
    result = success(request(f, "GET", path))
    assert len(result["items"]) == len(targets) - 2 and len(result["history"]) == len(targets) + 2
    assert success(request(f, "GET", f"/revisions/{row['id']}"))["version"] == row["version"]


def test_awp_assesses_ifc_evidence_without_auto_clear_or_package_release(fixture):
    f = fixture
    _, row = draft(f)
    ready, blocked = f.engineering_packages["EWP"]
    for target in (ready, blocked):
        mapping(f, row, target_kind="EWP", target_id=target["id"])
    path = f.awp_root
    constraint = success(
        request(
            f,
            "POST",
            path + "/constraints",
            actor="admin",
            payload={
                **REASON,
                "code": f"ENGINEERING-{uuid4().hex[:8]}",
                "constraint_type": "ENGINEERING",
                "title": "Technical IFC evidence required",
                "blocking": True,
                "owner_user_id": f.users["preparer"].id,
            },
        ),
        201,
    )
    mapped = success(
        request(
            f,
            "POST",
            path + f"/constraints/{constraint['id']}/mappings",
            actor="admin",
            version=constraint["version"],
            payload={**REASON, "target_kind": "PACKAGE", "target_id": blocked["id"]},
        ),
        201,
    )
    params = {"work_package_id": ready["id"], "as_of": TODAY.isoformat()}
    assert success(request(f, "GET", "/readiness", params=params))["status"] != "ELIGIBLE"
    approved = approve(f, row)
    released = release(f, approved)
    fact = released["release"]
    evidence = success(request(f, "GET", "/readiness", params=params))
    assert evidence["status"] == "ELIGIBLE" and evidence["coverage"]["covered"] == 1
    assert evidence["sources"][0]["release_hash"] == fact["release_hash"]
    denied = success(
        request(f, "GET", "/readiness", params={**params, "as_of": (TODAY - timedelta(days=1)).isoformat()})
    )
    assert denied["status"] != "ELIGIBLE"
    for package, expected in ((ready, "READY"), (blocked, "NOT_READY")):
        assessed = success(
            request(
                f,
                "POST",
                path + f"/packages/{package['id']}/assess",
                actor="awp_manager",
                version=package["version"],
                payload={**REASON, "as_of": TODAY.isoformat(), "evidence_json": {}},
            ),
            201,
        )
        assert assessed["readiness_state"] == expected, assessed
        assert assessed["package"]["release_state"] != "RELEASED"
    with SessionLocal() as db:
        assert (
            db.scalar(text("SELECT status FROM awp_execution_constraints WHERE id=:id"), {"id": constraint["id"]})
            == "OPEN"
        )
    blocked_evidence = success(request(f, "GET", "/readiness", params={**params, "work_package_id": blocked["id"]}))
    transition = path + f"/constraints/{constraint['id']}/transition"
    evidence_ref = blocked_evidence["evidence_reference"]
    assert evidence_ref and evidence_ref.startswith(f"engineering:{blocked['id']}:")
    body = {**REASON, "status": "CLEARED", "evidence_reference": evidence_ref}
    denial(
        request(
            f,
            "POST",
            transition,
            actor="awp_manager",
            version=mapped["version"],
            payload={**body, "evidence_reference": f"engineering:{blocked['id']}:{'0' * 64}"},
        ),
        409,
        "AWP_ENGINEERING_CLEARANCE_EVIDENCE_INELIGIBLE",
    )
    denial(request(f, "POST", transition, actor="preparer", version=mapped["version"], payload=body), 403)
    cleared = success(request(f, "POST", transition, actor="awp_manager", version=mapped["version"], payload=body))
    assert cleared["status"] == "CLEARED" and cleared["evidence_reference"] == evidence_ref


def test_source_metrics_lookahead_history_are_read_only(fixture):
    f = fixture
    _, row = draft(f)
    with SessionLocal() as db:
        counts = {
            name: db.scalar(text(f"SELECT count(*) FROM {name}"))
            for name in (
                "engineering_history",
                "operational_context_commands",
                "scope_items",
                "schedule_versions",
                "cost_budget_versions",
                "progress_measurements",
                "forecast_versions",
            )
        }
    assert success(request(f, "GET", "/status"))["project"]["total_deliverables"] >= 1
    assert success(request(f, "GET", "/lookahead", params={"horizon_days": 14}))["horizon_days"] == 14
    success(request(f, "GET", "/source-facts"))
    success(request(f, "GET", f"/revisions/{row['id']}/reviews"))
    success(request(f, "GET", "/history"))
    with SessionLocal() as db:
        assert all(db.scalar(text(f"SELECT count(*) FROM {name}")) == count for name, count in counts.items())


def test_schedule_successor_stales_mapping_without_remapping(fixture):
    f = fixture
    _, row = draft(f)
    accepted = f.current_schedule_version
    wbs_id = accepted["snapshot_json"]["wbs"][0]["external_id"]
    for kind, external_id in (("ACTIVITY", "5001"), ("ACTIVITY", "5002"), ("WBS", wbs_id)):
        mapping(f, row, target_kind=kind, schedule_version_id=accepted["id"], external_id=external_id)
    path = f"/revisions/{row['id']}/mappings"
    before = success(request(f, "GET", path))
    assert {item["mapping_health"] for item in before["items"]} == {"VALID"}
    content = deepcopy(accepted["snapshot_json"])
    content["project"]["data_date"] = "2026-10-23T08:00:00"
    removed = deepcopy(content)
    removed["activities"] = [activity for activity in removed["activities"] if activity["external_id"] != "5001"]
    register = success(schedule_request(f, "GET", f"/registers/{f.schedule_register['id']}"))
    invalid = map_all(f, version(f, register, content=removed, predecessor=accepted["id"], kind="UPDATE"))
    response = schedule_request(
        f, "POST", f"/versions/{invalid['id']}/validate", version=invalid["version"], payload=REASON
    )
    denial(response, 409, "SCHEDULE_VALIDATION_BLOCKED")
    assert {"code": "SCHEDULE_MAPPING_BROKEN", "target": "5001"} in response.json()["detail"]["errors"]
    assert success(request(f, "GET", path)) == before
    register = success(schedule_request(f, "GET", f"/registers/{f.schedule_register['id']}"))
    successor = accept(f, map_all(f, version(f, register, content=content, predecessor=accepted["id"], kind="UPDATE")))
    after = success(request(f, "GET", path))
    assert after["version"] == before["version"]
    assert {item["id"] for item in after["items"]} == {item["id"] for item in before["items"]}
    for item in after["items"]:
        assert item["schedule_version_id"] == accepted["id"] and item["current_schedule_version_id"] == successor["id"]
        assert item["mapping_health"] == "REQUIRES_REVIEW"


def test_persisted_engineering_readiness_expiry_supersession_and_integrity(fixture, monkeypatch):
    f = fixture
    today = integration.utc_now().date()
    policy = publish_engineering_profile(
        f,
        scope={"type": "workspace", "workspace_id": f.project_workspace_id},
        readiness_evidence_rules={"max_age_days": 1},
    )
    package = success(
        request(
            f,
            "POST",
            f.awp_root + "/packages",
            actor="admin",
            payload={
                **REASON,
                "package_code": f"ENG-READINESS-{uuid4().hex[:8]}",
                "name": "Isolated Engineering readiness cutoff and integrity",
                "package_type": "EWP",
                "cwa_id": f.cwas[0]["id"],
            },
        ),
        201,
    )
    target = {"target_kind": "EWP", "target_id": package["id"]}

    def evidence(day):
        return success(
            request(f, "GET", "/readiness", params={"work_package_id": package["id"], "as_of": day.isoformat()})
        )

    _, first = draft(f)
    assert first["configuration_id"] == policy["id"]
    mapping(f, first, **target)
    first = release(f, approve(f, first), today)
    current = first["release"]
    assert current["snapshot_json"]["valid_until"] == (today + timedelta(days=1)).isoformat()

    _, missing = draft(f, doc=False)
    mapping(f, missing, **target)
    partial = evidence(today)
    assert partial["status"] == "NOT_ELIGIBLE" and partial["coverage"] == {"required": 2, "covered": 1}
    assert partial["reason_codes"] == ["ENGINEERING_IFC_REQUIRED"]
    mapping(f, missing, action="REMOVE", **target)

    later = success(
        request(
            f,
            "POST",
            f"/revisions/{first['id']}/successor",
            version=first["version"],
            payload=revision_body(revision_code="B"),
        ),
        201,
    )
    document, attachment = cde_document(f, f"ENG-READINESS-{uuid4().hex[:8]}", "B")
    later = success(
        request(
            f,
            "POST",
            f"/revisions/{later['id']}/document",
            version=later["version"],
            payload={**REASON, "document_id": document["id"], "attachment_id": attachment["id"]},
        )
    )
    effective = today + timedelta(days=3)
    later = release(f, approve(f, later), effective)
    assert later["ifc_release_status"] == "FUTURE_IFC"
    original = evidence(today)
    assert original["status"] == "ELIGIBLE" and original["sources"][0]["release_id"] == current["id"]

    # Advance only Engineering's observation clock, after real writes. The
    # HTTP handlers read genuine persisted dates, links, hashes and releases.
    def later_evidence(day):
        observed = integration.utc_now()
        with monkeypatch.context() as clock:
            clock.setattr(integration, "utc_now", lambda: observed + timedelta(days=3))
            return evidence(day)

    expired = later_evidence(today + timedelta(days=2))
    assert expired["status"] == "NOT_ELIGIBLE" and expired["reason_codes"] == ["ENGINEERING_EVIDENCE_EXPIRED"]
    assert expired["sources"][0]["release_id"] == current["id"]
    stale = later_evidence(effective)
    assert stale["status"] == "NOT_ELIGIBLE" and stale["reason_codes"] == ["ENGINEERING_MAPPING_REVISION_SUPERSEDED"]
    assert stale["sources"][0]["release_id"] == later["release"]["id"]
    mapping(f, later, **target)
    valid = later_evidence(effective)
    assert valid["status"] == "ELIGIBLE" and valid["coverage"] == {"required": 1, "covered": 1}
    assert valid["sources"][0]["release_hash"] == later["release"]["release_hash"]
    assert valid["evidence_hash"] != original["evidence_hash"]

    # Corrupt only this test-owned CDE attachment in disposable PostgreSQL;
    # never disable Engineering's release/mapping immutability triggers.
    old_sha = attachment["sha256"]
    changed_sha = ("0" if old_sha[0] != "0" else "1") + old_sha[1:]

    def change_sha(expected, replacement):
        with SessionLocal.begin() as db:
            changed = db.execute(
                text("""
                    UPDATE document_attachments SET sha256=:replacement
                    WHERE id=:id AND tenant_id=:tenant AND project_id=:project
                      AND document_id=:document AND sha256=:expected
                """),
                {
                    "id": attachment["id"],
                    "tenant": f.tenant_id,
                    "project": f.legacy_project_id,
                    "document": document["id"],
                    "expected": expected,
                    "replacement": replacement,
                },
            )
            assert changed.rowcount == 1

    change_sha(old_sha, changed_sha)
    try:
        compromised = later_evidence(effective)
        assert compromised["status"] == "NOT_ELIGIBLE"
        assert compromised["reason_codes"] == ["ENGINEERING_RELEASE_OR_CDE_INTEGRITY_INVALID"]
        assert compromised["evidence_reference"] is None
    finally:
        change_sha(changed_sha, old_sha)
    assert later_evidence(effective) == valid
