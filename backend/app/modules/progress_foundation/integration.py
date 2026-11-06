"""Governed baseline references, period reporting and read-only earned performance."""

from copy import deepcopy
from datetime import date

from fastapi import HTTPException
from sqlalchemy import inspect, select

from app.core.time import utc_now
from app.modules.awp.models import PackageMapping, WorkPackage
from app.modules.awp.service import AWPService
from app.modules.basic_data.service import _hash, _json
from app.modules.cost_foundation.financial_models import CostActualEntry
from app.modules.cost_foundation.models import ControlAccount, CostBaseline
from app.modules.cost_foundation.service import CostFoundationService
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.operational_context.models import ProjectControlsPeriod
from app.modules.operational_context.schemas import ActionIn
from app.modules.operational_context.service import OperationalContextService
from app.modules.progress_foundation.integration_models import (
    EarnedValueSnapshot,
    ProgressPeriodSnapshot,
    ProjectControlBaselineBundle,
)
from app.modules.progress_foundation.integration_policy import (
    EARNED_SOURCES,
    ZERO,
    earned_amount,
    evm_values,
    value,
)
from app.modules.progress_foundation.models import ProgressHistory, ProgressMeasurement
from app.modules.progress_foundation.service import ProgressFoundationService
from app.modules.schedule_foundation.models import ScheduleBaseline, ScheduleVersion
from app.modules.schedule_foundation.service import ScheduleFoundationService
from app.modules.scope_foundation.models import PlanItem, PlanItemScopeLink, ScopeBaseline
from app.modules.scope_foundation.service import ScopeFoundationService


def _period_identity(period):
    return _json(
        {
            key: getattr(period, key)
            for key in (
                "id",
                "tenant_id",
                "project_workspace_id",
                "revision",
                "period_start",
                "period_end",
                "cutoff_at",
                "timezone",
                "schedule_data_date",
                "configuration_id",
                "source_configuration_hash",
                "reopen_parent_id",
            )
        }
    )


