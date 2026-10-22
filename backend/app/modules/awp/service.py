"""AWP execution governance downstream of immutable Scope and Schedule sources."""

from copy import deepcopy
from datetime import date

from fastapi import HTTPException
from sqlalchemy import func, select

from app.core.time import utc_now
from app.domain.models import AdminConfiguration, SecurityEvent, UserAccount
from app.modules.awp.models import (
    CWA,
    AWPHistory,
    ConstraintMapping,
    ExecutionConstraint,
    PackageDependency,
    PackageMapping,
    ReadinessAssessment,
    WorkPackage,
)
from app.modules.awp.permissions import ACTIONS
from app.modules.awp.policy import CONSTRAINT_TYPES, DEFAULT_PROFILE, DIMENSIONS, LIFECYCLE, assess_policy, has_cycle
from app.modules.basic_data.service import _hash
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.operational_context.models import OperationalContextCommand
from app.modules.schedule_foundation.models import ScheduleVersion
from app.modules.scope_foundation.models import PlanItem, PlanItemScopeLink, ScopeItem
from app.modules.scope_foundation.service import ScopeFoundationService

PROFILE_KIND = "awp_profile"


class AWPService(ScopeFoundationService):
    def _permission(self, action, workspace=None):
        if self.access_context is None:
            return
        if action not in self._permission_contexts:
            self._permission_contexts[action] = require_enterprise_permission(
                self.db, self.tenant_id, self.actor_id, f"awp.{action}", bootstrap=False
            )
        access = self._permission_contexts[action]
        if action.startswith("admin.") and not access.organization_wide:
            self._error(403, "AWP_ADMIN_ORGANIZATION_SCOPE_REQUIRED")
        if workspace is not None:
            self._scope(workspace, access)

    def allowed_actions(self, workspace=None):
        actions = []
        for action in ACTIONS:
            try:
                self._permission(action, workspace)
                actions.append(action)
            except HTTPException as error:
                if error.status_code != 403:
                    raise
        return actions

    def _event(self, action, target_id, metadata, *, outcome="success"):
        self.db.add(
            SecurityEvent(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                event_type=f"awp.{action}",
                outcome=outcome,
                target_type="AWP",
                target_id=target_id,
                metadata_json=deepcopy(metadata),
            )
        )

    def _scope_service(self):
        return ScopeFoundationService(self.db, self.tenant_id, self.actor_id, self.access_context)

    def _awp_profile(self, project):
        candidates = []
        now = utc_now()
        for row in self.db.scalars(
            select(AdminConfiguration).where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == PROFILE_KIND,
                AdminConfiguration.status == "published",
            )
        ):
            content = row.content_json
            start, end = self._instant(content.get("effective_from")), self._instant(content.get("effective_to"))
            if start and now < start or end and now >= end:
                continue
            scope = content["scope"]
            if scope["type"] == "tenant":
                depth = 0
            elif scope["workspace_id"] == project.id:
                depth = 100
            elif content["inherit_to_descendants"] and scope["workspace_id"] in self._workspace_paths.get(
                project.id, set()
            ):
                depth = 50
            else:
                continue
            candidates.append((depth, row))
        if not candidates:
            return None
        depth = max(item[0] for item in candidates)
        top = [row for priority, row in candidates if priority == depth]
        if len({row.code for row in top}) > 1:
            self._error(409, "AWP_PROFILE_AMBIGUOUS")
        return max(top, key=lambda row: row.revision)

    def _ready(self, workspace_id, action):
        project = self._project(workspace_id)
        self._permission(action, project)
        self._scope_service()._ready(workspace_id, "read")
        baseline = self._scope_service()._current_baseline(workspace_id)
        if baseline is None:
            self._error(409, "APPROVED_SCOPE_BASELINE_REQUIRED")
        profile = self._awp_profile(project)
        if profile is None:
            self._error(409, "PUBLISHED_AWP_PROFILE_REQUIRED")
        return project, profile

    def _owner(self, identity):
        if (
            identity is not None
            and self.db.scalar(
                select(UserAccount.id).where(UserAccount.id == identity, UserAccount.tenant_id == self.tenant_id)
            )
            is None
        ):
            self._error(422, "AWP_OWNER_TENANT_MISMATCH")

    def _record(self, row, event, reason, *, changed=False):
        if changed:
            row.version += 1
            row.revision += 1
            row.updated_by, row.updated_at = self.actor_id, utc_now()
        self.db.flush()
        snapshot = self._out(row)
        self.db.add(
            AWPHistory(
                **self._base(row.project_workspace_id),
                entity_type=type(row).__name__,
                entity_id=row.id,
                revision=row.revision,
                snapshot_json=snapshot,
                event_type=event,
                reason=reason,
            )
        )
        self._event(
            event, row.id, {"project_workspace_id": row.project_workspace_id, "version": row.version, "reason": reason}
        )
        return snapshot

    def _write(self, command, workspace, payload, key, apply, identity=None, expected=None):
        return self._command(
            f"awp.{command}",
            key,
            {"project": workspace, "id": identity, "expected": expected, **payload.model_dump(mode="json")},
            apply,
        )

    def _validate_cwa(self, workspace, payload, profile, identity=None):
        if payload.parent_cwa_id:
            if not profile.content_json["cwa_rules"]["allow_nested"]:
                self._error(422, "AWP_NESTED_CWA_DISABLED")
            parent = self._get(CWA, workspace, payload.parent_cwa_id)
            if parent.status != "ACTIVE":
                self._error(409, "AWP_PARENT_CWA_INACTIVE")
        edges = [
            (row.id, row.parent_cwa_id)
            for row in self._rows(CWA, workspace)
            if row.id != identity and row.parent_cwa_id
        ]
        if payload.parent_cwa_id:
            edges.append((identity or -1, payload.parent_cwa_id))
        if has_cycle(edges):
            self._error(422, "AWP_CWA_CYCLE")

    def save_cwa(self, workspace, payload, key, identity=None, expected=None):
        self._ready(workspace, "cwa.manage")

        def apply():
            _, profile = self._ready(workspace, "cwa.manage")
            self._validate_cwa(workspace, payload, profile, identity)
            if identity:
                row = self._get(CWA, workspace, identity, lock=True)
                self._version(row.version, expected)
                for field, value in payload.model_dump(exclude={"reason"}).items():
                    setattr(row, field, value)
            else:
                row = CWA(**self._base(workspace), updated_by=self.actor_id, **payload.model_dump(exclude={"reason"}))
                self.db.add(row)
            return self._record(
                row, "CWA_REVISED" if identity else "CWA_CREATED", payload.reason, changed=bool(identity)
            )

        return self._write("cwa.save", workspace, payload, key, apply, identity, expected)

    def save_package(self, workspace, payload, key, identity=None, expected=None):
        self._ready(workspace, "package.edit")

        def apply():
            _, profile = self._ready(workspace, "package.edit")
            if payload.package_type not in profile.content_json["package_types"]:
                self._error(422, "AWP_PACKAGE_TYPE_NOT_GOVERNED")
            if payload.cwa_id and self._get(CWA, workspace, payload.cwa_id).status != "ACTIVE":
                self._error(409, "AWP_CWA_INACTIVE")
            self._owner(payload.owner_user_id)
            if identity:
                row = self._get(WorkPackage, workspace, identity, lock=True)
                self._version(row.version, expected)
                if row.status not in {"DRAFT", "PLANNED", "UNDER_REVIEW", "READY"}:
                    self._error(409, "AWP_RELEASED_PACKAGE_MATERIAL_IMMUTABLE")
                for field, value in payload.model_dump(exclude={"reason"}).items():
                    setattr(row, field, value)
                row.readiness_state = "NOT_ASSESSED"
                if row.status == "READY":
                    row.status = "PLANNED"
            else:
                row = WorkPackage(
                    **self._base(workspace), updated_by=self.actor_id, **payload.model_dump(exclude={"reason"})
                )
                self.db.add(row)
            return self._record(
                row,
                "WORK_PACKAGE_REVISED" if identity else "WORK_PACKAGE_CREATED",
                payload.reason,
                changed=bool(identity),
            )

        return self._write("package.save", workspace, payload, key, apply, identity, expected)

    def transition_package(self, workspace, identity, payload, expected, key):
        action = (
            "package.review" if payload.status in {"UNDER_REVIEW", "READY", "COMPLETED", "CLOSED"} else "package.edit"
        )
        self._ready(workspace, action)

        def apply():
            _, profile = self._ready(workspace, action)
            row = self._get(WorkPackage, workspace, identity, lock=True)
            self._version(row.version, expected)
            if payload.status not in profile.content_json["package_lifecycle"].get(row.status, []):
                self._error(409, "AWP_PACKAGE_INVALID_TRANSITION")
            if payload.status == "READY":
                current = self._current_readiness(workspace, row, profile)
                if current["readiness_state"] != "READY" or current["stale"]:
                    self._error(409, "AWP_CURRENT_READY_ASSESSMENT_REQUIRED")
            row.status = payload.status
            return self._record(
                row,
                "WORK_PACKAGE_READY" if row.status == "READY" else "WORK_PACKAGE_REVISED",
                payload.reason,
                changed=True,
            )

        return self._write("package.transition", workspace, payload, key, apply, identity, expected)

    def _target(self, workspace, payload, *, package=False):
        kind = payload.target_kind
        if kind == "ACTIVITY":
            if payload.target_id is not None or not payload.schedule_version_id or not payload.activity_external_id:
                self._error(422, "AWP_ACTIVITY_REFERENCE_REQUIRED")
            version = self._get(ScheduleVersion, workspace, payload.schedule_version_id)
            if version.accepted_at is None:
                self._error(409, "AWP_ACCEPTED_SCHEDULE_REQUIRED")
            if not any(
                str(activity.get("external_id")) == payload.activity_external_id
                for activity in version.snapshot_json.get("activities", [])
            ):
                self._error(422, "AWP_ACTIVITY_NOT_FOUND")
            return {"schedule_hash": version.content_hash, "activity_external_id": payload.activity_external_id}
        if (
            payload.target_id is None
            or payload.schedule_version_id is not None
            or payload.activity_external_id is not None
        ):
            self._error(422, "AWP_CANONICAL_TARGET_REQUIRED")
        model = {"SCOPE": ScopeItem, "PLAN": PlanItem, "PACKAGE": WorkPackage, "CWA": CWA}[kind]
        row = self._get(model, workspace, payload.target_id)
        if kind == "PLAN":
            if row.status != "PUBLISHED":
                self._error(409, "AWP_PUBLISHED_PLAN_REQUIRED")
            resolved = list(
                self.db.scalars(select(PlanItemScopeLink.scope_item_id).where(PlanItemScopeLink.plan_item_id == row.id))
            )
        elif kind == "SCOPE":
            resolved = [row.id]
        else:
            resolved = []
        if kind in {"SCOPE", "PLAN"}:
            baseline = self._scope_service()._current_baseline(workspace)
            ids = {item["id"] for item in baseline.snapshot_json["items"]} if baseline else set()
            if not resolved or not set(resolved) <= ids:
                self._error(409, "AWP_CURRENT_APPROVED_SCOPE_REQUIRED")
        return {"resolved_scope_item_ids": resolved, "target_version": row.version}

    @staticmethod
    def _mapping_key(row):
        return (
            row.target_kind,
            row.target_id,
            row.schedule_version_id,
            row.activity_external_id,
            getattr(row, "phase", "EXECUTE"),
        )

    def _effective(self, model, workspace, owner_field, identity=None):
        latest = {}
        for row in self._rows(model, workspace):
            owner = getattr(row, owner_field)
            if identity is None or owner == identity:
                latest[(owner, *self._mapping_key(row))] = row
        return [row for row in latest.values() if row.status == "ACTIVE"]

    def _mapping_out(self, row, workspace):
        result = self._out(row)
        result["mapping_health"] = "VALID"
        if row.target_kind == "ACTIVITY":
            version = self._get(ScheduleVersion, workspace, row.schedule_version_id)
            current = self.db.scalar(
                select(ScheduleVersion).where(
                    ScheduleVersion.tenant_id == self.tenant_id,
                    ScheduleVersion.project_workspace_id == workspace,
                    ScheduleVersion.register_id == version.register_id,
                    ScheduleVersion.status == "ACCEPTED_CURRENT",
                )
            )
            if current and current.id != version.id:
                match = next(
                    (
                        item
                        for item in current.snapshot_json.get("activities", [])
                        if str(item.get("external_id")) == row.activity_external_id
                    ),
                    None,
                )
                result["mapping_health"] = "REQUIRES_REVIEW" if match else "BROKEN"
                result["current_schedule_version_id"] = current.id
        elif row.target_kind in {"SCOPE", "PLAN"}:
            target = self._get(ScopeItem if row.target_kind == "SCOPE" else PlanItem, workspace, row.target_id)
            baseline = self._scope_service()._current_baseline(workspace)
            active = {item["id"] for item in baseline.snapshot_json["items"]} if baseline else set()
            scopes = (
                row.lineage_json.get("resolved_scope_item_ids", [])
                if isinstance(row, PackageMapping)
                else (
                    [target.id]
                    if row.target_kind == "SCOPE"
                    else list(
                        self.db.scalars(
                            select(PlanItemScopeLink.scope_item_id).where(PlanItemScopeLink.plan_item_id == target.id)
                        )
                    )
                )
            )
            if not set(scopes) <= active or row.target_kind == "PLAN" and target.status != "PUBLISHED":
                result["mapping_health"] = "STALE"
        return result

    def map_package(self, workspace, identity, payload, expected, key):
        self._ready(workspace, "mapping.edit")

        def apply():
            self._ready(workspace, "mapping.edit")
            package = self._get(WorkPackage, workspace, identity, lock=True)
            self._version(package.version, expected)
            if package.status in {"CLOSED", "SUPERSEDED"}:
                self._error(409, "AWP_PACKAGE_MAPPING_CLOSED")
            lineage = self._target(workspace, payload, package=True)
            fields = payload.model_dump(exclude={"action", "reason"})
            prior = [
                row
                for row in self._rows(PackageMapping, workspace)
                if row.work_package_id == identity
                and self._mapping_key(row)
                == (
                    payload.target_kind,
                    payload.target_id,
                    payload.schedule_version_id,
                    payload.activity_external_id,
                    payload.phase,
                )
            ]
            row = PackageMapping(
                **self._base(workspace),
                work_package_id=identity,
                **fields,
                status="ACTIVE" if payload.action == "SET" else "REMOVED",
                revision=max((item.revision for item in prior), default=0) + 1,
                lineage_json=lineage,
                reason=payload.reason,
            )
            self.db.add(row)
            package.readiness_state = "NOT_ASSESSED"
            self._record(package, f"WORK_PACKAGE_MAPPED_TO_{payload.target_kind}", payload.reason, changed=True)
            self.db.flush()
            if payload.target_kind == "ACTIVITY":
                self._event(
                    "FOUR_D_MAPPING_CHANGED",
                    row.id,
                    {
                        "project_workspace_id": workspace,
                        "work_package_id": identity,
                        "schedule_version_id": payload.schedule_version_id,
                        "activity_external_id": payload.activity_external_id,
                        "phase": payload.phase,
                        "reason": payload.reason,
                    },
                )
            return self._out(row) | {"version": package.version, "package": self._out(package)}

        return self._write("package.mapping", workspace, payload, key, apply, identity, expected)

    def save_dependency(self, workspace, payload, key, identity=None, expected=None):
        self._ready(workspace, "dependency.edit")

        def apply():
            _, profile = self._ready(workspace, "dependency.edit")
            self._get(WorkPackage, workspace, payload.predecessor_package_id)
            self._get(WorkPackage, workspace, payload.successor_package_id)
            if payload.predecessor_package_id == payload.successor_package_id:
                self._error(422, "AWP_DEPENDENCY_SELF_CYCLE")
            if payload.dependency_type not in profile.content_json["dependency_types"]:
                self._error(422, "AWP_DEPENDENCY_TYPE_NOT_GOVERNED")
            edges = [
                (row.predecessor_package_id, row.successor_package_id)
                for row in self._rows(PackageDependency, workspace)
                if row.id != identity and row.status == "ACTIVE"
            ]
            if payload.status == "ACTIVE":
                edges.append((payload.predecessor_package_id, payload.successor_package_id))
            if profile.content_json["reject_dependency_cycles"] and has_cycle(edges):
                self._error(422, "AWP_DEPENDENCY_CYCLE")
            if payload.status == "CLEARED" and not payload.evidence_reference:
                self._error(422, "AWP_DEPENDENCY_CLEARANCE_EVIDENCE_REQUIRED")
            if identity:
                row = self._get(PackageDependency, workspace, identity, lock=True)
                self._version(row.version, expected)
                for field, value in payload.model_dump().items():
                    setattr(row, field, value)
            else:
                row = PackageDependency(**self._base(workspace), updated_by=self.actor_id, **payload.model_dump())
                self.db.add(row)
            return self._record(row, "WORK_PACKAGE_DEPENDENCY_CHANGED", payload.reason, changed=bool(identity))

        return self._write("dependency.save", workspace, payload, key, apply, identity, expected)

    def save_constraint(self, workspace, payload, key, identity=None, expected=None):
        self._ready(workspace, "constraint.raise")

        def apply():
            _, profile = self._ready(workspace, "constraint.raise")
            rule = profile.content_json["constraint_types"].get(payload.constraint_type)
            if not rule or not rule["enabled"]:
                self._error(422, "AWP_CONSTRAINT_TYPE_NOT_GOVERNED")
            if rule["blocking"] != "USER_SELECTABLE" and payload.blocking != (rule["blocking"] == "ALWAYS"):
                self._error(422, "AWP_CONSTRAINT_BLOCKING_POLICY")
            self._owner(payload.owner_user_id)
            if payload.due_date:
                try:
                    date.fromisoformat(payload.due_date[:10])
                    self._instant(payload.due_date)
                except ValueError as error:
                    raise HTTPException(422, detail={"code": "AWP_DUE_DATE_INVALID"}) from error
            if identity:
                row = self._get(ExecutionConstraint, workspace, identity, lock=True)
                self._version(row.version, expected)
                if row.status not in {"OPEN", "IN_PROGRESS"}:
                    self._error(409, "AWP_CLOSED_CONSTRAINT_IMMUTABLE")
                for field, value in payload.model_dump(exclude={"reason"}).items():
                    setattr(row, field, value)
            else:
                row = ExecutionConstraint(
                    **self._base(workspace), updated_by=self.actor_id, **payload.model_dump(exclude={"reason"})
                )
                self.db.add(row)
            return self._record(
                row,
                "EXECUTION_CONSTRAINT_UPDATED" if identity else "EXECUTION_CONSTRAINT_RAISED",
                payload.reason,
                changed=bool(identity),
            )

        return self._write("constraint.save", workspace, payload, key, apply, identity, expected)

    def transition_constraint(self, workspace, identity, payload, expected, key):
        action = (
            "constraint.waive"
            if payload.status in {"WAIVED", "CANCELLED"}
            else "constraint.clear"
            if payload.status == "CLEARED"
            else "constraint.raise"
        )
        self._ready(workspace, action)

        def apply():
            _, profile = self._ready(workspace, action)
            row = self._get(ExecutionConstraint, workspace, identity, lock=True)
            self._version(row.version, expected)
            if row.status not in {"OPEN", "IN_PROGRESS"}:
                self._error(409, "AWP_CLOSED_CONSTRAINT_IMMUTABLE")
            if payload.status != "IN_PROGRESS":
                if not payload.evidence_reference:
                    self._error(422, "AWP_CONSTRAINT_CLEARANCE_EVIDENCE_REQUIRED")
                if profile.content_json["separation_of_duties"]["owner_cannot_clear"] and self.actor_id in {
                    row.owner_user_id,
                    row.created_by,
                }:
                    self._error(403, "AWP_CONSTRAINT_CLEARANCE_SOD")
                if payload.status == "WAIVED" and not payload.waiver_reference:
                    self._error(422, "AWP_CONSTRAINT_WAIVER_REFERENCE_REQUIRED")
                row.cleared_by, row.cleared_at = self.actor_id, utc_now()
            row.status = payload.status
            row.evidence_reference, row.waiver_reference = payload.evidence_reference, payload.waiver_reference
            return self._record(
                row,
                "EXECUTION_CONSTRAINT_WAIVED"
                if row.status == "WAIVED"
                else "EXECUTION_CONSTRAINT_CLEARED"
                if row.status == "CLEARED"
                else "EXECUTION_CONSTRAINT_UPDATED",
                payload.reason,
                changed=True,
            )

        return self._write("constraint.transition", workspace, payload, key, apply, identity, expected)

    def map_constraint(self, workspace, identity, payload, expected, key):
        self._ready(workspace, "constraint.raise")

        def apply():
            self._ready(workspace, "constraint.raise")
            constraint = self._get(ExecutionConstraint, workspace, identity, lock=True)
            self._version(constraint.version, expected)
            if constraint.status not in {"OPEN", "IN_PROGRESS"}:
                self._error(409, "AWP_CLOSED_CONSTRAINT_IMMUTABLE")
            self._target(workspace, payload)
            prior = [
                row
                for row in self._rows(ConstraintMapping, workspace)
                if row.constraint_id == identity
                and self._mapping_key(row)
                == (
                    payload.target_kind,
                    payload.target_id,
                    payload.schedule_version_id,
                    payload.activity_external_id,
                    "EXECUTE",
                )
            ]
            row = ConstraintMapping(
                **self._base(workspace),
                constraint_id=identity,
                **payload.model_dump(exclude={"reason", "action"}),
                status="ACTIVE" if payload.action == "SET" else "REMOVED",
                revision=max((item.revision for item in prior), default=0) + 1,
                reason=payload.reason,
            )
            self.db.add(row)
            self._record(constraint, "EXECUTION_CONSTRAINT_UPDATED", payload.reason, changed=True)
            self.db.flush()
            return self._out(row) | {"version": constraint.version, "constraint": self._out(constraint)}

        return self._write("constraint.mapping", workspace, payload, key, apply, identity, expected)

    @staticmethod
    def _effective_records(rows, owner_field):
        latest = {(getattr(row, owner_field), *AWPService._mapping_key(row)): row for row in rows}
        return [row for row in latest.values() if row.status == "ACTIVE"]

    def _readiness_facts(self, workspace):
        """Request-local projection only. No database writes or cross-request cache."""
        facts = {
            model: self._rows(model, workspace)
            for model in (
                CWA,
                WorkPackage,
                PackageMapping,
                PackageDependency,
                ExecutionConstraint,
                ConstraintMapping,
                ReadinessAssessment,
            )
        }
        facts["package_mappings"] = self._effective_records(facts[PackageMapping], "work_package_id")
        facts["constraint_mappings"] = self._effective_records(facts[ConstraintMapping], "constraint_id")
        facts["mapping_output"] = {row.id: self._mapping_out(row, workspace) for row in facts["package_mappings"]}
        return facts

    def _readiness_inputs(self, workspace, package, profile, facts=None):
        facts = facts if facts is not None else self._readiness_facts(workspace)
        mappings = [row for row in facts["package_mappings"] if row.work_package_id == package.id]
        mapping_out = [facts["mapping_output"][row.id] for row in mappings]
        scope_ids = {identity for row in mappings for identity in row.lineage_json.get("resolved_scope_item_ids", [])}
        plans = {row.target_id for row in mappings if row.target_kind == "PLAN"}
        activities = {
            (row.schedule_version_id, row.activity_external_id) for row in mappings if row.target_kind == "ACTIVITY"
        }
        cwas = set()
        cwa_id = package.cwa_id
        while cwa_id and cwa_id not in cwas:
            cwas.add(cwa_id)
            cwa_id = next(row.parent_cwa_id for row in facts[CWA] if row.id == cwa_id)
        matches = set()
        for row in facts["constraint_mappings"]:
            if (
                row.target_kind == "PACKAGE"
                and row.target_id == package.id
                or row.target_kind == "CWA"
                and row.target_id in cwas
                or row.target_kind == "SCOPE"
                and row.target_id in scope_ids
                or row.target_kind == "PLAN"
                and row.target_id in plans
                or row.target_kind == "ACTIVITY"
                and (row.schedule_version_id, row.activity_external_id) in activities
            ):
                matches.add(row.constraint_id)
        constraints = [self._out(row) for row in facts[ExecutionConstraint] if row.id in matches]
        predecessor_status = {row.id: row.status for row in facts[WorkPackage]}
        dependencies = [
            self._out(row) | {"predecessor_status": predecessor_status[row.predecessor_package_id]}
            for row in facts[PackageDependency]
            if row.successor_package_id == package.id
        ]
        material = self._out(
            package,
            (
                "version",
                "revision",
                "updated_by",
                "updated_at",
                "status",
                "readiness_state",
                "release_state",
                "released_by",
                "released_at",
            ),
        )
        hashes = {
            "package": _hash(material),
            "mappings": _hash(mapping_out),
            "constraints": _hash(constraints),
            "dependencies": _hash(dependencies),
            "policy": profile.content_hash,
        }
        return mapping_out, constraints, dependencies, hashes

    def _current_readiness(self, workspace, package, profile, facts=None):
        facts = facts if facts is not None else self._readiness_facts(workspace)
        assessments = [row for row in facts[ReadinessAssessment] if row.work_package_id == package.id]
        last = assessments[-1] if assessments else None
        mappings, constraints, dependencies, hashes = self._readiness_inputs(workspace, package, profile, facts)
        evidence = last.evidence_state.get("references", {}) if last else {}
        result = assess_policy(
            package.package_type,
            profile.content_json,
            constraints,
            dependencies,
            evidence,
            any(row["target_kind"] in {"SCOPE", "PLAN"} and row["mapping_health"] == "VALID" for row in mappings),
            any(row["target_kind"] == "ACTIVITY" and row["mapping_health"] == "VALID" for row in mappings),
        )
        stale = last is None or last.source_hashes != hashes
        if last is None and result["readiness_state"] != "NOT_READY" or stale and result["readiness_state"] == "READY":
            result["readiness_state"] = "NOT_ASSESSED"
        if package.release_state == "RELEASED" and result["readiness_state"] == "READY" and not stale:
            result["readiness_state"] = "RELEASED"
        return result | {
            "work_package_id": package.id,
            "assessment_id": last.id if last else None,
            "as_of": last.as_of if last else None,
            "source_hashes": hashes,
            "stale": stale,
            "policy_revision": profile.revision,
            "assessed_by": last.created_by if last else None,
        }

    def assess(self, workspace, identity, payload, expected, key):
        self._ready(workspace, "readiness.assess")

        def apply():
            _, profile = self._ready(workspace, "readiness.assess")
            package = self._get(WorkPackage, workspace, identity, lock=True)
            self._version(package.version, expected)
            try:
                date.fromisoformat(payload.as_of[:10])
                self._instant(payload.as_of)
            except ValueError as error:
                raise HTTPException(422, detail={"code": "AWP_AS_OF_INVALID"}) from error
            if not set(payload.evidence_json) <= set(DIMENSIONS) or any(
                not value.strip() or len(value) > 1000 for value in payload.evidence_json.values()
            ):
                self._error(422, "AWP_READINESS_EVIDENCE_INVALID")
            mappings, constraints, dependencies, hashes = self._readiness_inputs(workspace, package, profile)
            result = assess_policy(
                package.package_type,
                profile.content_json,
                constraints,
                dependencies,
                payload.evidence_json,
                any(row["target_kind"] in {"SCOPE", "PLAN"} and row["mapping_health"] == "VALID" for row in mappings),
                any(row["target_kind"] == "ACTIVITY" and row["mapping_health"] == "VALID" for row in mappings),
            )
            row = ReadinessAssessment(
                **self._base(workspace),
                work_package_id=identity,
                as_of=payload.as_of,
                **result,
                source_hashes=hashes,
                policy_revision=profile.revision,
                configuration_id=profile.id,
                reason=payload.reason,
            )
            self.db.add(row)
            package.readiness_state = result["readiness_state"]
            self._record(package, "READINESS_ASSESSED", payload.reason, changed=True)
            self.db.flush()
            return self._out(row) | {"version": package.version, "package": self._out(package)}

        return self._write("readiness.assess", workspace, payload, key, apply, identity, expected)

    def release(self, workspace, identity, payload, expected, key):
        self._ready(workspace, "package.release")

        def apply():
            _, profile = self._ready(workspace, "package.release")
            package = self._get(WorkPackage, workspace, identity, lock=True)
            self._version(package.version, expected)
            if package.status != "READY":
                self._error(409, "AWP_READY_LIFECYCLE_REQUIRED")
            current = self._current_readiness(workspace, package, profile)
            if current["readiness_state"] != "READY" or current["stale"]:
                self._error(409, "AWP_CURRENT_READY_ASSESSMENT_REQUIRED")
            sod = profile.content_json["separation_of_duties"]
            histories = [
                row
                for row in self._rows(AWPHistory, workspace)
                if row.entity_type == "WorkPackage"
                and row.entity_id == identity
                and row.event_type
                in {
                    "WORK_PACKAGE_CREATED",
                    "WORK_PACKAGE_REVISED",
                    "WORK_PACKAGE_MAPPED_TO_SCOPE",
                    "WORK_PACKAGE_MAPPED_TO_PLAN",
                    "WORK_PACKAGE_MAPPED_TO_ACTIVITY",
                }
            ]
            preparers = {row.created_by for row in histories} | {package.created_by, package.owner_user_id}
            if (
                sod["preparer_cannot_release"]
                and self.actor_id in preparers
                or sod["assessor_cannot_release"]
                and self.actor_id == current["assessed_by"]
            ):
                self._error(403, "AWP_PACKAGE_RELEASE_SOD")
            package.status, package.readiness_state, package.release_state = "RELEASED", "RELEASED", "RELEASED"
            package.released_by, package.released_at = self.actor_id, utc_now()
            return self._record(package, "WORK_PACKAGE_RELEASED", payload.reason, changed=True)

        return self._write("package.release", workspace, payload, key, apply, identity, expected)

    def read_model(self, workspace):
        project = self._project(workspace)
        self._permission("read", project)
        profile = self._awp_profile(project)
        facts = self._readiness_facts(workspace)
        packages = facts[WorkPackage]
        return {
            "version": 1,
            "configuration": self._profile_out(profile) if profile else None,
            "cwas": [self._out(row) for row in facts[CWA]],
            "packages": [self._out(row) for row in packages],
            "mappings": [self._out(row) for row in facts[PackageMapping]],
            "effective_mappings": [facts["mapping_output"][row.id] for row in facts["package_mappings"]],
            "dependencies": [self._out(row) for row in facts[PackageDependency]],
            "constraints": [self._out(row) for row in facts[ExecutionConstraint]],
            "constraint_mappings": [self._out(row) for row in facts["constraint_mappings"]],
            "assessments": [self._out(row) for row in facts[ReadinessAssessment]],
            "current_readiness": {
                str(row.id): self._current_readiness(workspace, row, profile, facts) for row in packages
            }
            if profile
            else {},
        }

    def overview(self, workspace):
        result = self.read_model(workspace)
        scope = self._scope_service()
        scope._permission("read", self._project(workspace))
        baseline = scope._current_baseline(workspace)
        return result | {
            "context": self._operational().context(workspace),
            "allowed_actions": self.allowed_actions(self._project(workspace)),
            "scope_items": [scope._item_out(row) for row in scope._rows(ScopeItem, workspace)],
            "plan_items": [scope._plan_out(row) for row in scope._rows(PlanItem, workspace)],
            "schedule_versions": [
                self._out(row) for row in self._rows(ScheduleVersion, workspace) if row.accepted_at is not None
            ],
            "current_scope_item_ids": [item["id"] for item in baseline.snapshot_json["items"]] if baseline else [],
            "authority": {
                "scope": "SCOPE_FOUNDATION",
                "schedule": "SCHEDULE_FOUNDATION",
                "cpm": "PRIMAVERA_P6_EXTERNAL",
                "execution_constraints": "AWP_SEPARATE_FROM_P6",
                "scheduled_is_ready": False,
            },
        }

    def history(self, workspace, entity_type, identity):
        self._permission("read", self._project(workspace))
        return {
            "items": [
                self._out(row)
                for row in self._rows(AWPHistory, workspace)
                if row.entity_type == entity_type and row.entity_id == identity
            ]
        }

    def _profile(self, identity, *, lock=False):
        query = select(AdminConfiguration).where(
            AdminConfiguration.tenant_id == self.tenant_id,
            AdminConfiguration.kind == PROFILE_KIND,
            AdminConfiguration.id == identity,
        )
        row = self.db.scalar(query.with_for_update().execution_options(populate_existing=True) if lock else query)
        if row is None:
            self._error(404, "AWP_PROFILE_NOT_FOUND")
        return row

    def profiles(self):
        self._permission("admin.configure")
        return {
            "items": [
                self._profile_out(row)
                for row in self.db.scalars(
                    select(AdminConfiguration)
                    .where(AdminConfiguration.tenant_id == self.tenant_id, AdminConfiguration.kind == PROFILE_KIND)
                    .order_by(AdminConfiguration.code, AdminConfiguration.revision.desc())
                )
            ],
            "default_content": deepcopy(DEFAULT_PROFILE),
            "allowed_actions": self.allowed_actions(),
        }

    def _validate_profile(self, content):
        try:
            if (
                set(content) != set(DEFAULT_PROFILE)
                or content["release_workflow"] != DEFAULT_PROFILE["release_workflow"]
            ):
                raise ValueError("keys/workflow")
            for field in ("package_types", "dependency_types"):
                values = content[field]
                if (
                    not isinstance(values, list)
                    or not values
                    or len(set(values)) != len(values)
                    or any(not isinstance(value, str) or not value.strip() or len(value) > 80 for value in values)
                ):
                    raise ValueError(field)
            if not {"EWP", "PWP", "CWP", "IWP", "TWP"} <= set(content["package_types"]):
                raise ValueError("required package types")
            if (
                type(content["reject_dependency_cycles"]) is not bool
                or type(content["inherit_to_descendants"]) is not bool
            ):
                raise ValueError("booleans")
            if (
                set(content["cwa_rules"]) != {"allow_nested", "reject_cycles"}
                or content["cwa_rules"]["reject_cycles"] is not True
                or type(content["cwa_rules"]["allow_nested"]) is not bool
            ):
                raise ValueError("cwa")
            if set(content["package_lifecycle"]) != set(LIFECYCLE) or any(
                not isinstance(next_states, list) or not set(next_states) <= set(LIFECYCLE[state])
                for state, next_states in content["package_lifecycle"].items()
            ):
                raise ValueError("lifecycle transitions cannot bypass authority")
            if set(content["constraint_types"]) != set(CONSTRAINT_TYPES):
                raise ValueError("constraint types")
            for rule in content["constraint_types"].values():
                if (
                    set(rule) != {"enabled", "blocking"}
                    or type(rule["enabled"]) is not bool
                    or rule["blocking"] not in {"ALWAYS", "NEVER", "USER_SELECTABLE"}
                ):
                    raise ValueError("constraint rule")
            if set(content["readiness_requirements"]) != set(content["package_types"]):
                raise ValueError("tailoring")
            for rule in content["readiness_requirements"].values():
                if (
                    set(rule) != {"required_dimensions", "require_scope_or_plan", "require_activity"}
                    or not isinstance(rule["required_dimensions"], list)
                    or not set(rule["required_dimensions"]) <= set(DIMENSIONS)
                    or type(rule["require_scope_or_plan"]) is not bool
                    or type(rule["require_activity"]) is not bool
                ):
                    raise ValueError("requirements")
            sod = content["separation_of_duties"]
            if set(sod) != set(DEFAULT_PROFILE["separation_of_duties"]) or any(
                type(value) is not bool for value in sod.values()
            ):
                raise ValueError("SoD")
            scope = content["scope"]
            if set(scope) != {"type", "workspace_id"}:
                raise ValueError("scope")
            if scope["type"] == "workspace":
                self._project(scope["workspace_id"])
            elif scope != {"type": "tenant", "workspace_id": None}:
                raise ValueError("scope")
            start, end = self._instant(content["effective_from"]), self._instant(content["effective_to"])
            if start and end and end <= start:
                raise ValueError("window")
        except (KeyError, TypeError, ValueError) as error:
            raise HTTPException(422, detail={"code": "AWP_PROFILE_INVALID"}) from error

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
                self._error(409, "AWP_PROFILE_CODE_EXISTS")
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
            self._event("AWP_PROFILE_CREATED", row.id, {"hash": row.content_hash})
            return self._profile_out(row)

        return self._command("awp.profile.create", key, payload.model_dump(mode="json"), apply)

    def update_profile(self, identity, payload, expected, key):
        self._permission("admin.configure")

        def apply():
            row = self._profile(identity, lock=True)
            self._version(row.version, expected)
            if row.status != "draft":
                self._error(409, "AWP_PROFILE_PUBLISHED_IMMUTABLE")
            self._validate_profile(payload.content_json)
            row.name, row.content_json, row.content_hash = (
                payload.name,
                deepcopy(payload.content_json),
                _hash(payload.content_json),
            )
            row.version, row.updated_at = row.version + 1, utc_now()
            self.db.flush()
            self._event("AWP_PROFILE_UPDATED", row.id, {"version": row.version})
            return self._profile_out(row)

        return self._command(
            "awp.profile.update", key, {"id": identity, "expected": expected, **payload.model_dump(mode="json")}, apply
        )

    def publish_profile(self, identity, payload, expected, key):
        self._permission("admin.publish")

        def apply():
            row = self._profile(identity, lock=True)
            self._version(row.version, expected)
            if row.status != "draft":
                self._error(409, "AWP_PROFILE_PUBLISHED_IMMUTABLE")
            self._validate_profile(row.content_json)
            editor = row.created_by_user_id
            if row.version > 1:
                receipt = self.db.scalar(
                    select(OperationalContextCommand).where(
                        OperationalContextCommand.tenant_id == self.tenant_id,
                        OperationalContextCommand.command_type == "awp.profile.update",
                        OperationalContextCommand.result_json["id"].as_integer() == row.id,
                        OperationalContextCommand.result_json["version"].as_integer() == row.version,
                    )
                )
                if receipt is None or receipt.result_json.get("content_hash") != row.content_hash:
                    self._error(409, "AWP_PROFILE_EDITOR_PROVENANCE_REQUIRED")
                editor = receipt.actor_id
            if row.content_json["separation_of_duties"]["author_cannot_publish"] and self.actor_id in {
                row.created_by_user_id,
                editor,
            }:
                self._error(403, "AWP_PROFILE_PUBLICATION_SOD")
            row.status, row.published_at, row.version = "published", utc_now(), row.version + 1
            self.db.flush()
            self._event("AWP_CONFIGURATION_PUBLISHED", row.id, {"hash": row.content_hash, "reason": payload.reason})
            return self._profile_out(row)

        return self._command(
            "awp.profile.publish", key, {"id": identity, "expected": expected, **payload.model_dump(mode="json")}, apply
        )

    def successor_profile(self, identity, payload, expected, key):
        self._permission("admin.configure")

        def apply():
            old = self._profile(identity, lock=True)
            self._version(old.version, expected)
            if old.status != "published":
                self._error(409, "AWP_PUBLISHED_PROFILE_REQUIRED")
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
            self._event("AWP_PROFILE_SUCCESSOR", row.id, {"predecessor_id": old.id, "reason": payload.reason})
            return self._profile_out(row)

        return self._command(
            "awp.profile.successor",
            key,
            {"id": identity, "expected": expected, **payload.model_dump(mode="json")},
            apply,
        )
