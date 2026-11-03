"""把受控 MCP 工具包装成 LangChain StructuredTool。"""

from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import uuid4

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.domain.models import AgentRole
from app.mcp.client import call_mcp_tool

EventEmitter = Callable[
    [str, AgentRole, str, dict[str, Any]],
    Awaitable[None],
]

ARCHITECTURE_TOOLS = {
    "list_repository_tree",
    "read_repository_file",
    "search_repository_code",
}
QUALITY_TOOLS = {
    "read_repository_file",
    "search_repository_code",
    "run_static_rules",
}
TEST_TOOLS = {"find_related_tests"}
SECURITY_TOOLS = {"run_static_rules"}


class ListTreeInput(BaseModel):
    """仓库目录工具参数。"""

    max_entries: int = Field(default=300, ge=20, le=1_000)


class ReadFileInput(BaseModel):
    """仓库文件读取工具参数。"""

    path: str = Field(min_length=1, max_length=500, description="仓库内相对路径")
    start_line: int = Field(default=1, ge=1, le=100_000)
    max_lines: int = Field(default=160, ge=1, le=400)


class SearchCodeInput(BaseModel):
    """仓库代码搜索工具参数。"""

    query: str = Field(min_length=2, max_length=200, description="类名、方法名或代码片段")
    case_sensitive: bool = False
    max_results: int = Field(default=30, ge=1, le=100)


class RepositoryToolRunner:
    """执行已授权 MCP 工具并持久化工具事件。"""

    def __init__(
        self,
        *,
        analysis_id: str,
        role: AgentRole,
        allowed_tools: set[str],
        event_emitter: EventEmitter | None,
    ) -> None:
        self.analysis_id = analysis_id
        self.role = role
        self.allowed_tools = allowed_tools
        self.event_emitter = event_emitter
        self.call_count = 0

    async def call(self, tool_name: str, arguments: dict[str, Any]) -> str:
        if tool_name not in self.allowed_tools:
            raise PermissionError(f"{self.role.value} Agent 不允许调用 {tool_name}")
        settings = get_settings()
        if self.call_count >= settings.agent_max_tool_calls:
            raise RuntimeError("当前 Agent 的 MCP 工具调用次数已超限")
        self.call_count += 1

        call_id = uuid4().hex
        safe_arguments = _safe_arguments(arguments)
        await self._emit(
            "tool.started",
            f"调用 MCP 工具 {tool_name}",
            {"call_id": call_id, "tool": tool_name, "arguments": safe_arguments},
        )
        started = time.perf_counter()
        try:
            output = await call_mcp_tool(
                tool_name,
                {"analysis_id": self.analysis_id, **arguments},
            )
            duration_ms = round((time.perf_counter() - started) * 1_000)
            await self._emit(
                "tool.completed",
                f"MCP 工具 {tool_name} 完成（{duration_ms} ms，{len(output)} 字符）",
                {
                    "call_id": call_id,
                    "tool": tool_name,
                    "duration_ms": duration_ms,
                    "output_chars": len(output),
                    "preview": output[:500],
                },
            )
            return output
        except Exception as exc:
            await self._emit(
                "tool.failed",
                f"MCP 工具 {tool_name} 执行失败",
                {
                    "call_id": call_id,
                    "tool": tool_name,
                    "duration_ms": round((time.perf_counter() - started) * 1_000),
                    "error_type": type(exc).__name__,
                },
            )
            raise

    async def call_json(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        output = await self.call(tool_name, arguments)
        payload = json.loads(output)
        if not isinstance(payload, dict):
            raise ValueError(f"MCP 工具 {tool_name} 未返回 JSON 对象")
        return payload

    async def _emit(self, event_type: str, message: str, data: dict[str, Any]) -> None:
        if self.event_emitter is not None:
            await self.event_emitter(event_type, self.role, message, data)


def build_langchain_tools(
    *,
    runner: RepositoryToolRunner,
) -> list[StructuredTool]:
    """按 Agent 权限创建 LangChain 工具列表。"""

    tools: list[StructuredTool] = []
    if "list_repository_tree" in runner.allowed_tools:
        tools.append(
            StructuredTool.from_function(
                coroutine=_list_tree_call(runner),
                name="list_repository_tree",
                description="列出仓库文件，用于确认模块和包结构。只读。",
                args_schema=ListTreeInput,
            )
        )
    if "read_repository_file" in runner.allowed_tools:
        tools.append(
            StructuredTool.from_function(
                coroutine=_read_file_call(runner),
                name="read_repository_file",
                description="读取仓库内指定文件的行范围。只读，结果已脱敏。",
                args_schema=ReadFileInput,
            )
        )
    if "search_repository_code" in runner.allowed_tools:
        tools.append(
            StructuredTool.from_function(
                coroutine=_search_code_call(runner),
                name="search_repository_code",
                description="按字面量搜索仓库源码，返回文件、行号和脱敏上下文。只读。",
                args_schema=SearchCodeInput,
            )
        )
    return tools


def _list_tree_call(
    runner: RepositoryToolRunner,
) -> Callable[..., Awaitable[str]]:
    async def call(max_entries: int = 300) -> str:
        return await runner.call(
            "list_repository_tree",
            {"max_entries": max_entries},
        )

    return call


def _read_file_call(
    runner: RepositoryToolRunner,
) -> Callable[..., Awaitable[str]]:
    async def call(
        path: str,
        start_line: int = 1,
        max_lines: int = 160,
    ) -> str:
        return await runner.call(
            "read_repository_file",
            {
                "path": path,
                "start_line": start_line,
                "max_lines": max_lines,
            },
        )

    return call


def _search_code_call(
    runner: RepositoryToolRunner,
) -> Callable[..., Awaitable[str]]:
    async def call(
        query: str,
        case_sensitive: bool = False,
        max_results: int = 30,
    ) -> str:
        return await runner.call(
            "search_repository_code",
            {
                "query": query,
                "case_sensitive": case_sensitive,
                "max_results": max_results,
            },
        )

    return call


def _safe_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        str(key)[:80]: _safe_value(value)
        for key, value in list(arguments.items())[:20]
    }


def _safe_value(value: Any) -> Any:
    if isinstance(value, str):
        return value[:300]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if isinstance(value, list):
        return [_safe_value(item) for item in value[:10]]
    if isinstance(value, dict):
        return {
            str(key)[:80]: _safe_value(item)
            for key, item in list(value.items())[:20]
        }
    return str(value)[:300]
