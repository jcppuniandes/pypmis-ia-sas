"""QRA Foundation authority: source evidence, approved methodology and model definitions.

Canonical workspace, scope, ETag and audit primitives are reused. Evaluators and
receipts belong exclusively here. All upstream adapters are read-only.
"""

import json
from copy import deepcopy
from datetime import date
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import Integer, cast, func, select, true
from sqlalchemy.dialects.postgresql import JSONB, array
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import defer

from app.api.v1.routers.admin_configuration import _workspace_path
from app.core.time import utc_now
from app.domain.models import (
    AdminConfiguration,
    AdminNumberSequence,
    PermissionCatalog,
    SecurityAccessAssignment,
    SecurityEvent,
    SecurityGroupMember,
    SecurityRole,
    SecurityRolePermission,
    Tenant,
)
from app.modules.basic_data.service import BasicDataService, _hash, _json
from app.modules.owner_capability.service import OwnerCapabilityService
from app.modules.qra_foundation.adapters import SourceAdapters
from app.modules.qra_foundation.models import (
    CostSourceReadinessAssessment,
    QraCommand,
    QraModelDefinition,
    ScheduleSourceReadinessAssessment,
)
from app.modules.qra_foundation.policy import (
    ANALYSIS_TYPES,
    CORRELATION_METHODS,
    DEFAULT_CONFIGURATION,
    DISTRIBUTIONS,
    QUALITY_VALUES,
    RANGE_TYPES,
    configuration_issues,
    correlation_issues,
    input_issues,
    matches,
    numeric,
    references_valid,
    tailored_requirements,
)
from app.modules.qra_foundation.schemas import ModelCreateIn, SourceCreateIn

CONFIGURATION_KIND = "qra_methodology_configuration"
MODELS = {
    "cost": CostSourceReadinessAssessment,
    "schedule": ScheduleSourceReadinessAssessment,
    "model": QraModelDefinition,
}
PROVIDER_KEYS = {"cost": "COST_SOURCE_READINESS_PROVIDER", "schedule": "SCHEDULE_SOURCE_READINESS_PROVIDER"}


