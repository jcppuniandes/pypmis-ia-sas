"""PostgreSQL-only hardening checks for Gate 07D release validation."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from tests.test_portfolio_planning_gate07d import _approved_decision, _target_portfolio
from tests.test_project_proposal_gate07b import _headers

from app.database.session import SessionLocal, engine
from app.domain.models import AdminConfiguration, EnterpriseWorkspace, SecurityEvent, UserAccount
from app.main import app
from app.modules.portfolio_planning.models import PortfolioProjectMembership
from app.modules.portfolio_planning.schemas import PortfolioMembershipCreateIn, StrategicPlanningCreateIn
from app.modules.portfolio_planning.service import DEFAULT_CONFIGURATION, PortfolioPlanningService, _hash
from app.modules.project_creation.models import ProjectCreationRequest
from app.modules.project_creation.service import ProjectCreationService

pytestmark = pytest.mark.skipif(engine.dialect.name != "postgresql", reason="PostgreSQL concurrency required")


def _actor_ids() -> tuple[int, int, int]:
    with SessionLocal() as db:
        admin = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
        assert admin is not None
        approver = db.scalar(
            select(UserAccount).where(
                UserAccount.tenant_id == admin.tenant_id,
                UserAccount.id != admin.id,
                UserAccount.status == "active",
            )
        )
        assert approver is not None
        return admin.tenant_id, admin.id, approver.id


def _payload(decision_id: int, tenant_id: int, actor_id: int) -> StrategicPlanningCreateIn:
    with SessionLocal() as db:
        planning = PortfolioPlanningService(db, tenant_id, actor_id, None)
        preview = planning.preview(decision_id)
        parent_id = int(preview.default_project_parent["id"])
        options = ProjectCreationService(db, tenant_id, actor_id).options(parent_id)
        project_types = options.classifications["project-type"]
        assert project_types
        return StrategicPlanningCreateIn(
            strategic_gate_decision_id=decision_id,
            project_parent_workspace_id=parent_id,
            project_template_config_id=int(preview.template_options[0]["id"]),
            project_manager_user_id=int(preview.project_manager_options[0]["id"]),
            project_type=str(project_types[0]["code"]),
            expected_decision_hash=preview.source_decision_hash,
            expected_readiness_hash=preview.source_readiness_hash,
        )


def _approve_request(request_id: int, tenant_id: int, requestor_id: int, approver_id: int) -> None:
    with SessionLocal() as db:
        requestor = ProjectCreationService(db, tenant_id, requestor_id)
        request = db.get(ProjectCreationRequest, request_id)
        assert request is not None
        submitted = requestor.submit(request_id, request.revision_version)
        reviewed = requestor.start_review(request_id, submitted.revision_version)
        approved = ProjectCreationService(db, tenant_id, approver_id).approve(request_id, reviewed.revision_version)
        assert approved.state == "approved"


def test_concurrent_strategic_create_and_materialize_are_idempotent(monkeypatch: pytest.MonkeyPatch) -> None:
    with TestClient(app) as client:
        decision = _approved_decision(client, _headers(client))
    tenant_id, actor_id, approver_id = _actor_ids()
    payload = _payload(decision["id"], tenant_id, actor_id)

    original_lookup = PortfolioPlanningService._request_for_decision
    barrier = Barrier(2)
    lookup_lock = Lock()
    synchronized_lookups = 0

    def synchronized_lookup(self: PortfolioPlanningService, decision_id: int):
        nonlocal synchronized_lookups
        result = original_lookup(self, decision_id)
        should_wait = False
        if result is None:
            with lookup_lock:
                if synchronized_lookups < 2:
                    synchronized_lookups += 1
                    should_wait = True
        if should_wait:
            barrier.wait(timeout=15)
        return result

    monkeypatch.setattr(PortfolioPlanningService, "_request_for_decision", synchronized_lookup)

    def create_once() -> int:
        with SessionLocal() as db:
            result = PortfolioPlanningService(db, tenant_id, actor_id, None).create(payload)
            assert result.project_creation_request is not None
            return result.project_creation_request.id

    with ThreadPoolExecutor(max_workers=2) as executor:
        request_ids = list(executor.map(lambda _value: create_once(), range(2)))
    assert len(set(request_ids)) == 1
    request_id = request_ids[0]
    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count(ProjectCreationRequest.id)).where(
                    ProjectCreationRequest.tenant_id == tenant_id,
                    ProjectCreationRequest.strategic_gate_decision_id == decision["id"],
                )
            )
            == 1
        )

    _approve_request(request_id, tenant_id, actor_id, approver_id)
    materialize_barrier = Barrier(2)

    def materialize_once() -> tuple[str, int]:
        with SessionLocal() as db:
            materialize_barrier.wait(timeout=15)
            result = ProjectCreationService(db, tenant_id, actor_id).materialize(request_id)
            return result.result, result.materialized_workspace_id

    with ThreadPoolExecutor(max_workers=2) as executor:
        materializations = list(executor.map(lambda _value: materialize_once(), range(2)))
    assert {item[0] for item in materializations} == {"CREATED", "ALREADY_CREATED"}
    assert len({item[1] for item in materializations}) == 1
    project_id = materializations[0][1]
    with SessionLocal() as db:
        request = db.get(ProjectCreationRequest, request_id)
        assert request is not None
        assert request.materialized_workspace_id == project_id
        assert (
            db.scalar(
                select(func.count(PortfolioProjectMembership.id)).where(
                    PortfolioProjectMembership.project_workspace_id == project_id,
                    PortfolioProjectMembership.is_target_portfolio.is_(True),
                    PortfolioProjectMembership.status == "ACTIVE",
                )
            )
            == 1
        )


def test_concurrent_project_numbers_record_codes_and_membership_are_unique() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        decisions = [_approved_decision(client, headers), _approved_decision(client, headers)]
    tenant_id, actor_id, approver_id = _actor_ids()
    request_ids: list[int] = []
    for decision in decisions:
        payload = _payload(decision["id"], tenant_id, actor_id)
        with SessionLocal() as db:
            entry = PortfolioPlanningService(db, tenant_id, actor_id, None).create(payload)
            assert entry.project_creation_request is not None
            request_ids.append(entry.project_creation_request.id)
        _approve_request(request_ids[-1], tenant_id, actor_id, approver_id)

    barrier = Barrier(2)

    def materialize(request_id: int) -> tuple[str, str, int]:
        with SessionLocal() as db:
            barrier.wait(timeout=15)
            result = ProjectCreationService(db, tenant_id, actor_id).materialize(request_id)
            return result.project_number, result.record_code, result.materialized_workspace_id

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(materialize, request_ids))
    assert len({item[0] for item in results}) == 2
    assert len({item[1] for item in results}) == 2

    project_id = results[0][2]
    _tenant_id, _target_portfolio_id, secondary_portfolio = _target_portfolio()
    with SessionLocal() as db:
        project = db.get(EnterpriseWorkspace, project_id)
        assert project is not None
        original_parent_id = project.parent_id
        expected_version = project.version
    membership_barrier = Barrier(2)

    def add_membership() -> int:
        with SessionLocal() as db:
            membership_barrier.wait(timeout=15)
            result = PortfolioPlanningService(db, tenant_id, actor_id, None).create_membership(
                project_id,
                PortfolioMembershipCreateIn(
                    portfolio_workspace_id=secondary_portfolio,
                    membership_source="MANUAL",
                ),
                expected_version,
            )
            return result.id

    with ThreadPoolExecutor(max_workers=2) as executor:
        membership_ids = list(executor.map(lambda _value: add_membership(), range(2)))
    assert len(set(membership_ids)) == 1
    with SessionLocal() as db:
        project = db.get(EnterpriseWorkspace, project_id)
        assert project is not None and project.parent_id == original_parent_id
        assert (
            db.scalar(
                select(func.count(PortfolioProjectMembership.id)).where(
                    PortfolioProjectMembership.project_workspace_id == project_id,
                    PortfolioProjectMembership.portfolio_workspace_id == secondary_portfolio,
                    PortfolioProjectMembership.status == "ACTIVE",
                )
            )
            == 1
        )


def test_readiness_contracts_target_protection_and_security_events() -> None:
    with TestClient(app) as client:
        decision = _approved_decision(client, _headers(client))
    tenant_id, actor_id, approver_id = _actor_ids()
    with SessionLocal() as db:
        entry = PortfolioPlanningService(db, tenant_id, actor_id, None).create(
            _payload(decision["id"], tenant_id, actor_id)
        )
        assert entry.project_creation_request is not None
        request_id = entry.project_creation_request.id
    _approve_request(request_id, tenant_id, actor_id, approver_id)
    with SessionLocal() as db:
        materialized = ProjectCreationService(db, tenant_id, actor_id).materialize(request_id)
        project_id = materialized.materialized_workspace_id
        service = PortfolioPlanningService(db, tenant_id, actor_id, None)
        ready = service.project_readiness(project_id)
        assert ready.status == "READY_FOR_PORTFOLIO_PLANNING"
        assert ready.portfolio_evaluation_readiness.status == "READY"
        assert ready.project_definition_readiness.status == "READY"
        membership = db.scalar(
            select(PortfolioProjectMembership).where(
                PortfolioProjectMembership.project_workspace_id == project_id,
                PortfolioProjectMembership.is_target_portfolio.is_(True),
            )
        )
        assert membership is not None
        with pytest.raises(HTTPException) as protected:
            service.remove_membership(project_id, membership.id, membership.revision_version)
        assert protected.value.status_code == 409

        request = db.get(ProjectCreationRequest, request_id)
        assert request is not None
        source = dict(request.strategic_source_snapshot_json)
        values = dict(source["source_values"])
        values["preliminary_scope"] = ""
        source["source_values"] = values
        request.strategic_source_snapshot_json = source
        db.commit()
        case_a = service.project_readiness(project_id)
        assert case_a.portfolio_evaluation_readiness.status == "READY"
        assert case_a.project_definition_readiness.status == "BLOCKED"
        assert case_a.status == "GATE07D_REWORK_REQUIRED"

        values["preliminary_scope"] = "Restored controlled scope"
        source["source_values"] = values
        request.strategic_source_snapshot_json = source
        membership.status = "INACTIVE"
        db.commit()
        case_b = service.project_readiness(project_id)
        assert case_b.portfolio_evaluation_readiness.status == "BLOCKED"
        assert case_b.project_definition_readiness.status == "READY"
        assert case_b.status == "GATE07D_REWORK_REQUIRED"

        event_types = set(
            db.scalars(
                select(SecurityEvent.event_type).where(
                    SecurityEvent.tenant_id == tenant_id,
                    SecurityEvent.target_id.in_([request_id, project_id, membership.id]),
                )
            ).all()
        )
        assert {
            "strategic_project_planning.request_created",
            "strategic_project_planning.request_linked",
            "strategic_project_planning.project_materialized",
            "portfolio_membership.created",
            "portfolio_planning.entry_ready",
            "portfolio_project.ready_for_planning",
            "portfolio_project.ready_for_evaluation",
            "project_definition.ready",
        }.issubset(event_types)


def test_admin_configuration_is_immutable_etagged_inheritable_and_has_no_scoring() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        records = client.get(
            "/api/v1/strategic-project-planning/admin/configurations",
            headers=headers,
        )
        assert records.status_code == 200, records.text
        published = next(item for item in records.json() if item["status"] == "published")
        immutable = client.put(
            f"/api/v1/strategic-project-planning/admin/configurations/{published['id']}",
            headers={**headers, "If-Match": f'"{published["version"]}"'},
            json={
                "name": published["name"],
                "description": published["description"],
                "content_json": published["content_json"],
            },
        )
        assert immutable.status_code == 409
        cloned = client.post(
            f"/api/v1/strategic-project-planning/admin/configurations/{published['id']}/clone",
            headers={**headers, "If-Match": f'"{published["version"]}"'},
        )
        assert cloned.status_code == 200, cloned.text
        draft = cloned.json()
        stale = client.put(
            f"/api/v1/strategic-project-planning/admin/configurations/{draft['id']}",
            headers={**headers, "If-Match": f'"{draft["version"] + 1}"'},
            json={
                "name": draft["name"],
                "description": draft["description"],
                "content_json": draft["content_json"],
            },
        )
        assert stale.status_code == 412
        forbidden_content = dict(draft["content_json"])
        forbidden_content["pdri_threshold"] = 70
        forbidden = client.put(
            f"/api/v1/strategic-project-planning/admin/configurations/{draft['id']}",
            headers={**headers, "If-Match": f'"{draft["version"]}"'},
            json={
                "name": draft["name"],
                "description": draft["description"],
                "content_json": forbidden_content,
            },
        )
        assert forbidden.status_code == 422
        saved = client.put(
            f"/api/v1/strategic-project-planning/admin/configurations/{draft['id']}",
            headers={**headers, "If-Match": f'"{draft["version"]}"'},
            json={
                "name": draft["name"],
                "description": draft["description"],
                "content_json": draft["content_json"],
            },
        )
        assert saved.status_code == 200, saved.text
        assert saved.headers["etag"] == f'"{saved.json()["version"]}"'
        published_clone = client.post(
            f"/api/v1/strategic-project-planning/admin/configurations/{draft['id']}/publish",
            headers={**headers, "If-Match": saved.headers["etag"]},
        )
        assert published_clone.status_code == 200, published_clone.text

    tenant_id, actor_id, _approver_id = _actor_ids()
    _tenant, portfolio_id, _secondary = _target_portfolio()
    with SessionLocal() as db:
        portfolio = db.get(EnterpriseWorkspace, portfolio_id)
        assert portfolio is not None and portfolio.parent_id is not None
        parent = db.get(EnterpriseWorkspace, portfolio.parent_id)
        assert parent is not None
        for workspace, membership_policy in ((parent, "RULE_BASED"), (portfolio, "HYBRID")):
            code = f"workspace-{workspace.id}"
            if db.scalar(
                select(AdminConfiguration).where(
                    AdminConfiguration.tenant_id == tenant_id,
                    AdminConfiguration.kind == "portfolio_planning_configuration",
                    AdminConfiguration.code == code,
                )
            ):
                continue
            content = dict(DEFAULT_CONFIGURATION)
            content.update(
                {
                    "workspace_id": workspace.id,
                    "inherit_to_descendants": True,
                    "membership_policy": membership_policy,
                }
            )
            db.add(
                AdminConfiguration(
                    tenant_id=tenant_id,
                    kind="portfolio_planning_configuration",
                    code=code,
                    name=f"Gate07D override {workspace.id}",
                    description="PostgreSQL inheritance validation",
                    status="published",
                    revision=1,
                    version=1,
                    content_json=content,
                    content_hash=_hash(content),
                    created_by_user_id=actor_id,
                )
            )
        db.commit()
        preview = PortfolioPlanningService(db, tenant_id, actor_id, None).configuration_preview(portfolio_id)
        assert preview.source["source_workspace_id"] == portfolio_id
        assert preview.effective["membership_policy"] == "HYBRID"
