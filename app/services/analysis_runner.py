"""执行 Git 仓库分析工作流。"""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from sqlalchemy import and_, or_, select

from app.agents.checkpoint import get_checkpointer
from app.agents.specialists import RepositoryAnalysisExecutor
from app.agents.supervisor import AnalysisState, build_analysis_graph
from app.core.config import get_settings
from app.db.models import (
    AnalysisArtifactRecord,
    AnalysisRecord,
    FindingRecord,
    RepositoryRecord,
)
from app.db.session import get_session_factory
from app.domain.models import AgentRole, AnalysisStatus
from app.services.analysis_events import append_analysis_event
from app.services.report_visuals import (
    build_html_report,
    build_report_visuals,
    inject_markdown_visuals,
)
from app.services.repository import (
    clone_repository,
    repository_workspace,
    scan_repository,
)

WORKER_ID = uuid4().hex
HEARTBEAT_INTERVAL_SECONDS = 15
STALE_AFTER_SECONDS = 60
# 保存本进程中的任务句柄，取消时才能中断正在运行的异步工作流。
_RUNNING_TASKS: dict[UUID, asyncio.Task[None]] = {}
_HEARTBEAT_TASKS: set[asyncio.Task[None]] = set()


async def recover_interrupted_analyses() -> None:
    """把心跳超时的分析标记为失败。"""

    cutoff = datetime.now(UTC) - timedelta(seconds=STALE_AFTER_SECONDS)
    async with get_session_factory()() as session:
        analyses = await session.scalars(
            select(AnalysisRecord).where(
                and_(
                    AnalysisRecord.status.in_(
                        [AnalysisStatus.CLONING.value, AnalysisStatus.ANALYZING.value]
                    ),
                    or_(
                        AnalysisRecord.heartbeat_at.is_(None),
                        AnalysisRecord.heartbeat_at < cutoff,
                    ),
                    AnalysisRecord.started_at < cutoff,
                )
            )
        )
        for analysis in analyses.all():
            analysis.status = AnalysisStatus.FAILED.value
            analysis.error_message = "分析进程中断"
            analysis.completed_at = datetime.now(UTC)
            await append_analysis_event(
                session,
                analysis.id,
                "analysis.interrupted",
                AgentRole.MAIN,
                "分析进程中断",
            )
        await session.commit()


async def _heartbeat_loop(analysis_id: UUID) -> None:
    """对运行中的分析持续更新时间戳，供进程重启后的中断检测使用。"""

    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
        async with get_session_factory()() as session:
            analysis = await session.get(AnalysisRecord, analysis_id)
            if analysis is None or analysis.status not in {
                AnalysisStatus.CLONING.value,
                AnalysisStatus.ANALYZING.value,
            }:
                return
            analysis.heartbeat_at = datetime.now(UTC)
            await session.commit()


async def _emit_event(
    analysis_id: UUID,
    event_type: str,
    agent: AgentRole,
    message: str,
    data: dict[str, Any],
) -> None:
    """持久化事件，并同步更新当前 Agent 字段。"""

    async with get_session_factory()() as session:
        await append_analysis_event(
            session,
            analysis_id,
            event_type,
            agent,
            message,
            data,
        )
        analysis = await session.get(AnalysisRecord, analysis_id)
        if analysis is not None and analysis.status in {
            AnalysisStatus.CLONING.value,
            AnalysisStatus.ANALYZING.value,
        }:
            analysis.current_agent = agent.value
        await session.commit()


async def _mark_cancelled(analysis_id: UUID) -> None:
    """把未结束的分析标记为用户取消。"""

    async with get_session_factory()() as session:
        analysis = await session.get(AnalysisRecord, analysis_id)
        if analysis is None or analysis.status in {
            AnalysisStatus.COMPLETED.value,
            AnalysisStatus.FAILED.value,
            AnalysisStatus.CANCELLED.value,
        }:
            return
        analysis.status = AnalysisStatus.CANCELLED.value
        analysis.error_message = "用户取消"
        analysis.completed_at = datetime.now(UTC)
        await append_analysis_event(
            session,
            analysis_id,
            "analysis.cancelled",
            AgentRole.MAIN,
            "分析已由用户取消",
        )
        await session.commit()


async def cancel_analysis(analysis_id: UUID) -> None:
    """先持久化取消状态，再终止本进程内的异步任务。"""

    await _mark_cancelled(analysis_id)
    task = _RUNNING_TASKS.get(analysis_id)
    if task is not None and not task.done():
        task.cancel()


