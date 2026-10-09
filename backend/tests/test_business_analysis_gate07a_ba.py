"""Gate 07A-BA acceptance tests for governed Business Analysis."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import hash_password
from app.core.time import utc_now
from app.database.session import SessionLocal
from app.domain.models import (
    AdminConfiguration,
    AdminNumberSequence,
    AuthCredential,
    EnterpriseWorkspace,
    SecurityAccessAssignment,
    SecurityEvent,
    SecurityRole,
    UserAccount,
)
from app.main import app
from app.modules.business_analysis.models import BusinessAnalysis, BusinessAnalysisRevision
from app.modules.business_analysis.schemas import BusinessAnalysisRatingIn
from app.modules.business_analysis.service import (
    CONFIGURATION_KIND,
    DEFAULT_CODE,
    NUMBER_RULE,
    BusinessAnalysisService,
    ensure_business_analysis_seed_records,
)
from app.modules.enterprise_structure.models import EnterpriseStrategicObjective
from app.modules.enterprise_structure.permissions import EnterprisePermissionContext


def _headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin", "password": "1234", "tenant_slug": "demo-energy"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _workspace_and_objective() -> tuple[int, str]:
    with SessionLocal() as db:
        admin = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
        assert admin is not None
        workspace = db.scalar(
            select(EnterpriseWorkspace)
            .where(EnterpriseWorkspace.workspace_type_code.in_(["enterprise", "business-unit", "portfolio"]))
            .order_by(EnterpriseWorkspace.id)
        )
        if workspace is None:
            workspace = EnterpriseWorkspace(
                tenant_id=admin.tenant_id,
                parent_id=None,
                workspace_type_code="enterprise",
                code="G07A-BA-ENTERPRISE",
                external_key="g07a-ba-enterprise",
                record_code="G07A.BA.01",
                name="Gate 07A-BA Enterprise",
                status="active",
                defaults_json={"governance_model": "CAPITAL_OWNER"},
                sort_order=1,
                version=1,
                created_by_user_id=admin.id,
            )
            db.add(workspace)
            db.flush()
        objective = db.scalar(
            select(EnterpriseStrategicObjective)
            .where(
                EnterpriseStrategicObjective.tenant_id == admin.tenant_id,
                EnterpriseStrategicObjective.active.is_(True),
            )
            .order_by(EnterpriseStrategicObjective.id)
        )
        if objective is None:
            objective = EnterpriseStrategicObjective(
                tenant_id=admin.tenant_id,
                code=f"ba-objective-{uuid4().hex[:8]}",
                name="Governed capital growth",
                strategic_line="Enterprise",
                priority="high",
                horizon="2028",
                responsible_area="Strategy",
                active=True,
                description="Gate 07A-BA objective",
                source_release_code="GATE07A-BA-TEST",
                created_by_user_id=admin.id,
            )
            db.add(objective)
            db.commit()
        return workspace.id, objective.code


def _accepted_idea(client: TestClient, headers: dict[str, str]) -> dict:
    workspace_id, objective_code = _workspace_and_objective()
    options = client.get("/api/v1/ideas/options", headers=headers).json()
    created = client.post(
        "/api/v1/ideas",
        headers=headers,
        json={
            "title": "Modernize governed asset operations",
            "description": "Analyze alternatives before creating the governed project proposal.",
            "idea_type": options["idea_types"][0]["code"],
            "category": options["categories"][0]["code"],
            "expected_benefit": "Improve reliability and reduce lifecycle cost.",
            "estimated_value": "850000.00",
            "currency_code": "COP",
            "owning_workspace_id": workspace_id,
            "target_portfolio_workspace_id": None,
            "strategic_objective_codes": [objective_code],
            "attachment_refs": [{"document_id": "BA-EVIDENCE-001"}],
        },
    )
    assert created.status_code == 201, created.text
    idea = created.json()

    def action(path: str, body: dict | None = None) -> None:
        nonlocal idea
        response = client.post(
            f"/api/v1/ideas/{idea['id']}/{path}",
            headers={**headers, "If-Match": f'"{idea["revision_version"]}"'},
            json=body,
        )
        assert response.status_code == 200, response.text
        idea = response.json()

    action("submit")
    checklist = client.get("/api/v1/ideas/options", headers=headers).json()["screening_checklist"]
    action("screen", {"checklist": {item["code"]: True for item in checklist}, "notes": "Complete"})
    action("route", {"route_code": "default", "notes": "Default route"})
    with SessionLocal() as db:
        admin_id = db.scalar(select(UserAccount.id).where(UserAccount.email == "admin@demo.local"))
    action("assign-owner", {"owner_user_id": admin_id})
    action("evaluation/start")
    configurations = client.get("/api/v1/ideas/admin/configurations/list", headers=headers).json()
    matrix = next(item for item in configurations if item["kind"] == "idea_evaluation_matrix")
    action(
        "evaluation/complete",
        {
            "ratings": [
                {"criterion_code": item["code"], "rating": 4, "comment": "Validated"}
                for item in matrix["content_json"]["criteria"]
            ],
            "comments": "Eligible for Business Analysis",
        },
    )
    action("accept", {"reason": "Business Analysis required before proposal"})
    return idea


def _complete_payload(options: dict, objective_code: str) -> dict:
    criteria = options["evaluation_criteria"]

    def option(option_id: str, option_type: str, name: str, score: int) -> dict:
        return {
            "id": option_id,
            "name": name,
            "option_type": option_type,
            "description": f"Governed alternative {name}",
            "scope_concept": f"Scope for {name}",
            "expected_benefits": "Measurable reliability and cost improvement",
            "rough_cost_range": {"low": 500000, "high": 900000, "currency": "COP"},
            "rough_timeline": {"minimum_months": 8, "maximum_months": 14},
            "major_risks": [{"risk": "Adoption", "response": "Phased rollout"}],
            "major_dependencies": [{"dependency": "Data readiness"}],
            "feasibility_notes": "Feasible with staged controls",
            "strategic_fit": "Direct contribution to the selected objective",
            "evaluation": [
                {"criterion_code": item["code"], "rating": score, "comment": "Evidence reviewed"} for item in criteria
            ],
        }

    return {
        "analysis_type": options["analysis_types"][0]["code"],
        "statement": "Asset operations require a governed modernization decision.",
        "background": "The accepted Idea and evaluation establish the source baseline.",
        "business_context": "Enterprise capital planning",
        "urgency_timing": "Decision required in the current planning cycle",
        "consequences_no_action": "Reliability and lifecycle-cost exposure continue.",
        "business_drivers": [{"code": options["business_drivers"][0]["code"], "rationale": "Material"}],
        "strategic_alignment": [
            {"objective_code": objective_code, "contribution": "Improves asset reliability", "strength": 4}
        ],
        "stakeholders": [{"category": "BUSINESS_OWNER", "name": "Operations", "impact": "high"}],
        "current_state": {"summary": "Fragmented operational controls", "pain_points": ["Low visibility"]},
        "desired_outcomes": {"business_outcomes": "Controlled and measurable asset performance"},
        "expected_value": [{"dimension": "FINANCIAL", "description": "Lower lifecycle cost"}],
        "assumptions": [{"statement": "Required operational data remains available"}],
        "constraints": [{"statement": "Implementation must preserve service continuity"}],
        "business_requirements": [{"id": "BR-001", "statement": "Provide governed performance traceability"}],
        "options": [
            option("do-nothing", "DO_NOTHING", "Do nothing", 1),
            option("new-capability", "NEW_CAPABILITY", "Implement target capability", 4),
        ],
        "recommended_option_id": "new-capability",
        "recommendation_rationale": "Highest governed value with manageable delivery risk.",
        "key_trade_offs": [{"trade_off": "Upfront investment for lower lifecycle cost"}],
        "conditions": [{"condition": "Confirm data readiness before mobilization"}],
        "unresolved_concerns": [],
    }


def test_gate07a_ba_full_path_sod_lineage_and_immutable_snapshots() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        idea = _accepted_idea(client, headers)
        objective_code = idea["strategic_objective_codes"][0]

        readiness_before = client.get(f"/api/v1/ideas/{idea['id']}/proposal-readiness", headers=headers)
        assert readiness_before.status_code == 200
        assert readiness_before.json()["status"] == "READY_FOR_BUSINESS_ANALYSIS"

        options = client.get("/api/v1/business-analyses/options", headers=headers)
        assert options.status_code == 200, options.text
        eligible = next(item for item in options.json()["eligible_ideas"] if item["id"] == idea["id"])
        assert eligible["can_start"] is True
        assert eligible["business_analysis_required"] is True

        idempotency_key = f"test-ba-{uuid4()}"
        created = client.post(
            "/api/v1/business-analyses",
            headers={**headers, "Idempotency-Key": idempotency_key},
            json={"source_idea_id": idea["id"]},
        )
        assert created.status_code == 201, created.text
        analysis = created.json()
        assert analysis["status"] == "DRAFT"
        assert analysis["source_idea_evaluation_id"] == idea["accepted_evaluation_id"]

        duplicate = client.post(
            "/api/v1/business-analyses",
            headers={**headers, "Idempotency-Key": idempotency_key},
            json={"source_idea_id": idea["id"]},
        )
        assert duplicate.status_code == 201
        assert duplicate.json()["id"] == analysis["id"]

        payload = _complete_payload(options.json(), objective_code)
        stale = client.put(
            f"/api/v1/business-analyses/{analysis['id']}",
            headers={**headers, "If-Match": '"9999"'},
            json=payload,
        )
        assert stale.status_code == 412
        updated = client.put(
            f"/api/v1/business-analyses/{analysis['id']}",
            headers={**headers, "If-Match": f'"{analysis["revision_version"]}"'},
            json=payload,
        )
        assert updated.status_code == 200, updated.text
        analysis = updated.json()
        submitted = client.post(
            f"/api/v1/business-analyses/{analysis['id']}/submit",
            headers={**headers, "If-Match": f'"{analysis["revision_version"]}"'},
        )
        assert submitted.status_code == 200, submitted.text
        analysis = submitted.json()

        same_actor_review = client.post(
            f"/api/v1/business-analyses/{analysis['id']}/start-review",
            headers={**headers, "If-Match": f'"{analysis["revision_version"]}"'},
        )
        assert same_actor_review.status_code == 409
        assert same_actor_review.json()["detail"]["reason"] == "SEPARATION_OF_DUTIES_REQUIRED"

        with SessionLocal() as db:
            admin = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
            assert admin is not None
            reviewer = UserAccount(
                tenant_id=admin.tenant_id,
                email=f"ba-reviewer-{uuid4().hex[:8]}@demo.local",
                full_name="Independent BA Reviewer",
                title="Business Analysis Reviewer",
                status="active",
            )
            db.add(reviewer)
            db.commit()
            db.refresh(reviewer)
            context = EnterprisePermissionContext(
                user=reviewer,
                organization_wide=True,
                scope_unit_ids=frozenset(),
                workspace_ids=frozenset(),
                role_codes=frozenset({"business_analysis_reviewer"}),
            )
            service = BusinessAnalysisService(db, admin.tenant_id, reviewer.id, context)
            reviewed = service.start_review(analysis["id"], analysis["revision_version"])
            reviewer_id = reviewer.id

            other_reviewer = UserAccount(
                tenant_id=admin.tenant_id,
                email=f"ba-other-reviewer-{uuid4().hex[:8]}@demo.local",
                full_name="Unassigned BA Reviewer",
                title="Business Analysis Reviewer",
                status="active",
            )
            db.add(other_reviewer)
            db.commit()
            db.refresh(other_reviewer)
            other_service = BusinessAnalysisService(
                db,
                admin.tenant_id,
                other_reviewer.id,
                EnterprisePermissionContext(
                    user=other_reviewer,
                    organization_wide=True,
                    scope_unit_ids=frozenset(),
                    workspace_ids=frozenset(),
                    role_codes=frozenset({"business_analysis_reviewer"}),
                ),
            )
            with pytest.raises(HTTPException) as unassigned_completion:
                other_service.complete(analysis["id"], reviewed.revision_version)
            assert getattr(unassigned_completion.value, "status_code", None) == 409
            assert unassigned_completion.value.detail["reason"] == "REVIEW_ASSIGNED_TO_ANOTHER_USER"

            returned = service.return_analysis(
                analysis["id"],
                "Clarify the recommended option evidence",
                reviewed.revision_version,
            )
            assert returned.status == "RETURNED"

        revised = client.put(
            f"/api/v1/business-analyses/{analysis['id']}",
            headers={**headers, "If-Match": f'"{returned.revision_version}"'},
            json=payload,
        )
        assert revised.status_code == 200, revised.text
        resubmitted = client.post(
            f"/api/v1/business-analyses/{analysis['id']}/submit",
            headers={**headers, "If-Match": f'"{revised.json()["revision_version"]}"'},
        )
        assert resubmitted.status_code == 200, resubmitted.text
        with SessionLocal() as db:
            admin = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
            reviewer = db.get(UserAccount, reviewer_id)
            assert admin is not None and reviewer is not None
            service = BusinessAnalysisService(
                db,
                admin.tenant_id,
                reviewer.id,
                EnterprisePermissionContext(
                    user=reviewer,
                    organization_wide=True,
                    scope_unit_ids=frozenset(),
                    workspace_ids=frozenset(),
                    role_codes=frozenset({"business_analysis_reviewer"}),
                ),
            )
            reviewed = service.start_review(analysis["id"], resubmitted.json()["revision_version"])
            completed = service.complete(analysis["id"], reviewed.revision_version)
            assert completed.status == "COMPLETED"
            assert completed.completion_hash

        readiness = client.get(f"/api/v1/business-analyses/{analysis['id']}/readiness", headers=headers)
        assert readiness.status_code == 200, readiness.text
        assert readiness.json()["output"] == "READY_FOR_PROJECT_PROPOSAL"
        idea_readiness = client.get(f"/api/v1/ideas/{idea['id']}/proposal-readiness", headers=headers)
        assert idea_readiness.json()["can_create_project_proposal"] is True

        preview = client.post(
            "/api/v1/project-proposals/preview",
            headers=headers,
            json={"source_idea_id": idea["id"]},
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["blockers"] == []
        assert preview.json()["business_analysis"]["id"] == analysis["id"]
        assert preview.json()["mapped_fields"]["business_need"] == payload["statement"]

        proposal = client.post(
            "/api/v1/project-proposals",
            headers=headers,
            json={"source_idea_id": idea["id"]},
        )
        assert proposal.status_code == 201, proposal.text
        assert proposal.json()["source_business_analysis_id"] == analysis["id"]
        assert proposal.json()["source_business_analysis_hash"]

        reused_creation_key = client.post(
            f"/api/v1/business-analyses/{analysis['id']}/new-revision",
            headers={**headers, "Idempotency-Key": idempotency_key},
        )
        assert reused_creation_key.status_code == 409
        assert reused_creation_key.json()["detail"]["reason"] == "IDEMPOTENCY_KEY_REUSED"

        material_revision = client.post(
            f"/api/v1/business-analyses/{analysis['id']}/new-revision",
            headers={**headers, "Idempotency-Key": f"test-ba-revision-{uuid4()}"},
        )
        assert material_revision.status_code == 201, material_revision.text
        successor = material_revision.json()
        assert successor["supersedes_analysis_id"] == analysis["id"]
        successor_update = client.put(
            f"/api/v1/business-analyses/{successor['id']}",
            headers={**headers, "If-Match": f'"{successor["revision_version"]}"'},
            json=payload,
        )
        assert successor_update.status_code == 200, successor_update.text
        successor_submit = client.post(
            f"/api/v1/business-analyses/{successor['id']}/submit",
            headers={**headers, "If-Match": f'"{successor_update.json()["revision_version"]}"'},
        )
        assert successor_submit.status_code == 200, successor_submit.text
        with SessionLocal() as db:
            admin = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
            reviewer = db.get(UserAccount, reviewer_id)
            assert admin is not None and reviewer is not None
            service = BusinessAnalysisService(
                db,
                admin.tenant_id,
                reviewer.id,
                EnterprisePermissionContext(
                    user=reviewer,
                    organization_wide=True,
                    scope_unit_ids=frozenset(),
                    workspace_ids=frozenset(),
                    role_codes=frozenset({"business_analysis_reviewer"}),
                ),
            )
            successor_review = service.start_review(successor["id"], successor_submit.json()["revision_version"])
            successor_complete = service.complete(successor["id"], successor_review.revision_version)
            assert successor_complete.status == "COMPLETED"
        predecessor = client.get(f"/api/v1/business-analyses/{analysis['id']}", headers=headers)
        assert predecessor.status_code == 200
        assert predecessor.json()["status"] == "SUPERSEDED"

        forbidden_mutation = client.put(
            f"/api/v1/business-analyses/{analysis['id']}",
            headers={**headers, "If-Match": f'"{predecessor.json()["revision_version"]}"'},
            json=payload,
        )
        assert forbidden_mutation.status_code == 409
        with SessionLocal() as db:
            snapshots = db.scalars(
                select(BusinessAnalysisRevision).where(BusinessAnalysisRevision.business_analysis_id == analysis["id"])
            ).all()
            assert len(snapshots) >= 5
            events = db.scalars(
                select(SecurityEvent).where(
                    SecurityEvent.target_type == "BusinessAnalysis",
                    SecurityEvent.target_id == analysis["id"],
                )
            ).all()
            assert {item.event_type for item in events} >= {
                "business_analysis.created",
                "business_analysis.updated",
                "business_analysis.submitted",
                "business_analysis.review_started",
                "business_analysis.returned",
                "business_analysis.completed",
                "business_analysis.superseded",
            }
            stored = db.get(BusinessAnalysis, analysis["id"])
            assert stored is not None and stored.status == "SUPERSEDED"

        configurations = client.get("/api/v1/business-analyses/admin/configurations", headers=headers).json()
        published = next(item for item in configurations if item["code"] == "default" and item["status"] == "published")
        cloned = client.post(
            f"/api/v1/business-analyses/admin/configurations/{published['id']}/clone",
            headers={**headers, "If-Match": f'"{published["version"]}"'},
        )
        assert cloned.status_code == 200, cloned.text
        draft = cloned.json()
        revised_content = dict(draft["content_json"])
        revised_content["business_drivers"] = [dict(item) for item in revised_content["business_drivers"]]
        revised_content["business_drivers"][0]["label"] = f"Strategic growth {uuid4().hex[:6]}"
        updated_configuration = client.put(
            f"/api/v1/business-analyses/admin/configurations/{draft['id']}",
            headers={**headers, "If-Match": f'"{draft["version"]}"'},
            json={
                "name": draft["name"],
                "description": "Published successor proving stale-analysis detection",
                "content_json": revised_content,
            },
        )
        assert updated_configuration.status_code == 200, updated_configuration.text
        published_successor = client.post(
            f"/api/v1/business-analyses/admin/configurations/{draft['id']}/publish",
            headers={
                **headers,
                "If-Match": f'"{updated_configuration.json()["version"]}"',
            },
        )
        assert published_successor.status_code == 200, published_successor.text
        stale_readiness = client.get(f"/api/v1/business-analyses/{analysis['id']}/readiness", headers=headers)
        assert stale_readiness.status_code == 200
        assert stale_readiness.json()["status"] == "STALE"
        assert "STALE_EVALUATION_MATRIX" in stale_readiness.json()["blockers"]
        idea_after_config_change = client.get(
            f"/api/v1/ideas/{idea['id']}/proposal-readiness",
            headers=headers,
        )
        assert idea_after_config_change.json()["status"] == "BUSINESS_ANALYSIS_STALE"
        historical_proposal = client.get(
            f"/api/v1/project-proposals/{proposal.json()['id']}",
            headers=headers,
        )
        assert historical_proposal.status_code == 200
        assert (
            historical_proposal.json()["source_business_analysis_hash"]
            == proposal.json()["source_business_analysis_hash"]
        )


def test_gate07a_ba_admin_preview_is_non_persistent_and_published_is_immutable() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        workspace_id, _objective_code = _workspace_and_objective()
        before = client.get("/api/v1/business-analyses/admin/configurations", headers=headers)
        assert before.status_code == 200, before.text
        count_before = len(before.json())
        preview = client.post(
            "/api/v1/business-analyses/admin/configuration/preview",
            headers=headers,
            json={"owning_workspace_id": workspace_id},
        )
        assert preview.status_code == 200, preview.text
        assert preview.json()["persisted"] is False
        after = client.get("/api/v1/business-analyses/admin/configurations", headers=headers)
        assert len(after.json()) == count_before

        published = next(item for item in after.json() if item["status"] == "published")
        rejected = client.put(
            f"/api/v1/business-analyses/admin/configurations/{published['id']}",
            headers={**headers, "If-Match": f'"{published["version"]}"'},
            json={
                "name": published["name"],
                "description": published["description"],
                "content_json": published["content_json"],
            },
        )
        assert rejected.status_code == 409


@pytest.mark.parametrize(
    ("governance_model", "required"),
    [
        ("CAPITAL_OWNER", True),
        ("CONTRACTOR_DELIVERY", False),
        ("DIRECT_INTERNAL", False),
        ("LEGACY_UNCLASSIFIED", False),
    ],
)
def test_gate07a_ba_governance_policy_is_snapshotted_and_legacy_safe(
    governance_model: str,
    required: bool,
) -> None:
    policy = {
        "CAPITAL_OWNER": True,
        "CONTRACTOR_DELIVERY": False,
        "DIRECT_INTERNAL": False,
        "LEGACY_UNCLASSIFIED": False,
    }
    idea = SimpleNamespace(
        configuration_snapshot_json={
            "effective": {
                "governance_model": governance_model,
                "business_analysis_required_by_governance_model": policy,
            }
        }
    )
    assert BusinessAnalysisService.requirement_for_idea(idea) is required

    grandfathered = SimpleNamespace(configuration_snapshot_json={"effective": {}})
    assert BusinessAnalysisService.requirement_for_idea(grandfathered) is False


def test_gate07a_ba_user_role_cannot_access_admin_configuration() -> None:
    with TestClient(app) as client:
        admin_headers = _headers(client)
        assert client.get("/api/v1/business-analyses/options", headers=admin_headers).status_code == 200
        with SessionLocal() as db:
            admin = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
            role = db.scalar(select(SecurityRole).where(SecurityRole.code == "business_analysis_author"))
            assert admin is not None and role is not None
            email = f"ba-author-{uuid4().hex[:8]}@demo.local"
            author = UserAccount(
                tenant_id=admin.tenant_id,
                email=email,
                full_name="Business Analysis Author Only",
                title="Analyst",
                status="active",
            )
            db.add(author)
            db.flush()
            db.add(
                AuthCredential(
                    tenant_id=admin.tenant_id,
                    user_id=author.id,
                    provider="local",
                    password_hash=hash_password("1234"),
                    is_active=True,
                )
            )
            db.add(
                SecurityAccessAssignment(
                    tenant_id=admin.tenant_id,
                    subject_type="user",
                    user_id=author.id,
                    role_id=role.id,
                    scope_type="organization",
                    status="active",
                    granted_by_user_id=admin.id,
                )
            )
            db.commit()
        login = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "1234", "tenant_slug": "demo-energy"},
        )
        assert login.status_code == 200, login.text
        author_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        assert client.get("/api/v1/business-analyses/options", headers=author_headers).status_code == 200
        denied = client.get("/api/v1/business-analyses/admin/configurations", headers=author_headers)
        assert denied.status_code == 403


def test_gate07a_ba_void_is_audited_and_releases_the_active_slot() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        idea = _accepted_idea(client, headers)
        created = client.post(
            "/api/v1/business-analyses",
            headers={**headers, "Idempotency-Key": f"test-ba-void-{uuid4()}"},
            json={"source_idea_id": idea["id"]},
        )
        assert created.status_code == 201, created.text
        analysis = created.json()
        voided = client.post(
            f"/api/v1/business-analyses/{analysis['id']}/void",
            headers={**headers, "If-Match": f'"{analysis["revision_version"]}"'},
            json={"reason": "Duplicate discovery record"},
        )
        assert voided.status_code == 200, voided.text
        assert voided.json()["status"] == "VOIDED"
        replacement = client.post(
            "/api/v1/business-analyses",
            headers={**headers, "Idempotency-Key": f"test-ba-replacement-{uuid4()}"},
            json={"source_idea_id": idea["id"]},
        )
        assert replacement.status_code == 201, replacement.text
        assert replacement.json()["id"] != analysis["id"]
        history = client.get(f"/api/v1/business-analyses/{analysis['id']}/history", headers=headers)
        assert history.status_code == 200
        assert "business_analysis.voided" in {item["event_type"] for item in history.json()}


def test_gate07a_ba_cursor_pagination_is_bounded_stable_and_rejects_invalid_ratings() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        idea = _accepted_idea(client, headers)
        options = client.get("/api/v1/business-analyses/options", headers=headers)
        assert options.status_code == 200, options.text

        created = client.post(
            "/api/v1/business-analyses",
            headers={**headers, "Idempotency-Key": f"test-ba-rating-{uuid4()}"},
            json={"source_idea_id": idea["id"]},
        )
        assert created.status_code == 201, created.text
        payload = _complete_payload(options.json(), idea["strategic_objective_codes"][0])
        payload["options"][0]["evaluation"][0]["rating"] = 99
        updated = client.put(
            f"/api/v1/business-analyses/{created.json()['id']}",
            headers={**headers, "If-Match": f'"{created.json()["revision_version"]}"'},
            json=payload,
        )
        assert updated.status_code == 200, updated.text
        assert any(
            blocker.startswith("OPTION_RATING_OUT_OF_RANGE:") for blocker in updated.json()["readiness"]["blockers"]
        )
        rejected_submit = client.post(
            f"/api/v1/business-analyses/{created.json()['id']}/submit",
            headers={**headers, "If-Match": f'"{updated.json()["revision_version"]}"'},
        )
        assert rejected_submit.status_code == 422
        assert rejected_submit.json()["detail"]["reason"] == "BUSINESS_ANALYSIS_NOT_READY"

        marker = f"hardening-page-{uuid4().hex[:10]}"
        with SessionLocal() as db:
            admin = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
            configuration = db.scalar(
                select(AdminConfiguration)
                .where(
                    AdminConfiguration.tenant_id == admin.tenant_id,
                    AdminConfiguration.kind == CONFIGURATION_KIND,
                    AdminConfiguration.status == "published",
                )
                .order_by(AdminConfiguration.revision.desc())
            )
            assert admin is not None and configuration is not None
            timestamp = utc_now()
            db.add_all(
                [
                    BusinessAnalysis(
                        tenant_id=admin.tenant_id,
                        analysis_number=f"BA-PAGE-{uuid4().hex[:12]}",
                        source_idea_id=idea["id"],
                        source_idea_evaluation_id=idea["accepted_evaluation_id"],
                        owning_workspace_id=idea["owning_workspace_id"],
                        status="COMPLETED",
                        title=f"{marker}-{index}",
                        content_json={"statement": marker},
                        readiness_json={"blockers": []},
                        source_idea_hash="a" * 64,
                        configuration_id=configuration.id,
                        configuration_revision=configuration.revision,
                        configuration_hash=configuration.content_hash,
                        review_json={},
                        completion_hash="b" * 64,
                        idempotency_key=f"{marker}-{index}",
                        revision_version=1,
                        created_by_user_id=admin.id,
                        updated_by_user_id=admin.id,
                        created_at=timestamp + timedelta(seconds=index),
                        updated_at=timestamp + timedelta(seconds=index),
                    )
                    for index in range(4)
                ]
            )
            db.commit()

        first_page = client.get(
            "/api/v1/business-analyses",
            headers=headers,
            params={"search": marker, "limit": 2},
        )
        assert first_page.status_code == 200, first_page.text
        assert len(first_page.json()) == 2
        assert first_page.headers["X-Page-Limit"] == "2"
        assert first_page.headers["X-Result-Count"] == "2"
        cursor = first_page.headers.get("X-Next-Cursor")
        assert cursor

        second_page = client.get(
            "/api/v1/business-analyses",
            headers=headers,
            params={"search": marker, "limit": 2, "cursor": cursor},
        )
        assert second_page.status_code == 200, second_page.text
        assert len(second_page.json()) == 2
        assert {item["id"] for item in first_page.json()}.isdisjoint({item["id"] for item in second_page.json()})
        assert "X-Next-Cursor" not in second_page.headers
        assert (
            client.get(
                "/api/v1/business-analyses",
                headers=headers,
                params={"limit": 101},
            ).status_code
            == 422
        )
        invalid_cursor = client.get(
            "/api/v1/business-analyses",
            headers=headers,
            params={"cursor": "not-a-valid-cursor"},
        )
        assert invalid_cursor.status_code == 400
        assert invalid_cursor.json()["detail"]["reason"] == "INVALID_CURSOR"

    with pytest.raises(ValueError):
        BusinessAnalysisRatingIn(criterion_code="strategic-fit", rating=float("nan"))


def test_gate07a_ba_rejects_invalid_admin_scoring_configuration() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        configurations = client.get("/api/v1/business-analyses/admin/configurations", headers=headers)
        assert configurations.status_code == 200, configurations.text
        published = max(
            (item for item in configurations.json() if item["status"] == "published"),
            key=lambda item: item["revision"],
        )
        cloned = client.post(
            f"/api/v1/business-analyses/admin/configurations/{published['id']}/clone",
            headers={**headers, "If-Match": f'"{published["version"]}"'},
        )
        assert cloned.status_code == 200, cloned.text
        draft = cloned.json()
        invalid_content = deepcopy(draft["content_json"])
        invalid_content["evaluation_matrix"]["scale"] = {
            "min": 5,
            "max": 1,
            "allowed_values": [1, 2, 3, 4, 5],
        }
        rejected = client.put(
            f"/api/v1/business-analyses/admin/configurations/{draft['id']}",
            headers={**headers, "If-Match": f'"{draft["version"]}"'},
            json={
                "name": draft["name"],
                "description": draft["description"],
                "content_json": invalid_content,
            },
        )
        assert rejected.status_code == 422
        issues = rejected.json()["detail"]["issues"]
        assert "EVALUATION_SCALE_RANGE_INVALID" in issues


def test_gate07a_ba_config_admin_cannot_execute_user_transactions() -> None:
    with TestClient(app) as client:
        admin_headers = _headers(client)
        assert (
            client.get(
                "/api/v1/business-analyses/admin/configurations",
                headers=admin_headers,
            ).status_code
            == 200
        )
        with SessionLocal() as db:
            admin = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
            role = db.scalar(select(SecurityRole).where(SecurityRole.code == "business_analysis_config_admin"))
            assert admin is not None and role is not None
            email = f"ba-config-admin-{uuid4().hex[:8]}@demo.local"
            config_admin = UserAccount(
                tenant_id=admin.tenant_id,
                email=email,
                full_name="Business Analysis Configuration Admin",
                title="Configuration Administrator",
                status="active",
            )
            db.add(config_admin)
            db.flush()
            db.add(
                AuthCredential(
                    tenant_id=admin.tenant_id,
                    user_id=config_admin.id,
                    provider="local",
                    password_hash=hash_password("1234"),
                    is_active=True,
                )
            )
            db.add(
                SecurityAccessAssignment(
                    tenant_id=admin.tenant_id,
                    subject_type="user",
                    user_id=config_admin.id,
                    role_id=role.id,
                    scope_type="organization",
                    status="active",
                    granted_by_user_id=admin.id,
                )
            )
            db.commit()
        login = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "1234", "tenant_slug": "demo-energy"},
        )
        assert login.status_code == 200, login.text
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        assert (
            client.get(
                "/api/v1/business-analyses/admin/configurations",
                headers=headers,
            ).status_code
            == 200
        )
        assert client.get("/api/v1/business-analyses/options", headers=headers).status_code == 403
        denied_transaction = client.post(
            "/api/v1/business-analyses",
            headers={**headers, "Idempotency-Key": f"config-admin-denied-{uuid4()}"},
            json={"source_idea_id": 1},
        )
        assert denied_transaction.status_code == 403


def test_gate07a_ba_default_seed_is_idempotent_under_concurrent_sessions() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        assert client.get("/api/v1/business-analyses/options", headers=headers).status_code == 200

    with SessionLocal() as db:
        admin = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
        assert admin is not None
        tenant_id, actor_id = admin.tenant_id, admin.id

    def seed_once(_attempt: int) -> None:
        with SessionLocal() as db:
            ensure_business_analysis_seed_records(db, tenant_id, actor_id)
            db.commit()

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(seed_once, range(8)))

    with SessionLocal() as db:
        configurations = db.scalars(
            select(AdminConfiguration).where(
                AdminConfiguration.tenant_id == tenant_id,
                AdminConfiguration.kind == CONFIGURATION_KIND,
                AdminConfiguration.code == DEFAULT_CODE,
                AdminConfiguration.revision == 1,
            )
        ).all()
        sequences = db.scalars(
            select(AdminNumberSequence).where(
                AdminNumberSequence.tenant_id == tenant_id,
                AdminNumberSequence.rule_code == NUMBER_RULE,
                AdminNumberSequence.scope_key == "tenant",
            )
        ).all()
        assert len(configurations) == 1
        assert len(sequences) == 1
