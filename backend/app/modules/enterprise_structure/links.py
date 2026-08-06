"""Validation for relationships that must not distort the hierarchy."""

from fastapi import HTTPException

from app.domain.models import EnterpriseWorkspace
from app.modules.enterprise_structure.constants import RELATIONSHIP_TYPES


def validate_workspace_link(
    source: EnterpriseWorkspace,
    target: EnterpriseWorkspace,
    relationship_type: str,
) -> None:
    if source.id == target.id:
        raise HTTPException(status_code=409, detail="A workspace cannot link to itself")
    if relationship_type not in RELATIONSHIP_TYPES:
        raise HTTPException(status_code=422, detail=f"Unsupported relationship type: {relationship_type}")
    pair = (source.workspace_type_code, target.workspace_type_code)
    allowed_pairs = {
        ("project", "property"),
        ("project", "facility"),
        ("property", "business-unit"),
        ("facility", "business-unit"),
    }
    if pair not in allowed_pairs:
        raise HTTPException(
            status_code=409,
            detail=f"Relationship is not supported between {pair[0]} and {pair[1]}",
        )
