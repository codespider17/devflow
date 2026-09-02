from datetime import UTC, datetime
from typing import Literal

from sqlalchemy.orm import Session

from app.models import PipelineRun

PipelineStatus = Literal["queued", "running", "succeeded", "failed", "cancelled"]
CallbackStatus = Literal["running", "succeeded", "failed", "cancelled"]
TERMINAL_STATUSES = {"succeeded", "failed", "cancelled"}
ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "queued": {"running", "failed", "cancelled"},
    "running": {"succeeded", "failed", "cancelled"},
}


class InvalidPipelineStatusTransition(ValueError):
    pass


def update_pipeline_run_status(
    db: Session,
    pipeline_run: PipelineRun,
    new_status: CallbackStatus,
    image_reference: str | None = None,
) -> PipelineRun:
    current_status: PipelineStatus = pipeline_run.status
    if new_status == current_status:
        if image_reference is not None:
            pipeline_run.image_reference = image_reference
            db.commit()
            db.refresh(pipeline_run)
        return pipeline_run

    if current_status in TERMINAL_STATUSES:
        raise InvalidPipelineStatusTransition(
            f"terminal pipeline run cannot transition from {current_status}"
        )

    if new_status not in ALLOWED_TRANSITIONS.get(current_status, set()):
        raise InvalidPipelineStatusTransition(
            f"invalid pipeline run transition: {current_status} -> {new_status}"
        )

    now = datetime.now(UTC)
    pipeline_run.status = new_status
    if new_status == "running" and pipeline_run.started_at is None:
        pipeline_run.started_at = now
    if new_status in TERMINAL_STATUSES:
        pipeline_run.finished_at = now
    if image_reference is not None:
        pipeline_run.image_reference = image_reference

    db.commit()
    db.refresh(pipeline_run)
    return pipeline_run
