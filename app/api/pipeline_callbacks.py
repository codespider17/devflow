from hmac import compare_digest
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import PipelineRun
from app.schemas import PipelineRunRead, PipelineRunStatusUpdate
from app.services.pipeline_status import (
    InvalidPipelineStatusTransition,
    update_pipeline_run_status,
)
from app.settings import get_settings

router = APIRouter(prefix="/api/v1/pipeline-runs", tags=["pipeline-callbacks"])
DatabaseSession = Annotated[Session, Depends(get_db)]
AuthorizationHeader = Annotated[str | None, Header(alias="Authorization")]


def require_pipeline_callback_token(
    authorization: AuthorizationHeader = None,
) -> None:
    configured_token = get_settings().devflow_pipeline_callback_token
    if configured_token is None or not configured_token.get_secret_value():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="pipeline callback token is not configured",
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
            detail="invalid pipeline callback token",
            headers={"WWW-Authenticate": "Bearer"},
        )


CallbackAuthorization = Annotated[None, Depends(require_pipeline_callback_token)]


@router.post(
    "/{pipeline_run_id}/status",
    response_model=PipelineRunRead,
)
def update_pipeline_status(
    pipeline_run_id: UUID,
    payload: PipelineRunStatusUpdate,
    db: DatabaseSession,
    _authorization: CallbackAuthorization,
) -> PipelineRun:
    pipeline_run = db.get(PipelineRun, pipeline_run_id)
    if pipeline_run is None:
        raise HTTPException(status_code=404, detail="pipeline run not found")

    try:
        return update_pipeline_run_status(
            db,
            pipeline_run,
            payload.status,
            payload.image_reference,
        )
    except InvalidPipelineStatusTransition as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
