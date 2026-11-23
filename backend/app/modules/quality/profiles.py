"""Quality Management profile lifecycle over the shared administrative store."""

from copy import deepcopy
from datetime import datetime

from pydantic import ValidationError
from sqlalchemy import func, select

from app.core.time import utc_now
from app.domain.models import AdminConfiguration, EnterpriseWorkspace
from app.modules.basic_data.service import _hash
from app.modules.operational_context.models import OperationalContextCommand
from app.modules.quality.policy import DEFAULT_PROFILE, PROFILE_KIND, QualityManagementProfile


class QualityProfilesMixin:
    def _profile(self, identity, *, lock=False):
        self._require_schema()
        query = select(AdminConfiguration).where(
            AdminConfiguration.id == identity,
            AdminConfiguration.tenant_id == self.tenant_id,
            AdminConfiguration.kind == PROFILE_KIND,
        )
        row = self.db.scalar(query.with_for_update().execution_options(populate_existing=True) if lock else query)
        if row is None:
            self._error(404, "QUALITY_PROFILE_NOT_FOUND")
        return row

    def _quality_profile(self, project):
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
            scope = body["scope"]
            if scope["type"] == "tenant":
                rank = 0
            elif scope["workspace_id"] == project.id:
                rank = 100
            elif body["inherit_to_descendants"] and scope["workspace_id"] in self._workspace_paths[project.id]:
                rank = 50
            else:
                continue
            start, end = self._instant(body["effective_from"]), self._instant(body["effective_to"])
            if (start and now < start) or (end and now >= end):
                continue
            candidates.append((rank, row))
        if not candidates:
            return None
        priority = max(rank for rank, _ in candidates)
        top = [row for rank, row in candidates if rank == priority]
        if len({row.code for row in top}) != 1:
            self._error(409, "QUALITY_PROFILE_AMBIGUOUS")
        chosen = max(top, key=lambda row: row.revision)
        if _hash(chosen.content_json) != chosen.content_hash:
            self._error(409, "QUALITY_PROFILE_HASH_MISMATCH")
        return chosen

    def _pinned_profile(self, row):
        profile = self._profile(row.configuration_id)
        if (
            profile.status != "published"
            or profile.content_hash != row.configuration_hash
            or _hash(profile.content_json) != row.configuration_hash
        ):
            self._error(409, "QUALITY_PINNED_PROFILE_INVALID")
        return profile.content_json

    def _validate_profile(self, content):
        try:
            profile = QualityManagementProfile.model_validate(content)
            start, end = self._instant(profile.effective_from), self._instant(profile.effective_to)
        except (ValueError, TypeError, ValidationError):
            self._error(422, "QUALITY_PROFILE_INVALID")
        if any(
            value is not None and instant is None
            for value, instant in (
                (profile.effective_from, start),
                (profile.effective_to, end),
            )
        ) or (start and end and end <= start):
            self._error(422, "QUALITY_PROFILE_WINDOW_INVALID")
        target = profile.scope.workspace_id
        if (
            target
            and self.db.scalar(
                select(EnterpriseWorkspace.id).where(
                    EnterpriseWorkspace.tenant_id == self.tenant_id,
                    EnterpriseWorkspace.id == target,
                )
            )
            is None
        ):
            self._error(422, "QUALITY_PROFILE_WORKSPACE_INVALID")
        return profile.model_dump(mode="json")

    def profiles(self):
        self._require_schema()
        self._permission("admin.configure")
        items = self.db.scalars(
            select(AdminConfiguration)
            .where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == PROFILE_KIND,
            )
            .order_by(AdminConfiguration.code, AdminConfiguration.revision.desc())
        )
        return {
            "items": [self._profile_out(item) for item in items],
            "default_content": deepcopy(DEFAULT_PROFILE),
            "allowed_actions": self.allowed_actions(),
        }

    def _profile_command(self, action, payload, key, apply, identity=None, expected=None):
        self._require_schema()
        self._permission("admin.publish" if action == "publish" else "admin.configure")
        return self._command(
            f"quality.profile.{action}",
            key,
            {"id": identity, "expected": expected, **payload.model_dump(mode="json")},
            apply,
        )

    def create_profile(self, payload, key):
        def apply():
            content = self._validate_profile(payload.content_json)
            code = payload.code.upper()
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
                self._error(409, "QUALITY_PROFILE_CODE_EXISTS")
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
            self._event("profile.created", row.id, {"reason": payload.reason, "hash": row.content_hash})
            return self._profile_out(row)

        return self._profile_command("create", payload, key, apply)

    def update_profile(self, identity, payload, expected, key):
        def apply():
            row = self._profile(identity, lock=True)
            self._version(row.version, expected)
            if row.status != "draft":
                self._error(409, "QUALITY_PROFILE_IMMUTABLE")
            content = self._validate_profile(payload.content_json)
            row.name, row.content_json, row.content_hash = payload.name, content, _hash(content)
            row.version, row.updated_at = row.version + 1, utc_now()
            self.db.flush()
            self._event("profile.updated", row.id, {"reason": payload.reason, "version": row.version})
            return self._profile_out(row)

        return self._profile_command("update", payload, key, apply, identity, expected)

    def publish_profile(self, identity, payload, expected, key):
        def apply():
            row = self._profile(identity, lock=True)
            self._version(row.version, expected)
            if row.status != "draft":
                self._error(409, "QUALITY_PROFILE_IMMUTABLE")
            self._validate_profile(row.content_json)
            if _hash(row.content_json) != row.content_hash:
                self._error(409, "QUALITY_PROFILE_HASH_MISMATCH")
            edit_receipts = self.db.execute(
                select(
                    OperationalContextCommand.actor_id,
                    OperationalContextCommand.result_json["version"].as_integer(),
                ).where(
                    OperationalContextCommand.tenant_id == self.tenant_id,
                    OperationalContextCommand.command_type == "quality.profile.update",
                    OperationalContextCommand.result_json["id"].as_integer() == row.id,
                )
            ).all()
            if {version for _, version in edit_receipts} != set(range(2, row.version + 1)):
                self._error(409, "QUALITY_PROFILE_EDITOR_PROVENANCE_REQUIRED")
            if self.actor_id in {row.created_by_user_id, *(actor for actor, _ in edit_receipts)}:
                self._error(403, "QUALITY_PROFILE_PUBLICATION_SOD")
            scope, start, end = (
                row.content_json["scope"],
                self._instant(row.content_json["effective_from"]) or datetime.min,
                self._instant(row.content_json["effective_to"]) or datetime.max,
            )
            for contender in self.db.scalars(
                select(AdminConfiguration).where(
                    AdminConfiguration.tenant_id == self.tenant_id,
                    AdminConfiguration.kind == PROFILE_KIND,
                    AdminConfiguration.status == "published",
                    AdminConfiguration.code != row.code,
                )
            ):
                other = contender.content_json
                if (
                    scope == other["scope"]
                    and start < (self._instant(other["effective_to"]) or datetime.max)
                    and end > (self._instant(other["effective_from"]) or datetime.min)
                ):
                    self._error(409, "QUALITY_PROFILE_EFFECTIVE_SCOPE_CONFLICT")
            row.status, row.published_at, row.updated_at, row.version = (
                "published",
                utc_now(),
                utc_now(),
                row.version + 1,
            )
            self.db.flush()
            self._event("profile.published", row.id, {"reason": payload.reason, "hash": row.content_hash})
            return self._profile_out(row)

        return self._profile_command("publish", payload, key, apply, identity, expected)

    def successor_profile(self, identity, payload, expected, key):
        def apply():
            old = self._profile(identity, lock=True)
            self._version(old.version, expected)
            latest = self.db.scalar(
                select(func.max(AdminConfiguration.revision)).where(
                    AdminConfiguration.tenant_id == self.tenant_id,
                    AdminConfiguration.kind == PROFILE_KIND,
                    AdminConfiguration.code == old.code,
                )
            )
            if old.status != "published" or latest != old.revision:
                self._error(409, "QUALITY_PROFILE_SUCCESSOR_NOT_ALLOWED")
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
            self._event("profile.successor", row.id, {"reason": payload.reason, "prior_id": old.id})
            return self._profile_out(row)

        return self._profile_command("successor", payload, key, apply, identity, expected)
