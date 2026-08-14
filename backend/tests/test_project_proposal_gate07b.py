"""Gate 07B acceptance tests for Project Proposal foundation and lifecycle."""

from copy import deepcopy

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database.session import SessionLocal
from app.domain.models import AdminConfiguration, EnterpriseWorkspace, SecurityEvent, UserAccount
from app.main import app
from app.modules.enterprise_structure.models import EnterpriseStrategicObjective
from app.modules.idea_demand.models import Idea, IdeaEvaluation
from app.modules.project_proposal.models import ProjectProposal, ProjectProposalEvaluation


def _headers(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "admin", "password": "1234", "tenant_slug": "demo-energy"},
    )
    assert response.status_code == 200, response.text
    headers = {"Authorization": f"Bearer {response.json()['access_token']}"}
    assert client.get("/api/v1/ideas/options", headers=headers).status_code == 200
    return headers


def _accepted_idea(*, state: str = "ACCEPTED", with_objective: bool = True) -> tuple[int, dict]:
    with SessionLocal() as db:
        admin = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
        assert admin is not None
        workspace = db.scalar(
            select(EnterpriseWorkspace)
            .where(
                EnterpriseWorkspace.tenant_id == admin.tenant_id,
                EnterpriseWorkspace.workspace_type_code.in_(["enterprise", "business-unit", "portfolio"]),
            )
            .order_by(EnterpriseWorkspace.id)
        )
        if workspace is None:
            workspace = EnterpriseWorkspace(
                tenant_id=admin.tenant_id,
                parent_id=None,
                workspace_type_code="enterprise",
                code="G07B-ENTERPRISE",
                external_key="g07b-enterprise",
                record_code="G07B.01",
                name="Gate 07B Enterprise",
                status="active",
                defaults_json={},
                sort_order=1,
                version=1,
                created_by_user_id=admin.id,
            )
            db.add(workspace)
            db.flush()
        objective = db.scalar(
            select(EnterpriseStrategicObjective).where(
                EnterpriseStrategicObjective.tenant_id == admin.tenant_id,
                EnterpriseStrategicObjective.active.is_(True),
            )
        )
        if objective is None:
            objective = EnterpriseStrategicObjective(
                tenant_id=admin.tenant_id,
                code="gate07b-growth",
                name="Gate 07B Sustainable Growth",
                strategic_line="Enterprise",
                priority="high",
                horizon="2026",
                responsible_area="Strategy",
                active=True,
                description="Gate 07B test objective",
                source_release_code="G07B-TEST",
                created_by_user_id=admin.id,
            )
            db.add(objective)
            db.flush()
        matrix = db.scalar(
            select(AdminConfiguration).where(
                AdminConfiguration.tenant_id == admin.tenant_id,
                AdminConfiguration.kind == "idea_evaluation_matrix",
                AdminConfiguration.status == "published",
            )
        )
        idea_config = db.scalar(
            select(AdminConfiguration).where(
                AdminConfiguration.tenant_id == admin.tenant_id,
                AdminConfiguration.kind == "idea_demand_configuration",
                AdminConfiguration.status == "published",
            )
        )
        assert matrix is not None and idea_config is not None
        idea = Idea(
            tenant_id=admin.tenant_id,
            idea_number=f"IDEA-G07B-{int(db.scalar(select(func.count(Idea.id))) or 0) + 1:04d}",
            title="Enterprise digital delivery platform",
            description="Create a controlled enterprise platform for digital project delivery.",
            idea_type="innovation",
            category="growth",
            expected_benefit="Improve delivery predictability and strategic visibility.",
            estimated_value="2400000.00",
            currency_code="COP",
            owning_workspace_id=workspace.id,
            target_portfolio_workspace_id=(workspace.id if workspace.workspace_type_code == "portfolio" else None),
            strategic_objective_codes=[objective.code] if with_objective else [],
            requestor_user_id=admin.id,
            owner_user_id=admin.id,
            state=state,
            screening_json={},
            routing_json={},
            configuration_snapshot_json={"effective": idea_config.content_json},
            attachment_refs_json=[{"reference": "IDEA-EVIDENCE-07B"}],
            accepted_evaluation_id=None,
            decision_reason="Accepted for Project Proposal" if state == "ACCEPTED" else None,
            decision_by_user_id=admin.id if state == "ACCEPTED" else None,
            readiness_json={},
            revision_version=1,
            last_modified_by_user_id=admin.id,
        )
        db.add(idea)
        db.flush()
        evaluation = IdeaEvaluation(
            tenant_id=admin.tenant_id,
            idea_id=idea.id,
            evaluation_version=1,
            matrix_configuration_id=matrix.id,
            matrix_revision=matrix.revision,
            matrix_snapshot_json=matrix.content_json,
            ratings_json=[],
            total_score="82.5000",
            result="RECOMMENDED",
            comments="Accepted source snapshot",
            evaluator_user_id=admin.id,
        )
        db.add(evaluation)
        db.flush()
        idea.accepted_evaluation_id = evaluation.id
        db.commit()
        snapshot = {
            "state": idea.state,
            "accepted_evaluation_id": idea.accepted_evaluation_id,
            "owning_workspace_id": idea.owning_workspace_id,
            "objectives": deepcopy(idea.strategic_objective_codes),
            "evaluation_score": str(evaluation.total_score),
        }
        return idea.id, snapshot


