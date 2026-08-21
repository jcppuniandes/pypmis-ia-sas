"""Gate 05A configuration service for the PROJECT Workspace Type.

This module deliberately configures reusable ADMIN metadata only. It does not
create a Project Workspace and is therefore safe to execute before Gate 05B.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domain.models import (
    AdminConfiguration,
    AdminNumberSequence,
    EnterpriseWorkspace,
    SecurityEvent,
    Tenant,
)
from app.modules.enterprise_structure.models import EnterpriseWorkspaceClassification
from app.modules.enterprise_structure.project_schemas import (
    ProjectConfigurationOut,
    ProjectCreationPolicyUpdate,
    ProjectGovernancePolicyPreviewRequest,
    ProjectGovernancePolicyUpdate,
    ProjectNumberingUpdate,
    ProjectParentOption,
    ProjectPreviewOut,
    ProjectPreviewRequest,
    ProjectTemplatePayload,
    ProjectTemplateUpdate,
    ProjectTemplateValidationOut,
)
from app.modules.enterprise_structure.record_codes import next_record_code
from app.modules.enterprise_structure.schemas import ConfigurationVersionOut
from app.modules.project_creation.governance import ProjectGovernancePolicyService

PROJECT_ALLOWED_PARENTS = ("portfolio", "program")
PROJECT_NUMBERING_CODE = "project-workspace"
PROJECT_POLICY_CODE = "project-creation"
PROJECT_CONFIGURATION_VERSION = "gate-05a-v1.0"

PROJECT_TEMPLATE_SEED: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    (
        "PYP-PRJ-GENERAL",
        "Proyecto general",
        "Plantilla base para Project Workspaces sin especializacion sectorial.",
        ("scope-manager", "schedule-manager", "cost-manager"),
    ),
    (
        "PYP-PRJ-CONSULTING",
        "Consultoria",
        "Plantilla para proyectos de consultoria y asistencia tecnica.",
        ("scope-manager", "schedule-manager", "cost-manager"),
    ),
    (
        "PYP-PRJ-PMO",
        "PMO",
        "Plantilla para servicios y proyectos de Project Management Office.",
        ("scope-manager", "schedule-manager", "cost-manager"),
    ),
    (
        "PYP-PRJ-TECH",
        "Tecnologia",
        "Plantilla para desarrollo e implantacion tecnologica.",
        ("scope-manager", "schedule-manager"),
    ),
    (
        "PYP-PRJ-CONSTRUCTION",
        "Construccion",
        "Plantilla para ejecucion y control de proyectos de construccion.",
        ("scope-manager", "schedule-manager", "cost-manager"),
    ),
)

PROJECT_CLASSIFICATION_PROPOSALS: dict[str, dict[str, Any]] = {
    "project-phase": {
        "name": "Project Phase",
        "description": "Propuesta controlada de fases para Project Workspaces.",
        "items": [
            {"code": "initiation", "label": "Initiation"},
            {"code": "planning", "label": "Planning"},
            {"code": "execution", "label": "Execution"},
            {"code": "closing", "label": "Closing"},
        ],
    },
    "priority": {
        "name": "Project Priority",
        "description": "Propuesta controlada de prioridad para Project Workspaces.",
        "items": [
            {"code": "high", "label": "High"},
            {"code": "medium", "label": "Medium"},
            {"code": "low", "label": "Low"},
        ],
    },
    "region": {
        "name": "Project Region",
        "description": "Propuesta controlada de region para Project Workspaces.",
        "items": [
            {"code": "caribbean", "label": "Caribbean"},
            {"code": "andean", "label": "Andean"},
            {"code": "pacific", "label": "Pacific"},
            {"code": "orinoquia-amazonia", "label": "Orinoquia / Amazonia"},
        ],
    },
}


class ProjectWorkspaceConfigurationService:
    """Tenant-scoped reuse layer for Project Workspace ADMIN configuration."""

    def __init__(self, db: Session, tenant_id: int, actor_id: int) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.actor_id = actor_id

    def ensure_seed(self) -> None:
        self.db.execute(select(Tenant.id).where(Tenant.id == self.tenant_id).with_for_update()).scalar_one()
        self._seed_numbering_rule()
        self._seed_creation_policy()
        self._seed_templates()
        self._seed_classification_proposals()
        ProjectGovernancePolicyService(self.db, self.tenant_id, self.actor_id).ensure_seed()
        self.db.commit()

    def overview(self) -> ProjectConfigurationOut:
        project_type = self._latest("workspace_type", "project", published_only=True)
        numbering = self._latest("numbering_rule", PROJECT_NUMBERING_CODE, published_only=True)
        policy = self._latest("creation_policy", PROJECT_POLICY_CODE, published_only=True)
        if project_type is None or numbering is None or policy is None:
            raise HTTPException(status_code=409, detail="Gate 05A configuration seed is incomplete")
        templates = self._latest_by_code("project_template", include_archived=True)
        classifications = [
            item
            for item in self._latest_by_code("catalog", include_archived=False)
            if item.code in {"strategic-objective", "project-type", *PROJECT_CLASSIFICATION_PROPOSALS}
        ]
        modules = self._published_modules()
        parents = self._parent_options()
        governance_models = ProjectGovernancePolicyService(self.db, self.tenant_id, self.actor_id).list_policies()
        return ProjectConfigurationOut(
            project_type=_configuration_out(project_type),
            templates=[_configuration_out(item) for item in templates],
            numbering_rule=_configuration_out(numbering),
            creation_policy=_configuration_out(policy),
            governance_models=governance_models,
            classification_sets=[_configuration_out(item) for item in classifications],
            available_modules=[_configuration_out(item) for item in modules],
            parent_options=parents,
            allowed_parent_types=list(PROJECT_ALLOWED_PARENTS),
            summary={
                "templates": len(templates),
                "draft_templates": sum(item.status == "draft" for item in templates),
                "published_templates": sum(item.status == "published" for item in templates),
                "classification_proposals": sum(item.status == "draft" for item in classifications),
                "available_modules": len(modules),
                "eligible_parents": len(parents),
            },
            gate_status="READY_FOR_PROJECT_CREATION_PROCESS",
            gate_05b_contract={
                "workspace_table": "enterprise_workspaces",
                "workspace_type_code": "project",
                "allowed_parent_types": list(PROJECT_ALLOWED_PARENTS),
                "numbering_rule_code": PROJECT_NUMBERING_CODE,
                "creation_policy_code": PROJECT_POLICY_CODE,
                "template_kind": "project_template",
                "materialization_endpoint": None,
                "configuration_requires_core_revision": False,
            },
            multi_source_status="READY_FOR_MULTI_SOURCE_PROJECT_CREATION",
        )

    def create_template(self, payload: ProjectTemplatePayload) -> ConfigurationVersionOut:
        code = _required_code(payload.code)
        if self._latest("project_template", code) is not None:
            raise HTTPException(status_code=409, detail=f"Project Template already exists: {code}")
        content = self._template_content(payload)
        record = self._new_configuration(
            "project_template", code, payload.name, payload.description, content, status="draft", revision=1
        )
        self.db.flush()
        self._event("enterprise_structure.project_template.created", record)
        self._commit("Project Template code already exists")
        return _configuration_out(record)

    def clone_template(self, configuration_id: int) -> ConfigurationVersionOut:
        source = self._configuration(configuration_id, "project_template")
        if source.status != "published":
            raise HTTPException(status_code=409, detail="Only a published Project Template can be cloned")
        latest = self._latest("project_template", source.code)
        if latest is not None and latest.status == "draft":
            raise HTTPException(status_code=409, detail="A Project Template draft already exists")
        clone = self._new_configuration(
            source.kind,
            source.code,
            source.name,
            source.description,
            json.loads(json.dumps(source.content_json)),
            status="draft",
            revision=self._next_revision(source.kind, source.code),
        )
        self.db.flush()
        self._event(
            "enterprise_structure.project_template.created",
            clone,
            {"action": "clone", "source_id": source.id},
        )
        self._commit("A Project Template draft already exists")
        return _configuration_out(clone)

    def update_template(self, configuration_id: int, payload: ProjectTemplateUpdate) -> ConfigurationVersionOut:
        record = self._configuration(configuration_id, "project_template")
        self._require_draft(record)
        if record.version != payload.expected_version:
            raise HTTPException(status_code=409, detail="Project Template changed concurrently; refresh and retry")
        code = _required_code(payload.code)
        if code != record.code:
            raise HTTPException(status_code=409, detail="Project Template code is immutable after creation")
        duplicate = self.db.scalar(
            select(AdminConfiguration.id).where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == "project_template",
                AdminConfiguration.code == code,
                AdminConfiguration.id != record.id,
                AdminConfiguration.revision == record.revision,
            )
        )
        if duplicate is not None:
            raise HTTPException(status_code=409, detail=f"Project Template code already exists: {code}")
        record.code = code
        record.name = payload.name.strip()
        record.description = payload.description.strip()
        record.content_json = self._template_content(payload)
        record.version += 1
        record.updated_at = utc_now()
        record.content_hash = _content_hash(record)
        self._event("enterprise_structure.project_template.updated", record)
        self._commit("Project Template changed concurrently")
        return _configuration_out(record)

    def validate_template(self, configuration_id: int) -> ProjectTemplateValidationOut:
        record = self._configuration(configuration_id, "project_template")
        issues, warnings = self._template_issues(record.content_json)
        return ProjectTemplateValidationOut(
            valid=not issues,
            issues=issues,
            warnings=warnings,
            configuration_ids=[record.id],
            content_hash=record.content_hash,
        )

    def publish_template(self, configuration_id: int, expected_hash: str) -> ConfigurationVersionOut:
        record = self._configuration(configuration_id, "project_template")
        self._require_draft(record)
        issues, _warnings = self._template_issues(record.content_json)
        if issues:
            raise HTTPException(status_code=422, detail={"message": "Project Template is invalid", "issues": issues})
        if record.content_hash != expected_hash:
            raise HTTPException(status_code=409, detail="Project Template changed after validation")
        record.status = "published"
        record.published_at = utc_now()
        record.version += 1
        record.updated_at = utc_now()
        record.content_hash = _content_hash(record)
        self._event("enterprise_structure.project_template.published", record)
        self._commit("Project Template changed concurrently")
        return _configuration_out(record)

    def archive_template(self, configuration_id: int) -> ConfigurationVersionOut:
        source = self._configuration(configuration_id, "project_template")
        if source.status == "archived":
            return _configuration_out(source)
        if source.status == "published":
            record = self._new_configuration(
                source.kind,
                source.code,
                source.name,
                source.description,
                json.loads(json.dumps(source.content_json)),
                status="archived",
                revision=self._next_revision(source.kind, source.code),
            )
        else:
            record = source
            record.status = "archived"
            record.version += 1
            record.updated_at = utc_now()
            record.content_hash = _content_hash(record)
        self.db.flush()
        self._event("enterprise_structure.project_template.updated", record, {"action": "archive"})
        self._commit("Project Template changed concurrently")
        return _configuration_out(record)

    def configure_numbering(self, payload: ProjectNumberingUpdate) -> ConfigurationVersionOut:
        prefix = payload.prefix.strip().upper().strip("-")
        if not prefix or any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-" for character in prefix):
            raise HTTPException(status_code=422, detail="Numbering prefix may contain A-Z, 0-9 and hyphen only")
        content = {
            "prefix": prefix,
            "pattern": f"{{prefix}}-{{sequence:0{payload.padding}d}}",
            "padding": payload.padding,
            "start": payload.start,
            "scope": "tenant",
            "unique": True,
            "no_reuse": payload.no_reuse,
            "preview_only_until_gate_05b": True,
            "configuration_version": PROJECT_CONFIGURATION_VERSION,
        }
        record = self._replace_published_configuration(
            "numbering_rule",
            PROJECT_NUMBERING_CODE,
            "Project Workspace Numbering",
            "Numeracion de negocio separada del id y del Record Code.",
            content,
        )
        self._event("enterprise_structure.project_numbering.configured", record)
        self._commit("Project numbering rule changed concurrently")
        return _configuration_out(record)

    def configure_creation_policy(self, payload: ProjectCreationPolicyUpdate) -> ConfigurationVersionOut:
        parents = _normalized_parent_types(payload.allowed_parent_types)
        if set(parents) != set(PROJECT_ALLOWED_PARENTS):
            raise HTTPException(status_code=422, detail="PROJECT parents must be PORTFOLIO and PROGRAM")
        if payload.initial_status not in {"draft", "pending"}:
            raise HTTPException(status_code=422, detail="Initial Project status must be draft or pending")
        content = {
            **payload.model_dump(),
            "allowed_parent_types": parents,
            "workspace_type_code": "project",
            "configuration_only": True,
            "configuration_version": PROJECT_CONFIGURATION_VERSION,
        }
        record = self._replace_published_configuration(
            "creation_policy",
            PROJECT_POLICY_CODE,
            "Project Creation Policy",
            "Guardrails declarativos para el futuro Project Creation Process de Gate 05B.",
            content,
        )
        self._event("enterprise_structure.project_creation_policy.configured", record)
        self._commit("Project creation policy changed concurrently")
        return _configuration_out(record)

    def configure_governance_policy(
        self,
        governance_model: str,
        payload: ProjectGovernancePolicyUpdate,
    ) -> dict[str, Any]:
        values = payload.model_dump(exclude={"scope_workspace_id"})
        return ProjectGovernancePolicyService(self.db, self.tenant_id, self.actor_id).configure(
            governance_model,
            values,
            scope_workspace_id=payload.scope_workspace_id,
        )

    def preview_governance_policy(self, payload: ProjectGovernancePolicyPreviewRequest) -> dict[str, Any]:
        return ProjectGovernancePolicyService(self.db, self.tenant_id, self.actor_id).preview(payload.model_dump())

    def preview(self, payload: ProjectPreviewRequest) -> ProjectPreviewOut:
        parent = self.db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.tenant_id == self.tenant_id,
                EnterpriseWorkspace.id == payload.parent_id,
            )
        )
        if parent is None:
            raise HTTPException(status_code=404, detail="Parent Workspace not found")
        template = self._configuration(payload.template_id, "project_template")
        if template.status == "archived":
            raise HTTPException(status_code=409, detail="Archived Project Template cannot be previewed")
        policy = self._latest("creation_policy", PROJECT_POLICY_CODE, published_only=True)
        numbering = self._latest("numbering_rule", PROJECT_NUMBERING_CODE, published_only=True)
        if policy is None or numbering is None:
            raise HTTPException(status_code=409, detail="Project configuration is incomplete")
        issues: list[str] = []
        allowed_parents = set(policy.content_json.get("allowed_parent_types", PROJECT_ALLOWED_PARENTS))
        if parent.workspace_type_code not in allowed_parents:
            issues.append(f"PROJECT is not allowed below {parent.workspace_type_code.upper()}")
        template_parents = set(template.content_json.get("applicable_parent_types", []))
        if parent.workspace_type_code not in template_parents:
            issues.append(f"Template {template.code} does not apply to {parent.workspace_type_code.upper()}")
        if parent.status not in {"active", "draft"}:
            issues.append("Parent Workspace is not available for project creation")
        sibling_codes = list(
            self.db.scalars(
                select(EnterpriseWorkspace.record_code).where(
                    EnterpriseWorkspace.tenant_id == self.tenant_id,
                    EnterpriseWorkspace.parent_id == parent.id,
                )
            ).all()
        )
        projected_record_code = next_record_code(parent.record_code, sibling_codes)
        projected_project_number = self._number_preview(numbering)
        inherited = self._inherited_classifications(parent.id, template.content_json)
        if policy.content_json.get("strategic_objective_required", True) and not any(
            item.get("category_set_code") == "strategic-objective" for item in inherited
        ):
            issues.append("A strategic objective is required and is not inherited from the selected parent/template")
        modules = self._valid_module_codes(template.content_json.get("enabled_modules", []))
        return ProjectPreviewOut(
            allowed=not issues,
            parent=_parent_out(parent),
            template_code=template.code,
            projected_record_code=projected_record_code,
            projected_project_number=projected_project_number,
            inherited_classifications=inherited,
            enabled_modules=modules,
            initial_status=str(policy.content_json.get("initial_status", "pending")),
            issues=issues,
            persisted=False,
        )

    def issue_project_number(self, *, scope_key: str = "tenant") -> str:
        """Contract for Gate 05B; allocates only a business number, never a workspace."""
        value = self.reserve_project_number(scope_key=scope_key)
        self._commit("Project number sequence changed concurrently; retry")
        return value

    def reserve_project_number(self, *, scope_key: str = "tenant") -> str:
        """Reserve a Project Number inside the caller's transaction without committing it."""
        rule = self._latest("numbering_rule", PROJECT_NUMBERING_CODE, published_only=True)
        if rule is None:
            raise HTTPException(status_code=409, detail="Published Project numbering rule not found")
        sequence = self.db.scalar(
            update(AdminNumberSequence)
            .where(
                AdminNumberSequence.tenant_id == self.tenant_id,
                AdminNumberSequence.rule_code == PROJECT_NUMBERING_CODE,
                AdminNumberSequence.scope_key == scope_key,
            )
            .values(
                next_value=AdminNumberSequence.next_value + 1,
                version=AdminNumberSequence.version + 1,
                updated_at=utc_now(),
            )
            .returning(AdminNumberSequence.next_value - 1)
        )
        if sequence is None:
            raise HTTPException(status_code=409, detail="Project number sequence is not initialized")
        return _format_number(rule.content_json, sequence)

    def _seed_numbering_rule(self) -> None:
        rule = self._latest("numbering_rule", PROJECT_NUMBERING_CODE, published_only=True)
        if rule is None:
            payload = ProjectNumberingUpdate()
            content = {
                "prefix": payload.prefix,
                "pattern": "{prefix}-{sequence:05d}",
                "padding": payload.padding,
                "start": payload.start,
                "scope": "tenant",
                "unique": True,
                "no_reuse": True,
                "preview_only_until_gate_05b": True,
                "configuration_version": PROJECT_CONFIGURATION_VERSION,
            }
            rule = self._new_configuration(
                "numbering_rule",
                PROJECT_NUMBERING_CODE,
                "Project Workspace Numbering",
                "Numeracion PYP-PRJ-00001 separada del Record Code.",
                content,
                status="published",
                revision=1,
            )
            rule.published_at = utc_now()
            self.db.flush()
            self._event("enterprise_structure.project_numbering.configured", rule, {"action": "seed"})
        counter = self.db.scalar(
            select(AdminNumberSequence).where(
                AdminNumberSequence.tenant_id == self.tenant_id,
                AdminNumberSequence.rule_code == PROJECT_NUMBERING_CODE,
                AdminNumberSequence.scope_key == "tenant",
            )
        )
        if counter is None:
            self.db.add(
                AdminNumberSequence(
                    tenant_id=self.tenant_id,
                    rule_code=PROJECT_NUMBERING_CODE,
                    scope_key="tenant",
                    next_value=int(rule.content_json.get("start", 1)),
                    version=1,
                )
            )

    def _seed_creation_policy(self) -> None:
        if self._latest("creation_policy", PROJECT_POLICY_CODE, published_only=True) is not None:
            return
        payload = ProjectCreationPolicyUpdate()
        content = {
            **payload.model_dump(),
            "workspace_type_code": "project",
            "configuration_only": True,
            "configuration_version": PROJECT_CONFIGURATION_VERSION,
        }
        record = self._new_configuration(
            "creation_policy",
            PROJECT_POLICY_CODE,
            "Project Creation Policy",
            "Configuracion previa del Project Creation Process; no materializa Project Workspaces.",
            content,
            status="published",
            revision=1,
        )
        record.published_at = utc_now()
        self.db.flush()
        self._event("enterprise_structure.project_creation_policy.configured", record, {"action": "seed"})

    def _seed_templates(self) -> None:
        valid_modules = {item.code for item in self._published_modules()}
        for code, name, description, proposed_modules in PROJECT_TEMPLATE_SEED:
            if self._latest("project_template", code) is not None:
                continue
            content = {
                "applicable_parent_types": list(PROJECT_ALLOWED_PARENTS),
                "default_classifications": [],
                "enabled_modules": [code for code in proposed_modules if code in valid_modules],
                "default_role_codes": [],
                "default_group_codes": [],
                "numbering_rule_code": PROJECT_NUMBERING_CODE,
                "default_attributes": {"currency": "COP", "country": "CO"},
                "creation_policy_code": PROJECT_POLICY_CODE,
                "configuration_version": PROJECT_CONFIGURATION_VERSION,
            }
            record = self._new_configuration(
                "project_template", code, name, description, content, status="draft", revision=1
            )
            self.db.flush()
            self._event("enterprise_structure.project_template.created", record, {"action": "seed"})

    def _seed_classification_proposals(self) -> None:
        for code, definition in PROJECT_CLASSIFICATION_PROPOSALS.items():
            if self._latest("catalog", code) is not None:
                continue
            content = {
                "applicable_types": ["project"],
                "items": definition["items"],
                "proposal_only": True,
                "configuration_version": PROJECT_CONFIGURATION_VERSION,
            }
            self._new_configuration(
                "catalog",
                code,
                definition["name"],
                definition["description"],
                content,
                status="draft",
                revision=1,
            )

    def _template_content(self, payload: ProjectTemplatePayload) -> dict[str, Any]:
        parents = _normalized_parent_types(payload.applicable_parent_types)
        content = {
            "applicable_parent_types": parents,
            "default_classifications": payload.default_classifications,
            "enabled_modules": sorted(set(payload.enabled_modules)),
            "default_role_codes": sorted(set(payload.default_role_codes)),
            "default_group_codes": sorted(set(payload.default_group_codes)),
            "numbering_rule_code": payload.numbering_rule_code.strip(),
            "default_attributes": payload.default_attributes,
            "creation_policy_code": payload.creation_policy_code.strip(),
            "configuration_version": PROJECT_CONFIGURATION_VERSION,
        }
        issues, _warnings = self._template_issues(content)
        if issues:
            raise HTTPException(status_code=422, detail={"message": "Invalid Project Template", "issues": issues})
        return content

    def _template_issues(self, content: dict[str, Any]) -> tuple[list[str], list[str]]:
        issues: list[str] = []
        warnings: list[str] = []
        parents = content.get("applicable_parent_types")
        if not isinstance(parents, list) or not parents:
            issues.append("At least one applicable parent type is required")
        elif any(item not in PROJECT_ALLOWED_PARENTS for item in parents):
            issues.append("Project Templates may apply only to PORTFOLIO and PROGRAM")
        unknown_modules = sorted(
            set(content.get("enabled_modules", [])) - {item.code for item in self._published_modules()}
        )
        if unknown_modules:
            issues.append(f"Unknown or unpublished modules: {', '.join(unknown_modules)}")
        classifications = content.get("default_classifications", [])
        if not isinstance(classifications, list):
            issues.append("default_classifications must be a list")
        else:
            available = {item.code: item for item in self._latest_by_code("catalog", include_archived=False)}
            for classification in classifications:
                category_code = str(classification.get("category_set_code", ""))
                item_code = str(classification.get("category_item_code", ""))
                category = available.get(category_code)
                if category is None:
                    issues.append(f"Unknown classification set: {category_code}")
                    continue
                if "project" not in category.content_json.get("applicable_types", []):
                    issues.append(f"Classification set does not apply to PROJECT: {category_code}")
                valid_items = {item.get("code") for item in category.content_json.get("items", [])}
                if item_code not in valid_items:
                    issues.append(f"Unknown classification item: {category_code}/{item_code}")
        if not content.get("enabled_modules"):
            warnings.append("The template enables no modules; this is valid and can be completed before publication")
        if content.get("numbering_rule_code") != PROJECT_NUMBERING_CODE:
            issues.append(f"Project Templates must use numbering rule {PROJECT_NUMBERING_CODE}")
        if content.get("creation_policy_code") != PROJECT_POLICY_CODE:
            issues.append(f"Project Templates must use creation policy {PROJECT_POLICY_CODE}")
        return issues, warnings

    def _replace_published_configuration(
        self, kind: str, code: str, name: str, description: str, content: dict[str, Any]
    ) -> AdminConfiguration:
        latest = self._latest(kind, code, published_only=True)
        if latest is not None and latest.content_json == content:
            return latest
        record = self._new_configuration(
            kind,
            code,
            name,
            description,
            content,
            status="published",
            revision=self._next_revision(kind, code),
        )
        record.published_at = utc_now()
        self.db.flush()
        return record

    def _new_configuration(
        self,
        kind: str,
        code: str,
        name: str,
        description: str,
        content: dict[str, Any],
        *,
        status: str,
        revision: int,
    ) -> AdminConfiguration:
        if not name.strip():
            raise HTTPException(status_code=422, detail="Configuration name is required")
        record = AdminConfiguration(
            tenant_id=self.tenant_id,
            kind=kind,
            code=code,
            name=name.strip(),
            description=description.strip(),
            status=status,
            revision=revision,
            version=1,
            content_json=content,
            published_at=utc_now() if status == "published" else None,
            created_by_user_id=self.actor_id,
        )
        record.content_hash = _content_hash(record)
        self.db.add(record)
        return record

    def _configuration(self, configuration_id: int, kind: str) -> AdminConfiguration:
        record = self.db.scalar(
            select(AdminConfiguration).where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.id == configuration_id,
                AdminConfiguration.kind == kind,
            )
        )
        if record is None:
            raise HTTPException(status_code=404, detail="Configuration not found")
        return record

    def _latest(self, kind: str, code: str, *, published_only: bool = False) -> AdminConfiguration | None:
        statement = select(AdminConfiguration).where(
            AdminConfiguration.tenant_id == self.tenant_id,
            AdminConfiguration.kind == kind,
            AdminConfiguration.code == code,
        )
        if published_only:
            statement = statement.where(AdminConfiguration.status == "published")
        return self.db.scalar(statement.order_by(AdminConfiguration.revision.desc()).limit(1))

    def _latest_by_code(self, kind: str, *, include_archived: bool) -> list[AdminConfiguration]:
        statement = select(AdminConfiguration).where(
            AdminConfiguration.tenant_id == self.tenant_id,
            AdminConfiguration.kind == kind,
        )
        if not include_archived:
            statement = statement.where(AdminConfiguration.status != "archived")
        rows = list(
            self.db.scalars(statement.order_by(AdminConfiguration.code, AdminConfiguration.revision.desc())).all()
        )
        selected: dict[str, AdminConfiguration] = {}
        for row in rows:
            selected.setdefault(row.code, row)
        return sorted(selected.values(), key=lambda item: item.name.lower())

    def _next_revision(self, kind: str, code: str) -> int:
        maximum = self.db.scalar(
            select(func.max(AdminConfiguration.revision)).where(
                AdminConfiguration.tenant_id == self.tenant_id,
                AdminConfiguration.kind == kind,
                AdminConfiguration.code == code,
            )
        )
        return int(maximum or 0) + 1

    def _published_modules(self) -> list[AdminConfiguration]:
        return list(
            self.db.scalars(
                select(AdminConfiguration)
                .where(
                    AdminConfiguration.tenant_id == self.tenant_id,
                    AdminConfiguration.kind == "module_definition",
                    AdminConfiguration.status == "published",
                )
                .order_by(AdminConfiguration.name)
            ).all()
        )

    def _valid_module_codes(self, values: list[str]) -> list[str]:
        available = {item.code for item in self._published_modules()}
        return sorted(set(values) & available)

    def _parent_options(self) -> list[ProjectParentOption]:
        rows = list(
            self.db.scalars(
                select(EnterpriseWorkspace)
                .where(
                    EnterpriseWorkspace.tenant_id == self.tenant_id,
                    EnterpriseWorkspace.workspace_type_code.in_(PROJECT_ALLOWED_PARENTS),
                    EnterpriseWorkspace.status != "archived",
                )
                .order_by(EnterpriseWorkspace.record_code)
            ).all()
        )
        return [_parent_out(item) for item in rows]

    def _number_preview(self, rule: AdminConfiguration) -> str:
        counter = self.db.scalar(
            select(AdminNumberSequence).where(
                AdminNumberSequence.tenant_id == self.tenant_id,
                AdminNumberSequence.rule_code == PROJECT_NUMBERING_CODE,
                AdminNumberSequence.scope_key == "tenant",
            )
        )
        sequence = counter.next_value if counter is not None else int(rule.content_json.get("start", 1))
        return _format_number(rule.content_json, sequence)

    def _inherited_classifications(self, parent_id: int, template_content: dict[str, Any]) -> list[dict[str, str]]:
        inherited = [
            {
                "category_set_code": item.category_set_code,
                "category_item_code": item.category_item_code,
                "source": "parent",
            }
            for item in self.db.scalars(
                select(EnterpriseWorkspaceClassification).where(
                    EnterpriseWorkspaceClassification.tenant_id == self.tenant_id,
                    EnterpriseWorkspaceClassification.workspace_id == parent_id,
                )
            ).all()
        ]
        keys = {(item["category_set_code"], item["category_item_code"]) for item in inherited}
        for item in template_content.get("default_classifications", []):
            key = (str(item.get("category_set_code", "")), str(item.get("category_item_code", "")))
            if key in keys:
                continue
            inherited.append({"category_set_code": key[0], "category_item_code": key[1], "source": "template"})
            keys.add(key)
        return inherited

    @staticmethod
    def _require_draft(record: AdminConfiguration) -> None:
        if record.status != "draft":
            raise HTTPException(status_code=409, detail="Published Project Templates are immutable; clone first")

    def _event(self, event_type: str, target: object, metadata: dict[str, Any] | None = None) -> None:
        self.db.add(
            SecurityEvent(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                event_type=event_type,
                outcome="success",
                target_type=target.__class__.__name__,
                target_id=getattr(target, "id", None),
                metadata_json=metadata or {},
            )
        )

    def _commit(self, conflict_message: str) -> None:
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise HTTPException(status_code=409, detail=conflict_message) from exc


