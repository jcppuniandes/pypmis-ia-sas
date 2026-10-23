"""Single Cost command authority, downstream of governed Scope and Schedule."""

from copy import deepcopy
from datetime import date
from decimal import Decimal, DecimalException

from fastapi import HTTPException
from sqlalchemy import select

from app.core.time import utc_now
from app.domain.models import AdminConfiguration, SecurityEvent, UserAccount
from app.modules.awp.models import WorkPackage
from app.modules.basic_data.service import _hash
from app.modules.cost_foundation.models import (
    BudgetLine,
    BudgetVersion,
    ControlAccount,
    CostAPU,
    CostBaseline,
    CostCBS,
    CostCode,
    CostHistory,
    CostMapping,
    CostPhasing,
    CostRate,
)
from app.modules.cost_foundation.permissions import ACTIONS
from app.modules.cost_foundation.policy import (
    BUDGET_LIFECYCLE,
    DEFAULT_PROFILE,
    aggregate_money,
    apu_total,
    money,
    spread_cost,
)
from app.modules.cost_foundation.schemas import BudgetLineIn
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.operational_context.models import OperationalContextCommand, ProjectControlsPeriod
from app.modules.schedule_foundation.models import ScheduleVersion
from app.modules.scope_foundation.models import PlanItem, PlanItemScopeLink, ScopeItem
from app.modules.scope_foundation.service import ScopeFoundationService

PROFILE_KIND = "cost_profile"
COLLECTIONS = {
    "cbs": CostCBS,
    "cost_codes": CostCode,
    "control_accounts": ControlAccount,
    "mappings": CostMapping,
    "rates": CostRate,
    "apus": CostAPU,
    "budgets": BudgetVersion,
    "budget_lines": BudgetLine,
    "baselines": CostBaseline,
    "phasing": CostPhasing,
    "history": CostHistory,
}


