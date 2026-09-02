from collections.abc import Generator
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import engine, get_db
from app.main import app
from app.models import Environment, PipelineRun, Project
from app.settings import get_settings

TEST_CALLBACK_TOKEN = "test-pipeline-callback-token"


@dataclass
class StatusTestContext:
    client: TestClient
    session: Session
    pipeline_run_id: UUID


@pytest.fixture
def status_context(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[StatusTestContext]:
    monkeypatch.setenv("DEVFLOW_PIPELINE_CALLBACK_TOKEN", TEST_CALLBACK_TOKEN)
    get_settings.cache_clear()
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    suffix = uuid4().hex
    project = Project(
        name=f"status-test-{suffix}",
        repository_url=f"git@github.com:codespider17/status-test-{suffix}.git",
        default_branch="main",
    )
    session.add(project)
    session.flush()
    environment = Environment(
        project_id=project.id,
        name="development",
        namespace="devflow-apps",
    )
    session.add(environment)
    session.flush()
    pipeline_run = PipelineRun(
        project_id=project.id,
        environment_id=environment.id,
        commit_sha="c" * 40,
        status="queued",
        trigger_source="github",
    )
    session.add(pipeline_run)
    session.commit()

    def override_get_db() -> Generator[Session]:
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            yield StatusTestContext(client, session, pipeline_run.id)
    finally:
        app.dependency_overrides.clear()
        session.close()
        transaction.rollback()
        connection.close()
        get_settings.cache_clear()


def _headers(token: str = TEST_CALLBACK_TOKEN) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _update(
    context: StatusTestContext,
    new_status: str,
    image_reference: str | None = None,
):
    payload: dict[str, str] = {"status": new_status}
    if image_reference is not None:
        payload["image_reference"] = image_reference
    return context.client.post(
        f"/api/v1/pipeline-runs/{context.pipeline_run_id}/status",
        headers=_headers(),
        json=payload,
    )


def test_queued_run_can_transition_to_running(
    status_context: StatusTestContext,
) -> None:
    response = _update(status_context, "running")
    assert response.status_code == 200
    assert response.json()["status"] == "running"
    assert response.json()["started_at"] is not None
    assert response.json()["finished_at"] is None


def test_running_run_can_succeed_with_image(status_context: StatusTestContext) -> None:
    assert _update(status_context, "running").status_code == 200
    response = _update(status_context, "succeeded", "harbor.local/devflow/api:sha")
    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"
    assert response.json()["finished_at"] is not None
    assert response.json()["image_reference"] == "harbor.local/devflow/api:sha"


def test_queued_run_cannot_skip_directly_to_succeeded(
    status_context: StatusTestContext,
) -> None:
    response = _update(status_context, "succeeded")
    assert response.status_code == 409
    assert "queued -> succeeded" in response.json()["detail"]


def test_same_running_status_is_idempotent(status_context: StatusTestContext) -> None:
    first = _update(status_context, "running")
    second = _update(status_context, "running")
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["started_at"] == first.json()["started_at"]


def test_terminal_run_cannot_transition_again(
    status_context: StatusTestContext,
) -> None:
    failed = _update(status_context, "failed")
    assert failed.status_code == 200
    assert failed.json()["finished_at"] is not None
    response = _update(status_context, "running")
    assert response.status_code == 409
    assert "terminal pipeline run" in response.json()["detail"]


def test_invalid_or_missing_token_is_rejected(
    status_context: StatusTestContext,
) -> None:
    url = f"/api/v1/pipeline-runs/{status_context.pipeline_run_id}/status"
    wrong = status_context.client.post(
        url, headers=_headers("wrong-token"), json={"status": "running"}
    )
    missing = status_context.client.post(url, json={"status": "running"})
    assert wrong.status_code == 401
    assert missing.status_code == 401


def test_unknown_pipeline_run_returns_not_found(
    status_context: StatusTestContext,
) -> None:
    response = status_context.client.post(
        f"/api/v1/pipeline-runs/{uuid4()}/status",
        headers=_headers(),
        json={"status": "running"},
    )
    assert response.status_code == 404
