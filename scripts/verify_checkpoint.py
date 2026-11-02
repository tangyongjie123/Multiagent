"""验证 LangGraph 工作流状态能够写入 PostgreSQL checkpoint。"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from app.agents.checkpoint import (
    close_checkpointer,
    get_checkpointer,
    initialize_checkpointer,
)
from app.agents.supervisor import build_supervisor_graph
from app.domain.models import AgentResult, AgentRole


async def executor(role: AgentRole, _: object) -> AgentResult:
    """使用确定性结果验证 checkpoint，不调用外部模型。"""

    return AgentResult(role=role, summary=f"{role.value} checkpoint test")


async def main() -> None:
    await initialize_checkpointer()
    checkpointer = get_checkpointer()
    if checkpointer is None:
        raise RuntimeError("PostgreSQL checkpointer 未初始化")

    graph = build_supervisor_graph(executor, checkpointer=checkpointer)
    thread_id = str(uuid4())
    config = {"configurable": {"thread_id": thread_id}}
    result = await graph.ainvoke(
        {
            "run_id": thread_id,
            "requirement": "验证 PostgreSQL checkpoint",
            "completed_agents": [],
            "results": [],
            "decisions": [],
            "repair_attempts": 0,
            "is_simulated": False,
        },
        config=config,
    )
    snapshot = await checkpointer.aget_tuple(config)
    print(f"thread_id={thread_id}")
    print(f"checkpoint_created={snapshot is not None}")
    print(f"completed_agents={len(result['completed_agents'])}")
    await close_checkpointer()


if __name__ == "__main__":
    asyncio.run(main())