class CostFoundationService(ScopeFoundationService):
    def _permission(self, action, workspace=None):
        if self.access_context is None:
            return
        if action not in self._permission_contexts:
            self._permission_contexts[action] = require_enterprise_permission(
                self.db, self.tenant_id, self.actor_id, f"cost.{action}", bootstrap=False
            )
        access = self._permission_contexts[action]
        if action.startswith("admin.") and not access.organization_wide:
            self._error(403, "COST_ADMIN_ORGANIZATION_SCOPE_REQUIRED")
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
                event_type=f"cost.{action}",
                outcome=outcome,
                target_type="CostFoundation",
                target_id=target_id,
                metadata_json=deepcopy(metadata),
            )
        )

    def _cost_profile(self, project):
        candidates, now = [], utc_now()
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
        if len({row.code for row in top}) > 1:
            self._error(409, "COST_PROFILE_AMBIGUOUS")
        return max(top, key=lambda r: r.revision)

    def _ready(self, workspace, action):
        project = self._project(workspace)
        self._permission(action, project)
        scope = ScopeFoundationService(self.db, self.tenant_id, self.actor_id, self.access_context)
        scope._ready(workspace, "read")
        if scope._current_baseline(workspace) is None:
            self._error(409, "APPROVED_SCOPE_BASELINE_REQUIRED")
        profile = self._cost_profile(project)
        if profile is None:
            self._error(409, "PUBLISHED_COST_PROFILE_REQUIRED")
        return project, profile

    def _write(self, command, workspace, payload, key, apply, identity=None, expected=None):
        def checked_apply():
            try:
                return apply()
            except (DecimalException, OverflowError):
                self._error(422, "COST_DECIMAL_RANGE_INVALID")

        return self._command(
            f"cost.{command}",
            key,
            {"project": workspace, "id": identity, "expected": expected, **payload.model_dump(mode="json")},
            checked_apply,
        )

    def _record(self, row, event, reason, *, changed=False):
        if changed:
            row.version += 1
            if hasattr(row, "updated_by"):
                row.updated_by, row.updated_at = self.actor_id, utc_now()
        self.db.flush()
        snapshot = self._out(row)
        self.db.add(
            CostHistory(
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

    def _currency(self, value, profile):
        if value not in profile.content_json["currencies"]:
            self._error(422, "COST_CURRENCY_NOT_CONFIGURED")

    def _unit(self, value, profile):
        if value not in profile.content_json["units"]:
            self._error(422, "COST_UNIT_NOT_CONFIGURED")

    def _owner(self, identity):
        if not self.db.scalar(
            select(UserAccount.id).where(UserAccount.id == identity, UserAccount.tenant_id == self.tenant_id)
        ):
            self._error(422, "COST_OWNER_TENANT_MISMATCH")

    def _dimensions(self, workspace, payload):
        for field, model in (("cbs_id", CostCBS), ("cost_code_id", CostCode), ("control_account_id", ControlAccount)):
            if getattr(payload, field, None) is not None:
                row = self._get(model, workspace, getattr(payload, field))
                if row.status != "ACTIVE":
                    self._error(409, "COST_DIMENSION_INACTIVE")

    def save_structure(self, workspace, kind, payload, key, identity=None, expected=None):
        model, action, event = {
            "cbs": (CostCBS, "cbs.edit", "CBS_CREATED"),
            "cost_codes": (CostCode, "code.edit", "COST_CODE_CREATED"),
            "control_accounts": (ControlAccount, "account.edit", "CONTROL_ACCOUNT_CREATED"),
        }[kind]
        self._ready(workspace, action)

        def apply():
            _, profile = self._ready(workspace, action)
            data = payload.model_dump(exclude={"reason"})
            if kind == "cbs":
                parent = self._get(CostCBS, workspace, payload.parent_id) if payload.parent_id else None
                if parent and parent.status != "ACTIVE":
                    self._error(409, "COST_PARENT_CBS_INACTIVE")
                seen = {identity} if identity else set()
                ancestor = parent
                while ancestor:
                    if ancestor.id in seen:
                        self._error(422, "COST_CBS_CYCLE")
                    seen.add(ancestor.id)
                    ancestor = self._get(CostCBS, workspace, ancestor.parent_id) if ancestor.parent_id else None
                data.update(path=f"{parent.path}/" if parent else "", level=parent.level + 1 if parent else 1)
                data["path"] += payload.code
                if identity and any(r.parent_id == identity for r in self._rows(CostCBS, workspace)):
                    old = self._get(CostCBS, workspace, identity)
                    if (old.code, old.parent_id) != (payload.code, payload.parent_id):
                        self._error(409, "COST_CBS_PARENT_WITH_CHILDREN_REQUIRES_SUCCESSOR")
            elif kind == "cost_codes" and payload.category not in profile.content_json["cost_code_categories"]:
                self._error(422, "COST_CATEGORY_NOT_CONFIGURED")
            elif kind == "control_accounts":
                self._owner(payload.owner_user_id)
            if identity:
                row = self._get(model, workspace, identity, lock=True)
                self._version(row.version, expected)
                for field, value in data.items():
                    setattr(row, field, value)
            else:
                row = model(**self._base(workspace), updated_by=self.actor_id, **data)
                self.db.add(row)
            return self._record(
                row,
                event if not identity else event.replace("CREATED", "REVISED"),
                payload.reason,
                changed=bool(identity),
            )

        return self._write(f"{kind}.save", workspace, payload, key, apply, identity, expected)

    def _source(self, workspace, kind, identity=None, schedule_version_id=None, external_id=""):
        if kind in {"SCOPE", "PLAN", "PACKAGE"}:
            if identity is None or schedule_version_id is not None or external_id:
                self._error(422, "COST_SOURCE_IDENTITY_INVALID")
            model = {"SCOPE": ScopeItem, "PLAN": PlanItem, "PACKAGE": WorkPackage}[kind]
            row = self._get(model, workspace, identity)
            if kind == "SCOPE":
                baseline = ScopeFoundationService(
                    self.db, self.tenant_id, self.actor_id, self.access_context
                )._current_baseline(workspace)
                if baseline is None or identity not in {r["id"] for r in baseline.snapshot_json["items"]}:
                    self._error(409, "COST_APPROVED_SCOPE_SOURCE_REQUIRED")
                frozen = deepcopy(next(r for r in baseline.snapshot_json["items"] if r["id"] == identity))
                frozen["cost_source_lineage"] = {
                    "scope_baseline_id": baseline.id,
                    "scope_baseline_hash": baseline.content_hash,
                }
                return frozen
            if kind == "PLAN" and row.status != "PUBLISHED":
                self._error(409, "COST_PUBLISHED_PLAN_REQUIRED")
            return self._out(row)
        if identity is not None or schedule_version_id is None or not external_id:
            self._error(422, "COST_SCHEDULE_SOURCE_IDENTITY_REQUIRED")
        version = self._get(ScheduleVersion, workspace, schedule_version_id)
        if version.status not in {"ACCEPTED_CURRENT", "SUPERSEDED"}:
            self._error(409, "COST_ACCEPTED_SCHEDULE_SOURCE_REQUIRED")
        source = next(
            (
                r
                for r in version.snapshot_json.get("wbs" if kind == "WBS" else "activities", [])
                if str(r["external_id"]) == external_id
            ),
            None,
        )
        if source is None:
            self._error(404, "COST_SCHEDULE_SOURCE_NOT_FOUND")
        return {"schedule_version_id": version.id, "schedule_hash": version.content_hash, "source": deepcopy(source)}

    def map_cost(self, workspace, payload, key, expected=None):
        self._ready(workspace, "mapping.edit")

        def apply():
            _, profile = self._ready(workspace, "mapping.edit")
            self._dimensions(workspace, payload)
            if not any((payload.cbs_id, payload.cost_code_id, payload.control_account_id)):
                self._error(422, "COST_MAPPING_TARGET_REQUIRED")
            source = self._source(
                workspace,
                payload.source_kind,
                payload.source_id,
                payload.schedule_version_id,
                payload.source_external_id,
            )
            if payload.quantity is not None:
                self._unit(payload.unit, profile)
                if payload.source_kind == "SCOPE" and payload.unit != source["unit"]:
                    self._error(422, "COST_SCOPE_UNIT_MISMATCH")
                if payload.source_kind == "SCOPE":
                    quantity = (
                        source["approved_quantity"]
                        if source["approved_quantity"] is not None
                        else source["current_quantity"]
                    )
                    if payload.quantity > Decimal(str(quantity)):
                        self._error(422, "COST_MAPPING_EXCEEDS_APPROVED_SCOPE_QUANTITY")
            if (payload.amount is None) != (payload.currency is None):
                self._error(422, "COST_MAPPING_CURRENCY_REQUIRED")
            if payload.currency:
                self._currency(payload.currency, profile)
            if payload.supersedes_id:
                previous = self._get(CostMapping, workspace, payload.supersedes_id)
                self._version(previous.version, expected)
                if any(r.supersedes_id == previous.id for r in self._rows(CostMapping, workspace)):
                    self._error(409, "COST_MAPPING_ALREADY_SUPERSEDED")
                if (
                    previous.source_kind,
                    previous.source_id,
                    previous.schedule_version_id,
                    previous.source_external_id,
                ) != (payload.source_kind, payload.source_id, payload.schedule_version_id, payload.source_external_id):
                    self._error(422, "COST_MAPPING_SUCCESSOR_SOURCE_CHANGED")
            elif payload.status == "REMOVED":
                self._error(422, "COST_MAPPING_REMOVAL_REQUIRES_PREDECESSOR")
            row = CostMapping(
                **self._base(workspace),
                **payload.model_dump(exclude={"reason"}),
                source_snapshot=source,
                reason=payload.reason,
            )
            self.db.add(row)
            return self._record(row, "COST_MAPPING_CHANGED", payload.reason)

        return self._write("mapping.save", workspace, payload, key, apply, payload.supersedes_id, expected)

    def save_rate(self, workspace, payload, key):
        self._ready(workspace, "rate.edit")

        def apply():
            _, profile = self._ready(workspace, "rate.edit")
            self._currency(payload.currency, profile)
            self._unit(payload.unit, profile)
            if payload.resource_type not in profile.content_json["resource_types"]:
                self._error(422, "COST_RESOURCE_TYPE_DISABLED")
            if payload.effective_to and payload.effective_to <= payload.effective_from:
                self._error(422, "COST_RATE_EFFECTIVE_WINDOW_INVALID")
            previous = self._get(CostRate, workspace, payload.supersedes_id) if payload.supersedes_id else None
            if previous and (previous.status != "PUBLISHED" or previous.code != payload.code):
                self._error(409, "COST_RATE_SUCCESSOR_REQUIRES_PUBLISHED_SAME_CODE")
            revision = (
                max((r.revision for r in self._rows(CostRate, workspace) if r.code == payload.code), default=0) + 1
            )
            if revision > 1 and previous is None:
                self._error(409, "COST_RATE_PREDECESSOR_REQUIRED")
            row = CostRate(
                **self._base(workspace),
                updated_by=self.actor_id,
                revision=revision,
                **payload.model_dump(exclude={"reason"}),
            )
            self.db.add(row)
            return self._record(row, "RATE_CREATED", payload.reason)

        return self._write("rate.create", workspace, payload, key, apply)

    def publish_cost(self, workspace, model, identity, payload, expected, key):
        action = "rate.publish" if model is CostRate else "apu.publish"
        self._ready(workspace, action)

        def apply():
            _, profile = self._ready(workspace, action)
            row = self._get(model, workspace, identity, lock=True)
            self._version(row.version, expected)
            if row.status != "DRAFT":
                self._error(409, "COST_PUBLISHED_SOURCE_IMMUTABLE")
            if profile.content_json["separation_of_duties"]["rate_editor_cannot_publish"] and self.actor_id in {
                row.created_by,
                row.updated_by,
            }:
                self._error(403, "COST_RATE_APU_PUBLICATION_SOD")
            row.status, row.published_by, row.published_at = "PUBLISHED", self.actor_id, utc_now()
            return self._record(
                row, "RATE_PUBLISHED" if model is CostRate else "APU_PUBLISHED", payload.reason, changed=True
            )

        return self._write(action, workspace, payload, key, apply, identity, expected)

    def save_apu(self, workspace, payload, key):
        self._ready(workspace, "apu.edit")

        def apply():
            _, profile = self._ready(workspace, "apu.edit")
            self._unit(payload.unit, profile)
            self._currency(payload.currency, profile)
            if payload.effective_to and payload.effective_to <= payload.effective_from:
                self._error(422, "COST_APU_EFFECTIVE_WINDOW_INVALID")
            components = []
            for component in payload.components:
                if component.category not in profile.content_json["apu_categories"]:
                    self._error(422, "COST_APU_CATEGORY_DISABLED")
                rate = self._get(CostRate, workspace, component.rate_id)
                if rate.status != "PUBLISHED" or rate.currency != payload.currency:
                    self._error(409, "COST_PUBLISHED_SAME_CURRENCY_RATE_REQUIRED")
                if rate.unit != component.unit or rate.resource_type != component.category:
                    self._error(422, "COST_APU_COMPONENT_UNIT_OR_TYPE_MISMATCH")
                if (
                    rate.effective_from > payload.effective_from
                    or rate.effective_to
                    and (not payload.effective_to or payload.effective_to > rate.effective_to)
                ):
                    self._error(422, "COST_APU_RATE_EFFECTIVE_WINDOW_MISMATCH")
                components.append(component.model_dump(mode="json") | {"rate_snapshot": self._out(rate)})
            previous = self._get(CostAPU, workspace, payload.supersedes_id) if payload.supersedes_id else None
            if previous and (previous.status != "PUBLISHED" or previous.code != payload.code):
                self._error(409, "COST_APU_SUCCESSOR_INVALID")
            revision = (
                max((r.revision for r in self._rows(CostAPU, workspace) if r.code == payload.code), default=0) + 1
            )
            if revision > 1 and previous is None:
                self._error(409, "COST_APU_PREDECESSOR_REQUIRED")
            factors = [r.model_dump(mode="json") for r in payload.factors]
            if len({r["name"] for r in factors}) != len(factors):
                self._error(422, "COST_APU_FACTOR_NAME_DUPLICATE")
            data = payload.model_dump(exclude={"reason", "components", "factors"})
            row = CostAPU(
                **self._base(workspace),
                updated_by=self.actor_id,
                revision=revision,
                **data,
                components_json=components,
                factors_json=factors,
                unit_amount=apu_total(components, factors),
                content_hash=_hash(
                    {"components": components, "factors": factors, "definition": payload.model_dump(mode="json")}
                ),
            )
            self.db.add(row)
            return self._record(row, "APU_CREATED", payload.reason)

        return self._write("apu.create", workspace, payload, key, apply)

    def create_budget(self, workspace, payload, key):
        self._ready(workspace, "budget.prepare")

        def apply():
            _, profile = self._ready(workspace, "budget.prepare")
            self._currency(payload.currency, profile)
            if payload.budget_type not in profile.content_json["budget_types"]:
                self._error(422, "COST_BUDGET_TYPE_DISABLED")
            previous = self._get(BudgetVersion, workspace, payload.predecessor_id) if payload.predecessor_id else None
            if previous and previous.status != "APPROVED":
                self._error(409, "COST_APPROVED_BUDGET_PREDECESSOR_REQUIRED")
            if previous and previous.currency != payload.currency:
                self._error(422, "COST_BUDGET_SUCCESSOR_CURRENCY_MISMATCH")
            if payload.budget_type != "ORIGINAL" and previous is None:
                self._error(422, "COST_CURRENT_BUDGET_PREDECESSOR_REQUIRED")
            if payload.budget_type == "ORIGINAL" and any(
                r.status == "APPROVED" for r in self._rows(BudgetVersion, workspace)
            ):
                self._error(409, "COST_ORIGINAL_BUDGET_ALREADY_EXISTS")
            revision = (
                max((r.revision for r in self._rows(BudgetVersion, workspace) if r.code == payload.code), default=0) + 1
            )
            row = BudgetVersion(
                **self._base(workspace),
                updated_by=self.actor_id,
                revision=revision,
                **payload.model_dump(exclude={"reason"}),
                configuration_id=profile.id,
                configuration_hash=profile.content_hash,
            )
            self.db.add(row)
            return self._record(row, "BUDGET_VERSION_CREATED", payload.reason)

        return self._write("budget.create", workspace, payload, key, apply)

    def _draft_budget(self, workspace, identity, expected):
        row = self._get(BudgetVersion, workspace, identity, lock=True)
        self._version(row.version, expected)
        if row.status != "DRAFT":
            self._error(409, "COST_BUDGET_NOT_DRAFT")
        return row

    def _budget_profile(self, budget):
        row = self._profile(budget.configuration_id)
        if row.status != "published" or row.content_hash != budget.configuration_hash:
            self._error(409, "COST_BUDGET_PINNED_CONFIGURATION_INVALID")
        return row

    def add_line(self, workspace, identity, payload, expected, key, line_identity=None, *, unwrapped=False):
        self._ready(workspace, "budget.prepare")

        def apply():
            _, profile = self._ready(workspace, "budget.prepare")
            budget = self._draft_budget(workspace, identity, expected)
            profile = self._budget_profile(budget)
            self._dimensions(workspace, payload)
            self._unit(payload.unit, profile)
            self._currency(payload.currency, profile)
            if budget.currency != payload.currency:
                self._error(422, "COST_BUDGET_CURRENCY_MISMATCH_NO_SILENT_FX")
            sources = deepcopy(payload.source_json)
            if payload.scope_item_id:
                source = self._source(workspace, "SCOPE", payload.scope_item_id)
                approved_quantity = (
                    source["approved_quantity"]
                    if source["approved_quantity"] is not None
                    else source["current_quantity"]
                )
                if source["unit"] != payload.unit or payload.quantity > Decimal(str(approved_quantity)):
                    self._error(422, "COST_SCOPE_QUANTITY_OR_UNIT_MISMATCH")
                sources["scope"] = source
            if payload.plan_item_id:
                sources["plan"] = self._source(workspace, "PLAN", payload.plan_item_id)
                if payload.scope_item_id and not self.db.scalar(
                    select(PlanItemScopeLink.id).where(
                        PlanItemScopeLink.tenant_id == self.tenant_id,
                        PlanItemScopeLink.project_workspace_id == workspace,
                        PlanItemScopeLink.plan_item_id == payload.plan_item_id,
                        PlanItemScopeLink.scope_item_id == payload.scope_item_id,
                    )
                ):
                    self._error(422, "COST_SCOPE_PLAN_LINEAGE_MISMATCH")
            if payload.work_package_id:
                sources["package"] = self._source(workspace, "PACKAGE", payload.work_package_id)
            if payload.apu_id:
                apu = self._get(CostAPU, workspace, payload.apu_id)
                if apu.status != "PUBLISHED" or (apu.unit, apu.currency, apu.unit_amount) != (
                    payload.unit,
                    payload.currency,
                    payload.rate,
                ):
                    self._error(422, "COST_APU_BUDGET_BASIS_MISMATCH")
                try:
                    pricing_date = date.fromisoformat(budget.source_references["pricing_date"])
                except (KeyError, TypeError, ValueError):
                    self._error(422, "COST_BUDGET_PRICING_DATE_REQUIRED")
                if pricing_date < apu.effective_from or apu.effective_to and pricing_date >= apu.effective_to:
                    self._error(422, "COST_APU_NOT_EFFECTIVE_ON_PRICING_DATE")
                sources["apu"] = self._out(apu)
            if payload.cost_class == "MANAGEMENT_RESERVE":
                self._permission("reserve.manage", self._project(workspace))
            fields = {
                **payload.model_dump(exclude={"reason", "source_json"}),
                "amount": money(payload.quantity * payload.rate),
                "source_json": sources,
            }
            if line_identity:
                row = self._get(BudgetLine, workspace, line_identity, lock=True)
                if row.budget_version_id != identity:
                    self._error(422, "COST_BUDGET_LINE_PARENT_MISMATCH")
                if row.cost_class == "MANAGEMENT_RESERVE":
                    self._permission("reserve.manage", self._project(workspace))
                for field, value in fields.items():
                    setattr(row, field, value)
            else:
                row = BudgetLine(**self._base(workspace), budget_version_id=identity, **fields)
                self.db.add(row)
            line = self._record(
                row,
                "BUDGET_LINE_REVISED" if line_identity else "BUDGET_LINE_CREATED",
                payload.reason,
                changed=bool(line_identity),
            )
            receipt = self._record(budget, "BUDGET_VERSION_REVISED", payload.reason, changed=True)
            return {**line, "budget_version": receipt, "candidate_only": True}

        if unwrapped:
            return apply()
        return self._write(
            f"budget.line.{line_identity or 'create'}", workspace, payload, key, apply, identity, expected
        )

    def candidate_from_scope(self, workspace, identity, payload, expected, key):
        self._ready(workspace, "budget.prepare")

        def apply():
            scope = self._source(workspace, "SCOPE", payload.scope_item_id)
            apu = self._get(CostAPU, workspace, payload.apu_id)
            quantity = Decimal(
                str(scope["approved_quantity"] if scope["approved_quantity"] is not None else scope["current_quantity"])
            )
            command = BudgetLineIn(
                **payload.model_dump(exclude={"apu_id", "line_code"}),
                line_code=payload.line_code,
                description=scope["name"],
                apu_id=apu.id,
                quantity=quantity,
                unit=scope["unit"],
                rate=apu.unit_amount,
                currency=apu.currency,
                source_json={"calculation": "APPROVED_SCOPE_QUANTITY_X_PUBLISHED_APU", "candidate_only": True},
            )
            return self.add_line(workspace, identity, command, expected, key, unwrapped=True)

        return self._write("budget.candidate_from_scope", workspace, payload, key, apply, identity, expected)

    def budget_calculation(self, workspace, identity):
        self._permission("read", self._project(workspace))
        row = self._get(BudgetVersion, workspace, identity)
        lines = [r for r in self._rows(BudgetLine, workspace) if r.budget_version_id == identity]
        baseline_lines = [r for r in lines if r.cost_class != "MANAGEMENT_RESERVE"]
        reserve = [r for r in lines if r.cost_class == "MANAGEMENT_RESERVE"]
        return {
            "budget_id": row.id,
            "status": row.status,
            "total": aggregate_money([self._out(r) for r in lines]),
            "control_baseline_total": aggregate_money([self._out(r) for r in baseline_lines], row.currency),
            "management_reserve": aggregate_money([self._out(r) for r in reserve], row.currency),
            "reserve_inside_baseline": False,
            "candidate_only": row.status != "APPROVED",
        }

    def transition_budget(self, workspace, identity, payload, expected, key):
        action = {
            "SUBMITTED": "budget.submit",
            "UNDER_REVIEW": "budget.review",
            "APPROVED": "budget.approve",
            "REJECTED": "budget.review",
        }[payload.status]
        self._ready(workspace, action)

        def apply():
            _, profile = self._ready(workspace, action)
            row = self._get(BudgetVersion, workspace, identity, lock=True)
            self._version(row.version, expected)
            if payload.status not in BUDGET_LIFECYCLE.get(row.status, set()):
                self._error(409, "COST_BUDGET_TRANSITION_INVALID")
            lines = [self._out(r) for r in self._rows(BudgetLine, workspace) if r.budget_version_id == identity]
            if not lines:
                self._error(422, "COST_BUDGET_LINES_REQUIRED")
            if payload.status == "APPROVED":
                if (
                    self.actor_id in {row.created_by, row.updated_by}
                    and profile.content_json["separation_of_duties"]["budget_preparer_cannot_approve"]
                ):
                    self._error(403, "COST_BUDGET_APPROVAL_SOD")
                if row.reviewed_by is None:
                    self._error(409, "COST_BUDGET_REVIEW_REQUIRED")
                approved = [r for r in self._rows(BudgetVersion, workspace) if r.status == "APPROVED"]
                if row.predecessor_id and any(r.predecessor_id == row.predecessor_id for r in approved):
                    self._error(409, "COST_CURRENT_BUDGET_BRANCH_CONFLICT")
                if not row.predecessor_id and approved:
                    self._error(409, "COST_ORIGINAL_BUDGET_ALREADY_APPROVED")
                calculation = self.budget_calculation(workspace, identity)
                row.approved_by, row.approved_at = self.actor_id, utc_now()
                row.snapshot_json = {
                    "lines": lines,
                    "configuration_id": row.configuration_id,
                    "configuration_hash": row.configuration_hash,
                    "source_references": deepcopy(row.source_references),
                    "calculation": {**calculation, "status": "APPROVED", "candidate_only": False},
                }
                row.content_hash = _hash(row.snapshot_json)
            if payload.status == "UNDER_REVIEW":
                row.reviewed_by = self.actor_id
            # updated_by tracks material preparer, not reviewers/approvers.
            row.status, row.version = payload.status, row.version + 1
            return self._record(row, f"BUDGET_{payload.status}", payload.reason)

        return self._write("budget.transition", workspace, payload, key, apply, identity, expected)

    def successor_budget(self, workspace, identity, payload, expected, key):
        self._ready(workspace, "budget.prepare")

        def apply():
            _, profile = self._ready(workspace, "budget.prepare")
            previous = self._get(BudgetVersion, workspace, identity, lock=True)
            self._version(previous.version, expected)
            if previous.status != "APPROVED":
                self._error(409, "COST_APPROVED_BUDGET_SUCCESSOR_REQUIRED")
            row = BudgetVersion(
                **self._base(workspace),
                updated_by=self.actor_id,
                revision=max(r.revision for r in self._rows(BudgetVersion, workspace) if r.code == previous.code) + 1,
                code=previous.code,
                name=previous.name,
                budget_type="CURRENT",
                currency=previous.currency,
                predecessor_id=previous.id,
                configuration_id=profile.id,
                configuration_hash=profile.content_hash,
                source_references={
                    **deepcopy(previous.source_references),
                    "approved_predecessor_id": previous.id,
                    "hash": previous.content_hash,
                },
            )
            self.db.add(row)
            self.db.flush()
            for source in self._rows(BudgetLine, workspace):
                if source.budget_version_id == previous.id:
                    fields = {
                        column.key: deepcopy(getattr(source, column.key))
                        for column in source.__table__.columns
                        if column.key
                        not in {
                            "id",
                            "tenant_id",
                            "project_workspace_id",
                            "version",
                            "created_by",
                            "created_at",
                            "budget_version_id",
                        }
                    }
                    self.db.add(BudgetLine(**self._base(workspace), budget_version_id=row.id, **fields))
            return self._record(row, "BUDGET_VERSION_CREATED", payload.reason)

        return self._write("budget.successor", workspace, payload, key, apply, identity, expected)

    def create_baseline(self, workspace, payload, key):
        self._ready(workspace, "baseline.prepare")

        def apply():
            _, profile = self._ready(workspace, "baseline.prepare")
            budget = self._get(BudgetVersion, workspace, payload.budget_version_id)
            if budget.status != "APPROVED":
                self._error(409, "COST_BASELINE_REQUIRES_APPROVED_BUDGET")
            previous = (
                self._get(CostBaseline, workspace, payload.previous_baseline_id)
                if payload.previous_baseline_id
                else None
            )
            if previous and previous.status != "APPROVED":
                self._error(409, "COST_APPROVED_BASELINE_PREDECESSOR_REQUIRED")
            snapshot = {
                "budget": self._out(budget),
                "lines": [r for r in budget.snapshot_json["lines"] if r["cost_class"] != "MANAGEMENT_RESERVE"],
                "control_structures": {
                    k: [self._out(r) for r in self._rows(m, workspace)]
                    for k, m in (("cbs", CostCBS), ("cost_codes", CostCode), ("accounts", ControlAccount))
                },
                "source_mappings": [self._out(r) for r in self._effective_mappings(workspace)],
                "phasing": [],
                "management_reserve": {"inside_control_baseline": False, "authority": "OWNER_ONLY_PROJECT_LEVEL"},
            }
            row = CostBaseline(
                **self._base(workspace),
                updated_by=self.actor_id,
                revision=max(
                    (r.revision for r in self._rows(CostBaseline, workspace) if r.code == payload.code), default=0
                )
                + 1,
                configuration_id=profile.id,
                **payload.model_dump(exclude={"reason"}),
                snapshot_json=snapshot,
                content_hash=_hash(snapshot),
            )
            self.db.add(row)
            return self._record(row, "COST_BASELINE_CANDIDATE_CREATED", payload.reason)

        return self._write("baseline.create", workspace, payload, key, apply)

    def phase_baseline(self, workspace, identity, payload, expected, key):
        self._ready(workspace, "phasing.edit")

        def apply():
            _, profile = self._ready(workspace, "phasing.edit")
            baseline = self._get(CostBaseline, workspace, identity, lock=True)
            self._version(baseline.version, expected)
            if baseline.status != "CANDIDATE":
                self._error(409, "COST_APPROVED_BASELINE_IMMUTABLE")
            if payload.method not in profile.content_json["phasing_methods"]:
                self._error(422, "COST_PHASING_METHOD_DISABLED")
            line = self._get(BudgetLine, workspace, payload.budget_line_id)
            if line.budget_version_id != baseline.budget_version_id or line.cost_class == "MANAGEMENT_RESERVE":
                self._error(422, "COST_BASELINE_LINE_INVALID")
            start, finish = payload.start_date, payload.finish_date
            basis = {"authority": "COST_EXPLICIT_MANUAL_DATES", "method": payload.method}
            if payload.schedule_version_id:
                source = self._source(
                    workspace,
                    "ACTIVITY",
                    schedule_version_id=payload.schedule_version_id,
                    external_id=payload.source_external_id,
                )
                activity = source["source"]
                source_start = (
                    activity.get("current_start")
                    or activity.get("planned_start")
                    or activity.get("start")
                    or activity.get("baseline_start")
                )
                source_finish = (
                    activity.get("current_finish")
                    or activity.get("planned_finish")
                    or activity.get("finish")
                    or activity.get("baseline_finish")
                )
                if not source_start or not source_finish:
                    self._error(422, "COST_ACTIVITY_DATES_REQUIRED")
                authoritative_start, authoritative_finish = (
                    date.fromisoformat(source_start[:10]),
                    date.fromisoformat(source_finish[:10]),
                )
                if start and start != authoritative_start or finish and finish != authoritative_finish:
                    self._error(422, "COST_SCHEDULE_DATE_OVERRIDE_FORBIDDEN")
                start, finish = authoritative_start, authoritative_finish
                basis = {"authority": "SCHEDULE_IMMUTABLE_SOURCE", **source}
            elif payload.method == "ACTIVITY_BASED":
                self._error(422, "COST_ACTIVITY_BASED_SOURCE_REQUIRED")
            if start is None or finish is None:
                self._error(422, "COST_PHASING_DATES_REQUIRED")
            if payload.period_id:
                period = self._get(ProjectControlsPeriod, workspace, payload.period_id)
                if period.status not in {"OPEN", "REVIEW"}:
                    self._error(409, "COST_HISTORICAL_PERIOD_IMMUTABLE")
                basis["period"] = self._out(period)
            try:
                spread = spread_cost(
                    line.amount,
                    start,
                    finish,
                    payload.method,
                    [r.model_dump(mode="json") for r in payload.manual_spread],
                    payload.curve_weights,
                )
            except ValueError as error:
                self._error(422, str(error))
            previous = next(
                (
                    r
                    for r in reversed(self._rows(CostPhasing, workspace))
                    if r.baseline_id == identity and r.budget_line_id == line.id
                ),
                None,
            )
            row = CostPhasing(
                **self._base(workspace),
                baseline_id=identity,
                budget_line_id=line.id,
                method=payload.method,
                revision=previous.revision + 1 if previous else 1,
                period_id=payload.period_id,
                start_date=start,
                finish_date=finish,
                schedule_version_id=payload.schedule_version_id,
                source_external_id=payload.source_external_id,
                basis_json=basis,
                spread_json=spread,
                amount=line.amount,
                currency=line.currency,
                content_hash=_hash({"basis": basis, "spread": spread}),
                supersedes_id=previous.id if previous else None,
                reason=payload.reason,
            )
            self.db.add(row)
            self.db.flush()
            baseline.snapshot_json = {
                **deepcopy(baseline.snapshot_json),
                "phasing": [self._out(r) for r in self._effective_phasing(workspace, identity)],
            }
            baseline.content_hash = _hash(baseline.snapshot_json)
            receipt = self._record(baseline, "COST_BASELINE_PHASED", payload.reason, changed=True)
            return {**self._record(row, "COST_PHASED", payload.reason), "baseline": receipt}

        return self._write("baseline.phase", workspace, payload, key, apply, identity, expected)

    def approve_baseline(self, workspace, identity, payload, expected, key):
        self._ready(workspace, "baseline.approve")

        def apply():
            _, profile = self._ready(workspace, "baseline.approve")
            row = self._get(CostBaseline, workspace, identity, lock=True)
            self._version(row.version, expected)
            if row.status != "CANDIDATE":
                self._error(409, "COST_BASELINE_TRANSITION_INVALID")
            if (
                self.actor_id in {row.created_by, row.updated_by}
                and profile.content_json["separation_of_duties"]["baseline_preparer_cannot_approve"]
            ):
                self._error(403, "COST_BASELINE_APPROVAL_SOD")
            phases = self._effective_phasing(workspace, identity)
            if {r.budget_line_id for r in phases} != {r["id"] for r in row.snapshot_json["lines"]}:
                self._error(409, "COST_BASELINE_COMPLETE_PHASING_REQUIRED")
            for phasing in phases:
                if phasing.period_id and self._get(ProjectControlsPeriod, workspace, phasing.period_id).status not in {
                    "OPEN",
                    "REVIEW",
                }:
                    self._error(409, "COST_BASELINE_PERIOD_CHANGED_REVIEW_REQUIRED")
            if _hash(row.snapshot_json) != row.content_hash:
                self._error(409, "COST_BASELINE_HASH_MISMATCH")
            row.status, row.approved_by, row.approved_at, row.version = (
                "APPROVED",
                self.actor_id,
                utc_now(),
                row.version + 1,
            )
            return self._record(row, "COST_BASELINE_APPROVED", payload.reason)

        return self._write("baseline.approve", workspace, payload, key, apply, identity, expected)

    def _effective_mappings(self, workspace):
        rows = self._rows(CostMapping, workspace)
        replaced = {r.supersedes_id for r in rows if r.supersedes_id}
        return [r for r in rows if r.id not in replaced and r.status == "ACTIVE"]

    def _effective_phasing(self, workspace, baseline):
        rows = [r for r in self._rows(CostPhasing, workspace) if r.baseline_id == baseline]
        replaced = {r.supersedes_id for r in rows if r.supersedes_id}
        return [r for r in rows if r.id not in replaced]

    def history(self, workspace, entity_type, identity):
        self._permission("read", self._project(workspace))
        items = [
            self._out(r)
            for r in self._rows(CostHistory, workspace)
            if r.entity_type == entity_type and r.entity_id == identity
        ]
        return {"items": items, "total": len(items)}

    def overview(self, workspace):
        project = self._project(workspace)
        self._permission("read", project)
        profile = self._cost_profile(project)
        result = {
            "context": self._operational().context(workspace),
            "configuration": self._profile_out(profile) if profile else None,
            "allowed_actions": self.allowed_actions(project),
            "authority": "CANONICAL_COST_WRITE_AUTHORITY",
            "version": 1,
        }
        result.update({key: [self._out(r) for r in self._rows(model, workspace)] for key, model in COLLECTIONS.items()})
        approved = [r for r in result["budgets"] if r["status"] == "APPROVED"]
        successors = {r["predecessor_id"] for r in approved if r["predecessor_id"]}
        for row in result["budgets"]:
            row["effective_status"] = "SUPERSEDED" if row["id"] in successors else row["status"]
        current = [r for r in approved if r["id"] not in successors]
        result["budget_semantics"] = {
            "original_budget": min(approved, key=lambda r: r["id"]) if approved else None,
            "approved_budgets": approved,
            "current_budget": current[0] if len(current) == 1 else None,
            "effective_supersession": "APPROVED_SUCCESSOR_REFERENCE_NOT_MUTATION",
            "original_baseline_immutable": True,
        }
        result.update(
            {
                "scope_items": [self._out(r) for r in self._rows(ScopeItem, workspace)],
                "plan_items": [self._out(r) for r in self._rows(PlanItem, workspace)],
                "packages": [self._out(r) for r in self._rows(WorkPackage, workspace)],
                "schedule_versions": [self._out(r) for r in self._rows(ScheduleVersion, workspace)],
                "periods": [self._out(r) for r in self._rows(ProjectControlsPeriod, workspace)],
                "effective_mappings": [self._out(r) for r in self._effective_mappings(workspace)],
                "accrual_status": "DEFERRED_WITH_CONTRACT",
                "etc_eac_status": "INTERFACE_ONLY_NO_FORECAST_AUTHORITY",
            }
        )
        return result

    def _profile(self, identity, *, lock=False):
        query = select(AdminConfiguration).where(
            AdminConfiguration.tenant_id == self.tenant_id,
            AdminConfiguration.kind == PROFILE_KIND,
            AdminConfiguration.id == identity,
        )
        row = self.db.scalar(query.with_for_update().execution_options(populate_existing=True) if lock else query)
        if row is None:
            self._error(404, "COST_PROFILE_NOT_FOUND")
        return row

    def profiles(self):
        self._permission("admin.configure")
        return {
            "items": [
                self._profile_out(r)
                for r in self.db.scalars(
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
            if (
                set(content) != set(DEFAULT_PROFILE)
                or content["budget_approval_workflow"] != DEFAULT_PROFILE["budget_approval_workflow"]
            ):
                raise ValueError("keys/workflow")
            for key in (
                "cost_code_categories",
                "apu_categories",
                "resource_types",
                "units",
                "currencies",
                "budget_types",
                "baseline_types",
                "phasing_methods",
                "commitment_inclusion_modes",
                "actual_source_types",
                "etc_methods",
            ):
                values = content[key]
                if (
                    not isinstance(values, list)
                    or not values
                    or len(values) != len(set(values))
                    or any(not isinstance(v, str) or not v.strip() for v in values)
                ):
                    raise ValueError(key)
            if (
                content["fx_policy"] != DEFAULT_PROFILE["fx_policy"]
                or content["reserve_rules"] != DEFAULT_PROFILE["reserve_rules"]
                or content["contingency_rules"] != DEFAULT_PROFILE["contingency_rules"]
                or content["accrual_policy"] != "DEFERRED_WITH_CONTRACT"
            ):
                raise ValueError("financial authority policy cannot be bypassed")
            if content["control_account_rules"] != DEFAULT_PROFILE["control_account_rules"]:
                raise ValueError("account authority")
            if set(content["separation_of_duties"]) != set(DEFAULT_PROFILE["separation_of_duties"]) or any(
                v is not True for v in content["separation_of_duties"].values()
            ):
                raise ValueError("SoD cannot be bypassed")
            if not set(content["phasing_methods"]) <= set(DEFAULT_PROFILE["phasing_methods"]):
                raise ValueError("phasing")
            scope = content["scope"]
            if scope["type"] == "workspace":
                self._project(scope["workspace_id"])
            elif scope != {"type": "tenant", "workspace_id": None}:
                raise ValueError("scope")
            start, end = self._instant(content["effective_from"]), self._instant(content["effective_to"])
            if start and end and end <= start:
                raise ValueError("window")
        except (KeyError, TypeError, ValueError) as error:
            raise HTTPException(422, detail={"code": "COST_PROFILE_INVALID"}) from error

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
                self._error(409, "COST_PROFILE_CODE_EXISTS")
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
            self._event("COST_PROFILE_CREATED", row.id, {"hash": row.content_hash})
            return self._profile_out(row)

        return self._command("cost.profile.create", key, payload.model_dump(mode="json"), apply)

    def update_profile(self, identity, payload, expected, key):
        self._permission("admin.configure")

        def apply():
            row = self._profile(identity, lock=True)
            self._version(row.version, expected)
            if row.status != "draft":
                self._error(409, "COST_PROFILE_PUBLISHED_IMMUTABLE")
            self._validate_profile(payload.content_json)
            row.name, row.content_json, row.content_hash = (
                payload.name,
                deepcopy(payload.content_json),
                _hash(payload.content_json),
            )
            row.version, row.updated_at = row.version + 1, utc_now()
            self.db.flush()
            return self._profile_out(row)

        return self._command(
            "cost.profile.update", key, {"id": identity, "expected": expected, **payload.model_dump(mode="json")}, apply
        )

    def publish_profile(self, identity, payload, expected, key):
        self._permission("admin.publish")

        def apply():
            row = self._profile(identity, lock=True)
            self._version(row.version, expected)
            if row.status != "draft":
                self._error(409, "COST_PROFILE_PUBLISHED_IMMUTABLE")
            self._validate_profile(row.content_json)
            editor = row.created_by_user_id
            if row.version > 1:
                receipt = self.db.scalar(
                    select(OperationalContextCommand).where(
                        OperationalContextCommand.tenant_id == self.tenant_id,
                        OperationalContextCommand.command_type == "cost.profile.update",
                        OperationalContextCommand.result_json["id"].as_integer() == row.id,
                        OperationalContextCommand.result_json["version"].as_integer() == row.version,
                    )
                )
                if receipt is None:
                    self._error(409, "COST_PROFILE_EDITOR_PROVENANCE_REQUIRED")
                editor = receipt.actor_id
            if self.actor_id in {row.created_by_user_id, editor}:
                self._error(403, "COST_PROFILE_PUBLICATION_SOD")
            row.status, row.published_at, row.version = "published", utc_now(), row.version + 1
            self.db.flush()
            self._event("COST_CONFIGURATION_PUBLISHED", row.id, {"hash": row.content_hash, "reason": payload.reason})
            return self._profile_out(row)

        return self._command(
            "cost.profile.publish",
            key,
            {"id": identity, "expected": expected, **payload.model_dump(mode="json")},
            apply,
        )

    def successor_profile(self, identity, payload, expected, key):
        self._permission("admin.configure")

        def apply():
            previous = self._profile(identity, lock=True)
            self._version(previous.version, expected)
            if previous.status != "published":
                self._error(409, "COST_PUBLISHED_PROFILE_SUCCESSOR_REQUIRED")
            revision = (
                max(
                    r.revision
                    for r in self.db.scalars(
                        select(AdminConfiguration).where(
                            AdminConfiguration.tenant_id == self.tenant_id,
                            AdminConfiguration.kind == PROFILE_KIND,
                            AdminConfiguration.code == previous.code,
                        )
                    )
                )
                + 1
            )
            row = AdminConfiguration(
                tenant_id=self.tenant_id,
                kind=PROFILE_KIND,
                code=previous.code,
                name=previous.name,
                revision=revision,
                version=1,
                status="draft",
                content_json=deepcopy(previous.content_json),
                content_hash=previous.content_hash,
                created_by_user_id=self.actor_id,
            )
            self.db.add(row)
            self.db.flush()
            return self._profile_out(row)

        return self._command(
            "cost.profile.successor",
            key,
            {"id": identity, "expected": expected, **payload.model_dump(mode="json")},
            apply,
        )
