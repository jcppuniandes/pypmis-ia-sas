"""USER and ADMIN APIs for Gate 07B Project Proposal."""

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.deps import get_tenant_id, get_user_id
from app.database.session import get_db
from app.domain.schemas import AdminConfigurationOut
from app.modules.enterprise_structure.permissions import EnterprisePermissionContext, require_enterprise_permission
from app.modules.project_proposal.schemas import (
    GateReadinessOut,
    ProjectProposalCreate,
    ProjectProposalEvaluationOut,
    ProjectProposalOut,
    ProjectProposalUpdate,
    ProposalConfigurationPreviewIn,
    ProposalConfigurationPreviewOut,
    ProposalConfigurationUpdateIn,
    ProposalEvaluationIn,
    ProposalHistoryItemOut,
    ProposalOptionsOut,
    ProposalPreviewOut,
    ProposalReturnIn,
)
from app.modules.project_proposal.service import ProjectProposalService

router = APIRouter(prefix="/project-proposals")
idea_router = APIRouter(prefix="/ideas")

REQUESTOR_ROLES = frozenset({"organization_admin", "proposal_requestor"})
REVIEWER_ROLES = frozenset({"organization_admin", "proposal_reviewer"})
EVALUATOR_ROLES = frozenset({"organization_admin", "proposal_owner", "proposal_evaluator"})
CONFIG_ROLES = frozenset({"organization_admin", "configuration_admin", "proposal_configuration_admin"})


def _if_match(if_match: str = Header(..., alias="If-Match")) -> int:
    normalized = if_match.strip()
    if normalized.startswith("W/"):
        normalized = normalized[2:]
    normalized = normalized.strip('"')
    if not normalized.isdigit() or int(normalized) < 1:
        raise HTTPException(status_code=400, detail={"reason": "INVALID_IF_MATCH"})
    return int(normalized)


def _authorized(
    db: Session,
    tenant_id: int,
    user_id: int,
    permission: str,
    roles: frozenset[str] | None = None,
) -> tuple[ProjectProposalService, EnterprisePermissionContext]:
    context = require_enterprise_permission(
        db,
        tenant_id,
        user_id,
        permission,
        allowed_role_codes=roles,
    )
    service = ProjectProposalService(db, tenant_id, context.user.id, context)
    service.ensure_seed()
    return service, context


def _etag(response: Response, value: ProjectProposalOut) -> ProjectProposalOut:
    response.headers["ETag"] = f'"{value.revision_version}"'
    response.headers["Cache-Control"] = "private, no-store"
    return value


