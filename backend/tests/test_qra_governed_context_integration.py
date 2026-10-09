"""Actual prerequisite providers and upstream preservation in an approved model."""

from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select, text
from tests.test_qra_foundation import _approve, _draft_model, _fixture, _key, _ready_sources

from app.database.session import SessionLocal
from app.domain.models import AdminConfiguration
from app.main import app
from app.modules.basic_data.service import _hash, _json
from app.modules.qra_foundation.schemas import ActionIn
from app.modules.qra_foundation.service import CONFIGURATION_KIND


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as value:
        yield value


def _upstream_fingerprint(db):
    """Freeze all actual upstream rows, not only the happy Project's few fields."""
    present = set(inspect(db.bind).get_table_names())
    domains = (
        "project_risks",
        "risk_readiness_assessments",
        "risk_register_entries",
        "basic_data_readiness_assessments",
        "project_basic_data_items",
        "owner_capability_assessments",
        "project_fel_statuses",
        "project_definition_assessments",
        "project_definition_actions",
        "business_cases",
        "business_case_revisions",
        "economic_financial_models",
        "economic_financial_model_versions",
        "financial_model_periods",
        "portfolio_budget_scenarios",
        "portfolio_budget_scenario_projects",
        "portfolio_resource_scenarios",
        "portfolio_resource_scenario_projects",
        "schedule_imports",
        "schedule_activity_maps",
        "activity_relationships",
        "schedule_validation_findings",
        "baseline_versions",
        "control_accounts",
        "activities",
        "wbs",
        "investment_gate_preparations",
        "investment_gate_evidence_items",
        "investment_decisions",
        "investment_decision_votes",
    )
    result = {
        table: _hash(_json([dict(row) for row in db.execute(text(f'SELECT * FROM "{table}" ORDER BY id')).mappings()]))
        for table in domains
        if table in present
    }
    policies = db.execute(
        select(AdminConfiguration.__table__)
        .where(AdminConfiguration.kind != CONFIGURATION_KIND)
        .order_by(AdminConfiguration.id)
    ).mappings()
    result["upstream_admin_configurations"] = _hash(_json([dict(row) for row in policies]))
    return result


def test_qra_approved_model_consumes_current_real_governed_prerequisites_without_mutation(client):
    with SessionLocal() as db:
        fixture = _fixture(db, contexts=True)
        service, project = fixture["preparer"], fixture["project"]
        contexts = service.contexts(project.id)
        for provider in ("basic_data", "owner_capability"):
            assert contexts[provider]["status"] == "AVAILABLE"
            assert contexts[provider]["source_current"] is True
        assert contexts["risk_readiness"]["status"] == "READY"
        assert contexts["risk_readiness"]["source_current"] is True
        assert contexts["risk_governance"]["status"] == "AVAILABLE"
        assert contexts["risk_governance"]["source"]
        assert contexts["fel_pdri"]["fel_stage"] == "FEL-3"
        assert contexts["fel_pdri"]["fel_provider_context"]["source_current"] is True
        before = _upstream_fingerprint(db)
        sources = _ready_sources(fixture)
        approved = _approve(fixture, _draft_model(fixture, sources))
        frozen = deepcopy(approved)
        assert approved["status"] == "APPROVED_FOR_ANALYSIS"
        assert approved["snapshot_json"]["derived_output"] == "READY_FOR_QRA_ANALYSIS"
        assert set(approved["snapshot_json"]["contexts"]) >= {
            "risk_readiness",
            "risk_governance",
            "basic_data",
            "owner_capability",
            "fel_pdri",
        }
        assert _upstream_fingerprint(db) == before
        current = fixture["final"].current_readiness(project.id, "model")
        assert current["source_current"] is True
        assert current["status"] == "APPROVED_FOR_ANALYSIS"
        assert fixture["final"].record("model", approved["id"])["snapshot_json"] == frozen["snapshot_json"]
        assert _upstream_fingerprint(db) == before
        for kind, row in {**sources, "model": approved}.items():
            preview = service.refresh_preview(kind, row["id"])
            assert preview["persisted"] is False
            successor = service.refresh_apply(
                kind, row["id"], row["revision_version"], ActionIn(), _key(f"governed-{kind}-refresh")
            )
            assert successor["status"] == "DRAFT"
            assert successor["predecessor_id"] == row["id"]
            assert fixture["final"].record(kind, row["id"])["hash"] == row["hash"]
            assert _upstream_fingerprint(db) == before
