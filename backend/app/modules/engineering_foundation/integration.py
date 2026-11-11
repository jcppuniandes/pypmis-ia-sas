"""Reference-only Engineering integrations and as-of EPC evidence."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import inspect, or_, select

from app.api.v1._helpers import require_membership
from app.api.v1.routers.documents import _can_access_document
from app.core.time import utc_now
from app.domain.models import Document, DocumentAttachment
from app.modules.awp.models import CWA, WorkPackage
from app.modules.basic_data.service import _hash
from app.modules.cost_foundation.models import ControlAccount, CostCBS, CostCode
from app.modules.engineering_foundation.integration_models import EngineeringMapping
from app.modules.engineering_foundation.models import (
    EngineeringDeliverable,
    EngineeringDesignPackage,
    EngineeringHistory,
    EngineeringRelease,
    EngineeringRevision,
)
from app.modules.operational_context.models import OperationalProjectBinding
from app.modules.schedule_foundation.models import ScheduleVersion
from app.modules.scope_foundation.models import PlanItem, PlanItemScopeLink, ScopeItem

TargetKind = Literal[
    "EWP", "CWP", "IWP", "CWA", "SCOPE", "PLAN", "WBS", "ACTIVITY", "MILESTONE", "CBS", "COST_CODE", "CONTROL_ACCOUNT"
]
PACKAGE_KINDS = {"EWP", "CWP", "IWP"}
SCHEDULE_KINDS = {"WBS", "ACTIVITY", "MILESTONE"}
TARGET_MODELS = {
    "EWP": WorkPackage,
    "CWP": WorkPackage,
    "IWP": WorkPackage,
    "CWA": CWA,
    "SCOPE": ScopeItem,
    "PLAN": PlanItem,
    "CBS": CostCBS,
    "COST_CODE": CostCode,
    "CONTROL_ACCOUNT": ControlAccount,
}
PROVIDER_KEY = "ENGINEERING_READINESS_PROVIDER"
CDE_SOURCE = "PYPMIS_CDE"


class EngineeringMappingIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: Literal["SET", "REMOVE"] = "SET"
    target_kind: TargetKind
    target_id: int | None = Field(default=None, gt=0)
    schedule_version_id: int | None = Field(default=None, gt=0)
    external_id: str | None = Field(default=None, min_length=1, max_length=160)
    reason: str = Field(min_length=3, max_length=1000)

    @model_validator(mode="after")
    def typed_reference(self):
        if self.target_kind in SCHEDULE_KINDS:
            if self.target_id is not None or self.schedule_version_id is None or self.external_id is None:
                raise ValueError("ENGINEERING_SCHEDULE_REFERENCE_REQUIRED")
        elif self.target_id is None or self.schedule_version_id is not None or self.external_id is not None:
            raise ValueError("ENGINEERING_CANONICAL_TARGET_REQUIRED")
        return self


def _cutoff(as_of=None):
    return as_of or utc_now().date()


def _day_end(day):
    return datetime.combine(day, time.max)


def _observed_at(as_of=None):
    """Cutoffs are UTC; a date includes the day but never future knowledge."""
    if as_of is None:
        return utc_now()
    instant = as_of if isinstance(as_of, datetime) else _day_end(as_of)
    instant = instant.astimezone(UTC).replace(tzinfo=None) if instant.tzinfo else instant
    return min(instant, utc_now())


def _recorded_day(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return (value.astimezone(UTC) if value.tzinfo is not None else value).date()
    return value


def _scoped(model, tenant, workspace):
    return select(model).where(model.tenant_id == tenant, model.project_workspace_id == workspace)


def _cde_binding(db, tenant, workspace, *, instant=None):
    query = _scoped(OperationalProjectBinding, tenant, workspace).where(
        OperationalProjectBinding.legacy_project_id.is_not(None)
    )
    if instant is None:
        query = query.where(
            OperationalProjectBinding.status == "ACTIVE",
            OperationalProjectBinding.effective_to.is_(None),
            OperationalProjectBinding.effective_from <= utc_now(),
        )
    else:
        query = query.where(
            OperationalProjectBinding.effective_from <= instant,
            or_(
                OperationalProjectBinding.effective_to.is_(None),
                OperationalProjectBinding.effective_to > instant,
            ),
        )
    return db.scalar(query.order_by(OperationalProjectBinding.revision.desc()).limit(1))


def _cde_rows(db, tenant, legacy_project):
    return (
        select(Document, DocumentAttachment)
        .join(
            DocumentAttachment,
            (DocumentAttachment.document_id == Document.id)
            & (DocumentAttachment.tenant_id == Document.tenant_id)
            & (DocumentAttachment.project_id == Document.project_id),
        )
        .where(Document.tenant_id == tenant, Document.project_id == legacy_project)
    )


def _sha_eligible(attachment):
    return (
        len(attachment.sha256) == 64
        and all(character in "0123456789abcdef" for character in attachment.sha256)
        and attachment.scan_status in {"clean", "passed", "not_scanned"}
    )


def _cde_reference(binding, document, attachment):
    return {
        "source_system": CDE_SOURCE,
        "binding_id": binding.id,
        "binding_revision": binding.revision,
        "legacy_project_id": binding.legacy_project_id,
        "document_id": document.id,
        "document_number": document.document_number,
        "document_revision": document.revision,
        "document_version": document.version,
        "attachment_id": attachment.id,
        "attachment_version": attachment.version,
        "sha256": attachment.sha256,
    }


def _mapping_key(row):
    return row.target_kind, row.target_id, row.schedule_version_id, row.external_id


def _mapping_content(row):
    return {
        field: getattr(row, field)
        for field in (
            "tenant_id",
            "project_workspace_id",
            "revision_id",
            "design_package_id",
            "target_kind",
            "target_id",
            "schedule_version_id",
            "external_id",
            "action",
            "version",
            "target_snapshot_json",
            "reason",
        )
    }


def _effective(rows):
    current = {}
    for row in rows:
        key = (row.revision_id, row.design_package_id, *_mapping_key(row))
        prior = current.get(key)
        if prior is None or row.version > prior.version:
            current[key] = row
    return sorted((row for row in current.values() if row.action == "SET"), key=lambda row: row.id)


def _schedule_rows(version, kind):
    candidates = version.snapshot_json.get("wbs" if kind == "WBS" else "activities", [])
    if kind == "MILESTONE":
        return [row for row in candidates if "milestone" in str(row.get("activity_type", "")).lower()]
    return candidates


def _schedule_item(version, kind, external_id):
    return next(
        (item for item in _schedule_rows(version, kind) if str(item.get("external_id")) == external_id),
        None,
    )


def _target_summary(row, kind):
    return {
        "id": row.id,
        "target_id": row.id,
        "target_kind": kind,
        "schedule_version_id": None,
        "external_id": None,
        "code": getattr(row, "package_code", getattr(row, "scope_code", getattr(row, "code", ""))),
        "title": row.name,
        "target_version": row.version,
        "target_status": row.status,
        "area": getattr(row, "area", None),
        "cwa_id": getattr(row, "cwa_id", None),
        "target_content_hash": getattr(row, "content_hash", None),
    }


def _schedule_summary(version, item, kind):
    return {
        "id": str(item["external_id"]),
        "target_id": None,
        "target_kind": kind,
        "schedule_version_id": version.id,
        "external_id": str(item["external_id"]),
        "code": str(item.get("code") or item["external_id"]),
        "title": item.get("name") or item.get("title") or str(item["external_id"]),
        "schedule_register_id": version.register_id,
        "schedule_content_hash": version.content_hash,
        "source_system": "SCHEDULE_ACCEPTED_P6",
    }


def _not_future(created, as_of):
    day = _recorded_day(created)
    return day is not None and day <= as_of


def _effective_release(releases, revision_by_id, as_of, observed_at=None):
    instant = observed_at or _observed_at(as_of)
    eligible = [
        row
        for row in releases
        if row.effective_date <= as_of and row.released_at <= instant and row.revision_id in revision_by_id
    ]
    return max(eligible, key=lambda row: (revision_by_id[row.revision_id].revision_sequence, row.id), default=None)


def _release_date_value(value):
    try:
        return date.fromisoformat(value) if value else None
    except (TypeError, ValueError):
        return None


class EngineeringReadinessReader:
    """One request's scoped source records, shared by AWP assessments or reads."""

    def __init__(self, db, tenant, workspace, mappings):
        self.db, self.tenant, self.workspace = db, tenant, workspace
        self._request_observed_at = utc_now()
        self.mappings_by_package = defaultdict(list)
        for row in mappings:
            self.mappings_by_package[row.target_id].append(row)
        revision_ids = {row.revision_id for row in mappings}
        deliverable_ids = (
            set(
                db.scalars(
                    select(EngineeringRevision.deliverable_id).where(
                        EngineeringRevision.tenant_id == tenant,
                        EngineeringRevision.project_workspace_id == workspace,
                        EngineeringRevision.id.in_(revision_ids),
                    )
                )
            )
            if revision_ids
            else set()
        )
        self.revision_by_id = {}
        self.releases_by_deliverable = defaultdict(list)
        if deliverable_ids:
            for row in db.scalars(
                _scoped(EngineeringRevision, tenant, workspace).where(
                    EngineeringRevision.deliverable_id.in_(deliverable_ids)
                )
            ):
                self.revision_by_id[row.id] = row
            for row in db.scalars(
                _scoped(EngineeringRelease, tenant, workspace).where(
                    EngineeringRelease.deliverable_id.in_(deliverable_ids)
                )
            ):
                self.releases_by_deliverable[row.deliverable_id].append(row)
        self._bindings = {}
        self._references = {}

    def _reference_valid(self, revision, instant):
        """Verify CDE identity and hash without granting download or exposing its metadata."""
        expected = revision.document_ref_json or {}
        if expected.get("source_system") != CDE_SOURCE or expected.get("sha256") != revision.document_hash:
            return False
        if instant not in self._bindings:
            self._bindings[instant] = _cde_binding(self.db, self.tenant, self.workspace, instant=instant)
        binding = self._bindings[instant]
        if binding is None or binding.id != expected.get("binding_id"):
            return False
        key = (binding.id, expected.get("document_id"), expected.get("attachment_id"))
        if key not in self._references:
            pair = self.db.execute(
                _cde_rows(self.db, self.tenant, binding.legacy_project_id).where(
                    Document.id == key[1], DocumentAttachment.id == key[2]
                )
            ).one_or_none()
            self._references[key] = _cde_reference(binding, *pair) if pair and _sha_eligible(pair[1]) else None
        return expected == self._references[key]

    def evidence(self, package, as_of=None):
        instant = _observed_at(as_of) if as_of is not None else self._request_observed_at
        cutoff = instant.date()
        history = [
            row
            for row in self.mappings_by_package.get(package.id, [])
            if row.target_kind == package.package_type and row.created_at <= instant
        ]
        if not history:
            return None
        active = _effective(history)
        mappings_by_deliverable = defaultdict(list)
        reason_codes = set()
        if not active:
            reason_codes.add("ENGINEERING_NO_ACTIVE_MAPPING")
        for row in active:
            revision = self.revision_by_id.get(row.revision_id)
            if revision is None or revision.created_at > instant or row.content_hash != _hash(_mapping_content(row)):
                reason_codes.add("ENGINEERING_MAPPING_INTEGRITY_INVALID")
                continue
            mappings_by_deliverable[revision.deliverable_id].append(row)
        covered, sources = 0, []
        for deliverable_id, mappings in sorted(mappings_by_deliverable.items()):
            all_releases = self.releases_by_deliverable[deliverable_id]
            release = _effective_release(all_releases, self.revision_by_id, cutoff, instant)
            source = {
                "deliverable_id": deliverable_id,
                "mapping_ids": [row.id for row in mappings],
                "mapping_hashes": [row.content_hash for row in mappings],
                "required_revision_ids": sorted({row.revision_id for row in mappings}),
                "revision_id": release.revision_id if release else None,
                "release_id": release.id if release else None,
                "release_hash": release.release_hash if release else None,
                "effective_date": release.effective_date.isoformat() if release else None,
                "valid_until": None,
            }
            reason = self._source_reason(source, release, all_releases, cutoff, instant)
            source["status"] = "ELIGIBLE" if reason is None else "NOT_ELIGIBLE"
            source["reason_code"] = reason
            sources.append(source)
            if reason:
                reason_codes.add(reason)
            else:
                covered += 1
        expected = len(mappings_by_deliverable)
        status = "ELIGIBLE" if expected > 0 and covered == expected and not reason_codes else "NOT_ELIGIBLE"
        material = {
            "provider_key": PROVIDER_KEY,
            "work_package_id": package.id,
            "status": status,
            "coverage": {"required": expected, "covered": covered},
            "reason_codes": sorted(reason_codes),
            "sources": sources,
        }
        return {
            **material,
            "as_of": cutoff.isoformat(),
            "evidence_hash": _hash(material),
        }

    def _source_reason(self, source, release, all_releases, cutoff, instant):
        if release is None:
            if all_releases:
                return "ENGINEERING_IFC_NOT_EFFECTIVE_AT_CUTOFF"
            return "ENGINEERING_IFC_REQUIRED"
        if release.revision_id not in source["required_revision_ids"]:
            return "ENGINEERING_MAPPING_REVISION_SUPERSEDED"
        revision = self.revision_by_id[release.revision_id]
        snapshot = release.snapshot_json or {}
        if (
            revision.status != "APPROVED"
            or not revision.approved_at
            or revision.approved_at > instant
            or not revision.document_hash
            or release.release_hash != _hash(snapshot)
            or snapshot.get("tenant_id") != release.tenant_id
            or snapshot.get("project_workspace_id") != release.project_workspace_id
            or snapshot.get("revision_id") != revision.id
            or snapshot.get("deliverable_id") != revision.deliverable_id
            or snapshot.get("effective_date") != release.effective_date.isoformat()
            or snapshot.get("revision_content_hash") != revision.content_hash
            or snapshot.get("document_hash") != revision.document_hash
            or snapshot.get("document_reference") != revision.document_ref_json
            or not self._reference_valid(revision, instant)
        ):
            return "ENGINEERING_RELEASE_OR_CDE_INTEGRITY_INVALID"
        expiry = _release_date_value(snapshot.get("valid_until"))
        source["valid_until"] = expiry.isoformat() if expiry else None
        if snapshot.get("valid_until") and expiry is None:
            return "ENGINEERING_EVIDENCE_EXPIRY_INVALID"
        if expiry and expiry < cutoff:
            return "ENGINEERING_EVIDENCE_EXPIRED"
        return None


