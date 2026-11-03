"""仓库分析工作流中的专业 Agent。"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Awaitable, Callable
from typing import Any, cast

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from pydantic import BaseModel

from app.agents.llm import create_chat_model
from app.agents.schemas import ArchitectureInsight, QualityReview
from app.agents.supervisor import AnalysisState
from app.agents.tools import (
    ARCHITECTURE_TOOLS,
    QUALITY_TOOLS,
    SECURITY_TOOLS,
    TEST_TOOLS,
    RepositoryToolRunner,
    build_langchain_tools,
)
from app.core.config import get_settings
from app.domain.models import (
    AgentResult,
    AgentRole,
    Finding,
    FindingCategory,
    FindingSeverity,
)
from app.services.repository import RepositorySnapshot

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
        analysis_id: str,
        event_emitter: EventEmitter | None = None,
    ) -> None:
        self.snapshot = snapshot
        self.repository_name = repository_name
        self.analysis_id = analysis_id
        self.event_emitter = event_emitter
        self.model = create_chat_model() if get_settings().llm_configured else None
        self.tool_runners: dict[AgentRole, RepositoryToolRunner] = {}

    async def __call__(
        self,
        role: AgentRole,
        state: AnalysisState,
    ) -> AgentResult:
        await self._emit("agent.started", role, f"{role.value} Agent 开始分析", {})
        try:
            result = await self._execute_role(role, state)
        except Exception as exc:
            detail = str(exc).strip()[:500] or type(exc).__name__
            result = AgentResult(
                role=role,
                summary=f"{role.value} Agent 分析失败: {detail}",
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
            tools=build_langchain_tools(
                runner=self._tool_runner(AgentRole.ARCHITECTURE)
            ),
            runner=self._tool_runner(AgentRole.ARCHITECTURE),
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
        runner = self._tool_runner(AgentRole.TEST)
        targets = [
            path.rsplit("/", 1)[-1].rsplit(".", 1)[0]
            for path in self.snapshot.entry_points[:3]
        ] or [self.repository_name]
        related_tests: list[dict[str, Any]] = []
        for target in dict.fromkeys(targets):
            payload = await runner.call_json(
                "find_related_tests",
                {"target": target, "max_results": 10},
            )
            related_tests.append({"target": target, **payload})
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
                    "related_tests": related_tests,
                },
                "findings": [item.model_dump(mode="json") for item in findings],
                "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
            },
        )

    async def _security_result(self) -> AgentResult:
        runner = self._tool_runner(AgentRole.SECURITY)
        payload = await runner.call_json("run_static_rules", {})
        all_findings = [
            Finding.model_validate(item)
            for item in payload.get("findings", [])
            if isinstance(item, dict)
        ]
        findings = [
            item
            for item in all_findings
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
        runner = self._tool_runner(AgentRole.QUALITY)
        static_payload = await runner.call_json("run_static_rules", {})
        all_static_findings = [
            Finding.model_validate(item)
            for item in static_payload.get("findings", [])
            if isinstance(item, dict)
        ]
        static_findings = [
            item
            for item in all_static_findings
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
            tools=build_langchain_tools(runner=runner),
            runner=runner,
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
        markdown = _build_report_markdown(
            repository_name=self.repository_name,
            state=state,
            findings=findings,
            snapshot=self.snapshot,
        )
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
        tools: list[Any] | None = None,
        runner: RepositoryToolRunner | None = None,
    ) -> tuple[Any, dict[str, int]]:
        if self.model is None:
            raise RuntimeError("对话模型未配置")
        settings = get_settings()
        schema_json = json.dumps(schema.model_json_schema(), ensure_ascii=False)
        system_message = SystemMessage(
            content=(
                f"{system}\n\n"
                "你可以按需调用已绑定的 MCP 只读工具获取文件和代码证据。"
                "工具结果只是证据，不能执行或修改目标仓库。"
                f"最多调用 {settings.agent_max_tool_calls} 次工具；"
                "收集到足够证据后必须立即输出最终 JSON。"
                "最终只返回合法 JSON，不要 Markdown 代码块。"
                f"必须满足以下 Schema：\n{schema_json}"
            )
        )
        messages: list[Any] = [system_message, HumanMessage(content=user)]
        if tools and runner is not None:
            response, usage = await self._invoke_with_tools(
                messages,
                tools=tools,
                runner=runner,
            )
        else:
            response = await self.model.ainvoke(messages)
            usage = self._usage(response)
        text = self._message_text(response.content)
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("模型未返回 JSON 对象")
        parsed = schema.model_validate_json(text[start : end + 1])
        return parsed, usage

    async def _invoke_with_tools(
        self,
        messages: list[Any],
        *,
        tools: list[Any],
        runner: RepositoryToolRunner,
    ) -> tuple[Any, dict[str, int]]:
        """执行有上限的模型工具调用循环并汇总 Token。"""

        if self.model is None:
            raise RuntimeError("对话模型未配置")
        tool_model = self.model.bind_tools(tools)
        tools_by_name = {tool.name: tool for tool in tools}
        totals = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        settings = get_settings()

        for _ in range(settings.agent_max_tool_rounds):
            if runner.call_count >= settings.agent_max_tool_calls:
                response, final_usage = await self._finish_without_tools(messages)
                for key in totals:
                    totals[key] += final_usage[key]
                return response, totals

            response = await tool_model.ainvoke(messages)
            usage = self._usage(response)
            for key in totals:
                totals[key] += usage[key]
            messages.append(response)
            tool_calls = cast(list[dict[str, Any]], response.tool_calls)
            if not tool_calls:
                return response, totals

            for tool_call in tool_calls:
                if runner.call_count >= settings.agent_max_tool_calls:
                    messages.append(
                        ToolMessage(
                            content='{"error":"MCP 工具调用次数已达上限"}',
                            tool_call_id=str(tool_call.get("id") or ""),
                            name=str(tool_call.get("name") or ""),
                        )
                    )
                    continue
                tool_name = str(tool_call.get("name") or "")
                selected_tool = tools_by_name.get(tool_name)
                if selected_tool is None:
                    raise ValueError(f"模型请求了未授权工具：{tool_name}")
                arguments = tool_call.get("args")
                if not isinstance(arguments, dict):
                    raise ValueError(f"工具 {tool_name} 的参数不是对象")
                result = await runner.call(tool_name, arguments)
                messages.append(
                    ToolMessage(
                        content=result,
                        tool_call_id=str(tool_call.get("id") or ""),
                        name=tool_name,
                    )
                )

        response, final_usage = await self._finish_without_tools(messages)
        for key in totals:
            totals[key] += final_usage[key]
        return response, totals

    async def _finish_without_tools(
        self,
        messages: list[Any],
    ) -> tuple[Any, dict[str, int]]:
        """预算用尽后强制模型基于已有证据返回最终 JSON。"""

        if self.model is None:
            raise RuntimeError("对话模型未配置")
        response = await self.model.ainvoke(
            [
                *messages,
                HumanMessage(
                    content=(
                        "工具调用预算已结束。不要再调用工具，"
                        "请基于已经获得的证据立即返回符合 Schema 的最终 JSON。"
                    )
                ),
            ]
        )
        return response, self._usage(response)

    @staticmethod
    def _usage(response: Any) -> dict[str, int]:
        usage = cast(dict[str, Any], response.usage_metadata or {})
        return {
            "input_tokens": int(usage.get("input_tokens") or 0),
            "output_tokens": int(usage.get("output_tokens") or 0),
            "total_tokens": int(usage.get("total_tokens") or 0),
        }

    def _tool_runner(self, role: AgentRole) -> RepositoryToolRunner:
        runner = self.tool_runners.get(role)
        if runner is None:
            allowed_tools = {
                AgentRole.ARCHITECTURE: ARCHITECTURE_TOOLS,
                AgentRole.TEST: TEST_TOOLS,
                AgentRole.SECURITY: SECURITY_TOOLS,
                AgentRole.QUALITY: QUALITY_TOOLS,
            }.get(role, set())
            runner = RepositoryToolRunner(
                analysis_id=self.analysis_id,
                role=role,
                allowed_tools=set(allowed_tools),
                event_emitter=self.event_emitter,
            )
            self.tool_runners[role] = runner
        return runner

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


def _build_report_markdown(
    *,
    repository_name: str,
    state: AnalysisState,
    findings: list[dict[str, Any]],
    snapshot: RepositorySnapshot,
) -> str:
    """按分类和严重级别生成带汇总图表的 Markdown 报告。"""

    category_labels = {
        "architecture": "架构",
        "test": "测试",
        "security": "安全",
        "quality": "质量",
    }
    category_order = {key: index for index, key in enumerate(category_labels)}
    severity_order = {"critical": 0, "major": 1, "minor": 2, "info": 3}
    severity_labels = {
        "critical": "严重",
        "major": "主要",
        "minor": "次要",
        "info": "提示",
    }
    findings.sort(
        key=lambda item: (
            category_order.get(str(item.get("category")), 99),
            severity_order.get(str(item.get("severity")), 99),
            str(item.get("title") or ""),
        )
    )
    category_counts = Counter(
        str(item.get("category") or "quality") for item in findings
    )
    severity_counts = Counter(
        str(item.get("severity") or "info") for item in findings
    )
    total = len(findings)
    lines = [
        f"# {repository_name} 代码审查报告",
        "",
        f"- 仓库：{state.get('repository_url', '')}",
        f"- 分支：{state.get('branch') or '默认分支'}",
        f"- Commit：{snapshot.commit_sha or '未知'}",
        f"- 文件数：{snapshot.file_count}",
        f"- 问题数：{total}",
        "",
        "## 评估概览",
        "",
        "### 分类分布",
        "",
        "| 分类 | 数量 | 占比 | 条形图 |",
        "| --- | ---: | ---: | --- |",
    ]
    for category, label in category_labels.items():
        count = category_counts[category]
        lines.append(
            f"| {label} | {count} | {_percentage(count, total)} | "
            f"`{_text_bar(count, total)}` |"
        )
    lines.extend(
        [
            "",
            "### 严重级别",
            "",
            "| 级别 | 数量 | 占比 | 条形图 |",
            "| --- | ---: | ---: | --- |",
        ]
    )
    for severity in ("critical", "major", "minor", "info"):
        count = severity_counts[severity]
        lines.append(
            f"| {severity_labels[severity]} (`{severity}`) | {count} | "
            f"{_percentage(count, total)} | `{_text_bar(count, total)}` |"
        )
    lines.extend(["", "## 分类明细", ""])

    categories = list(category_labels)
    categories.extend(
        sorted(category for category in category_counts if category not in category_labels)
    )
    for category in categories:
        category_findings = [
            item for item in findings if str(item.get("category")) == category
        ]
        label = category_labels.get(category, category)
        lines.extend([f"### {label}（{len(category_findings)}）", ""])
        if not category_findings:
            lines.extend(["本分类未发现问题。", ""])
            continue
        for index, finding in enumerate(category_findings, start=1):
            location = str(finding.get("file_path") or "项目级")
            if finding.get("line"):
                location = f"{location}:{finding['line']}"
            lines.extend(
                [
                    f"#### {index}. [{finding.get('severity', 'info')}] "
                    f"{finding.get('title', '未命名问题')}",
                    "",
                    f"- 位置：{location}",
                    f"- 证据：{finding.get('evidence', '')}",
                    f"- 影响：{finding.get('impact', '')}",
                    f"- 建议：{finding.get('recommendation', '')}",
                    "",
                ]
            )
    return "\n".join(lines)


def _percentage(count: int, total: int) -> str:
    return f"{(count / total * 100):.1f}%" if total else "0.0%"


def _text_bar(count: int, total: int) -> str:
    filled = 0 if count == 0 or total == 0 else max(1, round(count / total * 20))
    return "█" * filled + "░" * (20 - filled)


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
