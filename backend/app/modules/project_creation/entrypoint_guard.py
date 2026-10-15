"""Keep legacy ADMIN Workspace commands outside live Project authority."""

from fastapi import HTTPException


def _is_project(type_code: str) -> bool:
    return type_code.strip().lower().replace("_", "-").replace(" ", "-") == "project"


def require_non_project_admin_creation(*type_codes: str) -> None:
    """Check both requested and published/resolved taxonomy, before any DML."""
    if any(_is_project(code) for code in type_codes):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PROJECT_CREATION_PROCESS_REQUIRED",
                "dedicated_api": "/api/v1/project-creation-requests",
                "message": (
                    "Use the governed Project Creation Process; ADMIN configures Workspace Types, "
                    "USER creates Project Workspace Instances."
                ),
            },
        )


def require_governed_project_activation(
    type_code: str, current_status: str, requested_status: str | None, workspace_id: int
) -> None:
    if (
        _is_project(type_code)
        and requested_status is not None
        and requested_status.strip().lower() != current_status.strip().lower()
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PROJECT_WORKSPACE_LIFECYCLE_REQUIRED",
                "dedicated_api": (
                    f"/api/v1/project-workspaces/{workspace_id}/activate"
                    if requested_status.strip().lower() == "active"
                    else f"/api/v1/project-workspaces/{workspace_id}/initialization"
                ),
                "message": (
                    "Use governed Project Workspace Initialization and Activation; ADMIN cannot change a Project lifecycle state. "
                    "Unsupported lifecycle transitions are not released by this endpoint."
                ),
            },
        )