def awp_engineering_reader(db, tenant, workspace):
    """Before migration or without a revision-to-package link, preserve O1 behavior."""
    if not inspect(db.connection()).has_table(EngineeringMapping.__tablename__):
        return None
    mappings = list(
        db.scalars(
            _scoped(EngineeringMapping, tenant, workspace)
            .where(EngineeringMapping.target_kind.in_(PACKAGE_KINDS), EngineeringMapping.revision_id.is_not(None))
            .order_by(EngineeringMapping.id)
        )
    )
    return EngineeringReadinessReader(db, tenant, workspace, mappings) if mappings else None


def awp_evidence_reference(provider):
    return f"engineering:{provider['work_package_id']}:{provider['evidence_hash']}"


def _typed_ref(reference, prefix):
    parts = reference.split(":")
    if (
        len(parts) != 3
        or parts[0] != prefix
        or not parts[1].isdigit()
        or len(parts[1]) > 18
        or int(parts[1]) <= 0
        or len(parts[2]) != 64
        or any(char not in "0123456789abcdef" for char in parts[2])
    ):
        raise ValueError("ENGINEERING_SOURCE_REFERENCE_INVALID")
    return int(parts[1]), parts[2]


def _matching_subject_mappings(db, tenant, workspace, revision_id, subject, observed):
    rows = db.scalars(
        _scoped(EngineeringMapping, tenant, workspace)
        .where(EngineeringMapping.revision_id == revision_id, EngineeringMapping.created_at <= observed)
        .order_by(EngineeringMapping.id)
    )
    by_kind = {
        "SCOPE": "scope_item_id",
        "PLAN": "plan_item_id",
        "EWP": "work_package_id",
        "CWP": "work_package_id",
        "IWP": "work_package_id",
        "CONTROL_ACCOUNT": "control_account_id",
        "CBS": "cbs_id",
        "COST_CODE": "cost_code_id",
    }
    schedule = {"ACTIVITY": "activity_external_id", "MILESTONE": "activity_external_id", "WBS": "wbs_external_id"}
    matches = []
    for row in _effective(rows):
        if row.content_hash != _hash(_mapping_content(row)):
            continue
        field = by_kind.get(row.target_kind)
        schedule_field = schedule.get(row.target_kind)
        if (
            field
            and row.target_id == subject.get(field)
            or (
                schedule_field
                and row.schedule_version_id == subject.get("schedule_version_id")
                and row.external_id == subject.get(schedule_field)
            )
        ):
            matches.append({"mapping_id": row.id, "mapping_hash": row.content_hash})
    if not matches:
        raise ValueError("ENGINEERING_SOURCE_SUBJECT_MAPPING_REQUIRED")
    return matches


