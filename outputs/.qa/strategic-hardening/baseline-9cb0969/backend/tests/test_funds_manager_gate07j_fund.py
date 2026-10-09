"""Gate 07J-FUND acceptance coverage for governed funding readiness."""

from copy import deepcopy
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from tests.test_investment_gate_preparation_gate07j import _source

from app.core.time import utc_now
from app.domain.models import AdminConfiguration, SecurityEvent
from app.main import app
from app.modules.funds_manager.schemas import (
    FundCreateIn,
    FundingAssignmentCreateIn,
    FundingSourceCreateIn,
)
from app.modules.funds_manager.service import (
    CONFIGURATION_KIND,
    DEFAULT_CONFIGURATION,
    READY_OUTPUT,
    FundsManagerService,
    _hash,
)


@pytest.fixture(scope="module", autouse=True)
def _started_application():
    with TestClient(app):
        yield


def _published_policy(db, tenant_id: int, actor_id: int, **overrides) -> AdminConfiguration:
    content = deepcopy(DEFAULT_CONFIGURATION)
    content["scope"] = {"type": "tenant", "workspace_id": None}
    content.update(overrides)
    revision = (
        int(
            db.scalar(
                select(func.coalesce(func.max(AdminConfiguration.revision), 0)).where(
                    AdminConfiguration.tenant_id == tenant_id,
                    AdminConfiguration.kind == CONFIGURATION_KIND,
                )
            )
            or 0
        )
        + 1
    )
    record = AdminConfiguration(
        tenant_id=tenant_id,
        kind=CONFIGURATION_KIND,
        code=f"gate07j-fund-{uuid4().hex[:10]}",
        name="Published Funds Manager policy",
        description="Isolated Gate 07J-FUND acceptance policy.",
        status="published",
        revision=revision,
        version=1,
        content_json=content,
        content_hash=_hash(content),
        created_by_user_id=actor_id,
        published_at=utc_now(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _active_source(service: FundsManagerService, currency: str = "COP"):
    source = service.create_funding_source(
        FundingSourceCreateIn(
            source_name=f"Corporate capital source {currency}",
            source_type="CORPORATE_CAPEX",
            currency=currency,
            effective_from=date(2027, 1, 1),
            effective_to=date(2027, 12, 31),
            evidence_refs=[{"reference": "BOARD-CAPEX-2027"}],
            idempotency_key=f"source-{currency}-{uuid4()}",
        )
    )
    return service.transition_funding_source(
        source.id,
        source.revision_version,
        "activate",
        f"source-activate-{uuid4()}",
    )


def _active_fund(service: FundsManagerService, source, amount: Decimal):
    fund = service.create_fund(
        FundCreateIn(
            fund_name="Strategic investment envelope",
            funding_source_id=source.id,
            currency=source.currency,
            authorized_amount=amount,
            available_from=date(2027, 1, 1),
            available_to=date(2027, 12, 31),
            period_granularity="YEAR",
            authorized_amount_by_period=[
                {
                    "period_key": "2027",
                    "period_start": date(2027, 1, 1),
                    "period_end": date(2027, 12, 31),
                    "amount": amount,
                }
            ],
            evidence_refs=[{"reference": "AUTHORITY-2027"}],
            idempotency_key=f"fund-create-{uuid4()}",
        )
    )
    fund = service.transition_fund(fund.id, fund.revision_version, "authorize", f"fund-authorize-{uuid4()}")
    return service.transition_fund(fund.id, fund.revision_version, "activate", f"fund-activate-{uuid4()}")


def _confirmed_recommended_set_assignment(service: FundsManagerService, fund, portfolio_id: int, amount: Decimal):
    contract = service._requirement_contract(portfolio_id)
    assignment = service.create_funding_assignment(
        FundingAssignmentCreateIn(
            fund_id=fund.id,
            scope_type="RECOMMENDED_PROJECT_SET",
            portfolio_workspace_id=portfolio_id,
            recommended_project_set_hash=contract["selected_project_set_hash"],
            source_convergence_id=contract["convergence_id"],
            source_recommendation_hash=contract["recommendation_hash"],
            amount=amount,
            currency=fund.currency,
            period_start=date(2027, 1, 1),
            period_end=date(2027, 12, 31),
            period_profile=[{"period_key": "2027", "amount": amount}],
            assignment_purpose="Governed coverage of the recommended project set.",
            evidence_refs=[{"reference": "FUNDING-COMMITTEE-2027"}],
            idempotency_key=f"assignment-create-{uuid4()}",
        )
    )
    return service.transition_funding_assignment(
        assignment.id,
        assignment.revision_version,
        "confirm",
        f"assignment-confirm-{uuid4()}",
    )


def _recommended_set_assignment(
    service: FundsManagerService,
    fund,
    portfolio_id: int,
    amount: Decimal,
    *,
    currency: str | None = None,
    period_end: date | None = date(2027, 12, 31),
    conditions: list[dict] | None = None,
    key: str | None = None,
):
    contract = service._requirement_contract(portfolio_id)
    return service.create_funding_assignment(
        FundingAssignmentCreateIn(
            fund_id=fund.id,
            scope_type="RECOMMENDED_PROJECT_SET",
            portfolio_workspace_id=portfolio_id,
            recommended_project_set_hash=contract["selected_project_set_hash"],
            source_convergence_id=contract["convergence_id"],
            source_recommendation_hash=contract["recommendation_hash"],
            amount=amount,
            currency=currency or fund.currency,
            period_start=None if period_end and period_end < date.today() else date(2027, 1, 1),
            period_end=period_end,
            assignment_purpose="Lifecycle closeout coverage allocation.",
            conditions=conditions or [],
            evidence_refs=[{"reference": "FUND-H-E2E"}],
            idempotency_key=key or f"assignment-create-{uuid4()}",
        )
    )


def test_confirmed_coverage_supplies_governed_gate07j_evidence_and_stales_explicitly() -> None:
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
        requirement = service._funding_requirement(portfolio.id)
        required = Decimal(str(requirement["required_amount"]))
        source = _active_source(service)
        fund = _active_fund(service, source, required)
        _confirmed_recommended_set_assignment(service, fund, portfolio.id, required)

        preview = service.refresh_preview(portfolio.id)
        assert preview.persisted is False
        assert preview.proposed_source_hash
        snapshot = service.refresh(portfolio.id, preview.proposed_source_hash, f"refresh-{uuid4()}")
        evidence = service.investment_gate_evidence(portfolio.id)

        assert snapshot.funding_readiness_status == "READY"
        assert snapshot.confirmed_coverage_percent == Decimal("100.0000")
        assert snapshot.final_output == READY_OUTPUT
        assert evidence.source_module == "FUNDS_MANAGER"
        assert evidence.evidence_type == "FUNDING_READINESS"
        assert evidence.requirement_type == "FUNDING_READINESS"
        assert evidence.evidence_origin == "GOVERNED_SOURCE"
        assert evidence.can_supply_investment_gate_evidence is True
        assert evidence.funding_readiness_hash == snapshot.funding_readiness_hash

        service.transition_funding_source(source.id, source.revision_version, "suspend", f"source-suspend-{uuid4()}")
        stale = service.readiness(portfolio.id)
        assert stale.funding_readiness_status == "STALE"
        assert stale.source_current is False
        assert stale.can_supply_investment_gate_evidence is False
        assert "STALE_FUNDING_SOURCE" in stale.blockers
    finally:
        db.close()


def test_currency_mismatch_without_governed_normalization_is_blocking() -> None:
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
        source = _active_source(service, "USD")
        fund = _active_fund(service, source, required)
        _confirmed_recommended_set_assignment(service, fund, portfolio.id, required)

        readiness = service.readiness(portfolio.id)
        assert readiness.funding_readiness_status == "BLOCKED"
        assert readiness.confirmed_funding_amount == 0
        assert "CURRENCY_NOT_COMPARABLE" in readiness.blockers
        assert readiness.can_supply_investment_gate_evidence is False
    finally:
        db.close()


def test_four_eyes_etag_and_idempotency_controls_are_enforced() -> None:
    db, tenant_id, actor_id, portfolio, _projects, _convergence = _source()
    try:
        _published_policy(db, tenant_id, actor_id, fund_creator_cannot_authorize=True)
        service = FundsManagerService(db, tenant_id, actor_id)
        source = _active_source(service)
        created = service.create_fund(
            FundCreateIn(
                fund_name="Four-eyes authorization envelope",
                funding_source_id=source.id,
                currency="COP",
                authorized_amount=Decimal("1000000"),
                idempotency_key="fund-four-eyes-create",
            )
        )
        replay = service.create_fund(
            FundCreateIn(
                fund_name="Four-eyes authorization envelope",
                funding_source_id=source.id,
                currency="COP",
                authorized_amount=Decimal("1000000"),
                idempotency_key="fund-four-eyes-create",
            )
        )
        assert replay.id == created.id
        assert service._policy(None, require_published=True)["fund_creator_cannot_authorize"] is True
        assert service._fund(created.id).created_by == actor_id

        with pytest.raises(HTTPException) as sod:
            service.transition_fund(created.id, created.revision_version, "authorize", "fund-four-eyes-authorize")
        assert sod.value.detail["code"] == "FUND_AUTHORIZATION_FOUR_EYES_REQUIRED"

        with pytest.raises(HTTPException) as stale:
            service.update_funding_source(
                source.id,
                0,
                FundingSourceCreateIn(
                    source_name=source.source_name,
                    source_type=source.source_type,
                    currency=source.currency,
                    effective_from=source.effective_from,
                    effective_to=source.effective_to,
                    restrictions=source.restrictions,
                    evidence_refs=source.evidence_refs,
                    source_reference=source.source_reference,
                    idempotency_key="unused-update-shape",
                ),
            )
        assert stale.value.status_code == 412
    finally:
        db.close()


def test_parent_child_assignments_do_not_double_count_aggregate_coverage() -> None:
    db, tenant_id, actor_id, portfolio, projects, _convergence = _source()
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
        fund = _active_fund(service, source, required * 2)
        parent = service.create_funding_assignment(
            FundingAssignmentCreateIn(
                fund_id=fund.id,
                scope_type="PORTFOLIO",
                portfolio_workspace_id=portfolio.id,
                amount=required,
                currency="COP",
                assignment_purpose="Portfolio funding envelope.",
                idempotency_key=f"parent-{uuid4()}",
            )
        )
        parent = service.transition_funding_assignment(
            parent.id, parent.revision_version, "confirm", f"parent-confirm-{uuid4()}"
        )
        child = service.create_funding_assignment(
            FundingAssignmentCreateIn(
                fund_id=fund.id,
                parent_assignment_id=parent.id,
                scope_type="PROJECT",
                project_workspace_id=projects[0].id,
                amount=Decimal("100000"),
                currency="COP",
                assignment_purpose="Controlled project sub-allocation.",
                idempotency_key=f"child-{uuid4()}",
            )
        )
        service.transition_funding_assignment(child.id, child.revision_version, "confirm", f"child-confirm-{uuid4()}")

        readiness = service.readiness(portfolio.id)
        assert readiness.confirmed_funding_amount == required
        assert readiness.confirmed_coverage_percent == Decimal("100.0000")
    finally:
        db.close()


def test_release_is_historical_idempotent_and_restores_fund_availability() -> None:
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
        confirmed = _confirmed_recommended_set_assignment(service, fund, portfolio.id, required)
        ready_preview = service.refresh_preview(portfolio.id)
        ready = service.refresh(portfolio.id, ready_preview.proposed_source_hash, f"ready-{uuid4()}")
        assert ready.funding_readiness_status == "READY"
        assert service.fund(fund.id).available_amount == 0

        key = f"release-{uuid4()}"
        released = service.transition_funding_assignment(
            confirmed.id,
            confirmed.revision_version,
            "release",
            key,
        )
        replay = service.transition_funding_assignment(confirmed.id, confirmed.revision_version, "release", key)
        assert released.status == "RELEASED"
        assert replay.id == released.id
        assert replay.revision_version == released.revision_version
        assert service.fund(fund.id).available_amount == required
        assert service.funding_assignment(released.id).status == "RELEASED"

        stale = service.readiness(portfolio.id)
        assert stale.funding_readiness_status == "STALE"
        assert stale.source_current is False
        blocked_preview = service.refresh_preview(portfolio.id)
        blocked = service.refresh(portfolio.id, blocked_preview.proposed_source_hash, f"blocked-{uuid4()}")
        assert blocked.funding_readiness_status == "BLOCKED"
        assert blocked.confirmed_funding_amount == 0
        assert blocked.funding_gap == required
        assert (
            db.scalar(
                select(func.count(SecurityEvent.id)).where(
                    SecurityEvent.tenant_id == tenant_id,
                    SecurityEvent.event_type == "funding_assignment.released",
                    SecurityEvent.target_id == released.id,
                )
            )
            == 1
        )
    finally:
        db.close()


def test_expiry_is_derived_and_historical_without_persisted_transition() -> None:
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
        draft = _recommended_set_assignment(
            service,
            fund,
            portfolio.id,
            required,
            period_end=date.today() - timedelta(days=1),
        )
        confirmed = service.transition_funding_assignment(
            draft.id,
            draft.revision_version,
            "confirm",
            f"expired-confirm-{uuid4()}",
        )

        historical = service.funding_assignment(confirmed.id)
        readiness = service.readiness(portfolio.id)
        assert historical.status == "CONFIRMED"
        assert "ASSIGNMENT_EXPIRED" in historical.warnings
        assert readiness.funding_readiness_status == "EXPIRED"
        assert readiness.confirmed_funding_amount == 0
        assert readiness.funding_gap == required
        assert "EXPIRED_FUNDING_NOT_COUNTED" in readiness.warnings
        assert "REQUIRED_FUNDING_EXPIRED" in readiness.blockers
    finally:
        db.close()


def test_partial_restriction_condition_and_overallocation_negative_controls() -> None:
    db, tenant_id, actor_id, portfolio, _projects, _convergence = _source()
    try:
        _published_policy(
            db,
            tenant_id,
            actor_id,
            fund_creator_cannot_authorize=False,
            assignment_preparer_cannot_confirm=False,
            allow_reserved_overbooking=False,
        )
        service = FundsManagerService(db, tenant_id, actor_id)
        required = Decimal(str(service._funding_requirement(portfolio.id)["required_amount"]))
        source = _active_source(service)
        fund = _active_fund(service, source, required)
        confirmed_draft = _recommended_set_assignment(service, fund, portfolio.id, required * Decimal("0.70"))
        service.transition_funding_assignment(
            confirmed_draft.id,
            confirmed_draft.revision_version,
            "confirm",
            f"partial-confirm-{uuid4()}",
        )
        reserved_draft = _recommended_set_assignment(service, fund, portfolio.id, required * Decimal("0.20"))
        service.transition_funding_assignment(
            reserved_draft.id,
            reserved_draft.revision_version,
            "reserve",
            f"partial-reserve-{uuid4()}",
        )
        partial = service.readiness(portfolio.id)
        assert partial.confirmed_coverage_percent == Decimal("70.0000")
        assert partial.potential_coverage_percent == Decimal("90.0000")
        assert partial.funding_gap == required * Decimal("0.30")
        assert partial.funding_readiness_status == "BLOCKED"

        over = _recommended_set_assignment(service, fund, portfolio.id, required * Decimal("0.70"))
        with pytest.raises(HTTPException) as over_allocation:
            service.transition_funding_assignment(
                over.id,
                over.revision_version,
                "confirm",
                f"over-confirm-{uuid4()}",
            )
        assert over_allocation.value.detail["code"] == "FUND_AVAILABLE_AMOUNT_EXCEEDED"
        assert service.fund(fund.id).available_amount == required * Decimal("0.10")

        restricted = service.create_fund(
            FundCreateIn(
                fund_name="Restricted lifecycle closeout fund",
                funding_source_id=source.id,
                currency="COP",
                authorized_amount=required,
                restrictions={"portfolio_ids": [portfolio.id + 999_999]},
                idempotency_key=f"restricted-fund-{uuid4()}",
            )
        )
        restricted = service.transition_fund(
            restricted.id, restricted.revision_version, "authorize", f"restricted-authorize-{uuid4()}"
        )
        restricted = service.transition_fund(
            restricted.id, restricted.revision_version, "activate", f"restricted-activate-{uuid4()}"
        )
        restricted_assignment = _recommended_set_assignment(service, restricted, portfolio.id, required)
        service.transition_funding_assignment(
            restricted_assignment.id,
            restricted_assignment.revision_version,
            "confirm",
            f"restricted-confirm-{uuid4()}",
        )
        restricted_readiness = service.readiness(portfolio.id)
        assert restricted_readiness.restriction_summary["ineligible_assignments"] == 1
        assert "PORTFOLIO_RESTRICTION_MISMATCH" in restricted_readiness.warnings

        conditioned_fund = _active_fund(service, source, required)
        conditioned = _recommended_set_assignment(
            service,
            conditioned_fund,
            portfolio.id,
            required,
            conditions=[{"code": "BOARD_CONSENT", "status": "OPEN", "blocking": True}],
        )
        service.transition_funding_assignment(
            conditioned.id,
            conditioned.revision_version,
            "confirm",
            f"condition-confirm-{uuid4()}",
        )
        conditioned_readiness = service.readiness(portfolio.id)
        assert conditioned_readiness.conditions_summary["open_blocking"] == 1
        assert "OPEN_BLOCKING_FUNDING_CONDITION" in conditioned_readiness.blockers
    finally:
        db.close()


def test_contractor_delivery_is_optional_through_portfolio_membership_context() -> None:
    db, tenant_id, actor_id, portfolio, projects, _convergence = _source()
    try:
        for project in projects:
            context = deepcopy(project.defaults_json or {})
            context.setdefault("_project", {})["governance_model"] = "CONTRACTOR_DELIVERY"
            project.defaults_json = context
        db.commit()
        _published_policy(db, tenant_id, actor_id)
        service = FundsManagerService(db, tenant_id, actor_id)

        overview = service.overview(portfolio.id)
        project_overview = service.project_funding(projects[0].id)
        assert overview.governance_model_applicable is False
        assert project_overview.governance_model_applicable is False
        assert overview.funding_readiness == "NOT_STARTED"
        assert overview.readiness is None
    finally:
        db.close()
