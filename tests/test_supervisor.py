"""主 Agent 路由与专业 Agent 调用顺序测试。"""

from __future__ import annotations

import asyncio

from app.agents.supervisor import (
    SPECIALIST_SEQUENCE,
    WorkflowState,
    build_supervisor_graph,
)
from app.domain.models import AgentResult, AgentRole


def test_main_agent_routes_all_specialists_in_order() -> None:
    """主 Agent 必须依次调用六个专业 Agent。"""

    calls: list[AgentRole] = []

    async def executor(role: AgentRole, state: WorkflowState) -> AgentResult:
        calls.append(role)
        return AgentResult(
            role=role,
            summary=f"{role.value} completed",
            artifacts={"requirement_length": len(str(state.get("requirement", "")))},
        )

    graph = build_supervisor_graph(executor)
    result = asyncio.run(
        graph.ainvoke(
            {
                "run_id": "test-run",
                "requirement": "生成一个任务管理 REST API",
                "completed_agents": [],
                "results": [],
                "decisions": [],
                "repair_attempts": 0,
                "max_repair_attempts": 0,
                "is_simulated": False,
            }
        )
    )

    assert calls == list(SPECIALIST_SEQUENCE)
    assert result["completed_agents"] == [role.value for role in SPECIALIST_SEQUENCE]
    assert len(result["decisions"]) == 7
    assert result["decisions"][-1]["action"] == "finish"


def test_main_agent_stops_when_specialist_fails() -> None:
    """专业 Agent 失败后主 Agent 必须停止继续调度。"""

    calls: list[AgentRole] = []

    async def executor(role: AgentRole, _: WorkflowState) -> AgentResult:
        calls.append(role)
        return AgentResult(
            role=role,
            summary="failed",
            success=False,
        )

    graph = build_supervisor_graph(executor)
    result = asyncio.run(
        graph.ainvoke(
            {
                "run_id": "failed-run",
                "requirement": "测试失败停止",
                "completed_agents": [],
                "results": [],
                "decisions": [],
                "repair_attempts": 0,
                "max_repair_attempts": 0,
                "is_simulated": False,
            }
        )
    )

    assert calls == [AgentRole.PM]
    assert result["failed"] is True
    assert result["completed_agents"] == []
    assert result["decisions"][-1]["action"] == "fail"


def test_review_failure_returns_to_coder() -> None:
    """Reviewer 拒绝后主 Agent 必须让 Coder 修复并重新测试。"""

    calls: list[AgentRole] = []
    review_count = 0

    async def executor(role: AgentRole, _: WorkflowState) -> AgentResult:
        nonlocal review_count
        calls.append(role)
        if role is AgentRole.REVIEWER:
            review_count += 1
            return AgentResult(
                role=role,
                summary="review rejected" if review_count == 1 else "approved",
                success=review_count > 1,
            )
        return AgentResult(role=role, summary=f"{role.value} completed")

    graph = build_supervisor_graph(executor)
    result = asyncio.run(
        graph.ainvoke(
            {
                "run_id": "repair-run",
                "requirement": "验证修复循环",
                "completed_agents": [],
                "results": [],
                "decisions": [],
                "repair_attempts": 0,
                "max_repair_attempts": 3,
                "needs_repair": False,
                "last_failed_agent": None,
                "token_budget": 200_000,
                "is_simulated": False,
            }
        )
    )

    assert calls.count(AgentRole.REVIEWER) == 2
    assert calls[calls.index(AgentRole.REVIEWER) + 1] == AgentRole.CODER
    assert result["failed"] is False
    assert result["repair_attempts"] == 1
    assert result["completed_agents"][-1] == AgentRole.DOC.value
