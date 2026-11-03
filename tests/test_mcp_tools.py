"""MCP 仓库工具与 LangChain 工具包装测试。"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID, uuid4

import pytest

import app.agents.tools as agent_tools
import app.mcp.server as mcp_server_module
from app.agents.tools import (
    ARCHITECTURE_TOOLS,
    RepositoryToolRunner,
    build_langchain_tools,
    normalize_tool_name,
)
from app.domain.models import AgentRole


def _build_workspace(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    source = root / "src/main/java/example"
    source.mkdir(parents=True)
    (source / "DemoService.java").write_text(
        'class DemoService { String password = "super-secret-value"; }\n',
        encoding="utf-8",
    )
    test = root / "src/test/java/example"
    test.mkdir(parents=True)
    (test / "DemoServiceTest.java").write_text(
        "class DemoServiceTest { void testsDemoService() {} }\n",
        encoding="utf-8",
    )
    ignored = root / "node_modules/pkg"
    ignored.mkdir(parents=True)
    (ignored / "index.js").write_text("const ignored = true;", encoding="utf-8")
    return root


def test_common_model_tool_name_is_normalized() -> None:
    assert normalize_tool_name("read_repository_tree") == "list_repository_tree"
    assert normalize_tool_name("read_file") == "read_repository_file"
    assert normalize_tool_name("search_repository_code") == "search_repository_code"


@pytest.mark.asyncio
async def test_mcp_tools_read_search_and_redact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _build_workspace(tmp_path)
    analysis_id = uuid4()
    monkeypatch.setattr(
        mcp_server_module,
        "repository_workspace",
        lambda _: root,
    )

    file_result = await mcp_server_module.read_repository_file(
        str(analysis_id),
        "src/main/java/example/DemoService.java",
    )
    search_result = await mcp_server_module.search_repository_code(
        str(analysis_id),
        "password",
    )
    test_result = await mcp_server_module.find_related_tests(
        str(analysis_id),
        "DemoService",
    )
    tree_result = await mcp_server_module.list_repository_tree(str(analysis_id))

    assert "<REDACTED>" in file_result["content"]
    assert "super-secret-value" not in file_result["content"]
    assert search_result["matches"][0]["file_path"].endswith("DemoService.java")
    assert "super-secret-value" not in search_result["matches"][0]["preview"]
    assert test_result["matches"][0]["file_path"].endswith("DemoServiceTest.java")
    assert "node_modules/pkg/index.js" not in tree_result["entries"]


@pytest.mark.asyncio
async def test_mcp_tools_reject_path_escape(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = _build_workspace(tmp_path)
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")
    monkeypatch.setattr(
        mcp_server_module,
        "repository_workspace",
        lambda _: root,
    )

    with pytest.raises(ValueError, match="超出分析工作区"):
        await mcp_server_module.read_repository_file(
            str(uuid4()),
            "../outside.txt",
        )


@pytest.mark.asyncio
async def test_langchain_tool_uses_mcp_and_emits_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, dict[str, object]]] = []
    events: list[tuple[str, AgentRole, str, dict[str, object]]] = []

    async def fake_call(
        tool_name: str,
        arguments: dict[str, object],
    ) -> str:
        calls.append((tool_name, arguments))
        return json.dumps({"entries": ["src/App.java"], "count": 1})

    async def emitter(
        event_type: str,
        role: AgentRole,
        message: str,
        data: dict[str, object],
    ) -> None:
        events.append((event_type, role, message, data))

    monkeypatch.setattr(agent_tools, "call_mcp_tool", fake_call)
    runner = RepositoryToolRunner(
        analysis_id=str(UUID(int=1)),
        role=AgentRole.ARCHITECTURE,
        allowed_tools=ARCHITECTURE_TOOLS,
        event_emitter=emitter,
    )
    tool = build_langchain_tools(runner=runner)[0]

    result = await tool.ainvoke({"max_entries": 20})

    assert "src/App.java" in result
    assert calls == [
        (
            "list_repository_tree",
            {
                "analysis_id": str(UUID(int=1)),
                "max_entries": 20,
            },
        )
    ]
    assert [event[0] for event in events] == ["tool.started", "tool.completed"]


@pytest.mark.asyncio
async def test_langchain_tool_failure_emits_failed_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    async def failing_call(
        _tool_name: str,
        _arguments: dict[str, object],
    ) -> str:
        raise RuntimeError("tool unavailable")

    async def emitter(
        event_type: str,
        _role: AgentRole,
        _message: str,
        _data: dict[str, object],
    ) -> None:
        events.append(event_type)

    monkeypatch.setattr(agent_tools, "call_mcp_tool", failing_call)
    runner = RepositoryToolRunner(
        analysis_id=str(UUID(int=2)),
        role=AgentRole.ARCHITECTURE,
        allowed_tools=ARCHITECTURE_TOOLS,
        event_emitter=emitter,
    )
    tool = build_langchain_tools(runner=runner)[0]

    with pytest.raises(RuntimeError, match="tool unavailable"):
        await tool.ainvoke({"max_entries": 20})

    assert events == ["tool.started", "tool.failed"]
