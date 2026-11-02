"""使用真实对话模型执行六个专业 Agent。"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any, cast

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from app.agents.llm import create_chat_model
from app.agents.schemas import (
    ArchitectureSpec,
    CodeBundle,
    DocumentationBundle,
    GeneratedFile,
    RequirementSpec,
    ReviewReport,
)
from app.agents.supervisor import WorkflowState
from app.domain.models import AgentResult, AgentRole
from app.services.maven import run_maven_tests
from app.services.workspace import WorkspaceManager

EventEmitter = Callable[
    [str, AgentRole, str, dict[str, Any]],
    Awaitable[None],
]


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


class LLMSpecialistExecutor:
    """主 Agent 可调用的实时专业 Agent 执行器。"""

    def __init__(
        self,
        workspace: WorkspaceManager,
        event_emitter: EventEmitter | None = None,
    ) -> None:
        self.workspace = workspace
        self.event_emitter = event_emitter
        self.model = create_chat_model()

    async def __call__(
        self,
        role: AgentRole,
        state: WorkflowState,
    ) -> AgentResult:
        await self._emit("agent.started", role, f"{role.value} Agent 开始执行", {})
        try:
            result = await self._execute_role(role, state)
        except Exception as exc:
            result = AgentResult(
                role=role,
                summary=f"{role.value} Agent 执行失败: {type(exc).__name__}",
                success=False,
                is_simulated=False,
            )
        event_type = "agent.completed" if result.success else "agent.failed"
        await self._emit(
            event_type,
            role,
            result.summary,
            {
                "success": result.success,
                "artifact_keys": list(result.artifacts),
                "usage": result.artifacts.get("usage", {}),
            },
        )
        return result

    async def _execute_role(
        self,
        role: AgentRole,
        state: WorkflowState,
    ) -> AgentResult:
        if role is AgentRole.PM:
            return await self._run_pm(state)
        if role is AgentRole.ARCHITECT:
            return await self._run_architect(state)
        if role is AgentRole.CODER:
            return await self._run_coder(state)
        if role is AgentRole.TESTER:
            return await self._run_tester(state)
        if role is AgentRole.REVIEWER:
            return await self._run_reviewer(state)
        if role is AgentRole.DOC:
            return await self._run_doc(state)
        raise ValueError(f"不支持的专业 Agent: {role}")

    async def _run_pm(self, state: WorkflowState) -> AgentResult:
        payload, usage = await self._invoke(
            RequirementSpec,
            system=(
                "你是 PM Agent。把用户需求转成可执行、可验收的软件规格。"
                "默认目标是单个 Spring Boot CRUD 后端服务。"
                "不要生成代码，不要扩大为多模块、微服务或前端项目。"
                "任务必须具有稳定 task_id 和明确验收标准。"
            ),
            user=(
                "用户需求：\n"
                f"{state.get('requirement', '')}\n\n"
                "请输出完整需求规格。默认技术栈为 Java 21、Spring Boot 3、"
                "Maven、H2 demo 配置和 JUnit 5。"
            ),
        )
        return AgentResult(
            role=AgentRole.PM,
            summary=payload.summary,
            artifacts={"payload": payload.model_dump(mode="json"), "usage": usage},
        )

    async def _run_architect(self, state: WorkflowState) -> AgentResult:
        payload, usage = await self._invoke(
            ArchitectureSpec,
            system=(
                "你是 Architect Agent。根据需求和 PM 结果设计单体 Spring Boot "
                "REST 服务。必须使用 Java 包名 com.example.task。"
                "实体、接口和错误码必须一致，不得引入未声明依赖。"
                "数据库使用 JPA，demo 环境使用 H2。"
            ),
            user=(
                f"需求：\n{state.get('requirement', '')}\n\n"
                f"PM 规格：\n{_json(self._role_payload(state, AgentRole.PM))}"
            ),
        )
        return AgentResult(
            role=AgentRole.ARCHITECT,
            summary=payload.summary,
            artifacts={"payload": payload.model_dump(mode="json"), "usage": usage},
        )

    async def _run_coder(self, state: WorkflowState) -> AgentResult:
        repair_feedback = {
            "tester": self._role_result(state, AgentRole.TESTER),
            "reviewer": self._role_result(state, AgentRole.REVIEWER),
        }
        repair_instruction = (
            "这是修复轮次。保留已经正确的代码，只输出需要修改的完整文件。"
            if int(state.get("repair_attempts", 0)) > 0
            else ""
        )
        payload, usage = await self._invoke(
            CodeBundle,
            system=(
                "你是 Coder Agent。生成完整、可编译的 Spring Boot 生产代码。"
                "只能生成 src/main/java/com/example/task/ 下的 Java 文件。"
                "包名必须为 com.example.task 或其子包。"
                "禁止生成 pom.xml、启动类、配置文件、README、测试和文档。"
                "禁止使用 Lombok。使用 Jakarta Validation、Spring Data JPA、"
                "标准 Java 21 语法。文件内容必须是完整源码，不是 diff。"
                "OpenAPI 注解仅可使用 @Tag、@Operation、@ApiResponse、"
                "@Parameter 和 @Schema(description=...)，"
                "禁止使用 enumValues 等易变属性。"
            ),
            user=(
                f"需求：\n{state.get('requirement', '')}\n\n"
                f"PM 规格：\n{_json(self._role_payload(state, AgentRole.PM))}\n\n"
                "架构规格：\n"
                f"{_json(self._role_payload(state, AgentRole.ARCHITECT))}\n\n"
                f"修复反馈：\n{_json(repair_feedback)}\n\n"
                f"{repair_instruction}"
            ),
        )
        written_files = self.workspace.write_generated_files(
            payload.files,
            required_prefix="src/main/java/com/example/task/",
        )
        return AgentResult(
            role=AgentRole.CODER,
            summary=payload.summary,
            artifacts={
                "payload": payload.model_dump(mode="json"),
                "usage": usage,
                "written_files": written_files,
            },
        )

    async def _run_tester(self, state: WorkflowState) -> AgentResult:
        architecture = self._role_payload(state, AgentRole.ARCHITECT)
        test_file = self._build_contract_test(architecture)
        written_files = self.workspace.write_generated_files(
            [test_file],
            required_prefix="src/test/java/com/example/task/",
        )
        execution = await run_maven_tests(self.workspace.root)
        summary = (
            f"Maven 测试通过（{execution.command}）"
            if execution.passed
            else f"Maven 测试失败（退出码 {execution.exit_code}）"
        )
        return AgentResult(
            role=AgentRole.TESTER,
            summary=summary,
            success=execution.passed,
            artifacts={
                "payload": {
                    "summary": "根据 REST 契约生成并执行 JUnit 5 集成测试",
                    "files": [test_file.model_dump(mode="json")],
                },
                "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                "written_files": written_files,
                "execution": {
                    "command": execution.command,
                    "exit_code": execution.exit_code,
                    "passed": execution.passed,
                    "output": execution.output,
                    "log_path": execution.log_path,
                },
            },
        )

    @staticmethod
    def _build_contract_test(architecture: dict[str, Any]) -> GeneratedFile:
        """根据接口契约生成只依赖 HTTP 的集成测试。"""

        endpoints = architecture.get("endpoints", [])
        get_path = next(
            (
                item["path"]
                for item in endpoints
                if item.get("method") == "GET" and "{" not in item.get("path", "")
            ),
            None,
        )
        item_path = next(
            (
                item["path"]
                for item in endpoints
                if item.get("method") == "GET" and "{" in item.get("path", "")
            ),
            None,
        )
        post_path = next(
            (item["path"] for item in endpoints if item.get("method") == "POST"),
            None,
        )
        tests = [
            """
    @Test
    void contextLoads() {
        assertNotNull(baseUrl);
    }
