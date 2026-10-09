"""Real PostgreSQL service evidence for Gate 07M-BEN.

Run with ``PYPMIS_TEST_DATABASE_URL`` pointing to a disposable PostgreSQL
database whose schema is at Alembic head.
"""

from __future__ import annotations

from datetime import date
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from app.database.session import SessionLocal, engine
from app.domain.models import EnterpriseWorkspace, UserAccount
from app.main import app
from app.modules.strategic_benefits.schemas import (
    BenefitCreateIn,
    BenefitMeasureCreateIn,
    BenefitMeasureUpdateIn,
    BenefitOwnerIn,
    BenefitUpdateIn,
)
from app.modules.strategic_benefits.service import (
    EVIDENCE_TYPE,
    PROVIDER_KEY,
    SOURCE_MODULE,
    StrategicBenefitsService,
)

pytestmark = pytest.mark.skipif(
    engine.dialect.name != "postgresql",
    reason="PostgreSQL Gate 07M-BEN evidence requires PYPMIS_TEST_DATABASE_URL",
)


def _project(db, actor: UserAccount) -> EnterpriseWorkspace:
    token = uuid4().hex[:10]
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
            code=f"BEN-PG-ENT-{token}",
            external_key=f"ben-pg-ent-{token}",
            record_code=f"BEN.PG.ENT.{token}",
            name="PostgreSQL Benefits Enterprise",
            status="active",
            defaults_json={},
            sort_order=1,
            version=1,
            created_by_user_id=actor.id,
        )
        db.add(parent)
        db.flush()
    record = EnterpriseWorkspace(
        tenant_id=actor.tenant_id,
        parent_id=parent.id,
        workspace_type_code="project",
        code=f"BEN-PG-PRJ-{token}",
        external_key=f"ben-pg-prj-{token}",
        record_code=f"BEN.PG.PRJ.{token}",
        name=f"PostgreSQL Strategic Benefits {token}",
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
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def _benefit(
    *,
    index: int,
    name: str,
    benefit_type: str,
    category: str,
    monetizable: bool,
    expected_value: dict,
) -> BenefitCreateIn:
    return BenefitCreateIn(
        benefit_name=name,
        benefit_description=f"Governed PostgreSQL evidence for {name}.",
        benefit_direction="BENEFIT",
        benefit_type=benefit_type,
        benefit_category=category,
        strategic_objective_refs=[{"name": "Sustainable governed value"}],
        source_need_reference={"id": f"NEED-PG-{index}"},
        source_business_analysis_reference={
            "id": f"BA-PG-{index}",
            "recommended_option": {"id": f"OPT-PG-{index}"},
        },
        source_project_proposal_reference={"id": f"PP-PG-{index}"},
        source_business_case_reference={"id": "BC-PG-001", "revision": 1},
        expected_outputs=[{"id": f"OUT-PG-{index}"}],
        expected_outcomes=[{"id": f"OC-PG-{index}"}],
        benefit_statement=f"Realize and measure {name.lower()}.",
        owner=BenefitOwnerIn(
            owner_type="EXTERNAL_REFERENCE",
            owner_reference=f"OWNER-PG-{index}",
            accountability_statement="Accountable for baseline, target and measurement assurance.",
            acceptance_status="ACCEPTED",
        ),
        expected_value=expected_value,
        monetizable_flag=monetizable,
        dependencies=[],
        assumptions=[{"statement": "The approved operating basis remains valid."}],
        constraints=[],
        risk_references=[{"id": f"RISK-PG-{index}"}],
    )


def _measure(
    *,
    index: int,
    unit: str,
    direction: str,
    baseline,
    target,
) -> BenefitMeasureCreateIn:
    return BenefitMeasureCreateIn(
        measure_code=f"KPI-PG-{index}",
        measure_name=f"Governed benefit KPI {index}",
        definition="A controlled KPI with an evidenced baseline and dated target.",
        unit_of_measure=unit,
        direction=direction,
        is_primary=True,
        baseline_status="KNOWN",
        baseline_value=baseline,
        baseline_as_of_date=date(2026, 1, 1),
        baseline_source="Approved PostgreSQL evidence baseline",
        baseline_evidence_reference=f"DOC-PG-BASE-{index}",
        baseline_confidence="HIGH",
        target_value=target,
        target_date=date(2028, 12, 31),
        target_basis="Approved investment case target.",
        tolerance={"policy": "controlled"},
        measurement_method="Periodic controlled comparison against the approved baseline.",
        measurement_frequency="QUARTERLY",
        data_source_description="Governed operational and financial systems.",
        measurement_owner_reference={"reference": f"OWNER-PG-{index}"},
    )


def test_gate07m_ben_postgres_three_benefit_happy_path_and_bounded_traceability() -> None:
    with TestClient(app):
        with SessionLocal() as db:
            actor = db.scalar(select(UserAccount).where(UserAccount.email == "admin@demo.local"))
            assert actor is not None
            project = _project(db, actor)
            service = StrategicBenefitsService(db, actor.tenant_id, actor.id)
            service.ensure_seed()

            plan = service.create(
                project.id,
                "INITIAL_BENEFITS_PLAN",
                f"ben-pg-create-{uuid4()}",
            )
            version = plan.current_version
            assert version is not None
            outputs = [{"id": f"OUT-PG-{index}", "name": f"Controlled output {index}"} for index in range(1, 4)]
            outcomes = [
                {
                    "id": f"OC-PG-{index}",
                    "name": f"Controlled outcome {index}",
                    "source_output_refs": [{"id": f"OUT-PG-{index}"}],
                }
                for index in range(1, 4)
            ]
            current = service.update_version(
                plan.id,
                version.id,
                version.revision_version,
                overview_json={"purpose": "PostgreSQL three-Benefit release evidence"},
                outputs_json=outputs,
                outcomes_json=outcomes,
                assumptions_json=[],
                constraints_json=[],
                fel_stage_code="FEL-3",
                reviewer_user_id=None,
            )

            definitions = [
                (
                    _benefit(
                        index=1,
                        name="Lifecycle cost reduction",
                        benefit_type="FINANCIAL",
                        category="VALUE",
                        monetizable=True,
                        expected_value={"amount": 500_000, "currency": "COP"},
                    ),
                    _measure(index=1, unit="CURRENCY", direction="DECREASE", baseline=2_000_000, target=1_500_000),
                ),
                (
                    _benefit(
                        index=2,
                        name="Operational reliability improvement",
                        benefit_type="OPERATIONAL",
                        category="EFFICIENCY",
                        monetizable=False,
                        expected_value={"description": "Higher service availability"},
                    ),
                    _measure(index=2, unit="PERCENT", direction="INCREASE", baseline=92, target=98),
                ),
                (
                    _benefit(
                        index=3,
                        name="Regulatory obligation achieved",
                        benefit_type="REGULATORY",
                        category="COMPLIANCE",
                        monetizable=False,
                        expected_value={"description": "Demonstrable regulatory compliance"},
                    ),
                    _measure(
                        index=3,
                        unit="BINARY",
                        direction="BINARY_ACHIEVEMENT",
                        baseline=False,
                        target=True,
                    ),
                ),
            ]
            created_benefits = []
            measure_payloads = []
            for index, (benefit_payload, measure_payload) in enumerate(definitions, start=1):
                benefit = service.add_benefit(
                    plan.id,
                    version.id,
                    current.revision_version,
                    f"ben-pg-benefit-{index}-{uuid4()}",
                    benefit_payload,
                )
                current = service.get(plan.id).current_version
                assert current is not None
                service.add_measure(
                    plan.id,
                    version.id,
                    benefit.id,
                    current.revision_version,
                    f"ben-pg-measure-{index}-{uuid4()}",
                    measure_payload,
                )
                created_benefits.append((benefit, benefit_payload))
                measure_payloads.append(measure_payload)
                current = service.get(plan.id).current_version
                assert current is not None

            readiness = service.readiness(plan.id)
            assert readiness.status == "READY"
            assert len(readiness.dimensions) == 12
            assert set(readiness.dimensions.values()) == {"READY"}
            assert readiness.coverage["benefit_count"] == 3
            assert readiness.coverage["required_benefit_count"] == 3
            assert readiness.coverage["ready_benefit_count"] == 3
            assert readiness.coverage["traceability_coverage"] == 100.0

            statement_count = 0

            def count_statement(_conn, _cursor, _statement, _parameters, _context, _executemany):
                nonlocal statement_count
                statement_count += 1

            event.listen(engine, "before_cursor_execute", count_statement)
            try:
                traceability, next_cursor = service.traceability_page(
                    plan.id,
                    version_id=version.id,
                    limit=10,
                    cursor=None,
                )
            finally:
                event.remove(engine, "before_cursor_execute", count_statement)
            assert len(traceability) == 3
            assert next_cursor is None
            assert statement_count <= 8

            current = service.get(plan.id).current_version
            assert current is not None
            submitted = service.submit(
                plan.id,
                current.id,
                current.revision_version,
                f"ben-pg-submit-{uuid4()}",
            )
            reviewer = UserAccount(
                tenant_id=actor.tenant_id,
                email=f"ben-pg-reviewer-{uuid4().hex[:10]}@example.test",
                full_name="Independent PostgreSQL Benefits Reviewer",
                title="Benefits Reviewer",
                status="active",
            )
            db.add(reviewer)
            db.commit()
            db.refresh(reviewer)
            review_service = StrategicBenefitsService(db, actor.tenant_id, reviewer.id)
            reviewing = review_service.start_review(
                plan.id,
                submitted.id,
                submitted.revision_version,
                f"ben-pg-review-{uuid4()}",
            )
            completed = review_service.complete(
                plan.id,
                reviewing.id,
                reviewing.revision_version,
                f"ben-pg-complete-{uuid4()}",
            )
            assert completed.status == "COMPLETED"
            assert completed.readiness_status == "READY"
            assert completed.can_supply_investment_gate_evidence is True
            assert len(completed.benefits) == 3
            assert len({item.id for item in completed.benefits}) == 3
            assert len({item.benefit_number for item in completed.benefits}) == 3

            provider = review_service.provider_evidence(project.id)
            assert provider.provider_key == PROVIDER_KEY
            assert provider.source_module == SOURCE_MODULE
            assert provider.evidence_type == EVIDENCE_TYPE
            assert provider.status == "AVAILABLE"
            assert provider.benefit_count == 3
            assert provider.ready_benefit_count == 3
            assert provider.can_supply_investment_gate_evidence is True

            first_benefit, first_payload = created_benefits[0]
            first_measure = completed.benefits[0].measures[0]
            with pytest.raises(HTTPException) as snapshot_update:
                service.update_benefit(
                    plan.id,
                    completed.id,
                    first_benefit.id,
                    completed.revision_version,
                    BenefitUpdateIn(**first_payload.model_dump(), status="ACTIVE"),
                )
            assert snapshot_update.value.detail["code"] == "BENEFITS_PLAN_VERSION_NOT_EDITABLE"
            with pytest.raises(HTTPException) as measure_update:
                service.update_measure(
                    plan.id,
                    completed.id,
                    first_benefit.id,
                    first_measure.id,
                    completed.revision_version,
                    BenefitMeasureUpdateIn(**measure_payloads[0].model_dump()),
                )
            assert measure_update.value.detail["code"] == "BENEFITS_PLAN_VERSION_NOT_EDITABLE"
