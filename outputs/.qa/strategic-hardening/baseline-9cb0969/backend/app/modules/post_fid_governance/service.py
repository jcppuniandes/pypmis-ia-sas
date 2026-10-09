"""Gate 07L governance, eligibility and handoff orchestration.

This module reads the immutable Gate 07K FID and the canonical Project
Workspace lifecycle.  It never creates, initializes or activates a Project.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domain.models import AdminConfiguration, EnterpriseWorkspace, SecurityEvent
from app.modules.investment_decision.models import InvestmentDecision
from app.modules.investment_decision.service import InvestmentDecisionService
from app.modules.post_fid_governance.models import PostFIDProjectEligibility
from app.modules.post_fid_governance.schemas import (
    ConfigurationPreviewOut,
    EligibilityOut,
    HandoffOut,
    HistoryItemOut,
    PostFIDDecisionOut,
    RefreshDeltaOut,
    RefreshPreviewOut,
)
from app.modules.project_workspace_initialization.models import ProjectWorkspaceInitialization

CONFIGURATION_KIND = "post_fid_governance_configuration"
POST_FID_HANDOFF = "READY_FOR_POST_FID_PROJECT_GOVERNANCE"
READY_INITIALIZATION = "READY_FOR_PROJECT_WORKSPACE_INITIALIZATION"
READY_ACTIVATION = "READY_FOR_PROJECT_WORKSPACE_ACTIVATION"
BLOCKED = "POST_FID_PROJECT_GOVERNANCE_BLOCKED"
NO_REACTIVATION = "NO_REACTIVATION_REQUIRED"
NOT_APPLICABLE = "NOT_APPLICABLE"
STALE = "STALE"

SATISFIED_CONDITION_STATES = frozenset({"SATISFIED", "WAIVED"})
INITIALIZATION_SERVICE = "ProjectWorkspaceInitializationService"
ACTIVATION_SERVICE = "ProjectWorkspaceInitializationService.activate"


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


DEFAULT_CONFIGURATION: dict[str, Any] = {
    "applicable_gate_profiles": ["PYP-FFA"],
    "required_fid_semantics": {
        "status": "DECIDED",
        "outcome": "GO",
        "is_fid": True,
        "full_funds_authorized": True,
        "investment_authorized": True,
        "post_fid_handoff": POST_FID_HANDOFF,
    },
    "applicable_governance_models": ["CAPITAL_OWNER"],
    "project_state_mapping": {
        "workspace_active": ["active"],
        "workspace_pending": ["pending"],
        "workspace_incompatible": ["inactive", "suspended", "closed", "archived", "cancelled"],
        "initialization_not_started": ["NOT_STARTED"],
        "initialization_ready": ["READY_FOR_ACTIVATION"],
        "initialization_incompatible": ["INITIALIZING", "BLOCKED", "FAILED", "ACTIVATED"],
    },
    "condition_resolution_policy": {
        "satisfied_statuses": sorted(SATISFIED_CONDITION_STATES),
        "activation_flag": "blocking_for_activation",
        "commitment_flag": "blocking_for_commitment",
    },
    "authorization_validity": {
        "block_before_effective": True,
        "block_after_expiry": True,
    },
    "initialization_eligibility": {"require_fid_current": True, "require_no_activation_blockers": True},
    "activation_eligibility": {"require_fid_current": True, "require_no_activation_blockers": True},
    "handoff_rules": {
        "delegate_initialization": True,
        "delegate_activation": True,
        "automatic_initialization": False,
        "automatic_activation": False,
    },
    "freshness_rules": {
        "decision_hash": True,
        "decision_package_hash": True,
        "project_state": True,
        "conditions": True,
        "configuration": True,
    },
    "inheritance": {"inherit_to_descendants": True},
}


class PostFIDGovernanceService:
    def __init__(self, db: Session, tenant_id: int, actor_id: int, context=None) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.actor_id = actor_id
        self.context = context

    # Configuration -------------------------------------------------
    def ensure_seed(self) -> None:
        if self._published_configuration(required=False) is not None:
            return
        content = deepcopy(DEFAULT_CONFIGURATION)
        record = AdminConfiguration(
            tenant_id=self.tenant_id,
            kind=CONFIGURATION_KIND,
            code="default",
            name="Default Post-FID Project Governance",
            description="Gate 07L eligibility, freshness and handoff policy; no lifecycle execution.",
            status="published",
            revision=1,
            version=1,
            content_json=content,
            content_hash=_hash(content),
            published_at=utc_now(),
            created_by_user_id=self.actor_id,
        )
        self.db.add(record)
        self._event("post_fid_governance.configuration_published", "AdminConfiguration", None, {"seed": True})
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
        *,
        investment_decision_id: int | None,
        project_workspace_ids: list[int],
        configuration_id: int | None,
        content_json: dict | None,
    ) -> ConfigurationPreviewOut:
        base = self._configuration(configuration_id) if configuration_id else self._published_configuration()
        content = deepcopy(content_json if content_json is not None else base.content_json)
        issues = self._configuration_issues(content)
        projects: list[EligibilityOut] = []
        blockers: list[str] = []
        if investment_decision_id:
            decision = self._decision(investment_decision_id)
            config = self._transient_configuration(base, content)
            scoped = self._scope_projects(decision)
            requested = set(project_workspace_ids)
            scoped = [item for item in scoped if not requested or item.id in requested]
            projects = [self._evaluate_project(decision, item, config, persisted=False) for item in scoped]
            blockers = sorted({value for item in projects for value in item.blockers})
        return ConfigurationPreviewOut(
            investment_decision_id=investment_decision_id,
            effective=content,
            validation_issues=issues,
            warnings=[] if investment_decision_id else ["NO_DECISION_SELECTED_FOR_PROJECT_PREVIEW"],
            blockers=blockers,
            project_eligibility=projects,
            publishable=not issues,
            persisted=False,
        )

    def clone_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        source = self._configuration(configuration_id)
        self._check_version(source.version, expected_version, "POST_FID_CONFIGURATION_VERSION_CONFLICT")
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
            name=f"{source.name} rev {revision}",
            description=source.description,
            status="draft",
            revision=revision,
            version=1,
            content_json=deepcopy(source.content_json),
            content_hash=source.content_hash,
            created_by_user_id=self.actor_id,
        )
        self.db.add(clone)
        self.db.flush()
        self._event("post_fid_governance.configuration_cloned", "AdminConfiguration", clone.id, {})
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
        content_json: dict,
    ) -> AdminConfiguration:
        record = self._configuration(configuration_id, lock=True)
        self._check_version(record.version, expected_version, "POST_FID_CONFIGURATION_VERSION_CONFLICT")
        if record.status != "draft":
            raise HTTPException(status_code=409, detail={"code": "DRAFT_CONFIGURATION_REQUIRED"})
        issues = self._configuration_issues(content_json)
        if issues:
            raise HTTPException(status_code=422, detail={"code": "INVALID_CONFIGURATION", "issues": issues})
        record.name = name
        record.description = description
        record.content_json = deepcopy(content_json)
        record.content_hash = _hash(content_json)
        record.version += 1
        record.updated_at = utc_now()
        self._event("post_fid_governance.configuration_updated", "AdminConfiguration", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return record

    def publish_configuration(self, configuration_id: int, expected_version: int) -> AdminConfiguration:
        record = self._configuration(configuration_id, lock=True)
        self._check_version(record.version, expected_version, "POST_FID_CONFIGURATION_VERSION_CONFLICT")
        if record.status == "published":
            return record
        issues = self._configuration_issues(record.content_json)
        if issues:
            raise HTTPException(status_code=422, detail={"code": "INVALID_CONFIGURATION", "issues": issues})
        record.status = "published"
        record.published_at = utc_now()
        record.version += 1
        record.updated_at = utc_now()
        self._event("post_fid_governance.configuration_published", "AdminConfiguration", record.id, {})
        self.db.commit()
        self.db.refresh(record)
        return record

    # USER read/evaluate/refresh ------------------------------------
    def list(self) -> list[PostFIDDecisionOut]:
        self.ensure_seed()
        rows = self.db.scalars(
            select(InvestmentDecision)
            .where(InvestmentDecision.tenant_id == self.tenant_id, InvestmentDecision.status == "DECIDED")
            .order_by(InvestmentDecision.decided_at.desc(), InvestmentDecision.id.desc())
        ).all()
        return [self._decision_out(item) for item in rows]

    def get(self, decision_id: int) -> PostFIDDecisionOut:
        self.ensure_seed()
        return self._decision_out(self._decision(decision_id))

    def projects(self, decision_id: int) -> list[EligibilityOut]:
        self.ensure_seed()
        decision = self._decision(decision_id)
        config = self._published_configuration()
        return [self._current_or_preview(decision, project, config) for project in self._scope_projects(decision)]

    def evaluate(self, decision_id: int, idempotency_key: str, expected_version: int) -> list[EligibilityOut]:
        return self._persist_evaluation(
            decision_id,
            idempotency_key,
            expected_version=expected_version,
            operation_type="EVALUATE",
            refresh=False,
        )

    def refresh_preview(self, decision_id: int) -> RefreshPreviewOut:
        self.ensure_seed()
        decision = self._decision(decision_id)
        config = self._published_configuration()
        previews: list[EligibilityOut] = []
        deltas: list[RefreshDeltaOut] = []
        for project in self._scope_projects(decision):
            current = self._evaluate_project(decision, project, config, persisted=False)
            previous = self._latest(decision.id, project.id)
            previews.append(current)
            deltas.append(self._delta(previous, current))
        self._event(
            "post_fid_governance.refresh_previewed",
            "InvestmentDecision",
            decision.id,
            {
                "persisted": False,
                "delta_count": sum(1 for item in deltas if item.old_source_hash != item.new_source_hash),
            },
        )
        self.db.commit()
        return RefreshPreviewOut(investment_decision_id=decision.id, deltas=deltas, projects=previews, persisted=False)

    def refresh(self, decision_id: int, idempotency_key: str, expected_version: int) -> list[EligibilityOut]:
        return self._persist_evaluation(
            decision_id,
            idempotency_key,
            expected_version=expected_version,
            operation_type="REFRESH",
            refresh=True,
        )

    def project_eligibility(self, decision_id: int, project_id: int) -> EligibilityOut:
        self.ensure_seed()
        decision = self._decision(decision_id)
        project = self._project_in_scope(decision, project_id)
        return self._current_or_preview(decision, project, self._published_configuration())

    def initialization_handoff(self, decision_id: int, project_id: int, idempotency_key: str) -> HandoffOut:
        item = self.project_eligibility(decision_id, project_id)
        if item.eligibility_status != READY_INITIALIZATION or item.id is None:
            raise HTTPException(status_code=409, detail={"code": "PROJECT_NOT_ELIGIBLE_FOR_INITIALIZATION"})
        self._handoff_event_once(
            "post_fid_governance.initialization_handoff_invoked", decision_id, project_id, idempotency_key
        )
        workspace = self._project_in_scope(self._decision(decision_id), project_id)
        return HandoffOut(
            project_workspace_id=project_id,
            investment_decision_id=decision_id,
            fid_decision_hash=item.fid_decision_hash,
            eligibility_id=item.id,
            eligibility_hash=item.eligibility_hash,
            eligibility_status=item.eligibility_status,
            post_fid_conditions=item.post_fid_conditions,
            can_initialize=True,
            can_activate=False,
            delegated_service=INITIALIZATION_SERVICE,
            delegated_endpoint=f"/api/v1/project-workspaces/{project_id}/initialization/start",
            delegated_revision_version=workspace.version,
        )

    def activation_handoff(self, decision_id: int, project_id: int, idempotency_key: str) -> HandoffOut:
        item = self.project_eligibility(decision_id, project_id)
        if item.eligibility_status != READY_ACTIVATION or item.id is None:
            raise HTTPException(status_code=409, detail={"code": "PROJECT_NOT_ELIGIBLE_FOR_ACTIVATION"})
        initialization = self._initialization(project_id)
        if initialization is None:
            raise HTTPException(status_code=409, detail={"code": "INITIALIZATION_NOT_STARTED"})
        self._handoff_event_once(
            "post_fid_governance.activation_handoff_invoked", decision_id, project_id, idempotency_key
        )
        return HandoffOut(
            project_workspace_id=project_id,
            investment_decision_id=decision_id,
            fid_decision_hash=item.fid_decision_hash,
            eligibility_id=item.id,
            eligibility_hash=item.eligibility_hash,
            eligibility_status=item.eligibility_status,
            post_fid_conditions=item.post_fid_conditions,
            can_initialize=False,
            can_activate=True,
            delegated_service=ACTIVATION_SERVICE,
            delegated_endpoint=f"/api/v1/project-workspaces/{project_id}/activate",
            delegated_revision_version=initialization.revision_version,
        )

    def history(self, decision_id: int) -> list[HistoryItemOut]:
        self._decision(decision_id)
        rows = self.db.scalars(
            select(SecurityEvent)
            .where(
                SecurityEvent.tenant_id == self.tenant_id,
                SecurityEvent.event_type.like("post_fid_governance.%"),
                SecurityEvent.metadata_json["investment_decision_id"].as_integer() == decision_id,
            )
            .order_by(SecurityEvent.occurred_at.desc(), SecurityEvent.id.desc())
        ).all()
        return [
            HistoryItemOut(
                id=item.id,
                event_type=item.event_type,
                outcome=item.outcome,
                metadata=deepcopy(item.metadata_json or {}),
                occurred_at=item.occurred_at,
            )
            for item in rows
        ]

    # Evaluation internals -----------------------------------------
    def _persist_evaluation(
        self,
        decision_id: int,
        idempotency_key: str,
        *,
        expected_version: int,
        operation_type: str,
        refresh: bool,
    ) -> list[EligibilityOut]:
        self.ensure_seed()
        decision = self._decision(decision_id, lock=True)
        config = self._published_configuration()
        payload_hash = _hash({"decision_id": decision_id, "operation_type": operation_type})
        duplicates = list(
            self.db.scalars(
                select(PostFIDProjectEligibility).where(
                    PostFIDProjectEligibility.tenant_id == self.tenant_id,
                    PostFIDProjectEligibility.investment_decision_id == decision_id,
                    PostFIDProjectEligibility.operation_key == idempotency_key,
                )
            ).all()
        )
        if duplicates:
            if any(item.operation_payload_hash != payload_hash for item in duplicates):
                raise HTTPException(status_code=409, detail={"code": "IDEMPOTENCY_PAYLOAD_MISMATCH"})
            return [self._out(item, decision=decision) for item in duplicates]
        current_version = self.db.scalar(
            select(func.max(PostFIDProjectEligibility.eligibility_round)).where(
                PostFIDProjectEligibility.tenant_id == self.tenant_id,
                PostFIDProjectEligibility.investment_decision_id == decision_id,
            )
        )
        if expected_version != int(current_version or 1):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "POST_FID_VERSION_CONFLICT",
                    "expected": int(current_version or 1),
                    "received": expected_version,
                },
            )
        result: list[PostFIDProjectEligibility] = []
        for project in self._scope_projects(decision):
            current = self._evaluate_project(decision, project, config, persisted=False)
            previous = self._latest(decision.id, project.id, lock=True)
            if previous is not None and not refresh:
                result.append(previous)
                continue
            if previous is not None and previous.eligibility_hash == current.eligibility_hash:
                result.append(previous)
                continue
            round_number = (previous.eligibility_round if previous else 0) + 1
            snapshot = self._snapshot_from_out(
                current,
                config,
                round_number=round_number,
                operation_type=operation_type,
                operation_key=idempotency_key,
                operation_payload_hash=payload_hash,
            )
            self.db.add(snapshot)
            result.append(snapshot)
        try:
            self.db.flush()
        except IntegrityError as error:
            self.db.rollback()
            raise HTTPException(status_code=409, detail={"code": "POST_FID_CONCURRENT_EVALUATION"}) from error
        event_type = "post_fid_governance.refresh_applied" if refresh else "post_fid_governance.evaluated"
        self._event(event_type, "InvestmentDecision", decision.id, {"operation_key": idempotency_key})
        for item in result:
            self._status_event(item)
        self.db.commit()
        for item in result:
            if item.id:
                self.db.refresh(item)
        return [self._out(item, decision=decision) for item in result]

    def _evaluate_project(
        self,
        decision: InvestmentDecision,
        workspace: EnterpriseWorkspace,
        config: AdminConfiguration,
        *,
        persisted: bool,
    ) -> EligibilityOut:
        state, initialization_state, state_snapshot = self._project_state(workspace, config.content_json)
        governance_model = str(self._project_metadata(workspace).get("governance_model") or "CAPITAL_OWNER")
        applicable, fid_current, decision_blockers, decision_warnings = self._decision_validity(decision, config)
        conditions = deepcopy(decision.conditions_json or [])
        satisfied = {
            str(value).upper()
            for value in config.content_json.get("condition_resolution_policy", {}).get(
                "satisfied_statuses", SATISFIED_CONDITION_STATES
            )
        }
        unresolved = [item for item in conditions if str(item.get("status", "OPEN")).upper() not in satisfied]
        activation_blockers = [item for item in unresolved if bool(item.get("blocking_for_activation", False))]
        commitment_only = [
            item
            for item in unresolved
            if bool(item.get("blocking_for_commitment", False)) and not bool(item.get("blocking_for_activation", False))
        ]
        warnings = list(decision_warnings)
        blockers = list(decision_blockers)
        if commitment_only:
            warnings.append("OPEN_COMMITMENT_CONDITIONS")
        if activation_blockers:
            blockers.append("OPEN_ACTIVATION_BLOCKERS")

        configured_models = set(config.content_json.get("applicable_governance_models", ["CAPITAL_OWNER"]))
        if governance_model not in configured_models:
            applicable = False
            warnings.append(f"GOVERNANCE_MODEL_{governance_model}_UNAFFECTED")

        if not applicable:
            status = NOT_APPLICABLE
        elif not fid_current:
            status = STALE
        elif blockers:
            status = BLOCKED
        elif state == "ACTIVE":
            status = NO_REACTIVATION
        elif state == "NOT_INITIALIZED":
            status = READY_INITIALIZATION
        elif state == "INITIALIZED_NOT_ACTIVE":
            status = READY_ACTIVATION
        else:
            status = BLOCKED
            blockers.append("PROJECT_STATE_NOT_ELIGIBLE")

        warnings = sorted(set(warnings))
        blockers = sorted(set(blockers))
        condition_hash = _hash(conditions)
        eligibility_hash = _hash(
            {
                "investment_decision_id": decision.id,
                "fid_decision_hash": decision.decision_hash,
                "decision_package_hash": decision.source_package_hash,
                "project": state_snapshot,
                "conditions": conditions,
                "authorization_valid_until": decision.authorization_valid_until,
                "configuration_hash": config.content_hash,
                "eligibility_status": status,
                "warnings": warnings,
                "blockers": blockers,
            }
        )
        can_initialize = status == READY_INITIALIZATION
        can_activate = status == READY_ACTIVATION
        return EligibilityOut(
            investment_decision_id=decision.id,
            project_workspace_id=workspace.id,
            project_number=str(self._project_metadata(workspace).get("project_number") or workspace.code),
            project_name=workspace.name,
            project_type=str(self._project_metadata(workspace).get("project_type") or "PROJECT"),
            governance_model=governance_model,
            project_state=state,
            workspace_status=workspace.status,
            initialization_state=initialization_state,
            fid_current=fid_current,
            eligibility_round=0,
            snapshot_eligibility_status=status,
            eligibility_status=status,
            final_output=status,
            warnings=warnings,
            blockers=blockers,
            post_fid_conditions=conditions,
            open_activation_blockers=len(activation_blockers),
            open_commitment_conditions_count=len(commitment_only),
            can_initialize=can_initialize,
            can_activate=can_activate,
            next_allowed_process=self._next_for_status(status),
            allowed_actions=self._allowed_actions(status),
            fid_decision_hash=str(decision.decision_hash or ""),
            decision_package_hash=decision.source_package_hash,
            condition_snapshot_hash=condition_hash,
            eligibility_hash=eligibility_hash,
            source_current=fid_current,
            stale=status == STALE,
            persisted=persisted,
            revision_version=1,
        )

    def _decision_validity(
        self, decision: InvestmentDecision, config: AdminConfiguration
    ) -> tuple[bool, bool, list[str], list[str]]:
        blockers: list[str] = []
        warnings: list[str] = []
        output = InvestmentDecisionService(self.db, self.tenant_id, self.actor_id, self.context)._authorization_output(
            decision
        )
        applicable = bool(
            decision.status == "DECIDED"
            and decision.profile_code in config.content_json.get("applicable_gate_profiles", ["PYP-FFA"])
            and decision.profile_code == "PYP-FFA"
            and decision.outcome == "GO"
            and decision.is_fid
            and decision.full_funds_authorized
            and decision.investment_authorized
            and output.get("post_fid_handoff") == POST_FID_HANDOFF
        )
        if not applicable:
            return False, True, blockers, warnings

        source_current = True
        if _hash(decision.decision_package_snapshot_json or {}) != decision.source_package_hash:
            source_current = False
            blockers.append("DECISION_PACKAGE_HASH_MISMATCH")
        expected_decision_hash = InvestmentDecisionService(
            self.db, self.tenant_id, self.actor_id, self.context
        )._decision_hash(decision, decision.decided_at)
        if expected_decision_hash != decision.decision_hash:
            source_current = False
            blockers.append("INVESTMENT_DECISION_HASH_MISMATCH")
        newer = self.db.scalar(
            select(InvestmentDecision.id).where(
                InvestmentDecision.tenant_id == self.tenant_id,
                InvestmentDecision.investment_gate_preparation_id == decision.investment_gate_preparation_id,
                InvestmentDecision.profile_code == decision.profile_code,
                InvestmentDecision.decision_round > decision.decision_round,
                InvestmentDecision.status == "DECIDED",
            )
        )
        if newer is not None:
            source_current = False
            blockers.append("FID_SUPERSEDED")
        try:
            InvestmentDecisionService(self.db, self.tenant_id, self.actor_id, self.context)._assert_current(decision)
        except HTTPException as error:
            source_current = False
            detail = error.detail if isinstance(error.detail, dict) else {"code": str(error.detail)}
            blockers.append(str(detail.get("code", "FID_NOT_CURRENT")))
        effective = self._authorization_effective_date(decision)
        now = utc_now()
        if effective is not None and now < effective:
            blockers.append("AUTHORIZATION_NOT_YET_EFFECTIVE")
        if decision.authorization_valid_until is not None and now > decision.authorization_valid_until:
            blockers.append("AUTHORIZATION_EXPIRED")
        return True, source_current, blockers, warnings

    def _project_state(self, workspace: EnterpriseWorkspace, content: dict) -> tuple[str, str, dict]:
        initialization = self._initialization(workspace.id)
        initialization_state = initialization.state if initialization else "NOT_STARTED"
        mapping = dict(content.get("project_state_mapping", {}))
        active = set(mapping.get("workspace_active", ["active"]))
        pending = set(mapping.get("workspace_pending", ["pending"]))
        ready = set(mapping.get("initialization_ready", ["READY_FOR_ACTIVATION"]))
        not_started = set(mapping.get("initialization_not_started", ["NOT_STARTED"]))
        if workspace.status in active:
            state = "ACTIVE"
        elif workspace.status in pending and initialization_state in not_started:
            state = "NOT_INITIALIZED"
        elif workspace.status in pending and initialization_state in ready:
            state = "INITIALIZED_NOT_ACTIVE"
        else:
            state = "INVALID_STATE"
        snapshot = {
            "workspace_id": workspace.id,
            "workspace_type_code": workspace.workspace_type_code,
            "workspace_status": workspace.status,
            "workspace_version": workspace.version,
            "initialization_id": initialization.id if initialization else None,
            "initialization_state": initialization_state,
            "initialization_revision": initialization.revision_version if initialization else None,
            "classified_state": state,
        }
        return state, initialization_state, snapshot

    def _current_or_preview(
        self, decision: InvestmentDecision, project: EnterpriseWorkspace, config: AdminConfiguration
    ) -> EligibilityOut:
        latest = self._latest(decision.id, project.id)
        if latest is None:
            return self._evaluate_project(decision, project, config, persisted=False)
        return self._out(latest, decision=decision, config=config)

    def _out(
        self,
        record: PostFIDProjectEligibility,
        *,
        decision: InvestmentDecision | None = None,
        config: AdminConfiguration | None = None,
    ) -> EligibilityOut:
        decision = decision or self._decision(record.investment_decision_id)
        project = self._project_in_scope(decision, record.project_workspace_id)
        config = config or self._published_configuration()
        current = self._evaluate_project(decision, project, config, persisted=False)
        stale = current.eligibility_hash != record.eligibility_hash
        status = STALE if stale else record.eligibility_status
        state_snapshot = dict(record.project_state_snapshot or {})
        return current.model_copy(
            update={
                "id": record.id,
                "project_state": str(state_snapshot.get("classified_state", current.project_state)),
                "workspace_status": str(state_snapshot.get("workspace_status", current.workspace_status)),
                "initialization_state": str(state_snapshot.get("initialization_state", current.initialization_state)),
                "eligibility_round": record.eligibility_round,
                "snapshot_eligibility_status": record.eligibility_status,
                "eligibility_status": status,
                "final_output": status,
                "warnings": sorted(
                    set(record.warnings_json or []) | ({"ELIGIBILITY_SNAPSHOT_STALE"} if stale else set())
                ),
                "blockers": sorted(
                    set(record.blockers_json or []) | ({"POST_FID_GOVERNANCE_STALE"} if stale else set())
                ),
                "can_initialize": bool(record.eligible_for_initialization and not stale),
                "can_activate": bool(record.eligible_for_activation and not stale),
                "next_allowed_process": self._next_for_status(status),
                "allowed_actions": self._allowed_actions(status),
                "fid_decision_hash": record.fid_decision_hash,
                "decision_package_hash": record.decision_package_hash,
                "condition_snapshot_hash": record.condition_snapshot_hash,
                "eligibility_hash": record.eligibility_hash,
                "source_current": bool(record.source_current and not stale),
                "stale": stale,
                "persisted": True,
                "evaluated_at": record.evaluated_at,
                "evaluated_by": record.evaluated_by,
                "revision_version": record.revision_version,
            }
        )

    def _snapshot_from_out(
        self,
        item: EligibilityOut,
        config: AdminConfiguration,
        *,
        round_number: int,
        operation_type: str,
        operation_key: str,
        operation_payload_hash: str,
    ) -> PostFIDProjectEligibility:
        return PostFIDProjectEligibility(
            tenant_id=self.tenant_id,
            investment_decision_id=item.investment_decision_id,
            project_workspace_id=item.project_workspace_id,
            eligibility_round=round_number,
            fid_decision_hash=item.fid_decision_hash,
            decision_package_hash=item.decision_package_hash,
            project_state_snapshot={
                "classified_state": item.project_state,
                "workspace_status": item.workspace_status,
                "initialization_state": item.initialization_state,
            },
            condition_snapshot_hash=item.condition_snapshot_hash,
            eligibility_status=item.eligibility_status,
            warnings_json=item.warnings,
            blockers_json=item.blockers,
            eligible_for_initialization=item.can_initialize,
            eligible_for_activation=item.can_activate,
            evaluated_at=utc_now(),
            evaluated_by=self.actor_id,
            source_current=item.source_current,
            eligibility_hash=item.eligibility_hash,
            configuration_id=config.id,
            configuration_hash=config.content_hash,
            operation_type=operation_type,
            operation_key=operation_key,
            operation_payload_hash=operation_payload_hash,
            revision_version=round_number,
        )

    def _delta(self, previous: PostFIDProjectEligibility | None, current: EligibilityOut) -> RefreshDeltaOut:
        old_state = dict(previous.project_state_snapshot or {}) if previous else {}
        return RefreshDeltaOut(
            project_workspace_id=current.project_workspace_id,
            old_project_state=str(old_state.get("classified_state")) if previous else None,
            new_project_state=current.project_state,
            condition_changes=bool(previous and previous.condition_snapshot_hash != current.condition_snapshot_hash),
            fid_validity_changes=bool(previous and previous.source_current != current.source_current),
            scope_changes=False,
            old_eligibility=previous.eligibility_status if previous else None,
            new_eligibility=current.eligibility_status,
            old_source_hash=previous.eligibility_hash if previous else None,
            new_source_hash=current.eligibility_hash,
        )

    # Lookups/helpers ----------------------------------------------
    def _decision_out(self, decision: InvestmentDecision) -> PostFIDDecisionOut:
        projects = self.projects(decision.id)
        output = InvestmentDecisionService(self.db, self.tenant_id, self.actor_id, self.context)._authorization_output(
            decision
        )
        statuses = [item.eligibility_status for item in projects]
        if projects and all(value == NO_REACTIVATION for value in statuses):
            next_step = "READY_TO_ENTER_OPERATIONAL_MACROPROCESSES_REVIEW"
        elif READY_INITIALIZATION in statuses:
            next_step = "READY_FOR_EXISTING_PROJECT_WORKSPACE_INITIALIZATION"
        elif READY_ACTIVATION in statuses:
            next_step = "READY_FOR_EXISTING_PROJECT_WORKSPACE_ACTIVATION"
        else:
            next_step = "POST_FID_GOVERNANCE_COMPLETE"
        final_output = (
            "MIXED_PROJECT_ELIGIBILITY" if len(set(statuses)) > 1 else (statuses[0] if statuses else NOT_APPLICABLE)
        )
        return PostFIDDecisionOut(
            investment_decision_id=decision.id,
            decision_number=decision.decision_number,
            title=decision.title,
            gate_profile=decision.profile_code,
            status=decision.status,
            outcome=decision.outcome,
            is_fid=decision.is_fid,
            post_fid_handoff=output.get("post_fid_handoff"),
            final_output=final_output,
            project_count=len(projects),
            projects=projects,
            next=next_step,
        )

    def _scope_projects(self, decision: InvestmentDecision) -> list[EnterpriseWorkspace]:
        package = dict(decision.decision_package_snapshot_json or {})
        if package.get("exact_project_set_hash") != decision.decision_scope_hash:
            raise HTTPException(status_code=409, detail={"code": "PROJECT_SET_MISMATCH"})
        ids = [int(value) for value in package.get("selected_project_ids", [])]
        if not ids:
            return []
        rows = list(
            self.db.scalars(
                select(EnterpriseWorkspace).where(
                    EnterpriseWorkspace.tenant_id == self.tenant_id,
                    EnterpriseWorkspace.id.in_(ids),
                    EnterpriseWorkspace.workspace_type_code == "project",
                )
            ).all()
        )
        if {item.id for item in rows} != set(ids):
            raise HTTPException(status_code=409, detail={"code": "PROJECT_SCOPE_REFERENCE_INVALID"})
        return sorted(rows, key=lambda item: ids.index(item.id))

    def _project_in_scope(self, decision: InvestmentDecision, project_id: int) -> EnterpriseWorkspace:
        projects = self._scope_projects(decision)
        project = next((item for item in projects if item.id == project_id), None)
        if project is None:
            raise HTTPException(status_code=404, detail={"code": "PROJECT_NOT_IN_FID_SCOPE"})
        return project

    def _decision(self, decision_id: int, *, lock: bool = False) -> InvestmentDecision:
        statement = select(InvestmentDecision).where(
            InvestmentDecision.id == decision_id,
            InvestmentDecision.tenant_id == self.tenant_id,
        )
        if lock:
            statement = statement.with_for_update()
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "INVESTMENT_DECISION_NOT_FOUND"})
        return record

    def _initialization(self, project_id: int) -> ProjectWorkspaceInitialization | None:
        return self.db.scalar(
            select(ProjectWorkspaceInitialization).where(
                ProjectWorkspaceInitialization.tenant_id == self.tenant_id,
                ProjectWorkspaceInitialization.workspace_id == project_id,
            )
        )

    def _latest(self, decision_id: int, project_id: int, *, lock: bool = False) -> PostFIDProjectEligibility | None:
        statement = (
            select(PostFIDProjectEligibility)
            .where(
                PostFIDProjectEligibility.tenant_id == self.tenant_id,
                PostFIDProjectEligibility.investment_decision_id == decision_id,
                PostFIDProjectEligibility.project_workspace_id == project_id,
            )
            .order_by(PostFIDProjectEligibility.eligibility_round.desc())
            .limit(1)
        )
        if lock:
            statement = statement.with_for_update()
        return self.db.scalar(statement)

    def _configuration(self, configuration_id: int, *, lock: bool = False) -> AdminConfiguration:
        statement = select(AdminConfiguration).where(
            AdminConfiguration.id == configuration_id,
            AdminConfiguration.tenant_id == self.tenant_id,
            AdminConfiguration.kind == CONFIGURATION_KIND,
        )
        if lock:
            statement = statement.with_for_update()
        record = self.db.scalar(statement)
        if record is None:
            raise HTTPException(status_code=404, detail={"code": "POST_FID_CONFIGURATION_NOT_FOUND"})
        return record

    def _published_configuration(self, *, required: bool = True) -> AdminConfiguration | None:
        record = self.db.scalar(
            select(AdminConfiguration)
            .where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == CONFIGURATION_KIND,
                AdminConfiguration.status == "published",
            )
            .order_by(AdminConfiguration.revision.desc())
        )
        if record is None and required:
            raise HTTPException(status_code=409, detail={"code": "PUBLISHED_POST_FID_CONFIGURATION_REQUIRED"})
        return record

    @staticmethod
    def _transient_configuration(base: AdminConfiguration, content: dict) -> AdminConfiguration:
        transient = AdminConfiguration(
            id=base.id,
            tenant_id=base.tenant_id,
            kind=base.kind,
            code=base.code,
            name=base.name,
            description=base.description,
            status=base.status,
            revision=base.revision,
            version=base.version,
            content_json=content,
            content_hash=_hash(content),
            created_by_user_id=base.created_by_user_id,
        )
        return transient

    @staticmethod
    def _configuration_issues(content: dict) -> list[str]:
        issues: list[str] = []
        if "PYP-FFA" not in content.get("applicable_gate_profiles", []):
            issues.append("PYP_FFA_PROFILE_REQUIRED")
        if "CAPITAL_OWNER" not in content.get("applicable_governance_models", []):
            issues.append("CAPITAL_OWNER_DEFAULT_REQUIRED")
        handoff = dict(content.get("handoff_rules", {}))
        if not handoff.get("delegate_initialization") or not handoff.get("delegate_activation"):
            issues.append("EXISTING_LIFECYCLE_DELEGATION_REQUIRED")
        if handoff.get("automatic_initialization") or handoff.get("automatic_activation"):
            issues.append("AUTOMATIC_LIFECYCLE_EXECUTION_FORBIDDEN")
        return issues

    @staticmethod
    def _project_metadata(workspace: EnterpriseWorkspace) -> dict:
        return dict((workspace.defaults_json or {}).get("_project", {}))

    @staticmethod
    def _authorization_effective_date(decision: InvestmentDecision) -> datetime | None:
        package = dict(decision.decision_package_snapshot_json or {})
        value = package.get("authorization_effective_date") or dict(package.get("source_snapshot") or {}).get(
            "authorization_effective_date"
        )
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None

    def _allowed_actions(self, status: str) -> list[str]:
        roles = set(getattr(self.context, "role_codes", set()) or set())
        actions = ["can_view_post_fid", "can_view_history"]
        if roles & {"organization_admin", "post_fid_governance_manager"}:
            actions.append("can_refresh_eligibility")
        if status == READY_INITIALIZATION:
            actions.append("can_view_initialization_handoff")
            if roles & {"organization_admin", "project_workspace_initializer"}:
                actions.append("can_initialize_project")
        if status == READY_ACTIVATION:
            actions.append("can_view_activation_handoff")
            if roles & {"organization_admin", "project_workspace_activator"}:
                actions.append("can_activate_project")
        return actions

    @staticmethod
    def _next_for_status(status: str) -> str:
        if status == READY_INITIALIZATION:
            return "READY_FOR_EXISTING_PROJECT_WORKSPACE_INITIALIZATION"
        if status == READY_ACTIVATION:
            return "READY_FOR_EXISTING_PROJECT_WORKSPACE_ACTIVATION"
        return "POST_FID_GOVERNANCE_COMPLETE"

    def _status_event(self, item: PostFIDProjectEligibility) -> None:
        event = {
            BLOCKED: "post_fid_governance.blocked",
            READY_INITIALIZATION: "post_fid_governance.initialization_eligible",
            READY_ACTIVATION: "post_fid_governance.activation_eligible",
            NO_REACTIVATION: "post_fid_governance.no_reactivation_required",
            STALE: "post_fid_governance.stale_detected",
        }.get(item.eligibility_status)
        if event:
            self._event(
                event,
                "PostFIDProjectEligibility",
                item.id,
                {"project_workspace_id": item.project_workspace_id, "eligibility_status": item.eligibility_status},
            )

    def _handoff_event_once(self, event_type: str, decision_id: int, project_id: int, key: str) -> None:
        duplicate = self.db.scalar(
            select(SecurityEvent.id).where(
                SecurityEvent.tenant_id == self.tenant_id,
                SecurityEvent.event_type == event_type,
                SecurityEvent.metadata_json["idempotency_key"].as_string() == key,
            )
        )
        if duplicate is None:
            self._event(
                event_type,
                "InvestmentDecision",
                decision_id,
                {"project_workspace_id": project_id, "idempotency_key": key, "delegated": True},
            )
            self.db.commit()

    def _event(self, event_type: str, target_type: str, target_id: int | None, metadata: dict) -> None:
        decision_id = metadata.get("investment_decision_id")
        if decision_id is None and target_type == "InvestmentDecision":
            decision_id = target_id
        self.db.add(
            SecurityEvent(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                event_type=event_type,
                outcome="success",
                target_type=target_type,
                target_id=target_id,
                metadata_json={
                    "tenant_id": self.tenant_id,
                    "investment_decision_id": decision_id,
                    "actor_id": self.actor_id,
                    "timestamp": utc_now().isoformat(),
                    **metadata,
                },
            )
        )

    @staticmethod
    def _check_version(current: int, expected: int, code: str) -> None:
        if current != expected:
            raise HTTPException(status_code=409, detail={"code": code, "current_version": current})
