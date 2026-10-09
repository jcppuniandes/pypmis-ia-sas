"""Application service for Gate 07C Strategic Gate Decision lifecycle."""

from __future__ import annotations

import hashlib
import json
from datetime import date

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domain.models import (
    AdminConfiguration,
    AdminNumberSequence,
    EnterpriseWorkspace,
    SecurityEvent,
    UserAccount,
)
from app.modules.idea_demand.models import Idea, IdeaEvaluation
from app.modules.project_proposal.models import ProjectProposal, ProjectProposalEvaluation
from app.modules.project_proposal.service import ProjectProposalService
from app.modules.strategic_gate.models import StrategicGateDecision
from app.modules.strategic_gate.schemas import (
    PortfolioIntakeReadinessOut,
    StrategicGateConfigurationPreviewOut,
    StrategicGateDecideIn,
    StrategicGateDecisionOut,
    StrategicGateHistoryItemOut,
    StrategicGateOptionsOut,
    StrategicGateOutcome,
    StrategicGatePreviewOut,
    StrategicGateReturnIn,
    StrategicGateState,
    StrategicGateUpdate,
)

DECISION_NUMBER_RULE = "strategic-gate-decision"
ACTIVE_STATES = frozenset({"DRAFT", "SUBMITTED", "IN_REVIEW"})
VALID_OUTCOMES = frozenset({"APPROVE", "RETURN", "REJECT", "DEFER"})
OWNING_TYPES = frozenset({"enterprise", "business-unit", "portfolio"})
PRIVILEGED_ROLES = frozenset(
    {
        "organization_admin",
        "gate_preparer",
        "gate_reviewer",
        "gate_decision_maker",
        "gate_committee_member",
        "gate_configuration_admin",
    }
)

DEFAULT_STRATEGIC_GATE_CONFIGURATION = {
    "workspace_id": None,
    "inherit_to_descendants": True,
    "max_active_gate_decisions_per_proposal": 1,
    "gate_type": "PROJECT_PROPOSAL_GATE",
    "context_type": "PROJECT_PROPOSAL",
    "required_fields": ["decision_reason"],
    "decision_checklist": [
        {"code": "proposal_readiness_valid", "label": "Proposal readiness is valid", "blocking": True},
        {"code": "proposal_evaluation_valid", "label": "Proposal evaluation is current", "blocking": True},
        {"code": "business_case_reviewed", "label": "Business case reviewed", "blocking": True},
        {
            "code": "strategic_alignment_confirmed",
            "label": "Strategic alignment confirmed",
            "blocking": True,
        },
        {"code": "target_portfolio_confirmed", "label": "Target Portfolio confirmed", "blocking": True},
        {"code": "risks_reviewed", "label": "Risks reviewed", "blocking": True},
        {"code": "rom_cost_reviewed", "label": "ROM cost reviewed", "blocking": False},
        {
            "code": "schedule_assumptions_reviewed",
            "label": "Schedule assumptions reviewed",
            "blocking": False,
        },
        {"code": "sponsor_confirmed", "label": "Sponsor confirmed", "blocking": True},
        {
            "code": "funding_not_yet_required_acknowledged",
            "label": "Funding is not yet required",
            "blocking": True,
        },
    ],
    "decision_criteria": [
        {"code": "strategic_fit", "label": "Strategic Fit", "weight": 20},
        {"code": "value_benefit", "label": "Value / Benefit", "weight": 15},
        {"code": "affordability_rom", "label": "Affordability ROM", "weight": 15},
        {"code": "risk_acceptability", "label": "Risk Acceptability", "weight": 15},
        {"code": "organizational_capacity", "label": "Organizational Capacity", "weight": 10},
        {"code": "timing", "label": "Timing", "weight": 10},
        {"code": "portfolio_fit", "label": "Portfolio Fit", "weight": 10},
        {"code": "decision_conditions", "label": "Decision Conditions", "weight": 5},
    ],
    "decision_authority": {"mode": "SINGLE_DECISION_MAKER", "allowed_role": "gate_decision_maker"},
    "committee_policy": {
        "enabled": False,
        "quorum_required": 1,
        "chair_required": False,
        "record_votes": True,
    },
    "four_eyes": {
        "decision_maker_cannot_be_proposal_creator": False,
        "decision_maker_cannot_be_proposal_evaluator": False,
    },
    "return_rules": {"reason_required": True, "proposal_state": "RETURNED"},
    "reject_rules": {"reason_required": True, "proposal_state": "STRATEGIC_GATE_REJECTED"},
    "defer_rules": {"reason_required": True, "deferred_until_optional": True},
    "approve_output_policy": {
        "status": "READY_FOR_PORTFOLIO_INTAKE",
        "can_create_portfolio_candidate": False,
    },
}


