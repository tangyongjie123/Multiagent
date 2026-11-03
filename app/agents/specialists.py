"""仓库分析工作流中的专业 Agent。"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any, cast

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from app.agents.llm import create_chat_model
from app.agents.schemas import ArchitectureInsight, QualityReview
from app.agents.supervisor import AnalysisState
from app.core.config import get_settings
from app.domain.models import (
    AgentResult,
    AgentRole,
    Finding,
    FindingCategory,
    FindingSeverity,
)
from app.services.repository import RepositorySnapshot
from app.services.static_analysis import run_static_analysis

EventEmitter = Callable[
    [str, AgentRole, str, dict[str, Any]],
    Awaitable[None],
]


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


class RepositoryAnalysisExecutor:
    """执行只读仓库分析，不修改被审查仓库。"""

    def __init__(
        self,
        snapshot: RepositorySnapshot,
        repository_name: str,
        event_emitter: EventEmitter | None = None,
    ) -> None:
        self.snapshot = snapshot
        self.repository_name = repository_name
        self.event_emitter = event_emitter
        self.model = create_chat_model() if get_settings().llm_configured else None
        self.static_findings = run_static_analysis(snapshot)

    async def __call__(
        self,
        role: AgentRole,
        state: AnalysisState,
    ) -> AgentResult:
        await self._emit("agent.started", role, f"{role.value} Agent 开始分析", {})
        try:
            result = await self._execute_role(role, state)
        except Exception as exc:
            result = AgentResult(
                role=role,
                summary=f"{role.value} Agent 分析失败: {type(exc).__name__}",
                success=False,
            )
        await self._emit(
            "agent.completed" if result.success else "agent.failed",
            role,
            result.summary,
            {
                "success": result.success,
                "usage": result.artifacts.get("usage", {}),
                "finding_count": len(result.artifacts.get("findings", [])),
            },
        )
        return result

    async def _execute_role(
        self,
        role: AgentRole,
        state: AnalysisState,
    ) -> AgentResult:
        if role is AgentRole.REPOSITORY:
            return await self._repository_result()
        if role is AgentRole.ARCHITECTURE:
            return await self._architecture_result()
        if role is AgentRole.TEST:
            return await self._test_result()
        if role is AgentRole.SECURITY:
            return await self._security_result()
        if role is AgentRole.QUALITY:
            return await self._quality_result()
        if role is AgentRole.REPORT:
            return await self._report_result(state)
        raise ValueError(f"不支持的 Agent: {role}")

    async def _repository_result(self) -> AgentResult:
        languages = "、".join(
            f"{name} {count}" for name, count in self.snapshot.languages.items()
        ) or "未识别"
        summary = (
            f"已扫描 {self.snapshot.file_count} 个文件，共 "
            f"{self.snapshot.total_bytes / 1024 / 1024:.2f} MB；"
            f"主要语言：{languages}。"
        )
        return AgentResult(
            role=AgentRole.REPOSITORY,
            summary=summary,
            artifacts={
                "snapshot": self.snapshot.to_dict(),
                "findings": [],
                "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            },
        )

    async def _architecture_result(self) -> AgentResult:
        if self.model is None:
            raise RuntimeError("对话模型未配置")
        payload, usage = await self._invoke(
            ArchitectureInsight,
            system=(
                "你是 Architecture Agent，只分析现有代码，不生成或修改代码。"
                "根据文件树、构建文件和源码摘要识别技术栈、模块、分层问题、"
                "循环依赖风险和架构改进建议。"
            ),
            user=(
                f"仓库：{self.repository_name}\n"
                f"扫描摘要：{_json(self.snapshot.to_dict())}\n\n"
                f"源码摘要：{_json(self._source_excerpt(10))}"
            ),
        )
        return AgentResult(
            role=AgentRole.ARCHITECTURE,
            summary=payload.summary,
            artifacts={
                "payload": payload.model_dump(mode="json"),
                "findings": [
                    item.model_dump(mode="json") for item in payload.findings
                ],
                "usage": usage,
            },
        )

    async def _test_result(self) -> AgentResult:
        test_count = len(self.snapshot.test_files)
        framework_haystack = "\n".join(
            self.snapshot.source_files.get(path, "")
            for path in self.snapshot.build_files
        ).lower()
        frameworks = [
            label
            for label, marker in (
                ("JUnit", "junit"),
                ("Pytest", "pytest"),
                ("Jest", '"jest"'),
                ("Vitest", '"vitest"'),
                ("Spring Boot Test", "spring-boot-starter-test"),
            )
            if marker in framework_haystack
        ]
        findings: list[Finding] = []
        if test_count == 0:
            findings.append(
                Finding(
                    category=FindingCategory.TEST,
                    severity=FindingSeverity.MAJOR,
                    title="未识别到自动化测试",
                    evidence="仓库扫描未发现测试文件。",
                    impact="核心业务逻辑缺少回归保护。",
                    recommendation="补充 Service 单元测试和 API 集成测试。",
                )
            )
        return AgentResult(
            role=AgentRole.TEST,
            summary=f"发现 {test_count} 个测试相关文件。",
            artifacts={
                "payload": {
                    "test_files": self.snapshot.test_files,
                    "frameworks": frameworks,
                    "executed": False,
                },
                "findings": [item.model_dump(mode="json") for item in findings],
                "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            },
        )

    async def _security_result(self) -> AgentResult:
        findings = [
            item
            for item in self.static_findings
            if item.category is FindingCategory.SECURITY
        ]
        return AgentResult(
            role=AgentRole.SECURITY,
            summary=f"静态安全检查发现 {len(findings)} 个问题。",
            artifacts={
                "findings": [item.model_dump(mode="json") for item in findings],
                "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            },
        )

    async def _quality_result(self) -> AgentResult:
        static_findings = [
            item
            for item in self.static_findings
            if item.category in {FindingCategory.QUALITY, FindingCategory.TEST}
        ]
        if self.model is None:
            raise RuntimeError("对话模型未配置")
        payload, usage = await self._invoke(
            QualityReview,
            system=(
                "你是 Quality Agent。只分析现有代码，不修改代码。"
                "检查异常处理、资源释放、输入校验、可维护性、重复代码、"
                "并发风险和明显缺陷。每条问题必须包含文件位置或可验证证据。"
            ),
            user=(
                f"仓库：{self.repository_name}\n"
                f"确定性规则结果："
                f"{_json([item.model_dump(mode='json') for item in static_findings])}\n\n"
                f"源码摘要：{_json(self._source_excerpt(8))}"
            ),
        )
        findings = [*static_findings, *payload.findings]
        return AgentResult(
            role=AgentRole.QUALITY,
            summary=payload.summary,
            artifacts={
                "payload": payload.model_dump(mode="json"),
                "findings": [item.model_dump(mode="json") for item in findings],
                "usage": usage,
            },
        )

    async def _report_result(self, state: AnalysisState) -> AgentResult:
        findings = self._collect_findings(state.get("results", []))
        severity_order = {"critical": 0, "major": 1, "minor": 2, "info": 3}
        findings.sort(
            key=lambda item: (
                severity_order.get(str(item.get("severity")), 9),
                str(item.get("title") or ""),
            )
        )
        lines = [
            f"# {self.repository_name} 代码审查报告",
            "",
            f"- 仓库：{state.get('repository_url', '')}",
            f"- 分支：{state.get('branch') or '默认分支'}",
            f"- Commit：{self.snapshot.commit_sha or '未知'}",
            f"- 文件数：{self.snapshot.file_count}",
            f"- 问题数：{len(findings)}",
            "",
            "## 问题清单",
            "",
        ]
        if not findings:
            lines.append("未发现需要报告的问题。")
        for index, finding in enumerate(findings, start=1):
            location = finding.get("file_path") or "项目级"
            if finding.get("line"):
                location = f"{location}:{finding['line']}"
            lines.extend(
                [
                    f"### {index}. [{finding.get('severity', 'info')}] "
                    f"{finding.get('title', '未命名问题')}",
                    "",
                    f"- 分类：{finding.get('category', 'quality')}",
                    f"- 位置：{location}",
                    f"- 证据：{finding.get('evidence', '')}",
                    f"- 影响：{finding.get('impact', '')}",
                    f"- 建议：{finding.get('recommendation', '')}",
                    "",
                ]
            )
        markdown = "\n".join(lines)
        return AgentResult(
            role=AgentRole.REPORT,
            summary=f"生成 Markdown 审查报告，共 {len(findings)} 个问题。",
            artifacts={
                "payload": {
                    "summary": f"{self.repository_name} 静态分析完成",
                    "markdown": markdown,
                },
                "findings": findings,
                "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            },
        )

    async def _invoke(
        self,
        schema: type[BaseModel],
        *,
        system: str,
        user: str,
    ) -> tuple[Any, dict[str, int]]:
        if self.model is None:
            raise RuntimeError("对话模型未配置")
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        response = await self.model.ainvoke(
            [
                SystemMessage(
                    content=(
                        f"{system}\n\n只返回合法 JSON，不要 Markdown 代码块。"
                        f"必须满足以下 Schema：\n{schema_json}"
                    )
                ),
                HumanMessage(content=user),
            ]
        )
        text = self._message_text(response.content)
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("模型未返回 JSON 对象")
        parsed = schema.model_validate_json(text[start : end + 1])
        usage = cast(dict[str, Any], response.usage_metadata or {})
        return parsed, {
            "input_tokens": int(usage.get("input_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
        }

    @staticmethod
    def _message_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(
                str(item.get("text", "")) if isinstance(item, dict) else str(item)
                for item in content
            )
        return str(content)

    def _source_excerpt(self, limit: int) -> dict[str, str]:
        selected: dict[str, str] = {}
        ordered = sorted(
            self.snapshot.source_files.items(),
            key=lambda item: (_source_priority(item[0]), item[0]),
        )
        for path, content in ordered:
            if len(selected) >= limit:
                break
            selected[path] = content[:4_000]
        return selected

    @staticmethod
    def _collect_findings(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        seen: set[tuple[Any, ...]] = set()
        for result in results:
            artifacts = result.get("artifacts", {})
            for finding in artifacts.get("findings", []):
                if not isinstance(finding, dict):
                    continue
                key = (
                    finding.get("category"),
                    finding.get("severity"),
                    finding.get("title"),
                    finding.get("file_path"),
                    finding.get("line"),
                    finding.get("evidence"),
                )
                if key not in seen:
                    seen.add(key)
                    findings.append(finding)
        return findings

    async def _emit(
        self,
        event_type: str,
        role: AgentRole,
        message: str,
        data: dict[str, Any],
    ) -> None:
        if self.event_emitter is not None:
            await self.event_emitter(event_type, role, message, data)


def _source_priority(path: str) -> int:
    """让模型优先读取主源码，而不是测试和构建配置。"""

    lowered = path.lower()
    if "src/main/" in lowered:
        return 0
    if "/test/" in lowered or lowered.endswith(("test.java", "tests.py")):
        return 3
    if lowered.endswith(
        (".java", ".kt", ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".cs")
    ):
        return 1
    return 2
