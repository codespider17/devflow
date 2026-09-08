from hmac import compare_digest
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Approval, AuditEvent, Deployment
from app.schemas_delivery import (
    ApprovalDecision,
    ApprovalRead,
    AuditEventRead,
    DeploymentRead,
    DeploymentRequest,
)
from app.services.deployment_approval import (
    DeploymentConflictError,
    DeploymentNotFoundError,
    create_deployment_request,
    decide_deployment,
    get_deployment,
    list_deployment_audit_events,
)
from app.settings import get_settings

router = APIRouter(prefix="/api/v1/deployments", tags=["deployments"])
DatabaseSession = Annotated[Session, Depends(get_db)]
AuthorizationHeader = Annotated[str | None, Header(alias="Authorization")]


def require_approval_api_token(
    authorization: AuthorizationHeader = None,
) -> None:
    configured_token = get_settings().devflow_approval_api_token
    if configured_token is None or not configured_token.get_secret_value():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="approval api token is not configured",
        )
    scheme, separator, supplied_token = (authorization or "").partition(" ")
    expected_token = configured_token.get_secret_value()
    if (
        scheme.lower() != "bearer"
        or not separator
        or not supplied_token
        or not compare_digest(supplied_token, expected_token)
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid approval api token",
            headers={"WWW-Authenticate": "Bearer"},
        )


ApprovalAuthorization = Annotated[None, Depends(require_approval_api_token)]


def _translate_service_error(error: Exception) -> HTTPException:
    if isinstance(error, DeploymentNotFoundError):
        return HTTPException(status_code=404, detail=str(error))
    return HTTPException(status_code=409, detail=str(error))


@router.post("", response_model=DeploymentRead, status_code=status.HTTP_201_CREATED)
def request_deployment(
    payload: DeploymentRequest,
    db: DatabaseSession,
    _authorization: ApprovalAuthorization,
) -> Deployment:
    try:
        return create_deployment_request(db, payload)
    except (DeploymentNotFoundError, DeploymentConflictError) as error:
        raise _translate_service_error(error) from error


@router.get("/{deployment_id}", response_model=DeploymentRead)
def read_deployment(
    deployment_id: UUID,
    db: DatabaseSession,
    _authorization: ApprovalAuthorization,
) -> Deployment:
    try:
        return get_deployment(db, deployment_id)
    except DeploymentNotFoundError as error:
        raise _translate_service_error(error) from error


@router.post("/{deployment_id}/decision", response_model=ApprovalRead)
def update_deployment_decision(
    deployment_id: UUID,
    payload: ApprovalDecision,
    db: DatabaseSession,
    _authorization: ApprovalAuthorization,
) -> Approval:
    try:
        return decide_deployment(db, deployment_id, payload)
    except (DeploymentNotFoundError, DeploymentConflictError) as error:
        raise _translate_service_error(error) from error


@router.get(
    "/{deployment_id}/audit-events",
    response_model=list[AuditEventRead],
)
def read_deployment_audit_events(
    deployment_id: UUID,
    db: DatabaseSession,
    _authorization: ApprovalAuthorization,
) -> list[AuditEvent]:
    try:
        return list_deployment_audit_events(db, deployment_id)
    except DeploymentNotFoundError as error:
        raise _translate_service_error(error) from error
