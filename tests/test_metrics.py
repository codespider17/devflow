from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_metrics_endpoint_exposes_runtime_and_business_metrics() -> None:
    assert client.get("/healthz").status_code == 200

    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    body = response.text
    assert "devflow_http_requests_total" in body
    assert "devflow_http_request_duration_seconds_bucket" in body
    assert "devflow_pipeline_run_records" in body
    assert "devflow_deployment_records" in body
    assert "devflow_webhook_delivery_records" in body
    assert "devflow_http_requests_total{" in body
    assert "/healthz" in body


def test_metrics_endpoint_is_not_in_public_openapi_schema() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/metrics" not in response.json()["paths"]
