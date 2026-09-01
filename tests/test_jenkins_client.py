from urllib.error import URLError
from urllib.parse import parse_qs
from urllib.request import Request

import pytest

from app.clients.jenkins import (
    JenkinsClient,
    JenkinsClientError,
    JenkinsResponse,
)


def test_trigger_build_encodes_nested_job_and_parameters() -> None:
    captured: dict[str, object] = {}

    def transport(request: Request, timeout: float) -> JenkinsResponse:
        captured["request"] = request
        captured["timeout"] = timeout
        return JenkinsResponse(
            status_code=201,
            location="http://jenkins.example/queue/item/7/",
        )

    client = JenkinsClient(
        base_url="http://jenkins.example",
        username="devflow",
        api_token="test-token",
        job_name="platform/devflow",
        transport=transport,
    )
    location = client.trigger_build(
        {"PIPELINE_RUN_ID": "run-1", "GIT_COMMIT_SHA": "a" * 40}
    )

    request = captured["request"]
    assert isinstance(request, Request)
    assert request.full_url.endswith("/job/platform/job/devflow/buildWithParameters")
    assert request.get_method() == "POST"
    assert request.get_header("Authorization").startswith("Basic ")
    assert parse_qs(request.data.decode())["PIPELINE_RUN_ID"] == ["run-1"]
    assert captured["timeout"] == 10.0
    assert location == "http://jenkins.example/queue/item/7/"


def test_jenkins_url_must_not_contain_credentials() -> None:
    with pytest.raises(ValueError, match="must not contain credentials"):
        JenkinsClient(
            base_url="http://user:password@jenkins.example",
            username="devflow",
            api_token="test-token",
            job_name="devflow",
        )


def test_transport_error_does_not_expose_token() -> None:
    def failing_transport(request: Request, timeout: float) -> JenkinsResponse:
        raise URLError("connection refused")

    client = JenkinsClient(
        base_url="http://jenkins.example",
        username="devflow",
        api_token="super-secret-token",
        job_name="devflow",
        transport=failing_transport,
    )

    with pytest.raises(JenkinsClientError) as captured:
        client.trigger_build({"PIPELINE_RUN_ID": "run-1"})

    assert "super-secret-token" not in str(captured.value)


def test_unexpected_status_is_sanitized() -> None:
    def transport(request: Request, timeout: float) -> JenkinsResponse:
        return JenkinsResponse(status_code=403)

    client = JenkinsClient(
        base_url="http://jenkins.example",
        username="devflow",
        api_token="super-secret-token",
        job_name="devflow",
        transport=transport,
    )

    with pytest.raises(JenkinsClientError, match="HTTP 403") as captured:
        client.trigger_build({})

    assert "super-secret-token" not in str(captured.value)
