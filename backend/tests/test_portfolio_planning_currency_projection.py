"""Component regression for Proposal denomination across 07D -> 07E -> 07F.

The isolated test's Idea/Workspace/configuration helpers are component fixtures,
not a fresh Capital Owner release scenario or terminal-state UAT evidence. The
Proposal itself is created/updated through its ordinary API. No production or
historical Project is repaired, backfilled or silently assigned a currency.
"""

from copy import deepcopy
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from tests.test_portfolio_evaluation_gate07e import _complete, _portfolio, _project, _workspace_context
from tests.test_project_proposal_gate07b import _accepted_idea, _complete_payload, _headers

from app.database.session import SessionLocal
from app.domain.models import AdminConfiguration, EnterpriseWorkspace
from app.main import app
from app.modules.portfolio_analysis.schemas import AnalysisFiltersIn
from app.modules.portfolio_analysis.service import PortfolioAnalysisService
from app.modules.portfolio_evaluation.models import PortfolioProjectEvaluation
from app.modules.portfolio_evaluation.service import PortfolioEvaluationService
from app.modules.portfolio_planning.service import PortfolioPlanningService, _hash
from app.modules.project_proposal.models import ProjectProposal
from app.modules.strategic_gate.models import StrategicGateDecision


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def _proposal_usd_source(client, db, tenant_id, actor_id, owning_workspace_id):
    headers = _headers(client)
    idea_id, _ = _accepted_idea()
    created = client.post("/api/v1/project-proposals", headers=headers, json={"source_idea_id": idea_id})
    assert created.status_code == 201, created.text
    proposal = created.json()
    payload = _complete_payload(proposal)
    payload["currency_code"] = "USD"
    updated = client.put(
        f"/api/v1/project-proposals/{proposal['id']}",
        headers={**headers, "If-Match": f'"{proposal["revision_version"]}"'},
        json=payload,
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["currency_code"] == "USD"
    proposal = db.get(ProjectProposal, proposal["id"])
    assert proposal.currency_code == "USD"
    planning = PortfolioPlanningService(db, tenant_id, actor_id, None)
    planning.ensure_seed()
    configuration = db.scalar(
        select(AdminConfiguration).where(
            AdminConfiguration.tenant_id == tenant_id,
            AdminConfiguration.kind == "portfolio_planning_configuration",
            AdminConfiguration.code == "default",
        )
    )
    # The test isolates the snapshot projection; no invented decided Gate is
    # persisted or used as proof of an authorized investment lifecycle.
    decision = StrategicGateDecision(
        id=901,
        decision_number="COMPONENT-SNAPSHOT-ONLY",
        state="DRAFT",
        outcome=None,
        decision_hash="component-source-decision",
        conditions_json=[],
        strategic_objectives_snapshot_json=[{"code": "GROWTH"}],
        source_idea_snapshot_json={"id": idea_id},
        accepted_idea_evaluation_id=1,
        proposal_evaluation_id=1,
        owning_workspace_id=owning_workspace_id,
        proposal_score="80",
    )
    source = planning._source_snapshot(
        decision, proposal, SimpleNamespace(readiness_hash="component-readiness"), configuration, {}, {}
    )
    assert source["source_values"]["currency_code"] == "USD"
    assert source["proposal"]["currency_code"] == "USD"
    return planning, source


def _new_entry(planning, project, portfolio, membership, source):
    # Deliberately conflicting request/template defaults must not override the
    # denomination captured with the Proposal's ROM amount.
    request = SimpleNamespace(
        project_manager_user_id=planning.actor_id,
        source_decision_hash="component-source-decision",
        source_readiness_hash="component-readiness",
        currency_code="COP",
    )
    return planning._planning_entry_snapshot(request, project, portfolio, membership, source)


def test_proposal_usd_projects_to_new_planning_evaluation_and_analysis(client):
    tenant_id, actor_id, parent = _workspace_context()
    with SessionLocal() as db:
        planning, source = _proposal_usd_source(client, db, tenant_id, actor_id, parent.id)
        portfolio = _portfolio(db, tenant_id, actor_id, parent, f"Currency USD {uuid4().hex[:6]}")
        project, membership = _project(db, tenant_id, actor_id, parent, portfolio)
        entry = _new_entry(planning, project, portfolio, membership, source)
        assert entry["currency_code"] == entry["currency"] == "USD"
        project.defaults_json = {
            **dict(project.defaults_json),
            "_portfolio_planning": {
                "status": "READY_FOR_PORTFOLIO_PLANNING",
                "snapshot": entry,
                "planning_entry_hash": _hash(entry),
                "blocking_issues": [],
            },
        }
        db.commit()
        evaluation = _complete(PortfolioEvaluationService(db, tenant_id, actor_id), portfolio.id, project.id, 4)
        assert evaluation.source_snapshot["currency"] == "USD"
        assert evaluation.source_snapshot["planning_entry_snapshot"]["currency_code"] == "USD"
        analysis = PortfolioAnalysisService(db, tenant_id, actor_id)
        analysis.ensure_seed()
        dataset, _ = analysis._build_dataset(portfolio.id, AnalysisFiltersIn())
        assert len(dataset.rows) == 1
        assert dataset.rows[0].currency == "USD"
        assert "ROM_COST_CURRENCY_MISSING" not in dataset.warnings


@pytest.mark.parametrize("missing", [None, ""])
def test_missing_captured_currency_never_falls_back_to_request_or_proposal(client, missing):
    tenant_id, actor_id, parent = _workspace_context()
    with SessionLocal() as db:
        planning, source = _proposal_usd_source(client, db, tenant_id, actor_id, parent.id)
        portfolio = _portfolio(db, tenant_id, actor_id, parent, f"Currency absent {uuid4().hex[:6]}")
        project, membership = _project(db, tenant_id, actor_id, parent, portfolio)
        source["source_values"]["currency_code"] = missing
        # A nested Proposal containing USD is not a license to repair a damaged
        # captured source or use a COP request default while materializing.
        assert source["proposal"]["currency_code"] == "USD"
        entry = _new_entry(planning, project, portfolio, membership, source)
        assert entry["currency_code"] == entry["currency"] == missing
        matrix = db.scalar(
            select(AdminConfiguration).where(
                AdminConfiguration.tenant_id == tenant_id,
                AdminConfiguration.kind == "portfolio_evaluation_configuration",
                AdminConfiguration.content_json["scope"]["workspace_id"].as_integer() == portfolio.id,
            )
        )
        project.defaults_json = {
            **dict(project.defaults_json),
            "_portfolio_planning": {"snapshot": entry, "planning_entry_hash": _hash(entry)},
        }
        evaluated_source = PortfolioEvaluationService(db, tenant_id, actor_id)._source_snapshot(
            project, portfolio, membership, matrix
        )
        assert evaluated_source["currency"] == missing


def test_new_projection_does_not_backfill_historical_project_or_completed_evaluation(client):
    tenant_id, actor_id, parent = _workspace_context()
    with SessionLocal() as db:
        portfolio = _portfolio(db, tenant_id, actor_id, parent, f"Currency history {uuid4().hex[:6]}")
        historical, membership = _project(db, tenant_id, actor_id, parent, portfolio)
        old_entry = historical.defaults_json["_portfolio_planning"]["snapshot"]
        assert "currency" not in old_entry and "currency_code" not in old_entry
        db.commit()
        evaluation = _complete(PortfolioEvaluationService(db, tenant_id, actor_id), portfolio.id, historical.id, 4)
        stored = db.get(PortfolioProjectEvaluation, evaluation.id)
        historical_id, evaluation_id = historical.id, stored.id
        before = {
            "project_defaults": deepcopy(historical.defaults_json),
            "project_version": historical.version,
            "evaluation_source": deepcopy(stored.source_snapshot_json),
            "evaluation_hash": stored.source_snapshot_hash,
            "planning_hash": stored.planning_entry_hash,
            "evaluation_revision": stored.revision_version,
        }
        assert before["evaluation_source"]["currency"] is None
        planning, source = _proposal_usd_source(client, db, tenant_id, actor_id, parent.id)
        new_entry = _new_entry(planning, historical, portfolio, membership, source)
        assert new_entry["currency"] == "USD"
        db.commit()
        db.expire_all()
        historical = db.get(EnterpriseWorkspace, historical_id)
        stored = db.get(PortfolioProjectEvaluation, evaluation_id)
        assert historical.defaults_json == before["project_defaults"]
        assert historical.version == before["project_version"]
        assert stored.status == "COMPLETED"
        assert stored.source_snapshot_json == before["evaluation_source"]
        assert stored.source_snapshot_hash == before["evaluation_hash"]
        assert stored.planning_entry_hash == before["planning_hash"]
        assert stored.revision_version == before["evaluation_revision"]
