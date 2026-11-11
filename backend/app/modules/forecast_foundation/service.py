"""Governed projection commands over existing Scope, Schedule, Cost and Progress."""

from collections import defaultdict
from copy import deepcopy
from datetime import date
from decimal import DecimalException

from fastapi import HTTPException
from sqlalchemy import select

from app.core.time import utc_now
from app.domain.models import AdminConfiguration, SecurityEvent, UserAccount
from app.modules.awp.models import WorkPackage
from app.modules.awp.service import AWPService
from app.modules.basic_data.service import _hash, _json
from app.modules.cost_foundation.financial_models import CostActualEntry, CostCommitmentReference
from app.modules.cost_foundation.financials import (
    CostFinancialService,
    effective_obligation_rows,
    reconcile_obligations,
)
from app.modules.cost_foundation.models import (
    BudgetLine,
    BudgetVersion,
    ControlAccount,
    CostBaseline,
    CostCBS,
    CostCode,
)
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.forecast_foundation.models import (
    ForecastAssumption,
    ForecastComponent,
    ForecastHistory,
    ForecastVersion,
)
from app.modules.forecast_foundation.permissions import ACTIONS, require_forecast_schema
from app.modules.forecast_foundation.policy import (
    DEFAULT_PROFILE,
    METHODS,
    ZERO,
    cost_value,
    eac_values,
    number,
    resource_value,
    validate_profile,
)
from app.modules.forecast_foundation.schemas import AssumptionIn, ComponentIn, ForecastIn
from app.modules.operational_context.models import OperationalContextCommand, ProjectControlsPeriod
from app.modules.progress_foundation.integration import ProgressIntegrationService, _period_identity
from app.modules.progress_foundation.integration_models import ProjectControlBaselineBundle
from app.modules.schedule_foundation.models import ScheduleBaseline, ScheduleRegister, ScheduleVersion
from app.modules.scope_foundation.models import PlanItem, PlanItemScopeLink, ScopeBaseline, ScopeItem
from app.modules.scope_foundation.service import ScopeFoundationService

PROFILE_KIND = "forecast_profile"
FAMILIES = {"cost_items": "COST", "time_items": "TIME", "milestones": "MILESTONE", "resource_items": "RESOURCE"}


def _date(value):
    if value in (None, ""):
        return None
    return date.fromisoformat(str(value)[:10])


def _readiness_as_of(awp, as_of):
    """Consume only real dated AWP assessments, never infer historical release."""
    latest = {}
    for row in awp.get("assessments", []):
        assessed_date = _date(row.get("as_of"))
        if assessed_date is None or assessed_date > as_of:
            continue
        package_id = row["work_package_id"]
        previous = latest.get(package_id)
        # Forecast's cutoff is a business date; for the same date prefer the
        # last persisted assessment without comparing mixed time-zone strings.
        if previous is None or (assessed_date, row["id"]) > (_date(previous["as_of"]), previous["id"]):
            latest[package_id] = row

    assessments, readiness = [], {}
    current = awp.get("current_readiness", {})
    for package in awp.get("packages", []):
        package_id = package["id"]
        key = str(package_id)
        recorded = latest.get(package_id)
        if recorded is None:
            readiness[key] = {
                "work_package_id": package_id,
                "assessment_id": None,
                "as_of": None,
                "readiness_state": "UNKNOWN",
                "source_hashes": {},
                "basis": "NO_DATED_AWP_ASSESSMENT",
                "stale": True,
            }
            continue
        assessments.append(recorded)
        readiness[key] = {
            **{
                field: recorded[field]
                for field in (
                    "work_package_id",
                    "as_of",
                    "readiness_state",
                    "blocking_constraints",
                    "open_nonblocking_constraints",
                    "dependency_state",
                    "evidence_state",
                    "dimensions",
                    "source_hashes",
                    "policy_revision",
                )
            },
            "assessment_id": recorded["id"],
            "assessed_by": recorded["created_by"],
            "basis": "PERSISTED_AWP_ASSESSMENT_AS_OF",
            # Compare material source hashes only. In particular, never copy
            # today's READY/RELEASED label into a dated evidence snapshot.
            "stale": recorded["source_hashes"] != current.get(key, {}).get("source_hashes"),
        }
    return assessments, readiness


