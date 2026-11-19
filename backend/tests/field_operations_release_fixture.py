"""Actual O1/O2B sources for isolated Field Operations tests and browser UAT."""

import os
from copy import deepcopy
from datetime import UTC, datetime, timedelta

from tests.engineering_release_fixture import TODAY, add_actor, request
from tests.o2b_close_isolation import is_close_consumer_database
from tests.test_procurement_consumer_release import create_governed_fixture
from tests.test_procurement_o2b_release import expect

from app.core.security import hash_password
from app.domain.models import AuthCredential, ProjectMembership
from app.modules.awp.policy import DIMENSIONS
from app.modules.field_operations.permissions import ensure_field_permissions
from app.modules.field_operations.policy import DEFAULT_PROFILE

REASON = {"reason": "Controlled O3A field validation on disposable sources"}
ROLES = {
    "field_reporter": ("field_reporter", False),
    "field_supervisor": ("field_supervisor", False),
    "field_approver": ("field_approver", False),
    "field_configurator": ("field_configurator", True),
    "field_publisher": ("field_publisher", True),
    "field_instruction_issuer": ("field_instruction_issuer", False),
}


def field_root(f, workspace=None):
    return f"/api/v1/field-operations/projects/{workspace or f.project_workspace_id}"


def call(f, method, path, *, actor="field_reporter", payload=None, version=None, key=None, params=None):
    route = path if path.startswith("/api") else field_root(f) + path
    return request(f, method, route, actor=actor, payload=payload, version=version, key=key, params=params)


def command(f, path, payload=None, *, actor="field_reporter", version=None, key=None, status=201):
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


def release_iwp(f):
    overview = expect(request(f, "GET", f.awp_root + "/overview", actor="awp_manager"), 200)
    iwp = next(row for row in overview["packages"] if row["id"] == f.iwp["id"])
    assessment = expect(
        request(
            f,
            "POST",
            f.awp_root + f"/packages/{iwp['id']}/assess",
            actor="awp_manager",
            version=iwp["version"],
            payload=REASON
            | {"as_of": TODAY.isoformat(), "evidence_json": dict.fromkeys(DIMENSIONS, f"CDE:{f.document['id']}")},
        ),
        201,
    )
    if assessment["readiness_state"] != "READY":
        raise AssertionError(f"Actual sources did not permit native AWP readiness: {assessment}")
    iwp = expect(
        request(
            f,
            "POST",
            f.awp_root + f"/packages/{iwp['id']}/transition",
            actor="awp_manager",
            version=assessment["package"]["version"],
            payload=REASON | {"status": "READY"},
        ),
        200,
    )
    f.field_released_iwp = expect(
        request(
            f,
            "POST",
            f.awp_root + f"/packages/{iwp['id']}/release",
            actor="manager",
            version=iwp["version"],
            payload=REASON,
        ),
        200,
    )
    assert f.field_released_iwp["release_state"] == "RELEASED"


def setup(db, client, *, credentials=False, publish=True, material_required=False):
    assert os.getenv("PYPMIS_O3A_FIXTURE") == "disposable-only" and is_close_consumer_database(db)
    assert (db.bind.url.port, db.bind.url.database, db.bind.url.username) in {
        (5564, "o3a", "o3a"),
        (5565, "o3a", "o3a"),
    }
    f = create_governed_fixture(db, client, credentials=credentials)
    f.db = db
    workspace = f.workspaces["direct"]
    workspace.defaults_json = {
        **workspace.defaults_json,
        "enabled_modules": [*workspace.defaults_json["enabled_modules"], "field-operations"],
    }
    ensure_field_permissions(db, f.tenant_id, f.users["admin"].id)
    ensure_field_permissions(db, f.foreign_tenant.id, f.users["foreign"].id)
    for label, (role, organization) in ROLES.items():
        add_actor(db, f, label, role, organization=organization)
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
    f.field_roles = {name: f.users[name] for name in ROLES}
    release_iwp(f)
    f.field_document_pin = {"document_id": f.document["id"], "attachment_id": f.attachment["id"]}
    if publish:
        base = "/api/v1/field-operations/admin/profiles"
        content = deepcopy(DEFAULT_PROFILE)
        if material_required:
            content["production_policy"]["require_material_ready"] = True
            content["readiness_requirements"]["materials"] = True
        draft = command(
            f,
            base,
            {"code": f"FIELD-{f.token}", "name": "Controlled field profile", "content_json": content},
            actor="field_configurator",
        )
        f.field_profile = command(
            f, f"{base}/{draft['id']}/publish", actor="field_publisher", version=draft["version"], status=200
        )
    return f


