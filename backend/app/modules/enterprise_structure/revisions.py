"""Governed snapshot revisions for the published Enterprise Structure CORE."""

from __future__ import annotations

import copy
import hashlib
import json
import re
import uuid
from collections import Counter
from typing import Any

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domain.models import EnterpriseWorkspace, SecurityEvent, UserAccount
from app.modules.enterprise_structure.constants import WORKSPACE_STATUSES
from app.modules.enterprise_structure.models import (
    EnterpriseCoreRelease,
    EnterpriseWorkspaceClassification,
    EnterpriseWorkspaceLink,
)
from app.modules.enterprise_structure.repository import EnterpriseStructureRepository
from app.modules.enterprise_structure.schemas import (
    CoreReleaseOut,
    CoreRevisionOut,
    RevisionApprovalRequest,
    RevisionClassificationIn,
    RevisionClassificationsUpdate,
    RevisionDiffItem,
    RevisionDiffOut,
    RevisionMoveRequest,
    RevisionPublishRequest,
    RevisionRecordCodeImpact,
    RevisionRecordCodePreviewOut,
    RevisionRecordCodePreviewRequest,
    RevisionReleaseUpdate,
    RevisionRollbackRequest,
    RevisionValidationOut,
    RevisionWorkspaceCreate,
    RevisionWorkspaceOut,
    RevisionWorkspaceUpdate,
)

REVISION_STATES = {"draft", "published", "superseded", "unpublished"}