def _action(
    client: TestClient,
    headers: dict[str, str],
    proposal: dict,
    path: str,
    body: dict | None = None,
) -> dict:
    response = client.post(
        f"/api/v1/project-proposals/{proposal['id']}/{path}",
        headers={**headers, "If-Match": f'"{proposal["revision_version"]}"'},
        json=body,
    )
    assert response.status_code == 200, response.text
    assert response.headers["etag"] == f'"{response.json()["revision_version"]}"'
    return response.json()


def _complete_payload(proposal: dict) -> dict:
    return {
        "name": proposal["name"],
        "business_need": proposal["business_need"],
        "business_justification": proposal["business_justification"],
        "project_objectives": proposal["project_objectives"],
        "preliminary_scope": proposal["preliminary_scope"],
        "out_of_scope": "Enterprise investment decision and Project Workspace creation.",
        "expected_benefits": proposal["expected_benefits"],
        "benefit_owner_user_id": proposal["proposal_owner_user_id"],
        "rom_cost": proposal["rom_cost"],
        "currency_code": proposal["currency_code"],
        "preliminary_duration_days": 180,
        "target_start_date": "2027-01-15",
        "target_finish_date": "2027-07-14",
        "key_risks": [{"risk": "Adoption", "response": "Phased enablement"}],
        "assumptions": [{"assumption": "Executive sponsorship remains active"}],
        "constraints": [{"constraint": "Gate approval is outside Gate 07B"}],
        "strategic_objective_codes": proposal["strategic_objective_codes"],
        "target_portfolio_workspace_id": proposal["target_portfolio_workspace_id"],
        "sponsor_user_id": proposal["sponsor_user_id"],
        "proposal_owner_user_id": proposal["proposal_owner_user_id"],
        "attachment_refs": proposal["attachment_refs"],
    }


def test_gate07b_full_lifecycle_preserves_source_and_exposes_gate07c_contract() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        idea_id, source_before = _accepted_idea()
        with SessionLocal() as db:
            workspace_count_before = int(db.scalar(select(func.count(EnterpriseWorkspace.id))) or 0)

        preview_one = client.post(
            "/api/v1/project-proposals/preview",
            headers=headers,
            json={"source_idea_id": idea_id},
        )
        preview_two = client.post(
            f"/api/v1/ideas/{idea_id}/project-proposals/preview",
            headers=headers,
        )
        assert preview_one.status_code == 200, preview_one.text
        assert preview_two.status_code == 200, preview_two.text
        assert preview_one.json()["proposal_number_preview"] == preview_two.json()["proposal_number_preview"]
        assert preview_one.json()["persisted"] is False
        assert preview_one.json()["blockers"] == []

        created = client.post(
            "/api/v1/project-proposals",
            headers=headers,
            json={"source_idea_id": idea_id},
        )
        assert created.status_code == 201, created.text
        proposal = created.json()
        assert proposal["status"] == "DRAFT"
        assert proposal["proposal_number"].startswith("PROP-")
        assert proposal["source_idea_id"] == idea_id
        assert proposal["accepted_idea_evaluation_id"] == source_before["accepted_evaluation_id"]
        assert proposal["mapping_hash"]
        assert proposal["source_values_snapshot"]["idea_number"]

        duplicate = client.post(
            "/api/v1/project-proposals",
            headers=headers,
            json={"source_idea_id": idea_id},
        )
        assert duplicate.status_code == 201
        assert duplicate.json()["id"] == proposal["id"]
        assert duplicate.json()["proposal_number"] == proposal["proposal_number"]

        stale = client.put(
            f"/api/v1/project-proposals/{proposal['id']}",
            headers={**headers, "If-Match": '"9999"'},
            json=_complete_payload(proposal),
        )
        assert stale.status_code == 412

        updated = client.put(
            f"/api/v1/project-proposals/{proposal['id']}",
            headers={**headers, "If-Match": f'"{proposal["revision_version"]}"'},
            json=_complete_payload(proposal),
        )
        assert updated.status_code == 200, updated.text
        proposal = updated.json()
        proposal = _action(client, headers, proposal, "submit")
        proposal = _action(client, headers, proposal, "start-review")
        assert all(item["status"] == "PASS" for item in proposal["review"]["checks"])
        proposal = _action(client, headers, proposal, "start-evaluation")

        configs = client.get(
            "/api/v1/project-proposals/admin/configurations/list",
            headers=headers,
        ).json()
        matrix = next(item for item in configs if item["kind"] == "project_proposal_evaluation_matrix")
        ratings = [
            {"criterion_code": item["code"], "rating": 4, "comment": "Validated"}
            for item in matrix["content_json"]["criteria"]
        ]
        proposal = _action(
            client,
            headers,
            proposal,
            "complete-evaluation",
            {"ratings": ratings, "comments": "Gate 07B evaluation complete"},
        )
        readiness = client.get(
            f"/api/v1/project-proposals/{proposal['id']}/gate-readiness",
            headers=headers,
        )
        assert readiness.status_code == 200
        assert readiness.json()["can_enter_strategic_gate"] is True
        assert readiness.json()["proposal_evaluation_id"] == proposal["evaluations"][-1]["id"]
        assert readiness.json()["readiness_hash"]
        proposal = _action(client, headers, proposal, "mark-gate-ready")
        assert proposal["status"] == "READY_FOR_STRATEGIC_GATE_DECISION"

        assert (
            client.post(
                f"/api/v1/project-proposals/{proposal['id']}/approve",
                headers={**headers, "If-Match": f'"{proposal["revision_version"]}"'},
            ).status_code
            == 404
        )
        assert (
            client.post(
                f"/api/v1/project-proposals/{proposal['id']}/reject",
                headers={**headers, "If-Match": f'"{proposal["revision_version"]}"'},
            ).status_code
            == 404
        )

        with SessionLocal() as db:
            idea = db.get(Idea, idea_id)
            evaluation = db.get(IdeaEvaluation, source_before["accepted_evaluation_id"])
            assert idea is not None and evaluation is not None
            assert idea.state == source_before["state"] == "ACCEPTED"
            assert idea.accepted_evaluation_id == source_before["accepted_evaluation_id"]
            assert idea.owning_workspace_id == source_before["owning_workspace_id"]
            assert idea.strategic_objective_codes == source_before["objectives"]
            assert str(evaluation.total_score) == source_before["evaluation_score"]
            assert int(db.scalar(select(func.count(EnterpriseWorkspace.id))) or 0) == workspace_count_before
            assert (
                db.scalar(
                    select(SecurityEvent.id).where(
                        SecurityEvent.target_type == "ProjectProposal",
                        SecurityEvent.target_id == proposal["id"],
                        SecurityEvent.event_type == "project_proposal.ready_for_strategic_gate",
                    )
                )
                is not None
            )


