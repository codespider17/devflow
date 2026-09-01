from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from app.database import engine
from app.models import Environment, PipelineRun, Project
from app.settings import get_settings


def test_database_url_uses_postgresql_psycopg() -> None:
    settings = get_settings()

    assert settings.database_url.startswith("postgresql+psycopg://")
    assert settings.devflow_postgres_password.get_secret_value() not in str(
        settings.devflow_postgres_password
    )


def test_migrated_schema_contains_core_tables() -> None:
    schema = inspect(engine)
    tables = set(schema.get_table_names())

    assert {"alembic_version", "projects", "environments", "pipeline_runs"} <= tables
    assert {"name", "repository_url", "default_branch"} <= {
        column["name"] for column in schema.get_columns("projects")
    }


def test_project_environment_and_pipeline_run_transaction() -> None:
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, expire_on_commit=False)

    try:
        project = Project(
            name="devflow-integration-test",
            repository_url="git@github.com:codespider17/devflow.git",
        )
        environment = Environment(
            name="test",
            namespace="devflow-apps",
            project=project,
        )
        pipeline_run = PipelineRun(
            project=project,
            environment=environment,
            commit_sha="0" * 40,
            status="queued",
        )

        session.add(pipeline_run)
        session.flush()

        stored = session.scalar(
            select(PipelineRun).where(PipelineRun.id == pipeline_run.id)
        )

        assert stored is not None
        assert stored.project.name == "devflow-integration-test"
        assert stored.environment.namespace == "devflow-apps"
        assert stored.status == "queued"
    finally:
        session.close()
        transaction.rollback()
        connection.close()
