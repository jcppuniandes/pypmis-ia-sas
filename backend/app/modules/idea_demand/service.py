"""Application service for the single governed Idea lifecycle (Gate 07A)."""

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
from app.modules.idea_demand.schemas import (
    DecisionIn,
    EvaluationIn,
    IdeaConfigurationPreviewOut,
    IdeaCreate,
    IdeaEvaluationOut,
    IdeaHistoryItemOut,
    IdeaOptionsOut,
    IdeaOut,
    IdeaPayload,
    IdeaState,
    IdeaUpdate,
    OwnerAssignmentIn,
    ProposalReadinessOut,
    RoutingIn,
    ScreeningIn,
)

IDEA_NUMBER_RULE = "idea"
OWNING_TYPES = frozenset({"enterprise", "business-unit", "portfolio"})
FINAL_STATES = frozenset({"ACCEPTED", "REJECTED", "CANCELLED", "ARCHIVED"})
PRIVILEGED_ROLES = frozenset(
    {"organization_admin", "idea_intake_reviewer", "idea_owner", "idea_decision_maker", "idea_configuration_admin"}
)

DEFAULT_IDEA_CONFIGURATION = {
    "workspace_id": None,
    "inherit_to_descendants": True,
    "idea_types": [
        {"code": "improvement", "label": "Improvement"},
        {"code": "investment", "label": "Investment"},
        {"code": "innovation", "label": "Innovation"},
        {"code": "compliance", "label": "Compliance"},
    ],
    "categories": [
        {"code": "growth", "label": "Growth"},
        {"code": "efficiency", "label": "Efficiency"},
        {"code": "risk", "label": "Risk reduction"},
        {"code": "sustainability", "label": "Sustainability"},
    ],
    "objective_selection": "multiple",
    "screening_checklist": [
        {"code": "complete_description", "label": "Description is complete", "blocking": True},
        {"code": "benefit_identified", "label": "Expected benefit is identified", "blocking": True},
        {"code": "workspace_confirmed", "label": "Owning Workspace is confirmed", "blocking": True},
        {"code": "no_duplicate", "label": "No material duplicate was found", "blocking": True},
    ],
    "routing_rules": [{"code": "default", "label": "Default intake route"}],
    "required_fields": ["title", "description", "idea_type", "category", "owning_workspace_id"],
    "proposal_mapping": {
        "name": "title",
        "description": "description",
        "business_case": "expected_benefit",
        "estimated_budget": "estimated_value",
        "parent_workspace_id": "target_portfolio_workspace_id|owning_workspace_id",
        "strategic_objectives": "strategic_objective_codes",
    },
}

DEFAULT_MATRIX = {
    "workspace_id": None,
    "inherit_to_descendants": True,
    "scale": {"min": 1, "max": 5},
    "criteria": [
        {"code": "strategic_alignment", "label": "Strategic alignment", "weight": 30},
        {"code": "value", "label": "Expected value", "weight": 25},
        {"code": "feasibility", "label": "Feasibility", "weight": 20},
        {"code": "risk", "label": "Risk response", "weight": 15},
        {"code": "urgency", "label": "Urgency", "weight": 10},
    ],
    "recommendation_threshold": 70,
}


