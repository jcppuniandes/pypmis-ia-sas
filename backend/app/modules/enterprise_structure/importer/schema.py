"""Canonical JSON Schema projection for external tooling and templates."""

from typing import Any

from app.modules.enterprise_structure.importer.models import EnterpriseStructureImport


def canonical_json_schema() -> dict[str, Any]:
    return EnterpriseStructureImport.model_json_schema()
