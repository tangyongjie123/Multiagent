"""仓库分析 Agent 的结构化输出协议。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.domain.models import Finding


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
