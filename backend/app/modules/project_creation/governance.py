"""Project governance models, source adapters and tenant-scoped policy resolution.

This module is deliberately transversal: it normalizes business sources and
resolves declarative policy, but never materializes a Project Workspace.  The
single materialization engine remains :class:`ProjectCreationService`.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domain.models import AdminConfiguration, EnterpriseWorkspace, SecurityEvent


class ProjectGovernanceModel(StrEnum):
    CAPITAL_OWNER = "CAPITAL_OWNER"
    CONTRACTOR_DELIVERY = "CONTRACTOR_DELIVERY"
    DIRECT_INTERNAL = "DIRECT_INTERNAL"


class ProjectSourceContextType(StrEnum):
    STRATEGIC_GATE_DECISION = "STRATEGIC_GATE_DECISION"
    CONTRACT_AWARD = "CONTRACT_AWARD"
    DIRECT_AUTHORIZATION = "DIRECT_AUTHORIZATION"


GOVERNANCE_LABELS: dict[str, str] = {
    ProjectGovernanceModel.CAPITAL_OWNER: "Capital Owner",
    ProjectGovernanceModel.CONTRACTOR_DELIVERY: "Contractor Delivery",
    ProjectGovernanceModel.DIRECT_INTERNAL: "Direct Internal",
}

SOURCE_BY_GOVERNANCE: dict[str, str] = {
    ProjectGovernanceModel.CAPITAL_OWNER: ProjectSourceContextType.STRATEGIC_GATE_DECISION,
    ProjectGovernanceModel.CONTRACTOR_DELIVERY: ProjectSourceContextType.CONTRACT_AWARD,
    ProjectGovernanceModel.DIRECT_INTERNAL: ProjectSourceContextType.DIRECT_AUTHORIZATION,
}

PROJECT_GOVERNANCE_POLICY_KIND = "project_governance_policy"
PROJECT_GOVERNANCE_POLICY_VERSION = "multi-source-v1.0"


DEFAULT_GOVERNANCE_POLICIES: dict[str, dict[str, Any]] = {
    ProjectGovernanceModel.CAPITAL_OWNER: {
        "governance_model": ProjectGovernanceModel.CAPITAL_OWNER,
        "allowed_source_context_types": [ProjectSourceContextType.STRATEGIC_GATE_DECISION],
        "allowed_parent_types": ["portfolio", "program"],
        "required_fields": [
            "project_name",
            "parent_workspace_id",
            "project_template_config_id",
            "project_manager_user_id",
            "strategic_objective_codes",
        ],
        "optional_fields": ["planned_start", "planned_finish", "estimated_budget"],
        "required_source_fields": ["strategic_gate_decision_id"],
        "template_required": True,
        "project_manager_required": True,
        "strategic_objective_required": True,
        "portfolio_required": True,
        "fel_required": True,
        "pdri_required": False,
        "fid_required_for_creation": False,
        "contract_source_required": False,
        "notice_to_proceed_required": False,
        "initialization_requirements": [
            "source_valid",
            "project_manager",
            "template",
            "strategic_objective",
        ],
        "activation_requirements": ["investment_execution_authorized"],
        "pending_reason": "PORTFOLIO_AND_PROJECT_DEFINITION_REQUIRED",
        "planning_stage": "PORTFOLIO_AND_FEL_PLANNING",
    },
    ProjectGovernanceModel.CONTRACTOR_DELIVERY: {
        "governance_model": ProjectGovernanceModel.CONTRACTOR_DELIVERY,
        "allowed_source_context_types": [ProjectSourceContextType.CONTRACT_AWARD],
        "allowed_parent_types": ["portfolio", "program"],
        "required_fields": [
            "project_name",
            "parent_workspace_id",
            "project_template_config_id",
            "project_manager_user_id",
        ],
        "optional_fields": [
            "strategic_objective_codes",
            "planned_start",
            "planned_finish",
            "estimated_budget",
        ],
        "required_source_fields": ["client", "contract_number", "contractual_scope"],
        "template_required": True,
        "project_manager_required": True,
        "strategic_objective_required": False,
        "portfolio_required": False,
        "fel_required": False,
        "pdri_required": False,
        "fid_required_for_creation": False,
        "contract_source_required": True,
        "notice_to_proceed_required": False,
        "initialization_requirements": [
            "source_valid",
            "project_manager",
            "template",
            "required_fields",
            "mobilization_readiness",
        ],
        "activation_requirements": ["contract_or_mobilization_authorized"],
        "pending_reason": "INITIALIZATION_AND_MOBILIZATION_REQUIRED",
        "planning_stage": "CONTRACT_MOBILIZATION",
    },
    ProjectGovernanceModel.DIRECT_INTERNAL: {
        "governance_model": ProjectGovernanceModel.DIRECT_INTERNAL,
        "allowed_source_context_types": [ProjectSourceContextType.DIRECT_AUTHORIZATION],
        "allowed_parent_types": ["portfolio", "program"],
        "required_fields": [
            "project_name",
            "parent_workspace_id",
            "project_template_config_id",
            "project_manager_user_id",
        ],
        "optional_fields": [
            "strategic_objective_codes",
            "planned_start",
            "planned_finish",
            "estimated_budget",
        ],
        "required_source_fields": ["authorization_reference", "sponsor"],
        "template_required": True,
        "project_manager_required": True,
        "strategic_objective_required": False,
        "portfolio_required": False,
        "fel_required": False,
        "pdri_required": False,
        "fid_required_for_creation": False,
        "contract_source_required": False,
        "notice_to_proceed_required": False,
        "initialization_requirements": ["source_valid", "project_manager", "template", "basic_scope"],
        "activation_requirements": ["direct_internal_authorized"],
        "pending_reason": "INITIALIZATION_REQUIRED",
        "planning_stage": "DIRECT_AUTHORIZATION",
    },
}


@dataclass(frozen=True)
class NormalizedProjectCreationSource:
    governance_model: str
    source_context_type: str
    source_context_id: int | None
    source_external_key: str | None
    idempotency_key: str | None
    snapshot: dict[str, Any]
    source_hash: str
    strategic_fields: dict[str, Any]


@dataclass(frozen=True)
class EffectiveProjectGovernancePolicy:
    configuration: AdminConfiguration
    content: dict[str, Any]
    source_workspace_id: int | None
    resolution_chain: tuple[str, ...]


class ProjectCreationSourceAdapter:
    governance_model: str
    source_context_type: str

    def normalize(self, values: dict[str, Any]) -> NormalizedProjectCreationSource:
        raise NotImplementedError

    @staticmethod
    def _snapshot(values: dict[str, Any]) -> dict[str, Any]:
        raw = values.get("source_snapshot") or values.get("source_snapshot_json") or {}
        if not isinstance(raw, dict):
            raise HTTPException(status_code=422, detail="SOURCE_SNAPSHOT_MUST_BE_AN_OBJECT")
        return _json_compatible(raw)

    def _build(
        self,
        *,
        values: dict[str, Any],
        snapshot: dict[str, Any],
        source_context_id: int | None,
        source_external_key: str | None,
        idempotency_key: str | None,
        strategic_fields: dict[str, Any] | None = None,
    ) -> NormalizedProjectCreationSource:
        fingerprint = {
            "governance_model": self.governance_model,
            "source_context_type": self.source_context_type,
            "source_context_id": source_context_id,
            "source_external_key": source_external_key,
            "snapshot": snapshot,
        }
        return NormalizedProjectCreationSource(
            governance_model=self.governance_model,
            source_context_type=self.source_context_type,
            source_context_id=source_context_id,
            source_external_key=source_external_key,
            idempotency_key=idempotency_key,
            snapshot=snapshot,
            source_hash=_hash(fingerprint),
            strategic_fields=strategic_fields or {},
        )


class StrategicGateSourceAdapter(ProjectCreationSourceAdapter):
    governance_model = ProjectGovernanceModel.CAPITAL_OWNER
    source_context_type = ProjectSourceContextType.STRATEGIC_GATE_DECISION

    def normalize(self, values: dict[str, Any]) -> NormalizedProjectCreationSource:
        decision_id = values.get("strategic_gate_decision_id") or values.get("source_context_id")
        if not decision_id:
            raise HTTPException(status_code=422, detail="STRATEGIC_GATE_DECISION_REQUIRED")
        snapshot = self._snapshot(
            {"source_snapshot": values.get("strategic_source_snapshot_json") or values.get("source_snapshot")}
        )
        strategic_fields = {
            key: values.get(key)
            for key in (
                "strategic_gate_decision_id",
                "source_project_proposal_id",
                "source_idea_id",
                "source_decision_hash",
                "source_readiness_hash",
                "strategic_target_portfolio_workspace_id",
                "strategic_mapping_configuration_id",
                "strategic_mapping_revision",
                "strategic_mapping_hash",
                "strategic_source_snapshot_json",
            )
            if values.get(key) is not None
        }
        strategic_fields["strategic_gate_decision_id"] = int(decision_id)
        strategic_fields["strategic_source_snapshot_json"] = snapshot
        return self._build(
            values=values,
            snapshot=snapshot,
            source_context_id=int(decision_id),
            source_external_key=None,
            idempotency_key=None,
            strategic_fields=strategic_fields,
        )


class ContractAwardSourceAdapter(ProjectCreationSourceAdapter):
    governance_model = ProjectGovernanceModel.CONTRACTOR_DELIVERY
    source_context_type = ProjectSourceContextType.CONTRACT_AWARD

    def normalize(self, values: dict[str, Any]) -> NormalizedProjectCreationSource:
        snapshot = self._snapshot(values)
        missing = _missing(snapshot, ("client", "contract_number", "contractual_scope"))
        if missing:
            raise HTTPException(
                status_code=422,
                detail={"code": "CONTRACT_SOURCE_INCOMPLETE", "missing": missing},
            )
        external_key = str(values.get("source_external_key") or snapshot["contract_number"]).strip()
        if not external_key:
            raise HTTPException(status_code=422, detail="CONTRACT_SOURCE_EXTERNAL_KEY_REQUIRED")
        return self._build(
            values=values,
            snapshot=snapshot,
            source_context_id=_positive_int(values.get("source_context_id")),
            source_external_key=external_key,
            idempotency_key=str(values.get("idempotency_key") or external_key).strip(),
        )


class DirectAuthorizationSourceAdapter(ProjectCreationSourceAdapter):
    governance_model = ProjectGovernanceModel.DIRECT_INTERNAL
    source_context_type = ProjectSourceContextType.DIRECT_AUTHORIZATION

    def normalize(self, values: dict[str, Any]) -> NormalizedProjectCreationSource:
        snapshot = self._snapshot(values)
        missing = _missing(snapshot, ("authorization_reference", "sponsor"))
        if missing:
            raise HTTPException(
                status_code=422,
                detail={"code": "DIRECT_AUTHORIZATION_INCOMPLETE", "missing": missing},
            )
        idempotency_key = str(values.get("idempotency_key") or "").strip()
        if not idempotency_key:
            raise HTTPException(status_code=422, detail="DIRECT_IDEMPOTENCY_KEY_REQUIRED")
        external_key = str(values.get("source_external_key") or snapshot["authorization_reference"]).strip()
        return self._build(
            values=values,
            snapshot=snapshot,
            source_context_id=_positive_int(values.get("source_context_id")),
            source_external_key=external_key,
            idempotency_key=idempotency_key,
        )


SOURCE_ADAPTERS: dict[str, ProjectCreationSourceAdapter] = {
    ProjectGovernanceModel.CAPITAL_OWNER: StrategicGateSourceAdapter(),
    ProjectGovernanceModel.CONTRACTOR_DELIVERY: ContractAwardSourceAdapter(),
    ProjectGovernanceModel.DIRECT_INTERNAL: DirectAuthorizationSourceAdapter(),
}


def normalize_project_source(values: dict[str, Any]) -> NormalizedProjectCreationSource:
    try:
        governance_model = ProjectGovernanceModel(str(values.get("governance_model", "")).strip().upper())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="PROJECT_GOVERNANCE_MODEL_INVALID") from exc
    adapter = SOURCE_ADAPTERS[governance_model]
    requested_type = str(values.get("source_context_type") or adapter.source_context_type).strip().upper()
    if requested_type != adapter.source_context_type:
        raise HTTPException(status_code=422, detail="SOURCE_CONTEXT_NOT_ALLOWED_FOR_GOVERNANCE_MODEL")
    return adapter.normalize(values)


class ProjectGovernancePolicyService:
    """Revisioned AdminConfiguration policy with hierarchical lookup."""

    def __init__(self, db: Session, tenant_id: int, actor_id: int) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.actor_id = actor_id

    def ensure_seed(self) -> None:
        for model, content in DEFAULT_GOVERNANCE_POLICIES.items():
            code = self.configuration_code(model)
            if self._latest(code, published_only=True) is not None:
                continue
            record = AdminConfiguration(
                tenant_id=self.tenant_id,
                kind=PROJECT_GOVERNANCE_POLICY_KIND,
                code=code,
                name=f"{GOVERNANCE_LABELS[model]} Project Governance Policy",
                description="Tenant default for the shared Project Creation Process.",
                status="published",
                revision=1,
                version=1,
                content_json={
                    **_json_compatible(content),
                    "scope": "tenant",
                    "scope_workspace_id": None,
                    "configuration_version": PROJECT_GOVERNANCE_POLICY_VERSION,
                },
                content_hash=_hash(content),
                published_at=utc_now(),
                created_by_user_id=self.actor_id,
            )
            self.db.add(record)
            self.db.flush()
            self._event("project_governance_model.seeded", record, {"governance_model": model})

    def list_policies(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for model in ProjectGovernanceModel:
            record = self._latest(self.configuration_code(model), published_only=True)
            if record is None:
                continue
            result.append(self.configuration_out(record))
        return result

    def configure(
        self,
        governance_model: str,
        content: dict[str, Any],
        *,
        scope_workspace_id: int | None = None,
    ) -> dict[str, Any]:
        model = ProjectGovernanceModel(governance_model.upper())
        normalized = self._validated_content(model, content, scope_workspace_id)
        code = self.configuration_code(model, scope_workspace_id)
        current = self._latest(code, published_only=True)
        if current is not None and current.content_json == normalized:
            return self.configuration_out(current)
        if current is not None:
            current.status = "archived"
            current.version += 1
            current.updated_at = utc_now()
        revision = (current.revision if current else 0) + 1
        record = AdminConfiguration(
            tenant_id=self.tenant_id,
            kind=PROJECT_GOVERNANCE_POLICY_KIND,
            code=code,
            name=f"{GOVERNANCE_LABELS[model]} Project Governance Policy",
            description="Governance-specific policy for the shared Project Creation Process.",
            status="published",
            revision=revision,
            version=1,
            content_json=normalized,
            content_hash=_hash(normalized),
            published_at=utc_now(),
            created_by_user_id=self.actor_id,
        )
        self.db.add(record)
        self.db.flush()
        self._event(
            "project_governance_model.published",
            record,
            {"governance_model": model, "scope_workspace_id": scope_workspace_id},
        )
        self.db.commit()
        self.db.refresh(record)
        return self.configuration_out(record)

    def resolve(self, governance_model: str, parent_workspace_id: int | None) -> EffectiveProjectGovernancePolicy:
        model = ProjectGovernanceModel(governance_model.upper())
        chain = self._workspace_chain(parent_workspace_id)
        selected: AdminConfiguration | None = None
        selected_workspace_id: int | None = None
        resolution_chain = ["tenant"]
        tenant_record = self._latest(self.configuration_code(model), published_only=True)
        if tenant_record is not None:
            selected = tenant_record
        for workspace in chain:
            resolution_chain.append(f"{workspace.workspace_type_code}:{workspace.id}")
            override = self._latest(self.configuration_code(model, workspace.id), published_only=True)
            if override is not None:
                selected = override
                selected_workspace_id = workspace.id
        if selected is None:
            raise HTTPException(status_code=409, detail="PROJECT_GOVERNANCE_POLICY_NOT_PUBLISHED")
        return EffectiveProjectGovernancePolicy(
            configuration=selected,
            content=dict(selected.content_json or {}),
            source_workspace_id=selected_workspace_id,
            resolution_chain=tuple(resolution_chain),
        )

    def preview(self, values: dict[str, Any]) -> dict[str, Any]:
        model = ProjectGovernanceModel(str(values.get("governance_model", "")).upper())
        source_type = str(values.get("source_context_type") or SOURCE_BY_GOVERNANCE[model])
        parent_id = _positive_int(values.get("parent_workspace_id"))
        effective = self.resolve(model, parent_id)
        policy = effective.content
        warnings: list[str] = []
        blockers: list[str] = []
        if source_type not in policy.get("allowed_source_context_types", []):
            blockers.append("SOURCE_CONTEXT_NOT_ALLOWED_FOR_GOVERNANCE_MODEL")
        if values.get("project_type") and values.get("project_type") == model:
            warnings.append("PROJECT_TYPE_AND_GOVERNANCE_MODEL_ARE_INDEPENDENT")
        return {
            "governance_model": model,
            "source_context_type": source_type,
            "effective_policy": policy,
            "source_workspace_id": effective.source_workspace_id,
            "resolution_chain": list(effective.resolution_chain),
            "revision": effective.configuration.revision,
            "hash": effective.configuration.content_hash,
            "required_fields": list(policy.get("required_fields", [])),
            "optional_fields": list(policy.get("optional_fields", [])),
            "required_source": list(policy.get("required_source_fields", [])),
            "required_approvals": ["FOUR_EYES"] if policy.get("approval_required", True) else [],
            "initialization_requirements": list(policy.get("initialization_requirements", [])),
            "activation_requirements": list(policy.get("activation_requirements", [])),
            "warnings": warnings,
            "blockers": blockers,
            "persisted": False,
        }

    @staticmethod
    def configuration_code(governance_model: str, workspace_id: int | None = None) -> str:
        scope = f"workspace-{workspace_id}" if workspace_id is not None else "tenant"
        return f"project-governance-{str(governance_model).lower().replace('_', '-')}-{scope}"

    @staticmethod
    def configuration_out(record: AdminConfiguration) -> dict[str, Any]:
        content = dict(record.content_json or {})
        governance_model = str(content.get("governance_model", ""))
        return {
            "id": record.id,
            "configuration_id": record.id,
            "code": record.code,
            "name": record.name,
            "label": GOVERNANCE_LABELS.get(governance_model, governance_model),
            "governance_model": governance_model,
            "description": record.description,
            "status": record.status,
            "revision": record.revision,
            "version": record.version,
            "content_json": content,
            "content": content,
            "content_hash": record.content_hash,
            "source_workspace_id": content.get("scope_workspace_id"),
            "source_workspace_name": None,
            "resolution_chain": [str(content.get("scope", "tenant"))],
            "published_at": record.published_at,
        }

    def _validated_content(
        self,
        model: ProjectGovernanceModel,
        values: dict[str, Any],
        scope_workspace_id: int | None,
    ) -> dict[str, Any]:
        base = dict(DEFAULT_GOVERNANCE_POLICIES[model])
        allowed_keys = set(base) | {"approval_required"}
        for key, value in values.items():
            if key in allowed_keys:
                base[key] = _json_compatible(value)
        base["governance_model"] = model
        expected_source = SOURCE_BY_GOVERNANCE[model]
        allowed_sources = [str(item).upper() for item in base.get("allowed_source_context_types", [])]
        if expected_source not in allowed_sources:
            raise HTTPException(status_code=422, detail="DEFAULT_SOURCE_CONTEXT_MUST_REMAIN_ALLOWED")
        if scope_workspace_id is not None:
            workspace = self.db.scalar(
                select(EnterpriseWorkspace).where(
                    EnterpriseWorkspace.id == scope_workspace_id,
                    EnterpriseWorkspace.tenant_id == self.tenant_id,
                )
            )
            if workspace is None:
                raise HTTPException(status_code=404, detail="Policy scope Workspace not found")
        return {
            **base,
            "scope": "workspace" if scope_workspace_id is not None else "tenant",
            "scope_workspace_id": scope_workspace_id,
            "configuration_version": PROJECT_GOVERNANCE_POLICY_VERSION,
        }

    def _latest(self, code: str, *, published_only: bool) -> AdminConfiguration | None:
        statement = select(AdminConfiguration).where(
            AdminConfiguration.tenant_id == self.tenant_id,
            AdminConfiguration.kind == PROJECT_GOVERNANCE_POLICY_KIND,
            AdminConfiguration.code == code,
        )
        if published_only:
            statement = statement.where(AdminConfiguration.status == "published")
        return self.db.scalar(statement.order_by(AdminConfiguration.revision.desc()).limit(1))

    def _workspace_chain(self, workspace_id: int | None) -> list[EnterpriseWorkspace]:
        if workspace_id is None:
            return []
        chain: list[EnterpriseWorkspace] = []
        current_id: int | None = workspace_id
        visited: set[int] = set()
        while current_id is not None and current_id not in visited:
            visited.add(current_id)
            workspace = self.db.scalar(
                select(EnterpriseWorkspace).where(
                    EnterpriseWorkspace.tenant_id == self.tenant_id,
                    EnterpriseWorkspace.id == current_id,
                )
            )
            if workspace is None:
                break
            chain.append(workspace)
            current_id = workspace.parent_id
        return list(reversed(chain))

    def _event(self, event_type: str, record: AdminConfiguration, metadata: dict[str, Any]) -> None:
        self.db.add(
            SecurityEvent(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                event_type=event_type,
                outcome="success",
                target_type=PROJECT_GOVERNANCE_POLICY_KIND,
                target_id=record.id,
                metadata_json={
                    **metadata,
                    "configuration_id": record.id,
                    "revision": record.revision,
                    "hash": record.content_hash,
                },
            )
        )


def source_requirements_status(
    governance_model: str | None,
    source_context_type: str | None,
    source_snapshot: dict[str, Any] | None,
    policy: dict[str, Any] | None,
    *,
    strategic_gate_decision_id: int | None = None,
) -> tuple[list[str], list[str]]:
    """Return source/readiness blockers and warnings without reinterpreting history."""

    if not governance_model:
        return [], ["LEGACY_GOVERNANCE_MODEL_NOT_CLASSIFIED"]
    content = policy or DEFAULT_GOVERNANCE_POLICIES[governance_model]
    expected_source = SOURCE_BY_GOVERNANCE[governance_model]
    blockers: list[str] = []
    if source_context_type != expected_source:
        blockers.append("SOURCE_CONTEXT_NOT_ALLOWED_FOR_GOVERNANCE_MODEL")
    snapshot = source_snapshot or {}
    required = list(content.get("required_source_fields", []))
    if governance_model == ProjectGovernanceModel.CAPITAL_OWNER:
        if not strategic_gate_decision_id:
            blockers.append("STRATEGIC_GATE_DECISION_REQUIRED")
        required = [item for item in required if item != "strategic_gate_decision_id"]
    blockers.extend(f"SOURCE_FIELD_REQUIRED:{field}" for field in _missing(snapshot, required))
    if content.get("notice_to_proceed_required") and not snapshot.get("notice_to_proceed_date"):
        blockers.append("NOTICE_TO_PROCEED_REQUIRED")
    return sorted(set(blockers)), []


def activation_authorization_status(governance_model: str | None, snapshot: dict[str, Any] | None) -> bool:
    if not governance_model:
        return True
    values = snapshot or {}
    if governance_model == ProjectGovernanceModel.CAPITAL_OWNER:
        return bool(values.get("execution_authorized"))
    if governance_model == ProjectGovernanceModel.CONTRACTOR_DELIVERY:
        return bool(values.get("mobilization_authorized") or values.get("notice_to_proceed_date"))
    if governance_model == ProjectGovernanceModel.DIRECT_INTERNAL:
        return bool(values.get("authorization_approved"))
    return False


def _missing(values: dict[str, Any], keys: Any) -> list[str]:
    return sorted(key for key in keys if values.get(key) in (None, "", []))


def _positive_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="SOURCE_CONTEXT_ID_INVALID") from exc
    if parsed < 1:
        raise HTTPException(status_code=422, detail="SOURCE_CONTEXT_ID_INVALID")
    return parsed


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _json_compatible(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))
