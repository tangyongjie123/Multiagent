"""仓库分析事件持久化。"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AnalysisEventRecord
from app.domain.models import AgentRole


async def append_analysis_event(
    session: AsyncSession,
    analysis_id: UUID,
    event_type: str,
    agent: AgentRole,
    message: str,
    data: dict[str, Any] | None = None,
) -> AnalysisEventRecord:
    """按单个分析内的单调递增序号追加事件。

    调用方负责提交事务；本函数只 flush，便于与状态更新处于同一事务。
    """

    current_sequence = await session.scalar(
        select(func.coalesce(func.max(AnalysisEventRecord.sequence), 0)).where(
            AnalysisEventRecord.analysis_id == analysis_id
        )
    )
    event = AnalysisEventRecord(
        analysis_id=analysis_id,
        sequence=int(current_sequence or 0) + 1,
        event_type=event_type,
        agent=agent.value,
        message=message,
        data=data or {},
    )
    session.add(event)
    await session.flush()
    return event
