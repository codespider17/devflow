from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.clients.jenkins import JenkinsClientError
from app.models import Environment, GitHubWebhookDelivery, PipelineRun, Project

TriggerBuild = Callable[[Mapping[str, str]], str | None]
DispatchStatus = Literal["triggered", "ignored", "failed"]


@dataclass(frozen=True)
class PipelineDispatchResult:
    status: DispatchStatus
    reason: str
    pipeline_run_id: UUID | None = None
    queue_url: str | None = None


def repository_matches(repository_url: str, repository_full_name: str) -> bool:
    full_name = repository_full_name.strip().strip("/")
    if full_name.count("/") != 1:
        return False

    normalized_url = repository_url.strip().removesuffix(".git").rstrip("/")
    candidates = {
        f"https://github.com/{full_name}",
        f"git@github.com:{full_name}",
        f"ssh://git@github.com/{full_name}",
    }
    return normalized_url in candidates


def dispatch_github_delivery(
    db: Session,
    delivery: GitHubWebhookDelivery,
    trigger_build: TriggerBuild,
    environment_name: str = "development",
) -> PipelineDispatchResult:
    if delivery.pipeline_run_id is not None:
        return PipelineDispatchResult(
            status="ignored",
            reason="delivery_already_dispatched",
            pipeline_run_id=delivery.pipeline_run_id,
        )

    if delivery.event_type != "push":
        return PipelineDispatchResult(status="ignored", reason="event_not_push")

    if delivery.git_ref is None or delivery.commit_sha is None:
        return PipelineDispatchResult(
            status="ignored",
            reason="invalid_push_metadata",
        )

    projects = db.scalars(select(Project).order_by(Project.created_at)).all()
    project = next(
        (
            candidate
            for candidate in projects
            if repository_matches(
                candidate.repository_url,
                delivery.repository_full_name,
            )
        ),
        None,
    )
    if project is None:
        return PipelineDispatchResult(
            status="ignored",
            reason="repository_not_registered",
        )

    if delivery.git_ref != f"refs/heads/{project.default_branch}":
        return PipelineDispatchResult(
            status="ignored",
            reason="branch_not_default",
        )

    environment = db.scalar(
        select(Environment).where(
            Environment.project_id == project.id,
            Environment.name == environment_name,
        )
    )
    if environment is None:
        return PipelineDispatchResult(
            status="ignored",
            reason="environment_not_configured",
        )

    pipeline_run = PipelineRun(
        project_id=project.id,
        environment_id=environment.id,
        commit_sha=delivery.commit_sha.lower(),
        status="queued",
        trigger_source="github",
    )
    db.add(pipeline_run)
    db.flush()
    delivery.pipeline_run_id = pipeline_run.id

    parameters = {
        "PIPELINE_RUN_ID": str(pipeline_run.id),
        "GIT_COMMIT_SHA": pipeline_run.commit_sha,
    }

    try:
        queue_url = trigger_build(parameters)
        if not queue_url:
            raise JenkinsClientError("jenkins did not return a queue URL")
    except JenkinsClientError:
        pipeline_run.status = "failed"
        pipeline_run.trigger_error = "jenkins trigger request failed"
        pipeline_run.finished_at = datetime.now(UTC)
        db.commit()
        return PipelineDispatchResult(
            status="failed",
            reason="jenkins_trigger_failed",
            pipeline_run_id=pipeline_run.id,
        )

    pipeline_run.jenkins_queue_url = queue_url[:500]
    db.commit()
    return PipelineDispatchResult(
        status="triggered",
        reason="jenkins_queued",
        pipeline_run_id=pipeline_run.id,
        queue_url=pipeline_run.jenkins_queue_url,
    )
