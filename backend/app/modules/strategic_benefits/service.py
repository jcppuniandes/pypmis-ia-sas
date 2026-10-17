"""Gate 07M-BEN orchestration and deterministic Benefits readiness.

This module owns planned Benefit identity, versioned definitions, measures and
lineage.  It deliberately excludes actual realization, accounting and delivery
execution.
"""

from __future__ import annotations

import base64
import hashlib
import json
from copy import deepcopy
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domain.models import (
    AdminConfiguration,
    AdminNumberSequence,
    EnterpriseWorkspace,
    OrganizationUnit,
    SecurityEvent,
    SecurityRole,
    UserAccount,
)
from app.modules.business_analysis.models import BusinessAnalysis
from app.modules.business_case.models import BusinessCase, BusinessCaseRevision
from app.modules.business_case.source_links import current_bundle_matches_completed_case_link
from app.modules.commercial_strategy.models import CommercialContractingStrategy, CommercialStrategyVersion
from app.modules.economic_financial_model.models import EconomicFinancialModel, EconomicFinancialModelVersion
from app.modules.enterprise_structure.models import EnterpriseStrategicObjective
from app.modules.project_creation.models import ProjectCreationRequest
from app.modules.project_definition.models import ProjectFELStatus
from app.modules.project_proposal.models import ProjectProposal
from app.modules.strategic_benefits.models import (
    StrategicBenefit,
    StrategicBenefitMeasure,
    StrategicBenefitsPlan,
    StrategicBenefitsPlanVersion,
    StrategicBenefitVersionSnapshot,
)
from app.modules.strategic_benefits.schemas import (
    BenefitCreateIn,
    BenefitMeasureCreateIn,
    BenefitMeasureOut,
    BenefitMeasureUpdateIn,
    BenefitsConfigurationPreviewOut,
    BenefitsHistoryOut,
    BenefitsOptionsOut,
    BenefitsPlanOut,
    BenefitsPlanVersionOut,
    BenefitsReadinessOut,
    BenefitsReadinessProviderOut,
    BenefitsRefreshPreviewOut,
    BenefitsTraceabilityRowOut,
    BenefitUpdateIn,
    StrategicBenefitOut,
)

CONFIGURATION_KIND = "strategic_benefits_configuration"
PLAN_NUMBER_RULE = "STRATEGIC_BENEFITS_PLAN"
BENEFIT_NUMBER_RULE = "STRATEGIC_BENEFIT"
PROVIDER_KEY = "BENEFITS_READINESS_PROVIDER"
SOURCE_MODULE = "STRATEGIC_BENEFITS_PLAN"
EVIDENCE_TYPE = "BENEFITS_PLAN_READINESS"
READY_OUTPUT = "READY_FOR_GOVERNED_BENEFITS_PLAN_EVIDENCE"
NEXT_PROCESS = "ENHANCE_GATE07M_BC_WITH_FIVE_CASE_MODEL"
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100

VERSION_PURPOSES = frozenset(
    {
        "INITIAL_BENEFITS_PLAN",
        "FEL_1_UPDATE",
        "FEL_2_UPDATE",
        "INVESTMENT_SELECTION_UPDATE",
        "FEL_3_UPDATE",
        "FFA_UPDATE",
        "MATERIAL_CHANGE_UPDATE",
        "REVALIDATION",
        "OTHER",
    }
)
READINESS_STATES = frozenset({"NOT_STARTED", "IN_PROGRESS", "READY", "BLOCKED", "STALE", "NOT_APPLICABLE"})
QUEUES = ("mine", "draft", "in_review", "returned", "ready", "completed", "stale", "all_authorized")
READINESS_DIMENSIONS = (
    "STRATEGIC_ALIGNMENT_READINESS",
    "OUTPUT_READINESS",
    "OUTCOME_READINESS",
    "BENEFIT_DEFINITION_READINESS",
    "BENEFIT_OWNER_READINESS",
    "MEASUREMENT_READINESS",
    "BASELINE_READINESS",
    "TARGET_READINESS",
    "TARGET_DATE_READINESS",
    "VALUE_READINESS",
    "TRACEABILITY_READINESS",
    "OVERALL_BENEFITS_READINESS",
)


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


DEFAULT_CONFIGURATION: dict[str, Any] = {
    "enabled_by_governance_model": {
        "CAPITAL_OWNER": True,
        "CONTRACTOR_DELIVERY": False,
        "DIRECT_INTERNAL": False,
        "LEGACY_UNCLASSIFIED": False,
    },
    "applicable_project_types": ["*"],
    "applicable_gate_profiles": ["*"],
    "applicable_fel_stages": ["FEL-1", "FEL-2", "FEL-3", "FFA", "*"],
    "benefit_types": [
        "FINANCIAL",
        "ECONOMIC",
        "OPERATIONAL",
        "STRATEGIC",
        "REGULATORY",
        "SAFETY",
        "ENVIRONMENTAL",
        "SOCIAL",
        "CUSTOMER_SERVICE",
        "CAPACITY",
        "RISK_REDUCTION",
        "OTHER",
    ],
    "benefit_categories": ["VALUE", "EFFICIENCY", "COMPLIANCE", "CAPABILITY", "RESILIENCE", "OTHER"],
    "measure_directions": [
        "INCREASE",
        "DECREASE",
        "MAINTAIN_ABOVE",
        "MAINTAIN_BELOW",
        "BINARY_ACHIEVEMENT",
    ],
    "units_of_measure": ["PERCENT", "CURRENCY", "COUNT", "DAYS", "HOURS", "INDEX", "BINARY", "OTHER"],
    "measurement_frequencies": ["MONTHLY", "QUARTERLY", "SEMI_ANNUAL", "ANNUAL", "AT_TARGET_DATE", "OTHER"],
    "minimum_benefits": 1,
    "requirements": {
        "strategic_alignment": True,
        "output": True,
        "outcome": True,
        "benefit_owner": True,
        "owner_acceptance": False,
        "primary_measure": True,
        "known_baseline": True,
        "target": True,
        "target_date": True,
        "measurement_method": True,
        "expected_value": True,
        "traceability": True,
    },
    "coverage_thresholds": {
        "benefit_owner": 100,
        "measurement": 100,
        "baseline": 100,
        "target": 100,
        "traceability": 100,
    },
    "tailoring_rules": [],
    "separation_of_duties": {"reviewer_must_differ_from_preparer": True},
    "freshness": {"require_current_sources": True},
    "numbering": {"plan_prefix": "BPL", "benefit_prefix": "BEN", "padding": 6},
    "scope": {"workspace_id": None, "inherit_to_descendants": True},
}


