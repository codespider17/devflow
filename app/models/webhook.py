from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class GitHubWebhookDelivery(Base):
    __tablename__ = "github_webhook_deliveries"
    __table_args__ = (
        Index(
            "ix_github_webhook_deliveries_received_at",
            "received_at",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    delivery_id: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    repository_full_name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
    )
    git_ref: Mapped[str | None] = mapped_column(String(500))
    commit_sha: Mapped[str | None] = mapped_column(String(40))
    accepted: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
