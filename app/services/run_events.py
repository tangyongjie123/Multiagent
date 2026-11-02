"""运行事件持久化。"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentEventRecord
from app.domain.models import AgentRole


async def append_event(
    session: AsyncSession,
    run_id: UUID,
    event_type: str,
    agent: AgentRole,
    message: str,
    data: dict[str, Any] | None = None,
) -> AgentEventRecord:
    """按运行内顺序追加事件。"""

    current_sequence = await session.scalar(
        select(func.coalesce(func.max(AgentEventRecord.sequence), 0)).where(
            AgentEventRecord.run_id == run_id
        )
    )
    event = AgentEventRecord(
        run_id=run_id,
        sequence=int(current_sequence or 0) + 1,
        event_type=event_type,
        agent=agent.value,
        message=message,
        data=data or {},
    )
    session.add(event)
    await session.flush()
    return event
