"""同时启动 FastAPI 后端和 React 开发服务器。"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"


def main() -> None:
    node = shutil.which("node")
    vite_entry = FRONTEND / "node_modules" / "vite" / "bin" / "vite.js"
    if node is None:
        raise RuntimeError("未找到 Node.js，请先安装 Node.js")
    if not vite_entry.is_file():
        raise RuntimeError("前端依赖未安装，请先运行 npm install")

    backend = subprocess.Popen([sys.executable, str(ROOT / "main.py")], cwd=ROOT)
    frontend = subprocess.Popen(
        [node, str(vite_entry), "--host", "127.0.0.1"],
        cwd=FRONTEND,
    )
    try:
        while backend.poll() is None and frontend.poll() is None:
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        for process in (frontend, backend):
            if process.poll() is None:
                process.terminate()
        for process in (frontend, backend):
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    main()
