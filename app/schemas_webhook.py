from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


class GitHubWebhookReceipt(BaseModel):
    id: UUID
    delivery_id: str
    event_type: str
    status: Literal["accepted", "ignored", "duplicate"]
    accepted: bool
    received_at: datetime
