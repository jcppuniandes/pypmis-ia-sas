"""Gate 07C acceptance tests for Strategic Gate Decision."""

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from tests.test_project_proposal_gate07b import _accepted_idea, _complete_payload, _headers

from app.database.session import SessionLocal
from app.domain.models import EnterpriseWorkspace, SecurityEvent
from app.main import app
from app.modules.project_proposal.models import ProjectProposal
from app.modules.strategic_gate.models import StrategicGateDecision


def _proposal_action(
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
    return response.json()


def _ready_proposal(client: TestClient, headers: dict[str, str]) -> dict:
    idea_id, _snapshot = _accepted_idea()
    created = client.post(
        "/api/v1/project-proposals",
        headers=headers,
        json={"source_idea_id": idea_id},
    )
    assert created.status_code == 201, created.text
    proposal = created.json()
    updated = client.put(
        f"/api/v1/project-proposals/{proposal['id']}",
        headers={**headers, "If-Match": f'"{proposal["revision_version"]}"'},
        json=_complete_payload(proposal),
    )
    assert updated.status_code == 200, updated.text
    proposal = _proposal_action(client, headers, updated.json(), "submit")
    proposal = _proposal_action(client, headers, proposal, "start-review")
    proposal = _proposal_action(client, headers, proposal, "start-evaluation")
    configurations = client.get(
        "/api/v1/project-proposals/admin/configurations/list",
        headers=headers,
    ).json()
    matrix = next(item for item in configurations if item["kind"] == "project_proposal_evaluation_matrix")
    ratings = [
        {"criterion_code": item["code"], "rating": 4, "comment": "Gate 07C source validated"}
        for item in matrix["content_json"]["criteria"]
    ]
    proposal = _proposal_action(
        client,
        headers,
        proposal,
        "complete-evaluation",
        {"ratings": ratings, "comments": "Ready for strategic decision"},
    )
    proposal = _proposal_action(client, headers, proposal, "mark-gate-ready")
    assert proposal["status"] == "READY_FOR_STRATEGIC_GATE"
    readiness = client.get(
        f"/api/v1/project-proposals/{proposal['id']}/gate-readiness",
        headers=headers,
    )
    assert readiness.status_code == 200
    assert readiness.json()["status"] == "READY_FOR_STRATEGIC_GATE_DECISION"
    return proposal


def _create_decision(client: TestClient, headers: dict[str, str], proposal: dict) -> dict:
    first = client.post(
        "/api/v1/strategic-gate-decisions/preview",
        headers=headers,
        json={"project_proposal_id": proposal["id"]},
    )
    second = client.post(
        f"/api/v1/project-proposals/{proposal['id']}/strategic-gate-decisions/preview",
        headers=headers,
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["decision_number_preview"] == second.json()["decision_number_preview"]
    assert first.json()["persisted"] is False
    assert first.json()["blockers"] == []
    created = client.post(
        "/api/v1/strategic-gate-decisions",
        headers={**headers, "Idempotency-Key": f"create-{proposal['id']}"},
        json={"project_proposal_id": proposal["id"]},
    )
    assert created.status_code == 201, created.text
    decision = created.json()
    duplicate = client.post(
        "/api/v1/strategic-gate-decisions",
        headers={**headers, "Idempotency-Key": f"create-{proposal['id']}"},
        json={"project_proposal_id": proposal["id"]},
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == decision["id"]
    assert duplicate.json()["decision_number"] == decision["decision_number"]
    return decision


def _decision_action(
    client: TestClient,
    headers: dict[str, str],
    decision: dict,
    path: str,
    body: dict | None = None,
) -> dict:
    response = client.post(
        f"/api/v1/strategic-gate-decisions/{decision['id']}/{path}",
        headers={
            **headers,
            "If-Match": f'"{decision["revision_version"]}"',
            "Idempotency-Key": f"{path}-{decision['id']}",
        },
        json=body,
    )
    assert response.status_code == 200, response.text
    assert response.headers["etag"] == f'"{response.json()["revision_version"]}"'
    return response.json()


def _prepare_for_review(client: TestClient, headers: dict[str, str], decision: dict) -> dict:
    updated = client.put(
        f"/api/v1/strategic-gate-decisions/{decision['id']}",
        headers={**headers, "If-Match": f'"{decision["revision_version"]}"'},
        json={
            "decision_reason": "Strategic case reviewed and ready for formal decision.",
            "decision_comments": "Prepared under Gate 07C.",
            "decision_maker_user_id": decision["prepared_by_user_id"],
            "conditions": [],
            "evidence_refs": [{"reference": "SGD-EVIDENCE"}],
            "committee": None,
        },
    )
    assert updated.status_code == 200, updated.text
    decision = _decision_action(client, headers, updated.json(), "submit")
    return _decision_action(client, headers, decision, "start-review")


def test_gate07c_approve_produces_portfolio_intake_readiness_only() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        proposal = _ready_proposal(client, headers)
        with SessionLocal() as db:
            workspace_count = int(db.scalar(select(func.count(EnterpriseWorkspace.id))) or 0)
        decision = _prepare_for_review(client, headers, _create_decision(client, headers, proposal))
        source_snapshot = deepcopy(decision["proposal_snapshot"])
        decision = _decision_action(
            client,
            headers,
            decision,
            "decide",
            {
                "outcome": "APPROVE",
                "reason": "Approved exclusively for Portfolio Intake.",
                "conditions": [{"code": "PORTFOLIO_VALIDATE_CAPACITY"}],
                "comments": "No FID, Candidate, Project or Workspace is authorized.",
            },
        )
        assert decision["state"] == "DECIDED"
        assert decision["outcome"] == "APPROVE"
        assert decision["decision_hash"]
        assert decision["proposal_snapshot"] == source_snapshot

        readiness = client.get(
            f"/api/v1/strategic-gate-decisions/{decision['id']}/portfolio-intake-readiness",
            headers=headers,
        )
        assert readiness.status_code == 200, readiness.text
        payload = readiness.json()
        assert payload["status"] == "READY_FOR_PORTFOLIO_INTAKE"
        assert payload["can_create_portfolio_candidate"] is False
        assert payload["decision_hash"] == decision["decision_hash"]
        assert payload["readiness_hash"]

        stored_proposal = client.get(
            f"/api/v1/project-proposals/{proposal['id']}",
            headers=headers,
        ).json()
        assert stored_proposal["status"] == "STRATEGIC_GATE_APPROVED"
        assert client.post("/api/v1/portfolio-candidates", headers=headers, json={}).status_code == 404
        with SessionLocal() as db:
            assert int(db.scalar(select(func.count(EnterpriseWorkspace.id))) or 0) == workspace_count
            assert (
                db.scalar(
                    select(SecurityEvent.id).where(
                        SecurityEvent.target_type == "StrategicGateDecision",
                        SecurityEvent.target_id == decision["id"],
                        SecurityEvent.event_type == "strategic_gate.approved",
                    )
                )
                is not None
            )


@pytest.mark.parametrize(
    ("outcome", "expected_status"),
    [
        ("RETURN", "RETURNED"),
        ("REJECT", "STRATEGIC_GATE_REJECTED"),
        ("DEFER", "STRATEGIC_GATE_DEFERRED"),
    ],
)
def test_gate07c_non_approval_outcomes_never_produce_portfolio_intake(
    outcome: str,
    expected_status: str,
) -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        proposal = _ready_proposal(client, headers)
        decision = _prepare_for_review(client, headers, _create_decision(client, headers, proposal))
        body = {
            "outcome": outcome,
            "reason": f"Controlled {outcome.lower()} decision.",
            "conditions": [{"code": "FOLLOW_UP"}],
            "comments": "Historical decision remains immutable.",
        }
        decision = _decision_action(client, headers, decision, "decide", body)
        assert decision["outcome"] == outcome
        assert (
            client.get(f"/api/v1/project-proposals/{proposal['id']}", headers=headers).json()["status"]
            == expected_status
        )
        readiness = client.get(
            f"/api/v1/strategic-gate-decisions/{decision['id']}/portfolio-intake-readiness",
            headers=headers,
        ).json()
        assert readiness["status"] == "GATE07C_REWORK_REQUIRED"
        assert readiness["can_create_portfolio_candidate"] is False
        assert "DECISION_NOT_APPROVED" in readiness["blockers"]


def test_gate07c_stale_readiness_etag_and_closed_history_are_protected() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        proposal = _ready_proposal(client, headers)
        decision = _create_decision(client, headers, proposal)
        stale = client.put(
            f"/api/v1/strategic-gate-decisions/{decision['id']}",
            headers={**headers, "If-Match": '"9999"'},
            json={
                "decision_reason": "Stale",
                "decision_comments": "",
                "conditions": [],
                "evidence_refs": [],
            },
        )
        assert stale.status_code == 412
        with SessionLocal() as db:
            stored = db.get(ProjectProposal, proposal["id"])
            assert stored is not None
            stored.name += " - changed after preview"
            db.commit()
        updated = client.put(
            f"/api/v1/strategic-gate-decisions/{decision['id']}",
            headers={**headers, "If-Match": f'"{decision["revision_version"]}"'},
            json={
                "decision_reason": "Prepared before source changed.",
                "decision_comments": "",
                "conditions": [],
                "evidence_refs": [],
            },
        )
        assert updated.status_code == 200
        stale_readiness = client.post(
            f"/api/v1/strategic-gate-decisions/{decision['id']}/submit",
            headers={
                **headers,
                "If-Match": f'"{updated.json()["revision_version"]}"',
                "Idempotency-Key": "stale-readiness",
            },
        )
        assert stale_readiness.status_code == 412
        assert stale_readiness.json()["detail"]["reason"] == "STALE_READINESS"


def test_gate07c_defer_allows_a_new_historical_round_without_overwrite() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        proposal = _ready_proposal(client, headers)
        first = _prepare_for_review(client, headers, _create_decision(client, headers, proposal))
        first = _decision_action(
            client,
            headers,
            first,
            "decide",
            {
                "outcome": "DEFER",
                "reason": "Wait for the next planning window.",
                "conditions": [],
                "comments": "No deferred-until restriction.",
            },
        )
        second = _decision_action(client, headers, first, "new-round")
        assert second["id"] != first["id"]
        assert second["gate_round"] == first["gate_round"] + 1
        related = client.get(
            f"/api/v1/project-proposals/{proposal['id']}/strategic-gate-decisions",
            headers=headers,
        )
        assert related.status_code == 200
        assert [item["gate_round"] for item in related.json()] == [2, 1]
        with SessionLocal() as db:
            closed = db.get(StrategicGateDecision, first["id"])
            assert closed is not None
            closed.decision_reason = "Attempted overwrite"
            with pytest.raises(ValueError):
                db.commit()
            db.rollback()


def test_gate07c_governs_committee_quorum_and_four_eyes_without_admin_bypass() -> None:
    with TestClient(app) as client:
        headers = _headers(client)
        records = client.get(
            "/api/v1/strategic-gate-decisions/admin/configurations/list",
            headers=headers,
        ).json()
        published = next(item for item in records if item["status"] == "published")
        clone = client.post(
            f"/api/v1/strategic-gate-decisions/admin/configurations/{published['id']}/clone",
            headers={**headers, "If-Match": f'"{published["version"]}"'},
        )
        assert clone.status_code == 200, clone.text
        draft = clone.json()
        committee_content = deepcopy(draft["content_json"])
        committee_content["decision_authority"] = {
            "mode": "COMMITTEE",
            "allowed_role": "gate_committee_member",
        }
        committee_content["committee_policy"] = {
            "enabled": True,
            "quorum_required": 1,
            "chair_required": True,
            "record_votes": True,
        }
        saved = client.put(
            f"/api/v1/strategic-gate-decisions/admin/configurations/{draft['id']}",
            headers={**headers, "If-Match": f'"{draft["version"]}"'},
            json={
                "name": draft["name"],
                "description": "Committee Gate 07C test",
                "content_json": committee_content,
            },
        )
        assert saved.status_code == 200, saved.text
        committee_config = client.post(
            f"/api/v1/strategic-gate-decisions/admin/configurations/{draft['id']}/publish",
            headers={**headers, "If-Match": f'"{saved.json()["version"]}"'},
        )
        assert committee_config.status_code == 200, committee_config.text

        proposal = _ready_proposal(client, headers)
        decision = _create_decision(client, headers, proposal)
        committee = {
            "members": [
                {
                    "user_id": decision["prepared_by_user_id"],
                    "role": "Chair",
                    "chair": True,
                }
            ],
            "votes": [{"user_id": decision["prepared_by_user_id"], "recommendation": "APPROVE"}],
            "quorum_required": 1,
        }
        updated = client.put(
            f"/api/v1/strategic-gate-decisions/{decision['id']}",
            headers={**headers, "If-Match": f'"{decision["revision_version"]}"'},
            json={
                "decision_reason": "Committee package ready.",
                "decision_comments": "Quorum evidence attached.",
                "conditions": [],
                "evidence_refs": [],
                "committee": committee,
            },
        )
        assert updated.status_code == 200, updated.text
        decision = _decision_action(client, headers, updated.json(), "submit")
        decision = _decision_action(client, headers, decision, "start-review")
        decided = _decision_action(
            client,
            headers,
            decision,
            "decide",
            {
                "outcome": "APPROVE",
                "reason": "Committee approved for Portfolio Intake.",
                "conditions": [],
                "comments": "Quorum met.",
                "committee": committee,
            },
        )
        assert decided["committee_snapshot"]["quorum_met"] is True

        clone_sod = client.post(
            f"/api/v1/strategic-gate-decisions/admin/configurations/{committee_config.json()['id']}/clone",
            headers={**headers, "If-Match": f'"{committee_config.json()["version"]}"'},
        ).json()
        sod_content = deepcopy(clone_sod["content_json"])
        sod_content["decision_authority"] = {
            "mode": "SINGLE_DECISION_MAKER",
            "allowed_role": "gate_decision_maker",
        }
        sod_content["four_eyes"] = {
            "decision_maker_cannot_be_proposal_creator": True,
            "decision_maker_cannot_be_proposal_evaluator": True,
        }
        saved_sod = client.put(
            f"/api/v1/strategic-gate-decisions/admin/configurations/{clone_sod['id']}",
            headers={**headers, "If-Match": f'"{clone_sod["version"]}"'},
            json={
                "name": clone_sod["name"],
                "description": "Four-Eyes Gate 07C test",
                "content_json": sod_content,
            },
        ).json()
        published_sod = client.post(
            f"/api/v1/strategic-gate-decisions/admin/configurations/{clone_sod['id']}/publish",
            headers={**headers, "If-Match": f'"{saved_sod["version"]}"'},
        )
        assert published_sod.status_code == 200, published_sod.text

        blocked_proposal = _ready_proposal(client, headers)
        blocked_decision = _prepare_for_review(
            client,
            headers,
            _create_decision(client, headers, blocked_proposal),
        )
        blocked = client.post(
            f"/api/v1/strategic-gate-decisions/{blocked_decision['id']}/decide",
            headers={
                **headers,
                "If-Match": f'"{blocked_decision["revision_version"]}"',
                "Idempotency-Key": "four-eyes-no-admin-bypass",
            },
            json={
                "outcome": "APPROVE",
                "reason": "This must be blocked by Four-Eyes.",
                "conditions": [],
                "comments": "",
            },
        )
        assert blocked.status_code == 403
        assert "Four-Eyes" in blocked.text or "SoD" in blocked.text