class QraFoundationService(BasicDataService):
    def __init__(self, db, tenant_id, actor_id, context=None):
        super().__init__(db, tenant_id, actor_id, context)
        self.adapters = SourceAdapters(db, tenant_id)

    def ensure_seed(self):
        self.db.scalar(select(Tenant).where(Tenant.id == self.tenant_id).with_for_update())
        row = self.db.scalar(
            select(AdminConfiguration)
            .where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == CONFIGURATION_KIND,
                AdminConfiguration.code == "default",
            )
            .order_by(AdminConfiguration.revision.desc())
        )
        if row is None:
            row = AdminConfiguration(
                tenant_id=self.tenant_id,
                kind=CONFIGURATION_KIND,
                code="default",
                name="QRA Methodology & Source Readiness",
                description="Neutral DRAFT. No live source, model or simulation evidence.",
                status="draft",
                revision=1,
                version=1,
                content_json=deepcopy(DEFAULT_CONFIGURATION),
                content_hash=_hash(DEFAULT_CONFIGURATION),
                created_by_user_id=self.actor_id,
            )
            self.db.add(row)
            self.db.flush()
            self._event("qra.config.seeded", "AdminConfiguration", row.id, {"independent_publication": True})
        for kind in MODELS:
            if not self.db.scalar(
                select(AdminNumberSequence.id).where(
                    AdminNumberSequence.tenant_id == self.tenant_id,
                    AdminNumberSequence.rule_code == f"qra_{kind}",
                    AdminNumberSequence.scope_key == "tenant",
                )
            ):
                self.db.add(
                    AdminNumberSequence(
                        tenant_id=self.tenant_id, rule_code=f"qra_{kind}", scope_key="tenant", next_value=1, version=1
                    )
                )
        self.db.commit()
        return row

    def options(self, **kwargs):
        result = super().options(**kwargs)
        result.update(
            analysis_types=list(ANALYSIS_TYPES),
            quality_values=list(QUALITY_VALUES),
            confidence_values=["PRELIMINARY", "MODERATE", "HIGH"],
            range_types=list(RANGE_TYPES),
            distribution_families=list(DISTRIBUTIONS),
            correlation_methods=list(CORRELATION_METHODS),
            allowed_actions=self._allowed_actions(),
            no_simulation=True,
        )
        return result

    def _effective(self, project, context):
        path = _workspace_path(self.db, self.tenant_id, project)
        ranks = {w.id: i + 1 for i, w in enumerate(path)}
        candidates = []
        today = utc_now().date().isoformat()
        for row in self.db.scalars(
            select(AdminConfiguration).where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == CONFIGURATION_KIND,
                AdminConfiguration.status == "published",
            )
        ):
            content = row.content_json
            scope = content.get("scope", {}).get("workspace_id")
            if scope is not None and scope not in ranks:
                continue
            if scope is not None and scope != project.id and not content.get("inherit_to_descendants", True):
                continue
            if (
                not matches(content.get("applicability", {}), context)
                or (content.get("effective_from") or today) > today
                or (content.get("effective_to") or today) < today
            ):
                continue
            candidates.append((ranks.get(scope, 0), row.revision, row.id, row))
        candidates.sort(key=lambda x: x[:3])
        chain = [
            {
                "id": r.id,
                "revision": r.revision,
                "version": r.version,
                "hash": r.content_hash,
                "scope": r.content_json.get("scope"),
            }
            for _, _, _, r in candidates
        ]
        row = candidates[-1][3] if candidates else None
        return row, deepcopy(row.content_json if row else DEFAULT_CONFIGURATION), chain

    @staticmethod
    def _config_ref(row, chain):
        return {
            "id": row.id if row else None,
            "revision": row.revision if row else None,
            "version": row.version if row else None,
            "hash": row.content_hash if row else None,
            "resolution_chain": chain,
            "publisher_id": QraFoundationService._publisher_id(row) if row else None,
        }

    @staticmethod
    def _publisher_id(row):
        # Actual publisher is resolved from the audit below, not inferred author.
        return None

    def requirements(self, project_id):
        project = self._project(project_id)
        context = super()._context(project)
        row, policy, chain = self._effective(project, context)
        config = self._config_ref(row, chain)
        if row:
            event = self.db.scalar(
                select(SecurityEvent)
                .where(
                    SecurityEvent.tenant_id == self.tenant_id,
                    SecurityEvent.target_type == "AdminConfiguration",
                    SecurityEvent.target_id == row.id,
                    SecurityEvent.event_type == "qra.config.published",
                )
                .order_by(SecurityEvent.id.desc())
                .limit(1)
            )
            config["publisher_id"] = event.user_id if event else None
        return {
            "project_id": project_id,
            "configuration": config,
            "policy": policy,
            "context": context,
            "cost_requirements": tailored_requirements(policy, "cost", context) if row else [],
            "schedule_requirements": tailored_requirements(policy, "schedule", context) if row else [],
            "applicable": bool(row),
            "persisted": False,
        }

    def contexts(self, project_id):
        project = self._project(project_id)
        owner_service = OwnerCapabilityService(self.db, self.tenant_id, self.actor_id, self.context)
        sources = owner_service.contexts(project_id)
        sources["owner_capability"] = owner_service.provider_evidence(project_id)
        sources["basic_data"] = BasicDataService(
            self.db, self.tenant_id, self.actor_id, self.context
        ).provider_evidence(project_id)
        cost_sources = self.adapters.cost_sources(project)
        sources["fin"] = {
            "status": "AVAILABLE"
            if any(s["kind"] == "FIN_CAPEX" and s["source_current"] for s in cost_sources)
            else "NOT_AVAILABLE",
            "sources": [{k: v for k, v in s.items() if k != "items"} for s in cost_sources if s["kind"] == "FIN_CAPEX"],
            "source_current": any(s["kind"] == "FIN_CAPEX" and s["source_current"] for s in cost_sources),
        }
        sources["budget"] = {
            "status": "AVAILABLE"
            if any(s["kind"] == "PORTFOLIO_BUDGET" and s["source_current"] for s in cost_sources)
            else "NOT_AVAILABLE",
            "sources": [
                {k: v for k, v in s.items() if k != "items"} for s in cost_sources if s["kind"] == "PORTFOLIO_BUDGET"
            ],
        }
        return _json(sources)

    def source_options(self, project_id, kind, *, page=1, page_size=100):
        project = self._project(project_id)
        if kind == "schedule":
            return self.adapters.schedule_options(project, page=page, page_size=page_size)
        return self.adapters.cost_options(project, page=page, page_size=page_size)

    def _row(self, kind, record_id, *, lock=False):
        model = MODELS[kind]
        query = select(model).where(model.tenant_id == self.tenant_id, model.id == record_id)
        row = self.db.scalar(query.with_for_update().execution_options(populate_existing=True) if lock else query)
        if row is None:
            self._error(404, "QRA_RECORD_NOT_FOUND")
        self._project(row.project_workspace_id)
        return row

    def records(self, project_id, kind, *, page=1, page_size=50):
        self._project(project_id)
        model = MODELS[kind]
        query = select(model).where(model.tenant_id == self.tenant_id, model.project_workspace_id == project_id)
        total = self.db.scalar(select(func.count()).select_from(query.subquery()))
        rows = self._summary_rows(
            query.order_by(model.version.desc()).offset((page - 1) * page_size).limit(page_size), model
        )
        return {
            "items": [self._out(row, kind, summary=True) for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def record(self, kind, record_id, *, summary=False):
        if summary:
            model = MODELS[kind]
            rows = self._summary_rows(
                select(model).where(model.tenant_id == self.tenant_id, model.id == record_id), model
            )
            if not rows:
                self._error(404, "QRA_RECORD_NOT_FOUND")
            self._project(rows[0].project_workspace_id)
            return self._out(rows[0], kind, summary=True)
        return self._out(self._row(kind, record_id), kind, summary=summary)

    def _summary_rows(self, query, model):
        """Project JSON inside the database; never decode a full input snapshot."""
        dialect = self.db.get_bind().dialect.name
        if dialect == "postgresql":
            aggregate = cast(model.aggregate_json, JSONB)
            for key in ("inputs", "items", "gaps"):
                aggregate = aggregate.op("-")(key)
            aggregate = aggregate.op("#-")(array(["basis", "items"]))
        else:
            aggregate = func.json_remove(
                model.aggregate_json, "$.inputs", "$.items", "$.gaps", "$.basis.items"
            )
        keys = ("readiness_status", "coverage", "blockers", "as_of", "no_simulation")
        statement = query.options(defer(model.aggregate_json), defer(model.snapshot_json)).add_columns(
            aggregate, *(model.snapshot_json[key] for key in keys)
        )
        results = []
        for row, projected, *snapshot in self.db.execute(statement):
            projected = json.loads(projected) if isinstance(projected, str) else projected
            proxy = SimpleNamespace(**{key: value for key, value in vars(row).items() if key != "_sa_instance_state"})
            proxy.aggregate_json = projected or {}
            proxy.snapshot_json = dict(zip(keys, snapshot, strict=True))
            results.append(proxy)
        return results

    def record_items(self, kind, record_id, *, page=1, page_size=25):
        model = MODELS[kind]
        row = self.db.scalar(
            select(model)
            .where(model.tenant_id == self.tenant_id, model.id == record_id)
            .options(defer(model.aggregate_json), defer(model.snapshot_json))
        )
        if row is None:
            self._error(404, "QRA_RECORD_NOT_FOUND")
        self._project(row.project_workspace_id)
        array = model.aggregate_json["inputs"] if kind == "model" else model.snapshot_json["population"]
        dialect = self.db.get_bind().dialect.name
        if dialect == "postgresql":
            elements = (
                func.jsonb_array_elements(cast(array, JSONB))
                .table_valued("value", with_ordinality="ordinal")
                .render_derived()
            )
            total_expression = func.jsonb_array_length(cast(array, JSONB))
            order = elements.c.ordinal
        else:
            elements = func.json_each(array).table_valued("key", "value")
            total_expression = func.json_array_length(array)
            order = cast(elements.c.key, Integer)
        total = (
            self.db.scalar(select(total_expression).where(model.tenant_id == self.tenant_id, model.id == record_id))
            or 0
        )
        values = (
            self.db.scalars(
                select(elements.c.value)
                .select_from(model.__table__.join(elements, true()))
                .where(model.tenant_id == self.tenant_id, model.id == record_id)
                .order_by(order)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
            if total
            else []
        )
        items = [json.loads(value) if isinstance(value, str) else value for value in values]
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "hash": row.hash,
            "historical": row.status in {"COMPLETED", "APPROVED_FOR_ANALYSIS"},
        }

    def _out(self, row, kind, *, summary=False):
        result = _json(
            {
                k: getattr(row, k)
                for k in (
                    "id",
                    "number",
                    "version",
                    "predecessor_id",
                    "title",
                    "comments",
                    "status",
                    "hash",
                    "created_by",
                    "submitted_by",
                    "reviewed_by",
                    "approved_by",
                    "created_at",
                    "updated_at",
                    "submitted_at",
                    "reviewed_at",
                    "completed_at",
                    "revision_version",
                )
            }
        )
        if not summary:
            result.update(aggregate_json=_json(row.aggregate_json), snapshot_json=_json(row.snapshot_json))
        result.update(
            project_id=row.project_workspace_id,
            kind=kind,
            configuration={
                "id": row.configuration_id,
                "revision": row.configuration_revision,
                "hash": row.configuration_hash,
            },
        )
        actions = self._allowed_actions(row.project_workspace_id)
        allowed = []
        if row.status == "DRAFT":
            for action in ("edit", "submit"):
                if f"{kind}_{action}" in actions:
                    allowed.append(action)
        if row.status == "IN_REVIEW":
            policy = self.db.get(AdminConfiguration, row.configuration_id).content_json
            preparers = set(row.aggregate_json.get("preparers", [])) | {row.created_by, row.submitted_by}
            independent = self.actor_id not in preparers
            flag = "preparer_cannot_approve" if kind == "model" else "preparer_cannot_complete"
            if independent or not policy.get("separation_of_duties", {}).get(flag, True):
                if f"{kind}_review" in actions:
                    allowed.append("review")
                    if kind != "model" and row.reviewed_by:
                        allowed.append("complete")
                if kind == "model" and row.reviewed_by and "model_approve" in actions:
                    allowed.append("approve")
        if row.status in {"COMPLETED", "APPROVED_FOR_ANALYSIS"} and f"{kind}_create" in actions:
            allowed.append("refresh_apply")
        result["allowed_actions"] = allowed
        if kind == "model":
            result.update(
                analysis_type=row.analysis_type,
                model_number=row.model_number,
                cost_source_assessment_id=row.cost_source_assessment_id,
                schedule_source_assessment_id=row.schedule_source_assessment_id,
            )
        if summary:
            result["aggregate_json"] = {
                k: v for k, v in row.aggregate_json.items() if k not in {"inputs", "items", "gaps", "preparers"}
            }
            if "basis" in result["aggregate_json"]:
                result["aggregate_json"]["basis"] = {
                    k: v for k, v in result["aggregate_json"]["basis"].items() if k != "items"
                }
            result["snapshot_json"] = {
                k: row.snapshot_json.get(k)
                for k in ("readiness_status", "coverage", "blockers", "as_of", "no_simulation")
            }
        return result

    def _number(self, kind, policy):
        row = self.db.scalar(
            select(AdminNumberSequence)
            .where(
                AdminNumberSequence.tenant_id == self.tenant_id,
                AdminNumberSequence.rule_code == f"qra_{kind}",
                AdminNumberSequence.scope_key == "tenant",
            )
            .with_for_update()
        )
        if row is None:
            row = AdminNumberSequence(
                tenant_id=self.tenant_id, rule_code=f"qra_{kind}", scope_key="tenant", next_value=1, version=1
            )
            self.db.add(row)
            self.db.flush()
        rule = policy["numbering"]
        number = f"{rule[f'{kind}_prefix']}{rule.get('separator', '-')}{row.next_value:0{rule['padding']}d}"
        row.next_value += 1
        row.version += 1
        return number

    def _new(self, project_id, kind, payload, predecessor=None):
        resolved = self.requirements(project_id)
        if not resolved["applicable"]:
            self._error(409, "QRA_PUBLISHED_APPLICABLE_METHODOLOGY_REQUIRED")
        if kind == "model" and payload.analysis_type not in resolved["policy"]["analysis_types"]:
            self._error(422, "QRA_ANALYSIS_TYPE_NOT_ALLOWED")
        model = MODELS[kind]
        version = (
            self.db.scalar(
                select(func.max(model.version)).where(
                    model.tenant_id == self.tenant_id, model.project_workspace_id == project_id
                )
            )
            or 0
        ) + 1
        content = deepcopy(predecessor.aggregate_json) if predecessor else {}
        content["preparers"] = [self.actor_id]
        row = model(
            tenant_id=self.tenant_id,
            project_workspace_id=project_id,
            number=self._number(kind, resolved["policy"]),
            version=version,
            predecessor_id=predecessor.id if predecessor else None,
            title=payload.title,
            comments=payload.comments,
            status="DRAFT",
            configuration_id=resolved["configuration"]["id"],
            configuration_revision=resolved["configuration"]["revision"],
            configuration_hash=resolved["configuration"]["hash"],
            aggregate_json=content,
            snapshot_json={},
            created_by=self.actor_id,
            revision_version=1,
        )
        if kind == "model":
            row.analysis_type = payload.analysis_type
            row.model_number = predecessor.model_number if predecessor else row.number
            content["analysis_type"] = payload.analysis_type
            row.cost_source_assessment_id = content.get("cost_source_assessment_id")
            row.schedule_source_assessment_id = content.get("schedule_source_assessment_id")
        self.db.add(row)
        self.db.flush()
        row.snapshot_json = self.evaluate(project_id, kind, content, resolved=resolved)
        self._event(
            f"qra.{kind}.created", model.__name__, row.id, {"predecessor_id": row.predecessor_id, "no_simulation": True}
        )
        return self._out(row, kind)

    def create(self, project_id, kind, payload, key):
        self._project(project_id)
        return self._command(
            f"{kind}.create",
            key,
            {"project_id": project_id, "payload": payload.model_dump()},
            lambda: self._new(project_id, kind, payload),
        )

    def _current_config(self, row, resolved):
        if (
            row.configuration_hash != resolved["configuration"]["hash"]
            or row.configuration_id != resolved["configuration"]["id"]
        ):
            self._error(409, "QRA_METHODOLOGY_CHANGED_REFRESH_REQUIRED")

    def update(self, kind, record_id, expected, payload, key):
        self._row(kind, record_id)

        def apply():
            row = self._row(kind, record_id, lock=True)
            self._version(row.revision_version, expected)
            if row.status != "DRAFT":
                self._error(409, "QRA_DRAFT_REQUIRED")
            resolved = self.requirements(row.project_workspace_id)
            self._current_config(row, resolved)
            content = payload.model_dump(mode="json")
            content["preparers"] = sorted(
                set(row.aggregate_json.get("preparers", [])) | {self.actor_id, row.created_by}
            )
            self._validate_aggregate(row.project_workspace_id, kind, content, resolved)
            row.title, row.comments, row.aggregate_json = payload.title, payload.comments, content
            if kind == "model":
                row.analysis_type = payload.analysis_type
                row.cost_source_assessment_id = payload.cost_source_assessment_id
                row.schedule_source_assessment_id = payload.schedule_source_assessment_id
            row.snapshot_json = self.evaluate(row.project_workspace_id, kind, content, resolved=resolved)
            self._touch(row)
            self._event(f"qra.{kind}.updated", MODELS[kind].__name__, row.id, {"no_upstream_mutation": True})
            return self._out(row, kind)

        return self._command(
            f"{kind}.update", key, {"id": record_id, "expected": expected, "payload": payload.model_dump()}, apply
        )

    def patch_model(self, record_id, expected, payload, key, *, inputs=False):
        """Bounded incremental client updates, preserving unedited definitions."""
        self._row("model", record_id)

        def apply():
            row = self._row("model", record_id, lock=True)
            self._version(row.revision_version, expected)
            if row.status != "DRAFT":
                self._error(409, "QRA_DRAFT_REQUIRED")
            resolved = self.requirements(row.project_workspace_id)
            self._current_config(row, resolved)
            content = deepcopy(row.aggregate_json)
            if inputs:
                updates = payload.model_dump(mode="json")["inputs"]
                refs = [(item["source_kind"], item["source_item_ref"]) for item in updates]
                if len(set(refs)) != len(refs):
                    self._error(422, "QRA_DUPLICATE_INPUT_REFERENCE")
                positions = {
                    (item["source_kind"], item["source_item_ref"]): index
                    for index, item in enumerate(content.get("inputs", []))
                }
                content.setdefault("inputs", [])
                for item in updates:
                    ref = item["source_kind"], item["source_item_ref"]
                    if ref in positions:
                        content["inputs"][positions[ref]] = item
                    else:
                        content["inputs"].append(item)
                if len(content["inputs"]) > 20000:
                    self._error(422, "QRA_INPUT_LIMIT_EXCEEDED")
            else:
                content.update(payload.model_dump(mode="json", exclude_unset=True))
            # Also rejects null identity/scope values in a metadata patch.
            from pydantic import ValidationError

            from app.modules.qra_foundation.schemas import ModelUpdateIn

            try:
                typed = ModelUpdateIn.model_validate(
                    {key: value for key, value in content.items() if key != "preparers"}
                )
            except ValidationError as exc:
                raise HTTPException(422, detail={"code": "QRA_MODEL_PATCH_INVALID", "issues": str(exc)}) from exc
            content = typed.model_dump(mode="json")
            content["preparers"] = sorted(
                set(row.aggregate_json.get("preparers", [])) | {self.actor_id, row.created_by}
            )
            self._validate_aggregate(row.project_workspace_id, "model", content, resolved)
            row.title, row.comments, row.aggregate_json = typed.title, typed.comments, content
            row.analysis_type = typed.analysis_type
            row.cost_source_assessment_id = typed.cost_source_assessment_id
            row.schedule_source_assessment_id = typed.schedule_source_assessment_id
            row.snapshot_json = self.evaluate(row.project_workspace_id, "model", content, resolved=resolved)
            self._touch(row)
            self._event(
                "qra.model.inputs_patched" if inputs else "qra.model.metadata_patched",
                "QraModelDefinition",
                row.id,
                {"no_upstream_mutation": True},
            )
            return self._out(row, "model", summary=True)

        return self._command(
            "model.inputs_patch" if inputs else "model.metadata_patch",
            key,
            {"id": record_id, "expected": expected, "payload": payload.model_dump(exclude_unset=True)},
            apply,
        )

    def _validate_aggregate(self, project_id, kind, content, resolved):
        if kind == "model":
            if content["analysis_type"] not in resolved["policy"]["analysis_types"]:
                self._error(422, "QRA_ANALYSIS_TYPE_NOT_ALLOWED")
            for source_kind in ("cost", "schedule"):
                source_id = content.get(f"{source_kind}_source_assessment_id")
                if source_id and self._row(source_kind, source_id).project_workspace_id != project_id:
                    self._error(422, "QRA_SOURCE_PROJECT_MISMATCH")
            refs = [f"{i['source_kind']}:{i['source_item_ref']}" for i in content["inputs"]]
            if len(refs) != len(set(refs)):
                self._error(422, "QRA_DUPLICATE_INPUT_REFERENCE")
            issues = [
                issue
                for item in content["inputs"]
                for issue in input_issues(item, resolved["policy"], resolved["context"])
            ]
            issues += correlation_issues(
                content["correlations"],
                {ref for ref, item in zip(refs, content["inputs"], strict=True) if item["mode"] == "UNCERTAIN"},
                resolved["policy"],
            )
            if issues:
                raise HTTPException(422, detail={"code": "QRA_INPUT_DEFINITION_INVALID", "issues": sorted(set(issues))})
            if (
                content.get("valid_from")
                and content.get("valid_until")
                and content["valid_from"] > content["valid_until"]
            ):
                self._error(422, "QRA_VALIDITY_DATES_REVERSED")
        else:
            for key in ("basis_date",):
                value = content["basis"].get(key)
                if value is not None:
                    try:
                        date.fromisoformat(value)
                    except (TypeError, ValueError):
                        self._error(422, "QRA_COST_BASIS_DATE_INVALID")
            for ref in content["source_refs"]:
                if kind == "schedule" and ref["kind"] != "SCHEDULE_IMPORT":
                    self._error(422, "QRA_SCHEDULE_IMPORT_REFERENCE_REQUIRED")
                if kind == "cost" and ref["kind"] == "SCHEDULE_IMPORT":
                    self._error(422, "QRA_COST_SOURCE_REFERENCE_REQUIRED")
                if ref["kind"] == "EXTERNAL_REFERENCE" and (
                    not str(ref.get("reference") or "").strip()
                    or ref.get("version") is None
                    or not str(ref.get("hash") or "").strip()
                ):
                    self._error(422, "QRA_EXTERNAL_SOURCE_IDENTITY_REQUIRED")
            if kind == "schedule" and len(content["source_refs"]) > 1:
                self._error(422, "QRA_SINGLE_SCHEDULE_SNAPSHOT_REQUIRED")
            if content["evidence_refs"] and not references_valid(content["evidence_refs"]):
                self._error(422, "QRA_EVIDENCE_REFERENCE_REQUIRED")
            for item in content["basis"].get("items", []):
                if (
                    not isinstance(item, dict)
                    or not str(item.get("ref", "")).strip()
                    or not numeric(item.get("amount"))
                ):
                    self._error(422, "QRA_COST_ITEM_IDENTITY_AMOUNT_REQUIRED")
            for gap in content["gaps"]:
                if (
                    not isinstance(gap, dict)
                    or not gap.get("description")
                    or gap.get("status", "OPEN") not in {"OPEN", "IN_PROGRESS", "CLOSED"}
                ):
                    self._error(422, "QRA_GAP_INVALID")
                if gap.get("status") == "CLOSED" and not references_valid(gap.get("closure_evidence")):
                    self._error(422, "QRA_GAP_CLOSURE_EVIDENCE_REQUIRED")

    def preview(self, kind, record_id):
        row = self._row(kind, record_id)
        result = self.evaluate(row.project_workspace_id, kind, row.aggregate_json, completed_at=row.completed_at)
        if row.status in {"COMPLETED", "APPROVED_FOR_ANALYSIS"}:
            result["historical_hash"] = row.hash
        return result

    def action(self, kind, record_id, expected, payload, key, action):
        self._row(kind, record_id)

        def apply():
            row = self._row(kind, record_id, lock=True)
            self._version(row.revision_version, expected)
            if action == "submit" and row.status != "DRAFT" or action != "submit" and row.status != "IN_REVIEW":
                self._error(409, "QRA_LIFECYCLE_TRANSITION_INVALID")
            resolved = self.requirements(row.project_workspace_id)
            self._current_config(row, resolved)
            policy = resolved["policy"]
            preparers = set(row.aggregate_json.get("preparers", [])) | {row.created_by, row.submitted_by}
            sod = policy["separation_of_duties"]
            if (
                action != "submit"
                and sod.get("preparer_cannot_approve" if kind == "model" else "preparer_cannot_complete", True)
                and self.actor_id in preparers
            ):
                self._error(403, "QRA_SEPARATION_OF_DUTIES")
            snapshot = self.evaluate(row.project_workspace_id, kind, row.aggregate_json, resolved=resolved)
            if action == "submit":
                row.status, row.submitted_by, row.submitted_at = "IN_REVIEW", self.actor_id, utc_now()
            elif action == "review":
                if (
                    kind == "model"
                    and sod.get("reviewer_cannot_publish_methodology", False)
                    and self.actor_id == resolved["configuration"].get("publisher_id")
                ):
                    self._error(403, "QRA_METHODOLOGY_PUBLISHER_CANNOT_REVIEW")
                row.reviewed_by, row.reviewed_at = self.actor_id, utc_now()
            else:
                if not row.reviewed_by:
                    self._error(409, "QRA_REVIEW_REQUIRED")
                if kind == "model":
                    if snapshot["readiness_status"] != "READY_FOR_REVIEW":
                        raise HTTPException(
                            409, detail={"code": "QRA_MODEL_NOT_READY", "blockers": snapshot["blockers"]}
                        )
                    if sod.get("decision_maker_cannot_sole_approve", False):
                        decision_makers = (
                            (self._project(row.project_workspace_id).defaults_json or {})
                            .get("_project", {})
                            .get("decision_maker_user_ids", [])
                        )
                        if self.actor_id in decision_makers:
                            self._error(403, "QRA_DECISION_MAKER_CANNOT_SOLE_APPROVE")
                    if sod.get("source_preparer_cannot_approve", False):
                        for source_kind in ("cost", "schedule"):
                            source_id = row.aggregate_json.get(f"{source_kind}_source_assessment_id")
                            if source_id:
                                source = self._row(source_kind, source_id)
                                if self.actor_id in set(source.aggregate_json.get("preparers", [])) | {
                                    source.created_by,
                                    source.submitted_by,
                                }:
                                    self._error(403, "QRA_SOURCE_PREPARER_CANNOT_APPROVE")
                    row.status = "APPROVED_FOR_ANALYSIS"
                    snapshot["readiness_status"] = "APPROVED_FOR_ANALYSIS"
                    snapshot["derived_output"] = "READY_FOR_QRA_ANALYSIS"
                else:
                    row.status = "COMPLETED"
                row.approved_by, row.completed_at = self.actor_id, utc_now()
                snapshot["governance"] = {
                    "prepared_by": row.created_by,
                    "preparers": sorted(p for p in preparers if p is not None),
                    "reviewed_by": row.reviewed_by,
                    "approved_by": row.approved_by,
                }
                row.hash = _hash(
                    {
                        "aggregate": row.aggregate_json,
                        "snapshot": snapshot,
                        "number": row.number,
                        "version": row.version,
                    }
                )
            row.snapshot_json = snapshot
            self._touch(row)
            self._event(
                f"qra.{kind}.{action}",
                MODELS[kind].__name__,
                row.id,
                {
                    "hash": row.hash,
                    "comments": payload.comments,
                    "no_simulation": True,
                    "source_authorities_unchanged": True,
                },
            )
            return self._out(row, kind)

        return self._command(
            f"{kind}.{action}", key, {"id": record_id, "expected": expected, "payload": payload.model_dump()}, apply
        )

    @staticmethod
    def _material(snapshot):
        # Wall clock alone never changes a material fingerprint; expiry does.
        return _hash(
            {
                k: v
                for k, v in snapshot.items()
                if k
                not in {"as_of", "persisted", "historical_hash", "governance", "derived_output", "readiness_status"}
            }
        )

    def _latest(self, project_id, kind):
        model = MODELS[kind]
        return self.db.scalar(
            select(model)
            .where(
                model.tenant_id == self.tenant_id,
                model.project_workspace_id == project_id,
                model.status == ("APPROVED_FOR_ANALYSIS" if kind == "model" else "COMPLETED"),
            )
            .order_by(model.version.desc())
            .limit(1)
        )

    def current_readiness(self, project_id, kind, *, summary=False):
        self._project(project_id)
        row = self._latest(project_id, kind)
        if row is None:
            return {
                "project_id": project_id,
                "status": "NOT_STARTED",
                "readiness_status": "NOT_STARTED",
                "source_current": False,
                "governed": False,
                "warnings": [],
                "blockers": [],
                "no_simulation": True,
            }
        latest = self.evaluate(project_id, kind, row.aggregate_json, completed_at=row.completed_at)
        stale = self._material(row.snapshot_json) != self._material(latest)
        status = "STALE" if stale else row.snapshot_json["readiness_status"]
        result = {
            **deepcopy(row.snapshot_json),
            "project_id": project_id,
            "id": row.id,
            "assessment_id": row.id if kind != "model" else None,
            "model_id": row.id if kind == "model" else None,
            "version": row.version,
            "hash": row.hash,
            "assessment_hash": row.hash if kind != "model" else None,
            "status": status,
            "readiness_status": status,
            "source_current": not stale and latest.get("source_current", False),
            "governed": True,
            "latest_evaluation": latest if stale else None,
        }
        if summary:
            for key in (
                "population",
                "input_refs",
                "excluded_refs",
                "contexts",
                "schedule_summary",
                "requirement_results",
                "latest_evaluation",
            ):
                result.pop(key, None)
        return result

    def refresh_preview(self, kind, record_id):
        row = self._row(kind, record_id)
        latest = self.evaluate(row.project_workspace_id, kind, row.aggregate_json, completed_at=row.completed_at)
        return {
            "persisted": False,
            "record_id": row.id,
            "historical_hash": row.hash,
            "stale": self._material(row.snapshot_json) != self._material(latest),
            "historical_snapshot": deepcopy(row.snapshot_json),
            "current_preview": latest,
            "no_simulation": True,
        }

    def refresh_apply(self, kind, record_id, expected, payload, key):
        self._row(kind, record_id)

        def apply():
            row = self._row(kind, record_id, lock=True)
            self._version(row.revision_version, expected)
            if row.status not in {"COMPLETED", "APPROVED_FOR_ANALYSIS"}:
                self._error(409, "QRA_COMPLETED_HISTORY_REQUIRED")
            data = (
                ModelCreateIn(title=row.title, comments=payload.comments, analysis_type=row.analysis_type)
                if kind == "model"
                else SourceCreateIn(title=row.title, comments=payload.comments)
            )
            return self._new(row.project_workspace_id, kind, data, predecessor=row)

        return self._command(
            f"{kind}.refresh", key, {"id": record_id, "expected": expected, "payload": payload.model_dump()}, apply
        )

    def provider_evidence(self, project_id, kind="cost"):
        if kind not in PROVIDER_KEYS:
            self._error(422, "QRA_SOURCE_PROVIDER_KIND_REQUIRED")
        readiness = self.current_readiness(project_id, kind)
        available = readiness["status"] == "READY" and readiness["source_current"] and readiness["governed"]
        return {
            **readiness,
            "provider_key": PROVIDER_KEYS[kind],
            "source_module": "COST_SOURCE_READINESS" if kind == "cost" else "SCHEDULE_SOURCE_READINESS",
            "evidence_type": "COST_SOURCE_READINESS" if kind == "cost" else "SCHEDULE_SOURCE_READINESS",
            "scope": "EACH_PROJECT",
            "status": "AVAILABLE" if available else "UNAVAILABLE",
            "readiness": readiness["status"],
            "source_current": bool(available),
            "evidence_hash": readiness.get("hash") if available else None,
            "as_of_date": readiness.get("as_of"),
            "quality": readiness.get("quality"),
            "confidence": readiness.get("confidence"),
            "evidence_refs": readiness.get("source_refs", []),
            "no_simulation": True,
        }

    def evaluate(self, project_id, kind, content, *, resolved=None, completed_at=None):
        resolved = resolved or self.requirements(project_id)
        if kind == "model":
            result = self._evaluate_model(project_id, content, resolved)
            maximum_age = resolved["policy"]["freshness"].get("maximum_model_age_days")
            # Age is measured from the immutable approval, never the refreshed
            # projection's as_of timestamp. Calendar-day boundary matches source
            # freshness; the configured maximum remains eligible inclusively.
            if (
                completed_at is not None
                and maximum_age is not None
                and (utc_now().date() - completed_at.date()).days > maximum_age
            ):
                result["blockers"] = sorted(set(result["blockers"]) | {"MODEL_FRESHNESS_EXPIRED"})
                result["readiness_status"] = "BLOCKED" if resolved["applicable"] else "NOT_APPLICABLE"
                result["source_current"] = False
            return result
        return self._evaluate_source(project_id, kind, content, resolved)

    def _evaluate_source(self, project_id, kind, content, resolved):
        project = self._project(project_id)
        policy, context = resolved["policy"], resolved["context"]
        blockers, warnings = [], []
        sources = []
        basis = deepcopy(content.get("basis", {}))
        all_cost = self.adapters.cost_sources(project) if kind == "cost" else []
        for ref in content.get("source_refs", []):
            if kind == "schedule":
                source = self.adapters.schedule(project, ref.get("id"))
            elif ref["kind"] == "EXTERNAL_REFERENCE":
                source = self.adapters.external(ref, basis)
            else:
                source = next((s for s in all_cost if s["kind"] == ref["kind"] and s["id"] == ref.get("id")), None)
            if not source:
                blockers.append("SOURCE_REFERENCE_NOT_FOUND")
                continue
            if ref.get("hash") and ref["hash"] != source["hash"]:
                blockers.append("SOURCE_HASH_CHANGED")
            if ref.get("version") is not None and str(ref["version"]) != str(source.get("version")):
                blockers.append("SOURCE_VERSION_CHANGED")
            if not source.get("source_current"):
                blockers.append("SOURCE_NOT_CURRENT")
            sources.append(source)
            warnings.extend(source.get("warnings", []))
        if not sources:
            blockers.append("SOURCE_IDENTITY_REQUIRED")
        if kind == "schedule" and any(s.get("status") == "rejected" for s in sources):
            blockers.append("SCHEDULE_IMPORT_REJECTED")
        scope = content.get("analysis_scope", {"type": "ENTIRE_PROJECT", "refs": []})
        population = [deepcopy(item) for source in sources for item in source.get("items", [])]
        refs = [str(i.get("ref", "")) for i in population]
        if len(refs) != len(set(refs)) or any(not ref for ref in refs):
            blockers.append("SOURCE_ITEM_IDENTITY_INVALID")
        selected, excluded = population, []
        if scope.get("type") != "ENTIRE_PROJECT":
            selected_refs = set(scope.get("refs", []))
            if not selected_refs:
                blockers.append("EXPLICIT_SCOPE_REFERENCES_REQUIRED")
            if scope.get("type") == "SELECTED_WBS":
                selected = [i for i in population if str(i.get("wbs_code", i.get("wbs_id", ""))) in selected_refs]
                matched = {str(i.get("wbs_code", i.get("wbs_id", ""))) for i in selected}
            else:
                selected = [i for i in population if i["ref"] in selected_refs]
                matched = {i["ref"] for i in selected}
            if selected_refs - matched:
                blockers.append("SCOPE_UNKNOWN_REFERENCE")
            selected_ids = {i["ref"] for i in selected}
            excluded = [i["ref"] for i in population if i["ref"] not in selected_ids]
        if not selected:
            blockers.append("SOURCE_POPULATION_EMPTY")
        derived = {
            "source_identity": bool(sources),
            "scope_coverage": bool(selected),
            "currency": basis.get("currency"),
            "basis_date": basis.get("basis_date"),
            "quality": content.get("quality", "NOT_AVAILABLE"),
            "evidence_refs": content.get("evidence_refs", []),
            "analysis_scope": scope,
        }
        schedule_summary, reconciliation = {}, {"status": "NOT_COMPARABLE"}
        if kind == "schedule" and sources:
            source = sources[0]
            derived.update(
                data_date=source["data_date"],
                calendars=source["calendars"],
                baseline_refs=source["baseline_refs"],
                schedule_type=basis.get("schedule_type"),
            )
            schedule_summary, schedule_blockers = self._schedule_checks(
                source, selected, policy["schedule_quality_rules"]
            )
            blockers.extend(schedule_blockers)
            derived.update(schedule_summary)
        if kind == "cost":
            treatment = basis.get("contingency_basis")
            allowed = policy.get("model_governance", {}).get(
                "allowed_contingency_bases",
                ["BASE_COST", "COST_WITH_ESTIMATE_ALLOWANCE", "COST_WITH_CONTINGENCY", "OTHER_CONFIGURED_BASIS"],
            )
            if treatment not in allowed:
                blockers.append("CONTINGENCY_BASIS_REQUIRED")
            currencies = {str(i.get("currency")) for i in selected if i.get("currency")}
            if (
                not basis.get("currency")
                or any(c != basis["currency"] for c in currencies)
                or any(not i.get("currency") for i in selected)
            ):
                blockers.append("COST_CURRENCY_BASIS_MISMATCH")
            if any(not numeric(i.get("amount")) for i in selected):
                blockers.append("COST_AMOUNT_INVALID")
            reconciliation = self._reconcile(selected, basis, all_cost, policy)
            if (
                reconciliation["status"] == "OUT_OF_TOLERANCE"
                or policy["model_governance"].get("reconciliation_required", False)
                and reconciliation["status"] == "NOT_COMPARABLE"
            ):
                blockers.append("COST_RECONCILIATION_BLOCKED")
            derived.update(
                reconciliation=reconciliation,
                contingency_basis=treatment,
                total_amount=sum(i.get("amount", 0) for i in selected if numeric(i.get("amount")))
                if "COST_CURRENCY_BASIS_MISMATCH" not in blockers
                else None,
            )
        derived.update(basis)
        # Canonical imported fields are authoritative even when user provides an override.
        if kind == "schedule" and sources:
            derived["data_date"] = sources[0]["data_date"]
            derived["calendars"] = sources[0]["calendars"]
        requirements = resolved[f"{kind}_requirements"]
        results, required, covered = [], 0, 0
        for requirement in requirements:
            field = requirement["field"]
            value = derived
            for part in field.split("."):
                value = value.get(part) if isinstance(value, dict) else None
            fulfilled = value is not None and value != "" and value != [] and value != {} and value is not False
            if requirement.get("evidence_required", False):
                fulfilled = fulfilled and references_valid(content.get("evidence_refs"))
            quality = content.get("quality", "NOT_AVAILABLE")
            fulfilled = (
                fulfilled
                and quality in QUALITY_VALUES
                and QUALITY_VALUES.index(quality)
                >= QUALITY_VALUES.index(requirement.get("minimum_quality", "NOT_AVAILABLE"))
            )
            if requirement.get("allowed_values"):
                fulfilled = fulfilled and value in requirement["allowed_values"]
            is_required = requirement.get("required", True)
            required += int(is_required)
            covered += int(is_required and fulfilled)
            results.append(
                {
                    "code": requirement["code"],
                    "dimension": requirement["dimension"],
                    "required": is_required,
                    "fulfilled": bool(fulfilled),
                }
            )
            if is_required and not fulfilled:
                (blockers if requirement.get("blocking", True) else warnings).append(
                    f"SOURCE_REQUIREMENT_UNMET:{requirement['code']}"
                )
        if not requirements:
            blockers.append("SOURCE_REQUIREMENTS_NOT_CONFIGURED")
        for gap in content.get("gaps", []):
            if gap.get("blocking", False) and (
                gap.get("status") != "CLOSED" or not references_valid(gap.get("closure_evidence"))
            ):
                blockers.append("SOURCE_BLOCKING_GAP")
        today = utc_now().date()
        age = policy["freshness"].get("maximum_source_age_days")
        if age is not None:
            for source in sources:
                as_of = source.get("as_of")
                if not as_of or (today - date.fromisoformat(str(as_of)[:10])).days > age:
                    blockers.append("SOURCE_FRESHNESS_EXPIRED")
        coverage = {
            "required": required,
            "covered": covered,
            "percentage": round(100 * covered / required, 4) if required else 0,
            "population": len(population),
            "selected": len(selected),
            "excluded": len(excluded),
        }
        if required and covered < required:
            blockers.append("SOURCE_COVERAGE_INCOMPLETE")
        applicable = resolved["applicable"]
        return _json(
            {
                "persisted": False,
                "project_id": project_id,
                "kind": kind,
                "configuration": resolved["configuration"],
                "context": context,
                "source_refs": [
                    {
                        k: v
                        for k, v in s.items()
                        if k not in {"items", "relationships", "calendars", "existing_validation_findings"}
                    }
                    for s in sources
                ],
                "population": selected,
                "excluded_refs": excluded,
                "analysis_scope": scope,
                "basis": basis,
                "requirement_results": results,
                "dimensions": sorted({r["dimension"] for r in results}),
                "schedule_summary": schedule_summary,
                "reconciliation": reconciliation,
                "quality": content.get("quality", "NOT_AVAILABLE"),
                "confidence": content.get("confidence", "PRELIMINARY"),
                "coverage": coverage,
                "gaps": content.get("gaps", []),
                "blockers": sorted(set(blockers)) if applicable else [],
                "warnings": sorted(set(warnings)),
                "readiness_status": "NOT_APPLICABLE" if not applicable else "BLOCKED" if blockers else "READY",
                "source_current": applicable
                and bool(sources)
                and all(s.get("source_current") for s in sources)
                and "SOURCE_FRESHNESS_EXPIRED" not in blockers,
                "as_of": utc_now().isoformat(),
                "no_simulation": True,
                "no_cpm": True,
                "no_fx_conversion": True,
            }
        )

    @staticmethod
    def _reconcile(items, basis, all_cost, policy):
        reference = basis.get("reconciliation_ref", {})
        comparator = next(
            (s for s in all_cost if s["kind"] == reference.get("kind") and s["id"] == reference.get("id")), None
        )
        if (
            not comparator
            or comparator.get("amount") is None
            or comparator.get("currency") != basis.get("currency")
            or not comparator.get("source_current")
            or any(i.get("currency") != basis.get("currency") for i in items)
        ):
            return {
                "status": "NOT_COMPARABLE",
                "reason": "NO_CURRENT_SAME_CURRENCY_COMPARATOR",
                "no_fx_conversion": True,
            }
        amount = sum(i.get("amount", 0) for i in items if numeric(i.get("amount")))
        delta = abs(amount - comparator["amount"])
        tolerance = (
            policy["model_governance"].get("reconciliation_tolerance_absolute", 0)
            + abs(comparator["amount"]) * policy["model_governance"].get("reconciliation_tolerance_percent", 0) / 100
        )
        return {
            "status": "MATCHED" if delta == 0 else "WITHIN_TOLERANCE" if delta <= tolerance else "OUT_OF_TOLERANCE",
            "source_amount": amount,
            "governed_amount": comparator["amount"],
            "currency": basis["currency"],
            "absolute_difference": delta,
            "tolerance": tolerance,
            "reference": {"kind": comparator["kind"], "id": comparator["id"], "hash": comparator["hash"]},
            "no_fx_conversion": True,
        }

    @staticmethod
    def _schedule_checks(source, items, rules):
        blockers = []
        refs = {i["ref"] for i in items}
        relationships = source["relationships"]
        predecessors, successors = set(), set()
        invalid_relations, negative_lags, excessive_lags = [], [], []
        full_refs = {i["ref"] for i in source["items"]}
        valid_raw_types = {
            "FS",
            "SS",
            "FF",
            "SF",
            "FINISH_TO_START",
            "START_TO_START",
            "FINISH_TO_FINISH",
            "START_TO_FINISH",
            "FINISHTOSTART",
            "STARTTOSTART",
            "FINISHTOFINISH",
            "STARTTOFINISH",
            "PR_FS",
            "PR_SS",
            "PR_FF",
            "PR_SF",
        }
        for raw in source.get("raw_relationships", []):
            raw_type = str(raw.get("relationship_type", "")).upper().replace(" ", "_")
            if (
                raw_type not in valid_raw_types
                or raw.get("predecessor") not in full_refs
                or raw.get("successor") not in full_refs
                or raw.get("predecessor") == raw.get("successor")
            ):
                blockers.append("SCHEDULE_RAW_RELATIONSHIP_INVALID")
            lag_value = raw.get("lag")
            try:
                lag = float(lag_value) if lag_value not in {None, ""} else 0
            except (TypeError, ValueError):
                lag = None
            if lag is None or not numeric(lag):
                blockers.append("SCHEDULE_RAW_LAG_INVALID")
                continue
            if lag != 0 and not raw.get("lag_unit"):
                blockers.append("SCHEDULE_LAG_UNIT_NOT_AVAILABLE")
            if lag < 0:
                negative_lags.append(f"{raw.get('predecessor')}:{raw.get('successor')}")
            threshold = rules.get("maximum_lag_value")
            if threshold is not None and lag != 0:
                if str(raw.get("lag_unit") or "").upper() != str(rules.get("lag_unit") or "").upper():
                    blockers.append("SCHEDULE_LAG_POLICY_UNIT_MISMATCH")
                elif abs(lag) > threshold:
                    excessive_lags.append(f"{raw.get('predecessor')}:{raw.get('successor')}")
            if "maximum_lag_days" in rules and lag != 0:
                # Days threshold applies only to a source explicitly declared DAYS.
                if str(raw.get("lag_unit") or "").upper() != "DAYS":
                    blockers.append("SCHEDULE_LAG_POLICY_UNIT_MISMATCH")
                elif abs(lag) > rules["maximum_lag_days"]:
                    excessive_lags.append(f"{raw.get('predecessor')}:{raw.get('successor')}")
        for r in relationships:
            if r["predecessor"] in refs and r["successor"] in refs:
                predecessors.add(r["successor"])
                successors.add(r["predecessor"])
            if (
                r["type"] not in {"FS", "SS", "FF", "SF"}
                or r["predecessor"] == r["successor"]
                or r["predecessor"] not in full_refs
                or r["successor"] not in full_refs
            ):
                invalid_relations.append(r["id"])
            if not source.get("raw_relationships") and r["lag_days"] != 0:
                blockers.append("SCHEDULE_RAW_LAG_SOURCE_NOT_AVAILABLE")
        allowed_ends = set(rules.get("allowed_open_end_refs", []))
        missing_predecessors = [
            i["ref"] for i in items if i["ref"] not in predecessors and i["ref"] not in allowed_ends
        ]
        missing_successors = [i["ref"] for i in items if i["ref"] not in successors and i["ref"] not in allowed_ends]
        open_ends = sorted(set(missing_predecessors + missing_successors))
        calendar_refs = {str(c.get("source_id")) for c in source["calendars"]}
        missing_calendars = [
            i["ref"] for i in items if not i.get("calendar_ref") or str(i["calendar_ref"]) not in calendar_refs
        ]
        constraints = [
            i["ref"]
            for i in items
            if any(
                str(i.get(key) or "").strip().upper() not in {"", "NONE", "CS_NONE"}
                for key in ("primary_constraint_type", "secondary_constraint_type")
            )
        ]
        missing_duration, implausible_duration, status_findings = [], [], []
        for i in items:
            value = i.get("original_duration")
            try:
                duration = float(value) if value is not None else None
            except (TypeError, ValueError):
                duration = None
            if duration is None or not numeric(duration) or not i.get("duration_unit"):
                missing_duration.append(i["ref"])
            else:
                milestone = i.get("milestone", False)
                if duration < 0 or duration == 0 and not milestone:
                    implausible_duration.append(i["ref"])
                if not milestone and ("minimum_duration" in rules or "maximum_duration" in rules):
                    if (
                        str(i.get("duration_unit") or "").upper()
                        != str(rules.get("duration_threshold_unit") or "").upper()
                    ):
                        blockers.append("SCHEDULE_DURATION_POLICY_UNIT_MISMATCH")
                    elif duration <= rules.get("minimum_duration", 0) or duration > rules.get(
                        "maximum_duration", float("inf")
                    ):
                        implausible_duration.append(i["ref"])
            status = str(i.get("status") or "").upper()
            if (
                not status
                or "COMPLETE" in status
                and "NOT" not in status
                and not i.get("actual_finish")
                or i.get("actual_finish")
                and not i.get("actual_start")
            ):
                status_findings.append(i["ref"])
            if i.get("planned_start") and i.get("planned_finish") and i["planned_start"] > i["planned_finish"]:
                status_findings.append(i["ref"])
        if rules.get("require_data_date", True) and not source["data_date"]:
            blockers.append("SCHEDULE_DATA_DATE_REQUIRED")
        for key, values, limit in (
            ("OPEN_ENDS", open_ends, rules.get("maximum_open_ends", float("inf"))),
            ("CONSTRAINTS", constraints, rules.get("maximum_constraints", float("inf"))),
            ("NEGATIVE_LAGS", negative_lags, rules.get("maximum_negative_lags", float("inf"))),
            ("STATUS_FINDINGS", status_findings, rules.get("maximum_status_findings", float("inf"))),
        ):
            if len(values) > limit:
                blockers.append(f"SCHEDULE_{key}_THRESHOLD_EXCEEDED")
        if invalid_relations:
            blockers.append("SCHEDULE_RELATIONSHIP_INVALID")
        if excessive_lags:
            blockers.append("SCHEDULE_LAG_LIMIT_EXCEEDED")
        if rules.get("require_calendars", True) and missing_calendars:
            blockers.append("SCHEDULE_CALENDARS_MISSING")
        if rules.get("require_durations", True) and missing_duration:
            blockers.append("SCHEDULE_DURATION_SOURCE_MISSING")
        if implausible_duration:
            blockers.append("SCHEDULE_DURATION_IMPLAUSIBLE")
        if rules.get("require_metadata", True) and not source["metadata_available"]:
            blockers.append("SCHEDULE_IMPORTED_METADATA_NOT_AVAILABLE")
        if rules.get("require_baseline_pair", False) and not source["baseline_refs"]:
            blockers.append("SCHEDULE_BASELINE_CONTEXT_MISSING")
        return {
            "activity_count": len(items),
            "relationship_count": len(relationships),
            "missing_predecessors": missing_predecessors,
            "missing_successors": missing_successors,
            "open_ends": open_ends,
            "invalid_relationships": invalid_relations,
            "negative_lags": negative_lags,
            "excessive_lags": excessive_lags,
            "constraints": constraints,
            "missing_calendars": missing_calendars,
            "missing_duration_sources": missing_duration,
            "implausible_durations": implausible_duration,
            "status_findings": sorted(set(status_findings)),
            "calendars": source["calendars"],
            "data_date": source["data_date"],
            "eligible_activity_refs": sorted(refs),
            "milestone_refs": [i["ref"] for i in items if i.get("milestone")],
            "logic_current": source["source_current"],
            "no_cpm": True,
            "duration_units_not_converted": True,
        }, blockers

    def _evaluate_model(self, project_id, content, resolved):
        blockers, warnings, populations, source_refs = [], [], [], []
        policy = resolved["policy"]
        analysis_type = content.get("analysis_type", "COST_QRA")
        if analysis_type not in policy["analysis_types"]:
            blockers.append("ANALYSIS_TYPE_NOT_ALLOWED")
        required_kinds = (
            ["cost"]
            if analysis_type == "COST_QRA"
            else ["schedule"]
            if analysis_type == "SCHEDULE_QRA"
            else ["cost", "schedule"]
        )
        for kind in required_kinds:
            source_id = content.get(f"{kind}_source_assessment_id")
            source = self._row(kind, source_id) if source_id else None
            current = self.current_readiness(project_id, kind) if source else {}
            if (
                not source
                or source.project_workspace_id != project_id
                or source.status != "COMPLETED"
                or current.get("id") != source.id
                or current.get("status") != "READY"
                or not current.get("source_current")
            ):
                blockers.append(f"{kind.upper()}_SOURCE_NOT_ELIGIBLE")
            if source:
                source_refs.append(
                    {
                        "kind": kind,
                        "id": source.id,
                        "version": source.version,
                        "hash": source.hash,
                        "current_hash": current.get("hash"),
                        "readiness": current.get("status"),
                        "source_current": current.get("source_current", False),
                    }
                )
                populations.extend(
                    {"source_kind": kind.upper(), "source_item_ref": item["ref"]}
                    for item in source.snapshot_json.get("population", [])
                )
        refs = [f"{i['source_kind']}:{i['source_item_ref']}" for i in populations]
        required_refs = set(refs)
        definitions = content.get("inputs", [])
        declared = [f"{i['source_kind']}:{i['source_item_ref']}" for i in definitions]
        if len(declared) != len(set(declared)):
            blockers.append("DUPLICATE_INPUT_REFERENCE")
        unknown = set(declared) - required_refs
        missing = required_refs - set(declared)
        if unknown:
            blockers.append("INPUT_UNKNOWN_SOURCE_REFERENCE")
        if missing:
            blockers.append("INPUT_POPULATION_INCOMPLETE")
        if not refs:
            blockers.append("MODEL_INPUT_POPULATION_EMPTY")
        valid = 0
        deterministic = 0
        for item, ref in zip(definitions, declared, strict=True):
            issues = input_issues(item, policy, resolved["context"])
            blockers.extend(issues)
            valid += int(ref in required_refs and not issues)
            deterministic += int(item.get("mode") == "DETERMINISTIC")
        uncertain_refs = {r for r, i in zip(declared, definitions, strict=True) if i.get("mode") == "UNCERTAIN"}
        blockers.extend(
            correlation_issues(content.get("correlations", {"method": "NO_CORRELATION"}), uncertain_refs, policy)
        )
        contexts = self.contexts(project_id)
        required_contexts = policy["model_governance"].get("required_contexts", [])
        for key in required_contexts:
            context = contexts.get(key, {})
            if key == "fel_pdri":
                provider = context.get("fel_provider_context", {})
                eligible = (
                    provider.get("source_current", False)
                    and bool(context.get("definition_assessment"))
                    and provider.get("readiness_status", provider.get("readiness"))
                    in {"READY", "READY_WITH_WARNINGS", "READY_FOR_INVESTMENT_GATE"}
                )
            elif key == "risk_governance":
                eligible = context.get("status") not in {
                    "NOT_AVAILABLE",
                    "UNAVAILABLE",
                    "NOT_APPLICABLE",
                    "NOT_CONFIGURED",
                } and bool(context.get("source"))
            elif key in {"basic_data", "owner_capability"}:
                eligible = context.get("status") == "AVAILABLE" and context.get("source_current")
            elif key == "risk_readiness":
                eligible = context.get("status") in {"READY", "READY_WITH_WARNINGS"} and context.get("source_current")
            else:
                eligible = context.get("status") == "AVAILABLE" and context.get("source_current", True)
            if not eligible:
                blockers.append(f"MODEL_CONTEXT_NOT_CURRENT:{key}")
        today = utc_now().date().isoformat()
        if content.get("valid_from") and content["valid_from"] > today:
            blockers.append("MODEL_NOT_YET_VALID")
        if content.get("valid_until") and content["valid_until"] < today:
            blockers.append("MODEL_VALIDITY_EXPIRED")
        if not content.get("purpose"):
            blockers.append("MODEL_PURPOSE_REQUIRED")
        if not resolved["applicable"]:
            blockers.append("METHODOLOGY_NOT_CURRENT")
        scope = content.get("analysis_scope", {"type": "ENTIRE_PROJECT", "refs": []})
        for kind in required_kinds:
            source_id = content.get(f"{kind}_source_assessment_id")
            if source_id:
                source = self._row(kind, source_id)
                if source.snapshot_json.get("analysis_scope") != scope:
                    blockers.append("MODEL_SCOPE_SOURCE_MISMATCH")
        # Context material strips wall-clock and dynamic preview-only metadata.
        frozen_contexts = {
            key: self._stable_context(value)
            for key, value in contexts.items()
            if key in required_contexts or key == "fel_pdri"
        }
        return _json(
            {
                "persisted": False,
                "project_id": project_id,
                "kind": "model",
                "analysis_type": analysis_type,
                "configuration": resolved["configuration"],
                "methodology_profile": policy["methodology"],
                "analysis_scope": scope,
                "source_refs": source_refs,
                "contexts": frozen_contexts,
                "population": populations,
                "input_refs": declared,
                "range_policy_hash": _hash(policy["range_policies"]),
                "distribution_policy_hash": _hash(policy["distribution_families"]),
                "correlation_policy_hash": _hash(
                    {"methods": policy["correlation_methods"], "rules": policy["correlation_rules"]}
                ),
                "correlation_definition_hash": _hash(content.get("correlations", {})),
                "coverage": {
                    "required": len(refs),
                    "covered": valid,
                    "percentage": round(100 * valid / len(refs), 4) if refs else 0,
                    "uncertain": len(definitions) - deterministic,
                    "deterministic": deterministic,
                    "missing_refs": sorted(missing),
                    "unknown_refs": sorted(unknown),
                },
                "valid_from": content.get("valid_from"),
                "valid_until": content.get("valid_until"),
                "source_current": not any(
                    "NOT_CURRENT" in b or "NOT_ELIGIBLE" in b or "VALIDITY" in b or "NOT_YET_VALID" in b
                    for b in blockers
                ),
                "readiness_status": "NOT_APPLICABLE"
                if not resolved["applicable"]
                else "BLOCKED"
                if blockers
                else "READY_FOR_REVIEW",
                "warnings": warnings,
                "blockers": sorted(set(blockers)),
                "as_of": utc_now().isoformat(),
                "no_simulation": True,
                "simulation_results": None,
                "positive_semidefinite_validation": "NOT_IMPLEMENTED_STRUCTURAL_VALIDATION_ONLY",
            }
        )

    @classmethod
    def _stable_context(cls, value):
        if isinstance(value, dict):
            return {
                k: cls._stable_context(v)
                for k, v in value.items()
                if k
                not in {"as_of", "as_of_date", "persisted", "latest_evaluation", "current_preview", "snapshot_as_of"}
            }
        if isinstance(value, list):
            return [cls._stable_context(v) for v in value]
        return value

    def _configuration(self, configuration_id, *, lock=False):
        query = select(AdminConfiguration).where(
            AdminConfiguration.tenant_id == self.tenant_id,
            AdminConfiguration.kind == CONFIGURATION_KIND,
            AdminConfiguration.id == configuration_id,
        )
        row = self.db.scalar(query.with_for_update().execution_options(populate_existing=True) if lock else query)
        if row is None or not self._config_visible(row):
            self._error(404, "QRA_CONFIGURATION_NOT_FOUND")
        return row

    def _authors(self, row):
        events = self.db.scalars(
            select(SecurityEvent).where(
                SecurityEvent.tenant_id == self.tenant_id,
                SecurityEvent.target_type == "AdminConfiguration",
                SecurityEvent.target_id == row.id,
                SecurityEvent.event_type.in_(["qra.config.seeded", "qra.config.cloned", "qra.config.updated"]),
            )
        ).all()
        return {row.created_by_user_id, *(e.user_id for e in events)}

    def _configuration_out(self, row):
        result = _json(
            {
                k: getattr(row, k)
                for k in (
                    "id",
                    "kind",
                    "code",
                    "name",
                    "description",
                    "status",
                    "revision",
                    "version",
                    "content_json",
                    "content_hash",
                    "created_by_user_id",
                    "published_at",
                    "created_at",
                    "updated_at",
                )
            }
        )
        actions = self._allowed_actions(row.content_json.get("scope", {}).get("workspace_id"))
        result["allowed_actions"] = (
            (["clone"] if "admin_configure" in actions else [])
            + (["edit"] if row.status == "draft" and "admin_configure" in actions else [])
            + (
                ["publish"]
                if row.status == "draft" and "admin_publish" in actions and self.actor_id not in self._authors(row)
                else []
            )
            + (["archive"] if row.status == "published" and "admin_publish" in actions else [])
        )
        return result

    def configurations(self):
        return [
            self._configuration_out(r)
            for r in self.db.scalars(
                select(AdminConfiguration)
                .where(AdminConfiguration.tenant_id == self.tenant_id, AdminConfiguration.kind == CONFIGURATION_KIND)
                .order_by(AdminConfiguration.revision.desc(), AdminConfiguration.id.desc())
            )
            if self._config_visible(r)
        ]

    def configuration(self, configuration_id):
        return self._configuration_out(self._configuration(configuration_id))

    def configuration_history(self, configuration_id):
        row = self._configuration(configuration_id)
        return {"items": [r for r in self.configurations() if r["code"] == row.code], "persisted": False}

    def clone_configuration(self, configuration_id, expected, payload, key):
        self._configuration(configuration_id)

        def apply():
            source = self._configuration(configuration_id, lock=True)
            self._version(source.version, expected)
            content = deepcopy(source.content_json)
            if "target_workspace_id" in payload.model_fields_set:
                target = self._workspace(payload.target_workspace_id) if payload.target_workspace_id else None
                content["scope"] = {
                    "type": target.workspace_type_code if target else "tenant",
                    "workspace_id": target.id if target else None,
                }
            self._assert_config_scope(content)
            code = payload.code or source.code
            revision = (
                self.db.scalar(
                    select(func.max(AdminConfiguration.revision)).where(
                        AdminConfiguration.tenant_id == self.tenant_id,
                        AdminConfiguration.kind == CONFIGURATION_KIND,
                        AdminConfiguration.code == code,
                    )
                )
                or 0
            ) + 1
            row = AdminConfiguration(
                tenant_id=self.tenant_id,
                kind=CONFIGURATION_KIND,
                code=code,
                name=source.name,
                description=source.description,
                status="draft",
                revision=revision,
                version=1,
                content_json=content,
                content_hash=_hash(content),
                created_by_user_id=self.actor_id,
            )
            self.db.add(row)
            self.db.flush()
            self._event(
                "qra.config.cloned",
                "AdminConfiguration",
                row.id,
                {"source_id": source.id, "source_hash": source.content_hash},
            )
            return self._configuration_out(row)

        return self._command(
            "config.clone",
            key,
            {"id": configuration_id, "expected": expected, "payload": payload.model_dump(exclude_unset=True)},
            apply,
        )

    def update_configuration(self, configuration_id, expected, payload, key):
        self._configuration(configuration_id)

        def apply():
            row = self._configuration(configuration_id, lock=True)
            self._version(row.version, expected)
            if row.status != "draft":
                self._error(409, "QRA_PUBLISHED_METHODOLOGY_IMMUTABLE")
            issues = configuration_issues(payload.content_json)
            if issues:
                raise HTTPException(422, detail={"code": "QRA_CONFIGURATION_INVALID", "issues": issues})
            self._assert_config_scope(row.content_json)
            self._assert_config_scope(payload.content_json)
            row.name, row.description = payload.name, payload.description
            row.content_json, row.content_hash = deepcopy(payload.content_json), _hash(payload.content_json)
            row.version += 1
            row.updated_at = utc_now()
            self._event("qra.config.updated", "AdminConfiguration", row.id, {})
            return self._configuration_out(row)

        return self._command(
            "config.update", key, {"id": configuration_id, "expected": expected, "payload": payload.model_dump()}, apply
        )

    def publish_configuration(self, configuration_id, expected, key):
        self._configuration(configuration_id)

        def apply():
            row = self._configuration(configuration_id, lock=True)
            self._version(row.version, expected)
            if row.status != "draft":
                self._error(409, "QRA_DRAFT_METHODOLOGY_REQUIRED")
            self._assert_config_scope(row.content_json)
            issues = configuration_issues(row.content_json)
            if issues:
                raise HTTPException(422, detail={"code": "QRA_CONFIGURATION_INVALID", "issues": issues})
            if self.actor_id in self._authors(row):
                self._error(403, "QRA_CONFIGURATION_SEPARATION_OF_DUTIES")
            row.status, row.published_at = "published", utc_now()
            row.version += 1
            row.updated_at = utc_now()
            self._event(
                "qra.config.published",
                "AdminConfiguration",
                row.id,
                {"hash": row.content_hash, "historical_snapshots_unchanged": True},
            )
            return self._configuration_out(row)

        return self._command("config.publish", key, {"id": configuration_id, "expected": expected}, apply)

    def archive_configuration(self, configuration_id, expected, key):
        self._configuration(configuration_id)

        def apply():
            row = self._configuration(configuration_id, lock=True)
            self._version(row.version, expected)
            self._assert_config_scope(row.content_json)
            if row.status != "published":
                self._error(409, "QRA_PUBLISHED_METHODOLOGY_REQUIRED")
            row.status, row.updated_at = "archived", utc_now()
            row.version += 1
            self._event("qra.config.archived", "AdminConfiguration", row.id, {"historical_snapshots_unchanged": True})
            return self._configuration_out(row)

        return self._command("config.archive", key, {"id": configuration_id, "expected": expected}, apply)

    def configuration_preview(self, payload):
        row = self._configuration(payload.configuration_id) if payload.configuration_id else None
        content = deepcopy(
            payload.content_json
            if payload.content_json is not None
            else row.content_json
            if row
            else DEFAULT_CONFIGURATION
        )
        issues = configuration_issues(content)
        result = {
            "persisted": False,
            "effective_configuration": content,
            "configuration": self._configuration_out(row) if row else None,
            "issues": issues,
            "warnings": ["PREVIEW_ONLY_NOT_PUBLISHED", "NO_SIMULATION"],
            "blockers": issues,
        }
        if not issues:
            self._assert_config_scope(content)
        if payload.project_id and not issues:
            project = self._project(payload.project_id)
            context = super()._context(project)
            scope = content["scope"]["workspace_id"]
            today = utc_now().date().isoformat()
            applicable = (
                (scope is None or scope in {w.id for w in _workspace_path(self.db, self.tenant_id, project)})
                and (scope is None or scope == project.id or content["inherit_to_descendants"])
                and matches(content["applicability"], context)
                and (content.get("effective_from") or today) <= today <= (content.get("effective_to") or today)
            )
            result.update(
                project_id=project.id,
                context=context,
                applicable=applicable,
                cost_requirements=tailored_requirements(content, "cost", context) if applicable else [],
                schedule_requirements=tailored_requirements(content, "schedule", context) if applicable else [],
            )
        return result

    def _allowed_actions(self, project_id=None):
        if self.context is None:
            return []
        if project_id in self._action_cache:
            return self._action_cache[project_id]
        groups = set(
            self.db.scalars(
                select(SecurityGroupMember.group_id).where(
                    SecurityGroupMember.tenant_id == self.tenant_id, SecurityGroupMember.user_id == self.actor_id
                )
            )
        )
        path = (
            {w.id for w in _workspace_path(self.db, self.tenant_id, self._workspace(project_id))}
            if project_id
            else None
        )
        now = utc_now()
        assignments = self.db.scalars(
            select(SecurityAccessAssignment).where(
                SecurityAccessAssignment.tenant_id == self.tenant_id, SecurityAccessAssignment.status == "active"
            )
        )
        roles = {
            a.role_id
            for a in assignments
            if (a.user_id == self.actor_id or a.group_id in groups)
            and (a.starts_at is None or a.starts_at <= now)
            and (a.ends_at is None or a.ends_at > now)
            and (path is None or a.scope_type == "organization" or a.workspace_id in path)
        }
        permissions = set(
            self.db.scalars(
                select(PermissionCatalog.key)
                .join(SecurityRolePermission, SecurityRolePermission.permission_id == PermissionCatalog.id)
                .join(SecurityRole, SecurityRole.id == SecurityRolePermission.role_id)
                .where(
                    SecurityRole.tenant_id == self.tenant_id,
                    SecurityRole.status == "active",
                    SecurityRolePermission.tenant_id == self.tenant_id,
                    SecurityRolePermission.role_id.in_(roles or {-1}),
                    PermissionCatalog.status == "active",
                )
            )
        )
        mapping = {
            "read": "qra_foundation.read",
            "admin_configure": "qra_methodology.admin.configure",
            "admin_publish": "qra_methodology.admin.publish",
        }
        for kind in ("cost", "schedule"):
            mapping.update(
                {f"{kind}_{action}": f"qra_{kind}_source.{action}" for action in ("create", "edit", "submit", "review")}
            )
        mapping.update(
            {f"model_{action}": f"qra_model.{action}" for action in ("create", "edit", "submit", "review", "approve")}
        )
        result = [action for action, permission in mapping.items() if permission in permissions]
        self._action_cache[project_id] = result
        return result

    def _command(self, command, key, request, apply):
        if not key or len(key) > 160:
            self._error(422, "IDEMPOTENCY_KEY_REQUIRED")
        self.db.scalar(select(Tenant).where(Tenant.id == self.tenant_id).with_for_update())
        request_hash = _hash({"actor": self.actor_id, "request": request})
        old = self.db.scalar(
            select(QraCommand).where(QraCommand.tenant_id == self.tenant_id, QraCommand.idempotency_key == key)
        )
        if old:
            if old.command_type != command or old.request_hash != request_hash:
                self._error(409, "IDEMPOTENCY_KEY_REUSED")
            return deepcopy(old.result_json)
        try:
            result = _json(apply())
            self.db.add(
                QraCommand(
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
        except IntegrityError as exc:
            self.db.rollback()
            raise HTTPException(409, detail={"code": "QRA_CONCURRENT_CONFLICT"}) from exc
        except Exception:
            self.db.rollback()
            raise
