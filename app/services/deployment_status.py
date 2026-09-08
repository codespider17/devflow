from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import AuditEvent, Deployment
from app.schemas_deployment_callback import DeploymentStatusUpdate
from app.services.deployment_approval import (
    DeploymentConflictError,
    get_deployment,
)

ALLOWED_DEPLOYMENT_TRANSITIONS = {
    "approved": {"deploying"},
    "deploying": {"succeeded", "failed"},
    "failed": {"rolled_back"},
}


def update_deployment_status(
    db: Session,
    deployment_id: UUID,
    payload: DeploymentStatusUpdate,
) -> Deployment:
    deployment = get_deployment(db, deployment_id)

    if deployment.status == payload.status:
        return deployment

    allowed_targets = ALLOWED_DEPLOYMENT_TRANSITIONS.get(
        deployment.status,
        set(),
    )
    if payload.status not in allowed_targets:
        raise DeploymentConflictError(
            f"invalid deployment transition: {deployment.status} -> {payload.status}"
        )

    now = datetime.now(UTC)
    deployment.status = payload.status
    if payload.status == "deploying":
        deployment.deployed_at = now
    if payload.status in {"succeeded", "failed", "rolled_back"}:
        deployment.finished_at = now

    details: dict[str, str] = {"status": payload.status}
    if payload.reason:
        details["reason"] = payload.reason

    db.add(
        AuditEvent(
            deployment_id=deployment.id,
            pipeline_run_id=deployment.pipeline_run_id,
            event_type=f"deployment.{payload.status}",
            actor=payload.actor,
            details=details,
            occurred_at=now,
        )
    )
    db.commit()
    db.refresh(deployment)
    return deployment
