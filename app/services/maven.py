"""在生成工作区中执行真实 Maven 测试。"""

from __future__ import annotations

import asyncio
import subprocess
import sys
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

    if sys.platform == "win32":
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=workspace,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    else:
        process = await asyncio.create_subprocess_exec(
            *command,
            cwd=workspace,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )

    try:
        stdout, _ = await asyncio.wait_for(process.communicate(), timeout=300)
        output = stdout.decode("utf-8", errors="replace").strip()
        exit_code = process.returncode or 0
    except TimeoutError:
        await _stop_process_tree(process)
        output = "Maven 测试超时"
        exit_code = -1
    except asyncio.CancelledError:
        await _stop_process_tree(process)
        log_path.write_text("运行已取消，Maven 子进程已终止", encoding="utf-8")
        raise

    log_path.write_text(output, encoding="utf-8")
    return MavenTestResult(
        command="mvn -B test",
        exit_code=exit_code,
        passed=exit_code == 0,
        output=output[-20_000:],
        log_path=str(log_path),
    )


async def _stop_process_tree(process: asyncio.subprocess.Process) -> None:
    """终止 Maven 及其子 Java 进程。"""

    if process.returncode is not None:
        return
    if sys.platform == "win32":
        killer = await asyncio.create_subprocess_exec(
            "taskkill",
            "/PID",
            str(process.pid),
            "/T",
            "/F",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        await killer.wait()
    else:
        process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=10)
    except TimeoutError:
        process.kill()
        await process.wait()
