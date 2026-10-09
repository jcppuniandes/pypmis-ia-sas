"""Gate 07M-COMM orchestration and deterministic commercial readiness.

This service owns strategic commercial intent only.  It never creates or
mutates RFQs, tenders, bidders, vendors, contracts, commitments, POs, invoices,
payments, or operational procurement records.
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
from app.domain.models import AdminConfiguration, AdminNumberSequence, EnterpriseWorkspace, SecurityEvent
from app.modules.business_analysis.models import BusinessAnalysis
from app.modules.business_case.models import BusinessCase, BusinessCaseRevision
from app.modules.commercial_strategy.models import CommercialContractingStrategy, CommercialStrategyVersion
from app.modules.commercial_strategy.schemas import (
    CommercialConfigurationPreviewOut,
    CommercialReadinessProviderOut,
    CommercialStrategyHistoryOut,
    CommercialStrategyOptionsOut,
    CommercialStrategyOut,
    CommercialStrategyReadinessOut,
    CommercialStrategyRefreshPreviewOut,
    CommercialStrategyVersionOut,
)
from app.modules.economic_financial_model.models import EconomicFinancialModel, EconomicFinancialModelVersion
from app.modules.funds_manager.models import FundingReadinessSnapshot
from app.modules.permit_readiness.models import PermitReadinessAssessment
from app.modules.portfolio_budget.models import PortfolioBudgetScenario, PortfolioBudgetScenarioProject
from app.modules.project_creation.models import ProjectCreationRequest
from app.modules.project_definition.models import ProjectFELStatus
from app.modules.project_proposal.models import ProjectProposal
from app.modules.risk_readiness.models import RiskReadinessAssessment

CONFIGURATION_KIND = "commercial_strategy_configuration"
NUMBER_RULE = "COMMERCIAL_STRATEGY"
PROVIDER_KEY = "COMMERCIAL_READINESS_PROVIDER"
SOURCE_MODULE = "COMMERCIAL_CONTRACTING_STRATEGY"
EVIDENCE_TYPE = "COMMERCIAL_READINESS"
READY_OUTPUT = "READY_FOR_GOVERNED_COMMERCIAL_READINESS_EVIDENCE"
NEXT_PROCESS = "BUILD_STRATEGIC_BENEFITS_PLAN_AND_BENEFITS_TRACEABILITY"
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100

VERSION_PURPOSES = frozenset(
    {
        "INITIAL_COMMERCIAL_ASSESSMENT",
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
    "COMMERCIAL_CONTEXT_READINESS",
    "PROCUREMENT_APPROACH_READINESS",
    "PACKAGING_READINESS",
    "CONTRACTING_MODEL_READINESS",
    "MARKET_READINESS",
    "SUPPLY_CHAIN_READINESS",
    "RISK_ALLOCATION_READINESS",
    "PAYMENT_MECHANISM_READINESS",
    "COMMERCIAL_RECOMMENDATION_READINESS",
    "OVERALL_COMMERCIAL_READINESS",
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
    "procurement_approaches": [
        "TRADITIONAL_DESIGN_BID_BUILD",
        "DESIGN_BUILD",
        "EPC",
        "EPCM",
        "CONSTRUCTION_MANAGEMENT",
        "FRAMEWORK_IDIQ",
        "ALLIANCE_COLLABORATIVE",
        "PPP_CONCESSION",
        "DIRECT_AWARD_LEGALLY_PERMITTED",
        "OWNER_FURNISHED_MULTIPLE_PACKAGES",
        "OTHER",
    ],
    "contracting_models": [
        "LUMP_SUM",
        "UNIT_PRICE",
        "COST_REIMBURSABLE",
        "TARGET_COST",
        "GMP",
        "TIME_AND_MATERIALS",
        "HYBRID",
        "ALLIANCE_PAIN_GAIN",
        "CONCESSION_AVAILABILITY_PAYMENT",
        "OTHER",
    ],
    "package_types": ["WORK", "SERVICE", "EQUIPMENT", "MATERIAL", "MIXED", "OTHER"],
    "risk_allocation_categories": [
        "DESIGN",
        "CONSTRUCTION",
        "INTERFACE",
        "MARKET",
        "SCHEDULE",
        "COST",
        "REGULATORY",
        "SUPPLY_CHAIN",
        "PERFORMANCE",
        "OTHER",
    ],
    "payment_mechanisms": [
        "MILESTONE",
        "PROGRESS_MEASURED_WORK",
        "UNIT_RATE",
        "COST_REIMBURSABLE",
        "TARGET_COST",
        "AVAILABILITY_PAYMENT",
        "FIXED_PERIODIC",
        "HYBRID",
        "OTHER",
    ],
    "incentive_mechanisms": [
        "PAIN_GAIN_SHARE",
        "SCHEDULE_INCENTIVE",
        "PERFORMANCE_INCENTIVE",
        "AVAILABILITY_INCENTIVE",
        "QUALITY_INCENTIVE",
        "LIQUIDATED_DAMAGES_CONCEPT",
        "SERVICE_LEVEL_MECHANISM",
        "NONE",
        "OTHER",
    ],
    "market_assessment_criteria": [
        "supplier_depth",
        "competition",
        "relevant_experience",
        "capacity",
        "financial_capability",
        "market_appetite",
        "lead_times",
        "market_timing",
    ],
    "supply_chain_criteria": [
        "long_lead_items",
        "specialized_suppliers",
        "import_dependence",
        "logistics_constraints",
        "local_content_requirements",
        "capacity_constraints",
        "single_source_dependency",
    ],
    "required_sections": [
        "commercial_context",
        "procurement_approach",
        "packages",
        "contracting_model",
        "market_assessment",
        "supply_chain_constraints",
        "risk_allocations",
        "payment_mechanism",
        "recommendation",
    ],
    "required_fields": {
        "package": ["package_code", "package_name", "package_type", "scope_summary"],
        "risk_allocation": [
            "commercial_risk_category",
            "risk_description",
            "preferred_owner",
            "allocation_rationale",
            "contractual_treatment",
        ],
        "alternative": [
            "procurement_approach",
            "contracting_model",
            "risk_allocation",
            "payment_mechanism",
            "market_fit",
            "commercial_risk",
            "pros",
            "cons",
            "rating",
        ],
        "recommendation": [
            "recommended_procurement_approach",
            "recommended_packaging_strategy",
            "recommended_contracting_model",
            "recommended_payment_mechanism",
            "recommended_incentive_strategy",
            "rationale",
            "commercial_recommendation_status",
        ],
    },
    "alternatives_required_by_fel_stage": {"FEL-1": False, "FEL-2": False, "FEL-3": True, "FFA": True},
    "minimum_alternatives": 2,
    "market_blocking_threshold": 60,
    "tailoring_rules": [],
    "separation_of_duties": {"reviewer_must_differ_from_preparer": True},
    "freshness": {"require_current_sources": True},
    "numbering": {"prefix": "CCS", "padding": 6},
    "scope": {"workspace_id": None, "inherit_to_descendants": True},
}


EMPTY_CONTENT: dict[str, Any] = {
    "commercial_context": "",
    "procurement_approach": None,
    "packages": [],
    "contracting_model": None,
    "market_assessment": {},
    "supply_chain_constraints": [],
    "risk_allocations": [],
    "payment_mechanism": None,
    "incentive_strategy": {},
    "guarantees_securities_strategy": {},
    "commercial_assumptions": [],
    "commercial_constraints": [],
    "dependencies": [],
    "legal_regulatory_considerations": [],
    "alternatives": [],
    "recommendation": {},
    "conditions_open_issues": [],
}


class CommercialStrategyService:
    def __init__(self, db: Session, tenant_id: int, actor_id: int, context=None) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.actor_id = actor_id
        self.context = context

    # Configuration -----------------------------------------------------
    def ensure_seed(self) -> None:
        existing = self.db.scalar(
            select(AdminConfiguration.id).where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == CONFIGURATION_KIND,
                AdminConfiguration.status == "published",
            )
        )
        if existing is not None:
            self._ensure_sequence()
            return
        content = deepcopy(DEFAULT_CONFIGURATION)
        self.db.add(
            AdminConfiguration(
                tenant_id=self.tenant_id,
                kind=CONFIGURATION_KIND,
                code="default",
                name="Default Commercial Strategy Policy",
                description="Gate 07M-COMM catalogs, applicability, readiness, inheritance and SoD policy.",
                status="published",
                revision=1,
                version=1,
                content_json=content,
                content_hash=_hash(content),
                published_at=utc_now(),
                created_by_user_id=self.actor_id,
            )
        )
        self._ensure_sequence()
        self._configuration_event("commercial_strategy.configuration_published", None, {"seed": True})
        try:
            self.db.commit()
        except IntegrityError:
            self.db.rollback()

    def options(self, project_workspace_id: int | None = None) -> CommercialStrategyOptionsOut:
        project = self._project(project_workspace_id) if project_workspace_id is not None else None
        configuration = self._resolve_configuration(project)[0] if project else self._published_configuration()
        content = (
            self._tailored_policy(project, configuration.content_json, None)
            if project
            else dict(configuration.content_json or {})
        )

        def catalog(key: str) -> list[str]:
            return [str(value) for value in list(content.get(key) or [])]

        return CommercialStrategyOptionsOut(
            version_purposes=sorted(VERSION_PURPOSES),
            readiness_states=sorted(READINESS_STATES),
            queues=list(QUEUES),
            provider_key=PROVIDER_KEY,
            provider_status="AVAILABLE",
            configuration_id=configuration.id,
            configuration_revision=configuration.revision,
            configuration_hash=configuration.content_hash,
            procurement_approaches=catalog("procurement_approaches"),
            contracting_models=catalog("contracting_models"),
            package_types=catalog("package_types"),
            risk_allocation_categories=catalog("risk_allocation_categories"),
            payment_mechanisms=catalog("payment_mechanisms"),
            incentive_mechanisms=catalog("incentive_mechanisms"),
            market_assessment_criteria=catalog("market_assessment_criteria"),
            supply_chain_criteria=catalog("supply_chain_criteria"),
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
        return [record for record in records if self._configuration_in_authorized_scope(record)]

    def configuration_preview(
        self,
        project_workspace_id: int | None,
        configuration_id: int | None,
        content_json: dict[str, Any] | None,
    ) -> CommercialConfigurationPreviewOut:
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
                warnings.append("COMMERCIAL_STRATEGY_NOT_APPLICABLE_TO_PROJECT_CONTEXT")
            effective = self._tailored_policy(project, content, None)
        else:
            warnings.append("NO_PROJECT_SELECTED_FOR_EFFECTIVE_PREVIEW")
        return CommercialConfigurationPreviewOut(
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
        self._configuration_event(
            "commercial_strategy.configuration_cloned", record, {"source_configuration_id": source.id}
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
                detail={"code": "INVALID_COMMERCIAL_STRATEGY_CONFIGURATION", "issues": issues},
            )
        record.name = name
        record.description = description
        record.content_json = deepcopy(content_json)
        record.content_hash = _hash(content_json)
        record.version += 1
        record.updated_at = utc_now()
        self._configuration_event("commercial_strategy.configuration_updated", record)
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
            raise HTTPException(
                status_code=422,
                detail={"code": "INVALID_COMMERCIAL_STRATEGY_CONFIGURATION", "issues": issues},
            )
        record.status = "published"
        record.published_at = utc_now()
        record.version += 1
        record.updated_at = utc_now()
        self._configuration_event("commercial_strategy.configuration_published", record)
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
        self._configuration_event("commercial_strategy.configuration_archived", record)
        self.db.commit()
        self.db.refresh(record)
        return record

    # USER aggregate ----------------------------------------------------
    def list_page(
        self,
        *,
        queue: str,
        project_workspace_id: int | None,
        search: str,
        limit: int,
        cursor: str | None,
    ) -> tuple[list[CommercialStrategyOut], str | None]:
        normalized_queue = queue.strip().lower()
        normalized_queue = {"my_strategies": "mine", "all": "all_authorized"}.get(normalized_queue, normalized_queue)
        if normalized_queue not in {"", *QUEUES}:
            raise HTTPException(status_code=422, detail={"code": "INVALID_COMMERCIAL_STRATEGY_QUEUE"})
        statement = select(CommercialContractingStrategy).where(
            CommercialContractingStrategy.tenant_id == self.tenant_id
        )
        if project_workspace_id is not None:
            statement = statement.where(CommercialContractingStrategy.project_workspace_id == project_workspace_id)
        if self.context is not None and not self.context.organization_wide:
            allowed = list(self.context.workspace_ids)
            statement = statement.where(
                or_(
                    CommercialContractingStrategy.project_workspace_id.in_(allowed or [-1]),
                    CommercialContractingStrategy.created_by == self.actor_id,
                )
            )
        if normalized_queue in {"draft", "returned", "in_review", "completed"}:
            statement = statement.join(
                CommercialStrategyVersion,
                and_(
                    CommercialStrategyVersion.id == CommercialContractingStrategy.current_version_id,
                    CommercialStrategyVersion.tenant_id == self.tenant_id,
                ),
            )
        if normalized_queue == "draft":
            statement = statement.where(
                CommercialStrategyVersion.status == "DRAFT",
                CommercialStrategyVersion.return_reason.is_(None),
            )
        elif normalized_queue == "returned":
            statement = statement.where(
                CommercialStrategyVersion.status == "DRAFT",
                CommercialStrategyVersion.return_reason.is_not(None),
            )
        elif normalized_queue == "in_review":
            statement = statement.where(CommercialStrategyVersion.status == "IN_REVIEW")
        elif normalized_queue == "completed":
            statement = statement.where(CommercialStrategyVersion.status == "COMPLETED")
        elif normalized_queue == "mine":
            statement = statement.where(CommercialContractingStrategy.created_by == self.actor_id)
        if search.strip():
            token = f"%{search.strip().lower()}%"
            statement = statement.join(
                EnterpriseWorkspace,
                and_(
                    EnterpriseWorkspace.id == CommercialContractingStrategy.project_workspace_id,
                    EnterpriseWorkspace.tenant_id == self.tenant_id,
                ),
            ).where(
                or_(
                    func.lower(CommercialContractingStrategy.strategy_number).like(token),
                    func.lower(EnterpriseWorkspace.name).like(token),
                )
            )
        cursor_value = self._decode_cursor(cursor) if cursor else None
        if cursor_value:
            cursor_at, cursor_id = cursor_value
            statement = statement.where(
                or_(
                    CommercialContractingStrategy.updated_at < cursor_at,
                    and_(
                        CommercialContractingStrategy.updated_at == cursor_at,
                        CommercialContractingStrategy.id < cursor_id,
                    ),
                )
            )
        ordered = statement.order_by(
            CommercialContractingStrategy.updated_at.desc(),
            CommercialContractingStrategy.id.desc(),
        )
        readiness_by_strategy: dict[int, CommercialStrategyReadinessOut] = {}
        if normalized_queue in {"ready", "stale"}:
            rows = []
            for row in self.db.scalars(ordered.execution_options(yield_per=100)):
                version = self._current_version(row, required=False)
                if version is None:
                    continue
                readiness = self._recalculate(row, version, persist=False)
                matches = readiness.status == ("READY" if normalized_queue == "ready" else "STALE")
                if not matches:
                    continue
                rows.append(row)
                readiness_by_strategy[row.id] = readiness
                if len(rows) == limit + 1:
                    break
        else:
            rows = list(self.db.scalars(ordered.limit(limit + 1)).all())
        has_more = len(rows) > limit
        rows = rows[:limit]
        outputs = [self._strategy_out(row, readiness=readiness_by_strategy.get(row.id)) for row in rows]
        next_cursor = self._encode_cursor(rows[-1].updated_at, rows[-1].id) if has_more and rows else None
        return outputs, next_cursor

    def create(
        self,
        project_workspace_id: int,
        version_purpose: str,
        idempotency_key: str,
    ) -> CommercialStrategyOut:
        self._validate_purpose(version_purpose, allow_initial=True)
        duplicate = self.db.scalar(
            select(CommercialContractingStrategy).where(
                CommercialContractingStrategy.tenant_id == self.tenant_id,
                CommercialContractingStrategy.create_idempotency_key == idempotency_key,
            )
        )
        if duplicate:
            if duplicate.project_workspace_id != project_workspace_id:
                self._raise_idempotency_conflict()
            initial = self.db.scalar(
                select(CommercialStrategyVersion).where(
                    CommercialStrategyVersion.tenant_id == self.tenant_id,
                    CommercialStrategyVersion.commercial_strategy_id == duplicate.id,
                    CommercialStrategyVersion.version_number == 1,
                )
            )
            if initial is None or initial.version_purpose != version_purpose:
                self._raise_idempotency_conflict()
            return self._strategy_out(duplicate)
        project = self._project(project_workspace_id)
        self._assert_scope(project.id)
        existing = self.db.scalar(
            select(CommercialContractingStrategy).where(
                CommercialContractingStrategy.tenant_id == self.tenant_id,
                CommercialContractingStrategy.project_workspace_id == project.id,
            )
        )
        if existing:
            raise HTTPException(status_code=409, detail={"code": "COMMERCIAL_STRATEGY_ALREADY_EXISTS_FOR_PROJECT"})
        configuration, chain = self._resolve_configuration(project)
        if not self._is_applicable(project, configuration.content_json):
            raise HTTPException(
                status_code=409,
                detail={"code": "COMMERCIAL_STRATEGY_NOT_APPLICABLE", "governance_model": self._governance(project)},
            )
        references, hashes = self._source_bundle(project.id)
        record = CommercialContractingStrategy(
            tenant_id=self.tenant_id,
            project_workspace_id=project.id,
            strategy_number=self._reserve_number(configuration.content_json),
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
        self.db.add(record)
        self.db.flush()
        version = self._new_version(
            record,
            version_purpose,
            idempotency_key=f"{idempotency_key}:VERSION:1",
            configuration=configuration,
            source_references=references,
            source_hashes=hashes,
        )
        record.current_version_id = version.id
        self._event(
            "commercial_strategy.created",
            "CommercialContractingStrategy",
            record.id,
            {"project_workspace_id": project.id, "version_id": version.id},
        )
        self.db.commit()
        return self._strategy_out(record)

    def get(self, strategy_id: int) -> CommercialStrategyOut:
        return self._strategy_out(self._strategy(strategy_id))

    def by_project(self, project_workspace_id: int) -> CommercialStrategyOut:
        project = self._project(project_workspace_id)
        self._assert_scope(project.id)
        record = self.db.scalar(
            select(CommercialContractingStrategy).where(
                CommercialContractingStrategy.tenant_id == self.tenant_id,
                CommercialContractingStrategy.project_workspace_id == project.id,
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "COMMERCIAL_STRATEGY_NOT_FOUND"})
        return self._strategy_out(record)

    def update_version(
        self,
        strategy_id: int,
        version_id: int,
        expected_version: int,
        *,
        content_json: dict[str, Any],
        fel_stage_code: str | None,
        reviewer_user_id: int | None,
    ) -> CommercialStrategyVersionOut:
        strategy, version = self._strategy_version(strategy_id, version_id, lock=True)
        self._check_version(version.revision_version, expected_version)
        if version.status != "DRAFT":
            raise HTTPException(status_code=409, detail={"code": "COMMERCIAL_STRATEGY_VERSION_NOT_EDITABLE"})
        if version.preparer_user_id != self.actor_id and not self._organization_wide():
            raise HTTPException(status_code=403, detail={"code": "COMMERCIAL_STRATEGY_NOT_OWNED_BY_ACTOR"})
        self._validate_content_shape(content_json)
        version.content_json = deepcopy(content_json)
        if fel_stage_code is not None:
            version.fel_stage_code = fel_stage_code
        if reviewer_user_id is not None:
            version.reviewer_user_id = reviewer_user_id
        self._recalculate(strategy, version, persist=True)
        self._touch(strategy, version)
        self._event("commercial_strategy.version_updated", "CommercialStrategyVersion", version.id, {})
        self.db.commit()
        self.db.refresh(version)
        return self._version_out(version)

    def submit(
        self, strategy_id: int, version_id: int, expected_version: int, idempotency_key: str
    ) -> CommercialStrategyVersionOut:
        duplicate = self._idempotent_version(
            "submit_idempotency_key", idempotency_key, strategy_id=strategy_id, version_id=version_id
        )
        if duplicate:
            return self._version_out(duplicate)
        strategy, version = self._strategy_version(strategy_id, version_id, lock=True)
        self._check_version(version.revision_version, expected_version)
        if version.status != "DRAFT":
            raise HTTPException(status_code=409, detail={"code": "COMMERCIAL_STRATEGY_NOT_SUBMITTABLE"})
        readiness = self._recalculate(strategy, version, persist=True)
        if readiness.status != "READY":
            raise HTTPException(
                status_code=409,
                detail={"code": "COMMERCIAL_STRATEGY_BLOCKED", "blockers": readiness.blockers},
            )
        version.status = "IN_REVIEW"
        version.submit_idempotency_key = idempotency_key
        version.submitted_at = utc_now()
        strategy.status = "IN_REVIEW"
        self._touch(strategy, version)
        self._event("commercial_strategy.submitted", "CommercialStrategyVersion", version.id, {})
        self.db.commit()
        return self._version_out(version)

    def start_review(
        self, strategy_id: int, version_id: int, expected_version: int, idempotency_key: str
    ) -> CommercialStrategyVersionOut:
        duplicate = self._idempotent_version(
            "review_idempotency_key", idempotency_key, strategy_id=strategy_id, version_id=version_id
        )
        if duplicate:
            return self._version_out(duplicate)
        _strategy, version = self._strategy_version(strategy_id, version_id, lock=True)
        self._check_version(version.revision_version, expected_version)
        if version.status != "IN_REVIEW":
            raise HTTPException(status_code=409, detail={"code": "COMMERCIAL_STRATEGY_NOT_IN_REVIEW"})
        self._enforce_sod(version)
        if version.reviewer_user_id not in {None, self.actor_id}:
            raise HTTPException(status_code=409, detail={"code": "REVIEW_ASSIGNED_TO_ANOTHER_USER"})
        version.reviewer_user_id = self.actor_id
        version.review_idempotency_key = idempotency_key
        version.review_started_at = utc_now()
        version.updated_by = self.actor_id
        version.updated_at = utc_now()
        version.revision_version += 1
        self._event("commercial_strategy.review_started", "CommercialStrategyVersion", version.id, {})
        self.db.commit()
        return self._version_out(version)

    def return_version(
        self,
        strategy_id: int,
        version_id: int,
        expected_version: int,
        idempotency_key: str,
        reason: str,
    ) -> CommercialStrategyVersionOut:
        duplicate = self._idempotent_version(
            "return_idempotency_key",
            idempotency_key,
            strategy_id=strategy_id,
            version_id=version_id,
            payload_value=reason.strip(),
        )
        if duplicate:
            return self._version_out(duplicate)
        strategy, version = self._strategy_version(strategy_id, version_id, lock=True)
        self._check_version(version.revision_version, expected_version)
        if version.status != "IN_REVIEW":
            raise HTTPException(status_code=409, detail={"code": "COMMERCIAL_STRATEGY_NOT_RETURNABLE"})
        if version.reviewer_user_id not in {None, self.actor_id} and not self._organization_wide():
            raise HTTPException(status_code=409, detail={"code": "REVIEW_ASSIGNED_TO_ANOTHER_USER"})
        version.status = "DRAFT"
        version.return_reason = reason.strip()
        version.return_idempotency_key = idempotency_key
        version.returned_at = utc_now()
        strategy.status = "DRAFT"
        self._touch(strategy, version)
        self._event("commercial_strategy.returned", "CommercialStrategyVersion", version.id, {"reason": reason.strip()})
        self.db.commit()
        return self._version_out(version)

    def complete(
        self, strategy_id: int, version_id: int, expected_version: int, idempotency_key: str
    ) -> CommercialStrategyVersionOut:
        duplicate = self._idempotent_version(
            "complete_idempotency_key", idempotency_key, strategy_id=strategy_id, version_id=version_id
        )
        if duplicate:
            return self._version_out(duplicate)
        strategy, version = self._strategy_version(strategy_id, version_id, lock=True)
        self._check_version(version.revision_version, expected_version)
        if version.status != "IN_REVIEW":
            raise HTTPException(status_code=409, detail={"code": "COMMERCIAL_STRATEGY_NOT_COMPLETABLE"})
        self._enforce_sod(version)
        if version.reviewer_user_id != self.actor_id or version.review_started_at is None:
            raise HTTPException(status_code=409, detail={"code": "INDEPENDENT_REVIEW_REQUIRED"})
        readiness = self._recalculate(strategy, version, persist=True)
        if readiness.status != "READY" or readiness.blockers:
            raise HTTPException(
                status_code=409,
                detail={"code": "COMMERCIAL_STRATEGY_BLOCKED", "blockers": readiness.blockers},
            )
        version.status = "COMPLETED"
        version.complete_idempotency_key = idempotency_key
        version.completed_by = self.actor_id
        version.completed_at = utc_now()
        version.commercial_strategy_hash = self._version_hash(version)
        strategy.status = "COMPLETED"
        self._touch(strategy, version)
        self._event(
            "commercial_strategy.completed",
            "CommercialStrategyVersion",
            version.id,
            {"commercial_strategy_hash": version.commercial_strategy_hash},
        )
        self.db.commit()
        return self._version_out(version)

    def void(
        self,
        strategy_id: int,
        version_id: int,
        expected_version: int,
        idempotency_key: str,
        reason: str,
    ) -> CommercialStrategyVersionOut:
        duplicate = self._idempotent_version(
            "void_idempotency_key",
            idempotency_key,
            strategy_id=strategy_id,
            version_id=version_id,
            payload_value=reason.strip(),
        )
        if duplicate:
            return self._version_out(duplicate)
        strategy, version = self._strategy_version(strategy_id, version_id, lock=True)
        self._check_version(version.revision_version, expected_version)
        if version.status not in {"DRAFT", "IN_REVIEW"}:
            raise HTTPException(status_code=409, detail={"code": "COMMERCIAL_STRATEGY_NOT_VOIDABLE"})
        version.status = "VOIDED"
        version.void_reason = reason.strip()
        version.void_idempotency_key = idempotency_key
        version.voided_at = utc_now()
        strategy.status = "VOIDED"
        self._touch(strategy, version)
        self._event("commercial_strategy.voided", "CommercialStrategyVersion", version.id, {"reason": reason})
        self.db.commit()
        return self._version_out(version)

    def new_revision(
        self, strategy_id: int, version_purpose: str, idempotency_key: str
    ) -> CommercialStrategyVersionOut:
        self._validate_purpose(version_purpose, allow_initial=False)
        duplicate = self._idempotent_version(
            "create_idempotency_key",
            idempotency_key,
            strategy_id=strategy_id,
            payload_value=version_purpose,
        )
        if duplicate:
            return self._version_out(duplicate)
        strategy = self._strategy(strategy_id, lock=True)
        current = self._current_version(strategy)
        if current.status not in {"COMPLETED", "VOIDED"}:
            raise HTTPException(status_code=409, detail={"code": "OPEN_COMMERCIAL_STRATEGY_VERSION_EXISTS"})
        project = self._project(strategy.project_workspace_id)
        configuration, chain = self._resolve_configuration(project)
        references, hashes = self._source_bundle(project.id)
        version = self._new_version(
            strategy,
            version_purpose,
            idempotency_key=idempotency_key,
            configuration=configuration,
            source_references=references,
            source_hashes=hashes,
            source=current,
        )
        if current.status == "COMPLETED":
            current.status = "SUPERSEDED"
            current.updated_at = utc_now()
        strategy.current_version_id = version.id
        strategy.status = "DRAFT"
        strategy.configuration_id = configuration.id
        strategy.configuration_revision = configuration.revision
        strategy.configuration_hash = configuration.content_hash
        strategy.configuration_source_workspace_id = self._chain_source_id(chain)
        strategy.configuration_resolution_chain_json = chain
        strategy.updated_by = self.actor_id
        strategy.updated_at = utc_now()
        strategy.revision_version += 1
        self._event(
            "commercial_strategy.revision_created",
            "CommercialStrategyVersion",
            version.id,
            {"version_purpose": version_purpose, "supersedes_version_id": current.id},
        )
        self.db.commit()
        return self._version_out(version)

    def readiness(self, strategy_id: int) -> CommercialStrategyReadinessOut:
        strategy = self._strategy(strategy_id)
        version = self._current_version(strategy)
        return self._recalculate(strategy, version, persist=False)

    def history(self, strategy_id: int) -> list[CommercialStrategyHistoryOut]:
        strategy = self._strategy(strategy_id)
        versions = list(
            self.db.scalars(
                select(CommercialStrategyVersion)
                .where(
                    CommercialStrategyVersion.tenant_id == self.tenant_id,
                    CommercialStrategyVersion.commercial_strategy_id == strategy.id,
                )
                .order_by(CommercialStrategyVersion.version_number.desc())
            ).all()
        )
        events = list(
            self.db.scalars(
                select(SecurityEvent)
                .where(
                    SecurityEvent.tenant_id == self.tenant_id,
                    SecurityEvent.target_type == "CommercialStrategyVersion",
                    SecurityEvent.target_id.in_([item.id for item in versions] or [-1]),
                )
                .order_by(SecurityEvent.occurred_at)
            ).all()
        )
        by_id: dict[int, list[dict[str, Any]]] = {item.id: [] for item in versions}
        for event in events:
            if event.target_id in by_id:
                by_id[event.target_id].append(
                    {
                        "event_type": event.event_type,
                        "actor_user_id": event.user_id,
                        "occurred_at": event.occurred_at.isoformat(),
                        "metadata": deepcopy(event.metadata_json or {}),
                    }
                )
        return [
            CommercialStrategyHistoryOut(version=self._version_out(item), lifecycle_events=by_id[item.id])
            for item in versions
        ]

    def refresh_preview(self, strategy_id: int) -> CommercialStrategyRefreshPreviewOut:
        strategy = self._strategy(strategy_id)
        version = self._current_version(strategy)
        project = self._project(strategy.project_workspace_id)
        configuration, _chain = self._resolve_configuration(project)
        _references, current_hashes = self._source_bundle(project.id)
        source_delta = self._hash_delta(version.source_hashes_json, current_hashes)
        policy_delta = self._hash_delta(
            {"configuration": version.configuration_hash}, {"configuration": configuration.content_hash}
        )
        readiness = self._recalculate(strategy, version, persist=False)
        return CommercialStrategyRefreshPreviewOut(
            commercial_strategy_id=strategy.id,
            current_version_id=version.id,
            source_delta=source_delta,
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

    def refresh_apply(
        self, strategy_id: int, expected_version: int, idempotency_key: str
    ) -> CommercialStrategyVersionOut:
        duplicate = self._idempotent_version("refresh_idempotency_key", idempotency_key, strategy_id=strategy_id)
        if duplicate:
            return self._version_out(duplicate)
        strategy = self._strategy(strategy_id, lock=True)
        current = self._current_version(strategy)
        self._check_version(strategy.revision_version, expected_version)
        if current.status not in {"COMPLETED", "VOIDED"}:
            raise HTTPException(status_code=409, detail={"code": "REFRESH_REQUIRES_TERMINAL_VERSION"})
        preview = self.refresh_preview(strategy.id)
        project = self._project(strategy.project_workspace_id)
        configuration, chain = self._resolve_configuration(project)
        references, hashes = self._source_bundle(project.id)
        purpose = preview.recommended_version_purpose
        version = self._new_version(
            strategy,
            purpose,
            idempotency_key=None,
            configuration=configuration,
            source_references=references,
            source_hashes=hashes,
            source=current,
        )
        version.refresh_idempotency_key = idempotency_key
        if current.status == "COMPLETED":
            current.status = "SUPERSEDED"
            current.updated_at = utc_now()
        strategy.current_version_id = version.id
        strategy.status = "DRAFT"
        strategy.configuration_id = configuration.id
        strategy.configuration_revision = configuration.revision
        strategy.configuration_hash = configuration.content_hash
        strategy.configuration_source_workspace_id = self._chain_source_id(chain)
        strategy.configuration_resolution_chain_json = chain
        strategy.updated_by = self.actor_id
        strategy.updated_at = utc_now()
        strategy.revision_version += 1
        self._event(
            "commercial_strategy.refresh_applied",
            "CommercialStrategyVersion",
            version.id,
            {"source_delta": preview.source_delta, "policy_delta": preview.policy_delta},
        )
        self.db.commit()
        return self._version_out(version)

    def provider_evidence(self, project_workspace_id: int) -> CommercialReadinessProviderOut:
        strategy_out = self.by_project(project_workspace_id)
        if strategy_out.current_version is None:
            raise HTTPException(status_code=404, detail={"code": "COMMERCIAL_STRATEGY_VERSION_NOT_FOUND"})
        strategy = self._strategy(strategy_out.id)
        version = self._current_version(strategy)
        readiness = self._recalculate(strategy, version, persist=False)
        can_supply = bool(
            version.status == "COMPLETED"
            and readiness.status == "READY"
            and readiness.source_current
            and readiness.configuration_current
            and not readiness.blockers
        )
        return CommercialReadinessProviderOut(
            provider_key=PROVIDER_KEY,
            source_module=SOURCE_MODULE,
            evidence_type=EVIDENCE_TYPE,
            status="AVAILABLE",
            project_workspace_id=project_workspace_id,
            commercial_strategy_id=strategy.id,
            strategy_number=strategy.strategy_number,
            version_id=version.id,
            version_number=version.version_number,
            version_purpose=version.version_purpose,
            fel_stage_code=version.fel_stage_code,
            procurement_approach=self._selected_code(version.content_json.get("procurement_approach")),
            contracting_model=self._selected_code(version.content_json.get("contracting_model")),
            market_readiness=readiness.dimensions["MARKET_READINESS"],
            risk_allocation_readiness=readiness.dimensions["RISK_ALLOCATION_READINESS"],
            payment_mechanism_readiness=readiness.dimensions["PAYMENT_MECHANISM_READINESS"],
            overall_commercial_readiness=readiness.status,
            commercial_strategy_hash=version.commercial_strategy_hash,
            source_bundle_hash=version.source_bundle_hash,
            configuration_hash=version.configuration_hash,
            as_of_date=version.completed_at or version.updated_at,
            warnings=readiness.warnings,
            blockers=readiness.blockers,
            source_current=readiness.source_current,
            can_supply_investment_gate_evidence=can_supply,
        )

    # Internals ---------------------------------------------------------
    def _new_version(
        self,
        strategy: CommercialContractingStrategy,
        purpose: str,
        *,
        idempotency_key: str | None,
        configuration: AdminConfiguration,
        source_references: dict[str, Any],
        source_hashes: dict[str, str],
        source: CommercialStrategyVersion | None = None,
    ) -> CommercialStrategyVersion:
        number = (
            int(
                self.db.scalar(
                    select(func.coalesce(func.max(CommercialStrategyVersion.version_number), 0)).where(
                        CommercialStrategyVersion.tenant_id == self.tenant_id,
                        CommercialStrategyVersion.commercial_strategy_id == strategy.id,
                    )
                )
                or 0
            )
            + 1
        )
        fel = self.db.scalar(
            select(ProjectFELStatus).where(
                ProjectFELStatus.tenant_id == self.tenant_id,
                ProjectFELStatus.project_workspace_id == strategy.project_workspace_id,
            )
        )
        content = deepcopy(source.content_json if source else EMPTY_CONTENT)
        version = CommercialStrategyVersion(
            tenant_id=self.tenant_id,
            commercial_strategy_id=strategy.id,
            version_number=number,
            version_purpose=purpose,
            status="DRAFT",
            fel_stage_code=fel.current_stage_code if fel else None,
            content_json=content,
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
            content_hash=_hash(content),
            commercial_strategy_hash="",
            preparer_user_id=self.actor_id,
            reviewer_user_id=None,
            create_idempotency_key=idempotency_key,
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        version.commercial_strategy_hash = self._version_hash(version)
        self.db.add(version)
        self.db.flush()
        self._recalculate(strategy, version, persist=True)
        return version

    def _recalculate(
        self,
        strategy: CommercialContractingStrategy,
        version: CommercialStrategyVersion,
        *,
        persist: bool,
    ) -> CommercialStrategyReadinessOut:
        project = self._project(strategy.project_workspace_id)
        configuration, _chain = self._resolve_configuration(project)
        content = deepcopy(version.content_json or {})
        current_refs, current_hashes = self._source_bundle(project.id)
        source_current = current_hashes == dict(version.source_hashes_json or {})
        configuration_current = configuration.content_hash == version.configuration_hash
        effective_policy = self._tailored_policy(project, configuration.content_json, version.fel_stage_code)
        dimensions, warnings, blockers = self._readiness_dimensions(
            project, content, effective_policy, version.fel_stage_code
        )
        if not source_current:
            blockers.append("COMMERCIAL_STRATEGY_SOURCE_STALE")
        if not configuration_current:
            blockers.append("COMMERCIAL_STRATEGY_CONFIGURATION_STALE")
        if not self._is_applicable(project, configuration.content_json):
            dimensions = dict.fromkeys(READINESS_DIMENSIONS, "NOT_APPLICABLE")
            blockers = []
            status = "NOT_APPLICABLE"
        else:
            status = dimensions["OVERALL_COMMERCIAL_READINESS"]
            if not source_current or not configuration_current:
                status = "STALE"
                dimensions["OVERALL_COMMERCIAL_READINESS"] = "STALE"
        calculated_content_hash = _hash(content)
        readiness_hash = _hash(
            {
                "content": calculated_content_hash,
                "configuration": configuration.content_hash,
                "sources": current_hashes,
                "dimensions": dimensions,
                "warnings": sorted(set(warnings)),
                "blockers": sorted(set(blockers)),
            }
        )
        if persist:
            version.readiness_json = {**dimensions, "readiness_hash": readiness_hash}
            version.readiness_status = status
            version.readiness_warnings_json = sorted(set(warnings))
            version.readiness_blockers_json = sorted(set(blockers))
            version.source_current = source_current
            version.content_hash = calculated_content_hash
            version.commercial_strategy_hash = self._version_hash(version)
        return CommercialStrategyReadinessOut(
            commercial_strategy_id=strategy.id,
            version_id=version.id,
            dimensions=dimensions,
            status=status,
            overall_commercial_readiness=status,
            warnings=sorted(set(warnings)),
            blockers=sorted(set(blockers)),
            source_current=source_current,
            configuration_current=configuration_current,
            commercial_strategy_hash=version.commercial_strategy_hash,
            source_bundle_hash=version.source_bundle_hash,
            configuration_hash=version.configuration_hash,
            can_supply_investment_gate_evidence=bool(
                version.status == "COMPLETED"
                and status == "READY"
                and source_current
                and configuration_current
                and not blockers
            ),
            persisted=bool(persist and version.status == "COMPLETED"),
        )

    def _readiness_dimensions(
        self,
        project: EnterpriseWorkspace,
        content: dict[str, Any],
        policy: dict[str, Any],
        version_fel_stage: str | None,
    ) -> tuple[dict[str, str], list[str], list[str]]:
        blockers: list[str] = []
        warnings: list[str] = []
        dimensions: dict[str, str] = {}

        def required(section: str) -> bool:
            return section in set(policy.get("required_sections", []))

        def readiness_state(*, ready: bool, present: bool, section: str) -> str:
            if ready:
                return "READY"
            if not present and not required(section):
                return "NOT_APPLICABLE"
            return "BLOCKED"

        context_ready = bool(content.get("commercial_context"))
        dimensions["COMMERCIAL_CONTEXT_READINESS"] = readiness_state(
            ready=context_ready,
            present=context_ready,
            section="commercial_context",
        )
        if required("commercial_context") and not context_ready:
            blockers.append("REQUIRED_SECTION_MISSING:commercial_context")

        procurement = self._selected_code(content.get("procurement_approach"))
        procurement_ready = bool(procurement)
        dimensions["PROCUREMENT_APPROACH_READINESS"] = readiness_state(
            ready=procurement_ready,
            present=procurement_ready,
            section="procurement_approach",
        )
        if required("procurement_approach") and not procurement_ready:
            blockers.append("NO_PROCUREMENT_APPROACH_SELECTED")
        if procurement and procurement not in set(policy.get("procurement_approaches", [])):
            blockers.append("PROCUREMENT_APPROACH_NOT_IN_PUBLISHED_CATALOG")
            dimensions["PROCUREMENT_APPROACH_READINESS"] = "BLOCKED"

        packages = list(content.get("packages") or [])
        package_fields = set(dict(policy.get("required_fields") or {}).get("package", []))
        invalid_packages = [
            str(item.get("package_code") or index + 1)
            for index, item in enumerate(packages)
            if not package_fields.issubset({key for key, value in item.items() if value not in (None, "", [])})
        ]
        packaging_ready = bool(packages) and not invalid_packages
        dimensions["PACKAGING_READINESS"] = readiness_state(
            ready=packaging_ready,
            present=bool(packages),
            section="packages",
        )
        if required("packages") and not packages:
            blockers.append("REQUIRED_SECTION_MISSING:packages")
        if invalid_packages:
            blockers.extend(f"PACKAGE_REQUIRED_FIELD_MISSING:{code}" for code in invalid_packages)
        invalid_package_types = [
            str(item.get("package_code") or index + 1)
            for index, item in enumerate(packages)
            if item.get("package_type") and str(item.get("package_type")) not in set(policy.get("package_types", []))
        ]
        if invalid_package_types:
            blockers.extend(f"PACKAGE_TYPE_NOT_IN_PUBLISHED_CATALOG:{code}" for code in invalid_package_types)
            dimensions["PACKAGING_READINESS"] = "BLOCKED"
        invalid_package_procurement = [
            str(item.get("package_code") or index + 1)
            for index, item in enumerate(packages)
            if item.get("anticipated_procurement_approach")
            and str(item.get("anticipated_procurement_approach")) not in set(policy.get("procurement_approaches", []))
        ]
        invalid_package_contracting = [
            str(item.get("package_code") or index + 1)
            for index, item in enumerate(packages)
            if item.get("anticipated_contracting_model")
            and str(item.get("anticipated_contracting_model")) not in set(policy.get("contracting_models", []))
        ]
        if invalid_package_procurement:
            blockers.extend(
                f"PACKAGE_PROCUREMENT_NOT_IN_PUBLISHED_CATALOG:{code}" for code in invalid_package_procurement
            )
            dimensions["PACKAGING_READINESS"] = "BLOCKED"
        if invalid_package_contracting:
            blockers.extend(
                f"PACKAGE_CONTRACTING_NOT_IN_PUBLISHED_CATALOG:{code}" for code in invalid_package_contracting
            )
            dimensions["PACKAGING_READINESS"] = "BLOCKED"

        contracting = self._selected_code(content.get("contracting_model"))
        contracting_ready = bool(contracting)
        dimensions["CONTRACTING_MODEL_READINESS"] = readiness_state(
            ready=contracting_ready,
            present=contracting_ready,
            section="contracting_model",
        )
        if required("contracting_model") and not contracting_ready:
            blockers.append("CONTRACTING_MODEL_MISSING")
        if contracting and contracting not in set(policy.get("contracting_models", [])):
            blockers.append("CONTRACTING_MODEL_NOT_IN_PUBLISHED_CATALOG")
            dimensions["CONTRACTING_MODEL_READINESS"] = "BLOCKED"

        assessment = dict(content.get("market_assessment") or {})
        try:
            score = float(assessment.get("overall_score", 0))
        except (TypeError, ValueError):
            score = 0
        threshold = float(policy.get("market_blocking_threshold", 60))
        market_summary = str(assessment.get("summary") or content.get("market_assessment_summary") or "").strip()
        market_ready = bool(assessment) and (
            score >= threshold or ("overall_score" not in assessment and bool(market_summary))
        )
        dimensions["MARKET_READINESS"] = readiness_state(
            ready=market_ready,
            present=bool(assessment),
            section="market_assessment",
        )
        if required("market_assessment") and not assessment:
            blockers.append("REQUIRED_SECTION_MISSING:market_assessment")
        elif assessment and not market_ready:
            blockers.append("MARKET_CAPABILITY_BELOW_THRESHOLD")

        constraints = list(content.get("supply_chain_constraints") or [])
        unresolved_critical = [
            item
            for item in constraints
            if bool(item.get("critical", item.get("blocking", False)))
            and str(item.get("status", "OPEN")).upper() not in {"RESOLVED", "CLOSED", "MITIGATED"}
        ]
        supply_ready = not unresolved_critical
        dimensions["SUPPLY_CHAIN_READINESS"] = "READY" if supply_ready else "BLOCKED"
        if unresolved_critical:
            blockers.append("CRITICAL_SUPPLY_CHAIN_CONSTRAINT_UNRESOLVED")

        allocations = list(content.get("risk_allocations") or [])
        risk_fields = set(dict(policy.get("required_fields") or {}).get("risk_allocation", []))
        incomplete_allocations = [
            item
            for item in allocations
            if not risk_fields.issubset({key for key, value in item.items() if value not in (None, "", [])})
        ]
        mandatory_unallocated = [
            item
            for item in allocations
            if bool(item.get("mandatory", item.get("high_risk", False))) and not item.get("preferred_owner")
        ]
        risk_ready = bool(allocations) and not incomplete_allocations and not mandatory_unallocated
        dimensions["RISK_ALLOCATION_READINESS"] = readiness_state(
            ready=risk_ready,
            present=bool(allocations),
            section="risk_allocations",
        )
        if required("risk_allocations") and not allocations:
            blockers.append("RISK_ALLOCATION_INCOMPLETE")
        if incomplete_allocations:
            blockers.append("RISK_ALLOCATION_INCOMPLETE")
        if mandatory_unallocated:
            blockers.append("MANDATORY_HIGH_RISK_ITEM_UNALLOCATED")
        invalid_risk_categories = [
            str(item.get("commercial_risk_category") or index + 1)
            for index, item in enumerate(allocations)
            if item.get("commercial_risk_category")
            and str(item.get("commercial_risk_category")) not in set(policy.get("risk_allocation_categories", []))
        ]
        if invalid_risk_categories:
            blockers.extend(f"RISK_CATEGORY_NOT_IN_PUBLISHED_CATALOG:{code}" for code in invalid_risk_categories)
            dimensions["RISK_ALLOCATION_READINESS"] = "BLOCKED"

        payment = self._selected_code(content.get("payment_mechanism"))
        payment_ready = bool(payment)
        dimensions["PAYMENT_MECHANISM_READINESS"] = readiness_state(
            ready=payment_ready,
            present=payment_ready,
            section="payment_mechanism",
        )
        if required("payment_mechanism") and not payment_ready:
            blockers.append("PAYMENT_MECHANISM_MISSING")
        if payment and payment not in set(policy.get("payment_mechanisms", [])):
            blockers.append("PAYMENT_MECHANISM_NOT_IN_PUBLISHED_CATALOG")
            dimensions["PAYMENT_MECHANISM_READINESS"] = "BLOCKED"

        fel_stage = str(
            version_fel_stage
            or content.get("fel_stage_code")
            or dict((project.defaults_json or {}).get("_project", {})).get("fel_stage")
            or "FEL-1"
        )
        alternatives = list(content.get("alternatives") or [])
        alternatives_required = bool(dict(policy.get("alternatives_required_by_fel_stage") or {}).get(fel_stage, False))
        if alternatives_required:
            if len(alternatives) < int(policy.get("minimum_alternatives", 2)):
                blockers.append("REQUIRED_ALTERNATIVES_ABSENT")
            alternative_fields = set(dict(policy.get("required_fields") or {}).get("alternative", []))
            if any(
                not alternative_fields.issubset({key for key, value in item.items() if value not in (None, "", [])})
                for item in alternatives
            ):
                blockers.append("REQUIRED_ALTERNATIVE_FIELDS_MISSING")

        recommendation = dict(content.get("recommendation") or {})
        recommendation_fields = set(dict(policy.get("required_fields") or {}).get("recommendation", []))
        recommendation_ready = bool(recommendation) and recommendation_fields.issubset(
            {key for key, value in recommendation.items() if value not in (None, "", [])}
        )
        dimensions["COMMERCIAL_RECOMMENDATION_READINESS"] = readiness_state(
            ready=recommendation_ready,
            present=bool(recommendation),
            section="recommendation",
        )
        if required("recommendation") and not recommendation_ready:
            blockers.append("NO_RECOMMENDED_COMMERCIAL_STRATEGY")
        recommendation_catalogs = {
            "recommended_procurement_approach": set(policy.get("procurement_approaches", [])),
            "recommended_contracting_model": set(policy.get("contracting_models", [])),
            "recommended_payment_mechanism": set(policy.get("payment_mechanisms", [])),
            "recommended_incentive_strategy": set(policy.get("incentive_mechanisms", [])),
        }
        invalid_recommendations = [
            key
            for key, catalog_values in recommendation_catalogs.items()
            if recommendation.get(key) and str(recommendation.get(key)) not in catalog_values
        ]
        if invalid_recommendations:
            blockers.extend(f"RECOMMENDATION_NOT_IN_PUBLISHED_CATALOG:{key}" for key in invalid_recommendations)
            dimensions["COMMERCIAL_RECOMMENDATION_READINESS"] = "BLOCKED"

        open_issues = [
            item
            for item in list(content.get("conditions_open_issues") or [])
            if bool(item.get("blocking", True))
            and str(item.get("status", "OPEN")).upper() not in {"RESOLVED", "CLOSED"}
        ]
        if open_issues:
            blockers.append("BLOCKING_COMMERCIAL_ISSUE_UNRESOLVED")

        required_dimension_keys = [
            "COMMERCIAL_CONTEXT_READINESS",
            "PROCUREMENT_APPROACH_READINESS",
            "PACKAGING_READINESS",
            "CONTRACTING_MODEL_READINESS",
            "MARKET_READINESS",
            "SUPPLY_CHAIN_READINESS",
            "RISK_ALLOCATION_READINESS",
            "PAYMENT_MECHANISM_READINESS",
            "COMMERCIAL_RECOMMENDATION_READINESS",
        ]
        dimensions["OVERALL_COMMERCIAL_READINESS"] = (
            "READY"
            if not blockers and all(dimensions[key] in {"READY", "NOT_APPLICABLE"} for key in required_dimension_keys)
            else "BLOCKED"
        )
        return dimensions, warnings, blockers

    def _source_bundle(self, project_id: int) -> tuple[dict[str, Any], dict[str, str]]:
        project = self._project(project_id)
        references: dict[str, Any] = {
            "project": {
                "id": project.id,
                "version": project.version,
                "status": project.status,
                "project_type": self._project_type(project),
                "governance_model": self._governance(project),
            }
        }
        hashes: dict[str, str] = {
            "project_scope": _hash(
                {
                    "id": project.id,
                    "version": project.version,
                    "status": project.status,
                    "defaults": project.defaults_json,
                }
            )
        }
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
            proposal_hash = str(
                getattr(proposal, "completion_hash", "")
                or getattr(proposal, "readiness_hash", "")
                or getattr(proposal, "updated_at", "")
            )
            references["project_proposal"] = {"id": proposal.id, "status": proposal.status}
            hashes["project_proposal"] = proposal_hash
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
            references["fel"] = {
                "id": fel.id,
                "stage": fel.current_stage_code,
                "readiness": fel.readiness_status,
            }
            hashes["fel"] = _hash(
                {
                    "stage": fel.current_stage_code,
                    "source": fel.definition_source_hash,
                    "framework": fel.effective_framework_hash,
                    "readiness": fel.readiness_status,
                }
            )
        budget = self.db.scalar(
            select(PortfolioBudgetScenarioProject)
            .join(PortfolioBudgetScenario, PortfolioBudgetScenario.id == PortfolioBudgetScenarioProject.scenario_id)
            .where(
                PortfolioBudgetScenarioProject.tenant_id == self.tenant_id,
                PortfolioBudgetScenarioProject.project_workspace_id == project_id,
                PortfolioBudgetScenario.status == "FROZEN",
            )
            .order_by(PortfolioBudgetScenario.frozen_at.desc())
        )
        if budget:
            references["budget"] = {"id": budget.id, "scenario_id": budget.scenario_id}
            hashes["budget"] = budget.row_hash
        funding = self.db.scalar(
            select(FundingReadinessSnapshot)
            .where(
                FundingReadinessSnapshot.tenant_id == self.tenant_id,
                FundingReadinessSnapshot.project_workspace_id == project_id,
            )
            .order_by(FundingReadinessSnapshot.generated_at.desc())
        )
        if funding:
            references["funding"] = {
                "id": funding.id,
                "status": funding.status,
                "source_current": funding.source_current,
                "funding_readiness_hash": funding.funding_readiness_hash,
            }
        financial_model = self.db.scalar(
            select(EconomicFinancialModel).where(
                EconomicFinancialModel.tenant_id == self.tenant_id,
                EconomicFinancialModel.project_workspace_id == project_id,
            )
        )
        if financial_model and financial_model.current_version_id:
            financial_version = self.db.scalar(
                select(EconomicFinancialModelVersion).where(
                    EconomicFinancialModelVersion.tenant_id == self.tenant_id,
                    EconomicFinancialModelVersion.id == financial_model.current_version_id,
                    EconomicFinancialModelVersion.model_id == financial_model.id,
                )
            )
            if financial_version:
                references["economic_financial_model"] = {
                    "id": financial_model.id,
                    "version_id": financial_version.id,
                    "status": financial_version.status,
                    "overall_readiness": financial_version.overall_readiness,
                    "model_hash": financial_version.model_hash,
                }
        risk = self.db.scalar(
            select(RiskReadinessAssessment)
            .where(
                RiskReadinessAssessment.tenant_id == self.tenant_id,
                RiskReadinessAssessment.project_workspace_id == project_id,
                RiskReadinessAssessment.status == "COMPLETED",
            )
            .order_by(RiskReadinessAssessment.completed_at.desc())
        )
        if risk:
            references["risk"] = {"id": risk.id, "readiness": risk.readiness_status}
            hashes["risk"] = str(risk.risk_readiness_hash or risk.risk_register_hash)
        permit = self.db.scalar(
            select(PermitReadinessAssessment)
            .where(
                PermitReadinessAssessment.tenant_id == self.tenant_id,
                PermitReadinessAssessment.project_workspace_id == project_id,
            )
            .order_by(PermitReadinessAssessment.updated_at.desc())
        )
        if permit:
            references["permit"] = {
                "id": permit.id,
                "status": permit.status,
                "readiness": permit.readiness_status,
                "permit_readiness_hash": permit.permit_readiness_hash,
            }
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
        return references, hashes

    def _strategy_out(
        self,
        record: CommercialContractingStrategy,
        *,
        readiness: CommercialStrategyReadinessOut | None = None,
    ) -> CommercialStrategyOut:
        self._assert_scope(record.project_workspace_id)
        project = self._project(record.project_workspace_id)
        version = self._current_version(record, required=False)
        if version is not None and readiness is None:
            readiness = self._recalculate(record, version, persist=False)
        version_out = self._version_out(version, strategy=record, readiness=readiness) if version else None
        release_ready = bool(version and readiness and version.status == "COMPLETED" and readiness.status == "READY")
        return CommercialStrategyOut(
            id=record.id,
            project_workspace_id=record.project_workspace_id,
            project_workspace_name=project.name,
            strategy_number=record.strategy_number,
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
            current_version=version_out,
            allowed_actions=self._allowed_actions(record, version),
            final_output=READY_OUTPUT if release_ready else "COMMERCIAL_STRATEGY_IN_PROGRESS",
            next_process=NEXT_PROCESS if release_ready else "COMPLETE_GOVERNED_COMMERCIAL_STRATEGY",
        )

    def _version_out(
        self,
        version: CommercialStrategyVersion | None,
        *,
        strategy: CommercialContractingStrategy | None = None,
        readiness: CommercialStrategyReadinessOut | None = None,
    ) -> CommercialStrategyVersionOut:
        if version is None:
            raise HTTPException(status_code=404, detail={"code": "COMMERCIAL_STRATEGY_VERSION_NOT_FOUND"})
        strategy = strategy or self._strategy(version.commercial_strategy_id)
        readiness = readiness or self._recalculate(strategy, version, persist=False)
        values = {
            key: getattr(version, key)
            for key in CommercialStrategyVersionOut.model_fields
            if key != "allowed_actions" and hasattr(version, key)
        }
        values["readiness_status"] = readiness.status
        values["overall_commercial_readiness"] = readiness.overall_commercial_readiness
        values["readiness_json"] = {**readiness.dimensions, "readiness_hash": _hash(readiness.model_dump())}
        values["readiness_warnings_json"] = readiness.warnings
        values["readiness_blockers_json"] = readiness.blockers
        values["source_current"] = readiness.source_current
        values["can_supply_investment_gate_evidence"] = readiness.can_supply_investment_gate_evidence
        values["allowed_actions"] = self._allowed_actions(strategy, version)
        return CommercialStrategyVersionOut(**values)

    def _allowed_actions(
        self, strategy: CommercialContractingStrategy, version: CommercialStrategyVersion | None
    ) -> dict[str, bool]:
        roles = set(getattr(self.context, "role_codes", set()) or set())
        admin = "organization_admin" in roles
        author = admin or "commercial_strategy_author" in roles
        reviewer = admin or "commercial_strategy_reviewer" in roles
        status = version.status if version else None
        owned = version is None or version.preparer_user_id == self.actor_id or self._organization_wide()
        sod_ok = True
        review_assignment_ok = True
        if version is not None:
            configuration = self._configuration(version.configuration_id)
            sod_required = bool(
                dict(configuration.content_json.get("separation_of_duties") or {}).get(
                    "reviewer_must_differ_from_preparer", True
                )
            )
            sod_ok = not sod_required or version.preparer_user_id != self.actor_id
            review_assignment_ok = version.reviewer_user_id in {None, self.actor_id} or self._organization_wide()
        return {
            "can_create": author,
            "can_edit": bool(author and owned and status == "DRAFT"),
            "can_submit": bool(author and owned and status == "DRAFT"),
            "can_start_review": bool(reviewer and status == "IN_REVIEW" and sod_ok and review_assignment_ok),
            "can_return": bool(reviewer and status == "IN_REVIEW" and review_assignment_ok),
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
            "can_view_source": True,
            "can_refresh_preview": bool(author and status in {"COMPLETED", "VOIDED"}),
            "can_refresh_apply": bool(author and status in {"COMPLETED", "VOIDED"}),
        }

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
            scope = dict(item.content_json.get("scope") or {})
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
                "project_type": list(item.content_json.get("applicable_project_types", ["*"])),
                "gate_profile": list(item.content_json.get("applicable_gate_profiles", ["*"])),
                "fel_stage": list(item.content_json.get("applicable_fel_stages", ["*"])),
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
            raise HTTPException(status_code=409, detail={"code": "PUBLISHED_COMMERCIAL_CONFIGURATION_REQUIRED"})
        ranked.sort(key=lambda value: (value[0], value[1]))
        chain.sort(key=lambda value: (value["distance"], -value["configuration_revision"]))
        return ranked[0][2], chain

    def _strategy(self, strategy_id: int, *, lock: bool = False) -> CommercialContractingStrategy:
        statement = select(CommercialContractingStrategy).where(
            CommercialContractingStrategy.id == strategy_id,
            CommercialContractingStrategy.tenant_id == self.tenant_id,
        )
        if lock:
            statement = statement.with_for_update()
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "COMMERCIAL_STRATEGY_NOT_FOUND"})
        self._assert_scope(record.project_workspace_id)
        return record

    def _version(self, version_id: int, *, lock: bool = False) -> CommercialStrategyVersion:
        statement = select(CommercialStrategyVersion).where(
            CommercialStrategyVersion.id == version_id,
            CommercialStrategyVersion.tenant_id == self.tenant_id,
        )
        if lock:
            statement = statement.with_for_update()
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "COMMERCIAL_STRATEGY_VERSION_NOT_FOUND"})
        return record

    def _strategy_version(
        self, strategy_id: int, version_id: int, *, lock: bool = False
    ) -> tuple[CommercialContractingStrategy, CommercialStrategyVersion]:
        strategy = self._strategy(strategy_id, lock=lock)
        version = self._version(version_id, lock=lock)
        if version.commercial_strategy_id != strategy.id:
            raise HTTPException(status_code=404, detail={"code": "COMMERCIAL_STRATEGY_VERSION_NOT_FOUND"})
        return strategy, version

    def _current_version(
        self, strategy: CommercialContractingStrategy, *, required: bool = True
    ) -> CommercialStrategyVersion | None:
        record = (
            self.db.scalar(
                select(CommercialStrategyVersion).where(
                    CommercialStrategyVersion.id == strategy.current_version_id,
                    CommercialStrategyVersion.tenant_id == self.tenant_id,
                    CommercialStrategyVersion.commercial_strategy_id == strategy.id,
                )
            )
            if strategy.current_version_id
            else None
        )
        if record is None and required:
            raise HTTPException(status_code=409, detail={"code": "CURRENT_COMMERCIAL_STRATEGY_VERSION_REQUIRED"})
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
            raise HTTPException(status_code=404, detail={"code": "COMMERCIAL_CONFIGURATION_NOT_FOUND"})
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
            raise HTTPException(status_code=409, detail={"code": "PUBLISHED_COMMERCIAL_CONFIGURATION_REQUIRED"})
        return record

    def _ensure_sequence(self) -> None:
        exists = self.db.scalar(
            select(AdminNumberSequence.id).where(
                AdminNumberSequence.tenant_id == self.tenant_id,
                AdminNumberSequence.rule_code == NUMBER_RULE,
                AdminNumberSequence.scope_key == "tenant",
            )
        )
        if exists is None:
            self.db.add(
                AdminNumberSequence(
                    tenant_id=self.tenant_id,
                    rule_code=NUMBER_RULE,
                    scope_key="tenant",
                    next_value=1,
                    version=1,
                )
            )

    def _reserve_number(self, configuration: dict[str, Any]) -> str:
        sequence = self.db.scalar(
            select(AdminNumberSequence)
            .where(
                AdminNumberSequence.tenant_id == self.tenant_id,
                AdminNumberSequence.rule_code == NUMBER_RULE,
                AdminNumberSequence.scope_key == "tenant",
            )
            .with_for_update()
        )
        if sequence is None:
            sequence = AdminNumberSequence(
                tenant_id=self.tenant_id,
                rule_code=NUMBER_RULE,
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
        prefix = str(numbering.get("prefix") or "CCS")
        padding = int(numbering.get("padding") or 6)
        return f"{prefix}-{value:0{padding}d}"

    def _idempotent_version(
        self,
        field: str,
        key: str,
        *,
        strategy_id: int | None = None,
        version_id: int | None = None,
        payload_value: str | None = None,
    ) -> CommercialStrategyVersion | None:
        record = self.db.scalar(
            select(CommercialStrategyVersion).where(
                CommercialStrategyVersion.tenant_id == self.tenant_id,
                getattr(CommercialStrategyVersion, field) == key,
            )
        )
        if record is None:
            return None
        self._strategy(record.commercial_strategy_id)
        if strategy_id is not None and record.commercial_strategy_id != strategy_id:
            self._raise_idempotency_conflict()
        if version_id is not None and record.id != version_id:
            self._raise_idempotency_conflict()
        persisted_payload = {
            "create_idempotency_key": record.version_purpose,
            "return_idempotency_key": record.return_reason,
            "void_idempotency_key": record.void_reason,
        }.get(field)
        if payload_value is not None and persisted_payload != payload_value:
            self._raise_idempotency_conflict()
        return record

    @staticmethod
    def _raise_idempotency_conflict() -> None:
        raise HTTPException(status_code=409, detail={"code": "IDEMPOTENCY_KEY_REUSED"})

    def _touch(self, strategy: CommercialContractingStrategy, version: CommercialStrategyVersion) -> None:
        now = utc_now()
        version.updated_by = self.actor_id
        version.updated_at = now
        version.revision_version += 1
        strategy.updated_by = self.actor_id
        strategy.updated_at = now
        strategy.revision_version += 1

    def _enforce_sod(self, version: CommercialStrategyVersion) -> None:
        configuration = self._configuration(version.configuration_id)
        required = bool(
            dict(configuration.content_json.get("separation_of_duties") or {}).get(
                "reviewer_must_differ_from_preparer", True
            )
        )
        if required and version.preparer_user_id == self.actor_id:
            raise HTTPException(status_code=409, detail={"code": "SEPARATION_OF_DUTIES_REQUIRED"})

    def _version_hash(self, version: CommercialStrategyVersion) -> str:
        return _hash(
            {
                "commercial_strategy_id": version.commercial_strategy_id,
                "version_number": version.version_number,
                "version_purpose": version.version_purpose,
                "fel_stage_code": version.fel_stage_code,
                "content_hash": version.content_hash,
                "configuration_hash": version.configuration_hash,
                "source_bundle_hash": version.source_bundle_hash,
                "readiness": version.readiness_json,
            }
        )

    @staticmethod
    def _validate_content_shape(content: dict[str, Any]) -> None:
        list_fields = {
            "packages",
            "supply_chain_constraints",
            "risk_allocations",
            "commercial_assumptions",
            "commercial_constraints",
            "dependencies",
            "legal_regulatory_considerations",
            "alternatives",
            "conditions_open_issues",
        }
        invalid = sorted(field for field in list_fields if field in content and not isinstance(content[field], list))
        if invalid:
            raise HTTPException(
                status_code=422, detail={"code": "INVALID_COMMERCIAL_CONTENT", "list_fields_required": invalid}
            )

    @staticmethod
    def _configuration_issues(content: dict[str, Any]) -> list[str]:
        issues: list[str] = []
        for catalog in (
            "procurement_approaches",
            "contracting_models",
            "package_types",
            "risk_allocation_categories",
            "payment_mechanisms",
            "incentive_mechanisms",
        ):
            values = content.get(catalog)
            if not isinstance(values, list) or not values or len(values) != len(set(map(str, values))):
                issues.append(f"INVALID_OR_EMPTY_CATALOG:{catalog}")
        required = set(content.get("required_sections", []))
        if not {
            "commercial_context",
            "procurement_approach",
            "contracting_model",
            "risk_allocations",
            "payment_mechanism",
            "recommendation",
        }.issubset(required):
            issues.append("CORE_COMMERCIAL_SECTIONS_REQUIRED")
        applicability = content.get("enabled_by_governance_model")
        if not isinstance(applicability, dict) or "CAPITAL_OWNER" not in applicability:
            issues.append("GOVERNANCE_MODEL_APPLICABILITY_REQUIRED")
        sod = dict(content.get("separation_of_duties") or {})
        if not sod.get("reviewer_must_differ_from_preparer", False):
            issues.append("AUTHOR_REVIEWER_SOD_REQUIRED")
        try:
            threshold = float(content.get("market_blocking_threshold", -1))
        except (TypeError, ValueError):
            threshold = -1
        if threshold < 0 or threshold > 100:
            issues.append("MARKET_THRESHOLD_OUT_OF_RANGE")
        tailoring_rules = content.get("tailoring_rules", [])
        tailoring_keys = {
            "project_size",
            "project_risk",
            "project_complexity",
            "project_type",
            "governance_model",
            "gate_profile",
            "fel_stage",
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
        project: EnterpriseWorkspace,
        configuration: dict[str, Any],
        fel_stage_code: str | None,
    ) -> dict[str, Any]:
        effective = deepcopy(configuration or {})
        metadata = dict((project.defaults_json or {}).get("_project", {}))
        actual = {
            "project_size": str(metadata.get("project_size") or metadata.get("size_class") or ""),
            "project_risk": str(metadata.get("project_risk") or metadata.get("risk_class") or ""),
            "project_complexity": str(metadata.get("project_complexity") or metadata.get("complexity_class") or ""),
            "project_type": self._project_type(project),
            "governance_model": self._governance(project),
            "gate_profile": str(metadata.get("gate_profile") or ""),
            "fel_stage": str(fel_stage_code or metadata.get("fel_stage") or "FEL-1"),
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
    def _selected_code(value: Any) -> str | None:
        if isinstance(value, str):
            return value.strip() or None
        if isinstance(value, dict):
            result = value.get("code") or value.get("value") or value.get("id")
            return str(result).strip() if result else None
        return None

    @staticmethod
    def _validate_purpose(value: str, *, allow_initial: bool) -> None:
        if value not in VERSION_PURPOSES or (not allow_initial and value == "INITIAL_COMMERCIAL_ASSESSMENT"):
            raise HTTPException(status_code=422, detail={"code": "INVALID_COMMERCIAL_VERSION_PURPOSE"})

    def _assert_scope(self, workspace_id: int) -> None:
        if self.context is None or self.context.organization_wide:
            return
        if workspace_id not in self.context.workspace_ids:
            raise HTTPException(status_code=404, detail={"code": "COMMERCIAL_STRATEGY_NOT_FOUND"})

    def _organization_wide(self) -> bool:
        return bool(self.context is None or self.context.organization_wide)

    def _configuration_in_authorized_scope(self, record: AdminConfiguration) -> bool:
        if self.context is None or self.context.organization_wide:
            return True
        workspace_id = dict((record.content_json or {}).get("scope") or {}).get("workspace_id")
        return workspace_id is not None and int(workspace_id) in self.context.workspace_ids

    def _assert_configuration_admin_scope(self, record: AdminConfiguration) -> None:
        if not self._configuration_in_authorized_scope(record):
            raise HTTPException(status_code=404, detail={"code": "COMMERCIAL_CONFIGURATION_NOT_FOUND"})

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
            raise HTTPException(status_code=422, detail={"code": "INVALID_COMMERCIAL_STRATEGY_CURSOR"}) from exc

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

    def _configuration_event(
        self,
        event_type: str,
        record: AdminConfiguration | None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._event(
            event_type,
            "AdminConfiguration",
            record.id if record else None,
            {
                "kind": CONFIGURATION_KIND,
                "code": record.code if record else "default",
                "revision": record.revision if record else 1,
                **(metadata or {}),
            },
        )