def resolve_progress_release_fact(db, tenant, workspace, reference, as_of, measurement_date, subject):
    """An explicitly selected IFC event is evidence, never a progress calculation."""
    identity, expected = _typed_ref(reference, "engineering-release")
    observed = _observed_at(as_of)
    if measurement_date > observed.date() or not inspect(db.connection()).has_table(EngineeringMapping.__tablename__):
        raise ValueError("ENGINEERING_SOURCE_NOT_AVAILABLE")
    release = db.scalar(_scoped(EngineeringRelease, tenant, workspace).where(EngineeringRelease.id == identity))
    if not release or release.release_hash != expected:
        raise ValueError("ENGINEERING_RELEASE_REFERENCE_NOT_FOUND")
    reader = EngineeringReadinessReader(db, tenant, workspace, [])
    reader.revision_by_id = {
        row.id: row
        for row in db.scalars(
            _scoped(EngineeringRevision, tenant, workspace).where(
                EngineeringRevision.deliverable_id == release.deliverable_id
            )
        )
    }
    all_releases = list(
        db.scalars(
            _scoped(EngineeringRelease, tenant, workspace).where(
                EngineeringRelease.deliverable_id == release.deliverable_id
            )
        )
    )
    effective = _effective_release(all_releases, reader.revision_by_id, measurement_date, observed)
    if effective is None or effective.id != release.id:
        raise ValueError("ENGINEERING_RELEASE_NOT_CURRENT_AT_MEASUREMENT")
    source = {"required_revision_ids": [release.revision_id]}
    reason = reader._source_reason(source, release, all_releases, measurement_date, observed)
    if reason:
        raise ValueError(reason)
    return {
        "provider_key": PROVIDER_KEY,
        "deliverable_id": release.deliverable_id,
        "revision_id": release.revision_id,
        "release_id": release.id,
        "release_hash": release.release_hash,
        "effective_date": release.effective_date.isoformat(),
        "valid_until": source["valid_until"],
        "mappings": _matching_subject_mappings(db, tenant, workspace, release.revision_id, subject, observed),
    }


