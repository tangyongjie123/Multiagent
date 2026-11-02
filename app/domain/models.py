"""Agent 工作流使用的领域模型。"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AgentRole(StrEnum):
    """系统中的 Agent 角色。"""

    MAIN = "main"
    PM = "pm"
    ARCHITECT = "architect"
    CODER = "coder"
    TESTER = "tester"
    REVIEWER = "reviewer"
    DOC = "doc"


class RunStatus(StrEnum):
    """工作流运行状态。"""

    PENDING = "pending"
    RUNNING = "running"
    WAITING_REQUIREMENT = "waiting_requirement"
    WAITING_BUDGET = "waiting_budget"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentResult(BaseModel):
    """专业 Agent 返回给主 Agent 的结构化结果。"""

    role: AgentRole
    summary: str
    artifacts: dict[str, Any] = Field(default_factory=dict)
    success: bool = True
    is_simulated: bool = False


class AgentEvent(BaseModel):
    """可在前端展示的 Agent 运行事件。"""

    sequence: int = Field(ge=1)
    event_type: str
    agent: AgentRole
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class WorkflowResult(BaseModel):
    """一次完整 Agent 工作流的执行结果。"""

    run_id: str
    project_name: str
    requirement: str
    status: RunStatus
    completed_agents: list[AgentRole]
    results: list[AgentResult]
    events: list[AgentEvent]
    is_simulated: bool
