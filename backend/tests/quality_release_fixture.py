"""Real Field/Engineering/Procurement evidence for isolated O3B API and browser UAT."""

import os
from copy import deepcopy
from datetime import UTC, datetime

from sqlalchemy import text
from tests.engineering_release_fixture import TODAY, add_actor, request
from tests.field_operations_release_fixture import approve_report, create_core_chain, create_verified_production
from tests.field_operations_release_fixture import setup as field_setup
from tests.test_procurement_o2b_release import expect

from app.core.security import hash_password
from app.domain.models import AuthCredential, ProjectMembership
from app.modules.quality.permissions import ensure_quality_permissions
from app.modules.quality.policy import DEFAULT_PROFILE

REASON = {"reason": "Controlled O3B validation against actual governed source lifecycles"}
ROLES = {
    "quality_reporter": False,
    "quality_inspector": False,
    "quality_reviewer": False,
    "quality_approver": False,
    "quality_manager": False,
    "ncr_owner": False,
    "quality_configurator": True,
    "quality_publisher": True,
}


def root(f, workspace=None):
    return f"/api/v1/quality/projects/{workspace or f.project_workspace_id}"


def call(f, method, path, *, actor="quality_reporter", payload=None, version=None, key=None, params=None):
    return request(
        f,
        method,
        path if path.startswith("/api") else root(f) + path,
        actor=actor,
        payload=payload,
        version=version,
        key=key,
        params=params,
    )


def command(f, path, payload=None, *, actor="quality_reporter", version=None, key=None, status=201):
    return expect(
        call(f, "POST", path, actor=actor, payload=REASON | (payload or {}), version=version, key=key), status
    )


def action(f, resource, row, value, *, actor, status=200, **extras):
    return command(
        f,
        f"/{resource}/{row['id']}/actions",
        {"action": value, **extras},
        actor=actor,
        version=row["version"],
        status=status,
    )


def pin(source):
    return {key: source[key] for key in ("source_type", "source_id", "source_version", "source_hash")}


def source(f, kind, identity, *, as_of=None):
    params = {"source_type": kind, "source_id": identity}
    if as_of:
        params["as_of"] = as_of
    return expect(call(f, "GET", "/source", params=params), 200)


def setup(db, client, *, credentials=False, publish=True):
    """Serialize legacy global catalog provisioning, not Quality project commands."""
    assert os.getenv("PYPMIS_O3B_FIXTURE") == "disposable-only"
    assert (db.bind.url.host, db.bind.url.port, db.bind.url.database, db.bind.url.username) in {
        ("127.0.0.1", 5567, "o3b", "o3b"),
        ("127.0.0.1", 5568, "o3b", "o3b"),
    }
    # A dedicated connection keeps a session-level lock out of the application
    # session pool across the many intentional upstream API commits.
    with db.bind.connect() as lock_connection:
        lock_connection.execute(text("SELECT pg_advisory_lock(8030081)"))
        try:
            return _setup(db, client, credentials=credentials, publish=publish)
        finally:
            lock_connection.execute(text("SELECT pg_advisory_unlock(8030081)"))


def _setup(db, client, *, credentials=False, publish=True):
    assert os.getenv("PYPMIS_O3B_FIXTURE") == "disposable-only"
    assert (db.bind.url.host, db.bind.url.port, db.bind.url.database, db.bind.url.username) in {
        ("127.0.0.1", 5567, "o3b", "o3b"),
        ("127.0.0.1", 5568, "o3b", "o3b"),
    }
    f = create_core_chain(field_setup(db, client, credentials=credentials, material_required=True))
    create_verified_production(f)
    if credentials:
        approve_report(f)
    workspace = f.workspaces["direct"]
    workspace.defaults_json = {
        **workspace.defaults_json,
        "enabled_modules": [*workspace.defaults_json["enabled_modules"], "quality-manager"],
    }
    ensure_quality_permissions(db, f.tenant_id, f.users["admin"].id)
    ensure_quality_permissions(db, f.foreign_tenant.id, f.users["foreign"].id)
    for label, organization in ROLES.items():
        add_actor(db, f, label, label, organization=organization)
        actor = f.users[label]
        db.add(
            ProjectMembership(
                tenant_id=f.tenant_id,
                project_id=f.legacy_project_id,
                user_id=actor.id,
                role="Executive Viewer",
                can_configure=organization,
                can_capture_progress=False,
                can_capture_cost=False,
            )
        )
        if credentials:
            db.add(
                AuthCredential(
                    tenant_id=f.tenant_id,
                    user_id=actor.id,
                    provider="local",
                    password_hash=hash_password(f.password),
                    is_active=True,
                )
            )
    db.commit()
    f.quality_document_pin = f.field_document_pin
    if publish:
        base = "/api/v1/quality/admin/profiles"
        draft = command(
            f,
            base,
            {
                "code": f"QUALITY-{f.token}",
                "name": "Controlled Quality profile",
                "content_json": deepcopy(DEFAULT_PROFILE),
            },
            actor="quality_configurator",
        )
        f.quality_profile = command(
            f, base + f"/{draft['id']}/publish", actor="quality_publisher", version=draft["version"], status=200
        )
    f.quality_subject = pin(source(f, "FIELD_PRODUCTION", f.field_production["id"]))
    f.quality_engineering = pin(source(f, "IFC_RELEASE", f.ifc["id"]))
    return f


