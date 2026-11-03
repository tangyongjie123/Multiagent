"""Git 仓库分析 API 的请求和响应模型。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models import AnalysisStatus, FindingCategory, FindingSeverity


class RepositoryCreate(BaseModel):
    """添加并克隆 Git 仓库。"""

    url: str = Field(min_length=10, max_length=2_000)
    branch: str | None = Field(default=None, max_length=200)


class RepositoryResponse(BaseModel):
    """仓库信息。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    url: str
    name: str
    branch: str | None
    provider: str
    latest_commit: str | None
    created_at: datetime
    updated_at: datetime


class AnalysisCreate(BaseModel):
    """启动仓库分析。"""

    branch: str | None = Field(default=None, max_length=200)


class AnalysisResponse(BaseModel):
    """分析运行状态。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    repository_id: UUID
    status: AnalysisStatus
    current_agent: str | None
    branch: str | None
    commit_sha: str | None
    summary: str | None
    error_message: str | None
    finding_count: int
    input_tokens: int
    output_tokens: int
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class RepositorySubmission(BaseModel):
    """创建仓库后自动启动分析的响应。"""

    repository: RepositoryResponse
    analysis: AnalysisResponse


class EventResponse(BaseModel):
    """分析事件。"""

    model_config = ConfigDict(from_attributes=True)

    id: int
    analysis_id: UUID
    sequence: int
    event_type: str
    agent: str
    message: str
    data: dict[str, Any]
    created_at: datetime


class FindingResponse(BaseModel):
    """结构化问题。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    analysis_id: UUID
    category: FindingCategory
    severity: FindingSeverity
    title: str
    file_path: str | None
    line: int | None
    evidence: str
    impact: str
    recommendation: str
    created_at: datetime


class ArtifactResponse(BaseModel):
    """分析产物。"""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    analysis_id: UUID
    kind: str
    name: str
    content_type: str
    sha256: str
    created_at: datetime


class HealthComponent(BaseModel):
    """单个依赖服务状态。"""

    status: Literal["ok", "not_configured", "error"]
    detail: str | None = None


class HealthResponse(BaseModel):
    """平台健康检查。"""

    status: Literal["ok", "degraded"]
    version: str
    components: dict[str, HealthComponent]
