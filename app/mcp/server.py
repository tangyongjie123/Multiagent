"""通过 MCP Streamable HTTP 暴露只读仓库工具。"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from uuid import UUID

from mcp.server.mcpserver import MCPServer

from app.services.redaction import redact_sensitive_text
from app.services.repository import (
    IGNORED_DIRECTORIES,
    READABLE_FILE_NAMES,
    SOURCE_EXTENSIONS,
    repository_workspace,
    scan_repository,
)
from app.services.static_analysis import run_static_analysis

MAX_READ_BYTES = 2 * 1024 * 1024
MAX_TOOL_OUTPUT_CHARS = 100_000

mcp_server = MCPServer(
    name="RepoGraph Tools",
    title="RepoGraph 只读仓库工具",
    version="0.1.0",
    instructions="这些工具仅用于分析隔离工作区中的公开仓库，不执行目标仓库代码。",
)


@mcp_server.tool(
    name="list_repository_tree",
    description="列出当前分析工作区中的文件，忽略依赖、构建产物和版本控制目录。",
)
async def list_repository_tree(
    analysis_id: str,
    max_entries: int = 300,
) -> dict[str, Any]:
    """返回受限数量的仓库相对路径。"""

    root = await asyncio.to_thread(_repository_root, analysis_id)
    limit = max(1, min(max_entries, 1_000))
    files = await asyncio.to_thread(_list_files, root, limit + 1)
    return {
        "entries": files[:limit],
        "count": min(len(files), limit),
        "truncated": len(files) > limit,
    }


@mcp_server.tool(
    name="read_repository_file",
    description="读取仓库内文本文件的指定行范围，路径必须位于当前分析工作区。",
)
async def read_repository_file(
    analysis_id: str,
    path: str,
    start_line: int = 1,
    max_lines: int = 160,
) -> dict[str, Any]:
    """读取工作区文本文件，并限制行数和返回长度。"""

    root = await asyncio.to_thread(_repository_root, analysis_id)
    try:
        file_path = await asyncio.to_thread(_safe_file, root, path)
    except (OSError, ValueError) as exc:
        # 非法文件类型或路径应作为可纠正的工具结果返回给模型，
        # 不能让一次读文件失败直接终止整个 Agent。
        return {
            "path": path,
            "content": "",
            "error": str(exc),
            "truncated": False,
        }
    content = await asyncio.to_thread(_read_text, file_path)
    lines = _redact(content).splitlines()
    start = max(1, min(start_line, len(lines) or 1))
    count = max(1, min(max_lines, 400))
    selected = lines[start - 1 : start - 1 + count]
    return {
        "path": file_path.relative_to(root).as_posix(),
        "start_line": start,
        "end_line": start + len(selected) - 1 if selected else start - 1,
        "content": "\n".join(selected),
        "truncated": start - 1 + len(selected) < len(lines),
    }


@mcp_server.tool(
    name="search_repository_code",
    description="在仓库文本源码中执行大小写可配置的字面量搜索，返回文件名、行号和脱敏上下文。",
)
async def search_repository_code(
    analysis_id: str,
    query: str,
    case_sensitive: bool = False,
    max_results: int = 30,
) -> dict[str, Any]:
    """执行字面量搜索，避免把用户输入当作正则表达式。"""

    if not 2 <= len(query.strip()) <= 200:
        raise ValueError("搜索词长度必须在 2 到 200 个字符之间")
    root = await asyncio.to_thread(_repository_root, analysis_id)
    limit = max(1, min(max_results, 100))
    matches = await asyncio.to_thread(
        _search_files,
        root,
        query.strip(),
        case_sensitive,
        limit,
    )
    return {
        "query": query.strip(),
        "matches": matches,
        "count": len(matches),
        "truncated": len(matches) >= limit,
    }


@mcp_server.tool(
    name="find_related_tests",
    description="根据类名、方法名或路径关键词查找相关测试文件及匹配行。",
)
async def find_related_tests(
    analysis_id: str,
    target: str,
    max_results: int = 20,
) -> dict[str, Any]:
    """按测试路径和内容匹配目标类名或方法名。"""

    if not 2 <= len(target.strip()) <= 200:
        raise ValueError("目标名称长度必须在 2 到 200 个字符之间")
    root = await asyncio.to_thread(_repository_root, analysis_id)
    limit = max(1, min(max_results, 50))
    matches = await asyncio.to_thread(_find_tests, root, target.strip(), limit)
    return {
        "target": target.strip(),
        "matches": matches,
        "count": len(matches),
        "truncated": len(matches) >= limit,
    }


@mcp_server.tool(
    name="run_static_rules",
    description="在隔离工作区运行项目内置的确定性安全与质量规则，不执行目标仓库代码。",
)
async def run_static_rules(analysis_id: str) -> dict[str, Any]:
    """运行项目自己的规则，不执行被审查仓库代码。"""

    root = await asyncio.to_thread(_repository_root, analysis_id)
    snapshot = await scan_repository(root)
    findings = run_static_analysis(snapshot)
    return {
        "findings": [finding.model_dump(mode="json") for finding in findings],
        "count": len(findings),
    }


def create_mcp_http_app() -> Any:
    """创建挂载到 FastAPI 的 MCP Streamable HTTP 应用。"""

    return mcp_server.streamable_http_app(
        streamable_http_path="/",
        host="127.0.0.1",
        stateless_http=True,
        max_request_body_size=1024 * 1024,
        session_idle_timeout=60,
        max_sessions=100,
    )


def _repository_root(analysis_id: str) -> Path:
    """解析并验证一次分析的工作区根目录。"""

    try:
        parsed_id = UUID(analysis_id)
    except ValueError as exc:
        raise ValueError("analysis_id 必须是合法 UUID") from exc
    root = repository_workspace(parsed_id).resolve()
    if not root.is_dir():
        raise ValueError("分析工作区不存在")
    return root


def _iter_files(root: Path) -> list[Path]:
    """遍历允许读取的普通文件，跳过依赖、构建产物和软链接。"""

    files: list[Path] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in IGNORED_DIRECTORIES or part == ".analysis" for part in relative.parts):
            continue
        files.append(path)
    return files


def _list_files(root: Path, limit: int) -> list[str]:
    """把文件路径转换为稳定的 POSIX 相对路径。"""

    return [path.relative_to(root).as_posix() for path in _iter_files(root)[:limit]]


def _safe_file(root: Path, relative_path: str) -> Path:
    """阻止绝对路径、路径穿越、软链接逃逸和超大文件读取。"""

    if "\x00" in relative_path:
        raise ValueError("文件路径包含非法字符")
    supplied = Path(relative_path)
    if supplied.is_absolute():
        raise ValueError("只允许读取仓库内的相对路径")
    candidate = (root / supplied).resolve(strict=True)
    if not candidate.is_relative_to(root):
        raise ValueError("文件路径超出分析工作区")
    if not candidate.is_file():
        raise ValueError("指定路径不是文件")
    if candidate.stat().st_size > MAX_READ_BYTES:
        raise ValueError("文件超过 MCP 读取大小限制")
    if (
        candidate.suffix.lower() not in SOURCE_EXTENSIONS
        and candidate.name not in READABLE_FILE_NAMES
    ):
        raise ValueError("MCP 只允许读取源码、配置和构建文本文件")
    return candidate


def _read_text(path: Path) -> str:
    """以 UTF-8 读取文本，无法解码的字节用替换字符处理。"""

    return path.read_text(encoding="utf-8", errors="replace")


def _search_files(
    root: Path,
    query: str,
    case_sensitive: bool,
    limit: int,
) -> list[dict[str, Any]]:
    """在源码和构建文件中执行有结果上限的字面量搜索。"""

    needle = query if case_sensitive else query.casefold()
    matches: list[dict[str, Any]] = []
    for path in _iter_files(root):
        if (
            path.suffix.lower() not in SOURCE_EXTENSIONS
            and path.name not in READABLE_FILE_NAMES
        ):
            continue
        if path.stat().st_size > MAX_READ_BYTES:
            continue
        try:
            content = _redact(_read_text(path))
        except OSError:
            continue
        for line_number, line in enumerate(content.splitlines(), start=1):
            haystack = line if case_sensitive else line.casefold()
            if needle in haystack:
                matches.append(
                    {
                        "file_path": path.relative_to(root).as_posix(),
                        "line": line_number,
                        "preview": line.strip()[:300],
                    }
                )
                if len(matches) >= limit:
                    return matches
    return matches


def _find_tests(root: Path, target: str, limit: int) -> list[dict[str, Any]]:
    """查找路径或内容中包含目标名称的测试文件。"""

    matches: list[dict[str, Any]] = []
    needle = target.casefold()
    for path in _iter_files(root):
        relative = path.relative_to(root).as_posix()
        lowered = relative.lower()
        is_test = "/test/" in lowered or lowered.endswith(
            (
                "test.java",
                "tests.py",
                "_test.py",
                "test.php",
                "spec.ts",
                "spec.js",
                ".test.ts",
                ".test.js",
            )
        )
        if not is_test:
            continue
        path_match = needle in lowered
        matched_lines: list[dict[str, Any]] = []
        if path.stat().st_size <= MAX_READ_BYTES:
            try:
                content = _redact(_read_text(path))
            except OSError:
                content = ""
            for line_number, line in enumerate(content.splitlines(), start=1):
                if needle in line.casefold():
                    matched_lines.append({"line": line_number, "preview": line.strip()[:300]})
                    if len(matched_lines) >= 5:
                        break
        if path_match or matched_lines:
            matches.append(
                {
                    "file_path": relative,
                    "path_match": path_match,
                    "matches": matched_lines,
                }
            )
            if len(matches) >= limit:
                break
    return matches


def _redact(content: str) -> str:
    """脱敏常见密钥赋值、URL 凭证和私钥块。"""

    return redact_sensitive_text(content)[:MAX_TOOL_OUTPUT_CHARS]
