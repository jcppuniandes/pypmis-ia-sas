"""Real PostgreSQL acceptance for Gate 07J-EVID-2 decision criteria.

The increment is intentionally JSON-backed.  These tests prove that the
existing governed configuration and Gate 07J preparation aggregates persist
the new policy/snapshot contracts without introducing a parallel criteria
table or a second decision engine.
"""

from copy import deepcopy
from uuid import uuid4

import pytest
from sqlalchemy import inspect, select
from tests.test_investment_gate_preparation_gate07j import _preparation, _profile, _source

from app.core.time import utc_now
from app.database.session import SessionLocal, engine
from app.domain.models import AdminConfiguration, SecurityEvent
from app.modules.investment_evidence_policy.decision_criteria import (
    CONTROLLED_OPERATORS,
    DECISION_CRITERION_TYPES,
)
from app.modules.investment_evidence_policy.service import (
    CONFIGURATION_KIND as EVIDENCE_POLICY_KIND,
)
from app.modules.investment_evidence_policy.service import (
    DEFAULT_POLICY,
    EVID2_VALIDATED_RELEASE,
    InvestmentEvidencePolicyService,
    _hash,
)
from app.modules.investment_gate_preparation.models import InvestmentGatePreparation
from app.modules.investment_gate_preparation.service import InvestmentGatePreparationService

pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="PostgreSQL Gate 07J-EVID-2 acceptance required",
)


