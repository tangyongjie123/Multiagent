"""安全地克隆并扫描 Git 仓库。"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse
from uuid import UUID

from app.core.config import get_settings

IGNORED_DIRECTORIES = {
    ".git",
    ".idea",
    ".vscode",
    ".venv",
    "node_modules",
    "target",
    "build",
    "dist",
    "coverage",
    "__pycache__",
}
CODE_EXTENSIONS = {
    ".java": "Java",
    ".kt": "Kotlin",
    ".py": "Python",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".go": "Go",
    ".rs": "Rust",
    ".cs": "C#",
    ".xml": "XML",
    ".yml": "YAML",
    ".yaml": "YAML",
}
SOURCE_EXTENSIONS = {
    *CODE_EXTENSIONS,
    ".properties",
    ".json",
    ".toml",
    ".env",
    ".sh",
    ".sql",
}
BUILD_FILES = {
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "settings.gradle",
    "package.json",
    "pyproject.toml",
    "requirements.txt",
    "go.mod",
    "Cargo.toml",
}
SAFE_BRANCH = re.compile(r"^[A-Za-z0-9._/-]+$")


class RepositoryError(RuntimeError):
    """Git 仓库无法克隆或扫描。"""


def resolve_git_executable() -> str:
    """从配置、PATH 或 Windows 常见目录定位 Git。"""

    configured = get_settings().git_executable
    if configured and configured.strip():
        candidate = Path(configured.strip().strip('"'))
        if candidate.is_file():
            return str(candidate)
        raise RepositoryError(f"GIT_EXECUTABLE 指向的文件不存在：{candidate}")

    discovered = shutil.which("git")
    if discovered:
        return discovered

    if sys.platform == "win32":
        candidates = [
            Path(os.environ.get("PROGRAMFILES", "")) / "Git/cmd/git.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Git/cmd/git.exe",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Programs/Git/cmd/git.exe",
        ]
        for candidate in candidates:
            if candidate.is_file():
                return str(candidate)

    raise RepositoryError(
        "未找到 Git。请安装 Git，或在 .env 中配置 GIT_EXECUTABLE"
    )


@dataclass
class RepositorySnapshot:
    """一次静态仓库扫描结果。"""

    root: Path
    commit_sha: str | None
    file_count: int
    total_bytes: int
    languages: dict[str, int]
    build_files: list[str]
    test_files: list[str]
    entry_points: list[str]
    spring_indicators: list[str]
    tree: list[str]
    source_files: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "commit_sha": self.commit_sha,
            "file_count": self.file_count,
            "total_bytes": self.total_bytes,
            "languages": self.languages,
            "build_files": self.build_files,
            "test_files": self.test_files,
            "entry_points": self.entry_points,
            "spring_indicators": self.spring_indicators,
            "tree": self.tree[:500],
            "source_files": sorted(self.source_files),
        }


def validate_repository_url(url: str) -> tuple[str, str]:
    """校验 Git URL，返回规范化 URL 和主机名。

    仅允许配置的主机，并拒绝内嵌用户名、密码和非 HTTP(S) 协议。
    """

    parsed = urlparse(url.strip())
    if parsed.scheme not in {"https", "http"}:
        raise RepositoryError("仅支持 HTTP 或 HTTPS Git 地址")
    if parsed.username or parsed.password:
        raise RepositoryError("Git 地址中不得包含用户名或密码")
    host = (parsed.hostname or "").lower()
    if host not in get_settings().allowed_git_hosts:
        allowed = "、".join(sorted(get_settings().allowed_git_hosts))
        raise RepositoryError(f"当前仅允许克隆以下站点：{allowed}")
    if not parsed.path or not parsed.path.strip("/"):
        raise RepositoryError("Git 地址缺少仓库路径")
    return parsed.geturl(), host


def repository_name(url: str) -> str:
    """从 Git URL 提取仓库名称。"""

    name = Path(urlparse(url).path.rstrip("/")).name
    return name.removesuffix(".git") or "repository"


def repository_workspace(analysis_id: UUID) -> Path:
    """返回一次分析对应的仓库目录。"""

    return Path(__file__).resolve().parents[2] / "workspaces" / "repositories" / str(analysis_id)


async def clone_repository(
    url: str,
    branch: str | None,
    destination: Path,
) -> str | None:
    """浅克隆公开仓库并返回提交 SHA。"""

    normalized_url, _ = validate_repository_url(url)
    if branch and (not SAFE_BRANCH.fullmatch(branch) or branch.startswith("-")):
        raise RepositoryError("Git 分支名称不合法")
    git_executable = resolve_git_executable()

    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [git_executable, "clone", "--depth", "1", "--single-branch"]
    if branch:
        command.extend(["--branch", branch])
    command.extend([normalized_url, str(destination)])
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"

    process = await asyncio.to_thread(_start_clone_process, command, env)

    try:
        return_code, output = await asyncio.wait_for(
            asyncio.to_thread(
                _communicate_process,
                process,
                get_settings().git_clone_timeout_seconds,
            ),
            timeout=get_settings().git_clone_timeout_seconds,
        )
    except TimeoutError as exc:
        await _terminate_process(process)
        raise RepositoryError("Git 仓库克隆超时") from exc
    except asyncio.CancelledError:
        await _terminate_process(process)
        raise

    if return_code != 0:
        message = output[-2_000:]
        raise RepositoryError(f"Git 克隆失败：{message}")

    return await asyncio.to_thread(_read_commit_sync, destination)


def _scan_repository_sync(root: Path) -> RepositorySnapshot:
    """扫描仓库结构并提取有限数量的源码内容。"""

    settings = get_settings()
    max_bytes = settings.git_max_repository_mb * 1024 * 1024
    max_files = settings.git_max_files
    language_counts: Counter[str] = Counter()
    build_files: list[str] = []
    test_files: list[str] = []
    entry_points: list[str] = []
    spring_indicators: list[str] = []
    tree: list[str] = []
    source_files: dict[str, str] = {}
    file_count = 0
    total_bytes = 0

    for path in sorted(root.rglob("*")):
        # 不跟随软链接，避免仓库内容指向工作区外部。
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part in IGNORED_DIRECTORIES for part in relative.parts):
            continue
        file_count += 1
        if file_count > max_files:
            raise RepositoryError(f"仓库文件数超过限制 {max_files}")
        size = path.stat().st_size
        total_bytes += size
        if total_bytes > max_bytes:
            raise RepositoryError(
                f"仓库大小超过限制 {settings.git_max_repository_mb} MB"
            )
        relative_text = relative.as_posix()
        tree.append(relative_text)
        if path.name in BUILD_FILES:
            build_files.append(relative_text)
        suffix = path.suffix.lower()
        language = CODE_EXTENSIONS.get(suffix)
        if language:
            language_counts[language] += 1
        lowered = relative_text.lower()
        if any(part in lowered for part in ("/test/", "test.java", "spec.")):
            test_files.append(relative_text)
        if path.name.endswith("Application.java") or path.name in {
            "main.py",
            "manage.py",
        }:
            entry_points.append(relative_text)
        # source_files 有数量上限，防止把整个大型仓库发送给 Agent。
        if suffix in SOURCE_EXTENSIONS and len(source_files) < settings.git_analysis_max_files:
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "@SpringBootApplication" in content:
                spring_indicators.append(relative_text)
            source_files[relative_text] = content[
                : settings.git_analysis_max_file_chars
            ]

    return RepositorySnapshot(
        root=root,
        commit_sha=None,
        file_count=file_count,
        total_bytes=total_bytes,
        languages=dict(language_counts.most_common()),
        build_files=build_files[:50],
        test_files=test_files[:200],
        entry_points=entry_points[:50],
        spring_indicators=spring_indicators[:50],
        tree=tree,
        source_files=source_files,
    )


async def scan_repository(root: Path) -> RepositorySnapshot:
    """在线程中扫描仓库，避免阻塞 FastAPI 事件循环。"""

    snapshot = await asyncio.to_thread(_scan_repository_sync, root)
    snapshot.commit_sha = await asyncio.to_thread(_read_commit, root)
    return snapshot


def _read_commit_sync(root: Path) -> str | None:
    if not (root / ".git").exists():
        return None
    git_executable = resolve_git_executable()
    completed = subprocess.run(
        [git_executable, "rev-parse", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="ascii",
        errors="ignore",
        check=False,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    return completed.stdout.strip() if completed.returncode == 0 else None


def _read_commit(root: Path) -> str | None:
    return _read_commit_sync(root)


def _start_clone_process(
    command: list[str],
    env: dict[str, str],
) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )


def _communicate_process(
    process: subprocess.Popen[bytes],
    timeout: int,
) -> tuple[int, str]:
    try:
        stdout, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_process_tree_sync(process)
        return -1, "Git 仓库克隆超时"
    return process.returncode, stdout.decode("utf-8", errors="replace").strip()


async def _terminate_process(process: subprocess.Popen[bytes]) -> None:
    await asyncio.to_thread(_kill_process_tree_sync, process)


def _kill_process_tree_sync(process: subprocess.Popen[bytes]) -> None:
    if process.returncode is not None:
        return
    if sys.platform == "win32":
        subprocess.run(
            ["taskkill", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            check=False,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    else:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
