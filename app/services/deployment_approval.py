from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Approval, AuditEvent, Deployment, PipelineRun
from app.schemas_delivery import ApprovalDecision, DeploymentRequest


class DeploymentNotFoundError(LookupError):
    pass


class DeploymentConflictError(ValueError):
    pass


def create_deployment_request(
    db: Session,
    payload: DeploymentRequest,
) -> Deployment:
    existing = db.scalar(
        select(Deployment).where(Deployment.pipeline_run_id == payload.pipeline_run_id)
    )
    if existing is not None:
        return existing

    pipeline_run = db.get(PipelineRun, payload.pipeline_run_id)
    if pipeline_run is None:
        raise DeploymentNotFoundError("pipeline run not found")
    if pipeline_run.status != "succeeded":
        raise DeploymentConflictError("pipeline run has not succeeded")
    if not pipeline_run.image_reference:
        raise DeploymentConflictError("pipeline run has no image reference")

    deployment = Deployment(
        pipeline_run_id=pipeline_run.id,
        environment_id=pipeline_run.environment_id,
        image_reference=pipeline_run.image_reference,
        previous_image_reference=payload.previous_image_reference,
        helm_release=payload.helm_release,
        namespace=payload.namespace,
        status="awaiting_approval",
        requested_by=payload.requested_by,
    )
    deployment.approval = Approval(
        decision="pending",
        requested_by=payload.requested_by,
    )
    deployment.audit_events.append(
        AuditEvent(
            pipeline_run_id=pipeline_run.id,
            event_type="deployment.requested",
            actor=payload.requested_by,
            occurred_at=datetime.now(UTC),
            details={
                "image_reference": pipeline_run.image_reference,
                "namespace": payload.namespace,
                "helm_release": payload.helm_release,
            },
        )
    )
    db.add(deployment)
    db.commit()
    db.refresh(deployment)
    return deployment


def get_deployment(db: Session, deployment_id: UUID) -> Deployment:
    deployment = db.get(Deployment, deployment_id)
    if deployment is None:
        raise DeploymentNotFoundError("deployment not found")
    return deployment


def decide_deployment(
    db: Session,
    deployment_id: UUID,
    payload: ApprovalDecision,
) -> Approval:
    deployment = get_deployment(db, deployment_id)
    approval = db.scalar(
        select(Approval).where(Approval.deployment_id == deployment.id)
    )
    if approval is None:
        raise DeploymentNotFoundError("approval not found")

    if approval.decision == payload.decision:
        return approval
    if approval.decision != "pending":
        raise DeploymentConflictError("approval decision is already final")
    if deployment.status != "awaiting_approval":
        raise DeploymentConflictError("deployment is not awaiting approval")

    now = datetime.now(UTC)
    approval.decision = payload.decision
    approval.decided_by = payload.actor
    approval.reason = payload.reason
    approval.decided_at = now
    deployment.status = payload.decision
    if payload.decision == "rejected":
        deployment.finished_at = now

    db.add(
        AuditEvent(
            deployment_id=deployment.id,
            pipeline_run_id=deployment.pipeline_run_id,
            event_type=f"deployment.{payload.decision}",
            actor=payload.actor,
            occurred_at=now,
            details={
                "decision": payload.decision,
                "reason": payload.reason,
            },
        )
    )
    db.commit()
    db.refresh(approval)
    return approval


def list_deployment_audit_events(
    db: Session,
    deployment_id: UUID,
) -> list[AuditEvent]:
    get_deployment(db, deployment_id)
    return list(
        db.scalars(
            select(AuditEvent)
            .where(AuditEvent.deployment_id == deployment_id)
            .order_by(AuditEvent.occurred_at, AuditEvent.id)
        )
    )
