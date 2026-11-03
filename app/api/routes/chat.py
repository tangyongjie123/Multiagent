"""聊天会话与消息的持久化 API。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    status,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sse_starlette.sse import EventSourceResponse

from app.api.schemas import (
    ChatCitationResponse,
    ChatEventResponse,
    ChatMessageCreate,
    ChatMessageResponse,
    ChatSessionCreate,
    ChatSessionResponse,
    ChatTurnResponse,
)
from app.db.models import (
    AnalysisRecord,
    ChatCitationRecord,
    ChatEventRecord,
    ChatMessageRecord,
    ChatSessionRecord,
    RepositoryRecord,
)
from app.db.session import get_session, get_session_factory
from app.domain.models import (
    AgentRole,
    ChatMessageRole,
    ChatMessageStatus,
    ChatSessionStatus,
)
from app.services.chat_events import append_chat_event
from app.services.redaction import redact_sensitive_text

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
        if analysis.status != "completed":
            raise HTTPException(
                status_code=409,
                detail="只有已完成的分析才能用于聊天",
            )

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
    response_model=ChatTurnResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_chat_message(
    session_id: UUID,
    payload: ChatMessageCreate,
    session: SessionDep,
    background_tasks: BackgroundTasks,
) -> ChatTurnResponse:
    """保存用户消息并启动主 Agent 聊天工作流。"""

    chat_session = await _require_session(session, session_id)
    if chat_session.status != ChatSessionStatus.ACTIVE.value:
        raise HTTPException(status_code=409, detail="聊天会话已归档")
    await _require_completed_analysis(session, chat_session)
    generating_message = await session.scalar(
        select(ChatMessageRecord.id)
        .where(
            ChatMessageRecord.session_id == session_id,
            ChatMessageRecord.role == ChatMessageRole.ASSISTANT.value,
            ChatMessageRecord.status == ChatMessageStatus.GENERATING.value,
        )
        .limit(1)
    )
    if generating_message is not None:
        raise HTTPException(
            status_code=409,
            detail="上一条回答仍在生成，请等待完成后再提问",
        )

    now = datetime.now(UTC)
    user_message = ChatMessageRecord(
        session_id=chat_session.id,
        role=ChatMessageRole.USER.value,
        content=payload.content,
        status=ChatMessageStatus.RECORDED.value,
        created_at=now,
    )
    assistant_message = ChatMessageRecord(
        session_id=chat_session.id,
        role=ChatMessageRole.ASSISTANT.value,
        content="",
        status=ChatMessageStatus.GENERATING.value,
        created_at=now,
    )
    chat_session.last_message_at = now
    chat_session.updated_at = now
    session.add_all([user_message, assistant_message])
    await session.flush()
    await append_chat_event(
        session,
        session_id,
        "chat.turn.queued",
        AgentRole.MAIN,
        "聊天请求已创建，等待主 Agent 处理",
        {
            "user_message_id": str(user_message.id),
            "assistant_message_id": str(assistant_message.id),
        },
    )
    await session.commit()
    await session.refresh(user_message)
    await session.refresh(assistant_message)

    from app.services.chat_runner import run_chat_turn

    background_tasks.add_task(
        run_chat_turn,
        chat_session.id,
        user_message.id,
        assistant_message.id,
    )
    return ChatTurnResponse(
        user_message=ChatMessageResponse.model_validate(user_message),
        assistant_message=ChatMessageResponse.model_validate(assistant_message),
    )


async def _require_completed_analysis(
    session: AsyncSession,
    chat_session: ChatSessionRecord,
) -> AnalysisRecord:
    """确保聊天使用的是已完成且属于当前仓库的分析。"""

    if chat_session.analysis_id is not None:
        analysis = await session.get(AnalysisRecord, chat_session.analysis_id)
        if analysis is None or analysis.repository_id != chat_session.repository_id:
            raise HTTPException(status_code=409, detail="聊天关联的分析不存在")
    else:
        analysis = await session.scalar(
            select(AnalysisRecord)
            .where(
                AnalysisRecord.repository_id == chat_session.repository_id,
                AnalysisRecord.status == "completed",
            )
            .order_by(AnalysisRecord.created_at.desc())
            .limit(1)
        )
        if analysis is None:
            raise HTTPException(
                status_code=409,
                detail="该仓库还没有已完成的分析",
            )
    if analysis.status != "completed":
        raise HTTPException(
            status_code=409,
            detail="只有已完成的分析才能用于聊天",
        )
    return analysis


@router.get("/messages/{message_id}/citations", response_model=list[ChatCitationResponse])
async def list_message_citations(
    message_id: UUID,
    session: SessionDep,
) -> list[ChatCitationResponse]:
    """返回助手消息引用的 Finding 证据。"""

    message = await session.get(ChatMessageRecord, message_id)
    if message is None or message.role != ChatMessageRole.ASSISTANT.value:
        raise HTTPException(status_code=404, detail="助手消息不存在")
    citations = await session.scalars(
        select(ChatCitationRecord)
        .where(ChatCitationRecord.message_id == message_id)
        .order_by(ChatCitationRecord.created_at)
    )
    return [
        ChatCitationResponse.model_validate(citation).model_copy(
            update={"excerpt": redact_sensitive_text(citation.excerpt)}
        )
        for citation in citations.all()
    ]


@router.get("/sessions/{session_id}/events", response_model=list[ChatEventResponse])
async def list_chat_events(
    session_id: UUID,
    session: SessionDep,
) -> list[ChatEventResponse]:
    """按顺序返回聊天执行事件。"""

    await _require_session(session, session_id)
    events = await session.scalars(
        select(ChatEventRecord)
        .where(ChatEventRecord.session_id == session_id)
        .order_by(ChatEventRecord.sequence)
    )
    return [ChatEventResponse.model_validate(event) for event in events.all()]


@router.get("/sessions/{session_id}/events/stream")
async def stream_chat_events(
    session_id: UUID,
    request: Request,
    after_sequence: Annotated[int, Query(ge=0)] = 0,
) -> EventSourceResponse:
    """通过 SSE 推送聊天 Agent 事件。"""

    session_factory = get_session_factory()

    async def event_generator() -> AsyncIterator[dict[str, str]]:
        last_sequence = after_sequence
        terminal = {"chat.completed", "chat.failed"}
        while not await request.is_disconnected():
            async with session_factory() as session:
                chat_session = await session.get(ChatSessionRecord, session_id)
                if chat_session is None:
                    yield {
                        "event": "error",
                        "data": json.dumps(
                            {"detail": "聊天会话不存在"},
                            ensure_ascii=False,
                        ),
                    }
                    return
                events = await session.scalars(
                    select(ChatEventRecord)
                    .where(
                        ChatEventRecord.session_id == session_id,
                        ChatEventRecord.sequence > last_sequence,
                    )
                    .order_by(ChatEventRecord.sequence)
                )
                finished = False
                for event in events.all():
                    last_sequence = event.sequence
                    payload = ChatEventResponse.model_validate(event).model_dump(
                        mode="json"
                    )
                    if event.event_type in terminal:
                        finished = True
                    yield {
                        "id": str(event.sequence),
                        "event": event.event_type,
                        "data": json.dumps(payload, ensure_ascii=False),
                    }
                if finished:
                    return
            # 聊天回答包含增量文本，使用较短间隔降低“思考中”状态的可见延迟。
            await asyncio.sleep(0.25)

    return EventSourceResponse(event_generator())
