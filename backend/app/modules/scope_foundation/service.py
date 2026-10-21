"""Governed Scope commands over O1A identity, authorization and immutable receipts."""

from copy import deepcopy
from decimal import Decimal
from hashlib import sha256
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select

from app.core.time import utc_now
from app.domain.models import AdminConfiguration, ChangeRequest, SecurityEvent
from app.modules.basic_data.service import _hash, _json
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.operational_context.models import OperationalContextCommand
from app.modules.operational_context.service import OperationalContextService
from app.modules.scope_foundation.models import (
    DerivedModelVersion,
    ExecutionStrategy,
    PlanItem,
    PlanItemModelLink,
    PlanItemScopeLink,
    ScopeBaseline,
    ScopeBimObject,
    ScopeExcelImport,
    ScopeItem,
    ScopeModelMapping,
    ScopeModelVersion,
    ScopeRevision,
)
from app.modules.scope_foundation.permissions import ACTIONS
from app.modules.scope_foundation.schemas import AllocationIn, ItemIn, PlanIn

PROFILE_KIND = "scope_profile"
DEFAULT_PROFILE = {
    "scope": {"type": "tenant", "workspace_id": None},
    "inherit_to_descendants": True,
    "effective_from": None,
    "effective_to": None,
    "scope_natures": ["INSTALL", "REMOVE", "TEMPORARY", "MAINTENANCE"],
    "scope_types": ["DELIVERABLE", "WORK", "SERVICE"],
    "disciplines": ["*"],
    "units": ["m", "m2", "m3", "kg", "t", "ea", "h"],
    "unit_rules": {"conversion": "EXPLICIT_KNOWN_BASIS_ONLY"},
    "excel_templates": {"default": {"required_fields": ["scope_code", "name", "scope_nature", "quantity", "unit"]}},
    "ifc_classification_mapping": {},
    "scope_approval_workflow": ["DRAFT", "SUBMITTED", "REVIEWED", "APPROVED"],
    "segmentation_rule_templates": [
        "AREA",
        "LEVEL",
        "ZONE",
        "SYSTEM",
        "QUANTITY_RANGE",
        "WORKFRONT",
        "PACKAGE",
        "MODEL_SELECTION",
    ],
    "execution_strategy_templates": [],
    "plan_item_rules": {"approved_scope_required": True, "physical_split_enabled": False},
    "quantity_tolerance": "0.000001",
    "separation_of_duties": {
        "author_cannot_publish": True,
        "model_importer_cannot_accept": True,
        "revision_preparer_cannot_approve": True,
        "strategy_author_cannot_publish": True,
        "plan_author_cannot_publish": True,
    },
}


