"""仓库分析状态、事件、问题和报告接口。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.api.schemas import (
    AnalysisResponse,
    ArtifactResponse,
    EventResponse,
    FindingResponse,
)
from app.db.models import AnalysisArtifactRecord, AnalysisEventRecord, AnalysisRecord, FindingRecord
from app.db.session import get_session, get_session_factory
from app.domain.models import AnalysisStatus
from app.services.analysis_runner import cancel_analysis

router = APIRouter(prefix="/api/v1/analyses", tags=["analyses"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def _require_analysis(session: AsyncSession, analysis_id: UUID) -> AnalysisRecord:
    analysis = await session.get(AnalysisRecord, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="分析不存在")
    return analysis


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
    analysis = await _require_analysis(session, analysis_id)
    if analysis.status != AnalysisStatus.COMPLETED.value:
        raise HTTPException(status_code=409, detail="分析尚未完成")
    artifact = await session.scalar(
        select(AnalysisArtifactRecord).where(
            AnalysisArtifactRecord.analysis_id == analysis_id,
            AnalysisArtifactRecord.kind == "report",
        )
    )
    if artifact is None:
        raise HTTPException(status_code=404, detail="报告不存在")
    content = await asyncio.to_thread(
        Path(artifact.storage_path).read_text,
        encoding="utf-8",
    )
    return PlainTextResponse(content)
