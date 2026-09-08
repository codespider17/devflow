from typing import Literal

from pydantic import BaseModel, Field


class DeploymentStatusUpdate(BaseModel):
    status: Literal["deploying", "succeeded", "failed"]
    actor: str = Field(min_length=1, max_length=100)
    reason: str | None = Field(default=None, max_length=500)
