import json
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import engine, get_db
from app.main import app
from app.models import GitHubWebhookDelivery
from app.services.github_webhook import build_github_signature
from app.settings import get_settings

TEST_SECRET = "integration-test-webhook-secret"


@pytest.fixture
def webhook_client(
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[tuple[TestClient, Session]]:
    monkeypatch.setenv("DEVFLOW_GITHUB_WEBHOOK_SECRET", TEST_SECRET)
    get_settings.cache_clear()
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
            yield client, session
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
        "repository": {"full_name": "codespider17/devflow"},
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


def test_valid_push_is_accepted_and_persisted(webhook_client) -> None:
    client, session = webhook_client
    response = _request(client, "delivery-valid")

    assert response.status_code == 202
    assert response.json()["status"] == "accepted"
    delivery = session.scalar(
        select(GitHubWebhookDelivery).where(
            GitHubWebhookDelivery.delivery_id == "delivery-valid"
        )
    )
    assert delivery is not None
    assert delivery.repository_full_name == "codespider17/devflow"
    assert delivery.commit_sha == "a" * 40


def test_duplicate_delivery_is_idempotent(webhook_client) -> None:
    client, session = webhook_client
    assert _request(client, "delivery-duplicate").status_code == 202
    duplicate = _request(client, "delivery-duplicate")

    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "duplicate"
    count = session.scalar(
        select(func.count())
        .select_from(GitHubWebhookDelivery)
        .where(GitHubWebhookDelivery.delivery_id == "delivery-duplicate")
    )
    assert count == 1


def test_invalid_signature_is_rejected(webhook_client) -> None:
    client, session = webhook_client
    response = _request(
        client,
        "delivery-invalid",
        secret="wrong-secret",
    )

    assert response.status_code == 401
    count = session.scalar(select(func.count()).select_from(GitHubWebhookDelivery))
    assert count == 0


def test_unsupported_event_is_recorded_as_ignored(webhook_client) -> None:
    client, session = webhook_client
    response = _request(
        client,
        "delivery-ignored",
        event_type="issues",
    )

    assert response.status_code == 202
    assert response.json()["status"] == "ignored"
    delivery = session.scalar(
        select(GitHubWebhookDelivery).where(
            GitHubWebhookDelivery.delivery_id == "delivery-ignored"
        )
    )
    assert delivery is not None
    assert not delivery.accepted


def test_oversized_payload_is_rejected(webhook_client) -> None:
    client, _ = webhook_client
    body = b"x" * 1_048_577
    response = client.post(
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
