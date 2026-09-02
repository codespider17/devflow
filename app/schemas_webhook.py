from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel

DispatchStatus = Literal["triggered", "ignored", "failed"]


class GitHubWebhookReceipt(BaseModel):
    id: UUID
    delivery_id: str
    event_type: str
    status: Literal["accepted", "ignored", "duplicate"]
    accepted: bool
    received_at: datetime
    dispatch_status: DispatchStatus | None = None
    dispatch_reason: str | None = None
    pipeline_run_id: UUID | None = None
    jenkins_queue_url: str | None = None