def _published_evid2_policy(
    db,
    tenant_id: int,
    actor_id: int,
    portfolio_id: int,
) -> AdminConfiguration:
    """Publish an isolated portfolio-scoped EVID-2 revision via the real service."""

    code = f"gate07j-evid2-pg-{uuid4().hex[:12]}"
    source_content = deepcopy(DEFAULT_POLICY)
    source_content["scope"] = {"type": "portfolio", "workspace_id": portfolio_id}
    source_content["effective_from"] = utc_now().isoformat()
    source = AdminConfiguration(
        tenant_id=tenant_id,
        kind=EVIDENCE_POLICY_KIND,
        code=code,
        name="PostgreSQL legacy evidence policy",
        description="Isolated source revision for Gate 07J-EVID-2 acceptance.",
        status="published",
        revision=1,
        version=1,
        content_json=source_content,
        content_hash=_hash(source_content),
        published_at=utc_now(),
        created_by_user_id=actor_id,
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    service = InvestmentEvidencePolicyService(db, tenant_id, actor_id)
    draft = service.clone_gate07j_evid2_configuration(source.id, source.version)
    duplicate = service.clone_gate07j_evid2_configuration(source.id, source.version)
    assert duplicate.id == draft.id
    return service.publish_configuration(draft.id, draft.version)


def test_evid2_reuses_existing_json_aggregates_and_roundtrips_published_policy() -> None:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert {"admin_configurations", "investment_gate_preparations"}.issubset(tables)
    assert {
        "gate_decision_criteria",
        "investment_decision_criteria",
        "investment_evidence_criteria",
        "gate07j_evid2_policies",
    }.isdisjoint(tables)
    admin_columns = {item["name"] for item in inspector.get_columns("admin_configurations")}
    preparation_columns = {item["name"] for item in inspector.get_columns("investment_gate_preparations")}
    assert "content_json" in admin_columns
    assert {"source_snapshot_json", "evidence_summary_json"}.issubset(preparation_columns)

    db, tenant_id, actor_id, portfolio, _projects, _convergence = _source()
    try:
        published = _published_evid2_policy(db, tenant_id, actor_id, portfolio.id)
        published_id = published.id
        expected_hash = published.content_hash
        expected_revision = published.revision

        assert published.status == "published"
        assert published.content_json["release_status"] == EVID2_VALIDATED_RELEASE
        criterion_policy = published.content_json["decision_criterion_policy"]
        assert tuple(criterion_policy["criterion_types"]) == DECISION_CRITERION_TYPES
        assert tuple(criterion_policy["controlled_operators"]) == CONTROLLED_OPERATORS
        assert criterion_policy["unsafe_expression_execution"] is False
        assert set(criterion_policy["criteria_by_profile"]) == {
            "PYP-INV-SELECT",
            "PYP-FFA",
        }
        assert db.scalar(
            select(SecurityEvent.id).where(
                SecurityEvent.tenant_id == tenant_id,
                SecurityEvent.event_type == "gate_policy.published",
                SecurityEvent.target_id == published.id,
            )
        )
    finally:
        db.close()

    # A separate session proves the nested criteria survived a PostgreSQL JSON
    # roundtrip rather than merely remaining in SQLAlchemy's identity map.
    with SessionLocal() as verification_db:
        persisted = verification_db.get(AdminConfiguration, published_id)
        assert persisted is not None
        assert persisted.revision == expected_revision
        assert persisted.content_hash == expected_hash
        assert persisted.content_json["decision_criterion_policy"]["criteria_by_profile"]["PYP-FFA"]
        assert persisted.content_hash == _hash(persisted.content_json)


def test_select_and_ffa_persist_proportional_and_strict_criteria_snapshots() -> None:
    db, tenant_id, actor_id, portfolio, _projects, _convergence = _source()
    try:
        published = _published_evid2_policy(db, tenant_id, actor_id, portfolio.id)
        select_profile = _profile(db, tenant_id, actor_id)
        ffa_profile = _profile(db, tenant_id, actor_id, funding=True)
        service = InvestmentGatePreparationService(db, tenant_id, actor_id)

        select_preparation = _preparation(service, portfolio.id, select_profile.id)
        ffa_preparation = _preparation(service, portfolio.id, ffa_profile.id)

        select_policy = select_preparation.criterion_policy_snapshot
        ffa_policy = ffa_preparation.criterion_policy_snapshot
        select_codes = {item["criterion_code"] for item in select_policy["criteria"]}
        ffa_codes = {item["criterion_code"] for item in ffa_policy["criteria"]}

        assert select_policy["policy_revision"] == published.revision
        assert select_policy["formal_decision_authority"] == "GATE07K"
        assert select_policy["portfolio_rank_authority"] == "PORTFOLIO"
        assert {
            "FIN-READINESS",
            "COMMERCIAL-READINESS",
            "BENEFIT-OWNER-COVERAGE",
            "FIN-NPV-HURDLE",
        }.isdisjoint(select_codes)
        assert {
            "FIN-READINESS",
            "COMMERCIAL-READINESS",
            "BENEFIT-OWNER-COVERAGE",
            "FIN-NPV-HURDLE",
        }.issubset(ffa_codes)
        assert len(select_codes) < len(ffa_codes)
        assert all(
            item["weight"] is None for item in ffa_policy["criteria"] if item["criterion_type"] == "PRIORITIZATION"
        )

        published_profiles = published.content_json["gate_profiles"]
        select_classifications = {
            item["evidence_type"]: item["classification"]
            for item in published_profiles["PYP-INV-SELECT"]["requirements"]
        }
        ffa_classifications = {
            item["evidence_type"]: item["classification"] for item in published_profiles["PYP-FFA"]["requirements"]
        }
        for evidence_type in (
            "ECONOMIC_FINANCIAL_READINESS",
            "CONTRACTING_STRATEGY_READINESS",
            "BENEFITS_PLAN_READINESS",
        ):
            assert select_classifications[evidence_type] == "B"
            assert ffa_classifications[evidence_type] == "A"

        select_id = select_preparation.id
        ffa_id = ffa_preparation.id
        select_evaluations = deepcopy(select_preparation.criterion_evaluations)
        ffa_evaluations = deepcopy(ffa_preparation.criterion_evaluations)
        assert select_evaluations
        assert ffa_evaluations
        assert all(item["policy_hash"] == select_policy["policy_hash"] for item in select_evaluations)
        assert all(item["policy_hash"] == ffa_policy["policy_hash"] for item in ffa_evaluations)
        assert select_preparation.portfolio_context_snapshot["rank_authority"] == "PORTFOLIO"
        assert ffa_preparation.portfolio_context_snapshot["rank_authority"] == "PORTFOLIO"
    finally:
        db.close()

    with SessionLocal() as verification_db:
        persisted_select = verification_db.get(InvestmentGatePreparation, select_id)
        persisted_ffa = verification_db.get(InvestmentGatePreparation, ffa_id)
        assert persisted_select is not None
        assert persisted_ffa is not None
        # PostgreSQL JSON serializes the audit timestamp while the just-built
        # aggregate still exposes it as a datetime. Compare the governed
        # evaluation contract rather than that transport representation.
        stable_fields = {
            "criterion_id",
            "criterion_code",
            "criterion_type",
            "operator",
            "threshold_or_expected_value",
            "result",
            "blocking",
            "required",
            "weight",
            "policy_revision",
            "policy_hash",
        }

        def stable_evaluations(rows):
            return [{key: item.get(key) for key in stable_fields} for item in rows]

        assert stable_evaluations(persisted_select.source_snapshot_json["criterion_evaluations"]) == stable_evaluations(
            select_evaluations
        )
        assert stable_evaluations(persisted_ffa.source_snapshot_json["criterion_evaluations"]) == stable_evaluations(
            ffa_evaluations
        )
        assert persisted_select.source_snapshot_json["decision_criterion_policy"] == select_policy
        assert persisted_ffa.source_snapshot_json["decision_criterion_policy"] == ffa_policy
        assert persisted_select.source_snapshot_json["portfolio_context_snapshot"]["rank_authority"] == "PORTFOLIO"
        assert persisted_ffa.source_snapshot_json["portfolio_context_snapshot"]["rank_authority"] == "PORTFOLIO"
