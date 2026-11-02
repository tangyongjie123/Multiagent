"""项目创建与查询接口。"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import ProjectCreate, ProjectResponse
from app.db.models import ProjectRecord
from app.db.session import get_session

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    session: SessionDep,
) -> ProjectResponse:
    """创建项目并保存用户需求。"""

    project = ProjectRecord(
        name=payload.name.strip(),
        requirement=payload.requirement.strip(),
    )
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return ProjectResponse.model_validate(project)


@router.get("", response_model=list[ProjectResponse])
async def list_projects(
    session: SessionDep,
) -> list[ProjectResponse]:
    """按创建时间倒序返回项目。"""

    result = await session.scalars(
        select(ProjectRecord).order_by(ProjectRecord.created_at.desc())
    )
    return [ProjectResponse.model_validate(project) for project in result.all()]


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: UUID,
    session: SessionDep,
) -> ProjectResponse:
    """获取项目详情。"""

    project = await session.get(ProjectRecord, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    return ProjectResponse.model_validate(project)
