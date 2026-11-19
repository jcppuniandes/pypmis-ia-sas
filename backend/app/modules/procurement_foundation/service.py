"""Canonical procurement composition and scoped O1A command ledger."""

import re
from copy import deepcopy

from fastapi import HTTPException
from sqlalchemy import select

from app.core.time import utc_now
from app.domain.models import SecurityEvent, UserAccount, WorkspaceModuleSetting
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.procurement_foundation.integration import ProcurementIntegrationMixin
from app.modules.procurement_foundation.materials import MaterialsMixin
from app.modules.procurement_foundation.permissions import ACTIONS, require_procurement_schema
from app.modules.procurement_foundation.policy import CODE
from app.modules.procurement_foundation.profiles import ProcurementProfilesMixin
from app.modules.procurement_foundation.sourcing import ProcurementSourcingMixin
from app.modules.procurement_foundation.sourcing_models import ProcurementHistory
from app.modules.scope_foundation.service import ScopeFoundationService


class ProcurementFoundationService(
    ProcurementIntegrationMixin,
    MaterialsMixin,
    ProcurementSourcingMixin,
    ProcurementProfilesMixin,
    ScopeFoundationService,
):
    def _require_schema(self):
        if not self.__dict__.get("_procurement_schema_confirmed"):
            require_procurement_schema(self.db)
            self._procurement_schema_confirmed = True

    def _project(self, workspace_id):
        self._require_schema()
        project = super()._project(workspace_id)
        if project.status.lower() != "active":
            self._error(409, "PROCUREMENT_ACTIVE_PROJECT_REQUIRED")
        cache = self.__dict__.setdefault("_procurement_enabled", {})
        if workspace_id not in cache:
            keys = {"procurement", "procurement-manager"}
            defaults = dict(project.defaults_json or {})
            metadata = {**defaults, **dict(defaults.get("_enterprise") or {})}
            settings = dict(
                self.db.execute(
                    select(WorkspaceModuleSetting.module_key, WorkspaceModuleSetting.enabled).where(
                        WorkspaceModuleSetting.tenant_id == self.tenant_id,
                        WorkspaceModuleSetting.workspace_id == workspace_id,
                        WorkspaceModuleSetting.module_key.in_(keys),
                    )
                ).all()
            )
            cache[workspace_id] = not any(value is False for value in settings.values()) and bool(
                keys & set(metadata.get("enabled_modules") or []) or any(settings.values())
            )
        if not cache[workspace_id]:
            self._error(409, "PROCUREMENT_MODULE_NOT_ENABLED")
        return project

    def _permission(self, action, workspace=None):
        if self.access_context is None:
            return  # Trusted composition. Every HTTP route installs a permission context.
        if action not in self._permission_contexts:
            self._permission_contexts[action] = require_enterprise_permission(
                self.db,
                self.tenant_id,
                self.actor_id,
                f"procurement.{action}",
                bootstrap=False,
            )
        access = self._permission_contexts[action]
        if action.startswith(("admin.", "vendor.")) and not access.organization_wide:
            self._error(403, "PROCUREMENT_ORGANIZATION_SCOPE_REQUIRED")
        if workspace is not None:
            self._scope(workspace, access)

    def _restrict_profile(self, action, profile):
        if self.access_context is None or profile is None:
            return
        roles = {
            role for role, actions in profile.content_json.get("permission_profiles", {}).items() if action in actions
        }
        if roles and not roles.intersection(self._permission_contexts[action].role_codes):
            self._error(403, "PROCUREMENT_PROFILE_DUTY_DENIED")

    def allowed_actions(self, workspace=None):
        profile = self._procurement_profile(workspace) if workspace is not None else None
        available = []
        for action in ACTIONS:
            try:
                self._permission(action, workspace)
                self._restrict_profile(action, profile)
                available.append(action)
            except HTTPException as exc:
                if exc.status_code != 403:
                    raise
        return available

    def _read_project(self, workspace):
        project = self._project(workspace)
        self._permission("read", project)
        self._restrict_profile("read", self._procurement_profile(project))
        return project

    def _ready(self, workspace, action):
        project = self._project(workspace)
        self._permission(action, project)
        operational = self._operational()
        operational._operable(workspace)
        operational._policy_ready(project, operational._effective_profile(project))
        profile = self._procurement_profile(project)
        if profile is None:
            self._error(409, "PROCUREMENT_PUBLISHED_PROFILE_REQUIRED")
        self._restrict_profile(action, profile)
        return project, profile

    def configuration(self, workspace):
        project = self._read_project(workspace)
        profile = self._procurement_profile(project)
        return {
            "profile": self._profile_out(profile) if profile else None,
            "allowed_actions": self.allowed_actions(project),
        }

    def _scoped(self, model, workspace):
        return select(model).where(model.tenant_id == self.tenant_id, model.project_workspace_id == workspace)

    def _get(self, model, workspace_id, record_id, *, lock=False):
        query = self._scoped(model, workspace_id).where(model.id == record_id)
        row = self.db.scalar(query.with_for_update().execution_options(populate_existing=True) if lock else query)
        if row is None:
            self._error(404, "PROCUREMENT_RECORD_NOT_FOUND")
        return row

    def _new(self, model, workspace, **values):
        base = self._base(workspace)
        if hasattr(model, "updated_by"):
            base["updated_by"] = self.actor_id
        row = model(**(base | values))
        self.db.add(row)
        self.db.flush()
        return row

    def _code(self, value):
        value = value.strip().upper()
        if not re.fullmatch(CODE, value) or len(value) > 120:
            self._error(422, "PROCUREMENT_CODE_INVALID")
        return value

    def _actor(self, identity):
        identity = identity or self.actor_id
        if (
            self.db.scalar(
                select(UserAccount.id).where(
                    UserAccount.tenant_id == self.tenant_id,
                    UserAccount.id == identity,
                    UserAccount.status == "active",
                )
            )
            is None
        ):
            self._error(404, "PROCUREMENT_ACTOR_NOT_FOUND")
        return identity

    def _event(self, action, identity, metadata, *, outcome="success"):
        self.db.add(
            SecurityEvent(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                event_type=f"procurement.{action}",
                outcome=outcome,
                target_type="ProcurementFoundation",
                target_id=identity,
                metadata_json=deepcopy(metadata),
            )
        )

    def _record(self, row, event, reason, *, changed=False):
        previous = row.version if changed else None
        if changed:
            row.version += 1
            if hasattr(row, "updated_by"):
                row.updated_by, row.updated_at = self.actor_id, utc_now()
        self.db.flush()
        snapshot = self._out(row)
        self.db.add(
            ProcurementHistory(
                **self._base(row.project_workspace_id),
                entity_type=type(row).__name__,
                entity_id=row.id,
                entity_version=row.version,
                previous_version=previous,
                event_type=event,
                snapshot_json=snapshot,
                reason=reason,
            )
        )
        self._event(event, row.id, {"project_workspace_id": row.project_workspace_id, "version": row.version})
        return snapshot

    def _write(self, command, workspace, payload, key, apply, identity=None, expected=None):
        self._project(workspace)
        result = self._command(
            f"procurement.{command}",
            key,
            {"project": workspace, "id": identity, "expected": expected, **payload.model_dump(mode="json")},
            apply,
        )
        return self._redact(workspace, result)

    def history(self, workspace, *, limit=50, after_id=0, entity_type=None, entity_id=None):
        self._read_project(workspace)
        query = self._scoped(ProcurementHistory, workspace).where(ProcurementHistory.id > after_id)
        if entity_type is not None:
            query = query.where(ProcurementHistory.entity_type == entity_type)
        if entity_id is not None:
            query = query.where(ProcurementHistory.entity_id == entity_id)
        rows = list(self.db.scalars(query.order_by(ProcurementHistory.id).limit(limit + 1)))
        return self._redact(
            workspace,
            {
                "items": [self._out(row) for row in rows[:limit]],
                "next_after_id": rows[limit - 1].id if len(rows) > limit else None,
            },
        )
