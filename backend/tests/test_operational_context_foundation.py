"""O1A HTTP acceptance against a dedicated database and actual RBAC.

No dependency overrides, UI mocks, strategic authorization stubs or production
tenant mutations. PostgreSQL CI/release uses PYPMIS_TEST_DATABASE_URL; SQLite is
allowed only for fast developer feedback and is not claimed as release proof.
"""

from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from tests.operational_context_fixture import create_o1a_fixture

from app.database.session import SessionLocal, engine
from app.domain.models import (
    AdminConfiguration,
    EnterpriseWorkspace,
    Project,
    SecurityAccessAssignment,
    SecurityEvent,
    SecurityRole,
    SecurityRolePermission,
)
from app.main import app
from app.modules.operational_context.models import (
    OperationalContextCommand,
    OperationalProjectBinding,
    ProjectControlsPeriod,
)
from app.modules.operational_context.service import DEFAULT_PROFILE

ROOT = "/api/v1/operational"
REASON = {"reason": "Isolated governed O1A acceptance command", "notes": "No downstream domain snapshot"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as instance:
        yield instance


@pytest.fixture
def fixture(client):
    with SessionLocal() as db:
        result = create_o1a_fixture(db)
        result.client = client
        result.db = db
        yield result
        db.rollback()


def _request(f, method, path, *, actor="admin", payload=None, version=None, key=None):
    headers = dict(f.headers[actor])
    if method.upper() not in {"GET", "HEAD"}:
        headers["Idempotency-Key"] = key or f"o1a-{uuid4()}"
    if version is not None:
        headers["If-Match"] = f'"{version}"'
    return f.client.request(method, ROOT + path, headers=headers, json=payload)


def _project_path(f, suffix, project="direct"):
    return f"/projects/{f.workspaces[project].id}/{suffix}"


def _profile(f, *, content=None, publish=True):
    created = _request(
        f,
        "POST",
        "/admin/profiles",
        payload={
            "code": f"o1a-{uuid4().hex[:12]}",
            "name": "O1A governed acceptance profile",
            "content_json": deepcopy(DEFAULT_PROFILE) if content is None else content,
        },
    )
    assert created.status_code == 201, created.text
    row = created.json()
    if publish:
        published = _request(
            f, "POST", f"/admin/profiles/{row['id']}/publish", actor="publisher", version=row["version"], payload=REASON
        )
        assert published.status_code == 200, published.text
        row = published.json()
    return row


def _period_payload(**changes):
    payload = {
        **REASON,
        "period_code": f"W-O1A-{uuid4().hex[:8]}",
        "period_start": "2026-10-05",
        "period_end": "2026-10-11",
        "cutoff_at": "2026-10-11T18:00:00-05:00",
        "timezone": "America/Bogota",
        "schedule_data_date": "2026-10-08",
    }
    return payload | changes


def _open(f, **changes):
    response = _request(f, "POST", _project_path(f, "periods"), actor="manager", payload=_period_payload(**changes))
    assert response.status_code == 201, response.text
    return response.json()


def _transition(f, row, action, *, actor="manager", version=None, key=None):
    return _request(
        f,
        "POST",
        _project_path(f, f"periods/{row['id']}/{action}"),
        actor=actor,
        payload=REASON,
        version=row["version"] if version is None else version,
        key=key,
    )


def _published_period(f):
    _profile(f)
    row = _open(f)
    for action, actor in (("review", "manager"), ("close", "manager"), ("publish", "second_manager")):
        result = _transition(f, row, action, actor=actor)
        assert result.status_code == 200, result.text
        row = result.json()
    return row


def _code(response):
    detail = response.json().get("detail", {})
    return detail.get("code") if isinstance(detail, dict) else detail


def test_context_uses_canonical_identity_with_explicit_missing_binding(fixture):
    f = fixture
    _profile(f)
    response = _request(f, "GET", _project_path(f, "context"), actor="executive")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["project_workspace_id"] == f.workspaces["direct"].id
    assert result["project_workspace_id"] != f.legacy["primary"].id
    assert result["project_workspace_external_key"] == f.workspaces["direct"].external_key
    assert result["binding_state"] == "MISSING" and result["legacy_project_id"] is None
    assert result["governance_model"] == "DIRECT_INTERNAL"
    assert result["project_type"] == "CONSTRUCTION"
    assert result["authorization"]["authorized_for_operational_context"]
    assert not result["authorization"]["commitment_authorized"]
    assert "ACTIVE_IS_NOT_COMMITMENT_AUTHORITY" in result["warnings"]
    assert "period.publish" not in result["allowed_actions"]


def test_explicit_binding_create_idempotent_retry_and_unequal_ids(fixture):
    f = fixture
    key = f"binding-{uuid4()}"
    payload = REASON | {"legacy_project_id": f.legacy["primary"].id}
    first = _request(f, "POST", _project_path(f, "binding"), payload=payload, version=0, key=key)
    assert first.status_code == 201, first.text
    again = _request(f, "POST", _project_path(f, "binding"), payload=payload, version=0, key=key)
    assert again.status_code == 201 and again.json() == first.json()
    assert first.json()["project_workspace_id"] != first.json()["legacy_project_id"]
    assert first.json()["status"] == "ACTIVE"
    assert first.headers["ETag"] == '"1"'
    lookup = _request(f, "GET", _project_path(f, "binding"))
    assert len(lookup.json()["history"]) == 1


def test_binding_zero_legacy_is_a_deliberate_state_not_auto_creation(fixture):
    f = fixture
    before = f.db.scalar(select(func.count()).select_from(Project))
    result = _request(f, "POST", _project_path(f, "binding"), payload=REASON, version=0)
    assert result.status_code == 201, result.text
    assert result.json()["status"] == "NO_LEGACY_BINDING_REQUIRED"
    assert result.json()["legacy_project_id"] is None
    f.db.expire_all()
    assert f.db.scalar(select(func.count()).select_from(Project)) == before


def test_duplicate_canonical_binding_and_duplicate_legacy_binding_rejected(fixture):
    f = fixture
    payload = REASON | {"legacy_project_id": f.legacy["primary"].id}
    first = _request(f, "POST", _project_path(f, "binding"), payload=payload, version=0)
    assert first.status_code == 201
    duplicate = _request(f, "POST", _project_path(f, "binding"), payload=payload, version=1)
    assert duplicate.status_code == 409
    other = _request(f, "POST", _project_path(f, "binding", project="other_project"), payload=payload, version=0)
    assert other.status_code == 409 and _code(other) == "OPERATIONAL_PROJECT_BINDING_LEGACY_ALREADY_LINKED"


@pytest.mark.parametrize("legacy_name,status", [("foreign", 404), ("superseded", 409)])
def test_invalid_or_cross_tenant_legacy_binding_is_non_leaking(fixture, legacy_name, status):
    f = fixture
    result = _request(
        f,
        "POST",
        _project_path(f, "binding"),
        version=0,
        payload=REASON | {"legacy_project_id": f.legacy[legacy_name].id},
    )
    assert result.status_code == status, result.text
    assert _code(result) == "OPERATIONAL_PROJECT_BINDING_INVALID"
    assert _request(f, "GET", _project_path(f, "binding")).json()["state"] == "MISSING"


def test_binding_reconciliation_ambiguous_explicit_candidates_fail_closed(fixture):
    f = fixture
    for row in (f.legacy["primary"], f.legacy["second"]):
        row.configuration = {"enterprise_workspace_id": f.workspaces["direct"].id}
    f.db.commit()
    result = _request(
        f,
        "POST",
        _project_path(f, "binding/reconcile"),
        version=0,
        payload=REASON | {"source": "VERIFIED_EXISTING_RELATIONSHIP"},
    )
    assert result.status_code == 409 and _code(result) == "OPERATIONAL_PROJECT_BINDING_AMBIGUOUS"
    assert _request(f, "GET", _project_path(f, "binding")).json()["history"] == []


def test_binding_reconciliation_missing_trustworthy_candidate_fails_closed(fixture):
    f = fixture
    result = _request(
        f,
        "POST",
        _project_path(f, "binding/reconcile"),
        version=0,
        payload=REASON | {"source": "VERIFIED_EXISTING_RELATIONSHIP"},
    )
    assert result.status_code == 409 and _code(result) == "OPERATIONAL_PROJECT_BINDING_REQUIRED"


def test_binding_reconciliation_preserves_history_and_enforces_sod_etag(fixture):
    f = fixture
    _profile(f)
    first = _request(
        f,
        "POST",
        _project_path(f, "binding"),
        version=0,
        payload=REASON | {"legacy_project_id": f.legacy["primary"].id},
    )
    assert first.status_code == 201
    stale = _request(f, "POST", _project_path(f, "binding/reconcile"), actor="publisher", version=0, payload=REASON)
    assert stale.status_code == 412
    same_author = _request(f, "POST", _project_path(f, "binding/reconcile"), version=1, payload=REASON)
    assert same_author.status_code == 403 and _code(same_author) == "OPERATIONAL_BINDING_RECONCILIATION_SOD"
    key = f"reconcile-{uuid4()}"
    second = _request(
        f, "POST", _project_path(f, "binding/reconcile"), actor="publisher", version=1, payload=REASON, key=key
    )
    assert second.status_code == 201, second.text
    retry = _request(
        f, "POST", _project_path(f, "binding/reconcile"), actor="publisher", version=1, payload=REASON, key=key
    )
    assert retry.json() == second.json()
    history = _request(f, "GET", _project_path(f, "binding")).json()["history"]
    assert [row["status"] for row in history] == ["NO_LEGACY_BINDING_REQUIRED", "SUPERSEDED"]
    assert history[1]["effective_to"] is not None
    assert history[0]["revision"] == 2


@pytest.mark.parametrize("actor", ["executive", "planner", "manager", "unassigned"])
def test_binding_command_requires_duty_not_just_project_membership(fixture, actor):
    f = fixture
    result = _request(f, "POST", _project_path(f, "binding"), actor=actor, payload=REASON, version=0)
    assert result.status_code == 403, result.text


@pytest.mark.parametrize(
    "project,expected", [("direct", True), ("contractor", True), ("owner", False), ("inactive", False)]
)
def test_authorization_routes_do_not_fabricate_owner_authority(fixture, project, expected):
    f = fixture
    result = _request(f, "GET", _project_path(f, "authorization", project=project))
    assert result.status_code == 200, result.text
    decision = result.json()
    assert decision["authorized_for_operational_context"] is expected
    assert decision["commitment_authorized"] is False
    if project == "contractor":
        assert decision["authority_reference"].startswith("CTR-")
        assert "FID" not in decision["authority_source"]
    if project == "direct":
        assert decision["authority_reference"].startswith("INT-")
        assert decision["effective_date"] == "2026-10-01"
        assert decision["scope_context"]
    if project == "owner":
        assert "CAPITAL_OWNER_CURRENT_INVESTMENT_AUTHORIZATION_REQUIRED" in decision["blocking_conditions"]
    if project == "inactive":
        assert "OPERATIONAL_PROJECT_NOT_ACTIVE" in decision["blocking_conditions"]


@pytest.mark.parametrize("project", ["direct", "contractor"])
def test_non_owner_missing_source_authorization_blocks_operational_entry(fixture, project):
    f = fixture
    row = f.workspaces[project]
    metadata = deepcopy(row.defaults_json)
    metadata["_project"]["source_snapshot"] = {}
    row.defaults_json = metadata
    f.db.commit()
    result = _request(f, "GET", _project_path(f, "authorization", project=project))
    assert not result.json()["authorized_for_operational_context"]
    assert result.json()["blocking_conditions"]


def test_common_period_full_lifecycle_explicit_timezone_and_independent_data_date(fixture):
    f = fixture
    row = _published_period(f)
    assert row["status"] == "PUBLISHED" and row["version"] == 4
    assert row["timezone"] == "America/Bogota" and row["schedule_data_date"] == "2026-10-08"
    assert datetime.fromisoformat(row["cutoff_at"]).astimezone(UTC).isoformat() == "2026-10-11T23:00:00+00:00"
    snapshot = row["snapshot_json"]
    assert snapshot["publication_boundary"] == "PERIOD_HEADER_ONLY"
    assert snapshot["source_bundles"] == [] and snapshot["report_publication"] is False
    assert len(snapshot["header_hash"]) == 64
    assert not {"EAC", "ETC", "CPI", "SPI", "cost_snapshot", "schedule_snapshot", "progress_snapshot"} & snapshot.keys()
    assert row["opened_by"] != row["published_by"]
    history = _request(f, "GET", _project_path(f, "periods"), actor="executive")
    assert history.json()["total"] == 1 and history.json()["items"][0]["status"] == "PUBLISHED"


def test_period_review_close_publish_permissions_and_sod(fixture):
    f = fixture
    _profile(f)
    row = _open(f)
    denied = _transition(f, row, "review", actor="executive")
    assert denied.status_code == 403
    row = _transition(f, row, "review", actor="planner").json()
    denied = _transition(f, row, "close", actor="planner")
    assert denied.status_code == 403
    row = _transition(f, row, "close").json()
    denied = _transition(f, row, "publish", actor="manager")
    assert denied.status_code == 403 and _code(denied) == "OPERATIONAL_PERIOD_SEPARATION_OF_DUTIES"
    published = _transition(f, row, "publish", actor="second_manager")
    assert published.status_code == 200


def test_invalid_period_transition_and_stale_etag_rejected(fixture):
    f = fixture
    _profile(f)
    row = _open(f)
    assert _transition(f, row, "publish", actor="second_manager").status_code == 409
    row = _transition(f, row, "review").json()
    assert _transition(f, row, "close", version=1).status_code == 412
    assert _transition(f, row, "review").status_code == 409


def test_open_period_and_close_publish_retries_are_idempotent(fixture):
    f = fixture
    _profile(f)
    key = f"open-{uuid4()}"
    payload = _period_payload()
    first = _request(f, "POST", _project_path(f, "periods"), actor="manager", payload=payload, key=key)
    assert first.status_code == 201
    retry = _request(f, "POST", _project_path(f, "periods"), actor="manager", payload=payload, key=key)
    assert retry.json() == first.json()
    row = _transition(f, first.json(), "review").json()
    for action, actor in (("close", "manager"), ("publish", "second_manager")):
        key = f"{action}-{uuid4()}"
        original = _transition(f, row, action, actor=actor, key=key)
        assert original.status_code == 200, original.text
        retry = _transition(f, row, action, actor=actor, key=key)
        assert retry.status_code == 200 and retry.json() == original.json()
        row = original.json()


def test_duplicate_active_period_and_reused_key_different_payload_rejected(fixture):
    f = fixture
    _profile(f)
    key = f"open-{uuid4()}"
    payload = _period_payload()
    assert _request(f, "POST", _project_path(f, "periods"), payload=payload, key=key).status_code == 201
    other = _request(f, "POST", _project_path(f, "periods"), payload=_period_payload())
    assert other.status_code == 409 and _code(other) == "OPERATIONAL_ACTIVE_PERIOD_EXISTS"
    reused = _request(f, "POST", _project_path(f, "periods"), payload=payload | {"notes": "Different request"}, key=key)
    assert reused.status_code == 409 and _code(reused) == "IDEMPOTENCY_KEY_REUSED"


@pytest.mark.parametrize(
    "changes",
    [
        {"timezone": "UTC"},
        {"timezone": "Not/AZone"},
        {"cutoff_at": "2026-10-11T18:00:00"},
        {"cutoff_at": "2026-10-11T18:00:00+00:00"},
        {"cutoff_at": "2026-10-10T18:00:00-05:00"},
        {"period_end": "2026-10-10"},
        {"period_end": "2026-10-04"},
    ],
)
def test_invalid_calendar_timezone_cutoff_and_cadence_rejected(fixture, changes):
    f = fixture
    _profile(f)
    response = _request(f, "POST", _project_path(f, "periods"), payload=_period_payload(**changes))
    assert response.status_code == 422, response.text


@pytest.mark.parametrize(
    "cadence,start,end",
    [
        ("biweekly", "2026-10-05", "2026-10-18"),
        ("monthly", "2026-10-01", "2026-10-31"),
        ("custom", "2026-10-03", "2026-10-21"),
    ],
)
def test_supported_configurable_cadences(fixture, cadence, start, end):
    f = fixture
    content = deepcopy(DEFAULT_PROFILE)
    content["calendar"]["cadence"] = cadence
    _profile(f, content=content)
    row = _open(f, period_start=start, period_end=end, cutoff_at=f"{end}T18:00:00-05:00")
    assert row["status"] == "OPEN" and row["period_end"] == end


def test_published_header_immutable_and_reopen_creates_new_revision(fixture):
    f = fixture
    old = _published_period(f)
    prior_hash = old["snapshot_json"]["header_hash"]
    replay_transition = _transition(f, old, "review")
    assert replay_transition.status_code == 409
    revised = _transition(f, old, "reopen")
    assert revised.status_code == 200, revised.text
    new = revised.json()
    assert new["id"] != old["id"] and new["revision"] == 2 and new["status"] == "OPEN"
    assert new["reopen_parent_id"] == old["id"]
    history = _request(f, "GET", _project_path(f, "periods")).json()["items"]
    published = next(row for row in history if row["id"] == old["id"])
    assert published["snapshot_json"]["header_hash"] == prior_hash and published["version"] == old["version"]
    with SessionLocal() as db:
        row = db.get(ProjectControlsPeriod, old["id"])
        row.notes = "Forbidden late edit"
        with pytest.raises(ValueError, match="immutable"):
            db.flush()
        db.rollback()


def test_profile_draft_editable_stale_etag_rejected_and_publish_sod(fixture):
    f = fixture
    row = _profile(f, publish=False)
    content = deepcopy(row["content_json"])
    content["lookahead_default_days"] = 28
    stale = _request(
        f, "PUT", f"/admin/profiles/{row['id']}", payload={"name": row["name"], "content_json": content}, version=2
    )
    assert stale.status_code == 412
    edited = _request(
        f, "PUT", f"/admin/profiles/{row['id']}", payload={"name": row["name"], "content_json": content}, version=1
    )
    assert edited.status_code == 200, edited.text
    same_actor = _request(f, "POST", f"/admin/profiles/{row['id']}/publish", payload=REASON, version=2)
    assert same_actor.status_code == 403 and _code(same_actor) == "OPERATIONAL_PROFILE_PUBLICATION_SOD"
    published = _request(
        f, "POST", f"/admin/profiles/{row['id']}/publish", actor="publisher", payload=REASON, version=2
    )
    assert published.status_code == 200 and published.json()["status"] == "published"


def test_published_policy_immutable_successor_draft_and_effective_dating(fixture):
    f = fixture
    old = _profile(f)
    denied = _request(
        f,
        "PUT",
        f"/admin/profiles/{old['id']}",
        payload={"name": old["name"], "content_json": old["content_json"]},
        version=old["version"],
    )
    assert denied.status_code == 409 and _code(denied) == "PUBLISHED_OPERATIONAL_PROFILE_IMMUTABLE"
    successor = _request(f, "POST", f"/admin/profiles/{old['id']}/successor", payload=REASON, version=old["version"])
    assert successor.status_code == 201, successor.text
    draft = successor.json()
    assert draft["status"] == "draft" and draft["revision"] == 2
    content = deepcopy(draft["content_json"])
    content["effective_from"] = "2099-01-01T00:00:00Z"
    updated = _request(
        f, "PUT", f"/admin/profiles/{draft['id']}", payload={"name": draft["name"], "content_json": content}, version=1
    )
    assert updated.status_code == 200
    assert (
        _request(
            f, "POST", f"/admin/profiles/{draft['id']}/publish", actor="publisher", payload=REASON, version=2
        ).status_code
        == 200
    )
    current = _request(f, "GET", _project_path(f, "context")).json()
    assert current["operational_profile"]["id"] == old["id"]


@pytest.mark.parametrize(
    "applicability",
    [
        {"governance_models": ["CONTRACTOR_DELIVERY"], "project_types": ["*"]},
        {"governance_models": ["*"], "project_types": ["MAINTENANCE"]},
    ],
)
def test_policy_governance_and_project_type_applicability(fixture, applicability):
    f = fixture
    content = deepcopy(DEFAULT_PROFILE)
    content["applicability"] = applicability
    _profile(f, content=content)
    result = _request(f, "GET", _project_path(f, "context")).json()
    assert result["operational_profile"] is None
    assert "PUBLISHED_OPERATIONAL_PROFILE_REQUIRED" in result["blocking_conditions"]


def test_historical_period_retains_resolved_policy_revision(fixture):
    f = fixture
    old_profile = _profile(f)
    period = _open(f)
    successor = _request(
        f, "POST", f"/admin/profiles/{old_profile['id']}/successor", payload=REASON, version=old_profile["version"]
    ).json()
    published = _request(
        f,
        "POST",
        f"/admin/profiles/{successor['id']}/publish",
        actor="publisher",
        payload=REASON,
        version=successor["version"],
    )
    assert published.status_code == 200
    current = _request(f, "GET", _project_path(f, "context")).json()
    assert current["effective_policy_revision"] == 2
    history = _request(f, "GET", _project_path(f, "periods")).json()["items"][0]
    assert history["configuration_id"] == old_profile["id"]
    assert history["source_configuration_revision"] == period["source_configuration_revision"] == 1
    assert history["source_configuration_hash"] == old_profile["content_hash"]


@pytest.mark.parametrize(
    "actor", ["manager", "planner", "cost_controller", "progress_engineer", "executive", "project_admin", "unassigned"]
)
def test_user_cannot_access_or_edit_admin_profile_configuration(fixture, actor):
    f = fixture
    assert _request(f, "GET", "/admin/profiles", actor=actor).status_code == 403
    assert (
        _request(
            f,
            "POST",
            "/admin/profiles",
            actor=actor,
            payload={"code": "deny", "name": "Forbidden", "content_json": DEFAULT_PROFILE},
        ).status_code
        == 403
    )


def test_wrong_tenant_wrong_project_and_unauthorized_actor_denied(fixture):
    f = fixture
    assert _request(f, "GET", _project_path(f, "context"), actor="foreign").status_code == 404
    assert _request(f, "GET", _project_path(f, "context", project="foreign")).status_code == 404
    assert _request(f, "GET", _project_path(f, "context", project="other_project"), actor="manager").status_code == 403
    assert _request(f, "GET", _project_path(f, "context"), actor="unassigned").status_code == 403
    _profile(f)
    row = _open(f)
    cross = _request(
        f, "POST", _project_path(f, f"periods/{row['id']}/review", project="other_project"), payload=REASON, version=1
    )
    assert cross.status_code == 404


def test_all_new_get_routes_have_no_business_state_or_security_event_writes(fixture):
    f = fixture
    _profile(f)
    _open(f)
    tables = [
        AdminConfiguration,
        EnterpriseWorkspace,
        Project,
        ProjectControlsPeriod,
        OperationalProjectBinding,
        OperationalContextCommand,
        SecurityEvent,
        SecurityAccessAssignment,
        SecurityRole,
        SecurityRolePermission,
    ]

    def counts():
        from app.modules.basic_data.service import _hash, _json

        with SessionLocal() as db:
            return {
                model.__tablename__: _hash(
                    _json(
                        [
                            {column.name: getattr(row, column.name) for column in model.__table__.columns}
                            for row in db.scalars(
                                select(model).where(model.tenant_id == f.tenant_id).order_by(model.id)
                            )
                        ]
                    )
                )
                for model in tables
            }

    before = counts()
    for suffix in ("context", "binding", "authorization", "periods"):
        assert _request(f, "GET", _project_path(f, suffix)).status_code == 200
    assert _request(f, "GET", "/admin/profiles").status_code == 200
    assert _request(f, "GET", "/options").status_code == 200
    assert counts() == before


def test_audit_events_cover_binding_policy_and_period_commands(fixture):
    f = fixture
    _published_period(f)
    assert _request(f, "POST", _project_path(f, "binding"), version=0, payload=REASON).status_code == 201
    with SessionLocal() as db:
        events = set(db.scalars(select(SecurityEvent.event_type).where(SecurityEvent.tenant_id == f.tenant_id)))
    assert {
        "operational.profile.published",
        "operational.binding.created",
        "operational.period.opened",
        "operational.period.review_started",
        "operational.period.closed",
        "operational.period.published",
    } <= events


def test_postgresql_indexes_and_immutable_triggers_exist_when_postgresql():
    if engine.dialect.name != "postgresql":
        pytest.skip("PostgreSQL-only DDL evidence; SQLite does not qualify")
    with engine.connect() as connection:
        indexes = set(
            connection.scalars(
                text(
                    "SELECT indexname FROM pg_indexes WHERE schemaname=current_schema() AND tablename IN ('operational_project_bindings','project_controls_periods')"
                )
            )
        )
        assert {
            "uq_operational_binding_active_workspace",
            "uq_operational_binding_active_legacy",
            "ix_project_controls_period_lookup",
        } <= indexes
        triggers = set(
            connection.scalars(
                text(
                    "SELECT tgname FROM pg_trigger WHERE NOT tgisinternal AND tgrelid IN ('project_controls_periods'::regclass,'admin_configurations'::regclass)"
                )
            )
        )
        assert triggers, "Additive PostgreSQL immutability guards must be installed by migration"


def test_explicit_binding_revocation_keeps_immutable_history(fixture):
    f = fixture
    _profile(f)
    created = _request(
        f,
        "POST",
        _project_path(f, "binding"),
        payload=REASON | {"legacy_project_id": f.legacy["primary"].id},
        version=0,
    )
    assert created.status_code == 201
    same_actor = _request(f, "POST", _project_path(f, "binding/revoke"), payload=REASON, version=1)
    assert same_actor.status_code == 403
    revoked = _request(f, "POST", _project_path(f, "binding/revoke"), actor="publisher", payload=REASON, version=1)
    assert revoked.status_code == 200, revoked.text
    result = _request(f, "GET", _project_path(f, "binding")).json()
    assert result["state"] == "REVOKED" and result["history"][0]["effective_to"]
    with SessionLocal() as db:
        row = db.get(OperationalProjectBinding, created.json()["id"])
        row.reason = "Forbidden rewritten binding history"
        with pytest.raises(ValueError, match="immutable"):
            db.flush()
        db.rollback()


def test_legacy_material_command_requires_bound_canonical_context(fixture):
    from app.domain.models import WBS, ProjectMembership

    f = fixture
    _profile(f)
    with SessionLocal() as db:
        db.add(
            ProjectMembership(
                tenant_id=f.tenant_id,
                project_id=f.legacy["primary"].id,
                user_id=f.users["admin"].id,
                role="Project Administrator",
                can_configure=True,
            )
        )
        db.commit()
    payload = {"code": "O1A-GUARDED", "name": "Explicitly bound legacy source", "level": 1}
    route = f"/api/v1/projects/{f.legacy['primary'].id}/wbs"
    missing = f.client.post(route, headers=f.headers["admin"], json=payload)
    assert missing.status_code == 409 and _code(missing) == "OPERATIONAL_PROJECT_BINDING_REQUIRED", missing.text
    binding = _request(
        f,
        "POST",
        _project_path(f, "binding"),
        version=0,
        payload=REASON | {"legacy_project_id": f.legacy["primary"].id},
    )
    assert binding.status_code == 201
    created = f.client.post(route, headers=f.headers["admin"], json=payload)
    assert created.status_code == 200, created.text
    assert created.json()["code"] == payload["code"]
    # WBSOut deliberately omits persistence scoping fields. Prove the material
    # result in storage rather than inventing an extra response contract.
    with SessionLocal() as db:
        persisted = db.get(WBS, created.json()["id"])
        assert persisted is not None
        assert persisted.tenant_id == f.tenant_id
        assert persisted.project_id == f.legacy["primary"].id
        assert persisted.project_id != f.workspaces["direct"].id
        assert persisted.code == payload["code"]


def test_anonymous_background_commands_fail_closed_before_database_write():
    from fastapi import HTTPException

    from app.workers.tasks import run_control_cycle, run_daily_control_core

    with pytest.raises(HTTPException) as denied:
        run_control_cycle.run(999_999_999, 999_999_998)
    assert denied.value.status_code == 403
    assert denied.value.detail["code"] == "OPERATIONAL_EXECUTION_ACTOR_REQUIRED"
    result = run_daily_control_core.run()
    assert result["processed"] == 0 and result["status"] == "skipped"
    assert result["reason_code"] == "OPERATIONAL_EXECUTION_ACTOR_REQUIRED"


def test_postgresql_raw_sql_cannot_mutate_published_headers_or_profiles(fixture):
    from sqlalchemy.exc import DBAPIError

    if engine.dialect.name != "postgresql":
        pytest.skip("Requires real PostgreSQL immutable triggers")
    f = fixture
    period = _published_period(f)
    for statement, parameters in (
        ("UPDATE project_controls_periods SET notes='Forbidden bypass' WHERE id=:id", {"id": period["id"]}),
        ("DELETE FROM project_controls_periods WHERE id=:id", {"id": period["id"]}),
        ("UPDATE admin_configurations SET name='Forbidden bypass' WHERE id=:id", {"id": period["configuration_id"]}),
    ):
        with pytest.raises(DBAPIError, match="immutable"):
            with engine.begin() as connection:
                connection.execute(text(statement), parameters)


def test_postgresql_raw_constraint_rejects_duplicate_active_bindings(fixture):
    from sqlalchemy.exc import IntegrityError

    if engine.dialect.name != "postgresql":
        pytest.skip("Requires actual PostgreSQL unique active binding constraints")
    f = fixture
    first = _request(
        f,
        "POST",
        _project_path(f, "binding"),
        version=0,
        payload=REASON | {"legacy_project_id": f.legacy["primary"].id},
    )
    assert first.status_code == 201
    with SessionLocal() as db:
        db.add(
            OperationalProjectBinding(
                tenant_id=f.tenant_id,
                project_workspace_id=f.workspaces["direct"].id,
                legacy_project_id=f.legacy["second"].id,
                status="ACTIVE",
                revision=2,
                version=2,
                source="CONTROLLED_RECONCILIATION",
                reason="Adversarial duplicate canonical binding",
                created_by=f.users["admin"].id,
                validated_by=f.users["publisher"].id,
            )
        )
        with pytest.raises(IntegrityError, match="uq_operational_binding_active_workspace"):
            db.flush()
        db.rollback()


@pytest.mark.parametrize("project", ["direct", "contractor"])
@pytest.mark.parametrize(
    "field,value,code",
    [
        ("authorization_effective_date", "2099-01-01", "OPERATIONAL_AUTHORIZATION_NOT_YET_EFFECTIVE"),
        ("authorization_valid_until", "2000-01-01", "OPERATIONAL_AUTHORIZATION_EXPIRED"),
        ("authorization_effective_date", "invalid-date", "OPERATIONAL_AUTHORIZATION_DATE_INVALID"),
    ],
)
def test_non_owner_authorization_date_boundaries_fail_closed(fixture, project, field, value, code):
    f = fixture
    row = f.workspaces[project]
    content = deepcopy(row.defaults_json)
    content["_project"]["source_snapshot"][field] = value
    row.defaults_json = content
    f.db.commit()
    result = _request(f, "GET", _project_path(f, "authorization", project=project))
    assert result.status_code == 200
    assert not result.json()["authorized_for_operational_context"]
    assert code in result.json()["blocking_conditions"]
    binding = _request(f, "POST", _project_path(f, "binding", project=project), payload=REASON, version=0)
    assert binding.status_code == 409 and _code(binding) == code


def test_published_policy_required_setup_and_binding_are_command_preconditions(fixture):
    f = fixture
    content = deepcopy(DEFAULT_PROFILE)
    content["binding_policy"]["legacy_binding_required"] = True
    content["required_operational_setup"] = ["source_mapping_verified"]
    _profile(f, content=content)
    context = _request(f, "GET", _project_path(f, "context")).json()
    assert "OPERATIONAL_PROJECT_BINDING_REQUIRED" in context["blocking_conditions"]
    assert "REQUIRED_OPERATIONAL_SETUP:source_mapping_verified" in context["blocking_conditions"]
    blocked = _request(f, "POST", _project_path(f, "periods"), payload=_period_payload())
    assert blocked.status_code == 409 and _code(blocked) == "OPERATIONAL_PROJECT_BINDING_REQUIRED"
    binding = _request(
        f,
        "POST",
        _project_path(f, "binding"),
        payload=REASON | {"legacy_project_id": f.legacy["primary"].id},
        version=0,
    )
    assert binding.status_code == 201
    blocked = _request(f, "POST", _project_path(f, "periods"), payload=_period_payload())
    assert blocked.status_code == 409 and _code(blocked) == "REQUIRED_OPERATIONAL_SETUP:source_mapping_verified"
    # Explicit pre-existing setup reference supplied by an isolated fixture, not
    # a fabricated O1B baseline or a new generic public configuration mutation.
    metadata = deepcopy(f.workspaces["direct"].defaults_json)
    metadata["_project"]["operational_setup"] = {"source_mapping_verified": True}
    f.workspaces["direct"].defaults_json = metadata
    f.db.commit()
    assert _request(f, "POST", _project_path(f, "periods"), payload=_period_payload()).status_code == 201


def test_policy_workspace_specificity_and_tenant_scope_are_enforced(fixture):
    f = fixture
    inherited = _profile(f)
    content = deepcopy(DEFAULT_PROFILE)
    content["scope"] = {"type": "workspace", "workspace_id": f.workspaces["direct"].id}
    specific = _profile(f, content=content)
    direct = _request(f, "GET", _project_path(f, "context")).json()
    contractor = _request(f, "GET", _project_path(f, "context", project="contractor")).json()
    assert direct["operational_profile"]["id"] == specific["id"]
    assert contractor["operational_profile"]["id"] == inherited["id"]
    content["scope"]["workspace_id"] = f.workspaces["foreign"].id
    foreign = _request(
        f,
        "POST",
        "/admin/profiles",
        payload={"code": f"wrong-{uuid4().hex[:8]}", "name": "Wrong tenant scope", "content_json": content},
    )
    assert foreign.status_code == 422


def test_read_only_executive_cannot_use_legacy_configurator_flag_to_bypass_context(fixture):
    from app.domain.models import ProjectMembership

    f = fixture
    _profile(f)
    bound = _request(
        f,
        "POST",
        _project_path(f, "binding"),
        version=0,
        payload=REASON | {"legacy_project_id": f.legacy["primary"].id},
    )
    assert bound.status_code == 201
    with SessionLocal() as db:
        db.add(
            ProjectMembership(
                tenant_id=f.tenant_id,
                project_id=f.legacy["primary"].id,
                user_id=f.users["executive"].id,
                role="Historical Configurator",
                can_configure=True,
            )
        )
        db.commit()
    response = f.client.post(
        f"/api/v1/projects/{f.legacy['primary'].id}/wbs",
        headers=f.headers["executive"],
        json={"code": "NO-BYPASS", "name": "Must remain denied", "level": 1},
    )
    assert response.status_code == 403, response.text


@pytest.mark.parametrize(
    "actor,can_open,can_close",
    [
        ("project_admin", True, False),
        ("manager", True, True),
        ("second_manager", True, True),
        ("planner", True, False),
        ("cost_controller", True, False),
        ("progress_engineer", False, False),
        ("executive", False, False),
    ],
)
def test_operational_duty_permissions_visible_without_overbroad_roles(fixture, actor, can_open, can_close):
    f = fixture
    _profile(f)
    result = _request(f, "GET", _project_path(f, "context"), actor=actor)
    assert result.status_code == 200
    actions = result.json()["allowed_actions"]
    assert ("period.open" in actions) is can_open
    assert ("period.close" in actions) is can_close
    assert "admin.configure" not in actions