class StrategicGateService:
    def __init__(self, db: Session, tenant_id: int, actor_id: int, context) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.actor_id = actor_id
        self.context = context

    def ensure_seed(self) -> None:
        if self._latest_configuration("default") is None:
            self._seed_configuration(
                "default",
                "Default Strategic Gate Decision",
                DEFAULT_STRATEGIC_GATE_CONFIGURATION,
            )
        if self._sequence(required=False) is None:
            self.db.add(
                AdminNumberSequence(
                    tenant_id=self.tenant_id,
                    rule_code=DECISION_NUMBER_RULE,
                    scope_key="tenant",
                    next_value=1,
                    version=1,
                )
            )
        self.db.commit()

    def options(self) -> StrategicGateOptionsOut:
        proposals = self.db.scalars(
            self._proposal_scope(
                select(ProjectProposal).where(
                    ProjectProposal.tenant_id == self.tenant_id,
                    ProjectProposal.status == "READY_FOR_STRATEGIC_GATE",
                )
            ).order_by(ProjectProposal.updated_at.desc())
        ).all()
        eligible: list[dict] = []
        for proposal in proposals:
            preview = self.preview(proposal.id)
            eligible.append(
                {
                    "id": proposal.id,
                    "proposal_number": proposal.proposal_number,
                    "name": proposal.name,
                    "owning_workspace_id": proposal.owning_workspace_id,
                    "target_portfolio_workspace_id": proposal.target_portfolio_workspace_id,
                    "can_create": not preview.blockers,
                    "blockers": preview.blockers,
                }
            )
        return StrategicGateOptionsOut(
            decision_number_preview=self._preview_number(),
            eligible_proposals=eligible,
            users=[{"id": item.id, "name": item.full_name, "email": item.email} for item in self._users()],
            gate_types=["PROJECT_PROPOSAL_GATE"],
        )

    def preview(self, project_proposal_id: int) -> StrategicGatePreviewOut:
        proposal = self._proposal(project_proposal_id)
        readiness = self._readiness(proposal)
        evaluation = self._latest_proposal_evaluation(proposal.id)
        idea = self._idea(proposal.source_idea_id)
        idea_evaluation = self._idea_evaluation(proposal.accepted_idea_evaluation_id, idea.id)
        workspace = self._owning_workspace(proposal.owning_workspace_id)
        target = (
            self._workspace(proposal.target_portfolio_workspace_id) if proposal.target_portfolio_workspace_id else None
        )
        config, sources, _path, record = self._effective_configuration(workspace)
        blockers = self._entry_blockers(proposal, readiness, evaluation, idea, idea_evaluation, target)
        active = self._active_decision(proposal.id, str(config.get("gate_type", "PROJECT_PROPOSAL_GATE")))
        if active is not None:
            blockers.append("ACTIVE_GATE_DECISION_EXISTS")
        warnings = list(readiness.get("warnings", []))
        if proposal.rom_cost is None:
            warnings.append("ROM_COST_NOT_AVAILABLE")
        checklist = self._decision_checklist(config, proposal, readiness, evaluation, target)
        blockers.extend(
            f"CHECKLIST:{item['code']}" for item in checklist if item["blocking"] and item["status"] == "FAIL"
        )
        return StrategicGatePreviewOut(
            decision_number_preview=self._preview_number(),
            project_proposal=self._proposal_snapshot(proposal),
            source_idea=self._idea_snapshot(idea),
            accepted_idea_evaluation=self._idea_evaluation_snapshot(idea_evaluation),
            proposal_evaluation=self._proposal_evaluation_snapshot(evaluation),
            readiness=readiness,
            owning_workspace=self._workspace_option(workspace),
            target_portfolio=self._workspace_option(target) if target else None,
            strategic_objectives=self._strategic_objectives_snapshot(proposal),
            gate_type=str(config.get("gate_type", "PROJECT_PROPOSAL_GATE")),
            configuration={
                "id": record.id,
                "revision": record.revision,
                "hash": record.content_hash or self._hash(config),
                "source": sources,
            },
            decision_checklist=checklist,
            decision_criteria=list(config.get("decision_criteria", [])),
            authority=dict(config.get("decision_authority", {})),
            committee_policy=dict(config.get("committee_policy", {})),
            blockers=sorted(set(blockers)),
            warnings=sorted(set(warnings)),
        )

    def create(self, project_proposal_id: int, idempotency_key: str = "") -> StrategicGateDecisionOut:
        proposal = self._proposal(project_proposal_id, for_update=True)
        active = self._active_decision(proposal.id, "PROJECT_PROPOSAL_GATE", for_update=True)
        if active is not None:
            return self._out(active)
        preview = self.preview(proposal.id)
        if preview.blockers:
            raise HTTPException(
                status_code=409,
                detail={"reason": "GATE07C_REWORK_REQUIRED", "blockers": preview.blockers},
            )
        decision = self._build_decision(proposal, preview)
        self.db.add(decision)
        self.db.flush()
        self._event(
            "strategic_gate.created",
            decision,
            None,
            "DRAFT",
            {"idempotency_key": idempotency_key, "proposal_readiness_hash": decision.proposal_readiness_hash},
        )
        return self._commit(decision)

    def list(
        self,
        *,
        state_filter: str = "",
        outcome_filter: str = "",
        search: str = "",
        owning_workspace_id: int | None = None,
        queue: str = "",
    ) -> list[StrategicGateDecisionOut]:
        statement = self._decision_scope(
            select(StrategicGateDecision).where(StrategicGateDecision.tenant_id == self.tenant_id)
        )
        if state_filter.strip():
            statement = statement.where(StrategicGateDecision.state == state_filter.strip().upper())
        if outcome_filter.strip():
            statement = statement.where(StrategicGateDecision.outcome == outcome_filter.strip().upper())
        if owning_workspace_id:
            statement = statement.where(StrategicGateDecision.owning_workspace_id == owning_workspace_id)
        if search.strip():
            term = f"%{search.strip().lower()}%"
            statement = statement.where(func.lower(StrategicGateDecision.decision_number).like(term))
        queues = {
            "mine": StrategicGateDecision.prepared_by_user_id == self.actor_id,
            "prepare": StrategicGateDecision.state == "DRAFT",
            "submitted": StrategicGateDecision.state == "SUBMITTED",
            "review": StrategicGateDecision.state == "IN_REVIEW",
            "decided": StrategicGateDecision.state == "DECIDED",
            "approved": StrategicGateDecision.outcome == "APPROVE",
            "returned": StrategicGateDecision.outcome == "RETURN",
            "rejected": StrategicGateDecision.outcome == "REJECT",
            "deferred": StrategicGateDecision.outcome == "DEFER",
        }
        if queue in queues:
            statement = statement.where(queues[queue])
        rows = self.db.scalars(statement.order_by(StrategicGateDecision.updated_at.desc())).all()
        return [self._out(item) for item in rows]

    def get(self, decision_id: int) -> StrategicGateDecisionOut:
        return self._out(self._decision(decision_id))

    def update(
        self,
        decision_id: int,
        payload: StrategicGateUpdate,
        expected_version: int,
    ) -> StrategicGateDecisionOut:
        decision = self._decision(decision_id)
        self._check_version(decision, expected_version)
        if decision.state != "DRAFT":
            raise HTTPException(status_code=409, detail="Only a DRAFT Decision can be edited")
        if payload.decision_maker_user_id is not None:
            self._user(payload.decision_maker_user_id)
        decision.decision_reason = payload.decision_reason
        decision.decision_comments = payload.decision_comments
        decision.decision_maker_user_id = payload.decision_maker_user_id
        decision.conditions_json = payload.conditions
        decision.evidence_refs_json = payload.evidence_refs
        decision.committee_snapshot_json = payload.committee
        self._touch(decision)
        self._event("strategic_gate.updated", decision, "DRAFT", "DRAFT")
        return self._commit(decision)

    def submit(
        self,
        decision_id: int,
        expected_version: int,
        idempotency_key: str = "",
    ) -> StrategicGateDecisionOut:
        decision = self._decision(decision_id, for_update=True)
        if decision.state == "SUBMITTED":
            return self._out(decision)
        self._check_version(decision, expected_version)
        if decision.state != "DRAFT":
            raise HTTPException(status_code=409, detail="Decision cannot be submitted from its current state")
        self._assert_current_readiness(decision)
        blockers = self._required_field_blockers(decision)
        if blockers:
            raise HTTPException(status_code=422, detail={"reason": "INCOMPLETE_DECISION", "items": blockers})
        return self._transition(
            decision,
            "SUBMITTED",
            "strategic_gate.submitted",
            metadata={"idempotency_key": idempotency_key},
            submitted_at=utc_now(),
        )

    def start_review(
        self,
        decision_id: int,
        expected_version: int,
        idempotency_key: str = "",
    ) -> StrategicGateDecisionOut:
        decision = self._decision(decision_id, for_update=True)
        if decision.state == "IN_REVIEW":
            return self._out(decision)
        self._check_version(decision, expected_version)
        if decision.state != "SUBMITTED":
            raise HTTPException(status_code=409, detail="Review requires SUBMITTED state")
        self._assert_current_readiness(decision)
        return self._transition(
            decision,
            "IN_REVIEW",
            "strategic_gate.review_started",
            metadata={"idempotency_key": idempotency_key},
            review_started_at=utc_now(),
        )

    def return_to_preparer(
        self,
        decision_id: int,
        payload: StrategicGateReturnIn,
        expected_version: int,
        idempotency_key: str = "",
    ) -> StrategicGateDecisionOut:
        decision = self._decision(decision_id, for_update=True)
        self._check_version(decision, expected_version)
        if decision.state not in {"SUBMITTED", "IN_REVIEW"}:
            raise HTTPException(status_code=409, detail="Only submitted or in-review Decisions can be returned")
        before = decision.state
        decision.state = "DRAFT"
        decision.decision_comments = payload.reason
        decision.submitted_at = None
        decision.review_started_at = None
        self._touch(decision)
        self._event(
            "strategic_gate.returned_to_preparer",
            decision,
            before,
            "DRAFT",
            {"reason": payload.reason, "idempotency_key": idempotency_key},
        )
        return self._commit(decision)

    def decide(
        self,
        decision_id: int,
        payload: StrategicGateDecideIn,
        expected_version: int,
        idempotency_key: str = "",
    ) -> StrategicGateDecisionOut:
        decision = self._decision(decision_id, for_update=True)
        if decision.state == "DECIDED":
            if decision.outcome == payload.outcome.value:
                return self._out(decision)
            raise HTTPException(status_code=409, detail="Decision already closed with a different outcome")
        self._check_version(decision, expected_version)
        if decision.state != "IN_REVIEW":
            raise HTTPException(status_code=409, detail="Decision requires IN_REVIEW state")
        proposal = self._proposal(decision.project_proposal_id, for_update=True)
        self._assert_current_readiness(decision, proposal=proposal)
        config = dict(decision.configuration_snapshot_json or DEFAULT_STRATEGIC_GATE_CONFIGURATION)
        checklist = self._merge_checklist(decision, payload.checklist)
        blockers = [item["code"] for item in checklist if item.get("blocking") and item.get("status") != "PASS"]
        if blockers:
            raise HTTPException(
                status_code=422,
                detail={"reason": "DECISION_CHECKLIST_BLOCKED", "blockers": blockers},
            )
        committee = payload.committee or decision.committee_snapshot_json
        maker_id = self._validate_authority(decision, proposal, config, committee)
        now = utc_now()
        decision.state = "DECIDED"
        decision.outcome = payload.outcome.value
        decision.decision_reason = payload.reason
        decision.decision_comments = payload.comments
        decision.conditions_json = payload.conditions
        decision.decision_checklist_snapshot_json = checklist
        decision.committee_snapshot_json = committee
        decision.decision_maker_user_id = maker_id
        decision.decided_at = now
        decision.deferred_until = payload.deferred_until
        decision.updated_by = self.actor_id
        decision.updated_at = now
        proposal_before = proposal.status
        proposal.status = {
            "APPROVE": "STRATEGIC_GATE_APPROVED",
            "RETURN": "RETURNED",
            "REJECT": "STRATEGIC_GATE_REJECTED",
            "DEFER": "STRATEGIC_GATE_DEFERRED",
        }[payload.outcome.value]
        if payload.outcome == StrategicGateOutcome.RETURN:
            proposal.return_reason = payload.reason
            proposal.returned_stage = "STRATEGIC_GATE"
            proposal.returned_at = now
        proposal.updated_by = self.actor_id
        proposal.updated_at = now
        decision.decision_hash = self._decision_hash(decision)
        self._event(
            "strategic_gate.decided",
            decision,
            "IN_REVIEW",
            "DECIDED",
            {
                "outcome": decision.outcome,
                "decision_hash": decision.decision_hash,
                "idempotency_key": idempotency_key,
            },
        )
        outcome_event = {
            "APPROVE": "strategic_gate.approved",
            "RETURN": "strategic_gate.returned",
            "REJECT": "strategic_gate.rejected",
            "DEFER": "strategic_gate.deferred",
        }[payload.outcome.value]
        self._event(
            outcome_event,
            decision,
            "IN_REVIEW",
            "DECIDED",
            {"outcome": decision.outcome},
        )
        self._proposal_event(proposal, proposal_before, proposal.status, decision)
        self.db.commit()
        self.db.refresh(decision)
        return self._out(decision)

    def void(
        self,
        decision_id: int,
        expected_version: int,
        idempotency_key: str = "",
    ) -> StrategicGateDecisionOut:
        decision = self._decision(decision_id, for_update=True)
        if decision.state == "VOIDED":
            return self._out(decision)
        self._check_version(decision, expected_version)
        if decision.state not in ACTIVE_STATES:
            raise HTTPException(status_code=409, detail="Closed Decisions cannot be voided")
        return self._transition(
            decision,
            "VOIDED",
            "strategic_gate.voided",
            metadata={"idempotency_key": idempotency_key},
            voided_at=utc_now(),
        )

    def new_round(
        self,
        decision_id: int,
        expected_version: int,
        idempotency_key: str = "",
    ) -> StrategicGateDecisionOut:
        previous = self._decision(decision_id, for_update=True)
        self._check_version(previous, expected_version)
        if previous.state != "DECIDED" or previous.outcome not in {"RETURN", "DEFER"}:
            raise HTTPException(status_code=409, detail="A new round requires a RETURN or DEFER decision")
        if self._active_decision(previous.project_proposal_id, previous.gate_type, for_update=True) is not None:
            raise HTTPException(status_code=409, detail="An active Decision already exists")
        proposal = self._proposal(previous.project_proposal_id, for_update=True)
        if previous.outcome == "DEFER":
            if previous.deferred_until and previous.deferred_until > date.today():
                raise HTTPException(status_code=409, detail="Deferred Decision is not yet eligible for a new round")
            proposal.status = "READY_FOR_STRATEGIC_GATE"
            proposal.updated_by = self.actor_id
            proposal.updated_at = utc_now()
            self.db.flush()
            self.db.refresh(proposal)
        if proposal.status != "READY_FOR_STRATEGIC_GATE":
            raise HTTPException(
                status_code=409,
                detail="Returned Proposal must complete Gate 07B rework before a new decision round",
            )
        preview = self.preview(proposal.id)
        preview.blockers = [item for item in preview.blockers if item != "ACTIVE_GATE_DECISION_EXISTS"]
        if preview.blockers:
            raise HTTPException(
                status_code=409,
                detail={"reason": "GATE07C_REWORK_REQUIRED", "blockers": preview.blockers},
            )
        decision = self._build_decision(proposal, preview)
        self.db.add(decision)
        self.db.flush()
        self._event(
            "strategic_gate.new_round_created",
            decision,
            None,
            "DRAFT",
            {"previous_decision_id": previous.id, "idempotency_key": idempotency_key},
        )
        return self._commit(decision)

    def portfolio_intake_readiness(self, decision_id: int) -> PortfolioIntakeReadinessOut:
        decision = self._decision(decision_id)
        blockers: list[str] = []
        warnings: list[str] = []
        if decision.state != "DECIDED":
            blockers.append("DECISION_NOT_DECIDED")
        if decision.outcome != "APPROVE":
            blockers.append("DECISION_NOT_APPROVED")
        if not decision.decision_hash:
            blockers.append("DECISION_HASH_MISSING")
        payload = {
            "strategic_gate_decision_id": decision.id,
            "decision_number": decision.decision_number,
            "outcome": decision.outcome,
            "project_proposal_id": decision.project_proposal_id,
            "project_proposal_number": decision.proposal_snapshot_json.get("proposal_number", ""),
            "source_idea_id": decision.source_idea_id,
            "accepted_idea_evaluation_id": decision.accepted_idea_evaluation_id,
            "proposal_evaluation_id": decision.proposal_evaluation_id,
            "owning_workspace_id": decision.owning_workspace_id,
            "target_portfolio_workspace_id": decision.target_portfolio_workspace_id,
            "strategic_objectives": list(decision.strategic_objectives_snapshot_json or []),
            "proposal_score": decision.proposal_score,
            "conditions": list(decision.conditions_json or []),
            "decision_hash": decision.decision_hash,
            "blockers": blockers,
            "warnings": warnings,
        }
        return PortfolioIntakeReadinessOut(
            status="READY_FOR_PORTFOLIO_INTAKE" if not blockers else "GATE07C_REWORK_REQUIRED",
            can_create_portfolio_candidate=False,
            readiness_hash=self._hash(payload),
            **payload,
        )

    def history(self, decision_id: int) -> list[StrategicGateHistoryItemOut]:
        self._decision(decision_id)
        rows = self.db.scalars(
            select(SecurityEvent)
            .where(
                SecurityEvent.tenant_id == self.tenant_id,
                SecurityEvent.target_type == "StrategicGateDecision",
                SecurityEvent.target_id == decision_id,
            )
            .order_by(SecurityEvent.occurred_at)
        ).all()
        return [
            StrategicGateHistoryItemOut(
                event_type=item.event_type,
                outcome=item.outcome,
                actor_user_id=item.user_id,
                metadata=item.metadata_json,
                occurred_at=item.occurred_at,
            )
            for item in rows
        ]

    def related_to_proposal(self, proposal_id: int) -> list[StrategicGateDecisionOut]:
        self._proposal(proposal_id)
        rows = self.db.scalars(
            select(StrategicGateDecision)
            .where(
                StrategicGateDecision.tenant_id == self.tenant_id,
                StrategicGateDecision.project_proposal_id == proposal_id,
            )
            .order_by(StrategicGateDecision.gate_round.desc())
        ).all()
        return [self._out(item) for item in rows]

    def related_to_idea(self, idea_id: int) -> list[StrategicGateDecisionOut]:
        self._idea(idea_id)
        rows = self.db.scalars(
            select(StrategicGateDecision)
            .where(
                StrategicGateDecision.tenant_id == self.tenant_id,
                StrategicGateDecision.source_idea_id == idea_id,
            )
            .order_by(StrategicGateDecision.created_at.desc())
        ).all()
        return [self._out(item) for item in rows]

    def admin_configurations(self) -> list[AdminConfiguration]:
        return list(
            self.db.scalars(
                select(AdminConfiguration)
                .where(
                    AdminConfiguration.tenant_id == self.tenant_id,
                    AdminConfiguration.kind == "strategic_gate_configuration",
                )
                .order_by(AdminConfiguration.code, AdminConfiguration.revision.desc())
            ).all()
        )

    def configuration_preview(self, proposal_id: int) -> StrategicGateConfigurationPreviewOut:
        proposal = self._proposal(proposal_id)
        workspace = self._owning_workspace(proposal.owning_workspace_id)
        effective, sources, path, _record = self._effective_configuration(workspace)
        return StrategicGateConfigurationPreviewOut(
            project_proposal_id=proposal.id,
            owning_workspace_id=workspace.id,
            path=[self._workspace_option(item) for item in path],
            effective=effective,
            sources=sources,
            decision_preview=self.preview(proposal.id),
        )

    def clone_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        source = self._configuration(configuration_id)
        self._check_configuration_version(source, expected_version)
        if source.status != "published":
            raise HTTPException(status_code=409, detail="Only published Strategic Gate configuration can be cloned")
        revision = (
            int(
                self.db.scalar(
                    select(func.coalesce(func.max(AdminConfiguration.revision), 0)).where(
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
        self._configuration_event("strategic_gate.configuration_cloned", clone, {"source_id": source.id})
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
            raise HTTPException(status_code=409, detail="Published Strategic Gate configuration is immutable")
        self._validate_configuration_content(content)
        record.name = name
        record.description = description
        record.content_json = content
        record.content_hash = self._hash(content)
        record.version += 1
        record.updated_at = utc_now()
        self._configuration_event("strategic_gate.configuration_updated", record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def publish_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        record = self._configuration(configuration_id)
        self._check_configuration_version(record, expected_version)
        if record.status == "published":
            return record
        self._validate_configuration_content(record.content_json)
        record.status = "published"
        record.content_hash = self._hash(record.content_json)
        record.published_at = utc_now()
        record.updated_at = utc_now()
        record.version += 1
        self._configuration_event("strategic_gate.configuration_published", record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def _build_decision(
        self,
        proposal: ProjectProposal,
        preview: StrategicGatePreviewOut,
    ) -> StrategicGateDecision:
        evaluation = self._latest_proposal_evaluation(proposal.id)
        if evaluation is None:
            raise HTTPException(status_code=409, detail="Proposal evaluation is missing")
        effective, _sources, _path, record = self._effective_configuration(
            self._owning_workspace(proposal.owning_workspace_id)
        )
        round_number = (
            int(
                self.db.scalar(
                    select(func.coalesce(func.max(StrategicGateDecision.gate_round), 0)).where(
                        StrategicGateDecision.tenant_id == self.tenant_id,
                        StrategicGateDecision.project_proposal_id == proposal.id,
                        StrategicGateDecision.gate_type == preview.gate_type,
                    )
                )
                or 0
            )
            + 1
        )
        authority = dict(effective.get("decision_authority", {}))
        maker_id = self.actor_id if authority.get("mode", "SINGLE_DECISION_MAKER") == "SINGLE_DECISION_MAKER" else None
        return StrategicGateDecision(
            tenant_id=self.tenant_id,
            decision_number=self._reserve_number(),
            context_type="PROJECT_PROPOSAL",
            context_id=proposal.id,
            project_proposal_id=proposal.id,
            gate_type=preview.gate_type,
            gate_round=round_number,
            state="DRAFT",
            outcome=None,
            proposal_status_at_entry=proposal.status,
            proposal_readiness_status=str(preview.readiness.get("status", "")),
            proposal_readiness_hash=str(preview.readiness.get("readiness_hash", "")),
            proposal_readiness_snapshot_json=self._json_safe(preview.readiness),
            proposal_snapshot_json=self._json_safe(preview.project_proposal),
            source_idea_snapshot_json=self._json_safe(preview.source_idea),
            accepted_idea_evaluation_snapshot_json=self._json_safe(preview.accepted_idea_evaluation),
            proposal_evaluation_snapshot_json=self._json_safe(preview.proposal_evaluation),
            source_idea_id=proposal.source_idea_id,
            accepted_idea_evaluation_id=proposal.accepted_idea_evaluation_id,
            proposal_evaluation_id=evaluation.id,
            owning_workspace_id=proposal.owning_workspace_id,
            target_portfolio_workspace_id=proposal.target_portfolio_workspace_id,
            strategic_objectives_snapshot_json=list(preview.strategic_objectives),
            proposal_score=evaluation.total_score,
            proposal_evaluation_revision=evaluation.evaluation_version,
            configuration_id=record.id,
            configuration_revision=record.revision,
            configuration_hash=record.content_hash or self._hash(effective),
            configuration_snapshot_json=self._json_safe(effective),
            decision_criteria_snapshot_json=list(preview.decision_criteria),
            decision_checklist_snapshot_json=list(preview.decision_checklist),
            conditions_json=[],
            evidence_refs_json=list(proposal.attachment_refs_json or []),
            decision_reason="",
            decision_comments="",
            decision_maker_user_id=maker_id,
            committee_snapshot_json=None,
            decision_hash="",
            prepared_by_user_id=self.actor_id,
            prepared_at=utc_now(),
            revision_version=1,
            created_by=self.actor_id,
            updated_by=self.actor_id,
            updated_at=utc_now(),
        )

    def _entry_blockers(
        self,
        proposal: ProjectProposal,
        readiness: dict,
        evaluation: ProjectProposalEvaluation | None,
        idea: Idea,
        idea_evaluation: IdeaEvaluation,
        target: EnterpriseWorkspace | None,
    ) -> list[str]:
        blockers: list[str] = []
        if proposal.status != "READY_FOR_STRATEGIC_GATE":
            blockers.append("PROPOSAL_NOT_READY_FOR_STRATEGIC_GATE")
        if readiness.get("status") != "READY_FOR_STRATEGIC_GATE_DECISION" or not readiness.get(
            "can_enter_strategic_gate"
        ):
            blockers.append("PROPOSAL_READINESS_INVALID")
        blockers.extend(str(item) for item in readiness.get("blockers", []))
        if not readiness.get("readiness_hash"):
            blockers.append("PROPOSAL_READINESS_HASH_MISSING")
        if evaluation is None or readiness.get("proposal_evaluation_id") != evaluation.id:
            blockers.append("PROPOSAL_EVALUATION_STALE")
        if idea.state != "ACCEPTED" or idea.accepted_evaluation_id != idea_evaluation.id:
            blockers.append("SOURCE_IDEA_ACCEPTANCE_INVALID")
        if proposal.owning_workspace_id is None:
            blockers.append("OWNING_WORKSPACE_MISSING")
        if proposal.target_portfolio_workspace_id and (target is None or target.workspace_type_code != "portfolio"):
            blockers.append("TARGET_PORTFOLIO_INVALID")
        if not proposal.sponsor_user_id or not proposal.proposal_owner_user_id:
            blockers.append("SPONSOR_OR_OWNER_MISSING")
        return blockers

    def _readiness(self, proposal: ProjectProposal) -> dict:
        service = ProjectProposalService(self.db, self.tenant_id, self.actor_id, self.context)
        return service.gate_readiness(proposal.id).model_dump(mode="json")

    def _assert_current_readiness(
        self,
        decision: StrategicGateDecision,
        *,
        proposal: ProjectProposal | None = None,
    ) -> None:
        proposal = proposal or self._proposal(decision.project_proposal_id)
        current = self._readiness(proposal)
        if proposal.status != "READY_FOR_STRATEGIC_GATE":
            raise HTTPException(
                status_code=412,
                detail={"reason": "STALE_READINESS", "current_status": proposal.status},
            )
        if current.get("readiness_hash") != decision.proposal_readiness_hash:
            raise HTTPException(
                status_code=412,
                detail={
                    "reason": "STALE_READINESS",
                    "expected_hash": decision.proposal_readiness_hash,
                    "current_hash": current.get("readiness_hash"),
                },
            )
        if current.get("blockers"):
            raise HTTPException(
                status_code=412,
                detail={"reason": "STALE_READINESS", "blockers": current.get("blockers")},
            )

    def _decision_checklist(
        self,
        config: dict,
        proposal: ProjectProposal,
        readiness: dict,
        evaluation: ProjectProposalEvaluation | None,
        target: EnterpriseWorkspace | None,
    ) -> list[dict]:
        statuses = {
            "proposal_readiness_valid": not readiness.get("blockers"),
            "proposal_evaluation_valid": evaluation is not None,
            "business_case_reviewed": bool(proposal.review_completed_at),
            "strategic_alignment_confirmed": bool(proposal.strategic_objective_codes),
            "target_portfolio_confirmed": proposal.target_portfolio_workspace_id is None
            or (target is not None and target.workspace_type_code == "portfolio"),
            "risks_reviewed": bool(proposal.key_risks_json),
            "rom_cost_reviewed": proposal.rom_cost is not None,
            "schedule_assumptions_reviewed": bool(proposal.preliminary_duration_days),
            "sponsor_confirmed": bool(proposal.sponsor_user_id),
            "funding_not_yet_required_acknowledged": True,
        }
        result: list[dict] = []
        for item in config.get("decision_checklist", []):
            code = str(item.get("code", ""))
            passed = bool(statuses.get(code, False))
            result.append(
                {
                    "code": code,
                    "label": item.get("label", code),
                    "status": "PASS" if passed else ("FAIL" if item.get("blocking", True) else "WARNING"),
                    "blocking": bool(item.get("blocking", True)),
                    "evidence": self._checklist_evidence(code, proposal, readiness, evaluation),
                }
            )
        return result

    def _merge_checklist(self, decision: StrategicGateDecision, supplied: list[dict] | None) -> list[dict]:
        stored = [dict(item) for item in decision.decision_checklist_snapshot_json or []]
        if supplied is None:
            return stored
        by_code = {str(item.get("code")): item for item in supplied}
        result: list[dict] = []
        for item in stored:
            override = by_code.get(str(item.get("code")))
            if override:
                status = str(override.get("status", item.get("status", "FAIL"))).upper()
                if status not in {"PASS", "FAIL", "WARNING"}:
                    raise HTTPException(status_code=422, detail="Checklist status must be PASS, FAIL or WARNING")
                item["status"] = status
                item["evidence"] = str(override.get("evidence", item.get("evidence", "")))[:2000]
            result.append(item)
        return result

    def _validate_authority(
        self,
        decision: StrategicGateDecision,
        proposal: ProjectProposal,
        config: dict,
        committee: dict | None,
    ) -> int:
        authority = dict(config.get("decision_authority", {}))
        mode = str(authority.get("mode", "SINGLE_DECISION_MAKER"))
        maker_id = decision.decision_maker_user_id or self.actor_id
        if mode == "SINGLE_DECISION_MAKER":
            if maker_id != self.actor_id:
                raise HTTPException(status_code=403, detail="Only the assigned Decision Maker may decide")
            self._user(maker_id)
        elif mode == "COMMITTEE":
            if not committee:
                raise HTTPException(status_code=422, detail="Committee snapshot is required")
            members = list(committee.get("members", []))
            votes = list(committee.get("votes", []))
            member_ids = {int(item.get("user_id")) for item in members if item.get("user_id")}
            if self.actor_id not in member_ids:
                raise HTTPException(status_code=403, detail="Decision actor is not a committee member")
            quorum_required = int(
                committee.get(
                    "quorum_required",
                    config.get("committee_policy", {}).get("quorum_required", 1),
                )
            )
            voters = {int(item.get("user_id")) for item in votes if item.get("user_id") in member_ids}
            if len(voters) < quorum_required:
                raise HTTPException(
                    status_code=422,
                    detail={"reason": "QUORUM_NOT_MET", "required": quorum_required, "actual": len(voters)},
                )
            committee["quorum_met"] = True
            maker_id = self.actor_id
        else:
            raise HTTPException(status_code=422, detail="Unsupported Decision Authority mode")
        evaluation = self._latest_proposal_evaluation(proposal.id)
        four_eyes = dict(config.get("four_eyes", {}))
        if four_eyes.get("decision_maker_cannot_be_proposal_creator") and maker_id == proposal.created_by:
            raise HTTPException(status_code=403, detail="Four-Eyes blocks the Proposal creator from deciding")
        if (
            four_eyes.get("decision_maker_cannot_be_proposal_evaluator")
            and evaluation is not None
            and maker_id == evaluation.evaluator_user_id
        ):
            raise HTTPException(status_code=403, detail="SoD blocks the Proposal evaluator from deciding")
        return maker_id

    def _required_field_blockers(self, decision: StrategicGateDecision) -> list[str]:
        required = list(decision.configuration_snapshot_json.get("required_fields", []))
        values = {
            "decision_reason": decision.decision_reason,
            "decision_maker_user_id": decision.decision_maker_user_id,
            "committee_snapshot_json": decision.committee_snapshot_json,
        }
        return [item for item in required if not values.get(item)]

    def _effective_configuration(
        self,
        workspace: EnterpriseWorkspace,
    ) -> tuple[dict, dict, list[EnterpriseWorkspace], AdminConfiguration]:
        selected = self._latest_configuration("default")
        if selected is None:
            raise HTTPException(status_code=409, detail="No published Strategic Gate configuration")
        path = self._workspace_path(workspace)
        for item in path:
            candidate = self._latest_configuration(f"workspace-{item.id}")
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
        return dict(selected.content_json), {"strategic_gate_configuration": source}, path, selected

    def _latest_configuration(self, code: str) -> AdminConfiguration | None:
        return self.db.scalar(
            select(AdminConfiguration)
            .where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == "strategic_gate_configuration",
                AdminConfiguration.code == code,
                AdminConfiguration.status == "published",
            )
            .order_by(AdminConfiguration.revision.desc())
            .limit(1)
        )

    def _seed_configuration(self, code: str, name: str, content: dict) -> None:
        self.db.add(
            AdminConfiguration(
                tenant_id=self.tenant_id,
                kind="strategic_gate_configuration",
                code=code,
                name=name,
                description="Gate 07C governed default",
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
                AdminConfiguration.kind == "strategic_gate_configuration",
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail="Strategic Gate configuration not found")
        return record

    @staticmethod
    def _validate_configuration_content(content: dict) -> None:
        if int(content.get("max_active_gate_decisions_per_proposal", 1)) != 1:
            raise HTTPException(status_code=422, detail="Gate 07C currently requires one active Decision")
        if content.get("context_type", "PROJECT_PROPOSAL") != "PROJECT_PROPOSAL":
            raise HTTPException(status_code=422, detail="Only PROJECT_PROPOSAL context is operational")
        if content.get("gate_type", "PROJECT_PROPOSAL_GATE") != "PROJECT_PROPOSAL_GATE":
            raise HTTPException(status_code=422, detail="Only PROJECT_PROPOSAL_GATE is operational")
        if not isinstance(content.get("decision_checklist"), list):
            raise HTTPException(status_code=422, detail="Decision checklist is required")
        if not isinstance(content.get("decision_criteria"), list):
            raise HTTPException(status_code=422, detail="Decision criteria are required")
        mode = content.get("decision_authority", {}).get("mode")
        if mode not in {"SINGLE_DECISION_MAKER", "COMMITTEE"}:
            raise HTTPException(status_code=422, detail="Invalid Decision Authority mode")

    def _decision(self, decision_id: int, *, for_update: bool = False) -> StrategicGateDecision:
        statement = select(StrategicGateDecision).where(
            StrategicGateDecision.id == decision_id,
            StrategicGateDecision.tenant_id == self.tenant_id,
        )
        if for_update:
            statement = statement.with_for_update()
        decision = self.db.scalar(statement)
        if decision is None or not self._can_access_decision(decision):
            raise HTTPException(status_code=404, detail="Strategic Gate Decision not found")
        return decision

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

    def _active_decision(
        self,
        proposal_id: int,
        gate_type: str,
        *,
        for_update: bool = False,
    ) -> StrategicGateDecision | None:
        statement = select(StrategicGateDecision).where(
            StrategicGateDecision.tenant_id == self.tenant_id,
            StrategicGateDecision.project_proposal_id == proposal_id,
            StrategicGateDecision.gate_type == gate_type,
            StrategicGateDecision.state.in_(ACTIVE_STATES),
        )
        if for_update:
            statement = statement.with_for_update()
        return self.db.scalar(statement.order_by(StrategicGateDecision.id).limit(1))

    def _idea(self, idea_id: int) -> Idea:
        idea = self.db.scalar(select(Idea).where(Idea.id == idea_id, Idea.tenant_id == self.tenant_id))
        if idea is None:
            raise HTTPException(status_code=404, detail="Source Idea not found")
        return idea

    def _idea_evaluation(self, evaluation_id: int, idea_id: int) -> IdeaEvaluation:
        evaluation = self.db.scalar(
            select(IdeaEvaluation).where(
                IdeaEvaluation.id == evaluation_id,
                IdeaEvaluation.idea_id == idea_id,
                IdeaEvaluation.tenant_id == self.tenant_id,
            )
        )
        if evaluation is None:
            raise HTTPException(status_code=409, detail="Accepted Idea evaluation is missing")
        return evaluation

    def _latest_proposal_evaluation(self, proposal_id: int) -> ProjectProposalEvaluation | None:
        return self.db.scalar(
            select(ProjectProposalEvaluation)
            .where(
                ProjectProposalEvaluation.tenant_id == self.tenant_id,
                ProjectProposalEvaluation.project_proposal_id == proposal_id,
            )
            .order_by(ProjectProposalEvaluation.evaluation_version.desc())
            .limit(1)
        )

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
            raise HTTPException(status_code=422, detail="Invalid owning Workspace for Strategic Gate")
        if not self.context.organization_wide and workspace.id not in self.context.workspace_ids:
            raise HTTPException(status_code=404, detail="Owning Workspace not authorized")
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

    def _users(self) -> list[UserAccount]:
        return list(
            self.db.scalars(
                select(UserAccount)
                .where(UserAccount.tenant_id == self.tenant_id, UserAccount.status == "active")
                .order_by(UserAccount.full_name)
            ).all()
        )

    def _user(self, user_id: int) -> UserAccount:
        user = self.db.scalar(
            select(UserAccount).where(
                UserAccount.id == user_id,
                UserAccount.tenant_id == self.tenant_id,
                UserAccount.status == "active",
            )
        )
        if user is None:
            raise HTTPException(status_code=422, detail="Decision actor is inactive or cross-tenant")
        return user

    def _proposal_scope(self, statement):
        if self.context.organization_wide:
            return statement
        allowed = list(self.context.workspace_ids)
        return statement.where(
            (ProjectProposal.created_by == self.actor_id)
            | (ProjectProposal.proposal_owner_user_id == self.actor_id)
            | (ProjectProposal.owning_workspace_id.in_(allowed) if allowed else False)
        )

    def _decision_scope(self, statement):
        if self.context.organization_wide:
            return statement
        allowed = list(self.context.workspace_ids)
        return statement.where(
            (StrategicGateDecision.prepared_by_user_id == self.actor_id)
            | (StrategicGateDecision.decision_maker_user_id == self.actor_id)
            | (StrategicGateDecision.owning_workspace_id.in_(allowed) if allowed else False)
        )

    def _can_access_proposal(self, proposal: ProjectProposal) -> bool:
        return self.context.organization_wide or (
            proposal.created_by == self.actor_id
            or proposal.proposal_owner_user_id == self.actor_id
            or proposal.owning_workspace_id in self.context.workspace_ids
        )

    def _can_access_decision(self, decision: StrategicGateDecision) -> bool:
        return self.context.organization_wide or (
            decision.prepared_by_user_id == self.actor_id
            or decision.decision_maker_user_id == self.actor_id
            or decision.owning_workspace_id in self.context.workspace_ids
        )

    def _sequence(self, *, required: bool = True) -> AdminNumberSequence | None:
        sequence = self.db.scalar(
            select(AdminNumberSequence).where(
                AdminNumberSequence.tenant_id == self.tenant_id,
                AdminNumberSequence.rule_code == DECISION_NUMBER_RULE,
                AdminNumberSequence.scope_key == "tenant",
            )
        )
        if sequence is None and required:
            raise HTTPException(status_code=409, detail="Strategic Gate numbering is not initialized")
        return sequence

    def _preview_number(self) -> str:
        sequence = self._sequence()
        return f"SGD-{sequence.next_value:05d}"

    def _reserve_number(self) -> str:
        result = self.db.execute(
            update(AdminNumberSequence)
            .where(
                AdminNumberSequence.tenant_id == self.tenant_id,
                AdminNumberSequence.rule_code == DECISION_NUMBER_RULE,
                AdminNumberSequence.scope_key == "tenant",
            )
            .values(
                next_value=AdminNumberSequence.next_value + 1,
                version=AdminNumberSequence.version + 1,
                updated_at=utc_now(),
            )
            .returning(AdminNumberSequence.next_value)
        ).scalar_one()
        return f"SGD-{int(result) - 1:05d}"

    def _transition(
        self,
        decision: StrategicGateDecision,
        target: str,
        event_type: str,
        *,
        metadata: dict | None = None,
        **timestamps,
    ) -> StrategicGateDecisionOut:
        before = decision.state
        decision.state = target
        for key, value in timestamps.items():
            setattr(decision, key, value)
        self._touch(decision)
        self._event(event_type, decision, before, target, metadata)
        return self._commit(decision)

    def _touch(self, decision: StrategicGateDecision) -> None:
        decision.updated_by = self.actor_id
        decision.updated_at = utc_now()

    @staticmethod
    def _check_version(decision: StrategicGateDecision, expected: int) -> None:
        if decision.revision_version != expected:
            raise HTTPException(
                status_code=412,
                detail={
                    "reason": "ETAG_MISMATCH",
                    "current_version": decision.revision_version,
                    "expected_version": expected,
                },
            )

    @staticmethod
    def _check_configuration_version(record: AdminConfiguration, expected: int) -> None:
        if record.version != expected:
            raise HTTPException(
                status_code=412,
                detail={
                    "reason": "ETAG_MISMATCH",
                    "current_version": record.version,
                    "expected_version": expected,
                },
            )

    def _commit(self, decision: StrategicGateDecision) -> StrategicGateDecisionOut:
        self.db.commit()
        self.db.refresh(decision)
        return self._out(decision)

    def _event(
        self,
        event_type: str,
        decision: StrategicGateDecision,
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
                target_type="StrategicGateDecision",
                target_id=decision.id,
                metadata_json={
                    "state_before": state_before,
                    "state_after": state_after,
                    "decision_number": decision.decision_number,
                    **(metadata or {}),
                },
            )
        )

    def _proposal_event(
        self,
        proposal: ProjectProposal,
        before: str,
        after: str,
        decision: StrategicGateDecision,
    ) -> None:
        self.db.add(
            SecurityEvent(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                event_type=f"project_proposal.strategic_gate_{decision.outcome.lower()}",
                outcome="success",
                target_type="ProjectProposal",
                target_id=proposal.id,
                metadata_json={
                    "state_before": before,
                    "state_after": after,
                    "strategic_gate_decision_id": decision.id,
                    "decision_number": decision.decision_number,
                    "decision_hash": decision.decision_hash,
                },
            )
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

    def _out(self, decision: StrategicGateDecision) -> StrategicGateDecisionOut:
        proposal = self._proposal(decision.project_proposal_id)
        owning = self._workspace(decision.owning_workspace_id)
        target = (
            self._workspace(decision.target_portfolio_workspace_id) if decision.target_portfolio_workspace_id else None
        )
        maker = self.db.get(UserAccount, decision.decision_maker_user_id) if decision.decision_maker_user_id else None
        preparer = self.db.get(UserAccount, decision.prepared_by_user_id)
        return StrategicGateDecisionOut(
            id=decision.id,
            decision_number=decision.decision_number,
            context_type=decision.context_type,
            context_id=decision.context_id,
            project_proposal_id=decision.project_proposal_id,
            project_proposal_number=proposal.proposal_number,
            project_proposal_name=proposal.name,
            gate_type=decision.gate_type,
            gate_round=decision.gate_round,
            state=StrategicGateState(decision.state),
            outcome=StrategicGateOutcome(decision.outcome) if decision.outcome else None,
            proposal_status_at_entry=decision.proposal_status_at_entry,
            proposal_readiness_status=decision.proposal_readiness_status,
            proposal_readiness_hash=decision.proposal_readiness_hash,
            proposal_readiness_snapshot=dict(decision.proposal_readiness_snapshot_json or {}),
            proposal_snapshot=dict(decision.proposal_snapshot_json or {}),
            source_idea_snapshot=dict(decision.source_idea_snapshot_json or {}),
            accepted_idea_evaluation_snapshot=dict(decision.accepted_idea_evaluation_snapshot_json or {}),
            proposal_evaluation_snapshot=dict(decision.proposal_evaluation_snapshot_json or {}),
            source_idea_id=decision.source_idea_id,
            accepted_idea_evaluation_id=decision.accepted_idea_evaluation_id,
            proposal_evaluation_id=decision.proposal_evaluation_id,
            owning_workspace_id=decision.owning_workspace_id,
            owning_workspace_name=owning.name,
            target_portfolio_workspace_id=decision.target_portfolio_workspace_id,
            target_portfolio_name=target.name if target else None,
            strategic_objectives_snapshot=list(decision.strategic_objectives_snapshot_json or []),
            proposal_score=decision.proposal_score,
            proposal_evaluation_revision=decision.proposal_evaluation_revision,
            configuration_id=decision.configuration_id,
            configuration_revision=decision.configuration_revision,
            configuration_hash=decision.configuration_hash,
            configuration_snapshot=dict(decision.configuration_snapshot_json or {}),
            decision_criteria_snapshot=list(decision.decision_criteria_snapshot_json or []),
            decision_checklist_snapshot=list(decision.decision_checklist_snapshot_json or []),
            conditions=list(decision.conditions_json or []),
            evidence_refs=list(decision.evidence_refs_json or []),
            decision_reason=decision.decision_reason,
            decision_comments=decision.decision_comments,
            decision_maker_user_id=decision.decision_maker_user_id,
            decision_maker_name=maker.full_name if maker else None,
            committee_snapshot=dict(decision.committee_snapshot_json) if decision.committee_snapshot_json else None,
            decision_hash=decision.decision_hash,
            prepared_by_user_id=decision.prepared_by_user_id,
            prepared_by_name=preparer.full_name if preparer else "Unknown",
            prepared_at=decision.prepared_at,
            submitted_at=decision.submitted_at,
            review_started_at=decision.review_started_at,
            decided_at=decision.decided_at,
            deferred_until=decision.deferred_until,
            voided_at=decision.voided_at,
            allowed_actions=self._allowed_actions(decision),
            revision_version=decision.revision_version,
            created_at=decision.created_at,
            updated_at=decision.updated_at,
        )

    def _allowed_actions(self, decision: StrategicGateDecision) -> list[str]:
        admin = self.context.organization_wide or "organization_admin" in self.context.role_codes
        roles = self.context.role_codes
        actions: list[str] = []
        if decision.state == "DRAFT" and (admin or "gate_preparer" in roles):
            actions += ["edit", "submit", "void"]
        if decision.state == "SUBMITTED" and (admin or "gate_reviewer" in roles):
            actions += ["start_review", "return_to_preparer", "void"]
        if decision.state == "IN_REVIEW" and (admin or "gate_decision_maker" in roles):
            actions += ["decide", "return_to_preparer", "void"]
        if (
            decision.state == "DECIDED"
            and decision.outcome in {"RETURN", "DEFER"}
            and (admin or "gate_preparer" in roles)
        ):
            actions.append("create_new_round")
        return actions

    @staticmethod
    def _proposal_snapshot(proposal: ProjectProposal) -> dict:
        return {
            "id": proposal.id,
            "proposal_number": proposal.proposal_number,
            "name": proposal.name,
            "status": proposal.status,
            "business_need": proposal.business_need,
            "business_justification": proposal.business_justification,
            "preliminary_scope": proposal.preliminary_scope,
            "expected_benefits": proposal.expected_benefits,
            "rom_cost": str(proposal.rom_cost) if proposal.rom_cost is not None else None,
            "currency_code": proposal.currency_code,
            "preliminary_duration_days": proposal.preliminary_duration_days,
            "sponsor_user_id": proposal.sponsor_user_id,
            "proposal_owner_user_id": proposal.proposal_owner_user_id,
            "revision_version": proposal.revision_version,
            "mapping_hash": proposal.mapping_hash,
        }

    @staticmethod
    def _idea_snapshot(idea: Idea) -> dict:
        return {
            "id": idea.id,
            "idea_number": idea.idea_number,
            "title": idea.title,
            "state": idea.state,
            "owning_workspace_id": idea.owning_workspace_id,
            "accepted_evaluation_id": idea.accepted_evaluation_id,
        }

    @staticmethod
    def _idea_evaluation_snapshot(evaluation: IdeaEvaluation) -> dict:
        return {
            "id": evaluation.id,
            "evaluation_version": evaluation.evaluation_version,
            "total_score": str(evaluation.total_score),
            "result": evaluation.result,
            "created_at": evaluation.created_at.isoformat(),
        }

    @staticmethod
    def _proposal_evaluation_snapshot(evaluation: ProjectProposalEvaluation | None) -> dict:
        if evaluation is None:
            return {}
        return {
            "id": evaluation.id,
            "evaluation_version": evaluation.evaluation_version,
            "matrix_configuration_id": evaluation.matrix_configuration_id,
            "matrix_revision": evaluation.matrix_revision,
            "matrix_hash": evaluation.matrix_hash,
            "total_score": str(evaluation.total_score),
            "recommendation": evaluation.recommendation,
            "evaluator_user_id": evaluation.evaluator_user_id,
            "created_at": evaluation.created_at.isoformat(),
        }

    @staticmethod
    def _strategic_objectives_snapshot(proposal: ProjectProposal) -> list[dict]:
        return [{"code": code} for code in proposal.strategic_objective_codes or []]

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
    def _checklist_evidence(
        code: str,
        proposal: ProjectProposal,
        readiness: dict,
        evaluation: ProjectProposalEvaluation | None,
    ) -> str:
        evidence = {
            "proposal_readiness_valid": str(readiness.get("readiness_hash", "")),
            "proposal_evaluation_valid": f"evaluation:{evaluation.id}" if evaluation else "missing",
            "business_case_reviewed": str(proposal.review_completed_at or "missing"),
            "strategic_alignment_confirmed": ", ".join(proposal.strategic_objective_codes or []),
            "target_portfolio_confirmed": str(proposal.target_portfolio_workspace_id or "optional"),
            "risks_reviewed": f"{len(proposal.key_risks_json or [])} risk(s)",
            "rom_cost_reviewed": str(proposal.rom_cost or "not available"),
            "schedule_assumptions_reviewed": str(proposal.preliminary_duration_days or "not available"),
            "sponsor_confirmed": f"user:{proposal.sponsor_user_id}",
            "funding_not_yet_required_acknowledged": "Gate 07C does not authorize funding",
        }
        return evidence.get(code, "")[:2000]

    def _decision_hash(self, decision: StrategicGateDecision) -> str:
        return self._hash(
            {
                "decision_id": decision.id,
                "decision_number": decision.decision_number,
                "project_proposal_id": decision.project_proposal_id,
                "gate_round": decision.gate_round,
                "outcome": decision.outcome,
                "reason": decision.decision_reason,
                "conditions": decision.conditions_json,
                "maker": decision.decision_maker_user_id,
                "committee": decision.committee_snapshot_json,
                "proposal_readiness_hash": decision.proposal_readiness_hash,
                "configuration_hash": decision.configuration_hash,
                "decided_at": decision.decided_at,
            }
        )

    @staticmethod
    def _hash(value: object) -> str:
        return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode()).hexdigest()

    @staticmethod
    def _json_safe(value: object) -> dict:
        return json.loads(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str))
