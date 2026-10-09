"""Enterprise policy authority for Capacity / Appetite / Thresholds.

AdminConfiguration is the aggregate and SecurityEvent is the existing durable
command receipt. Commands serialize on the tenant row before checking receipts;
no new policy tables, executable expression language, Project Risk transactions,
readiness recalculation, or Gate decisions are introduced.
"""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.v1._helpers import touch_collaborative_record
from app.api.v1.routers.admin_configuration import _workspace_path
from app.core.time import utc_now
from app.domain.models import AdminConfiguration, EnterpriseWorkspace, SecurityEvent, Tenant
from app.modules.enterprise_structure.permissions import (
    EnterprisePermissionContext,
    ensure_enterprise_permissions,
    require_enterprise_permission,
)
from app.modules.investment_evidence_policy.decision_criteria import CONTROLLED_OPERATORS, _operator_satisfied
from app.modules.project_creation.models import ProjectCreationRequest
from app.modules.project_definition.service import ProjectDefinitionService
from app.modules.risk_governance.schemas import (
    ConfigurationPreviewIn,
    EffectiveContextIn,
    EffectiveContextOut,
    RiskConfigurationOut,
    RiskGovernancePolicy,
    ThresholdEvaluationIn,
    ThresholdEvaluationOut,
)

CONFIGURATION_KIND = "risk_governance_policy"
DEFAULT_CONFIGURATION_CODE = "default"
THRESHOLD_OPERATORS = tuple(
    item for item in CONTROLLED_OPERATORS if item not in {"IS_READY", "IS_CURRENT", "COVERAGE_AT_LEAST"}
) + ("WITHIN_RANGE", "OUTSIDE_RANGE")
NUMERIC_TYPES = frozenset({"QUANTITATIVE", "RANGE", "PERCENTAGE", "CURRENCY", "DURATION"})
NUMERIC_OPERATORS = frozenset(
    {"GREATER_THAN", "GREATER_THAN_OR_EQUAL", "LESS_THAN", "LESS_THAN_OR_EQUAL", "WITHIN_RANGE", "OUTSIDE_RANGE"}
)
CONTEXT_FIELDS = {
    "project_types": "project_type",
    "governance_models": "governance_model",
    "strategic_themes": "strategic_theme",
    "investment_categories": "investment_category",
}

# Deliberately neutral baseline: no quantitative risk tolerance is invented.
# Explicit ADMIN configuration is the only source of risk dimensions/boundaries.
DEFAULT_CONFIGURATION: dict[str, Any] = {
    "scope": {"type": "tenant", "workspace_id": None},
    "inherit_to_descendants": True,
    "effective_from": "2026-01-01",
    "effective_to": None,
    "dimensions": [],
    "applicability": {
        "project_types": [],
        "governance_models": ["CAPITAL_OWNER"],
        "strategic_themes": [],
        "investment_categories": [],
    },
    "capacity_statements": [],
    "appetite_statements": [],
    "thresholds": [],
    "escalation_rules": [],
    "separation_of_duties": {"preparer_cannot_publish": True},
}


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = Decimal(str(value))
        return result if result.is_finite() else None
    except (InvalidOperation, ValueError, TypeError):
        return None


