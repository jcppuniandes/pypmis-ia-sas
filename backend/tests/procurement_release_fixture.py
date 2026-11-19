"""Disposable Project fixture from real O1 and Engineering authority commands."""

import os
from copy import deepcopy

from tests.engineering_release_fixture import add_actor, approve, create_engineering_fixture, draft, release, request
from tests.o2b_close_isolation import is_close_consumer_database
from tests.test_scope_foundation_release import success

from app.core.security import hash_password
from app.domain.models import AuthCredential, ProjectMembership
from app.modules.procurement_foundation.permissions import ensure_procurement_permissions
from app.modules.procurement_foundation.policy import DEFAULT_PROFILE

REASON = {"reason": "Controlled O2B validation in a disposable Project"}
ROLES = {
    "buyer": "procurement_buyer",
    "req_approver": "procurement_requisition_approver",
    "rfq_issuer": "procurement_rfq_issuer",
    "technical": "procurement_technical_evaluator",
    "commercial": "procurement_commercial_evaluator",
    "award_approver": "procurement_award_approver",
    "po_approver": "procurement_po_approver",
    "material": "procurement_materials_controller",
    "inspector": "procurement_inspector",
    "acceptor": "procurement_acceptor",
    "logistician": "procurement_logistician",
    "receiver": "procurement_receiver",
    "procurement_publisher": "procurement_publisher",
}


def call(f, method, path, *, actor="buyer", payload=None, version=None, key=None, params=None):
    full_path = path if path.startswith("/api") else f"/api/v1/procurement/projects/{f.project_workspace_id}{path}"
    return request(f, method, full_path, actor=actor, payload=payload, version=version, key=key, params=params)


def create_procurement_fixture(db, client, *, publish=True, credentials=False, integrated=False):
    assert is_close_consumer_database(db) or (
        os.getenv("PYPMIS_O2B_FIXTURE") == "disposable-only"
        and db.bind.dialect.name == "postgresql"
        and db.bind.url.database in {"o2b", "o2b_browser"}
        and not integrated
    )
    f = create_engineering_fixture(db, client, credentials=credentials, integrated=integrated)
    workspace = f.workspaces["direct"]
    workspace.defaults_json = {
        **workspace.defaults_json,
        "enabled_modules": [*workspace.defaults_json["enabled_modules"], "procurement"],
    }
    ensure_procurement_permissions(db, f.tenant_id, f.users["admin"].id)
    ensure_procurement_permissions(db, f.foreign_tenant.id, f.users["foreign"].id)
    for label, role in ROLES.items():
        add_actor(db, f, label, role, organization=label == "procurement_publisher")
        actor = f.users[label]
        db.add(
            ProjectMembership(
                tenant_id=f.tenant_id,
                project_id=f.legacy_project_id,
                user_id=actor.id,
                role="Executive Viewer",
                can_configure=label == "procurement_publisher",
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
    f.deliverable, revision = draft(f)
    result = release(f, approve(f, revision))
    f.ifc = result["release"]
    f.engineering_revision = result
    f.pwp = success(
        request(
            f,
            "POST",
            f.awp_root + "/packages",
            actor="admin",
            payload={
                **REASON,
                "package_code": "PWP-O2B",
                "package_type": "PWP",
                "name": "Governed Procurement work package",
                "cwa_id": f.cwas[0]["id"],
            },
        ),
        201,
    )
    f.iwp = f.engineering_packages["IWP"][0]
    f.policy = {**deepcopy(DEFAULT_PROFILE), "require_engineering_ifc": True}
    if publish:
        admin = "/api/v1/procurement/admin/profiles"
        row = success(
            call(
                f,
                "POST",
                admin,
                actor="admin",
                payload={
                    **REASON,
                    "code": "O2B-CONTROLLED",
                    "name": "Procurement validation profile",
                    "content_json": f.policy,
                },
            ),
            201,
        )
        f.procurement_profile = success(
            call(
                f,
                "POST",
                f"{admin}/{row['id']}/publish",
                actor="procurement_publisher",
                version=row["version"],
                payload=REASON,
            )
        )
    return f
