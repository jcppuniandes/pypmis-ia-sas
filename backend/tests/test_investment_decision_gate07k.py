"""Gate 07K acceptance coverage for Investment Decision and FID governance."""

from copy import deepcopy
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from tests.test_investment_gate_preparation_gate07j import (
    _add_fel,
    _preparation,
    _profile,
    _reviewer,
    _source,
    _validate_latest_fel,
)

from app.core.time import utc_now
from app.domain.models import AdminConfiguration, EnterpriseWorkspace, UserAccount
from app.main import app
from app.modules.investment_decision.models import InvestmentDecision, InvestmentDecisionVote
from app.modules.investment_decision.schemas import (
    ChecklistAcknowledgement,
    DecisionCreateIn,
    DecisionDecideIn,
    DecisionReadyIn,
    DecisionUpdateIn,
    DecisionVoteIn,
)
from app.modules.investment_decision.service import (
    CONFIGURATION_KIND,
    DEFAULT_CONFIGURATION,
    InvestmentDecisionService,
    _hash,
)
from app.modules.investment_gate_preparation.schemas import EvidenceValidationIn, ManualEvidenceIn
from app.modules.investment_gate_preparation.service import InvestmentGatePreparationService


@pytest.fixture(scope="module", autouse=True)
def _started_application():
    with TestClient(app):
        yield


def _freeze_preparation(*, funding: bool = False):
    db, tenant_id, actor_id, portfolio, projects, _ = _source()
    profile = _profile(db, tenant_id, actor_id, funding=funding)
    reviewer = _reviewer(db, tenant_id)
    preparer = InvestmentGatePreparationService(db, tenant_id, actor_id)
    preparation = _preparation(preparer, portfolio.id, profile.id)
    for project in projects:
        preparation = _add_fel(
            preparer,
            preparation,
            project.id,
            fel_stage="FEL-3" if funding else "FEL-2",
        )
    if funding:
        preparation = preparer.add_evidence(
            preparation.id,
            preparation.revision_version,
            ManualEvidenceIn(
                requirement_key="funding-readiness",
                scope_type="PORTFOLIO",
                reference_id=f"FUNDING-{uuid4()}",
                evidence_date=utc_now(),
                issuer="Capital Funding Office",
                owner="Portfolio Governance",
                summary="Governed Full Funds Authorization readiness reference.",
                evidence_refs=[{"funding_readiness_hash": "f" * 64}],
                idempotency_key=f"gate07k-funding-{uuid4()}",
            ),
        )
    validator = InvestmentGatePreparationService(db, tenant_id, reviewer.id)
    for project in projects:
        preparation = _validate_latest_fel(validator, preparation, project.id)
    if funding:
        evidence = next(item for item in preparation.evidence if item.requirement_key == "funding-readiness")
        preparation = validator.validate_evidence(
            evidence.id,
            preparation.revision_version,
            EvidenceValidationIn(
                decision="VALID",
                validation_note="Independent funding evidence validation.",
                idempotency_key=f"gate07k-funding-validation-{uuid4()}",
            ),
        )
    preparation = preparer.ready_for_review(
        preparation.id, preparation.revision_version, f"gate07k-preparation-ready-{uuid4()}"
    )
    preparation = validator.freeze(
        preparation.id, preparation.revision_version, f"gate07k-preparation-freeze-{uuid4()}"
    )
    return db, tenant_id, actor_id, reviewer.id, portfolio, projects, preparation


