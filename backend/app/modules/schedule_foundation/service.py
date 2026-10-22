"""Schedule governance downstream of approved Scope; never a CPM engine."""

import json
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy import func, select

from app.core.time import utc_now
from app.domain.models import AdminConfiguration, SecurityEvent
from app.modules.basic_data.service import _hash, _json
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.operational_context.models import OperationalContextCommand, ProjectControlsPeriod
from app.modules.schedule_foundation.models import (
    ScheduleBaseline,
    ScheduleExportManifest,
    ScheduleMapping,
    SchedulePeriodAssociation,
    ScheduleRegister,
    ScheduleVersion,
)
from app.modules.schedule_foundation.permissions import ACTIONS
from app.modules.scope_foundation.models import DerivedModelVersion, PlanItem, PlanItemScopeLink, ScopeItem
from app.modules.scope_foundation.service import ScopeFoundationService
from app.services.schedule_parser import ScheduleParseError

PROFILE_KIND = "schedule_profile"
DEFAULT_PROFILE = {
    "scope": {"type": "tenant", "workspace_id": None},
    "inherit_to_descendants": True,
    "effective_from": None,
    "effective_to": None,
    "schedule_types": ["CONTRACT", "OWNER", "CONTROL", "COMMISSIONING", "SUBCONTRACT"],
    "baseline_types": ["ORIGINAL", "CONTROL", "CONTRACT", "TARGET"],
    "allow_multiple_streams": True,
    "near_critical_threshold": {"value": 40, "unit": "HOUR"},
    "quality_thresholds": {
        "max_open_ends": None,
        "long_duration_hours": 240,
        "max_lag_hours": 80,
        "negative_lag": "WARN",
        "hard_constraint": "WARN",
        "external_links": "BLOCK_UNRESOLVED",
    },
    "open_end_policy": {"authorized_milestone_types": ["Start Milestone", "Finish Milestone"]},
    "allowed_constraints": [
        "Start On",
        "Start On or After",
        "Start On or Before",
        "Finish On",
        "Finish On or After",
        "Finish On or Before",
        "Mandatory Start",
        "Mandatory Finish",
        "As Late As Possible",
    ],
    "supported_exchange": {
        "imports": ["P6_XML", "P6_XER"],
        "exports": ["XML"],
        "native_baseline_transport": False,
        "full_p6_parity": False,
    },
    "calendar_handling": "EXPLICIT_SOURCE_NO_8H_ASSUMPTION",
    "mapping_policy": {
        "activities_required": True,
        "wbs_required": False,
        "milestone_mapping_required": False,
        "published_plan_required": True,
        "allow_direct_scope": True,
    },
    "activity_code_mapping_rules": {},
    "baseline_workflow": ["BASELINE_CANDIDATE", "SUBMITTED", "UNDER_REVIEW", "APPROVED_BASELINE"],
    "lookahead_default_days": 28,
    "separation_of_duties": {
        "author_cannot_publish": True,
        "importer_cannot_accept": True,
        "baseline_preparer_cannot_approve": True,
    },
}