def create_core_chain(f):
    front_data = {
        "workfront_code": "FIELD-FRONT",
        "title": "Governed installation front",
        "description": "Actual execution",
        "location_reference": {"target_kind": "SCOPE", "target_id": f.scope_items[0]["id"]},
        "cwa_id": f.cwas[0]["id"],
        "iwp_id": f.field_released_iwp["id"],
        "responsible_user_id": f.users["field_supervisor"].id,
        "planned_start": TODAY.isoformat(),
        "planned_finish": (TODAY + timedelta(days=7)).isoformat(),
    }
    f.field_front_body = front_data
    front = command(f, "/workfronts", front_data)
    f.field_front = action(f, "workfronts", front, "activate", actor="field_supervisor")
    start = datetime.combine(TODAY, datetime.min.time()).replace(tzinfo=UTC)
    f.field_shift_body = {
        "shift_code": "FIELD-DAY",
        "shift_type": "DAY",
        "shift_date": TODAY.isoformat(),
        "start_time": start.isoformat(),
        "end_time": (start + timedelta(hours=23, minutes=59)).isoformat(),
        "workfront_id": f.field_front["id"],
        "supervisor_user_id": f.users["field_supervisor"].id,
    }
    f.field_shift = command(f, "/shifts", f.field_shift_body)
    f.field_crew = command(
        f,
        "/crews",
        {
            "crew_code": "FIELD-CREW",
            "description": "Operational installation crew",
            "trade": "CIVIL",
            "vendor_id": f.chain["po"]["vendor_id"],
            "supervisor_user_id": f.users["field_supervisor"].id,
        },
    )
    f.field_equipment_ref = command(
        f,
        "/equipment-references",
        {
            "source_system": "EXTERNAL_ASSET_REFERENCE",
            "external_id": "EQP-001",
            "description": "Existing equipment identified externally, without creating an asset",
            "equipment_type": "EXTERNAL_EQUIPMENT",
        },
    )
    f.field_labor = command(
        f,
        "/labor",
        {
            "record_code": "FIELD-LABOR",
            "shift_id": f.field_shift["id"],
            "workfront_id": f.field_front["id"],
            "crew_id": f.field_crew["id"],
            "trade": "CIVIL",
            "headcount": 2,
            "regular_hours": "8",
            "overtime_hours": "1",
            "productive_hours": "7",
            "nonproductive_hours": "2",
            "document_references": [f.field_document_pin],
        },
    )
    f.field_equipment = command(
        f,
        "/equipment",
        {
            "record_code": "FIELD-EQUIPMENT",
            "equipment_id": f.field_equipment_ref["id"],
            "shift_id": f.field_shift["id"],
            "workfront_id": f.field_front["id"],
            "usage_type": "PRODUCTION",
            "operating_hours": "6",
            "idle_hours": "1",
            "standby_hours": "1",
            "downtime_hours": "0",
            "document_references": [f.field_document_pin],
        },
    )
    f.field_condition = command(
        f,
        "/conditions",
        {
            "condition_code": "FIELD-CONDITION",
            "condition_date": TODAY.isoformat(),
            "shift_id": f.field_shift["id"],
            "workfront_id": f.field_front["id"],
            "location_reference": front_data["location_reference"],
            "weather_condition": "CLEAR",
            "temperature": "24",
            "rainfall": "0",
            "wind": "2",
            "access_condition": "AVAILABLE",
            "site_condition": "Safe access reported as an observed condition",
            "source": "Supervisor field observation",
            "document_references": [f.field_document_pin],
        },
    )
    f.field_report_body = {
        "report_number": "FIELD-DAILY",
        "report_date": TODAY.isoformat(),
        "shift_id": f.field_shift["id"],
        "workfront_ids": [f.field_front["id"]],
        "reporting_party": "Site supervision",
        "weather": {"condition": "CLEAR"},
        "work_conditions": "Workfront operational observation",
        "comments": "No automatic Progress or Cost",
        "document_references": [f.field_document_pin],
    }
    f.field_report = command(f, "/daily-reports", f.field_report_body)
    return f


def approve_report(f):
    row = f.field_report
    for value, actor in (("submit", "field_reporter"), ("review", "field_supervisor"), ("approve", "field_approver")):
        row = action(f, "daily-reports", row, value, actor=actor)
    f.field_report = row
    assert row["status"] == "APPROVED"
    return row


def provider_reference(f, kind, identity):
    pin = expect(call(f, "GET", "/source", params={"source_type": kind, "source_id": identity}), 200)
    return {
        "source_type": kind,
        "source_id": pin["source_entity_id"],
        "source_version": pin["source_version"],
        "source_hash": pin["source_hash"],
    }


def production_body(f, **changes):
    """Capture after the actual AWP release using current provider pins."""
    allocations = expect(call(f, "GET", "/reference-targets", params={"target_kind": "MATERIAL_ALLOCATION"}), 200)[
        "items"
    ]
    allocation = next(item for item in allocations if item["facts"]["work_package_id"] == f.field_released_iwp["id"])
    body = {
        "production_code": "FIELD-INSTALLATION",
        "workfront_id": f.field_front["id"],
        "shift_id": f.field_shift["id"],
        "report_id": f.field_report["id"],
        "scope_item_id": f.scope_items[0]["id"],
        "plan_item_id": f.plan_items[0]["id"],
        "iwp_id": f.field_released_iwp["id"],
        "quantity": "2",
        "planned_quantity": "3",
        "uom": f.scope_items[0]["unit"],
        "production_type": "INSTALLED",
        "observed_at": datetime.now(UTC).isoformat(),
        "source_reference": "CDE governed installation observation",
        "engineering_reference": provider_reference(f, "IFC_RELEASE", f.ifc["id"]),
        "material_reference": provider_reference(f, "MATERIAL_ALLOCATION", allocation["source_entity_id"]),
        "document_reference": f.field_document_pin,
    }
    return body | changes


def create_verified_production(f, **changes):
    f.field_production_body = production_body(f, **changes)
    row = command(f, "/production", f.field_production_body)
    f.field_production = action(f, "production", row, "verify", actor="field_supervisor")
    return f.field_production
