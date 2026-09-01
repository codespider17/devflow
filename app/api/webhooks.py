from json import JSONDecodeError, loads
from typing import Annotated, Any, Literal

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Request,
    Response,
    status,
)
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import GitHubWebhookDelivery
from app.schemas_webhook import GitHubWebhookReceipt
from app.services.github_webhook import (
    MAX_WEBHOOK_BODY_BYTES,
    extract_github_metadata,
    verify_github_signature,
)
from app.settings import get_settings

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])
DatabaseSession = Annotated[Session, Depends(get_db)]
GitHubEvent = Annotated[
    str,
    Header(alias="X-GitHub-Event", min_length=1, max_length=50),
]
GitHubDelivery = Annotated[
    str,
    Header(alias="X-GitHub-Delivery", min_length=1, max_length=100),
]
GitHubSignature = Annotated[
    str,
    Header(alias="X-Hub-Signature-256", min_length=1, max_length=100),
]
ReceiptStatus = Literal["accepted", "ignored", "duplicate"]


def _receipt(
    delivery: GitHubWebhookDelivery,
    receipt_status: ReceiptStatus,
) -> GitHubWebhookReceipt:
    return GitHubWebhookReceipt(
        id=delivery.id,
        delivery_id=delivery.delivery_id,
        event_type=delivery.event_type,
        status=receipt_status,
        accepted=delivery.accepted,
        received_at=delivery.received_at,
    )


def _webhook_secret() -> str:
    configured_secret = get_settings().devflow_github_webhook_secret
    if configured_secret is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="github webhook secret is not configured",
        )

    secret = configured_secret.get_secret_value()
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="github webhook secret is not configured",
        )
    return secret


@router.post(
    "/github",
    response_model=GitHubWebhookReceipt,
    status_code=status.HTTP_202_ACCEPTED,
)
async def receive_github_webhook(
    request: Request,
    response: Response,
    db: DatabaseSession,
    event_header: GitHubEvent,
    delivery_header: GitHubDelivery,
    signature_header: GitHubSignature,
) -> GitHubWebhookReceipt:
    body = await request.body()
    if len(body) > MAX_WEBHOOK_BODY_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="github webhook payload is too large",
        )

    if not verify_github_signature(body, signature_header, _webhook_secret()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid github webhook signature",
        )

    try:
        payload: Any = loads(body)
    except (JSONDecodeError, UnicodeDecodeError) as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid github webhook JSON",
        ) from error

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="github webhook payload must be an object",
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
        return _receipt(existing, "duplicate")

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
        return _receipt(duplicate, "duplicate")

    db.refresh(delivery)
    receipt_status: ReceiptStatus = "accepted" if accepted else "ignored"
    return _receipt(delivery, receipt_status)
