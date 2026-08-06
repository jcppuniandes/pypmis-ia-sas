"""Meaning-preserving normalization for declarative Enterprise Structure data."""

from __future__ import annotations

from typing import Any

from app.modules.enterprise_structure.importer.models import EnterpriseStructureImport


def _upper(value: str | None) -> str | None:
    normalized = (value or "").strip().upper()
    return normalized or None


def _lower(value: str | None) -> str | None:
    normalized = (value or "").strip().lower()
    return normalized or None


def normalize_configuration(configuration: EnterpriseStructureImport) -> EnterpriseStructureImport:
    payload: dict[str, Any] = configuration.model_dump()
    metadata = payload["metadata"]
    metadata["tenant_code"] = _upper(metadata["tenant_code"])
    metadata["release_code"] = _upper(metadata["release_code"])
    metadata["requested_by"] = _lower(metadata.get("requested_by"))

    for objective in payload["strategic_objectives"]:
        objective["code"] = _upper(objective["code"])
        objective["priority"] = _upper(objective.get("priority"))
        objective["responsible_area"] = _upper(objective.get("responsible_area"))
    for node in payload["nodes"]:
        node["external_key"] = _upper(node["external_key"])
        node["code"] = _upper(node["code"])
        node["parent_external_key"] = _upper(node.get("parent_external_key"))
        node["organization_unit_code"] = _upper(node.get("organization_unit_code"))
        node["responsible_email"] = _lower(node.get("responsible_email"))
        node["region_code"] = _upper(node.get("region_code"))
    for classification in payload["classifications"]:
        classification["workspace_external_key"] = _upper(classification["workspace_external_key"])
        classification["category_set_code"] = _upper(classification["category_set_code"])
        classification["category_item_code"] = _upper(classification["category_item_code"])
    for link in payload["links"]:
        link["source_external_key"] = _upper(link["source_external_key"])
        link["target_external_key"] = _upper(link["target_external_key"])
        link["relationship_type"] = _upper(link["relationship_type"])
    return EnterpriseStructureImport.model_validate(payload)


def internal_code(value: str) -> str:
    return value.strip().lower().replace("_", "-").replace(" ", "-")