def resolve_forecast_issue_fact(db, tenant, workspace, reference, as_of, subject=None):
    """Resolve only the revision's issue forecast, not a new Forecast authority."""
    identity, expected = _typed_ref(reference, "engineering-revision")
    observed = _observed_at(as_of)
    if not inspect(db.connection()).has_table(EngineeringMapping.__tablename__):
        raise ValueError("ENGINEERING_SOURCE_NOT_AVAILABLE")
    row = db.scalar(
        _scoped(EngineeringRevision, tenant, workspace).where(
            EngineeringRevision.id == identity, EngineeringRevision.created_at <= observed
        )
    )
    if (
        not row
        or row.updated_at > observed
        or row.content_hash != expected
        or row.status == "REJECTED"
        or row.forecast_issue_date is None
    ):
        raise ValueError("ENGINEERING_FORECAST_SOURCE_STALE_OR_UNAVAILABLE")
    latest = db.scalar(
        _scoped(EngineeringRevision, tenant, workspace)
        .where(EngineeringRevision.deliverable_id == row.deliverable_id, EngineeringRevision.created_at <= observed)
        .order_by(EngineeringRevision.revision_sequence.desc())
        .limit(1)
    )
    if latest is None or latest.id != row.id:
        raise ValueError("ENGINEERING_FORECAST_REVISION_SUPERSEDED")
    return {
        "deliverable_id": row.deliverable_id,
        "revision_id": row.id,
        "content_hash": row.content_hash,
        "forecast_issue_date": row.forecast_issue_date.isoformat(),
        "mappings": _matching_subject_mappings(db, tenant, workspace, row.id, subject, observed) if subject else [],
    }


