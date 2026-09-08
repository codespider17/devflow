from collections.abc import Generator
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import engine, get_db
from app.main import app
from app.models import AuditEvent, Deployment, Environment, PipelineRun, Project
from app.settings import get_settings


@pytest.fixture
def api_session() -> Generator[Session]:
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


@pytest.fixture
def api_client(api_session: Session) -> Generator[TestClient]:
    def override_get_db() -> Generator[Session]:
        yield api_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def authorization_headers() -> dict[str, str]:
    configured_token = get_settings().devflow_approval_api_token
    assert configured_token is not None
    token = configured_token.get_secret_value()
    assert token
    return {"Authorization": f"Bearer {token}"}


def create_pipeline_run(
    session: Session,
    *,
    status: str = "succeeded",
    with_image: bool = True,
) -> PipelineRun:
    suffix = uuid4().hex
    project = Project(
        name=f"deployment-api-{suffix}",
        repository_url="git@github.com:codespider17/devflow.git",
    )
    environment = Environment(
        name="production",
        namespace="devflow-system",
        project=project,
    )
    pipeline_run = PipelineRun(
        project=project,
        environment=environment,
        commit_sha="c" * 40,
        status=status,
        image_reference=(
            f"hb.reg.com/devflow/devflow-api:{'c' * 40}" if with_image else None
        ),
    )
    session.add(pipeline_run)
    session.commit()
    return pipeline_run


def deployment_payload(pipeline_run: PipelineRun) -> dict[str, str]:
    return {
        "pipeline_run_id": str(pipeline_run.id),
        "namespace": "devflow-system",
        "helm_release": "devflow",
        "requested_by": "platform-operator",
        "previous_image_reference": f"hb.reg.com/devflow/devflow-api:{'b' * 40}",
    }


def test_deployment_request_approval_and_audit_are_idempotent(
    api_client: TestClient,
    api_session: Session,
) -> None:
    pipeline_run = create_pipeline_run(api_session)
    headers = authorization_headers()
    payload = deployment_payload(pipeline_run)

    response = api_client.post("/api/v1/deployments", json=payload, headers=headers)
    assert response.status_code == 201
    deployment = response.json()
    deployment_id = deployment["id"]
    assert deployment["status"] == "awaiting_approval"
    assert deployment["image_reference"] == pipeline_run.image_reference

    duplicate = api_client.post(
        "/api/v1/deployments",
        json=payload,
        headers=headers,
    )
    assert duplicate.status_code == 201
    assert duplicate.json()["id"] == deployment_id
    deployment_count = api_session.scalar(
        select(func.count())
        .select_from(Deployment)
        .where(Deployment.pipeline_run_id == pipeline_run.id)
    )
    assert deployment_count == 1

    detail = api_client.get(
        f"/api/v1/deployments/{deployment_id}",
        headers=headers,
    )
    assert detail.status_code == 200

    decision_payload = {
        "decision": "approved",
        "actor": "platform-approver",
        "reason": "validated change window",
    }
    approved = api_client.post(
        f"/api/v1/deployments/{deployment_id}/decision",
        json=decision_payload,
        headers=headers,
    )
    assert approved.status_code == 200
    assert approved.json()["decision"] == "approved"
    assert approved.json()["decided_by"] == "platform-approver"

    repeated = api_client.post(
        f"/api/v1/deployments/{deployment_id}/decision",
        json=decision_payload,
        headers=headers,
    )
    assert repeated.status_code == 200
    assert repeated.json()["id"] == approved.json()["id"]

    audit_response = api_client.get(
        f"/api/v1/deployments/{deployment_id}/audit-events",
        headers=headers,
    )
    assert audit_response.status_code == 200
    events = audit_response.json()
    assert [event["event_type"] for event in events] == [
        "deployment.requested",
        "deployment.approved",
    ]
    assert all("token" not in str(event["details"]).lower() for event in events)
    audit_count = api_session.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(AuditEvent.deployment_id == UUID(deployment_id))
    )
    assert audit_count == 2


def test_approval_api_requires_bearer_token(
    api_client: TestClient,
    api_session: Session,
) -> None:
    pipeline_run = create_pipeline_run(api_session)
    response = api_client.post(
        "/api/v1/deployments",
        json=deployment_payload(pipeline_run),
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "invalid approval api token"


def test_unsuccessful_pipeline_run_cannot_request_deployment(
    api_client: TestClient,
    api_session: Session,
) -> None:
    pipeline_run = create_pipeline_run(api_session, status="failed")
    response = api_client.post(
        "/api/v1/deployments",
        json=deployment_payload(pipeline_run),
        headers=authorization_headers(),
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "pipeline run has not succeeded"


def test_final_approval_cannot_be_changed(
    api_client: TestClient,
    api_session: Session,
) -> None:
    pipeline_run = create_pipeline_run(api_session)
    headers = authorization_headers()
    deployment = api_client.post(
        "/api/v1/deployments",
        json=deployment_payload(pipeline_run),
        headers=headers,
    ).json()
    deployment_id = deployment["id"]
    approved = api_client.post(
        f"/api/v1/deployments/{deployment_id}/decision",
        json={"decision": "approved", "actor": "approver"},
        headers=headers,
    )
    assert approved.status_code == 200

    rejected = api_client.post(
        f"/api/v1/deployments/{deployment_id}/decision",
        json={"decision": "rejected", "actor": "other-approver"},
        headers=headers,
    )
    assert rejected.status_code == 409
    assert rejected.json()["detail"] == "approval decision is already final"
