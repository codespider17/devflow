from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    repository_url: str = Field(min_length=1, max_length=500)
    default_branch: str = Field(default="main", min_length=1, max_length=100)


class ProjectRead(ProjectCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class EnvironmentCreate(BaseModel):
    name: str = Field(min_length=1, max_length=50)
    namespace: str = Field(
        min_length=1,
        max_length=63,
        pattern=r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$",
    )


class EnvironmentRead(EnvironmentCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    created_at: datetime
    updated_at: datetime


class PipelineRunCreate(BaseModel):
    project_id: UUID
    environment_id: UUID
    commit_sha: str = Field(pattern=r"^[0-9a-fA-F]{40}$")


class PipelineRunRead(PipelineRunCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    trigger_source: Literal["manual", "github"]
    jenkins_queue_url: str | None
    trigger_error: str | None
    image_reference: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class PipelineRunStatusUpdate(BaseModel):
    status: Literal["running", "succeeded", "failed", "cancelled"]
    image_reference: str | None = Field(default=None, max_length=500)