class ScheduleFoundationService(ScopeFoundationService):
    def _permission(self, action, workspace=None):
        if self.access_context is None:
            return
        if action not in self._permission_contexts:
            self._permission_contexts[action] = require_enterprise_permission(
                self.db, self.tenant_id, self.actor_id, f"schedule_foundation.{action}", bootstrap=False
            )
        access = self._permission_contexts[action]
        if action.startswith("admin.") and not access.organization_wide:
            self._error(403, "SCHEDULE_ADMIN_ORGANIZATION_SCOPE_REQUIRED")
        if workspace is not None:
            self._scope(workspace, access)

    def allowed_actions(self, workspace=None):
        result = []
        for action in ACTIONS:
            try:
                self._permission(action, workspace)
                result.append(action)
            except HTTPException as error:
                if error.status_code != 403:
                    raise
        return result

    def _event(self, action, target_id, metadata, *, outcome="success"):
        self.db.add(
            SecurityEvent(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                event_type=f"schedule.{action}",
                outcome=outcome,
                target_type="ScheduleFoundation",
                target_id=target_id,
                metadata_json=deepcopy(metadata),
            )
        )

    def _scope_service(self):
        return ScopeFoundationService(self.db, self.tenant_id, self.actor_id, self.access_context)

    def _schedule_profile(self, project):
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
            else:
                self._scope(project, self.access_context)
                if scope["workspace_id"] == project.id:
                    depth = 100
                elif (
                    content.get("inherit_to_descendants", True)
                    and scope["workspace_id"] in self._workspace_paths[project.id]
                ):
                    depth = 50
                else:
                    continue
            candidates.append((depth, row))
        if not candidates:
            return None
        top_depth = max(depth for depth, _ in candidates)
        top = [row for depth, row in candidates if depth == top_depth]
        if len({row.code for row in top}) > 1:
            self._error(409, "SCHEDULE_PROFILE_AMBIGUOUS")
        return max(top, key=lambda row: row.revision)

    def _ready(self, workspace_id, action):
        project = self._project(workspace_id)
        self._permission(action, project)
        scope = self._scope_service()
        scope._ready(workspace_id, "read")
        baseline = scope._current_baseline(workspace_id)
        if baseline is None:
            self._error(409, "APPROVED_SCOPE_BASELINE_REQUIRED")
        profile = self._schedule_profile(project)
        if profile is None:
            self._error(409, "PUBLISHED_SCHEDULE_PROFILE_REQUIRED")
        return project, profile, baseline

    def _version_out(self, row):
        return self._out(row) | {
            "mappings": self._effective_mappings(row),
            "imported_at": row.created_at.isoformat(),
            "imported_by": row.created_by,
            "source_size_bytes": len(row.source_content),
        }

    def overview(self, workspace_id):
        project = self._project(workspace_id)
        self._permission("read", project)
        profile = self._schedule_profile(project)
        scope = self._scope_service()
        scope._permission("read", project)
        scope_baseline = scope._current_baseline(workspace_id)
        return {
            "version": 1,
            "context": self._operational().context(workspace_id),
            "configuration": self._profile_out(profile) if profile else None,
            "current_scope_baseline_id": scope_baseline.id if scope_baseline else None,
            "current_scope_item_ids": [item["id"] for item in scope_baseline.snapshot_json["items"]]
            if scope_baseline
            else [],
            "allowed_actions": self.allowed_actions(project),
            "registers": [self._out(row) for row in self._rows(ScheduleRegister, workspace_id)],
            "versions": [self._version_out(row) for row in self._rows(ScheduleVersion, workspace_id)],
            "baselines": [self._out(row) for row in self._rows(ScheduleBaseline, workspace_id)],
            "mappings": [self._out(row) for row in self._rows(ScheduleMapping, workspace_id)],
            "exports": [self._out(row) for row in self._rows(ScheduleExportManifest, workspace_id)],
            "period_associations": [self._out(row) for row in self._rows(SchedulePeriodAssociation, workspace_id)],
            "periods": [self._out(row) for row in self._rows(ProjectControlsPeriod, workspace_id)],
            "scope_items": [scope._item_out(row) for row in scope._rows(ScopeItem, workspace_id)],
            "plan_items": [scope._plan_out(row) for row in scope._rows(PlanItem, workspace_id)],
            "derived_models": [self._out(row) for row in self._rows(DerivedModelVersion, workspace_id)],
            "authority": {
                "scope": "SCOPE_FOUNDATION",
                "schedule": "SCHEDULE_FOUNDATION",
                "cpm": "PRIMAVERA_P6_EXTERNAL",
                "cost": "NOT_ACTIVE",
                "progress": "NOT_ACTIVE",
                "timeline_4d": "NOT_ACTIVE",
            },
        }

    def _effective_mappings(self, version, *, include_removed=False):
        rows = self.db.scalars(
            select(ScheduleMapping)
            .where(
                ScheduleMapping.tenant_id == self.tenant_id,
                ScheduleMapping.project_workspace_id == version.project_workspace_id,
                ScheduleMapping.schedule_version_id == version.id,
            )
            .order_by(ScheduleMapping.id)
        ).all()
        latest = {(row.target_kind, row.target_external_id): row for row in rows}
        result = []
        current = self._scope_service()._current_baseline(version.project_workspace_id)
        active_scope = {item["id"] for item in current.snapshot_json["items"]} if current else set()
        for row in latest.values():
            if row.status == "REMOVED" and not include_removed:
                continue
            out = self._out(row)
            if row.status != "REMOVED":
                targets = version.snapshot_json.get("wbs" if row.target_kind == "WBS" else "activities", [])
                if not any(str(target.get("external_id")) == row.target_external_id for target in targets):
                    out["status"] = "BROKEN"
                elif any(
                    identity not in active_scope for identity in row.lineage_json.get("resolved_scope_item_ids", [])
                ):
                    out["status"] = "STALE"
                elif any(
                    self._get(PlanItem, version.project_workspace_id, identity).status == "SUPERSEDED"
                    for identity in row.plan_item_ids
                ):
                    out["status"] = "STALE"
                out["resolved_scope_item_ids"] = list(row.lineage_json.get("resolved_scope_item_ids", []))
            result.append(out)
        return result

    def create_register(self, workspace_id, payload, key):
        self._ready(workspace_id, "register.edit")

        def apply():
            _, profile, _ = self._ready(workspace_id, "register.edit")
            if not payload.schedule_code.strip() or not payload.name.strip():
                self._error(422, "SCHEDULE_REGISTER_CODE_AND_NAME_REQUIRED")
            if payload.schedule_type not in profile.content_json["schedule_types"]:
                self._error(422, "SCHEDULE_TYPE_NOT_GOVERNED")
            try:
                ZoneInfo(payload.timezone)
            except (ZoneInfoNotFoundError, ValueError) as error:
                raise HTTPException(422, detail={"code": "SCHEDULE_TIMEZONE_INVALID"}) from error
            if not profile.content_json["allow_multiple_streams"] and self._rows(ScheduleRegister, workspace_id):
                self._error(409, "SCHEDULE_MULTIPLE_STREAMS_NOT_ALLOWED")
            row = ScheduleRegister(**self._base(workspace_id), **payload.model_dump(exclude={"reason"}))
            self.db.add(row)
            self.db.flush()
            self._event(
                "SCHEDULE_REGISTER_CREATED", row.id, {"project_workspace_id": workspace_id, "reason": payload.reason}
            )
            return self._out(row)

        return self._command(
            "schedule.register.create", key, {"project": workspace_id, **payload.model_dump(mode="json")}, apply
        )

    def _new_version(
        self,
        workspace_id,
        register,
        snapshot,
        content,
        filename,
        source_format,
        kind,
        predecessor_id,
        reason,
        parsed,
        profile,
        scope_baseline,
    ):
        from app.modules.schedule_foundation.exchange import diff_schedule, validate_snapshot

        if kind not in {"INITIAL", "UPDATE", "CORRECTION", "FORECAST", "SCENARIO", "APPROVED_CHANGE"}:
            self._error(422, "SCHEDULE_VERSION_KIND_INVALID")
        if kind == "APPROVED_CHANGE":
            self._error(409, "SCHEDULE_APPROVED_CHANGE_INTERFACE_RESERVED")
        predecessor_id = predecessor_id or register.current_version_id
        predecessor = self._get(ScheduleVersion, workspace_id, predecessor_id) if predecessor_id else None
        if predecessor and predecessor.register_id != register.id:
            self._error(422, "SCHEDULE_PREDECESSOR_STREAM_MISMATCH")
        revision = (
            self.db.scalar(select(func.max(ScheduleVersion.revision)).where(ScheduleVersion.register_id == register.id))
            or 0
        ) + 1
        snapshot = _json(deepcopy(snapshot))
        try:
            json.dumps(snapshot, allow_nan=False)
        except (TypeError, ValueError) as error:
            raise HTTPException(422, detail={"code": "SCHEDULE_FINITE_JSON_REQUIRED"}) from error
        if not isinstance(snapshot.get("project", {}), dict) or any(
            not isinstance(snapshot.get(collection, []), list)
            or any(not isinstance(item, dict) for item in snapshot.get(collection, []))
            for collection in (
                "wbs",
                "activities",
                "calendars",
                "relationships",
                "constraints",
                "codes",
                "code_assignments",
                "external_links",
            )
        ):
            self._error(422, "SCHEDULE_SNAPSHOT_STRUCTURE_INVALID")
        parsed = {**parsed, "validation": validate_snapshot(snapshot)}
        if len(filename) > 260 or len(str(snapshot.get("project", {}).get("data_date") or "")) > 80:
            self._error(422, "SCHEDULE_SOURCE_METADATA_LIMIT")
        # A staged WBS move is a successor source definition, never a mutation of
        # the accepted snapshot. Its path follows explicit parents, not UI input.
        wbs_index = {str(item.get("external_id")): item for item in snapshot.get("wbs", [])}
        for item in snapshot.get("wbs", []):
            current, visited, path = item, set(), []
            while current and str(current.get("external_id")) not in visited and len(visited) < 100:
                visited.add(str(current.get("external_id")))
                path.append(str(current.get("code") or current.get("external_id")))
                current = wbs_index.get(str(current.get("parent_external_id")))
            item["path"] = "/".join(reversed(path))
            item.setdefault("status", "ACTIVE")
        if len(str(snapshot)) > 40 * 1024 * 1024:
            self._error(422, "SCHEDULE_SNAPSHOT_TOO_LARGE")
        row = ScheduleVersion(
            **self._base(workspace_id),
            register_id=register.id,
            revision=revision,
            predecessor_version_id=predecessor_id,
            scope_baseline_id=scope_baseline.id,
            configuration_id=profile.id,
            configuration_hash=profile.content_hash,
            kind=kind,
            status="DRAFT" if source_format == "MANUAL" else "STAGED",
            data_date=str(snapshot.get("project", {}).get("data_date") or ""),
            source_file_name=filename,
            source_format=source_format,
            source_hash=sha256(content).hexdigest(),
            source_content=content,
            snapshot_json=snapshot,
            content_hash=_hash(snapshot),
            validation_json=parsed["validation"],
            import_manifest_json={
                "source_format": source_format,
                "supported_subset": parsed.get("supported_subset"),
                "unsupported_fields": parsed.get("unsupported_fields", []),
                "expected_current_version_id": register.current_version_id,
                "scope_baseline_id": scope_baseline.id,
                "configuration_hash": profile.content_hash,
                "cpm_authority": "PRIMAVERA_P6_EXTERNAL",
                "native_baseline_transport": False,
            },
            diff_json=diff_schedule(predecessor.snapshot_json if predecessor else {}, snapshot),
            last_material_editor=self.actor_id,
            reason=reason,
        )
        self.db.add(row)
        self.db.flush()
        if predecessor:
            for old in self._effective_mappings(predecessor):
                collection = "wbs" if old["target_kind"] == "WBS" else "activities"
                target_exists = any(
                    str(item.get("external_id")) == old["target_external_id"] for item in snapshot.get(collection, [])
                )
                changed = old["target_external_id"] in row.diff_json.get("mapping_impacts", {}).get(collection, {}).get(
                    "changed", []
                )
                status = "BROKEN" if not target_exists else "REQUIRES_REVIEW" if changed else old["status"]
                self.db.add(
                    ScheduleMapping(
                        **self._base(workspace_id),
                        schedule_version_id=row.id,
                        target_kind=old["target_kind"],
                        target_external_id=old["target_external_id"],
                        status=status,
                        plan_item_ids=deepcopy(old["plan_item_ids"]),
                        scope_item_ids=deepcopy(old["scope_item_ids"]),
                        lineage_json=deepcopy(old["lineage_json"])
                        | {"inherited_mapping_id": old["id"], "predecessor_version_id": predecessor.id},
                        reason="Explicit inherited source mapping; reconciliation required if changed",
                    )
                )
        register.version += 1
        self.db.flush()
        row.health_json = self._health(row, profile)
        self.db.flush()
        self._event(
            "SCHEDULE_IMPORTED" if source_format != "MANUAL" else "SCHEDULE_VERSION_CREATED",
            row.id,
            {"project_workspace_id": workspace_id, "register_id": register.id, "source_hash": row.source_hash},
        )
        return self._version_out(row)

    def stage_import(self, workspace_id, register_id, content, filename, reason, kind, predecessor_id, expected, key):
        from app.modules.schedule_foundation.exchange import parse_schedule_source

        self._ready(workspace_id, "import")
        if not content or len(content) > 40 * 1024 * 1024 or not 3 <= len(reason.strip()) <= 3000:
            self._error(422, "SCHEDULE_SOURCE_INPUT_INVALID")

        def apply():
            _, profile, scope_baseline = self._ready(workspace_id, "import")
            register = self._get(ScheduleRegister, workspace_id, register_id, lock=True)
            self._version(register.version, expected)
            try:
                parsed = parse_schedule_source(content, filename)
            except (ScheduleParseError, ValueError) as error:
                raise HTTPException(
                    422, detail={"code": "SCHEDULE_SOURCE_INVALID", "message": str(error)[:500]}
                ) from error
            if parsed["source_format"] not in profile.content_json["supported_exchange"]["imports"]:
                self._error(422, "SCHEDULE_IMPORT_SUBSET_NOT_GOVERNED")
            return self._new_version(
                workspace_id,
                register,
                parsed["snapshot"],
                content,
                filename,
                parsed["source_format"],
                kind,
                predecessor_id,
                reason,
                parsed,
                profile,
                scope_baseline,
            )

        return self._command(
            "schedule.import",
            key,
            {
                "project": workspace_id,
                "register": register_id,
                "hash": sha256(content).hexdigest(),
                "filename": filename,
                "reason": reason,
                "kind": kind,
                "predecessor": predecessor_id,
                "expected": expected,
            },
            apply,
        )

    def create_version(self, workspace_id, register_id, payload, expected, key):
        from app.modules.schedule_foundation.exchange import validate_snapshot

        self._ready(workspace_id, "version.edit")

        def apply():
            _, profile, scope_baseline = self._ready(workspace_id, "version.edit")
            register = self._get(ScheduleRegister, workspace_id, register_id, lock=True)
            self._version(register.version, expected)
            predecessor_id = payload.predecessor_version_id or register.current_version_id
            predecessor = self._get(ScheduleVersion, workspace_id, predecessor_id) if predecessor_id else None
            old = (
                {str(row.get("external_id")): row for row in predecessor.snapshot_json.get("activities", [])}
                if predecessor
                else {}
            )
            cpm_fields = (
                "total_float",
                "free_float",
                "critical",
                "early_start",
                "early_finish",
                "late_start",
                "late_finish",
            )
            activities = payload.snapshot_json.get("activities", [])
            if not isinstance(activities, list) or any(not isinstance(item, dict) for item in activities):
                self._error(422, "SCHEDULE_SNAPSHOT_STRUCTURE_INVALID")
            for activity in activities:
                if any(
                    activity.get(name) is not None
                    and activity.get(name) != old.get(str(activity.get("external_id")), {}).get(name)
                    for name in cpm_fields
                ):
                    self._error(422, "SCHEDULE_CPM_RESULTS_REQUIRE_IMPORTED_SOURCE")
            snapshot = _json(payload.snapshot_json)
            parsed = {
                "validation": validate_snapshot(snapshot),
                "supported_subset": "MANUAL_GOVERNED_SNAPSHOT_NO_CPM",
                "unsupported_fields": [],
            }
            return self._new_version(
                workspace_id,
                register,
                snapshot,
                str(snapshot).encode("utf-8"),
                "manual-schedule-definition",
                "MANUAL",
                payload.kind,
                payload.predecessor_version_id,
                payload.reason,
                parsed,
                profile,
                scope_baseline,
            )

        return self._command(
            "schedule.version.create",
            key,
            {"project": workspace_id, "register": register_id, "expected": expected, **payload.model_dump(mode="json")},
            apply,
        )

    def _health(self, row, profile):
        from app.modules.schedule_foundation.exchange import validate_snapshot

        policy = profile.content_json
        snapshot = row.snapshot_json
        validation = validate_snapshot(snapshot)
        errors, warnings = deepcopy(validation.get("errors", [])), deepcopy(validation.get("warnings", []))
        if errors:
            return {
                "errors": errors,
                "warnings": warnings,
                "can_accept": False,
                "quality_is_not_cpm": True,
                "metrics": {},
                "near_critical_threshold": deepcopy(policy["near_critical_threshold"]),
            }
        activities, calendars = snapshot.get("activities", []), snapshot.get("calendars", [])
        activity_ids = {str(item.get("external_id")) for item in activities}
        calendar_ids = {str(item.get("external_id")): item for item in calendars}
        mappings = self._effective_mappings(row)
        mapped = {(item["target_kind"], item["target_external_id"]) for item in mappings if item["status"] == "VALID"}
        invalid_mappings = [item for item in mappings if item["status"] != "VALID"]
        errors.extend(
            {"code": "SCHEDULE_MAPPING_" + item["status"], "target": item["target_external_id"]}
            for item in invalid_mappings
        )
        current_scope = self._scope_service()._current_baseline(row.project_workspace_id)
        if current_scope is None or current_scope.id != row.scope_baseline_id:
            errors.append({"code": "SCHEDULE_SCOPE_BASELINE_CHANGED_CREATE_SUCCESSOR"})
        predecessor_ids, successor_ids = set(), set()
        unresolved = []
        thresholds = policy["quality_thresholds"]
        for relation in snapshot.get("relationships", []):
            predecessor, successor = (
                str(relation.get("predecessor_external_id")),
                str(relation.get("successor_external_id")),
            )
            if not relation.get("is_external") and predecessor in activity_ids and successor in activity_ids:
                successor_ids.add(predecessor)
                predecessor_ids.add(successor)
            else:
                unresolved.append(relation.get("external_id"))
            lag = relation.get("lag")
            if lag is not None:
                lag = Decimal(str(lag))
                if relation.get("lag_unit") not in {"HOUR", "DAY"}:
                    errors.append({"code": "SCHEDULE_LAG_UNIT_UNKNOWN", "target": relation.get("external_id")})
                elif relation.get("lag_unit") == "DAY":
                    warnings.append(
                        {"code": "SCHEDULE_LAG_DAY_PRESERVED_NOT_CONVERTED", "target": relation.get("external_id")}
                    )
                if lag < 0:
                    (errors if thresholds["negative_lag"] == "BLOCK" else warnings).append(
                        {"code": "SCHEDULE_NEGATIVE_LAG", "target": relation.get("external_id")}
                    )
                if relation.get("lag_unit") == "HOUR" and abs(lag) > Decimal(str(thresholds["max_lag_hours"])):
                    warnings.append({"code": "SCHEDULE_EXCESSIVE_LAG", "target": relation.get("external_id")})
        if unresolved:
            (errors if thresholds["external_links"] == "BLOCK_UNRESOLVED" else warnings).append(
                {"code": "SCHEDULE_UNRESOLVED_EXTERNAL_LINKS", "references": unresolved}
            )
        open_ends, missing_calendar, missing_mapping = [], [], []
        exempt_types = policy["open_end_policy"]["authorized_milestone_types"]
        for activity in activities:
            identity = str(activity.get("external_id"))
            kind = activity.get("activity_type", "Task Dependent")
            milestone = "Milestone" in kind
            if identity not in predecessor_ids or identity not in successor_ids:
                if kind not in exempt_types:
                    open_ends.append(identity)
            calendar = calendar_ids.get(str(activity.get("calendar_external_id")))
            if not milestone and calendar is None:
                missing_calendar.append(identity)
            unit = activity.get("duration_unit")
            if (
                unit not in {"HOUR", "DAY"}
                or unit == "DAY"
                and (calendar is None or calendar.get("hours_per_day") is None)
            ):
                errors.append({"code": "SCHEDULE_DURATION_BASIS_UNKNOWN_NO_8H_ASSUMPTION", "target": identity})
            duration = activity.get("original_duration")
            if (
                duration is not None
                and unit == "HOUR"
                and Decimal(str(duration)) > Decimal(str(thresholds["long_duration_hours"]))
            ):
                warnings.append({"code": "SCHEDULE_LONG_DURATION", "target": identity})
            needs_mapping = (
                policy["mapping_policy"]["milestone_mapping_required"]
                if milestone
                else policy["mapping_policy"]["activities_required"]
            )
            if needs_mapping and ("ACTIVITY", identity) not in mapped:
                missing_mapping.append(identity)
        if missing_calendar:
            errors.append({"code": "SCHEDULE_CALENDAR_REFERENCE_MISSING", "references": missing_calendar})
        if missing_mapping:
            errors.append({"code": "SCHEDULE_SCOPE_PLAN_MAPPING_REQUIRED", "references": missing_mapping})
        if policy["mapping_policy"]["wbs_required"]:
            missing_wbs = [
                str(item.get("external_id"))
                for item in snapshot.get("wbs", [])
                if ("WBS", str(item.get("external_id"))) not in mapped
            ]
            if missing_wbs:
                errors.append({"code": "SCHEDULE_WBS_MAPPING_REQUIRED", "references": missing_wbs})
        if open_ends:
            maximum = thresholds["max_open_ends"]
            (errors if maximum is not None and len(open_ends) > maximum else warnings).append(
                {"code": "SCHEDULE_OPEN_ENDS", "references": open_ends}
            )
        for constraint in snapshot.get("constraints", []):
            kind = constraint.get("type")
            if kind not in policy["allowed_constraints"]:
                errors.append({"code": "SCHEDULE_CONSTRAINT_NOT_GOVERNED", "target": constraint.get("external_id")})
            if kind in {"Mandatory Start", "Mandatory Finish"}:
                (errors if thresholds["hard_constraint"] == "BLOCK" else warnings).append(
                    {"code": "SCHEDULE_HARD_CONSTRAINT", "target": constraint.get("external_id")}
                )
        return {
            "errors": errors,
            "warnings": warnings,
            "can_accept": not errors,
            "quality_is_not_cpm": True,
            "metrics": {
                "activities": len(activities),
                "wbs": len(snapshot.get("wbs", [])),
                "open_ends": len(open_ends),
                "missing_calendars": len(missing_calendar),
                "missing_mappings": len(missing_mapping),
                "invalid_mappings": len(invalid_mappings),
                "unresolved_external_links": len(unresolved),
            },
            "near_critical_threshold": deepcopy(policy["near_critical_threshold"]),
        }

    def transition_version(self, workspace_id, identity, action, payload, expected, key):
        duty = "review" if action == "reject" else action
        self._ready(workspace_id, duty)

        def apply():
            _, profile, _ = self._ready(workspace_id, duty)
            row = self._get(ScheduleVersion, workspace_id, identity, lock=True)
            self._version(row.version, expected)
            if action == "reject":
                if row.status not in {"DRAFT", "STAGED", "VALIDATED", "UNDER_REVIEW"}:
                    self._error(409, "SCHEDULE_REJECTION_TRANSITION_INVALID")
                row.status = "REJECTED"
                event = "SCHEDULE_VERSION_REJECTED"
            else:
                allowed, target = {
                    "validate": ({"DRAFT", "STAGED", "VALIDATED"}, "VALIDATED"),
                    "review": ({"VALIDATED"}, "UNDER_REVIEW"),
                    "accept": ({"UNDER_REVIEW"}, "ACCEPTED_CURRENT"),
                }[action]
                if row.status not in allowed:
                    self._error(409, "SCHEDULE_VERSION_TRANSITION_INVALID")
                health = self._health(row, profile)
                if health["errors"]:
                    raise HTTPException(409, detail={"code": "SCHEDULE_VALIDATION_BLOCKED", "errors": health["errors"]})
                row.health_json = health
                row.validation_json = {
                    "errors": [],
                    "warnings": health["warnings"],
                    "can_accept": True,
                    "configuration_hash": profile.content_hash,
                }
                if action == "accept":
                    if profile.content_json["separation_of_duties"]["importer_cannot_accept"] and self.actor_id in {
                        row.created_by,
                        row.last_material_editor,
                    }:
                        self._error(403, "SCHEDULE_ACCEPTANCE_SOD")
                    register = self._get(ScheduleRegister, workspace_id, row.register_id, lock=True)
                    if register.current_version_id != row.import_manifest_json["expected_current_version_id"]:
                        self._error(409, "SCHEDULE_CURRENT_CHANGED_CREATE_SUCCESSOR")
                    if register.current_version_id:
                        old = self._get(ScheduleVersion, workspace_id, register.current_version_id, lock=True)
                        old.status, old.version = "SUPERSEDED", old.version + 1
                    row.accepted_by, row.accepted_at = self.actor_id, utc_now()
                    row.accepted_mapping_hash = _hash(self._effective_mappings(row))
                    register.current_version_id, register.version = row.id, register.version + 1
                if action == "review":
                    row.reviewed_by, row.reviewed_at = self.actor_id, utc_now()
                row.status = target
                event = {
                    "validate": "SCHEDULE_IMPORT_VALIDATED",
                    "review": "SCHEDULE_VERSION_REVIEWED",
                    "accept": "SCHEDULE_VERSION_ACCEPTED",
                }[action]
            row.version += 1
            self.db.flush()
            self._event(event, row.id, {"project_workspace_id": workspace_id, "reason": payload.reason})
            return self._version_out(row)

        return self._command(
            "schedule.version." + action,
            key,
            {"project": workspace_id, "id": identity, "expected": expected, **payload.model_dump(mode="json")},
            apply,
        )

    def set_mapping(self, workspace_id, identity, payload, expected, key):
        self._ready(workspace_id, "mapping.edit")

        def apply():
            _, profile, baseline = self._ready(workspace_id, "mapping.edit")
            version = self._get(ScheduleVersion, workspace_id, identity, lock=True)
            self._version(version.version, expected)
            if version.status not in {"DRAFT", "STAGED", "VALIDATED", "UNDER_REVIEW"}:
                self._error(409, "SCHEDULE_ACCEPTED_MAPPING_IMMUTABLE_CREATE_SUCCESSOR")
            old = next(
                (
                    row
                    for row in self._effective_mappings(version, include_removed=True)
                    if row["target_kind"] == payload.target_kind
                    and row["target_external_id"] == payload.target_external_id
                ),
                None,
            )
            if payload.action == "REMOVE":
                if old is None or old["status"] == "REMOVED" or payload.plan_item_ids or payload.scope_item_ids:
                    self._error(422, "SCHEDULE_MAPPING_REMOVAL_INVALID")
                lineage = deepcopy(old["lineage_json"])
            else:
                if not any(
                    str(row.get("external_id")) == payload.target_external_id
                    for row in version.snapshot_json.get("wbs" if payload.target_kind == "WBS" else "activities", [])
                ):
                    self._error(422, "SCHEDULE_MAPPING_TARGET_NOT_FOUND")
                if not payload.plan_item_ids and not payload.scope_item_ids:
                    self._error(422, "SCHEDULE_MAPPING_REFERENCES_REQUIRED")
                if len(set(payload.plan_item_ids)) != len(payload.plan_item_ids) or len(
                    set(payload.scope_item_ids)
                ) != len(payload.scope_item_ids):
                    self._error(422, "SCHEDULE_MAPPING_DUPLICATE_REFERENCE")
                current_scope = {row["id"] for row in baseline.snapshot_json["items"]}
                plans, resolved_scope = [], set()
                for plan_id in payload.plan_item_ids:
                    plan = self._get(PlanItem, workspace_id, plan_id)
                    if (
                        plan.status == "SUPERSEDED"
                        or profile.content_json["mapping_policy"]["published_plan_required"]
                        and plan.status != "PUBLISHED"
                    ):
                        self._error(409, "SCHEDULE_PUBLISHED_CURRENT_PLAN_REQUIRED")
                    links = self.db.scalars(
                        select(PlanItemScopeLink).where(
                            PlanItemScopeLink.tenant_id == self.tenant_id,
                            PlanItemScopeLink.project_workspace_id == workspace_id,
                            PlanItemScopeLink.plan_item_id == plan.id,
                        )
                    ).all()
                    if any(link.scope_item_id not in current_scope for link in links):
                        self._error(409, "SCHEDULE_PLAN_SCOPE_STALE")
                    resolved_scope.update(link.scope_item_id for link in links)
                    plans.append({"id": plan.id, "version": plan.version, "content_hash": plan.content_hash})
                if payload.scope_item_ids and not profile.content_json["mapping_policy"]["allow_direct_scope"]:
                    self._error(422, "SCHEDULE_DIRECT_SCOPE_MAPPING_DISABLED")
                if any(identity not in current_scope for identity in payload.scope_item_ids):
                    self._error(409, "SCHEDULE_CURRENT_APPROVED_SCOPE_REQUIRED")
                for scope_id in payload.scope_item_ids:
                    self._get(ScopeItem, workspace_id, scope_id)
                if payload.plan_item_ids and not set(payload.scope_item_ids) <= resolved_scope:
                    self._error(422, "SCHEDULE_DIRECT_SCOPE_CONTRADICTS_PLAN")
                resolved_scope.update(payload.scope_item_ids)
                derived = [
                    self._out(row)
                    for row in self._rows(DerivedModelVersion, workspace_id)
                    if any(
                        member.get("plan_item_id") in payload.plan_item_ids
                        for member in row.snapshot_json.get("memberships", [])
                    )
                ]
                lineage = {
                    "scope_baseline_id": baseline.id,
                    "resolved_scope_item_ids": sorted(resolved_scope),
                    "plan_items": plans,
                    "scope_natures": {
                        str(row["id"]): row["scope_nature"]
                        for row in baseline.snapshot_json["items"]
                        if row["id"] in resolved_scope
                    },
                    "derived_models": [{"id": row["id"], "content_hash": row["content_hash"]} for row in derived],
                    "future_4d": "NOT_ACTIVE",
                }
            row = ScheduleMapping(
                **self._base(workspace_id),
                schedule_version_id=version.id,
                target_kind=payload.target_kind,
                target_external_id=payload.target_external_id,
                revision=(old["revision"] + 1) if old else 1,
                status="REMOVED" if payload.action == "REMOVE" else "VALID",
                plan_item_ids=payload.plan_item_ids,
                scope_item_ids=payload.scope_item_ids,
                lineage_json=lineage,
                reason=payload.reason,
            )
            self.db.add(row)
            version.version, version.status, version.last_material_editor = version.version + 1, "STAGED", self.actor_id
            version.reviewed_by, version.reviewed_at = None, None
            self.db.flush()
            self._event(
                "SCHEDULE_MAPPING_CHANGED",
                row.id,
                {"project_workspace_id": workspace_id, "version_id": version.id, "reason": payload.reason},
            )
            return self._out(row) | {"schedule_version": self._version_out(version), "version": version.version}

        return self._command(
            "schedule.mapping.set",
            key,
            {"project": workspace_id, "id": identity, "expected": expected, **payload.model_dump(mode="json")},
            apply,
        )

    def prepare_baseline(self, workspace_id, identity, payload, expected, key):
        self._ready(workspace_id, "baseline.prepare")

        def apply():
            _, profile, _ = self._ready(workspace_id, "baseline.prepare")
            version = self._get(ScheduleVersion, workspace_id, identity, lock=True)
            self._version(version.version, expected)
            if version.accepted_at is None or version.status not in {"ACCEPTED_CURRENT", "SUPERSEDED"}:
                self._error(409, "SCHEDULE_ACCEPTED_VERSION_REQUIRED_FOR_BASELINE")
            if payload.baseline_type not in profile.content_json["baseline_types"]:
                self._error(422, "SCHEDULE_BASELINE_TYPE_NOT_GOVERNED")
            if self._health(version, profile)["errors"]:
                self._error(409, "SCHEDULE_BASELINE_MAPPING_NOT_CURRENT")
            register = self._get(ScheduleRegister, workspace_id, version.register_id)
            previous = self.db.scalars(
                select(ScheduleBaseline)
                .where(
                    ScheduleBaseline.tenant_id == self.tenant_id,
                    ScheduleBaseline.register_id == register.id,
                    ScheduleBaseline.status == "APPROVED_BASELINE",
                )
                .order_by(ScheduleBaseline.revision.desc())
            ).first()
            if (previous.id if previous else None) != payload.previous_baseline_id:
                self._error(409, "SCHEDULE_SUCCESSOR_BASELINE_REFERENCE_REQUIRED")
            if payload.baseline_type == "ORIGINAL" and previous is not None:
                self._error(409, "SCHEDULE_ORIGINAL_BASELINE_ALREADY_EXISTS")
            revision = (
                self.db.scalar(
                    select(func.max(ScheduleBaseline.revision)).where(ScheduleBaseline.register_id == register.id)
                )
                or 0
            ) + 1
            snapshot = {
                "schedule_version_id": version.id,
                "schedule_content_hash": version.content_hash,
                "schedule_snapshot": deepcopy(version.snapshot_json),
                "mappings": self._effective_mappings(version),
                "previous_baseline_id": payload.previous_baseline_id,
                "last_material_editor": version.last_material_editor,
                "register_baseline_version_id": register.baseline_version_id,
            }
            row = ScheduleBaseline(
                **self._base(workspace_id),
                register_id=register.id,
                schedule_version_id=version.id,
                baseline_type=payload.baseline_type,
                revision=revision,
                previous_baseline_id=payload.previous_baseline_id,
                snapshot_json=snapshot,
                content_hash=_hash(snapshot),
                configuration_id=profile.id,
                reason=payload.reason,
            )
            self.db.add(row)
            self.db.flush()
            self._event(
                "SCHEDULE_BASELINE_CANDIDATE_CREATED",
                row.id,
                {"project_workspace_id": workspace_id, "schedule_version_id": version.id},
            )
            return self._out(row)

        return self._command(
            "schedule.baseline.prepare",
            key,
            {"project": workspace_id, "id": identity, "expected": expected, **payload.model_dump(mode="json")},
            apply,
        )

    def transition_baseline(self, workspace_id, identity, action, payload, expected, key):
        self._ready(workspace_id, "baseline." + action)

        def apply():
            self._ready(workspace_id, "baseline." + action)
            row = self._get(ScheduleBaseline, workspace_id, identity, lock=True)
            self._version(row.version, expected)
            before, after = {
                "submit": ("BASELINE_CANDIDATE", "SUBMITTED"),
                "review": ("SUBMITTED", "UNDER_REVIEW"),
                "approve": ("UNDER_REVIEW", "APPROVED_BASELINE"),
            }[action]
            if row.status != before:
                self._error(409, "SCHEDULE_BASELINE_TRANSITION_INVALID")
            profile = self._profile(row.configuration_id)
            version = self._get(ScheduleVersion, workspace_id, row.schedule_version_id)
            register = self._get(ScheduleRegister, workspace_id, row.register_id, lock=True)
            if (
                self._health(version, profile)["errors"]
                or _hash(self._effective_mappings(version)) != version.accepted_mapping_hash
            ):
                self._error(409, "SCHEDULE_BASELINE_SOURCE_STALE")
            if action == "approve":
                latest_approved = self.db.scalar(
                    select(ScheduleBaseline.id)
                    .where(
                        ScheduleBaseline.tenant_id == self.tenant_id,
                        ScheduleBaseline.register_id == register.id,
                        ScheduleBaseline.status == "APPROVED_BASELINE",
                    )
                    .order_by(ScheduleBaseline.revision.desc())
                    .limit(1)
                )
                if latest_approved != row.previous_baseline_id:
                    self._error(409, "SCHEDULE_BASELINE_PREDECESSOR_CHANGED_REPREPARE")
                if register.baseline_version_id != row.snapshot_json["register_baseline_version_id"]:
                    self._error(409, "SCHEDULE_BASELINE_POINTER_CHANGED_REPREPARE")
                if profile.content_json["separation_of_duties"][
                    "baseline_preparer_cannot_approve"
                ] and self.actor_id in {row.created_by, row.snapshot_json["last_material_editor"]}:
                    self._error(403, "SCHEDULE_BASELINE_APPROVAL_SOD")
                row.approved_by, row.approved_at = self.actor_id, utc_now()
                register.baseline_version_id, register.version = version.id, register.version + 1
            if action == "review":
                row.reviewed_by = self.actor_id
            row.status, row.version = after, row.version + 1
            self.db.flush()
            self._event(
                {
                    "submit": "SCHEDULE_BASELINE_SUBMITTED",
                    "review": "SCHEDULE_BASELINE_REVIEWED",
                    "approve": "SCHEDULE_BASELINE_APPROVED",
                }[action],
                row.id,
                {"project_workspace_id": workspace_id, "reason": payload.reason},
            )
            return self._out(row)

        return self._command(
            "schedule.baseline." + action,
            key,
            {"project": workspace_id, "id": identity, "expected": expected, **payload.model_dump(mode="json")},
            apply,
        )

    def export_version(self, workspace_id, identity, payload, expected, key):
        from app.modules.schedule_foundation.exchange import export_schedule_xml

        self._ready(workspace_id, "export")

        def apply():
            _, profile, _ = self._ready(workspace_id, "export")
            row = self._get(ScheduleVersion, workspace_id, identity)
            self._version(row.version, expected)
            if payload.format not in profile.content_json["supported_exchange"]["exports"] or payload.format != "XML":
                self._error(422, "SCHEDULE_XER_EXPORT_NOT_SUPPORTED")
            baseline = None
            if payload.purpose == "BASELINE":
                if payload.baseline_id is None:
                    self._error(422, "SCHEDULE_EXPLICIT_BASELINE_REFERENCE_REQUIRED")
                baseline = self._get(ScheduleBaseline, workspace_id, payload.baseline_id)
                if baseline.status != "APPROVED_BASELINE" or baseline.schedule_version_id != row.id:
                    self._error(409, "SCHEDULE_APPROVED_BASELINE_MISMATCH")
            elif payload.baseline_id is not None:
                self._error(422, "SCHEDULE_EXPORT_BASELINE_PURPOSE_REQUIRED")
            if payload.purpose == "CURRENT" and row.status != "ACCEPTED_CURRENT":
                self._error(409, "SCHEDULE_ACCEPTED_CURRENT_REQUIRED")
            if payload.purpose == "CURRENT":
                health = self._health(row, profile)
                if health["errors"]:
                    raise HTTPException(
                        409,
                        detail={"code": "SCHEDULE_CURRENT_EXPORT_REQUIRES_VALID_LINEAGE", "errors": health["errors"]},
                    )
            try:
                content = export_schedule_xml(
                    row.snapshot_json,
                    baseline_reference={"id": baseline.id, "content_hash": baseline.content_hash} if baseline else None,
                )
            except (ScheduleParseError, ValueError) as error:
                raise HTTPException(
                    422, detail={"code": "SCHEDULE_EXPORT_SUBSET_UNSUPPORTED", "message": str(error)[:500]}
                ) from error
            result = ScheduleExportManifest(
                **self._base(workspace_id),
                schedule_version_id=row.id,
                baseline_id=baseline.id if baseline else None,
                purpose=payload.purpose,
                source_file_name=f"schedule-{row.register_id}-v{row.revision}.xml",
                source_hash=sha256(content).hexdigest(),
                source_content=content,
                manifest_json={
                    "format": "P6_XML",
                    "supported_subset": "P6_API_BUSINESS_OBJECTS_XML_LIMITED",
                    "source_version_hash": row.content_hash,
                    "source_import_hash": row.source_hash,
                    "data_date": row.data_date,
                    "baseline_reference": {"id": baseline.id, "hash": baseline.content_hash} if baseline else None,
                    "native_baseline_transport": False,
                    "full_p6_parity": False,
                    "p6_application_roundtrip_proven": False,
                    "cpm_calculation_performed": False,
                    "manual_exchange_only": True,
                },
                reason=payload.reason,
            )
            self.db.add(result)
            self.db.flush()
            self._event(
                "SCHEDULE_EXPORT_GENERATED",
                result.id,
                {"project_workspace_id": workspace_id, "source_hash": result.source_hash},
            )
            return self._out(result)

        return self._command(
            "schedule.export",
            key,
            {"project": workspace_id, "id": identity, "expected": expected, **payload.model_dump(mode="json")},
            apply,
        )

    def export_file(self, workspace_id, identity):
        self._permission("read", self._project(workspace_id))
        return self._get(ScheduleExportManifest, workspace_id, identity)

    def associate_period(self, workspace_id, identity, payload, expected, key):
        self._ready(workspace_id, "period.associate")

        def apply():
            self._ready(workspace_id, "period.associate")
            version = self._get(ScheduleVersion, workspace_id, identity)
            self._version(version.version, expected)
            if version.accepted_at is None:
                self._error(409, "SCHEDULE_ACCEPTED_VERSION_REQUIRED")
            period = self._get(ProjectControlsPeriod, workspace_id, payload.period_id, lock=True)
            if period.status not in {"OPEN", "REVIEW"}:
                self._error(409, "SCHEDULE_PERIOD_NOT_OPEN_FOR_ASSOCIATION")
            snapshot = {
                "schedule_data_date": version.data_date,
                "schedule_content_hash": version.content_hash,
                "period_id": period.id,
                "period_version": period.version,
                "period_cutoff_at": period.cutoff_at.isoformat(),
                "period_timezone": period.timezone,
                "data_date_is_not_cutoff": True,
            }
            row = SchedulePeriodAssociation(
                **self._base(workspace_id),
                schedule_version_id=version.id,
                period_id=period.id,
                snapshot_json=snapshot,
                reason=payload.reason,
            )
            self.db.add(row)
            self.db.flush()
            self._event("SCHEDULE_PERIOD_ASSOCIATED", row.id, {"project_workspace_id": workspace_id, **snapshot})
            return self._out(row)

        return self._command(
            "schedule.period.associate",
            key,
            {"project": workspace_id, "id": identity, "expected": expected, **payload.model_dump(mode="json")},
            apply,
        )

    def version_query(self, workspace_id, identity, field):
        self._permission("read", self._project(workspace_id))
        row = self._get(ScheduleVersion, workspace_id, identity)
        profile = self._schedule_profile(self._project(workspace_id)) or self._profile(row.configuration_id)
        if field == "health":
            return self._health(row, profile)
        if field == "mappings":
            items = self._effective_mappings(row)
        else:
            items = deepcopy(row.snapshot_json.get(field, []))
        if field == "activities":
            threshold = profile.content_json["near_critical_threshold"]
            for item in items:
                value = item.get("total_float")
                item["near_critical"] = (
                    "UNKNOWN"
                    if value is None or item.get("float_unit") != threshold["unit"]
                    else Decimal(str(value)) <= Decimal(str(threshold["value"]))
                )
                item["criticality_authority"] = "P6_IMPORTED" if item.get("critical") is not None else "UNKNOWN"
        if field != "mappings":
            for item in items:
                item["source_schedule_version"] = row.id
                item["source_schedule_revision"] = row.revision
                item["external_p6_identity"] = item.get("external_id")
        return {"items": items, "total": len(items), "schedule_version_id": identity, "version": row.version}

    def look_ahead(self, workspace_id, identity, horizon_days=None):
        self._permission("read", self._project(workspace_id))
        row = self._get(ScheduleVersion, workspace_id, identity)
        profile = self._schedule_profile(self._project(workspace_id)) or self._profile(row.configuration_id)
        days = horizon_days or profile.content_json["lookahead_default_days"]
        if not 1 <= days <= 366:
            self._error(422, "SCHEDULE_LOOKAHEAD_HORIZON_INVALID")
        try:
            start = self._instant(row.data_date)
        except (TypeError, ValueError) as error:
            raise HTTPException(409, detail={"code": "SCHEDULE_DATA_DATE_INVALID"}) from error
        if start is None:
            self._error(409, "SCHEDULE_DATA_DATE_REQUIRED")
        end = start + timedelta(days=days)
        mappings = self._effective_mappings(row)
        result = []
        for activity in self.version_query(workspace_id, identity, "activities")["items"]:
            if activity.get("actual_finish"):
                continue
            try:
                planned = self._instant(activity.get("planned_start") or activity.get("start"))
            except (TypeError, ValueError) as error:
                raise HTTPException(409, detail={"code": "SCHEDULE_LOOKAHEAD_SOURCE_DATES_INVALID"}) from error
            if not activity.get("actual_start") and (planned is None or not start <= planned <= end):
                continue
            linked = [
                item
                for item in mappings
                if item["target_kind"] == "ACTIVITY" and item["target_external_id"] == str(activity.get("external_id"))
            ]
            result.append({**activity, "mappings": linked, "future_constraints_issues_references": []})
        return {
            "items": result,
            "data_date": row.data_date,
            "horizon_days": days,
            "query_contract_only": True,
            "cpm_calculation_performed": False,
        }

    def _profile(self, identity, *, lock=False):
        statement = select(AdminConfiguration).where(
            AdminConfiguration.tenant_id == self.tenant_id,
            AdminConfiguration.kind == PROFILE_KIND,
            AdminConfiguration.id == identity,
        )
        row = self.db.scalar(
            statement.with_for_update().execution_options(populate_existing=True) if lock else statement
        )
        if row is None:
            self._error(404, "SCHEDULE_PROFILE_NOT_FOUND")
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
            if set(content) != set(DEFAULT_PROFILE):
                raise ValueError("configuration keys")
            for field in ("schedule_types", "baseline_types", "allowed_constraints"):
                if (
                    not isinstance(content[field], list)
                    or not content[field]
                    or any(
                        not isinstance(value, str) or not value.strip() or len(value) > 100 for value in content[field]
                    )
                    or len(set(content[field])) != len(content[field])
                ):
                    raise ValueError(field)
            if not set(content["allowed_constraints"]) <= set(DEFAULT_PROFILE["allowed_constraints"]):
                raise ValueError("unsupported constraint subset")
            if (
                content["calendar_handling"] != DEFAULT_PROFILE["calendar_handling"]
                or content["supported_exchange"] != DEFAULT_PROFILE["supported_exchange"]
                or content["baseline_workflow"] != DEFAULT_PROFILE["baseline_workflow"]
            ):
                raise ValueError("unsupported authority/subset/workflow")
            threshold = content["near_critical_threshold"]
            if (
                set(threshold) != {"unit", "value"}
                or type(threshold["value"]) is bool
                or threshold["unit"] != "HOUR"
                or not Decimal(str(threshold["value"])).is_finite()
                or Decimal(str(threshold["value"])) < 0
            ):
                raise ValueError("near critical")
            quality = content["quality_thresholds"]
            if set(quality) != set(DEFAULT_PROFILE["quality_thresholds"]):
                raise ValueError("quality keys")
            for field in ("long_duration_hours", "max_lag_hours"):
                if (
                    type(quality[field]) is bool
                    or not Decimal(str(quality[field])).is_finite()
                    or Decimal(str(quality[field])) < 0
                ):
                    raise ValueError(field)
            if quality["max_open_ends"] is not None and (
                type(quality["max_open_ends"]) is not int or quality["max_open_ends"] < 0
            ):
                raise ValueError("open ends")
            if (
                quality["negative_lag"] not in {"WARN", "BLOCK"}
                or quality["hard_constraint"] not in {"WARN", "BLOCK"}
                or quality["external_links"] not in {"WARN", "BLOCK_UNRESOLVED"}
            ):
                raise ValueError("quality policy")
            for field in ("mapping_policy", "separation_of_duties"):
                if set(content[field]) != set(DEFAULT_PROFILE[field]) or any(
                    type(value) is not bool for value in content[field].values()
                ):
                    raise ValueError(field)
            open_end_policy = content["open_end_policy"]
            if (
                set(open_end_policy) != {"authorized_milestone_types"}
                or not isinstance(open_end_policy["authorized_milestone_types"], list)
                or any(
                    not isinstance(value, str) or "Milestone" not in value
                    for value in open_end_policy["authorized_milestone_types"]
                )
            ):
                raise ValueError("milestone open-end exemptions")
            if not isinstance(content["activity_code_mapping_rules"], dict):
                raise ValueError("activity code mapping rules")
            if (
                type(content["inherit_to_descendants"]) is not bool
                or type(content["allow_multiple_streams"]) is not bool
                or type(content["lookahead_default_days"]) is not int
                or not 1 <= content["lookahead_default_days"] <= 366
            ):
                raise ValueError("streams/lookahead")
            scope = content["scope"]
            if set(scope) != {"type", "workspace_id"}:
                raise ValueError("scope keys")
            if scope["type"] == "workspace":
                if type(scope["workspace_id"]) is not int or scope["workspace_id"] < 1:
                    raise ValueError("workspace identity")
                self._project(scope["workspace_id"])
            elif scope["type"] != "tenant" or scope.get("workspace_id") is not None:
                raise ValueError("scope")
            start, end = self._instant(content.get("effective_from")), self._instant(content.get("effective_to"))
            if start and end and end <= start:
                raise ValueError("window")
        except (KeyError, TypeError, ValueError, InvalidOperation) as error:
            raise HTTPException(422, detail={"code": "SCHEDULE_PROFILE_INVALID"}) from error

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
                self._error(409, "SCHEDULE_PROFILE_CODE_EXISTS")
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
            self._event("SCHEDULE_PROFILE_CREATED", row.id, {"hash": row.content_hash})
            return self._profile_out(row)

        return self._command("schedule.profile.create", key, payload.model_dump(mode="json"), apply)

    def update_profile(self, identity, payload, expected, key):
        self._permission("admin.configure")

        def apply():
            row = self._profile(identity, lock=True)
            self._version(row.version, expected)
            if row.status != "draft":
                self._error(409, "SCHEDULE_PROFILE_PUBLISHED_IMMUTABLE")
            self._validate_profile(payload.content_json)
            row.name, row.content_json, row.content_hash = (
                payload.name,
                deepcopy(payload.content_json),
                _hash(payload.content_json),
            )
            row.version, row.updated_at = row.version + 1, utc_now()
            self.db.flush()
            self._event("SCHEDULE_PROFILE_UPDATED", row.id, {"version": row.version})
            return self._profile_out(row)

        return self._command(
            "schedule.profile.update",
            key,
            {"id": identity, "expected": expected, **payload.model_dump(mode="json")},
            apply,
        )

    def publish_profile(self, identity, payload, expected, key):
        self._permission("admin.publish")

        def apply():
            row = self._profile(identity, lock=True)
            self._version(row.version, expected)
            if row.status != "draft":
                self._error(409, "SCHEDULE_PROFILE_PUBLISHED_IMMUTABLE")
            self._validate_profile(row.content_json)
            editor = row.created_by_user_id
            if row.version > 1:
                receipt = self.db.scalar(
                    select(OperationalContextCommand).where(
                        OperationalContextCommand.tenant_id == self.tenant_id,
                        OperationalContextCommand.command_type == "schedule.profile.update",
                        OperationalContextCommand.result_json["id"].as_integer() == row.id,
                        OperationalContextCommand.result_json["version"].as_integer() == row.version,
                    )
                )
                if receipt is None or receipt.result_json.get("content_hash") != row.content_hash:
                    self._error(409, "SCHEDULE_PROFILE_EDITOR_PROVENANCE_REQUIRED")
                editor = receipt.actor_id
            if row.content_json["separation_of_duties"]["author_cannot_publish"] and self.actor_id in {
                row.created_by_user_id,
                editor,
            }:
                self._error(403, "SCHEDULE_PROFILE_PUBLICATION_SOD")
            row.status, row.published_at, row.version = "published", utc_now(), row.version + 1
            self.db.flush()
            self._event("SCHEDULE_PROFILE_PUBLISHED", row.id, {"hash": row.content_hash, "reason": payload.reason})
            return self._profile_out(row)

        return self._command(
            "schedule.profile.publish",
            key,
            {"id": identity, "expected": expected, **payload.model_dump(mode="json")},
            apply,
        )

    def successor_profile(self, identity, payload, expected, key):
        self._permission("admin.configure")

        def apply():
            old = self._profile(identity, lock=True)
            self._version(old.version, expected)
            if old.status != "published":
                self._error(409, "PUBLISHED_SCHEDULE_PROFILE_REQUIRED")
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
            self._event("SCHEDULE_PROFILE_SUCCESSOR", row.id, {"predecessor_id": old.id})
            return self._profile_out(row)

        return self._command(
            "schedule.profile.successor",
            key,
            {"id": identity, "expected": expected, **payload.model_dump(mode="json")},
            apply,
        )
