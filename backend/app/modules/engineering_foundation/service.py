"""O2A technical authority; writes run through the O1A scoped command ledger."""

from copy import deepcopy

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select

from app.core.time import utc_now
from app.domain.models import AdminConfiguration, EnterpriseWorkspace, SecurityEvent, WorkspaceModuleSetting
from app.modules.basic_data.service import _hash, _json
from app.modules.engineering_foundation.integration import EngineeringIntegrationMixin
from app.modules.engineering_foundation.models import (
    EngineeringDeliverable,
    EngineeringDesignPackage,
    EngineeringHistory,
    EngineeringInterface,
    EngineeringRelease,
    EngineeringReview,
    EngineeringReviewComment,
    EngineeringRevision,
)
from app.modules.engineering_foundation.permissions import ACTIONS, require_engineering_schema
from app.modules.engineering_foundation.policy import (
    DEFAULT_PROFILE,
    PROFILE_KIND,
    REVIEW_ACTIONS,
    REVISION_EDITABLE,
    REVISION_TERMINAL,
    EngineeringProfile,
    normalized_code,
    release_status,
    revision_code,
    validity_end,
)
from app.modules.enterprise_structure.permissions import require_enterprise_permission
from app.modules.operational_context.models import OperationalContextCommand
from app.modules.scope_foundation.service import ScopeFoundationService


