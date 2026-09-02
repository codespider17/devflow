from typing import Annotated, Literal

from fastapi import Depends, FastAPI
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.api.core import router as core_router
from app.api.pipeline_callbacks import router as pipeline_callbacks_router
from app.api.webhooks import router as webhooks_router
from app.database import get_db


class StatusResponse(BaseModel):
    status: Literal["ok", "ready"]
    service: str
    version: str


class ServiceInfo(BaseModel):
    name: str
    version: str
    environment: str


app = FastAPI(
    title="DevFlow API",
    description="Cloud-native delivery and engineering efficiency platform",
    version="0.1.0",
)

app.include_router(core_router)
app.include_router(webhooks_router)
app.include_router(pipeline_callbacks_router)

DatabaseSession = Annotated[Session, Depends(get_db)]


@app.get("/healthz", response_model=StatusResponse, tags=["system"])
def healthz() -> StatusResponse:
    return StatusResponse(
        status="ok",
        service="devflow-api",
        version=app.version,
    )


@app.get("/readyz", response_model=StatusResponse, tags=["system"])
def readyz(db: DatabaseSession) -> StatusResponse:
    db.execute(text("SELECT 1"))
    return StatusResponse(
        status="ready",
        service="devflow-api",
        version=app.version,
    )


@app.get("/api/v1/info", response_model=ServiceInfo, tags=["system"])
def service_info() -> ServiceInfo:
    return ServiceInfo(
        name="DevFlow",
        version=app.version,
        environment="development",
    )