class ForecastFoundationService(ScopeFoundationService):
    @staticmethod
    def _error(status, code, **metadata):
        raise HTTPException(status, detail={"code": code, **metadata})

    def _project(self, identity):
        require_forecast_schema(self.db)
        return super()._project(identity)

    def _permission(self, action, workspace=None):
        if self.access_context is None:
            return
        if action not in self._permission_contexts:
            self._permission_contexts[action] = require_enterprise_permission(
                self.db, self.tenant_id, self.actor_id, f"forecast.{action}", bootstrap=False
            )
        access = self._permission_contexts[action]
        if action.startswith("admin.") and not access.organization_wide:
            self._error(403, "FORECAST_ADMIN_ORGANIZATION_SCOPE_REQUIRED")
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

    def _event(self, action, identity, metadata, *, outcome="success"):
        self.db.add(
            SecurityEvent(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                event_type=f"forecast.{action}",
                outcome=outcome,
                target_type="ForecastFoundation",
                target_id=identity,
                metadata_json=deepcopy(metadata),
            )
        )

    def _record(self, row, event, reason, *, changed=False):
        if changed:
            row.version += 1
        self.db.flush()
        snapshot = self._version_out(row) if isinstance(row, ForecastVersion) else self._out(row)
        self.db.add(
            ForecastHistory(
                **self._base(row.project_workspace_id),
                entity_type=type(row).__name__,
                entity_id=row.id,
                revision=row.version,
                event_type=event,
                snapshot_json=snapshot,
                reason=reason,
            )
        )
        self._event(
            event, row.id, {"project_workspace_id": row.project_workspace_id, "version": row.version, "reason": reason}
        )
        return snapshot

    def _write(self, command, workspace, payload, key, apply, identity=None, expected=None):
        def checked():
            try:
                return apply()
            except (ValueError, DecimalException, OverflowError) as error:
                raise HTTPException(422, detail={"code": str(error) or "FORECAST_VALUE_INVALID"}) from error

        return self._command(
            f"forecast.{command}",
            key,
            {"project": workspace, "id": identity, "expected": expected, **payload.model_dump(mode="json")},
            checked,
        )

    def _forecast_profile(self, project):
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
        top = [row for priority, row in candidates if priority == max(p for p, _ in candidates)]
        if len({r.code for r in top}) != 1:
            self._error(409, "FORECAST_PROFILE_AMBIGUOUS")
        return max(top, key=lambda row: row.revision)

    def _ready(self, workspace, action):
        project = self._project(workspace)
        self._permission(action, project)
        operational = self._operational()
        operational._operable(workspace)
        operational._policy_ready(project, operational._effective_profile(project))
        profile = self._forecast_profile(project)
        if profile is None:
            self._error(409, "FORECAST_PUBLISHED_PROFILE_REQUIRED")
        return project, profile

    def _profile(self, identity, *, lock=False):
        require_forecast_schema(self.db)
        statement = select(AdminConfiguration).where(
            AdminConfiguration.id == identity,
            AdminConfiguration.tenant_id == self.tenant_id,
            AdminConfiguration.kind == PROFILE_KIND,
        )
        row = self.db.scalar(
            statement.with_for_update().execution_options(populate_existing=True) if lock else statement
        )
        if row is None:
            self._error(404, "FORECAST_PROFILE_NOT_FOUND")
        return row

    def _validate_profile(self, content):
        try:
            validate_profile(content)
            scope = content["scope"]
            if scope["type"] == "workspace":
                self._project(scope["workspace_id"])
            elif scope != {"type": "tenant", "workspace_id": None}:
                raise ValueError("scope")
            start, finish = self._instant(content["effective_from"]), self._instant(content["effective_to"])
            if start and finish and finish <= start:
                raise ValueError("window")
        except (ValueError, TypeError, KeyError) as error:
            raise HTTPException(422, detail={"code": "FORECAST_PROFILE_INVALID"}) from error

    def profiles(self):
        require_forecast_schema(self.db)
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

    def create_profile(self, payload, key):
        require_forecast_schema(self.db)
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
                self._error(409, "FORECAST_PROFILE_CODE_EXISTS")
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
            self._event("FORECAST_PROFILE_CREATED", row.id, {"reason": payload.reason, "hash": row.content_hash})
            return self._profile_out(row)

        return self._command("forecast.profile.create", key, payload.model_dump(mode="json"), apply)

    def update_profile(self, identity, payload, expected, key):
        self._permission("admin.configure")

        def apply():
            row = self._profile(identity, lock=True)
            self._version(row.version, expected)
            if row.status != "draft":
                self._error(409, "FORECAST_PROFILE_IMMUTABLE")
            self._validate_profile(payload.content_json)
            row.name, row.content_json, row.content_hash = (
                payload.name,
                deepcopy(payload.content_json),
                _hash(payload.content_json),
            )
            row.version, row.updated_at = row.version + 1, utc_now()
            self.db.flush()
            self._event("FORECAST_PROFILE_UPDATED", row.id, {"reason": payload.reason})
            return self._profile_out(row)

        return self._command(
            "forecast.profile.update",
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
                self._error(409, "FORECAST_PROFILE_IMMUTABLE")
            self._validate_profile(row.content_json)
            editor = row.created_by_user_id
            if row.version > 1:
                receipt = self.db.scalar(
                    select(OperationalContextCommand).where(
                        OperationalContextCommand.tenant_id == self.tenant_id,
                        OperationalContextCommand.command_type == "forecast.profile.update",
                        OperationalContextCommand.result_json["id"].as_integer() == row.id,
                        OperationalContextCommand.result_json["version"].as_integer() == row.version,
                    )
                )
                if receipt is None:
                    self._error(409, "FORECAST_PROFILE_EDITOR_PROVENANCE_REQUIRED")
                editor = receipt.actor_id
            if self.actor_id in {row.created_by_user_id, editor}:
                self._error(403, "FORECAST_PROFILE_PUBLICATION_SOD")
            row.status, row.published_at, row.version = "published", utc_now(), row.version + 1
            self.db.flush()
            self._event(
                "FORECAST_CONFIGURATION_PUBLISHED", row.id, {"reason": payload.reason, "hash": row.content_hash}
            )
            return self._profile_out(row)

        return self._command(
            "forecast.profile.publish",
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
                self._error(409, "FORECAST_PUBLISHED_PROFILE_SUCCESSOR_REQUIRED")
            rows = list(
                self.db.scalars(
                    select(AdminConfiguration).where(
                        AdminConfiguration.tenant_id == self.tenant_id,
                        AdminConfiguration.kind == PROFILE_KIND,
                        AdminConfiguration.code == old.code,
                    )
                )
            )
            row = AdminConfiguration(
                tenant_id=self.tenant_id,
                kind=PROFILE_KIND,
                code=old.code,
                name=old.name,
                status="draft",
                revision=max(r.revision for r in rows) + 1,
                version=1,
                content_json=deepcopy(old.content_json),
                content_hash=old.content_hash,
                created_by_user_id=self.actor_id,
            )
            self.db.add(row)
            self.db.flush()
            self._event(
                "FORECAST_PROFILE_SUCCESSOR_CREATED", row.id, {"reason": payload.reason, "supersedes_id": old.id}
            )
            return self._profile_out(row)

        return self._command(
            "forecast.profile.successor",
            key,
            {"id": identity, "expected": expected, **payload.model_dump(mode="json")},
            apply,
        )

    def _source_context(self, workspace, values, profile=None):
        """All facts remain scoped reads; period lifecycle status is not a source rebaseline."""
        project = self._project(workspace)
        profile = profile or self._forecast_profile(project)
        progress = ProgressIntegrationService(self.db, self.tenant_id, self.actor_id, self.access_context)
        bundle = self._get(ProjectControlBaselineBundle, workspace, values.bundle_id)
        period = self._get(ProjectControlsPeriod, workspace, values.period_id)
        schedule = self._get(ScheduleVersion, workspace, values.schedule_version_id)
        register = self._get(ScheduleRegister, workspace, schedule.register_id)
        baseline_scope = self._get(ScopeBaseline, workspace, bundle.scope_baseline_id)
        baseline_schedule = self._get(ScheduleBaseline, workspace, bundle.schedule_baseline_id)
        baseline_cost = self._get(CostBaseline, workspace, bundle.cost_baseline_id)
        reasons = []
        validation = progress.bundle_validation(workspace, bundle.id)
        if bundle.status != "APPROVED" or validation["effective_state"] != "APPROVED":
            reasons.append("FORECAST_APPROVED_CURRENT_BUNDLE_REQUIRED")
        if schedule.status != "ACCEPTED_CURRENT" or register.current_version_id != schedule.id:
            reasons.append("FORECAST_ACCEPTED_CURRENT_SCHEDULE_REQUIRED")
        if schedule.scope_baseline_id != bundle.scope_baseline_id:
            reasons.append("FORECAST_CURRENT_SCOPE_BASIS_MISMATCH")
        if _hash(schedule.snapshot_json) != schedule.content_hash:
            reasons.append("FORECAST_SCHEDULE_CONTENT_HASH_MISMATCH")
        if not period.period_start <= values.as_of <= period.period_end:
            reasons.append("FORECAST_PERIOD_AS_OF_MISMATCH")
        data_date = _date(schedule.data_date)
        if data_date is None or data_date > values.as_of:
            reasons.append("FORECAST_SCHEDULE_DATA_DATE_INCOMPATIBLE")
        if values.currency != bundle.currency:
            reasons.append("FORECAST_CURRENCY_MISMATCH")
        operational = bundle.source_snapshot_json.get("operational_period_policy", {})
        if period.configuration_id != operational.get(
            "configuration_id"
        ) or period.source_configuration_hash != operational.get("hash"):
            reasons.append("FORECAST_PERIOD_POLICY_MISMATCH")
        actuals = [
            self._out(r)
            for r in self._rows(CostActualEntry, workspace)
            if r.status == "RECOGNIZED" and r.recognition_date <= values.as_of
        ]
        for actual in actuals:
            source_period = self._get(ProjectControlsPeriod, workspace, actual["period_id"])
            if actual["currency"] != values.currency:
                reasons.append("FORECAST_ACTUAL_CURRENCY_MISMATCH")
            if (
                source_period.configuration_id != period.configuration_id
                or source_period.source_configuration_hash != period.source_configuration_hash
            ):
                reasons.append("FORECAST_ACTUAL_PERIOD_POLICY_MISMATCH")
            if not source_period.period_start <= _date(actual["recognition_date"]) <= source_period.period_end:
                reasons.append("FORECAST_ACTUAL_RECOGNITION_PERIOD_MISMATCH")
        financial = CostFinancialService(self.db, self.tenant_id, self.actor_id, self.access_context)
        financials = financial.financial_overview(workspace)
        commitments = self._commitments_as_of(workspace, values.as_of, financial)
        if commitments["issues"]:
            reasons.append("FORECAST_COMMITMENT_RECONCILIATION_REQUIRED")
        budget_rows = self._rows(BudgetVersion, workspace)
        current_budget = next((r for r in budget_rows if r.id == financials["current_budget_id"]), None)
        if current_budget is None:
            reasons.append("FORECAST_UNAMBIGUOUS_CURRENT_BUDGET_REQUIRED")
        elif current_budget.currency != values.currency:
            reasons.append("FORECAST_CURRENT_BUDGET_CURRENCY_MISMATCH")
        approved_progress = progress.effective_approved(workspace, period_id=period.id, as_of=values.as_of)
        awp = AWPService(self.db, self.tenant_id, self.actor_id, self.access_context).overview(workspace)
        assessments, readiness = _readiness_as_of(awp, values.as_of)
        snapshot = {
            "bundle": {
                "id": bundle.id,
                "hash": bundle.content_hash,
                "configuration_hash": bundle.configuration_hash,
                "effective_date": bundle.effective_date.isoformat(),
            },
            "baseline_scope": self._out(baseline_scope),
            "baseline_schedule": self._out(baseline_schedule),
            "baseline_cost": self._out(baseline_cost),
            "current_schedule": self._out(schedule),
            "current_schedule_mappings": self._out_schedule_mappings(workspace, schedule),
            "operational_period": _period_identity(period),
            "approved_progress": [self._out(r) for r in approved_progress],
            "actuals": actuals,
            "commitments": commitments,
            "original_budget": financials["original_budget"],
            "current_budget": financials["current_budget"],
            "current_budget_version": self._out(current_budget) if current_budget else None,
            "current_budget_lines": [
                self._out(r)
                for r in self._rows(BudgetLine, workspace)
                if current_budget and r.budget_version_id == current_budget.id
            ],
            "packages": [
                {field: value for field, value in row.items() if field != "readiness_state"}
                for row in awp.get("packages", [])
            ],
            "package_mappings": awp.get("mappings", []),
            "effective_package_mappings": awp.get("effective_mappings", []),
            "readiness": assessments,
            "current_readiness": readiness,
            "constraints": awp.get("constraints", []),
            "constraint_mappings": awp.get("constraint_mappings", []),
            "cwas": awp.get("cwas", []),
            "package_dependencies": awp.get("dependencies", []),
            "plans": [self._out(r) for r in self._rows(PlanItem, workspace)],
            "plan_allocations": [self._out(r) for r in self._rows(PlanItemScopeLink, workspace)],
            "control_accounts": [self._out(r) for r in self._rows(ControlAccount, workspace)],
            "forecast_configuration": {"id": profile.id, "hash": profile.content_hash, "revision": profile.revision}
            if profile
            else None,
            "progress_projections": {
                kind: progress.aggregation(
                    workspace, progress_type=kind, group_by="PROJECT", period_id=period.id, as_of=values.as_of
                )
                for kind in ("PHYSICAL", "QUANTITY")
            },
            "schedule_progress": progress.schedule_progress(workspace, period_id=period.id, as_of=values.as_of),
            "cost_progress": progress.cost_progress(workspace, period_id=period.id, as_of=values.as_of),
        }
        snapshot = _json(snapshot)
        snapshot["hashes"] = {key: _hash(value) for key, value in snapshot.items()}
        return snapshot, list(dict.fromkeys(reasons))

    def _commitments_as_of(self, workspace, as_of, financial):
        """Apply the native Cost reconciliation only after business-date selection.

        A future verified refresh must not suppress an obligation effective at
        this Forecast's as-of. No alternate obligation authority is introduced.
        """
        rows = {r.id: r for r in self._rows(CostCommitmentReference, workspace) if r.effective_date <= as_of}
        items, stale = [], []
        for item in effective_obligation_rows([self._out(row) for row in rows.values()]):
            if item["status"] == "VERIFIED":
                try:
                    financial._validate_obligation_source(workspace, rows[item["id"]])
                except HTTPException as error:
                    item["status"] = "SOURCE_STALE"
                    stale.append({"id": item["id"], "code": error.detail})
            items.append(item)
        result = reconcile_obligations(items)
        if stale:
            result["issues"] += stale
            result.update(status="RECONCILIATION_REQUIRED", net_commitment=None, currency=None)
        return result

    def _out_schedule_mappings(self, workspace, version):
        from app.modules.schedule_foundation.service import ScheduleFoundationService

        return ScheduleFoundationService(
            self.db, self.tenant_id, self.actor_id, self.access_context
        )._effective_mappings(version)

    def _version_out(self, row):
        result = self._out(row)
        assumptions = [
            self._out(r)
            for r in self._rows(ForecastAssumption, row.project_workspace_id)
            if r.forecast_version_id == row.id
        ]
        components = [
            self._out(r)
            for r in self._rows(ForecastComponent, row.project_workspace_id)
            if r.forecast_version_id == row.id
        ]
        result["assumptions"] = assumptions
        for family, kind in FAMILIES.items():
            result[family] = [r for r in components if r["component_kind"] == kind]
        result["input_json"] = {
            key: result[key] for key in ForecastIn.model_fields if key not in {"reason", *FAMILIES, "assumptions"}
        }
        result["input_json"]["assumptions"] = [{key: r[key] for key in AssumptionIn.model_fields} for r in assumptions]
        result["input_json"].update(
            {family: [{key: r[key] for key in ComponentIn.model_fields} for r in result[family]] for family in FAMILIES}
        )
        result["input_json"]["reason"] = row.reason
        successors = [
            r
            for r in self._rows(ForecastVersion, row.project_workspace_id)
            if r.supersedes_id == row.id and r.status == "APPROVED"
        ]
        result["effective_status"] = "SUPERSEDED" if successors else row.status
        return result

    def version(self, workspace, identity):
        self._permission("read", self._project(workspace))
        return self._version_out(self._get(ForecastVersion, workspace, identity))

    def versions(self, workspace):
        self._permission("read", self._project(workspace))
        rows = self._rows(ForecastVersion, workspace)
        return {"items": [self._version_out(row) for row in rows], "total": len(rows)}

    def overview(self, workspace):
        project = self._project(workspace)
        self._permission("read", project)
        profile = self._forecast_profile(project)
        collections = {
            "baseline_bundles": ProjectControlBaselineBundle,
            "periods": ProjectControlsPeriod,
            "schedule_versions": ScheduleVersion,
            "scope_items": ScopeItem,
            "plan_items": PlanItem,
            "packages": WorkPackage,
            "control_accounts": ControlAccount,
            "cbs": CostCBS,
            "cost_codes": CostCode,
            "commitments": CostCommitmentReference,
        }
        return {
            "context": self._operational().context(workspace),
            "authority": "GOVERNED_FORECAST_PROJECTION",
            "configuration": self._profile_out(profile) if profile else None,
            "allowed_actions": self.allowed_actions(project),
            "methods": METHODS,
            "versions": self.versions(workspace)["items"],
            "history": self.history(workspace)["items"],
            "users": [
                {"id": r.id, "name": r.full_name}
                for r in self.db.scalars(select(UserAccount).where(UserAccount.tenant_id == self.tenant_id))
            ],
            **{name: [self._out(r) for r in self._rows(model, workspace)] for name, model in collections.items()},
        }

    def history(self, workspace):
        self._permission("read", self._project(workspace))
        rows = self._rows(ForecastHistory, workspace)
        return {"items": [self._out(r) for r in rows], "total": len(rows)}

    def _editable_period(self, workspace, values, profile, *, successor=None):
        period = self._get(ProjectControlsPeriod, workspace, values.period_id, lock=True)
        if not period.period_start <= values.as_of <= period.period_end:
            self._error(422, "FORECAST_PERIOD_AS_OF_MISMATCH")
        if period.status in {"OPEN", "REVIEW"}:
            return period
        if (
            period.status == "PUBLISHED"
            and successor is not None
            and successor.status == "APPROVED"
            and profile.content_json["allow_published_period_successor"]
            and values.evidence_ref
        ):
            return period
        self._error(409, "FORECAST_PERIOD_NOT_EDITABLE_SUCCESSOR_REQUIRED")

    def _validate_input(self, workspace, payload, profile):
        if (
            payload.currency not in profile.content_json["currencies"]
            or payload.method not in profile.content_json["allowed_methods"]
        ):
            self._error(422, "FORECAST_METHOD_OR_CURRENCY_DISABLED")
        codes = [r.code for r in payload.assumptions]
        if len(codes) != len(set(codes)):
            self._error(422, "FORECAST_DUPLICATE_ASSUMPTION")
        for assumption in payload.assumptions:
            owner = self.db.scalar(
                select(UserAccount.id).where(
                    UserAccount.id == assumption.owner_id, UserAccount.tenant_id == self.tenant_id
                )
            )
            if owner is None:
                self._error(422, "FORECAST_ASSUMPTION_OWNER_OUTSIDE_TENANT")
            if assumption.effective_date > payload.as_of:
                self._error(422, "FORECAST_ASSUMPTION_NOT_EFFECTIVE_AS_OF")
            if assumption.source_reference.startswith("engineering-revision:"):
                from app.modules.engineering_foundation.integration import resolve_forecast_issue_fact

                if assumption.kind != "FORECAST_DATE" or assumption.unit != "date":
                    self._error(422, "FORECAST_ENGINEERING_DATE_ASSUMPTION_REQUIRED")
                try:
                    fact = resolve_forecast_issue_fact(
                        self.db,
                        self.tenant_id,
                        workspace,
                        assumption.source_reference,
                        payload.as_of,
                    )
                except ValueError as error:
                    self._error(409, str(error))
                if fact["forecast_issue_date"] != assumption.value:
                    self._error(422, "FORECAST_ENGINEERING_DATE_MISMATCH")
        dimensions = {
            "scope_item_id": ScopeItem,
            "plan_item_id": PlanItem,
            "work_package_id": WorkPackage,
            "control_account_id": ControlAccount,
            "cbs_id": CostCBS,
            "cost_code_id": CostCode,
            "schedule_version_id": ScheduleVersion,
        }
        for family in FAMILIES:
            components = getattr(payload, family)
            if len({r.code for r in components}) != len(components):
                self._error(422, "FORECAST_DUPLICATE_COMPONENT")
            for component in components:
                if component.method not in profile.content_json["allowed_methods"]:
                    self._error(422, "FORECAST_METHOD_DISABLED")
                if set(component.assumption_codes) - set(codes) or len(component.assumption_codes) != len(
                    set(component.assumption_codes)
                ):
                    self._error(422, "FORECAST_ASSUMPTION_REFERENCE_INVALID")
                for field, model in dimensions.items():
                    if getattr(component, field):
                        self._get(model, workspace, getattr(component, field))
                if component.schedule_version_id not in {None, payload.schedule_version_id}:
                    self._error(422, "FORECAST_COMPONENT_SCHEDULE_VERSION_MISMATCH")
                if component.currency not in {None, payload.currency}:
                    self._error(422, "FORECAST_COMPONENT_CURRENCY_MISMATCH")

    def save_version(self, workspace, payload, key, identity=None, expected=None, *, successor=False):
        self._ready(workspace, "create" if identity is None or successor else "edit")

        def apply():
            _, profile = self._ready(workspace, "create" if identity is None or successor else "edit")
            old = self._get(ForecastVersion, workspace, identity, lock=True) if identity else None
            if old:
                self._version(old.version, expected)
                if successor and old.status != "APPROVED" or not successor and old.status != "DRAFT":
                    self._error(409, "FORECAST_APPROVED_IMMUTABLE_SUCCESSOR_REQUIRED")
            parent = (
                old
                if successor
                else self._get(ForecastVersion, workspace, old.supersedes_id)
                if old and old.supersedes_id
                else None
            )
            self._editable_period(workspace, payload, profile, successor=parent)
            self._validate_input(workspace, payload, profile)
            snapshot, _ = self._source_context(workspace, payload, profile)
            if old is None or successor:
                if successor and payload.code != old.code:
                    self._error(422, "FORECAST_SUCCESSOR_CODE_MUST_MATCH")
                existing = [r for r in self._rows(ForecastVersion, workspace) if r.code == payload.code]
                if existing and not successor:
                    self._error(409, "FORECAST_CODE_EXISTS")
                if successor and (
                    any(r.supersedes_id == old.id for r in existing)
                    or max((r.revision for r in existing), default=0) != old.revision
                ):
                    self._error(409, "FORECAST_LATEST_VERSION_WITHOUT_SUCCESSOR_REQUIRED")
                row = ForecastVersion(
                    **self._base(workspace),
                    prepared_by=self.actor_id,
                    updated_by=self.actor_id,
                    revision=old.revision + 1 if successor else 1,
                    supersedes_id=old.id if successor else None,
                    status="DRAFT",
                )
                self.db.add(row)
            else:
                row = old
                self._permission("assumption.edit", self._project(workspace))
                for model in (ForecastAssumption, ForecastComponent):
                    for child in self._rows(model, workspace):
                        if child.forecast_version_id == row.id:
                            self.db.delete(child)
                self.db.flush()
                row.version += 1
                row.updated_by = self.actor_id
            for field in ForecastIn.model_fields:
                if field not in {"assumptions", *FAMILIES}:
                    setattr(row, field, getattr(payload, field))
            row.configuration_id, row.configuration_hash = profile.id, profile.content_hash
            row.source_snapshot_json, row.source_hashes_json = snapshot, snapshot["hashes"]
            row.data_date_reference = snapshot["current_schedule"]["data_date"]
            row.result_json = {}
            row.content_hash = _hash(payload.model_dump(mode="json"))
            self.db.flush()
            for assumption in payload.assumptions:
                values = assumption.model_dump(mode="json")
                values["effective_date"] = assumption.effective_date
                self.db.add(
                    ForecastAssumption(
                        **self._base(workspace),
                        forecast_version_id=row.id,
                        content_hash=_hash(assumption.model_dump(mode="json")),
                        **values,
                    )
                )
            for family, kind in FAMILIES.items():
                for component in getattr(payload, family):
                    values = component.model_dump(mode="json")
                    self.db.add(
                        ForecastComponent(
                            **self._base(workspace),
                            forecast_version_id=row.id,
                            component_kind=kind,
                            content_hash=_hash(values),
                            result_json={},
                            **values,
                        )
                    )
            result = self._record(
                row,
                "FORECAST_VERSION_CREATED"
                if old is None
                else "FORECAST_SUCCESSOR_CREATED"
                if successor
                else "FORECAST_ASSUMPTION_CHANGED",
                payload.reason,
            )
            return result

        return self._write(
            "version.successor" if successor else "version.save", workspace, payload, key, apply, identity, expected
        )

    def _assumption(self, row, component, assumptions, pointer, kind, *, unit=None, monetary=False):
        code = component["inputs"].get(pointer)
        if code is None:
            candidates = [
                a for a in assumptions.values() if a["code"] in component["assumption_codes"] and a["kind"] == kind
            ]
            if len(candidates) == 1:
                code = candidates[0]["code"]
        if code not in component["assumption_codes"] or code not in assumptions:
            raise ValueError("FORECAST_EXPLICIT_ASSUMPTION_REQUIRED:" + pointer)
        assumption = assumptions[code]
        if (
            assumption["kind"] != kind
            or assumption["status"] != "CONFIRMED"
            or _date(assumption["effective_date"]) > row.as_of
        ):
            raise ValueError("FORECAST_CONFIRMED_COMPATIBLE_ASSUMPTION_REQUIRED:" + code)
        if unit is not None and assumption["unit"] != unit:
            raise ValueError("FORECAST_ASSUMPTION_UNIT_MISMATCH:" + code)
        if monetary and assumption["currency"] != row.currency:
            raise ValueError("FORECAST_ASSUMPTION_CURRENCY_MISMATCH:" + code)
        return assumption

    @staticmethod
    def _matches_dimensions(item, component):
        fields = ("control_account_id", "cbs_id", "cost_code_id", "scope_item_id", "plan_item_id", "work_package_id")
        return all(item.get(key) == component.get(key) for key in fields if component.get(key))

    def _component_lineage(self, component, snapshot):
        scopes = {r["id"]: r for r in snapshot["baseline_scope"]["snapshot_json"].get("items", [])}
        plans = {r["id"]: r for r in snapshot["plans"]}
        scope_ids = set()
        if component.get("scope_item_id"):
            if component["scope_item_id"] not in scopes:
                raise ValueError("FORECAST_SCOPE_OUTSIDE_APPROVED_BASELINE")
            scope_ids.add(component["scope_item_id"])
        if component.get("plan_item_id"):
            plan = plans.get(component["plan_item_id"])
            if not plan or plan["status"] != "PUBLISHED":
                raise ValueError("FORECAST_PUBLISHED_PLAN_REQUIRED")
            allocated = {a["scope_item_id"] for a in snapshot["plan_allocations"] if a["plan_item_id"] == plan["id"]}
            if not allocated or allocated - set(scopes) or scope_ids and not scope_ids.issubset(allocated):
                raise ValueError("FORECAST_PLAN_SCOPE_COVERAGE_INVALID")
            scope_ids |= allocated
        activities = {
            str(r["external_id"]): r for r in snapshot["current_schedule"]["snapshot_json"].get("activities", [])
        }
        if component.get("activity_external_id"):
            if component["activity_external_id"] not in activities:
                raise ValueError("FORECAST_CURRENT_ACTIVITY_NOT_FOUND")
            mappings = [
                r
                for r in snapshot["current_schedule_mappings"]
                if r.get("target_kind") == "ACTIVITY"
                and str(r["target_external_id"]) == component["activity_external_id"]
            ]
            if not mappings or any(r.get("status") != "VALID" for r in mappings):
                raise ValueError("FORECAST_ACTIVITY_MAPPING_REQUIRES_REVIEW")
            mapped = {i for r in mappings for i in r.get("resolved_scope_item_ids", r.get("scope_item_ids", []))}
            if mapped - set(scopes) or scope_ids and not scope_ids.issubset(mapped):
                raise ValueError("FORECAST_ACTIVITY_SCOPE_MISMATCH")
            scope_ids |= mapped
        if component.get("wbs_external_id") and component["wbs_external_id"] not in {
            str(r["external_id"]) for r in snapshot["current_schedule"]["snapshot_json"].get("wbs", [])
        }:
            raise ValueError("FORECAST_CURRENT_WBS_NOT_FOUND")
        if component.get("work_package_id"):
            package = next((r for r in snapshot["packages"] if r["id"] == component["work_package_id"]), None)
            mappings = [
                r
                for r in snapshot["effective_package_mappings"]
                if r.get("work_package_id") == component["work_package_id"]
            ]
            if package is None or package["status"] == "SUPERSEDED" or not mappings:
                raise ValueError("FORECAST_VALID_PACKAGE_MAPPING_REQUIRED")
            if any(r.get("mapping_health", "VALID") != "VALID" for r in mappings):
                raise ValueError("FORECAST_PACKAGE_MAPPING_REQUIRES_REVIEW")
            direct = {r["target_id"] for r in mappings if r["target_kind"] == "SCOPE"}
            mapped_plans = {r["target_id"] for r in mappings if r["target_kind"] == "PLAN"}
            direct |= {a["scope_item_id"] for a in snapshot["plan_allocations"] if a["plan_item_id"] in mapped_plans}
            if direct - set(scopes) or scope_ids and direct and not scope_ids.issubset(direct):
                raise ValueError("FORECAST_PACKAGE_SCOPE_MISMATCH")
            scope_ids |= direct
        if component["component_kind"] == "COST":
            lines = snapshot["baseline_cost"]["snapshot_json"].get("lines", [])
            if not any(self._matches_dimensions(line, component) for line in lines):
                raise ValueError("FORECAST_COST_CONTROL_COVERAGE_INVALID")
        return sorted(scope_ids)

    def _remaining_quantity(self, row, component, assumptions, snapshot):
        explicit = component["inputs"].get("quantity_assumption_code")
        if explicit:
            assumption = self._assumption(
                row, component, assumptions, "quantity_assumption_code", "QUANTITY", unit=component["unit"]
            )
            return number(assumption["value"]), {
                "source": "GOVERNED_REMAINING_QUANTITY_ASSUMPTION",
                "assumption_code": assumption["code"],
                "unit": component["unit"],
            }
        dimension = (
            "plan_item_id"
            if component.get("plan_item_id")
            else "scope_item_id"
            if component.get("scope_item_id")
            else "work_package_id"
            if component.get("work_package_id")
            else None
        )
        if dimension is None:
            raise ValueError("FORECAST_REMAINING_QUANTITY_BASIS_REQUIRED")
        matches = [
            r
            for r in snapshot["approved_progress"]
            if r.get(dimension) == component[dimension]
            and r["method"] == "QUANTITY_BASED"
            and r["progress_type"] in {"QUANTITY", "PHYSICAL"}
            and r["unit"] == component["unit"]
        ]
        phase = component["inputs"].get("phase")
        if phase:
            matches = [r for r in matches if r["phase"] == phase]
        preferred = [r for r in matches if r["progress_type"] == "QUANTITY"] or matches
        if len(preferred) != 1:
            raise ValueError("FORECAST_APPROVED_QUANTITY_COVERAGE_AMBIGUOUS_OR_MISSING")
        progress = preferred[0]
        if component.get("scope_item_id") and progress.get("scope_item_id") not in {None, component["scope_item_id"]}:
            raise ValueError("FORECAST_QUANTITY_SCOPE_MISMATCH")
        denominator, completed = number(progress["denominator"], positive=True), number(progress["cumulative_quantity"])
        remaining = max(ZERO, denominator - completed)
        return number(remaining), {
            "source": "APPROVED_QUANTITY_PROGRESS",
            "measurement_id": progress["id"],
            "measurement_hash": progress["content_hash"],
            "denominator": str(denominator),
            "completed": str(completed),
            "overrun": completed > denominator,
            "unit": progress["unit"],
        }

    def _commitment_remaining(self, row, component, snapshot, used_commitments, used_actuals):
        identities = component["inputs"].get("commitment_ids", [])
        if not identities or len(identities) != len(set(identities)):
            raise ValueError("FORECAST_VERIFIED_COMMITMENT_REFERENCE_REQUIRED")
        all_commitments = {r["id"]: r for r in snapshot["commitments"]["items"]}
        actual_ids = component["inputs"].get("incurred_actual_ids", [])
        if len(actual_ids) != len(set(actual_ids)) or set(actual_ids) & used_actuals:
            raise ValueError("FORECAST_INCURRED_ACTUAL_DOUBLE_COUNT")
        if len(identities) > 1 and actual_ids:
            raise ValueError("FORECAST_COMMITMENT_INCURRED_ALLOCATION_AMBIGUOUS")
        total, basis = ZERO, []
        for identity in identities:
            commitment = all_commitments.get(identity)
            if identity in used_commitments:
                raise ValueError("FORECAST_COMMITMENT_DOUBLE_ADD")
            if (
                commitment is None
                or commitment["status"] != "VERIFIED"
                or commitment["reconciliation_decision"] != "ADDITIVE_ONCE"
            ):
                raise ValueError("FORECAST_ADDITIVE_VERIFIED_COMMITMENT_REQUIRED")
            financial_fields = ("control_account_id", "cbs_id", "cost_code_id")
            if (
                commitment["currency"] != row.currency
                or not any(component.get(key) for key in financial_fields)
                or any(commitment.get(key) != component.get(key) for key in financial_fields if component.get(key))
            ):
                raise ValueError("FORECAST_COMMITMENT_BASIS_MISMATCH")
            compatible_actuals = [
                a
                for a in snapshot["actuals"]
                if all(a.get(k) == commitment.get(k) for k in ("control_account_id", "cbs_id", "cost_code_id"))
            ]
            assigned = [a for a in compatible_actuals if a["id"] in actual_ids]
            if set(actual_ids) != {a["id"] for a in assigned}:
                raise ValueError("FORECAST_INCURRED_ACTUAL_BASIS_MISMATCH")
            # Absence of an explicit mapping is not evidence that an obligation
            # sharing recognized costs is entirely unincurred.
            if compatible_actuals and not actual_ids:
                raise ValueError("FORECAST_COMMITMENT_INCURRED_MAPPING_REQUIRED")
            incurred = sum((number(a["amount"], nonnegative=False) for a in assigned), ZERO)
            gross = number(commitment["net_contribution"])
            if incurred < ZERO or incurred > gross:
                raise ValueError("FORECAST_INCURRED_EXCEEDS_COMMITMENT")
            total += gross - incurred
            used_commitments.add(identity)
            used_actuals.update(actual_ids)
            basis.append(
                {
                    "commitment_id": identity,
                    "economic_origin": commitment["economic_origin"],
                    "source_hash": commitment["source_hash"],
                    "gross": str(gross),
                    "recognized_incurred": str(incurred),
                    "incurred_actual_ids": actual_ids,
                    "remaining": str(gross - incurred),
                }
            )
        return number(total), basis

    def _cost_item(self, row, component, assumptions, snapshot, used_commitments, used_actuals):
        method, inputs = component["method"], component["inputs"]

        def monetary(pointer, kind="AMOUNT", unit=None):
            return number(
                self._assumption(row, component, assumptions, pointer, kind, unit=unit, monetary=True)["value"]
            )

        arguments, quantity_basis = {}, None
        if method in {"BOTTOM_UP", "CONTROL_ACCOUNT", "MANUAL_GOVERNED"}:
            if method == "CONTROL_ACCOUNT" and not component.get("control_account_id"):
                raise ValueError("FORECAST_CONTROL_ACCOUNT_REQUIRED")
            arguments["amount"] = monetary("amount_assumption_code", unit=row.currency)
        elif method == "QUANTITY_RATE":
            arguments["quantity"], quantity_basis = self._remaining_quantity(row, component, assumptions, snapshot)
            arguments["rate"] = monetary("rate_assumption_code", "RATE", f"{row.currency}/{component['unit']}")
        elif method == "ACTIVITY_REMAINING_DURATION":
            if not component.get("activity_external_id"):
                raise ValueError("FORECAST_DURATION_COST_ACTIVITY_REFERENCE_REQUIRED")
            duration = self._assumption(row, component, assumptions, "duration_assumption_code", "DURATION")
            if duration["unit"] not in {"day", "h"}:
                raise ValueError("FORECAST_DURATION_UNIT_REQUIRED")
            arguments["duration"] = number(duration["value"])
            arguments["daily_rate"] = monetary("rate_assumption_code", "RATE", f"{row.currency}/{duration['unit']}")
        elif method == "PRODUCTIVITY_BASED":
            arguments["quantity"], quantity_basis = self._remaining_quantity(row, component, assumptions, snapshot)
            productivity = self._assumption(
                row,
                component,
                assumptions,
                "productivity_assumption_code",
                "PRODUCTIVITY",
                unit=f"{component['unit']}/day",
            )
            arguments["productivity"] = number(productivity["value"], positive=True)
            arguments["daily_rate"] = monetary("rate_assumption_code", "RATE", f"{row.currency}/day")
        elif method == "COMMITMENT_BASED":
            arguments["commitment_remaining"], quantity_basis = self._commitment_remaining(
                row, component, snapshot, used_commitments, used_actuals
            )
        elif method == "TREND_BASED":
            prior = self._get(ForecastVersion, row.project_workspace_id, inputs.get("prior_forecast_id", 0))
            if (
                prior.status != "APPROVED"
                or prior.as_of >= row.as_of
                or prior.currency != row.currency
                or prior.result_json.get("cost", {}).get("status") != "COMPUTABLE"
            ):
                raise ValueError("FORECAST_APPROVED_PRIOR_TREND_BASIS_REQUIRED")
            arguments["prior_etc"] = prior.result_json["cost"]["etc"]
            factor = self._assumption(
                row, component, assumptions, "trend_factor_assumption_code", "FACTOR", unit="ratio"
            )
            arguments["trend_factor"] = number(factor["value"], positive=True)
            quantity_basis = {"prior_forecast_id": prior.id, "hash": prior.content_hash}
        value = cost_value(method, **arguments)
        bucket = inputs.get("cost_bucket", "COMMITTED" if method == "COMMITMENT_BASED" else "UNCOMMITTED")
        if bucket not in {"COMMITTED", "UNCOMMITTED", "ALLOWANCE"}:
            raise ValueError("FORECAST_COST_BUCKET_INVALID")
        if (
            method == "COMMITMENT_BASED"
            and bucket != "COMMITTED"
            or method != "COMMITMENT_BASED"
            and bucket == "COMMITTED"
        ):
            raise ValueError("FORECAST_COMMITTED_ETC_REQUIRES_VERIFIED_OBLIGATION")
        if bucket == "ALLOWANCE" and not self._profile(row.configuration_id).content_json["allow_allowance"]:
            raise ValueError("FORECAST_ALLOWANCE_DISABLED")
        phasing = inputs.get("forecast_spread", inputs.get("phasing", []))
        if phasing:
            if (
                any(
                    _date(point["date"]) <= row.as_of or point.get("currency", row.currency) != row.currency
                    for point in phasing
                )
                or sum((number(point["amount"]) for point in phasing), ZERO) != value
            ):
                raise ValueError("FORECAST_PHASING_MUST_RECONCILE_ETC_AFTER_ASOF")
        return {
            "status": "COMPUTABLE",
            "reason_codes": [],
            "amount": str(value),
            "cost_bucket": bucket,
            "currency": row.currency,
            "quantity_basis": quantity_basis,
            "inputs_resolved": _json(arguments),
            "phasing": phasing,
        }

    def _time_item(self, row, component, assumptions, snapshot, profile):
        identity = component.get("activity_external_id")
        activity = next(
            (
                r
                for r in snapshot["current_schedule"]["snapshot_json"].get("activities", [])
                if str(r["external_id"]) == identity
            ),
            None,
        )
        baseline = next(
            (
                r
                for r in snapshot["baseline_schedule"]["snapshot_json"]
                .get("schedule_snapshot", {})
                .get("activities", [])
                if str(r["external_id"]) == identity
            ),
            None,
        )
        current_finish = _date(activity.get("finish") or activity.get("planned_finish")) if activity else None
        baseline_finish = _date(baseline.get("finish") or baseline.get("planned_finish")) if baseline else None
        engineering_source = None
        if component["inputs"].get("date_assumption_code"):
            if not profile.content_json["allow_manual_finish"] or component["method"] != "MANUAL_GOVERNED":
                raise ValueError("FORECAST_MANUAL_FINISH_DISABLED_OR_METHOD_INVALID")
            assumption = self._assumption(
                row, component, assumptions, "date_assumption_code", "FORECAST_DATE", unit="date"
            )
            projected = _date(assumption["value"])
            source = "GOVERNED_MANUAL_FINISH_ASSUMPTION"
            if assumption.get("source_reference", "").startswith("engineering-revision:"):
                from app.modules.engineering_foundation.integration import resolve_forecast_issue_fact

                engineering_source = resolve_forecast_issue_fact(
                    self.db,
                    self.tenant_id,
                    row.project_workspace_id,
                    assumption["source_reference"],
                    row.as_of,
                    component | {"schedule_version_id": row.schedule_version_id},
                )
                if engineering_source["forecast_issue_date"] != assumption["value"]:
                    raise ValueError("FORECAST_ENGINEERING_DATE_MISMATCH")
                source = "GOVERNED_ENGINEERING_ISSUE_ASSUMPTION"
        elif activity is not None and component["method"] == "ACTIVITY_REMAINING_DURATION":
            projected, source = current_finish, "ACCEPTED_P6_FINISH_NO_LOCAL_CPM"
        else:
            raise ValueError("FORECAST_ACCEPTED_ACTIVITY_OR_MANUAL_FINISH_REQUIRED")
        if projected is None:
            raise ValueError("FORECAST_FINISH_SOURCE_MISSING")
        if (
            projected < row.as_of
            and activity
            and str(activity.get("status", "")).upper() not in {"COMPLETED", "COMPLETE"}
        ):
            raise ValueError("FORECAST_UNCOMPLETED_FINISH_BEFORE_ASOF")
        result = {
            "status": "COMPUTABLE",
            "reason_codes": [],
            "baseline_finish": str(baseline_finish) if baseline_finish else None,
            "current_finish": str(current_finish) if current_finish else None,
            "forecast_finish": projected.isoformat(),
            "finish_variance_days": (projected - baseline_finish).days if baseline_finish else None,
            "current_variance_days": (projected - current_finish).days if current_finish else None,
            "source_activity": identity,
            "source_schedule_version_id": row.schedule_version_id,
            "source": source,
            "data_date": row.data_date_reference,
            "remaining_duration": activity.get("remaining_duration") if activity else None,
            "remaining_duration_basis": "P6_IMPORTED_NO_CALENDAR_ADDITION",
            "milestone_type": component["inputs"].get("milestone_type", "KEY_PROJECT"),
            "cpm_calculated": False,
        }
        if engineering_source:
            result["engineering_source"] = engineering_source
        return result

    def _resource_item(self, row, component, assumptions, snapshot, profile):
        if component["method"] != "PRODUCTIVITY_BASED":
            raise ValueError("FORECAST_RESOURCE_PRODUCTIVITY_METHOD_REQUIRED")
        kind = component["inputs"].get("resource_type")
        if kind not in profile.content_json["resource_types"]:
            raise ValueError("FORECAST_RESOURCE_TYPE_DISABLED")
        quantity, basis = self._remaining_quantity(row, component, assumptions, snapshot)
        productivity_basis = component["inputs"].get("productivity_basis", "HOURS_PER_UNIT")
        unit = f"h/{component['unit']}" if productivity_basis == "HOURS_PER_UNIT" else f"{component['unit']}/day"
        productivity = self._assumption(
            row, component, assumptions, "productivity_assumption_code", "PRODUCTIVITY", unit=unit
        )
        crew = (
            self._assumption(row, component, assumptions, "crew_assumption_code", "CREW", unit="person")
            if component["inputs"].get("crew_assumption_code")
            else None
        )
        if crew is not None and productivity_basis != "QUANTITY_PER_DAY":
            raise ValueError("FORECAST_CREW_REQUIRES_QUANTITY_PER_DAY_BASIS")
        result = resource_value(
            quantity, productivity["value"], productivity_basis, crew_size=crew["value"] if crew else None
        )
        references = {}
        for key in ("planned_productivity_assumption_code", "actual_productivity_assumption_code"):
            if component["inputs"].get(key):
                reference = self._assumption(row, component, assumptions, key, "PRODUCTIVITY", unit=unit)
                references[key.removesuffix("_assumption_code")] = {
                    "value": str(number(reference["value"], positive=True)),
                    "source_reference": reference["source_reference"],
                    "code": reference["code"],
                }
        if kind == "EQUIPMENT" and result["unit"] == "h":
            result["unit"] = "equipment-hour"
        if kind == "CREW" and result["unit"] == "day":
            result["unit"] = "crew-day"
        return {
            "status": "COMPUTABLE",
            "reason_codes": [],
            "resource_type": kind,
            **result,
            "remaining_quantity": str(quantity),
            "quantity_unit": component["unit"],
            "quantity_basis": basis,
            "forecast_productivity": {
                "value": str(number(productivity["value"], positive=True)),
                "unit": unit,
                "assumption_code": productivity["code"],
            },
            **references,
            "cpm_calculated": False,
        }

    def _calculate(self, row, profile):
        snapshot, source_errors = self._source_context(row.project_workspace_id, row, profile)
        if row.configuration_id != profile.id or row.configuration_hash != profile.content_hash:
            source_errors.append("FORECAST_CONFIGURATION_SUCCESSOR_REQUIRES_REVIEW")
        assumptions = {
            r.code: self._out(r)
            for r in self._rows(ForecastAssumption, row.project_workspace_id)
            if r.forecast_version_id == row.id
        }
        components = [
            self._out(r, exclude={"result_json", "amount", "quantity", "forecast_finish"})
            for r in self._rows(ForecastComponent, row.project_workspace_id)
            if r.forecast_version_id == row.id
        ]
        if profile.content_json["require_confirmed_assumptions"] and any(
            r["status"] != "CONFIRMED" for r in assumptions.values()
        ):
            source_errors.append("FORECAST_CONFIRMED_ASSUMPTIONS_REQUIRED")
        families = {kind: [] for kind in FAMILIES.values()}
        used_commitments, used_actuals, coverages = set(), set(), []
        for component in components:
            try:
                scope_ids = self._component_lineage(component, snapshot)
                if component["component_kind"] == "COST":
                    bucket = component["inputs"].get(
                        "cost_bucket", "COMMITTED" if component["method"] == "COMMITMENT_BASED" else "UNCOMMITTED"
                    )
                    control_key = tuple(component.get(key) for key in ("control_account_id", "cbs_id", "cost_code_id"))
                    for prior_scopes, prior_key, prior_bucket in coverages:
                        if (
                            scope_ids
                            and set(scope_ids) & prior_scopes
                            and control_key == prior_key
                            and bucket == prior_bucket
                        ):
                            raise ValueError("FORECAST_COST_COVERAGE_OVERLAP")
                    coverages.append((set(scope_ids), control_key, bucket))
                    calculation = self._cost_item(row, component, assumptions, snapshot, used_commitments, used_actuals)
                elif component["component_kind"] in {"TIME", "MILESTONE"}:
                    calculation = self._time_item(row, component, assumptions, snapshot, profile)
                else:
                    calculation = self._resource_item(row, component, assumptions, snapshot, profile)
                calculation["resolved_scope_item_ids"] = scope_ids
            except (ValueError, DecimalException, OverflowError, KeyError, TypeError) as error:
                calculation = {
                    "status": "NOT_COMPUTABLE",
                    "reason_codes": [str(error) or "FORECAST_COMPONENT_BASIS_INVALID"],
                    "amount": None,
                    "quantity": None,
                    "forecast_finish": None,
                }
            families[component["component_kind"]].append({**component, **calculation})
        engineering_facts = {
            f"{kind}:{component['code']}": component["engineering_source"]
            for kind in ("TIME", "MILESTONE")
            for component in families[kind]
            if component.get("engineering_source")
        }
        if engineering_facts:
            snapshot["engineering_issue_facts"] = engineering_facts
            snapshot["hashes"]["engineering_issue_facts"] = _hash(engineering_facts)
        cost_errors = list(source_errors)
        cost_items = families["COST"]
        if not cost_items:
            cost_errors.append("FORECAST_COST_COMPONENTS_REQUIRED")
        for component in cost_items:
            if component["status"] != "COMPUTABLE":
                cost_errors.extend(component["reason_codes"])
        buckets = {
            name: sum(
                (number(r["amount"]) for r in cost_items if r["status"] == "COMPUTABLE" and r["cost_bucket"] == name),
                ZERO,
            )
            for name in ("COMMITTED", "UNCOMMITTED", "ALLOWANCE")
        }
        actuals = snapshot["actuals"]
        actual = sum((number(a["amount"], nonnegative=False) for a in actuals), ZERO) if actuals else None
        if actual is not None and actual < ZERO:
            cost_errors.append("FORECAST_NEGATIVE_RECOGNIZED_ACTUAL_BASIS")
        baseline_lines = snapshot["baseline_cost"]["snapshot_json"].get("lines", [])
        if any(line["currency"] != row.currency for line in baseline_lines):
            cost_errors.append("FORECAST_BASELINE_CURRENCY_MISMATCH")
        structures = snapshot["baseline_cost"]["snapshot_json"].get("control_structures", {})
        for item in actuals:
            for field, collection in (
                ("control_account_id", "accounts"),
                ("cbs_id", "cbs"),
                ("cost_code_id", "cost_codes"),
            ):
                if item.get(field) and item[field] not in {r["id"] for r in structures.get(collection, [])}:
                    cost_errors.append("FORECAST_ACTUAL_CONTROL_BASIS_MISMATCH")
        bac = sum((number(line["amount"]) for line in baseline_lines), ZERO) if baseline_lines else None
        cost = eac_values(actual, sum(buckets.values(), ZERO) if not cost_errors else None, bac, reasons=cost_errors)
        groups = {}
        for name in (
            "control_account_id",
            "cbs_id",
            "cost_code_id",
            "scope_item_id",
            "plan_item_id",
            "work_package_id",
            "wbs_external_id",
        ):
            grouped = defaultdict(list)
            for component in cost_items:
                grouped[str(component.get(name) or "UNASSIGNED")].append(component)
            groups[name] = [
                {
                    "key": key,
                    "status": "COMPUTABLE" if all(c["status"] == "COMPUTABLE" for c in values) else "NOT_COMPUTABLE",
                    "etc": str(sum((number(c["amount"]) for c in values), ZERO))
                    if all(c["status"] == "COMPUTABLE" for c in values)
                    else None,
                    "component_ids": [c["id"] for c in values],
                    "currency": row.currency,
                }
                for key, values in grouped.items()
            ]
        cost.update(
            currency=row.currency,
            as_of=row.as_of.isoformat(),
            original_budget=snapshot["original_budget"],
            current_budget=snapshot["current_budget"],
            cost_baseline={
                "id": snapshot["baseline_cost"]["id"],
                "hash": snapshot["baseline_cost"]["content_hash"],
                "amount": str(bac) if bac is not None else None,
                "currency": row.currency,
            },
            commitment=snapshot["commitments"],
            committed_etc=str(buckets["COMMITTED"]) if not cost_errors else None,
            uncommitted_etc=str(buckets["UNCOMMITTED"]) if not cost_errors else None,
            allowance=str(buckets["ALLOWANCE"]) if not cost_errors else None,
            items=cost_items,
            groups=groups,
            commitment_added_to_eac=False,
            source_values={
                "recognized_actual": str(actual) if actual is not None else None,
                "baseline_bac": str(bac) if bac is not None else None,
            },
        )
        baseline_activities = (
            snapshot["baseline_schedule"]["snapshot_json"].get("schedule_snapshot", {}).get("activities", [])
        )
        current_activities = snapshot["current_schedule"]["snapshot_json"].get("activities", [])
        baseline_finish = max(
            (
                _date(a.get("finish") or a.get("planned_finish"))
                for a in baseline_activities
                if a.get("finish") or a.get("planned_finish")
            ),
            default=None,
        )
        current_finish = max(
            (
                _date(a.get("finish") or a.get("planned_finish"))
                for a in current_activities
                if a.get("finish") or a.get("planned_finish")
            ),
            default=None,
        )
        times = families["TIME"]
        milestones = families["MILESTONE"]
        time_errors = list(source_errors)
        for component in times + milestones:
            if component["status"] != "COMPUTABLE":
                time_errors.extend(component["reason_codes"])
        activity_overrides = defaultdict(list)
        valid_dates = []
        for component in times:
            if component["status"] == "COMPUTABLE":
                projected = _date(component["forecast_finish"])
                if component.get("source_activity"):
                    activity_overrides[component["source_activity"]].append(projected)
                else:
                    valid_dates.append(projected)
        if any(len(values) > 1 for values in activity_overrides.values()):
            time_errors.append("FORECAST_ACTIVITY_FINISH_OVERRIDE_AMBIGUOUS")
        for activity in current_activities:
            identity = str(activity["external_id"])
            if identity in activity_overrides:
                valid_dates.extend(activity_overrides[identity])
            elif activity.get("finish") or activity.get("planned_finish"):
                valid_dates.append(_date(activity.get("finish") or activity.get("planned_finish")))
        forecast_finish = max(valid_dates, default=None)
        if forecast_finish is None:
            time_errors.append("FORECAST_ACCEPTED_FINISH_REQUIRED")
        if (
            forecast_finish
            and forecast_finish < row.as_of
            and any(str(a.get("status", "")).upper() not in {"COMPLETED", "COMPLETE"} for a in current_activities)
        ):
            time_errors.append("FORECAST_UNCOMPLETED_PROJECT_FINISH_BEFORE_ASOF")
        time = {
            "status": "NOT_COMPUTABLE" if time_errors else "COMPUTABLE",
            "reason_codes": list(dict.fromkeys(time_errors)),
            "baseline_finish": baseline_finish.isoformat() if baseline_finish else None,
            "current_finish": current_finish.isoformat() if current_finish else None,
            "forecast_finish": forecast_finish.isoformat() if forecast_finish and not time_errors else None,
            "finish_variance_days": (forecast_finish - baseline_finish).days
            if forecast_finish and baseline_finish and not time_errors
            else None,
            "current_finish_variance_days": (forecast_finish - current_finish).days
            if forecast_finish and current_finish and not time_errors
            else None,
            "source_schedule_version_id": row.schedule_version_id,
            "source_schedule_hash": snapshot["current_schedule"]["content_hash"],
            "data_date": row.data_date_reference,
            "items": times,
            "milestones": milestones,
            "cpm_calculated": False,
            "default_forecast_method": "ACCEPTED_P6_FINISH_NO_LOCAL_CPM" if not times else "EXPLICIT_COMPONENT_METHODS",
            "unmodified_activities_use_accepted_finish": True,
        }
        resources = families["RESOURCE"]
        resource_groups = defaultdict(list)
        for component in resources:
            if component["status"] == "COMPUTABLE":
                resource_groups[(component["resource_type"], component["unit"])].append(component)
        resource_result = {
            "status": "NOT_COMPUTABLE"
            if any(c["status"] != "COMPUTABLE" for c in resources)
            else "COMPUTABLE"
            if resources
            else "NOT_PROVIDED",
            "reason_codes": [reason for c in resources for reason in c["reason_codes"]],
            "items": resources,
            "groups": [
                {
                    "resource_type": kind,
                    "unit": unit,
                    "quantity": str(sum((number(c["quantity"]) for c in values), ZERO)),
                    "component_ids": [c["id"] for c in values],
                }
                for (kind, unit), values in sorted(resource_groups.items())
            ],
            "cross_unit_aggregation": False,
        }
        progress = ProgressIntegrationService(self.db, self.tenant_id, self.actor_id, self.access_context)
        evm = progress.evm(row.project_workspace_id, row.bundle_id, row.period_id, row.as_of, row.currency)
        errors = list(dict.fromkeys([*cost["reason_codes"], *time["reason_codes"], *resource_result["reason_codes"]]))
        result = {
            "status": "NOT_COMPUTABLE" if errors else "COMPUTABLE",
            "reason_codes": errors,
            "forecast_version_id": row.id,
            "period_id": row.period_id,
            "as_of": row.as_of.isoformat(),
            "currency": row.currency,
            "cost": cost,
            "time": time,
            "resources": resource_result,
            "evm": evm,
            "source_refs": {
                "bundle_id": row.bundle_id,
                "schedule_version_id": row.schedule_version_id,
                "cost_baseline_id": snapshot["baseline_cost"]["id"],
                "scope_baseline_id": snapshot["baseline_scope"]["id"],
                "forecast_configuration_id": row.configuration_id,
            },
            "source_hashes": snapshot["hashes"],
            "assumption_hashes": {a["code"]: a["content_hash"] for a in assumptions.values()},
            "confidence": {
                "label": row.confidence,
                "rationale": row.confidence_rationale,
                "statistical": False,
                "data_completeness": row.data_completeness,
                "assumption_maturity": row.assumption_maturity,
            },
            "authority": {
                "projection": "FORECAST",
                "actual": "COST",
                "baseline": "APPROVED_INTEGRATED_BUNDLE",
                "current_schedule": "ACCEPTED_P6",
                "source_mutations": False,
            },
        }
        return _json(result), snapshot

    def calculation_result(self, workspace, identity):
        self._permission("eac.view", self._project(workspace))
        row = self._get(ForecastVersion, workspace, identity)
        if row.status in {"APPROVED", "REJECTED"}:
            return deepcopy(row.result_json) | {"frozen": True, "forecast_status": row.status}
        _, profile = self._ready(workspace, "eac.view")
        result, _ = self._calculate(row, profile)
        return result | {"frozen": False, "preview_only": True, "forecast_status": row.status}

    def calculate_version(self, workspace, identity, payload, expected, key):
        self._ready(workspace, "etc.calculate")

        def apply():
            _, profile = self._ready(workspace, "etc.calculate")
            row = self._get(ForecastVersion, workspace, identity, lock=True)
            self._version(row.version, expected)
            if row.status != "DRAFT":
                self._error(409, "FORECAST_CALCULATE_DRAFT_REQUIRED")
            parent = self._get(ForecastVersion, workspace, row.supersedes_id) if row.supersedes_id else None
            self._editable_period(workspace, row, profile, successor=parent)
            result, snapshot = self._calculate(row, profile)
            row.result_json, row.source_snapshot_json, row.source_hashes_json = result, snapshot, snapshot["hashes"]
            material_input = {k: v for k, v in self._version_out(row)["input_json"].items() if k != "reason"}
            row.content_hash = _hash({"input": material_input, "result": result, "sources": snapshot["hashes"]})
            row.updated_by = self.actor_id
            for family in (
                result["cost"]["items"],
                result["time"]["items"],
                result["time"]["milestones"],
                result["resources"]["items"],
            ):
                for item in family:
                    child = self._get(ForecastComponent, workspace, item["id"])
                    child.result_json = {
                        key: value
                        for key, value in item.items()
                        if key not in ComponentIn.model_fields
                        and key
                        not in {
                            "result_json",
                            "created_at",
                            "created_by",
                            "tenant_id",
                            "project_workspace_id",
                            "forecast_version_id",
                        }
                    }
                    child.amount = number(item["amount"]) if item.get("amount") is not None else None
                    child.quantity = number(item["quantity"]) if item.get("quantity") is not None else None
                    child.forecast_finish = _date(item.get("forecast_finish"))
            return self._record(row, "FORECAST_CALCULATED", payload.reason, changed=True)

        return self._write("version.calculate", workspace, payload, key, apply, identity, expected)

    def transition_version(self, workspace, identity, payload, expected, key):
        action = "submit" if payload.action == "review" else "approve" if payload.action == "approve" else "review"
        self._ready(workspace, action)

        def apply():
            _, profile = self._ready(workspace, action)
            row = self._get(ForecastVersion, workspace, identity, lock=True)
            self._version(row.version, expected)
            expected_state = "DRAFT" if payload.action == "review" else "UNDER_REVIEW"
            if row.status != expected_state:
                self._error(409, "FORECAST_TRANSITION_STATE_INVALID")
            parent = self._get(ForecastVersion, workspace, row.supersedes_id) if row.supersedes_id else None
            self._editable_period(workspace, row, profile, successor=parent)
            if payload.action in {"review", "approve"}:
                if not row.result_json:
                    self._error(409, "FORECAST_EXPLICIT_CALCULATION_REQUIRED")
                live, snapshot = self._calculate(row, profile)
                if snapshot["hashes"] != row.source_hashes_json or live != row.result_json:
                    self._error(409, "FORECAST_SOURCE_DRIFT_RECALCULATION_REQUIRED")
                if profile.content_json["approval_requires_computable_cost"] and live["cost"]["status"] != "COMPUTABLE":
                    self._error(409, "FORECAST_NOT_COMPUTABLE", reason_codes=live["cost"]["reason_codes"])
                if live["time"]["status"] != "COMPUTABLE" or live["resources"]["status"] == "NOT_COMPUTABLE":
                    self._error(409, "FORECAST_NOT_COMPUTABLE", reason_codes=live["reason_codes"])
                if profile.content_json["approval_requires_assessed_completeness"] and (
                    row.data_completeness == "NOT_ASSESSED" or row.assumption_maturity == "NOT_ASSESSED"
                ):
                    self._error(409, "FORECAST_COMPLETENESS_AND_MATURITY_ASSESSMENT_REQUIRED")
            if payload.action == "approve":
                sod = profile.content_json["separation_of_duties"]
                if (
                    sod["preparer_cannot_approve"]
                    and self.actor_id == row.prepared_by
                    or sod["last_material_editor_cannot_approve"]
                    and self.actor_id == row.updated_by
                ):
                    self._error(403, "FORECAST_APPROVAL_SOD")
                row.approved_by, row.approved_at, row.status = self.actor_id, utc_now(), "APPROVED"
            elif payload.action == "review":
                row.reviewed_by, row.reviewed_at, row.status = self.actor_id, utc_now(), "UNDER_REVIEW"
            else:
                row.status = "REJECTED"
            row.reason = payload.reason
            return self._record(
                row,
                {"review": "FORECAST_SUBMITTED", "approve": "FORECAST_APPROVED", "reject": "FORECAST_REJECTED"}[
                    payload.action
                ],
                payload.reason,
                changed=True,
            )

        return self._write("version.transition", workspace, payload, key, apply, identity, expected)
