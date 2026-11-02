"""Agent 运行、事件和产物接口。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.api.schemas import ArtifactResponse, EventResponse, RunCreate, RunResponse
from app.core.config import get_settings
from app.db.models import AgentEventRecord, ArtifactRecord, ProjectRecord, RunRecord
from app.db.session import get_session, get_session_factory
from app.domain.models import AgentRole, RunStatus
from app.services.run_events import append_event

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
