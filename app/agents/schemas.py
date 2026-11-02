"""六个专业 Agent 的结构化交接协议。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    """拒绝未知字段，保证 Agent 输出稳定。"""

    model_config = ConfigDict(extra="forbid")


class WorkItem(StrictModel):
    """PM 拆分出的实现任务。"""

    task_id: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=2_000)
    acceptance_criteria: list[str] = Field(min_length=1)
    dependencies: list[str] = Field(default_factory=list)


class RequirementSpec(StrictModel):
    """PM Agent 输出的需求规格。"""

    summary: str = Field(min_length=1)
    functional_requirements: list[str] = Field(min_length=1)
    acceptance_criteria: list[str] = Field(min_length=1)
    tasks: list[WorkItem] = Field(min_length=1)
    assumptions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class EntityFieldSpec(StrictModel):
    """数据库实体字段。"""

    name: str
    java_type: str
    nullable: bool = False
    description: str


class EntitySpec(StrictModel):
    """数据库实体设计。"""

    name: str
    table_name: str
    fields: list[EntityFieldSpec] = Field(min_length=1)


class ApiEndpointSpec(StrictModel):
    """REST 接口契约。"""

    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"]
    path: str
    purpose: str
    request_schema: str | None = None
    response_schema: str
    error_codes: list[int] = Field(default_factory=list)


class ArchitectureSpec(StrictModel):
    """Architect Agent 输出的架构规格。"""

    summary: str = Field(min_length=1)
    package_name: str = Field(pattern=r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
    modules: list[str] = Field(min_length=1)
    entities: list[EntitySpec] = Field(min_length=1)
    endpoints: list[ApiEndpointSpec] = Field(min_length=1)
    decisions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class GeneratedFile(StrictModel):
    """Agent 生成或修改的文件。"""

    path: str = Field(min_length=1, max_length=300)
    content: str = Field(min_length=1, max_length=200_000)


class CodeBundle(StrictModel):
    """Coder Agent 输出的生产代码。"""

    summary: str = Field(min_length=1)
    files: list[GeneratedFile] = Field(min_length=1)
    notes: list[str] = Field(default_factory=list)


class TestBundle(StrictModel):
    """Tester Agent 输出的测试代码。"""

    summary: str = Field(min_length=1)
    files: list[GeneratedFile] = Field(min_length=1)
    notes: list[str] = Field(default_factory=list)


class ReviewFinding(StrictModel):
    """Reviewer Agent 的单项评审意见。"""

    severity: Literal["blocking", "major", "minor"]
    file: str | None = None
    line: int | None = Field(default=None, ge=1)
    issue: str = Field(min_length=1)
    recommendation: str = Field(min_length=1)


class ReviewReport(StrictModel):
    """Reviewer Agent 的评审报告。"""

    approved: bool
    summary: str = Field(min_length=1)
    findings: list[ReviewFinding] = Field(default_factory=list)


class DocumentationBundle(StrictModel):
    """Doc Agent 输出的交付文档。"""

    summary: str = Field(min_length=1)
    readme: str = Field(min_length=1)
    user_manual: str = Field(min_length=1)
    openapi_yaml: str = Field(min_length=1)
