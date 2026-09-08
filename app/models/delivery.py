from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.core import Environment, PipelineRun, TimestampMixin


class Deployment(TimestampMixin, Base):
    __tablename__ = "deployments"
    __table_args__ = (
        CheckConstraint(
            "status IN ("
            "'pending', 'awaiting_approval', 'approved', 'rejected', "
            "'deploying', 'succeeded', 'failed', 'rolled_back'"
            ")",
            name="ck_deployments_status",
        ),
        Index("ix_deployments_environment_created", "environment_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    pipeline_run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )
    environment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("environments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    image_reference: Mapped[str] = mapped_column(String(500), nullable=False)
    previous_image_reference: Mapped[str | None] = mapped_column(String(500))
    helm_release: Mapped[str] = mapped_column(
        String(100),
        default="devflow",
        server_default="devflow",
        nullable=False,
    )
    namespace: Mapped[str] = mapped_column(String(63), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30),
        default="pending",
        server_default="pending",
        nullable=False,
    )
    requested_by: Mapped[str] = mapped_column(
        String(100),
        default="devflow",
        server_default="devflow",
        nullable=False,
    )
    deployed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    pipeline_run: Mapped[PipelineRun] = relationship()
    environment: Mapped[Environment] = relationship()
    approval: Mapped[Approval | None] = relationship(
        back_populates="deployment",
        cascade="all, delete-orphan",
        uselist=False,
    )
    audit_events: Mapped[list[AuditEvent]] = relationship(
        back_populates="deployment",
        cascade="all, delete-orphan",
    )


class Approval(TimestampMixin, Base):
    __tablename__ = "approvals"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('pending', 'approved', 'rejected')",
            name="ck_approvals_decision",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    deployment_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("deployments.id", ondelete="CASCADE"),
        unique=True,
        nullable=False,
    )
    decision: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        server_default="pending",
        nullable=False,
    )
    requested_by: Mapped[str] = mapped_column(String(100), nullable=False)
    decided_by: Mapped[str | None] = mapped_column(String(100))
    reason: Mapped[str | None] = mapped_column(String(500))
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    deployment: Mapped[Deployment] = relationship(back_populates="approval")


class AuditEvent(Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_occurred_at", "occurred_at"),
        Index("ix_audit_events_deployment_occurred", "deployment_id", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        primary_key=True,
        default=uuid.uuid4,
    )
    deployment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("deployments.id", ondelete="CASCADE")
    )
    pipeline_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    actor: Mapped[str] = mapped_column(
        String(100),
        default="system",
        server_default="system",
        nullable=False,
    )
    details: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        default=dict,
        server_default=text("'{}'::jsonb"),
        nullable=False,
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    deployment: Mapped[Deployment | None] = relationship(back_populates="audit_events")
    pipeline_run: Mapped[PipelineRun | None] = relationship()
