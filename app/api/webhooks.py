import json
from collections.abc import Callable, Mapping
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.clients.jenkins import JenkinsClient, JenkinsClientError
from app.database import get_db
from app.models import GitHubWebhookDelivery, PipelineRun
from app.schemas_webhook import GitHubWebhookReceipt
from app.services.github_webhook import (
    MAX_WEBHOOK_BODY_BYTES,
    extract_github_metadata,
    verify_github_signature,
)
from app.services.pipeline_dispatch import (
    PipelineDispatchResult,
    dispatch_github_delivery,
)
from app.settings import get_settings

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])
DatabaseSession = Annotated[Session, Depends(get_db)]
GitHubEvent = Annotated[
    str, Header(alias="X-GitHub-Event", min_length=1, max_length=50)
]
GitHubDelivery = Annotated[
    str, Header(alias="X-GitHub-Delivery", min_length=1, max_length=100)
]
GitHubSignature = Annotated[
    str, Header(alias="X-Hub-Signature-256", min_length=1, max_length=100)
]
ReceiptStatus = Literal["accepted", "ignored", "duplicate"]
TriggerBuild = Callable[[Mapping[str, str]], str | None]


def configured_jenkins_trigger(parameters: Mapping[str, str]) -> str | None:
    settings = get_settings()
    username = settings.devflow_jenkins_username
    configured_token = settings.devflow_jenkins_api_token
    if username is None or configured_token is None:
        raise JenkinsClientError("jenkins credentials are not configured")
    api_token = configured_token.get_secret_value()
    if not username or not api_token:
        raise JenkinsClientError("jenkins credentials are not configured")
    return JenkinsClient(
        base_url=settings.devflow_jenkins_url,
        username=username,
        api_token=api_token,
        job_name=settings.devflow_jenkins_job_name,
    ).trigger_build(parameters)


def get_jenkins_trigger() -> TriggerBuild:
    return configured_jenkins_trigger


JenkinsTrigger = Annotated[TriggerBuild, Depends(get_jenkins_trigger)]


def _duplicate_dispatch(
    db: Session, delivery: GitHubWebhookDelivery
) -> PipelineDispatchResult | None:
    if delivery.pipeline_run_id is None:
        return None
    pipeline_run = db.get(PipelineRun, delivery.pipeline_run_id)
    if pipeline_run is None:
        return None
    dispatch_status: Literal["triggered", "failed"]
    dispatch_status = "failed" if pipeline_run.status == "failed" else "triggered"
    return PipelineDispatchResult(
        status=dispatch_status,
        reason="delivery_already_dispatched",
        pipeline_run_id=pipeline_run.id,
        queue_url=pipeline_run.jenkins_queue_url,
    )


def _receipt(
    delivery: GitHubWebhookDelivery,
    receipt_status: ReceiptStatus,
    dispatch: PipelineDispatchResult | None = None,
) -> GitHubWebhookReceipt:
    return GitHubWebhookReceipt(
        id=delivery.id,
        delivery_id=delivery.delivery_id,
        event_type=delivery.event_type,
        status=receipt_status,
        accepted=delivery.accepted,
        received_at=delivery.received_at,
        dispatch_status=None if dispatch is None else dispatch.status,
        dispatch_reason=None if dispatch is None else dispatch.reason,
        pipeline_run_id=None if dispatch is None else dispatch.pipeline_run_id,
        jenkins_queue_url=None if dispatch is None else dispatch.queue_url,
    )


def _webhook_secret() -> str:
    configured_secret = get_settings().devflow_github_webhook_secret
    if configured_secret is None or not configured_secret.get_secret_value():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="github webhook secret is not configured",
        )
    return configured_secret.get_secret_value()


@router.post(
    "/github",
    response_model=GitHubWebhookReceipt,
    status_code=status.HTTP_202_ACCEPTED,
)
async def receive_github_webhook(
    request: Request,
    response: Response,
    db: DatabaseSession,
    trigger_build: JenkinsTrigger,
    event_header: GitHubEvent,
    delivery_header: GitHubDelivery,
    signature_header: GitHubSignature,
) -> GitHubWebhookReceipt:
    body = await request.body()
    if len(body) > MAX_WEBHOOK_BODY_BYTES:
        raise HTTPException(
            status_code=413, detail="github webhook payload is too large"
        )
    if not verify_github_signature(body, signature_header, _webhook_secret()):
        raise HTTPException(status_code=401, detail="invalid github webhook signature")
    try:
        payload: Any = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise HTTPException(
            status_code=400, detail="invalid github webhook JSON"
        ) from error
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=400, detail="github webhook payload must be an object"
        )

    event_type = event_header.strip().lower()
    delivery_id = delivery_header.strip()
    existing = db.scalar(
        select(GitHubWebhookDelivery).where(
            GitHubWebhookDelivery.delivery_id == delivery_id
        )
    )
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return _receipt(existing, "duplicate", _duplicate_dispatch(db, existing))

    repository_full_name, git_ref, commit_sha = extract_github_metadata(payload)
    accepted = event_type in {"ping", "push"}
    delivery = GitHubWebhookDelivery(
        delivery_id=delivery_id,
        event_type=event_type,
        repository_full_name=repository_full_name,
        git_ref=git_ref,
        commit_sha=commit_sha,
        accepted=accepted,
    )
    db.add(delivery)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        duplicate = db.scalar(
            select(GitHubWebhookDelivery).where(
                GitHubWebhookDelivery.delivery_id == delivery_id
            )
        )
        if duplicate is None:
            raise
        response.status_code = status.HTTP_200_OK
        return _receipt(duplicate, "duplicate", _duplicate_dispatch(db, duplicate))

    db.refresh(delivery)
    dispatch = dispatch_github_delivery(db, delivery, trigger_build)
    db.refresh(delivery)
    receipt_status: ReceiptStatus = "accepted" if accepted else "ignored"
    return _receipt(delivery, receipt_status, dispatch)
