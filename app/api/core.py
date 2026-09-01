from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Environment, PipelineRun, Project
from app.schemas import (
    EnvironmentCreate,
    EnvironmentRead,
    PipelineRunCreate,
    PipelineRunRead,
    ProjectCreate,
    ProjectRead,
)

router = APIRouter(prefix="/api/v1", tags=["delivery"])
DatabaseSession = Annotated[Session, Depends(get_db)]


@router.post(
    "/projects",
    response_model=ProjectRead,
    status_code=status.HTTP_201_CREATED,
)
def create_project(payload: ProjectCreate, db: DatabaseSession) -> Project:
    project = Project(**payload.model_dump())
    db.add(project)

    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="project name already exists",
        ) from error

    db.refresh(project)
    return project


@router.get("/projects", response_model=list[ProjectRead])
def list_projects(db: DatabaseSession) -> list[Project]:
    return list(db.scalars(select(Project).order_by(Project.name)))


@router.post(
    "/projects/{project_id}/environments",
    response_model=EnvironmentRead,
    status_code=status.HTTP_201_CREATED,
)
def create_environment(
    project_id: UUID,
    payload: EnvironmentCreate,
    db: DatabaseSession,
) -> Environment:
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="project not found",
        )

    environment = Environment(project_id=project.id, **payload.model_dump())
    db.add(environment)

    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="environment already exists for project",
        ) from error

    db.refresh(environment)
    return environment


@router.post(
    "/pipeline-runs",
    response_model=PipelineRunRead,
    status_code=status.HTTP_201_CREATED,
)
def create_pipeline_run(
    payload: PipelineRunCreate,
    db: DatabaseSession,
) -> PipelineRun:
    project = db.get(Project, payload.project_id)
    environment = db.get(Environment, payload.environment_id)

    if project is None or environment is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="project or environment not found",
        )

    if environment.project_id != project.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="environment does not belong to project",
        )

    pipeline_run = PipelineRun(
        **payload.model_dump(),
        status="queued",
    )
    db.add(pipeline_run)
    db.commit()
    db.refresh(pipeline_run)
    return pipeline_run


@router.get(
    "/pipeline-runs/{pipeline_run_id}",
    response_model=PipelineRunRead,
)
def get_pipeline_run(
    pipeline_run_id: UUID,
    db: DatabaseSession,
) -> PipelineRun:
    pipeline_run = db.get(PipelineRun, pipeline_run_id)
    if pipeline_run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="pipeline run not found",
        )

    return pipeline_run