def create_itp(f, *, test_required=False, control_type="HOLD"):
    f.quality_plan_body = {
        "code": "QUALITY-PLAN",
        "title": "Governed project quality strategy",
        "scope": "Verified installation quality",
        "responsible_user_id": f.users["quality_manager"].id,
        "effective_date": TODAY.isoformat(),
        "source_references": [{"target_kind": "SCOPE", "target_id": f.scope_items[0]["id"]}],
        "document_references": [f.quality_document_pin],
    }
    plan = command(f, "/plans", f.quality_plan_body)
    plan = action(f, "plans", plan, "submit", actor="quality_reporter")
    f.quality_plan = action(f, "plans", plan, "approve", actor="quality_approver")
    f.quality_itp_body = {
        "code": "QUALITY-ITP",
        "title": "Installation inspection and test plan",
        "quality_plan_id": f.quality_plan["id"],
        "discipline": "CIVIL",
        "effective_date": TODAY.isoformat(),
        "engineering_reference": f.quality_engineering,
        "source_references": [{"target_kind": "IWP", "target_id": f.field_released_iwp["id"]}],
        "document_references": [f.quality_document_pin],
    }
    itp = command(f, "/itps", f.quality_itp_body)
    f.quality_item_body = {
        "itp_id": itp["id"],
        "itp_item_code": "QC-INSTALLATION",
        "sequence": 10,
        "activity": "Installed work conformity",
        "control_type": control_type,
        "requirement_reference": "Current governed IFC requirement",
        "acceptance_criteria": "Conformity verified by structured checklist and independent review",
        "responsible_party": "Quality inspector",
        "witness_party": "Owner",
        "evidence_required": True,
        "next_step_rule": "Explicit Quality control release required",
        "required": True,
        "inspection_required": True,
        "test_required": test_required,
        "checklist_template_code": "GENERAL",
    }
    if test_required:
        f.quality_item_body |= {
            "test_type": "CONCRETE_STRENGTH",
            "test_uom": "MPa",
            "test_lower_limit": "30",
            "test_upper_limit": "80",
        }
    f.quality_item = command(f, "/itp-items", f.quality_item_body)
    itp = action(f, "itps", itp, "submit", actor="quality_reporter")
    f.quality_itp = action(f, "itps", itp, "approve", actor="quality_approver")
    return f.quality_itp


def create_inspection(
    f,
    *,
    result="PASS",
    reinspection_of_id=None,
    corrective_action_id=None,
    subject_reference=None,
    code="QC-INSPECTION",
    uom=None,
    inspection_type=None,
):
    now = datetime.now(UTC).isoformat()
    body = {
        "request_number": code,
        "itp_item_id": f.quality_item["id"],
        "subject_reference": subject_reference or f.quality_subject,
        "quantity": "1",
        "uom": uom or f.scope_items[0]["unit"],
        "requested_at": now,
        "requested_for": now,
        "inspector_user_id": f.users["quality_inspector"].id,
        "inspection_type": inspection_type or ("REINSPECTION" if reinspection_of_id else "GENERAL"),
        "document_references": [f.quality_document_pin],
        "reinspection_of_id": reinspection_of_id,
        "corrective_action_id": corrective_action_id,
    }
    f.quality_request_body = body
    row = command(f, "/inspection-requests", body)
    for value, actor in (
        ("submit", "quality_reporter"),
        ("schedule", "quality_inspector"),
        ("start", "quality_inspector"),
    ):
        row = action(f, "inspection-requests", row, value, actor=actor)
    f.quality_request = row
    f.quality_inspection_body = {
        "record_number": code,
        "request_id": row["id"],
        "engineering_reference": f.quality_engineering,
        "inspected_at": datetime.now(UTC).isoformat(),
        "result": result,
        "checklist_responses": [
            {"item_code": "CONFORMITY", "response_code": result, "evidence_references": [f.quality_document_pin]}
        ],
        "document_references": [f.quality_document_pin],
    }
    f.quality_inspection = command(f, "/inspections", f.quality_inspection_body, actor="quality_inspector")
    return f.quality_inspection


