"""Real PostgreSQL acceptance for the Gate 07M-EVID policy update."""

from copy import deepcopy

import pytest
from sqlalchemy import inspect, select
from tests.test_investment_gate_preparation_gate07j import _source

from app.database.session import engine
from app.domain.models import AdminConfiguration, SecurityEvent
from app.modules.investment_evidence_policy.service import (
    CONFIGURATION_KIND,
    InvestmentEvidencePolicyService,
)

pytestmark = pytest.mark.skipif(engine.dialect.name != "postgresql", reason="PostgreSQL Gate 07J-EVID required")


def test_gate07j_evid_reuses_admin_configuration_and_publishes_immutable_snapshot() -> None:
    tables = set(inspect(engine).get_table_names())
    assert "admin_configurations" in tables
    assert "investment_evidence_policies" not in tables
    assert "gate07m_evidence_policies" not in tables
    assert "business_cases" in tables
    assert "economic_financial_models" in tables
    assert "investment_decisions" in tables

    db, tenant_id, actor_id, portfolio, projects, _convergence = _source()
    try:
        service = InvestmentEvidencePolicyService(db, tenant_id, actor_id)
        service.ensure_seed()
        draft = next(item for item in service.configurations() if item.status == "draft")
        content = deepcopy(draft.content_json)
        preview = service.preview(
            portfolio_id=portfolio.id,
            gate_profile_code="PYP-FFA",
            project_ids=[project.id for project in projects],
            configuration_id=draft.id,
            content_override=content,
        )
        assert preview.persisted is False
        assert preview.can_enter_fid is False
        assert preview.recommended_next_development == {"next": "READY_TO_REVALIDATE_NEW_FID_PATH"}

        published = service.publish_configuration(draft.id, draft.version)
        snapshot = service.published_snapshot(
            portfolio.id,
            "PYP-FFA",
            [project.id for project in projects],
        )
        assert snapshot is not None
        assert snapshot["policy_id"] == published.id
        assert snapshot["policy_hash"] == published.content_hash
        assert published.content_json["effective_from"]
        assert snapshot["can_enter_fid"] is False
        rows = {item["evidence_type"]: item for item in snapshot["requirements"]}
        assert rows["BUSINESS_CASE_READINESS"]["classification"] == "A"
        assert rows["BUSINESS_CASE_READINESS"]["coverage_requirement"] == 100
        assert rows["ECONOMIC_FINANCIAL_READINESS"]["classification"] == "A"
        assert rows["ECONOMIC_FINANCIAL_READINESS"]["coverage_requirement"] == 100
        release = service.overview().release_contract
        assert release["business_case_provider_status"] == "AVAILABLE"
        assert release["economic_financial_provider_status"] == "AVAILABLE"
        assert release["missing_provider_count"] == 0
        assert release["exclusive_status"] == "GATE07M_EVID_POLICY_UPDATE_VALIDATED"
        assert release["final_output"] == "READY_FOR_BUSINESS_CASE_AND_ECONOMIC_FINANCIAL_GATE_EVIDENCE"
        assert db.scalar(
            select(SecurityEvent.id).where(
                SecurityEvent.tenant_id == tenant_id,
                SecurityEvent.event_type == "investment_evidence_policy.published",
            )
        )

        first_hash = published.content_hash
        clone = service.clone_configuration(published.id, published.version)
        revised = deepcopy(clone.content_json)
        revised["effective_from"] = None
        revised["policy_update_note"] = "Gate 07M-EVID PostgreSQL history acceptance"
        clone = service.update_configuration(clone.id, clone.version, clone.name, clone.description, revised)
        next_published = service.publish_configuration(clone.id, clone.version)
        db.refresh(published)
        assert published.status == "superseded"
        assert published.content_hash == first_hash
        assert next_published.revision == published.revision + 1
        assert next_published.content_hash != first_hash
        assert (
            db.scalar(
                select(AdminConfiguration.id).where(
                    AdminConfiguration.tenant_id == tenant_id,
                    AdminConfiguration.kind == CONFIGURATION_KIND,
                    AdminConfiguration.status == "published",
                )
            )
            == next_published.id
        )
    finally:
        db.close()
