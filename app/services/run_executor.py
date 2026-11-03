"""执行真实多 Agent 软件生成运行。"""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.checkpoint import get_checkpointer
from app.agents.specialists import LLMSpecialistExecutor
from app.agents.supervisor import build_supervisor_graph
from app.core.config import get_settings
from app.db.models import ArtifactRecord, ProjectRecord, RunRecord
from app.db.session import get_session_factory
from app.domain.models import AgentRole, RunStatus
from app.services.run_events import append_event
from app.services.workspace import WorkspaceManager

WORKER_ID = uuid4().hex
HEARTBEAT_INTERVAL_SECONDS = 15
STALE_AFTER_SECONDS = 60
_HEARTBEAT_TASKS: set[asyncio.Task[None]] = set()
_RUNNING_TASKS: dict[UUID, asyncio.Task[None]] = {}


async def recover_interrupted_runs() -> None:
    """把心跳超时的 running 运行标记为中断。"""

    cutoff = datetime.now(UTC) - timedelta(seconds=STALE_AFTER_SECONDS)
    async with get_session_factory()() as session:
        runs = await session.scalars(
            select(RunRecord).where(
                and_(
                    RunRecord.status == RunStatus.RUNNING.value,
                    or_(
                        RunRecord.heartbeat_at.is_(None),
                        RunRecord.heartbeat_at < cutoff,
                    ),
                    RunRecord.started_at < cutoff,
                )
            )
        )
        for run in runs.all():
            run.status = RunStatus.FAILED.value
            run.error_message = "服务进程中断"
            run.completed_at = datetime.now(UTC)
            await append_event(
                session,
                run.id,
                "run.interrupted",
                AgentRole.MAIN,
                "服务进程中断，运行已标记失败",
                {},
            )
        await session.commit()


async def _heartbeat_loop(run_id: UUID) -> None:
    """定期更新运行心跳，供启动恢复判断 Worker 是否仍存活。"""

    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
        async with get_session_factory()() as session:
            run = await session.get(RunRecord, run_id)
            if run is None or run.status != RunStatus.RUNNING.value:
                return
            run.heartbeat_at = datetime.now(UTC)
            await session.commit()


async def _emit_event(
    run_id: UUID,
    event_type: str,
    role: AgentRole,
    message: str,
    data: dict[str, Any],
) -> None:
    async with get_session_factory()() as session:
        await append_event(session, run_id, event_type, role, message, data)
        await session.commit()


async def _persist_result_artifacts(
    session: AsyncSession,
    run_id: UUID,
    workspace: WorkspaceManager,
    results: list[dict[str, Any]],
    decisions: list[dict[str, Any]],
) -> None:
    for index, result in enumerate(results, start=1):
        role = str(result.get("role", "unknown"))
        content = json.dumps(result, ensure_ascii=False, indent=2)
        storage_path = workspace.write_artifact(
            f"{index:02d}-{role}.json",
            content,
        )
        session.add(
            ArtifactRecord(
                run_id=run_id,
                kind=f"{role}.result",
                name=f"{index:02d}-{role}.json",
                content_type="application/json",
                storage_path=storage_path,
                sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            )
        )

    decisions_content = json.dumps(decisions, ensure_ascii=False, indent=2)
    decisions_path = workspace.write_artifact(
        "main-agent-decisions.json",
        decisions_content,
    )
    session.add(
        ArtifactRecord(
            run_id=run_id,
            kind="main.decisions",
            name="main-agent-decisions.json",
            content_type="application/json",
            storage_path=decisions_path,
            sha256=hashlib.sha256(decisions_content.encode("utf-8")).hexdigest(),
        )
    )


async def _mark_cancelled(run_id: UUID) -> None:
    """幂等地把运行标记为已取消。"""

    async with get_session_factory()() as session:
        run = await session.get(RunRecord, run_id)
        if run is None or run.status in {
            RunStatus.COMPLETED.value,
            RunStatus.FAILED.value,
            RunStatus.CANCELLED.value,
        }:
            return
        run.status = RunStatus.CANCELLED.value
        run.error_message = "用户取消"
        run.completed_at = datetime.now(UTC)
        await append_event(
            session,
            run_id,
            "run.cancelled",
            AgentRole.MAIN,
            "运行已由用户取消",
            {},
        )
        await session.commit()


async def cancel_run(run_id: UUID) -> None:
    """取消正在执行的 Agent 后台任务。"""

    await _mark_cancelled(run_id)
    task = _RUNNING_TASKS.get(run_id)
    if task is not None and not task.done():
        task.cancel()


