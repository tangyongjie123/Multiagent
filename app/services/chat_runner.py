"""执行一次基于已分析仓库证据的聊天回答。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.chat_specialists import ChatAgentExecutor
from app.agents.checkpoint import get_checkpointer
from app.agents.supervisor import ChatState, build_chat_graph
from app.core.config import get_settings
from app.db.models import (
    AnalysisRecord,
    ChatCitationRecord,
    ChatMessageRecord,
    ChatSessionRecord,
    FindingRecord,
    RepositoryRecord,
)
from app.db.session import get_session_factory
from app.domain.models import (
    AgentRole,
    ChatMessageStatus,
    ChatSessionStatus,
)
from app.services.chat_events import append_chat_event
from app.services.redaction import redact_sensitive_text


async def run_chat_turn(
    session_id: UUID,
    user_message_id: UUID,
    assistant_message_id: UUID,
) -> None:
    """后台生成助手回答，并持久化消息、事件和 Finding 引用。"""

    session_factory = get_session_factory()
    settings = get_settings()
    try:
        async with session_factory() as session:
            chat_session = await session.get(ChatSessionRecord, session_id)
            user_message = await session.get(ChatMessageRecord, user_message_id)
            assistant_message = await session.get(
                ChatMessageRecord, assistant_message_id
            )
            if (
                chat_session is None
                or user_message is None
                or assistant_message is None
            ):
                return
            repository = await session.get(
                RepositoryRecord, chat_session.repository_id
            )
            if repository is None:
                raise RuntimeError("聊天关联仓库不存在")

            analysis = await _resolve_analysis(session, chat_session)
            findings = await _load_findings(session, analysis.id) if analysis else []
            previous_messages = await session.scalars(
                select(ChatMessageRecord)
                .where(
                    ChatMessageRecord.session_id == session_id,
                    ChatMessageRecord.id != user_message_id,
                    ChatMessageRecord.created_at < user_message.created_at,
                    ChatMessageRecord.status.in_(
                        [
                            ChatMessageStatus.RECORDED.value,
                            ChatMessageStatus.COMPLETED.value,
                        ]
                    ),
                )
                .order_by(ChatMessageRecord.created_at.desc())
                .limit(settings.chat_history_messages)
            )
            history = [
                {
                    "role": item.role,
                    "content": redact_sensitive_text(item.content),
                }
                for item in reversed(previous_messages.all())
            ]
            evidence = [_finding_evidence(item) for item in findings]
            analysis_summary = analysis.summary if analysis else None
            repository_name = repository.name

        async def emitter(
            event_type: str,
            role: AgentRole,
            message: str,
            data: dict[str, Any],
        ) -> None:
            await _emit_event(session_id, event_type, role, message, data)

        await _emit_event(
            session_id,
            "chat.turn.started",
            AgentRole.MAIN,
            "主 Agent 已启动聊天处理",
            {"user_message_id": str(user_message_id)},
        )
        executor = ChatAgentExecutor(emitter)
        graph = build_chat_graph(executor, get_checkpointer())
        initial_state: ChatState = {
            "session_id": str(session_id),
            "user_content": redact_sensitive_text(user_message.content),
            "repository_name": repository_name,
            "analysis_summary": (
                redact_sensitive_text(analysis_summary)
                if analysis_summary
                else None
            ),
            "history": history,
            "evidence": evidence,
            "completed_agents": [],
            "results": [],
            "decisions": [],
            "input_tokens": 0,
            "output_tokens": 0,
            "token_budget": settings.chat_token_budget,
        }
        result = await graph.ainvoke(
            initial_state,
            config={
                "configurable": {
                    "thread_id": f"chat:{session_id}:{assistant_message_id}"
                }
            },
        )
        for decision in result.get("decisions", []):
            await _emit_event(
                session_id,
                "chat.main.decision",
                AgentRole.MAIN,
                str(decision.get("reason") or "主 Agent 路由决策"),
                decision,
            )
        if result.get("failed"):
            raise RuntimeError(str(result.get("error") or "聊天工作流失败"))

        answer = result.get("verified_answer")
        citations = result.get("citations", [])
        if not isinstance(answer, str) or not answer.strip():
            raise RuntimeError("聊天工作流未生成回答")

        async with session_factory() as session:
            assistant = await session.get(ChatMessageRecord, assistant_message_id)
            chat_session = await session.get(ChatSessionRecord, session_id)
            if assistant is None or chat_session is None:
                return
            assistant.content = redact_sensitive_text(answer.strip())
            assistant.status = ChatMessageStatus.COMPLETED.value
            assistant.model_name = settings.effective_chat_model
            assistant.input_tokens = int(result.get("input_tokens", 0))
            assistant.output_tokens = int(result.get("output_tokens", 0))
            for citation in citations:
                if not isinstance(citation, dict):
                    continue
                finding_id = citation.get("id")
                session.add(
                    ChatCitationRecord(
                        message_id=assistant.id,
                        finding_id=UUID(str(finding_id)) if finding_id else None,
                        source_type="finding",
                        file_path=(
                            str(citation["file_path"])
                            if citation.get("file_path")
                            else None
                        ),
                        line=(
                            int(citation["line"])
                            if citation.get("line") is not None
                            else None
                        ),
                        excerpt=(
                            redact_sensitive_text(
                                f"{citation.get('title', '')}: "
                                f"{citation.get('evidence', '')}"
                            )
                        )[:2_000],
                        created_at=datetime.now(UTC),
                    )
                )
            chat_session.status = ChatSessionStatus.ACTIVE.value
            chat_session.updated_at = datetime.now(UTC)
            chat_session.last_message_at = datetime.now(UTC)
            await append_chat_event(
                session,
                session_id,
                "chat.completed",
                AgentRole.MAIN,
                "聊天回答已生成并完成证据校验",
                {
                    "assistant_message_id": str(assistant.id),
                    "citation_count": len(citations),
                },
            )
            await session.commit()
    except Exception as exc:
        await _mark_failed(assistant_message_id, session_id, exc)


async def _resolve_analysis(
    session: AsyncSession,
    chat_session: ChatSessionRecord,
) -> AnalysisRecord | None:
    if chat_session.analysis_id is not None:
        analysis = await session.get(AnalysisRecord, chat_session.analysis_id)
        if analysis is not None:
            return analysis
    return await session.scalar(
        select(AnalysisRecord)
        .where(
            AnalysisRecord.repository_id == chat_session.repository_id,
            AnalysisRecord.status == "completed",
        )
        .order_by(AnalysisRecord.created_at.desc())
        .limit(1)
    )


async def _load_findings(
    session: AsyncSession,
    analysis_id: UUID,
) -> list[FindingRecord]:
    findings = await session.scalars(
        select(FindingRecord)
        .where(FindingRecord.analysis_id == analysis_id)
        .order_by(FindingRecord.created_at)
        .limit(50)
    )
    return list(findings.all())


def _finding_evidence(finding: FindingRecord) -> dict[str, Any]:
    return {
        "id": str(finding.id),
        "category": finding.category,
        "severity": finding.severity,
        "title": redact_sensitive_text(finding.title),
        "file_path": finding.file_path,
        "line": finding.line,
        "evidence": redact_sensitive_text(finding.evidence),
        "impact": redact_sensitive_text(finding.impact),
        "recommendation": redact_sensitive_text(finding.recommendation),
    }


async def _emit_event(
    session_id: UUID,
    event_type: str,
    agent: AgentRole,
    message: str,
    data: dict[str, Any],
) -> None:
    async with get_session_factory()() as session:
        await append_chat_event(
            session,
            session_id,
            event_type,
            agent,
            message,
            data,
        )
        await session.commit()


async def _mark_failed(
    assistant_message_id: UUID,
    session_id: UUID,
    exc: Exception,
) -> None:
    detail = redact_sensitive_text(
        str(exc).strip()[:1_000] or type(exc).__name__
    )
    async with get_session_factory()() as session:
        assistant = await session.get(ChatMessageRecord, assistant_message_id)
        if assistant is not None:
            assistant.status = ChatMessageStatus.FAILED.value
            assistant.content = f"回答生成失败：{detail}"
        await append_chat_event(
            session,
            session_id,
            "chat.failed",
            AgentRole.MAIN,
            f"聊天回答生成失败：{detail}",
            {"error_type": type(exc).__name__},
        )
        await session.commit()
