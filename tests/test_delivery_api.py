from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.database import engine, get_db
from app.main import app


@pytest.fixture
def api_client() -> Generator[TestClient]:
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )

    def override_get_db() -> Generator[Session]:
        yield session

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()
        session.close()
        transaction.rollback()
        connection.close()


def test_delivery_api_workflow(api_client: TestClient) -> None:
    project_response = api_client.post(
        "/api/v1/projects",
        json={
            "name": "devflow-api-test",
            "repository_url": "git@github.com:codespider17/devflow.git",
            "default_branch": "main",
        },
    )
    assert project_response.status_code == 201
    project = project_response.json()
    project_id = project["id"]

    list_response = api_client.get("/api/v1/projects")
    assert list_response.status_code == 200
    assert project_id in {item["id"] for item in list_response.json()}

    environment_response = api_client.post(
        f"/api/v1/projects/{project_id}/environments",
        json={"name": "test", "namespace": "devflow-apps"},
    )
    assert environment_response.status_code == 201
    environment = environment_response.json()

    run_response = api_client.post(
        "/api/v1/pipeline-runs",
        json={
            "project_id": project["id"],
            "environment_id": environment["id"],
            "commit_sha": "a" * 40,
        },
    )
    assert run_response.status_code == 201
    pipeline_run = run_response.json()
    pipeline_run_id = pipeline_run["id"]
    assert pipeline_run["status"] == "queued"

    detail_response = api_client.get(f"/api/v1/pipeline-runs/{pipeline_run_id}")
    assert detail_response.status_code == 200
    assert detail_response.json()["commit_sha"] == "a" * 40


def test_duplicate_project_returns_conflict(api_client: TestClient) -> None:
    payload = {
        "name": "duplicate-project",
        "repository_url": "https://github.com/codespider17/devflow.git",
    }

    assert api_client.post("/api/v1/projects", json=payload).status_code == 201
    response = api_client.post("/api/v1/projects", json=payload)

    assert response.status_code == 409
    assert response.json()["detail"] == "project name already exists"