""".strip()
        ]
        if get_path:
            tests.append(
                f"""
    @Test
    void listEndpointReturnsSuccess() throws Exception {{
        var response = get("{get_path}");
        assertTrue(response.statusCode() >= 200 && response.statusCode() < 300);
    }}
""".strip()
            )
        if item_path:
            missing_path = item_path.replace(
                "{id}", "00000000-0000-0000-0000-000000000000"
            )
            tests.append(
                f"""
    @Test
    void missingResourceReturnsNotFound() throws Exception {{
        var response = get("{missing_path}");
        assertEquals(404, response.statusCode());
    }}
""".strip()
            )
        if post_path:
            tests.append(
                f"""
    @Test
    void invalidCreateRequestReturnsBadRequest() throws Exception {{
        var request = HttpRequest.newBuilder(URI.create(baseUrl + "{post_path}"))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString("{{}}"))
                .build();
        var response = CLIENT.send(request, HttpResponse.BodyHandlers.ofString());
        assertEquals(400, response.statusCode());
    }}
""".strip()
            )
        source = f"""\
package com.example.task;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class GeneratedApiContractTest {{
    private static final HttpClient CLIENT = HttpClient.newHttpClient();

    @LocalServerPort
    private int port;

    private String baseUrl;

    @BeforeEach
    void setUp() {{
        baseUrl = "http://127.0.0.1:" + port;
    }}

    private HttpResponse<String> get(String path) throws Exception {{
        var request = HttpRequest.newBuilder(URI.create(baseUrl + path)).GET().build();
        return CLIENT.send(request, HttpResponse.BodyHandlers.ofString());
    }}

{chr(10).join(tests)}
}}
"""
        return GeneratedFile(
            path="src/test/java/com/example/task/GeneratedApiContractTest.java",
            content=source,
        )

    async def _run_reviewer(self, state: WorkflowState) -> AgentResult:
        sources = self.workspace.read_java_sources()
        tests = self.workspace.read_java_sources(tests=True)
        tester = self._role_result(state, AgentRole.TESTER)
        execution = (
            (tester or {}).get("artifacts", {}).get("execution", {})
            if tester
            else {}
        )
        payload, usage = await self._invoke(
            ReviewReport,
            system=(
                "你是 Reviewer Agent。检查正确性、安全性、异常处理、接口契约、"
                "测试有效性和跨模块影响。测试未通过时必须 approved=false。"
                "只报告具体问题，必须给出文件级别建议。"
                "README 和使用手册由后续 Doc Agent 生成，不得因为当前尚未生成文档而拒绝。"
                "当前 MVP 采用真实 HTTP 契约集成测试；缺少更细粒度单元测试本身不能作为阻断项。"
            ),
            user=(
                f"需求：\n{state.get('requirement', '')}\n\n"
                f"架构：\n{_json(self._role_payload(state, AgentRole.ARCHITECT))}\n\n"
                f"生产源码：\n{_json(sources)}\n\n"
                f"测试源码：\n{_json(tests)}\n\n"
                f"测试执行：\n{_json(execution)}"
            ),
        )
        blocking = any(item.severity == "blocking" for item in payload.findings)
        approved = payload.approved and not blocking
        return AgentResult(
            role=AgentRole.REVIEWER,
            summary=payload.summary,
            success=approved,
            artifacts={"payload": payload.model_dump(mode="json"), "usage": usage},
        )

    async def _run_doc(self, state: WorkflowState) -> AgentResult:
        source_files = sorted(self.workspace.read_java_sources())
        test_files = sorted(self.workspace.read_java_sources(tests=True))
        payload, usage = await self._invoke(
            DocumentationBundle,
            system=(
                "你是 Doc Agent。根据最终需求、架构、源码文件、测试和评审结果，"
                "生成中文 README、完整中文使用手册和 OpenAPI 3 YAML。"
                "命令、端口、路径和接口必须与项目一致。"
                "使用手册必须包含环境要求、demo 启动、mvn test、停止清理、"
                "接口调用示例和故障排查。"
            ),
            user=(
                f"需求：\n{state.get('requirement', '')}\n\n"
                f"架构：\n{_json(self._role_payload(state, AgentRole.ARCHITECT))}\n\n"
                f"生产文件：{_json(source_files)}\n"
                f"测试文件：{_json(test_files)}\n\n"
                "评审：\n"
                f"{_json(self._role_payload(state, AgentRole.REVIEWER))}"
            ),
        )
        written_files = self.workspace.write_delivery_files(
            readme=payload.readme,
            user_manual=payload.user_manual,
            openapi_yaml=payload.openapi_yaml,
        )
        return AgentResult(
            role=AgentRole.DOC,
            summary=payload.summary,
            artifacts={
                "payload": payload.model_dump(mode="json"),
                "usage": usage,
                "written_files": written_files,
            },
        )

    async def _invoke(
        self,
        schema: type[BaseModel],
        *,
        system: str,
        user: str,
    ) -> tuple[Any, dict[str, int]]:
        schema_json = json.dumps(
            schema.model_json_schema(),
            ensure_ascii=False,
        )
        response = await self.model.ainvoke(
            [
                SystemMessage(
                    content=(
                        f"{system}\n\n只返回一个合法 JSON 对象，不要 Markdown 代码块。"
                        f"JSON 必须满足以下 Schema：\n{schema_json}"
                    )
                ),
                HumanMessage(content=user),
            ]
        )
        text = self._message_text(response.content)
        json_start = text.find("{")
        json_end = text.rfind("}")
        if json_start < 0 or json_end <= json_start:
            raise ValueError("模型未返回 JSON 对象")
        parsed = schema.model_validate_json(text[json_start : json_end + 1])
        raw_usage = cast(dict[str, Any], response.usage_metadata or {})
        usage = {
            "input_tokens": int(raw_usage.get("input_tokens") or 0),
            "output_tokens": int(raw_usage.get("output_tokens") or 0),
            "total_tokens": int(raw_usage.get("total_tokens") or 0),
        }
        return parsed, usage

    @staticmethod
    def _message_text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict) and isinstance(block.get("text"), str):
                    parts.append(block["text"])
            return "\n".join(parts)
        return str(content)

    async def _emit(
        self,
        event_type: str,
        role: AgentRole,
        message: str,
        data: dict[str, Any],
    ) -> None:
        if self.event_emitter is not None:
            await self.event_emitter(event_type, role, message, data)

    @staticmethod
    def _role_result(
        state: WorkflowState,
        role: AgentRole,
    ) -> dict[str, Any] | None:
        for result in reversed(state.get("results", [])):
            if result.get("role") == role.value:
                return cast(dict[str, Any], result)
        return None

    @classmethod
    def _role_payload(
        cls,
        state: WorkflowState,
        role: AgentRole,
    ) -> dict[str, Any]:
        result = cls._role_result(state, role)
        if result is None:
            return {}
        return cast(
            dict[str, Any],
            result.get("artifacts", {}).get("payload", {}),
        )