class StrategicBenefitsService:
    def __init__(self, db: Session, tenant_id: int, actor_id: int, context=None) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.actor_id = actor_id
        self.context = context

    # Configuration -------------------------------------------------
    def ensure_seed(self) -> None:
        existing = self.db.scalar(
            select(AdminConfiguration.id).where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == CONFIGURATION_KIND,
                AdminConfiguration.status == "published",
            )
        )
        if existing is not None:
            self._ensure_sequences()
            return
        content = deepcopy(DEFAULT_CONFIGURATION)
        self.db.add(
            AdminConfiguration(
                tenant_id=self.tenant_id,
                kind=CONFIGURATION_KIND,
                code="default",
                name="Default Strategic Benefits Policy",
                description="Gate 07M-BEN catalogs, coverage, readiness, inheritance and SoD policy.",
                status="published",
                revision=1,
                version=1,
                content_json=content,
                content_hash=_hash(content),
                published_at=utc_now(),
                created_by_user_id=self.actor_id,
            )
        )
        self._ensure_sequences()
        self._event("benefits_plan.configuration_published", "AdminConfiguration", None, {"seed": True})
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()

    def options(self, project_workspace_id: int | None = None) -> BenefitsOptionsOut:
        self.ensure_seed()
        project = self._project(project_workspace_id) if project_workspace_id else None
        configuration = self._resolve_configuration(project)[0] if project else self._published_configuration()
        content = (
            self._tailored_policy(project, configuration.content_json, None) if project else configuration.content_json
        )

        def catalog(key: str) -> list[str]:
            return [str(item) for item in list(content.get(key) or [])]

        return BenefitsOptionsOut(
            version_purposes=sorted(VERSION_PURPOSES),
            readiness_states=sorted(READINESS_STATES),
            queues=list(QUEUES),
            provider_key=PROVIDER_KEY,
            provider_status="AVAILABLE",
            configuration_id=configuration.id,
            configuration_revision=configuration.revision,
            configuration_hash=configuration.content_hash,
            benefit_types=catalog("benefit_types"),
            benefit_categories=catalog("benefit_categories"),
            measure_directions=catalog("measure_directions"),
            units_of_measure=catalog("units_of_measure"),
            measurement_frequencies=catalog("measurement_frequencies"),
        )

    def configurations(self) -> list[AdminConfiguration]:
        self.ensure_seed()
        records = list(
            self.db.scalars(
                select(AdminConfiguration)
                .where(
                    AdminConfiguration.tenant_id == self.tenant_id,
                    AdminConfiguration.kind == CONFIGURATION_KIND,
                )
                .order_by(AdminConfiguration.code, AdminConfiguration.revision.desc())
            ).all()
        )
        return [item for item in records if self._configuration_in_authorized_scope(item)]

    def configuration_preview(
        self,
        project_workspace_id: int | None,
        configuration_id: int | None,
        content_json: dict[str, Any] | None,
    ) -> BenefitsConfigurationPreviewOut:
        self.ensure_seed()
        base = self._configuration(configuration_id) if configuration_id else self._published_configuration()
        self._assert_configuration_admin_scope(base)
        content = deepcopy(content_json if content_json is not None else base.content_json)
        issues = self._configuration_issues(content)
        warnings: list[str] = []
        chain: list[dict[str, Any]] = []
        effective = content
        if project_workspace_id:
            project = self._project(project_workspace_id)
            self._assert_scope(project.id)
            _, chain = self._resolve_configuration(project, override=base if configuration_id else None)
            if not self._is_applicable(project, content):
                warnings.append("BENEFITS_PLAN_NOT_APPLICABLE_TO_PROJECT_CONTEXT")
            effective = self._tailored_policy(project, content, None)
        else:
            warnings.append("NO_PROJECT_SELECTED_FOR_EFFECTIVE_PREVIEW")
        return BenefitsConfigurationPreviewOut(
            effective=effective,
            resolution_chain=chain,
            validation_issues=issues,
            warnings=warnings,
            publishable=not issues,
            persisted=False,
        )

    def clone_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        source = self._configuration(configuration_id, lock=True)
        self._assert_configuration_admin_scope(source)
        self._check_version(source.version, expected_version)
        revision = (
            int(
                self.db.scalar(
                    select(func.coalesce(func.max(AdminConfiguration.revision), 0)).where(
                        AdminConfiguration.tenant_id == self.tenant_id,
                        AdminConfiguration.kind == CONFIGURATION_KIND,
                        AdminConfiguration.code == source.code,
                    )
                )
                or 0
            )
            + 1
        )
        record = AdminConfiguration(
            tenant_id=self.tenant_id,
            kind=CONFIGURATION_KIND,
            code=source.code,
            name=f"{source.name} R{revision}",
            description=source.description,
            status="draft",
            revision=revision,
            version=1,
            content_json=deepcopy(source.content_json),
            content_hash=source.content_hash,
            created_by_user_id=self.actor_id,
        )
        self.db.add(record)
        self.db.flush()
        self._event(
            "benefits_plan.configuration_cloned",
            "AdminConfiguration",
            record.id,
            {"source_configuration_id": source.id},
        )
        self.db.commit()
        self.db.refresh(record)
        return record

    def update_configuration(
        self,
        configuration_id: int,
        expected_version: int,
        name: str,
        description: str,
        content_json: dict[str, Any],
    ) -> AdminConfiguration:
        record = self._configuration(configuration_id, lock=True)
        self._assert_configuration_admin_scope(record)
        self._check_version(record.version, expected_version)
        if record.status != "draft":
            raise HTTPException(status_code=409, detail={"code": "PUBLISHED_CONFIGURATION_IMMUTABLE"})
        issues = self._configuration_issues(content_json)
        if issues:
            raise HTTPException(
                status_code=422,
                detail={"code": "INVALID_BENEFITS_CONFIGURATION", "issues": issues},
            )
        record.name = name
        record.description = description
        record.content_json = deepcopy(content_json)
        record.content_hash = _hash(content_json)
        record.version += 1
        record.updated_at = utc_now()
        self._event("benefits_plan.configuration_updated", "AdminConfiguration", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return record

    def publish_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        record = self._configuration(configuration_id, lock=True)
        self._assert_configuration_admin_scope(record)
        self._check_version(record.version, expected_version)
        if record.status == "published":
            return record
        if record.status != "draft":
            raise HTTPException(status_code=409, detail={"code": "CONFIGURATION_NOT_PUBLISHABLE"})
        issues = self._configuration_issues(record.content_json)
        if issues:
            raise HTTPException(status_code=422, detail={"code": "INVALID_BENEFITS_CONFIGURATION", "issues": issues})
        record.status = "published"
        record.published_at = utc_now()
        record.version += 1
        record.updated_at = utc_now()
        self._event("benefits_plan.configuration_published", "AdminConfiguration", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return record

    def archive_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        record = self._configuration(configuration_id, lock=True)
        self._assert_configuration_admin_scope(record)
        self._check_version(record.version, expected_version)
        if record.status == "archived":
            return record
        if record.status != "published":
            raise HTTPException(status_code=409, detail={"code": "ONLY_PUBLISHED_CONFIGURATION_CAN_BE_ARCHIVED"})
        record.status = "archived"
        record.version += 1
        record.updated_at = utc_now()
        self._event("benefits_plan.configuration_archived", "AdminConfiguration", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return record

    # USER aggregate ------------------------------------------------
    def list_page(
        self,
        *,
        queue: str,
        project_workspace_id: int | None,
        search: str,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[BenefitsPlanOut], str | None]:
        normalized = queue.strip().lower() or "all_authorized"
        if normalized not in QUEUES:
            raise HTTPException(status_code=422, detail={"code": "INVALID_BENEFITS_QUEUE"})
        statement = select(StrategicBenefitsPlan).where(StrategicBenefitsPlan.tenant_id == self.tenant_id)
        if not self._organization_wide():
            statement = statement.where(
                StrategicBenefitsPlan.project_workspace_id.in_(self.context.workspace_ids or {-1})
            )
        if project_workspace_id:
            self._assert_scope(project_workspace_id)
            statement = statement.where(StrategicBenefitsPlan.project_workspace_id == project_workspace_id)
        if normalized == "mine":
            statement = statement.where(StrategicBenefitsPlan.created_by == self.actor_id)
        elif normalized == "draft":
            statement = statement.where(StrategicBenefitsPlan.status == "DRAFT")
        elif normalized == "in_review":
            statement = statement.where(StrategicBenefitsPlan.status == "IN_REVIEW")
        elif normalized == "completed":
            statement = statement.where(StrategicBenefitsPlan.status == "COMPLETED")
        if search.strip():
            term = f"%{search.strip()}%"
            statement = statement.where(StrategicBenefitsPlan.plan_number.ilike(term))
        if cursor:
            updated_at, record_id = self._decode_cursor(cursor)
            statement = statement.where(
                or_(
                    StrategicBenefitsPlan.updated_at < updated_at,
                    and_(StrategicBenefitsPlan.updated_at == updated_at, StrategicBenefitsPlan.id < record_id),
                )
            )
        ordered = statement.order_by(StrategicBenefitsPlan.updated_at.desc(), StrategicBenefitsPlan.id.desc())
        rows: list[StrategicBenefitsPlan] = []
        if normalized in {"ready", "stale", "returned"}:
            for row in self.db.scalars(ordered.execution_options(yield_per=100)):
                version = self._current_version(row, required=False)
                if version is None:
                    continue
                readiness = self._recalculate(row, version, persist=False)
                returned = version.returned_at is not None and version.status == "DRAFT"
                if (
                    (normalized == "ready" and readiness.status == "READY")
                    or (normalized == "stale" and readiness.status == "STALE")
                    or (normalized == "returned" and returned)
                ):
                    rows.append(row)
                if len(rows) == limit + 1:
                    break
        else:
            rows = list(self.db.scalars(ordered.limit(limit + 1)).all())
        more = len(rows) > limit
        rows = rows[:limit]
        output = [self._plan_out(row) for row in rows]
        next_cursor = self._encode_cursor(rows[-1].updated_at, rows[-1].id) if more and rows else None
        return output, next_cursor

    def create(self, project_workspace_id: int, purpose: str, idempotency_key: str) -> BenefitsPlanOut:
        self.ensure_seed()
        self._validate_purpose(purpose, allow_initial=True)
        duplicate = self.db.scalar(
            select(StrategicBenefitsPlan).where(
                StrategicBenefitsPlan.tenant_id == self.tenant_id,
                StrategicBenefitsPlan.create_idempotency_key == idempotency_key,
            )
        )
        if duplicate:
            if duplicate.project_workspace_id != project_workspace_id:
                self._idempotency_conflict()
            first = self.db.scalar(
                select(StrategicBenefitsPlanVersion).where(
                    StrategicBenefitsPlanVersion.benefits_plan_id == duplicate.id,
                    StrategicBenefitsPlanVersion.version_number == 1,
                )
            )
            if first is None or first.version_purpose != purpose:
                self._idempotency_conflict()
            return self._plan_out(duplicate)
        project = self._project(project_workspace_id)
        self._assert_scope(project.id)
        existing = self.db.scalar(
            select(StrategicBenefitsPlan.id).where(
                StrategicBenefitsPlan.tenant_id == self.tenant_id,
                StrategicBenefitsPlan.project_workspace_id == project.id,
            )
        )
        if existing:
            raise HTTPException(status_code=409, detail={"code": "BENEFITS_PLAN_ALREADY_EXISTS_FOR_PROJECT"})
        configuration, chain = self._resolve_configuration(project)
        if not self._is_applicable(project, configuration.content_json):
            raise HTTPException(status_code=409, detail={"code": "BENEFITS_PLAN_NOT_APPLICABLE"})
        references, hashes = self._source_bundle(project.id)
        plan = StrategicBenefitsPlan(
            tenant_id=self.tenant_id,
            project_workspace_id=project.id,
            plan_number=self._reserve_number(PLAN_NUMBER_RULE, configuration.content_json),
            status="DRAFT",
            configuration_id=configuration.id,
            configuration_revision=configuration.revision,
            configuration_hash=configuration.content_hash,
            configuration_source_workspace_id=self._chain_source_id(chain),
            configuration_resolution_chain_json=chain,
            create_idempotency_key=idempotency_key,
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.db.add(plan)
        self.db.flush()
        version = self._new_version(
            plan,
            purpose,
            idempotency_key=f"{idempotency_key}:VERSION:1",
            configuration=configuration,
            source_references=references,
            source_hashes=hashes,
        )
        plan.current_version_id = version.id
        self._event("benefits_plan.created", "StrategicBenefitsPlan", plan.id, {"version_id": version.id})
        self.db.commit()
        return self._plan_out(plan)

    def get(self, plan_id: int) -> BenefitsPlanOut:
        return self._plan_out(self._plan(plan_id))

    def by_project(self, project_id: int) -> BenefitsPlanOut:
        project = self._project(project_id)
        self._assert_scope(project.id)
        plan = self.db.scalar(
            select(StrategicBenefitsPlan).where(
                StrategicBenefitsPlan.tenant_id == self.tenant_id,
                StrategicBenefitsPlan.project_workspace_id == project.id,
            )
        )
        if plan is None:
            raise HTTPException(status_code=404, detail={"code": "BENEFITS_PLAN_NOT_FOUND"})
        return self._plan_out(plan)

    def update_version(
        self,
        plan_id: int,
        version_id: int,
        expected_version: int,
        *,
        overview_json: dict[str, Any],
        outputs_json: list[dict[str, Any]],
        outcomes_json: list[dict[str, Any]],
        assumptions_json: list[dict[str, Any]],
        constraints_json: list[dict[str, Any]],
        fel_stage_code: str | None,
        reviewer_user_id: int | None,
    ) -> BenefitsPlanVersionOut:
        plan, version = self._plan_version(plan_id, version_id, lock=True)
        self._check_version(version.revision_version, expected_version)
        self._assert_editable(version)
        if reviewer_user_id is not None:
            self._user(reviewer_user_id)
        self._validate_outputs_outcomes(outputs_json, outcomes_json)
        version.overview_json = deepcopy(overview_json)
        version.outputs_json = deepcopy(outputs_json)
        version.outcomes_json = deepcopy(outcomes_json)
        version.assumptions_json = deepcopy(assumptions_json)
        version.constraints_json = deepcopy(constraints_json)
        if fel_stage_code is not None:
            version.fel_stage_code = fel_stage_code
        version.reviewer_user_id = reviewer_user_id
        self._recalculate(plan, version, persist=True)
        self._touch(plan, version)
        self._event("benefits_plan.version_updated", "StrategicBenefitsPlanVersion", version.id, {})
        self.db.commit()
        return self._version_out(version)

    def add_benefit(
        self,
        plan_id: int,
        version_id: int,
        expected_version: int,
        idempotency_key: str,
        payload: BenefitCreateIn,
    ) -> StrategicBenefitOut:
        duplicate = self.db.scalar(
            select(StrategicBenefit).where(
                StrategicBenefit.tenant_id == self.tenant_id,
                StrategicBenefit.create_idempotency_key == idempotency_key,
            )
        )
        if duplicate:
            if duplicate.benefits_plan_id != plan_id:
                self._idempotency_conflict()
            snapshot = self.db.scalar(
                select(StrategicBenefitVersionSnapshot).where(
                    StrategicBenefitVersionSnapshot.tenant_id == self.tenant_id,
                    StrategicBenefitVersionSnapshot.plan_version_id == version_id,
                    StrategicBenefitVersionSnapshot.strategic_benefit_id == duplicate.id,
                )
            )
            if snapshot is None or self._snapshot_payload_signature(snapshot) != self._benefit_payload_signature(
                payload
            ):
                self._idempotency_conflict()
            return self._benefit_out(duplicate, snapshot)
        plan, version = self._plan_version(plan_id, version_id, lock=True)
        self._check_version(version.revision_version, expected_version)
        self._assert_editable(version)
        configuration = self._configuration(version.configuration_id)
        self._validate_benefit_payload(payload, configuration.content_json, version)
        benefit = StrategicBenefit(
            tenant_id=self.tenant_id,
            benefits_plan_id=plan.id,
            benefit_number=self._reserve_number(BENEFIT_NUMBER_RULE, configuration.content_json),
            status="ACTIVE",
            create_idempotency_key=idempotency_key,
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.db.add(benefit)
        self.db.flush()
        snapshot = self._snapshot_from_payload(version, benefit, payload)
        self.db.add(snapshot)
        self.db.flush()
        self._validate_dependency_graph(version.id)
        self._recalculate(plan, version, persist=True)
        self._touch(plan, version)
        self._event(
            "benefits_plan.benefit_created",
            "StrategicBenefit",
            benefit.id,
            {"plan_version_id": version.id, "benefit_number": benefit.benefit_number},
        )
        if self._owner_reference_present(snapshot):
            self._event(
                "benefits_plan.owner_assigned",
                "StrategicBenefitVersionSnapshot",
                snapshot.id,
                {"benefit_id": benefit.id, "owner": self._owner_out(snapshot)},
            )
        self.db.commit()
        return self._benefit_out(benefit, snapshot)

    def update_benefit(
        self,
        plan_id: int,
        version_id: int,
        benefit_id: int,
        expected_version: int,
        payload: BenefitUpdateIn,
    ) -> StrategicBenefitOut:
        plan, version = self._plan_version(plan_id, version_id, lock=True)
        self._check_version(version.revision_version, expected_version)
        self._assert_editable(version)
        benefit, snapshot = self._benefit_snapshot(version, benefit_id, lock=True)
        configuration = self._configuration(version.configuration_id)
        self._validate_benefit_payload(payload, configuration.content_json, version, benefit_id=benefit.id)
        owner_before = self._owner_out(snapshot)
        self._apply_benefit_payload(snapshot, payload)
        snapshot.status = payload.status
        snapshot.updated_by = self.actor_id
        snapshot.updated_at = utc_now()
        snapshot.revision_version += 1
        snapshot.snapshot_hash = self._snapshot_hash(snapshot)
        self.db.flush()
        self._validate_dependency_graph(version.id)
        self._recalculate(plan, version, persist=True)
        self._touch(plan, version)
        self._event(
            "benefits_plan.benefit_updated",
            "StrategicBenefit",
            benefit.id,
            {"plan_version_id": version.id, "snapshot_id": snapshot.id},
        )
        owner_after = self._owner_out(snapshot)
        if owner_before != owner_after:
            self._event(
                "benefits_plan.owner_assigned",
                "StrategicBenefitVersionSnapshot",
                snapshot.id,
                {"benefit_id": benefit.id, "before": owner_before, "after": owner_after},
            )
        self.db.commit()
        return self._benefit_out(benefit, snapshot)

    def add_measure(
        self,
        plan_id: int,
        version_id: int,
        benefit_id: int,
        expected_version: int,
        idempotency_key: str,
        payload: BenefitMeasureCreateIn,
    ) -> BenefitMeasureOut:
        duplicate = self.db.scalar(
            select(StrategicBenefitMeasure).where(
                StrategicBenefitMeasure.tenant_id == self.tenant_id,
                StrategicBenefitMeasure.create_idempotency_key == idempotency_key,
            )
        )
        if duplicate:
            snapshot = self._snapshot(duplicate.benefit_snapshot_id)
            if snapshot.plan_version_id != version_id or snapshot.strategic_benefit_id != benefit_id:
                self._idempotency_conflict()
            if self._stored_measure_payload_signature(duplicate) != self._measure_payload_signature(payload):
                self._idempotency_conflict()
            return self._measure_out(duplicate)
        plan, version = self._plan_version(plan_id, version_id, lock=True)
        self._check_version(version.revision_version, expected_version)
        self._assert_editable(version)
        _benefit, snapshot = self._benefit_snapshot(version, benefit_id, lock=True)
        self._validate_measure_payload(payload, self._configuration(version.configuration_id).content_json)
        if payload.is_primary:
            existing_primary = self.db.scalar(
                select(StrategicBenefitMeasure.id).where(
                    StrategicBenefitMeasure.tenant_id == self.tenant_id,
                    StrategicBenefitMeasure.benefit_snapshot_id == snapshot.id,
                    StrategicBenefitMeasure.is_primary.is_(True),
                )
            )
            if existing_primary:
                raise HTTPException(status_code=409, detail={"code": "PRIMARY_MEASURE_ALREADY_EXISTS"})
        measure = self._measure_from_payload(snapshot, payload, idempotency_key)
        self.db.add(measure)
        self.db.flush()
        self._recalculate(plan, version, persist=True)
        self._touch(plan, version)
        self._event(
            "benefits_plan.measure_created",
            "StrategicBenefitMeasure",
            measure.id,
            {"benefit_id": benefit_id, "plan_version_id": version.id},
        )
        self.db.commit()
        return self._measure_out(measure)

    def update_measure(
        self,
        plan_id: int,
        version_id: int,
        benefit_id: int,
        measure_id: int,
        expected_version: int,
        payload: BenefitMeasureUpdateIn,
    ) -> BenefitMeasureOut:
        plan, version = self._plan_version(plan_id, version_id, lock=True)
        self._check_version(version.revision_version, expected_version)
        self._assert_editable(version)
        _benefit, snapshot = self._benefit_snapshot(version, benefit_id, lock=True)
        measure = self.db.scalar(
            select(StrategicBenefitMeasure)
            .where(
                StrategicBenefitMeasure.id == measure_id,
                StrategicBenefitMeasure.tenant_id == self.tenant_id,
                StrategicBenefitMeasure.benefit_snapshot_id == snapshot.id,
            )
            .with_for_update()
        )
        if measure is None:
            raise HTTPException(status_code=404, detail={"code": "BENEFIT_MEASURE_NOT_FOUND"})
        self._validate_measure_payload(payload, self._configuration(version.configuration_id).content_json)
        if payload.is_primary and not measure.is_primary:
            other = self.db.scalar(
                select(StrategicBenefitMeasure.id).where(
                    StrategicBenefitMeasure.benefit_snapshot_id == snapshot.id,
                    StrategicBenefitMeasure.is_primary.is_(True),
                    StrategicBenefitMeasure.id != measure.id,
                )
            )
            if other:
                raise HTTPException(status_code=409, detail={"code": "PRIMARY_MEASURE_ALREADY_EXISTS"})
        self._apply_measure_payload(measure, payload)
        measure.updated_by = self.actor_id
        measure.updated_at = utc_now()
        measure.revision_version += 1
        measure.measure_hash = self._measure_hash(measure)
        self._recalculate(plan, version, persist=True)
        self._touch(plan, version)
        self._event("benefits_plan.measure_updated", "StrategicBenefitMeasure", measure.id, {})
        self.db.commit()
        return self._measure_out(measure)

    # Lifecycle -----------------------------------------------------
    def submit(
        self, plan_id: int, version_id: int, expected_version: int, idempotency_key: str
    ) -> BenefitsPlanVersionOut:
        duplicate = self._idempotent_version(
            "submit_idempotency_key", idempotency_key, plan_id=plan_id, version_id=version_id
        )
        if duplicate:
            return self._version_out(duplicate)
        plan, version = self._plan_version(plan_id, version_id, lock=True)
        self._check_version(version.revision_version, expected_version)
        self._assert_editable(version)
        readiness = self._recalculate(plan, version, persist=True)
        if readiness.status != "READY":
            raise HTTPException(
                status_code=409, detail={"code": "BENEFITS_PLAN_BLOCKED", "blockers": readiness.blockers}
            )
        version.status = "IN_REVIEW"
        version.submit_idempotency_key = idempotency_key
        version.submitted_at = utc_now()
        plan.status = "IN_REVIEW"
        self._touch(plan, version)
        self._event("benefits_plan.submitted", "StrategicBenefitsPlanVersion", version.id, {})
        self.db.commit()
        return self._version_out(version)

    def start_review(
        self, plan_id: int, version_id: int, expected_version: int, idempotency_key: str
    ) -> BenefitsPlanVersionOut:
        duplicate = self._idempotent_version(
            "review_idempotency_key", idempotency_key, plan_id=plan_id, version_id=version_id
        )
        if duplicate:
            return self._version_out(duplicate)
        _plan, version = self._plan_version(plan_id, version_id, lock=True)
        self._check_version(version.revision_version, expected_version)
        if version.status != "IN_REVIEW":
            raise HTTPException(status_code=409, detail={"code": "BENEFITS_PLAN_NOT_IN_REVIEW"})
        self._enforce_sod(version)
        if version.reviewer_user_id not in {None, self.actor_id}:
            raise HTTPException(status_code=409, detail={"code": "REVIEW_ASSIGNED_TO_ANOTHER_USER"})
        version.reviewer_user_id = self.actor_id
        version.review_idempotency_key = idempotency_key
        version.review_started_at = utc_now()
        version.updated_by = self.actor_id
        version.updated_at = utc_now()
        version.revision_version += 1
        self._event("benefits_plan.review_started", "StrategicBenefitsPlanVersion", version.id, {})
        self.db.commit()
        return self._version_out(version)

    def return_version(
        self,
        plan_id: int,
        version_id: int,
        expected_version: int,
        idempotency_key: str,
        reason: str,
    ) -> BenefitsPlanVersionOut:
        duplicate = self._idempotent_version(
            "return_idempotency_key",
            idempotency_key,
            plan_id=plan_id,
            version_id=version_id,
            payload_value=reason.strip(),
        )
        if duplicate:
            return self._version_out(duplicate)
        plan, version = self._plan_version(plan_id, version_id, lock=True)
        self._check_version(version.revision_version, expected_version)
        if version.status != "IN_REVIEW":
            raise HTTPException(status_code=409, detail={"code": "BENEFITS_PLAN_NOT_RETURNABLE"})
        version.status = "DRAFT"
        version.return_reason = reason.strip()
        version.return_idempotency_key = idempotency_key
        version.returned_at = utc_now()
        plan.status = "DRAFT"
        self._touch(plan, version)
        self._event("benefits_plan.returned", "StrategicBenefitsPlanVersion", version.id, {"reason": reason.strip()})
        self.db.commit()
        return self._version_out(version)

    def complete(
        self, plan_id: int, version_id: int, expected_version: int, idempotency_key: str
    ) -> BenefitsPlanVersionOut:
        duplicate = self._idempotent_version(
            "complete_idempotency_key", idempotency_key, plan_id=plan_id, version_id=version_id
        )
        if duplicate:
            return self._version_out(duplicate)
        plan, version = self._plan_version(plan_id, version_id, lock=True)
        self._check_version(version.revision_version, expected_version)
        if version.status != "IN_REVIEW":
            raise HTTPException(status_code=409, detail={"code": "BENEFITS_PLAN_NOT_COMPLETABLE"})
        self._enforce_sod(version)
        if version.reviewer_user_id != self.actor_id or version.review_started_at is None:
            raise HTTPException(status_code=409, detail={"code": "INDEPENDENT_REVIEW_REQUIRED"})
        readiness = self._recalculate(plan, version, persist=True)
        if readiness.status != "READY" or readiness.blockers:
            raise HTTPException(
                status_code=409, detail={"code": "BENEFITS_PLAN_BLOCKED", "blockers": readiness.blockers}
            )
        version.status = "COMPLETED"
        version.complete_idempotency_key = idempotency_key
        version.completed_by = self.actor_id
        version.completed_at = utc_now()
        version.benefits_plan_hash = self._plan_hash(version)
        plan.status = "COMPLETED"
        self._touch(plan, version)
        self._event(
            "benefits_plan.completed",
            "StrategicBenefitsPlanVersion",
            version.id,
            {"benefits_plan_hash": version.benefits_plan_hash},
        )
        self.db.commit()
        return self._version_out(version)

    def void(
        self,
        plan_id: int,
        version_id: int,
        expected_version: int,
        idempotency_key: str,
        reason: str,
    ) -> BenefitsPlanVersionOut:
        duplicate = self._idempotent_version(
            "void_idempotency_key",
            idempotency_key,
            plan_id=plan_id,
            version_id=version_id,
            payload_value=reason.strip(),
        )
        if duplicate:
            return self._version_out(duplicate)
        plan, version = self._plan_version(plan_id, version_id, lock=True)
        self._check_version(version.revision_version, expected_version)
        if version.status not in {"DRAFT", "IN_REVIEW"}:
            raise HTTPException(status_code=409, detail={"code": "BENEFITS_PLAN_NOT_VOIDABLE"})
        version.status = "VOIDED"
        version.void_reason = reason.strip()
        version.void_idempotency_key = idempotency_key
        version.voided_at = utc_now()
        plan.status = "VOIDED"
        self._touch(plan, version)
        self._event("benefits_plan.voided", "StrategicBenefitsPlanVersion", version.id, {"reason": reason.strip()})
        self.db.commit()
        return self._version_out(version)

    def new_revision(self, plan_id: int, purpose: str, idempotency_key: str) -> BenefitsPlanVersionOut:
        self._validate_purpose(purpose, allow_initial=False)
        duplicate = self._idempotent_version(
            "create_idempotency_key", idempotency_key, plan_id=plan_id, payload_value=purpose
        )
        if duplicate:
            return self._version_out(duplicate)
        plan = self._plan(plan_id, lock=True)
        current = self._current_version(plan)
        if current.status not in {"COMPLETED", "VOIDED"}:
            raise HTTPException(status_code=409, detail={"code": "OPEN_BENEFITS_PLAN_VERSION_EXISTS"})
        project = self._project(plan.project_workspace_id)
        configuration, chain = self._resolve_configuration(project)
        references, hashes = self._source_bundle(project.id)
        version = self._new_version(
            plan,
            purpose,
            idempotency_key=idempotency_key,
            configuration=configuration,
            source_references=references,
            source_hashes=hashes,
            source=current,
        )
        self._clone_benefits(current, version)
        if current.status == "COMPLETED":
            current.status = "SUPERSEDED"
            current.updated_at = utc_now()
        plan.current_version_id = version.id
        plan.status = "DRAFT"
        plan.configuration_id = configuration.id
        plan.configuration_revision = configuration.revision
        plan.configuration_hash = configuration.content_hash
        plan.configuration_source_workspace_id = self._chain_source_id(chain)
        plan.configuration_resolution_chain_json = chain
        plan.updated_by = self.actor_id
        plan.updated_at = utc_now()
        plan.revision_version += 1
        self._recalculate(plan, version, persist=True)
        self._event(
            "benefits_plan.revision_created",
            "StrategicBenefitsPlanVersion",
            version.id,
            {"version_purpose": purpose, "supersedes_version_id": current.id},
        )
        self.db.commit()
        return self._version_out(version)

    def readiness(self, plan_id: int) -> BenefitsReadinessOut:
        plan = self._plan(plan_id)
        return self._recalculate(plan, self._current_version(plan), persist=False)

    def history(self, plan_id: int) -> list[BenefitsHistoryOut]:
        plan = self._plan(plan_id)
        versions = list(
            self.db.scalars(
                select(StrategicBenefitsPlanVersion)
                .where(
                    StrategicBenefitsPlanVersion.tenant_id == self.tenant_id,
                    StrategicBenefitsPlanVersion.benefits_plan_id == plan.id,
                )
                .order_by(StrategicBenefitsPlanVersion.version_number.desc())
            ).all()
        )
        events = list(
            self.db.scalars(
                select(SecurityEvent)
                .where(
                    SecurityEvent.tenant_id == self.tenant_id,
                    SecurityEvent.target_type == "StrategicBenefitsPlanVersion",
                    SecurityEvent.target_id.in_([item.id for item in versions] or [-1]),
                )
                .order_by(SecurityEvent.occurred_at)
            ).all()
        )
        by_version: dict[int, list[dict[str, Any]]] = {item.id: [] for item in versions}
        for event in events:
            if event.target_id in by_version:
                by_version[event.target_id].append(
                    {
                        "event_type": event.event_type,
                        "actor_user_id": event.user_id,
                        "occurred_at": event.occurred_at.isoformat(),
                        "metadata": deepcopy(event.metadata_json or {}),
                    }
                )
        return [
            BenefitsHistoryOut(version=self._version_out(item), lifecycle_events=by_version[item.id])
            for item in versions
        ]

    def traceability_page(
        self, plan_id: int, *, version_id: int | None, limit: int, cursor: str | None
    ) -> tuple[list[BenefitsTraceabilityRowOut], str | None]:
        plan = self._plan(plan_id)
        version = self._version(version_id) if version_id else self._current_version(plan)
        if version.benefits_plan_id != plan.id:
            raise HTTPException(status_code=404, detail={"code": "BENEFITS_PLAN_VERSION_NOT_FOUND"})
        statement = (
            select(StrategicBenefitVersionSnapshot, StrategicBenefit)
            .join(StrategicBenefit, StrategicBenefit.id == StrategicBenefitVersionSnapshot.strategic_benefit_id)
            .where(
                StrategicBenefitVersionSnapshot.tenant_id == self.tenant_id,
                StrategicBenefitVersionSnapshot.plan_version_id == version.id,
            )
        )
        if cursor:
            cursor_id = self._decode_simple_cursor(cursor)
            statement = statement.where(StrategicBenefitVersionSnapshot.id > cursor_id)
        pairs = list(self.db.execute(statement.order_by(StrategicBenefitVersionSnapshot.id).limit(limit + 1)).all())
        more = len(pairs) > limit
        pairs = pairs[:limit]
        snapshot_ids = [snapshot.id for snapshot, _benefit in pairs]
        measures = list(
            self.db.scalars(
                select(StrategicBenefitMeasure)
                .where(
                    StrategicBenefitMeasure.tenant_id == self.tenant_id,
                    StrategicBenefitMeasure.benefit_snapshot_id.in_(snapshot_ids or [-1]),
                )
                .order_by(StrategicBenefitMeasure.benefit_snapshot_id, StrategicBenefitMeasure.id)
            ).all()
        )
        measures_by_snapshot: dict[int, list[StrategicBenefitMeasure]] = {}
        for measure in measures:
            measures_by_snapshot.setdefault(measure.benefit_snapshot_id, []).append(measure)
        project = self._project(plan.project_workspace_id)
        rows = []
        for snapshot, benefit in pairs:
            source_ba = deepcopy(snapshot.source_business_analysis_reference_json or {})
            rows.append(
                BenefitsTraceabilityRowOut(
                    strategic_objectives=deepcopy(snapshot.strategic_objective_refs_json or []),
                    need_opportunity=deepcopy(snapshot.source_need_reference_json or {}),
                    business_analysis=source_ba,
                    recommended_option=deepcopy(source_ba.get("recommended_option") or {}),
                    project={"id": project.id, "code": project.code, "name": project.name},
                    business_case=deepcopy(snapshot.source_business_case_reference_json or {}),
                    expected_outputs=deepcopy(snapshot.expected_outputs_json or []),
                    expected_outcomes=deepcopy(snapshot.expected_outcomes_json or []),
                    benefit_id=benefit.id,
                    benefit_number=benefit.benefit_number,
                    benefit_name=snapshot.benefit_name,
                    measures=[
                        {
                            "code": item.measure_code,
                            "name": item.measure_name,
                            "baseline_status": item.baseline_status,
                            "baseline": item.baseline_value_json,
                            "target": item.target_value_json,
                            "target_date": item.target_date,
                        }
                        for item in measures_by_snapshot.get(snapshot.id, [])
                    ],
                    owner=self._owner_out(snapshot),
                    target_dates=[
                        item.target_date
                        for item in measures_by_snapshot.get(snapshot.id, [])
                        if item.target_date is not None
                    ],
                    expected_value=deepcopy(snapshot.expected_value_json or {}),
                    status=snapshot.status,
                )
            )
        next_cursor = self._encode_simple_cursor(pairs[-1][0].id) if more and pairs else None
        return rows, next_cursor

    def refresh_preview(self, plan_id: int) -> BenefitsRefreshPreviewOut:
        plan = self._plan(plan_id)
        version = self._current_version(plan)
        project = self._project(plan.project_workspace_id)
        configuration, _ = self._resolve_configuration(project)
        _refs, current_hashes = self._source_bundle(project.id)
        source_delta = self._hash_delta(version.source_hashes_json, current_hashes)
        policy_delta = self._hash_delta(
            {"configuration": version.configuration_hash}, {"configuration": configuration.content_hash}
        )
        readiness = self._recalculate(plan, version, persist=False)
        return BenefitsRefreshPreviewOut(
            benefits_plan_id=plan.id,
            current_version_id=version.id,
            source_delta=source_delta,
            benefit_delta=[],
            owner_delta=[],
            measure_delta=[],
            target_delta=[],
            policy_delta=policy_delta,
            readiness_delta={
                "stored": version.readiness_status,
                "current": readiness.status,
                "dimensions": readiness.dimensions,
            },
            warnings=readiness.warnings,
            blockers=readiness.blockers,
            recommended_version_purpose="MATERIAL_CHANGE_UPDATE" if source_delta else "REVALIDATION",
            persisted=False,
        )

    def refresh_apply(self, plan_id: int, expected_version: int, idempotency_key: str) -> BenefitsPlanVersionOut:
        duplicate = self._idempotent_version("refresh_idempotency_key", idempotency_key, plan_id=plan_id)
        if duplicate:
            return self._version_out(duplicate)
        plan = self._plan(plan_id, lock=True)
        current = self._current_version(plan)
        self._check_version(current.revision_version, expected_version)
        if current.status not in {"COMPLETED", "VOIDED"}:
            raise HTTPException(status_code=409, detail={"code": "BENEFITS_REFRESH_REQUIRES_TERMINAL_VERSION"})
        preview = self.refresh_preview(plan_id)
        project = self._project(plan.project_workspace_id)
        configuration, chain = self._resolve_configuration(project)
        references, hashes = self._source_bundle(project.id)
        version = self._new_version(
            plan,
            preview.recommended_version_purpose,
            idempotency_key=None,
            configuration=configuration,
            source_references=references,
            source_hashes=hashes,
            source=current,
        )
        version.refresh_idempotency_key = idempotency_key
        self._clone_benefits(current, version)
        if current.status == "COMPLETED":
            current.status = "SUPERSEDED"
            current.updated_at = utc_now()
        plan.current_version_id = version.id
        plan.status = "DRAFT"
        plan.configuration_id = configuration.id
        plan.configuration_revision = configuration.revision
        plan.configuration_hash = configuration.content_hash
        plan.configuration_source_workspace_id = self._chain_source_id(chain)
        plan.configuration_resolution_chain_json = chain
        plan.updated_by = self.actor_id
        plan.updated_at = utc_now()
        plan.revision_version += 1
        self._recalculate(plan, version, persist=True)
        self._event(
            "benefits_plan.refresh_applied",
            "StrategicBenefitsPlanVersion",
            version.id,
            {"source_delta": preview.source_delta, "policy_delta": preview.policy_delta},
        )
        self.db.commit()
        return self._version_out(version)

    def provider_evidence(self, project_workspace_id: int) -> BenefitsReadinessProviderOut:
        plan_out = self.by_project(project_workspace_id)
        if plan_out.current_version is None:
            raise HTTPException(status_code=404, detail={"code": "BENEFITS_PLAN_VERSION_NOT_FOUND"})
        plan = self._plan(plan_out.id)
        version = self._current_version(plan)
        readiness = self._recalculate(plan, version, persist=False)
        coverage = readiness.coverage
        benefit_snapshots = []
        for snapshot in self._snapshots(version.id):
            if snapshot.status != "ACTIVE":
                continue
            benefit = self._benefit(snapshot.strategic_benefit_id)
            benefit_snapshots.append(
                {
                    "benefit_id": benefit.id,
                    "benefit_number": benefit.benefit_number,
                    "snapshot_id": snapshot.id,
                    "snapshot_hash": snapshot.snapshot_hash,
                    "owner": self._owner_out(snapshot),
                    "expected_value": deepcopy(snapshot.expected_value_json or {}),
                    "measures": [
                        {
                            "measure_id": item.id,
                            "measure_code": item.measure_code,
                            "measure_hash": item.measure_hash,
                            "is_primary": item.is_primary,
                            "baseline_status": item.baseline_status,
                            "baseline_value": deepcopy(item.baseline_value_json),
                            "target_value": deepcopy(item.target_value_json),
                            "target_date": item.target_date,
                        }
                        for item in self._measures(snapshot.id)
                    ],
                }
            )
        return BenefitsReadinessProviderOut(
            provider_key=PROVIDER_KEY,
            source_module=SOURCE_MODULE,
            evidence_type=EVIDENCE_TYPE,
            status="AVAILABLE",
            project_workspace_id=project_workspace_id,
            benefits_plan_id=plan.id,
            plan_number=plan.plan_number,
            plan_version_id=version.id,
            plan_version_number=version.version_number,
            plan_version_purpose=version.version_purpose,
            fel_stage_code=version.fel_stage_code,
            benefit_count=int(coverage["benefit_count"]),
            required_benefit_count=int(coverage["required_benefit_count"]),
            ready_benefit_count=int(coverage["ready_benefit_count"]),
            benefit_owner_coverage=float(coverage["benefit_owner_coverage"]),
            measurement_coverage=float(coverage["measurement_coverage"]),
            baseline_coverage=float(coverage["baseline_coverage"]),
            target_coverage=float(coverage["target_coverage"]),
            traceability_coverage=float(coverage["traceability_coverage"]),
            overall_benefits_readiness=readiness.status,
            benefit_snapshots=benefit_snapshots,
            benefits_plan_hash=version.benefits_plan_hash,
            source_bundle_hash=version.source_bundle_hash,
            configuration_hash=version.configuration_hash,
            as_of_date=version.completed_at or version.updated_at,
            warnings=readiness.warnings,
            blockers=readiness.blockers,
            source_current=readiness.source_current,
            can_supply_investment_gate_evidence=readiness.can_supply_investment_gate_evidence,
        )

    # Internals -----------------------------------------------------
    def _new_version(
        self,
        plan: StrategicBenefitsPlan,
        purpose: str,
        *,
        idempotency_key: str | None,
        configuration: AdminConfiguration,
        source_references: dict[str, Any],
        source_hashes: dict[str, str],
        source: StrategicBenefitsPlanVersion | None = None,
    ) -> StrategicBenefitsPlanVersion:
        number = (
            int(
                self.db.scalar(
                    select(func.coalesce(func.max(StrategicBenefitsPlanVersion.version_number), 0)).where(
                        StrategicBenefitsPlanVersion.tenant_id == self.tenant_id,
                        StrategicBenefitsPlanVersion.benefits_plan_id == plan.id,
                    )
                )
                or 0
            )
            + 1
        )
        fel = self.db.scalar(
            select(ProjectFELStatus).where(
                ProjectFELStatus.tenant_id == self.tenant_id,
                ProjectFELStatus.project_workspace_id == plan.project_workspace_id,
            )
        )
        version = StrategicBenefitsPlanVersion(
            tenant_id=self.tenant_id,
            benefits_plan_id=plan.id,
            version_number=number,
            version_purpose=purpose,
            status="DRAFT",
            fel_stage_code=fel.current_stage_code if fel else (source.fel_stage_code if source else None),
            overview_json=deepcopy(source.overview_json if source else {}),
            outputs_json=deepcopy(source.outputs_json if source else []),
            outcomes_json=deepcopy(source.outcomes_json if source else []),
            assumptions_json=deepcopy(source.assumptions_json if source else []),
            constraints_json=deepcopy(source.constraints_json if source else []),
            readiness_json={},
            readiness_status="NOT_STARTED",
            readiness_warnings_json=[],
            readiness_blockers_json=[],
            source_references_json=deepcopy(source_references),
            source_hashes_json=deepcopy(source_hashes),
            source_bundle_hash=_hash(source_hashes),
            source_current=True,
            configuration_id=configuration.id,
            configuration_revision=configuration.revision,
            configuration_hash=configuration.content_hash,
            content_hash="",
            benefit_set_hash=_hash([]),
            traceability_hash=_hash([]),
            benefits_plan_hash="",
            preparer_user_id=self.actor_id,
            reviewer_user_id=None,
            create_idempotency_key=idempotency_key,
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        version.content_hash = self._content_hash(version)
        version.benefits_plan_hash = self._plan_hash(version)
        self.db.add(version)
        self.db.flush()
        self._recalculate(plan, version, persist=True)
        return version

    def _clone_benefits(self, source: StrategicBenefitsPlanVersion, destination: StrategicBenefitsPlanVersion) -> None:
        snapshots = self._snapshots(source.id)
        for item in snapshots:
            clone = StrategicBenefitVersionSnapshot(
                tenant_id=self.tenant_id,
                plan_version_id=destination.id,
                strategic_benefit_id=item.strategic_benefit_id,
                benefit_name=item.benefit_name,
                benefit_description=item.benefit_description,
                benefit_direction=item.benefit_direction,
                benefit_type=item.benefit_type,
                benefit_category=item.benefit_category,
                strategic_objective_refs_json=deepcopy(item.strategic_objective_refs_json),
                source_need_reference_json=deepcopy(item.source_need_reference_json),
                source_business_analysis_reference_json=deepcopy(item.source_business_analysis_reference_json),
                source_project_proposal_reference_json=deepcopy(item.source_project_proposal_reference_json),
                source_business_case_reference_json=deepcopy(item.source_business_case_reference_json),
                expected_outputs_json=deepcopy(item.expected_outputs_json),
                expected_outcomes_json=deepcopy(item.expected_outcomes_json),
                benefit_statement=item.benefit_statement,
                owner_type=item.owner_type,
                owner_user_id=item.owner_user_id,
                owner_organization_unit_id=item.owner_organization_unit_id,
                owner_security_role_id=item.owner_security_role_id,
                owner_reference=item.owner_reference,
                owner_snapshot_json=deepcopy(item.owner_snapshot_json),
                owner_effective_from=item.owner_effective_from,
                owner_effective_to=item.owner_effective_to,
                accountability_statement=item.accountability_statement,
                owner_acceptance_status=item.owner_acceptance_status,
                expected_value_json=deepcopy(item.expected_value_json),
                monetizable_flag=item.monetizable_flag,
                dependencies_json=deepcopy(item.dependencies_json),
                assumptions_json=deepcopy(item.assumptions_json),
                constraints_json=deepcopy(item.constraints_json),
                risk_references_json=deepcopy(item.risk_references_json),
                status=item.status,
                snapshot_hash=item.snapshot_hash,
                created_by=self.actor_id,
                updated_by=self.actor_id,
            )
            self.db.add(clone)
            self.db.flush()
            for measure in self._measures(item.id):
                self.db.add(
                    StrategicBenefitMeasure(
                        tenant_id=self.tenant_id,
                        benefit_snapshot_id=clone.id,
                        measure_code=measure.measure_code,
                        measure_name=measure.measure_name,
                        definition=measure.definition,
                        unit_of_measure=measure.unit_of_measure,
                        direction=measure.direction,
                        is_primary=measure.is_primary,
                        baseline_status=measure.baseline_status,
                        baseline_value_json=deepcopy(measure.baseline_value_json),
                        baseline_as_of_date=measure.baseline_as_of_date,
                        baseline_source=measure.baseline_source,
                        baseline_evidence_reference=measure.baseline_evidence_reference,
                        baseline_confidence=measure.baseline_confidence,
                        target_value_json=deepcopy(measure.target_value_json),
                        target_date=measure.target_date,
                        target_basis=measure.target_basis,
                        tolerance_json=deepcopy(measure.tolerance_json),
                        measurement_method=measure.measurement_method,
                        measurement_frequency=measure.measurement_frequency,
                        data_source_description=measure.data_source_description,
                        measurement_owner_reference_json=deepcopy(measure.measurement_owner_reference_json),
                        measure_hash=measure.measure_hash,
                        create_idempotency_key=None,
                        created_by=self.actor_id,
                        updated_by=self.actor_id,
                    )
                )
        self.db.flush()

    def _recalculate(
        self,
        plan: StrategicBenefitsPlan,
        version: StrategicBenefitsPlanVersion,
        *,
        persist: bool,
    ) -> BenefitsReadinessOut:
        project = self._project(plan.project_workspace_id)
        configuration, _ = self._resolve_configuration(project)
        _current_refs, current_hashes = self._source_bundle(project.id)
        source_current = current_bundle_matches_completed_case_link(
            self.db,
            tenant_id=self.tenant_id,
            project_id=project.id,
            source_key="benefits",
            aggregate_id=plan.id,
            version_id=version.id,
            version_number=version.version_number,
            source_hash=version.benefits_plan_hash,
            source_status=version.status,
            captured_references=dict(version.source_references_json or {}),
            captured_hashes=dict(version.source_hashes_json or {}),
            current_hashes=current_hashes,
        )
        configuration_current = configuration.content_hash == version.configuration_hash
        policy = self._tailored_policy(project, configuration.content_json, version.fel_stage_code)
        snapshots = [item for item in self._snapshots(version.id) if item.status == "ACTIVE"]
        measures_by_snapshot = {item.id: self._measures(item.id) for item in snapshots}
        dimensions, coverage, warnings, blockers = self._readiness_dimensions(
            version, snapshots, measures_by_snapshot, policy
        )
        if not source_current:
            blockers.append("BENEFITS_PLAN_SOURCE_STALE")
        if not configuration_current:
            blockers.append("BENEFITS_PLAN_CONFIGURATION_STALE")
        if not self._is_applicable(project, configuration.content_json):
            dimensions = dict.fromkeys(READINESS_DIMENSIONS, "NOT_APPLICABLE")
            blockers = []
            status = "NOT_APPLICABLE"
        else:
            status = dimensions["OVERALL_BENEFITS_READINESS"]
            if not source_current or not configuration_current:
                status = "STALE"
                dimensions["OVERALL_BENEFITS_READINESS"] = "STALE"
        content_hash = self._content_hash(version)
        benefit_rows = [
            {
                "benefit_id": item.strategic_benefit_id,
                "snapshot_hash": self._snapshot_hash(item),
                "measures": [self._measure_hash(measure) for measure in measures_by_snapshot.get(item.id, [])],
            }
            for item in snapshots
        ]
        benefit_set_hash = _hash(benefit_rows)
        traceability_hash = _hash(
            [
                {
                    "benefit_id": item.strategic_benefit_id,
                    "objectives": item.strategic_objective_refs_json,
                    "need": item.source_need_reference_json,
                    "analysis": item.source_business_analysis_reference_json,
                    "proposal": item.source_project_proposal_reference_json,
                    "case": item.source_business_case_reference_json,
                    "outputs": item.expected_outputs_json,
                    "outcomes": item.expected_outcomes_json,
                }
                for item in snapshots
            ]
        )
        readiness_hash = _hash(
            {
                "content": content_hash,
                "benefits": benefit_set_hash,
                "traceability": traceability_hash,
                "configuration": configuration.content_hash,
                "sources": current_hashes,
                "dimensions": dimensions,
                "coverage": coverage,
                "warnings": sorted(set(warnings)),
                "blockers": sorted(set(blockers)),
            }
        )
        if persist:
            version.readiness_json = {**dimensions, "coverage": coverage, "readiness_hash": readiness_hash}
            version.readiness_status = status
            version.readiness_warnings_json = sorted(set(warnings))
            version.readiness_blockers_json = sorted(set(blockers))
            version.source_current = source_current
            version.content_hash = content_hash
            version.benefit_set_hash = benefit_set_hash
            version.traceability_hash = traceability_hash
            version.benefits_plan_hash = self._plan_hash(version)
        return BenefitsReadinessOut(
            benefits_plan_id=plan.id,
            version_id=version.id,
            dimensions=dimensions,
            coverage=coverage,
            status=status,
            overall_benefits_readiness=status,
            warnings=sorted(set(warnings)),
            blockers=sorted(set(blockers)),
            source_current=source_current,
            configuration_current=configuration_current,
            benefits_plan_hash=version.benefits_plan_hash,
            source_bundle_hash=version.source_bundle_hash,
            configuration_hash=version.configuration_hash,
            can_supply_investment_gate_evidence=bool(
                version.status == "COMPLETED"
                and status == "READY"
                and source_current
                and configuration_current
                and not blockers
            ),
            persisted=bool(version.status == "COMPLETED" and version.readiness_json),
        )

    def _readiness_dimensions(
        self,
        version: StrategicBenefitsPlanVersion,
        snapshots: list[StrategicBenefitVersionSnapshot],
        measures_by_snapshot: dict[int, list[StrategicBenefitMeasure]],
        policy: dict[str, Any],
    ) -> tuple[dict[str, str], dict[str, Any], list[str], list[str]]:
        warnings: list[str] = []
        blockers: list[str] = []
        requirements = dict(policy.get("requirements") or {})
        minimum = max(0, int(policy.get("minimum_benefits", 1)))
        denominator = len(snapshots)
        if denominator < minimum:
            blockers.append("NO_REQUIRED_BENEFIT_DEFINED")

        ready_counts = {
            "alignment": 0,
            "output": 0,
            "outcome": 0,
            "definition": 0,
            "owner": 0,
            "measurement": 0,
            "baseline": 0,
            "target": 0,
            "target_date": 0,
            "value": 0,
            "traceability": 0,
            "ready": 0,
        }
        catalog_types = set(map(str, policy.get("benefit_types", [])))
        catalog_categories = set(map(str, policy.get("benefit_categories", [])))
        for snapshot in snapshots:
            code = self._benefit_number(snapshot.strategic_benefit_id)
            measures = measures_by_snapshot.get(snapshot.id, [])
            primary = [item for item in measures if item.is_primary]
            alignment_ok = bool(snapshot.strategic_objective_refs_json)
            output_ok = bool(snapshot.expected_outputs_json)
            outcome_ok = bool(snapshot.expected_outcomes_json)
            definition_ok = bool(snapshot.benefit_name and snapshot.benefit_statement and snapshot.benefit_type)
            owner_ok = bool(snapshot.owner_type and self._owner_reference_present(snapshot))
            if requirements.get("owner_acceptance"):
                owner_ok = owner_ok and str(snapshot.owner_acceptance_status or "").upper() == "ACCEPTED"
            measure_ok = bool(measures and len(primary) == 1)
            if requirements.get("measurement_method"):
                measure_ok = measure_ok and all(bool(item.measurement_method) for item in primary)
            baseline_ok = bool(primary) and all(
                item.baseline_status == "KNOWN"
                and item.baseline_value_json is not None
                and item.baseline_as_of_date is not None
                and bool(item.baseline_source)
                for item in primary
            )
            target_ok = bool(primary) and all(item.target_value_json is not None for item in primary)
            target_date_ok = bool(primary) and all(item.target_date is not None for item in primary)
            value_ok = bool(snapshot.expected_value_json)
            traceability_ok = bool(
                alignment_ok
                and output_ok
                and outcome_ok
                and (
                    snapshot.source_need_reference_json
                    or snapshot.source_business_analysis_reference_json
                    or snapshot.source_project_proposal_reference_json
                )
            )
            checks = {
                "alignment": alignment_ok or not requirements.get("strategic_alignment", True),
                "output": output_ok or not requirements.get("output", True),
                "outcome": outcome_ok or not requirements.get("outcome", True),
                "definition": definition_ok,
                "owner": owner_ok or not requirements.get("benefit_owner", True),
                "measurement": measure_ok or not requirements.get("primary_measure", True),
                "baseline": baseline_ok or not requirements.get("known_baseline", True),
                "target": target_ok or not requirements.get("target", True),
                "target_date": target_date_ok or not requirements.get("target_date", True),
                "value": value_ok or not requirements.get("expected_value", True),
                "traceability": traceability_ok or not requirements.get("traceability", True),
            }
            for key, passed in checks.items():
                ready_counts[key] += int(passed)
            if all(checks.values()):
                ready_counts["ready"] += 1
            blocker_codes = {
                "alignment": "STRATEGIC_ALIGNMENT_MISSING",
                "output": "OUTPUT_LINEAGE_MISSING",
                "outcome": "OUTCOME_LINEAGE_MISSING",
                "definition": "BENEFIT_DEFINITION_INCOMPLETE",
                "owner": "BENEFIT_OWNER_MISSING_OR_UNACCEPTED",
                "measurement": "PRIMARY_MEASURE_MISSING_OR_INVALID",
                "baseline": "BASELINE_UNKNOWN_OR_MISSING",
                "target": "TARGET_MISSING",
                "target_date": "TARGET_DATE_MISSING",
                "value": "EXPECTED_VALUE_MISSING",
                "traceability": "BENEFIT_TRACEABILITY_INCOMPLETE",
            }
            blockers.extend(f"{value}:{code}" for key, value in blocker_codes.items() if not checks[key])
            if snapshot.benefit_type not in catalog_types:
                blockers.append(f"BENEFIT_TYPE_NOT_IN_PUBLISHED_CATALOG:{code}")
            if snapshot.benefit_category and snapshot.benefit_category not in catalog_categories:
                blockers.append(f"BENEFIT_CATEGORY_NOT_IN_PUBLISHED_CATALOG:{code}")

        def pct(value: int) -> float:
            return round(100.0 * value / denominator, 2) if denominator else 0.0

        coverage = {
            "benefit_count": denominator,
            "required_benefit_count": max(minimum, denominator),
            "ready_benefit_count": ready_counts["ready"],
            "benefit_owner_coverage": pct(ready_counts["owner"]),
            "measurement_coverage": pct(ready_counts["measurement"]),
            "baseline_coverage": pct(ready_counts["baseline"]),
            "target_coverage": pct(ready_counts["target"]),
            "traceability_coverage": pct(ready_counts["traceability"]),
        }
        thresholds = dict(policy.get("coverage_thresholds") or {})
        for key, coverage_key in (
            ("benefit_owner", "benefit_owner_coverage"),
            ("measurement", "measurement_coverage"),
            ("baseline", "baseline_coverage"),
            ("target", "target_coverage"),
            ("traceability", "traceability_coverage"),
        ):
            if float(coverage[coverage_key]) < float(thresholds.get(key, 100)):
                blockers.append(f"COVERAGE_BELOW_POLICY:{key}")
        dimensions = {
            "STRATEGIC_ALIGNMENT_READINESS": self._dimension(ready_counts["alignment"], denominator),
            "OUTPUT_READINESS": self._dimension(ready_counts["output"], denominator),
            "OUTCOME_READINESS": self._dimension(ready_counts["outcome"], denominator),
            "BENEFIT_DEFINITION_READINESS": self._dimension(ready_counts["definition"], denominator),
            "BENEFIT_OWNER_READINESS": self._dimension(ready_counts["owner"], denominator),
            "MEASUREMENT_READINESS": self._dimension(ready_counts["measurement"], denominator),
            "BASELINE_READINESS": self._dimension(ready_counts["baseline"], denominator),
            "TARGET_READINESS": self._dimension(ready_counts["target"], denominator),
            "TARGET_DATE_READINESS": self._dimension(ready_counts["target_date"], denominator),
            "VALUE_READINESS": self._dimension(ready_counts["value"], denominator),
            "TRACEABILITY_READINESS": self._dimension(ready_counts["traceability"], denominator),
            "OVERALL_BENEFITS_READINESS": "READY" if denominator >= minimum and not blockers else "BLOCKED",
        }
        return dimensions, coverage, warnings, blockers

    @staticmethod
    def _dimension(ready: int, total: int) -> str:
        if total == 0:
            return "BLOCKED"
        return "READY" if ready == total else "BLOCKED"

    def _source_bundle(self, project_id: int) -> tuple[dict[str, Any], dict[str, str]]:
        project = self._project(project_id)
        references: dict[str, Any] = {
            "project": {
                "id": project.id,
                "code": project.code,
                "version": project.version,
                "status": project.status,
                "project_type": self._project_type(project),
                "governance_model": self._governance(project),
            }
        }
        hashes: dict[str, str] = {
            "project": _hash(
                {
                    "id": project.id,
                    "version": project.version,
                    "status": project.status,
                    "project": dict((project.defaults_json or {}).get("_project", {})),
                }
            )
        }
        objectives = list(
            self.db.scalars(
                select(EnterpriseStrategicObjective).where(
                    EnterpriseStrategicObjective.tenant_id == self.tenant_id,
                    EnterpriseStrategicObjective.active.is_(True),
                )
            ).all()
        )
        references["strategic_objectives"] = [
            {"id": item.id, "code": item.code, "name": item.name} for item in objectives
        ]
        hashes["strategic_objectives"] = _hash(
            [
                {
                    "id": item.id,
                    "code": item.code,
                    "name": item.name,
                    "description": item.description,
                    "updated_at": item.updated_at,
                }
                for item in objectives
            ]
        )
        request = self.db.scalar(
            select(ProjectCreationRequest).where(
                ProjectCreationRequest.tenant_id == self.tenant_id,
                ProjectCreationRequest.materialized_workspace_id == project_id,
            )
        )
        proposal = None
        if request and request.source_project_proposal_id:
            proposal = self.db.scalar(
                select(ProjectProposal).where(
                    ProjectProposal.tenant_id == self.tenant_id,
                    ProjectProposal.id == request.source_project_proposal_id,
                )
            )
        if proposal:
            references["project_proposal"] = {
                "id": proposal.id,
                "status": proposal.status,
                "expected_benefits": proposal.expected_benefits,
            }
            hashes["project_proposal"] = str(
                getattr(proposal, "completion_hash", "")
                or getattr(proposal, "readiness_hash", "")
                or _hash({"id": proposal.id, "updated_at": proposal.updated_at})
            )
            analysis_id = getattr(proposal, "source_business_analysis_id", None)
            if analysis_id:
                analysis = self.db.scalar(
                    select(BusinessAnalysis).where(
                        BusinessAnalysis.tenant_id == self.tenant_id,
                        BusinessAnalysis.id == analysis_id,
                    )
                )
                if analysis:
                    references["business_analysis"] = {
                        "id": analysis.id,
                        "status": analysis.status,
                        "recommended_option_id": analysis.recommended_option_id,
                    }
                    hashes["business_analysis"] = analysis.completion_hash or _hash(analysis.content_json)
        fel = self.db.scalar(
            select(ProjectFELStatus).where(
                ProjectFELStatus.tenant_id == self.tenant_id,
                ProjectFELStatus.project_workspace_id == project_id,
            )
        )
        if fel:
            references["fel"] = {"id": fel.id, "stage": fel.current_stage_code, "readiness": fel.readiness_status}
            hashes["fel"] = _hash(
                {
                    "stage": fel.current_stage_code,
                    "source": fel.definition_source_hash,
                    "framework": fel.effective_framework_hash,
                    "readiness": fel.readiness_status,
                }
            )
        business_case = self.db.scalar(
            select(BusinessCase).where(
                BusinessCase.tenant_id == self.tenant_id,
                BusinessCase.project_workspace_id == project_id,
            )
        )
        if business_case and business_case.current_revision_id:
            revision = self.db.scalar(
                select(BusinessCaseRevision).where(
                    BusinessCaseRevision.tenant_id == self.tenant_id,
                    BusinessCaseRevision.id == business_case.current_revision_id,
                )
            )
            if revision:
                references["business_case"] = {
                    "id": business_case.id,
                    "revision_id": revision.id,
                    "status": revision.status,
                }
                hashes["business_case"] = revision.content_hash
        commercial = self.db.scalar(
            select(CommercialContractingStrategy).where(
                CommercialContractingStrategy.tenant_id == self.tenant_id,
                CommercialContractingStrategy.project_workspace_id == project_id,
            )
        )
        if commercial and commercial.current_version_id:
            commercial_version = self.db.scalar(
                select(CommercialStrategyVersion).where(
                    CommercialStrategyVersion.tenant_id == self.tenant_id,
                    CommercialStrategyVersion.id == commercial.current_version_id,
                )
            )
            if commercial_version:
                references["commercial_strategy"] = {
                    "id": commercial.id,
                    "version_id": commercial_version.id,
                    "status": commercial_version.status,
                }
                hashes["commercial_strategy"] = commercial_version.commercial_strategy_hash
        financial = self.db.scalar(
            select(EconomicFinancialModel).where(
                EconomicFinancialModel.tenant_id == self.tenant_id,
                EconomicFinancialModel.project_workspace_id == project_id,
            )
        )
        if financial and financial.current_version_id:
            financial_version = self.db.scalar(
                select(EconomicFinancialModelVersion).where(
                    EconomicFinancialModelVersion.tenant_id == self.tenant_id,
                    EconomicFinancialModelVersion.id == financial.current_version_id,
                )
            )
            if financial_version:
                references["economic_financial_model"] = {
                    "id": financial.id,
                    "version_id": financial_version.id,
                    "status": financial_version.status,
                    "model_hash": financial_version.model_hash,
                }
                hashes["economic_financial_model"] = financial_version.model_hash
        return references, hashes

    def _plan_out(self, record: StrategicBenefitsPlan) -> BenefitsPlanOut:
        self._assert_scope(record.project_workspace_id)
        project = self._project(record.project_workspace_id)
        version = self._current_version(record, required=False)
        readiness = self._recalculate(record, version, persist=False) if version else None
        release_ready = bool(
            version
            and readiness
            and version.status == "COMPLETED"
            and readiness.status == "READY"
            and readiness.can_supply_investment_gate_evidence
        )
        return BenefitsPlanOut(
            id=record.id,
            project_workspace_id=record.project_workspace_id,
            project_workspace_name=project.name,
            plan_number=record.plan_number,
            status=record.status,
            current_version_id=record.current_version_id,
            configuration_id=record.configuration_id,
            configuration_revision=record.configuration_revision,
            configuration_hash=record.configuration_hash,
            configuration_source_workspace_id=record.configuration_source_workspace_id,
            configuration_resolution_chain_json=deepcopy(record.configuration_resolution_chain_json or []),
            created_by=record.created_by,
            created_at=record.created_at,
            updated_by=record.updated_by,
            updated_at=record.updated_at,
            revision_version=record.revision_version,
            current_version=self._version_out(version, plan=record, readiness=readiness) if version else None,
            allowed_actions=self._allowed_actions(record, version),
            final_output=READY_OUTPUT if release_ready else "BENEFITS_PLAN_IN_PROGRESS",
            next_process=NEXT_PROCESS if release_ready else "COMPLETE_GOVERNED_BENEFITS_PLAN",
        )

    def _version_out(
        self,
        version: StrategicBenefitsPlanVersion | None,
        *,
        plan: StrategicBenefitsPlan | None = None,
        readiness: BenefitsReadinessOut | None = None,
    ) -> BenefitsPlanVersionOut:
        if version is None:
            raise HTTPException(status_code=404, detail={"code": "BENEFITS_PLAN_VERSION_NOT_FOUND"})
        plan = plan or self._plan(version.benefits_plan_id)
        readiness = readiness or self._recalculate(plan, version, persist=False)
        benefits = []
        for snapshot in self._snapshots(version.id):
            identity = self._benefit(snapshot.strategic_benefit_id)
            benefits.append(self._benefit_out(identity, snapshot))
        return BenefitsPlanVersionOut(
            id=version.id,
            benefits_plan_id=version.benefits_plan_id,
            version_number=version.version_number,
            version_purpose=version.version_purpose,
            status=version.status,
            fel_stage_code=version.fel_stage_code,
            overview_json=deepcopy(version.overview_json or {}),
            outputs_json=deepcopy(version.outputs_json or []),
            outcomes_json=deepcopy(version.outcomes_json or []),
            assumptions_json=deepcopy(version.assumptions_json or []),
            constraints_json=deepcopy(version.constraints_json or []),
            benefits=benefits,
            readiness_json={**readiness.dimensions, "coverage": readiness.coverage},
            readiness_status=readiness.status,
            overall_benefits_readiness=readiness.status,
            readiness_warnings_json=readiness.warnings,
            readiness_blockers_json=readiness.blockers,
            coverage=readiness.coverage,
            source_references_json=deepcopy(version.source_references_json or {}),
            source_hashes_json=deepcopy(version.source_hashes_json or {}),
            source_bundle_hash=version.source_bundle_hash,
            source_current=readiness.source_current,
            configuration_id=version.configuration_id,
            configuration_revision=version.configuration_revision,
            configuration_hash=version.configuration_hash,
            content_hash=version.content_hash,
            benefit_set_hash=version.benefit_set_hash,
            traceability_hash=version.traceability_hash,
            benefits_plan_hash=version.benefits_plan_hash,
            preparer_user_id=version.preparer_user_id,
            reviewer_user_id=version.reviewer_user_id,
            return_reason=version.return_reason,
            void_reason=version.void_reason,
            created_at=version.created_at,
            updated_at=version.updated_at,
            submitted_at=version.submitted_at,
            review_started_at=version.review_started_at,
            returned_at=version.returned_at,
            completed_at=version.completed_at,
            completed_by=version.completed_by,
            voided_at=version.voided_at,
            revision_version=version.revision_version,
            can_supply_investment_gate_evidence=readiness.can_supply_investment_gate_evidence,
            allowed_actions=self._allowed_actions(plan, version),
        )

    def _benefit_out(self, benefit: StrategicBenefit, snapshot: StrategicBenefitVersionSnapshot) -> StrategicBenefitOut:
        return StrategicBenefitOut(
            id=benefit.id,
            benefit_number=benefit.benefit_number,
            identity_status=benefit.status,
            snapshot_id=snapshot.id,
            benefit_name=snapshot.benefit_name,
            benefit_description=snapshot.benefit_description,
            benefit_direction=snapshot.benefit_direction,
            benefit_type=snapshot.benefit_type,
            benefit_category=snapshot.benefit_category,
            strategic_objective_refs=deepcopy(snapshot.strategic_objective_refs_json or []),
            source_need_reference=deepcopy(snapshot.source_need_reference_json or {}),
            source_business_analysis_reference=deepcopy(snapshot.source_business_analysis_reference_json or {}),
            source_project_proposal_reference=deepcopy(snapshot.source_project_proposal_reference_json or {}),
            source_business_case_reference=deepcopy(snapshot.source_business_case_reference_json or {}),
            expected_outputs=deepcopy(snapshot.expected_outputs_json or []),
            expected_outcomes=deepcopy(snapshot.expected_outcomes_json or []),
            benefit_statement=snapshot.benefit_statement,
            owner=self._owner_out(snapshot),
            expected_value=deepcopy(snapshot.expected_value_json or {}),
            monetizable_flag=snapshot.monetizable_flag,
            dependencies=deepcopy(snapshot.dependencies_json or []),
            assumptions=deepcopy(snapshot.assumptions_json or []),
            constraints=deepcopy(snapshot.constraints_json or []),
            risk_references=deepcopy(snapshot.risk_references_json or []),
            status=snapshot.status,
            snapshot_hash=snapshot.snapshot_hash,
            measures=[self._measure_out(item) for item in self._measures(snapshot.id)],
            revision_version=snapshot.revision_version,
        )

    @staticmethod
    def _measure_out(record: StrategicBenefitMeasure) -> BenefitMeasureOut:
        return BenefitMeasureOut(
            id=record.id,
            benefit_snapshot_id=record.benefit_snapshot_id,
            measure_code=record.measure_code,
            measure_name=record.measure_name,
            definition=record.definition,
            unit_of_measure=record.unit_of_measure,
            direction=record.direction,
            is_primary=record.is_primary,
            baseline_status=record.baseline_status,
            baseline_value=deepcopy(record.baseline_value_json),
            baseline_as_of_date=record.baseline_as_of_date,
            baseline_source=record.baseline_source,
            baseline_evidence_reference=record.baseline_evidence_reference,
            baseline_confidence=record.baseline_confidence,
            target_value=deepcopy(record.target_value_json),
            target_date=record.target_date,
            target_basis=record.target_basis,
            tolerance=deepcopy(record.tolerance_json or {}),
            measurement_method=record.measurement_method,
            measurement_frequency=record.measurement_frequency,
            data_source_description=record.data_source_description,
            measurement_owner_reference=deepcopy(record.measurement_owner_reference_json or {}),
            measure_hash=record.measure_hash,
            created_at=record.created_at,
            updated_at=record.updated_at,
            revision_version=record.revision_version,
        )

    def _allowed_actions(
        self, plan: StrategicBenefitsPlan, version: StrategicBenefitsPlanVersion | None
    ) -> dict[str, bool]:
        roles = set(getattr(self.context, "role_codes", set()) or set())
        admin = "organization_admin" in roles
        author = admin or "benefits_plan_author" in roles
        reviewer = admin or "benefits_plan_reviewer" in roles
        status = version.status if version else None
        owned = version is None or version.preparer_user_id == self.actor_id or self._organization_wide()
        sod_ok = True
        assignment_ok = True
        if version:
            configuration = self._configuration(version.configuration_id)
            sod_required = bool(
                dict(configuration.content_json.get("separation_of_duties") or {}).get(
                    "reviewer_must_differ_from_preparer", True
                )
            )
            sod_ok = not sod_required or version.preparer_user_id != self.actor_id
            assignment_ok = version.reviewer_user_id in {None, self.actor_id} or self._organization_wide()
        editable = bool(author and owned and status == "DRAFT")
        return {
            "can_create": author,
            "can_edit": editable,
            "can_add_benefit": editable,
            "can_edit_benefit": editable,
            "can_assign_owner": editable,
            "can_submit": editable,
            "can_start_review": bool(reviewer and status == "IN_REVIEW" and sod_ok and assignment_ok),
            "can_return": bool(reviewer and status == "IN_REVIEW" and assignment_ok),
            "can_complete": bool(
                reviewer
                and status == "IN_REVIEW"
                and sod_ok
                and version is not None
                and version.reviewer_user_id == self.actor_id
                and version.review_started_at is not None
            ),
            "can_void": bool(author and owned and status in {"DRAFT", "IN_REVIEW"}),
            "can_create_revision": bool(author and status in {"COMPLETED", "VOIDED"}),
            "can_view_sources": True,
            "can_refresh_preview": bool(author and status in {"COMPLETED", "VOIDED"}),
            "can_refresh_apply": bool(author and status in {"COMPLETED", "VOIDED"}),
        }

    def _snapshot_from_payload(
        self,
        version: StrategicBenefitsPlanVersion,
        benefit: StrategicBenefit,
        payload: BenefitCreateIn,
    ) -> StrategicBenefitVersionSnapshot:
        snapshot = StrategicBenefitVersionSnapshot(
            tenant_id=self.tenant_id,
            plan_version_id=version.id,
            strategic_benefit_id=benefit.id,
            benefit_name=payload.benefit_name.strip(),
            benefit_description=payload.benefit_description.strip(),
            benefit_direction=payload.benefit_direction,
            benefit_type=payload.benefit_type,
            benefit_category=payload.benefit_category,
            strategic_objective_refs_json=deepcopy(payload.strategic_objective_refs),
            source_need_reference_json=deepcopy(payload.source_need_reference),
            source_business_analysis_reference_json=deepcopy(payload.source_business_analysis_reference),
            source_project_proposal_reference_json=deepcopy(payload.source_project_proposal_reference),
            source_business_case_reference_json=deepcopy(payload.source_business_case_reference),
            expected_outputs_json=deepcopy(payload.expected_outputs),
            expected_outcomes_json=deepcopy(payload.expected_outcomes),
            benefit_statement=payload.benefit_statement.strip(),
            expected_value_json=deepcopy(payload.expected_value),
            monetizable_flag=payload.monetizable_flag,
            dependencies_json=deepcopy(payload.dependencies),
            assumptions_json=deepcopy(payload.assumptions),
            constraints_json=deepcopy(payload.constraints),
            risk_references_json=deepcopy(payload.risk_references),
            status="ACTIVE",
            snapshot_hash="",
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self._apply_owner(snapshot, payload.owner)
        snapshot.snapshot_hash = self._snapshot_hash(snapshot)
        return snapshot

    def _apply_benefit_payload(self, snapshot: StrategicBenefitVersionSnapshot, payload: BenefitUpdateIn) -> None:
        snapshot.benefit_name = payload.benefit_name.strip()
        snapshot.benefit_description = payload.benefit_description.strip()
        snapshot.benefit_direction = payload.benefit_direction
        snapshot.benefit_type = payload.benefit_type
        snapshot.benefit_category = payload.benefit_category
        snapshot.strategic_objective_refs_json = deepcopy(payload.strategic_objective_refs)
        snapshot.source_need_reference_json = deepcopy(payload.source_need_reference)
        snapshot.source_business_analysis_reference_json = deepcopy(payload.source_business_analysis_reference)
        snapshot.source_project_proposal_reference_json = deepcopy(payload.source_project_proposal_reference)
        snapshot.source_business_case_reference_json = deepcopy(payload.source_business_case_reference)
        snapshot.expected_outputs_json = deepcopy(payload.expected_outputs)
        snapshot.expected_outcomes_json = deepcopy(payload.expected_outcomes)
        snapshot.benefit_statement = payload.benefit_statement.strip()
        snapshot.expected_value_json = deepcopy(payload.expected_value)
        snapshot.monetizable_flag = payload.monetizable_flag
        snapshot.dependencies_json = deepcopy(payload.dependencies)
        snapshot.assumptions_json = deepcopy(payload.assumptions)
        snapshot.constraints_json = deepcopy(payload.constraints)
        snapshot.risk_references_json = deepcopy(payload.risk_references)
        self._apply_owner(snapshot, payload.owner)

    def _apply_owner(self, snapshot: StrategicBenefitVersionSnapshot, owner) -> None:
        snapshot.owner_type = owner.owner_type if owner else None
        snapshot.owner_user_id = owner.owner_user_id if owner else None
        snapshot.owner_organization_unit_id = owner.owner_organization_unit_id if owner else None
        snapshot.owner_security_role_id = owner.owner_security_role_id if owner else None
        snapshot.owner_reference = owner.owner_reference if owner else None
        snapshot.owner_effective_from = owner.effective_from if owner else None
        snapshot.owner_effective_to = owner.effective_to if owner else None
        snapshot.accountability_statement = owner.accountability_statement if owner else ""
        snapshot.owner_acceptance_status = owner.acceptance_status if owner else None
        snapshot.owner_snapshot_json = self._owner_snapshot(owner) if owner else {}

    def _owner_snapshot(self, owner) -> dict[str, Any]:
        if owner.owner_type == "USER" and owner.owner_user_id:
            record = self._user(owner.owner_user_id)
            return {"type": "USER", "id": record.id, "name": record.full_name, "email": record.email}
        if owner.owner_type == "ORGANIZATION_UNIT" and owner.owner_organization_unit_id:
            record = self.db.scalar(
                select(OrganizationUnit).where(
                    OrganizationUnit.id == owner.owner_organization_unit_id,
                    OrganizationUnit.tenant_id == self.tenant_id,
                    OrganizationUnit.status == "active",
                )
            )
            if record is None:
                raise HTTPException(status_code=422, detail={"code": "BENEFIT_OWNER_NOT_FOUND"})
            return {"type": "ORGANIZATION_UNIT", "id": record.id, "code": record.code, "name": record.name}
        if owner.owner_type == "SECURITY_ROLE" and owner.owner_security_role_id:
            record = self.db.scalar(
                select(SecurityRole).where(
                    SecurityRole.id == owner.owner_security_role_id,
                    SecurityRole.tenant_id == self.tenant_id,
                    SecurityRole.status == "active",
                )
            )
            if record is None:
                raise HTTPException(status_code=422, detail={"code": "BENEFIT_OWNER_NOT_FOUND"})
            return {"type": "SECURITY_ROLE", "id": record.id, "code": record.code, "name": record.name}
        if owner.owner_type == "EXTERNAL_REFERENCE" and owner.owner_reference:
            return {"type": "EXTERNAL_REFERENCE", "reference": owner.owner_reference}
        raise HTTPException(status_code=422, detail={"code": "INVALID_BENEFIT_OWNER_REFERENCE"})

    @staticmethod
    def _owner_reference_present(snapshot: StrategicBenefitVersionSnapshot) -> bool:
        return bool(
            snapshot.owner_user_id
            or snapshot.owner_organization_unit_id
            or snapshot.owner_security_role_id
            or snapshot.owner_reference
        )

    def _owner_out(self, snapshot: StrategicBenefitVersionSnapshot) -> dict[str, Any]:
        return {
            "owner_type": snapshot.owner_type,
            "owner_user_id": snapshot.owner_user_id,
            "owner_organization_unit_id": snapshot.owner_organization_unit_id,
            "owner_security_role_id": snapshot.owner_security_role_id,
            "owner_reference": snapshot.owner_reference,
            "snapshot": deepcopy(snapshot.owner_snapshot_json or {}),
            "effective_from": snapshot.owner_effective_from,
            "effective_to": snapshot.owner_effective_to,
            "accountability_statement": snapshot.accountability_statement,
            "acceptance_status": snapshot.owner_acceptance_status,
        }

    def _measure_from_payload(
        self,
        snapshot: StrategicBenefitVersionSnapshot,
        payload: BenefitMeasureCreateIn,
        idempotency_key: str,
    ) -> StrategicBenefitMeasure:
        measure = StrategicBenefitMeasure(
            tenant_id=self.tenant_id,
            benefit_snapshot_id=snapshot.id,
            measure_code=payload.measure_code.strip(),
            measure_name=payload.measure_name.strip(),
            definition=payload.definition.strip(),
            unit_of_measure=payload.unit_of_measure,
            direction=payload.direction,
            is_primary=payload.is_primary,
            baseline_status=payload.baseline_status,
            baseline_value_json=deepcopy(payload.baseline_value),
            baseline_as_of_date=payload.baseline_as_of_date,
            baseline_source=payload.baseline_source,
            baseline_evidence_reference=payload.baseline_evidence_reference,
            baseline_confidence=payload.baseline_confidence,
            target_value_json=deepcopy(payload.target_value),
            target_date=payload.target_date,
            target_basis=payload.target_basis,
            tolerance_json=deepcopy(payload.tolerance),
            measurement_method=payload.measurement_method.strip(),
            measurement_frequency=payload.measurement_frequency,
            data_source_description=payload.data_source_description,
            measurement_owner_reference_json=deepcopy(payload.measurement_owner_reference),
            measure_hash="",
            create_idempotency_key=idempotency_key,
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        measure.measure_hash = self._measure_hash(measure)
        return measure

    @staticmethod
    def _apply_measure_payload(measure: StrategicBenefitMeasure, payload: BenefitMeasureUpdateIn) -> None:
        measure.measure_code = payload.measure_code.strip()
        measure.measure_name = payload.measure_name.strip()
        measure.definition = payload.definition.strip()
        measure.unit_of_measure = payload.unit_of_measure
        measure.direction = payload.direction
        measure.is_primary = payload.is_primary
        measure.baseline_status = payload.baseline_status
        measure.baseline_value_json = deepcopy(payload.baseline_value)
        measure.baseline_as_of_date = payload.baseline_as_of_date
        measure.baseline_source = payload.baseline_source
        measure.baseline_evidence_reference = payload.baseline_evidence_reference
        measure.baseline_confidence = payload.baseline_confidence
        measure.target_value_json = deepcopy(payload.target_value)
        measure.target_date = payload.target_date
        measure.target_basis = payload.target_basis
        measure.tolerance_json = deepcopy(payload.tolerance)
        measure.measurement_method = payload.measurement_method.strip()
        measure.measurement_frequency = payload.measurement_frequency
        measure.data_source_description = payload.data_source_description
        measure.measurement_owner_reference_json = deepcopy(payload.measurement_owner_reference)

    def _validate_benefit_payload(
        self,
        payload: BenefitCreateIn | BenefitUpdateIn,
        configuration: dict[str, Any],
        version: StrategicBenefitsPlanVersion,
        *,
        benefit_id: int | None = None,
    ) -> None:
        if not payload.benefit_name.strip() or not payload.benefit_statement.strip():
            raise HTTPException(status_code=422, detail={"code": "BENEFIT_DEFINITION_INCOMPLETE"})
        if isinstance(payload, BenefitUpdateIn) and payload.status not in {"ACTIVE", "REMOVED"}:
            raise HTTPException(status_code=422, detail={"code": "INVALID_BENEFIT_STATUS"})
        if payload.benefit_direction not in {"BENEFIT", "DISBENEFIT"}:
            raise HTTPException(status_code=422, detail={"code": "INVALID_BENEFIT_DIRECTION"})
        if payload.benefit_type not in set(map(str, configuration.get("benefit_types", []))):
            raise HTTPException(status_code=422, detail={"code": "INVALID_BENEFIT_TYPE"})
        if payload.benefit_category and payload.benefit_category not in set(
            map(str, configuration.get("benefit_categories", []))
        ):
            raise HTTPException(status_code=422, detail={"code": "INVALID_BENEFIT_CATEGORY"})
        valid_objectives = set(
            self.db.scalars(
                select(EnterpriseStrategicObjective.code).where(
                    EnterpriseStrategicObjective.tenant_id == self.tenant_id,
                    EnterpriseStrategicObjective.active.is_(True),
                )
            ).all()
        )
        requested = {str(item.get("code") or "") for item in payload.strategic_objective_refs if item.get("code")}
        if requested - valid_objectives:
            raise HTTPException(status_code=422, detail={"code": "UNKNOWN_STRATEGIC_OBJECTIVE"})
        output_ids = {str(item.get("id") or item.get("code") or "") for item in version.outputs_json}
        outcome_ids = {str(item.get("id") or item.get("code") or "") for item in version.outcomes_json}
        for item in payload.expected_outputs:
            reference = str(item.get("id") or item.get("code") or "")
            if not reference:
                raise HTTPException(status_code=422, detail={"code": "EXPECTED_OUTPUT_REFERENCE_REQUIRED"})
            if output_ids and reference not in output_ids:
                raise HTTPException(status_code=422, detail={"code": "UNKNOWN_EXPECTED_OUTPUT"})
        for item in payload.expected_outcomes:
            reference = str(item.get("id") or item.get("code") or "")
            if not reference:
                raise HTTPException(status_code=422, detail={"code": "EXPECTED_OUTCOME_REFERENCE_REQUIRED"})
            if outcome_ids and reference not in outcome_ids:
                raise HTTPException(status_code=422, detail={"code": "UNKNOWN_EXPECTED_OUTCOME"})
        if payload.monetizable_flag:
            value = dict(payload.expected_value or {})
            if value and (value.get("amount") is None or not value.get("currency")):
                raise HTTPException(status_code=422, detail={"code": "MONETIZABLE_VALUE_REQUIRES_AMOUNT_CURRENCY"})
        for dependency in payload.dependencies:
            target = dependency.get("benefit_id")
            if target is not None and int(target) == benefit_id:
                raise HTTPException(status_code=422, detail={"code": "BENEFIT_DEPENDENCY_SELF_REFERENCE"})

    @staticmethod
    def _validate_measure_payload(
        payload: BenefitMeasureCreateIn | BenefitMeasureUpdateIn, configuration: dict[str, Any]
    ) -> None:
        if payload.direction not in set(map(str, configuration.get("measure_directions", []))):
            raise HTTPException(status_code=422, detail={"code": "INVALID_MEASURE_DIRECTION"})
        if payload.unit_of_measure not in set(map(str, configuration.get("units_of_measure", []))):
            raise HTTPException(status_code=422, detail={"code": "INVALID_UNIT_OF_MEASURE"})
        if payload.measurement_frequency and payload.measurement_frequency not in set(
            map(str, configuration.get("measurement_frequencies", []))
        ):
            raise HTTPException(status_code=422, detail={"code": "INVALID_MEASUREMENT_FREQUENCY"})
        if payload.baseline_status not in {"KNOWN", "UNKNOWN"}:
            raise HTTPException(status_code=422, detail={"code": "INVALID_BASELINE_STATUS"})
        if payload.baseline_status == "UNKNOWN" and payload.baseline_value is not None:
            raise HTTPException(status_code=422, detail={"code": "UNKNOWN_BASELINE_MUST_BE_NULL"})
        if payload.baseline_status == "KNOWN" and payload.baseline_value is None:
            raise HTTPException(status_code=422, detail={"code": "KNOWN_BASELINE_REQUIRES_VALUE"})
        if payload.baseline_status == "KNOWN" and (
            payload.baseline_as_of_date is None or not str(payload.baseline_source or "").strip()
        ):
            raise HTTPException(status_code=422, detail={"code": "KNOWN_BASELINE_REQUIRES_DATE_AND_SOURCE"})

    @staticmethod
    def _validate_outputs_outcomes(outputs: list[dict[str, Any]], outcomes: list[dict[str, Any]]) -> None:
        def keys(items: list[dict[str, Any]], label: str) -> set[str]:
            values = [str(item.get("id") or item.get("code") or "") for item in items]
            if any(not item for item in values) or len(values) != len(set(values)):
                raise HTTPException(status_code=422, detail={"code": f"INVALID_{label}_IDENTITY"})
            return set(values)

        output_ids = keys(outputs, "OUTPUT")
        keys(outcomes, "OUTCOME")
        for outcome in outcomes:
            for reference in list(outcome.get("source_output_refs") or []):
                value = str(reference.get("id") or reference.get("code") or "")
                if value not in output_ids:
                    raise HTTPException(status_code=422, detail={"code": "OUTCOME_SOURCE_OUTPUT_NOT_FOUND"})

    @staticmethod
    def _benefit_payload_signature(payload: BenefitCreateIn | BenefitUpdateIn) -> str:
        owner = payload.owner.model_dump(mode="json") if payload.owner else None
        return _hash(
            {
                "benefit_name": payload.benefit_name.strip(),
                "benefit_description": payload.benefit_description.strip(),
                "benefit_direction": payload.benefit_direction,
                "benefit_type": payload.benefit_type,
                "benefit_category": payload.benefit_category,
                "strategic_objective_refs": payload.strategic_objective_refs,
                "source_need_reference": payload.source_need_reference,
                "source_business_analysis_reference": payload.source_business_analysis_reference,
                "source_project_proposal_reference": payload.source_project_proposal_reference,
                "source_business_case_reference": payload.source_business_case_reference,
                "expected_outputs": payload.expected_outputs,
                "expected_outcomes": payload.expected_outcomes,
                "benefit_statement": payload.benefit_statement.strip(),
                "owner": owner,
                "expected_value": payload.expected_value,
                "monetizable_flag": payload.monetizable_flag,
                "dependencies": payload.dependencies,
                "assumptions": payload.assumptions,
                "constraints": payload.constraints,
                "risk_references": payload.risk_references,
            }
        )

    @staticmethod
    def _snapshot_payload_signature(snapshot: StrategicBenefitVersionSnapshot) -> str:
        owner = (
            {
                "owner_type": snapshot.owner_type,
                "owner_user_id": snapshot.owner_user_id,
                "owner_organization_unit_id": snapshot.owner_organization_unit_id,
                "owner_security_role_id": snapshot.owner_security_role_id,
                "owner_reference": snapshot.owner_reference,
                "effective_from": snapshot.owner_effective_from,
                "effective_to": snapshot.owner_effective_to,
                "accountability_statement": snapshot.accountability_statement,
                "acceptance_status": snapshot.owner_acceptance_status,
            }
            if snapshot.owner_type
            else None
        )
        return _hash(
            {
                "benefit_name": snapshot.benefit_name,
                "benefit_description": snapshot.benefit_description,
                "benefit_direction": snapshot.benefit_direction,
                "benefit_type": snapshot.benefit_type,
                "benefit_category": snapshot.benefit_category,
                "strategic_objective_refs": snapshot.strategic_objective_refs_json or [],
                "source_need_reference": snapshot.source_need_reference_json or {},
                "source_business_analysis_reference": snapshot.source_business_analysis_reference_json or {},
                "source_project_proposal_reference": snapshot.source_project_proposal_reference_json or {},
                "source_business_case_reference": snapshot.source_business_case_reference_json or {},
                "expected_outputs": snapshot.expected_outputs_json or [],
                "expected_outcomes": snapshot.expected_outcomes_json or [],
                "benefit_statement": snapshot.benefit_statement,
                "owner": owner,
                "expected_value": snapshot.expected_value_json or {},
                "monetizable_flag": snapshot.monetizable_flag,
                "dependencies": snapshot.dependencies_json or [],
                "assumptions": snapshot.assumptions_json or [],
                "constraints": snapshot.constraints_json or [],
                "risk_references": snapshot.risk_references_json or [],
            }
        )

    @staticmethod
    def _measure_payload_signature(payload: BenefitMeasureCreateIn | BenefitMeasureUpdateIn) -> str:
        return _hash(payload.model_dump(mode="json"))

    @staticmethod
    def _stored_measure_payload_signature(measure: StrategicBenefitMeasure) -> str:
        return _hash(
            {
                "measure_code": measure.measure_code,
                "measure_name": measure.measure_name,
                "definition": measure.definition,
                "unit_of_measure": measure.unit_of_measure,
                "direction": measure.direction,
                "is_primary": measure.is_primary,
                "baseline_status": measure.baseline_status,
                "baseline_value": measure.baseline_value_json,
                "baseline_as_of_date": measure.baseline_as_of_date,
                "baseline_source": measure.baseline_source,
                "baseline_evidence_reference": measure.baseline_evidence_reference,
                "baseline_confidence": measure.baseline_confidence,
                "target_value": measure.target_value_json,
                "target_date": measure.target_date,
                "target_basis": measure.target_basis,
                "tolerance": measure.tolerance_json or {},
                "measurement_method": measure.measurement_method,
                "measurement_frequency": measure.measurement_frequency,
                "data_source_description": measure.data_source_description,
                "measurement_owner_reference": measure.measurement_owner_reference_json or {},
            }
        )

    def _validate_dependency_graph(self, version_id: int) -> None:
        snapshots = self._snapshots(version_id)
        graph: dict[int, set[int]] = {item.strategic_benefit_id: set() for item in snapshots}
        for item in snapshots:
            for dependency in item.dependencies_json or []:
                if str(dependency.get("type") or "BENEFIT").upper() != "BENEFIT":
                    continue
                target = dependency.get("benefit_id")
                if target is None:
                    continue
                target_id = int(target)
                if target_id not in graph:
                    raise HTTPException(status_code=422, detail={"code": "BENEFIT_DEPENDENCY_NOT_IN_PLAN"})
                graph[item.strategic_benefit_id].add(target_id)
        visiting: set[int] = set()
        visited: set[int] = set()

        def visit(node: int) -> None:
            if node in visiting:
                raise HTTPException(status_code=422, detail={"code": "BENEFIT_DEPENDENCY_CYCLE"})
            if node in visited:
                return
            visiting.add(node)
            for child in graph[node]:
                visit(child)
            visiting.remove(node)
            visited.add(node)

        for node in graph:
            visit(node)

    # Persistence, configuration and concurrency helpers -----------------
    def _resolve_configuration(
        self, project: EnterpriseWorkspace, override: AdminConfiguration | None = None
    ) -> tuple[AdminConfiguration, list[dict[str, Any]]]:
        candidates = (
            [override]
            if override
            else list(
                self.db.scalars(
                    select(AdminConfiguration)
                    .where(
                        AdminConfiguration.tenant_id == self.tenant_id,
                        AdminConfiguration.kind == CONFIGURATION_KIND,
                        AdminConfiguration.status == "published",
                    )
                    .order_by(AdminConfiguration.revision.desc())
                ).all()
            )
        )
        path = self._workspace_path(project)
        ancestor_ids = [item.id for item in reversed(path)]
        metadata = dict((project.defaults_json or {}).get("_project", {}))
        actual = {
            "project_type": self._project_type(project),
            "gate_profile": str(metadata.get("gate_profile") or ""),
            "fel_stage": str(metadata.get("fel_stage") or ""),
        }
        ranked: list[tuple[int, int, AdminConfiguration]] = []
        chain: list[dict[str, Any]] = []
        for item in candidates:
            scope = dict((item.content_json or {}).get("scope") or {})
            workspace_id = scope.get("workspace_id")
            if workspace_id is not None and workspace_id not in ancestor_ids:
                continue
            if (
                workspace_id is not None
                and workspace_id != project.id
                and not bool(scope.get("inherit_to_descendants", True))
            ):
                continue
            filters = {
                "project_type": list((item.content_json or {}).get("applicable_project_types", ["*"])),
                "gate_profile": list((item.content_json or {}).get("applicable_gate_profiles", ["*"])),
                "fel_stage": list((item.content_json or {}).get("applicable_fel_stages", ["*"])),
            }
            if any("*" not in filters[key] and actual[key] not in filters[key] for key in filters):
                continue
            distance = ancestor_ids.index(workspace_id) if workspace_id in ancestor_ids else len(ancestor_ids) + 1
            ranked.append((distance, -item.revision, item))
            chain.append(
                {
                    "configuration_id": item.id,
                    "configuration_revision": item.revision,
                    "workspace_id": workspace_id,
                    "distance": distance,
                }
            )
        if not ranked:
            raise HTTPException(status_code=409, detail={"code": "PUBLISHED_BENEFITS_CONFIGURATION_REQUIRED"})
        ranked.sort(key=lambda value: (value[0], value[1]))
        chain.sort(key=lambda value: (value["distance"], -value["configuration_revision"]))
        return ranked[0][2], chain

    def _plan(self, plan_id: int, *, lock: bool = False) -> StrategicBenefitsPlan:
        statement = select(StrategicBenefitsPlan).where(
            StrategicBenefitsPlan.id == plan_id,
            StrategicBenefitsPlan.tenant_id == self.tenant_id,
        )
        if lock:
            statement = statement.with_for_update()
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "BENEFITS_PLAN_NOT_FOUND"})
        self._assert_scope(record.project_workspace_id)
        return record

    def _version(self, version_id: int, *, lock: bool = False) -> StrategicBenefitsPlanVersion:
        statement = select(StrategicBenefitsPlanVersion).where(
            StrategicBenefitsPlanVersion.id == version_id,
            StrategicBenefitsPlanVersion.tenant_id == self.tenant_id,
        )
        if lock:
            statement = statement.with_for_update()
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "BENEFITS_PLAN_VERSION_NOT_FOUND"})
        return record

    def _plan_version(
        self, plan_id: int, version_id: int, *, lock: bool = False
    ) -> tuple[StrategicBenefitsPlan, StrategicBenefitsPlanVersion]:
        plan = self._plan(plan_id, lock=lock)
        version = self._version(version_id, lock=lock)
        if version.benefits_plan_id != plan.id:
            raise HTTPException(status_code=404, detail={"code": "BENEFITS_PLAN_VERSION_NOT_FOUND"})
        return plan, version

    def _current_version(
        self, plan: StrategicBenefitsPlan, *, required: bool = True
    ) -> StrategicBenefitsPlanVersion | None:
        record = (
            self.db.scalar(
                select(StrategicBenefitsPlanVersion).where(
                    StrategicBenefitsPlanVersion.id == plan.current_version_id,
                    StrategicBenefitsPlanVersion.tenant_id == self.tenant_id,
                    StrategicBenefitsPlanVersion.benefits_plan_id == plan.id,
                )
            )
            if plan.current_version_id
            else None
        )
        if record is None and required:
            raise HTTPException(status_code=409, detail={"code": "CURRENT_BENEFITS_PLAN_VERSION_REQUIRED"})
        return record

    def _project(self, project_id: int) -> EnterpriseWorkspace:
        record = self.db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.id == project_id,
                EnterpriseWorkspace.tenant_id == self.tenant_id,
                EnterpriseWorkspace.workspace_type_code == "project",
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "PROJECT_WORKSPACE_NOT_FOUND"})
        return record

    def _workspace(self, workspace_id: int) -> EnterpriseWorkspace:
        record = self.db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.id == workspace_id,
                EnterpriseWorkspace.tenant_id == self.tenant_id,
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "WORKSPACE_NOT_FOUND"})
        return record

    def _workspace_path(self, workspace: EnterpriseWorkspace) -> list[EnterpriseWorkspace]:
        path: list[EnterpriseWorkspace] = []
        current: EnterpriseWorkspace | None = workspace
        seen: set[int] = set()
        while current is not None and current.id not in seen:
            seen.add(current.id)
            path.append(current)
            current = self._workspace(current.parent_id) if current.parent_id else None
        return list(reversed(path))

    def _user(self, user_id: int) -> UserAccount:
        record = self.db.scalar(
            select(UserAccount).where(
                UserAccount.id == user_id,
                UserAccount.tenant_id == self.tenant_id,
                UserAccount.status == "active",
            )
        )
        if record is None:
            raise HTTPException(status_code=422, detail={"code": "USER_NOT_FOUND"})
        return record

    def _benefit(self, benefit_id: int, *, lock: bool = False) -> StrategicBenefit:
        statement = select(StrategicBenefit).where(
            StrategicBenefit.id == benefit_id,
            StrategicBenefit.tenant_id == self.tenant_id,
        )
        if lock:
            statement = statement.with_for_update()
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "STRATEGIC_BENEFIT_NOT_FOUND"})
        return record

    def _snapshot(self, snapshot_id: int, *, lock: bool = False) -> StrategicBenefitVersionSnapshot:
        statement = select(StrategicBenefitVersionSnapshot).where(
            StrategicBenefitVersionSnapshot.id == snapshot_id,
            StrategicBenefitVersionSnapshot.tenant_id == self.tenant_id,
        )
        if lock:
            statement = statement.with_for_update()
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "BENEFIT_SNAPSHOT_NOT_FOUND"})
        return record

    def _benefit_snapshot(
        self,
        version: StrategicBenefitsPlanVersion,
        benefit_id: int,
        *,
        lock: bool = False,
    ) -> tuple[StrategicBenefit, StrategicBenefitVersionSnapshot]:
        benefit = self._benefit(benefit_id, lock=lock)
        if benefit.benefits_plan_id != version.benefits_plan_id:
            raise HTTPException(status_code=404, detail={"code": "STRATEGIC_BENEFIT_NOT_FOUND"})
        statement = select(StrategicBenefitVersionSnapshot).where(
            StrategicBenefitVersionSnapshot.tenant_id == self.tenant_id,
            StrategicBenefitVersionSnapshot.plan_version_id == version.id,
            StrategicBenefitVersionSnapshot.strategic_benefit_id == benefit.id,
        )
        if lock:
            statement = statement.with_for_update()
        snapshot = self.db.scalar(statement)
        if snapshot is None:
            raise HTTPException(status_code=404, detail={"code": "BENEFIT_SNAPSHOT_NOT_FOUND"})
        return benefit, snapshot

    def _snapshots(self, version_id: int) -> list[StrategicBenefitVersionSnapshot]:
        return list(
            self.db.scalars(
                select(StrategicBenefitVersionSnapshot)
                .where(
                    StrategicBenefitVersionSnapshot.tenant_id == self.tenant_id,
                    StrategicBenefitVersionSnapshot.plan_version_id == version_id,
                )
                .order_by(StrategicBenefitVersionSnapshot.id)
            ).all()
        )

    def _measures(self, snapshot_id: int) -> list[StrategicBenefitMeasure]:
        return list(
            self.db.scalars(
                select(StrategicBenefitMeasure)
                .where(
                    StrategicBenefitMeasure.tenant_id == self.tenant_id,
                    StrategicBenefitMeasure.benefit_snapshot_id == snapshot_id,
                )
                .order_by(StrategicBenefitMeasure.is_primary.desc(), StrategicBenefitMeasure.id)
            ).all()
        )

    def _benefit_number(self, benefit_id: int) -> str:
        value = self.db.scalar(
            select(StrategicBenefit.benefit_number).where(
                StrategicBenefit.id == benefit_id,
                StrategicBenefit.tenant_id == self.tenant_id,
            )
        )
        if value is None:
            raise HTTPException(status_code=404, detail={"code": "STRATEGIC_BENEFIT_NOT_FOUND"})
        return str(value)

    def _configuration(self, configuration_id: int | None, *, lock: bool = False) -> AdminConfiguration:
        statement = select(AdminConfiguration).where(
            AdminConfiguration.id == configuration_id,
            AdminConfiguration.tenant_id == self.tenant_id,
            AdminConfiguration.kind == CONFIGURATION_KIND,
        )
        if lock:
            statement = statement.with_for_update()
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "BENEFITS_CONFIGURATION_NOT_FOUND"})
        return record

    def _published_configuration(self) -> AdminConfiguration:
        record = self.db.scalar(
            select(AdminConfiguration)
            .where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == CONFIGURATION_KIND,
                AdminConfiguration.status == "published",
            )
            .order_by(AdminConfiguration.revision.desc())
        )
        if record is None:
            raise HTTPException(status_code=409, detail={"code": "PUBLISHED_BENEFITS_CONFIGURATION_REQUIRED"})
        return record

    def _ensure_sequences(self) -> None:
        for rule_code in (PLAN_NUMBER_RULE, BENEFIT_NUMBER_RULE):
            exists = self.db.scalar(
                select(AdminNumberSequence.id).where(
                    AdminNumberSequence.tenant_id == self.tenant_id,
                    AdminNumberSequence.rule_code == rule_code,
                    AdminNumberSequence.scope_key == "tenant",
                )
            )
            if exists is None:
                self.db.add(
                    AdminNumberSequence(
                        tenant_id=self.tenant_id,
                        rule_code=rule_code,
                        scope_key="tenant",
                        next_value=1,
                        version=1,
                    )
                )

    def _reserve_number(self, rule_code: str, configuration: dict[str, Any]) -> str:
        sequence = self.db.scalar(
            select(AdminNumberSequence)
            .where(
                AdminNumberSequence.tenant_id == self.tenant_id,
                AdminNumberSequence.rule_code == rule_code,
                AdminNumberSequence.scope_key == "tenant",
            )
            .with_for_update()
        )
        if sequence is None:
            sequence = AdminNumberSequence(
                tenant_id=self.tenant_id,
                rule_code=rule_code,
                scope_key="tenant",
                next_value=1,
                version=1,
            )
            self.db.add(sequence)
            self.db.flush()
        value = sequence.next_value
        sequence.next_value += 1
        sequence.version += 1
        sequence.updated_at = utc_now()
        numbering = dict(configuration.get("numbering") or {})
        prefix_key = "plan_prefix" if rule_code == PLAN_NUMBER_RULE else "benefit_prefix"
        fallback = "BPL" if rule_code == PLAN_NUMBER_RULE else "BEN"
        prefix = str(numbering.get(prefix_key) or fallback)
        padding = int(numbering.get("padding") or 6)
        return f"{prefix}-{value:0{padding}d}"

    def _idempotent_version(
        self,
        field: str,
        key: str,
        *,
        plan_id: int | None = None,
        version_id: int | None = None,
        payload_value: str | None = None,
    ) -> StrategicBenefitsPlanVersion | None:
        if field not in {
            "create_idempotency_key",
            "submit_idempotency_key",
            "review_idempotency_key",
            "return_idempotency_key",
            "complete_idempotency_key",
            "void_idempotency_key",
            "refresh_idempotency_key",
        }:
            raise ValueError("Unsupported idempotency field")
        record = self.db.scalar(
            select(StrategicBenefitsPlanVersion).where(
                StrategicBenefitsPlanVersion.tenant_id == self.tenant_id,
                getattr(StrategicBenefitsPlanVersion, field) == key,
            )
        )
        if record is None:
            return None
        self._plan(record.benefits_plan_id)
        if plan_id is not None and record.benefits_plan_id != plan_id:
            self._idempotency_conflict()
        if version_id is not None and record.id != version_id:
            self._idempotency_conflict()
        persisted_payload = {
            "create_idempotency_key": record.version_purpose,
            "return_idempotency_key": record.return_reason,
            "void_idempotency_key": record.void_reason,
        }.get(field)
        if payload_value is not None and persisted_payload != payload_value:
            self._idempotency_conflict()
        return record

    @staticmethod
    def _idempotency_conflict() -> None:
        raise HTTPException(status_code=409, detail={"code": "IDEMPOTENCY_KEY_REUSED"})

    def _touch(self, plan: StrategicBenefitsPlan, version: StrategicBenefitsPlanVersion) -> None:
        now = utc_now()
        version.updated_by = self.actor_id
        version.updated_at = now
        version.revision_version += 1
        plan.updated_by = self.actor_id
        plan.updated_at = now
        plan.revision_version += 1

    @staticmethod
    def _assert_editable(version: StrategicBenefitsPlanVersion) -> None:
        if version.status != "DRAFT":
            raise HTTPException(status_code=409, detail={"code": "BENEFITS_PLAN_VERSION_NOT_EDITABLE"})

    def _enforce_sod(self, version: StrategicBenefitsPlanVersion) -> None:
        configuration = self._configuration(version.configuration_id)
        required = bool(
            dict((configuration.content_json or {}).get("separation_of_duties") or {}).get(
                "reviewer_must_differ_from_preparer", True
            )
        )
        if required and version.preparer_user_id == self.actor_id:
            raise HTTPException(status_code=409, detail={"code": "SEPARATION_OF_DUTIES_REQUIRED"})

    @staticmethod
    def _content_hash(version: StrategicBenefitsPlanVersion) -> str:
        return _hash(
            {
                "overview": version.overview_json or {},
                "outputs": version.outputs_json or [],
                "outcomes": version.outcomes_json or [],
                "assumptions": version.assumptions_json or [],
                "constraints": version.constraints_json or [],
                "fel_stage_code": version.fel_stage_code,
            }
        )

    @staticmethod
    def _snapshot_hash(snapshot: StrategicBenefitVersionSnapshot) -> str:
        return _hash(
            {
                "benefit_id": snapshot.strategic_benefit_id,
                "name": snapshot.benefit_name,
                "description": snapshot.benefit_description,
                "direction": snapshot.benefit_direction,
                "type": snapshot.benefit_type,
                "category": snapshot.benefit_category,
                "strategic_objectives": snapshot.strategic_objective_refs_json or [],
                "source_need": snapshot.source_need_reference_json or {},
                "source_business_analysis": snapshot.source_business_analysis_reference_json or {},
                "source_project_proposal": snapshot.source_project_proposal_reference_json or {},
                "source_business_case": snapshot.source_business_case_reference_json or {},
                "expected_outputs": snapshot.expected_outputs_json or [],
                "expected_outcomes": snapshot.expected_outcomes_json or [],
                "benefit_statement": snapshot.benefit_statement,
                "owner": {
                    "type": snapshot.owner_type,
                    "user_id": snapshot.owner_user_id,
                    "organization_unit_id": snapshot.owner_organization_unit_id,
                    "security_role_id": snapshot.owner_security_role_id,
                    "reference": snapshot.owner_reference,
                    "snapshot": snapshot.owner_snapshot_json or {},
                    "effective_from": snapshot.owner_effective_from,
                    "effective_to": snapshot.owner_effective_to,
                    "accountability": snapshot.accountability_statement,
                    "acceptance": snapshot.owner_acceptance_status,
                },
                "expected_value": snapshot.expected_value_json or {},
                "monetizable": snapshot.monetizable_flag,
                "dependencies": snapshot.dependencies_json or [],
                "assumptions": snapshot.assumptions_json or [],
                "constraints": snapshot.constraints_json or [],
                "risk_references": snapshot.risk_references_json or [],
                "status": snapshot.status,
            }
        )

    @staticmethod
    def _measure_hash(measure: StrategicBenefitMeasure) -> str:
        return _hash(
            {
                "code": measure.measure_code,
                "name": measure.measure_name,
                "definition": measure.definition,
                "unit": measure.unit_of_measure,
                "direction": measure.direction,
                "is_primary": measure.is_primary,
                "baseline_status": measure.baseline_status,
                "baseline_value": measure.baseline_value_json,
                "baseline_as_of": measure.baseline_as_of_date,
                "baseline_source": measure.baseline_source,
                "baseline_evidence": measure.baseline_evidence_reference,
                "baseline_confidence": measure.baseline_confidence,
                "target_value": measure.target_value_json,
                "target_date": measure.target_date,
                "target_basis": measure.target_basis,
                "tolerance": measure.tolerance_json or {},
                "measurement_method": measure.measurement_method,
                "measurement_frequency": measure.measurement_frequency,
                "data_source": measure.data_source_description,
                "measurement_owner": measure.measurement_owner_reference_json or {},
            }
        )

    @staticmethod
    def _plan_hash(version: StrategicBenefitsPlanVersion) -> str:
        return _hash(
            {
                "benefits_plan_id": version.benefits_plan_id,
                "version_number": version.version_number,
                "version_purpose": version.version_purpose,
                "fel_stage_code": version.fel_stage_code,
                "content_hash": version.content_hash,
                "benefit_set_hash": version.benefit_set_hash,
                "traceability_hash": version.traceability_hash,
                "configuration_hash": version.configuration_hash,
                "source_bundle_hash": version.source_bundle_hash,
                "readiness": version.readiness_json or {},
            }
        )

    @staticmethod
    def _configuration_issues(content: dict[str, Any]) -> list[str]:
        issues: list[str] = []
        for catalog in (
            "benefit_types",
            "benefit_categories",
            "measure_directions",
            "units_of_measure",
            "measurement_frequencies",
        ):
            values = content.get(catalog)
            if not isinstance(values, list) or not values or len(values) != len(set(map(str, values))):
                issues.append(f"INVALID_OR_EMPTY_CATALOG:{catalog}")
        applicability = content.get("enabled_by_governance_model")
        if not isinstance(applicability, dict) or "CAPITAL_OWNER" not in applicability:
            issues.append("GOVERNANCE_MODEL_APPLICABILITY_REQUIRED")
        sod = dict(content.get("separation_of_duties") or {})
        if not sod.get("reviewer_must_differ_from_preparer", False):
            issues.append("AUTHOR_REVIEWER_SOD_REQUIRED")
        requirements = content.get("requirements")
        if not isinstance(requirements, dict):
            issues.append("BENEFITS_REQUIREMENTS_REQUIRED")
        try:
            minimum = int(content.get("minimum_benefits", -1))
        except (TypeError, ValueError):
            minimum = -1
        if minimum < 1:
            issues.append("MINIMUM_BENEFITS_INVALID")
        thresholds = content.get("coverage_thresholds")
        if not isinstance(thresholds, dict):
            issues.append("COVERAGE_THRESHOLDS_REQUIRED")
        else:
            for key in ("benefit_owner", "measurement", "baseline", "target", "traceability"):
                try:
                    value = float(thresholds.get(key, -1))
                except (TypeError, ValueError):
                    value = -1
                if value < 0 or value > 100:
                    issues.append(f"COVERAGE_THRESHOLD_OUT_OF_RANGE:{key}")
        tailoring_rules = content.get("tailoring_rules", [])
        tailoring_keys = {
            "project_size",
            "project_risk",
            "project_complexity",
            "project_type",
            "governance_model",
            "gate_profile",
            "fel_stage",
            "benefit_type",
        }
        invalid_tailoring = not isinstance(tailoring_rules, list)
        for rule in tailoring_rules if isinstance(tailoring_rules, list) else []:
            match = rule.get("match") if isinstance(rule, dict) else None
            overrides = rule.get("overrides") if isinstance(rule, dict) else None
            if (
                not isinstance(match, dict)
                or not match
                or not set(match).issubset(tailoring_keys)
                or any(value in (None, "", []) for value in match.values())
                or not isinstance(overrides, dict)
                or not overrides
            ):
                invalid_tailoring = True
                break
        if invalid_tailoring:
            issues.append("INVALID_TAILORING_RULES")
        return list(dict.fromkeys(issues))

    def _tailored_policy(
        self,
        project: EnterpriseWorkspace | None,
        configuration: dict[str, Any],
        fel_stage_code: str | None,
    ) -> dict[str, Any]:
        effective = deepcopy(configuration or {})
        if project is None:
            return effective
        metadata = dict((project.defaults_json or {}).get("_project", {}))
        actual = {
            "project_size": str(metadata.get("project_size") or metadata.get("size_class") or ""),
            "project_risk": str(metadata.get("project_risk") or metadata.get("risk_class") or ""),
            "project_complexity": str(metadata.get("project_complexity") or metadata.get("complexity_class") or ""),
            "project_type": self._project_type(project),
            "governance_model": self._governance(project),
            "gate_profile": str(metadata.get("gate_profile") or ""),
            "fel_stage": str(fel_stage_code or metadata.get("fel_stage") or "FEL-1"),
            "benefit_type": "*",
        }
        for rule in list(configuration.get("tailoring_rules") or []):
            match = dict(rule.get("match") or {})
            matches = True
            for key, expected_values in match.items():
                if key not in actual:
                    matches = False
                    break
                values = expected_values if isinstance(expected_values, list) else [expected_values]
                normalized = {str(value).upper() for value in values}
                if "*" not in normalized and actual[key].upper() not in normalized:
                    matches = False
                    break
            if not matches:
                continue
            for key, value in dict(rule.get("overrides") or {}).items():
                if isinstance(value, dict) and isinstance(effective.get(key), dict):
                    effective[key] = {**dict(effective[key]), **deepcopy(value)}
                else:
                    effective[key] = deepcopy(value)
        return effective

    def _is_applicable(self, project: EnterpriseWorkspace, configuration: dict[str, Any]) -> bool:
        governance = self._governance(project)
        applicability = dict(configuration.get("enabled_by_governance_model") or {})
        if governance in applicability:
            return bool(applicability[governance])
        return bool(applicability.get("LEGACY_UNCLASSIFIED", False))

    @staticmethod
    def _project_type(project: EnterpriseWorkspace) -> str:
        return str(dict((project.defaults_json or {}).get("_project", {})).get("project_type") or "OTHER")

    @staticmethod
    def _governance(project: EnterpriseWorkspace) -> str:
        value = str(dict((project.defaults_json or {}).get("_project", {})).get("governance_model") or "")
        return value.upper() or "LEGACY_UNCLASSIFIED"

    @staticmethod
    def _validate_purpose(value: str, *, allow_initial: bool) -> None:
        if value not in VERSION_PURPOSES or (not allow_initial and value == "INITIAL_BENEFITS_PLAN"):
            raise HTTPException(status_code=422, detail={"code": "INVALID_BENEFITS_VERSION_PURPOSE"})

    def _assert_scope(self, workspace_id: int) -> None:
        if self.context is None or self.context.organization_wide:
            return
        if workspace_id not in self.context.workspace_ids:
            raise HTTPException(status_code=404, detail={"code": "BENEFITS_PLAN_NOT_FOUND"})

    def _organization_wide(self) -> bool:
        return bool(self.context is None or self.context.organization_wide)

    def _configuration_in_authorized_scope(self, record: AdminConfiguration) -> bool:
        if self.context is None or self.context.organization_wide:
            return True
        workspace_id = dict((record.content_json or {}).get("scope") or {}).get("workspace_id")
        return workspace_id is not None and int(workspace_id) in self.context.workspace_ids

    def _assert_configuration_admin_scope(self, record: AdminConfiguration) -> None:
        if not self._configuration_in_authorized_scope(record):
            raise HTTPException(status_code=404, detail={"code": "BENEFITS_CONFIGURATION_NOT_FOUND"})

    @staticmethod
    def _check_version(actual: int, expected: int) -> None:
        if actual != expected:
            raise HTTPException(
                status_code=412,
                detail={"code": "ETAG_MISMATCH", "current_version": actual, "expected_version": expected},
            )

    @staticmethod
    def _chain_source_id(chain: list[dict[str, Any]]) -> int | None:
        return chain[0].get("workspace_id") if chain else None

    @staticmethod
    def _hash_delta(before: dict[str, Any], after: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {"source": key, "before": before.get(key), "after": after.get(key)}
            for key in sorted(set(before) | set(after))
            if before.get(key) != after.get(key)
        ]

    @staticmethod
    def _encode_cursor(updated_at: datetime, record_id: int) -> str:
        payload = json.dumps({"updated_at": updated_at.isoformat(), "id": record_id}, separators=(",", ":"))
        return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_cursor(value: str) -> tuple[datetime, int]:
        try:
            padding = "=" * (-len(value) % 4)
            payload = json.loads(base64.urlsafe_b64decode((value + padding).encode("ascii")))
            return datetime.fromisoformat(str(payload["updated_at"])), int(payload["id"])
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=422, detail={"code": "INVALID_BENEFITS_PLAN_CURSOR"}) from exc

    @staticmethod
    def _encode_simple_cursor(record_id: int) -> str:
        return base64.urlsafe_b64encode(str(record_id).encode("ascii")).decode("ascii").rstrip("=")

    @staticmethod
    def _decode_simple_cursor(value: str) -> int:
        try:
            padding = "=" * (-len(value) % 4)
            record_id = int(base64.urlsafe_b64decode((value + padding).encode("ascii")).decode("ascii"))
            if record_id <= 0:
                raise ValueError
            return record_id
        except (ValueError, UnicodeDecodeError) as exc:
            raise HTTPException(status_code=422, detail={"code": "INVALID_BENEFITS_TRACEABILITY_CURSOR"}) from exc

    def _event(self, event_type: str, target_type: str, target_id: int | None, metadata: dict[str, Any]) -> None:
        self.db.add(
            SecurityEvent(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                event_type=event_type,
                outcome="success",
                target_type=target_type,
                target_id=target_id,
                metadata_json=deepcopy(metadata),
            )
        )
