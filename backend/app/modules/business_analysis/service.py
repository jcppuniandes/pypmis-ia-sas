"""Application service for governed Business Analysis and Options Analysis."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import math
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domain.models import AdminConfiguration, AdminNumberSequence, EnterpriseWorkspace, SecurityEvent
from app.modules.business_analysis.models import BusinessAnalysis, BusinessAnalysisRevision
from app.modules.business_analysis.schemas import (
    BusinessAnalysisConfigurationPreviewOut,
    BusinessAnalysisHistoryOut,
    BusinessAnalysisOptionsOut,
    BusinessAnalysisOut,
    BusinessAnalysisPayload,
    BusinessAnalysisReadinessOut,
)
from app.modules.enterprise_structure.models import EnterpriseStrategicObjective
from app.modules.enterprise_structure.permissions import EnterprisePermissionContext, ensure_enterprise_permissions
from app.modules.idea_demand.models import Idea, IdeaEvaluation

CONFIGURATION_KIND = "business_analysis_configuration"
DEFAULT_CODE = "default"
NUMBER_RULE = "business-analysis"
ACTIVE_STATES = frozenset({"DRAFT", "SUBMITTED", "IN_REVIEW", "RETURNED"})
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100
PRIVILEGED_ROLES = frozenset(
    {"organization_admin", "business_analysis_author", "business_analysis_reviewer", "business_analysis_viewer"}
)

DEFAULT_BUSINESS_ANALYSIS_CONFIGURATION: dict[str, Any] = {
    "workspace_id": None,
    "inherit_to_descendants": True,
    "business_analysis_required_by_governance_model": {
        "CAPITAL_OWNER": True,
        "CONTRACTOR_DELIVERY": False,
        "DIRECT_INTERNAL": False,
        "LEGACY_UNCLASSIFIED": False,
    },
    "analysis_types": [
        {"code": "NEED", "label": "Need"},
        {"code": "PROBLEM", "label": "Problem"},
        {"code": "OPPORTUNITY", "label": "Opportunity"},
    ],
    "business_drivers": [
        {"code": "strategic_growth", "label": "Strategic growth"},
        {"code": "capacity_shortage", "label": "Capacity shortage"},
        {"code": "regulatory_requirement", "label": "Regulatory requirement"},
        {"code": "cost_reduction", "label": "Cost reduction"},
        {"code": "risk_reduction", "label": "Risk reduction"},
        {"code": "reliability", "label": "Reliability"},
        {"code": "safety", "label": "Safety"},
        {"code": "market_opportunity", "label": "Market opportunity"},
        {"code": "asset_replacement", "label": "Asset replacement"},
        {"code": "transformation", "label": "Technology and transformation"},
        {"code": "other", "label": "Other"},
    ],
    "stakeholder_categories": [
        {"code": "SPONSOR", "label": "Sponsor"},
        {"code": "USER", "label": "User or beneficiary"},
        {"code": "REGULATOR", "label": "Regulator"},
        {"code": "DELIVERY", "label": "Delivery organization"},
        {"code": "COMMUNITY", "label": "Community"},
    ],
    "stakeholder_scales": {
        "interest": ["LOW", "MEDIUM", "HIGH"],
        "influence": ["LOW", "MEDIUM", "HIGH"],
        "impact": ["LOW", "MEDIUM", "HIGH"],
    },
    "value_dimensions": [
        {"code": "financial_value", "label": "Financial value"},
        {"code": "cost_avoidance", "label": "Cost avoidance"},
        {"code": "service_level", "label": "Service level"},
        {"code": "capacity", "label": "Capacity"},
        {"code": "risk_reduction", "label": "Risk reduction"},
        {"code": "compliance", "label": "Compliance"},
        {"code": "safety", "label": "Safety"},
        {"code": "reliability", "label": "Reliability"},
        {"code": "social_value", "label": "Social or public value"},
        {"code": "strategic_value", "label": "Strategic value"},
    ],
    "option_types": [
        {"code": "DO_NOTHING", "label": "Do nothing"},
        {"code": "DO_MINIMUM", "label": "Do minimum"},
        {"code": "ENHANCE_EXISTING", "label": "Enhance existing"},
        {"code": "NEW_CAPABILITY", "label": "New capability"},
        {"code": "OUTSOURCE", "label": "Outsource"},
        {"code": "PARTNER_JV", "label": "Partner or joint venture"},
        {"code": "OTHER", "label": "Other"},
    ],
    "required_option_rules": {"minimum_options": 2, "required_option_types": ["DO_NOTHING"]},
    "evaluation_matrix": {
        "scale": {"min": 1, "max": 5, "allowed_values": [1, 2, 3, 4, 5]},
        "criteria": [
            {"code": "strategic_fit", "label": "Strategic fit", "weight": 20},
            {"code": "expected_value", "label": "Expected value", "weight": 15},
            {"code": "technical_feasibility", "label": "Technical feasibility", "weight": 10},
            {"code": "commercial_feasibility", "label": "Commercial feasibility", "weight": 10},
            {"code": "preliminary_affordability", "label": "Preliminary affordability", "weight": 10},
            {"code": "schedule", "label": "Schedule and timing", "weight": 10},
            {"code": "risk", "label": "Risk", "weight": 10},
            {"code": "organizational_capacity", "label": "Organizational capacity", "weight": 5},
            {"code": "regulatory_complexity", "label": "Regulatory and permit complexity", "weight": 5},
            {"code": "resource_demand", "label": "Resource demand", "weight": 5},
        ],
    },
    "required_fields": [
        "analysis_type",
        "statement",
        "business_drivers",
        "strategic_alignment",
        "stakeholders",
        "current_state",
        "desired_outcomes",
        "expected_value",
        "assumptions",
        "constraints",
        "business_requirements",
        "options",
        "recommended_option_id",
        "recommendation_rationale",
    ],
    "readiness_checklist": [
        "SOURCE_IDEA_CURRENT",
        "NEED_OPPORTUNITY_COMPLETE",
        "STRATEGIC_ALIGNMENT_PRESENT",
        "STAKEHOLDERS_ANALYZED",
        "EXPECTED_OUTCOMES_VALUE_DEFINED",
        "MINIMUM_OPTIONS_AVAILABLE",
        "OPTIONS_EVALUATED_CURRENT_MATRIX",
        "RECOMMENDED_OPTION_SELECTED",
        "ASSUMPTIONS_CONSTRAINTS_CAPTURED",
        "BLOCKERS_RESOLVED_OR_ACCEPTED",
    ],
    "proposal_mapping": {
        "business_need": "statement",
        "business_justification": "recommendation_rationale",
        "preliminary_scope": "recommended_option.scope_concept",
        "expected_benefits": "recommended_option.expected_benefits|desired_outcomes",
        "strategic_objectives": "strategic_alignment",
        "key_risks": "recommended_option.major_risks",
        "assumptions": "assumptions",
        "constraints": "constraints",
    },
    "numbering": {"prefix": "BA", "padding": 5},
    "sod_policy": {"author_may_final_review": False},
}


def ensure_business_analysis_seed_records(db: Session, tenant_id: int, actor_id: int) -> None:
    """Insert BA defaults idempotently using database uniqueness as the concurrency boundary."""
    configuration_values = {
        "tenant_id": tenant_id,
        "kind": CONFIGURATION_KIND,
        "code": DEFAULT_CODE,
        "name": "Default Business Analysis and Options",
        "description": "Gate 07A-BA governed default",
        "status": "published",
        "revision": 1,
        "version": 1,
        "content_json": DEFAULT_BUSINESS_ANALYSIS_CONFIGURATION,
        "content_hash": BusinessAnalysisService._hash(DEFAULT_BUSINESS_ANALYSIS_CONFIGURATION),
        "published_at": utc_now(),
        "created_by_user_id": actor_id,
    }
    sequence_values = {
        "tenant_id": tenant_id,
        "rule_code": NUMBER_RULE,
        "scope_key": "tenant",
        "next_value": 1,
        "version": 1,
    }
    dialect_name = db.get_bind().dialect.name
    if dialect_name == "postgresql":
        configuration_insert = postgresql_insert(AdminConfiguration).values(**configuration_values)
        sequence_insert = postgresql_insert(AdminNumberSequence).values(**sequence_values)
    elif dialect_name == "sqlite":
        configuration_insert = sqlite_insert(AdminConfiguration).values(**configuration_values)
        sequence_insert = sqlite_insert(AdminNumberSequence).values(**sequence_values)
    else:  # pragma: no cover - supported production/test dialects use native upsert above
        if (
            db.scalar(
                select(AdminConfiguration.id).where(
                    AdminConfiguration.tenant_id == tenant_id,
                    AdminConfiguration.kind == CONFIGURATION_KIND,
                    AdminConfiguration.code == DEFAULT_CODE,
                    AdminConfiguration.revision == 1,
                )
            )
            is None
        ):
            db.add(AdminConfiguration(**configuration_values))
        if (
            db.scalar(
                select(AdminNumberSequence.id).where(
                    AdminNumberSequence.tenant_id == tenant_id,
                    AdminNumberSequence.rule_code == NUMBER_RULE,
                    AdminNumberSequence.scope_key == "tenant",
                )
            )
            is None
        ):
            db.add(AdminNumberSequence(**sequence_values))
        return

    db.execute(configuration_insert.on_conflict_do_nothing(index_elements=["tenant_id", "kind", "code", "revision"]))
    db.execute(sequence_insert.on_conflict_do_nothing(index_elements=["tenant_id", "rule_code", "scope_key"]))


class BusinessAnalysisService:
    def __init__(self, db: Session, tenant_id: int, actor_id: int, context: EnterprisePermissionContext) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.actor_id = actor_id
        self.context = context

    def ensure_seed(self) -> None:
        ensure_enterprise_permissions(self.db, self.tenant_id, self.actor_id)
        ensure_business_analysis_seed_records(self.db, self.tenant_id, self.actor_id)
        self.db.commit()

    def options(self) -> BusinessAnalysisOptionsOut:
        eligible: list[dict] = []
        for idea in self.db.scalars(
            select(Idea)
            .where(Idea.tenant_id == self.tenant_id, Idea.state == "ACCEPTED")
            .order_by(Idea.updated_at.desc())
        ).all():
            if not self._can_access(idea.owning_workspace_id, idea.requestor_user_id, idea.owner_user_id):
                continue
            blockers = self._idea_eligibility_blockers(idea)
            current = self._current_for_idea(idea.id)
            eligible.append(
                {
                    "id": idea.id,
                    "idea_number": idea.idea_number,
                    "title": idea.title,
                    "owning_workspace_id": idea.owning_workspace_id,
                    "can_start": not blockers and current is None,
                    "blockers": blockers + (["ACTIVE_ANALYSIS_EXISTS"] if current is not None else []),
                    "governance_model": self.governance_model(idea),
                    "business_analysis_required": self.requirement_for_idea(idea),
                }
            )
        config, _record, _path = self._effective_configuration(None)
        return BusinessAnalysisOptionsOut(
            number_preview=self._number_preview(),
            eligible_ideas=eligible,
            analysis_types=list(config.get("analysis_types", [])),
            business_drivers=list(config.get("business_drivers", [])),
            strategic_objectives=self._objectives(),
            option_types=list(config.get("option_types", [])),
            evaluation_criteria=list(config.get("evaluation_matrix", {}).get("criteria", [])),
            evaluation_scale=dict(config.get("evaluation_matrix", {}).get("scale") or {}),
            stakeholder_categories=list(config.get("stakeholder_categories", [])),
            value_dimensions=list(config.get("value_dimensions", [])),
        )

    def create(self, source_idea_id: int, idempotency_key: str) -> BusinessAnalysisOut:
        normalized_key = idempotency_key.strip()
        if not normalized_key:
            raise HTTPException(status_code=400, detail={"reason": "IDEMPOTENCY_KEY_REQUIRED"})
        duplicate = self.db.scalar(
            select(BusinessAnalysis).where(
                BusinessAnalysis.tenant_id == self.tenant_id,
                BusinessAnalysis.idempotency_key == normalized_key,
            )
        )
        if duplicate is not None:
            if duplicate.source_idea_id != source_idea_id:
                raise HTTPException(status_code=409, detail={"reason": "IDEMPOTENCY_KEY_REUSED"})
            return self._out(duplicate)
        idea = self._idea(source_idea_id, for_update=True)
        blockers = self._idea_eligibility_blockers(idea)
        if blockers:
            raise HTTPException(status_code=409, detail={"reason": "IDEA_NOT_ELIGIBLE", "blockers": blockers})
        existing = self._current_for_idea(idea.id)
        if existing is not None:
            raise HTTPException(
                status_code=409, detail={"reason": "ACTIVE_OR_CURRENT_ANALYSIS_EXISTS", "id": existing.id}
            )
        workspace = self._workspace(idea.owning_workspace_id)
        config, record, _path = self._effective_configuration(workspace)
        evaluation = self._accepted_evaluation(idea)
        content = self._initial_content(idea, config)
        analysis = BusinessAnalysis(
            tenant_id=self.tenant_id,
            analysis_number=self._reserve_number(config),
            source_idea_id=idea.id,
            source_idea_evaluation_id=evaluation.id,
            owning_workspace_id=workspace.id,
            supersedes_analysis_id=None,
            status="DRAFT",
            title=f"Business Analysis for {idea.title}",
            content_json=content,
            recommended_option_id=None,
            readiness_json={},
            source_idea_hash=self.idea_hash(idea, evaluation),
            configuration_id=record.id,
            configuration_revision=record.revision,
            configuration_hash=record.content_hash or self._hash(record.content_json),
            review_json={},
            completion_hash="",
            idempotency_key=normalized_key,
            revision_version=1,
            created_by_user_id=self.actor_id,
            updated_by_user_id=self.actor_id,
        )
        self.db.add(analysis)
        self.db.flush()
        self._snapshot(analysis)
        self._event("business_analysis.created", analysis, None, "DRAFT", {"source_idea_id": idea.id})
        self.db.commit()
        self.db.refresh(analysis)
        return self._out(analysis)

    def list(
        self,
        *,
        queue: str = "",
        search: str = "",
        owning_workspace_id: int | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        cursor: str | None = None,
    ) -> list[BusinessAnalysisOut]:
        items, _next_cursor = self.list_page(
            queue=queue,
            search=search,
            owning_workspace_id=owning_workspace_id,
            limit=limit,
            cursor=cursor,
        )
        return items

    def list_page(
        self,
        *,
        queue: str = "",
        search: str = "",
        owning_workspace_id: int | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
        cursor: str | None = None,
    ) -> tuple[list[BusinessAnalysisOut], str | None]:
        if limit < 1 or limit > MAX_PAGE_SIZE:
            raise HTTPException(
                status_code=422,
                detail={"reason": "INVALID_PAGE_SIZE", "minimum": 1, "maximum": MAX_PAGE_SIZE},
            )
        statement = select(BusinessAnalysis).where(BusinessAnalysis.tenant_id == self.tenant_id)
        if not self.context.organization_wide:
            allowed = list(self.context.workspace_ids)
            statement = statement.where(
                (BusinessAnalysis.created_by_user_id == self.actor_id)
                | (BusinessAnalysis.reviewer_user_id == self.actor_id)
                | (BusinessAnalysis.owning_workspace_id.in_(allowed) if allowed else False)
            )
        elif not (self.context.role_codes & PRIVILEGED_ROLES):
            statement = statement.where(BusinessAnalysis.created_by_user_id == self.actor_id)
        queues = {
            "mine": BusinessAnalysis.created_by_user_id == self.actor_id,
            "draft": BusinessAnalysis.status == "DRAFT",
            "submitted": BusinessAnalysis.status == "SUBMITTED",
            "review": BusinessAnalysis.status == "IN_REVIEW",
            "returned": BusinessAnalysis.status == "RETURNED",
            "ready": BusinessAnalysis.status == "COMPLETED",
            "completed": BusinessAnalysis.status == "COMPLETED",
        }
        if queue in queues:
            statement = statement.where(queues[queue])
        if owning_workspace_id:
            statement = statement.where(BusinessAnalysis.owning_workspace_id == owning_workspace_id)
        if search.strip():
            term = f"%{search.strip().lower()}%"
            statement = statement.where(
                func.lower(BusinessAnalysis.analysis_number).like(term) | func.lower(BusinessAnalysis.title).like(term)
            )
        if cursor:
            cursor_timestamp, cursor_id = self._decode_cursor(cursor)
            statement = statement.where(
                or_(
                    BusinessAnalysis.updated_at < cursor_timestamp,
                    and_(BusinessAnalysis.updated_at == cursor_timestamp, BusinessAnalysis.id < cursor_id),
                )
            )
        rows = list(
            self.db.scalars(
                statement.order_by(BusinessAnalysis.updated_at.desc(), BusinessAnalysis.id.desc()).limit(limit + 1)
            ).all()
        )
        has_more = len(rows) > limit
        page_rows = rows[:limit]
        next_cursor = self._encode_cursor(page_rows[-1]) if has_more and page_rows else None
        return [self._out(item) for item in page_rows], next_cursor

    def list_for_idea_page(
        self,
        idea_id: int,
        *,
        limit: int = DEFAULT_PAGE_SIZE,
        cursor: str | None = None,
    ) -> tuple[list[BusinessAnalysisOut], str | None]:
        self._idea(idea_id)
        if limit < 1 or limit > MAX_PAGE_SIZE:
            raise HTTPException(
                status_code=422,
                detail={"reason": "INVALID_PAGE_SIZE", "minimum": 1, "maximum": MAX_PAGE_SIZE},
            )
        statement = select(BusinessAnalysis).where(
            BusinessAnalysis.tenant_id == self.tenant_id,
            BusinessAnalysis.source_idea_id == idea_id,
        )
        if cursor:
            cursor_timestamp, cursor_id = self._decode_cursor(cursor)
            statement = statement.where(
                or_(
                    BusinessAnalysis.updated_at < cursor_timestamp,
                    and_(BusinessAnalysis.updated_at == cursor_timestamp, BusinessAnalysis.id < cursor_id),
                )
            )
        rows = list(
            self.db.scalars(
                statement.order_by(BusinessAnalysis.updated_at.desc(), BusinessAnalysis.id.desc()).limit(limit + 1)
            ).all()
        )
        has_more = len(rows) > limit
        page_rows = rows[:limit]
        next_cursor = self._encode_cursor(page_rows[-1]) if has_more and page_rows else None
        return [self._out(item) for item in page_rows], next_cursor

    def get(self, analysis_id: int) -> BusinessAnalysisOut:
        return self._out(self._analysis(analysis_id))

    def update(self, analysis_id: int, payload: BusinessAnalysisPayload, expected_version: int) -> BusinessAnalysisOut:
        analysis = self._analysis(analysis_id)
        self._check_version(analysis, expected_version)
        if analysis.status not in {"DRAFT", "RETURNED"}:
            raise HTTPException(status_code=409, detail="Only DRAFT or RETURNED analyses can be edited")
        if analysis.created_by_user_id != self.actor_id and not self.context.organization_wide:
            raise HTTPException(status_code=403, detail="Only the author can edit this Business Analysis")
        content = payload.model_dump(mode="json")
        before = analysis.status
        analysis.content_json = content
        analysis.recommended_option_id = payload.recommended_option_id
        analysis.status = "DRAFT"
        analysis.review_json = {}
        analysis.readiness_json = self._readiness_data(analysis, content=content)
        self._touch(analysis)
        self._snapshot(analysis)
        self._event("business_analysis.updated", analysis, before, analysis.status)
        return self._commit(analysis)

    def submit(self, analysis_id: int, expected_version: int) -> BusinessAnalysisOut:
        analysis = self._analysis(analysis_id)
        if analysis.status == "SUBMITTED":
            return self._out(analysis)
        self._check_version(analysis, expected_version)
        if analysis.status not in {"DRAFT", "RETURNED"}:
            raise HTTPException(status_code=409, detail="Business Analysis cannot be submitted from its current state")
        readiness = self._readiness_data(analysis)
        if readiness["blockers"]:
            raise HTTPException(status_code=422, detail={"reason": "BUSINESS_ANALYSIS_NOT_READY", **readiness})
        return self._transition(analysis, "SUBMITTED", "business_analysis.submitted", submitted_at=utc_now())

    def start_review(self, analysis_id: int, expected_version: int) -> BusinessAnalysisOut:
        analysis = self._analysis(analysis_id)
        if analysis.status == "IN_REVIEW":
            if analysis.reviewer_user_id != self.actor_id:
                raise HTTPException(status_code=409, detail={"reason": "REVIEW_ALREADY_ASSIGNED"})
            return self._out(analysis)
        self._check_version(analysis, expected_version)
        if analysis.status != "SUBMITTED":
            raise HTTPException(status_code=409, detail="Review requires SUBMITTED state")
        self._enforce_sod(analysis)
        analysis.reviewer_user_id = self.actor_id
        analysis.review_json = {"reviewer_user_id": self.actor_id, "started_at": utc_now().isoformat()}
        return self._transition(
            analysis,
            "IN_REVIEW",
            "business_analysis.review_started",
            review_started_at=utc_now(),
        )

    def return_analysis(self, analysis_id: int, reason: str, expected_version: int) -> BusinessAnalysisOut:
        analysis = self._analysis(analysis_id)
        self._check_version(analysis, expected_version)
        if analysis.status != "IN_REVIEW":
            raise HTTPException(status_code=409, detail="Only an analysis in review can be returned")
        self._require_assigned_reviewer(analysis)
        analysis.review_json = {**dict(analysis.review_json or {}), "return_reason": reason.strip()}
        return self._transition(
            analysis,
            "RETURNED",
            "business_analysis.returned",
            metadata={"reason": reason.strip()},
            returned_at=utc_now(),
        )

    def complete(self, analysis_id: int, expected_version: int) -> BusinessAnalysisOut:
        analysis = self._analysis(analysis_id)
        if analysis.status == "COMPLETED":
            return self._out(analysis)
        self._check_version(analysis, expected_version)
        if analysis.status != "IN_REVIEW":
            raise HTTPException(status_code=409, detail="Completion requires IN_REVIEW state")
        self._enforce_sod(analysis)
        self._require_assigned_reviewer(analysis)
        readiness = self._readiness_data(analysis)
        if readiness["blockers"]:
            raise HTTPException(status_code=422, detail={"reason": "BUSINESS_ANALYSIS_NOT_READY", **readiness})
        analysis.readiness_json = readiness
        analysis.completion_hash = self._hash(
            {
                "content": analysis.content_json,
                "source_idea_hash": analysis.source_idea_hash,
                "configuration_hash": analysis.configuration_hash,
                "reviewer_user_id": self.actor_id,
            }
        )
        analysis.review_json = {**dict(analysis.review_json or {}), "completed_by": self.actor_id}
        self._supersede_predecessor(analysis)
        return self._transition(
            analysis,
            "COMPLETED",
            "business_analysis.completed",
            metadata={"completion_hash": analysis.completion_hash},
            completed_at=utc_now(),
        )

    def void(self, analysis_id: int, reason: str, expected_version: int) -> BusinessAnalysisOut:
        analysis = self._analysis(analysis_id)
        if analysis.status == "VOIDED":
            return self._out(analysis)
        self._check_version(analysis, expected_version)
        if analysis.status not in {"DRAFT", "RETURNED"}:
            raise HTTPException(status_code=409, detail="Only a DRAFT or RETURNED Business Analysis can be voided")
        if analysis.created_by_user_id != self.actor_id and not self.context.organization_wide:
            raise HTTPException(status_code=403, detail="Only the author can void this Business Analysis")
        normalized_reason = reason.strip()
        analysis.review_json = {**dict(analysis.review_json or {}), "void_reason": normalized_reason}
        return self._transition(
            analysis,
            "VOIDED",
            "business_analysis.voided",
            metadata={"reason": normalized_reason},
            voided_at=utc_now(),
        )

    def clone_revision(self, analysis_id: int, idempotency_key: str) -> BusinessAnalysisOut:
        source = self._analysis(analysis_id)
        if source.status != "COMPLETED":
            raise HTTPException(
                status_code=409, detail="Only a completed Business Analysis can start a material revision"
            )
        normalized_key = idempotency_key.strip()
        if not normalized_key:
            raise HTTPException(status_code=400, detail={"reason": "IDEMPOTENCY_KEY_REQUIRED"})
        duplicate = self.db.scalar(
            select(BusinessAnalysis).where(
                BusinessAnalysis.tenant_id == self.tenant_id,
                BusinessAnalysis.idempotency_key == normalized_key,
            )
        )
        if duplicate is not None:
            if duplicate.supersedes_analysis_id != source.id:
                raise HTTPException(status_code=409, detail={"reason": "IDEMPOTENCY_KEY_REUSED"})
            return self._out(duplicate)
        active = self.db.scalar(
            select(BusinessAnalysis.id).where(
                BusinessAnalysis.tenant_id == self.tenant_id,
                BusinessAnalysis.source_idea_id == source.source_idea_id,
                BusinessAnalysis.status.in_(ACTIVE_STATES),
            )
        )
        if active is not None:
            raise HTTPException(status_code=409, detail={"reason": "ACTIVE_ANALYSIS_EXISTS", "id": active})
        idea = self._idea(source.source_idea_id, for_update=True)
        evaluation = self._accepted_evaluation(idea)
        config, record, _path = self._effective_configuration(self._workspace(idea.owning_workspace_id))
        clone = BusinessAnalysis(
            tenant_id=self.tenant_id,
            analysis_number=self._reserve_number(config),
            source_idea_id=idea.id,
            source_idea_evaluation_id=evaluation.id,
            owning_workspace_id=idea.owning_workspace_id,
            supersedes_analysis_id=source.id,
            status="DRAFT",
            title=source.title,
            content_json=dict(source.content_json),
            recommended_option_id=source.recommended_option_id,
            readiness_json={},
            source_idea_hash=self.idea_hash(idea, evaluation),
            configuration_id=record.id,
            configuration_revision=record.revision,
            configuration_hash=record.content_hash or self._hash(record.content_json),
            review_json={},
            completion_hash="",
            idempotency_key=normalized_key,
            revision_version=1,
            created_by_user_id=self.actor_id,
            updated_by_user_id=self.actor_id,
        )
        self.db.add(clone)
        self.db.flush()
        self._snapshot(clone)
        self._event("business_analysis.revision_created", clone, None, "DRAFT", {"supersedes": source.id})
        self.db.commit()
        self.db.refresh(clone)
        return self._out(clone)

    def readiness(self, analysis_id: int) -> BusinessAnalysisReadinessOut:
        return self.readiness_for_record(self._analysis(analysis_id))

    def readiness_for_record(self, analysis: BusinessAnalysis) -> BusinessAnalysisReadinessOut:
        """Evaluate a loaded record for trusted upstream/downstream gate integrations."""
        if analysis.tenant_id != self.tenant_id:
            raise HTTPException(status_code=404, detail="Business Analysis not found")
        data = self._readiness_data(analysis)
        ready = analysis.status == "COMPLETED" and not data["blockers"]
        status = (
            "STALE" if any(item.startswith("STALE_") for item in data["blockers"]) else "READY" if ready else "BLOCKED"
        )
        return BusinessAnalysisReadinessOut(
            business_analysis_id=analysis.id,
            status=status,
            ready=ready,
            output="READY_FOR_PROJECT_PROPOSAL" if ready else None,
            blockers=data["blockers"],
            warnings=data["warnings"],
            source_idea_hash=analysis.source_idea_hash,
            current_source_idea_hash=data["current_source_idea_hash"],
            configuration_hash=analysis.configuration_hash,
            readiness_hash=data["readiness_hash"],
        )

    def history(self, analysis_id: int) -> list[BusinessAnalysisHistoryOut]:
        self._analysis(analysis_id)
        rows = self.db.scalars(
            select(SecurityEvent)
            .where(
                SecurityEvent.tenant_id == self.tenant_id,
                SecurityEvent.target_type == "BusinessAnalysis",
                SecurityEvent.target_id == analysis_id,
            )
            .order_by(SecurityEvent.occurred_at)
        ).all()
        return [
            BusinessAnalysisHistoryOut(
                event_type=item.event_type,
                outcome=item.outcome,
                actor_user_id=item.user_id,
                metadata=item.metadata_json,
                occurred_at=item.occurred_at,
            )
            for item in rows
        ]

    def configurations(self) -> list[AdminConfiguration]:
        return list(
            self.db.scalars(
                select(AdminConfiguration)
                .where(AdminConfiguration.tenant_id == self.tenant_id, AdminConfiguration.kind == CONFIGURATION_KIND)
                .order_by(AdminConfiguration.code, AdminConfiguration.revision.desc())
            ).all()
        )

    def configuration_preview(self, owning_workspace_id: int) -> BusinessAnalysisConfigurationPreviewOut:
        workspace = self._workspace(owning_workspace_id)
        content, record, path = self._effective_configuration(workspace)
        issues = self._configuration_issues(content)
        return BusinessAnalysisConfigurationPreviewOut(
            owning_workspace_id=workspace.id,
            path=[self._workspace_option(item) for item in path],
            effective=content,
            source={
                "configuration_id": record.id,
                "code": record.code,
                "revision": record.revision,
                "hash": record.content_hash,
            },
            validation={"valid": not issues, "issues": issues},
            persisted=False,
        )

    def clone_configuration(
        self,
        configuration_id: int,
        expected_version: int,
        *,
        owning_workspace_id: int | None = None,
    ) -> AdminConfiguration:
        source = self._configuration(configuration_id)
        self._check_configuration_version(source, expected_version)
        if source.status != "published":
            raise HTTPException(
                status_code=409, detail="Only a published Business Analysis configuration can be cloned"
            )
        target_code = source.code
        target_content = dict(source.content_json)
        if owning_workspace_id is not None:
            workspace = self._workspace(owning_workspace_id)
            target_code = f"workspace-{workspace.id}"
            target_content["workspace_id"] = workspace.id
        next_revision = (
            int(
                self.db.scalar(
                    select(func.coalesce(func.max(AdminConfiguration.revision), 0)).where(
                        AdminConfiguration.tenant_id == self.tenant_id,
                        AdminConfiguration.kind == CONFIGURATION_KIND,
                        AdminConfiguration.code == target_code,
                    )
                )
                or 0
            )
            + 1
        )
        clone = AdminConfiguration(
            tenant_id=self.tenant_id,
            kind=CONFIGURATION_KIND,
            code=target_code,
            name=source.name,
            description=source.description,
            status="draft",
            revision=next_revision,
            version=1,
            content_json=target_content,
            content_hash="",
            created_by_user_id=self.actor_id,
        )
        self.db.add(clone)
        self.db.flush()
        self._configuration_event("business_analysis.configuration_cloned", clone, {"source_id": source.id})
        self.db.commit()
        self.db.refresh(clone)
        return clone

    def update_configuration(
        self,
        configuration_id: int,
        expected_version: int,
        *,
        name: str,
        description: str,
        content: dict,
    ) -> AdminConfiguration:
        record = self._configuration(configuration_id)
        self._check_configuration_version(record, expected_version)
        if record.status != "draft":
            raise HTTPException(status_code=409, detail="Published Business Analysis configuration is immutable")
        issues = self._configuration_issues(content)
        if issues:
            raise HTTPException(status_code=422, detail={"reason": "INVALID_CONFIGURATION", "issues": issues})
        record.name = name.strip()
        record.description = description.strip()
        record.content_json = content
        record.version += 1
        record.updated_at = utc_now()
        self._configuration_event("business_analysis.configuration_updated", record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def publish_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        record = self._configuration(configuration_id)
        self._check_configuration_version(record, expected_version)
        if record.status != "draft":
            raise HTTPException(status_code=409, detail="Only a DRAFT Business Analysis configuration can be published")
        issues = self._configuration_issues(record.content_json)
        if issues:
            raise HTTPException(status_code=422, detail={"reason": "INVALID_CONFIGURATION", "issues": issues})
        record.status = "published"
        record.content_hash = self._hash(record.content_json)
        record.published_at = utc_now()
        record.version += 1
        record.updated_at = utc_now()
        self._configuration_event("business_analysis.configuration_published", record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def archive_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        record = self._configuration(configuration_id)
        self._check_configuration_version(record, expected_version)
        if record.status != "published":
            raise HTTPException(status_code=409, detail="Only a published configuration can be archived")
        record.status = "archived"
        record.version += 1
        record.updated_at = utc_now()
        self._configuration_event("business_analysis.configuration_archived", record)
        self.db.commit()
        self.db.refresh(record)
        return record

    @staticmethod
    def requirement_for_idea(idea: Idea) -> bool:
        effective = dict((idea.configuration_snapshot_json or {}).get("effective") or {})
        policy = effective.get("business_analysis_required_by_governance_model")
        if not isinstance(policy, dict):
            return False
        workspace_governance = str(effective.get("governance_model") or "CAPITAL_OWNER").upper()
        return bool(policy.get(workspace_governance, policy.get("LEGACY_UNCLASSIFIED", False)))

    def governance_model(self, idea: Idea) -> str:
        effective = dict((idea.configuration_snapshot_json or {}).get("effective") or {})
        snapshotted = str(effective.get("governance_model") or "").upper()
        if snapshotted in {"CAPITAL_OWNER", "CONTRACTOR_DELIVERY", "DIRECT_INTERNAL", "LEGACY_UNCLASSIFIED"}:
            return snapshotted
        workspace = self._workspace(idea.owning_workspace_id)
        configured = str((workspace.defaults_json or {}).get("governance_model") or "").upper()
        if configured in {"CAPITAL_OWNER", "CONTRACTOR_DELIVERY", "DIRECT_INTERNAL"}:
            return configured
        return "LEGACY_UNCLASSIFIED"

    @staticmethod
    def idea_hash(idea: Idea, evaluation: IdeaEvaluation | None) -> str:
        payload = {
            "idea_id": idea.id,
            "revision_version": idea.revision_version,
            "state": idea.state,
            "accepted_evaluation_id": idea.accepted_evaluation_id,
            "evaluation_version": evaluation.evaluation_version if evaluation else None,
            "evaluation_score": str(evaluation.total_score) if evaluation else None,
            "owning_workspace_id": idea.owning_workspace_id,
            "strategic_objective_codes": sorted(idea.strategic_objective_codes or []),
        }
        return BusinessAnalysisService._hash(payload)

    def current_completed_for_idea(self, idea: Idea) -> BusinessAnalysis | None:
        current = self._current_for_idea(idea.id)
        if current is None or current.status != "COMPLETED":
            return None
        readiness = self._readiness_data(current)
        return current if not readiness["blockers"] else None

    def _idea_eligibility_blockers(self, idea: Idea) -> list[str]:
        blockers: list[str] = []
        if idea.state != "ACCEPTED":
            blockers.append("IDEA_NOT_ACCEPTED")
        if idea.accepted_evaluation_id is None or self._accepted_evaluation(idea, required=False) is None:
            blockers.append("NO_ACCEPTED_IDEA_EVALUATION")
        if not idea.strategic_objective_codes:
            blockers.append("NO_STRATEGIC_OBJECTIVE")
        return blockers

    def _readiness_data(self, analysis: BusinessAnalysis, *, content: dict | None = None) -> dict:
        data = dict(content or analysis.content_json or {})
        blockers: list[str] = []
        warnings: list[str] = []
        idea = self._idea(analysis.source_idea_id)
        evaluation = self._accepted_evaluation(idea, required=False)
        current_source_hash = self.idea_hash(idea, evaluation)
        if current_source_hash != analysis.source_idea_hash:
            blockers.append("STALE_SOURCE_IDEA")
        config, record, _path = self._effective_configuration(self._workspace(analysis.owning_workspace_id))
        current_config_hash = record.content_hash or self._hash(record.content_json)
        if current_config_hash != analysis.configuration_hash:
            blockers.append("STALE_EVALUATION_MATRIX")
        if not str(data.get("analysis_type") or "").strip() or not str(data.get("statement") or "").strip():
            blockers.append("NEED_OPPORTUNITY_INCOMPLETE")
        if not data.get("business_drivers"):
            blockers.append("BUSINESS_DRIVERS_MISSING")
        if not data.get("strategic_alignment"):
            blockers.append("STRATEGIC_ALIGNMENT_MISSING")
        if not data.get("stakeholders"):
            blockers.append("STAKEHOLDER_ANALYSIS_MISSING")
        if not data.get("current_state"):
            blockers.append("CURRENT_STATE_MISSING")
        if not data.get("desired_outcomes") or not data.get("expected_value"):
            blockers.append("OUTCOMES_OR_VALUE_MISSING")
        if not data.get("assumptions") or not data.get("constraints"):
            blockers.append("ASSUMPTIONS_OR_CONSTRAINTS_MISSING")
        if not data.get("business_requirements"):
            blockers.append("BUSINESS_REQUIREMENTS_MISSING")
        for field_name in config.get("required_fields", []):
            value = data.get(str(field_name))
            if value is None or value == "" or value == [] or value == {}:
                blockers.append(f"REQUIRED_FIELD_MISSING:{field_name}")
        valid_objectives = {item["code"] for item in self._objectives()}
        alignment_codes = {str(item.get("objective_code") or "") for item in data.get("strategic_alignment", [])}
        if alignment_codes - valid_objectives:
            blockers.append("STRATEGIC_ALIGNMENT_INVALID")
        if set(idea.strategic_objective_codes or []) - alignment_codes:
            blockers.append("SOURCE_STRATEGIC_ALIGNMENT_MISSING")
        options = list(data.get("options") or [])
        rules = dict(config.get("required_option_rules") or {})
        minimum = int(rules.get("minimum_options", 1))
        if len(options) < minimum:
            blockers.append("INSUFFICIENT_OPTIONS")
        option_types = {str(item.get("option_type")) for item in options}
        missing_types = set(rules.get("required_option_types", [])) - option_types
        if missing_types:
            blockers.extend(f"REQUIRED_OPTION_TYPE:{item}" for item in sorted(missing_types))
        criteria = {str(item.get("code")) for item in config.get("evaluation_matrix", {}).get("criteria", [])}
        scale = dict(config.get("evaluation_matrix", {}).get("scale") or {})
        minimum_rating = float(scale.get("min", 1))
        maximum_rating = float(scale.get("max", 5))
        configured_allowed_values = scale.get("allowed_values")
        allowed_ratings = (
            [float(value) for value in configured_allowed_values] if isinstance(configured_allowed_values, list) else []
        )
        for option in options:
            evaluation_rows = list(option.get("evaluation", []))
            rating_codes = [str(item.get("criterion_code")) for item in evaluation_rows]
            ratings = set(rating_codes)
            if criteria - ratings:
                blockers.append(f"OPTION_NOT_FULLY_EVALUATED:{option.get('id', 'unknown')}")
            if ratings - criteria:
                blockers.append(f"OPTION_HAS_UNKNOWN_CRITERIA:{option.get('id', 'unknown')}")
            if len(rating_codes) != len(ratings):
                blockers.append(f"OPTION_HAS_DUPLICATE_CRITERIA:{option.get('id', 'unknown')}")
            for row in evaluation_rows:
                try:
                    if isinstance(row.get("rating"), bool):
                        raise ValueError
                    rating = float(row.get("rating"))
                except (TypeError, ValueError):
                    blockers.append(f"OPTION_RATING_INVALID:{option.get('id', 'unknown')}")
                    continue
                if not math.isfinite(rating):
                    blockers.append(f"OPTION_RATING_INVALID:{option.get('id', 'unknown')}")
                elif not minimum_rating <= rating <= maximum_rating:
                    blockers.append(f"OPTION_RATING_OUT_OF_RANGE:{option.get('id', 'unknown')}")
                elif allowed_ratings and not any(
                    math.isclose(rating, allowed, abs_tol=1e-9) for allowed in allowed_ratings
                ):
                    blockers.append(f"OPTION_RATING_NOT_ALLOWED:{option.get('id', 'unknown')}")
        recommended = str(data.get("recommended_option_id") or "")
        if not recommended or recommended not in {str(item.get("id")) for item in options}:
            blockers.append("RECOMMENDED_OPTION_MISSING")
        if not str(data.get("recommendation_rationale") or "").strip():
            blockers.append("RECOMMENDATION_RATIONALE_MISSING")
        unresolved = [
            item
            for item in data.get("unresolved_concerns", [])
            if item.get("blocking", True) and not item.get("accepted", False)
        ]
        if unresolved:
            blockers.append("UNRESOLVED_BLOCKERS")
        if not options:
            warnings.append("NO_ROUGH_COST_OR_TIMELINE_AVAILABLE")
        payload = {
            "analysis_id": analysis.id,
            "content_hash": self._hash(data),
            "blockers": sorted(set(blockers)),
            "warnings": sorted(set(warnings)),
            "current_source_idea_hash": current_source_hash,
            "current_configuration_hash": current_config_hash,
        }
        return {**payload, "readiness_hash": self._hash(payload)}

    def _initial_content(self, idea: Idea, config: dict) -> dict:
        return {
            "analysis_type": str(config.get("analysis_types", [{}])[0].get("code", "NEED")),
            "statement": idea.description,
            "background": "",
            "business_context": "",
            "urgency_timing": "",
            "consequences_no_action": "",
            "business_drivers": [],
            "strategic_alignment": [
                {"objective_code": code, "contribution": "", "strength": None}
                for code in idea.strategic_objective_codes or []
            ],
            "stakeholders": [],
            "current_state": {},
            "desired_outcomes": {"business_outcomes": idea.expected_benefit} if idea.expected_benefit else {},
            "expected_value": [],
            "assumptions": [],
            "constraints": [],
            "business_requirements": [],
            "options": [],
            "recommended_option_id": None,
            "recommendation_rationale": "",
            "key_trade_offs": [],
            "conditions": [],
            "unresolved_concerns": [],
        }

    def _current_for_idea(self, idea_id: int) -> BusinessAnalysis | None:
        return self.db.scalar(
            select(BusinessAnalysis)
            .where(
                BusinessAnalysis.tenant_id == self.tenant_id,
                BusinessAnalysis.source_idea_id == idea_id,
                BusinessAnalysis.status != "VOIDED",
            )
            .order_by(BusinessAnalysis.id.desc())
            .limit(1)
        )

    def _effective_configuration(
        self, workspace: EnterpriseWorkspace | None
    ) -> tuple[dict, AdminConfiguration, list[EnterpriseWorkspace]]:
        selected = self._latest_configuration(DEFAULT_CODE)
        if selected is None:
            raise HTTPException(status_code=409, detail={"reason": "NO_PUBLISHED_BUSINESS_ANALYSIS_CONFIGURATION"})
        path = self._workspace_path(workspace) if workspace else []
        for item in path:
            candidate = self._latest_configuration(f"workspace-{item.id}")
            if candidate is not None and (
                item.id == workspace.id or candidate.content_json.get("inherit_to_descendants", True)
            ):
                selected = candidate
        return dict(selected.content_json), selected, path

    def _latest_configuration(self, code: str) -> AdminConfiguration | None:
        return self.db.scalar(
            select(AdminConfiguration)
            .where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == CONFIGURATION_KIND,
                AdminConfiguration.code == code,
                AdminConfiguration.status == "published",
            )
            .order_by(AdminConfiguration.revision.desc())
            .limit(1)
        )

    def _configuration(self, configuration_id: int) -> AdminConfiguration:
        record = self.db.scalar(
            select(AdminConfiguration).where(
                AdminConfiguration.id == configuration_id,
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == CONFIGURATION_KIND,
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail="Business Analysis configuration not found")
        return record

    @staticmethod
    def _configuration_issues(content: dict) -> list[str]:
        issues: list[str] = []
        for key in (
            "analysis_types",
            "business_drivers",
            "stakeholder_categories",
            "value_dimensions",
            "option_types",
            "required_fields",
            "readiness_checklist",
        ):
            if not isinstance(content.get(key), list) or not content.get(key):
                issues.append(f"{key.upper()}_REQUIRED")
        evaluation_matrix = content.get("evaluation_matrix")
        if not isinstance(evaluation_matrix, dict):
            issues.append("EVALUATION_MATRIX_REQUIRED")
            evaluation_matrix = {}
        criteria = evaluation_matrix.get("criteria", [])
        if not isinstance(criteria, list) or not criteria:
            issues.append("EVALUATION_CRITERIA_REQUIRED")
        else:
            criterion_codes = [str(item.get("code") or "").strip() for item in criteria if isinstance(item, dict)]
            if len(criterion_codes) != len(criteria) or any(not code for code in criterion_codes):
                issues.append("EVALUATION_CRITERION_CODE_REQUIRED")
            if len(criterion_codes) != len(set(criterion_codes)):
                issues.append("EVALUATION_CRITERION_CODES_MUST_BE_UNIQUE")
            weights: list[float] = []
            for item in criteria:
                try:
                    if not isinstance(item, dict) or isinstance(item.get("weight"), bool):
                        raise ValueError
                    weight = float(item.get("weight"))
                    if not math.isfinite(weight) or weight < 0:
                        raise ValueError
                    weights.append(weight)
                except (TypeError, ValueError):
                    issues.append("EVALUATION_WEIGHT_INVALID")
                    break
            if len(weights) == len(criteria) and not math.isclose(sum(weights), 100.0, abs_tol=1e-6):
                issues.append("EVALUATION_WEIGHTS_MUST_TOTAL_100")
        scale = evaluation_matrix.get("scale")
        if not isinstance(scale, dict):
            issues.append("EVALUATION_SCALE_REQUIRED")
        else:
            try:
                if isinstance(scale.get("min"), bool) or isinstance(scale.get("max"), bool):
                    raise ValueError
                minimum_rating = float(scale.get("min"))
                maximum_rating = float(scale.get("max"))
                if (
                    not math.isfinite(minimum_rating)
                    or not math.isfinite(maximum_rating)
                    or minimum_rating >= maximum_rating
                ):
                    raise ValueError
            except (TypeError, ValueError):
                issues.append("EVALUATION_SCALE_RANGE_INVALID")
            else:
                allowed_values = scale.get("allowed_values")
                if allowed_values is not None:
                    if not isinstance(allowed_values, list) or not allowed_values:
                        issues.append("EVALUATION_ALLOWED_VALUES_INVALID")
                    else:
                        normalized_values: list[float] = []
                        for value in allowed_values:
                            try:
                                if isinstance(value, bool):
                                    raise ValueError
                                normalized = float(value)
                                if (
                                    not math.isfinite(normalized)
                                    or normalized < minimum_rating
                                    or normalized > maximum_rating
                                ):
                                    raise ValueError
                                normalized_values.append(normalized)
                            except (TypeError, ValueError):
                                issues.append("EVALUATION_ALLOWED_VALUES_INVALID")
                                break
                        if len(normalized_values) == len(allowed_values) and len(normalized_values) != len(
                            set(normalized_values)
                        ):
                            issues.append("EVALUATION_ALLOWED_VALUES_MUST_BE_UNIQUE")
        rules = content.get("required_option_rules", {})
        try:
            minimum_options = int(rules.get("minimum_options", 0)) if isinstance(rules, dict) else 0
        except (TypeError, ValueError):
            minimum_options = 0
        if minimum_options < 1 or minimum_options > 30:
            issues.append("MINIMUM_OPTIONS_MUST_BE_POSITIVE")
        policy = content.get("business_analysis_required_by_governance_model")
        if (
            not isinstance(policy, dict)
            or "CAPITAL_OWNER" not in policy
            or any(not isinstance(value, bool) for value in policy.values())
        ):
            issues.append("GOVERNANCE_MODEL_POLICY_REQUIRED")
        return list(dict.fromkeys(issues))

    def _enforce_sod(self, analysis: BusinessAnalysis) -> None:
        config = self._configuration(analysis.configuration_id)
        policy = dict(config.content_json.get("sod_policy") or {})
        if not bool(policy.get("author_may_final_review", False)) and analysis.created_by_user_id == self.actor_id:
            raise HTTPException(status_code=409, detail={"reason": "SEPARATION_OF_DUTIES_REQUIRED"})

    def _require_assigned_reviewer(self, analysis: BusinessAnalysis) -> None:
        if analysis.reviewer_user_id != self.actor_id:
            raise HTTPException(status_code=409, detail={"reason": "REVIEW_ASSIGNED_TO_ANOTHER_USER"})

    def _idea(self, idea_id: int, *, for_update: bool = False) -> Idea:
        statement = select(Idea).where(Idea.id == idea_id, Idea.tenant_id == self.tenant_id)
        if for_update:
            statement = statement.with_for_update()
        idea = self.db.scalar(statement)
        if idea is None or not self._can_access(idea.owning_workspace_id, idea.requestor_user_id, idea.owner_user_id):
            raise HTTPException(status_code=404, detail="Idea not found or not authorized")
        return idea

    def _analysis(self, analysis_id: int) -> BusinessAnalysis:
        analysis = self.db.scalar(
            select(BusinessAnalysis).where(
                BusinessAnalysis.id == analysis_id,
                BusinessAnalysis.tenant_id == self.tenant_id,
            )
        )
        if analysis is None or not self._can_access(
            analysis.owning_workspace_id, analysis.created_by_user_id, analysis.reviewer_user_id
        ):
            raise HTTPException(status_code=404, detail="Business Analysis not found or not authorized")
        return analysis

    def _accepted_evaluation(self, idea: Idea, *, required: bool = True) -> IdeaEvaluation | None:
        evaluation = (
            self.db.scalar(
                select(IdeaEvaluation).where(
                    IdeaEvaluation.id == idea.accepted_evaluation_id,
                    IdeaEvaluation.tenant_id == self.tenant_id,
                    IdeaEvaluation.idea_id == idea.id,
                )
            )
            if idea.accepted_evaluation_id
            else None
        )
        if required and evaluation is None:
            raise HTTPException(status_code=409, detail={"reason": "NO_ACCEPTED_IDEA_EVALUATION"})
        return evaluation

    def _workspace(self, workspace_id: int) -> EnterpriseWorkspace:
        workspace = self.db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.id == workspace_id,
                EnterpriseWorkspace.tenant_id == self.tenant_id,
            )
        )
        if workspace is None:
            raise HTTPException(status_code=404, detail="Owning Workspace not found")
        return workspace

    def _workspace_path(self, workspace: EnterpriseWorkspace) -> list[EnterpriseWorkspace]:
        path: list[EnterpriseWorkspace] = []
        cursor: EnterpriseWorkspace | None = workspace
        seen: set[int] = set()
        while cursor is not None and cursor.id not in seen:
            seen.add(cursor.id)
            path.append(cursor)
            cursor = self._workspace(cursor.parent_id) if cursor.parent_id else None
        return list(reversed(path))

    def _can_access(self, workspace_id: int, creator_id: int, reviewer_id: int | None) -> bool:
        return (
            self.context.organization_wide
            or workspace_id in self.context.workspace_ids
            or creator_id == self.actor_id
            or reviewer_id == self.actor_id
        )

    def _objectives(self) -> list[dict]:
        return [
            {"code": item.code, "label": item.name}
            for item in self.db.scalars(
                select(EnterpriseStrategicObjective).where(
                    EnterpriseStrategicObjective.tenant_id == self.tenant_id,
                    EnterpriseStrategicObjective.active.is_(True),
                )
            ).all()
        ]

    def _sequence(self, *, required: bool = True) -> AdminNumberSequence | None:
        record = self.db.scalar(
            select(AdminNumberSequence).where(
                AdminNumberSequence.tenant_id == self.tenant_id,
                AdminNumberSequence.rule_code == NUMBER_RULE,
                AdminNumberSequence.scope_key == "tenant",
            )
        )
        if required and record is None:
            raise HTTPException(status_code=409, detail="Business Analysis numbering is not initialized")
        return record

    def _number_preview(self) -> str:
        sequence = self._sequence()
        config, _record, _path = self._effective_configuration(None)
        numbering = dict(config.get("numbering") or {})
        return f"{numbering.get('prefix', 'BA')}-{sequence.next_value:0{int(numbering.get('padding', 5))}d}"

    def _reserve_number(self, config: dict) -> str:
        value = self.db.execute(
            update(AdminNumberSequence)
            .where(
                AdminNumberSequence.tenant_id == self.tenant_id,
                AdminNumberSequence.rule_code == NUMBER_RULE,
                AdminNumberSequence.scope_key == "tenant",
            )
            .values(
                next_value=AdminNumberSequence.next_value + 1,
                version=AdminNumberSequence.version + 1,
                updated_at=utc_now(),
            )
            .returning(AdminNumberSequence.next_value)
        ).scalar_one()
        numbering = dict(config.get("numbering") or {})
        return f"{numbering.get('prefix', 'BA')}-{int(value) - 1:0{int(numbering.get('padding', 5))}d}"

    def _snapshot(self, analysis: BusinessAnalysis) -> None:
        revision_number = (
            int(
                self.db.scalar(
                    select(func.coalesce(func.max(BusinessAnalysisRevision.revision_number), 0)).where(
                        BusinessAnalysisRevision.tenant_id == self.tenant_id,
                        BusinessAnalysisRevision.business_analysis_id == analysis.id,
                    )
                )
                or 0
            )
            + 1
        )
        snapshot = {
            "status": analysis.status,
            "content": analysis.content_json,
            "readiness": analysis.readiness_json,
            "recommended_option_id": analysis.recommended_option_id,
        }
        self.db.add(
            BusinessAnalysisRevision(
                tenant_id=self.tenant_id,
                business_analysis_id=analysis.id,
                revision_number=revision_number,
                lifecycle_status=analysis.status,
                source_idea_hash=analysis.source_idea_hash,
                configuration_hash=analysis.configuration_hash,
                content_json=dict(analysis.content_json or {}),
                readiness_json=dict(analysis.readiness_json or {}),
                snapshot_hash=self._hash(snapshot),
                actor_user_id=self.actor_id,
            )
        )

    def _supersede_predecessor(self, successor: BusinessAnalysis) -> None:
        if successor.supersedes_analysis_id is None:
            return
        predecessor = self.db.scalar(
            select(BusinessAnalysis).where(
                BusinessAnalysis.id == successor.supersedes_analysis_id,
                BusinessAnalysis.tenant_id == self.tenant_id,
            )
        )
        if predecessor is None:
            raise HTTPException(status_code=409, detail={"reason": "SUPERSEDED_ANALYSIS_NOT_FOUND"})
        if predecessor.status == "SUPERSEDED":
            return
        if predecessor.status != "COMPLETED":
            raise HTTPException(status_code=409, detail={"reason": "PREDECESSOR_NOT_COMPLETED"})
        before = predecessor.status
        predecessor.status = "SUPERSEDED"
        self._touch(predecessor)
        self._snapshot(predecessor)
        self._event(
            "business_analysis.superseded",
            predecessor,
            before,
            "SUPERSEDED",
            {"successor_business_analysis_id": successor.id},
        )

    def _transition(
        self,
        analysis: BusinessAnalysis,
        target: str,
        event_type: str,
        *,
        metadata: dict | None = None,
        **timestamps,
    ) -> BusinessAnalysisOut:
        before = analysis.status
        analysis.status = target
        for key, value in timestamps.items():
            setattr(analysis, key, value)
        self._touch(analysis)
        self._snapshot(analysis)
        self._event(event_type, analysis, before, target, metadata)
        return self._commit(analysis)

    def _touch(self, analysis: BusinessAnalysis) -> None:
        analysis.updated_by_user_id = self.actor_id
        analysis.updated_at = utc_now()

    @staticmethod
    def _check_version(analysis: BusinessAnalysis, expected_version: int) -> None:
        if analysis.revision_version != expected_version:
            raise HTTPException(
                status_code=412,
                detail={
                    "reason": "ETAG_MISMATCH",
                    "current_version": analysis.revision_version,
                    "expected_version": expected_version,
                },
            )

    @staticmethod
    def _check_configuration_version(record: AdminConfiguration, expected_version: int) -> None:
        if record.version != expected_version:
            raise HTTPException(
                status_code=412,
                detail={
                    "reason": "ETAG_MISMATCH",
                    "current_version": record.version,
                    "expected_version": expected_version,
                },
            )

    def _commit(self, analysis: BusinessAnalysis) -> BusinessAnalysisOut:
        self.db.commit()
        self.db.refresh(analysis)
        return self._out(analysis)

    def _event(
        self,
        event_type: str,
        analysis: BusinessAnalysis,
        state_before: str | None,
        state_after: str,
        metadata: dict | None = None,
    ) -> None:
        self.db.add(
            SecurityEvent(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                event_type=event_type,
                outcome="success",
                target_type="BusinessAnalysis",
                target_id=analysis.id,
                metadata_json={"state_before": state_before, "state_after": state_after, **(metadata or {})},
            )
        )

    def _configuration_event(self, event_type: str, record: AdminConfiguration, metadata: dict | None = None) -> None:
        self.db.add(
            SecurityEvent(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                event_type=event_type,
                outcome="success",
                target_type="AdminConfiguration",
                target_id=record.id,
                metadata_json={
                    "kind": record.kind,
                    "code": record.code,
                    "revision": record.revision,
                    **(metadata or {}),
                },
            )
        )

    def _out(self, analysis: BusinessAnalysis) -> BusinessAnalysisOut:
        idea = self._idea(analysis.source_idea_id)
        workspace = self._workspace(analysis.owning_workspace_id)
        return BusinessAnalysisOut(
            id=analysis.id,
            analysis_number=analysis.analysis_number,
            source_idea_id=idea.id,
            source_idea_number=idea.idea_number,
            source_idea_title=idea.title,
            source_idea_evaluation_id=analysis.source_idea_evaluation_id,
            owning_workspace_id=workspace.id,
            owning_workspace_name=workspace.name,
            supersedes_analysis_id=analysis.supersedes_analysis_id,
            status=analysis.status,
            title=analysis.title,
            content=dict(analysis.content_json or {}),
            recommended_option_id=analysis.recommended_option_id,
            readiness=dict(analysis.readiness_json or {}),
            source_idea_hash=analysis.source_idea_hash,
            configuration_id=analysis.configuration_id,
            configuration_revision=analysis.configuration_revision,
            configuration_hash=analysis.configuration_hash,
            review=dict(analysis.review_json or {}),
            completion_hash=analysis.completion_hash,
            revision_version=analysis.revision_version,
            created_by_user_id=analysis.created_by_user_id,
            reviewer_user_id=analysis.reviewer_user_id,
            allowed_actions=self._allowed_actions(analysis),
            created_at=analysis.created_at,
            updated_at=analysis.updated_at,
            submitted_at=analysis.submitted_at,
            review_started_at=analysis.review_started_at,
            completed_at=analysis.completed_at,
        )

    def _allowed_actions(self, analysis: BusinessAnalysis) -> list[str]:
        roles = self.context.role_codes
        organization_admin = "organization_admin" in roles
        author = organization_admin or "business_analysis_author" in roles
        reviewer = organization_admin or "business_analysis_reviewer" in roles
        actions: list[str] = []
        if (
            author
            and analysis.status in {"DRAFT", "RETURNED"}
            and (analysis.created_by_user_id == self.actor_id or self.context.organization_wide)
        ):
            actions += ["edit", "submit", "void"]
        if analysis.status == "SUBMITTED" and reviewer:
            if analysis.created_by_user_id != self.actor_id:
                actions.append("start_review")
        if analysis.status == "IN_REVIEW" and reviewer and analysis.reviewer_user_id == self.actor_id:
            actions += ["return", "complete"]
        if analysis.status == "COMPLETED" and author:
            actions.append("new_revision")
        return actions

    @staticmethod
    def _encode_cursor(analysis: BusinessAnalysis) -> str:
        payload = json.dumps(
            [analysis.updated_at.isoformat(timespec="microseconds"), analysis.id],
            separators=(",", ":"),
        ).encode()
        return base64.urlsafe_b64encode(payload).decode().rstrip("=")

    @staticmethod
    def _decode_cursor(cursor: str) -> tuple[datetime, int]:
        try:
            padding = "=" * (-len(cursor) % 4)
            payload = base64.b64decode((cursor + padding).encode(), altchars=b"-_", validate=True)
            raw_timestamp, raw_id = json.loads(payload)
            timestamp = datetime.fromisoformat(str(raw_timestamp))
            identifier = int(raw_id)
            if timestamp.tzinfo is not None or identifier < 1:
                raise ValueError
        except (binascii.Error, UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError):
            raise HTTPException(status_code=400, detail={"reason": "INVALID_CURSOR"}) from None
        return timestamp, identifier

    @staticmethod
    def _workspace_option(workspace: EnterpriseWorkspace) -> dict:
        return {
            "id": workspace.id,
            "code": workspace.code,
            "record_code": workspace.record_code,
            "name": workspace.name,
            "workspace_type_code": workspace.workspace_type_code,
        }

    @staticmethod
    def _hash(value: object) -> str:
        return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()