def _maker(db, tenant_id: int, label: str = "Decision Maker") -> UserAccount:
    record = UserAccount(
        tenant_id=tenant_id,
        email=f"gate07k-maker-{uuid4().hex[:12]}@example.test",
        full_name=label,
        title="Investment Decision Authority",
        status="active",
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _next_configuration_revision(db, tenant_id: int) -> int:
    """Allocate a free revision when the module suite shares its SQLite app DB."""
    latest = db.scalar(
        select(func.max(AdminConfiguration.revision)).where(
            AdminConfiguration.tenant_id == tenant_id,
            AdminConfiguration.kind == CONFIGURATION_KIND,
            AdminConfiguration.code == "default",
        )
    )
    return int(latest or 0) + 1


def _decision_ready(db, tenant_id, actor_id, reviewer_id, preparation, maker_id):
    preparer = InvestmentDecisionService(db, tenant_id, actor_id)
    preparer.ensure_seed()
    decision = preparer.create(
        DecisionCreateIn(
            investment_gate_preparation_id=preparation.id,
            title="Formal governed investment decision",
            executive_summary="Frozen Gate 07J package reviewed without recalculating source scores.",
            idempotency_key=f"gate07k-create-{uuid4()}",
        )
    )
    decision = preparer.update(
        decision.id,
        decision.revision_version,
        DecisionUpdateIn(decision_maker_user_id=maker_id, rationale="Formal decision authority assigned."),
    )
    decision = preparer.submit(decision.id, decision.revision_version, f"gate07k-submit-{uuid4()}")
    reviewer = InvestmentDecisionService(db, tenant_id, reviewer_id)
    decision = reviewer.start_review(decision.id, decision.revision_version, f"gate07k-review-{uuid4()}")
    checklist = [
        ChecklistAcknowledgement(code=item["code"], acknowledged=True, note="Reviewed") for item in decision.checklist
    ]
    return reviewer.ready(
        decision.id,
        decision.revision_version,
        DecisionReadyIn(idempotency_key=f"gate07k-ready-{uuid4()}", checklist=checklist),
    )


def test_investment_selection_go_is_not_fid_and_has_no_project_activation() -> None:
    db, tenant_id, actor_id, reviewer_id, _portfolio, _projects, preparation = _freeze_preparation()
    try:
        maker = _maker(db, tenant_id)
        decision = _decision_ready(db, tenant_id, actor_id, reviewer_id, preparation, maker.id)
        before_workspaces = db.scalar(select(func.count()).select_from(EnterpriseWorkspace))
        maker_service = InvestmentDecisionService(db, tenant_id, maker.id)
        decided = maker_service.decide(
            decision.id,
            decision.revision_version,
            DecisionDecideIn(
                outcome="GO",
                rationale="Continue controlled development; this is not FID.",
                idempotency_key=f"gate07k-decide-{uuid4()}",
            ),
        )
        assert decided.outcome == "GO"
        assert decided.profile_code == "PYP-INV-SELECT"
        assert decided.is_fid is False
        assert decided.full_funds_authorized is False
        assert decided.investment_authorized is False
        assert decided.can_activate_project is False
        assert decided.authorization_output["final_output"] == "AUTHORIZED_TO_CONTINUE_PROJECT_DEVELOPMENT"
        assert db.scalar(select(func.count()).select_from(EnterpriseWorkspace)) == before_workspaces
        with pytest.raises(ValueError, match="immutable"):
            stored = db.get(InvestmentDecision, decided.id)
            stored.rationale = "Forbidden mutation"
            db.commit()
    finally:
        db.rollback()
        db.close()


def test_pyp_ffa_go_is_single_fid_and_duplicate_decide_is_idempotent() -> None:
    db, tenant_id, actor_id, reviewer_id, _portfolio, _projects, preparation = _freeze_preparation(funding=True)
    try:
        maker = _maker(db, tenant_id, "Independent FID Authority")
        preparer = InvestmentDecisionService(db, tenant_id, actor_id)
        preparer.ensure_seed()
        current = db.scalar(
            select(AdminConfiguration).where(
                AdminConfiguration.tenant_id == tenant_id,
                AdminConfiguration.kind == CONFIGURATION_KIND,
                AdminConfiguration.status == "published",
            )
        )
        limited_configuration = deepcopy(DEFAULT_CONFIGURATION)
        limited_configuration["authority_limits"] = {
            "enabled": True,
            "limits": [{"user_id": maker.id, "maximum_amount": "20000000.00", "currency": "USD"}],
        }
        db.add(
            AdminConfiguration(
                tenant_id=tenant_id,
                kind=CONFIGURATION_KIND,
                code="default",
                name="Gate 07K authority limits",
                description="Acceptance fixture for formal FID authority limits.",
                status="published",
                revision=current.revision + 1,
                version=1,
                content_json=limited_configuration,
                content_hash=_hash(limited_configuration),
                published_at=utc_now(),
                created_by_user_id=actor_id,
            )
        )
        db.commit()
        decision = _decision_ready(db, tenant_id, actor_id, reviewer_id, preparation, maker.id)
        maker_service = InvestmentDecisionService(db, tenant_id, maker.id)
        decision_count = db.scalar(
            select(func.count()).select_from(InvestmentDecision).where(InvestmentDecision.tenant_id == tenant_id)
        )
        with pytest.raises(HTTPException) as limit:
            maker_service.decide(
                decision.id,
                decision.revision_version,
                DecisionDecideIn(
                    outcome="GO",
                    rationale="Amount intentionally exceeds the frozen authority limit.",
                    authorized_amount=Decimal("25000000.00"),
                    authorized_currency="USD",
                    idempotency_key=f"gate07k-fid-limit-{uuid4()}",
                ),
            )
        assert limit.value.detail["code"] == "AUTHORITY_LIMIT_EXCEEDED"
        key = f"gate07k-fid-{uuid4()}"
        payload = DecisionDecideIn(
            outcome="GO",
            rationale="Approve Final Investment Decision and Full Funds Authorization.",
            authorized_amount=Decimal("12500000.00"),
            authorized_currency="USD",
            idempotency_key=key,
        )
        decided = maker_service.decide(decision.id, decision.revision_version, payload)
        duplicate = maker_service.decide(decision.id, decision.revision_version, payload)
        assert duplicate.id == decided.id
        assert duplicate.decision_hash == decided.decision_hash
        assert decided.is_fid is True
        assert decided.full_funds_authorized is True
        assert decided.investment_authorized is True
        assert decided.authorization_output["final_output"] == "FINAL_INVESTMENT_DECISION_GO"
        assert decided.authorization_output["post_fid_handoff"] == "READY_FOR_POST_FID_PROJECT_GOVERNANCE"
        assert decided.authorization_output["can_activate_project"] is False
        assert (
            db.scalar(
                select(func.count()).select_from(InvestmentDecision).where(InvestmentDecision.tenant_id == tenant_id)
            )
            == decision_count
        )
    finally:
        db.close()


@pytest.mark.parametrize(
    ("outcome", "extra", "expected_output"),
    [
        ("HOLD", {"hold_reason": "Await formal sponsor clarification."}, "INVESTMENT_SELECTION_HELD"),
        (
            "RECYCLE",
            {"recycle_target": "INVESTMENT_GATE_PREPARATION"},
            "INVESTMENT_SELECTION_RECYCLE_REQUIRED",
        ),
        ("KILL", {}, "INVESTMENT_SELECTION_KILLED"),
    ],
)
def test_alternate_outcomes_are_closed_without_fid(outcome, extra, expected_output) -> None:
    db, tenant_id, actor_id, reviewer_id, _portfolio, _projects, preparation = _freeze_preparation()
    try:
        maker = _maker(db, tenant_id)
        decision = _decision_ready(db, tenant_id, actor_id, reviewer_id, preparation, maker.id)
        decided = InvestmentDecisionService(db, tenant_id, maker.id).decide(
            decision.id,
            decision.revision_version,
            DecisionDecideIn(
                outcome=outcome,
                rationale=f"Governed {outcome} rationale.",
                idempotency_key=f"gate07k-{outcome.lower()}-{uuid4()}",
                **extra,
            ),
        )
        assert decided.is_fid is False
        assert decided.status == "DECIDED"
        assert decided.authorization_output["final_output"] == expected_output
    finally:
        db.close()


def test_ffa_segregation_of_duties_and_stale_policy_block_decision() -> None:
    db, tenant_id, actor_id, reviewer_id, _portfolio, _projects, preparation = _freeze_preparation(funding=True)
    try:
        preparer = InvestmentDecisionService(db, tenant_id, actor_id)
        preparer.ensure_seed()
        decision = preparer.create(
            DecisionCreateIn(
                investment_gate_preparation_id=preparation.id,
                title="SoD negative case",
                idempotency_key=f"gate07k-sod-create-{uuid4()}",
            )
        )
        decision = preparer.update(
            decision.id,
            decision.revision_version,
            DecisionUpdateIn(decision_maker_user_id=actor_id),
        )
        decision = preparer.submit(decision.id, decision.revision_version, f"gate07k-sod-submit-{uuid4()}")
        reviewer = InvestmentDecisionService(db, tenant_id, reviewer_id)
        decision = reviewer.start_review(decision.id, decision.revision_version, f"gate07k-sod-review-{uuid4()}")
        checklist = [
            ChecklistAcknowledgement(code=item["code"], acknowledged=True, note="Reviewed")
            for item in decision.checklist
        ]
        with pytest.raises(HTTPException) as sod:
            reviewer.ready(
                decision.id,
                decision.revision_version,
                DecisionReadyIn(
                    checklist=checklist,
                    idempotency_key=f"gate07k-sod-ready-{uuid4()}",
                ),
            )
        assert sod.value.detail["code"] == "DECISION_NOT_READY"
        assert "SEGREGATION_OF_DUTIES_VIOLATION" in sod.value.detail["blockers"]
        decision = reviewer.void(decision.id, decision.revision_version, f"gate07k-sod-void-{uuid4()}")

        maker = _maker(db, tenant_id, "Independent policy-staleness authority")
        decision = _decision_ready(db, tenant_id, actor_id, reviewer_id, preparation, maker.id)

        replacement_content = deepcopy(DEFAULT_CONFIGURATION)
        replacement_content["validity"]["authorization_validity_days"] = 365
        replacement = AdminConfiguration(
            tenant_id=tenant_id,
            kind=CONFIGURATION_KIND,
            code="default",
            name="Changed Gate 07K policy",
            description="Test policy staleness.",
            status="published",
            revision=_next_configuration_revision(db, tenant_id),
            version=1,
            content_json=replacement_content,
            content_hash=_hash(replacement_content),
            published_at=utc_now(),
            created_by_user_id=actor_id,
        )
        db.add(replacement)
        db.commit()
        readiness = InvestmentDecisionService(db, tenant_id, reviewer_id).readiness(decision.id)
        assert readiness.readiness_status == "STALE"
        assert "POLICY_MISMATCH" in readiness.blockers
    finally:
        db.close()


def test_committee_quorum_and_voting_rule_govern_decision() -> None:
    db, tenant_id, actor_id, reviewer_id, _portfolio, _projects, preparation = _freeze_preparation()
    try:
        chair = _maker(db, tenant_id, "Investment Committee Chair")
        member = _maker(db, tenant_id, "Investment Committee Member")
        observer = _maker(db, tenant_id, "Investment Committee Observer")
        preparer = InvestmentDecisionService(db, tenant_id, actor_id)
        preparer.ensure_seed()
        committee_configuration = deepcopy(DEFAULT_CONFIGURATION)
        committee_configuration["authority"]["model"] = "COMMITTEE"
        committee_configuration["committee"] = {
            "members": [
                {"user_id": chair.id, "role": "CHAIR", "voting_right": True},
                {"user_id": member.id, "role": "MEMBER", "voting_right": True},
                {"user_id": observer.id, "role": "OBSERVER", "voting_right": False},
            ],
            "chair_user_id": chair.id,
        }
        committee_configuration["quorum"] = {
            "minimum_member_count": 2,
            "minimum_percentage": 100,
            "chair_required": True,
        }
        configured = AdminConfiguration(
            tenant_id=tenant_id,
            kind=CONFIGURATION_KIND,
            code="default",
            name="Gate 07K committee authority",
            description="Committee quorum and simple-majority acceptance fixture.",
            status="published",
            revision=_next_configuration_revision(db, tenant_id),
            version=1,
            content_json=committee_configuration,
            content_hash=_hash(committee_configuration),
            published_at=utc_now(),
            created_by_user_id=actor_id,
        )
        db.add(configured)
        db.commit()

        decision = preparer.create(
            DecisionCreateIn(
                investment_gate_preparation_id=preparation.id,
                title="Committee-governed investment selection",
                idempotency_key=f"gate07k-committee-create-{uuid4()}",
            )
        )
        decision = preparer.submit(
            decision.id,
            decision.revision_version,
            f"gate07k-committee-submit-{uuid4()}",
        )
        reviewer = InvestmentDecisionService(db, tenant_id, reviewer_id)
        decision = reviewer.start_review(
            decision.id,
            decision.revision_version,
            f"gate07k-committee-review-{uuid4()}",
        )
        checklist = [
            ChecklistAcknowledgement(code=item["code"], acknowledged=True, note="Reviewed")
            for item in decision.checklist
        ]
        with pytest.raises(HTTPException) as no_quorum:
            reviewer.ready(
                decision.id,
                decision.revision_version,
                DecisionReadyIn(
                    checklist=checklist,
                    idempotency_key=f"gate07k-committee-no-quorum-{uuid4()}",
                ),
            )
        assert "QUORUM_NOT_MET" in no_quorum.value.detail["blockers"]

        chair_service = InvestmentDecisionService(db, tenant_id, chair.id)
        chair_service.cast_vote(
            decision.id,
            DecisionVoteIn(
                vote="GO",
                rationale="Chair supports the controlled selection decision.",
                idempotency_key=f"gate07k-chair-vote-{uuid4()}",
            ),
        )
        member_service = InvestmentDecisionService(db, tenant_id, member.id)
        member_service.cast_vote(
            decision.id,
            DecisionVoteIn(
                vote="HOLD",
                rationale="Initial dissent to exercise the voting rule.",
                idempotency_key=f"gate07k-member-hold-{uuid4()}",
            ),
        )
        decision = reviewer.ready(
            decision.id,
            decision.revision_version,
            DecisionReadyIn(
                checklist=checklist,
                idempotency_key=f"gate07k-committee-ready-{uuid4()}",
            ),
        )
        with pytest.raises(HTTPException) as split_vote:
            chair_service.decide(
                decision.id,
                decision.revision_version,
                DecisionDecideIn(
                    outcome="GO",
                    rationale="Split vote must not authorize a majority decision.",
                    idempotency_key=f"gate07k-split-decision-{uuid4()}",
                ),
            )
        assert split_vote.value.detail["code"] == "VOTING_RULE_NOT_MET"

        member_service.cast_vote(
            decision.id,
            DecisionVoteIn(
                vote="GO",
                rationale="Updated vote after governed committee deliberation.",
                idempotency_key=f"gate07k-member-go-{uuid4()}",
            ),
        )
        decided = chair_service.decide(
            decision.id,
            decision.revision_version,
            DecisionDecideIn(
                outcome="GO",
                rationale="Committee quorum and simple majority are satisfied.",
                idempotency_key=f"gate07k-committee-decision-{uuid4()}",
            ),
        )
        assert decided.status == "DECIDED"
        assert decided.authorization_output["final_output"] == "AUTHORIZED_TO_CONTINUE_PROJECT_DEVELOPMENT"
        assert decided.authorization_output["can_activate_project"] is False
    finally:
        db.close()


def test_vote_constraints_are_persistent() -> None:
    assert InvestmentDecisionVote.__tablename__ == "investment_decision_votes"
    assert {item.name for item in InvestmentDecisionVote.__table__.constraints} >= {
        "uq_investment_vote_member",
        "uq_investment_vote_key",
        "ck_investment_vote_value",
    }