def test_gate07b_blocks_ineligible_source_and_keeps_evaluations_immutable() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        idea_id, _snapshot = _accepted_idea(state="EVALUATED")
        preview = client.post(
            "/api/v1/project-proposals/preview",
            headers=headers,
            json={"source_idea_id": idea_id},
        )
        assert preview.status_code == 200
        assert "IDEA_NOT_ACCEPTED" in preview.json()["blockers"]
        blocked = client.post(
            "/api/v1/project-proposals",
            headers=headers,
            json={"source_idea_id": idea_id},
        )
        assert blocked.status_code == 409

        with SessionLocal() as db:
            evaluation = db.scalar(select(ProjectProposalEvaluation).order_by(ProjectProposalEvaluation.id.desc()))
            if evaluation is not None:
                evaluation.comments = "Attempted mutation"
                try:
                    db.commit()
                    raise AssertionError("Immutable Proposal evaluation update unexpectedly committed")
                except ValueError:
                    db.rollback()


def test_gate07b_return_resubmit_cancel_and_related_idea_api() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        idea_id, _snapshot = _accepted_idea()
        proposal = client.post(
            "/api/v1/project-proposals",
            headers=headers,
            json={"source_idea_id": idea_id},
        ).json()
        updated = client.put(
            f"/api/v1/project-proposals/{proposal['id']}",
            headers={**headers, "If-Match": f'"{proposal["revision_version"]}"'},
            json=_complete_payload(proposal),
        )
        assert updated.status_code == 200, updated.text
        proposal = _action(client, headers, updated.json(), "submit")
        proposal = _action(
            client,
            headers,
            proposal,
            "return",
            {"reason": "Clarify the preliminary scope"},
        )
        assert proposal["status"] == "RETURNED"
        corrected_payload = _complete_payload(proposal)
        corrected_payload["preliminary_scope"] += " Scope clarification completed."
        corrected = client.put(
            f"/api/v1/project-proposals/{proposal['id']}",
            headers={**headers, "If-Match": f'"{proposal["revision_version"]}"'},
            json=corrected_payload,
        )
        assert corrected.status_code == 200
        proposal = _action(client, headers, corrected.json(), "submit")
        proposal = _action(
            client,
            headers,
            proposal,
            "return",
            {"reason": "Business case withdrawn before review"},
        )
        proposal = _action(client, headers, proposal, "cancel")
        assert proposal["status"] == "CANCELLED"
        related = client.get(f"/api/v1/ideas/{idea_id}/project-proposals", headers=headers)
        assert related.status_code == 200
        assert [item["id"] for item in related.json()] == [proposal["id"]]

        with SessionLocal() as db:
            stored = db.get(ProjectProposal, proposal["id"])
            assert stored is not None
            assert stored.source_idea_id == idea_id
