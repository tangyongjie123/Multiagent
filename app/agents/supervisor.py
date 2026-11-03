"""主 Agent 调度的 Git 仓库静态分析工作流。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph

from app.domain.models import AgentResult, AgentRole

SPECIALIST_SEQUENCE = (
    AgentRole.REPOSITORY,
    AgentRole.ARCHITECTURE,
    AgentRole.TEST,
    AgentRole.SECURITY,
    AgentRole.QUALITY,
    AgentRole.REPORT,
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


def _next_role(state: AnalysisState) -> AgentRole | None:
    completed = set(state.get("completed_agents", []))
    for role in SPECIALIST_SEQUENCE:
        if role.value not in completed:
            return role
    return None


def _main_agent_node(state: AnalysisState) -> AnalysisState:
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
    action = state.get("next_action", "fail")
    return END if action in {"finish", "fail"} else action


def build_analysis_graph(executor: Executor, checkpointer: Any = None) -> Any:
    """构建主 Agent 到六个分析 Agent 的状态图。"""

    graph = StateGraph(AnalysisState)
    graph.add_node("main_agent", _main_agent_node)

    for role in SPECIALIST_SEQUENCE:

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
                updated["failed"] = True
                updated["error"] = result.summary
            elif input_tokens + output_tokens > int(
                state.get("token_budget", 120_000)
            ):
                updated["failed"] = True
                updated["error"] = "分析 Token 预算已超限"
            return updated

        graph.add_node(role.value, run_specialist)
        graph.add_edge(role.value, "main_agent")

    graph.add_edge(START, "main_agent")
    graph.add_conditional_edges(
        "main_agent",
        _route_main_agent,
        {
            **{role.value: role.value for role in SPECIALIST_SEQUENCE},
            END: END,
        },
    )
    return graph.compile(checkpointer=checkpointer)
