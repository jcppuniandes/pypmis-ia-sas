"""Real PostgreSQL acceptance evidence for Gate 07J-FUND."""

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import inspect
from tests.test_funds_manager_gate07j_fund import (
    _active_fund,
    _active_source,
    _confirmed_recommended_set_assignment,
    _published_policy,
)
from tests.test_investment_gate_preparation_gate07j import _source

from app.database.session import engine
from app.modules.funds_manager.service import FundsManagerService

pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql", reason="PostgreSQL Gate 07J-FUND evidence required"
)


def test_gate07j_fund_postgresql_schema_and_governed_readiness_lifecycle() -> None:
    assert {
        "strategic_funding_sources",
        "funds",
        "funding_assignments",
        "funding_readiness_snapshots",
    }.issubset(set(inspect(engine).get_table_names()))
    db, tenant_id, actor_id, portfolio, _projects, _convergence = _source()
    try:
        _published_policy(
            db,
            tenant_id,
            actor_id,
            fund_creator_cannot_authorize=False,
            assignment_preparer_cannot_confirm=False,
        )
        service = FundsManagerService(db, tenant_id, actor_id)
        required = Decimal(str(service._funding_requirement(portfolio.id)["required_amount"]))
        source = _active_source(service)
        fund = _active_fund(service, source, required)
        assignment = _confirmed_recommended_set_assignment(service, fund, portfolio.id, required)

        preview = service.refresh_preview(portfolio.id)
        idempotency_key = f"postgres-funding-{uuid4()}"
        first = service.refresh(portfolio.id, preview.proposed_source_hash, idempotency_key)
        replay = service.refresh(portfolio.id, preview.proposed_source_hash, idempotency_key)

        assert first.snapshot_id is not None
        assert first.funding_readiness_status == "READY"
        assert first.can_supply_investment_gate_evidence is True
        assert replay.snapshot_id == first.snapshot_id
        assert replay.funding_readiness_hash == first.funding_readiness_hash

        release_key = f"postgres-release-{uuid4()}"
        released = service.transition_funding_assignment(
            assignment.id,
            assignment.revision_version,
            "release",
            release_key,
        )
        release_replay = service.transition_funding_assignment(
            assignment.id,
            assignment.revision_version,
            "release",
            release_key,
        )
        assert released.status == "RELEASED"
        assert release_replay.id == released.id
        assert service.fund(fund.id).available_amount == required
        stale = service.readiness(portfolio.id)
        assert stale.funding_readiness_status == "STALE"
        assert stale.source_current is False
        blocked_preview = service.refresh_preview(portfolio.id)
        blocked = service.refresh(
            portfolio.id,
            blocked_preview.proposed_source_hash,
            f"postgres-refresh-after-release-{uuid4()}",
        )
        assert blocked.funding_readiness_status == "BLOCKED"
        assert blocked.funding_gap == required
    finally:
        db.close()
