"""聊天持久化基础测试。"""

from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from app.agents.chat_specialists import (
    _partial_json_string_value,
    _stream_blocks,
)
from app.api.schemas import ChatMessageCreate, ChatSessionCreate
from app.db.base import Base
from app.db.models import FindingRecord
from app.main import app
from app.services.chat_runner import _finding_evidence


def test_chat_tables_are_registered() -> None:
    assert "chat_sessions" in Base.metadata.tables
    assert "chat_messages" in Base.metadata.tables
    assert "chat_citations" in Base.metadata.tables
    assert "chat_events" in Base.metadata.tables


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
    assert "/api/v1/chat/sessions/{session_id}/events/stream" in paths
    assert "/api/v1/chat/messages/{message_id}/citations" in paths


def test_chat_finding_evidence_is_redacted_before_model_use() -> None:
    finding = FindingRecord(
        analysis_id=UUID("00000000-0000-0000-0000-000000000001"),
        category="security",
        severity="major",
        title="DATABASE_PASSWORD='root-secret'",
        evidence="DB_PWD='root-secret'",
        impact="可能泄露",
        recommendation="移除明文密码",
    )

    evidence = _finding_evidence(finding)

    assert "root-secret" not in evidence["title"]
    assert "root-secret" not in evidence["evidence"]
    assert "<REDACTED>" in evidence["evidence"]


def test_partial_json_answer_can_be_extracted_while_streaming() -> None:
    document = '{"answer":"第一行\\n第二行 \\u4e2d'

    assert _partial_json_string_value(document, "answer") == "第一行\n第二行 中"
    assert _partial_json_string_value('{"citations":[]', "answer") == ""


def test_stream_blocks_wait_for_complete_lines() -> None:
    blocks, remaining = _stream_blocks("第一行\n第二行", final=False)
    assert blocks == ["第一行\n"]
    assert remaining == "第二行"

    final_blocks, final_remaining = _stream_blocks(remaining, final=True)
    assert final_blocks == ["第二行"]
    assert final_remaining == ""


def test_stream_blocks_flush_long_single_line_before_completion() -> None:
    text = "这是一段需要在生成过程中逐步显示的长文本，" * 6

    blocks, remaining = _stream_blocks(text, final=False)

    assert blocks
    assert "".join(blocks) + remaining == text
    assert remaining
