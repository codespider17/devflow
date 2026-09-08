from hmac import compare_digest
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Deployment
from app.schemas_delivery import DeploymentRead
from app.schemas_deployment_callback import DeploymentStatusUpdate
from app.services.deployment_approval import (
    DeploymentConflictError,
    DeploymentNotFoundError,
)
from app.services.deployment_status import update_deployment_status
from app.settings import get_settings

router = APIRouter(
    prefix="/api/v1/deployments",
    tags=["deployment-callbacks"],
)
DatabaseSession = Annotated[Session, Depends(get_db)]
AuthorizationHeader = Annotated[str | None, Header(alias="Authorization")]


def require_deployment_callback_token(
    authorization: AuthorizationHeader = None,
) -> None:
    configured_token = get_settings().devflow_deployment_callback_token
    if configured_token is None or not configured_token.get_secret_value():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="deployment callback token is not configured",
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
            detail="invalid deployment callback token",
            headers={"WWW-Authenticate": "Bearer"},
        )


DeploymentCallbackAuthorization = Annotated[
    None,
    Depends(require_deployment_callback_token),
]


@router.post(
    "/{deployment_id}/status",
    response_model=DeploymentRead,
)
def write_deployment_status(
    deployment_id: UUID,
    payload: DeploymentStatusUpdate,
    db: DatabaseSession,
    _authorization: DeploymentCallbackAuthorization,
) -> Deployment:
    try:
        return update_deployment_status(db, deployment_id, payload)
    except DeploymentNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except DeploymentConflictError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
