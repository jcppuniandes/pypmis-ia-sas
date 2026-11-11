"""Canonical measurement, certification and approval without upstream write-back."""

from copy import deepcopy
from datetime import date
from decimal import DecimalException

from fastapi import HTTPException
from sqlalchemy import select

from app.core.time import utc_now
from app.domain.models import AdminConfiguration, SecurityEvent
from app.modules.awp.models import PackageMapping, WorkPackage
from app.modules.basic_data.service import _hash
from app.modules.cost_foundation.models import ControlAccount, CostBaseline
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.operational_context.models import OperationalContextCommand, ProjectControlsPeriod
from app.modules.progress_foundation.models import ProgressHistory, ProgressMeasurement, ProgressRule
from app.modules.progress_foundation.permissions import ACTIONS
from app.modules.progress_foundation.policy import (
    DEFAULT_PROFILE,
    METHODS,
    TYPES,
    WEIGHTING_BASES,
    cost_progress_ratio,
    credit_progress,
    number,
    percentage,
    rounded,
    validate_profile,
    weighted_progress,
)
from app.modules.progress_foundation.schemas import MeasurementIn
from app.modules.schedule_foundation.models import ScheduleBaseline, ScheduleMapping, ScheduleRegister, ScheduleVersion
from app.modules.scope_foundation.models import PlanItem, PlanItemScopeLink, ScopeBaseline, ScopeItem
from app.modules.scope_foundation.service import ScopeFoundationService

PROFILE_KIND = "progress_profile"


