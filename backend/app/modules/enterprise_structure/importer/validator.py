"""Pure dry-run validation and reporting orchestration for Nivel 2B."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter

from app.modules.enterprise_structure.constants import (
    CATEGORY_SEED,
    RELATIONSHIP_TYPES,
    WORKSPACE_TYPE_SEED,
)
from app.modules.enterprise_structure.importer.diff import build_diff
from app.modules.enterprise_structure.importer.models import (
    DiffAction,
    DryRunReport,
    EnterpriseStructureImport,
    NodeType,
    RecordStatus,
    Severity,
    TenantSnapshot,
    ValidationFinding,
)
from app.modules.enterprise_structure.importer.normalizer import internal_code

CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9._-]*$")


def _finding(
    severity: Severity,
    code: str,
    section: str,
    reference: str,
    message: str,
    recommendation: str,
) -> ValidationFinding:
    return ValidationFinding(
        severity=severity,
        code=code,
        section=section,
        reference=reference,
        message=message,
        recommendation=recommendation,
    )


def build_dry_run(
    configuration: EnterpriseStructureImport,
    snapshot: TenantSnapshot | None = None,
) -> DryRunReport:
    findings, order = validate_configuration(configuration, snapshot)
    diff = build_diff(configuration, snapshot)
    for item in diff:
        if item.action == DiffAction.CONFLICT:
            findings.append(
                _finding(
                    Severity.ERROR,
                    "DIFF_CONFLICT",
                    item.entity,
                    item.key,
                    item.reason,
                    "Resolve the declarative identity or code collision before apply.",
                )
            )
    counts = Counter(item.severity.value for item in findings)
    action_counts = Counter(item.action.value for item in diff)
    finding_codes = Counter(item.code for item in findings)
    summary = {
        "nodes": len(configuration.nodes),
        "strategic_objectives": len(configuration.strategic_objectives),
        "classifications": len(configuration.classifications),
        "links": len(configuration.links),
        "errors": counts[Severity.ERROR.value],
        "warnings": counts[Severity.WARNING.value],
        "info": counts[Severity.INFO.value],
        "adopt": action_counts[DiffAction.ADOPT.value],
        "create": action_counts[DiffAction.CREATE.value],
        "update": action_counts[DiffAction.UPDATE.value],
        "unchanged": action_counts[DiffAction.UNCHANGED.value],
        "conflict": action_counts[DiffAction.CONFLICT.value],
        "hierarchy_errors": sum(
            finding_codes[code]
            for code in (
                "ROOT_COUNT",
                "INVALID_ROOT_TYPE",
                "PARENT_NOT_FOUND",
                "INCOMPATIBLE_PARENT_CHILD",
                "HIERARCHY_CYCLE",
                "ARCHIVED_WITH_ACTIVE_CHILDREN",
            )
        ),
        "required_classification_missing": finding_codes["REQUIRED_CLASSIFICATION_MISSING"],
        "category_not_applicable": finding_codes["CATEGORY_NOT_APPLICABLE"],
        "identity_conflicts": sum(
            finding_codes[code]
            for code in (
                "DUPLICATE_RECONCILIATION_KEY",
                "DUPLICATE_RECONCILIATION_ID",
                "RECONCILIATION_NODE_NOT_FOUND",
                "ADOPTION_TARGET_NOT_FOUND",
                "CROSS_TENANT_ADOPTION",
                "ADOPTION_TYPE_MISMATCH",
                "ADOPTION_EXTERNAL_KEY_CONFLICT",
                "ADOPTION_CHILD_REFERENCE_UNMAPPED",
                "ADOPTION_HIERARCHY_CYCLE",
                "EXISTING_EXTERNAL_KEY_DUPLICATE",
                "EXISTING_RECORD_CODE_DUPLICATE",
            )
        ),
        "base_mutations": 0,
    }
    payload = configuration.model_dump(mode="json")
    input_hash = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return DryRunReport(
        tenant_code=configuration.metadata.tenant_code,
        release_code=configuration.metadata.release_code,
        input_hash=input_hash,
        valid=counts[Severity.ERROR.value] == 0,
        findings=sorted(
            findings,
            key=lambda item: (
                {Severity.ERROR: 0, Severity.WARNING: 1, Severity.INFO: 2}[item.severity],
                item.section,
                item.reference,
                item.code,
            ),
        ),
        diff=diff,
        topological_order=order,
        summary=summary,
    )


def validate_configuration(
    configuration: EnterpriseStructureImport,
    snapshot: TenantSnapshot | None = None,
) -> tuple[list[ValidationFinding], list[str]]:
    findings: list[ValidationFinding] = []
    node_by_key = {item.external_key: item for item in configuration.nodes}
    findings.extend(_duplicates(configuration))
    findings.extend(_validate_reconciliation(configuration, snapshot))
    coded_values = [
        ("metadata", "release_code", configuration.metadata.release_code),
        *[("nodes", item.external_key, item.external_key) for item in configuration.nodes],
        *[("nodes", item.external_key, item.code) for item in configuration.nodes],
        *[("strategic_objectives", item.code, item.code) for item in configuration.strategic_objectives],
    ]
    for section, reference, value in coded_values:
        if not CODE_PATTERN.fullmatch(value):
            findings.append(
                _finding(
                    Severity.ERROR,
                    "INVALID_CODE_FORMAT",
                    section,
                    reference,
                    f"Code {value} contains unsupported characters.",
                    "Use uppercase letters, numbers, dot, underscore or hyphen.",
                )
            )

    roots = [
        item
        for item in configuration.nodes
        if item.parent_external_key is None and item.status != RecordStatus.ARCHIVED
    ]
    enterprise_roots = [item for item in roots if item.node_type == NodeType.ENTERPRISE]
    if len(enterprise_roots) != 1 or len(roots) != 1:
        findings.append(
            _finding(
                Severity.ERROR,
                "ROOT_COUNT",
                "nodes",
                "",
                "Exactly one non-archived Enterprise root is required.",
                "Leave one ENTERPRISE node without parent_external_key.",
            )
        )

    for node in configuration.nodes:
        ref = node.external_key
        if node.valid_from and node.valid_to and node.valid_to <= node.valid_from:
            findings.append(_date_finding("nodes", ref))
        if node.parent_external_key is None:
            if node.node_type != NodeType.ENTERPRISE:
                findings.append(
                    _finding(
                        Severity.ERROR,
                        "INVALID_ROOT_TYPE",
                        "nodes",
                        ref,
                        f"{node.node_type.value} cannot be a root.",
                        "Assign a compatible parent or change the type to ENTERPRISE.",
                    )
                )
            continue
        parent = node_by_key.get(node.parent_external_key)
        if parent is None:
            findings.append(
                _finding(
                    Severity.ERROR,
                    "PARENT_NOT_FOUND",
                    "nodes",
                    ref,
                    f"Parent {node.parent_external_key} does not exist in the input.",
                    "Add the parent row or correct parent_external_key.",
                )
            )
            continue
        allowed = set(WORKSPACE_TYPE_SEED[internal_code(parent.node_type.value)]["allowed_children"])
        child_type = internal_code(node.node_type.value)
        if child_type not in allowed:
            findings.append(
                _finding(
                    Severity.ERROR,
                    "INCOMPATIBLE_PARENT_CHILD",
                    "nodes",
                    ref,
                    f"{parent.node_type.value} cannot contain {node.node_type.value}.",
                    "Use a parent-child combination allowed by the published composition rules.",
                )
            )

    order, cycle_keys = topological_order(configuration)
    for key in cycle_keys:
        findings.append(
            _finding(
                Severity.ERROR,
                "HIERARCHY_CYCLE",
                "nodes",
                key,
                "The parent chain contains a cycle.",
                "Break the cycle before apply.",
            )
        )
        if key in {item.external_key for item in configuration.reconciliation}:
            findings.append(
                _finding(
                    Severity.ERROR,
                    "ADOPTION_HIERARCHY_CYCLE",
                    "reconciliation",
                    key,
                    "The hierarchy after adoption would contain a cycle.",
                    "Correct the canonical parent chain before approving adoption.",
                )
            )

    active_children = {
        item.parent_external_key
        for item in configuration.nodes
        if item.parent_external_key and item.status != RecordStatus.ARCHIVED
    }
    for node in configuration.nodes:
        if node.status == RecordStatus.ARCHIVED and node.external_key in active_children:
            findings.append(
                _finding(
                    Severity.ERROR,
                    "ARCHIVED_WITH_ACTIVE_CHILDREN",
                    "nodes",
                    node.external_key,
                    "An archived node still has non-archived children.",
                    "Archive or move the children first.",
                )
            )

    objective_codes = {item.code for item in configuration.strategic_objectives}
    assigned_categories: dict[str, set[str]] = {}
    for item in configuration.classifications:
        ref = f"{item.workspace_external_key}:{item.category_set_code}:{item.category_item_code}"
        workspace = node_by_key.get(item.workspace_external_key)
        if workspace is None:
            findings.append(
                _finding(
                    Severity.ERROR,
                    "CLASSIFICATION_WORKSPACE_NOT_FOUND",
                    "classifications",
                    ref,
                    "The classified workspace is not present in the input.",
                    "Correct workspace_external_key.",
                )
            )
            continue
        if item.valid_from and item.valid_to and item.valid_to <= item.valid_from:
            findings.append(_date_finding("classifications", ref))
        category_code = internal_code(item.category_set_code)
        assigned_categories.setdefault(item.workspace_external_key, set()).add(category_code)
        if category_code == "strategic-objective":
            if item.category_item_code not in objective_codes and not _snapshot_has_item(
                snapshot, category_code, item.category_item_code
            ):
                findings.append(
                    _finding(
                        Severity.ERROR,
                        "OBJECTIVE_NOT_FOUND",
                        "classifications",
                        ref,
                        "The Strategic Objective is neither declared nor published.",
                        "Add the objective or use a published objective code.",
                    )
                )
        elif snapshot is not None and category_code not in snapshot.published_categories:
            findings.append(
                _finding(
                    Severity.ERROR,
                    "CATEGORY_SET_NOT_PUBLISHED",
                    "classifications",
                    ref,
                    f"Category Set {item.category_set_code} is not published.",
                    "Publish the required category in ADMIN MODE before apply.",
                )
            )
        if snapshot is not None and category_code in snapshot.published_categories:
            category = snapshot.published_categories[category_code]
            applicable = set(category.get("applicable_types", []))
            if applicable and internal_code(workspace.node_type.value) not in applicable:
                findings.append(
                    _finding(
                        Severity.ERROR,
                        "CATEGORY_NOT_APPLICABLE",
                        "classifications",
                        ref,
                        "The category is not applicable to the workspace type.",
                        "Use a category allowed by the published catalog.",
                    )
                )
            published_items = {
                str(published.get("code", "")).strip().upper() for published in category.get("items", [])
            }
            if category_code != "strategic-objective" and item.category_item_code not in published_items:
                findings.append(
                    _finding(
                        Severity.ERROR,
                        "CATEGORY_ITEM_NOT_PUBLISHED",
                        "classifications",
                        ref,
                        f"Category item {item.category_item_code} is not published.",
                        "Use a published category item or configure it in ADMIN MODE first.",
                    )
                )

    for node in configuration.nodes:
        required_categories = set(WORKSPACE_TYPE_SEED[internal_code(node.node_type.value)]["required_categories"])
        missing = sorted(required_categories - assigned_categories.get(node.external_key, set()))
        if missing and node.status != RecordStatus.ARCHIVED:
            findings.append(
                _finding(
                    Severity.ERROR,
                    "REQUIRED_CLASSIFICATION_MISSING",
                    "classifications",
                    node.external_key,
                    f"Required categories are missing: {', '.join(missing)}.",
                    "Assign every category required by the published workspace type.",
                )
            )

    allowed_pairs = {
        ("project", "property"),
        ("project", "facility"),
        ("property", "business-unit"),
        ("facility", "business-unit"),
    }
    for item in configuration.links:
        ref = f"{item.source_external_key}:{item.target_external_key}:{item.relationship_type}"
        source = node_by_key.get(item.source_external_key)
        target = node_by_key.get(item.target_external_key)
        if source is None or target is None:
            findings.append(
                _finding(
                    Severity.ERROR,
                    "LINK_ENDPOINT_NOT_FOUND",
                    "links",
                    ref,
                    "Source or target is not present in the input.",
                    "Correct both external_key references.",
                )
            )
            continue
        if source.external_key == target.external_key:
            findings.append(
                _finding(
                    Severity.ERROR,
                    "SELF_LINK",
                    "links",
                    ref,
                    "A workspace cannot link to itself.",
                    "Choose a different target.",
                )
            )
        if item.relationship_type not in RELATIONSHIP_TYPES:
            findings.append(
                _finding(
                    Severity.ERROR,
                    "UNSUPPORTED_RELATIONSHIP",
                    "links",
                    ref,
                    f"Relationship {item.relationship_type} is not supported.",
                    "Use a published relationship type.",
                )
            )
        pair = (internal_code(source.node_type.value), internal_code(target.node_type.value))
        if pair not in allowed_pairs:
            findings.append(
                _finding(
                    Severity.ERROR,
                    "UNSUPPORTED_RELATIONSHIP_PAIR",
                    "links",
                    ref,
                    f"Relationship is not supported between {pair[0]} and {pair[1]}.",
                    "Use Project-Property or Project-Facility for transversal links.",
                )
            )
        if item.valid_from and item.valid_to and item.valid_to <= item.valid_from:
            findings.append(_date_finding("links", ref))

    if snapshot is not None:
        findings.extend(_validate_snapshot(configuration, snapshot))
    else:
        findings.append(
            _finding(
                Severity.INFO,
                "DATABASE_NOT_CHECKED",
                "governance",
                configuration.metadata.tenant_code,
                "Database references and ADMIN publication state were not checked.",
                "Run validate with --tenant against the target environment.",
            )
        )
    return findings, order


def topological_order(configuration: EnterpriseStructureImport) -> tuple[list[str], list[str]]:
    parents = {item.external_key: item.parent_external_key for item in configuration.nodes}
    ordered: list[str] = []
    permanent: set[str] = set()
    visiting: set[str] = set()
    cycles: set[str] = set()

    def visit(key: str) -> None:
        if key in permanent:
            return
        if key in visiting:
            cycles.update(visiting)
            return
        visiting.add(key)
        parent = parents.get(key)
        if parent in parents:
            visit(parent)
        visiting.discard(key)
        permanent.add(key)
        ordered.append(key)

    for key in parents:
        visit(key)
    return ordered, sorted(cycles)


def _duplicates(configuration: EnterpriseStructureImport) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    groups = [
        ("DUPLICATE_EXTERNAL_KEY", "nodes", [item.external_key for item in configuration.nodes]),
        ("DUPLICATE_NODE_CODE", "nodes", [item.code for item in configuration.nodes]),
        ("DUPLICATE_OBJECTIVE", "strategic_objectives", [item.code for item in configuration.strategic_objectives]),
        (
            "DUPLICATE_CLASSIFICATION",
            "classifications",
            [
                f"{item.workspace_external_key}:{item.category_set_code}:{item.category_item_code}"
                for item in configuration.classifications
            ],
        ),
        (
            "DUPLICATE_LINK",
            "links",
            [
                f"{item.source_external_key}:{item.target_external_key}:{item.relationship_type}"
                for item in configuration.links
            ],
        ),
    ]
    for code, section, values in groups:
        for value, count in Counter(values).items():
            if count > 1:
                findings.append(
                    _finding(
                        Severity.ERROR,
                        code,
                        section,
                        value,
                        f"Duplicate declarative identity appears {count} times.",
                        "Keep one authoritative record.",
                    )
                )
    return findings


def _validate_reconciliation(
    configuration: EnterpriseStructureImport,
    snapshot: TenantSnapshot | None,
) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    if not configuration.reconciliation:
        return findings
    if snapshot is None:
        return [
            _finding(
                Severity.ERROR,
                "RECONCILIATION_REQUIRES_DATABASE",
                "reconciliation",
                configuration.metadata.tenant_code,
                "Explicit adoption cannot be validated without the target tenant database snapshot.",
                "Run validate with --tenant against the target environment.",
            )
        ]

    nodes_by_key = {item.external_key: item for item in configuration.nodes}
    existing_by_id = {item.id: item for item in snapshot.nodes}
    key_counts = Counter(item.external_key for item in configuration.reconciliation)
    id_counts = Counter(item.existing_id for item in configuration.reconciliation)
    for key, count in key_counts.items():
        if count > 1:
            findings.append(
                _finding(
                    Severity.ERROR,
                    "DUPLICATE_RECONCILIATION_KEY",
                    "reconciliation",
                    key,
                    f"Canonical external_key is reconciled {count} times.",
                    "Keep one explicit adoption decision per external_key.",
                )
            )
    for existing_id, count in id_counts.items():
        if count > 1:
            findings.append(
                _finding(
                    Severity.ERROR,
                    "DUPLICATE_RECONCILIATION_ID",
                    "reconciliation",
                    str(existing_id),
                    f"Workspace id {existing_id} is claimed by {count} canonical external_keys.",
                    "A persisted workspace may be adopted by only one canonical identity.",
                )
            )

    adopted_ids = set(id_counts)
    for decision in configuration.reconciliation:
        node = nodes_by_key.get(decision.external_key)
        if node is None:
            findings.append(
                _finding(
                    Severity.ERROR,
                    "RECONCILIATION_NODE_NOT_FOUND",
                    "reconciliation",
                    decision.external_key,
                    "The reconciliation external_key is not declared in nodes.",
                    "Correct the external_key or add the canonical node.",
                )
            )
            continue
        owner_tenant = snapshot.workspace_tenant_ids.get(decision.existing_id)
        if owner_tenant is not None and owner_tenant != snapshot.tenant_id:
            findings.append(
                _finding(
                    Severity.ERROR,
                    "CROSS_TENANT_ADOPTION",
                    "reconciliation",
                    decision.external_key,
                    f"Workspace {decision.existing_id} belongs to tenant {owner_tenant}, not {snapshot.tenant_id}.",
                    "Adopt only workspaces owned by the target tenant.",
                )
            )
            continue
        existing = existing_by_id.get(decision.existing_id)
        if existing is None:
            findings.append(
                _finding(
                    Severity.ERROR,
                    "ADOPTION_TARGET_NOT_FOUND",
                    "reconciliation",
                    decision.external_key,
                    f"Workspace {decision.existing_id} does not exist in the target tenant snapshot.",
                    "Use a valid existing_id or remove the adoption decision.",
                )
            )
            continue
        expected_type = internal_code(node.node_type.value)
        if existing.node_type != expected_type:
            findings.append(
                _finding(
                    Severity.ERROR,
                    "ADOPTION_TYPE_MISMATCH",
                    "reconciliation",
                    decision.external_key,
                    f"Workspace {existing.id} type {existing.node_type} does not match {expected_type}.",
                    "Adopt a workspace with the same canonical type.",
                )
            )
        if existing.external_key and existing.external_key != decision.external_key:
            findings.append(
                _finding(
                    Severity.ERROR,
                    "ADOPTION_EXTERNAL_KEY_CONFLICT",
                    "reconciliation",
                    decision.external_key,
                    f"Workspace {existing.id} already owns external_key {existing.external_key}.",
                    "Do not overwrite an established declarative identity without a separate approval.",
                )
            )
        unmapped_children = sorted(
            child_id
            for child_id in existing.child_ids
            if child_id not in adopted_ids
            and (child_id not in existing_by_id or existing_by_id[child_id].external_key not in nodes_by_key)
        )
        if unmapped_children:
            findings.append(
                _finding(
                    Severity.ERROR,
                    "ADOPTION_CHILD_REFERENCE_UNMAPPED",
                    "reconciliation",
                    decision.external_key,
                    f"Existing child workspace ids are not reconciled: {', '.join(map(str, unmapped_children))}.",
                    "Adopt or explicitly KEEP each referenced child before changing this node.",
                )
            )
    return findings


def _validate_snapshot(
    configuration: EnterpriseStructureImport,
    snapshot: TenantSnapshot,
) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    input_tenant = configuration.metadata.tenant_code.replace("_", "-")
    if input_tenant != snapshot.tenant_code.replace("_", "-"):
        findings.append(
            _finding(
                Severity.ERROR,
                "TENANT_MISMATCH",
                "metadata",
                configuration.metadata.tenant_code,
                f"Input tenant does not match target tenant {snapshot.tenant_code}.",
                "Use the correct tenant_code and --tenant value.",
            )
        )
    roots = [item for item in snapshot.nodes if item.parent_id is None and item.status != "archived"]
    if len(roots) != 1:
        findings.append(
            _finding(
                Severity.ERROR,
                "EXISTING_ROOT_COUNT",
                "database",
                snapshot.tenant_code,
                f"Target tenant has {len(roots)} active root workspaces.",
                "Reconcile the existing roots before apply.",
            )
        )
    external_counts = Counter(item.external_key for item in snapshot.nodes if item.external_key)
    for key, count in external_counts.items():
        if count > 1:
            findings.append(
                _finding(
                    Severity.ERROR,
                    "EXISTING_EXTERNAL_KEY_DUPLICATE",
                    "database",
                    key,
                    f"Existing external_key is used {count} times.",
                    "Resolve persisted declarative identity duplication.",
                )
            )
    record_counts = Counter(item.record_code for item in snapshot.nodes)
    for record_code, count in record_counts.items():
        if count > 1:
            findings.append(
                _finding(
                    Severity.ERROR,
                    "EXISTING_RECORD_CODE_DUPLICATE",
                    "database",
                    record_code,
                    f"Existing Record Code is used {count} times.",
                    "Repair tenant-scoped Record Code uniqueness before apply.",
                )
            )
    for issue in snapshot.integrity_issues:
        findings.append(
            _finding(
                Severity.ERROR,
                issue.code,
                "database",
                issue.reference,
                issue.message,
                "Repair the persisted cross-tenant or broken reference before apply.",
            )
        )
    if configuration.metadata.release_code in snapshot.existing_release_codes:
        findings.append(
            _finding(
                Severity.ERROR,
                "RELEASE_CODE_EXISTS",
                "metadata",
                configuration.metadata.release_code,
                "The release code was already applied or published.",
                "Use the existing release for audit or choose a new approved code.",
            )
        )
    missing_types = sorted(set(WORKSPACE_TYPE_SEED) - snapshot.published_type_codes)
    if missing_types:
        findings.append(
            _finding(
                Severity.ERROR,
                "WORKSPACE_TYPES_NOT_PUBLISHED",
                "governance",
                ",".join(missing_types),
                "Required workspace types are not published.",
                "Complete Enterprise Structure Configuration in ADMIN MODE.",
            )
        )
    missing_categories = sorted(set(CATEGORY_SEED) - set(snapshot.published_categories))
    if missing_categories:
        findings.append(
            _finding(
                Severity.ERROR,
                "CATEGORIES_NOT_PUBLISHED",
                "governance",
                ",".join(missing_categories),
                "Required enterprise categories are not published.",
                "Publish the five seed categories before apply.",
            )
        )
    requester = configuration.metadata.requested_by
    if requester and requester not in snapshot.user_emails:
        findings.append(
            _finding(
                Severity.WARNING,
                "REQUESTER_NOT_FOUND",
                "metadata",
                requester,
                "requested_by does not resolve to an active tenant user.",
                "Confirm the requester before apply.",
            )
        )
    elif requester and snapshot.requester_has_manage_permission is False:
        findings.append(
            _finding(
                Severity.ERROR,
                "REQUESTER_NOT_AUTHORIZED",
                "governance",
                requester,
                "The requester lacks admin.enterprise_structure.manage.",
                "Assign an authorized role with organization scope.",
            )
        )
    for node in configuration.nodes:
        if node.responsible_email and node.responsible_email not in snapshot.user_emails:
            findings.append(
                _finding(
                    Severity.WARNING,
                    "RESPONSIBLE_NOT_FOUND",
                    "nodes",
                    node.external_key,
                    f"Responsible user {node.responsible_email} does not exist in the tenant.",
                    "Create/activate the user or justify the warning.",
                )
            )
        if node.organization_unit_code and node.organization_unit_code not in snapshot.organization_unit_codes:
            findings.append(
                _finding(
                    Severity.WARNING,
                    "ORGANIZATION_UNIT_NOT_FOUND",
                    "nodes",
                    node.external_key,
                    f"Organization unit {node.organization_unit_code} does not exist.",
                    "Create the unit or correct the code before apply.",
                )
            )
    return findings


def _snapshot_has_item(snapshot: TenantSnapshot | None, category_code: str, item_code: str) -> bool:
    if snapshot is None:
        return False
    category = snapshot.published_categories.get(category_code, {})
    return item_code in {str(item.get("code", "")).upper() for item in category.get("items", [])}


def _date_finding(section: str, reference: str) -> ValidationFinding:
    return _finding(
        Severity.ERROR,
        "INVALID_DATE_RANGE",
        section,
        reference,
        "valid_to must be after valid_from.",
        "Correct the validity dates.",
    )
