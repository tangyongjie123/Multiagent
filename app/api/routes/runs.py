"""Agent 运行、事件和产物接口。"""

from __future__ import annotations

import asyncio
import io
import json
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import PlainTextResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.api.schemas import (
    ArtifactResponse,
    DiffResponse,
    EventResponse,
    FileEntry,
    FileListResponse,
    RunCreate,
    RunResponse,
)
from app.core.config import get_settings
from app.db.models import AgentEventRecord, ArtifactRecord, ProjectRecord, RunRecord
from app.db.session import get_session, get_session_factory
from app.domain.models import AgentRole, RunStatus
from app.services.artifacts import (
    ArtifactPathError,
    build_workspace_diff,
    build_workspace_zip,
    list_workspace_files,
    resolve_workspace_file,
    run_workspace,
)
from app.services.run_events import append_event
from app.services.run_executor import cancel_run as cancel_run_task

router = APIRouter(prefix="/api/v1", tags=["runs"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


@router.post(
    "/projects/{project_id}/runs",
    response_model=RunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_run(
    project_id: UUID,
    payload: RunCreate,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> RunResponse:
    """创建运行并在响应后启动主 Agent 工作流。"""

    project = await session.get(ProjectRecord, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")

    settings = get_settings()
    run = RunRecord(
        project_id=project_id,
        status=RunStatus.PENDING.value,
        is_simulated=settings.agent_execution_mode == "simulation",
        token_budget=settings.run_token_budget,
    )
    session.add(run)
    await session.flush()
    await append_event(
        session,
        run.id,
        event_type="run.created",
        agent=AgentRole.MAIN,
        message="运行已创建，等待主 Agent 调度",
        data={
            "additional_context": payload.additional_context,
            "execution_mode": settings.agent_execution_mode,
        },
    )
    await session.commit()
    await session.refresh(run)

    from app.services.run_executor import execute_run

    background_tasks.add_task(execute_run, run.id)
    return RunResponse.model_validate(run)


@router.get("/runs/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: UUID,
    session: SessionDep,
) -> RunResponse:
    """查询运行状态。"""

    run = await session.get(RunRecord, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="运行不存在")
    return RunResponse.model_validate(run)


@router.post("/runs/{run_id}/cancel", response_model=RunResponse)
async def cancel_run(
    run_id: UUID,
    session: SessionDep,
) -> RunResponse:
    """取消运行中的 Agent 任务。"""

    run = await session.get(RunRecord, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="运行不存在")
    if run.status in {
        RunStatus.COMPLETED.value,
        RunStatus.FAILED.value,
        RunStatus.CANCELLED.value,
    }:
        raise HTTPException(status_code=409, detail="运行已经结束")
    await cancel_run_task(run_id)
    await session.refresh(run)
    return RunResponse.model_validate(run)


@router.get(
    "/projects/{project_id}/runs",
    response_model=list[RunResponse],
)
async def list_project_runs(
    project_id: UUID,
    session: SessionDep,
) -> list[RunResponse]:
    """返回项目的运行历史。"""

    project = await session.get(ProjectRecord, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    runs = await session.scalars(
        select(RunRecord)
        .where(RunRecord.project_id == project_id)
        .order_by(RunRecord.created_at.desc())
    )
    return [RunResponse.model_validate(run) for run in runs.all()]


@router.get("/runs/{run_id}/events", response_model=list[EventResponse])
async def list_events(
    run_id: UUID,
    session: SessionDep,
) -> list[EventResponse]:
    """按顺序返回持久化事件。"""

    events = await session.scalars(
        select(AgentEventRecord)
        .where(AgentEventRecord.run_id == run_id)
        .order_by(AgentEventRecord.sequence)
    )
    return [EventResponse.model_validate(event) for event in events.all()]


@router.get("/runs/{run_id}/events/stream")
async def stream_events(run_id: UUID, request: Request) -> EventSourceResponse:
    """通过 SSE 推送新增事件。"""

    session_factory = get_session_factory()

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        last_sequence = 0
        terminal_statuses = {
            RunStatus.COMPLETED.value,
            RunStatus.FAILED.value,
            RunStatus.CANCELLED.value,
        }
        while not await request.is_disconnected():
            async with session_factory() as session:
                run = await session.get(RunRecord, run_id)
                if run is None:
                    yield {
                        "event": "error",
                        "data": json.dumps(
                            {"detail": "运行不存在"}, ensure_ascii=False
                        ),
                    }
                    return
                events = await session.scalars(
                    select(AgentEventRecord)
                    .where(
                        AgentEventRecord.run_id == run_id,
                        AgentEventRecord.sequence > last_sequence,
                    )
                    .order_by(AgentEventRecord.sequence)
                )
                for event in events.all():
                    last_sequence = event.sequence
                    payload = EventResponse.model_validate(event).model_dump(mode="json")
                    yield {
                        "id": str(event.sequence),
                        "event": event.event_type,
                        "data": json.dumps(payload, ensure_ascii=False),
                    }
                if run.status in terminal_statuses:
                    return
            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())


@router.get("/runs/{run_id}/artifacts", response_model=list[ArtifactResponse])
async def list_artifacts(
    run_id: UUID,
    session: SessionDep,
) -> list[ArtifactResponse]:
    """获取运行产物元数据。"""

    artifacts = await session.scalars(
        select(ArtifactRecord)
        .where(ArtifactRecord.run_id == run_id)
        .order_by(ArtifactRecord.created_at)
    )
    return [
        ArtifactResponse.model_validate(artifact) for artifact in artifacts.all()
    ]


@router.get("/runs/{run_id}/files", response_model=FileListResponse)
async def list_generated_files(
    run_id: UUID,
    session: SessionDep,
) -> FileListResponse:
    """列出生成工程文件。"""

    await _require_run(session, run_id)
    try:
        workspace = run_workspace(run_id)
        entries = list_workspace_files(workspace)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileListResponse(
        run_id=run_id,
        files=[FileEntry(path=path, size=size) for path, size in entries],
        file_count=len(entries),
        total_size=sum(size for _, size in entries),
    )


@router.get("/runs/{run_id}/files/content", response_class=PlainTextResponse)
async def get_generated_file(
    run_id: UUID,
    path: str,
    session: SessionDep,
) -> PlainTextResponse:
    """读取生成工程中的单个文本文件。"""

    await _require_run(session, run_id)
    try:
        workspace = run_workspace(run_id)
        file_path = resolve_workspace_file(workspace, path)
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except (FileNotFoundError, ArtifactPathError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return PlainTextResponse(content)


@router.get("/runs/{run_id}/diff", response_model=DiffResponse)
async def get_generated_diff(
    run_id: UUID,
    session: SessionDep,
) -> DiffResponse:
    """返回生成工程相对空目录的初始 Diff。"""

    await _require_run(session, run_id)
    try:
        workspace = run_workspace(run_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    additions, deletions, patch = build_workspace_diff(workspace)
    return DiffResponse(
        run_id=run_id,
        additions=additions,
        deletions=deletions,
        patch=patch,
    )


@router.get("/runs/{run_id}/download")
async def download_generated_project(
    run_id: UUID,
    session: SessionDep,
) -> StreamingResponse:
    """下载完整生成工程 ZIP。"""

    await _require_run(session, run_id)
    try:
        workspace = run_workspace(run_id)
        payload = build_workspace_zip(workspace)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="multiagent-{run_id}.zip"'
        },
    )


async def _require_run(session: AsyncSession, run_id: UUID) -> RunRecord:
    run = await session.get(RunRecord, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="运行不存在")
    return run
