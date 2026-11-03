"""Git 仓库分析使用的领域模型。"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class AgentRole(StrEnum):
    """仓库分析系统中的 Agent 角色。"""

    MAIN = "main"
    REPOSITORY = "repository"
    ARCHITECTURE = "architecture"
    TEST = "test"
    SECURITY = "security"
    QUALITY = "quality"
    REPORT = "report"
    INTENT = "intent"
    CONVERSATION = "conversation"
    EVIDENCE_VERIFIER = "evidence_verifier"


class AnalysisStatus(StrEnum):
    """一次仓库分析的运行状态。"""

    PENDING = "pending"
    CLONING = "cloning"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ChatSessionStatus(StrEnum):
    """聊天会话状态。"""

    ACTIVE = "active"
    ARCHIVED = "archived"


class ChatMessageRole(StrEnum):
    """聊天消息来源。"""

    USER = "user"
    ASSISTANT = "assistant"


class ChatMessageStatus(StrEnum):
    """聊天消息处理状态。"""

    RECORDED = "recorded"
    GENERATING = "generating"
    COMPLETED = "completed"
    FAILED = "failed"


class ChatIntent(StrEnum):
    """Chat Agent 支持的用户意图。"""

    ASK_FOLLOW_UP = "ask_follow_up"
    EXPLAIN_FINDING = "explain_finding"
    REMEDIATION_PLAN = "remediation_plan"
    CLARIFY = "clarify"


class FindingSeverity(StrEnum):
    """问题严重级别。"""

    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    INFO = "info"


class FindingCategory(StrEnum):
    """问题分类。"""

    ARCHITECTURE = "architecture"
    TEST = "test"
    SECURITY = "security"
    QUALITY = "quality"


class AgentResult(BaseModel):
    """专业 Agent 返回给主 Agent 的结构化结果。"""

    role: AgentRole
    summary: str
    artifacts: dict[str, Any] = Field(default_factory=dict)
    success: bool = True
    is_simulated: bool = False


class Finding(BaseModel):
    """一条可定位的代码审查问题。"""

    category: FindingCategory
    severity: FindingSeverity
    title: str
    file_path: str | None = None
    line: int | None = Field(default=None, ge=1)
    evidence: str
    impact: str
    recommendation: str


class AgentEvent(BaseModel):
    """可持久化并实时推送的 Agent 事件。"""

    sequence: int = Field(ge=1)
    event_type: str
    agent: AgentRole
    message: str
    data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
