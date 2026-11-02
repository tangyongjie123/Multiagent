"""HTTP API 使用的请求和响应模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models import RunStatus


class ProjectCreate(BaseModel):
    """创建项目请求。"""

    name: str = Field(min_length=1, max_length=200)
    requirement: str = Field(min_length=10, max_length=20_000)


class ProjectResponse(BaseModel):
    """项目详情。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    requirement: str
    created_at: datetime
    updated_at: datetime


class RunCreate(BaseModel):
    """启动一次 Agent 运行。"""

    additional_context: str | None = Field(default=None, max_length=5_000)


class RunResponse(BaseModel):
    """运行状态。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    status: RunStatus
    current_agent: str | None
    is_simulated: bool
    token_budget: int
    input_tokens: int
    output_tokens: int
    estimated_cost: float
    error_message: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class EventResponse(BaseModel):
    """Agent 事件。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: UUID
    sequence: int
    event_type: str
    agent: str
    message: str
    data: dict[str, Any]
    created_at: datetime


class ArtifactResponse(BaseModel):
    """运行产物元数据。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    run_id: UUID
    kind: str
    name: str
    content_type: str
    sha256: str
    created_at: datetime


class HealthComponent(BaseModel):
    """单个依赖服务的健康状态。"""

    status: Literal["ok", "not_configured", "error"]
    detail: str | None = None


class HealthResponse(BaseModel):
    """平台健康检查响应。"""

    status: Literal["ok", "degraded"]
    version: str
    components: dict[str, HealthComponent]
