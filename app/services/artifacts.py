"""生成工程文件浏览、Diff 和 ZIP 打包。"""

from __future__ import annotations

import difflib
import io
import zipfile
from pathlib import Path
from uuid import UUID

from app.core.config import PROJECT_ROOT

IGNORED_PARTS = {"target", "__pycache__", ".git", ".idea", ".mypy_cache", ".ruff_cache"}
TEXT_SUFFIXES = {".java", ".xml", ".yml", ".yaml", ".md", ".json", ".properties", ".txt"}
MAX_VIEW_BYTES = 1_000_000


class ArtifactPathError(ValueError):
    """生成产物路径无效。"""


def run_workspace(run_id: UUID) -> Path:
    """返回运行工作区，不存在时抛出 FileNotFoundError。"""

    workspace = (PROJECT_ROOT / "workspaces" / str(run_id)).resolve()
    expected_root = (PROJECT_ROOT / "workspaces").resolve()
    if expected_root not in workspace.parents:
        raise ArtifactPathError("运行工作区路径无效")
    if not workspace.is_dir():
        raise FileNotFoundError("该运行尚未生成工作区")
    return workspace


def _workspace_files(workspace: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(workspace.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(workspace)
        if any(part in IGNORED_PARTS for part in relative.parts):
            continue
        files.append(path)
    return files


def list_workspace_files(workspace: Path) -> list[tuple[str, int]]:
    """返回工程相对路径和文件大小。"""

    return [
        (path.relative_to(workspace).as_posix(), path.stat().st_size)
        for path in _workspace_files(workspace)
    ]


def resolve_workspace_file(workspace: Path, relative_path: str) -> Path:
    """安全解析文件路径，阻止目录穿越。"""

    candidate = (workspace / relative_path).resolve()
    if workspace != candidate and workspace not in candidate.parents:
        raise ArtifactPathError("拒绝访问工作区外文件")
    if not candidate.is_file():
        raise FileNotFoundError("文件不存在")
    if candidate.stat().st_size > MAX_VIEW_BYTES:
        raise ArtifactPathError("文件过大，无法在线查看")
    return candidate


def build_workspace_zip(workspace: Path) -> bytes:
    """打包生成工程，排除 Maven 构建目录和缓存。"""

    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in _workspace_files(workspace):
            archive.write(path, arcname=path.relative_to(workspace).as_posix())
    return output.getvalue()


def build_workspace_diff(workspace: Path) -> tuple[int, int, str]:
    """把生成工程与空目录比较，输出初始新增 Diff。"""

    additions = 0
    patch_parts: list[str] = []
    for path in _workspace_files(workspace):
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        relative = path.relative_to(workspace).as_posix()
        content = path.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines(keepends=True)
        additions += len(lines)
        diff_lines = difflib.unified_diff(
            [],
            lines,
            fromfile="/dev/null",
            tofile=f"b/{relative}",
        )
        patch_parts.append(f"diff --git a/{relative} b/{relative}\n")
        patch_parts.extend(diff_lines)
    return additions, 0, "".join(patch_parts)
