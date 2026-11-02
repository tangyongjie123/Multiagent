"""在 Windows 上使用兼容 psycopg 的事件循环启动 FastAPI。"""

from __future__ import annotations

import asyncio
import sys

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

import uvicorn

from app.core.config import get_settings


def selector_event_loop() -> asyncio.AbstractEventLoop:
    """为 Uvicorn 提供兼容 psycopg 的事件循环。"""

    return asyncio.SelectorEventLoop()


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        loop="scripts.run_api:selector_event_loop",
    )


if __name__ == "__main__":
    main()
