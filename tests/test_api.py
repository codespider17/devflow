from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_healthz() -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "devflow-api",
        "version": "0.1.0",
    }


def test_readyz() -> None:
    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"


def test_service_info() -> None:
    response = client.get("/api/v1/info")

    assert response.status_code == 200
    assert response.json() == {
        "name": "DevFlow",
        "version": "0.1.0",
        "environment": "development",
    }


def test_openapi_contains_system_routes() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert {"/healthz", "/readyz", "/api/v1/info"} <= set(response.json()["paths"])