class IdeaDemandService:
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
        """Install reusable defaults and numbering idempotently; never create an Idea."""
        ensure_enterprise_permissions(self.db, self.tenant_id, self.actor_id)
        if self._latest_configuration("idea_demand_configuration", "default") is None:
            self._seed_configuration(
                "idea_demand_configuration", "default", "Default Idea Lifecycle", DEFAULT_IDEA_CONFIGURATION
            )
        if self._latest_configuration("idea_evaluation_matrix", "default") is None:
            self._seed_configuration("idea_evaluation_matrix", "default", "Default Idea Evaluation Matrix", DEFAULT_MATRIX)
        sequence = self.db.scalar(
            select(AdminNumberSequence).where(
                AdminNumberSequence.tenant_id == self.tenant_id,
                AdminNumberSequence.rule_code == IDEA_NUMBER_RULE,
                AdminNumberSequence.scope_key == "tenant",
            )
        )
        if sequence is None:
            self.db.add(
                AdminNumberSequence(
                    tenant_id=self.tenant_id,
                    rule_code=IDEA_NUMBER_RULE,
                    scope_key="tenant",
                    next_value=1,
                    version=1,
                )
            )
        self.db.commit()

    def options(self, owning_workspace_id: int | None = None) -> IdeaOptionsOut:
        workspaces = self._authorized_workspaces()
        workspace = next((item for item in workspaces if item.id == owning_workspace_id), None)
        if owning_workspace_id is not None and workspace is None:
            raise HTTPException(status_code=404, detail="Owning Workspace not found or not authorized")
        effective, sources, _path = self._effective_configuration(workspace)
        sequence = self._sequence()
        objectives = list(
            self.db.scalars(
                select(EnterpriseStrategicObjective)
                .where(
                    EnterpriseStrategicObjective.tenant_id == self.tenant_id,
                    EnterpriseStrategicObjective.active.is_(True),
                )
                .order_by(EnterpriseStrategicObjective.name)
            ).all()
        )
        users = list(
            self.db.scalars(
                select(UserAccount)
                .where(UserAccount.tenant_id == self.tenant_id, UserAccount.status == "active")
                .order_by(UserAccount.full_name)
            ).all()
        )
        return IdeaOptionsOut(
            number_preview=f"IDEA-{sequence.next_value:05d}",
            owning_workspaces=[self._workspace_option(item) for item in workspaces],
            target_portfolios=[self._workspace_option(item) for item in workspaces if item.workspace_type_code == "portfolio"],
            strategic_objectives=[{"code": item.code, "label": item.name} for item in objectives],
            users=[{"id": item.id, "name": item.full_name, "email": item.email} for item in users],
            idea_types=list(effective.get("idea_types", [])),
            categories=list(effective.get("categories", [])),
            screening_checklist=list(effective.get("screening_checklist", [])),
            objective_selection=str(effective.get("objective_selection", "multiple")),
            configuration_source=sources,
        )

    def configuration_preview(self, owning_workspace_id: int) -> IdeaConfigurationPreviewOut:
        workspace = self._owning_workspace(owning_workspace_id)
        effective, sources, path = self._effective_configuration(workspace)
        return IdeaConfigurationPreviewOut(
            owning_workspace_id=workspace.id,
            path=[self._workspace_option(item) for item in path],
            effective=effective,
            sources=sources,
        )

    def create(self, payload: IdeaCreate) -> IdeaOut:
        workspace, config, sources = self._validate_payload(payload)
        idea = Idea(
            tenant_id=self.tenant_id,
            idea_number=self._reserve_number(),
            requestor_user_id=self.actor_id,
            state=IdeaState.DRAFT,
            configuration_snapshot_json={"effective": config, "sources": sources},
            revision_version=1,
            last_modified_by_user_id=self.actor_id,
            **self._payload_values(payload),
        )
        self.db.add(idea)
        self.db.flush()
        self._event("idea.created", idea, None, "DRAFT", {"owning_workspace_id": workspace.id})
        self.db.commit()
        self.db.refresh(idea)
        return self._out(idea)

    def list(
        self,
        *,
        state: str = "",
        search: str = "",
        owning_workspace_id: int | None = None,
        queue: str = "",
    ) -> list[IdeaOut]:
        statement = select(Idea).where(Idea.tenant_id == self.tenant_id)
        if not self.context.organization_wide:
            allowed = list(self.context.workspace_ids)
            statement = statement.where(
                (Idea.requestor_user_id == self.actor_id)
                | (Idea.owner_user_id == self.actor_id)
                | (Idea.owning_workspace_id.in_(allowed) if allowed else False)
            )
        elif not (self.context.role_codes & PRIVILEGED_ROLES):
            statement = statement.where(Idea.requestor_user_id == self.actor_id)
        if state.strip():
            statement = statement.where(Idea.state == state.strip().upper())
        if owning_workspace_id:
            statement = statement.where(Idea.owning_workspace_id == owning_workspace_id)
        if search.strip():
            term = f"%{search.strip().lower()}%"
            statement = statement.where(
                func.lower(Idea.idea_number).like(term) | func.lower(Idea.title).like(term)
            )
        queues = {
            "mine": Idea.requestor_user_id == self.actor_id,
            "screen": Idea.state.in_(["SUBMITTED", "SCREENING"]),
            "assigned": Idea.owner_user_id == self.actor_id,
            "evaluate": (Idea.owner_user_id == self.actor_id) & Idea.state.in_(["OWNER_ASSIGNED", "UNDER_EVALUATION"]),
            "decision": Idea.state == "EVALUATED",
        }
        if queue in queues:
            statement = statement.where(queues[queue])
        rows = self.db.scalars(statement.order_by(Idea.updated_at.desc())).all()
        return [self._out(item) for item in rows]

    def get(self, idea_id: int) -> IdeaOut:
        return self._out(self._idea(idea_id))

    def update(self, idea_id: int, payload: IdeaUpdate, expected_version: int) -> IdeaOut:
        idea = self._idea(idea_id)
        self._check_version(idea, expected_version)
        if idea.requestor_user_id != self.actor_id and not self.context.organization_wide:
            raise HTTPException(status_code=403, detail="Only the requestor can edit this Idea")
        if idea.state not in {"DRAFT", "RETURNED"}:
            raise HTTPException(status_code=409, detail="Only DRAFT or RETURNED Ideas can be edited")
        _workspace, config, sources = self._validate_payload(payload)
        before = idea.state
        for key, value in self._payload_values(payload).items():
            setattr(idea, key, value)
        idea.state = "DRAFT"
        idea.configuration_snapshot_json = {"effective": config, "sources": sources}
        self._touch(idea)
        self._event("idea.updated", idea, before, idea.state)
        return self._commit(idea)

    def submit(self, idea_id: int, expected_version: int) -> IdeaOut:
        idea = self._idea(idea_id)
        if idea.state == "SUBMITTED":
            return self._out(idea)
        self._check_version(idea, expected_version)
        if idea.state not in {"DRAFT", "RETURNED"}:
            raise HTTPException(status_code=409, detail="Idea cannot be submitted from its current state")
        self._validate_existing(idea)
        return self._transition(idea, "SUBMITTED", "idea.submitted", submitted_at=utc_now())

    def screen(self, idea_id: int, payload: ScreeningIn, expected_version: int) -> IdeaOut:
        idea = self._idea(idea_id)
        self._check_version(idea, expected_version)
        if idea.state not in {"SUBMITTED", "SCREENING"}:
            raise HTTPException(status_code=409, detail="Only submitted Ideas can be screened")
        before = idea.state
        config = self._configuration_snapshot(idea)
        known = {str(item.get("code")) for item in config.get("screening_checklist", [])}
        if set(payload.checklist) - known:
            raise HTTPException(status_code=422, detail="Screening checklist contains unknown items")
        idea.state = "SCREENING"
        idea.screening_json = {"checklist": payload.checklist, "notes": payload.notes, "screened_by": self.actor_id}
        idea.screened_at = utc_now()
        self._touch(idea)
        self._event("idea.screened", idea, before, idea.state, {"checklist": payload.checklist})
        return self._commit(idea)

    def route(self, idea_id: int, payload: RoutingIn, expected_version: int) -> IdeaOut:
        idea = self._idea(idea_id)
        self._check_version(idea, expected_version)
        if idea.state != "SCREENING":
            raise HTTPException(status_code=409, detail="Routing requires SCREENING state")
        self._require_screening_complete(idea)
        if payload.target_portfolio_workspace_id is not None:
            portfolio = self._workspace(payload.target_portfolio_workspace_id)
            if portfolio.workspace_type_code != "portfolio":
                raise HTTPException(status_code=422, detail="Target Workspace must be a Portfolio")
            idea.target_portfolio_workspace_id = portfolio.id
        idea.routing_json = {
            "route_code": payload.route_code,
            "notes": payload.notes,
            "routed_by": self.actor_id,
            "routed_at": utc_now().isoformat(),
        }
        self._touch(idea)
        self._event("idea.routed", idea, idea.state, idea.state, idea.routing_json)
        return self._commit(idea)

    def assign_owner(self, idea_id: int, payload: OwnerAssignmentIn, expected_version: int) -> IdeaOut:
        idea = self._idea(idea_id)
        if idea.state == "OWNER_ASSIGNED" and idea.owner_user_id == payload.owner_user_id:
            return self._out(idea)
        self._check_version(idea, expected_version)
        if idea.state != "SCREENING":
            raise HTTPException(status_code=409, detail="Owner assignment requires SCREENING state")
        self._require_screening_complete(idea)
        if not idea.routing_json:
            raise HTTPException(status_code=422, detail="Route the Idea before assigning its owner")
        self._validate_owner(payload.owner_user_id, idea.owning_workspace_id)
        idea.owner_user_id = payload.owner_user_id
        return self._transition(
            idea,
            "OWNER_ASSIGNED",
            "idea.owner_assigned",
            metadata={"owner_user_id": payload.owner_user_id},
        )

    def start_evaluation(self, idea_id: int, expected_version: int) -> IdeaOut:
        idea = self._idea(idea_id)
        if idea.state == "UNDER_EVALUATION":
            return self._out(idea)
        self._check_version(idea, expected_version)
        if idea.state != "OWNER_ASSIGNED":
            raise HTTPException(status_code=409, detail="Evaluation requires an assigned owner")
        if idea.owner_user_id != self.actor_id and not self.context.organization_wide:
            raise HTTPException(status_code=403, detail="Only the assigned owner can evaluate this Idea")
        return self._transition(idea, "UNDER_EVALUATION", "idea.evaluation_started")

    def complete_evaluation(self, idea_id: int, payload: EvaluationIn, expected_version: int) -> IdeaOut:
        idea = self._idea(idea_id)
        if idea.state == "EVALUATED":
            return self._out(idea)
        self._check_version(idea, expected_version)
        if idea.state != "UNDER_EVALUATION":
            raise HTTPException(status_code=409, detail="Start evaluation before completing it")
        if idea.owner_user_id != self.actor_id and not self.context.organization_wide:
            raise HTTPException(status_code=403, detail="Only the assigned owner can complete evaluation")
        matrix, _sources, _path = self._effective_matrix(self._workspace(idea.owning_workspace_id))
        criteria = {str(item["code"]): item for item in matrix.content_json["criteria"]}
        ratings = {str(item.get("criterion_code")): item for item in payload.ratings}
        if set(ratings) != set(criteria):
            raise HTTPException(status_code=422, detail="Every matrix criterion must have exactly one rating")
        scale = matrix.content_json.get("scale", {"min": 1, "max": 5})
        maximum = Decimal(str(scale.get("max", 5)))
        minimum = Decimal(str(scale.get("min", 1)))
        total = Decimal("0")
        normalized_ratings: list[dict] = []
        for code, criterion in criteria.items():
            rating = Decimal(str(ratings[code].get("rating", 0)))
            if rating < minimum or rating > maximum:
                raise HTTPException(status_code=422, detail=f"Rating for {code} is outside the configured scale")
            weight = Decimal(str(criterion.get("weight", 0)))
            total += rating / maximum * weight
            normalized_ratings.append(
                {"criterion_code": code, "rating": float(rating), "weight": float(weight), "comment": ratings[code].get("comment", "")}
            )
        version = int(
            self.db.scalar(
                select(func.coalesce(func.max(IdeaEvaluation.evaluation_version), 0)).where(
                    IdeaEvaluation.tenant_id == self.tenant_id, IdeaEvaluation.idea_id == idea.id
                )
            )
            or 0
        ) + 1
        threshold = Decimal(str(matrix.content_json.get("recommendation_threshold", 70)))
        evaluation = IdeaEvaluation(
            tenant_id=self.tenant_id,
            idea_id=idea.id,
            evaluation_version=version,
            matrix_configuration_id=matrix.id,
            matrix_revision=matrix.revision,
            matrix_snapshot_json=matrix.content_json,
            ratings_json=normalized_ratings,
            total_score=total.quantize(Decimal("0.0001")),
            result="RECOMMENDED" if total >= threshold else "NOT_RECOMMENDED",
            comments=payload.comments,
            evaluator_user_id=self.actor_id,
        )
        self.db.add(evaluation)
        self.db.flush()
        idea.accepted_evaluation_id = evaluation.id
        idea.evaluated_at = utc_now()
        before = idea.state
        idea.state = "EVALUATED"
        self._touch(idea)
        self._event(
            "idea.evaluated",
            idea,
            before,
            idea.state,
            {"evaluation_id": evaluation.id, "evaluation_version": version, "score": str(total)},
        )
        return self._commit(idea)

    def decide(self, idea_id: int, payload: DecisionIn, expected_version: int, *, accept: bool) -> IdeaOut:
        idea = self._idea(idea_id)
        target = "ACCEPTED" if accept else "REJECTED"
        if idea.state == target:
            return self._out(idea)
        self._check_version(idea, expected_version)
        if idea.state != "EVALUATED":
            raise HTTPException(status_code=409, detail="Only an evaluated Idea can be decided")
        idea.decision_reason = payload.reason
        idea.decision_by_user_id = self.actor_id
        idea.decided_at = utc_now()
        if accept:
            readiness = self._readiness(idea, assume_accepted=True)
            idea.readiness_json = readiness
        return self._transition(idea, target, f"idea.{target.lower()}", metadata={"reason": payload.reason})

    def return_idea(self, idea_id: int, payload: DecisionIn, expected_version: int) -> IdeaOut:
        idea = self._idea(idea_id)
        if idea.state == "RETURNED":
            return self._out(idea)
        self._check_version(idea, expected_version)
        if idea.state not in {"SUBMITTED", "SCREENING", "OWNER_ASSIGNED", "UNDER_EVALUATION", "EVALUATED"}:
            raise HTTPException(status_code=409, detail="Idea cannot be returned from its current state")
        idea.decision_reason = payload.reason
        return self._transition(idea, "RETURNED", "idea.returned", metadata={"reason": payload.reason})

    def cancel(self, idea_id: int, expected_version: int) -> IdeaOut:
        idea = self._idea(idea_id)
        if idea.state == "CANCELLED":
            return self._out(idea)
        self._check_version(idea, expected_version)
        if idea.requestor_user_id != self.actor_id and not self.context.organization_wide:
            raise HTTPException(status_code=403, detail="Only the requestor can cancel this Idea")
        if idea.state in FINAL_STATES or idea.state in {"UNDER_EVALUATION", "EVALUATED"}:
            raise HTTPException(status_code=409, detail="Idea cannot be cancelled from its current state")
        return self._transition(idea, "CANCELLED", "idea.cancelled")

    def readiness(self, idea_id: int) -> ProposalReadinessOut:
        idea = self._idea(idea_id)
        readiness = self._readiness(idea)
        return ProposalReadinessOut(
            idea_id=idea.id,
            idea_number=idea.idea_number,
            ready=not readiness["blocking_issues"],
            status="READY_FOR_PROJECT_PROPOSAL" if not readiness["blocking_issues"] else "GATE07A_REWORK_REQUIRED",
            blocking_issues=readiness["blocking_issues"],
            mapping_preview=readiness["mapping_preview"],
            can_create_project_proposal=False,
        )

    def history(self, idea_id: int) -> list[IdeaHistoryItemOut]:
        self._idea(idea_id)
        rows = self.db.scalars(
            select(SecurityEvent)
            .where(
                SecurityEvent.tenant_id == self.tenant_id,
                SecurityEvent.target_type == "Idea",
                SecurityEvent.target_id == idea_id,
            )
            .order_by(SecurityEvent.occurred_at)
        ).all()
        return [
            IdeaHistoryItemOut(
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
                    AdminConfiguration.kind.in_(["idea_demand_configuration", "idea_evaluation_matrix"]),
                )
                .order_by(AdminConfiguration.kind, AdminConfiguration.code, AdminConfiguration.revision.desc())
            ).all()
        )

    def clone_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        source = self._idea_configuration(configuration_id)
        self._check_configuration_version(source, expected_version)
        if source.status != "published":
            raise HTTPException(status_code=409, detail="Only a published Idea configuration can be cloned")
        revision = int(
            self.db.scalar(
                select(func.max(AdminConfiguration.revision)).where(
                    AdminConfiguration.tenant_id == self.tenant_id,
                    AdminConfiguration.kind == source.kind,
                    AdminConfiguration.code == source.code,
                )
            )
            or 0
        ) + 1
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
        self._configuration_event("idea.configuration_cloned", clone, {"source_configuration_id": source.id})
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
        record = self._idea_configuration(configuration_id)
        self._check_configuration_version(record, expected_version)
        if record.status != "draft":
            raise HTTPException(status_code=409, detail="Published Idea configuration is immutable; clone it first")
        self._validate_configuration_content(record.kind, content)
        record.name = name.strip()
        record.description = description.strip()
        record.content_json = content
        record.version += 1
        record.updated_at = utc_now()
        self._configuration_event("idea.configuration_updated", record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def publish_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        record = self._idea_configuration(configuration_id)
        self._check_configuration_version(record, expected_version)
        if record.status != "draft":
            raise HTTPException(status_code=409, detail="Only a DRAFT Idea configuration can be published")
        self._validate_configuration_content(record.kind, record.content_json)
        record.status = "published"
        record.content_hash = hashlib.sha256(
            json.dumps(record.content_json, ensure_ascii=False, sort_keys=True).encode()
        ).hexdigest()
        record.published_at = utc_now()
        record.version += 1
        record.updated_at = utc_now()
        self._configuration_event("idea.configuration_published", record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def _validate_payload(self, payload: IdeaPayload) -> tuple[EnterpriseWorkspace, dict, dict]:
        workspace = self._owning_workspace(payload.owning_workspace_id)
        effective, sources, _path = self._effective_configuration(workspace)
        types = {str(item.get("code")) for item in effective.get("idea_types", [])}
        categories = {str(item.get("code")) for item in effective.get("categories", [])}
        if payload.idea_type not in types or payload.category not in categories:
            raise HTTPException(status_code=422, detail="Idea type or category is not enabled by effective configuration")
        if payload.target_portfolio_workspace_id is not None:
            portfolio = self._workspace(payload.target_portfolio_workspace_id)
            if portfolio.workspace_type_code != "portfolio":
                raise HTTPException(status_code=422, detail="Target Workspace must be a Portfolio")
        valid_objectives = set(
            self.db.scalars(
                select(EnterpriseStrategicObjective.code).where(
                    EnterpriseStrategicObjective.tenant_id == self.tenant_id,
                    EnterpriseStrategicObjective.active.is_(True),
                )
            ).all()
        )
        if set(payload.strategic_objective_codes) - valid_objectives:
            raise HTTPException(status_code=422, detail="One or more strategic objectives are inactive or unknown")
        if effective.get("objective_selection") == "one" and len(payload.strategic_objective_codes) > 1:
            raise HTTPException(status_code=422, detail="Effective configuration permits only one strategic objective")
        return workspace, effective, sources

    def _idea_configuration(self, configuration_id: int) -> AdminConfiguration:
        record = self.db.scalar(
            select(AdminConfiguration).where(
                AdminConfiguration.id == configuration_id,
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind.in_(["idea_demand_configuration", "idea_evaluation_matrix"]),
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail="Idea configuration not found")
        return record

    @staticmethod
    def _check_configuration_version(record: AdminConfiguration, expected_version: int) -> None:
        if record.version != expected_version:
            raise HTTPException(
                status_code=412,
                detail={"reason": "ETAG_MISMATCH", "current_version": record.version, "expected_version": expected_version},
            )

    @staticmethod
    def _validate_configuration_content(kind: str, content: dict) -> None:
        if kind == "idea_demand_configuration":
            if not isinstance(content.get("idea_types"), list) or not isinstance(content.get("categories"), list):
                raise HTTPException(status_code=422, detail="Idea configuration requires idea_types and categories")
            if content.get("objective_selection", "multiple") not in {"one", "multiple"}:
                raise HTTPException(status_code=422, detail="objective_selection must be one or multiple")
            return
        criteria = content.get("criteria")
        if not isinstance(criteria, list) or not criteria:
            raise HTTPException(status_code=422, detail="Evaluation matrix requires criteria")
        if round(sum(float(item.get("weight", 0)) for item in criteria), 4) != 100:
            raise HTTPException(status_code=422, detail="Evaluation matrix weights must total 100")

    def _configuration_event(
        self, event_type: str, record: AdminConfiguration, metadata: dict | None = None
    ) -> None:
        self.db.add(
            SecurityEvent(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                event_type=event_type,
                outcome="success",
                target_type="AdminConfiguration",
                target_id=record.id,
                metadata_json={"kind": record.kind, "code": record.code, "revision": record.revision, **(metadata or {})},
            )
        )

    def _validate_existing(self, idea: Idea) -> None:
        payload = IdeaCreate(
            title=idea.title,
            description=idea.description,
            idea_type=idea.idea_type,
            category=idea.category,
            expected_benefit=idea.expected_benefit,
            estimated_value=idea.estimated_value,
            currency_code=idea.currency_code,
            owning_workspace_id=idea.owning_workspace_id,
            target_portfolio_workspace_id=idea.target_portfolio_workspace_id,
            strategic_objective_codes=idea.strategic_objective_codes,
            attachment_refs=idea.attachment_refs_json,
        )
        self._validate_payload(payload)

    def _owning_workspace(self, workspace_id: int) -> EnterpriseWorkspace:
        workspace = self._workspace(workspace_id)
        if workspace.workspace_type_code not in OWNING_TYPES:
            raise HTTPException(status_code=422, detail="Ideas can only be owned by Enterprise, Business Unit or Portfolio")
        if not self.context.organization_wide and workspace.id not in self.context.workspace_ids:
            raise HTTPException(status_code=404, detail="Owning Workspace not found or not authorized")
        return workspace

    def _workspace(self, workspace_id: int) -> EnterpriseWorkspace:
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

    def _authorized_workspaces(self) -> list[EnterpriseWorkspace]:
        statement = select(EnterpriseWorkspace).where(
            EnterpriseWorkspace.tenant_id == self.tenant_id,
            EnterpriseWorkspace.workspace_type_code.in_(OWNING_TYPES),
            EnterpriseWorkspace.status.in_(["active", "draft"]),
        )
        if not self.context.organization_wide:
            statement = statement.where(EnterpriseWorkspace.id.in_(list(self.context.workspace_ids)))
        return list(self.db.scalars(statement.order_by(EnterpriseWorkspace.sort_order, EnterpriseWorkspace.name)).all())

    def _idea(self, idea_id: int) -> Idea:
        idea = self.db.scalar(select(Idea).where(Idea.id == idea_id, Idea.tenant_id == self.tenant_id))
        if idea is None:
            raise HTTPException(status_code=404, detail="Idea not found")
        if not self.context.organization_wide and not (
            idea.requestor_user_id == self.actor_id
            or idea.owner_user_id == self.actor_id
            or idea.owning_workspace_id in self.context.workspace_ids
        ):
            raise HTTPException(status_code=404, detail="Idea not found")
        return idea

    def _effective_configuration(
        self, workspace: EnterpriseWorkspace | None
    ) -> tuple[dict, dict, list[EnterpriseWorkspace]]:
        default = self._latest_configuration("idea_demand_configuration", "default")
        if default is None:
            raise HTTPException(status_code=409, detail="No published Idea configuration")
        path = self._workspace_path(workspace) if workspace else []
        selected = default
        for item in path:
            candidate = self._latest_configuration("idea_demand_configuration", f"workspace-{item.id}")
            if candidate is not None and (item.id == getattr(workspace, "id", None) or candidate.content_json.get("inherit_to_descendants", True)):
                selected = candidate
        source = {
            "configuration_id": selected.id,
            "code": selected.code,
            "revision": selected.revision,
            "workspace_id": selected.content_json.get("workspace_id"),
        }
        return dict(selected.content_json), {"idea_demand_configuration": source}, path

    def _effective_matrix(
        self, workspace: EnterpriseWorkspace
    ) -> tuple[AdminConfiguration, dict, list[EnterpriseWorkspace]]:
        default = self._latest_configuration("idea_evaluation_matrix", "default")
        if default is None:
            raise HTTPException(status_code=409, detail="No published evaluation matrix")
        path = self._workspace_path(workspace)
        selected = default
        for item in path:
            candidate = self._latest_configuration("idea_evaluation_matrix", f"workspace-{item.id}")
            if candidate is not None and (item.id == workspace.id or candidate.content_json.get("inherit_to_descendants", True)):
                selected = candidate
        return selected, {"matrix_configuration_id": selected.id, "revision": selected.revision}, path

    def _workspace_path(self, workspace: EnterpriseWorkspace | None) -> list[EnterpriseWorkspace]:
        if workspace is None:
            return []
        path: list[EnterpriseWorkspace] = []
        cursor: EnterpriseWorkspace | None = workspace
        seen: set[int] = set()
        while cursor is not None and cursor.id not in seen:
            seen.add(cursor.id)
            path.append(cursor)
            cursor = (
                self.db.scalar(
                    select(EnterpriseWorkspace).where(
                        EnterpriseWorkspace.id == cursor.parent_id,
                        EnterpriseWorkspace.tenant_id == self.tenant_id,
                    )
                )
                if cursor.parent_id
                else None
            )
        return list(reversed(path))

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
        serialized = json.dumps(content, ensure_ascii=False, sort_keys=True)
        self.db.add(
            AdminConfiguration(
                tenant_id=self.tenant_id,
                kind=kind,
                code=code,
                name=name,
                description="Gate 07A governed default",
                status="published",
                revision=1,
                version=1,
                content_json=content,
                content_hash=hashlib.sha256(serialized.encode()).hexdigest(),
                published_at=utc_now(),
                created_by_user_id=self.actor_id,
            )
        )

    def _sequence(self) -> AdminNumberSequence:
        sequence = self.db.scalar(
            select(AdminNumberSequence).where(
                AdminNumberSequence.tenant_id == self.tenant_id,
                AdminNumberSequence.rule_code == IDEA_NUMBER_RULE,
                AdminNumberSequence.scope_key == "tenant",
            )
        )
        if sequence is None:
            raise HTTPException(status_code=409, detail="Idea numbering is not initialized")
        return sequence

    def _reserve_number(self) -> str:
        result = self.db.execute(
            update(AdminNumberSequence)
            .where(
                AdminNumberSequence.tenant_id == self.tenant_id,
                AdminNumberSequence.rule_code == IDEA_NUMBER_RULE,
                AdminNumberSequence.scope_key == "tenant",
            )
            .values(
                next_value=AdminNumberSequence.next_value + 1,
                version=AdminNumberSequence.version + 1,
                updated_at=utc_now(),
            )
            .returning(AdminNumberSequence.next_value)
        ).scalar_one()
        return f"IDEA-{int(result) - 1:05d}"

    def _validate_owner(self, user_id: int, workspace_id: int) -> None:
        user = self.db.scalar(
            select(UserAccount).where(
                UserAccount.id == user_id, UserAccount.tenant_id == self.tenant_id, UserAccount.status == "active"
            )
        )
        if user is None:
            raise HTTPException(status_code=422, detail="Owner must be an active tenant user")
        assignment = self.db.scalar(
            select(SecurityAccessAssignment.id)
            .join(SecurityRolePermission, SecurityRolePermission.role_id == SecurityAccessAssignment.role_id)
            .join(PermissionCatalog, PermissionCatalog.id == SecurityRolePermission.permission_id)
            .where(
                SecurityAccessAssignment.tenant_id == self.tenant_id,
                SecurityAccessAssignment.user_id == user_id,
                SecurityAccessAssignment.status == "active",
                PermissionCatalog.key == "idea.evaluate",
                (SecurityAccessAssignment.scope_type == "organization")
                | (SecurityAccessAssignment.workspace_id == workspace_id),
            )
            .limit(1)
        )
        if assignment is None:
            raise HTTPException(status_code=422, detail="Owner lacks idea.evaluate in the owning Workspace scope")

    def _require_screening_complete(self, idea: Idea) -> None:
        config = self._configuration_snapshot(idea)
        checklist = idea.screening_json.get("checklist", {})
        missing = [
            item.get("code")
            for item in config.get("screening_checklist", [])
            if item.get("blocking", True) and not checklist.get(str(item.get("code")), False)
        ]
        if missing:
            raise HTTPException(status_code=422, detail={"reason": "INCOMPLETE_SCREENING", "items": missing})

    @staticmethod
    def _configuration_snapshot(idea: Idea) -> dict:
        return dict(idea.configuration_snapshot_json.get("effective") or DEFAULT_IDEA_CONFIGURATION)

    def _readiness(self, idea: Idea, *, assume_accepted: bool = False) -> dict:
        issues: list[str] = []
        if idea.state != "ACCEPTED" and not assume_accepted:
            issues.append("IDEA_NOT_ACCEPTED")
        if idea.accepted_evaluation_id is None:
            issues.append("NO_ACCEPTED_EVALUATION")
        if not idea.strategic_objective_codes:
            issues.append("NO_STRATEGIC_OBJECTIVE")
        config = self._configuration_snapshot(idea)
        mapping = {
            "project_name": idea.title,
            "description": idea.description,
            "business_case": idea.expected_benefit,
            "estimated_budget": str(idea.estimated_value) if idea.estimated_value is not None else None,
            "currency_code": idea.currency_code,
            "parent_workspace_id": idea.target_portfolio_workspace_id or idea.owning_workspace_id,
            "strategic_objective_codes": idea.strategic_objective_codes,
            "source_idea_id": idea.id,
            "source_idea_number": idea.idea_number,
            "mapping_rule": config.get("proposal_mapping", {}),
        }
        return {"blocking_issues": issues, "mapping_preview": mapping}

    def _transition(
        self,
        idea: Idea,
        target: str,
        event_type: str,
        *,
        metadata: dict | None = None,
        **timestamps,
    ) -> IdeaOut:
        before = idea.state
        idea.state = target
        for key, value in timestamps.items():
            setattr(idea, key, value)
        self._touch(idea)
        self._event(event_type, idea, before, target, metadata)
        return self._commit(idea)

    def _touch(self, idea: Idea) -> None:
        idea.last_modified_by_user_id = self.actor_id
        idea.updated_at = utc_now()

    def _check_version(self, idea: Idea, expected: int) -> None:
        if idea.revision_version != expected:
            raise HTTPException(
                status_code=412,
                detail={"reason": "ETAG_MISMATCH", "current_version": idea.revision_version, "expected_version": expected},
            )

    def _commit(self, idea: Idea) -> IdeaOut:
        self.db.commit()
        self.db.refresh(idea)
        return self._out(idea)

    def _event(
        self,
        event_type: str,
        idea: Idea,
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
                target_type="Idea",
                target_id=idea.id,
                metadata_json={"state_before": state_before, "state_after": state_after, **(metadata or {})},
            )
        )

    def _out(self, idea: Idea) -> IdeaOut:
        workspace = self._workspace(idea.owning_workspace_id)
        requestor = self.db.get(UserAccount, idea.requestor_user_id)
        owner = self.db.get(UserAccount, idea.owner_user_id) if idea.owner_user_id else None
        evaluations = list(
            self.db.scalars(
                select(IdeaEvaluation)
                .where(IdeaEvaluation.tenant_id == self.tenant_id, IdeaEvaluation.idea_id == idea.id)
                .order_by(IdeaEvaluation.evaluation_version)
            ).all()
        )
        return IdeaOut(
            id=idea.id,
            idea_number=idea.idea_number,
            title=idea.title,
            description=idea.description,
            idea_type=idea.idea_type,
            category=idea.category,
            expected_benefit=idea.expected_benefit,
            estimated_value=idea.estimated_value,
            currency_code=idea.currency_code,
            owning_workspace_id=idea.owning_workspace_id,
            owning_workspace_name=workspace.name,
            target_portfolio_workspace_id=idea.target_portfolio_workspace_id,
            strategic_objective_codes=idea.strategic_objective_codes or [],
            requestor_user_id=idea.requestor_user_id,
            requestor_name=requestor.full_name if requestor else "Unknown",
            owner_user_id=idea.owner_user_id,
            owner_name=owner.full_name if owner else None,
            state=IdeaState(idea.state),
            screening=idea.screening_json or {},
            routing=idea.routing_json or {},
            attachment_refs=idea.attachment_refs_json or [],
            accepted_evaluation_id=idea.accepted_evaluation_id,
            decision_reason=idea.decision_reason,
            readiness=idea.readiness_json or {},
            evaluations=[IdeaEvaluationOut.model_validate(item) for item in evaluations],
            allowed_actions=self._allowed_actions(idea),
            revision_version=idea.revision_version,
            created_at=idea.created_at,
            updated_at=idea.updated_at,
            submitted_at=idea.submitted_at,
            evaluated_at=idea.evaluated_at,
            decided_at=idea.decided_at,
        )

    def _allowed_actions(self, idea: Idea) -> list[str]:
        admin = self.context.organization_wide or "organization_admin" in self.context.role_codes
        roles = self.context.role_codes
        actions: list[str] = []
        if idea.state in {"DRAFT", "RETURNED"} and (idea.requestor_user_id == self.actor_id or admin):
            actions += ["edit", "submit", "cancel"]
        if idea.state in {"SUBMITTED", "SCREENING"} and (admin or "idea_intake_reviewer" in roles):
            actions += ["screen", "return"]
        if idea.state == "SCREENING" and (admin or "idea_intake_reviewer" in roles):
            actions += ["route", "assign_owner"]
        if idea.state in {"OWNER_ASSIGNED", "UNDER_EVALUATION"} and (
            admin or idea.owner_user_id == self.actor_id or "idea_owner" in roles
        ):
            actions += ["start_evaluation" if idea.state == "OWNER_ASSIGNED" else "complete_evaluation", "return"]
        if idea.state == "EVALUATED" and (admin or "idea_decision_maker" in roles):
            actions += ["accept", "reject", "return"]
        if idea.state == "ACCEPTED":
            actions.append("proposal_readiness")
        return actions

    @staticmethod
    def _payload_values(payload: IdeaPayload) -> dict:
        return {
            "title": payload.title,
            "description": payload.description,
            "idea_type": payload.idea_type,
            "category": payload.category,
            "expected_benefit": payload.expected_benefit,
            "estimated_value": payload.estimated_value,
            "currency_code": payload.currency_code.upper(),
            "owning_workspace_id": payload.owning_workspace_id,
            "target_portfolio_workspace_id": payload.target_portfolio_workspace_id,
            "strategic_objective_codes": payload.strategic_objective_codes,
            "attachment_refs_json": payload.attachment_refs,
        }

    @staticmethod
    def _workspace_option(workspace: EnterpriseWorkspace) -> dict:
        return {
            "id": workspace.id,
            "code": workspace.code,
            "record_code": workspace.record_code,
            "name": workspace.name,
            "workspace_type_code": workspace.workspace_type_code,
        }