class ScopeFoundationService(OperationalContextService):
    def _permission(self, action, workspace=None):
        if self.access_context is None:
            return
        if action not in self._permission_contexts:
            self._permission_contexts[action] = require_enterprise_permission(
                self.db, self.tenant_id, self.actor_id, f"scope_foundation.{action}", bootstrap=False
            )
        access = self._permission_contexts[action]
        if action.startswith("admin.") and not access.organization_wide:
            self._error(403, "SCOPE_ADMIN_ORGANIZATION_SCOPE_REQUIRED")
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
                event_type=f"scope.{action}",
                outcome=outcome,
                target_type="ScopeFoundation",
                target_id=target_id,
                metadata_json=deepcopy(metadata),
            )
        )

    def _base(self, workspace_id):
        return {
            "tenant_id": self.tenant_id,
            "project_workspace_id": workspace_id,
            "created_by": self.actor_id,
            "version": 1,
        }

    def _rows(self, model, workspace_id):
        return self.db.scalars(
            select(model)
            .where(model.tenant_id == self.tenant_id, model.project_workspace_id == workspace_id)
            .order_by(model.id)
        ).all()

    def _get(self, model, workspace_id, record_id, *, lock=False):
        statement = select(model).where(
            model.tenant_id == self.tenant_id, model.project_workspace_id == workspace_id, model.id == record_id
        )
        row = self.db.scalar(
            statement.with_for_update().execution_options(populate_existing=True) if lock else statement
        )
        if row is None:
            self._error(404, "SCOPE_RECORD_NOT_FOUND")
        return row

    @staticmethod
    def _out(row, exclude=()):
        return _json(
            {
                column.key: getattr(row, column.key)
                for column in row.__table__.columns
                if column.key not in {"source_content", *exclude}
            }
        )

    def _operational(self):
        return OperationalContextService(self.db, self.tenant_id, self.actor_id, self.access_context)

    def _ready(self, workspace_id, action):
        project = self._project(workspace_id)
        self._permission(action, project)
        operational = self._operational()
        operational._operable(workspace_id)
        operational._policy_ready(project, operational._effective_profile(project))
        profile = self._scope_profile(project)
        if profile is None:
            self._error(409, "PUBLISHED_SCOPE_PROFILE_REQUIRED")
        return project, profile

    def _scope_profile(self, project):
        now = utc_now()
        candidates = []
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
            scope = content.get("scope", {})
            target = scope.get("workspace_id")
            if scope.get("type", "tenant") == "tenant":
                depth = 0
            else:
                if project.id not in self._workspace_paths:
                    self._scope(project, self.access_context)
                if target == project.id:
                    depth = 100
                elif content.get("inherit_to_descendants", True) and target in self._workspace_paths[project.id]:
                    depth = 50
                else:
                    continue
            candidates.append((depth, row))
        if not candidates:
            return None
        depth = max(priority for priority, _ in candidates)
        top = [row for priority, row in candidates if priority == depth]
        codes = {row.code for row in top}
        if len(codes) > 1:
            self._error(409, "SCOPE_PROFILE_AMBIGUOUS")
        return max(top, key=lambda row: row.revision)

    def _item_out(self, row):
        result = self._out(row)
        result["model_object_ids"] = list(
            self.db.scalars(select(ScopeModelMapping.model_object_id).where(ScopeModelMapping.scope_item_id == row.id))
        )
        result["excel_import_id"] = row.lineage_json.get("excel", {}).get("import_id")
        result["excel_row_number"] = row.lineage_json.get("excel", {}).get("row_number")
        result["approved_change_id"] = row.lineage_json.get("approved_change_id")
        basis = row.lineage_json.get("measurement_basis")
        result["source_quantity_name"] = basis.get("quantity_name", "") if isinstance(basis, dict) else ""
        return result

    def _object_out(self, row):
        result = self._out(row)
        result["scope_item_ids"] = list(
            self.db.scalars(select(ScopeModelMapping.scope_item_id).where(ScopeModelMapping.model_object_id == row.id))
        )
        result["plan_item_ids"] = list(
            self.db.scalars(select(PlanItemModelLink.plan_item_id).where(PlanItemModelLink.model_object_id == row.id))
        )
        return result

    def _model_out(self, row, *, objects=False):
        result = self._out(row, ("diff_json",)) | {
            "model_id": row.model_code,
            "model_version_id": row.id,
            "diff": deepcopy(row.diff_json),
            "imported_at": row.created_at.isoformat(),
            "imported_by": row.created_by,
            "source_size_bytes": len(row.source_content),
        }
        if objects:
            result["objects_json"] = [
                self._object_out(item)
                for item in self.db.scalars(
                    select(ScopeBimObject).where(
                        ScopeBimObject.tenant_id == self.tenant_id, ScopeBimObject.model_version_id == row.id
                    )
                )
            ]
        return result

    def _plan_out(self, row):
        result = self._out(row)
        result["allocations"] = [
            self._out(link)
            for link in self.db.scalars(select(PlanItemScopeLink).where(PlanItemScopeLink.plan_item_id == row.id))
        ]
        result["model_object_ids"] = list(
            self.db.scalars(select(PlanItemModelLink.model_object_id).where(PlanItemModelLink.plan_item_id == row.id))
        )
        return result

    def overview(self, workspace_id):
        project = self._project(workspace_id)
        self._permission("read", project)
        profile = self._scope_profile(project)
        return {
            "context": self._operational().context(workspace_id),
            "version": 1,
            "allowed_actions": self.allowed_actions(project),
            "configuration": self._profile_out(profile) if profile else None,
            "models": [self._model_out(r, objects=True) for r in self._rows(ScopeModelVersion, workspace_id)],
            "imports": [self._out(r) for r in self._rows(ScopeExcelImport, workspace_id)],
            "items": [self._item_out(r) for r in self._rows(ScopeItem, workspace_id)],
            "revisions": [self._out(r) for r in self._rows(ScopeRevision, workspace_id)],
            "baselines": [self._out(r) for r in self._rows(ScopeBaseline, workspace_id)],
            "strategies": [self._out(r) | {"paths": r.paths_json} for r in self._rows(ExecutionStrategy, workspace_id)],
            "plan_items": [self._plan_out(r) for r in self._rows(PlanItem, workspace_id)],
            "derived_models": [self._out(r) for r in self._rows(DerivedModelVersion, workspace_id)],
        }

    def model_objects(self, workspace_id, model_id):
        self._permission("read", self._project(workspace_id))
        row = self._get(ScopeModelVersion, workspace_id, model_id)
        objects = self._model_out(row, objects=True)["objects_json"]
        return {"items": objects, "total": len(objects)}

    def model_source(self, workspace_id, model_id):
        self._permission("read", self._project(workspace_id))
        return self._get(ScopeModelVersion, workspace_id, model_id)

    def stage_model(self, workspace_id, content, filename, model_code, reason, key):
        from app.modules.scope_foundation.imports import parse_ifc_source

        _, profile = self._ready(workspace_id, "model.import")
        if not model_code.strip() or len(model_code) > 120 or len(content) > 40 * 1024 * 1024:
            self._error(422, "SCOPE_MODEL_INPUT_INVALID")

        def apply():
            self._ready(workspace_id, "model.import")
            previous = self.db.scalar(
                select(ScopeModelVersion)
                .where(
                    ScopeModelVersion.tenant_id == self.tenant_id,
                    ScopeModelVersion.project_workspace_id == workspace_id,
                    ScopeModelVersion.model_code == model_code,
                    ScopeModelVersion.is_current.is_(True),
                )
                .order_by(ScopeModelVersion.id.desc())
            )
            old_objects = self._model_out(previous, objects=True)["objects_json"] if previous else None
            mapped_guids = [
                r.guid
                for r in self._rows(ScopeBimObject, workspace_id)
                if previous
                and r.model_version_id == previous.id
                and r.id
                in set(
                    self.db.scalars(
                        select(ScopeModelMapping.model_object_id).where(
                            ScopeModelMapping.tenant_id == self.tenant_id,
                            ScopeModelMapping.project_workspace_id == workspace_id,
                        )
                    )
                )
            ]
            parsed = parse_ifc_source(
                content, filename, profile.content_json, previous_objects=old_objects, mapped_guids=mapped_guids
            )
            revision = (
                self.db.scalar(
                    select(func.max(ScopeModelVersion.revision)).where(
                        ScopeModelVersion.tenant_id == self.tenant_id,
                        ScopeModelVersion.project_workspace_id == workspace_id,
                        ScopeModelVersion.model_code == model_code,
                    )
                )
                or 0
            ) + 1
            row = ScopeModelVersion(
                **self._base(workspace_id),
                model_code=model_code,
                revision=revision,
                source_file_name=filename[:260],
                source_hash=sha256(content).hexdigest(),
                source_content=content,
                schema=parsed.get("schema", ""),
                units=parsed.get("units", {}),
                status="STAGED",
                supersedes=previous.id if previous else None,
                validation_summary=parsed["validation"],
                diff_json=parsed.get("diff", {}),
                object_count=len(parsed.get("objects", [])),
                reason=reason,
            )
            self.db.add(row)
            self.db.flush()
            seen = set()
            for index, obj in enumerate(parsed.get("objects", [])):
                identity = str(
                    obj.get("source_identity") or obj.get("guid") or f"EXPRESS:{obj.get('express_id', index)}"
                )
                if identity in seen:
                    identity = f"{identity}:DUPLICATE:{index}"
                seen.add(identity)
                fields = {
                    k: deepcopy(obj[k])
                    for k in (
                        "guid",
                        "express_id",
                        "ifc_class",
                        "name",
                        "properties",
                        "quantities",
                        "classification",
                        "discipline",
                        "level",
                        "area",
                        "zone",
                        "system",
                        "materials",
                        "geometry_reference",
                    )
                    if k in obj
                }
                self.db.add(
                    ScopeBimObject(
                        **self._base(workspace_id), model_version_id=row.id, source_identity=identity, **fields
                    )
                )
            self.db.flush()
            self._event(
                "IFC_IMPORTED",
                row.id,
                {
                    "project_workspace_id": workspace_id,
                    "source_hash": row.source_hash,
                    "validation": parsed["validation"],
                    "status": row.status,
                },
            )
            return self._model_out(row, objects=True)

        return self._command(
            "scope.model.import",
            key,
            {
                "project": workspace_id,
                "hash": sha256(content).hexdigest(),
                "filename": filename,
                "model_code": model_code,
                "reason": reason,
            },
            apply,
        )

    def transition_model(self, workspace_id, model_id, action, payload, expected, key):
        duty = "model.accept" if action == "accept" else "model.review"
        self._ready(workspace_id, duty)

        def apply():
            _, profile = self._ready(workspace_id, duty)
            row = self._get(ScopeModelVersion, workspace_id, model_id, lock=True)
            self._version(row.version, expected)
            if row.status in {"ACCEPTED", "REJECTED"}:
                self._error(409, "SCOPE_MODEL_VERSION_TERMINAL")
            if action != "reject" and not row.validation_summary.get(
                "can_accept", not row.validation_summary.get("errors")
            ):
                self._error(409, "SCOPE_MODEL_VALIDATION_ERRORS")
            if action == "review":
                if row.status != "STAGED":
                    self._error(409, "SCOPE_MODEL_TRANSITION_INVALID")
                row.status, row.reviewed_by = "REVIEW", self.actor_id
            elif action == "accept":
                if row.status != "REVIEW":
                    self._error(409, "SCOPE_MODEL_REVIEW_REQUIRED")
                if (
                    profile.content_json.get("separation_of_duties", {}).get("model_importer_cannot_accept", True)
                    and row.created_by == self.actor_id
                ):
                    self._error(403, "SCOPE_MODEL_ACCEPTANCE_SOD")
                current = self.db.scalar(
                    select(ScopeModelVersion).where(
                        ScopeModelVersion.tenant_id == self.tenant_id,
                        ScopeModelVersion.project_workspace_id == workspace_id,
                        ScopeModelVersion.model_code == row.model_code,
                        ScopeModelVersion.is_current.is_(True),
                    )
                )
                if (current.id if current else None) != row.supersedes:
                    self._error(409, "SCOPE_MODEL_CURRENT_CHANGED_REIMPORT_REQUIRED")
                if current:
                    current.is_current = False
                row.status, row.is_current, row.accepted_by, row.accepted_at = (
                    "ACCEPTED",
                    True,
                    self.actor_id,
                    utc_now(),
                )
                self._event(
                    "MODEL_VERSION_ACCEPTED",
                    row.id,
                    {"source_hash": row.source_hash, "project_workspace_id": workspace_id},
                )
            else:
                row.status = "REJECTED"
            row.reason, row.version = payload.reason, row.version + 1
            self.db.flush()
            return self._model_out(row, objects=True)

        return self._command(
            f"scope.model.{action}",
            key,
            {"project": workspace_id, "id": model_id, "expected": expected, **payload.model_dump(mode="json")},
            apply,
        )

    def stage_excel(self, workspace_id, content, filename, mapping, reason, key):
        from app.modules.scope_foundation.imports import parse_excel_source

        _, profile = self._ready(workspace_id, "item.edit")
        if len(content) > 40 * 1024 * 1024:
            self._error(422, "SCOPE_IMPORT_TOO_LARGE")

        def apply():
            self._ready(workspace_id, "item.edit")
            parsed = parse_excel_source(
                content,
                filename,
                profile.content_json,
                field_mapping=mapping,
                existing_scope_codes=[r.scope_code for r in self._rows(ScopeItem, workspace_id)],
            )
            row = ScopeExcelImport(
                **self._base(workspace_id),
                source_file_name=filename[:260],
                source_hash=sha256(content).hexdigest(),
                source_content=content,
                field_mapping=mapping,
                headers=parsed.get("headers", []),
                rows_json=parsed.get("rows", []),
                validation_summary=parsed["validation"],
                reason=reason,
            )
            self.db.add(row)
            self.db.flush()
            self._event("EXCEL_STAGED", row.id, {"project_workspace_id": workspace_id, "source_hash": row.source_hash})
            return self._out(row)

        return self._command(
            "scope.excel.stage",
            key,
            {
                "project": workspace_id,
                "hash": sha256(content).hexdigest(),
                "filename": filename,
                "mapping": mapping,
                "reason": reason,
            },
            apply,
        )

    def excel_candidate(self, workspace_id, import_id, payload, expected, key):
        self._ready(workspace_id, "item.edit")

        def apply():
            _, profile = self._ready(workspace_id, "item.edit")
            row = self._get(ScopeExcelImport, workspace_id, import_id, lock=True)
            self._version(row.version, expected)
            if row.status != "STAGED":
                self._error(409, "SCOPE_EXCEL_ALREADY_CONSUMED")
            if not row.validation_summary.get("can_accept", not row.validation_summary.get("errors")):
                self._error(409, "SCOPE_EXCEL_VALIDATION_ERRORS")
            current_baseline = self._current_baseline(workspace_id)
            created = (
                {item["scope_code"]: item["id"] for item in current_baseline.snapshot_json["items"]}
                if current_baseline
                else {}
            )
            pending, candidate_ids = list(row.rows_json), []
            while pending:
                progressed = False
                for values in pending[:]:
                    parent_code = values.get("parent_scope_code") or ""
                    if parent_code and parent_code not in created:
                        continue
                    fields = {
                        k: v
                        for k, v in values.items()
                        if k in ItemIn.model_fields
                        and k
                        not in {"reason", "model_object_ids", "source_type", "source_reference", "source_revision"}
                    }
                    row_number = values.get("lineage", {}).get(
                        "row_number", values.get("row_number", len(candidate_ids) + 2)
                    )
                    predecessor_id = created.get(values["scope_code"])
                    fields.update(
                        source_type="EXCEL",
                        source_reference=f"excel:{row.id}:row:{row_number}",
                        source_revision=row.source_hash,
                        excel_import_id=row.id,
                        excel_row_number=row_number,
                        predecessor_id=predecessor_id,
                        parent_scope_item_id=created.get(parent_code),
                        reason=payload.reason,
                    )
                    item = self._create_item_record(workspace_id, ItemIn(**fields), profile)
                    created[item.scope_code] = item.id
                    candidate_ids.append(item.id)
                    pending.remove(values)
                    progressed = True
                if not progressed:
                    self._error(422, "SCOPE_EXCEL_PARENT_CYCLE_OR_MISSING")
            row.status, row.candidate_item_ids, row.version = "CANDIDATE", candidate_ids, row.version + 1
            self.db.flush()
            self._event(
                "EXCEL_SCOPE_CANDIDATE_CREATED",
                row.id,
                {"project_workspace_id": workspace_id, "item_ids": list(created.values())},
            )
            return self._out(row)

        return self._command(
            "scope.excel.candidate",
            key,
            {"project": workspace_id, "id": import_id, "expected": expected, **payload.model_dump(mode="json")},
            apply,
        )

    def _objects(self, workspace_id, ids, *, accepted=True):
        if len(set(ids)) != len(ids) or any(not isinstance(i, int) or i < 1 for i in ids):
            self._error(422, "SCOPE_MODEL_OBJECT_REFERENCES_INVALID")
        result = []
        for identity in ids:
            row = self._get(ScopeBimObject, workspace_id, identity)
            version = self._get(ScopeModelVersion, workspace_id, row.model_version_id)
            if accepted and version.status != "ACCEPTED":
                self._error(409, "SCOPE_ACCEPTED_MODEL_VERSION_REQUIRED")
            result.append(row)
        return result

    def _validate_item(self, workspace_id, payload, profile, *, current=None):
        policy = profile.content_json
        if payload.unit not in policy["units"]:
            self._error(422, "SCOPE_UNIT_NOT_GOVERNED")
        if payload.scope_nature not in policy["scope_natures"] or payload.scope_type not in policy["scope_types"]:
            self._error(422, "SCOPE_CLASSIFICATION_NOT_GOVERNED")
        if (
            policy.get("disciplines")
            and "*" not in policy["disciplines"]
            and payload.discipline not in policy["disciplines"]
        ):
            self._error(422, "SCOPE_DISCIPLINE_NOT_GOVERNED")
        parent = payload.parent_scope_item_id
        visited = {current.id} if current else set()
        while parent:
            if parent in visited:
                self._error(422, "SCOPE_HIERARCHY_CYCLE")
            visited.add(parent)
            parent_row = self._get(ScopeItem, workspace_id, parent)
            parent = parent_row.parent_scope_item_id
        objects = self._objects(workspace_id, payload.model_object_ids)
        if payload.source_type == "IFC" and not objects:
            self._error(422, "SCOPE_IFC_OBJECT_LINEAGE_REQUIRED")
        if payload.source_type == "EXCEL":
            if payload.excel_import_id is None or payload.excel_row_number is None:
                self._error(422, "SCOPE_EXCEL_STAGING_LINEAGE_REQUIRED")
            source = self._get(ScopeExcelImport, workspace_id, payload.excel_import_id)
            if source.validation_summary.get("errors"):
                self._error(409, "SCOPE_EXCEL_VALIDATION_ERRORS")
            candidates = [
                r
                for r in source.rows_json
                if r.get("lineage", {}).get("row_number", r.get("row_number")) == payload.excel_row_number
            ]
            if len(candidates) != 1 or candidates[0].get("scope_code") != payload.scope_code:
                self._error(422, "SCOPE_EXCEL_ROW_LINEAGE_INVALID")
            if candidates[0].get("unit") != payload.unit:
                self._error(422, "SCOPE_EXCEL_UNIT_MISMATCH_NO_SILENT_CONVERSION")
        if payload.source_type == "APPROVED_CHANGE":
            binding = self._operational().binding(workspace_id)
            if binding["state"] != "ACTIVE" or payload.approved_change_id is None:
                self._error(409, "SCOPE_APPROVED_CHANGE_SOURCE_REQUIRED")
            change = self.db.scalar(
                select(ChangeRequest).where(
                    ChangeRequest.tenant_id == self.tenant_id,
                    ChangeRequest.project_id == binding["binding"]["legacy_project_id"],
                    ChangeRequest.id == payload.approved_change_id,
                )
            )
            if change is None or str(change.status) != "approved":
                self._error(409, "SCOPE_CHANGE_NOT_APPROVED")
        return objects

    def _create_item_record(self, workspace_id, payload, profile):
        objects = self._validate_item(workspace_id, payload, profile)
        existing = self.db.scalars(
            select(ScopeItem)
            .where(
                ScopeItem.tenant_id == self.tenant_id,
                ScopeItem.project_workspace_id == workspace_id,
                ScopeItem.scope_code == payload.scope_code,
            )
            .order_by(ScopeItem.revision.desc())
        ).first()
        predecessor = self._get(ScopeItem, workspace_id, payload.predecessor_id) if payload.predecessor_id else None
        if existing and (predecessor is None or predecessor.id != existing.id or existing.status != "APPROVED"):
            self._error(409, "SCOPE_CODE_EXISTS_CREATE_APPROVED_SUCCESSOR")
        if predecessor and predecessor.scope_code != payload.scope_code:
            self._error(422, "SCOPE_SUCCESSOR_CODE_MISMATCH")
        fields = payload.model_dump(
            exclude={
                "reason",
                "model_object_ids",
                "excel_import_id",
                "excel_row_number",
                "approved_change_id",
                "predecessor_id",
                "source_quantity_name",
            }
        )
        source_quantity = payload.quantity
        lineage = {
            "source_type": payload.source_type,
            "source_reference": payload.source_reference,
            "source_revision": payload.source_revision,
            "source_quantity": str(payload.quantity),
            "unit": payload.unit,
            "conversion_applied": False,
            "model_objects": [
                {
                    "object_id": r.id,
                    "model_version_id": r.model_version_id,
                    "guid": r.guid,
                    "express_id": r.express_id,
                    "source_hash": self._get(ScopeModelVersion, workspace_id, r.model_version_id).source_hash,
                    "source_quantities": deepcopy(r.quantities),
                }
                for r in objects
            ],
        }
        if payload.source_type == "IFC":
            if payload.measurement_method == "SOURCE_OBJECT_COUNT":
                if payload.unit != "ea":
                    self._error(422, "SCOPE_OBJECT_COUNT_UNIT_MUST_BE_EA")
                source_quantity = Decimal(len(objects))
                lineage["measurement_basis"] = "SOURCE_OBJECT_COUNT"
            else:
                matches = [
                    [
                        q
                        for q in obj.quantities
                        if q.get("unit") == payload.unit
                        and (not payload.source_quantity_name or q.get("name") == payload.source_quantity_name)
                    ]
                    for obj in objects
                ]
                if any(len(values) != 1 for values in matches):
                    self._error(422, "SCOPE_IFC_QUANTITY_BASIS_AMBIGUOUS_OR_UNIT_MISMATCH")
                names = {values[0].get("name") for values in matches}
                if len(names) != 1:
                    self._error(422, "SCOPE_IFC_MEASUREMENT_BASIS_MUST_MATCH")
                source_quantity = sum((Decimal(str(values[0]["value"])) for values in matches), Decimal(0))
                lineage["measurement_basis"] = {"quantity_name": next(iter(names)), "unit": payload.unit}
            fields["source_reference"] = "IFC_OBJECTS:" + ",".join(str(obj.id) for obj in objects)
            fields["source_revision"] = _hash([r["source_hash"] for r in lineage["model_objects"]])
        if payload.source_type == "EXCEL":
            source = self._get(ScopeExcelImport, workspace_id, payload.excel_import_id)
            lineage["excel"] = {
                "import_id": source.id,
                "row_number": payload.excel_row_number,
                "source_hash": source.source_hash,
            }
            staged = next(
                r
                for r in source.rows_json
                if r.get("lineage", {}).get("row_number", r.get("row_number")) == payload.excel_row_number
            )
            source_quantity = Decimal(str(staged["quantity"]))
            lineage["excel"]["original_row"] = deepcopy(staged)
            fields["source_reference"] = f"EXCEL:{source.id}:ROW:{payload.excel_row_number}"
            fields["source_revision"] = source.source_hash
        if payload.source_type == "APPROVED_CHANGE":
            lineage["approved_change_id"] = payload.approved_change_id
        row = ScopeItem(
            **self._base(workspace_id),
            **fields,
            scope_item_key=predecessor.scope_item_key if predecessor else uuid4().hex,
            revision=(predecessor.revision + 1) if predecessor else 1,
            predecessor_id=predecessor.id if predecessor else None,
            source_quantity=source_quantity,
            current_quantity=payload.quantity,
            updated_by=self.actor_id,
            lineage_json=lineage
            | {
                "source_quantity": str(source_quantity),
                "source_reference": fields["source_reference"],
                "source_revision": fields["source_revision"],
            },
        )
        self.db.add(row)
        self.db.flush()
        for obj in objects:
            self.db.add(ScopeModelMapping(**self._base(workspace_id), scope_item_id=row.id, model_object_id=obj.id))
        self.db.flush()
        self._event(
            "SCOPE_ITEM_CREATED",
            row.id,
            {
                "project_workspace_id": workspace_id,
                "scope_code": row.scope_code,
                "scope_nature": row.scope_nature,
                "source_type": row.source_type,
            },
        )
        return row

    def create_item(self, workspace_id, payload, key):
        self._ready(workspace_id, "item.edit")

        def apply():
            _, profile = self._ready(workspace_id, "item.edit")
            return self._item_out(self._create_item_record(workspace_id, payload, profile))

        return self._command(
            "scope.item.create", key, {"project": workspace_id, **payload.model_dump(mode="json")}, apply
        )

    def update_item(self, workspace_id, item_id, payload, expected, key):
        self._ready(workspace_id, "item.edit")

        def apply():
            _, profile = self._ready(workspace_id, "item.edit")
            row = self._get(ScopeItem, workspace_id, item_id, lock=True)
            self._version(row.version, expected)
            if row.status != "DRAFT":
                self._error(409, "APPROVED_SCOPE_ITEM_IMMUTABLE")
            if (
                payload.scope_code != row.scope_code
                or payload.source_type != row.source_type
                or payload.source_reference != row.source_reference
                or payload.source_revision != row.source_revision
            ):
                self._error(422, "SCOPE_SOURCE_LINEAGE_IMMUTABLE")
            if payload.unit != row.unit:
                self._error(422, "SCOPE_UNIT_CHANGE_REQUIRES_EXPLICIT_CONVERSION_BASIS")
            existing_objects = set(self._item_out(row)["model_object_ids"])
            if set(payload.model_object_ids) != existing_objects:
                self._error(422, "SCOPE_SOURCE_MAPPINGS_IMMUTABLE_CREATE_SUCCESSOR")
            self._validate_item(workspace_id, payload, profile, current=row)
            excluded = {
                "reason",
                "model_object_ids",
                "excel_import_id",
                "excel_row_number",
                "approved_change_id",
                "predecessor_id",
                "source_quantity_name",
            }
            for name, value in payload.model_dump(exclude=excluded).items():
                setattr(row, name, value)
            row.current_quantity, row.updated_by, row.updated_at, row.version = (
                payload.quantity,
                self.actor_id,
                utc_now(),
                row.version + 1,
            )
            self.db.flush()
            self._event("SCOPE_ITEM_UPDATED", row.id, {"project_workspace_id": workspace_id, "version": row.version})
            return self._item_out(row)

        return self._command(
            "scope.item.update",
            key,
            {"project": workspace_id, "id": item_id, "expected": expected, **payload.model_dump(mode="json")},
            apply,
        )

    def _current_baseline(self, workspace_id):
        return self.db.scalars(
            select(ScopeBaseline)
            .where(ScopeBaseline.tenant_id == self.tenant_id, ScopeBaseline.project_workspace_id == workspace_id)
            .order_by(ScopeBaseline.revision.desc())
        ).first()

    def create_revision(self, workspace_id, payload, key):
        self._ready(workspace_id, "revision.prepare")

        def apply():
            _, profile = self._ready(workspace_id, "revision.prepare")
            current = self._current_baseline(workspace_id)
            original = deepcopy(current.snapshot_json.get("items", [])) if current else []
            candidate_ids = (
                payload.item_ids
                if payload.item_ids is not None
                else [r.id for r in self._rows(ScopeItem, workspace_id) if r.status == "DRAFT"]
            )
            if (
                len(set(candidate_ids)) != len(candidate_ids)
                or not candidate_ids
                and not payload.removed_scope_item_ids
            ):
                self._error(422, "SCOPE_REVISION_CANDIDATES_REQUIRED")
            candidates = [self._get(ScopeItem, workspace_id, identity) for identity in candidate_ids]
            if any(r.status != "DRAFT" for r in candidates):
                self._error(409, "SCOPE_DRAFT_ITEMS_REQUIRED")
            original_by_code = {item["scope_code"]: item for item in original}
            original_ids = {item["id"] for item in original}
            if set(payload.removed_scope_item_ids) - original_ids:
                self._error(422, "SCOPE_REMOVAL_NOT_IN_CURRENT_APPROVED_SCOPE")
            merged = {item["scope_code"]: item for item in original if item["id"] not in payload.removed_scope_item_ids}
            for item in candidates:
                merged[item.scope_code] = self._item_out(item)
            merged_ids = {item["id"] for item in merged.values()}
            if any(
                item.get("parent_scope_item_id") and item["parent_scope_item_id"] not in merged_ids
                for item in merged.values()
            ):
                self._error(422, "SCOPE_REVISION_PARENT_NOT_INCLUDED")
            added = [r.id for r in candidates if r.scope_code not in original_by_code]
            modified = [r.id for r in candidates if r.scope_code in original_by_code]
            snapshot = {
                "items": list(merged.values()),
                "candidate_ids": candidate_ids,
                "added_items": added,
                "removed_items": payload.removed_scope_item_ids,
                "modified_items": modified,
                "quantity_changes": [
                    {
                        "scope_code": r.scope_code,
                        "before": original_by_code[r.scope_code]["quantity"],
                        "after": str(r.quantity),
                    }
                    for r in candidates
                    if r.scope_code in original_by_code
                    and Decimal(str(original_by_code[r.scope_code]["quantity"])) != r.quantity
                ],
                "classification_changes": [
                    {
                        "scope_code": r.scope_code,
                        "before": original_by_code[r.scope_code]["scope_nature"],
                        "after": r.scope_nature,
                    }
                    for r in candidates
                    if r.scope_code in original_by_code
                    and original_by_code[r.scope_code]["scope_nature"] != r.scope_nature
                ],
                "mapping_impacts": [
                    {"scope_item_id": identity, "requires_future_reconciliation": True}
                    for identity in payload.removed_scope_item_ids + modified
                ],
                "previous_baseline_id": current.id if current else None,
                "sources": [r.lineage_json for r in candidates],
                "configuration_id": profile.id,
                "configuration_hash": profile.content_hash,
            }
            row = ScopeRevision(
                **self._base(workspace_id),
                revision_code=payload.revision_code,
                revision=(current.revision + 1) if current else 1,
                reason=payload.reason,
                snapshot_json=_json(snapshot),
                content_hash=_hash(snapshot),
                configuration_id=profile.id,
            )
            self.db.add(row)
            self.db.flush()
            self._event(
                "SCOPE_REVISION_PREPARED", row.id, {"project_workspace_id": workspace_id, "hash": row.content_hash}
            )
            return self._out(row)

        return self._command(
            "scope.revision.prepare", key, {"project": workspace_id, **payload.model_dump(mode="json")}, apply
        )

    def transition_revision(self, workspace_id, revision_id, action, payload, expected, key):
        self._ready(workspace_id, f"revision.{action}")

        def apply():
            self._ready(workspace_id, f"revision.{action}")
            row = self._get(ScopeRevision, workspace_id, revision_id, lock=True)
            self._version(row.version, expected)
            required, target = {
                "submit": ("DRAFT", "SUBMITTED"),
                "review": ("SUBMITTED", "REVIEWED"),
                "approve": ("REVIEWED", "APPROVED"),
            }[action]
            if row.status != required:
                self._error(409, "SCOPE_REVISION_TRANSITION_INVALID")
            current = self._current_baseline(workspace_id)
            if (current.id if current else None) != row.snapshot_json["previous_baseline_id"]:
                self._error(409, "SCOPE_CURRENT_BASELINE_CHANGED_REPREPARE")
            originals = {item["id"]: item for item in row.snapshot_json["items"]}
            candidates = [
                self._get(ScopeItem, workspace_id, identity, lock=True)
                for identity in row.snapshot_json["candidate_ids"]
            ]
            if any(r.status != "DRAFT" or _hash(self._item_out(r)) != _hash(originals[r.id]) for r in candidates):
                self._error(409, "SCOPE_CANDIDATE_CHANGED_REPREPARE")
            config = self._profile(row.configuration_id)
            if (
                config.content_json.get("separation_of_duties", {}).get("revision_preparer_cannot_approve", True)
                and action == "approve"
                and self.actor_id in {row.created_by, *(r.updated_by for r in candidates)}
            ):
                self._error(403, "SCOPE_BASELINE_APPROVAL_SOD")
            if action == "review":
                row.reviewed_by = self.actor_id
            row.status, row.version = target, row.version + 1
            result = None
            if action == "approve":
                row.approved_by = self.actor_id
                baseline = ScopeBaseline(
                    **self._base(workspace_id),
                    scope_revision_id=row.id,
                    revision=row.revision,
                    previous_baseline_id=current.id if current else None,
                    original_baseline_id=(current.original_baseline_id or current.id) if current else None,
                    snapshot_json=deepcopy(row.snapshot_json),
                    content_hash=row.content_hash,
                    approved_by=self.actor_id,
                )
                self.db.add(baseline)
                self.db.flush()
                for item in candidates:
                    item.status, item.approved_quantity, item.baseline_reference = (
                        "APPROVED",
                        item.quantity,
                        baseline.id,
                    )
                    item.version += 1
                self._event(
                    "SCOPE_BASELINE_APPROVED",
                    baseline.id,
                    {"project_workspace_id": workspace_id, "scope_revision_id": row.id, "hash": row.content_hash},
                )
                result = self._out(baseline)
            self.db.flush()
            if action == "submit":
                self._event("SCOPE_REVISION_SUBMITTED", row.id, {"project_workspace_id": workspace_id})
            return self._out(row) | ({"baseline": result} if result else {})

        return self._command(
            f"scope.revision.{action}",
            key,
            {"project": workspace_id, "id": revision_id, "expected": expected, **payload.model_dump(mode="json")},
            apply,
        )

    def create_strategy(self, workspace_id, payload, key):
        self._ready(workspace_id, "strategy.edit")

        def apply():
            self._ready(workspace_id, "strategy.edit")
            codes = [p.code for p in payload.paths]
            if len(set(codes)) != len(codes) or any(p.mode == "CONDITIONAL" and not p.condition for p in payload.paths):
                self._error(422, "SCOPE_EXECUTION_PATH_INVALID")
            fields = payload.model_dump(mode="json")
            row = ExecutionStrategy(
                **self._base(workspace_id),
                code=payload.code,
                name=payload.name,
                reason=payload.reason,
                paths_json=fields.pop("paths"),
                segmentation_rules=fields.pop("segmentation_rules"),
                settings_json={k: v for k, v in fields.items() if k not in {"code", "name", "reason"}},
                content_hash=_hash(fields),
            )
            self.db.add(row)
            self.db.flush()
            self._event("EXECUTION_STRATEGY_CREATED", row.id, {"project_workspace_id": workspace_id})
            return self._out(row) | {"paths": row.paths_json}

        return self._command(
            "scope.strategy.create", key, {"project": workspace_id, **payload.model_dump(mode="json")}, apply
        )

    def transition_strategy(self, workspace_id, strategy_id, action, payload, expected, key):
        duty = "strategy.publish" if action == "publish" else "strategy.edit"
        self._ready(workspace_id, duty)

        def apply():
            _, profile = self._ready(workspace_id, duty)
            row = self._get(ExecutionStrategy, workspace_id, strategy_id, lock=True)
            self._version(row.version, expected)
            if action == "publish":
                if row.status != "DRAFT":
                    self._error(409, "SCOPE_STRATEGY_PUBLISHED_IMMUTABLE")
                editor = row.created_by
                if row.version > 1:
                    receipt = self.db.scalar(
                        select(OperationalContextCommand).where(
                            OperationalContextCommand.tenant_id == self.tenant_id,
                            OperationalContextCommand.command_type == "scope.strategy.update",
                            OperationalContextCommand.result_json["id"].as_integer() == row.id,
                            OperationalContextCommand.result_json["version"].as_integer() == row.version,
                        )
                    )
                    if receipt is None or receipt.result_json.get("content_hash") != row.content_hash:
                        self._error(409, "SCOPE_STRATEGY_EDITOR_PROVENANCE_REQUIRED")
                    editor = receipt.actor_id
                if profile.content_json["separation_of_duties"].get(
                    "strategy_author_cannot_publish", True
                ) and self.actor_id in {row.created_by, editor}:
                    self._error(403, "SCOPE_STRATEGY_PUBLICATION_SOD")
                row.status, row.published_by, row.version = "PUBLISHED", self.actor_id, row.version + 1
                row.content_hash = _hash(
                    {"paths": row.paths_json, "segmentation": row.segmentation_rules, "settings": row.settings_json}
                )
                self._event(
                    "EXECUTION_STRATEGY_PUBLISHED",
                    row.id,
                    {"project_workspace_id": workspace_id, "hash": row.content_hash},
                )
            else:
                if row.status != "PUBLISHED":
                    self._error(409, "PUBLISHED_SCOPE_STRATEGY_REQUIRED")
                revision = (
                    self.db.scalar(
                        select(func.max(ExecutionStrategy.revision)).where(
                            ExecutionStrategy.tenant_id == self.tenant_id,
                            ExecutionStrategy.project_workspace_id == workspace_id,
                            ExecutionStrategy.code == row.code,
                        )
                    )
                    or 0
                ) + 1
                row = ExecutionStrategy(
                    **self._base(workspace_id),
                    code=row.code,
                    name=row.name,
                    revision=revision,
                    predecessor_id=row.id,
                    reason=payload.reason,
                    paths_json=deepcopy(row.paths_json),
                    segmentation_rules=deepcopy(row.segmentation_rules),
                    settings_json=deepcopy(row.settings_json),
                    content_hash=row.content_hash,
                )
                self.db.add(row)
            self.db.flush()
            return self._out(row) | {"paths": row.paths_json}

        return self._command(
            f"scope.strategy.{action}",
            key,
            {"project": workspace_id, "id": strategy_id, "expected": expected, **payload.model_dump(mode="json")},
            apply,
        )

    def update_strategy(self, workspace_id, strategy_id, payload, expected, key):
        self._ready(workspace_id, "strategy.edit")

        def apply():
            self._ready(workspace_id, "strategy.edit")
            row = self._get(ExecutionStrategy, workspace_id, strategy_id, lock=True)
            self._version(row.version, expected)
            if row.status != "DRAFT":
                self._error(409, "SCOPE_STRATEGY_PUBLISHED_IMMUTABLE")
            if row.code != payload.code:
                self._error(422, "SCOPE_STRATEGY_CODE_IMMUTABLE")
            codes = [p.code for p in payload.paths]
            if len(set(codes)) != len(codes) or any(p.mode == "CONDITIONAL" and not p.condition for p in payload.paths):
                self._error(422, "SCOPE_EXECUTION_PATH_INVALID")
            fields = payload.model_dump(mode="json")
            row.name, row.reason = payload.name, payload.reason
            row.paths_json, row.segmentation_rules = fields.pop("paths"), fields.pop("segmentation_rules")
            row.settings_json = {k: v for k, v in fields.items() if k not in {"code", "name", "reason"}}
            row.version += 1
            row.content_hash = _hash(
                {"paths": row.paths_json, "segmentation": row.segmentation_rules, "settings": row.settings_json}
            )
            self.db.flush()
            self._event(
                "EXECUTION_STRATEGY_UPDATED", row.id, {"project_workspace_id": workspace_id, "version": row.version}
            )
            return self._out(row) | {"paths": row.paths_json}

        return self._command(
            "scope.strategy.update",
            key,
            {"project": workspace_id, "id": strategy_id, "expected": expected, **payload.model_dump(mode="json")},
            apply,
        )

    def _allocation_totals(self, workspace_id, *, exclude=()):
        totals = {}
        active = {r.id for r in self._rows(PlanItem, workspace_id) if r.status != "SUPERSEDED" and r.id not in exclude}
        for link in self._rows(PlanItemScopeLink, workspace_id):
            if link.plan_item_id in active:
                totals[link.scope_item_id] = totals.get(link.scope_item_id, Decimal(0)) + link.quantity
        return totals

    def _create_plan_record(
        self, workspace_id, payload, profile, *, operation="CREATE", supersedes=(), exclude=(), rule=None
    ):
        if len({a.scope_item_id for a in payload.allocations}) != len(payload.allocations):
            self._error(422, "PLAN_DUPLICATE_SCOPE_ALLOCATION")
        if payload.parent_plan_item_id:
            parent = self._get(PlanItem, workspace_id, payload.parent_plan_item_id)
            if parent.status == "SUPERSEDED":
                self._error(409, "PLAN_PARENT_SUPERSEDED")
        if payload.strategy_id:
            self._get(ExecutionStrategy, workspace_id, payload.strategy_id)
        baseline = self._current_baseline(workspace_id)
        current_scope = {r["id"] for r in baseline.snapshot_json["items"]} if baseline else set()
        totals = self._allocation_totals(workspace_id, exclude=exclude)
        tolerance = Decimal(str(profile.content_json["quantity_tolerance"]))
        for link in payload.allocations:
            item = self._get(ScopeItem, workspace_id, link.scope_item_id)
            if profile.content_json["plan_item_rules"].get("approved_scope_required", True) and (
                item.status != "APPROVED" or item.id not in current_scope
            ):
                self._error(409, "PLAN_CURRENT_APPROVED_SCOPE_REQUIRED")
            if link.unit != item.unit:
                self._error(422, "PLAN_UNIT_MISMATCH_NO_SILENT_CONVERSION")
            if totals.get(item.id, Decimal(0)) + link.quantity > item.quantity + tolerance:
                self._error(422, "PLAN_SCOPE_QUANTITY_OVERALLOCATED")
        objects = self._objects(workspace_id, payload.model_object_ids)
        mapped = set(
            self.db.scalars(
                select(ScopeModelMapping.model_object_id).where(
                    ScopeModelMapping.tenant_id == self.tenant_id,
                    ScopeModelMapping.project_workspace_id == workspace_id,
                    ScopeModelMapping.scope_item_id.in_([a.scope_item_id for a in payload.allocations]),
                )
            )
        )
        if any(obj.id not in mapped for obj in objects):
            self._error(422, "PLAN_OBJECT_NOT_MAPPED_TO_SCOPE")
        object_ids = set(payload.model_object_ids) or mapped
        row = PlanItem(
            **self._base(workspace_id),
            code=payload.code,
            name=payload.name,
            parent_plan_item_id=payload.parent_plan_item_id,
            strategy_id=payload.strategy_id,
            reason=payload.reason,
            operation=operation,
            supersedes_ids=list(supersedes),
            future_mappings={
                name: {"status": "NOT_ACTIVE", "references": []}
                for name in ("WBS", "ACTIVITY", "CBS", "AWP", "PROGRESS", "CONTRACT_PACKAGE")
            },
            rule_json=deepcopy(rule or {}),
            content_hash=_hash(payload.model_dump(mode="json")),
        )
        self.db.add(row)
        self.db.flush()
        for allocation in payload.allocations:
            self.db.add(PlanItemScopeLink(**self._base(workspace_id), plan_item_id=row.id, **allocation.model_dump()))
        for object_id in object_ids:
            self.db.add(PlanItemModelLink(**self._base(workspace_id), plan_item_id=row.id, model_object_id=object_id))
        self.db.flush()
        self._event("PLAN_ITEM_CREATED", row.id, {"project_workspace_id": workspace_id, "operation": operation})
        return row

    def create_plan(self, workspace_id, payload, key):
        self._ready(workspace_id, "plan.edit")

        def apply():
            _, profile = self._ready(workspace_id, "plan.edit")
            return self._plan_out(self._create_plan_record(workspace_id, payload, profile))

        return self._command(
            "scope.plan.create", key, {"project": workspace_id, **payload.model_dump(mode="json")}, apply
        )

    def segment_strategy(self, workspace_id, strategy_id, payload, expected, key):
        self._ready(workspace_id, "plan.edit")

        def apply():
            _, profile = self._ready(workspace_id, "plan.edit")
            strategy = self._get(ExecutionStrategy, workspace_id, strategy_id, lock=True)
            self._version(strategy.version, expected)
            if payload.rule_index >= len(strategy.segmentation_rules):
                self._error(422, "SCOPE_SEGMENTATION_RULE_NOT_FOUND")
            rule = deepcopy(strategy.segmentation_rules[payload.rule_index])
            kind = rule["kind"]
            if kind not in profile.content_json["segmentation_rule_templates"]:
                self._error(422, "SCOPE_SEGMENTATION_RULE_NOT_GOVERNED")
            if len(set(payload.scope_item_ids)) != len(payload.scope_item_ids):
                self._error(422, "SCOPE_SEGMENTATION_DUPLICATE_ITEM")
            items = [self._get(ScopeItem, workspace_id, identity) for identity in payload.scope_item_ids]
            groups = {}
            totals = self._allocation_totals(workspace_id)
            for item in items:
                remaining = item.quantity - totals.get(item.id, Decimal(0))
                if remaining <= 0:
                    self._error(422, "SCOPE_SEGMENTATION_NO_UNALLOCATED_QUANTITY")
                if kind == "QUANTITY_RANGE":
                    size = Decimal(str(rule.get("quantity") or 0))
                    if size <= 0:
                        self._error(422, "SCOPE_SEGMENTATION_RANGE_REQUIRED")
                    index = 1
                    while remaining > 0:
                        if index > 1000:
                            self._error(422, "SCOPE_SEGMENTATION_TOO_MANY_PARTS")
                        amount = min(remaining, size)
                        groups[f"{item.scope_code}-{index}"] = [
                            AllocationIn(scope_item_id=item.id, quantity=amount, unit=item.unit)
                        ]
                        remaining -= amount
                        index += 1
                    continue
                if kind in {"AREA", "ZONE", "SYSTEM"}:
                    label = getattr(item, kind.lower())
                elif kind == "LEVEL":
                    objects = self._objects(workspace_id, self._item_out(item)["model_object_ids"])
                    levels = {obj.level for obj in objects if obj.level}
                    if len(levels) != 1:
                        self._error(422, "SCOPE_LEVEL_SPLIT_REQUIRES_EXPLICIT_ALLOCATION")
                    label = next(iter(levels))
                else:
                    # No invented workfront/package/geometry quantity inference.
                    label = payload.assignments.get(str(item.id), "")
                if not label or rule.get("values") and label not in rule["values"]:
                    self._error(422, "SCOPE_SEGMENTATION_EXPLICIT_ASSIGNMENT_REQUIRED")
                groups.setdefault(label, []).append(
                    AllocationIn(scope_item_id=item.id, quantity=remaining, unit=item.unit)
                )
            rows = []
            rule_reference = {
                "strategy_id": strategy.id,
                "strategy_version": strategy.version,
                "strategy_hash": strategy.content_hash,
                "rule_index": payload.rule_index,
                "rule": rule,
                "assignments": payload.assignments,
                "scope_item_ids": payload.scope_item_ids,
            }
            for index, (label, allocations) in enumerate(groups.items(), 1):
                plan = PlanIn(
                    code=f"{payload.code_prefix}-{index}",
                    name=f"{label}"[:300],
                    strategy_id=strategy.id,
                    allocations=allocations,
                    reason=payload.reason,
                )
                rows.append(
                    self._create_plan_record(
                        workspace_id, plan, profile, operation=f"SEGMENT_{kind}", rule=rule_reference
                    )
                )
            self._event(
                "PLAN_ITEMS_SEGMENTED",
                strategy.id,
                {"project_workspace_id": workspace_id, "rule": rule, "plan_item_ids": [row.id for row in rows]},
            )
            return {
                "items": [self._plan_out(row) for row in rows],
                "version": strategy.version,
                "candidate_only": True,
                "schedule_records_created": 0,
            }

        return self._command(
            "scope.strategy.segment",
            key,
            {"project": workspace_id, "id": strategy_id, "expected": expected, **payload.model_dump(mode="json")},
            apply,
        )

    def transform_plans(self, workspace_id, payload, key):
        self._ready(workspace_id, "plan.edit")

        def apply():
            _, profile = self._ready(workspace_id, "plan.edit")
            ids = payload.source_plan_item_ids
            if (
                len(set(ids)) != len(ids)
                or payload.operation == "GROUP"
                and (len(ids) < 2 or len(payload.outputs) != 1)
                or payload.operation == "SPLIT"
                and (len(ids) != 1 or len(payload.outputs) < 2)
            ):
                self._error(422, "PLAN_TRANSFORM_CARDINALITY_INVALID")
            sources = [self._get(PlanItem, workspace_id, identity, lock=True) for identity in ids]
            input_totals, output_totals = {}, {}
            for source in sources:
                self._version(source.version, payload.expected_versions.get(str(source.id)))
                if source.status == "SUPERSEDED":
                    self._error(409, "PLAN_SOURCE_ALREADY_SUPERSEDED")
                for allocation in self._plan_out(source)["allocations"]:
                    identity = allocation["scope_item_id"]
                    input_totals[identity] = input_totals.get(identity, Decimal(0)) + Decimal(
                        str(allocation["quantity"])
                    )
            for output in payload.outputs:
                for allocation in output.allocations:
                    identity = allocation.scope_item_id
                    output_totals[identity] = output_totals.get(identity, Decimal(0)) + allocation.quantity
            tolerance = Decimal(str(profile.content_json["quantity_tolerance"]))
            if set(input_totals) != set(output_totals) or any(
                abs(input_totals[i] - output_totals[i]) > tolerance for i in input_totals
            ):
                self._error(422, "PLAN_TRANSFORM_QUANTITY_NOT_CONSERVED")
            for source in sources:
                source.status, source.version = "SUPERSEDED", source.version + 1
            self.db.flush()
            rows = [
                self._create_plan_record(workspace_id, output, profile, operation=payload.operation, supersedes=ids)
                for output in payload.outputs
            ]
            self._event(
                f"PLAN_ITEM_{ {'GROUP': 'GROUPED', 'SPLIT': 'SPLIT', 'RECOMPOSE': 'RECOMPOSED'}[payload.operation] }",
                rows[0].id,
                {"project_workspace_id": workspace_id, "source_ids": ids, "result_ids": [r.id for r in rows]},
            )
            return {"items": [self._plan_out(row) for row in rows], "version": 1, "operation": payload.operation}

        return self._command(
            "scope.plan.transform", key, {"project": workspace_id, **payload.model_dump(mode="json")}, apply
        )

    def publish_plan(self, workspace_id, plan_id, payload, expected, key):
        self._ready(workspace_id, "plan.publish")

        def apply():
            _, profile = self._ready(workspace_id, "plan.publish")
            row = self._get(PlanItem, workspace_id, plan_id, lock=True)
            self._version(row.version, expected)
            if row.status != "DRAFT":
                self._error(409, "PLAN_PUBLICATION_TRANSITION_INVALID")
            if (
                profile.content_json["separation_of_duties"].get("plan_author_cannot_publish", True)
                and row.created_by == self.actor_id
            ):
                self._error(403, "PLAN_PUBLICATION_SOD")
            totals = self._allocation_totals(workspace_id)
            tolerance = Decimal(str(profile.content_json["quantity_tolerance"]))
            baseline = self._current_baseline(workspace_id)
            current_scope = {item["id"] for item in baseline.snapshot_json["items"]} if baseline else set()
            for allocation in self._plan_out(row)["allocations"]:
                item = self._get(ScopeItem, workspace_id, allocation["scope_item_id"])
                if profile.content_json["plan_item_rules"].get("approved_scope_required", True) and (
                    item.status != "APPROVED" or item.id not in current_scope
                ):
                    self._error(409, "PLAN_CURRENT_APPROVED_SCOPE_REQUIRED")
                if abs(totals.get(item.id, Decimal(0)) - item.quantity) > tolerance:
                    self._error(422, "PLAN_ALLOCATION_RECONCILIATION_REQUIRED")
            row.status, row.published_by, row.version = "PUBLISHED", self.actor_id, row.version + 1
            self.db.flush()
            self._event("PLAN_ITEM_PUBLISHED", row.id, {"project_workspace_id": workspace_id})
            return self._plan_out(row)

        return self._command(
            "scope.plan.publish",
            key,
            {"project": workspace_id, "id": plan_id, "expected": expected, **payload.model_dump(mode="json")},
            apply,
        )

    def create_derived(self, workspace_id, payload, key):
        self._ready(workspace_id, "derived.edit")

        def apply():
            self._ready(workspace_id, "derived.edit")
            if len(set(payload.plan_item_ids)) != len(payload.plan_item_ids):
                self._error(422, "DERIVED_DUPLICATE_PLAN_REFERENCE")
            plans = [self._get(PlanItem, workspace_id, identity) for identity in payload.plan_item_ids]
            if any(row.status == "SUPERSEDED" for row in plans):
                self._error(409, "DERIVED_PLAN_SUPERSEDED")
            linked = set()
            memberships = []
            for plan in plans:
                detail = self._plan_out(plan)
                linked.update(detail["model_object_ids"])
                memberships.append(
                    {
                        "plan_item_id": plan.id,
                        "plan_version": plan.version,
                        "operation": plan.operation,
                        "scope_item_ids": [r["scope_item_id"] for r in detail["allocations"]],
                        "allocations": detail["allocations"],
                    }
                )
            selected = set(payload.model_object_ids) or linked
            if not selected or not selected <= linked:
                self._error(422, "DERIVED_ORPHAN_MODEL_OBJECT_FORBIDDEN")
            objects = self._objects(workspace_id, sorted(selected))
            previous = self.db.scalars(
                select(DerivedModelVersion)
                .where(
                    DerivedModelVersion.tenant_id == self.tenant_id,
                    DerivedModelVersion.project_workspace_id == workspace_id,
                )
                .order_by(DerivedModelVersion.revision.desc())
            ).first()
            snapshot = {
                "representation_type": "LOGICAL",
                "physical_geometry_modified": False,
                "memberships": memberships,
                "split_rule": payload.split_rule,
                "objects": [
                    {
                        "object_id": r.id,
                        "model_version_id": r.model_version_id,
                        "guid": r.guid,
                        "express_id": r.express_id,
                        "geometry_reference": r.geometry_reference,
                        "source_hash": self._get(ScopeModelVersion, workspace_id, r.model_version_id).source_hash,
                    }
                    for r in objects
                ],
                "visibility": payload.visibility_json,
                "section": payload.section_json,
                "future_4d": "NOT_ACTIVE",
                "created_by": self.actor_id,
            }
            if payload.restore_version_id:
                restore = self._get(DerivedModelVersion, workspace_id, payload.restore_version_id)
                restored_objects = {r["object_id"] for r in restore.snapshot_json["objects"]}
                if not restored_objects <= linked:
                    self._error(409, "DERIVED_RESTORE_MEMBERSHIP_STALE")
                snapshot["restored_from_id"] = restore.id
                snapshot["visibility"] = deepcopy(restore.snapshot_json["visibility"])
                snapshot["section"] = deepcopy(restore.snapshot_json["section"])
            row = DerivedModelVersion(
                **self._base(workspace_id),
                revision=previous.revision + 1 if previous else 1,
                predecessor_id=previous.id if previous else None,
                reason=payload.reason,
                snapshot_json=_json(snapshot),
                content_hash=_hash(snapshot),
            )
            self.db.add(row)
            self.db.flush()
            self._event(
                "DERIVED_MODEL_UPDATED", row.id, {"project_workspace_id": workspace_id, "hash": row.content_hash}
            )
            return self._out(row)

        return self._command(
            "scope.derived.create", key, {"project": workspace_id, **payload.model_dump(mode="json")}, apply
        )

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
            self._error(404, "SCOPE_PROFILE_NOT_FOUND")
        return row

    def profiles(self):
        self._permission("admin.configure")
        rows = self.db.scalars(
            select(AdminConfiguration)
            .where(AdminConfiguration.tenant_id == self.tenant_id, AdminConfiguration.kind == PROFILE_KIND)
            .order_by(AdminConfiguration.code, AdminConfiguration.revision.desc())
        )
        return {
            "items": [self._profile_out(row) for row in rows],
            "default_content": deepcopy(DEFAULT_PROFILE),
            "allowed_actions": self.allowed_actions(),
        }

    def _validate_scope_profile(self, content):
        try:
            if set(content) - set(DEFAULT_PROFILE):
                raise ValueError("unknown configuration key")
            if set(content["scope_natures"]) != set(DEFAULT_PROFILE["scope_natures"]):
                raise ValueError("four governed Scope natures required")
            for name in ("scope_types", "disciplines", "units"):
                if (
                    not isinstance(content[name], list)
                    or not content[name]
                    or any(not isinstance(v, str) or not v.strip() for v in content[name])
                ):
                    raise ValueError(name)
            tolerance = Decimal(str(content["quantity_tolerance"]))
            if not tolerance.is_finite() or tolerance < 0 or tolerance > Decimal("0.1"):
                raise ValueError("absolute allocation tolerance")
            if content["scope_approval_workflow"] != DEFAULT_PROFILE["scope_approval_workflow"]:
                raise ValueError("unsupported workflow")
            if set(content["segmentation_rule_templates"]) - set(DEFAULT_PROFILE["segmentation_rule_templates"]):
                raise ValueError("segmentation template")
            if content["plan_item_rules"].get("physical_split_enabled", False):
                raise ValueError("physical split not implemented")
            if content["unit_rules"].get("conversion") != "EXPLICIT_KNOWN_BASIS_ONLY":
                raise ValueError("unit conversion")
            if any(not isinstance(v, bool) for v in content["separation_of_duties"].values()):
                raise ValueError("SoD")
            scope = content["scope"]
            if scope["type"] not in {"tenant", "workspace"}:
                raise ValueError("scope")
            if scope["type"] == "workspace":
                self._project(scope["workspace_id"])
            elif scope.get("workspace_id") is not None:
                raise ValueError("scope target")
            start, end = self._instant(content.get("effective_from")), self._instant(content.get("effective_to"))
            if start and end and end <= start:
                raise ValueError("effective window")
        except (KeyError, TypeError, ValueError) as error:
            raise HTTPException(422, detail={"code": "SCOPE_PROFILE_INVALID"}) from error

    def create_profile(self, payload, key):
        self._permission("admin.configure")

        def apply():
            self._validate_scope_profile(payload.content_json)
            if self.db.scalar(
                select(AdminConfiguration.id).where(
                    AdminConfiguration.tenant_id == self.tenant_id,
                    AdminConfiguration.kind == PROFILE_KIND,
                    AdminConfiguration.code == payload.code,
                )
            ):
                self._error(409, "SCOPE_PROFILE_CODE_EXISTS")
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
            self._event("SCOPE_PROFILE_CREATED", row.id, {"hash": row.content_hash})
            return self._profile_out(row)

        return self._command("scope.profile.create", key, payload.model_dump(mode="json"), apply)

    def update_profile(self, identity, payload, expected, key):
        self._permission("admin.configure")

        def apply():
            row = self._profile(identity, lock=True)
            self._version(row.version, expected)
            if row.status != "draft":
                self._error(409, "SCOPE_PROFILE_PUBLISHED_IMMUTABLE")
            self._validate_scope_profile(payload.content_json)
            row.name, row.content_json, row.content_hash = (
                payload.name,
                deepcopy(payload.content_json),
                _hash(payload.content_json),
            )
            row.version += 1
            row.updated_at = utc_now()
            self.db.flush()
            self._event("SCOPE_PROFILE_UPDATED", row.id, {"version": row.version, "hash": row.content_hash})
            return self._profile_out(row)

        return self._command(
            "scope.profile.update",
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
                self._error(409, "SCOPE_PROFILE_PUBLISHED_IMMUTABLE")
            self._validate_scope_profile(row.content_json)
            editor = row.created_by_user_id
            if row.version > 1:
                receipt = self.db.scalar(
                    select(OperationalContextCommand).where(
                        OperationalContextCommand.tenant_id == self.tenant_id,
                        OperationalContextCommand.command_type == "scope.profile.update",
                        OperationalContextCommand.result_json["id"].as_integer() == row.id,
                        OperationalContextCommand.result_json["version"].as_integer() == row.version,
                    )
                )
                if receipt is None or receipt.result_json.get("content_hash") != row.content_hash:
                    self._error(409, "SCOPE_PROFILE_EDITOR_PROVENANCE_REQUIRED")
                editor = receipt.actor_id
            if row.content_json["separation_of_duties"].get("author_cannot_publish", True) and self.actor_id in {
                row.created_by_user_id,
                editor,
            }:
                self._error(403, "SCOPE_PROFILE_PUBLICATION_SOD")
            row.status, row.published_at, row.version = "published", utc_now(), row.version + 1
            self.db.flush()
            self._event("SCOPE_PROFILE_PUBLISHED", row.id, {"hash": row.content_hash, "reason": payload.reason})
            return self._profile_out(row)

        return self._command(
            "scope.profile.publish",
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
                self._error(409, "PUBLISHED_SCOPE_PROFILE_REQUIRED")
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
            self._event("SCOPE_PROFILE_SUCCESSOR", row.id, {"predecessor_id": old.id})
            return self._profile_out(row)

        return self._command(
            "scope.profile.successor",
            key,
            {"id": identity, "expected": expected, **payload.model_dump(mode="json")},
            apply,
        )
