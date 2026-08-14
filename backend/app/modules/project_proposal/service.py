"""Application service for Gate 07B Project Proposal lifecycle."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domain.models import (
    AdminConfiguration,
    AdminNumberSequence,
    EnterpriseWorkspace,
    PermissionCatalog,
    SecurityAccessAssignment,
    SecurityEvent,
    SecurityRolePermission,
    UserAccount,
)
from app.modules.enterprise_structure.models import EnterpriseStrategicObjective
from app.modules.enterprise_structure.permissions import EnterprisePermissionContext, ensure_enterprise_permissions
from app.modules.idea_demand.models import Idea, IdeaEvaluation
from app.modules.project_proposal.models import ProjectProposal, ProjectProposalEvaluation
from app.modules.project_proposal.schemas import (
    GateReadinessOut,
    ProjectProposalEvaluationOut,
    ProjectProposalOut,
    ProjectProposalState,
    ProjectProposalUpdate,
    ProposalConfigurationPreviewOut,
    ProposalEvaluationIn,
    ProposalHistoryItemOut,
    ProposalOptionsOut,
    ProposalPreviewOut,
    ProposalReturnIn,
)

PROPOSAL_NUMBER_RULE = "project-proposal"
OWNING_TYPES = frozenset({"enterprise", "business-unit", "portfolio"})
INACTIVE_STATES = frozenset(
    {"CANCELLED", "ARCHIVED", "STRATEGIC_GATE_APPROVED", "STRATEGIC_GATE_REJECTED"}
)
PRIVILEGED_ROLES = frozenset(
    {
        "organization_admin",
        "proposal_owner",
        "proposal_reviewer",
        "proposal_evaluator",
        "proposal_configuration_admin",
    }
)

DEFAULT_PROPOSAL_CONFIGURATION = {
    "workspace_id": None,
    "inherit_to_descendants": True,
    "max_active_proposals_per_idea": 1,
    "target_portfolio_required": False,
    "rom_cost_required": False,
    "duration_required": False,
    "required_fields": [
        "name",
        "business_need",
        "business_justification",
        "project_objectives_json",
        "preliminary_scope",
        "expected_benefits",
        "strategic_objective_codes",
        "sponsor_user_id",
        "proposal_owner_user_id",
        "key_risks_json",
    ],
    "idea_to_proposal_mapping": {
        "name": "title",
        "business_need": "description",
        "business_justification": "expected_benefit",
        "project_objectives_json": "strategic_objective_codes",
        "preliminary_scope": "description",
        "expected_benefits": "expected_benefit",
        "rom_cost": "estimated_value",
        "currency_code": "currency_code",
        "strategic_objective_codes": "strategic_objective_codes",
        "sponsor_user_id": "owner_user_id|requestor_user_id",
        "proposal_owner_user_id": "owner_user_id|requestor_user_id",
        "target_portfolio_workspace_id": "target_portfolio_workspace_id",
        "origin_idea_score": "accepted_evaluation.total_score",
    },
    "review_checklist": [
        {"code": "business_need_complete", "label": "Business need complete", "blocking": True},
        {
            "code": "business_justification_complete",
            "label": "Business justification complete",
            "blocking": True,
        },
        {"code": "objectives_defined", "label": "Objectives defined", "blocking": True},
        {"code": "preliminary_scope_defined", "label": "Preliminary scope defined", "blocking": True},
        {"code": "expected_benefits_defined", "label": "Expected benefits defined", "blocking": True},
        {"code": "sponsor_valid", "label": "Sponsor valid", "blocking": True},
        {"code": "proposal_owner_valid", "label": "Proposal owner valid", "blocking": True},
        {
            "code": "rom_cost_available_if_required",
            "label": "ROM cost available when required",
            "blocking": True,
        },
        {
            "code": "duration_available_if_required",
            "label": "Duration available when required",
            "blocking": True,
        },
        {"code": "key_risks_identified", "label": "Key risks identified", "blocking": True},
        {
            "code": "strategic_objectives_valid",
            "label": "Strategic objectives valid",
            "blocking": True,
        },
        {
            "code": "target_portfolio_valid_if_required",
            "label": "Target Portfolio valid when required",
            "blocking": True,
        },
    ],
    "gate_readiness_policy": {
        "require_completed_review": True,
        "require_latest_evaluation": True,
        "minimum_score": 60,
    },
}

DEFAULT_PROPOSAL_MATRIX = {
    "workspace_id": None,
    "inherit_to_descendants": True,
    "scale": {"min": 1, "max": 5},
    "criteria": [
        {"code": "strategic_alignment", "label": "Strategic Alignment", "weight": 15},
        {"code": "business_value", "label": "Business Value", "weight": 15},
        {"code": "business_case_quality", "label": "Business Case Quality", "weight": 15},
        {"code": "technical_feasibility", "label": "Technical Feasibility", "weight": 10},
        {"code": "financial_feasibility", "label": "Financial Feasibility", "weight": 10},
        {"code": "execution_feasibility", "label": "Execution Feasibility", "weight": 10},
        {"code": "risk", "label": "Risk", "weight": 10},
        {"code": "urgency", "label": "Urgency", "weight": 10},
        {"code": "organizational_capacity", "label": "Organizational Capacity", "weight": 5},
    ],
    "recommendation_threshold": 60,
}


class ProjectProposalService:
    def __init__(
        self,
        db: Session,
        tenant_id: int,
        actor_id: int,
        context: EnterprisePermissionContext,
    ) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.actor_id = actor_id
        self.context = context

    def ensure_seed(self) -> None:
        """Install configuration and numbering only; never create a Proposal."""
        ensure_enterprise_permissions(self.db, self.tenant_id, self.actor_id)
        if self._latest_configuration("project_proposal_configuration", "default") is None:
            self._seed_configuration(
                "project_proposal_configuration",
                "default",
                "Default Project Proposal Lifecycle",
                DEFAULT_PROPOSAL_CONFIGURATION,
            )
        if self._latest_configuration("project_proposal_evaluation_matrix", "default") is None:
            self._seed_configuration(
                "project_proposal_evaluation_matrix",
                "default",
                "Default Project Proposal Evaluation Matrix",
                DEFAULT_PROPOSAL_MATRIX,
            )
        sequence = self._sequence(required=False)
        if sequence is None:
            self.db.add(
                AdminNumberSequence(
                    tenant_id=self.tenant_id,
                    rule_code=PROPOSAL_NUMBER_RULE,
                    scope_key="tenant",
                    next_value=1,
                    version=1,
                )
            )
        self.db.commit()

    def options(self) -> ProposalOptionsOut:
        workspaces = self._authorized_workspaces()
        objectives = self._objectives()
        users = self._users()
        eligible: list[dict] = []
        ideas = self.db.scalars(
            select(Idea)
            .where(Idea.tenant_id == self.tenant_id, Idea.state == "ACCEPTED")
            .order_by(Idea.updated_at.desc())
        ).all()
        for idea in ideas:
            if not self._can_access_idea(idea):
                continue
            config, _sources, _path, _record = self._effective_configuration(self._workspace(idea.owning_workspace_id))
            blockers = self._source_blockers(idea, config)
            eligible.append(
                {
                    "id": idea.id,
                    "idea_number": idea.idea_number,
                    "title": idea.title,
                    "owning_workspace_id": idea.owning_workspace_id,
                    "can_create": not blockers,
                    "blockers": blockers,
                }
            )
        sequence = self._sequence()
        return ProposalOptionsOut(
            number_preview=f"PROP-{sequence.next_value:05d}",
            eligible_ideas=eligible,
            owning_workspaces=[self._workspace_option(item) for item in workspaces],
            target_portfolios=[
                self._workspace_option(item) for item in workspaces if item.workspace_type_code == "portfolio"
            ],
            strategic_objectives=objectives,
            users=[{"id": item.id, "name": item.full_name, "email": item.email} for item in users],
        )

    def preview(self, source_idea_id: int) -> ProposalPreviewOut:
        idea = self._idea(source_idea_id)
        workspace = self._owning_workspace(idea.owning_workspace_id)
        config, sources, _path, config_record = self._effective_configuration(workspace)
        matrix = self._effective_matrix(workspace)
        evaluation = self._accepted_evaluation(idea, required=False)
        source_values, mapped_values = self._mapping_values(idea, evaluation)
        blockers = self._source_blockers(idea, config)
        warnings: list[str] = []
        if mapped_values.get("rom_cost") is None:
            warnings.append("ROM_COST_NOT_AVAILABLE")
        if idea.target_portfolio_workspace_id is None:
            warnings.append("TARGET_PORTFOLIO_NOT_SELECTED")
        target = self._workspace(idea.target_portfolio_workspace_id) if idea.target_portfolio_workspace_id else None
        return ProposalPreviewOut(
            proposal_number_preview=f"PROP-{self._sequence().next_value:05d}",
            source_idea={
                "id": idea.id,
                "idea_number": idea.idea_number,
                "title": idea.title,
                "status": idea.state,
            },
            accepted_evaluation={
                "id": evaluation.id if evaluation else None,
                "version": evaluation.evaluation_version if evaluation else None,
                "score": str(evaluation.total_score) if evaluation else None,
                "created_at": evaluation.created_at.isoformat() if evaluation else None,
            },
            mapping={
                "configuration_id": config_record.id,
                "revision": config_record.revision,
                "hash": self._hash(config.get("idea_to_proposal_mapping", {})),
                "source": sources,
            },
            mapped_fields=mapped_values,
            owning_workspace=self._workspace_option(workspace),
            target_portfolio=self._workspace_option(target) if target else None,
            strategic_objectives=[
                item for item in self._objectives() if item["code"] in idea.strategic_objective_codes
            ],
            required_fields=list(config.get("required_fields", [])),
            review_checklist=list(config.get("review_checklist", [])),
            policy={
                "max_active_proposals_per_idea": int(config.get("max_active_proposals_per_idea", 1)),
                "target_portfolio_required": bool(config.get("target_portfolio_required", False)),
                "gate_readiness_policy": config.get("gate_readiness_policy", {}),
            },
            evaluation_matrix={
                "configuration_id": matrix.id,
                "revision": matrix.revision,
                "criteria": matrix.content_json.get("criteria", []),
            },
            blockers=blockers,
            warnings=warnings,
        )

    def configuration_preview(self, source_idea_id: int) -> ProposalConfigurationPreviewOut:
        idea = self._idea(source_idea_id)
        workspace = self._owning_workspace(idea.owning_workspace_id)
        effective, sources, path, _record = self._effective_configuration(workspace)
        return ProposalConfigurationPreviewOut(
            source_idea_id=idea.id,
            owning_workspace_id=workspace.id,
            path=[self._workspace_option(item) for item in path],
            effective=effective,
            sources=sources,
            proposal_preview=self.preview(idea.id),
        )

    def create(self, source_idea_id: int) -> ProjectProposalOut:
        idea = self._idea(source_idea_id, for_update=True)
        existing = self.db.scalar(
            select(ProjectProposal)
            .where(
                ProjectProposal.tenant_id == self.tenant_id,
                ProjectProposal.source_idea_id == idea.id,
                ProjectProposal.status.not_in(INACTIVE_STATES),
            )
            .order_by(ProjectProposal.id)
            .limit(1)
        )
        if existing is not None:
            return self._out(existing)
        workspace = self._owning_workspace(idea.owning_workspace_id)
        config, sources, _path, config_record = self._effective_configuration(workspace)
        blockers = self._source_blockers(idea, config)
        if blockers:
            raise HTTPException(status_code=409, detail={"reason": "SOURCE_IDEA_NOT_READY", "blockers": blockers})
        evaluation = self._accepted_evaluation(idea)
        source_values, mapped = self._mapping_values(idea, evaluation)
        mapping = config.get("idea_to_proposal_mapping", {})
        proposal = ProjectProposal(
            tenant_id=self.tenant_id,
            proposal_number=self._reserve_number(),
            source_idea_id=idea.id,
            accepted_idea_evaluation_id=evaluation.id,
            owning_workspace_id=idea.owning_workspace_id,
            target_portfolio_workspace_id=idea.target_portfolio_workspace_id,
            name=str(mapped["name"]),
            business_need=str(mapped["business_need"]),
            business_justification=str(mapped["business_justification"]),
            project_objectives_json=list(mapped["project_objectives_json"]),
            preliminary_scope=str(mapped["preliminary_scope"]),
            out_of_scope="",
            expected_benefits=str(mapped["expected_benefits"]),
            benefit_owner_user_id=None,
            rom_cost=mapped["rom_cost"],
            currency_code=str(mapped["currency_code"]),
            preliminary_duration_days=None,
            target_start_date=None,
            target_finish_date=None,
            key_risks_json=[],
            assumptions_json=[],
            constraints_json=[],
            strategic_objective_codes=list(mapped["strategic_objective_codes"]),
            sponsor_user_id=int(mapped["sponsor_user_id"]),
            proposal_owner_user_id=int(mapped["proposal_owner_user_id"]),
            origin_idea_score=evaluation.total_score,
            status="DRAFT",
            mapping_configuration_id=config_record.id,
            mapping_revision=config_record.revision,
            mapping_hash=self._hash(mapping),
            source_values_snapshot_json=source_values,
            mapped_values_snapshot_json=self._json_safe(mapped),
            configuration_snapshot_json={"effective": config, "sources": sources},
            review_snapshot_json={},
            attachment_refs_json=list(idea.attachment_refs_json or []),
            revision_version=1,
            created_by=self.actor_id,
            updated_by=self.actor_id,
        )
        self.db.add(proposal)
        self.db.flush()
        self._event(
            "project_proposal.created",
            proposal,
            None,
            "DRAFT",
            {"source_idea_id": idea.id, "accepted_idea_evaluation_id": evaluation.id},
        )
        self.db.commit()
        self.db.refresh(proposal)
        return self._out(proposal)

    def list(
        self,
        *,
        status_filter: str = "",
        search: str = "",
        owning_workspace_id: int | None = None,
        queue: str = "",
    ) -> list[ProjectProposalOut]:
        statement = select(ProjectProposal).where(ProjectProposal.tenant_id == self.tenant_id)
        if not self.context.organization_wide:
            allowed = list(self.context.workspace_ids)
            statement = statement.where(
                (ProjectProposal.created_by == self.actor_id)
                | (ProjectProposal.proposal_owner_user_id == self.actor_id)
                | (ProjectProposal.owning_workspace_id.in_(allowed) if allowed else False)
            )
        elif not (self.context.role_codes & PRIVILEGED_ROLES):
            statement = statement.where(ProjectProposal.created_by == self.actor_id)
        if status_filter.strip():
            statement = statement.where(ProjectProposal.status == status_filter.strip().upper())
        if owning_workspace_id:
            statement = statement.where(ProjectProposal.owning_workspace_id == owning_workspace_id)
        if search.strip():
            term = f"%{search.strip().lower()}%"
            statement = statement.where(
                func.lower(ProjectProposal.proposal_number).like(term) | func.lower(ProjectProposal.name).like(term)
            )
        queues = {
            "mine": ProjectProposal.created_by == self.actor_id,
            "review": ProjectProposal.status.in_(["SUBMITTED", "UNDER_REVIEW"]),
            "assigned": ProjectProposal.proposal_owner_user_id == self.actor_id,
            "evaluation": ProjectProposal.status == "UNDER_EVALUATION",
            "gate": ProjectProposal.status == "READY_FOR_STRATEGIC_GATE",
            "returned": ProjectProposal.status == "RETURNED",
            "cancelled": ProjectProposal.status == "CANCELLED",
        }
        if queue in queues:
            statement = statement.where(queues[queue])
        rows = self.db.scalars(statement.order_by(ProjectProposal.updated_at.desc())).all()
        return [self._out(item) for item in rows]

    def related_to_idea(self, idea_id: int) -> list[ProjectProposalOut]:
        self._idea(idea_id)
        rows = self.db.scalars(
            select(ProjectProposal)
            .where(ProjectProposal.tenant_id == self.tenant_id, ProjectProposal.source_idea_id == idea_id)
            .order_by(ProjectProposal.created_at.desc())
        ).all()
        return [self._out(item) for item in rows]

    def get(self, proposal_id: int) -> ProjectProposalOut:
        return self._out(self._proposal(proposal_id))

    def update(self, proposal_id: int, payload: ProjectProposalUpdate, expected_version: int) -> ProjectProposalOut:
        proposal = self._proposal(proposal_id)
        self._check_version(proposal, expected_version)
        if proposal.status not in {"DRAFT", "RETURNED"}:
            raise HTTPException(status_code=409, detail="Only DRAFT or RETURNED Proposals can be edited")
        self._validate_workspace(proposal.owning_workspace_id, proposal.target_portfolio_workspace_id)
        self._validate_user(payload.sponsor_user_id, "project_proposal.submit", proposal.owning_workspace_id)
        self._validate_user(payload.proposal_owner_user_id, "project_proposal.evaluate", proposal.owning_workspace_id)
        if payload.benefit_owner_user_id is not None:
            self._validate_user(payload.benefit_owner_user_id, "project_proposal.read", proposal.owning_workspace_id)
        valid_objectives = {item["code"] for item in self._objectives()}
        if set(payload.strategic_objective_codes) - valid_objectives:
            raise HTTPException(status_code=422, detail="One or more Strategic Objectives are inactive or unknown")
        before = proposal.status
        for key, value in self._payload_values(payload).items():
            setattr(proposal, key, value)
        proposal.status = "DRAFT"
        proposal.return_reason = None
        proposal.returned_stage = None
        self._touch(proposal)
        self._event("project_proposal.updated", proposal, before, proposal.status)
        return self._commit(proposal)

    def submit(self, proposal_id: int, expected_version: int) -> ProjectProposalOut:
        proposal = self._proposal(proposal_id)
        if proposal.status == "SUBMITTED":
            return self._out(proposal)
        self._check_version(proposal, expected_version)
        if proposal.status not in {"DRAFT", "RETURNED"}:
            raise HTTPException(status_code=409, detail="Proposal cannot be submitted from its current state")
        blockers = self._required_field_blockers(proposal)
        if blockers:
            raise HTTPException(status_code=422, detail={"reason": "INCOMPLETE_PROPOSAL", "items": blockers})
        return self._transition(
            proposal,
            "SUBMITTED",
            "project_proposal.submitted",
            submitted_at=utc_now(),
        )

    def start_review(self, proposal_id: int, expected_version: int) -> ProjectProposalOut:
        proposal = self._proposal(proposal_id)
        if proposal.status == "UNDER_REVIEW":
            return self._out(proposal)
        self._check_version(proposal, expected_version)
        if proposal.status != "SUBMITTED":
            raise HTTPException(status_code=409, detail="Review requires SUBMITTED state")
        proposal.review_snapshot_json = self._review(proposal)
        return self._transition(
            proposal,
            "UNDER_REVIEW",
            "project_proposal.review_started",
            review_started_at=utc_now(),
        )

    def return_proposal(
        self,
        proposal_id: int,
        payload: ProposalReturnIn,
        expected_version: int,
    ) -> ProjectProposalOut:
        proposal = self._proposal(proposal_id)
        if proposal.status == "RETURNED":
            return self._out(proposal)
        self._check_version(proposal, expected_version)
        if proposal.status not in {"SUBMITTED", "UNDER_REVIEW", "UNDER_EVALUATION", "EVALUATED"}:
            raise HTTPException(status_code=409, detail="Proposal cannot be returned from its current state")
        proposal.return_reason = payload.reason.strip()
        proposal.returned_stage = proposal.status
        return self._transition(
            proposal,
            "RETURNED",
            "project_proposal.returned",
            metadata={"reason": proposal.return_reason, "stage": proposal.returned_stage},
            returned_at=utc_now(),
        )

    def start_evaluation(self, proposal_id: int, expected_version: int) -> ProjectProposalOut:
        proposal = self._proposal(proposal_id)
        if proposal.status == "UNDER_EVALUATION":
            return self._out(proposal)
        self._check_version(proposal, expected_version)
        if proposal.status != "UNDER_REVIEW":
            raise HTTPException(status_code=409, detail="Evaluation requires UNDER_REVIEW state")
        review = self._review(proposal)
        blocking = [item["code"] for item in review["checks"] if item["blocking"] and item["status"] == "FAIL"]
        if blocking:
            proposal.review_snapshot_json = review
            raise HTTPException(status_code=422, detail={"reason": "REVIEW_BLOCKED", "items": blocking})
        proposal.review_snapshot_json = review
        proposal.review_completed_at = utc_now()
        return self._transition(
            proposal,
            "UNDER_EVALUATION",
            "project_proposal.evaluation_started",
            evaluation_started_at=utc_now(),
        )

    def complete_evaluation(
        self,
        proposal_id: int,
        payload: ProposalEvaluationIn,
        expected_version: int,
    ) -> ProjectProposalOut:
        proposal = self._proposal(proposal_id, for_update=True)
        if proposal.status == "EVALUATED":
            return self._out(proposal)
        self._check_version(proposal, expected_version)
        if proposal.status != "UNDER_EVALUATION":
            raise HTTPException(status_code=409, detail="Start evaluation before completing it")
        matrix = self._effective_matrix(self._workspace(proposal.owning_workspace_id))
        criteria = {str(item["code"]): item for item in matrix.content_json.get("criteria", [])}
        ratings = {str(item.get("criterion_code")): item for item in payload.ratings}
        if set(ratings) != set(criteria):
            raise HTTPException(status_code=422, detail="Every Proposal matrix criterion requires exactly one rating")
        scale = matrix.content_json.get("scale", {"min": 1, "max": 5})
        minimum = Decimal(str(scale.get("min", 1)))
        maximum = Decimal(str(scale.get("max", 5)))
        total = Decimal("0")
        normalized: list[dict] = []
        for code, criterion in criteria.items():
            rating = Decimal(str(ratings[code].get("rating", 0)))
            if rating < minimum or rating > maximum:
                raise HTTPException(status_code=422, detail=f"Rating for {code} is outside the configured scale")
            weight = Decimal(str(criterion.get("weight", 0)))
            score = rating / maximum * weight
            total += score
            normalized.append(
                {
                    "criterion_code": code,
                    "rating": float(rating),
                    "weight": float(weight),
                    "score": float(score.quantize(Decimal("0.0001"))),
                    "comment": str(ratings[code].get("comment", "")),
                }
            )
        version = (
            int(
                self.db.scalar(
                    select(func.coalesce(func.max(ProjectProposalEvaluation.evaluation_version), 0)).where(
                        ProjectProposalEvaluation.tenant_id == self.tenant_id,
                        ProjectProposalEvaluation.project_proposal_id == proposal.id,
                    )
                )
                or 0
            )
            + 1
        )
        threshold = Decimal(str(matrix.content_json.get("recommendation_threshold", 60)))
        evaluation = ProjectProposalEvaluation(
            tenant_id=self.tenant_id,
            project_proposal_id=proposal.id,
            evaluation_version=version,
            matrix_configuration_id=matrix.id,
            matrix_revision=matrix.revision,
            matrix_hash=matrix.content_hash or self._hash(matrix.content_json),
            criteria_snapshot_json=list(matrix.content_json.get("criteria", [])),
            ratings_json=normalized,
            total_score=total.quantize(Decimal("0.0001")),
            recommendation="PROCEED_TO_GATE" if total >= threshold else "REWORK",
            comments=payload.comments,
            evaluator_user_id=self.actor_id,
        )
        self.db.add(evaluation)
        self.db.flush()
        proposal.evaluation_completed_at = utc_now()
        before = proposal.status
        proposal.status = "EVALUATED"
        self._touch(proposal)
        self._event(
            "project_proposal.evaluated",
            proposal,
            before,
            proposal.status,
            {"evaluation_id": evaluation.id, "evaluation_version": version, "score": str(total)},
        )
        return self._commit(proposal)

    def mark_gate_ready(self, proposal_id: int, expected_version: int) -> ProjectProposalOut:
        proposal = self._proposal(proposal_id, for_update=True)
        if proposal.status == "READY_FOR_STRATEGIC_GATE":
            return self._out(proposal)
        self._check_version(proposal, expected_version)
        if proposal.status != "EVALUATED":
            raise HTTPException(status_code=409, detail="Only an EVALUATED Proposal can be marked gate ready")
        readiness = self._gate_readiness(proposal)
        if readiness["blockers"]:
            raise HTTPException(
                status_code=422,
                detail={"reason": "GATE07B_REWORK_REQUIRED", "blockers": readiness["blockers"]},
            )
        return self._transition(
            proposal,
            "READY_FOR_STRATEGIC_GATE",
            "project_proposal.ready_for_strategic_gate",
            metadata={"readiness_hash": readiness["readiness_hash"]},
            ready_for_gate_at=utc_now(),
        )

    def cancel(self, proposal_id: int, expected_version: int) -> ProjectProposalOut:
        proposal = self._proposal(proposal_id)
        if proposal.status == "CANCELLED":
            return self._out(proposal)
        self._check_version(proposal, expected_version)
        if proposal.status not in {"DRAFT", "SUBMITTED", "RETURNED"}:
            raise HTTPException(status_code=409, detail="Proposal cannot be cancelled from its current state")
        return self._transition(
            proposal,
            "CANCELLED",
            "project_proposal.cancelled",
            cancelled_at=utc_now(),
        )

    def gate_readiness(self, proposal_id: int) -> GateReadinessOut:
        proposal = self._proposal(proposal_id)
        data = self._gate_readiness(proposal)
        latest = self._latest_evaluation(proposal.id)
        sponsor = self.db.get(UserAccount, proposal.sponsor_user_id)
        owner = self.db.get(UserAccount, proposal.proposal_owner_user_id)
        return GateReadinessOut(
            project_proposal_id=proposal.id,
            status=("READY_FOR_STRATEGIC_GATE_DECISION" if not data["blockers"] else "GATE07B_REWORK_REQUIRED"),
            can_enter_strategic_gate=not data["blockers"],
            source_idea_id=proposal.source_idea_id,
            accepted_idea_evaluation_id=proposal.accepted_idea_evaluation_id,
            proposal_evaluation_id=latest.id if latest else None,
            proposal_score=latest.total_score if latest else None,
            owning_workspace_id=proposal.owning_workspace_id,
            target_portfolio_workspace_id=proposal.target_portfolio_workspace_id,
            strategic_objectives=list(proposal.strategic_objective_codes or []),
            sponsor={"id": sponsor.id, "name": sponsor.full_name} if sponsor else {},
            proposal_owner={"id": owner.id, "name": owner.full_name} if owner else {},
            blockers=data["blockers"],
            warnings=data["warnings"],
            readiness_hash=data["readiness_hash"],
        )

    def evaluations(self, proposal_id: int) -> list[ProjectProposalEvaluationOut]:
        proposal = self._proposal(proposal_id)
        return [ProjectProposalEvaluationOut.model_validate(item) for item in self._evaluations(proposal.id)]

    def history(self, proposal_id: int) -> list[ProposalHistoryItemOut]:
        self._proposal(proposal_id)
        rows = self.db.scalars(
            select(SecurityEvent)
            .where(
                SecurityEvent.tenant_id == self.tenant_id,
                SecurityEvent.target_type == "ProjectProposal",
                SecurityEvent.target_id == proposal_id,
            )
            .order_by(SecurityEvent.occurred_at)
        ).all()
        return [
            ProposalHistoryItemOut(
                event_type=item.event_type,
                outcome=item.outcome,
                actor_user_id=item.user_id,
                metadata=item.metadata_json,
                occurred_at=item.occurred_at,
            )
            for item in rows
        ]

    def admin_configurations(self) -> list[AdminConfiguration]:
        return list(
            self.db.scalars(
                select(AdminConfiguration)
                .where(
                    AdminConfiguration.tenant_id == self.tenant_id,
                    AdminConfiguration.kind.in_(
                        ["project_proposal_configuration", "project_proposal_evaluation_matrix"]
                    ),
                )
                .order_by(AdminConfiguration.kind, AdminConfiguration.code, AdminConfiguration.revision.desc())
            ).all()
        )

    def clone_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        source = self._configuration(configuration_id)
        self._check_configuration_version(source, expected_version)
        if source.status != "published":
            raise HTTPException(status_code=409, detail="Only a published Proposal configuration can be cloned")
        revision = (
            int(
                self.db.scalar(
                    select(func.max(AdminConfiguration.revision)).where(
                        AdminConfiguration.tenant_id == self.tenant_id,
                        AdminConfiguration.kind == source.kind,
                        AdminConfiguration.code == source.code,
                    )
                )
                or 0
            )
            + 1
        )
        clone = AdminConfiguration(
            tenant_id=self.tenant_id,
            kind=source.kind,
            code=source.code,
            name=source.name,
            description=source.description,
            status="draft",
            revision=revision,
            version=1,
            content_json=source.content_json,
            content_hash="",
            created_by_user_id=self.actor_id,
        )
        self.db.add(clone)
        self.db.flush()
        self._configuration_event(
            "project_proposal.configuration_cloned",
            clone,
            {"source_configuration_id": source.id},
        )
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
            raise HTTPException(status_code=409, detail="Published Proposal configuration is immutable")
        self._validate_configuration_content(record.kind, content)
        record.name = name.strip()
        record.description = description.strip()
        record.content_json = content
        record.version += 1
        record.updated_at = utc_now()
        self._configuration_event("project_proposal.configuration_updated", record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def publish_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        record = self._configuration(configuration_id)
        self._check_configuration_version(record, expected_version)
        if record.status != "draft":
            raise HTTPException(status_code=409, detail="Only a DRAFT Proposal configuration can be published")
        self._validate_configuration_content(record.kind, record.content_json)
        record.status = "published"
        record.content_hash = self._hash(record.content_json)
        record.published_at = utc_now()
        record.version += 1
        record.updated_at = utc_now()
        self._configuration_event("project_proposal.configuration_published", record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def _source_blockers(self, idea: Idea, config: dict) -> list[str]:
        blockers: list[str] = []
        if idea.state != "ACCEPTED":
            blockers.append("IDEA_NOT_ACCEPTED")
        if idea.accepted_evaluation_id is None or self._accepted_evaluation(idea, required=False) is None:
            blockers.append("NO_ACCEPTED_IDEA_EVALUATION")
        if not idea.strategic_objective_codes:
            blockers.append("NO_STRATEGIC_OBJECTIVE")
        maximum = int(config.get("max_active_proposals_per_idea", 1))
        active_count = int(
            self.db.scalar(
                select(func.count(ProjectProposal.id)).where(
                    ProjectProposal.tenant_id == self.tenant_id,
                    ProjectProposal.source_idea_id == idea.id,
                    ProjectProposal.status.not_in(INACTIVE_STATES),
                )
            )
            or 0
        )
        if maximum > 0 and active_count >= maximum:
            blockers.append("MAX_ACTIVE_PROPOSALS_REACHED")
        return blockers

    def _mapping_values(self, idea: Idea, evaluation: IdeaEvaluation | None) -> tuple[dict, dict]:
        source = {
            "idea_id": idea.id,
            "idea_number": idea.idea_number,
            "title": idea.title,
            "description": idea.description,
            "expected_benefit": idea.expected_benefit,
            "estimated_value": str(idea.estimated_value) if idea.estimated_value is not None else None,
            "currency_code": idea.currency_code,
            "owning_workspace_id": idea.owning_workspace_id,
            "target_portfolio_workspace_id": idea.target_portfolio_workspace_id,
            "strategic_objective_codes": list(idea.strategic_objective_codes or []),
            "owner_user_id": idea.owner_user_id,
            "requestor_user_id": idea.requestor_user_id,
            "accepted_evaluation_id": evaluation.id if evaluation else None,
            "accepted_evaluation_score": str(evaluation.total_score) if evaluation else None,
        }
        responsible = idea.owner_user_id or idea.requestor_user_id
        mapped = {
            "name": idea.title,
            "business_need": idea.description,
            "business_justification": idea.expected_benefit or idea.description,
            "project_objectives_json": [
                {"code": code, "statement": code.replace("-", " ").title()} for code in idea.strategic_objective_codes
            ],
            "preliminary_scope": idea.description,
            "expected_benefits": idea.expected_benefit or "Benefit definition required",
            "rom_cost": idea.estimated_value,
            "currency_code": idea.currency_code,
            "strategic_objective_codes": list(idea.strategic_objective_codes or []),
            "sponsor_user_id": responsible,
            "proposal_owner_user_id": responsible,
            "target_portfolio_workspace_id": idea.target_portfolio_workspace_id,
            "origin_idea_score": evaluation.total_score if evaluation else None,
        }
        return source, mapped

    def _required_field_blockers(self, proposal: ProjectProposal) -> list[str]:
        config = self._configuration_snapshot(proposal)
        blockers: list[str] = []
        for field in config.get("required_fields", []):
            value = getattr(proposal, str(field), None)
            if value is None or value == "" or value == []:
                blockers.append(str(field))
        return blockers

    def _review(self, proposal: ProjectProposal) -> dict:
        config = self._configuration_snapshot(proposal)
        valid_objectives = {item["code"] for item in self._objectives()}
        checks = {
            "business_need_complete": bool(proposal.business_need.strip()),
            "business_justification_complete": bool(proposal.business_justification.strip()),
            "objectives_defined": bool(proposal.project_objectives_json),
            "preliminary_scope_defined": bool(proposal.preliminary_scope.strip()),
            "expected_benefits_defined": bool(proposal.expected_benefits.strip()),
            "sponsor_valid": self._user_exists(proposal.sponsor_user_id),
            "proposal_owner_valid": self._user_exists(proposal.proposal_owner_user_id),
            "rom_cost_available_if_required": (
                proposal.rom_cost is not None or not bool(config.get("rom_cost_required", False))
            ),
            "duration_available_if_required": (
                proposal.preliminary_duration_days is not None or not bool(config.get("duration_required", False))
            ),
            "key_risks_identified": bool(proposal.key_risks_json),
            "strategic_objectives_valid": bool(proposal.strategic_objective_codes)
            and not (set(proposal.strategic_objective_codes) - valid_objectives),
            "target_portfolio_valid_if_required": self._target_portfolio_valid(
                proposal.target_portfolio_workspace_id,
                bool(config.get("target_portfolio_required", False)),
            ),
        }
        result: list[dict] = []
        for item in config.get("review_checklist", []):
            code = str(item.get("code"))
            passed = checks.get(code, False)
            result.append(
                {
                    "code": code,
                    "label": item.get("label", code),
                    "status": "PASS" if passed else "FAIL",
                    "blocking": bool(item.get("blocking", True)),
                    "evidence": self._review_evidence(code, proposal),
                }
            )
        return {"checks": result, "reviewed_by": self.actor_id, "reviewed_at": utc_now().isoformat()}

    def _gate_readiness(self, proposal: ProjectProposal) -> dict:
        blockers: list[str] = []
        warnings: list[str] = []
        if proposal.status not in {"EVALUATED", "READY_FOR_STRATEGIC_GATE"}:
            blockers.append("PROPOSAL_NOT_EVALUATED")
        latest = self._latest_evaluation(proposal.id)
        if latest is None:
            blockers.append("NO_PROPOSAL_EVALUATION")
        config = self._configuration_snapshot(proposal)
        minimum = Decimal(str(config.get("gate_readiness_policy", {}).get("minimum_score", 60)))
        if latest is not None and latest.total_score < minimum:
            blockers.append("PROPOSAL_SCORE_BELOW_GATE_THRESHOLD")
        blockers.extend(f"REQUIRED_FIELD:{item}" for item in self._required_field_blockers(proposal))
        review = self._review(proposal)
        blockers.extend(
            f"REVIEW:{item['code']}" for item in review["checks"] if item["blocking"] and item["status"] == "FAIL"
        )
        if proposal.rom_cost is None:
            warnings.append("ROM_COST_NOT_AVAILABLE")
        payload = {
            "project_proposal_id": proposal.id,
            "revision_version": proposal.revision_version,
            "source_idea_id": proposal.source_idea_id,
            "accepted_idea_evaluation_id": proposal.accepted_idea_evaluation_id,
            "proposal_evaluation_id": latest.id if latest else None,
            "proposal_score": str(latest.total_score) if latest else None,
            "blockers": sorted(set(blockers)),
            "warnings": sorted(set(warnings)),
        }
        return {**payload, "readiness_hash": self._hash(payload)}

    def _effective_configuration(
        self,
        workspace: EnterpriseWorkspace,
    ) -> tuple[dict, dict, list[EnterpriseWorkspace], AdminConfiguration]:
        selected = self._latest_configuration("project_proposal_configuration", "default")
        if selected is None:
            raise HTTPException(status_code=409, detail="No published Project Proposal configuration")
        path = self._workspace_path(workspace)
        for item in path:
            candidate = self._latest_configuration("project_proposal_configuration", f"workspace-{item.id}")
            if candidate is not None and (
                item.id == workspace.id or candidate.content_json.get("inherit_to_descendants", True)
            ):
                selected = candidate
        source = {
            "configuration_id": selected.id,
            "code": selected.code,
            "revision": selected.revision,
            "workspace_id": selected.content_json.get("workspace_id"),
        }
        return dict(selected.content_json), {"project_proposal_configuration": source}, path, selected

    def _effective_matrix(self, workspace: EnterpriseWorkspace) -> AdminConfiguration:
        selected = self._latest_configuration("project_proposal_evaluation_matrix", "default")
        if selected is None:
            raise HTTPException(status_code=409, detail="No published Project Proposal evaluation matrix")
        for item in self._workspace_path(workspace):
            candidate = self._latest_configuration(
                "project_proposal_evaluation_matrix",
                f"workspace-{item.id}",
            )
            if candidate is not None and (
                item.id == workspace.id or candidate.content_json.get("inherit_to_descendants", True)
            ):
                selected = candidate
        return selected

    def _configuration_snapshot(self, proposal: ProjectProposal) -> dict:
        return dict(proposal.configuration_snapshot_json.get("effective") or DEFAULT_PROPOSAL_CONFIGURATION)

    def _latest_configuration(self, kind: str, code: str) -> AdminConfiguration | None:
        return self.db.scalar(
            select(AdminConfiguration)
            .where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == kind,
                AdminConfiguration.code == code,
                AdminConfiguration.status == "published",
            )
            .order_by(AdminConfiguration.revision.desc())
            .limit(1)
        )

    def _seed_configuration(self, kind: str, code: str, name: str, content: dict) -> None:
        self.db.add(
            AdminConfiguration(
                tenant_id=self.tenant_id,
                kind=kind,
                code=code,
                name=name,
                description="Gate 07B governed default",
                status="published",
                revision=1,
                version=1,
                content_json=content,
                content_hash=self._hash(content),
                published_at=utc_now(),
                created_by_user_id=self.actor_id,
            )
        )

    def _configuration(self, configuration_id: int) -> AdminConfiguration:
        record = self.db.scalar(
            select(AdminConfiguration).where(
                AdminConfiguration.id == configuration_id,
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind.in_(["project_proposal_configuration", "project_proposal_evaluation_matrix"]),
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail="Project Proposal configuration not found")
        return record

    @staticmethod
    def _validate_configuration_content(kind: str, content: dict) -> None:
        if kind == "project_proposal_configuration":
            if not isinstance(content.get("required_fields"), list):
                raise HTTPException(status_code=422, detail="Proposal configuration requires required_fields")
            if not isinstance(content.get("review_checklist"), list):
                raise HTTPException(status_code=422, detail="Proposal configuration requires review_checklist")
            if int(content.get("max_active_proposals_per_idea", 1)) < 1:
                raise HTTPException(status_code=422, detail="max_active_proposals_per_idea must be at least 1")
            return
        criteria = content.get("criteria")
        if not isinstance(criteria, list) or not criteria:
            raise HTTPException(status_code=422, detail="Proposal evaluation matrix requires criteria")
        if round(sum(float(item.get("weight", 0)) for item in criteria), 4) != 100:
            raise HTTPException(status_code=422, detail="Proposal evaluation matrix weights must total 100")

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

    def _configuration_event(
        self,
        event_type: str,
        record: AdminConfiguration,
        metadata: dict | None = None,
    ) -> None:
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

    def _proposal(self, proposal_id: int, *, for_update: bool = False) -> ProjectProposal:
        statement = select(ProjectProposal).where(
            ProjectProposal.id == proposal_id,
            ProjectProposal.tenant_id == self.tenant_id,
        )
        if for_update:
            statement = statement.with_for_update()
        proposal = self.db.scalar(statement)
        if proposal is None or not self._can_access_proposal(proposal):
            raise HTTPException(status_code=404, detail="Project Proposal not found")
        return proposal

    def _idea(self, idea_id: int, *, for_update: bool = False) -> Idea:
        statement = select(Idea).where(Idea.id == idea_id, Idea.tenant_id == self.tenant_id)
        if for_update:
            statement = statement.with_for_update()
        idea = self.db.scalar(statement)
        if idea is None or not self._can_access_idea(idea):
            raise HTTPException(status_code=404, detail="Source Idea not found")
        return idea

    def _can_access_idea(self, idea: Idea) -> bool:
        return self.context.organization_wide or (
            idea.requestor_user_id == self.actor_id
            or idea.owner_user_id == self.actor_id
            or idea.owning_workspace_id in self.context.workspace_ids
        )

    def _can_access_proposal(self, proposal: ProjectProposal) -> bool:
        return self.context.organization_wide or (
            proposal.created_by == self.actor_id
            or proposal.proposal_owner_user_id == self.actor_id
            or proposal.owning_workspace_id in self.context.workspace_ids
        )

    def _accepted_evaluation(self, idea: Idea, *, required: bool = True) -> IdeaEvaluation | None:
        evaluation = (
            self.db.scalar(
                select(IdeaEvaluation).where(
                    IdeaEvaluation.id == idea.accepted_evaluation_id,
                    IdeaEvaluation.idea_id == idea.id,
                    IdeaEvaluation.tenant_id == self.tenant_id,
                )
            )
            if idea.accepted_evaluation_id
            else None
        )
        if evaluation is None and required:
            raise HTTPException(status_code=409, detail="Accepted Idea evaluation is missing")
        return evaluation

    def _workspace(self, workspace_id: int | None) -> EnterpriseWorkspace:
        workspace = self.db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.id == workspace_id,
                EnterpriseWorkspace.tenant_id == self.tenant_id,
                EnterpriseWorkspace.status.in_(["active", "draft"]),
            )
        )
        if workspace is None:
            raise HTTPException(status_code=404, detail="Workspace not found")
        return workspace

    def _owning_workspace(self, workspace_id: int) -> EnterpriseWorkspace:
        workspace = self._workspace(workspace_id)
        if workspace.workspace_type_code not in OWNING_TYPES:
            raise HTTPException(
                status_code=422,
                detail="Project Proposals can only be owned by Enterprise, Business Unit or Portfolio",
            )
        if not self.context.organization_wide and workspace.id not in self.context.workspace_ids:
            raise HTTPException(status_code=404, detail="Owning Workspace not found or not authorized")
        return workspace

    def _validate_workspace(self, owning_workspace_id: int, target_portfolio_id: int | None) -> None:
        self._owning_workspace(owning_workspace_id)
        if target_portfolio_id is not None and self._workspace(target_portfolio_id).workspace_type_code != "portfolio":
            raise HTTPException(status_code=422, detail="Target Workspace must be a Portfolio")

    def _target_portfolio_valid(self, workspace_id: int | None, required: bool) -> bool:
        if workspace_id is None:
            return not required
        try:
            return self._workspace(workspace_id).workspace_type_code == "portfolio"
        except HTTPException:
            return False

    def _authorized_workspaces(self) -> list[EnterpriseWorkspace]:
        statement = select(EnterpriseWorkspace).where(
            EnterpriseWorkspace.tenant_id == self.tenant_id,
            EnterpriseWorkspace.workspace_type_code.in_(OWNING_TYPES),
            EnterpriseWorkspace.status.in_(["active", "draft"]),
        )
        if not self.context.organization_wide:
            statement = statement.where(EnterpriseWorkspace.id.in_(list(self.context.workspace_ids)))
        return list(self.db.scalars(statement.order_by(EnterpriseWorkspace.sort_order, EnterpriseWorkspace.name)).all())

    def _workspace_path(self, workspace: EnterpriseWorkspace) -> list[EnterpriseWorkspace]:
        path: list[EnterpriseWorkspace] = []
        cursor: EnterpriseWorkspace | None = workspace
        seen: set[int] = set()
        while cursor is not None and cursor.id not in seen:
            seen.add(cursor.id)
            path.append(cursor)
            cursor = self._workspace(cursor.parent_id) if cursor.parent_id else None
        return list(reversed(path))

    def _objectives(self) -> list[dict]:
        rows = self.db.scalars(
            select(EnterpriseStrategicObjective)
            .where(
                EnterpriseStrategicObjective.tenant_id == self.tenant_id,
                EnterpriseStrategicObjective.active.is_(True),
            )
            .order_by(EnterpriseStrategicObjective.name)
        ).all()
        return [{"code": item.code, "label": item.name} for item in rows]

    def _users(self) -> list[UserAccount]:
        return list(
            self.db.scalars(
                select(UserAccount)
                .where(UserAccount.tenant_id == self.tenant_id, UserAccount.status == "active")
                .order_by(UserAccount.full_name)
            ).all()
        )

    def _user_exists(self, user_id: int) -> bool:
        return (
            self.db.scalar(
                select(UserAccount.id).where(
                    UserAccount.id == user_id,
                    UserAccount.tenant_id == self.tenant_id,
                    UserAccount.status == "active",
                )
            )
            is not None
        )

    def _validate_user(self, user_id: int, permission: str, workspace_id: int) -> None:
        if not self._user_exists(user_id):
            raise HTTPException(status_code=422, detail="User must be active in the current tenant")
        if self.context.organization_wide:
            return
        assignment = self.db.scalar(
            select(SecurityAccessAssignment.id)
            .join(SecurityRolePermission, SecurityRolePermission.role_id == SecurityAccessAssignment.role_id)
            .join(PermissionCatalog, PermissionCatalog.id == SecurityRolePermission.permission_id)
            .where(
                SecurityAccessAssignment.tenant_id == self.tenant_id,
                SecurityAccessAssignment.user_id == user_id,
                SecurityAccessAssignment.status == "active",
                PermissionCatalog.key == permission,
                (SecurityAccessAssignment.scope_type == "organization")
                | (SecurityAccessAssignment.workspace_id == workspace_id),
            )
            .limit(1)
        )
        if assignment is None:
            raise HTTPException(status_code=422, detail=f"User lacks {permission} in the owning Workspace scope")

    def _sequence(self, *, required: bool = True) -> AdminNumberSequence | None:
        sequence = self.db.scalar(
            select(AdminNumberSequence).where(
                AdminNumberSequence.tenant_id == self.tenant_id,
                AdminNumberSequence.rule_code == PROPOSAL_NUMBER_RULE,
                AdminNumberSequence.scope_key == "tenant",
            )
        )
        if sequence is None and required:
            raise HTTPException(status_code=409, detail="Project Proposal numbering is not initialized")
        return sequence

    def _reserve_number(self) -> str:
        result = self.db.execute(
            update(AdminNumberSequence)
            .where(
                AdminNumberSequence.tenant_id == self.tenant_id,
                AdminNumberSequence.rule_code == PROPOSAL_NUMBER_RULE,
                AdminNumberSequence.scope_key == "tenant",
            )
            .values(
                next_value=AdminNumberSequence.next_value + 1,
                version=AdminNumberSequence.version + 1,
                updated_at=utc_now(),
            )
            .returning(AdminNumberSequence.next_value)
        ).scalar_one()
        return f"PROP-{int(result) - 1:05d}"

    def _latest_evaluation(self, proposal_id: int) -> ProjectProposalEvaluation | None:
        return self.db.scalar(
            select(ProjectProposalEvaluation)
            .where(
                ProjectProposalEvaluation.tenant_id == self.tenant_id,
                ProjectProposalEvaluation.project_proposal_id == proposal_id,
            )
            .order_by(ProjectProposalEvaluation.evaluation_version.desc())
            .limit(1)
        )

    def _evaluations(self, proposal_id: int) -> list[ProjectProposalEvaluation]:
        return list(
            self.db.scalars(
                select(ProjectProposalEvaluation)
                .where(
                    ProjectProposalEvaluation.tenant_id == self.tenant_id,
                    ProjectProposalEvaluation.project_proposal_id == proposal_id,
                )
                .order_by(ProjectProposalEvaluation.evaluation_version)
            ).all()
        )

    def _transition(
        self,
        proposal: ProjectProposal,
        target: str,
        event_type: str,
        *,
        metadata: dict | None = None,
        **timestamps,
    ) -> ProjectProposalOut:
        before = proposal.status
        proposal.status = target
        for key, value in timestamps.items():
            setattr(proposal, key, value)
        self._touch(proposal)
        self._event(event_type, proposal, before, target, metadata)
        return self._commit(proposal)

    def _touch(self, proposal: ProjectProposal) -> None:
        proposal.updated_by = self.actor_id
        proposal.updated_at = utc_now()

    @staticmethod
    def _check_version(proposal: ProjectProposal, expected: int) -> None:
        if proposal.revision_version != expected:
            raise HTTPException(
                status_code=412,
                detail={
                    "reason": "ETAG_MISMATCH",
                    "current_version": proposal.revision_version,
                    "expected_version": expected,
                },
            )

    def _commit(self, proposal: ProjectProposal) -> ProjectProposalOut:
        self.db.commit()
        self.db.refresh(proposal)
        return self._out(proposal)

    def _event(
        self,
        event_type: str,
        proposal: ProjectProposal,
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
                target_type="ProjectProposal",
                target_id=proposal.id,
                metadata_json={
                    "state_before": state_before,
                    "state_after": state_after,
                    **(metadata or {}),
                },
            )
        )

    def _out(self, proposal: ProjectProposal) -> ProjectProposalOut:
        idea = self._idea(proposal.source_idea_id)
        workspace = self._workspace(proposal.owning_workspace_id)
        sponsor = self.db.get(UserAccount, proposal.sponsor_user_id)
        owner = self.db.get(UserAccount, proposal.proposal_owner_user_id)
        evaluations = self._evaluations(proposal.id)
        return ProjectProposalOut(
            id=proposal.id,
            proposal_number=proposal.proposal_number,
            source_idea_id=proposal.source_idea_id,
            source_idea_number=idea.idea_number,
            source_idea_title=idea.title,
            accepted_idea_evaluation_id=proposal.accepted_idea_evaluation_id,
            owning_workspace_id=proposal.owning_workspace_id,
            owning_workspace_name=workspace.name,
            target_portfolio_workspace_id=proposal.target_portfolio_workspace_id,
            name=proposal.name,
            business_need=proposal.business_need,
            business_justification=proposal.business_justification,
            project_objectives=list(proposal.project_objectives_json or []),
            preliminary_scope=proposal.preliminary_scope,
            out_of_scope=proposal.out_of_scope,
            expected_benefits=proposal.expected_benefits,
            benefit_owner_user_id=proposal.benefit_owner_user_id,
            rom_cost=proposal.rom_cost,
            currency_code=proposal.currency_code,
            preliminary_duration_days=proposal.preliminary_duration_days,
            target_start_date=proposal.target_start_date,
            target_finish_date=proposal.target_finish_date,
            key_risks=list(proposal.key_risks_json or []),
            assumptions=list(proposal.assumptions_json or []),
            constraints=list(proposal.constraints_json or []),
            strategic_objective_codes=list(proposal.strategic_objective_codes or []),
            sponsor_user_id=proposal.sponsor_user_id,
            sponsor_name=sponsor.full_name if sponsor else "Unknown",
            proposal_owner_user_id=proposal.proposal_owner_user_id,
            proposal_owner_name=owner.full_name if owner else "Unknown",
            origin_idea_score=proposal.origin_idea_score,
            status=ProjectProposalState(proposal.status),
            mapping_configuration_id=proposal.mapping_configuration_id,
            mapping_revision=proposal.mapping_revision,
            mapping_hash=proposal.mapping_hash,
            source_values_snapshot=dict(proposal.source_values_snapshot_json or {}),
            mapped_values_snapshot=dict(proposal.mapped_values_snapshot_json or {}),
            review=dict(proposal.review_snapshot_json or {}),
            attachment_refs=list(proposal.attachment_refs_json or []),
            return_reason=proposal.return_reason,
            returned_stage=proposal.returned_stage,
            evaluations=[ProjectProposalEvaluationOut.model_validate(item) for item in evaluations],
            allowed_actions=self._allowed_actions(proposal),
            revision_version=proposal.revision_version,
            created_at=proposal.created_at,
            updated_at=proposal.updated_at,
        )

    def _allowed_actions(self, proposal: ProjectProposal) -> list[str]:
        admin = self.context.organization_wide or "organization_admin" in self.context.role_codes
        roles = self.context.role_codes
        actions: list[str] = []
        if proposal.status in {"DRAFT", "RETURNED"} and (
            admin or proposal.created_by == self.actor_id or proposal.proposal_owner_user_id == self.actor_id
        ):
            actions += ["edit", "submit", "cancel"]
        if proposal.status in {"SUBMITTED", "UNDER_REVIEW"} and (admin or "proposal_reviewer" in roles):
            actions += ["start_review" if proposal.status == "SUBMITTED" else "start_evaluation", "return"]
        if proposal.status == "UNDER_EVALUATION" and (
            admin or proposal.proposal_owner_user_id == self.actor_id or "proposal_evaluator" in roles
        ):
            actions += ["complete_evaluation", "return"]
        if proposal.status == "EVALUATED" and (admin or "proposal_reviewer" in roles):
            actions += ["mark_gate_ready", "return"]
        return actions

    @staticmethod
    def _payload_values(payload: ProjectProposalUpdate) -> dict:
        return {
            "name": payload.name,
            "business_need": payload.business_need,
            "business_justification": payload.business_justification,
            "project_objectives_json": payload.project_objectives,
            "preliminary_scope": payload.preliminary_scope,
            "out_of_scope": payload.out_of_scope,
            "expected_benefits": payload.expected_benefits,
            "benefit_owner_user_id": payload.benefit_owner_user_id,
            "rom_cost": payload.rom_cost,
            "currency_code": payload.currency_code.upper(),
            "preliminary_duration_days": payload.preliminary_duration_days,
            "target_start_date": payload.target_start_date,
            "target_finish_date": payload.target_finish_date,
            "key_risks_json": payload.key_risks,
            "assumptions_json": payload.assumptions,
            "constraints_json": payload.constraints,
            "strategic_objective_codes": payload.strategic_objective_codes,
            "target_portfolio_workspace_id": payload.target_portfolio_workspace_id,
            "sponsor_user_id": payload.sponsor_user_id,
            "proposal_owner_user_id": payload.proposal_owner_user_id,
            "attachment_refs_json": payload.attachment_refs,
        }

    @staticmethod
    def _review_evidence(code: str, proposal: ProjectProposal) -> str:
        evidence = {
            "business_need_complete": proposal.business_need,
            "business_justification_complete": proposal.business_justification,
            "objectives_defined": f"{len(proposal.project_objectives_json or [])} objective(s)",
            "preliminary_scope_defined": proposal.preliminary_scope,
            "expected_benefits_defined": proposal.expected_benefits,
            "sponsor_valid": f"user:{proposal.sponsor_user_id}",
            "proposal_owner_valid": f"user:{proposal.proposal_owner_user_id}",
            "rom_cost_available_if_required": str(proposal.rom_cost or "optional"),
            "duration_available_if_required": str(proposal.preliminary_duration_days or "optional"),
            "key_risks_identified": f"{len(proposal.key_risks_json or [])} risk(s)",
            "strategic_objectives_valid": ", ".join(proposal.strategic_objective_codes or []),
            "target_portfolio_valid_if_required": str(proposal.target_portfolio_workspace_id or "optional"),
        }
        return evidence.get(code, "")[:500]

    @staticmethod
    def _workspace_option(workspace: EnterpriseWorkspace) -> dict:
        return {
            "id": workspace.id,
            "code": workspace.code,
            "name": workspace.name,
            "workspace_type_code": workspace.workspace_type_code,
            "status": workspace.status,
            "parent_id": workspace.parent_id,
        }

    @staticmethod
    def _hash(value: object) -> str:
        return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()

    @staticmethod
    def _json_safe(value: object) -> dict:
        return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))
