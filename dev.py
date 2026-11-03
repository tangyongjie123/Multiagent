"""同时启动 FastAPI、MCP 工具服务和 React 开发服务器。"""

from __future__ import annotations

import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from app.core.config import get_settings

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"
FRONTEND_HOST = "127.0.0.1"
FRONTEND_PORT = 5173


def log(message: str) -> None:
    """输出带项目前缀的中文启动日志。"""

    print(f"[RepoGraph] {message}", flush=True)


def port_in_use(host: str, port: int) -> bool:
    """检查本机端口是否已被占用。"""

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        client.settimeout(0.5)
        return client.connect_ex((host, port)) == 0


def endpoint_ready(url: str) -> bool:
    """通过 HTTP 判断服务是否已经可访问。"""

    try:
        with urlopen(url, timeout=1) as response:
            status = int(response.status)
            return 200 <= status < 500
    except (OSError, URLError):
        return False


def wait_until_ready(
    process: subprocess.Popen[bytes],
    *,
    service_name: str,
    url: str,
    timeout_seconds: float = 30,
) -> None:
    """等待服务就绪，并在子进程提前退出时给出中文错误。"""

    deadline = time.monotonic() + timeout_seconds
    log(f"正在等待 {service_name} 就绪：{url}")
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"{service_name}启动失败，进程退出码为 {process.returncode}"
            )
        if endpoint_ready(url):
            log(f"{service_name} 已就绪：{url}")
            return
        time.sleep(0.5)
    raise RuntimeError(f"{service_name}在 {timeout_seconds:.0f} 秒内未完成启动")


def stop_processes(
    processes: tuple[tuple[str, subprocess.Popen[bytes]], ...],
) -> None:
    """按顺序关闭开发服务器子进程。"""

    for name, process in reversed(processes):
        if process.poll() is None:
            log(f"正在停止 {name}...")
            if sys.platform == "win32":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    check=False,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
            else:
                process.terminate()
    for name, process in reversed(processes):
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            log(f"{name}未及时退出，正在强制结束")
            process.kill()


def main() -> None:
    settings = get_settings()
    backend_host = "127.0.0.1"
    backend_port = settings.app_port
    backend_url = f"http://{backend_host}:{backend_port}"
    mcp_url = settings.effective_mcp_tool_url
    frontend_url = f"http://{FRONTEND_HOST}:{FRONTEND_PORT}"

    log("正在检查开发环境...")
    node = shutil.which("node")
    vite_entry = FRONTEND / "node_modules" / "vite" / "bin" / "vite.js"
    if node is None:
        raise RuntimeError("未找到 Node.js，请先安装 Node.js")
    if not vite_entry.is_file():
        raise RuntimeError("前端依赖未安装，请先进入 frontend 执行 npm install")

    node_version = subprocess.run(
        [node, "--version"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    ).stdout.strip()
    log(f"Python 版本：{sys.version.split()[0]}")
    log(f"Node.js 版本：{node_version or '未知'}")

    if port_in_use(backend_host, backend_port):
        raise RuntimeError(
            f"后端端口 {backend_port} 已被占用，请停止占用进程或修改 APP_PORT"
        )
    if port_in_use(FRONTEND_HOST, FRONTEND_PORT):
        raise RuntimeError(f"前端端口 {FRONTEND_PORT} 已被占用，请停止占用进程")

    backend: subprocess.Popen[bytes] | None = None
    frontend: subprocess.Popen[bytes] | None = None
    processes: tuple[tuple[str, subprocess.Popen[bytes]], ...] = ()
    try:
        log("正在启动 FastAPI 后端...")
        log(f"MCP 工具服务将随 FastAPI 启动，地址：{mcp_url}")
        backend = subprocess.Popen([sys.executable, str(ROOT / "main.py")], cwd=ROOT)

        log("正在启动 React 前端开发服务器...")
        frontend = subprocess.Popen(
            [
                node,
                str(vite_entry),
                "--host",
                FRONTEND_HOST,
                "--port",
                str(FRONTEND_PORT),
                "--strictPort",
            ],
            cwd=FRONTEND,
        )
        processes = (("FastAPI 后端", backend), ("React 前端", frontend))

        wait_until_ready(
            backend,
            service_name="FastAPI 后端",
            url=f"{backend_url}/health/live",
        )
        wait_until_ready(
            frontend,
            service_name="React 前端",
            url=frontend_url,
        )

        log("启动完成，开发环境已可用")
        log(f"可视化界面：{frontend_url}")
        log(f"接口文档：{backend_url}/docs")
        log(f"MCP 工具端点：{mcp_url}")
        log("按 Ctrl+C 同时停止前后端服务")

        while backend.poll() is None and frontend.poll() is None:
            time.sleep(0.5)
        if backend.poll() is not None:
            log(f"FastAPI 后端已退出，退出码：{backend.returncode}")
        if frontend.poll() is not None:
            log(f"React 前端已退出，退出码：{frontend.returncode}")
    except KeyboardInterrupt:
        log("收到停止信号，正在关闭开发环境...")
    except Exception as exc:
        log(f"启动失败：{exc}")
        raise
    finally:
        stop_processes(processes)
        log("开发环境已停止")


if __name__ == "__main__":
    main()