@router.get("/options", response_model=ProposalOptionsOut)
def options(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProposalOptionsOut:
    service, _ = _authorized(db, tenant_id, user_id, "project_proposal.create")
    return service.options()


@router.post("/preview", response_model=ProposalPreviewOut)
def preview(
    payload: ProjectProposalCreate,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProposalPreviewOut:
    service, _ = _authorized(db, tenant_id, user_id, "project_proposal.create", REQUESTOR_ROLES)
    return service.preview(payload.source_idea_id)


@router.post("", response_model=ProjectProposalOut, status_code=status.HTTP_201_CREATED)
def create(
    payload: ProjectProposalCreate,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectProposalOut:
    service, _ = _authorized(db, tenant_id, user_id, "project_proposal.create", REQUESTOR_ROLES)
    return _etag(response, service.create(payload.source_idea_id))


@router.get("", response_model=list[ProjectProposalOut])
def list_proposals(
    status_filter: str = Query("", alias="status", max_length=48),
    search: str = Query("", max_length=180),
    owning_workspace_id: int | None = None,
    queue: str = Query("", max_length=30),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ProjectProposalOut]:
    service, _ = _authorized(db, tenant_id, user_id, "project_proposal.read")
    return service.list(
        status_filter=status_filter,
        search=search,
        owning_workspace_id=owning_workspace_id,
        queue=queue,
    )


@router.get("/admin/configurations/list", response_model=list[AdminConfigurationOut])
def admin_configurations(
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[AdminConfigurationOut]:
    service, _ = _authorized(
        db,
        tenant_id,
        user_id,
        "project_proposal.admin.configure",
        CONFIG_ROLES,
    )
    return [AdminConfigurationOut.model_validate(item) for item in service.admin_configurations()]


@router.post("/admin/configuration/preview", response_model=ProposalConfigurationPreviewOut)
def configuration_preview(
    payload: ProposalConfigurationPreviewIn,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProposalConfigurationPreviewOut:
    service, _ = _authorized(
        db,
        tenant_id,
        user_id,
        "project_proposal.admin.configure",
        CONFIG_ROLES,
    )
    return service.configuration_preview(payload.source_idea_id)


@router.post("/admin/configurations/{configuration_id}/clone", response_model=AdminConfigurationOut)
def clone_configuration(
    configuration_id: int,
    expected: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AdminConfigurationOut:
    service, _ = _authorized(
        db,
        tenant_id,
        user_id,
        "project_proposal.admin.configure",
        CONFIG_ROLES,
    )
    return AdminConfigurationOut.model_validate(service.clone_configuration(configuration_id, expected))


@router.put("/admin/configurations/{configuration_id}", response_model=AdminConfigurationOut)
def update_configuration(
    configuration_id: int,
    payload: ProposalConfigurationUpdateIn,
    expected: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AdminConfigurationOut:
    service, _ = _authorized(
        db,
        tenant_id,
        user_id,
        "project_proposal.admin.configure",
        CONFIG_ROLES,
    )
    return AdminConfigurationOut.model_validate(
        service.update_configuration(
            configuration_id,
            expected,
            name=payload.name,
            description=payload.description,
            content=payload.content_json,
        )
    )


@router.post("/admin/configurations/{configuration_id}/publish", response_model=AdminConfigurationOut)
def publish_configuration(
    configuration_id: int,
    expected: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> AdminConfigurationOut:
    service, _ = _authorized(
        db,
        tenant_id,
        user_id,
        "project_proposal.admin.publish",
        CONFIG_ROLES,
    )
    return AdminConfigurationOut.model_validate(service.publish_configuration(configuration_id, expected))


@router.get("/{proposal_id}", response_model=ProjectProposalOut)
def get_proposal(
    proposal_id: int,
    response: Response,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectProposalOut:
    service, _ = _authorized(db, tenant_id, user_id, "project_proposal.read")
    return _etag(response, service.get(proposal_id))


@router.put("/{proposal_id}", response_model=ProjectProposalOut)
def update_proposal(
    proposal_id: int,
    payload: ProjectProposalUpdate,
    response: Response,
    expected: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectProposalOut:
    service, _ = _authorized(db, tenant_id, user_id, "project_proposal.edit")
    return _etag(response, service.update(proposal_id, payload, expected))


def _transition_route(permission: str, roles: frozenset[str], method: str):
    def endpoint(
        proposal_id: int,
        response: Response,
        expected: int = Depends(_if_match),
        db: Session = Depends(get_db),
        tenant_id: int = Depends(get_tenant_id),
        user_id: int = Depends(get_user_id),
    ) -> ProjectProposalOut:
        service, _ = _authorized(db, tenant_id, user_id, permission, roles)
        return _etag(response, getattr(service, method)(proposal_id, expected))

    return endpoint


router.add_api_route(
    "/{proposal_id}/submit",
    _transition_route("project_proposal.submit", REQUESTOR_ROLES, "submit"),
    methods=["POST"],
    response_model=ProjectProposalOut,
)
router.add_api_route(
    "/{proposal_id}/start-review",
    _transition_route("project_proposal.review", REVIEWER_ROLES, "start_review"),
    methods=["POST"],
    response_model=ProjectProposalOut,
)
router.add_api_route(
    "/{proposal_id}/start-evaluation",
    _transition_route("project_proposal.evaluate", EVALUATOR_ROLES | REVIEWER_ROLES, "start_evaluation"),
    methods=["POST"],
    response_model=ProjectProposalOut,
)
router.add_api_route(
    "/{proposal_id}/mark-gate-ready",
    _transition_route("project_proposal.mark_gate_ready", REVIEWER_ROLES, "mark_gate_ready"),
    methods=["POST"],
    response_model=ProjectProposalOut,
)
router.add_api_route(
    "/{proposal_id}/cancel",
    _transition_route("project_proposal.cancel", REQUESTOR_ROLES, "cancel"),
    methods=["POST"],
    response_model=ProjectProposalOut,
)


@router.post("/{proposal_id}/return", response_model=ProjectProposalOut)
def return_proposal(
    proposal_id: int,
    payload: ProposalReturnIn,
    response: Response,
    expected: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectProposalOut:
    service, _ = _authorized(db, tenant_id, user_id, "project_proposal.return", REVIEWER_ROLES)
    return _etag(response, service.return_proposal(proposal_id, payload, expected))


@router.post("/{proposal_id}/complete-evaluation", response_model=ProjectProposalOut)
def complete_evaluation(
    proposal_id: int,
    payload: ProposalEvaluationIn,
    response: Response,
    expected: int = Depends(_if_match),
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProjectProposalOut:
    service, _ = _authorized(
        db,
        tenant_id,
        user_id,
        "project_proposal.evaluate",
        EVALUATOR_ROLES,
    )
    return _etag(response, service.complete_evaluation(proposal_id, payload, expected))


@router.get("/{proposal_id}/evaluations", response_model=list[ProjectProposalEvaluationOut])
def evaluations(
    proposal_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ProjectProposalEvaluationOut]:
    service, _ = _authorized(db, tenant_id, user_id, "project_proposal.read")
    return service.evaluations(proposal_id)


@router.get("/{proposal_id}/history", response_model=list[ProposalHistoryItemOut])
def history(
    proposal_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ProposalHistoryItemOut]:
    service, _ = _authorized(db, tenant_id, user_id, "project_proposal.read")
    return service.history(proposal_id)


@router.get("/{proposal_id}/gate-readiness", response_model=GateReadinessOut)
def gate_readiness(
    proposal_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> GateReadinessOut:
    service, _ = _authorized(db, tenant_id, user_id, "project_proposal.read")
    return service.gate_readiness(proposal_id)


@idea_router.get("/{idea_id}/project-proposals", response_model=list[ProjectProposalOut])
def idea_project_proposals(
    idea_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> list[ProjectProposalOut]:
    service, _ = _authorized(db, tenant_id, user_id, "project_proposal.read")
    return service.related_to_idea(idea_id)


@idea_router.post("/{idea_id}/project-proposals/preview", response_model=ProposalPreviewOut)
def idea_project_proposal_preview(
    idea_id: int,
    db: Session = Depends(get_db),
    tenant_id: int = Depends(get_tenant_id),
    user_id: int = Depends(get_user_id),
) -> ProposalPreviewOut:
    service, _ = _authorized(db, tenant_id, user_id, "project_proposal.create", REQUESTOR_ROLES)
    return service.preview(idea_id)
