"""由主 Agent 集中调度六个专业子 Agent 的 LangGraph 工作流。"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph

from app.domain.models import AgentResult, AgentRole

SPECIALIST_SEQUENCE = (
    AgentRole.PM,
    AgentRole.ARCHITECT,
    AgentRole.CODER,
    AgentRole.TESTER,
    AgentRole.REVIEWER,
    AgentRole.DOC,
)


class WorkflowState(TypedDict, total=False):
    """在 LangGraph 节点间传递的可序列化状态。"""

    run_id: str
    requirement: str
    current_agent: str | None
    next_action: str
    completed_agents: list[str]
    results: list[dict[str, Any]]
    decisions: list[dict[str, Any]]
    repair_attempts: int
    max_repair_attempts: int
    needs_repair: bool
    last_failed_agent: str | None
    token_budget: int
    input_tokens: int
    output_tokens: int
    is_simulated: bool
    failed: bool
    error: str | None


class SpecialistExecutor(Protocol):
    """主 Agent 调用的专业 Agent 执行器。"""

    async def __call__(
        self,
        role: AgentRole,
        state: WorkflowState,
    ) -> AgentResult: ...


Executor = SpecialistExecutor | Callable[[AgentRole, WorkflowState], Awaitable[AgentResult]]


def _next_role(state: WorkflowState) -> AgentRole | None:
    completed = set(state.get("completed_agents", []))
    for role in SPECIALIST_SEQUENCE:
        if role.value not in completed:
            return role
    return None


def _main_agent_node(state: WorkflowState) -> WorkflowState:
    """作为唯一调度节点选择下一个合法子 Agent。"""

    if state.get("failed"):
        decision = {
            "sequence": len(state.get("decisions", [])) + 1,
            "agent": AgentRole.MAIN.value,
            "action": "fail",
            "reason": state.get("error") or "专业 Agent 执行失败",
        }
        return {
            **state,
            "current_agent": AgentRole.MAIN.value,
            "next_action": "fail",
            "decisions": [*state.get("decisions", []), decision],
        }

    if state.get("needs_repair"):
        failed_role = state.get("last_failed_agent", AgentRole.CODER.value)
        attempts = int(state.get("repair_attempts", 0))
        max_attempts = int(state.get("max_repair_attempts", 3))
        if attempts > max_attempts:
            decision = {
                "sequence": len(state.get("decisions", [])) + 1,
                "agent": AgentRole.MAIN.value,
                "action": "fail",
                "reason": "修复次数已达到上限",
            }
            return {
                **state,
                "failed": True,
                "error": "修复次数已达到上限",
                "next_action": "fail",
                "decisions": [*state.get("decisions", []), decision],
            }

        repair_target = (
            failed_role
            if failed_role in {AgentRole.PM.value, AgentRole.ARCHITECT.value}
            else AgentRole.CODER.value
        )
        completed = list(state.get("completed_agents", []))
        if repair_target == AgentRole.CODER.value:
            downstream = {
                AgentRole.CODER.value,
                AgentRole.TESTER.value,
                AgentRole.REVIEWER.value,
                AgentRole.DOC.value,
            }
            completed = [agent for agent in completed if agent not in downstream]
        decision = {
            "sequence": len(state.get("decisions", [])) + 1,
            "agent": AgentRole.MAIN.value,
            "action": repair_target,
            "reason": f"处理 {failed_role} 失败，第 {attempts} 次修复",
        }
        return {
            **state,
            "needs_repair": False,
            "next_action": repair_target,
            "completed_agents": completed,
            "decisions": [*state.get("decisions", []), decision],
        }

    next_role = _next_role(state)
    action = next_role.value if next_role is not None else "finish"
    decision = {
        "sequence": len(state.get("decisions", [])) + 1,
        "agent": AgentRole.MAIN.value,
        "action": action,
        "reason": (
            "按当前阶段选择尚未完成的专业 Agent"
            if next_role is not None
            else "所有专业 Agent 已完成"
        ),
    }
    return {
        **state,
        "current_agent": AgentRole.MAIN.value,
        "next_action": action,
        "completed_agents": list(state.get("completed_agents", [])),
        "results": list(state.get("results", [])),
        "decisions": [*state.get("decisions", []), decision],
    }


def _route_main_agent(state: WorkflowState) -> str:
    action = state.get("next_action", "fail")
    return END if action in {"finish", "fail"} else action


def build_supervisor_graph(executor: Executor, checkpointer: Any = None) -> Any:
    """构建主 Agent 到六个专业 Agent 的受控状态图。"""

    graph = StateGraph(WorkflowState)
    graph.add_node("main_agent", _main_agent_node)

    for role in SPECIALIST_SEQUENCE:

        async def run_specialist(
            state: WorkflowState,
            specialist_role: AgentRole = role,
        ) -> WorkflowState:
            result = await executor(specialist_role, state)
            usage = result.artifacts.get("usage", {})
            input_tokens = state.get("input_tokens", 0)
            output_tokens = state.get("output_tokens", 0)
            if isinstance(usage, dict):
                input_tokens += int(usage.get("input_tokens") or 0)
                output_tokens += int(usage.get("output_tokens") or 0)
            completed_agents = list(state.get("completed_agents", []))
            if result.success:
                completed_agents.append(specialist_role.value)
            updated: WorkflowState = {
                **state,
                "current_agent": specialist_role.value,
                "completed_agents": completed_agents,
                "results": [
                    *state.get("results", []),
                    result.model_dump(mode="json"),
                ],
                "is_simulated": bool(state.get("is_simulated") or result.is_simulated),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            }
            if not result.success:
                updated["needs_repair"] = True
                updated["last_failed_agent"] = specialist_role.value
                updated["repair_attempts"] = (
                    int(state.get("repair_attempts", 0)) + 1
                )
                updated["error"] = result.summary
            else:
                updated["failed"] = False
                updated["error"] = None
            if (
                result.success
                and input_tokens + output_tokens
                > int(state.get("token_budget", 200_000))
            ):
                updated["failed"] = True
                updated["error"] = "运行 Token 预算已超限"
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
