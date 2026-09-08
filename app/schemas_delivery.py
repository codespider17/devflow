from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

DeploymentStatus = Literal[
    "pending",
    "awaiting_approval",
    "approved",
    "rejected",
    "deploying",
    "succeeded",
    "failed",
    "rolled_back",
]
ApprovalDecisionValue = Literal["pending", "approved", "rejected"]


class DeploymentRequest(BaseModel):
    pipeline_run_id: UUID
    namespace: str = Field(
        min_length=1,
        max_length=63,
        pattern=r"^[a-z0-9]([-a-z0-9]*[a-z0-9])?$",
    )
    helm_release: str = Field(default="devflow", min_length=1, max_length=100)
    requested_by: str = Field(min_length=1, max_length=100)
    previous_image_reference: str | None = Field(default=None, max_length=500)


class DeploymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    pipeline_run_id: UUID
    environment_id: UUID
    image_reference: str
    previous_image_reference: str | None
    helm_release: str
    namespace: str
    status: DeploymentStatus
    requested_by: str
    deployed_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ApprovalDecision(BaseModel):
    decision: Literal["approved", "rejected"]
    actor: str = Field(min_length=1, max_length=100)
    reason: str | None = Field(default=None, max_length=500)


class ApprovalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    deployment_id: UUID
    decision: ApprovalDecisionValue
    requested_by: str
    decided_by: str | None
    reason: str | None
    decided_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    deployment_id: UUID | None
    pipeline_run_id: UUID | None
    event_type: str
    actor: str
    details: dict[str, Any]
    occurred_at: datetime
