import json
from collections.abc import Generator, Mapping
from dataclasses import dataclass
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.webhooks import get_jenkins_trigger
from app.clients.jenkins import JenkinsClientError
from app.database import engine, get_db
from app.main import app
from app.models import Environment, GitHubWebhookDelivery, PipelineRun, Project
from app.services.github_webhook import build_github_signature
from app.settings import get_settings

TEST_SECRET = "integration-test-webhook-secret"
TEST_REPOSITORY = "codespider17/devflow-webhook-test"


@dataclass
class WebhookTestContext:
    client: TestClient
    session: Session
    trigger_calls: list[dict[str, str]]


@pytest.fixture
def webhook_context(monkeypatch: pytest.MonkeyPatch) -> Generator[WebhookTestContext]:
    monkeypatch.setenv("DEVFLOW_GITHUB_WEBHOOK_SECRET", TEST_SECRET)
    get_settings.cache_clear()
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    project = Project(
        name=f"webhook-test-{uuid4().hex}",
        repository_url=f"git@github.com:{TEST_REPOSITORY}.git",
        default_branch="main",
    )
    session.add(project)
    session.flush()
    session.add(
        Environment(project_id=project.id, name="development", namespace="devflow-apps")
    )
    session.commit()
    calls: list[dict[str, str]] = []

    def override_get_db() -> Generator[Session]:
        yield session

    def fake_trigger(parameters: Mapping[str, str]) -> str:
        calls.append(dict(parameters))
        return "http://jenkins.test/queue/item/42/"

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_jenkins_trigger] = lambda: fake_trigger
    try:
        with TestClient(app) as client:
            yield WebhookTestContext(client, session, calls)
    finally:
        app.dependency_overrides.clear()
        session.close()
        transaction.rollback()
        connection.close()
        get_settings.cache_clear()


def _request(
    client: TestClient,
    delivery_id: str,
    event_type: str = "push",
    payload: dict[str, object] | None = None,
    secret: str = TEST_SECRET,
):
    data = payload or {
        "ref": "refs/heads/main",
        "after": "a" * 40,
        "repository": {"full_name": TEST_REPOSITORY},
    }
    body = json.dumps(data, separators=(",", ":"), sort_keys=True).encode()
    return client.post(
        "/api/v1/webhooks/github",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": event_type,
            "X-GitHub-Delivery": delivery_id,
            "X-Hub-Signature-256": build_github_signature(body, secret),
        },
    )


def test_valid_push_creates_run_and_triggers_jenkins(
    webhook_context: WebhookTestContext,
) -> None:
    response = _request(webhook_context.client, "delivery-valid")
    receipt = response.json()
    assert response.status_code == 202
    assert receipt["status"] == "accepted"
    assert receipt["dispatch_status"] == "triggered"
    assert receipt["dispatch_reason"] == "jenkins_queued"
    assert receipt["jenkins_queue_url"] == "http://jenkins.test/queue/item/42/"
    assert len(webhook_context.trigger_calls) == 1
    run = webhook_context.session.get(PipelineRun, receipt["pipeline_run_id"])
    assert run is not None
    assert run.status == "queued"
    assert run.trigger_source == "github"


def test_duplicate_delivery_does_not_trigger_twice(
    webhook_context: WebhookTestContext,
) -> None:
    first = _request(webhook_context.client, "delivery-duplicate")
    duplicate = _request(webhook_context.client, "delivery-duplicate")
    assert first.status_code == 202
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "duplicate"
    assert duplicate.json()["pipeline_run_id"] == first.json()["pipeline_run_id"]
    assert len(webhook_context.trigger_calls) == 1
    count = webhook_context.session.scalar(
        select(func.count())
        .select_from(GitHubWebhookDelivery)
        .where(GitHubWebhookDelivery.delivery_id == "delivery-duplicate")
    )
    assert count == 1


def test_invalid_signature_is_rejected(webhook_context: WebhookTestContext) -> None:
    response = _request(
        webhook_context.client, "delivery-invalid", secret="wrong-secret"
    )
    assert response.status_code == 401
    assert not webhook_context.trigger_calls


def test_unsupported_event_is_recorded_without_trigger(
    webhook_context: WebhookTestContext,
) -> None:
    response = _request(webhook_context.client, "delivery-ignored", event_type="issues")
    assert response.status_code == 202
    assert response.json()["status"] == "ignored"
    assert response.json()["dispatch_reason"] == "event_not_push"
    assert not webhook_context.trigger_calls


def test_ping_is_accepted_without_trigger(webhook_context: WebhookTestContext) -> None:
    response = _request(webhook_context.client, "delivery-ping", event_type="ping")
    assert response.status_code == 202
    assert response.json()["status"] == "accepted"
    assert response.json()["dispatch_reason"] == "event_not_push"
    assert not webhook_context.trigger_calls


def test_non_default_branch_is_ignored_by_dispatch(
    webhook_context: WebhookTestContext,
) -> None:
    response = _request(
        webhook_context.client,
        "delivery-feature",
        payload={
            "ref": "refs/heads/feature/test",
            "after": "b" * 40,
            "repository": {"full_name": TEST_REPOSITORY},
        },
    )
    assert response.status_code == 202
    assert response.json()["dispatch_reason"] == "branch_not_default"
    assert response.json()["pipeline_run_id"] is None
    assert not webhook_context.trigger_calls


def test_jenkins_failure_is_persisted_without_secret(
    webhook_context: WebhookTestContext,
) -> None:
    def failing_trigger(parameters: Mapping[str, str]) -> str | None:
        del parameters
        raise JenkinsClientError("sensitive-token-from-provider")

    app.dependency_overrides[get_jenkins_trigger] = lambda: failing_trigger
    response = _request(webhook_context.client, "delivery-failed")
    receipt = response.json()
    assert response.status_code == 202
    assert receipt["dispatch_status"] == "failed"
    assert receipt["dispatch_reason"] == "jenkins_trigger_failed"
    run = webhook_context.session.get(PipelineRun, receipt["pipeline_run_id"])
    assert run is not None
    assert run.status == "failed"
    assert run.trigger_error == "jenkins trigger request failed"
    assert "sensitive-token" not in run.trigger_error


def test_oversized_payload_is_rejected(webhook_context: WebhookTestContext) -> None:
    body = b"x" * 1_048_577
    response = webhook_context.client.post(
        "/api/v1/webhooks/github",
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-GitHub-Delivery": "delivery-large",
            "X-Hub-Signature-256": build_github_signature(body, TEST_SECRET),
        },
    )
    assert response.status_code == 413
    assert not webhook_context.trigger_calls
