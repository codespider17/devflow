from collections.abc import Generator
from uuid import uuid4

import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.orm import Session

from app.database import engine
from app.models import (
    Approval,
    AuditEvent,
    Deployment,
    Environment,
    PipelineRun,
    Project,
)


@pytest.fixture
def delivery_session() -> Generator[Session]:
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


def test_migrated_schema_contains_delivery_control_tables() -> None:
    schema = inspect(engine)
    tables = set(schema.get_table_names())

    assert {"deployments", "approvals", "audit_events"} <= tables
    assert {
        "pipeline_run_id",
        "environment_id",
        "image_reference",
        "previous_image_reference",
        "helm_release",
        "namespace",
        "status",
        "requested_by",
        "deployed_at",
        "finished_at",
    } <= {column["name"] for column in schema.get_columns("deployments")}
    assert {
        "deployment_id",
        "decision",
        "requested_by",
        "decided_by",
        "reason",
        "decided_at",
    } <= {column["name"] for column in schema.get_columns("approvals")}
    assert {
        "deployment_id",
        "pipeline_run_id",
        "event_type",
        "actor",
        "details",
        "occurred_at",
    } <= {column["name"] for column in schema.get_columns("audit_events")}


def test_deployment_approval_and_audit_transaction(
    delivery_session: Session,
) -> None:
    suffix = uuid4().hex
    project = Project(
        name=f"delivery-model-{suffix}",
        repository_url="git@github.com:codespider17/devflow.git",
    )
    environment = Environment(
        name="production",
        namespace="devflow-apps",
        project=project,
    )
    pipeline_run = PipelineRun(
        project=project,
        environment=environment,
        commit_sha="b" * 40,
        status="succeeded",
        image_reference=f"hb.reg.com/devflow/devflow-api:{'b' * 40}",
    )
    deployment = Deployment(
        pipeline_run=pipeline_run,
        environment=environment,
        image_reference=pipeline_run.image_reference,
        previous_image_reference=f"hb.reg.com/devflow/devflow-api:{'a' * 40}",
        helm_release="devflow",
        namespace="devflow-system",
        status="awaiting_approval",
        requested_by="github-webhook",
    )
    approval = Approval(
        deployment=deployment,
        decision="pending",
        requested_by="github-webhook",
    )
    requested_event = AuditEvent(
        deployment=deployment,
        pipeline_run=pipeline_run,
        event_type="deployment.requested",
        actor="github-webhook",
        details={
            "image_reference": deployment.image_reference,
            "environment": environment.name,
        },
    )
    delivery_session.add_all([approval, requested_event])
    delivery_session.flush()

    stored = delivery_session.scalar(
        select(Deployment).where(Deployment.id == deployment.id)
    )
    assert stored is not None
    assert stored.pipeline_run_id == pipeline_run.id
    assert stored.environment_id == environment.id
    assert stored.approval is not None
    assert stored.approval.decision == "pending"
    assert stored.audit_events[0].event_type == "deployment.requested"
    assert stored.audit_events[0].details["environment"] == "production"

    approval.decision = "approved"
    approval.decided_by = "platform-operator"
    deployment.status = "approved"
    delivery_session.add(
        AuditEvent(
            deployment=deployment,
            pipeline_run=pipeline_run,
            event_type="deployment.approved",
            actor="platform-operator",
            details={"decision": "approved"},
        )
    )
    delivery_session.flush()

    event_count = delivery_session.scalar(
        select(func.count())
        .select_from(AuditEvent)
        .where(AuditEvent.deployment_id == deployment.id)
    )
    assert event_count == 2
    assert approval.decision == "approved"
    assert deployment.status == "approved"
