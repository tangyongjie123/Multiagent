"""仓库分析状态、事件、问题和报告接口。"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse, Response
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.api.schemas import (
    AnalysisResponse,
    ArtifactResponse,
    EventResponse,
    FindingResponse,
)
from app.db.models import (
    AnalysisArtifactRecord,
    AnalysisEventRecord,
    AnalysisRecord,
    FindingRecord,
    RepositoryRecord,
)
from app.db.session import get_session, get_session_factory
from app.domain.models import AnalysisStatus
from app.services.analysis_runner import cancel_analysis
from app.services.report_visuals import build_html_report, build_report_visuals
from app.services.repository import repository_workspace

router = APIRouter(prefix="/api/v1/analyses", tags=["analyses"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]
SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


async def _require_analysis(session: AsyncSession, analysis_id: UUID) -> AnalysisRecord:
    analysis = await session.get(AnalysisRecord, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="分析不存在")
    return analysis


async def _require_completed_artifact(
    session: AsyncSession,
    analysis_id: UUID,
    kind: str,
) -> tuple[AnalysisRecord, AnalysisArtifactRecord]:
    analysis = await _require_analysis(session, analysis_id)
    if analysis.status != AnalysisStatus.COMPLETED.value:
        raise HTTPException(status_code=409, detail="分析尚未完成")
    artifact = await session.scalar(
        select(AnalysisArtifactRecord).where(
            AnalysisArtifactRecord.analysis_id == analysis_id,
            AnalysisArtifactRecord.kind == kind,
        )
    )
    if artifact is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    return analysis, artifact


@router.get("/{analysis_id}", response_model=AnalysisResponse)
async def get_analysis(
    analysis_id: UUID,
    session: SessionDep,
) -> AnalysisResponse:
    return AnalysisResponse.model_validate(
        await _require_analysis(session, analysis_id)
    )


@router.post("/{analysis_id}/cancel", response_model=AnalysisResponse)
async def cancel_repository_analysis(
    analysis_id: UUID,
    session: SessionDep,
) -> AnalysisResponse:
    analysis = await _require_analysis(session, analysis_id)
    if analysis.status in {
        AnalysisStatus.COMPLETED.value,
        AnalysisStatus.FAILED.value,
        AnalysisStatus.CANCELLED.value,
    }:
        raise HTTPException(status_code=409, detail="分析已经结束")
    await cancel_analysis(analysis_id)
    await session.refresh(analysis)
    return AnalysisResponse.model_validate(analysis)


@router.get("/{analysis_id}/events", response_model=list[EventResponse])
async def list_analysis_events(
    analysis_id: UUID,
    session: SessionDep,
) -> list[EventResponse]:
    await _require_analysis(session, analysis_id)
    events = await session.scalars(
        select(AnalysisEventRecord)
        .where(AnalysisEventRecord.analysis_id == analysis_id)
        .order_by(AnalysisEventRecord.sequence)
    )
    return [EventResponse.model_validate(event) for event in events.all()]


@router.get("/{analysis_id}/events/stream")
async def stream_analysis_events(
    analysis_id: UUID,
    request: Request,
) -> EventSourceResponse:
    session_factory = get_session_factory()

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        last_sequence = 0
        terminal = {
            AnalysisStatus.COMPLETED.value,
            AnalysisStatus.FAILED.value,
            AnalysisStatus.CANCELLED.value,
        }
        while not await request.is_disconnected():
            async with session_factory() as session:
                analysis = await session.get(AnalysisRecord, analysis_id)
                if analysis is None:
                    yield {
                        "event": "error",
                        "data": json.dumps(
                            {"detail": "分析不存在"}, ensure_ascii=False
                        ),
                    }
                    return
                events = await session.scalars(
                    select(AnalysisEventRecord)
                    .where(
                        AnalysisEventRecord.analysis_id == analysis_id,
                        AnalysisEventRecord.sequence > last_sequence,
                    )
                    .order_by(AnalysisEventRecord.sequence)
                )
                for event in events.all():
                    last_sequence = event.sequence
                    payload = EventResponse.model_validate(event).model_dump(mode="json")
                    yield {
                        "id": str(event.sequence),
                        "event": event.event_type,
                        "data": json.dumps(payload, ensure_ascii=False),
                    }
                if analysis.status in terminal:
                    return
            await asyncio.sleep(1)

    return EventSourceResponse(event_generator())


@router.get("/{analysis_id}/findings", response_model=list[FindingResponse])
async def list_analysis_findings(
    analysis_id: UUID,
    session: SessionDep,
) -> list[FindingResponse]:
    await _require_analysis(session, analysis_id)
    severity_order = case(
        (FindingRecord.severity == "critical", 0),
        (FindingRecord.severity == "major", 1),
        (FindingRecord.severity == "minor", 2),
        else_=3,
    )
    findings = await session.scalars(
        select(FindingRecord)
        .where(FindingRecord.analysis_id == analysis_id)
        .order_by(severity_order, FindingRecord.created_at)
    )
    return [FindingResponse.model_validate(item) for item in findings.all()]


@router.get("/{analysis_id}/artifacts", response_model=list[ArtifactResponse])
async def list_analysis_artifacts(
    analysis_id: UUID,
    session: SessionDep,
) -> list[ArtifactResponse]:
    await _require_analysis(session, analysis_id)
    artifacts = await session.scalars(
        select(AnalysisArtifactRecord)
        .where(AnalysisArtifactRecord.analysis_id == analysis_id)
        .order_by(AnalysisArtifactRecord.created_at)
    )
    return [ArtifactResponse.model_validate(item) for item in artifacts.all()]


@router.get("/{analysis_id}/report", response_class=PlainTextResponse)
async def get_analysis_report(
    analysis_id: UUID,
    session: SessionDep,
) -> PlainTextResponse:
    _, artifact = await _require_completed_artifact(
        session,
        analysis_id,
        "report",
    )
    content = await asyncio.to_thread(
        Path(artifact.storage_path).read_text,
        encoding="utf-8",
    )
    return PlainTextResponse(content)


@router.get("/{analysis_id}/report/download")
async def download_analysis_report(
    analysis_id: UUID,
    session: SessionDep,
) -> FileResponse:
    analysis, artifact = await _require_completed_artifact(
        session,
        analysis_id,
        "report",
    )

    report_path = await asyncio.to_thread(
        _resolve_artifact_path,
        analysis_id,
        artifact.storage_path,
    )
    if report_path is None:
        raise HTTPException(status_code=404, detail="报告文件不存在")

    repository = await session.get(RepositoryRecord, analysis.repository_id)
    filename = _report_filename(repository, analysis_id, "md")
    return FileResponse(
        path=report_path,
        media_type="text/markdown",
        filename=filename,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/{analysis_id}/report/html", response_class=HTMLResponse)
async def get_html_report(
    analysis_id: UUID,
    session: SessionDep,
) -> HTMLResponse:
    analysis = await _require_analysis(session, analysis_id)
    if analysis.status != AnalysisStatus.COMPLETED.value:
        raise HTTPException(status_code=409, detail="分析尚未完成")
    artifact = await session.scalar(
        select(AnalysisArtifactRecord).where(
            AnalysisArtifactRecord.analysis_id == analysis_id,
            AnalysisArtifactRecord.kind == "report_html",
        )
    )
    content: str | None = None
    if artifact is not None:
        report_path = await asyncio.to_thread(
            _resolve_artifact_path,
            analysis_id,
            artifact.storage_path,
        )
        if report_path is not None:
            content = await asyncio.to_thread(
                report_path.read_text,
                encoding="utf-8",
            )
    if content is None:
        content = await _generate_html_from_findings(session, analysis)
    return HTMLResponse(
        content,
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": (
                "default-src 'none'; style-src 'unsafe-inline'; img-src data:"
            ),
        },
    )


@router.get("/{analysis_id}/report/html/download")
async def download_html_report(
    analysis_id: UUID,
    session: SessionDep,
) -> Response:
    analysis = await _require_analysis(session, analysis_id)
    if analysis.status != AnalysisStatus.COMPLETED.value:
        raise HTTPException(status_code=409, detail="分析尚未完成")
    artifact = await session.scalar(
        select(AnalysisArtifactRecord).where(
            AnalysisArtifactRecord.analysis_id == analysis_id,
            AnalysisArtifactRecord.kind == "report_html",
        )
    )
    repository = await session.get(RepositoryRecord, analysis.repository_id)
    filename = _report_filename(repository, analysis_id, "html")
    if artifact is not None:
        report_path = await asyncio.to_thread(
            _resolve_artifact_path,
            analysis_id,
            artifact.storage_path,
        )
        if report_path is not None:
            return FileResponse(
                path=report_path,
                media_type="text/html",
                filename=filename,
                headers={"Cache-Control": "no-store"},
            )
    content = await _generate_html_from_findings(session, analysis)
    return Response(
        content=content,
        media_type="text/html",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )


def _resolve_artifact_path(analysis_id: UUID, storage_path: str) -> Path | None:
    """校验报告文件位于对应分析工作区内。"""

    try:
        workspace = repository_workspace(analysis_id).resolve(strict=True)
        report_path = Path(storage_path).resolve(strict=True)
    except OSError:
        return None
    if not report_path.is_relative_to(workspace) or not report_path.is_file():
        return None
    return report_path


def _report_filename(
    repository: RepositoryRecord | None,
    analysis_id: UUID,
    extension: str,
) -> str:
    repository_slug = SAFE_FILENAME.sub(
        "-",
        repository.name if repository is not None else "repository",
    ).strip(".-_") or "repository"
    return f"{repository_slug}-{str(analysis_id)[:8]}-report.{extension}"


async def _generate_html_from_findings(
    session: AsyncSession,
    analysis: AnalysisRecord,
) -> str:
    """为没有预生成 HTML 的历史分析即时生成图文报告。"""

    repository = await session.get(RepositoryRecord, analysis.repository_id)
    if repository is None:
        raise HTTPException(status_code=404, detail="仓库不存在")
    records = await session.scalars(
        select(FindingRecord)
        .where(FindingRecord.analysis_id == analysis.id)
        .order_by(FindingRecord.created_at)
    )
    findings = [
        {
            "category": item.category,
            "severity": item.severity,
            "title": item.title,
            "file_path": item.file_path,
            "line": item.line,
            "evidence": item.evidence,
            "impact": item.impact,
            "recommendation": item.recommendation,
        }
        for item in records.all()
    ]
    file_count = 0
    snapshot_artifact = await session.scalar(
        select(AnalysisArtifactRecord).where(
            AnalysisArtifactRecord.analysis_id == analysis.id,
            AnalysisArtifactRecord.kind == "repository",
        )
    )
    if snapshot_artifact is not None:
        snapshot_path = await asyncio.to_thread(
            _resolve_artifact_path,
            analysis.id,
            snapshot_artifact.storage_path,
        )
        if snapshot_path is not None:
            try:
                snapshot_data = await asyncio.to_thread(
                    Path(snapshot_path).read_text,
                    encoding="utf-8",
                )
                parsed = json.loads(snapshot_data)
                file_count = int(parsed.get("file_count") or 0)
            except (OSError, ValueError, TypeError):
                file_count = 0
    visuals = build_report_visuals(
        repository_name=repository.name,
        findings=findings,
    )
    return build_html_report(
        repository_name=repository.name,
        repository_url=repository.url,
        branch=analysis.branch or repository.branch,
        commit_sha=analysis.commit_sha,
        file_count=file_count,
        findings=findings,
        visuals=visuals,
    )
