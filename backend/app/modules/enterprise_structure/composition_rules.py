"""Validation helpers for published parent-child composition rules."""

from fastapi import HTTPException

from app.domain.models import AdminConfiguration, EnterpriseWorkspace


def validate_parent_child(parent: EnterpriseWorkspace, child_type: str, parent_type: AdminConfiguration) -> None:
    allowed = set(parent_type.content_json.get("allowed_children", []))
    if child_type not in allowed:
        raise HTTPException(
            status_code=409,
            detail=f"{parent.workspace_type_code} cannot contain {child_type}",
        )


def validate_rule_definition(code: str, content: dict, known_type_codes: set[str], known_categories: set[str]) -> list[str]:
    issues: list[str] = []
    allowed_children = content.get("allowed_children", [])
    if not isinstance(allowed_children, list):
        return [f"{code}: allowed_children must be a list"]
    unknown_children = sorted(set(allowed_children) - known_type_codes)
    if unknown_children:
        issues.append(f"{code}: unknown child types: {', '.join(unknown_children)}")
    required_categories = content.get("required_categories", [])
    if not isinstance(required_categories, list):
        issues.append(f"{code}: required_categories must be a list")
    else:
        unknown_categories = sorted(set(required_categories) - known_categories)
        if unknown_categories:
            issues.append(f"{code}: unknown required categories: {', '.join(unknown_categories)}")
    required_fields = content.get("required_fields", [])
    if not isinstance(required_fields, list) or not {"code", "name"}.issubset(set(required_fields)):
        issues.append(f"{code}: required_fields must include code and name")
    max_depth = content.get("max_depth")
    if max_depth is not None and (not isinstance(max_depth, int) or max_depth < 1):
        issues.append(f"{code}: max_depth must be a positive integer")
    return issues
