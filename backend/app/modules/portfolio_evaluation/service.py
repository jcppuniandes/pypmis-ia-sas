"""Gate 07E evaluation, contextual ranking and readiness service."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domain.models import AdminConfiguration, EnterpriseWorkspace, SecurityEvent
from app.modules.enterprise_structure.permissions import EnterprisePermissionContext
from app.modules.portfolio_evaluation.models import PortfolioProjectEvaluation
from app.modules.portfolio_evaluation.schemas import (
    ConfigurationPreviewOut,
    EvaluationOut,
    EvaluationQueueItemOut,
    EvaluationUpdateIn,
    PrioritizationItemOut,
    PrioritizationOut,
    PrioritizationPreviewIn,
    PrioritizationReadinessOut,
)
from app.modules.portfolio_planning.models import PortfolioProjectMembership

CONFIGURATION_KIND = "portfolio_evaluation_configuration"
DEFAULT_CODE = "gate07e-default"
READY_STATUS = "READY_FOR_PORTFOLIO_ANALYSIS"
REWORK_STATUS = "GATE07E_REWORK_REQUIRED"

DEFAULT_CONFIGURATION: dict[str, Any] = {
    "scope": {"type": "tenant", "workspace_id": None},
    "inherit_to_descendants": True,
    "applicable_governance_models": ["CAPITAL_OWNER"],
    "eligible_workspace_statuses": ["pending"],
    "scoring_scale": {"minimum": 1, "maximum": 5, "step": 1},
    "criteria": [
        {"code": "strategic_alignment", "label": "Strategic Alignment", "weight": 25, "evidence_required": True},
        {"code": "economic", "label": "Economic", "weight": 20, "evidence_required": True},
        {"code": "benefits", "label": "Benefits", "weight": 15, "evidence_required": True},
        {"code": "risk", "label": "Risk", "weight": 15, "evidence_required": True},
        {"code": "urgency", "label": "Urgency", "weight": 10, "evidence_required": False},
        {"code": "capacity", "label": "Capacity", "weight": 10, "evidence_required": False},
        {"code": "dependencies", "label": "Dependencies", "weight": 5, "evidence_required": False},
    ],
    "ranking_rules": {
        "score": "normalized_score_desc",
        "tie_breakers": [
            "strategic_alignment_desc",
            "risk_asc",
            "planned_finish_asc",
            "project_number_asc",
        ],
        "manual_override": False,
    },
    "required_sources": ["active_portfolio_membership", "planning_entry_snapshot", "planning_entry_hash"],
}


class PortfolioEvaluationService:
    def __init__(
        self,
        db: Session,
        tenant_id: int,
        actor_id: int,
        context: EnterprisePermissionContext | None = None,
    ) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.actor_id = actor_id
        self.context = context

    def ensure_seed(self) -> None:
        existing = self.db.scalar(
            select(AdminConfiguration.id).where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == CONFIGURATION_KIND,
                AdminConfiguration.code == DEFAULT_CODE,
            )
        )
        if existing is None:
            self.db.add(
                AdminConfiguration(
                    tenant_id=self.tenant_id,
                    kind=CONFIGURATION_KIND,
                    code=DEFAULT_CODE,
                    name="Default Portfolio Evaluation Matrix",
                    description="Gate 07E starter matrix. Review and publish explicitly before operational use.",
                    status="draft",
                    revision=1,
                    version=1,
                    content_json=DEFAULT_CONFIGURATION,
                    content_hash=_hash(DEFAULT_CONFIGURATION),
                    created_by_user_id=self.actor_id,
                )
            )
            self._event("portfolio_evaluation.configuration_seeded_as_draft", "AdminConfiguration", None, {})
            self.db.commit()

    # ------------------------------------------------------------------
    # USER MODE evaluation lifecycle
    # ------------------------------------------------------------------
    def evaluation_queue(self, portfolio_id: int, queue: str | None = None) -> list[EvaluationQueueItemOut]:
        portfolio = self._workspace(portfolio_id)
        self._assert_workspace_type(portfolio, "portfolio")
        self._assert_scope(portfolio_id)
        memberships = list(
            self.db.scalars(
                select(PortfolioProjectMembership)
                .where(
                    PortfolioProjectMembership.tenant_id == self.tenant_id,
                    PortfolioProjectMembership.portfolio_workspace_id == portfolio_id,
                    PortfolioProjectMembership.status == "ACTIVE",
                )
                .order_by(PortfolioProjectMembership.project_workspace_id)
            ).all()
        )
        result: list[EvaluationQueueItemOut] = []
        for membership in memberships:
            project = self._workspace(membership.project_workspace_id)
            blockers = self._eligibility_blockers(project, portfolio, membership)
            latest = self._latest_evaluation(portfolio_id, project.id)
            queue_name = self._queue_name(blockers, latest)
            if queue and queue.upper() not in {"ALL", "ALL_AUTHORIZED", queue_name}:
                continue
            result.append(
                EvaluationQueueItemOut(
                    portfolio_workspace_id=portfolio_id,
                    project_workspace_id=project.id,
                    project_number=project.code,
                    project_name=project.name,
                    membership_id=membership.id,
                    queue=queue_name,
                    eligible=not blockers,
                    blocking_issues=blockers,
                    allowed_actions=["read", *(["start"] if not blockers and latest is None else [])],
                    latest_evaluation=self._evaluation_out(latest) if latest else None,
                )
            )
        return result

    def start_evaluation(self, portfolio_id: int, project_id: int, idempotency_key: str) -> EvaluationOut:
        replay = self.db.scalar(
            select(PortfolioProjectEvaluation).where(
                PortfolioProjectEvaluation.tenant_id == self.tenant_id,
                PortfolioProjectEvaluation.start_idempotency_key == idempotency_key,
            )
        )
        if replay is not None:
            if (replay.portfolio_workspace_id, replay.project_workspace_id) != (portfolio_id, project_id):
                raise HTTPException(status_code=409, detail={"code": "IDEMPOTENCY_KEY_REUSED"})
            return self._evaluation_out(replay)
        portfolio, project, membership = self._eligible_context(portfolio_id, project_id)
        record = self._effective_configuration(portfolio, published_only=True)
        if record is None:
            raise HTTPException(status_code=422, detail={"code": "PUBLISHED_EVALUATION_MATRIX_REQUIRED"})
        content = dict(record.content_json or {})
        self._validate_configuration(content)
        latest = self._latest_evaluation(portfolio_id, project_id)
        if latest is not None and latest.status in {"DRAFT", "IN_PROGRESS"}:
            if latest.start_idempotency_key == idempotency_key:
                return self._evaluation_out(latest)
            raise HTTPException(status_code=409, detail={"code": "EVALUATION_ALREADY_IN_PROGRESS", "id": latest.id})
        next_version = (
            int(
                self.db.scalar(
                    select(func.coalesce(func.max(PortfolioProjectEvaluation.evaluation_version), 0)).where(
                        PortfolioProjectEvaluation.tenant_id == self.tenant_id,
                        PortfolioProjectEvaluation.portfolio_workspace_id == portfolio_id,
                        PortfolioProjectEvaluation.project_workspace_id == project_id,
                    )
                )
                or 0
            )
            + 1
        )
        source = self._source_snapshot(project, portfolio, membership, record)
        planning_hash = str(
            dict(project.defaults_json or {}).get("_portfolio_planning", {}).get("planning_entry_hash", "")
        )
        evaluation = PortfolioProjectEvaluation(
            tenant_id=self.tenant_id,
            portfolio_workspace_id=portfolio.id,
            project_workspace_id=project.id,
            portfolio_membership_id=membership.id,
            evaluation_version=next_version,
            status="DRAFT",
            matrix_configuration_id=record.id,
            matrix_revision=record.revision,
            matrix_hash=record.content_hash or _hash(content),
            matrix_snapshot_json=content,
            source_snapshot_json=source,
            source_snapshot_hash=_hash(source),
            planning_entry_hash=planning_hash,
            ratings_json=[],
            score_components_json=[],
            evaluator_user_id=self.actor_id,
            start_idempotency_key=idempotency_key,
        )
        self.db.add(evaluation)
        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            replay = self.db.scalar(
                select(PortfolioProjectEvaluation).where(
                    PortfolioProjectEvaluation.tenant_id == self.tenant_id,
                    PortfolioProjectEvaluation.start_idempotency_key == idempotency_key,
                )
            )
            if replay is not None:
                return self._evaluation_out(replay)
            raise HTTPException(status_code=409, detail={"code": "EVALUATION_START_CONFLICT"}) from exc
        self._event(
            "portfolio_evaluation.started", "PortfolioProjectEvaluation", evaluation.id, self._event_context(evaluation)
        )
        self.db.commit()
        self.db.refresh(evaluation)
        return self._evaluation_out(evaluation)

    def get_evaluation(self, evaluation_id: int) -> EvaluationOut:
        evaluation = self._evaluation(evaluation_id)
        self._assert_scope(evaluation.portfolio_workspace_id, evaluation.project_workspace_id)
        return self._evaluation_out(evaluation)

    def update_evaluation(
        self, evaluation_id: int, expected_version: int, payload: EvaluationUpdateIn
    ) -> EvaluationOut:
        evaluation = self._evaluation(evaluation_id, lock=True)
        self._check_version(evaluation, expected_version)
        if evaluation.status not in {"DRAFT", "IN_PROGRESS"}:
            raise HTTPException(status_code=409, detail={"code": "EVALUATION_IMMUTABLE"})
        self._assert_current_planning_hash(evaluation)
        ratings = [item.model_dump(mode="json") for item in payload.ratings]
        self._validate_ratings(evaluation.matrix_snapshot_json, ratings, complete=False)
        evaluation.ratings_json = ratings
        evaluation.comments = payload.comments.strip()
        evaluation.status = "IN_PROGRESS" if ratings else "DRAFT"
        evaluation.updated_at = utc_now()
        self._event(
            "portfolio_evaluation.updated", "PortfolioProjectEvaluation", evaluation.id, self._event_context(evaluation)
        )
        self.db.commit()
        self.db.refresh(evaluation)
        return self._evaluation_out(evaluation)

    def complete_evaluation(self, evaluation_id: int, expected_version: int, idempotency_key: str) -> EvaluationOut:
        replay = self.db.scalar(
            select(PortfolioProjectEvaluation).where(
                PortfolioProjectEvaluation.tenant_id == self.tenant_id,
                PortfolioProjectEvaluation.complete_idempotency_key == idempotency_key,
            )
        )
        if replay is not None:
            if replay.id != evaluation_id:
                raise HTTPException(status_code=409, detail={"code": "IDEMPOTENCY_KEY_REUSED"})
            return self._evaluation_out(replay)
        evaluation = self._evaluation(evaluation_id, lock=True)
        if evaluation.complete_idempotency_key == idempotency_key:
            return self._evaluation_out(evaluation)
        self._check_version(evaluation, expected_version)
        if evaluation.status not in {"DRAFT", "IN_PROGRESS"}:
            raise HTTPException(status_code=409, detail={"code": "EVALUATION_IMMUTABLE"})
        self._assert_current_planning_hash(evaluation)
        self._validate_ratings(evaluation.matrix_snapshot_json, list(evaluation.ratings_json or []), complete=True)
        score, components, strategic, risk = self._calculate_score(
            evaluation.matrix_snapshot_json, list(evaluation.ratings_json or [])
        )
        evaluation.normalized_score = score
        evaluation.score_components_json = components
        evaluation.strategic_alignment_score = strategic
        evaluation.risk_score = risk
        evaluation.status = "COMPLETED"
        evaluation.complete_idempotency_key = idempotency_key
        evaluation.completed_at = utc_now()
        evaluation.updated_at = evaluation.completed_at
        self._event(
            "portfolio_evaluation.completed",
            "PortfolioProjectEvaluation",
            evaluation.id,
            {**self._event_context(evaluation), "normalized_score": str(score)},
        )
        self.db.commit()
        self.db.refresh(evaluation)
        return self._evaluation_out(evaluation)

    def reevaluate(self, evaluation_id: int, idempotency_key: str) -> EvaluationOut:
        replay = self.db.scalar(
            select(PortfolioProjectEvaluation).where(
                PortfolioProjectEvaluation.tenant_id == self.tenant_id,
                PortfolioProjectEvaluation.reevaluation_idempotency_key == idempotency_key,
            )
        )
        if replay is not None:
            return self._evaluation_out(replay)
        previous = self._evaluation(evaluation_id, lock=True)
        if previous.status not in {"COMPLETED", "SUPERSEDED"}:
            raise HTTPException(status_code=409, detail={"code": "COMPLETED_EVALUATION_REQUIRED"})
        if previous.status == "SUPERSEDED":
            latest = self._latest_evaluation(previous.portfolio_workspace_id, previous.project_workspace_id)
            if latest and latest.evaluation_version > previous.evaluation_version:
                return self._evaluation_out(latest)
        portfolio, project, membership = self._eligible_context(
            previous.portfolio_workspace_id, previous.project_workspace_id
        )
        matrix = self._effective_configuration(portfolio, published_only=True)
        if matrix is None:
            raise HTTPException(status_code=422, detail={"code": "PUBLISHED_EVALUATION_MATRIX_REQUIRED"})
        source = self._source_snapshot(project, portfolio, membership, matrix)
        next_record = PortfolioProjectEvaluation(
            tenant_id=self.tenant_id,
            portfolio_workspace_id=portfolio.id,
            project_workspace_id=project.id,
            portfolio_membership_id=membership.id,
            evaluation_version=previous.evaluation_version + 1,
            status="DRAFT",
            matrix_configuration_id=matrix.id,
            matrix_revision=matrix.revision,
            matrix_hash=matrix.content_hash or _hash(matrix.content_json),
            matrix_snapshot_json=dict(matrix.content_json or {}),
            source_snapshot_json=source,
            source_snapshot_hash=_hash(source),
            planning_entry_hash=str(
                dict(project.defaults_json or {}).get("_portfolio_planning", {}).get("planning_entry_hash", "")
            ),
            ratings_json=[],
            score_components_json=[],
            evaluator_user_id=self.actor_id,
            start_idempotency_key=f"reevaluate-start:{idempotency_key}",
            reevaluation_idempotency_key=idempotency_key,
        )
        if previous.status == "COMPLETED":
            previous.status = "SUPERSEDED"
            previous.updated_at = utc_now()
        self.db.add(next_record)
        self.db.flush()
        self._event(
            "portfolio_evaluation.reevaluation_started",
            "PortfolioProjectEvaluation",
            next_record.id,
            {**self._event_context(next_record), "supersedes_evaluation_id": previous.id},
        )
        self.db.commit()
        self.db.refresh(next_record)
        return self._evaluation_out(next_record)

    # ------------------------------------------------------------------
    # Contextual Portfolio prioritization (derived, never globally stored)
    # ------------------------------------------------------------------
    def prioritization(self, portfolio_id: int) -> PrioritizationOut:
        portfolio = self._workspace(portfolio_id)
        self._assert_workspace_type(portfolio, "portfolio")
        self._assert_scope(portfolio_id)
        rows = self._ranking_rows(portfolio_id)
        items = self._rank(rows)
        matrix = self._effective_configuration(portfolio, published_only=True)
        rules = dict((matrix.content_json if matrix else DEFAULT_CONFIGURATION).get("ranking_rules", {}))
        output_hash = _hash([item.model_dump(mode="json") for item in items])
        self._event(
            "portfolio_prioritization.recomputed",
            "EnterpriseWorkspace",
            portfolio_id,
            {"item_count": len(items), "matrix_hash": output_hash},
        )
        self.db.commit()
        return PrioritizationOut(
            portfolio_workspace_id=portfolio_id,
            generated_at=utc_now(),
            ranking_rules=rules,
            matrix_hash=output_hash,
            items=items,
        )

    def prioritization_preview(self, portfolio_id: int, payload: PrioritizationPreviewIn) -> PrioritizationOut:
        portfolio = self._workspace(portfolio_id)
        project = self._workspace(payload.project_workspace_id)
        self._assert_scope(portfolio_id, project.id)
        rows = [item for item in self._ranking_rows(portfolio_id) if item.project_workspace_id != project.id]
        rows.append(
            _RankingRow(
                portfolio_workspace_id=portfolio_id,
                project_workspace_id=project.id,
                project_number=project.code,
                project_name=project.name,
                evaluation_id=0,
                evaluation_version=0,
                normalized_score=payload.normalized_score,
                strategic_alignment_score=payload.strategic_alignment_score,
                risk_score=payload.risk_score,
                proposal_score=None,
                strategic_objectives=[],
                rom_cost=None,
                evaluation_status="PREVIEW",
                completed_at=utc_now(),
                planned_finish=_planned_finish(project),
            )
        )
        items = self._rank(rows)
        matrix = self._effective_configuration(portfolio, published_only=True)
        rules = dict((matrix.content_json if matrix else DEFAULT_CONFIGURATION).get("ranking_rules", {}))
        return PrioritizationOut(
            portfolio_workspace_id=portfolio_id,
            generated_at=utc_now(),
            ranking_rules=rules,
            matrix_hash=_hash([item.model_dump(mode="json") for item in items]),
            items=items,
        )

    def readiness(self, portfolio_id: int) -> PrioritizationReadinessOut:
        queue = self.evaluation_queue(portfolio_id)
        eligible = [item for item in queue if item.eligible]
        completed = [
            item for item in eligible if item.latest_evaluation and item.latest_evaluation.status == "COMPLETED"
        ]
        in_progress = [
            item
            for item in eligible
            if item.latest_evaluation and item.latest_evaluation.status in {"DRAFT", "IN_PROGRESS"}
        ]
        blocked = [item for item in queue if not item.eligible]
        coverage = (
            (Decimal(len(completed)) * Decimal("100") / Decimal(len(eligible))).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if eligible
            else Decimal("0")
        )
        blockers: list[str] = []
        if not eligible:
            blockers.append("NO_ELIGIBLE_CAPITAL_OWNER_PROJECTS")
        if in_progress:
            blockers.append("PORTFOLIO_EVALUATIONS_INCOMPLETE")
        if len(completed) < len(eligible):
            blockers.append("PORTFOLIO_EVALUATION_COVERAGE_INCOMPLETE")
        if blocked:
            blockers.append("PORTFOLIO_HAS_BLOCKED_PROJECTS")
        can_enter = bool(eligible) and len(completed) == len(eligible) and not in_progress and not blocked
        snapshot = {
            "portfolio_workspace_id": portfolio_id,
            "eligible_project_ids": [item.project_workspace_id for item in eligible],
            "completed_evaluation_ids": [item.latest_evaluation.id for item in completed if item.latest_evaluation],
            "blocked_project_ids": [item.project_workspace_id for item in blocked],
            "blocking_issues": sorted(set(blockers)),
        }
        return PrioritizationReadinessOut(
            portfolio_workspace_id=portfolio_id,
            status="READY" if can_enter else "BLOCKED",
            eligible_project_count=len(eligible),
            completed_evaluation_count=len(completed),
            in_progress_evaluation_count=len(in_progress),
            blocked_project_count=len(blocked),
            coverage_percent=coverage,
            blocking_issues=sorted(set(blockers)),
            readiness_hash=_hash(snapshot),
            can_enter_portfolio_analysis=can_enter,
            final_output=READY_STATUS if can_enter else REWORK_STATUS,
        )

    # ------------------------------------------------------------------
    # ADMIN MODE configuration governance
    # ------------------------------------------------------------------
    def configurations(self) -> list[AdminConfiguration]:
        return list(
            self.db.scalars(
                select(AdminConfiguration)
                .where(
                    AdminConfiguration.tenant_id == self.tenant_id,
                    AdminConfiguration.kind == CONFIGURATION_KIND,
                )
                .order_by(AdminConfiguration.code, AdminConfiguration.revision.desc())
            ).all()
        )

    def configuration_preview(
        self,
        workspace_id: int | None,
        configuration_id: int | None = None,
        content_override: dict | None = None,
    ) -> ConfigurationPreviewOut:
        workspace = self._workspace(workspace_id) if workspace_id else None
        path = self._workspace_path(workspace) if workspace else []
        selected = self._configuration(configuration_id) if configuration_id else None
        if selected is None:
            selected = (
                self._effective_configuration(workspace, published_only=True) if workspace else self._tenant_published()
            )
        if selected is None:
            selected = self.db.scalar(
                select(AdminConfiguration)
                .where(
                    AdminConfiguration.tenant_id == self.tenant_id,
                    AdminConfiguration.kind == CONFIGURATION_KIND,
                )
                .order_by(AdminConfiguration.revision.desc())
            )
        content = (
            dict(content_override)
            if content_override is not None
            else (dict(selected.content_json or {}) if selected else dict(DEFAULT_CONFIGURATION))
        )
        issues = self._configuration_issues(content)
        return ConfigurationPreviewOut(
            workspace_id=workspace_id,
            path=[self._workspace_summary(item) for item in path],
            effective=content,
            source=(
                {
                    "id": selected.id,
                    "code": selected.code,
                    "revision": selected.revision,
                    "status": selected.status,
                    "hash": _hash(content) if content_override is not None else selected.content_hash,
                    "preview": content_override is not None,
                }
                if selected
                else {"id": None, "code": DEFAULT_CODE, "revision": 0, "status": "draft", "hash": _hash(content)}
            ),
            publishable=not issues,
            validation_issues=issues,
        )

    def clone_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        source = self._configuration(configuration_id)
        self._check_configuration_version(source, expected_version)
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
        clone = AdminConfiguration(
            tenant_id=self.tenant_id,
            kind=CONFIGURATION_KIND,
            code=source.code,
            name=source.name,
            description=source.description,
            status="draft",
            revision=revision,
            version=1,
            content_json=dict(source.content_json or {}),
            content_hash=source.content_hash or _hash(source.content_json),
            created_by_user_id=self.actor_id,
        )
        self.db.add(clone)
        self.db.flush()
        self._event(
            "portfolio_evaluation.configuration_cloned", "AdminConfiguration", clone.id, {"source_id": source.id}
        )
        self.db.commit()
        self.db.refresh(clone)
        return clone

    def update_configuration(
        self,
        configuration_id: int,
        expected_version: int,
        name: str,
        description: str,
        content: dict,
    ) -> AdminConfiguration:
        record = self._configuration(configuration_id, lock=True)
        self._check_configuration_version(record, expected_version)
        if record.status != "draft":
            raise HTTPException(status_code=409, detail={"code": "PUBLISHED_CONFIGURATION_IMMUTABLE"})
        self._validate_configuration(content)
        record.name = name.strip()
        record.description = description.strip()
        record.content_json = content
        record.content_hash = _hash(content)
        record.version += 1
        record.updated_at = utc_now()
        self._event("portfolio_evaluation.configuration_updated", "AdminConfiguration", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return record

    def publish_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        record = self._configuration(configuration_id, lock=True)
        self._check_configuration_version(record, expected_version)
        if record.status != "draft":
            raise HTTPException(status_code=409, detail={"code": "PUBLISHED_CONFIGURATION_IMMUTABLE"})
        self._validate_configuration(dict(record.content_json or {}))
        record.status = "published"
        record.content_hash = _hash(record.content_json)
        record.published_at = utc_now()
        record.updated_at = record.published_at
        record.version += 1
        self._event("portfolio_evaluation.configuration_published", "AdminConfiguration", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return record

    # ------------------------------------------------------------------
    # Validation and projections
    # ------------------------------------------------------------------
    def _eligible_context(
        self, portfolio_id: int, project_id: int
    ) -> tuple[EnterpriseWorkspace, EnterpriseWorkspace, PortfolioProjectMembership]:
        portfolio = self._workspace(portfolio_id)
        project = self._workspace(project_id)
        self._assert_scope(portfolio_id, project_id)
        membership = self.db.scalar(
            select(PortfolioProjectMembership).where(
                PortfolioProjectMembership.tenant_id == self.tenant_id,
                PortfolioProjectMembership.portfolio_workspace_id == portfolio_id,
                PortfolioProjectMembership.project_workspace_id == project_id,
                PortfolioProjectMembership.status == "ACTIVE",
            )
        )
        blockers = self._eligibility_blockers(project, portfolio, membership)
        if blockers:
            self._event(
                "portfolio_evaluation.eligibility_blocked",
                "EnterpriseWorkspace",
                project_id,
                {"portfolio_workspace_id": portfolio_id, "blocking_issues": blockers},
            )
            self.db.commit()
            raise HTTPException(status_code=422, detail={"code": "PROJECT_NOT_ELIGIBLE", "blocking_issues": blockers})
        assert membership is not None
        return portfolio, project, membership

    def _eligibility_blockers(
        self,
        project: EnterpriseWorkspace,
        portfolio: EnterpriseWorkspace,
        membership: PortfolioProjectMembership | None,
    ) -> list[str]:
        blockers: list[str] = []
        if project.workspace_type_code != "project":
            blockers.append("WORKSPACE_IS_NOT_PROJECT")
        if portfolio.workspace_type_code != "portfolio":
            blockers.append("WORKSPACE_IS_NOT_PORTFOLIO")
        if project.status.lower() != "pending":
            blockers.append("PROJECT_STATUS_PENDING_REQUIRED")
        if membership is None or membership.status != "ACTIVE":
            blockers.append("ACTIVE_PORTFOLIO_MEMBERSHIP_REQUIRED")
        defaults = dict(project.defaults_json or {})
        project_context = dict(defaults.get("_project", {}))
        governance = str(project_context.get("governance_model") or "")
        if not governance and project_context.get("planning_origin") == "STRATEGIC_GATE":
            governance = "CAPITAL_OWNER"
        if governance != "CAPITAL_OWNER":
            blockers.append(f"GOVERNANCE_MODEL_{governance or 'LEGACY'}_NOT_APPLICABLE")
        planning = dict(defaults.get("_portfolio_planning", {}))
        if planning.get("status") != "READY_FOR_PORTFOLIO_PLANNING":
            blockers.append("READY_FOR_PORTFOLIO_PLANNING_REQUIRED")
        snapshot = planning.get("snapshot")
        planning_hash = str(planning.get("planning_entry_hash") or "")
        if not isinstance(snapshot, dict) or not snapshot:
            blockers.append("PLANNING_ENTRY_SNAPSHOT_REQUIRED")
        if not planning_hash:
            blockers.append("PLANNING_ENTRY_HASH_REQUIRED")
        elif isinstance(snapshot, dict) and _hash(snapshot) != planning_hash:
            blockers.append("PLANNING_ENTRY_HASH_INVALID")
        return sorted(set(blockers))

    def _source_snapshot(
        self,
        project: EnterpriseWorkspace,
        portfolio: EnterpriseWorkspace,
        membership: PortfolioProjectMembership,
        matrix: AdminConfiguration,
    ) -> dict:
        defaults = dict(project.defaults_json or {})
        project_context = dict(defaults.get("_project", {}))
        planning = dict(defaults.get("_portfolio_planning", {}))
        entry = dict(planning.get("snapshot", {}))
        governance = str(project_context.get("governance_model") or "")
        if not governance and project_context.get("planning_origin") == "STRATEGIC_GATE":
            governance = "CAPITAL_OWNER"
        return {
            "project": self._workspace_summary(project),
            "governance_model": governance,
            "project_type": project_context.get("project_type"),
            "portfolio": self._workspace_summary(portfolio),
            "membership": {
                "id": membership.id,
                "status": membership.status,
                "source": membership.membership_source,
                "is_target_portfolio": membership.is_target_portfolio,
            },
            "planning_entry_hash": planning.get("planning_entry_hash"),
            "planning_entry_snapshot": entry,
            "strategic_gate_decision": entry.get("strategic_gate_decision", {}),
            "project_proposal": entry.get("project_proposal", {}),
            "source_idea": entry.get("source_idea", {}),
            "strategic_objectives": entry.get("strategic_objectives", []),
            "proposal_score": entry.get("proposal_score"),
            "rom_cost": entry.get("rom_cost"),
            "target_start": entry.get("target_start"),
            "target_finish": entry.get("target_finish"),
            "expected_benefits": entry.get("expected_benefits"),
            "risk_summary": entry.get("risk_summary", []),
            "matrix": {
                "id": matrix.id,
                "revision": matrix.revision,
                "hash": matrix.content_hash or _hash(matrix.content_json),
            },
        }

    def _assert_current_planning_hash(self, evaluation: PortfolioProjectEvaluation) -> None:
        project = self._workspace(evaluation.project_workspace_id)
        planning = dict(dict(project.defaults_json or {}).get("_portfolio_planning", {}))
        current_hash = str(planning.get("planning_entry_hash") or "")
        if not current_hash or current_hash != evaluation.planning_entry_hash:
            raise HTTPException(
                status_code=412,
                detail={
                    "code": "PLANNING_SNAPSHOT_STALE",
                    "expected": evaluation.planning_entry_hash,
                    "actual": current_hash,
                },
            )

    def _validate_ratings(self, matrix: dict, ratings: list[dict], *, complete: bool) -> None:
        criteria = {str(item.get("code")): item for item in matrix.get("criteria", [])}
        scale = dict(matrix.get("scoring_scale", {}))
        minimum = Decimal(str(scale.get("minimum", 1)))
        maximum = Decimal(str(scale.get("maximum", 5)))
        seen: set[str] = set()
        for rating in ratings:
            code = str(rating.get("criterion_code", ""))
            if code not in criteria:
                raise HTTPException(status_code=422, detail={"code": "UNKNOWN_CRITERION", "criterion": code})
            if code in seen:
                raise HTTPException(status_code=422, detail={"code": "DUPLICATE_CRITERION", "criterion": code})
            seen.add(code)
            value = Decimal(str(rating.get("rating")))
            if value < minimum or value > maximum:
                raise HTTPException(status_code=422, detail={"code": "RATING_OUT_OF_SCALE", "criterion": code})
            if criteria[code].get("evidence_required") and not str(rating.get("evidence", "")).strip():
                raise HTTPException(status_code=422, detail={"code": "EVIDENCE_REQUIRED", "criterion": code})
        if complete and seen != set(criteria):
            raise HTTPException(
                status_code=422,
                detail={"code": "ALL_CRITERIA_REQUIRED", "missing": sorted(set(criteria) - seen)},
            )

    @staticmethod
    def _calculate_score(matrix: dict, ratings: list[dict]) -> tuple[Decimal, list[dict], Decimal, Decimal]:
        by_code = {str(item.get("criterion_code")): item for item in ratings}
        scale = dict(matrix.get("scoring_scale", {}))
        minimum = Decimal(str(scale.get("minimum", 1)))
        maximum = Decimal(str(scale.get("maximum", 5)))
        span = maximum - minimum
        components: list[dict] = []
        total = Decimal("0")
        strategic = Decimal("0")
        risk = Decimal("0")
        for criterion in matrix.get("criteria", []):
            code = str(criterion.get("code"))
            rating = Decimal(str(by_code[code]["rating"]))
            normalized = ((rating - minimum) * Decimal("100") / span) if span else Decimal("100")
            weight = Decimal(str(criterion.get("weight", 0)))
            contribution = normalized * weight / Decimal("100")
            normalized = normalized.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            contribution = contribution.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            total += contribution
            if code == "strategic_alignment":
                strategic = normalized
            if code == "risk":
                risk = rating.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
            components.append(
                {
                    "criterion_code": code,
                    "rating": str(rating),
                    "weight": str(weight),
                    "normalized": str(normalized),
                    "weighted_contribution": str(contribution),
                }
            )
        return (
            total.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP),
            components,
            strategic,
            risk,
        )

    def _ranking_rows(self, portfolio_id: int) -> list[_RankingRow]:
        memberships = list(
            self.db.scalars(
                select(PortfolioProjectMembership).where(
                    PortfolioProjectMembership.tenant_id == self.tenant_id,
                    PortfolioProjectMembership.portfolio_workspace_id == portfolio_id,
                    PortfolioProjectMembership.status == "ACTIVE",
                )
            ).all()
        )
        rows: list[_RankingRow] = []
        for membership in memberships:
            evaluation = self.db.scalar(
                select(PortfolioProjectEvaluation)
                .where(
                    PortfolioProjectEvaluation.tenant_id == self.tenant_id,
                    PortfolioProjectEvaluation.portfolio_workspace_id == portfolio_id,
                    PortfolioProjectEvaluation.project_workspace_id == membership.project_workspace_id,
                    PortfolioProjectEvaluation.status == "COMPLETED",
                )
                .order_by(PortfolioProjectEvaluation.evaluation_version.desc())
            )
            if evaluation is None or evaluation.completed_at is None:
                continue
            project = self._workspace(evaluation.project_workspace_id)
            source = dict(evaluation.source_snapshot_json or {})
            rows.append(
                _RankingRow(
                    portfolio_workspace_id=portfolio_id,
                    project_workspace_id=project.id,
                    project_number=project.code,
                    project_name=project.name,
                    evaluation_id=evaluation.id,
                    evaluation_version=evaluation.evaluation_version,
                    normalized_score=Decimal(evaluation.normalized_score),
                    strategic_alignment_score=Decimal(evaluation.strategic_alignment_score),
                    risk_score=Decimal(evaluation.risk_score),
                    proposal_score=_optional_decimal(source.get("proposal_score")),
                    strategic_objectives=list(source.get("strategic_objectives") or []),
                    rom_cost=_optional_decimal(source.get("rom_cost")),
                    evaluation_status=evaluation.status,
                    completed_at=evaluation.completed_at,
                    planned_finish=_parse_date(source.get("target_finish")),
                )
            )
        return rows

    @staticmethod
    def _rank(rows: list[_RankingRow]) -> list[PrioritizationItemOut]:
        ordered = sorted(
            rows,
            key=lambda item: (
                -item.normalized_score,
                -item.strategic_alignment_score,
                item.risk_score,
                item.planned_finish or date.max,
                item.project_number,
            ),
        )
        return [PrioritizationItemOut(rank=index, **item.as_dict()) for index, item in enumerate(ordered, 1)]

    def _effective_configuration(
        self, workspace: EnterpriseWorkspace | None, *, published_only: bool
    ) -> AdminConfiguration | None:
        records = list(
            self.db.scalars(
                select(AdminConfiguration).where(
                    AdminConfiguration.tenant_id == self.tenant_id,
                    AdminConfiguration.kind == CONFIGURATION_KIND,
                    *([AdminConfiguration.status == "published"] if published_only else []),
                )
            ).all()
        )
        path = self._workspace_path(workspace) if workspace else []
        path_ids = {item.id: item for item in path}
        candidates: list[tuple[int, int, AdminConfiguration]] = []
        for record in records:
            scope = dict((record.content_json or {}).get("scope", {}))
            scope_type = str(scope.get("type") or "tenant")
            scope_id = scope.get("workspace_id")
            specificity = 0
            if scope_type != "tenant":
                if scope_id not in path_ids:
                    continue
                scoped_workspace = path_ids[int(scope_id)]
                expected = {"enterprise": "enterprise", "business-unit": "business-unit", "portfolio": "portfolio"}.get(
                    scope_type
                )
                if expected and scoped_workspace.workspace_type_code != expected:
                    continue
                specificity = {"enterprise": 1, "business-unit": 2, "portfolio": 3}.get(scope_type, 0)
            candidates.append((specificity, record.revision, record))
        return max(candidates, key=lambda item: (item[0], item[1]))[2] if candidates else None

    def _tenant_published(self) -> AdminConfiguration | None:
        return self._effective_configuration(None, published_only=True)

    def _configuration_issues(self, content: dict) -> list[str]:
        issues: list[str] = []
        scope = dict(content.get("scope", {}))
        if scope.get("type", "tenant") not in {"tenant", "enterprise", "business-unit", "portfolio"}:
            issues.append("INVALID_CONFIGURATION_SCOPE")
        if scope.get("type", "tenant") != "tenant" and not scope.get("workspace_id"):
            issues.append("SCOPED_CONFIGURATION_WORKSPACE_REQUIRED")
        applicable = list(content.get("applicable_governance_models", []))
        if applicable != ["CAPITAL_OWNER"]:
            issues.append("GATE07E_ONLY_SUPPORTS_CAPITAL_OWNER")
        scale = dict(content.get("scoring_scale", {}))
        try:
            minimum = Decimal(str(scale.get("minimum")))
            maximum = Decimal(str(scale.get("maximum")))
            if minimum >= maximum:
                issues.append("INVALID_SCORING_SCALE")
        except Exception:
            issues.append("INVALID_SCORING_SCALE")
        criteria = list(content.get("criteria", []))
        codes = [str(item.get("code", "")) for item in criteria]
        if not criteria or any(not code for code in codes) or len(codes) != len(set(codes)):
            issues.append("INVALID_CRITERIA")
        try:
            weight = sum(Decimal(str(item.get("weight", 0))) for item in criteria)
            if weight != Decimal("100"):
                issues.append("CRITERIA_WEIGHTS_MUST_TOTAL_100")
        except Exception:
            issues.append("INVALID_CRITERIA_WEIGHT")
        if dict(content.get("ranking_rules", {})).get("manual_override") is not False:
            issues.append("MANUAL_RANK_OVERRIDE_NOT_SUPPORTED")
        forbidden = {"pdri", "fel", "fid", "budget_allocation", "resource_allocation"}
        serialized = json.dumps(content, ensure_ascii=False).lower()
        if any(term in serialized for term in forbidden):
            issues.append("DOWNSTREAM_CAPABILITY_NOT_ALLOWED_IN_GATE07E")
        return sorted(set(issues))

    def _validate_configuration(self, content: dict) -> None:
        issues = self._configuration_issues(content)
        if issues:
            raise HTTPException(status_code=422, detail={"code": "INVALID_CONFIGURATION", "issues": issues})

    def _configuration(self, configuration_id: int, *, lock: bool = False) -> AdminConfiguration:
        statement = select(AdminConfiguration).where(
            AdminConfiguration.id == configuration_id,
            AdminConfiguration.tenant_id == self.tenant_id,
            AdminConfiguration.kind == CONFIGURATION_KIND,
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail="Portfolio evaluation configuration not found")
        return record

    @staticmethod
    def _check_configuration_version(record: AdminConfiguration, expected: int) -> None:
        if record.version != expected:
            raise HTTPException(status_code=412, detail={"code": "ETAG_MISMATCH"})

    def _evaluation(self, evaluation_id: int, *, lock: bool = False) -> PortfolioProjectEvaluation:
        statement = select(PortfolioProjectEvaluation).where(
            PortfolioProjectEvaluation.id == evaluation_id,
            PortfolioProjectEvaluation.tenant_id == self.tenant_id,
        )
        if lock:
            statement = statement.with_for_update().execution_options(populate_existing=True)
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail="Portfolio evaluation not found")
        return record

    @staticmethod
    def _check_version(record: PortfolioProjectEvaluation, expected: int) -> None:
        if record.revision_version != expected:
            raise HTTPException(status_code=412, detail={"code": "ETAG_MISMATCH"})

    def _latest_evaluation(self, portfolio_id: int, project_id: int) -> PortfolioProjectEvaluation | None:
        return self.db.scalar(
            select(PortfolioProjectEvaluation)
            .where(
                PortfolioProjectEvaluation.tenant_id == self.tenant_id,
                PortfolioProjectEvaluation.portfolio_workspace_id == portfolio_id,
                PortfolioProjectEvaluation.project_workspace_id == project_id,
            )
            .order_by(PortfolioProjectEvaluation.evaluation_version.desc())
        )

    def _evaluation_out(self, record: PortfolioProjectEvaluation) -> EvaluationOut:
        portfolio = self._workspace(record.portfolio_workspace_id)
        project = self._workspace(record.project_workspace_id)
        blockers: list[str] = []
        membership = self.db.get(PortfolioProjectMembership, record.portfolio_membership_id)
        if record.status in {"DRAFT", "IN_PROGRESS"}:
            blockers = self._eligibility_blockers(project, portfolio, membership)
            current_hash = str(
                dict(project.defaults_json or {}).get("_portfolio_planning", {}).get("planning_entry_hash", "")
            )
            if current_hash != record.planning_entry_hash:
                blockers.append("PLANNING_SNAPSHOT_STALE")
        actions = ["read"]
        if record.status in {"DRAFT", "IN_PROGRESS"} and not blockers:
            actions.extend(["edit", "complete"])
        if record.status in {"COMPLETED", "SUPERSEDED"} and not self._eligibility_blockers(
            project, portfolio, membership
        ):
            actions.append("reevaluate")
        return EvaluationOut(
            id=record.id,
            tenant_id=record.tenant_id,
            portfolio_workspace_id=record.portfolio_workspace_id,
            portfolio_name=portfolio.name,
            project_workspace_id=record.project_workspace_id,
            project_number=project.code,
            project_name=project.name,
            portfolio_membership_id=record.portfolio_membership_id,
            evaluation_version=record.evaluation_version,
            status=record.status,
            matrix_configuration_id=record.matrix_configuration_id,
            matrix_revision=record.matrix_revision,
            matrix_hash=record.matrix_hash,
            matrix_snapshot=dict(record.matrix_snapshot_json or {}),
            source_snapshot=dict(record.source_snapshot_json or {}),
            source_snapshot_hash=record.source_snapshot_hash,
            planning_entry_hash=record.planning_entry_hash,
            ratings=list(record.ratings_json or []),
            score_components=list(record.score_components_json or []),
            normalized_score=Decimal(record.normalized_score),
            strategic_alignment_score=Decimal(record.strategic_alignment_score),
            risk_score=Decimal(record.risk_score),
            comments=record.comments,
            evaluator_user_id=record.evaluator_user_id,
            revision_version=record.revision_version,
            started_at=record.started_at,
            completed_at=record.completed_at,
            allowed_actions=actions,
            blocking_issues=sorted(set(blockers)),
        )

    @staticmethod
    def _queue_name(blockers: list[str], evaluation: PortfolioProjectEvaluation | None) -> str:
        if blockers:
            return "BLOCKED"
        if evaluation is None:
            return "TO_EVALUATE"
        if evaluation.status in {"DRAFT", "IN_PROGRESS"}:
            return "IN_PROGRESS"
        if evaluation.status == "COMPLETED":
            return "COMPLETED"
        return "TO_EVALUATE"

    def _workspace(self, workspace_id: int | None) -> EnterpriseWorkspace:
        if workspace_id is None:
            raise HTTPException(status_code=404, detail="Workspace not found")
        workspace = self.db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.id == workspace_id,
                EnterpriseWorkspace.tenant_id == self.tenant_id,
            )
        )
        if workspace is None:
            raise HTTPException(status_code=404, detail="Workspace not found")
        return workspace

    @staticmethod
    def _assert_workspace_type(workspace: EnterpriseWorkspace, expected: str) -> None:
        if workspace.workspace_type_code != expected:
            raise HTTPException(status_code=422, detail=f"WORKSPACE_IS_NOT_{expected.upper().replace('-', '_')}")

    def _assert_scope(self, *workspace_ids: int) -> None:
        if self.context is None or self.context.organization_wide:
            return
        if not any(item in self.context.workspace_ids for item in workspace_ids):
            raise HTTPException(status_code=403, detail="Workspace is outside the authorized scope")

    def _workspace_path(self, workspace: EnterpriseWorkspace | None) -> list[EnterpriseWorkspace]:
        if workspace is None:
            return []
        path = [workspace]
        visited = {workspace.id}
        current = workspace
        while current.parent_id is not None:
            parent = self.db.scalar(
                select(EnterpriseWorkspace).where(
                    EnterpriseWorkspace.tenant_id == self.tenant_id,
                    EnterpriseWorkspace.id == current.parent_id,
                )
            )
            if parent is None or parent.id in visited:
                break
            path.append(parent)
            visited.add(parent.id)
            current = parent
        return list(reversed(path))

    @staticmethod
    def _workspace_summary(workspace: EnterpriseWorkspace) -> dict:
        return {
            "id": workspace.id,
            "code": workspace.code,
            "name": workspace.name,
            "workspace_type_code": workspace.workspace_type_code,
            "status": workspace.status,
            "record_code": workspace.record_code,
            "parent_id": workspace.parent_id,
            "version": workspace.version,
        }

    @staticmethod
    def _event_context(record: PortfolioProjectEvaluation) -> dict:
        return {
            "portfolio_workspace_id": record.portfolio_workspace_id,
            "project_workspace_id": record.project_workspace_id,
            "evaluation_version": record.evaluation_version,
            "matrix_hash": record.matrix_hash,
            "planning_entry_hash": record.planning_entry_hash,
        }

    def _event(self, event_type: str, target_type: str, target_id: int | None, metadata: dict) -> None:
        self.db.add(
            SecurityEvent(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                event_type=event_type,
                outcome="success",
                target_type=target_type,
                target_id=target_id,
                metadata_json=metadata,
            )
        )


class _RankingRow:
    def __init__(
        self,
        *,
        portfolio_workspace_id: int,
        project_workspace_id: int,
        project_number: str,
        project_name: str,
        evaluation_id: int,
        evaluation_version: int,
        normalized_score: Decimal,
        strategic_alignment_score: Decimal,
        risk_score: Decimal,
        proposal_score: Decimal | None,
        strategic_objectives: list[dict],
        rom_cost: Decimal | None,
        evaluation_status: str,
        completed_at,
        planned_finish: date | None,
    ) -> None:
        self.portfolio_workspace_id = portfolio_workspace_id
        self.project_workspace_id = project_workspace_id
        self.project_number = project_number
        self.project_name = project_name
        self.evaluation_id = evaluation_id
        self.evaluation_version = evaluation_version
        self.normalized_score = normalized_score
        self.strategic_alignment_score = strategic_alignment_score
        self.risk_score = risk_score
        self.proposal_score = proposal_score
        self.strategic_objectives = strategic_objectives
        self.rom_cost = rom_cost
        self.evaluation_status = evaluation_status
        self.completed_at = completed_at
        self.planned_finish = planned_finish

    def as_dict(self) -> dict:
        return {
            "portfolio_workspace_id": self.portfolio_workspace_id,
            "project_workspace_id": self.project_workspace_id,
            "project_number": self.project_number,
            "project_name": self.project_name,
            "evaluation_id": self.evaluation_id,
            "evaluation_version": self.evaluation_version,
            "normalized_score": self.normalized_score,
            "strategic_alignment_score": self.strategic_alignment_score,
            "risk_score": self.risk_score,
            "proposal_score": self.proposal_score,
            "strategic_objectives": self.strategic_objectives,
            "rom_cost": self.rom_cost,
            "evaluation_status": self.evaluation_status,
            "completed_at": self.completed_at,
            "planned_finish": self.planned_finish,
        }


def _parse_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _planned_finish(project: EnterpriseWorkspace) -> date | None:
    planning = dict(dict(project.defaults_json or {}).get("_portfolio_planning", {}))
    return _parse_date(dict(planning.get("snapshot") or {}).get("target_finish"))


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
