"""仓库分析 Agent 的结构化输出协议。"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models import ChatIntent, Finding


class StrictModel(BaseModel):
    """拒绝未知字段。"""

    model_config = ConfigDict(extra="forbid")


class ArchitectureInsight(StrictModel):
    """Architecture Agent 输出。"""

    summary: str
    tech_stack: list[str] = Field(default_factory=list)
    modules: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class QualityReview(StrictModel):
    """Quality Agent 输出。"""

    summary: str
    findings: list[Finding] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)


class AnalysisReport(StrictModel):
    """Report Agent 输出。"""

    summary: str
    markdown: str


class ChatIntentResult(StrictModel):
    """Intent Agent 的结构化输出。"""

    intent: ChatIntent
    reason: str
    target_finding_id: UUID | None = None


class ConversationAnswer(StrictModel):
    """Conversation Agent 的结构化输出。"""

    answer: str
    cited_finding_ids: list[UUID] = Field(default_factory=list)
    insufficient_evidence: bool = False