async def run_analysis(analysis_id: UUID) -> None:
    """后台执行分析并处理取消。"""

    task = asyncio.current_task()
    if task is not None:
        _RUNNING_TASKS[analysis_id] = task
    try:
        await _run_analysis(analysis_id)
    except asyncio.CancelledError:
        await _mark_cancelled(analysis_id)
    finally:
        _RUNNING_TASKS.pop(analysis_id, None)


async def _run_analysis(analysis_id: UUID) -> None:
    """执行从克隆到报告落库的完整后台流程。"""

    settings = get_settings()
    session_factory = get_session_factory()

    async with session_factory() as session:
        analysis = await session.get(AnalysisRecord, analysis_id)
        if analysis is None or analysis.status == AnalysisStatus.CANCELLED.value:
            return
        repository = await session.get(RepositoryRecord, analysis.repository_id)
        if repository is None:
            return
        repo_url = repository.url
        repo_name = repository.name
        branch = analysis.branch or repository.branch
        analysis.status = AnalysisStatus.CLONING.value
        analysis.worker_id = WORKER_ID
        analysis.started_at = datetime.now(UTC)
        analysis.heartbeat_at = analysis.started_at
        await append_analysis_event(
            session,
            analysis_id,
            "analysis.started",
            AgentRole.MAIN,
            "主 Agent 已启动仓库分析",
            {"url": repo_url, "branch": branch},
        )
        await session.commit()

    heartbeat = asyncio.create_task(_heartbeat_loop(analysis_id))
    _HEARTBEAT_TASKS.add(heartbeat)
    heartbeat.add_done_callback(_HEARTBEAT_TASKS.discard)

    async def emitter(
        event_type: str,
        role: AgentRole,
        message: str,
        data: dict[str, Any],
    ) -> None:
        await _emit_event(analysis_id, event_type, role, message, data)

    try:
        # 第一阶段：浅克隆和只读扫描。
        workspace = repository_workspace(analysis_id)
        commit_sha = await clone_repository(repo_url, branch, workspace)
        snapshot = await scan_repository(workspace)
        async with session_factory() as session:
            analysis = await session.get(AnalysisRecord, analysis_id)
            if analysis is None:
                return
            repository = await session.get(RepositoryRecord, analysis.repository_id)
            if repository is None:
                return
            analysis.status = AnalysisStatus.ANALYZING.value
            analysis.commit_sha = commit_sha
            repository.latest_commit = commit_sha
            await append_analysis_event(
                session,
                analysis_id,
                "repository.scanned",
                AgentRole.REPOSITORY,
                (
                    f"仓库克隆完成，已扫描 {snapshot.file_count} 个文件，"
                    f"发现 {len(snapshot.test_files)} 个测试文件"
                ),
                snapshot.to_dict(),
            )
            await session.commit()

        # 第二阶段：交给 LangGraph 主 Agent 依次调度专业 Agent。
        executor = RepositoryAnalysisExecutor(
            snapshot=snapshot,
            repository_name=repo_name,
            analysis_id=str(analysis_id),
            event_emitter=emitter,
        )
        graph = build_analysis_graph(executor, get_checkpointer())
        initial_state: AnalysisState = {
            "analysis_id": str(analysis_id),
            "repository_url": repo_url,
            "branch": branch,
            "repo_path": str(workspace),
            "completed_agents": [],
            "results": [],
            "decisions": [],
            "input_tokens": 0,
            "output_tokens": 0,
            "token_budget": settings.analysis_token_budget,
        }
        result = await graph.ainvoke(
            initial_state,
            config={"configurable": {"thread_id": f"analysis:{analysis_id}"}},
        )
        failed = bool(result.get("failed"))
        final_status = AnalysisStatus.FAILED if failed else AnalysisStatus.COMPLETED

        # 第三阶段：生成 Markdown、HTML、SVG 和结构化中间产物。
        findings = RepositoryAnalysisExecutor._collect_findings(
            result.get("results", [])
        )
        report = _report_markdown(repo_name, result, findings)
        visuals = build_report_visuals(
            repository_name=repo_name,
            findings=findings,
        )
        report = inject_markdown_visuals(report, visuals)
        html_report = build_html_report(
            repository_name=repo_name,
            repository_url=repo_url,
            branch=branch,
            commit_sha=snapshot.commit_sha,
            file_count=snapshot.file_count,
            findings=findings,
            visuals=visuals,
        )
        artifact_dir = workspace / ".analysis"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        report_path = artifact_dir / "report.md"
        report_path.write_text(report, encoding="utf-8")
        html_report_path = artifact_dir / "report.html"
        html_report_path.write_text(html_report, encoding="utf-8")
        severity_chart_path = artifact_dir / "severity-distribution.svg"
        severity_chart_path.write_text(visuals.severity_svg, encoding="utf-8")
        category_chart_path = artifact_dir / "category-distribution.svg"
        category_chart_path.write_text(visuals.category_svg, encoding="utf-8")
        findings_path = artifact_dir / "findings.json"
        findings_path.write_text(
            json.dumps(findings, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        snapshot_path = artifact_dir / "repository.json"
        snapshot_path.write_text(
            json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # 第四阶段：问题、产物和最终状态在同一事务中落库。
        async with session_factory() as session:
            analysis = await session.get(AnalysisRecord, analysis_id)
            if analysis is None:
                return
            for finding in findings:
                session.add(
                    FindingRecord(
                        analysis_id=analysis_id,
                        category=finding["category"],
                        severity=finding["severity"],
                        title=finding["title"],
                        file_path=finding.get("file_path"),
                        line=finding.get("line"),
                        evidence=finding["evidence"],
                        impact=finding["impact"],
                        recommendation=finding["recommendation"],
                    )
                )
            for kind, name, path in (
                ("report", "report.md", report_path),
                ("report_html", "report.html", html_report_path),
                ("severity_chart", "severity-distribution.svg", severity_chart_path),
                ("category_chart", "category-distribution.svg", category_chart_path),
                ("findings", "findings.json", findings_path),
                ("repository", "repository.json", snapshot_path),
            ):
                content = path.read_bytes()
                if path.suffix == ".html":
                    content_type = "text/html"
                elif path.suffix == ".svg":
                    content_type = "image/svg+xml"
                elif path.suffix == ".md":
                    content_type = "text/markdown"
                else:
                    content_type = "application/json"
                session.add(
                    AnalysisArtifactRecord(
                        analysis_id=analysis_id,
                        kind=kind,
                        name=name,
                        content_type=content_type,
                        storage_path=str(path),
                        sha256=hashlib.sha256(content).hexdigest(),
                    )
                )
            analysis.status = final_status.value
            analysis.current_agent = "main"
            analysis.summary = (
                f"完成静态分析，共发现 {len(findings)} 个问题。"
                if not failed
                else str(result.get("error"))
            )
            analysis.error_message = (
                str(result.get("error")) if result.get("error") else None
            )
            analysis.finding_count = len(findings)
            analysis.input_tokens = int(result.get("input_tokens", 0))
            analysis.output_tokens = int(result.get("output_tokens", 0))
            analysis.completed_at = datetime.now(UTC)
            await append_analysis_event(
                session,
                analysis_id,
                f"analysis.{final_status.value}",
                AgentRole.MAIN,
                (
                    "仓库分析完成"
                    if final_status is AnalysisStatus.COMPLETED
                    else "仓库分析失败"
                ),
                {
                    "finding_count": len(findings),
                    "completed_agents": result.get("completed_agents", []),
                },
            )
            await session.commit()
    except Exception as exc:
        # 失败也必须落库，避免前端一直停留在 analyzing 状态。
        error_message = str(exc).strip()[:2_000] or type(exc).__name__
        async with session_factory() as session:
            analysis = await session.get(AnalysisRecord, analysis_id)
            if analysis is None:
                return
            analysis.status = AnalysisStatus.FAILED.value
            analysis.error_message = error_message
            analysis.completed_at = datetime.now(UTC)
            await append_analysis_event(
                session,
                analysis_id,
                "analysis.failed",
                AgentRole.MAIN,
                f"仓库分析失败：{error_message}",
                {"error_type": type(exc).__name__, "error": error_message},
            )
            await session.commit()


def _report_markdown(
    repo_name: str,
    result: AnalysisState,
    findings: list[dict[str, Any]],
) -> str:
    """优先使用 Report Agent 的 Markdown，缺失时生成最小兜底报告。"""

    report_result = next(
        (
            item
            for item in reversed(result.get("results", []))
            if item.get("role") == AgentRole.REPORT.value
        ),
        None,
    )
    if report_result:
        payload = report_result.get("artifacts", {}).get("payload", {})
        if isinstance(payload, dict) and isinstance(payload.get("markdown"), str):
            return cast(str, payload["markdown"])

    lines = [f"# {repo_name} 代码审查报告", "", f"共发现 {len(findings)} 个问题。"]
    return "\n".join(lines)
