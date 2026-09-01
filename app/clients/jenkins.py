from __future__ import annotations

import base64
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen


class JenkinsClientError(RuntimeError):
    """Safe Jenkins client error without credential values."""


@dataclass(frozen=True)
class JenkinsResponse:
    status_code: int
    location: str | None = None


Transport = Callable[[Request, float], JenkinsResponse]


def urllib_transport(request: Request, timeout: float) -> JenkinsResponse:
    with urlopen(request, timeout=timeout) as response:
        return JenkinsResponse(
            status_code=response.status,
            location=response.headers.get("Location"),
        )


def _job_path(job_name: str) -> str:
    parts = [part for part in job_name.split("/") if part]
    if not parts:
        raise ValueError("jenkins job name must not be empty")
    return "".join(f"/job/{quote(part)}" for part in parts)


class JenkinsClient:
    def __init__(
        self,
        *,
        base_url: str,
        username: str,
        api_token: str,
        job_name: str,
        timeout_seconds: float = 10.0,
        transport: Transport = urllib_transport,
    ) -> None:
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("jenkins URL must use http or https")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("jenkins URL must not contain credentials")
        if not username or not api_token:
            raise ValueError("jenkins username and API token are required")

        self.base_url = base_url.rstrip("/")
        self.username = username
        self.api_token = api_token
        self.job_name = job_name
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def trigger_build(self, parameters: Mapping[str, str]) -> str | None:
        credentials = base64.b64encode(
            f"{self.username}:{self.api_token}".encode()
        ).decode("ascii")
        request = Request(
            f"{self.base_url}{_job_path(self.job_name)}/buildWithParameters",
            data=urlencode(dict(parameters)).encode(),
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="POST",
        )

        try:
            response = self.transport(request, self.timeout_seconds)
        except (HTTPError, URLError, TimeoutError) as error:
            raise JenkinsClientError("jenkins build trigger request failed") from error

        if response.status_code not in {200, 201, 202}:
            raise JenkinsClientError(
                f"jenkins returned unexpected HTTP {response.status_code}"
            )
        return response.location
