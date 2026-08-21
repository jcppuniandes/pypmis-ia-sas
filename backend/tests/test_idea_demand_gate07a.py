"""Gate 07A acceptance tests for the single governed Idea lifecycle."""

from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database.session import SessionLocal
from app.domain.models import EnterpriseWorkspace, UserAccount
from app.main import app
from app.modules.enterprise_structure.models import EnterpriseStrategicObjective
from app.modules.idea_demand.models import IdeaEvaluation


def _headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin", "password": "1234", "tenant_slug": "demo-energy"},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _workspace_id() -> int:
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
                code="G07A-ENTERPRISE",
                external_key="g07a-enterprise",
                record_code="G07A.01",
                name="Gate 07A Enterprise",
                status="active",
                defaults_json={},
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
            db.add(
                EnterpriseStrategicObjective(
                    tenant_id=admin.tenant_id,
                    code=f"g07a-objective-{uuid4().hex[:8]}",
                    name="Sustainable growth",
                    strategic_line="Enterprise",
                    priority="high",
                    horizon="2026",
                    responsible_area="Strategy",
                    active=True,
                    description="Gate 07A objective",
                    source_release_code="G07A-TEST",
                    created_by_user_id=admin.id,
                )
            )
        db.commit()
        return workspace.id


def test_gate07a_fixture_restores_its_strategic_objective_precondition() -> None:
    with TestClient(app):
        with SessionLocal() as db:
            objectives = db.scalars(select(EnterpriseStrategicObjective)).all()
            for objective in objectives:
                objective.active = False
            db.commit()

        _workspace_id()

        with SessionLocal() as db:
            assert db.scalar(select(EnterpriseStrategicObjective).where(EnterpriseStrategicObjective.active.is_(True)))


def _payload(client: TestClient, headers: dict[str, str]) -> dict:
    workspace_id = _workspace_id()
    options = client.get("/api/v1/ideas/options", headers=headers)
    assert options.status_code == 200, options.text
    body = options.json()
    assert body["number_preview"].startswith("IDEA-")
    return {
        "title": "Optimize enterprise energy demand",
        "description": "Controlled idea used to validate the complete Gate 07A lifecycle.",
        "idea_type": body["idea_types"][0]["code"],
        "category": body["categories"][0]["code"],
        "expected_benefit": "Reduce operating cost while preserving service levels.",
        "estimated_value": "125000.00",
        "currency_code": "COP",
        "owning_workspace_id": workspace_id,
        "target_portfolio_workspace_id": None,
        "strategic_objective_codes": [item["code"] for item in body["strategic_objectives"][:1]],
        "attachment_refs": [{"document_id": "EVIDENCE-001", "label": "Opportunity assessment"}],
    }


def _action(client: TestClient, headers: dict[str, str], idea: dict, path: str, body: dict | None = None) -> dict:
    response = client.post(
        f"/api/v1/ideas/{idea['id']}/{path}",
        headers={**headers, "If-Match": f'"{idea["revision_version"]}"'},
        json=body,
    )
    assert response.status_code == 200, response.text
    assert response.headers["etag"] == f'"{response.json()["revision_version"]}"'
    return response.json()


def test_gate07a_full_lifecycle_readiness_and_audit() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        created = client.post("/api/v1/ideas", headers=headers, json=_payload(client, headers))
        assert created.status_code == 201, created.text
        idea = created.json()
        assert idea["state"] == "DRAFT"
        idea = _action(client, headers, idea, "submit")
        assert idea["state"] == "SUBMITTED"
        checklist = client.get("/api/v1/ideas/options", headers=headers).json()["screening_checklist"]
        idea = _action(
            client,
            headers,
            idea,
            "screen",
            {"checklist": {item["code"]: True for item in checklist}, "notes": "Complete"},
        )
        idea = _action(client, headers, idea, "route", {"route_code": "default", "notes": "Default route"})
        with SessionLocal() as db:
            admin_id = db.scalar(select(UserAccount.id).where(UserAccount.email == "admin@demo.local"))
        idea = _action(client, headers, idea, "assign-owner", {"owner_user_id": admin_id})
        assert idea["state"] == "OWNER_ASSIGNED"
        idea = _action(client, headers, idea, "evaluation/start")
        matrix = client.get("/api/v1/ideas/admin/configurations/list", headers=headers).json()
        published_matrix = next(item for item in matrix if item["kind"] == "idea_evaluation_matrix")
        ratings = [
            {"criterion_code": item["code"], "rating": 4, "comment": "Validated"}
            for item in published_matrix["content_json"]["criteria"]
        ]
        idea = _action(client, headers, idea, "evaluation/complete", {"ratings": ratings, "comments": "Complete"})
        assert idea["state"] == "EVALUATED"
        assert len(idea["evaluations"]) == 1
        idea = _action(client, headers, idea, "accept", {"reason": "Meets the enterprise decision criteria"})
        assert idea["state"] == "ACCEPTED"
        readiness = client.get(f"/api/v1/ideas/{idea['id']}/proposal-readiness", headers=headers)
        assert readiness.status_code == 200
        assert readiness.json()["status"] == "READY_FOR_PROJECT_PROPOSAL"
        assert readiness.json()["can_create_project_proposal"] is True
        history = client.get(f"/api/v1/ideas/{idea['id']}/history", headers=headers).json()
        assert {item["event_type"] for item in history} >= {
            "idea.created",
            "idea.submitted",
            "idea.screened",
            "idea.routed",
            "idea.owner_assigned",
            "idea.evaluated",
            "idea.accepted",
        }


def test_gate07a_etag_scope_and_preview_do_not_consume_number() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        before = client.get("/api/v1/ideas/options", headers=headers).json()["number_preview"]
        again = client.get("/api/v1/ideas/options", headers=headers).json()["number_preview"]
        assert before == again
        payload = _payload(client, headers)
        payload["owning_workspace_id"] = client.get("/api/v1/workspaces", headers=headers).json()[0]["workspace_id"]
        with SessionLocal() as db:
            target = db.get(EnterpriseWorkspace, payload["owning_workspace_id"])
        if target and target.workspace_type_code not in {"enterprise", "business-unit", "portfolio"}:
            invalid = client.post("/api/v1/ideas", headers=headers, json=payload)
            assert invalid.status_code == 422
        payload["owning_workspace_id"] = _workspace_id()
        created = client.post("/api/v1/ideas", headers=headers, json=payload).json()
        mismatch = client.put(
            f"/api/v1/ideas/{created['id']}",
            headers={**headers, "If-Match": '"9999"'},
            json=payload,
        )
        assert mismatch.status_code == 412


def test_gate07a_evaluation_is_immutable_and_proposal_source_remains_read_only() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        assert client.post("/api/v1/ideas/1/create-project-proposal", headers=headers).status_code == 404
        with SessionLocal() as db:
            evaluation = db.scalar(select(IdeaEvaluation).order_by(IdeaEvaluation.id.desc()))
            if evaluation is not None:
                evaluation.comments = "Attempted mutation"
                try:
                    db.commit()
                    raise AssertionError("Immutable evaluation update unexpectedly committed")
                except ValueError:
                    db.rollback()