class ProgressIntegrationService(ProgressFoundationService):
    def _bundle_row(self, workspace, identity, *, lock=False):
        return self._get(ProjectControlBaselineBundle, workspace, identity, lock=lock)

    def _scoped_reference(self, model, workspace, identity, label, reasons):
        row = self.db.scalar(
            select(model).where(
                model.id == identity, model.tenant_id == self.tenant_id, model.project_workspace_id == workspace
            )
        )
        if row is None:
            reasons.append(f"{label}_NOT_FOUND_IN_PROJECT")
        return row

    def _phasing_period_sources(self, workspace, phases, operational_policy, reasons):
        """Resolve each approved phase against its own immutable O1A period identity."""
        sources = {}
        for phase in phases:
            identity = phase.get("period_id")
            if identity is None:
                continue
            period = self._scoped_reference(
                ProjectControlsPeriod, workspace, identity, "COST_BASELINE_PHASE_PERIOD", reasons
            )
            if period is None:
                continue
            if period.configuration_id != operational_policy.get(
                "configuration_id"
            ) or period.source_configuration_hash != operational_policy.get("hash"):
                reasons.append("COST_BASELINE_PHASE_PERIOD_POLICY_MISMATCH")
            for point in phase.get("spread_json", []):
                point_date = date.fromisoformat(point["date"][:10])
                if not period.period_start <= point_date <= period.period_end:
                    reasons.append("COST_BASELINE_PHASE_DATE_PERIOD_MISMATCH")
            sources[identity] = _period_identity(period)
        return [sources[identity] for identity in sorted(sources)]

    def _bundle_sources(self, workspace, values, profile):
        """Resolve the full reference set atomically. No source records are changed."""
        reasons = []
        scope = self._scoped_reference(ScopeBaseline, workspace, values.scope_baseline_id, "SCOPE_BASELINE", reasons)
        schedule = self._scoped_reference(
            ScheduleBaseline, workspace, values.schedule_baseline_id, "SCHEDULE_BASELINE", reasons
        )
        cost = self._scoped_reference(CostBaseline, workspace, values.cost_baseline_id, "COST_BASELINE", reasons)
        if reasons:
            return {}, reasons
        current_scope = ScopeFoundationService(
            self.db, self.tenant_id, self.actor_id, self.access_context
        )._current_baseline(workspace)
        if not current_scope or scope.id != current_scope.id:
            reasons.append("SCOPE_BASELINE_NOT_CURRENT")
        if _hash(scope.snapshot_json) != scope.content_hash:
            reasons.append("SCOPE_BASELINE_HASH_MISMATCH")
        if schedule.status != "APPROVED_BASELINE":
            reasons.append("APPROVED_SCHEDULE_BASELINE_REQUIRED")
        if cost.status != "APPROVED":
            reasons.append("APPROVED_COST_BASELINE_REQUIRED")
        if _hash(schedule.snapshot_json) != schedule.content_hash or _hash(cost.snapshot_json) != cost.content_hash:
            reasons.append("SOURCE_BASELINE_HASH_MISMATCH")
        approved_schedule = [
            r
            for r in self._rows(ScheduleBaseline, workspace)
            if r.register_id == schedule.register_id and r.status == "APPROVED_BASELINE"
        ]
        if approved_schedule and max(approved_schedule, key=lambda r: r.revision).id != schedule.id:
            reasons.append("SCHEDULE_BASELINE_SUPERSEDED")
        approved_cost = [r for r in self._rows(CostBaseline, workspace) if r.status == "APPROVED"]
        if any(r.previous_baseline_id == cost.id for r in approved_cost):
            reasons.append("COST_BASELINE_SUPERSEDED")
        version = self._scoped_reference(
            ScheduleVersion, workspace, schedule.schedule_version_id, "SCHEDULE_VERSION", reasons
        )
        if version and (
            version.status not in {"ACCEPTED_CURRENT", "SUPERSEDED"} or version.scope_baseline_id != scope.id
        ):
            reasons.append("SCHEDULE_SCOPE_BASIS_MISMATCH")
        frozen_version_hash = schedule.snapshot_json.get("schedule_content_hash")
        if version and version.content_hash != frozen_version_hash:
            reasons.append("SCHEDULE_SOURCE_HASH_CHANGED")
        if profile is None or profile.status != "published" or profile.kind != "progress_profile":
            reasons.append("PUBLISHED_PROGRESS_PROFILE_REQUIRED")
            return {}, reasons
        effective = values.effective_date
        for key, exclusive in (("effective_from", False), ("effective_to", True)):
            boundary = profile.content_json.get(key)
            if boundary and (
                effective >= date.fromisoformat(str(boundary)[:10])
                if exclusive
                else effective < date.fromisoformat(str(boundary)[:10])
            ):
                reasons.append("PROGRESS_PROFILE_EFFECTIVE_DATE_MISMATCH")
        scope_ids = {int(row["id"]) for row in scope.snapshot_json.get("items", [])}
        plans = {r.id: r for r in self._rows(PlanItem, workspace)}
        packages = {r.id: r for r in self._rows(WorkPackage, workspace)}
        plan_links = self._rows(PlanItemScopeLink, workspace)
        schedule_maps = deepcopy(schedule.snapshot_json.get("mappings", []))
        if version is not None:
            current_maps = ScheduleFoundationService(
                self.db, self.tenant_id, self.actor_id, self.access_context
            )._effective_mappings(version)
            if _hash(current_maps) != _hash(schedule_maps):
                reasons.append("SCHEDULE_MAPPING_REBASE_REQUIRED")
        schedule_activity_ids = {
            str(row["external_id"]) for row in schedule.snapshot_json.get("schedule_snapshot", {}).get("activities", [])
        }
        schedule_wbs_ids = {
            str(row["external_id"]) for row in schedule.snapshot_json.get("schedule_snapshot", {}).get("wbs", [])
        }
        for mapping in schedule_maps:
            if mapping.get("status") != "VALID":
                reasons.append("STALE_SCHEDULE_MAPPING")
            if (
                mapping.get("target_kind") == "ACTIVITY"
                and str(mapping.get("target_external_id")) not in schedule_activity_ids
            ):
                reasons.append("BROKEN_ACTIVITY_IDENTITY")
            if mapping.get("target_kind") == "WBS" and str(mapping.get("target_external_id")) not in schedule_wbs_ids:
                reasons.append("BROKEN_WBS_IDENTITY")
            if not set(mapping.get("resolved_scope_item_ids", mapping.get("scope_item_ids", []))).issubset(scope_ids):
                reasons.append("SCHEDULE_SCOPE_MAPPING_CHANGED")
            for identity in mapping.get("plan_item_ids", []):
                if identity not in plans or plans[identity].status != "PUBLISHED":
                    reasons.append("BROKEN_PLAN_MAPPING")
        cost_service = CostFoundationService(self.db, self.tenant_id, self.actor_id, self.access_context)
        cost_maps = [self._out(row) for row in cost_service._effective_mappings(workspace)]
        frozen_cost_maps = cost.snapshot_json.get("source_mappings", [])
        if _hash(cost_maps) != _hash(frozen_cost_maps):
            reasons.append("COST_MAPPING_REBASE_REQUIRED")
        relevant_plan_ids, relevant_package_ids = set(), set()
        lines = deepcopy(cost.snapshot_json.get("lines", []))
        # Line references are also mapping roots. They cannot be omitted merely
        # because the optional Cost source-mapping register has no matching row.
        relevant_plan_ids.update(line["plan_item_id"] for line in lines if line.get("plan_item_id"))
        relevant_package_ids.update(line["work_package_id"] for line in lines if line.get("work_package_id"))
        for mapping in cost_maps:
            kind, identity = mapping["source_kind"], mapping.get("source_id")
            if kind == "SCOPE" and identity not in scope_ids:
                reasons.append("COST_SCOPE_MAPPING_CHANGED")
            if kind == "PLAN":
                relevant_plan_ids.add(identity)
                if identity not in plans or plans[identity].status != "PUBLISHED":
                    reasons.append("BROKEN_PLAN_MAPPING")
            if kind == "PACKAGE":
                relevant_package_ids.add(identity)
                if identity not in packages or packages[identity].status in {"CLOSED", "SUPERSEDED"}:
                    reasons.append("BROKEN_PACKAGE_MAPPING")
            if kind in {"ACTIVITY", "WBS"}:
                if not version or mapping.get("schedule_version_id") != version.id:
                    reasons.append("COST_SCHEDULE_VERSION_MISMATCH")
                identities = schedule_activity_ids if kind == "ACTIVITY" else schedule_wbs_ids
                if mapping.get("source_external_id") not in identities:
                    reasons.append("BROKEN_ACTIVITY_IDENTITY" if kind == "ACTIVITY" else "BROKEN_WBS_IDENTITY")
        package_maps = AWPService._effective_records(self._rows(PackageMapping, workspace), "work_package_id")
        relevant_package_maps = [r for r in package_maps if r.work_package_id in relevant_package_ids]
        for mapping in relevant_package_maps:
            if mapping.target_kind == "SCOPE" and mapping.target_id not in scope_ids:
                reasons.append("BROKEN_PACKAGE_SCOPE_MAPPING")
            if mapping.target_kind == "PLAN":
                relevant_plan_ids.add(mapping.target_id)
                if mapping.target_id not in plans or plans[mapping.target_id].status != "PUBLISHED":
                    reasons.append("BROKEN_PACKAGE_PLAN_MAPPING")
            if mapping.target_kind == "ACTIVITY" and (
                not version
                or mapping.schedule_version_id != version.id
                or mapping.activity_external_id not in schedule_activity_ids
            ):
                reasons.append("STALE_PACKAGE_ACTIVITY_MAPPING")
        for identity in relevant_plan_ids:
            if not any(r.plan_item_id == identity and r.scope_item_id in scope_ids for r in plan_links):
                reasons.append("PLAN_SCOPE_ALLOCATION_REQUIRED")
        account_ids = {int(row["id"]) for row in cost.snapshot_json.get("control_structures", {}).get("accounts", [])}
        for line in lines:
            if line.get("scope_item_id") and line["scope_item_id"] not in scope_ids:
                reasons.append("COST_LINE_SCOPE_BASIS_MISMATCH")
            if line.get("scope_item_id"):
                lineage = line.get("source_json", {}).get("scope", {}).get("cost_source_lineage", {})
                if (
                    lineage.get("scope_baseline_id") != scope.id
                    or lineage.get("scope_baseline_hash") != scope.content_hash
                ):
                    reasons.append("COST_SCOPE_BASELINE_REBASE_REQUIRED")
            if line.get("plan_item_id"):
                identity = line["plan_item_id"]
                relevant_plan_ids.add(identity)
                if identity not in plans or plans[identity].status != "PUBLISHED":
                    reasons.append("BROKEN_PLAN_MAPPING")
            if line.get("work_package_id"):
                identity = line["work_package_id"]
                relevant_package_ids.add(identity)
                if identity not in packages or packages[identity].status in {"CLOSED", "SUPERSEDED"}:
                    reasons.append("BROKEN_PACKAGE_MAPPING")
            if line.get("control_account_id") and line["control_account_id"] not in account_ids:
                reasons.append("CONTROL_ACCOUNT_NOT_IN_BASELINE")
        currency = cost.snapshot_json.get("budget", {}).get("currency", "")
        if not currency or any(row.get("currency") != currency for row in lines):
            reasons.append("BASELINE_CURRENCY_MISMATCH")
        if any(row.get("currency") != currency for row in cost.snapshot_json.get("phasing", [])):
            reasons.append("PHASING_CURRENCY_MISMATCH")
        coverage = value(profile.content_json.get("baseline_policy", {}).get("control_account_coverage_percent", "0"))
        total = sum((value(row["amount"]) for row in lines), ZERO)
        covered = sum((value(row["amount"]) for row in lines if row.get("control_account_id")), ZERO)
        if coverage > ZERO and (total <= ZERO or covered * 100 < total * coverage):
            reasons.append("CONTROL_ACCOUNT_COVERAGE_BELOW_POLICY")
        operational_profile = OperationalContextService(
            self.db, self.tenant_id, self.actor_id, self.access_context
        )._effective_profile(self._project(workspace))
        if operational_profile is None:
            reasons.append("PUBLISHED_OPERATIONAL_PERIOD_POLICY_REQUIRED")
        operational_policy = (
            {
                "configuration_id": operational_profile.id,
                "revision": operational_profile.revision,
                "hash": operational_profile.content_hash,
            }
            if operational_profile
            else {}
        )
        phasing_periods = self._phasing_period_sources(
            workspace, cost.snapshot_json.get("phasing", []), operational_policy, reasons
        )
        snapshot = {
            "scope_baseline": {"id": scope.id, "revision": scope.revision, "hash": scope.content_hash},
            "schedule_baseline": {
                "id": schedule.id,
                "revision": schedule.revision,
                "hash": schedule.content_hash,
                "schedule_version_id": schedule.schedule_version_id,
            },
            "cost_baseline": {"id": cost.id, "revision": cost.revision, "hash": cost.content_hash},
            "progress_profile": {
                "id": profile.id,
                "revision": profile.revision,
                "hash": profile.content_hash,
                "content": deepcopy(profile.content_json),
            },
            "effective_date": effective.isoformat(),
            "currency": currency,
            "schedule_mappings": schedule_maps,
            "cost_mappings": cost_maps,
            "package_mappings": [self._out(row) for row in relevant_package_maps],
            "plans": [self._out(plans[i]) for i in sorted(relevant_plan_ids) if i in plans],
            "plan_allocations": [self._out(row) for row in plan_links if row.plan_item_id in relevant_plan_ids],
            "packages": [
                {key: getattr(packages[i], key) for key in ("id", "package_code", "package_type")}
                for i in sorted(relevant_package_ids)
                if i in packages
            ],
            "control_accounts": [
                self._out(row) for row in self._rows(ControlAccount, workspace) if row.id in account_ids
            ],
            "period_policy": deepcopy(profile.content_json.get("period_policy", {})),
            "operational_period_policy": operational_policy or None,
            "phasing_periods": phasing_periods,
            "control_account_coverage": {
                "required_percent": str(coverage),
                "budget_amount": str(total),
                "covered_amount": str(covered),
            },
        }
        return _json(snapshot), list(dict.fromkeys(reasons))

    def bundle_validation(self, workspace, identity):
        project = self._project(workspace)
        self._permission("read", project)
        row = self._bundle_row(workspace, identity)
        profile = self._progress_profile(project)
        snapshot, reasons = self._bundle_sources(workspace, row, profile)
        if row.content_hash != _hash(row.source_snapshot_json):
            reasons.append("BUNDLE_CONTENT_HASH_MISMATCH")
        if snapshot and _hash(snapshot) != row.content_hash:
            reasons.append("BUNDLE_SOURCE_DRIFT")
        successors = [
            r
            for r in self._rows(ProjectControlBaselineBundle, workspace)
            if r.status == "APPROVED" and r.supersedes_id == row.id
        ]
        return {
            "bundle_id": row.id,
            "status": "BLOCK" if reasons else "VALID",
            "effective_state": "SUPERSEDED" if successors else "REQUIRES_REVIEW" if reasons else row.status,
            "reason_codes": list(dict.fromkeys(reasons)),
            "frozen_hash": row.content_hash,
            "current_hash": _hash(snapshot) if snapshot else None,
            "frozen_sources": deepcopy(row.source_snapshot_json),
            "current_sources": snapshot,
            "approved_bundle_mutated": False,
        }

    def bundles(self, workspace):
        self._permission("read", self._project(workspace))
        rows = self._rows(ProjectControlBaselineBundle, workspace)
        return {
            "items": [self._out(row) | {"validation": self.bundle_validation(workspace, row.id)} for row in rows],
            "total": len(rows),
        }

    def bundle(self, workspace, identity):
        self._permission("read", self._project(workspace))
        return self._out(self._bundle_row(workspace, identity)) | {
            "validation": self.bundle_validation(workspace, identity)
        }

    def create_bundle(self, workspace, payload, key, *, predecessor=None, expected=None):
        self._ready(workspace, "baseline.prepare")

        def apply():
            project, profile = self._ready(workspace, "baseline.prepare")
            self.db.refresh(project, with_for_update=True)
            old = self._bundle_row(workspace, predecessor, lock=True) if predecessor else None
            if old:
                self._version(old.version, expected)
                if old.status != "APPROVED" or old.code != payload.code:
                    self._error(409, "BUNDLE_SUCCESSOR_REQUIRES_APPROVED_SAME_CODE")
                if any(row.supersedes_id == old.id for row in self._rows(ProjectControlBaselineBundle, workspace)):
                    self._error(409, "BUNDLE_SUCCESSOR_ALREADY_EXISTS")
            existing = [row for row in self._rows(ProjectControlBaselineBundle, workspace) if row.code == payload.code]
            if existing and not old:
                self._error(409, "BUNDLE_SUCCESSOR_REFERENCE_REQUIRED")
            snapshot, reasons = self._bundle_sources(workspace, payload, profile)
            if reasons:
                raise HTTPException(409, detail={"code": "BASELINE_BUNDLE_INCONSISTENT", "reason_codes": reasons})
            row = ProjectControlBaselineBundle(
                **self._base(workspace),
                **payload.model_dump(exclude={"reason"}),
                revision=old.revision + 1 if old else 1,
                supersedes_id=old.id if old else None,
                progress_profile_id=profile.id,
                configuration_hash=profile.content_hash,
                currency=snapshot["currency"],
                source_snapshot_json=snapshot,
                content_hash=_hash(snapshot),
                updated_by=self.actor_id,
                reason=payload.reason,
            )
            self.db.add(row)
            return self._record(row, "CONTROL_BASELINE_BUNDLE_CREATED", payload.reason)

        return self._write(
            "bundle.create" if not predecessor else "bundle.successor",
            workspace,
            payload,
            key,
            apply,
            predecessor,
            expected,
        )

    def transition_bundle(self, workspace, identity, payload, expected, key):
        action = "baseline.approve" if payload.action == "approve" else "baseline.prepare"
        self._ready(workspace, action)

        def apply():
            project, _profile = self._ready(workspace, action)
            self.db.refresh(project, with_for_update=True)
            row = self._bundle_row(workspace, identity, lock=True)
            self._version(row.version, expected)
            target = {"review": ("DRAFT", "UNDER_REVIEW"), "approve": ("UNDER_REVIEW", "APPROVED")}[payload.action]
            if row.status != target[0]:
                self._error(409, "BUNDLE_TRANSITION_INVALID")
            validation = self.bundle_validation(workspace, identity)
            if validation["status"] != "VALID":
                raise HTTPException(
                    409, detail={"code": "BASELINE_BUNDLE_INCONSISTENT", "reason_codes": validation["reason_codes"]}
                )
            if payload.action == "approve":
                if self.actor_id in {row.created_by, row.updated_by}:
                    self._error(403, "BUNDLE_PREPARER_CANNOT_APPROVE")
                if row.supersedes_id and any(
                    r.status == "APPROVED" and r.supersedes_id == row.supersedes_id and r.id != row.id
                    for r in self._rows(ProjectControlBaselineBundle, workspace)
                ):
                    self._error(409, "BUNDLE_APPROVED_BRANCH_CONFLICT")
                row.approved_by, row.approved_at = self.actor_id, utc_now()
            else:
                row.reviewed_by = self.actor_id
            row.status, row.version = target[1], row.version + 1
            event = (
                "CONTROL_BASELINE_BUNDLE_APPROVED"
                if payload.action == "approve"
                else "CONTROL_BASELINE_BUNDLE_UNDER_REVIEW"
            )
            result = self._record(row, event, payload.reason)
            if payload.action == "approve" and row.supersedes_id:
                self._event(
                    "CONTROL_BASELINE_BUNDLE_SUPERSEDED",
                    row.supersedes_id,
                    {"successor_id": row.id, "old_frozen_content_mutated": False},
                )
            return result

        return self._write("bundle.transition", workspace, payload, key, apply, identity, expected)

    def period_review(self, workspace, identity):
        self._permission("read", self._project(workspace))
        period = self._get(ProjectControlsPeriod, workspace, identity)
        snapshots = [row for row in self._rows(ProgressPeriodSnapshot, workspace) if row.period_id == identity]
        rows = [row for row in self._rows(ProgressMeasurement, workspace) if row.period_id == identity]
        return {
            "period": self._out(period),
            "snapshot": self._out(snapshots[0]) if snapshots else None,
            "measurements": [self._out(row) for row in rows],
            "candidate_set_frozen": bool(snapshots),
            "allowed_actions": self.allowed_actions(self._project(workspace)),
            "authority": "O1A_PROJECT_CONTROLS_PERIOD_WITH_PROGRESS_REPORTING_SNAPSHOT",
        }

    def transition_progress_period(self, workspace, identity, payload, expected, key):
        self._permission("period.publish" if payload.action == "publish" else "period.freeze", self._project(workspace))
        # Existing O1A writer invokes the shared hook, even when called through
        # its original API. Its existing idempotency, SoD and successor govern.
        operational = OperationalContextService(self.db, self.tenant_id, self.actor_id, self.access_context)
        result = operational.transition_period(
            workspace, identity, payload.action, ActionIn(reason=payload.reason, notes=payload.notes), expected, key
        )
        return {"period": result, "review": self.period_review(workspace, result["id"])}

    def _covers_budgeted_scope(self, workspace, row, line, visited=None):
        """Method-neutral allocation proof; a percent unit is not scope coverage."""
        if not line.get("scope_item_id"):
            return True
        visited = set() if visited is None else visited
        if row.id in visited:
            return False
        visited = visited | {row.id}
        required = value(line["quantity"])
        if row.plan_item_id:
            allocations = [
                item
                for item in row.source_snapshot.get("plan_allocations", [])
                if item.get("scope_item_id") == line["scope_item_id"]
            ]
            if (
                not allocations
                or any(item.get("unit") != line.get("unit") for item in allocations)
                or sum((value(item["quantity"]) for item in allocations), ZERO) < required
            ):
                return False
        package_basis = row.source_snapshot.get("package_quantity_basis")
        if row.work_package_id and package_basis:
            quantities = {
                (str(value(item["quantity"])), item["unit"])
                for item in package_basis.get("mappings", [])
                if item.get("quantity") is not None and item.get("unit")
            }
            if len(quantities) != 1:
                return False
            quantity, unit = next(iter(quantities))
            if unit != line.get("unit") or value(quantity) < required:
                return False
        for component in row.source_snapshot.get("component_measurements", []):
            child = self._get(ProgressMeasurement, workspace, component["id"])
            if not self._covers_budgeted_scope(workspace, child, line, visited):
                return False
        return True

    def evm(self, workspace, bundle_id, period_id, as_of, currency=None):
        self._permission("evm.view", self._project(workspace))
        bundle = self._bundle_row(workspace, bundle_id)
        period = self._get(ProjectControlsPeriod, workspace, period_id)
        cost = self._get(CostBaseline, workspace, bundle.cost_baseline_id)
        errors, earned_lines = [], []
        validation = self.bundle_validation(workspace, bundle_id)
        if bundle.status != "APPROVED":
            errors.append("APPROVED_CONTROL_BASELINE_BUNDLE_REQUIRED")
        if validation["effective_state"] != "APPROVED":
            errors.append("BASELINE_BUNDLE_REQUIRES_REVIEW")
        if not period.period_start <= as_of <= period.period_end:
            errors.append("PERIOD_AS_OF_MISMATCH")
        if as_of < bundle.effective_date:
            errors.append("BUNDLE_EFFECTIVE_DATE_MISMATCH")
        operational_policy = bundle.source_snapshot_json.get("operational_period_policy") or {}
        if period.configuration_id != operational_policy.get(
            "configuration_id"
        ) or period.source_configuration_hash != operational_policy.get("hash"):
            errors.append("PERIOD_POLICY_BASIS_MISMATCH")
        target_currency = currency or bundle.currency
        if target_currency != bundle.currency:
            errors.append("CURRENCY_MISMATCH")
        phases = cost.snapshot_json.get("phasing", [])
        phase_periods = self._phasing_period_sources(workspace, phases, operational_policy, errors)
        pv = ZERO
        for phase in phases:
            if phase.get("currency") != target_currency:
                errors.append("CURRENCY_MISMATCH")
            for point in phase.get("spread_json", []):
                point_date = date.fromisoformat(point["date"][:10])
                # PV is cumulative project phasing, not the amount belonging
                # exclusively to the reporting period. Future phases are valid
                # approved sources and contribute zero until their own dates.
                if point_date <= as_of:
                    pv += value(point["amount"])
        if not phases:
            errors.append("BASELINE_PHASING_REQUIRED")
        measurements = self.effective_approved(workspace, period_id=period_id, as_of=as_of)
        pinned_profile = bundle.source_snapshot_json["progress_profile"]
        policy = pinned_profile["content"].get("evm_policy", {})
        priority = policy.get("earned_source_priority", ["PHYSICAL", "QUANTITY", "MILESTONE"])
        allowed = set(policy.get("allowed_earned_sources", sorted(EARNED_SOURCES))) & EARNED_SOURCES
        candidates = [row for row in measurements if row.progress_type in allowed]
        ev = ZERO
        lines = cost.snapshot_json.get("lines", [])
        for line in lines:
            dimensions = [
                key
                for key in ("scope_item_id", "plan_item_id", "work_package_id", "control_account_id")
                if line.get(key)
            ]
            matched = []
            incomplete_coverage = False
            for row in candidates:
                # A represented physical object may legitimately price several
                # distinct budget lines; each line is earned once, never once
                # per M:N mapping or per parallel progress type.
                if not dimensions or not any(getattr(row, name) == line[name] for name in dimensions):
                    continue
                if any(getattr(row, name) is not None and getattr(row, name) != line[name] for name in dimensions):
                    continue
                # A coarse Plan/Package/CA completion cannot be spread over
                # heterogeneous priced Scope lines without allocated earned
                # weights. A direct Scope measurement (or singleton resolved
                # Scope coverage) is provably attributable to that line.
                if line.get("scope_item_id") and row.scope_item_id != line["scope_item_id"]:
                    if set(row.source_snapshot.get("scope_item_ids", [])) != {line["scope_item_id"]}:
                        incomplete_coverage = True
                        continue
                if not self._covers_budgeted_scope(workspace, row, line):
                    incomplete_coverage = True
                    continue
                matched.append(row)
            rank = min(
                (priority.index(row.progress_type) for row in matched if row.progress_type in priority), default=None
            )
            selected = [
                row for row in matched if row.progress_type in priority and priority.index(row.progress_type) == rank
            ]
            if len(selected) != 1:
                if not selected and incomplete_coverage:
                    errors.append("INCOMPATIBLE_BUDGETED_PROGRESS_COVERAGE")
                errors.append(
                    "APPROVED_EARNED_PROGRESS_REQUIRED" if not selected else "AMBIGUOUS_EARNED_PROGRESS_BASIS"
                )
                continue
            row = selected[0]
            if self._source_state(row) != "CURRENT":
                errors.append("PROGRESS_SOURCE_REQUIRES_REVIEW")
            if (
                row.configuration_id != bundle.progress_profile_id
                or row.configuration_hash != bundle.configuration_hash
            ):
                errors.append("PROGRESS_PROFILE_BASIS_MISMATCH")
            if (
                row.source_snapshot.get("scope_baseline_id") != bundle.scope_baseline_id
                or row.source_snapshot.get("scope_baseline_hash")
                != bundle.source_snapshot_json["scope_baseline"]["hash"]
            ):
                errors.append("PROGRESS_SCOPE_BASIS_MISMATCH")
            if (
                row.schedule_version_id is not None
                and row.schedule_version_id != bundle.source_snapshot_json["schedule_baseline"]["schedule_version_id"]
            ):
                errors.append("PROGRESS_SCHEDULE_BASIS_MISMATCH")
            if row.progress_value > 100 or row.progress_value < 0:
                errors.append("EARNED_OVERRUN_NOT_COMPUTABLE")
                continue
            if line.get("currency") != target_currency:
                errors.append("CURRENCY_MISMATCH")
            amount = earned_amount(line["amount"], row.progress_value)
            ev += amount
            earned_lines.append(
                {
                    "budget_line_id": line["id"],
                    "measurement_id": row.id,
                    "progress_type": row.progress_type,
                    "progress_value": str(row.progress_value),
                    "budgeted_value": str(line["amount"]),
                    "earned_value": str(amount),
                    "currency": line["currency"],
                    "source_hashes": {
                        "measurement": row.content_hash,
                        "source": row.source_hash,
                        "cost_baseline": cost.content_hash,
                    },
                }
            )
        if not lines:
            errors.append("BUDGETED_CONTROL_VALUE_REQUIRED")
        actuals = [
            row
            for row in self._rows(CostActualEntry, workspace)
            if row.status == "RECOGNIZED" and row.recognition_date <= as_of
        ]
        ac = sum((row.amount for row in actuals), ZERO) if actuals else None
        structures = cost.snapshot_json.get("control_structures", {})
        controls = {
            "control_account_id": {r["id"] for r in structures.get("accounts", [])},
            "cbs_id": {r["id"] for r in structures.get("cbs", [])},
            "cost_code_id": {r["id"] for r in structures.get("cost_codes", [])},
        }
        used_controls = {key: {line[key] for line in lines if line.get(key)} for key in controls}
        for row in actuals:
            if row.currency != target_currency:
                errors.append("CURRENCY_MISMATCH")
            actual_period = self._get(ProjectControlsPeriod, workspace, row.period_id)
            if actual_period.configuration_id != operational_policy.get(
                "configuration_id"
            ) or actual_period.source_configuration_hash != operational_policy.get("hash"):
                errors.append("ACTUAL_PERIOD_POLICY_BASIS_MISMATCH")
            if not actual_period.period_start <= row.recognition_date <= actual_period.period_end:
                errors.append("ACTUAL_RECOGNITION_PERIOD_MISMATCH")
            if any(getattr(row, key) and getattr(row, key) not in ids for key, ids in controls.items()):
                errors.append("ACTUAL_CONTROL_BASIS_MISMATCH")
            if any(getattr(row, key) and getattr(row, key) not in ids for key, ids in used_controls.items()):
                errors.append("ACTUAL_BUDGETED_CONTROL_BASIS_MISMATCH")
            if any(used_controls.values()) and not any(getattr(row, key) for key in controls):
                errors.append("ACTUAL_CONTROL_BASIS_UNMAPPED")
        if len(earned_lines) != len(lines):
            ev = None
        result = evm_values(pv, ev, ac, errors=errors)
        return {
            **result,
            "currency": target_currency,
            "bundle_id": bundle_id,
            "period_id": period_id,
            "as_of": as_of.isoformat(),
            "earned_lines": earned_lines,
            "basis": {
                "project_workspace_id": workspace,
                "bundle_hash": bundle.content_hash,
                "source_hashes": {
                    name: bundle.source_snapshot_json[name]["hash"]
                    for name in ("scope_baseline", "schedule_baseline", "cost_baseline", "progress_profile")
                },
                "period": _period_identity(period),
                "schedule_data_date": self._get(
                    ScheduleVersion, workspace, bundle.source_snapshot_json["schedule_baseline"]["schedule_version_id"]
                ).data_date,
                "actual_recognition_dates": sorted({row.recognition_date.isoformat() for row in actuals}),
                "actual_period_ids": sorted({row.period_id for row in actuals}),
                "phasing_period_ids": [source["id"] for source in phase_periods],
                "progress_measurement_dates": sorted({row.measurement_date.isoformat() for row in candidates}),
                "actual_source_hash": _hash([self._out(row) for row in actuals]),
                "earned_source_priority": priority,
            },
            "authority": {
                "pv": "APPROVED_COST_BASELINE_PHASING",
                "ev": "APPROVED_PHYSICAL_QUANTITY_MILESTONE_ONLY",
                "ac": "COST_RECOGNIZED_ACTUAL_NOT_PAYMENTS",
                "forecast_performed": False,
            },
        }

    def save_evm_snapshot(self, workspace, payload, key):
        self._ready(workspace, "period.publish")

        def apply():
            self._ready(workspace, "period.publish")
            period = self._get(ProjectControlsPeriod, workspace, payload.period_id, lock=True)
            if period.status == "PUBLISHED":
                self._error(409, "PUBLISHED_PERIOD_REPORTING_IMMUTABLE")
            report = _json(self.evm(workspace, payload.bundle_id, payload.period_id, payload.as_of, payload.currency))
            row = EarnedValueSnapshot(
                **self._base(workspace),
                bundle_id=payload.bundle_id,
                period_id=payload.period_id,
                as_of=payload.as_of,
                status=report["status"],
                currency=report["currency"],
                **{
                    name: value(report[name]) if report[name] is not None else None
                    for name in ("pv", "ev", "ac", "cpi", "spi")
                },
                snapshot_json=report,
                content_hash=_hash(report),
                reason=payload.reason,
            )
            self.db.add(row)
            return self._record(row, "EARNED_VALUE_SNAPSHOT_CAPTURED", payload.reason)

        return self._write("evm.snapshot", workspace, payload, key, apply)

    def evm_snapshots(self, workspace):
        self._permission("evm.view", self._project(workspace))
        return {"items": [self._out(row) for row in self._rows(EarnedValueSnapshot, workspace)]}

    def curves(self, workspace, bundle_id, period_id, as_of):
        self._permission("read", self._project(workspace))
        bundle = self._bundle_row(workspace, bundle_id)
        cost = self._get(CostBaseline, workspace, bundle.cost_baseline_id)
        validation = self.bundle_validation(workspace, bundle_id)
        planned = {}
        for phase in cost.snapshot_json.get("phasing", []):
            for point in phase.get("spread_json", []):
                key = point["date"][:10]
                if date.fromisoformat(key) <= as_of:
                    planned[key] = planned.get(key, ZERO) + value(point["amount"])
        running, planned_curve = ZERO, []
        for day, amount in sorted(planned.items()):
            running += amount
            planned_curve.append(
                {
                    "date": day,
                    "period_value": str(amount),
                    "cumulative_value": str(running),
                    "currency": bundle.currency,
                }
            )
        measurements = self.effective_approved(workspace, period_id=period_id, as_of=as_of)
        days = sorted({row.as_of for row in measurements})
        earned = [self.evm(workspace, bundle_id, period_id, day) for day in days]
        approved = []
        for day in days:
            for progress_type in ("PHYSICAL", "QUANTITY", "MILESTONE"):
                rows = [row for row in measurements if row.progress_type == progress_type and row.as_of == day]
                if rows:
                    aggregate = self.aggregation(
                        workspace, progress_type=progress_type, period_id=period_id, as_of=day, group_by="PROJECT"
                    )
                    point = aggregate["items"][0]
                    approved.append(
                        {
                            "date": day.isoformat(),
                            "progress_type": progress_type,
                            **point,
                            "measurement_ids": point["input_ids"],
                            "inputs_snapshot": aggregate["inputs_snapshot"],
                            "content_hash": aggregate["content_hash"],
                        }
                    )
        return {
            "status": "CURRENT" if validation["effective_state"] == "APPROVED" else "REQUIRES_REVIEW",
            "reason_codes": validation["reason_codes"],
            "planned_curve": planned_curve,
            "approved_progress_curve": approved,
            "earned_curve": [
                {"date": row["as_of"], "status": row["status"], "ev": row["ev"], "reason_codes": row["reason_codes"]}
                for row in earned
            ],
            "forecast_curve": None,
            "authority": "APPROVED_SOURCES_ONLY_NOT_FORECAST_GOVERNANCE",
        }

    def four_d_overlay(self, workspace, bundle_id, period_id, as_of):
        self._permission("read", self._project(workspace))
        bundle = self._bundle_row(workspace, bundle_id)
        period = self._get(ProjectControlsPeriod, workspace, period_id)
        validation = self.bundle_validation(workspace, bundle_id)
        errors = list(validation["reason_codes"])
        if validation["effective_state"] != "APPROVED":
            errors.append("APPROVED_CURRENT_CONTROL_BASELINE_BUNDLE_REQUIRED")
        if not period.period_start <= as_of <= period.period_end:
            errors.append("PERIOD_AS_OF_MISMATCH")
        if as_of < bundle.effective_date:
            errors.append("BUNDLE_EFFECTIVE_DATE_MISMATCH")
        operational_policy = bundle.source_snapshot_json.get("operational_period_policy") or {}
        if period.configuration_id != operational_policy.get(
            "configuration_id"
        ) or period.source_configuration_hash != operational_policy.get("hash"):
            errors.append("PERIOD_POLICY_BASIS_MISMATCH")
        from app.modules.schedule_four_d.service import FourDService

        planned = FourDService(self.db, self.tenant_id, self.actor_id, self.access_context).model(
            workspace, source="BASELINE", baseline_id=bundle.schedule_baseline_id, at=as_of.isoformat()
        )
        measurements = self.effective_approved(workspace, period_id=period_id, as_of=as_of, progress_type="PHYSICAL")
        items = []
        for item in planned["items"]:
            relevant = [
                row
                for row in measurements
                if row.scope_item_id == item["scope_item_id"]
                and (row.plan_item_id is None or row.plan_item_id == item.get("plan_item_id"))
            ]
            healthy = [
                row
                for row in relevant
                if self._source_state(row) == "CURRENT"
                and row.source_snapshot.get("scope_baseline_id") == bundle.scope_baseline_id
            ]
            progress = approved_overlay_state(item["scope_nature"], [self._out(row) for row in healthy])
            if relevant and len(healthy) != len(relevant):
                progress = {
                    "state": "REQUIRES_REVIEW",
                    "progress_value": None,
                    "reason_codes": ["STALE_PROGRESS_SOURCE"],
                }
            if errors:
                progress = {
                    "state": "REQUIRES_REVIEW",
                    "progress_value": None,
                    "reason_codes": list(dict.fromkeys(errors)),
                }
            items.append(
                {
                    "id": item["id"],
                    "scope_item_id": item["scope_item_id"],
                    "plan_item_id": item.get("plan_item_id"),
                    "scope_nature": item["scope_nature"],
                    "schedule_state": item["state"],
                    "schedule_semantic_state": item["semantic_state"],
                    "approved_physical_state": progress,
                    "objects": deepcopy(item["objects"]),
                    "schedule_mapping_issues": item["mapping_issues"],
                    "progress_measurement_ids": [row.id for row in relevant],
                }
            )
        return {
            "bundle_id": bundle_id,
            "period_id": period_id,
            "as_of": as_of.isoformat(),
            "reason_codes": list(dict.fromkeys(errors)),
            "items": items,
            "total": len(items),
            "source_hashes": planned["source_hashes"],
            "read_model_hash": _hash(items),
            "authority": {
                "schedule_state": "EXISTING_FOUR_D_MODEL",
                "physical_state": "APPROVED_PROGRESS_ONLY",
                "schedule_mutated": False,
                "ifc_mutated": False,
            },
        }


