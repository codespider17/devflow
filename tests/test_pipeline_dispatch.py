from collections.abc import Generator, Mapping
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.clients.jenkins import JenkinsClientError
from app.database import engine
from app.models import Environment, GitHubWebhookDelivery, PipelineRun, Project
from app.services.pipeline_dispatch import dispatch_github_delivery


@pytest.fixture
def dispatch_session() -> Generator[Session]:
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


def create_case(
    session: Session,
    *,
    repository_full_name: str | None = None,
    git_ref: str = "refs/heads/main",
    event_type: str = "push",
    create_environment: bool = True,
) -> GitHubWebhookDelivery:
    suffix = uuid4().hex
    registered_repository = f"codespider17/devflow-test-{suffix}"
    project = Project(
        name=f"devflow-{suffix}",
        repository_url=f"git@github.com:{registered_repository}.git",
        default_branch="main",
    )
    session.add(project)
    session.flush()

    if create_environment:
        session.add(
            Environment(
                project_id=project.id,
                name="development",
                namespace="devflow-apps",
            )
        )

    delivery = GitHubWebhookDelivery(
        delivery_id=f"delivery-{suffix}",
        event_type=event_type,
        repository_full_name=repository_full_name or registered_repository,
        git_ref=git_ref,
        commit_sha="a" * 40,
        accepted=event_type in {"ping", "push"},
    )
    session.add(delivery)
    session.commit()
    return delivery


def test_matching_push_creates_and_queues_pipeline_run(
    dispatch_session: Session,
) -> None:
    delivery = create_case(dispatch_session)
    captured: list[Mapping[str, str]] = []

    def trigger(parameters: Mapping[str, str]) -> str:
        captured.append(parameters)
        return "http://jenkins.example/queue/item/7/"

    result = dispatch_github_delivery(dispatch_session, delivery, trigger)

    assert result.status == "triggered"
    assert result.pipeline_run_id is not None
    pipeline_run = dispatch_session.get(PipelineRun, result.pipeline_run_id)
    assert pipeline_run is not None
    assert pipeline_run.status == "queued"
    assert pipeline_run.trigger_source == "github"
    assert pipeline_run.jenkins_queue_url == result.queue_url
    assert delivery.pipeline_run_id == pipeline_run.id
    assert captured == [
        {
            "PIPELINE_RUN_ID": str(pipeline_run.id),
            "GIT_COMMIT_SHA": "a" * 40,
        }
    ]


def test_same_delivery_is_not_triggered_twice(
    dispatch_session: Session,
) -> None:
    delivery = create_case(dispatch_session)
    calls = 0

    def trigger(parameters: Mapping[str, str]) -> str:
        nonlocal calls
        calls += 1
        return "http://jenkins.example/queue/item/8/"

    first = dispatch_github_delivery(dispatch_session, delivery, trigger)
    second = dispatch_github_delivery(dispatch_session, delivery, trigger)

    assert first.status == "triggered"
    assert second.status == "ignored"
    assert second.reason == "delivery_already_dispatched"
    assert calls == 1


def test_non_default_branch_is_ignored(dispatch_session: Session) -> None:
    delivery = create_case(
        dispatch_session,
        git_ref="refs/heads/feature/test",
    )
    result = dispatch_github_delivery(
        dispatch_session,
        delivery,
        lambda parameters: "unexpected",
    )

    assert result.status == "ignored"
    assert result.reason == "branch_not_default"
    assert delivery.pipeline_run_id is None


def test_unregistered_repository_is_ignored(
    dispatch_session: Session,
) -> None:
    delivery = create_case(
        dispatch_session,
        repository_full_name="someone/other",
    )
    result = dispatch_github_delivery(
        dispatch_session,
        delivery,
        lambda parameters: "unexpected",
    )

    assert result.status == "ignored"
    assert result.reason == "repository_not_registered"


def test_missing_environment_is_ignored(dispatch_session: Session) -> None:
    delivery = create_case(dispatch_session, create_environment=False)
    result = dispatch_github_delivery(
        dispatch_session,
        delivery,
        lambda parameters: "unexpected",
    )

    assert result.status == "ignored"
    assert result.reason == "environment_not_configured"


def test_jenkins_failure_is_persisted_without_secret(
    dispatch_session: Session,
) -> None:
    delivery = create_case(dispatch_session)

    def trigger(parameters: Mapping[str, str]) -> str:
        raise JenkinsClientError("secret-token-must-not-be-stored")

    result = dispatch_github_delivery(dispatch_session, delivery, trigger)

    assert result.status == "failed"
    assert result.pipeline_run_id is not None
    pipeline_run = dispatch_session.get(PipelineRun, result.pipeline_run_id)
    assert pipeline_run is not None
    assert pipeline_run.status == "failed"
    assert pipeline_run.finished_at is not None
    assert pipeline_run.trigger_error == "jenkins trigger request failed"
    assert "secret-token" not in pipeline_run.trigger_error
    count = dispatch_session.scalar(
        select(func.count())
        .select_from(PipelineRun)
        .where(PipelineRun.project_id == pipeline_run.project_id)
    )
    assert count == 1