class EngineeringFoundationService(EngineeringIntegrationMixin, ScopeFoundationService):
    """Core service; concrete router composes schema and CDE adapters."""

    def _require_schema(self):
        if not self.__dict__.get("_engineering_schema_confirmed"):
            require_engineering_schema(self.db)
            self._engineering_schema_confirmed = True

    def _project(self, workspace_id):
        self._require_schema()
        project = super()._project(workspace_id)
        if project.status.lower() != "active":
            self._error(409, "ENGINEERING_ACTIVE_PROJECT_REQUIRED")
        configured = self.__dict__.setdefault("_engineering_enabled_cache", {})
        if workspace_id not in configured:
            keys = {"engineering", "engineering-manager"}
            defaults = dict(project.defaults_json or {})
            metadata = {**defaults, **dict(defaults.get("_enterprise") or {})}
            settings = dict(
                self.db.execute(
                    select(WorkspaceModuleSetting.module_key, WorkspaceModuleSetting.enabled).where(
                        WorkspaceModuleSetting.tenant_id == self.tenant_id,
                        WorkspaceModuleSetting.workspace_id == workspace_id,
                        WorkspaceModuleSetting.module_key.in_(keys),
                    )
                ).all()
            )
            configured[workspace_id] = not any(value is False for value in settings.values()) and bool(
                keys & set(metadata.get("enabled_modules") or []) or any(settings.values())
            )
        if not configured[workspace_id]:
            self._error(409, "ENGINEERING_MODULE_NOT_ENABLED")
        return project

    def _permission(self, action, workspace=None):
        if self.access_context is None:
            return  # Trusted internal composition only; router always supplies permission context.
        if action not in self._permission_contexts:
            self._permission_contexts[action] = require_enterprise_permission(
                self.db, self.tenant_id, self.actor_id, f"engineering.{action}", bootstrap=False
            )
        access = self._permission_contexts[action]
        if action.startswith("admin.") and not access.organization_wide:
            self._error(403, "ENGINEERING_ADMIN_ORGANIZATION_SCOPE_REQUIRED")
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

    def _event(self, action, identity, metadata, *, outcome="success"):
        self.db.add(
            SecurityEvent(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                event_type=f"engineering.{action}",
                outcome=outcome,
                target_type="EngineeringFoundation",
                target_id=identity,
                metadata_json=deepcopy(metadata),
            )
        )

    def _record(self, row, event, reason, *, changed=False):
        if changed:
            row.version += 1
        self.db.flush()
        snapshot = self._out(row)
        self.db.add(
            EngineeringHistory(
                **self._base(row.project_workspace_id),
                entity_type=type(row).__name__,
                entity_id=row.id,
                entity_version=row.version,
                event_type=event,
                snapshot_json=snapshot,
                reason=reason,
            )
        )
        self._event(event, row.id, {"project_workspace_id": row.project_workspace_id, "version": row.version})
        return snapshot

    def _write(self, command, workspace, payload, key, apply, identity=None, expected=None):
        self._project(workspace)  # Check current Project scope before any receipt replay.

        def checked():
            try:
                return apply()
            except (ValueError, OverflowError) as error:
                raise HTTPException(422, detail={"code": str(error) or "ENGINEERING_VALUE_INVALID"}) from error

        result = self._command(
            f"engineering.{command}",
            key,
            {"project": workspace, "id": identity, "expected": expected, **payload.model_dump(mode="json")},
            checked,
        )
        return self._redact(workspace, result)

    def _scoped(self, model, workspace):
        return select(model).where(model.tenant_id == self.tenant_id, model.project_workspace_id == workspace)

    def _get(self, model, workspace_id, record_id, *, lock=False):
        stmt = self._scoped(model, workspace_id).where(model.id == record_id)
        row = self.db.scalar(stmt.with_for_update().execution_options(populate_existing=True) if lock else stmt)
        if row is None:
            self._error(404, "ENGINEERING_RECORD_NOT_FOUND")
        return row

    def _read_project(self, workspace):
        project = self._project(workspace)
        self._permission("read", project)
        return project

    def _engineering_profile(self, project):
        now = utc_now()
        candidates = []
        for row in self.db.scalars(
            select(AdminConfiguration).where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == PROFILE_KIND,
                AdminConfiguration.status == "published",
            )
        ):
            body = row.content_json
            start, end = self._instant(body["effective_from"]), self._instant(body["effective_to"])
            if (start and now < start) or (end and now >= end):
                continue
            scope = body["scope"]
            if scope["type"] == "tenant":
                priority = 0
            elif scope["workspace_id"] == project.id:
                priority = 100
            elif body["inherit_to_descendants"] and scope["workspace_id"] in self._workspace_paths.get(
                project.id, set()
            ):
                priority = 50
            else:
                continue
            candidates.append((priority, row))
        if not candidates:
            return None
        maximum = max(priority for priority, _ in candidates)
        rows = [row for priority, row in candidates if priority == maximum]
        if len({row.code for row in rows}) != 1:
            self._error(409, "ENGINEERING_PROFILE_AMBIGUOUS")
        return max(rows, key=lambda row: row.revision)

    def _ready(self, workspace, action):
        project = self._project(workspace)
        self._permission(action, project)
        operational = self._operational()
        operational._operable(workspace)
        operational._policy_ready(project, operational._effective_profile(project))
        profile = self._engineering_profile(project)
        if profile is None:
            self._error(409, "ENGINEERING_PUBLISHED_PROFILE_REQUIRED")
        return project, profile

    def _pinned_profile(self, row):
        profile = self._profile(row.configuration_id)
        if (
            profile.status != "published"
            or profile.content_hash != row.configuration_hash
            or _hash(profile.content_json) != row.configuration_hash
        ):
            self._error(409, "ENGINEERING_PINNED_PROFILE_INVALID")
        return profile.content_json

    def configuration(self, workspace):
        project = self._read_project(workspace)
        profile = self._engineering_profile(project)
        return {
            "profile": self._profile_out(profile) if profile else None,
            "allowed_actions": self.allowed_actions(project),
        }

    def _profile(self, identity, *, lock=False):
        self._require_schema()
        stmt = select(AdminConfiguration).where(
            AdminConfiguration.id == identity,
            AdminConfiguration.tenant_id == self.tenant_id,
            AdminConfiguration.kind == PROFILE_KIND,
        )
        row = self.db.scalar(stmt.with_for_update().execution_options(populate_existing=True) if lock else stmt)
        if row is None:
            self._error(404, "ENGINEERING_PROFILE_NOT_FOUND")
        return row

    def _validate_profile(self, value):
        try:
            profile = EngineeringProfile.model_validate(value)
            start, end = self._instant(profile.effective_from), self._instant(profile.effective_to)
            if profile.effective_from == "" or profile.effective_to == "" or start and end and end <= start:
                raise ValueError("window")
        except (ValueError, TypeError, ValidationError) as error:
            raise HTTPException(422, detail={"code": "ENGINEERING_PROFILE_INVALID"}) from error
        identity = profile.scope.workspace_id
        if (
            identity is not None
            and self.db.scalar(
                select(EnterpriseWorkspace.id).where(
                    EnterpriseWorkspace.id == identity, EnterpriseWorkspace.tenant_id == self.tenant_id
                )
            )
            is None
        ):
            self._error(422, "ENGINEERING_PROFILE_WORKSPACE_INVALID")
        return profile.model_dump(mode="json")

    def profiles(self):
        self._require_schema()
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

    def _admin_command(self, action, payload, key, apply, *, identity=None, expected=None):
        self._require_schema()
        self._permission("admin.publish" if action == "publish" else "admin.configure")
        return self._command(
            f"engineering.profile.{action}",
            key,
            {"id": identity, "expected": expected, **payload.model_dump(mode="json")},
            apply,
        )

    def create_profile(self, payload, key):
        def apply():
            content = self._validate_profile(payload.content_json)
            try:
                code = normalized_code(payload.code)
            except ValueError:
                self._error(422, "ENGINEERING_CODE_INVALID")
            if (
                self.db.scalar(
                    select(AdminConfiguration.id)
                    .where(
                        AdminConfiguration.tenant_id == self.tenant_id,
                        AdminConfiguration.kind == PROFILE_KIND,
                        AdminConfiguration.code == code,
                    )
                    .limit(1)
                )
                is not None
            ):
                self._error(409, "ENGINEERING_PROFILE_CODE_EXISTS")
            row = AdminConfiguration(
                tenant_id=self.tenant_id,
                kind=PROFILE_KIND,
                code=code,
                name=payload.name,
                status="draft",
                revision=1,
                version=1,
                content_json=content,
                content_hash=_hash(content),
                created_by_user_id=self.actor_id,
            )
            self.db.add(row)
            self.db.flush()
            self._event("ENGINEERING_PROFILE_CREATED", row.id, {"reason": payload.reason, "hash": row.content_hash})
            return self._profile_out(row)

        return self._admin_command("create", payload, key, apply)

    def update_profile(self, identity, payload, expected, key):
        def apply():
            row = self._profile(identity, lock=True)
            self._version(row.version, expected)
            if row.status != "draft":
                self._error(409, "ENGINEERING_PROFILE_IMMUTABLE")
            content = self._validate_profile(payload.content_json)
            row.name, row.content_json, row.content_hash = payload.name, content, _hash(content)
            row.version, row.updated_at = row.version + 1, utc_now()
            self.db.flush()
            self._event("ENGINEERING_PROFILE_UPDATED", row.id, {"reason": payload.reason, "version": row.version})
            return self._profile_out(row)

        return self._admin_command("update", payload, key, apply, identity=identity, expected=expected)

    def publish_profile(self, identity, payload, expected, key):
        def apply():
            row = self._profile(identity, lock=True)
            self._version(row.version, expected)
            if row.status != "draft":
                self._error(409, "ENGINEERING_PROFILE_IMMUTABLE")
            self._validate_profile(row.content_json)
            if _hash(row.content_json) != row.content_hash:
                self._error(409, "ENGINEERING_PROFILE_HASH_MISMATCH")
            editors = {row.created_by_user_id}
            if row.version > 1:
                result = self.db.execute(
                    select(
                        OperationalContextCommand.actor_id,
                        OperationalContextCommand.result_json["version"].as_integer(),
                    ).where(
                        OperationalContextCommand.tenant_id == self.tenant_id,
                        OperationalContextCommand.command_type == "engineering.profile.update",
                        OperationalContextCommand.result_json["id"].as_integer() == row.id,
                    )
                ).all()
                if {version for _, version in result} != set(range(2, row.version + 1)):
                    self._error(409, "ENGINEERING_PROFILE_EDITOR_PROVENANCE_REQUIRED")
                editors.update(actor for actor, _ in result)
            if self.actor_id in editors:
                self._error(403, "ENGINEERING_PROFILE_PUBLICATION_SOD")
            row.status, row.published_at, row.updated_at, row.version = (
                "published",
                utc_now(),
                utc_now(),
                row.version + 1,
            )
            self.db.flush()
            self._event("ENGINEERING_PROFILE_PUBLISHED", row.id, {"reason": payload.reason, "hash": row.content_hash})
            return self._profile_out(row)

        return self._admin_command("publish", payload, key, apply, identity=identity, expected=expected)

    def successor_profile(self, identity, payload, expected, key):
        def apply():
            old = self._profile(identity, lock=True)
            self._version(old.version, expected)
            if old.status != "published":
                self._error(409, "ENGINEERING_PUBLISHED_PROFILE_SUCCESSOR_REQUIRED")
            max_revision = self.db.scalar(
                select(func.max(AdminConfiguration.revision)).where(
                    AdminConfiguration.tenant_id == self.tenant_id,
                    AdminConfiguration.kind == PROFILE_KIND,
                    AdminConfiguration.code == old.code,
                )
            )
            if max_revision != old.revision:
                self._error(409, "ENGINEERING_PROFILE_SUCCESSOR_ALREADY_EXISTS")
            row = AdminConfiguration(
                tenant_id=self.tenant_id,
                kind=PROFILE_KIND,
                code=old.code,
                name=old.name,
                status="draft",
                revision=old.revision + 1,
                version=1,
                content_json=deepcopy(old.content_json),
                content_hash=old.content_hash,
                created_by_user_id=self.actor_id,
            )
            self.db.add(row)
            self.db.flush()
            self._event(
                "ENGINEERING_PROFILE_SUCCESSOR_CREATED", row.id, {"reason": payload.reason, "supersedes_id": old.id}
            )
            return self._profile_out(row)

        return self._admin_command("successor", payload, key, apply, identity=identity, expected=expected)

    @staticmethod
    def _same_document(pin, current):
        return pin == current

    def _document_visible(self, workspace, reference):
        if not reference:
            return False
        key = (workspace, reference.get("document_id"), reference.get("attachment_id"))
        cache = self.__dict__.setdefault("_document_access_cache", {})
        if key not in cache:
            try:
                cache[key] = self._resolve_document(*key)
            except HTTPException as error:
                if error.status_code not in {403, 404, 409, 422}:
                    raise
                cache[key] = None
        resolved = cache[key]
        return bool(resolved and self._same_document(reference, resolved))

    def _redact(self, workspace, value):
        if isinstance(value, list):
            return [self._redact(workspace, item) for item in value]
        if not isinstance(value, dict):
            return value
        result = {key: self._redact(workspace, item) for key, item in value.items()}
        for key in ("document_ref_json", "document_reference"):
            if result.get(key) and not self._document_visible(workspace, result[key]):
                result[key] = {} if key == "document_ref_json" else None
                if "document_hash" in result:
                    result["document_hash"] = ""
                result["document_reference_restricted"] = True
        return result

    def _verified_document(self, row):
        pin = row.document_ref_json
        if not pin or not row.document_hash:
            self._error(409, "ENGINEERING_DOCUMENT_EVIDENCE_REQUIRED")
        document = self._resolve_document(row.project_workspace_id, pin["document_id"], pin["attachment_id"])
        if not self._same_document(pin, document) or document["sha256"] != row.document_hash:
            self._error(409, "ENGINEERING_DOCUMENT_PIN_STALE")
        return document

    def _page(self, stmt, model, *, limit, after_id):
        if not 1 <= limit <= 200 or after_id < 0:
            self._error(422, "ENGINEERING_PAGINATION_INVALID")
        rows = self.db.scalars(stmt.where(model.id > after_id).order_by(model.id).limit(limit + 1)).all()
        return rows[:limit], rows[limit - 1].id if len(rows) > limit else None

    def _latest_revision(self, workspace, deliverable_id):
        return self.db.scalar(
            self._scoped(EngineeringRevision, workspace)
            .where(EngineeringRevision.deliverable_id == deliverable_id)
            .order_by(EngineeringRevision.revision_sequence.desc())
            .limit(1)
        )

    def _effective_releases(self, workspace, deliverable_ids, as_of=None, known_at=None):
        if not deliverable_ids:
            return {}
        now = known_at or utc_now()
        as_of = as_of or now.date()
        first = (
            select(
                EngineeringRelease.id.label("release_id"),
                func.row_number()
                .over(
                    partition_by=EngineeringRelease.deliverable_id,
                    order_by=EngineeringRevision.revision_sequence.desc(),
                )
                .label("rank"),
            )
            .join(EngineeringRevision, EngineeringRevision.id == EngineeringRelease.revision_id)
            .where(
                EngineeringRelease.tenant_id == self.tenant_id,
                EngineeringRelease.project_workspace_id == workspace,
                EngineeringRelease.deliverable_id.in_(deliverable_ids),
                EngineeringRelease.effective_date <= as_of,
                EngineeringRelease.released_at <= now,
            )
            .subquery()
        )
        return {
            r.deliverable_id: r
            for r in self.db.scalars(
                select(EngineeringRelease)
                .join(first, first.c.release_id == EngineeringRelease.id)
                .where(first.c.rank == 1)
            )
        }

    def _deliverable_out(self, row, latest, effective, *, detailed):
        status = latest.status if latest else "DRAFT"
        if latest and effective and latest.id == effective.revision_id:
            status = "IFC_RELEASED"
        return {
            **self._out(row),
            "current_revision_id": latest.id if latest else None,
            "current_ifc_revision_id": effective.revision_id if effective else None,
            "status": status,
            "approval_status": latest.status if latest and latest.status in REVISION_TERMINAL else "NOT_APPROVED",
            "ifc_release_status": "CURRENT_IFC" if effective else "NOT_RELEASED",
            "document_linked": bool(latest and latest.document_ref_json),
            "document_reference": latest.document_ref_json if detailed and latest else None,
            "actual_issue_date": effective.effective_date.isoformat() if effective else None,
        }

    def deliverables(self, workspace, *, limit=50, after_id=0):
        project = self._read_project(workspace)
        rows, next_cursor = self._page(
            self._scoped(EngineeringDeliverable, workspace), EngineeringDeliverable, limit=limit, after_id=after_id
        )
        ids = [row.id for row in rows]
        newest = {}
        if ids:
            latest = (
                select(
                    EngineeringRevision.deliverable_id,
                    func.max(EngineeringRevision.revision_sequence).label("sequence"),
                )
                .where(
                    EngineeringRevision.tenant_id == self.tenant_id,
                    EngineeringRevision.project_workspace_id == workspace,
                    EngineeringRevision.deliverable_id.in_(ids),
                )
                .group_by(EngineeringRevision.deliverable_id)
                .subquery()
            )
            newest = {
                r.deliverable_id: r
                for r in self.db.scalars(
                    select(EngineeringRevision).join(
                        latest,
                        (latest.c.deliverable_id == EngineeringRevision.deliverable_id)
                        & (latest.c.sequence == EngineeringRevision.revision_sequence),
                    )
                )
            }
        effective = self._effective_releases(workspace, ids)
        return {
            "items": [
                self._deliverable_out(row, newest.get(row.id), effective.get(row.id), detailed=False) for row in rows
            ],
            "next_cursor": next_cursor,
            "allowed_actions": self.allowed_actions(project),
        }

    def deliverable(self, workspace, identity):
        self._read_project(workspace)
        row = self._get(EngineeringDeliverable, workspace, identity)
        return self._redact(
            workspace,
            self._deliverable_out(
                row,
                self._latest_revision(workspace, identity),
                self._effective_releases(workspace, [identity]).get(identity),
                detailed=True,
            ),
        )

    def save_deliverable(self, workspace, payload, key, identity=None, expected=None):
        action = "deliverable.edit" if identity is not None else "deliverable.create"
        self._permission(action, self._project(workspace))

        def apply():
            _, profile = self._ready(workspace, action)
            row = self._get(EngineeringDeliverable, workspace, identity, lock=True) if identity is not None else None
            if row is not None:
                self._version(row.version, expected)
                catalog = self._pinned_profile(row)
            else:
                catalog = profile.content_json
                if _hash(catalog) != profile.content_hash:
                    self._error(409, "ENGINEERING_PROFILE_HASH_MISMATCH")
            values = payload.model_dump(exclude={"reason"})
            for key_name in ("code", "discipline", "deliverable_type"):
                values[key_name] = normalized_code(values[key_name])
            if values["discipline"] not in catalog["disciplines"]:
                self._error(422, "ENGINEERING_DISCIPLINE_NOT_CONFIGURED")
            if values["deliverable_type"] not in catalog["deliverable_types"]:
                self._error(422, "ENGINEERING_DELIVERABLE_TYPE_NOT_CONFIGURED")
            values.update(
                updated_by=self.actor_id,
                updated_at=utc_now(),
            )
            if row is None:
                if values["design_package_id"]:
                    self._require_open_package(workspace, values["design_package_id"])
                row = EngineeringDeliverable(
                    **self._base(workspace),
                    **values,
                    configuration_id=profile.id,
                    configuration_hash=profile.content_hash,
                )
                self.db.add(row)
                self._record(row, "ENGINEERING_DELIVERABLE_CREATED", payload.reason)
            else:
                if values["code"] != row.code:
                    self._error(409, "ENGINEERING_DELIVERABLE_CODE_IMMUTABLE")
                if values["design_package_id"] != row.design_package_id:
                    for package_id in {values["design_package_id"], row.design_package_id} - {None}:
                        self._require_open_package(workspace, package_id)
                latest = self._latest_revision(workspace, identity)
                if latest and (
                    values["discipline"] != row.discipline or values["deliverable_type"] != row.deliverable_type
                ):
                    self._error(409, "ENGINEERING_DELIVERABLE_CLASSIFICATION_HAS_REVISIONS")
                for name, value in values.items():
                    setattr(row, name, value)
                self._record(row, "ENGINEERING_DELIVERABLE_UPDATED", payload.reason, changed=True)
            return self._deliverable_out(
                row,
                self._latest_revision(workspace, row.id),
                self._effective_releases(workspace, [row.id]).get(row.id),
                detailed=True,
            )

        return self._write(action, workspace, payload, key, apply, identity, expected)

    def _latest_review(self, workspace, identity, *, lock=False):
        stmt = (
            self._scoped(EngineeringReview, workspace)
            .where(EngineeringReview.revision_id == identity)
            .order_by(EngineeringReview.round_number.desc())
            .limit(1)
        )
        return self.db.scalar(stmt.with_for_update().execution_options(populate_existing=True) if lock else stmt)

    def _release(self, workspace, identity):
        return self.db.scalar(
            self._scoped(EngineeringRelease, workspace).where(EngineeringRelease.revision_id == identity)
        )

    def _revision_out(self, row, *, effective=None, release=None, review=None, supplied=False):
        if not supplied:
            effective = self._effective_releases(row.project_workspace_id, [row.deliverable_id]).get(row.deliverable_id)
            release = self._release(row.project_workspace_id, row.id)
            review = self._latest_review(row.project_workspace_id, row.id)
        state = release_status(row.id, release, effective, utc_now().date())
        return {
            **self._out(row),
            "document_linked": bool(row.document_ref_json),
            "ifc_release_status": state,
            "actual_issue_date": release.effective_date.isoformat()
            if state in {"CURRENT_IFC", "SUPERSEDED_IFC"}
            else None,
            "release": self._out(release) if release else None,
            "review_status": review.status if review else "NOT_SUBMITTED",
            "review_id": review.id if review else None,
        }

    def revisions(self, workspace, deliverable_id, *, limit=50, after_id=0):
        project = self._read_project(workspace)
        self._get(EngineeringDeliverable, workspace, deliverable_id)
        rows, next_cursor = self._page(
            self._scoped(EngineeringRevision, workspace).where(EngineeringRevision.deliverable_id == deliverable_id),
            EngineeringRevision,
            limit=limit,
            after_id=after_id,
        )
        ids = [row.id for row in rows]
        releases = {
            r.revision_id: r
            for r in self.db.scalars(
                self._scoped(EngineeringRelease, workspace).where(EngineeringRelease.revision_id.in_(ids))
            )
        }
        reviews = {}
        for r in self.db.scalars(
            self._scoped(EngineeringReview, workspace)
            .where(EngineeringReview.revision_id.in_(ids))
            .order_by(EngineeringReview.round_number)
        ):
            reviews[r.revision_id] = r
        effective = self._effective_releases(workspace, [deliverable_id]).get(deliverable_id)
        items = [
            self._revision_out(
                row, effective=effective, release=releases.get(row.id), review=reviews.get(row.id), supplied=True
            )
            for row in rows
        ]
        return {
            "items": self._redact(workspace, items),
            "next_cursor": next_cursor,
            "allowed_actions": self.allowed_actions(project),
        }

    def revision(self, workspace, identity):
        self._read_project(workspace)
        return self._redact(workspace, self._revision_out(self._get(EngineeringRevision, workspace, identity)))

    @staticmethod
    def _material(row):
        return _json(
            {
                "tenant_id": row.tenant_id,
                "project_workspace_id": row.project_workspace_id,
                "deliverable_id": row.deliverable_id,
                "revision_code": row.revision_code,
                "revision_sequence": row.revision_sequence,
                "supersedes_revision_id": row.supersedes_revision_id,
                "purpose_of_issue": row.purpose_of_issue,
                "description": row.description,
                "planned_issue_date": row.planned_issue_date,
                "forecast_issue_date": row.forecast_issue_date,
                "document_ref_json": row.document_ref_json,
                "document_hash": row.document_hash,
                "configuration_id": row.configuration_id,
                "configuration_hash": row.configuration_hash,
                "prepared_by": row.prepared_by,
            }
        )

    def _revision_values(self, payload, profile):
        values = payload.model_dump(exclude={"reason"})
        values["revision_code"] = revision_code(payload.revision_code, profile["revision_code_rule"])
        values["purpose_of_issue"] = normalized_code(payload.purpose_of_issue)
        if values["purpose_of_issue"] not in profile["purposes_of_issue"]:
            self._error(422, "ENGINEERING_PURPOSE_NOT_CONFIGURED")
        return values

    def _new_revision(self, workspace, deliverable, payload, profile, previous=None):
        if _hash(profile.content_json) != profile.content_hash:
            self._error(409, "ENGINEERING_PROFILE_HASH_MISMATCH")
        row = EngineeringRevision(
            **self._base(workspace),
            **self._revision_values(payload, profile.content_json),
            deliverable_id=deliverable.id,
            revision_sequence=previous.revision_sequence + 1 if previous else 1,
            supersedes_revision_id=previous.id if previous else None,
            status="DRAFT",
            prepared_by=self.actor_id,
            updated_by=self.actor_id,
            updated_at=utc_now(),
            document_ref_json={},
            document_hash="",
            configuration_id=profile.id,
            configuration_hash=profile.content_hash,
        )
        row.content_hash = _hash(self._material(row))
        self.db.add(row)
        self._record(row, "ENGINEERING_REVISION_CREATED", payload.reason)
        if previous:
            self._record(row, "ENGINEERING_REVISION_SUCCESSOR_CREATED", payload.reason)
        return self._revision_out(row)

    def save_revision(self, workspace, deliverable_id, payload, key):
        self._permission("revision.create", self._project(workspace))

        def apply():
            _, profile = self._ready(workspace, "revision.create")
            deliverable = self._get(EngineeringDeliverable, workspace, deliverable_id, lock=True)
            if self._latest_revision(workspace, deliverable_id):
                self._error(409, "ENGINEERING_REVISION_EXPLICIT_SUCCESSOR_REQUIRED")
            return self._new_revision(workspace, deliverable, payload, profile)

        return self._write("revision.create", workspace, payload, key, apply, deliverable_id)

    def update_revision(self, workspace, identity, payload, expected, key):
        self._permission("revision.edit", self._project(workspace))

        def apply():
            self._ready(workspace, "revision.edit")
            row = self._get(EngineeringRevision, workspace, identity, lock=True)
            self._version(row.version, expected)
            self._require_revision_editable(row)
            values = self._revision_values(payload, self._pinned_profile(row))
            if values["revision_code"] != row.revision_code:
                self._error(409, "ENGINEERING_REVISION_CODE_IMMUTABLE")
            for name, value in values.items():
                setattr(row, name, value)
            row.updated_by, row.updated_at = self.actor_id, utc_now()
            row.content_hash = _hash(self._material(row))
            self._record(row, "ENGINEERING_REVISION_UPDATED", payload.reason, changed=True)
            return self._revision_out(row)

        return self._write("revision.edit", workspace, payload, key, apply, identity, expected)

    def successor_revision(self, workspace, identity, payload, expected, key):
        self._permission("revision.supersede", self._project(workspace))

        def apply():
            _, profile = self._ready(workspace, "revision.supersede")
            old = self._get(EngineeringRevision, workspace, identity, lock=True)
            self._version(old.version, expected)
            deliverable = self._get(EngineeringDeliverable, workspace, old.deliverable_id, lock=True)
            if old.status not in REVISION_TERMINAL or self._latest_revision(workspace, deliverable.id).id != old.id:
                self._error(409, "ENGINEERING_TERMINAL_LATEST_REVISION_REQUIRED")
            return self._new_revision(workspace, deliverable, payload, profile, previous=old)

        return self._write("revision.supersede", workspace, payload, key, apply, identity, expected)

    def _require_revision_editable(self, row):
        if row.status not in REVISION_EDITABLE:
            self._error(409, "ENGINEERING_REVISION_NOT_EDITABLE_CREATE_SUCCESSOR")

    def link_document(self, workspace, identity, payload, expected, key):
        self._permission("document.link", self._project(workspace))

        def apply():
            self._ready(workspace, "document.link")
            row = self._get(EngineeringRevision, workspace, identity, lock=True)
            self._version(row.version, expected)
            self._require_revision_editable(row)
            reference = self._resolve_document(workspace, payload.document_id, payload.attachment_id)
            row.document_ref_json, row.document_hash = reference, reference["sha256"]
            row.updated_by, row.updated_at = self.actor_id, utc_now()
            row.content_hash = _hash(self._material(row))
            self._record(row, "ENGINEERING_DOCUMENT_LINKED", payload.reason, changed=True)
            return self._revision_out(row)

        return self._write("document.link", workspace, payload, key, apply, identity, expected)

    def reviews(self, workspace, identity):
        project = self._read_project(workspace)
        row = self._get(EngineeringRevision, workspace, identity)
        reviews = self.db.scalars(
            self._scoped(EngineeringReview, workspace)
            .where(EngineeringReview.revision_id == identity)
            .order_by(EngineeringReview.round_number)
        ).all()
        by_review = {}
        for comment in self.db.scalars(
            self._scoped(EngineeringReviewComment, workspace)
            .where(EngineeringReviewComment.revision_id == identity)
            .order_by(EngineeringReviewComment.id)
        ):
            by_review.setdefault(comment.review_id, []).append(self._out(comment))
        return {
            "items": [{**self._out(review), "comments": by_review.get(review.id, [])} for review in reviews],
            "allowed_actions": self.allowed_actions(project),
            "revision_version": row.version,
        }

    def _authors(self, row):
        return {
            row.prepared_by,
            row.updated_by,
            *self.db.scalars(
                select(EngineeringHistory.created_by).where(
                    EngineeringHistory.tenant_id == self.tenant_id,
                    EngineeringHistory.project_workspace_id == row.project_workspace_id,
                    EngineeringHistory.entity_type == "EngineeringRevision",
                    EngineeringHistory.entity_id == row.id,
                    EngineeringHistory.event_type.in_(("ENGINEERING_REVISION_UPDATED", "ENGINEERING_DOCUMENT_LINKED")),
                )
            ),
        }

    def _independent(self, row, *actors):
        if self.actor_id in self._authors(row) or self.actor_id in actors:
            self._error(403, "ENGINEERING_SEPARATION_OF_DUTIES")

    def _review_hash(self, row, review):
        if row.content_hash != _hash(self._material(row)) or review.submitted_hash != row.content_hash:
            self._error(409, "ENGINEERING_SUBMITTED_CONTENT_CHANGED")

    def _closed_comments(self, row):
        if (
            self.db.scalar(
                select(EngineeringReviewComment.id)
                .where(
                    EngineeringReviewComment.tenant_id == self.tenant_id,
                    EngineeringReviewComment.project_workspace_id == row.project_workspace_id,
                    EngineeringReviewComment.revision_id == row.id,
                    EngineeringReviewComment.status != "CLOSED",
                )
                .limit(1)
            )
            is not None
        ):
            self._error(409, "ENGINEERING_REVIEW_COMMENTS_OPEN")

    def review_action(self, workspace, identity, payload, expected, key):
        action = payload.action
        permission = REVIEW_ACTIONS[action]
        self._permission(permission, self._project(workspace))

        def apply():
            self._ready(workspace, permission)
            row = self._get(EngineeringRevision, workspace, identity, lock=True)
            self._version(row.version, expected)
            review = self._latest_review(workspace, identity, lock=True)
            profile = self._pinned_profile(row)
            now = utc_now()
            if action == "submit":
                self._require_revision_editable(row)
                if row.status == "CHANGES_REQUESTED":
                    self._closed_comments(row)
                    if (
                        not review
                        or review.decision != "REVISE_AND_RESUBMIT"
                        or review.submitted_hash == row.content_hash
                    ):
                        self._error(409, "ENGINEERING_REVISED_CONTENT_REQUIRED")
                if profile["review_rules"]["require_document_before_submit"] or row.document_ref_json:
                    self._verified_document(row)
                review = EngineeringReview(
                    **self._base(workspace),
                    revision_id=row.id,
                    round_number=review.round_number + 1 if review else 1,
                    status="SUBMITTED",
                    submitted_hash=row.content_hash,
                )
                self.db.add(review)
                self._record(review, "ENGINEERING_REVIEW_ROUND_CREATED", payload.reason)
                row.status = "UNDER_REVIEW"
                row.checked_by = row.checked_at = None
                self._record(row, "ENGINEERING_SUBMITTED_FOR_REVIEW", payload.reason, changed=True)
                return self._revision_out(row)

            if review is None:
                self._error(409, "ENGINEERING_REVIEW_NOT_SUBMITTED")
            self._independent(row)
            if action == "close":
                if review.status not in {"APPROVED", "REJECTED"} or row.status not in REVISION_TERMINAL:
                    self._error(409, "ENGINEERING_REVIEW_DECISION_REQUIRED")
                review.status, review.closed_by, review.closed_at = "CLOSED", self.actor_id, now
                self._record(review, "ENGINEERING_REVIEW_CLOSED", payload.reason, changed=True)
                return self._revision_out(row)
            if row.status != "UNDER_REVIEW":
                self._error(409, "ENGINEERING_REVISION_NOT_UNDER_REVIEW")
            self._review_hash(row, review)

            review_changed = True
            if action == "start" and review.status == "SUBMITTED":
                review.status, review.reviewer_id = "UNDER_REVIEW", self.actor_id
                event = "ENGINEERING_REVIEW_STARTED"
            elif action == "request_changes" and review.status in {"UNDER_REVIEW", "COMMENTS_ISSUED"}:
                row.status = "CHANGES_REQUESTED"
                review.status = review.decision = "REVISE_AND_RESUBMIT"
                review.decision_by, review.decision_at = self.actor_id, now
                event = "ENGINEERING_REVISION_CHANGES_REQUESTED"
            elif action == "accept" and review.status in {"UNDER_REVIEW", "COMMENTS_ISSUED"}:
                self._closed_comments(row)
                review.status, review.reviewer_id, review.reviewed_at = "ACCEPTED", self.actor_id, now
                event = "ENGINEERING_REVIEW_COMPLETED"
            elif action == "check" and review.status == "ACCEPTED" and row.checked_by is None:
                self._closed_comments(row)
                row.checked_by, row.checked_at = self.actor_id, now
                review_changed = False
                event = "ENGINEERING_TECHNICAL_CHECK_COMPLETED"
            elif action == "approve" and review.status == "ACCEPTED":
                self._closed_comments(row)
                if profile["review_rules"]["require_technical_check"] and row.checked_by is None:
                    self._error(409, "ENGINEERING_TECHNICAL_CHECK_REQUIRED")
                self._independent(row, row.checked_by, review.reviewer_id)
                if row.document_ref_json:
                    self._verified_document(row)
                row.status, row.approved_by, row.approved_at = "APPROVED", self.actor_id, now
                review.status = review.decision = "APPROVED"
                review.decision_by, review.decision_at = self.actor_id, now
                event = "ENGINEERING_APPROVED"
            elif action == "reject" and review.status in {"UNDER_REVIEW", "COMMENTS_ISSUED", "ACCEPTED"}:
                self._independent(row, row.checked_by, review.reviewer_id)
                row.status = "REJECTED"
                review.status = review.decision = "REJECTED"
                review.decision_by, review.decision_at = self.actor_id, now
                event = "ENGINEERING_REVISION_REJECTED"
            else:
                self._error(409, "ENGINEERING_REVIEW_TRANSITION_INVALID")
            # One flush of the revision before the terminal SQL guard takes
            # effect; do not bump version after persisting APPROVED/REJECTED.
            row.version += 1
            if review_changed:
                self._record(review, f"{event}_ROUND", payload.reason, changed=True)
            self._record(row, event, payload.reason)
            return self._revision_out(row)

        return self._write(f"review.{action}", workspace, payload, key, apply, identity, expected)

    def add_comment(self, workspace, identity, payload, expected, key):
        self._permission("review.comment", self._project(workspace))

        def apply():
            self._ready(workspace, "review.comment")
            row = self._get(EngineeringRevision, workspace, identity, lock=True)
            self._version(row.version, expected)
            self._independent(row)
            review = self._latest_review(workspace, identity, lock=True)
            if (
                row.status != "UNDER_REVIEW"
                or review is None
                or review.status not in {"UNDER_REVIEW", "COMMENTS_ISSUED"}
            ):
                self._error(409, "ENGINEERING_REVIEW_COMMENT_STAGE_INVALID")
            values = payload.model_dump(exclude={"reason"})
            values["discipline"] = normalized_code(payload.discipline)
            if values["discipline"] not in self._pinned_profile(row)["disciplines"]:
                self._error(422, "ENGINEERING_DISCIPLINE_NOT_CONFIGURED")
            values["category"] = normalized_code(payload.category)
            comment = EngineeringReviewComment(
                **self._base(workspace), review_id=review.id, revision_id=row.id, status="OPEN", **values
            )
            self.db.add(comment)
            if review.status != "COMMENTS_ISSUED":
                review.status = "COMMENTS_ISSUED"
                self._record(review, "ENGINEERING_REVIEW_COMMENTS_ISSUED", payload.reason, changed=True)
            self._record(comment, "ENGINEERING_REVIEW_COMMENT_CREATED", payload.reason)
            row.version += 1
            return {**self._out(comment), "revision_version": row.version}

        return self._write("review.comment", workspace, payload, key, apply, identity, expected)

    def comment_action(self, workspace, comment_id, payload, expected, key):
        action = payload.action
        permission = f"review.{action}"
        self._permission(permission, self._project(workspace))

        def apply():
            self._ready(workspace, permission)
            comment = self._get(EngineeringReviewComment, workspace, comment_id, lock=True)
            self._version(comment.version, expected)
            row = self._get(EngineeringRevision, workspace, comment.revision_id, lock=True)
            if row.status not in {"UNDER_REVIEW", "CHANGES_REQUESTED"}:
                self._error(409, "ENGINEERING_REVIEW_COMMENT_FROZEN")
            if action == "respond":
                if comment.status != "OPEN" or not payload.response:
                    self._error(409, "ENGINEERING_REVIEW_COMMENT_RESPONSE_REQUIRED")
                if self.actor_id not in self._authors(row) or self.actor_id == comment.created_by:
                    self._error(403, "ENGINEERING_COMMENT_RESPONSE_AUTHOR_REQUIRED")
                comment.response, comment.response_by, comment.response_at = payload.response, self.actor_id, utc_now()
                comment.status = "RESPONDED"
                event = "ENGINEERING_REVIEW_COMMENT_RESPONDED"
            else:
                self._independent(row, comment.response_by)
                if comment.status != "RESPONDED":
                    self._error(409, "ENGINEERING_REVIEW_COMMENT_RESPONSE_REQUIRED")
                comment.status, comment.closed_by, comment.closed_at = "CLOSED", self.actor_id, utc_now()
                event = "ENGINEERING_REVIEW_COMMENT_CLOSED"
            result = self._record(comment, event, payload.reason, changed=True)
            row.version += 1
            return {**result, "revision_version": row.version}

        return self._write(f"review.comment.{action}", workspace, payload, key, apply, comment_id, expected)

    def release_ifc(self, workspace, identity, payload, expected, key):
        self._permission("ifc.release", self._project(workspace))

        def apply():
            self._ready(workspace, "ifc.release")
            row = self._get(EngineeringRevision, workspace, identity, lock=True)
            self._version(row.version, expected)
            self._get(EngineeringDeliverable, workspace, row.deliverable_id, lock=True)
            if row.status != "APPROVED" or row.approved_at is None:
                self._error(409, "ENGINEERING_APPROVED_REVISION_REQUIRED")
            if self._latest_revision(workspace, row.deliverable_id).id != row.id:
                self._error(409, "ENGINEERING_CURRENT_REVISION_REQUIRED")
            if self._release(workspace, identity):
                self._error(409, "ENGINEERING_IFC_ALREADY_RELEASED")
            review = self._latest_review(workspace, identity)
            if review is None or review.status not in {"APPROVED", "CLOSED"} or review.decision != "APPROVED":
                self._error(409, "ENGINEERING_APPROVED_REVIEW_REQUIRED")
            self._review_hash(row, review)
            self._closed_comments(row)
            profile = self._pinned_profile(row)
            release_rules = profile["ifc_release_rules"]
            if profile["review_rules"]["require_technical_check"] and row.checked_by is None:
                self._error(409, "ENGINEERING_TECHNICAL_CHECK_REQUIRED")
            if row.purpose_of_issue not in release_rules["eligible_purposes"]:
                self._error(409, "ENGINEERING_IFC_PURPOSE_NOT_ELIGIBLE")
            self._independent(row, row.approved_by if release_rules["releaser_distinct_from_approver"] else None)
            document = self._verified_document(row)
            previous_date = self.db.scalar(
                select(func.max(EngineeringRelease.effective_date)).where(
                    EngineeringRelease.tenant_id == self.tenant_id,
                    EngineeringRelease.project_workspace_id == workspace,
                    EngineeringRelease.deliverable_id == row.deliverable_id,
                )
            )
            if payload.effective_date < row.approved_at.date() or (
                previous_date and payload.effective_date < previous_date
            ):
                self._error(422, "ENGINEERING_IFC_EFFECTIVE_DATE_BEFORE_APPROVAL_OR_PREDECESSOR")
            released_at = utc_now()
            snapshot = _json(
                {
                    "tenant_id": self.tenant_id,
                    "project_workspace_id": workspace,
                    "deliverable_id": row.deliverable_id,
                    "revision_id": row.id,
                    "revision_sequence": row.revision_sequence,
                    "revision_code": row.revision_code,
                    "revision_content_hash": row.content_hash,
                    "review_id": review.id,
                    "review_submitted_hash": review.submitted_hash,
                    "reviewed_by": review.reviewer_id,
                    "checked_by": row.checked_by,
                    "approved_by": row.approved_by,
                    "approved_at": row.approved_at,
                    "configuration_id": row.configuration_id,
                    "configuration_hash": row.configuration_hash,
                    "document_reference": document,
                    "document_hash": row.document_hash,
                    "released_by": self.actor_id,
                    "released_at": released_at,
                    "effective_date": payload.effective_date,
                    "valid_until": validity_end(
                        payload.effective_date, profile["readiness_evidence_rules"]["max_age_days"]
                    ),
                    "release_reference": payload.release_reference,
                }
            )
            release = EngineeringRelease(
                **self._base(workspace),
                revision_id=row.id,
                deliverable_id=row.deliverable_id,
                effective_date=payload.effective_date,
                released_at=released_at,
                released_by=self.actor_id,
                release_reference=payload.release_reference,
                release_hash=_hash(snapshot),
                snapshot_json=snapshot,
            )
            self.db.add(release)
            self._record(release, "ENGINEERING_IFC_RELEASED", payload.reason)
            if previous_date is not None:
                self._record(release, "ENGINEERING_REVISION_SUPERSEDED", payload.reason)
            self._record(release, "ENGINEERING_READINESS_EVIDENCE_PUBLISHED", payload.reason)
            return self._revision_out(row)

        return self._write("ifc.release", workspace, payload, key, apply, identity, expected)

    def _require_open_package(self, workspace, identity):
        row = self._get(EngineeringDesignPackage, workspace, identity, lock=True)
        if row.status not in {"DRAFT", "REVIEWED"}:
            self._error(409, "ENGINEERING_DESIGN_PACKAGE_MEMBERSHIP_FROZEN")
        return row

    def design_packages(self, workspace):
        project = self._read_project(workspace)
        return {
            "items": [self._out(row) for row in self._rows(EngineeringDesignPackage, workspace)],
            "allowed_actions": self.allowed_actions(project),
        }

    def save_design_package(self, workspace, payload, key, identity=None, expected=None):
        permission = "design_package.manage"
        self._permission(permission, self._project(workspace))

        def apply():
            self._ready(workspace, permission)
            values = payload.model_dump(exclude={"reason"})
            values["code"] = normalized_code(payload.code)
            values.update(updated_by=self.actor_id, updated_at=utc_now())
            if identity is None:
                row = EngineeringDesignPackage(**self._base(workspace), **values, status="DRAFT")
                self.db.add(row)
                return self._record(row, "ENGINEERING_DESIGN_PACKAGE_CREATED", payload.reason)
            row = self._get(EngineeringDesignPackage, workspace, identity, lock=True)
            self._version(row.version, expected)
            if row.status != "DRAFT" or row.code != values["code"]:
                self._error(409, "ENGINEERING_DESIGN_PACKAGE_NOT_EDITABLE")
            for name, value in values.items():
                setattr(row, name, value)
            return self._record(row, "ENGINEERING_DESIGN_PACKAGE_UPDATED", payload.reason, changed=True)

        return self._write(
            f"design_package.{'edit' if identity else 'create'}", workspace, payload, key, apply, identity, expected
        )

    def design_package_action(self, workspace, identity, payload, expected, key):
        permission = "design_package.manage"
        self._permission(permission, self._project(workspace))

        def apply():
            self._ready(workspace, permission)
            row = self._get(EngineeringDesignPackage, workspace, identity, lock=True)
            self._version(row.version, expected)
            transition = (row.status, payload.action)
            if transition == ("DRAFT", "review"):
                state = "REVIEWED"
            elif transition == ("REVIEWED", "issue"):
                if (
                    self.db.scalar(
                        self._scoped(EngineeringDeliverable, workspace)
                        .where(EngineeringDeliverable.design_package_id == identity)
                        .limit(1)
                    )
                    is None
                ):
                    self._error(409, "ENGINEERING_DESIGN_PACKAGE_MEMBERS_REQUIRED")
                state = "ISSUED"
            elif transition in {("DRAFT", "cancel"), ("REVIEWED", "cancel")}:
                state = "CANCELLED"
            else:
                self._error(409, "ENGINEERING_DESIGN_PACKAGE_TRANSITION_INVALID")
            row.status, row.updated_by, row.updated_at = state, self.actor_id, utc_now()
            return self._record(row, f"ENGINEERING_DESIGN_PACKAGE_{state}", payload.reason, changed=True)

        return self._write(f"design_package.{payload.action}", workspace, payload, key, apply, identity, expected)

    def interfaces(self, workspace):
        project = self._read_project(workspace)
        return {
            "items": [self._out(row) for row in self._rows(EngineeringInterface, workspace)],
            "allowed_actions": self.allowed_actions(project),
            "technical_query_authority": "DEFERRED_REFERENCE_ONLY",
        }

    def save_interface(self, workspace, payload, key):
        permission = "interface.manage"
        self._permission(permission, self._project(workspace))

        def apply():
            self._ready(workspace, permission)
            if payload.deliverable_id is not None:
                self._get(EngineeringDeliverable, workspace, payload.deliverable_id)
            values = payload.model_dump(exclude={"reason", "code"})
            row = EngineeringInterface(
                **self._base(workspace),
                **values,
                code=normalized_code(payload.code),
                status="OPEN",
                updated_by=self.actor_id,
                updated_at=utc_now(),
            )
            self.db.add(row)
            return self._record(row, "ENGINEERING_INTERFACE_CREATED", payload.reason)

        return self._write("interface.create", workspace, payload, key, apply)

    def interface_action(self, workspace, identity, payload, expected, key):
        permission = "interface.manage"
        self._permission(permission, self._project(workspace))

        def apply():
            self._ready(workspace, permission)
            row = self._get(EngineeringInterface, workspace, identity, lock=True)
            self._version(row.version, expected)
            transition = (row.status, payload.action)
            if transition == ("OPEN", "resolve") and payload.resolution:
                row.status, row.resolution = "RESOLVED", payload.resolution
            elif transition == ("RESOLVED", "close"):
                row.status = "CLOSED"
            elif transition == ("OPEN", "cancel"):
                row.status = "CANCELLED"
            else:
                self._error(409, "ENGINEERING_INTERFACE_TRANSITION_INVALID")
            row.updated_by, row.updated_at = self.actor_id, utc_now()
            return self._record(row, f"ENGINEERING_INTERFACE_{row.status}", payload.reason, changed=True)

        return self._write(f"interface.{payload.action}", workspace, payload, key, apply, identity, expected)

    def history(self, workspace, *, limit=50, after_id=0):
        self._read_project(workspace)
        rows, next_cursor = self._page(
            self._scoped(EngineeringHistory, workspace), EngineeringHistory, limit=limit, after_id=after_id
        )
        return {"items": self._redact(workspace, [self._out(row) for row in rows]), "next_cursor": next_cursor}
