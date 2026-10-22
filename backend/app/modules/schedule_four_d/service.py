"""Version-keyed, source-hash-aware 4D projections with zero business writes on GET."""

from copy import deepcopy

from fastapi import HTTPException
from sqlalchemy import event, inspect, select

from app.core.time import utc_now
from app.domain.models import AdminConfiguration, SecurityEvent
from app.modules.basic_data.service import _hash
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.operational_context.models import OperationalContextCommand
from app.modules.schedule_foundation.models import (
    ScheduleBaseline,
    ScheduleMapping,
    SchedulePeriodAssociation,
    ScheduleRegister,
    ScheduleVersion,
)
from app.modules.schedule_four_d.state import (
    activity_dates,
    compare_states,
    instant,
    near_critical,
    resolve_state,
)
from app.modules.scope_foundation.models import (
    DerivedModelVersion,
    PlanItem,
    PlanItemModelLink,
    PlanItemScopeLink,
    ScopeBaseline,
    ScopeBimObject,
    ScopeItem,
    ScopeModelMapping,
    ScopeModelVersion,
)
from app.modules.scope_foundation.service import ScopeFoundationService

PROFILE_KIND = "four_d_profile"
SEMANTICS = {
    "INSTALL": ["FUTURE_NOT_INSTALLED", "INSTALLATION", "INSTALLED"],
    "REMOVE": ["EXISTING", "REMOVAL", "REMOVED"],
    "TEMPORARY": [
        "ABSENT_BEFORE_INSTALL",
        "TEMPORARY_INSTALLATION",
        "TEMPORARY_IN_USE",
        "TEMPORARY_REMOVAL",
        "ABSENT_AFTER_REMOVAL",
    ],
    "MAINTENANCE": ["EXISTING_IN_SERVICE", "MAINTENANCE_INTERVENTION", "RESTORED_IN_SERVICE"],
}
DEFAULT_PROFILE = {
    "scope": {"type": "tenant", "workspace_id": None},
    "inherit_to_descendants": True,
    "state_rules": deepcopy(SEMANTICS),
    "display": {
        "NOT_STARTED": {"color": "#94a3b8", "opacity": 0.2},
        "IN_PROGRESS": {"color": "#0284c7", "opacity": 1.0},
        "COMPLETED": {"color": "#16a34a", "opacity": 1.0},
        "DELAYED": {"color": "#dc2626", "opacity": 1.0},
        "CRITICAL": {"color": "#be123c", "opacity": 1.0},
        "NEAR_CRITICAL": {"color": "#d97706", "opacity": 1.0},
        "BLOCKED_BY_READINESS": {"color": "#7c3aed", "opacity": 1.0},
        "REMOVED": {"color": "#64748b", "opacity": 0.0},
        "TEMPORARY": {"color": "#eab308", "opacity": 0.85},
        "MAINTENANCE": {"color": "#0891b2", "opacity": 1.0},
        "UNKNOWN": {"color": "#6b7280", "opacity": 1.0},
    },
    "mapping_completeness_policy": "FLAG_AND_RENDER_UNKNOWN",
    "temporary_phase_policy": "EXPLICIT_INSTALL_USE_REMOVE",
    "allow_direct_scope_mapping": True,
    "separation_of_duties": {"author_cannot_publish": True},
}


@event.listens_for(AdminConfiguration, "before_update")
@event.listens_for(AdminConfiguration, "before_delete")
def _immutable_profile(_mapper, _connection, row):
    if row.kind == PROFILE_KIND:
        history = inspect(row).attrs.status.history
        if (history.deleted[0] if history.deleted else row.status) == "published":
            raise ValueError("Published 4D configuration is immutable; create successor")