def close_inspection(f, row):
    row = action(f, "inspections", row, "submit", actor="quality_inspector")
    f.quality_inspection = action(f, "inspections", row, "close", actor="quality_reviewer")
    return f.quality_inspection


def release_control(f, inspection, test=None, *, subject_reference=None, version=0):
    f.quality_control = command(
        f,
        "/control-point-decisions",
        {
            "itp_item_id": f.quality_item["id"],
            "subject_reference": subject_reference or f.quality_subject,
            "inspection_record_id": inspection["id"],
            "test_record_id": test["id"] if test else None,
            "decision": "RELEASED",
            "document_references": [f.quality_document_pin],
        },
        actor="quality_approver",
        version=version,
    )
    return f.quality_control


def create_acceptance(f):
    """Actual PASS/HOLD lifecycle, without silently adopting any native consumer."""
    create_itp(f)
    inspection = close_inspection(f, create_inspection(f))
    release_control(f, inspection)
    f.quality_acceptance_body = {
        "acceptance_code": "QUALITY-ACCEPTANCE",
        "subject_reference": f.quality_subject,
        "itp_id": f.quality_itp["id"],
        "quantity": "1",
        "uom": f.scope_items[0]["unit"],
        "effective_at": datetime.now(UTC).isoformat(),
        "document_reference": f.quality_document_pin,
    }
    f.quality_acceptance = command(f, "/acceptances", f.quality_acceptance_body, actor="quality_approver")
    return f.quality_acceptance


def create_test(f, *, code="QC-TEST", measurements=None, result="PASS"):
    now = datetime.now(UTC).isoformat()
    body = {
        "request_number": code,
        "itp_item_id": f.quality_item["id"],
        "subject_reference": f.quality_subject,
        "quantity": "1",
        "uom": f.scope_items[0]["unit"],
        "requested_at": now,
        "requested_for": now,
        "inspector_user_id": f.users["quality_inspector"].id,
        "test_type": "CONCRETE_STRENGTH",
        "document_references": [f.quality_document_pin],
    }
    row = command(f, "/test-requests", body)
    for value, actor in (
        ("submit", "quality_reporter"),
        ("schedule", "quality_inspector"),
        ("start", "quality_inspector"),
    ):
        row = action(f, "test-requests", row, value, actor=actor)
    f.quality_test_request = row
    f.quality_test_body = {
        "record_number": code,
        "request_id": row["id"],
        "engineering_reference": f.quality_engineering,
        "tested_at": datetime.now(UTC).isoformat(),
        "result": result,
        "method": "Governed specimen test method",
        "standard": "Controlled project technical test standard",
        "measurements": measurements
        or [
            {
                "code": "SPECIMEN-1",
                "numeric_value": "40",
                "uom": "MPa",
                "lower_limit": "30",
                "upper_limit": "80",
                "result": "PASS",
            },
            {
                "code": "SPECIMEN-2",
                "numeric_value": "42",
                "uom": "MPa",
                "lower_limit": "30",
                "upper_limit": "80",
                "result": "PASS",
            },
        ],
        "document_references": [f.quality_document_pin],
    }
    f.quality_test = command(f, "/tests", f.quality_test_body, actor="quality_inspector")
    return f.quality_test


def close_test(f, row):
    row = action(f, "tests", row, "submit", actor="quality_inspector")
    f.quality_test = action(f, "tests", row, "close", actor="quality_reviewer")
    return f.quality_test
