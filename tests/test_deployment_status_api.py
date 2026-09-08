from collections.abc import Generator
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import engine, get_db
from app.main import app
from app.models import AuditEvent, Environment, PipelineRun, Project
from app.settings import get_settings


@pytest.fixture
def status_session() -> Generator[Session]:
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
def status_client(status_session: Session) -> Generator[TestClient]:
    def override_get_db() -> Generator[Session]:
        yield status_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def token_headers(setting_name: str) -> dict[str, str]:
    configured_token = getattr(get_settings(), setting_name)
    assert configured_token is not None
    token = configured_token.get_secret_value()
    assert token
    return {"Authorization": f"Bearer {token}"}


def create_approved_deployment(
    client: TestClient,
    session: Session,
) -> str:
    suffix = uuid4().hex
    project = Project(
        name=f"deployment-status-{suffix}",
        repository_url=f"https://github.com/codespider17/{suffix}.git",
        default_branch="main",
    )
    environment = Environment(
        project=project,
        name="development",
        namespace="devflow-system",
    )
    pipeline_run = PipelineRun(
        project=project,
        environment=environment,
        commit_sha="d" * 40,
        status="succeeded",
        image_reference=f"hb.reg.com/devflow/devflow-api:{'d' * 40}",
    )
    session.add(pipeline_run)
    session.commit()

    approval_headers = token_headers("devflow_approval_api_token")
    request_response = client.post(
        "/api/v1/deployments",
        headers=approval_headers,
        json={
            "pipeline_run_id": str(pipeline_run.id),
            "namespace": "devflow-system",
            "helm_release": "devflow",
            "requested_by": "platform-operator",
            "previous_image_reference": (f"hb.reg.com/devflow/devflow-api:{'c' * 40}"),
        },
    )
    assert request_response.status_code == 201
    deployment_id = request_response.json()["id"]

    approval_response = client.post(
        f"/api/v1/deployments/{deployment_id}/decision",
        headers=approval_headers,
        json={
            "decision": "approved",
            "actor": "platform-approver",
            "reason": "approved for deployment execution",
        },
    )
    assert approval_response.status_code == 200
    return deployment_id


def write_status(
    client: TestClient,
    deployment_id: str,
    status_value: str,
    *,
    reason: str | None = None,
):
    payload = {
        "status": status_value,
        "actor": "jenkins-deployer",
    }
    if reason is not None:
        payload["reason"] = reason
    return client.post(
        f"/api/v1/deployments/{deployment_id}/status",
        headers=token_headers("devflow_deployment_callback_token"),
        json=payload,
    )


def test_approved_deployment_reaches_succeeded_with_ordered_audit(
    status_client: TestClient,
    status_session: Session,
) -> None:
    deployment_id = create_approved_deployment(status_client, status_session)

    deploying = write_status(status_client, deployment_id, "deploying")
    assert deploying.status_code == 200
    assert deploying.json()["status"] == "deploying"
    assert deploying.json()["deployed_at"] is not None
    assert deploying.json()["finished_at"] is None

    repeated = write_status(status_client, deployment_id, "deploying")
    assert repeated.status_code == 200

    succeeded = write_status(status_client, deployment_id, "succeeded")
    assert succeeded.status_code == 200
    assert succeeded.json()["status"] == "succeeded"
    assert succeeded.json()["finished_at"] is not None

    audit_response = status_client.get(
        f"/api/v1/deployments/{deployment_id}/audit-events",
        headers=token_headers("devflow_approval_api_token"),
    )
    assert audit_response.status_code == 200
    assert [event["event_type"] for event in audit_response.json()] == [
        "deployment.requested",
        "deployment.approved",
        "deployment.deploying",
        "deployment.succeeded",
    ]

    deploying_count = status_session.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(
            AuditEvent.deployment_id == UUID(deployment_id),
            AuditEvent.event_type == "deployment.deploying",
        )
    )
    assert deploying_count == 1


def test_deploying_deployment_can_reach_failed(
    status_client: TestClient,
    status_session: Session,
) -> None:
    deployment_id = create_approved_deployment(status_client, status_session)
    assert write_status(status_client, deployment_id, "deploying").status_code == 200

    failed = write_status(
        status_client,
        deployment_id,
        "failed",
        reason="rollout health check failed",
    )
    assert failed.status_code == 200
    assert failed.json()["status"] == "failed"
    assert failed.json()["finished_at"] is not None


def test_deployment_status_callback_requires_token(
    status_client: TestClient,
    status_session: Session,
) -> None:
    deployment_id = create_approved_deployment(status_client, status_session)
    path = f"/api/v1/deployments/{deployment_id}/status"
    payload = {"status": "deploying", "actor": "jenkins-deployer"}

    assert status_client.post(path, json=payload).status_code == 401
    assert (
        status_client.post(
            path,
            json=payload,
            headers={"Authorization": "Bearer wrong-token"},
        ).status_code
        == 401
    )


def test_invalid_and_terminal_transitions_are_rejected(
    status_client: TestClient,
    status_session: Session,
) -> None:
    deployment_id = create_approved_deployment(status_client, status_session)

    direct_success = write_status(status_client, deployment_id, "succeeded")
    assert direct_success.status_code == 409

    assert write_status(status_client, deployment_id, "deploying").status_code == 200
    assert write_status(status_client, deployment_id, "succeeded").status_code == 200
    terminal_change = write_status(status_client, deployment_id, "failed")
    assert terminal_change.status_code == 409


def test_unknown_deployment_returns_not_found(
    status_client: TestClient,
) -> None:
    response = write_status(
        status_client,
        str(uuid4()),
        "deploying",
    )
    assert response.status_code == 404


def test_failed_deployment_can_reach_rolled_back_with_audit(
    status_client: TestClient,
    status_session: Session,
) -> None:
    deployment_id = create_approved_deployment(status_client, status_session)
    assert write_status(status_client, deployment_id, "deploying").status_code == 200
    assert (
        write_status(
            status_client,
            deployment_id,
            "failed",
            reason="rollout health check failed",
        ).status_code
        == 200
    )

    rolled_back = write_status(
        status_client,
        deployment_id,
        "rolled_back",
        reason="automatic helm rollback verified",
    )
    assert rolled_back.status_code == 200
    assert rolled_back.json()["status"] == "rolled_back"
    assert rolled_back.json()["finished_at"] is not None

    audit_response = status_client.get(
        f"/api/v1/deployments/{deployment_id}/audit-events",
        headers=token_headers("devflow_approval_api_token"),
    )
    assert audit_response.status_code == 200
    assert [event["event_type"] for event in audit_response.json()] == [
        "deployment.requested",
        "deployment.approved",
        "deployment.deploying",
        "deployment.failed",
        "deployment.rolled_back",
    ]


def test_rolled_back_requires_failed_state(
    status_client: TestClient,
    status_session: Session,
) -> None:
    deployment_id = create_approved_deployment(status_client, status_session)
    assert write_status(status_client, deployment_id, "deploying").status_code == 200
    response = write_status(status_client, deployment_id, "rolled_back")
    assert response.status_code == 409