class EngineeringIntegrationMixin:
    """Concrete handlers; core service owns policy, write receipts and audit."""

    def _resolve_document(self, workspace, document_id, attachment_id):
        binding = _cde_binding(self.db, self.tenant_id, workspace)
        if binding is None:
            self._error(409, "ENGINEERING_CDE_ACTIVE_BINDING_REQUIRED")
        membership = require_membership(self.db, self.tenant_id, binding.legacy_project_id, self.actor_id)
        pair = self.db.execute(
            _cde_rows(self.db, self.tenant_id, binding.legacy_project_id).where(
                Document.id == document_id, DocumentAttachment.id == attachment_id
            )
        ).one_or_none()
        if not pair or not _can_access_document(membership, pair[0]):
            self._error(404, "ENGINEERING_CDE_REFERENCE_NOT_FOUND")
        if not _sha_eligible(pair[1]):
            self._error(409, "ENGINEERING_CDE_HASH_REQUIRED")
        return _cde_reference(binding, *pair)

    def document_targets(self, workspace, limit=100, after=0):
        self._project(workspace)
        self._require_schema()
        binding = _cde_binding(self.db, self.tenant_id, workspace)
        if binding is None:
            return {"items": [], "next_cursor": None, "reason_codes": ["ENGINEERING_CDE_ACTIVE_BINDING_REQUIRED"]}
        membership = require_membership(self.db, self.tenant_id, binding.legacy_project_id, self.actor_id)
        eligible = (
            _cde_reference(binding, document, attachment) | {"title": document.title}
            for document, attachment in self.db.execute(
                _cde_rows(self.db, self.tenant_id, binding.legacy_project_id)
                .where(DocumentAttachment.id > after)
                .order_by(DocumentAttachment.id)
            )
            if _can_access_document(membership, document) and _sha_eligible(attachment)
        )
        items = []
        for row in eligible:
            items.append(row)
            if len(items) > limit:
                break
        return {
            "items": items[:limit],
            "next_cursor": items[limit - 1]["attachment_id"] if len(items) > limit else None,
            "reason_codes": [],
        }

    def _approved_scope_ids(self, workspace):
        baseline = self._current_baseline(workspace)
        return {item["id"] for item in baseline.snapshot_json.get("items", [])} if baseline else set()

    def _target_for_mapping(self, workspace, payload):
        kind = payload.target_kind
        if kind in SCHEDULE_KINDS:
            version = self._get(ScheduleVersion, workspace, payload.schedule_version_id)
            if version.status != "ACCEPTED_CURRENT" or not version.accepted_at:
                self._error(409, "ENGINEERING_ACCEPTED_CURRENT_SCHEDULE_REQUIRED")
            item = _schedule_item(version, kind, payload.external_id)
            if item is None:
                self._error(422, "ENGINEERING_SCHEDULE_TARGET_NOT_FOUND")
            return _schedule_summary(version, item, kind)
        row = self._get(TARGET_MODELS[kind], workspace, payload.target_id)
        if kind in PACKAGE_KINDS and row.package_type != kind:
            self._error(422, "ENGINEERING_WORK_PACKAGE_TYPE_MISMATCH")
        if kind == "PLAN" and row.status != "PUBLISHED":
            self._error(409, "ENGINEERING_PUBLISHED_PLAN_REQUIRED")
        if kind in {"SCOPE", "PLAN"}:
            ids = (
                {row.id}
                if kind == "SCOPE"
                else set(
                    self.db.scalars(
                        _scoped(PlanItemScopeLink, self.tenant_id, workspace)
                        .with_only_columns(PlanItemScopeLink.scope_item_id)
                        .where(PlanItemScopeLink.plan_item_id == row.id)
                    )
                )
            )
            if not ids or not ids <= self._approved_scope_ids(workspace):
                self._error(409, "ENGINEERING_CURRENT_APPROVED_SCOPE_REQUIRED")
        if kind in {"CWA", "CBS", "COST_CODE", "CONTROL_ACCOUNT"} and row.status != "ACTIVE":
            self._error(409, "ENGINEERING_ACTIVE_TARGET_REQUIRED")
        return _target_summary(row, kind)

    def mapping_targets(self, workspace, target_kind: TargetKind, limit=100, after=0):
        self._project(workspace)
        self._require_schema()
        if target_kind in SCHEDULE_KINDS:
            versions = self.db.scalars(
                _scoped(ScheduleVersion, self.tenant_id, workspace)
                .where(ScheduleVersion.status == "ACCEPTED_CURRENT", ScheduleVersion.accepted_at.is_not(None))
                .order_by(ScheduleVersion.id)
            )
            rows = [
                _schedule_summary(version, item, target_kind)
                for version in versions
                for item in _schedule_rows(version, target_kind)
                if item.get("external_id") is not None
            ]
            return {
                "items": rows[after : after + limit],
                "next_cursor": after + limit if len(rows) > after + limit else None,
            }
        model = TARGET_MODELS[target_kind]
        query = _scoped(model, self.tenant_id, workspace).where(model.id > after).order_by(model.id)
        if target_kind in PACKAGE_KINDS:
            query = query.where(WorkPackage.package_type == target_kind)
        if target_kind == "PLAN":
            query = query.where(PlanItem.status == "PUBLISHED")
        if target_kind == "SCOPE":
            query = query.where(ScopeItem.id.in_(self._approved_scope_ids(workspace)))
        if target_kind in {"CWA", "CBS", "COST_CODE", "CONTROL_ACCOUNT"}:
            query = query.where(model.status == "ACTIVE")
        rows = list(self.db.scalars(query.limit(limit + 1)))
        return {
            "items": [_target_summary(row, target_kind) for row in rows[:limit]],
            "next_cursor": rows[limit - 1].id if len(rows) > limit else None,
        }

    def _mapping_rows(self, workspace, identity, design_package):
        field = EngineeringMapping.design_package_id if design_package else EngineeringMapping.revision_id
        return list(
            self.db.scalars(
                _scoped(EngineeringMapping, self.tenant_id, workspace)
                .where(field == identity)
                .order_by(EngineeringMapping.version)
            )
        )

    def _mapping_out(self, row):
        result = self._out(row) | {"mapping_health": "VALID", "status": "ACTIVE" if row.action == "SET" else "REMOVED"}
        if row.action == "REMOVE":
            return result | {"mapping_health": "REMOVED"}
        if row.content_hash != _hash(_mapping_content(row)):
            return result | {"mapping_health": "INTEGRITY_INVALID"}
        if row.target_kind in SCHEDULE_KINDS:
            snapshot = row.target_snapshot_json
            current = self.db.scalar(
                _scoped(ScheduleVersion, self.tenant_id, row.project_workspace_id).where(
                    ScheduleVersion.register_id == snapshot.get("schedule_register_id"),
                    ScheduleVersion.status == "ACCEPTED_CURRENT",
                )
            )
            if current is None or current.id != row.schedule_version_id:
                return result | {
                    "mapping_health": "REQUIRES_REVIEW"
                    if current and _schedule_item(current, row.target_kind, row.external_id)
                    else "BROKEN",
                    "current_schedule_version_id": current.id if current else None,
                }
        return result

    def mappings(self, workspace, identity, *, design_package=False):
        self._project(workspace)
        self._require_schema()
        self._get(EngineeringDesignPackage if design_package else EngineeringRevision, workspace, identity)
        rows = self._mapping_rows(workspace, identity, design_package)
        return {
            "version": rows[-1].version if rows else 1,
            "items": [self._mapping_out(row) for row in _effective(rows)],
            "history": [self._mapping_out(row) for row in rows],
        }

    def map_target(self, workspace, identity, payload, expected, key, *, design_package=False):
        self._ready(workspace, "mapping.edit")

        def apply():
            self._ready(workspace, "mapping.edit")
            self._get(
                EngineeringDesignPackage if design_package else EngineeringRevision, workspace, identity, lock=True
            )
            if design_package and payload.target_kind != "EWP":
                self._error(422, "ENGINEERING_DESIGN_PACKAGE_EWP_ONLY")
            history = self._mapping_rows(workspace, identity, design_package)
            current = history[-1].version if history else 1
            self._version(current, expected)
            prior = next((row for row in _effective(history) if _mapping_key(row) == _mapping_key(payload)), None)
            if payload.action == "REMOVE":
                if prior is None:
                    self._error(404, "ENGINEERING_ACTIVE_MAPPING_NOT_FOUND")
                target = prior.target_snapshot_json
            else:
                target = self._target_for_mapping(workspace, payload)
                if prior is not None and prior.target_snapshot_json == target:
                    self._error(409, "ENGINEERING_MAPPING_ALREADY_ACTIVE")
            row = EngineeringMapping(
                **(self._base(workspace) | {"version": current + 1}),
                revision_id=None if design_package else identity,
                design_package_id=identity if design_package else None,
                target_snapshot_json=target,
                **payload.model_dump(),
            )
            row.content_hash = _hash(_mapping_content(row))
            self.db.add(row)
            self._record(row, "ENGINEERING_MAPPING_CHANGED", payload.reason)
            return self._mapping_out(row)

        command = "design_package.mapping" if design_package else "revision.mapping"
        return self._write(command, workspace, payload, key, apply, identity, expected)

    def readiness(self, workspace, work_package_id, as_of=None):
        self._project(workspace)
        self._require_schema()
        if _cutoff(as_of) > utc_now().date():
            self._error(422, "ENGINEERING_READINESS_AS_OF_IN_FUTURE")
        package = self._get(WorkPackage, workspace, work_package_id)
        reader = awp_engineering_reader(self.db, self.tenant_id, workspace)
        evidence = reader.evidence(package, as_of) if reader else None
        if evidence is None:
            return {
                "provider_key": PROVIDER_KEY,
                "work_package_id": work_package_id,
                "as_of": _cutoff(as_of).isoformat(),
                "coverage": {"required": 0, "covered": 0},
                "status": "NOT_APPLICABLE",
                "reason_codes": ["ENGINEERING_PACKAGE_MAPPING_MISSING"],
                "sources": [],
                "evidence_hash": None,
                "evidence_reference": None,
            }
        return evidence | {
            "evidence_reference": awp_evidence_reference(evidence) if evidence["status"] == "ELIGIBLE" else None
        }

    def _engineering_read_facts(self, workspace, as_of=None):
        project = self._project(workspace)
        self._require_schema()
        cutoff = _cutoff(as_of)
        deadline = _observed_at(cutoff)
        deliverables = list(
            self.db.scalars(
                _scoped(EngineeringDeliverable, self.tenant_id, workspace)
                .where(EngineeringDeliverable.created_at <= deadline)
                .order_by(EngineeringDeliverable.id)
            )
        )
        revisions = list(
            self.db.scalars(
                _scoped(EngineeringRevision, self.tenant_id, workspace)
                .where(EngineeringRevision.created_at <= deadline)
                .order_by(EngineeringRevision.deliverable_id, EngineeringRevision.revision_sequence)
            )
        )
        revisions_by_id = {row.id: row for row in revisions}
        revision_by_deliverable = {row.deliverable_id: row for row in revisions}
        releases_by_deliverable = defaultdict(list)
        for row in self.db.scalars(
            _scoped(EngineeringRelease, self.tenant_id, workspace)
            .where(EngineeringRelease.effective_date <= cutoff, EngineeringRelease.released_at <= deadline)
            .order_by(EngineeringRelease.id)
        ):
            releases_by_deliverable[row.deliverable_id].append(row)
        mapping_rows = list(
            self.db.scalars(
                _scoped(EngineeringMapping, self.tenant_id, workspace)
                .where(EngineeringMapping.created_at <= deadline, EngineeringMapping.revision_id.is_not(None))
                .order_by(EngineeringMapping.id)
            )
        )
        by_revision = defaultdict(list)
        for row in _effective(mapping_rows):
            by_revision[row.revision_id].append(row)
        by_history = {}
        if any(not _not_future(row.updated_at, cutoff) for row in (*deliverables, *revisions)):
            for row in self.db.scalars(
                _scoped(EngineeringHistory, self.tenant_id, workspace)
                .where(
                    EngineeringHistory.created_at <= deadline,
                    EngineeringHistory.entity_type.in_(["EngineeringDeliverable", "EngineeringRevision"]),
                )
                .order_by(EngineeringHistory.id)
            ):
                by_history[(row.entity_type, row.entity_id)] = row.snapshot_json
        facts = []
        for deliverable in deliverables:
            revision = revision_by_deliverable.get(deliverable.id)
            effective = _effective_release(
                releases_by_deliverable[deliverable.id], revisions_by_id, deadline.date(), deadline
            )
            header = (
                self._out(deliverable)
                if _not_future(deliverable.updated_at, cutoff)
                else by_history.get(("EngineeringDeliverable", deliverable.id), {})
            )
            rev = (
                (
                    self._out(revision)
                    if _not_future(revision.updated_at, cutoff)
                    else by_history.get(("EngineeringRevision", revision.id), {})
                )
                if revision
                else {}
            )
            planned = rev.get("planned_issue_date") or header.get("planned_issue_date")
            forecast = rev.get("forecast_issue_date") or header.get("current_forecast_date")
            revision_id = revision.id if revision else None
            effective_revision_id = effective.revision_id if effective else None
            mapped = by_revision[revision_id] if revision else []
            # A later draft is not a replacement for an effective IFC release. Retain its context too.
            if effective and revision and effective_revision_id != revision_id:
                mapped = sorted([*mapped, *by_revision[effective_revision_id]], key=lambda row: row.id)
            facts.append(
                {
                    "deliverable_id": deliverable.id,
                    "deliverable_code": header.get("code"),
                    "title": header.get("title"),
                    "discipline": header.get("discipline"),
                    "area": header.get("area"),
                    "revision_id": revision_id,
                    "revision_code": rev.get("revision_code"),
                    "status": rev.get("status", "NO_REVISION" if revision is None else "HISTORICAL_STATE_UNAVAILABLE"),
                    "revision_content_hash": rev.get("content_hash"),
                    "planned_issue_date": planned,
                    "forecast_issue_date": forecast,
                    "actual_issue_date": effective.effective_date.isoformat() if effective else None,
                    "effective_ifc_revision_id": effective_revision_id,
                    "release_id": effective.id if effective else None,
                    "release_hash": effective.release_hash if effective else None,
                    # The predecessor can remain effective while the latest issue is overdue.
                    "overdue": bool(
                        planned
                        and planned < cutoff.isoformat()
                        and (effective_revision_id is None or effective_revision_id != revision_id)
                    ),
                    "forecast_late": bool(planned and forecast and forecast > planned),
                    "superseded_ifc": sum(
                        other.effective_date <= deadline.date() and other.id != effective.id
                        for other in releases_by_deliverable[deliverable.id]
                    )
                    if effective
                    else 0,
                    "mappings": [
                        {
                            "mapping_id": row.id,
                            "revision_id": row.revision_id,
                            "target_kind": row.target_kind,
                            "target_id": row.target_id,
                            "schedule_version_id": row.schedule_version_id,
                            "external_id": row.external_id,
                            "target": row.target_snapshot_json,
                            "content_hash": row.content_hash,
                        }
                        for row in mapped
                    ],
                }
            )
        return project, cutoff, facts

    def status_metrics(self, workspace, as_of=None, group_by=None):
        _, cutoff, facts = self._engineering_read_facts(workspace, as_of)
        dimension = group_by.upper() if group_by else None

        def summarize(rows):
            counts = Counter(row["status"] for row in rows)
            return {
                "total_deliverables": len(rows),
                "planned": sum(bool(row["planned_issue_date"]) for row in rows),
                "submitted": counts["UNDER_REVIEW"]
                + counts["CHANGES_REQUESTED"]
                + counts["APPROVED"]
                + counts["REJECTED"],
                "under_review": counts["UNDER_REVIEW"],
                "approved": counts["APPROVED"],
                "ifc_released": sum(bool(row["release_id"]) for row in rows),
                "overdue": sum(row["overdue"] for row in rows),
                "forecast_late": sum(row["forecast_late"] for row in rows),
                "superseded": sum(row["superseded_ifc"] for row in rows),
            }

        groups = defaultdict(list)
        if dimension == "PROJECT":
            groups[("PROJECT", workspace)] = facts
        else:
            for row in facts:
                keys = {("DISCIPLINE", row["discipline"]), ("AREA", row["area"])}
                for mapping in row["mappings"]:
                    if mapping["target_kind"] in {"EWP", "CWA"}:
                        keys.add((mapping["target_kind"], mapping["target_id"]))
                    if mapping["target"].get("cwa_id"):
                        keys.add(("CWA", mapping["target"]["cwa_id"]))
                    if mapping["target"].get("area"):
                        keys.add(("AREA", mapping["target"]["area"]))
                for kind, value in keys:
                    if value not in {None, ""} and (dimension is None or dimension == kind):
                        groups[(kind, value)].append(row)
        return {
            "as_of": cutoff.isoformat(),
            "project": summarize(facts),
            "groups": [
                {"dimension": kind, "key": value, **summarize(rows)}
                for (kind, value), rows in sorted(groups.items(), key=lambda item: (item[0][0], str(item[0][1])))
            ],
            "items": [{key: value for key, value in row.items() if key != "mappings"} for row in facts],
            "authority": "ENGINEERING_STATUS_NOT_PHYSICAL_PROGRESS_OR_CPM",
        }

    def lookahead(self, workspace, as_of=None, horizon_days=None):
        project, cutoff, facts = self._engineering_read_facts(workspace, as_of)
        profile = self._engineering_profile(project)
        horizon = (
            horizon_days if horizon_days is not None else profile.content_json["lookahead_days"] if profile else 28
        )
        if not 1 <= horizon <= 120:
            self._error(422, "ENGINEERING_LOOKAHEAD_HORIZON_INVALID")
        last = (cutoff + timedelta(days=horizon)).isoformat()
        start = cutoff.isoformat()
        candidates = [
            row
            | {
                "ifc_release_due": row["forecast_issue_date"] or row["planned_issue_date"],
                "readiness_impact": "EVIDENCE_REVIEW_REQUIRED"
                if any(mapping["target_kind"] in PACKAGE_KINDS for mapping in row["mappings"])
                else "NO_EXPLICIT_PACKAGE_MAPPING",
            }
            for row in facts
            if row["effective_ifc_revision_id"] != row["revision_id"] or not row["release_id"]
            if row["overdue"]
            or any(
                target is not None and start <= target <= last
                for target in (row["planned_issue_date"], row["forecast_issue_date"])
            )
        ]
        return {
            "as_of": start,
            "through": last,
            "horizon_days": horizon,
            "authority": "ENGINEERING_ISSUE_DATES_NO_SCHEDULE_RECALCULATION",
            "items": sorted(
                candidates, key=lambda row: (not row["overdue"], row["ifc_release_due"] or "", row["deliverable_id"])
            ),
        }

    def source_facts(self, workspace, as_of=None):
        project, cutoff, facts = self._engineering_read_facts(workspace, as_of)
        profile = self._engineering_profile(project)
        method = profile.content_json["progress_default_method"] if profile else "DELIVERABLE_MILESTONE"
        return {
            "as_of": cutoff.isoformat(),
            "progress": {
                "authority": "PROGRESS",
                "engineering_default_method": method,
                "evidence_only": True,
                "items": [
                    {
                        "deliverable_id": row["deliverable_id"],
                        "revision_id": row["effective_ifc_revision_id"] or row["revision_id"],
                        "milestone": "IFC_RELEASED" if row["release_id"] else "APPROVED",
                        "source_hash": row["release_hash"] or row["revision_content_hash"],
                        "source_reference": f"engineering-release:{row['release_id']}:{row['release_hash']}"
                        if row["release_id"]
                        else None,
                    }
                    for row in facts
                    if row["release_id"] or row["status"] == "APPROVED"
                ],
            },
            "forecast": {
                "authority": "FORECAST",
                "candidate_only": True,
                "items": [
                    {
                        key: row[key]
                        for key in (
                            "deliverable_id",
                            "revision_id",
                            "forecast_issue_date",
                            "planned_issue_date",
                            "status",
                            "revision_content_hash",
                            "release_hash",
                        )
                    }
                    | {
                        "source_reference": f"engineering-revision:{row['revision_id']}:{row['revision_content_hash']}"
                        if row["revision_content_hash"] and row["forecast_issue_date"]
                        else None
                    }
                    for row in facts
                ],
            },
            "cost": {
                "authority": "COST",
                "recognizes_actual": False,
                "items": [
                    {"deliverable_id": row["deliverable_id"], **mapping}
                    for row in facts
                    for mapping in row["mappings"]
                    if mapping["target_kind"] in {"CBS", "COST_CODE", "CONTROL_ACCOUNT"}
                ],
            },
        }