async def execute_run(run_id: UUID) -> None:
    """登记后台任务并处理取消。"""

    task = asyncio.current_task()
    if task is not None:
        _RUNNING_TASKS[run_id] = task
    try:
        await _execute_run(run_id)
    except asyncio.CancelledError:
        await _mark_cancelled(run_id)
    finally:
        _RUNNING_TASKS.pop(run_id, None)


async def _execute_run(run_id: UUID) -> None:
    """后台执行主 Agent 工作流并持久化状态、事件和产物。"""

    settings = get_settings()
    session_factory = get_session_factory()
    async with session_factory() as session:
        run = await session.get(RunRecord, run_id)
        if run is None:
            return
        if run.status == RunStatus.CANCELLED.value:
            return
        project = await session.get(ProjectRecord, run.project_id)
        if project is None:
            return
        requirement = project.requirement
        run.status = RunStatus.RUNNING.value
        run.worker_id = WORKER_ID
        run.started_at = datetime.now(UTC)
        run.heartbeat_at = run.started_at
        await append_event(
            session,
            run.id,
            "run.started",
            AgentRole.MAIN,
            "主 Agent 已启动",
            {"chat_model": settings.effective_chat_model},
        )
        await session.commit()

    heartbeat_task = asyncio.create_task(_heartbeat_loop(run_id))
    _HEARTBEAT_TASKS.add(heartbeat_task)
    heartbeat_task.add_done_callback(_HEARTBEAT_TASKS.discard)
    workspace = WorkspaceManager(str(run_id))
    workspace.initialize()

    async def emitter(
        event_type: str,
        role: AgentRole,
        message: str,
        data: dict[str, Any],
    ) -> None:
        await _emit_event(run_id, event_type, role, message, data)

    try:
        if not settings.llm_configured:
            raise RuntimeError("对话模型 API 未配置")
        executor = LLMSpecialistExecutor(workspace, event_emitter=emitter)
        checkpointer = get_checkpointer()
        graph = build_supervisor_graph(executor, checkpointer=checkpointer)
        initial_state = {
            "run_id": str(run_id),
            "requirement": requirement,
            "completed_agents": [],
            "results": [],
            "decisions": [],
            "repair_attempts": 0,
            "max_repair_attempts": settings.max_repair_attempts,
            "needs_repair": False,
            "last_failed_agent": None,
            "token_budget": settings.run_token_budget,
            "input_tokens": 0,
            "output_tokens": 0,
            "is_simulated": False,
        }
        result = await graph.ainvoke(
            initial_state,
            config={"configurable": {"thread_id": str(run_id)}},
        )
        failed = bool(result.get("failed"))
        final_status = RunStatus.FAILED if failed else RunStatus.COMPLETED

        async with session_factory() as session:
            current_run = await session.get(RunRecord, run_id)
            if current_run is None:
                return
            await _persist_result_artifacts(
                session,
                run_id,
                workspace,
                list(result.get("results", [])),
                list(result.get("decisions", [])),
            )
            current_run.status = final_status.value
            current_run.current_agent = str(result.get("current_agent") or "")
            current_run.input_tokens = int(result.get("input_tokens", 0))
            current_run.output_tokens = int(result.get("output_tokens", 0))
            current_run.error_message = (
                str(result.get("error")) if result.get("error") else None
            )
            current_run.completed_at = datetime.now(UTC)
            await append_event(
                session,
                run_id,
                f"run.{final_status.value}",
                AgentRole.MAIN,
                (
                    "主 Agent 工作流完成"
                    if final_status is RunStatus.COMPLETED
                    else "主 Agent 工作流失败"
                ),
                {
                    "completed_agents": result.get("completed_agents", []),
                    "input_tokens": current_run.input_tokens,
                    "output_tokens": current_run.output_tokens,
                    "error": current_run.error_message,
                },
            )
            await session.commit()
    except Exception as exc:
        async with session_factory() as session:
            current_run = await session.get(RunRecord, run_id)
            if current_run is None:
                return
            current_run.status = RunStatus.FAILED.value
            current_run.error_message = type(exc).__name__
            current_run.completed_at = datetime.now(UTC)
            await append_event(
                session,
                run_id,
                "run.failed",
                AgentRole.MAIN,
                "主 Agent 执行异常",
                {"error_type": type(exc).__name__},
            )
            await session.commit()
