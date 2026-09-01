"""Real PostgreSQL acceptance for Gate 07J-EVID policy governance."""

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
    assert "investment_decisions" not in tables

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
        assert preview.recommended_next_development == {"next": "READY_TO_DESIGN_GATE07K"}

        published = service.publish_configuration(draft.id, draft.version)
        snapshot = service.published_snapshot(
            portfolio.id,
            "PYP-FFA",
            [project.id for project in projects],
        )
        assert snapshot is not None
        assert snapshot["policy_id"] == published.id
        assert snapshot["policy_hash"] == published.content_hash
        assert snapshot["can_enter_fid"] is False
        assert db.scalar(
            select(SecurityEvent.id).where(
                SecurityEvent.tenant_id == tenant_id,
                SecurityEvent.event_type == "investment_evidence_policy.published",
            )
        )
        assert (
            db.scalar(
                select(AdminConfiguration.id).where(
                    AdminConfiguration.tenant_id == tenant_id,
                    AdminConfiguration.kind == CONFIGURATION_KIND,
                    AdminConfiguration.status == "published",
                )
            )
            == published.id
        )
    finally:
        db.close()
