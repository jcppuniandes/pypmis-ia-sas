"""Governed Procurement catalog publication using the existing ADMIN store."""

from copy import deepcopy
from datetime import datetime

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select

from app.core.time import utc_now
from app.domain.models import AdminConfiguration, EnterpriseWorkspace
from app.modules.basic_data.service import _hash
from app.modules.operational_context.models import OperationalContextCommand
from app.modules.procurement_foundation.permissions import ACTIONS
from app.modules.procurement_foundation.policy import DEFAULT_PROFILE, PROFILE_KIND, ProcurementProfile


class ProcurementProfilesMixin:
    def _profile(self, identity, *, lock=False):
        self._require_schema()
        stmt = select(AdminConfiguration).where(
            AdminConfiguration.id == identity,
            AdminConfiguration.tenant_id == self.tenant_id,
            AdminConfiguration.kind == PROFILE_KIND,
        )
        row = self.db.scalar(stmt.with_for_update().execution_options(populate_existing=True) if lock else stmt)
        if row is None:
            self._error(404, "PROCUREMENT_PROFILE_NOT_FOUND")
        return row

    def _procurement_profile(self, project):
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
            elif body["inherit_to_descendants"] and scope["workspace_id"] in self._workspace_paths.get(
                project.id, set()
            ):
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
            self._error(409, "PROCUREMENT_PROFILE_AMBIGUOUS")
        latest = max(top, key=lambda row: row.revision)
        if _hash(latest.content_json) != latest.content_hash:
            self._error(409, "PROCUREMENT_PROFILE_HASH_MISMATCH")
        return latest

    def _pinned_profile(self, row):
        profile = self._profile(row.configuration_id)
        if (
            profile.status != "published"
            or profile.content_hash != row.configuration_hash
            or _hash(profile.content_json) != row.configuration_hash
        ):
            self._error(409, "PROCUREMENT_PINNED_PROFILE_INVALID")
        return profile.content_json

    def _validate_profile(self, value):
        try:
            profile = ProcurementProfile.model_validate(value)
            start, end = self._instant(profile.effective_from), self._instant(profile.effective_to)
            if profile.effective_from == "" or profile.effective_to == "" or (start and end and end <= start):
                raise ValueError("Invalid effective window")
            for role, actions in profile.permission_profiles.items():
                if not role or len(role) > 120 or not actions or set(actions) - set(ACTIONS):
                    raise ValueError("Invalid restrictive permission profile")
        except (ValueError, TypeError, ValidationError) as exc:
            raise HTTPException(422, detail={"code": "PROCUREMENT_PROFILE_INVALID"}) from exc
        identity = profile.scope.workspace_id
        if (
            identity is not None
            and self.db.scalar(
                select(EnterpriseWorkspace.id).where(
                    EnterpriseWorkspace.tenant_id == self.tenant_id,
                    EnterpriseWorkspace.id == identity,
                )
            )
            is None
        ):
            self._error(422, "PROCUREMENT_PROFILE_WORKSPACE_INVALID")
        return profile.model_dump(mode="json")

    def profiles(self):
        self._require_schema()
        self._permission("admin.configure")
        rows = self.db.scalars(
            select(AdminConfiguration)
            .where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == PROFILE_KIND,
            )
            .order_by(AdminConfiguration.code, AdminConfiguration.revision.desc())
        ).all()
        return {
            "items": [self._profile_out(row) for row in rows],
            "default_content": deepcopy(DEFAULT_PROFILE),
            "allowed_actions": self.allowed_actions(),
        }

    def _admin_command(self, action, payload, key, apply, *, identity=None, expected=None):
        self._require_schema()
        self._permission("admin.publish" if action == "publish" else "admin.configure")
        return self._command(
            f"procurement.profile.{action}",
            key,
            {"id": identity, "expected": expected, **payload.model_dump(mode="json")},
            apply,
        )

    def create_profile(self, payload, key):
        def apply():
            content = self._validate_profile(payload.content_json)
            code = self._code(payload.code)
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
                self._error(409, "PROCUREMENT_PROFILE_CODE_EXISTS")
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

        return self._admin_command("create", payload, key, apply)

    def update_profile(self, identity, payload, expected, key):
        def apply():
            row = self._profile(identity, lock=True)
            self._version(row.version, expected)
            if row.status != "draft":
                self._error(409, "PROCUREMENT_PROFILE_IMMUTABLE")
            content = self._validate_profile(payload.content_json)
            row.name, row.content_json, row.content_hash = payload.name, content, _hash(content)
            row.version, row.updated_at = row.version + 1, utc_now()
            self.db.flush()
            self._event("profile.updated", row.id, {"reason": payload.reason, "version": row.version})
            return self._profile_out(row)

        return self._admin_command("update", payload, key, apply, identity=identity, expected=expected)

    def publish_profile(self, identity, payload, expected, key):
        def apply():
            row = self._profile(identity, lock=True)
            self._version(row.version, expected)
            if row.status != "draft":
                self._error(409, "PROCUREMENT_PROFILE_IMMUTABLE")
            self._validate_profile(row.content_json)
            if _hash(row.content_json) != row.content_hash:
                self._error(409, "PROCUREMENT_PROFILE_HASH_MISMATCH")
            receipts = self.db.execute(
                select(
                    OperationalContextCommand.actor_id,
                    OperationalContextCommand.result_json["version"].as_integer(),
                ).where(
                    OperationalContextCommand.tenant_id == self.tenant_id,
                    OperationalContextCommand.command_type == "procurement.profile.update",
                    OperationalContextCommand.result_json["id"].as_integer() == row.id,
                )
            ).all()
            if {version for _, version in receipts} != set(range(2, row.version + 1)):
                self._error(409, "PROCUREMENT_PROFILE_EDITOR_PROVENANCE_REQUIRED")
            if self.actor_id in {row.created_by_user_id, *(actor for actor, _ in receipts)}:
                self._error(403, "PROCUREMENT_PROFILE_PUBLICATION_SOD")
            contenders = self.db.scalars(
                select(AdminConfiguration).where(
                    AdminConfiguration.tenant_id == self.tenant_id,
                    AdminConfiguration.kind == PROFILE_KIND,
                    AdminConfiguration.status == "published",
                    AdminConfiguration.code != row.code,
                )
            ).all()
            body = row.content_json
            start = self._instant(body["effective_from"]) or datetime.min
            end = self._instant(body["effective_to"]) or datetime.max
            for candidate in contenders:
                other = candidate.content_json
                if (
                    body["scope"] == other["scope"]
                    and start < (self._instant(other["effective_to"]) or datetime.max)
                    and end > (self._instant(other["effective_from"]) or datetime.min)
                ):
                    self._error(409, "PROCUREMENT_PROFILE_EFFECTIVE_SCOPE_CONFLICT")
            row.status, row.published_at, row.updated_at, row.version = (
                "published",
                utc_now(),
                utc_now(),
                row.version + 1,
            )
            self.db.flush()
            self._event("profile.published", row.id, {"reason": payload.reason, "hash": row.content_hash})
            return self._profile_out(row)

        return self._admin_command("publish", payload, key, apply, identity=identity, expected=expected)

    def successor_profile(self, identity, payload, expected, key):
        def apply():
            old = self._profile(identity, lock=True)
            self._version(old.version, expected)
            if old.status != "published":
                self._error(409, "PROCUREMENT_PUBLISHED_PROFILE_SUCCESSOR_REQUIRED")
            maximum = self.db.scalar(
                select(func.max(AdminConfiguration.revision)).where(
                    AdminConfiguration.tenant_id == self.tenant_id,
                    AdminConfiguration.kind == PROFILE_KIND,
                    AdminConfiguration.code == old.code,
                )
            )
            if maximum != old.revision:
                self._error(409, "PROCUREMENT_PROFILE_SUCCESSOR_EXISTS")
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
            self._event("profile.successor_created", row.id, {"reason": payload.reason, "supersedes_id": old.id})
            return self._profile_out(row)

        return self._admin_command("successor", payload, key, apply, identity=identity, expected=expected)