class FourDService(ScopeFoundationService):
    def _permission(self, action, workspace=None):
        if self.access_context is None:
            return
        if action not in self._permission_contexts:
            self._permission_contexts[action] = require_enterprise_permission(
                self.db, self.tenant_id, self.actor_id, f"four_d.{action}", bootstrap=False
            )
        access = self._permission_contexts[action]
        if action.startswith("admin.") and not access.organization_wide:
            self._error(403, "FOUR_D_ADMIN_ORGANIZATION_SCOPE_REQUIRED")
        if workspace is not None:
            self._scope(workspace, access)

    def _event(self, action, target_id, metadata, *, outcome="success"):
        self.db.add(
            SecurityEvent(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                event_type=f"four_d.{action}",
                outcome=outcome,
                target_type="FourDConfiguration",
                target_id=target_id,
                metadata_json=deepcopy(metadata),
            )
        )

    def _configuration(self, project):
        candidates = []
        for row in self.db.scalars(
            select(AdminConfiguration).where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == PROFILE_KIND,
                AdminConfiguration.status == "published",
            )
        ):
            scope = row.content_json["scope"]
            if scope["type"] == "tenant":
                candidates.append((0, row))
            elif scope["workspace_id"] == project.id:
                candidates.append((100, row))
            elif row.content_json["inherit_to_descendants"] and scope["workspace_id"] in self._workspace_paths.get(
                project.id, []
            ):
                candidates.append((50, row))
        if not candidates:
            self._error(409, "PUBLISHED_FOUR_D_PROFILE_REQUIRED")
        depth = max(item[0] for item in candidates)
        top = [row for priority, row in candidates if priority == depth]
        if len({row.code for row in top}) != 1:
            self._error(409, "FOUR_D_PROFILE_AMBIGUOUS")
        return max(top, key=lambda row: row.revision)

    def _source(self, workspace_id, source, version_id, baseline_id):
        baseline = None
        if source == "BASELINE":
            if baseline_id is None:
                self._error(422, "FOUR_D_EXPLICIT_BASELINE_REQUIRED")
            baseline = self._get(ScheduleBaseline, workspace_id, baseline_id)
            if baseline.status != "APPROVED_BASELINE":
                self._error(409, "FOUR_D_APPROVED_BASELINE_REQUIRED")
            version = self._get(ScheduleVersion, workspace_id, baseline.schedule_version_id)
            if version_id is not None and version_id != version.id:
                self._error(422, "FOUR_D_SOURCE_REFERENCE_MISMATCH")
            snapshot = deepcopy(baseline.snapshot_json["schedule_snapshot"])
            mappings = deepcopy(baseline.snapshot_json["mappings"])
        elif source == "CURRENT":
            if baseline_id is not None:
                self._error(422, "FOUR_D_BASELINE_NOT_CURRENT")
            current = [row for row in self._rows(ScheduleVersion, workspace_id) if row.status == "ACCEPTED_CURRENT"]
            if version_id is None:
                if len(current) != 1:
                    self._error(409, "FOUR_D_EXPLICIT_CURRENT_REQUIRED")
                version = current[0]
            else:
                version = self._get(ScheduleVersion, workspace_id, version_id)
            register = self._get(ScheduleRegister, workspace_id, version.register_id)
            if (
                version.status != "ACCEPTED_CURRENT"
                or version.accepted_at is None
                or register.current_version_id != version.id
            ):
                self._error(409, "FOUR_D_ACCEPTED_CURRENT_REQUIRED")
            snapshot = deepcopy(version.snapshot_json)
            latest = {}
            for row in self._rows(ScheduleMapping, workspace_id):
                if row.schedule_version_id == version.id:
                    latest[(row.target_kind, row.target_external_id)] = self._out(row)
            mappings = [row for row in latest.values() if row["status"] != "REMOVED"]
        else:
            self._error(422, "FOUR_D_SOURCE_INVALID")
        register = self._get(ScheduleRegister, workspace_id, version.register_id)
        reference = {
            "kind": source,
            "schedule_version_id": version.id,
            "schedule_revision": version.revision,
            "register_id": register.id,
            "register_code": register.schedule_code,
            "timezone": register.timezone,
            "baseline_id": baseline.id if baseline else None,
            "baseline_revision": baseline.revision if baseline else None,
            "data_date": snapshot.get("project", {}).get("data_date") or version.data_date,
            "content_hash": baseline.content_hash if baseline else version.content_hash,
            "schedule_content_hash": version.content_hash,
            "current_reference": register.current_version_id,
        }
        approved = [
            row
            for row in self._rows(ScheduleBaseline, workspace_id)
            if row.register_id == register.id and row.status == "APPROVED_BASELINE"
        ]
        reference["approved_baseline_reference"] = baseline.id if baseline else approved[-1].id if approved else None
        return version, snapshot, mappings, reference

    def model(self, workspace_id, *, source="CURRENT", version_id=None, baseline_id=None, at=None, filters=None):
        project = self._project(workspace_id)
        self._permission("read", project)
        profile = self._configuration(project)
        version, snapshot, mappings, reference = self._source(workspace_id, source, version_id, baseline_id)
        selected = at or reference["data_date"]
        try:
            if instant(selected, reference["timezone"]) is None:
                raise ValueError("missing")
        except (ValueError, TypeError) as error:
            raise HTTPException(422, detail={"code": "FOUR_D_SELECTED_DATE_INVALID"}) from error
        scope_baseline = self._get(ScopeBaseline, workspace_id, version.scope_baseline_id)
        scope_ids = {row["id"] for row in scope_baseline.snapshot_json["items"]}
        scopes = {row.id: row for row in self._rows(ScopeItem, workspace_id) if row.id in scope_ids}
        plans = {row.id: row for row in self._rows(PlanItem, workspace_id) if row.status in {"PUBLISHED", "SUPERSEDED"}}
        links = self._rows(PlanItemScopeLink, workspace_id)
        model_links = self._rows(ScopeModelMapping, workspace_id)
        plan_model_links = self._rows(PlanItemModelLink, workspace_id)
        objects = {row.id: row for row in self._rows(ScopeBimObject, workspace_id)}
        models = {row.id: row for row in self._rows(ScopeModelVersion, workspace_id)}
        derived = self._rows(DerivedModelVersion, workspace_id)
        from app.modules.awp.service import AWPService

        awp = AWPService(self.db, self.tenant_id, self.actor_id, self.access_context).read_model(workspace_id)
        package_rows = {row["id"]: row for row in awp["packages"]}
        cwas = {row["id"]: row for row in awp["cwas"]}
        package_mappings = awp["effective_mappings"]
        mapped_packages = {
            row["work_package_id"]
            for row in package_mappings
            if row["target_kind"] == "ACTIVITY" and row["schedule_version_id"] == version.id
        }
        mapped_plans = {identity for mapping in mappings for identity in mapping["plan_item_ids"]}
        mapped_plans.update(
            row["target_id"]
            for row in package_mappings
            if row["target_kind"] == "PLAN" and row["work_package_id"] in mapped_packages
        )
        activities = {str(row["external_id"]): row for row in snapshot.get("activities", [])}
        wbs = {str(row["external_id"]): row for row in snapshot.get("wbs", [])}
        schedule_profile = self.db.scalar(
            select(AdminConfiguration).where(
                AdminConfiguration.id == version.configuration_id,
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == "schedule_profile",
                AdminConfiguration.status == "published",
            )
        )
        if schedule_profile is None:
            self._error(409, "FOUR_D_SCHEDULE_CONFIGURATION_INVALID")
        threshold = schedule_profile.content_json["near_critical_threshold"]
        items = []
        for scope in scopes.values():
            scope_plans = sorted(
                {
                    link.plan_item_id
                    for link in links
                    if link.scope_item_id == scope.id
                    and link.plan_item_id in plans
                    and link.plan_item_id in mapped_plans
                }
            )
            for plan_id in scope_plans or [None]:
                plan = plans.get(plan_id)
                members = {
                    row["work_package_id"]
                    for row in package_mappings
                    if row["target_kind"] == "SCOPE"
                    and row["target_id"] == scope.id
                    or row["target_kind"] == "PLAN"
                    and row["target_id"] == plan_id
                    and plan_id is not None
                }
                packages = [package_rows[identity] for identity in sorted(members) if identity in package_rows]
                activity_refs = []
                issues = []
                for mapping in mappings:
                    if mapping["target_kind"] != "ACTIVITY":
                        continue
                    direct_scope = scope.id in mapping["scope_item_ids"]
                    direct_allowed = (
                        profile.content_json["allow_direct_scope_mapping"]
                        and schedule_profile.content_json["mapping_policy"]["allow_direct_scope"]
                    )
                    if direct_scope and not direct_allowed:
                        issues.append("DIRECT_SCOPE_MAPPING_DISABLED")
                    if plan_id in mapping["plan_item_ids"] or direct_scope and direct_allowed:
                        if mapping["status"] != "VALID":
                            issues.append(f"SCHEDULE_MAPPING_{mapping['status']}")
                        else:
                            activity_refs.append((mapping["target_external_id"], "EXECUTE"))
                phased_refs = []
                for mapping in package_mappings:
                    if mapping["work_package_id"] in members and mapping["target_kind"] == "ACTIVITY":
                        if mapping["schedule_version_id"] != version.id:
                            # Other source-qualified memberships are valid history,
                            # not a current mapping. Only flag when no membership to
                            # this selected version exists for the same activity.
                            if not any(
                                candidate["work_package_id"] == mapping["work_package_id"]
                                and candidate["target_kind"] == "ACTIVITY"
                                and candidate["schedule_version_id"] == version.id
                                and candidate["activity_external_id"] == mapping["activity_external_id"]
                                for candidate in package_mappings
                            ):
                                issues.append(
                                    "PACKAGE_ACTIVITY_MAPPING_BROKEN"
                                    if str(mapping["activity_external_id"]) not in activities
                                    else "PACKAGE_ACTIVITY_VERSION_REVIEW_REQUIRED"
                                )
                        else:
                            phased_refs.append((mapping["activity_external_id"], mapping["phase"]))
                if scope.scope_nature == "TEMPORARY" and phased_refs:
                    activity_refs = phased_refs
                else:
                    activity_refs.extend(phased_refs)
                selected_activities = []
                for external_id, phase in sorted(set(activity_refs)):
                    activity = activities.get(str(external_id))
                    if activity is None:
                        issues.append("ACTIVITY_MAPPING_BROKEN")
                        continue
                    selected_activities.append(
                        {
                            **deepcopy(activity),
                            "phase": phase,
                            "schedule_version_id": version.id,
                            "near_critical": near_critical(activity, threshold),
                            "criticality_authority": "P6_IMPORTED"
                            if activity.get("critical") is not None
                            else "UNKNOWN",
                        }
                    )
                readiness = [
                    awp["current_readiness"].get(
                        str(row["id"]), {"package_id": row["id"], "readiness_state": "NOT_ASSESSED"}
                    )
                    for row in packages
                ]
                blocked = any(
                    row.get("stale") or row.get("readiness_state") not in {"READY", "RELEASED"} for row in readiness
                )
                state = resolve_state(
                    scope.scope_nature,
                    selected_activities,
                    selected,
                    baseline=source == "BASELINE",
                    threshold=threshold,
                    blocked=blocked,
                    timezone_name=reference["timezone"],
                    data_date=reference["data_date"],
                )
                object_ids = {link.model_object_id for link in model_links if link.scope_item_id == scope.id}
                plan_objects = {link.model_object_id for link in plan_model_links if link.plan_item_id == plan_id}
                if plan_objects:
                    object_ids = object_ids & plan_objects if object_ids else plan_objects
                source_objects = [
                    {
                        "object_id": row.id,
                        "model_version_id": row.model_version_id,
                        "guid": row.guid,
                        "express_id": row.express_id,
                        "geometry_reference": deepcopy(row.geometry_reference),
                        "source_hash": models[row.model_version_id].source_hash,
                        "source_url": f"/api/v1/scope/projects/{workspace_id}/models/{row.model_version_id}/source",
                    }
                    for identity in sorted(object_ids)
                    if (row := objects.get(identity)) and row.model_version_id in models
                ]
                derived_members = [
                    row
                    for row in derived
                    if plan_id is not None
                    and any(member["plan_item_id"] == plan_id for member in row.snapshot_json.get("memberships", []))
                ]
                # Prefer the immutable subset identities recorded by the selected
                # Schedule mapping. A later derived revision must not replace a
                # historical Baseline's recorded geometry lineage.
                recorded_derived = {
                    entry["id"]
                    for mapping in mappings
                    if plan_id in mapping["plan_item_ids"] or scope.id in mapping["scope_item_ids"]
                    for entry in mapping.get("lineage_json", {}).get("derived_models", [])
                }
                selected_derived = [row for row in derived_members if row.id in recorded_derived]
                if not recorded_derived:
                    selected_derived = [row for row in derived_members if row.created_at <= version.created_at][-1:]
                if selected_derived:
                    subset_objects = {
                        entry["object_id"] for row in selected_derived for entry in row.snapshot_json.get("objects", [])
                    }
                    source_objects = [entry for entry in source_objects if entry["object_id"] in subset_objects]
                constraint_ids = set()
                for link in awp["constraint_mappings"]:
                    if link.get("status") == "REMOVED":
                        continue
                    kind, target = link.get("target_kind"), link.get("target_id")
                    if (
                        kind == "PACKAGE"
                        and target in members
                        or kind == "SCOPE"
                        and target == scope.id
                        or kind == "PLAN"
                        and target == plan_id
                        and plan_id is not None
                        or kind == "CWA"
                        and target in {row.get("cwa_id") for row in packages}
                        or kind == "ACTIVITY"
                        and link.get("schedule_version_id") == version.id
                        and link.get("activity_external_id") in {row["external_id"] for row in selected_activities}
                    ):
                        constraint_ids.add(link["constraint_id"])
                constraints = [row for row in awp["constraints"] if row["id"] in constraint_ids]
                if any(row.get("blocking") and row["status"] in {"OPEN", "IN_PROGRESS"} for row in constraints):
                    blocked = True
                    state["visual_classes"] = list(dict.fromkeys([*state["visual_classes"], "BLOCKED_BY_READINESS"]))
                item = {
                    "id": f"scope:{scope.id}:plan:{plan_id or 'direct'}",
                    "scope_item_id": scope.id,
                    "scope_code": scope.scope_code,
                    "name": scope.name,
                    "scope_nature": scope.scope_nature,
                    "plan_item_id": plan_id,
                    "plan_code": plan.code if plan else None,
                    "area": scope.area,
                    "zone": scope.zone,
                    "system": scope.system,
                    **state,
                    "activities": selected_activities,
                    "wbs": self._wbs_memberships(wbs, selected_activities),
                    "packages": packages,
                    "cwas": [
                        cwas[identity]
                        for identity in sorted({row["cwa_id"] for row in packages if row.get("cwa_id")})
                        if identity in cwas
                    ],
                    "readiness": readiness,
                    "readiness_diagnostics": ["READINESS_ASSESSMENT_STALE"]
                    if any(row.get("stale") for row in readiness)
                    else [],
                    "constraints": constraints,
                    "blocked": blocked,
                    "objects": source_objects,
                    "derived_models": [
                        {
                            "id": row.id,
                            "revision": row.revision,
                            "content_hash": row.content_hash,
                            "representation_type": row.representation_type,
                        }
                        for row in selected_derived
                    ],
                    "mapping_issues": list(dict.fromkeys([*issues, *state["mapping_issues"]])),
                    "readiness_basis": "CURRENT_OPERATIONAL_NOT_HISTORICAL_SCHEDULE",
                }
                # Partial mappings cannot make a whole membership look installed
                # or completed. Keep valid readiness/criticality overlays distinct.
                if item["mapping_issues"]:
                    item["state"], item["semantic_state"], item["visible"] = "UNKNOWN", "UNKNOWN", True
                    item["visual_classes"] = [
                        "UNKNOWN",
                        *[
                            value
                            for value in item["visual_classes"]
                            if value in {"CRITICAL", "NEAR_CRITICAL", "BLOCKED_BY_READINESS"}
                        ],
                    ]
                if item["mapping_issues"] and profile.content_json["mapping_completeness_policy"] == "BLOCK_INCOMPLETE":
                    raise HTTPException(
                        409,
                        detail={
                            "code": "FOUR_D_MAPPING_INCOMPLETE",
                            "item_id": item["id"],
                            "issues": item["mapping_issues"],
                        },
                    )
                if self._matches(item, filters or {}):
                    items.append(item)
        periods = [
            self._out(row)
            for row in self._rows(SchedulePeriodAssociation, workspace_id)
            if row.schedule_version_id == version.id
        ]
        bounds = []
        milestones = []
        for activity in activities.values():
            try:
                start, finish = activity_dates(
                    activity, baseline=source == "BASELINE", timezone_name=reference["timezone"]
                )
                bounds.extend(value for value in (start, finish) if value)
                if "Milestone" in str(activity.get("activity_type", "")) and (start or finish):
                    milestones.append(
                        {
                            "external_id": activity["external_id"],
                            "name": activity.get("name"),
                            "date": (start or finish).isoformat(),
                        }
                    )
            except (ValueError, TypeError):
                pass
        hashes = {
            "schedule": reference["schedule_content_hash"],
            "source": reference["content_hash"],
            "scope_baseline": scope_baseline.content_hash,
            "four_d_profile": profile.content_hash,
            "awp_operational": _hash(awp),
            "derived_models": _hash([row.content_hash for row in derived]),
            "original_models": _hash({row.id: row.source_hash for row in models.values()}),
        }
        versions = self._rows(ScheduleVersion, workspace_id)
        baselines = self._rows(ScheduleBaseline, workspace_id)
        return {
            "version": 1,
            "project_workspace_id": workspace_id,
            "source": reference,
            "at": selected,
            "configuration": self._profile_out(profile),
            "items": items,
            "total": len(items),
            "sources": {
                "current": [
                    {"id": row.id, "register_id": row.register_id, "revision": row.revision, "data_date": row.data_date}
                    for row in versions
                    if row.status == "ACCEPTED_CURRENT"
                ],
                "baselines": [
                    {
                        "id": row.id,
                        "register_id": row.register_id,
                        "schedule_version_id": row.schedule_version_id,
                        "revision": row.revision,
                    }
                    for row in baselines
                    if row.status == "APPROVED_BASELINE"
                ],
            },
            "milestones": milestones,
            "timeline": {
                "start": min(bounds).isoformat() if bounds else None,
                "finish": max(bounds).isoformat() if bounds else None,
                "data_date": reference["data_date"],
            },
            "period_associations": periods,
            "source_hashes": hashes,
            "read_model_hash": _hash(
                {"sources": hashes, "source": reference, "at": selected, "filters": filters or {}}
            ),
            "diagnostics": list(dict.fromkeys(issue for item in items for issue in item["mapping_issues"])),
            "authority": {
                "geometry": "ORIGINAL_IFC_AND_EXISTING_DERIVED_SUBSETS",
                "scope": "APPROVED_SCOPE_BASELINE",
                "schedule": "GOVERNED_SCHEDULE_FOUNDATION",
                "cpm": "PRIMAVERA_P6_EXTERNAL",
                "cpm_calculation_performed": False,
                "business_writes_performed": False,
                "cache": "REBUILDABLE_SOURCE_HASH_AWARE_NO_PERSISTENCE",
            },
        }

    @staticmethod
    def _wbs_memberships(index, activities):
        """A WBS filter includes its existing source subtree, not only a leaf."""
        identities = {str(row.get("wbs_external_id")) for row in activities}
        pending = list(identities)
        while pending:
            row = index.get(pending.pop())
            parent = str(row.get("parent_external_id")) if row else "None"
            if parent in index and parent not in identities:
                identities.add(parent)
                pending.append(parent)
        return [deepcopy(index[identity]) for identity in sorted(identities) if identity in index]

    @staticmethod
    def _matches(item, filters):
        fields = {"scope_item_id", "scope_nature", "plan_item_id", "area", "zone", "system", "blocked"}
        for key in fields:
            if filters.get(key) is not None and item.get(key) != filters[key]:
                return False
        checks = {
            "activity": lambda value: any(str(row["external_id"]) == str(value) for row in item["activities"]),
            "wbs": lambda value: any(str(row["external_id"]) == str(value) for row in item["wbs"]),
            "cwa_id": lambda value: any(row["id"] == value for row in item["cwas"]),
            "work_package_id": lambda value: any(row["id"] == value for row in item["packages"]),
            "package_type": lambda value: any(row["package_type"] == value for row in item["packages"]),
            "activity_status": lambda value: any(row.get("status") == value for row in item["activities"]),
            "critical": lambda value: any(row.get("critical") is value for row in item["activities"]),
            "near_critical": lambda value: any(row.get("near_critical") is value for row in item["activities"]),
            "execution_readiness": lambda value: any(row.get("readiness_state") == value for row in item["readiness"]),
        }
        return all(value is None or key not in checks or checks[key](value) for key, value in filters.items())

    def traceability(self, workspace_id, scope_item_id, **options):
        result = self.model(
            workspace_id, **{**options, "filters": {**options.get("filters", {}), "scope_item_id": scope_item_id}}
        )
        if not result["items"]:
            self._error(404, "FOUR_D_SCOPE_NOT_IN_SELECTED_SOURCE")
        return result | {"traceability": result["items"]}

    def compare(self, workspace_id, baseline_id, version_id=None, at=None, filters=None):
        current = self.model(workspace_id, source="CURRENT", version_id=version_id, at=at, filters=filters)
        baseline = self.model(
            workspace_id, source="BASELINE", baseline_id=baseline_id, at=current["at"], filters=filters
        )
        if current["source"]["register_id"] != baseline["source"]["register_id"]:
            self._error(422, "FOUR_D_COMPARE_STREAM_MISMATCH")
        before = {row["id"]: row for row in baseline["items"]}
        after = {row["id"]: row for row in current["items"]}
        items = []
        for key in sorted(before.keys() | after.keys()):
            previous, following = before.get(key), after.get(key)
            item = following or previous
            classification = compare_states(previous, following)
            if classification == "BEHIND_BASELINE" and following:
                following["visual_classes"] = list(dict.fromkeys([*following["visual_classes"], "DELAYED"]))
            items.append(
                {
                    "id": key,
                    "scope_item_id": item["scope_item_id"],
                    "plan_item_id": item["plan_item_id"],
                    "baseline_state": previous["state"] if previous else None,
                    "current_state": following["state"] if following else None,
                    "variance_classification": classification,
                }
            )
        return {
            "at": current["at"],
            "baseline": baseline,
            "current": current,
            "items": items,
            "cpm_calculation_performed": False,
            "business_writes_performed": False,
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
            self._error(404, "FOUR_D_PROFILE_NOT_FOUND")
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

    def allowed_actions(self, workspace=None):
        result = []
        for action in ("read", "admin.configure", "admin.publish"):
            try:
                self._permission(action, workspace)
                result.append(action)
            except HTTPException as error:
                if error.status_code != 403:
                    raise
        return result

    def _validate_profile(self, content):
        import re

        try:
            if set(content) != set(DEFAULT_PROFILE) or content["state_rules"] != SEMANTICS:
                raise ValueError("Semantic rules are fixed; configure presentation only")
            if content["temporary_phase_policy"] != "EXPLICIT_INSTALL_USE_REMOVE":
                raise ValueError("Explicit temporary phases required")
            if content["mapping_completeness_policy"] not in {"FLAG_AND_RENDER_UNKNOWN", "BLOCK_INCOMPLETE"}:
                raise ValueError("Mapping completeness policy")
            if (
                type(content["allow_direct_scope_mapping"]) is not bool
                or type(content["inherit_to_descendants"]) is not bool
            ):
                raise ValueError("Booleans")
            if content["separation_of_duties"] != {"author_cannot_publish": True}:
                raise ValueError("Independent publication required")
            scope = content["scope"]
            if set(scope) != {"type", "workspace_id"}:
                raise ValueError("Scope keys")
            if scope["type"] == "workspace":
                if type(scope["workspace_id"]) is not int or scope["workspace_id"] < 1:
                    raise ValueError("Canonical Project required")
                self._project(scope["workspace_id"])
            elif scope["type"] != "tenant" or scope["workspace_id"] is not None:
                raise ValueError("Scope")
            if set(content["display"]) != set(DEFAULT_PROFILE["display"]):
                raise ValueError("Display classes")
            for display in content["display"].values():
                if set(display) != {"color", "opacity"} or not re.fullmatch(r"#[0-9a-fA-F]{6}", display["color"]):
                    raise ValueError("Color")
                if type(display["opacity"]) not in {int, float} or not 0 <= display["opacity"] <= 1:
                    raise ValueError("Opacity")
        except (KeyError, TypeError, ValueError) as error:
            raise HTTPException(422, detail={"code": "FOUR_D_PROFILE_INVALID"}) from error

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
                self._error(409, "FOUR_D_PROFILE_CODE_EXISTS")
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
            self._event("FOUR_D_CONFIGURATION_CREATED", row.id, {"hash": row.content_hash})
            return self._profile_out(row)

        return self._command("four_d.profile.create", key, payload.model_dump(mode="json"), apply)

    def update_profile(self, identity, payload, expected, key):
        self._permission("admin.configure")

        def apply():
            row = self._profile(identity, lock=True)
            self._version(row.version, expected)
            if row.status != "draft":
                self._error(409, "FOUR_D_PROFILE_PUBLISHED_IMMUTABLE")
            self._validate_profile(payload.content_json)
            row.name, row.content_json, row.content_hash = (
                payload.name,
                deepcopy(payload.content_json),
                _hash(payload.content_json),
            )
            row.version, row.updated_at = row.version + 1, utc_now()
            self.db.flush()
            self._event("FOUR_D_CONFIGURATION_UPDATED", row.id, {"version": row.version})
            return self._profile_out(row)

        return self._command(
            "four_d.profile.update",
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
                self._error(409, "FOUR_D_PROFILE_PUBLISHED_IMMUTABLE")
            self._validate_profile(row.content_json)
            editor = row.created_by_user_id
            if row.version > 1:
                receipt = self.db.scalar(
                    select(OperationalContextCommand).where(
                        OperationalContextCommand.tenant_id == self.tenant_id,
                        OperationalContextCommand.command_type == "four_d.profile.update",
                        OperationalContextCommand.result_json["id"].as_integer() == row.id,
                        OperationalContextCommand.result_json["version"].as_integer() == row.version,
                    )
                )
                if receipt is None or receipt.result_json.get("content_hash") != row.content_hash:
                    self._error(409, "FOUR_D_PROFILE_EDITOR_PROVENANCE_REQUIRED")
                editor = receipt.actor_id
            if self.actor_id in {row.created_by_user_id, editor}:
                self._error(403, "FOUR_D_PROFILE_PUBLICATION_SOD")
            row.status, row.published_at, row.version = "published", utc_now(), row.version + 1
            self.db.flush()
            self._event("FOUR_D_CONFIGURATION_PUBLISHED", row.id, {"hash": row.content_hash, "reason": payload.reason})
            return self._profile_out(row)

        return self._command(
            "four_d.profile.publish",
            key,
            {"id": identity, "expected": expected, **payload.model_dump(mode="json")},
            apply,
        )

    def successor_profile(self, identity, payload, expected, key):
        from sqlalchemy import func

        self._permission("admin.configure")

        def apply():
            old = self._profile(identity, lock=True)
            self._version(old.version, expected)
            if old.status != "published":
                self._error(409, "PUBLISHED_FOUR_D_PROFILE_REQUIRED")
            revision = (
                self.db.scalar(
                    select(func.max(AdminConfiguration.revision)).where(
                        AdminConfiguration.tenant_id == self.tenant_id,
                        AdminConfiguration.kind == PROFILE_KIND,
                        AdminConfiguration.code == old.code,
                    )
                )
                + 1
            )
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
            self._event("FOUR_D_CONFIGURATION_SUCCESSOR", row.id, {"predecessor_id": old.id})
            return self._profile_out(row)

        return self._command(
            "four_d.profile.successor",
            key,
            {"id": identity, "expected": expected, **payload.model_dump(mode="json")},
            apply,
        )
