"""Classification rules shared by ADMIN assignment and USER filters."""

from fastapi import HTTPException

from app.domain.models import AdminConfiguration, EnterpriseWorkspace


def validate_classification(
    workspace: EnterpriseWorkspace,
    category: AdminConfiguration,
    item_code: str,
) -> None:
    applicable_types = set(category.content_json.get("applicable_types", []))
    if workspace.workspace_type_code not in applicable_types:
        raise HTTPException(
            status_code=409,
            detail=f"Category {category.code} is not applicable to {workspace.workspace_type_code}",
        )
    items = {str(item.get("code", "")).strip().lower() for item in category.content_json.get("items", [])}
    if item_code not in items:
        raise HTTPException(status_code=422, detail=f"Unknown category item: {item_code}")
