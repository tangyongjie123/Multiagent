"""主 Agent 调度的 Git 仓库静态分析工作流。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph

from app.domain.models import AgentResult, AgentRole

# 主 Agent 只能按此顺序选择专业 Agent，避免模型自行跳步或无限调度。
SPECIALIST_SEQUENCE = (
    AgentRole.REPOSITORY,
    AgentRole.ARCHITECTURE,
    AgentRole.TEST,
    AgentRole.SECURITY,
    AgentRole.QUALITY,
    AgentRole.REPORT,
)
CHAT_SPECIALIST_SEQUENCE = (
    AgentRole.INTENT,
    AgentRole.CONVERSATION,
    AgentRole.EVIDENCE_VERIFIER,
)


class AnalysisState(TypedDict, total=False):
    """在 LangGraph 节点间传递的分析状态。"""

    analysis_id: str
    repository_url: str
    branch: str | None
    repo_path: str
    current_agent: str | None
    next_action: str
    completed_agents: list[str]
    results: list[dict[str, Any]]
    decisions: list[dict[str, Any]]
    input_tokens: int
    output_tokens: int
    token_budget: int
    failed: bool
    error: str | None


class ChatState(TypedDict, total=False):
    """主 Agent 编排聊天专业 Agent 时使用的状态。"""

    session_id: str
    user_content: str
    repository_name: str
    analysis_summary: str | None
    history: list[dict[str, str]]
    evidence: list[dict[str, Any]]
    intent: str | None
    conversation: dict[str, Any] | None
    verified_answer: str | None
    citations: list[dict[str, Any]]
    current_agent: str | None
    next_action: str
    completed_agents: list[str]
    results: list[dict[str, Any]]
    decisions: list[dict[str, Any]]
    input_tokens: int
    output_tokens: int
    token_budget: int
    failed: bool
    error: str | None


class SpecialistExecutor(Protocol):
    """专业 Agent 执行器。"""

    async def __call__(
        self,
        role: AgentRole,
        state: AnalysisState,
    ) -> AgentResult: ...


Executor = SpecialistExecutor | Callable[
    [AgentRole, AnalysisState],
    Awaitable[AgentResult],
]


class ChatSpecialistExecutor(Protocol):
    """聊天专业 Agent 执行器。"""

    async def __call__(
        self,
        role: AgentRole,
        state: ChatState,
    ) -> AgentResult: ...


ChatExecutor = ChatSpecialistExecutor | Callable[
    [AgentRole, ChatState],
    Awaitable[AgentResult],
]


def _next_role(state: AnalysisState) -> AgentRole | None:
    """返回序列中第一个尚未完成的专业 Agent。"""

    completed = set(state.get("completed_agents", []))
    for role in SPECIALIST_SEQUENCE:
        if role.value not in completed:
            return role
    return None


def _main_agent_node(state: AnalysisState) -> AnalysisState:
    """执行主 Agent 的确定性路由。

    主 Agent 当前不调用大模型，也没有系统提示词。它只检查失败标记、已完成
    角色和 Token 预算，并从 LangGraph 允许的动作中选择下一步。
    """

    if state.get("failed"):
        action = "fail"
        reason = state.get("error") or "专业 Agent 执行失败"
    else:
        next_role = _next_role(state)
        action = next_role.value if next_role is not None else "finish"
        reason = (
            "选择下一个未完成的分析 Agent"
            if next_role is not None
            else "所有分析 Agent 已完成"
        )
    decision = {
        "sequence": len(state.get("decisions", [])) + 1,
        "agent": AgentRole.MAIN.value,
        "action": action,
        "reason": reason,
    }
    return {
        **state,
        "current_agent": AgentRole.MAIN.value,
        "next_action": action,
        "decisions": [*state.get("decisions", []), decision],
    }


def _route_main_agent(state: AnalysisState) -> str:
    """把主 Agent 的下一步动作转换为 LangGraph 条件边目标。"""

    action = state.get("next_action", "fail")
    return END if action in {"finish", "fail"} else action


def build_analysis_graph(executor: Executor, checkpointer: Any = None) -> Any:
    """构建主 Agent 到六个分析 Agent 的状态图。

    每个专业 Agent 完成后都会返回主 Agent，由主 Agent 决定继续、失败或结束。
    checkpointer 用于恢复节点状态，不参与业务结果判断。
    """

    graph = StateGraph(AnalysisState)
    graph.add_node("main_agent", _main_agent_node)

    for role in SPECIALIST_SEQUENCE:

        # 使用默认参数捕获当前 role，避免闭包在循环结束后全部引用最后一个角色。
        async def run_specialist(
            state: AnalysisState,
            specialist_role: AgentRole = role,
        ) -> AnalysisState:
            result = await executor(specialist_role, state)
            usage = result.artifacts.get("usage", {})
            input_tokens = int(state.get("input_tokens", 0))
            output_tokens = int(state.get("output_tokens", 0))
            if isinstance(usage, dict):
                input_tokens += int(usage.get("input_tokens") or 0)
                output_tokens += int(usage.get("output_tokens") or 0)

            completed = list(state.get("completed_agents", []))
            if result.success:
                completed.append(specialist_role.value)
            updated: AnalysisState = {
                **state,
                "current_agent": specialist_role.value,
                "completed_agents": completed,
                "results": [
                    *state.get("results", []),
                    result.model_dump(mode="json"),
                ],
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            }
            if not result.success:
                # 子 Agent 失败由主 Agent 统一终止，不能悄悄继续后续步骤。
                updated["failed"] = True
                updated["error"] = result.summary
            elif input_tokens + output_tokens > int(
                state.get("token_budget", 120_000)
            ):
                # 预算超限属于工作流失败，避免继续产生不可控成本。
                updated["failed"] = True
                updated["error"] = "分析 Token 预算已超限"
            return updated

        graph.add_node(role.value, run_specialist)
        graph.add_edge(role.value, "main_agent")

    graph.add_edge(START, "main_agent")
    # 条件边只暴露已声明的 Agent 枚举和结束节点。
    graph.add_conditional_edges(
        "main_agent",
        _route_main_agent,
        {
            **{role.value: role.value for role in SPECIALIST_SEQUENCE},
            END: END,
        },
    )
    return graph.compile(checkpointer=checkpointer)


def _next_chat_role(state: ChatState) -> AgentRole | None:
    completed = set(state.get("completed_agents", []))
    for role in CHAT_SPECIALIST_SEQUENCE:
        if role.value not in completed:
            return role
    return None


def _chat_main_agent_node(state: ChatState) -> ChatState:
    """聊天场景的主 Agent 确定性路由。"""

    if state.get("failed"):
        action = "fail"
        reason = state.get("error") or "聊天专业 Agent 执行失败"
    else:
        next_role = _next_chat_role(state)
        action = next_role.value if next_role is not None else "finish"
        reason = (
            "选择下一个未完成的聊天 Agent"
            if next_role is not None
            else "所有聊天 Agent 已完成"
        )
    decision = {
        "sequence": len(state.get("decisions", [])) + 1,
        "agent": AgentRole.MAIN.value,
        "action": action,
        "reason": reason,
    }
    return {
        **state,
        "current_agent": AgentRole.MAIN.value,
        "next_action": action,
        "decisions": [*state.get("decisions", []), decision],
    }


def _route_chat_main_agent(state: ChatState) -> str:
    action = state.get("next_action", "fail")
    return END if action in {"finish", "fail"} else action


def build_chat_graph(executor: ChatExecutor, checkpointer: Any = None) -> Any:
    """构建聊天场景的主 Agent 与三个专业 Agent。"""

    graph = StateGraph(ChatState)
    graph.add_node("main_agent", _chat_main_agent_node)

    for role in CHAT_SPECIALIST_SEQUENCE:

        async def run_chat_specialist(
            state: ChatState,
            specialist_role: AgentRole = role,
        ) -> ChatState:
            result = await executor(specialist_role, state)
            usage = result.artifacts.get("usage", {})
            input_tokens = int(state.get("input_tokens", 0))
            output_tokens = int(state.get("output_tokens", 0))
            if isinstance(usage, dict):
                input_tokens += int(usage.get("input_tokens") or 0)
                output_tokens += int(usage.get("output_tokens") or 0)
            completed = list(state.get("completed_agents", []))
            if result.success:
                completed.append(specialist_role.value)
            updated: ChatState = {
                **state,
                "current_agent": specialist_role.value,
                "completed_agents": completed,
                "results": [
                    *state.get("results", []),
                    result.model_dump(mode="json"),
                ],
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            }
            payload = result.artifacts.get("payload")
            if result.success and isinstance(payload, dict):
                if specialist_role is AgentRole.INTENT:
                    updated["intent"] = str(payload.get("intent") or "")
                elif specialist_role is AgentRole.CONVERSATION:
                    updated["conversation"] = payload
                elif specialist_role is AgentRole.EVIDENCE_VERIFIER:
                    updated["verified_answer"] = str(payload.get("answer") or "")
                    citations = payload.get("citations")
                    updated["citations"] = citations if isinstance(citations, list) else []
            if not result.success:
                updated["failed"] = True
                updated["error"] = result.summary
            elif input_tokens + output_tokens > int(
                state.get("token_budget", 60_000)
            ):
                updated["failed"] = True
                updated["error"] = "聊天 Token 预算已超限"
            return updated

        graph.add_node(role.value, run_chat_specialist)
        graph.add_edge(role.value, "main_agent")

    graph.add_edge(START, "main_agent")
    graph.add_conditional_edges(
        "main_agent",
        _route_chat_main_agent,
        {
            **{role.value: role.value for role in CHAT_SPECIALIST_SEQUENCE},
            END: END,
        },
    )
    return graph.compile(checkpointer=checkpointer)
