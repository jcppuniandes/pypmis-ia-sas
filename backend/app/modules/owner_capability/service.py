"""Owner Capability governed aggregate and read-only strategic-source adapters.

BasicDataService supplies only canonical workspace/scope, ETag, audit and option
utilities. All domain resolution, vocabulary, permissions and receipts are owned
here. No third-party service evaluator or seed is invoked by context reads.
"""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from datetime import date, timedelta
from types import SimpleNamespace

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

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
from app.modules.basic_data.models import BasicDataReadinessAssessment
from app.modules.basic_data.service import BasicDataService, _hash, _json
from app.modules.commercial_strategy.models import CommercialContractingStrategy, CommercialStrategyVersion
from app.modules.commercial_strategy.service import CommercialStrategyService
from app.modules.owner_capability.models import OwnerCapabilityAssessment, OwnerCapabilityCommand
from app.modules.owner_capability.schemas import (
    AssessmentCreateIn,
    MitigationIn,
)
from app.modules.portfolio_resource.models import PortfolioResourceScenario, PortfolioResourceScenarioProject
from app.modules.risk_governance.schemas import EffectiveContextIn
from app.modules.risk_governance.service import RiskGovernanceService
from app.modules.risk_readiness.models import ProjectRisk, RiskReadinessAssessment
from app.modules.risk_readiness.service import RiskReadinessService
from app.modules.strategic_benefits.models import StrategicBenefitsPlan, StrategicBenefitsPlanVersion

CONFIGURATION_KIND = "owner_capability_readiness_configuration"
NUMBER_RULE = "owner_capability_assessment"
PROVIDER_KEY = "OWNER_CAPABILITY_READINESS_PROVIDER"
SOURCE_MODULE = EVIDENCE_TYPE = "OWNER_CAPABILITY_READINESS"
CONFIDENCE_VALUES = ("PRELIMINARY", "MODERATE", "HIGH")
APPLICABILITY_FIELDS = {
    "governance_models": "governance_model",
    "project_types": "project_type",
    "industries": "industry",
    "fel_stages": "fel_stage",
    "gate_profiles": "gate_profile",
    "complexities": "complexity",
    "risks": "risk",
    "uncertainty_levels": "uncertainty",
    "project_sizes": "project_size",
    "commercial_strategy_types": "commercial_strategy_type",
    "delivery_models": "delivery_model",
    "locations": "location",
}
DEFAULT_CONFIGURATION = {
    "scope": {"type": "tenant", "workspace_id": None},
    "inherit_to_descendants": True,
    "applicability": {"governance_models": ["CAPITAL_OWNER"], "project_types": ["*"]},
    "framework": {"code": "OWNER_CAPABILITY", "name": "Owner Capability Framework"},
    "dimensions": [],
    "requirements": [],
    "maturity_scale": [
        {"code": "NOT_ESTABLISHED", "name": "Not established", "order": 0},
        {"code": "INITIAL", "name": "Initial", "order": 1},
        {"code": "DEFINED", "name": "Defined", "order": 2},
        {"code": "IMPLEMENTED", "name": "Implemented", "order": 3},
        {"code": "EFFECTIVE", "name": "Effective", "order": 4},
        {"code": "OPTIMIZED", "name": "Optimized", "order": 5},
    ],
    "evidence_quality_scale": [
        {"code": "NOT_AVAILABLE", "name": "Not available", "order": 0},
        {"code": "UNVERIFIED", "name": "Unverified", "order": 1},
        {"code": "PARTIALLY_VERIFIED", "name": "Partially verified", "order": 2},
        {"code": "VERIFIED", "name": "Verified", "order": 3},
    ],
    "coverage_rules": {"minimum_percent": 100},
    "mitigation_acceptance_rules": {
        "accepted_mitigation_sufficient": False,
        "allowed_approaches": [],
        "required_statuses": ["IMPLEMENTED", "CLOSED"],
        "require_closure_evidence": True,
    },
    "freshness": {
        "material_context_sources": [
            "fel_pdri",
            "commercial",
            "resources",
            "risk_governance",
            "risk_readiness",
            "basic_data",
            "benefits",
            "project_classification",
        ]
    },
    "separation_of_duties": {"preparer_cannot_complete": True, "author_cannot_publish": True},
    "numbering": {"prefix": "OCA", "padding": 6, "separator": "-"},
}


