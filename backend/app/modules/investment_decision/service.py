"""Gate 07K governed Investment Decision and FID service.

The service consumes only a frozen Gate 07J preparation.  It deliberately
stops before Project creation/activation, contracting, accounting, payment,
NTP or execution.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from decimal import Decimal
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domain.models import AdminConfiguration, AdminNumberSequence, SecurityEvent, UserAccount
from app.modules.investment_decision.models import InvestmentDecision, InvestmentDecisionVote
from app.modules.investment_decision.schemas import (
    ConfigurationPreviewOut,
    DecisionCreateIn,
    DecisionDecideIn,
    DecisionHistoryItemOut,
    DecisionReadinessOut,
    DecisionReadyIn,
    DecisionUpdateIn,
    DecisionVoteIn,
    DecisionVoteOut,
    InvestmentDecisionOut,
)
from app.modules.investment_gate_preparation.models import InvestmentGatePreparation
from app.modules.investment_gate_preparation.service import InvestmentGatePreparationService

CONFIGURATION_KIND = "investment_decision_configuration"
NUMBER_RULE = "investment-decision"
READY_OUTPUT = "READY_FOR_INVESTMENT_DECISION"
POST_FID_OUTPUT = "READY_FOR_POST_FID_PROJECT_GOVERNANCE"
INVESTMENT_CONTINUATION_OUTPUT = "AUTHORIZED_TO_CONTINUE_PROJECT_DEVELOPMENT"
FID_OUTPUT = "FINAL_INVESTMENT_DECISION_GO"
REWORK_OUTPUT = "INVESTMENT_DECISION_REWORK_REQUIRED"

ACTIVE_STATES = frozenset({"DRAFT", "SUBMITTED", "IN_REVIEW", "READY_FOR_DECISION"})
OUTCOMES = frozenset({"GO", "HOLD", "RECYCLE", "KILL"})
RECYCLE_TARGETS = [
    "PORTFOLIO_SCENARIO_CONVERGENCE",
    "INVESTMENT_GATE_PREPARATION",
    "PROJECT_DEFINITION_FEL",
    "FUNDING_READINESS",
    "RISK_READINESS",
    "PERMIT_READINESS",
]


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


DEFAULT_CONFIGURATION: dict[str, Any] = {
    "applicable_governance_models": ["CAPITAL_OWNER"],
    "profiles": {
        "PYP-INV-SELECT": {
            "purpose": "INVESTMENT_SELECTION",
            "go_output": INVESTMENT_CONTINUATION_OUTPUT,
            "go_is_fid": False,
            "full_funds_required": False,
        },
        "PYP-FFA": {
            "purpose": "FULL_FUNDS_AUTHORIZATION",
            "go_output": "FINAL_INVESTMENT_DECISION_GO",
            "go_is_fid": True,
            "full_funds_required": True,
        },
    },
    "outcomes": ["GO", "HOLD", "RECYCLE", "KILL"],
    "authority": {
        "model": "SINGLE_DECISION_MAKER",
        "allowed_role": "investment_decision_maker",
    },
    "authority_limits": {"enabled": False, "limits": []},
    "committee": {"members": [], "chair_user_id": None},
    "quorum": {"minimum_member_count": 1, "minimum_percentage": 50, "chair_required": False},
    "voting_rule": {"rule": "SIMPLE_MAJORITY", "supermajority_percentage": 66.67},
    "segregation_of_duties": {
        "PYP-INV-SELECT": {"decision_maker_differs_from_preparation_creator": False},
        "PYP-FFA": {
            "decision_maker_differs_from_preparation_creator": True,
            "decision_maker_differs_from_preparation_last_modifier": True,
            "silent_admin_bypass": False,
        },
    },
    "decision_checklist": [
        {"code": "package_reviewed", "label": "Frozen decision package reviewed", "blocking": True},
        {"code": "scope_confirmed", "label": "Exact Project Set scope confirmed", "blocking": True},
        {"code": "evidence_reviewed", "label": "Evidence, blockers and warnings reviewed", "blocking": True},
        {"code": "conditions_acknowledged", "label": "Input conditions acknowledged", "blocking": True},
        {"code": "authority_confirmed", "label": "Decision authority confirmed", "blocking": True},
    ],
    "conditions": {"allow_go_conditions": True, "open_input_blockers_prohibit_entry": True},
    "recycle_targets": RECYCLE_TARGETS,
    "fid_rules": {
        "fid_profile": "PYP-FFA",
        "fid_outcome": "GO",
        "require_authorized_amount": True,
        "require_currency": True,
    },
    "authorization_output": {
        "can_activate_project": False,
        "can_create_project": False,
        "can_issue_ntp": False,
        "can_execute": False,
    },
    "validity": {"authorization_validity_days": None, "reauthorization_requires_new_round": True},
    "numbering": {"prefix": "IDEC-", "padding": 5},
    "inheritance": {"inherit_to_descendants": True},
}


class InvestmentDecisionService:
    def __init__(self, db: Session, tenant_id: int, actor_id: int, context=None) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.actor_id = actor_id
        self.context = context

    # Bootstrap/configuration ------------------------------------
    def ensure_seed(self) -> None:
        changed = False
        if self._published_configuration(required=False) is None:
            content = deepcopy(DEFAULT_CONFIGURATION)
            self.db.add(
                AdminConfiguration(
                    tenant_id=self.tenant_id,
                    kind=CONFIGURATION_KIND,
                    code="default",
                    name="Default Investment Decision / FID Governance",
                    description="Gate 07K governed decision authority, outcomes, voting, SoD and FID semantics.",
                    status="published",
                    revision=1,
                    version=1,
                    content_json=content,
                    content_hash=_hash(content),
                    published_at=utc_now(),
                    created_by_user_id=self.actor_id,
                )
            )
            changed = True
        if self._sequence(required=False) is None:
            self.db.add(
                AdminNumberSequence(
                    tenant_id=self.tenant_id,
                    rule_code=NUMBER_RULE,
                    scope_key="tenant",
                    next_value=1,
                    version=1,
                )
            )
            changed = True
        if changed:
            self._event("investment_decision.configuration_seeded", "AdminConfiguration", None, {})
            self.db.commit()

    def configurations(self) -> list[AdminConfiguration]:
        self.ensure_seed()
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
        portfolio_workspace_id: int | None,
        configuration_id: int | None,
        content_override: dict | None,
    ) -> ConfigurationPreviewOut:
        record = self._configuration(configuration_id) if configuration_id else self._published_configuration()
        content = deepcopy(content_override if content_override is not None else record.content_json)
        issues = self._configuration_issues(content)
        return ConfigurationPreviewOut(
            portfolio_workspace_id=portfolio_workspace_id,
            effective=content,
            validation_issues=issues,
            warnings=["Dry-run only; no Decision, FID, Project, Funds or execution record is persisted."],
            blockers=issues,
            publishable=not issues,
        )

    def clone_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        source = self._configuration(configuration_id)
        self._check_version(
            source.revision_version if hasattr(source, "revision_version") else source.version, expected_version
        )
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
            name=f"{source.name} · draft {revision}",
            description=source.description,
            status="draft",
            revision=revision,
            version=1,
            content_json=deepcopy(source.content_json),
            content_hash=_hash(source.content_json),
            created_by_user_id=self.actor_id,
        )
        self.db.add(clone)
        self.db.flush()
        self._event("investment_decision.configuration_cloned", "AdminConfiguration", clone.id, {})
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
        self._check_version(record.version, expected_version)
        if record.status != "draft":
            raise HTTPException(status_code=409, detail={"code": "PUBLISHED_CONFIGURATION_IMMUTABLE"})
        issues = self._configuration_issues(content)
        if issues:
            raise HTTPException(status_code=422, detail={"code": "INVALID_CONFIGURATION", "issues": issues})
        record.name = name
        record.description = description
        record.content_json = deepcopy(content)
        record.content_hash = _hash(content)
        record.version += 1
        record.updated_at = utc_now()
        self._event("investment_decision.configuration_updated", "AdminConfiguration", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return record

    def publish_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        record = self._configuration(configuration_id, lock=True)
        self._check_version(record.version, expected_version)
        if record.status == "published":
            return record
        issues = self._configuration_issues(record.content_json)
        if issues:
            raise HTTPException(status_code=422, detail={"code": "INVALID_CONFIGURATION", "issues": issues})
        record.status = "published"
        record.content_hash = _hash(record.content_json)
        record.published_at = utc_now()
        record.version += 1
        record.updated_at = utc_now()
        self._event("investment_decision.configuration_published", "AdminConfiguration", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return record

    # Decision lifecycle ----------------------------------------
    def create(self, payload: DecisionCreateIn) -> InvestmentDecisionOut:
        duplicate = self.db.scalar(
            select(InvestmentDecision).where(
                InvestmentDecision.tenant_id == self.tenant_id,
                InvestmentDecision.create_idempotency_key == payload.idempotency_key,
            )
        )
        if duplicate is not None:
            return self._out(duplicate)
        preparation = self._preparation(payload.investment_gate_preparation_id, lock=True)
        handoff = self._validate_entry(preparation)
        active = self.db.scalar(
            select(InvestmentDecision).where(
                InvestmentDecision.tenant_id == self.tenant_id,
                InvestmentDecision.investment_gate_preparation_id == preparation.id,
                InvestmentDecision.profile_code == preparation.profile_code,
                InvestmentDecision.status.in_(ACTIVE_STATES),
            )
        )
        if active is not None:
            return self._out(active)
        config = (
            self._configuration(payload.configuration_id)
            if payload.configuration_id
            else self._published_configuration()
        )
        if config.status != "published":
            raise HTTPException(status_code=409, detail={"code": "PUBLISHED_DECISION_CONFIGURATION_REQUIRED"})
        round_number = (
            int(
                self.db.scalar(
                    select(func.coalesce(func.max(InvestmentDecision.decision_round), 0)).where(
                        InvestmentDecision.tenant_id == self.tenant_id,
                        InvestmentDecision.investment_gate_preparation_id == preparation.id,
                        InvestmentDecision.profile_code == preparation.profile_code,
                    )
                )
                or 0
            )
            + 1
        )
        content = deepcopy(config.content_json)
        authority = deepcopy(content.get("authority", {}))
        package = self._decision_package(preparation, handoff, content)
        now = utc_now()
        record = InvestmentDecision(
            tenant_id=self.tenant_id,
            decision_number=self._next_number(content),
            investment_gate_preparation_id=preparation.id,
            portfolio_workspace_id=preparation.portfolio_workspace_id,
            investment_gate_profile_id=preparation.investment_gate_profile_id,
            profile_code=preparation.profile_code,
            decision_round=round_number,
            decision_scope_hash=preparation.recommended_project_set_hash,
            title=payload.title,
            executive_summary=payload.executive_summary,
            conditions_json=deepcopy(preparation.conditions_json or []),
            source_preparation_hash=str(preparation.preparation_hash),
            source_package_hash=_hash(package),
            source_profile_hash=preparation.profile_hash,
            source_policy_hash=dict(preparation.source_snapshot_json.get("evidence_policy") or {}).get("policy_hash"),
            decision_package_snapshot_json=package,
            configuration_id=config.id,
            configuration_revision=config.revision,
            configuration_hash=config.content_hash,
            configuration_snapshot_json=content,
            authority_model=str(authority.get("model", "SINGLE_DECISION_MAKER")),
            authority_snapshot_json=authority,
            committee_snapshot_json=deepcopy(content.get("committee", {})),
            quorum_snapshot_json=deepcopy(content.get("quorum", {})),
            voting_rule_snapshot_json=deepcopy(content.get("voting_rule", {})),
            checklist_snapshot_json=[
                {**item, "acknowledged": False, "note": ""} for item in content.get("decision_checklist", [])
            ],
            create_idempotency_key=payload.idempotency_key,
            created_by=self.actor_id,
            created_at=now,
            updated_by=self.actor_id,
            updated_at=now,
        )
        self.db.add(record)
        self.db.flush()
        self._event(
            "investment_decision.created",
            "InvestmentDecision",
            record.id,
            {"preparation_hash": record.source_preparation_hash, "package_hash": record.source_package_hash},
        )
        self.db.commit()
        self.db.refresh(record)
        return self._out(record)

    def list(
        self,
        *,
        status: str = "",
        outcome: str = "",
        profile_code: str = "",
        portfolio_workspace_id: int | None = None,
        queue: str = "",
    ) -> list[InvestmentDecisionOut]:
        statement = select(InvestmentDecision).where(InvestmentDecision.tenant_id == self.tenant_id)
        if status:
            statement = statement.where(InvestmentDecision.status == status.upper())
        if outcome:
            statement = statement.where(InvestmentDecision.outcome == outcome.upper())
        if profile_code:
            statement = statement.where(InvestmentDecision.profile_code == profile_code.upper())
        if portfolio_workspace_id:
            statement = statement.where(InvestmentDecision.portfolio_workspace_id == portfolio_workspace_id)
        if queue == "mine":
            statement = statement.where(
                (InvestmentDecision.created_by == self.actor_id)
                | (InvestmentDecision.decision_maker_user_id == self.actor_id)
            )
        if queue == "ready":
            statement = statement.where(InvestmentDecision.status == "READY_FOR_DECISION")
        rows = self.db.scalars(statement.order_by(InvestmentDecision.updated_at.desc())).all()
        return [self._out(item) for item in rows]

    def get(self, decision_id: int) -> InvestmentDecisionOut:
        return self._out(self._decision(decision_id))

    def update(self, decision_id: int, expected_version: int, payload: DecisionUpdateIn) -> InvestmentDecisionOut:
        record = self._decision(decision_id, lock=True)
        self._check_version(record.revision_version, expected_version)
        if record.status != "DRAFT":
            raise HTTPException(status_code=409, detail={"code": "DRAFT_DECISION_REQUIRED"})
        values = payload.model_dump(exclude_unset=True)
        if "title" in values:
            record.title = values["title"]
        if "executive_summary" in values:
            record.executive_summary = values["executive_summary"]
        if "rationale" in values:
            record.rationale = values["rationale"]
        if "conditions" in values:
            record.conditions_json = values["conditions"]
        if "decision_maker_user_id" in values:
            self._user(values["decision_maker_user_id"])
            record.decision_maker_user_id = values["decision_maker_user_id"]
        if "committee" in values:
            record.committee_snapshot_json = self._validated_committee(values["committee"])
        self._touch(record)
        self._event("investment_decision.updated", "InvestmentDecision", record.id, {})
        return self._commit(record)

    def submit(self, decision_id: int, expected_version: int, idempotency_key: str) -> InvestmentDecisionOut:
        return self._transition(
            decision_id,
            expected_version,
            idempotency_key,
            expected="DRAFT",
            target="SUBMITTED",
            event="investment_decision.submitted",
            timestamp="submitted_at",
        )

    def start_review(self, decision_id: int, expected_version: int, idempotency_key: str) -> InvestmentDecisionOut:
        return self._transition(
            decision_id,
            expected_version,
            idempotency_key,
            expected="SUBMITTED",
            target="IN_REVIEW",
            event="investment_decision.review_started",
            timestamp="review_started_at",
        )

    def ready(
        self,
        decision_id: int,
        expected_version: int,
        payload: DecisionReadyIn,
    ) -> InvestmentDecisionOut:
        record = self._decision(decision_id, lock=True)
        if record.status == "READY_FOR_DECISION":
            return self._out(record)
        self._check_version(record.revision_version, expected_version)
        if record.status != "IN_REVIEW":
            raise HTTPException(status_code=409, detail={"code": "IN_REVIEW_DECISION_REQUIRED"})
        self._assert_current(record)
        acknowledgement = {item.code: item for item in payload.checklist}
        checklist = []
        for item in record.checklist_snapshot_json or []:
            answer = acknowledgement.get(str(item.get("code")))
            checklist.append(
                {
                    **item,
                    "acknowledged": bool(answer and answer.acknowledged),
                    "note": answer.note if answer else "",
                }
            )
        record.checklist_snapshot_json = checklist
        readiness = self._readiness(record)
        if readiness.blockers:
            raise HTTPException(
                status_code=409,
                detail={"code": "DECISION_NOT_READY", "blockers": readiness.blockers},
            )
        record.status = "READY_FOR_DECISION"
        record.ready_at = utc_now()
        self._touch(record)
        self._event(
            "investment_decision.ready_for_decision",
            "InvestmentDecision",
            record.id,
            {"idempotency_key": payload.idempotency_key},
        )
        return self._commit(record)

    def cast_vote(self, decision_id: int, payload: DecisionVoteIn) -> InvestmentDecisionOut:
        duplicate = self.db.scalar(
            select(InvestmentDecisionVote).where(
                InvestmentDecisionVote.tenant_id == self.tenant_id,
                InvestmentDecisionVote.idempotency_key == payload.idempotency_key,
            )
        )
        if duplicate is not None:
            return self._out(self._decision(duplicate.investment_decision_id))
        record = self._decision(decision_id, lock=True)
        if record.status not in {"IN_REVIEW", "READY_FOR_DECISION"}:
            raise HTTPException(status_code=409, detail={"code": "VOTING_NOT_OPEN"})
        if record.authority_model != "COMMITTEE":
            raise HTTPException(status_code=409, detail={"code": "COMMITTEE_AUTHORITY_REQUIRED"})
        members = self._committee_members(record)
        if self.actor_id not in {item["user_id"] for item in members if item.get("voting_right", True)}:
            raise HTTPException(status_code=403, detail={"code": "NOT_COMMITTEE_VOTER"})
        vote = self.db.scalar(
            select(InvestmentDecisionVote).where(
                InvestmentDecisionVote.tenant_id == self.tenant_id,
                InvestmentDecisionVote.investment_decision_id == record.id,
                InvestmentDecisionVote.voter_user_id == self.actor_id,
            )
        )
        if vote is None:
            vote = InvestmentDecisionVote(
                tenant_id=self.tenant_id,
                investment_decision_id=record.id,
                voter_user_id=self.actor_id,
                vote=payload.vote,
                rationale=payload.rationale,
                cast_at=utc_now(),
                idempotency_key=payload.idempotency_key,
            )
            self.db.add(vote)
        else:
            vote.vote = payload.vote
            vote.rationale = payload.rationale
            vote.cast_at = utc_now()
            vote.idempotency_key = payload.idempotency_key
            vote.revision_version += 1
        self._event(
            "investment_decision.vote_cast",
            "InvestmentDecision",
            record.id,
            {"voter_user_id": self.actor_id, "vote": payload.vote},
        )
        self.db.commit()
        return self._out(record)

    def decide(
        self,
        decision_id: int,
        expected_version: int,
        payload: DecisionDecideIn,
    ) -> InvestmentDecisionOut:
        payload_hash = _hash(payload.model_dump(mode="json", exclude={"idempotency_key"}))
        duplicate = self.db.scalar(
            select(InvestmentDecision).where(
                InvestmentDecision.tenant_id == self.tenant_id,
                InvestmentDecision.decide_idempotency_key == payload.idempotency_key,
            )
        )
        if duplicate is not None:
            if duplicate.decide_payload_hash != payload_hash:
                raise HTTPException(status_code=409, detail={"code": "IDEMPOTENCY_PAYLOAD_MISMATCH"})
            return self._out(duplicate)
        record = self._decision(decision_id, lock=True)
        if record.status == "DECIDED":
            raise HTTPException(status_code=409, detail={"code": "DECISION_ALREADY_CLOSED"})
        self._check_version(record.revision_version, expected_version)
        if record.status != "READY_FOR_DECISION":
            raise HTTPException(status_code=409, detail={"code": "READY_FOR_DECISION_REQUIRED"})
        self._assert_current(record)
        self._assert_authority(record, payload.outcome)
        if payload.outcome == "RECYCLE" and payload.recycle_target not in list(
            record.configuration_snapshot_json.get("recycle_targets", RECYCLE_TARGETS)
        ):
            raise HTTPException(status_code=422, detail={"code": "INVALID_RECYCLE_TARGET"})
        fid = record.profile_code == "PYP-FFA" and payload.outcome == "GO"
        fid_rules = dict(record.configuration_snapshot_json.get("fid_rules", {}))
        if fid and fid_rules.get("require_authorized_amount", True) and payload.authorized_amount is None:
            raise HTTPException(status_code=422, detail={"code": "AUTHORIZED_AMOUNT_REQUIRED"})
        if fid and fid_rules.get("require_currency", True) and not payload.authorized_currency:
            raise HTTPException(status_code=422, detail={"code": "AUTHORIZED_CURRENCY_REQUIRED"})
        self._assert_authority_limit(record, payload.authorized_amount)
        now = utc_now()
        record.status = "DECIDED"
        record.outcome = payload.outcome
        record.rationale = payload.rationale
        record.conditions_json = self._merge_conditions(record.conditions_json, payload.conditions)
        record.hold_reason = payload.hold_reason
        record.recycle_target = payload.recycle_target
        record.authorized_amount = payload.authorized_amount
        record.authorized_currency = payload.authorized_currency.upper() if payload.authorized_currency else None
        record.authorization_valid_until = payload.authorization_valid_until
        record.decided_at = now
        record.decided_by = self.actor_id
        record.decision_maker_user_id = record.decision_maker_user_id or self.actor_id
        record.is_fid = fid
        record.full_funds_authorized = fid
        record.investment_authorized = fid
        record.decide_idempotency_key = payload.idempotency_key
        record.decide_payload_hash = payload_hash
        record.decision_hash = self._decision_hash(record, now)
        self._touch(record, now=now)
        output = self._authorization_output(record)
        self._event(
            "investment_decision.decided",
            "InvestmentDecision",
            record.id,
            {
                "outcome": record.outcome,
                "is_fid": record.is_fid,
                "decision_hash": record.decision_hash,
                "authorization_output": output,
            },
        )
        if fid:
            self._event(
                "investment_decision.fid_recorded",
                "InvestmentDecision",
                record.id,
                {"full_funds_authorized": True, "can_activate_project": False},
            )
        self.db.commit()
        self.db.refresh(record)
        return self._out(record)

    def void(self, decision_id: int, expected_version: int, idempotency_key: str) -> InvestmentDecisionOut:
        record = self._decision(decision_id, lock=True)
        if record.status == "VOIDED":
            return self._out(record)
        self._check_version(record.revision_version, expected_version)
        if record.status not in ACTIVE_STATES:
            raise HTTPException(status_code=409, detail={"code": "CLOSED_DECISION_IMMUTABLE"})
        before = record.status
        record.status = "VOIDED"
        record.voided_at = utc_now()
        self._touch(record)
        self._event(
            "investment_decision.voided",
            "InvestmentDecision",
            record.id,
            {"from": before, "idempotency_key": idempotency_key},
        )
        return self._commit(record)

    # Read models ------------------------------------------------
    def package(self, decision_id: int) -> dict:
        return deepcopy(self._decision(decision_id).decision_package_snapshot_json or {})

    def committee(self, decision_id: int) -> dict:
        record = self._decision(decision_id)
        return {
            "authority_model": record.authority_model,
            "authority": deepcopy(record.authority_snapshot_json or {}),
            "committee": deepcopy(record.committee_snapshot_json or {}),
            "quorum": deepcopy(record.quorum_snapshot_json or {}),
            "voting_rule": deepcopy(record.voting_rule_snapshot_json or {}),
            "votes": [item.model_dump(mode="json") for item in self._votes_out(record.id)],
        }

    def readiness(self, decision_id: int) -> DecisionReadinessOut:
        return self._readiness(self._decision(decision_id))

    def history(self, decision_id: int) -> list[DecisionHistoryItemOut]:
        self._decision(decision_id)
        rows = self.db.scalars(
            select(SecurityEvent)
            .where(
                SecurityEvent.tenant_id == self.tenant_id,
                SecurityEvent.target_type == "InvestmentDecision",
                SecurityEvent.target_id == decision_id,
            )
            .order_by(SecurityEvent.occurred_at.desc(), SecurityEvent.id.desc())
        ).all()
        return [
            DecisionHistoryItemOut(
                id=item.id,
                event_type=item.event_type,
                outcome=item.outcome,
                metadata=deepcopy(item.metadata_json or {}),
                occurred_at=item.occurred_at,
            )
            for item in rows
        ]

    def authorization_output(self, decision_id: int) -> dict:
        return self._authorization_output(self._decision(decision_id))

    # Validation/calculation -------------------------------------
    def _validate_entry(self, preparation: InvestmentGatePreparation):
        if preparation.status != "FROZEN" or preparation.readiness_status != "READY":
            raise HTTPException(status_code=409, detail={"code": "PREPARATION_NOT_READY"})
        if not preparation.preparation_hash:
            raise HTTPException(status_code=409, detail={"code": "PACKAGE_NOT_FROZEN"})
        prep_service = InvestmentGatePreparationService(self.db, self.tenant_id, self.actor_id, self.context)
        handoff = prep_service.handoff(preparation.id)
        if handoff.preparation_hash != preparation.preparation_hash:
            raise HTTPException(status_code=409, detail={"code": "PACKAGE_HASH_MISMATCH"})
        blockers = list(handoff.blockers or [])
        if blockers:
            raise HTTPException(status_code=409, detail={"code": "EVIDENCE_BLOCKER_PRESENT", "blockers": blockers})
        self._assert_preparation_current(preparation, prep_service)
        return handoff

    def _assert_preparation_current(
        self,
        preparation: InvestmentGatePreparation,
        service: InvestmentGatePreparationService | None = None,
    ) -> None:
        service = service or InvestmentGatePreparationService(self.db, self.tenant_id, self.actor_id, self.context)
        try:
            contract = service._gate07i_contract(preparation.portfolio_workspace_id)
            profile = service._effective_profile_for_code(
                service._portfolio(preparation.portfolio_workspace_id), preparation.profile_code
            )
        except HTTPException as error:
            raise HTTPException(status_code=409, detail={"code": "PREPARATION_STALE"}) from error
        if profile is None or profile.content_hash != preparation.profile_hash:
            raise HTTPException(status_code=409, detail={"code": "POLICY_MISMATCH"})
        current_hash = service._current_preparation_hash(preparation, contract, profile.content_hash)
        if current_hash != preparation.preparation_source_hash:
            if contract.get("selected_project_set_hash") != preparation.recommended_project_set_hash:
                raise HTTPException(status_code=409, detail={"code": "PROJECT_SET_MISMATCH"})
            raise HTTPException(status_code=409, detail={"code": "PREPARATION_STALE"})

    def _assert_current(self, record: InvestmentDecision) -> None:
        preparation = self._preparation(record.investment_gate_preparation_id, lock=True)
        if preparation.status != "FROZEN" or not preparation.preparation_hash:
            raise HTTPException(status_code=409, detail={"code": "PACKAGE_NOT_FROZEN"})
        if preparation.preparation_hash != record.source_preparation_hash:
            raise HTTPException(status_code=409, detail={"code": "PACKAGE_HASH_MISMATCH"})
        if preparation.recommended_project_set_hash != record.decision_scope_hash:
            raise HTTPException(status_code=409, detail={"code": "PROJECT_SET_MISMATCH"})
        self._assert_preparation_current(preparation)
        current_config = self._published_configuration()
        if current_config.content_hash != record.configuration_hash:
            raise HTTPException(status_code=409, detail={"code": "POLICY_MISMATCH"})

    def _readiness(self, record: InvestmentDecision) -> DecisionReadinessOut:
        blockers: list[str] = []
        warnings: list[str] = []
        source_current = True
        try:
            self._assert_current(record)
        except HTTPException as error:
            source_current = False
            detail = error.detail if isinstance(error.detail, dict) else {"code": str(error.detail)}
            blockers.append(str(detail.get("code", "PREPARATION_STALE")))
        checklist = list(record.checklist_snapshot_json or [])
        checklist_complete = all(
            not item.get("blocking", False) or item.get("acknowledged", False) for item in checklist
        )
        if not checklist_complete:
            blockers.append("DECISION_CHECKLIST_INCOMPLETE")
        authority_valid = self._authority_valid(record)
        if not authority_valid:
            blockers.append("DECISION_AUTHORITY_INVALID")
        quorum_met = self._quorum_met(record)
        if record.authority_model == "COMMITTEE" and not quorum_met:
            blockers.append("QUORUM_NOT_MET")
        voting_rule_met = True
        sod_valid = self._sod_valid(record)
        if not sod_valid:
            blockers.append("SEGREGATION_OF_DUTIES_VIOLATION")
        if record.conditions_json:
            warnings.append("CONDITIONS_PRESENT")
        status = "READY" if not blockers else ("STALE" if not source_current else "BLOCKED")
        return DecisionReadinessOut(
            investment_decision_id=record.id,
            readiness_status=status,
            source_current=source_current,
            package_frozen=True,
            exact_scope=True,
            checklist_complete=checklist_complete,
            authority_valid=authority_valid,
            quorum_met=quorum_met,
            voting_rule_met=voting_rule_met,
            segregation_of_duties_valid=sod_valid,
            blockers=sorted(set(blockers)),
            warnings=sorted(set(warnings)),
            final_output=READY_OUTPUT if status == "READY" else REWORK_OUTPUT,
        )

    def _assert_authority(self, record: InvestmentDecision, outcome: str) -> None:
        if record.authority_model == "SINGLE_DECISION_MAKER":
            if record.decision_maker_user_id != self.actor_id:
                raise HTTPException(status_code=403, detail={"code": "DECISION_AUTHORITY_REQUIRED"})
            if not self._sod_valid(record):
                raise HTTPException(status_code=409, detail={"code": "SEGREGATION_OF_DUTIES_VIOLATION"})
            return
        members = self._committee_members(record)
        if self.actor_id not in {item["user_id"] for item in members}:
            raise HTTPException(status_code=403, detail={"code": "COMMITTEE_AUTHORITY_REQUIRED"})
        if not self._quorum_met(record):
            raise HTTPException(status_code=409, detail={"code": "QUORUM_NOT_MET"})
        if not self._voting_rule_met(record, outcome):
            raise HTTPException(status_code=409, detail={"code": "VOTING_RULE_NOT_MET"})

    def _authority_valid(self, record: InvestmentDecision) -> bool:
        if record.authority_model == "SINGLE_DECISION_MAKER":
            return record.decision_maker_user_id is not None
        members = self._committee_members(record)
        return bool(members) and all(self._user_exists(item["user_id"]) for item in members)

    def _sod_valid(self, record: InvestmentDecision) -> bool:
        if record.authority_model != "SINGLE_DECISION_MAKER" or record.decision_maker_user_id is None:
            return record.authority_model == "COMMITTEE"
        preparation = self._preparation(record.investment_gate_preparation_id)
        rules = dict(record.configuration_snapshot_json.get("segregation_of_duties", {}).get(record.profile_code, {}))
        if rules.get("decision_maker_differs_from_preparation_creator") and (
            record.decision_maker_user_id == preparation.created_by
        ):
            return False
        if rules.get("decision_maker_differs_from_preparation_last_modifier") and (
            record.decision_maker_user_id == preparation.updated_by
        ):
            return False
        return True

    def _quorum_met(self, record: InvestmentDecision) -> bool:
        if record.authority_model != "COMMITTEE":
            return True
        members = [item for item in self._committee_members(record) if item.get("voting_right", True)]
        votes = self._votes(record.id)
        voters = {item.voter_user_id for item in votes}
        present = sum(1 for item in members if item["user_id"] in voters)
        rule = dict(record.quorum_snapshot_json or {})
        minimum_count = int(rule.get("minimum_member_count", 1))
        percentage = (present / len(members) * 100) if members else 0
        if present < minimum_count or percentage < float(rule.get("minimum_percentage", 50)):
            return False
        chair_id = dict(record.committee_snapshot_json or {}).get("chair_user_id")
        return not rule.get("chair_required", False) or chair_id in voters

    def _voting_rule_met(self, record: InvestmentDecision, outcome: str) -> bool:
        votes = [item for item in self._votes(record.id) if item.vote != "ABSTAIN"]
        if not votes:
            return False
        rule = dict(record.voting_rule_snapshot_json or {})
        code = rule.get("rule", "SIMPLE_MAJORITY")
        matching = sum(1 for item in votes if item.vote == outcome)
        if code == "UNANIMOUS":
            return matching == len(votes)
        if code == "SUPERMAJORITY":
            return matching / len(votes) * 100 >= float(rule.get("supermajority_percentage", 66.67))
        if code == "CHAIR_DECIDES":
            chair = dict(record.committee_snapshot_json or {}).get("chair_user_id")
            return any(item.voter_user_id == chair and item.vote == outcome for item in votes)
        return matching > len(votes) / 2

    def _assert_authority_limit(self, record: InvestmentDecision, amount: Decimal | None) -> None:
        policy = dict(record.configuration_snapshot_json.get("authority_limits", {}))
        if not policy.get("enabled") or amount is None:
            return
        applicable = [
            item
            for item in policy.get("limits", [])
            if item.get("user_id") in {None, record.decision_maker_user_id, self.actor_id}
        ]
        if applicable and amount > max(Decimal(str(item.get("maximum_amount", 0))) for item in applicable):
            raise HTTPException(status_code=409, detail={"code": "AUTHORITY_LIMIT_EXCEEDED"})

    # Internals --------------------------------------------------
    def _transition(
        self,
        decision_id: int,
        expected_version: int,
        idempotency_key: str,
        *,
        expected: str,
        target: str,
        event: str,
        timestamp: str,
    ) -> InvestmentDecisionOut:
        record = self._decision(decision_id, lock=True)
        if record.status == target:
            return self._out(record)
        self._check_version(record.revision_version, expected_version)
        if record.status != expected:
            raise HTTPException(status_code=409, detail={"code": f"{expected}_DECISION_REQUIRED"})
        self._assert_current(record)
        record.status = target
        setattr(record, timestamp, utc_now())
        self._touch(record)
        self._event(event, "InvestmentDecision", record.id, {"idempotency_key": idempotency_key})
        return self._commit(record)

    def _decision_package(self, preparation, handoff, configuration: dict) -> dict:
        return {
            "schema": "PPMIS.GATE07K.DECISION_PACKAGE.v1",
            "frozen_at": utc_now().isoformat(),
            "preparation": handoff.model_dump(mode="json"),
            "source_snapshot": deepcopy(preparation.source_snapshot_json or {}),
            "evidence_summary": deepcopy(preparation.evidence_summary_json or {}),
            "conditions": deepcopy(preparation.conditions_json or []),
            "warnings": deepcopy(preparation.warnings_json or []),
            "blockers": deepcopy(preparation.blockers_json or []),
            "selected_project_ids": deepcopy(preparation.source_snapshot_json.get("selected_project_ids", [])),
            "exact_project_set_hash": preparation.recommended_project_set_hash,
            "authority": deepcopy(configuration.get("authority", {})),
            "committee": deepcopy(configuration.get("committee", {})),
            "quorum": deepcopy(configuration.get("quorum", {})),
            "voting_rule": deepcopy(configuration.get("voting_rule", {})),
            "checklist": deepcopy(configuration.get("decision_checklist", [])),
        }

    def _decision_hash(self, record: InvestmentDecision, timestamp) -> str:
        return _hash(
            {
                "decision_number": record.decision_number,
                "preparation_hash": record.source_preparation_hash,
                "package_hash": record.source_package_hash,
                "configuration_hash": record.configuration_hash,
                "profile_hash": record.source_profile_hash,
                "policy_hash": record.source_policy_hash,
                "scope_hash": record.decision_scope_hash,
                "authority": record.authority_snapshot_json,
                "committee": record.committee_snapshot_json,
                "quorum": record.quorum_snapshot_json,
                "voting_rule": record.voting_rule_snapshot_json,
                "votes": [item.model_dump(mode="json") for item in self._votes_out(record.id)],
                "outcome": record.outcome,
                "rationale": record.rationale,
                "conditions": record.conditions_json,
                "authorized_amount": record.authorized_amount,
                "authorized_currency": record.authorized_currency,
                "decided_at": timestamp,
            }
        )

    def _authorization_output(self, record: InvestmentDecision) -> dict:
        package = dict(record.decision_package_snapshot_json or {})
        base = {
            "decision_id": record.id,
            "decision_number": record.decision_number,
            "decision_round": record.decision_round,
            "gate_profile": record.profile_code,
            "status": record.status,
            "outcome": record.outcome,
            "decision_date": record.decided_at.isoformat() if record.decided_at else None,
            "decision_authority": record.decided_by or record.decision_maker_user_id,
            "committee_snapshot": deepcopy(record.committee_snapshot_json or {}),
            "quorum_snapshot": deepcopy(record.quorum_snapshot_json or {}),
            "source_preparation_id": record.investment_gate_preparation_id,
            "source_preparation_hash": record.source_preparation_hash,
            "decision_package_hash": record.source_package_hash,
            "investment_decision_hash": record.decision_hash,
            "decision_conditions": deepcopy(record.conditions_json or []),
            "is_fid": record.is_fid,
            "full_funds_authorized": record.full_funds_authorized,
            "investment_authorized": record.investment_authorized,
            "can_continue_project_development": bool(
                record.status == "DECIDED" and record.outcome == "GO" and record.profile_code == "PYP-INV-SELECT"
            ),
            "can_create_project": False,
            "can_activate_project": False,
            "can_issue_ntp": False,
            "can_execute": False,
            "authorized_investment_amount": (
                str(record.authorized_amount) if record.authorized_amount is not None else None
            ),
            "authorized_capex": None,
            "authorized_expense": None,
            "authorized_currency": record.authorized_currency,
            "authorization_valid_until": (
                record.authorization_valid_until.isoformat() if record.authorization_valid_until else None
            ),
            "funding_readiness": deepcopy(package.get("preparation", {}).get("funding_summary", {})),
            "risk_readiness": deepcopy(package.get("preparation", {}).get("risk_summary", {})),
            "permit_readiness": deepcopy(package.get("preparation", {}).get("permit_summary", {})),
            "project_definition_readiness": deepcopy(
                package.get("preparation", {}).get("definition_maturity_summary", {})
            ),
        }
        if record.status != "DECIDED":
            return {**base, "final_output": "INVESTMENT_DECISION_PENDING"}
        if record.outcome == "GO" and record.profile_code == "PYP-INV-SELECT":
            return {**base, "final_output": INVESTMENT_CONTINUATION_OUTPUT}
        if record.outcome == "GO" and record.profile_code == "PYP-FFA":
            return {
                **base,
                "final_output": FID_OUTPUT,
                "post_fid_handoff": POST_FID_OUTPUT,
            }
        alternate_outputs = {
            "PYP-INV-SELECT": {
                "HOLD": "INVESTMENT_SELECTION_HELD",
                "RECYCLE": "INVESTMENT_SELECTION_RECYCLE_REQUIRED",
                "KILL": "INVESTMENT_SELECTION_KILLED",
            },
            "PYP-FFA": {
                "HOLD": "FID_HELD",
                "RECYCLE": "FID_RECYCLE_REQUIRED",
                "KILL": "FID_KILLED",
            },
        }
        final_output = alternate_outputs.get(record.profile_code, {}).get(
            str(record.outcome), f"INVESTMENT_DECISION_{record.outcome}"
        )
        return {**base, "final_output": final_output}

    @staticmethod
    def _merge_conditions(source: list[dict], decided: list[dict]) -> list[dict]:
        result = [{**item, "origin": item.get("origin", "GATE07J_INPUT")} for item in source or []]
        result.extend({**item, "origin": item.get("origin", "GATE07K_DECISION")} for item in decided or [])
        return result

    def _out(self, record: InvestmentDecision) -> InvestmentDecisionOut:
        readiness = (
            self._readiness(record)
            if record.status not in {"DECIDED", "VOIDED"}
            else DecisionReadinessOut(
                investment_decision_id=record.id,
                readiness_status="READY" if record.status == "DECIDED" else "BLOCKED",
                source_current=True,
                package_frozen=True,
                exact_scope=True,
                checklist_complete=True,
                authority_valid=True,
                quorum_met=True,
                voting_rule_met=True,
                segregation_of_duties_valid=True,
                blockers=[] if record.status == "DECIDED" else ["DECISION_VOIDED"],
                warnings=[],
                final_output=self._authorization_output(record)["final_output"],
            )
        )
        return InvestmentDecisionOut(
            id=record.id,
            tenant_id=record.tenant_id,
            decision_number=record.decision_number,
            investment_gate_preparation_id=record.investment_gate_preparation_id,
            portfolio_workspace_id=record.portfolio_workspace_id,
            investment_gate_profile_id=record.investment_gate_profile_id,
            profile_code=record.profile_code,
            decision_round=record.decision_round,
            decision_scope_type=record.decision_scope_type,
            decision_scope_hash=record.decision_scope_hash,
            status=record.status,
            outcome=record.outcome,
            title=record.title,
            executive_summary=record.executive_summary,
            rationale=record.rationale,
            conditions=deepcopy(record.conditions_json or []),
            hold_reason=record.hold_reason,
            recycle_target=record.recycle_target,
            source_preparation_hash=record.source_preparation_hash,
            source_package_hash=record.source_package_hash,
            source_profile_hash=record.source_profile_hash,
            source_policy_hash=record.source_policy_hash,
            decision_package_snapshot=deepcopy(record.decision_package_snapshot_json or {}),
            configuration_id=record.configuration_id,
            configuration_revision=record.configuration_revision,
            configuration_hash=record.configuration_hash,
            configuration_snapshot=deepcopy(record.configuration_snapshot_json or {}),
            authority_model=record.authority_model,
            authority=deepcopy(record.authority_snapshot_json or {}),
            committee=deepcopy(record.committee_snapshot_json or {}),
            quorum=deepcopy(record.quorum_snapshot_json or {}),
            voting_rule=deepcopy(record.voting_rule_snapshot_json or {}),
            checklist=deepcopy(record.checklist_snapshot_json or []),
            authorized_amount=record.authorized_amount,
            authorized_currency=record.authorized_currency,
            authorization_valid_until=record.authorization_valid_until,
            decision_maker_user_id=record.decision_maker_user_id,
            submitted_at=record.submitted_at,
            review_started_at=record.review_started_at,
            ready_at=record.ready_at,
            decided_at=record.decided_at,
            voided_at=record.voided_at,
            decided_by=record.decided_by,
            is_fid=record.is_fid,
            full_funds_authorized=record.full_funds_authorized,
            investment_authorized=record.investment_authorized,
            decision_hash=record.decision_hash,
            revision_version=record.revision_version,
            created_by=record.created_by,
            created_at=record.created_at,
            updated_by=record.updated_by,
            updated_at=record.updated_at,
            votes=self._votes_out(record.id),
            readiness=readiness,
            allowed_actions=self._allowed_actions(record, readiness),
            authorization_output=self._authorization_output(record),
        )

    @staticmethod
    def _allowed_actions(record: InvestmentDecision, readiness: DecisionReadinessOut) -> list[str]:
        actions = ["can_view_decision", "can_view_package", "can_view_history", "can_view_authorization_output"]
        if record.status == "DRAFT":
            actions.extend(["can_edit_decision", "can_submit_decision", "can_void_decision"])
        elif record.status == "SUBMITTED":
            actions.extend(["can_start_review", "can_void_decision"])
        elif record.status == "IN_REVIEW":
            actions.extend(["can_mark_ready_for_decision", "can_void_decision"])
            if record.authority_model == "COMMITTEE":
                actions.append("can_cast_vote")
        elif record.status == "READY_FOR_DECISION":
            actions.extend(["can_decide", "can_void_decision"])
            if record.authority_model == "COMMITTEE":
                actions.append("can_cast_vote")
        if readiness.readiness_status == "STALE":
            actions = [item for item in actions if item not in {"can_mark_ready_for_decision", "can_decide"}]
        return actions

    def _votes(self, decision_id: int) -> list[InvestmentDecisionVote]:
        return list(
            self.db.scalars(
                select(InvestmentDecisionVote)
                .where(
                    InvestmentDecisionVote.tenant_id == self.tenant_id,
                    InvestmentDecisionVote.investment_decision_id == decision_id,
                )
                .order_by(InvestmentDecisionVote.cast_at, InvestmentDecisionVote.id)
            ).all()
        )

    def _votes_out(self, decision_id: int) -> list[DecisionVoteOut]:
        return [
            DecisionVoteOut(
                id=item.id,
                voter_user_id=item.voter_user_id,
                vote=item.vote,
                rationale=item.rationale,
                cast_at=item.cast_at,
                revision_version=item.revision_version,
            )
            for item in self._votes(decision_id)
        ]

    @staticmethod
    def _committee_members(record: InvestmentDecision) -> list[dict]:
        return [
            {**item, "user_id": int(item["user_id"])}
            for item in dict(record.committee_snapshot_json or {}).get("members", [])
            if item.get("user_id")
        ]

    def _validated_committee(self, value: dict) -> dict:
        members = []
        seen: set[int] = set()
        for item in value.get("members", []):
            user_id = int(item.get("user_id", 0))
            if not user_id or user_id in seen:
                raise HTTPException(status_code=422, detail={"code": "INVALID_COMMITTEE_MEMBER"})
            self._user(user_id)
            seen.add(user_id)
            members.append(
                {
                    "user_id": user_id,
                    "role": str(item.get("role", "MEMBER")),
                    "voting_right": bool(item.get("voting_right", True)),
                }
            )
        chair = value.get("chair_user_id")
        if chair is not None and int(chair) not in seen:
            raise HTTPException(status_code=422, detail={"code": "CHAIR_MUST_BE_COMMITTEE_MEMBER"})
        return {"members": members, "chair_user_id": int(chair) if chair is not None else None}

    def _configuration_issues(self, content: dict) -> list[str]:
        issues: list[str] = []
        profiles = dict(content.get("profiles", {}))
        if set(profiles) != {"PYP-INV-SELECT", "PYP-FFA"}:
            issues.append("REQUIRED_GATE_PROFILES_MISSING")
        if profiles.get("PYP-INV-SELECT", {}).get("go_is_fid") is not False:
            issues.append("INVESTMENT_SELECTION_MUST_NOT_BE_FID")
        if profiles.get("PYP-FFA", {}).get("go_is_fid") is not True:
            issues.append("PYP_FFA_GO_MUST_BE_FID")
        if set(content.get("outcomes", [])) != OUTCOMES:
            issues.append("EXACT_OUTCOMES_REQUIRED")
        if content.get("authority", {}).get("model") not in {"SINGLE_DECISION_MAKER", "COMMITTEE"}:
            issues.append("INVALID_AUTHORITY_MODEL")
        if content.get("voting_rule", {}).get("rule") not in {
            "SIMPLE_MAJORITY",
            "SUPERMAJORITY",
            "UNANIMOUS",
            "CHAIR_DECIDES",
        }:
            issues.append("INVALID_VOTING_RULE")
        if content.get("authorization_output", {}).get("can_activate_project") is not False:
            issues.append("PROJECT_ACTIVATION_MUST_REMAIN_FALSE")
        return sorted(set(issues))

    def _next_number(self, content: dict) -> str:
        sequence = self._sequence(lock=True)
        value = sequence.next_value
        sequence.next_value += 1
        sequence.version += 1
        sequence.updated_at = utc_now()
        numbering = dict(content.get("numbering", {}))
        return f"{numbering.get('prefix', 'IDEC-')}{value:0{int(numbering.get('padding', 5))}d}"

    def _sequence(self, *, required: bool = True, lock: bool = False) -> AdminNumberSequence | None:
        statement = select(AdminNumberSequence).where(
            AdminNumberSequence.tenant_id == self.tenant_id,
            AdminNumberSequence.rule_code == NUMBER_RULE,
            AdminNumberSequence.scope_key == "tenant",
        )
        if lock:
            statement = statement.with_for_update()
        record = self.db.scalar(statement)
        if record is None and required:
            raise HTTPException(status_code=409, detail={"code": "DECISION_NUMBER_SEQUENCE_REQUIRED"})
        return record

    def _published_configuration(self, *, required: bool = True) -> AdminConfiguration | None:
        record = self.db.scalar(
            select(AdminConfiguration)
            .where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == CONFIGURATION_KIND,
                AdminConfiguration.code == "default",
                AdminConfiguration.status == "published",
            )
            .order_by(AdminConfiguration.revision.desc())
        )
        if record is None and required:
            raise HTTPException(status_code=409, detail={"code": "PUBLISHED_DECISION_CONFIGURATION_REQUIRED"})
        return record

    def _configuration(self, configuration_id: int | None, *, lock: bool = False) -> AdminConfiguration:
        if configuration_id is None:
            raise HTTPException(status_code=404, detail="Investment Decision configuration not found")
        statement = select(AdminConfiguration).where(
            AdminConfiguration.id == configuration_id,
            AdminConfiguration.tenant_id == self.tenant_id,
            AdminConfiguration.kind == CONFIGURATION_KIND,
        )
        if lock:
            statement = statement.with_for_update()
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail="Investment Decision configuration not found")
        return record

    def _preparation(self, preparation_id: int, *, lock: bool = False) -> InvestmentGatePreparation:
        statement = select(InvestmentGatePreparation).where(
            InvestmentGatePreparation.id == preparation_id,
            InvestmentGatePreparation.tenant_id == self.tenant_id,
        )
        if lock:
            statement = statement.with_for_update()
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail="Investment Gate Preparation not found")
        return record

    def _decision(self, decision_id: int, *, lock: bool = False) -> InvestmentDecision:
        statement = select(InvestmentDecision).where(
            InvestmentDecision.id == decision_id,
            InvestmentDecision.tenant_id == self.tenant_id,
        )
        if lock:
            statement = statement.with_for_update()
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail="Investment Decision not found")
        return record

    def _user(self, user_id: int) -> UserAccount:
        record = self.db.scalar(
            select(UserAccount).where(UserAccount.id == user_id, UserAccount.tenant_id == self.tenant_id)
        )
        if record is None:
            raise HTTPException(status_code=404, detail="Decision authority user not found")
        return record

    def _user_exists(self, user_id: int) -> bool:
        return (
            self.db.scalar(
                select(UserAccount.id).where(UserAccount.id == user_id, UserAccount.tenant_id == self.tenant_id)
            )
            is not None
        )

    @staticmethod
    def _check_version(current: int, expected: int) -> None:
        if current != expected:
            raise HTTPException(
                status_code=412,
                detail={"code": "STALE_ETAG", "expected": current, "received": expected},
            )

    def _touch(self, record: InvestmentDecision, *, now=None) -> None:
        record.revision_version += 1
        record.updated_by = self.actor_id
        record.updated_at = now or utc_now()

    def _commit(self, record: InvestmentDecision) -> InvestmentDecisionOut:
        self.db.commit()
        self.db.refresh(record)
        return self._out(record)

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
                occurred_at=utc_now(),
            )
        )
