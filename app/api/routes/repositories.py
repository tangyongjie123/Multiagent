"""Git 仓库和分析启动接口。"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    AnalysisCreate,
    AnalysisResponse,
    RepositoryCreate,
    RepositoryResponse,
    RepositorySubmission,
)
from app.db.models import AnalysisRecord, RepositoryRecord
from app.db.session import get_session
from app.domain.models import AgentRole, AnalysisStatus
from app.services.analysis_events import append_analysis_event
from app.services.repository import (
    RepositoryError,
    repository_name,
    validate_repository_url,
)

router = APIRouter(prefix="/api/v1/repositories", tags=["repositories"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def _create_analysis(
    session: AsyncSession,
    repository: RepositoryRecord,
    branch: str | None,
) -> AnalysisRecord:
    """创建一个待执行分析并写入初始事件。"""

    analysis = AnalysisRecord(
        repository_id=repository.id,
        status=AnalysisStatus.PENDING.value,
        branch=branch or repository.branch,
    )
    session.add(analysis)
    await session.flush()
    await append_analysis_event(
        session,
        analysis.id,
        "analysis.created",
        AgentRole.MAIN,
        "仓库分析任务已创建",
        {"repository_url": repository.url, "branch": analysis.branch},
    )
    return analysis


@router.post("", response_model=RepositorySubmission, status_code=status.HTTP_202_ACCEPTED)
async def submit_repository(
    payload: RepositoryCreate,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> RepositorySubmission:
    """添加公开 Git 仓库并立即开始分析。"""

    try:
        url, provider = validate_repository_url(payload.url)
    except RepositoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    repository = RepositoryRecord(
        url=url,
        name=repository_name(url),
        branch=payload.branch,
        provider=provider,
    )
    session.add(repository)
    await session.flush()
    analysis = await _create_analysis(session, repository, payload.branch)
    await session.commit()
    await session.refresh(repository)
    await session.refresh(analysis)

    from app.services.analysis_runner import run_analysis

    background_tasks.add_task(run_analysis, analysis.id)
    return RepositorySubmission(
        repository=RepositoryResponse.model_validate(repository),
        analysis=AnalysisResponse.model_validate(analysis),
    )


@router.get("", response_model=list[RepositoryResponse])
async def list_repositories(session: SessionDep) -> list[RepositoryResponse]:
    """按创建时间倒序返回仓库列表。"""

    repositories = await session.scalars(
        select(RepositoryRecord).order_by(RepositoryRecord.created_at.desc())
    )
    return [
        RepositoryResponse.model_validate(repository)
        for repository in repositories.all()
    ]


@router.get("/{repository_id}", response_model=RepositoryResponse)
async def get_repository(
    repository_id: UUID,
    session: SessionDep,
) -> RepositoryResponse:
    """返回单个仓库元数据。"""

    repository = await session.get(RepositoryRecord, repository_id)
    if repository is None:
        raise HTTPException(status_code=404, detail="仓库不存在")
    return RepositoryResponse.model_validate(repository)


@router.get(
    "/{repository_id}/analyses",
    response_model=list[AnalysisResponse],
)
async def list_repository_analyses(
    repository_id: UUID,
    session: SessionDep,
) -> list[AnalysisResponse]:
    """返回指定仓库的分析历史。"""

    repository = await session.get(RepositoryRecord, repository_id)
    if repository is None:
        raise HTTPException(status_code=404, detail="仓库不存在")
    analyses = await session.scalars(
        select(AnalysisRecord)
        .where(AnalysisRecord.repository_id == repository_id)
        .order_by(AnalysisRecord.created_at.desc())
    )
    return [
        AnalysisResponse.model_validate(analysis) for analysis in analyses.all()
    ]


@router.post(
    "/{repository_id}/analyses",
    response_model=AnalysisResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_repository_analysis(
    repository_id: UUID,
    payload: AnalysisCreate,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> AnalysisResponse:
    """对已有仓库发起一次新分析。"""

    repository = await session.get(RepositoryRecord, repository_id)
    if repository is None:
        raise HTTPException(status_code=404, detail="仓库不存在")
    analysis = await _create_analysis(session, repository, payload.branch)
    await session.commit()
    await session.refresh(analysis)

    from app.services.analysis_runner import run_analysis

    background_tasks.add_task(run_analysis, analysis.id)
    return AnalysisResponse.model_validate(analysis)