class ProgressFoundationService(ScopeFoundationService):
    def _permission(self, action, workspace=None):
        if self.access_context is None:
            return
        if action not in self._permission_contexts:
            self._permission_contexts[action] = require_enterprise_permission(
                self.db, self.tenant_id, self.actor_id, f"progress.{action}", bootstrap=False
            )
        access = self._permission_contexts[action]
        if action.startswith("admin.") and not access.organization_wide:
            self._error(403, "PROGRESS_ADMIN_ORGANIZATION_SCOPE_REQUIRED")
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
                event_type=f"progress.{action}",
                outcome=outcome,
                target_type="ProgressFoundation",
                target_id=target_id,
                metadata_json=deepcopy(metadata),
            )
        )

    def _record(self, row, event, reason, *, changed=False):
        if changed:
            row.version += 1
            if hasattr(row, "updated_by"):
                row.updated_by = self.actor_id
        self.db.flush()
        snapshot = self._out(row)
        self.db.add(
            ProgressHistory(
                **self._base(row.project_workspace_id),
                entity_type=type(row).__name__,
                entity_id=row.id,
                revision=row.version,
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
        def checked_apply():
            try:
                return apply()
            except (DecimalException, OverflowError) as error:
                raise HTTPException(422, detail={"code": "PROGRESS_DECIMAL_RANGE_INVALID"}) from error
            except ValueError as error:
                raise HTTPException(422, detail={"code": str(error)}) from error

        return self._command(
            f"progress.{command}",
            key,
            {"project": workspace, "id": identity, "expected": expected, **payload.model_dump(mode="json")},
            checked_apply,
        )

    def _progress_profile(self, project):
        candidates, now = [], utc_now()
        for row in self.db.scalars(
            select(AdminConfiguration).where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == PROFILE_KIND,
                AdminConfiguration.status == "published",
            )
        ):
            content = row.content_json
            start, finish = self._instant(content.get("effective_from")), self._instant(content.get("effective_to"))
            if start and now < start or finish and now >= finish:
                continue
            scope = content["scope"]
            if scope["type"] == "tenant":
                priority = 0
            elif scope["workspace_id"] == project.id:
                priority = 100
            elif content["inherit_to_descendants"] and scope["workspace_id"] in self._workspace_paths.get(
                project.id, set()
            ):
                priority = 50
            else:
                continue
            candidates.append((priority, row))
        if not candidates:
            return None
        top = [row for priority, row in candidates if priority == max(priority for priority, _ in candidates)]
        if len({row.code for row in top}) != 1:
            self._error(409, "PROGRESS_PROFILE_AMBIGUOUS")
        return max(top, key=lambda row: row.revision)

    def _ready(self, workspace, action):
        project = self._project(workspace)
        self._permission(action, project)
        scope = ScopeFoundationService(self.db, self.tenant_id, self.actor_id, self.access_context)
        scope._ready(workspace, "read")
        if scope._current_baseline(workspace) is None:
            self._error(409, "PROGRESS_APPROVED_SCOPE_BASELINE_REQUIRED")
        profile = self._progress_profile(project)
        if profile is None:
            self._error(409, "PROGRESS_PUBLISHED_PROFILE_REQUIRED")
        return project, profile

    def _profile(self, identity, *, lock=False):
        query = select(AdminConfiguration).where(
            AdminConfiguration.tenant_id == self.tenant_id,
            AdminConfiguration.kind == PROFILE_KIND,
            AdminConfiguration.id == identity,
        )
        row = self.db.scalar(query.with_for_update().execution_options(populate_existing=True) if lock else query)
        if row is None:
            self._error(404, "PROGRESS_PROFILE_NOT_FOUND")
        return row

    def profiles(self):
        self._permission("admin.configure")
        return {
            "items": [
                self._profile_out(row)
                for row in self.db.scalars(
                    select(AdminConfiguration)
                    .where(AdminConfiguration.tenant_id == self.tenant_id, AdminConfiguration.kind == PROFILE_KIND)
                    .order_by(AdminConfiguration.id)
                )
            ],
            "default_content": deepcopy(DEFAULT_PROFILE),
            "allowed_actions": self.allowed_actions(),
        }

    def _validate_profile(self, content):
        try:
            validate_profile(content)
            scope = content["scope"]
            if scope["type"] == "workspace":
                self._project(scope["workspace_id"])
            elif scope != {"type": "tenant", "workspace_id": None}:
                raise ValueError("scope")
            start, end = self._instant(content["effective_from"]), self._instant(content["effective_to"])
            if start and end and end <= start:
                raise ValueError("window")
        except (KeyError, ValueError, TypeError) as error:
            raise HTTPException(422, detail={"code": "PROGRESS_PROFILE_INVALID"}) from error

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
                self._error(409, "PROGRESS_PROFILE_CODE_EXISTS")
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
            self._event("PROGRESS_PROFILE_CREATED", row.id, {"hash": row.content_hash, "reason": payload.reason})
            return self._profile_out(row)

        return self._command("progress.profile.create", key, payload.model_dump(mode="json"), apply)

    def update_profile(self, identity, payload, expected, key):
        self._permission("admin.configure")

        def apply():
            row = self._profile(identity, lock=True)
            self._version(row.version, expected)
            if row.status != "draft":
                self._error(409, "PROGRESS_PROFILE_PUBLISHED_IMMUTABLE")
            self._validate_profile(payload.content_json)
            row.name, row.content_json, row.content_hash = (
                payload.name,
                deepcopy(payload.content_json),
                _hash(payload.content_json),
            )
            row.version, row.updated_at = row.version + 1, utc_now()
            self.db.flush()
            self._event("PROGRESS_PROFILE_UPDATED", row.id, {"hash": row.content_hash, "reason": payload.reason})
            return self._profile_out(row)

        return self._command(
            "progress.profile.update",
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
                self._error(409, "PROGRESS_PROFILE_PUBLISHED_IMMUTABLE")
            self._validate_profile(row.content_json)
            editor = row.created_by_user_id
            if row.version > 1:
                receipt = self.db.scalar(
                    select(OperationalContextCommand).where(
                        OperationalContextCommand.tenant_id == self.tenant_id,
                        OperationalContextCommand.command_type == "progress.profile.update",
                        OperationalContextCommand.result_json["id"].as_integer() == row.id,
                        OperationalContextCommand.result_json["version"].as_integer() == row.version,
                    )
                )
                if receipt is None:
                    self._error(409, "PROGRESS_PROFILE_EDITOR_PROVENANCE_REQUIRED")
                editor = receipt.actor_id
            if self.actor_id in {row.created_by_user_id, editor}:
                self._error(403, "PROGRESS_PROFILE_PUBLICATION_SOD")
            row.status, row.published_at, row.version = "published", utc_now(), row.version + 1
            self.db.flush()
            self._event(
                "PROGRESS_CONFIGURATION_PUBLISHED", row.id, {"hash": row.content_hash, "reason": payload.reason}
            )
            return self._profile_out(row)

        return self._command(
            "progress.profile.publish",
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
                self._error(409, "PROGRESS_PUBLISHED_PROFILE_SUCCESSOR_REQUIRED")
            rows = self.db.scalars(
                select(AdminConfiguration).where(
                    AdminConfiguration.tenant_id == self.tenant_id,
                    AdminConfiguration.kind == PROFILE_KIND,
                    AdminConfiguration.code == old.code,
                )
            )
            revision = max(row.revision for row in rows) + 1
            row = AdminConfiguration(
                tenant_id=self.tenant_id,
                kind=PROFILE_KIND,
                code=old.code,
                name=old.name,
                revision=revision,
                version=1,
                status="draft",
                content_json=deepcopy(old.content_json),
                content_hash=old.content_hash,
                created_by_user_id=self.actor_id,
            )
            self.db.add(row)
            self.db.flush()
            self._event(
                "PROGRESS_PROFILE_SUCCESSOR_CREATED", row.id, {"predecessor_id": old.id, "reason": payload.reason}
            )
            return self._profile_out(row)

        return self._command(
            "progress.profile.successor",
            key,
            {"id": identity, "expected": expected, **payload.model_dump(mode="json")},
            apply,
        )

    def _period_for_measurement(self, workspace, period_id, *, capture=False, row=None):
        period = self._get(ProjectControlsPeriod, workspace, period_id, lock=capture or row is not None)
        if period.status not in ({"OPEN"} if capture else {"OPEN", "REVIEW"}):
            self._error(409, "PROGRESS_PERIOD_FROZEN_OR_CLOSED")
        if row is not None and period.status == "REVIEW":
            from app.modules.progress_foundation.integration_models import ProgressPeriodSnapshot

            report = self.db.scalar(
                select(ProgressPeriodSnapshot).where(
                    ProgressPeriodSnapshot.tenant_id == self.tenant_id,
                    ProgressPeriodSnapshot.project_workspace_id == workspace,
                    ProgressPeriodSnapshot.period_id == period.id,
                )
            )
            if report is None or not any(
                candidate["id"] == row.id and candidate["content_hash"] == row.content_hash
                for candidate in report.candidate_snapshot_json
            ):
                self._error(409, "PROGRESS_NOT_IN_FROZEN_REVIEW_SET")
        return period

    def _rule(self, workspace, identity):
        row = self._get(ProgressRule, workspace, identity)
        if row.status != "PUBLISHED":
            self._error(409, "PROGRESS_PUBLISHED_RULE_REQUIRED")
        return row

    def save_rule(self, workspace, payload, key, identity=None, expected=None, *, successor=False):
        self._ready(workspace, "rule.manage")

        def apply():
            _, profile = self._ready(workspace, "rule.manage")
            credit_progress([step.model_dump(mode="json") for step in payload.steps], [], ordered=payload.ordered)
            if payload.method not in profile.content_json["allowed_methods"]:
                self._error(422, "PROGRESS_METHOD_DISABLED")
            for nature in payload.scope_natures:
                if payload.method not in profile.content_json["methods_by_scope_nature"][nature]:
                    self._error(422, "PROGRESS_NATURE_METHOD_DISABLED")
            if len(set(payload.package_types)) != len(payload.package_types) or not set(payload.package_types) <= set(
                profile.content_json["package_methods"]
            ):
                self._error(422, "PROGRESS_PACKAGE_TYPE_NOT_CONFIGURED")
            basis = payload.measurement_basis
            if basis:
                if not set(basis) <= {
                    "denominator",
                    "unit",
                    "work_package_id",
                    "scope_item_id",
                    "plan_item_id",
                    "weight",
                    "weighting_basis",
                    "source_reference",
                    "phase",
                }:
                    self._error(422, "PROGRESS_MEASUREMENT_BASIS_INVALID")
                if "denominator" in basis and (
                    number(basis["denominator"]) <= 0 or not basis.get("unit") or not basis.get("source_reference")
                ):
                    self._error(422, "PROGRESS_APPROVED_BASIS_SOURCE_REQUIRED")
                for field, model in (
                    ("work_package_id", WorkPackage),
                    ("scope_item_id", ScopeItem),
                    ("plan_item_id", PlanItem),
                ):
                    if basis.get(field):
                        self._get(model, workspace, int(basis[field]))
                if "weight" in basis and (
                    number(basis["weight"]) <= 0
                    or basis.get("weighting_basis") not in WEIGHTING_BASES
                    or not basis.get("source_reference")
                    or basis.get("weighting_basis") in {"LABOR_HOURS", "ENGINEERING_HOURS", "CONTRACT_VALUE"}
                    and not basis.get("unit")
                ):
                    self._error(422, "PROGRESS_APPROVED_WEIGHT_SOURCE_REQUIRED")
            old = self._get(ProgressRule, workspace, identity, lock=True) if identity else None
            if old:
                self._version(old.version, expected)
                if old.status != ("PUBLISHED" if successor else "DRAFT"):
                    self._error(409, "PROGRESS_RULE_IMMUTABLE")
                if successor and payload.code != old.code:
                    self._error(422, "PROGRESS_SUCCESSOR_CODE_MISMATCH")
            data = payload.model_dump(exclude={"reason", "steps"}) | {
                "steps_json": [step.model_dump(mode="json") for step in payload.steps]
            }
            if old and not successor:
                row = old
                for field, value in data.items():
                    setattr(row, field, value)
                row.configuration_id, row.configuration_hash = profile.id, profile.content_hash
            else:
                if any(rule.code == payload.code for rule in self._rows(ProgressRule, workspace)) and not successor:
                    self._error(409, "PROGRESS_RULE_CODE_EXISTS")
                row = ProgressRule(
                    **self._base(workspace),
                    **data,
                    revision=max(
                        (rule.revision for rule in self._rows(ProgressRule, workspace) if rule.code == payload.code),
                        default=0,
                    )
                    + 1,
                    supersedes_id=old.id if old else None,
                    updated_by=self.actor_id,
                    configuration_id=profile.id,
                    configuration_hash=profile.content_hash,
                )
                self.db.add(row)
            row.content_hash = _hash(data)
            return self._record(
                row,
                "PROGRESS_RULE_REVISED" if old else "PROGRESS_RULE_CREATED",
                payload.reason,
                changed=bool(old and not successor),
            )

        return self._write(
            "rule.successor" if successor else "rule.save", workspace, payload, key, apply, identity, expected
        )

    def publish_rule(self, workspace, identity, payload, expected, key):
        self._ready(workspace, "rule.publish")

        def apply():
            self._ready(workspace, "rule.publish")
            row = self._get(ProgressRule, workspace, identity, lock=True)
            self._version(row.version, expected)
            if row.status != "DRAFT":
                self._error(409, "PROGRESS_RULE_IMMUTABLE")
            if self.actor_id in {row.created_by, row.updated_by}:
                self._error(403, "PROGRESS_RULE_PUBLICATION_SOD")
            if any(
                rule.status == "PUBLISHED" and rule.supersedes_id == row.supersedes_id and rule.code == row.code
                for rule in self._rows(ProgressRule, workspace)
            ):
                self._error(409, "PROGRESS_RULE_APPROVED_BRANCH_CONFLICT")
            row.status, row.published_by, row.published_at = "PUBLISHED", self.actor_id, utc_now()
            return self._record(row, "PROGRESS_RULE_PUBLISHED", payload.reason, changed=True)

        return self._write("rule.publish", workspace, payload, key, apply, identity, expected)

    def _source_basis(self, workspace, payload, profile):
        scope = ScopeFoundationService(self.db, self.tenant_id, self.actor_id, self.access_context)
        baseline = scope._current_baseline(workspace)
        frozen = {int(item["id"]): deepcopy(item) for item in baseline.snapshot_json["items"]}
        source = {
            "scope_baseline_id": baseline.id,
            "scope_baseline_hash": baseline.content_hash,
            "scope_item_ids": [],
            "phase": payload.phase,
        }
        denominator, source_unit = None, payload.unit
        if payload.scope_item_id:
            if payload.scope_item_id not in frozen:
                self._error(409, "PROGRESS_SCOPE_NOT_IN_APPROVED_BASELINE")
            item = frozen[payload.scope_item_id]
            source["scope"] = item
            source["scope_item_ids"] = [payload.scope_item_id]
            denominator = number(
                item.get("approved_quantity") if item.get("approved_quantity") is not None else item["quantity"]
            )
            source_unit = item["unit"]
            if item["scope_nature"] != payload.scope_nature:
                self._error(422, "PROGRESS_SCOPE_NATURE_MISMATCH")
        plan = None
        if payload.plan_item_id:
            plan = self._get(PlanItem, workspace, payload.plan_item_id)
            if plan.status != "PUBLISHED":
                self._error(409, "PROGRESS_PUBLISHED_PLAN_REQUIRED")
            links = [link for link in self._rows(PlanItemScopeLink, workspace) if link.plan_item_id == plan.id]
            if not links or any(link.scope_item_id not in frozen for link in links):
                self._error(409, "PROGRESS_PLAN_ALLOCATION_STALE")
            if payload.scope_item_id:
                links = [link for link in links if link.scope_item_id == payload.scope_item_id]
                if not links:
                    self._error(422, "PROGRESS_PLAN_SCOPE_MAPPING_REQUIRED")
            units = {link.unit for link in links}
            if len(units) != 1 or any(
                frozen[link.scope_item_id]["scope_nature"] != payload.scope_nature for link in links
            ):
                self._error(422, "PROGRESS_PLAN_REQUIRES_COMPATIBLE_SCOPE_ALLOCATION")
            source["plan"] = self._out(plan)
            source["plan_allocations"] = [self._out(link) for link in links]
            source["scope_item_ids"] = sorted({link.scope_item_id for link in links})
            if payload.denominator_basis in {"AUTO", "PLAN"}:
                denominator, source_unit = sum(link.quantity for link in links), next(iter(units))
        package = None
        if payload.work_package_id:
            package = self._get(WorkPackage, workspace, payload.work_package_id)
            source["package"] = {
                key: value
                for key, value in self._out(package).items()
                if key
                not in {
                    "readiness_state",
                    "release_state",
                    "released_by",
                    "released_at",
                    "status",
                    "version",
                    "updated_by",
                    "updated_at",
                }
            }
            # Readiness and release never supply completed work or denominator.
            mappings = {}
            for link in self._rows(PackageMapping, workspace):
                if link.work_package_id == package.id:
                    mappings[
                        (
                            link.target_kind,
                            link.target_id,
                            link.schedule_version_id,
                            link.activity_external_id,
                            link.phase,
                        )
                    ] = link
            active = [link for link in mappings.values() if link.status == "ACTIVE"]
            if plan and not any(link.target_kind == "PLAN" and link.target_id == plan.id for link in active):
                self._error(422, "PROGRESS_PACKAGE_PLAN_MAPPING_REQUIRED")
            if (
                payload.scope_item_id
                and not plan
                and not any(link.target_kind == "SCOPE" and link.target_id == payload.scope_item_id for link in active)
            ):
                self._error(422, "PROGRESS_PACKAGE_SCOPE_MAPPING_REQUIRED")
            source["package_mappings"] = [self._out(link) for link in active]
            if payload.denominator_basis in {"AUTO", "PACKAGE"}:
                approved = [row for row in self._rows(CostBaseline, workspace) if row.status == "APPROVED"]
                previous = {row.previous_baseline_id for row in approved if row.previous_baseline_id}
                leaves = [row for row in approved if row.id not in previous]
                allocations = []
                if len(leaves) == 1:
                    allocations = [
                        row
                        for row in leaves[0].snapshot_json.get("source_mappings", [])
                        if row["source_kind"] == "PACKAGE"
                        and row["source_id"] == package.id
                        and row.get("quantity") is not None
                        and row.get("unit")
                    ]
                values = {(str(number(row["quantity"])), row["unit"]) for row in allocations}
                if len(values) == 1:
                    amount, source_unit = next(iter(values))
                    denominator = number(amount)
                    source["package_quantity_basis"] = {
                        "cost_baseline_id": leaves[0].id,
                        "cost_baseline_hash": leaves[0].content_hash,
                        "mappings": allocations,
                    }
                else:
                    denominator = None
        if payload.activity_external_id or payload.wbs_external_id or payload.schedule_version_id:
            if not payload.schedule_version_id or not (payload.activity_external_id or payload.wbs_external_id):
                self._error(422, "PROGRESS_SCHEDULE_IDENTITY_REQUIRED")
            version = self._get(ScheduleVersion, workspace, payload.schedule_version_id)
            register = self._get(ScheduleRegister, workspace, version.register_id)
            if version.status != "ACCEPTED_CURRENT" or register.current_version_id != version.id:
                self._error(409, "PROGRESS_ACCEPTED_CURRENT_SCHEDULE_REQUIRED")
            source.update(
                schedule_version_id=version.id, schedule_hash=version.content_hash, schedule_data_date=version.data_date
            )
            for field, table_key, kind in (
                ("activity_external_id", "activities", "ACTIVITY"),
                ("wbs_external_id", "wbs", "WBS"),
            ):
                external = getattr(payload, field)
                if not external:
                    continue
                record = next(
                    (row for row in version.snapshot_json.get(table_key, []) if str(row["external_id"]) == external),
                    None,
                )
                if record is None:
                    self._error(422, "PROGRESS_ACTIVITY_IDENTITY_BROKEN")
                matches = [
                    row
                    for row in self._rows(ScheduleMapping, workspace)
                    if row.schedule_version_id == version.id
                    and row.target_kind == kind
                    and row.target_external_id == external
                ]
                link = max(matches, key=lambda row: row.revision) if matches else None
                if link is None or link.status != "VALID":
                    self._error(409, "PROGRESS_ACTIVITY_MAPPING_REQUIRES_REVIEW")
                resolved_scope = link.lineage_json.get("resolved_scope_item_ids", link.scope_item_ids)
                if (
                    payload.scope_item_id
                    and payload.scope_item_id not in resolved_scope
                    or payload.plan_item_id
                    and payload.plan_item_id not in link.plan_item_ids
                ):
                    self._error(422, "PROGRESS_SCHEDULE_SCOPE_PLAN_MISMATCH")
                source[table_key] = deepcopy(record)
                source[f"{table_key}_mapping"] = self._out(link)
                if not source["scope_item_ids"]:
                    source["scope_item_ids"] = sorted(resolved_scope)
            if package and payload.activity_external_id:
                activity_links = [
                    link
                    for link in source["package_mappings"]
                    if link["target_kind"] == "ACTIVITY"
                    and link["schedule_version_id"] == version.id
                    and link["activity_external_id"] == payload.activity_external_id
                ]
                if not activity_links:
                    self._error(422, "PROGRESS_PACKAGE_ACTIVITY_MAPPING_REQUIRED")
                if payload.scope_nature == "TEMPORARY" and {link["phase"] for link in activity_links} != {
                    payload.phase
                }:
                    self._error(422, "PROGRESS_PACKAGE_ACTIVITY_PHASE_MISMATCH")
        rule = self._rule(workspace, payload.rule_id) if payload.rule_id else None
        if rule:
            if (
                payload.scope_nature not in rule.scope_natures
                or package
                and package.package_type not in rule.package_types
            ):
                self._error(422, "PROGRESS_RULE_APPLICABILITY_MISMATCH")
            source["rule"] = self._out(rule)
            basis = rule.measurement_basis
            if (
                payload.denominator_basis == "APPROVED_RULE"
                or payload.method == "QUANTITY_BASED"
                and denominator is None
            ):
                subjects = [
                    (field, getattr(payload, field))
                    for field in ("scope_item_id", "plan_item_id", "work_package_id")
                    if getattr(payload, field)
                ]
                if (
                    not subjects
                    or not any(basis.get(field) == identity for field, identity in subjects)
                    or not basis.get("denominator")
                    or not basis.get("source_reference")
                ):
                    self._error(422, "PROGRESS_APPROVED_QUANTITY_BASIS_REQUIRED")
                denominator, source_unit = number(basis["denominator"]), basis["unit"]
        if payload.method == "QUANTITY_BASED" and (denominator is None or denominator <= 0):
            self._error(422, "PROGRESS_APPROVED_DENOMINATOR_REQUIRED")
        if payload.method == "QUANTITY_BASED" and payload.unit != source_unit:
            self._error(422, "PROGRESS_UNIT_MISMATCH_NO_IMPLICIT_CONVERSION")
        if (
            not any(
                (
                    payload.scope_item_id,
                    payload.plan_item_id,
                    payload.work_package_id,
                    payload.activity_external_id,
                    payload.control_account_id,
                    payload.area,
                    payload.system,
                    payload.discipline,
                )
            )
            and payload.method != "WEIGHTED_COMPONENTS"
        ):
            self._error(422, "PROGRESS_MEASUREMENT_SUBJECT_REQUIRED")
        if payload.control_account_id:
            account = self._get(ControlAccount, workspace, payload.control_account_id)
            if account.status != "ACTIVE":
                self._error(409, "PROGRESS_CONTROL_ACCOUNT_INACTIVE")
            source["control_account"] = self._out(account)
            approved = [row for row in self._rows(CostBaseline, workspace) if row.status == "APPROVED"]
            previous = {row.previous_baseline_id for row in approved if row.previous_baseline_id}
            leaves = [row for row in approved if row.id not in previous]
            expected = {
                "SCOPE": payload.scope_item_id,
                "PLAN": payload.plan_item_id,
                "PACKAGE": payload.work_package_id,
                "ACTIVITY": payload.activity_external_id,
            }
            expected = {kind: identity for kind, identity in expected.items() if identity}
            mappings = (
                []
                if len(leaves) != 1
                else [
                    link
                    for link in leaves[0].snapshot_json.get("source_mappings", [])
                    if link.get("control_account_id") == account.id
                    and link.get("status") == "ACTIVE"
                    and (
                        not any(expected.values())
                        or expected.get(link["source_kind"]) is not None
                        and expected.get(link["source_kind"])
                        == (
                            link.get("source_external_id")
                            if link["source_kind"] == "ACTIVITY"
                            else link.get("source_id")
                        )
                        and (
                            link["source_kind"] != "ACTIVITY"
                            or link.get("schedule_version_id") == payload.schedule_version_id
                        )
                    )
                ]
            )
            if not mappings:
                self._error(422, "PROGRESS_EXPLICIT_CONTROL_ACCOUNT_MAPPING_REQUIRED")
            if any(
                identity is not None and not any(link["source_kind"] == kind for link in mappings)
                for kind, identity in expected.items()
            ):
                self._error(422, "PROGRESS_EXPLICIT_CONTROL_ACCOUNT_MAPPING_REQUIRED")
            source["control_account_basis"] = {
                "cost_baseline_id": leaves[0].id,
                "cost_baseline_hash": leaves[0].content_hash,
                "mappings": mappings,
            }
        source["scope_items"] = [frozen[identity] for identity in source["scope_item_ids"] if identity in frozen]
        source["denominator_unit"] = source_unit
        references = [ref for ref in payload.evidence_refs if ref.reference.startswith("engineering-release:")]
        if references:
            from app.modules.engineering_foundation.integration import resolve_progress_release_fact

            if payload.progress_type not in {"MILESTONE", "WEIGHTED"}:
                self._error(422, "PROGRESS_ENGINEERING_RELEASE_NOT_PHYSICAL_QUANTITY_EVIDENCE")
            if len({ref.reference for ref in references}) != len(references):
                self._error(422, "PROGRESS_ENGINEERING_EVIDENCE_DUPLICATE")
            facts = []
            for ref in references:
                if ref.kind != "DOCUMENT":
                    self._error(422, "PROGRESS_ENGINEERING_EVIDENCE_KIND_INVALID")
                try:
                    fact = resolve_progress_release_fact(
                        self.db,
                        self.tenant_id,
                        workspace,
                        ref.reference,
                        payload.as_of,
                        payload.measurement_date,
                        payload.model_dump(),
                    )
                except ValueError as error:
                    self._error(409, str(error))
                if ref.content_hash and ref.content_hash != fact["release_hash"]:
                    self._error(409, "PROGRESS_ENGINEERING_EVIDENCE_HASH_MISMATCH")
                facts.append(fact)
            source["engineering_release_evidence"] = facts
        return source, denominator, rule, package

    def effective_approved(self, workspace, *, period_id=None, as_of=None, progress_type=None):
        rows = [row for row in self._rows(ProgressMeasurement, workspace) if row.status == "APPROVED"]
        if as_of is not None:
            if isinstance(as_of, str):
                as_of = date.fromisoformat(as_of)
            rows = [row for row in rows if row.as_of <= as_of]
        if period_id is not None:
            rows = [row for row in rows if row.period_id == period_id]
        # A reporting revision can supersede a measurement in a reopened period.
        # Explicit historical period reads still consume that period's own truth.
        replaced = {row.supersedes_id for row in rows if row.supersedes_id}
        rows = [row for row in rows if row.id not in replaced]
        if progress_type is not None:
            rows = [row for row in rows if row.progress_type == progress_type]
        return rows

    def _source_state(self, row):
        """Derived freshness never edits the immutable approved measurement."""
        try:
            project = self._project(row.project_workspace_id)
            current_profile = self._progress_profile(project)
            if (
                current_profile is None
                or current_profile.id != row.configuration_id
                or current_profile.content_hash != row.configuration_hash
            ):
                return "REQUIRES_REVIEW"
            payload = MeasurementIn.model_validate(row.input_json)
            sources, denominator, rule, _ = self._source_basis(row.project_workspace_id, payload, current_profile)
            original = deepcopy(row.source_snapshot)
            # Calculation inputs are frozen separately from read-only upstream identities.
            for key in (
                "previous_measurement",
                "weight_source",
                "component_measurements",
                "component_coverage",
                "component_total_weight",
                "period_reopen_predecessor",
            ):
                original.pop(key, None)
            if _hash(sources) != _hash(original):
                return "REQUIRES_REVIEW"
            _, weight_basis = self._governed_weight(row.project_workspace_id, payload, sources, denominator, rule)
            if _hash(weight_basis) != _hash(row.source_snapshot["weight_source"]):
                return "REQUIRES_REVIEW"
            reopen = row.source_snapshot.get("period_reopen_predecessor")
            if reopen:
                predecessor = self._get(ProgressMeasurement, row.project_workspace_id, reopen["measurement_id"])
                if self._reopen_basis(row.project_workspace_id, row.period_id, predecessor) != reopen:
                    return "REQUIRES_REVIEW"
            approved_ids = {candidate.id for candidate in self.effective_approved(row.project_workspace_id)}
            for component in row.source_snapshot.get("component_measurements", []):
                child = self._get(ProgressMeasurement, row.project_workspace_id, component["id"])
                if (
                    child.id not in approved_ids
                    or child.content_hash != component["content_hash"]
                    or self._source_state(child) != "CURRENT"
                ):
                    return "REQUIRES_REVIEW"
            if row.rule_id:
                rules = [
                    rule
                    for rule in self._rows(ProgressRule, row.project_workspace_id)
                    if rule.status == "PUBLISHED" and rule.code == sources["rule"]["code"]
                ]
                if any(rule.id != row.rule_id and rule.revision > sources["rule"]["revision"] for rule in rules):
                    return "REQUIRES_REVIEW"
            return "CURRENT"
        except (HTTPException, KeyError, TypeError, ValueError):
            return "REQUIRES_REVIEW"

    def _measurement_out(self, row):
        approved = [
            candidate
            for candidate in self._rows(ProgressMeasurement, row.project_workspace_id)
            if candidate.status == "APPROVED"
        ]
        successors = {candidate.supersedes_id for candidate in approved if candidate.supersedes_id}
        return self._out(row) | {
            "effective_status": "SUPERSEDED" if row.id in successors else row.status,
            "source_state": self._source_state(row),
            "progress_unit": "PERCENT_0_100",
            "period_quantity_unit": row.unit,
            "cumulative_quantity_unit": row.unit,
            "period_progress_unit": "PERCENTAGE_POINTS",
            "variance": "QUANTITY_OVERRUN" if row.overrun else None,
        }

    @staticmethod
    def _subject(payload):
        if payload.activity_external_id:
            identity = f"ACTIVITY:{payload.schedule_version_id}:{payload.activity_external_id}"
        elif payload.work_package_id:
            identity = f"PACKAGE:{payload.work_package_id}"
        elif payload.plan_item_id:
            identity = f"PLAN:{payload.plan_item_id}"
        elif payload.scope_item_id:
            identity = f"SCOPE:{payload.scope_item_id}"
        elif payload.control_account_id:
            identity = f"CONTROL_ACCOUNT:{payload.control_account_id}"
        elif payload.area:
            identity = f"AREA:{payload.area}"
        elif payload.system:
            identity = f"SYSTEM:{payload.system}"
        elif payload.discipline:
            identity = f"DISCIPLINE:{payload.discipline}"
        else:
            identity = "PROJECT_DERIVED"
        phase = {"INSTALL": "INSTALL", "REMOVE": "REMOVE"}.get(payload.scope_nature, payload.phase)
        return f"{identity}:{payload.scope_nature}:{phase}"

    def _previous_period_measurement(self, workspace, payload, subject):
        rows = [
            row
            for row in self.effective_approved(workspace, as_of=payload.as_of, progress_type=payload.progress_type)
            if row.subject_key == subject and row.period_id != payload.period_id
        ]
        earlier = [
            row
            for row in rows
            if self._get(ProjectControlsPeriod, workspace, row.period_id).period_end
            < self._get(ProjectControlsPeriod, workspace, payload.period_id).period_start
        ]
        return max(earlier, key=lambda row: (row.as_of, row.revision, row.id)) if earlier else None

    def _period_family(self, workspace, identity):
        period, seen = self._get(ProjectControlsPeriod, workspace, identity), set()
        while period.reopen_parent_id:
            if period.id in seen:
                self._error(409, "PROGRESS_REOPEN_PERIOD_CYCLE")
            seen.add(period.id)
            period = self._get(ProjectControlsPeriod, workspace, period.reopen_parent_id)
        return period.id

    @staticmethod
    def _periods_overlap(first, second):
        return first.period_start <= second.period_end and second.period_start <= first.period_end

    def _reopen_basis(self, workspace, period_id, predecessor):
        """An explicit O1A reopen is the only cross-period successor authority."""
        current = self._get(ProjectControlsPeriod, workspace, period_id)
        original = self._get(ProjectControlsPeriod, workspace, predecessor.period_id)
        basis_fields = (
            "period_code",
            "period_start",
            "period_end",
            "cutoff_at",
            "timezone",
            "schedule_data_date",
            "configuration_id",
            "source_configuration_revision",
            "source_configuration_hash",
        )
        if any(getattr(current, key) != getattr(original, key) for key in basis_fields):
            self._error(422, "PROGRESS_REOPEN_PERIOD_BASIS_MISMATCH")
        cursor, seen = current, set()
        while cursor.id != original.id:
            if cursor.id in seen or cursor.reopen_parent_id is None:
                self._error(422, "PROGRESS_REOPEN_LINEAGE_REQUIRED")
            seen.add(cursor.id)
            parent = self._get(ProjectControlsPeriod, workspace, cursor.reopen_parent_id)
            if parent.status not in {"CLOSED", "PUBLISHED"} or parent.revision >= cursor.revision:
                self._error(422, "PROGRESS_REOPEN_LINEAGE_REQUIRED")
            if any(getattr(cursor, key) != getattr(parent, key) for key in basis_fields):
                self._error(422, "PROGRESS_REOPEN_PERIOD_BASIS_MISMATCH")
            cursor = parent
        if not seen:
            self._error(422, "PROGRESS_REOPEN_LINEAGE_REQUIRED")
        return {
            "measurement_id": predecessor.id,
            "measurement_hash": predecessor.content_hash,
            "period_id": original.id,
            "period_revision": original.revision,
            "reopen_period_id": current.id,
            "reopen_period_revision": current.revision,
            "configuration_id": original.configuration_id,
            "configuration_hash": original.source_configuration_hash,
        }

    @staticmethod
    def _coverage(row):
        # Component coverage, never a caller-supplied parent label, owns the
        # represented work of a weighted aggregate (including nested PHYSICAL).
        if row.method == "WEIGHTED_COMPONENTS":
            return {tuple(item) for item in row.source_snapshot.get("component_coverage", [])}
        phase = {"INSTALL": "INSTALL", "REMOVE": "REMOVE"}.get(row.scope_nature, row.phase)
        return {(identity, phase) for identity in row.source_snapshot.get("scope_item_ids", [])} or {
            (row.subject_key, phase)
        }

    def _governed_weight(self, workspace, payload, source, denominator, rule):
        if payload.weighting_basis == "MANUAL_APPROVED_WEIGHT":
            return payload.weight, {
                "authority": "INDEPENDENT_MEASUREMENT_APPROVAL",
                "basis": payload.weighting_basis,
                "weight": str(payload.weight),
                "source_reference": payload.source_reference,
            }
        if payload.weighting_basis == "QUANTITY" and denominator is not None:
            weight = rounded(denominator)
            basis = {"authority": "APPROVED_DENOMINATOR", "unit": source["denominator_unit"], "weight": str(weight)}
        elif payload.weighting_basis == "BUDGET":
            approved = [row for row in self._rows(CostBaseline, workspace) if row.status == "APPROVED"]
            superseded = {row.previous_baseline_id for row in approved if row.previous_baseline_id}
            leaves = [row for row in approved if row.id not in superseded]
            if len(leaves) != 1:
                self._error(422, "PROGRESS_APPROVED_BUDGET_WEIGHT_REQUIRED")
            dimensions = {
                field: getattr(payload, field)
                for field in ("scope_item_id", "plan_item_id", "work_package_id", "control_account_id")
                if getattr(payload, field)
            }
            selected = [
                line
                for line in leaves[0].snapshot_json["lines"]
                if dimensions
                and line.get("cost_class") != "MANAGEMENT_RESERVE"
                and all(line.get(field) == identity for field, identity in dimensions.items())
            ]
            if not selected or len({line["currency"] for line in selected}) != 1:
                self._error(422, "PROGRESS_UNAMBIGUOUS_BUDGET_WEIGHT_REQUIRED")
            weight = rounded(sum(number(line["amount"]) for line in selected))
            basis = {
                "authority": "APPROVED_COST_BASELINE",
                "cost_baseline_id": leaves[0].id,
                "cost_baseline_hash": leaves[0].content_hash,
                "line_ids": [line["id"] for line in selected],
                "currency": selected[0]["currency"],
                "weight": str(weight),
            }
        else:
            basis = rule.measurement_basis if rule else {}
            identities = [
                field for field in ("scope_item_id", "plan_item_id", "work_package_id") if getattr(payload, field)
            ]
            if (
                not basis
                or basis.get("weighting_basis") != payload.weighting_basis
                or not basis.get("weight")
                or not basis.get("source_reference")
                or not any(basis.get(field) == getattr(payload, field) for field in identities)
            ):
                self._error(422, "PROGRESS_PUBLISHED_WEIGHT_BASIS_REQUIRED")
            weight = rounded(basis["weight"])
            basis = {"authority": "PUBLISHED_RULE", "rule_id": rule.id, "rule_hash": rule.content_hash, **basis}
        if weight <= 0 or number(payload.weight) != weight:
            self._error(422, "PROGRESS_WEIGHT_MUST_MATCH_GOVERNED_SOURCE")
        return weight, deepcopy(basis)

    @staticmethod
    def _weight_signature(row):
        basis = row.source_snapshot.get("weight_source", {})
        return row.weighting_basis, basis.get("currency") or basis.get("unit") or "APPROVED_RELATIVE_WEIGHT"

    def _calculation(self, workspace, payload, profile, source, denominator, rule, package, predecessor=None):
        source_denominator = denominator
        if (
            payload.progress_type not in profile.content_json["allowed_progress_types"]
            or payload.method not in profile.content_json["allowed_methods"]
        ):
            self._error(422, "PROGRESS_TYPE_OR_METHOD_DISABLED")
        if payload.method not in profile.content_json["methods_by_scope_nature"][payload.scope_nature]:
            self._error(422, "PROGRESS_NATURE_METHOD_DISABLED")
        if package and payload.method not in profile.content_json["package_methods"].get(package.package_type, []):
            self._error(422, "PROGRESS_PACKAGE_METHOD_DISABLED")
        expected_phases = {
            "INSTALL": {"INSTALL", "EXECUTE"},
            "REMOVE": {"REMOVE", "EXECUTE"},
            "TEMPORARY": {"INSTALL", "USE", "REMOVE"},
            "MAINTENANCE": {"INTERVENTION", "RESTORATION"},
        }
        if payload.phase not in expected_phases[payload.scope_nature]:
            self._error(422, "PROGRESS_NATURE_PHASE_REQUIRED")
        if (
            payload.progress_type == "QUANTITY"
            and payload.method != "QUANTITY_BASED"
            or payload.progress_type == "MILESTONE"
            and payload.method not in {"MILESTONE_BASED", "STEP_METHOD", "RULE_OF_CREDIT"}
            or payload.progress_type == "WEIGHTED"
            and payload.method != "WEIGHTED_COMPONENTS"
        ):
            self._error(422, "PROGRESS_TYPE_METHOD_MISMATCH")
        if payload.weighting_basis not in profile.content_json["weighting_rules"]["allowed_bases"]:
            self._error(422, "PROGRESS_WEIGHTING_BASIS_DISABLED")
        subject = self._subject(payload)
        previous = self._previous_period_measurement(workspace, payload, subject)
        if previous and (
            previous.unit != payload.unit or previous.denominator != denominator and payload.method == "QUANTITY_BASED"
        ):
            self._error(409, "PROGRESS_PRIOR_DENOMINATOR_OR_UNIT_REQUIRES_REVIEW")
        previous_quantity = previous.numerator if previous else number(0)
        if previous:
            source["previous_measurement"] = {
                "id": previous.id,
                "content_hash": previous.content_hash,
                "as_of": str(previous.as_of),
            }
        numerator = number(payload.numerator)
        if payload.method == "QUANTITY_BASED":
            if payload.components or payload.completed_steps:
                self._error(422, "PROGRESS_METHOD_INPUTS_AMBIGUOUS")
            if payload.input_mode == "PERIOD_DELTA":
                numerator += previous_quantity
            value = percentage(numerator, denominator, allow_overrun=payload.progress_type == "QUANTITY")
        elif payload.method in {"RULE_OF_CREDIT", "STEP_METHOD", "MILESTONE_BASED"}:
            if (
                rule is None
                or rule.method != payload.method
                or payload.components
                or payload.numerator != 0
                or payload.input_mode != "CUMULATIVE"
            ):
                self._error(422, "PROGRESS_PUBLISHED_RULE_AND_COMPLETION_REQUIRED")
            numerator = credit_progress(rule.steps_json, payload.completed_steps, ordered=rule.ordered)
            denominator, value = number(100), numerator
            if payload.unit != "%":
                self._error(422, "PROGRESS_PERCENT_UNIT_REQUIRED")
        elif payload.method == "WEIGHTED_COMPONENTS":
            if (
                not payload.components
                or payload.numerator != 0
                or payload.completed_steps
                or payload.input_mode != "CUMULATIVE"
            ):
                self._error(422, "PROGRESS_WEIGHTED_COMPONENTS_REQUIRED")
            components, seen, identities, bases, signatures = [], set(), set(), set(), set()
            for component in payload.components:
                candidate = self._get(ProgressMeasurement, workspace, component.measurement_id)
                if (
                    candidate.id in identities
                    or candidate not in self.effective_approved(workspace)
                    or candidate.period_id != payload.period_id
                    or candidate.as_of != payload.as_of
                    or candidate.overrun
                    or candidate.progress_type not in {"QUANTITY", "PHYSICAL", "MILESTONE"}
                    or candidate.source_snapshot.get("scope_baseline_id") != source["scope_baseline_id"]
                    or self._source_state(candidate) != "CURRENT"
                ):
                    self._error(409, "PROGRESS_APPROVED_COMPATIBLE_COMPONENT_REQUIRED")
                if number(component.weight) != candidate.weight:
                    self._error(422, "PROGRESS_COMPONENT_WEIGHT_OVERRIDE_FORBIDDEN")
                coverage = self._coverage(candidate)
                if not coverage:
                    self._error(422, "PROGRESS_COMPONENT_COVERAGE_REQUIRED")
                if payload.plan_item_id:
                    if candidate.plan_item_id is not None and candidate.plan_item_id != payload.plan_item_id:
                        self._error(422, "PROGRESS_COMPONENT_OUTSIDE_SUBJECT_COVERAGE")
                    if candidate.plan_item_id is None:
                        # A whole-Scope component cannot stand in for an
                        # unallocated subset of that Scope within a Plan.
                        allocations = {
                            item["scope_item_id"]: (number(item["quantity"]), item["unit"])
                            for item in source.get("plan_allocations", [])
                        }
                        full = {
                            item["id"]: (
                                number(
                                    item.get("approved_quantity")
                                    if item.get("approved_quantity") is not None
                                    else item["quantity"]
                                ),
                                item["unit"],
                            )
                            for item in source["scope_items"]
                        }
                        if any(
                            allocations.get(identity) != full.get(identity) or identity not in full
                            for identity, _phase in coverage
                        ):
                            self._error(422, "PROGRESS_COMPONENT_OUTSIDE_SUBJECT_COVERAGE")
                if seen & coverage:
                    self._error(422, "PROGRESS_OVERLAPPING_COMPONENT_WORK")
                seen |= coverage
                identities.add(candidate.id)
                bases.add(candidate.weighting_basis)
                signatures.add(self._weight_signature(candidate))
                components.append(
                    {
                        "id": candidate.id,
                        "progress_value": str(candidate.progress_value),
                        "weight": str(candidate.weight),
                        "content_hash": candidate.content_hash,
                        "subject_key": candidate.subject_key,
                    }
                )
            if len(bases) != 1 or next(iter(bases)) != payload.weighting_basis or len(signatures) != 1:
                self._error(422, "PROGRESS_MIXED_WEIGHTING_BASES_FORBIDDEN")
            value, total_weight = weighted_progress(components)
            denominator = number(100)
            numerator = value
            source["component_measurements"] = components
            source["component_coverage"] = [list(item) for item in sorted(seen, key=str)]
            source["component_total_weight"] = str(total_weight)
            # A weighted value cannot be labelled as one Scope/Plan while its
            # underlying components actually represent additional work.
            covered_scope_ids = {identity for identity, _phase in seen}
            if (payload.scope_item_id or payload.plan_item_id) and not covered_scope_ids.issubset(
                set(source["scope_item_ids"])
            ):
                self._error(422, "PROGRESS_COMPONENT_OUTSIDE_SUBJECT_COVERAGE")
            if payload.unit != "%":
                self._error(422, "PROGRESS_PERCENT_UNIT_REQUIRED")
        else:
            if payload.components or payload.completed_steps or payload.unit != "%":
                self._error(422, "PROGRESS_MANUAL_PERCENT_BASIS_REQUIRED")
            if payload.input_mode == "PERIOD_DELTA":
                numerator += previous_quantity
            denominator, value = number(100), percentage(numerator, 100)
        weight, basis = self._governed_weight(workspace, payload, source, source_denominator, rule)
        source["weight_source"] = basis
        if not payload.evidence_refs:
            self._error(422, "PROGRESS_EVIDENCE_REQUIRED")
        current_approved = [
            row
            for row in self.effective_approved(
                workspace, period_id=payload.period_id, progress_type=payload.progress_type
            )
            if row.subject_key == subject
        ]
        reference = max(current_approved, key=lambda row: row.revision) if current_approved else previous
        if predecessor is not None and predecessor.status == "APPROVED" and predecessor.subject_key == subject:
            reference = predecessor
        negative = reference is not None and numerator < reference.numerator or numerator < previous_quantity
        if negative and (
            payload.correction_kind == "NONE"
            or not profile.content_json["negative_progress_policy"]["allow_corrections"]
            or not profile.content_json["rework_policy"]["enabled"]
        ):
            self._error(422, "PROGRESS_NEGATIVE_CORRECTION_REQUIRES_POLICY_AND_REASON")
        return {
            "subject_key": subject,
            "numerator": rounded(numerator),
            "denominator": rounded(denominator),
            "weight": rounded(weight),
            "progress_value": rounded(value),
            "period_quantity": rounded(numerator - previous_quantity),
            "cumulative_quantity": rounded(numerator),
            "period_progress": rounded(value - (previous.progress_value if previous else 0)),
            "overrun": numerator > denominator and payload.progress_type == "QUANTITY",
        }

    @staticmethod
    def _content(row):
        ignored = {
            "id",
            "created_at",
            "created_by",
            "version",
            "status",
            "prepared_by",
            "updated_by",
            "reviewed_by",
            "certified_by",
            "approved_by",
            "approved_at",
            "certified_at",
            "content_hash",
        }
        return {column.key: getattr(row, column.key) for column in row.__table__.columns if column.key not in ignored}

    def save_measurement(self, workspace, payload, key, identity=None, expected=None, *, successor=False):
        self._ready(workspace, "capture")

        def apply():
            _, profile = self._ready(workspace, "capture")
            period = self._period_for_measurement(workspace, payload.period_id, capture=True)
            if (
                not period.period_start <= payload.measurement_date <= period.period_end
                or payload.as_of < payload.measurement_date
            ):
                self._error(422, "PROGRESS_MEASUREMENT_DATE_OR_ASOF_INVALID")
            old = self._get(ProgressMeasurement, workspace, identity, lock=True) if identity else None
            source, denominator, rule, package = self._source_basis(workspace, payload, profile)
            values = self._calculation(
                workspace, payload, profile, source, denominator, rule, package, old if successor else None
            )
            if old:
                self._version(old.version, expected)
                if old.status not in ({"APPROVED", "REJECTED"} if successor else {"DRAFT"}):
                    self._error(409, "PROGRESS_APPROVED_MEASUREMENT_IMMUTABLE")
                if (
                    old.code != payload.code
                    or old.subject_key != values["subject_key"]
                    or old.progress_type != payload.progress_type
                ):
                    self._error(422, "PROGRESS_SUCCESSOR_IDENTITY_MISMATCH")
                if old.period_id != payload.period_id:
                    if not successor:
                        self._error(422, "PROGRESS_SUCCESSOR_IDENTITY_MISMATCH")
                    source["period_reopen_predecessor"] = self._reopen_basis(workspace, payload.period_id, old)
                if (
                    old.denominator != values["denominator"]
                    or old.source_snapshot["scope_baseline_hash"] != source["scope_baseline_hash"]
                ):
                    self._error(409, "PROGRESS_DENOMINATOR_CHANGE_REQUIRES_NEW_CONTROL_BASIS")
            elif any(row.code == payload.code for row in self._rows(ProgressMeasurement, workspace)):
                self._error(409, "PROGRESS_MEASUREMENT_CODE_EXISTS")
            data = payload.model_dump(
                exclude={
                    "numerator",
                    "input_mode",
                    "denominator_basis",
                    "weight",
                    "rule_id",
                    "completed_steps",
                    "components",
                    "evidence_refs",
                }
            )
            data.update(
                values,
                input_json=payload.model_dump(mode="json"),
                source_domain="GOVERNED_FIELD_MEASUREMENT",
                configuration_id=profile.id,
                configuration_hash=profile.content_hash,
                rule_id=rule.id if rule else None,
                source_snapshot=source,
                source_hash=_hash(source),
                evidence_json=[evidence.model_dump(mode="json") for evidence in payload.evidence_refs],
            )
            if old and not successor:
                row = old
                for field, value in data.items():
                    setattr(row, field, value)
                row.certified_by, row.certified_at = None, None
            else:
                row = ProgressMeasurement(
                    **self._base(workspace),
                    **data,
                    prepared_by=self.actor_id,
                    updated_by=self.actor_id,
                    revision=max(
                        (
                            candidate.revision
                            for candidate in self._rows(ProgressMeasurement, workspace)
                            if candidate.code == payload.code
                        ),
                        default=0,
                    )
                    + 1,
                    supersedes_id=old.id if old else None,
                )
                self.db.add(row)
            row.content_hash = _hash(self._content(row))
            result = self._record(
                row,
                "PROGRESS_REVISED" if old else "PROGRESS_MEASUREMENT_CREATED",
                payload.reason,
                changed=bool(old and not successor),
            )
            if payload.method in {"RULE_OF_CREDIT", "STEP_METHOD"}:
                self._event(
                    "RULE_OF_CREDIT_APPLIED",
                    row.id,
                    {"rule_id": row.rule_id, "content_hash": row.content_hash, "reason": payload.reason},
                )
            return result

        return self._write(
            "measurement.successor" if successor else "measurement.save",
            workspace,
            payload,
            key,
            apply,
            identity,
            expected,
        )

    def certify_measurement(self, workspace, identity, payload, expected, key):
        self._ready(workspace, "read")

        def apply():
            row = self._get(ProgressMeasurement, workspace, identity, lock=True)
            self._permission(
                "quantity.certify" if row.method == "QUANTITY_BASED" else "milestone.certify", self._project(workspace)
            )
            self._version(row.version, expected)
            self._period_for_measurement(workspace, row.period_id, row=row)
            if row.status not in {"SUBMITTED", "UNDER_REVIEW"}:
                self._error(409, "PROGRESS_SUBMITTED_CERTIFICATION_REQUIRED")
            if self.actor_id in {row.prepared_by, row.updated_by}:
                self._error(403, "PROGRESS_RECORDER_CERTIFIER_SOD")
            if self._source_state(row) != "CURRENT":
                self._error(409, "PROGRESS_SOURCE_REQUIRES_REVIEW")
            row.certified_by, row.certified_at = self.actor_id, utc_now()
            self._event(
                "PROGRESS_CERTIFICATION_EVIDENCE",
                row.id,
                {"evidence_reference": payload.evidence_reference, "certified_content_hash": row.content_hash},
            )
            # Certifying does not make the certifier the material editor.
            row.version += 1
            return self._record(
                row,
                "QUANTITY_CERTIFIED" if row.method == "QUANTITY_BASED" else "MILESTONE_CREDIT_AWARDED",
                payload.reason,
            )

        return self._write("measurement.certify", workspace, payload, key, apply, identity, expected)

    def transition_measurement(self, workspace, identity, payload, expected, key):
        action = {"SUBMITTED": "submit", "UNDER_REVIEW": "review", "APPROVED": "approve", "REJECTED": "review"}[
            payload.status
        ]
        self._ready(workspace, action)

        def apply():
            self._ready(workspace, action)
            row = self._get(ProgressMeasurement, workspace, identity, lock=True)
            self._version(row.version, expected)
            self._period_for_measurement(workspace, row.period_id, row=row)
            allowed = {
                "DRAFT": {"SUBMITTED"},
                "SUBMITTED": {"UNDER_REVIEW", "REJECTED"},
                "UNDER_REVIEW": {"APPROVED", "REJECTED"},
            }
            if payload.status not in allowed.get(row.status, set()):
                self._error(409, "PROGRESS_LIFECYCLE_INVALID")
            if payload.status in {"UNDER_REVIEW", "APPROVED", "REJECTED"} and self.actor_id in {
                row.prepared_by,
                row.updated_by,
            }:
                self._error(403, "PROGRESS_PREPARER_APPROVER_SOD")
            if payload.status != "REJECTED" and self._source_state(row) != "CURRENT":
                self._error(409, "PROGRESS_SOURCE_REQUIRES_REVIEW")
            if payload.status == "UNDER_REVIEW":
                row.reviewed_by = self.actor_id
            if payload.status == "APPROVED":
                if row.method != "MANUAL_EXPERT_ASSESSMENT" and row.certified_by is None:
                    self._error(409, "PROGRESS_INDEPENDENT_CERTIFICATION_REQUIRED")
                ancestors, pointer = set(), row.supersedes_id
                while pointer:
                    if pointer in ancestors:
                        self._error(409, "PROGRESS_SUCCESSOR_CYCLE")
                    ancestors.add(pointer)
                    pointer = self._get(ProgressMeasurement, workspace, pointer).supersedes_id
                same = [
                    candidate
                    for candidate in self.effective_approved(workspace, progress_type=row.progress_type)
                    if candidate.subject_key == row.subject_key
                ]
                period_family = self._period_family(workspace, row.period_id)
                if any(
                    self._period_family(workspace, candidate.period_id) == period_family
                    and candidate.id not in ancestors
                    for candidate in same
                ):
                    self._error(409, "PROGRESS_APPROVED_BRANCH_OR_DUPLICATE_SUBJECT")
                period = self._get(ProjectControlsPeriod, workspace, row.period_id)
                if any(
                    candidate.as_of == row.as_of
                    and self._period_family(workspace, candidate.period_id) != period_family
                    and self._periods_overlap(period, self._get(ProjectControlsPeriod, workspace, candidate.period_id))
                    for candidate in same
                ):
                    self._error(409, "PROGRESS_OVERLAPPING_PERIOD_CONTROL_BASIS")
                if any(
                    candidate.as_of > row.as_of
                    and candidate.period_id != row.period_id
                    and candidate.id not in ancestors
                    for candidate in same
                ):
                    self._error(409, "PROGRESS_RETROACTIVE_CORRECTION_REQUIRES_REOPEN")
                payload_original = MeasurementIn.model_validate(row.input_json)
                previous = self._previous_period_measurement(workspace, payload_original, row.subject_key)
                pinned_previous = row.source_snapshot.get("previous_measurement")
                if (previous.id if previous else None) != (pinned_previous.get("id") if pinned_previous else None):
                    self._error(409, "PROGRESS_CUMULATIVE_BASIS_CHANGED")
                row.approved_by, row.approved_at = self.actor_id, utc_now()
            row.status, row.version = payload.status, row.version + 1
            return self._record(row, f"PROGRESS_{payload.status}", payload.reason)

        return self._write("measurement.transition", workspace, payload, key, apply, identity, expected)

    def measurements(self, workspace, *, progress_type=None, period_id=None):
        self._permission("read", self._project(workspace))
        rows = self._rows(ProgressMeasurement, workspace)
        rows = [
            row
            for row in rows
            if (progress_type is None or row.progress_type == progress_type)
            and (period_id is None or row.period_id == period_id)
        ]
        return {"items": [self._measurement_out(row) for row in rows], "total": len(rows)}

    def overview(self, workspace):
        project = self._project(workspace)
        self._permission("read", project)
        profile = self._progress_profile(project)
        collections = {
            "scope_items": ScopeItem,
            "scope_baselines": ScopeBaseline,
            "plan_items": PlanItem,
            "packages": WorkPackage,
            "schedule_versions": ScheduleVersion,
            "schedule_baselines": ScheduleBaseline,
            "cost_baselines": CostBaseline,
            "periods": ProjectControlsPeriod,
            "control_accounts": ControlAccount,
            "rules": ProgressRule,
        }
        return {
            "context": self._operational().context(workspace),
            "version": 1,
            "authority": "GOVERNED_PROGRESS",
            "physical_progress_automatic": False,
            "allowed_actions": self.allowed_actions(project),
            "configuration": self._profile_out(profile) if profile else None,
            "measurements": self.measurements(workspace)["items"],
            "types": TYPES,
            "methods": METHODS,
            "weighting_bases": WEIGHTING_BASES,
            **{key: [self._out(row) for row in self._rows(model, workspace)] for key, model in collections.items()},
        }

    def history(self, workspace, entity_type=None, identity=None):
        self._permission("read", self._project(workspace))
        rows = [
            row
            for row in self._rows(ProgressHistory, workspace)
            if (entity_type is None or row.entity_type == entity_type)
            and (identity is None or row.entity_id == identity)
        ]
        return {"items": [self._out(row) for row in rows], "total": len(rows)}

    def aggregation(self, workspace, *, progress_type="PHYSICAL", period_id=None, as_of=None, group_by="PROJECT"):
        self._permission("read", self._project(workspace))
        fields = {
            "SCOPE": "scope_item_id",
            "PLAN": "plan_item_id",
            "PACKAGE": "work_package_id",
            "ACTIVITY": "activity_external_id",
            "CONTROL_ACCOUNT": "control_account_id",
            "WBS": "wbs_external_id",
            "AREA": "area",
            "SYSTEM": "system",
            "DISCIPLINE": "discipline",
        }
        if group_by not in {*fields, "PROJECT"} or progress_type not in {
            "QUANTITY",
            "PHYSICAL",
            "WEIGHTED",
            "MILESTONE",
        }:
            self._error(422, "PROGRESS_AGGREGATION_DIMENSION_INVALID")
        approved = self.effective_approved(workspace, period_id=period_id, as_of=as_of, progress_type=progress_type)
        # Cumulative records are snapshots, never add successive reporting periods.
        by_subject, latest, ambiguous = {}, [], set()
        periods = {period.id: period for period in self._rows(ProjectControlsPeriod, workspace)}
        for row in approved:
            by_subject.setdefault(row.subject_key, []).append(row)
        for rows in by_subject.values():
            latest_as_of = max(row.as_of for row in rows)
            contenders = [row for row in rows if row.as_of == latest_as_of]
            conflicting = any(
                self._period_family(workspace, first.period_id) != self._period_family(workspace, second.period_id)
                and self._periods_overlap(periods[first.period_id], periods[second.period_id])
                for index, first in enumerate(contenders)
                for second in contenders[index + 1 :]
            )
            if conflicting:
                latest.extend(contenders)
                ambiguous.update(row.id for row in contenders)
            else:
                latest.append(
                    max(
                        contenders,
                        key=lambda row: (
                            periods[row.period_id].period_end,
                            periods[row.period_id].revision,
                            row.revision,
                            row.id,
                        ),
                    )
                )
        groups = {}
        for row in latest:
            key = str(workspace) if group_by == "PROJECT" else str(getattr(row, fields[group_by]) or "UNMAPPED")
            groups.setdefault(key, []).append(row)
        result, all_inputs = [], []
        for key, rows in sorted(groups.items()):
            reasons, covered, bases = [], set(), {row.weighting_basis for row in rows}
            for row in rows:
                if row.id in ambiguous:
                    reasons.append("INCOMPATIBLE_PERIOD_LINEAGES")
                if self._source_state(row) != "CURRENT":
                    reasons.append("SOURCE_REQUIRES_REVIEW")
                if row.overrun:
                    reasons.append("QUANTITY_OVERRUN")
                coverage = self._coverage(row)
                if not coverage:
                    reasons.append("PROGRESS_COMPONENT_COVERAGE_REQUIRED")
                if covered & coverage:
                    reasons.append("OVERLAPPING_WORK_MEASUREMENTS")
                covered |= coverage
            if len(bases) != 1:
                reasons.append("INCOMPATIBLE_WEIGHTING_BASES")
            if len({self._weight_signature(row) for row in rows}) != 1:
                reasons.append("INCOMPATIBLE_WEIGHT_UNIT_OR_CURRENCY")
            if len({row.source_snapshot.get("scope_baseline_hash") for row in rows}) != 1:
                reasons.append("INCOMPATIBLE_CONTROL_BASIS")
            inputs = [
                {
                    "id": row.id,
                    "progress_value": str(row.progress_value),
                    "weight": str(row.weight),
                    "content_hash": row.content_hash,
                    "source_hash": row.source_hash,
                }
                for row in rows
            ]
            value, total = (None, sum(row.weight for row in rows)) if reasons else weighted_progress(inputs)
            result.append(
                {
                    "key": key,
                    "progress_value": str(value) if value is not None else None,
                    "total_weight": str(total),
                    "input_ids": [row.id for row in rows],
                    "weighting_basis": next(iter(bases)) if len(bases) == 1 else None,
                    "status": "NOT_COMPUTABLE" if reasons else "COMPUTABLE",
                    "reason_codes": sorted(set(reasons)),
                }
            )
            all_inputs.extend(inputs)
        return {
            "items": result,
            "inputs_snapshot": all_inputs,
            "content_hash": _hash(all_inputs),
            "authority": "BACKEND_DERIVED_APPROVED_PROGRESS",
            "progress_unit": "PERCENT_0_100",
            "group_by": group_by,
            "progress_type": progress_type,
        }

    def schedule_progress(self, workspace, *, as_of=None, period_id=None):
        self._permission("read", self._project(workspace))
        period = self._get(ProjectControlsPeriod, workspace, period_id) if period_id else None
        items = []
        for version in self._rows(ScheduleVersion, workspace):
            if version.status != "ACCEPTED_CURRENT":
                continue
            for row in version.snapshot_json.get("activities", []):
                percent = row.get("percent_complete")
                value = None
                reasons = []
                try:
                    if percent is not None:
                        value = percentage(str(percent), 100)
                except ValueError:
                    pass
                if value is None:
                    reasons.append("SCHEDULE_PERCENT_COMPLETE_UNAVAILABLE_OR_INVALID")
                if as_of and version.data_date:
                    try:
                        data_day = date.fromisoformat(str(version.data_date)[:10])
                        if data_day > date.fromisoformat(str(as_of)):
                            value = None
                            reasons.append("SCHEDULE_DATA_DATE_AFTER_AS_OF")
                    except ValueError:
                        value = None
                        reasons.append("SCHEDULE_DATA_DATE_INVALID")
                items.append(
                    {
                        "schedule_version_id": version.id,
                        "activity_external_id": str(row["external_id"]),
                        "progress_type": "SCHEDULE",
                        "method": "P6_ACCEPTED_PERCENT_COMPLETE",
                        "source_domain": "SCHEDULE",
                        "progress_value": str(value) if value is not None else None,
                        "result": "COMPUTABLE" if value is not None else "NOT_COMPUTABLE",
                        "reason_codes": reasons,
                        "source_snapshot": {
                            "schedule_hash": version.content_hash,
                            "schedule_data_date": version.data_date,
                            "status": row.get("status"),
                            "actual_start": row.get("actual_start"),
                            "actual_finish": row.get("actual_finish"),
                            "remaining_duration": row.get("remaining_duration"),
                            "percent_complete_type": row.get("percent_complete_type"),
                        },
                        "as_of": str(as_of) if as_of else None,
                        "period_id": period.id if period else None,
                        "cutoff_at": period.cutoff_at.isoformat() if period else None,
                    }
                )
        return {"items": items, "authority": "SCHEDULE_READ_PROJECTION", "physical_progress_automatic": False}

    def cost_progress(self, workspace, *, as_of=None, period_id=None):
        self._permission("read", self._project(workspace))
        from app.modules.cost_foundation.financials import CostFinancialService
        from app.modules.cost_foundation.models import BudgetLine, BudgetVersion

        cost = CostFinancialService(self.db, self.tenant_id, self.actor_id)
        period = self._get(ProjectControlsPeriod, workspace, period_id) if period_id else None
        as_of = as_of or (period.period_end if period else None)
        actual = cost.actuals(workspace, as_of=as_of)["recognized"]
        budgets = [row for row in self._rows(BudgetVersion, workspace) if row.status == "APPROVED"]
        previous = {row.predecessor_id for row in budgets if row.predecessor_id}
        leaves = [row for row in budgets if row.id not in previous]
        lines = [
            row
            for row in self._rows(BudgetLine, workspace)
            if len(leaves) == 1 and row.budget_version_id == leaves[0].id and row.cost_class != "MANAGEMENT_RESERVE"
        ]
        totals = {}
        for line in lines:
            totals[line.currency] = totals.get(line.currency, number(0)) + line.amount
        value, raw_ratio, reasons = None, None, []
        if len(totals) != 1 or actual.get("amount") is None or actual.get("currency") not in totals:
            reasons.append("COST_CURRENCY_OR_CONTROL_BASIS_INCOMPATIBLE")
        else:
            denominator = next(iter(totals.values()))
            if denominator <= 0:
                reasons.append("COST_ZERO_DENOMINATOR")
            else:
                try:
                    value, raw_ratio = cost_progress_ratio(actual["amount"], denominator)
                    if value is None:
                        reasons.append("COST_PROGRESS_BOUNDS_EXCEEDED")
                except (ValueError, DecimalException):
                    reasons.append("COST_RATIO_OUT_OF_RANGE")
        return {
            "items": [
                {
                    "metric": "RECOGNIZED_ACTUAL_OVER_CURRENT_BUDGET",
                    "progress_type": "COST",
                    "progress_value": str(value) if value is not None else None,
                    "raw_ratio": str(raw_ratio) if raw_ratio is not None else None,
                    "result": "NOT_COMPUTABLE" if reasons else "COMPUTABLE",
                    "reason_codes": reasons,
                    "overrun": raw_ratio is not None and raw_ratio > 100,
                    "variance_flags": ["COST_OVER_BUDGET"] if raw_ratio is not None and raw_ratio > 100 else [],
                    "source_snapshot": {
                        "actual": actual,
                        "budget_id": leaves[0].id if len(leaves) == 1 else None,
                        "budget_hash": leaves[0].content_hash if len(leaves) == 1 else None,
                        "by_currency": {key: str(value) for key, value in totals.items()},
                        "cost_recognition_as_of": str(as_of) if as_of else None,
                        "period_id": period_id,
                    },
                }
            ],
            "authority": "COST_READ_PROJECTION",
            "physical_progress_automatic": False,
        }