class OwnerCapabilityService(BasicDataService):
    @staticmethod
    def _config_ref(config, chain):
        return BasicDataService._config_ref(config, chain) | {"version": config.version if config else None}

    @staticmethod
    def _valid_reference(ref):
        # Preserve both live UI and legacy fixture aliases. Metadata is optional;
        # a hash/version alone is not an identifiable evidence reference.
        return isinstance(ref, dict) and any(
            isinstance(ref.get(key), str) and bool(ref[key].strip()) for key in ("source_reference", "reference")
        )

    @classmethod
    def _valid_references(cls, refs):
        return isinstance(refs, list) and bool(refs) and all(cls._valid_reference(ref) for ref in refs)

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
                name="Owner Capability Readiness Configuration",
                description="Neutral DRAFT. No Project capability evidence is fabricated.",
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
                "owner_capability.config.seeded", "AdminConfiguration", row.id, {"author_cannot_publish_required": True}
            )
        if not self.db.scalar(
            select(AdminNumberSequence.id).where(
                AdminNumberSequence.tenant_id == self.tenant_id,
                AdminNumberSequence.rule_code == NUMBER_RULE,
                AdminNumberSequence.scope_key == "tenant",
            )
        ):
            self.db.add(
                AdminNumberSequence(
                    tenant_id=self.tenant_id, rule_code=NUMBER_RULE, scope_key="tenant", next_value=1, version=1
                )
            )
        self.db.commit()
        return row

    def options(self, **kwargs):
        result = super().options(**kwargs)
        for key in ("availability_values", "validation_values"):
            result.pop(key, None)
        result["quality_values"] = [v["code"] for v in DEFAULT_CONFIGURATION["evidence_quality_scale"]]
        result["maturity_values"] = [v["code"] for v in DEFAULT_CONFIGURATION["maturity_scale"]]
        return result

    @staticmethod
    def _matches(applicability, context):
        return all(
            not values
            or "*" in values
            or str(context.get(APPLICABILITY_FIELDS[k], "")).upper() in {str(v).upper() for v in values}
            for k, values in applicability.items()
            if k in APPLICABILITY_FIELDS
        )

    def contexts(self, project_id):
        project = self._project(project_id)
        fel = super()._context(project)
        commercial = self.db.scalar(
            select(CommercialContractingStrategy).where(
                CommercialContractingStrategy.tenant_id == self.tenant_id,
                CommercialContractingStrategy.project_workspace_id == project_id,
            )
        )
        version = (
            self.db.scalar(
                select(CommercialStrategyVersion).where(
                    CommercialStrategyVersion.tenant_id == self.tenant_id,
                    CommercialStrategyVersion.commercial_strategy_id == commercial.id,
                    CommercialStrategyVersion.id == commercial.current_version_id,
                )
            )
            if commercial
            else None
        )
        commercial_context = (
            {
                "status": commercial.status,
                "id": commercial.id,
                "version_id": version.id if version else None,
                "version": version.version_number if version else None,
                "hash": version.commercial_strategy_hash if version else None,
                "source_current": version.source_current if version else False,
                "delivery_model": CommercialStrategyService._selected_code(
                    version.content_json.get("contracting_model")
                )
                if version
                else None,
                "commercial_strategy_type": CommercialStrategyService._selected_code(
                    version.content_json.get("procurement_approach")
                )
                if version
                else None,
            }
            if commercial
            else {"status": "NOT_AVAILABLE"}
        )
        resource_rows = self.db.execute(
            select(PortfolioResourceScenario, PortfolioResourceScenarioProject)
            .join(
                PortfolioResourceScenarioProject,
                PortfolioResourceScenarioProject.scenario_id == PortfolioResourceScenario.id,
            )
            .where(
                PortfolioResourceScenario.tenant_id == self.tenant_id,
                PortfolioResourceScenarioProject.tenant_id == self.tenant_id,
                PortfolioResourceScenarioProject.project_workspace_id == project_id,
                PortfolioResourceScenario.status.notin_(["SUPERSEDED", "VOIDED"]),
            )
            .order_by(PortfolioResourceScenario.id.desc())
        ).all()
        resources = [
            {
                "id": scenario.id,
                "status": scenario.status,
                "version": scenario.scenario_revision,
                "hash": scenario.scenario_hash,
                "project_row_hash": membership.row_hash,
                "selection_state": membership.selection_state,
                "overload_policy": scenario.overload_policy,
            }
            for scenario, membership in resource_rows
        ]
        risk_context = self.context or SimpleNamespace(organization_wide=True, workspace_ids=frozenset())
        risk_policy = (
            RiskGovernanceService(self.db, self.tenant_id, self.actor_id, risk_context)
            .effective(EffectiveContextIn(workspace_id=project_id))
            .model_dump(mode="json")
        )
        risk = self.db.scalar(
            select(RiskReadinessAssessment)
            .where(
                RiskReadinessAssessment.tenant_id == self.tenant_id,
                RiskReadinessAssessment.project_workspace_id == project_id,
                RiskReadinessAssessment.status == "COMPLETED",
            )
            .order_by(RiskReadinessAssessment.assessment_version.desc())
            .limit(1)
        )
        risk_readiness = (
            RiskReadinessService(self.db, self.tenant_id, self.actor_id).project_readiness(project_id) if risk else None
        )
        basic = self.db.scalar(
            select(BasicDataReadinessAssessment)
            .where(
                BasicDataReadinessAssessment.tenant_id == self.tenant_id,
                BasicDataReadinessAssessment.project_workspace_id == project_id,
                BasicDataReadinessAssessment.status == "COMPLETED",
            )
            .order_by(BasicDataReadinessAssessment.assessment_version.desc())
            .limit(1)
        )
        benefits = self.db.scalar(
            select(StrategicBenefitsPlan).where(
                StrategicBenefitsPlan.tenant_id == self.tenant_id,
                StrategicBenefitsPlan.project_workspace_id == project_id,
            )
        )
        benefits_version = (
            self.db.scalar(
                select(StrategicBenefitsPlanVersion).where(
                    StrategicBenefitsPlanVersion.tenant_id == self.tenant_id,
                    StrategicBenefitsPlanVersion.benefits_plan_id == benefits.id,
                    StrategicBenefitsPlanVersion.id == benefits.current_version_id,
                )
            )
            if benefits
            else None
        )
        return _json(
            {
                "fel_pdri": fel,
                "commercial": commercial_context,
                "resources": {"status": "AVAILABLE" if resources else "NOT_AVAILABLE", "scenarios": resources},
                "risk_governance": {
                    "status": risk_policy["status"],
                    "source": risk_policy.get("source"),
                    "warnings": risk_policy.get("warnings", []),
                },
                "risk_readiness": {
                    "status": risk_readiness.readiness_status,
                    "assessment_id": risk.id,
                    "version": risk.assessment_version,
                    "hash": risk.risk_readiness_hash,
                    "valid_until": risk.valid_until,
                    "source_current": risk_readiness.source_current,
                    "warnings": risk_readiness.warnings,
                    "blockers": risk_readiness.blockers,
                }
                if risk
                else {"status": "NOT_AVAILABLE"},
                "basic_data": {
                    "status": basic.snapshot_json.get("readiness_status"),
                    "assessment_id": basic.id,
                    "version": basic.assessment_version,
                    "hash": basic.assessment_hash,
                    "note": "HISTORICAL_COMPLETED_SUMMARY_NO_REEVALUATION",
                }
                if basic
                else {"status": "NOT_AVAILABLE"},
                "benefits": {
                    "status": benefits.status,
                    "id": benefits.id,
                    "version_id": benefits_version.id if benefits_version else None,
                    "version": benefits_version.version_number if benefits_version else None,
                    "hash": benefits_version.benefits_plan_hash if benefits_version else None,
                }
                if benefits
                else {"status": "NOT_AVAILABLE"},
                "project_classification": deepcopy((project.defaults_json or {}).get("_project", {})),
            }
        )

    def _context(self, project):
        sources = self.contexts(project.id)
        result = deepcopy(sources["fel_pdri"])
        values = (project.defaults_json or {}).get("_project", {})
        result.update(
            {
                "project_size": values.get("project_size", values.get("size", "")),
                "commercial_strategy_type": sources["commercial"].get("commercial_strategy_type")
                or values.get("commercial_strategy_type", ""),
                "delivery_model": sources["commercial"].get("delivery_model") or values.get("delivery_model", ""),
                "sources": sources,
            }
        )
        return result

    def _effective(self, project, context):
        path = _workspace_path(self.db, self.tenant_id, project)
        ranks = {w.id: i + 1 for i, w in enumerate(path)}
        candidates = []
        now = utc_now().date().isoformat()
        for row in self.db.scalars(
            select(AdminConfiguration).where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == CONFIGURATION_KIND,
                AdminConfiguration.status == "published",
            )
        ):
            c = row.content_json
            scope_id = c.get("scope", {}).get("workspace_id")
            if scope_id is not None and (
                scope_id not in ranks or scope_id != project.id and not c.get("inherit_to_descendants", True)
            ):
                continue
            if (
                not self._matches(c.get("applicability", {"governance_models": ["CAPITAL_OWNER"]}), context)
                or (c.get("effective_from") or now) > now
                or c.get("effective_to")
                and c["effective_to"] < now
            ):
                continue
            specificity = sum(bool(v) and "*" not in v for v in c.get("applicability", {}).values())
            candidates.append(
                ((ranks.get(scope_id, 0), specificity, c.get("effective_from") or "", row.revision, row.id), row)
            )
        chain = [
            {"id": r.id, "revision": r.revision, "hash": r.content_hash, "scope": r.content_json.get("scope")}
            for _, r in sorted(candidates)
        ]
        chosen = max(candidates, key=lambda pair: pair[0])[1] if candidates else None
        return chosen, deepcopy(chosen.content_json if chosen else DEFAULT_CONFIGURATION), chain

    @staticmethod
    def _tailored_requirement(requirement, context, policy):
        result = deepcopy(requirement)
        rules = {
            "stage_rules": "fel_stage",
            "gate_profile_rules": "gate_profile",
            "project_type_rules": "project_type",
            "governance_model_rules": "governance_model",
            "complexity_rules": "complexity",
            "risk_rules": "risk",
            "uncertainty_rules": "uncertainty",
            "commercial_strategy_rules": "commercial_strategy_type",
            "delivery_model_rules": "delivery_model",
        }
        for name, field in rules.items():
            result.update(deepcopy(policy.get(name, {}).get(str(context.get(field, "")), {})))
            result.update(deepcopy(requirement.get(name, {}).get(str(context.get(field, "")), {})))
        return result

    def requirements(self, project_id):
        project = self._project(project_id)
        context = self._context(project)
        configuration, policy, chain = self._effective(project, context)
        applicable = bool(configuration) and self._matches(policy.get("applicability", {}), context)
        requirements = (
            [
                self._tailored_requirement(r, context, policy)
                for r in policy.get("requirements", [])
                if r.get("active", True) and self._matches(r.get("applicability", {}), context)
            ]
            if applicable
            else []
        )
        return {
            "project_id": project_id,
            "configuration": self._config_ref(configuration, chain),
            "context": context,
            "dimensions": deepcopy(policy.get("dimensions", [])),
            "maturity_scale": deepcopy(policy.get("maturity_scale", [])),
            "quality_scale": deepcopy(policy.get("evidence_quality_scale", [])),
            "requirements": requirements,
            "applicable": applicable,
            "coverage_rules": deepcopy(policy.get("coverage_rules", {})),
            "policy": policy,
            "allowed_actions": self._allowed_actions(project_id),
        }

    def assessments(self, project_id, *, page=1, page_size=50):
        self._project(project_id)
        stmt = select(OwnerCapabilityAssessment).where(
            OwnerCapabilityAssessment.tenant_id == self.tenant_id,
            OwnerCapabilityAssessment.project_workspace_id == project_id,
        )
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        rows = self.db.scalars(
            stmt.order_by(OwnerCapabilityAssessment.assessment_version.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
        return {"items": [self._assessment_out(r) for r in rows], "total": total, "page": page, "page_size": page_size}

    def _assessment(self, assessment_id, *, lock=False):
        stmt = select(OwnerCapabilityAssessment).where(
            OwnerCapabilityAssessment.tenant_id == self.tenant_id, OwnerCapabilityAssessment.id == assessment_id
        )
        row = self.db.scalar(stmt.with_for_update().execution_options(populate_existing=True) if lock else stmt)
        if row is None:
            self._error(404, "OWNER_CAPABILITY_ASSESSMENT_NOT_FOUND")
        self._project(row.project_workspace_id)
        return row

    def assessment(self, assessment_id):
        return self._assessment_out(self._assessment(assessment_id))

    def _assessment_out(self, row):
        result = _json({column.name: getattr(row, column.name) for column in row.__table__.columns})
        actions = self._allowed_actions(row.project_workspace_id)
        authors = set(row.aggregate_json.get("preparer_ids", [row.created_by]))
        sod = row.snapshot_json.get("policy", {}).get("separation_of_duties", {}).get("preparer_cannot_complete", True)
        result["allowed_actions"] = [
            a
            for a in actions
            if a in {"assessment_edit", "assessment_submit", "mitigation_edit"}
            and row.status == "DRAFT"
            or a in {"assessment_review", "assessment_complete"}
            and row.status == "IN_REVIEW"
            and (not sod or self.actor_id not in authors)
            or a == "assessment_create"
            and row.status == "COMPLETED"
        ]
        return result

    def _new_assessment(self, project_id, payload, predecessor=None):
        resolved = self.requirements(project_id)
        if not resolved["applicable"] or not resolved["requirements"]:
            self._error(422, "OWNER_CAPABILITY_PUBLISHED_APPLICABLE_FRAMEWORK_REQUIRED")
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
            self._error(409, "OWNER_CAPABILITY_NUMBERING_NOT_PROVISIONED")
        number = resolved["policy"].get("numbering", DEFAULT_CONFIGURATION["numbering"])
        identifier = (
            f"{number['prefix']}{number.get('separator', '-')}{sequence.next_value:0{number.get('padding', 6)}d}"
        )
        sequence.next_value += 1
        sequence.version += 1
        sequence.updated_at = utc_now()
        version = (
            self.db.scalar(
                select(func.max(OwnerCapabilityAssessment.assessment_version)).where(
                    OwnerCapabilityAssessment.tenant_id == self.tenant_id,
                    OwnerCapabilityAssessment.project_workspace_id == project_id,
                )
            )
            or 0
        ) + 1
        aggregate = {
            "items": deepcopy(predecessor.aggregate_json.get("items", [])) if predecessor else [],
            "gaps": deepcopy(predecessor.aggregate_json.get("gaps", [])) if predecessor else [],
            "mitigations": deepcopy(predecessor.aggregate_json.get("mitigations", [])) if predecessor else [],
            "preparer_ids": [self.actor_id],
        }
        for mitigation in aggregate["mitigations"]:
            mitigation.pop("accepted_by", None)
        configuration = resolved["configuration"]
        row = OwnerCapabilityAssessment(
            tenant_id=self.tenant_id,
            project_workspace_id=project_id,
            assessment_number=identifier,
            assessment_version=version,
            predecessor_id=predecessor.id if predecessor else None,
            title=payload.title,
            comments=payload.comments,
            configuration_id=configuration["id"],
            configuration_revision=configuration["revision"],
            configuration_hash=configuration["hash"],
            aggregate_json=aggregate,
            snapshot_json=self.evaluate(project_id, aggregate, resolved=resolved),
            created_by=self.actor_id,
        )
        self.db.add(row)
        self.db.flush()
        self._event(
            "owner_capability.assessment.created",
            "OwnerCapabilityAssessment",
            row.id,
            {"project_id": project_id, "assessment_number": identifier, "predecessor_id": row.predecessor_id},
        )
        return self._assessment_out(row)

    def create_assessment(self, project_id, payload, key):
        self._project(project_id)
        return self._command(
            "assessment.create",
            key,
            {"project_id": project_id, "payload": payload.model_dump()},
            lambda: self._new_assessment(project_id, payload),
        )

    def _assert_draft(self, row):
        if row.status != "DRAFT":
            self._error(409, "OWNER_CAPABILITY_DRAFT_REQUIRED")

    def _validate_aggregate(self, project_id, aggregate, resolved):
        requirements = {r["requirement_code"] for r in resolved["requirements"]}
        maturities = {r["code"] for r in resolved["maturity_scale"]}
        qualities = {r["code"] for r in resolved["quality_scale"]}
        codes = [i["requirement_code"] for i in aggregate["items"]]
        if len(codes) != len(set(codes)):
            self._error(422, "OWNER_CAPABILITY_DUPLICATE_ITEM")
        for record in [*aggregate["items"], *aggregate["gaps"], *aggregate["mitigations"]]:
            for field in ("evidence_refs", "closure_evidence"):
                refs = record.get(field, [])
                if refs and not self._valid_references(refs):
                    self._error(422, "OWNER_CAPABILITY_INVALID_EVIDENCE_REFERENCE")
        for item in aggregate["items"]:
            if (
                item["requirement_code"] not in requirements
                or item.get("current_maturity") is not None
                and item["current_maturity"] not in maturities
                or item["evidence_quality"] not in qualities
            ):
                self._error(422, "OWNER_CAPABILITY_INVALID_ITEM_VOCABULARY_OR_REQUIREMENT")
            if item.get("source_date") and date.fromisoformat(item["source_date"]) > utc_now().date():
                self._error(422, "OWNER_CAPABILITY_FUTURE_EVIDENCE_DATE")
            for risk_id in item.get("related_risk_ids", []):
                if not self.db.scalar(
                    select(ProjectRisk.id).where(
                        ProjectRisk.id == risk_id,
                        ProjectRisk.tenant_id == self.tenant_id,
                        ProjectRisk.project_workspace_id == project_id,
                    )
                ):
                    self._error(422, "OWNER_CAPABILITY_RELATED_RISK_PROJECT_MISMATCH")
        for item in [*aggregate["gaps"], *aggregate["mitigations"]]:
            if item["requirement_code"] not in requirements:
                self._error(422, "OWNER_CAPABILITY_REQUIREMENT_NOT_APPLICABLE")
        for gap in aggregate["gaps"]:
            if gap["status"] == "CLOSED" and not self._valid_references(gap.get("closure_evidence")):
                self._error(422, "OWNER_CAPABILITY_GAP_CLOSURE_EVIDENCE_REQUIRED")

    def update_assessment(self, assessment_id, expected, payload, key):
        self._assessment(assessment_id)

        def apply():
            row = self._assessment(assessment_id, lock=True)
            self._version(row.revision_version, expected)
            self._assert_draft(row)
            resolved = self.requirements(row.project_workspace_id)
            self._assert_current_configuration(row, resolved)
            aggregate = payload.model_dump(mode="json", exclude={"title", "comments"})
            prior_mitigations = [
                {k: v for k, v in m.items() if k in MitigationIn.model_fields}
                for m in row.aggregate_json.get("mitigations", [])
            ]
            if (
                aggregate["mitigations"] != prior_mitigations
                and self.context is not None
                and "mitigation_edit" not in self._allowed_actions(row.project_workspace_id)
            ):
                self._error(403, "OWNER_CAPABILITY_MITIGATION_PERMISSION_REQUIRED")
            aggregate["preparer_ids"] = sorted(
                set(row.aggregate_json.get("preparer_ids", [row.created_by])) | {self.actor_id}
            )
            for index, mitigation in enumerate(aggregate["mitigations"], 1):
                mitigation["id"] = index
            self._validate_aggregate(row.project_workspace_id, aggregate, resolved)
            row.title, row.comments, row.aggregate_json = payload.title, payload.comments, aggregate
            row.snapshot_json = self.evaluate(row.project_workspace_id, aggregate, resolved=resolved)
            self._touch(row)
            self._event(
                "owner_capability.assessment.updated",
                "OwnerCapabilityAssessment",
                row.id,
                {"preparer_ids": aggregate["preparer_ids"]},
            )
            return self._assessment_out(row)

        return self._command(
            "assessment.update",
            key,
            {"id": assessment_id, "expected": expected, "payload": payload.model_dump(mode="json")},
            apply,
        )

    def _assert_current_configuration(self, row, resolved):
        if (
            row.configuration_id != resolved["configuration"]["id"]
            or row.configuration_hash != resolved["configuration"]["hash"]
        ):
            self._error(409, "OWNER_CAPABILITY_CONFIGURATION_CHANGED_REFRESH_REQUIRED")

    def preview(self, assessment_id):
        row = self._assessment(assessment_id)
        if row.status == "COMPLETED":
            return deepcopy(row.snapshot_json) | {"persisted": False, "historical": True}
        return self.evaluate(row.project_workspace_id, row.aggregate_json)

    def _independent(self, row):
        if row.snapshot_json.get("policy", {}).get("separation_of_duties", {}).get(
            "preparer_cannot_complete", True
        ) and self.actor_id in set(row.aggregate_json.get("preparer_ids", [row.created_by])):
            self._error(403, "OWNER_CAPABILITY_SEPARATION_OF_DUTIES")

    def _action(self, assessment_id, expected, payload, key, action):
        self._assessment(assessment_id)

        def apply():
            row = self._assessment(assessment_id, lock=True)
            self._version(row.revision_version, expected)
            resolved = self.requirements(row.project_workspace_id)
            self._assert_current_configuration(row, resolved)
            if action == "submit":
                self._assert_draft(row)
                row.status, row.submitted_by, row.submitted_at = "IN_REVIEW", self.actor_id, utc_now()
            else:
                if row.status != "IN_REVIEW":
                    self._error(409, "OWNER_CAPABILITY_IN_REVIEW_REQUIRED")
                self._independent(row)
                if action == "review":
                    row.reviewed_by, row.reviewed_at = self.actor_id, utc_now()
                    aggregate = deepcopy(row.aggregate_json)
                    for m in aggregate.get("mitigations", []):
                        if m.get("status") in {"ACCEPTED", "IMPLEMENTED", "CLOSED"}:
                            m["accepted_by"] = self.actor_id
                    row.aggregate_json = aggregate
                elif row.reviewed_by != self.actor_id:
                    self._error(403, "OWNER_CAPABILITY_FINAL_REVIEW_REQUIRED")
            row.snapshot_json = self.evaluate(row.project_workspace_id, row.aggregate_json, resolved=resolved)
            row.comments = payload.comments or row.comments
            if action == "complete":
                row.status, row.completed_by, row.completed_at = "COMPLETED", self.actor_id, utc_now()
                row.snapshot_json = row.snapshot_json | {"persisted": True}
                row.assessment_hash = _hash(
                    {
                        "project_id": row.project_workspace_id,
                        "version": row.assessment_version,
                        "aggregate": row.aggregate_json,
                        "snapshot": row.snapshot_json,
                    }
                )
            self._touch(row)
            self._event(
                f"owner_capability.assessment.{action}",
                "OwnerCapabilityAssessment",
                row.id,
                {"assessment_hash": row.assessment_hash, "readiness": row.snapshot_json["readiness_status"]},
            )
            return self._assessment_out(row)

        return self._command(
            f"assessment.{action}",
            key,
            {"id": assessment_id, "expected": expected, "payload": payload.model_dump()},
            apply,
        )

    def submit(self, assessment_id, expected, payload, key):
        return self._action(assessment_id, expected, payload, key, "submit")

    def review(self, assessment_id, expected, payload, key):
        return self._action(assessment_id, expected, payload, key, "review")

    def complete(self, assessment_id, expected, payload, key):
        return self._action(assessment_id, expected, payload, key, "complete")

    def mitigations(self, assessment_id):
        row = self._assessment(assessment_id)
        return {
            "items": deepcopy(row.aggregate_json.get("mitigations", [])),
            "revision_version": row.revision_version,
            "allowed_actions": self._assessment_out(row)["allowed_actions"],
        }

    def save_mitigation(self, assessment_id, expected, payload, key, mitigation_id=None):
        self._assessment(assessment_id)

        def apply():
            row = self._assessment(assessment_id, lock=True)
            self._version(row.revision_version, expected)
            self._assert_draft(row)
            aggregate = deepcopy(row.aggregate_json)
            mitigations = aggregate.setdefault("mitigations", [])
            result = payload.model_dump(mode="json")
            result["id"] = mitigation_id if mitigation_id else max((m.get("id", 0) for m in mitigations), default=0) + 1
            if mitigation_id:
                position = next((i for i, m in enumerate(mitigations) if m.get("id") == mitigation_id), None)
                if position is None:
                    self._error(404, "OWNER_CAPABILITY_MITIGATION_NOT_FOUND")
                mitigations[position] = result
            else:
                if len(mitigations) >= 2000:
                    self._error(422, "OWNER_CAPABILITY_MITIGATION_LIMIT")
                mitigations.append(result)
            aggregate["preparer_ids"] = sorted(set(aggregate.get("preparer_ids", [row.created_by])) | {self.actor_id})
            resolved = self.requirements(row.project_workspace_id)
            self._assert_current_configuration(row, resolved)
            self._validate_aggregate(row.project_workspace_id, aggregate, resolved)
            row.aggregate_json, row.snapshot_json = (
                aggregate,
                self.evaluate(row.project_workspace_id, aggregate, resolved=resolved),
            )
            self._touch(row)
            self._event(
                "owner_capability.mitigation.updated",
                "OwnerCapabilityAssessment",
                row.id,
                {"mitigation_id": result["id"], "acceptance_requires_independent_review": True},
            )
            return self._assessment_out(row)

        return self._command(
            "mitigation.update" if mitigation_id else "mitigation.create",
            key,
            {
                "id": assessment_id,
                "mitigation_id": mitigation_id,
                "expected": expected,
                "payload": payload.model_dump(mode="json"),
            },
            apply,
        )

    def evaluate(self, project_id, aggregate=None, *, resolved=None):
        resolved = resolved or self.requirements(project_id)
        aggregate = aggregate or {"items": [], "gaps": [], "mitigations": []}
        policy = resolved["policy"]
        maturity = {v["code"]: v["order"] for v in resolved["maturity_scale"]}
        quality = {v["code"]: v["order"] for v in resolved["quality_scale"]}
        items = {i["requirement_code"]: i for i in aggregate.get("items", [])}
        results, blockers, critical, warnings, refs = [], [], [], [], []
        now = utc_now().date()
        for requirement in resolved["requirements"]:
            code = requirement["requirement_code"]
            item = items.get(code)
            missing = []
            current = item.get("current_maturity") if item else None
            required_maturity = requirement["minimum_maturity"]
            minimum_quality = requirement.get("minimum_evidence_quality", requirement.get("minimum_quality"))
            stale = bool(item) and (
                not item.get("source_current", True)
                or item.get("expires_on")
                and now > date.fromisoformat(item["expires_on"])
            )
            age = requirement.get("max_age_days", policy.get("freshness", {}).get("max_age_days"))
            if (
                item
                and age is not None
                and (not item.get("source_date") or now > date.fromisoformat(item["source_date"]) + timedelta(days=age))
            ):
                stale = True
            if current not in maturity or maturity[current] < maturity.get(required_maturity, 10**9):
                missing.append("MATURITY_BELOW_REQUIRED")
            if (
                not item
                or item.get("evidence_quality") not in quality
                or quality[item["evidence_quality"]] < quality.get(minimum_quality, 10**9)
            ):
                missing.append("EVIDENCE_QUALITY_BELOW_REQUIRED")
            if requirement.get("evidence_required", True) and (
                not item or not self._valid_references(item.get("evidence_refs"))
            ):
                missing.append("EVIDENCE_REFERENCE_MISSING")
            if item and item.get("evidence_refs") and not self._valid_references(item["evidence_refs"]):
                missing.append("EVIDENCE_REFERENCE_INVALID")
                stale = True
            if requirement.get("responsible_function_required", False) and (
                not item or not item.get("responsible_function")
            ):
                missing.append("ACCOUNTABILITY_MISSING")
            if item and item.get("capability_source", "INTERNAL") not in requirement.get(
                "allowed_capability_sources", ["INTERNAL", "EXTERNAL_CONTRACTED", "HYBRID"]
            ):
                missing.append("CAPABILITY_SOURCE_NOT_ACCEPTED")
            if stale:
                missing.append("EVIDENCE_STALE")
            unresolved = [
                g
                for g in aggregate.get("gaps", [])
                if g["requirement_code"] == code
                and (g["status"] != "CLOSED" or not self._valid_references(g.get("closure_evidence")))
            ]
            if unresolved:
                missing.append("UNRESOLVED_CAPABILITY_GAP")
            acceptance = requirement.get("mitigation_acceptance_rules", policy.get("mitigation_acceptance_rules", {}))
            accepted = [
                m
                for m in aggregate.get("mitigations", [])
                if m["requirement_code"] == code
                and acceptance.get("accepted_mitigation_sufficient", False)
                and m.get("accepted_by")
                and (not m.get("evidence_refs") or self._valid_references(m["evidence_refs"]))
                and (not m.get("closure_evidence") or self._valid_references(m["closure_evidence"]))
                and m["approach"] in acceptance.get("allowed_approaches", [])
                and m["status"] in acceptance.get("required_statuses", ["IMPLEMENTED", "CLOSED"])
                and (
                    not acceptance.get("require_closure_evidence", True)
                    or self._valid_references(m.get("closure_evidence"))
                )
                and (
                    not m.get("target_date")
                    or now <= date.fromisoformat(m["target_date"])
                    or m["status"] in {"IMPLEMENTED", "CLOSED"}
                )
            ]
            # Policy may accept genuine independently-reviewed external strengthening.
            # It never waives evidence quality/freshness or an explicit blocking gap.
            if accepted:
                missing = [m for m in missing if m != "MATURITY_BELOW_REQUIRED"]
            satisfied = not missing
            blocking = requirement.get("blocking", False) or any(g["blocking"] for g in unresolved)
            if not satisfied and blocking:
                blockers.append(f"CAPABILITY_BLOCKER:{code}")
                critical.append(
                    {"requirement_code": code, "dimension": requirement["dimension"], "gaps": missing, "blocking": True}
                )
            if not satisfied:
                warnings.append(f"CAPABILITY_GAP:{code}")
            if accepted:
                warnings.append(f"SATISFIED_BY_GOVERNED_MITIGATION:{code}")
            if item:
                refs.extend(deepcopy(ref) for ref in item.get("evidence_refs") or [] if self._valid_reference(ref))
            results.append(
                deepcopy(requirement)
                | {
                    "result": "SATISFIED" if satisfied else "MISSING" if item is None else "PARTIAL",
                    "current_maturity": current,
                    "required_maturity": required_maturity,
                    "item": deepcopy(item),
                    "gaps": missing,
                    "stale": bool(stale),
                    "accepted_mitigations": [m["id"] for m in accepted],
                }
            )
        required = len(results)
        satisfied = sum(r["result"] == "SATISFIED" for r in results)
        coverage = {
            "required": required,
            "satisfied": satisfied,
            "missing": sum(r["result"] == "MISSING" for r in results),
            "partial": sum(r["result"] == "PARTIAL" for r in results),
            "percentage": round(100 * satisfied / required, 6) if required else None,
        }
        if required and coverage["percentage"] < policy.get("coverage_rules", {}).get("minimum_percent", 100):
            blockers.append("REQUIRED_COVERAGE_NOT_MET")
        governance = resolved["context"]["governance_model"]
        if not resolved["configuration"]["id"]:
            status = "NOT_APPLICABLE" if governance != "CAPITAL_OWNER" else "NOT_STARTED"
            if status == "NOT_STARTED":
                blockers.append("PUBLISHED_CONFIGURATION_MISSING")
        elif not resolved["applicable"] or not required:
            status = "NOT_APPLICABLE"
        else:
            status = "BLOCKED" if blockers else "READY"
        dimensions = {}
        for dimension in resolved["dimensions"]:
            rows = [r for r in results if r["dimension"] == dimension["code"]]
            count = sum(r["result"] == "SATISFIED" for r in rows)
            dimensions[dimension["code"]] = {
                "required": len(rows),
                "satisfied": count,
                "status": "NOT_APPLICABLE" if not rows else "READY" if count == len(rows) else "BLOCKED",
            }
        dimensions["OVERALL_OWNER_CAPABILITY_READINESS"] = status
        return _json(
            {
                "project_id": project_id,
                "status": status,
                "readiness_status": status,
                "applicable": resolved["applicable"],
                "configuration": resolved["configuration"],
                "policy": policy,
                "context": resolved["context"],
                "requirements": results,
                "coverage": coverage,
                "dimensions": dimensions,
                "critical_gaps": critical,
                "gaps": deepcopy(aggregate.get("gaps", [])),
                "mitigation_summary": {
                    "total": len(aggregate.get("mitigations", [])),
                    "states": dict(Counter(m["status"] for m in aggregate.get("mitigations", []))),
                },
                "warnings": sorted(set(warnings)),
                "blockers": sorted(set(blockers)),
                "evidence_refs": refs,
                "source_current": not any(r["stale"] for r in results),
                "as_of": now.isoformat(),
                "persisted": False,
            }
        )

    def _latest(self, project_id):
        return self.db.scalar(
            select(OwnerCapabilityAssessment)
            .where(
                OwnerCapabilityAssessment.tenant_id == self.tenant_id,
                OwnerCapabilityAssessment.project_workspace_id == project_id,
            )
            .order_by(OwnerCapabilityAssessment.assessment_version.desc())
            .limit(1)
        )

    @staticmethod
    def _material(snapshot):
        policy = snapshot.get("policy", {})
        selected = policy.get("freshness", {}).get(
            "material_context_sources", DEFAULT_CONFIGURATION["freshness"]["material_context_sources"]
        )
        context = snapshot.get("context", {})
        return _hash(
            {
                "configuration": snapshot.get("configuration"),
                "context": {
                    k: context.get(k)
                    for k in (
                        "governance_model",
                        "project_type",
                        "industry",
                        "fel_stage",
                        "gate_profile",
                        "complexity",
                        "risk",
                        "uncertainty",
                        "project_size",
                        "commercial_strategy_type",
                        "delivery_model",
                    )
                },
                "sources": {k: context.get("sources", {}).get(k) for k in selected},
                "requirements": snapshot.get("requirements"),
                "coverage": snapshot.get("coverage"),
                "blockers": snapshot.get("blockers"),
            }
        )

    def current_readiness(self, project_id):
        self._project(project_id)
        row = self._latest(project_id)
        if row is None:
            return self.evaluate(project_id) | {"assessment": None, "source_current": False}
        current = self.evaluate(project_id, row.aggregate_json)
        stale = row.status == "COMPLETED" and (
            self._material(current) != self._material(row.snapshot_json) or not current["source_current"]
        )
        if stale:
            current = current | {
                "status": "STALE",
                "readiness_status": "STALE",
                "source_current": False,
                "warnings": sorted(set(current["warnings"] + ["COMPLETED_CONTEXT_OR_EVIDENCE_CHANGED"])),
            }
        elif row.status != "COMPLETED":
            current = current | {"status": "IN_PROGRESS", "readiness_status": "IN_PROGRESS", "source_current": False}
        return current | {"assessment": self._assessment_out(row), "historical_hash": row.assessment_hash}

    def refresh_preview(self, assessment_id):
        row = self._assessment(assessment_id)
        current = self.evaluate(row.project_workspace_id, row.aggregate_json)
        before, after = (
            {r["requirement_code"]: r for r in row.snapshot_json.get("requirements", [])},
            {r["requirement_code"]: r for r in current["requirements"]},
        )
        return {
            "persisted": False,
            "assessment_id": row.id,
            "historical_hash": row.assessment_hash,
            "readiness": current,
            "deltas": {
                "new_requirements": sorted(after.keys() - before.keys()),
                "removed_requirements": sorted(before.keys() - after.keys()),
                "changed_requirements": sorted(k for k in before.keys() & after.keys() if before[k] != after[k]),
                "context_delta": {"before": row.snapshot_json.get("context"), "after": current["context"]},
                "coverage_delta": {"before": row.snapshot_json.get("coverage"), "after": current["coverage"]},
                "new_blockers": sorted(set(current["blockers"]) - set(row.snapshot_json.get("blockers", []))),
            },
        }

    def refresh_apply(self, assessment_id, expected, payload, key):
        self._assessment(assessment_id)

        def apply():
            row = self._assessment(assessment_id, lock=True)
            self._version(row.revision_version, expected)
            if row.status != "COMPLETED":
                self._error(409, "OWNER_CAPABILITY_COMPLETED_PREDECESSOR_REQUIRED")
            result = self._new_assessment(
                row.project_workspace_id,
                AssessmentCreateIn(title=row.title, comments=payload.comments),
                predecessor=row,
            )
            self._event(
                "owner_capability.assessment.refreshed",
                "OwnerCapabilityAssessment",
                result["id"],
                {"predecessor_id": row.id, "historical_hash_unchanged": row.assessment_hash},
            )
            return result

        return self._command(
            "assessment.refresh",
            key,
            {"id": assessment_id, "expected": expected, "payload": payload.model_dump()},
            apply,
        )

    def provider_evidence(self, project_id):
        current = self.current_readiness(project_id)
        row = self._latest(project_id)
        eligible = bool(
            row
            and row.status == "COMPLETED"
            and current["readiness_status"] == "READY"
            and current["source_current"]
            and current["applicable"]
        )
        if not eligible:
            return {
                "status": "NOT_AVAILABLE",
                "provider_key": PROVIDER_KEY,
                "source_module": SOURCE_MODULE,
                "evidence_type": EVIDENCE_TYPE,
                "project_id": project_id,
                "readiness_status": current["readiness_status"],
                "source_current": False,
                "warnings": current["warnings"],
                "blockers": current["blockers"],
            }
        snapshot = deepcopy(row.snapshot_json)
        return {
            "status": "AVAILABLE",
            "provider_key": PROVIDER_KEY,
            "source_module": SOURCE_MODULE,
            "evidence_type": EVIDENCE_TYPE,
            "project_id": project_id,
            "assessment_id": row.id,
            "assessment_version": row.assessment_version,
            "assessment_hash": row.assessment_hash,
            "evidence_hash": row.assessment_hash,
            "framework": snapshot["policy"].get("framework", {}),
            "configuration": snapshot["configuration"],
            "readiness_status": "READY",
            "readiness": "READY",
            "dimension_readiness": snapshot["dimensions"],
            "coverage": snapshot["coverage"],
            "critical_gaps": snapshot["critical_gaps"],
            "mitigation_summary": snapshot["mitigation_summary"],
            "warnings": snapshot["warnings"],
            "blockers": snapshot["blockers"],
            "as_of": snapshot["as_of"],
            "as_of_date": snapshot["as_of"],
            "source_current": True,
            "evidence_refs": snapshot["evidence_refs"],
        }

    # Framework remains a canonical AdminConfiguration, not a second policy store.
    def _configuration(self, configuration_id, *, lock=False):
        stmt = select(AdminConfiguration).where(
            AdminConfiguration.tenant_id == self.tenant_id,
            AdminConfiguration.kind == CONFIGURATION_KIND,
            AdminConfiguration.id == configuration_id,
        )
        row = self.db.scalar(stmt.with_for_update().execution_options(populate_existing=True) if lock else stmt)
        if row is None or not self._config_visible(row):
            self._error(404, "OWNER_CAPABILITY_CONFIGURATION_NOT_FOUND")
        return row

    def _authors(self, row):
        events = self.db.scalars(
            select(SecurityEvent).where(
                SecurityEvent.tenant_id == self.tenant_id,
                SecurityEvent.target_type == "AdminConfiguration",
                SecurityEvent.target_id == row.id,
                SecurityEvent.event_type.in_(
                    [
                        "owner_capability.config.seeded",
                        "owner_capability.config.cloned",
                        "owner_capability.config.updated",
                    ]
                ),
            )
        ).all()
        return {row.created_by_user_id, *(e.user_id for e in events)}, any(
            e.metadata_json.get("author_cannot_publish_required", False) for e in events
        )

    def _configuration_out(self, row, **_kwargs):
        result = _json(
            {
                key: getattr(row, key)
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
        actions = self._allowed_actions(row.content_json.get("scope", {}).get("workspace_id"))
        authors, inherited = self._authors(row)
        can_publish = "config_publish" in actions and (
            not (inherited or row.content_json.get("separation_of_duties", {}).get("author_cannot_publish", True))
            or self.actor_id not in authors
        )
        result["allowed_actions"] = (
            (["clone"] if "config_prepare" in actions else [])
            + (["edit"] if row.status == "draft" and "config_prepare" in actions else [])
            + (["publish"] if row.status == "draft" and can_publish else [])
            + (["archive"] if row.status == "published" and "config_publish" in actions else [])
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
                "owner_capability.config.cloned",
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

    def update_configuration(self, configuration_id, expected, payload, key):
        self._configuration(configuration_id)

        def apply():
            row = self._configuration(configuration_id, lock=True)
            self._version(row.version, expected)
            if row.status != "draft":
                self._error(409, "OWNER_CAPABILITY_PUBLISHED_CONFIGURATION_IMMUTABLE")
            self._assert_config_scope(row.content_json)
            self._validate_configuration(payload.content_json)
            self._assert_config_scope(payload.content_json)
            row.name, row.description = payload.name, payload.description
            row.content_json, row.content_hash = deepcopy(payload.content_json), _hash(payload.content_json)
            row.version += 1
            row.updated_at = utc_now()
            self._event("owner_capability.config.updated", "AdminConfiguration", row.id, {})
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
                self._error(409, "OWNER_CAPABILITY_DRAFT_CONFIGURATION_REQUIRED")
            self._assert_config_scope(row.content_json)
            self._validate_configuration(row.content_json)
            authors, inherited = self._authors(row)
            if (
                inherited or row.content_json.get("separation_of_duties", {}).get("author_cannot_publish", True)
            ) and self.actor_id in authors:
                self._error(403, "OWNER_CAPABILITY_CONFIGURATION_SEPARATION_OF_DUTIES")
            row.status, row.published_at = "published", utc_now()
            row.version += 1
            row.updated_at = utc_now()
            self._event(
                "owner_capability.config.published",
                "AdminConfiguration",
                row.id,
                {"hash": row.content_hash, "existing_snapshots_untouched": True},
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
                self._error(409, "OWNER_CAPABILITY_PUBLISHED_CONFIGURATION_REQUIRED")
            row.status = "archived"
            row.version += 1
            row.updated_at = utc_now()
            self._event("owner_capability.config.archived", "AdminConfiguration", row.id, {})
            return self._configuration_out(row)

        return self._command("config.archive", key, {"id": configuration_id, "expected": expected}, apply)

    def configuration_preview(self, payload):
        record = self._configuration(payload.configuration_id) if payload.configuration_id else None
        content = deepcopy(
            payload.content_json
            if payload.content_json is not None
            else record.content_json
            if record
            else DEFAULT_CONFIGURATION
        )
        issues = self._configuration_issues(content)
        if not issues:
            self._assert_config_scope(content)
        result = {
            "persisted": False,
            "configuration": self._configuration_out(record) if record else None,
            "effective_configuration": content,
            "issues": issues,
            "warnings": ["PREVIEW_ONLY_NOT_PUBLISHED"],
            "blockers": issues,
        }
        if payload.project_id and not issues:
            project = self._project(payload.project_id)
            context = self._context(project)
            scope = content.get("scope", {}).get("workspace_id")
            if scope is not None and scope not in {w.id for w in _workspace_path(self.db, self.tenant_id, project)}:
                self._error(422, "OWNER_CAPABILITY_CONFIGURATION_PROJECT_SCOPE_MISMATCH")
            today = utc_now().date().isoformat()
            applicable = (
                self._matches(content.get("applicability", {}), context)
                and (scope is None or scope == project.id or content.get("inherit_to_descendants", True))
                and (content.get("effective_from") or today) <= today
                and (content.get("effective_to") or today) >= today
            )
            result["readiness"] = self.evaluate(
                project.id,
                resolved={
                    "project_id": project.id,
                    "configuration": self._config_ref(record, []),
                    "policy": content,
                    "context": context,
                    "maturity_scale": content["maturity_scale"],
                    "quality_scale": content["evidence_quality_scale"],
                    "dimensions": content["dimensions"],
                    "coverage_rules": content["coverage_rules"],
                    "requirements": [
                        self._tailored_requirement(r, context, content)
                        for r in content["requirements"]
                        if applicable and r.get("active", True) and self._matches(r.get("applicability", {}), context)
                    ],
                    "applicable": applicable,
                },
            )
        return result

    def _configuration_issues(self, content):
        issues = []
        if not isinstance(content, dict):
            return ["INVALID_POLICY_OBJECT"]

        def text_code(value, maximum=120):
            return isinstance(value, str) and 0 < len(value.strip()) <= maximum

        framework = content.get("framework")
        if (
            not isinstance(framework, dict)
            or not text_code(framework.get("code"))
            or not text_code(framework.get("name"), 240)
        ):
            issues.append("INVALID_CAPABILITY_FRAMEWORK")

        def mitigation_issues(value):
            if not isinstance(value, dict):
                return ["INVALID_MITIGATION_ACCEPTANCE"]
            approaches = value.get("allowed_approaches", [])
            statuses = value.get("required_statuses", ["IMPLEMENTED", "CLOSED"])
            return (
                ["INVALID_MITIGATION_ACCEPTANCE"]
                if (
                    not isinstance(value.get("accepted_mitigation_sufficient", False), bool)
                    or not isinstance(value.get("require_closure_evidence", True), bool)
                    or not isinstance(approaches, list)
                    or any(not text_code(v) for v in approaches)
                    or len(approaches) != len(set(approaches))
                    or not isinstance(statuses, list)
                    or any(not isinstance(v, str) or v not in {"ACCEPTED", "IMPLEMENTED", "CLOSED"} for v in statuses)
                    or value.get("accepted_mitigation_sufficient", False)
                    and (not approaches or not statuses)
                )
                else []
            )

        if any(
            not isinstance(content.get(k, {}), dict)
            for k in (
                "scope",
                "applicability",
                "coverage_rules",
                "separation_of_duties",
                "numbering",
                "freshness",
                "mitigation_acceptance_rules",
            )
        ):
            return ["INVALID_POLICY_OBJECT"]
        collections = ("dimensions", "requirements", "maturity_scale", "evidence_quality_scale")
        if any(not isinstance(content.get(k), list) or len(content[k]) > 2000 for k in collections):
            return ["INVALID_FRAMEWORK_COLLECTION"]
        for name in ("dimensions", "maturity_scale", "evidence_quality_scale"):
            values = content[name]
            if any(
                not isinstance(v, dict)
                or not text_code(v.get("code"), 120 if name == "dimensions" else 80)
                or not text_code(v.get("name"), 240)
                or not isinstance(v.get("active", True), bool)
                for v in values
            ):
                issues.append(f"INVALID_{name.upper()}")
                continue
            if len({v["code"] for v in values}) != len(values):
                issues.append(f"DUPLICATE_{name.upper()}_CODE")
            if name.endswith("scale") and (
                not values
                or any(not isinstance(v.get("order"), int) or isinstance(v.get("order"), bool) for v in values)
                or len({v.get("order") for v in values}) != len(values)
            ):
                issues.append(f"INVALID_{name.upper()}_ORDER")
        if issues:
            return sorted(set(issues))
        maturities = {v["code"] for v in content["maturity_scale"]}
        qualities = {v["code"] for v in content["evidence_quality_scale"]}
        # Semantic separation is additive: old Gate/Basic vocabulary is untouched.
        if qualities & {"LOW_CONFIDENCE", "PRELIMINARY", "MODERATE", "HIGH"}:
            issues.append("QUALITY_CONFIDENCE_AMBIGUITY_NOT_ALLOWED")
        dimensions = {v["code"] for v in content["dimensions"] if v.get("active", True)}
        codes = []
        rule_names = (
            "stage_rules",
            "gate_profile_rules",
            "project_type_rules",
            "governance_model_rules",
            "complexity_rules",
            "risk_rules",
            "uncertainty_rules",
            "commercial_strategy_rules",
            "delivery_model_rules",
        )
        allowed_rule_fields = {
            "minimum_maturity",
            "minimum_evidence_quality",
            "minimum_quality",
            "blocking",
            "evidence_required",
            "responsible_function_required",
            "max_age_days",
            "allowed_capability_sources",
            "mitigation_acceptance_rules",
        }
        global_values = []
        for name in rule_names:
            rules = content.get(name, {})
            if not isinstance(rules, dict) or any(
                not text_code(k) or not isinstance(v, dict) or set(v) - allowed_rule_fields for k, v in rules.items()
            ):
                issues.append("INVALID_GLOBAL_TAILORING_RULE")
            else:
                global_values.extend(rules.values())

        def requirement_value_issues(value, *, required=False):
            if (
                "minimum_maturity" in value
                and (not isinstance(value["minimum_maturity"], str) or value["minimum_maturity"] not in maturities)
                or required
                and "minimum_maturity" not in value
            ):
                issues.append("INVALID_MINIMUM_MATURITY")
            q = value.get("minimum_evidence_quality", value.get("minimum_quality"))
            if q is not None and (not isinstance(q, str) or q not in qualities) or required and q is None:
                issues.append("INVALID_MINIMUM_EVIDENCE_QUALITY")
            if any(
                k in value and not isinstance(value[k], bool)
                for k in ("blocking", "evidence_required", "responsible_function_required", "active")
            ):
                issues.append("INVALID_REQUIREMENT_FLAG")
            if value.get("max_age_days") is not None and (
                not isinstance(value["max_age_days"], int)
                or isinstance(value["max_age_days"], bool)
                or not 0 <= value["max_age_days"] <= 36500
            ):
                issues.append("INVALID_FRESHNESS")
            if "allowed_capability_sources" in value and (
                not isinstance(value["allowed_capability_sources"], list)
                or not value["allowed_capability_sources"]
                or any(
                    not isinstance(v, str) or v not in {"INTERNAL", "EXTERNAL_CONTRACTED", "HYBRID"}
                    for v in value["allowed_capability_sources"]
                )
            ):
                issues.append("INVALID_CAPABILITY_SOURCE_POLICY")
            if "mitigation_acceptance_rules" in value:
                issues.extend(mitigation_issues(value["mitigation_acceptance_rules"]))

        # Empty frameworks remain valid drafts, but their global rules must still
        # be well-typed before preview/publish. Validate each global rule once.
        for value in global_values:
            requirement_value_issues(value)
        for req in content["requirements"]:
            if (
                not isinstance(req, dict)
                or not text_code(req.get("requirement_code"))
                or not text_code(req.get("name"), 240)
                or not isinstance(req.get("dimension"), str)
                or req.get("dimension") not in dimensions
            ):
                issues.append("INVALID_REQUIREMENT")
                continue
            codes.append(req["requirement_code"])
            values = [req]
            for name in rule_names:
                rules = req.get(name, {})
                if not isinstance(rules, dict) or any(
                    not text_code(k) or not isinstance(v, dict) or set(v) - allowed_rule_fields
                    for k, v in rules.items()
                ):
                    issues.append("INVALID_TAILORING_RULE")
                else:
                    values.extend(rules.values())
            for value in values:
                requirement_value_issues(value, required=value is req)
            issues.extend(self._applicability_issues(req.get("applicability", {})))
        if len(codes) != len(set(codes)):
            issues.append("DUPLICATE_REQUIREMENT_CODE")
        issues.extend(self._applicability_issues(content.get("applicability", {})))
        coverage = content.get("coverage_rules", {}).get("minimum_percent", 100)
        if isinstance(coverage, bool) or not isinstance(coverage, int | float) or not 0 <= coverage <= 100:
            issues.append("INVALID_COVERAGE_PERCENT")
        scope = content.get("scope", {})
        if (
            not isinstance(scope.get("type"), str)
            or scope.get("type") not in {"tenant", "enterprise", "business-unit", "portfolio"}
            or (scope.get("type") == "tenant") != (scope.get("workspace_id") is None)
            or (
                scope.get("workspace_id") is not None
                and (
                    not isinstance(scope["workspace_id"], int)
                    or isinstance(scope["workspace_id"], bool)
                    or scope["workspace_id"] <= 0
                )
            )
        ):
            issues.append("INVALID_CONFIGURATION_SCOPE")
        n = content.get("numbering", DEFAULT_CONFIGURATION["numbering"])
        if (
            not isinstance(n.get("prefix"), str)
            or not 1 <= len(n["prefix"]) <= 20
            or not isinstance(n.get("padding", 6), int)
            or isinstance(n.get("padding", 6), bool)
            or not 1 <= n.get("padding", 6) <= 12
            or not isinstance(n.get("separator", "-"), str)
            or len(n.get("separator", "-")) > 3
        ):
            issues.append("INVALID_NUMBERING")
        if any(
            not isinstance(content.get("separation_of_duties", {}).get(k, True), bool)
            for k in ("author_cannot_publish", "preparer_cannot_complete")
        ) or not isinstance(content.get("inherit_to_descendants", True), bool):
            issues.append("INVALID_GOVERNANCE_FLAG")
        issues.extend(mitigation_issues(content.get("mitigation_acceptance_rules", {})))
        freshness = content.get("freshness", {})
        sources = freshness.get(
            "material_context_sources", DEFAULT_CONFIGURATION["freshness"]["material_context_sources"]
        )
        allowed_sources = set(DEFAULT_CONFIGURATION["freshness"]["material_context_sources"])
        if not isinstance(sources, list) or any(not isinstance(v, str) or v not in allowed_sources for v in sources):
            issues.append("INVALID_MATERIAL_CONTEXT_SOURCES")
        age = freshness.get("max_age_days")
        if age is not None and (not isinstance(age, int) or isinstance(age, bool) or not 0 <= age <= 36500):
            issues.append("INVALID_FRESHNESS")
        parsed_dates = {}
        for key in ("effective_from", "effective_to"):
            if content.get(key) is not None:
                try:
                    parsed_dates[key] = date.fromisoformat(content[key])
                except (ValueError, TypeError):
                    issues.append("INVALID_EFFECTIVE_DATE")
        if len(parsed_dates) == 2 and parsed_dates["effective_to"] < parsed_dates["effective_from"]:
            issues.append("INVALID_EFFECTIVE_DATE_RANGE")
        stack = [content]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                if set(node) & {"script", "expression", "formula", "python", "javascript"}:
                    issues.append("EXECUTABLE_POLICY_NOT_ALLOWED")
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
        return sorted(set(issues))

    @staticmethod
    def _applicability_issues(value):
        return (
            []
            if isinstance(value, dict)
            and all(
                k in APPLICABILITY_FIELDS
                and isinstance(v, list)
                and len(v) <= 1000
                and all(isinstance(s, str) and 0 < len(s.strip()) <= 120 for s in v)
                for k, v in value.items()
            )
            else ["INVALID_APPLICABILITY"]
        )

    def _validate_configuration(self, content):
        issues = self._configuration_issues(content)
        if issues:
            raise HTTPException(422, detail={"code": "INVALID_OWNER_CAPABILITY_CONFIGURATION", "issues": issues})

    def _allowed_actions(self, project_id=None):
        if project_id in self._action_cache:
            return self._action_cache[project_id]
        if self.context is None:
            return []
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
            "assessment_create": "assessment.create",
            "assessment_edit": "assessment.edit",
            "assessment_submit": "assessment.submit",
            "assessment_review": "assessment.review",
            "assessment_complete": "assessment.complete",
            "mitigation_edit": "mitigation.edit",
            "config_prepare": "admin.configure",
            "config_publish": "admin.publish",
        }
        result = [a for a, p in mapping.items() if f"owner_capability.{p}" in permissions]
        self._action_cache[project_id] = result
        return result

    def _command(self, command, key, request, apply):
        if not key or len(key) > 160:
            self._error(422, "IDEMPOTENCY_KEY_REQUIRED")
        self.db.scalar(select(Tenant).where(Tenant.id == self.tenant_id).with_for_update())
        request_hash = _hash({"actor": self.actor_id, "request": request})
        old = self.db.scalar(
            select(OwnerCapabilityCommand).where(
                OwnerCapabilityCommand.tenant_id == self.tenant_id, OwnerCapabilityCommand.idempotency_key == key
            )
        )
        if old:
            if old.command_type != command or old.request_hash != request_hash:
                self._error(409, "IDEMPOTENCY_KEY_REUSED")
            return deepcopy(old.result_json)
        try:
            result = _json(apply())
            self.db.add(
                OwnerCapabilityCommand(
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
            raise HTTPException(409, detail={"code": "OWNER_CAPABILITY_CONCURRENT_CONFLICT"}) from exc
        except Exception:
            self.db.rollback()
            raise
