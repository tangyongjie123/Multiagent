"""在生成工作区中执行真实 Maven 测试。"""

from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MavenTestResult:
    """Maven 测试命令结果。"""

    command: str
    exit_code: int
    passed: bool
    output: str
    log_path: str


async def run_maven_tests(workspace: Path) -> MavenTestResult:
    """执行 Maven 测试并保存原始日志。"""

    log_path = workspace / "artifacts" / "maven-test.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    command = ["cmd.exe", "/d", "/c", "mvn", "-B", "test"]

    def execute() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            cwd=workspace,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
            check=False,
        )

    try:
        completed = await asyncio.to_thread(execute)
        output = f"{completed.stdout}\n{completed.stderr}".strip()
        exit_code = completed.returncode
    except subprocess.TimeoutExpired as exc:
        output = f"Maven 测试超时: {exc}"
        exit_code = -1

    log_path.write_text(output, encoding="utf-8")
    return MavenTestResult(
        command="mvn -B test",
        exit_code=exit_code,
        passed=exit_code == 0,
        output=output[-20_000:],
        log_path=str(log_path),
    )
