"""Disposable Engineering validation on real O1 authorities and CDE."""

import os
from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from tests.awp_browser_fixture import create_awp_browser_fixture
from tests.forecast_release_fixture import create_forecast_fixture
from tests.operational_context_fixture import fixture_headers
from tests.test_scope_foundation_release import profile, success

from app.core.security import hash_password
from app.domain.models import AuthCredential, ProjectMembership, SecurityAccessAssignment, SecurityRole, UserAccount
from app.modules.awp.policy import DEFAULT_PROFILE as AWP_PROFILE
from app.modules.engineering_foundation.permissions import ensure_engineering_permissions
from app.modules.engineering_foundation.policy import DEFAULT_PROFILE

REASON = {"reason": "Isolated governed O2A Engineering validation"}
TODAY = datetime.now(UTC).date()


def request(f, method, path, *, payload=None, actor="preparer", version=None, key=None, params=None, files=None):
    headers = dict(f.headers[actor])
    if method != "GET":
        headers["Idempotency-Key"] = key or f"o2a-{uuid4()}"
    if version is not None:
        headers["If-Match"] = f'"{version}"'
    root = f"/api/v1/engineering/projects/{f.project_workspace_id}"
    return f.client.request(
        method,
        path if path.startswith("/api") else root + path,
        headers=headers,
        json=payload,
        params=params,
        files=files,
    )


def add_actor(db, f, name, role_code, *, organization=False):
    actor = UserAccount(
        tenant_id=f.tenant_id,
        email=f"{name}-{f.token}@o2a.test",
        full_name=f"O2A {name.replace('_', ' ').title()}",
        status="active",
    )
    db.add(actor)
    db.flush()
    role = db.scalar(select(SecurityRole).where(SecurityRole.tenant_id == f.tenant_id, SecurityRole.code == role_code))
    assert role
    db.add(
        SecurityAccessAssignment(
            tenant_id=f.tenant_id,
            subject_type="user",
            user_id=actor.id,
            role_id=role.id,
            scope_type="organization" if organization else "workspace",
            workspace_id=None if organization else f.project_workspace_id,
            granted_by_user_id=f.users["admin"].id,
            status="active",
        )
    )
    f.users[name] = actor
    f.headers[name] = fixture_headers(actor)


def cde_document(f, code, revision):
    root = f"/api/v1/projects/{f.legacy_project_id}"
    doc = success(
        request(
            f,
            "POST",
            root + "/documents",
            actor="admin",
            payload={
                "document_number": code,
                "revision": revision,
                "revision_date": TODAY.isoformat(),
                "linked_entity_type": "PROJECT",
                "linked_entity_id": f.legacy_project_id,
                "title": f"Isolated technical design {revision}",
                "doc_type": "Drawing",
                "discipline": "Mechanical",
                "confidentiality": "project",
                "uri": f"urn:o2a:{f.token}:{revision}",
            },
        ),
        200,
    )
    attachments = success(
        request(
            f,
            "POST",
            root + f"/documents/{doc['id']}/attachments",
            actor="admin",
            files={
                "file": (
                    f"{code}-{revision}.txt",
                    f"Isolated test drawing {f.token} revision {revision}".encode(),
                    "text/plain",
                )
            },
        ),
        200,
    )
    return doc, attachments[0]


def publish_engineering_profile(f, **changes):
    content = deepcopy(DEFAULT_PROFILE)
    content.update(changes)
    base = "/api/v1/engineering/admin/profiles"
    draft = success(
        request(
            f,
            "POST",
            base,
            actor="admin",
            payload={
                **REASON,
                "code": f"ENG-{uuid4().hex[:8]}",
                "name": "Engineering isolated policy",
                "content_json": content,
            },
        ),
        201,
    )
    return success(
        request(f, "POST", f"{base}/{draft['id']}/publish", actor="publisher", version=draft["version"], payload=REASON)
    )