def approved_overlay_state(nature, rows):
    if not rows:
        return {
            "state": "NOT_MEASURED",
            "progress_value": None,
            "reason_codes": ["APPROVED_PHYSICAL_PROGRESS_REQUIRED"],
        }
    if nature == "TEMPORARY":
        order = {"INSTALL": 0, "USE": 1, "REMOVE": 2}
        if any(row.get("phase") not in order for row in rows):
            return {"state": "REQUIRES_REVIEW", "progress_value": None, "reason_codes": ["TEMPORARY_PHASE_REQUIRED"]}
        if len({row["phase"] for row in rows}) != len(rows):
            return {"state": "REQUIRES_REVIEW", "progress_value": None, "reason_codes": ["AMBIGUOUS_PHYSICAL_PROGRESS"]}
        rows = sorted(rows, key=lambda row: (row["as_of"], order[row["phase"]], row["revision"]))
        selected = rows[-1]
        progress = value(selected["progress_value"])
        state = {
            "INSTALL": "TEMPORARY_IN_USE"
            if progress == 100
            else "TEMPORARY_INSTALLATION"
            if progress
            else "ABSENT_BEFORE_INSTALL",
            "USE": "TEMPORARY_IN_USE",
            "REMOVE": "ABSENT_AFTER_REMOVAL" if progress == 100 else "TEMPORARY_REMOVAL",
        }[selected["phase"]]
    else:
        if len(rows) != 1:
            return {"state": "REQUIRES_REVIEW", "progress_value": None, "reason_codes": ["AMBIGUOUS_PHYSICAL_PROGRESS"]}
        progress = value(rows[0]["progress_value"])
        labels = {
            "INSTALL": ("FUTURE_NOT_INSTALLED", "INSTALLATION", "INSTALLED"),
            "REMOVE": ("EXISTING", "REMOVAL", "REMOVED"),
            "MAINTENANCE": ("EXISTING_IN_SERVICE", "MAINTENANCE_INTERVENTION", "RESTORED_IN_SERVICE"),
        }
        if nature not in labels:
            return {"state": "REQUIRES_REVIEW", "progress_value": None, "reason_codes": ["SCOPE_NATURE_INVALID"]}
        state = labels[nature][0 if progress == 0 else 2 if progress == 100 else 1]
    if not ZERO <= progress <= 100:
        return {"state": "REQUIRES_REVIEW", "progress_value": str(progress), "reason_codes": ["PHYSICAL_OVERRUN"]}
    return {"state": state, "progress_value": str(progress), "reason_codes": []}


