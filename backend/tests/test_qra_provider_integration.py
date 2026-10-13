"""Independent registry, authority and historical-provider acceptance."""

from copy import deepcopy

import pytest
from sqlalchemy import select
from tests.test_qra_foundation import _approve, _draft_model, _draft_source, _fixture, _ready_sources
from tests.test_qra_foundation import client as client

from app.database.session import SessionLocal
from app.domain.models import AdminConfiguration, Base, ControlAccount
from app.modules.investment_evidence_policy.service import (
    DEFAULT_POLICY as GATE_DEFAULT,
)
from app.modules.investment_evidence_policy.service import (
    PROVIDER_REGISTRY,
    InvestmentEvidencePolicyService,
)
from app.modules.qra_foundation.service import CONFIGURATION_KIND, _hash


def _authorities(db, tenant_id):
    """Hash actual persisted rows, not fabricated provider availability."""
    names = (
        "enterprise_workspaces",
        "portfolio_resource_scenarios",
        "commercial_strategy_versions",
        "project_fel_statuses",
        "project_definition_assessments",
        "project_risks",
        "risk_readiness_assessments",
        "project_basic_data_items",
        "basic_data_readiness_assessments",
        "owner_capability_assessments",
        "owner_capability_commands",
        "business_case_revisions",
        "economic_financial_model_versions",
        "financial_model_assumptions",
        "financial_model_periods",
        "portfolio_budget_scenarios",
        "portfolio_budget_scenario_projects",
        "funding_readiness_snapshots",
        "strategic_benefits_plan_versions",
        "investment_gate_preparations",
        "investment_decisions",
        "post_fid_project_eligibilities",
        "portfolio_review_sessions",
        "schedule_imports",
        "schedule_activity_maps",
        "activity_relationships",
        "activities",
        "wbs",
        "baseline_versions",
        "security_roles",
        "security_access_assignments",
        "project_memberships",
        "control_accounts",
    )
    result = {}
    for name in names:
        table = Base.metadata.tables[name]
        rows = db.execute(select(table).where(table.c.tenant_id == tenant_id).order_by(table.c.id)).mappings()
        result[name] = _hash([dict(r) for r in rows])
    result["non_qra_policies"] = _hash(
        [
            {"id": r.id, "hash": r.content_hash, "content": r.content_json, "status": r.status}
            for r in db.scalars(
                select(AdminConfiguration)
                .where(AdminConfiguration.tenant_id == tenant_id, AdminConfiguration.kind != CONFIGURATION_KIND)
                .order_by(AdminConfiguration.id)
            )
        ]
    )
    return result


@pytest.mark.parametrize("kind", ["cost", "schedule"])
def test_registry_never_claims_project_evidence_from_a_draft(client, kind):
    with SessionLocal() as db:
        f = _fixture(db)
        _draft_source(f, kind)
        provider = f"{kind.upper()}_SOURCE_READINESS_PROVIDER"
        gate = InvestmentEvidencePolicyService(db, f["author"].tenant_id, f["author"].id)
        assert PROVIDER_REGISTRY[provider]["status"] == "AVAILABLE"  # Implemented contract, not project proof.
        assert gate._provider_payload(provider, {}, "EACH_PROJECT", f["project"].id) is None
        assert f["preparer"].provider_evidence(f["project"].id, kind)["status"] == "UNAVAILABLE"


def test_real_five_contexts_approved_model_and_providers_preserve_existing_authorities(client):
    with SessionLocal() as db:
        f = _fixture(db, contexts=True)
        before = _authorities(db, f["author"].tenant_id)
        gate_policy = deepcopy(GATE_DEFAULT)
        sources = _ready_sources(f)
        row = _approve(f, _draft_model(f, sources))
        assert row["status"] == "APPROVED_FOR_ANALYSIS"
        assert row["snapshot_json"]["derived_output"] == "READY_FOR_QRA_ANALYSIS"
        gate = InvestmentEvidencePolicyService(db, f["author"].tenant_id, f["author"].id)
        for kind in ("cost", "schedule"):
            provider = f"{kind.upper()}_SOURCE_READINESS_PROVIDER"
            proof = gate._provider_payload(provider, {}, "EACH_PROJECT", f["project"].id)
            assert proof["readiness_status"] == "READY"
            assert proof["evidence_hash"] == sources[kind]["hash"]
            assert proof["source_current"] and proof["blockers"] == []
            assert proof["evidence_type"] == f"{kind.upper()}_SOURCE_READINESS"
        assert GATE_DEFAULT == gate_policy
        assert "QRA_FOUNDATION_READINESS_PROVIDER" not in PROVIDER_REGISTRY
        assert _authorities(db, f["author"].tenant_id) == before


def test_changed_cost_authority_withdraws_provider_without_rewriting_history(client):
    with SessionLocal() as db:
        f = _fixture(db)
        sources = _ready_sources(f)
        historical = deepcopy(sources["cost"]["snapshot_json"])
        frozen_hash = sources["cost"]["hash"]
        account = db.scalar(select(ControlAccount).where(ControlAccount.project_id == f["operational_project"].id))
        account.budget += 1
        account.version += 1
        db.commit()
        gate = InvestmentEvidencePolicyService(db, f["author"].tenant_id, f["author"].id)
        assert gate._provider_payload("COST_SOURCE_READINESS_PROVIDER", {}, "EACH_PROJECT", f["project"].id) is None
        assert f["preparer"].provider_evidence(f["project"].id, "cost")["status"] == "UNAVAILABLE"
        old = f["preparer"].record("cost", sources["cost"]["id"])
        assert old["snapshot_json"] == historical and old["hash"] == frozen_hash
