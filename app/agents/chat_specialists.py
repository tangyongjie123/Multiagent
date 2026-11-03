"""聊天场景中的 Intent、Conversation 和 Evidence Verifier Agent。"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any, cast

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from app.agents.llm import create_chat_model
from app.agents.prompts import CONVERSATION_SYSTEM_PROMPT, INTENT_SYSTEM_PROMPT
from app.agents.schemas import ChatIntentResult, ConversationAnswer
from app.agents.supervisor import ChatState
from app.domain.models import AgentResult, AgentRole, ChatIntent

EventEmitter = Callable[
    [str, AgentRole, str, dict[str, Any]],
    Awaitable[None],
]


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


class ChatAgentExecutor:
    """执行聊天意图识别、回答生成和证据校验。"""

    def __init__(self, event_emitter: EventEmitter | None = None) -> None:
        self.model = create_chat_model()
        self.event_emitter = event_emitter

    async def __call__(
        self,
        role: AgentRole,
        state: ChatState,
    ) -> AgentResult:
        await self._emit("chat.agent.started", role, f"{role.value} Agent 开始处理", {})
        try:
            if role is AgentRole.INTENT:
                result = await self._intent_result(state)
            elif role is AgentRole.CONVERSATION:
                result = await self._conversation_result(state)
            elif role is AgentRole.EVIDENCE_VERIFIER:
                result = await self._verify_result(state)
            else:
                raise ValueError(f"不支持的聊天 Agent: {role}")
        except Exception as exc:
            detail = str(exc).strip()[:500] or type(exc).__name__
            result = AgentResult(
                role=role,
                summary=f"{role.value} Agent 处理失败: {detail}",
                success=False,
            )
        await self._emit(
            "chat.agent.completed" if result.success else "chat.agent.failed",
            role,
            result.summary,
            {
                "success": result.success,
                "usage": result.artifacts.get("usage", {}),
            },
        )
        return result

    async def _intent_result(self, state: ChatState) -> AgentResult:
        intent, usage = await self._invoke(
            ChatIntentResult,
            system=INTENT_SYSTEM_PROMPT,
            user=(
                f"仓库：{state.get('repository_name', '')}\n"
                f"分析摘要：{state.get('analysis_summary') or '暂无'}\n"
                f"可用证据：{_json(state.get('evidence', []))}\n"
                f"用户消息：{state.get('user_content', '')}"
            ),
        )
        return AgentResult(
            role=AgentRole.INTENT,
            summary=f"识别聊天意图：{intent.intent.value}",
            artifacts={
                "payload": intent.model_dump(mode="json"),
                "usage": usage,
            },
        )

    async def _conversation_result(self, state: ChatState) -> AgentResult:
        answer, usage = await self._invoke(
            ConversationAnswer,
            system=CONVERSATION_SYSTEM_PROMPT,
            user=(
                f"仓库：{state.get('repository_name', '')}\n"
                f"意图：{state.get('intent') or ChatIntent.ASK_FOLLOW_UP.value}\n"
                f"分析摘要：{state.get('analysis_summary') or '暂无'}\n"
                f"历史消息：{_json(state.get('history', []))}\n"
                f"可用证据：{_json(state.get('evidence', []))}\n"
                f"用户问题：{state.get('user_content', '')}"
            ),
        )
        return AgentResult(
            role=AgentRole.CONVERSATION,
            summary="生成基于分析证据的聊天回答",
            artifacts={
                "payload": answer.model_dump(mode="json"),
                "usage": usage,
            },
        )

    async def _verify_result(self, state: ChatState) -> AgentResult:
        payload = state.get("conversation")
        if not isinstance(payload, dict):
            raise ValueError("缺少 Conversation Agent 输出")
        answer = ConversationAnswer.model_validate(payload)
        if not answer.answer.strip():
            raise ValueError("回答内容为空")

        evidence_by_id = {
            str(item.get("id")): item
            for item in state.get("evidence", [])
            if item.get("id")
        }
        citations = [
            evidence_by_id[finding_id]
            for finding_id in dict.fromkeys(str(item) for item in answer.cited_finding_ids)
            if finding_id in evidence_by_id
        ]
        final_answer = answer.answer.strip()
        if answer.insufficient_evidence or not citations:
            note = (
                "当前回答没有找到可直接引用的分析证据，请结合现有报告谨慎判断。"
                if evidence_by_id
                else "当前仓库还没有可用的审查 Finding，无法提供有证据的代码结论。"
            )
            if note not in final_answer:
                final_answer = f"{final_answer}\n\n> {note}"
        return AgentResult(
            role=AgentRole.EVIDENCE_VERIFIER,
            summary=f"证据校验完成，引用 {len(citations)} 条 Finding",
            artifacts={
                "payload": {
                    "answer": final_answer,
                    "citations": citations,
                    "insufficient_evidence": answer.insufficient_evidence,
                },
                "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            },
        )

    async def _invoke(
        self,
        schema: type[BaseModel],
        *,
        system: str,
        user: str,
    ) -> tuple[Any, dict[str, int]]:
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        response = await self.model.ainvoke(
            [
                SystemMessage(
                    content=(
                        f"{system}\n\n只返回合法 JSON，不要 Markdown 代码围栏。"
                        f"必须满足以下 Schema：\n{schema_json}"
                    )
                ),
                HumanMessage(content=user),
            ]
        )
        text = self._message_text(response.content)
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("模型未返回 JSON 对象")
        parsed = schema.model_validate_json(text[start : end + 1])
        usage = cast(dict[str, Any], response.usage_metadata or {})
        return parsed, {
            "input_tokens": int(usage.get("input_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
        }

    @staticmethod
    def _message_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(
                str(item.get("text", "")) if isinstance(item, dict) else str(item)
                for item in content
            )
        return str(content)

    async def _emit(
        self,
        event_type: str,
        role: AgentRole,
        message: str,
        data: dict[str, Any],
    ) -> None:
        if self.event_emitter is not None:
            await self.event_emitter(event_type, role, message, data)
