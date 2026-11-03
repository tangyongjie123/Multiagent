"""聊天持久化基础测试。"""

from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from app.api.schemas import ChatMessageCreate, ChatSessionCreate
from app.db.base import Base
from app.main import app


def test_chat_tables_are_registered() -> None:
    assert "chat_sessions" in Base.metadata.tables
    assert "chat_messages" in Base.metadata.tables


def test_chat_message_is_trimmed_and_blank_message_is_rejected() -> None:
    payload = ChatMessageCreate(content="  这个问题具体在哪里？  ")
    assert payload.content == "这个问题具体在哪里？"

    with pytest.raises(ValidationError):
        ChatMessageCreate(content="   ")


def test_chat_session_title_is_optional_and_normalized() -> None:
    payload = ChatSessionCreate(
        repository_id=UUID("00000000-0000-0000-0000-000000000001"),
        title="  安全审查对话  ",
    )
    assert payload.title == "安全审查对话"


def test_chat_routes_are_registered() -> None:
    paths = app.openapi()["paths"]
    assert "/api/v1/chat/sessions" in paths
    assert "/api/v1/chat/sessions/{session_id}/messages" in paths
