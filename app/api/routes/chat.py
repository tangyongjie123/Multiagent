"""聊天会话与消息的持久化 API。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import (
    ChatMessageCreate,
    ChatMessageResponse,
    ChatSessionCreate,
    ChatSessionResponse,
)
from app.db.models import (
    AnalysisRecord,
    ChatMessageRecord,
    ChatSessionRecord,
    RepositoryRecord,
)
from app.db.session import get_session
from app.domain.models import ChatMessageRole, ChatMessageStatus, ChatSessionStatus

router = APIRouter(prefix="/api/v1/chat", tags=["chat"])
SessionDep = Annotated[AsyncSession, Depends(get_session)]


async def _require_session(
    session: AsyncSession,
    session_id: UUID,
) -> ChatSessionRecord:
    """加载聊天会话，不存在时返回 404。"""

    chat_session = await session.get(ChatSessionRecord, session_id)
    if chat_session is None:
        raise HTTPException(status_code=404, detail="聊天会话不存在")
    return chat_session


@router.post(
    "/sessions",
    response_model=ChatSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_chat_session(
    payload: ChatSessionCreate,
    session: SessionDep,
) -> ChatSessionResponse:
    """创建绑定仓库和可选分析结果的聊天会话。"""

    repository = await session.get(RepositoryRecord, payload.repository_id)
    if repository is None:
        raise HTTPException(status_code=404, detail="仓库不存在")

    if payload.analysis_id is not None:
        analysis = await session.get(AnalysisRecord, payload.analysis_id)
        if analysis is None or analysis.repository_id != repository.id:
            raise HTTPException(status_code=400, detail="分析结果不属于该仓库")

    now = datetime.now(UTC)
    chat_session = ChatSessionRecord(
        repository_id=repository.id,
        analysis_id=payload.analysis_id,
        title=payload.title or f"{repository.name} 审查对话",
        status=ChatSessionStatus.ACTIVE.value,
        created_at=now,
        updated_at=now,
    )
    session.add(chat_session)
    await session.commit()
    await session.refresh(chat_session)
    return ChatSessionResponse.model_validate(chat_session)


@router.get("/sessions", response_model=list[ChatSessionResponse])
async def list_chat_sessions(
    session: SessionDep,
    repository_id: Annotated[UUID | None, Query()] = None,
) -> list[ChatSessionResponse]:
    """按更新时间倒序返回聊天会话，可按仓库筛选。"""

    statement = select(ChatSessionRecord)
    if repository_id is not None:
        statement = statement.where(
            ChatSessionRecord.repository_id == repository_id
        )
    chat_sessions = await session.scalars(
        statement.order_by(ChatSessionRecord.updated_at.desc())
    )
    return [
        ChatSessionResponse.model_validate(chat_session)
        for chat_session in chat_sessions.all()
    ]


@router.get("/sessions/{session_id}", response_model=ChatSessionResponse)
async def get_chat_session(
    session_id: UUID,
    session: SessionDep,
) -> ChatSessionResponse:
    """返回单个聊天会话。"""

    return ChatSessionResponse.model_validate(
        await _require_session(session, session_id)
    )


@router.get(
    "/sessions/{session_id}/messages",
    response_model=list[ChatMessageResponse],
)
async def list_chat_messages(
    session_id: UUID,
    session: SessionDep,
) -> list[ChatMessageResponse]:
    """按创建时间返回会话中的消息。"""

    await _require_session(session, session_id)
    messages = await session.scalars(
        select(ChatMessageRecord)
        .where(ChatMessageRecord.session_id == session_id)
        .order_by(ChatMessageRecord.created_at)
    )
    return [
        ChatMessageResponse.model_validate(message) for message in messages.all()
    ]


@router.post(
    "/sessions/{session_id}/messages",
    response_model=ChatMessageResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_chat_message(
    session_id: UUID,
    payload: ChatMessageCreate,
    session: SessionDep,
) -> ChatMessageResponse:
    """保存用户消息。

    当前阶段不生成助手回复，下一阶段会由主 Agent 和聊天专业 Agent 接管。
    """

    chat_session = await _require_session(session, session_id)
    if chat_session.status != ChatSessionStatus.ACTIVE.value:
        raise HTTPException(status_code=409, detail="聊天会话已归档")

    now = datetime.now(UTC)
    message = ChatMessageRecord(
        session_id=chat_session.id,
        role=ChatMessageRole.USER.value,
        content=payload.content,
        status=ChatMessageStatus.RECORDED.value,
        created_at=now,
    )
    chat_session.last_message_at = now
    chat_session.updated_at = now
    session.add(message)
    await session.commit()
    await session.refresh(message)
    return ChatMessageResponse.model_validate(message)