class RiskGovernanceService:
    def __init__(self, db: Session, tenant_id: int, actor_id: int, context: EnterprisePermissionContext):
        self.db, self.tenant_id, self.actor_id, self.context = db, tenant_id, actor_id, context
        self._permission_contexts: dict[str, EnterprisePermissionContext | None] = {}

    def configuration_output(self, record: AdminConfiguration) -> RiskConfigurationOut:
        """Actor-aware UI affordances; command authorization remains authoritative."""
        result = RiskConfigurationOut.model_validate(record)
        actions: list[str] = []
        if self._can_mutate(record, "risk_governance.admin.configure"):
            if record.status == "published":
                actions.append("clone")
            if record.status == "draft":
                actions.extend(["edit", "save"])
        if self._can_mutate(record, "risk_governance.admin.publish"):
            if record.status == "draft" and not self._sod_denied(record, record.content_json):
                actions.append("publish")
            if record.status != "archived":
                actions.append("archive")
        result.allowed_actions = actions
        return result

    def _can_mutate(self, record: AdminConfiguration, permission: str) -> bool:
        if permission not in self._permission_contexts:
            try:
                self._permission_contexts[permission] = require_enterprise_permission(
                    self.db,
                    self.tenant_id,
                    self.actor_id,
                    permission,
                    allowed_role_codes=frozenset(
                        {"organization_admin", "configuration_admin", "risk_configuration_admin"}
                    ),
                    bootstrap=False,
                )
            except HTTPException as exc:
                if exc.status_code != 403:
                    raise
                self._permission_contexts[permission] = None
        context = self._permission_contexts[permission]
        if context is None:
            return False
        target_id = record.content_json.get("scope", {}).get("workspace_id")
        if context.organization_wide:
            return True
        return target_id is not None and bool(
            {item.id for item in _workspace_path(self.db, self.tenant_id, self._workspace(target_id))}
            & set(context.workspace_ids)
        )

    def ensure_seed(self) -> None:
        """Explicit additive provisioning; never called by a read or resolver."""
        self._lock_tenant()
        ensure_enterprise_permissions(self.db, self.tenant_id, self.actor_id)
        existing = self.db.scalar(
            select(AdminConfiguration.id).where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == CONFIGURATION_KIND,
                AdminConfiguration.code == DEFAULT_CONFIGURATION_CODE,
            )
        )
        if existing is None:
            content = deepcopy(DEFAULT_CONFIGURATION)
            self.db.add(
                AdminConfiguration(
                    tenant_id=self.tenant_id,
                    kind=CONFIGURATION_KIND,
                    code=DEFAULT_CONFIGURATION_CODE,
                    name="Risk Governance",
                    description="Neutral enterprise policy template; ADMIN configures actual risk boundaries.",
                    status="published",
                    revision=1,
                    version=1,
                    content_json=content,
                    content_hash=_hash(content),
                    published_at=utc_now(),
                    created_by_user_id=self.actor_id,
                )
            )
        self.db.commit()

    def configurations(self, *, code: str | None = None) -> list[AdminConfiguration]:
        statement = select(AdminConfiguration).where(
            AdminConfiguration.tenant_id == self.tenant_id, AdminConfiguration.kind == CONFIGURATION_KIND
        )
        if code is not None:
            statement = statement.where(AdminConfiguration.code == code)
        records = self.db.scalars(statement.order_by(AdminConfiguration.code, AdminConfiguration.revision.desc())).all()
        return [record for record in records if self._visible(record)]

    def configuration(self, configuration_id: int, *, lock: bool = False) -> AdminConfiguration:
        statement = select(AdminConfiguration).where(
            AdminConfiguration.id == configuration_id,
            AdminConfiguration.tenant_id == self.tenant_id,
            AdminConfiguration.kind == CONFIGURATION_KIND,
        )
        record = self.db.scalar(statement.with_for_update() if lock else statement)
        if record is None or not self._visible(record):
            raise HTTPException(404, detail={"code": "RISK_GOVERNANCE_CONFIGURATION_NOT_FOUND"})
        return record

    def effective(self, payload: EffectiveContextIn) -> EffectiveContextOut:
        return self._resolve(payload)

    def preview(self, payload: ConfigurationPreviewIn) -> EffectiveContextOut:
        if payload.content_json is not None and payload.configuration_id is None:
            raise HTTPException(422, detail={"code": "CONFIGURATION_PREVIEW_ID_REQUIRED"})
        if payload.configuration_id is None:
            return self._resolve(payload)
        record = self.configuration(payload.configuration_id)
        content = self.validate_configuration(
            payload.content_json if payload.content_json is not None else record.content_json
        )
        self._assert_same_scope(record.content_json, content)
        return self._resolve(payload, preview=(record, content))

    def clone_configuration(
        self,
        configuration_id: int,
        expected_version: int,
        idempotency_key: str,
        *,
        target_workspace_id: int | None = None,
    ) -> RiskConfigurationOut:
        self._lock_tenant()
        source = self.configuration(configuration_id, lock=True)
        target_id = (
            target_workspace_id if target_workspace_id is not None else source.content_json["scope"]["workspace_id"]
        )
        self._assert_mutable_scope(target_id)
        request = {
            "source_id": configuration_id,
            "target_workspace_id": target_id,
            "expected_version": expected_version,
        }
        replay = self._replay("cloned", idempotency_key, request)
        if replay is not None:
            return replay
        self._check_version(source, expected_version)
        if source.status != "published":
            raise HTTPException(409, detail={"code": "PUBLISHED_CONFIGURATION_REQUIRED"})
        target = self._workspace(target_id) if target_id else None
        if target is not None and target.workspace_type_code not in {"enterprise", "business-unit", "portfolio"}:
            raise HTTPException(422, detail={"code": "RISK_GOVERNANCE_SCOPE_INVALID"})
        code = source.code if target_id == source.content_json["scope"]["workspace_id"] else f"workspace-{target_id}"
        revision = (
            int(
                self.db.scalar(
                    select(func.coalesce(func.max(AdminConfiguration.revision), 0)).where(
                        AdminConfiguration.tenant_id == self.tenant_id,
                        AdminConfiguration.kind == CONFIGURATION_KIND,
                        AdminConfiguration.code == code,
                    )
                )
                or 0
            )
            + 1
        )
        content = deepcopy(source.content_json)
        content["scope"] = {"type": "workspace" if target_id else "tenant", "workspace_id": target_id}
        record = AdminConfiguration(
            tenant_id=self.tenant_id,
            kind=CONFIGURATION_KIND,
            code=code,
            name=f"{source.name} — {target.name}" if target else source.name,
            description=source.description,
            status="draft",
            revision=revision,
            version=1,
            content_json=content,
            content_hash=_hash(content),
            created_by_user_id=self.actor_id,
        )
        self.db.add(record)
        self.db.flush()
        return self._finish_command(
            record,
            "cloned",
            idempotency_key,
            request,
            {
                "source_configuration_id": source.id,
                "source_requires_sod": bool(
                    source.content_json.get("separation_of_duties", {}).get("preparer_cannot_publish", True)
                ),
            },
        )

    def update_configuration(
        self, configuration_id: int, expected_version: int, *, name: str, description: str, content: dict[str, Any]
    ) -> RiskConfigurationOut:
        self._lock_tenant()
        record = self.configuration(configuration_id, lock=True)
        self._assert_mutable_scope(record.content_json["scope"]["workspace_id"])
        self._check_version(record, expected_version)
        if record.status != "draft":
            raise HTTPException(409, detail={"code": "DRAFT_CONFIGURATION_REQUIRED"})
        normalized = self.validate_configuration(content)
        self._assert_same_scope(record.content_json, normalized)
        if not name.strip():
            raise HTTPException(422, detail={"code": "CONFIGURATION_NAME_REQUIRED"})
        record.name, record.description = name.strip(), description.strip()
        record.content_json, record.content_hash = normalized, _hash(normalized)
        touch_collaborative_record(record)
        self._event("updated", record.id, {"content_hash": record.content_hash})
        self.db.commit()
        self.db.refresh(record)
        return self.configuration_output(record)

    def publish_configuration(
        self, configuration_id: int, expected_version: int, idempotency_key: str
    ) -> RiskConfigurationOut:
        self._lock_tenant()
        record = self.configuration(configuration_id, lock=True)
        self._assert_mutable_scope(record.content_json["scope"]["workspace_id"])
        request = {"configuration_id": configuration_id, "expected_version": expected_version}
        replay = self._replay("published", idempotency_key, request)
        if replay is not None:
            return replay
        self._check_version(record, expected_version)
        if record.status != "draft":
            raise HTTPException(409, detail={"code": "DRAFT_CONFIGURATION_REQUIRED"})
        normalized = self.validate_configuration(record.content_json)
        if self._sod_denied(record, normalized):
            raise HTTPException(409, detail={"code": "RISK_GOVERNANCE_SOD_PUBLISH_DENIED"})
        # Prior publications remain available for their effective dates/history.
        # Effective resolution selects a version, never merges risk boundaries.
        record.content_json, record.content_hash = normalized, _hash(normalized)
        record.status, record.published_at = "published", utc_now()
        touch_collaborative_record(record)
        return self._finish_command(record, "published", idempotency_key, request, {"reviewer_user_id": self.actor_id})

    def _sod_denied(self, record: AdminConfiguration, normalized: dict[str, Any]) -> bool:
        cloned = self.db.scalar(
            select(SecurityEvent)
            .where(
                SecurityEvent.tenant_id == self.tenant_id,
                SecurityEvent.event_type == "risk_governance.config.cloned",
                SecurityEvent.target_id == record.id,
            )
            .order_by(SecurityEvent.id.desc())
        )
        requires_sod = normalized["separation_of_duties"]["preparer_cannot_publish"] or (
            cloned is not None and bool(cloned.metadata_json.get("source_requires_sod", True))
        )
        editors = set(
            self.db.scalars(
                select(SecurityEvent.user_id).where(
                    SecurityEvent.tenant_id == self.tenant_id,
                    SecurityEvent.target_id == record.id,
                    SecurityEvent.target_type == "AdminConfiguration",
                    SecurityEvent.event_type.in_({"risk_governance.config.cloned", "risk_governance.config.updated"}),
                )
            ).all()
        )
        return requires_sod and self.actor_id in editors | {record.created_by_user_id}

    def archive_configuration(
        self, configuration_id: int, expected_version: int, idempotency_key: str
    ) -> RiskConfigurationOut:
        self._lock_tenant()
        record = self.configuration(configuration_id, lock=True)
        self._assert_mutable_scope(record.content_json["scope"]["workspace_id"])
        request = {"configuration_id": configuration_id, "expected_version": expected_version}
        replay = self._replay("archived", idempotency_key, request)
        if replay is not None:
            return replay
        self._check_version(record, expected_version)
        if record.status == "archived":
            raise HTTPException(409, detail={"code": "CONFIGURATION_ALREADY_ARCHIVED"})
        record.status = "archived"
        touch_collaborative_record(record)
        return self._finish_command(record, "archived", idempotency_key, request)

    def _resolve(
        self, payload: EffectiveContextIn, *, preview: tuple[AdminConfiguration, dict[str, Any]] | None = None
    ) -> EffectiveContextOut:
        workspace = self._workspace(payload.workspace_id) if payload.workspace_id else None
        if workspace is not None:
            self._assert_scope(workspace.id)
        elif not self.context.organization_wide:
            raise HTTPException(403, detail={"code": "RISK_GOVERNANCE_WORKSPACE_CONTEXT_REQUIRED"})
        path = _workspace_path(self.db, self.tenant_id, workspace) if workspace is not None else []
        context = self._context(payload, path)
        as_of = payload.effective_date or utc_now().date()
        base = {
            "workspace_id": payload.workspace_id,
            "effective_date": as_of,
            "context": context,
            "resolution_path": [
                {"id": item.id, "code": item.code, "name": item.name, "workspace_type_code": item.workspace_type_code}
                for item in path
            ],
        }
        records = (
            [preview[0]]
            if preview is not None
            else list(
                self.db.scalars(
                    select(AdminConfiguration).where(
                        AdminConfiguration.tenant_id == self.tenant_id,
                        AdminConfiguration.kind == CONFIGURATION_KIND,
                        AdminConfiguration.status == "published",
                    )
                ).all()
            )
        )
        candidates: list[tuple[tuple[Any, ...], AdminConfiguration, dict[str, Any]]] = []
        scope_candidates = False
        path_ids = [item.id for item in path]
        for record in records:
            raw_content = preview[1] if preview is not None else record.content_json
            raw_target_id = raw_content.get("scope", {}).get("workspace_id")
            if preview is None and raw_target_id is not None and raw_target_id not in path_ids:
                continue
            content = self.validate_configuration(raw_content)
            target_id = content["scope"]["workspace_id"]
            if target_id is not None and target_id not in path_ids:
                if preview is not None:
                    raise HTTPException(422, detail={"code": "CONFIGURATION_PREVIEW_SCOPE_MISMATCH"})
                continue
            if target_id is not None and target_id != payload.workspace_id and not content["inherit_to_descendants"]:
                continue
            scope_candidates = True
            if not (
                date.fromisoformat(content["effective_from"]) <= as_of
                and (content["effective_to"] is None or as_of <= date.fromisoformat(content["effective_to"]))
            ):
                continue
            if not self._applicable(content["applicability"], context):
                continue
            specificity = sum(bool(values) and "*" not in values for values in content["applicability"].values())
            score = (
                path_ids.index(target_id) + 1 if target_id is not None else 0,
                specificity,
                content["effective_from"],
                record.revision,
                record.id,
            )
            candidates.append((score, record, content))
        if not candidates:
            return EffectiveContextOut(status="NOT_APPLICABLE" if scope_candidates else "NOT_CONFIGURED", **base)
        _score, selected, content = max(candidates, key=lambda item: item[0])
        rows = {
            key: [deepcopy(item) for item in content[key] if self._applicable(item["applicability"], context)]
            for key in ("capacity_statements", "appetite_statements", "thresholds")
        }
        warnings = [] if any(rows.values()) else ["NO_RISK_BOUNDARIES_CONFIGURED"]
        return EffectiveContextOut(
            status="AVAILABLE",
            policy=deepcopy(content),
            source={
                "configuration_id": selected.id,
                "code": selected.code,
                "revision": selected.revision,
                "version": selected.version,
                "content_hash": _hash(content),
                "status": selected.status,
                "precedence": "NEAREST_SCOPE_THEN_CONTEXT_SPECIFICITY_THEN_EFFECTIVE_DATE_THEN_REVISION",
            },
            warnings=warnings,
            **rows,
            **base,
        )

    def evaluate_threshold(self, payload: ThresholdEvaluationIn) -> ThresholdEvaluationOut:
        effective = self.effective(payload)
        threshold = next((item for item in effective.thresholds if item["code"] == payload.threshold_code), None)
        base = {"threshold_code": payload.threshold_code, "source": effective.source, "threshold": threshold}
        if threshold is None:
            return ThresholdEvaluationOut(status="NOT_EVALUABLE", warnings=["EFFECTIVE_THRESHOLD_UNAVAILABLE"], **base)
        if payload.source_value is None:
            return ThresholdEvaluationOut(status="NOT_EVALUABLE", warnings=["SOURCE_VALUE_ABSENT"], **base)
        if threshold["type"] == "CURRENCY" and (payload.currency_code or "").upper() != threshold["currency_code"]:
            return ThresholdEvaluationOut(status="NOT_EVALUABLE", warnings=["CURRENCY_MISMATCH_NO_FX"], **base)
        if threshold["unit"] and payload.unit != threshold["unit"]:
            return ThresholdEvaluationOut(status="NOT_EVALUABLE", warnings=["SOURCE_UNIT_MISMATCH"], **base)
        actual, expected, operator = payload.source_value, threshold["value"], threshold["operator"]
        boundary = False
        if threshold["type"] in NUMERIC_TYPES:
            actual = _decimal(actual)
            if actual is None:
                return ThresholdEvaluationOut(status="NOT_EVALUABLE", warnings=["SOURCE_VALUE_NOT_NUMERIC"], **base)
            if operator in {"WITHIN_RANGE", "OUTSIDE_RANGE"}:
                minimum, maximum = _decimal(expected["minimum"]), _decimal(expected["maximum"])
                within = minimum <= actual <= maximum
                boundary = actual in {minimum, maximum}
                satisfied = within if operator == "WITHIN_RANGE" else not within
            else:
                expected = _decimal(expected)
                boundary = actual == expected
                satisfied = _operator_satisfied(operator, actual, expected)
        elif threshold["type"] == "BOOLEAN" and not isinstance(actual, bool):
            return ThresholdEvaluationOut(status="NOT_EVALUABLE", warnings=["SOURCE_VALUE_NOT_BOOLEAN"], **base)
        else:
            if not isinstance(actual, str | bool | int | float):
                return ThresholdEvaluationOut(status="NOT_EVALUABLE", warnings=["SOURCE_VALUE_NOT_SCALAR"], **base)
            satisfied = _operator_satisfied(operator, actual, expected)
        return ThresholdEvaluationOut(
            status="AT_THRESHOLD" if boundary else "WITHIN_APPETITE" if satisfied else "OUTSIDE_APPETITE", **base
        )

    def validate_configuration(self, content: dict[str, Any]) -> dict[str, Any]:
        try:
            normalized = RiskGovernancePolicy.model_validate(content).model_dump(mode="json")
        except ValidationError as exc:
            raise HTTPException(422, detail={"code": "RISK_GOVERNANCE_POLICY_INVALID", "errors": str(exc)}) from exc
        target_id = normalized["scope"]["workspace_id"]
        if target_id is not None and self._workspace(target_id).workspace_type_code not in {
            "enterprise",
            "business-unit",
            "portfolio",
        }:
            raise HTTPException(422, detail={"code": "RISK_GOVERNANCE_SCOPE_INVALID"})
        for values in normalized["applicability"].values():
            if any(not value.strip() or len(value) > 120 for value in values) or len(values) != len(set(values)):
                raise HTTPException(422, detail={"code": "RISK_GOVERNANCE_APPLICABILITY_INVALID"})
        dimensions = {item["code"] for item in normalized["dimensions"] if item["active"]}
        escalation_codes = {item["code"] for item in normalized["escalation_rules"]}
        for section in ("dimensions", "capacity_statements", "appetite_statements", "thresholds", "escalation_rules"):
            codes = [item["code"] for item in normalized[section]]
            if any(not code.strip() for code in codes) or len(codes) != len(set(codes)):
                raise HTTPException(422, detail={"code": "RISK_GOVERNANCE_DUPLICATE_OR_EMPTY_CODE", "section": section})
        for section in ("capacity_statements", "appetite_statements", "thresholds"):
            for row in normalized[section]:
                if row["dimension_code"] not in dimensions:
                    raise HTTPException(422, detail={"code": "RISK_GOVERNANCE_DIMENSION_INVALID"})
                for values in row["applicability"].values():
                    if any(not value.strip() or len(value) > 120 for value in values):
                        raise HTTPException(422, detail={"code": "RISK_GOVERNANCE_APPLICABILITY_INVALID"})
        for threshold in normalized["thresholds"]:
            operator, value = threshold["operator"], threshold["value"]
            if operator not in THRESHOLD_OPERATORS:
                raise HTTPException(422, detail={"code": "RISK_GOVERNANCE_OPERATOR_INVALID"})
            if threshold["escalation_rule_code"] and threshold["escalation_rule_code"] not in escalation_codes:
                raise HTTPException(422, detail={"code": "RISK_GOVERNANCE_ESCALATION_INVALID"})
            if threshold["type"] in NUMERIC_TYPES:
                if operator in {"WITHIN_RANGE", "OUTSIDE_RANGE"}:
                    if not isinstance(value, dict) or set(value) != {"minimum", "maximum"}:
                        raise HTTPException(422, detail={"code": "RISK_GOVERNANCE_RANGE_INVALID"})
                    lower, upper = _decimal(value["minimum"]), _decimal(value["maximum"])
                    if lower is None or upper is None or lower > upper:
                        raise HTTPException(422, detail={"code": "RISK_GOVERNANCE_RANGE_INVALID"})
                    if threshold["type"] == "PERCENTAGE" and (lower < 0 or upper > 100):
                        raise HTTPException(422, detail={"code": "RISK_GOVERNANCE_PERCENTAGE_INVALID"})
                elif operator not in NUMERIC_OPERATORS | {"EQUALS", "NOT_EQUALS"} or _decimal(value) is None:
                    raise HTTPException(422, detail={"code": "RISK_GOVERNANCE_NUMERIC_THRESHOLD_INVALID"})
                elif threshold["type"] == "PERCENTAGE" and not 0 <= _decimal(value) <= 100:
                    raise HTTPException(422, detail={"code": "RISK_GOVERNANCE_PERCENTAGE_INVALID"})
                if threshold["type"] == "CURRENCY":
                    currency = threshold["currency_code"] or ""
                    if len(currency) != 3 or not currency.isalpha():
                        raise HTTPException(422, detail={"code": "RISK_GOVERNANCE_CURRENCY_REQUIRED"})
                    threshold["currency_code"] = currency.upper()
                if threshold["type"] == "DURATION" and not threshold["unit"]:
                    raise HTTPException(422, detail={"code": "RISK_GOVERNANCE_DURATION_UNIT_REQUIRED"})
            elif threshold["type"] == "BOOLEAN":
                if operator not in {"IS_TRUE", "IS_FALSE", "EQUALS", "NOT_EQUALS"} or (
                    operator in {"EQUALS", "NOT_EQUALS"} and not isinstance(value, bool)
                ):
                    raise HTTPException(422, detail={"code": "RISK_GOVERNANCE_BOOLEAN_THRESHOLD_INVALID"})
            elif operator in {"IN", "NOT_IN"}:
                if (
                    not isinstance(value, list)
                    or not value
                    or any(not isinstance(item, str | int | float | bool) for item in value)
                ):
                    raise HTTPException(422, detail={"code": "RISK_GOVERNANCE_CATEGORY_THRESHOLD_INVALID"})
            elif operator not in {"EQUALS", "NOT_EQUALS"} or not isinstance(value, str | int | float | bool):
                raise HTTPException(422, detail={"code": "RISK_GOVERNANCE_CATEGORY_THRESHOLD_INVALID"})
        return normalized

    def _context(self, payload: EffectiveContextIn, path: list[EnterpriseWorkspace]) -> dict[str, Any]:
        context: dict[str, Any] = {}
        for workspace in path:
            context.update(
                {
                    key: workspace.defaults_json[key]
                    for key in CONTEXT_FIELDS.values()
                    if workspace.defaults_json.get(key) is not None
                }
            )
            context.update(
                {
                    key: workspace.defaults_json.get("project_context", {})[key]
                    for key in CONTEXT_FIELDS.values()
                    if workspace.defaults_json.get("project_context", {}).get(key) is not None
                }
            )
        if path and path[-1].workspace_type_code == "project":
            request = self.db.scalar(
                select(ProjectCreationRequest).where(
                    ProjectCreationRequest.tenant_id == self.tenant_id,
                    ProjectCreationRequest.materialized_workspace_id == path[-1].id,
                )
            )
            if request is not None:
                context.update(
                    {
                        key: getattr(request, key)
                        for key in ("project_type", "governance_model")
                        if getattr(request, key) is not None
                    }
                )
            # Canonical Project/FEL classifiers take precedence over creation
            # request metadata; request fields are only a legacy fallback.
            project = path[-1]
            if "_project" in project.defaults_json:
                project_context = dict(project.defaults_json.get("_project") or {})
                context.update(
                    {
                        key: project_context[key]
                        for key in CONTEXT_FIELDS.values()
                        if project_context.get(key) is not None
                    }
                )
                context["project_type"] = ProjectDefinitionService._project_type(project)
                context["governance_model"] = ProjectDefinitionService._governance_model(project)
        for key in CONTEXT_FIELDS.values():
            supplied = getattr(payload, key)
            if supplied is not None:
                context[key] = supplied
        return context

    @staticmethod
    def _applicable(applicability: dict[str, Any], context: dict[str, Any]) -> bool:
        return all(
            not values or "*" in values or context.get(CONTEXT_FIELDS[key]) in values
            for key, values in applicability.items()
        )

    def _workspace(self, workspace_id: int) -> EnterpriseWorkspace:
        workspace = self.db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.id == workspace_id, EnterpriseWorkspace.tenant_id == self.tenant_id
            )
        )
        if workspace is None:
            raise HTTPException(404, detail={"code": "WORKSPACE_NOT_FOUND"})
        return workspace

    def _assert_scope(self, workspace_id: int) -> None:
        if self.context.organization_wide:
            return
        path = _workspace_path(self.db, self.tenant_id, self._workspace(workspace_id))
        if {item.id for item in path} & set(self.context.workspace_ids):
            return
        raise HTTPException(403, detail={"code": "WORKSPACE_SCOPE_DENIED"})

    def _assert_mutable_scope(self, workspace_id: int | None) -> None:
        if workspace_id is not None:
            self._assert_scope(workspace_id)
        elif not self.context.organization_wide:
            raise HTTPException(403, detail={"code": "CONFIGURATION_TENANT_SCOPE_DENIED"})

    def _visible(self, record: AdminConfiguration) -> bool:
        if self.context.organization_wide:
            return True
        target_id = record.content_json.get("scope", {}).get("workspace_id")
        if target_id is None:
            return record.status == "published"
        try:
            self._assert_scope(target_id)
            return True
        except HTTPException:
            return record.status == "published" and any(
                target_id in {item.id for item in _workspace_path(self.db, self.tenant_id, self._workspace(allowed))}
                for allowed in self.context.workspace_ids
            )

    @staticmethod
    def _assert_same_scope(prior: dict[str, Any], changed: dict[str, Any]) -> None:
        if prior.get("scope") != changed.get("scope"):
            raise HTTPException(422, detail={"code": "CONFIGURATION_SCOPE_IMMUTABLE_USE_CLONE"})

    @staticmethod
    def _check_version(record: AdminConfiguration, expected_version: int) -> None:
        if record.version != expected_version:
            raise HTTPException(412, detail={"code": "ETAG_MISMATCH", "current_version": record.version})

    def _lock_tenant(self) -> None:
        self.db.scalar(select(Tenant.id).where(Tenant.id == self.tenant_id).with_for_update())

    def _replay(self, operation: str, key: str, request: dict[str, Any]) -> RiskConfigurationOut | None:
        if not key or not 8 <= len(key) <= 160:
            raise HTTPException(400, detail={"code": "INVALID_IDEMPOTENCY_KEY"})
        events = self.db.scalars(
            select(SecurityEvent).where(
                SecurityEvent.tenant_id == self.tenant_id,
                SecurityEvent.user_id == self.actor_id,
                SecurityEvent.event_type == f"risk_governance.config.{operation}",
                SecurityEvent.metadata_json["idempotency_key"].as_string() == key,
            )
        ).all()
        event = events[0] if events else None
        if event is None:
            return None
        if event.metadata_json.get("request_hash") != _hash(request):
            raise HTTPException(409, detail={"code": "IDEMPOTENCY_KEY_REUSED"})
        result = RiskConfigurationOut.model_validate(event.metadata_json["response_snapshot"])
        self._assert_mutable_scope(result.content_json["scope"]["workspace_id"])
        return result

    def _finish_command(
        self,
        record: AdminConfiguration,
        operation: str,
        key: str,
        request: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> RiskConfigurationOut:
        self.db.flush()
        response = self.configuration_output(record)
        self._event(
            operation,
            record.id,
            {
                **(metadata or {}),
                "idempotency_key": key,
                "request_hash": _hash(request),
                "response_snapshot": response.model_dump(mode="json"),
            },
        )
        self.db.commit()
        return response

    def _event(self, operation: str, record_id: int, metadata: dict[str, Any]) -> None:
        self.db.add(
            SecurityEvent(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                event_type=f"risk_governance.config.{operation}",
                outcome="success",
                target_type="AdminConfiguration",
                target_id=record_id,
                metadata_json=deepcopy(metadata),
            )
        )
