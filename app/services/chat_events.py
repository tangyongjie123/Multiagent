"""聊天执行事件持久化。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ChatEventRecord
from app.domain.models import AgentRole


async def append_chat_event(
    session: AsyncSession,
    session_id: UUID,
    event_type: str,
    agent: AgentRole,
    message: str,
    data: dict[str, Any] | None = None,
) -> ChatEventRecord:
    """按聊天会话内的单调序号追加事件。"""

    current_sequence = await session.scalar(
        select(func.coalesce(func.max(ChatEventRecord.sequence), 0)).where(
            ChatEventRecord.session_id == session_id
        )
    )
    event = ChatEventRecord(
        session_id=session_id,
        sequence=int(current_sequence or 0) + 1,
        event_type=event_type,
        agent=agent.value,
        message=message,
        data=data or {},
        created_at=datetime.now(UTC),
    )
    session.add(event)
    await session.flush()
    return event