def create_engineering_fixture(db, client, *, integrated=False, publish=True, credentials=False):
    assert os.getenv("PYPMIS_O2A_FIXTURE") == "disposable-only"
    assert db.bind.dialect.name == "postgresql" and db.bind.url.database in {"o2a", "o2a_browser"}
    f = create_forecast_fixture(db, client, real_model=True) if integrated else create_awp_browser_fixture(db, client)
    f.db = db
    workspace = f.workspaces["direct"]
    workspace.defaults_json = {
        **workspace.defaults_json,
        "enabled_modules": [*workspace.defaults_json["enabled_modules"], "engineering"],
    }
    ensure_engineering_permissions(db, f.tenant_id, f.users["admin"].id)
    ensure_engineering_permissions(db, f.foreign_tenant.id, f.users["foreign"].id)
    for label, role in {
        "preparer": "engineering_author",
        "reviewer": "engineering_reviewer",
        "checker": "engineering_checker",
        "approver": "engineering_approver",
        "releaser": "engineering_ifc_releaser",
        "awp_manager": "project_manager",
    }.items():
        add_actor(db, f, label, role)
    f.users["outsider"] = f.users["foreign"]
    f.headers["outsider"] = f.headers["foreign"]
    f.password = "O2a-disposable-only!"
    for label, user in f.users.items():
        if label == "outsider":
            continue
        if user.tenant_id == f.tenant_id:
            db.add(
                ProjectMembership(
                    tenant_id=f.tenant_id,
                    project_id=f.legacy_project_id,
                    user_id=user.id,
                    role="Control Manager" if label in {"admin", "publisher"} else "Executive Viewer",
                    can_configure=label in {"admin", "publisher"},
                    can_capture_progress=False,
                    can_capture_cost=False,
                )
            )
        if credentials:
            db.add(
                AuthCredential(
                    tenant_id=user.tenant_id,
                    user_id=user.id,
                    provider="local",
                    password_hash=hash_password(f.password),
                    is_active=True,
                )
            )
    db.commit()
    success(
        request(
            f,
            "POST",
            f"/api/v1/operational/projects/{f.project_workspace_id}/binding",
            actor="admin",
            version=0,
            payload={**REASON, "legacy_project_id": f.legacy_project_id},
        ),
        201,
    )
    f.document, f.attachment = cde_document(f, f"ENG-{f.token}", "A")
    f.successor_document, f.successor_attachment = cde_document(f, f"ENG-{f.token}", "B")
    if not integrated:
        f.awp_profile = profile(f, "/api/v1/awp", AWP_PROFILE)
    awp = f"/api/v1/awp/projects/{f.project_workspace_id}"
    f.awp_root = awp
    f.cwas = [
        success(
            request(
                f,
                "POST",
                awp + "/cwas",
                actor="admin",
                payload={
                    **REASON,
                    "code": f"ENG-{index}",
                    "name": f"Engineering CWA {index}",
                    "area": "North",
                },
            ),
            201,
        )
        for index in (1, 2)
    ]
    f.engineering_packages = {}
    for kind, count in (("EWP", 2), ("CWP", 1), ("IWP", 1)):
        rows = []
        for index in range(count):
            row = success(
                request(
                    f,
                    "POST",
                    awp + "/packages",
                    actor="admin",
                    payload={
                        **REASON,
                        "package_code": f"ENG-{kind}-{index}",
                        "name": f"Engineering validation {kind} {index}",
                        "package_type": kind,
                        "cwa_id": f.cwas[index]["id"],
                    },
                ),
                201,
            )
            mapped = success(
                request(
                    f,
                    "POST",
                    awp + f"/packages/{row['id']}/mappings",
                    actor="admin",
                    version=row["version"],
                    payload={**REASON, "target_kind": "PLAN", "target_id": f.plan_items[index]["id"]},
                ),
                201,
            )
            row = mapped["package"]
            for status, actor in (("PLANNED", "admin"), ("UNDER_REVIEW", "awp_manager")):
                row = success(
                    request(
                        f,
                        "POST",
                        awp + f"/packages/{row['id']}/transition",
                        actor=actor,
                        version=row["version"],
                        payload={**REASON, "status": status},
                    )
                )
            rows.append(row)
        f.engineering_packages[kind] = rows
    if publish:
        f.engineering_profile = publish_engineering_profile(f)
    return f


def deliverable_body(**changes):
    return {
        **REASON,
        "code": f"TECH-{uuid4().hex[:8]}",
        "title": "Controlled engineering deliverable",
        "discipline": "MECHANICAL",
        "deliverable_type": "DRAWING",
        "responsible_party": "Engineering Team",
        "area": "North",
        "planned_issue_date": TODAY.isoformat(),
        "current_forecast_date": TODAY.isoformat(),
        **changes,
    }


def revision_body(**changes):
    return {
        **REASON,
        "revision_code": "A",
        "purpose_of_issue": "FOR_CONSTRUCTION",
        "planned_issue_date": TODAY.isoformat(),
        "forecast_issue_date": TODAY.isoformat(),
        **changes,
    }


def draft(f, *, doc=True):
    parent = success(request(f, "POST", "/deliverables", payload=deliverable_body()), 201)
    row = success(request(f, "POST", f"/deliverables/{parent['id']}/revisions", payload=revision_body()), 201)
    if doc:
        row = link(f, row)
    return parent, row


def link(f, row, *, successor=False):
    doc, attach = (f.successor_document, f.successor_attachment) if successor else (f.document, f.attachment)
    return success(
        request(
            f,
            "POST",
            f"/revisions/{row['id']}/document",
            version=row["version"],
            payload={**REASON, "document_id": doc["id"], "attachment_id": attach["id"]},
        )
    )


def review(f, row, action, actor):
    return success(
        request(
            f,
            "POST",
            f"/revisions/{row['id']}/review-action",
            actor=actor,
            version=row["version"],
            payload={**REASON, "action": action},
        )
    )


def approve(f, row):
    for action, actor in (
        ("submit", "preparer"),
        ("start", "reviewer"),
        ("accept", "reviewer"),
        ("check", "checker"),
        ("approve", "approver"),
    ):
        row = review(f, row, action, actor)
    return row


def release(f, row, effective=TODAY):
    return success(
        request(
            f,
            "POST",
            f"/revisions/{row['id']}/ifc-release",
            actor="releaser",
            version=row["version"],
            payload={**REASON, "effective_date": effective.isoformat(), "release_reference": "O2A-SIGNED-ISSUE"},
        ),
        201,
    )
