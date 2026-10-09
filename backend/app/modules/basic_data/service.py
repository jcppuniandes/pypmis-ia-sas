"""Wave 2B Basic Data governance, metadata and backend-owned readiness.

Technical evidence is distinct from FEL/PDRI, Risk, Permit, FIN and FID.
Those source authorities are read-only. Completed snapshots never resolve live
items; current-readiness is a separate, non-persisting freshness projection.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Callable
from copy import deepcopy
from datetime import date, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.v1.routers.admin_configuration import _workspace_path
from app.core.time import utc_now
from app.domain.models import (
    AdminConfiguration,
    AdminNumberSequence,
    EnterpriseWorkspace,
    PermissionCatalog,
    SecurityAccessAssignment,
    SecurityEvent,
    SecurityGroupMember,
    SecurityRole,
    SecurityRolePermission,
    Tenant,
)
from app.modules.basic_data.models import BasicDataCommand, BasicDataReadinessAssessment, ProjectBasicDataItem
from app.modules.basic_data.schemas import (
    AssessmentActionIn,
    AssessmentCreateIn,
    ConfigurationCloneIn,
    ConfigurationPreviewIn,
    ConfigurationUpdateIn,
    ItemCreateIn,
    ItemUpdateIn,
    ItemValidateIn,
)
from app.modules.enterprise_structure.permissions import EnterprisePermissionContext
from app.modules.investment_evidence_policy.decision_criteria import EVIDENCE_QUALITY_STATES
from app.modules.project_definition.models import ProjectDefinitionAssessment, ProjectFELStatus
from app.modules.project_definition.service import ProjectDefinitionService

CONFIGURATION_KIND = "basic_data_readiness_configuration"
DEFAULT_CODE = "default"
NUMBER_RULE = "basic_data_assessment"
PROVIDER_KEY = "BASIC_DATA_READINESS_PROVIDER"
SOURCE_MODULE = "BASIC_DATA_READINESS"
EVIDENCE_TYPE = "BASIC_DATA_READINESS"
AVAILABILITY_VALUES = ("NOT_AVAILABLE", "PARTIALLY_AVAILABLE", "AVAILABLE")
VALIDATION_VALUES = ("NOT_VALIDATED", "UNDER_VALIDATION", "VALIDATED", "REJECTED")
CONFIDENCE_VALUES = ("PRELIMINARY", "MODERATE", "HIGH")
QUALITY_ORDER = {
    "NOT_AVAILABLE": 0,
    "NOT_VALIDATED": 0,
    "LOW_CONFIDENCE": 1,
    "PRELIMINARY": 2,
    "PARTIALLY_VALIDATED": 3,
    "VALIDATED": 4,
}
APPLICABILITY_FIELDS = {
    "governance_models": "governance_model",
    "project_types": "project_type",
    "industries": "industry",
    "fel_stages": "fel_stage",
    "gate_profiles": "gate_profile",
    "locations": "location",
    "risks": "risk",
    "complexities": "complexity",
    "uncertainty_levels": "uncertainty",
}
DEFAULT_CONFIGURATION: dict[str, Any] = {
    "scope": {"type": "tenant", "workspace_id": None},
    "inherit_to_descendants": True,
    "applicability": {"governance_models": ["CAPITAL_OWNER"], "project_types": ["*"]},
    "categories": [],
    "requirements": [],
    "coverage_rules": {"minimum_percent": 100},
    "separation_of_duties": {"preparer_cannot_complete": True, "author_cannot_publish": True},
    "numbering": {"prefix": "BDA", "padding": 6, "separator": "-"},
}


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _json(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


class BasicDataService:
    def __init__(self, db: Session, tenant_id: int, actor_id: int, context: EnterprisePermissionContext | None = None):
        self.db, self.tenant_id, self.actor_id, self.context = db, tenant_id, actor_id, context
        self._action_cache: dict[int | None, list[str]] = {}

    def ensure_seed(self) -> AdminConfiguration:
        """Explicit provisioning only; never called by a GET or evaluator."""
        self.db.scalar(select(Tenant).where(Tenant.id == self.tenant_id).with_for_update())
        row = self.db.scalar(
            select(AdminConfiguration)
            .where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == CONFIGURATION_KIND,
                AdminConfiguration.code == DEFAULT_CODE,
            )
            .order_by(AdminConfiguration.revision.desc())
        )
        if row is None:
            row = AdminConfiguration(
                tenant_id=self.tenant_id,
                kind=CONFIGURATION_KIND,
                code=DEFAULT_CODE,
                name="Basic Data Readiness Configuration",
                description="Empty DRAFT; configure actual requirements and explicitly publish before use.",
                status="draft",
                revision=1,
                version=1,
                content_json=deepcopy(DEFAULT_CONFIGURATION),
                content_hash=_hash(DEFAULT_CONFIGURATION),
                created_by_user_id=self.actor_id,
            )
            self.db.add(row)
            self.db.flush()
            self._event(
                "basic_data.config.seeded", "AdminConfiguration", row.id, {"author_cannot_publish_required": True}
            )
        if (
            self.db.scalar(
                select(AdminNumberSequence.id).where(
                    AdminNumberSequence.tenant_id == self.tenant_id,
                    AdminNumberSequence.rule_code == NUMBER_RULE,
                    AdminNumberSequence.scope_key == "tenant",
                )
            )
            is None
        ):
            self.db.add(
                AdminNumberSequence(
                    tenant_id=self.tenant_id, rule_code=NUMBER_RULE, scope_key="tenant", next_value=1, version=1
                )
            )
        self.db.commit()
        return row

    def options(self, *, page=1, page_size=100, search: str | None = None) -> dict:
        statement = select(EnterpriseWorkspace).where(
            EnterpriseWorkspace.tenant_id == self.tenant_id, EnterpriseWorkspace.workspace_type_code == "project"
        )
        if self.context is not None and not self.context.organization_wide:
            # Batched hierarchy projection avoids an ancestor query for every option.
            hierarchy = self.db.execute(
                select(EnterpriseWorkspace.id, EnterpriseWorkspace.parent_id).where(
                    EnterpriseWorkspace.tenant_id == self.tenant_id
                )
            ).all()
            allowed = set(self.context.workspace_ids)
            changed = True
            while changed:
                children = {row.id for row in hierarchy if row.parent_id in allowed}
                changed = bool(children - allowed)
                allowed.update(children)
            statement = statement.where(EnterpriseWorkspace.id.in_(allowed or {-1}))
        if search:
            statement = statement.where(EnterpriseWorkspace.name.ilike(f"%{search}%"))
        total = self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        projects = self.db.scalars(
            statement.order_by(EnterpriseWorkspace.name, EnterpriseWorkspace.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return {
            "projects": [
                ProjectDefinitionService._project_summary(p) | {"workspace_type_code": p.workspace_type_code}
                for p in projects
            ],
            "quality_values": list(EVIDENCE_QUALITY_STATES),
            "confidence_values": list(CONFIDENCE_VALUES),
            "availability_values": list(AVAILABILITY_VALUES),
            "validation_values": list(VALIDATION_VALUES),
            "allowed_actions": self._allowed_actions(),
            "project_total": total,
            "page": page,
            "page_size": page_size,
        }

    def requirements(self, project_id: int) -> dict:
        project = self._project(project_id)
        context = self._context(project)
        configuration, content, chain = self._effective(project, context)
        applicable = configuration is not None and self._matches(content.get("applicability", {}), context)
        requirements = (
            [
                self._stage_requirement(r, context)
                for r in content.get("requirements", [])
                if r.get("active", True) and self._matches(r.get("applicability", {}), context)
            ]
            if applicable
            else []
        )
        return {
            "project_id": project_id,
            "configuration": self._config_ref(configuration, chain),
            "context": context,
            "categories": deepcopy(content.get("categories", [])),
            "requirements": requirements,
            "applicable": applicable,
            "inheritance_path": chain,
            "coverage_rules": deepcopy(content.get("coverage_rules", {})),
            "policy": content,
            "allowed_actions": self._allowed_actions(project_id),
        }

    def items(
        self, project_id: int, *, page=1, page_size=50, category: str | None = None, validation_state: str | None = None
    ) -> dict:
        self._project(project_id)
        statement = select(ProjectBasicDataItem).where(
            ProjectBasicDataItem.tenant_id == self.tenant_id, ProjectBasicDataItem.project_workspace_id == project_id
        )
        if category:
            statement = statement.where(ProjectBasicDataItem.category == category)
        if validation_state:
            statement = statement.where(ProjectBasicDataItem.validation_state == validation_state)
        total = self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        rows = self.db.scalars(
            statement.order_by(ProjectBasicDataItem.requirement_code, ProjectBasicDataItem.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return {"items": [self._item_out(r) for r in rows], "total": total, "page": page, "page_size": page_size}

    def item(self, item_id: int) -> dict:
        return self._item_out(self._item(item_id))

    def create_item(self, project_id: int, payload: ItemCreateIn, key: str) -> dict:
        self._project(project_id)

        def apply():
            requirement = self._requirement(project_id, payload.requirement_code)
            if self.db.scalar(
                select(ProjectBasicDataItem.id).where(
                    ProjectBasicDataItem.tenant_id == self.tenant_id,
                    ProjectBasicDataItem.project_workspace_id == project_id,
                    ProjectBasicDataItem.requirement_code == payload.requirement_code,
                )
            ):
                self._error(409, "BASIC_DATA_REQUIREMENT_ITEM_EXISTS")
            self._validate_item_values(payload)
            values = payload.model_dump(exclude={"requirement_code", "evidence_refs"})
            row = ProjectBasicDataItem(
                tenant_id=self.tenant_id,
                project_workspace_id=project_id,
                category=requirement["category"],
                requirement_code=payload.requirement_code,
                **values,
                evidence_refs_json=deepcopy(payload.evidence_refs),
                created_by=self.actor_id,
                updated_by=self.actor_id,
            )
            self.db.add(row)
            self.db.flush()
            self._event("basic_data.item.created", "ProjectBasicDataItem", row.id, {"project_id": project_id})
            self._stale_event(project_id, "ITEM_CREATED")
            return self._item_out(row)

        return self._command(
            "item.create", key, {"project_id": project_id, "payload": payload.model_dump(mode="json")}, apply
        )

    def update_item(self, item_id: int, expected: int, payload: ItemUpdateIn, key: str) -> dict:
        self._item(item_id)

        def apply():
            row = self._item(item_id, lock=True)
            self._version(row.revision_version, expected)
            self._validate_item_values(payload)
            values = payload.model_dump(exclude={"evidence_refs"})
            material = (
                any(
                    getattr(row, k) != v
                    for k, v in values.items()
                    if k not in {"comments", "limitations", "assumptions", "gaps"}
                )
                or row.evidence_refs_json != payload.evidence_refs
            )
            for name, value in values.items():
                setattr(row, name, value)
            row.evidence_refs_json = deepcopy(payload.evidence_refs)
            if material:
                row.validation_state, row.validated_by, row.validated_at = "NOT_VALIDATED", None, None
            row.updated_by = self.actor_id
            self._touch(row)
            self._event("basic_data.item.updated", "ProjectBasicDataItem", row.id, {"validation_reset": material})
            self._stale_event(row.project_workspace_id, "ITEM_UPDATED")
            return self._item_out(row)

        return self._command(
            "item.update", key, {"id": item_id, "expected": expected, "payload": payload.model_dump(mode="json")}, apply
        )

    def validate_item(self, item_id: int, expected: int, payload: ItemValidateIn, key: str) -> dict:
        self._item(item_id)

        def apply():
            row = self._item(item_id, lock=True)
            self._version(row.revision_version, expected)
            if payload.validation_state == "VALIDATED" and (
                row.availability == "NOT_AVAILABLE" or not row.source_reference
            ):
                self._error(422, "BASIC_DATA_VALIDATION_REQUIRES_AVAILABLE_SOURCE")
            row.validation_state = payload.validation_state
            row.validated_by, row.validated_at = self.actor_id, utc_now()
            row.comments = payload.comments or row.comments
            row.updated_by = self.actor_id
            self._touch(row)
            self._event(
                "basic_data.item.validated", "ProjectBasicDataItem", row.id, {"validation_state": row.validation_state}
            )
            self._stale_event(row.project_workspace_id, "VALIDATION_CHANGED")
            return self._item_out(row)

        return self._command(
            "item.validate", key, {"id": item_id, "expected": expected, "payload": payload.model_dump()}, apply
        )

    def assessments(self, project_id: int, *, page=1, page_size=50) -> dict:
        self._project(project_id)
        statement = select(BasicDataReadinessAssessment).where(
            BasicDataReadinessAssessment.tenant_id == self.tenant_id,
            BasicDataReadinessAssessment.project_workspace_id == project_id,
        )
        total = self.db.scalar(select(func.count()).select_from(statement.subquery())) or 0
        rows = self.db.scalars(
            statement.order_by(BasicDataReadinessAssessment.assessment_version.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return {"items": [self._assessment_out(r) for r in rows], "total": total, "page": page, "page_size": page_size}

    def assessment(self, assessment_id: int) -> dict:
        return self._assessment_out(self._assessment(assessment_id))

    def create_assessment(self, project_id: int, payload: AssessmentCreateIn, key: str) -> dict:
        self._project(project_id)
        return self._command(
            "assessment.create",
            key,
            {"project_id": project_id, "payload": payload.model_dump()},
            lambda: self._new_assessment(project_id, payload),
        )

    def _new_assessment(self, project_id: int, payload: AssessmentCreateIn, predecessor_id: int | None = None) -> dict:
        readiness = self.evaluate(project_id)
        if readiness["configuration"]["id"] is None or not readiness["applicable"]:
            self._error(422, "BASIC_DATA_PUBLISHED_APPLICABLE_CONFIGURATION_REQUIRED")
        version = (
            self.db.scalar(
                select(func.max(BasicDataReadinessAssessment.assessment_version)).where(
                    BasicDataReadinessAssessment.tenant_id == self.tenant_id,
                    BasicDataReadinessAssessment.project_workspace_id == project_id,
                )
            )
            or 0
        ) + 1
        sequence = self.db.scalar(
            select(AdminNumberSequence)
            .where(
                AdminNumberSequence.tenant_id == self.tenant_id,
                AdminNumberSequence.rule_code == NUMBER_RULE,
                AdminNumberSequence.scope_key == "tenant",
            )
            .with_for_update()
        )
        if sequence is None:
            self._error(409, "BASIC_DATA_NUMBERING_NOT_PROVISIONED")
        policy = self.requirements(project_id)["policy"]
        number = policy.get("numbering", DEFAULT_CONFIGURATION["numbering"])
        business_number = (
            f"{number['prefix']}{number.get('separator', '-')}{sequence.next_value:0{int(number.get('padding', 6))}d}"
        )
        sequence.next_value += 1
        sequence.version += 1
        sequence.updated_at = utc_now()
        config = readiness["configuration"]
        row = BasicDataReadinessAssessment(
            tenant_id=self.tenant_id,
            project_workspace_id=project_id,
            assessment_number=business_number,
            assessment_version=version,
            predecessor_id=predecessor_id,
            title=payload.title,
            comments=payload.comments,
            configuration_id=config["id"],
            configuration_revision=config["revision"],
            configuration_hash=config["hash"],
            snapshot_json=readiness,
            created_by=self.actor_id,
        )
        self.db.add(row)
        self.db.flush()
        self._event(
            "basic_data.assessment.created",
            "BasicDataReadinessAssessment",
            row.id,
            {"number": business_number, "predecessor_id": predecessor_id},
        )
        return self._assessment_out(row)

    def preview(self, assessment_id: int) -> dict:
        row = self._assessment(assessment_id)
        if row.status == "COMPLETED":
            return {"persisted": False, **deepcopy(row.snapshot_json), "assessment_id": row.id, "historical": True}
        return {
            "persisted": False,
            **self.evaluate(row.project_workspace_id),
            "assessment_id": row.id,
            "historical": False,
        }

    def submit(self, assessment_id: int, expected: int, payload: AssessmentActionIn, key: str) -> dict:
        self._assessment(assessment_id)

        def apply():
            row = self._assessment(assessment_id, lock=True)
            self._version(row.revision_version, expected)
            if row.status != "DRAFT":
                self._error(409, "BASIC_DATA_DRAFT_REQUIRED")
            snapshot = self.evaluate(row.project_workspace_id)
            if not snapshot["configuration"]["id"] or not snapshot["applicable"]:
                self._error(422, "BASIC_DATA_PUBLISHED_APPLICABLE_CONFIGURATION_REQUIRED")
            row.snapshot_json = snapshot
            row.configuration_id = snapshot["configuration"]["id"]
            row.configuration_revision = snapshot["configuration"]["revision"]
            row.configuration_hash = snapshot["configuration"]["hash"]
            row.status, row.submitted_by, row.submitted_at = "IN_REVIEW", self.actor_id, utc_now()
            row.comments = payload.comments or row.comments
            self._touch(row)
            self._event(
                "basic_data.assessment.submitted",
                "BasicDataReadinessAssessment",
                row.id,
                {"readiness": snapshot["status"]},
            )
            return self._assessment_out(row)

        return self._command(
            "assessment.submit",
            key,
            {"id": assessment_id, "expected": expected, "payload": payload.model_dump()},
            apply,
        )

    def complete(self, assessment_id: int, expected: int, payload: AssessmentActionIn, key: str) -> dict:
        self._assessment(assessment_id)

        def apply():
            row = self._assessment(assessment_id, lock=True)
            self._version(row.revision_version, expected)
            if row.status != "IN_REVIEW":
                self._error(409, "BASIC_DATA_REVIEW_REQUIRED")
            current = self.evaluate(row.project_workspace_id)
            if self._fingerprint(current) != self._fingerprint(row.snapshot_json):
                self._error(409, "BASIC_DATA_REVIEW_SOURCE_STALE")
            policy = self.requirements(row.project_workspace_id)["policy"]
            if policy.get("separation_of_duties", {}).get("preparer_cannot_complete", True) and self.actor_id in {
                row.created_by,
                row.submitted_by,
            }:
                self._error(403, "BASIC_DATA_SEPARATION_OF_DUTIES")
            row.status, row.completed_by, row.completed_at = "COMPLETED", self.actor_id, utc_now()
            row.comments = payload.comments or row.comments
            row.assessment_hash = _hash(
                {
                    "project_id": row.project_workspace_id,
                    "version": row.assessment_version,
                    "snapshot": row.snapshot_json,
                }
            )
            self._touch(row)
            self._event(
                "basic_data.assessment.completed",
                "BasicDataReadinessAssessment",
                row.id,
                {"hash": row.assessment_hash, "readiness": row.snapshot_json["status"]},
            )
            return self._assessment_out(row)

        return self._command(
            "assessment.complete",
            key,
            {"id": assessment_id, "expected": expected, "payload": payload.model_dump()},
            apply,
        )

    def current_readiness(self, project_id: int) -> dict:
        current = self.evaluate(project_id)
        row = self._latest_completed(project_id)
        if row is None:
            return current | {
                "assessment_id": None,
                "assessment_version": None,
                "assessment_hash": None,
                "source_current": False,
                "governed": False,
            }
        frozen = deepcopy(row.snapshot_json)
        stale = self._fingerprint(current) != self._fingerprint(frozen)
        reasons = self._deltas(frozen, current)
        return frozen | {
            "assessment_id": row.id,
            "assessment_version": row.assessment_version,
            "assessment_hash": row.assessment_hash,
            "status": "STALE" if stale else frozen["status"],
            "readiness_status": "STALE" if stale else frozen["status"],
            "source_current": not stale,
            "governed": True,
            "current_projection": current,
            "stale_reasons": reasons if stale else {},
            "persisted": False,
        }

    def refresh_preview(self, assessment_id: int) -> dict:
        row = self._assessment(assessment_id)
        current = self.evaluate(row.project_workspace_id)
        return {
            "persisted": False,
            "assessment_id": row.id,
            "deltas": self._deltas(row.snapshot_json, current),
            "current_readiness": current,
            "historical_hash": row.assessment_hash,
        }

    def refresh_apply(self, assessment_id: int, expected: int, payload: AssessmentActionIn, key: str) -> dict:
        self._assessment(assessment_id)

        def apply():
            row = self._assessment(assessment_id, lock=True)
            self._version(row.revision_version, expected)
            if row.status != "COMPLETED":
                self._error(409, "BASIC_DATA_COMPLETED_PREDECESSOR_REQUIRED")
            self._event("basic_data.assessment.stale", "BasicDataReadinessAssessment", row.id, {"refresh": True})
            return self._new_assessment(
                row.project_workspace_id, AssessmentCreateIn(title=row.title, comments=payload.comments), row.id
            )

        return self._command(
            "assessment.refresh",
            key,
            {"id": assessment_id, "expected": expected, "payload": payload.model_dump()},
            apply,
        )

    def provider_evidence(self, project_id: int) -> dict:
        readiness = self.current_readiness(project_id)
        available = readiness.get("governed") and readiness["status"] == "READY" and readiness["source_current"]
        return {
            **readiness,
            "provider_key": PROVIDER_KEY,
            "source_module": SOURCE_MODULE,
            "evidence_type": EVIDENCE_TYPE,
            "scope": "EACH_PROJECT",
            "status": "AVAILABLE" if available else "UNAVAILABLE",
            "readiness": readiness["status"],
            "readiness_status": readiness["status"],
            "evidence_hash": readiness.get("assessment_hash") if available else None,
            "as_of_date": readiness.get("as_of"),
            "quality": readiness.get("quality_summary"),
            "confidence": readiness.get("confidence_summary"),
            "evidence_refs": readiness.get("source_refs", []),
            "source_current": bool(available),
        }

    def evaluate(
        self, project_id: int, *, as_of: date | None = None, requirements_override: dict | None = None
    ) -> dict:
        """One batched register lookup, exact denominator, independent dimensions."""
        resolved = requirements_override or self.requirements(project_id)
        now = as_of or utc_now().date()
        rows = self.db.scalars(
            select(ProjectBasicDataItem).where(
                ProjectBasicDataItem.tenant_id == self.tenant_id,
                ProjectBasicDataItem.project_workspace_id == project_id,
            )
        ).all()
        by_code = {row.requirement_code: row for row in rows}
        results, warnings, blockers, critical, refs = [], [], [], [], []
        for requirement in resolved["requirements"]:
            row = by_code.get(requirement["requirement_code"])
            state = self._item_out(row, include_actions=False) if row else None
            stale = bool(row and self._source_stale(row, requirement, now))
            tests = {
                "availability": bool(
                    row
                    and AVAILABILITY_VALUES.index(row.availability)
                    >= AVAILABILITY_VALUES.index(requirement.get("minimum_availability", "AVAILABLE"))
                ),
                "validation": bool(
                    row
                    and row.validation_state
                    in self._validation_acceptable(requirement.get("minimum_validation_state", "VALIDATED"))
                ),
                "quality": bool(
                    row
                    and QUALITY_ORDER.get(row.quality, -1)
                    >= QUALITY_ORDER.get(requirement.get("minimum_quality", "VALIDATED"), 4)
                ),
                "confidence": bool(
                    row
                    and CONFIDENCE_VALUES.index(row.confidence)
                    >= CONFIDENCE_VALUES.index(requirement.get("minimum_confidence", "HIGH"))
                ),
                "freshness": bool(row and not stale),
                "evidence": bool(
                    row
                    and row.source_reference
                    and (not requirement.get("evidence_required", True) or row.evidence_refs_json)
                ),
            }
            satisfied = all(tests.values())
            missing = row is None or row.availability == "NOT_AVAILABLE"
            result = "SATISFIED" if satisfied else "MISSING" if missing else "PARTIAL"
            gaps = [name.upper() for name, passed in tests.items() if not passed]
            if not satisfied and requirement.get("blocking", True):
                critical.append(requirement["requirement_code"])
                blockers.append(f"CRITICAL_REQUIREMENT:{requirement['requirement_code']}")
            elif not satisfied:
                warnings.append(f"INCOMPLETE_REQUIREMENT:{requirement['requirement_code']}")
            if row:
                refs.append(
                    {
                        "item_id": row.id,
                        "requirement_code": row.requirement_code,
                        "source_type": row.source_type,
                        "source_id": row.source_reference,
                        "source_reference": row.source_reference,
                        "source_version": row.source_version,
                        "source_hash": row.source_hash,
                        "source_date": str(row.source_date) if row.source_date else None,
                        "as_of": now.isoformat(),
                        "source_current": not stale,
                        "validated_by": row.validated_by,
                        "validated_at": str(row.validated_at) if row.validated_at else None,
                        "evidence_refs": deepcopy(row.evidence_refs_json),
                    }
                )
            results.append(
                {
                    **deepcopy(requirement),
                    "result": result,
                    "gaps": gaps,
                    "stale": stale,
                    "dimensions": tests,
                    "item": state,
                }
            )
        counts = Counter(r["result"] for r in results)
        required = len(results)
        coverage = {
            "required": required,
            "satisfied": counts["SATISFIED"],
            "partial": counts["PARTIAL"],
            "missing": counts["MISSING"],
            "percentage": round(100 * counts["SATISFIED"] / required, 6) if required else None,
        }
        minimum = resolved["coverage_rules"].get("minimum_percent", 100)
        if required and coverage["percentage"] < minimum:
            blockers.append("REQUIRED_COVERAGE_NOT_MET")
        if not resolved["configuration"]["id"]:
            status = "NOT_STARTED"
            blockers.append("PUBLISHED_CONFIGURATION_MISSING")
        elif not resolved["applicable"] or not required:
            status = "NOT_APPLICABLE"
        else:
            status = "BLOCKED" if blockers else "READY"
        dimensions = {
            name.upper() + "_READINESS": {
                "satisfied": sum(r["dimensions"][name] for r in results),
                "required": required,
                "status": "NOT_APPLICABLE"
                if not required
                else "READY"
                if all(r["dimensions"][name] for r in results)
                else "BLOCKED",
            }
            for name in ("availability", "validation", "quality", "confidence", "freshness")
        }
        dimensions["REQUIREMENT_COVERAGE"] = coverage
        dimensions["CRITICAL_GAPS"] = critical
        dimensions["OVERALL_BASIC_DATA_READINESS"] = status
        return _json(
            {
                "project_id": project_id,
                "status": status,
                "readiness_status": status,
                "applicable": resolved["applicable"],
                "configuration": resolved["configuration"],
                "context": resolved["context"],
                "categories": resolved["categories"],
                "coverage": coverage,
                "dimensions": dimensions,
                "critical_gaps": critical,
                "warnings": sorted(set(warnings)),
                "blockers": sorted(set(blockers)),
                "requirements": results,
                "quality_summary": dict(
                    Counter(r["item"]["quality"] if r["item"] else "NOT_AVAILABLE" for r in results)
                ),
                "confidence_summary": dict(
                    Counter(r["item"]["confidence"] if r["item"] else "NOT_AVAILABLE" for r in results)
                ),
                "source_refs": refs,
                "source_current": not any(r["stale"] for r in results),
                "as_of": now.isoformat(),
                "persisted": False,
            }
        )

    # Reusable AdminConfiguration lifecycle ---------------------------------
    def configurations(self) -> list[dict]:
        records = self.db.scalars(
            select(AdminConfiguration)
            .where(AdminConfiguration.tenant_id == self.tenant_id, AdminConfiguration.kind == CONFIGURATION_KIND)
            .order_by(AdminConfiguration.revision.desc(), AdminConfiguration.id.desc())
        ).all()
        visible = [r for r in records if self._config_visible(r)]
        events = (
            self.db.scalars(
                select(SecurityEvent).where(
                    SecurityEvent.tenant_id == self.tenant_id,
                    SecurityEvent.target_type == "AdminConfiguration",
                    SecurityEvent.target_id.in_([r.id for r in visible]),
                    SecurityEvent.event_type.in_(
                        ["basic_data.config.seeded", "basic_data.config.cloned", "basic_data.config.updated"]
                    ),
                )
            ).all()
            if visible
            else []
        )
        return [
            self._configuration_out(r, preparation_events=[e for e in events if e.target_id == r.id]) for r in visible
        ]

    def clone_configuration(
        self, configuration_id: int, expected: int, payload: ConfigurationCloneIn, key: str
    ) -> dict:
        self._configuration(configuration_id)

        def apply():
            source = self._configuration(configuration_id, lock=True)
            self._version(source.version, expected)
            content = deepcopy(source.content_json)
            if "target_workspace_id" in payload.model_fields_set:
                target = self._workspace(payload.target_workspace_id) if payload.target_workspace_id else None
                if target:
                    self._scope(target)
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
                "basic_data.config.cloned",
                "AdminConfiguration",
                row.id,
                {
                    "source_id": source.id,
                    "author_cannot_publish_required": source.content_json.get("separation_of_duties", {}).get(
                        "author_cannot_publish", True
                    ),
                },
            )
            return self._configuration_out(row)

        return self._command(
            "config.clone",
            key,
            {"id": configuration_id, "expected": expected, "payload": payload.model_dump(exclude_unset=True)},
            apply,
        )

    def update_configuration(
        self, configuration_id: int, expected: int, payload: ConfigurationUpdateIn, key: str
    ) -> dict:
        self._configuration(configuration_id)

        def apply():
            row = self._configuration(configuration_id, lock=True)
            self._version(row.version, expected)
            if row.status != "draft":
                self._error(409, "BASIC_DATA_PUBLISHED_CONFIGURATION_IMMUTABLE")
            self._assert_config_scope(row.content_json)
            self._assert_config_scope(payload.content_json)
            self._validate_configuration(payload.content_json)
            row.name, row.description = payload.name.strip(), payload.description.strip()
            row.content_json, row.content_hash = deepcopy(payload.content_json), _hash(payload.content_json)
            row.version += 1
            row.updated_at = utc_now()
            self._event("basic_data.config.updated", "AdminConfiguration", row.id, {"hash": row.content_hash})
            return self._configuration_out(row)

        return self._command(
            "config.update", key, {"id": configuration_id, "expected": expected, "payload": payload.model_dump()}, apply
        )

    def publish_configuration(self, configuration_id: int, expected: int, key: str) -> dict:
        self._configuration(configuration_id)

        def apply():
            row = self._configuration(configuration_id, lock=True)
            self._version(row.version, expected)
            self._assert_config_scope(row.content_json)
            if row.status != "draft":
                self._error(409, "BASIC_DATA_DRAFT_CONFIGURATION_REQUIRED")
            self._validate_configuration(row.content_json)
            preparation_events = self.db.scalars(
                select(SecurityEvent).where(
                    SecurityEvent.tenant_id == self.tenant_id,
                    SecurityEvent.target_type == "AdminConfiguration",
                    SecurityEvent.target_id == row.id,
                    SecurityEvent.event_type.in_(
                        ["basic_data.config.seeded", "basic_data.config.cloned", "basic_data.config.updated"]
                    ),
                )
            ).all()
            authors = {row.created_by_user_id, *(event.user_id for event in preparation_events)}
            inherited_sod = any(
                event.metadata_json.get("author_cannot_publish_required", False) for event in preparation_events
            )
            required_sod = inherited_sod or row.content_json.get("separation_of_duties", {}).get(
                "author_cannot_publish", True
            )
            if required_sod and self.actor_id in authors:
                self._error(403, "BASIC_DATA_CONFIGURATION_SEPARATION_OF_DUTIES")
            row.status, row.published_at = "published", utc_now()
            row.version += 1
            row.updated_at = utc_now()
            self._event(
                "basic_data.config.published",
                "AdminConfiguration",
                row.id,
                {"revision": row.revision, "hash": row.content_hash, "existing_snapshots_untouched": True},
            )
            return self._configuration_out(row)

        return self._command("config.publish", key, {"id": configuration_id, "expected": expected}, apply)

    def archive_configuration(self, configuration_id: int, expected: int, key: str) -> dict:
        self._configuration(configuration_id)

        def apply():
            row = self._configuration(configuration_id, lock=True)
            self._version(row.version, expected)
            self._assert_config_scope(row.content_json)
            if row.status != "published":
                self._error(409, "BASIC_DATA_PUBLISHED_CONFIGURATION_REQUIRED")
            row.status = "archived"
            row.version += 1
            row.updated_at = utc_now()
            self._event("basic_data.config.archived", "AdminConfiguration", row.id, {})
            return self._configuration_out(row)

        return self._command("config.archive", key, {"id": configuration_id, "expected": expected}, apply)

    def configuration_preview(self, payload: ConfigurationPreviewIn) -> dict:
        record = self._configuration(payload.configuration_id) if payload.configuration_id else None
        content = deepcopy(
            payload.content_json
            if payload.content_json is not None
            else record.content_json
            if record
            else DEFAULT_CONFIGURATION
        )
        self._assert_config_scope(content)
        issues = self._configuration_issues(content)
        preview = {
            "persisted": False,
            "configuration": self._configuration_out(record) if record else None,
            "effective_configuration": content,
            "issues": issues,
            "warnings": ["PREVIEW_ONLY_NOT_PUBLISHED"],
            "blockers": issues,
        }
        if payload.project_id is not None and not issues:
            project = self._project(payload.project_id)
            context = self._context(project)
            target = (content.get("scope") or {}).get("workspace_id")
            if target is not None and target not in {w.id for w in _workspace_path(self.db, self.tenant_id, project)}:
                self._error(422, "BASIC_DATA_CONFIGURATION_PROJECT_SCOPE_MISMATCH")
            applicable = self._matches(content.get("applicability", {}), context)
            resolved = {
                "configuration": self._config_ref(record, []),
                "context": context,
                "categories": content.get("categories", []),
                "requirements": [
                    self._stage_requirement(r, context)
                    for r in content.get("requirements", [])
                    if r.get("active", True) and self._matches(r.get("applicability", {}), context)
                ]
                if applicable
                else [],
                "applicable": applicable,
                "coverage_rules": content.get("coverage_rules", {}),
            }
            preview["readiness"] = self.evaluate(project.id, requirements_override=resolved)
        return preview

    # Resolution, source freshness and persistence helpers -------------------
    def _context(self, project: EnterpriseWorkspace) -> dict:
        # Reuse the actual FEL adapter's project classifications; no authority write.
        values = dict((project.defaults_json or {}).get("_project", {}))
        fel = self.db.scalar(
            select(ProjectFELStatus).where(
                ProjectFELStatus.tenant_id == self.tenant_id, ProjectFELStatus.project_workspace_id == project.id
            )
        )
        assessment_id = fel.latest_completed_assessment_id if fel else None
        definition = (
            self.db.scalar(
                select(ProjectDefinitionAssessment).where(
                    ProjectDefinitionAssessment.tenant_id == self.tenant_id,
                    ProjectDefinitionAssessment.id == assessment_id,
                )
            )
            if assessment_id
            else None
        )
        fel_evidence = (
            ProjectDefinitionService(self.db, self.tenant_id, self.actor_id)
            .investment_gate_evidence(project.id)
            .model_dump(mode="json")
        )
        return {
            "project_type": ProjectDefinitionService._project_type(project),
            "governance_model": ProjectDefinitionService._governance_model(project),
            "fel_stage": fel.current_stage_code if fel else values.get("fel_stage", "NOT_STARTED"),
            "gate_profile": values.get("gate_profile", values.get("gate_profile_code", "")),
            "industry": values.get("industry", values.get("sector", "")),
            "location": values.get("location", ""),
            "risk": values.get("risk", values.get("project_risk", "")),
            "complexity": values.get("complexity", ""),
            "uncertainty": values.get("uncertainty", ""),
            "definition_assessment": {
                "id": definition.id,
                "hash": definition.assessment_hash,
                "score": definition.normalized_score,
                "maturity": definition.maturity_level,
                "framework_hash": definition.framework_hash,
            }
            if definition
            else None,
            "fel_status": fel.status if fel else "NOT_STARTED",
            "fel_context_version": fel.revision_version if fel else None,
            "fel_provider_key": "GATE07J_FEL_PROJECT_DEFINITION",
            "fel_provider_context": fel_evidence,
        }

    def _effective(self, project: EnterpriseWorkspace, context: dict) -> tuple[AdminConfiguration | None, dict, list]:
        path = _workspace_path(self.db, self.tenant_id, project)
        path_order = {row.id: i + 1 for i, row in enumerate(path)}
        records = self.db.scalars(
            select(AdminConfiguration).where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == CONFIGURATION_KIND,
                AdminConfiguration.status == "published",
            )
        ).all()
        selected: dict[int, AdminConfiguration] = {}
        for row in records:
            scope = (row.content_json.get("scope") or {}).get("workspace_id")
            if scope is not None and scope not in path_order:
                continue
            if scope is not None and scope != project.id and not row.content_json.get("inherit_to_descendants", True):
                continue
            if not self._matches(row.content_json.get("applicability", {}), context):
                continue
            rank = path_order.get(scope, 0)
            prior = selected.get(rank)
            if prior is None or (row.revision, row.id) > (prior.revision, prior.id):
                selected[rank] = row
        chain = [
            {"id": row.id, "revision": row.revision, "hash": row.content_hash, "scope": row.content_json.get("scope")}
            for _, row in sorted(selected.items())
        ]
        if not chain:
            return None, deepcopy(DEFAULT_CONFIGURATION), []
        # Most-specific governed policy is an explicit complete override, not an
        # implicit merge of required categories across industries or stages.
        record = selected[max(selected)]
        return record, deepcopy(record.content_json), chain

    @staticmethod
    def _matches(applicability: dict, context: dict) -> bool:
        return all(
            not values
            or "*" in values
            or str(context.get(APPLICABILITY_FIELDS[key], "")).upper() in {str(v).upper() for v in values}
            for key, values in applicability.items()
            if key in APPLICABILITY_FIELDS
        )

    @staticmethod
    def _stage_requirement(requirement: dict, context: dict) -> dict:
        result = deepcopy(requirement)
        result.update(deepcopy((requirement.get("stage_rules") or {}).get(context["fel_stage"], {})))
        return result

    @staticmethod
    def _source_stale(item: ProjectBasicDataItem, requirement: dict, now: date) -> bool:
        if not item.source_current or (item.expires_on is not None and now > item.expires_on):
            return True
        max_age = requirement.get("max_age_days")
        return max_age is not None and (
            item.source_date is None or now > item.source_date + timedelta(days=int(max_age))
        )

    @staticmethod
    def _validation_acceptable(minimum: str) -> set[str]:
        return (
            {"VALIDATED"}
            if minimum == "VALIDATED"
            else {"UNDER_VALIDATION", "VALIDATED"}
            if minimum == "UNDER_VALIDATION"
            else {"NOT_VALIDATED", "UNDER_VALIDATION", "VALIDATED"}
        )

    @staticmethod
    def _fingerprint(snapshot: dict) -> str:
        # Time itself does not stale evidence; requirement-specific freshness does.
        stable = deepcopy(snapshot)
        for key in ("as_of", "persisted"):
            stable.pop(key, None)
        for ref in stable.get("source_refs", []):
            ref.pop("as_of", None)
        return _hash(stable)

    @staticmethod
    def _deltas(old: dict, new: dict) -> dict:
        previous = {r["requirement_code"]: r for r in old.get("requirements", [])}
        current = {r["requirement_code"]: r for r in new.get("requirements", [])}
        return {
            "new_requirements": sorted(current.keys() - previous.keys()),
            "removed_requirements": sorted(previous.keys() - current.keys()),
            "changed_applicability": old.get("configuration") != new.get("configuration"),
            "changed_items": [code for code in current.keys() & previous.keys() if current[code] != previous[code]],
            "stale_sources": [code for code, r in current.items() if r.get("stale")],
            "coverage_delta": {"before": old.get("coverage"), "after": new.get("coverage")},
            "quality_delta": {"before": old.get("quality_summary"), "after": new.get("quality_summary")},
            "confidence_delta": {"before": old.get("confidence_summary"), "after": new.get("confidence_summary")},
            "new_blockers": sorted(set(new.get("blockers", [])) - set(old.get("blockers", []))),
            "fel_pdri_context_delta": {"before": old.get("context"), "after": new.get("context")}
            if old.get("context") != new.get("context")
            else None,
        }

    def _configuration_issues(self, content: dict) -> list[str]:
        issues = []
        if any(
            not isinstance(content.get(key, {}), dict)
            for key in ("scope", "applicability", "coverage_rules", "separation_of_duties", "numbering")
        ):
            return ["INVALID_POLICY_OBJECT"]
        categories = content.get("categories", [])
        requirements = content.get("requirements", [])
        if not isinstance(categories, list) or not isinstance(requirements, list) or len(requirements) > 2000:
            return ["INVALID_CATEGORY_REQUIREMENT_COLLECTION"]
        if any(not isinstance(c, dict) or not c.get("code") or not c.get("name") for c in categories):
            return ["INVALID_CATEGORY"]
        codes = [c["code"] for c in categories]
        if len(codes) != len(set(codes)):
            issues.append("DUPLICATE_CATEGORY_CODE")
        requirement_codes = []
        for r in requirements:
            if (
                not isinstance(r, dict)
                or not r.get("requirement_code")
                or not r.get("name")
                or r.get("category") not in codes
            ):
                issues.append("INVALID_REQUIREMENT")
                continue
            requirement_codes.append(r["requirement_code"])
            stage_rules = r.get("stage_rules") or {}
            if not isinstance(stage_rules, dict) or any(not isinstance(key, str) or not key for key in stage_rules):
                issues.append("INVALID_STAGE_RULE")
                stage_rules = {}
            allowed_stage_fields = {
                "minimum_quality",
                "minimum_confidence",
                "minimum_validation_state",
                "minimum_availability",
                "max_age_days",
                "blocking",
                "evidence_required",
            }
            if any(not isinstance(value, dict) or set(value) - allowed_stage_fields for value in stage_rules.values()):
                issues.append("INVALID_STAGE_RULE_FIELDS")
            for values in [r, *stage_rules.values()]:
                if not isinstance(values, dict):
                    issues.append("INVALID_STAGE_RULE")
                    continue
                if values.get("minimum_quality", "VALIDATED") not in QUALITY_ORDER:
                    issues.append("INVALID_QUALITY_POLICY")
                if values.get("minimum_confidence", "HIGH") not in CONFIDENCE_VALUES:
                    issues.append("INVALID_CONFIDENCE_POLICY")
                if values.get("minimum_validation_state", "VALIDATED") not in {
                    "NOT_VALIDATED",
                    "UNDER_VALIDATION",
                    "VALIDATED",
                }:
                    issues.append("INVALID_VALIDATION_POLICY")
                if values.get("minimum_availability", "AVAILABLE") not in AVAILABILITY_VALUES:
                    issues.append("INVALID_AVAILABILITY_POLICY")
                max_age = values.get("max_age_days")
                if max_age is not None and (
                    not isinstance(max_age, int) or isinstance(max_age, bool) or not 0 <= max_age <= 36500
                ):
                    issues.append("INVALID_FRESHNESS_POLICY")
                if any(not isinstance(values.get(key, True), bool) for key in ("blocking", "evidence_required")):
                    issues.append("INVALID_REQUIREMENT_FLAG")
            issues.extend(self._applicability_issues(r.get("applicability", {})))
        if len(requirement_codes) != len(set(requirement_codes)):
            issues.append("DUPLICATE_REQUIREMENT_CODE")
        issues.extend(self._applicability_issues(content.get("applicability", {})))
        coverage = content.get("coverage_rules", {}).get("minimum_percent", 100)
        if isinstance(coverage, bool) or not isinstance(coverage, (int, float)) or not 0 <= coverage <= 100:
            issues.append("INVALID_COVERAGE_PERCENT")
        scope = content.get("scope", {})
        if not isinstance(scope, dict) or scope.get("type") not in {
            "tenant",
            "enterprise",
            "business-unit",
            "portfolio",
            "program",
            "project",
        }:
            issues.append("INVALID_SCOPE")
        numbering = content.get("numbering", DEFAULT_CONFIGURATION["numbering"])
        if (
            not isinstance(numbering.get("prefix"), str)
            or not numbering.get("prefix")
            or len(numbering["prefix"]) > 20
            or not isinstance(numbering.get("padding", 6), int)
            or not 1 <= numbering.get("padding", 6) <= 12
        ):
            issues.append("INVALID_NUMBERING")
        if any(
            not isinstance(content.get("separation_of_duties", {}).get(key, True), bool)
            for key in ("preparer_cannot_complete", "author_cannot_publish")
        ):
            issues.append("INVALID_SEPARATION_OF_DUTIES")
        if not isinstance(content.get("inherit_to_descendants", True), bool):
            issues.append("INVALID_INHERITANCE_FLAG")
        # Policy is declarative only, never executable expressions.
        serialized = json.dumps(content).lower()
        if any(f'"{key}"' in serialized for key in ("script", "expression", "formula", "python", "javascript")):
            issues.append("EXECUTABLE_POLICY_NOT_ALLOWED")
        return sorted(set(issues))

    @staticmethod
    def _applicability_issues(value: Any) -> list[str]:
        if not isinstance(value, dict) or any(
            k not in APPLICABILITY_FIELDS or not isinstance(v, list) or any(not isinstance(x, str) for x in v)
            for k, v in value.items()
        ):
            return ["INVALID_APPLICABILITY"]
        return []

    def _validate_configuration(self, content: dict) -> None:
        issues = self._configuration_issues(content)
        if issues:
            raise HTTPException(status_code=422, detail={"code": "INVALID_BASIC_DATA_CONFIGURATION", "issues": issues})

    @staticmethod
    def _validate_item_values(payload: ItemUpdateIn) -> None:
        if payload.quality not in QUALITY_ORDER or payload.confidence not in CONFIDENCE_VALUES:
            raise HTTPException(status_code=422, detail={"code": "INVALID_BASIC_DATA_EVIDENCE_VOCABULARY"})
        if payload.source_date and payload.source_date > utc_now().date():
            raise HTTPException(status_code=422, detail={"code": "BASIC_DATA_FUTURE_SOURCE_DATE"})
        if payload.source_date and payload.expires_on and payload.expires_on < payload.source_date:
            raise HTTPException(status_code=422, detail={"code": "BASIC_DATA_EXPIRY_BEFORE_SOURCE"})

    def _workspace(self, workspace_id: int | None) -> EnterpriseWorkspace:
        row = self.db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.tenant_id == self.tenant_id, EnterpriseWorkspace.id == workspace_id
            )
        )
        if row is None:
            self._error(404, "WORKSPACE_NOT_FOUND")
        return row

    def _project(self, project_id: int) -> EnterpriseWorkspace:
        row = self._workspace(project_id)
        if row.workspace_type_code != "project":
            self._error(422, "PROJECT_WORKSPACE_REQUIRED")
        self._scope(row)
        return row

    def _scope(self, workspace: EnterpriseWorkspace) -> None:
        if not self._in_scope(workspace):
            self._error(403, "WORKSPACE_SCOPE_DENIED")

    def _in_scope(self, workspace: EnterpriseWorkspace) -> bool:
        return (
            self.context is None
            or self.context.organization_wide
            or bool(
                {w.id for w in _workspace_path(self.db, self.tenant_id, workspace)} & set(self.context.workspace_ids)
            )
        )

    def _item(self, item_id: int, *, lock=False) -> ProjectBasicDataItem:
        statement = select(ProjectBasicDataItem).where(
            ProjectBasicDataItem.tenant_id == self.tenant_id, ProjectBasicDataItem.id == item_id
        )
        row = self.db.scalar(
            statement.with_for_update().execution_options(populate_existing=True) if lock else statement
        )
        if row is None:
            self._error(404, "BASIC_DATA_ITEM_NOT_FOUND")
        self._project(row.project_workspace_id)
        return row

    def _assessment(self, assessment_id: int, *, lock=False) -> BasicDataReadinessAssessment:
        statement = select(BasicDataReadinessAssessment).where(
            BasicDataReadinessAssessment.tenant_id == self.tenant_id, BasicDataReadinessAssessment.id == assessment_id
        )
        row = self.db.scalar(
            statement.with_for_update().execution_options(populate_existing=True) if lock else statement
        )
        if row is None:
            self._error(404, "BASIC_DATA_ASSESSMENT_NOT_FOUND")
        self._project(row.project_workspace_id)
        return row

    def _latest_completed(self, project_id: int) -> BasicDataReadinessAssessment | None:
        return self.db.scalar(
            select(BasicDataReadinessAssessment)
            .where(
                BasicDataReadinessAssessment.tenant_id == self.tenant_id,
                BasicDataReadinessAssessment.project_workspace_id == project_id,
                BasicDataReadinessAssessment.status == "COMPLETED",
            )
            .order_by(BasicDataReadinessAssessment.assessment_version.desc())
            .limit(1)
        )

    def _requirement(self, project_id: int, code: str) -> dict:
        row = next((r for r in self.requirements(project_id)["requirements"] if r["requirement_code"] == code), None)
        if row is None:
            self._error(422, "BASIC_DATA_REQUIREMENT_NOT_APPLICABLE")
        return row

    def _configuration(self, config_id: int, *, lock=False) -> AdminConfiguration:
        statement = select(AdminConfiguration).where(
            AdminConfiguration.tenant_id == self.tenant_id,
            AdminConfiguration.kind == CONFIGURATION_KIND,
            AdminConfiguration.id == config_id,
        )
        row = self.db.scalar(
            statement.with_for_update().execution_options(populate_existing=True) if lock else statement
        )
        if row is None or not self._config_visible(row):
            self._error(404, "BASIC_DATA_CONFIGURATION_NOT_FOUND")
        return row

    def _config_visible(self, config: AdminConfiguration) -> bool:
        if self.context is None or self.context.organization_wide:
            return True
        scope_id = (config.content_json.get("scope") or {}).get("workspace_id")
        if scope_id is None:
            return config.status == "published"
        target = self._workspace(scope_id)
        if self._in_scope(target):
            return True
        return config.status == "published" and any(
            scope_id in {w.id for w in _workspace_path(self.db, self.tenant_id, self._workspace(allowed))}
            for allowed in self.context.workspace_ids
        )

    def _assert_config_scope(self, content: dict) -> None:
        scope_id = (content.get("scope") or {}).get("workspace_id")
        if scope_id is None:
            if self.context is not None and not self.context.organization_wide:
                self._error(403, "CONFIGURATION_TENANT_SCOPE_DENIED")
        else:
            workspace = self._workspace(scope_id)
            self._scope(workspace)
            if (content.get("scope") or {}).get("type") != workspace.workspace_type_code:
                self._error(422, "BASIC_DATA_SCOPE_TYPE_MISMATCH")

    @staticmethod
    def _config_ref(config: AdminConfiguration | None, chain: list) -> dict:
        return {
            "id": config.id if config else None,
            "revision": config.revision if config else None,
            "hash": config.content_hash if config else None,
            "resolution_hash": _hash(chain),
            "lineage": deepcopy(chain),
        }

    def _configuration_out(self, config: AdminConfiguration, preparation_events: list | None = None) -> dict:
        result = _json(
            {
                key: getattr(config, key)
                for key in (
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
        permissions = self._allowed_actions((config.content_json.get("scope") or {}).get("workspace_id"))
        can_prepare = "config_prepare" in permissions
        can_publish = "config_publish" in permissions
        actions = ["clone"] if can_prepare else []
        if config.status == "draft":
            if can_prepare:
                actions.append("edit")
            events = (
                preparation_events
                if preparation_events is not None
                else self.db.scalars(
                    select(SecurityEvent).where(
                        SecurityEvent.tenant_id == self.tenant_id,
                        SecurityEvent.target_type == "AdminConfiguration",
                        SecurityEvent.target_id == config.id,
                        SecurityEvent.event_type.in_(
                            ["basic_data.config.seeded", "basic_data.config.cloned", "basic_data.config.updated"]
                        ),
                    )
                ).all()
            )
            authors = {config.created_by_user_id, *(e.user_id for e in events)}
            required_sod = config.content_json.get("separation_of_duties", {}).get(
                "author_cannot_publish", True
            ) or any(e.metadata_json.get("author_cannot_publish_required", False) for e in events)
            if can_publish and (not required_sod or self.actor_id not in authors):
                actions.append("publish")
        elif config.status == "published" and can_publish:
            actions.append("archive")
        result["allowed_actions"] = actions
        return result

    def _item_out(self, item: ProjectBasicDataItem, *, include_actions=True) -> dict:
        result = {
            key: getattr(item, key)
            for key in (
                "id",
                "project_workspace_id",
                "requirement_code",
                "category",
                "availability",
                "validation_state",
                "quality",
                "confidence",
                "source_type",
                "source_reference",
                "source_version",
                "source_hash",
                "source_date",
                "expires_on",
                "source_current",
                "limitations",
                "assumptions",
                "gaps",
                "comments",
                "validated_by",
                "validated_at",
                "created_by",
                "updated_by",
                "created_at",
                "updated_at",
                "revision_version",
            )
        }
        result["evidence_refs"] = deepcopy(item.evidence_refs_json)
        if include_actions:
            result["allowed_actions"] = [
                a for a in self._allowed_actions(item.project_workspace_id) if a.startswith("item_")
            ]
        return _json(result)

    def _assessment_out(self, row: BasicDataReadinessAssessment) -> dict:
        result = {
            key: getattr(row, key)
            for key in (
                "id",
                "project_workspace_id",
                "assessment_number",
                "assessment_version",
                "predecessor_id",
                "title",
                "comments",
                "status",
                "configuration_id",
                "configuration_revision",
                "configuration_hash",
                "snapshot_json",
                "assessment_hash",
                "created_by",
                "submitted_by",
                "completed_by",
                "created_at",
                "updated_at",
                "submitted_at",
                "completed_at",
                "revision_version",
            )
        }
        actions = self._allowed_actions(row.project_workspace_id)
        result["allowed_actions"] = [
            a
            for a in actions
            if a == "assessment_submit"
            and row.status == "DRAFT"
            or a == "assessment_complete"
            and row.status == "IN_REVIEW"
            or a == "assessment_create"
            and row.status == "COMPLETED"
        ]
        return _json(result)

    def _allowed_actions(self, project_id: int | None = None) -> list[str]:
        if project_id in self._action_cache:
            return self._action_cache[project_id]
        if self.context is None:
            return []
        group_ids = self.db.scalars(
            select(SecurityGroupMember.group_id).where(
                SecurityGroupMember.tenant_id == self.tenant_id, SecurityGroupMember.user_id == self.actor_id
            )
        ).all()
        now = utc_now()
        assignments = self.db.scalars(
            select(SecurityAccessAssignment).where(
                SecurityAccessAssignment.tenant_id == self.tenant_id, SecurityAccessAssignment.status == "active"
            )
        ).all()
        path_ids = (
            {w.id for w in _workspace_path(self.db, self.tenant_id, self._workspace(project_id))}
            if project_id
            else None
        )
        role_ids = {
            a.role_id
            for a in assignments
            if (a.user_id == self.actor_id or a.group_id in group_ids)
            and (a.starts_at is None or a.starts_at <= now)
            and (a.ends_at is None or a.ends_at > now)
            and (path_ids is None or a.scope_type == "organization" or a.workspace_id in path_ids)
        }
        permissions = (
            set(
                self.db.scalars(
                    select(PermissionCatalog.key)
                    .join(SecurityRolePermission, SecurityRolePermission.permission_id == PermissionCatalog.id)
                    .join(SecurityRole, SecurityRole.id == SecurityRolePermission.role_id)
                    .where(
                        PermissionCatalog.status == "active",
                        SecurityRole.status == "active",
                        SecurityRole.tenant_id == self.tenant_id,
                        SecurityRolePermission.tenant_id == self.tenant_id,
                        SecurityRolePermission.role_id.in_(role_ids),
                    )
                ).all()
            )
            if role_ids
            else set()
        )
        mapping = {
            "item_create": "basic_data.item.create",
            "item_edit": "basic_data.item.edit",
            "item_validate": "basic_data.item.validate",
            "assessment_create": "basic_data.assessment.create",
            "assessment_submit": "basic_data.assessment.submit",
            "assessment_complete": "basic_data.assessment.complete",
            "config_prepare": "basic_data.admin.configure",
            "config_publish": "basic_data.admin.publish",
        }
        actions = [action for action, permission in mapping.items() if permission in permissions]
        self._action_cache[project_id] = actions
        return actions

    def _command(self, command: str, key: str, request: dict, apply: Callable[[], dict]) -> dict:
        if not key or len(key) > 160:
            self._error(422, "IDEMPOTENCY_KEY_REQUIRED")
        # Existing tenant lock convention serializes numbering and concurrent retries.
        self.db.scalar(select(Tenant).where(Tenant.id == self.tenant_id).with_for_update())
        request_hash = _hash({"actor": self.actor_id, "request": request})
        old = self.db.scalar(
            select(BasicDataCommand).where(
                BasicDataCommand.tenant_id == self.tenant_id, BasicDataCommand.idempotency_key == key
            )
        )
        if old:
            if old.command_type != command or old.request_hash != request_hash:
                self._error(409, "IDEMPOTENCY_KEY_REUSED")
            return deepcopy(old.result_json)
        try:
            result = _json(apply())
            self.db.add(
                BasicDataCommand(
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
            raise HTTPException(status_code=409, detail={"code": "BASIC_DATA_CONCURRENT_CONFLICT"}) from exc
        except Exception:
            self.db.rollback()
            raise

    def _stale_event(self, project_id: int, reason: str) -> None:
        latest = self._latest_completed(project_id)
        if latest:
            self._event(
                "basic_data.assessment.stale",
                "BasicDataReadinessAssessment",
                latest.id,
                {"reason": reason, "historical_hash_unchanged": latest.assessment_hash},
            )

    def _event(self, action: str, target_type: str, target_id: int, metadata: dict) -> None:
        self.db.add(
            SecurityEvent(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                event_type=action,
                outcome="success",
                target_type=target_type,
                target_id=target_id,
                metadata_json=deepcopy(metadata),
            )
        )

    @staticmethod
    def _touch(row) -> None:
        row.revision_version += 1
        row.updated_at = utc_now()

    @staticmethod
    def _version(actual: int, expected: int) -> None:
        if actual != expected:
            raise HTTPException(
                status_code=412, detail={"code": "ETAG_MISMATCH", "actual": actual, "expected": expected}
            )

    @staticmethod
    def _error(status: int, code: str) -> None:
        raise HTTPException(status_code=status, detail={"code": code})
