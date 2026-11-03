"""调用 RepoGraph MCP Streamable HTTP 工具服务。"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from mcp import ClientSession
from mcp import types as mcp_types
from mcp.client.streamable_http import streamable_http_client

from app.core.config import get_settings


class MCPToolError(RuntimeError):
    """MCP 工具调用失败。"""


async def call_mcp_tool(
    tool_name: str,
    arguments: dict[str, Any],
    *,
    timeout_seconds: float | None = None,
) -> str:
    """通过 Streamable HTTP 建立 MCP 会话并调用一个工具。

    每次调用使用独立会话，避免某个 Agent 的工具状态串到其他分析任务。
    """

    settings = get_settings()
    timeout = timeout_seconds or settings.mcp_tool_timeout_seconds

    async def invoke() -> str:
        async with (
            streamable_http_client(settings.effective_mcp_tool_url) as (
                read_stream,
                write_stream,
            ),
            ClientSession(read_stream, write_stream) as session,
        ):
            await session.initialize()
            result = await session.call_tool(tool_name, arguments)
            return _result_text(tool_name, result)

    try:
        return await asyncio.wait_for(invoke(), timeout=timeout)
    except TimeoutError as exc:
        raise MCPToolError(f"MCP 工具 {tool_name} 调用超时") from exc
    except MCPToolError:
        raise
    except Exception as exc:
        raise MCPToolError(
            f"MCP 工具 {tool_name} 调用失败：{type(exc).__name__}"
        ) from exc


def _result_text(tool_name: str, result: mcp_types.CallToolResult) -> str:
    """优先返回结构化内容，否则拼接文本内容。"""

    if result.is_error:
        details = _content_text(result)
        raise MCPToolError(details or f"MCP 工具 {tool_name} 返回错误")
    if result.structured_content is not None:
        return json.dumps(result.structured_content, ensure_ascii=False)
    text = _content_text(result)
    if not text:
        raise MCPToolError(f"MCP 工具 {tool_name} 未返回内容")
    return text


def _content_text(result: mcp_types.CallToolResult) -> str:
    """提取 MCP 响应中的纯文本部分。"""

    return "\n".join(
        item.text
        for item in result.content
        if isinstance(item, mcp_types.TextContent)
    ).strip()
