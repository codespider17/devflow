from collections.abc import Awaitable, Callable
from time import perf_counter

from fastapi import Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Deployment, GitHubWebhookDelivery, PipelineRun

HTTP_REQUESTS = Counter(
    "devflow_http_requests_total",
    "Total DevFlow HTTP requests",
    ["method", "path", "status"],
)
HTTP_DURATION = Histogram(
    "devflow_http_request_duration_seconds",
    "DevFlow HTTP request duration in seconds",
    ["method", "path"],
)
PIPELINE_RUN_RECORDS = Gauge(
    "devflow_pipeline_run_records",
    "Persisted pipeline run records by status",
    ["status"],
)
DEPLOYMENT_RECORDS = Gauge(
    "devflow_deployment_records",
    "Persisted deployment records by status",
    ["status"],
)
WEBHOOK_DELIVERY_RECORDS = Gauge(
    "devflow_webhook_delivery_records",
    "Persisted GitHub webhook delivery records by acceptance",
    ["accepted"],
)

PIPELINE_STATUSES = ("queued", "running", "succeeded", "failed", "cancelled")
DEPLOYMENT_STATUSES = (
    "pending",
    "awaiting_approval",
    "approved",
    "rejected",
    "deploying",
    "succeeded",
    "failed",
    "rolled_back",
)


async def observe_http_request(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    started = perf_counter()
    status = "500"
    try:
        response = await call_next(request)
        status = str(response.status_code)
        return response
    finally:
        route = request.scope.get("route")
        path = getattr(route, "path", "unmatched")
        HTTP_REQUESTS.labels(
            method=request.method,
            path=path,
            status=status,
        ).inc()
        HTTP_DURATION.labels(method=request.method, path=path).observe(
            perf_counter() - started
        )


def _refresh_business_metrics(db: Session) -> None:
    for status in PIPELINE_STATUSES:
        PIPELINE_RUN_RECORDS.labels(status=status).set(0)
    for status, count in db.execute(
        select(PipelineRun.status, func.count()).group_by(PipelineRun.status)
    ):
        PIPELINE_RUN_RECORDS.labels(status=status).set(count)

    for status in DEPLOYMENT_STATUSES:
        DEPLOYMENT_RECORDS.labels(status=status).set(0)
    for status, count in db.execute(
        select(Deployment.status, func.count()).group_by(Deployment.status)
    ):
        DEPLOYMENT_RECORDS.labels(status=status).set(count)

    for accepted in (True, False):
        WEBHOOK_DELIVERY_RECORDS.labels(accepted=str(accepted).lower()).set(0)
    for accepted, count in db.execute(
        select(GitHubWebhookDelivery.accepted, func.count()).group_by(
            GitHubWebhookDelivery.accepted
        )
    ):
        WEBHOOK_DELIVERY_RECORDS.labels(accepted=str(accepted).lower()).set(count)


def render_metrics(db: Session) -> Response:
    _refresh_business_metrics(db)
    return Response(
        content=generate_latest(),
        headers={"Content-Type": CONTENT_TYPE_LATEST},
    )
