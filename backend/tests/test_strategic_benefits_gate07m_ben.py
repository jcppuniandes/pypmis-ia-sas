"""Gate 07M-BEN acceptance coverage for governed Strategic Benefits Plans."""

from __future__ import annotations

from copy import deepcopy
from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.session import SessionLocal
from app.domain.models import AdminConfiguration, EnterpriseWorkspace, UserAccount
from app.main import app
from app.modules.investment_evidence_policy.service import (
    DEFAULT_POLICY,
    PROVIDER_REGISTRY,
    InvestmentEvidencePolicyService,
)
from app.modules.strategic_benefits.models import (
    StrategicBenefit,
    StrategicBenefitsPlanVersion,
)
from app.modules.strategic_benefits.schemas import (
    BenefitCreateIn,
    BenefitMeasureCreateIn,
    BenefitOwnerIn,
    BenefitUpdateIn,
)
from app.modules.strategic_benefits.service import (
    EVIDENCE_TYPE,
    PROVIDER_KEY,
    SOURCE_MODULE,
    StrategicBenefitsService,
)


@pytest.fixture(scope="module", autouse=True)
def _started_application():
    with TestClient(app):
        yield


def _fixture() -> tuple[Session, UserAccount, EnterpriseWorkspace, StrategicBenefitsService]:
    db = SessionLocal()
    actor = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
    assert actor is not None
    suffix = uuid4().hex[:10]
    parent = db.scalar(
        select(EnterpriseWorkspace)
        .where(
            EnterpriseWorkspace.tenant_id == actor.tenant_id,
            EnterpriseWorkspace.workspace_type_code.in_(["enterprise", "business-unit", "portfolio"]),
        )
        .order_by(EnterpriseWorkspace.id)
    )
    if parent is None:
        parent = EnterpriseWorkspace(
            tenant_id=actor.tenant_id,
            parent_id=None,
            workspace_type_code="enterprise",
            code=f"BEN-ENT-{suffix}",
            external_key=f"ben-ent-{suffix}",
            record_code=f"BEN.ENT.{suffix}",
            name="Strategic Benefits Enterprise",
            status="active",
            defaults_json={},
            sort_order=1,
            version=1,
            created_by_user_id=actor.id,
        )
        db.add(parent)
        db.flush()
    project = EnterpriseWorkspace(
        tenant_id=actor.tenant_id,
        parent_id=parent.id,
        workspace_type_code="project",
        code=f"BEN-PRJ-{suffix}",
        external_key=f"ben-prj-{suffix}",
        record_code=f"BEN.PRJ.{suffix}",
        name=f"Strategic Benefits Project {suffix}",
        status="active",
        defaults_json={
            "_project": {
                "project_type": "CAPITAL",
                "governance_model": "CAPITAL_OWNER",
                "fel_stage": "FEL-3",
            }
        },
        sort_order=1,
        version=1,
        created_by_user_id=actor.id,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    service = StrategicBenefitsService(db, actor.tenant_id, actor.id)
    service.ensure_seed()
    return db, actor, project, service


def _reviewer(db: Session, actor: UserAccount) -> UserAccount:
    reviewer = UserAccount(
        tenant_id=actor.tenant_id,
        email=f"ben-reviewer-{uuid4().hex[:10]}@example.test",
        full_name="Independent Benefits Reviewer",
        title="Strategic Benefits Reviewer",
        status="active",
    )
    db.add(reviewer)
    db.commit()
    db.refresh(reviewer)
    return reviewer


def _plan_content() -> dict:
    return {
        "overview_json": {
            "purpose": "Define governed strategic benefits before the investment decision.",
            "value_thesis": "Improve reliability while reducing lifecycle cost.",
        },
        "outputs_json": [{"id": "OUT-001", "name": "Modernized operating capability", "type": "OUTPUT"}],
        "outcomes_json": [
            {
                "id": "OC-001",
                "name": "More reliable operations",
                "type": "OUTCOME",
                "source_output_refs": [{"id": "OUT-001"}],
            }
        ],
        "assumptions_json": [{"statement": "Operational data remains available."}],
        "constraints_json": [{"statement": "Service continuity must be preserved."}],
        "fel_stage_code": "FEL-3",
        "reviewer_user_id": None,
    }


def _ready_benefit(actor: UserAccount) -> BenefitCreateIn:
    return BenefitCreateIn(
        benefit_name="Lower lifecycle operating cost",
        benefit_description="A measurable reduction in controlled lifecycle cost.",
        benefit_direction="BENEFIT",
        benefit_type="FINANCIAL",
        benefit_category="VALUE",
        # A non-coded reference is intentionally accepted as an imported, governed source snapshot.
        strategic_objective_refs=[{"name": "Improve sustainable asset value"}],
        source_need_reference={"id": "NEED-001", "title": "Reduce operating cost"},
        source_business_analysis_reference={"id": "BA-001", "recommended_option": "OPT-002"},
        source_project_proposal_reference={"id": "PP-001"},
        source_business_case_reference={"id": "BC-001", "revision": 1},
        expected_outputs=[{"id": "OUT-001"}],
        expected_outcomes=[{"id": "OC-001"}],
        benefit_statement="Deliver a sustained reduction in lifecycle operating cost.",
        owner=BenefitOwnerIn(
            owner_type="USER",
            owner_user_id=actor.id,
            accountability_statement="Own the baseline, target and governed measurement plan.",
            acceptance_status="ACCEPTED",
        ),
        expected_value={"amount": 250_000, "currency": "COP", "basis": "annual avoided cost"},
        monetizable_flag=True,
        dependencies=[],
        assumptions=[{"statement": "Maintenance demand remains comparable."}],
        constraints=[],
        risk_references=[{"id": "RISK-001"}],
    )


def _ready_measure(code: str = "KPI-COST") -> BenefitMeasureCreateIn:
    return BenefitMeasureCreateIn(
        measure_code=code,
        measure_name="Annual lifecycle operating cost",
        definition="Audited annual operating cost on a comparable asset basis.",
        unit_of_measure="CURRENCY",
        direction="DECREASE",
        is_primary=True,
        baseline_status="KNOWN",
        baseline_value=1_000_000,
        baseline_as_of_date=date(2026, 1, 1),
        baseline_source="Approved operating ledger",
        baseline_evidence_reference="DOC-BASELINE-001",
        baseline_confidence="HIGH",
        target_value=750_000,
        target_date=date(2028, 12, 31),
        target_basis="Approved investment case target.",
        tolerance={"maximum": 800_000},
        measurement_method="Annual audited comparison against the approved baseline.",
        measurement_frequency="ANNUAL",
        data_source_description="Controlled financial ledger.",
        measurement_owner_reference={"role": "Benefits Owner"},
    )


def _current(service: StrategicBenefitsService, plan_id: int):
    result = service.get(plan_id).current_version
    assert result is not None
    return result


def _complete_plan(db, actor, project, service):
    create_key = f"ben-create-{uuid4()}"
    created = service.create(project.id, "INITIAL_BENEFITS_PLAN", create_key)
    duplicate = service.create(project.id, "INITIAL_BENEFITS_PLAN", create_key)
    assert duplicate.id == created.id
    assert duplicate.plan_number == created.plan_number
    version = created.current_version
    assert version is not None

    with pytest.raises(HTTPException) as stale_etag:
        service.update_version(
            created.id,
            version.id,
            version.revision_version + 1,
            **_plan_content(),
        )
    assert stale_etag.value.status_code == 412
    assert stale_etag.value.detail["code"] == "ETAG_MISMATCH"

    updated = service.update_version(
        created.id,
        version.id,
        version.revision_version,
        **_plan_content(),
    )
    benefit_key = f"ben-benefit-{uuid4()}"
    benefit = service.add_benefit(
        created.id,
        version.id,
        updated.revision_version,
        benefit_key,
        _ready_benefit(actor),
    )
    benefit_duplicate = service.add_benefit(
        created.id,
        version.id,
        updated.revision_version,
        benefit_key,
        _ready_benefit(actor),
    )
    assert benefit_duplicate.id == benefit.id
    assert benefit_duplicate.benefit_number == benefit.benefit_number

    after_benefit = _current(service, created.id)
    measure = service.add_measure(
        created.id,
        version.id,
        benefit.id,
        after_benefit.revision_version,
        f"ben-measure-{uuid4()}",
        _ready_measure(),
    )
    assert measure.baseline_status == "KNOWN"
    assert measure.baseline_value == 1_000_000

    ready = service.readiness(created.id)
    assert ready.status == "READY"
    assert ready.coverage == {
        "benefit_count": 1,
        "required_benefit_count": 1,
        "ready_benefit_count": 1,
        "benefit_owner_coverage": 100.0,
        "measurement_coverage": 100.0,
        "baseline_coverage": 100.0,
        "target_coverage": 100.0,
        "traceability_coverage": 100.0,
    }
    assert set(ready.dimensions.values()) == {"READY"}
    assert ready.can_supply_investment_gate_evidence is False

    current = _current(service, created.id)
    submit_key = f"ben-submit-{uuid4()}"
    submitted = service.submit(created.id, current.id, current.revision_version, submit_key)
    submit_duplicate = service.submit(created.id, current.id, current.revision_version, submit_key)
    assert submit_duplicate.id == submitted.id
    assert submit_duplicate.revision_version == submitted.revision_version

    with pytest.raises(HTTPException) as sod:
        service.start_review(
            created.id,
            submitted.id,
            submitted.revision_version,
            f"ben-review-sod-{uuid4()}",
        )
    assert sod.value.status_code == 409
    assert sod.value.detail["code"] == "SEPARATION_OF_DUTIES_REQUIRED"

    reviewer = _reviewer(db, actor)
    review_service = StrategicBenefitsService(db, actor.tenant_id, reviewer.id)
    review_key = f"ben-review-{uuid4()}"
    reviewing = review_service.start_review(
        created.id,
        submitted.id,
        submitted.revision_version,
        review_key,
    )
    review_duplicate = review_service.start_review(
        created.id,
        submitted.id,
        submitted.revision_version,
        review_key,
    )
    assert review_duplicate.id == reviewing.id
    assert review_duplicate.revision_version == reviewing.revision_version

    complete_key = f"ben-complete-{uuid4()}"
    completed = review_service.complete(
        created.id,
        reviewing.id,
        reviewing.revision_version,
        complete_key,
    )
    complete_duplicate = review_service.complete(
        created.id,
        reviewing.id,
        reviewing.revision_version,
        complete_key,
    )
    assert complete_duplicate.id == completed.id
    assert complete_duplicate.benefits_plan_hash == completed.benefits_plan_hash
    return created, benefit, completed, review_service


def test_lifecycle_stable_identity_sod_provider_and_terminal_immutability() -> None:
    db, actor, project, service = _fixture()
    try:
        created, benefit, completed, review_service = _complete_plan(db, actor, project, service)
        assert completed.status == "COMPLETED"
        assert completed.readiness_status == "READY"
        assert completed.can_supply_investment_gate_evidence is True
        assert benefit.benefit_number.startswith("BEN-")

        provider = review_service.provider_evidence(project.id)
        assert provider.provider_key == PROVIDER_KEY
        assert provider.source_module == SOURCE_MODULE
        assert provider.evidence_type == EVIDENCE_TYPE
        assert provider.status == "AVAILABLE"
        assert provider.overall_benefits_readiness == "READY"
        assert provider.can_supply_investment_gate_evidence is True
        assert provider.blockers == []

        with pytest.raises(HTTPException) as terminal_update:
            service.update_version(
                created.id,
                completed.id,
                completed.revision_version,
                **_plan_content(),
            )
        assert terminal_update.value.detail["code"] == "BENEFITS_PLAN_VERSION_NOT_EDITABLE"

        stored = db.get(StrategicBenefitsPlanVersion, completed.id)
        assert stored is not None
        frozen_overview = deepcopy(stored.overview_json)
        stored.overview_json = {"tampered": True}
        with pytest.raises(ValueError, match="immutable"):
            db.commit()
        db.rollback()
        db.expire_all()
        stored = db.get(StrategicBenefitsPlanVersion, completed.id)
        assert stored is not None
        assert stored.overview_json == frozen_overview
    finally:
        db.rollback()
        db.close()


def test_unknown_baseline_is_null_and_blocks_submission_with_explicit_denominators() -> None:
    db, actor, project, service = _fixture()
    try:
        created = service.create(
            project.id,
            "INITIAL_BENEFITS_PLAN",
            f"ben-negative-create-{uuid4()}",
        )
        version = created.current_version
        assert version is not None
        updated = service.update_version(
            created.id,
            version.id,
            version.revision_version,
            **_plan_content(),
        )
        payload = _ready_benefit(actor)
        payload.owner = None
        payload.expected_value = {}
        benefit = service.add_benefit(
            created.id,
            version.id,
            updated.revision_version,
            f"ben-negative-benefit-{uuid4()}",
            payload,
        )
        current = _current(service, created.id)
        unknown = _ready_measure("KPI-UNKNOWN")
        unknown.baseline_status = "UNKNOWN"
        unknown.baseline_value = None
        measure = service.add_measure(
            created.id,
            version.id,
            benefit.id,
            current.revision_version,
            f"ben-negative-measure-{uuid4()}",
            unknown,
        )
        assert measure.baseline_status == "UNKNOWN"
        assert measure.baseline_value is None

        readiness = service.readiness(created.id)
        assert readiness.status == "BLOCKED"
        assert readiness.coverage["benefit_count"] == 1
        assert readiness.coverage["required_benefit_count"] == 1
        assert readiness.coverage["baseline_coverage"] == 0.0
        assert readiness.coverage["benefit_owner_coverage"] == 0.0
        assert {
            f"BASELINE_UNKNOWN_OR_MISSING:{benefit.benefit_number}",
            f"BENEFIT_OWNER_MISSING_OR_UNACCEPTED:{benefit.benefit_number}",
            f"EXPECTED_VALUE_MISSING:{benefit.benefit_number}",
            "COVERAGE_BELOW_POLICY:baseline",
            "COVERAGE_BELOW_POLICY:benefit_owner",
        }.issubset(readiness.blockers)

        current = _current(service, created.id)
        with pytest.raises(HTTPException) as blocked_submit:
            service.submit(
                created.id,
                current.id,
                current.revision_version,
                f"ben-negative-submit-{uuid4()}",
            )
        assert blocked_submit.value.detail["code"] == "BENEFITS_PLAN_BLOCKED"

        with pytest.raises(ValidationError, match="UNKNOWN baseline must use a null value"):
            BenefitMeasureCreateIn(
                measure_code="KPI-INVALID",
                measure_name="Invalid baseline",
                unit_of_measure="COUNT",
                direction="INCREASE",
                baseline_status="UNKNOWN",
                baseline_value=0,
            )
    finally:
        db.rollback()
        db.close()


def test_new_revision_preserves_benefit_identity_and_staleness_refresh_is_non_destructive() -> None:
    db, actor, project, service = _fixture()
    try:
        created, benefit, completed, _review_service = _complete_plan(db, actor, project, service)
        completed_hash = completed.benefits_plan_hash
        original_snapshot_id = completed.benefits[0].snapshot_id
        original_measure_id = completed.benefits[0].measures[0].id

        revision = service.new_revision(
            created.id,
            "MATERIAL_CHANGE_UPDATE",
            f"ben-revision-{uuid4()}",
        )
        assert revision.status == "DRAFT"
        assert revision.version_number == 2
        assert revision.benefits[0].id == benefit.id
        assert revision.benefits[0].benefit_number == benefit.benefit_number
        assert revision.benefits[0].snapshot_id != original_snapshot_id
        assert revision.benefits[0].measures[0].id != original_measure_id

        history = service.history(created.id)
        assert [item.version.version_number for item in history] == [2, 1]
        assert history[1].version.status == "SUPERSEDED"
        assert history[1].version.benefits_plan_hash == completed_hash

        # A source mutation makes the cloned draft stale without changing historical data.
        project.version += 1
        db.commit()
        stale = service.readiness(created.id)
        assert stale.status == "STALE"
        assert stale.source_current is False
        assert "BENEFITS_PLAN_SOURCE_STALE" in stale.blockers
        assert stale.can_supply_investment_gate_evidence is False

        stable = db.get(StrategicBenefit, benefit.id)
        assert stable is not None
        assert stable.benefit_number == benefit.benefit_number
        history_after = service.history(created.id)
        assert history_after[1].version.benefits_plan_hash == completed_hash
    finally:
        db.rollback()
        db.close()


def test_negative_readiness_lineage_coverage_cycle_and_idempotency_mismatch() -> None:
    db, actor, project, service = _fixture()
    try:
        created = service.create(
            project.id,
            "INITIAL_BENEFITS_PLAN",
            f"ben-matrix-create-{uuid4()}",
        )
        version = created.current_version
        assert version is not None
        updated = service.update_version(
            created.id,
            version.id,
            version.revision_version,
            **_plan_content(),
        )

        first_payload = _ready_benefit(actor)
        first_payload.benefit_name = "Benefit without governed lineage or KPI"
        first_payload.owner = None
        first_payload.expected_value = {}
        first_payload.expected_outputs = []
        first_payload.expected_outcomes = []
        first_payload.strategic_objective_refs = []
        first_payload.source_need_reference = {}
        first_payload.source_business_analysis_reference = {}
        first_payload.source_project_proposal_reference = {}
        first_key = f"ben-matrix-first-{uuid4()}"
        first = service.add_benefit(
            created.id,
            version.id,
            updated.revision_version,
            first_key,
            first_payload,
        )
        with pytest.raises(HTTPException) as idempotency_mismatch:
            service.add_benefit(
                created.id,
                version.id,
                updated.revision_version,
                first_key,
                first_payload.model_copy(update={"benefit_name": "Different payload for the same key"}),
            )
        assert idempotency_mismatch.value.status_code == 409
        assert idempotency_mismatch.value.detail["code"] == "IDEMPOTENCY_KEY_REUSED"

        second_payload = _ready_benefit(actor)
        second_payload.benefit_name = "Benefit with incomplete target definition"
        second_payload.benefit_type = "OPERATIONAL"
        second_payload.benefit_category = "EFFICIENCY"
        second_payload.monetizable_flag = False
        second_payload.expected_value = {"description": "Fewer unplanned outages"}
        second_payload.dependencies = [{"type": "BENEFIT", "benefit_id": first.id}]
        current = _current(service, created.id)
        second = service.add_benefit(
            created.id,
            version.id,
            current.revision_version,
            f"ben-matrix-second-{uuid4()}",
            second_payload,
        )
        incomplete_measure = _ready_measure("KPI-INCOMPLETE-TARGET")
        incomplete_measure.target_value = None
        incomplete_measure.target_date = None
        current = _current(service, created.id)
        service.add_measure(
            created.id,
            version.id,
            second.id,
            current.revision_version,
            f"ben-matrix-measure-{uuid4()}",
            incomplete_measure,
        )

        readiness = service.readiness(created.id)
        assert readiness.status == "BLOCKED"
        assert readiness.coverage["benefit_count"] == 2
        assert readiness.coverage["required_benefit_count"] == 2
        assert readiness.coverage["benefit_owner_coverage"] == 50.0
        assert readiness.coverage["measurement_coverage"] == 50.0
        assert readiness.coverage["target_coverage"] == 0.0
        assert {
            f"PRIMARY_MEASURE_MISSING_OR_INVALID:{first.benefit_number}",
            f"TARGET_MISSING:{first.benefit_number}",
            f"TARGET_DATE_MISSING:{first.benefit_number}",
            f"OUTPUT_LINEAGE_MISSING:{first.benefit_number}",
            f"OUTCOME_LINEAGE_MISSING:{first.benefit_number}",
            f"BENEFIT_TRACEABILITY_INCOMPLETE:{first.benefit_number}",
            f"TARGET_MISSING:{second.benefit_number}",
            f"TARGET_DATE_MISSING:{second.benefit_number}",
            "COVERAGE_BELOW_POLICY:benefit_owner",
            "COVERAGE_BELOW_POLICY:measurement",
            "COVERAGE_BELOW_POLICY:target",
            "COVERAGE_BELOW_POLICY:traceability",
        }.issubset(readiness.blockers)

        cycle_payload = BenefitUpdateIn(
            **first_payload.model_dump(),
            status="ACTIVE",
        )
        cycle_payload.dependencies = [{"type": "BENEFIT", "benefit_id": second.id}]
        current = _current(service, created.id)
        with pytest.raises(HTTPException) as dependency_cycle:
            service.update_benefit(
                created.id,
                version.id,
                first.id,
                current.revision_version,
                cycle_payload,
            )
        assert dependency_cycle.value.status_code == 422
        assert dependency_cycle.value.detail["code"] == "BENEFIT_DEPENDENCY_CYCLE"
        db.rollback()
    finally:
        db.rollback()
        db.close()


def test_stale_source_and_configuration_preview_then_refresh_apply_new_draft() -> None:
    db, actor, project, service = _fixture()
    try:
        created, benefit, completed, _review_service = _complete_plan(db, actor, project, service)
        completed_hash = completed.benefits_plan_hash
        project.version += 1
        configuration = db.get(AdminConfiguration, created.configuration_id)
        assert configuration is not None
        configuration.content_hash = "f" * 64
        db.commit()

        stale = service.readiness(created.id)
        assert stale.status == "STALE"
        assert stale.source_current is False
        assert stale.configuration_current is False
        assert {
            "BENEFITS_PLAN_SOURCE_STALE",
            "BENEFITS_PLAN_CONFIGURATION_STALE",
        }.issubset(stale.blockers)

        preview = service.refresh_preview(created.id)
        assert preview.persisted is False
        assert preview.source_delta
        assert preview.policy_delta
        assert preview.recommended_version_purpose == "MATERIAL_CHANGE_UPDATE"
        refresh_key = f"ben-refresh-{uuid4()}"
        refreshed = service.refresh_apply(
            created.id,
            completed.revision_version,
            refresh_key,
        )
        assert refreshed.status == "DRAFT"
        assert refreshed.version_number == 2
        assert refreshed.benefits[0].id == benefit.id
        assert refreshed.benefits[0].benefit_number == benefit.benefit_number
        duplicate = service.refresh_apply(
            created.id,
            completed.revision_version,
            refresh_key,
        )
        assert duplicate.id == refreshed.id

        history = service.history(created.id)
        assert [entry.version.version_number for entry in history] == [2, 1]
        assert history[1].version.status == "SUPERSEDED"
        assert history[1].version.benefits_plan_hash == completed_hash
    finally:
        db.rollback()
        db.close()


def test_provider_registration_does_not_mutate_gate07j_default_policy() -> None:
    policy_snapshot = deepcopy(DEFAULT_POLICY)
    registry_snapshot = deepcopy(PROVIDER_REGISTRY)
    policy_service = InvestmentEvidencePolicyService(None, tenant_id=1, actor_id=1)

    providers = {item.provider_key: item for item in policy_service.providers()}
    benefits = providers[PROVIDER_KEY]
    assert benefits.status == "AVAILABLE"
    assert benefits.source_module == SOURCE_MODULE
    assert benefits.evidence_type == EVIDENCE_TYPE
    registry_entry = PROVIDER_REGISTRY[PROVIDER_KEY]
    assert registry_entry["evidence_type"] == EVIDENCE_TYPE
    assert registry_entry["source_contract"] == "BenefitsReadinessProviderOut"
    assert registry_entry["supports_project_scope"] is True
    assert registry_entry["contract_status"] == "VALID"

    policy_rows = [item for profile in DEFAULT_POLICY["gate_profiles"].values() for item in profile["requirements"]]
    assert not [item for item in policy_rows if item["evidence_type"] == EVIDENCE_TYPE]
    assert DEFAULT_POLICY == policy_snapshot
    assert PROVIDER_REGISTRY == registry_snapshot
