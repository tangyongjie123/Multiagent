"""仓库分析主 Agent 调度测试。"""

from __future__ import annotations

import asyncio

from app.agents.supervisor import (
    SPECIALIST_SEQUENCE,
    AnalysisState,
    build_analysis_graph,
)
from app.domain.models import AgentResult, AgentRole


def test_main_agent_runs_all_analysis_roles() -> None:
    calls: list[AgentRole] = []

    async def executor(role: AgentRole, _: AnalysisState) -> AgentResult:
        calls.append(role)
        return AgentResult(role=role, summary=f"{role.value} completed")

    graph = build_analysis_graph(executor)
    result = asyncio.run(
        graph.ainvoke(
            {
                "analysis_id": "analysis-1",
                "repository_url": "https://github.com/example/repo.git",
                "branch": "main",
                "repo_path": "/tmp/repo",
                "completed_agents": [],
                "results": [],
                "decisions": [],
                "input_tokens": 0,
                "output_tokens": 0,
                "token_budget": 120_000,
            }
        )
    )

    assert calls == list(SPECIALIST_SEQUENCE)
    assert result["completed_agents"] == [
        role.value for role in SPECIALIST_SEQUENCE
    ]
    assert result["decisions"][-1]["action"] == "finish"


def test_main_agent_stops_after_agent_failure() -> None:
    async def executor(role: AgentRole, _: AnalysisState) -> AgentResult:
        return AgentResult(role=role, summary="analysis failed", success=False)

    graph = build_analysis_graph(executor)
    result = asyncio.run(
        graph.ainvoke(
            {
                "analysis_id": "analysis-2",
                "repository_url": "https://github.com/example/repo.git",
                "completed_agents": [],
                "results": [],
                "decisions": [],
                "input_tokens": 0,
                "output_tokens": 0,
                "token_budget": 120_000,
            }
        )
    )

    assert result["failed"] is True
    assert result["completed_agents"] == []
