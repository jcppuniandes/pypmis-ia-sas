"""Gate 06A physical/geographic configuration over existing Enterprise engines."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import utc_now
from app.domain.models import AdminConfiguration, AdminNumberSequence, EnterpriseWorkspace, SecurityEvent, Tenant
from app.modules.enterprise_structure.constants import WORKSPACE_TYPE_SEED
from app.modules.enterprise_structure.physical_schemas import (
    PhysicalConfigurationOut,
    PhysicalCreationPolicyUpdate,
    PhysicalNumberingUpdate,
    PhysicalTemplatePayload,
    PhysicalTemplateUpdate,
    PhysicalTemplateValidationOut,
    PhysicalWorkspaceParentOption,
    PhysicalWorkspacePreviewOut,
    PhysicalWorkspacePreviewRequest,
)
from app.modules.enterprise_structure.record_codes import next_record_code
from app.modules.enterprise_structure.schemas import ConfigurationVersionOut

PHYSICAL_TYPE_CODES = ("region", "district", "site", "property", "facility", "warehouse")
RESERVED_TYPE_CODE = "linear-asset"
NUMBERING = {
    "region": ("physical-region", "REG"),
    "district": ("physical-district", "DST"),
    "site": ("physical-site", "SIT"),
    "property": ("physical-property", "PYP-PROP"),
    "facility": ("physical-facility", "PYP-FAC"),
    "warehouse": ("physical-warehouse", "PYP-WH"),
}
CREATION_TYPES = ("property", "facility", "warehouse")
COMPOSITION_CAPABILITIES = {
    "enterprise": {"region", "site", "property", "facility", "warehouse"},
    "region": {"region", "district", "site", "property", "facility", "warehouse"},
    "district": {"site", "property", "facility", "warehouse"},
    "site": {"property", "facility", "warehouse"},
    "property": {"facility", "warehouse"},
    "facility": {"warehouse"},
    "warehouse": set(),
}
TEMPLATE_SEED = (
    ("PYP-PROP-GENERAL", "Property general", "property"),
    ("PYP-FAC-GENERAL", "Facility general", "facility"),
    ("PYP-FAC-BUILDING", "Facility building", "facility"),
    ("PYP-FAC-INDUSTRIAL", "Facility industrial", "facility"),
    ("PYP-WH-GENERAL", "Warehouse general", "warehouse"),
)
GATE_VERSION = "gate-06a-v1.0"


class PhysicalWorkspaceConfigurationService:
    def __init__(self, db: Session, tenant_id: int, actor_id: int) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.actor_id = actor_id

    def ensure_seed(self) -> None:
        self.db.execute(select(Tenant.id).where(Tenant.id == self.tenant_id).with_for_update()).scalar_one()
        self._seed_numbering()
        self._seed_templates()
        self._seed_policies()
        self.db.commit()

    def configure_type(self, workspace_type_code: str, *, expected_version: int) -> ConfigurationVersionOut:
        code = _type_code(workspace_type_code)
        if code not in {*PHYSICAL_TYPE_CODES, RESERVED_TYPE_CODE}:
            raise HTTPException(status_code=422, detail="Unsupported physical Workspace Type")
        record = self._required("workspace_type", code, published_only=True)
        self._assert_version(record, expected_version)
        event = {
            "property": "enterprise_structure.property_type_configured",
            "facility": "enterprise_structure.facility_type_configured",
            "warehouse": "enterprise_structure.warehouse_type_configured",
        }.get(code, "enterprise_structure.geographic_type_configured")
        self._event(event, record, {"workspace_type_code": code, "result": "UNCHANGED"})
        self._commit("Physical Workspace Type changed concurrently")
        return _out(record)

    def overview(self) -> PhysicalConfigurationOut:
        types = [
            self._required("workspace_type", code, published_only=True)
            for code in (*PHYSICAL_TYPE_CODES, RESERVED_TYPE_CODE)
        ]
        templates = self._latest_by_code("physical_template")
        rules = [
            self._required("numbering_rule", NUMBERING[code][0], published_only=True) for code in PHYSICAL_TYPE_CODES
        ]
        policies = [self._required("creation_policy", f"physical-{code}-creation") for code in CREATION_TYPES]
        modules = self._published_modules()
        return PhysicalConfigurationOut(
            workspace_types=[_out(item) for item in types],
            composition_rules={
                code: list(
                    self._required("workspace_type", code, published_only=True).content_json.get("allowed_children", [])
                )
                for code in ("enterprise", *PHYSICAL_TYPE_CODES)
            },
            templates=[_out(item) for item in templates],
            numbering_rules=[_out(item) for item in rules],
            creation_policies=[_out(item) for item in policies],
            available_modules=[_out(item) for item in modules],
            parent_options=self._parent_options(),
            relationship_contract=[
                {"source": "project", "target": "property", "relationship_type": "LOCATED_AT"},
                {"source": "project", "target": "facility", "relationship_type": "LOCATED_AT"},
                {"source": "project", "target": "warehouse", "relationship_type": "SERVES"},
            ],
            summary={
                "active_types": len(PHYSICAL_TYPE_CODES),
                "reserved_types": 1,
                "draft_templates": sum(item.status == "draft" for item in templates),
                "draft_policies": sum(item.status == "draft" for item in policies),
                "real_instances": self._real_instance_count(),
            },
            gate_status="READY_FOR_PHYSICAL_WORKSPACE_CREATION_PROCESSES",
            exclusions={
                "asset_is_workspace_type": False,
                "linear_asset_creatable": False,
                "creation_process": False,
                "inventory": False,
                "asset_manager": False,
            },
        )

    def preview(self, payload: PhysicalWorkspacePreviewRequest) -> PhysicalWorkspacePreviewOut:
        code = _type_code(payload.workspace_type_code)
        if code not in PHYSICAL_TYPE_CODES:
            if code == RESERVED_TYPE_CODE:
                raise HTTPException(status_code=409, detail="LINEAR_ASSET is reserved and cannot be created")
            raise HTTPException(status_code=422, detail=f"Unsupported physical Workspace Type: {code}")
        workspace_type = self._required("workspace_type", code, published_only=True)
        parent = self.db.scalar(
            select(EnterpriseWorkspace).where(
                EnterpriseWorkspace.tenant_id == self.tenant_id, EnterpriseWorkspace.id == payload.parent_id
            )
        )
        if parent is None:
            raise HTTPException(status_code=404, detail="Parent Workspace not found")
        issues: list[str] = []
        warnings: list[str] = []
        parent_type = self._required("workspace_type", parent.workspace_type_code, published_only=True)
        if code not in parent_type.content_json.get("allowed_children", []):
            issues.append(f"{code.upper()} is not allowed below {parent.workspace_type_code.upper()}")
        template: AdminConfiguration | None = None
        if payload.template_id is not None:
            template = self._configuration(payload.template_id, "physical_template")
            if template.status == "archived":
                issues.append("Archived template cannot be used")
            if template.content_json.get("workspace_type_code") != code:
                issues.append(f"Template {template.code} does not apply to {code.upper()}")
            if parent.workspace_type_code not in template.content_json.get("applicable_parent_types", []):
                issues.append(f"Template {template.code} does not apply below {parent.workspace_type_code.upper()}")
        elif code in CREATION_TYPES:
            warnings.append("No DRAFT template selected; creation policy may require one in a future process")
        required = [
            str(item) for item in workspace_type.content_json.get("required_fields", []) if item not in {"code"}
        ]
        missing = [item for item in required if not str(payload.minimal_attributes.get(item, "")).strip()]
        if missing:
            issues.append(f"Missing minimal attributes: {', '.join(missing)}")
        siblings = list(
            self.db.scalars(
                select(EnterpriseWorkspace.record_code).where(
                    EnterpriseWorkspace.tenant_id == self.tenant_id, EnterpriseWorkspace.parent_id == parent.id
                )
            ).all()
        )
        numbering = self._required("numbering_rule", NUMBERING[code][0], published_only=True)
        modules = self._valid_modules(template.content_json.get("enabled_modules", []) if template else [])
        return PhysicalWorkspacePreviewOut(
            allowed=not issues,
            workspace_type_code=code,
            parent=_parent_out(parent),
            template_code=template.code if template else None,
            projected_record_code=next_record_code(parent.record_code, siblings),
            projected_business_number=self._number_preview(numbering),
            applicable_classifications=list(workspace_type.content_json.get("required_categories", [])),
            enabled_modules=modules,
            planned_modules=list(workspace_type.content_json.get("planned_modules", [])),
            initial_status="pending" if code in CREATION_TYPES else "draft",
            issues=issues,
            warnings=warnings,
            persisted=False,
        )

    def configure_composition(
        self, parent_type_code: str, allowed_children: list[str], *, expected_version: int
    ) -> dict[str, list[str]]:
        parent = _type_code(parent_type_code)
        if parent not in {"enterprise", *PHYSICAL_TYPE_CODES}:
            raise HTTPException(status_code=422, detail="Unsupported physical composition parent")
        allowed = list(dict.fromkeys(_type_code(item) for item in allowed_children))
        if set(allowed) - COMPOSITION_CAPABILITIES[parent]:
            raise HTTPException(
                status_code=422,
                detail=f"Physical composition contains unsupported children for {parent.upper()}",
            )
        record = self._required("workspace_type", parent, published_only=True)
        self._assert_version(record, expected_version)
        existing_children = [_type_code(item) for item in record.content_json.get("allowed_children", [])]
        non_physical_children = [item for item in existing_children if item not in set(PHYSICAL_TYPE_CODES)]
        merged_children = list(dict.fromkeys([*non_physical_children, *allowed]))
        replacement = self._replace_published(
            record,
            {
                **record.content_json,
                "allowed_children": merged_children,
                "seed_version": GATE_VERSION,
            },
        )
        self._event(
            "enterprise_structure.physical_composition_updated",
            replacement,
            {
                "parent": parent,
                "allowed_physical_children": allowed,
                "preserved_non_physical_children": non_physical_children,
            },
        )
        self._commit("Physical composition changed concurrently")
        return {parent: allowed}

    def configure_numbering(
        self, workspace_type_code: str, payload: PhysicalNumberingUpdate, *, expected_version: int
    ) -> ConfigurationVersionOut:
        code = _type_code(workspace_type_code)
        if code not in PHYSICAL_TYPE_CODES:
            raise HTTPException(status_code=422, detail="Unsupported numbering Workspace Type")
        prefix = _prefix(payload.prefix)
        rule_code = NUMBERING[code][0]
        self._assert_version(self._required("numbering_rule", rule_code, published_only=True), expected_version)
        content = _number_content(prefix, payload.padding, payload.start, payload.no_reuse)
        record = self._replace_kind(
            "numbering_rule",
            rule_code,
            f"{code.title()} Numbering",
            f"Business Number for {code.upper()} Workspaces.",
            content,
            "published",
        )
        self._event("enterprise_structure.physical_numbering_updated", record, {"workspace_type_code": code})
        self._commit("Physical numbering changed concurrently")
        return _out(record)

    def configure_policy(
        self, workspace_type_code: str, payload: PhysicalCreationPolicyUpdate, *, expected_version: int
    ) -> ConfigurationVersionOut:
        code = _type_code(workspace_type_code)
        if code not in CREATION_TYPES:
            raise HTTPException(
                status_code=422, detail="Creation Policy is supported only for PROPERTY, FACILITY and WAREHOUSE"
            )
        allowed = list(dict.fromkeys(_type_code(item) for item in payload.allowed_parent_types))
        canonical = set(self._allowed_parents(code))
        if not set(allowed) or set(allowed) - canonical:
            raise HTTPException(status_code=422, detail=f"Invalid parents for {code.upper()}")
        self._assert_version(self._required("creation_policy", f"physical-{code}-creation"), expected_version)
        content = {
            **payload.model_dump(),
            "allowed_parent_types": allowed,
            "workspace_type_code": code,
            "configuration_only": True,
            "creation_process_implemented": False,
            "configuration_version": GATE_VERSION,
        }
        record = self._replace_kind(
            "creation_policy",
            f"physical-{code}-creation",
            f"{code.title()} Creation Policy",
            "DRAFT contract for a future governed creation process.",
            content,
            "draft",
        )
        self._event("enterprise_structure.physical_creation_policy_updated", record, {"workspace_type_code": code})
        self._commit("Physical creation policy changed concurrently")
        return _out(record)

    def create_template(self, payload: PhysicalTemplatePayload) -> ConfigurationVersionOut:
        code = _template_code(payload.code)
        type_code = _type_code(payload.workspace_type_code)
        if type_code not in CREATION_TYPES:
            raise HTTPException(
                status_code=422, detail="Physical Templates are supported for PROPERTY, FACILITY and WAREHOUSE"
            )
        if self._latest("physical_template", code) is not None:
            raise HTTPException(status_code=409, detail=f"Physical Template already exists: {code}")
        content = self._template_content(payload, type_code)
        record = self._new("physical_template", code, payload.name, payload.description, content, "draft")
        self.db.flush()
        self._event("enterprise_structure.physical_template_created", record)
        self._commit("Physical Template already exists")
        return _out(record)

    def update_template(self, configuration_id: int, payload: PhysicalTemplateUpdate) -> ConfigurationVersionOut:
        record = self._configuration(configuration_id, "physical_template")
        if record.status != "draft":
            raise HTTPException(status_code=409, detail="Published Physical Templates are immutable")
        self._assert_version(record, payload.expected_version)
        if _template_code(payload.code) != record.code:
            raise HTTPException(status_code=409, detail="Physical Template code is immutable")
        type_code = _type_code(payload.workspace_type_code)
        record.name = payload.name.strip()
        record.description = payload.description.strip()
        record.content_json = self._template_content(payload, type_code)
        record.version += 1
        record.updated_at = utc_now()
        record.content_hash = _hash(record)
        self._event("enterprise_structure.physical_template_updated", record)
        self._commit("Physical Template changed concurrently")
        return _out(record)

    def validate_template(self, configuration_id: int) -> PhysicalTemplateValidationOut:
        record = self._configuration(configuration_id, "physical_template")
        issues = self._template_issues(record)
        return PhysicalTemplateValidationOut(
            valid=not issues,
            issues=issues,
            warnings=[],
            configuration_ids=[record.id],
            content_hash=record.content_hash,
        )

    def publish_template(self, configuration_id: int, expected_hash: str) -> ConfigurationVersionOut:
        record = self._configuration(configuration_id, "physical_template")
        if record.status != "draft":
            raise HTTPException(status_code=409, detail="Only DRAFT Physical Templates can be published")
        if record.created_by_user_id == self.actor_id:
            raise HTTPException(
                status_code=409,
                detail={
                    "reason": "FOUR_EYES_VIOLATION",
                    "message": "Physical Template publisher must differ from its creator",
                },
            )
        issues = self._template_issues(record)
        if issues:
            raise HTTPException(status_code=422, detail={"message": "Physical Template is invalid", "issues": issues})
        if record.content_hash != expected_hash:
            raise HTTPException(status_code=409, detail="Physical Template changed after validation")
        record.status = "published"
        record.published_at = utc_now()
        record.version += 1
        record.updated_at = utc_now()
        record.content_hash = _hash(record)
        self._event("enterprise_structure.physical_template_published", record)
        self._commit("Physical Template changed concurrently")
        return _out(record)

    def archive_template(self, configuration_id: int) -> ConfigurationVersionOut:
        record = self._configuration(configuration_id, "physical_template")
        if record.status == "archived":
            return _out(record)
        record.status = "archived"
        record.version += 1
        record.updated_at = utc_now()
        record.content_hash = _hash(record)
        self._event("enterprise_structure.physical_template_updated", record, {"action": "archive"})
        self._commit("Physical Template changed concurrently")
        return _out(record)

    def issue_business_number(self, workspace_type_code: str, scope_key: str = "tenant") -> str:
        code = _type_code(workspace_type_code)
        if code not in PHYSICAL_TYPE_CODES:
            raise HTTPException(status_code=422, detail="Unsupported numbering Workspace Type")
        rule_code = NUMBERING[code][0]
        rule = self._required("numbering_rule", rule_code, published_only=True)
        counter = self.db.scalar(
            select(AdminNumberSequence)
            .where(
                AdminNumberSequence.tenant_id == self.tenant_id,
                AdminNumberSequence.rule_code == rule_code,
                AdminNumberSequence.scope_key == scope_key,
            )
            .with_for_update()
        )
        if counter is None:
            raise HTTPException(status_code=409, detail="Physical number sequence is not initialized")
        value = counter.next_value
        counter.next_value += 1
        counter.version += 1
        counter.updated_at = utc_now()
        result = _format_number(rule.content_json, value)
        self._commit("Physical number sequence changed concurrently")
        return result

    def _seed_numbering(self) -> None:
        for code, (rule_code, prefix) in NUMBERING.items():
            rule = self._latest("numbering_rule", rule_code, published_only=True)
            if rule is None:
                rule = self._new(
                    "numbering_rule",
                    rule_code,
                    f"{code.title()} Numbering",
                    f"Preview-ready Business Number for {code.upper()}.",
                    _number_content(prefix, 5, 1, True),
                    "published",
                )
                rule.published_at = utc_now()
                self.db.flush()
                self._event(
                    "enterprise_structure.physical_numbering_updated",
                    rule,
                    {"action": "seed", "workspace_type_code": code},
                )
            if (
                self.db.scalar(
                    select(AdminNumberSequence).where(
                        AdminNumberSequence.tenant_id == self.tenant_id,
                        AdminNumberSequence.rule_code == rule_code,
                        AdminNumberSequence.scope_key == "tenant",
                    )
                )
                is None
            ):
                self.db.add(
                    AdminNumberSequence(
                        tenant_id=self.tenant_id,
                        rule_code=rule_code,
                        scope_key="tenant",
                        next_value=int(rule.content_json.get("start", 1)),
                        version=1,
                    )
                )

    def _seed_templates(self) -> None:
        for code, name, type_code in TEMPLATE_SEED:
            if self._latest("physical_template", code) is not None:
                continue
            payload = PhysicalTemplatePayload(
                code=code,
                name=name,
                description="Gate 06A controlled DRAFT template.",
                workspace_type_code=type_code,
                applicable_parent_types=self._allowed_parents(type_code),
            )
            record = self._new(
                "physical_template",
                code,
                name,
                payload.description,
                self._template_content(payload, type_code),
                "draft",
            )
            self.db.flush()
            self._event("enterprise_structure.physical_template_created", record, {"action": "seed"})

    def _seed_policies(self) -> None:
        for code in CREATION_TYPES:
            policy_code = f"physical-{code}-creation"
            if self._latest("creation_policy", policy_code) is not None:
                continue
            payload = PhysicalCreationPolicyUpdate(allowed_parent_types=self._allowed_parents(code))
            content = {
                **payload.model_dump(),
                "workspace_type_code": code,
                "configuration_only": True,
                "creation_process_implemented": False,
                "configuration_version": GATE_VERSION,
            }
            record = self._new(
                "creation_policy",
                policy_code,
                f"{code.title()} Creation Policy",
                "DRAFT policy; no creation process is implemented in Gate 06A.",
                content,
                "draft",
            )
            self.db.flush()
            self._event(
                "enterprise_structure.physical_creation_policy_updated",
                record,
                {"action": "seed", "workspace_type_code": code},
            )

    def _template_content(self, payload: PhysicalTemplatePayload, type_code: str) -> dict[str, Any]:
        parents = [_type_code(item) for item in payload.applicable_parent_types]
        allowed = set(self._allowed_parents(type_code))
        if not parents or set(parents) - allowed:
            raise HTTPException(status_code=422, detail=f"Invalid template parents for {type_code.upper()}")
        modules = self._valid_modules(payload.enabled_modules)
        if len(modules) != len(set(payload.enabled_modules)):
            raise HTTPException(status_code=422, detail="Physical Template contains unknown or unpublished modules")
        return {
            "workspace_type_code": type_code,
            "applicable_parent_types": parents,
            "default_classifications": payload.default_classifications,
            "enabled_modules": modules,
            "default_attributes": payload.default_attributes,
            "numbering_rule_code": NUMBERING[type_code][0],
            "creation_policy_code": f"physical-{type_code}-creation",
            "planned_modules": WORKSPACE_TYPE_SEED[type_code].get("planned_modules", []),
            "configuration_version": GATE_VERSION,
        }

    def _template_issues(self, record: AdminConfiguration) -> list[str]:
        content = record.content_json
        type_code = str(content.get("workspace_type_code", ""))
        issues: list[str] = []
        if type_code not in CREATION_TYPES:
            issues.append("Unsupported physical template Workspace Type")
            return issues
        if set(content.get("applicable_parent_types", [])) - set(self._allowed_parents(type_code)):
            issues.append("Template has invalid parent types")
        if set(content.get("enabled_modules", [])) - {item.code for item in self._published_modules()}:
            issues.append("Template has unknown or unpublished modules")
        return issues

    def _parent_options(self) -> list[PhysicalWorkspaceParentOption]:
        allowed = {"enterprise", *PHYSICAL_TYPE_CODES}
        rows = list(
            self.db.scalars(
                select(EnterpriseWorkspace)
                .where(
                    EnterpriseWorkspace.tenant_id == self.tenant_id,
                    EnterpriseWorkspace.workspace_type_code.in_(allowed),
                    EnterpriseWorkspace.status != "archived",
                )
                .order_by(EnterpriseWorkspace.record_code)
            ).all()
        )
        return [_parent_out(item) for item in rows]

    def _real_instance_count(self) -> int:
        return int(
            self.db.scalar(
                select(func.count())
                .select_from(EnterpriseWorkspace)
                .where(
                    EnterpriseWorkspace.tenant_id == self.tenant_id,
                    EnterpriseWorkspace.workspace_type_code.in_(PHYSICAL_TYPE_CODES),
                )
            )
            or 0
        )

    def _number_preview(self, rule: AdminConfiguration) -> str:
        counter = self.db.scalar(
            select(AdminNumberSequence).where(
                AdminNumberSequence.tenant_id == self.tenant_id,
                AdminNumberSequence.rule_code == rule.code,
                AdminNumberSequence.scope_key == "tenant",
            )
        )
        return _format_number(
            rule.content_json, counter.next_value if counter else int(rule.content_json.get("start", 1))
        )

    def _allowed_parents(self, child: str) -> list[str]:
        return [
            code
            for code in ("enterprise", *PHYSICAL_TYPE_CODES)
            if child in WORKSPACE_TYPE_SEED[code].get("allowed_children", [])
        ]

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

    def _valid_modules(self, values: list[str]) -> list[str]:
        available = {item.code for item in self._published_modules()}
        return sorted(set(values) & available)

    def _replace_published(self, source: AdminConfiguration, content: dict[str, Any]) -> AdminConfiguration:
        return self._replace_kind(source.kind, source.code, source.name, source.description, content, "published")

    def _replace_kind(
        self, kind: str, code: str, name: str, description: str, content: dict[str, Any], status: str
    ) -> AdminConfiguration:
        latest = self._latest(kind, code)
        if latest is not None and latest.content_json == content and latest.status == status:
            return latest
        record = self._new(kind, code, name, description, content, status)
        if status == "published":
            record.published_at = utc_now()
        self.db.flush()
        return record

    def _new(
        self, kind: str, code: str, name: str, description: str, content: dict[str, Any], status: str
    ) -> AdminConfiguration:
        record = AdminConfiguration(
            tenant_id=self.tenant_id,
            kind=kind,
            code=code,
            name=name.strip(),
            description=description.strip(),
            status=status,
            revision=self._next_revision(kind, code),
            version=1,
            content_json=content,
            published_at=utc_now() if status == "published" else None,
            created_by_user_id=self.actor_id,
        )
        record.content_hash = _hash(record)
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

    def _required(self, kind: str, code: str, *, published_only: bool = False) -> AdminConfiguration:
        record = self._latest(kind, code, published_only=published_only)
        if record is None:
            raise HTTPException(status_code=409, detail=f"Missing Gate 06A configuration: {kind}/{code}")
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

    def _latest_by_code(self, kind: str) -> list[AdminConfiguration]:
        rows = list(
            self.db.scalars(
                select(AdminConfiguration)
                .where(AdminConfiguration.tenant_id == self.tenant_id, AdminConfiguration.kind == kind)
                .order_by(AdminConfiguration.code, AdminConfiguration.revision.desc())
            ).all()
        )
        selected: dict[str, AdminConfiguration] = {}
        for row in rows:
            selected.setdefault(row.code, row)
        return sorted(selected.values(), key=lambda item: item.code)

    def _next_revision(self, kind: str, code: str) -> int:
        return (
            int(
                self.db.scalar(
                    select(func.max(AdminConfiguration.revision)).where(
                        AdminConfiguration.tenant_id == self.tenant_id,
                        AdminConfiguration.kind == kind,
                        AdminConfiguration.code == code,
                    )
                )
                or 0
            )
            + 1
        )

    def _event(self, event_type: str, target: object, metadata: dict[str, Any] | None = None) -> None:
        self.db.add(
            SecurityEvent(
                tenant_id=self.tenant_id,
                user_id=self.actor_id,
                event_type=event_type,
                outcome="success",
                target_type=target.__class__.__name__,
                target_id=getattr(target, "id", None),
                metadata_json={"gate": "06A", **(metadata or {})},
            )
        )

    @staticmethod
    def _assert_version(record: AdminConfiguration, expected_version: int) -> None:
        if record.version != expected_version:
            raise HTTPException(
                status_code=409,
                detail={"reason": "PHYSICAL_CONFIGURATION_VERSION_CONFLICT", "current_version": record.version},
            )

    def _commit(self, message: str) -> None:
        try:
            self.db.commit()
        except IntegrityError as exc:
            self.db.rollback()
            raise HTTPException(status_code=409, detail=message) from exc


def _type_code(value: str) -> str:
    return value.strip().lower().replace("_", "-").replace(" ", "-")


def _prefix(value: str) -> str:
    prefix = value.strip().upper().strip("-")
    if not prefix or any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-" for character in prefix):
        raise HTTPException(status_code=422, detail="Prefix may contain A-Z, 0-9 and hyphen only")
    return prefix


def _template_code(value: str) -> str:
    return _prefix(value)


def _number_content(prefix: str, padding: int, start: int, no_reuse: bool) -> dict[str, Any]:
    return {
        "prefix": prefix,
        "pattern": f"{{prefix}}-{{sequence:0{padding}d}}",
        "padding": padding,
        "start": start,
        "scope": "tenant",
        "unique": True,
        "no_reuse": no_reuse,
        "preview_consumes_sequence": False,
        "configuration_version": GATE_VERSION,
    }


def _format_number(content: dict[str, Any], value: int) -> str:
    try:
        return str(content["pattern"]).format(prefix=content["prefix"], sequence=value)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"Invalid physical numbering rule: {exc}") from exc


def _hash(record: AdminConfiguration) -> str:
    payload = {
        "kind": record.kind,
        "code": record.code,
        "revision": record.revision,
        "name": record.name,
        "description": record.description,
        "content": record.content_json,
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def _out(record: AdminConfiguration) -> ConfigurationVersionOut:
    return ConfigurationVersionOut.model_validate(record)


def _parent_out(record: EnterpriseWorkspace) -> PhysicalWorkspaceParentOption:
    return PhysicalWorkspaceParentOption(
        id=record.id,
        name=record.name,
        workspace_type_code=record.workspace_type_code,
        record_code=record.record_code,
        status=record.status,
    )