class EnterpriseStructureRevisionService:
    def __init__(self, db: Session, tenant_id: int, actor_id: int) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.actor_id = actor_id
        self.repository = EnterpriseStructureRepository(db, tenant_id)

    def create_revision(self, published_id: int) -> CoreRevisionOut:
        source = self._release(published_id)
        if source.state != "published":
            raise HTTPException(
                status_code=409, detail="A revision can only be created from the current published release"
            )
        current = self.repository.latest_core_release()
        if current is None or current.id != source.id:
            raise HTTPException(status_code=409, detail="The selected release is not the current published release")
        existing = self.repository.latest_draft_release()
        if existing is not None:
            if existing.previous_release_id == source.id:
                return self.revision_out(existing)
            raise HTTPException(status_code=409, detail="Another draft revision already exists")

        revision_number = max(source.revision_number + 1, self.repository.release_count() + 1)
        release_code = self._next_release_code(revision_number)
        snapshot = self._normalized_snapshot(source)
        now = utc_now()
        draft_hash = _snapshot_hash(release_code, snapshot)
        draft = EnterpriseCoreRelease(
            tenant_id=self.tenant_id,
            release_code=release_code,
            release_name=f"Workspace Structure Revision {revision_number:03d}",
            revision_number=revision_number,
            state="draft",
            source_hash=source.source_hash,
            canonical_hash=source.canonical_hash,
            content_fingerprint=draft_hash,
            source_release_code=source.release_code,
            previous_release_id=source.id,
            base_content_fingerprint=source.content_fingerprint,
            snapshot_json=snapshot,
            workspace_count=len(snapshot["workspaces"]),
            objective_count=len(snapshot["strategic_objectives"]),
            classification_count=len(snapshot["classifications"]),
            link_count=len(snapshot["links"]),
            validation_json={},
            diff_hash=_hash([]),
            created_at=now,
            created_by_user_id=self.actor_id,
            updated_at=now,
        )
        self.db.add(draft)
        self.db.flush()
        draft.diff_hash = self._diff(draft).diff_hash
        self._event(
            "enterprise_structure.revision_created",
            draft,
            {
                "previous_release_id": source.id,
                "previous_release": source.release_code,
                "draft_hash": draft.content_fingerprint,
                "diff_hash": draft.diff_hash,
                "result": "created",
            },
        )
        self.db.commit()
        self.db.refresh(draft)
        return self.revision_out(draft)

    def get_revision(self, release_id: int) -> CoreRevisionOut:
        return self.revision_out(self._release(release_id))

    def update_revision(self, release_id: int, payload: RevisionReleaseUpdate) -> CoreRevisionOut:
        release = self._draft(release_id)
        release.release_name = payload.release_name.strip()
        self._refresh_draft(release, release.snapshot_json, operation="release_updated")
        self.db.commit()
        return self.revision_out(release)

    def record_code_preview(
        self,
        release_id: int,
        payload: RevisionRecordCodePreviewRequest,
    ) -> RevisionRecordCodePreviewOut:
        release = self._draft(release_id)
        snapshot = self._normalized_snapshot(release)
        workspaces = snapshot["workspaces"]
        parent = self._workspace(workspaces, payload.parent_key)
        self._ensure_allowed_child(parent, payload.workspace_type_code)
        workspace = self._workspace(workspaces, payload.workspace_key) if payload.workspace_key else None
        record_code = self._next_record_code(workspaces, parent, exclude_key=payload.workspace_key)
        affected: list[RevisionRecordCodeImpact] = []
        if workspace:
            old_code = workspace["record_code"]
            for descendant in self._descendants(workspaces, workspace["external_key"]):
                affected.append(
                    RevisionRecordCodeImpact(
                        workspace_key=descendant["external_key"],
                        before=descendant["record_code"],
                        after=f"{record_code}{descendant['record_code'][len(old_code) :]}",
                    )
                )
        return RevisionRecordCodePreviewOut(
            current_record_code=workspace["record_code"] if workspace else None,
            record_code=record_code,
            affected_descendants=affected,
        )

    def add_workspace(self, release_id: int, payload: RevisionWorkspaceCreate) -> CoreRevisionOut:
        release = self._draft(release_id)
        snapshot = self._normalized_snapshot(release)
        workspaces = snapshot["workspaces"]
        parent = self._workspace(workspaces, payload.parent_key)
        type_code = _configuration_code(payload.workspace_type_code)
        self._ensure_allowed_child(parent, type_code)
        status = payload.status.strip().lower()
        if status not in WORKSPACE_STATUSES:
            raise HTTPException(status_code=422, detail=f"Unsupported workspace status: {status}")
        workspace_key = f"REV-{release.id}-{uuid.uuid4().hex[:12].upper()}"
        code = self._generated_code(type_code, workspaces)
        workspaces.append(
            {
                "id": None,
                "technical_id": None,
                "external_key": workspace_key,
                "parent_id": parent.get("id"),
                "parent_external_key": parent["external_key"],
                "record_code": self._next_record_code(workspaces, parent),
                "code": code,
                "name": _required(payload.name, "Workspace name"),
                "workspace_type": type_code,
                "workspace_type_code": type_code,
                "description": payload.description.strip(),
                "responsible_user_id": payload.responsible_user_id,
                "status": status,
                "sort_order": self._next_sort_order(workspaces, parent["external_key"]),
            }
        )
        for classification in payload.applicable_classifications:
            snapshot["classifications"].append(self._classification(workspace_key, classification))
        self._refresh_draft(release, snapshot, operation="workspace_added", workspace_key=workspace_key)
        self.db.commit()
        return self.revision_out(release)

    def edit_workspace(
        self,
        release_id: int,
        workspace_key: str,
        payload: RevisionWorkspaceUpdate,
    ) -> CoreRevisionOut:
        release = self._draft(release_id)
        snapshot = self._normalized_snapshot(release)
        workspace = self._workspace(snapshot["workspaces"], workspace_key)
        if payload.name is not None:
            workspace["name"] = _required(payload.name, "Workspace name")
        if payload.description is not None:
            workspace["description"] = payload.description.strip()
        if "responsible_user_id" in payload.model_fields_set:
            workspace["responsible_user_id"] = payload.responsible_user_id
        if payload.status is not None:
            status = payload.status.strip().lower()
            if status not in WORKSPACE_STATUSES:
                raise HTTPException(status_code=422, detail=f"Unsupported workspace status: {status}")
            if workspace["status"] == "archived" and status != "archived":
                raise HTTPException(status_code=409, detail="Archived workspaces cannot be reactivated inside a draft")
            workspace["status"] = status
        self._refresh_draft(release, snapshot, operation="workspace_edited", workspace_key=workspace_key)
        self.db.commit()
        return self.revision_out(release)

    def move_workspace(
        self,
        release_id: int,
        workspace_key: str,
        payload: RevisionMoveRequest,
    ) -> CoreRevisionOut:
        release = self._draft(release_id)
        snapshot = self._normalized_snapshot(release)
        workspaces = snapshot["workspaces"]
        workspace = self._workspace(workspaces, workspace_key)
        parent = self._workspace(workspaces, payload.new_parent_key)
        if workspace["parent_external_key"] is None:
            raise HTTPException(status_code=409, detail="The Enterprise root cannot be moved")
        if parent["external_key"] == workspace["external_key"] or parent["external_key"] in {
            item["external_key"] for item in self._descendants(workspaces, workspace["external_key"])
        }:
            raise HTTPException(status_code=409, detail="Workspace hierarchy cannot contain cycles")
        self._ensure_allowed_child(parent, workspace["workspace_type_code"])
        old_code = workspace["record_code"]
        new_code = self._next_record_code(workspaces, parent, exclude_key=workspace["external_key"])
        descendants = self._descendants(workspaces, workspace["external_key"])
        workspace["parent_external_key"] = parent["external_key"]
        workspace["parent_id"] = parent.get("id")
        workspace["record_code"] = new_code
        for descendant in descendants:
            descendant["record_code"] = f"{new_code}{descendant['record_code'][len(old_code) :]}"
        self._refresh_draft(
            release,
            snapshot,
            operation="workspace_moved",
            workspace_key=workspace_key,
            extra={"before": old_code, "after": new_code, "affected_descendants": len(descendants)},
        )
        self.db.commit()
        return self.revision_out(release)

    def archive_workspace(self, release_id: int, workspace_key: str) -> CoreRevisionOut:
        release = self._draft(release_id)
        snapshot = self._normalized_snapshot(release)
        workspaces = snapshot["workspaces"]
        workspace = self._workspace(workspaces, workspace_key)
        children = [
            item
            for item in workspaces
            if item["parent_external_key"] == workspace["external_key"] and item["status"] != "archived"
        ]
        if children:
            raise HTTPException(status_code=409, detail="Cannot archive a workspace with active children")
        if workspace["parent_external_key"] is None:
            raise HTTPException(status_code=409, detail="The Enterprise root cannot be archived")
        workspace["status"] = "archived"
        self._refresh_draft(release, snapshot, operation="workspace_archived", workspace_key=workspace_key)
        self.db.commit()
        return self.revision_out(release)

    def set_classifications(
        self,
        release_id: int,
        workspace_key: str,
        payload: RevisionClassificationsUpdate,
    ) -> CoreRevisionOut:
        release = self._draft(release_id)
        snapshot = self._normalized_snapshot(release)
        self._workspace(snapshot["workspaces"], workspace_key)
        replacement = [self._classification(workspace_key, item) for item in payload.classifications]
        pairs = [(item["category_set_code"], item["category_item_code"]) for item in replacement]
        if len(pairs) != len(set(pairs)):
            raise HTTPException(status_code=422, detail="Classification values must be unique")
        snapshot["classifications"] = [
            item for item in snapshot["classifications"] if item["workspace_external_key"] != workspace_key
        ] + replacement
        self._refresh_draft(release, snapshot, operation="classifications_updated", workspace_key=workspace_key)
        self.db.commit()
        return self.revision_out(release)

    def validate_revision(self, release_id: int) -> RevisionValidationOut:
        release = self._draft(release_id)
        result = self._validate(release)
        now = utc_now()
        release.validation_json = {
            "valid": result.valid,
            "errors": result.errors,
            "conflicts": result.conflicts,
            "checks": result.checks,
            "draft_hash": result.draft_hash,
            "diff_hash": result.diff_hash,
        }
        release.validated_at = now
        release.validated_by_user_id = self.actor_id
        release.validated_draft_hash = result.draft_hash
        release.updated_at = now
        self._event(
            "enterprise_structure.revision_validated",
            release,
            {
                "draft_hash": result.draft_hash,
                "diff_hash": result.diff_hash,
                "errors": len(result.errors),
                "conflicts": len(result.conflicts),
                "result": "valid" if result.valid else "invalid",
            },
        )
        self.db.commit()
        return result.model_copy(update={"validated_at": now})

    def compare_revision(self, release_id: int) -> RevisionDiffOut:
        release = self._release(release_id)
        return self._diff(release)

    def approve_revision(self, release_id: int, payload: RevisionApprovalRequest) -> CoreRevisionOut:
        release = self._draft(release_id)
        current_diff = self._diff(release)
        self._ensure_hash_match(release, current_diff, payload.draft_hash, payload.diff_hash)
        validation = release.validation_json or {}
        if not validation.get("valid") or release.validated_draft_hash != release.content_fingerprint:
            raise HTTPException(status_code=409, detail="A current successful validation is required before approval")
        now = utc_now()
        release.approved_at = now
        release.approved_by_user_id = self.actor_id
        release.approved_draft_hash = release.content_fingerprint
        release.approved_diff_hash = current_diff.diff_hash
        release.updated_at = now
        self._event(
            "enterprise_structure.revision_approved",
            release,
            {
                "source_release": release.previous_release_id,
                "draft_release": release.id,
                "draft_hash": release.content_fingerprint,
                "diff_hash": current_diff.diff_hash,
                "result": "approved",
            },
        )
        self.db.commit()
        return self.revision_out(release)

    def publish_revision(self, release_id: int, payload: RevisionPublishRequest) -> CoreRevisionOut:
        release = self._release(release_id)
        current_diff = self._diff(release)
        if release.state == "published":
            self._ensure_hash_match(release, current_diff, payload.draft_hash, payload.diff_hash)
            return self.revision_out(release)
        if release.state != "draft":
            raise HTTPException(status_code=409, detail="Only a draft revision can be published")
        self._ensure_hash_match(release, current_diff, payload.draft_hash, payload.diff_hash)
        validation = self._validate(release)
        if not validation.valid or release.validated_draft_hash != release.content_fingerprint:
            raise HTTPException(status_code=409, detail="The revision must pass validation again before publishing")
        if (
            release.approved_at is None
            or release.approved_draft_hash != release.content_fingerprint
            or release.approved_diff_hash != current_diff.diff_hash
        ):
            raise HTTPException(status_code=409, detail="Explicit approval for the current draft and diff is required")
        current = self.repository.latest_core_release()
        if current is None or current.id != release.previous_release_id:
            raise HTTPException(status_code=409, detail={"reason": "BASE_RELEASE_CHANGED"})

        try:
            snapshot = self._materialize_snapshot(release.snapshot_json)
            now = utc_now()
            current.state = "superseded"
            release.snapshot_json = snapshot
            release.content_fingerprint = _snapshot_hash(release.release_code, snapshot)
            release.workspace_count = len(snapshot["workspaces"])
            release.objective_count = len(snapshot["strategic_objectives"])
            release.classification_count = len(snapshot["classifications"])
            release.link_count = len(snapshot["links"])
            release.state = "published"
            release.published_at = now
            release.published_by_user_id = self.actor_id
            release.updated_at = now
            self._event(
                "enterprise_structure.core_published",
                release,
                {
                    "previous_release": current.release_code,
                    "previous_release_id": current.id,
                    "draft_hash": release.content_fingerprint,
                    "diff_hash": current_diff.diff_hash,
                    "workspace_count": release.workspace_count,
                    "result": "published",
                },
            )
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise HTTPException(
                status_code=409, detail="Revision publication conflicts with persisted identities"
            ) from exc
        self.db.refresh(release)
        return self.revision_out(release)

    def rollback_revision(self, release_id: int, payload: RevisionRollbackRequest) -> CoreRevisionOut:
        release = self._release(release_id)
        if not payload.confirm:
            raise HTTPException(status_code=409, detail="Explicit rollback confirmation is required")
        current = self.repository.latest_core_release()
        if release.state != "published" or current is None or current.id != release.id:
            raise HTTPException(status_code=409, detail="Only the current published release can be rolled back")
        if release.previous_release_id is None:
            raise HTTPException(status_code=409, detail="The initial release has no predecessor to reactivate")
        previous = self._release(release.previous_release_id)
        try:
            self._materialize_snapshot(previous.snapshot_json)
            now = utc_now()
            release.state = "unpublished"
            release.unpublished_at = now
            release.unpublished_by_user_id = self.actor_id
            release.rollback_reason = payload.reason.strip()
            previous.state = "published"
            self._event(
                "enterprise_structure.core_unpublished",
                release,
                {
                    "reactivated_release": previous.release_code,
                    "reactivated_release_id": previous.id,
                    "reason": payload.reason.strip(),
                    "result": "unpublished",
                },
            )
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise HTTPException(
                status_code=409, detail="Rollback conflicts with persisted workspace identities"
            ) from exc
        return self.revision_out(previous)

    def revision_out(self, release: EnterpriseCoreRelease) -> CoreRevisionOut:
        snapshot = self._normalized_snapshot(release)
        diff = self._diff(release)
        action_by_key: dict[str, str] = {}
        for item in diff.items:
            if item.action != "CLASSIFICATION" or item.workspace_key not in action_by_key:
                action_by_key[item.workspace_key] = item.action.lower()
        classifications = self._classifications_by_workspace(snapshot)
        created_by = self._actor_email(release.created_by_user_id) or "unknown"
        published_by = self._actor_email(release.published_by_user_id)
        approved_by = self._actor_email(release.approved_by_user_id)
        validation = None
        if release.validation_json:
            validation_payload = release.validation_json
            validation = RevisionValidationOut(
                valid=bool(validation_payload.get("valid", False)),
                errors=validation_payload.get("errors", []),
                conflicts=validation_payload.get("conflicts", []),
                checks=validation_payload.get("checks", {}),
                draft_hash=validation_payload.get("draft_hash", release.content_fingerprint),
                diff_hash=validation_payload.get("diff_hash", diff.diff_hash),
                validated_at=release.validated_at,
            )
        return CoreRevisionOut(
            id=release.id,
            release_code=release.release_code,
            release_name=release.release_name,
            revision_number=release.revision_number,
            state=release.state,
            previous_release_id=release.previous_release_id,
            source_hash=release.source_hash,
            canonical_hash=release.canonical_hash,
            content_fingerprint=release.content_fingerprint,
            workspace_count=release.workspace_count,
            objective_count=release.objective_count,
            classification_count=release.classification_count,
            link_count=release.link_count,
            published_at=release.published_at,
            published_by=published_by,
            base_content_fingerprint=release.base_content_fingerprint,
            created_at=release.created_at,
            created_by=created_by,
            updated_at=release.updated_at,
            validated_at=release.validated_at,
            approved_at=release.approved_at,
            approved_by=approved_by,
            draft_hash=release.content_fingerprint,
            diff_hash=diff.diff_hash,
            validation=validation,
            workspaces=[
                RevisionWorkspaceOut(
                    workspace_key=item["external_key"],
                    technical_id=item.get("id"),
                    parent_key=item.get("parent_external_key"),
                    record_code=item["record_code"],
                    code=item["code"],
                    name=item["name"],
                    workspace_type_code=item["workspace_type_code"],
                    description=item.get("description", ""),
                    responsible_user_id=item.get("responsible_user_id"),
                    status=item["status"],
                    sort_order=int(item.get("sort_order", 0)),
                    change_state=action_by_key.get(item["external_key"], "unchanged"),
                    classifications=classifications.get(item["external_key"], []),
                )
                for item in sorted(snapshot["workspaces"], key=lambda row: _record_code_key(row["record_code"]))
            ],
        )

    def _validate(self, release: EnterpriseCoreRelease) -> RevisionValidationOut:
        snapshot = self._normalized_snapshot(release)
        workspaces = snapshot["workspaces"]
        errors: list[str] = []
        conflicts: list[str] = []
        checks = {
            "single_root": True,
            "acyclic": True,
            "parent_child_compatibility": True,
            "record_code_unique": True,
            "external_key_unique": True,
            "required_classifications": True,
            "category_applicability": True,
            "links_valid": True,
            "cross_tenant_zero": True,
            "no_orphans": True,
            "status_transitions": True,
            "codes_unique": True,
        }
        tenant = snapshot.get("tenant", {})
        if tenant.get("id") != self.tenant_id:
            checks["cross_tenant_zero"] = False
            errors.append("Snapshot tenant does not match the authenticated tenant")

        keys = [str(item.get("external_key") or "") for item in workspaces]
        if "" in keys or len(keys) != len(set(keys)):
            checks["external_key_unique"] = False
            errors.append("external_key must be present and unique")
        record_codes = [str(item.get("record_code") or "") for item in workspaces]
        if "" in record_codes or len(record_codes) != len(set(record_codes)):
            checks["record_code_unique"] = False
            errors.append("record_code must be present and unique")
        codes = [str(item.get("code") or "") for item in workspaces]
        if "" in codes or len(codes) != len(set(codes)):
            checks["codes_unique"] = False
            errors.append("Workspace codes must be present and unique")
        roots = [
            item for item in workspaces if item.get("parent_external_key") is None and item["status"] != "archived"
        ]
        if len(roots) != 1:
            checks["single_root"] = False
            errors.append("Exactly one non-archived Enterprise root is required")

        by_key = {item["external_key"]: item for item in workspaces if item.get("external_key")}
        base = (
            self._normalized_snapshot(self._release(release.previous_release_id))
            if release.previous_release_id
            else None
        )
        base_by_key = {item["external_key"]: item for item in (base or {}).get("workspaces", [])}
        missing_baseline = sorted(set(base_by_key) - set(by_key))
        if missing_baseline:
            conflicts.append(f"Baseline identities are missing: {', '.join(missing_baseline)}")

        types = {
            item.code: item for item in self.repository.latest_configurations("workspace_type", published_only=True)
        }
        categories = {item.code: item for item in self.repository.latest_configurations("catalog", published_only=True)}
        classifications = self._classifications_by_workspace(snapshot)
        for workspace in workspaces:
            key = workspace["external_key"]
            status = workspace["status"]
            if status not in WORKSPACE_STATUSES:
                checks["status_transitions"] = False
                errors.append(f"{key}: unsupported status {status}")
            baseline = base_by_key.get(key)
            if baseline and not self._valid_status_transition(baseline["status"], status):
                checks["status_transitions"] = False
                errors.append(f"{key}: invalid status transition {baseline['status']} -> {status}")
            workspace_type = types.get(workspace["workspace_type_code"])
            if workspace_type is None:
                checks["parent_child_compatibility"] = False
                errors.append(f"{key}: workspace type is not published")
                continue
            parent_key = workspace.get("parent_external_key")
            if parent_key is None:
                if not workspace_type.content_json.get("can_be_root", False):
                    checks["parent_child_compatibility"] = False
                    errors.append(f"{key}: type cannot be root")
            else:
                parent = by_key.get(parent_key)
                if parent is None:
                    checks["no_orphans"] = False
                    errors.append(f"{key}: parent does not exist")
                else:
                    parent_type = types.get(parent["workspace_type_code"])
                    if parent_type is None or workspace["workspace_type_code"] not in parent_type.content_json.get(
                        "allowed_children", []
                    ):
                        checks["parent_child_compatibility"] = False
                        errors.append(f"{key}: incompatible parent-child composition")
            if status != "archived":
                assigned_sets = {item.category_set_code for item in classifications.get(key, [])}
                required = set(workspace_type.content_json.get("required_categories", []))
                missing = sorted(required - assigned_sets)
                if missing:
                    checks["required_classifications"] = False
                    errors.append(f"{key}: missing required classifications {', '.join(missing)}")
            for classification in classifications.get(key, []):
                category = categories.get(classification.category_set_code)
                if category is None:
                    checks["category_applicability"] = False
                    errors.append(f"{key}: category {classification.category_set_code} is not published")
                    continue
                if workspace["workspace_type_code"] not in category.content_json.get("applicable_types", []):
                    checks["category_applicability"] = False
                    errors.append(f"{key}: category {classification.category_set_code} is not applicable")
                valid_items = {str(item["code"]).lower() for item in category.content_json.get("items", [])}
                if classification.category_set_code == "strategic-objective":
                    valid_items |= {
                        item.code.lower() for item in self.repository.strategic_objectives(active_only=True)
                    }
                if classification.category_item_code.lower() not in valid_items:
                    checks["category_applicability"] = False
                    errors.append(
                        f"{key}: value {classification.category_item_code} is not active in "
                        f"{classification.category_set_code}"
                    )

        for workspace in workspaces:
            visited: set[str] = set()
            current = workspace
            while current.get("parent_external_key") is not None:
                parent_key = current["parent_external_key"]
                if parent_key in visited or parent_key == workspace["external_key"]:
                    checks["acyclic"] = False
                    errors.append(f"{workspace['external_key']}: hierarchy contains a cycle")
                    break
                visited.add(parent_key)
                parent = by_key.get(parent_key)
                if parent is None:
                    break
                current = parent

        for link in snapshot["links"]:
            source_key = link.get("source_workspace_external_key") or link.get("source_external_key")
            target_key = link.get("target_workspace_external_key") or link.get("target_external_key")
            if source_key not in by_key or target_key not in by_key or source_key == target_key:
                checks["links_valid"] = False
                errors.append("Workspace link references invalid or identical endpoints")

        diff = self._diff(release)
        draft_hash = _snapshot_hash(release.release_code, snapshot)
        return RevisionValidationOut(
            valid=not errors and not conflicts,
            errors=sorted(set(errors)),
            conflicts=sorted(set(conflicts)),
            checks=checks,
            draft_hash=draft_hash,
            diff_hash=diff.diff_hash,
        )

    def _diff(self, release: EnterpriseCoreRelease) -> RevisionDiffOut:
        current = self._normalized_snapshot(release)
        baseline = (
            self._normalized_snapshot(self._release(release.previous_release_id))
            if release.previous_release_id is not None
            else {"workspaces": [], "classifications": []}
        )
        before = {item["external_key"]: item for item in baseline["workspaces"]}
        after = {item["external_key"]: item for item in current["workspaces"]}
        before_classifications = self._classifications_by_workspace(baseline)
        after_classifications = self._classifications_by_workspace(current)
        items: list[RevisionDiffItem] = []
        summary = Counter(
            added=0,
            modified=0,
            moved=0,
            archived=0,
            classification_changes=0,
            unchanged=0,
        )
        for key in sorted(set(before) | set(after)):
            old = before.get(key)
            new = after.get(key)
            old_classes = before_classifications.get(key, [])
            new_classes = after_classifications.get(key, [])
            if old is None and new is not None:
                summary["added"] += 1
                items.append(self._diff_item("ADD", key, None, new, old_classes, new_classes))
                continue
            if new is None and old is not None:
                summary["archived"] += 1
                items.append(self._diff_item("ARCHIVE", key, old, None, old_classes, new_classes))
                continue
            assert old is not None and new is not None
            changed = False
            if old["status"] != "archived" and new["status"] == "archived":
                summary["archived"] += 1
                items.append(self._diff_item("ARCHIVE", key, old, new, old_classes, new_classes))
                changed = True
            elif old.get("parent_external_key") != new.get("parent_external_key"):
                summary["moved"] += 1
                item = self._diff_item("MOVE", key, old, new, old_classes, new_classes)
                item.affected_descendants = [
                    descendant["external_key"] for descendant in self._descendants(current["workspaces"], key)
                ]
                items.append(item)
                changed = True
            elif any(
                old.get(field) != new.get(field)
                for field in ("name", "description", "responsible_user_id", "status", "workspace_type_code")
            ):
                summary["modified"] += 1
                items.append(self._diff_item("MODIFY", key, old, new, old_classes, new_classes))
                changed = True
            if _classification_pairs(old_classes) != _classification_pairs(new_classes):
                summary["classification_changes"] += 1
                items.append(self._diff_item("CLASSIFICATION", key, old, new, old_classes, new_classes))
                changed = True
            if not changed:
                summary["unchanged"] += 1
        payload = [item.model_dump(mode="json") for item in items]
        return RevisionDiffOut(
            release_id=release.id,
            draft_hash=_snapshot_hash(release.release_code, current),
            diff_hash=_hash(payload),
            summary=dict(summary),
            items=items,
        )

    def _diff_item(
        self,
        action: str,
        key: str,
        old: dict[str, Any] | None,
        new: dict[str, Any] | None,
        old_classes: list[RevisionClassificationIn],
        new_classes: list[RevisionClassificationIn],
    ) -> RevisionDiffItem:
        selected = new or old or {}
        return RevisionDiffItem(
            action=action,
            workspace_key=key,
            old_record_code=old.get("record_code") if old else None,
            new_record_code=new.get("record_code") if new else None,
            workspace_type=selected.get("workspace_type_code", ""),
            name=selected.get("name", ""),
            parent_before=old.get("parent_external_key") if old else None,
            parent_after=new.get("parent_external_key") if new else None,
            classifications_before=old_classes,
            classifications_after=new_classes,
            status_before=old.get("status") if old else None,
            status_after=new.get("status") if new else None,
        )

    def _normalized_snapshot(self, release: EnterpriseCoreRelease) -> dict[str, Any]:
        snapshot = copy.deepcopy(release.snapshot_json or {})
        snapshot.setdefault("tenant", {"id": self.tenant_id})
        snapshot.setdefault("workspaces", [])
        snapshot.setdefault("strategic_objectives", [])
        snapshot.setdefault("classifications", [])
        snapshot.setdefault("links", [])
        by_id = {item.get("id"): item for item in snapshot["workspaces"] if item.get("id") is not None}
        for item in snapshot["workspaces"]:
            item["technical_id"] = item.get("id")
            item["external_key"] = str(item.get("external_key") or "").strip().upper()
            item["parent_external_key"] = item.get("parent_external_key") or (
                by_id.get(item.get("parent_id"), {}).get("external_key") if item.get("parent_id") is not None else None
            )
            if item["parent_external_key"]:
                item["parent_external_key"] = str(item["parent_external_key"]).strip().upper()
            item["workspace_type_code"] = _configuration_code(
                str(item.get("workspace_type_code") or item.get("workspace_type") or "")
            )
            item["workspace_type"] = item["workspace_type_code"]
            item["description"] = str(item.get("description") or "")
            item["responsible_user_id"] = item.get("responsible_user_id")
            item["sort_order"] = int(item.get("sort_order") or 0)
            item["status"] = str(item.get("status") or "draft").strip().lower()
        normalized_classifications: list[dict[str, Any]] = []
        for item in snapshot["classifications"]:
            workspace_key = item.get("workspace_external_key")
            if not workspace_key and item.get("workspace_id") in by_id:
                workspace_key = by_id[item["workspace_id"]].get("external_key")
            normalized_classifications.append(
                {
                    "workspace_id": item.get("workspace_id"),
                    "workspace_external_key": str(workspace_key or "").strip().upper(),
                    "category_set_code": _configuration_code(str(item.get("category_set_code") or "")),
                    "category_item_code": _configuration_code(str(item.get("category_item_code") or "")),
                }
            )
        snapshot["classifications"] = normalized_classifications
        return snapshot

    def _materialize_snapshot(self, raw_snapshot: dict[str, Any]) -> dict[str, Any]:
        holder = EnterpriseCoreRelease(
            id=-1,
            tenant_id=self.tenant_id,
            release_code="MATERIALIZE",
            release_name="Materialize",
            revision_number=0,
            state="draft",
            source_hash="",
            canonical_hash="",
            content_fingerprint="",
            base_content_fingerprint="",
            snapshot_json=raw_snapshot,
            workspace_count=0,
            objective_count=0,
            classification_count=0,
            link_count=0,
            created_by_user_id=self.actor_id,
        )
        snapshot = self._normalized_snapshot(holder)
        desired = snapshot["workspaces"]
        existing = self.repository.workspaces()
        existing_by_key = {str(item.external_key or "").upper(): item for item in existing}
        original_codes = {item.id: item.record_code for item in existing}
        desired_record_codes = {item["record_code"] for item in desired}
        for workspace in existing:
            workspace.parent_id = None
            workspace.record_code = f"__REVISION_{workspace.id}"
        self.db.flush()

        physical_by_key: dict[str, EnterpriseWorkspace] = {}
        for item in desired:
            key = item["external_key"]
            workspace = existing_by_key.get(key)
            if workspace is None:
                workspace = EnterpriseWorkspace(
                    tenant_id=self.tenant_id,
                    parent_id=None,
                    workspace_type_code=item["workspace_type_code"],
                    code=item["code"],
                    external_key=key,
                    record_code=f"__NEW_REVISION_{uuid.uuid4().hex}",
                    name=item["name"],
                    status=item["status"],
                    defaults_json={},
                    sort_order=item["sort_order"],
                    version=1,
                    created_by_user_id=self.actor_id,
                )
                self.db.add(workspace)
                self.db.flush()
            physical_by_key[key] = workspace

        now = utc_now()
        for item in desired:
            workspace = physical_by_key[item["external_key"]]
            workspace.parent_id = (
                physical_by_key[item["parent_external_key"]].id if item.get("parent_external_key") else None
            )
            workspace.workspace_type_code = item["workspace_type_code"]
            workspace.code = item["code"]
            workspace.external_key = item["external_key"]
            workspace.record_code = item["record_code"]
            workspace.name = item["name"]
            workspace.status = item["status"]
            workspace.sort_order = item["sort_order"]
            defaults = dict(workspace.defaults_json or {})
            metadata = dict(defaults.get("_enterprise") or {})
            metadata.update(
                {
                    "description": item.get("description", ""),
                    "responsible_user_id": item.get("responsible_user_id"),
                    "external_key": item["external_key"],
                }
            )
            defaults["_enterprise"] = metadata
            workspace.defaults_json = defaults
            workspace.version += 1
            workspace.updated_at = now
        desired_keys = set(physical_by_key)
        for key, workspace in existing_by_key.items():
            if key in desired_keys:
                continue
            workspace.status = "archived"
            original = original_codes[workspace.id]
            workspace.record_code = original if original not in desired_record_codes else f"ARCHIVED.{workspace.id}"
            workspace.version += 1
            workspace.updated_at = now
        self.db.flush()

        id_by_key = {key: workspace.id for key, workspace in physical_by_key.items()}
        self.db.execute(
            delete(EnterpriseWorkspaceClassification).where(
                EnterpriseWorkspaceClassification.tenant_id == self.tenant_id
            )
        )
        for item in snapshot["classifications"]:
            workspace_id = id_by_key[item["workspace_external_key"]]
            self.db.add(
                EnterpriseWorkspaceClassification(
                    tenant_id=self.tenant_id,
                    workspace_id=workspace_id,
                    category_set_code=item["category_set_code"],
                    category_item_code=item["category_item_code"],
                    created_by_user_id=self.actor_id,
                )
            )
        self.db.execute(delete(EnterpriseWorkspaceLink).where(EnterpriseWorkspaceLink.tenant_id == self.tenant_id))
        for item in snapshot["links"]:
            source_key = item.get("source_workspace_external_key") or item.get("source_external_key")
            target_key = item.get("target_workspace_external_key") or item.get("target_external_key")
            self.db.add(
                EnterpriseWorkspaceLink(
                    tenant_id=self.tenant_id,
                    source_workspace_id=id_by_key[source_key],
                    target_workspace_id=id_by_key[target_key],
                    relationship_type=item["relationship_type"],
                    valid_from=item.get("valid_from"),
                    valid_to=item.get("valid_to"),
                    status=item.get("status", "active"),
                    created_by_user_id=self.actor_id,
                )
            )
        self.db.flush()
        return snapshot

    def _refresh_draft(
        self,
        release: EnterpriseCoreRelease,
        snapshot: dict[str, Any],
        *,
        operation: str,
        workspace_key: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        release.snapshot_json = snapshot
        release.workspace_count = len(snapshot["workspaces"])
        release.objective_count = len(snapshot["strategic_objectives"])
        release.classification_count = len(snapshot["classifications"])
        release.link_count = len(snapshot["links"])
        release.content_fingerprint = _snapshot_hash(release.release_code, snapshot)
        release.diff_hash = self._diff(release).diff_hash
        release.validation_json = {}
        release.validated_at = None
        release.validated_by_user_id = None
        release.validated_draft_hash = None
        release.approved_at = None
        release.approved_by_user_id = None
        release.approved_draft_hash = None
        release.approved_diff_hash = None
        release.updated_at = utc_now()
        metadata = {
            "release": release.release_code,
            "previous_release": release.previous_release_id,
            "workspace_key": workspace_key,
            "draft_hash": release.content_fingerprint,
            "diff_hash": release.diff_hash,
            "operation": operation,
            "result": "modified",
        }
        metadata.update(extra or {})
        self._event("enterprise_structure.revision_modified", release, metadata)

    def _classifications_by_workspace(
        self,
        snapshot: dict[str, Any],
    ) -> dict[str, list[RevisionClassificationIn]]:
        output: dict[str, list[RevisionClassificationIn]] = {}
        for item in snapshot.get("classifications", []):
            output.setdefault(item["workspace_external_key"], []).append(
                RevisionClassificationIn(
                    category_set_code=item["category_set_code"],
                    category_item_code=item["category_item_code"],
                )
            )
        for values in output.values():
            values.sort(key=lambda item: (item.category_set_code, item.category_item_code))
        return output

    def _classification(
        self,
        workspace_key: str,
        item: RevisionClassificationIn,
    ) -> dict[str, Any]:
        return {
            "workspace_id": None,
            "workspace_external_key": workspace_key.strip().upper(),
            "category_set_code": _configuration_code(item.category_set_code),
            "category_item_code": _configuration_code(item.category_item_code),
        }

    def _ensure_allowed_child(self, parent: dict[str, Any], child_type: str) -> None:
        type_code = _configuration_code(child_type)
        parent_type = self.repository.latest_configuration(
            "workspace_type", parent["workspace_type_code"], published_only=True
        )
        if parent_type is None or type_code not in parent_type.content_json.get("allowed_children", []):
            raise HTTPException(
                status_code=409,
                detail=f"{type_code} is not allowed below {parent['workspace_type_code']}",
            )

    def _workspace(self, workspaces: list[dict[str, Any]], workspace_key: str | None) -> dict[str, Any]:
        normalized = str(workspace_key or "").strip().upper()
        selected = next((item for item in workspaces if item["external_key"] == normalized), None)
        if selected is None:
            raise HTTPException(status_code=404, detail="Draft workspace not found")
        return selected

    def _descendants(self, workspaces: list[dict[str, Any]], workspace_key: str) -> list[dict[str, Any]]:
        descendants: list[dict[str, Any]] = []
        pending = [workspace_key]
        visited = {workspace_key}
        while pending:
            parent_key = pending.pop()
            children = [
                item
                for item in workspaces
                if item.get("parent_external_key") == parent_key and item["external_key"] not in visited
            ]
            descendants.extend(children)
            child_keys = {item["external_key"] for item in children}
            visited.update(child_keys)
            pending.extend(child_keys)
        return descendants

    def _next_record_code(
        self,
        workspaces: list[dict[str, Any]],
        parent: dict[str, Any],
        *,
        exclude_key: str | None = None,
    ) -> str:
        sibling_codes = [
            item["record_code"]
            for item in workspaces
            if item.get("parent_external_key") == parent["external_key"] and item["external_key"] != exclude_key
        ]
        sequences = []
        for code in sibling_codes:
            try:
                sequences.append(int(str(code).split(".")[-1]))
            except ValueError:
                continue
        segment = str(max(sequences, default=0) + 1).zfill(2)
        return f"{parent['record_code']}.{segment}"

    def _next_sort_order(self, workspaces: list[dict[str, Any]], parent_key: str) -> int:
        return (
            max(
                (
                    int(item.get("sort_order") or 0)
                    for item in workspaces
                    if item.get("parent_external_key") == parent_key
                ),
                default=0,
            )
            + 10
        )

    def _generated_code(self, type_code: str, workspaces: list[dict[str, Any]]) -> str:
        prefix = "".join(part[:3].upper() for part in type_code.split("-"))[:8] or "WS"
        existing = {item["code"] for item in workspaces}
        sequence = 1
        while f"{prefix}-{sequence:03d}" in existing:
            sequence += 1
        return f"{prefix}-{sequence:03d}"

    def _valid_status_transition(self, before: str, after: str) -> bool:
        allowed = {
            "draft": {"draft", "active", "inactive", "archived"},
            "active": {"active", "inactive", "archived"},
            "inactive": {"inactive", "active", "archived"},
            "archived": {"archived"},
        }
        return after in allowed.get(before, set())

    def _ensure_hash_match(
        self,
        release: EnterpriseCoreRelease,
        diff: RevisionDiffOut,
        draft_hash: str,
        diff_hash: str,
    ) -> None:
        if draft_hash != release.content_fingerprint or diff_hash != diff.diff_hash:
            raise HTTPException(
                status_code=409,
                detail={
                    "reason": "HASH_MISMATCH",
                    "observed_draft_hash": release.content_fingerprint,
                    "observed_diff_hash": diff.diff_hash,
                },
            )

    def _draft(self, release_id: int) -> EnterpriseCoreRelease:
        release = self._release(release_id)
        if release.state != "draft":
            raise HTTPException(status_code=409, detail="Published releases are immutable; create a new revision")
        return release

    def _release(self, release_id: int | None) -> EnterpriseCoreRelease:
        if release_id is None:
            raise HTTPException(status_code=404, detail="CORE release not found")
        release = self.repository.core_release(release_id)
        if release is None:
            raise HTTPException(status_code=404, detail="CORE release not found")
        if release.state not in REVISION_STATES:
            raise HTTPException(status_code=409, detail="Unsupported CORE release state")
        return release

    def _next_release_code(self, revision_number: int) -> str:
        base = f"ES-PYP-CORE-REV-{revision_number:03d}"
        candidate = base
        suffix = 1
        while self.db.scalar(
            select(EnterpriseCoreRelease.id).where(
                EnterpriseCoreRelease.tenant_id == self.tenant_id,
                EnterpriseCoreRelease.release_code == candidate,
            )
        ):
            suffix += 1
            candidate = f"{base}-{suffix}"
        return candidate

    def _actor_email(self, user_id: int | None) -> str | None:
        if user_id is None:
            return None
        return self.db.scalar(select(UserAccount.email).where(UserAccount.id == user_id))

    def _event(self, event_type: str, release: EnterpriseCoreRelease, metadata: dict[str, Any]) -> None:
        self.db.add(
            SecurityEvent(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                event_type=event_type,
                outcome="success",
                target_type="EnterpriseCoreRelease",
                target_id=release.id,
                metadata_json={"tenant_id": self.tenant_id, "release_id": release.id, **metadata},
            )
        )


def core_release_out(db: Session, release: EnterpriseCoreRelease) -> CoreReleaseOut:
    actor = (
        db.scalar(select(UserAccount.email).where(UserAccount.id == release.published_by_user_id))
        if release.published_by_user_id
        else None
    )
    return CoreReleaseOut(
        id=release.id,
        release_code=release.release_code,
        release_name=release.release_name,
        revision_number=release.revision_number,
        state=release.state,
        previous_release_id=release.previous_release_id,
        source_hash=release.source_hash,
        canonical_hash=release.canonical_hash,
        content_fingerprint=release.content_fingerprint,
        workspace_count=release.workspace_count,
        objective_count=release.objective_count,
        classification_count=release.classification_count,
        link_count=release.link_count,
        published_at=release.published_at,
        published_by=actor,
    )


def _snapshot_hash(release_code: str, snapshot: dict[str, Any]) -> str:
    return _hash({"release_code": release_code, "snapshot": snapshot})


def _hash(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def _classification_pairs(items: list[RevisionClassificationIn]) -> list[tuple[str, str]]:
    return sorted((item.category_set_code, item.category_item_code) for item in items)


def _record_code_key(value: str) -> tuple[int, ...]:
    return tuple(int(part) if part.isdigit() else 999999 for part in str(value).split("."))


def _configuration_code(value: str) -> str:
    code = re.sub(r"-+", "-", value.strip().lower().replace("_", "-").replace(" ", "-"))
    if not code:
        raise HTTPException(status_code=422, detail="Code is required")
    return code


def _required(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise HTTPException(status_code=422, detail=f"{label} is required")
    return normalized