def _required_code(value: str) -> str:
    code = value.strip().upper().replace("_", "-").replace(" ", "-")
    if not code:
        raise HTTPException(status_code=422, detail="Project Template code is required")
    if any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-" for character in code):
        raise HTTPException(status_code=422, detail="Project Template code may contain A-Z, 0-9 and hyphen only")
    return code


def _normalized_parent_types(values: list[str]) -> list[str]:
    result = list(dict.fromkeys(item.strip().lower().replace("_", "-") for item in values if item.strip()))
    if not result:
        raise HTTPException(status_code=422, detail="At least one Project parent type is required")
    return result


def _format_number(content: dict[str, Any], sequence: int) -> str:
    try:
        return str(content["pattern"]).format(prefix=content.get("prefix", "PYP-PRJ"), sequence=sequence)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid Project numbering rule: {exc}") from exc


def _content_hash(record: AdminConfiguration) -> str:
    payload = {
        "kind": record.kind,
        "code": record.code,
        "revision": record.revision,
        "name": record.name,
        "description": record.description,
        "content": record.content_json,
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _configuration_out(record: AdminConfiguration) -> ConfigurationVersionOut:
    return ConfigurationVersionOut.model_validate(record)


def _parent_out(workspace: EnterpriseWorkspace) -> ProjectParentOption:
    return ProjectParentOption(
        id=workspace.id,
        name=workspace.name,
        workspace_type_code=workspace.workspace_type_code,
        record_code=workspace.record_code,
        status=workspace.status,
    )