def guard_operational_period_transition(db, tenant_id, actor_id, row, target, reason=""):
    """Invoked by O1A for every API path; inert before explicit Progress adoption."""
    connection = db.connection()
    if not inspect(connection).has_table("progress_history"):
        return
    adopted = db.scalar(
        select(ProgressHistory.id)
        .where(ProgressHistory.tenant_id == tenant_id, ProgressHistory.project_workspace_id == row.project_workspace_id)
        .limit(1)
    )
    if adopted is None:
        return
    action = "period.publish" if target == "PUBLISHED" else "period.freeze"
    context = require_enterprise_permission(db, tenant_id, actor_id, f"progress.{action}", bootstrap=False)
    service = ProgressIntegrationService(db, tenant_id, actor_id, context)
    service._permission(action, service._project(row.project_workspace_id))
    db.refresh(row, with_for_update=True)
    existing = db.scalar(
        select(ProgressPeriodSnapshot)
        .where(
            ProgressPeriodSnapshot.tenant_id == tenant_id,
            ProgressPeriodSnapshot.project_workspace_id == row.project_workspace_id,
            ProgressPeriodSnapshot.period_id == row.id,
        )
        .with_for_update()
    )
    if target == "REVIEW":
        if existing:
            service._error(409, "PROGRESS_PERIOD_ALREADY_FROZEN")
        measurements = [
            measurement
            for measurement in service._rows(ProgressMeasurement, row.project_workspace_id)
            if measurement.period_id == row.id and measurement.status != "REJECTED"
        ]
        approved_replaced = {
            measurement.supersedes_id
            for measurement in measurements
            if measurement.supersedes_id and measurement.status == "APPROVED"
        }
        pending_replaced = {
            measurement.supersedes_id
            for measurement in measurements
            if measurement.supersedes_id and measurement.status != "APPROVED"
        }
        candidates = [
            {
                "id": measurement.id,
                "content_hash": measurement.content_hash,
                "source_hash": measurement.source_hash,
                "prepared_by": measurement.prepared_by,
            }
            for measurement in measurements
            if measurement.id not in approved_replaced
            and (measurement.status == "APPROVED" or measurement.id not in pending_replaced)
        ]
        snapshot = ProgressPeriodSnapshot(
            **service._base(row.project_workspace_id),
            period_id=row.id,
            candidate_snapshot_json=candidates,
            report_snapshot_json={},
            content_hash=_hash(candidates),
            period_source_hash=_hash(_period_identity(row)),
            frozen_by=actor_id,
            reason=reason,
        )
        db.add(snapshot)
        service._record(snapshot, "PROGRESS_PERIOD_FROZEN", reason)
        return
    if existing is None:
        service._error(409, "PROGRESS_FROZEN_CANDIDATE_SET_REQUIRED")
    if existing.period_source_hash != _hash(_period_identity(row)):
        service._error(409, "PROGRESS_PERIOD_SOURCE_CHANGED")
    if target == "CLOSED":
        if existing.status != "FROZEN":
            service._error(409, "PROGRESS_PERIOD_SNAPSHOT_TRANSITION_INVALID")
        rows = [
            service._get(ProgressMeasurement, row.project_workspace_id, candidate["id"])
            for candidate in existing.candidate_snapshot_json
        ]
        if any(measurement.status not in {"APPROVED", "REJECTED"} for measurement in rows):
            service._error(409, "PROGRESS_PERIOD_UNRESOLVED_CANDIDATES")
        by_id = {measurement.id: measurement for measurement in rows}
        if any(
            by_id[candidate["id"]].content_hash != candidate["content_hash"]
            for candidate in existing.candidate_snapshot_json
        ):
            service._error(409, "PROGRESS_FROZEN_CANDIDATE_CHANGED")
        effective_ids = {
            measurement.id for measurement in service.effective_approved(row.project_workspace_id, period_id=row.id)
        }
        if any(
            service._source_state(measurement) != "CURRENT" for measurement in rows if measurement.id in effective_ids
        ):
            service._error(409, "PROGRESS_APPROVED_SOURCE_REQUIRES_REVIEW")
        report = {
            "period": _period_identity(row),
            "approved_measurements": [
                service._out(measurement) for measurement in rows if measurement.id in effective_ids
            ],
            "rejected_measurement_ids": [measurement.id for measurement in rows if measurement.status == "REJECTED"],
            "frozen_candidates_hash": _hash(existing.candidate_snapshot_json),
        }
        existing.report_snapshot_json, existing.content_hash = report, _hash(report)
        existing.status, existing.closed_by, existing.closed_at = "CLOSED", actor_id, utc_now()
        service._record(existing, "PROGRESS_PERIOD_CLOSED", reason, changed=True)
    elif target == "PUBLISHED":
        if existing.status != "CLOSED" or existing.closed_by == actor_id:
            service._error(403 if existing.closed_by == actor_id else 409, "PROGRESS_PERIOD_PUBLICATION_SOD_OR_STATE")
        if existing.content_hash != _hash(existing.report_snapshot_json):
            service._error(409, "PROGRESS_CLOSED_SNAPSHOT_HASH_MISMATCH")
        existing.status, existing.published_by, existing.published_at = "PUBLISHED", actor_id, utc_now()
        service._record(existing, "PROGRESS_PERIOD_PUBLISHED", reason, changed=True)
