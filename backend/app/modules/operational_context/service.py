"""Canonical O1A commands and read-only resolution. No downstream domain writes."""

import logging
from copy import deepcopy
from datetime import UTC, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.api.v1.routers.admin_configuration import _workspace_path
from app.core.time import utc_now
from app.domain.models import AdminConfiguration, EnterpriseWorkspace, Project, SecurityEvent, Tenant
from app.modules.basic_data.service import _hash, _json
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.operational_context.models import (
    OperationalContextCommand,
    OperationalProjectBinding,
    ProjectControlsPeriod,
)
from app.modules.operational_context.permissions import ACTIONS
from app.modules.post_fid_governance.models import PostFIDProjectEligibility
from app.modules.post_fid_governance.service import PostFIDGovernanceService
from app.modules.project_creation.governance import activation_authorization_status

logger = logging.getLogger(__name__)
PROFILE_KIND = "operational_profile"
MODELS = {"CAPITAL_OWNER", "CONTRACTOR_DELIVERY", "DIRECT_INTERNAL"}
DEFAULT_PROFILE = {
    "scope": {"type": "tenant", "workspace_id": None},
    "inherit_to_descendants": True,
    "applicability": {"governance_models": sorted(MODELS), "project_types": ["*"]},
    "effective_from": None,
    "effective_to": None,
    "required_operational_setup": [],
    "calendar": {
        "cadence": "weekly",
        "timezone": "America/Bogota",
        "cutoff_convention": "EXPLICIT_OFFSET_TIMESTAMP",
        "allow_parallel_active_periods": False,
        "schedule_data_date_rule": "INDEPENDENT",
    },
    "binding_policy": {"legacy_binding_required": False, "reconciliation_requires_independent_actor": True},
    "baseline_governance_profile": None,
    "change_governance_profile_reference": None,
    "progress_method_policy_reference": None,
    "forecast_policy_reference": None,
    "lookahead_default_days": 21,
    "document_evidence_requirements": [],
    "separation_of_duties": {
        "author_cannot_publish": True,
        "opener_cannot_close": False,
        "closer_cannot_publish": True,
    },
}


class OperationalContextService:
    def __init__(self, db, tenant_id, actor_id, context=None):
        self.db, self.tenant_id, self.actor_id, self.access_context = db, tenant_id, actor_id, context
        self._allowed_cache = {}
        self._permission_contexts = {}
        self._workspace_paths = {}

    @staticmethod
    def _error(status, code):
        raise HTTPException(status, detail={"code": code})

    @staticmethod
    def _version(actual, expected):
        if actual != expected:
            raise HTTPException(412, detail={"code": "ETAG_MISMATCH", "actual": actual, "expected": expected})

    def _project(self, workspace_id):
        row = self.db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.tenant_id == self.tenant_id, EnterpriseWorkspace.id == workspace_id
            )
        )
        if row is None:
            self._error(404, "PROJECT_WORKSPACE_NOT_FOUND")
        if row.workspace_type_code.lower() != "project":
            self._error(422, "PROJECT_WORKSPACE_REQUIRED")
        self._scope(row, self.access_context)
        return row

    def _scope(self, workspace, context):
        if workspace.id not in self._workspace_paths:
            self._workspace_paths[workspace.id] = {w.id for w in _workspace_path(self.db, self.tenant_id, workspace)}
        if (
            context is not None
            and not context.organization_wide
            and not (self._workspace_paths[workspace.id] & set(context.workspace_ids))
        ):
            logger.warning(
                "operational.context.denied",
                extra={
                    "tenant_id": self.tenant_id,
                    "workspace_id": workspace.id,
                    "reason_code": "OPERATIONAL_PROJECT_CONTEXT_UNAUTHORIZED",
                },
            )
            self._error(403, "OPERATIONAL_PROJECT_CONTEXT_UNAUTHORIZED")

    def _permission(self, action, workspace=None):
        if self.access_context is None:  # Trusted service use only; HTTP always supplies permission context.
            return
        if action not in self._permission_contexts:
            self._permission_contexts[action] = require_enterprise_permission(
                self.db, self.tenant_id, self.actor_id, f"operational_context.{action}", bootstrap=False
            )
        access = self._permission_contexts[action]
        if action.startswith("admin.") and not access.organization_wide:
            self._error(403, "OPERATIONAL_ADMIN_ORGANIZATION_SCOPE_REQUIRED")
        if workspace is not None:
            self._scope(workspace, access)

    def allowed_actions(self, workspace=None):
        cache_key = workspace.id if workspace else None
        if cache_key in self._allowed_cache:
            return self._allowed_cache[cache_key]
        result = []
        for action in ACTIONS:
            try:
                self._permission(action, workspace)
                result.append(action)
            except HTTPException as error:
                if error.status_code != 403:
                    raise
        self._allowed_cache[cache_key] = result
        return result

    def options(self):
        rows = self.db.scalars(
            select(EnterpriseWorkspace)
            .where(
                EnterpriseWorkspace.tenant_id == self.tenant_id, EnterpriseWorkspace.workspace_type_code == "project"
            )
            .order_by(EnterpriseWorkspace.name)
        )
        result = []
        for row in rows:
            try:
                self._scope(row, self.access_context)
            except HTTPException:
                continue
            result.append(
                {
                    k: getattr(row, k)
                    for k in ("id", "name", "code", "record_code", "external_key", "workspace_type_code")
                }
            )
        return {"projects": result, "allowed_actions": self.allowed_actions()}

    def _latest_binding(self, workspace_id):
        return self.db.scalar(
            select(OperationalProjectBinding)
            .where(
                OperationalProjectBinding.tenant_id == self.tenant_id,
                OperationalProjectBinding.project_workspace_id == workspace_id,
            )
            .order_by(OperationalProjectBinding.revision.desc())
            .limit(1)
            .execution_options(populate_existing=True)
        )

    @staticmethod
    def _binding_out(row):
        return _json(
            {
                k: getattr(row, k)
                for k in (
                    "id",
                    "project_workspace_id",
                    "legacy_project_id",
                    "status",
                    "version",
                    "revision",
                    "source",
                    "reason",
                    "created_by",
                    "validated_by",
                    "created_at",
                    "effective_from",
                    "effective_to",
                )
            }
        )

    def binding(self, workspace_id):
        self._project(workspace_id)
        rows = self.db.scalars(
            select(OperationalProjectBinding)
            .where(
                OperationalProjectBinding.tenant_id == self.tenant_id,
                OperationalProjectBinding.project_workspace_id == workspace_id,
            )
            .order_by(OperationalProjectBinding.revision.desc())
        ).all()
        current = rows[0] if rows else None
        return {
            "state": current.status if current else "MISSING",
            "version": current.version if current else 0,
            "binding": self._binding_out(current) if current else None,
            "history": [self._binding_out(r) for r in rows],
        }

    def authorization(self, workspace_id):
        project = self._project(workspace_id)
        metadata = dict((project.defaults_json or {}).get("_project", {}))
        model = metadata.get("governance_model")
        snapshot = metadata.get("source_snapshot") or {}
        blockers, commitments, warnings = [], [], []
        source, reference, revision = None, None, None
        strategic_handoff = None
        if project.status.lower() != "active":
            blockers.append("OPERATIONAL_PROJECT_NOT_ACTIVE")
        if model == "CAPITAL_OWNER":
            latest = self.db.scalar(
                select(PostFIDProjectEligibility)
                .where(
                    PostFIDProjectEligibility.tenant_id == self.tenant_id,
                    PostFIDProjectEligibility.project_workspace_id == workspace_id,
                )
                .order_by(PostFIDProjectEligibility.evaluated_at.desc(), PostFIDProjectEligibility.id.desc())
                .limit(1)
            )
            if latest is None:
                blockers.append("CAPITAL_OWNER_CURRENT_INVESTMENT_AUTHORIZATION_REQUIRED")
            else:
                service = PostFIDGovernanceService(self.db, self.tenant_id, self.actor_id)
                try:
                    decision = service._decision(latest.investment_decision_id)
                    service._project_in_scope(decision, workspace_id)
                    config = service._published_configuration()
                    applicable, current, source_blockers, source_warnings = service._decision_validity(decision, config)
                    blockers.extend(source_blockers)
                    warnings.extend(source_warnings)
                    if not applicable or not current:
                        blockers.append("CAPITAL_OWNER_INVESTMENT_AUTHORIZATION_INVALID")
                    if (
                        not latest.source_current
                        or latest.fid_decision_hash != decision.decision_hash
                        or latest.condition_snapshot_hash != _hash(decision.conditions_json or [])
                        or latest.configuration_hash != config.content_hash
                    ):
                        blockers.append("POST_FID_SOURCE_STALE")
                    if (
                        latest.eligibility_status in {"STALE", "POST_FID_PROJECT_GOVERNANCE_BLOCKED", "NOT_APPLICABLE"}
                        or latest.blockers_json
                    ):
                        blockers.append("POST_FID_OPERATIONAL_HANDOFF_BLOCKED")
                    satisfied = set(
                        config.content_json.get("condition_resolution_policy", {}).get(
                            "satisfied_statuses", ["SATISFIED", "CLOSED", "RESOLVED", "WAIVED"]
                        )
                    )
                    unresolved = [
                        c
                        for c in decision.conditions_json or []
                        if str(c.get("status", "OPEN")).upper() not in satisfied
                    ]
                    blockers.extend(
                        f"POST_FID_ACTIVATION_CONDITION:{c.get('code') or c.get('id') or i}"
                        for i, c in enumerate(unresolved)
                        if c.get("blocking_for_activation")
                    )
                    commitments = [deepcopy(c) for c in unresolved if c.get("blocking_for_commitment")]
                    source, reference, revision = "GATE07K_FID_AND_GATE07L", str(decision.id), decision.decision_hash
                    strategic_handoff = {
                        "investment_decision_id": decision.id,
                        "decision_number": decision.decision_number,
                        "decision_hash": decision.decision_hash,
                        "post_fid_eligibility_id": latest.id,
                        "post_fid_status": latest.eligibility_status,
                        "post_fid_round": latest.eligibility_round,
                        "post_fid_source_current": latest.source_current,
                        "authorized_capital_constraint": {
                            "amount": str(decision.authorized_amount)
                            if decision.authorized_amount is not None
                            else None,
                            "currency": decision.authorized_currency,
                        },
                        "source_configuration_id": latest.configuration_id,
                        "source_configuration_hash": latest.configuration_hash,
                        "source_authority": "READ_ONLY_STRATEGIC_REFERENCES",
                    }
                except HTTPException:
                    blockers.append("CAPITAL_OWNER_INVESTMENT_AUTHORIZATION_UNAVAILABLE")
        elif model == "CONTRACTOR_DELIVERY":
            source, reference = "CONTRACT_AWARD_OR_NOTICE_TO_PROCEED", snapshot.get("contract_number")
            if not all(
                snapshot.get(k) for k in ("client", "contract_number", "contractual_scope")
            ) or not activation_authorization_status(model, snapshot):
                blockers.append("CONTRACTOR_DELIVERY_AUTHORIZATION_REQUIRED")
            revision = _hash(snapshot)
        elif model == "DIRECT_INTERNAL":
            source, reference = "INTERNAL_SPONSOR_AUTHORIZATION", snapshot.get("authorization_reference")
            if not all(
                snapshot.get(k) for k in ("authorization_reference", "sponsor")
            ) or not activation_authorization_status(model, snapshot):
                blockers.append("DIRECT_INTERNAL_AUTHORIZATION_REQUIRED")
            revision = _hash(snapshot)
        else:
            blockers.append("PROJECT_GOVERNANCE_MODEL_REQUIRED")
        if model in {"CONTRACTOR_DELIVERY", "DIRECT_INTERNAL"}:
            effective_value = snapshot.get("authorization_effective_date") or snapshot.get("effective_date")
            if model == "CONTRACTOR_DELIVERY" and not snapshot.get("mobilization_authorized"):
                effective_value = effective_value or snapshot.get("notice_to_proceed_date")
            expiry_value = snapshot.get("authorization_valid_until")
            try:
                effective = self._instant(effective_value)
                expiry = self._instant(expiry_value)
                if effective and effective > utc_now():
                    blockers.append("OPERATIONAL_AUTHORIZATION_NOT_YET_EFFECTIVE")
                if expiry and expiry <= utc_now():
                    blockers.append("OPERATIONAL_AUTHORIZATION_EXPIRED")
            except (ValueError, TypeError):
                blockers.append("OPERATIONAL_AUTHORIZATION_DATE_INVALID")
        result = {
            "authorized_for_operational_context": not blockers,
            "route": model,
            "authority_source": source,
            "authority_reference": reference,
            "as_of": utc_now().replace(tzinfo=UTC).isoformat(),
            "effective_date": snapshot.get("authorization_effective_date")
            or snapshot.get("effective_date")
            or snapshot.get("notice_to_proceed_date"),
            "scope_context": {
                "project_workspace_id": workspace_id,
                "source_scope": snapshot.get("contractual_scope")
                or snapshot.get("basic_scope")
                or snapshot.get("authorization_scope"),
            },
            "blocking_conditions": sorted(set(blockers)),
            "commitment_conditions": commitments,
            "warnings": sorted(
                set(warnings + (["ACTIVE_IS_NOT_COMMITMENT_AUTHORITY"] if project.status.lower() == "active" else []))
            ),
            "source_hash": revision,
            "commitment_authorized": False,
            "strategic_handoff": strategic_handoff,
        }
        logger.info(
            "operational.authorization.resolved",
            extra={
                "tenant_id": self.tenant_id,
                "workspace_id": workspace_id,
                "route": model,
                "reason_codes": result["blocking_conditions"],
            },
        )
        return result

    def _effective_profile(self, project, as_of=None):
        now = as_of or utc_now()
        metadata = (project.defaults_json or {}).get("_project", {})
        path = [w.id for w in _workspace_path(self.db, self.tenant_id, project)]
        candidates = []
        for row in self.db.scalars(
            select(AdminConfiguration).where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == PROFILE_KIND,
                AdminConfiguration.status == "published",
            )
        ):
            content = row.content_json or {}
            start, end = self._instant(content.get("effective_from")), self._instant(content.get("effective_to"))
            if start and now < start or end and now >= end:
                continue
            applicability = content.get("applicability", {})
            if any(
                values
                and "*" not in values
                and str(metadata.get(key, "")).upper() not in {str(v).upper() for v in values}
                for key, values in (
                    ("governance_model", applicability.get("governance_models", [])),
                    ("project_type", applicability.get("project_types", [])),
                )
            ):
                continue
            scope = content.get("scope", {})
            target = scope.get("workspace_id")
            if target is not None and (
                target not in path or target != project.id and not content.get("inherit_to_descendants", True)
            ):
                continue
            candidates.append(
                (path.index(target) + 1 if target in path else 0, start or datetime.min, row.revision, row)
            )
        if not candidates:
            return None
        candidates.sort(key=lambda value: (value[0], value[1], value[2]), reverse=True)
        best = candidates[0]
        if any(v[:2] == best[:2] and v[3].code != best[3].code for v in candidates[1:]):
            self._error(409, "OPERATIONAL_PROFILE_AMBIGUOUS")
        return best[3]

    @staticmethod
    def _instant(value):
        if not value:
            return None
        instant = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return instant.astimezone(UTC).replace(tzinfo=None) if instant.tzinfo else instant

    def context(self, workspace_id):
        project = self._project(workspace_id)
        metadata = (project.defaults_json or {}).get("_project", {})
        binding = self.binding(workspace_id)
        profile = self._effective_profile(project)
        authorization = self.authorization(workspace_id)
        blockers = list(authorization["blocking_conditions"])
        if profile is None:
            blockers.append("PUBLISHED_OPERATIONAL_PROFILE_REQUIRED")
        if (
            profile
            and profile.content_json.get("binding_policy", {}).get("legacy_binding_required")
            and binding["state"] != "ACTIVE"
        ):
            blockers.append("OPERATIONAL_PROJECT_BINDING_REQUIRED")
        if profile:
            setup = metadata.get("operational_setup", {})
            blockers.extend(
                f"REQUIRED_OPERATIONAL_SETUP:{key}"
                for key in profile.content_json.get("required_operational_setup", [])
                if not setup.get(key)
            )
        current = self.db.scalar(
            select(ProjectControlsPeriod)
            .where(
                ProjectControlsPeriod.tenant_id == self.tenant_id,
                ProjectControlsPeriod.project_workspace_id == workspace_id,
                ProjectControlsPeriod.status.in_(["OPEN", "REVIEW"]),
            )
            .order_by(ProjectControlsPeriod.id.desc())
            .limit(1)
        )
        result = {
            "tenant_id": self.tenant_id,
            "project_workspace_id": project.id,
            "name": project.name,
            "project_workspace_external_key": project.external_key,
            "project_workspace_record_code": project.record_code,
            "project_workspace_status": project.status,
            "governance_model": metadata.get("governance_model"),
            "project_type": metadata.get("project_type"),
            "authorization_route": authorization["route"],
            "activation_state": project.status.upper(),
            "legacy_project_id": binding["binding"]["legacy_project_id"] if binding["state"] == "ACTIVE" else None,
            "binding_state": binding["state"],
            "binding_version": binding["version"],
            "operational_profile": self._profile_out(profile) if profile else None,
            "effective_policy_revision": profile.revision if profile else None,
            "current_reporting_period": self._period_out(current) if current else None,
            "authorization": authorization,
            "blocking_conditions": sorted(set(blockers)),
            "warnings": authorization["warnings"],
            "allowed_actions": self.allowed_actions(project),
            "role_context": sorted(self.access_context.role_codes) if self.access_context else ["TRUSTED_SERVICE"],
        }
        logger.info(
            "operational.context.resolved",
            extra={
                "tenant_id": self.tenant_id,
                "workspace_id": workspace_id,
                "binding_state": binding["state"],
                "reason_codes": result["blocking_conditions"],
            },
        )
        return result

    def _operable(self, workspace_id):
        project = self._project(workspace_id)
        decision = self.authorization(workspace_id)
        if not decision["authorized_for_operational_context"]:
            self._error(409, decision["blocking_conditions"][0])
        return project

    def _policy_ready(self, project, profile):
        if profile is None:
            self._error(409, "PUBLISHED_OPERATIONAL_PROFILE_REQUIRED")
        if profile.content_json.get("binding_policy", {}).get("legacy_binding_required", False):
            current = self._latest_binding(project.id)
            if current is None or current.status != "ACTIVE":
                self._error(409, "OPERATIONAL_PROJECT_BINDING_REQUIRED")
        metadata = (project.defaults_json or {}).get("_project", {})
        setup = metadata.get("operational_setup", {})
        for key in profile.content_json.get("required_operational_setup", []):
            if not setup.get(key):
                self._error(409, f"REQUIRED_OPERATIONAL_SETUP:{key}")

    def create_binding(self, workspace_id, payload, expected, key, *, reconcile=False):
        project = self._project(workspace_id)
        self._permission("binding.manage", project)

        def apply():
            self._operable(workspace_id)
            old = self._latest_binding(workspace_id)
            self._version(old.version if old else 0, expected)
            if payload.expected_binding_version is not None:
                self._version(expected, payload.expected_binding_version)
            profile = self._effective_profile(project)
            if old and not reconcile:
                self._error(409, "OPERATIONAL_PROJECT_BINDING_ALREADY_EXISTS")
            if (
                old
                and (profile.content_json if profile else DEFAULT_PROFILE)
                .get("binding_policy", {})
                .get("reconciliation_requires_independent_actor", True)
                and old.created_by == self.actor_id
            ):
                self._error(403, "OPERATIONAL_BINDING_RECONCILIATION_SOD")
            legacy_id = payload.legacy_project_id
            if reconcile and payload.source == "VERIFIED_EXISTING_RELATIONSHIP":
                forward = (project.defaults_json or {}).get("_project", {}).get("operational_project_id")
                reverse = self.db.scalars(
                    select(Project.id).where(
                        Project.tenant_id == self.tenant_id,
                        Project.configuration["enterprise_workspace_id"].as_integer() == workspace_id,
                    )
                ).all()
                candidates = set(reverse) | ({forward} if isinstance(forward, int) else set())
                if len(candidates) > 1:
                    self._error(409, "OPERATIONAL_PROJECT_BINDING_AMBIGUOUS")
                if not candidates:
                    self._error(409, "OPERATIONAL_PROJECT_BINDING_REQUIRED")
                candidate = next(iter(candidates))
                if legacy_id is not None and legacy_id != candidate:
                    self._error(409, "OPERATIONAL_PROJECT_BINDING_INVALID")
                legacy_id = candidate
            if legacy_id is not None:
                legacy = self.db.scalar(
                    select(Project).where(Project.tenant_id == self.tenant_id, Project.id == legacy_id)
                )
                if legacy is None:
                    self._error(404, "OPERATIONAL_PROJECT_BINDING_INVALID")
                if legacy.status.lower() in {"superseded", "revoked", "deleted", "archived"}:
                    self._error(409, "OPERATIONAL_PROJECT_BINDING_INVALID")
                reverse = (legacy.configuration or {}).get("enterprise_workspace_id")
                if reverse not in {None, workspace_id}:
                    self._error(409, "OPERATIONAL_PROJECT_BINDING_INVALID")
                other = self.db.scalar(
                    select(OperationalProjectBinding.id).where(
                        OperationalProjectBinding.tenant_id == self.tenant_id,
                        OperationalProjectBinding.legacy_project_id == legacy_id,
                        OperationalProjectBinding.status == "ACTIVE",
                        OperationalProjectBinding.project_workspace_id != workspace_id,
                    )
                )
                if other:
                    self._error(409, "OPERATIONAL_PROJECT_BINDING_LEGACY_ALREADY_LINKED")
            if old and old.status in {"ACTIVE", "NO_LEGACY_BINDING_REQUIRED"}:
                old.status, old.effective_to = "SUPERSEDED", utc_now()
                self.db.flush()
                self._event("binding.superseded", old.id, {"revision": old.revision})
            row = OperationalProjectBinding(
                tenant_id=self.tenant_id,
                project_workspace_id=workspace_id,
                legacy_project_id=legacy_id,
                status="ACTIVE" if legacy_id is not None else "NO_LEGACY_BINDING_REQUIRED",
                revision=(old.revision + 1) if old else 1,
                version=(old.version + 1) if old else 1,
                source=payload.source,
                reason=payload.reason,
                created_by=self.actor_id,
                validated_by=self.actor_id,
            )
            self.db.add(row)
            self.db.flush()
            self._event(
                "binding.created",
                row.id,
                {"project_workspace_id": workspace_id, "legacy_project_id": legacy_id, "reason": payload.reason},
            )
            if legacy_id:
                self._event(
                    "binding.activated", row.id, {"project_workspace_id": workspace_id, "legacy_project_id": legacy_id}
                )
            return self._binding_out(row)

        return self._command(
            "binding.reconcile" if reconcile else "binding.create",
            key,
            {"project": workspace_id, "expected": expected, **payload.model_dump(mode="json")},
            apply,
        )

    def revoke_binding(self, workspace_id, payload, expected, key):
        project = self._project(workspace_id)
        self._permission("binding.manage", project)

        def apply():
            self._operable(workspace_id)
            row = self._latest_binding(workspace_id)
            if row is None or row.status not in {"ACTIVE", "NO_LEGACY_BINDING_REQUIRED"}:
                self._error(409, "OPERATIONAL_PROJECT_BINDING_REQUIRED")
            self._version(row.version, expected)
            profile = self._effective_profile(project)
            policy = (profile.content_json if profile else DEFAULT_PROFILE).get("binding_policy", {})
            if policy.get("reconciliation_requires_independent_actor", True) and row.created_by == self.actor_id:
                self._error(403, "OPERATIONAL_BINDING_RECONCILIATION_SOD")
            row.status, row.effective_to, row.version = "REVOKED", utc_now(), row.version + 1
            self.db.flush()
            self._event("binding.revoked", row.id, {"project_workspace_id": workspace_id, "reason": payload.reason})
            return self._binding_out(row)

        return self._command(
            "binding.revoke",
            key,
            {"project": workspace_id, "expected": expected, **payload.model_dump(mode="json")},
            apply,
        )

    def periods(self, workspace_id):
        self._project(workspace_id)
        rows = self.db.scalars(
            select(ProjectControlsPeriod)
            .where(
                ProjectControlsPeriod.tenant_id == self.tenant_id,
                ProjectControlsPeriod.project_workspace_id == workspace_id,
            )
            .order_by(
                ProjectControlsPeriod.period_end.desc(),
                ProjectControlsPeriod.revision.desc(),
                ProjectControlsPeriod.id.desc(),
            )
        ).all()
        return {"items": [self._period_out(row) for row in rows], "total": len(rows)}

    def _period_out(self, row):
        fields = (
            "id",
            "project_workspace_id",
            "period_code",
            "period_start",
            "period_end",
            "cutoff_at",
            "timezone",
            "status",
            "revision",
            "version",
            "profile_code",
            "configuration_id",
            "source_configuration_revision",
            "source_configuration_hash",
            "schedule_data_date",
            "reopen_parent_id",
            "reason",
            "notes",
            "opened_at",
            "opened_by",
            "review_started_at",
            "review_started_by",
            "closed_at",
            "closed_by",
            "published_at",
            "published_by",
            "snapshot_json",
        )
        permissions = set(self.allowed_actions(self._project(row.project_workspace_id)))
        policy = self._profile(row.configuration_id).content_json.get("separation_of_duties", {})
        available = {
            "OPEN": {"period.review"},
            "REVIEW": {"period.close"},
            "CLOSED": {"period.publish", "period.reopen"},
            "PUBLISHED": {"period.reopen"},
        }[row.status]
        if row.opened_by == self.actor_id and policy.get("opener_cannot_close", False):
            available.discard("period.close")
        if row.closed_by == self.actor_id and policy.get("closer_cannot_publish", True):
            available.discard("period.publish")
        return _json({k: getattr(row, k) for k in fields}) | {"allowed_actions": sorted(permissions & available)}

    def _period(self, workspace_id, period_id):
        row = self.db.scalar(
            select(ProjectControlsPeriod)
            .where(
                ProjectControlsPeriod.tenant_id == self.tenant_id,
                ProjectControlsPeriod.project_workspace_id == workspace_id,
                ProjectControlsPeriod.id == period_id,
            )
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if row is None:
            self._error(404, "PROJECT_CONTROLS_PERIOD_NOT_FOUND")
        return row

    def _validate_period(self, payload, profile):
        calendar = profile.content_json["calendar"]
        try:
            zone = ZoneInfo(payload.timezone)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise HTTPException(422, detail={"code": "OPERATIONAL_PERIOD_TIMEZONE_INVALID"}) from error
        if payload.timezone != calendar["timezone"]:
            self._error(422, "OPERATIONAL_PERIOD_TIMEZONE_POLICY_MISMATCH")
        if payload.cutoff_at.tzinfo is None or payload.period_end < payload.period_start:
            self._error(422, "OPERATIONAL_PERIOD_EXPLICIT_CUTOFF_REQUIRED")
        local = payload.cutoff_at.astimezone(zone)
        if local.utcoffset() != payload.cutoff_at.utcoffset():
            self._error(422, "OPERATIONAL_PERIOD_CUTOFF_OFFSET_MISMATCH")
        if local.date() < payload.period_end:
            self._error(422, "OPERATIONAL_PERIOD_CUTOFF_BEFORE_END")
        days = (payload.period_end - payload.period_start).days + 1
        cadence = calendar["cadence"]
        if (
            cadence == "weekly"
            and days != 7
            or cadence == "biweekly"
            and days != 14
            or cadence == "monthly"
            and not (
                payload.period_start.day == 1
                and payload.period_start.replace(day=1) == payload.period_end.replace(day=1)
                and (
                    payload.period_end.replace(day=1).month % 12 + 1
                    == (payload.period_end.fromordinal(payload.period_end.toordinal() + 1)).month
                )
            )
        ):
            self._error(422, "OPERATIONAL_PERIOD_CADENCE_MISMATCH")

    def _new_period(self, workspace_id, payload, profile, *, parent=None):
        self._validate_period(payload, profile)
        parallel = profile.content_json["calendar"].get("allow_parallel_active_periods", False)
        if not parallel and self.db.scalar(
            select(ProjectControlsPeriod.id).where(
                ProjectControlsPeriod.tenant_id == self.tenant_id,
                ProjectControlsPeriod.project_workspace_id == workspace_id,
                ProjectControlsPeriod.profile_code == profile.code,
                ProjectControlsPeriod.status.in_(["OPEN", "REVIEW"]),
            )
        ):
            self._error(409, "OPERATIONAL_ACTIVE_PERIOD_EXISTS")
        if not parent and self.db.scalar(
            select(ProjectControlsPeriod.id).where(
                ProjectControlsPeriod.tenant_id == self.tenant_id,
                ProjectControlsPeriod.project_workspace_id == workspace_id,
                ProjectControlsPeriod.period_code == payload.period_code,
            )
        ):
            self._error(409, "OPERATIONAL_PERIOD_CODE_EXISTS")
        revision = (
            self.db.scalar(
                select(func.max(ProjectControlsPeriod.revision)).where(
                    ProjectControlsPeriod.tenant_id == self.tenant_id,
                    ProjectControlsPeriod.project_workspace_id == workspace_id,
                    ProjectControlsPeriod.period_code == payload.period_code,
                )
            )
            or 0
        ) + 1
        row = ProjectControlsPeriod(
            tenant_id=self.tenant_id,
            project_workspace_id=workspace_id,
            period_code=payload.period_code,
            period_start=payload.period_start,
            period_end=payload.period_end,
            cutoff_at=payload.cutoff_at,
            timezone=payload.timezone,
            status="OPEN",
            revision=revision,
            version=1,
            profile_code=profile.code,
            active_slot=str(uuid4()) if parallel else "ACTIVE",
            configuration_id=profile.id,
            source_configuration_revision=profile.revision,
            source_configuration_hash=profile.content_hash,
            schedule_data_date=payload.schedule_data_date,
            reopen_parent_id=parent.id if parent else None,
            reason=payload.reason,
            notes=payload.notes,
            opened_by=self.actor_id,
        )
        self.db.add(row)
        self.db.flush()
        self._event(
            "period.reopened" if parent else "period.opened",
            row.id,
            {
                "project_workspace_id": workspace_id,
                "parent_id": parent.id if parent else None,
                "configuration_id": profile.id,
            },
        )
        return row

    def open_period(self, workspace_id, payload, key):
        project = self._project(workspace_id)
        self._permission("period.open", project)

        def apply():
            self._operable(workspace_id)
            profile = self._effective_profile(project)
            self._policy_ready(project, profile)
            return self._period_out(self._new_period(workspace_id, payload, profile))

        return self._command("period.open", key, {"project": workspace_id, **payload.model_dump(mode="json")}, apply)

    def transition_period(self, workspace_id, period_id, action, payload, expected, key):
        project = self._project(workspace_id)
        if action not in {"review", "close", "publish", "reopen"}:
            self._error(422, "OPERATIONAL_PERIOD_COMMAND_INVALID")
        self._permission(f"period.{action}", project)

        def apply():
            self._operable(workspace_id)
            row = self._period(workspace_id, period_id)
            self._version(row.version, expected)
            profile = self._profile(row.configuration_id)
            self._policy_ready(project, profile)
            policy = profile.content_json.get("separation_of_duties", {})
            if action == "reopen":
                if row.status not in {"CLOSED", "PUBLISHED"}:
                    self._error(409, "OPERATIONAL_PERIOD_TRANSITION_INVALID")
                from app.modules.operational_context.schemas import PeriodOpenIn

                # Reopen creates a successor with the original pinned policy.
                local_cutoff = row.cutoff_at.replace(tzinfo=UTC) if row.cutoff_at.tzinfo is None else row.cutoff_at
                values = PeriodOpenIn(
                    period_code=row.period_code,
                    period_start=row.period_start,
                    period_end=row.period_end,
                    cutoff_at=local_cutoff.astimezone(ZoneInfo(row.timezone)),
                    timezone=row.timezone,
                    schedule_data_date=row.schedule_data_date,
                    reason=payload.reason,
                    notes=payload.notes,
                )
                return self._period_out(self._new_period(workspace_id, values, profile, parent=row))
            required, target = {
                "review": ("OPEN", "REVIEW"),
                "close": ("REVIEW", "CLOSED"),
                "publish": ("CLOSED", "PUBLISHED"),
            }[action]
            if row.status != required:
                self._error(409, "OPERATIONAL_PERIOD_TRANSITION_INVALID")
            if (
                action == "close"
                and policy.get("opener_cannot_close", False)
                and row.opened_by == self.actor_id
                or action == "publish"
                and policy.get("closer_cannot_publish", True)
                and row.closed_by == self.actor_id
            ):
                self._error(403, "OPERATIONAL_PERIOD_SEPARATION_OF_DUTIES")
            row.status, row.version = target, row.version + 1
            stamp = {"review": "review_started", "close": "closed", "publish": "published"}[action]
            setattr(row, f"{stamp}_at", utc_now())
            setattr(row, f"{stamp}_by", self.actor_id)
            if action in {"close", "publish"}:
                row.active_slot = None
            row.reason, row.notes = payload.reason, payload.notes
            if action == "publish":
                row.snapshot_json = {
                    "publication_boundary": "PERIOD_HEADER_ONLY",
                    "project_workspace_id": workspace_id,
                    "period_code": row.period_code,
                    "period_start": row.period_start.isoformat(),
                    "period_end": row.period_end.isoformat(),
                    "revision": row.revision,
                    "configuration_id": row.configuration_id,
                    "configuration_revision": row.source_configuration_revision,
                    "configuration_hash": row.source_configuration_hash,
                    "cutoff_at": row.cutoff_at.isoformat(),
                    "timezone": row.timezone,
                    "schedule_data_date": str(row.schedule_data_date) if row.schedule_data_date else None,
                    "source_bundles": [],
                    "report_publication": False,
                }
                row.snapshot_json = row.snapshot_json | {"header_hash": _hash(row.snapshot_json)}
            self.db.flush()
            self._event(
                f"period.{stamp}",
                row.id,
                {"project_workspace_id": workspace_id, "reason": payload.reason, "version": row.version},
            )
            return self._period_out(row)

        return self._command(
            f"period.{action}",
            key,
            {"project": workspace_id, "period": period_id, "expected": expected, **payload.model_dump(mode="json")},
            apply,
        )

    @staticmethod
    def _profile_out(row):
        return _json(
            {
                k: getattr(row, k)
                for k in (
                    "id",
                    "code",
                    "name",
                    "status",
                    "revision",
                    "version",
                    "content_json",
                    "content_hash",
                    "created_by_user_id",
                    "published_at",
                )
            }
        )

    def profiles(self):
        self._permission("admin.configure")
        rows = self.db.scalars(
            select(AdminConfiguration)
            .where(AdminConfiguration.tenant_id == self.tenant_id, AdminConfiguration.kind == PROFILE_KIND)
            .order_by(AdminConfiguration.code, AdminConfiguration.revision.desc())
        ).all()
        return {
            "items": [self._profile_out(row) for row in rows],
            "default_content": deepcopy(DEFAULT_PROFILE),
            "allowed_actions": self.allowed_actions(),
        }

    def _profile(self, profile_id, *, lock=False):
        statement = select(AdminConfiguration).where(
            AdminConfiguration.tenant_id == self.tenant_id,
            AdminConfiguration.kind == PROFILE_KIND,
            AdminConfiguration.id == profile_id,
        )
        row = self.db.scalar(
            statement.with_for_update().execution_options(populate_existing=True) if lock else statement
        )
        if row is None:
            self._error(404, "OPERATIONAL_PROFILE_NOT_FOUND")
        return row

    def _validate_profile(self, content):
        try:
            if any(
                not isinstance(content.get(key, {}), dict)
                for key in ("calendar", "applicability", "scope", "binding_policy", "separation_of_duties")
            ):
                raise ValueError("policy object")
            calendar = content["calendar"]
            if calendar["cadence"] not in {"weekly", "biweekly", "monthly", "custom"}:
                raise ValueError("cadence")
            ZoneInfo(calendar["timezone"])
            if calendar.get("schedule_data_date_rule", "INDEPENDENT") != "INDEPENDENT":
                raise ValueError("data date independent")
            if not isinstance(calendar.get("allow_parallel_active_periods", False), bool):
                raise ValueError("parallel periods")
            applicability = content["applicability"]
            if (
                not isinstance(applicability["governance_models"], list)
                or not isinstance(applicability["project_types"], list)
                or any(not isinstance(value, str) or not value.strip() for value in applicability["project_types"])
                or not applicability["governance_models"]
                or set(applicability["governance_models"]) - (MODELS | {"*"})
                or not applicability["project_types"]
            ):
                raise ValueError("applicability")
            if any(not isinstance(value, bool) for value in content.get("binding_policy", {}).values()):
                raise ValueError("binding policy")
            required = content.get("required_operational_setup", [])
            if not isinstance(required, list) or any(
                not isinstance(value, str) or not value.strip() for value in required
            ):
                raise ValueError("required setup")
            start, end = self._instant(content.get("effective_from")), self._instant(content.get("effective_to"))
            if end and start and end <= start:
                raise ValueError("effective window")
            scope = content.get("scope", {})
            scope_type = scope.get("type", "tenant")
            target = scope.get("workspace_id")
            if (
                scope_type == "workspace"
                and (not isinstance(target, int) or isinstance(target, bool) or target < 1)
                or scope_type == "tenant"
                and target is not None
            ):
                raise ValueError("scope identity")
            if scope.get("workspace_id") is not None:
                row = self.db.scalar(
                    select(EnterpriseWorkspace).where(
                        EnterpriseWorkspace.tenant_id == self.tenant_id, EnterpriseWorkspace.id == scope["workspace_id"]
                    )
                )
                if row is None:
                    raise ValueError("scope")
            if scope.get("type", "tenant") not in {"tenant", "workspace"}:
                raise ValueError("scope type")
            if not isinstance(content.get("inherit_to_descendants", True), bool):
                raise ValueError("inheritance")
            for value in content.get("separation_of_duties", {}).values():
                if not isinstance(value, bool):
                    raise ValueError("SoD")
        except (KeyError, TypeError, ValueError, ZoneInfoNotFoundError) as error:
            raise HTTPException(422, detail={"code": "OPERATIONAL_PROFILE_INVALID"}) from error

    def create_profile(self, payload, key):
        self._permission("admin.configure")

        def apply():
            self._validate_profile(payload.content_json)
            if self.db.scalar(
                select(AdminConfiguration.id).where(
                    AdminConfiguration.tenant_id == self.tenant_id,
                    AdminConfiguration.kind == PROFILE_KIND,
                    AdminConfiguration.code == payload.code,
                )
            ):
                self._error(409, "OPERATIONAL_PROFILE_CODE_EXISTS")
            row = AdminConfiguration(
                tenant_id=self.tenant_id,
                kind=PROFILE_KIND,
                code=payload.code,
                name=payload.name,
                status="draft",
                revision=1,
                version=1,
                content_json=deepcopy(payload.content_json),
                content_hash=_hash(payload.content_json),
                created_by_user_id=self.actor_id,
            )
            self.db.add(row)
            self.db.flush()
            self._event("profile.created", row.id, {"revision": row.revision})
            return self._profile_out(row)

        return self._command("profile.create", key, payload.model_dump(mode="json"), apply)

    def update_profile(self, profile_id, payload, expected, key):
        self._permission("admin.configure")

        def apply():
            row = self._profile(profile_id, lock=True)
            self._version(row.version, expected)
            if row.status != "draft":
                self._error(409, "PUBLISHED_OPERATIONAL_PROFILE_IMMUTABLE")
            self._validate_profile(payload.content_json)
            row.name, row.content_json, row.content_hash, row.version, row.updated_at = (
                payload.name,
                deepcopy(payload.content_json),
                _hash(payload.content_json),
                row.version + 1,
                utc_now(),
            )
            self.db.flush()
            self._event(
                "profile.updated",
                row.id,
                {"revision": row.revision, "version": row.version, "content_hash": row.content_hash},
            )
            return self._profile_out(row)

        return self._command(
            "profile.update", key, {"id": profile_id, "expected": expected, **payload.model_dump(mode="json")}, apply
        )

    def publish_profile(self, profile_id, payload, expected, key):
        self._permission("admin.publish")

        def apply():
            row = self._profile(profile_id, lock=True)
            self._version(row.version, expected)
            if row.status != "draft":
                self._error(409, "PUBLISHED_OPERATIONAL_PROFILE_IMMUTABLE")
            self._validate_profile(row.content_json)
            if row.content_json.get("separation_of_duties", {}).get("author_cannot_publish", True):
                # The creator is not necessarily the current policy author.
                # Resolve the current-version editor from immutable server-side
                # receipts, never a client-editable policy JSON attribution.
                editor = row.created_by_user_id
                if row.version > 1:
                    receipt = self.db.scalar(
                        select(OperationalContextCommand).where(
                            OperationalContextCommand.tenant_id == self.tenant_id,
                            OperationalContextCommand.command_type == "profile.update",
                            OperationalContextCommand.result_json["id"].as_integer() == row.id,
                            OperationalContextCommand.result_json["version"].as_integer() == row.version,
                        )
                    )
                    if receipt is None or receipt.result_json.get("content_hash") != row.content_hash:
                        self._error(409, "OPERATIONAL_PROFILE_EDITOR_PROVENANCE_REQUIRED")
                    editor = receipt.actor_id
                if self.actor_id in {row.created_by_user_id, editor}:
                    self._error(403, "OPERATIONAL_PROFILE_PUBLICATION_SOD")
            row.status, row.published_at, row.version = "published", utc_now(), row.version + 1
            self.db.flush()
            self._event(
                "profile.published",
                row.id,
                {"revision": row.revision, "reason": payload.reason, "hash": row.content_hash},
            )
            return self._profile_out(row)

        return self._command(
            "profile.publish", key, {"id": profile_id, "expected": expected, **payload.model_dump(mode="json")}, apply
        )

    def successor_profile(self, profile_id, payload, expected, key):
        self._permission("admin.configure")

        def apply():
            old = self._profile(profile_id, lock=True)
            self._version(old.version, expected)
            if old.status != "published":
                self._error(409, "PUBLISHED_OPERATIONAL_PROFILE_REQUIRED")
            revision = (
                self.db.scalar(
                    select(func.max(AdminConfiguration.revision)).where(
                        AdminConfiguration.tenant_id == self.tenant_id,
                        AdminConfiguration.kind == PROFILE_KIND,
                        AdminConfiguration.code == old.code,
                    )
                )
                or 0
            ) + 1
            row = AdminConfiguration(
                tenant_id=self.tenant_id,
                kind=PROFILE_KIND,
                code=old.code,
                name=old.name,
                description=payload.reason,
                status="draft",
                revision=revision,
                version=1,
                content_json=deepcopy(old.content_json),
                content_hash=old.content_hash,
                created_by_user_id=self.actor_id,
            )
            self.db.add(row)
            self.db.flush()
            self._event("profile.successor_created", row.id, {"predecessor_id": old.id})
            return self._profile_out(row)

        return self._command(
            "profile.successor", key, {"id": profile_id, "expected": expected, **payload.model_dump(mode="json")}, apply
        )

    def _event(self, action, target_id, metadata, *, outcome="success"):
        self.db.add(
            SecurityEvent(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                event_type=f"operational.{action}",
                outcome=outcome,
                target_type="OperationalContext",
                target_id=target_id,
                metadata_json=deepcopy(metadata),
            )
        )
        logger.info(
            f"operational.{action}",
            extra={"tenant_id": self.tenant_id, "target_id": target_id, "reason_codes": [action]},
        )

    def _command(self, command, key, request, apply):
        if not key or not 8 <= len(key) <= 160:
            self._error(422, "IDEMPOTENCY_KEY_REQUIRED")
        self.db.scalar(select(Tenant).where(Tenant.id == self.tenant_id).with_for_update())
        request_hash = _hash({"actor": self.actor_id, "request": request})
        old = self.db.scalar(
            select(OperationalContextCommand).where(
                OperationalContextCommand.tenant_id == self.tenant_id, OperationalContextCommand.idempotency_key == key
            )
        )
        if old:
            if old.command_type != command or old.request_hash != request_hash:
                self._error(409, "IDEMPOTENCY_KEY_REUSED")
            return deepcopy(old.result_json)
        try:
            result = _json(apply())
            self.db.add(
                OperationalContextCommand(
                    tenant_id=self.tenant_id,
                    idempotency_key=key,
                    command_type=command,
                    request_hash=request_hash,
                    result_json=deepcopy(result),
                    actor_id=self.actor_id,
                )
            )
            self.db.commit()
            return result
        except IntegrityError as error:
            self.db.rollback()
            raise HTTPException(409, detail={"code": "OPERATIONAL_CONCURRENT_CONFLICT"}) from error
        except HTTPException as error:
            self.db.rollback()
            code = error.detail.get("code") if isinstance(error.detail, dict) else "OPERATIONAL_COMMAND_DENIED"
            self._event(
                "binding.reconciliation_failed" if command.startswith("binding.") else "context.denied",
                request.get("project"),
                {"reason_code": code, "command": command},
                outcome="denied",
            )
            self.db.commit()
            raise
        except Exception:
            self.db.rollback()
            raise


def guard_legacy_operational_write(db, tenant_id, actor_id, legacy_project_id):
    """Compatibility adapter: resolve canonical scope before a material legacy write."""
    db.scalar(select(Tenant).where(Tenant.id == tenant_id).with_for_update())
    rows = db.scalars(
        select(OperationalProjectBinding)
        .where(
            OperationalProjectBinding.tenant_id == tenant_id,
            OperationalProjectBinding.legacy_project_id == legacy_project_id,
            OperationalProjectBinding.status == "ACTIVE",
        )
        .limit(2)
        .with_for_update()
    ).all()
    if len(rows) != 1:
        OperationalContextService._error(
            409, "OPERATIONAL_PROJECT_BINDING_AMBIGUOUS" if rows else "OPERATIONAL_PROJECT_BINDING_REQUIRED"
        )
    context = require_enterprise_permission(
        db, tenant_id, actor_id, "operational_context.legacy.execute", bootstrap=False
    )
    service = OperationalContextService(db, tenant_id, actor_id, context)
    service._operable(rows[0].project_workspace_id)
    resolved = service.context(rows[0].project_workspace_id)
    if resolved["blocking_conditions"]:
        service._error(409, resolved["blocking_conditions"][0])
    return resolved
